# QA Report — issue #69 v1

Date: 2026-07-30T14:21:14Z
Branch: issue-69-render-temporal-digests
Commit under test: fde295f
PR: https://github.com/BankNatchapol/AI-Researcher/pull/81

## Scope

Non-visual ACs (library/CLI/unit tests only). No UI — screenshots intentionally omitted.

## Acceptance Criteria plan

| AC | Observable test | Result |
|----|-----------------|--------|
| AC1 `airesearch digest --since` writes file + stdout | `test_cli_digest_writes_file_and_stdout` + `cli-digest-help.log` | PASS |
| AC2 exactly two top-level sections Evidence / Community attention | `test_render_has_exactly_two_top_level_sections` | PASS |
| AC3 no attention figures in Evidence section | `test_evidence_section_contains_no_attention_figures` | PASS |
| AC4 score movement as separate confidence / evidence_quality before→after | `test_score_movement_renders_separate_before_after_pairs` | PASS |
| AC5 community items link to posts; pytest covers populated + empty + separation | `test_community_items_link_to_original_post_not_body`, `test_empty_window_produces_legible_nothing_changed_digest`, full `tests/test_digest.py` (7 passed) | PASS |

## Invariant spot-check (AGENTS.md)

- Dual scores: render emits `confidence: A → B` and `evidence_quality: C → D` separately; tests forbid blended deltas.
- Channel separation: community counts/links only under `## Community attention`; Evidence asserts no upvote/comment/attention scores or discourse URLs.
- Attention disclaimer present: "Attention is not evidence of validity".
- Digest consumes `ChangeSet` / discourse mention IDs for enrichment only; scoring path untouched.

## Commands

See pytest-ac.log, pytest-full.log, ruff.log, ruff-format.log, cli-digest-help.log.
