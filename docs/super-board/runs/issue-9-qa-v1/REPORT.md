# Issue #9 QA Evidence v1

- Branch: `issue-9-parse-pdfs-through-grobid-into-a-normalized-section-hierarchy`
- Builder commit: `556f1af`
- When: 2026-07-26T14:30:00Z (approx)
- Result: **PASS**

## Test plan (one observable check per AC)

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | Parsing a PDF populates `paper.tei_xml` verbatim and sets `parse_status='parsed'` | PASS | `test_parse_pdf_stores_tei_and_sections_from_grobid` |
| AC2 | `section` rows reproduce TEI `<body>` hierarchy with `parent_id` + `ordinal` | PASS | `test_tei_fixture_produces_expected_nested_section_titles_in_order` |
| AC3 | `page_start`/`page_end` + `char_start`/`char_end` recorded | PASS | same TEI fixture test (pages 1–6, char offsets into own `body_text`) |
| AC4 | GROBID failure records error, `parse_status='failed'`, does not raise | PASS | `test_grobid_failure_is_recorded_without_raising` (+ missing-PDF companion) |
| AC5 | `uv run pytest tests/test_parse.py` exits 0 against committed TEI fixture | PASS | 5 passed (incl. live GROBID when reachable) |

## Commands run

```bash
uv run pytest tests/test_parse.py -v   # 5 passed
uv run pytest                          # 84 passed
uv run ruff check .                    # All checks passed
uv run ruff format --check .           # 50 files already formatted
```

## Visual evidence

Skipped intentionally — this issue is a library/ingest task with no UI surface.
Screenshots do not apply. Logs in this directory are the primary evidence.

## Invariant spot-check

- No embeddings / vector similarity introduced.
- No LLM imports outside `ai_researcher.llm.gateway` (parse path is HTTP→GROBID only).
- Failures recorded on the paper object; parse call does not raise.
- No DB writes in parse module (pipeline task 10 owns persistence) — matches task out-of-scope.
