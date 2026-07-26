# Issue #11 QA report — v1

- PR: #25
- Branch: `issue-11-add-the-corpus-status-command-and-structured-logging`
- Builder commit tested: `fc915ac`
- Date: 2026-07-26
- Result: PASS

## Acceptance-criterion results

| AC | Observable check | Result |
|---|---|---|
| 1 | `airesearch status` prints per-scope paper/parsed/abstract_only/failed/sections counts | PASS — `test_status_cli_prints_counts_and_scope_filter` (stdout includes `papers: 3`, `parsed: 1`, `abstract_only: 1`, `failed: 1`, `sections: 2`) |
| 2 | `airesearch status --scope <name>` restricts to one scope and lists failed papers with errors | PASS — same test; scoped output excludes `empty-scope`, includes `Failed papers:` / `grobid boom` |
| 3 | Logs to stderr at INFO by default and DEBUG under `--verbose`; stdout clean | PASS — `test_logs_go_to_stderr_not_stdout` + probe (`stderr_handler True`, DEBUG only when verbose) |
| 4 | `airesearch ingest` emits per-paper progress `processed/total` | PASS — `test_ingest_emits_per_paper_progress_lines` captured `1/2` and `2/2` INFO log lines |
| 5 | `uv run pytest tests/test_status.py` exits 0 against seeded mixed corpus | PASS — 5 passed in 0.75s |

## Commands

```text
uv run pytest tests/test_status.py -v
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Full command output is recorded in `command-output.txt`.

## Visual evidence

Intentionally omitted: issue #11 contains only CLI, logging, SQL aggregation, and pytest
acceptance criteria, with no UI or visual behavior.
