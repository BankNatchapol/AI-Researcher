"""Link extracted claims to supporting, refuting, and mentioning tree nodes."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeAlias

from sqlalchemy import Connection, delete, insert, select, update

from ai_researcher.db import connect
from ai_researcher.db.models import claim as claim_table
from ai_researcher.db.models import claim_evidence as claim_evidence_table
from ai_researcher.db.models import paper_scope, section, tree_node
from ai_researcher.db.models import scope as scope_table
from ai_researcher.llm import gateway
from ai_researcher.logging import get_logger
from ai_researcher.retrieval import TraversalResult, traverse

Stance: TypeAlias = Literal["supports", "refutes", "mentions"]
ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
CompleteFn = Callable[..., str | dict]
TraverseFn = Callable[[str, str], TraversalResult]
ClaimLike = Mapping[str, Any] | Any

STANCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                    "stance": {
                        "type": "string",
                        "enum": ["supports", "refutes", "mentions"],
                    },
                    "rationale": {"type": "string"},
                    "is_direct": {"type": "boolean"},
                },
                "required": ["node_id", "stance", "rationale", "is_direct"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["classifications"],
    "additionalProperties": False,
}

logger = get_logger(__name__)


class EvidenceLinkingError(RuntimeError):
    """Raised when a claim cannot be linked because required context is invalid."""


class EvidenceStore(Protocol):
    """Persistence operations required by evidence linking."""

    def resolve_scope(self, claim: ClaimLike) -> str:
        """Return a saved scope containing the claim's origin paper."""

    def load_candidate_nodes(self, node_ids: list[int]) -> tuple[CandidateNode, ...]:
        """Load candidate node bodies in traversal order."""

    def save_links(
        self,
        claim_id: int,
        links: list[ClaimEvidence],
    ) -> list[ClaimEvidence]:
        """Reconcile valid evidence links for one claim."""

    def load_unlinked_claims(self, scope_name: str) -> tuple[ClaimLike, ...]:
        """Load claims in a scope that do not yet have evidence links."""


@dataclass(frozen=True, slots=True)
class CandidateNode:
    """A traversal-selected tree node with the text needed for quote validation."""

    node_id: int
    paper_id: int
    body_text: str


@dataclass(frozen=True, slots=True)
class ClaimEvidence:
    """One auditable relation between a claim and a passage-anchored node."""

    claim_id: int
    tree_node_id: int
    paper_id: int
    stance: Stance
    rationale_text: str
    is_direct: bool


@dataclass(frozen=True, slots=True)
class EvidenceLinkScopeResult:
    """Summary of evidence linking for all currently unlinked claims in a scope."""

    claims_linked: int
    evidence_links: int
    failed: int


