# AC → test mapping (issue #65)

| AC | Criterion | Covering tests |
|----|-----------|----------------|
| AC1 | `airesearch subscribe topic <scope>` creates active topic subscription | `test_subscribe_topic_creates_active_subscription`, `test_cli_subscribe_topic_subscriptions_and_unsubscribe` |
| AC2 | `airesearch subscribe claim <claim-id>` creates active claim sub; unknown ID → named error | `test_subscribe_claim_creates_active_subscription`, `test_subscribe_claim_rejects_unknown_id_with_named_error`, `test_cli_subscribe_claim_rejects_unknown_id`, `test_subscribe_claim_targets_canonical_claim` |
| AC3 | `airesearch subscriptions` lists kind, target, active | `test_list_subscriptions_includes_kind_target_and_active`, CLI portion of `test_cli_subscribe_topic_subscriptions_and_unsubscribe` |
| AC4 | `airesearch unsubscribe <id>` sets `active=false`, row remains | `test_unsubscribe_deactivates_without_deleting` (asserts row still exists), CLI unsubscribe in `test_cli_subscribe_topic_subscriptions_and_unsubscribe` |
| AC5 | `uv run pytest tests/test_subscriptions.py` exits 0 covering both kinds, duplicates, unknown targets, deactivate-not-delete | entire file: 11 tests passed |

Also covered: duplicate prevention (`test_duplicate_*`), unknown scope (`test_subscribe_topic_rejects_unknown_scope`).
