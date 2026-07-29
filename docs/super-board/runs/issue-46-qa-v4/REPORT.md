# Issue #46 QA evidence — v4

- Issue: #46 — Canonicalize duplicate claims behind a cheap prefilter
- PR: #55
- Branch: `issue-46-canonicalize-duplicate-claims-behind-a-cheap-prefilter`
- Builder rebuild commit tested: `e8aa7163e3675ca50bda8583d18277b56add255d`
- Result: PASS

## Issue-scoped test plan and results

| AC | Observable test | Result |
|---|---|---|
| AC1 | `test_canonicalize_preserves_original_claims_and_repoints_all_evidence` creates duplicate claims from two papers with overlapping source evidence, then verifies one canonical claim owns exactly two evidence rows naming both contributing papers. | PASS |
| AC2 | The persistence test verifies both original claim rows and texts remain. `test_merging_existing_canonical_roots_repoints_descendants_to_final_root` additionally verifies every preserved non-root points directly to the final canonical row after staged merges. | PASS |
| AC3 | `test_prefilter_requires_type_metric_and_overlapping_normalized_quantity` excludes type, metric, unit, and numeric-range near-misses. `test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call` records exactly one batched identity-model invocation and verifies its payload contains only the eligible pair. | PASS |
| AC4 | The prefilter test keeps a same-metric non-overlapping value out of the comparison set. `test_canonicalize_does_not_bridge_non_prefiltered_numeric_endpoints` verifies overlapping adjacent pairs cannot transitively merge non-overlapping endpoints. | PASS |
| AC5 | The task's exact command, `uv run pytest tests/test_claim_identity.py`, collected and passed all nine items, including true duplicate, near-miss, unit mismatch, prefilter call count, persistence, CLI, backlog, and unchanged-rerun coverage. | PASS |

## Reviewer rebuild-3 regression

| Finding | Observable test | Result |
|---|---|---|
| Deferred dedup backlog | `test_extract_cli_processes_dedup_backlog_after_opt_out` runs `extract --no-dedup` and then both default and explicit dedup variants. It verifies the later run invokes canonicalization and reports non-zero identity work. | PASS |
| Unchanged processed rerun | `test_extract_rerun_does_no_identity_or_stance_work` verifies an already-canonicalized rerun makes zero identity/stance model calls, performs zero related writes, and leaves the database unchanged. | PASS |

## Regression red-green proof

The new parametrized backlog regression was applied to the pre-fix commit
`216899ca9e88619bc8c8b9082540f4116bef9b56`. Both variants failed at the expected
assertion because the guarded CLI path never called canonicalization:

```text
tests/test_claim_identity.py::test_extract_cli_processes_dedup_backlog_after_opt_out[default] FAILED
tests/test_claim_identity.py::test_extract_cli_processes_dedup_backlog_after_opt_out[explicit] FAILED
E       AssertionError: assert [] == ['surface-codes']
============================== 2 failed in 1.37s ===============================
```

The same focused command on rebuild commit `e8aa7163e3675ca50bda8583d18277b56add255d`
passed both variants:

```text
tests/test_claim_identity.py::test_extract_cli_processes_dedup_backlog_after_opt_out[default] PASSED
tests/test_claim_identity.py::test_extract_cli_processes_dedup_backlog_after_opt_out[explicit] PASSED
============================== 2 passed in 1.28s ===============================
```

## Verification output

### Task acceptance command

Command: `uv run pytest tests/test_claim_identity.py`

```text
collected 9 items
tests/test_claim_identity.py .........                                   [100%]
============================== 9 passed in 0.61s ===============================
```

### Full repository verification

Command:

```text
uv run pytest && uv run ruff check . && uv run ruff format --check .
```

Output:

```text
collected 195 items
tests/test_claim_identity.py .........                                   [ 23%]
...
tests/test_tree_schema.py ..                                             [100%]
============================= 195 passed in 14.26s =============================
All checks passed!
98 files already formatted
```

## Review threads

All five `[builder]` threads are resolved. No unresolved `[QA]` threads exist on PR #55.

## Visual evidence

Intentionally omitted: issue #46 changes backend canonicalization, PostgreSQL persistence,
and CLI orchestration only. It has no UI or visual acceptance criteria, so executable test
evidence is the applicable proof.
