# Issue #45 QA report — v2

- Issue: #45 — Link claims to supporting and refuting evidence with quoted rationale
- PR: #54
- Branch: `issue-45-link-claim-evidence`
- Builder rebuild commit tested: `7b3c0b410917ae1b9f9e0e739078652090e027ed`
- Test type: non-visual Python unit/integration-boundary verification
- Visual evidence: intentionally omitted because the issue changes backend evidence-linking
  and CLI behavior only; it has no UI or visual acceptance criteria.

## Rebuild finding verification

Reviewer v1 found that an incomplete stance batch could silently omit a traversal candidate
while persisting the remaining evidence. Builder rebuild v1 added claim-scope completeness
validation.

`test_link_evidence_rejects_incomplete_batch_without_persistence` exercises two traversal
candidates from different papers, makes the mocked stance gateway omit the cross-paper
refutation, and observes both required outcomes:

1. `EvidenceLinkingError` is raised because every candidate was not classified exactly once.
2. The evidence store receives zero persistence calls and remains empty.

The focused run passed this regression at Builder commit `7b3c0b4`.

## Acceptance-criterion test plan

| AC | Observable verification | Result |
|---|---|---|
| AC1 | `test_link_evidence_assigns_all_stances_and_keeps_cross_paper_nodes` asserts traversal receives the normalized claim and returned candidates receive `supports`, `refutes`, and `mentions`. | Pass |
| AC2 | The same two-paper fixture asserts a refuting node from paper 202 is retained for a claim originating in paper 101. | Pass |
| AC3 | The stance fixture asserts each persisted rationale is a source substring; `test_verbatim_span_preserves_exact_source_whitespace` proves whitespace-normalized matching returns the exact source span. | Pass |
| AC4 | `test_link_evidence_rejects_non_verbatim_rationale_before_persistence` asserts a paraphrased rationale is absent from both returned and saved links. | Pass |
| AC5 | `test_link_evidence_batches_every_candidate_in_one_stance_call` sends eight candidates and asserts exactly one `job="stance"` gateway call. | Pass |
| AC6 | The task-prescribed focused pytest command runs with the gateway mocked, covering support, refutation, mention, cross-paper evidence, rejected rationale, and incomplete batches. | Pass |

## Verification

### Task acceptance command

```text
$ uv run pytest tests/test_evidence_linking.py
collected 6 items
tests/test_evidence_linking.py ...... [100%]
6 passed in 0.09s
```

### Full repository suite

```text
$ uv run pytest
collected 186 items
186 passed in 13.22s
```

### Lint and formatting

```text
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
96 files already formatted
```

## QA conclusion

All six issue acceptance criteria have observable passing coverage. The incomplete-batch
regression now proves claim-scope failure with no partial persistence. No product defect,
unresolved `[QA]` review thread, or hard-invariant violation was found.
