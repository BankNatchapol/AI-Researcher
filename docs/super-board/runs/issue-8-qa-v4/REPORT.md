# Issue #8 QA evidence — v4

- Issue: #8 — Implement PDF acquisition with open-access detection
- Pull request: #22
- Branch: `issue-8-implement-pdf-acquisition-with-open-access-detection`
- Human-authorized fix commit tested: `674955a916f676f064ce9a103c5a2db3c073e769`
- Tested at: `2026-07-26T20:01:15+07:00`
- Environment: macOS arm64, CPython 3.11.15, pytest 9.1.1
- Result: PASS

## Rebuild target

The Reviewer found that `http.client.IncompleteRead`, which may be raised while reading a
truncated HTTP response body, is not an `OSError`. It therefore escaped the acquisition
failure handler, violating AC4 and the repository rule that per-paper failures are recorded
rather than raised.

Human-authorized commit `674955a` catches the narrow `http.client.HTTPException` family
alongside the existing download exceptions and adds an offline `IncompleteRead` regression.

## Acceptance-criterion test plan

| AC | Observable test | Result |
|---|---|---|
| AC1 — download an open-access PDF to configured storage and populate `pdf_path` | `tests/test_acquire.py::test_open_access_pdf_is_downloaded_and_recorded` observes the numeric-ID file and populated paper state; `test_default_acquisition_uses_configured_storage_directory` observes the configured directory | PASS |
| AC2 — preserve a no-PDF paper as `abstract_only` with OA status | `tests/test_acquire.py::test_paper_without_pdf_is_kept_as_abstract_only` observes the retained paper state; both `test_non_pdf_response_is_treated_as_no_pdf_available` cases reject invalid PDF responses without dropping the paper | PASS |
| AC3 — skip an existing download without touching it | `tests/test_acquire.py::test_existing_download_is_skipped_without_touching_file` observes unchanged bytes and nanosecond mtime, preserved metadata, and no source/download call | PASS |
| AC4 — record a download failure against the paper without raising | `test_download_failure_is_recorded_against_paper_without_raising`, `test_truncated_http_response_is_recorded_against_paper_without_raising`, `test_malformed_pdf_url_is_recorded_without_raising`, and `test_storage_failure_is_recorded_without_raising` observe paper-linked failed results and coherent failure state | PASS |
| AC5 — focused offline fixture suite exits 0 | `uv run pytest tests/test_acquire.py` | PASS — 13 passed |
| Reviewer rebuild 1 — successful retry clears stale failure state | `tests/test_acquire.py::test_successful_retry_resets_failed_paper_to_pending` | PASS |
| Reviewer rebuild 2 — malformed URLs and missing recorded files remain coherent | `test_malformed_pdf_url_is_recorded_without_raising` and both `test_abstract_only_reacquisition_clears_missing_pdf_path` cases | PASS |
| Reviewer rebuild 3 — truncated HTTP bodies are isolated and recorded | `test_truncated_http_response_is_recorded_against_paper_without_raising` | PASS |

## Regression sensitivity

The new regression was run against the PR head, then the
`HTTPException` catch was temporarily removed from the QA worktree:

```text
$ uv run pytest tests/test_acquire.py::test_truncated_http_response_is_recorded_against_paper_without_raising -q
.                                                                        [100%]
1 passed in 0.03s

$ # temporarily restore the pre-fix exception tuple
$ uv run pytest tests/test_acquire.py::test_truncated_http_response_is_recorded_against_paper_without_raising -q
FAILED tests/test_acquire.py::test_truncated_http_response_is_recorded_against_paper_without_raising
E http.client.IncompleteRead: IncompleteRead(16 bytes read, 4096 more expected)
1 failed in 0.03s

$ # restore commit 674955a
$ uv run pytest tests/test_acquire.py::test_truncated_http_response_is_recorded_against_paper_without_raising -q
.                                                                        [100%]
1 passed in 0.01s
```

The failure is the exact pre-fix behavior: the exception escapes from the injected
download requester before a paper-linked result can be returned.

## Required command

```text
$ uv run pytest tests/test_acquire.py
collected 13 items
tests/test_acquire.py ............. [100%]
13 passed in 0.02s
exit code: 0
```

The suite uses a committed PDF fixture and injected source/download fakes. It performs no
live network access.

## Repository verification

```text
$ uv run pytest && uv run ruff check .
collected 79 items
79 passed in 7.86s
All checks passed!
exit code: 0

$ uv run ruff format --check .
47 files already formatted
exit code: 0
```

## Review notes

- `IncompleteRead` now returns `AcquisitionResult(status="failed", paper_id=..., error=...)`
  and sets `oa_status = "download_failed"` / `parse_status = "failed"` without escaping.
- The handler catches the standard-library HTTP protocol exception family without adding a
  blanket `Exception` catch.
- The earlier retry, malformed-URL, missing-file, no-PDF, and storage-failure regressions
  remain green.
- No unresolved `[QA]` review thread exists.
- The Reviewer-created `[builder]` thread for this defect remains unresolved; Tester
  ownership rules do not permit this lane to resolve builder-owned threads.

## Visual evidence

Intentionally omitted. Issue #8 changes a Python acquisition/configuration path and has no
UI or visual acceptance criterion; the reproducible test output above is the relevant
evidence.
