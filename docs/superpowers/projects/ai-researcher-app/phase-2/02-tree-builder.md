---
title: Build per-paper node trees with LLM summaries and versioned caching
order: 2
depends_on_task: 01-tree-schema
project: ai-researcher-app
phase: 2
depends_on_phase: 1
design: docs/superpowers/projects/ai-researcher-app/phase-2/PHASE.md
plan_task: Requirements 3, 4, 5, 6, 7
skills: test-driven-development, verification-before-completion
---

## Goal

`airesearch index <scope>` converts each parsed paper's section hierarchy into a node tree
with concise LLM-generated summaries, cached and versioned so rebuilds are per-paper and rare.

## Acceptance Criteria

- [ ] `uv run airesearch index <scope>` builds trees for parsed papers lacking a current tree and reports built versus skipped counts; re-running with no new papers and no version change builds zero and exits 0
- [ ] Every `tree_node` links to exactly one `section` and inherits its `page_start`, `page_end`, and section path
- [ ] Every node `summary` is 60 words or fewer, and summaries are generated in **one batched call per paper**, asserted by a test that counts gateway calls and fails if the count scales with node count rather than paper count
- [ ] Trees deeper than 4 levels are flattened at level 4 with the original depth preserved in `node_path`, asserted by a test on a 6-level fixture
- [ ] `uv run pytest tests/test_tree_builder.py` exits 0 with the LLM mocked

## Implementation notes

**Files:**
- Create: `src/ai_researcher/trees/__init__.py`
- Create: `src/ai_researcher/trees/build.py` — `build_tree(paper) -> list[TreeNode]`; walks `section` rows, batches summary generation via `llm.gateway.complete(job="node_summary")`
- Create: `src/ai_researcher/trees/version.py` — `TREE_SCHEMA_VERSION` constant and `is_stale(paper)` comparing stored `tree_schema_version` and `summary_model` against current config
- Modify: `src/ai_researcher/cli.py` — register the `index` command
- Test: `tests/fixtures/deep-sections.json` — a 6-level section hierarchy
- Test: `tests/test_tree_builder.py`

**Interfaces:**
- Consumes: `section` rows from Phase 1 task 09; `llm.gateway.complete()` from Phase 1 task 04; `tree_node` from task 01
- Produces: `tree_node` rows — consumed by task 03 shortlisting, task 04 traversal, and Phase 3 claim anchoring

**Behaviour notes:**
- Staleness is per-paper: ingesting 10 new papers costs exactly 10 tree builds
- A paper whose `parse_status` is `abstract_only` gets a single-node tree from its abstract, so it is still reachable by retrieval
- Summary generation failure for one paper is recorded and skipped without aborting the run

## Out of scope

No corpus-level index — task 03 owns the File System layer. No retrieval or traversal. No
extraction. No re-parsing of PDFs; this task reads `section` rows only.
