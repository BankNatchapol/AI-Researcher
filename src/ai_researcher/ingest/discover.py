"""Discover candidate papers for a scope via registered evidence adapters."""

from __future__ import annotations

from collections.abc import Iterable

from ai_researcher.ingest.dedup import MergedPaper, resolve_identity
from ai_researcher.scoping import ScopeDefinition
from ai_researcher.sources import registry
from ai_researcher.sources.base import EvidenceSource, PaperMetadata, Scope


def discover_candidates(
    scope: ScopeDefinition | Scope,
    *,
    sources: Iterable[EvidenceSource] | None = None,
) -> list[MergedPaper]:
    """Search every adapter, fetch metadata, and merge duplicate identities."""

    adapters = registry.registered() if sources is None else tuple(sources)
    limit = getattr(scope, "per_source_limit", 100)
    candidates: list[PaperMetadata] = []
    for adapter in adapters:
        for ref in adapter.search(scope, limit):
            candidates.append(adapter.fetch_metadata(ref))
    return resolve_identity(candidates)


__all__ = ["discover_candidates"]
