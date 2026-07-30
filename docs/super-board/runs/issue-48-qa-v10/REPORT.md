# Issue #48 QA Report — v10

**PR:** #57  
**Builder head tested:** `b83a59d19f0fb099e90811c15e96b9cf3efa602c`  
**Result:** PASS  
**Date:** 2026-07-30

## Scope

This QA pass verifies rebuild 8 after QA v9's mapping-style access finding. The Builder
closed `row.get(...)` / `getattr(...)` string-literal score access in the AST lint and
reframed AC4 so the AST walker is best-effort defense-in-depth; the complete separation
guarantee is the pre-existing behavioral proof on `score_scope_confidence`.

All acceptance criteria are non-visual Python/library checks, and v1 has no web UI, so
screenshot evidence is intentionally omitted.

## Acceptance criteria

### AC1 — Rubric-driven bounded score

**Observable test:** `test_score_returns_bounded_value_and_every_documented_factor`

`score_quality` returns a 0–100 value, exposes exactly the five factors documented in
`scoring/rubric.md`, and equals the rounded sum of their independently reported
contributions.

**Result:** PASS

### AC2 — Content-derived rubric version on every score row

**Observable tests:**

- `test_rubric_version_changes_when_any_rubric_file_content_changes`
- `test_persisted_claim_score_rows_carry_the_exact_rubric_version`
- `test_confidence_persistence_requires_computed_quality_and_current_rubric_version`
- `test_score_scope_persists_independently_computed_quality_with_confidence`

Changing rubric content changes the SHA-256-derived version. Production persistence writes
the computed quality and current rubric version; no `pending-evidence-quality` placeholder
remains on the live path.

**Result:** PASS

### AC3 — Abstract-only penalty

**Observable test:**
`test_abstract_only_claim_scores_lower_than_otherwise_identical_full_text_claim`

Claims that differ only in `parse_status` show a strictly lower score for abstract-only,
with only the `full_text` factor contribution changing.

**Result:** PASS

### AC4 — Score / discourse separation (AST lint + behavioral guarantee)

**Observable tests:**

- `test_no_module_performs_arithmetic_combining_the_two_scores` (repo scan)
- `test_score_arithmetic_gate_detects_mapping_get_access` (v9 regression)
- `test_score_arithmetic_gate_detects_getattr_access` (rebuild 8 addition)
- prior alias / callable / closure / dunder / AugAssign regressions
- `test_scoring_package_does_not_import_discourse`
- `test_score_scope_persists_independently_computed_quality_with_confidence`
- `test_postgres_store_persists_both_scores_without_combining_them`

The mapping/`getattr` regressions from v9 now fail the gate as expected. The task file and
test docstring now state the AST lint is best-effort (not exhaustive); the complete
guarantee is the behavioral path on `score_scope_confidence`. No further adversarial syntax
probe was filed as a blocker — that loop is what rebuild 8 closed.

**Result:** PASS

### AC5 — Each rubric factor isolated

**Observable tests:**

- `test_abstract_only_claim_scores_lower_than_otherwise_identical_full_text_claim`
- `test_peer_reviewed_claim_scores_higher_than_otherwise_identical_preprint`
- `test_direct_evidence_scores_higher_than_otherwise_identical_inference`
- `test_recent_claim_scores_higher_than_otherwise_identical_old_claim`
- `test_independent_replication_changes_only_replication_factor`
- `test_replication_counts_distinct_supporting_papers_only`

Each real v1 rubric input is varied independently. Table/figure presentation remains out of
scope for v1 per the corrected task contract.

**Result:** PASS

## Fresh verification

```text
$ uv run pytest tests/test_score_separation.py tests/test_quality.py tests/test_confidence.py
57 passed in 2.17s

$ uv run pytest
257 passed in 15.33s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
104 files already formatted
```

## Review-thread check

- Unresolved `[QA]` threads: 0
- Unresolved `[builder]` threads: 0 (all four historical threads resolved)

## Conclusion

All five task acceptance criteria pass at `b83a59d`. Rebuild 8 closed the v9 mapping-access
gap and correctly reframed AC4 so future AST-edge discoveries are not automatic Ready
bounces. Ready for Review.
