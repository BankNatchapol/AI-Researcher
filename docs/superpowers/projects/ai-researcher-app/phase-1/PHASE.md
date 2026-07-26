# Phase 1: Foundation & Corpus Ingestion

**Project:** ai-researcher-app
**Goal:** A researcher can narrow a broad topic into a defensible scope, then ingest that scope so 100–1,000 quantum/AI papers are fetched, parsed by GROBID into structured TEI, and stored locally with their full section hierarchy.
**Depends on:** None

## Scope

This phase builds the foundation and the entire ingestion path. It ends with a populated
local corpus that later phases index and reason over.

1. **Repo skeleton** — `uv`-managed Python 3.11+ project, `src/ai_researcher/` layout,
   `pytest` + `ruff` configured, `airesearch` console entry point.
2. **Backing services** — `docker-compose.yml` running PostgreSQL 16 and GROBID, both
   arm64-compatible, with a health-check wait so `ingest` fails fast when services are down.
3. **Database schema and migrations** — tables for sources, scopes, papers, authors,
   provenance, sections, and ingest jobs.
4. **CLI model gateway** — the single place any model is called, shelling out to `claude -p`
   or `codex exec` selected per job type. Used in this phase for the scoping dialogue only.
5. **`EvidenceSource` interface and registry** — a fixed protocol plus a registry so a new
   source is one new adapter file and one registration line.
6. **Three evidence adapters** — arXiv, OpenAlex, Semantic Scholar. Crossref used for DOI
   resolution only, not as a discovery adapter.
7. **Interactive topic scoping** — a narrowing dialogue that turns a broad topic into a
   persisted, re-runnable scope definition with explicit include/exclude terms.
8. **PDF acquisition** — fetch open-access PDFs, record when only an abstract is available.
9. **GROBID parsing** — PDF → TEI XML → normalized section hierarchy in Postgres.
10. **CLI** — `airesearch scope`, `airesearch ingest`, `airesearch status`.

## Out of Scope

Deferred to later phases — agents must not build these here:

- Tree building, node summaries, PageIndex, or any retrieval (Phase 2)
- Question answering, citations, or answer synthesis (Phase 2)
- The MCP server (Phase 2)
- The evaluation gold set and eval harness (Phase 2)
- Claim/method/result/date extraction and scoring (Phase 3)
- `DiscourseSource`, Reddit/HN/blog adapters, scheduling, digests (Phase 4)
- Zotero import (post-v1; the interface must not assume it)
- Any vector embedding or similarity search (excluded from v1 entirely)
- Web UI of any kind

## Consumes from Prior Phase

None — this is Phase 1.

## Produces for Next Phase

Phase 2 consumes:

- `paper` rows with `tei_xml` populated and `parse_status = 'parsed'`
- `section` rows forming a complete parent/child hierarchy per paper, each carrying
  `section_path`, `title`, `page_start`, `page_end`, `char_start`, `char_end`, `body_text`
- `scope` rows defining which papers belong to a working corpus
- `ai_researcher.llm.gateway` — the CLI model-call interface
- `ai_researcher.sources.registry` — the `EvidenceSource` registry
- `ai_researcher.db` — connection handling and the migration runner
- The `airesearch` CLI app object, so Phase 2 adds `ask` as a new subcommand

## Architecture

**Package layout:**

```
src/ai_researcher/
  __init__.py
  cli.py                  # Typer app; subcommands register here
  config.py               # env-driven settings (DB URL, GROBID URL, model names)
  db/
    __init__.py           # connection/session handling
    migrations/           # numbered .sql files, applied in order
    models.py             # table definitions
  llm/
    gateway.py            # the ONLY module that invokes a model CLI
    registry.py           # job -> backend resolution
    backends/             # claude_cli.py, codex_cli.py
  sources/
    base.py               # EvidenceSource protocol
    registry.py           # name -> adapter registration and lookup
    arxiv.py
    openalex.py
    semantic_scholar.py
    crossref.py           # DOI resolution helper, not a discovery adapter
  scoping/
    dialogue.py           # narrowing conversation
    store.py              # persist/load scope definitions
  ingest/
    discover.py           # scope -> candidate papers via adapters
    acquire.py            # PDF fetching, OA detection
    parse.py              # GROBID client + TEI -> section hierarchy
    pipeline.py           # orchestrates discover -> acquire -> parse -> store
```

**Data flow:** `scope` → `discover` (adapters, deduped by DOI/arXiv ID) → `acquire` (OA PDF
or abstract-only) → `parse` (GROBID → TEI → sections) → Postgres.

**`EvidenceSource` protocol** — every adapter implements exactly:

```python
class EvidenceSource(Protocol):
    name: str
    def search(self, scope: Scope, limit: int) -> Iterable[PaperRef]: ...
    def fetch_metadata(self, ref: PaperRef) -> PaperMetadata: ...
    def pdf_url(self, ref: PaperRef) -> str | None: ...
```

Adapters never touch the database and never call an LLM. They return plain dataclasses.
This keeps them independently testable against recorded fixtures.

**Deduplication:** a paper surfaced by multiple sources becomes one `paper` row with
multiple `paper_source` provenance rows. Identity resolution order: DOI → arXiv ID →
normalized-title + first-author-surname + publication year.

**Scoping dialogue:** the LLM proposes candidate sub-topics, adjacent terms, and exclusions
based on a trial search; the user accepts or rejects each. The persisted `scope` records the
accepted include terms, exclude terms, arXiv categories, date range, and per-source result
caps — so `ingest` is reproducible and re-runnable without repeating the dialogue.

## Requirements

