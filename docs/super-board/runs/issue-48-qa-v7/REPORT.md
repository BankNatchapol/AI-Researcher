# Issue #48 QA v7 — FAIL

- Issue: #48 — Compute evidence quality from a written rubric and enforce score separation
- PR: #57
- Branch: `issue-48-compute-evidence-quality-from-a-written-rubric-and-enforce-score-separation`
- Builder head tested: `c085fe44d8cc9f3eab24d4ed760066c3a6dbe318`
- Date: 2026-07-30
- Result: **FAIL — AC4**

## Acceptance-criterion results

| AC | Result | Observable evidence |
|---|---|---|
| AC1 — rubric-only bounded quality score | PASS | `tests/test_quality.py` verifies the score is 0–100, equals the sum of the five documented factor contributions, and contains no undocumented factor. |
| AC2 — content-derived rubric version on every score row | PASS | Quality and confidence persistence tests store the exact version returned by `load_rubric()` and reject the former placeholder path. |
| AC3 — abstract-only penalty | PASS | The otherwise-identical abstract-only/full-text comparison changes only the `full_text` contribution and lowers the abstract-only score. |
| AC4 — mechanical score/discourse separation gate | **FAIL** | Direct arithmetic through `row.confidence.__add__(row.evidence_quality)` bypasses the AST gate. The v7 mutation at `tests/test_score_separation.py:363` does not trigger the expected assertion. |
| AC5 — each approved v1 rubric factor isolated | PASS | The 12-test quality suite independently covers full text, peer review, directness, recency, and replication. Figure/table grounding remains intentionally excluded by the corrected task contract and `AGENTS.md`. |

## Reproduction

The added mutation is:

```python
def blend(row):
    return row.confidence.__add__(row.evidence_quality)
```

Python numeric dunder methods perform the same arithmetic as their operator syntax. The
gate sees both score fields but classifies only `ast.BinOp` nodes and calls whose names are
in `ARITHMETIC_CALLS`; `__add__` is not classified as arithmetic, so the forbidden
combination is accepted.

Focused command:

```text
uv run pytest tests/test_score_separation.py
1 failed, 19 passed
Failed: DID NOT RAISE AssertionError
Failure: tests/test_score_separation.py:382
```

## Required commands

```text
uv run pytest tests/test_score_separation.py
1 failed, 19 passed

uv run pytest tests/test_quality.py
12 passed

uv run pytest
1 failed, 253 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
104 files already formatted
```

## What fixed should look like

The score-separation gate must classify numeric arithmetic dunder calls such as `__add__`
as arithmetic when they receive both `confidence` and `evidence_quality`. The committed v7
mutation must raise the same `score arithmetic combines` assertion as direct `+`,
`operator.add`, callable aliases, defaults, and closure-captured aliases, while all earlier
separation and quality tests remain green.

## Evidence notes

- Test file: `tests/test_score_separation.py`
- Failure frame: `tests/test_score_separation.py:382`
- Root-cause input: `qa|test_assertion|tests/test_score_separation.py:382`
- Root-cause hash: `d083c1dde6c7`
- Screenshots intentionally omitted: every acceptance criterion is a non-visual Python or
  persistence/build-gate check, and this repository has no web UI in v1.
