"""Query extracted claims with both scores kept as distinct fields."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, func, select

from ai_researcher.answer.citation import Citation, render_citation
from ai_researcher.db import connect
from ai_researcher.db.models import claim as claim_table
from ai_researcher.db.models import claim_evidence as claim_evidence_table
from ai_researcher.db.models import claim_score, paper, paper_scope, tree_node
from ai_researcher.db.models import scope as scope_table
from ai_researcher.scoring.confidence import (
    ConfidenceClaim,
    ConfidenceFactor,
    SupportingNode,
    score_confidence,
)
from ai_researcher.scoring.quality import (
    QualityClaim,
    QualityEvidence,
    QualityFactor,
    score_quality,
)

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]


class UnknownScopeError(LookupError):
    """Raised when a claims query names a scope that does not exist."""


class UnknownClaimError(LookupError):
    """Raised when a claim ID cannot be resolved."""


@dataclass(frozen=True, slots=True)
class ClaimFilters:
    """Filters applied when listing claims for a scope."""

    scope: str
    claim_type: str | None = None
    min_confidence: int | None = None
    min_quality: int | None = None


@dataclass(frozen=True, slots=True)
class ScoreFactor:
    """One named contribution to either score."""

    name: str
    raw_value: int | float | str | bool | None
    contribution: float
    max_contribution: float


@dataclass(frozen=True, slots=True)
class ClaimSummary:
    """One claim row for tabular listing."""

    id: int
    claim_text: str
    claim_type: str
    paper_id: int
    confidence: int
    evidence_quality: int
    replication_count: int


@dataclass(frozen=True, slots=True)
class ClaimEvidenceItem:
    """One linked evidence node with stance and verbatim rationale."""

    tree_node_id: int
    paper_id: int
    stance: str
    rationale_text: str
    citation: Citation | None = None


@dataclass(frozen=True, slots=True)
class ClaimDetail:
    """Full claim view including both score factor breakdowns and evidence."""

    id: int
    claim_text: str
    claim_type: str
    paper_id: int
    confidence: int
    evidence_quality: int
    replication_count: int
    confidence_factors: tuple[ScoreFactor, ...]
    evidence_quality_factors: tuple[ScoreFactor, ...]
    evidence: tuple[ClaimEvidenceItem, ...]


def list_claims(
    filters: ClaimFilters,
    *,
    claims: Sequence[ClaimSummary] | None = None,
    connection_factory: ConnectionFactory | None = None,
) -> tuple[ClaimSummary, ...]:
    """Return claims for a scope, filtered without blending the two scores."""

    source = (
        tuple(claims)
        if claims is not None
        else _load_claim_summaries(
            filters.scope,
            connection_factory=connection_factory,
        )
    )
    return tuple(claim for claim in source if _matches_filters(claim, filters))


def get_claim(
    claim_id: int,
    *,
    claim: ClaimDetail | None = None,
    connection_factory: ConnectionFactory | None = None,
) -> ClaimDetail | None:
    """Return one claim with both scores, factors, and linked evidence."""

    if claim is not None:
        return claim if claim.id == claim_id else None
    return _load_claim_detail(claim_id, connection_factory=connection_factory)


def find_claim_evidence(
    claim_id: int,
    *,
    claim: ClaimDetail | None = None,
    connection_factory: ConnectionFactory | None = None,
) -> tuple[ClaimEvidenceItem, ...]:
    """Return every evidence row linked to a claim."""

    detail = get_claim(claim_id, claim=claim, connection_factory=connection_factory)
    if detail is None:
        return ()
    return detail.evidence


def _matches_filters(claim: ClaimSummary, filters: ClaimFilters) -> bool:
    if filters.claim_type is not None and claim.claim_type != filters.claim_type:
        return False
    if filters.min_confidence is not None and claim.confidence < filters.min_confidence:
        return False
    if filters.min_quality is not None and claim.evidence_quality < filters.min_quality:
        return False
    return True


def _load_claim_summaries(
    scope_name: str,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> tuple[ClaimSummary, ...]:
    factory = connect if connection_factory is None else connection_factory
    with factory() as connection:
        _require_scope(connection, scope_name)
        latest_score = _latest_score_subquery()
        replication = _replication_subquery()
        rows = (
            connection.execute(
                select(
                    claim_table.c.id,
                    claim_table.c.claim_text,
                    claim_table.c.claim_type,
                    claim_table.c.paper_id,
                    latest_score.c.confidence,
                    latest_score.c.evidence_quality,
                    func.coalesce(replication.c.replication_count, 0).label("replication_count"),
                )
                .select_from(claim_table)
                .join(paper_scope, paper_scope.c.paper_id == claim_table.c.paper_id)
                .join(scope_table, scope_table.c.id == paper_scope.c.scope_id)
                .join(latest_score, latest_score.c.claim_id == claim_table.c.id)
                .outerjoin(replication, replication.c.claim_id == claim_table.c.id)
                .where(
                    scope_table.c.name == scope_name,
                    claim_table.c.canonical_claim_id.is_(None),
                )
                .order_by(claim_table.c.id)
            )
            .mappings()
            .all()
        )
    return tuple(
        ClaimSummary(
            id=int(row["id"]),
            claim_text=str(row["claim_text"]),
            claim_type=str(row["claim_type"]),
            paper_id=int(row["paper_id"]),
            confidence=int(row["confidence"]),
            evidence_quality=int(row["evidence_quality"]),
            replication_count=int(row["replication_count"]),
        )
        for row in rows
    )


def _load_claim_detail(
    claim_id: int,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> ClaimDetail | None:
    factory = connect if connection_factory is None else connection_factory
    with factory() as connection:
        latest_score = _latest_score_subquery()
        replication = _replication_subquery()
        row = (
            connection.execute(
                select(
                    claim_table.c.id,
                    claim_table.c.claim_text,
                    claim_table.c.claim_type,
                    claim_table.c.paper_id,
                    latest_score.c.confidence,
                    latest_score.c.evidence_quality,
                    func.coalesce(replication.c.replication_count, 0).label("replication_count"),
                    paper.c.parse_status,
                    paper.c.is_preprint,
                    paper.c.venue,
                    paper.c.published_at,
                )
                .select_from(claim_table)
                .join(paper, paper.c.id == claim_table.c.paper_id)
                .outerjoin(latest_score, latest_score.c.claim_id == claim_table.c.id)
                .outerjoin(replication, replication.c.claim_id == claim_table.c.id)
                .where(claim_table.c.id == claim_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        if row["confidence"] is None or row["evidence_quality"] is None:
            raise UnknownClaimError(f"Claim {claim_id} has no claim_score row yet")

        evidence_rows = (
            connection.execute(
                select(
                    claim_evidence_table.c.tree_node_id,
                    claim_evidence_table.c.paper_id,
                    claim_evidence_table.c.stance,
                    claim_evidence_table.c.rationale_text,
                    tree_node.c.section_path,
                    tree_node.c.page_start,
                    tree_node.c.page_end,
                    tree_node.c.body_text,
                )
                .select_from(claim_evidence_table)
                .join(tree_node, tree_node.c.id == claim_evidence_table.c.tree_node_id)
                .where(claim_evidence_table.c.claim_id == claim_id)
                .order_by(claim_evidence_table.c.id)
            )
            .mappings()
            .all()
        )

        evidence_items: list[ClaimEvidenceItem] = []
        for evidence_row in evidence_rows:
            citation = None
            try:
                citation = render_citation(
                    _CitationNode(
                        node_id=int(evidence_row["tree_node_id"]),
                        paper_id=int(evidence_row["paper_id"]),
                        section_path=str(evidence_row["section_path"]),
                        page_start=evidence_row["page_start"],
                        page_end=evidence_row["page_end"],
                    )
                )
            except LookupError:
                citation = None
            evidence_items.append(
                ClaimEvidenceItem(
                    tree_node_id=int(evidence_row["tree_node_id"]),
                    paper_id=int(evidence_row["paper_id"]),
                    stance=str(evidence_row["stance"]),
                    rationale_text=str(evidence_row["rationale_text"]),
                    citation=citation,
                )
            )

        confidence_factors = _confidence_factors(
            connection,
            claim_id=int(row["id"]),
            claim_text=str(row["claim_text"]),
            evidence_rows=evidence_rows,
        )
        quality_factors = _quality_factors(
            claim_id=int(row["id"]),
            parse_status=str(row["parse_status"]),
            is_preprint=bool(row["is_preprint"]),
            venue=None if row["venue"] is None else str(row["venue"]),
            published_at=row["published_at"],
            evidence_rows=evidence_rows,
        )

    return ClaimDetail(
        id=int(row["id"]),
        claim_text=str(row["claim_text"]),
        claim_type=str(row["claim_type"]),
        paper_id=int(row["paper_id"]),
        confidence=int(row["confidence"]),
        evidence_quality=int(row["evidence_quality"]),
        replication_count=int(row["replication_count"]),
        confidence_factors=confidence_factors,
        evidence_quality_factors=quality_factors,
        evidence=tuple(evidence_items),
    )


def _confidence_factors(
    connection: Connection,
    *,
    claim_id: int,
    claim_text: str,
    evidence_rows: Sequence[Mapping[str, Any]],
) -> tuple[ScoreFactor, ...]:
    supporting_nodes = tuple(
        SupportingNode(
            tree_node_id=int(row["tree_node_id"]),
            body_text=str(row["body_text"] or ""),
            paper_id=int(row["paper_id"]),
        )
        for row in evidence_rows
        if str(row["stance"]) == "supports"
    )
    # Self-consistency and validation signals are optional for display; fall
    # back to empty / zero when observations or extraction state are absent.
    from ai_researcher.db.models import claim_extraction_observation, paper_extraction_state

    observations = (
        connection.execute(
            select(claim_extraction_observation.c.claim_text).where(
                claim_extraction_observation.c.claim_id == claim_id
            )
        )
        .scalars()
        .all()
    )
    validation = (
        connection.execute(
            select(
                paper_extraction_state.c.validation_accepted,
                paper_extraction_state.c.validation_rejected,
            )
            .select_from(claim_table)
            .join(
                paper_extraction_state,
                paper_extraction_state.c.paper_id == claim_table.c.paper_id,
            )
            .where(claim_table.c.id == claim_id)
        )
        .mappings()
        .first()
    )
    stopped_reason = "no_candidates"
    from ai_researcher.db.models import retrieval_trace

    trace_row = (
        connection.execute(
            select(retrieval_trace.c.stopped_reason).order_by(retrieval_trace.c.id.desc()).limit(1)
        )
        .scalars()
        .first()
    )
    if trace_row is not None:
        stopped_reason = str(trace_row)

    score = score_confidence(
        ConfidenceClaim(
            id=claim_id,
            claim_text=claim_text,
            supporting_nodes=supporting_nodes,
            repeated_extractions=tuple(str(text) for text in observations),
            stopped_reason=stopped_reason,
            validation_accepted=0 if validation is None else int(validation["validation_accepted"]),
            validation_rejected=0 if validation is None else int(validation["validation_rejected"]),
        )
    )
    return tuple(_from_confidence_factor(factor) for factor in score.factors)


def _quality_factors(
    *,
    claim_id: int,
    parse_status: str,
    is_preprint: bool,
    venue: str | None,
    published_at: Any,
    evidence_rows: Sequence[Mapping[str, Any]],
) -> tuple[ScoreFactor, ...]:
    evidence = tuple(
        QualityEvidence(
            tree_node_id=int(row["tree_node_id"]),
            paper_id=int(row["paper_id"]),
            stance=str(row["stance"]),  # type: ignore[arg-type]
            is_direct=True,
        )
        for row in evidence_rows
    )
    score = score_quality(
        QualityClaim(
            id=claim_id,
            parse_status=parse_status,
            is_preprint=is_preprint,
            venue=venue,
            published_at=published_at,
            evidence=evidence,
        )
    )
    return tuple(_from_quality_factor(factor) for factor in score.factors)


def _from_confidence_factor(factor: ConfidenceFactor) -> ScoreFactor:
    return ScoreFactor(
        name=factor.name,
        raw_value=factor.raw_value,
        contribution=factor.contribution,
        max_contribution=factor.max_contribution,
    )


def _from_quality_factor(factor: QualityFactor) -> ScoreFactor:
    return ScoreFactor(
        name=factor.name,
        raw_value=factor.raw_value,
        contribution=factor.contribution,
        max_contribution=factor.max_contribution,
    )


def _latest_score_subquery() -> Any:
    ranked = select(
        claim_score.c.claim_id,
        claim_score.c.confidence,
        claim_score.c.evidence_quality,
        func.row_number()
        .over(
            partition_by=claim_score.c.claim_id,
            order_by=(claim_score.c.scored_at.desc(), claim_score.c.id.desc()),
        )
        .label("rn"),
    ).subquery()
    return (
        select(
            ranked.c.claim_id,
            ranked.c.confidence,
            ranked.c.evidence_quality,
        )
        .where(ranked.c.rn == 1)
        .subquery()
    )


def _replication_subquery() -> Any:
    supporting = (
        select(
            claim_evidence_table.c.claim_id,
            func.count(func.distinct(claim_evidence_table.c.paper_id)).label("replication_count"),
        )
        .where(claim_evidence_table.c.stance == "supports")
        .group_by(claim_evidence_table.c.claim_id)
        .subquery()
    )
    return supporting


def _require_scope(connection: Connection, scope_name: str) -> None:
    exists = connection.execute(
        select(scope_table.c.id).where(scope_table.c.name == scope_name)
    ).scalar_one_or_none()
    if exists is None:
        raise UnknownScopeError(f"Unknown scope: {scope_name}")


@dataclass(frozen=True, slots=True)
class _CitationNode:
    node_id: int
    paper_id: int
    section_path: str
    page_start: int | None
    page_end: int | None


__all__ = [
    "ClaimDetail",
    "ClaimEvidenceItem",
    "ClaimFilters",
    "ClaimSummary",
    "ScoreFactor",
    "UnknownClaimError",
    "UnknownScopeError",
    "find_claim_evidence",
    "get_claim",
    "list_claims",
]
