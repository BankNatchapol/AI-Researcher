# Issue #28 QA evidence — v1

- PR: #36
- Builder commit tested: `38920b864ca0663fa1a1a12f2b0451d5d3ea48ac`
- Task: `docs/superpowers/projects/ai-researcher-app/phase-2/03-shortlist-protocol.md`
- Result: PASS
- Visual evidence: intentionally omitted because all acceptance criteria concern Python
  protocols, configuration, PostgreSQL queries, migrations, and automated test behavior.

## Acceptance-criterion test plan

| AC | Observable test or check | Result |
|---|---|---|
| 1. Protocol with two registered implementations | `test_two_shortlist_implementations_are_registered_and_satisfy_protocol` checks the exact registry and runtime protocol conformance. | PASS |
| 2. PageIndex is default and respects `limit` | `test_config_switches_both_backends_for_the_same_question` exercises the unset/default backend; `test_pageindex_shortlist_caps_model_selection_at_limit` observes a three-ID model response being capped to two. | PASS |
| 3. `SHORTLIST_BACKEND=postgres_fts` switches implementations for the same question | `test_config_switches_both_backends_for_the_same_question` runs the public `shortlist()` entry point before and after the environment-only switch and validates returned IDs against the seeded corpus. | PASS |
| 4. PostgreSQL FTS searches title, abstract, and section body without embeddings | The three cases of `test_postgres_fts_searches_title_abstract_and_section_body` each find a distinct seeded paper through one required field; static invariant scans found no embedding, vector-similarity, pgvector, or reranker implementation. | PASS |
| 5. Exact task command exits 0 with seeded corpus and mocked LLM | `uv run pytest tests/test_shortlist.py` collected 7 tests and reported `7 passed in 2.13s`, with no skips. | PASS |

## Commands and fresh results

```text
$ uv run pytest tests/test_shortlist.py
collected 7 items
tests/test_shortlist.py ....... [100%]
7 passed in 2.13s

$ uv run pytest
collected 112 items
112 passed in 9.26s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
67 files already formatted
```

## Invariant checks

- Retrieval remains vectorless: no embedding, vector-similarity, pgvector, or reranker
  implementation terms occur in the issue-scoped retrieval, corpus, migration, or test files.
- The only model call in the shortlist implementation is
  `ai_researcher.llm.gateway.complete(..., job="shortlist")`.
- The PageIndex path makes one mocked, batched model call over all three seeded candidates.
- The PostgreSQL tests used an isolated migrated database and exercised real full-text search;
  the acceptance run contained no skipped tests.
- `git diff --check origin/main...HEAD` produced no whitespace errors before evidence was added.
