# AC results — issue #68 QA v2

| AC | Result | Evidence |
|----|--------|----------|
| AC1 ChangeSet categories | PASS | category tests in pytest-ac.log |
| AC2 first refutes → stance flip | PASS | test_first_refutes_evidence_is_reported_as_stance_flip |
| AC3 separate confidence / evidence_quality deltas | PASS | test_score_movement_reports_separate_deltas_beyond_threshold |
| AC4 threshold default 10 + configurable | PASS | test_score_movement_threshold_defaults_to_ten_and_is_configurable |
| AC5 focused pytest (quiet + categories + pre-baseline) | PASS | 10 passed |

Rebuild regression: test_pre_baseline_score_delta_is_not_re_reported PASS
