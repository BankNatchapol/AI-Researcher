# Issue #10 QA Evidence v1

- Branch: `issue-10-wire-the-ingest-pipeline-with-resumability-and-the-corpus-ceiling`
- Builder commit: `9483d37`
- When: 2026-07-26T14:59Z
- Result: **PASS**

## Test plan (one observable check per AC)

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | `airesearch ingest <scope>` completes full pipeline and writes one `ingest_job` with `papers_found`, `papers_parsed`, terminal state | PASS | `test_clean_ingest_writes_job_papers_and_sections` — job state=`completed`, found=1, parsed=1; paper + section + paper_scope rows written |
| AC2 | Re-running ingest for same scope reports zero newly parsed papers | PASS | `test_resumed_ingest_reports_zero_newly_parsed_papers` — `papers_newly_parsed==0`, acquire/parse each called once across both runs |
| AC3 | Scope >1,000 papers exits non-zero naming resolved count and 1,000 ceiling | PASS | `test_corpus_ceiling_refuses_before_any_download` + `test_cli_ingest_ceiling_exits_nonzero_with_counts` — message contains both counts; no PDF downloads |
| AC4 | Single paper parse failure recorded; run continues to completion | PASS | `test_parse_failure_is_recorded_and_run_continues` — failed paper `parse_status='failed'`, sibling parsed, job `completed` |
| AC5 | `uv run pytest tests/test_ingest_pipeline.py` exits 0 covering clean/resume/ceiling/mid-run failure | PASS | 7 passed (see `pytest-ingest.txt`) |

## Commands run

```bash
uv run pytest tests/test_ingest_pipeline.py -v   # 7 passed
uv run pytest                                    # 91 passed
uv run ruff check .                              # All checks passed
uv run ruff format --check .                     # 53 files already formatted
```

## Visual evidence

Skipped intentionally — this issue is a library/ingest task with no UI surface.
Screenshots do not apply. Logs in this directory are the primary evidence.

## Local path

- `docs/super-board/runs/issue-10-qa-v1/REPORT.md`
- `docs/super-board/runs/issue-10-qa-v1/pytest-ingest.txt`
- `docs/super-board/runs/issue-10-qa-v1/pytest-full.txt`
- `docs/super-board/runs/issue-10-qa-v1/ruff-check.txt`
- `docs/super-board/runs/issue-10-qa-v1/ruff-format.txt`

## Invariant spot-check

- No embeddings / vector similarity / `pgvector` in `ingest/`.
- No LLM SDK imports (`openai`/`anthropic`/`litellm`) in ingest path.
- No `discourse` imports from ingest (evidence/discourse channel separation).
- Failures recorded on papers; ceiling refusal happens before any PDF download.
- Corpus ceiling constant is 1,000 as required.
