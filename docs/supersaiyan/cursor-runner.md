# Running the autonomous loop on Cursor Agent CLI

[`scripts/supersaiyan-cursor-run.sh`](../../scripts/supersaiyan-cursor-run.sh) is a fork of
SuperSaiyan's `super-board-run.sh` (via the Codex edition) that dispatches
`agent -p` workers instead of `claude -p` / `codex exec`. Use it against
`.claude/supersaiyan/configs/ai-researcher-cursor.json` — the dedicated Cursor
board config (`"worker_backend": "cursor-agent"`).

## Why a fork was needed

`supersaiyan run` is not a set of instructions — it is an executor. Upstream's
runner dispatches one `claude -p` worker per lane. The Codex fork calls
`codex exec`. Neither path uses Cursor's subscription-authenticated CLI.

Only the worker spawn differs from the Codex fork. Board polling, atomic
assignee claiming, inflight locks, the lane-zombie watchdog, the GraphQL
rate-limit guard, and `strict_task_chain` are inherited unchanged.

1. `dispatch_lane()` calls `agent -p --force --trust` instead of `codex exec`
2. Lane prompts point at `$CURSOR_SKILLS_DIR` with absolute skill paths
3. Orphan detection matches Cursor workers — and refuses to start if a Codex
   or Claude runner is live
4. Auth is **subscription login** (`agent login`), not `CURSOR_API_KEY`

## Prerequisites

```bash
# Install Cursor Agent CLI
curl https://cursor.com/install -fsS | bash
agent --version

# Subscription auth (browser login — do this once)
agent login
agent status          # must show authenticated

# Symlink SuperSaiyan skills where the runner can resolve them
scripts/setup-cursor-skills.sh
ls ~/.cursor/skills
```

If `~/.codex/skills` already has those symlinks, the runner falls back to that
directory automatically — you can skip the `~/.cursor/skills` setup.

Confirm the model id your account can use **after** `agent login`:

```bash
agent models
```

Set the chosen id in `.claude/supersaiyan/configs/ai-researcher-cursor.json` under
`cursor.model` (repo default: `cursor-grok-4.5-high` — must match an id from
`agent models` exactly; `grok-4-5` is not valid). Override per run with
`CURSOR_MODEL=...`.

Smoke check without draining the board: with no login, the runner must exit 77
and print the `agent login` hint. After login, start supervised:

```bash
CURSOR_MAX_PARALLEL=1 scripts/supersaiyan-cursor-run.sh ai-researcher-cursor
```

## Config — one file per tool

