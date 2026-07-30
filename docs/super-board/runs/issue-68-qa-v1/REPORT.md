# QA Report — issue #68 v1

Date: 2026-07-30T11:45:41Z
Branch: issue-68-change-detection
Commit under test: 6885b52
PR: https://github.com/BankNatchapol/AI-Researcher/pull/80

## Scope

Non-visual ACs (library/unit tests only). No UI — screenshots intentionally omitted.

## Acceptance Criteria plan

| AC | Observable test | Result |
|----|-----------------|--------|
| AC1 detect_changes reports all 5 categories | `test_detects_new_papers_*`, `test_detects_new_claim_evidence_*`, `test_first_refutes_*`, `test_score_movement_reports_*`, `test_detects_new_discourse_*` | PASS |
| AC2 first `refutes` is stance flip | `test_first_refutes_evidence_is_reported_as_stance_flip` (+ `test_second_refutes_is_not_a_stance_flip`) | PASS |
| AC3 separate confidence / evidence_quality deltas, never blended | `test_score_movement_reports_separate_deltas_beyond_threshold` | PASS |
| AC4 threshold defaults to 10 and is configurable | `test_score_movement_threshold_defaults_to_ten_and_is_configurable` | PASS |
| AC5 `uv run pytest tests/test_change_detection.py` exits 0 (quiet + each category) | full file (9 tests) including `test_quiet_period_produces_empty_changeset` | PASS |

## Invariant spot-check (AGENTS.md)

- Dual scores: `ScoreMovementChange` exposes `confidence_*` and `evidence_quality_*` fields separately; tests assert no `score_delta` / `combined_delta` / `blended_delta`.
- Channel separation: discourse mentions live in `ChangeSet.discourse_mentions` only; `detect_changes` does not feed discourse into score movement.
- No LLM / embedding / vector usage in `monitor/changes.py`.

## Commands

See `pytest-ac.log`, `pytest-full.log`, `ruff.log`.
