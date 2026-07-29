# Issue #47 QA v1 — Confidence scorer

- PR: #56
- Builder commit tested: `d6bcc11064f304c0c52d424b25a6e86aa71183a5`
- Branch: `issue-47-compute-the-pipeline-confidence-score`
- Result: **FAIL**
- Evidence type: automated Python tests and source-level reproduction
- Screenshots: intentionally omitted because every acceptance criterion is non-visual

## Issue-scoped test plan

| Acceptance criterion | Observable test | Result |
|---|---|---|
| `score_confidence()` returns a bounded 0–100 `ConfidenceScore` with contributing factors | `test_score_returns_bounded_value_and_names_every_contributing_factor` | PASS |
| The score combines all five named factors, with each factor independently observable | Five isolation tests plus `test_verbatim_overlap_does_not_treat_shuffled_words_as_verbatim` | **FAIL** |
| `budget_exhausted` scores below otherwise-identical `sufficient_evidence` | `test_budget_exhausted_scores_lower_than_identical_sufficient_evidence_claim` | PASS |
| Persistence targets `claim_score.confidence` while evidence-quality calculation remains pending | `test_postgres_store_targets_claim_score_confidence_without_quality_scoring` | PASS |
| The task's exact pytest command exits 0 | `uv run pytest tests/test_confidence.py` | **FAIL (exit 1)** |

## Failure

### Expected

The `verbatim_overlap` factor must reward claim text that appears in the node body in the
same wording/order. A node body containing the same tokens in reverse order is not a
verbatim overlap and must receive a lower contribution.

### Actual

Both the exact sentence and the reversed-token sentence receive raw overlap `1.0`, the
maximum contribution `25.0`, and total score `83`:

```text
verbatim 83 1.0 25.0
shuffled 83 1.0 25.0
```

The acceptance command fails at `tests/test_confidence.py:129`:

```text
E       assert 25.0 < 25.0
========================= 1 failed, 11 passed in 0.15s =========================
```

The reproducer points to `_token_coverage()` in
`src/ai_researcher/scoring/confidence.py:448`. It compares token `Counter` objects, so it
discards word order and cannot distinguish verbatim text from shuffled text.

## What fixed should look like

- Make the overlap signal order-sensitive so exact/in-order text scores above shuffled
  tokens.
- Keep the existing factor-isolation properties: changing the node body must change only
  `verbatim_overlap`.
- Re-run `uv run pytest tests/test_confidence.py`; all 12 tests must pass.

## Command evidence

```text
$ uv run pytest tests/test_confidence.py
collected 12 items
tests/test_confidence.py ...F........
FAILED tests/test_confidence.py::test_verbatim_overlap_does_not_treat_shuffled_words_as_verbatim
1 failed, 11 passed in 0.15s

$ uv run pytest tests/test_confidence.py -k 'not shuffled_words' -q
11 passed, 1 deselected in 0.12s
```
