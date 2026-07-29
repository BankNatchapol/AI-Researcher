# Phase 3: Structured Extraction & Dual Scoring

**Project:** ai-researcher-app
**Goal:** Claims, methods, results, and dates are extracted from ingested papers, each anchored to a specific tree node, linked to supporting or refuting evidence, and carrying two independent scores — pipeline confidence and evidence quality — that are never combined into one number.
**Depends on:** Phase 2

## Scope

This phase turns prose into queryable structure. It is what makes claim-level monitoring
possible in Phase 4.

1. **Extraction schema** — claims, methods, results, datasets, and metrics as first-class
   rows, every one anchored to a `tree_node`.
2. **Extraction pipeline** — per-paper LLM passes producing strict structured output, with
   schema validation and rejection of unanchored records.
3. **Evidence linking** — relations between a claim and the nodes that support or refute it,
   including cross-paper links.
4. **Confidence scorer** — a pipeline-internal score from retrieval and extraction signals.
5. **Evidence-quality scorer** — a source-and-evidence score from an explicit, documented
   rubric.
6. **Claim identity and dedup** — deciding when two papers state the same claim.
7. **Query surfaces** — CLI and MCP tools for browsing claims and their evidence.
8. **Extraction evaluation** — extending the Phase 2 gold set with extraction metrics.

## Out of Scope

Deferred — agents must not build these here:

- Monitoring, scheduling, digests, `DiscourseSource` adapters (Phase 4)
- Any use of community attention in scoring — the discourse channel does not exist yet and
  must never be a scoring input
- Figure and table grounding (post-v1; text-only extraction in this phase)
- Automated critique, peer-review generation, or survey drafting
- Vector embeddings of any kind
- Web UI

## Consumes from Prior Phase

From Phase 2:

- `tree_node` rows with stable IDs, section linkage, page ranges, and summaries
- `ai_researcher.retrieval.traverse` — used to gather candidate evidence for a claim
- `retrieval_trace` rows — retrieval signals feed the confidence score
- `eval/goldset.yaml` and `eval/harness.py` — extended here, not replaced

From Phase 1:

- `paper` metadata: `is_preprint`, `oa_status`, `published_at`, `venue`, `parse_status`
  — all are evidence-quality rubric inputs

## Produces for Next Phase

Phase 4 consumes:

- `claim` rows with stable IDs, so subscriptions can target a specific claim
- `claim_evidence` rows, so digests can report when new supporting or refuting evidence
  appears
- `claim_score` rows with timestamps, so digests can report score movement over time
- `ai_researcher.extraction.pipeline.extract_paper()` — called on newly ingested papers

## Architecture

**New package modules:**

```
src/ai_researcher/
  extraction/
    schema.py           # pydantic models for claim/method/result/dataset/metric
    pipeline.py         # per-paper extraction orchestration
    prompts.py          # extraction prompts, versioned
    validate.py         # rejects unanchored or malformed records
  evidence/
    link.py             # claim -> supporting/refuting nodes, incl. cross-paper
    identity.py         # claim dedup and canonicalization
  scoring/
    confidence.py       # pipeline-internal score
    quality.py          # evidence-quality rubric
    rubric.md           # the written rubric, human-readable and versioned
```

**Extraction flow:** for each parsed paper, walk its tree nodes, run a structured-output LLM
pass per section group, validate every record against the schema, reject anything lacking a
`tree_node_id`, then persist. Extraction is per-paper and resumable.

**The two scores — kept apart on purpose.**

`confidence` answers *"how much do I trust that the pipeline read this correctly?"* Inputs:
- number of independent nodes supporting the extraction
- whether the extracted text overlaps verbatim with node body text
- self-consistency across repeated extraction runs
- retrieval stopping reason from `retrieval_trace`
- schema validation cleanliness

`evidence_quality` answers *"how good is the underlying science?"* Inputs, from the rubric:
- full text versus abstract-only (`parse_status`)
- peer-reviewed versus preprint (`is_preprint`, `venue`)
- direct statement versus inferred (`claim_evidence.is_direct`, set by the batched stance
  call in evidence linking)
- recency (`published_at`)
- replication — count of independent papers with a supporting claim

These are stored as separate columns and rendered as separate numbers everywhere. A test
asserts no code path multiplies, averages, or otherwise merges them.

**Claim identity:** two claims are the same when they share a normalized proposition and
compatible quantities. Canonicalization uses an LLM comparison gated behind a cheap
prefilter (same metric, overlapping numeric range). Merged claims keep one canonical row and
one `claim_evidence` row per source paper — never a silent overwrite.

## Requirements

1. A migration adds `claim(id, paper_id, tree_node_id, claim_text, normalized_text,
   claim_type, subject, predicate, object_value, unit, canonical_claim_id, extraction_model,
   prompt_version, created_at)`.
