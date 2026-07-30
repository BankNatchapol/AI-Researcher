# Issue #48 QA v8 — FAIL

- Issue: #48 — Compute evidence quality from a written rubric and enforce score separation
- PR: #57
- Branch: `issue-48-compute-evidence-quality-from-a-written-rubric-and-enforce-score-separation`
- Builder head tested: `d249ccb77f5ed7c2cd08529fcbaaf410e3901964`
- Date: 2026-07-30
- Result: **FAIL — AC4**

## Acceptance-criterion results

| AC | Result | Observable evidence |
|---|---|---|
| AC1 — rubric-only bounded quality score | PASS | `tests/test_quality.py` verifies the score is bounded to 0–100, equals the sum of the five documented factor contributions, and contains no undocumented factor. |
| AC2 — content-derived rubric version on every score row | PASS | Quality and confidence persistence tests store the exact content-derived version returned by `load_rubric()` and reject the former placeholder path. |
| AC3 — abstract-only penalty | PASS | The otherwise-identical abstract-only/full-text test changes only the `full_text` contribution and produces a lower abstract-only score. |
| AC4 — mechanical score/discourse separation gate | **FAIL** | Augmented assignment bypasses the AST gate: after `combined = row.confidence`, `combined += row.evidence_quality` is accepted. The v8 mutation at `tests/test_score_separation.py:403` does not trigger the required assertion at line 426. |
| AC5 — each approved v1 rubric factor isolated | PASS | The 12-test quality suite independently covers full text, peer review, directness, recency, and replication. Figure/table grounding remains intentionally excluded by the corrected task contract and `AGENTS.md`. |

## Reproduction

The added mutation is:

```python
def blend(row):
    combined = row.confidence
    combined += row.evidence_quality
    return combined
```

`ast.AugAssign` performs in-place arithmetic but is neither an `ast.BinOp` nor an
`ast.Call`, the two node forms classified by the current gate. Score-alias discovery
correctly knows that `combined` carries `confidence`, but the augmented-assignment node is
never checked as arithmetic.

Focused command:

```text
uv run pytest tests/test_score_separation.py
1 failed, 20 passed
Failed: DID NOT RAISE AssertionError
Failure: tests/test_score_separation.py:426
```

## Required commands

```text
uv run pytest tests/test_score_separation.py
1 failed, 20 passed

uv run pytest tests/test_quality.py
12 passed

uv run pytest
1 failed, 254 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
104 files already formatted
```

Before adding the v8 mutation, the builder baseline was green:

```text
uv run pytest tests/test_score_separation.py
20 passed

uv run pytest tests/test_quality.py
12 passed
```

## What fixed should look like

The score-separation gate must classify `ast.AugAssign` as arithmetic and resolve score
aliases on both its target and value. The committed v8 mutation must raise the same
`score arithmetic combines` assertion as direct binary syntax, arithmetic callables,
defaults, closures, and numeric dunder methods, while all earlier separation and quality
tests remain green.

## Evidence notes

- Test file: `tests/test_score_separation.py`
- Mutation definition: `tests/test_score_separation.py:403`
- Failure frame: `tests/test_score_separation.py:426`
- Root-cause input: `qa|test_assertion|tests/test_score_separation.py:426`
- Root-cause hash: `b6d117286971`
- Screenshots intentionally omitted: every acceptance criterion is a non-visual Python or
  persistence/build-gate check, and this repository has no web UI in v1.
