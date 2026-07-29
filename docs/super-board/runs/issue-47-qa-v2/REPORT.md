# Issue #47 QA v2 — Confidence scorer

- PR: #56
- Builder rebuild commit tested: `a1f40d10e238f2a580ee47d4fb815b15fad8d636`
- Branch: `issue-47-compute-the-pipeline-confidence-score`
- Result: **PASS**
- Evidence type: automated Python tests and source-level verification
- Screenshots: intentionally omitted because this backend/CLI task has no UI or visual acceptance criteria

## Issue-scoped test plan

| Acceptance criterion | Observable test | Result |
|---|---|---|
| `score_confidence()` returns a bounded 0–100 `ConfidenceScore` with contributing factors | `test_score_returns_bounded_value_and_names_every_contributing_factor` | PASS |
| The score combines all five named factors, with each factor independently observable | Five factor-isolation tests plus `test_verbatim_overlap_does_not_treat_shuffled_words_as_verbatim` | PASS |
| `budget_exhausted` scores below otherwise-identical `sufficient_evidence` | `test_budget_exhausted_scores_lower_than_identical_sufficient_evidence_claim` | PASS |
| Persistence targets `claim_score.confidence` while evidence-quality calculation remains pending | `test_postgres_store_targets_claim_score_confidence_without_quality_scoring` | PASS |
| The task's exact pytest command exits 0 | `uv run pytest tests/test_confidence.py` | PASS (12 tests) |

## Rebuild verification

QA v1 showed that an exact claim sentence and its reversed-token form both received the
maximum `verbatim_overlap` contribution. Rebuild commit `a1f40d1` replaces unordered token
intersection with the longest contiguous, in-order token span. The committed regression
test now passes and exact wording scores above shuffled wording.

The scorer still exposes the five pipeline-only factors independently:

1. independent supporting nodes;
2. verbatim claim/node overlap;
3. repeated-extraction self-consistency;
4. retrieval stopping reason; and
5. schema-validation cleanliness.

No peer-review, preprint, recency, replication, community, or discourse input is used.
Persistence writes the computed value to `claim_score.confidence`; the evidence-quality
fields remain explicit task-07 placeholders and are not calculated or blended here.

## Command evidence

```text
$ uv run pytest tests/test_confidence.py
collected 12 items
tests/test_confidence.py ............                                    [100%]
12 passed in 1.11s

$ uv run pytest
collected 211 items
211 passed in 14.48s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
101 files already formatted
```

Full command results are recorded in `verification.txt`.
