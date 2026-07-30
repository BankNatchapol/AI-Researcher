"""Public contracts for community-attention discourse adapters.

Deliberately distinct from ``ai_researcher.sources.base.EvidenceSource`` —
the two protocols share no common base class beyond ``typing.Protocol``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from ai_researcher.sources.base import PaperRef


@dataclass(frozen=True, slots=True)
class DiscourseItem:
    """A community post/item returned by a discourse adapter (no persistence)."""

    source: str
    external_id: str
    url: str
    title: str | None = None
    author: str | None = None
    body: str | None = None
    posted_at: datetime | None = None
    score: int | None = None
    num_comments: int | None = None


class DiscourseLinkMixin:
    """Shared default ``link_targets`` — adapters inherit instead of reimplementing."""

    def link_targets(self, item: DiscourseItem) -> list[PaperRef]:
        from ai_researcher.discourse.resolve import link_targets as resolve_link_targets

        return resolve_link_targets(item)


@runtime_checkable
class DiscourseSource(Protocol):
    """Fixed interface implemented by every community-attention adapter."""

    name: str

    def poll(self, since: datetime) -> Iterable[DiscourseItem]: ...

    def link_targets(self, item: DiscourseItem) -> list[PaperRef]: ...
