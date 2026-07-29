"""Score how reliably the pipeline extracted a claim.

Confidence is deliberately independent of scientific evidence quality. The
weights below describe pipeline behavior only and sum to 100:

* independent supporting nodes: 25
* verbatim claim/node overlap: 25
* repeated-extraction self-consistency: 20
* retrieval stopping reason: 20
* schema-validation cleanliness: 10
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import Connection, insert, select

from ai_researcher.db import connect
from ai_researcher.db.models import claim as claim_table
from ai_researcher.db.models import (
    claim_evidence,
    claim_score,
    paper_scope,
    retrieval_trace,
    section,
    tree_node,
)
from ai_researcher.db.models import scope as scope_table
from ai_researcher.logging import get_logger

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
ClaimLike = Mapping[str, Any] | Any

SUPPORTING_NODES_WEIGHT = 25.0
VERBATIM_OVERLAP_WEIGHT = 25.0
SELF_CONSISTENCY_WEIGHT = 20.0
STOPPED_REASON_WEIGHT = 20.0
VALIDATION_CLEANLINESS_WEIGHT = 10.0
PENDING_EVIDENCE_QUALITY = 0
PENDING_RUBRIC_VERSION = "pending-evidence-quality"

_STOPPED_REASON_VALUES = {
    "sufficient_evidence": 1.0,
    "budget_exhausted": 0.25,
    "no_candidates": 0.0,
}
_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SupportingNode:
    """One independent supporting node and the source text used for overlap."""

    tree_node_id: int
    body_text: str
    paper_id: int | None = None


@dataclass(frozen=True, slots=True)
class ConfidenceClaim:
    """All pipeline signals needed to score one claim."""

    id: int
    claim_text: str
    supporting_nodes: tuple[SupportingNode, ...]
    repeated_extractions: tuple[str, ...]
    stopped_reason: str
    validation_accepted: int
    validation_rejected: int


@dataclass(frozen=True, slots=True)
class ConfidenceFactor:
    """A named raw signal and its weighted contribution."""

    name: str
    raw_value: int | float | str
    contribution: float
    max_contribution: float


@dataclass(frozen=True, slots=True)
class ConfidenceScore:
    """A bounded confidence value and every factor that produced it."""

    value: int
    factors: tuple[ConfidenceFactor, ...]

    @property
    def confidence(self) -> int:
        """Alias matching the ``claim_score.confidence`` column name."""

        return self.value

    @property
    def score(self) -> int:
        """Convenience alias for callers displaying the numeric score."""

        return self.value


@dataclass(frozen=True, slots=True)
class ConfidenceScopeResult:
    """Summary of scoring all currently unscored claims in a scope."""

    scored: int
    failed: int
    scores: tuple[ConfidenceScore, ...]


class ConfidenceStore(Protocol):
    """Persistence operations needed by scope-level confidence scoring."""

    def load_unscored_claims(self, scope_name: str) -> tuple[ClaimLike, ...]:
        """Return enriched claim inputs that do not yet have a score."""

    def save_confidence(self, claim_id: int, confidence: int) -> None:
        """Persist only the pipeline confidence calculation."""


class PostgresConfidenceStore:
    """Load confidence signals and persist scores in PostgreSQL."""

    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connect if connection_factory is None else connection_factory

    def load_unscored_claims(self, scope_name: str) -> tuple[ConfidenceClaim, ...]:
        scored_claim = (
            select(claim_score.c.id).where(claim_score.c.claim_id == claim_table.c.id).exists()
        )
        with self._connection_factory() as connection:
            scope_id = connection.execute(
                select(scope_table.c.id).where(scope_table.c.name == scope_name)
            ).scalar_one_or_none()
            if scope_id is None:
                raise ValueError(f"Unknown scope: {scope_name}")

            candidates = (
                connection.execute(
                    select(
                        claim_table.c.id,
                        claim_table.c.claim_text,
                        claim_table.c.normalized_text,
                        claim_table.c.canonical_claim_id,
                    )
                    .join(paper_scope, paper_scope.c.paper_id == claim_table.c.paper_id)
                    .where(
                        paper_scope.c.scope_id == scope_id,
                        ~scored_claim,
                    )
                    .order_by(claim_table.c.id)
                )
                .mappings()
                .all()
            )
            if not candidates:
                return ()

            root_ids = {int(row["canonical_claim_id"] or row["id"]) for row in candidates}
            group_rows = (
                connection.execute(
                    select(
                        claim_table.c.id,
                        claim_table.c.claim_text,
                        claim_table.c.canonical_claim_id,
                    ).where(
                        (claim_table.c.id.in_(root_ids))
                        | (claim_table.c.canonical_claim_id.in_(root_ids))
                    )
                )
                .mappings()
                .all()
            )
            extractions_by_root: dict[int, list[tuple[int, str]]] = {
                root_id: [] for root_id in root_ids
            }
            for row in group_rows:
                root_id = int(row["canonical_claim_id"] or row["id"])
                extractions_by_root.setdefault(root_id, []).append(
                    (int(row["id"]), str(row["claim_text"]))
                )

            evidence_rows = (
                connection.execute(
                    select(
                        claim_evidence.c.claim_id,
                        claim_evidence.c.tree_node_id,
                        claim_evidence.c.paper_id,
                        section.c.body_text,
                    )
                    .join(tree_node, tree_node.c.id == claim_evidence.c.tree_node_id)
                    .join(section, section.c.id == tree_node.c.section_id)
                    .where(
                        claim_evidence.c.claim_id.in_(root_ids),
                        claim_evidence.c.stance == "supports",
                    )
                    .order_by(claim_evidence.c.id)
                )
                .mappings()
                .all()
            )
            nodes_by_root: dict[int, list[SupportingNode]] = {root_id: [] for root_id in root_ids}
            for row in evidence_rows:
                nodes_by_root[int(row["claim_id"])].append(
                    SupportingNode(
                        tree_node_id=int(row["tree_node_id"]),
                        body_text=str(row["body_text"] or ""),
                        paper_id=int(row["paper_id"]),
                    )
                )

            questions = {
                str(row["normalized_text"]).strip()
                for row in candidates
                if str(row["normalized_text"]).strip()
            }
            trace_rows = (
                connection.execute(
                    select(
                        retrieval_trace.c.question,
                        retrieval_trace.c.stopped_reason,
                        retrieval_trace.c.created_at,
                    )
                    .where(
                        retrieval_trace.c.scope_id == scope_id,
                        retrieval_trace.c.question.in_(questions),
                    )
                    .order_by(retrieval_trace.c.created_at.desc())
                )
                .mappings()
                .all()
                if questions
                else []
            )
            stopped_reason_by_question: dict[str, str] = {}
            for row in trace_rows:
                stopped_reason_by_question.setdefault(
                    str(row["question"]),
                    str(row["stopped_reason"]),
                )

        claims: list[ConfidenceClaim] = []
        for row in candidates:
            claim_id = int(row["id"])
            root_id = int(row["canonical_claim_id"] or claim_id)
            normalized_text = str(row["normalized_text"]).strip()
            repeated_extractions = tuple(
                text
                for extraction_id, text in extractions_by_root.get(root_id, ())
                if extraction_id != claim_id
            )
            claims.append(
                ConfidenceClaim(
                    id=claim_id,
                    claim_text=str(row["claim_text"]),
                    supporting_nodes=tuple(nodes_by_root.get(root_id, ())),
                    repeated_extractions=repeated_extractions,
                    stopped_reason=stopped_reason_by_question.get(
                        normalized_text,
                        "no_candidates",
                    ),
                    # Persisted claims passed schema validation. Rejected
                    # records are never stored as claims.
                    validation_accepted=1,
                    validation_rejected=0,
                )
            )
        return tuple(claims)

    def save_confidence(self, claim_id: int, confidence: int) -> None:
        with self._connection_factory() as connection:
            connection.execute(
                insert(claim_score).values(
                    claim_id=claim_id,
                    confidence=confidence,
                    # Task 07 owns the real evidence-quality calculation.
                    evidence_quality=PENDING_EVIDENCE_QUALITY,
                    rubric_version=PENDING_RUBRIC_VERSION,
                )
            )


def score_confidence(claim: ClaimLike) -> ConfidenceScore:
    """Return a 0–100 pipeline confidence score with named contributions."""

    candidate = _coerce_claim(claim)
    distinct_nodes = {node.tree_node_id: node for node in candidate.supporting_nodes}
    node_count = len(distinct_nodes)
    node_ratio = min(node_count / 3.0, 1.0)
    overlap_ratio = max(
        (_token_coverage(candidate.claim_text, node.body_text) for node in distinct_nodes.values()),
        default=0.0,
    )
    consistency_ratio = _self_consistency(
        candidate.claim_text,
        candidate.repeated_extractions,
    )
    stopped_ratio = _STOPPED_REASON_VALUES.get(candidate.stopped_reason, 0.0)
    validation_total = candidate.validation_accepted + candidate.validation_rejected
    validation_ratio = (
        candidate.validation_accepted / validation_total if validation_total > 0 else 0.0
    )

    factors = (
        _factor(
            "independent_supporting_nodes",
            node_count,
            node_ratio,
            SUPPORTING_NODES_WEIGHT,
        ),
        _factor(
            "verbatim_overlap",
            overlap_ratio,
            overlap_ratio,
            VERBATIM_OVERLAP_WEIGHT,
        ),
        _factor(
            "self_consistency",
            consistency_ratio,
            consistency_ratio,
            SELF_CONSISTENCY_WEIGHT,
        ),
        _factor(
            "retrieval_stopped_reason",
            candidate.stopped_reason,
            stopped_ratio,
            STOPPED_REASON_WEIGHT,
        ),
        _factor(
            "schema_validation_cleanliness",
            validation_ratio,
            validation_ratio,
            VALIDATION_CLEANLINESS_WEIGHT,
        ),
    )
    value = max(0, min(100, round(sum(factor.contribution for factor in factors))))
    return ConfidenceScore(value=value, factors=factors)


def score_scope_confidence(
    scope_name: str,
    *,
    store: ConfidenceStore | None = None,
) -> ConfidenceScopeResult:
    """Score every currently unscored claim, recording failures per claim."""

    confidence_store = PostgresConfidenceStore() if store is None else store
    try:
        claims = confidence_store.load_unscored_claims(scope_name)
    except Exception:  # noqa: BLE001 — stage failure is reported, not raised
        logger.exception("Confidence scoring could not load scope %s", scope_name)
        return ConfidenceScopeResult(scored=0, failed=1, scores=())
    scores: list[ConfidenceScore] = []
    failed = 0
    for claim in claims:
        try:
            claim_id = _positive_integer(_field(claim, "id"), "id")
            result = score_confidence(claim)
            confidence_store.save_confidence(claim_id, result.value)
        except Exception:  # noqa: BLE001 — one claim must not abort the scope
            failed += 1
            logger.exception(
                "Confidence scoring failed for claim %r",
                _field(claim, "id", default=None),
            )
            continue
        scores.append(result)
    return ConfidenceScopeResult(
        scored=len(scores),
        failed=failed,
        scores=tuple(scores),
    )


def _factor(
    name: str,
    raw_value: int | float | str,
    ratio: float,
    weight: float,
) -> ConfidenceFactor:
    return ConfidenceFactor(
        name=name,
        raw_value=raw_value,
        contribution=round(max(0.0, min(1.0, ratio)) * weight, 4),
        max_contribution=weight,
    )


def _coerce_claim(claim: ClaimLike) -> ConfidenceClaim:
    if isinstance(claim, ConfidenceClaim):
        return claim
    claim_id = _positive_integer(_field(claim, "id"), "id")
    claim_text = str(_field(claim, "claim_text")).strip()
    if not claim_text:
        raise ValueError("Claim claim_text must not be empty")

    nodes: list[SupportingNode] = []
    for raw_node in _field(claim, "supporting_nodes", default=()):
        if isinstance(raw_node, SupportingNode):
            node = raw_node
        else:
            raw_paper_id = _field(raw_node, "paper_id", default=None)
            node = SupportingNode(
                tree_node_id=_positive_integer(
                    _field(raw_node, "tree_node_id"),
                    "tree_node_id",
                ),
                body_text=str(_field(raw_node, "body_text")),
                paper_id=(
                    _positive_integer(raw_paper_id, "paper_id")
                    if raw_paper_id is not None
                    else None
                ),
            )
        nodes.append(node)

    repeated_extractions = tuple(
        str(text).strip()
        for text in _field(claim, "repeated_extractions", default=())
        if str(text).strip()
    )
    validation_accepted = _nonnegative_integer(
        _field(claim, "validation_accepted", default=0),
        "validation_accepted",
    )
    validation_rejected = _nonnegative_integer(
        _field(claim, "validation_rejected", default=0),
        "validation_rejected",
    )
    return ConfidenceClaim(
        id=claim_id,
        claim_text=claim_text,
        supporting_nodes=tuple(nodes),
        repeated_extractions=repeated_extractions,
        stopped_reason=str(_field(claim, "stopped_reason", default="no_candidates")),
        validation_accepted=validation_accepted,
        validation_rejected=validation_rejected,
    )


def _token_coverage(claim_text: str, body_text: str) -> float:
    claim_tokens = Counter(_tokens(claim_text))
    if not claim_tokens:
        return 0.0
    body_tokens = Counter(_tokens(body_text))
    overlap = sum((claim_tokens & body_tokens).values())
    return overlap / sum(claim_tokens.values())


def _self_consistency(claim_text: str, repeated_extractions: tuple[str, ...]) -> float:
    if not repeated_extractions:
        return 0.0
    claim_tokens = set(_tokens(claim_text))
    if not claim_tokens:
        return 0.0
    similarities: list[float] = []
    for extraction in repeated_extractions:
        repeated_tokens = set(_tokens(extraction))
        union = claim_tokens | repeated_tokens
        similarities.append(len(claim_tokens & repeated_tokens) / len(union) if union else 0.0)
    return sum(similarities) / len(similarities)


def _tokens(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.casefold())


def _field(value: ClaimLike, field_name: str, *, default: Any = ...) -> Any:
    if isinstance(value, Mapping):
        if default is ...:
            return value[field_name]
        return value.get(field_name, default)
    if default is ...:
        return getattr(value, field_name)
    return getattr(value, field_name, default)


def _positive_integer(value: Any, field_name: str) -> int:
    integer = _nonnegative_integer(value, field_name)
    if integer < 1:
        raise ValueError(f"Claim {field_name} must be positive")
    return integer


def _nonnegative_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Claim {field_name} must be an integer")
    try:
        integer = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Claim {field_name} must be an integer") from error
    if integer < 0:
        raise ValueError(f"Claim {field_name} must not be negative")
    return integer


__all__ = [
    "ConfidenceClaim",
    "ConfidenceFactor",
    "ConfidenceScopeResult",
    "ConfidenceScore",
    "ConfidenceStore",
    "PostgresConfidenceStore",
    "SupportingNode",
    "score_confidence",
    "score_scope_confidence",
]
