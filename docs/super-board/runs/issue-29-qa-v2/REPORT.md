# Issue #29 QA report — v2

- PR: #37
- Branch: `issue-29-implement-budgeted-llm-tree-traversal`
- Builder commit tested: `e9973ab5a0b2d4c0e5366aaef3a4615a2c50298b`
- Result: PASS
- Scope: non-visual Python retrieval behavior; screenshots intentionally omitted.

## Acceptance evidence

| AC | Observable test | Result |
|---|---|---|
| AC1 — ranked nodes plus full expansion trace | `test_traverse_returns_ranked_nodes_and_full_expansion_trace` | PASS |
| AC2 — exactly one trace with an allowed stop reason | `test_traverse_returns_ranked_nodes_and_full_expansion_trace`, `test_traversal_never_expands_more_than_three_nodes`, and `test_no_shortlisted_candidates_writes_one_trace_without_expansion_call` cover all allowed reasons and single-write behavior | PASS |
| AC3 — default/config/call budgets and hard cap | `test_node_budget_defaults_and_overrides` plus `test_traversal_never_expands_more_than_three_nodes` | PASS |
| AC4 — empty shortlist avoids the expansion LLM | `test_no_shortlisted_candidates_writes_one_trace_without_expansion_call` | PASS |
| AC5 — task test command exits zero with mocked LLM | `uv run pytest tests/test_traversal.py` | PASS, 9 passed |

The machine-readable target-suite result is in `pytest-traversal.xml`.

## Rebuild regression

The reviewer found that a depleted traversal frontier was previously recorded as
`budget_exhausted` even when the numeric budget had capacity remaining.
`test_depleted_frontier_with_remaining_budget_is_not_budget_exhausted` now exercises a
model response with `expand=false` and `sufficient_evidence=false` under `max_nodes=10`.
It opens one root, records `no_candidates`, and persists the same honest stop reason.

## Verification commands

```text
uv run pytest tests/test_traversal.py
9 passed in 0.87s

uv run pytest tests/test_traversal.py --junitxml=docs/super-board/runs/issue-29-qa-v2/pytest-traversal.xml
9 passed in 0.08s

uv run pytest
122 passed in 9.78s

uv run ruff check .
All checks passed!

uv run ruff format --check .
70 files already formatted
```

## Invariant review

- Retrieval remains vectorless; traversal ranks only model judgements.
- The traversal model call goes through `ai_researcher.llm.gateway.complete`.
- Returned evidence nodes retain node ID, paper ID, section path, and page range.
- The expansion budget remains global across shortlisted papers and is consumed before
  each model batch.
- The rebuild changes no schema, store, provider SDK, or model-call boundary.

## Findings

No QA findings.
