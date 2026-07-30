# AC mapping — issue #70 · QA v1

| AC | Criterion | Observable check | Command / test |
|----|-----------|------------------|----------------|
| AC1 | `airesearch schedule start` runs APScheduler with both daily sweeps registered | CLI start with non-blocking `BlockingScheduler.start` monkeypatch; job IDs present | `test_cli_schedule_start_registers_jobs_without_blocking` + `test_build_scheduler_registers_daily_evidence_and_discourse_jobs` |
| AC2 | `airesearch schedule status` reports next run time for each job | CLI status output names evidence + discourse and includes datetime fragments | `test_cli_schedule_status_reports_next_run_times` + `test_next_run_times_reports_both_jobs` |
| AC3 | Hours configurable via `SWEEP_EVIDENCE_HOUR` / `SWEEP_DISCOURSE_HOUR`; defaults differ | Defaults 6≠7; env override 2/14; `.env.example` documents both | `test_sweep_hours_default_to_different_values` + `test_sweep_hours_read_from_environment` + `test_env_example_documents_sweep_hours` |
| AC4 | Failing job logged; does not stop scheduler | Deliberate boom job swallowed; second job still runs; ERROR log | `test_failing_job_is_logged_and_does_not_stop_scheduler` |
| AC5 | `pytest tests/test_scheduler.py` exits 0 (test mode, non-blocking) | Full focused suite green | `uv run pytest tests/test_scheduler.py` |

Visual ACs: none (CLI/library). Screenshots omitted intentionally.
