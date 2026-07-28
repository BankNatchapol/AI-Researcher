"""Tests for per-paper extraction pipeline, resumability, and prompt versioning."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, delete, func, insert, select, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.db.models import (
    claim,
    dataset,
    method,
    metric,
    paper,
    paper_scope,
    result,
    tree_node,
)
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
    database_name = f"test_extraction_pipeline_{uuid.uuid4().hex}"
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


def _extraction_payload(node_ids: list[int], *, model: str = "codex", version: str = "1") -> dict:
    records: list[dict[str, Any]] = []
    for node_id in node_ids:
        records.extend(
            [
                {
                    "record_type": "claim",
                    "tree_node_id": node_id,
                    "claim_text": f"Claim at node {node_id}",
                    "normalized_text": f"claim at node {node_id}",
                    "claim_type": "fact",
                    "extraction_model": model,
                    "prompt_version": version,
                },
                {
                    "record_type": "method",
                    "tree_node_id": node_id,
                    "method_text": f"Method at node {node_id}",
                    "extraction_model": model,
                    "prompt_version": version,
                },
                {
                    "record_type": "result",
                    "tree_node_id": node_id,
                    "result_text": f"Result at node {node_id}",
                    "extraction_model": model,
                    "prompt_version": version,
                },
                {
                    "record_type": "dataset",
                    "tree_node_id": node_id,
                    "dataset_name": f"dataset-{node_id}",
                    "extraction_model": model,
                    "prompt_version": version,
                },
                {
                    "record_type": "metric",
                    "tree_node_id": node_id,
                    "metric_name": f"metric-{node_id}",
                    "object_value": "1%",
                    "extraction_model": model,
                    "prompt_version": version,
                },
            ]
        )
    return {"records": records}


def _seed_scope_with_valid_section_fks(engine: Engine) -> tuple[int, int, list[int], list[int]]:
    """Seed papers + sections + tree nodes with valid foreign keys."""
    from ai_researcher.db.models import section

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

        parsed_node_ids: list[int] = []
        parent_section_id: int | None = None
        for ordinal, path, title, body in (
            (0, "1", "Introduction", "Intro body."),
            (1, "1/1.1", "Methods", "Method body."),
            (2, "1/1.2", "Results", "Result body."),
        ):
            section_id = int(
                connection.execute(
                    insert(section)
                    .values(
                        paper_id=parsed_id,
                        parent_id=parent_section_id if ordinal > 0 else None,
                        section_path=path,
                        title=title,
                        ordinal=ordinal if ordinal == 0 else ordinal - 1,
                        page_start=ordinal + 1,
                        page_end=ordinal + 2,
                        body_text=body,
                    )
                    .returning(section.c.id)
                ).scalar_one()
            )
            if ordinal == 0:
                parent_section_id = section_id
            node_id = int(
                connection.execute(
                    insert(tree_node)
                    .values(
                        paper_id=parsed_id,
                        section_id=section_id,
                        parent_id=None if ordinal == 0 else parsed_node_ids[0],
                        node_path=path,
                        title=title,
                        summary=f"Summary {title}",
                        page_start=ordinal + 1,
                        page_end=ordinal + 2,
                        depth=0 if ordinal == 0 else 1,
                        tree_schema_version="1",
                        summary_model="codex",
                    )
                    .returning(tree_node.c.id)
                ).scalar_one()
            )
            parsed_node_ids.append(node_id)

        abs_section_id = int(
            connection.execute(
                insert(section)
                .values(
                    paper_id=abstract_id,
                    parent_id=None,
                    section_path="Abstract",
                    title="Abstract",
                    ordinal=0,
                    page_start=None,
                    page_end=None,
                    body_text="Only an abstract is available.",
                )
                .returning(section.c.id)
            ).scalar_one()
        )
        abstract_node_id = int(
            connection.execute(
                insert(tree_node)
                .values(
                    paper_id=abstract_id,
                    section_id=abs_section_id,
                    parent_id=None,
                    node_path="Abstract",
                    title="Abstract",
                    summary="Abstract summary.",
                    page_start=None,
                    page_end=None,
                    depth=0,
                    tree_schema_version="1",
                    summary_model="codex",
                )
                .returning(tree_node.c.id)
            ).scalar_one()
        )

    return parsed_id, abstract_id, parsed_node_ids, [abstract_node_id]


def test_extract_paper_batches_one_call_per_paper_not_per_node() -> None:
    from ai_researcher.extraction.pipeline import PaperExtractionInput, TreeNodeInput, extract_paper
    from ai_researcher.extraction.prompts import PROMPT_VERSION

    nodes = tuple(
        TreeNodeInput(
            id=node_id,
            node_path=f"1/{node_id}",
            title=f"Section {node_id}",
            summary=f"Summary {node_id}",
            page_start=1,
            page_end=2,
            depth=1,
            body_text=f"Body {node_id}",
        )
        for node_id in (101, 102, 103, 104, 105)
    )
    calls: list[tuple[str, dict | None]] = []

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        calls.append((job, schema))
        payload = json.loads(messages[-1]["content"])
        assert "nodes" not in payload
        groups = payload["section_groups"]
        node_ids = [node["tree_node_id"] for group in groups for node in group["nodes"]]
        return _extraction_payload(node_ids, version=PROMPT_VERSION)

    result = extract_paper(
        PaperExtractionInput(
            id=7,
            title="Many-node paper",
            abstract="Abstract.",
            parse_status="parsed",
            nodes=nodes,
        ),
        complete_fn=fake_complete,
        extraction_model="fixture-model",
        persist=False,
    )

    assert len(calls) == 1
    assert calls[0][0] == "extraction"
    assert calls[0][1] is not None
    assert result.claims == 5
    assert result.methods == 5
    assert result.results == 5
    assert result.datasets == 5
    assert result.metrics == 5
    assert result.failed is False


def test_extract_cli_clean_resume_prompt_bump_and_paper_failure(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.extraction import prompts
    from ai_researcher.llm import gateway

    parsed_id, abstract_id, parsed_nodes, abstract_nodes = _seed_scope_with_valid_section_fks(
        isolated_database
    )
    call_count = 0
    fail_paper_id: int | None = None

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        nonlocal call_count
        del schema
        assert job == "extraction"
        call_count += 1
        payload = json.loads(messages[-1]["content"])
        paper_payload = payload["paper"]
        node_ids = [
            node["tree_node_id"] for group in payload["section_groups"] for node in group["nodes"]
        ]
        if fail_paper_id is not None and int(paper_payload["id"]) == fail_paper_id:
            raise RuntimeError("simulated extraction failure")
        return _extraction_payload(node_ids, version=prompts.PROMPT_VERSION)

    monkeypatch.setattr(gateway, "complete", fake_complete)
    runner = CliRunner()

    first = runner.invoke(app, ["extract", "surface-codes"])
    assert first.exit_code == 0, first.output
    assert "claims=" in first.stdout
    assert "methods=" in first.stdout
    assert "results=" in first.stdout
    assert "datasets=" in first.stdout
    assert "metrics=" in first.stdout
    assert "extracted 2" in first.stdout
    assert "skipped 0" in first.stdout
    assert "failed 0" in first.stdout
    assert call_count == 2  # one call per paper, not per node

    with isolated_database.connect() as connection:
        claim_rows = connection.execute(select(claim)).mappings().all()
        method_rows = connection.execute(select(method)).mappings().all()
        result_rows = connection.execute(select(result)).mappings().all()
        dataset_rows = connection.execute(select(dataset)).mappings().all()
        metric_rows = connection.execute(select(metric)).mappings().all()

    assert len(claim_rows) == 4  # 3 parsed nodes + 1 abstract node
    assert len(method_rows) == 4
    assert len(result_rows) == 4
    assert len(dataset_rows) == 4
    assert len(metric_rows) == 4
    assert {row["paper_id"] for row in claim_rows} == {parsed_id, abstract_id}
    assert all(row["extraction_model"] for row in claim_rows)
    assert all(row["prompt_version"] == prompts.PROMPT_VERSION for row in claim_rows)
    assert all(row["extraction_model"] for row in method_rows)
    assert all(row["prompt_version"] == prompts.PROMPT_VERSION for row in method_rows)
    assert {row["tree_node_id"] for row in claim_rows} == set(parsed_nodes + abstract_nodes)

    # Resume: no new work.
    prior_calls = call_count
    second = runner.invoke(app, ["extract", "surface-codes"])
    assert second.exit_code == 0, second.output
    assert "extracted 0" in second.stdout
    assert "skipped 2" in second.stdout
    assert call_count == prior_calls

    # Prompt version bump re-extracts only papers whose rows are stale.
    monkeypatch.setattr(prompts, "PROMPT_VERSION", "2")
    call_count = 0
    third = runner.invoke(app, ["extract", "surface-codes"])
    assert third.exit_code == 0, third.output
    assert "extracted 2" in third.stdout
    assert "skipped 0" in third.stdout
    assert call_count == 2

    with isolated_database.connect() as connection:
        versions = {
            row["prompt_version"]
            for row in connection.execute(select(claim.c.prompt_version)).mappings().all()
        }
        claim_count = connection.execute(select(func.count()).select_from(claim)).scalar_one()
    assert versions == {"2"}
    assert claim_count == 4

    # Per-paper failure continues the run: wipe one paper's extractions, fail that paper.
    with isolated_database.begin() as connection:
        connection.execute(delete(claim).where(claim.c.paper_id == parsed_id))
        connection.execute(delete(method).where(method.c.paper_id == parsed_id))
        connection.execute(delete(result).where(result.c.paper_id == parsed_id))
        connection.execute(delete(dataset).where(dataset.c.paper_id == parsed_id))
        connection.execute(delete(metric).where(metric.c.paper_id == parsed_id))

    fail_paper_id = parsed_id
    call_count = 0
    fourth = runner.invoke(app, ["extract", "surface-codes"])
    assert fourth.exit_code == 0, fourth.output
    assert "failed 1" in fourth.stdout
    assert "skipped 1" in fourth.stdout or "extracted 0" in fourth.stdout


def test_prompt_version_constant_exists() -> None:
    from ai_researcher.extraction.prompts import PROMPT_VERSION

    assert isinstance(PROMPT_VERSION, str)
    assert PROMPT_VERSION


def test_every_persisted_record_type_carries_extraction_provenance(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.extraction import prompts
    from ai_researcher.llm import gateway

    _seed_scope_with_valid_section_fks(isolated_database)

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del schema
        assert job == "extraction"
        payload = json.loads(messages[-1]["content"])
        node_ids = [
            node["tree_node_id"] for group in payload["section_groups"] for node in group["nodes"]
        ]
        return _extraction_payload(node_ids, model="untrusted-model", version="stale")

    monkeypatch.setattr(gateway, "complete", fake_complete)

    completed = CliRunner().invoke(app, ["extract", "surface-codes"])

    assert completed.exit_code == 0, completed.output
    with isolated_database.connect() as connection:
        for extraction_table in (claim, method, result, dataset, metric):
            rows = connection.execute(
                select(
                    extraction_table.c.extraction_model,
                    extraction_table.c.prompt_version,
                )
            ).all()
            assert rows
            assert all(row.extraction_model == "codex" for row in rows)
            assert all(row.prompt_version == prompts.PROMPT_VERSION for row in rows)


def test_prompt_version_bump_reextracts_only_stale_papers(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.extraction import prompts
    from ai_researcher.llm import gateway

    parsed_id, abstract_id, _, _ = _seed_scope_with_valid_section_fks(isolated_database)
    called_paper_ids: list[int] = []

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del schema
        assert job == "extraction"
        payload = json.loads(messages[-1]["content"])
        called_paper_ids.append(int(payload["paper"]["id"]))
        node_ids = [
            node["tree_node_id"] for group in payload["section_groups"] for node in group["nodes"]
        ]
        return _extraction_payload(node_ids)

    monkeypatch.setattr(gateway, "complete", fake_complete)
    runner = CliRunner()
    initial = runner.invoke(app, ["extract", "surface-codes"])
    assert initial.exit_code == 0, initial.output

    with isolated_database.begin() as connection:
        for extraction_table in (claim, method, result, dataset, metric):
            connection.execute(
                update(extraction_table)
                .where(extraction_table.c.paper_id == abstract_id)
                .values(prompt_version="2")
            )

    monkeypatch.setattr(prompts, "PROMPT_VERSION", "2")
    called_paper_ids.clear()

    bumped = runner.invoke(app, ["extract", "surface-codes"])

    assert bumped.exit_code == 0, bumped.output
    assert "extracted 1" in bumped.stdout
    assert "skipped 1" in bumped.stdout
    assert called_paper_ids == [parsed_id]

    with isolated_database.connect() as connection:
        for extraction_table in (claim, method, result, dataset, metric):
            versions_by_paper = connection.execute(
                select(
                    extraction_table.c.paper_id,
                    extraction_table.c.prompt_version,
                )
            ).all()
            assert versions_by_paper
            assert {(row.paper_id, row.prompt_version) for row in versions_by_paper} == {
                (parsed_id, "2"),
                (abstract_id, "2"),
            }
