---
title: Implement the shortlist protocol with PageIndex File System and a Postgres fallback
order: 3
depends_on_task: 02-tree-builder
project: ai-researcher-app
phase: 2
depends_on_phase: 1
design: docs/superpowers/projects/ai-researcher-app/phase-2/PHASE.md
plan_task: Requirements 8
skills: test-driven-development, verification-before-completion
---

## Goal

A question narrows a 1,000-paper scope to at most 20 candidate papers through a swappable
shortlist interface, with a corpus-level tree index as the default and a Postgres full-text
implementation available by configuration.

## Acceptance Criteria

- [ ] `shortlist(scope, question, limit) -> list[paper_id]` is defined as a protocol with two registered implementations
- [ ] The PageIndex File System implementation is the default and returns at most `limit` paper IDs
- [ ] Setting `SHORTLIST_BACKEND=postgres_fts` switches implementations with no code change, verified by a test asserting both satisfy the protocol and return valid paper IDs for the same question
- [ ] The Postgres implementation queries `paper.title`, `paper.abstract`, and `section.body_text` using full-text search, with no embeddings involved
- [ ] `uv run pytest tests/test_shortlist.py` exits 0, exercising both backends against a seeded fixture corpus with the LLM mocked

## Implementation notes

**Files:**
- Create: `src/ai_researcher/trees/corpus.py` — PageIndex File System over the scope's paper trees; reasons over paper-level titles and root node summaries via `llm.gateway.complete(job="shortlist")`
- Create: `src/ai_researcher/retrieval/__init__.py`
- Create: `src/ai_researcher/retrieval/shortlist.py` — the `Shortlist` protocol plus backend selection from config
- Create: `src/ai_researcher/retrieval/fts.py` — the Postgres full-text implementation
- Create: `src/ai_researcher/db/migrations/0003_fts_index.sql` — a GIN index supporting the fallback
- Modify: `src/ai_researcher/config.py` — add `SHORTLIST_BACKEND` defaulting to `pageindex`
- Test: `tests/test_shortlist.py`

**Interfaces:**
- Consumes: `tree_node` rows from task 02; `paper`/`section` from Phase 1
- Produces: `shortlist()` — consumed by task 04 traversal

**Why both exist:** PROJECT.md risk 3 records PageIndex File System as the newest, least
proven layer. Building the interface with two implementations now means adopting the fallback
is a config change rather than a redesign, if the gold set in task 08 shows it underperforming.

## Out of scope

No within-paper traversal — task 04 owns that. No answer synthesis. No vector or embedding
backend; both implementations are vectorless by design. No reranker model.
