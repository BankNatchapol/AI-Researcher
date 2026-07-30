# QA Report — issue #68 v2

Date: 2026-07-30T12:01:59Z
Branch: issue-68-change-detection
Commit under test: ad4f780 (ad4f780)
PR: https://github.com/BankNatchapol/AI-Researcher/pull/80
Prior: v1 passed on 6885b52; Reviewer bounced ([builder] score movement ignored `since`); Builder rebuild 1 at ad4f780.

## Scope

Non-visual ACs (library/unit tests only). No UI — screenshots intentionally omitted.

## Rebuild focus

Verify Reviewer finding is fixed: quiet windows must not re-report pre-baseline score deltas.
- Code: `_score_movements` takes `since` and skips when newer `scored_at <= since`
- Test: `test_pre_baseline_score_delta_is_not_re_reported`

## Acceptance Criteria plan

| AC | Observable test | Result |
|----|-----------------|--------|
| AC1 detect_changes reports all 5 categories | category tests in pytest-ac.log | PASS |
| AC2 first `refutes` is stance flip | `test_first_refutes_evidence_is_reported_as_stance_flip` | PASS |
| AC3 separate confidence / evidence_quality deltas | `test_score_movement_reports_separate_deltas_beyond_threshold` | PASS |
| AC4 threshold defaults to 10 and is configurable | `test_score_movement_threshold_defaults_to_ten_and_is_configurable` | PASS |
| AC5 focused pytest exits 0 (quiet + each category + pre-baseline regression) | 10 passed including quiet + `test_pre_baseline_score_delta_is_not_re_reported` | PASS |

## Invariant spot-check (AGENTS.md)

- Dual scores: `ScoreMovementChange` exposes separate confidence_* and evidence_quality_* fields; tests assert no score_delta / combined_delta / blended_delta.
- Channel separation: discourse mentions only in `ChangeSet.discourse_mentions`; no discourse import in `monitor/changes.py`.
- `since` gate on score movements restores quiet-empty semantics after rebuild.

## Commands

See pytest-ac.log, pytest-full.log, ruff.log, ruff-format.log.
