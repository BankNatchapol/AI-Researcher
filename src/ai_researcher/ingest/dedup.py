"""Deterministic cross-source paper identity resolution."""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from typing import TypeVar

from ai_researcher.sources.base import PaperMetadata

_Value = TypeVar("_Value")


@dataclass(frozen=True, slots=True)
class PaperSource:
    """A future ``paper_source`` row without persistence-owned columns."""

    source: str
    external_id: str


@dataclass(frozen=True, slots=True)
class MergedPaper:
    """Canonical paper fields plus every source that surfaced the paper."""

    title: str
    abstract: str | None = None
    authors: tuple[str, ...] = ()
    published_at: date | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    s2_id: str | None = None
    is_preprint: bool = False
    pdf_url: str | None = None
    paper_sources: tuple[PaperSource, ...] = ()


def normalize_title(title: str) -> str:
    """Return a title key suitable for exact identity comparisons."""

    normalized = unicodedata.normalize("NFKC", title).casefold()
    return "".join(character for character in normalized if character.isalnum())


def resolve_identity(candidates: Iterable[PaperMetadata]) -> list[MergedPaper]:
    """Group source candidates that describe the same paper."""

    merged_papers: list[MergedPaper] = []
    for candidate in candidates:
        match = next(
            (paper for paper in merged_papers if _same_identity(paper, candidate)),
            None,
        )
        if match is None:
            merged_papers.append(_from_metadata(candidate))
            continue

        index = merged_papers.index(match)
        merged_papers[index] = _merge_metadata(match, candidate)
    return merged_papers


def _same_identity(paper: MergedPaper, candidate: PaperMetadata) -> bool:
    paper_doi = _normalize_doi(paper.doi)
    candidate_doi = _normalize_doi(candidate.doi)
    if paper_doi is not None and candidate_doi is not None:
        return paper_doi == candidate_doi

    paper_arxiv_id = _normalize_arxiv_id(paper.arxiv_id)
    candidate_arxiv_id = _normalize_arxiv_id(candidate.arxiv_id)
    if paper_arxiv_id is not None and candidate_arxiv_id is not None:
        return paper_arxiv_id == candidate_arxiv_id

    paper_fallback = _title_author_year_key(
        paper.title,
        paper.authors,
        paper.published_at,
    )
    candidate_fallback = _title_author_year_key(
        candidate.title,
        candidate.authors,
        candidate.published_at,
    )
    return paper_fallback is not None and paper_fallback == candidate_fallback


def _from_metadata(candidate: PaperMetadata) -> MergedPaper:
    return MergedPaper(
        title=candidate.title,
        abstract=candidate.abstract,
        authors=candidate.authors,
        published_at=candidate.published_at,
        venue=candidate.venue,
        doi=candidate.doi,
        arxiv_id=candidate.arxiv_id,
        openalex_id=candidate.openalex_id,
        s2_id=candidate.s2_id,
        is_preprint=candidate.is_preprint,
        pdf_url=candidate.pdf_url,
        paper_sources=(PaperSource(candidate.source, candidate.external_id),),
    )


def _merge_metadata(paper: MergedPaper, candidate: PaperMetadata) -> MergedPaper:
    sources = paper.paper_sources
    if all(source.source != candidate.source for source in sources):
        sources = (*sources, PaperSource(candidate.source, candidate.external_id))
    return replace(
        paper,
        title=_first_present(paper.title, candidate.title),
        abstract=_first_present(paper.abstract, candidate.abstract),
        authors=_first_present(paper.authors, candidate.authors),
        published_at=_first_present(paper.published_at, candidate.published_at),
        venue=_first_present(paper.venue, candidate.venue),
        doi=_first_present(paper.doi, candidate.doi),
        arxiv_id=_first_present(paper.arxiv_id, candidate.arxiv_id),
        openalex_id=_first_present(paper.openalex_id, candidate.openalex_id),
        s2_id=_first_present(paper.s2_id, candidate.s2_id),
        pdf_url=_first_present(paper.pdf_url, candidate.pdf_url),
        paper_sources=sources,
    )


def _first_present(current: _Value, later: _Value) -> _Value:
    if current is None or current == "" or current == ():
        return later
    return current


def _normalize_doi(doi: str | None) -> str | None:
    if doi is None:
        return None
    normalized = doi.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
            break
    return normalized or None


def _normalize_arxiv_id(arxiv_id: str | None) -> str | None:
    if arxiv_id is None:
        return None
    normalized = arxiv_id.strip().casefold().removeprefix("arxiv:")
    normalized = re.sub(r"v\d+$", "", normalized)
    return normalized or None


def _title_author_year_key(
    title: str,
    authors: tuple[str, ...],
    published_at: date | None,
) -> tuple[str, str, int] | None:
    if not authors or published_at is None:
        return None
    normalized_title = normalize_title(title)
    surname = authors[0].split(",", maxsplit=1)[0] if "," in authors[0] else authors[0].split()[-1]
    normalized_surname = normalize_title(surname)
    if not normalized_title or not normalized_surname:
        return None
    return normalized_title, normalized_surname, published_at.year
