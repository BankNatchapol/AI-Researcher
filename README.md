# AI-Researcher

A local-first research engine for quantum computing and AI literature, built for a single
researcher. It narrows a broad topic into a defensible corpus of 100–1,000 papers, ingests
and structurally parses them, and answers questions where every statement cites a specific
paper section with a page range. It extracts claims, methods, results, and datasets as
queryable structure with two independent scores — pipeline confidence and evidence
quality — and runs daily sweeps that report what changed, keeping scholarly evidence and
community attention in strictly separate channels.

Retrieval is vectorless: no embeddings, no vector database. GROBID's TEI section hierarchy
becomes a per-paper node tree; an LLM reasons down selected trees to the exact sections that
answer a question.

## Status

v1 is complete — all four phases shipped and merged:

| Phase | What it built |
|---|---|
| 1 — Foundation & Corpus Ingestion | Topic scoping, multi-source discovery/dedup, PDF acquisition, GROBID parsing |
| 2 — Vectorless Tree Retrieval & Grounded Q&A | Node trees, budgeted tree traversal, cited answer synthesis, MCP server |
| 3 — Structured Extraction & Dual Scoring | Claim/method/result extraction, evidence linking, confidence + evidence-quality scoring |
| 4 — Monitoring, Discourse & Temporal Digests | Discourse adapters, subscriptions, daily sweeps, change detection, digests |

## Why vectorless

Chunking and embedding a paper throws away the one structure a paper already has: its
section hierarchy. This project parses that hierarchy directly (via GROBID → TEI) into a
tree per paper, then has an LLM traverse the tree the way a researcher would — narrowing
from title to section to paragraph — instead of nearest-neighbor search over floating-point
vectors. Every answer traces back to a specific tree node with a page range, not a
similarity score.

## Hard invariants

These hold across the whole codebase, each backed by a test that fails the build if broken:

- **Retrieval is vectorless** — no embeddings, no vector similarity, no reranker models.
- **Every stored claim carries a passage anchor** — paper, tree node, section path, page
  range. Bare claim text is never stored.
- **Confidence and evidence quality are separate scores** — never averaged, multiplied, or
  blended into one number. `confidence` describes the pipeline; `evidence_quality` describes
  the science.
- **Evidence and discourse are separate channels** — nothing from Reddit/HN/RSS/etc. may
  influence a score. Community attention measures interest, not validity.
- **All model calls go through one CLI gateway** — access is via CLI subscription
  (`claude -p`, `codex exec`), never a provider API key.
- **Corpus ceiling is 1,000 papers per scope** — precision over recall.

## Stack

Python 3.11+ · [`uv`](https://docs.astral.sh/uv/) for dependencies and tooling · `pytest` +
`ruff` · PostgreSQL (plain, no vector extension) · [GROBID](https://github.com/kermitt2/grobid)
in Docker for PDF → TEI parsing · a CLI (`airesearch`) and an MCP server over one core
library.

## Quick start

```bash
# 1. Bring up Postgres + GROBID
docker compose up -d

# 2. Install dependencies
uv sync

# 3. Configure environment (contact email, DB URL, LLM backend, etc.)
cp .env.example .env

# 4. Apply the schema
uv run airesearch db migrate

# 5. Scope a topic and pull in papers
uv run airesearch scope new my-topic --description "..." --category quant-ph
uv run airesearch ingest my-topic

# 6. Ask a question, grounded in the corpus
uv run airesearch ask "What's the current surface code threshold?" --scope my-topic

# 7. Extract structured claims with dual scores
uv run airesearch extract my-topic
uv run airesearch claims --scope my-topic --min-quality 70

# 8. Track a topic and get a digest of what changed
uv run airesearch subscribe topic my-topic
uv run airesearch sweep --kind evidence
uv run airesearch sweep --kind discourse
uv run airesearch digest --since 2026-01-01
```

Run `uv run airesearch --help` for the full command list, or `uv run airesearch mcp` to
serve the same tools over MCP stdio.

## Development

```bash
uv run pytest                  # all tests
uv run ruff check .            # lint
uv run ruff format --check .   # format check
```

See [`AGENTS.md`](AGENTS.md) for the full architecture, conventions, and phase-by-phase task
contracts that agents (Claude Code, Codex, Cursor) build against in this repo.
