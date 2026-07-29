# Issue #47 — QA v4 report

- Issue: #47 — Compute the pipeline confidence score
- Pull request: #56
- Branch: `issue-47-compute-the-pipeline-confidence-score`
- Builder rebuild: `b449a3a`
- Result: PASS
- Scope: Tester verification after Reviewer rebuild 3

## Acceptance results

### AC1 — bounded, explainable score

PASS. `test_score_returns_bounded_value_and_names_every_contributing_factor`
observes a `ConfidenceScore` bounded to 0–100, verifies that its value is the
sum of the factor contributions, and verifies that every contribution is
bounded by its documented maximum.

### AC2 — all five pipeline factors contribute

PASS. The focused suite varies each required factor in isolation:

- independent supporting-node count
- order-sensitive verbatim overlap
- repeated-extraction self-consistency
- retrieval stopping reason
- schema-validation cleanliness

Rebuild 3 adds production-path coverage proving that extraction executions
append passage-anchored observations for the same claim, that prior
observations reach the confidence loader, and that agreement versus
disagreement changes only the `self_consistency` contribution. Observations
for a different canonical sibling remain excluded.

### AC3 — budget exhaustion is penalized

PASS. `test_budget_exhausted_scores_lower_than_identical_sufficient_evidence_claim`
compares otherwise-identical claims and observes a strictly lower score for
`budget_exhausted`.

### AC4 — confidence is stored separately

PASS. `test_postgres_store_targets_claim_score_confidence_without_quality_scoring`
observes the insert into `claim_score.confidence`. The repeated-run
observation table stores only pipeline extraction provenance and passage
anchors; no evidence-quality or discourse input is introduced or blended.

### AC5 — exact task command

PASS. `uv run pytest tests/test_confidence.py` exited 0 with 18 passing tests.

## Rebuild 3 verification

The rebuilt path passed both unit-level and database-backed coverage:

1. Prior observations for the exact claim are loaded as repeated runs.
2. Agreement and disagreement affect only `self_consistency`.
3. Each extraction execution records paper, tree-node, model, and prompt
   provenance.
4. Prompt-version reruns append observations and make stored confidence
   eligible for refresh.
5. Migration `0009_claim_extraction_observations` applies idempotently with
   the expected non-null columns and foreign keys.

## Repository verification

- `uv run pytest tests/test_confidence.py` — PASS, 18 tests
- `uv run pytest tests/test_extraction_pipeline.py tests/test_migrations.py` —
  PASS, 17 tests
- `uv run pytest` — PASS, 217 tests
- `uv run ruff check .` — PASS
- `uv run ruff format --check .` — PASS, 101 files
- `git diff --check` — PASS

## Visual evidence

Intentionally omitted. Issue #47 changes backend scoring, PostgreSQL
persistence, migrations, tests, and CLI orchestration only; it has no UI or
visual acceptance criteria.
