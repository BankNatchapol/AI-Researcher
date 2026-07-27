"""Integration tests for the PostgreSQL migration runner and schema."""

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app

EXPECTED_COLUMNS = {
    "source": {"id", "name", "kind", "enabled"},
    "scope": {
        "id",
        "name",
        "description",
        "include_terms",
        "exclude_terms",
        "categories",
        "date_from",
        "date_to",
        "per_source_limit",
        "created_at",
    },
    "paper": {
        "id",
        "doi",
        "arxiv_id",
        "openalex_id",
        "s2_id",
        "title",
        "abstract",
        "published_at",
        "venue",
        "is_preprint",
        "oa_status",
        "pdf_path",
        "tei_xml",
        "parse_status",
        "parse_error",
        "created_at",
    },
    "paper_author": {"id", "paper_id", "position", "full_name"},
    "paper_source": {
        "id",
        "paper_id",
        "source_id",
        "external_id",
        "retrieved_at",
    },
    "paper_scope": {"paper_id", "scope_id"},
    "section": {
        "id",
        "paper_id",
        "parent_id",
        "section_path",
        "title",
        "ordinal",
        "page_start",
        "page_end",
        "char_start",
        "char_end",
        "body_text",
    },
    "ingest_job": {
        "id",
        "scope_id",
        "state",
        "papers_found",
        "papers_parsed",
        "started_at",
        "finished_at",
        "error",
    },
    "tree_node": {
        "id",
        "paper_id",
        "section_id",
        "parent_id",
        "node_path",
        "title",
        "summary",
        "page_start",
        "page_end",
        "depth",
        "tree_schema_version",
        "summary_model",
        "created_at",
    },
    "retrieval_trace": {
        "id",
        "question",
        "scope_id",
        "expanded_node_ids",
        "selected_node_ids",
        "nodes_expanded",
        "stopped_reason",
        "created_at",
    },
}


def _pg8000_url(url: str | URL) -> URL:
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
    database_name = f"test_migrations_{uuid.uuid4().hex}"
    admin_engine = create_engine(_pg8000_url(database_url), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

    scoped_url = make_url(database_url).set(database=database_name)
    database_engine = create_engine(_pg8000_url(scoped_url))
    monkeypatch.setenv("DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")

    try:
        yield database_engine
    finally:
        database_engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')
        admin_engine.dispose()


def test_db_help_lists_migrate_command() -> None:
    result = CliRunner().invoke(app, ["db", "--help"])

    assert result.exit_code == 0, result.output
    assert "migrate" in result.output


def test_models_define_every_migrated_table() -> None:
    from ai_researcher.db.models import metadata

    assert set(metadata.tables) == {"schema_migration", *EXPECTED_COLUMNS}
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        assert set(metadata.tables[table_name].columns.keys()) == expected_columns


def test_cli_applies_all_migrations_and_is_idempotent(
    isolated_database: Engine,
) -> None:
    runner = CliRunner()

    first_run = runner.invoke(app, ["db", "migrate"])
    second_run = runner.invoke(app, ["db", "migrate"])

    assert first_run.exit_code == 0, first_run.output
    assert "Applied migration 0001_initial" in first_run.output
    assert "Applied migration 0002_paper_parse_error" in first_run.output
    assert "Applied migration 0003_trees" in first_run.output
    assert "Applied migration 0004_fts_index" in first_run.output
    assert second_run.exit_code == 0, second_run.output
    assert "already up to date" in second_run.output

    with isolated_database.connect() as connection:
        table_rows = connection.exec_driver_sql(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
            """
        ).fetchall()
        columns = connection.exec_driver_sql(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
            """
        ).fetchall()
        applied = connection.exec_driver_sql(
            "SELECT version, name, applied_at FROM schema_migration"
        ).fetchall()

    assert {row[0] for row in table_rows} == {"schema_migration", *EXPECTED_COLUMNS}
    actual_columns: dict[str, set[str]] = {}
    for table_name, column_name in columns:
        actual_columns.setdefault(table_name, set()).add(column_name)
    for table_name, expected in EXPECTED_COLUMNS.items():
        assert actual_columns[table_name] == expected
    assert len(applied) == 4
    assert applied[0][0:2] == (1, "0001_initial")
    assert applied[1][0:2] == (2, "0002_paper_parse_error")
    assert applied[2][0:2] == (3, "0003_trees")
    assert applied[3][0:2] == (4, "0004_fts_index")
    assert applied[0][2] is not None
    assert applied[1][2] is not None
    assert applied[2][2] is not None
    assert applied[3][2] is not None


@pytest.mark.parametrize("identifier", ["doi", "arxiv_id"])
def test_non_null_paper_identifiers_are_unique(isolated_database: Engine, identifier: str) -> None:
    from ai_researcher.db.migrate import migrate

    migrate()
    statement = text(f"INSERT INTO paper (title, {identifier}) VALUES (:title, :identifier)")

    with isolated_database.begin() as connection:
        connection.execute(statement, {"title": "First paper", "identifier": "duplicate-id"})
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(statement, {"title": "Second paper", "identifier": "duplicate-id"})


def test_multiple_null_paper_identifiers_are_allowed(
    isolated_database: Engine,
) -> None:
    from ai_researcher.db.migrate import migrate

    migrate()
    with isolated_database.begin() as connection:
        connection.exec_driver_sql("INSERT INTO paper (title) VALUES ('First paper')")
        connection.exec_driver_sql("INSERT INTO paper (title) VALUES ('Second paper')")