`ai-researcher-cursor.json` is this dispatcher's own config, separate from
`ai-researcher-codex.json` and `ai-researcher-claude.json`. All three point at
the same GitHub Project (#6), but none share a mutable field — starting one
can no longer silently flip another's `worker_backend`. That used to be a
single shared `ai-researcher.json`; the split exists precisely because two
tools fighting over one `worker_backend` value caused a real incident.

```json
"worker_backend": "cursor-agent",
"cursor": {
  "model": "cursor-grok-4.5-high"
}
```

To use Codex instead, run `scripts/supersaiyan-codex-run.sh ai-researcher-codex`
— no config edit needed. Never run both dispatchers at once regardless of
which config file each reads (see below).

## Usage

```bash
# from the repo root — supervised first run (one worker at a time)
CURSOR_MAX_PARALLEL=1 scripts/supersaiyan-cursor-run.sh ai-researcher-cursor

# unattended later
nohup scripts/supersaiyan-cursor-run.sh ai-researcher-cursor &

# watch it
scripts/watch-run.sh follow
# or
tail -f .claude/supersaiyan/cursor-logs/issue-*-build.log
```

Stop workers with:

```bash
pkill -f 'agent.*lane worker for SuperSaiyan'
pkill -f 'supersaiyan-cursor-run.sh'
```

## Auth: subscription, not API key

| Method | Intended? |
|---|---|
| `agent login` (stored local session) | **Yes** — matches `claude -p` / `codex exec` subscription style |
| `CURSOR_API_KEY` | **No** — CI escape hatch only; the runner warns if it is set |

The runner refuses to start when `agent status` does not show an authenticated
session. Do not treat the SDK (`@cursor/sdk`) as the worker path — it requires
an API key.

## Sandbox

| `CURSOR_SANDBOX` | Behaviour |
|---|---|
| `disabled` (default) | Workers can `git push` / `gh`. Closest to Codex `danger-full-access`. |
| `enabled` | Sandboxed; push/gh may fail. |

```bash
CURSOR_SANDBOX=disabled CURSOR_MAX_PARALLEL=1 \
  scripts/supersaiyan-cursor-run.sh ai-researcher-cursor
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CURSOR_MODEL` | config `cursor.model` | Model id from `agent models` |
| `CURSOR_SANDBOX` | `disabled` | Agent CLI sandbox mode |
| `CURSOR_SKILLS_DIR` | `~/.cursor/skills` or `~/.codex/skills` | Absolute skill roots in prompts |
| `CURSOR_WORKER_LOG_DIR` | `.claude/supersaiyan/cursor-logs` | Per-worker logs |
| `CURSOR_MAX_PARALLEL` | config `max_workers` | Cap concurrent lane workers |
| `REPO_ROOT` | `pwd` | `--workspace` passed to `agent` |
| `poll_seconds` (config) | `5` | Local-only liveness poll interval while a lane is busy — free, no GitHub calls |
| `idle_recheck_seconds` (config) | `60` | Board recheck interval only when every lane is idle and nothing was dispatchable |

## Board polling is event-driven, not timer-driven

While any lane has a live worker, the dispatcher checks only local process
liveness (`kill -0`) every `poll_seconds` — zero GitHub calls. The moment a
worker exits, it fetches the board and dispatches immediately, rather than
waiting out a fixed interval. Only when every lane is idle and nothing was
dispatchable does it fall back to `idle_recheck_seconds`, since there's no
local signal left to react to.

This replaces an earlier fixed-tick design that once drained GitHub's GraphQL
quota to zero during a real run (see `AGENTS.md` / codex-runner.md for the
incident). The event-driven model removes the busy-time polling that caused
it, while cutting dead time between stages from the old tick interval down to
`poll_seconds`.

## What is proven and what is not

**Proven end to end.** Issue #42 (Phase 3, `CURSOR_MAX_PARALLEL=1`,
`cursor-grok-4.5-high`) drained through this dispatcher: `Ready → Building →
QA (pass v1) → Review (truth gate 94/100) → Done`, a real PR opened and
squash-merged, `git push`/`gh` working under `--sandbox disabled`. Verified
independently afterward — pulled the merge, re-ran migrations and the full
test suite (161 passed) against live Postgres/GROBID, not just trusted the
worker's own summary.

**Not yet proven live:** the event-driven poll/idle-recheck timing (replacing
the old fixed tick) is verified in isolation — the local liveness-detection
mechanism was tested standalone, and both dispatcher scripts pass a structural
test asserting the busy-wait path never calls `fetch_project_items` — but issue
#42's run predates this change, so the *live* dead-time reduction hasn't been
observed end to end yet. Watch the first real run's dispatch timestamps; they
should land seconds after a worker exits, not up to 10 minutes later.

**Before unattended drain:** unstick any thrashing card (e.g. issue #8 / PR #22
review-thread loops), sync local `main`, and clear stale
`.claude/supersaiyan/inflight/` locks.

## Never run both runners at once

The Claude, Codex, and Cursor runners all claim issues via GitHub assignee, against the
same GitHub Project regardless of which config file each reads. Running any two races those
claims and produces duplicate PRs. Startup guards refuse to start when a peer is detected
(matched by process name, not config file) — do not defeat them.

## What still works from Claude Code / Cursor chat

Everything except the Claude-native `run` backend. `setup`, `new`, `prepare`,
`lint`, and `status` are pure instructions plus `gh` and work from either tool.
To drain the board with Cursor models, use this script — not `/supersaiyan run`
inside Claude Code.
