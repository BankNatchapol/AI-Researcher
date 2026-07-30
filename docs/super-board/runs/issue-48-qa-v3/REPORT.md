# Issue #48 QA Report — v3

**PR:** #57  
**Builder head tested:** `ba48717754b0b11208970aa59ec34fbc55be9b9e`  
**Result:** PASS  
**Date:** 2026-07-30

## Scope

This QA pass verifies the rebuilt production persistence path and alias-aware score
separation gate after the v2 failures. All acceptance criteria are non-visual Python/library
behavior, and the project explicitly has no web UI in v1, so screenshot evidence is
intentionally omitted.

## Acceptance criteria

### AC1 — Rubric-driven bounded score

**Observable test:** `test_score_returns_bounded_value_and_every_documented_factor`

The score is bounded to 0–100, exposes exactly the five factors documented in
`scoring/rubric.md`, and equals the rounded sum of their independently reported
contributions.

**Result:** PASS

### AC2 — Content-derived rubric version on every score row

**Observable tests:**

- `test_rubric_version_changes_when_any_rubric_file_content_changes`
- `test_persisted_claim_score_rows_carry_the_exact_rubric_version`
- `test_confidence_persistence_requires_computed_quality_and_current_rubric_version`
- `test_score_scope_persists_independently_computed_quality_with_confidence`
- `test_postgres_loader_supplies_real_metadata_and_evidence_to_quality_scoring`

Changing any rubric content changes the SHA-256-derived version. The production scope
scoring path now loads real paper/evidence inputs, computes evidence quality independently,
and delegates the only `claim_score` insert to `PostgresQualityStore`; no
`pending-evidence-quality` placeholder remains in production code.

**Result:** PASS

### AC3 — Abstract-only penalty

**Observable test:**
`test_abstract_only_claim_scores_lower_than_otherwise_identical_full_text_claim`

The abstract-only and parsed claims differ only in `parse_status`; the parsed claim scores
strictly higher, and only the `full_text` factor contribution changes.

**Result:** PASS

### AC4 — Mechanical score/discourse separation

**Observable tests:**

- `test_no_module_performs_arithmetic_combining_the_two_scores`
- `test_score_arithmetic_gate_detects_aliased_score_fields`
- `test_scoring_package_does_not_import_discourse`
- `test_discourse_gate_detects_from_package_import`

The AST gate passes over the repository and its regression fixture proves that local aliases
of `confidence` and `evidence_quality` are still detected when arithmetic combines them.
The scoring package has no discourse imports, including package-level `from ... import`
forms.

**Result:** PASS

### AC5 — Each rubric factor isolated

**Observable tests:**

- `test_abstract_only_claim_scores_lower_than_otherwise_identical_full_text_claim`
- `test_peer_reviewed_claim_scores_higher_than_otherwise_identical_preprint`
- `test_direct_evidence_scores_higher_than_otherwise_identical_inference`
- `test_recent_claim_scores_higher_than_otherwise_identical_old_claim`
- `test_independent_replication_changes_only_replication_factor`
- `test_replication_counts_distinct_supporting_papers_only`

Each real v1 rubric input is varied independently, with assertions that only the expected
factor contribution changes. Replication counts distinct supporting paper IDs rather than
passages.

**Result:** PASS

## Fresh verification

```text
$ uv run pytest tests/test_score_separation.py
4 passed in 0.08s

$ uv run pytest tests/test_quality.py
12 passed in 1.25s

$ uv run pytest
238 passed in 15.71s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
104 files already formatted
```

## Review-thread check

- Unresolved `[QA]` threads: 0
- The remaining unresolved `[review]` contract thread is reviewer-owned; its underlying
  schema decision is reflected in the corrected task/phase contract and rebuilt code.

## Conclusion

All five task acceptance criteria pass at the current PR head. The two v2 regressions are
green, repository-wide tests and quality gates pass, and the change is ready for Review.
