"""Per-paper tree schema and summary-model invalidation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_researcher.config import get_settings

TREE_SCHEMA_VERSION = "1"


@dataclass(frozen=True, slots=True)
class TreeVersionState:
    """Versions shared by every node in one persisted paper tree."""

    tree_schema_version: str
    summary_model: str


def current_summary_model() -> str:
    """Return the configured backend identity used for node summaries."""

    settings = get_settings()
    return settings.llm_backend_overrides.get(
        "NODE_SUMMARY",
        settings.llm_backend_default,
    ).lower()


def is_stale(
    paper: TreeVersionState | Any | None,
    *,
    summary_model: str | None = None,
) -> bool:
    """Report whether a paper tree is absent or uses an outdated version."""

    if paper is None:
        return True
    expected_model = current_summary_model() if summary_model is None else summary_model
    return (
        _value(paper, "tree_schema_version") != TREE_SCHEMA_VERSION
        or _value(paper, "summary_model") != expected_model
    )


def _value(record: Any, name: str) -> Any:
    if isinstance(record, dict):
        return record.get(name)
    mapping = getattr(record, "_mapping", None)
    if mapping is not None:
        return mapping.get(name)
    return getattr(record, name, None)


__all__ = [
    "TREE_SCHEMA_VERSION",
    "TreeVersionState",
    "current_summary_model",
    "is_stale",
]
