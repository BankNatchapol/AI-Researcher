---
title: Canonicalize duplicate claims behind a cheap prefilter
order: 5
depends_on_task: 04-evidence-linking
project: ai-researcher-app
phase: 3
depends_on_phase: 2
design: docs/superpowers/projects/ai-researcher-app/phase-3/PHASE.md
plan_task: Requirements 13, 14
skills: test-driven-development, verification-before-completion
---

## Goal

The same result stated by several papers becomes one canonical claim with evidence from each
paper, decided by an LLM comparison that only ever runs on cheaply prefiltered pairs.

## Acceptance Criteria

- [ ] A claim stated by two papers yields one canonical claim and two `claim_evidence` rows naming both papers
- [ ] Original claim rows are preserved with `canonical_claim_id` pointing at the canonical row — nothing is overwritten or deleted
- [ ] The non-LLM prefilter matches on claim type, metric, and overlapping numeric range before any model call, asserted by a test that counts LLM invocations and proves non-prefiltered pairs are never compared
- [ ] Two claims with the same metric but non-overlapping values stay distinct rather than merging
- [ ] `uv run pytest tests/test_claim_identity.py` exits 0, covering a true duplicate, a near-miss that must stay separate, a unit-mismatch pair, and the prefilter call-count assertion

## Implementation notes

**Files:**
- Create: `src/ai_researcher/evidence/identity.py` — `prefilter_pairs(claims)` then `canonicalize(pairs)`; the LLM comparison runs strictly on prefiltered output
- Modify: `src/ai_researcher/cli.py` — extend `extract` with a `--dedup` flag, defaulting on
- Test: `tests/test_claim_identity.py`

**Interfaces:**
- Consumes: `claim` rows (task 03), `claim_evidence` rows (task 04), `parse_quantity()` (task 02)
- Produces: `canonical_claim_id` links — consumed by task 08 display, and by Phase 4 so a subscription tracks one canonical claim rather than many duplicates

**Ordering constraint:**
- The prefilter is mandatory and non-negotiable: it is what keeps dedup cost linear rather than
  quadratic in LLM calls at the 1,000-paper ceiling. The call-count test enforces the ordering.
- Numeric comparison uses `object_value` and `unit` from task 02, so `1%` and `0.01` compare
  as equal quantities rather than differing strings

## Out of scope

No embedding or vector similarity for matching — prefilter plus LLM comparison only. No
merging of methods, results, datasets, or metrics; claims only in this task. No scoring.
