"""Tests for rubric-driven, science-only evidence-quality scoring."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def _evidence(**overrides: Any):
    from ai_researcher.scoring.quality import QualityEvidence

    values = {
        "tree_node_id": 11,
        "paper_id": 101,
        "stance": "supports",
        "is_direct": True,
    }
    values.update(overrides)
    return QualityEvidence(**values)


def _claim(**overrides: Any):
    from ai_researcher.scoring.quality import QualityClaim

    values = {
        "id": 7,
        "parse_status": "parsed",
        "is_preprint": False,
        "venue": "Physical Review Letters",
        "published_at": date.today() - timedelta(days=365),
        "evidence": (_evidence(),),
    }
    values.update(overrides)
    return QualityClaim(**values)


def _contributions(score: Any) -> dict[str, float]:
    return {factor.name: factor.contribution for factor in score.factors}


def _assert_only_factor_changed(lower: Any, higher: Any, factor_name: str) -> None:
    lower_factors = _contributions(lower)
    higher_factors = _contributions(higher)

    assert higher.value > lower.value
    assert higher_factors[factor_name] > lower_factors[factor_name]
    assert {
        name: contribution for name, contribution in higher_factors.items() if name != factor_name
    } == {name: contribution for name, contribution in lower_factors.items() if name != factor_name}


def test_score_returns_bounded_value_and_every_documented_factor() -> None:
    from ai_researcher.scoring.quality import score_quality

    score = score_quality(_claim())

    assert 0 <= score.value <= 100
    assert score.evidence_quality == score.value
    assert {factor.name for factor in score.factors} == {
        "full_text",
        "peer_review",
        "directness",
        "recency",
        "replication",
    }
    assert score.value == round(sum(factor.contribution for factor in score.factors))
    assert all(0 <= factor.contribution <= factor.max_contribution for factor in score.factors)
    assert score.rubric_version


def test_abstract_only_claim_scores_lower_than_otherwise_identical_full_text_claim() -> None:
    from ai_researcher.scoring.quality import score_quality

    abstract_only = _claim(parse_status="abstract_only")
    full_text = replace(abstract_only, parse_status="parsed")

    _assert_only_factor_changed(
        score_quality(abstract_only),
        score_quality(full_text),
        "full_text",
    )


def test_peer_reviewed_claim_scores_higher_than_otherwise_identical_preprint() -> None:
    from ai_researcher.scoring.quality import score_quality

    preprint = _claim(is_preprint=True, venue="arXiv")
    peer_reviewed = replace(
        preprint,
        is_preprint=False,
        venue="Physical Review Letters",
    )

    _assert_only_factor_changed(
        score_quality(preprint),
        score_quality(peer_reviewed),
        "peer_review",
    )


def test_direct_evidence_scores_higher_than_otherwise_identical_inference() -> None:
    from ai_researcher.scoring.quality import score_quality

    inferred = _claim(evidence=(_evidence(is_direct=False),))
    direct = replace(inferred, evidence=(_evidence(is_direct=True),))

    _assert_only_factor_changed(
        score_quality(inferred),
        score_quality(direct),
        "directness",
    )


def test_recent_claim_scores_higher_than_otherwise_identical_old_claim() -> None:
    from ai_researcher.scoring.quality import score_quality

    old = _claim(published_at=date.today() - timedelta(days=365 * 20))
    recent = replace(old, published_at=date.today() - timedelta(days=365))

    _assert_only_factor_changed(
        score_quality(old),
        score_quality(recent),
        "recency",
    )


def test_independent_replication_changes_only_replication_factor() -> None:
    from ai_researcher.scoring.quality import score_quality

    unreplicated = _claim(evidence=(_evidence(paper_id=101),))
    replicated = replace(
        unreplicated,
        evidence=(
            _evidence(tree_node_id=11, paper_id=101),
            _evidence(tree_node_id=22, paper_id=202),
            _evidence(tree_node_id=33, paper_id=303),
        ),
    )

    _assert_only_factor_changed(
        score_quality(unreplicated),
        score_quality(replicated),
        "replication",
    )


def test_replication_counts_distinct_supporting_papers_only() -> None:
    from ai_researcher.scoring.quality import score_quality

    repeated_nodes = _claim(
        evidence=(
            _evidence(tree_node_id=11, paper_id=101),
            _evidence(tree_node_id=12, paper_id=101),
            _evidence(tree_node_id=22, paper_id=202, stance="refutes"),
        )
    )
    one_supporting_paper = _claim(evidence=(_evidence(tree_node_id=11, paper_id=101),))

    assert (
        _contributions(score_quality(repeated_nodes))["replication"]
        == _contributions(score_quality(one_supporting_paper))["replication"]
    )


def test_mapping_input_is_supported_by_score_quality() -> None:
    from ai_researcher.scoring.quality import score_quality

    score = score_quality(
        {
            "id": 7,
            "parse_status": "parsed",
            "is_preprint": False,
            "venue": "Physical Review Letters",
            "published_at": date.today().isoformat(),
            "evidence": [
                {
                    "tree_node_id": 11,
                    "paper_id": 101,
                    "stance": "supports",
                    "is_direct": True,
                }
            ],
        }
    )

    assert score.value > 0


def test_rubric_version_changes_when_any_rubric_file_content_changes(tmp_path: Path) -> None:
    from ai_researcher.scoring.quality import RUBRIC_PATH, load_rubric

    original = RUBRIC_PATH.read_text(encoding="utf-8")
    changed_path = tmp_path / "rubric.md"
    changed_path.write_text(f"{original}\nEditorial clarification.\n", encoding="utf-8")

    assert load_rubric().version != load_rubric(changed_path).version


def test_persisted_claim_score_rows_carry_the_exact_rubric_version(tmp_path: Path) -> None:
    from ai_researcher.db.models import claim_score
    from ai_researcher.scoring.quality import (
        RUBRIC_PATH,
        PostgresQualityStore,
        score_quality,
    )

    changed_path = tmp_path / "rubric.md"
    changed_path.write_text(
        f"{RUBRIC_PATH.read_text(encoding='utf-8')}\nEditorial clarification.\n",
        encoding="utf-8",
    )
    scores = (
        score_quality(_claim()),
        score_quality(_claim(), rubric_path=changed_path),
    )
    inserted: list[dict[str, Any]] = []

    class RecordingConnection:
        def execute(self, statement) -> None:
            assert statement.table is claim_score
            inserted.append(statement.compile().params)

    @contextmanager
    def connection_factory():
        yield RecordingConnection()

    store = PostgresQualityStore(connection_factory=connection_factory)
    for score in scores:
        store.save_quality(claim_id=7, confidence=63, quality=score)

    assert [row["rubric_version"] for row in inserted] == [score.rubric_version for score in scores]
    assert all(row["rubric_version"] != "pending-evidence-quality" for row in inserted)
    assert [row["evidence_quality"] for row in inserted] == [score.value for score in scores]
