---
title: Add the migration runner and core database schema
order: 3
depends_on_task: 02-docker-compose-services
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 4, 5, 6
skills: test-driven-development, verification-before-completion
---

## Goal

An idempotent migration runner applies numbered SQL files in order and creates the full
Phase 1 schema, so every later task has real tables to write to.

## Acceptance Criteria

- [ ] `uv run airesearch db migrate` against an empty database applies all migrations and exits 0
- [ ] Running `uv run airesearch db migrate` a second time reports "already up to date" and exits 0 without re-applying
- [ ] A `schema_migration` table records each applied version with a timestamp
- [ ] All nine tables exist with the columns named in PHASE.md Requirement 5: `source`, `scope`, `paper`, `paper_author`, `paper_source`, `paper_scope`, `section`, `ingest_job`
- [ ] `uv run pytest tests/test_migrations.py` exits 0, including a test that inserting two `paper` rows with the same non-null `doi` raises a uniqueness violation, and the same for `arxiv_id`

## Implementation notes

**Files:**
- Create: `src/ai_researcher/db/__init__.py` — connection handling reading `DATABASE_URL` from config
- Create: `src/ai_researcher/db/models.py` — table definitions
- Create: `src/ai_researcher/db/migrate.py` — runner that reads `migrations/*.sql` sorted by numeric prefix, applies unapplied ones in a transaction, and records them
- Create: `src/ai_researcher/db/migrations/0001_initial.sql` — all Phase 1 tables
- Modify: `src/ai_researcher/cli.py` — register the `db` subcommand group with `migrate`
- Test: `tests/test_migrations.py` — runs against a disposable test database

**Interfaces:**
- Consumes: `ai_researcher.config` (task 01), running Postgres (task 02)
- Produces: `ai_researcher.db` connection handling and the migration runner, used by every later task in this phase and by Phases 2–4 for their own migrations

**Schema notes:**
- `paper.doi` and `paper.arxiv_id` are both nullable with a unique constraint that applies only when the value is present
- `section.parent_id` is a self-referencing foreign key; `section.ordinal` preserves document order
- `paper_scope` is a join table with a composite primary key `(paper_id, scope_id)`

## Out of scope

No adapters, no ingestion, no data population. Later phases add their own migration files
(`tree_node` in Phase 2, `claim` in Phase 3, `discourse_item` in Phase 4) — do not create
those tables here.
