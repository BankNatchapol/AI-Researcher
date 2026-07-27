# Issue #27 QA report — v1

- PR: #35
- Branch: `issue-27-build-per-paper-node-trees-with-llm-summaries-and-versioned-caching`
- Builder commit tested: `b64073a134e22c6e318689f1867235c42958e8d8`
- Result: PASS
- Scope: CLI, pure tree construction, and PostgreSQL persistence
- Visual evidence: intentionally omitted because issue #27 has no UI or visual acceptance
  criteria

## Acceptance-criterion evidence

| AC | Observable check | Result |
|---|---|---|
| AC1 | `test_index_cli_builds_and_then_skips_current_per_paper_trees` observed `built 2 / skipped 0` followed by `built 0 / skipped 2`. QA added `test_index_rebuilds_only_the_paper_with_a_stale_tree_version`, which made one tree stale and observed `built 1 / skipped 1 / failed 0` with one additional per-paper gateway call. | PASS |
| AC2 | `test_build_tree_batches_one_gateway_call_and_preserves_section_anchors` checked every generated node's section ID, section path, page range, and parent section. `test_index_cli_builds_and_then_skips_current_per_paper_trees` joined persisted nodes back to sections and checked paper ownership, path inheritance, and page ranges. | PASS |
| AC3 | `test_build_tree_batches_one_gateway_call_and_preserves_section_anchors` observed exactly one `node_summary` gateway call for a three-node paper and checked every summary was at most 60 words. The integration test observed exactly two calls for two papers, not one call per node. | PASS |
| AC4 | `test_six_level_tree_is_flattened_at_depth_four_without_losing_original_path` loaded the committed six-level fixture, checked depths `[0, 1, 2, 3, 4, 4]`, checked flattened parentage, and checked the level-six source path remained in `node_path`. | PASS |
| AC5 | The exact task command `uv run pytest tests/test_tree_builder.py` completed with 6 passed and 0 failed. All LLM behavior was mocked. | PASS |

## Fresh verification

Run from the QA worktree after adding the QA regression test:

```text
uv run pytest tests/test_tree_builder.py
6 passed in 0.61s

uv run pytest
104 passed in 7.67s

uv run ruff check .
All checks passed!

uv run ruff format --check .
62 files already formatted
```

`uv run airesearch index --help` also exited 0 and showed the required `SCOPE` argument.
