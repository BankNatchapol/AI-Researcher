# Issue #48 QA evidence — v1

- Issue: #48 — Compute evidence quality from a written rubric and enforce score separation
- PR: #57
- Branch: `issue-48-compute-evidence-quality-from-a-written-rubric-and-enforce-score-separation`
- Builder commit tested: `7018bc88fd98975e6f5f0651a776d3671dbf96fc`
- QA result: PASS
- Date: 2026-07-29

## Test plan and results

| Acceptance criterion | Observable test | Result |
|---|---|---|
| AC1 — `score_quality` returns a rubric-derived 0–100 `QualityScore` | `test_score_returns_bounded_value_and_every_documented_factor` verifies the bound, the exact six documented factors, and that the value equals their summed contributions. | PASS |
| AC2 — every persisted score has a content-derived rubric version | `test_rubric_version_changes_when_any_rubric_file_content_changes` and `test_persisted_claim_score_rows_carry_the_exact_rubric_version` verify content changes alter the version and that each inserted row receives the corresponding exact version. | PASS |
| AC3 — abstract-only evidence scores lower than otherwise-identical full text | `test_abstract_only_claim_scores_lower_than_otherwise_identical_full_text_claim` changes only `parse_status` and verifies only the full-text factor and total score increase. | PASS |
| AC4 — score arithmetic and discourse imports are build-gated | `tests/test_score_separation.py` scans the package AST. An intentional binary-score violation produced the expected failure at `scoring/_qa_issue48_violation.py:7`. QA also found and fixed a missing `from ai_researcher import discourse` import form with a RED→GREEN regression test. | PASS |
| AC5 — every rubric factor is isolated | `tests/test_quality.py` independently varies full-text availability, peer-review status, directness, evidence presentation, recency, and distinct supporting-paper count while asserting other contributions stay unchanged. | PASS |

## QA regression added

The original discourse gate inspected only `ImportFrom.module`, so this forbidden form was
not detected:

```python
from ai_researcher import discourse
```

QA added `test_discourse_gate_detects_from_package_import`. Before the detector change, the
focused test failed with `Failed: DID NOT RAISE AssertionError`. After including imported
names in the module candidates, the focused test and complete separation suite passed.

## Command evidence

```text
$ uv run pytest tests/test_score_separation.py
collected 3 items
tests/test_score_separation.py ... [100%]
3 passed in 0.05s

$ uv run pytest tests/test_quality.py
collected 11 items
tests/test_quality.py ........... [100%]
11 passed in 0.10s

$ uv run pytest
collected 234 items
234 passed in 15.79s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
104 files already formatted
```

## Visual evidence

Screenshots are intentionally omitted. Issue #48 changes a Python scoring library, a written
rubric, persistence parameters, and offline AST/unit-test gates; it has no UI-affecting
acceptance criterion, and the project explicitly excludes a web UI from v1.
