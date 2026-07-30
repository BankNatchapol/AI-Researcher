# Issue #48 QA Report — v5

**PR:** #57
**Builder head tested:** `5fd122fb951ef37d8845f65b5c28c4731e4a0bc2`
**Result:** FAIL
**Date:** 2026-07-30

## Scope

This QA pass verifies rebuild 3, especially the arithmetic-callable alias regression from
QA v4. All acceptance criteria are non-visual Python/library behavior, and the project
explicitly has no web UI in v1, so screenshot evidence is intentionally omitted.

Before adding the v5 mutation, the untouched Builder head passed both task commands:

```text
$ uv run pytest tests/test_score_separation.py
15 passed in 0.10s

$ uv run pytest tests/test_quality.py
12 passed in 0.93s
```

The v4 assignment and import-alias reproducers are green. The new v5 reproducer covers the
same arithmetic callable passed under a function-parameter alias.

## Acceptance criteria

### AC1 — Rubric-driven bounded score

**Observable test:** `test_score_returns_bounded_value_and_every_documented_factor`

The score remains bounded to 0–100, exposes exactly the five documented v1 factors, and
equals the rounded sum of their independently reported contributions.

**Result:** PASS

### AC2 — Content-derived rubric version on every score row

**Observable tests:**

- `test_rubric_version_changes_when_any_rubric_file_content_changes`
- `test_persisted_claim_score_rows_carry_the_exact_rubric_version`
- `test_confidence_persistence_requires_computed_quality_and_current_rubric_version`
- `test_score_scope_persists_independently_computed_quality_with_confidence`
- `test_postgres_loader_supplies_real_metadata_and_evidence_to_quality_scoring`

Rubric edits change the content-derived version. The production scoring path computes
evidence quality independently and persists the current rubric version without a placeholder
write path.

**Result:** PASS

### AC3 — Abstract-only penalty

**Observable test:**
`test_abstract_only_claim_scores_lower_than_otherwise_identical_full_text_claim`

The abstract-only and parsed claims differ only in `parse_status`; the parsed claim scores
strictly higher, and only the `full_text` contribution changes.

**Result:** PASS

### AC4 — Mechanical score/discourse separation

**Observable tests:**

- `test_no_module_performs_arithmetic_combining_the_two_scores`
- `test_score_arithmetic_gate_detects_aliased_score_fields`
- `test_score_arithmetic_gate_detects_arithmetic_callables`
- `test_score_arithmetic_gate_detects_aliased_arithmetic_callables`
- `test_scoring_package_does_not_import_discourse`
- `test_discourse_gate_detects_from_package_import`

Rebuild 3 detects callable aliases created through local assignments and import aliases.
The same forbidden operation still bypasses the build gate when the callable is supplied as
a defaulted function parameter:

```python
import operator

def blend(row, combine=operator.add):
    return combine(row.confidence, row.evidence_quality)
```

The mutation fails because the gate does not connect the `combine` parameter with its
`operator.add` default and therefore does not raise the expected
`score arithmetic combines` assertion.

**Reproducer:** `tests/test_score_separation.py:350`
**Failure assertion:** `tests/test_score_separation.py:367`

**Result:** FAIL

### AC5 — Each rubric factor isolated

**Observable tests:**

- `test_abstract_only_claim_scores_lower_than_otherwise_identical_full_text_claim`
- `test_peer_reviewed_claim_scores_higher_than_otherwise_identical_preprint`
- `test_direct_evidence_scores_higher_than_otherwise_identical_inference`
- `test_recent_claim_scores_higher_than_otherwise_identical_old_claim`
- `test_independent_replication_changes_only_replication_factor`
- `test_replication_counts_distinct_supporting_papers_only`

Each real v1 rubric input is varied independently, and replication counts distinct
supporting paper IDs rather than passages.

**Result:** PASS

## Fresh verification

```text
$ uv run pytest tests/test_score_separation.py
1 failed, 15 passed in 0.11s

$ uv run pytest tests/test_quality.py
12 passed in 0.13s

$ uv run pytest
1 failed, 249 passed in 16.08s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
104 files already formatted
```

## Review-thread check

- Unresolved `[QA]` threads: 0
- Unresolved review threads of any prefix: 0

## What fixed should look like

The AST gate should map function parameters to arithmetic callable defaults when building
the function scope's callable-alias set. The v5 mutation must raise the gate's assertion,
while the repository scan and all prior direct, assignment-alias, and import-alias mutations
remain green.

## Conclusion

AC4 remains open. The QA reproducer is committed for rebuild, while AC1, AC2, AC3, and AC5
continue to pass. Issue #48 is not ready for Review.

`root-cause-hash: 6b8bed27d8e0`
