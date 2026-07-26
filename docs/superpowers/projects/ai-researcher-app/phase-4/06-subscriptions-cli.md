---
title: Add topic and claim subscriptions
order: 6
depends_on_task: 05-paper-link-resolution
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 13
skills: test-driven-development, verification-before-completion
---

## Goal

A researcher can subscribe to a whole topic or to one specific claim, and unsubscribe without
losing the history of what was already tracked.

## Acceptance Criteria

- [ ] `uv run airesearch subscribe topic <scope>` creates an active topic subscription
- [ ] `uv run airesearch subscribe claim <claim-id>` creates an active claim subscription and rejects an unknown claim ID with a named error
- [ ] `uv run airesearch subscriptions` lists all subscriptions with kind, target, and active state
- [ ] `uv run airesearch unsubscribe <id>` sets `active = false` and leaves the row in place, verified by a test asserting the row still exists after unsubscribing
- [ ] `uv run pytest tests/test_subscriptions.py` exits 0, covering both kinds, duplicate prevention, unknown targets, and the deactivate-not-delete behaviour

## Implementation notes

**Files:**
- Create: `src/ai_researcher/monitor/__init__.py`
- Create: `src/ai_researcher/monitor/subscription.py` — create, list, deactivate; enforces the exactly-one-target rule at the application layer as well as in the schema
- Modify: `src/ai_researcher/cli.py` — register `subscribe`, `subscriptions`, `unsubscribe`
- Test: `tests/test_subscriptions.py`

**Interfaces:**
- Consumes: `subscription` table (task 01); `scope` rows (Phase 1 task 07); `claim` rows (Phase 3 task 03)
- Produces: active subscriptions — read by task 07 evidence sweep, task 09 change detection, task 10 digests

**Behaviour notes:**
- A claim subscription targets the canonical claim from Phase 3 task 05, so tracking survives
  later dedup merges rather than pointing at an orphaned duplicate
- Subscribing twice to the same target is rejected rather than creating a second row
- Claim-level subscription is what the design doc identifies as the differentiator: most tools
  monitor papers, not the evolution of a specific proposition

## Out of scope

No sweeps or scheduling — tasks 07, 08, 11. No digest rendering — task 10. No notification
delivery of any kind. No subscription editing beyond activate and deactivate.
