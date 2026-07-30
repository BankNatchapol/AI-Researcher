# Issue #48 QA v9 — FAIL

- Issue: #48 — Compute evidence quality from a written rubric and enforce score separation
- PR: #57
- Branch: `issue-48-compute-evidence-quality-from-a-written-rubric-and-enforce-score-separation`
- Builder head tested: `8b9dfc4297569ce6ca849576e74a8d557bc2b4ba`
- Date: 2026-07-30
- Result: **FAIL — AC4**

## Acceptance-criterion results

| AC | Result | Observable evidence |
|---|---|---|
| AC1 — rubric-only bounded quality score | PASS | `test_score_returns_bounded_value_and_every_documented_factor` verifies the score is 0–100, equals the five documented factor contributions, and contains no undocumented factor. |
| AC2 — content-derived rubric version on every score row | PASS | `test_persisted_claim_score_rows_carry_the_exact_rubric_version` and `test_confidence_persistence_requires_computed_quality_and_current_rubric_version` verify both persistence paths store the current content-derived version and computed quality. |
| AC3 — abstract-only penalty | PASS | `test_abstract_only_claim_scores_lower_than_otherwise_identical_full_text_claim` changes only `parse_status` and verifies the abstract-only score is lower. |
| AC4 — mechanical score/discourse separation gate | **FAIL** | Mapping-style field access bypasses the AST gate: `row.get("confidence") + row.get("evidence_quality")` is accepted. The v9 mutation at `tests/test_score_separation.py:430` does not trigger the required assertion at line 449. Existing discourse-import and augmented-assignment coverage remains green. |
| AC5 — each approved v1 rubric factor isolated | PASS | The 12-test quality suite independently covers full text, peer review, directness, recency, and replication. Figure/table grounding remains intentionally excluded by the corrected task contract and `AGENTS.md`. |

## Reproduction

The added mutation is:

```python
def blend(row):
    return row.get("confidence") + row.get("evidence_quality")
```

`_score_fields` recognizes score names in attributes and string-key subscripts, but it does
not recognize string field names passed to mapping accessors such as `get`. The surrounding
`ast.BinOp` is arithmetic, yet neither score name reaches the resolved-field set, so the
forbidden blend passes undetected.

Focused command:

```text
uv run pytest tests/test_score_separation.py::test_score_arithmetic_gate_detects_mapping_get_access -vv
1 failed
Failed: DID NOT RAISE AssertionError
Failure: tests/test_score_separation.py:449
```

## Required commands

```text
uv run pytest tests/test_score_separation.py
1 failed, 21 passed

uv run pytest tests/test_quality.py
12 passed

uv run pytest
1 failed, 255 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
104 files already formatted
```

Before adding the v9 mutation, the Builder baseline was green:

```text
uv run pytest tests/test_score_separation.py
21 passed

uv run pytest tests/test_quality.py
12 passed
```

## What fixed should look like

The score-separation gate must recognize `confidence` and `evidence_quality` when accessed
through mapping-style calls such as `row.get("confidence")` and
`row.get("evidence_quality")`. The committed v9 mutation must raise the same
`score arithmetic combines` assertion as attribute, subscript, alias, callable, closure,
dunder, and augmented-assignment forms, while all earlier separation and quality tests
remain green.

## Evidence notes

- Test file: `tests/test_score_separation.py`
- Mutation definition: `tests/test_score_separation.py:430`
- Failure frame: `tests/test_score_separation.py:449`
- Root-cause input: `qa|test_assertion|tests/test_score_separation.py:449`
- Root-cause hash: `61879e732f0f`
- Screenshots intentionally omitted: every acceptance criterion is a non-visual Python or
  persistence/build-gate check, and this repository has no web UI in v1.
