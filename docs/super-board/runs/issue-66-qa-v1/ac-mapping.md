# AC mapping — issue #66

| AC | Criterion | Observable check | Result |
|----|-----------|------------------|--------|
| AC1 | `uv run airesearch sweep --kind evidence` processes subscribed scopes and writes one `sweep_run` with `kind='evidence'`, `items_found`, terminal state | `test_new_paper_sweep_writes_run_and_processes_end_to_end` asserts one `sweep_run` row (`kind=evidence`, `items_found=1`, terminal state + `finished_at`); `test_cli_sweep_kind_evidence_exits_zero` exercises CLI `--kind evidence` | PASS |
| AC2 | Newly discovered paper ends with built tree, extracted claims, linked evidence (fixture returning one new paper) | Same new-paper test: 1 paper, ≥1 `tree_node`, ≥1 `claim`, ≥1 `claim_evidence`; index/extract/link/score invoked for the scope | PASS |
| AC3 | Immediate re-run with no new upstream content creates zero new papers and exits 0 | `test_empty_rerun_creates_zero_new_papers_and_exits_zero`: second sweep `items_found=0`, paper count unchanged, CLI exit 0 | PASS |
| AC4 | Scope at 1,000-paper ceiling stops adding papers and logs a clear ceiling line | `test_ceiling_refusal_logs_and_stops_adding_papers`: ingest not called; log contains `1000` + `ceiling`; count stays at CORPUS_CEILING | PASS |
| AC5 | `uv run pytest tests/test_evidence_sweep.py` exits 0 covering new-paper, empty, ceiling, per-paper failure isolation | 5 passed: new-paper, empty rerun, ceiling, per-scope failure isolation, CLI | PASS |
