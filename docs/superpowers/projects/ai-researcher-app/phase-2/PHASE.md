# Phase 2: Vectorless Tree Retrieval & Grounded Q&A

**Project:** ai-researcher-app
**Goal:** A researcher can ask a natural-language question against an ingested scope and receive an answer in which every statement cites a specific paper section with a page range, retrieved entirely without embeddings via LLM reasoning over document trees.
**Depends on:** Phase 1

## Scope

This phase turns a parsed corpus into a working research assistant. It is the phase that
answers "do I actually use this?"

1. **Tree builder** — convert each paper's `section` hierarchy into a PageIndex-style node
   tree, with an LLM-generated summary per node. Cached and versioned.
2. **Corpus-level index** — a PageIndex File System over all paper trees in a scope, used to
   shortlist papers before per-paper traversal.
3. **Traversal engine** — LLM reasoning that walks from the corpus index down into selected
   paper trees to specific sections, under an explicit node budget and stopping rule.
4. **Answer synthesis** — compose an answer where every statement is attributed to retrieved
   nodes, with section path and page range.
5. **Insufficient-evidence path** — when the budget is exhausted or retrieved nodes do not
   support an answer, say so instead of generating unsupported prose.
6. **MCP server** — expose scoping, ingestion status, and asking as MCP tools.
7. **CLI `ask`** — the same capability from the terminal.
8. **Gold set and eval harness** — 20–30 questions with known evidence sections, plus a
   command that scores retrieval and citation correctness.

## Out of Scope

Deferred — agents must not build these here:

- Claim/method/result/date extraction and any structured records (Phase 3)
- Confidence and evidence-quality scoring (Phase 3)
- Monitoring, scheduling, digests, discourse sources (Phase 4)
- Any vector embedding, similarity search, or reranker model
- New evidence source adapters beyond Phase 1's three
- Web UI

## Consumes from Prior Phase

From Phase 1:

- `paper` rows with `tei_xml` and `parse_status = 'parsed'`
- `section` rows with `section_path`, `title`, `page_start`, `page_end`, `char_start`,
  `char_end`, `body_text`, and parent/child nesting
- `scope` and `paper_scope` defining the working corpus
- `ai_researcher.llm.gateway.complete()` for all model calls
- `ai_researcher.db` connection handling and migration runner
- The `airesearch` Typer app, extended here with `ask` and `index`

## Produces for Next Phase

Phase 3 consumes:

- `tree_node` rows — the per-paper node trees with summaries, stable IDs, and section linkage
- `ai_researcher.retrieval.traverse` — the interface returning ranked nodes for a query
- `retrieval_trace` rows — what was expanded and selected for a given query, so Phase 3 can
  attach confidence signals to the retrieval that produced a claim
- The gold set and eval harness, extended in Phase 3 with extraction metrics

## Architecture

**New package modules:**

```
src/ai_researcher/
  trees/
    build.py            # section hierarchy -> tree_node rows + LLM node summaries
    corpus.py           # PageIndex File System over paper trees in a scope
    version.py          # tree schema + summary-model versioning and invalidation
  retrieval/
    traverse.py         # budgeted LLM tree search; returns ranked nodes + trace
    budget.py           # node-expansion budget and stopping rule
  answer/
    synthesize.py       # nodes -> answer with per-statement citations
    citation.py         # node -> (paper, section_path, pages) rendering
  mcp/
    server.py           # MCP tool definitions over the core library
  eval/
    goldset.py          # load/validate the gold set
    harness.py          # retrieval + citation scoring
```

**Retrieval flow:**

```
question
  -> corpus index (File System)  : 1000 papers -> <= 20 candidate papers
  -> per-paper tree traversal    : LLM expands nodes under a budget
  -> selected nodes              : ranked, each with section_path + pages
  -> synthesis                   : answer where every statement cites node IDs
```

No step embeds text or computes similarity. Selection is LLM reasoning over node titles and
summaries, which is why traces are human-readable.

**Tree node granularity:** one `tree_node` per `section` row, preserving Phase 1's nesting.
Node summaries are capped at 60 words. Papers deeper than 4 levels are flattened at level 4
so traversal cost stays bounded.

**Versioning and invalidation:** each `tree_node` records `tree_schema_version` and
`summary_model`. A tree is rebuilt only when either changes or when the paper is re-parsed.
Rebuilds are per-paper, never corpus-wide, so an ingest of 10 new papers costs 10 tree builds.

**Budget and stopping rule:** traversal expands at most `max_nodes` (default 40) across all
candidate papers for one question. Traversal stops early when the model reports sufficient
evidence. If the budget is exhausted first, the answer is produced from what was gathered
**and explicitly labelled as budget-limited**, or reported as insufficient evidence when
fewer than 2 supporting nodes were found.

