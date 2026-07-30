# QA Report — issue #66 · v1

**Issue:** #66 — Run the evidence sweep over subscribed topics  
**PR:** #78  
**Branch:** `issue-66-run-the-evidence-sweep-over-subscribed-topics`  
**Commit under test:** `f002da6`  
**Task file:** `docs/superpowers/projects/ai-researcher-app/phase-4/07-evidence-sweep.md`  
**Result:** PASS  
**When:** 2026-07-30

## Acceptance criteria

| AC | Criterion | Command / check | Result |
|----|-----------|-----------------|--------|
| AC1 | CLI evidence sweep writes terminal `sweep_run` (`kind=evidence`, `items_found`) | `test_new_paper_sweep_*` + `test_cli_sweep_kind_evidence_exits_zero` | ✅ |
| AC2 | New paper → tree + claims + linked evidence | Fixture one-paper path in `test_new_paper_sweep_*` | ✅ |
| AC3 | Empty re-run → zero new papers, exit 0 | `test_empty_rerun_*` | ✅ |
| AC4 | 1,000-paper ceiling refusal + log line | `test_ceiling_refusal_*` | ✅ |
| AC5 | `tests/test_evidence_sweep.py` covers new/empty/ceiling/failure isolation | 5 passed | ✅ |

## Commands run (exit 0)

```bash
uv run pytest tests/test_evidence_sweep.py -v   # 5 passed
uv run pytest                                  # 329 passed
uv run ruff check .                            # All checks passed
uv run ruff format --check .                   # 133 files already formatted
```

## Evidence files

- `ac-focused-pytest.log`
- `ac-mapping.md`
- `full-pytest.log`
- `ruff-check.log`
- `ruff-format.log`

## Visual evidence

Omitted intentionally — CLI/library task (no UI ACs).

## Notes for Reviewer

- Sweep walks active **topic** subscriptions only through ingest → index → extract → link → confidence rescore.
- Ceiling check uses `CORPUS_CEILING` (1000) before ingest; log names the ceiling.
- Per-scope failures are recorded on the `sweep_run` and do not abort other scopes.
- Default `score_fn` is `score_scope_confidence` only (task says "rescore"; quality scorer not wired in this PR — out of stated AC scope).
