# Issue #30 QA evidence — v3

- PR: #38
- Branch: `issue-30-synthesize-answers-with-node-citations`
- Builder rebuild commit tested: `b2277c87c127d5dd834c1eb03027efb237373480`
- Prior Reviewer finding: page-less nodes could support synthesis and missing paper
  identifiers could escape as `CitationResolutionError`
- Result: PASS
- Visual evidence: intentionally omitted because every acceptance criterion concerns
  Python library behavior and there is no UI or visual surface.

## Acceptance test plan and result

| AC | Observable check | Test evidence | Result |
|---|---|---|---|
| 1 | Every rendered factual statement has at least one supplied node ID; unattributed, unknown-node, and multiline records fail validation. | `test_synthesis_attributes_every_statement_to_supplied_nodes`; `test_newline_containing_statement_is_rejected_and_regenerated`; `test_any_unattributed_statement_returns_insufficient_evidence` | PASS |
| 2 | Citations render paper title, section path, real page range, and DOI/arXiv metadata; page-less evidence and missing identifiers fail closed. | `test_citation_renders_paper_section_pages_and_identifier`; `test_nodes_without_real_page_ranges_return_insufficient_evidence`; `test_missing_paper_identifier_returns_insufficient_evidence`; `test_tei_page_range_uses_every_coordinate_group_in_a_paragraph` | PASS |
| 3 | Fewer than two supporting nodes bypasses model synthesis and returns explicit insufficient evidence with no answer text. | `test_fewer_than_two_nodes_returns_insufficient_evidence_without_synthesis` | PASS |
| 4 | `stopped_reason="budget_exhausted"` sets `Answer.budget_limited` while preserving a grounded answer when enough support exists. | `test_budget_exhaustion_sets_budget_limited_on_synthesized_answer` | PASS |
| 5 | The exact task command exits zero and covers synthesis, insufficient evidence, and budget limiting. | `uv run pytest tests/test_synthesis.py` | PASS — 10 tests |

## Reviewer-finding regression checks

The page-range filter was temporarily removed from
`src/ai_researcher/answer/synthesize.py`, recreating the first reported defect:

```text
$ uv run pytest tests/test_synthesis.py::test_nodes_without_real_page_ranges_return_insufficient_evidence
FAILED tests/test_synthesis.py::test_nodes_without_real_page_ranges_return_insufficient_evidence
E Failed: nodes without real page ranges must not support synthesis
1 failed
```

The filter was restored immediately and the same focused test passed:

```text
$ uv run pytest tests/test_synthesis.py::test_nodes_without_real_page_ranges_return_insufficient_evidence
1 passed in 0.09s
```

The `CitationResolutionError` handler was then temporarily disabled, recreating the
second reported defect:

```text
$ uv run pytest tests/test_synthesis.py::test_missing_paper_identifier_returns_insufficient_evidence
FAILED tests/test_synthesis.py::test_missing_paper_identifier_returns_insufficient_evidence
E ai_researcher.answer.citation.CitationResolutionError:
E Paper has neither a DOI nor an arXiv ID
1 failed
```

The handler was restored immediately and the same focused test passed:

```text
$ uv run pytest tests/test_synthesis.py::test_missing_paper_identifier_returns_insufficient_evidence
1 passed in 0.06s
```

`git diff -- src/ai_researcher/answer/synthesize.py` was empty after both checks,
confirming that QA left no production-code mutation behind.

## Fresh verification

```text
$ uv run pytest tests/test_synthesis.py
collected 10 items
tests/test_synthesis.py .......... [100%]
10 passed in 0.07s

$ uv run pytest
collected 133 items
133 passed in 9.47s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
74 files already formatted
```
