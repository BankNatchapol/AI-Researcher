---
title: Add the extraction, evidence, and dual-score schema
order: 1
depends_on_task: null
project: ai-researcher-app
phase: 3
depends_on_phase: 2
design: docs/superpowers/projects/ai-researcher-app/phase-3/PHASE.md
plan_task: Requirements 1, 2, 3, 4
skills: test-driven-development, verification-before-completion
---

## Goal

The database holds claims, methods, results, datasets, metrics, evidence links, and two
independent scores — with passage anchoring enforced at the constraint level.

## Acceptance Criteria

- [ ] `uv run airesearch db migrate` applies the new migration and exits 0; re-running reports "already up to date"
- [ ] `claim`, `method`, `result`, `dataset`, and `metric` tables exist, each with `paper_id` and a `NOT NULL` `tree_node_id` foreign key to `tree_node`
- [ ] `claim_evidence` exists with `id, claim_id, tree_node_id, paper_id, stance, rationale_text, created_at`, with `stance` constrained to `supports`, `refutes`, `mentions`
- [ ] `claim_score` exists with `confidence` and `evidence_quality` as two separate `NOT NULL` columns plus `rubric_version` and `scored_at`
- [ ] `uv run pytest tests/test_extraction_schema.py` exits 0, asserting an insert with a null `tree_node_id` is rejected on every extraction table, and that an invalid `stance` value is rejected

## Implementation notes

**Files:**
- Create: `src/ai_researcher/db/migrations/0004_extraction.sql`
- Modify: `src/ai_researcher/db/models.py` — add all seven table definitions
- Test: `tests/test_extraction_schema.py`

**Interfaces:**
- Consumes: `tree_node` from Phase 2 task 01; `paper` from Phase 1 task 03; the migration runner
- Produces: the extraction and scoring tables — written by tasks 03, 04, 06, 07; read by task 08 and by Phase 4 subscriptions and digests

**Schema notes:**
- `claim` carries `claim_text`, `normalized_text`, `claim_type`, `subject`, `predicate`, `object_value`, `unit`, `canonical_claim_id`, `extraction_model`, `prompt_version`
- `claim.canonical_claim_id` self-references `claim.id`, null when the claim is itself canonical
- `object_value` is numeric and `unit` is text, kept separate so quantities compare numerically rather than as strings
- There is deliberately **no** combined-score column; PROJECT.md requires the two scores stay separate

## Out of scope

No extraction logic, no scoring computation, no LLM calls. No discourse tables — Phase 4.
Do not add any column that blends confidence and evidence quality.
