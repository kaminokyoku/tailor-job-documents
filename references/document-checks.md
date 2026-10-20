# Offline Document Checks

Use after drafting/rendering and again immediately before a future upload. This adds checks; it never generates claims, renders files, submits applications or changes the application history. Only the fact-checking helper and its dependencies are vendored from Career Ops. See `scripts/vendor/career-ops/PROVENANCE.json` and its MIT license. Do not replace them with a moving checkout or enable its scanner/AI clients.

## Private Configuration

All candidate-specific values stay under `JOBS_ROOT/private`, not in the skill or its tests:

- `candidate-profile.json`: current identity, employment, qualifications and certifications. Existing explicit corrections remain authoritative.
- `source-index.json`: source IDs and root-relative paths. Include explicit-answer sources if used; do not feed entire screening files to the checker.
- `verified-document-facts.json`: `schema_version: 1`, `facts` array. Each item has `id`, `status: verified_positive`, `text`, and `refs: [{source_id, locator}]`. Manually verify each statement against its source and preserve context. Include positive evidence only: no unknowns, warnings, job requirements or benchmark-only claims. Do not automatically copy the evidence bank into this file.
- `document-quality.json`: `schema_version: 1`; `required_fields` with `id` and a `path` array into the profile; optional `aliases` bound to the exact `profile_value`; `employment_checks` with profile `index` and optional title `aliases` bound to `profile_title`; `tool_aliases` with `from`, `to`, `fact_id`; `forbidden_phrases`; and `review_patterns` with `id`, `pattern`, `reason`. No blanket allowlists. Regex patterns raise review findings, not new facts.

For a new candidate, populate these from verified private sources. Missing/empty configuration is a blocking condition, not permission to borrow another candidate's settings. Update aliases only after reviewing their meaning. Unknown career facts stay unknown. Inspect positive facts again when their original sources change; never rubber-stamp new hashes.

## Document Manifest Additions

Retain the existing manifest fields. Editable DOCX source is required for both output modes. Each document needs a PDF: the submission PDF for `seek_pdf`, or `qa.rendered_pdfs.cv` / `.cover` for manual Word output. Paths resolve relative to the manifest and must stay inside `JOBS_ROOT`; keep QA renders within the run folder. A cover letter still requires an explicit request.

The exact employment check expects an employer paragraph followed by a role line in the form `Formal title | Location | Mon YYYY - Mon YYYY`. Verified title abbreviations belong in private configuration. This matches the current CV layout; do not silently disable the check for a different layout.

Add `document_review` to the manifest after actually reviewing the evidence and every rendered page:

```json
{
  "document_review": {
    "input_sha256": {},
    "cv": {
      "docx_sha256": "SHA256_OF_REVIEWED_WORD",
      "pdf_sha256": "SHA256_OF_REVIEWED_PDF",
      "evidence_map_sha256": "SHA256_OF_REVIEWED_MAP",
      "pages": 2,
      "all_pages_visually_checked": true,
      "evidence_checked": true,
      "reviewed_on": "ISO_DATE",
      "reviewer": "Reviewer identity",
      "resolutions": {}
    }
  }
}
```

Include an analogous `cover` entry only when present. `input_sha256` records the checker report's private source/config/evidence hashes, excluding the manifest itself. This is an attestation of completed review, not something to fill automatically just to make a test pass. Review covers the meaning, scope and source of every substantive claim, including claims that the pattern checker cannot recognise. Resolve discrepancies or mark blocked; do not infer new facts from a generated CV.

## Run And Resolve

Use bundled Python with `python-docx` and `pdfplumber`, and bundled Node.js (18+); discover them through the workspace-dependency tool. No new service, package install or network access is needed.

```sh
"$PYTHON" scripts/check_documents.py --root "$JOBS_ROOT" \
  --manifest "$RUN_DIR/job Document Manifest.json" \
  --output "$RUN_DIR/job.document-checks.json" --node "$NODE"
```

Exit 0 means `checks_passed` and `eligible_for_ready: true`; exit 2 means blocked or review required. Read the report even on a nonzero exit. A missing runtime, unreadable file, stale source, changed dependency or incomplete review must stop readiness. Never reuse an old successful report after a failed run.

Findings with severity `block` cannot be waived. Fix their cause and rerun. A `review` finding may be a genuine problem or a false alarm; inspect its exact paragraph and source. Correct unsupported content. Only a verified false alarm may receive a resolution under `document_review.cv.resolutions` (or `cover`), keyed by the report finding ID:

```json
{"decision": "verified", "reason": "Specific explanation grounded in the actual evidence", "source_refs": ["source_id"]}
```

Use `visual_inspection` only for layout/footer text, never to establish experience. These resolutions are bound to reviewed document and source hashes. Do not automatically dismiss unknown tools, quantities or language-coverage warnings. PDF-only text must be inspected too; it may be a normal footer or an unintended claim. All warnings stay visible in the report, even when resolved.

The helper does not change the manifest to ready. Set it ready only after a successful check and all existing job-specific requirements. Add `document_checks: {"report": "job.document-checks.json", "checker_version": "1.0.0"}` to the manifest. Rerun after this manifest edit and before upload. The calling skill checks current report status and hashes; a saved ready label alone is insufficient.

Historical submissions are not retroactively rewritten or resubmitted. An older pending pack without review metadata needs fresh checks before any future upload. There is no new authority to apply, change a reservation, or answer a screening question.

## Changed Private Inputs

A private answer added for another job can invalidate a pending pack's source hashes even when its Word/PDF files did not change. Treat that as a real review checkpoint, not a reason to weaken the checker or refresh every pack's hashes.

1. Run the checker and read the stale-input findings. Compare the previously reviewed source content with the current content using a retained snapshot or a reliable structured diff. Hashes alone do not explain the change. If the previous content cannot be established, perform a fresh full source/evidence review instead of asserting the change was unrelated.
2. Identify changed facts, their provenance and exact job/question scope. Check their effect on the CV, supporting document, evidence map, aliases, positive-fact corpus and prior finding resolutions. Keep personal data in the private workspace and avoid copying whole private files into logs.
3. If meaning or claims change, correct the evidence and documents, render and inspect every revised page, and create new review metadata. If the change is demonstrably unrelated, verify that the reviewed Word/PDF/evidence-map hashes are unchanged and that all other inputs are accounted for. Previous visual inspection can then remain valid for those exact unchanged files; it does not establish the new source review.
4. Record the review in the private per-job manifest or adjacent review note: changed source, old/new hashes, relevant scope, impact decision, evidence checked, reviewer and date. Only after that review may the affected input attestations be rebound to the current hashes. Reconsider any source-dependent finding resolutions; do not automatically carry them forward.
5. Rerun the full checker, retaining its current report and all existing readiness gates. A source-change review is not a waiver for blocking findings and does not permit incomplete visual or evidence review. Do not bulk-rebind unrelated packs or alter the report/artifacts preserved for completed submissions.

## Limitations

Pattern matching is advisory, not semantic fact verification or an employer ATS score. Exact comparisons catch configured fields but cannot prove every duty or detect every false claim. Extracted text and Word structure checks complement, not replace, visual review. Do not use a clean result to lower the existing tailoring standard.

Run regression tests with `CHECKER_NODE="$NODE" "$PYTHON" -m unittest discover -s scripts -p 'test_document_checks.py'`. Fixtures are synthetic and must remain free of candidate information.
