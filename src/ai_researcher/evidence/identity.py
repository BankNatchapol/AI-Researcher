"""Canonicalize duplicate claims after a cheap, deterministic prefilter."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, NamedTuple, Protocol, TypeAlias

from sqlalchemy import Connection, delete, or_, select, update

from ai_researcher.db import connect
from ai_researcher.db.models import claim as claim_table
from ai_researcher.db.models import claim_evidence as claim_evidence_table
from ai_researcher.db.models import paper_scope
from ai_researcher.db.models import scope as scope_table
from ai_researcher.extraction.quantities import parse_quantity
from ai_researcher.llm import gateway

ClaimLike: TypeAlias = Mapping[str, Any] | Any
CompleteFn = Callable[..., str | dict]
ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
_RANGE_TOLERANCE = 0.05

IDENTITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "comparisons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "left_id": {"type": "integer"},
                    "right_id": {"type": "integer"},
                    "same_claim": {"type": "boolean"},
                },
                "required": ["left_id", "right_id", "same_claim"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["comparisons"],
    "additionalProperties": False,
}


class ClaimPair(NamedTuple):
    """Two claims whose structured fields make an LLM comparison worthwhile."""

    left: ClaimLike
    right: ClaimLike


@dataclass(frozen=True, slots=True)
class CanonicalGroup:
    """A canonical claim and every original claim row it represents."""

    canonical_id: int
    claim_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    """Summary of one identity-comparison batch."""

    pairs_compared: int
    canonical_claims: int
    merged_claims: int


class IdentityStore(Protocol):
    """Persistence operation used after duplicate groups are decided."""

    def save_canonical_groups(self, groups: list[CanonicalGroup]) -> None:
        """Point originals and evidence at each group's canonical claim."""


