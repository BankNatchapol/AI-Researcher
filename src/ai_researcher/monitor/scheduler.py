"""APScheduler wiring for daily evidence and discourse sweeps."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from ai_researcher.config import get_settings
from ai_researcher.logging import get_logger

logger = get_logger(__name__)

JOB_EVIDENCE = "evidence_sweep"
JOB_DISCOURSE = "discourse_sweep"

# Laptop asleep at the scheduled hour should still run the sweep on wake.
MISFIRE_GRACE_SECONDS = 6 * 60 * 60

EvidenceFn = Callable[[], Any]
DiscourseFn = Callable[[], Any]


def _safe_job(name: str, fn: Callable[[], Any]) -> Callable[[], None]:
    """Wrap a job so a raised error is logged and does not stop the scheduler."""

    def run() -> None:
        try:
            fn()
        except Exception:  # noqa: BLE001 — one job must not kill the scheduler
            logger.exception("Scheduled job %s failed", name)

    return run


def _default_evidence_fn() -> Any:
    from ai_researcher.monitor.sweep import run_evidence_sweep

    return run_evidence_sweep()


def _default_discourse_fn() -> Any:
    from ai_researcher.monitor.discourse_sweep import run_discourse_sweep

    return run_discourse_sweep()


def build_scheduler(
    *,
    evidence_hour: int | None = None,
    discourse_hour: int | None = None,
    evidence_fn: EvidenceFn | None = None,
    discourse_fn: DiscourseFn | None = None,
) -> BlockingScheduler:
    """Build a BlockingScheduler with both daily sweeps registered (not started)."""

    settings = get_settings()
    hour_evidence = settings.sweep_evidence_hour if evidence_hour is None else evidence_hour
    hour_discourse = settings.sweep_discourse_hour if discourse_hour is None else discourse_hour
    run_evidence = evidence_fn if evidence_fn is not None else _default_evidence_fn
    run_discourse = discourse_fn if discourse_fn is not None else _default_discourse_fn

    scheduler = BlockingScheduler()
    scheduler.add_job(
        _safe_job(JOB_EVIDENCE, run_evidence),
        CronTrigger(hour=hour_evidence),
        id=JOB_EVIDENCE,
        name="Evidence sweep",
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_job(JOB_DISCOURSE, run_discourse),
        CronTrigger(hour=hour_discourse),
        id=JOB_DISCOURSE,
        name="Discourse sweep",
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
        coalesce=True,
        replace_existing=True,
    )
    return scheduler


def next_run_times(
    scheduler: BlockingScheduler | None = None,
) -> dict[str, datetime]:
    """Return the next fire time for each registered sweep job."""

    active = scheduler if scheduler is not None else build_scheduler()
    now = datetime.now(tz=active.timezone)
    times: dict[str, datetime] = {}
    for job_id in (JOB_EVIDENCE, JOB_DISCOURSE):
        job = active.get_job(job_id)
        if job is None:
            raise RuntimeError(f"Scheduler job {job_id} is not registered")
        next_time = job.trigger.get_next_fire_time(None, now)
        if next_time is None:
            raise RuntimeError(f"Scheduler job {job_id} has no next run time")
        times[job_id] = next_time
    return times


def start_scheduler() -> None:
    """Run the scheduler in the foreground until interrupted."""

    scheduler = build_scheduler()
    logger.info(
        "Starting scheduler (evidence hour=%s, discourse hour=%s)",
        get_settings().sweep_evidence_hour,
        get_settings().sweep_discourse_hour,
    )
    scheduler.start()


__all__ = [
    "JOB_DISCOURSE",
    "JOB_EVIDENCE",
    "BlockingScheduler",
    "build_scheduler",
    "next_run_times",
    "start_scheduler",
]
