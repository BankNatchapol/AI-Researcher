---
title: Run the per-paper extraction pipeline with resumability and prompt versioning
order: 3
depends_on_task: 02-extraction-models-validation
project: ai-researcher-app
phase: 3
depends_on_phase: 2
design: docs/superpowers/projects/ai-researcher-app/phase-3/PHASE.md
plan_task: Requirements 7, 8, 9
skills: test-driven-development, verification-before-completion
---

## Goal

`airesearch extract <scope>` walks each paper's tree, extracts claims, methods, results,
datasets, and metrics anchored to nodes, and skips work already done at the current prompt
version.

## Acceptance Criteria

- [ ] `uv run airesearch extract <scope>` extracts from every parsed paper lacking current extractions and reports per-paper counts by record type
- [ ] Re-running with no new papers and no prompt version change extracts zero records and exits 0
- [ ] Every persisted row records `extraction_model` and `prompt_version`
- [ ] Bumping `PROMPT_VERSION` causes only affected papers to be re-extracted on the next run, asserted by a test
- [ ] `uv run pytest tests/test_extraction_pipeline.py` exits 0 with the LLM mocked, covering a clean run, a resumed run, a prompt-version bump, and a per-paper failure that does not abort the run

## Implementation notes

**Files:**
- Create: `src/ai_researcher/extraction/prompts.py` — extraction prompts with a `PROMPT_VERSION` constant
- Create: `src/ai_researcher/extraction/pipeline.py` — `extract_paper(paper) -> ExtractionResult`; groups tree nodes into section batches, calls `llm.gateway.complete(job="extraction")` with structured output, validates via task 02, persists
- Modify: `src/ai_researcher/cli.py` — register the `extract` command with `--scope`
- Test: `tests/test_extraction_pipeline.py`

**Interfaces:**
- Consumes: `tree_node` rows (Phase 2 task 02), `validate_batch()` (task 02), `llm.gateway.complete()` (Phase 1 task 04), extraction tables (task 01)
- Produces: `extract_paper()` — called by task 04 evidence linking, and re-invoked by Phase 4's evidence sweep on newly discovered papers

**Behaviour notes:**
- Extraction is batched per section group rather than per node, keeping call volume proportional to paper count
- Papers with `parse_status = 'abstract_only'` are extracted from their single-node tree, not skipped
- A per-paper failure is recorded and the run continues, matching Phase 1's ingest behaviour

## Out of scope

No evidence linking across papers (task 04), no dedup (task 05), no scoring (tasks 06–07).
No claims CLI (task 08). No re-parsing or re-tree-building; this task reads `tree_node` rows
as they are.
