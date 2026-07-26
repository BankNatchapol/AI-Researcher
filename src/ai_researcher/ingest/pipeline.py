"""Orchestrate discover → acquire → parse → persist for one scope."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ai_researcher.db import connect
from ai_researcher.db.models import (
    ingest_job,
    paper,
    paper_author,
    paper_scope,
    paper_source,
    section,
)
from ai_researcher.db.models import scope as scope_table
from ai_researcher.db.models import source as source_table
from ai_researcher.ingest.acquire import AcquisitionPaper, AcquisitionResult, acquire_pdf
from ai_researcher.ingest.dedup import MergedPaper
from ai_researcher.ingest.discover import discover_candidates
from ai_researcher.ingest.parse import ParsePaper, ParseResult, parse_pdf
from ai_researcher.ingest.tei import SectionRecord
from ai_researcher.logging import get_logger
from ai_researcher.sources.base import PaperRef

CORPUS_CEILING = 1000
TERMINAL_PARSE_STATUSES = frozenset({"parsed", "abstract_only"})
logger = get_logger(__name__)

ConnectionFactory = Callable[[], AbstractContextManager[Connection]]
DiscoverFn = Callable[..., list[MergedPaper]]
AcquireFn = Callable[..., AcquisitionResult]
ParseFn = Callable[..., ParseResult]


class CorpusCeilingExceededError(RuntimeError):
    """Raised when discovery resolves more papers than the corpus ceiling allows."""

    def __init__(self, resolved_count: int, ceiling: int = CORPUS_CEILING) -> None:
        self.resolved_count = resolved_count
        self.ceiling = ceiling
        super().__init__(
            f"Scope resolved to {resolved_count} papers, which exceeds the {ceiling}-paper ceiling"
        )


class UnknownScopeError(LookupError):
    """Raised when ingest is asked for a scope name that is not persisted."""


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Summary of one ingest job after it reaches a terminal state."""

    job_id: int
    state: str
    papers_found: int
    papers_parsed: int
    papers_newly_parsed: int


def run_ingest(
    scope_name: str,
    *,
    connection_factory: ConnectionFactory | None = None,
    discover_fn: DiscoverFn = discover_candidates,
    acquire_fn: AcquireFn = acquire_pdf,
    parse_fn: ParseFn = parse_pdf,
    storage_dir: str | Path | None = None,
) -> IngestResult:
    """Run the full ingest pipeline for ``scope_name`` and return job totals."""

    open_connection = connect if connection_factory is None else connection_factory

    with open_connection() as connection:
        scope_row = (
            connection.execute(select(scope_table).where(scope_table.c.name == scope_name))
            .mappings()
            .one_or_none()
        )
        if scope_row is None:
            raise UnknownScopeError(f"Unknown scope: {scope_name}")
        scope_id = int(scope_row["id"])
        job_id = int(
            connection.execute(
                insert(ingest_job)
                .values(scope_id=scope_id, state="running", papers_found=0, papers_parsed=0)
                .returning(ingest_job.c.id)
            ).scalar_one()
        )

    candidates = discover_fn(_scope_definition_from_row(scope_row))
    papers_found = len(candidates)

    if papers_found > CORPUS_CEILING:
        error = CorpusCeilingExceededError(papers_found, CORPUS_CEILING)
        _finish_job(
            open_connection,
            job_id,
            state="failed",
            papers_found=papers_found,
            papers_parsed=0,
            error=str(error),
        )
        raise error

    papers_newly_parsed = 0
    total = papers_found
    for index, candidate in enumerate(candidates, start=1):
        logger.info(
            "Processing paper %s/%s: %s",
            index,
            total,
            candidate.title,
        )
        with open_connection() as connection:
            paper_id, parse_status, pdf_path, oa_status = _upsert_paper(
                connection,
                candidate,
                scope_id=scope_id,
            )
            if parse_status in TERMINAL_PARSE_STATUSES:
                continue

            acquisition_paper = AcquisitionPaper(
                id=paper_id,
                ref=_paper_ref_for(candidate),
                pdf_path=pdf_path,
                oa_status=oa_status,
                parse_status=parse_status,
            )

        acquisition = acquire_fn(acquisition_paper, storage_dir=storage_dir)
        with open_connection() as connection:
            connection.execute(
                update(paper)
                .where(paper.c.id == paper_id)
                .values(
                    pdf_path=acquisition_paper.pdf_path,
                    oa_status=acquisition_paper.oa_status,
                    parse_status=acquisition_paper.parse_status,
                    parse_error=acquisition.error
                    if acquisition_paper.parse_status == "failed"
                    else None,
                )
            )

        if acquisition_paper.parse_status in TERMINAL_PARSE_STATUSES:
            continue
        if acquisition.status == "failed" or acquisition_paper.parse_status == "failed":
            continue

        parse_paper = ParsePaper(
            id=paper_id,
            pdf_path=acquisition_paper.pdf_path,
            parse_status=acquisition_paper.parse_status,
        )
        parse_result = parse_fn(parse_paper)
        with open_connection() as connection:
            connection.execute(
                update(paper)
                .where(paper.c.id == paper_id)
                .values(
                    tei_xml=parse_paper.tei_xml,
                    parse_status=parse_paper.parse_status,
                    parse_error=parse_result.error
                    if parse_paper.parse_status == "failed"
                    else None,
                )
            )
            if parse_result.status == "parsed":
                _persist_sections(connection, paper_id, parse_result.sections)
                papers_newly_parsed += 1

    _finish_job(
        open_connection,
        job_id,
        state="completed",
        papers_found=papers_found,
        papers_parsed=papers_newly_parsed,
        error=None,
    )
    return IngestResult(
        job_id=job_id,
        state="completed",
        papers_found=papers_found,
        papers_parsed=papers_newly_parsed,
        papers_newly_parsed=papers_newly_parsed,
    )


