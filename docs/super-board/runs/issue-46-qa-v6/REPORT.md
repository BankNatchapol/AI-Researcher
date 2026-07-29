# Issue #46 QA evidence — v6

- Issue: #46 — Canonicalize duplicate claims behind a cheap prefilter
- PR: #55
- Branch: `issue-46-canonicalize-duplicate-claims-behind-a-cheap-prefilter`
- Builder commit tested: `5cacc5e58941b8ed147687fdeeb9dfc12512bd10`
- Result: **FAIL**
- Root-cause hash: `6dfa9451cbb6`

## Issue-scoped test plan and results

| AC | Observable test | Result |
|---|---|---|
| AC1 | `test_canonicalize_preserves_original_claims_and_repoints_all_evidence` creates duplicate claims from two papers and verifies one canonical claim owns exactly two paper-specific evidence rows. | PASS |
| AC2 | The persistence test verifies original rows remain, while `test_merging_existing_canonical_roots_repoints_descendants_to_final_root` verifies direct links after staged merges. The new prompt-bump regression found that an old member can retain a stale direct link after its root changes proposition. | **FAIL** |
| AC3 | `test_prefilter_requires_type_metric_and_overlapping_normalized_quantity` and `test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call` verify the type/metric/unit/range gate and one batched model call containing only eligible pairs. | PASS |
| AC4 | Static and transitive non-overlap tests pass. `test_reextraction_detaches_old_canonical_member_when_root_value_diverges` proves a preserved 1% member remains canonicalized under a root after that root changes to 2%, violating the requirement that non-overlapping values stay distinct. | **FAIL** |
| AC5 | The exact task command, `uv run pytest tests/test_claim_identity.py`, collected and passed all 11 issue tests. | PASS |

## Latest-fix verification

The direct fix's narrower regression passes:

```text
$ uv run pytest tests/test_extraction_pipeline.py::test_reextraction_invalidates_identity_marker_when_value_changes_into_overlap -vv
tests/test_extraction_pipeline.py::test_reextraction_invalidates_identity_marker_when_value_changes_into_overlap PASSED
============================== 1 passed in 0.58s ===============================
```

This proves `_reconcile_claims()` clears `identity_checked_at` when the updated
root becomes eligible for a new comparison. It does not invalidate the root's
existing canonical group.

## Failing regression

Reproduction:

1. Extract a 1% root, a 1% cross-paper member, and a distinct 2% root.
2. Canonicalize the 1% pair; the member points at the 1% root.
3. Bump the prompt version and re-extract the canonical root as 2%.
4. The updated root is correctly compared with and merged into the other 2% root.
5. Inspect the preserved 1% member's `canonical_claim_id`.

Expected:

- The old 1% member becomes a root again (`canonical_claim_id IS NULL`) because
  it no longer overlaps the updated 2% canonical proposition.
- The updated 2% root and the pre-existing 2% root may canonicalize together.

Actual:

- The old 1% member still points at the updated 2% root.
- `PostgresClaimIdentityStore.load_claims()` excludes the member because its
  `canonical_claim_id` is non-null, so it cannot be reconsidered.

Failure location: `tests/test_extraction_pipeline.py:966`

```text
$ uv run pytest tests/test_extraction_pipeline.py::test_reextraction_detaches_old_canonical_member_when_root_value_diverges -vv
FAILED
>       assert final_rows[old_member_id].canonical_claim_id is None
E       assert 1 is None
E        +  where 1 = (3, 1.0, 1).canonical_claim_id
============================== 1 failed in 1.50s ===============================
```

What fixed should look like:

- Reconciliation of identity-driving fields invalidates the entire affected
  canonical group, not only the updated root's completion marker.
- Preserved members become eligible roots again before the next prefilter/model
  pass.
- Re-canonicalization keeps non-overlapping former members distinct and
  reconciles any consolidated evidence without deleting original claim rows.

## Verification output

### Task acceptance command

Command: `uv run pytest tests/test_claim_identity.py`

```text
collected 11 items
tests/test_claim_identity.py ...........                                 [100%]
============================== 11 passed in 0.93s ==============================
```

### Full repository verification

Command: `uv run pytest`

```text
collected 199 items
tests/test_extraction_pipeline.py ..........F                            [ 40%]
...
FAILED tests/test_extraction_pipeline.py::test_reextraction_detaches_old_canonical_member_when_root_value_diverges
======================== 1 failed, 198 passed in 13.92s ========================
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

- Six historical `[builder]` threads are resolved.
- The newest `[builder]` thread remains unresolved; Tester ownership rules do
  not permit QA to resolve Builder threads.
- No unresolved `[QA]` threads exist.

## Visual evidence

Intentionally omitted: issue #46 changes backend canonicalization, PostgreSQL
persistence, and CLI orchestration only. It has no UI or visual acceptance
criteria, so executable test output is the applicable evidence.
