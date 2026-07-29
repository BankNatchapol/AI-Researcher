# Issue #46 QA evidence — v7

- Issue: #46 — Canonicalize duplicate claims behind a cheap prefilter
- PR: #55
- Branch: `issue-46-canonicalize-duplicate-claims-behind-a-cheap-prefilter`
- Builder commit tested: `1434070b9037207e40b625b545d5b1b0d3feb11c`
- Result: **PASS**

## Issue-scoped test plan and results

| AC | Observable test | Result |
|---|---|---|
| AC1 | `test_canonicalize_preserves_original_claims_and_repoints_all_evidence` creates duplicate claims from two papers and verifies one canonical claim owns exactly two paper-specific evidence rows. The prompt-bump regression additionally verifies invalidation restores each consolidated row to the correct source-paper original. | PASS |
| AC2 | The persistence test verifies original rows remain, and `test_merging_existing_canonical_roots_repoints_descendants_to_final_root` verifies direct final-root links. `test_reextraction_detaches_old_canonical_member_when_root_value_diverges` now proves a changed root detaches its incompatible preserved member instead of leaving a stale canonical link. | PASS |
| AC3 | `test_prefilter_requires_type_metric_and_overlapping_normalized_quantity` and `test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call` verify the type/metric/unit/range gate and one batched model call containing only eligible pairs. The prompt-bump regressions verify invalidated roots still return through this gate. | PASS |
| AC4 | Static and transitive non-overlap tests keep incompatible quantities distinct. The prompt-bump regression proves the preserved 1% member remains distinct when its former canonical root changes to 2%. | PASS |
| AC5 | The exact task command, `uv run pytest tests/test_claim_identity.py`, collected and passed all 11 issue tests. | PASS |

## QA v6 regression verification

The v6 regression models a complete merge, prompt-version re-extraction, group
invalidation, and re-canonicalization lifecycle:

1. A 1% root and a cross-paper 1% original canonicalize together.
2. Their evidence is consolidated on the root.
3. A prompt bump changes the root to 2%.
4. Group invalidation exposes every preserved original and restores evidence by source paper.
5. The cheap prefilter compares the changed 2% root only with the compatible 2% claim.
6. The old 1% original stays distinct with `canonical_claim_id IS NULL`.

Focused command:

```text
$ uv run pytest tests/test_claim_identity.py \
    tests/test_extraction_pipeline.py::test_reextraction_invalidates_identity_marker_when_value_changes_into_overlap \
    tests/test_extraction_pipeline.py::test_reextraction_detaches_old_canonical_member_when_root_value_diverges -vv
collected 13 items
tests/test_claim_identity.py::test_prefilter_requires_type_metric_and_overlapping_normalized_quantity PASSED
tests/test_claim_identity.py::test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call PASSED
tests/test_claim_identity.py::test_canonicalize_does_not_bridge_non_prefiltered_numeric_endpoints PASSED
tests/test_claim_identity.py::test_canonicalize_preserves_original_claims_and_repoints_all_evidence PASSED
tests/test_claim_identity.py::test_negative_identity_decision_is_not_repeated_on_unchanged_rerun PASSED
tests/test_claim_identity.py::test_unchecked_claim_compares_with_checked_roots_without_rechecking_old_pair PASSED
tests/test_claim_identity.py::test_merging_existing_canonical_roots_repoints_descendants_to_final_root PASSED
tests/test_claim_identity.py::test_extract_cli_canonicalizes_by_default_and_allows_opt_out PASSED
tests/test_claim_identity.py::test_extract_cli_processes_dedup_backlog_after_opt_out[default] PASSED
tests/test_claim_identity.py::test_extract_cli_processes_dedup_backlog_after_opt_out[explicit] PASSED
tests/test_claim_identity.py::test_extract_rerun_does_no_identity_or_stance_work PASSED
tests/test_extraction_pipeline.py::test_reextraction_invalidates_identity_marker_when_value_changes_into_overlap PASSED
tests/test_extraction_pipeline.py::test_reextraction_detaches_old_canonical_member_when_root_value_diverges PASSED
============================== 13 passed in 2.50s ==============================
```

## Regression red-green proof

The same canonical-root divergence test failed on the previous QA commit
`b2f89c109b2a85616b2a8e5931e38a8e18d675dd`:

```text
FAILED tests/test_extraction_pipeline.py::test_reextraction_detaches_old_canonical_member_when_root_value_diverges
>       assert final_rows[old_member_id].canonical_claim_id is None
E       assert 1 is None
======================== 1 failed, 198 passed in 13.92s ========================
```

On builder commit `1434070b9037207e40b625b545d5b1b0d3feb11c`, the focused
regression passes and verifies the restored evidence mapping:

```text
parsed/root paper -> updated canonical root
abstract/member paper -> detached preserved original
```

## Verification output

### Task acceptance command

Command: `uv run pytest tests/test_claim_identity.py`

```text
collected 11 items
tests/test_claim_identity.py ...........                                 [100%]
============================== 11 passed in 0.76s ==============================
```

### Full repository verification

Command: `uv run pytest`

```text
collected 199 items
tests/test_claim_identity.py ...........                                 [ 23%]
tests/test_extraction_pipeline.py ...........                            [ 40%]
tests/test_tree_schema.py ..                                             [100%]
============================= 199 passed in 13.73s =============================
```

Command: `uv run ruff check .`

```text
All checks passed!
```

Command: `uv run ruff format --check .`

```text
98 files already formatted
```

## Review threads

All seven historical `[builder]` threads are resolved. No unresolved `[QA]`
threads exist on PR #55.

## Visual evidence

Intentionally omitted: issue #46 changes backend canonicalization, PostgreSQL
persistence, and CLI orchestration only. It has no UI or visual acceptance
criteria, so executable test output is the applicable evidence.
