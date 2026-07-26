---
title: Parse PDFs through GROBID into a normalized section hierarchy
order: 9
depends_on_task: 08-pdf-acquisition
project: ai-researcher-app
phase: 1
depends_on_phase: null
design: docs/superpowers/projects/ai-researcher-app/phase-1/PHASE.md
plan_task: Requirements 17, 18
skills: test-driven-development, verification-before-completion
---

## Goal

A downloaded PDF is parsed by GROBID, its TEI XML stored verbatim, and its body hierarchy
normalized into `section` rows that preserve nesting, order, page ranges, and character
offsets — the structure every later phase depends on.

## Acceptance Criteria

- [ ] Parsing a PDF populates `paper.tei_xml` with GROBID's TEI output verbatim and sets `parse_status = 'parsed'`
- [ ] `section` rows reproduce the TEI `<body>` hierarchy with correct `parent_id` nesting and `ordinal` document order
- [ ] Each `section` row records `page_start` and `page_end` when GROBID supplies coordinates, and `char_start`/`char_end` offsets into its own `body_text`
- [ ] A GROBID failure records the error on the paper, sets `parse_status = 'failed'`, and does not raise out of the parse call
- [ ] `uv run pytest tests/test_parse.py` exits 0 against a committed TEI fixture, asserting a known paper produces the expected nested section titles in the expected order

## Implementation notes

**Files:**
- Create: `src/ai_researcher/ingest/parse.py` — `parse_pdf(paper) -> ParseResult`; posts to GROBID `/api/processFulltextDocument` with `teiCoordinates` enabled so page positions are available
- Create: `src/ai_researcher/ingest/tei.py` — `tei_to_sections(tei_xml) -> list[SectionRecord]`; walks `<body>` divs recursively building `section_path` as a slash-joined heading trail
- Test: `tests/fixtures/sample-paper.tei.xml` — a real committed TEI document
- Test: `tests/test_parse.py` — parses the fixture offline; a separate marked test hits a live GROBID and is skipped when `GROBID_URL` is unreachable

**Interfaces:**
- Consumes: `paper.pdf_path` from task 08; `section` table from task 03; `GROBID_URL` from config
- Produces: `section` rows with full hierarchy — the direct input to Phase 2's tree builder, and to Phase 3's `tree_node_id` anchoring

**Structure notes:**
- `section_path` is the slash-joined trail of ancestor titles, e.g. `Results/Threshold estimates`
- Sections with no heading take a positional placeholder title so `section_path` stays unique within a paper
- `body_text` holds only that section's own text, not its children's, so offsets stay meaningful

## Out of scope

No tree building, node summaries, or LLM calls — Phase 2 owns `trees/build.py`. No table or
figure extraction; figure and table grounding is deferred post-v1. No reference or citation
parsing. No pipeline orchestration (task 10).
