# Project: AI-Researcher App

**Slug:** ai-researcher-app
**Started:** 2026-07-26
**Design:** docs/supersaiyan/designs/ai-researcher-app-design.md

## Goal

A local-first research engine for quantum computing and AI literature, built for a single
researcher. It narrows a broad topic into a defensible corpus of 100–1,000 papers, ingests
and structurally parses them, and answers questions where every statement cites a specific
paper section with a page range. Later phases extract claims, methods, results, and dates as
queryable structure with separate confidence and evidence-quality scores, then run daily
sweeps that report what changed — keeping scholarly evidence and community attention in
strictly separate channels.

The project deliberately inverts the usual priority: **retrieval → parsing → extraction →
evidence linking → scoring → synthesis.** Generated prose is the last layer, never the
center. The goal is not an "AI scientist" but the most trustworthy local research memory
and evidence engine for one person.

## Architecture

Decisions that apply across **all** phases:

- **Language/runtime:** Python 3.11+ (floor set by paper-qa and the MCP SDK).
- **Tooling:** `uv` for dependency and Python-version management, `pytest` for tests, `ruff`
  for lint and format. No Poetry, no black/flake8.
- **Single store:** PostgreSQL, plain. No vector extension. All papers, TEI, trees, claims,
  evidence links, scores, and jobs live in one database.
- **Retrieval is vectorless.** Documents are never chunked into fixed windows and never
  embedded. GROBID's TEI section hierarchy becomes a node tree per paper; a corpus-level
  PageIndex File System shortlists papers; an LLM reasons down selected trees to sections.
- **Local services via Docker Compose:** Postgres and GROBID. GROBID publishes ARM images
  for Apple Silicon. One `docker compose up` brings up the whole backing stack.
- **Model access only through the CLI gateway module.** Access is via CLI subscription
  (`claude -p`, `codex exec`) — there is no provider API key anywhere. No module outside
  `ai_researcher/llm/` invokes a model CLI or imports an LLM SDK. Backend selection by job
  type is configuration, not product logic.
- **Model calls are non-agentic and batched.** Gateway calls run read-only with a turn limit
  so they can never modify the working tree. Callers batch many items into one call — at CLI
  latency, per-item calls are the difference between an overnight job and an infeasible one.
- **Two surfaces over one core library:** a CLI and an MCP server. Neither contains business
  logic; both call the same core. No web UI in v1.
- **Sources are plugins.** Two registries with separate interfaces:
  - `EvidenceSource` — scholarly (papers, metadata, full text)
  - `DiscourseSource` — community attention (posts, scores, timestamps, links)
  Adding a source means writing one adapter against a fixed interface, never editing the
  pipeline.
- **Evidence and discourse never mix.** Nothing from a `DiscourseSource` may modify any
  evidence or confidence score. This is a hard invariant, enforced by tests.
- **Every stored assertion carries a passage anchor** — paper ID, tree node ID, section
  path, page range, and the extraction model + version. Bare claim text is never stored.
- **Confidence and evidence quality are separate scores**, computed and stored separately,
  never collapsed into a single number.

## Constraints

From `CLAUDE.md` and the confirmed design:

- Feature specs live at `docs/superpowers/specs/<slug>-design.md`
- Board tasks live at `docs/superpowers/tasks/<slug>/NN-*.md`
- Project phase specs live at `docs/superpowers/projects/ai-researcher-app/phase-N/`
- Designs live at `docs/supersaiyan/designs/<slug>-design.md`
- Python floor: **3.11**
- Platform: macOS on Apple Silicon (arm64) — all container images must have arm64 builds
- Base branch: `main`; squash-merge; auto-merge enabled
- Corpus ceiling for v1: **1,000 papers.** Precision over recall is the design objective;
  the system narrows scope rather than maximizing candidates.
- Domains: quantum computing and AI only. PubMed and biomedical sources are out of scope.
- Licenses of pinned dependencies must be permissive (Apache-2.0/MIT). Verified:
  GROBID Apache-2.0, PageIndex MIT, paper-qa Apache-2.0.
- `ai-train=no` is respected for every scraped source. No source content is ever used to
  train or fine-tune a model.

## Phases

| Phase | Name | Goal | Produces | Depends on | Status |
|-------|------|------|----------|------------|--------|
| 1 | Foundation & Corpus Ingestion | A scoped set of quantum/AI papers is discovered, fetched, parsed to structured TEI, and stored locally | Repo skeleton, Docker Compose (Postgres+GROBID), DB schema, CLI model gateway, `EvidenceSource` registry + arXiv/OpenAlex/S2 adapters, topic scoping, PDF acquisition, GROBID→TEI storage, CLI `scope`/`ingest`/`status` | — | Done |
| 2 | Vectorless Tree Retrieval & Grounded Q&A | Ask a question, get an answer where every statement cites a specific section with a page range | TEI→node tree builder, corpus-level PageIndex File System, tree traversal with budget + stopping rule, node-anchored answer synthesis, MCP server, CLI `ask`, gold set, eval harness | Phase 1 | Done |
| 3 | Structured Extraction & Dual Scoring | Claims, methods, results, and dates are extracted, anchored to tree nodes, and carry separate confidence and evidence-quality scores | Extraction schema + pipeline, passage-anchored records, evidence linking, confidence scorer, evidence-quality rubric, claim identity/dedup, CLI `extract`/`claims`, MCP tools, extraction eval | Phase 2 | Ready |
| 4 | Monitoring, Discourse & Temporal Digests | A daily sweep surfaces what changed for tracked topics and claims, with community attention in a separate channel | `DiscourseSource` registry + Reddit/HN/Google-blogs/HF-alphaXiv adapters, APScheduler jobs, change detection, temporal digests, topic+claim subscriptions, SciRate spike with defer exit, CLI `monitor`/`digest` | Phase 3 | Queued |

