---
title: Link claims to supporting and refuting evidence with quoted rationale
order: 4
depends_on_task: 03-extraction-pipeline
project: ai-researcher-app
phase: 3
depends_on_phase: 2
design: docs/superpowers/projects/ai-researcher-app/phase-3/PHASE.md
plan_task: Requirements 11, 12
skills: test-driven-development, verification-before-completion
---

## Goal

Each claim is connected to the nodes that support, refute, or merely mention it — including
nodes in other papers — with a verbatim quote making every link auditable.

## Acceptance Criteria

- [ ] `link_evidence(claim) -> list[ClaimEvidence]` finds candidate nodes using Phase 2 traversal and assigns each a stance of `supports`, `refutes`, or `mentions`, plus an `is_direct` boolean classified in the same call (consumed later by task 07's evidence-quality rubric)
- [ ] Evidence links include nodes from papers other than the claim's origin paper, asserted by a test with a two-paper fixture where one refutes the other
- [ ] Every `claim_evidence` row stores `rationale_text` quoted verbatim from the node's `body_text`, not paraphrased
- [ ] A rationale that does not appear verbatim in the referenced node is rejected and the link is not persisted
- [ ] Stance classification is **batched**: all candidate nodes for one claim are classified in a single gateway call, asserted by a test that counts calls and fails if the count scales with node count
- [ ] `uv run pytest tests/test_evidence_linking.py` exits 0 with the LLM mocked, covering supporting, refuting, mentioning, cross-paper, and rejected-rationale cases

## Implementation notes

**Files:**
- Create: `src/ai_researcher/evidence/__init__.py`
- Create: `src/ai_researcher/evidence/link.py` — `link_evidence(claim)`; builds a query from the claim's `normalized_text`, calls `traverse()`, classifies stance per node via `llm.gateway.complete(job="stance")`, verifies the quote
- Modify: `src/ai_researcher/cli.py` — extend `extract` with a `--link-evidence` flag, defaulting on
- Test: `tests/test_evidence_linking.py`

**Interfaces:**
- Consumes: `claim` rows (task 03), `traverse()` (Phase 2 task 04), `tree_node` rows, `claim_evidence` table (task 01)
- Produces: `claim_evidence` rows — consumed by task 05 dedup, tasks 06–07 scoring, task 08 display, and Phase 4 change detection

**Batching is mandatory, not an optimization.** Model access is a CLI subprocess on a
subscription (PROJECT.md risk 7): every call costs seconds of startup and counts against a
rate cap. One call per claim×node pair at the 1,000-paper ceiling is 10,000+ invocations and
20+ hours. Classify every candidate node for a claim in one call, returning a list of
`(node_id, stance, rationale)`. The call-count test is what keeps this true as the code changes.

**Verification notes:**
- The verbatim check is a plain substring comparison after whitespace normalization, so it is
  cheap and deterministic — no model judges whether the quote is faithful
- Refuting evidence is as important as supporting evidence; the stance prompt must not be
  biased toward confirmation, and the fixture test asserts a genuine refutation is found

## Out of scope

No claim merging or canonicalization — task 05. No scoring. No citation-intent taxonomy
beyond the three stances. No use of community or discourse data; that channel does not exist
until Phase 4 and may never inform evidence.
