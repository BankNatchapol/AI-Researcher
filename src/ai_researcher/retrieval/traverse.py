"""Budgeted LLM reasoning over persisted paper-section trees."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from sqlalchemy import Connection, insert, select

from ai_researcher.config import get_settings
from ai_researcher.db import connect
from ai_researcher.db.models import retrieval_trace, tree_node
from ai_researcher.db.models import scope as scope_table
from ai_researcher.llm import gateway
from ai_researcher.retrieval.budget import ExpansionBudget
from ai_researcher.retrieval.shortlist import shortlist

SHORTLIST_LIMIT = 20
StopReason: TypeAlias = Literal[
    "sufficient_evidence",
    "budget_exhausted",
    "no_candidates",
]
ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
CompleteFn = Callable[..., str | dict]
ShortlistFn = Callable[[str, str, int], list[int]]

TRAVERSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "judgements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                    "relevance": {"type": "integer", "minimum": 0, "maximum": 100},
                    "selected": {"type": "boolean"},
                    "expand": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["node_id", "relevance", "selected", "expand", "reason"],
                "additionalProperties": False,
            },
        },
        "sufficient_evidence": {"type": "boolean"},
    },
    "required": ["judgements", "sufficient_evidence"],
    "additionalProperties": False,
}


class TraversalResponseError(RuntimeError):
    """Raised when the traversal model returns an unusable judgement."""


class UnknownTraversalScopeError(LookupError):
    """Raised when traversal is requested for a scope absent from the store."""


@dataclass(frozen=True, slots=True)
class TraversalNode:
    """One persisted tree node available to the traversal engine."""

    id: int
    paper_id: int
    parent_id: int | None
    section_path: str
    title: str | None
    summary: str
    page_start: int | None
    page_end: int | None


@dataclass(frozen=True, slots=True)
class ExpandedNode:
    """A human-readable record of one node opened by the model."""

    node_id: int
    paper_id: int
    section_path: str
    page_start: int | None
    page_end: int | None
    relevance: int
    selected: bool
    expand_children: bool
    reason: str


@dataclass(frozen=True, slots=True)
class RankedNode:
    """A selected evidence node ranked by the model's relevance judgement."""

    node_id: int
    paper_id: int
    section_path: str
    title: str | None
    summary: str
    page_start: int | None
    page_end: int | None
    relevance: int
    reason: str


@dataclass(frozen=True, slots=True)
class TraversalTrace:
    """Every expansion in order plus the traversal stopping decision."""

    expanded_nodes: tuple[ExpandedNode, ...]
    selected_node_ids: tuple[int, ...]
    stopped_reason: StopReason

    @property
    def nodes_expanded(self) -> int:
        """Return the number of nodes opened during traversal."""

        return len(self.expanded_nodes)


@dataclass(frozen=True, slots=True)
class TraversalResult:
    """Ranked evidence nodes and the full trace that produced them."""

    ranked_nodes: tuple[RankedNode, ...]
    trace: TraversalTrace

    @property
    def nodes(self) -> tuple[RankedNode, ...]:
        """Provide a concise alias for callers consuming selected nodes."""

        return self.ranked_nodes


class TraversalStore(Protocol):
    """Persistence operations needed by traversal."""

    def load_scope_tree(
        self,
        scope: str,
        paper_ids: list[int],
    ) -> tuple[int, tuple[TraversalNode, ...]]:
        """Resolve a scope and load candidate paper trees."""

    def write_trace(
        self,
        *,
        question: str,
        scope_id: int,
        expanded_node_ids: list[int],
        selected_node_ids: list[int],
        nodes_expanded: int,
        stopped_reason: StopReason,
    ) -> None:
        """Write exactly one trace for a completed traversal."""