## Known Risks

Recorded so later phases inherit them rather than rediscovering them:

1. **Unused-tool risk.** The failure mode for personal tools is building everything and never
   opening it. The usability test lands at the end of Phase 2. If Phase 2 ships and goes
   unused for two weeks, that is a signal to stop, not to build Phase 3.
2. **Benchmark transfer.** PageIndex reports 98.7% on FinanceBench, which measures
   single-document lookup over 10-K filings. This project's central question is
   cross-document. Treat that number as evidence the approach is sound, not as a predicted
   result. The Phase 2 gold set exists to settle it empirically.
3. **PageIndex File System maturity.** It is the newest layer in that stack. **Named
   fallback:** a Postgres full-text prefilter to shortlist papers, with per-paper tree
   reasoning unchanged. Adopt the fallback if corpus-level trees underperform on the gold set.
4. **Tree build cost.** Building a tree requires an LLM pass per paper for node summaries.
   Trees must be cached and versioned so re-ingestion does not re-pay that cost.
5. **SciRate is not dependable.** robots.txt permits crawling (`search=yes`, `Allow: /`) but
   sets `ai-train=no` and `use=reference`, and Cloudflare returns 403 to non-browser clients.
   The `scirate` PyPI client is v0.1.0 from April 2018 and scrapes HTML — effectively dead.
   It is a time-boxed spike in Phase 4 with an explicit defer-to-future-work exit, never a
   dependency.
6. **Naming collision.** SciRate "scites" (community upvotes, an attention signal) are
   unrelated to scite.ai "Smart Citations" (citation-intent classification, an evidence
   signal). Conflating them would corrupt the scoring layer.
7. **CLI-subscription model access is the binding cost constraint.** There is no provider
   API key; every model call is a `claude -p` or `codex exec` subprocess with multi-second
   startup, subject to subscription rate caps. This makes **batching mandatory, not an
   optimization**. Per-item calls at the 1,000-paper ceiling would mean 15,000+ invocations
   and 20+ hours; batched, the same work is roughly 1,000 calls and runs overnight. Any task
   that loops the gateway per item is a defect. Recorded escape hatch: if API access is ever
   obtained, add a LiteLLM backend behind the same `complete()` interface — no caller changes.
8. **`data/papers/` (the PDF `STORAGE_DIR`) is not gitignored.** Found during Phase 1 review,
   2026-07-26. No harm yet — nothing has been ingested against this repo — but a real
   `airesearch ingest` run before this is fixed risks committing downloaded PDFs, which may
   be copyrighted. Fix: add `data/papers/` (or the configured `STORAGE_DIR`) to `.gitignore`
   before the first real ingest.
9. **`tei.py`'s page-range extraction only reads the first coordinate group in GROBID's
   `coords` attribute.** Found during Phase 1 review, 2026-07-26. GROBID coords are
   semicolon-separated `page,x,y,w,h` groups, one per line-box; `_page_from_coords` takes only
   the first group. A paragraph that starts on one page and continues onto the next is
   attributed entirely to its starting page when it is the only paragraph in its section —
   understating `page_end`. Low blast radius today (no phase depends on exact page ranges
   yet), but Phase 2 builds citation rendering directly on `section.page_start`/`page_end`,
   so a wrong page range there is worse than a missing one. Fix before Phase 2 task 05
   (answer synthesis / citation rendering) ships: parse all semicolon-separated groups per
   `<p>` and take the true min/max page across all of them, not just the first group's page.
10. **Two independent identity-matching heuristics exist and can disagree.**
    `scoping/estimate.py` (DOI → normalized title → source+external_id) and
    `ingest/dedup.py` (DOI → arXiv ID → title+first-author-surname+year) are separately
    implemented. The estimate shown by `airesearch scope show` before ingesting can
    therefore run slightly higher than the deduplicated corpus size `ingest` actually
    produces, since the estimate's heuristic merges less aggressively. Not a bug — the
    estimate is documented as an estimate — but worth consolidating into one shared identity
    function if the discrepancy becomes confusing in practice.

## Running the Project

Each phase runs through the autonomous loop independently. Each tool reads its own board
config, so switching tools between phases never requires editing a shared file:

```
# Phase 1-2 (Codex, per phase ownership below):
scripts/supersaiyan-codex-run.sh ai-researcher-codex

# when a phase is Done, unlock the next one:
/supersaiyan prepare ai-researcher-app --phase N

# Phase 3-4 (Cursor):
scripts/supersaiyan-cursor-run.sh ai-researcher-cursor
```

`/supersaiyan prepare` works identically regardless of which tool builds the phase — it
only files issues and reconciles the board, it never touches `worker_backend`.

## Source

- Design: docs/supersaiyan/designs/ai-researcher-app-design.md
- Phases: docs/superpowers/projects/ai-researcher-app/phase-N/
- Origin report: project-report.md
