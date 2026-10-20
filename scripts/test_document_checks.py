"""Synthetic regression fixtures only; never uses a real candidate's files."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_documents as checker


class DocumentChecksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'private').mkdir()
        self.node = os.environ.get('CHECKER_NODE', 'node')
        self.manifest_path = self.root / 'manifest.json'
        self.profile = {
            'identity': {'name': 'Example Candidate', 'phone': '+00 12345678', 'email': 'example@example.test'},
            'employment': [{'employer': 'Example Research', 'title': 'Research Intern',
                            'start': '2024-01', 'end': '2024-06', 'cv_dates': 'Jan 2024 - Jun 2024'}],
            'education': [{'qualification': 'Bachelor of Science', 'institution': 'Example University'}],
            'certifications': [],
        }
        self.policy = {
            'schema_version': 1,
            'required_fields': [{'id': 'degree', 'path': ['education', 0, 'qualification']}],
            'employment_checks': [{'index': 0}],
            'tool_aliases': [{'from': 'Python/Flask', 'to': 'Python and Flask', 'fact_id': 'tools'}],
            'forbidden_phrases': ['Tailored CV for'],
            'review_patterns': [{'id': 'statutory', 'pattern': 'statutory interviews', 'reason': 'Verify scope.'}],
        }
        self.facts = {'schema_version': 1, 'facts': [
            {'id': 'tools', 'status': 'verified_positive', 'text': 'Built a project using Python and Flask.',
             'refs': [{'source_id': 'original', 'locator': 'Projects'}]},
        ]}
        self.index = {'sources': [{'id': 'original', 'path': 'original.txt', 'purpose': 'Original source'}]}
        self.paragraphs = [
            'Example Candidate', '+00 12345678 | example@example.test', 'EXPERIENCE', 'Example Research',
            'Research Intern | Example City | Jan 2024 - Jun 2024',
            'Built a project using Python/Flask.', 'EDUCATION', 'Bachelor of Science | Example University',
        ]
        for name in ('cv.docx', 'cv.pdf', 'evidence.md', 'original.txt'):
            (self.root / name).write_text('Synthetic test contents for ' + name)
        self.manifest = {'job_url': 'https://nz.seek.com/job/12345678', 'output_mode': 'seek_pdf',
                         'cv_docx': 'cv.docx', 'cv_pdf': 'cv.pdf', 'cover_requested': False,
                         'evidence_map': 'evidence.md', 'unresolved_claims': []}
        self.save_private()
        self.save_manifest()
        self.pdf_extra, self.unsafe = '', []
        self.doc_mock = patch.object(checker, 'docx_content', side_effect=lambda _: (self.paragraphs, self.unsafe))
        self.pdf_mock = patch.object(checker, 'pdf_content', side_effect=lambda _: [
            {'text': '\n'.join(self.paragraphs) + self.pdf_extra, 'chars': 500, 'off_page': 0}])
        self.doc_mock.start()
        self.pdf_mock.start()
        self.addCleanup(self.doc_mock.stop)
        self.addCleanup(self.pdf_mock.stop)

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def save_private(self):
        for name, data in [('candidate-profile', self.profile), ('document-quality', self.policy),
                           ('verified-document-facts', self.facts), ('source-index', self.index)]:
            self.write('private/' + name + '.json', data)

    def save_manifest(self):
        self.write('manifest.json', self.manifest)

    def run_check(self):
        return checker.check(self.root, self.manifest_path, self.node)

    def attest_synthetic_review(self):
        # The generated fixture is known and reviewed by construction. This is
        # deliberately test-only; never auto-attest a real candidate's documents.
        report = self.run_check()
        self.manifest['document_review'] = {
            'input_sha256': {p: h for p, h in report['input_sha256'].items() if p != str(self.manifest_path)},
            'cv': {'docx_sha256': checker.digest(self.root / 'cv.docx'),
                   'pdf_sha256': checker.digest(self.root / 'cv.pdf'),
                   'evidence_map_sha256': checker.digest(self.root / 'evidence.md'),
                   'pages': 1, 'all_pages_visually_checked': True, 'evidence_checked': True,
                   'reviewer': 'Synthetic test fixture', 'reviewed_on': '2026-01-01', 'resolutions': {}},
        }
        self.save_manifest()

    def codes(self, result=None):
        return {f['code'] for f in (result or self.run_check())['findings']}

    def test_clean_requires_review_then_passes(self):
        self.assertFalse(self.run_check()['eligible_for_ready'])
        self.attest_synthetic_review()
        self.assertEqual(self.run_check()['status'], 'checks_passed')

    def test_no_source_fails_closed(self):
        (self.root / 'original.txt').unlink()
        self.assertIn('check_failed', self.codes())

    def test_no_configuration_fails_closed(self):
        (self.root / 'private/document-quality.json').unlink()
        self.assertIn('check_failed', self.codes())

    def test_empty_facts_fail_closed(self):
        self.facts['facts'] = []
        self.save_private()
        self.assertIn('check_failed', self.codes())

    def test_negative_evidence_status_rejected(self):
        self.facts['facts'][0]['status'] = 'unknown'
        self.save_private()
        self.assertIn('check_failed', self.codes())

    def test_negative_caution_cannot_be_positive_evidence(self):
        self.facts['facts'][0]['text'] = 'No confirmed Databricks experience.'
        self.save_private()
        self.assertIn('check_failed', self.codes())

    def test_benchmark_is_not_positive_source(self):
        self.index['sources'][0]['id'] = 'benchmark_cv'
        self.facts['facts'][0]['refs'][0]['source_id'] = 'benchmark_cv'
        self.save_private()
        self.assertIn('check_failed', self.codes())

    def test_wrong_contact(self):
        self.paragraphs[1] = '+00 99999999 | example@example.test'
        self.assertIn('identity_phone', self.codes())

    def test_changed_title_cannot_hide_behind_summary(self):
        self.paragraphs[4] = self.paragraphs[4].replace('Research Intern', 'Research Director')
        self.paragraphs.append('Previously a Research Intern.')
        self.assertIn('employment_title_0', self.codes())

    def test_present_date_blocked(self):
        self.paragraphs[4] = self.paragraphs[4].replace('Jun 2024', 'Present')
        self.assertIn('employment_dates_0', self.codes())

    def test_missing_qualification(self):
        self.paragraphs[-1] = 'Doctor of Science | Example University'
        self.assertIn('degree', self.codes())

    def test_source_change_invalidates_review(self):
        self.attest_synthetic_review()
        (self.root / 'original.txt').write_text('Changed source')
        self.assertIn('source_review_stale', self.codes())

    def test_doc_change_invalidates_review(self):
        self.attest_synthetic_review()
        (self.root / 'cv.pdf').write_text('Changed PDF')
        self.assertIn('review_attestation', self.codes())

    def test_hidden_word_content_blocks(self):
        self.unsafe = ['vanish']
        self.assertIn('word_structure', self.codes())

    def test_missing_pdf_blocks(self):
        (self.root / 'cv.pdf').unlink()
        self.assertIn('check_failed', self.codes())

    def test_actual_pipeline_detects_mismatched_pdf(self):
        with patch.object(checker, 'pdf_content', return_value=[{'text': 'Different CV', 'chars': 500, 'off_page': 0}]):
            self.assertIn('word_pdf_mismatch', self.codes())

    def test_off_page_pdf_blocks(self):
        with patch.object(checker, 'pdf_content', return_value=[{'text': '\n'.join(self.paragraphs), 'chars': 500, 'off_page': 1}]):
            self.assertIn('off_page', self.codes())

    def test_empty_pdf_blocks(self):
        with patch.object(checker, 'pdf_content', return_value=[{'text': '', 'chars': 0, 'off_page': 0}]):
            self.assertIn('text_layer', self.codes())

    def test_corrupt_source_config_fails_closed(self):
        (self.root / 'private/document-quality.json').write_text('{broken')
        self.assertIn('check_failed', self.codes())

    def test_unresolved_claim_blocks(self):
        self.manifest['unresolved_claims'] = ['Unverified responsibility']
        self.save_manifest()
        self.assertIn('unresolved_claims', self.codes())

    def test_recorded_layout_issue_blocks(self):
        self.manifest['qa'] = {'issues': ['Clipped paragraph']}
        self.save_manifest()
        self.attest_synthetic_review()
        self.assertIn('unresolved_layout', self.codes())
        self.assertFalse(self.run_check()['eligible_for_ready'])

    def test_unrequested_cover_blocks(self):
        self.manifest['cover_pdf'] = 'unrequested.pdf'
        self.save_manifest()
        self.assertIn('unrequested_cover', self.codes())

    def test_outside_root_is_rejected(self):
        self.manifest['cv_pdf'] = '../outside.pdf'
        self.save_manifest()
        self.assertIn('check_failed', self.codes())

    def test_manual_docx_requires_render(self):
        self.manifest['output_mode'] = 'manual_docx'
        self.manifest['cv_pdf'] = None
        self.save_manifest()
        self.assertIn('check_failed', self.codes())
        self.manifest['qa'] = {'rendered_pdfs': {'cv': 'cv.pdf'}}
        self.save_manifest()
        self.attest_synthetic_review()
        self.assertEqual(self.run_check()['status'], 'checks_passed')

    def test_paragraphs_prevent_false_quantity(self):
        self.paragraphs.extend(['Graduation | 2011', 'CERTIFICATIONS'])
        self.assertNotIn('fact_metric', self.codes())

    def test_alias_does_not_hide_unsupported_tool(self):
        self.paragraphs.append('Built a system using Python/Flask and Databricks.')
        self.attest_synthetic_review()
        report = self.run_check()
        self.assertEqual(report['status'], 'review_required')
        self.assertTrue(any(f['code'] == 'fact_tool' and f['detail']['value'] == 'databricks' for f in report['findings']))

    def test_metric_needs_review(self):
        self.paragraphs.append('Managed 900 staff.')
        self.attest_synthetic_review()
        self.assertEqual(self.run_check()['status'], 'review_required')
        self.assertIn('fact_metric', self.codes())

    def test_internal_label_not_waivable(self):
        self.paragraphs.append('Tailored CV for Example Employer')
        self.attest_synthetic_review()
        self.assertEqual(self.run_check()['status'], 'blocked')

    def test_semantic_risk_pattern_needs_review(self):
        self.paragraphs.append('Conducted statutory interviews.')
        self.attest_synthetic_review()
        self.assertEqual(self.run_check()['status'], 'review_required')
        self.assertIn('claim_review', self.codes())

    def test_pdf_only_text_not_silently_ignored(self):
        self.pdf_extra = '\nPage 1'
        self.attest_synthetic_review()
        report = self.run_check()
        finding = next(f for f in report['findings'] if f['code'] == 'extra_pdf_text')
        self.assertEqual(report['status'], 'review_required')
        self.manifest['document_review']['cv']['resolutions'][finding['id']] = {
            'decision': 'verified', 'reason': 'The known synthetic footer is the only extra text.',
            'source_refs': ['visual_inspection']}
        self.save_manifest()
        self.assertEqual(self.run_check()['status'], 'checks_passed')

    def test_visual_review_cannot_establish_experience(self):
        self.paragraphs.append('Managed 900 staff.')
        self.attest_synthetic_review()
        finding = next(f for f in self.run_check()['findings'] if f['code'] == 'fact_metric')
        self.manifest['document_review']['cv']['resolutions'][finding['id']] = {
            'decision': 'verified', 'reason': 'Looks fine.', 'source_refs': ['visual_inspection']}
        self.save_manifest()
        self.assertEqual(self.run_check()['status'], 'review_required')

    def test_missing_node_fails_closed(self):
        self.node = str(self.root / 'no-node')
        self.assertIn('check_failed', self.codes())

    def test_text_mismatch_and_order(self):
        paragraphs = ['Long evidence paragraph ' * 5, 'Second evidence paragraph ' * 5]
        missing, ordered, _ = checker.compare_text(paragraphs, paragraphs[1] + paragraphs[0])
        self.assertFalse(missing)
        self.assertFalse(ordered)
        self.assertTrue(checker.compare_text(paragraphs, 'Unrelated content')[0])

    def test_stale_title_alias_rejected(self):
        self.policy['employment_checks'][0].update({'profile_title': 'Old Title', 'aliases': ['Research Intern']})
        self.save_private()
        self.assertIn('check_failed', self.codes())


if __name__ == '__main__':
    unittest.main()
