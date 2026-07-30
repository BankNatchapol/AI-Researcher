"""Scheduler: daily evidence and discourse sweeps without blocking the test suite."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest
from typer.testing import CliRunner


def _set_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/research")
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")


def test_sweep_hours_default_to_different_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.delenv("SWEEP_EVIDENCE_HOUR", raising=False)
    monkeypatch.delenv("SWEEP_DISCOURSE_HOUR", raising=False)

    from ai_researcher.config import get_settings

    settings = get_settings()

    assert settings.sweep_evidence_hour == 6
    assert settings.sweep_discourse_hour == 7
    assert settings.sweep_evidence_hour != settings.sweep_discourse_hour


def test_sweep_hours_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv("SWEEP_EVIDENCE_HOUR", "2")
    monkeypatch.setenv("SWEEP_DISCOURSE_HOUR", "14")

    from ai_researcher.config import get_settings

    settings = get_settings()

    assert settings.sweep_evidence_hour == 2
    assert settings.sweep_discourse_hour == 14


def test_build_scheduler_registers_daily_evidence_and_discourse_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.delenv("SWEEP_EVIDENCE_HOUR", raising=False)
    monkeypatch.delenv("SWEEP_DISCOURSE_HOUR", raising=False)

    from ai_researcher.monitor.scheduler import (
        JOB_DISCOURSE,
        JOB_EVIDENCE,
        build_scheduler,
    )

    calls: list[str] = []
    scheduler = build_scheduler(
        evidence_fn=lambda: calls.append("evidence"),
        discourse_fn=lambda: calls.append("discourse"),
    )

    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {JOB_EVIDENCE, JOB_DISCOURSE}

    evidence = jobs[JOB_EVIDENCE]
    discourse = jobs[JOB_DISCOURSE]
    evidence_hour = next(f for f in evidence.trigger.fields if f.name == "hour")
    discourse_hour = next(f for f in discourse.trigger.fields if f.name == "hour")
    assert evidence_hour.expressions[0].first == 6
    assert discourse_hour.expressions[0].first == 7
    assert evidence.misfire_grace_time is not None and evidence.misfire_grace_time > 0
    assert discourse.misfire_grace_time is not None and discourse.misfire_grace_time > 0
    assert calls == []  # registration must not run sweeps


def test_next_run_times_reports_both_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_environment(monkeypatch)

    from ai_researcher.monitor.scheduler import (
        JOB_DISCOURSE,
        JOB_EVIDENCE,
        build_scheduler,
        next_run_times,
    )

    scheduler = build_scheduler(
        evidence_fn=lambda: None,
        discourse_fn=lambda: None,
    )
    times = next_run_times(scheduler)

    assert set(times) == {JOB_EVIDENCE, JOB_DISCOURSE}
    assert isinstance(times[JOB_EVIDENCE], datetime)
    assert isinstance(times[JOB_DISCOURSE], datetime)
    assert times[JOB_EVIDENCE] is not None
    assert times[JOB_DISCOURSE] is not None


def test_failing_job_is_logged_and_does_not_stop_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)

    from ai_researcher.monitor import scheduler as scheduler_mod

    ran_second = {"ok": False}

    def boom() -> None:
        raise RuntimeError("deliberate job failure")

    def ok() -> None:
        ran_second["ok"] = True

    scheduler = scheduler_mod.build_scheduler(
        evidence_fn=boom,
        discourse_fn=ok,
        evidence_hour=6,
        discourse_hour=7,
    )

    evidence_job = scheduler.get_job(scheduler_mod.JOB_EVIDENCE)
    discourse_job = scheduler.get_job(scheduler_mod.JOB_DISCOURSE)
    assert evidence_job is not None
    assert discourse_job is not None

    # Package logger uses propagate=False, so patch logger.exception directly.
    with patch.object(scheduler_mod.logger, "exception") as mock_exception:
        evidence_job.func()  # wrapped callable must swallow the error
        discourse_job.func()

    assert ran_second["ok"] is True
    mock_exception.assert_called_once()
    assert mock_exception.call_args.args == ("Scheduled job %s failed", "evidence_sweep")


def test_cli_schedule_status_reports_next_run_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)

    from ai_researcher.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["schedule", "status"])

    assert result.exit_code == 0, result.output
    lower = result.output.lower()
    assert "evidence" in lower
    assert "discourse" in lower
    # ISO-ish datetime fragment should appear twice (one per job)
    assert result.output.count("-") >= 2


def test_cli_schedule_start_registers_jobs_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`schedule start` must wire APScheduler; tests inject a non-blocking start."""

    _set_required_environment(monkeypatch)

    from ai_researcher.cli import app
    from ai_researcher.monitor import scheduler as scheduler_mod

    started: dict[str, object] = {}

    def fake_start(self: object) -> None:  # noqa: ANN001 — mirrors BlockingScheduler.start
        started["scheduler"] = self
        started["jobs"] = {job.id for job in self.get_jobs()}  # type: ignore[attr-defined]

    monkeypatch.setattr(
        scheduler_mod.BlockingScheduler,
        "start",
        fake_start,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["schedule", "start"])

    assert result.exit_code == 0, result.output
    assert started.get("jobs") == {
        scheduler_mod.JOB_EVIDENCE,
        scheduler_mod.JOB_DISCOURSE,
    }


def test_env_example_documents_sweep_hours() -> None:
    text = Path(".env.example").read_text(encoding="utf-8")
    assert "SWEEP_EVIDENCE_HOUR" in text
    assert "SWEEP_DISCOURSE_HOUR" in text


def test_scheduler_module_exports(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_environment(monkeypatch)
    from ai_researcher.monitor import scheduler as mod

    assert hasattr(mod, "build_scheduler")
    assert hasattr(mod, "next_run_times")
    assert hasattr(mod, "start_scheduler")
    assert isinstance(mod, ModuleType)
