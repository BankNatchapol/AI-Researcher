# Issue #46 QA evidence — v3

- Issue: #46 — Canonicalize duplicate claims behind a cheap prefilter
- PR: #55
- Branch: `issue-46-canonicalize-duplicate-claims-behind-a-cheap-prefilter`
- Builder rebuild commit tested: `97061c1cc0773f545d7ced2cf55038132d0f6f3e`
- Result: PASS

## Issue-scoped test plan and results

| AC | Observable test | Result |
|---|---|---|
| AC1 | `test_canonicalize_preserves_original_claims_and_repoints_all_evidence` creates duplicate claims from two papers with overlapping source evidence, then verifies one canonical claim owns exactly two evidence rows naming both contributing papers. | PASS |
| AC2 | The persistence test verifies both original claim rows and texts remain. `test_merging_existing_canonical_roots_repoints_descendants_to_final_root` additionally verifies every preserved non-root points directly to the final canonical row after a two-stage merge. | PASS |
| AC3 | `test_prefilter_requires_type_metric_and_overlapping_normalized_quantity` excludes type, metric, unit, and numeric-range near-misses. `test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call` records exactly one batched identity-model invocation and verifies its payload contains only the eligible pair. | PASS |
| AC4 | The prefilter test keeps a same-metric non-overlapping value out of the comparison set. `test_canonicalize_does_not_bridge_non_prefiltered_numeric_endpoints` verifies overlapping adjacent pairs cannot transitively merge non-overlapping endpoints. | PASS |
| AC5 | The task's exact command, `uv run pytest tests/test_claim_identity.py`, collects and passes all seven issue tests covering a true duplicate, near-miss, unit mismatch, prefilter call count, persistence, CLI default/opt-out, and unchanged rerun. | PASS |

## Reviewer rebuild-2 regressions

| Finding | Observable test | Result |
|---|---|---|
| Transitive bridge merge | `test_canonicalize_does_not_bridge_non_prefiltered_numeric_endpoints` presents values `0.94`, `1.00`, and `1.06`. The LLM sees only adjacent prefiltered pairs, and the non-overlapping endpoints remain outside the same canonical group. | PASS |
| Indirect canonical chain | `test_merging_existing_canonical_roots_repoints_descendants_to_final_root` performs two staged canonical merges and verifies both descendants point directly to the final root. | PASS |

## Verification output

### Task acceptance command

Command: `uv run pytest tests/test_claim_identity.py`

```text
collected 7 items
tests/test_claim_identity.py .......                                     [100%]
============================== 7 passed in 1.80s ===============================
```

Named issue tests were also run with `-vv`:

```text
test_prefilter_requires_type_metric_and_overlapping_normalized_quantity PASSED
test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call PASSED
test_canonicalize_does_not_bridge_non_prefiltered_numeric_endpoints PASSED
test_canonicalize_preserves_original_claims_and_repoints_all_evidence PASSED
test_merging_existing_canonical_roots_repoints_descendants_to_final_root PASSED
test_extract_cli_canonicalizes_by_default_and_allows_opt_out PASSED
test_extract_rerun_does_no_identity_or_stance_work PASSED
============================== 7 passed in 0.53s ===============================
```

### Full repository verification

Command:

```text
uv run pytest && uv run ruff check . && uv run ruff format --check .
```

Output:

```text
collected 193 items
tests/test_claim_identity.py .......                                     [ 22%]
...
tests/test_tree_schema.py ..                                             [100%]
============================= 193 passed in 13.10s =============================
All checks passed!
98 files already formatted
```

## Visual evidence

Intentionally omitted: issue #46 changes backend canonicalization, PostgreSQL persistence,
and CLI orchestration only. It has no UI or visual acceptance criteria, so executable test
evidence is the applicable proof.
