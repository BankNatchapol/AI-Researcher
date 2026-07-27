# QA Report — issue #42 (v1)

**Issue:** #42 — Add the extraction, evidence, and dual-score schema  
**PR:** https://github.com/BankNatchapol/AI-Researcher/pull/51  
**Branch:** `issue-42-add-the-extraction-evidence-and-dual-score-schema`  
**Commit under test:** `cd76ad0`  
**Task file:** `docs/superpowers/projects/ai-researcher-app/phase-3/01-extraction-schema.md`  
**Result:** ✅ PASS

## Visual evidence

Intentionally omitted — schema/migration/SQL constraints only; no UI surface.

## Acceptance criteria

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | `uv run airesearch db migrate` applies; re-run "already up to date" | ✅ PASS | `schema-probe.log`, `test_extraction_schema.py` |
| AC2 | claim/method/result/dataset/metric have `paper_id` + NOT NULL `tree_node_id` FK | ✅ PASS | `schema-probe.log`, model + DB inspect in test |
| AC3 | `claim_evidence` columns + stance CHECK (`supports`/`refutes`/`mentions`) | ✅ PASS | `schema-probe.log`; invalid `agrees` rejected |
| AC4 | `claim_score` has separate NOT NULL `confidence` + `evidence_quality` (+ rubric_version, scored_at) | ✅ PASS | `schema-probe.log`; no combined score column |
| AC5 | `uv run pytest tests/test_extraction_schema.py` exits 0 | ✅ PASS | `test-output.log` — 2 passed |

## Commands run

```bash
uv run pytest tests/test_extraction_schema.py -v   # 2 passed
uv run pytest                                      # 150 passed
uv run ruff check .                                # All checks passed
uv run ruff format --check .                       # 84 files already formatted
```

## Notes

- Migration shipped as `0005_extraction.sql` (not `0004`) because `0004_fts_index` already exists — acceptable; ACs check behavior, not filename.
- Hard invariants preserved: passage anchors NOT NULL; confidence and evidence_quality never blended.
