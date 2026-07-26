---
title: Expose claims through the CLI and MCP with both scores shown separately
order: 8
depends_on_task: 07-quality-rubric-and-invariants
project: ai-researcher-app
phase: 3
depends_on_phase: 2
design: docs/superpowers/projects/ai-researcher-app/phase-3/PHASE.md
plan_task: Requirements 20, 21, 22
skills: test-driven-development, verification-before-completion
---

## Goal

A researcher can browse extracted claims and inspect the evidence behind any one of them,
with confidence and evidence quality always displayed as two distinct numbers.

## Acceptance Criteria

- [ ] `uv run airesearch claims --scope <name>` lists claims with `confidence` and `evidence_quality` in separate columns
- [ ] `--type`, `--min-confidence`, and `--min-quality` filter the list, and `--min-quality 70` returns only claims scoring at least 70 on evidence quality regardless of confidence
- [ ] `uv run airesearch claim show <id>` prints the claim, both scores with their contributing factors, and every linked evidence node with stance and verbatim rationale
- [ ] MCP tools `list_claims`, `get_claim`, and `find_claim_evidence` return JSON where `confidence` and `evidence_quality` are distinct top-level fields
- [ ] `uv run pytest tests/test_claims_surface.py` exits 0, including a test asserting no rendered output contains a combined or averaged score

## Implementation notes

**Files:**
- Create: `src/ai_researcher/claims/__init__.py`
- Create: `src/ai_researcher/claims/query.py` — `list_claims(filters)` and `get_claim(id)`, returning claims with both scores and evidence
- Create: `src/ai_researcher/claims/render.py` — terminal rendering with two score columns
- Modify: `src/ai_researcher/cli.py` — register the `claims` command and the `claim show` subcommand
- Modify: `src/ai_researcher/mcp/server.py` — add the three claim tools
- Test: `tests/test_claims_surface.py`

**Interfaces:**
- Consumes: `claim`, `claim_evidence`, `claim_score` rows (tasks 01–07); `render_citation()` from Phase 2 task 06 for node display
- Produces: the claims surface — extended by Phase 4 with subscription commands targeting a claim ID

**Display constraint:**
- The two scores appear as separate labelled columns, never side by side under one heading
  that implies they combine. Canonical claims display their replication count, since that is
  what makes a claim's evidence quality legible at a glance.

## Out of scope

No claim editing or manual correction. No subscriptions or monitoring — Phase 4. No web UI.
No export to bibliography or citation-manager formats.
