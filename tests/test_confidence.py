"""Tests for explainable, pipeline-only claim confidence scoring."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from typer.testing import CliRunner

from ai_researcher.cli import app


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
