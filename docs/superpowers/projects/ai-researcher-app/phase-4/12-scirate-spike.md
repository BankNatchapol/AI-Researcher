---
title: Spike a compliant SciRate signal fetch, disabled by default
order: 12
depends_on_task: 11-scheduler
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 24
skills: verification-before-completion
---

## Goal

A time-boxed investigation establishes whether SciRate scite counts can be fetched
compliantly, ships the adapter disabled by default, and records the finding either way — so
the question is answered rather than left open.

## Acceptance Criteria

- [ ] `docs/supersaiyan/designs/scirate-spike.md` exists and records the outcome, the exact approach attempted, and the recommendation — written whether the spike succeeds or fails
- [ ] A `scirate` adapter exists implementing `DiscourseSource`, registered but **disabled by default**, requiring `DISCOURSE_SCIRATE_ENABLED=true` to activate
- [ ] With the flag unset, `uv run airesearch sweep --kind discourse` does not contact SciRate at all, asserted by a test
- [ ] If fetching succeeds, the adapter stores only scite count, arXiv ID, and a link back — never page content — asserted by a test on the stored row shape
- [ ] `uv run pytest tests/discourse/test_scirate.py` exits 0, passing in both the enabled and disabled configurations

## Implementation notes

**Time box:** one working session. If a compliant fetch is not working by then, stop, ship
the adapter disabled, record the finding, and move the work to future work. This task must
never block the phase.

**Files:**
- Create: `src/ai_researcher/discourse/scirate.py` — signal-only fetch keyed by arXiv ID
- Create: `docs/supersaiyan/designs/scirate-spike.md` — findings and recommendation
- Modify: `src/ai_researcher/config.py` — add `DISCOURSE_SCIRATE_ENABLED`, defaulting false
- Test: `tests/discourse/test_scirate.py`

**Interfaces:**
- Consumes: `DiscourseSource` protocol (task 02); `discourse_item` and `discourse_mention` (task 01)
- Produces: an optional attention signal; nothing downstream may depend on it being available

**Constraints established by prior investigation, recorded in PROJECT.md risk 5:**
- robots.txt sets `search=yes`, `ai-train=no`, `use=reference` with `Allow: /`; `ai-input` is unspecified
- The site returns 403 to non-browser clients even with a browser User-Agent
- The `scirate` PyPI package is v0.1.0 from April 2018 and scrapes HTML — do not depend on it
- Therefore: fetch the numeric signal only, send an identifying User-Agent with a contact
  address, rate-limit conservatively, cache aggressively, and degrade silently on 403
- Never use any fetched content to train or fine-tune a model — `ai-train=no` is explicit

**Naming caution:** SciRate "scites" are community upvotes, an attention signal. They are
unrelated to scite.ai "Smart Citations", which classify citation intent. This adapter belongs
strictly to the discourse channel.

## Out of scope

No self-hosting of the SciRate Rails application — a local instance would have no community
scites and therefore no signal. No storing of page content. No use of scite counts in any
score. No browser automation or bot-detection circumvention; if a polite fetch does not work,
the answer is to defer, not to escalate.
