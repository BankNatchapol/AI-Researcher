"""Expansion-budget accounting for vectorless tree traversal."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_NODES = 40


@dataclass(slots=True)
class ExpansionBudget:
    """Count node expansions across every shortlisted paper in one traversal."""

    limit: int
    used: int = 0

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("Node expansion limit must be a positive integer")
        if self.used < 0 or self.used > self.limit:
            raise ValueError("Used node expansions must be between zero and the limit")

    @property
    def remaining(self) -> int:
        """Return how many more nodes may be opened."""

        return self.limit - self.used

    @property
    def exhausted(self) -> bool:
        """Return whether no more nodes may be opened."""

        return self.remaining == 0

    def consume(self, count: int) -> None:
        """Record expansions without permitting the caller to exceed the limit."""

        if count < 0:
            raise ValueError("Expansion count must not be negative")
        if count > self.remaining:
            raise ValueError("Node expansion budget exceeded")
        self.used += count


__all__ = ["DEFAULT_MAX_NODES", "ExpansionBudget"]
