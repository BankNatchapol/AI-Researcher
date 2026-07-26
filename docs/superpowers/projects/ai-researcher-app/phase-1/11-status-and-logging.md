---
title: Add the corpus status command and structured logging
order: 11
depends_on_task: 10-ingest-pipeline
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 19, 21
skills: test-driven-development, verification-before-completion
---

## Goal

A researcher can see the state of every scope's corpus at a glance, and every command emits
structured logs with visible per-paper progress during long ingest runs.

## Acceptance Criteria

- [ ] `uv run airesearch status` prints, per scope: paper count, parsed count, abstract-only count, failed count, and total sections
- [ ] `uv run airesearch status --scope <name>` restricts output to one scope and additionally lists each failed paper with its recorded error
- [ ] Logs are written to stderr at INFO by default and at DEBUG under `--verbose`, leaving stdout clean for command output
- [ ] `uv run airesearch ingest <scope>` emits a per-paper progress line with a running count of processed versus total
- [ ] `uv run pytest tests/test_status.py` exits 0, asserting counts against a seeded test database, including a scope containing parsed, abstract-only, and failed papers

## Implementation notes

**Files:**
- Create: `src/ai_researcher/logging.py` — structured logger configured to stderr, level driven by a global `--verbose` flag
- Create: `src/ai_researcher/corpus/status.py` — `scope_status(scope_name | None) -> list[ScopeStatus]`, aggregating counts by SQL rather than in Python
- Modify: `src/ai_researcher/cli.py` — register the `status` command and add the global `--verbose` flag
- Modify: `src/ai_researcher/ingest/pipeline.py` — emit per-paper progress through the logger
- Test: `tests/test_status.py`

**Interfaces:**
- Consumes: `paper`, `section`, `paper_scope`, `ingest_job` tables (task 03); the populated corpus from task 10
- Produces: `scope_status()` — reused by Phase 2's index reporting and Phase 4's sweep summaries; `ai_researcher.logging` used by every later module

**Behaviour notes:**
- Counts come from aggregate SQL queries, so `status` stays fast at the 1,000-paper ceiling
- stdout carries only command results, so `status` output stays pipeable

## Out of scope

No tree, claim, or discourse counts — those tables do not exist yet and are added in Phases
2, 3, and 4 respectively. No log file output, no log shipping, no metrics endpoint. No
progress bars requiring a TTY; plain log lines only, so output stays readable when redirected.
