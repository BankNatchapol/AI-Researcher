"""Integration tests for the Phase 4 discourse, subscription, and sweep schema."""

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, insert, inspect, select, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import DatabaseError, SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app

DISCOURSE_TABLES = (
    "discourse_source",
    "discourse_item",
    "discourse_mention",
    "subscription",
    "sweep_run",
)

DISCOURSE_SOURCE_COLUMNS = {
    "id",
    "name",
    "kind",
    "enabled",
    "last_polled_at",
}
DISCOURSE_ITEM_COLUMNS = {
    "id",
    "source_id",
    "external_id",
    "url",
    "title",
    "author",
    "posted_at",
    "score",
    "num_comments",
    "retrieved_at",
}
DISCOURSE_MENTION_COLUMNS = {
    "id",
    "discourse_item_id",
    "paper_id",
    "resolved_by",
    "created_at",
}
SUBSCRIPTION_COLUMNS = {
    "id",
    "kind",
    "scope_id",
    "claim_id",
    "created_at",
    "active",
}
SWEEP_RUN_COLUMNS = {
    "id",
    "kind",
    "started_at",
    "finished_at",
    "state",
    "items_found",
    "error",
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
    database_name = f"test_discourse_schema_{uuid.uuid4().hex}"
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


def _seed_paper_and_claim(connection) -> tuple[int, int, int]:
    from ai_researcher.db.models import metadata

    paper = metadata.tables["paper"]
    section = metadata.tables["section"]
    tree_node = metadata.tables["tree_node"]
    claim = metadata.tables["claim"]
    scope = metadata.tables["scope"]

    scope_id = connection.execute(
        insert(scope).values(name=f"scope-{uuid.uuid4().hex[:8]}").returning(scope.c.id)
    ).scalar_one()
    paper_id = connection.execute(
        insert(paper).values(title="Discourse schema paper").returning(paper.c.id)
    ).scalar_one()
    section_id = connection.execute(
        insert(section)
        .values(paper_id=paper_id, section_path="Results", ordinal=1, body_text="body")
        .returning(section.c.id)
    ).scalar_one()
    tree_node_id = connection.execute(
        insert(tree_node)
        .values(
            paper_id=paper_id,
            section_id=section_id,
            node_path="1",
            summary="Summary",
            depth=0,
            tree_schema_version="1",
            summary_model="test-model",
        )
        .returning(tree_node.c.id)
    ).scalar_one()
    claim_id = connection.execute(
        insert(claim)
        .values(
            paper_id=paper_id,
            tree_node_id=tree_node_id,
            claim_text="Threshold is 1%",
            normalized_text="threshold is 1%",
            claim_type="quantitative",
            extraction_model="test-model",
            prompt_version="1",
        )
        .returning(claim.c.id)
    ).scalar_one()
    return scope_id, paper_id, claim_id


def test_models_define_discourse_tables() -> None:
    from ai_researcher.db.models import metadata

    assert set(metadata.tables["discourse_source"].columns.keys()) == DISCOURSE_SOURCE_COLUMNS
    assert set(metadata.tables["discourse_item"].columns.keys()) == DISCOURSE_ITEM_COLUMNS
    assert set(metadata.tables["discourse_mention"].columns.keys()) == DISCOURSE_MENTION_COLUMNS
    assert set(metadata.tables["subscription"].columns.keys()) == SUBSCRIPTION_COLUMNS
    assert set(metadata.tables["sweep_run"].columns.keys()) == SWEEP_RUN_COLUMNS

    for table_name in DISCOURSE_TABLES:
        for fk in metadata.tables[table_name].foreign_keys:
            assert fk.column.table.name != "claim_score"


def test_discourse_migration_applies_and_enforces_constraints(
    isolated_database: Engine,
) -> None:
    runner = CliRunner()

    first_run = runner.invoke(app, ["db", "migrate"])
    second_run = runner.invoke(app, ["db", "migrate"])

    assert first_run.exit_code == 0, first_run.output
    assert "Applied migration 0011_discourse" in first_run.output
    assert second_run.exit_code == 0, second_run.output
    assert "already up to date" in second_run.output

    database_inspector = inspect(isolated_database)
    assert {
        column["name"] for column in database_inspector.get_columns("discourse_source")
    } == DISCOURSE_SOURCE_COLUMNS
    assert {
        column["name"] for column in database_inspector.get_columns("discourse_item")
    } == DISCOURSE_ITEM_COLUMNS
    assert {
        column["name"] for column in database_inspector.get_columns("discourse_mention")
    } == DISCOURSE_MENTION_COLUMNS
    assert {
        column["name"] for column in database_inspector.get_columns("subscription")
    } == SUBSCRIPTION_COLUMNS
    assert {
        column["name"] for column in database_inspector.get_columns("sweep_run")
    } == SWEEP_RUN_COLUMNS

    with isolated_database.connect() as connection:
        fk_targets = connection.execute(
            text(
                """
                SELECT ccu.table_name AS foreign_table_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = current_schema()
                  AND tc.table_name = ANY(:tables)
                """
            ),
            {"tables": list(DISCOURSE_TABLES)},
        ).fetchall()
    assert all(row[0] != "claim_score" for row in fk_targets)

    from ai_researcher.db.models import metadata

    discourse_source = metadata.tables["discourse_source"]
    discourse_item = metadata.tables["discourse_item"]
    subscription = metadata.tables["subscription"]
    sweep_run = metadata.tables["sweep_run"]

    with isolated_database.begin() as connection:
        scope_id, _paper_id, claim_id = _seed_paper_and_claim(connection)

        source_id = connection.execute(
            insert(discourse_source)
            .values(name="reddit", kind="reddit", enabled=True)
            .returning(discourse_source.c.id)
        ).scalar_one()

        connection.execute(
            insert(discourse_item).values(
                source_id=source_id,
                external_id="abc123",
                url="https://example.com/post/abc123",
                title="A post",
                author="alice",
                score=10,
                num_comments=2,
            )
        )
        with pytest.raises(DatabaseError), connection.begin_nested():
            connection.execute(
                insert(discourse_item).values(
                    source_id=source_id,
                    external_id="abc123",
                    url="https://example.com/post/abc123-dup",
                    title="Duplicate",
                    author="bob",
                    score=1,
                    num_comments=0,
                )
            )

        with pytest.raises(DatabaseError), connection.begin_nested():
            connection.execute(
                insert(subscription).values(
                    kind="topic",
                    scope_id=None,
                    claim_id=None,
                    active=True,
                )
            )
        with pytest.raises(DatabaseError), connection.begin_nested():
            connection.execute(
                insert(subscription).values(
                    kind="topic",
                    scope_id=scope_id,
                    claim_id=claim_id,
                    active=True,
                )
            )

        connection.execute(
            insert(subscription).values(
                kind="topic",
                scope_id=scope_id,
                claim_id=None,
                active=True,
            )
        )
        connection.execute(
            insert(subscription).values(
                kind="claim",
                scope_id=None,
                claim_id=claim_id,
                active=True,
            )
        )

        with pytest.raises(DatabaseError), connection.begin_nested():
            connection.execute(
                insert(sweep_run).values(
                    kind="attention",
                    state="running",
                    items_found=0,
                )
            )
        connection.execute(
            insert(sweep_run).values(
                kind="discourse",
                state="completed",
                items_found=1,
            )
        )

        stored = (
            connection.execute(
                select(discourse_item.c.external_id).where(discourse_item.c.source_id == source_id)
            )
            .scalars()
            .all()
        )
        assert stored == ["abc123"]
