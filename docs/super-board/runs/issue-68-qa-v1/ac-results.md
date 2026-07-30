# Per-AC results — issue #68 QA v1

| AC | Criterion | Command / test | Expected | Actual | Pass |
|----|-----------|----------------|----------|--------|------|
| AC1 | `detect_changes(since) -> ChangeSet` reports new papers, new claim_evidence, stance flips, score movement, discourse mentions | five category tests in `tests/test_change_detection.py` | Each category populated when seeded after baseline | all PASSED | ✅ |
| AC2 | First `refutes` evidence is a stance flip | `test_first_refutes_evidence_is_reported_as_stance_flip` | one StanceFlipChange for first refute; second refute alone is not a flip | PASSED | ✅ |
| AC3 | Score movement = separate confidence and evidence_quality deltas | `test_score_movement_reports_separate_deltas_beyond_threshold` | deltas 20 / 15; no blended attrs | PASSED | ✅ |
| AC4 | Threshold defaults to 10, configurable | `test_score_movement_threshold_defaults_to_ten_and_is_configurable` | default 10; threshold=5 reports delta 6 | PASSED | ✅ |
| AC5 | Focused pytest exits 0 covering each category + quiet empty ChangeSet | `uv run pytest tests/test_change_detection.py` | exit 0 | 9 passed in 2.83s | ✅ |

**Visual evidence:** N/A — non-visual ACs (library/API only). Screenshots intentionally omitted.

**Regression:** full `uv run pytest` + `uv run ruff check .` + `uv run ruff format --check .` — see logs.
