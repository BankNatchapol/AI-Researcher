# Issue #29 QA report — v1

- PR: #37
- Branch: `issue-29-implement-budgeted-llm-tree-traversal`
- Builder commit tested: `a3a6461275a41f2890b72c0060455cd1c9dbbe5f`
- Result: PASS
- Scope: non-visual Python retrieval behavior; screenshots intentionally omitted.

## Acceptance evidence

| AC | Observable test | Result |
|---|---|---|
| AC1 — ranked nodes plus full expansion trace | `test_traverse_returns_ranked_nodes_and_full_expansion_trace` | PASS |
| AC2 — exactly one trace with an allowed stop reason | `test_traverse_returns_ranked_nodes_and_full_expansion_trace`, `test_traversal_never_expands_more_than_three_nodes`, and `test_no_shortlisted_candidates_writes_one_trace_without_expansion_call` cover all three allowed reasons and single-write behavior | PASS |
| AC3 — default/config/call budgets and hard cap | `test_node_budget_defaults_and_overrides` plus `test_traversal_never_expands_more_than_three_nodes` | PASS |
| AC4 — empty shortlist avoids the expansion LLM | `test_no_shortlisted_candidates_writes_one_trace_without_expansion_call` | PASS |
| AC5 — task test command exits zero with mocked LLM | `uv run pytest tests/test_traversal.py` | PASS, 8 passed |

The machine-readable target-suite result is in `pytest-traversal.xml`.

## Verification commands

```text
uv run pytest tests/test_traversal.py
8 passed in 0.85s

uv run pytest
121 passed in 9.23s

uv run ruff check .
All checks passed!

uv run ruff format --check .
70 files already formatted
```

## Invariant review

- Retrieval remains vectorless; traversal ranks only model judgements.
- The traversal model call goes through `ai_researcher.llm.gateway.complete`.
- Returned evidence nodes retain node ID, paper ID, section path, and page range.
- The expansion budget is global across shortlisted papers and is consumed before each model batch.
- No schema changes, new store, provider SDK, or direct model CLI call were introduced.

## Findings

No QA findings.
