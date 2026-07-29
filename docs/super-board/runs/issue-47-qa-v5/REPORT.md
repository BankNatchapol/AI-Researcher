# Issue #47 — QA v5 report

- Issue: #47 — Compute the pipeline confidence score
- Pull request: #56
- Branch: `issue-47-compute-the-pipeline-confidence-score`
- Builder rebuild: `3e5f2e2`
- Result: PASS
- Scope: Tester verification after Reviewer rebuild 4

## Acceptance results

### AC1 — bounded, explainable score

PASS. `test_score_returns_bounded_value_and_names_every_contributing_factor`
observes a `ConfidenceScore` bounded to 0–100 and verifies every named
factor contribution.

### AC2 — all five pipeline factors contribute

PASS. The focused suite varies each required factor in isolation:

- independent supporting-node count
- order-sensitive verbatim overlap
- repeated-extraction self-consistency
- retrieval stopping reason
- schema-validation cleanliness

Production-path regressions also prove that real same-claim extraction
observations reach self-consistency scoring, validation outcomes are loaded,
and newer supporting evidence or retrieval traces make an existing score
eligible for refresh.

### AC3 — budget exhaustion is penalized

PASS. `test_budget_exhausted_scores_lower_than_identical_sufficient_evidence_claim`
compares otherwise-identical claims and observes a strictly lower score for
`budget_exhausted`.

### AC4 — confidence is stored separately

PASS. `test_postgres_store_targets_claim_score_confidence_without_quality_scoring`
observes the insert into `claim_score.confidence`. Evidence quality remains
stored independently and no discourse input is introduced.

### AC5 — exact task command

PASS. `uv run pytest tests/test_confidence.py` exited 0 with 19 passing tests.

## Rebuild 4 verification

`test_confidence_refreshes_when_evidence_and_trace_arrive_after_initial_score`
passed against PostgreSQL without skipping. It creates an incomplete score,
adds a newer supporting evidence link and `sufficient_evidence` retrieval
trace, and observes a refreshed, higher persisted confidence score.

## Tester-owned review thread

The extra blank line at the end of
`docs/super-board/runs/issue-47-qa-v3/REPORT.md` was reproduced with
`git diff --check origin/main...HEAD` and removed. The combined branch plus
working-tree diff now passes `git diff --check origin/main`.

## Repository verification

- `uv run pytest tests/test_confidence.py` — PASS, 19 tests
- Rebuild-4 PostgreSQL regression — PASS, 1 test, 11 deselected
- `uv run pytest` — PASS, 219 tests
- `uv run ruff check .` — PASS
- `uv run ruff format --check .` — PASS, 101 files
- `git diff --check origin/main` — PASS

## Visual evidence

Intentionally omitted. Issue #47 changes backend scoring, PostgreSQL
persistence, tests, and CLI orchestration only; it has no UI or visual
acceptance criteria.
