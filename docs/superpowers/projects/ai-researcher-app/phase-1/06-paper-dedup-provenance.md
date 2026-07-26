---
title: Implement cross-source paper deduplication and provenance
order: 6
depends_on_task: 05-evidence-source-adapters
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 11
skills: test-driven-development, verification-before-completion
---

## Goal

A paper surfaced by several sources becomes exactly one `paper` row carrying one
`paper_source` provenance row per source that found it.

## Acceptance Criteria

- [ ] The same paper returned by arXiv, OpenAlex, and Semantic Scholar produces one `paper` row and three `paper_source` rows
- [ ] Identity resolution follows the order DOI → arXiv ID → normalized title with first-author surname and publication year
- [ ] Title normalization ignores case, punctuation, and whitespace differences, asserted by a test using two real variants of one title
- [ ] Merging fills empty fields from later sources without overwriting non-null values already present
- [ ] `uv run pytest tests/test_dedup.py` exits 0, covering DOI match, arXiv match, title-year match, and a near-miss pair that must stay two distinct papers

## Implementation notes

**Files:**
- Create: `src/ai_researcher/ingest/dedup.py` — `resolve_identity(candidates) -> list[MergedPaper]` and `normalize_title()`
- Create: `src/ai_researcher/ingest/__init__.py`
- Test: `tests/test_dedup.py`

**Interfaces:**
- Consumes: `PaperMetadata` dataclasses from task 05 adapters; `paper` and `paper_source` tables from task 03
- Produces: `resolve_identity()` — called by task 10's ingest pipeline before any write

**Algorithm notes:**
- Two records with different non-null DOIs are never merged, even when titles match
- The near-miss test case must include two genuinely different papers sharing a title prefix, proving the matcher does not over-merge

## Out of scope

No fuzzy or embedding-based similarity matching — exact and normalized comparisons only.
No claim-level deduplication; that is Phase 3's `evidence/identity.py` and solves a different
problem. No writing to the database in this task; task 10 owns persistence.