class PostgresClaimIdentityStore:
    """Persist canonical links without deleting or rewriting original claims."""

    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connect if connection_factory is None else connection_factory

    def load_claims(self, scope_name: str) -> tuple[ClaimLike, ...]:
        with self._connection_factory() as connection:
            rows = (
                connection.execute(
                    select(
                        claim_table.c.id,
                        claim_table.c.paper_id,
                        claim_table.c.claim_text,
                        claim_table.c.normalized_text,
                        claim_table.c.claim_type,
                        claim_table.c.predicate,
                        claim_table.c.object_value,
                        claim_table.c.unit,
                        claim_table.c.canonical_claim_id,
                    )
                    .join(paper_scope, paper_scope.c.paper_id == claim_table.c.paper_id)
                    .join(scope_table, scope_table.c.id == paper_scope.c.scope_id)
                    .where(
                        scope_table.c.name == scope_name,
                        claim_table.c.canonical_claim_id.is_(None),
                    )
                    .order_by(claim_table.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(rows)

    def save_canonical_groups(self, groups: list[CanonicalGroup]) -> None:
        with self._connection_factory() as connection:
            for group in groups:
                if group.canonical_id not in group.claim_ids:
                    raise ValueError("Canonical claim must be a member of its group")
                duplicate_ids = [
                    claim_id for claim_id in group.claim_ids if claim_id != group.canonical_id
                ]
                connection.execute(
                    update(claim_table)
                    .where(claim_table.c.id == group.canonical_id)
                    .values(canonical_claim_id=None)
                )
                if duplicate_ids:
                    connection.execute(
                        update(claim_table)
                        .where(
                            or_(
                                claim_table.c.id.in_(duplicate_ids),
                                claim_table.c.canonical_claim_id.in_(duplicate_ids),
                            )
                        )
                        .values(canonical_claim_id=group.canonical_id)
                    )
                evidence_rows = (
                    connection.execute(
                        select(
                            claim_evidence_table.c.id,
                            claim_evidence_table.c.claim_id,
                            claim_evidence_table.c.paper_id,
                        )
                        .where(claim_evidence_table.c.claim_id.in_(group.claim_ids))
                        .order_by(claim_evidence_table.c.id)
                    )
                    .mappings()
                    .all()
                )
                ordered_evidence = sorted(
                    evidence_rows,
                    key=lambda row: (
                        int(row["claim_id"]) != group.canonical_id,
                        int(row["id"]),
                    ),
                )
                kept_by_paper: dict[int, int] = {}
                stale_evidence_ids: list[int] = []
                for row in ordered_evidence:
                    evidence_id = int(row["id"])
                    paper_id = int(row["paper_id"])
                    if paper_id in kept_by_paper:
                        stale_evidence_ids.append(evidence_id)
                    else:
                        kept_by_paper[paper_id] = evidence_id
                if stale_evidence_ids:
                    connection.execute(
                        delete(claim_evidence_table).where(
                            claim_evidence_table.c.id.in_(stale_evidence_ids)
                        )
                    )
                if kept_by_paper:
                    connection.execute(
                        update(claim_evidence_table)
                        .where(claim_evidence_table.c.id.in_(kept_by_paper.values()))
                        .values(claim_id=group.canonical_id)
                    )


def prefilter_pairs(claims: Iterable[ClaimLike]) -> list[ClaimPair]:
    """Return pairs matching on type, metric, unit, and numeric range."""

    grouped: dict[tuple[str, str, str], list[tuple[ClaimLike, float]]] = {}
    for candidate in claims:
        claim_type = _normalized_text(_field(candidate, "claim_type"))
        metric = _normalized_text(
            _field(candidate, "metric", default=_field(candidate, "predicate", default=None))
        )
        quantity = _normalized_quantity(candidate)
        if not claim_type or not metric or quantity is None:
            continue
        value, unit = quantity
        grouped.setdefault((claim_type, metric, unit), []).append((candidate, value))

    pairs: list[ClaimPair] = []
    for candidates in grouped.values():
        for index, (left, left_value) in enumerate(candidates):
            for right, right_value in candidates[index + 1 :]:
                if _ranges_overlap(left_value, right_value):
                    pairs.append(ClaimPair(left, right))
    return pairs


def canonicalize(
    pairs: Iterable[ClaimPair],
    *,
    complete_fn: CompleteFn | None = None,
    store: IdentityStore | None = None,
) -> CanonicalizationResult:
    """Compare only prefiltered pairs in one model call and save duplicate groups."""

    candidates = list(pairs)
    if not candidates:
        return CanonicalizationResult(
            pairs_compared=0,
            canonical_claims=0,
            merged_claims=0,
        )

    payload = {
        "instructions": (
            "Decide whether each pair states the same scientific claim. "
            "The structured fields have already passed a non-LLM compatibility prefilter. "
            "Require the propositions to be semantically equivalent; a shared topic alone "
            "is not enough. Return exactly one decision for every pair."
        ),
        "candidate_pairs": [
            {
                "left": _claim_payload(pair.left),
                "right": _claim_payload(pair.right),
            }
            for pair in candidates
        ],
    }
    call_model = gateway.complete if complete_fn is None else complete_fn
    response = call_model(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        job="claim_identity",
        schema=IDENTITY_SCHEMA,
    )
    duplicate_pairs = _validated_duplicate_pairs(response, candidates)
    groups = _canonical_groups(duplicate_pairs)
    if store is not None and groups:
        store.save_canonical_groups(groups)
    return CanonicalizationResult(
        pairs_compared=len(candidates),
        canonical_claims=len(groups),
        merged_claims=sum(len(group.claim_ids) - 1 for group in groups),
    )


def canonicalize_scope(
    scope_name: str,
    *,
    complete_fn: CompleteFn | None = None,
    store: PostgresClaimIdentityStore | None = None,
) -> CanonicalizationResult:
    """Prefilter and canonicalize every claim in one saved scope."""

    identity_store = PostgresClaimIdentityStore() if store is None else store
    claims = identity_store.load_claims(scope_name)
    return canonicalize(
        prefilter_pairs(claims),
        complete_fn=complete_fn,
        store=identity_store,
    )


def _validated_duplicate_pairs(
    response: str | dict,
    candidates: list[ClaimPair],
) -> list[tuple[int, int]]:
    if not isinstance(response, dict) or not isinstance(response.get("comparisons"), list):
        raise ValueError("Claim identity model returned an invalid response")

    expected = {
        (_integer_field(pair.left, "id"), _integer_field(pair.right, "id")) for pair in candidates
    }
    seen: set[tuple[int, int]] = set()
    duplicates: list[tuple[int, int]] = []
    for comparison in response["comparisons"]:
        if not isinstance(comparison, dict):
            raise ValueError("Claim identity model returned an invalid comparison")
        left_id = comparison.get("left_id")
        right_id = comparison.get("right_id")
        same_claim = comparison.get("same_claim")
        pair_ids = (left_id, right_id)
        if (
            isinstance(left_id, bool)
            or not isinstance(left_id, int)
            or isinstance(right_id, bool)
            or not isinstance(right_id, int)
            or not isinstance(same_claim, bool)
            or pair_ids not in expected
            or pair_ids in seen
        ):
            raise ValueError("Claim identity model returned an invalid comparison")
        seen.add(pair_ids)
        if same_claim:
            duplicates.append(pair_ids)
    if seen != expected:
        raise ValueError("Claim identity model must compare every prefiltered pair exactly once")
    return duplicates


def _canonical_groups(duplicate_pairs: list[tuple[int, int]]) -> list[CanonicalGroup]:
    parent: dict[int, int] = {}
    members: dict[int, set[int]] = {}
    accepted_pairs = {
        (min(left_id, right_id), max(left_id, right_id)) for left_id, right_id in duplicate_pairs
    }

    def find(claim_id: int) -> int:
        parent.setdefault(claim_id, claim_id)
        members.setdefault(claim_id, {claim_id})
        while parent[claim_id] != claim_id:
            parent[claim_id] = parent[parent[claim_id]]
            claim_id = parent[claim_id]
        return claim_id

    for left_id, right_id in sorted(accepted_pairs):
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root == right_root:
            continue
        if not all(
            (min(left_member, right_member), max(left_member, right_member)) in accepted_pairs
            for left_member in members[left_root]
            for right_member in members[right_root]
        ):
            continue
        new_root = min(left_root, right_root)
        old_root = max(left_root, right_root)
        parent[old_root] = new_root
        members[new_root].update(members.pop(old_root))

    return [
        CanonicalGroup(canonical_id=root, claim_ids=tuple(sorted(claim_ids)))
        for root, claim_ids in sorted(members.items())
        if len(claim_ids) > 1
    ]


def _claim_payload(claim: ClaimLike) -> dict[str, Any]:
    return {
        "id": _integer_field(claim, "id"),
        "paper_id": _integer_field(claim, "paper_id"),
        "claim_text": _field(claim, "claim_text", default=""),
        "normalized_text": _field(claim, "normalized_text", default=""),
        "claim_type": _field(claim, "claim_type"),
        "metric": _field(
            claim,
            "metric",
            default=_field(claim, "predicate", default=None),
        ),
        "object_value": _field(claim, "object_value", default=None),
        "unit": _field(claim, "unit", default=None),
    }


def _normalized_quantity(claim: ClaimLike) -> tuple[float, str] | None:
    raw_value = _field(claim, "object_value", default=None)
    raw_unit = _field(claim, "unit", default=None)
    parsed_value, parsed_unit = parse_quantity(raw_value)
    if parsed_value is None:
        return None
    unit = raw_unit if raw_unit not in (None, "") else parsed_unit
    normalized_unit = _normalized_text(unit)
    if normalized_unit in {"%", "percent", "percentage"}:
        return parsed_value / 100.0, ""
    return parsed_value, normalized_unit


def _ranges_overlap(left: float, right: float) -> bool:
    left_delta = abs(left) * _RANGE_TOLERANCE
    right_delta = abs(right) * _RANGE_TOLERANCE
    left_range = (left - left_delta, left + left_delta)
    right_range = (right - right_delta, right + right_delta)
    return left_range[0] <= right_range[1] and right_range[0] <= left_range[1]


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _field(claim: ClaimLike, field_name: str, *, default: Any = ...) -> Any:
    if isinstance(claim, Mapping):
        if default is ...:
            return claim[field_name]
        return claim.get(field_name, default)
    if default is ...:
        return getattr(claim, field_name)
    return getattr(claim, field_name, default)


def _integer_field(claim: ClaimLike, field_name: str) -> int:
    value = _field(claim, field_name)
    if isinstance(value, bool):
        raise ValueError(f"Claim {field_name} must be an integer")
    try:
        integer_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Claim {field_name} must be an integer") from error
    if integer_value < 1:
        raise ValueError(f"Claim {field_name} must be positive")
    return integer_value


__all__ = [
    "CanonicalGroup",
    "CanonicalizationResult",
    "ClaimPair",
    "IDENTITY_SCHEMA",
    "PostgresClaimIdentityStore",
    "canonicalize",
    "canonicalize_scope",
    "prefilter_pairs",
]
