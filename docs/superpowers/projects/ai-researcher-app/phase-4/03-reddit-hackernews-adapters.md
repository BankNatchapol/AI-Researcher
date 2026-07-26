---
title: Implement the Reddit and Hacker News discourse adapters
order: 3
depends_on_task: 02-discourse-protocol-and-invariants
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 8, 10, 11
skills: test-driven-development, verification-before-completion
---

## Goal

Reddit and Hacker News are pollable as community-attention sources through their official
APIs, with missing credentials degrading gracefully rather than failing.

## Acceptance Criteria

- [ ] Both adapters implement `DiscourseSource` and are registered
- [ ] The Reddit adapter uses the official API with OAuth credentials from environment variables and polls `r/QuantumComputing` and `r/MachineLearning` by default
- [ ] With Reddit credentials absent, the adapter is skipped with a clear log line and the process exits 0 rather than raising
- [ ] The Hacker News adapter uses the public Firebase API and requires no credentials
- [ ] `uv run pytest tests/discourse/test_reddit.py tests/discourse/test_hackernews.py` exits 0, served entirely from recorded fixtures with no live network, and asserting each sends a User-Agent containing the tool name and `CONTACT_EMAIL`

## Implementation notes

**Files:**
- Create: `src/ai_researcher/discourse/reddit.py` — OAuth via `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`; subreddit list from config
- Create: `src/ai_researcher/discourse/hackernews.py` — Firebase API search over story titles and URLs
- Modify: `src/ai_researcher/config.py` — add `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_SUBREDDITS`
- Modify: `.env.example` — document all three, marked optional
- Test: `tests/discourse/fixtures/` — recorded API responses
- Test: `tests/discourse/test_reddit.py`, `tests/discourse/test_hackernews.py`

**Interfaces:**
- Consumes: `DiscourseSource` protocol and registry (task 02); the rate limiter from Phase 1 task 05
- Produces: registered adapters — polled by task 08's discourse sweep

**Behaviour notes:**
- `poll(since)` returns only items newer than `since`, so repeat sweeps stay cheap
- Both adapters reuse the per-source rate limiter rather than introducing a second mechanism
- Neither adapter resolves papers; `link_targets` is implemented in task 05 as shared logic

## Out of scope

No RSS or Hugging Face adapters — task 04. No SciRate — task 12. No sentiment analysis of
any kind; attention counts and links only. No storing of full post bodies beyond what
`discourse_item` defines.
