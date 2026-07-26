"""Topic-scope definitions shared by dialogue, storage, and source adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ScopeDefinition:
    """A persisted, re-runnable scholarly discovery scope."""

    name: str
    description: str
    include_terms: tuple[str, ...]
    exclude_terms: tuple[str, ...]
    categories: tuple[str, ...]
    date_from: date | None
    date_to: date | None
    per_source_limit: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Scope name must not be empty")
        if not self.include_terms:
            raise ValueError("A scope must contain at least one include term")
        if self.per_source_limit < 1:
            raise ValueError("Per-source limit must be a positive integer")
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("Scope start date must not be after its end date")


__all__ = ["ScopeDefinition"]
