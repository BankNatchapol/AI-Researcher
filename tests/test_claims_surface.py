"""Claims CLI and MCP surface — both scores stay separate everywhere."""

from __future__ import annotations

import re
from typing import Any

import pytest
from typer.testing import CliRunner

from ai_researcher.answer.citation import Citation
from ai_researcher.claims.query import (
    ClaimDetail,
    ClaimEvidenceItem,
    ClaimFilters,
    ClaimSummary,
    ScoreFactor,
    find_claim_evidence,
    get_claim,
    list_claims,
)
from ai_researcher.claims.render import render_claim_detail, render_claims_table
from ai_researcher.cli import app

runner = CliRunner()

_COMBINED_SCORE_PATTERNS = (
    re.compile(r"\b(?:combined|blended|averaged|overall)\s+score\b", re.IGNORECASE),
    re.compile(r"\b(?:confidence\s*[+/×*]\s*evidence[_\s-]?quality)\b", re.IGNORECASE),
    re.compile(r"\b(?:evidence[_\s-]?quality\s*[+/×*]\s*confidence)\b", re.IGNORECASE),
    re.compile(r"\bavg(?:erage)?\s*\(\s*confidence\b", re.IGNORECASE),
)


def _factor(name: str, raw: Any, contribution: float, maximum: float = 25.0) -> ScoreFactor:
    return ScoreFactor(
        name=name,
        raw_value=raw,
        contribution=contribution,
        max_contribution=maximum,
    )


def _citation(node_id: int = 11, paper_id: int = 101) -> Citation:
    return Citation(
        node_id=node_id,
        paper_id=paper_id,
        paper_title=f"Paper {paper_id}",
        section_path="Results/Threshold",
        page_start=4,
        page_end=5,
        identifier_type="doi",
        identifier=f"10.1000/{paper_id}",
    )


def _summary(
    *,
    claim_id: int = 1,
    claim_type: str = "threshold",
    confidence: int = 80,
    evidence_quality: int = 72,
    replication_count: int = 2,
    claim_text: str = "Surface-code threshold is 1%.",
) -> ClaimSummary:
    return ClaimSummary(
        id=claim_id,
        claim_text=claim_text,
        claim_type=claim_type,
        paper_id=101,
        confidence=confidence,
        evidence_quality=evidence_quality,
        replication_count=replication_count,
    )


def _detail(*, claim_id: int = 1) -> ClaimDetail:
    summary = _summary(claim_id=claim_id)
    return ClaimDetail(
        id=summary.id,
        claim_text=summary.claim_text,
        claim_type=summary.claim_type,
        paper_id=summary.paper_id,
        confidence=summary.confidence,
        evidence_quality=summary.evidence_quality,
        replication_count=summary.replication_count,
        confidence_factors=(
            _factor("independent_supporting_nodes", 2, 16.0, 25.0),
            _factor("verbatim_overlap", 0.8, 20.0, 25.0),
        ),
        evidence_quality_factors=(
            _factor("full_text", "parsed", 20.0, 20.0),
            _factor("replication", 2, 15.0, 20.0),
        ),
        evidence=(
            ClaimEvidenceItem(
                tree_node_id=11,
                paper_id=101,
                stance="supports",
                rationale_text="The threshold is reported as 1%.",
                citation=_citation(11, 101),
            ),
            ClaimEvidenceItem(
                tree_node_id=22,
                paper_id=202,
                stance="refutes",
                rationale_text="Prior work found no such threshold.",
                citation=_citation(22, 202),
            ),
        ),
    )


def _assert_no_combined_score(text: str) -> None:
    for pattern in _COMBINED_SCORE_PATTERNS:
        assert pattern.search(text) is None, f"combined-score phrasing found: {pattern.pattern}"
    assert "confidence" in text.lower()
    assert "evidence_quality" in text.lower() or "evidence quality" in text.lower()


def test_render_claims_table_uses_separate_score_columns() -> None:
    output = render_claims_table(
        (
            _summary(claim_id=1, confidence=90, evidence_quality=40),
            _summary(claim_id=2, confidence=30, evidence_quality=85, replication_count=3),
        )
    )

    header = output.splitlines()[0]
    assert "confidence" in header
    assert "evidence_quality" in header
    assert "replication" in header
    # Separate labelled columns — never one blended score heading.
    assert "score" not in header.replace("evidence_quality", "")
    _assert_no_combined_score(output)
    assert "90" in output and "40" in output
    assert "30" in output and "85" in output


def test_render_claim_detail_shows_factors_and_evidence_without_blending() -> None:
    output = render_claim_detail(_detail())

    assert "Surface-code threshold is 1%." in output
    assert "confidence" in output.lower()
    assert "evidence_quality" in output.lower() or "evidence quality" in output.lower()
    assert "independent_supporting_nodes" in output
    assert "replication" in output
    assert "supports" in output
    assert "refutes" in output
    assert "The threshold is reported as 1%." in output
    assert "Prior work found no such threshold." in output
    assert "Paper 101" in output
    _assert_no_combined_score(output)


