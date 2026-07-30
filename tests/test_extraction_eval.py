"""Offline tests for extraction and stance evaluation against the gold set."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_researcher.cli import app

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "eval-corpus"
runner = CliRunner()


@dataclass(frozen=True)
class FixtureSectionCatalog:
    """Expose the committed fixture's known paths without a database."""

    corpus: dict

    def section_paths(self, scope: str) -> frozenset[str]:
        records = self.corpus["scopes"].get(scope, {}).get("sections", [])
        return frozenset(record["section_path"] for record in records)


@pytest.fixture
def fixture_corpus() -> dict:
    return json.loads((FIXTURE_DIR / "corpus.json").read_text())


def test_default_goldset_has_at_least_fifteen_labelled_claims() -> None:
    from ai_researcher.eval.goldset import load_gold_claims

    claims = load_gold_claims(Path("eval/goldset.yaml"))

    assert len(claims) >= 15
    assert all(claim.section_path and claim.stance for claim in claims)
    assert all(claim.normalized_text for claim in claims)
    assert {claim.stance for claim in claims} <= {"supports", "refutes", "mentions"}


def test_gold_claims_fail_loudly_when_section_path_matches_no_known_section(
    fixture_corpus: dict,
    tmp_path: Path,
) -> None:
    from ai_researcher.eval.goldset import GoldSetValidationError, load_gold_claims

    bad_goldset = tmp_path / "bad-claims.yaml"
    bad_goldset.write_text(
        "\n".join(
            [
                "version: 1",
                "questions:",
                "  - question: placeholder",
                "    scope: fixture-eval",
                "    section_paths:",
                "      - Results/Threshold",
                "claims:",
                "  - normalized_text: a missing-path claim",
                "    scope: fixture-eval",
                "    section_path: Results/Does Not Exist",
                "    stance: supports",
            ]
        )
    )

    with pytest.raises(GoldSetValidationError, match="Results/Does Not Exist"):
        load_gold_claims(
            bad_goldset,
            scope="fixture-eval",
            section_catalog=FixtureSectionCatalog(fixture_corpus),
        )


def test_claim_matching_uses_normalized_text_and_quantity_parsing() -> None:
    from ai_researcher.eval.extraction_metrics import claims_match
    from ai_researcher.eval.goldset import GoldClaim

    gold = GoldClaim(
        normalized_text="surface code threshold is 1%",
        scope="fixture-eval",
        section_path="Results/Threshold",
        stance="supports",
        object_value=1.0,
        unit="%",
    )
    matching = {
        "normalized_text": "Surface Code Threshold Is 1%",
        "object_value": 1.0,
        "unit": "%",
    }
    numeric_mismatch = {
        "normalized_text": "surface code threshold is 1%",
        "object_value": 2.0,
        "unit": "%",
    }
    text_mismatch = {
        "normalized_text": "a different claim entirely",
        "object_value": 1.0,
        "unit": "%",
    }

    assert claims_match(matching, gold) is True
    assert claims_match(numeric_mismatch, gold) is False
    assert claims_match(text_mismatch, gold) is False


def test_extraction_metrics_compute_precision_recall_f1_span_and_stance() -> None:
    from ai_researcher.eval.extraction_metrics import (
        ExtractedClaimObservation,
        ExtractedEvidenceObservation,
        compute_extraction_metrics,
    )
    from ai_researcher.eval.goldset import GoldClaim

    gold = (
        GoldClaim(
            normalized_text="threshold is approximately 1 percent",
            scope="fixture-eval",
            section_path="Results/Threshold",
            stance="supports",
            object_value=1.0,
            unit="%",
        ),
        GoldClaim(
            normalized_text="minimum-weight perfect matching is the decoder",
            scope="fixture-eval",
            section_path="Methods/Decoder",
            stance="supports",
        ),
        GoldClaim(
            normalized_text="lattice surgery has high overhead",
            scope="fixture-eval",
            section_path="Discussion/Limitations",
            stance="refutes",
        ),
    )
    extracted = (
        ExtractedClaimObservation(
            id=1,
            normalized_text="threshold is approximately 1 percent",
            object_value=1.0,
            unit="%",
            evidence=(
                ExtractedEvidenceObservation(
                    section_path="Results/Threshold",
                    stance="supports",
                ),
                ExtractedEvidenceObservation(
                    section_path="Introduction",
                    stance="mentions",
                ),
            ),
        ),
        ExtractedClaimObservation(
            id=2,
            normalized_text="minimum-weight perfect matching is the decoder",
            object_value=None,
            unit=None,
            evidence=(
                ExtractedEvidenceObservation(
                    section_path="Discussion/Limitations",
                    stance="supports",
                ),
            ),
        ),
        ExtractedClaimObservation(
            id=3,
            normalized_text="spurious extracted claim with no gold",
            object_value=None,
            unit=None,
            evidence=(
                ExtractedEvidenceObservation(
                    section_path="Introduction",
                    stance="mentions",
                ),
            ),
        ),
    )

    metrics = compute_extraction_metrics(gold, extracted)

    # 2 of 3 extracted match gold → precision 2/3
    # 2 of 3 gold found → recall 2/3
    assert metrics.claim_precision == pytest.approx(2 / 3)
    assert metrics.claim_recall == pytest.approx(2 / 3)
    assert metrics.claim_f1 == pytest.approx(2 / 3)
    # 4 evidence rows total; only 1 lands on its matched gold section_path
    assert metrics.evidence_span_precision == pytest.approx(1 / 4)
    # Among the 3 evidence rows on matched claims, 2 share the gold stance
    # (claim1 supports@Threshold; claim2 supports@Limitations — section wrong
    # but stance still matches gold "supports"; claim1 mentions@Intro misses)
    assert metrics.stance_accuracy == pytest.approx(2 / 3)


