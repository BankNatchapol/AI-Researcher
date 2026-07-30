# QA Report — issue #50 v1

Date: 2026-07-30
Branch: `issue-50-extend-the-eval-harness-with-extraction-and-stance-metrics`
Commit under test: `a120a13`
PR: https://github.com/BankNatchapol/AI-Researcher/pull/59

## Scope

Non-visual ACs (CLI / eval harness / unit tests only). No UI — screenshots intentionally omitted.

## Acceptance Criteria plan

| AC | Observable test | Result |
|----|-----------------|--------|
| AC1 | ≥15 gold claims each with `section_path` + stance | **PASS** (20 claims) |
| AC2 | `airesearch eval --extraction` reports P/R/F1, span precision, stance accuracy | **PASS** |
| AC3 | Extraction appends to same dated `eval-<date>.json` as retrieval | **PASS** |
| AC4 | Invalid labelled `section_path` raises loudly | **PASS** |
| AC5 | `uv run pytest tests/test_extraction_eval.py` exits 0 offline | **PASS** (6/6) |

## Per-AC evidence

### AC1 — goldset claims

```
claim_count=20
missing_section_path_or_stance=0
stances=['mentions', 'supports']
AC1_PASS
```

See `ac1-goldset-claims.txt`.

### AC2 — metric reporting

- CLI exposes `--extraction` (`airesearch eval --help`).
- `test_eval_cli_extraction_flag_reports_metrics` asserts stdout contains all five metrics.
- Fixture-backed `run_extraction_evaluation` produced:

```
claim precision: 0.667
claim recall: 0.667
claim f1: 0.667
evidence-span precision: 0.250
stance accuracy: 0.667
```

- Live `airesearch eval --extraction --scope surface-codes` against the local DB correctly refused (gold paths not present in corpus) — that is AC4 behaviour, not a metric regression. Offline fixture path is the stated verification surface for this task.

See `ac2-extraction-cli-metrics.txt`, `ac2-live-cli.txt`.

### AC3 — shared dated report

Retrieval + extraction both wrote to the same `eval-2026-07-30.json`; report has `runs[0].kind=retrieval` and `runs[1].kind=extraction` with the five extraction metrics.

See `ac3-append-both-kinds.txt`, `ac3-shared-report/eval-2026-07-30.json`.

### AC4 — loud validation

```
raised GoldSetValidationError: Gold section_path 'Results/Does Not Exist'
  for 'a missing-path claim' matches no section in scope 'fixture-eval'
AC4_PASS
```

Also confirmed live against empty local corpus for `surface-codes` / `transformers`.

### AC5 — offline pytest

```
tests/test_extraction_eval.py — 6 passed in 0.95s
EXIT=0
```

See `ac5-pytest-extraction-eval.txt`.

## Regression gate

```
272 passed in 14.87s
ruff check: All checks passed!
ruff format --check: 110 files already formatted
```

See `full-suite.txt`.

## Verdict

**PASS** — all five acceptance criteria verified. Ready for Review.
