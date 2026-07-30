# QA Report — issue #70 · v1

**Issue:** #70 — Schedule the daily evidence and discourse sweeps  
**PR:** #82  
**Branch:** `issue-70-schedule-the-daily-evidence-and-discourse-sweeps`  
**Commit under test:** (see tip after evidence commit)  
**Task file:** `docs/superpowers/projects/ai-researcher-app/phase-4/11-scheduler.md`  
**Result:** PASS  
**When:** 2026-07-30

## Acceptance criteria

| AC | Criterion | Command / check | Result |
|----|-----------|-----------------|--------|
| AC1 | `airesearch schedule start` registers daily evidence + discourse jobs (foreground APScheduler; non-blocking in tests) | `test_cli_schedule_start_*` + `test_build_scheduler_*` | ✅ |
| AC2 | `airesearch schedule status` reports next run time for each job | `test_cli_schedule_status_*` + `test_next_run_times_*` + live CLI smoke | ✅ |
| AC3 | Hours via `SWEEP_EVIDENCE_HOUR` / `SWEEP_DISCOURSE_HOUR`; defaults differ (6 vs 7) | defaults + env override + `.env.example` tests | ✅ |
| AC4 | Failing job logged; does not stop scheduler | `test_failing_job_*` (deliberate boom; second job still runs) | ✅ |
| AC5 | `uv run pytest tests/test_scheduler.py` exits 0 | 9 passed | ✅ |

## Commands run (exit 0)

```bash
uv run pytest tests/test_scheduler.py -v   # 9 passed
uv run ruff check .                        # All checks passed
uv run ruff format --check .               # 143 files already formatted
uv run airesearch schedule status          # evidence + discourse next_run lines
```

## Tester note

Hardened AC4 assertion: package logging uses `propagate=False`, so `caplog` alone was order-flaky. Replaced with `patch.object(scheduler_mod.logger, "exception")` while keeping the deliberate-failure + second-job-runs contract.

Full-tree `uv run pytest` hit 72 Postgres fixture setup errors (local test DB unreachable) — environmental, not in AC scope; see `full-pytest-note.md`.

## Evidence files

- `ac-mapping.md`
- `ac-focused-pytest.log`
- `ac1-schedule-start.log`
- `ac2-schedule-status.log`
- `ac2-cli-status-smoke.log`
- `ac3-sweep-hours.log`
- `ac4-failure-isolation.log`
- `full-pytest.log` / `full-pytest-note.md`
- `ruff-check.log` / `ruff-format.log`

## Visual evidence

Omitted intentionally — CLI/library task (no UI ACs).

## Notes for Reviewer

- `BlockingScheduler` registers `evidence_sweep` + `discourse_sweep` with `CronTrigger(hour=…)` and `misfire_grace_time=6h`.
- Defaults: evidence hour 6, discourse hour 7 (non-contending).
- `_safe_job` wraps each sweep so exceptions are logged and isolated.
- CLI: `airesearch schedule start|status`.
