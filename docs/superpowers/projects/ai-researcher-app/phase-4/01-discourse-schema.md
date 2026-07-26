---
title: Add the discourse, subscription, and sweep schema
order: 1
depends_on_task: null
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 1, 2, 3, 4, 5
skills: test-driven-development, verification-before-completion
---

## Goal

Community attention, subscriptions, and sweep runs have their own tables — deliberately
separate from every evidence and scoring table.

## Acceptance Criteria

- [ ] `uv run airesearch db migrate` applies the new migration and exits 0; re-running reports "already up to date"
- [ ] `discourse_source`, `discourse_item`, `discourse_mention`, `subscription`, and `sweep_run` all exist with the columns named in PHASE.md Requirements 1–5
- [ ] `discourse_item` enforces uniqueness on `(source_id, external_id)`, asserted by a test that a duplicate insert is rejected
- [ ] `subscription` enforces that exactly one of `scope_id` and `claim_id` is non-null, asserted by a test rejecting both-null and both-set rows
- [ ] `uv run pytest tests/test_discourse_schema.py` exits 0, additionally asserting no discourse table carries a foreign key into `claim_score`

## Implementation notes

**Files:**
- Create: `src/ai_researcher/db/migrations/0005_discourse.sql`
- Modify: `src/ai_researcher/db/models.py` — add the five table definitions
- Test: `tests/test_discourse_schema.py`

**Interfaces:**
- Consumes: `paper` (Phase 1), `claim` (Phase 3), `scope` (Phase 1), the migration runner
- Produces: the discourse and monitoring tables — written by tasks 03–08, read by tasks 09–10

**Schema notes:**
- `sweep_run.kind` is constrained to `evidence` or `discourse`
- `subscription.kind` is constrained to `topic` or `claim`, with a check constraint enforcing
  the exactly-one-target rule
- `discourse_mention.resolved_by` records whether the paper link came from an arXiv ID or a DOI
- `discourse_item` stores `score` and `num_comments` as plain attention counts — these are
  never read by any scoring code

## Out of scope

No adapters, no sweeps, no digests. No column anywhere in these tables that feeds a claim or
evidence score — PROJECT.md bars discourse data from scoring permanently.
