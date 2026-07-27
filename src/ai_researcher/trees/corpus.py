"""Corpus-level PageIndex File System for paper shortlisting."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy import Connection, select

from ai_researcher.db import connect
from ai_researcher.db.models import paper, paper_scope, tree_node
from ai_researcher.db.models import scope as scope_table
from ai_researcher.llm import gateway
from ai_researcher.retrieval.shortlist import validate_shortlist_request

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
CompleteFn = Callable[..., str | dict]

SHORTLIST_SCHEMA = {
    "type": "object",
    "properties": {
        "paper_ids": {
            "type": "array",
            "items": {"type": "integer"},
        }
    },
    "required": ["paper_ids"],
    "additionalProperties": False,
}


class ShortlistResponseError(RuntimeError):
    """Raised when the shortlist model returns invalid paper identifiers."""


class PageIndexShortlist:
    """Reason over paper titles and root-node summaries in one batched model call."""

    def __init__(
        self,
        connection_factory: ConnectionFactory | None = None,
        complete_fn: CompleteFn | None = None,
    ) -> None:
        self._connection_factory = connect if connection_factory is None else connection_factory
        self._complete_fn = complete_fn

    def shortlist(self, scope: str, question: str, limit: int) -> list[int]:
        """Return model-selected paper IDs from the scope's corpus tree."""

        validate_shortlist_request(scope, question, limit)
        candidates = self._load_candidates(scope)
        if not candidates:
            return []

        payload = {
            "scope": scope,
            "question": question,
            "limit": limit,
            "instructions": (
                "Select the paper IDs most likely to contain evidence that answers the "
                "question. Return them in descending relevance order and select no more "
                f"than {limit}."
            ),
            "candidates": candidates,
        }
        call_model = gateway.complete if self._complete_fn is None else self._complete_fn
        response = call_model(
            [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            job="shortlist",
            schema=SHORTLIST_SCHEMA,
        )
        return _validated_paper_ids(response, candidates=candidates, limit=limit)

    def _load_candidates(self, scope: str) -> list[dict]:
        with self._connection_factory() as connection:
            rows = (
                connection.execute(
                    select(
                        paper.c.id,
                        paper.c.title,
                        tree_node.c.summary,
                    )
                    .join(paper_scope, paper_scope.c.paper_id == paper.c.id)
                    .join(scope_table, scope_table.c.id == paper_scope.c.scope_id)
                    .join(
                        tree_node,
                        (tree_node.c.paper_id == paper.c.id) & tree_node.c.parent_id.is_(None),
                    )
                    .where(scope_table.c.name == scope)
                    .order_by(paper.c.id, tree_node.c.id)
                )
                .mappings()
                .all()
            )

        candidates_by_id: dict[int, dict] = {}
        for row in rows:
            paper_id = int(row["id"])
            candidate = candidates_by_id.setdefault(
                paper_id,
                {
                    "paper_id": paper_id,
                    "title": str(row["title"]),
                    "root_summaries": [],
                },
            )
            candidate["root_summaries"].append(str(row["summary"]))
        return list(candidates_by_id.values())


def _validated_paper_ids(
    response: str | dict,
    *,
    candidates: list[dict],
    limit: int,
) -> list[int]:
    if not isinstance(response, dict) or not isinstance(response.get("paper_ids"), list):
        raise ShortlistResponseError("Shortlist model returned an invalid object")

    candidate_ids = {candidate["paper_id"] for candidate in candidates}
    selected: list[int] = []
    for paper_id in response["paper_ids"]:
        if (
            isinstance(paper_id, bool)
            or not isinstance(paper_id, int)
            or paper_id not in candidate_ids
            or paper_id in selected
        ):
            raise ShortlistResponseError("Shortlist model returned an invalid paper ID")
        selected.append(paper_id)
    return selected[:limit]


__all__ = ["PageIndexShortlist", "ShortlistResponseError"]
