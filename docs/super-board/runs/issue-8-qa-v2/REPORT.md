# Issue #8 QA evidence — v2

- Issue: #8 — Implement PDF acquisition with open-access detection
- Pull request: #22
- Branch: `issue-8-implement-pdf-acquisition-with-open-access-detection`
- Builder rebuild commit tested: `3e8813b6516b6e307a3b3b0cc09865412abbe300`
- Tested at: `2026-07-26T18:49:29+07:00`
- Environment: macOS arm64, CPython 3.11.15, pytest 9.1.1
- Result: PASS

## Rebuild target

Reviewer rebuild 1 found that a successful acquisition retry could return `downloaded`
and set `pdf_path`/`oa_status` while leaving the previous
`parse_status = "failed"` unchanged. Commit `3e8813b` resets a successful acquisition to
`parse_status = "pending"` and adds
`tests/test_acquire.py::test_successful_retry_resets_failed_paper_to_pending`.

The regression constructs a paper in the prior failure state
(`oa_status = "download_failed"`, `parse_status = "failed"`), performs a fixture-backed
successful retry, and observes all of:

- result status is `downloaded`
- `pdf_path` points to the newly written numeric-ID PDF
- `oa_status` is `open_access`
- `parse_status` is `pending`

## Acceptance-criterion test plan

| AC | Observable test | Result |
|---|---|---|
| AC1 — download an open-access PDF to configured storage and populate `pdf_path` | `tests/test_acquire.py::test_open_access_pdf_is_downloaded_and_recorded` and `tests/test_acquire.py::test_default_acquisition_uses_configured_storage_directory` | PASS |
| AC2 — preserve a no-PDF paper as `abstract_only` with OA status | `tests/test_acquire.py::test_paper_without_pdf_is_kept_as_abstract_only` and both cases of `tests/test_acquire.py::test_non_pdf_response_is_treated_as_no_pdf_available` | PASS |
| AC3 — skip an existing download without touching the file | `tests/test_acquire.py::test_existing_download_is_skipped_without_touching_file` observes unchanged bytes and nanosecond mtime, preserved metadata, and no source/download call | PASS |
| AC4 — record download failure without raising | `tests/test_acquire.py::test_download_failure_is_recorded_against_paper_without_raising` observes the paper-linked error result and failed statuses; `test_storage_failure_is_recorded_without_raising` covers local write failure | PASS |
| AC5 — focused offline fixture suite exits 0 | `uv run pytest tests/test_acquire.py` | PASS — 9 passed |
| Reviewer rebuild — successful retry clears stale acquisition failure state | `tests/test_acquire.py::test_successful_retry_resets_failed_paper_to_pending` | PASS |

## Required command

```text
$ uv run pytest tests/test_acquire.py
collected 9 items
tests/test_acquire.py ......... [100%]
9 passed in 0.03s
exit code: 0
```

The suite uses a committed PDF fixture plus injected source and download fakes. Every
acquisition attempt supplies a `PdfDownloadClient` whose requester is local test code, so
the default `urlopen` requester is never reached and no live network is used.

## Repository verification

```text
$ uv run pytest
collected 75 items
75 passed in 7.73s
exit code: 0

$ uv run ruff check .
All checks passed!
exit code: 0

$ uv run ruff format --check .
47 files already formatted
exit code: 0
```

## Review notes

- The reviewer’s failure → successful retry transition is now coherent at the task 09
  boundary: `downloaded` / `open_access` / `pending`, with a populated PDF path.
- Downloaded files use the numeric paper ID (`<paper.id>.pdf`), independent of unsafe
  title or external-ID characters.
- Candidate responses must have both the PDF content type and `%PDF-` magic bytes.
- Missing and invalid PDF responses take the abstract-only path rather than dropping the
  paper.
- Network and storage `OSError` failures return a paper-linked `AcquisitionResult` and set
  failure statuses instead of escaping the acquisition call.
- Download requests reuse the shared `MinimumIntervalLimiter` implementation and the
  configured per-source interval.
- `.env.example` remains append-only and documents `STORAGE_DIR`.
- The only PR review thread is `[builder]`-owned and resolved; no unresolved `[QA]` thread
  exists.

## Visual evidence

Not applicable. Issue #8 changes a Python library acquisition path and environment
configuration only; it has no UI or visual acceptance criterion.
