"""Offline tests for discover → acquire → parse ingest orchestration."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.db.models import ingest_job, paper, paper_scope, section
from ai_researcher.db.models import scope as scope_table
from ai_researcher.db.models import source as source_table
from ai_researcher.ingest.acquire import AcquisitionPaper, AcquisitionResult
from ai_researcher.ingest.parse import ParsePaper, ParseResult
from ai_researcher.ingest.tei import SectionRecord
from ai_researcher.scoping import ScopeDefinition
from ai_researcher.sources.base import PaperMetadata, PaperRef

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_TEI = (FIXTURES / "sample-paper.tei.xml").read_text(encoding="utf-8")


def _pg8000_url(url: str):
    return make_url(url).set(drivername="postgresql+pg8000")


@pytest.fixture
def database_url() -> str:
    url = os.environ.get(
        "AI_RESEARCHER_TEST_DATABASE_URL",
        os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:issue3@127.0.0.1:55432/ai_researcher_test",
        ),
    )
    engine = create_engine(_pg8000_url(url), connect_args={"timeout": 2})
    try:
        with engine.connect():
            pass
    except SQLAlchemyError:
        pytest.skip("PostgreSQL test database is unavailable")
    finally:
        engine.dispose()
    return url


@pytest.fixture
def isolated_database(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    database_name = f"test_ingest_{uuid.uuid4().hex}"
    admin_engine = create_engine(_pg8000_url(database_url), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

    scoped_url = make_url(database_url).set(database=database_name)
    database_engine = create_engine(_pg8000_url(scoped_url))
    monkeypatch.setenv("DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")
    monkeypatch.setenv("ARXIV_MIN_INTERVAL_SECONDS", "0")

    from ai_researcher.db.migrate import migrate

    migrate()

    try:
        yield database_engine
    finally:
        database_engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')
        admin_engine.dispose()


def _connection_factory(engine: Engine):
    @contextmanager
    def open_connection():
        with engine.begin() as connection:
            yield connection

    return open_connection


def _scope(**overrides) -> ScopeDefinition:
    values = {
        "name": "surface-codes",
        "description": "Quantum error correction with surface codes",
        "include_terms": ("quantum error correction",),
        "exclude_terms": (),
        "categories": ("quant-ph",),
        "date_from": date(2020, 1, 1),
        "date_to": date(2025, 12, 31),
        "per_source_limit": 10,
    }
    values.update(overrides)
    return ScopeDefinition(**values)


@dataclass
class FixtureSource:
    """Evidence source serving in-memory discovery and metadata fixtures."""

    name: str
    refs: tuple[PaperRef, ...] = ()
    metadata_by_id: dict[str, PaperMetadata] = field(default_factory=dict)
    search_calls: list[int] = field(default_factory=list)
    pdf_urls: dict[str, str | None] = field(default_factory=dict)

    def search(self, scope, limit: int) -> list[PaperRef]:
        del scope
        self.search_calls.append(limit)
        return list(self.refs[:limit])

    def fetch_metadata(self, ref: PaperRef) -> PaperMetadata:
        return self.metadata_by_id[ref.external_id]

    def pdf_url(self, ref: PaperRef) -> str | None:
        if ref.external_id in self.pdf_urls:
            return self.pdf_urls[ref.external_id]
        return ref.pdf_url


def _insert_scope(engine: Engine, definition: ScopeDefinition) -> int:
    with engine.begin() as connection:
        row = connection.execute(
            insert(scope_table)
            .values(
                name=definition.name,
                description=definition.description,
                include_terms=list(definition.include_terms),
                exclude_terms=list(definition.exclude_terms),
                categories=list(definition.categories),
                date_from=definition.date_from,
                date_to=definition.date_to,
                per_source_limit=definition.per_source_limit,
            )
            .returning(scope_table.c.id)
        ).one()
    return int(row[0])


def test_discover_queries_every_source_and_merges_by_identity(monkeypatch) -> None:
    from ai_researcher.ingest import discover
    from ai_researcher.sources import registry

    shared_doi = "10.1000/shared"
    arxiv = FixtureSource(
        name="arxiv",
        refs=(PaperRef("arxiv", "2401.00001", title="Shared", doi=shared_doi),),
        metadata_by_id={
            "2401.00001": PaperMetadata(
                source="arxiv",
                external_id="2401.00001",
                title="Shared paper",
                doi=shared_doi,
                arxiv_id="2401.00001",
                authors=("Ada Lovelace",),
                published_at=date(2024, 1, 1),
            )
        },
    )
    openalex = FixtureSource(
        name="openalex",
        refs=(
            PaperRef("openalex", "W1", title="Shared", doi=shared_doi),
            PaperRef("openalex", "W2", title="Only OpenAlex"),
        ),
        metadata_by_id={
            "W1": PaperMetadata(
                source="openalex",
                external_id="W1",
                title="Shared paper",
                doi=shared_doi,
                openalex_id="W1",
                authors=("Ada Lovelace",),
                published_at=date(2024, 1, 1),
            ),
            "W2": PaperMetadata(
                source="openalex",
                external_id="W2",
                title="Only OpenAlex",
                openalex_id="W2",
                authors=("Grace Hopper",),
                published_at=date(2024, 2, 1),
            ),
        },
    )
    monkeypatch.setattr(registry, "_SOURCES", {"arxiv": arxiv, "openalex": openalex})

    merged = discover.discover_candidates(_scope(per_source_limit=5))

    assert arxiv.search_calls == [5]
    assert openalex.search_calls == [5]
    assert len(merged) == 2
    shared = next(paper for paper in merged if paper.doi == shared_doi)
    assert {row.source for row in shared.paper_sources} == {"arxiv", "openalex"}


class FailingSearchSource:
    """Evidence source whose search always raises, simulating a rate-limited API."""

    def __init__(self, name: str) -> None:
        self.name = name

    def search(self, scope, limit: int):
        del scope, limit
        raise RuntimeError(f"{self.name} search failed")

    def fetch_metadata(self, ref: PaperRef) -> PaperMetadata:
        raise AssertionError(f"discovery fetched metadata for {ref.external_id}")


def test_discover_skips_a_source_whose_search_fails_and_keeps_the_rest(monkeypatch) -> None:
    from ai_researcher.ingest import discover
    from ai_researcher.sources import registry

    broken = FailingSearchSource("semantic_scholar")
    arxiv = FixtureSource(
        name="arxiv",
        refs=(PaperRef("arxiv", "2401.00001", title="Still discovered"),),
        metadata_by_id={
            "2401.00001": PaperMetadata(
                source="arxiv",
                external_id="2401.00001",
                title="Still discovered",
                arxiv_id="2401.00001",
                authors=("Ada Lovelace",),
                published_at=date(2024, 1, 1),
            )
        },
    )
    monkeypatch.setattr(registry, "_SOURCES", {"semantic_scholar": broken, "arxiv": arxiv})

    merged = discover.discover_candidates(_scope(per_source_limit=5))

    assert len(merged) == 1
    assert merged[0].title == "Still discovered"


def test_discover_skips_a_paper_whose_metadata_fetch_fails_and_keeps_the_rest(
    monkeypatch,
) -> None:
    from ai_researcher.ingest import discover
    from ai_researcher.sources import registry

    arxiv = FixtureSource(
        name="arxiv",
        refs=(
            PaperRef("arxiv", "2401.00001", title="Fetch fails"),
            PaperRef("arxiv", "2401.00002", title="Fetch succeeds"),
        ),
        metadata_by_id={
            "2401.00002": PaperMetadata(
                source="arxiv",
                external_id="2401.00002",
                title="Fetch succeeds",
                arxiv_id="2401.00002",
                authors=("Grace Hopper",),
                published_at=date(2024, 2, 1),
            )
        },
    )
    monkeypatch.setattr(registry, "_SOURCES", {"arxiv": arxiv})

    merged = discover.discover_candidates(_scope(per_source_limit=5))

    assert len(merged) == 1
    assert merged[0].title == "Fetch succeeds"


def test_clean_ingest_writes_job_papers_and_sections(
    isolated_database: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.ingest import pipeline
    from ai_researcher.sources import registry

    definition = _scope()
    _insert_scope(isolated_database, definition)

    source = FixtureSource(
        name="arxiv",
        refs=(
            PaperRef(
                "arxiv",
                "2401.00001",
                title="Surface codes",
                pdf_url="https://example.test/a.pdf",
            ),
        ),
        metadata_by_id={
            "2401.00001": PaperMetadata(
                source="arxiv",
                external_id="2401.00001",
                title="Surface codes",
                abstract="An abstract.",
                authors=("Ada Lovelace",),
                published_at=date(2024, 1, 1),
                arxiv_id="2401.00001",
                is_preprint=True,
                pdf_url="https://example.test/a.pdf",
            )
        },
        pdf_urls={"2401.00001": "https://example.test/a.pdf"},
    )
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})

    def fake_acquire(paper: AcquisitionPaper, **kwargs) -> AcquisitionResult:
        del kwargs
        pdf_path = tmp_path / f"{paper.id}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fixture")
        paper.pdf_path = str(pdf_path)
        paper.oa_status = "open_access"
        paper.parse_status = "pending"
        return AcquisitionResult(paper_id=paper.id, status="downloaded")

    def fake_parse(paper: ParsePaper, **kwargs) -> ParseResult:
        del kwargs
        paper.tei_xml = SAMPLE_TEI
        paper.parse_status = "parsed"
        return ParseResult(
            paper_id=paper.id,
            status="parsed",
            sections=[
                SectionRecord(
                    id=1,
                    parent_id=None,
                    section_path="Introduction",
                    title="Introduction",
                    ordinal=0,
                    page_start=1,
                    page_end=1,
                    char_start=0,
                    char_end=12,
                    body_text="Hello world.",
                )
            ],
        )

    result = pipeline.run_ingest(
        definition.name,
        connection_factory=_connection_factory(isolated_database),
        acquire_fn=fake_acquire,
        parse_fn=fake_parse,
        storage_dir=tmp_path,
    )

    assert result.state == "completed"
    assert result.papers_found == 1
    assert result.papers_parsed == 1
    assert result.papers_newly_parsed == 1

    with isolated_database.connect() as connection:
        job = connection.execute(select(ingest_job)).mappings().one()
        paper_row = connection.execute(select(paper)).mappings().one()
        link = connection.execute(select(paper_scope)).mappings().one()
        sections = connection.execute(select(section)).mappings().all()
        source_rows = connection.execute(select(source_table)).mappings().all()

    assert job["papers_found"] == 1
    assert job["papers_parsed"] == 1
    assert job["state"] == "completed"
    assert job["finished_at"] is not None
    assert paper_row["parse_status"] == "parsed"
    assert paper_row["tei_xml"] == SAMPLE_TEI
    assert paper_row["title"] == "Surface codes"
    assert link["paper_id"] == paper_row["id"]
    assert len(sections) == 1
    assert sections[0]["section_path"] == "Introduction"
    assert {row["name"] for row in source_rows} == {"arxiv"}


def test_resumed_ingest_reports_zero_newly_parsed_papers(
    isolated_database: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.ingest import pipeline
    from ai_researcher.sources import registry

    definition = _scope()
    _insert_scope(isolated_database, definition)
    source = FixtureSource(
        name="arxiv",
        refs=(PaperRef("arxiv", "2401.00001", title="Surface codes"),),
        metadata_by_id={
            "2401.00001": PaperMetadata(
                source="arxiv",
                external_id="2401.00001",
                title="Surface codes",
                arxiv_id="2401.00001",
                authors=("Ada Lovelace",),
                published_at=date(2024, 1, 1),
                pdf_url="https://example.test/a.pdf",
            )
        },
        pdf_urls={"2401.00001": "https://example.test/a.pdf"},
    )
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})

    acquire_calls: list[int] = []
    parse_calls: list[int] = []

    def fake_acquire(paper: AcquisitionPaper, **kwargs) -> AcquisitionResult:
        del kwargs
        acquire_calls.append(paper.id)
        pdf_path = tmp_path / f"{paper.id}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fixture")
        paper.pdf_path = str(pdf_path)
        paper.oa_status = "open_access"
        paper.parse_status = "pending"
        return AcquisitionResult(paper_id=paper.id, status="downloaded")

    def fake_parse(paper: ParsePaper, **kwargs) -> ParseResult:
        del kwargs
        parse_calls.append(paper.id)
        paper.tei_xml = SAMPLE_TEI
        paper.parse_status = "parsed"
        return ParseResult(paper_id=paper.id, status="parsed", sections=[])

    pipeline.run_ingest(
        definition.name,
        connection_factory=_connection_factory(isolated_database),
        acquire_fn=fake_acquire,
        parse_fn=fake_parse,
        storage_dir=tmp_path,
    )
    resumed = pipeline.run_ingest(
        definition.name,
        connection_factory=_connection_factory(isolated_database),
        acquire_fn=fake_acquire,
        parse_fn=fake_parse,
        storage_dir=tmp_path,
    )

    assert resumed.papers_found == 1
    assert resumed.papers_newly_parsed == 0
    assert resumed.papers_parsed == 0
    assert resumed.state == "completed"
    assert len(acquire_calls) == 1
    assert len(parse_calls) == 1


def test_corpus_ceiling_refuses_before_any_download(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.ingest import pipeline
    from ai_researcher.sources import registry

    definition = _scope(per_source_limit=2000)
    _insert_scope(isolated_database, definition)

    refs = tuple(
        PaperRef("arxiv", f"2401.{index:05d}", title=f"Paper {index}") for index in range(1001)
    )
    metadata = {
        ref.external_id: PaperMetadata(
            source="arxiv",
            external_id=ref.external_id,
            title=ref.title or ref.external_id,
            arxiv_id=ref.external_id,
            authors=("Ada Lovelace",),
            published_at=date(2024, 1, 1),
        )
        for ref in refs
    }
    source = FixtureSource(name="arxiv", refs=refs, metadata_by_id=metadata)
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})

    acquire_calls: list[int] = []

    def fake_acquire(paper: AcquisitionPaper, **kwargs) -> AcquisitionResult:
        del kwargs
        acquire_calls.append(paper.id)
        raise AssertionError("ceiling refusal must not download PDFs")

    with pytest.raises(pipeline.CorpusCeilingExceededError) as raised:
        pipeline.run_ingest(
            definition.name,
            connection_factory=_connection_factory(isolated_database),
            acquire_fn=fake_acquire,
        )

    assert raised.value.resolved_count == 1001
    assert raised.value.ceiling == 1000
    assert "1001" in str(raised.value)
    assert "1000" in str(raised.value)
    assert acquire_calls == []

    with isolated_database.connect() as connection:
        jobs = connection.execute(select(ingest_job)).mappings().all()
        papers = connection.execute(select(paper)).mappings().all()

    assert len(jobs) == 1
    assert jobs[0]["state"] == "failed"
    assert jobs[0]["papers_found"] == 1001
    assert papers == []


def test_parse_failure_is_recorded_and_run_continues(
    isolated_database: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.ingest import pipeline
    from ai_researcher.sources import registry

    definition = _scope()
    _insert_scope(isolated_database, definition)
    source = FixtureSource(
        name="arxiv",
        refs=(
            PaperRef("arxiv", "2401.00001", title="Fails parse"),
            PaperRef("arxiv", "2401.00002", title="Succeeds"),
        ),
        metadata_by_id={
            "2401.00001": PaperMetadata(
                source="arxiv",
                external_id="2401.00001",
                title="Fails parse",
                arxiv_id="2401.00001",
                authors=("Ada Lovelace",),
                published_at=date(2024, 1, 1),
                pdf_url="https://example.test/fail.pdf",
            ),
            "2401.00002": PaperMetadata(
                source="arxiv",
                external_id="2401.00002",
                title="Succeeds",
                arxiv_id="2401.00002",
                authors=("Grace Hopper",),
                published_at=date(2024, 1, 2),
                pdf_url="https://example.test/ok.pdf",
            ),
        },
        pdf_urls={
            "2401.00001": "https://example.test/fail.pdf",
            "2401.00002": "https://example.test/ok.pdf",
        },
    )
    monkeypatch.setattr(registry, "_SOURCES", {source.name: source})

    def fake_acquire(paper: AcquisitionPaper, **kwargs) -> AcquisitionResult:
        del kwargs
        pdf_path = tmp_path / f"{paper.id}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fixture")
        paper.pdf_path = str(pdf_path)
        paper.oa_status = "open_access"
        paper.parse_status = "pending"
        return AcquisitionResult(paper_id=paper.id, status="downloaded")

    def fake_parse(parse_paper: ParsePaper, **kwargs) -> ParseResult:
        del kwargs
        with isolated_database.connect() as connection:
            title = connection.execute(
                select(paper.c.title).where(paper.c.id == parse_paper.id)
            ).scalar_one()
        if title == "Fails parse":
            parse_paper.parse_status = "failed"
            return ParseResult(paper_id=parse_paper.id, status="failed", error="grobid boom")
        parse_paper.tei_xml = SAMPLE_TEI
        parse_paper.parse_status = "parsed"
        return ParseResult(paper_id=parse_paper.id, status="parsed", sections=[])

    result = pipeline.run_ingest(
        definition.name,
        connection_factory=_connection_factory(isolated_database),
        acquire_fn=fake_acquire,
        parse_fn=fake_parse,
        storage_dir=tmp_path,
    )

    assert result.state == "completed"
    assert result.papers_found == 2
    assert result.papers_parsed == 1

    with isolated_database.connect() as connection:
        statuses = {
            row["title"]: row["parse_status"]
            for row in connection.execute(select(paper)).mappings().all()
        }
        job = connection.execute(select(ingest_job)).mappings().one()

    assert statuses == {"Fails parse": "failed", "Succeeds": "parsed"}
    assert job["state"] == "completed"
    assert job["papers_parsed"] == 1


def test_cli_ingest_ceiling_exits_nonzero_with_counts(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.ingest import pipeline

    definition = _scope()
    _insert_scope(isolated_database, definition)

    def fake_run(scope_name: str, **kwargs):
        del scope_name, kwargs
        raise pipeline.CorpusCeilingExceededError(resolved_count=1500, ceiling=1000)

    monkeypatch.setattr(pipeline, "run_ingest", fake_run)

    result = CliRunner().invoke(app, ["ingest", definition.name])

    assert result.exit_code != 0
    assert "1500" in result.output
    assert "1000" in result.output


def test_cli_ingest_help_lists_command() -> None:
    result = CliRunner().invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0, result.output
    assert "scope" in result.output.lower() or "NAME" in result.output
