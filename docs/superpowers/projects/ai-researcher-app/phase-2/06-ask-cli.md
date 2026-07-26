---
title: Add the ask command with trace and JSON output
order: 6
depends_on_task: 05-answer-synthesis
project: ai-researcher-app
phase: 2
depends_on_phase: 1
design: docs/superpowers/projects/ai-researcher-app/phase-2/PHASE.md
plan_task: Requirements 16, 17
skills: test-driven-development, verification-before-completion
---

## Goal

A researcher asks a question from the terminal and gets a cited answer, with the full
retrieval path visible on demand and machine-readable output available for scripting.

## Acceptance Criteria

- [ ] `uv run airesearch ask "<question>" --scope <name>` prints the answer with numbered citations resolving to paper, section path, and page range
- [ ] `--verbose` additionally prints the traversal trace showing which nodes were expanded and the stopping reason
- [ ] `--json` emits machine-readable output containing answer text, citations with node IDs and page ranges, and a trace summary, and emits nothing else on stdout
- [ ] `--max-nodes N` overrides the traversal budget, and a low value produces output labelled budget-limited
- [ ] `uv run pytest tests/test_ask_cli.py` exits 0, covering default, verbose, JSON, low-budget, and insufficient-evidence output shapes

## Implementation notes

**Files:**
- Modify: `src/ai_researcher/cli.py` — register the `ask` command with `--scope`, `--verbose`, `--json`, `--max-nodes`
- Create: `src/ai_researcher/answer/render.py` — terminal rendering of an `Answer`, including the numbered citation list and the optional trace block
- Test: `tests/test_ask_cli.py`

**Interfaces:**
- Consumes: `synthesize()` from task 05; `traverse()` from task 04
- Produces: the `ask` command surface; `render.py` is reused by Phase 4's digest rendering for citation formatting

**Behaviour notes:**
- `cli.py` contains no retrieval or synthesis logic; it parses arguments and calls the core, matching the constraint verified in task 07
- Under `--json`, logs stay on stderr so stdout is valid JSON and pipeable
- An insufficient-evidence result exits 0 with the explicit message — it is a valid answer, not an error

## Out of scope

No MCP server — task 07. No interactive follow-up or REPL mode. No answer persistence or
history. No export to markdown or bibliography formats.
