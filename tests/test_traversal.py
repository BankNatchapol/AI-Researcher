"""Tests for budgeted, vectorless traversal over persisted paper trees."""

from __future__ import annotations

import json
from typing import Any

import pytest


class FakeTraversalStore:
    """Offline store double that records exactly what traversal persists."""

    def __init__(self, nodes: list[Any], scope_id: int = 17) -> None:
        self.nodes = tuple(nodes)
        self.scope_id = scope_id
        self.loads: list[tuple[str, list[int]]] = []
        self.writes: list[dict[str, Any]] = []

    def load_scope_tree(self, scope: str, paper_ids: list[int]) -> tuple[int, tuple[Any, ...]]:
        self.loads.append((scope, paper_ids))
        selected = tuple(node for node in self.nodes if node.paper_id in paper_ids)
        return self.scope_id, selected

    def write_trace(self, **values: Any) -> None:
        self.writes.append(values)


def _node(
    node_id: int,
    *,
    paper_id: int = 101,
    parent_id: int | None = None,
    path: str | None = None,
):
    from ai_researcher.retrieval.traverse import TraversalNode

    return TraversalNode(
        id=node_id,
        paper_id=paper_id,
        parent_id=parent_id,
        section_path=path or f"Section {node_id}",
        title=f"Node {node_id}",
        summary=f"Summary for node {node_id}",
        page_start=node_id,
        page_end=node_id + 1,
    )


def _model_response(
    payload: dict[str, Any],
    *,
    selected: set[int] | None = None,
    expanded: set[int] | None = None,
    relevance: dict[int, int] | None = None,
    sufficient_evidence: bool = False,
) -> dict[str, Any]:
    selected = set() if selected is None else selected
    expanded = set() if expanded is None else expanded
    relevance = {} if relevance is None else relevance
    return {
        "judgements": [
            {
                "node_id": node["node_id"],
                "relevance": relevance.get(node["node_id"], 10),
                "selected": node["node_id"] in selected,
                "expand": node["node_id"] in expanded,
                "reason": f"judged node {node['node_id']}",
            }
            for node in payload["nodes"]
        ],
        "sufficient_evidence": sufficient_evidence,
    }


def _set_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/research")
    monkeypatch.setenv("GROBID_URL", "http://localhost:8070")
    monkeypatch.setenv("LLM_BACKEND_DEFAULT", "codex")
    monkeypatch.setenv("CONTACT_EMAIL", "researcher@example.com")


def test_traverse_returns_ranked_nodes_and_full_expansion_trace() -> None:
    from ai_researcher.retrieval.traverse import traverse

    store = FakeTraversalStore(
        [
            _node(1),
            _node(2, parent_id=1, path="Results > Threshold"),
            _node(3, parent_id=1, path="Results > Decoder"),
            _node(4, parent_id=2, path="Results > Threshold > Details"),
        ]
    )
    shortlist_calls: list[tuple[str, str, int]] = []
    model_calls: list[dict[str, Any]] = []

    def fake_shortlist(scope: str, question: str, limit: int) -> list[int]:
        shortlist_calls.append((scope, question, limit))
        return [101]

    def fake_complete(
        messages: list[dict],
        job: str,
        schema: dict | None = None,
    ) -> dict[str, Any]:
        assert job == "traversal"
        assert schema is not None
        payload = json.loads(messages[-1]["content"])
        model_calls.append(payload)
        if len(model_calls) == 1:
            assert [node["node_id"] for node in payload["nodes"]] == [1]
            return _model_response(payload, expanded={1})
        assert [node["node_id"] for node in payload["nodes"]] == [2, 3]
        return _model_response(
            payload,
            selected={2, 3},
            relevance={2: 61, 3: 94},
            sufficient_evidence=True,
        )

    result = traverse(
        "Which decoder performs best?",
        "surface-codes",
        max_nodes=10,
        shortlist_fn=fake_shortlist,
        complete_fn=fake_complete,
        store=store,
    )

    assert shortlist_calls == [("surface-codes", "Which decoder performs best?", 20)]
    assert [node.node_id for node in result.ranked_nodes] == [3, 2]
    assert result.nodes == result.ranked_nodes
    assert [item.node_id for item in result.trace.expanded_nodes] == [1, 2, 3]
    assert [item.reason for item in result.trace.expanded_nodes] == [
        "judged node 1",
        "judged node 2",
        "judged node 3",
    ]
    assert result.trace.nodes_expanded == 3
    assert result.trace.stopped_reason == "sufficient_evidence"
    assert len(model_calls) == 2
    assert store.writes == [
        {
            "question": "Which decoder performs best?",
            "scope_id": 17,
            "expanded_node_ids": [1, 2, 3],
            "selected_node_ids": [3, 2],
            "nodes_expanded": 3,
            "stopped_reason": "sufficient_evidence",
        }
    ]


