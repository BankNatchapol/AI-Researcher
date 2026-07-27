"""Citation values for retrieved paper-section nodes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select

from ai_researcher.db import connect
from ai_researcher.db.models import paper


class CitationNode(Protocol):
    """Retrieved-node fields needed to produce a passage citation."""

    node_id: int
    paper_id: int
    section_path: str
    page_start: int | None
    page_end: int | None


@dataclass(frozen=True, slots=True)
class CitationPaper:
    """Paper metadata needed by citation rendering."""

    id: int
    title: str
    doi: str | None
    arxiv_id: str | None


PaperLookup = Callable[[int], CitationPaper]


class CitationResolutionError(LookupError):
    """Raised when a retrieved node cannot be rendered as an openable citation."""


@dataclass(frozen=True, slots=True)
class Citation:
    """A user-facing citation anchored to one retrieved tree node."""

    node_id: int
    paper_id: int
    paper_title: str
    section_path: str
    page_start: int | None
    page_end: int | None
    identifier_type: str
    identifier: str

    @property
    def rendered(self) -> str:
        """Render the complete human-readable citation."""

        if self.page_start is None:
            pages = "pages unavailable"
        elif self.page_end is None or self.page_end == self.page_start:
            pages = f"p. {self.page_start}"
        else:
            pages = f"pp. {self.page_start}–{self.page_end}"
        identifier_label = "DOI" if self.identifier_type == "doi" else "arXiv"
        return (
            f"{self.paper_title} — {self.section_path} — {pages} — "
            f"{identifier_label}: {self.identifier}"
        )

    def __str__(self) -> str:
        """Use the complete rendered citation in prose contexts."""

        return self.rendered


def render_citation(
    node: CitationNode,
    *,
    paper_lookup: PaperLookup | None = None,
) -> Citation:
    """Resolve a retrieved node to paper metadata and renderable citation fields."""

    lookup = _load_paper if paper_lookup is None else paper_lookup
    paper_record = lookup(node.paper_id)
    if paper_record.id != node.paper_id:
        raise CitationResolutionError(
            f"Citation paper {paper_record.id} does not match node paper {node.paper_id}"
        )
    if paper_record.doi:
        identifier_type = "doi"
        identifier = paper_record.doi
    elif paper_record.arxiv_id:
        identifier_type = "arxiv"
        identifier = paper_record.arxiv_id
    else:
        raise CitationResolutionError(f"Paper {paper_record.id} has neither a DOI nor an arXiv ID")
    return Citation(
        node_id=node.node_id,
        paper_id=node.paper_id,
        paper_title=paper_record.title,
        section_path=node.section_path,
        page_start=node.page_start,
        page_end=node.page_end,
        identifier_type=identifier_type,
        identifier=identifier,
    )


def _load_paper(paper_id: int) -> CitationPaper:
    with connect() as connection:
        row = (
            connection.execute(
                select(
                    paper.c.id,
                    paper.c.title,
                    paper.c.doi,
                    paper.c.arxiv_id,
                ).where(paper.c.id == paper_id)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        raise CitationResolutionError(f"Unknown paper for citation: {paper_id}")
    return CitationPaper(
        id=int(row["id"]),
        title=str(row["title"]),
        doi=row["doi"],
        arxiv_id=row["arxiv_id"],
    )


__all__ = [
    "Citation",
    "CitationPaper",
    "CitationResolutionError",
    "render_citation",
]
