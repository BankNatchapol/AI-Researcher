"""Contract tests for the stdio MCP surface."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ai_researcher.answer import Answer, Citation
from ai_researcher.cli import app
from ai_researcher.corpus.status import FailedPaper, ScopeStatus
from ai_researcher.retrieval import RankedNode, TraversalResult, TraversalTrace
from ai_researcher.scoping import ScopeDefinition

REPO_ROOT = Path(__file__).parents[1]
MAIN_REPO_ROOT = REPO_ROOT.parents[1] if REPO_ROOT.parent.name == ".worktrees" else REPO_ROOT
runner = CliRunner()


def _server_module():
    try:
        from ai_researcher.mcp import server
    except ModuleNotFoundError:
        pytest.fail("The ai_researcher.mcp server package is missing")
    return server


def _traversal() -> TraversalResult:
    return TraversalResult(
        ranked_nodes=(
            RankedNode(
                node_id=11,
                paper_id=101,
                section_path="Results/Threshold",
                title="Threshold",
                summary="A threshold estimate.",
                page_start=4,
                page_end=5,
                relevance=96,
                reason="Direct evidence.",
            ),
            RankedNode(
                node_id=22,
                paper_id=202,
                section_path="Discussion/Comparison",
                title="Comparison",
                summary="A comparison.",
                page_start=8,
                page_end=8,
                relevance=88,
                reason="Corroborating evidence.",
            ),
        ),
        trace=TraversalTrace(
            expanded_nodes=(),
            selected_node_ids=(11, 22),
            stopped_reason="budget_exhausted",
        ),
    )


def _answer() -> Answer:
    return Answer(
        answer_text="The reported threshold is 1.1 percent. [node 11]",
        citations=[
            Citation(
                node_id=11,
                paper_id=101,
                paper_title="Threshold paper",
                section_path="Results/Threshold",
                page_start=4,
                page_end=5,
                identifier_type="doi",
                identifier="10.1000/threshold",
            )
        ],
        budget_limited=True,
        insufficient_evidence=False,
        message=None,
    )


def _json_rpc_messages(stdout: str) -> dict[int, dict[str, Any]]:
    messages = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    return {message["id"]: message for message in messages if "id" in message}


def test_mcp_command_serves_required_tools_over_stdio() -> None:
    executable = str(Path(sys.executable).with_name("airesearch"))
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    completed = subprocess.run(
        [executable, "mcp"],
        cwd=REPO_ROOT,
        input="\n".join(json.dumps(request) for request in requests) + "\n",
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    responses = _json_rpc_messages(completed.stdout)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "result" in responses[1]
    tools = responses[2]["result"]["tools"]
    assert {tool["name"] for tool in tools} >= {
        "list_scopes",
        "scope_status",
        "ask_corpus",
        "get_paper_sections",
    }
    assert all(tool["outputSchema"]["type"] == "object" for tool in tools)


def test_scope_tools_return_named_structured_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _server_module()
    definition = ScopeDefinition(
        name="surface-codes",
        description="Surface-code thresholds",
        include_terms=("surface code",),
        exclude_terms=("medicine",),
        categories=("quant-ph",),
        date_from=date(2020, 1, 1),
        date_to=None,
        per_source_limit=50,
    )
    status = ScopeStatus(
        scope_name="surface-codes",
        paper_count=3,
        parsed_count=2,
        abstract_only_count=0,
        failed_count=1,
        section_count=8,
        failed_papers=(FailedPaper(paper_id=9, title="Broken", error="parse failed"),),
    )
    monkeypatch.setattr(server.scope_store, "list_scopes", lambda: [definition])
    monkeypatch.setattr(server.corpus_status, "scope_status", lambda scope: [status])

    scopes = server.list_scopes_tool()
    statuses = server.scope_status_tool("surface-codes")

    assert scopes == {
        "scopes": [
            {
                "name": "surface-codes",
                "description": "Surface-code thresholds",
                "include_terms": ["surface code"],
                "exclude_terms": ["medicine"],
                "categories": ["quant-ph"],
                "date_from": "2020-01-01",
                "date_to": None,
                "per_source_limit": 50,
            }
        ]
    }
    assert statuses["scopes"][0]["scope_name"] == "surface-codes"
    assert statuses["scopes"][0]["section_count"] == 8
    assert statuses["scopes"][0]["failed_papers"] == [
        {"paper_id": 9, "title": "Broken", "error": "parse failed"}
    ]


def test_ask_corpus_returns_grounding_and_limits_as_distinct_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server_module()
    import ai_researcher.answer
    import ai_researcher.retrieval

    monkeypatch.setattr(ai_researcher.retrieval, "traverse", lambda *args, **kwargs: _traversal())
    monkeypatch.setattr(ai_researcher.answer, "synthesize", lambda *args, **kwargs: _answer())

    result = server.ask_corpus_tool(
        question="What threshold is reported?",
        scope="surface-codes",
        max_nodes=2,
    )

    assert result["answer"].startswith("The reported threshold")
    assert result["citations"][0]["node_id"] == 11
    assert result["citations"][0]["page_start"] == 4
    assert result["citations"][0]["page_end"] == 5
    assert result["budget_limited"] is True
    assert result["insufficient_evidence"] is False
    assert result["trace"] == {
        "nodes_expanded": 0,
        "selected_node_ids": [11, 22],
        "stopped_reason": "budget_exhausted",
    }


def test_ask_cli_and_mcp_call_the_same_synthesize_entry_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server_module()
    import ai_researcher.answer
    import ai_researcher.retrieval

    traversal = _traversal()
    synthesis_calls: list[tuple[str, TraversalResult]] = []

    monkeypatch.setattr(ai_researcher.retrieval, "traverse", lambda *args, **kwargs: traversal)

    def fake_synthesize(question: str, result: TraversalResult) -> Answer:
        synthesis_calls.append((question, result))
        return _answer()

    monkeypatch.setattr(ai_researcher.answer, "synthesize", fake_synthesize)

    cli_result = runner.invoke(
        app,
        ["ask", "What threshold?", "--scope", "surface-codes", "--json"],
    )
    mcp_result = server.ask_corpus_tool("What threshold?", "surface-codes")

    assert cli_result.exit_code == 0, cli_result.output
    assert mcp_result["answer"]
    assert synthesis_calls == [
        ("What threshold?", traversal),
        ("What threshold?", traversal),
    ]


def test_get_paper_sections_returns_structured_section_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server_module()
    monkeypatch.setattr(
        server,
        "_load_paper_sections",
        lambda paper_id: {
            "paper_id": paper_id,
            "paper_title": "Threshold paper",
            "sections": [
                {
                    "section_id": 17,
                    "parent_id": None,
                    "section_path": "Results/Threshold",
                    "title": "Threshold",
                    "ordinal": 3,
                    "page_start": 4,
                    "page_end": 5,
                    "body_text": "The threshold is 1.1 percent.",
                }
            ],
        },
    )

    result = server.get_paper_sections_tool(101)

    assert result["paper_id"] == 101
    assert result["sections"][0]["section_id"] == 17
    assert result["sections"][0]["section_path"] == "Results/Threshold"
    assert result["sections"][0]["page_start"] == 4
    assert result["sections"][0]["page_end"] == 5


def test_mcp_setup_documents_exact_claude_code_registration() -> None:
    setup = (REPO_ROOT / "docs/supersaiyan/mcp-setup.md").read_text()

    assert "claude mcp add" in setup
    assert "uv run airesearch mcp" in setup
    assert str(MAIN_REPO_ROOT) in setup
