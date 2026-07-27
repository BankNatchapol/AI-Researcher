# Running the autonomous loop on Codex

[`scripts/supersaiyan-codex-run.sh`](../../scripts/supersaiyan-codex-run.sh) is a fork of
SuperSaiyan's `super-board-run.sh` that dispatches `codex exec` workers instead of
`claude -p`. Use it when Codex owns the phase being built (phases 1–2 per `AGENTS.md`).

## Why a fork was needed

`supersaiyan run` is not a set of instructions — it is an executor. Upstream's runner
dispatches one `claude -p` worker per lane into its own git worktree. Bridging the *skill*
into Codex (via MCP or otherwise) would leave the dispatch line still calling `claude -p`,
so Codex would end up supervising Claude Code doing the work.

Only four things differ from upstream. Everything else — board polling, atomic assignee
claiming, inflight locks, the lane-zombie watchdog, the GraphQL rate-limit guard, the
per-tick project cache — is inherited unchanged, because none of it is tool-specific.

1. `dispatch_lane()` calls `codex exec` instead of `claude -p`
2. Lane prompts point at `$CODEX_SKILLS_DIR`, since Codex cannot read `.claude/skills/`
3. Orphan detection matches the codex worker pattern — **and** refuses to start if a
   Claude-side runner is live, since two runners would race on assignee claims and produce
   duplicate PRs
4. Sandbox mode is configurable

## Prerequisites

```bash
codex --version                 # 0.142.4 verified
ls ~/.codex/skills/supersaiyan  # skills must be installed (symlinked)
```

The nine SuperSaiyan skills are symlinked into `~/.codex/skills/`, pointing at the Claude
plugin cache. Codex CLI supports the same `SKILL.md` format natively, so no MCP bridge is
involved. If you ever remove the SuperSaiyan marketplace from Claude Code, these symlinks
break — re-run the install, or copy instead of symlinking.

## Usage

```bash
# from the repo root
nohup scripts/supersaiyan-codex-run.sh ai-researcher-codex &

# watch it
tail -f .claude/supersaiyan/codex-logs/issue-*-build.log
```

Stop it with `pkill -f 'codex exec .*lane worker for SuperSaiyan'`.

## The setting that makes or breaks this

Lane workers must run `git push`, `gh issue edit`, and `gh pr create` — all of which need
network. **Codex sandboxes deny network by default.**

