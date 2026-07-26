---
title: Build the interactive topic scoping dialogue and scope CLI
order: 7
depends_on_task: 06-paper-dedup-provenance
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 12, 13
skills: test-driven-development, verification-before-completion
---

## Goal

A researcher turns a broad topic into a narrow, persisted, re-runnable scope definition
through a dialogue that shows the candidate count shrinking as each decision is made.

## Acceptance Criteria

- [ ] `uv run airesearch scope new <name>` runs a dialogue that proposes sub-topics, adjacent terms, and exclusions, then writes one `scope` row
- [ ] The dialogue prints a candidate-count estimate before narrowing and after each accepted decision, so the effect of every choice is visible
- [ ] `uv run airesearch scope show <name>` prints include terms, exclude terms, arXiv categories, date range, per-source limit, and the current estimated corpus size
- [ ] `uv run airesearch scope list` prints every scope with its name and estimated size
- [ ] `uv run pytest tests/test_scoping.py` exits 0 with the LLM mocked and counts served from adapter fixtures

## Implementation notes

**Files:**
- Create: `src/ai_researcher/scoping/__init__.py`
- Create: `src/ai_researcher/scoping/dialogue.py` — proposes candidates via `llm.gateway.complete(job="scoping")`, applies user accept/reject, re-estimates after each round
- Create: `src/ai_researcher/scoping/store.py` — persist and load `scope` rows
- Create: `src/ai_researcher/scoping/estimate.py` — candidate count via adapter `search` with a result cap, without fetching metadata or PDFs
- Modify: `src/ai_researcher/cli.py` — register the `scope` subcommand group with `new`, `list`, `show`
- Test: `tests/test_scoping.py`

**Interfaces:**
- Consumes: `llm.gateway.complete()` (task 04), `sources.registry` (task 05), `scope` table (task 03)
- Produces: persisted `scope` rows — consumed by task 10 ingest, Phase 2 indexing and asking, Phase 4 topic subscriptions

**Behaviour notes:**
- Estimation must be cheap: count-only queries, never full metadata fetches
- A scope is re-runnable — `ingest` reads the stored definition and never re-opens the dialogue

## Out of scope

No ingestion, PDF fetching, or parsing — task 10 runs the pipeline. No enforcement of the
1,000-paper ceiling here; the dialogue only reports estimates, and task 10 enforces the limit.
No scope editing after creation.
