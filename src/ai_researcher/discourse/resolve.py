"""Shared paper-link resolution for discourse items (arXiv ID / DOI).

Adapters never reimplement identifier extraction — they inherit
``DiscourseLinkMixin.link_targets`` or call :func:`link_targets` directly.
Corpus matching is exact on ``paper.arxiv_id`` / ``paper.doi``; unmatched
identifiers are logged and produce no ``discourse_mention`` row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Connection, insert, select

from ai_researcher.db.models import discourse_item, discourse_mention, paper
from ai_researcher.discourse.base import DiscourseItem
from ai_researcher.logging import get_logger
from ai_researcher.sources.base import PaperRef

ResolvedBy = Literal["arxiv", "doi"]
IdentifierKind = Literal["arxiv", "doi"]

_logger = get_logger(__name__)

# Modern (YYMM.NNNNN) and legacy (archive/YYMMNNN) arXiv identifiers.
_ARXIV_MODERN = re.compile(
    r"(?i)(?:arxiv\.org/(?:abs|pdf)/|arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?"
)
_ARXIV_LEGACY = re.compile(
    r"(?i)(?:arxiv\.org/(?:abs|pdf)/|arxiv:)?"
    r"([a-z\-]+(?:\.[A-Za-z]{2})?/\d{7})(?:v\d+)?(?:\.pdf)?"
)
_DOI = re.compile(r"(?i)(?:https?://(?:dx\.)?doi\.org/|doi:)?(10\.\d{4,9}/[^\s\"<>]+)")


@dataclass(frozen=True, slots=True)
class Identifier:
    """A normalized paper identifier extracted from discourse text."""

    kind: IdentifierKind
    value: str


@dataclass(frozen=True, slots=True)
class DiscourseMentionRef:
    """A corpus match ready to persist as ``discourse_mention``."""

    paper_id: int
    resolved_by: ResolvedBy


def extract_identifiers(text: str) -> list[Identifier]:
    """Extract unique arXiv IDs and DOIs from free text (URL or body)."""

    if not text:
        return []

    found: list[Identifier] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: IdentifierKind, value: str) -> None:
        normalized = _normalize(kind, value)
        if normalized is None:
            return
        key = (kind, normalized)
        if key in seen:
            return
        seen.add(key)
        found.append(Identifier(kind=kind, value=normalized))

    for match in _ARXIV_MODERN.finditer(text):
        _add("arxiv", match.group(1))
    for match in _ARXIV_LEGACY.finditer(text):
        _add("arxiv", match.group(1))
    for match in _DOI.finditer(text):
        raw = match.group(1).rstrip(").,;]")
        _add("doi", raw)

    return found


def link_targets(item: DiscourseItem) -> list[PaperRef]:
    """Extract paper refs from an item's URL, title, and body text."""

    chunks = [item.url]
    if item.title:
        chunks.append(item.title)
    if item.body:
        chunks.append(item.body)
    identifiers = extract_identifiers("\n".join(chunks))
    refs: list[PaperRef] = []
    for identifier in identifiers:
        if identifier.kind == "arxiv":
            refs.append(PaperRef(source="arxiv", external_id=identifier.value))
        else:
            refs.append(
                PaperRef(
                    source="doi",
                    external_id=identifier.value,
                    doi=identifier.value,
                )
            )
    return refs


def resolve_against_corpus(
    item: DiscourseItem,
    *,
    connection: Connection,
) -> list[DiscourseMentionRef]:
    """Match extracted identifiers to local ``paper`` rows; log unmatched ones."""

    identifiers = extract_identifiers(
        "\n".join(part for part in (item.url, item.title, item.body) if part)
    )
    if not identifiers:
        return []

    rows = connection.execute(select(paper.c.id, paper.c.arxiv_id, paper.c.doi)).all()
    by_arxiv: dict[str, int] = {}
    by_doi: dict[str, int] = {}
    for row in rows:
        arxiv_key = _normalize("arxiv", row.arxiv_id) if row.arxiv_id else None
        doi_key = _normalize("doi", row.doi) if row.doi else None
        if arxiv_key is not None:
            by_arxiv[arxiv_key] = row.id
        if doi_key is not None:
            by_doi[doi_key] = row.id

    mentions: list[DiscourseMentionRef] = []
    seen_papers: set[int] = set()
    for identifier in identifiers:
        paper_id: int | None = None
        resolved_by: ResolvedBy
        if identifier.kind == "arxiv":
            paper_id = by_arxiv.get(identifier.value)
            resolved_by = "arxiv"
        else:
            paper_id = by_doi.get(identifier.value)
            resolved_by = "doi"

        if paper_id is None:
            _logger.info(
                "Unmatched discourse identifier kind=%s value=%s source=%s external_id=%s",
                identifier.kind,
                identifier.value,
                item.source,
                item.external_id,
            )
            continue
        if paper_id in seen_papers:
            continue
        seen_papers.add(paper_id)
        mentions.append(DiscourseMentionRef(paper_id=paper_id, resolved_by=resolved_by))
    return mentions


def store_item_with_mentions(
    connection: Connection,
    *,
    source_id: int,
    item: DiscourseItem,
) -> tuple[int, list[DiscourseMentionRef]]:
    """Persist a discourse item and any corpus-matched mentions.

    Items with no identifiers, or only unmatched identifiers, are still stored
    (topic-level signal) with zero ``discourse_mention`` rows.
    """

    item_id = connection.execute(
        insert(discourse_item)
        .values(
            source_id=source_id,
            external_id=item.external_id,
            url=item.url,
            title=item.title,
            author=item.author,
            posted_at=item.posted_at,
            score=item.score,
            num_comments=item.num_comments,
        )
        .returning(discourse_item.c.id)
    ).scalar_one()

    mentions = resolve_against_corpus(item, connection=connection)
    for mention in mentions:
        connection.execute(
            insert(discourse_mention).values(
                discourse_item_id=item_id,
                paper_id=mention.paper_id,
                resolved_by=mention.resolved_by,
            )
        )
    return item_id, mentions


def _normalize(kind: IdentifierKind, value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if kind == "arxiv":
        normalized = stripped.casefold().removeprefix("arxiv:")
        normalized = re.sub(r"v\d+$", "", normalized)
        return normalized or None
    normalized = stripped.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
            break
    return normalized.rstrip(").,;]") or None
