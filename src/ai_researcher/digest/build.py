"""Assemble a temporal digest from a ChangeSet."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Connection, select

from ai_researcher.answer.citation import (
    CitationPaper,
    CitationResolutionError,
    render_citation,
)
from ai_researcher.db import connect
from ai_researcher.db.models import (
    claim_evidence,
    discourse_item,
    discourse_mention,
    paper,
    section,
)
from ai_researcher.db.models import tree_node as tree_node_table
from ai_researcher.monitor.changes import ChangeSet, detect_changes

DEFAULT_DIGEST_DIR = Path("docs/supersaiyan/runs")

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
DetectFn = Callable[..., ChangeSet]
EnrichFn = Callable[..., "Digest"]


@dataclass(frozen=True, slots=True)
class _CitationNode:
    node_id: int
    paper_id: int
    section_path: str
    page_start: int | None
    page_end: int | None


@dataclass(frozen=True, slots=True)
class CommunityMention:
    """A discourse mention enriched for digest rendering (link + counts only)."""

    url: str
    title: str | None
    score: int | None
    num_comments: int | None
    paper_id: int
    claim_id: int


@dataclass(frozen=True, slots=True)
class Digest:
    """Evidence and community changes for one ``since`` window."""

    since: date
    changes: ChangeSet
    paper_refs: Mapping[int, str]
    community: tuple[CommunityMention, ...]


def build_digest(
    since: datetime,
    *,
    connection_factory: ConnectionFactory | None = None,
    detect_fn: DetectFn | None = None,
    enrich_fn: EnrichFn | None = None,
) -> Digest:
    """Build a digest for everything that changed after ``since``."""

    detect = detect_changes if detect_fn is None else detect_fn
    changes = detect(since, connection_factory=connection_factory)
    since_date = since.date() if isinstance(since, datetime) else since
    if enrich_fn is not None:
        return enrich_fn(changes, since_date=since_date, connection_factory=connection_factory)
    return _enrich_digest(changes, since_date, connection_factory=connection_factory)


def write_digest(
    since: datetime,
    *,
    output_dir: Path | None = None,
    connection_factory: ConnectionFactory | None = None,
) -> tuple[str, Path]:
    """Render a digest to markdown, write it under ``output_dir``, return content + path."""

    digest = build_digest(since, connection_factory=connection_factory)
    from ai_researcher.digest.render import render_digest

    markdown = render_digest(digest)
    directory = DEFAULT_DIGEST_DIR if output_dir is None else output_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"digest-{digest.since.isoformat()}.md"
    path.write_text(markdown, encoding="utf-8")
    return markdown, path


def _enrich_digest(
    changes: ChangeSet,
    since_date: date,
    *,
    connection_factory: ConnectionFactory | None = None,
) -> Digest:
    open_connection = connect if connection_factory is None else connection_factory
    paper_ids = {item.paper_id for item in changes.new_papers}
    paper_ids.update(item.paper_id for item in changes.discourse_mentions)

    with open_connection() as connection:
        paper_refs = _paper_refs(connection, changes, paper_ids)
        community = _community_mentions(connection, changes)

    return Digest(
        since=since_date,
        changes=changes,
        paper_refs=paper_refs,
        community=community,
    )


def _paper_refs(
    connection: Connection,
    changes: ChangeSet,
    paper_ids: set[int],
) -> dict[int, str]:
    refs: dict[int, str] = {}

    evidence_ids = {item.claim_evidence_id for item in changes.new_evidence}
    evidence_ids.update(item.claim_evidence_id for item in changes.stance_flips)
    if evidence_ids:
        rows = connection.execute(
            select(
                claim_evidence.c.paper_id,
                tree_node_table.c.id.label("tree_node_id"),
                section.c.section_path,
                tree_node_table.c.page_start,
                tree_node_table.c.page_end,
            )
            .select_from(
                claim_evidence.join(
                    tree_node_table,
                    tree_node_table.c.id == claim_evidence.c.tree_node_id,
                ).join(section, section.c.id == tree_node_table.c.section_id)
            )
            .where(claim_evidence.c.id.in_(evidence_ids))
        ).all()
        papers = _load_papers(connection, {int(r.paper_id) for r in rows} | paper_ids)

        def lookup(paper_id: int) -> CitationPaper:
            return papers[paper_id]

        for row in rows:
            node = _CitationNode(
                node_id=int(row.tree_node_id),
                paper_id=int(row.paper_id),
                section_path=str(row.section_path),
                page_start=row.page_start,
                page_end=row.page_end,
            )
            try:
                citation = render_citation(node, paper_lookup=lookup)
                refs[int(row.paper_id)] = citation.rendered
            except (CitationResolutionError, KeyError):
                continue

    missing = paper_ids - set(refs)
    if missing:
        papers = _load_papers(connection, missing)
        for paper_id, record in papers.items():
            refs[paper_id] = _format_paper_ref(record)
    return refs


def _load_papers(connection: Connection, paper_ids: set[int]) -> dict[int, CitationPaper]:
    if not paper_ids:
        return {}
    rows = connection.execute(
        select(paper.c.id, paper.c.title, paper.c.doi, paper.c.arxiv_id).where(
            paper.c.id.in_(paper_ids)
        )
    ).all()
    return {
        int(row.id): CitationPaper(
            id=int(row.id),
            title=str(row.title),
            doi=row.doi,
            arxiv_id=row.arxiv_id,
        )
        for row in rows
    }


def _format_paper_ref(record: CitationPaper) -> str:
    if record.doi:
        return f"{record.title} — DOI: {record.doi}"
    if record.arxiv_id:
        return f"{record.title} — arXiv: {record.arxiv_id}"
    return f"{record.title} — paper #{record.id}"


def _community_mentions(
    connection: Connection,
    changes: ChangeSet,
) -> tuple[CommunityMention, ...]:
    if not changes.discourse_mentions:
        return ()
    mention_ids = [item.discourse_mention_id for item in changes.discourse_mentions]
    claim_by_mention = {
        item.discourse_mention_id: item.claim_id for item in changes.discourse_mentions
    }
    paper_by_mention = {
        item.discourse_mention_id: item.paper_id for item in changes.discourse_mentions
    }
    rows = connection.execute(
        select(
            discourse_mention.c.id,
            discourse_item.c.url,
            discourse_item.c.title,
            discourse_item.c.score,
            discourse_item.c.num_comments,
        )
        .select_from(
            discourse_mention.join(
                discourse_item,
                discourse_item.c.id == discourse_mention.c.discourse_item_id,
            )
        )
        .where(discourse_mention.c.id.in_(mention_ids))
        .order_by(discourse_mention.c.id)
    ).all()
    return tuple(
        CommunityMention(
            url=str(row.url),
            title=row.title,
            score=None if row.score is None else int(row.score),
            num_comments=None if row.num_comments is None else int(row.num_comments),
            paper_id=paper_by_mention[int(row.id)],
            claim_id=claim_by_mention[int(row.id)],
        )
        for row in rows
    )
