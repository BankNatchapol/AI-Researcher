# QA Report — issue #71 · v1

**Issue:** #71 — Spike a compliant SciRate signal fetch, disabled by default  
**PR:** #83  
**Branch:** `issue-71-spike-a-compliant-scirate-signal-fetch-disabled-by-default`  
**Commit under test:** `84d9722`  
**Task file:** `docs/superpowers/projects/ai-researcher-app/phase-4/12-scirate-spike.md`  
**Result:** PASS  
**When:** 2026-07-30

## Acceptance criteria

| AC | Criterion | Command / check | Result |
|----|-----------|-----------------|--------|
| AC1 | Spike design doc records outcome, approach, recommendation | `docs/supersaiyan/designs/scirate-spike.md` + `test_design_doc_records_spike_outcome` | ✅ |
| AC2 | SciRate `DiscourseSource` registered, disabled by default | registry + `DISCOURSE_SCIRATE_ENABLED` default false | ✅ |
| AC3 | Flag unset ⇒ no SciRate HTTP contact from discourse sweep path | disabled poll / tracking-requester tests | ✅ |
| AC4 | Success path stores only scite count + arXiv ID + link | stored-row-shape tests (`body`/`title`/`author` None) | ✅ |
| AC5 | `uv run pytest tests/discourse/test_scirate.py` exits 0 | 10 passed (enabled + disabled configs) | ✅ |

## Commands run (exit 0)

```bash
uv run pytest tests/discourse/test_scirate.py -v   # 10 passed
uv run pytest                                      # 370 passed
uv run ruff check .                                # All checks passed
uv run ruff format --check .                       # 145 files already formatted
```

## Spike outcome (verified in design doc)

Live polite GET to SciRate returns Cloudflare 403 (`cf-mitigated: challenge`). Adapter ships registered but disabled; recommendation is defer — no browser automation.

## Visual evidence

Omitted intentionally — library/adapter task (no UI ACs).

## Evidence files

- `ac-results.md`
- `pytest-ac.log`
- `pytest-full.log`
- `ruff-check.log`
- `ruff-format.log`

## Notes for Reviewer

- `SciRateSource.poll` short-circuits when `discourse_scirate_enabled` is false — zero HTTP.
- Enabled path (fixture) parses numeric scite count only; never stores HTML body/title/author.
- HTTP 403 degrades silently to empty poll result.
- Hard invariant: discourse channel only; must not feed `scoring/`.
