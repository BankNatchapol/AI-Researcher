# Issue #8 QA evidence — v3

- Issue: #8 — Implement PDF acquisition with open-access detection
- Pull request: #22
- Branch: `issue-8-implement-pdf-acquisition-with-open-access-detection`
- Builder rebuild commit tested: `82e21c1e338ea8264e3ef01978b7230d01039b94`
- Tested at: `2026-07-26T19:20:44+07:00`
- Environment: macOS arm64, CPython 3.11.15, pytest 9.1.1
- Result: PASS

## Rebuild target

Reviewer rebuild 2 identified two state-isolation gaps:

1. A malformed adapter PDF URL raised `ValueError` out of `acquire_pdf` instead of
   returning a paper-linked failure.
2. Reacquiring a paper whose recorded PDF file had disappeared could transition to
   `abstract_only` while retaining the missing file's stale `pdf_path`.

Builder commit `82e21c1` adds a narrow `InvalidPdfUrlError`, records that failure through
the existing paper-linked failure path, and clears a recorded `pdf_path` after confirming
that its file no longer exists. Offline regressions cover the malformed URL plus both
no-URL and invalid-response reacquisition paths.

## Acceptance-criterion test plan

| AC | Observable test | Result |
|---|---|---|
| AC1 — download an open-access PDF to configured storage and populate `pdf_path` | `tests/test_acquire.py::test_open_access_pdf_is_downloaded_and_recorded` and `tests/test_acquire.py::test_default_acquisition_uses_configured_storage_directory` | PASS |
| AC2 — preserve a no-PDF paper as `abstract_only` with OA status | `tests/test_acquire.py::test_paper_without_pdf_is_kept_as_abstract_only` and both cases of `tests/test_acquire.py::test_non_pdf_response_is_treated_as_no_pdf_available` | PASS |
| AC3 — skip an existing download without touching the file | `tests/test_acquire.py::test_existing_download_is_skipped_without_touching_file` observes unchanged bytes and nanosecond mtime, preserved metadata, and no source/download call | PASS |
| AC4 — record download failure without raising | `tests/test_acquire.py::test_download_failure_is_recorded_against_paper_without_raising`, `test_malformed_pdf_url_is_recorded_without_raising`, and `test_storage_failure_is_recorded_without_raising` observe paper-linked failure results and failed statuses | PASS |
| AC5 — focused offline fixture suite exits 0 | `uv run pytest tests/test_acquire.py` | PASS — 12 passed |
| Reviewer rebuild 1 — successful retry clears stale failure state | `tests/test_acquire.py::test_successful_retry_resets_failed_paper_to_pending` | PASS |
| Reviewer rebuild 2a — malformed URL is isolated and recorded | `tests/test_acquire.py::test_malformed_pdf_url_is_recorded_without_raising` | PASS |
| Reviewer rebuild 2b — missing recorded file does not leave stale `pdf_path` | Both cases of `tests/test_acquire.py::test_abstract_only_reacquisition_clears_missing_pdf_path` | PASS |

## Required command

```text
$ uv run pytest tests/test_acquire.py
collected 12 items
tests/test_acquire.py ............ [100%]
12 passed in 0.03s
exit code: 0
```

The suite uses a committed PDF fixture and injected source/download fakes. The malformed
URL regression exercises the real standard-library `Request` constructor, which rejects
the URL before `urlopen` can be reached. All other download attempts use local injected
requesters, so the suite performs no live network access.

## Reviewer regression isolation

```text
$ uv run pytest tests/test_acquire.py::test_malformed_pdf_url_is_recorded_without_raising tests/test_acquire.py::test_abstract_only_reacquisition_clears_missing_pdf_path
collected 3 items
tests/test_acquire.py ... [100%]
3 passed in 0.01s
exit code: 0
```

## Repository verification

```text
$ uv run pytest && uv run ruff check .
collected 78 items
78 passed in 6.38s
All checks passed!
exit code: 0

$ uv run ruff format --check .
47 files already formatted
exit code: 0
```

## Review notes

- Malformed URLs now return `AcquisitionResult(status="failed", paper_id=..., error=...)`
  and set `oa_status = "download_failed"` / `parse_status = "failed"` without escaping.
- When a recorded PDF path points to a missing file, acquisition clears it before resolving
  the current source state. Both terminal `abstract_only` paths leave `pdf_path` null.
- A prior failed acquisition still transitions coherently to
  `downloaded` / `open_access` / `pending` on a successful retry.
- Existing valid downloads remain untouched and skip adapter URL resolution and download.
- Candidate responses still require both the PDF content type and `%PDF-` magic bytes.
- `.env.example` remains append-only and documents `STORAGE_DIR`.
- All three `[builder]` review threads are resolved; no `[QA]` thread exists.

## Visual evidence

Intentionally omitted. Issue #8 changes a Python acquisition/configuration path and has no
UI or visual acceptance criterion; the reproducible test output above is the relevant
evidence.
