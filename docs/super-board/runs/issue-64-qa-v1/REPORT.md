# QA Report — issue #64 · v1

**Issue:** #64 — Resolve discourse items to the papers they reference  
**PR:** #76  
**Branch:** `issue-64-paper-link-resolution`  
**Commit under test:** `7125dce`  
**Task file:** `docs/superpowers/projects/ai-researcher-app/phase-4/05-paper-link-resolution.md`  
**Result:** PASS  
**When:** 2026-07-30

## Acceptance criteria

| AC | Criterion | Command / check | Result |
|----|-----------|-----------------|--------|
| AC1 | `link_targets(item) -> list[PaperRef]` extracts arXiv IDs and DOIs from URL and body | `uv run pytest tests/discourse/test_link_resolution.py` (extract + link_targets cases) | ✅ |
| AC2 | Resolved item writes `discourse_mention` with `resolved_by` arXiv/DOI | DB tests assert `resolved_by == "arxiv"` / `"doi"` (schema CHECK) | ✅ |
| AC3 | No-reference item stored with zero mentions and not dropped | `test_no_reference_item_stored_without_mentions` | ✅ |
| AC4 | Unknown-paper identifier logged; no mention row | `test_unknown_paper_logs_and_writes_no_mention` | ✅ |
| AC5 | Focused suite covers abs URL, PDF URL, bare ID, DOI, unknown, no-ref | `uv run pytest tests/discourse/test_link_resolution.py` | ✅ (11 passed) |

## Commands run (exit 0)

```bash
uv run pytest tests/discourse/test_link_resolution.py -v   # 11 passed
uv run pytest                                              # 313 passed
uv run ruff check .                                        # All checks passed
uv run ruff format --check .                               # 128 files already formatted
```

## Evidence files

- `ac1-link-targets-extract.log`
- `ac2-resolved-by-mention.log`
- `ac3-no-reference-kept.log`
- `ac4-unknown-paper-logged.log`
- `ac5-focused-pytest.log`
- `ac-adapters-shared-resolver.log`
- `schema-resolved-by-constraint.log`
- `full-pytest.log`
- `ruff-check.log`
- `ruff-format.log`

## Visual evidence

Omitted intentionally — library/DB resolution task (no UI ACs).

## Notes for Reviewer

- Task-file wording says `resolved_by` of `arxiv_id` or `doi`; migration `0011_discourse.sql` CHECK constrains `resolved_by IN ('arxiv', 'doi')`. Implementation correctly stores `arxiv` / `doi`, matching the schema invariant from task 01.
- `extract_identifiers` handles modern (`2601.01234`) and legacy (`quant-ph/0601001`) arXiv forms; corpus match is exact on `paper.arxiv_id` / `paper.doi`.
- Adapters inherit `DiscourseLinkMixin` and delegate to shared `link_targets`.
- Hard invariants: no embeddings; discourse stays out of scoring (channel-separation suite still green in full run).
