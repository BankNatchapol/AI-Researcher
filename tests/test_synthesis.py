"""Grounded answer synthesis tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ai_researcher.retrieval import RankedNode, TraversalResult, TraversalTrace


def _answer_module():
    try:
        import ai_researcher.answer as answer
    except ModuleNotFoundError:
        pytest.fail("ai_researcher.answer has not been implemented")
    return answer


def _node(
    node_id: int,
    *,
    paper_id: int,
    section_path: str,
    page_start: int,
    page_end: int,
) -> RankedNode:
    return RankedNode(
        node_id=node_id,
        paper_id=paper_id,
        section_path=section_path,
        title=section_path.rsplit("/", 1)[-1],
        summary=f"Evidence from node {node_id}.",
        page_start=page_start,
        page_end=page_end,
        relevance=90,
        reason="Direct support",
    )


def _traversal(
    *nodes: RankedNode,
    stopped_reason: str = "sufficient_evidence",
) -> TraversalResult:
    return TraversalResult(
        ranked_nodes=nodes,
        trace=TraversalTrace(
            expanded_nodes=(),
            selected_node_ids=tuple(node.node_id for node in nodes),
            stopped_reason=stopped_reason,
        ),
    )


def test_synthesis_attributes_every_statement_to_supplied_nodes() -> None:
    answer = _answer_module()
    nodes = (
        _node(
            11,
            paper_id=101,
            section_path="Results/Threshold",
            page_start=4,
            page_end=5,
        ),
        _node(
            22,
            paper_id=202,
            section_path="Discussion/Comparison",
            page_start=8,
            page_end=8,
        ),
    )
    model_calls: list[dict[str, Any]] = []

    def fake_complete(
        messages: list[dict],
        job: str,
        schema: dict | None = None,
    ) -> dict[str, Any]:
        assert job == "answer_synthesis"
        assert schema is not None
        model_calls.append(json.loads(messages[-1]["content"]))
        return {
            "statements": [
                {"text": "The reported threshold is 1.1 percent.", "node_ids": [11]},
                {"text": "The comparison uses two decoders.", "node_ids": [11, 22]},
            ]
        }

    def fake_citation(node: RankedNode):
        return answer.Citation(
            node_id=node.node_id,
            paper_id=node.paper_id,
            paper_title=f"Paper {node.paper_id}",
            section_path=node.section_path,
            page_start=node.page_start,
            page_end=node.page_end,
            identifier_type="doi",
            identifier=f"10.1000/{node.paper_id}",
        )

    result = answer.synthesize(
        "What threshold and comparison are reported?",
        _traversal(*nodes),
        complete_fn=fake_complete,
        citation_fn=fake_citation,
    )

    assert result.insufficient_evidence is False
    assert result.answer_text is not None
    rendered_statements = result.answer_text.splitlines()
    assert rendered_statements == [
        "The reported threshold is 1.1 percent. [node 11]",
        "The comparison uses two decoders. [nodes 11, 22]",
    ]
    assert all("[node" in statement for statement in rendered_statements)
    assert [citation.node_id for citation in result.citations] == [11, 22]
    assert model_calls[0]["allowed_node_ids"] == [11, 22]


def test_citation_renders_paper_section_pages_and_identifier() -> None:
    answer = _answer_module()
    node = _node(
        11,
        paper_id=101,
        section_path="Results/Threshold",
        page_start=4,
        page_end=5,
    )

    citation = answer.render_citation(
        node,
        paper_lookup=lambda paper_id: answer.CitationPaper(
            id=paper_id,
            title="Threshold estimates for surface codes",
            doi="10.1000/surface.101",
            arxiv_id="2401.00101",
        ),
    )

    assert citation.node_id == 11
    assert citation.identifier_type == "doi"
    assert citation.identifier == "10.1000/surface.101"
    assert citation.rendered == (
        "Threshold estimates for surface codes — Results/Threshold — "
        "pp. 4–5 — DOI: 10.1000/surface.101"
    )


def test_fewer_than_two_nodes_returns_insufficient_evidence_without_synthesis() -> None:
    answer = _answer_module()
    node = _node(
        11,
        paper_id=101,
        section_path="Results/Threshold",
        page_start=4,
        page_end=5,
    )

    def unexpected_model_call(*args: Any, **kwargs: Any) -> dict:
        pytest.fail("thin evidence must not invoke answer synthesis")

    result = answer.synthesize(
        "What threshold is reported?",
        _traversal(node),
        complete_fn=unexpected_model_call,
    )

    assert result.insufficient_evidence is True
    assert result.answer_text is None
    assert result.citations == []
    assert result.message is not None
    assert "insufficient evidence" in result.message.casefold()


def test_budget_exhaustion_sets_budget_limited_on_synthesized_answer() -> None:
    answer = _answer_module()
    nodes = (
        _node(11, paper_id=101, section_path="Results", page_start=4, page_end=5),
        _node(22, paper_id=202, section_path="Discussion", page_start=8, page_end=8),
    )

    result = answer.synthesize(
        "What evidence was found before the budget ended?",
        _traversal(*nodes, stopped_reason="budget_exhausted"),
        complete_fn=lambda *args, **kwargs: {
            "statements": [{"text": "Two nodes provide partial support.", "node_ids": [11, 22]}]
        },
        citation_fn=lambda node: answer.Citation(
            node_id=node.node_id,
            paper_id=node.paper_id,
            paper_title=f"Paper {node.paper_id}",
            section_path=node.section_path,
            page_start=node.page_start,
            page_end=node.page_end,
            identifier_type="arxiv",
            identifier=f"2401.00{node.node_id}",
        ),
    )

    assert result.budget_limited is True
    assert result.insufficient_evidence is False
    assert result.answer_text == "Two nodes provide partial support. [nodes 11, 22]"


def test_unknown_node_attribution_is_regenerated_once() -> None:
    answer = _answer_module()
    nodes = (
        _node(11, paper_id=101, section_path="Results", page_start=4, page_end=5),
        _node(22, paper_id=202, section_path="Discussion", page_start=8, page_end=8),
    )
    responses = iter(
        [
            {"statements": [{"text": "Unsupported.", "node_ids": [999]}]},
            {"statements": [{"text": "Supported.", "node_ids": [11]}]},
        ]
    )
    attempts: list[dict[str, Any]] = []

    def fake_complete(
        messages: list[dict],
        job: str,
        schema: dict | None = None,
    ) -> dict[str, Any]:
        attempts.append(json.loads(messages[-1]["content"]))
        return next(responses)

    result = answer.synthesize(
        "What is supported?",
        _traversal(*nodes),
        complete_fn=fake_complete,
        citation_fn=lambda node: answer.Citation(
            node_id=node.node_id,
            paper_id=node.paper_id,
            paper_title="Paper",
            section_path=node.section_path,
            page_start=node.page_start,
            page_end=node.page_end,
            identifier_type="doi",
            identifier="10.1000/paper",
        ),
    )

    assert len(attempts) == 2
    assert attempts[1]["regeneration"] is True
    assert result.answer_text == "Supported. [node 11]"


def test_second_invalid_attribution_returns_insufficient_evidence() -> None:
    answer = _answer_module()
    nodes = (
        _node(11, paper_id=101, section_path="Results", page_start=4, page_end=5),
        _node(22, paper_id=202, section_path="Discussion", page_start=8, page_end=8),
    )
    attempts = 0

    def invalid_complete(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        return {"statements": [{"text": "Still unsupported.", "node_ids": [999]}]}

    result = answer.synthesize(
        "What is supported?",
        _traversal(*nodes),
        complete_fn=invalid_complete,
    )

    assert attempts == 2
    assert result.insufficient_evidence is True
    assert result.answer_text is None
    assert result.citations == []


def test_any_unattributed_statement_returns_insufficient_evidence() -> None:
    answer = _answer_module()
    nodes = (
        _node(11, paper_id=101, section_path="Results", page_start=4, page_end=5),
        _node(22, paper_id=202, section_path="Discussion", page_start=8, page_end=8),
    )
    attempts = 0

    def partly_unattributed_complete(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        return {
            "statements": [
                {"text": "Supported.", "node_ids": [11]},
                {"text": "Missing its attribution.", "node_ids": []},
            ]
        }

    result = answer.synthesize(
        "What is supported?",
        _traversal(*nodes),
        complete_fn=partly_unattributed_complete,
        citation_fn=lambda node: answer.Citation(
            node_id=node.node_id,
            paper_id=node.paper_id,
            paper_title="Paper",
            section_path=node.section_path,
            page_start=node.page_start,
            page_end=node.page_end,
            identifier_type="doi",
            identifier="10.1000/paper",
        ),
    )

    assert attempts == 2
    assert result.insufficient_evidence is True
    assert result.answer_text is None
    assert result.citations == []
