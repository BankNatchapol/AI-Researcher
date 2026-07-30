"""Topic and claim subscription create / list / deactivate behaviour."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.db.models import claim as claim_table
from ai_researcher.db.models import paper, section, tree_node
from ai_researcher.db.models import scope as scope_table
from ai_researcher.db.models import subscription as subscription_table


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
    database_name = f"test_subscriptions_{uuid.uuid4().hex}"
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


def _seed_scope_and_claim(
    engine: Engine,
    *,
    scope_name: str = "surface-codes",
    claim_text: str = "Threshold is 1%",
    canonical_claim_id: int | None = None,
) -> tuple[int, int]:
    with engine.begin() as connection:
        scope_id = int(
            connection.execute(
                insert(scope_table)
                .values(
                    name=scope_name,
                    description="Surface codes",
                    include_terms=["surface code"],
                    exclude_terms=[],
                    categories=["quant-ph"],
                    per_source_limit=10,
                )
                .returning(scope_table.c.id)
            ).scalar_one()
        )
        paper_id = int(
            connection.execute(
                insert(paper).values(title="Seed paper").returning(paper.c.id)
            ).scalar_one()
        )
        section_id = int(
            connection.execute(
                insert(section)
                .values(
                    paper_id=paper_id,
                    section_path="Results",
                    ordinal=1,
                    body_text="body",
                )
                .returning(section.c.id)
            ).scalar_one()
        )
        tree_node_id = int(
            connection.execute(
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
        )
        claim_id = int(
            connection.execute(
                insert(claim_table)
                .values(
                    paper_id=paper_id,
                    tree_node_id=tree_node_id,
                    claim_text=claim_text,
                    normalized_text=claim_text.lower(),
                    claim_type="quantitative",
                    extraction_model="test-model",
                    prompt_version="1",
                    canonical_claim_id=canonical_claim_id,
                )
                .returning(claim_table.c.id)
            ).scalar_one()
        )
    return scope_id, claim_id


def test_subscribe_topic_creates_active_subscription(isolated_database: Engine) -> None:
    from ai_researcher.monitor.subscription import subscribe_topic

    scope_id, _claim_id = _seed_scope_and_claim(isolated_database)
    factory = _connection_factory(isolated_database)

    record = subscribe_topic("surface-codes", connection_factory=factory)

    assert record.kind == "topic"
    assert record.scope_id == scope_id
    assert record.claim_id is None
    assert record.active is True
    assert record.id > 0

    with isolated_database.connect() as connection:
        row = (
            connection.execute(
                select(subscription_table).where(subscription_table.c.id == record.id)
            )
            .mappings()
            .one()
        )
    assert row["kind"] == "topic"
    assert row["scope_id"] == scope_id
    assert row["claim_id"] is None
    assert row["active"] is True


def test_subscribe_claim_creates_active_subscription(isolated_database: Engine) -> None:
    from ai_researcher.monitor.subscription import subscribe_claim

    _scope_id, claim_id = _seed_scope_and_claim(isolated_database)
    factory = _connection_factory(isolated_database)

    record = subscribe_claim(claim_id, connection_factory=factory)

    assert record.kind == "claim"
    assert record.claim_id == claim_id
    assert record.scope_id is None
    assert record.active is True


def test_subscribe_claim_rejects_unknown_id_with_named_error(
    isolated_database: Engine,
) -> None:
    from ai_researcher.monitor.subscription import UnknownClaimError, subscribe_claim

    factory = _connection_factory(isolated_database)

    with pytest.raises(UnknownClaimError, match=r"Unknown claim"):
        subscribe_claim(999_999, connection_factory=factory)


def test_subscribe_claim_targets_canonical_claim(isolated_database: Engine) -> None:
    from ai_researcher.monitor.subscription import subscribe_claim

    _scope_id, canonical_id = _seed_scope_and_claim(
        isolated_database, claim_text="Canonical threshold"
    )
    _dup_scope_id, duplicate_id = _seed_scope_and_claim(
        isolated_database,
        scope_name="other-scope",
        claim_text="Duplicate threshold",
        canonical_claim_id=canonical_id,
    )
    factory = _connection_factory(isolated_database)

    record = subscribe_claim(duplicate_id, connection_factory=factory)

    assert record.claim_id == canonical_id
    assert record.claim_id != duplicate_id


def test_duplicate_topic_subscription_is_rejected(isolated_database: Engine) -> None:
    from ai_researcher.monitor.subscription import (
        DuplicateSubscriptionError,
        subscribe_topic,
    )

    _seed_scope_and_claim(isolated_database)
    factory = _connection_factory(isolated_database)
    subscribe_topic("surface-codes", connection_factory=factory)

    with pytest.raises(DuplicateSubscriptionError, match=r"[Dd]uplicate"):
        subscribe_topic("surface-codes", connection_factory=factory)


def test_duplicate_claim_subscription_is_rejected(isolated_database: Engine) -> None:
    from ai_researcher.monitor.subscription import (
        DuplicateSubscriptionError,
        subscribe_claim,
    )

    _scope_id, claim_id = _seed_scope_and_claim(isolated_database)
    factory = _connection_factory(isolated_database)
    subscribe_claim(claim_id, connection_factory=factory)

    with pytest.raises(DuplicateSubscriptionError, match=r"[Dd]uplicate"):
        subscribe_claim(claim_id, connection_factory=factory)


def test_subscribe_topic_rejects_unknown_scope(isolated_database: Engine) -> None:
    from ai_researcher.monitor.subscription import UnknownScopeError, subscribe_topic

    factory = _connection_factory(isolated_database)

    with pytest.raises(UnknownScopeError, match=r"Unknown scope"):
        subscribe_topic("missing-scope", connection_factory=factory)


def test_list_subscriptions_includes_kind_target_and_active(
    isolated_database: Engine,
) -> None:
    from ai_researcher.monitor.subscription import (
        list_subscriptions,
        subscribe_claim,
        subscribe_topic,
    )

    scope_id, claim_id = _seed_scope_and_claim(isolated_database)
    factory = _connection_factory(isolated_database)
    topic = subscribe_topic("surface-codes", connection_factory=factory)
    claim = subscribe_claim(claim_id, connection_factory=factory)

    records = list_subscriptions(connection_factory=factory)

    assert {(r.id, r.kind, r.active) for r in records} >= {
        (topic.id, "topic", True),
        (claim.id, "claim", True),
    }
    by_id = {r.id: r for r in records}
    assert by_id[topic.id].target == "surface-codes" or by_id[topic.id].scope_id == scope_id
    assert by_id[claim.id].claim_id == claim_id


def test_unsubscribe_deactivates_without_deleting(isolated_database: Engine) -> None:
    from ai_researcher.monitor.subscription import (
        list_subscriptions,
        subscribe_topic,
        unsubscribe,
    )

    _seed_scope_and_claim(isolated_database)
    factory = _connection_factory(isolated_database)
    record = subscribe_topic("surface-codes", connection_factory=factory)

    deactivated = unsubscribe(record.id, connection_factory=factory)

    assert deactivated.id == record.id
    assert deactivated.active is False

    with isolated_database.connect() as connection:
        row = (
            connection.execute(
                select(subscription_table).where(subscription_table.c.id == record.id)
            )
            .mappings()
            .one_or_none()
        )
    assert row is not None, "unsubscribe must leave the row in place"
    assert row["active"] is False

    listed = list_subscriptions(connection_factory=factory)
    assert any(item.id == record.id and item.active is False for item in listed)


def test_cli_subscribe_topic_subscriptions_and_unsubscribe(
    isolated_database: Engine,
) -> None:
    _seed_scope_and_claim(isolated_database)
    runner = CliRunner()

    topic = runner.invoke(app, ["subscribe", "topic", "surface-codes"])
    assert topic.exit_code == 0, topic.output
    assert "topic" in topic.output.lower()
    assert "active" in topic.output.lower() or "subscribed" in topic.output.lower()

    listed = runner.invoke(app, ["subscriptions"])
    assert listed.exit_code == 0, listed.output
    assert "topic" in listed.output
    assert "surface-codes" in listed.output
    assert "active" in listed.output.lower() or "True" in listed.output or "true" in listed.output

    with isolated_database.connect() as connection:
        sub_id = connection.execute(select(subscription_table.c.id)).scalar_one()

    unsub = runner.invoke(app, ["unsubscribe", str(sub_id)])
    assert unsub.exit_code == 0, unsub.output

    with isolated_database.connect() as connection:
        row = (
            connection.execute(select(subscription_table).where(subscription_table.c.id == sub_id))
            .mappings()
            .one()
        )
    assert row["active"] is False


def test_cli_subscribe_claim_rejects_unknown_id(isolated_database: Engine) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["subscribe", "claim", "999999"])
    assert result.exit_code != 0
    assert "Unknown claim" in result.output or "unknown claim" in result.output.lower()
