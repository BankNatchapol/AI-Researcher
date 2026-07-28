"""Integration tests for the Phase 3 extraction, evidence, and dual-score schema."""

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, insert, inspect, select
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import DatabaseError, SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app

EXTRACTION_TABLES = ("claim", "method", "result", "dataset", "metric")

CLAIM_COLUMNS = {
    "id",
    "paper_id",
    "tree_node_id",
    "claim_text",
    "normalized_text",
    "claim_type",
    "subject",
    "predicate",
    "object_value",
    "unit",
    "canonical_claim_id",
    "identity_checked_at",
    "extraction_model",
    "prompt_version",
    "created_at",
}
METHOD_COLUMNS = {
    "id",
    "paper_id",
    "tree_node_id",
    "method_text",
    "extraction_model",
    "prompt_version",
    "created_at",
}
RESULT_COLUMNS = {
    "id",
    "paper_id",
    "tree_node_id",
    "result_text",
    "extraction_model",
    "prompt_version",
    "created_at",
}
DATASET_COLUMNS = {
    "id",
    "paper_id",
    "tree_node_id",
    "dataset_name",
    "description",
    "extraction_model",
    "prompt_version",
    "created_at",
}
METRIC_COLUMNS = {
    "id",
    "paper_id",
    "tree_node_id",
    "metric_name",
    "object_value",
    "unit",
    "extraction_model",
    "prompt_version",
    "created_at",
}
CLAIM_EVIDENCE_COLUMNS = {
    "id",
    "claim_id",
    "tree_node_id",
    "paper_id",
    "stance",
    "rationale_text",
    "created_at",
}
CLAIM_SCORE_COLUMNS = {
    "id",
    "claim_id",
    "confidence",
    "evidence_quality",
    "rubric_version",
    "scored_at",
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
    database_name = f"test_extraction_schema_{uuid.uuid4().hex}"
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


def _seed_paper_and_tree_node(connection) -> tuple[int, int]:
    from ai_researcher.db.models import metadata

    paper = metadata.tables["paper"]
    section = metadata.tables["section"]
    tree_node = metadata.tables["tree_node"]

    paper_id = connection.execute(
        insert(paper).values(title="Extraction schema paper").returning(paper.c.id)
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
    return paper_id, tree_node_id


def test_models_define_extraction_tables() -> None:
    from ai_researcher.db.models import metadata

    assert set(metadata.tables["claim"].columns.keys()) == CLAIM_COLUMNS
    assert set(metadata.tables["method"].columns.keys()) == METHOD_COLUMNS
    assert set(metadata.tables["result"].columns.keys()) == RESULT_COLUMNS
    assert set(metadata.tables["dataset"].columns.keys()) == DATASET_COLUMNS
    assert set(metadata.tables["metric"].columns.keys()) == METRIC_COLUMNS
    assert set(metadata.tables["claim_evidence"].columns.keys()) == CLAIM_EVIDENCE_COLUMNS
    assert set(metadata.tables["claim_score"].columns.keys()) == CLAIM_SCORE_COLUMNS

    for table_name in EXTRACTION_TABLES:
        table = metadata.tables[table_name]
        assert table.c.paper_id.nullable is False
        assert table.c.tree_node_id.nullable is False
        assert {fk.target_fullname for fk in table.c.paper_id.foreign_keys} == {"paper.id"}
        assert {fk.target_fullname for fk in table.c.tree_node_id.foreign_keys} == {"tree_node.id"}

    claim_score = metadata.tables["claim_score"]
    assert claim_score.c.confidence.nullable is False
    assert claim_score.c.evidence_quality.nullable is False
    assert "combined_score" not in claim_score.columns
    assert "score" not in claim_score.columns


def test_extraction_migration_rejects_null_tree_node_and_invalid_stance(
    isolated_database: Engine,
) -> None:
    runner = CliRunner()

    first_run = runner.invoke(app, ["db", "migrate"])
    second_run = runner.invoke(app, ["db", "migrate"])

    assert first_run.exit_code == 0, first_run.output
    assert "Applied migration 0005_extraction" in first_run.output
    assert second_run.exit_code == 0, second_run.output
    assert "already up to date" in second_run.output

    database_inspector = inspect(isolated_database)
    assert {column["name"] for column in database_inspector.get_columns("claim")} == CLAIM_COLUMNS
    assert {column["name"] for column in database_inspector.get_columns("method")} == METHOD_COLUMNS
    assert {column["name"] for column in database_inspector.get_columns("result")} == RESULT_COLUMNS
    assert {
        column["name"] for column in database_inspector.get_columns("dataset")
    } == DATASET_COLUMNS
    assert {column["name"] for column in database_inspector.get_columns("metric")} == METRIC_COLUMNS
    assert {
        column["name"] for column in database_inspector.get_columns("claim_evidence")
    } == CLAIM_EVIDENCE_COLUMNS
    assert {
        column["name"] for column in database_inspector.get_columns("claim_score")
    } == CLAIM_SCORE_COLUMNS

    claim_score_columns = {
        column["name"]: column for column in database_inspector.get_columns("claim_score")
    }
    assert claim_score_columns["confidence"]["nullable"] is False
    assert claim_score_columns["evidence_quality"]["nullable"] is False

    from ai_researcher.db.models import metadata

    claim = metadata.tables["claim"]
    method = metadata.tables["method"]
    result = metadata.tables["result"]
    dataset = metadata.tables["dataset"]
    metric = metadata.tables["metric"]
    claim_evidence = metadata.tables["claim_evidence"]
    claim_score = metadata.tables["claim_score"]

    with isolated_database.begin() as connection:
        paper_id, tree_node_id = _seed_paper_and_tree_node(connection)

        null_anchor_inserts = (
            insert(claim).values(
                paper_id=paper_id,
                tree_node_id=None,
                claim_text="Threshold is 1%",
                normalized_text="threshold is 1%",
                claim_type="quantitative",
                extraction_model="test-model",
                prompt_version="1",
            ),
            insert(method).values(
                paper_id=paper_id,
                tree_node_id=None,
                method_text="surface code decoding",
                extraction_model="test-model",
                prompt_version="1",
            ),
            insert(result).values(
                paper_id=paper_id,
                tree_node_id=None,
                result_text="logical error rate decreased",
                extraction_model="test-model",
                prompt_version="1",
            ),
            insert(dataset).values(
                paper_id=paper_id,
                tree_node_id=None,
                dataset_name="SurfaceBench",
                extraction_model="test-model",
                prompt_version="1",
            ),
            insert(metric).values(
                paper_id=paper_id,
                tree_node_id=None,
                metric_name="logical_error_rate",
                extraction_model="test-model",
                prompt_version="1",
            ),
        )
        for statement in null_anchor_inserts:
            with pytest.raises(DatabaseError), connection.begin_nested():
                connection.execute(statement)

        claim_id = connection.execute(
            insert(claim)
            .values(
                paper_id=paper_id,
                tree_node_id=tree_node_id,
                claim_text="Threshold is 1%",
                normalized_text="threshold is 1%",
                claim_type="quantitative",
                subject="surface code",
                predicate="has_threshold",
                object_value=1.0,
                unit="%",
                extraction_model="test-model",
                prompt_version="1",
            )
            .returning(claim.c.id)
        ).scalar_one()

        with pytest.raises(DatabaseError), connection.begin_nested():
            connection.execute(
                insert(claim_evidence).values(
                    claim_id=claim_id,
                    tree_node_id=tree_node_id,
                    paper_id=paper_id,
                    stance="agrees",
                    rationale_text="quoted rationale",
                )
            )

        connection.execute(
            insert(claim_evidence).values(
                claim_id=claim_id,
                tree_node_id=tree_node_id,
                paper_id=paper_id,
                stance="supports",
                rationale_text="quoted rationale",
            )
        )
        connection.execute(
            insert(claim_score).values(
                claim_id=claim_id,
                confidence=80,
                evidence_quality=70,
                rubric_version="1",
            )
        )

        stored = connection.execute(
            select(claim_score.c.confidence, claim_score.c.evidence_quality).where(
                claim_score.c.claim_id == claim_id
            )
        ).one()
        assert stored == (80, 70)
