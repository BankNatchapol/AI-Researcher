# Issue #32 QA evidence — v1

- PR: #40
- Branch: `issue-32-expose-the-research-engine-as-an-mcp-server`
- Builder commit tested: `9995d0bcaff83d387343f3dc3bda653157b1487a`
- Result: PASS
- Local tests: `uv run pytest tests/test_mcp_server.py`

This issue changes a stdio/API surface and has no UI or visual acceptance criteria.
Screenshots are therefore intentionally omitted.

## Acceptance-criterion results

| AC | Observable check | Result |
|---|---|---|
| 1 | `test_mcp_command_serves_required_tools_over_stdio` starts `airesearch mcp`, completes MCP initialization, and receives `tools/list`. | PASS |
| 2 | The stdio response advertises `list_scopes`, `scope_status`, `ask_corpus`, and `get_paper_sections`. | PASS |
| 3 | `tools/list` reports an object output schema for every tool; focused tests verify named dictionary fields for scope, status, answer, citation, trace, and section results. | PASS |
| 4 | `test_ask_corpus_returns_grounding_and_limits_as_distinct_fields` verifies answer text, citation node ID, page range, `budget_limited`, and `insufficient_evidence` as separate fields. | PASS |
| 5 | The exact task command passes, including `test_ask_cli_and_mcp_call_the_same_synthesize_entry_point`. | PASS |

## Fresh command evidence

### Task acceptance command

```text
$ uv run pytest tests/test_mcp_server.py
collected 6 items
tests/test_mcp_server.py ...... [100%]
6 passed in 2.81s
```

### Repository gates

```text
$ uv run pytest && uv run ruff check . && uv run ruff format --check .
collected 144 items
144 passed in 9.24s
All checks passed!
79 files already formatted
```

### Independent stdio handshake

An MCP SDK client initialized the server and called `tools/list`. The concise protocol
result is recorded in `tools-list.json`.

