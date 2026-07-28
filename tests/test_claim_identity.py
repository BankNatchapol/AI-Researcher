"""Tests for prefiltered, passage-preserving claim canonicalization."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner


def _pg8000_url(url: str):
    return make_url(url).set(drivername="postgresql+pg8000")


@pytest.fixture
def identity_database_url() -> str:
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
def identity_database(
    identity_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Engine]:
    database_name = f"test_claim_identity_{uuid.uuid4().hex}"
    admin_engine = create_engine(
        _pg8000_url(identity_database_url),
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

    scoped_url = make_url(identity_database_url).set(database=database_name)
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


def test_prefilter_requires_type_metric_and_overlapping_normalized_quantity() -> None:
    from ai_researcher.evidence.identity import prefilter_pairs

    claims = [
        {
            "id": 1,
            "paper_id": 101,
            "claim_type": "measurement",
            "predicate": "logical error rate",
            "object_value": 1.0,
            "unit": "%",
        },
        {
            "id": 2,
            "paper_id": 202,
            "claim_type": "measurement",
            "predicate": "Logical Error Rate",
            "object_value": 0.01,
            "unit": None,
        },
        {
            "id": 3,
            "paper_id": 303,
            "claim_type": "measurement",
            "predicate": "logical error rate",
            "object_value": 0.2,
            "unit": None,
        },
        {
            "id": 4,
            "paper_id": 404,
            "claim_type": "forecast",
            "predicate": "logical error rate",
            "object_value": 0.01,
            "unit": None,
        },
        {
            "id": 5,
            "paper_id": 505,
            "claim_type": "measurement",
            "predicate": "fidelity",
            "object_value": 0.01,
            "unit": None,
        },
        {
            "id": 6,
            "paper_id": 606,
            "claim_type": "measurement",
            "predicate": "logical error rate",
            "object_value": 0.01,
            "unit": "seconds",
        },
    ]

    pairs = prefilter_pairs(claims)

    assert [(pair.left["id"], pair.right["id"]) for pair in pairs] == [(1, 2)]


def test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call() -> None:
    from ai_researcher.evidence.identity import canonicalize, prefilter_pairs

    claims = [
        {
            "id": 1,
            "paper_id": 101,
            "claim_text": "The decoder lowered logical error rate to one percent.",
            "normalized_text": "decoder lowers logical error rate",
            "claim_type": "measurement",
            "predicate": "logical error rate",
            "object_value": 1.0,
            "unit": "%",
        },
        {
            "id": 2,
            "paper_id": 202,
            "claim_text": "Logical errors fell to 0.01 with the decoder.",
            "normalized_text": "decoder reduces logical errors",
            "claim_type": "measurement",
            "predicate": "logical error rate",
            "object_value": 0.01,
            "unit": None,
        },
        {
            "id": 3,
            "paper_id": 303,
            "claim_text": "The decoder lowered logical error rate to twenty percent.",
            "normalized_text": "decoder lowers logical error rate",
            "claim_type": "measurement",
            "predicate": "logical error rate",
            "object_value": 0.2,
            "unit": None,
        },
        {
            "id": 4,
            "paper_id": 404,
            "claim_text": "The decoder ran for 0.01 seconds.",
            "normalized_text": "decoder runtime",
            "claim_type": "measurement",
            "predicate": "logical error rate",
            "object_value": 0.01,
            "unit": "seconds",
        },
    ]
    pairs = prefilter_pairs(claims)
    model_payloads: list[dict[str, Any]] = []

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        assert job == "claim_identity"
        assert schema is not None
        payload = json.loads(messages[-1]["content"])
        model_payloads.append(payload)
        return {
            "comparisons": [
                {
                    "left_id": 1,
                    "right_id": 2,
                    "same_claim": True,
                }
            ]
        }

    class MemoryIdentityStore:
        def __init__(self) -> None:
            self.groups: list[Any] = []

        def save_canonical_groups(self, groups: list[Any]) -> None:
            self.groups = list(groups)

    store = MemoryIdentityStore()
    result = canonicalize(pairs, complete_fn=fake_complete, store=store)

    assert len(model_payloads) == 1
    assert [
        (candidate["left"]["id"], candidate["right"]["id"])
        for candidate in model_payloads[0]["candidate_pairs"]
    ] == [(1, 2)]
    assert [(group.canonical_id, group.claim_ids) for group in store.groups] == [(1, (1, 2))]
    assert result.pairs_compared == 1
    assert result.merged_claims == 1


def test_canonicalize_preserves_original_claims_and_repoints_all_evidence(
    identity_database: Engine,
) -> None:
    from ai_researcher.db.models import (
        claim,
        claim_evidence,
        paper,
        paper_scope,
        section,
        tree_node,
    )
    from ai_researcher.db.models import scope as scope_table
    from ai_researcher.evidence.identity import (
        PostgresClaimIdentityStore,
        canonicalize_scope,
    )

    with identity_database.begin() as connection:
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
        claim_rows: list[dict[str, Any]] = []
        for paper_number, text, normalized, value, unit in (
            (
                1,
                "The decoder lowered logical error rate to one percent.",
                "decoder lowers logical error rate",
                1.0,
                "%",
            ),
            (
                2,
                "Logical errors fell to 0.01 with the decoder.",
                "decoder reduces logical errors",
                0.01,
                None,
            ),
        ):
            paper_id = int(
                connection.execute(
                    insert(paper)
                    .values(title=f"Paper {paper_number}", parse_status="parsed")
                    .returning(paper.c.id)
                ).scalar_one()
            )
            connection.execute(insert(paper_scope).values(paper_id=paper_id, scope_id=scope_id))
            section_id = int(
                connection.execute(
                    insert(section)
                    .values(
                        paper_id=paper_id,
                        section_path="Results",
                        ordinal=0,
                        body_text=text,
                    )
                    .returning(section.c.id)
                ).scalar_one()
            )
            node_id = int(
                connection.execute(
                    insert(tree_node)
                    .values(
                        paper_id=paper_id,
                        section_id=section_id,
                        node_path="Results",
                        summary=text,
                        depth=0,
                        tree_schema_version="1",
                        summary_model="codex",
                    )
                    .returning(tree_node.c.id)
                ).scalar_one()
            )
            claim_id = int(
                connection.execute(
                    insert(claim)
                    .values(
                        paper_id=paper_id,
                        tree_node_id=node_id,
                        claim_text=text,
                        normalized_text=normalized,
                        claim_type="measurement",
                        predicate="logical error rate",
                        object_value=value,
                        unit=unit,
                        extraction_model="codex",
                        prompt_version="1",
                    )
                    .returning(claim.c.id)
                ).scalar_one()
            )
            connection.execute(
                insert(claim_evidence).values(
                    claim_id=claim_id,
                    tree_node_id=node_id,
                    paper_id=paper_id,
                    stance="supports",
                    rationale_text=text,
                )
            )
            claim_rows.append(
                {
                    "id": claim_id,
                    "paper_id": paper_id,
                    "claim_text": text,
                    "normalized_text": normalized,
                    "claim_type": "measurement",
                    "predicate": "logical error rate",
                    "object_value": value,
                    "unit": unit,
                }
            )

    canonical_id = claim_rows[0]["id"]
    canonicalize_scope(
        "surface-codes",
        complete_fn=lambda messages, job, schema=None: {
            "comparisons": [
                {
                    "left_id": claim_rows[0]["id"],
                    "right_id": claim_rows[1]["id"],
                    "same_claim": True,
                }
            ]
        },
        store=PostgresClaimIdentityStore(),
    )

    with identity_database.connect() as connection:
        stored_claims = connection.execute(select(claim).order_by(claim.c.id)).mappings().all()
        stored_evidence = (
            connection.execute(select(claim_evidence).order_by(claim_evidence.c.id))
            .mappings()
            .all()
        )

    assert len(stored_claims) == 2
    assert [row["claim_text"] for row in stored_claims] == [row["claim_text"] for row in claim_rows]
    assert stored_claims[0]["canonical_claim_id"] is None
    assert stored_claims[1]["canonical_claim_id"] == canonical_id
    assert len(stored_evidence) == 2
    assert {row["paper_id"] for row in stored_evidence} == {row["paper_id"] for row in claim_rows}
    assert {row["claim_id"] for row in stored_evidence} == {canonical_id}


def test_extract_cli_canonicalizes_by_default_and_allows_opt_out(monkeypatch) -> None:
    from ai_researcher.cli import app
    from ai_researcher.evidence import identity
    from ai_researcher.evidence import link as evidence_link
    from ai_researcher.extraction import pipeline
    from ai_researcher.extraction.pipeline import ExtractScopeResult

    monkeypatch.setattr(
        pipeline,
        "extract_scope",
        lambda scope_name: ExtractScopeResult(extracted=0, skipped=0, failed=0),
    )
    monkeypatch.setattr(
        evidence_link,
        "link_scope_evidence",
        lambda scope_name: SimpleNamespace(claims_linked=0, evidence_links=0, failed=0),
    )
    canonicalized_scopes: list[str] = []

    def fake_canonicalize_scope(scope_name: str) -> SimpleNamespace:
        canonicalized_scopes.append(scope_name)
        return SimpleNamespace(pairs_compared=1, canonical_claims=1, merged_claims=1)

    monkeypatch.setattr(identity, "canonicalize_scope", fake_canonicalize_scope)
    runner = CliRunner()

    default_result = runner.invoke(app, ["extract", "surface-codes"])
    disabled_result = runner.invoke(app, ["extract", "surface-codes", "--no-dedup"])

    assert default_result.exit_code == 0, default_result.output
    assert "Claim canonicalization complete: pairs=1 canonical=1 merged=1." in default_result.stdout
    assert disabled_result.exit_code == 0, disabled_result.output
    assert canonicalized_scopes == ["surface-codes"]
