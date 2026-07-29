"""Tests for per-paper extraction pipeline, resumability, and prompt versioning."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, delete, func, insert, select, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.db.models import (
    claim,
    claim_evidence,
    claim_extraction_observation,
    claim_score,
    dataset,
    method,
    metric,
    paper,
    paper_extraction_state,
    paper_scope,
    result,
    retrieval_trace,
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


def test_confidence_refreshes_when_evidence_and_trace_arrive_after_initial_score(
    isolated_database: Engine,
) -> None:
    """A score written by --no-link-evidence must not freeze incomplete inputs."""

    from ai_researcher.scoring.confidence import score_scope_confidence

    parsed_id, _abstract_id, parsed_nodes, _abstract_nodes = _seed_scope_with_valid_section_fks(
        isolated_database
    )
    initial_input_at = datetime(2026, 1, 1, tzinfo=UTC)
    initial_score_at = datetime(2026, 2, 1, tzinfo=UTC)
    linked_at = datetime(2026, 3, 1, tzinfo=UTC)
    traced_at = datetime(2026, 4, 1, tzinfo=UTC)

    with isolated_database.begin() as connection:
        scope_id = int(
            connection.execute(
                select(scope_table.c.id).where(scope_table.c.name == "surface-codes")
            ).scalar_one()
        )
        claim_id = int(
            connection.execute(
                insert(claim)
                .values(
                    paper_id=parsed_id,
                    tree_node_id=parsed_nodes[0],
                    claim_text="Intro body.",
                    normalized_text="intro body",
                    claim_type="fact",
                    extraction_model="codex",
                    prompt_version="1",
                    created_at=initial_input_at,
                )
                .returning(claim.c.id)
            ).scalar_one()
        )
        connection.execute(
            insert(claim_extraction_observation).values(
                claim_id=claim_id,
                paper_id=parsed_id,
                tree_node_id=parsed_nodes[0],
                claim_text="Intro body.",
                extraction_model="codex",
                prompt_version="1",
                recorded_at=initial_input_at,
            )
        )
        connection.execute(
            insert(paper_extraction_state).values(
                paper_id=parsed_id,
                extraction_model="codex",
                prompt_version="1",
                validation_accepted=1,
                validation_rejected=0,
                completed_at=initial_input_at,
            )
        )
        connection.execute(
            insert(claim_score).values(
                claim_id=claim_id,
                confidence=10,
                evidence_quality=0,
                rubric_version="pending-evidence-quality",
                scored_at=initial_score_at,
            )
        )

    assert score_scope_confidence("surface-codes").scored == 0

    with isolated_database.begin() as connection:
        connection.execute(
            insert(claim_evidence).values(
                claim_id=claim_id,
                tree_node_id=parsed_nodes[0],
                paper_id=parsed_id,
                stance="supports",
                rationale_text="Intro body.",
                is_direct=True,
                created_at=linked_at,
            )
        )
        connection.execute(
            insert(retrieval_trace).values(
                question="intro body",
                scope_id=scope_id,
                expanded_node_ids=parsed_nodes,
                selected_node_ids=[parsed_nodes[0]],
                nodes_expanded=len(parsed_nodes),
                stopped_reason="sufficient_evidence",
                created_at=traced_at,
            )
        )

    refreshed = score_scope_confidence("surface-codes")

    assert refreshed.scored == 1
    assert refreshed.scores[0].value > 10
    with isolated_database.connect() as connection:
        persisted_scores = connection.execute(
            select(claim_score.c.confidence)
            .where(claim_score.c.claim_id == claim_id)
            .order_by(claim_score.c.id)
        ).scalars()
        assert list(persisted_scores) == [10, refreshed.scores[0].value]


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
    from ai_researcher.scoring.confidence import score_scope_confidence

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
    assert score_scope_confidence("surface-codes").scored == 4

    with isolated_database.connect() as connection:
        claim_rows = connection.execute(select(claim)).mappings().all()
        observation_rows = connection.execute(select(claim_extraction_observation)).mappings().all()
        initial_score_count = connection.execute(
            select(func.count()).select_from(claim_score)
        ).scalar_one()
        method_rows = connection.execute(select(method)).mappings().all()
        result_rows = connection.execute(select(result)).mappings().all()
        dataset_rows = connection.execute(select(dataset)).mappings().all()
        metric_rows = connection.execute(select(metric)).mappings().all()

    assert len(claim_rows) == 4  # 3 parsed nodes + 1 abstract node
    assert len(observation_rows) == 4
    assert initial_score_count == 4
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
    assert score_scope_confidence("surface-codes").scored == 4

    with isolated_database.connect() as connection:
        versions = {
            row["prompt_version"]
            for row in connection.execute(select(claim.c.prompt_version)).mappings().all()
        }
        claim_count = connection.execute(select(func.count()).select_from(claim)).scalar_one()
        observation_versions = connection.execute(
            select(
                claim_extraction_observation.c.claim_id,
                claim_extraction_observation.c.prompt_version,
            )
        ).all()
        refreshed_score_count = connection.execute(
            select(func.count()).select_from(claim_score)
        ).scalar_one()
    assert versions == {"2"}
    assert claim_count == 4
    assert len(observation_versions) == 8
    assert {row.prompt_version for row in observation_versions} == {"1", "2"}
    assert refreshed_score_count == 8

    # Per-paper failure continues the run: wipe one paper's extractions, fail that paper.
    with isolated_database.begin() as connection:
        connection.execute(delete(claim).where(claim.c.paper_id == parsed_id))
        connection.execute(delete(method).where(method.c.paper_id == parsed_id))
        connection.execute(delete(result).where(result.c.paper_id == parsed_id))
        connection.execute(delete(dataset).where(dataset.c.paper_id == parsed_id))
        connection.execute(delete(metric).where(metric.c.paper_id == parsed_id))
        connection.execute(
            delete(paper_extraction_state).where(paper_extraction_state.c.paper_id == parsed_id)
        )

    fail_paper_id = parsed_id
    call_count = 0
    fourth = runner.invoke(app, ["extract", "surface-codes"])
    assert fourth.exit_code == 0, fourth.output
    assert "failed 1" in fourth.stdout
    assert "skipped 1" in fourth.stdout or "extracted 0" in fourth.stdout


def test_paper_failure_does_not_abort_remaining_stale_papers(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.llm import gateway

    parsed_id, abstract_id, _, abstract_nodes = _seed_scope_with_valid_section_fks(
        isolated_database
    )
    called_paper_ids: list[int] = []

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del schema
        assert job == "extraction"
        payload = json.loads(messages[-1]["content"])
        paper_id = int(payload["paper"]["id"])
        called_paper_ids.append(paper_id)
        if paper_id == parsed_id:
            raise RuntimeError("simulated first-paper failure")
        node_ids = [
            node["tree_node_id"] for group in payload["section_groups"] for node in group["nodes"]
        ]
        return _extraction_payload(node_ids)

    monkeypatch.setattr(gateway, "complete", fake_complete)

    completed = CliRunner().invoke(app, ["extract", "surface-codes"])

    assert completed.exit_code == 0, completed.output
    assert "extracted 1" in completed.stdout
    assert "failed 1" in completed.stdout
    assert called_paper_ids == [parsed_id, parsed_id, abstract_id]
    with isolated_database.connect() as connection:
        persisted = connection.execute(select(claim.c.paper_id, claim.c.tree_node_id)).all()
    assert {(row.paper_id, row.tree_node_id) for row in persisted} == {
        (abstract_id, abstract_nodes[0])
    }


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
        connection.execute(
            update(paper_extraction_state)
            .where(paper_extraction_state.c.paper_id == abstract_id)
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


def test_valid_empty_extraction_is_resumable(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.llm import gateway

    _seed_scope_with_valid_section_fks(isolated_database)
    call_count = 0

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        nonlocal call_count
        del messages, schema
        assert job == "extraction"
        call_count += 1
        return {"records": []}

    monkeypatch.setattr(gateway, "complete", fake_complete)
    runner = CliRunner()

    first = runner.invoke(app, ["extract", "surface-codes"])
    second = runner.invoke(app, ["extract", "surface-codes"])

    assert first.exit_code == 0, first.output
    assert "extracted 2" in first.stdout
    assert "failed 0" in first.stdout
    assert second.exit_code == 0, second.output
    assert "extracted 0" in second.stdout
    assert "skipped 2" in second.stdout
    assert call_count == 2


def test_all_rejected_output_does_not_replace_valid_extractions(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.extraction import prompts
    from ai_researcher.llm import gateway

    _seed_scope_with_valid_section_fks(isolated_database)
    reject_all = False

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del schema
        assert job == "extraction"
        payload = json.loads(messages[-1]["content"])
        if reject_all:
            return {
                "records": [
                    {
                        "record_type": "claim",
                        "tree_node_id": 999_999,
                        "claim_text": "Cross-paper claim",
                        "normalized_text": "cross-paper claim",
                        "claim_type": "fact",
                    }
                ]
            }
        node_ids = [
            node["tree_node_id"] for group in payload["section_groups"] for node in group["nodes"]
        ]
        return _extraction_payload(node_ids)

    monkeypatch.setattr(gateway, "complete", fake_complete)
    runner = CliRunner()
    initial = runner.invoke(app, ["extract", "surface-codes"])
    assert initial.exit_code == 0, initial.output

    with isolated_database.connect() as connection:
        original_claim_ids = set(connection.execute(select(claim.c.id)).scalars())

    reject_all = True
    monkeypatch.setattr(prompts, "PROMPT_VERSION", "2")
    bumped = runner.invoke(app, ["extract", "surface-codes"])

    assert bumped.exit_code == 0, bumped.output
    assert "extracted 0" in bumped.stdout
    assert "failed 2" in bumped.stdout
    with isolated_database.connect() as connection:
        assert set(connection.execute(select(claim.c.id)).scalars()) == original_claim_ids


def test_prompt_bump_preserves_claim_identity_and_dependents(
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
        return _extraction_payload(node_ids)

    monkeypatch.setattr(gateway, "complete", fake_complete)
    runner = CliRunner()
    initial = runner.invoke(app, ["extract", "surface-codes", "--no-score"])
    assert initial.exit_code == 0, initial.output

    with isolated_database.begin() as connection:
        original_claim = connection.execute(
            select(claim.c.id, claim.c.paper_id, claim.c.tree_node_id).order_by(claim.c.id)
        ).first()
        assert original_claim is not None
        connection.execute(
            insert(claim_evidence).values(
                claim_id=original_claim.id,
                tree_node_id=original_claim.tree_node_id,
                paper_id=original_claim.paper_id,
                stance="supports",
                rationale_text="Quoted support.",
                is_direct=True,
            )
        )
        connection.execute(
            insert(claim_score).values(
                claim_id=original_claim.id,
                confidence=80,
                evidence_quality=70,
                rubric_version="1",
            )
        )

    monkeypatch.setattr(prompts, "PROMPT_VERSION", "2")
    bumped = runner.invoke(app, ["extract", "surface-codes", "--no-score"])

    assert bumped.exit_code == 0, bumped.output
    with isolated_database.connect() as connection:
        refreshed_claim_id = connection.execute(
            select(claim.c.id).where(
                claim.c.paper_id == original_claim.paper_id,
                claim.c.tree_node_id == original_claim.tree_node_id,
            )
        ).scalar_one()
        assert refreshed_claim_id == original_claim.id
        assert (
            connection.execute(
                select(func.count())
                .select_from(claim_evidence)
                .where(claim_evidence.c.claim_id == original_claim.id)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(claim_score)
                .where(claim_score.c.claim_id == original_claim.id)
            ).scalar_one()
            == 1
        )


def test_reextraction_invalidates_identity_marker_when_value_changes_into_overlap(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for issue #46 rebuild 3.

    A claim's identity_checked_at marker previously survived reconciliation even
    when the reconciled value changed enough to newly overlap another
    already-checked claim -- canonicalize_scope() then silently skipped the pair
    (identity_checked_at remained set on both sides, so neither was "pending").
    Reconciliation must clear the marker when it rewrites a field the dedup
    prefilter matches on (predicate/object_value/unit), so the pair becomes
    eligible for comparison again.
    """

    from ai_researcher.extraction import prompts
    from ai_researcher.llm import gateway

    parsed_id, _abstract_id, parsed_node_ids, _abstract_node_ids = (
        _seed_scope_with_valid_section_fks(isolated_database)
    )
    node_a, node_b = parsed_node_ids[0], parsed_node_ids[1]

    identity_calls: list[list[tuple[int, int]]] = []
    claim_a_value = {"value": 0.20}

    def claim_record(node_id: int, *, value: float, version: str) -> dict[str, Any]:
        return {
            "record_type": "claim",
            "tree_node_id": node_id,
            "claim_text": f"Threshold at node {node_id} is {value}%.",
            "normalized_text": f"threshold at node {node_id}",
            "claim_type": "measurement",
            "predicate": "logical error threshold",
            "object_value": value,
            "unit": "%",
            "extraction_model": "codex",
            "prompt_version": version,
        }

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del schema
        payload = json.loads(messages[-1]["content"])
        if job == "extraction":
            requested_node_ids = {
                node["tree_node_id"]
                for group in payload["section_groups"]
                for node in group["nodes"]
            }
            # This scope has two papers; only the parsed paper's request should
            # produce the two claims under test. The abstract-only paper's
            # request must return no records rather than misattributed claims.
            if not requested_node_ids & {node_a, node_b}:
                return {"records": []}
            version = prompts.PROMPT_VERSION
            records = [
                claim_record(node_a, value=claim_a_value["value"], version=version),
                claim_record(node_b, value=1.0, version=version),
            ]
            return {"records": records}
        if job == "claim_identity":
            pairs = [
                (candidate["left"]["id"], candidate["right"]["id"])
                for candidate in payload["candidate_pairs"]
            ]
            identity_calls.append(pairs)
            return {
                "comparisons": [
                    {"left_id": left_id, "right_id": right_id, "same_claim": False}
                    for left_id, right_id in pairs
                ]
            }
        raise AssertionError(f"unexpected job: {job}")

    monkeypatch.setattr(gateway, "complete", fake_complete)
    runner = CliRunner()

    # Run 1: claim_a=0.20%, claim_b=1.0% -- outside the 5% overlap tolerance.
    # Prefilter finds no candidate pair; both claims still get marked checked.
    first = runner.invoke(app, ["extract", "surface-codes", "--no-link-evidence"])
    assert first.exit_code == 0, first.output
    assert "pairs=0" in first.output
    assert identity_calls == []

    with isolated_database.connect() as connection:
        checked_count = connection.execute(
            select(func.count())
            .select_from(claim)
            .where(claim.c.paper_id == parsed_id, claim.c.identity_checked_at.is_not(None))
        ).scalar_one()
        assert checked_count == 2

    # Run 2: prompt version bumps, re-extraction changes claim_a to 0.99% --
    # now within tolerance of claim_b's unchanged 1.0%. Without the fix,
    # claim_a's stale identity_checked_at (from run 1) suppresses the pair
    # entirely and canonicalize_scope() reports zero comparisons.
    monkeypatch.setattr(prompts, "PROMPT_VERSION", "2")
    claim_a_value["value"] = 0.99
    second = runner.invoke(app, ["extract", "surface-codes", "--no-link-evidence"])

    assert second.exit_code == 0, second.output
    assert "pairs=1" in second.output
    assert len(identity_calls) == 1
    assert len(identity_calls[0]) == 1


