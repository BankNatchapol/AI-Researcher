# Issue #46 QA evidence — v1

- Issue: #46 — Canonicalize duplicate claims behind a cheap prefilter
- PR: #55
- Branch: `issue-46-canonicalize-duplicate-claims-behind-a-cheap-prefilter`
- Builder commit tested: `f23a5b638fca22d11fec8ceca69f3b09914a5d48`
- Result: PASS

## Issue-scoped test plan and results

| AC | Observable test | Result |
|---|---|---|
| AC1 | `test_canonicalize_preserves_original_claims_and_repoints_all_evidence` persists two source-paper evidence rows that both reference the single canonical claim. | PASS |
| AC2 | The same database test verifies both original claim rows and their original text remain, while the duplicate row points to the canonical row. | PASS |
| AC3 | `test_prefilter_requires_type_metric_and_overlapping_normalized_quantity` excludes type, metric, range, and unit near-misses; `test_canonicalize_batches_only_prefiltered_pairs_into_one_model_call` records exactly one model invocation and inspects its payload. | PASS |
| AC4 | The prefilter test includes the same metric at a non-overlapping value and verifies that pair is absent, so it cannot be merged. | PASS |
| AC5 | The task's exact pytest command collects and passes the duplicate, near-miss, unit-mismatch, call-count, persistence, and CLI cases. | PASS |

## Verification output

### Task acceptance command

Command: `uv run pytest tests/test_claim_identity.py`

```text
collected 4 items
tests/test_claim_identity.py ....                                        [100%]
============================== 4 passed in 0.23s ===============================
```

### Full repository tests

Command: `uv run pytest`

```text
collected 190 items
tests/test_claim_identity.py ....                                        [ 21%]
tests/test_evidence_linking.py ......                                    [ 32%]
...
tests/test_tree_schema.py ..                                             [100%]
============================= 190 passed in 13.49s =============================
```

### Lint and format

Commands:

```text
uv run ruff check .
uv run ruff format --check .
```

Output:

```text
All checks passed!
98 files already formatted
```

### Patch hygiene

Command: `git diff --check origin/main...HEAD`

Result: exit 0 with no output.

## Visual evidence

Not captured: issue #46 changes backend canonicalization, PostgreSQL persistence, and CLI
orchestration only. It has no UI or visual acceptance criteria. The executable test evidence
above is the applicable proof.
