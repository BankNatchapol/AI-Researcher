# Issue #3 QA plan

PR: #17
Branch: `issue-3-add-the-migration-runner-and-core-database-schema`
Task: `docs/superpowers/projects/ai-researcher-app/phase-1/03-migration-runner-and-schema.md`

This is a non-visual database and CLI change, so screenshot evidence is intentionally omitted.
Command results and database observations are recorded in `REPORT.md`.

## Acceptance-criterion checks

1. Run `uv run airesearch db migrate` with `DATABASE_URL` pointing to a newly created,
   empty PostgreSQL database. Require exit code 0 and an `Applied migration 0001_initial.`
   message.
2. Run the same command a second time against the same database. Require exit code 0 and
   `Database already up to date.` without another migration row.
3. Query `schema_migration` in the migrated database. Require exactly one row with version
   `1`, name `0001_initial`, and a non-null `applied_at`.
4. Query `information_schema.columns`. Require `schema_migration` plus all eight Phase 1
   domain tables, with every column named by PHASE.md Requirement 5.
5. Run `uv run pytest tests/test_migrations.py`. Require all tests to pass, including the
   parameterized non-null DOI and arXiv ID uniqueness checks.

## Repository gates

- Run `uv run pytest`.
- Run `uv run ruff check .`.
- Run `uv run ruff format --check .`.
