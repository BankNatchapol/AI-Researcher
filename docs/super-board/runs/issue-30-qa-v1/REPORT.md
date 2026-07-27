# Issue #30 QA evidence — v1

- PR: #38
- Branch: `issue-30-synthesize-answers-with-node-citations`
- Builder commit tested: `9355297638506cc1b3169198f41e74d8449f6563`
- Result: PASS
- Visual evidence: intentionally omitted because all acceptance criteria concern
  Python library behavior and have no UI or visual surface.

## Acceptance test plan and result

| AC | Observable check | Test evidence | Result |
|---|---|---|---|
| 1 | Every returned factual statement has at least one supplied node ID; a partly unattributed response is rejected twice and fails closed. | `test_synthesis_attributes_every_statement_to_supplied_nodes`; `test_any_unattributed_statement_returns_insufficient_evidence` | PASS |
| 2 | A citation exposes and renders paper title, section path, real page range, and DOI/arXiv identifier. | `test_citation_renders_paper_section_pages_and_identifier` | PASS |
| 3 | Zero or one supporting node bypasses synthesis and returns an explicit insufficient-evidence result with no answer text. | `test_fewer_than_two_nodes_returns_insufficient_evidence_without_synthesis` | PASS |
| 4 | `stopped_reason="budget_exhausted"` sets `Answer.budget_limited` while preserving a grounded answer when at least two nodes support it. | `test_budget_exhaustion_sets_budget_limited_on_synthesized_answer` | PASS |
| 5 | The exact issue-scoped pytest command exits zero and covers full synthesis, insufficient evidence, and budget-limited behavior. | `uv run pytest tests/test_synthesis.py` | PASS — 7 tests |

## Attribution mutation check

To prove the AC1 regression is sensitive to the missing-attribution defect, the
`or not node_ids` validation guard was temporarily removed and only
`test_any_unattributed_statement_returns_insufficient_evidence` was run.

Expected red result:

```text
FAILED tests/test_synthesis.py::test_any_unattributed_statement_returns_insufficient_evidence
E assert 1 == 2
1 failed
```

The guard was restored immediately. `git diff` confirms there is no production-code
change from the mutation check, and the restored test passes.

## Fresh verification

```text
$ uv run pytest tests/test_synthesis.py
collected 7 items
tests/test_synthesis.py ....... [100%]
7 passed in 0.07s

$ uv run pytest
collected 130 items
130 passed in 9.08s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
74 files already formatted
```
