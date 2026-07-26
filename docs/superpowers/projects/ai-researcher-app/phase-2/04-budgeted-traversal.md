---
title: Implement budgeted LLM tree traversal with a recorded trace
order: 4
depends_on_task: 03-shortlist-protocol
project: ai-researcher-app
phase: 2
depends_on_phase: 1
design: docs/superpowers/projects/ai-researcher-app/phase-2/PHASE.md
plan_task: Requirements 9, 10, 11
skills: test-driven-development, verification-before-completion
---

## Goal

An LLM walks from shortlisted papers down into their node trees to specific sections, under
an explicit expansion budget, recording every node it opened and why it stopped.

## Acceptance Criteria

- [ ] `traverse(question, scope, max_nodes) -> TraversalResult` returns ranked nodes plus the full expansion trace
- [ ] Every traversal writes exactly one `retrieval_trace` row with `stopped_reason` in `sufficient_evidence`, `budget_exhausted`, or `no_candidates`
- [ ] The node budget defaults to 40, is overridable per call and via config, and traversal never expands more than `max_nodes` — asserted by a test running with `max_nodes=3` against a corpus with many relevant sections
- [ ] A question with no shortlisted candidates returns an empty result with `stopped_reason = 'no_candidates'` and does not call the LLM for expansion
- [ ] `uv run pytest tests/test_traversal.py` exits 0 with the LLM mocked

## Implementation notes

**Files:**
- Create: `src/ai_researcher/retrieval/traverse.py` — `traverse()`; starts from `shortlist()`, expands nodes by LLM reasoning over titles and summaries, ranks selected nodes
- Create: `src/ai_researcher/retrieval/budget.py` — expansion counter and stopping rule; stops early when the model reports sufficient evidence
- Test: `tests/test_traversal.py`

**Interfaces:**
- Consumes: `shortlist()` from task 03; `tree_node` rows from task 02; `llm.gateway.complete(job="traversal")`; `retrieval_trace` from task 01
- Produces: `TraversalResult` (ranked nodes with section path and page range) and `retrieval_trace` rows — consumed by task 05 synthesis, task 08 eval, and Phase 3 as a confidence-score input

**Behaviour notes:**
- The trace records nodes in expansion order so a human can read the retrieval path
- Ranking is by the model's stated relevance judgement, not by any similarity score
- The budget counts node expansions across all candidate papers for one question, not per paper

## Out of scope

No answer text generation — task 05 owns synthesis. No citation rendering. No claim
extraction. No caching of traversal results between questions.
