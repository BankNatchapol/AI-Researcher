# Issue #46 QA evidence — v5

- Issue: #46 — Canonicalize duplicate claims behind a cheap prefilter
- PR: #55
- Branch: `issue-46-canonicalize-duplicate-claims-behind-a-cheap-prefilter`
- Builder rebuild commit tested: `8e61c7eb0b1ade256a89a088210d7e03659ac43b`
- Result: PASS

## Issue-scoped test plan and results

| AC | Observable test | Result |
|---|---|---|
| AC1 | `test_canonicalize_preserves_original_claims_and_repoints_all_evidence` creates duplicate claims from two papers with overlapping source evidence, then verifies one canonical claim owns exactly two evidence rows naming both contributing papers. | PASS |
| AC2 | The persistence test verifies both original claim rows and texts remain. `test_merging_existing_canonical_roots_repoints_descendants_to_final_root` additionally verifies every preserved non-root points directly to the final canonical row after staged merges. | PASS |
| AC3 | `test_prefilter_requires_type_metric_and_overlapping_normalized_quantity` excludes type, metric, unit, and numeric-range near-misses. `test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call` records exactly one batched identity-model invocation and verifies its payload contains only the eligible pair. | PASS |
| AC4 | The prefilter test keeps a same-metric non-overlapping value out of the comparison set. `test_canonicalize_does_not_bridge_non_prefiltered_numeric_endpoints` verifies overlapping adjacent pairs cannot transitively merge non-overlapping endpoints. | PASS |
| AC5 | The task's exact command, `uv run pytest tests/test_claim_identity.py`, collected and passed all 11 items, including true duplicate, near-miss, unit mismatch, prefilter call count, persistence, CLI, deferred-backlog, and unchanged-rerun coverage. | PASS |

## Reviewer rebuild-4 regression

| Finding | Observable test | Result |
|---|---|---|
| Persist negative decisions | `test_negative_identity_decision_is_not_repeated_on_unchanged_rerun` returns `same_claim=false`, verifies both roots receive `identity_checked_at`, then proves the unchanged second run performs zero comparisons, zero model calls, and zero `INSERT`/`UPDATE`/`DELETE` statements. | PASS |
| Pending-only comparisons | `test_unchecked_claim_compares_with_checked_roots_without_rechecking_old_pair` verifies a new unchecked claim is compared with both compatible checked roots, the checked–checked pair is omitted, and only the new claim is marked checked. | PASS |
| Deferred dedup remains eligible | `test_extract_cli_processes_dedup_backlog_after_opt_out` verifies both default and explicit dedup process claims created by an earlier `--no-dedup` run. | PASS |
| Truly unchanged rerun | `test_extract_rerun_does_no_identity_or_stance_work` verifies an already-processed rerun makes zero identity/stance model calls, performs zero related writes, and leaves the database unchanged. | PASS |

## Regression red-green proof

The new negative-decision regression was executed against the pre-fix QA v4 commit
`d25624d8da0b4d5bf5214b2cf821c1e265f5682f`, using that commit's production source:

```text
test_negative_identity_decision_is_not_repeated_on_unchanged_rerun FAILED
E       assert 1 == 0
E        +  where 1 = CanonicalizationResult(
E             pairs_compared=1,
E             canonical_claims=0,
E             merged_claims=0,
E          ).pairs_compared
============================== 1 failed in 0.40s ===============================
```

The same focused regression on rebuild commit
`8e61c7eb0b1ade256a89a088210d7e03659ac43b` passed:

```text
test_negative_identity_decision_is_not_repeated_on_unchanged_rerun PASSED
============================== 1 passed in 0.25s ===============================
```

## Verification output

### Task acceptance command

Command: `uv run pytest tests/test_claim_identity.py`

```text
collected 11 items
tests/test_claim_identity.py ...........                                 [100%]
============================== 11 passed in 0.66s ==============================
```

### Full repository verification

Command: `uv run pytest`

```text
collected 197 items
tests/test_claim_identity.py ...........                                 [ 23%]
...
tests/test_tree_schema.py ..                                             [100%]
============================= 197 passed in 13.71s =============================
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

All six `[builder]` threads are resolved. No unresolved `[QA]` threads exist on PR #55.

## Visual evidence

Intentionally omitted: issue #46 changes backend canonicalization, PostgreSQL persistence,
and CLI orchestration only. It has no UI or visual acceptance criteria, so executable test
evidence is the applicable proof.
