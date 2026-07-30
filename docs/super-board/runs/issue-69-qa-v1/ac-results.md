# AC results — issue #69 QA v1

| AC | Result | Evidence |
|----|--------|----------|
| AC1 digest CLI writes `digest-<date>.md` and prints same content | PASS | `test_cli_digest_writes_file_and_stdout`; `cli-digest-help.log` |
| AC2 exactly two top-level sections | PASS | `test_render_has_exactly_two_top_level_sections` |
| AC3 no attention figures in Evidence | PASS | `test_evidence_section_contains_no_attention_figures` |
| AC4 separate confidence / evidence_quality before→after | PASS | `test_score_movement_renders_separate_before_after_pairs` |
| AC5 community links + pytest (populated, empty, separation) | PASS | `test_community_*`, `test_empty_window_*`; 7 passed in pytest-ac.log |

Full suite: 351 passed (`pytest-full.log`). Ruff check + format: clean.
