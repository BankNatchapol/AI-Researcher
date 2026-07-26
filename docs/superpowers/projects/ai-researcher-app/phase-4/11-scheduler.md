---
title: Schedule the daily evidence and discourse sweeps
order: 11
depends_on_task: 10-digest-builder
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 22
skills: test-driven-development, verification-before-completion
---

## Goal

Both sweeps run daily without manual invocation, and the researcher can see when each will
next fire.

## Acceptance Criteria

- [ ] `uv run airesearch schedule start` runs APScheduler in the foreground with the evidence and discourse sweeps registered as daily jobs
- [ ] `uv run airesearch schedule status` reports the next run time for each job
- [ ] Sweep times are configurable via `SWEEP_EVIDENCE_HOUR` and `SWEEP_DISCOURSE_HOUR`, defaulting to different hours so the two never contend
- [ ] A job raising an error is logged and does not stop the scheduler, asserted by a test with a deliberately failing job
- [ ] `uv run pytest tests/test_scheduler.py` exits 0, covering job registration, next-run reporting, and failure isolation, with the scheduler run in test mode rather than blocking

## Implementation notes

**Files:**
- Create: `src/ai_researcher/monitor/scheduler.py` — APScheduler `BlockingScheduler`; registers both sweeps; `next_run_times()` for the status command
- Modify: `src/ai_researcher/config.py` — add `SWEEP_EVIDENCE_HOUR` (default 6) and `SWEEP_DISCOURSE_HOUR` (default 7)
- Modify: `.env.example` — document both
- Modify: `src/ai_researcher/cli.py` — register the `schedule` group with `start` and `status`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `sweep()` (task 07) and `discourse_sweep()` (task 08)
- Produces: the scheduled runtime — the last piece making the system operate unattended

**Behaviour notes:**
- The scheduler runs in the foreground so the researcher controls its lifecycle with normal
  shell job control; no daemon, no launchd plist, no service installation
- Jobs use `misfire_grace_time` so a laptop asleep at the scheduled hour still runs the sweep
  on wake rather than silently skipping the day — the failure mode that would quietly make
  monitoring useless
- The two sweeps are separate jobs, so discourse polling failures never delay evidence
  processing

## Out of scope

No daemonization, launchd integration, or system service installation. No digest generation
on a schedule — digests stay on-demand in v1. No notification delivery. No distributed or
multi-machine scheduling.
