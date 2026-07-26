---
title: Implement PDF acquisition with open-access detection
order: 8
depends_on_task: 07-topic-scoping-dialogue
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 16
skills: test-driven-development, verification-before-completion
---

## Goal

Open-access PDFs are downloaded to local storage and recorded on the paper row; papers
without an accessible PDF are kept as abstract-only rather than dropped or silently failed.

## Acceptance Criteria

- [ ] A paper with an open-access PDF is downloaded to the configured storage directory and its `paper.pdf_path` is populated
- [ ] A paper with no accessible PDF is stored with `parse_status = 'abstract_only'` and its `oa_status` recorded, and is never dropped
- [ ] Re-running acquisition for an already-downloaded paper skips the download and leaves the existing file untouched
- [ ] A download failure records the error against the paper and does not raise out of the acquisition call
- [ ] `uv run pytest tests/test_acquire.py` exits 0, covering successful download, no-PDF-available, HTTP failure, and the skip-if-present path, all against fixtures with no live network

## Implementation notes

**Files:**
- Create: `src/ai_researcher/ingest/acquire.py` — `acquire_pdf(paper) -> AcquisitionResult`; resolves a URL via the source adapter's `pdf_url()`, downloads, verifies the response is a PDF by content type and magic bytes, writes to storage
- Modify: `src/ai_researcher/config.py` — add `STORAGE_DIR` for downloaded PDFs
- Modify: `.env.example` — document `STORAGE_DIR`
- Test: `tests/test_acquire.py`

**Interfaces:**
- Consumes: `pdf_url()` from task 05 adapters; `paper` table columns `pdf_path`, `oa_status`, `parse_status` from task 03
- Produces: downloaded PDFs at `paper.pdf_path` — consumed by task 09 GROBID parsing

**Behaviour notes:**
- Files are named by paper ID, not by title, so no filesystem-unsafe characters can appear
- Downloads honour the same per-source rate limiter introduced in task 05
- A response that is not a PDF is treated as no-PDF-available, not as a successful download

## Out of scope

No paywall circumvention of any kind — only openly accessible PDFs are fetched. No GROBID
parsing (task 09), no pipeline orchestration (task 10). No OCR and no handling of scanned
documents.
