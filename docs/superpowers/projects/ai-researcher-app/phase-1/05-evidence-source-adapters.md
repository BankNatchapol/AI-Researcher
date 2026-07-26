---
title: Define the EvidenceSource protocol, registry, and three scholarly adapters
order: 5
depends_on_task: 04-cli-model-gateway
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 8, 9, 10
skills: test-driven-development, verification-before-completion
---

## Goal

A fixed `EvidenceSource` protocol plus a registry, with working arXiv, OpenAlex, and
Semantic Scholar adapters, so adding a future source is one file and one registration line.

## Acceptance Criteria

- [ ] `ai_researcher.sources.registry.get("arxiv")` returns a registered adapter; `get("nope")` raises a named `UnknownSourceError`
- [ ] All three adapters implement `search`, `fetch_metadata`, and `pdf_url` and are registered at import time
- [ ] `uv run pytest tests/sources/` exits 0 with every adapter test served from recorded fixtures and no live network access
- [ ] Each adapter sends a User-Agent containing the tool name and the configured `CONTACT_EMAIL`, asserted by a test per adapter
- [ ] Each adapter enforces its own configured minimum interval between requests, asserted by a test that two consecutive calls are spaced apart

## Implementation notes

**Files:**
- Create: `src/ai_researcher/sources/base.py` — `EvidenceSource` as a `typing.Protocol`, plus `PaperRef` and `PaperMetadata` dataclasses
- Create: `src/ai_researcher/sources/registry.py` — name → instance mapping, `register()` and `get()`, `UnknownSourceError`
- Create: `src/ai_researcher/sources/arxiv.py` — arXiv API, category and date filtering
- Create: `src/ai_researcher/sources/openalex.py` — OpenAlex works endpoint with `from_publication_date` filtering
- Create: `src/ai_researcher/sources/semantic_scholar.py` — Semantic Scholar Graph API
- Create: `src/ai_researcher/sources/crossref.py` — `resolve_doi()` helper only; not registered as a discovery adapter
- Create: `src/ai_researcher/sources/ratelimit.py` — per-source minimum-interval limiter
- Test: `tests/sources/fixtures/` — recorded JSON/XML responses per source
- Test: `tests/sources/test_arxiv.py`, `test_openalex.py`, `test_semantic_scholar.py`, `test_registry.py`

**Interfaces:**
- Consumes: `ai_researcher.config` for `CONTACT_EMAIL` and per-source rate limits
- Produces: `sources.registry` and the `EvidenceSource` protocol — consumed by task 06 dedup, task 07 scoping estimates, task 10 ingest, and mirrored by Phase 4's separate `DiscourseSource`

**Design constraints:**
- Adapters never touch the database and never call an LLM; they return plain dataclasses
- Adapters must not import each other

## Out of scope

No deduplication across sources (task 06), no PDF downloading (task 08), no persistence of
results (task 10). PubMed is excluded from the project entirely. No `DiscourseSource` — that
is a separate protocol introduced in Phase 4.
