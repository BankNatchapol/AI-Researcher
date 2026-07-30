"""Offline tests for discourse paper-link resolution (arXiv ID / DOI)."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.discourse.base import DiscourseItem, DiscourseLinkMixin
from ai_researcher.discourse.resolve import (
    Identifier,
    extract_identifiers,
    link_targets,
    store_item_with_mentions,
)
from ai_researcher.logging import ROOT_LOGGER_NAME, configure_logging
from ai_researcher.sources.base import PaperRef


def _pg8000_url(url: str):
    return make_url(url).set(drivername="postgresql+pg8000")


@pytest.fixture
def database_url() -> str:
    # Prefer the dedicated test DSN. Ignore the offline placeholder that
    # ``discourse_environment`` sets on DATABASE_URL for adapter unit tests.
    url = os.environ.get(
        "AI_RESEARCHER_TEST_DATABASE_URL",
        "postgresql://postgres:issue3@127.0.0.1:55432/ai_researcher_test",
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
    database_name = f"test_link_resolution_{uuid.uuid4().hex}"
    admin_engine = create_engine(_pg8000_url(database_url), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

    scoped_url = make_url(database_url).set(database=database_name)
    database_engine = create_engine(_pg8000_url(scoped_url))
    monkeypatch.setenv("DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")

    runner = CliRunner()
    result = runner.invoke(app, ["db", "migrate"])
    assert result.exit_code == 0, result.output

    try:
        yield database_engine
    finally:
        database_engine.dispose()
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')
        admin_engine.dispose()


def _item(**kwargs: object) -> DiscourseItem:
    defaults: dict[str, object] = {
        "source": "reddit",
        "external_id": "t3_abc",
        "url": "https://www.reddit.com/r/QuantumComputing/comments/abc",
        "title": "Interesting discussion",
        "body": None,
        "posted_at": datetime(2026, 1, 15, tzinfo=UTC),
        "score": 10,
        "num_comments": 2,
    }
    defaults.update(kwargs)
    return DiscourseItem(**defaults)  # type: ignore[arg-type]


def test_extract_identifiers_from_arxiv_abs_url() -> None:
    ids = extract_identifiers("https://arxiv.org/abs/2601.01234")
    assert ids == [Identifier(kind="arxiv", value="2601.01234")]


def test_extract_identifiers_from_arxiv_pdf_url() -> None:
    ids = extract_identifiers("https://arxiv.org/pdf/quant-ph/0601001.pdf")
    assert ids == [Identifier(kind="arxiv", value="quant-ph/0601001")]


def test_extract_identifiers_bare_arxiv_id_in_body() -> None:
    ids = extract_identifiers("See 2601.01234 for the construction and also arXiv:1706.03762v5.")
    assert Identifier(kind="arxiv", value="2601.01234") in ids
    assert Identifier(kind="arxiv", value="1706.03762") in ids


def test_extract_identifiers_from_doi_url() -> None:
    ids = extract_identifiers("https://doi.org/10.1038/s41586-023-00001-x")
    assert ids == [Identifier(kind="doi", value="10.1038/s41586-023-00001-x")]


def test_link_targets_reads_url_and_body() -> None:
    item = _item(
        url="https://arxiv.org/abs/2601.01234",
        body="Also compare https://doi.org/10.1038/s41586-023-00001-x",
    )
    refs = link_targets(item)
    assert PaperRef(source="arxiv", external_id="2601.01234") in refs
    assert any(ref.doi == "10.1038/s41586-023-00001-x" for ref in refs)


def test_adapters_inherit_shared_link_targets() -> None:
    class Adapter(DiscourseLinkMixin):
        name = "mixin-adapter"

        def poll(self, since):  # noqa: ANN001
            del since
            return []

    item = _item(url="https://arxiv.org/pdf/2601.01234.pdf", body=None)
    assert Adapter().link_targets(item) == [PaperRef(source="arxiv", external_id="2601.01234")]


def test_resolved_item_writes_mention_with_resolved_by(
    isolated_database: Engine,
) -> None:
    from ai_researcher.db.models import metadata

    paper = metadata.tables["paper"]
    discourse_source = metadata.tables["discourse_source"]
    discourse_mention = metadata.tables["discourse_mention"]

    with isolated_database.begin() as connection:
        paper_id = connection.execute(
            insert(paper).values(title="Known paper", arxiv_id="2601.01234").returning(paper.c.id)
        ).scalar_one()
        source_id = connection.execute(
            insert(discourse_source)
            .values(name="reddit", kind="reddit", enabled=True)
            .returning(discourse_source.c.id)
        ).scalar_one()

        item = _item(url="https://arxiv.org/abs/2601.01234")
        item_id, mentions = store_item_with_mentions(connection, source_id=source_id, item=item)

        assert item_id is not None
        assert len(mentions) == 1
        assert mentions[0].paper_id == paper_id
        assert mentions[0].resolved_by == "arxiv"

        rows = connection.execute(
            select(discourse_mention.c.paper_id, discourse_mention.c.resolved_by).where(
                discourse_mention.c.discourse_item_id == item_id
            )
        ).all()
        assert rows == [(paper_id, "arxiv")]


def test_resolved_doi_writes_mention(
    isolated_database: Engine,
) -> None:
    from ai_researcher.db.models import metadata

    paper = metadata.tables["paper"]
    discourse_source = metadata.tables["discourse_source"]
    discourse_mention = metadata.tables["discourse_mention"]

    with isolated_database.begin() as connection:
        paper_id = connection.execute(
            insert(paper)
            .values(title="DOI paper", doi="10.1038/s41586-023-00001-x")
            .returning(paper.c.id)
        ).scalar_one()
        source_id = connection.execute(
            insert(discourse_source)
            .values(name="hackernews", kind="hackernews", enabled=True)
            .returning(discourse_source.c.id)
        ).scalar_one()

        item = _item(
            source="hackernews",
            external_id="123",
            url="https://doi.org/10.1038/s41586-023-00001-x",
        )
        item_id, mentions = store_item_with_mentions(connection, source_id=source_id, item=item)

        assert mentions[0].resolved_by == "doi"
        rows = (
            connection.execute(
                select(discourse_mention.c.resolved_by).where(
                    discourse_mention.c.discourse_item_id == item_id
                )
            )
            .scalars()
            .all()
        )
        assert rows == ["doi"]
        assert paper_id == mentions[0].paper_id


def test_no_reference_item_stored_without_mentions(
    isolated_database: Engine,
) -> None:
    from ai_researcher.db.models import metadata

    discourse_source = metadata.tables["discourse_source"]
    discourse_item = metadata.tables["discourse_item"]
    discourse_mention = metadata.tables["discourse_mention"]

    with isolated_database.begin() as connection:
        source_id = connection.execute(
            insert(discourse_source)
            .values(name="rss", kind="rss", enabled=True)
            .returning(discourse_source.c.id)
        ).scalar_one()

        item = _item(
            source="rss",
            external_id="post-1",
            url="https://blog.example.com/quantum-news",
            title="Community buzz with no paper link",
            body="Just vibes about quantum computing.",
        )
        item_id, mentions = store_item_with_mentions(connection, source_id=source_id, item=item)

        assert item_id is not None
        assert mentions == []
        stored = connection.execute(
            select(discourse_item.c.id).where(discourse_item.c.id == item_id)
        ).scalar_one()
        assert stored == item_id
        count = connection.execute(
            select(discourse_mention.c.id).where(discourse_mention.c.discourse_item_id == item_id)
        ).all()
        assert count == []


def test_unknown_paper_logs_and_writes_no_mention(
    isolated_database: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ai_researcher.db.models import metadata

    discourse_source = metadata.tables["discourse_source"]
    discourse_mention = metadata.tables["discourse_mention"]

    configure_logging(verbose=False)
    with isolated_database.begin() as connection:
        source_id = connection.execute(
            insert(discourse_source)
            .values(name="huggingface", kind="huggingface", enabled=True)
            .returning(discourse_source.c.id)
        ).scalar_one()

        item = _item(
            source="huggingface",
            external_id="hf-1",
            url="https://arxiv.org/abs/9999.99999",
            body="Unknown preprint 9999.99999",
        )
        with caplog.at_level(logging.INFO, logger=ROOT_LOGGER_NAME):
            item_id, mentions = store_item_with_mentions(connection, source_id=source_id, item=item)

        assert item_id is not None
        assert mentions == []
        assert (
            connection.execute(
                select(discourse_mention.c.id).where(
                    discourse_mention.c.discourse_item_id == item_id
                )
            ).all()
            == []
        )
        assert any(
            "9999.99999" in record.getMessage() and "unmatched" in record.getMessage().casefold()
            for record in caplog.records
        )


def test_registered_adapters_delegate_to_shared_link_targets() -> None:
    from ai_researcher.discourse import registry

    item = _item(url="https://arxiv.org/abs/2601.01234")
    for name in ("reddit", "hackernews", "rss_blogs", "huggingface"):
        refs = registry.get(name).link_targets(item)
        assert refs == [PaperRef(source="arxiv", external_id="2601.01234")], name
