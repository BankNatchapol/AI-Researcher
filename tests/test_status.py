"""Offline tests for corpus status reporting and structured logging."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.db.models import paper, paper_scope, section
from ai_researcher.db.models import scope as scope_table
from ai_researcher.ingest.acquire import AcquisitionPaper, AcquisitionResult
from ai_researcher.ingest.dedup import MergedPaper, PaperSource
from ai_researcher.ingest.parse import ParsePaper, ParseResult
from ai_researcher.ingest.tei import SectionRecord
from ai_researcher.scoping import ScopeDefinition


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
    database_name = f"test_status_{uuid.uuid4().hex}"
    admin_engine = create_engine(_pg8000_url(database_url), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

    scoped_url = make_url(database_url).set(database=database_name)
    database_engine = create_engine(_pg8000_url(scoped_url))
    monkeypatch.setenv("DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")

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


def _seed_mixed_scope(engine: Engine) -> None:
    with engine.begin() as connection:
        scope_id = int(
            connection.execute(
                insert(scope_table)
                .values(
                    name="mixed-corpus",
                    description="Parsed, abstract-only, and failed papers",
                    include_terms=["quantum"],
                    exclude_terms=[],
                    categories=["quant-ph"],
                    date_from=date(2020, 1, 1),
                    date_to=date(2025, 12, 31),
                    per_source_limit=10,
                )
                .returning(scope_table.c.id)
            ).scalar_one()
        )
        empty_scope_id = int(
            connection.execute(
                insert(scope_table)
                .values(
                    name="empty-scope",
                    description="No papers yet",
                    include_terms=["empty"],
                    exclude_terms=[],
                    categories=[],
                    per_source_limit=10,
                )
                .returning(scope_table.c.id)
            ).scalar_one()
        )
        del empty_scope_id

        parsed_id = int(
            connection.execute(
                insert(paper)
                .values(
                    title="Parsed paper",
                    parse_status="parsed",
                    oa_status="open",
                    doi="10.1000/parsed",
                )
                .returning(paper.c.id)
            ).scalar_one()
        )
        abstract_id = int(
            connection.execute(
                insert(paper)
                .values(
                    title="Abstract only paper",
                    parse_status="abstract_only",
                    oa_status="closed",
                    doi="10.1000/abstract",
                )
                .returning(paper.c.id)
            ).scalar_one()
        )
        failed_id = int(
            connection.execute(
                insert(paper)
                .values(
                    title="Failed paper",
                    parse_status="failed",
                    oa_status="download_failed",
                    parse_error="grobid boom",
                    doi="10.1000/failed",
                )
                .returning(paper.c.id)
            ).scalar_one()
        )
        for paper_id in (parsed_id, abstract_id, failed_id):
            connection.execute(insert(paper_scope).values(paper_id=paper_id, scope_id=scope_id))

        connection.execute(
            insert(section).values(
                paper_id=parsed_id,
                parent_id=None,
                section_path="1",
                title="Introduction",
                ordinal=0,
                page_start=1,
                page_end=2,
                char_start=0,
                char_end=12,
                body_text="Hello world.",
            )
        )
        connection.execute(
            insert(section).values(
                paper_id=parsed_id,
                parent_id=None,
                section_path="2",
                title="Methods",
                ordinal=1,
                page_start=2,
                page_end=3,
                char_start=0,
                char_end=7,
                body_text="Details.",
            )
        )


def test_scope_status_aggregates_counts_by_sql(isolated_database: Engine) -> None:
    from ai_researcher.corpus.status import scope_status

    _seed_mixed_scope(isolated_database)

    statuses = scope_status(None, connection_factory=_connection_factory(isolated_database))
    by_name = {item.scope_name: item for item in statuses}

    assert set(by_name) == {"mixed-corpus", "empty-scope"}
    mixed = by_name["mixed-corpus"]
    assert mixed.paper_count == 3
    assert mixed.parsed_count == 1
    assert mixed.abstract_only_count == 1
    assert mixed.failed_count == 1
    assert mixed.section_count == 2
    assert mixed.failed_papers == ()

    empty = by_name["empty-scope"]
    assert empty.paper_count == 0
    assert empty.parsed_count == 0
    assert empty.abstract_only_count == 0
    assert empty.failed_count == 0
    assert empty.section_count == 0


def test_scope_status_for_one_scope_lists_failed_papers(
    isolated_database: Engine,
) -> None:
    from ai_researcher.corpus.status import scope_status

    _seed_mixed_scope(isolated_database)

    statuses = scope_status(
        "mixed-corpus",
        connection_factory=_connection_factory(isolated_database),
    )
    assert len(statuses) == 1
    status = statuses[0]
    assert status.scope_name == "mixed-corpus"
    assert status.failed_count == 1
    assert len(status.failed_papers) == 1
    failed = status.failed_papers[0]
    assert failed.title == "Failed paper"
    assert failed.error == "grobid boom"


def test_status_cli_prints_counts_and_scope_filter(
    isolated_database: Engine,
) -> None:
    _seed_mixed_scope(isolated_database)
    runner = CliRunner()

    all_scopes = runner.invoke(app, ["status"])
    assert all_scopes.exit_code == 0, all_scopes.output
    assert "mixed-corpus" in all_scopes.stdout
    assert "empty-scope" in all_scopes.stdout
    assert "papers: 3" in all_scopes.stdout
    assert "parsed: 1" in all_scopes.stdout
    assert "abstract_only: 1" in all_scopes.stdout
    assert "failed: 1" in all_scopes.stdout
    assert "sections: 2" in all_scopes.stdout
    assert "Failed papers:" not in all_scopes.stdout

    one_scope = runner.invoke(app, ["status", "--scope", "mixed-corpus"])
    assert one_scope.exit_code == 0, one_scope.output
    assert "mixed-corpus" in one_scope.stdout
    assert "empty-scope" not in one_scope.stdout
    assert "Failed papers:" in one_scope.stdout
    assert "Failed paper" in one_scope.stdout
    assert "grobid boom" in one_scope.stdout


def test_logs_go_to_stderr_not_stdout(isolated_database: Engine) -> None:
    import sys

    from ai_researcher.logging import ROOT_LOGGER_NAME, configure_logging, get_logger

    _seed_mixed_scope(isolated_database)
    runner = CliRunner()

    result = runner.invoke(app, ["status", "--scope", "mixed-corpus"])
    assert result.exit_code == 0, result.output
    assert "mixed-corpus" in result.output
    # Command results stay free of log-record formatting on the captured stream.
    assert "ai_researcher.corpus" not in result.output

    configure_logging(verbose=False)
    info_logger = get_logger("ai_researcher.test")
    assert info_logger.isEnabledFor(logging.INFO)
    assert not info_logger.isEnabledFor(logging.DEBUG)

    configure_logging(verbose=True)
    debug_logger = get_logger("ai_researcher.test")
    assert debug_logger.isEnabledFor(logging.DEBUG)

    package_logger = logging.getLogger(ROOT_LOGGER_NAME)
    stderr_handlers = [
        handler
        for handler in package_logger.handlers
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stderr
    ]
    assert stderr_handlers, "expected a StreamHandler bound to sys.stderr"


def test_ingest_emits_per_paper_progress_lines(
    isolated_database: Engine,
) -> None:
    from ai_researcher.ingest import pipeline
    from ai_researcher.logging import ROOT_LOGGER_NAME, configure_logging

    definition = ScopeDefinition(
        name="progress-scope",
        description="Progress logging",
        include_terms=("quantum",),
        exclude_terms=(),
        categories=("quant-ph",),
        date_from=date(2020, 1, 1),
        date_to=date(2025, 12, 31),
        per_source_limit=10,
    )
    with isolated_database.begin() as connection:
        connection.execute(
            insert(scope_table).values(
                name=definition.name,
                description=definition.description,
                include_terms=list(definition.include_terms),
                exclude_terms=list(definition.exclude_terms),
                categories=list(definition.categories),
                date_from=definition.date_from,
                date_to=definition.date_to,
                per_source_limit=definition.per_source_limit,
            )
        )

    candidates = [
        MergedPaper(
            title="First",
            doi="10.1000/first",
            authors=("Ada",),
            published_at=date(2024, 1, 1),
            is_preprint=True,
            pdf_url="https://example.com/first.pdf",
            paper_sources=(PaperSource(source="arxiv", external_id="2401.00001"),),
        ),
        MergedPaper(
            title="Second",
            doi="10.1000/second",
            authors=("Grace",),
            published_at=date(2024, 2, 1),
            is_preprint=True,
            pdf_url="https://example.com/second.pdf",
            paper_sources=(PaperSource(source="arxiv", external_id="2401.00002"),),
        ),
    ]

    def fake_discover(scope, **_kwargs):
        del scope
        return list(candidates)

    def fake_acquire(acq_paper: AcquisitionPaper, **_kwargs) -> AcquisitionResult:
        acq_paper.pdf_path = f"/tmp/{acq_paper.id}.pdf"
        acq_paper.oa_status = "open"
        acq_paper.parse_status = "pending"
        return AcquisitionResult(paper_id=acq_paper.id, status="acquired")

    def fake_parse(parse_paper: ParsePaper) -> ParseResult:
        parse_paper.tei_xml = "<TEI/>"
        parse_paper.parse_status = "parsed"
        return ParseResult(
            paper_id=parse_paper.id,
            status="parsed",
            sections=[
                SectionRecord(
                    id=1,
                    parent_id=None,
                    section_path="1",
                    title="Body",
                    ordinal=0,
                    page_start=1,
                    page_end=1,
                    char_start=0,
                    char_end=4,
                    body_text="Body",
                )
            ],
        )

    configure_logging(verbose=False)
    captured: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    handler = _Capture()
    handler.setLevel(logging.INFO)
    logging.getLogger(ROOT_LOGGER_NAME).addHandler(handler)
    try:
        result = pipeline.run_ingest(
            "progress-scope",
            connection_factory=_connection_factory(isolated_database),
            discover_fn=fake_discover,
            acquire_fn=fake_acquire,
            parse_fn=fake_parse,
        )
    finally:
        logging.getLogger(ROOT_LOGGER_NAME).removeHandler(handler)

    assert result.state == "completed"
    assert any("1/2" in message for message in captured)
    assert any("2/2" in message for message in captured)
