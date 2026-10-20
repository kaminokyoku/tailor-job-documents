---
name: tailor-job-documents
description: Create evidence-led, job-specific CVs and explicitly requested cover letters using separate private candidate sources, with editable Word or submission-ready PDF output and visual quality checks.
---

# Tailor Job Documents

Use independently for one vacancy or as the document stage of `seek-job-search`. This skill contains no candidate details, examples from a real candidate or absolute personal paths. Do not submit applications from this skill.

## Inputs and Private Sources

Resolve `jobs_root` from the caller, user's folder or current workspace. Read `private/candidate-profile.json`, `private/evidence-bank.md`, `private/source-index.json`, `private/screening-answers.json` and document preferences in `private/workflow.json`. Never treat private screening answers as material to include wholesale in a CV. Profile data should separate identity, employment, education, certifications and languages; each claim needs provenance. Sources need an ID, path and purpose; screening entries need an answer, scope, source and confirmation date. Missing values remain unknown. The companion search skill provides a fuller private-data contract for new-user setup.

Required job input: employer, title, canonical URL/ID, complete ad, essential/desirable requirements, route, output directory and `output_mode` (`seek_pdf` or `manual_docx`). Caller may supply score/gaps, but recheck the evidence. If only a snippet is available, obtain the full advertisement before final tailoring. If sources are missing, report exactly what is missing and do not invent a complete candidate history.

Use the current profile source as baseline and configured benchmark documents for writing/layout quality. Read original experience/project sources relevant to the role. A benchmark may contain stronger unsupported claims; it is not permission to reproduce them. Current explicit user facts override stale documents. Keep formal titles, internships, employment dates and qualification status truthful; preserve promotions where relevant. Never transplant a previous candidate's content.

## Build the Case Before Drafting

Read [Writing and Layout Review](references/writing-and-layout.md) before drafting or substantially revising a pack. Apply its evidence, editorial and visual passes alongside the technical document checks; a clean checker result alone does not establish persuasive writing or good design.

Save an internal requirement-to-evidence map in the run folder: each important responsibility/criterion, supporting source and page/section, exact factual basis, planned emphasis, and gap. Separate direct experience, transferable duties, academic/project work and aspirations. No claim should be created by paraphrasing the ad as an accomplishment.

Choose the most persuasive truthful career narrative for this employer. Prioritise relevant work within roles; retain coherent chronology and use a clearly named projects section for project-only skills. Do not relabel informal duties as a formal job title, turn a qualification into practising admission, count an entire tenure as specialist experience, or invent interviewing/statutory powers, metrics, software ownership or certifications. Bind each grade or award to its own qualification. Absence from a source does not establish a negative claim about the candidate; keep unknowns out of final copy rather than asserting they have no experience.

## CV Standard

- Normally two polished pages, not a shallow one-page keyword list. Use substantial evidence-led bullets showing action, context/method and a supported output or contribution; outcomes do not need invented numbers.
- Make summary and ordering specific to the role. Retain relevant experience, technical skills, core competencies, education and certifications without repeating the same assertion in several sections.
- Change the evidence selection and emphasis, not merely the employer name and keywords. Use the evidence map to explain internally which verified work answers this role's principal needs; omit weak filler rather than manufacture a connection.
- Use natural professional language and terminology the candidate can defend in an interview. Match the configured benchmark's depth and presentation, not its unsupported wording.
- Preserve official job titles. Do not add labels such as '(Data Focus)', 'Tailored CV for ...', fit scores, match labels, internal rationale, drafting notes or prompts in final documents.
- Use contact details from the current private profile. Do not include a full street address, sensitive declarations, work-rights documents, identity numbers or references' private details unless specifically required and authorised.
- Avoid decorative layouts that compromise scanning or text extraction: restrained typography, clear hierarchy, consistent dates, readable margins and bullets. No text boxes for essential experience, awkward orphan headings, cramped type or padding to fill pages.
- Use meaningful action, context and supported contribution, not compulsory numbers or stronger ownership verbs. Retain "assisted" or "contributed" when that is the true scope. Record missing metrics as questions in private working notes; never estimate achievements from plausibility.