def _scope_definition_from_row(row: Any):
    from ai_researcher.scoping import ScopeDefinition

    return ScopeDefinition(
        name=row["name"],
        description=row["description"],
        include_terms=tuple(row["include_terms"]),
        exclude_terms=tuple(row["exclude_terms"]),
        categories=tuple(row["categories"]),
        date_from=row["date_from"],
        date_to=row["date_to"],
        per_source_limit=row["per_source_limit"],
    )


def _paper_ref_for(candidate: MergedPaper) -> PaperRef:
    primary = candidate.paper_sources[0]
    return PaperRef(
        source=primary.source,
        external_id=primary.external_id,
        title=candidate.title,
        doi=candidate.doi,
        pdf_url=candidate.pdf_url,
    )


def _upsert_paper(
    connection: Connection,
    candidate: MergedPaper,
    *,
    scope_id: int,
) -> tuple[int, str, str | None, str | None]:
    existing = _find_existing_paper(connection, candidate)
    if existing is None:
        paper_id = int(
            connection.execute(
                insert(paper)
                .values(
                    doi=candidate.doi,
                    arxiv_id=candidate.arxiv_id,
                    openalex_id=candidate.openalex_id,
                    s2_id=candidate.s2_id,
                    title=candidate.title,
                    abstract=candidate.abstract,
                    published_at=candidate.published_at,
                    venue=candidate.venue,
                    is_preprint=candidate.is_preprint,
                    parse_status="pending",
                )
                .returning(paper.c.id)
            ).scalar_one()
        )
        for position, author in enumerate(candidate.authors):
            connection.execute(
                insert(paper_author).values(
                    paper_id=paper_id,
                    position=position,
                    full_name=author,
                )
            )
        parse_status = "pending"
        pdf_path = None
        oa_status = None
    else:
        paper_id = int(existing["id"])
        parse_status = str(existing["parse_status"])
        pdf_path = existing["pdf_path"]
        oa_status = existing["oa_status"]

    connection.execute(
        pg_insert(paper_scope)
        .values(paper_id=paper_id, scope_id=scope_id)
        .on_conflict_do_nothing(index_elements=["paper_id", "scope_id"])
    )

    for provenance in candidate.paper_sources:
        source_id = _ensure_source(connection, provenance.source)
        existing_provenance = connection.execute(
            select(paper_source.c.id).where(
                paper_source.c.paper_id == paper_id,
                paper_source.c.source_id == source_id,
                paper_source.c.external_id == provenance.external_id,
            )
        ).scalar_one_or_none()
        if existing_provenance is None:
            connection.execute(
                insert(paper_source).values(
                    paper_id=paper_id,
                    source_id=source_id,
                    external_id=provenance.external_id,
                )
            )

    return paper_id, parse_status, pdf_path, oa_status


def _find_existing_paper(connection: Connection, candidate: MergedPaper) -> Any | None:
    if candidate.doi:
        row = (
            connection.execute(select(paper).where(paper.c.doi == candidate.doi))
            .mappings()
            .one_or_none()
        )
        if row is not None:
            return row
    if candidate.arxiv_id:
        row = (
            connection.execute(select(paper).where(paper.c.arxiv_id == candidate.arxiv_id))
            .mappings()
            .one_or_none()
        )
        if row is not None:
            return row
    return None


def _ensure_source(connection: Connection, name: str) -> int:
    existing = connection.execute(
        select(source_table.c.id).where(source_table.c.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    return int(
        connection.execute(
            insert(source_table)
            .values(name=name, kind="evidence", enabled=True)
            .returning(source_table.c.id)
        ).scalar_one()
    )


def _persist_sections(
    connection: Connection,
    paper_id: int,
    sections: list[SectionRecord],
) -> None:
    connection.execute(section.delete().where(section.c.paper_id == paper_id))
    local_to_db: dict[int, int] = {}
    for record in sections:
        parent_db_id = None if record.parent_id is None else local_to_db[record.parent_id]
        db_id = int(
            connection.execute(
                insert(section)
                .values(
                    paper_id=paper_id,
                    parent_id=parent_db_id,
                    section_path=record.section_path,
                    title=record.title,
                    ordinal=record.ordinal,
                    page_start=record.page_start,
                    page_end=record.page_end,
                    char_start=record.char_start,
                    char_end=record.char_end,
                    body_text=record.body_text,
                )
                .returning(section.c.id)
            ).scalar_one()
        )
        local_to_db[record.id] = db_id


def _finish_job(
    open_connection: ConnectionFactory,
    job_id: int,
    *,
    state: str,
    papers_found: int,
    papers_parsed: int,
    error: str | None,
) -> None:
    with open_connection() as connection:
        connection.execute(
            update(ingest_job)
            .where(ingest_job.c.id == job_id)
            .values(
                state=state,
                papers_found=papers_found,
                papers_parsed=papers_parsed,
                finished_at=datetime.now(UTC),
                error=error,
            )
        )


__all__ = [
    "CORPUS_CEILING",
    "CorpusCeilingExceededError",
    "IngestResult",
    "UnknownScopeError",
    "run_ingest",
]
