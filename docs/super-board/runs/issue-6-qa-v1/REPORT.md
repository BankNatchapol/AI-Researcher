# Issue #6 QA evidence — v1

- PR: #20
- Branch: `issue-6-implement-cross-source-paper-deduplication-and-provenance`
- Builder commit tested: `b3a9ecd56d5e98edf75d624d5b8a4e1bf32d10c1`
- Scope: deterministic cross-source paper deduplication and provenance
- Result: PASS

## Acceptance-criterion test plan

| AC | Observable test | Result |
|---|---|---|
| 1 | `test_doi_match_merges_three_sources_with_three_provenance_rows` asserts one merged paper and distinct arXiv, OpenAlex, and Semantic Scholar provenance entries. | PASS |
| 2 | The DOI, arXiv ID, title-author-year fallback, and conflicting-DOI tests exercise the required identity order and its non-overmerge guard. | PASS |
| 3 | `test_normalize_title_ignores_case_punctuation_and_whitespace` compares two variants of “Attention Is All You Need.” | PASS |
| 4 | `test_merging_fills_empty_fields_without_overwriting_existing_values` verifies later metadata fills gaps while first-source values remain canonical. | PASS |
| 5 | The required issue-scoped command collects all seven deduplication tests, including the title-prefix near miss, and exits successfully. | PASS |

## Commands and results

```text
$ uv run pytest tests/test_dedup.py -vv
collected 7 items
7 passed in 0.02s

$ uv run pytest
collected 58 items
58 passed in 7.72s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
40 files already formatted
```

## Invariant and scope checks

- No embeddings, vector matching, fuzzy matching, or reranker code was added.
- The implementation consumes adapter dataclasses and performs no database or LLM calls.
- No dependency, schema, or shared configuration file changed.
- The PR diff is limited to `src/ai_researcher/ingest/` and `tests/test_dedup.py`.

## Visual evidence

Screenshots are intentionally omitted because issue #6 changes backend-only Python identity
resolution and has no UI or visual acceptance criteria. This report and the test output are
the applicable evidence.
