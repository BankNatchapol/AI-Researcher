# QA Report — issue #67 · v1

**Issue:** #67 — Run the discourse sweep with per-source failure isolation  
**PR:** #79  
**Branch:** `issue-67-discourse-sweep`  
**Commit under test:** `6ed6184`  
**Task file:** `docs/superpowers/projects/ai-researcher-app/phase-4/08-discourse-sweep.md`  
**Result:** PASS  
**When:** 2026-07-30

## Acceptance criteria

| AC | Criterion | Command / check | Result |
|----|-----------|-----------------|--------|
| AC1 | CLI discourse sweep polls enabled sources since `last_polled_at` and writes one `sweep_run` with `kind='discourse'` | `test_clean_poll_*` + `test_cli_discourse_sweep_*` | ✅ |
| AC2 | Items stored with mentions via task 05; `last_polled_at` advances on success | `test_clean_poll_*` (mentions + last_polled assert) | ✅ |
| AC3 | Immediate re-run adds zero duplicate `discourse_item` rows | `test_repeat_poll_adds_zero_duplicate_items` | ✅ |
| AC4 | Failing source recorded on `sweep_run`; others complete; CLI exits 0 | `test_failing_source_*` + `test_cli_discourse_sweep_*` | ✅ |
| AC5 | `tests/test_discourse_sweep.py` covers clean / repeat / fail-isolation / missing-creds skip | 5 passed | ✅ |

## Commands run (exit 0)

```bash
uv run pytest tests/test_discourse_sweep.py -v   # 5 passed
uv run pytest                                  # 334 passed
uv run ruff check .                            # All checks passed
uv run ruff format --check .                   # 135 files already formatted
uv run pytest tests/test_channel_separation.py -v  # 5 passed (AGENTS invariant 4)
```

## Evidence files

- `ac-focused-pytest.log`
- `ac-mapping.md`
- `ac-channel-separation.log`
- `full-pytest.log`
- `ruff-check.log`
- `ruff-format.log`

## Visual evidence

Omitted intentionally — CLI/library task (no UI ACs).

## Notes for Reviewer

- Sweep iterates enabled discourse registry adapters, polls since `last_polled_at` (or epoch), upserts items with `ON CONFLICT DO NOTHING`, resolves mentions via `resolve_against_corpus`, advances `last_polled_at` only on success.
- Per-source exceptions are collected into `sweep_run.error`; state becomes `completed_with_errors` when any source fails but others succeed; CLI still exits 0.
- Reddit without credentials is skipped (logged) and does not count as a failure.
- Channel separation invariant holds: `scoring/` does not import `discourse/`.
