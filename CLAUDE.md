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

Project #6 under `BankNatchapol`. Each tool has its own config file — they all point at the
same board, but never share a mutable field, so starting one can't silently reconfigure
another:

| Config | Tool | `worker_backend` |
|--------|------|------------------|
| `.claude/supersaiyan/configs/ai-researcher-claude.json` | Claude Code | `workflow` |
| `.claude/supersaiyan/configs/ai-researcher-codex.json` | Codex | `codex-exec` |
| `.claude/supersaiyan/configs/ai-researcher-cursor.json` | Cursor | `cursor-agent` |

`.claude/supersaiyan/configs/ai-researcher.json` (no suffix) still exists — it's a read-only
template a Cursor-side test fixture depends on. Don't dispatch against it and don't delete it.

Phases 1–4 are owned by Codex and Cursor (see the phase ownership table in `AGENTS.md`).
They run **manually** unless you deliberately start a board dispatcher.

Consequences:

- `/supersaiyan prepare ai-researcher-app --phase N` still files that phase's issues to
  Ready — useful as a tracker even when another tool does the building.
- `/supersaiyan run ai-researcher-claude` drains Ready with headless `claude -p` (or
  workflow) workers.
- For Cursor subscription workers: `scripts/supersaiyan-cursor-run.sh ai-researcher-cursor`
  — see `docs/supersaiyan/cursor-runner.md`.
- For Codex workers: `scripts/supersaiyan-codex-run.sh ai-researcher-codex`
  — see `docs/supersaiyan/codex-runner.md`.
- Always pass the slug explicitly. `.claude/supersaiyan/active` is a single shared pointer
  (gitignored, currently `ai-researcher-codex`) — fine for a bare `/supersaiyan status`, but
  relying on it for `run`/dispatcher scripts means whichever tool set it last wins for
  everyone who omits the slug.
- Never run two dispatchers at once regardless of config file — they all target the same
  GitHub Project and race on assignee claims. Each script's orphan guard checks for the
  *other* runner's process name, not its config, so this holds across all three configs.
- Under pure manual operation, nothing moves board cards automatically. Cards move by
  hand or via `gh`.

## Verification before claiming completion

A task's acceptance criteria are executable. Run them and read the output before saying a
task is done:

```bash
uv run pytest && uv run ruff check . && uv run ruff format --check .
```

This matters more than usual here: three different tools write code in this repo, so the
executable checks — not instructions — are what actually keep the invariants intact.
