# Issue #31 QA v1

- Issue: #31 — Add the ask command with trace and JSON output
- PR: #39
- Branch: `issue-31-add-the-ask-command-with-trace-and-json-output`
- Product commit tested: `005a56ec1d7feb87b9f37f2688374b2b6551850c`
- Result: PASS

## Acceptance-criterion evidence

| AC | Observable test | Result |
|---|---|---|
| Default output includes an answer and numbered citations resolving to paper, section path, and page range | `test_ask_prints_answer_and_numbered_citations` invokes the Typer app and asserts the numbered answer markers plus `Paper 101 — Results/Threshold — pp. 4–5` and `Paper 202 — Discussion/Comparison — pp. 4–5`. | PASS |
| `--verbose` includes expanded nodes and the stopping reason | `test_ask_verbose_prints_expanded_nodes_and_stopping_reason` asserts the trace heading, node ID, section path, expansion reason, and `Stopping reason: sufficient_evidence`. | PASS |
| `--json` emits only machine-readable structured output | `test_ask_json_emits_machine_readable_output_only` parses all stdout as JSON, checks citation node IDs/page ranges and the trace summary, then proves stdout equals exactly one serialized JSON document. | PASS |
| `--max-nodes N` overrides the budget and low-budget output is labelled | `test_ask_max_nodes_override_labels_budget_limited_output` asserts `max_nodes=2` reaches the traversal call and the terminal response contains `BUDGET-LIMITED`. | PASS |
| Default, verbose, JSON, low-budget, and insufficient-evidence shapes are covered and successful | `uv run pytest tests/test_ask_cli.py` collected all five shape tests, including `test_ask_insufficient_evidence_is_an_explicit_successful_result`; all five passed. | PASS |

## Commands run

### Issue-scoped suite

```text
$ uv run pytest tests/test_ask_cli.py
collected 5 items
tests/test_ask_cli.py ..... [100%]
5 passed in 0.09s
```

### Repository verification

```text
$ uv run pytest && uv run ruff check . && uv run ruff format --check .
138 passed in 8.38s
All checks passed!
76 files already formatted
```

## Visual evidence

Screenshots are intentionally omitted. Issue #31 changes a terminal-only CLI surface and
has no UI or visual acceptance criterion; executable CLI tests and their captured results
are the applicable evidence.
