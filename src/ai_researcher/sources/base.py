"""Public contracts shared by scholarly evidence-source adapters."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable


class Scope(Protocol):
    """The subset of a persisted scope required by discovery adapters."""

    include_terms: Sequence[str]
    exclude_terms: Sequence[str]
    categories: Sequence[str]
    date_from: date | None
    date_to: date | None


@dataclass(frozen=True, slots=True)
class PaperRef:
    """A lightweight source-owned paper reference returned by discovery."""

    source: str
    external_id: str
    title: str | None = None
    doi: str | None = None
    pdf_url: str | None = None


@dataclass(frozen=True, slots=True)
class PaperMetadata:
    """Normalized paper metadata returned without persistence side effects."""

    source: str
    external_id: str
    title: str
    abstract: str | None = None
    authors: tuple[str, ...] = ()
    published_at: date | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    s2_id: str | None = None
    is_preprint: bool = False
    pdf_url: str | None = None


@runtime_checkable
class EvidenceSource(Protocol):
    """Fixed interface implemented by every scholarly discovery adapter."""

    name: str

    def search(self, scope: Scope, limit: int) -> Iterable[PaperRef]: ...

    def fetch_metadata(self, ref: PaperRef) -> PaperMetadata: ...

    def pdf_url(self, ref: PaperRef) -> str | None: ...
