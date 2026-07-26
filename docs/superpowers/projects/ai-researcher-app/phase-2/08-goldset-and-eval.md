---
title: Build the evaluation gold set and retrieval eval harness
order: 8
depends_on_task: 07-mcp-server
project: ai-researcher-app
phase: 2
depends_on_phase: 1
design: docs/superpowers/projects/ai-researcher-app/phase-2/PHASE.md
plan_task: Requirements 21, 22, 23, 24
skills: test-driven-development, verification-before-completion
---

## Goal

A hand-labelled gold set and a scoring command make retrieval quality measurable, so the
PageIndex-versus-Postgres question and every later change are settled by evidence.

## Acceptance Criteria

- [ ] `eval/goldset.yaml` contains at least 20 questions, each with the question text, its scope, and the `section_path`s of sections that genuinely answer it
- [ ] `uv run airesearch eval --scope <name>` reports retrieval recall@k against gold sections, citation precision, and the unsupported-statement rate
- [ ] Each eval run writes a JSON report to `docs/supersaiyan/runs/eval-<date>.json` so runs are comparable over time
- [ ] `uv run pytest tests/test_eval_harness.py` exits 0, running the harness end to end against a committed fixture corpus with no network access
- [ ] Running eval under both `SHORTLIST_BACKEND` values produces comparable reports, demonstrating the fallback path from task 03 is measurable

## Implementation notes

**Files:**
- Create: `eval/goldset.yaml` — 20+ entries over the quantum and AI domains
- Create: `src/ai_researcher/eval/__init__.py`
- Create: `src/ai_researcher/eval/goldset.py` — loads and validates the gold set, failing loudly on a `section_path` that matches no section
- Create: `src/ai_researcher/eval/harness.py` — runs each question, compares retrieved nodes to gold sections, computes recall@k, citation precision, and unsupported-statement rate
- Modify: `src/ai_researcher/cli.py` — register the `eval` command with `--scope`
- Test: `tests/fixtures/eval-corpus/` — a small committed corpus with known sections
- Test: `tests/test_eval_harness.py`

**Interfaces:**
- Consumes: `traverse()` (task 04), `synthesize()` (task 05), `section`/`tree_node` rows
- Produces: `eval/goldset.yaml` and `eval/harness.py` — extended in Phase 3 with extraction precision, recall, F1, evidence-span precision, and stance accuracy

**Metric definitions (so results are comparable across runs):**
- **recall@k** — fraction of gold sections appearing in the top *k* retrieved nodes
- **citation precision** — fraction of cited nodes that are gold sections for that question
- **unsupported-statement rate** — fraction of answer statements carrying no valid node attribution

## Out of scope

No extraction metrics — Phase 3 extends this harness. No human-rating workflow, no
inter-annotator agreement tooling. No CI gate on metric thresholds; this task makes quality
measurable, not enforced.