| `CODEX_SANDBOX` | Behaviour |
|---|---|
| `workspace-write` (default) | Writes limited to the repo. Requests network via `sandbox_workspace_write.network_access=true`. **On macOS the seatbelt sandbox is documented to sometimes ignore this** ([openai/codex#10390](https://github.com/openai/codex/issues/10390)). If workers fail on push or `gh`, this is the cause. |
| `danger-full-access` | No sandbox. What actually works on macOS today, and the closest equivalent to how `claude -p` runs upstream. Every worker can do anything your shell can. |

The runner prints a warning at startup when it detects macOS + `workspace-write`.

```bash
CODEX_SANDBOX=danger-full-access nohup scripts/supersaiyan-codex-run.sh ai-researcher-codex &
```

For repositories whose task files form a strict predecessor chain, set
`"strict_task_chain": true` in the board config. The dispatcher will then keep
the lowest-numbered unfinished issue in control of the pipeline through Build,
QA, and Review. It will not start the next Ready issue until that issue reaches
Done (or Skipped).

Board polling is event-driven, not timer-driven. While any lane has a live
worker, the dispatcher only checks local process liveness (`kill -0`) every
`POLL_SECONDS` — zero GitHub calls, so this can be small (default 5) with no
rate-limit cost. The moment a worker exits, it fetches the board and dispatches
immediately, instead of waiting for a fixed interval to elapse. Only when every
lane is idle and nothing was dispatchable does it fall back to a periodic
`IDLE_RECHECK_SECONDS` (default 60) recheck, since there's no local signal left
to react to.

This replaces an earlier fixed-tick design. That design once drained GitHub's
GraphQL quota to zero during a real run, forcing a ~30 minute recovery sleep —
the event-driven model removes the busy-time polling that caused it, while
actually reducing dead time between stages (previously bounded by the tick
interval, now bounded by `POLL_SECONDS`).

Lane prompts forbid workers from calling the expensive full-board discovery
commands; workers operate only on their assigned issue and PR and trust
successful status mutations instead of re-fetching the project.

Choose `danger-full-access` deliberately, not by default. It removes the sandbox for every
worker the loop spawns, and those workers act on GitHub with your credentials.

## Other environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CODEX_SANDBOX` | `workspace-write` | Sandbox policy (see above) |
| `CODEX_SKILLS_DIR` | `~/.codex/skills` | Where workers read SuperSaiyan skills from |
| `CODEX_MODEL` | Codex config default | Per-run model override |
| `CODEX_WORKER_LOG_DIR` | `.claude/supersaiyan/codex-logs` | Per-worker logs and last messages |
| `poll_seconds` (config) | `5` | Local-only liveness poll interval while a lane is busy — free, no GitHub calls |
| `idle_recheck_seconds` (config) | `60` | Board recheck interval only when every lane is idle and nothing was dispatchable |

## What is proven and what is not

**Proven end to end.** All 11 Phase 1 issues drained through this dispatcher
(`danger-full-access`, `gpt-5.6-sol` at `high` reasoning): `Ready → Building → QA → Review →
Done`, real PRs opened and squash-merged, `git push`/`gh` working under the unsandboxed
setting. `super-build`/`super-qa`/`super-review` work correctly even though they were
written describing Claude Code's behaviours — the lane prompt's override ("perform the work
directly instead of delegating it") held up in practice, not just in theory.

One real defect surfaced and was fixed during that run: a builder overwrote `.gitignore`
from scratch instead of appending, dropping existing rules. `AGENTS.md`'s
"Editing shared config files" section (append-or-merge only) exists because of this.

**Still worth watching per-phase:** Phase 2 (tree traversal, retrieval quality) is a harder
judgment-call phase than Phase 1's mostly-mechanical scaffolding — a passing test suite
doesn't tell you the retrieval is actually good. Read the eval report, don't just trust the
green checkmark.

**Not yet proven live:** the event-driven poll/idle-recheck timing above replaced the fixed
tick this dispatcher used for Phase 1 and Phase 2 — those 19 issues all ran under the old
timer, not this one. The local liveness-detection mechanism is verified in isolation, and
both dispatcher scripts pass a structural test asserting the busy-wait path never calls
`fetch_project_items`, but the *live* dead-time reduction hasn't been observed end to end on
this dispatcher yet. Watch the first real run's dispatch timestamps.

## Config split — one file per tool

`.claude/supersaiyan/configs/ai-researcher-codex.json` is this dispatcher's own config.
Claude Code and Cursor each have their own (`ai-researcher-claude.json`,
`ai-researcher-cursor.json`) — all three point at the same GitHub Project, but none share a
mutable field, so starting one can't silently flip another's `worker_backend` out from under
it. Always pass the slug explicitly:

```bash
scripts/supersaiyan-codex-run.sh ai-researcher-codex
```

Don't rely on `.claude/supersaiyan/active` for dispatch — it's one shared pointer, fine for
a bare `/supersaiyan status`, but whichever tool set it last wins for anyone who omits the
slug on a `run`/dispatcher command.

## Never run both runners at once

Regardless of config file, every dispatcher targets the same GitHub Project and claims
issues via assignee. Running two at once races on those claims and produces duplicate PRs.
Each script's orphan guard checks for the *other* tool's process name (not its config file),
so it refuses to start if Cursor's or Claude's runner is already live — but don't rely on
the guard as your only safety net; don't start two on purpose.

## What still works from Claude Code

Everything except `run`. `setup`, `new`, `prepare`, `lint`, and `status` are pure
instructions plus `gh` calls and work identically from any tool — including the phase
gating you need, which never touches `worker_backend`:

```
/supersaiyan prepare ai-researcher-app --phase 2
```
