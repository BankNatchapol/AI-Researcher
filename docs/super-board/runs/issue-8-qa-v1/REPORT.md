# Issue #8 QA evidence — v1

- Issue: #8 — Implement PDF acquisition with open-access detection
- Pull request: #22
- Branch: `issue-8-implement-pdf-acquisition-with-open-access-detection`
- Builder commit tested: `d1b8d1c8b168e7e33409104d38b6b80e7c39b46b`
- Tested at: `2026-07-26T18:08:41+07:00`
- Environment: macOS, CPython 3.11.15, pytest 9.1.1
- Result: PASS

## Acceptance-criterion test plan

| AC | Observable test | Result |
|---|---|---|
| AC1 — download an open-access PDF to configured storage and populate `pdf_path` | `tests/test_acquire.py::test_open_access_pdf_is_downloaded_and_recorded` and `tests/test_acquire.py::test_default_acquisition_uses_configured_storage_directory` | PASS |
| AC2 — preserve a no-PDF paper as `abstract_only` with OA status | `tests/test_acquire.py::test_paper_without_pdf_is_kept_as_abstract_only` and the two cases in `tests/test_acquire.py::test_non_pdf_response_is_treated_as_no_pdf_available` | PASS |
| AC3 — skip an existing download without touching the file | `tests/test_acquire.py::test_existing_download_is_skipped_without_touching_file` checks bytes, nanosecond mtime, metadata, and that no source/download call occurs | PASS |
| AC4 — record download failure without raising | `tests/test_acquire.py::test_download_failure_is_recorded_against_paper_without_raising` checks the paper-linked error result and failed statuses | PASS |
| AC5 — focused offline fixture suite exits 0 | `uv run pytest tests/test_acquire.py` | PASS — 8 passed |

## Required command

```text
$ uv run pytest tests/test_acquire.py
collected 8 items
tests/test_acquire.py ........ [100%]
8 passed in 0.03s
exit code: 0
```

The suite uses a committed PDF fixture plus injected source and download fakes. Every
acquisition call in the suite supplies a `PdfDownloadClient` whose requester is local test
code, so the default `urlopen` requester is never reached.

## Repository verification

```text
$ uv run pytest
collected 74 items
74 passed in 6.54s
exit code: 0

$ uv run ruff check .
All checks passed!
exit code: 0

$ uv run ruff format --check .
47 files already formatted
exit code: 0
```

## Review notes

- Downloaded files use the numeric paper ID (`<paper.id>.pdf`), independent of unsafe
  title or external-ID characters.
- Candidate responses must have both the PDF content type and `%PDF-` magic bytes.
- Missing and invalid PDF responses take the abstract-only path rather than dropping the
  paper.
- Network and storage `OSError` failures return a paper-linked `AcquisitionResult` and set
  failure statuses instead of escaping the acquisition call.
- Download requests reuse the shared `MinimumIntervalLimiter` implementation and the
  configured per-source interval.
- `.env.example` was append-only and documents `STORAGE_DIR`.

## Visual evidence

Not applicable. Issue #8 changes a Python library acquisition path and environment
configuration only; it has no UI or visual acceptance criterion.
