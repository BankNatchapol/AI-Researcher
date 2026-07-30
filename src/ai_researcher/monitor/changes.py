"""Detect corpus/claim/discourse changes since a baseline timestamp."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, and_, exists, func, select

from ai_researcher.config import get_settings
from ai_researcher.db import connect
from ai_researcher.db.models import (
    claim_evidence,
    claim_score,
    discourse_mention,
    paper,
    paper_scope,
    subscription,
)

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]


@dataclass(frozen=True, slots=True)
class NewPaperChange:
    """A paper newly associated with a subscribed topic scope."""

    paper_id: int
    scope_id: int


@dataclass(frozen=True, slots=True)
class NewEvidenceChange:
    """A new claim_evidence row for a subscribed claim."""

    claim_id: int
    claim_evidence_id: int
    stance: str


@dataclass(frozen=True, slots=True)
class StanceFlipChange:
    """A subscribed claim that gained its first ``refutes`` evidence link."""

    claim_id: int
    claim_evidence_id: int


@dataclass(frozen=True, slots=True)
class ScoreMovementChange:
    """Score movement with separate confidence and evidence-quality deltas."""

    claim_id: int
    confidence_before: int
    confidence_after: int
    confidence_delta: int
    evidence_quality_before: int
    evidence_quality_after: int
    evidence_quality_delta: int


@dataclass(frozen=True, slots=True)
class DiscourseMentionChange:
    """A new discourse mention of a paper that backs a subscribed claim."""

    discourse_mention_id: int
    paper_id: int
    claim_id: int


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """Independent change categories assembled for digest rendering."""

    new_papers: tuple[NewPaperChange, ...]
    new_evidence: tuple[NewEvidenceChange, ...]
    stance_flips: tuple[StanceFlipChange, ...]
    score_movements: tuple[ScoreMovementChange, ...]
    discourse_mentions: tuple[DiscourseMentionChange, ...]


def detect_changes(
    since: datetime,
    *,
    connection_factory: ConnectionFactory | None = None,
    threshold: int | None = None,
) -> ChangeSet:
    """Report subscribed-scope/claim changes since ``since``.

    Each category is queried independently. Score movement compares the two
    most recent ``claim_score`` rows per subscribed claim by ``scored_at`` and
    reports confidence and evidence-quality deltas separately — never blended.
    A movement is only emitted when the newer score's ``scored_at`` is after
    ``since``, so quiet windows do not re-report stale deltas.
    """

    open_connection = connect if connection_factory is None else connection_factory
    movement_threshold = get_settings().score_movement_threshold if threshold is None else threshold

    with open_connection() as connection:
        return ChangeSet(
            new_papers=_new_papers(connection, since),
            new_evidence=_new_evidence(connection, since),
            stance_flips=_stance_flips(connection, since),
            score_movements=_score_movements(connection, since, movement_threshold),
            discourse_mentions=_discourse_mentions(connection, since),
        )


def _active_claim_ids(connection: Connection) -> select:
    return select(subscription.c.claim_id).where(
        subscription.c.kind == "claim",
        subscription.c.active.is_(True),
        subscription.c.claim_id.is_not(None),
    )


def _new_papers(connection: Connection, since: datetime) -> tuple[NewPaperChange, ...]:
    rows = connection.execute(
        select(paper.c.id, paper_scope.c.scope_id)
        .select_from(
            paper.join(paper_scope, paper_scope.c.paper_id == paper.c.id).join(
                subscription,
                and_(
                    subscription.c.scope_id == paper_scope.c.scope_id,
                    subscription.c.kind == "topic",
                    subscription.c.active.is_(True),
                ),
            )
        )
        .where(paper.c.created_at > since)
        .order_by(paper.c.id, paper_scope.c.scope_id)
    ).all()
    return tuple(NewPaperChange(paper_id=int(r.id), scope_id=int(r.scope_id)) for r in rows)


def _new_evidence(connection: Connection, since: datetime) -> tuple[NewEvidenceChange, ...]:
    claim_ids = _active_claim_ids(connection)
    rows = connection.execute(
        select(
            claim_evidence.c.claim_id,
            claim_evidence.c.id,
            claim_evidence.c.stance,
        )
        .where(
            claim_evidence.c.claim_id.in_(claim_ids),
            claim_evidence.c.created_at > since,
        )
        .order_by(claim_evidence.c.id)
    ).all()
    return tuple(
        NewEvidenceChange(
            claim_id=int(r.claim_id),
            claim_evidence_id=int(r.id),
            stance=str(r.stance),
        )
        for r in rows
    )


def _stance_flips(connection: Connection, since: datetime) -> tuple[StanceFlipChange, ...]:
    """First ``refutes`` evidence after ``since`` for claims that had none before."""

    claim_ids = _active_claim_ids(connection)
    prior = claim_evidence.alias("prior_refute")
    new_refute = claim_evidence.alias("new_refute")

    had_prior_refute = exists(
        select(1).where(
            prior.c.claim_id == new_refute.c.claim_id,
            prior.c.stance == "refutes",
            prior.c.created_at <= since,
        )
    )
    ranked = (
        select(
            new_refute.c.claim_id,
            new_refute.c.id,
            func.row_number()
            .over(
                partition_by=new_refute.c.claim_id,
                order_by=new_refute.c.id.asc(),
            )
            .label("rn"),
        )
        .where(
            new_refute.c.claim_id.in_(claim_ids),
            new_refute.c.stance == "refutes",
            new_refute.c.created_at > since,
            ~had_prior_refute,
        )
        .subquery("first_refutes")
    )
    rows = connection.execute(
        select(ranked.c.claim_id, ranked.c.id).where(ranked.c.rn == 1).order_by(ranked.c.id)
    ).all()
    return tuple(
        StanceFlipChange(claim_id=int(r.claim_id), claim_evidence_id=int(r.id)) for r in rows
    )


def _score_movements(
    connection: Connection,
    since: datetime,
    threshold: int,
) -> tuple[ScoreMovementChange, ...]:
    """Compare the two most recent scores per claim; emit only if newer is after ``since``."""

    claim_ids = _active_claim_ids(connection)
    rows = connection.execute(
        select(
            claim_score.c.claim_id,
            claim_score.c.confidence,
            claim_score.c.evidence_quality,
            claim_score.c.scored_at,
            claim_score.c.id,
        )
        .where(claim_score.c.claim_id.in_(claim_ids))
        .order_by(
            claim_score.c.claim_id.asc(),
            claim_score.c.scored_at.desc(),
            claim_score.c.id.desc(),
        )
    ).all()

    by_claim: dict[int, list[tuple[int, int, datetime]]] = {}
    for row in rows:
        claim_id = int(row.claim_id)
        bucket = by_claim.setdefault(claim_id, [])
        if len(bucket) >= 2:
            continue
        bucket.append((int(row.confidence), int(row.evidence_quality), row.scored_at))

    movements: list[ScoreMovementChange] = []
    for claim_id, scores in sorted(by_claim.items()):
        if len(scores) < 2:
            continue
        confidence_after, evidence_quality_after, scored_at_after = scores[0]
        confidence_before, evidence_quality_before, _scored_at_before = scores[1]
        # Quiet windows must not re-report deltas whose newer row is ≤ the baseline.
        if scored_at_after <= since:
            continue
        confidence_delta = confidence_after - confidence_before
        evidence_quality_delta = evidence_quality_after - evidence_quality_before
        confidence_moved = abs(confidence_delta) >= threshold
        quality_moved = abs(evidence_quality_delta) >= threshold
        if not confidence_moved and not quality_moved:
            continue
        movements.append(
            ScoreMovementChange(
                claim_id=claim_id,
                confidence_before=confidence_before,
                confidence_after=confidence_after,
                confidence_delta=confidence_delta,
                evidence_quality_before=evidence_quality_before,
                evidence_quality_after=evidence_quality_after,
                evidence_quality_delta=evidence_quality_delta,
            )
        )
    return tuple(movements)


def _discourse_mentions(
    connection: Connection,
    since: datetime,
) -> tuple[DiscourseMentionChange, ...]:
    claim_ids = _active_claim_ids(connection)
    # Mentions of papers that already back a subscribed claim via claim_evidence.
    backing = (
        select(
            claim_evidence.c.claim_id,
            claim_evidence.c.paper_id,
        )
        .where(claim_evidence.c.claim_id.in_(claim_ids))
        .distinct()
        .subquery("backing_papers")
    )
    rows = connection.execute(
        select(
            discourse_mention.c.id,
            discourse_mention.c.paper_id,
            backing.c.claim_id,
        )
        .select_from(
            discourse_mention.join(
                backing,
                backing.c.paper_id == discourse_mention.c.paper_id,
            )
        )
        .where(discourse_mention.c.created_at > since)
        .order_by(discourse_mention.c.id, backing.c.claim_id)
    ).all()
    return tuple(
        DiscourseMentionChange(
            discourse_mention_id=int(r.id),
            paper_id=int(r.paper_id),
            claim_id=int(r.claim_id),
        )
        for r in rows
    )
