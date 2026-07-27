# Issue #33 QA v1

## Result

PASS — all five acceptance criteria have observable offline coverage.

## Test plan and evidence

| Acceptance criterion | Observable check | Result |
|---|---|---|
| AC1 — 20+ labelled questions with question, scope, and answering section paths | Load `eval/goldset.yaml`, validate every required field, count entries, and inspect represented scopes | PASS — 20 questions across `surface-codes` and `transformers` |
| AC2 — CLI reports recall@k, citation precision, and unsupported-statement rate | `test_eval_cli_reports_all_metrics_and_report_path` invokes `airesearch eval --scope surface-codes --k 5` through Typer's CLI runner | PASS — all three named metrics and the report path are asserted |
| AC3 — dated JSON report is written | Run the offline fixture evaluation with a fixed 2026-07-27 timestamp and inspect the generated JSON | PASS — `eval-2026-07-27.json` contains a dated report and per-question scores |
| AC4 — fixture harness runs end to end without network access | Run the task's exact focused pytest command against the committed fixture corpus | PASS — 4 tests passed |
| AC5 — both shortlist backends produce comparable reports | Set `SHORTLIST_BACKEND` to `pageindex` and `postgres_fts`, run the same fixture evaluation, then compare report schema and metrics | PASS — both labelled runs are present with identical metric structure and values |

## Commands

```text
uv run pytest tests/test_eval_harness.py
```

Focused result: `4 passed`.

The independent fixture probe produced:

```text
gold_questions: 20
scopes: surface-codes, transformers
backends: pageindex, postgres_fts
recall_at_k: 0.5
citation_precision: 0.5
unsupported_statement_rate: 0.3333333333333333
```

Full repository verification is recorded in `pytest-full.xml` and summarized below:

```text
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Full result: `148 passed`; Ruff reported `All checks passed!` and
`83 files already formatted`.

## Artifacts

- `eval-2026-07-27.json` — persisted two-backend fixture evaluation with per-question scores
- `pytest-focused.xml` — focused acceptance-suite result
- `pytest-full.xml` — full repository test result

## Visual evidence

Screenshots are intentionally omitted. Issue #33 changes a CLI and Python evaluation
library only; it has no UI or visual acceptance criterion.
