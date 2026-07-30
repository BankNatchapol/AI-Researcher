# AC → test mapping — issue #67

| AC | Observable check | Test |
|----|------------------|------|
| AC1 | `sweep_run.kind == 'discourse'`, CLI `airesearch sweep --kind discourse` | `test_clean_poll_writes_sweep_run_stores_mentions_advances_last_polled`, `test_cli_discourse_sweep_exits_zero_with_failing_source` |
| AC2 | `discourse_item` + `discourse_mention` rows; `discourse_source.last_polled_at` set | `test_clean_poll_writes_sweep_run_stores_mentions_advances_last_polled` |
| AC3 | Second poll → `items_found == 0`, item count stays 1, `since == last_polled` | `test_repeat_poll_adds_zero_duplicate_items` |
| AC4 | Good source stores items; bad source in `error`; bad `last_polled_at` stays null; CLI exit 0 | `test_failing_source_recorded_while_others_complete`, `test_cli_discourse_sweep_exits_zero_with_failing_source` |
| AC5 | Suite covers clean / repeat / fail / skip-creds | all five tests in `tests/test_discourse_sweep.py` |

Command: `uv run pytest tests/test_discourse_sweep.py`
