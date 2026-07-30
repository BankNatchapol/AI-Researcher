# AC ↔ test mapping — issue #69

| AC | Task criterion | Primary test(s) |
|----|----------------|-----------------|
| AC1 | CLI writes `docs/supersaiyan/runs/digest-<date>.md` and stdout matches | `test_cli_digest_writes_file_and_stdout` |
| AC2 | Exactly two top-level sections: Evidence, Community attention | `test_render_has_exactly_two_top_level_sections` |
| AC3 | No attention figures inside Evidence | `test_evidence_section_contains_no_attention_figures` |
| AC4 | Score movement as separate confidence / evidence_quality pairs | `test_score_movement_renders_separate_before_after_pairs` |
| AC5 | Community items link out; populated + empty + separation covered | `test_community_items_link_to_original_post_not_body`, `test_empty_window_produces_legible_nothing_changed_digest`, `test_build_digest_from_injected_changeset` |

Command: `uv run pytest tests/test_digest.py`