## Cover Letter / Introduction

Create only when the advertisement or actual application explicitly requests one, or the user separately requests it. An optional generic upload slot is insufficient. Record the requirement that triggered creation.

Normally one page: clear reason for this employer/role, two or three specific source-backed connections, a candid transferable-skills bridge where necessary, and a concise close. Make the positive case confidently without internal phrases such as 'without claiming' or a catalogue of missing skills; answer an explicitly requested gap honestly. Do not repeat the CV, claim unprovided motivation, invent an addressee, or use generic praise. Answer any requested points/word limit. Use standing availability/salary only if asked. Label file contents professionally, not as a tailoring exercise.

## Produce, Render, Inspect

Use available document/PDF skills and bundled dependencies for generation and rendering; follow their current instructions. Keep editable working content outside the skill directory.

- `seek_pdf`: deliver a verified PDF CV and a PDF supporting document only when requested. Retain editable source for later corrections.
- `manual_docx`: deliver editable DOCX CV and, only if requested, DOCX supporting document. Render DOCX to PDF/page images for QA; the deliverable remains editable Word.
- If the route changes to manual/blocked, ensure DOCX exists and point the manual list to it.
- Name files with candidate, employer and role from runtime data. Save all outputs beneath the requested run directory; never overwrite old source CVs.
- Render and visually inspect **every page of every final document**. Check page count, clipping, overlap, whitespace, line breaks, headings, typography, contact details and pagination. Inspect new renders after edits. Verify PDF text is extractable and no internal labels, placeholders or unsupported claims remain. Text extraction alone is not visual QA.
- Save a brief internal editorial review with the evidence map: strongest role-specific proof, unsupported requirements left out, removed repetition, and concrete layout/read-order observations. Do not label this an employer ATS score or promise screening success.
- If rendering/inspection cannot be completed, mark the documents draft/QA-blocked and do not call them submission-ready. Do not silently substitute an unverified PDF or screenshot-only CV.

## Additional Document Checks

Before marking any new or pending pack ready, follow [Offline Document Checks](references/document-checks.md) and run `scripts/check_documents.py`. It uses a pinned local Career Ops fact checker, private positive evidence and exact profile comparisons, plus checks on the actual DOCX/PDF files. Keep every candidate fact, alias and exception in the private files described there. Never feed negative cautions, job advertisements or generated CVs as positive evidence.

The checker must finish with `checks_passed` and `eligible_for_ready: true`. Missing inputs, changed files, incomplete visual/evidence review and unresolved warnings block readiness. The helper does not establish truth or grant submission approval: keep the existing full evidence review and page inspection. Save the report alongside the manifest, bind reviews to the current file/source hashes, and rerun after any relevant change. If private inputs change while a pack is pending, follow the reference's Changed Private Inputs procedure; never make a stale report pass by blindly replacing hashes. Do not rewrite completed submission history when introducing these checks.

## Return Contract

Save a per-job manifest and return it to `seek-job-search` (or the user):

```json
{
  "job_url": "https://nz.seek.com/job/12345678",
  "status": "ready",
  "output_mode": "manual_docx",
  "cv_docx": "relative filename.docx",
  "cv_pdf": null,
  "cover_requested": false,
  "cover_requirement": null,
  "cover_docx": null,
  "cover_pdf": null,
  "evidence_map": "relative evidence-map filename.md",
  "source_refs": [],
  "document_checks": {"report": "job.document-checks.json", "checker_version": "1.0.0"},
  "qa": {"rendered": true, "all_pages_visually_checked": true, "issues": []},
  "unresolved_claims": []
}
```

Use `draft` or `blocked` when required checks fail. Only `ready` files with a current passing document-check report may be uploaded by the calling skill. Ready means document readiness only, not employer disclosure or submission authorisation. If an already-uploaded document changes, return its new version and hashes so the caller replaces and verifies the attachment before submitting; do not assume SEEK has the revision. Scores and evidence maps stay in internal records, never in the candidate-facing CV. Update the private evidence store only from explicit user facts or newly verified source facts, with provenance; a generated CV is not independent evidence for future claims.