def test_list_claims_filters_min_quality_independently_of_confidence() -> None:
    claims = (
        _summary(claim_id=1, confidence=95, evidence_quality=40, claim_type="threshold"),
        _summary(claim_id=2, confidence=20, evidence_quality=80, claim_type="threshold"),
        _summary(claim_id=3, confidence=70, evidence_quality=75, claim_type="error_rate"),
    )

    filtered = list_claims(
        ClaimFilters(scope="surface-codes", min_quality=70),
        claims=claims,
    )

    assert [claim.id for claim in filtered] == [2, 3]
    assert all(claim.evidence_quality >= 70 for claim in filtered)
    # High confidence alone must not pass the quality filter.
    assert 1 not in {claim.id for claim in filtered}


def test_list_claims_filters_type_and_min_confidence() -> None:
    claims = (
        _summary(claim_id=1, confidence=80, evidence_quality=70, claim_type="threshold"),
        _summary(claim_id=2, confidence=50, evidence_quality=90, claim_type="threshold"),
        _summary(claim_id=3, confidence=90, evidence_quality=90, claim_type="error_rate"),
    )

    by_type = list_claims(
        ClaimFilters(scope="surface-codes", claim_type="threshold"),
        claims=claims,
    )
    by_confidence = list_claims(
        ClaimFilters(scope="surface-codes", min_confidence=70),
        claims=claims,
    )

    assert [claim.id for claim in by_type] == [1, 2]
    assert [claim.id for claim in by_confidence] == [1, 3]


def test_claims_cli_lists_separate_score_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ai_researcher.claims.query.list_claims",
        lambda filters, **kwargs: (_summary(claim_id=7, confidence=88, evidence_quality=61),),
    )

    result = runner.invoke(app, ["claims", "--scope", "surface-codes"])

    assert result.exit_code == 0, result.output
    assert "confidence" in result.output
    assert "evidence_quality" in result.output
    assert "88" in result.output
    assert "61" in result.output
    _assert_no_combined_score(result.output)


def test_claims_cli_min_quality_filter_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_list(filters: ClaimFilters, **kwargs: Any) -> tuple[ClaimSummary, ...]:
        seen["filters"] = filters
        return (_summary(claim_id=2, confidence=15, evidence_quality=77),)

    monkeypatch.setattr("ai_researcher.claims.query.list_claims", fake_list)

    result = runner.invoke(
        app,
        [
            "claims",
            "--scope",
            "surface-codes",
            "--type",
            "threshold",
            "--min-confidence",
            "10",
            "--min-quality",
            "70",
        ],
    )

    assert result.exit_code == 0, result.output
    filters = seen["filters"]
    assert filters.scope == "surface-codes"
    assert filters.claim_type == "threshold"
    assert filters.min_confidence == 10
    assert filters.min_quality == 70
    assert "77" in result.output


def test_claim_show_cli_prints_factors_and_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ai_researcher.claims.query.get_claim",
        lambda claim_id: _detail(claim_id=9),
    )

    result = runner.invoke(app, ["claim", "show", "9"])

    assert result.exit_code == 0, result.output
    assert "Surface-code threshold is 1%." in result.output
    assert "independent_supporting_nodes" in result.output
    assert "supports" in result.output
    assert "The threshold is reported as 1%." in result.output
    _assert_no_combined_score(result.output)


def test_mcp_claim_tools_keep_scores_as_distinct_top_level_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_researcher.mcp import server

    monkeypatch.setattr(
        "ai_researcher.claims.query.list_claims",
        lambda filters, **kwargs: (_summary(claim_id=3, confidence=66, evidence_quality=71),),
    )
    monkeypatch.setattr(
        "ai_researcher.claims.query.get_claim",
        lambda claim_id: _detail(claim_id=claim_id),
    )
    monkeypatch.setattr(
        "ai_researcher.claims.query.find_claim_evidence",
        lambda claim_id: _detail(claim_id=claim_id).evidence,
    )

    listed = server.list_claims_tool(scope="surface-codes", min_quality=70)
    detail = server.get_claim_tool(claim_id=1)
    evidence = server.find_claim_evidence_tool(claim_id=1)

    assert "claims" in listed
    claim = listed["claims"][0]
    assert claim["confidence"] == 66
    assert claim["evidence_quality"] == 71
    assert "combined_score" not in claim
    assert "score" not in claim

    assert detail["confidence"] == 80
    assert detail["evidence_quality"] == 72
    assert "combined_score" not in detail
    assert isinstance(detail["confidence_factors"], list)
    assert isinstance(detail["evidence_quality_factors"], list)

    assert evidence["claim_id"] == 1
    assert evidence["evidence"][0]["stance"] == "supports"
    assert evidence["evidence"][0]["rationale_text"] == "The threshold is reported as 1%."


def test_find_claim_evidence_and_get_claim_return_detail_objects() -> None:
    detail = _detail(claim_id=4)
    assert get_claim(4, claim=detail) == detail
    assert find_claim_evidence(4, claim=detail) == detail.evidence
