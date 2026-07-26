---
title: Add the tree_node and retrieval_trace schema
order: 1
depends_on_task: null
project: ai-researcher-app
phase: 2
depends_on_phase: 1
design: docs/superpowers/projects/ai-researcher-app/phase-2/PHASE.md
plan_task: Requirements 1, 2
skills: test-driven-development, verification-before-completion
---

## Goal

The database holds per-paper tree nodes and per-question retrieval traces, so tree building
and traversal have somewhere to write.

## Acceptance Criteria

- [ ] `uv run airesearch db migrate` applies the new migration and exits 0; re-running reports "already up to date"
- [ ] `tree_node` exists with `id, paper_id, section_id, parent_id, node_path, title, summary, page_start, page_end, depth, tree_schema_version, summary_model, created_at`
- [ ] `retrieval_trace` exists with `id, question, scope_id, expanded_node_ids, selected_node_ids, nodes_expanded, stopped_reason, created_at`
- [ ] `tree_node.section_id` is a non-null foreign key to `section`, and `tree_node.paper_id` a non-null foreign key to `paper`
- [ ] `uv run pytest tests/test_tree_schema.py` exits 0, asserting a `tree_node` insert with a null `section_id` is rejected by the database

## Implementation notes

**Files:**
- Create: `src/ai_researcher/db/migrations/0002_trees.sql`
- Modify: `src/ai_researcher/db/models.py` — add both table definitions
- Test: `tests/test_tree_schema.py`

**Interfaces:**
- Consumes: the migration runner and `paper`/`section`/`scope` tables from Phase 1 task 03
- Produces: `tree_node` and `retrieval_trace` — written by tasks 02 and 04, read by Phase 3 for claim anchoring

**Schema notes:**
- `stopped_reason` is constrained to `sufficient_evidence`, `budget_exhausted`, `no_candidates`
- `expanded_node_ids` and `selected_node_ids` are stored as arrays preserving traversal order
- An index on `(paper_id, tree_schema_version, summary_model)` makes staleness checks cheap

## Out of scope

No tree building, no traversal, no LLM calls. No claim or discourse tables — those belong to
Phases 3 and 4. No vector columns of any kind; retrieval in this project is vectorless.
