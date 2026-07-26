---
title: Scaffold the Python project with uv, pytest, and ruff
order: 1
depends_on_task: null
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 1, 2, 22
skills: test-driven-development, verification-before-completion
---

## Goal

A `uv`-managed Python 3.11+ project exists with a `src/ai_researcher/` layout, an
`airesearch` console script, environment-driven config, and passing lint and test commands.

## Acceptance Criteria

- [ ] `uv sync` installs the project on Python 3.11+ with no errors
- [ ] `uv run airesearch --help` prints the CLI usage text and exits 0
- [ ] `uv run ruff check .` and `uv run ruff format --check .` both exit 0 with zero findings
- [ ] `uv run pytest` exits 0 and collects at least one test
- [ ] `.env.example` exists listing `DATABASE_URL`, `GROBID_URL`, `LLM_BACKEND_DEFAULT`, and `CONTACT_EMAIL`; `.env` is gitignored

## Implementation notes

**Files:**
- Create: `pyproject.toml` — `requires-python = ">=3.11"`, `[project.scripts] airesearch = "ai_researcher.cli:app"`, dev deps `pytest` and `ruff`
- Create: `src/ai_researcher/__init__.py`
- Create: `src/ai_researcher/cli.py` — Typer app object named `app`, exported for later subcommand registration
- Create: `src/ai_researcher/config.py` — settings read from environment variables only, with no hardcoded defaults for secrets
- Create: `.env.example` — `LLM_BACKEND_DEFAULT` names a CLI backend (`claude` or `codex`), not a model or an API key
- Create: `.gitignore` entries for `.env`, `.venv/`, `__pycache__/`
- Test: `tests/test_cli_smoke.py` — asserts `airesearch --help` exits 0
- Test: `tests/test_config.py` — asserts config reads `DATABASE_URL` from the environment and raises a named error when a required variable is missing

**Interfaces:**
- Consumes: nothing
- Produces: `ai_researcher.cli.app` (Typer app all later tasks register subcommands on), `ai_researcher.config` settings accessor

## Out of scope

No database connection, no Docker, no adapters, no LLM calls. Per PHASE.md Out of Scope:
no trees, retrieval, extraction, MCP server, or discourse sources.
