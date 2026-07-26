"""Cheap corpus-size estimates over lightweight adapter search results."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ai_researcher.scoping import ScopeDefinition
from ai_researcher.sources import registry
from ai_researcher.sources.base import EvidenceSource, PaperRef


def estimate_scope(
    scope: ScopeDefinition,
    *,
    sources: Iterable[EvidenceSource] | None = None,
) -> int:
    """Estimate unique candidates without fetching metadata or PDFs."""

    adapters = registry.registered() if sources is None else tuple(sources)
    identities: set[tuple[str, str]] = set()
    for adapter in adapters:
        for ref in adapter.search(scope, scope.per_source_limit):
            identities.add(_reference_identity(ref))
    return len(identities)


def _reference_identity(ref: PaperRef) -> tuple[str, str]:
    if ref.doi:
        return "doi", _normalize_doi(ref.doi)
    if ref.title:
        normalized_title = re.sub(r"\W+", "", ref.title.casefold())
        if normalized_title:
            return "title", normalized_title
    return ref.source, ref.external_id


def _normalize_doi(doi: str) -> str:
    normalized = doi.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            return normalized.removeprefix(prefix)
    return normalized


__all__ = ["estimate_scope"]
