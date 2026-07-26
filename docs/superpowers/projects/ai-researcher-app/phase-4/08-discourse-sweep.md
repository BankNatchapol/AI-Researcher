---
title: Run the discourse sweep with per-source failure isolation
order: 8
depends_on_task: 07-evidence-sweep
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 15, 16, 23
skills: test-driven-development, verification-before-completion
---

## Goal

`airesearch sweep --kind discourse` polls every enabled community source since its last run,
stores items and paper mentions, and keeps one broken source from taking down the sweep.

## Acceptance Criteria

- [ ] `uv run airesearch sweep --kind discourse` polls each enabled source since its `last_polled_at` and writes one `sweep_run` row with `kind = 'discourse'`
- [ ] Items are stored with mentions resolved via task 05, and `discourse_source.last_polled_at` advances on success
- [ ] Re-running immediately adds zero duplicate `discourse_item` rows, proving the uniqueness constraint and `since` filtering both work
- [ ] A source raising an error is recorded on the `sweep_run` row while every other source completes, and the command still exits 0
- [ ] `uv run pytest tests/test_discourse_sweep.py` exits 0, covering a clean poll, a repeat poll, one failing source among several, and a source with no credentials being skipped

## Implementation notes

**Files:**
- Create: `src/ai_researcher/monitor/discourse_sweep.py` — iterates enabled sources from the discourse registry, calls `poll(since)`, resolves mentions, persists, updates `last_polled_at`
- Modify: `src/ai_researcher/cli.py` — extend `sweep` to accept `--kind discourse`
- Test: `tests/test_discourse_sweep.py`

**Interfaces:**
- Consumes: discourse registry and adapters (tasks 02–04); `link_targets()` (task 05); `discourse_source`, `discourse_item`, `discourse_mention`, `sweep_run` (task 01)
- Produces: `discourse_item` and `discourse_mention` rows — read by task 09 change detection and task 10 digests

**Isolation notes:**
- `last_polled_at` advances only on a successful poll, so a failing source retries from where
  it left off rather than skipping a window
- A source whose credentials are absent is skipped with a log line and recorded as skipped
  rather than failed, distinguishing "not configured" from "broken"
- This sweep writes only to discourse tables; the channel-separation test from task 02 keeps
  that true as the code changes

## Out of scope

No evidence processing — task 07. No change detection or digests. No scheduling — task 11.
No sentiment analysis, and no path by which any polled number reaches a claim score.