class PostgresEvidenceStore:
    """Load and persist evidence links in the project's single PostgreSQL store."""

    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connect if connection_factory is None else connection_factory

    def resolve_scope(self, claim: ClaimLike) -> str:
        paper_id = _integer_claim_field(claim, "paper_id")
        with self._connection_factory() as connection:
            scope_name = connection.execute(
                select(scope_table.c.name)
                .join(paper_scope, paper_scope.c.scope_id == scope_table.c.id)
                .where(paper_scope.c.paper_id == paper_id)
                .order_by(scope_table.c.id)
                .limit(1)
            ).scalar_one_or_none()
        if scope_name is None:
            raise EvidenceLinkingError(f"Claim paper {paper_id} does not belong to a saved scope")
        return str(scope_name)

    def load_candidate_nodes(self, node_ids: list[int]) -> tuple[CandidateNode, ...]:
        if not node_ids:
            return ()
        with self._connection_factory() as connection:
            rows = (
                connection.execute(
                    select(
                        tree_node.c.id,
                        tree_node.c.paper_id,
                        section.c.body_text,
                    )
                    .join(section, section.c.id == tree_node.c.section_id)
                    .where(tree_node.c.id.in_(node_ids))
                )
                .mappings()
                .all()
            )
        by_id = {
            int(row["id"]): CandidateNode(
                node_id=int(row["id"]),
                paper_id=int(row["paper_id"]),
                body_text=str(row["body_text"] or ""),
            )
            for row in rows
        }
        return tuple(by_id[node_id] for node_id in node_ids if node_id in by_id)

    def save_links(
        self,
        claim_id: int,
        links: list[ClaimEvidence],
    ) -> list[ClaimEvidence]:
        with self._connection_factory() as connection:
            existing_rows = (
                connection.execute(
                    select(
                        claim_evidence_table.c.id,
                        claim_evidence_table.c.tree_node_id,
                        claim_evidence_table.c.paper_id,
                        claim_evidence_table.c.stance,
                        claim_evidence_table.c.rationale_text,
                        claim_evidence_table.c.is_direct,
                    ).where(claim_evidence_table.c.claim_id == claim_id)
                )
                .mappings()
                .all()
            )
            existing_by_node = {int(row["tree_node_id"]): row for row in existing_rows}
            linked_node_ids = {link.tree_node_id for link in links}

            stale_ids = [
                int(row["id"])
                for row in existing_rows
                if int(row["tree_node_id"]) not in linked_node_ids
            ]
            if stale_ids:
                connection.execute(
                    delete(claim_evidence_table).where(claim_evidence_table.c.id.in_(stale_ids))
                )

            for link in links:
                values = {
                    "claim_id": link.claim_id,
                    "tree_node_id": link.tree_node_id,
                    "paper_id": link.paper_id,
                    "stance": link.stance,
                    "rationale_text": link.rationale_text,
                    "is_direct": link.is_direct,
                }
                existing = existing_by_node.get(link.tree_node_id)
                if existing is None:
                    connection.execute(insert(claim_evidence_table).values(**values))
                    continue
                if (
                    int(existing["paper_id"]) != link.paper_id
                    or str(existing["stance"]) != link.stance
                    or str(existing["rationale_text"]) != link.rationale_text
                    or bool(existing["is_direct"]) != link.is_direct
                ):
                    connection.execute(
                        update(claim_evidence_table)
                        .where(claim_evidence_table.c.id == int(existing["id"]))
                        .values(**values)
                    )
        return list(links)

    def load_unlinked_claims(self, scope_name: str) -> tuple[ClaimLike, ...]:
        linked_claim = (
            select(claim_evidence_table.c.id)
            .where(claim_evidence_table.c.claim_id == claim_table.c.id)
            .exists()
        )
        with self._connection_factory() as connection:
            rows = (
                connection.execute(
                    select(
                        claim_table.c.id,
                        claim_table.c.paper_id,
                        claim_table.c.normalized_text,
                    )
                    .join(paper_scope, paper_scope.c.paper_id == claim_table.c.paper_id)
                    .join(scope_table, scope_table.c.id == paper_scope.c.scope_id)
                    .where(
                        scope_table.c.name == scope_name,
                        claim_table.c.canonical_claim_id.is_(None),
                        ~linked_claim,
                    )
                    .order_by(claim_table.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(rows)


def link_evidence(
    claim: ClaimLike,
    *,
    scope: str | None = None,
    traverse_fn: TraverseFn | None = None,
    complete_fn: CompleteFn | None = None,
    store: EvidenceStore | None = None,
) -> list[ClaimEvidence]:
    """Find, classify, verify, and persist candidate evidence for one claim."""

    claim_id = _integer_claim_field(claim, "id")
    normalized_text = str(_claim_field(claim, "normalized_text")).strip()
    if not normalized_text:
        raise EvidenceLinkingError("Claim normalized_text must not be empty")

    evidence_store = PostgresEvidenceStore() if store is None else store
    scope_name = evidence_store.resolve_scope(claim) if scope is None else scope
    if not scope_name.strip():
        raise EvidenceLinkingError("Evidence scope must not be empty")

    run_traversal = traverse if traverse_fn is None else traverse_fn
    traversal = run_traversal(normalized_text, scope_name)
    node_ids = list(dict.fromkeys(node.node_id for node in traversal.ranked_nodes))
    candidates = evidence_store.load_candidate_nodes(node_ids)
    if not candidates:
        return []

    payload = {
        "claim": {
            "claim_id": claim_id,
            "normalized_text": normalized_text,
        },
        "instructions": (
            "Classify every candidate independently as supports, refutes, or mentions. "
            "Treat refuting evidence as equally important as supporting evidence. "
            "For rationale, copy one exact verbatim passage from that candidate's body_text; "
            "do not paraphrase or combine passages. Also set is_direct to true only when the "
            "candidate explicitly states the claim; set it to false when the claim can only be "
            "reached by an inferential step from what the passage says."
        ),
        "candidate_nodes": [
            {
                "node_id": candidate.node_id,
                "paper_id": candidate.paper_id,
                "body_text": candidate.body_text,
            }
            for candidate in candidates
        ],
    }
    call_model = gateway.complete if complete_fn is None else complete_fn
    response = call_model(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        job="stance",
        schema=STANCE_SCHEMA,
    )
    links = _validated_links(
        response,
        claim_id=claim_id,
        candidates=candidates,
    )
    return evidence_store.save_links(claim_id, links)


def link_scope_evidence(
    scope_name: str,
    *,
    store: EvidenceStore | None = None,
) -> EvidenceLinkScopeResult:
    """Link every currently unlinked claim in a scope, continuing past failures."""

    evidence_store = PostgresEvidenceStore() if store is None else store
    claims = evidence_store.load_unlinked_claims(scope_name)
    claims_linked = 0
    evidence_links = 0
    failed = 0
    for claim in claims:
        try:
            links = link_evidence(
                claim,
                scope=scope_name,
                store=evidence_store,
            )
        except Exception:  # noqa: BLE001 — one claim must not abort the scope
            failed += 1
            logger.exception(
                "Evidence linking failed for claim %s",
                _claim_field(claim, "id"),
            )
            continue
        claims_linked += 1
        evidence_links += len(links)
    return EvidenceLinkScopeResult(
        claims_linked=claims_linked,
        evidence_links=evidence_links,
        failed=failed,
    )


def _validated_links(
    response: str | dict,
    *,
    claim_id: int,
    candidates: tuple[CandidateNode, ...],
) -> list[ClaimEvidence]:
    if not isinstance(response, dict):
        raise EvidenceLinkingError("Stance model returned an invalid object")
    classifications = response.get("classifications")
    if not isinstance(classifications, list):
        raise EvidenceLinkingError("Stance model omitted classifications")

    candidates_by_id = {candidate.node_id: candidate for candidate in candidates}
    seen_node_ids: set[int] = set()
    links: list[ClaimEvidence] = []
    for classification in classifications:
        if not isinstance(classification, dict):
            raise EvidenceLinkingError("Stance model returned an invalid classification")
        node_id = classification.get("node_id")
        stance = classification.get("stance")
        rationale = classification.get("rationale")
        is_direct = classification.get("is_direct")
        if (
            isinstance(node_id, bool)
            or not isinstance(node_id, int)
            or node_id in seen_node_ids
            or node_id not in candidates_by_id
            or stance not in {"supports", "refutes", "mentions"}
            or not isinstance(rationale, str)
            or not isinstance(is_direct, bool)
        ):
            raise EvidenceLinkingError("Stance model returned an invalid classification")
        seen_node_ids.add(node_id)
        candidate = candidates_by_id[node_id]
        verbatim_rationale = _verbatim_span(candidate.body_text, rationale)
        if verbatim_rationale is None:
            logger.warning(
                "Rejected non-verbatim evidence rationale for claim %s node %s",
                claim_id,
                node_id,
            )
            continue
        links.append(
            ClaimEvidence(
                claim_id=claim_id,
                tree_node_id=node_id,
                paper_id=candidate.paper_id,
                stance=stance,
                rationale_text=verbatim_rationale,
                is_direct=is_direct,
            )
        )
    if seen_node_ids != set(candidates_by_id):
        raise EvidenceLinkingError("Stance model must classify every candidate node exactly once")
    return links


def _verbatim_span(body_text: str, rationale: str) -> str | None:
    """Return the exact source span when rationale matches after whitespace normalization."""

    words = rationale.split()
    if not words:
        return None
    whitespace_flexible_pattern = r"\s+".join(re.escape(word) for word in words)
    match = re.search(whitespace_flexible_pattern, body_text)
    return None if match is None else match.group(0)


def _claim_field(claim: ClaimLike, field_name: str) -> Any:
    if isinstance(claim, Mapping):
        try:
            return claim[field_name]
        except KeyError as error:
            raise EvidenceLinkingError(f"Claim is missing {field_name}") from error
    try:
        return getattr(claim, field_name)
    except AttributeError as error:
        raise EvidenceLinkingError(f"Claim is missing {field_name}") from error


def _integer_claim_field(claim: ClaimLike, field_name: str) -> int:
    value = _claim_field(claim, field_name)
    if isinstance(value, bool):
        raise EvidenceLinkingError(f"Claim {field_name} must be an integer")
    try:
        integer_value = int(value)
    except (TypeError, ValueError) as error:
        raise EvidenceLinkingError(f"Claim {field_name} must be an integer") from error
    if integer_value < 1:
        raise EvidenceLinkingError(f"Claim {field_name} must be positive")
    return integer_value


__all__ = [
    "CandidateNode",
    "ClaimEvidence",
    "EvidenceLinkScopeResult",
    "EvidenceLinkingError",
    "PostgresEvidenceStore",
    "link_evidence",
    "link_scope_evidence",
]
