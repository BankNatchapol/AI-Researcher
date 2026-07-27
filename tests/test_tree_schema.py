"""Integration tests for the vectorless retrieval tree schema."""

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, insert, inspect
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import DatabaseError, SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app

TREE_NODE_COLUMNS = {
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
}
RETRIEVAL_TRACE_COLUMNS = {
    "id",
    "question",
    "scope_id",
    "expanded_node_ids",
    "selected_node_ids",
    "nodes_expanded",
    "stopped_reason",
    "created_at",
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
    database_name = f"test_tree_schema_{uuid.uuid4().hex}"
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


def test_models_define_tree_and_retrieval_trace_tables() -> None:
    from ai_researcher.db.models import metadata

    assert set(metadata.tables["tree_node"].columns.keys()) == TREE_NODE_COLUMNS
    assert set(metadata.tables["retrieval_trace"].columns.keys()) == RETRIEVAL_TRACE_COLUMNS

    tree_node = metadata.tables["tree_node"]
    assert tree_node.c.paper_id.nullable is False
    assert tree_node.c.section_id.nullable is False
    assert {foreign_key.target_fullname for foreign_key in tree_node.c.paper_id.foreign_keys} == {
        "paper.id"
    }
    assert {foreign_key.target_fullname for foreign_key in tree_node.c.section_id.foreign_keys} == {
        "section.id"
    }


def test_tree_migration_is_idempotent_and_rejects_null_section(
    isolated_database: Engine,
) -> None:
    runner = CliRunner()

    first_run = runner.invoke(app, ["db", "migrate"])
    second_run = runner.invoke(app, ["db", "migrate"])

    assert first_run.exit_code == 0, first_run.output
    assert "Applied migration 0003_trees" in first_run.output
    assert second_run.exit_code == 0, second_run.output
    assert "already up to date" in second_run.output

    database_inspector = inspect(isolated_database)
    assert {
        column["name"] for column in database_inspector.get_columns("tree_node")
    } == TREE_NODE_COLUMNS
    assert {
        column["name"] for column in database_inspector.get_columns("retrieval_trace")
    } == RETRIEVAL_TRACE_COLUMNS

    from ai_researcher.db.models import metadata

    paper = metadata.tables["paper"]
    tree_node = metadata.tables["tree_node"]
    with isolated_database.begin() as connection:
        paper_id = connection.execute(
            insert(paper).values(title="Tree schema paper").returning(paper.c.id)
        ).scalar_one()
        with pytest.raises(DatabaseError), connection.begin_nested():
            connection.execute(
                insert(tree_node).values(
                    paper_id=paper_id,
                    section_id=None,
                    node_path="1",
                    summary="Summary",
                    depth=0,
                    tree_schema_version="1",
                    summary_model="test-model",
                )
            )
