# Issue #48 QA Report — v4

**PR:** #57
**Builder head tested:** `2540a405a796b1a6da8b5a2af141fed4c3140f68`
**Result:** FAIL
**Date:** 2026-07-30

## Scope

This QA pass verifies rebuild 2, especially the direct arithmetic-callable regression raised
by Review. All acceptance criteria are non-visual Python/library behavior, and the project
explicitly has no web UI in v1, so screenshot evidence is intentionally omitted.

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
evidence quality independently and persists the current rubric version without the removed
placeholder path.

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

Rebuild 2 detects direct forms such as
`operator.add(row.confidence, row.evidence_quality)`, but the same forbidden operation
bypasses the build gate when the callable is assigned or imported under a local alias:

```python
combine = operator.add
return combine(row.confidence, row.evidence_quality)
```

```python
from operator import add as combine
return combine(row.confidence, row.evidence_quality)
```

Both mutation cases fail because the gate does not raise the expected
`score arithmetic combines` assertion.

**Reproducer:** `tests/test_score_separation.py:301`
**Failure assertion:** `tests/test_score_separation.py:313`

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
2 failed, 13 passed in 0.11s

$ uv run pytest tests/test_quality.py
12 passed in 0.95s

$ uv run pytest
2 failed, 247 passed in 16.79s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
104 files already formatted
```

## Review-thread check

- Unresolved `[QA]` threads: 0
- Unresolved review threads of any prefix: 0

## What fixed should look like

The AST gate should resolve arithmetic callable aliases created by imports and local
assignments, then classify calls through those aliases as arithmetic. Both v4 mutation cases
must raise the gate's assertion while the repository scan remains green.

## Conclusion

AC4 remains open. The QA reproducer is committed for rebuild, while AC1, AC2, AC3, and AC5
continue to pass. Issue #48 is not ready for Review.

`root-cause-hash: aa0a3851fff3`
