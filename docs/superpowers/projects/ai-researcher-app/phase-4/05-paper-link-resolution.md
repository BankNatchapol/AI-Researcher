---
title: Resolve discourse items to the papers they reference
order: 5
depends_on_task: 04-rss-and-huggingface-adapters
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 12
skills: test-driven-development, verification-before-completion
---

## Goal

A community post that references a paper is linked to it by arXiv ID or DOI, while posts
referencing nothing known are kept as topic-level signal rather than discarded.

## Acceptance Criteria

- [ ] `link_targets(item) -> list[PaperRef]` extracts arXiv IDs and DOIs from an item's URL and body text
- [ ] A resolved item produces a `discourse_mention` row with `resolved_by` set to `arxiv_id` or `doi`
- [ ] An item referencing no known paper is stored with zero `discourse_mention` rows and is not dropped
- [ ] An item referencing a paper not in the local corpus produces no mention row and logs the unmatched identifier
- [ ] `uv run pytest tests/discourse/test_link_resolution.py` exits 0, covering an arXiv abs URL, an arXiv PDF URL, a bare arXiv ID in body text, a DOI URL, an unknown paper, and a no-reference post

## Implementation notes

**Files:**
- Create: `src/ai_researcher/discourse/resolve.py` — `extract_identifiers(text) -> list[Identifier]` and `link_targets(item)`; shared by every adapter rather than reimplemented per source
- Modify: `src/ai_researcher/discourse/base.py` — provide `link_targets` as a shared default implementation adapters inherit
- Test: `tests/discourse/test_link_resolution.py`

**Interfaces:**
- Consumes: `DiscourseItem` from adapters (tasks 03–04); `paper.arxiv_id` and `paper.doi` (Phase 1 task 03); `discourse_mention` table (task 01)
- Produces: `discourse_mention` rows — read by task 09 change detection and task 10 digests

**Matching notes:**
- arXiv ID extraction handles both the modern `2601.01234` form and legacy `quant-ph/0601001` form, since the quantum literature contains both
- Matching against the corpus is exact on `arxiv_id` or `doi`; no fuzzy title matching, so a
  mention is never attributed to the wrong paper

## Out of scope

No creation of new `paper` rows from discourse mentions — a post about an uningested paper
does not trigger ingestion. No sentiment or stance classification of posts; discourse carries
no stance, only attention. No influence on any score.
