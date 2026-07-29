# Issue #47 — QA v6 report

- Issue: #47 — Compute the pipeline confidence score
- Pull request: #56
- Branch: `issue-47-compute-the-pipeline-confidence-score`
- Builder rebuild: `9e9d3d6`
- Result: PASS
- Scope: Tester verification after Reviewer rebuild 5

## Acceptance results

### AC1 — bounded, explainable score

PASS. `test_score_returns_bounded_value_and_names_every_contributing_factor`
observes a `ConfidenceScore` bounded to 0–100, verifies all five named factor
contributions, and confirms the total is their rounded sum.

### AC2 — all five pipeline factors contribute

PASS. The focused suite varies each required factor in isolation:

- independent supporting-node count
- order-sensitive verbatim overlap
- repeated-extraction self-consistency
- retrieval stopping reason
- schema-validation cleanliness

Production-path regressions also prove that real same-claim extraction
observations reach self-consistency scoring, persisted validation outcomes
are loaded, evidence and retrieval changes refresh stale scores, and
canonicalization refreshes scores whose supporting-node inputs changed.

### AC3 — budget exhaustion is penalized

PASS. `test_budget_exhausted_scores_lower_than_identical_sufficient_evidence_claim`
compares otherwise-identical claims and observes a strictly lower score for
`budget_exhausted`.

### AC4 — confidence is stored separately

PASS. `test_postgres_store_targets_claim_score_confidence_without_quality_scoring`
observes the insert into `claim_score.confidence`. Evidence quality remains
stored independently, and no discourse input is introduced.

### AC5 — exact task command

PASS. `uv run pytest tests/test_confidence.py` exited 0 with 20 passing tests
and no skips.

## Rebuild 5 verification

`test_default_dedup_refreshes_scores_created_by_prior_no_dedup_run` passed
against PostgreSQL without skipping. It first scores two linked claims through
`extract --no-dedup`, then runs default canonicalization and observes both
claims become score-eligible again. The canonical root receives a new, higher
confidence score after gaining the second independent supporting node.

## Review threads

All PR review threads are resolved. There are no unresolved `[QA]` threads.

## Repository verification

- `uv run pytest tests/test_confidence.py` — PASS, 20 tests
- Rebuild-5 PostgreSQL regression — PASS, 1 test
- `uv run pytest` — PASS, 220 tests
- `uv run ruff check .` — PASS
- `uv run ruff format --check .` — PASS, 101 files
- `git diff --check origin/main...HEAD` — PASS

## Visual evidence

Intentionally omitted. Issue #47 changes backend scoring, PostgreSQL
persistence, tests, and CLI orchestration only; it has no UI or visual
acceptance criteria.
