"""Tests for explainable, pipeline-only claim confidence scoring."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, insert, select, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from ai_researcher.cli import app


def _pg8000_url(url: str):
    return make_url(url).set(drivername="postgresql+pg8000")


@pytest.fixture
def confidence_database_url() -> str:
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
def confidence_database(
    confidence_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Engine]:
    database_name = f"test_confidence_{uuid.uuid4().hex}"
    admin_engine = create_engine(
        _pg8000_url(confidence_database_url),
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')

    scoped_url = make_url(confidence_database_url).set(database=database_name)
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


def _claim(**overrides: Any):
    from ai_researcher.scoring.confidence import ConfidenceClaim, SupportingNode

    values = {
        "id": 7,
        "claim_text": "The decoder reduces logical error rates.",
        "supporting_nodes": (
            SupportingNode(
                tree_node_id=11,
                body_text="The decoder reduces logical error rates.",
            ),
        ),
        "repeated_extractions": ("The decoder reduces logical error rates.",),
        "stopped_reason": "sufficient_evidence",
        "validation_accepted": 1,
        "validation_rejected": 0,
    }
    values.update(overrides)
    return ConfidenceClaim(**values)


def _contributions(score: Any) -> dict[str, float]:
    return {factor.name: factor.contribution for factor in score.factors}


def _assert_only_factor_changed(
    lower: Any,
    higher: Any,
    factor_name: str,
) -> None:
    lower_factors = _contributions(lower)
    higher_factors = _contributions(higher)

    assert higher.value > lower.value
    assert higher_factors[factor_name] > lower_factors[factor_name]
    assert {
        name: contribution for name, contribution in higher_factors.items() if name != factor_name
    } == {name: contribution for name, contribution in lower_factors.items() if name != factor_name}


def test_score_returns_bounded_value_and_names_every_contributing_factor() -> None:
    from ai_researcher.scoring.confidence import score_confidence

    score = score_confidence(_claim())

    assert 0 <= score.value <= 100
    assert score.confidence == score.value
    assert {factor.name for factor in score.factors} == {
        "independent_supporting_nodes",
        "verbatim_overlap",
        "self_consistency",
        "retrieval_stopped_reason",
        "schema_validation_cleanliness",
    }
    assert score.value == round(sum(factor.contribution for factor in score.factors))
    assert all(0 <= factor.contribution <= factor.max_contribution for factor in score.factors)


def test_independent_supporting_node_count_changes_only_its_factor() -> None:
    from ai_researcher.scoring.confidence import SupportingNode, score_confidence

    lower_claim = _claim()
    higher_claim = replace(
        lower_claim,
        supporting_nodes=(
            SupportingNode(11, lower_claim.claim_text),
            SupportingNode(22, lower_claim.claim_text),
            SupportingNode(33, lower_claim.claim_text),
        ),
    )

    _assert_only_factor_changed(
        score_confidence(lower_claim),
        score_confidence(higher_claim),
        "independent_supporting_nodes",
    )


def test_verbatim_overlap_changes_only_its_factor() -> None:
    from ai_researcher.scoring.confidence import SupportingNode, score_confidence

    lower_claim = replace(
        _claim(),
        supporting_nodes=(SupportingNode(11, "An unrelated sentence about qubits."),),
    )
    higher_claim = replace(
        lower_claim,
        supporting_nodes=(SupportingNode(11, lower_claim.claim_text),),
    )

    _assert_only_factor_changed(
        score_confidence(lower_claim),
        score_confidence(higher_claim),
        "verbatim_overlap",
    )


def test_verbatim_overlap_does_not_treat_shuffled_words_as_verbatim() -> None:
    from ai_researcher.scoring.confidence import SupportingNode, score_confidence

    exact_claim = _claim()
    shuffled_claim = replace(
        exact_claim,
        supporting_nodes=(
            SupportingNode(
                11,
                "rates error logical reduces decoder the.",
            ),
        ),
    )

    exact_overlap = _contributions(score_confidence(exact_claim))["verbatim_overlap"]
    shuffled_overlap = _contributions(score_confidence(shuffled_claim))["verbatim_overlap"]

    assert shuffled_overlap < exact_overlap


def test_repeated_extraction_consistency_changes_only_its_factor() -> None:
    from ai_researcher.scoring.confidence import score_confidence

    lower_claim = replace(
        _claim(),
        repeated_extractions=("The experiment reports a longer runtime.",),
    )
    higher_claim = replace(
        lower_claim,
        repeated_extractions=(lower_claim.claim_text,),
    )

    _assert_only_factor_changed(
        score_confidence(lower_claim),
        score_confidence(higher_claim),
        "self_consistency",
    )


def test_retrieval_stopping_reason_changes_only_its_factor() -> None:
    from ai_researcher.scoring.confidence import score_confidence

    lower_claim = replace(_claim(), stopped_reason="budget_exhausted")
    higher_claim = replace(lower_claim, stopped_reason="sufficient_evidence")

    _assert_only_factor_changed(
        score_confidence(lower_claim),
        score_confidence(higher_claim),
        "retrieval_stopped_reason",
    )


def test_schema_validation_cleanliness_changes_only_its_factor() -> None:
    from ai_researcher.scoring.confidence import score_confidence

    lower_claim = replace(_claim(), validation_accepted=1, validation_rejected=2)
    higher_claim = replace(lower_claim, validation_rejected=0)

    _assert_only_factor_changed(
        score_confidence(lower_claim),
        score_confidence(higher_claim),
        "schema_validation_cleanliness",
    )


def test_budget_exhausted_scores_lower_than_identical_sufficient_evidence_claim() -> None:
    from ai_researcher.scoring.confidence import score_confidence

    sufficient = score_confidence(_claim(stopped_reason="sufficient_evidence"))
    exhausted = score_confidence(_claim(stopped_reason="budget_exhausted"))

    assert exhausted.value < sufficient.value


def test_mapping_input_is_supported_by_score_confidence() -> None:
    from ai_researcher.scoring.confidence import score_confidence

    score = score_confidence(
        {
            "id": 7,
            "claim_text": "The decoder reduces logical error rates.",
            "supporting_nodes": [
                {
                    "tree_node_id": 11,
                    "body_text": "The decoder reduces logical error rates.",
                }
            ],
            "repeated_extractions": ["The decoder reduces logical error rates."],
            "stopped_reason": "sufficient_evidence",
            "validation_accepted": 1,
            "validation_rejected": 0,
        }
    )

    assert score.value > 0


def test_score_scope_writes_confidence_and_continues_past_claim_failures() -> None:
    from ai_researcher.scoring.confidence import score_scope_confidence

    class MemoryStore:
        def __init__(self) -> None:
            self.saved: list[tuple[int, int]] = []

        def load_unscored_claims(self, scope_name: str) -> tuple[Any, ...]:
            assert scope_name == "surface-codes"
            return (_claim(id=7), {"id": 8})

        def save_confidence(self, claim_id: int, confidence: int) -> None:
            self.saved.append((claim_id, confidence))

    store = MemoryStore()
    result = score_scope_confidence("surface-codes", store=store)

    assert result.scored == 1
    assert result.failed == 1
    assert store.saved == [(7, result.scores[0].value)]


def test_postgres_store_targets_claim_score_confidence_without_quality_scoring() -> None:
    from ai_researcher.db.models import claim_score
    from ai_researcher.scoring.confidence import (
        PENDING_EVIDENCE_QUALITY,
        PENDING_RUBRIC_VERSION,
        PostgresConfidenceStore,
    )

    inserted: list[dict[str, Any]] = []

    class RecordingConnection:
        def execute(self, statement) -> None:
            assert statement.table is claim_score
            inserted.append(statement.compile().params)

    @contextmanager
    def connection_factory():
        yield RecordingConnection()

    PostgresConfidenceStore(connection_factory=connection_factory).save_confidence(7, 63)

    assert inserted == [
        {
            "claim_id": 7,
            "confidence": 63,
            "evidence_quality": PENDING_EVIDENCE_QUALITY,
            "rubric_version": PENDING_RUBRIC_VERSION,
        }
    ]


def test_postgres_loader_uses_prior_same_claim_observations_as_repeated_runs() -> None:
    from ai_researcher.scoring.confidence import PostgresConfidenceStore

    loaded = PostgresConfidenceStore(
        connection_factory=_confidence_loader_connection,
    ).load_unscored_claims("surface-codes")

    assert len(loaded) == 1
    assert loaded[0].repeated_extractions == ("The decoder reduces logical error rates.",)


def test_postgres_loader_watches_evidence_and_retrieval_freshness() -> None:
    from ai_researcher.scoring.confidence import PostgresConfidenceStore

    class FreshnessCheckingConnection(_ConfidenceLoaderConnection):
        def execute(self, statement) -> _RowsResult:
            sql = str(statement)
            if "FROM claim JOIN paper_scope" in sql:
                assert "max(claim_evidence.created_at)" in sql
                assert "max(retrieval_trace.created_at)" in sql
                return _RowsResult()
            return super().execute(statement)

    @contextmanager
    def connection_factory():
        yield FreshnessCheckingConnection()

    assert (
        PostgresConfidenceStore(
            connection_factory=connection_factory,
        ).load_unscored_claims("surface-codes")
        == ()
    )


def test_default_dedup_refreshes_scores_created_by_prior_no_dedup_run(
    confidence_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonicalizing linked claims must refresh their supporting-node factor."""

    from ai_researcher.db.models import (
        claim,
        claim_evidence,
        claim_extraction_observation,
        claim_score,
        paper,
        paper_extraction_state,
        paper_scope,
        retrieval_trace,
        section,
        tree_node,
    )
    from ai_researcher.db.models import scope as scope_table
    from ai_researcher.evidence import identity, link
    from ai_researcher.extraction import pipeline

    with confidence_database.begin() as connection:
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
            (1, "The decoder lowered logical error rate to 0.01."),
            (2, "Logical error rate fell to 0.01 with the decoder."),
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
            node_id = int(
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
            claim_id = int(
                connection.execute(
                    insert(claim)
                    .values(
                        paper_id=paper_id,
                        tree_node_id=node_id,
                        claim_text=claim_text,
                        normalized_text="decoder lowers logical error rate to 0.01",
                        claim_type="measurement",
                        predicate="logical error rate",
                        object_value=0.01,
                        extraction_model="codex",
                        prompt_version="1",
                    )
                    .returning(claim.c.id)
                ).scalar_one()
            )
            claim_ids.append(claim_id)
            connection.execute(
                insert(claim_extraction_observation).values(
                    claim_id=claim_id,
                    paper_id=paper_id,
                    tree_node_id=node_id,
                    claim_text=claim_text,
                    extraction_model="codex",
                    prompt_version="1",
                )
            )
            connection.execute(
                insert(paper_extraction_state).values(
                    paper_id=paper_id,
                    extraction_model="codex",
                    prompt_version="1",
                    validation_accepted=1,
                    validation_rejected=0,
                )
            )
            connection.execute(
                insert(claim_evidence).values(
                    claim_id=claim_id,
                    tree_node_id=node_id,
                    paper_id=paper_id,
                    stance="supports",
                    rationale_text=claim_text,
                )
            )
        connection.execute(
            insert(retrieval_trace).values(
                question="decoder lowers logical error rate to 0.01",
                scope_id=scope_id,
                expanded_node_ids=[],
                selected_node_ids=[],
                nodes_expanded=0,
                stopped_reason="sufficient_evidence",
            )
        )

    monkeypatch.setattr(
        pipeline,
        "extract_scope",
        lambda scope_name: SimpleNamespace(
            extracted=0,
            skipped=2,
            failed=0,
            papers=(),
        ),
    )
    monkeypatch.setattr(
        link,
        "link_scope_evidence",
        lambda scope_name: SimpleNamespace(
            claims_linked=0,
            evidence_links=0,
            failed=0,
        ),
    )
    monkeypatch.setattr(
        identity.gateway,
        "complete",
        lambda *args, **kwargs: {
            "comparisons": [
                {
                    "left_id": claim_ids[0],
                    "right_id": claim_ids[1],
                    "same_claim": True,
                }
            ]
        },
    )
    runner = CliRunner()

    no_dedup = runner.invoke(app, ["extract", "surface-codes", "--no-dedup"])
    assert no_dedup.exit_code == 0
    assert "Confidence scoring complete: scored=2 failed=0." in no_dedup.stdout

    with confidence_database.connect() as connection:
        initial_scores = connection.execute(
            select(claim_score.c.claim_id, claim_score.c.confidence).order_by(
                claim_score.c.claim_id,
                claim_score.c.id,
            )
        ).all()
    assert len(initial_scores) == 2
    with confidence_database.begin() as connection:
        connection.execute(
            update(claim)
            .where(claim.c.id == claim_ids[0])
            .values(identity_checked_at=datetime(2020, 1, 1, tzinfo=UTC))
        )

    default_dedup = runner.invoke(app, ["extract", "surface-codes"])

    assert default_dedup.exit_code == 0
    assert "Claim canonicalization complete: pairs=1 canonical=1 merged=1." in (
        default_dedup.stdout
    )
    assert "Confidence scoring complete: scored=2 failed=0." in default_dedup.stdout
    with confidence_database.connect() as connection:
        score_history = connection.execute(
            select(claim_score.c.claim_id, claim_score.c.confidence).order_by(
                claim_score.c.claim_id,
                claim_score.c.id,
            )
        ).all()
    root_scores = [confidence for claim_id, confidence in score_history if claim_id == claim_ids[0]]
    assert len(root_scores) == 2
    assert root_scores[-1] > root_scores[0]


def test_production_repeated_run_agreement_changes_only_self_consistency() -> None:
    from ai_researcher.scoring.confidence import PostgresConfidenceStore, score_confidence

    agreed = PostgresConfidenceStore(
        connection_factory=_confidence_loader_connection,
    ).load_unscored_claims("surface-codes")
    disagreed = PostgresConfidenceStore(
        connection_factory=_disagreeing_confidence_loader_connection,
    ).load_unscored_claims("surface-codes")

    assert len(agreed) == len(disagreed) == 1
    _assert_only_factor_changed(
        score_confidence(disagreed[0]),
        score_confidence(agreed[0]),
        "self_consistency",
    )


def test_postgres_loader_uses_persisted_validation_outcomes() -> None:
    from ai_researcher.scoring.confidence import PostgresConfidenceStore, score_confidence

    loaded = PostgresConfidenceStore(
        connection_factory=_confidence_loader_connection,
    ).load_unscored_claims("surface-codes")

    assert len(loaded) == 1
    assert loaded[0].validation_accepted == 3
    assert loaded[0].validation_rejected == 1
    loaded_contribution = _contributions(score_confidence(loaded[0]))[
        "schema_validation_cleanliness"
    ]
    clean_contribution = _contributions(
        score_confidence(replace(loaded[0], validation_rejected=0))
    )["schema_validation_cleanliness"]
    assert loaded_contribution < clean_contribution


def test_extraction_persists_validation_outcomes_for_confidence(
    monkeypatch,
) -> None:
    from ai_researcher.extraction import pipeline
    from ai_researcher.extraction.schema import ClaimRecord

    accepted = ClaimRecord(
        tree_node_id=11,
        claim_text="The decoder reduces logical error rates.",
        normalized_text="decoder reduces logical error rates",
        claim_type="result",
        extraction_model="codex",
        prompt_version="v1",
    )
    monkeypatch.setattr(
        pipeline,
        "validate_llm_output",
        lambda fetch, allowed_ids: SimpleNamespace(
            accepted=[accepted],
            rejected=[object(), object()],
            paper_failed=False,
            failure_reason=None,
        ),
    )
    persisted: list[dict[str, Any]] = []
    monkeypatch.setattr(
        pipeline,
        "_persist_extractions",
        lambda connection, **values: persisted.append(values),
    )
    paper_input = pipeline.PaperExtractionInput(
        id=5,
        title="Decoder study",
        abstract=None,
        parse_status="parsed",
        nodes=(
            pipeline.TreeNodeInput(
                id=11,
                node_path="results",
                title="Results",
                summary="Decoder results",
                page_start=2,
                page_end=2,
                depth=0,
                body_text="The decoder reduces logical error rates.",
            ),
        ),
    )

    result = pipeline.extract_paper(
        paper_input,
        complete_fn=lambda *args, **kwargs: {},
        extraction_model="codex",
        prompt_version="v1",
        persist=True,
        connection=object(),
    )

    assert result.claims == 1
    assert persisted[0]["validation_accepted"] == 1
    assert persisted[0]["validation_rejected"] == 2


def test_extraction_records_passage_anchored_claim_observations() -> None:
    from ai_researcher.db.models import claim_extraction_observation
    from ai_researcher.extraction.pipeline import _record_claim_observation
    from ai_researcher.extraction.schema import ClaimRecord

    statements: list[Any] = []

    class RecordingConnection:
        def execute(self, statement) -> None:
            statements.append(statement)

    record = ClaimRecord(
        tree_node_id=11,
        claim_text="The decoder reduces logical error rates.",
        normalized_text="decoder reduces logical error rates",
        claim_type="result",
        extraction_model="codex",
        prompt_version="v2",
    )

    _record_claim_observation(
        RecordingConnection(),
        claim_id=7,
        paper_id=5,
        record=record,
    )

    assert len(statements) == 1
    assert statements[0].table is claim_extraction_observation
    assert statements[0].compile().params == {
        "claim_id": 7,
        "paper_id": 5,
        "tree_node_id": 11,
        "claim_text": "The decoder reduces logical error rates.",
        "extraction_model": "codex",
        "prompt_version": "v2",
    }


def test_extract_scores_by_default_and_no_score_disables_it(
    monkeypatch,
) -> None:
    from ai_researcher.evidence import identity, link
    from ai_researcher.extraction import pipeline
    from ai_researcher.scoring import confidence

    monkeypatch.setattr(
        pipeline,
        "extract_scope",
        lambda scope_name: SimpleNamespace(
            extracted=0,
            skipped=0,
            failed=0,
            papers=(),
        ),
    )
    monkeypatch.setattr(
        link,
        "link_scope_evidence",
        lambda scope_name: SimpleNamespace(
            claims_linked=0,
            evidence_links=0,
            failed=0,
        ),
    )
    monkeypatch.setattr(
        identity,
        "canonicalize_scope",
        lambda scope_name: SimpleNamespace(
            pairs_compared=0,
            canonical_claims=0,
            merged_claims=0,
        ),
    )
    score_calls: list[str] = []
    monkeypatch.setattr(
        confidence,
        "score_scope_confidence",
        lambda scope_name: (
            score_calls.append(scope_name) or SimpleNamespace(scored=2, failed=0, scores=())
        ),
    )

    runner = CliRunner()
    default_result = runner.invoke(
        app,
        ["extract", "surface-codes", "--no-link-evidence", "--no-dedup"],
    )
    disabled_result = runner.invoke(
        app,
        [
            "extract",
            "surface-codes",
            "--no-link-evidence",
            "--no-dedup",
            "--no-score",
        ],
    )

    assert default_result.exit_code == 0
    assert "Confidence scoring complete: scored=2 failed=0." in default_result.stdout
    assert disabled_result.exit_code == 0
    assert "Confidence scoring complete" not in disabled_result.stdout
    assert score_calls == ["surface-codes"]


def test_extract_defers_scoring_until_transient_evidence_link_failures_clear(
    monkeypatch,
) -> None:
    from ai_researcher.evidence import link
    from ai_researcher.extraction import pipeline
    from ai_researcher.scoring import confidence

    monkeypatch.setattr(
        pipeline,
        "extract_scope",
        lambda scope_name: SimpleNamespace(
            extracted=0,
            skipped=0,
            failed=0,
            papers=(),
        ),
    )
    link_results = iter(
        (
            SimpleNamespace(claims_linked=0, evidence_links=0, failed=1),
            SimpleNamespace(claims_linked=1, evidence_links=2, failed=0),
        )
    )
    monkeypatch.setattr(link, "link_scope_evidence", lambda scope_name: next(link_results))
    score_calls: list[str] = []
    monkeypatch.setattr(
        confidence,
        "score_scope_confidence",
        lambda scope_name: (
            score_calls.append(scope_name) or SimpleNamespace(scored=1, failed=0, scores=())
        ),
    )
    runner = CliRunner()

    failed_link = runner.invoke(
        app,
        ["extract", "surface-codes", "--no-dedup"],
    )
    successful_retry = runner.invoke(
        app,
        ["extract", "surface-codes", "--no-dedup"],
    )

    assert failed_link.exit_code == 0
    assert "Confidence scoring deferred: evidence linking failed for 1 claim(s)." in (
        failed_link.stdout
    )
    assert "Confidence scoring complete" not in failed_link.stdout
    assert successful_retry.exit_code == 0
    assert "Confidence scoring complete: scored=1 failed=0." in successful_retry.stdout
    assert score_calls == ["surface-codes"]


class _RowsResult:
    def __init__(
        self,
        *,
        rows: tuple[dict[str, Any], ...] = (),
        scalar: int | None = None,
    ) -> None:
        self._rows = rows
        self._scalar = scalar

    def scalar_one_or_none(self) -> int | None:
        return self._scalar

    def mappings(self) -> _RowsResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _ConfidenceLoaderConnection:
    repeated_claim_text = "The decoder reduces logical error rates."

    def execute(self, statement) -> _RowsResult:
        sql = str(statement)
        if "FROM scope" in sql:
            return _RowsResult(scalar=9)
        if "FROM claim JOIN paper_scope" in sql:
            return _RowsResult(
                rows=(
                    {
                        "id": 7,
                        "paper_id": 1,
                        "claim_text": "The decoder reduces logical error rates.",
                        "normalized_text": "decoder reduces logical error rates",
                        "canonical_claim_id": None,
                        "extraction_model": "codex",
                        "prompt_version": "v1",
                    },
                )
            )
        if "FROM claim_evidence" in sql:
            return _RowsResult()
        if "FROM retrieval_trace" in sql:
            return _RowsResult(
                rows=(
                    {
                        "question": "decoder reduces logical error rates",
                        "stopped_reason": "sufficient_evidence",
                        "created_at": None,
                    },
                )
            )
        if "FROM paper_extraction_state" in sql:
            return _RowsResult(
                rows=(
                    {
                        "paper_id": 1,
                        "extraction_model": "codex",
                        "prompt_version": "v1",
                        "validation_accepted": 3,
                        "validation_rejected": 1,
                    },
                )
            )
        if "FROM claim_extraction_observation" in sql:
            assert "claim_extraction_observation.claim_id IN" in sql
            return _RowsResult(
                rows=(
                    {
                        "id": 1,
                        "claim_id": 7,
                        "claim_text": self.repeated_claim_text,
                    },
                    {
                        "id": 2,
                        "claim_id": 7,
                        "claim_text": "The decoder reduces logical error rates.",
                    },
                    {
                        "id": 3,
                        "claim_id": 8,
                        "claim_text": "The decoder reduces logical error rates.",
                    },
                )
            )
        if "FROM claim" in sql:
            return _RowsResult(
                rows=(
                    {
                        "id": 7,
                        "claim_text": "The decoder reduces logical error rates.",
                        "canonical_claim_id": None,
                    },
                    {
                        "id": 8,
                        "claim_text": "The decoder reduces logical error rates.",
                        "canonical_claim_id": 7,
                    },
                )
            )
        raise AssertionError(f"Unexpected confidence query: {sql}")


@contextmanager
def _confidence_loader_connection():
    yield _ConfidenceLoaderConnection()


class _DisagreeingConfidenceLoaderConnection(_ConfidenceLoaderConnection):
    repeated_claim_text = "The experiment reports a longer runtime."


@contextmanager
def _disagreeing_confidence_loader_connection():
    yield _DisagreeingConfidenceLoaderConnection()
