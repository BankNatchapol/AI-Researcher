@AGENTS.md

# Claude Code additions

`AGENTS.md` above is the source of truth for this repo and is shared with Codex and Cursor.
Everything below is Claude-specific and must not contradict it.

## SuperSaiyan pipeline paths

| Artifact | Path |
|----------|------|
| Project guide | `docs/superpowers/projects/ai-researcher-app/PROJECT.md` |
| Phase specs | `docs/superpowers/projects/ai-researcher-app/phase-N/PHASE.md` |
| Board tasks | `docs/superpowers/projects/ai-researcher-app/phase-N/NN-*.md` |
| Issue map | `docs/superpowers/projects/ai-researcher-app/phase-N/.issue-map.json` |
| Designs | `docs/supersaiyan/designs/<slug>-design.md` |
| Pre-flight | `docs/supersaiyan/pre-flight.md` |
| Eval reports | `docs/supersaiyan/runs/eval-<date>.json` |

When saving design docs from `/office-hours` or similar tools, also save a copy to
`docs/supersaiyan/designs/<name>-design.md`.

## Board state

Config: `.claude/supersaiyan/configs/ai-researcher.json` · Project #6 under `BankNatchapol`

Phases 1–4 are owned by Codex and Cursor and run **manually** (see the phase ownership table
in `AGENTS.md`). The autonomous loop is not driving them.

Consequences:

- `/supersaiyan prepare ai-researcher-app --phase N` still files that phase's issues to
  Ready — useful as a tracker even when another tool does the building.
- `/supersaiyan run` would drain whatever is in Ready with headless `claude -p` workers.
  Do not run it unless the intent really is to hand that phase to Claude Code.
- Nothing moves board cards automatically under manual operation. Cards move by hand or via
  `gh`.

## Verification before claiming completion

A task's acceptance criteria are executable. Run them and read the output before saying a
task is done:

```bash
uv run pytest && uv run ruff check . && uv run ruff format --check .
```

This matters more than usual here: three different tools write code in this repo, so the
executable checks — not instructions — are what actually keep the invariants intact.
