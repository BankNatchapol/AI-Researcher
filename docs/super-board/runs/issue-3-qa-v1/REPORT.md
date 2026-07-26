# Issue #3 QA report

Result: **PASS**

PR: #17
Branch: `issue-3-add-the-migration-runner-and-core-database-schema`
Builder commit tested: `2c3520fa6979209f15e82a3c0941db259de9ed03`
Environment: macOS, Python 3.11.15, PostgreSQL 16 in a healthy localhost-only Docker
test service

This ticket only changes the CLI and PostgreSQL schema. Screenshots were intentionally
omitted because none of the acceptance criteria are visual.

## Acceptance criteria

### AC1 — Empty-database migration

Command:

```text
uv run airesearch db migrate
```

The command ran against a newly created, empty PostgreSQL database and exited 0:

```text
Applied migration 0001_initial.
```

### AC2 — Idempotent second migration

The same command ran a second time against the same database and exited 0:

```text
Database already up to date.
```

The second run did not add another row to `schema_migration`.

### AC3 — Migration record

The live database query returned exactly one migration row:

```text
version | name         | applied_at                    | has_timestamp
1       | 0001_initial | 2026-07-26 06:45:44.032845+00 | true
```

### AC4 — Required schema

`information_schema.columns` returned exactly these nine tables:

```text
schema_migration(version, name, applied_at)
source(id, name, kind, enabled)
scope(id, name, description, include_terms, exclude_terms, categories, date_from, date_to,
      per_source_limit, created_at)
paper(id, doi, arxiv_id, openalex_id, s2_id, title, abstract, published_at, venue,
      is_preprint, oa_status, pdf_path, tei_xml, parse_status, created_at)
paper_author(id, paper_id, position, full_name)
paper_source(id, paper_id, source_id, external_id, retrieved_at)
paper_scope(paper_id, scope_id)
section(id, paper_id, parent_id, section_path, title, ordinal, page_start, page_end,
        char_start, char_end, body_text)
ingest_job(id, scope_id, state, papers_found, papers_parsed, started_at, finished_at, error)
```

### AC5 — Migration integration tests and identifier uniqueness

Command:

```text
uv run pytest tests/test_migrations.py
```

Result:

```text
collected 6 items
tests/test_migrations.py ...... [100%]
6 passed in 0.44s
```

The six passing tests include the parameterized uniqueness test for both `paper.doi` and
`paper.arxiv_id`, plus the multiple-null-identifiers case.

## Repository gates

```text
uv run pytest
12 passed in 0.52s

uv run ruff check .
All checks passed!

uv run ruff format --check .
11 files already formatted
```

No failures, skips, warnings, or acceptance gaps were observed.
