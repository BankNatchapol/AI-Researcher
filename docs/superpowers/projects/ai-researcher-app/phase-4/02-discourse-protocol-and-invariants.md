---
title: Define the DiscourseSource protocol and enforce channel separation
order: 2
depends_on_task: 01-discourse-schema
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 6, 7
skills: test-driven-development, verification-before-completion
---

## Goal

Community sources have their own protocol and registry, structurally distinct from
`EvidenceSource`, with the separation from scoring enforced by tests that fail the build.

## Acceptance Criteria

- [ ] `DiscourseSource` is defined in `discourse/base.py` with `poll(since)` and `link_targets(item)`
- [ ] `ai_researcher.discourse.registry.get(name)` returns a registered adapter and raises a named error for an unknown name
- [ ] `uv run pytest tests/test_channel_separation.py` exits 0, asserting `DiscourseSource` and `EvidenceSource` share no base class and that no module under `scoring/` imports anything from `discourse/`
- [ ] The same test asserts no code path writes a discourse-derived value into `claim_score`
- [ ] `uv run pytest tests/test_discourse_registry.py` exits 0

## Implementation notes

**Files:**
- Create: `src/ai_researcher/discourse/__init__.py`
- Create: `src/ai_researcher/discourse/base.py` — `DiscourseSource` protocol plus the `DiscourseItem` dataclass; deliberately does **not** subclass or share types with `sources/base.py`
- Create: `src/ai_researcher/discourse/registry.py` — separate registry from `sources/registry.py`
- Test: `tests/test_channel_separation.py` — AST-level import-boundary checks
- Test: `tests/test_discourse_registry.py`

**Interfaces:**
- Consumes: `discourse_source` table (task 01)
- Produces: the `DiscourseSource` protocol and registry — implemented by tasks 03, 04, 12 and driven by task 08's sweep

**Why two registries rather than one:** a shared registry would make it trivially easy for a
future change to feed attention data into scoring. Two protocols with no common base means
the type system, not a comment, keeps the channels apart. This complements the score
separation test built in Phase 3 task 07.

## Out of scope

No adapter implementations — tasks 03, 04, 12. No polling or sweeps. No changes to
`EvidenceSource`; the two protocols evolve independently and must not be unified.