2. Migrations add `method`, `result`, `dataset`, and `metric` tables, each with `paper_id`
   and a non-null `tree_node_id`.
3. A migration adds `claim_evidence(id, claim_id, tree_node_id, paper_id, stance,
   rationale_text, is_direct, created_at)` where `stance` is one of `supports`, `refutes`,
   `mentions`, and `is_direct` is a non-null boolean set by the same batched stance call.
4. A migration adds `claim_score(id, claim_id, confidence, evidence_quality, rubric_version,
   scored_at)` with `confidence` and `evidence_quality` as separate non-null columns.
5. Every extracted record has a non-null `tree_node_id`; records failing this are rejected
   and logged, never persisted. A test asserts a `NOT NULL` constraint exists on each table.
6. Extraction output is validated against pydantic models before persistence; malformed LLM
   output is retried once, then recorded as a failure for that paper without aborting the run.
7. `airesearch extract <scope>` extracts from every parsed paper lacking current extractions
   and reports per-paper counts of claims, methods, results, datasets, and metrics.
8. Extraction is resumable and idempotent: re-running with no new papers and no prompt
   version change extracts nothing.
9. `prompt_version` and `extraction_model` are recorded on every row so a prompt change can
   be detected and selectively re-run.
10. Numeric claims capture `object_value` and `unit` as separate fields, so a threshold of
    "1%" and "0.01" are comparable rather than string-matched.
11. Evidence linking finds supporting and refuting nodes for a claim using Phase 2 traversal,
    including nodes in papers other than the claim's origin paper.
12. Every `claim_evidence` row records a `rationale_text` quoted from the node body, not
    paraphrased, so the link is auditable, and an `is_direct` boolean classified in the same
    batched call, consumed later by the evidence-quality rubric (task 07).
13. Claim identity merges duplicates into a canonical claim via `canonical_claim_id`, keeping
    every original row and one `claim_evidence` row per contributing paper.
14. The dedup prefilter is non-LLM (matching metric and overlapping numeric range); the LLM
    comparison runs only on prefiltered pairs, and this ordering is asserted by a test.
15. `scoring/confidence.py` computes a 0–100 score from the inputs named in Architecture and
    records which inputs contributed.
16. `scoring/quality.py` computes a 0–100 score strictly from `scoring/rubric.md`, and the
    rubric file is versioned with `rubric_version` stored on every `claim_score` row.
17. No code path combines `confidence` and `evidence_quality`. A test greps the package for
    arithmetic on both and fails if found.
18. Community, social, or attention data is not an input to either score. A test asserts the
    `scoring` package imports nothing from a discourse module.
19. Abstract-only papers are scored, not skipped, and the rubric penalizes them explicitly.
20. `airesearch claims --scope <name>` lists claims with both scores shown as separate
    columns, filterable by `--type`, `--min-confidence`, and `--min-quality`.
21. `airesearch claim show <id>` prints the claim, both scores with their contributing
    factors, and every linked evidence node with stance and quoted rationale.
22. MCP tools `list_claims`, `get_claim`, and `find_claim_evidence` expose the same data as
    structured JSON with both scores as separate fields.
23. The gold set is extended with at least 15 hand-labelled claims carrying known
    `section_path` anchors and expected stances.
24. `airesearch eval --extraction --scope <name>` reports claim extraction precision, recall,
    and F1; evidence-span precision; and stance-label accuracy, appending to the same
    `docs/supersaiyan/runs/eval-<date>.json` report.

## Acceptance

- `uv run pytest` exits 0, including the test proving no code path merges the two scores and
  the test proving `scoring` does not import any discourse module.
- `uv run airesearch extract surface-codes` completes and reports non-zero claim counts;
  re-running extracts zero.
- A SQL query confirms zero rows in `claim`, `method`, `result`, `dataset`, or `metric` have
  a null `tree_node_id`.
- `uv run airesearch claims --scope surface-codes --min-quality 70` returns only claims whose
  `evidence_quality` is at least 70, with confidence displayed independently.
- `uv run airesearch claim show <id>` prints both scores separately, never a blended figure,
  along with linked evidence showing stance and a verbatim quoted rationale.
- A claim stated by two different papers appears once as canonical with two
  `claim_evidence` rows naming both papers.
- An abstract-only paper produces claims whose `evidence_quality` is measurably lower than a
  comparable full-text paper, demonstrating the rubric penalty.
- `uv run airesearch eval --extraction --scope surface-codes` writes a report containing
  extraction precision/recall/F1, evidence-span precision, and stance accuracy.
- MCP `list_claims` returns JSON in which `confidence` and `evidence_quality` are distinct
  top-level fields.

## Source

- Project: docs/superpowers/projects/ai-researcher-app/PROJECT.md
- Phase spec date: 2026-07-26
