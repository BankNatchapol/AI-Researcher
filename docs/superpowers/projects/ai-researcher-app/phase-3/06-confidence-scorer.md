---
title: Compute the pipeline confidence score
order: 6
depends_on_task: 05-claim-identity-dedup
project: ai-researcher-app
phase: 3
depends_on_phase: 2
design: docs/superpowers/projects/ai-researcher-app/phase-3/PHASE.md
plan_task: Requirements 15
skills: test-driven-development, verification-before-completion
---

## Goal

Every claim carries a 0–100 score answering "how much do I trust that the pipeline read this
correctly?", with the contributing factors recorded so the number is explainable.

## Acceptance Criteria

- [ ] `score_confidence(claim) -> ConfidenceScore` returns a 0–100 value plus the contributing factors
- [ ] The score combines: number of independent supporting nodes, verbatim overlap between claim text and node body, self-consistency across repeated extraction, the retrieval `stopped_reason`, and schema validation cleanliness
- [ ] A claim retrieved with `stopped_reason = 'budget_exhausted'` scores strictly lower than an identical claim retrieved with `sufficient_evidence`, asserted by a test
- [ ] Scores are written to `claim_score.confidence`, leaving `evidence_quality` to task 07
- [ ] `uv run pytest tests/test_confidence.py` exits 0, covering each factor's effect in isolation and the budget-exhausted comparison

## Implementation notes

**Files:**
- Create: `src/ai_researcher/scoring/__init__.py`
- Create: `src/ai_researcher/scoring/confidence.py` — `score_confidence(claim)`; each factor contributes a documented weight, and the returned object names every factor and its contribution
- Modify: `src/ai_researcher/cli.py` — extend `extract` with a `--score` flag, defaulting on
- Test: `tests/test_confidence.py`

**Interfaces:**
- Consumes: `claim` and `claim_evidence` rows (tasks 03–04), `retrieval_trace` rows (Phase 2 task 01), validation outcomes (task 02)
- Produces: `claim_score.confidence` — displayed by task 08, tracked over time by Phase 4 digests

**Boundary constraint:**
- This score describes the **pipeline**, not the science. Peer-review status, preprint status,
  recency, and replication are evidence-quality inputs and belong to task 07 — they must not
  appear here. Keeping the two independent is what makes the separation meaningful.

## Out of scope

No evidence-quality scoring — task 07. No blending of the two scores anywhere. No community
or discourse input of any kind. No calibration study against ground truth; task 09 measures
extraction quality separately.
