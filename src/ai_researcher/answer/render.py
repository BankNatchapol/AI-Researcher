"""Render grounded answers for terminal and machine-readable CLI output."""

from __future__ import annotations

import json
import re

from ai_researcher.answer.synthesize import Answer
from ai_researcher.retrieval import TraversalTrace
from ai_researcher.retrieval.traverse import ExpandedNode


def render_answer(
    answer: Answer,
    trace: TraversalTrace,
    *,
    verbose: bool = False,
) -> str:
    """Render an answer with numbered citations and an optional traversal trace."""

    sections: list[str] = []
    if answer.budget_limited:
        sections.append("BUDGET-LIMITED: the traversal node budget was exhausted.")

    if answer.insufficient_evidence:
        sections.append(answer.message or "Insufficient evidence.")
    else:
        if answer.answer_text:
            citation_numbers = {
                citation.node_id: number
                for number, citation in enumerate(answer.citations, start=1)
            }
            sections.append(_number_citation_markers(answer.answer_text, citation_numbers))
        if answer.citations:
            citation_lines = ["Citations"]
            citation_lines.extend(
                f"[{number}] {citation.rendered}"
                for number, citation in enumerate(answer.citations, start=1)
            )
            sections.append("\n".join(citation_lines))

    if verbose:
        sections.append(_render_trace(trace))
    return "\n\n".join(sections)


def render_answer_json(answer: Answer, trace: TraversalTrace) -> str:
    """Serialize an answer and concise trace summary as one JSON document."""

    payload = {
        "answer": answer.answer_text,
        "citations": [
            {
                "number": number,
                "node_id": citation.node_id,
                "paper_id": citation.paper_id,
                "paper_title": citation.paper_title,
                "section_path": citation.section_path,
                "page_start": citation.page_start,
                "page_end": citation.page_end,
                "identifier_type": citation.identifier_type,
                "identifier": citation.identifier,
            }
            for number, citation in enumerate(answer.citations, start=1)
        ],
        "budget_limited": answer.budget_limited,
        "insufficient_evidence": answer.insufficient_evidence,
        "message": answer.message,
        "trace": {
            "nodes_expanded": trace.nodes_expanded,
            "selected_node_ids": list(trace.selected_node_ids),
            "stopped_reason": trace.stopped_reason,
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _render_trace(trace: TraversalTrace) -> str:
    lines = ["Traversal trace"]
    if trace.expanded_nodes:
        lines.extend(_render_expanded_node(node) for node in trace.expanded_nodes)
    else:
        lines.append("(no nodes expanded)")
    lines.append(f"Stopping reason: {trace.stopped_reason}")
    lines.append(f"Nodes expanded: {trace.nodes_expanded}")
    return "\n".join(lines)


def _number_citation_markers(answer_text: str, citation_numbers: dict[int, int]) -> str:
    def replace_marker(match: re.Match[str]) -> str:
        node_ids = [int(value) for value in match.group("node_ids").split(", ")]
        if any(node_id not in citation_numbers for node_id in node_ids):
            return match.group(0)
        numbers = ", ".join(str(citation_numbers[node_id]) for node_id in node_ids)
        return f"[{numbers}]"

    return re.sub(
        r"\[nodes? (?P<node_ids>\d+(?:, \d+)*)\]",
        replace_marker,
        answer_text,
    )


def _render_expanded_node(node: ExpandedNode) -> str:
    selected = "selected" if node.selected else "not selected"
    expansion = "expand children" if node.expand_children else "do not expand"
    return (
        f"- node {node.node_id} | paper {node.paper_id} | {node.section_path} | "
        f"{_render_pages(node.page_start, node.page_end)} | relevance {node.relevance} | "
        f"{selected} | {expansion} | {node.reason}"
    )


def _render_pages(page_start: int | None, page_end: int | None) -> str:
    if page_start is None:
        return "pages unavailable"
    if page_end is None or page_end == page_start:
        return f"p. {page_start}"
    return f"pp. {page_start}–{page_end}"


__all__ = ["render_answer", "render_answer_json"]
