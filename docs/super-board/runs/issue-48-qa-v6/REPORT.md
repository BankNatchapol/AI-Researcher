# Issue #48 QA v6 — FAIL

- Issue: #48 — Compute evidence quality from a written rubric and enforce score separation
- PR: #57
- Branch: `issue-48-compute-evidence-quality-from-a-written-rubric-and-enforce-score-separation`
- Builder head tested: `c2cf721d5cb1c150626ff239fc5c89e0352ee615`
- Date: 2026-07-30
- Result: **FAIL — AC4**

## Acceptance-criterion results

| AC | Result | Observable evidence |
|---|---|---|
| AC1 — rubric-only bounded quality score | PASS | `tests/test_quality.py` verifies the score is 0–100, equals the sum of the five documented factor contributions, and contains no undocumented factor. |
| AC2 — content-derived rubric version on every score row | PASS | Quality and confidence persistence tests store the exact version returned by `load_rubric()` and reject the former placeholder path. |
| AC3 — abstract-only penalty | PASS | The otherwise-identical abstract-only/full-text comparison changes only the `full_text` contribution and lowers the abstract-only score. |
| AC4 — mechanical score/discourse separation gate | **FAIL** | A default arithmetic callable captured by a nested closure bypasses the AST gate. The mutation at `tests/test_score_separation.py:394` does not trigger the expected assertion. |
| AC5 — each approved v1 rubric factor isolated | PASS | The 12-test quality suite independently covers full text, peer review, directness, recency, and replication. Figure/table grounding is intentionally excluded by the corrected task contract and `AGENTS.md`. |

## Reproduction

The added mutation is:

```python
import operator

def make_blender(combine=operator.add):
    def blend(row):
        return combine(row.confidence, row.evidence_quality)
    return blend
```

The outer scope correctly recognizes `combine` as an alias for `operator.add`, but that
callable alias is not propagated into the nested `blend` scope. The inner arithmetic call
therefore remains unclassified and the forbidden score combination is accepted.

Focused command:

```text
uv run pytest tests/test_score_separation.py -k aliased_arithmetic_callables -vv
1 failed, 3 passed, 13 deselected
Failed: DID NOT RAISE AssertionError
```

## Required commands

```text
uv run pytest tests/test_score_separation.py
1 failed, 16 passed

uv run pytest tests/test_quality.py
12 passed

uv run pytest
1 failed, 250 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
104 files already formatted
```

## What fixed should look like

The separation gate must carry arithmetic-callable aliases through lexical parent scopes,
including function defaults captured by nested functions, without leaking aliases into
unrelated sibling scopes. The committed nested-closure mutation must raise the same
`score arithmetic combines` assertion as the direct/default/import alias cases, while all
existing separation and quality tests remain green.

## Evidence notes

- Test file: `tests/test_score_separation.py`
- Failure frame: `tests/test_score_separation.py:414`
- Root-cause input: `qa|test_assertion|tests/test_score_separation.py:414`
- Root-cause hash: `aa1bb2bb4991`
- Screenshots intentionally omitted: every acceptance criterion is a non-visual Python or
  persistence/build-gate check, and this repository has no web UI in v1.
