# Issue #46 QA evidence — v2

- Issue: #46 — Canonicalize duplicate claims behind a cheap prefilter
- PR: #55
- Branch: `issue-46-canonicalize-duplicate-claims-behind-a-cheap-prefilter`
- Builder rebuild commit tested: `8a3787d6a3b7220515aa4ba49532e0906b7a88da`
- Result: PASS

## Issue-scoped test plan and results

| AC | Observable test | Result |
|---|---|---|
| AC1 | `test_canonicalize_preserves_original_claims_and_repoints_all_evidence` starts with overlapping evidence on both duplicate claims, then verifies the canonical claim retains exactly two evidence rows with one row per contributing paper. | PASS |
| AC2 | The same database test verifies both original claim rows and their text remain, while only the duplicate row receives `canonical_claim_id`. | PASS |
| AC3 | `test_prefilter_requires_type_metric_and_overlapping_normalized_quantity` excludes type, metric, range, and unit near-misses; `test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call` records one batched identity-model invocation and inspects its payload. | PASS |
| AC4 | The prefilter test includes the same metric at a non-overlapping value and verifies that pair is absent, preventing a merge. | PASS |
| AC5 | The task's exact pytest target collects and passes all five issue-scoped tests, covering the duplicate, near-miss, unit mismatch, call count, persistence, CLI default/opt-out, and rerun behavior. | PASS |

## Reviewer rebuild regressions

| Finding | Observable test | Result |
|---|---|---|
| Duplicate cross-paper evidence after repointing | `test_canonicalize_preserves_original_claims_and_repoints_all_evidence` creates four overlapping evidence rows and verifies only two unique paper rows remain on the canonical claim. | PASS |
| Unchanged rerun repeats stance and identity work | `test_extract_rerun_does_no_identity_or_stance_work` invokes `extract` twice and verifies the second run makes zero model calls, zero evidence writes, zero identity writes, and no database changes. | PASS |

## Verification output

### Task acceptance command

Command: `uv run pytest tests/test_claim_identity.py -vv`

```text
collected 5 items
tests/test_claim_identity.py::test_prefilter_requires_type_metric_and_overlapping_normalized_quantity PASSED
tests/test_claim_identity.py::test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call PASSED
tests/test_claim_identity.py::test_canonicalize_preserves_original_claims_and_repoints_all_evidence PASSED
tests/test_claim_identity.py::test_extract_cli_canonicalizes_by_default_and_allows_opt_out PASSED
tests/test_claim_identity.py::test_extract_rerun_does_no_identity_or_stance_work PASSED
============================== 5 passed in 2.00s ===============================
```

### Full repository verification

Command:

```text
uv run pytest && uv run ruff check . && uv run ruff format --check .
```

Output:

```text
collected 191 items
tests/test_claim_identity.py .....                                       [ 21%]
tests/test_evidence_linking.py ......                                    [ 32%]
...
tests/test_tree_schema.py ..                                             [100%]
============================= 191 passed in 13.74s =============================
All checks passed!
98 files already formatted
```

## Visual evidence

Intentionally omitted: issue #46 changes backend canonicalization, PostgreSQL persistence,
and CLI orchestration only. It has no UI or visual acceptance criteria, so executable test
evidence is the applicable proof.
