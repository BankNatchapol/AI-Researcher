# Issue #8 QA evidence — v5

- Issue: #8 — Implement PDF acquisition with open-access detection
- Pull request: #22
- Branch: `issue-8-implement-pdf-acquisition-with-open-access-detection`
- Builder Gate 1 resolve commit tested: `ad850128ba88d7d2ec0174d15b4938457a956aba`
- Human-authorized IncompleteRead fix still present: `674955a916f676f064ce9a103c5a2db3c073e769`
- Tested at: `2026-07-26T21:00:00+07:00`
- Environment: macOS arm64, CPython 3.11.15, pytest 9.1.1
- Result: PASS

## Rebuild target

After QA v4, Review Gate 1 bounced the card because the Reviewer-created
`[builder]` IncompleteRead thread was still unresolved. Builder commit
`ad85012` verified the existing `HTTPException` catch, typed `_record_failure`
to accept `HTTPException`, and resolved that thread. This QA pass re-verifies
AC1–AC5 plus all prior rebuild regressions on the Gate 1 tip.

## Acceptance-criterion test plan

| AC | Observable test | Result |
|---|---|---|
| AC1 — download an open-access PDF to configured storage and populate `pdf_path` | `tests/test_acquire.py::test_open_access_pdf_is_downloaded_and_recorded`; `test_default_acquisition_uses_configured_storage_directory` | PASS |
| AC2 — preserve a no-PDF paper as `abstract_only` with OA status | `test_paper_without_pdf_is_kept_as_abstract_only`; both `test_non_pdf_response_is_treated_as_no_pdf_available` cases | PASS |
| AC3 — skip an existing download without touching it | `test_existing_download_is_skipped_without_touching_file` | PASS |
| AC4 — record a download failure against the paper without raising | `test_download_failure_is_recorded_against_paper_without_raising`, `test_truncated_http_response_is_recorded_against_paper_without_raising`, `test_malformed_pdf_url_is_recorded_without_raising`, `test_storage_failure_is_recorded_without_raising` | PASS |
| AC5 — focused offline fixture suite exits 0 | `uv run pytest tests/test_acquire.py` | PASS — 13 passed |
| Reviewer rebuild 1 — successful retry clears stale failure state | `test_successful_retry_resets_failed_paper_to_pending` | PASS |
| Reviewer rebuild 2 — malformed URLs and missing recorded files remain coherent | `test_malformed_pdf_url_is_recorded_without_raising`; both `test_abstract_only_reacquisition_clears_missing_pdf_path` cases | PASS |
| Reviewer rebuild 3 / human-authorized — truncated HTTP bodies are isolated | `test_truncated_http_response_is_recorded_against_paper_without_raising` | PASS |
| Gate 1 — unresolved `[builder]` IncompleteRead thread | GraphQL reviewThreads: all four threads `isResolved: true`; no unresolved `[QA]` threads | PASS |

## Required command

```text
$ uv run pytest tests/test_acquire.py -v
collected 13 items
tests/test_acquire.py::test_open_access_pdf_is_downloaded_and_recorded PASSED
tests/test_acquire.py::test_paper_without_pdf_is_kept_as_abstract_only PASSED
tests/test_acquire.py::test_non_pdf_response_is_treated_as_no_pdf_available[...] PASSED
tests/test_acquire.py::test_non_pdf_response_is_treated_as_no_pdf_available[...] PASSED
tests/test_acquire.py::test_existing_download_is_skipped_without_touching_file PASSED
tests/test_acquire.py::test_download_failure_is_recorded_against_paper_without_raising PASSED
tests/test_acquire.py::test_truncated_http_response_is_recorded_against_paper_without_raising PASSED
tests/test_acquire.py::test_malformed_pdf_url_is_recorded_without_raising PASSED
tests/test_acquire.py::test_abstract_only_reacquisition_clears_missing_pdf_path[...] PASSED
tests/test_acquire.py::test_abstract_only_reacquisition_clears_missing_pdf_path[...] PASSED
tests/test_acquire.py::test_successful_retry_resets_failed_paper_to_pending PASSED
tests/test_acquire.py::test_default_acquisition_uses_configured_storage_directory PASSED
tests/test_acquire.py::test_storage_failure_is_recorded_without_raising PASSED
13 passed in 0.03s
exit code: 0
```

The suite uses a committed PDF fixture and injected source/download fakes. It performs no
live network access.

## Repository verification

```text
$ uv run pytest && uv run ruff check .
collected 79 items
79 passed in 6.34s
All checks passed!
exit code: 0

$ uv run ruff format --check .
47 files already formatted
exit code: 0
```

## Review notes

- Gate 1 tip `ad85012` keeps the human-authorized `HTTPException` catch from `674955a`.
- `_record_failure` is typed to accept `InvalidPdfUrlError | OSError | HTTPException`,
  matching the download failure catch that records IncompleteRead as a paper-linked failure.
- Prior retry, malformed-URL, missing-file, no-PDF, storage-failure, and truncated-HTTP
  regressions remain green.
- All `[builder]` review threads are resolved. No unresolved `[QA]` threads exist.

## Visual evidence

Intentionally omitted. Issue #8 changes a Python acquisition/configuration path and has no
UI or visual acceptance criterion; the reproducible test output above is the relevant
evidence.
