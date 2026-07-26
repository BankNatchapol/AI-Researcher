# AI-Researcher App

**Mode:** Builder
**Date:** 2026-07-26
**Slug:** ai-researcher-app

## Problem

Staying on top of quantum computing and AI literature is a daily, compounding cost. Both
fields are arXiv-dominant and fast-moving: dozens of potentially relevant preprints appear
per day, claims are made and quietly revised, and the same result gets restated across
papers with different framing. The practical failures are specific:

1. **Scope explodes.** A query like "quantum error correction" returns thousands of papers.
   Existing tools optimize for recall — they hand back more candidates, which makes the
   problem worse, not better.
2. **Claims aren't verifiable without reading everything.** General chat assistants answer
   confidently about papers with no passage anchoring and a documented tendency to
   fabricate references.
3. **Nothing persists.** Each session starts cold. What was read, what was believed, and
   what changed since is not retained anywhere queryable.
4. **The tooling is fragmented or rented.** Open source does one thing each — PaperQA
   answers with citations, GROBID parses structure, OpenAlex serves metadata, Zotero
   manages a library. Commercial tools integrate all of it but keep the data in their cloud.

## Target User

One researcher — the repo owner — working across quantum computing and AI. Single user,
single machine. No second persona, no team, no customers.

Concrete consequences they face: hours lost re-reading papers already read; missing
relevant work published while heads-down; citing claims that can't be quickly re-grounded
to a specific passage when challenged.

## Status Quo

Manual arXiv and SciRate browsing to spot new work. Ad-hoc questions to general chat
assistants about papers, with no passage grounding and no memory between sessions. Zotero
available but not central. No persistent claim store, no monitoring, no way to ask "what
changed about this specific result since last month."

Cost: recurring daily reading overhead, plus the tail risk of building on a claim that was
already contested in a paper never surfaced.

## Demand Evidence

This is a personal tool, so the only honest demand test is whether the owner uses it after
it ships. Stated intent is not evidence, and this section should not pretend otherwise.

What exists today: the owner independently produced a deep landscape report on this problem
space, and already browses SciRate on a near-daily cadence to track quantum work. That is
real behavior around the problem, not around the solution.

**Explicit risk:** the failure mode for personal tools is building the full architecture and
then not opening it. Phase 1 is deliberately scoped to be independently useful so that
"do I actually use this?" is answered before Phases 2 and 3 are built. If Phase 1 goes
unused for two weeks, that is a signal to stop, not to keep building.

## Proposed Direction

A local-first research engine for quantum computing and AI, built as one core library with
two thin surfaces (CLI and MCP server). The owner keeps all data and indexes on their own
machine; model access goes through a single gateway that shells out to the `claude` or
`codex` CLI, since access is by subscription rather than a provider API key.

The architecture inverts the usual priority: **retrieval → parsing → extraction → evidence
linking → scoring → synthesis**. Generated prose is the last layer, never the center.

Five design commitments distinguish it from the surveyed landscape:

1. **Narrowing, not broadening.** The system argues the topic down to a defensible corpus
   boundary before ingesting. Precision over recall is the explicit objective.
2. **Every assertion carries a passage anchor.** No bare claim text is ever stored.
3. **Two scores, never merged.** Model confidence (pipeline-internal) and evidence quality
   (source-and-evidence properties) are computed and stored separately.
4. **Evidence and discourse are separate channels.** Scholarly evidence and community
   attention are never mixed; attention can never move an evidence score.
5. **Sources are plugins.** Adding a source means writing one adapter against a fixed
   interface — not editing the pipeline.

### Stack (v1)

| Layer | Choice | Rationale |
|---|---|---|
| Store | PostgreSQL (plain) | One durable store for papers, TEI, trees, claims, evidence links, scores, jobs. No vector extension in v1. |
| Parsing | GROBID (Docker) | Apache 2.0, TEI XML with real section hierarchy — feeds the tree builder directly and patches PageIndex's documented PDF-parsing weakness. ~10.6 PDF/sec on 16 CPUs. |
| Retrieval | PageIndex-style trees (vectorless) | Per-paper node trees (title, summary, section/page range) plus a corpus-level PageIndex File System for shortlisting. LLM reasoning replaces similarity search. |
| Model gateway | CLI subprocess (`claude -p` / `codex exec`) | Access is via CLI subscription, not a provider API key. Backend resolved per job from config; calls run read-only and turn-limited. |
| Surfaces | CLI + MCP server | Both over one core library. MCP makes the engine callable from Claude Code directly. |
| Runtime | Python 3.11+, uv, pytest, ruff | Matches paper-qa (3.11+), GROBID clients, and the MCP SDK. |
| Local services | Docker Compose | Postgres + GROBID in one `docker compose up`. GROBID publishes ARM images for Apple Silicon. |
| Scheduler | APScheduler (Phase 3) | Minimal operational surface for daily sweeps. |

