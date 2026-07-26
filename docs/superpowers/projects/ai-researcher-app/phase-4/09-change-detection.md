---
title: Detect what changed since the last completed sweep
order: 9
depends_on_task: 08-discourse-sweep
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 18
skills: test-driven-development, verification-before-completion
---

## Goal

Comparing the current state against the last completed sweep yields a precise list of what
changed — including claim-level stance flips and score movement, not just new papers.

## Acceptance Criteria

- [ ] `detect_changes(since) -> ChangeSet` reports new papers per subscribed scope, new `claim_evidence` rows for subscribed claims, stance flips, score movement beyond a threshold, and new `discourse_mention` rows for papers backing subscribed claims
- [ ] A claim that gains its first `refutes` evidence link is reported as a stance flip, asserted by a test
- [ ] Score movement is reported as separate confidence and evidence-quality deltas, never a single blended number
- [ ] The movement threshold defaults to 10 points and is configurable
- [ ] `uv run pytest tests/test_change_detection.py` exits 0, covering each change category and a quiet period producing an empty `ChangeSet`

## Implementation notes

**Files:**
- Create: `src/ai_researcher/monitor/changes.py` — `detect_changes(since)`; queries each category independently and assembles a `ChangeSet`
- Modify: `src/ai_researcher/config.py` — add `SCORE_MOVEMENT_THRESHOLD` defaulting to 10
- Test: `tests/test_change_detection.py`

**Interfaces:**
- Consumes: `sweep_run` (task 01), `paper`/`paper_scope` (Phase 1), `claim_evidence` and `claim_score` with `scored_at` (Phase 3), `discourse_mention` (tasks 01, 05), subscriptions (task 06)
- Produces: `ChangeSet` — rendered by task 10's digest

**Detection notes:**
- The comparison baseline is the last `sweep_run` with a terminal `completed` state, so a
  failed sweep does not silently consume a reporting window
- Score movement compares the two most recent `claim_score` rows per claim by `scored_at`,
  which is why Phase 3 stores scores as timestamped rows rather than mutable columns
- Discourse changes are collected into their own field on `ChangeSet`, keeping the two
  channels separate all the way through to rendering

## Out of scope

No rendering or formatting — task 10 owns the digest. No scheduling — task 11. No
notification delivery. No inference about why something changed; detection reports facts only.
