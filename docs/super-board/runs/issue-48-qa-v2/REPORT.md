# Issue #48 — QA v2

**PR:** #57  
**Builder head tested:** `f89b7b6`  
**Verdict:** FAIL — AC2 and AC4 remain unmet

## Scope

This QA pass tested the revised five-factor task contract on the issue branch. The
table/figure factor is intentionally absent because figure/table grounding is out of scope
for v1. The rebuild's durable `claim_evidence.is_direct` input was tested through the real
`ClaimEvidence` dataclass.

All acceptance criteria are non-visual Python/library checks, and the project has no web UI.
Screenshots are therefore intentionally omitted; command output and executable regression
tests are the appropriate evidence.

## Acceptance-criterion plan and results

| AC | Observable check | Result |
|---|---|---|
| AC1 | Score a claim through all five documented factors; also pass the persisted `ClaimEvidence` shape into `score_quality` and observe the directness contribution. | PASS |
| AC2 | Change rubric content and observe a changed version; inspect both quality and confidence persistence writes and require every inserted row to carry the content-derived version. | **FAIL** |
| AC3 | Compare otherwise-identical parsed and abstract-only claims and require the parsed claim to score higher only on `full_text`. | PASS |
| AC4 | Run the separation suite, inject aliased `confidence`/`evidence_quality` arithmetic, and require the AST gate to reject it; retain the discourse-import mutation check. | **FAIL** |
| AC5 | Isolate full-text, peer-review, directness, recency, and replication contributions in `tests/test_quality.py`. | PASS |

## Failure 1 — production persistence writes a pending rubric version

Reproducer: `tests/test_quality.py::test_confidence_persistence_cannot_create_a_pending_rubric_version`

Expected:

```text
rubric_version = 2+sha256:f0fcd032a86a
```

Actual:

```text
rubric_version = pending-evidence-quality
```

`PostgresConfidenceStore.save_confidence` remains a production `claim_score` writer and
inserts `evidence_quality=0` plus the pending version. The new `PostgresQualityStore` has no
production caller, so AC2's “every claim_score row” guarantee is not true.

What fixed should look like:

- The real scope scoring/persistence flow computes both independent scores without combining
  them.
- No `claim_score` writer can persist a pending rubric version.
- An integration test covers every production `claim_score` write.

## Failure 2 — aliased score arithmetic bypasses the build gate

Reproducer: `tests/test_score_separation.py::test_score_arithmetic_gate_detects_aliased_score_fields`

The injected violation is:

```python
pipeline = row.confidence
science = row.evidence_quality
return (pipeline + science) / 2
```

Expected: `test_no_module_performs_arithmetic_combining_the_two_scores` raises an assertion.

Actual: the gate reports no violation because it only inspects field names syntactically
inside the arithmetic expression and does not follow local assignments.

What fixed should look like:

- Track local aliases derived from either score field within a function, or use an
  equivalently conservative data-flow check.
- Keep the new mutation test green so trivial renaming cannot bypass the hard invariant.

## Commands and output

Before the new mutation/regression tests were added, the task commands were false-green:

```text
uv run pytest tests/test_score_separation.py
3 passed

uv run pytest tests/test_quality.py
10 passed
```

After adding the QA tests:

```text
uv run pytest tests/test_score_separation.py
1 failed, 3 passed

uv run pytest tests/test_quality.py
1 failed, 11 passed

uv run pytest
2 failed, 234 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
104 files already formatted
```

The added persisted-evidence-shape check was also run directly:

```text
uv run pytest tests/test_quality.py -k persisted_claim_evidence_shape
1 passed, 11 deselected
```

## Review-thread state

There are no unresolved `[QA]` threads. The PR still has two unresolved `[builder]` threads
covering the two failures above and one unresolved `[review]` contract thread. QA did not
resolve threads owned by other lanes.

`root-cause-hash: 3d1ec6ec148e`
