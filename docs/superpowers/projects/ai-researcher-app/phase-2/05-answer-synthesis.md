---
title: Synthesize answers where every statement cites a tree node
order: 5
depends_on_task: 04-budgeted-traversal
project: ai-researcher-app
phase: 2
depends_on_phase: 1
design: docs/superpowers/projects/ai-researcher-app/phase-2/PHASE.md
plan_task: Requirements 12, 13, 14, 15
skills: test-driven-development, verification-before-completion
---

## Goal

Retrieved nodes become an answer in which every factual statement is attributed to specific
nodes with real section paths and page ranges — and thin evidence produces an honest refusal
rather than confident prose.

## Acceptance Criteria

- [ ] Every factual statement in a synthesized answer carries at least one node ID attribution, asserted by a test that fails if any statement is unattributed
- [ ] Citations render as paper title, section path, page range, and the paper's DOI or arXiv ID
- [ ] A traversal returning fewer than 2 supporting nodes produces an explicit insufficient-evidence response with no synthesized answer
- [ ] A result with `stopped_reason = 'budget_exhausted'` is returned with a budget-limited flag set on the response object
- [ ] `uv run pytest tests/test_synthesis.py` exits 0, covering full synthesis, the insufficient-evidence path, and the budget-limited path

## Implementation notes

**Files:**
- Create: `src/ai_researcher/answer/__init__.py`
- Create: `src/ai_researcher/answer/synthesize.py` — `synthesize(question, traversal_result) -> Answer`; prompts for statement-level attribution and validates every returned statement against the supplied node IDs
- Create: `src/ai_researcher/answer/citation.py` — `render_citation(node) -> Citation`; resolves node → paper, section path, pages, identifier
- Test: `tests/test_synthesis.py`

**Interfaces:**
- Consumes: `TraversalResult` from task 04; `tree_node` and `paper` rows
- Produces: the `Answer` object (answer text, `list[Citation]`, `budget_limited` flag, `insufficient_evidence` flag) — consumed by task 06 CLI, task 07 MCP, task 08 eval

**Validation notes:**
- Any statement the model returns citing a node ID that was not in the traversal result is rejected and the answer regenerated once; a second failure returns insufficient evidence
- This validation is the mechanism enforcing PROJECT.md's passage-anchor invariant at the answer layer

## Out of scope

No CLI or MCP surface — tasks 06 and 07. No claim extraction or scoring; an `Answer` is
transient and is not persisted as structured claims. No multi-turn conversation or follow-up
question handling.
