---
title: Extend the eval harness with extraction and stance metrics
order: 9
depends_on_task: 08-claims-cli-and-mcp
project: ai-researcher-app
phase: 3
depends_on_phase: 2
design: docs/superpowers/projects/ai-researcher-app/phase-3/PHASE.md
plan_task: Requirements 23, 24
skills: test-driven-development, verification-before-completion
---

## Goal

Extraction quality is measurable against hand-labelled claims, so prompt and model changes
are judged by evidence rather than impression.

## Acceptance Criteria

- [ ] `eval/goldset.yaml` gains at least 15 hand-labelled claims, each with its `section_path` anchor and expected stance
- [ ] `uv run airesearch eval --extraction --scope <name>` reports claim extraction precision, recall, and F1; evidence-span precision; and stance-label accuracy
- [ ] Extraction results append to the same `docs/supersaiyan/runs/eval-<date>.json` report the retrieval metrics write to
- [ ] Gold-set validation fails loudly when a labelled `section_path` matches no section in the corpus
- [ ] `uv run pytest tests/test_extraction_eval.py` exits 0, running against the committed fixture corpus with no network access

## Implementation notes

**Files:**
- Modify: `eval/goldset.yaml` — add a `claims:` block alongside the existing questions
- Modify: `src/ai_researcher/eval/goldset.py` — load and validate labelled claims
- Create: `src/ai_researcher/eval/extraction_metrics.py` — precision, recall, F1, evidence-span precision, stance accuracy
- Modify: `src/ai_researcher/eval/harness.py` — add the `--extraction` path, appending to the same report
- Modify: `src/ai_researcher/cli.py` — add the `--extraction` flag to `eval`
- Test: `tests/test_extraction_eval.py`

**Interfaces:**
- Consumes: `claim`, `claim_evidence` rows; the Phase 2 gold set and harness
- Produces: extraction metrics in the shared eval report — the baseline Phase 4 sweeps must not regress

**Metric definitions (stated so runs stay comparable):**
- **claim precision** — fraction of extracted claims matching a gold claim
- **claim recall** — fraction of gold claims found
- **evidence-span precision** — fraction of `claim_evidence` rows whose node matches the gold anchor
- **stance accuracy** — fraction of evidence links whose stance matches the gold label

**Matching rule:** an extracted claim matches a gold claim when normalized text matches and,
for numeric claims, `object_value` and `unit` agree — reusing task 02's quantity parsing so
eval and dedup judge equality identically.

## Out of scope

No CI gate on thresholds; this makes quality measurable, not enforced. No human-rating
workflow or inter-annotator agreement. No calibration curve between confidence and
correctness. No monitoring metrics — Phase 4 has no eval requirements of its own.