class PostgresTraversalStore:
    """Load trees and persist traces in the single PostgreSQL store."""

    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connect if connection_factory is None else connection_factory

    def load_scope_tree(
        self,
        scope: str,
        paper_ids: list[int],
    ) -> tuple[int, tuple[TraversalNode, ...]]:
        with self._connection_factory() as connection:
            scope_id = connection.execute(
                select(scope_table.c.id).where(scope_table.c.name == scope)
            ).scalar_one_or_none()
            if scope_id is None:
                raise UnknownTraversalScopeError(f"Unknown scope: {scope}")
            if not paper_ids:
                return int(scope_id), ()
            rows = (
                connection.execute(
                    select(
                        tree_node.c.id,
                        tree_node.c.paper_id,
                        tree_node.c.parent_id,
                        tree_node.c.node_path,
                        tree_node.c.title,
                        tree_node.c.summary,
                        tree_node.c.page_start,
                        tree_node.c.page_end,
                        tree_node.c.depth,
                    ).where(tree_node.c.paper_id.in_(paper_ids))
                )
                .mappings()
                .all()
            )

        paper_order = {paper_id: index for index, paper_id in enumerate(paper_ids)}
        rows.sort(
            key=lambda row: (
                paper_order[int(row["paper_id"])],
                int(row["depth"]),
                int(row["id"]),
            )
        )
        return int(scope_id), tuple(
            TraversalNode(
                id=int(row["id"]),
                paper_id=int(row["paper_id"]),
                parent_id=None if row["parent_id"] is None else int(row["parent_id"]),
                section_path=str(row["node_path"]),
                title=row["title"],
                summary=str(row["summary"]),
                page_start=row["page_start"],
                page_end=row["page_end"],
            )
            for row in rows
        )

    def write_trace(
        self,
        *,
        question: str,
        scope_id: int,
        expanded_node_ids: list[int],
        selected_node_ids: list[int],
        nodes_expanded: int,
        stopped_reason: StopReason,
    ) -> None:
        with self._connection_factory() as connection:
            connection.execute(
                insert(retrieval_trace).values(
                    question=question,
                    scope_id=scope_id,
                    expanded_node_ids=expanded_node_ids,
                    selected_node_ids=selected_node_ids,
                    nodes_expanded=nodes_expanded,
                    stopped_reason=stopped_reason,
                )
            )


@dataclass(frozen=True, slots=True)
class _Judgement:
    relevance: int
    selected: bool
    expand: bool
    reason: str


