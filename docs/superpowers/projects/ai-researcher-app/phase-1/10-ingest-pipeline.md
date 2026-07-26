---
title: Wire the ingest pipeline with resumability and the corpus ceiling
order: 10
depends_on_task: 09-grobid-tei-parsing
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 14, 15, 20
skills: test-driven-development, verification-before-completion
---

## Goal

`airesearch ingest <scope>` runs discover → acquire → parse → store end to end, tracked as a
job, resumable on re-run, and refusing to exceed the 1,000-paper ceiling.

## Acceptance Criteria

- [ ] `uv run airesearch ingest <scope>` completes the full pipeline and writes one `ingest_job` row with `papers_found`, `papers_parsed`, and a terminal state
- [ ] Re-running ingest for the same scope reports zero newly parsed papers, proving resumability
- [ ] A scope resolving to more than 1,000 papers exits non-zero with a message naming both the resolved count and the 1,000 ceiling
- [ ] A single paper's parse failure is recorded against that paper and the run continues to completion rather than aborting
- [ ] `uv run pytest tests/test_ingest_pipeline.py` exits 0, covering a clean run, a resumed run, ceiling refusal, and a mid-run parse failure

## Implementation notes

**Files:**
- Create: `src/ai_researcher/ingest/discover.py` — reads a `scope`, queries every registered adapter, applies `resolve_identity()` from task 06, returns merged candidates
- Create: `src/ai_researcher/ingest/pipeline.py` — orchestrates discover → acquire → parse → persist; writes and updates the `ingest_job` row
- Modify: `src/ai_researcher/cli.py` — register the `ingest` command taking a scope name
- Test: `tests/test_ingest_pipeline.py`

**Interfaces:**
- Consumes: `scope` rows (task 07), `sources.registry` (task 05), `resolve_identity()` (task 06), `acquire_pdf()` (task 08), `parse_pdf()` (task 09), `ingest_job`/`paper`/`paper_scope` tables (task 03)
- Produces: a populated corpus — `paper` rows with `tei_xml` and `section` hierarchies linked to a scope. This is exactly what Phase 2 consumes, and what Phase 4's evidence sweep re-invokes for newly discovered papers

**Behaviour notes:**
- Resumability keys on `(scope, paper)` with `parse_status` already terminal — parsed and abstract-only papers are both skipped on re-run
- The ceiling is checked after discovery and deduplication, before any PDF is downloaded, so an oversized scope costs no bandwidth
- Papers are linked to the scope via `paper_scope`, so one paper can belong to several scopes without duplication

## Out of scope

No tree building, retrieval, or extraction. No scheduling or automatic re-runs — Phase 4
owns sweeps. No status reporting command; task 11 adds `status`. No partial-scope ingestion
flags.