**Retrieval is vectorless by design.** Documents are never chunked into fixed windows and
never embedded. GROBID's TEI hierarchy becomes a node tree per paper; a corpus-level
PageIndex File System narrows 1,000 papers to a working set; an LLM then reasons down the
selected trees to specific sections. Retrieval paths are therefore human-readable and
auditable — a property opaque vector similarity cannot offer, and one that matters when the
whole point is verifiable evidence.

**Documented fallback:** PageIndex File System is the newest and least proven layer in that
stack. If corpus-level trees underperform on the gold set, the named fallback is a Postgres
full-text prefilter to shortlist papers, with per-paper tree reasoning unchanged. This is
recorded now so the failure has a planned exit rather than a redesign.

Deliberately **excluded from v1**: pgvector and all embedding-based retrieval, Neo4j,
DuckDB/Parquet, a local OpenAlex mirror, a web UI, and fully-local inference. Each is a real
option later; none is justified before a concrete wall is hit. The report proposed five
persistent stores for a single-user MVP — this design uses one, with no vector index.

### Source adapters

Two interfaces, strictly separated:

- **`EvidenceSource`** — scholarly. Yields papers, metadata, and full text.
  v1: arXiv (API + RSS), OpenAlex, Semantic Scholar. Crossref for DOI resolution.
  Optional importer: Zotero (read-only, via local API/SQLite).
- **`DiscourseSource`** — community attention. Yields posts/scores/timestamps and links.
  v1: Reddit (r/QuantumComputing, r/MachineLearning), Hacker News, Google Research and
  Google Quantum AI blogs (RSS), Hugging Face Papers / alphaXiv.

Both register through a common adapter registry so new sources are additive.

## Wedge / MVP

**Phase 1 — scope, ingest, and answer with citations.**

The smallest independently useful version: point it at a topic, have it interrogate you
until the scope is narrow and defensible, ingest the resulting 100–1,000 papers, and answer
questions with passage-level citations you can click through and verify.

That is usable on its own with no Phase 2 or 3, and it directly replaces the current
workflow of manual browsing plus ungrounded chat.

## Key Premises

1. **Personal tool, single user.** No auth, no multi-tenancy, no onboarding.
2. **Local-first = owning data and index.** Papers, parsed text, embeddings, claims, and
   scores live in local Postgres. Passages *do* leave the machine on LLM calls — accepted.
3. **v1 stack is plain Postgres, GROBID, a CLI model gateway, PageIndex-style trees.** One store, two
   services, no vector index. Retrieval is vectorless: GROBID hierarchy → per-paper node
   trees → corpus-level File System for shortlisting → LLM tree traversal.
4. **Two surfaces over one core library:** CLI and MCP. No web UI in v1.
5. **Precision over recall.** Corpus stays at 100–1,000 papers; the system actively narrows
   scope rather than maximizing candidates.
6. **Sources are pluggable adapters**, split into `EvidenceSource` and `DiscourseSource`.
   v1 evidence: arXiv, OpenAlex, Semantic Scholar (+Crossref for DOI). v1 discourse: Reddit,
   Hacker News, Google Research/Quantum AI blogs, Hugging Face Papers/alphaXiv.
   PubMed is out of scope — wrong domains.
7. **Zotero is an optional read-only importer**, never a runtime dependency, never a plugin
   target. The app is standalone; Zotero is one ingestion path among several.
8. **Evaluation starts in Phase 1.** A hand-labeled gold set (~20–30 questions with known
   evidence passages) is built as soon as a corpus exists. Without it, every later scoring
   claim is unfalsifiable.
9. **Confidence and evidence quality stay separate.** Stored separately, never collapsed.
10. **Every stored assertion carries a passage anchor** — paper ID, section, chunk, char
    span, extraction model. No bare claim text.
11. **Discourse never moves evidence scores.** Community attention is displayed alongside
    evidence, never folded into it.

## Landscape

Verified during this session (the source report's citation markers were unresolvable, so
load-bearing facts were re-checked directly):

- **paper-qa / PaperQA2** — Apache 2.0, Python 3.11+, CalVer since Dec 2025. Three-tool
  agentic flow: paper search → gather evidence → generate answer. Already routes through
  LiteLLM. The closest reference architecture for Phase 1; permissive license. Note its
  LiteLLM path is unusable here — see the subscription constraint below.