def traverse(
    question: str,
    scope: str,
    max_nodes: int | None = None,
    *,
    shortlist_fn: ShortlistFn | None = None,
    complete_fn: CompleteFn | None = None,
    store: TraversalStore | None = None,
) -> TraversalResult:
    """Walk shortlisted paper trees under one global node-expansion budget."""

    if not question.strip():
        raise ValueError("question must not be empty")
    if not scope.strip():
        raise ValueError("scope must not be empty")

    select_papers = shortlist if shortlist_fn is None else shortlist_fn
    candidate_paper_ids = select_papers(scope, question, SHORTLIST_LIMIT)
    traversal_store = PostgresTraversalStore() if store is None else store
    scope_id, nodes = traversal_store.load_scope_tree(scope, candidate_paper_ids)
    if not candidate_paper_ids or not nodes:
        return _finish(
            store=traversal_store,
            question=question,
            scope_id=scope_id,
            ranked_nodes=(),
            expanded_nodes=(),
            stopped_reason="no_candidates",
        )

    configured_limit = get_settings().traversal_max_nodes if max_nodes is None else max_nodes
    budget = ExpansionBudget(configured_limit)
    call_model = gateway.complete if complete_fn is None else complete_fn
    nodes_by_id = {node.id: node for node in nodes}
    if len(nodes_by_id) != len(nodes):
        raise ValueError("Tree node IDs must be unique")

    children: dict[int, list[TraversalNode]] = defaultdict(list)
    roots: list[TraversalNode] = []
    for node in nodes:
        if node.parent_id is None or node.parent_id not in nodes_by_id:
            roots.append(node)
        else:
            children[node.parent_id].append(node)

    frontier = list(roots)
    queued_ids = {node.id for node in frontier}
    expanded_nodes: list[ExpandedNode] = []
    selected: dict[int, tuple[TraversalNode, _Judgement]] = {}
    sufficient_evidence = False

    while frontier and not budget.exhausted:
        batch = frontier[: budget.remaining]
        del frontier[: len(batch)]
        budget.consume(len(batch))
        payload = _traversal_payload(
            question=question,
            scope=scope,
            budget=budget,
            nodes=batch,
        )
        response = call_model(
            [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            job="traversal",
            schema=TRAVERSAL_SCHEMA,
        )
        judgements, sufficient_evidence = _validated_judgements(response, batch)

        for node in batch:
            judgement = judgements[node.id]
            expanded_nodes.append(
                ExpandedNode(
                    node_id=node.id,
                    paper_id=node.paper_id,
                    section_path=node.section_path,
                    page_start=node.page_start,
                    page_end=node.page_end,
                    relevance=judgement.relevance,
                    selected=judgement.selected,
                    expand_children=judgement.expand,
                    reason=judgement.reason,
                )
            )
            if judgement.selected:
                selected[node.id] = (node, judgement)

        if sufficient_evidence:
            break

        for node in batch:
            if not judgements[node.id].expand:
                continue
            for child in children[node.id]:
                if child.id not in queued_ids:
                    frontier.append(child)
                    queued_ids.add(child.id)

    expansion_order = {expanded.node_id: index for index, expanded in enumerate(expanded_nodes)}
    ranked_pairs = sorted(
        selected.values(),
        key=lambda pair: (
            -pair[1].relevance,
            expansion_order[pair[0].id],
        ),
    )
    ranked_nodes = tuple(
        RankedNode(
            node_id=node.id,
            paper_id=node.paper_id,
            section_path=node.section_path,
            title=node.title,
            summary=node.summary,
            page_start=node.page_start,
            page_end=node.page_end,
            relevance=judgement.relevance,
            reason=judgement.reason,
        )
        for node, judgement in ranked_pairs
    )
    if sufficient_evidence:
        stopped_reason: StopReason = "sufficient_evidence"
    elif budget.exhausted:
        stopped_reason = "budget_exhausted"
    else:
        stopped_reason = "no_candidates"
    return _finish(
        store=traversal_store,
        question=question,
        scope_id=scope_id,
        ranked_nodes=ranked_nodes,
        expanded_nodes=tuple(expanded_nodes),
        stopped_reason=stopped_reason,
    )


def _traversal_payload(
    *,
    question: str,
    scope: str,
    budget: ExpansionBudget,
    nodes: list[TraversalNode],
) -> dict:
    return {
        "question": question,
        "scope": scope,
        "budget": {
            "max_nodes": budget.limit,
            "nodes_expanded": budget.used,
            "nodes_remaining": budget.remaining,
        },
        "instructions": (
            "Judge every opened node for relevance to the question. Select nodes that "
            "directly contain useful evidence, request child expansion only when deeper "
            "sections are likely to improve the evidence, and report sufficient evidence "
            "only when the selected nodes can support an answer."
        ),
        "nodes": [
            {
                "node_id": node.id,
                "paper_id": node.paper_id,
                "section_path": node.section_path,
                "title": node.title,
                "summary": node.summary,
                "page_start": node.page_start,
                "page_end": node.page_end,
            }
            for node in nodes
        ],
    }


def _validated_judgements(
    response: str | dict,
    nodes: list[TraversalNode],
) -> tuple[dict[int, _Judgement], bool]:
    if not isinstance(response, dict):
        raise TraversalResponseError("Traversal model returned an invalid object")
    records = response.get("judgements")
    sufficient_evidence = response.get("sufficient_evidence")
    if not isinstance(records, list) or not isinstance(sufficient_evidence, bool):
        raise TraversalResponseError("Traversal model returned an invalid object")

    expected_ids = {node.id for node in nodes}
    judgements: dict[int, _Judgement] = {}
    for record in records:
        if not isinstance(record, dict):
            raise TraversalResponseError("Traversal model returned an invalid judgement")
        node_id = record.get("node_id")
        relevance = record.get("relevance")
        selected = record.get("selected")
        expand = record.get("expand")
        reason = record.get("reason")
        if (
            isinstance(node_id, bool)
            or not isinstance(node_id, int)
            or node_id not in expected_ids
            or node_id in judgements
            or isinstance(relevance, bool)
            or not isinstance(relevance, int)
            or not 0 <= relevance <= 100
            or not isinstance(selected, bool)
            or not isinstance(expand, bool)
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise TraversalResponseError("Traversal model returned an invalid judgement")
        judgements[node_id] = _Judgement(
            relevance=relevance,
            selected=selected,
            expand=expand,
            reason=reason.strip(),
        )
    if set(judgements) != expected_ids:
        raise TraversalResponseError("Traversal model must judge every opened node exactly once")
    return judgements, sufficient_evidence


def _finish(
    *,
    store: TraversalStore,
    question: str,
    scope_id: int,
    ranked_nodes: tuple[RankedNode, ...],
    expanded_nodes: tuple[ExpandedNode, ...],
    stopped_reason: StopReason,
) -> TraversalResult:
    selected_node_ids = [node.node_id for node in ranked_nodes]
    trace = TraversalTrace(
        expanded_nodes=expanded_nodes,
        selected_node_ids=tuple(selected_node_ids),
        stopped_reason=stopped_reason,
    )
    store.write_trace(
        question=question,
        scope_id=scope_id,
        expanded_node_ids=[node.node_id for node in expanded_nodes],
        selected_node_ids=selected_node_ids,
        nodes_expanded=trace.nodes_expanded,
        stopped_reason=stopped_reason,
    )
    return TraversalResult(ranked_nodes=ranked_nodes, trace=trace)


__all__ = [
    "ExpandedNode",
    "PostgresTraversalStore",
    "RankedNode",
    "TraversalResponseError",
    "TraversalResult",
    "TraversalTrace",
    "TraversalNode",
    "UnknownTraversalScopeError",
    "traverse",
]
