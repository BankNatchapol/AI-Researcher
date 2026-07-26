---
title: Expose the research engine as an MCP server
order: 7
depends_on_task: 06-ask-cli
project: ai-researcher-app
phase: 2
depends_on_phase: 1
design: docs/superpowers/projects/ai-researcher-app/phase-2/PHASE.md
plan_task: Requirements 18, 19, 20
skills: test-driven-development, verification-before-completion
---

## Goal

The engine is callable from Claude Code as MCP tools returning structured JSON, sharing
exactly the same core code path as the CLI.

## Acceptance Criteria

- [ ] `uv run airesearch mcp` starts an MCP server over stdio that responds to `tools/list`
- [ ] The server exposes at least `list_scopes`, `scope_status`, `ask_corpus`, and `get_paper_sections`
- [ ] Every tool returns structured JSON with named fields, never a prose blob
- [ ] `ask_corpus` returns answer text, citations with node IDs and page ranges, and the budget-limited and insufficient-evidence flags as distinct fields
- [ ] `uv run pytest tests/test_mcp_server.py` exits 0, including a test asserting `ask_corpus` and the `ask` CLI command call the same `synthesize()` entry point

## Implementation notes

**Files:**
- Create: `src/ai_researcher/mcp/__init__.py`
- Create: `src/ai_researcher/mcp/server.py` — tool definitions with JSON schemas, served over stdio
- Modify: `src/ai_researcher/cli.py` — register the `mcp` command
- Create: `docs/supersaiyan/mcp-setup.md` — how to register this server with Claude Code, including the exact command and working directory
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `synthesize()` (task 05), `traverse()` (task 04), `scope_status()` (Phase 1 task 11), `section` rows (Phase 1 task 09)
- Produces: the MCP surface; Phase 3 adds `list_claims`, `get_claim`, `find_claim_evidence`, and Phase 4 adds monitoring tools to this same server

**Shared-path constraint:**
- Neither `cli.py` nor `mcp/server.py` may contain retrieval or synthesis logic. The test
  asserting a shared entry point is the mechanism that keeps the two surfaces from drifting.

## Out of scope

No HTTP or SSE transport — stdio only. No authentication; this is a single-user local
server. No claim or monitoring tools, which arrive with Phases 3 and 4. No write operations
through MCP in this phase; ingestion stays CLI-driven.
