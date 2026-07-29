# Issue #47 — QA v3 report

- Issue: #47 — Compute the pipeline confidence score
- Pull request: #56
- Branch: `issue-47-compute-the-pipeline-confidence-score`
- Builder rebuild: `43e6341`
- Result: PASS
- Scope: Tester verification after Reviewer rebuild 2

## Acceptance results

### AC1 — bounded, explainable score

PASS. `test_score_returns_bounded_value_and_names_every_contributing_factor`
observes a `ConfidenceScore` bounded to 0–100, verifies that its value is the
sum of the factor contributions, and verifies every contribution is bounded by
its documented maximum.

### AC2 — all five pipeline factors contribute

PASS. The focused suite varies each factor in isolation:

- independent supporting-node count
- order-sensitive verbatim overlap
- repeated-extraction self-consistency
- retrieval stopping reason
- schema-validation cleanliness

The rebuild regressions additionally verify that canonical duplicates are not
treated as repeated extraction runs, persisted validation outcomes reach the
production loader, and extraction persists accepted/rejected validation counts.

### AC3 — budget exhaustion is penalized

PASS. `test_budget_exhausted_scores_lower_than_identical_sufficient_evidence_claim`
compares otherwise-identical claims and observes a strictly lower score for
`budget_exhausted`.

### AC4 — confidence is stored separately

PASS. `test_postgres_store_targets_claim_score_confidence_without_quality_scoring`
observes the insert into `claim_score.confidence`. Evidence quality remains a
separate pending field and is neither calculated nor blended by this task.

### AC5 — exact task command

PASS. `uv run pytest tests/test_confidence.py` exited 0 with 16 passing tests.

## Reviewer rebuild regressions

The four production-path tests below passed together:

1. Canonical duplicates do not become repeated extraction runs.
2. The PostgreSQL loader uses persisted validation outcomes.
3. Extraction persists accepted/rejected validation counts.
4. Scoring is deferred after evidence-link failure and runs after a successful retry.

## Repository verification

- `uv run pytest tests/test_confidence.py` — PASS, 16 tests
- Reviewer-regression selection — PASS, 4 tests
- `uv run pytest` — PASS, 215 tests
- `uv run ruff check .` — PASS
- `uv run ruff format --check .` — PASS, 101 files

## Visual evidence

Intentionally omitted. Issue #47 changes backend scoring, persistence, and CLI
orchestration only; it has no UI or visual acceptance criteria.
