# QA Report — issue #65 · v1

**Issue:** #65 — Add topic and claim subscriptions  
**PR:** #77  
**Branch:** `issue-65-add-topic-and-claim-subscriptions`  
**Commit under test:** `9a29483`  
**Task file:** `docs/superpowers/projects/ai-researcher-app/phase-4/06-subscriptions-cli.md`  
**Result:** PASS  
**When:** 2026-07-30

## Acceptance criteria

| AC | Criterion | Command / check | Result |
|----|-----------|-----------------|--------|
| AC1 | `uv run airesearch subscribe topic <scope>` creates an active topic subscription | `test_subscribe_topic_creates_active_subscription` + CLI invoke in `test_cli_subscribe_topic_subscriptions_and_unsubscribe` | ✅ |
| AC2 | `uv run airesearch subscribe claim <claim-id>` creates active claim sub; unknown ID → named error | `test_subscribe_claim_*` + `test_cli_subscribe_claim_rejects_unknown_id` (`UnknownClaimError`) | ✅ |
| AC3 | `uv run airesearch subscriptions` lists kind, target, and active state | `test_list_subscriptions_includes_kind_target_and_active` + CLI list | ✅ |
| AC4 | `uv run airesearch unsubscribe <id>` sets `active=false` and leaves the row | `test_unsubscribe_deactivates_without_deleting` asserts row still exists | ✅ |
| AC5 | `uv run pytest tests/test_subscriptions.py` exits 0 (both kinds, duplicates, unknown targets, deactivate-not-delete) | 11 passed | ✅ |

## Commands run (exit 0)

```bash
uv run pytest tests/test_subscriptions.py -v   # 11 passed
uv run pytest                                  # 324 passed
uv run ruff check .                            # All checks passed
uv run ruff format --check .                   # 131 files already formatted
```

## Evidence files

- `ac-focused-pytest.log`
- `ac-mapping.md`
- `full-pytest.log`
- `ruff-check.log`
- `ruff-format.log`

## Visual evidence

Omitted intentionally — CLI/library task (no UI ACs).

## Notes for Reviewer

- Claim subscriptions resolve to `canonical_claim_id` when present (survives Phase 3 dedup merges).
- Duplicate active subscriptions are rejected via `DuplicateSubscriptionError`.
- Unsubscribe is deactivate-not-delete; row retained with `active=false`.
- Exactly-one-target rule enforced at application layer (`SubscriptionTargetError`).
