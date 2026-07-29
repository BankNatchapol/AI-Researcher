---
title: Compute evidence quality from a written rubric and enforce score separation
order: 7
depends_on_task: 06-confidence-scorer
project: ai-researcher-app
phase: 3
depends_on_phase: 2
design: docs/superpowers/projects/ai-researcher-app/phase-3/PHASE.md
plan_task: Requirements 16, 17, 18, 19
skills: test-driven-development, verification-before-completion
---

## Goal

Every claim carries a second, independent 0–100 score describing the quality of the
underlying science, computed from a versioned written rubric — and the codebase is
mechanically prevented from ever merging the two scores.

## Acceptance Criteria

- [ ] `score_quality(claim) -> QualityScore` computes a 0–100 value strictly from the factors documented in `src/ai_researcher/scoring/rubric.md`
- [ ] `rubric_version` is stored on every `claim_score` row and changes when the rubric file changes
- [ ] An abstract-only paper's claim scores measurably lower than an otherwise identical full-text claim, asserted by a test
- [ ] `uv run pytest tests/test_score_separation.py` exits 0, failing the build if any module performs arithmetic combining `confidence` and `evidence_quality`, and if `scoring/` imports any discourse module
- [ ] `uv run pytest tests/test_quality.py` exits 0, covering each rubric factor in isolation: full-text versus abstract-only, peer-reviewed versus preprint, direct versus inferred, recency, and replication count

## Implementation notes

**Files:**
- Create: `src/ai_researcher/scoring/rubric.md` — the human-readable rubric with a version header and each factor's weight and justification
- Create: `src/ai_researcher/scoring/quality.py` — `score_quality(claim)`; reads factors from paper metadata and evidence, returns the score plus contributing factors
- Test: `tests/test_quality.py`
- Test: `tests/test_score_separation.py` — walks `src/ai_researcher/`, parses the AST for expressions combining both score fields, and asserts `scoring/` has no import from a discourse module

**Interfaces:**
- Consumes: `paper.is_preprint`, `paper.venue`, `paper.oa_status`, `paper.parse_status`, `paper.published_at` (Phase 1); `claim_evidence` rows (task 04); `canonical_claim_id` for replication count (task 05)
- Produces: `claim_score.evidence_quality` — displayed separately by task 08, tracked over time by Phase 4

**Rubric factors (all sourced from real columns, none invented):**
- full text versus abstract-only — `parse_status`
- peer-reviewed versus preprint — `is_preprint`, `venue`
- direct statement versus inferred — `claim_evidence.is_direct`, set by the batched stance
  call in evidence linking (task 04); the quality scorer only reads the stored flag
- recency — `published_at`
- replication — count of distinct papers with supporting evidence for the canonical claim

**Dropped from v1:** table/figure-backed versus narrative-only. GROBID's TEI parsing (Phase 1)
does not preserve any figure/table distinction, so there is no real signal to score this
factor against — figure and table grounding is explicitly out of scope for v1 (`AGENTS.md`).
Storing a column with no real signal behind it would misrepresent itself as evidence-quality
data. See `src/ai_researcher/scoring/rubric.md`'s "Out of scope for v1" section.

**Why the separation test is a build gate:** PROJECT.md makes the two-score split a hard
invariant. A convention would erode; an AST-level test that fails CI cannot.

## Out of scope

No confidence scoring — task 06. No single combined score, ever, under any name. No
community or attention input; the discourse channel does not exist until Phase 4 and is
permanently barred from scoring.
