"""Synthesize answers whose every statement names its supporting tree nodes."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_researcher.answer.citation import Citation, render_citation
from ai_researcher.llm import gateway
from ai_researcher.retrieval import RankedNode, TraversalResult

CompleteFn = Callable[..., str | dict]
CitationFn = Callable[[RankedNode], Citation]

SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "statements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "node_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 1,
                    },
                },
                "required": ["text", "node_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["statements"],
    "additionalProperties": False,
}


@dataclass(slots=True)
class Answer:
    """A transient grounded response suitable for CLI and MCP rendering."""

    answer_text: str | None
    citations: list[Citation]
    budget_limited: bool
    insufficient_evidence: bool
    message: str | None = None

    @property
    def text(self) -> str | None:
        """Alias the synthesized prose for concise callers."""

        return self.answer_text


class SynthesisResponseError(ValueError):
    """Raised when synthesized statements are missing valid passage attribution."""


@dataclass(frozen=True, slots=True)
class _Statement:
    text: str
    node_ids: tuple[int, ...]


def synthesize(
    question: str,
    traversal_result: TraversalResult,
    *,
    complete_fn: CompleteFn | None = None,
    citation_fn: CitationFn | None = None,
) -> Answer:
    """Create grounded prose from selected traversal nodes."""

    budget_limited = traversal_result.trace.stopped_reason == "budget_exhausted"
    if len(traversal_result.ranked_nodes) < 2:
        return _insufficient_answer(
            budget_limited=budget_limited,
            message=(
                "Insufficient evidence: at least two supporting nodes are required "
                "to synthesize an answer."
            ),
        )

    nodes_by_id = {node.node_id: node for node in traversal_result.ranked_nodes}
    call_model = gateway.complete if complete_fn is None else complete_fn
    statements: tuple[_Statement, ...] | None = None
    for attempt in range(2):
        response = call_model(
            [
                {
                    "role": "user",
                    "content": json.dumps(
                        _synthesis_payload(
                            question,
                            traversal_result.ranked_nodes,
                            regeneration=attempt > 0,
                        ),
                        ensure_ascii=False,
                    ),
                }
            ],
            job="answer_synthesis",
            schema=SYNTHESIS_SCHEMA,
        )
        try:
            statements = _validated_statements(response, set(nodes_by_id))
        except SynthesisResponseError:
            continue
        break
    if statements is None:
        return _insufficient_answer(
            budget_limited=budget_limited,
            message=(
                "Insufficient evidence: synthesis could not produce statements "
                "grounded only in the retrieved nodes."
            ),
        )

    cited_node_ids = list(
        dict.fromkeys(node_id for statement in statements for node_id in statement.node_ids)
    )
    cite_node = render_citation if citation_fn is None else citation_fn
    citations = [cite_node(nodes_by_id[node_id]) for node_id in cited_node_ids]
    return Answer(
        answer_text="\n".join(_render_statement(statement) for statement in statements),
        citations=citations,
        budget_limited=budget_limited,
        insufficient_evidence=False,
    )


def _synthesis_payload(
    question: str,
    nodes: tuple[RankedNode, ...],
    *,
    regeneration: bool,
) -> dict[str, Any]:
    return {
        "question": question,
        "allowed_node_ids": [node.node_id for node in nodes],
        "regeneration": regeneration,
        "instructions": (
            "Return the answer as atomic factual statements. Attribute every statement "
            "to one or more allowed node IDs. Never cite a node not supplied here."
            + (
                " The previous response failed attribution validation; regenerate it "
                "using only the allowed IDs."
                if regeneration
                else ""
            )
        ),
        "evidence": [
            {
                "node_id": node.node_id,
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


def _validated_statements(
    response: str | dict,
    allowed_node_ids: set[int],
) -> tuple[_Statement, ...]:
    if not isinstance(response, dict) or not isinstance(response.get("statements"), list):
        raise SynthesisResponseError("Synthesis model returned an invalid object")
    statements: list[_Statement] = []
    for record in response["statements"]:
        if not isinstance(record, dict):
            raise SynthesisResponseError("Synthesis model returned an invalid statement")
        text = record.get("text")
        node_ids = record.get("node_ids")
        if (
            not isinstance(text, str)
            or not text.strip()
            or not isinstance(node_ids, list)
            or not node_ids
            or any(
                isinstance(node_id, bool)
                or not isinstance(node_id, int)
                or node_id not in allowed_node_ids
                for node_id in node_ids
            )
        ):
            raise SynthesisResponseError("Every statement must cite only supplied node IDs")
        statements.append(_Statement(text=text.strip(), node_ids=tuple(dict.fromkeys(node_ids))))
    if not statements:
        raise SynthesisResponseError("Synthesis model returned no statements")
    return tuple(statements)


def _render_statement(statement: _Statement) -> str:
    label = "node" if len(statement.node_ids) == 1 else "nodes"
    identifiers = ", ".join(str(node_id) for node_id in statement.node_ids)
    return f"{statement.text} [{label} {identifiers}]"


def _insufficient_answer(*, budget_limited: bool, message: str) -> Answer:
    return Answer(
        answer_text=None,
        citations=[],
        budget_limited=budget_limited,
        insufficient_evidence=True,
        message=message,
    )


__all__ = [
    "Answer",
    "SYNTHESIS_SCHEMA",
    "SynthesisResponseError",
    "synthesize",
]