1. `uv sync` installs the project on Python 3.11+ and exposes an `airesearch` console script.
2. `ruff check .` and `ruff format --check .` pass with zero findings.
3. `docker compose up -d` starts PostgreSQL 16 and GROBID; both expose health checks and
   both images resolve on linux/arm64.
4. A migration runner applies numbered SQL files from `db/migrations/` in order, records
   applied versions in a `schema_migration` table, and is idempotent on re-run.
5. The schema contains these tables with the columns Phase 2 depends on:
   - `source(id, name, kind, enabled)`
   - `scope(id, name, description, include_terms, exclude_terms, categories, date_from, date_to, per_source_limit, created_at)`
   - `paper(id, doi, arxiv_id, openalex_id, s2_id, title, abstract, published_at, venue, is_preprint, oa_status, pdf_path, tei_xml, parse_status, created_at)`
   - `paper_author(id, paper_id, position, full_name)`
   - `paper_source(id, paper_id, source_id, external_id, retrieved_at)`
   - `paper_scope(paper_id, scope_id)`
   - `section(id, paper_id, parent_id, section_path, title, ordinal, page_start, page_end, char_start, char_end, body_text)`
   - `ingest_job(id, scope_id, state, papers_found, papers_parsed, started_at, finished_at, error)`
6. `paper` enforces uniqueness on `doi` and on `arxiv_id` (both nullable, unique when present).
7. `ai_researcher.llm.gateway` exposes a single `complete(messages, job, schema=None)`
   function that shells out to a CLI backend resolved from config by job type — `claude -p`
   or `codex exec`. There is no provider API key anywhere: access is via CLI subscription.
   Gateway calls run non-agentically (`codex exec --sandbox read-only`, `claude -p
   --max-turns 1`) so a model call can never modify the working tree. Every call has a
   timeout, and parallel subprocesses are capped by `LLM_MAX_CONCURRENCY`. No module outside
   `ai_researcher/llm/` invokes a CLI or imports an LLM SDK — enforced by a test that walks
   the package.
8. `EvidenceSource` is defined as a `Protocol` in `sources/base.py`; the registry maps
   source name → adapter instance and raises a named error for an unknown source.
9. arXiv, OpenAlex, and Semantic Scholar adapters each implement the protocol and are
   registered. Each is unit-tested against recorded HTTP fixtures with no live network.
10. Every adapter applies per-source rate limiting and sends a descriptive User-Agent
    identifying the tool and a contact address, read from config.
11. Deduplication merges records surfaced by multiple sources into one `paper` row with one
    `paper_source` row per source, using the identity order in Architecture.
12. `airesearch scope new <name>` runs the narrowing dialogue and persists a `scope` row.
    The dialogue must present a candidate-count estimate before and after narrowing so the
    user sees the effect of each decision.
13. `airesearch scope list` prints all scopes; `airesearch scope show <name>` prints the full
    definition including include/exclude terms and estimated corpus size.
14. `airesearch ingest <scope>` runs discover → acquire → parse → store, writes an
    `ingest_job` row, and is resumable: re-running skips papers already parsed for that scope.
15. Ingestion refuses to exceed 1,000 papers for a single scope, exiting with a clear message
    naming the current count and the ceiling.
16. When no open-access PDF is available, the paper is stored with `oa_status` recorded and
    `parse_status = 'abstract_only'` rather than being dropped or silently failing.
17. GROBID output is stored verbatim in `paper.tei_xml`, and the TEI `<body>` hierarchy is
    normalized into `section` rows preserving parent/child nesting and document order.
18. Each `section` row records `page_start`/`page_end` when GROBID provides coordinates, and
    `char_start`/`char_end` offsets into `body_text`, so Phase 2 can anchor citations.
19. `airesearch status` prints, per scope: paper count, parsed count, abstract-only count,
    failed count, and total sections.
20. Parse failures are recorded per paper with the error message and do not abort the run.
21. Structured logging to stderr at INFO by default; `--verbose` enables DEBUG. Progress
    during ingest is visible (per-paper, with a running count).
22. Secrets (API keys, DB URL) come only from environment variables or a gitignored `.env`.
    No credential is ever committed, and `.env.example` documents every required variable.

## Acceptance

Observable outcomes that prove this phase is complete:

- `uv sync && uv run ruff check . && uv run ruff format --check .` exits 0.
- `uv run pytest` exits 0 with all adapter tests running offline against fixtures.
- `uv run pytest tests/test_no_direct_model_calls.py` passes, proving no module outside
  `ai_researcher/llm/` invokes `claude` or `codex` or imports an LLM SDK.
- `docker compose up -d` followed by `docker compose ps` shows `postgres` and `grobid` both
  healthy.
- `uv run airesearch db migrate` applies all migrations from an empty database and exits 0;
  running it a second time reports "already up to date" and exits 0.
- `uv run airesearch scope new surface-codes` completes a narrowing dialogue and
  `uv run airesearch scope show surface-codes` prints include terms, exclude terms,
  categories, date range, and an estimated corpus size.
- `uv run airesearch ingest surface-codes` completes against live APIs and
  `uv run airesearch status` reports a non-zero parsed count with total sections > 0.
- Re-running `uv run airesearch ingest surface-codes` reports zero newly parsed papers,
  proving resumability.
- A SQL query joining `paper` to `section` returns, for any parsed paper, a nested section
  hierarchy whose root titles match the paper's real headings.
- Attempting a scope resolving to more than 1,000 papers exits non-zero with a message
  naming both the count and the 1,000 ceiling.

## Source

- Project: docs/superpowers/projects/ai-researcher-app/PROJECT.md
- Phase spec date: 2026-07-26
