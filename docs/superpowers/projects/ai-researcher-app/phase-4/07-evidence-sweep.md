---
title: Run the evidence sweep over subscribed topics
order: 7
depends_on_task: 06-subscriptions-cli
project: ai-researcher-app
phase: 4
depends_on_phase: 3
design: docs/superpowers/projects/ai-researcher-app/phase-4/PHASE.md
plan_task: Requirements 14, 16, 17
skills: test-driven-development, verification-before-completion
---

## Goal

`airesearch sweep --kind evidence` discovers new papers for subscribed topics and carries each
all the way through ingest, tree building, extraction, evidence linking, and rescoring.

## Acceptance Criteria

- [ ] `uv run airesearch sweep --kind evidence` processes each subscribed scope end to end and writes one `sweep_run` row with `kind = 'evidence'`, `items_found`, and a terminal state
- [ ] A newly discovered paper ends the sweep with a built tree, extracted claims, and linked evidence, asserted by a test against a fixture returning one new paper
- [ ] Re-running immediately with no new upstream content creates zero new papers and exits 0
- [ ] A scope already at the 1,000-paper ceiling stops adding papers and logs a clear line naming the ceiling
- [ ] `uv run pytest tests/test_evidence_sweep.py` exits 0, covering a new-paper run, an empty run, ceiling refusal, and a per-paper failure that does not abort the sweep

## Implementation notes

**Files:**
- Create: `src/ai_researcher/monitor/sweep.py` — for each active topic subscription: `discover` → `ingest_pipeline` → `build_tree` → `extract_paper` → `link_evidence` → rescore
- Modify: `src/ai_researcher/cli.py` — register `sweep` with `--kind`
- Test: `tests/test_evidence_sweep.py`

**Interfaces:**
- Consumes: active topic subscriptions (task 06); `ingest/pipeline.py` (Phase 1 task 10); `trees/build.py` (Phase 2 task 02); `extraction/pipeline.extract_paper()` (Phase 3 task 03); `link_evidence()` (Phase 3 task 04); scorers (Phase 3 tasks 06–07)
- Produces: `sweep_run` rows and newly processed papers — read by task 09 change detection

**Behaviour notes:**
- The sweep reuses Phase 1's ingest pipeline rather than reimplementing discovery, so the
  dedup, ceiling, and resumability guarantees hold identically
- Rescoring covers claims whose replication count changed because a new paper supports them,
  not only newly extracted claims — this is what makes score movement meaningful in digests
- A failure on one scope is recorded and the remaining subscribed scopes still run

## Out of scope

No discourse polling — task 08. No change detection or digests — tasks 09, 10. No scheduling
— task 11. No new evidence source adapters; the sweep uses Phase 1's three.