def test_reextraction_detaches_old_canonical_member_when_root_value_diverges(
    isolated_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An updated canonical root must not retain a now-incompatible member.

    Re-extraction can change a canonical root's identity-driving quantity while
    a preserved original still points at that root. Clearing only the root's
    identity_checked_at marker is insufficient: the old member remains hidden
    from identity loading and keeps an invalid canonical_claim_id. The existing
    group must be invalidated before the updated roots are canonicalized again.
    """

    from ai_researcher.extraction import prompts
    from ai_researcher.llm import gateway

    parsed_id, abstract_id, parsed_node_ids, abstract_node_ids = _seed_scope_with_valid_section_fks(
        isolated_database
    )
    root_node, new_match_node = parsed_node_ids[:2]
    old_member_node = abstract_node_ids[0]
    root_value = {"value": 1.0}
    identity_calls: list[list[tuple[int, int]]] = []

    def claim_record(
        node_id: int,
        *,
        normalized_text: str,
        value: float,
    ) -> dict[str, Any]:
        return {
            "record_type": "claim",
            "tree_node_id": node_id,
            "claim_text": f"{normalized_text} at {value}%.",
            "normalized_text": normalized_text,
            "claim_type": "measurement",
            "predicate": "logical error threshold",
            "object_value": value,
            "unit": "%",
            "extraction_model": "codex",
            "prompt_version": prompts.PROMPT_VERSION,
        }

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del schema
        payload = json.loads(messages[-1]["content"])
        if job == "extraction":
            requested_node_ids = {
                node["tree_node_id"]
                for group in payload["section_groups"]
                for node in group["nodes"]
            }
            records = []
            if root_node in requested_node_ids:
                records.extend(
                    [
                        claim_record(
                            root_node,
                            normalized_text="root threshold",
                            value=root_value["value"],
                        ),
                        claim_record(
                            new_match_node,
                            normalized_text="new matching threshold",
                            value=2.0,
                        ),
                    ]
                )
            if old_member_node in requested_node_ids:
                records.append(
                    claim_record(
                        old_member_node,
                        normalized_text="old member threshold",
                        value=1.0,
                    )
                )
            return {"records": records}
        if job == "claim_identity":
            pairs = [
                (candidate["left"]["id"], candidate["right"]["id"])
                for candidate in payload["candidate_pairs"]
            ]
            identity_calls.append(pairs)
            return {
                "comparisons": [
                    {"left_id": left_id, "right_id": right_id, "same_claim": True}
                    for left_id, right_id in pairs
                ]
            }
        raise AssertionError(f"unexpected job: {job}")

    monkeypatch.setattr(gateway, "complete", fake_complete)
    runner = CliRunner()

    # Run 1: the root and old member are both 1%; the 2% claim is distinct.
    first = runner.invoke(app, ["extract", "surface-codes", "--no-link-evidence"])
    assert first.exit_code == 0, first.output
    assert "pairs=1" in first.output

    with isolated_database.connect() as connection:
        initial_rows = {
            int(row.tree_node_id): row
            for row in connection.execute(
                select(
                    claim.c.id,
                    claim.c.tree_node_id,
                    claim.c.canonical_claim_id,
                )
            )
        }
    root_id = int(initial_rows[root_node].id)
    new_match_id = int(initial_rows[new_match_node].id)
    old_member_id = int(initial_rows[old_member_node].id)
    assert initial_rows[root_node].canonical_claim_id is None
    assert initial_rows[new_match_node].canonical_claim_id is None
    assert initial_rows[old_member_node].canonical_claim_id == root_id
    assert identity_calls == [[(root_id, old_member_id)]]

    # Canonicalization consolidates evidence from both contributing papers onto
    # the canonical row. Invalidating the group must restore each paper's
    # evidence to its preserved original rather than leaving the old member
    # evidence attached to a proposition that is about to change.
    with isolated_database.begin() as connection:
        connection.execute(
            insert(claim_evidence),
            [
                {
                    "claim_id": root_id,
                    "tree_node_id": root_node,
                    "paper_id": parsed_id,
                    "stance": "supports",
                    "rationale_text": "Root-paper support.",
                    "is_direct": True,
                },
                {
                    "claim_id": root_id,
                    "tree_node_id": old_member_node,
                    "paper_id": abstract_id,
                    "stance": "supports",
                    "rationale_text": "Member-paper support.",
                    "is_direct": True,
                },
            ],
        )

    # Run 2: the canonical root moves to 2%. It should merge with the existing
    # 2% root, while the preserved 1% original must be detached because it no
    # longer overlaps the updated canonical proposition.
    monkeypatch.setattr(prompts, "PROMPT_VERSION", "2")
    root_value["value"] = 2.0
    second = runner.invoke(app, ["extract", "surface-codes", "--no-link-evidence"])

    assert second.exit_code == 0, second.output
    assert "pairs=1" in second.output
    assert identity_calls == [[(root_id, old_member_id)], [(root_id, new_match_id)]]

    with isolated_database.connect() as connection:
        final_rows = {
            int(row.id): row
            for row in connection.execute(
                select(
                    claim.c.id,
                    claim.c.object_value,
                    claim.c.canonical_claim_id,
                )
            )
        }
    assert final_rows[root_id].canonical_claim_id is None
    assert final_rows[new_match_id].canonical_claim_id == root_id
    assert final_rows[old_member_id].object_value == 1.0
    assert final_rows[old_member_id].canonical_claim_id is None

    with isolated_database.connect() as connection:
        evidence_by_paper = {
            int(row.paper_id): int(row.claim_id)
            for row in connection.execute(
                select(claim_evidence.c.paper_id, claim_evidence.c.claim_id)
            )
        }
    assert evidence_by_paper == {
        parsed_id: root_id,
        abstract_id: old_member_id,
    }
