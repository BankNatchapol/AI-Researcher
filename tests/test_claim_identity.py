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


def test_canonicalize_does_not_bridge_non_prefiltered_numeric_endpoints() -> None:
    from ai_researcher.evidence.identity import canonicalize, prefilter_pairs

    claims = [
        {
            "id": claim_id,
            "paper_id": 100 + claim_id,
            "claim_text": f"Logical error rate was {value}.",
            "normalized_text": "logical error rate measurement",
            "claim_type": "measurement",
            "predicate": "logical error rate",
            "object_value": value,
            "unit": None,
        }
        for claim_id, value in ((1, 0.94), (2, 1.0), (3, 1.06))
    ]
    pairs = prefilter_pairs(claims)
    compared_pairs: list[tuple[int, int]] = []

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        assert job == "claim_identity"
        assert schema is not None
        payload = json.loads(messages[-1]["content"])
        compared_pairs.extend(
            (candidate["left"]["id"], candidate["right"]["id"])
            for candidate in payload["candidate_pairs"]
        )
        return {
            "comparisons": [
                {
                    "left_id": left_id,
                    "right_id": right_id,
                    "same_claim": True,
                }
                for left_id, right_id in compared_pairs
            ]
        }

    class MemoryIdentityStore:
        def __init__(self) -> None:
            self.groups: list[Any] = []

        def save_canonical_groups(self, groups: list[Any]) -> None:
            self.groups = list(groups)

    store = MemoryIdentityStore()
    result = canonicalize(pairs, complete_fn=fake_complete, store=store)

    assert compared_pairs == [(1, 2), (2, 3)]
    assert [(group.canonical_id, group.claim_ids) for group in store.groups] == [(1, (1, 2))]
    assert result.canonical_claims == 1
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
            claim_rows.append(
                {
                    "id": claim_id,
                    "paper_id": paper_id,
                    "tree_node_id": node_id,
                    "claim_text": text,
                    "normalized_text": normalized,
                    "claim_type": "measurement",
                    "predicate": "logical error rate",
                    "object_value": value,
                    "unit": unit,
                }
            )
        connection.execute(
            insert(claim_evidence),
            [
                {
                    "claim_id": claim_row["id"],
                    "tree_node_id": source_row["tree_node_id"],
                    "paper_id": source_row["paper_id"],
                    "stance": "supports",
                    "rationale_text": source_row["claim_text"],
                }
                for claim_row in claim_rows
                for source_row in claim_rows
            ],
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
    assert len({row["paper_id"] for row in stored_evidence}) == len(stored_evidence)
    assert {row["claim_id"] for row in stored_evidence} == {canonical_id}


def test_negative_identity_decision_is_not_repeated_on_unchanged_rerun(
    identity_database: Engine,
) -> None:
    from ai_researcher.db.models import claim, paper, paper_scope, section, tree_node
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
        claim_ids: list[int] = []
        for paper_number, claim_text in (
            (1, "The decoder lowered logical error rate to one percent."),
            (2, "A different decoder also reached a one percent logical error rate."),
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
                        body_text=claim_text,
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
                        node_path="Results",
                        summary=claim_text,
                        depth=0,
                        tree_schema_version="1",
                        summary_model="codex",
                    )
                    .returning(tree_node.c.id)
                ).scalar_one()
            )
            claim_ids.append(
                int(
                    connection.execute(
                        insert(claim)
                        .values(
                            paper_id=paper_id,
                            tree_node_id=tree_node_id,
                            claim_text=claim_text,
                            normalized_text=claim_text.lower(),
                            claim_type="measurement",
                            predicate="logical error rate",
                            object_value=1.0,
                            unit="%",
                            extraction_model="codex",
                            prompt_version="1",
                        )
                        .returning(claim.c.id)
                    ).scalar_one()
                )
            )

    model_calls: list[tuple[int, int]] = []

    def distinct_claims(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        assert job == "claim_identity"
        assert schema is not None
        payload = json.loads(messages[-1]["content"])
        compared_pair = payload["candidate_pairs"][0]
        pair_ids = (compared_pair["left"]["id"], compared_pair["right"]["id"])
        model_calls.append(pair_ids)
        return {
            "comparisons": [
                {
                    "left_id": pair_ids[0],
                    "right_id": pair_ids[1],
                    "same_claim": False,
                }
            ]
        }

    store = PostgresClaimIdentityStore(connection_factory=identity_database.begin)
    initial = canonicalize_scope("surface-codes", complete_fn=distinct_claims, store=store)
    with identity_database.connect() as connection:
        rows_after_initial = connection.execute(select(claim).order_by(claim.c.id)).all()

    rerun = canonicalize_scope("surface-codes", complete_fn=distinct_claims, store=store)
    with identity_database.connect() as connection:
        rows_after_rerun = connection.execute(select(claim).order_by(claim.c.id)).all()

    assert initial.pairs_compared == 1
    assert rerun.pairs_compared == 0
    assert model_calls == [tuple(claim_ids)]
    assert rows_after_rerun == rows_after_initial
    with identity_database.connect() as connection:
        checked_at = (
            connection.execute(select(claim.c.identity_checked_at).order_by(claim.c.id))
            .scalars()
            .all()
        )
    assert all(value is not None for value in checked_at)


def test_merging_existing_canonical_roots_repoints_descendants_to_final_root(
    identity_database: Engine,
) -> None:
    from ai_researcher.db.models import claim, paper, section, tree_node
    from ai_researcher.evidence.identity import CanonicalGroup, PostgresClaimIdentityStore

    claim_ids: list[int] = []
    with identity_database.begin() as connection:
        for paper_number in range(1, 4):
            text = f"Paper {paper_number} reports a logical error rate."
            paper_id = int(
                connection.execute(
                    insert(paper)
                    .values(title=f"Paper {paper_number}", parse_status="parsed")
                    .returning(paper.c.id)
                ).scalar_one()
            )
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
            claim_ids.append(
                int(
                    connection.execute(
                        insert(claim)
                        .values(
                            paper_id=paper_id,
                            tree_node_id=node_id,
                            claim_text=text,
                            normalized_text="logical error rate measurement",
                            claim_type="measurement",
                            predicate="logical error rate",
                            object_value=0.01,
                            extraction_model="codex",
                            prompt_version="1",
                        )
                        .returning(claim.c.id)
                    ).scalar_one()
                )
            )

    store = PostgresClaimIdentityStore(connection_factory=identity_database.begin)
    store.save_canonical_groups(
        [
            CanonicalGroup(
                canonical_id=claim_ids[1],
                claim_ids=(claim_ids[1], claim_ids[2]),
            )
        ]
    )
    store.save_canonical_groups(
        [
            CanonicalGroup(
                canonical_id=claim_ids[0],
                claim_ids=(claim_ids[0], claim_ids[1]),
            )
        ]
    )

    with identity_database.connect() as connection:
        canonical_links = connection.execute(
            select(claim.c.id, claim.c.canonical_claim_id).order_by(claim.c.id)
        ).all()

    assert canonical_links == [
        (claim_ids[0], None),
        (claim_ids[1], claim_ids[0]),
        (claim_ids[2], claim_ids[0]),
    ]


def test_extract_cli_canonicalizes_by_default_and_allows_opt_out(monkeypatch) -> None:
    from ai_researcher.cli import app
    from ai_researcher.evidence import identity
    from ai_researcher.evidence import link as evidence_link
    from ai_researcher.extraction import pipeline
    from ai_researcher.extraction.pipeline import ExtractScopeResult

    monkeypatch.setattr(
        pipeline,
        "extract_scope",
        lambda scope_name: ExtractScopeResult(extracted=1, skipped=0, failed=0),
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


@pytest.mark.parametrize("dedup_args", [[], ["--dedup"]], ids=["default", "explicit"])
def test_extract_cli_processes_dedup_backlog_after_opt_out(
    monkeypatch: pytest.MonkeyPatch,
    dedup_args: list[str],
) -> None:
    from ai_researcher.cli import app
    from ai_researcher.evidence import identity
    from ai_researcher.evidence import link as evidence_link
    from ai_researcher.extraction import pipeline
    from ai_researcher.extraction.pipeline import ExtractScopeResult

    extraction_results = iter(
        (
            ExtractScopeResult(extracted=1, skipped=0, failed=0),
            ExtractScopeResult(extracted=0, skipped=1, failed=0),
        )
    )
    monkeypatch.setattr(pipeline, "extract_scope", lambda scope_name: next(extraction_results))
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

    opted_out = runner.invoke(app, ["extract", "surface-codes", "--no-dedup"])
    opted_in = runner.invoke(app, ["extract", "surface-codes", *dedup_args])

    assert opted_out.exit_code == 0, opted_out.output
    assert opted_in.exit_code == 0, opted_in.output
    assert canonicalized_scopes == ["surface-codes"]
    assert "Claim canonicalization complete: pairs=1 canonical=1 merged=1." in opted_in.stdout


def test_extract_rerun_does_no_identity_or_stance_work(
    identity_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.cli import app
    from ai_researcher.db.models import (
        claim,
        claim_evidence,
        paper,
        paper_scope,
        section,
        tree_node,
    )
    from ai_researcher.db.models import scope as scope_table
    from ai_researcher.evidence import identity
    from ai_researcher.evidence import link as evidence_link
    from ai_researcher.extraction import pipeline
    from ai_researcher.extraction.pipeline import ExtractScopeResult
    from ai_researcher.llm import gateway
    from ai_researcher.retrieval import RankedNode, TraversalResult, TraversalTrace

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
        claim_ids: list[int] = []
        ranked_nodes: list[RankedNode] = []
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
            claim_ids.append(
                int(
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
            )
            ranked_nodes.append(
                RankedNode(
                    node_id=node_id,
                    paper_id=paper_id,
                    section_path="Results",
                    title=None,
                    summary=text,
                    page_start=1,
                    page_end=1,
                    relevance=100,
                    reason="Relevant duplicate evidence.",
                )
            )

    extraction_results = iter(
        (
            ExtractScopeResult(extracted=2, skipped=0, failed=0),
            ExtractScopeResult(extracted=0, skipped=2, failed=0),
        )
    )
    monkeypatch.setattr(pipeline, "extract_scope", lambda scope_name: next(extraction_results))
    monkeypatch.setattr(
        evidence_link,
        "traverse",
        lambda question, scope: TraversalResult(
            ranked_nodes=tuple(ranked_nodes),
            trace=TraversalTrace(
                expanded_nodes=(),
                selected_node_ids=tuple(node.node_id for node in ranked_nodes),
                stopped_reason="sufficient_evidence",
            ),
        ),
    )
    model_jobs: list[str] = []

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del schema
        model_jobs.append(job)
        payload = json.loads(messages[-1]["content"])
        if job == "stance":
            return {
                "classifications": [
                    {
                        "node_id": candidate["node_id"],
                        "stance": "supports",
                        "rationale": candidate["body_text"],
                    }
                    for candidate in payload["candidate_nodes"]
                ]
            }
        assert job == "claim_identity"
        return {
            "comparisons": [
                {
                    "left_id": pair["left"]["id"],
                    "right_id": pair["right"]["id"],
                    "same_claim": True,
                }
                for pair in payload["candidate_pairs"]
            ]
        }

    monkeypatch.setattr(gateway, "complete", fake_complete)
    evidence_writes: list[int] = []
    identity_writes: list[int] = []
    original_save_links = evidence_link.PostgresEvidenceStore.save_links
    original_save_groups = identity.PostgresClaimIdentityStore.save_canonical_groups

    def save_links(self, claim_id, links):
        evidence_writes.append(claim_id)
        return original_save_links(self, claim_id, links)

    def save_groups(self, groups):
        identity_writes.append(len(groups))
        return original_save_groups(self, groups)

    monkeypatch.setattr(evidence_link.PostgresEvidenceStore, "save_links", save_links)
    monkeypatch.setattr(identity.PostgresClaimIdentityStore, "save_canonical_groups", save_groups)
    runner = CliRunner()

    initial = runner.invoke(app, ["extract", "surface-codes"])
    assert initial.exit_code == 0, initial.output
    assert model_jobs == ["stance", "stance", "claim_identity"]
    assert evidence_writes == claim_ids
    assert identity_writes == [1]

    with identity_database.connect() as connection:
        claims_before = connection.execute(
            select(claim.c.id, claim.c.canonical_claim_id).order_by(claim.c.id)
        ).all()
        evidence_before = connection.execute(
            select(
                claim_evidence.c.id,
                claim_evidence.c.claim_id,
                claim_evidence.c.tree_node_id,
                claim_evidence.c.paper_id,
                claim_evidence.c.stance,
                claim_evidence.c.rationale_text,
            ).order_by(claim_evidence.c.id)
        ).all()

    model_jobs.clear()
    evidence_writes.clear()
    identity_writes.clear()
    rerun = runner.invoke(app, ["extract", "surface-codes"])

    assert rerun.exit_code == 0, rerun.output
    assert model_jobs == []
    assert evidence_writes == []
    assert identity_writes == []
    assert "Evidence linking complete: claims=0 links=0 failed=0." in rerun.stdout
    assert "Claim canonicalization complete: pairs=0 canonical=0 merged=0." in rerun.stdout
    with identity_database.connect() as connection:
        assert (
            connection.execute(
                select(claim.c.id, claim.c.canonical_claim_id).order_by(claim.c.id)
            ).all()
            == claims_before
        )
        assert (
            connection.execute(
                select(
                    claim_evidence.c.id,
                    claim_evidence.c.claim_id,
                    claim_evidence.c.tree_node_id,
                    claim_evidence.c.paper_id,
                    claim_evidence.c.stance,
                    claim_evidence.c.rationale_text,
                ).order_by(claim_evidence.c.id)
            ).all()
            == evidence_before
        )
