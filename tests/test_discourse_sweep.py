"""Discourse sweep: poll enabled sources with per-source failure isolation."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.db.models import (
    discourse_item,
    discourse_mention,
    discourse_source,
    paper,
    sweep_run,
)
from ai_researcher.discourse.base import DiscourseItem, DiscourseLinkMixin


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
    database_name = f"test_discourse_sweep_{uuid.uuid4().hex}"
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


class _FakeSource(DiscourseLinkMixin):
    """Test double implementing DiscourseSource."""

    def __init__(
        self,
        name: str,
        items: list[DiscourseItem] | None = None,
        *,
        error: Exception | None = None,
        poll_calls: list[datetime] | None = None,
    ) -> None:
        self.name = name
        self._items = items or []
        self._error = error
        self.poll_calls = poll_calls if poll_calls is not None else []

    def poll(self, since: datetime) -> Iterable[DiscourseItem]:
        self.poll_calls.append(since)
        if self._error is not None:
            raise self._error
        return list(self._items)


def _seed_source(
    engine: Engine,
    name: str,
    *,
    enabled: bool = True,
    last_polled_at: datetime | None = None,
) -> int:
    with engine.begin() as connection:
        return int(
            connection.execute(
                insert(discourse_source)
                .values(
                    name=name,
                    kind=name,
                    enabled=enabled,
                    last_polled_at=last_polled_at,
                )
                .returning(discourse_source.c.id)
            ).scalar_one()
        )


def _seed_paper(engine: Engine, *, arxiv_id: str = "2401.00001") -> int:
    with engine.begin() as connection:
        return int(
            connection.execute(
                insert(paper)
                .values(title=f"Paper {arxiv_id}", arxiv_id=arxiv_id)
                .returning(paper.c.id)
            ).scalar_one()
        )


def _item(
    *,
    source: str = "alpha",
    external_id: str = "ext-1",
    url: str = "https://arxiv.org/abs/2401.00001",
    title: str = "Discussing a paper",
    **overrides: Any,
) -> DiscourseItem:
    values = {
        "source": source,
        "external_id": external_id,
        "url": url,
        "title": title,
        "author": "tester",
        "body": None,
        "posted_at": datetime(2024, 6, 1, tzinfo=UTC),
        "score": 10,
        "num_comments": 2,
    }
    values.update(overrides)
    return DiscourseItem(**values)


def test_clean_poll_writes_sweep_run_stores_mentions_advances_last_polled(
    isolated_database: Engine,
) -> None:
    from ai_researcher.monitor.discourse_sweep import run_discourse_sweep

    paper_id = _seed_paper(isolated_database)
    _seed_source(isolated_database, "alpha")
    source = _FakeSource(
        "alpha",
        [_item(source="alpha", external_id="post-1")],
    )

    result = run_discourse_sweep(
        connection_factory=_connection_factory(isolated_database),
        sources=[source],
    )

    assert result.kind == "discourse"
    assert result.state == "completed"
    assert result.items_found == 1
    assert result.error is None

    with isolated_database.connect() as connection:
        runs = connection.execute(
            select(sweep_run.c.kind, sweep_run.c.state, sweep_run.c.items_found)
        ).all()
        assert runs == [("discourse", "completed", 1)]

        items = connection.execute(select(discourse_item.c.external_id)).scalars().all()
        assert items == ["post-1"]

        mentions = connection.execute(select(discourse_mention.c.paper_id)).scalars().all()
        assert mentions == [paper_id]

        last_polled = connection.execute(
            select(discourse_source.c.last_polled_at).where(discourse_source.c.name == "alpha")
        ).scalar_one()
        assert last_polled is not None
        assert last_polled.tzinfo is not None

    assert len(source.poll_calls) == 1
    assert source.poll_calls[0] == datetime(1970, 1, 1, tzinfo=UTC)


def test_repeat_poll_adds_zero_duplicate_items(
    isolated_database: Engine,
) -> None:
    from ai_researcher.monitor.discourse_sweep import run_discourse_sweep

    _seed_paper(isolated_database)
    _seed_source(isolated_database, "alpha")
    item = _item(source="alpha", external_id="post-dup")
    source = _FakeSource("alpha", [item])
    factory = _connection_factory(isolated_database)

    first = run_discourse_sweep(connection_factory=factory, sources=[source])
    assert first.items_found == 1

    with isolated_database.connect() as connection:
        last_polled = connection.execute(
            select(discourse_source.c.last_polled_at).where(discourse_source.c.name == "alpha")
        ).scalar_one()

    sticky = _FakeSource("alpha", [item])
    second = run_discourse_sweep(connection_factory=factory, sources=[sticky])

    assert second.state == "completed"
    assert second.items_found == 0
    assert sticky.poll_calls == [last_polled]

    with isolated_database.connect() as connection:
        count = connection.execute(select(func.count()).select_from(discourse_item)).scalar_one()
        assert int(count) == 1
        run_count = connection.execute(select(func.count()).select_from(sweep_run)).scalar_one()
        assert int(run_count) == 2


def test_failing_source_recorded_while_others_complete(
    isolated_database: Engine,
) -> None:
    from ai_researcher.monitor.discourse_sweep import run_discourse_sweep

    _seed_paper(isolated_database)
    _seed_source(isolated_database, "good")
    _seed_source(isolated_database, "bad")
    good = _FakeSource(
        "good",
        [_item(source="good", external_id="ok-1")],
    )
    bad = _FakeSource("bad", error=RuntimeError("upstream down"))

    result = run_discourse_sweep(
        connection_factory=_connection_factory(isolated_database),
        sources=[good, bad],
    )

    assert result.kind == "discourse"
    assert result.state == "completed_with_errors"
    assert result.items_found == 1
    assert result.error is not None
    assert "bad" in result.error
    assert "upstream down" in result.error

    with isolated_database.connect() as connection:
        items = connection.execute(select(discourse_item.c.external_id)).scalars().all()
        assert items == ["ok-1"]

        good_polled = connection.execute(
            select(discourse_source.c.last_polled_at).where(discourse_source.c.name == "good")
        ).scalar_one()
        bad_polled = connection.execute(
            select(discourse_source.c.last_polled_at).where(discourse_source.c.name == "bad")
        ).scalar_one()
        assert good_polled is not None
        assert bad_polled is None


def test_missing_credentials_skipped_not_failed(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ai_researcher.monitor.discourse_sweep import run_discourse_sweep

    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    _seed_source(isolated_database, "reddit")
    _seed_source(isolated_database, "hackernews")
    reddit = _FakeSource(
        "reddit",
        [_item(source="reddit", external_id="should-not-store")],
    )
    hn = _FakeSource(
        "hackernews",
        [
            _item(
                source="hackernews",
                external_id="hn-1",
                url="https://example.test/no-paper",
            )
        ],
    )

    with caplog.at_level(logging.INFO):
        result = run_discourse_sweep(
            connection_factory=_connection_factory(isolated_database),
            sources=[reddit, hn],
        )

    assert result.state == "completed"
    assert result.items_found == 1
    assert result.error is None
    assert reddit.poll_calls == []
    assert len(hn.poll_calls) == 1
    assert any(
        "reddit" in record.message.lower() and "skip" in record.message.lower()
        for record in caplog.records
    )

    with isolated_database.connect() as connection:
        names = connection.execute(select(discourse_item.c.external_id)).scalars().all()
        assert names == ["hn-1"]
        reddit_polled = connection.execute(
            select(discourse_source.c.last_polled_at).where(discourse_source.c.name == "reddit")
        ).scalar_one()
        assert reddit_polled is None


def test_cli_discourse_sweep_exits_zero_with_failing_source(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_researcher.monitor.discourse_sweep as discourse_sweep_module

    _seed_source(isolated_database, "ok")
    _seed_source(isolated_database, "boom")
    ok = _FakeSource("ok", [])
    boom = _FakeSource("boom", error=RuntimeError("boom"))
    real_run = discourse_sweep_module.run_discourse_sweep

    def fake_run(**_kwargs):
        return real_run(
            connection_factory=_connection_factory(isolated_database),
            sources=[ok, boom],
        )

    monkeypatch.setattr(discourse_sweep_module, "run_discourse_sweep", fake_run)

    runner = CliRunner()
    result = runner.invoke(app, ["sweep", "--kind", "discourse"])
    assert result.exit_code == 0, result.output
    assert "kind=discourse" in result.output
    assert "completed_with_errors" in result.output
