"""Monitoring package — subscriptions, sweeps, and change detection."""

from ai_researcher.monitor.changes import ChangeSet, detect_changes
from ai_researcher.monitor.discourse_sweep import run_discourse_sweep
from ai_researcher.monitor.subscription import (
    list_subscriptions,
    subscribe_claim,
    subscribe_topic,
    unsubscribe,
)
from ai_researcher.monitor.sweep import SweepResult, run_evidence_sweep

__all__ = [
    "ChangeSet",
    "SweepResult",
    "detect_changes",
    "list_subscriptions",
    "run_discourse_sweep",
    "run_evidence_sweep",
    "subscribe_claim",
    "subscribe_topic",
    "unsubscribe",
]
