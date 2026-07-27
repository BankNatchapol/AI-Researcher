# Issue #30 QA evidence — v2

- PR: #38
- Branch: `issue-30-synthesize-answers-with-node-citations`
- Builder rebuild commit tested: `f5580d3dabb3270169a56c2097658d5f6a62606f`
- Prior Reviewer finding: newline-containing model text could render a factual line
  without a node attribution
- Result: PASS
- Visual evidence: intentionally omitted because every acceptance criterion concerns
  Python library behavior and there is no UI or visual surface.

## Acceptance test plan and result

| AC | Observable check | Test evidence | Result |
|---|---|---|---|
| 1 | Every returned factual statement has at least one supplied node ID, and a multiline model record is rejected and regenerated before rendering. | `test_synthesis_attributes_every_statement_to_supplied_nodes`; `test_newline_containing_statement_is_rejected_and_regenerated`; `test_any_unattributed_statement_returns_insufficient_evidence` | PASS |
| 2 | A citation exposes and renders paper title, section path, real page range, and DOI/arXiv identifier. | `test_citation_renders_paper_section_pages_and_identifier`; `test_tei_page_range_uses_every_coordinate_group_in_a_paragraph` | PASS |
| 3 | Fewer than two supporting nodes bypasses model synthesis and returns an explicit insufficient-evidence result with no answer text. | `test_fewer_than_two_nodes_returns_insufficient_evidence_without_synthesis` | PASS |
| 4 | `stopped_reason="budget_exhausted"` sets `Answer.budget_limited` while preserving a grounded answer when at least two nodes support it. | `test_budget_exhaustion_sets_budget_limited_on_synthesized_answer` | PASS |
| 5 | The exact issue-scoped pytest command exits zero and covers full synthesis, insufficient evidence, and budget-limited behavior. | `uv run pytest tests/test_synthesis.py` | PASS — 8 tests |

## Reviewer-finding regression check

The newline-validation guard was temporarily removed from
`src/ai_researcher/answer/synthesize.py`, recreating the behavior identified by
the Reviewer. The focused regression was then run:

```text
$ uv run pytest tests/test_synthesis.py::test_newline_containing_statement_is_rejected_and_regenerated
FAILED tests/test_synthesis.py::test_newline_containing_statement_is_rejected_and_regenerated
E assert 1 == 2
1 failed
```

The guard was restored immediately and the same focused test passed:

```text
$ uv run pytest tests/test_synthesis.py::test_newline_containing_statement_is_rejected_and_regenerated
1 passed in 0.09s
```

`git diff -- src/ai_researcher/answer/synthesize.py` was empty after restoration,
confirming that QA left no production-code mutation behind.

## Fresh verification

```text
$ uv run pytest tests/test_synthesis.py
collected 8 items
tests/test_synthesis.py ........ [100%]
8 passed in 1.21s

$ uv run pytest
collected 131 items
131 passed in 9.71s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
74 files already formatted
```
