"""Tests for vectorless corpus shortlisting backends."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, insert, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from ai_researcher.db.models import paper, paper_scope, section, tree_node
from ai_researcher.db.models import scope as scope_table


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
    database_name = f"test_shortlist_{uuid.uuid4().hex}"
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


@pytest.fixture
def seeded_corpus(isolated_database: Engine) -> tuple[str, tuple[int, int, int]]:
    scope_name = "surface-codes"
    with isolated_database.begin() as connection:
        scope_id = int(
            connection.execute(
                insert(scope_table)
                .values(
                    name=scope_name,
                    description="Quantum error-correction literature",
                    include_terms=["surface code"],
                    exclude_terms=[],
                    categories=["quant-ph"],
                )
                .returning(scope_table.c.id)
            ).scalar_one()
        )
        title_match_id = int(
            connection.execute(
                insert(paper)
                .values(
                    title="Surface code threshold estimates",
                    abstract="A study of fault-tolerant architectures.",
                    parse_status="parsed",
                )
                .returning(paper.c.id)
            ).scalar_one()
        )
        abstract_match_id = int(
            connection.execute(
                insert(paper)
                .values(
                    title="Learning for fault tolerance",
                    abstract="A neural decoder improves quantum error correction.",
                    parse_status="parsed",
                )
                .returning(paper.c.id)
            ).scalar_one()
        )
        section_match_id = int(
            connection.execute(
                insert(paper)
                .values(
                    title="Logical gate constructions",
                    abstract="Methods for protected logical operations.",
                    parse_status="parsed",
                )
                .returning(paper.c.id)
            ).scalar_one()
        )

        paper_ids = (title_match_id, abstract_match_id, section_match_id)
        for paper_id in paper_ids:
            connection.execute(insert(paper_scope).values(paper_id=paper_id, scope_id=scope_id))

        section_bodies = {
            title_match_id: "Detailed numerical results for the threshold.",
            abstract_match_id: "Decoder training and evaluation details.",
            section_match_id: "A transversal CNOT construction preserves the code space.",
        }
        summaries = {
            title_match_id: "Reports surface-code threshold estimates.",
            abstract_match_id: "Studies learned decoders.",
            section_match_id: "Constructs protected logical gates.",
        }
        for paper_id in paper_ids:
            section_id = int(
                connection.execute(
                    insert(section)
                    .values(
                        paper_id=paper_id,
                        parent_id=None,
                        section_path="1",
                        title="Results",
                        ordinal=0,
                        page_start=1,
                        page_end=2,
                        body_text=section_bodies[paper_id],
                    )
                    .returning(section.c.id)
                ).scalar_one()
            )
            connection.execute(
                insert(tree_node).values(
                    paper_id=paper_id,
                    section_id=section_id,
                    parent_id=None,
                    node_path="1",
                    title="Results",
                    summary=summaries[paper_id],
                    page_start=1,
                    page_end=2,
                    depth=0,
                    tree_schema_version="fixture",
                    summary_model="fixture",
                )
            )

    return scope_name, paper_ids


def test_two_shortlist_implementations_are_registered_and_satisfy_protocol() -> None:
    from ai_researcher.retrieval import (
        PageIndexShortlist,
        PostgresFTSShortlist,
        Shortlist,
        registered_shortlist_backends,
    )

    registered = registered_shortlist_backends()

    assert registered == {
        "pageindex": PageIndexShortlist,
        "postgres_fts": PostgresFTSShortlist,
    }
    assert isinstance(PageIndexShortlist(), Shortlist)
    assert isinstance(PostgresFTSShortlist(), Shortlist)


def test_config_switches_both_backends_for_the_same_question(
    seeded_corpus: tuple[str, tuple[int, int, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.llm import gateway
    from ai_researcher.retrieval import shortlist

    scope_name, paper_ids = seeded_corpus
    relevant_id = paper_ids[0]
    calls: list[dict] = []

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        assert job == "shortlist"
        assert schema is not None
        payload = json.loads(messages[-1]["content"])
        calls.append(payload)
        assert payload["scope"] == scope_name
        assert payload["question"] == "surface code threshold"
        assert len(payload["candidates"]) == 3
        assert "transversal CNOT" not in messages[-1]["content"]
        return {"paper_ids": [relevant_id]}

    monkeypatch.setattr(gateway, "complete", fake_complete)
    monkeypatch.delenv("SHORTLIST_BACKEND", raising=False)
    default_result = shortlist(scope_name, "surface code threshold", limit=20)

    monkeypatch.setenv("SHORTLIST_BACKEND", "postgres_fts")
    fallback_result = shortlist(scope_name, "surface code threshold", limit=20)

    assert default_result == [relevant_id]
    assert fallback_result == [relevant_id]
    assert set(default_result + fallback_result) <= set(paper_ids)
    assert len(calls) == 1


def test_pageindex_shortlist_caps_model_selection_at_limit(
    seeded_corpus: tuple[str, tuple[int, int, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.llm import gateway
    from ai_researcher.retrieval import PageIndexShortlist

    scope_name, paper_ids = seeded_corpus

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del messages, schema
        assert job == "shortlist"
        return {"paper_ids": list(reversed(paper_ids))}

    monkeypatch.setattr(gateway, "complete", fake_complete)

    assert PageIndexShortlist().shortlist(scope_name, "logical gates", limit=2) == [
        paper_ids[2],
        paper_ids[1],
    ]


@pytest.mark.parametrize(
    ("question", "paper_position"),
    [
        ("surface code threshold", 0),
        ("neural decoder", 1),
        ("transversal CNOT", 2),
    ],
)
def test_postgres_fts_searches_title_abstract_and_section_body(
    seeded_corpus: tuple[str, tuple[int, int, int]],
    question: str,
    paper_position: int,
) -> None:
    from ai_researcher.retrieval import PostgresFTSShortlist

    scope_name, paper_ids = seeded_corpus

    result = PostgresFTSShortlist().shortlist(scope_name, question, limit=20)

    assert result
    assert result[0] == paper_ids[paper_position]
    assert set(result) <= set(paper_ids)


def test_fts_migration_adds_gin_indexes(isolated_database: Engine) -> None:
    with isolated_database.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname IN ('ix_paper_search_document', 'ix_section_search_document')
                """
            )
        ).all()

    assert {row.indexname for row in rows} == {
        "ix_paper_search_document",
        "ix_section_search_document",
    }
    assert all("USING gin" in row.indexdef for row in rows)
