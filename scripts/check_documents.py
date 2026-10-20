"""Local, read-only document checks. Never edits documents or grants submission permission."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unicodedata
from zipfile import ZipFile
from xml.etree import ElementTree as ET

VERSION = '1.0.0'
HERE = Path(__file__).resolve().parent
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def json_file(path):
    return json.loads(Path(path).read_text())


def local(root, base, name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Missing required file path')
    path = (base / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Input/output path is outside the selected Jobs root')
    return path


def lookup(profile, path):
    value = profile
    for part in path:
        value = value[int(part)] if isinstance(value, list) else value[part]
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Required private profile value is missing')
    return value


def add(findings, code, severity, message, document=None, detail=None):
    payload = {'code': code, 'severity': severity, 'message': message, 'document': document, 'detail': detail}
    payload['id'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]
    findings.append(payload)


def docx_content(path):
    import docx
    document = docx.Document(path)
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    with ZipFile(path) as archive:
        tree = ET.fromstring(archive.read('word/document.xml'))
        unsafe = [name for name in ('tbl', 'txbxContent', 'vanish', 'webHidden', 'ins', 'del')
                  if tree.findall('.//w:' + name, NS)]
        for column in tree.findall('.//w:cols', NS):
            if column.get('{' + NS['w'] + '}num', '1') != '1':
                unsafe.append('multiple_columns')
    return paragraphs, unsafe


def pdf_content(path):
    import pdfplumber
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append({'text': page.extract_text() or '', 'chars': len(page.chars),
                          'off_page': sum(c['x0'] < -1 or c['x1'] > page.width + 1 or
                                          c['top'] < -1 or c['bottom'] > page.height + 1 for c in page.chars)})
    return pages


def compare_text(paragraphs, pdf_text):
    target = norm(pdf_text)
    missing = [i for i, p in enumerate(paragraphs) if norm(p) not in target]
    cursor = 0
    ordered = True
    for paragraph in paragraphs:
        needle = norm(paragraph)
        if len(needle) <= 55:
            continue
        position = target.find(needle, cursor)
        if position < 0:
            ordered = False
            break
        cursor = position + len(needle)
    # Extra PDF text can be headers/page numbers, but must be reviewed, not ignored.
    remainder = target
    for paragraph in paragraphs:
        remainder = remainder.replace(norm(paragraph), '', 1)
    return missing, ordered, remainder


def exact_checks(paragraphs, kind, profile, policy):
    findings = []
    body = '\n'.join(paragraphs)
    for field in ('name', 'phone', 'email'):
        if norm(lookup(profile, ['identity', field])) not in norm(body):
            findings.append('identity_' + field)
    if kind != 'cv':
        return findings
    for rule in policy['required_fields']:
        expected = lookup(profile, rule['path'])
        if rule.get('aliases') and rule.get('profile_value') != expected:
            raise ValueError('Private aliases are stale for ' + rule['id'])
        if not any(norm(value) in norm(body) for value in [expected] + rule.get('aliases', [])):
            findings.append(rule['id'])
    for rule in policy['employment_checks']:
        job = profile['employment'][rule['index']]
        if rule.get('aliases') and rule.get('profile_title') != job['title']:
            raise ValueError('Private job-title aliases are stale')
        indices = [i for i, p in enumerate(paragraphs) if norm(p) == norm(job['employer'])]
        if len(indices) != 1 or indices[0] + 1 >= len(paragraphs):
            findings.append('employment_heading_' + str(rule['index']))
            continue
        role_line = paragraphs[indices[0] + 1]
        role = role_line.split('|', 1)[0].strip()
        titles = [job['title']] + rule.get('aliases', [])
        if norm(role) not in [norm(x) for x in titles]:
            findings.append('employment_title_' + str(rule['index']))
        expected_dates = job.get('cv_dates')
        if not expected_dates:
            from datetime import datetime
            expected_dates = ' - '.join(datetime.strptime(job[x][:7], '%Y-%m').strftime('%b %Y') for x in ('start', 'end'))
        if norm(expected_dates) not in norm(role_line):
            findings.append('employment_dates_' + str(rule['index']))
    return findings


def check(root, manifest_path, node):
    root, manifest_path = Path(root).resolve(), Path(manifest_path).resolve()
    findings, artifacts, input_hashes = [], {}, {}
    report = {'schema_version': 1, 'checker_version': VERSION, 'status': 'blocked',
              'eligible_for_ready': False, 'findings': findings, 'artifacts': artifacts,
              'input_sha256': input_hashes,
              'limitation': 'Pattern checks and review attestations do not prove every claim or authorise submission.'}
    try:
        if not manifest_path.is_relative_to(root):
            raise ValueError('Manifest is outside Jobs root')
        private = root / 'private'
        profile_path = local(root, private, 'candidate-profile.json')
        policy_path = local(root, private, 'document-quality.json')
        facts_path = local(root, private, 'verified-document-facts.json')
        index_path = local(root, private, 'source-index.json')
        for path in (manifest_path, profile_path, policy_path, facts_path, index_path):
            input_hashes[str(path)] = digest(path)
        manifest, profile, policy, facts, index = map(json_file, (manifest_path, profile_path, policy_path, facts_path, index_path))
        if policy['schema_version'] != 1 or facts['schema_version'] != 1:
            raise ValueError('Unsupported private checks schema')
        if not facts['facts'] or not policy['employment_checks'] or not policy['required_fields']:
            raise ValueError('Required facts or profile checks are empty')
        source_index = {s['id']: s for s in index['sources']}
        corpus = []
        for fact in facts['facts']:
            if fact.get('status') != 'verified_positive' or not fact.get('text', '').strip() or not fact.get('refs'):
                raise ValueError('Facts must be verified positive evidence with provenance')
            if re.search(r'\b(?:not confirmed|no confirmed|unsupported|unverified|do not claim|unknown)\b', fact['text'], re.I):
                raise ValueError('An uncertainty/caution was placed in positive evidence; review and separate it')
            for ref in fact['refs']:
                if not ref.get('locator'):
                    raise ValueError('A fact source locator is missing')
                source = source_index[ref['source_id']]
                if source['id'].startswith('benchmark'):
                    raise ValueError('Benchmarks cannot be independent factual evidence')
                source_path = local(root, root, source['path'])
                input_hashes[str(source_path)] = digest(source_path)
            corpus.append(fact['text'])
        # Whitelist positive structured fields, never profile cautions or unknowns.
        corpus.extend(lookup(profile, ['identity', field]) for field in ('name', 'phone', 'email'))
        for job in profile['employment']:
            corpus.extend([job['employer'], job['title']])
        for item in profile['education']:
            corpus.extend(item[field] for field in ('qualification', 'institution', 'award') if item.get(field))
        corpus.extend(item['name'] for item in profile.get('certifications', []))
        corpus_text = '\n\n'.join(corpus)
        fact_ids = {f['id']: f for f in facts['facts']}
        for alias in policy['tool_aliases']:
            if not alias['from'] or not alias['to'] or alias['to'] not in fact_ids[alias['fact_id']]['text']:
                raise ValueError('Tool alias lacks positive factual evidence')
        vendor = HERE / 'vendor/career-ops'
        provenance = json_file(vendor / 'PROVENANCE.json')
        for name, expected in provenance['sha256'].items():
            if digest(vendor / name) != expected:
                raise ValueError('Pinned checker dependency changed: ' + name)
        report['upstream'] = {k: provenance[k] for k in ('version', 'commit')}
        evidence_path = local(root, manifest_path.parent, manifest['evidence_map'])
        if not evidence_path.read_text().strip():
            raise ValueError('Evidence map is empty')
        input_hashes[str(evidence_path)] = digest(evidence_path)
        if manifest.get('unresolved_claims') != []:
            add(findings, 'unresolved_claims', 'block', 'Resolve the recorded unsupported claims.')
        if manifest.get('qa', {}).get('issues'):
            add(findings, 'unresolved_layout', 'block', 'Resolve the recorded visual/layout issues.')
        if manifest['output_mode'] not in ('seek_pdf', 'manual_docx'):
            raise ValueError('Unsupported output mode')
        if manifest.get('cover_requested') is not True and (manifest.get('cover_docx') or manifest.get('cover_pdf')):
            add(findings, 'unrequested_cover', 'block', 'A supporting document was not explicitly requested.')
        if manifest.get('cover_requested') and not manifest.get('cover_requirement'):
            add(findings, 'cover_requirement', 'block', 'Record the explicit request for a supporting document.')
        kinds = ['cv'] + (['cover'] if manifest.get('cover_requested') else [])
        with tempfile.TemporaryDirectory(prefix='document-checks-') as temporary:
            temp = Path(temporary)
            source = temp / 'positive.txt'
            config = temp / 'phrases.json'
            source.write_text(corpus_text)
            config.write_text(json.dumps({'allow_metrics': [], 'allow_facts': [], 'forbidden_phrases': [], 'warn_phrases': []}))
            source.chmod(0o600)
            config.chmod(0o600)
            for kind in kinds:
                word = local(root, manifest_path.parent, manifest[kind + '_docx'])
                if word.suffix.lower() != '.docx':
                    raise ValueError('Editable source must be DOCX')
                pdf_name = manifest.get(kind + '_pdf') or manifest.get('qa', {}).get('rendered_pdfs', {}).get(kind)
                pdf = local(root, manifest_path.parent, pdf_name)
                if pdf.suffix.lower() != '.pdf':
                    raise ValueError('A PDF render is required')
                if manifest['output_mode'] == 'seek_pdf' and not manifest.get(kind + '_pdf'):
                    raise ValueError('SEEK submission PDF is missing')
                for path in (word, pdf):
                    artifacts[str(path)] = digest(path)
                paragraphs, unsafe = docx_content(word)
                pages = pdf_content(pdf)
                if not paragraphs or not pages or any(p['chars'] < 30 for p in pages):
                    add(findings, 'text_layer', 'block', 'Empty document or missing PDF text layer.', kind)
                if unsafe:
                    add(findings, 'word_structure', 'block', 'Unsupported Word structure, hidden content or unresolved tracked changes.', kind, unsafe)
                if any(p['off_page'] for p in pages):
                    add(findings, 'off_page', 'block', 'PDF text extends outside the page.', kind)
                pdf_text = '\n'.join(p['text'] for p in pages)
                missing, ordered, extra = compare_text(paragraphs, pdf_text)
                if missing or not ordered:
                    add(findings, 'word_pdf_mismatch', 'block', 'PDF text does not preserve the Word content/order.', kind, missing)
                if extra:
                    add(findings, 'extra_pdf_text', 'review', 'Review PDF-only text, including headers and page numbers.', kind, extra)
                for code in exact_checks(paragraphs, kind, profile, policy):
                    add(findings, code, 'block', 'Document differs from required private profile facts.', kind)
                label_text = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', '\n'.join(paragraphs) + pdf_text)).casefold()
                for phrase in policy['forbidden_phrases']:
                    if re.sub(r'\s+', ' ', phrase).casefold() in label_text:
                        add(findings, 'internal_label', 'block', 'Remove an internal or prohibited label.', kind, phrase)
                for risk in policy['review_patterns']:
                    if re.search(risk['pattern'], '\n'.join(paragraphs) + '\n' + pdf_text, re.I):
                        add(findings, 'claim_review', 'review', risk['reason'], kind, risk['id'])
                payload = {'sourcePath': str(source), 'configPath': str(config), 'paragraphs': paragraphs, 'aliases': policy['tool_aliases']}
                proc = subprocess.run([node, str(HERE / 'fact_adapter.mjs')], input=json.dumps(payload),
                                      text=True, capture_output=True, timeout=60, check=True)
                for item in json.loads(proc.stdout):
                    add(findings, 'fact_' + item['code'], 'review', 'Verify this pattern-based finding against its source; do not silently whitelist it.', kind, item)
                review = manifest.get('document_review', {}).get(kind, {})
                current = {'docx_sha256': digest(word), 'pdf_sha256': digest(pdf), 'pages': len(pages)}
                if not all(review.get(k) == v for k, v in current.items()) or not all(review.get(k) is True for k in ('all_pages_visually_checked', 'evidence_checked')) or not review.get('reviewed_on') or not review.get('reviewer'):
                    add(findings, 'review_attestation', 'block', 'Current files need hash-bound visual and evidence review.', kind)
                if review.get('evidence_map_sha256') != digest(evidence_path):
                    add(findings, 'evidence_review_stale', 'block', 'Evidence-map review is missing or stale.', kind)
                for finding in [f for f in findings if f['document'] == kind and f['severity'] == 'review']:
                    resolution = review.get('resolutions', {}).get(finding['id'], {})
                    if resolution.get('decision') == 'verified' and resolution.get('reason') and resolution.get('source_refs'):
                        valid = all(
                            (ref == 'visual_inspection' and finding['code'] == 'extra_pdf_text') or
                            (ref in source_index and not ref.startswith('benchmark') and
                             str(local(root, root, source_index[ref]['path'])) in input_hashes)
                            for ref in resolution['source_refs'])
                        if valid:
                            finding['resolution'] = resolution
        # Bind the review to private inputs too: changing evidence must invalidate
        # an old approval even when the candidate-facing file is unchanged.
        review_inputs = manifest.get('document_review', {}).get('input_sha256', {})
        if any(review_inputs.get(p) != h for p, h in input_hashes.items() if p != str(manifest_path)):
            add(findings, 'source_review_stale', 'block', 'Private inputs changed or have not been bound to the review.')
        if any(digest(Path(p)) != h for p, h in {**input_hashes, **artifacts}.items()):
            add(findings, 'changed_during_check', 'block', 'An input changed during checking; rerun.')
        if not any(f['severity'] == 'block' for f in findings):
            report['status'] = 'review_required' if any(f['severity'] == 'review' and not f.get('resolution') for f in findings) else 'checks_passed'
            report['eligible_for_ready'] = report['status'] == 'checks_passed'
    except Exception as error:
        add(findings, 'check_failed', 'block', f'Required check could not complete: {type(error).__name__}: {error}')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--node', default='node')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = local(root, Path.cwd(), args.output)
    if not output.name.endswith('.document-checks.json') or output.is_symlink():
        parser.error('Output must be a local *.document-checks.json report')
    if output.exists() and json_file(output).get('checker_version') is None:
        parser.error('Refusing to overwrite a non-checker file')
    report = check(root, args.manifest, args.node)
    if str(output) in {**report['input_sha256'], **report['artifacts']}:
        parser.error('Refusing to overwrite an input file')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=output.parent, delete=False) as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
        temporary = Path(stream.name)
    temporary.chmod(0o600)
    os.replace(temporary, output)
    print(json.dumps({'status': report['status'], 'eligible_for_ready': report['eligible_for_ready'], 'report': str(output)}))
    return 0 if report['eligible_for_ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
