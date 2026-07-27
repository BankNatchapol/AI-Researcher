"""Structured, read-only MCP tools over the AI-Researcher core library."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from typing_extensions import TypedDict

from ai_researcher.corpus import status as corpus_status
from ai_researcher.db import connect
from ai_researcher.db.models import paper, section
from ai_researcher.scoping import store as scope_store


class ScopeRecord(TypedDict):
    """One persisted research scope."""

    name: str
    description: str
    include_terms: list[str]
    exclude_terms: list[str]
    categories: list[str]
    date_from: str | None
    date_to: str | None
    per_source_limit: int


class ListScopesResult(TypedDict):
    """Structured result for ``list_scopes``."""

    scopes: list[ScopeRecord]


class FailedPaperRecord(TypedDict):
    """One paper whose parsing failed."""

    paper_id: int
    title: str
    error: str


class ScopeStatusRecord(TypedDict):
    """Corpus counts for one scope."""

    scope_name: str
    paper_count: int
    parsed_count: int
    abstract_only_count: int
    failed_count: int
    section_count: int
    failed_papers: list[FailedPaperRecord]


class ScopeStatusResult(TypedDict):
    """Structured result for ``scope_status``."""

    scopes: list[ScopeStatusRecord]


class CitationRecord(TypedDict):
    """One answer citation anchored to a paper section."""

    number: int
    node_id: int
    paper_id: int
    paper_title: str
    section_path: str
    page_start: int | None
    page_end: int | None
    identifier_type: str
    identifier: str


class TraceRecord(TypedDict):
    """Concise traversal evidence for one question."""

    nodes_expanded: int
    selected_node_ids: list[int]
    stopped_reason: Literal[
        "sufficient_evidence",
        "budget_exhausted",
        "no_candidates",
    ]


class AskCorpusResult(TypedDict):
    """Structured grounded-answer result."""

    answer: str | None
    citations: list[CitationRecord]
    budget_limited: bool
    insufficient_evidence: bool
    message: str | None
    trace: TraceRecord


class SectionRecord(TypedDict):
    """One structurally parsed paper section."""

    section_id: int
    parent_id: int | None
    section_path: str
    title: str | None
    ordinal: int
    page_start: int | None
    page_end: int | None
    body_text: str


class PaperSectionsResult(TypedDict):
    """Structured result for ``get_paper_sections``."""

    paper_id: int
    paper_title: str | None
    sections: list[SectionRecord]


mcp = FastMCP(
    "AI-Researcher",
    instructions=(
        "Read-only access to research scopes, corpus status, grounded answers, "
        "and parsed paper sections."
    ),
)


def list_scopes_tool() -> ListScopesResult:
    """List saved research scopes and their reproducible definitions."""

    return {
        "scopes": [
            {
                "name": definition.name,
                "description": definition.description,
                "include_terms": list(definition.include_terms),
                "exclude_terms": list(definition.exclude_terms),
                "categories": list(definition.categories),
                "date_from": (
                    definition.date_from.isoformat() if definition.date_from is not None else None
                ),
                "date_to": (
                    definition.date_to.isoformat() if definition.date_to is not None else None
                ),
                "per_source_limit": definition.per_source_limit,
            }
            for definition in scope_store.list_scopes()
        ]
    }


def scope_status_tool(scope: str | None = None) -> ScopeStatusResult:
    """Return corpus counts for every scope or one named scope."""

    return {
        "scopes": [
            {
                "scope_name": item.scope_name,
                "paper_count": item.paper_count,
                "parsed_count": item.parsed_count,
                "abstract_only_count": item.abstract_only_count,
                "failed_count": item.failed_count,
                "section_count": item.section_count,
                "failed_papers": [
                    {
                        "paper_id": failed.paper_id,
                        "title": failed.title,
                        "error": failed.error,
                    }
                    for failed in item.failed_papers
                ],
            }
            for item in corpus_status.scope_status(scope)
        ]
    }


def ask_corpus_tool(
    question: str,
    scope: str,
    max_nodes: int | None = None,
) -> AskCorpusResult:
    """Answer a question from node-anchored evidence in one saved scope."""

    from ai_researcher import answer, retrieval

    traversal_result = retrieval.traverse(question, scope, max_nodes=max_nodes)
    grounded_answer = answer.synthesize(question, traversal_result)
    return {
        "answer": grounded_answer.answer_text,
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
            for number, citation in enumerate(grounded_answer.citations, start=1)
        ],
        "budget_limited": grounded_answer.budget_limited,
        "insufficient_evidence": grounded_answer.insufficient_evidence,
        "message": grounded_answer.message,
        "trace": {
            "nodes_expanded": traversal_result.trace.nodes_expanded,
            "selected_node_ids": list(traversal_result.trace.selected_node_ids),
            "stopped_reason": traversal_result.trace.stopped_reason,
        },
    }


def get_paper_sections_tool(paper_id: int) -> PaperSectionsResult:
    """Return every parsed section for one paper in structural order."""

    return _load_paper_sections(paper_id)


def _load_paper_sections(paper_id: int) -> PaperSectionsResult:
    with connect() as connection:
        paper_title = connection.execute(
            select(paper.c.title).where(paper.c.id == paper_id)
        ).scalar_one_or_none()
        rows = (
            connection.execute(
                select(
                    section.c.id,
                    section.c.parent_id,
                    section.c.section_path,
                    section.c.title,
                    section.c.ordinal,
                    section.c.page_start,
                    section.c.page_end,
                    section.c.body_text,
                )
                .where(section.c.paper_id == paper_id)
                .order_by(section.c.ordinal, section.c.id)
            )
            .mappings()
            .all()
        )
    return {
        "paper_id": paper_id,
        "paper_title": None if paper_title is None else str(paper_title),
        "sections": [
            {
                "section_id": int(row["id"]),
                "parent_id": None if row["parent_id"] is None else int(row["parent_id"]),
                "section_path": str(row["section_path"]),
                "title": None if row["title"] is None else str(row["title"]),
                "ordinal": int(row["ordinal"]),
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "body_text": str(row["body_text"]),
            }
            for row in rows
        ],
    }


mcp.tool(name="list_scopes")(list_scopes_tool)
mcp.tool(name="scope_status")(scope_status_tool)
mcp.tool(name="ask_corpus")(ask_corpus_tool)
mcp.tool(name="get_paper_sections")(get_paper_sections_tool)


def run() -> None:
    """Serve the tools over standard input/output."""

    mcp.run(transport="stdio")


__all__ = [
    "ask_corpus_tool",
    "get_paper_sections_tool",
    "list_scopes_tool",
    "mcp",
    "run",
    "scope_status_tool",
]
