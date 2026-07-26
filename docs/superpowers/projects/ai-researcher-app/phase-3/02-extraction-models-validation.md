---
title: Define extraction models and reject unanchored records
order: 2
depends_on_task: 01-extraction-schema
project: ai-researcher-app
phase: 3
depends_on_phase: 2
design: docs/superpowers/projects/ai-researcher-app/phase-3/PHASE.md
plan_task: Requirements 5, 6, 10
skills: test-driven-development, verification-before-completion
---

## Goal

LLM extraction output is validated against strict models before it can reach the database,
with unanchored or malformed records rejected rather than persisted.

## Acceptance Criteria

- [ ] Pydantic models exist for claim, method, result, dataset, and metric, each requiring a non-empty `tree_node_id`
- [ ] A record missing `tree_node_id` fails validation with a named error and is logged, never persisted
- [ ] Numeric claims parse `object_value` as a number and `unit` as separate text, so `"1%"` yields value `1` and unit `%`
- [ ] Malformed LLM output is retried once, then recorded as a paper-level failure without raising
- [ ] `uv run pytest tests/test_extraction_validation.py` exits 0, covering a valid record, a missing anchor, unparseable JSON, and three numeric-unit variants including `1%`, `0.01`, and `1e-2`

## Implementation notes

**Files:**
- Create: `src/ai_researcher/extraction/__init__.py`
- Create: `src/ai_researcher/extraction/schema.py` — pydantic models with `tree_node_id` required on every type
- Create: `src/ai_researcher/extraction/validate.py` — `validate_batch(raw, allowed_node_ids) -> ValidationOutcome`; rejects records citing node IDs outside the paper being extracted
- Create: `src/ai_researcher/extraction/quantities.py` — `parse_quantity(text) -> tuple[float | None, str | None]`
- Test: `tests/test_extraction_validation.py`

**Interfaces:**
- Consumes: `tree_node` IDs from Phase 2 task 02
- Produces: validated model instances — consumed by task 03's pipeline before any write

**Validation notes:**
- A record citing a `tree_node_id` belonging to a different paper is rejected; this is the
  mechanism preventing cross-paper anchor corruption
- Rejection is always logged with the offending record so extraction quality is debuggable

## Out of scope

No pipeline orchestration or LLM calls — task 03. No database writes. No evidence linking,
scoring, or dedup. No figure or table parsing; extraction in this phase is text-only.
