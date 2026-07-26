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
nohup scripts/supersaiyan-codex-run.sh ai-researcher &

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
CODEX_SANDBOX=danger-full-access nohup scripts/supersaiyan-codex-run.sh ai-researcher &
```

Choose `danger-full-access` deliberately, not by default. It removes the sandbox for every
worker the loop spawns, and those workers act on GitHub with your credentials.

## Other environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CODEX_SANDBOX` | `workspace-write` | Sandbox policy (see above) |
| `CODEX_SKILLS_DIR` | `~/.codex/skills` | Where workers read SuperSaiyan skills from |
| `CODEX_MODEL` | Codex config default | Per-run model override |
| `CODEX_WORKER_LOG_DIR` | `.claude/supersaiyan/codex-logs` | Per-worker logs and last messages |

## What is proven and what is not

**Proven:** the dispatcher logic is inherited from upstream and unchanged. The fork passes
`bash -n`, and flag assembly was verified across all three configurations.

**Not proven:** the Codex worker path has not been run end to end. `super-build`,
`super-qa`, and `super-review` were written for Claude Code and describe its behaviours —
including instructions to spawn `claude -p` sub-workers, which the lane prompt explicitly
overrides. Expect to iterate on the prompts.

**Run the first one supervised:**

```bash
# one lane, one issue, watch it the whole way
CODEX_MAX_PARALLEL=1 CODEX_SANDBOX=danger-full-access \
  scripts/supersaiyan-codex-run.sh ai-researcher
```

Watch a single issue go `Ready → Building → QA → Review` before trusting it unattended.

## Never run both runners at once

The Claude runner and this one both claim issues via GitHub assignee. Running both races on
those claims and produces duplicate PRs. The startup guard refuses to start if it detects
the other, but do not defeat it.

## What still works from Claude Code

Everything except `run`. `setup`, `new`, `prepare`, `lint`, and `status` are pure
instructions plus `gh` calls and work identically from either tool — including the phase
gating you need:

```
/supersaiyan prepare ai-researcher-app --phase 2
```