**Documented fallback (from PROJECT.md risk 3):** if corpus-level trees underperform on the
gold set, replace `trees/corpus.py` shortlisting with a Postgres full-text prefilter over
`section.body_text` and `paper.title`/`abstract`. Per-paper traversal is unchanged. The
interface `shortlist(scope, question, limit) -> list[paper_id]` is defined so either
implementation satisfies it.

## Requirements

1. A migration adds `tree_node(id, paper_id, section_id, parent_id, node_path, title,
   summary, page_start, page_end, depth, tree_schema_version, summary_model, created_at)`.
2. A migration adds `retrieval_trace(id, question, scope_id, expanded_node_ids,
   selected_node_ids, nodes_expanded, stopped_reason, created_at)`.
3. `airesearch index <scope>` builds trees for every parsed paper in the scope that lacks a
   current tree, and reports how many were built versus skipped.
4. Tree building is idempotent: re-running `index` with no version change and no new papers
   builds zero trees.
5. Every `tree_node` links to exactly one `section` row and inherits its `page_start`,
   `page_end`, and `section_path`, so citations resolve to real pages.
6. Node summaries are generated through `llm.gateway` and are 60 words or fewer; generation
   is batched per paper, not one call per node.
7. Trees deeper than 4 levels are flattened at level 4, and the flattening is recorded in
   `node_path` so no content is lost.
8. `shortlist(scope, question, limit) -> list[paper_id]` is defined as a protocol with the
   PageIndex File System as the default implementation and a Postgres full-text
   implementation available behind config, so the fallback needs no code rewrite.
9. `traverse(question, scope, max_nodes) -> TraversalResult` returns ranked nodes plus a
   trace of every node expanded and the stopping reason.
10. The default node budget is 40 and is overridable per call and via config.
11. Traversal writes one `retrieval_trace` row per question with `stopped_reason` in
    {`sufficient_evidence`, `budget_exhausted`, `no_candidates`}.
12. Answer synthesis attributes every factual statement to one or more node IDs. A statement
    with no node attribution is a bug, caught by a test on a fixture corpus.
13. Citations render as paper title, section path, and page range, and include the paper's
    DOI or arXiv ID so the user can open the source.
14. When traversal returns fewer than 2 supporting nodes, the system reports insufficient
    evidence and does not synthesize an answer.
15. When `stopped_reason = 'budget_exhausted'`, the answer is labelled budget-limited in
    CLI output and in the MCP tool response.
16. `airesearch ask "<question>" --scope <name>` prints the answer with numbered citations
    and, under `--verbose`, the full traversal trace.
17. `airesearch ask --json` emits machine-readable output containing answer text, citations
    with node IDs and page ranges, and the trace summary.
18. An MCP server exposes at least these tools: `list_scopes`, `scope_status`,
    `ask_corpus`, `get_paper_sections`. Each returns structured JSON, never prose blobs.
19. The MCP server runs over stdio and is startable with `uv run airesearch mcp`.
20. Neither `cli.py` nor `mcp/server.py` contains retrieval or synthesis logic; both call the
    same core functions, verified by a test asserting the shared code path.
21. A gold set of at least 20 questions lives at `eval/goldset.yaml`, each with the question,
    the scope, and the `section_path`s of sections that genuinely answer it.
22. `airesearch eval --scope <name>` reports retrieval recall@k against gold sections,
    citation precision (fraction of cited nodes that are gold), and the rate of unsupported
    statements.
23. Eval results are written to `docs/supersaiyan/runs/eval-<date>.json` so runs are
    comparable over time.
24. The eval harness runs against a committed fixture corpus offline in CI, and against the
    live corpus when pointed at a real scope.

## Acceptance

- `uv run pytest` exits 0, including a test proving every synthesized statement carries a
  node attribution.
- `uv run airesearch index surface-codes` builds trees and reports counts; re-running builds
  zero and exits 0.
- A SQL query confirms every `tree_node` has a non-null `section_id` and a `summary` of 60
  words or fewer.
- `uv run airesearch ask "What threshold estimates are reported for the surface code?" --scope surface-codes`
  prints an answer where each statement carries a numbered citation resolving to a real paper,
  section path, and page range.
- Running the same command with `--verbose` prints the traversal trace showing which nodes
  were expanded and why traversal stopped.
- Asking a question with no support in the corpus returns an explicit insufficient-evidence
  message rather than a synthesized answer.
- Setting the budget to a deliberately low value (`--max-nodes 2`) produces a response
  labelled budget-limited.
- `uv run airesearch mcp` starts an MCP server that responds to a `tools/list` request with
  at least the four required tools.
- `uv run airesearch eval --scope surface-codes` completes and writes a JSON report
  containing recall@k, citation precision, and unsupported-statement rate.
- Switching `shortlist` to the Postgres full-text implementation via config and re-running
  `eval` produces a comparable report, proving the fallback path works.

## Source

- Project: docs/superpowers/projects/ai-researcher-app/PROJECT.md
- Phase spec date: 2026-07-26