def test_extraction_eval_appends_to_same_dated_report(
    fixture_corpus: dict,
    tmp_path: Path,
) -> None:
    from ai_researcher.answer import Answer, Citation
    from ai_researcher.eval.extraction_metrics import (
        ExtractedClaimObservation,
        ExtractedEvidenceObservation,
    )
    from ai_researcher.eval.harness import run_evaluation, run_extraction_evaluation
    from ai_researcher.retrieval import RankedNode, TraversalResult, TraversalTrace

    fixed_time = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    catalog = FixtureSectionCatalog(fixture_corpus)

    def traverse(question: str, scope: str, max_nodes: int | None = None) -> TraversalResult:
        del question, max_nodes
        sections = fixture_corpus["scopes"][scope]["sections"]
        nodes = tuple(
            RankedNode(
                node_id=record["node_id"],
                paper_id=record["paper_id"],
                section_path=record["section_path"],
                title=record["section_path"].rsplit("/", 1)[-1],
                summary="fixture",
                page_start=record["page_start"],
                page_end=record["page_end"],
                relevance=1,
                reason="fixture",
            )
            for record in sections[:1]
        )
        return TraversalResult(
            ranked_nodes=nodes,
            trace=TraversalTrace(
                expanded_nodes=(),
                selected_node_ids=tuple(node.node_id for node in nodes),
                stopped_reason="sufficient_evidence",
            ),
        )

    def synthesize(question: str, traversal_result: TraversalResult) -> Answer:
        del question
        node = traversal_result.ranked_nodes[0]
        return Answer(
            answer_text=f"Fixture answer. [node {node.node_id}]",
            citations=(
                Citation(
                    node_id=node.node_id,
                    paper_id=node.paper_id,
                    paper_title="fixture",
                    section_path=node.section_path,
                    page_start=node.page_start,
                    page_end=node.page_end,
                    identifier_type="doi",
                    identifier="10.0/fixture",
                ),
            ),
            budget_limited=False,
            insufficient_evidence=False,
        )

    retrieval = run_evaluation(
        "fixture-eval",
        goldset_path=FIXTURE_DIR / "goldset.yaml",
        report_dir=tmp_path,
        k=1,
        traverse_fn=traverse,
        synthesize_fn=synthesize,
        section_catalog=catalog,
        shortlist_backend="fixture",
        now=fixed_time,
    )

    extracted = tuple(
        ExtractedClaimObservation(
            id=index + 1,
            normalized_text=record["normalized_text"],
            object_value=record.get("object_value"),
            unit=record.get("unit"),
            evidence=tuple(
                ExtractedEvidenceObservation(
                    section_path=ev["section_path"],
                    stance=ev["stance"],
                )
                for ev in record["evidence"]
            ),
        )
        for index, record in enumerate(fixture_corpus["scopes"]["fixture-eval"]["extracted_claims"])
    )

    extraction = run_extraction_evaluation(
        "fixture-eval",
        goldset_path=FIXTURE_DIR / "goldset.yaml",
        report_dir=tmp_path,
        section_catalog=catalog,
        extracted_claims=extracted,
        now=fixed_time,
    )

    assert retrieval.report_path == extraction.report_path
    assert extraction.report_path == tmp_path / "eval-2026-07-30.json"
    report = json.loads(extraction.report_path.read_text())
    assert len(report["runs"]) == 2
    assert "recall_at_k" in report["runs"][0]["metrics"]
    extraction_metrics = report["runs"][1]["metrics"]
    assert set(extraction_metrics) >= {
        "claim_precision",
        "claim_recall",
        "claim_f1",
        "evidence_span_precision",
        "stance_accuracy",
    }
    assert report["runs"][1]["kind"] == "extraction"


def test_eval_cli_extraction_flag_reports_metrics(monkeypatch, tmp_path: Path) -> None:
    import ai_researcher.eval
    from ai_researcher.eval import ExtractionEvaluationResult, ExtractionMetrics

    report_path = tmp_path / "eval-2026-07-30.json"
    calls: list[str] = []

    def fake_run(scope: str) -> ExtractionEvaluationResult:
        calls.append(scope)
        return ExtractionEvaluationResult(
            scope=scope,
            claim_count=15,
            metrics=ExtractionMetrics(
                claim_precision=0.8,
                claim_recall=0.7,
                claim_f1=0.746,
                evidence_span_precision=0.65,
                stance_accuracy=0.9,
            ),
            report_path=report_path,
        )

    monkeypatch.setattr(ai_researcher.eval, "run_extraction_evaluation", fake_run)

    result = runner.invoke(
        app,
        ["eval", "--extraction", "--scope", "surface-codes"],
    )

    assert result.exit_code == 0, result.output
    assert calls == ["surface-codes"]
    assert "claim precision: 0.800" in result.stdout
    assert "claim recall: 0.700" in result.stdout
    assert "claim f1: 0.746" in result.stdout
    assert "evidence-span precision: 0.650" in result.stdout
    assert "stance accuracy: 0.900" in result.stdout
    assert str(report_path) in result.stdout
