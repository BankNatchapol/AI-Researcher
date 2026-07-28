# Issue #45 QA report — v1

- Issue: #45 — Link claims to supporting and refuting evidence with quoted rationale
- PR: #54
- Branch: `issue-45-link-claim-evidence`
- Builder commit tested: `1fb02f34e84324f1fb46c8a8c34cc49460125717`
- Test type: non-visual Python unit/integration-boundary verification
- Visual evidence: intentionally omitted because the issue changes backend evidence-linking
  and CLI behavior only; it has no UI or visual acceptance criteria.

## Acceptance-criterion test plan

| AC | Observable verification | Result |
|---|---|---|
| AC1 | `test_link_evidence_assigns_all_stances_and_keeps_cross_paper_nodes` asserts traversal receives the normalized claim and returned candidates receive `supports`, `refutes`, and `mentions`. | Pass |
| AC2 | The same two-paper fixture asserts refuting links from paper 202 are retained for a claim originating in paper 101. | Pass |
| AC3 | The stance fixture asserts persisted rationales are source substrings; `test_verbatim_span_preserves_exact_source_whitespace` additionally proves whitespace-normalized matching returns the exact source span. | Pass |
| AC4 | `test_link_evidence_rejects_non_verbatim_rationale_before_persistence` asserts a paraphrase is absent from both returned and saved links. | Pass |
| AC5 | `test_link_evidence_batches_every_candidate_in_one_stance_call` sends eight candidates and asserts exactly one `job="stance"` gateway call. | Pass |
| AC6 | The task-prescribed focused pytest command runs with the gateway mocked. | Pass |

## Red/green evidence for the QA regression

The new exact-source-whitespace regression was first run against `origin/main`
(`4d4e0c7`) and failed as expected because the evidence-linking package did not yet exist:

```text
FAILED tests/test_evidence_linking.py::test_verbatim_span_preserves_exact_source_whitespace
ModuleNotFoundError: No module named 'ai_researcher.evidence'
1 failed
```

The same regression then passed on PR #54:

```text
tests/test_evidence_linking.py::test_verbatim_span_preserves_exact_source_whitespace PASSED
1 passed, 4 deselected
```

## Verification

### Task acceptance command

```text
$ uv run pytest tests/test_evidence_linking.py
collected 5 items
tests/test_evidence_linking.py ..... [100%]
5 passed in 0.13s
```

### Full repository suite

```text
$ uv run pytest
collected 185 items
185 passed in 13.40s
```

### Lint and formatting

```text
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
96 files already formatted
```

## QA conclusion

All six issue acceptance criteria have observable passing coverage. No product-code
defect, unresolved QA review thread, or invariant violation was found.
