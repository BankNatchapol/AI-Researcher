"""Tests for batched, cross-paper claim evidence linking."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from ai_researcher.cli import app
from ai_researcher.extraction.pipeline import ExtractScopeResult
from ai_researcher.retrieval import RankedNode, TraversalResult, TraversalTrace


def _traversal(*nodes: RankedNode) -> TraversalResult:
    return TraversalResult(
        ranked_nodes=tuple(nodes),
        trace=TraversalTrace(
            expanded_nodes=(),
            selected_node_ids=tuple(node.node_id for node in nodes),
            stopped_reason="sufficient_evidence",
        ),
    )


def _ranked_node(node_id: int, paper_id: int) -> RankedNode:
    return RankedNode(
        node_id=node_id,
        paper_id=paper_id,
        section_path=f"Results/{node_id}",
        title=f"Node {node_id}",
        summary=f"Candidate evidence {node_id}.",
        page_start=1,
        page_end=1,
        relevance=90,
        reason="Relevant to the claim.",
    )


def _memory_store(module: Any, nodes: list[Any]) -> Any:
    class MemoryEvidenceStore:
        def __init__(self) -> None:
            self.nodes = {node.node_id: node for node in nodes}
            self.saved: list[Any] = []
            self.save_calls = 0

        def resolve_scope(self, claim: Any) -> str:
            del claim
            return "surface-codes"

        def load_candidate_nodes(self, node_ids: list[int]) -> tuple[Any, ...]:
            return tuple(self.nodes[node_id] for node_id in node_ids)

        def save_links(self, claim_id: int, links: list[Any]) -> list[Any]:
            assert claim_id == 7
            self.save_calls += 1
            self.saved = list(links)
            return list(links)

    return MemoryEvidenceStore()


def test_link_evidence_assigns_all_stances_and_keeps_cross_paper_nodes() -> None:
    from ai_researcher.evidence import link as evidence_link

    claim = {"id": 7, "paper_id": 101, "normalized_text": "method lowers logical error rate"}
    nodes = [
        evidence_link.CandidateNode(
            node_id=11,
            paper_id=101,
            body_text="The method lowers the logical error rate by 20 percent.",
        ),
        evidence_link.CandidateNode(
            node_id=22,
            paper_id=202,
            body_text="Our measurements show the method does not lower the logical error rate.",
        ),
        evidence_link.CandidateNode(
            node_id=33,
            paper_id=202,
            body_text="The method and logical error rate are discussed in Appendix B.",
        ),
    ]
    store = _memory_store(evidence_link, nodes)
    traversal_calls: list[tuple[str, str]] = []
    gateway_calls: list[dict[str, Any]] = []

    def fake_traverse(question: str, scope: str) -> TraversalResult:
        traversal_calls.append((question, scope))
        return _traversal(
            _ranked_node(11, 101),
            _ranked_node(22, 202),
            _ranked_node(33, 202),
        )

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        assert job == "stance"
        assert schema is not None
        payload = json.loads(messages[-1]["content"])
        gateway_calls.append(payload)
        return {
            "classifications": [
                {
                    "node_id": 11,
                    "stance": "supports",
                    "rationale": "The method lowers the logical error rate by 20 percent.",
                },
                {
                    "node_id": 22,
                    "stance": "refutes",
                    "rationale": (
                        "Our measurements show the method does not lower the logical error rate."
                    ),
                },
                {
                    "node_id": 33,
                    "stance": "mentions",
                    "rationale": ("The method and logical error rate are discussed in Appendix B."),
                },
            ]
        }

    links = evidence_link.link_evidence(
        claim,
        traverse_fn=fake_traverse,
        complete_fn=fake_complete,
        store=store,
    )

    assert traversal_calls == [("method lowers logical error rate", "surface-codes")]
    assert len(gateway_calls) == 1
    assert [candidate["node_id"] for candidate in gateway_calls[0]["candidate_nodes"]] == [
        11,
        22,
        33,
    ]
    assert [(link.tree_node_id, link.paper_id, link.stance) for link in links] == [
        (11, 101, "supports"),
        (22, 202, "refutes"),
        (33, 202, "mentions"),
    ]
    assert any(link.paper_id != claim["paper_id"] for link in links)
    assert store.saved == links


def test_link_evidence_rejects_non_verbatim_rationale_before_persistence() -> None:
    from ai_researcher.evidence import link as evidence_link

    claim = {"id": 7, "paper_id": 101, "normalized_text": "decoder improves accuracy"}
    nodes = [
        evidence_link.CandidateNode(
            node_id=11,
            paper_id=101,
            body_text="The decoder improves accuracy by five percent.",
        ),
        evidence_link.CandidateNode(
            node_id=22,
            paper_id=202,
            body_text="The independent evaluation found no measurable improvement.",
        ),
    ]
    store = _memory_store(evidence_link, nodes)

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del messages, schema
        assert job == "stance"
        return {
            "classifications": [
                {
                    "node_id": 11,
                    "stance": "supports",
                    "rationale": "The decoder improves accuracy by five percent.",
                },
                {
                    "node_id": 22,
                    "stance": "refutes",
                    "rationale": "A separate study found the decoder ineffective.",
                },
            ]
        }

    links = evidence_link.link_evidence(
        claim,
        traverse_fn=lambda question, scope: _traversal(
            _ranked_node(11, 101),
            _ranked_node(22, 202),
        ),
        complete_fn=fake_complete,
        store=store,
    )

    assert [link.tree_node_id for link in links] == [11]
    assert links[0].rationale_text in nodes[0].body_text
    assert [link.tree_node_id for link in store.saved] == [11]


def test_link_evidence_rejects_incomplete_batch_without_persistence() -> None:
    from ai_researcher.evidence import link as evidence_link

    claim = {"id": 7, "paper_id": 101, "normalized_text": "decoder improves accuracy"}
    nodes = [
        evidence_link.CandidateNode(
            node_id=11,
            paper_id=101,
            body_text="The decoder improves accuracy by five percent.",
        ),
        evidence_link.CandidateNode(
            node_id=22,
            paper_id=202,
            body_text="The independent evaluation found no measurable improvement.",
        ),
    ]
    store = _memory_store(evidence_link, nodes)

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        del messages, schema
        assert job == "stance"
        return {
            "classifications": [
                {
                    "node_id": 11,
                    "stance": "supports",
                    "rationale": "The decoder improves accuracy by five percent.",
                }
            ]
        }

    with pytest.raises(
        evidence_link.EvidenceLinkingError,
        match="classify every candidate node exactly once",
    ):
        evidence_link.link_evidence(
            claim,
            traverse_fn=lambda question, scope: _traversal(
                _ranked_node(11, 101),
                _ranked_node(22, 202),
            ),
            complete_fn=fake_complete,
            store=store,
        )

    assert store.save_calls == 0
    assert store.saved == []


def test_verbatim_span_preserves_exact_source_whitespace() -> None:
    from ai_researcher.evidence.link import _verbatim_span

    body_text = "The decoder lowers\n  the logical error rate by 20 percent."
    model_rationale = "The decoder lowers the logical error rate by 20 percent."

    rationale_text = _verbatim_span(body_text, model_rationale)

    assert rationale_text == "The decoder lowers\n  the logical error rate by 20 percent."
    assert rationale_text in body_text


def test_link_evidence_batches_every_candidate_in_one_stance_call() -> None:
    from ai_researcher.evidence import link as evidence_link

    claim = {"id": 7, "paper_id": 101, "normalized_text": "batched claim"}
    nodes = [
        evidence_link.CandidateNode(
            node_id=node_id,
            paper_id=100 + node_id,
            body_text=f"Exact rationale for node {node_id}.",
        )
        for node_id in range(1, 9)
    ]
    store = _memory_store(evidence_link, nodes)
    call_count = 0

    def fake_complete(messages: list[dict], job: str, schema: dict | None = None) -> dict:
        nonlocal call_count
        del schema
        assert job == "stance"
        call_count += 1
        payload = json.loads(messages[-1]["content"])
        return {
            "classifications": [
                {
                    "node_id": candidate["node_id"],
                    "stance": "mentions",
                    "rationale": candidate["body_text"],
                }
                for candidate in payload["candidate_nodes"]
            ]
        }

    links = evidence_link.link_evidence(
        claim,
        traverse_fn=lambda question, scope: _traversal(
            *[_ranked_node(node.node_id, node.paper_id) for node in nodes]
        ),
        complete_fn=fake_complete,
        store=store,
    )

    assert len(links) == len(nodes)
    assert call_count == 1


def test_extract_cli_links_evidence_by_default_and_allows_opt_out(monkeypatch) -> None:
    from ai_researcher.evidence import link as evidence_link
    from ai_researcher.extraction import pipeline

    monkeypatch.setattr(
        pipeline,
        "extract_scope",
        lambda scope_name: ExtractScopeResult(extracted=0, skipped=0, failed=0),
    )
    linked_scopes: list[str] = []

    def fake_link_scope(scope_name: str) -> SimpleNamespace:
        linked_scopes.append(scope_name)
        return SimpleNamespace(claims_linked=2, evidence_links=3, failed=0)

    monkeypatch.setattr(evidence_link, "link_scope_evidence", fake_link_scope)
    runner = CliRunner()

    default_result = runner.invoke(app, ["extract", "surface-codes", "--no-dedup"])
    disabled_result = runner.invoke(
        app,
        ["extract", "surface-codes", "--no-link-evidence", "--no-dedup"],
    )

    assert default_result.exit_code == 0, default_result.output
    assert "Evidence linking complete: claims=2 links=3 failed=0." in default_result.stdout
    assert disabled_result.exit_code == 0, disabled_result.output
    assert linked_scopes == ["surface-codes"]
