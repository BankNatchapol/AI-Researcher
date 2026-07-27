"""Tests for the grounded question-answering CLI surface."""

from __future__ import annotations

import json
from collections.abc import Callable

from typer.testing import CliRunner

from ai_researcher.answer import Answer, Citation
from ai_researcher.cli import app
from ai_researcher.retrieval import (
    ExpandedNode,
    RankedNode,
    TraversalResult,
    TraversalTrace,
)

runner = CliRunner()


def _citation(node_id: int, *, paper_id: int, section_path: str) -> Citation:
    return Citation(
        node_id=node_id,
        paper_id=paper_id,
        paper_title=f"Paper {paper_id}",
        section_path=section_path,
        page_start=4,
        page_end=5,
        identifier_type="doi",
        identifier=f"10.1000/{paper_id}",
    )


def _traversal(stopped_reason: str = "sufficient_evidence") -> TraversalResult:
    ranked_nodes = (
        RankedNode(
            node_id=11,
            paper_id=101,
            section_path="Results/Threshold",
            title="Threshold",
            summary="A threshold estimate.",
            page_start=4,
            page_end=5,
            relevance=96,
            reason="Directly reports the threshold.",
        ),
        RankedNode(
            node_id=22,
            paper_id=202,
            section_path="Discussion/Comparison",
            title="Comparison",
            summary="A comparison with prior work.",
            page_start=8,
            page_end=8,
            relevance=88,
            reason="Provides corroborating context.",
        ),
    )
    expanded_nodes = tuple(
        ExpandedNode(
            node_id=node.node_id,
            paper_id=node.paper_id,
            section_path=node.section_path,
            page_start=node.page_start,
            page_end=node.page_end,
            relevance=node.relevance,
            selected=True,
            expand_children=node.node_id == 11,
            reason=node.reason,
        )
        for node in ranked_nodes
    )
    return TraversalResult(
        ranked_nodes=ranked_nodes,
        trace=TraversalTrace(
            expanded_nodes=expanded_nodes,
            selected_node_ids=(11, 22),
            stopped_reason=stopped_reason,
        ),
    )


def _answer(*, budget_limited: bool = False) -> Answer:
    return Answer(
        answer_text=(
            "The reported threshold is 1.1 percent. [node 11]\n"
            "A second paper provides a comparison. [node 22]"
        ),
        citations=[
            _citation(11, paper_id=101, section_path="Results/Threshold"),
            _citation(22, paper_id=202, section_path="Discussion/Comparison"),
        ],
        budget_limited=budget_limited,
        insufficient_evidence=False,
    )


def _install_core_fakes(
    monkeypatch,
    *,
    traversal: TraversalResult,
    answer_factory: Callable[[], Answer],
) -> list[tuple[str, str, int | None]]:
    import ai_researcher.answer
    import ai_researcher.retrieval

    traversal_calls: list[tuple[str, str, int | None]] = []

    def fake_traverse(question: str, scope: str, max_nodes: int | None = None):
        traversal_calls.append((question, scope, max_nodes))
        return traversal

    def fake_synthesize(question: str, traversal_result: TraversalResult):
        assert question
        assert traversal_result is traversal
        return answer_factory()

    monkeypatch.setattr(ai_researcher.retrieval, "traverse", fake_traverse)
    monkeypatch.setattr(ai_researcher.answer, "synthesize", fake_synthesize)
    return traversal_calls


def test_ask_prints_answer_and_numbered_citations(monkeypatch) -> None:
    calls = _install_core_fakes(
        monkeypatch,
        traversal=_traversal(),
        answer_factory=_answer,
    )

    result = runner.invoke(
        app,
        ["ask", "What threshold is reported?", "--scope", "surface-codes"],
    )

    assert result.exit_code == 0, result.output
    assert calls == [("What threshold is reported?", "surface-codes", None)]
    assert "The reported threshold is 1.1 percent. [1]" in result.stdout
    assert "A second paper provides a comparison. [2]" in result.stdout
    assert "[1] Paper 101 — Results/Threshold — pp. 4–5" in result.stdout
    assert "[2] Paper 202 — Discussion/Comparison — pp. 4–5" in result.stdout
    assert "Traversal trace" not in result.stdout


def test_ask_verbose_prints_expanded_nodes_and_stopping_reason(monkeypatch) -> None:
    _install_core_fakes(
        monkeypatch,
        traversal=_traversal(),
        answer_factory=_answer,
    )

    result = runner.invoke(
        app,
        [
            "ask",
            "What threshold is reported?",
            "--scope",
            "surface-codes",
            "--verbose",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Traversal trace" in result.stdout
    assert "node 11" in result.stdout
    assert "Results/Threshold" in result.stdout
    assert "Directly reports the threshold." in result.stdout
    assert "Stopping reason: sufficient_evidence" in result.stdout


def test_ask_json_emits_machine_readable_output_only(monkeypatch) -> None:
    _install_core_fakes(
        monkeypatch,
        traversal=_traversal(),
        answer_factory=_answer,
    )

    result = runner.invoke(
        app,
        [
            "ask",
            "What threshold is reported?",
            "--scope",
            "surface-codes",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["answer"].startswith("The reported threshold")
    assert payload["citations"][0] == {
        "number": 1,
        "node_id": 11,
        "paper_id": 101,
        "paper_title": "Paper 101",
        "section_path": "Results/Threshold",
        "page_start": 4,
        "page_end": 5,
        "identifier_type": "doi",
        "identifier": "10.1000/101",
    }
    assert payload["trace"] == {
        "nodes_expanded": 2,
        "selected_node_ids": [11, 22],
        "stopped_reason": "sufficient_evidence",
    }
    assert result.stdout.strip() == json.dumps(payload, ensure_ascii=False)


def test_ask_max_nodes_override_labels_budget_limited_output(monkeypatch) -> None:
    calls = _install_core_fakes(
        monkeypatch,
        traversal=_traversal("budget_exhausted"),
        answer_factory=lambda: _answer(budget_limited=True),
    )

    result = runner.invoke(
        app,
        [
            "ask",
            "What threshold is reported?",
            "--scope",
            "surface-codes",
            "--max-nodes",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [("What threshold is reported?", "surface-codes", 2)]
    assert "BUDGET-LIMITED" in result.stdout


def test_ask_insufficient_evidence_is_an_explicit_successful_result(monkeypatch) -> None:
    insufficient = Answer(
        answer_text=None,
        citations=[],
        budget_limited=False,
        insufficient_evidence=True,
        message="Insufficient evidence: at least two supporting nodes are required.",
    )
    _install_core_fakes(
        monkeypatch,
        traversal=_traversal("no_candidates"),
        answer_factory=lambda: insufficient,
    )

    result = runner.invoke(
        app,
        ["ask", "Is there evidence?", "--scope", "surface-codes"],
    )

    assert result.exit_code == 0, result.output
    assert "Insufficient evidence" in result.stdout
    assert "Citations" not in result.stdout
