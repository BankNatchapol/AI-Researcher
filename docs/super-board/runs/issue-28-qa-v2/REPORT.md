# Issue #28 QA evidence — v2

- PR: #36
- Builder rebuild commit tested: `9977686877748ab93f0de913e471c10267af383b`
- Prior QA evidence commit: `a919f70827c8655d99311f589d52f3e37263ae02`
- Task: `docs/superpowers/projects/ai-researcher-app/phase-2/03-shortlist-protocol.md`
- Result: PASS
- Visual evidence: intentionally omitted because all acceptance criteria concern Python
  protocols, configuration, PostgreSQL queries, migrations, and automated test behavior.

## Rebuild regression

Reviewer reported that importing `PageIndexShortlist` directly from
`ai_researcher.trees.corpus` in a fresh interpreter failed because
`ai_researcher.retrieval.__init__` eagerly closed a circular import.

The original reproducer was run against both sides of the rebuild:

```text
$ git worktree add --detach <temporary-worktree> a919f70
$ uv run python -c 'from ai_researcher.trees.corpus import PageIndexShortlist; print(PageIndexShortlist.__name__)'
ImportError: cannot import name 'PageIndexShortlist' from partially initialized module
'ai_researcher.trees.corpus' (most likely due to a circular import)
exit 1

$ uv run python -c 'from ai_researcher.trees.corpus import PageIndexShortlist; print(PageIndexShortlist.__name__)'
PageIndexShortlist
exit 0
```

`test_pageindex_module_imports_in_fresh_interpreter` preserves this reproducer as an
automated regression test. The pre-fix failure and rebuilt-head pass demonstrate that the
test distinguishes the reported defect.

## Acceptance-criterion test plan

| AC | Observable test or check | Result |
|---|---|---|
| 1. Protocol with two registered implementations | `test_two_shortlist_implementations_are_registered_and_satisfy_protocol` checks the exact registry and runtime protocol conformance after lazy registration. | PASS |
| 2. PageIndex is default and respects `limit` | `test_config_switches_both_backends_for_the_same_question` exercises the unset/default backend; `test_pageindex_shortlist_caps_model_selection_at_limit` observes a three-ID model response being capped to two. | PASS |
| 3. `SHORTLIST_BACKEND=postgres_fts` switches implementations for the same question | `test_config_switches_both_backends_for_the_same_question` runs the public `shortlist()` entry point before and after the environment-only switch and validates returned IDs against the seeded corpus. | PASS |
| 4. PostgreSQL FTS searches title, abstract, and section body without embeddings | The three cases of `test_postgres_fts_searches_title_abstract_and_section_body` each find a distinct seeded paper through one required field; `test_fts_migration_adds_gin_indexes` checks the supporting indexes; a static invariant scan found no embedding, vector-similarity, pgvector, or reranker implementation. | PASS |
| 5. Exact task command exits 0 with seeded corpus and mocked LLM | `uv run pytest tests/test_shortlist.py` collected 8 tests and reported `8 passed in 0.67s`, with no skips. | PASS |

## Commands and fresh results

```text
$ uv run pytest tests/test_shortlist.py
collected 8 items
tests/test_shortlist.py ........ [100%]
8 passed in 0.67s

$ uv run pytest
collected 113 items
113 passed in 9.16s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
67 files already formatted

$ git diff --check origin/main...HEAD
exit 0
```

## Invariant checks

- Retrieval remains vectorless: no embedding, vector-similarity, pgvector, or reranker
  implementation terms occur in the issue-scoped retrieval, corpus, or migration files.
- The only model call in the shortlist implementation is
  `ai_researcher.llm.gateway.complete(..., job="shortlist")`.
- The PageIndex path makes one mocked, batched model call over all three seeded candidates.
- The PostgreSQL tests used an isolated migrated database and exercised real full-text search;
  the acceptance run contained no skipped tests.
- The resolved `[builder]` review thread is covered by a fresh-process subprocess test.
- There are no unresolved `[QA]` review threads on PR #36.