- **GROBID** — Apache 2.0, OpenJDK 21, Docker images published, TEI XML with 68 labels.
- **PageIndex** (VectifyAI, Sept 2025) — MIT, Python, 34.6k stars, 322 commits. Builds a
  hierarchical tree per document (each node: title, summary, page range), then has an LLM
  reason over the tree to select nodes. No chunking, no embeddings. Reports 98.7% on
  FinanceBench. A "PageIndex File System" layer extends tree reasoning across a whole
  corpus. Documented weakness: standard PDF parsing in the OSS package. Maintenance signal:
  68 open issues, 75 open PRs — pin the version.
- **pgvector** — v0.8.5, HNSW + IVFFlat, up to 16k dimensions, hybrid search alongside
  Postgres FTS. Evaluated and **not used in v1**; recorded as the escape hatch if vectorless
  retrieval fails on the gold set.

**Transfer risk worth stating plainly:** FinanceBench measures single-document lookup over
10-Ks — long, rigidly structured filings with consistent tables of contents. This project's
central question ("across 500 papers, what is actually claimed about X?") is cross-document,
which is a different retrieval shape than that benchmark exercises. Papers are shorter and
more uniformly structured than 10-Ks, which likely helps; but the 98.7% figure should be
treated as evidence the approach is sound, not as a predicted result here. The gold set in
Phase 1 exists precisely to settle this.
- **SciRate** — MIT, Rails + Elasticsearch + Postgres, no documented API or JSON export.
  robots.txt (Cloudflare Content-Signals) sets `search=yes, ai-train=no, use=reference`
  with `Allow: /`; `ai-input` is unspecified. The site returns **403 to non-browser clients**
  even with a browser UA. The `scirate` PyPI client is v0.1.0, last released **April 2018**,
  and scrapes HTML — effectively dead.

**Naming collision worth recording:** SciRate "scites" are Reddit-style upvotes meaning "I
found this interesting" — explicitly *not* peer review, and skewed toward well-known groups
and trending keywords. This is unrelated to scite.ai "Smart Citations," which classify
citation intent (supporting/contrasting/mentioning). The first is an attention signal; the
second is an evidence signal. Conflating them would corrupt the scoring layer.

**Where the landscape falls short:** open source is strong at one function each and weak at
integration; commercial tools integrate well but are cloud-resident. Neither optimizes for
narrowing scope — every surveyed tool maximizes recall. That gap plus local-first ownership
is the wedge.

## Out of Scope (initial)

- Autonomous paper writing, hypothesis generation, or experiment design ("AI scientist")
- Automated peer-review or critique generation
- Multi-user, auth, hosting, or any productization
- Web UI or visual graph explorer
- PubMed and biomedical coverage
- Neo4j, DuckDB/Parquet analytics, local OpenAlex mirror
- Vector embeddings and similarity search of any kind (pgvector is the recorded escape hatch,
  not a v1 component)
- Fully-local LLM inference
- Figure and table grounding (acknowledged as a real domain requirement for benchmark
  tables and ablations — deferred to post-v1, not dismissed)
- **SciRate ingestion** — time-boxed spike in Phase 3 only. If Cloudflare blocking makes a
  polite signal-only fetch impractical, it moves to future work rather than blocking a phase.

## Open Questions

Deferred to the spec phase:

1. **Tree node granularity.** How deep does the tree go — section, subsection, or paragraph?
   Deeper trees give sharper citations but cost more tokens per traversal. What is the node
   summary length budget?
2. **Traversal budget and stopping rule.** How many nodes may an LLM expand per query before
   it must answer? What happens when the budget is exhausted mid-traversal — answer with
   partial evidence, or report insufficient evidence?
3. **Topic-scoping interaction.** What does the narrowing dialogue actually look like — how
   does the system propose sub-topics, and what does the user accept or reject? What is the
   persisted representation of a "scoped topic"?
4. **PDF acquisition.** Which papers are legally fetchable in full text, and what happens
   when only an abstract is available? Does evidence quality encode abstract-only?
5. **Evidence quality rubric.** What concrete features feed it — full-text vs abstract,
   direct vs inferential, peer-reviewed vs preprint, table/figure-backed vs narrative,
   recency, replication?
6. **Gold set construction.** Who labels the 20–30 evaluation questions, and against which
   seed topic?
7. **Claim identity and dedup.** When two papers state the same result differently, is that
   one claim with two evidence links or two claims related by an edge?
8. **Tree build cost and invalidation.** Building a tree requires an LLM pass per paper to
   generate node summaries. What does that cost per paper, and when must a tree be rebuilt
   (new GROBID version, new model, corrected PDF)? Are trees cached and versioned?
9. **Monitoring trigger semantics.** Does a daily sweep watch topics, specific claims, or
   both? Claim-level monitoring is the differentiator but depends on Phase 2.
10. **Reddit API access.** OAuth app registration, free-tier rate limits, and whether those
    limits support the intended sweep cadence.
