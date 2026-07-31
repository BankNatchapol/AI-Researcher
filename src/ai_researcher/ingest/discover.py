"""Discover candidate papers for a scope via registered evidence adapters."""

from __future__ import annotations

from collections.abc import Iterable

from ai_researcher.ingest.dedup import MergedPaper, resolve_identity
from ai_researcher.logging import get_logger
from ai_researcher.scoping import ScopeDefinition
from ai_researcher.sources import registry
from ai_researcher.sources.base import EvidenceSource, PaperMetadata, Scope

logger = get_logger(__name__)


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
        try:
            refs = list(adapter.search(scope, limit))
        except Exception:  # noqa: BLE001 — one source must not abort discovery
            logger.exception("Candidate discovery search failed for source %s", adapter.name)
            continue
        for ref in refs:
            try:
                candidates.append(adapter.fetch_metadata(ref))
            except Exception:  # noqa: BLE001 — one paper must not abort discovery
                logger.exception(
                    "Metadata fetch failed for %s from source %s",
                    ref.external_id,
                    adapter.name,
                )
    return resolve_identity(candidates)


__all__ = ["discover_candidates"]
