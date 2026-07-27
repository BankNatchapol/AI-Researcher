"""Tests for per-paper tree construction, persistence, and caching."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert, select, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.db.models import paper, paper_scope, section, tree_node
from ai_researcher.db.models import scope as scope_table

FIXTURES = Path(__file__).parent / "fixtures"


def _summary_response(section_ids: list[int], *, long_section_id: int | None = None) -> dict:
    long_summary = " ".join(f"word-{number}" for number in range(75))
    return {
        "summaries": [
            {
                "section_id": section_id,
                "summary": long_summary
                if section_id == long_section_id
                else f"Summary for section {section_id}.",
            }
            for section_id in section_ids
        ]
    }


def test_build_tree_batches_one_gateway_call_and_preserves_section_anchors() -> None:
    from ai_researcher.trees.build import PaperTreeInput, SectionTreeInput, build_tree

    sections = (
        SectionTreeInput(
            id=11,
            parent_id=None,
            section_path="1",
            title="Introduction",
            ordinal=0,
            page_start=2,
            page_end=3,
            body_text="Introductory evidence.",
        ),
        SectionTreeInput(
            id=12,
            parent_id=11,
            section_path="1/1.1",
            title="Threshold estimate",
            ordinal=0,
            page_start=3,
            page_end=5,
            body_text="A detailed threshold estimate.",
        ),
        SectionTreeInput(
            id=13,
            parent_id=11,
            section_path="1/1.2",
            title="Limitations",
            ordinal=1,
            page_start=5,
            page_end=6,
            body_text="Known limitations.",
        ),
    )
    calls: list[tuple[list[dict], str, dict | None]] = []

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        calls.append((messages, job, schema))
        return _summary_response([11, 12, 13], long_section_id=12)

    nodes = build_tree(
        PaperTreeInput(
            id=7,
            title="Surface-code thresholds",
            abstract="Abstract.",
            parse_status="parsed",
            sections=sections,
        ),
        complete_fn=fake_complete,
        summary_model="fixture-model",
    )

    assert len(calls) == 1
    assert calls[0][1] == "node_summary"
    assert calls[0][2] is not None
    assert len(nodes) == len(sections)
    assert [node.section_id for node in nodes] == [11, 12, 13]
    assert [node.node_path for node in nodes] == ["1", "1/1.1", "1/1.2"]
    assert [(node.page_start, node.page_end) for node in nodes] == [(2, 3), (3, 5), (5, 6)]
    assert nodes[1].parent_section_id == 11
    assert all(len(node.summary.split()) <= 60 for node in nodes)
    assert {node.summary_model for node in nodes} == {"fixture-model"}


def test_six_level_tree_is_flattened_at_depth_four_without_losing_original_path() -> None:
    from ai_researcher.trees.build import PaperTreeInput, SectionTreeInput, build_tree

    records = json.loads((FIXTURES / "deep-sections.json").read_text(encoding="utf-8"))
    sections = tuple(SectionTreeInput(**record) for record in records)
    calls = 0

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        nonlocal calls
        del messages, schema
        calls += 1
        assert job == "node_summary"
        return _summary_response([record["id"] for record in records])

    nodes = build_tree(
        PaperTreeInput(
            id=8,
            title="Deep paper",
            abstract=None,
            parse_status="parsed",
            sections=sections,
        ),
        complete_fn=fake_complete,
        summary_model="fixture-model",
    )

    assert calls == 1
    assert [node.depth for node in nodes] == [0, 1, 2, 3, 4, 4]
    assert nodes[4].parent_section_id == 4
    assert nodes[5].parent_section_id == 4
    assert nodes[5].node_path == records[5]["section_path"]


def test_tree_version_staleness_compares_schema_and_summary_model() -> None:
    from ai_researcher.trees.version import TREE_SCHEMA_VERSION, TreeVersionState, is_stale

    assert is_stale(None, summary_model="codex")
    assert not is_stale(
        TreeVersionState(
            tree_schema_version=TREE_SCHEMA_VERSION,
            summary_model="codex",
        ),
        summary_model="codex",
    )
    assert is_stale(
        TreeVersionState(
            tree_schema_version="old-schema",
            summary_model="codex",
        ),
        summary_model="codex",
    )
    assert is_stale(
        TreeVersionState(
            tree_schema_version=TREE_SCHEMA_VERSION,
            summary_model="claude",
        ),
        summary_model="codex",
    )


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
    database_name = f"test_tree_builder_{uuid.uuid4().hex}"
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


def _seed_scope_with_parsed_and_abstract_papers(engine: Engine) -> tuple[int, int]:
    with engine.begin() as connection:
        scope_id = int(
            connection.execute(
                insert(scope_table)
                .values(
                    name="surface-codes",
                    description="Surface-code literature",
                    include_terms=["surface code"],
                    exclude_terms=[],
                    categories=["quant-ph"],
                    per_source_limit=10,
                )
                .returning(scope_table.c.id)
            ).scalar_one()
        )
        parsed_id = int(
            connection.execute(
                insert(paper)
                .values(title="Parsed paper", abstract="Parsed abstract.", parse_status="parsed")
                .returning(paper.c.id)
            ).scalar_one()
        )
        abstract_id = int(
            connection.execute(
                insert(paper)
                .values(
                    title="Abstract-only paper",
                    abstract="Only an abstract is available.",
                    parse_status="abstract_only",
                )
                .returning(paper.c.id)
            ).scalar_one()
        )
        for paper_id in (parsed_id, abstract_id):
            connection.execute(insert(paper_scope).values(paper_id=paper_id, scope_id=scope_id))

        root_id = int(
            connection.execute(
                insert(section)
                .values(
                    paper_id=parsed_id,
                    parent_id=None,
                    section_path="1",
                    title="Results",
                    ordinal=0,
                    page_start=4,
                    page_end=5,
                    body_text="Reported results.",
                )
                .returning(section.c.id)
            ).scalar_one()
        )
        connection.execute(
            insert(section).values(
                paper_id=parsed_id,
                parent_id=root_id,
                section_path="1/1.1",
                title="Threshold",
                ordinal=0,
                page_start=5,
                page_end=7,
                body_text="Threshold evidence.",
            )
        )
    return parsed_id, abstract_id


def test_index_cli_builds_and_then_skips_current_per_paper_trees(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.llm import gateway

    parsed_id, abstract_id = _seed_scope_with_parsed_and_abstract_papers(isolated_database)
    calls: list[list[int]] = []

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del schema
        assert job == "node_summary"
        payload = json.loads(messages[-1]["content"])
        section_ids = [item["section_id"] for item in payload["sections"]]
        calls.append(section_ids)
        return _summary_response(section_ids)

    monkeypatch.setattr(gateway, "complete", fake_complete)
    runner = CliRunner()

    first = runner.invoke(app, ["index", "surface-codes"])
    second = runner.invoke(app, ["index", "surface-codes"])

    assert first.exit_code == 0, first.output
    assert "built 2" in first.stdout
    assert "skipped 0" in first.stdout
    assert "failed 0" in first.stdout
    assert second.exit_code == 0, second.output
    assert "built 0" in second.stdout
    assert "skipped 2" in second.stdout
    assert len(calls) == 2

    with isolated_database.connect() as connection:
        rows = (
            connection.execute(
                select(
                    tree_node.c.paper_id,
                    tree_node.c.section_id,
                    tree_node.c.node_path,
                    tree_node.c.page_start,
                    tree_node.c.page_end,
                    tree_node.c.summary,
                    section.c.paper_id.label("section_paper_id"),
                    section.c.section_path,
                    section.c.title,
                ).join(section, section.c.id == tree_node.c.section_id)
            )
            .mappings()
            .all()
        )

    assert len(rows) == 3
    assert {row["paper_id"] for row in rows} == {parsed_id, abstract_id}
    assert all(row["paper_id"] == row["section_paper_id"] for row in rows)
    assert all(row["node_path"] == row["section_path"] for row in rows)
    assert all(len(row["summary"].split()) <= 60 for row in rows)
    parsed_rows = [row for row in rows if row["paper_id"] == parsed_id]
    assert [(row["page_start"], row["page_end"]) for row in parsed_rows] == [(4, 5), (5, 7)]
    abstract_row = next(row for row in rows if row["paper_id"] == abstract_id)
    assert abstract_row["title"] == "Abstract"
    assert abstract_row["node_path"] == "Abstract"


def test_index_rebuilds_only_the_paper_with_a_stale_tree_version(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.llm import gateway

    parsed_id, _ = _seed_scope_with_parsed_and_abstract_papers(isolated_database)
    calls: list[list[int]] = []

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del schema
        assert job == "node_summary"
        payload = json.loads(messages[-1]["content"])
        section_ids = [item["section_id"] for item in payload["sections"]]
        calls.append(section_ids)
        return _summary_response(section_ids)

    monkeypatch.setattr(gateway, "complete", fake_complete)
    runner = CliRunner()

    first = runner.invoke(app, ["index", "surface-codes"])
    with isolated_database.begin() as connection:
        connection.execute(
            update(tree_node)
            .where(tree_node.c.paper_id == parsed_id)
            .values(tree_schema_version="stale-schema")
        )
    second = runner.invoke(app, ["index", "surface-codes"])

    assert first.exit_code == 0, first.output
    assert "built 2" in first.stdout
    assert second.exit_code == 0, second.output
    assert "built 1" in second.stdout
    assert "skipped 1" in second.stdout
    assert "failed 0" in second.stdout
    assert len(calls) == 3
    assert len(calls[-1]) == 2


def test_index_continues_after_one_paper_summary_failure(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.llm import gateway

    _seed_scope_with_parsed_and_abstract_papers(isolated_database)
    attempts = 0

    def flaky_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        nonlocal attempts
        del schema
        assert job == "node_summary"
        attempts += 1
        if attempts == 1:
            raise RuntimeError("summary backend unavailable")
        payload = json.loads(messages[-1]["content"])
        return _summary_response([item["section_id"] for item in payload["sections"]])

    monkeypatch.setattr(gateway, "complete", flaky_complete)

    result = CliRunner().invoke(app, ["index", "surface-codes"])

    assert result.exit_code == 0, result.output
    assert "built 1" in result.stdout
    assert "failed 1" in result.stdout
    assert attempts == 2
