---
title: Implement the config-driven RSS blog adapter and Hugging Face Papers adapter
order: 4
depends_on_task: 03-reddit-hackernews-adapters
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 8, 9, 10
skills: test-driven-development, verification-before-completion
---

## Goal

Research blogs are followed through a single configuration-driven RSS adapter, and Hugging
Face Papers / alphaXiv supply daily curated AI attention — so adding a new blog is a config
line, not a code change.

## Acceptance Criteria

- [ ] Adding a feed URL to `DISCOURSE_RSS_FEEDS` makes it pollable with no code change, asserted by a test adding a fixture feed via config only
- [ ] Google Research and Google Quantum AI ship as default feeds in `.env.example`
- [ ] The Hugging Face Papers / alphaXiv adapter implements `DiscourseSource` and is registered
- [ ] A malformed or unreachable feed is logged and skipped without aborting the poll of remaining feeds
- [ ] `uv run pytest tests/discourse/test_rss.py tests/discourse/test_huggingface.py` exits 0 from recorded fixtures with no live network

## Implementation notes

**Files:**
- Create: `src/ai_researcher/discourse/rss_blogs.py` — one adapter instance per configured feed URL; parses standard RSS and Atom
- Create: `src/ai_researcher/discourse/huggingface.py` — daily papers listing with attention counts
- Modify: `src/ai_researcher/config.py` — add `DISCOURSE_RSS_FEEDS` as a comma-separated URL list
- Modify: `.env.example` — document the variable with the two Google feeds as defaults
- Test: `tests/discourse/fixtures/google-research.rss.xml`, `tests/discourse/fixtures/hf-papers.json`
- Test: `tests/discourse/test_rss.py`, `tests/discourse/test_huggingface.py`

**Interfaces:**
- Consumes: `DiscourseSource` protocol and registry (task 02); the rate limiter from Phase 1 task 05
- Produces: registered adapters — polled by task 08

**Extensibility note:** the RSS adapter is the answer to "make it easy to add more sources"
from the design doc. Any blog publishing a feed is one config entry away; only sources
without a feed need new adapter code.

## Out of scope

No HTML scraping of blogs without feeds. No SciRate — task 12. No full-article fetching;
titles, links, and dates only, consistent with linking back rather than reproducing content.
No sentiment scoring.
