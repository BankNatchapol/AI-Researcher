---
title: Render temporal digests with evidence and attention kept apart
order: 10
depends_on_task: 09-change-detection
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 19, 20, 21, 25
skills: test-driven-development, verification-before-completion
---

## Goal

A readable markdown digest reports what changed over a time window, with scholarly evidence
and community attention in two clearly labelled sections that never blur together.

## Acceptance Criteria

- [ ] `uv run airesearch digest --since <date>` writes `docs/supersaiyan/runs/digest-<date>.md` and prints the same content to stdout
- [ ] The digest contains exactly two top-level sections, "Evidence" and "Community attention", asserted by a test on both headers
- [ ] A test asserts no attention figure — score, upvote count, or comment count — appears anywhere inside the Evidence section
- [ ] Score movement renders as separate confidence and evidence-quality before/after pairs, never a blended delta
- [ ] Every community item links back to its original post rather than reproducing its body, and `uv run pytest tests/test_digest.py` exits 0 covering a populated digest, an empty window, and the two separation assertions

## Implementation notes

**Files:**
- Create: `src/ai_researcher/digest/__init__.py`
- Create: `src/ai_researcher/digest/build.py` — `build_digest(since) -> Digest` from a `ChangeSet`
- Create: `src/ai_researcher/digest/render.py` — markdown rendering with the two fixed sections
- Modify: `src/ai_researcher/cli.py` — register `digest` with `--since`
- Test: `tests/test_digest.py`

**Interfaces:**
- Consumes: `ChangeSet` (task 09); `render_citation()` from Phase 2 task 06 for consistent paper references
- Produces: dated markdown digests under `docs/supersaiyan/runs/`

**Rendering rules:**
- The Evidence section covers new papers, new supporting or refuting evidence for subscribed
  claims, stance flips, and score movement
- The Community attention section covers new mentions with counts and links, and states
  plainly that attention is not evidence of validity
- An empty window produces a digest saying nothing changed rather than an empty file, so the
  absence of change is itself legible
- Content is linked, never reproduced in full, consistent with the `use=reference` signal
  recorded in PROJECT.md risk 5

## Out of scope

No email, Telegram, or push delivery — digests are files and stdout in v1. No HTML or PDF
rendering. No scheduling — task 11. No editorializing about what changes mean.
