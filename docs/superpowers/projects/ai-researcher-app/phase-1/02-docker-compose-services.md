---
title: Bring up PostgreSQL and GROBID via Docker Compose
order: 2
depends_on_task: 01-scaffold-python-project
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 3
skills: test-driven-development, verification-before-completion
---

## Goal

`docker compose up -d` starts PostgreSQL 16 and GROBID locally on Apple Silicon, both
reporting healthy, with connection details supplied through environment variables.

## Acceptance Criteria

- [ ] `docker compose up -d` followed by `docker compose ps` shows both `postgres` and `grobid` with state `healthy`
- [ ] `curl -sf http://localhost:8070/api/isalive` returns `true`
- [ ] `psql "$DATABASE_URL" -c "select 1"` succeeds against the running container
- [ ] Both images resolve and run on `linux/arm64` without emulation warnings
- [ ] `uv run pytest tests/test_services_config.py` exits 0, asserting `GROBID_URL` and `DATABASE_URL` are read from config rather than hardcoded

## Implementation notes

**Files:**
- Create: `docker-compose.yml` — services `postgres` (image `postgres:16`) and `grobid` (image `lfoppiano/grobid:0.8.1` or newer arm64-compatible tag), each with a `healthcheck` block and a named volume for Postgres data
- Modify: `.env.example` — confirm `DATABASE_URL` and `GROBID_URL` match the compose ports
- Create: `docs/supersaiyan/running-services.md` — how to start, stop, and reset the stack, including the volume name to remove for a clean slate
- Test: `tests/test_services_config.py`

**Interfaces:**
- Consumes: `ai_researcher.config` from task 01
- Produces: a running Postgres for task 03's migrations and a running GROBID for task 09's parsing

## Out of scope

No schema, no migrations, no application code that connects to either service — task 03
owns the first real connection. No production deployment or orchestration.