def test_traversal_never_expands_more_than_three_nodes() -> None:
    from ai_researcher.retrieval.traverse import traverse

    store = FakeTraversalStore([_node(node_id) for node_id in range(1, 13)])
    expanded_by_model: list[int] = []

    def fake_complete(
        messages: list[dict],
        job: str,
        schema: dict | None = None,
    ) -> dict[str, Any]:
        assert job == "traversal"
        assert schema is not None
        payload = json.loads(messages[-1]["content"])
        expanded_by_model.extend(node["node_id"] for node in payload["nodes"])
        return _model_response(payload)

    result = traverse(
        "Find relevant evidence",
        "large-corpus",
        max_nodes=3,
        shortlist_fn=lambda scope, question, limit: [101],
        complete_fn=fake_complete,
        store=store,
    )

    assert expanded_by_model == [1, 2, 3]
    assert result.trace.nodes_expanded == 3
    assert result.trace.stopped_reason == "budget_exhausted"
    assert len(store.writes) == 1
    assert store.writes[0]["nodes_expanded"] == 3


def test_depleted_frontier_with_remaining_budget_is_not_budget_exhausted() -> None:
    from ai_researcher.retrieval.traverse import traverse

    store = FakeTraversalStore([_node(1), _node(2, parent_id=1)])

    def fake_complete(
        messages: list[dict],
        job: str,
        schema: dict | None = None,
    ) -> dict[str, Any]:
        assert job == "traversal"
        assert schema is not None
        payload = json.loads(messages[-1]["content"])
        return _model_response(payload, sufficient_evidence=False)

    result = traverse(
        "Find relevant evidence",
        "surface-codes",
        max_nodes=10,
        shortlist_fn=lambda scope, question, limit: [101],
        complete_fn=fake_complete,
        store=store,
    )

    assert result.trace.nodes_expanded == 1
    assert result.trace.stopped_reason == "no_candidates"
    assert store.writes[0]["stopped_reason"] == "no_candidates"


@pytest.mark.parametrize(
    ("configured_limit", "call_limit", "expected_limit"),
    [
        (None, None, 40),
        ("2", None, 2),
        ("2", 3, 3),
    ],
)
def test_node_budget_defaults_and_overrides(
    monkeypatch: pytest.MonkeyPatch,
    configured_limit: str | None,
    call_limit: int | None,
    expected_limit: int,
) -> None:
    from ai_researcher.retrieval.traverse import traverse

    _set_required_environment(monkeypatch)
    if configured_limit is None:
        monkeypatch.delenv("TRAVERSAL_MAX_NODES", raising=False)
    else:
        monkeypatch.setenv("TRAVERSAL_MAX_NODES", configured_limit)
    store = FakeTraversalStore([_node(node_id) for node_id in range(1, 51)])
    batch_sizes: list[int] = []

    def fake_complete(
        messages: list[dict],
        job: str,
        schema: dict | None = None,
    ) -> dict[str, Any]:
        assert job == "traversal"
        assert schema is not None
        payload = json.loads(messages[-1]["content"])
        batch_sizes.append(len(payload["nodes"]))
        return _model_response(payload)

    result = traverse(
        "How much evidence is available?",
        "surface-codes",
        max_nodes=call_limit,
        shortlist_fn=lambda scope, question, limit: [101],
        complete_fn=fake_complete,
        store=store,
    )

    assert batch_sizes == [expected_limit]
    assert result.trace.nodes_expanded == expected_limit


def test_no_shortlisted_candidates_writes_one_trace_without_expansion_call() -> None:
    from ai_researcher.retrieval.traverse import traverse

    store = FakeTraversalStore([])

    def fail_if_called(*args: Any, **kwargs: Any) -> dict:
        raise AssertionError("The traversal LLM must not run without shortlisted papers")

    result = traverse(
        "Question outside the corpus",
        "surface-codes",
        shortlist_fn=lambda scope, question, limit: [],
        complete_fn=fail_if_called,
        store=store,
    )

    assert result.ranked_nodes == ()
    assert result.trace.expanded_nodes == ()
    assert result.trace.stopped_reason == "no_candidates"
    assert store.loads == [("surface-codes", [])]
    assert store.writes == [
        {
            "question": "Question outside the corpus",
            "scope_id": 17,
            "expanded_node_ids": [],
            "selected_node_ids": [],
            "nodes_expanded": 0,
            "stopped_reason": "no_candidates",
        }
    ]


@pytest.mark.parametrize("limit", [0, -1])
def test_expansion_budget_rejects_nonpositive_limits(limit: int) -> None:
    from ai_researcher.retrieval.budget import ExpansionBudget

    with pytest.raises(ValueError, match="positive"):
        ExpansionBudget(limit)
