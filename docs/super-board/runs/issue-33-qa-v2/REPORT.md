# Issue #33 QA v2

## Result

PASS — the Reviewer-requested AC5 evidence gap is closed, and all five acceptance criteria
have observable offline coverage.

## Rebuild correction

QA v1 passed `shortlist_backend` directly to `run_evaluation()`, which changed only the
report metadata while the fixture traversal bypassed shortlisting. QA v2 now:

1. sets the real `SHORTLIST_BACKEND` environment variable to `pageindex`;
2. runs evaluation through the public `shortlist()` selector and records two
   `PageIndexShortlist.shortlist()` calls, one per gold question;
3. switches `SHORTLIST_BACKEND` to `postgres_fts`;
4. records two `PostgresFTSShortlist.shortlist()` calls; and
5. compares the resulting report metrics and persisted report structure.

The regression assertion was observed RED with zero backend calls before fixture traversal
was connected to the configured selector, then GREEN after the correction.

## Test plan and evidence

| Acceptance criterion | Observable check | Result |
|---|---|---|
| AC1 — 20+ labelled questions with question, scope, and answering section paths | Load `eval/goldset.yaml`, validate every required field, count entries, and inspect represented scopes | PASS — 20 questions across `surface-codes` and `transformers` |
| AC2 — CLI reports recall@k, citation precision, and unsupported-statement rate | `test_eval_cli_reports_all_metrics_and_report_path` invokes `airesearch eval --scope surface-codes --k 5` through Typer's CLI runner | PASS — all three named metrics and the report path are asserted |
| AC3 — dated JSON report is written | Run the offline fixture evaluation with a fixed 2026-07-27 timestamp and inspect the generated JSON | PASS — `eval-2026-07-27.json` contains a dated report and per-question scores |
| AC4 — fixture harness runs end to end without network access | Run the task's exact focused pytest command against the committed fixture corpus | PASS — 4 tests passed |
| AC5 — both shortlist backends produce comparable reports | Switch the real `SHORTLIST_BACKEND`, route fixture traversal through public `shortlist()`, assert distinct implementation calls, and compare report schema and metrics | PASS — call order was `pageindex` ×2 followed by `postgres_fts` ×2; reports remain comparable |

## Commands

```text
uv run pytest tests/test_eval_harness.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Focused result: `4 passed`.

Full result: `148 passed`; Ruff reported `All checks passed!` and
`83 files already formatted`.

## Artifacts

- `pytest-focused.xml` — focused acceptance-suite result
- `pytest-full.xml` — full repository test result

## Visual evidence

Screenshots are intentionally omitted. Issue #33 changes a CLI and Python evaluation
library only; it has no UI or visual acceptance criterion.
