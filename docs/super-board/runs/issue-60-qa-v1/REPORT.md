# QA Report — issue #60 v1

**Issue:** #60 — Add the discourse, subscription, and sweep schema  
**PR:** #72  
**Branch:** `issue-60-add-the-discourse-subscription-and-sweep-schema`  
**Builder commit:** `fef592b`  
**Result:** ✅ PASS

## Visual evidence

Omitted intentionally — schema/migration-only task (no UI ACs). Evidence is CLI/pytest logs below.

## Acceptance criteria

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | `uv run airesearch db migrate` applies; re-run reports already up to date | ✅ PASS | `ac1-migrate.log` — Applied `0011_discourse`; second run: `Database already up to date.` |
| AC2 | Five tables exist with PHASE.md Req 1–5 columns | ✅ PASS | `ac1-migrate.log` column dump + `ac-discourse-schema-pytest.log` |
| AC3 | `discourse_item` unique `(source_id, external_id)` | ✅ PASS | pytest constraint rejection in `test_discourse_migration_applies_and_enforces_constraints` |
| AC4 | `subscription` exactly-one of `scope_id`/`claim_id` | ✅ PASS | pytest rejects both-null and both-set |
| AC5 | `pytest tests/test_discourse_schema.py` + no FK into `claim_score` | ✅ PASS | 2/2 passed; FK targets: discourse_source, discourse_item, paper, scope, claim only |

## Hard invariants checked

- Discourse tables have **no** FK into `claim_score` (AC5 + explicit SQL probe).
- `subscription` / `sweep_run` kind checks and attention-count columns are storage-only (no scoring path in this PR).

## Regression

- `uv run pytest` — **274 passed** (`full-pytest.log`)
- `uv run ruff check .` — clean
- `uv run ruff format --check .` — clean

## Local tests (for Reviewer re-run)

```
uv run pytest tests/test_discourse_schema.py && uv run pytest && uv run ruff check . && uv run ruff format --check .
```
