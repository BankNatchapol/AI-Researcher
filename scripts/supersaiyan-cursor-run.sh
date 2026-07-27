#!/usr/bin/env bash
# supersaiyan-cursor-run.sh — headless autonomous runner, Cursor Agent edition.
#
# FORK of SuperSaiyan's scripts/super-board-run.sh (via the Codex fork).
# Dispatches `agent -p` workers per lane instead of `claude -p` / `codex exec`.
# Everything else — board polling, assignee claiming, inflight locks, zombie
# watchdog, rate-limit guard — is unchanged and tool-agnostic.
#
# Spawned as `nohup scripts/supersaiyan-cursor-run.sh <config-slug> &`.
# Pure shell while-loop. Holds NO agent session state — re-reads GitHub only when a lane frees up or the idle recheck fires.
#
# ── What differs from the Codex / Claude runners ────────────────────────────
#   1. dispatch_lane() calls `agent -p --force --trust` instead of
#      `codex exec` / `claude -p`.
#   2. Lane prompts point at $CURSOR_SKILLS_DIR (absolute paths), because the
#      Cursor CLI does not auto-load Claude Code plugin skills.
#   3. Orphan detection matches the Cursor worker pattern — and refuses to
#      start if a Codex or Claude runner is live (assignee-claim races).
#   4. Auth is subscription-based via `agent login` (local stored credentials).
#      CURSOR_API_KEY is NOT required and is not the intended path.
#
# ── Auth ────────────────────────────────────────────────────────────────────
#   agent login          # once; opens browser, stores subscription session
#   agent status         # must report authenticated before this runner starts
#
# ── Sandbox ─────────────────────────────────────────────────────────────────
# Lane workers must run `git push`, `gh issue edit`, and `gh pr create`.
# Default is `--sandbox disabled` (same operational need as Codex
# danger-full-access). Override with CURSOR_SANDBOX=enabled only if you accept
# that push/gh may fail inside the sandbox.
#
# ── Status ──────────────────────────────────────────────────────────────────
# The dispatcher logic is inherited and proven. The Cursor worker path is NOT
# battle-tested: super-build/super-qa/super-review were written for Claude Code.
# Run with CURSOR_MAX_PARALLEL=1 the first time and watch one issue end to end.

set -euo pipefail

# ── Cursor configuration ───────────────────────────────────────────────────
# Skills: prefer ~/.cursor/skills (symlinks to SuperSaiyan skills); fall back
# to the Codex skill install if that already exists.
if [ -z "${CURSOR_SKILLS_DIR:-}" ]; then
  if [ -d "$HOME/.cursor/skills" ]; then
    CURSOR_SKILLS_DIR="$HOME/.cursor/skills"
  elif [ -d "$HOME/.codex/skills" ]; then
    CURSOR_SKILLS_DIR="$HOME/.codex/skills"
  else
    CURSOR_SKILLS_DIR="$HOME/.cursor/skills"
  fi
fi
CURSOR_WORKER_LOG_DIR="${CURSOR_WORKER_LOG_DIR:-.claude/supersaiyan/cursor-logs}"
CURSOR_SANDBOX="${CURSOR_SANDBOX:-disabled}"
CURSOR_MODEL="${CURSOR_MODEL:-}"
REPO_ROOT="${REPO_ROOT:-$(pwd)}"

cursor_flags() {
  # Assemble agent CLI flags. Emitted one per line so callers can read into an array.
  printf '%s\n' "-p"
  printf '%s\n' "--force"
  printf '%s\n' "--trust"
  printf '%s\n' "--sandbox" "$CURSOR_SANDBOX"
  printf '%s\n' "--workspace" "$REPO_ROOT"
  printf '%s\n' "--output-format" "text"
  [ -n "$CURSOR_MODEL" ] && printf '%s\n' "--model" "$CURSOR_MODEL"
  return 0
}

# ───────────────────────────── args + paths ─────────────────────────────
CONFIG_SLUG="${1:-}"
if [ -z "$CONFIG_SLUG" ]; then
  if [ -f .claude/supersaiyan/active ]; then
    CONFIG_SLUG=$(cat .claude/supersaiyan/active)
  else
    echo "usage: $0 <config-slug>  (or set .claude/supersaiyan/active)" >&2
    exit 64
  fi
fi

CONFIG_PATH=".claude/supersaiyan/configs/${CONFIG_SLUG}.json"
if [ ! -f "$CONFIG_PATH" ]; then
  echo "config not found: $CONFIG_PATH" >&2
  exit 66
fi

# ───────────────────────────── config read ─────────────────────────────
VARIANT=$(jq -r '.variant' "$CONFIG_PATH")
PROJECT_OWNER=$(jq -r '.project.owner' "$CONFIG_PATH")
PROJECT_NUMBER=$(jq -r '.project.number' "$CONFIG_PATH")
BASE_BRANCH=$(jq -r '.base_branch // "main"' "$CONFIG_PATH")
HUMAN_APPROVES=$(jq -r '.human_approves_merge // false' "$CONFIG_PATH")
REBUILD_CAP=$(jq -r '.rebuild_cap // 2' "$CONFIG_PATH")
BLOCK_ALERT_PCT=$(jq -r '.block_rate_alert_pct // 30' "$CONFIG_PATH")
MAX_WORKERS=$(jq -r '.max_workers // 3' "$CONFIG_PATH")

# Event-driven dispatch (replaces a fixed tick): while any lane is busy, we
# only ever check LOCAL process liveness (kill -0) -- zero GitHub calls, so
# POLL_SECONDS can be small with no rate-limit cost at all. A real board
# fetch happens the instant a lane's worker exits, not on a timer. Only when
# EVERY lane is idle and nothing was dispatchable do we fall back to a fixed
# recheck interval (IDLE_RECHECK_SECONDS), since there is no local signal
# left to react to and something external (a human unblocking a card, new
# work added) might have changed.
POLL_SECONDS=$(jq -r '.poll_seconds // 5' "$CONFIG_PATH")
IDLE_RECHECK_SECONDS=$(jq -r '.idle_recheck_seconds // 60' "$CONFIG_PATH")
STRICT_TASK_CHAIN=$(jq -r '.strict_task_chain // false' "$CONFIG_PATH")
BOT_LOGIN=$(jq -r '.notifications.bot_identity // .bot_identity // ""' "$CONFIG_PATH")
WORKER_BACKEND=$(jq -r '.worker_backend // "workflow"' "$CONFIG_PATH")

# shellcheck source=scripts/supersaiyan-dispatch-policy.sh
. "$(dirname "$0")/supersaiyan-dispatch-policy.sh"

# Board config supplies model unless already set in the env.
[ -z "$CURSOR_MODEL" ] && CURSOR_MODEL=$(jq -r '.cursor.model // ""' "$CONFIG_PATH")

# One-shot parallel cap for supervised first runs.
if [ -n "${CURSOR_MAX_PARALLEL:-}" ]; then
  MAX_WORKERS="$CURSOR_MAX_PARALLEL"
fi

# This fork dispatches Cursor Agent CLI workers. The config must say so
# explicitly — a board still set to workflow / claude-p / codex-exec must never
# be drained by this dispatcher by accident.
if [ "$WORKER_BACKEND" != "cursor-agent" ]; then
  echo "🛑 board '${CONFIG_SLUG}' is not configured for the Cursor dispatcher (worker_backend=${WORKER_BACKEND})." >&2
  echo "    This fork dispatches \`agent -p\` workers. To use it, set:" >&2
  echo "        \"worker_backend\": \"cursor-agent\"" >&2
  echo "    in .claude/supersaiyan/configs/${CONFIG_SLUG}.json" >&2
  echo "" >&2
  case "$WORKER_BACKEND" in
    workflow)
      echo "    (Current value 'workflow' means Claude Code dynamic workflows — that path" >&2
      echo "     runs in a Claude session via /supersaiyan run, not from this script.)" >&2
      ;;
    codex-exec)
      echo "    (Current value 'codex-exec' means the Codex dispatcher — use" >&2
      echo "     scripts/supersaiyan-codex-run.sh instead.)" >&2
      ;;
  esac
  exit 78
fi

RUN_DATE=$(date +%Y-%m-%d)
RUN_MANIFEST="docs/supersaiyan/runs/${RUN_DATE}-${CONFIG_SLUG}.md"
INFLIGHT_DIR=".claude/supersaiyan/inflight"
BOARD_CACHE="$INFLIGHT_DIR/board-cache.json"
OFFLINE_MARKERS="$INFLIGHT_DIR/offline-dispatches"
mkdir -p "docs/supersaiyan/runs" .worktrees "$INFLIGHT_DIR"

# ───────────────────────────── helpers ─────────────────────────────
log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$RUN_MANIFEST"; }

PROJECT_ITEMS_JSON=""
BOARD_FROM_CACHE=0
fetch_project_items() {
  # One gh call per tick; all column lookups read from this cache.
  local fresh
  if fresh=$(gh project item-list "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json --limit 100 2>/dev/null); then
    PROJECT_ITEMS_JSON="$fresh"
    BOARD_FROM_CACHE=0
    printf '%s\n' "$fresh" >"$BOARD_CACHE"
    rm -rf "$OFFLINE_MARKERS"
  elif [ -s "$BOARD_CACHE" ]; then
    PROJECT_ITEMS_JSON=$(cat "$BOARD_CACHE")
    BOARD_FROM_CACHE=1
    log "⚠ GitHub unavailable — using cached board snapshot (offline dispatch is single-use)"
  else
    PROJECT_ITEMS_JSON='{"items":[]}'
    BOARD_FROM_CACHE=1
    log "🛑 GitHub unavailable and no board cache exists"
  fi
}

column_count() {
  echo "$PROJECT_ITEMS_JSON" | jq --arg col "$1" '[.items[] | select(.status == $col)] | length'
}

top_card_in_column() {
  # Returns the FIRST issue number in $1 with no assignee AND no local in-flight lock.
  local col="$1" issue
  for issue in $(echo "$PROJECT_ITEMS_JSON" | jq -r --arg col "$col" '
        .items[]
        | select(.status == $col and .content.type == "Issue")
        | select((.content.assignees // []) | length == 0)
        | .content.number'); do
    if ! issue_locked "$issue"; then
      echo "$issue"
      return 0
    fi
  done
}

top_build_card() {
  local issue
  if [ "$STRICT_TASK_CHAIN" = "true" ]; then
    issue=$(strict_serial_ready_issue "$PROJECT_ITEMS_JSON")
    if [ "$BOARD_FROM_CACHE" -eq 1 ] && ! offline_dispatch_available "$OFFLINE_MARKERS" "$issue"; then
      return 0
    fi
    if [ -n "$issue" ] && ! issue_locked "$issue"; then
      echo "$issue"
    fi
    return 0
  fi
  top_card_in_column "Ready"
}

read_lock() {
  # Reads $INFLIGHT_DIR/$1 (bash-assignment format) into PID/LANE/STARTED.
  # Sets empty strings if the file is missing or legacy single-PID format.
  local lock="$INFLIGHT_DIR/$1"
  PID=""; LANE=""; STARTED=""
  [ -f "$lock" ] || return 1
  if grep -q '^PID=' "$lock" 2>/dev/null; then
    # shellcheck disable=SC1090
    . "$lock" 2>/dev/null || true
  else
    # Legacy format (pre v1.3.0): single line PID only.
    PID=$(cat "$lock" 2>/dev/null || echo "")
  fi
  return 0
}

issue_locked() {
  # Returns 0 if the issue has a live in-flight lock; cleans stale locks.
  local issue="$1" lock="$INFLIGHT_DIR/$1"
  [ -f "$lock" ] || return 1
  read_lock "$issue"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    return 0
  fi
  rm -f "$lock"
  return 1
}

lane_idle() {
  local pid="${1:-}"
  [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null
}

gh_rate_guard() {
  # Sleep until rate limit resets if GraphQL remaining < 200.
  local payload remaining reset now wait
  payload=$(gh api rate_limit 2>/dev/null || echo '{"resources":{"graphql":{"remaining":5000,"reset":0}}}')
  remaining=$(echo "$payload" | jq -r '.resources.graphql.remaining // 5000')
  if [ "$remaining" -lt 200 ]; then
    if [ -s "$BOARD_CACHE" ]; then
      log "⚠ GraphQL low (${remaining} left) — continuing from cached board snapshot"
      return 0
    fi
    reset=$(echo "$payload" | jq -r '.resources.graphql.reset // 0')
    now=$(date +%s)
    wait=$((reset - now + 10))
    [ "$wait" -lt 60 ] && wait=60
    log "⚠ GraphQL rate limit low (${remaining} left) — sleeping ${wait}s until reset"
    sleep "$wait"
  fi
}

try_claim_assignee() {
  # Atomic claim. Returns 0 if we won the claim, 1 if someone else beat us.
  # Skipped when bot_identity is unset (solo single-user runs rely on local locks only).
  local issue="$1"
  if [ "$BOARD_FROM_CACHE" -eq 1 ]; then
    log "offline claim on #${issue} — using local single-use lock"
    return 0
  fi
  [ -z "$BOT_LOGIN" ] && return 0
  gh issue edit "$issue" --add-assignee "$BOT_LOGIN" >/dev/null 2>&1 || {
    log "claim failed on #${issue} (race or gh api error) — skipping this tick"
    return 1
  }
  return 0
}

require_cursor_subscription_auth() {
  # Subscription login only. Do not require CURSOR_API_KEY.
  local status_out status_json
  if ! command -v agent >/dev/null 2>&1; then
    log "🛑 Cursor Agent CLI ('agent') not found on PATH."
    log "    Install: curl https://cursor.com/install -fsS | bash"
    log "    Then:    agent login && agent status"
    exit 69
  fi

  if [ -n "${CURSOR_API_KEY:-}" ]; then
    log "⚠ CURSOR_API_KEY is set; this runner is designed for subscription login"
    log "  (agent login). Unset CURSOR_API_KEY to use the stored session only."
  fi

  status_json=$(agent status --format json 2>/dev/null || true)
  if [ -n "$status_json" ]; then
    if echo "$status_json" | jq -e '
        (.authenticated == true)
        or (.loggedIn == true)
        or (.logged_in == true)
      ' >/dev/null 2>&1; then
      return 0
    fi
  fi

  status_out=$(agent status 2>&1 || true)
  # Use grep/bash — do not require rg on PATH (many shells don't have it).
  # Negative phrases first — "Not logged in" contains the substring "logged in".
  if printf '%s\n' "$status_out" | grep -Eiq \
      'not logged in|not authenticated|logged out|please log in|unauthenticated|no account|authentication required'; then
    log "🛑 Cursor Agent CLI is not authenticated with a subscription session."
    log "    Run: agent login"
    log "    Then: agent status   # must show you are logged in"
    log "    Auth is subscription-based — do not rely on CURSOR_API_KEY."
    exit 77
  fi
  # Accept "✓ Logged in as user@host" and similar success lines.
  if printf '%s\n' "$status_out" | grep -Eiq 'logged in as|[[:alnum:]._%+-]+@[[:alnum:].-]+'; then
    return 0
  fi

  log "🛑 could not confirm Cursor subscription auth from \`agent status\`."
  log "    Output was:"
  log "    $status_out"
  log "    Run: agent login && agent status"
  exit 77
}

dispatch_lane() {
  # $1 = lane (build|qa|review); $2 = issue number
  local lane="$1" issue="$2" prompt pid
  if issue_locked "$issue"; then
    log "skip dispatch lane=${lane} issue=#${issue} — already locked"
    return 0
  fi
  if ! try_claim_assignee "$issue"; then
    return 0
  fi
  local skill lifecycle
  case "$lane" in
    build)  skill="super-build";  lifecycle="Builder" ;;
    qa)     skill="super-qa";     lifecycle="Tester" ;;
    review) skill="super-review"; lifecycle="Reviewer" ;;
    *) log "unknown lane: $lane"; return 1 ;;
  esac

  # Cursor CLI does not auto-load Claude plugin skills, so the prompt names
  # absolute paths under CURSOR_SKILLS_DIR.
  prompt="You are the ${lifecycle} lane worker for SuperSaiyan issue #${issue}.

Read these files first, in order:
  1. ${CURSOR_SKILLS_DIR}/${skill}/SKILL.md
  2. ${CURSOR_SKILLS_DIR}/super-board/references/run.md  (section: ${lifecycle} lifecycle)
  3. AGENTS.md at the repo root — hard invariants that override anything else
  4. The task file referenced by issue #${issue}

Config: ${CONFIG_PATH}
Repo root: ${REPO_ROOT}

Scope: act on issue #${issue} only. Work in a git worktree under .worktrees/ as
the ${lifecycle} lifecycle describes. Do not pass Cursor CLI --worktree; create
repo-local worktrees yourself. Do not dispatch further workers — you ARE the
worker; the orchestrator loop that spawned you handles all lane scheduling.

GitHub Projects rate-limit rules:
  - Do NOT run \`gh project item-list\`.
  - Do NOT run \`gh project field-list\`.
  - Do NOT run \`gh project view\`.
    The dispatcher already selected and claimed this card.
  - Read only issue #${issue} and its linked PR. Do not scan unrelated issues,
    PRs, project cards, or project fields.
  - Trust successful project item-edit mutations; never re-fetch the board to
    verify a move.
  - Prefer local git data and REST-backed \`gh issue\`/\`gh pr\` operations.

Where those skill files describe running \`claude -p\` or \`codex exec\`, that
step does not apply to you: perform the work directly instead of delegating it.

A task is complete only when every acceptance criterion in its task file passes
by running the stated command and reading the output."

  mkdir -p "$CURSOR_WORKER_LOG_DIR"
  local flags=()
  while IFS= read -r f; do [ -n "$f" ] && flags+=("$f"); done < <(cursor_flags)

  nohup agent "${flags[@]}" \
      "$prompt" \
      >"${CURSOR_WORKER_LOG_DIR}/issue-${issue}-${lane}.log" 2>&1 &
  pid=$!
  # v1.3.0+ lock format: bash-assignment style so stop scripts can source it.
  printf 'PID=%s\nLANE=%s\nSTARTED=%s\n' "$pid" "$lane" "$(date -u +%FT%TZ)" > "$INFLIGHT_DIR/$issue"
  # Also capture the final assistant text when the worker exits (best-effort;
  # the full stream lives in the .log file).
  : >"${CURSOR_WORKER_LOG_DIR}/issue-${issue}-${lane}.last"
  if [ "$BOARD_FROM_CACHE" -eq 1 ]; then
    mark_offline_dispatch "$OFFLINE_MARKERS" "$issue"
  fi
  case "$lane" in
    build) BUILD_PID="$pid"; BUILD_ISSUE="$issue" ;;
    qa) QA_PID="$pid"; QA_ISSUE="$issue" ;;
    review) REVIEW_PID="$pid"; REVIEW_ISSUE="$issue" ;;
  esac
  log "dispatch lane=${lane} issue=#${issue} pid=${pid} claim=${BOT_LOGIN:-local-only}"
}

issue_status() {
  # Lookup issue #$1 in the cached project items; emit its current column name (or empty).
  echo "$PROJECT_ITEMS_JSON" | jq -r --arg n "$1" '
    .items[] | select(.content.number == ($n | tonumber)) | .status' | head -1
}

check_lane_zombie() {
  # $1 = lane name (build|qa|review); $2 = space-separated list of expected source columns.
  local lane="$1" expected="$2" pid="" issue=""
  case "$lane" in
    build)  pid="$BUILD_PID";  issue="$BUILD_ISSUE" ;;
    qa)     pid="$QA_PID";     issue="$QA_ISSUE" ;;
    review) pid="$REVIEW_PID"; issue="$REVIEW_ISSUE" ;;
    *) return 1 ;;
  esac
  [ -z "$pid" ] && return 0
  [ -z "$issue" ] && return 0
  kill -0 "$pid" 2>/dev/null || return 0
  local cur found=0 col
  cur=$(issue_status "$issue")
  [ -z "$cur" ] && return 0
  for col in $expected; do
    [ "$cur" = "$col" ] && found=1
  done
  if [ "$found" -eq 0 ]; then
    log "💀 zombie ${lane} worker on #${issue} (pid=${pid}) — card moved to '${cur}'; killing"
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$INFLIGHT_DIR/$issue"
    [ -n "$BOT_LOGIN" ] && gh issue edit "$issue" --remove-assignee "$BOT_LOGIN" >/dev/null 2>&1 || true
    case "$lane" in
      build)  BUILD_PID="";  BUILD_ISSUE="" ;;
      qa)     QA_PID="";     QA_ISSUE="" ;;
      review) REVIEW_PID=""; REVIEW_ISSUE="" ;;
    esac
  fi
}

sweep_lane_zombies() {
  check_lane_zombie build  "Ready Building"
  check_lane_zombie qa     "QA"
  check_lane_zombie review "Review"
}

reap_finished_locks() {
  local lock issue
  for lock in "$INFLIGHT_DIR"/*; do
    [ -f "$lock" ] || continue
    issue=$(basename "$lock")
    case "$issue" in *[!0-9]*|'') continue ;; esac
    read_lock "$issue"
    if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
      # Best-effort: copy tail of worker log into .last for post-mortems.
      if [ -n "${LANE:-}" ]; then
        local logf="${CURSOR_WORKER_LOG_DIR}/issue-${issue}-${LANE}.log"
        local lastf="${CURSOR_WORKER_LOG_DIR}/issue-${issue}-${LANE}.last"
        if [ -f "$logf" ]; then
          tail -n 80 "$logf" >"$lastf" 2>/dev/null || true
        fi
      fi
      rm -f "$lock"
      if [ -n "$BOT_LOGIN" ]; then
        gh issue edit "$issue" --remove-assignee "$BOT_LOGIN" >/dev/null 2>&1 || true
        log "reaped stale lock + swept assignee on #${issue} (pid=${PID:-empty})"
      else
        log "reaped stale lock for #${issue} (pid=${PID:-empty})"
      fi
    fi
  done
}

# ───────────────────────────── preconditions ─────────────────────────────
log "supersaiyan cursor run started — config=${CONFIG_SLUG} variant=${VARIANT} base=${BASE_BRANCH} poll=${POLL_SECONDS}s idle_recheck=${IDLE_RECHECK_SECONDS}s max_workers=${MAX_WORKERS}"
log "cursor: sandbox=${CURSOR_SANDBOX} skills=${CURSOR_SKILLS_DIR} workspace=${REPO_ROOT}"
log "cursor: model=${CURSOR_MODEL:-<cli default>}"

require_cursor_subscription_auth

if [ ! -d "$CURSOR_SKILLS_DIR/super-build" ] || [ ! -d "$CURSOR_SKILLS_DIR/super-qa" ] || [ ! -d "$CURSOR_SKILLS_DIR/super-review" ]; then
  log "🛑 SuperSaiyan skills missing under ${CURSOR_SKILLS_DIR}."
  log "    Symlink them from the Claude plugin cache, e.g.:"
  log "      mkdir -p ~/.cursor/skills"
  log "      for s in super-build super-qa super-review super-board supersaiyan \\"
  log "               test-driven-development verification-before-completion \\"
  log "               refining-spec writing-board-tasks; do"
  log "        ln -sfn \"\$HOME/.claude/plugins/cache/supersaiyan/supersaiyan/1.0.0/skills/\$s\" \\"
  log "               \"\$HOME/.cursor/skills/\$s\""
  log "      done"
  exit 69
fi

# Orphan / peer-runner guards.
ORPHANS=$(pgrep -f 'agent -p .*lane worker for SuperSaiyan' 2>/dev/null | grep -v "^$$\$" | wc -l | tr -d ' ' || true)
ORPHANS=${ORPHANS:-0}
CODEX_ORPHANS=$(pgrep -f 'codex exec .*lane worker for SuperSaiyan' 2>/dev/null | wc -l | tr -d ' ' || true)
CODEX_ORPHANS=${CODEX_ORPHANS:-0}
CLAUDE_ORPHANS=$(pgrep -f 'claude -p .*super-board run' 2>/dev/null | wc -l | tr -d ' ' || true)
CLAUDE_ORPHANS=${CLAUDE_ORPHANS:-0}
CODEX_DISPATCHER=$(pgrep -f 'supersaiyan-codex-run\.sh' 2>/dev/null | wc -l | tr -d ' ' || true)
CODEX_DISPATCHER=${CODEX_DISPATCHER:-0}
CURSOR_DISPATCHER=$(pgrep -f 'supersaiyan-cursor-run\.sh' 2>/dev/null | grep -v "^$$\$" | wc -l | tr -d ' ' || true)
CURSOR_DISPATCHER=${CURSOR_DISPATCHER:-0}

if [ "$ORPHANS" -gt 0 ]; then
  log "🛑 refusing to start: ${ORPHANS} Cursor lane workers already running."
  log "    Stop them first: pkill -f 'agent -p .*lane worker for SuperSaiyan'"
  log "    Then re-run: $0 $CONFIG_SLUG"
  exit 73
fi
if [ "$CURSOR_DISPATCHER" -gt 0 ]; then
  log "🛑 refusing to start: another supersaiyan-cursor-run.sh is already running."
  log "    Stop it first: pkill -f 'supersaiyan-cursor-run.sh'"
  exit 73
fi
if [ "$CODEX_ORPHANS" -gt 0 ] || [ "$CODEX_DISPATCHER" -gt 0 ]; then
  log "🛑 refusing to start: Codex SuperSaiyan runner/workers are live."
  log "    Two runners would race on GitHub assignee claims and produce duplicate PRs."
  log "    Stop them first: pkill -f 'supersaiyan-codex-run.sh'; pkill -f 'codex exec .*lane worker for SuperSaiyan'"
  exit 73
fi
if [ "$CLAUDE_ORPHANS" -gt 0 ]; then
  log "🛑 refusing to start: ${CLAUDE_ORPHANS} Claude Code super-board workers are running."
  log "    Two runners would race on GitHub assignee claims and produce duplicate PRs."
  log "    Stop them first: pkill -f 'claude -p .*super-board run'"
  exit 73
fi

# Workflow-backend mutual exclusion.
WAVE_LOCK=".claude/supersaiyan/inflight/workflow-wave.lock"
if [ -f "$WAVE_LOCK" ]; then
  log "🛑 refusing to start: workflow-backend wave in flight ($WAVE_LOCK exists)."
  log "    If no wave is actually running, remove the stale lock: rm $WAVE_LOCK"
  exit 74
fi

# Production-merge guard.
if [ "$BASE_BRANCH" = "main" ] && [ "$HUMAN_APPROVES" = "false" ]; then
  if rg -qU 'on:\s*\n?\s*push:\s*\n?\s*branches:[^a-z]*main' .github/workflows 2>/dev/null \
     || [ -f vercel.json ] || [ -f netlify.toml ]; then
    log "🛡 refusing to start: would auto-merge to production main."
    exit 75
  fi
fi

# Stale-worktree scan.
if [ -d .worktrees ]; then
  for wt in .worktrees/*/; do
    [ -d "$wt" ] || continue
    branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
    if [ -z "$branch" ] || ! git rev-parse --verify "$branch" >/dev/null 2>&1; then
      log "stale worktree: $wt (branch '$branch' missing) — removing"
      git worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
    fi
  done
fi

# Reap any leftover stale locks from a previous crashed run.
reap_finished_locks

# ───────────────────────────── main loop ─────────────────────────────
gh_rate_guard
fetch_project_items
INITIAL_READY=$(column_count "Ready")
log "initial Ready count: $INITIAL_READY"

NO_PROGRESS_TICKS=0
BUILD_PID=""; BUILD_ISSUE=""
QA_PID=""; QA_ISSUE=""
REVIEW_PID=""; REVIEW_ISSUE=""

while true; do
  if [ -f "$WAVE_LOCK" ]; then
    log "🛑 workflow-backend wave appeared mid-run ($WAVE_LOCK) — halting for mutual exclusion."
    log "    Resume after the wave: $0 $CONFIG_SLUG"
    exit 74
  fi

  # ── real pass: the only place a GitHub call happens ──────────────────────
  reap_finished_locks
  gh_rate_guard
  fetch_project_items

  sweep_lane_zombies
  BUILD_IDLE=1; QA_IDLE=1; REVIEW_IDLE=1
  lane_idle "$BUILD_PID" || BUILD_IDLE=0
  lane_idle "$QA_PID" || QA_IDLE=0
  lane_idle "$REVIEW_PID" || REVIEW_IDLE=0
  ACTIVE_WORKERS=0
  [ "$BUILD_IDLE" -eq 1 ] || ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))
  [ "$QA_IDLE" -eq 1 ] || ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))
  [ "$REVIEW_IDLE" -eq 1 ] || ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))

  READY=$(column_count "Ready")
  BUILDING=0
  [ "$VARIANT" = "full" ] && BUILDING=$(column_count "Building")
  QA=$(column_count "QA")
  REVIEW=$(column_count "Review")
  BLOCKED=$(column_count "Blocked")

  log "tick — Ready=$READY Building=$BUILDING QA=$QA Review=$REVIEW Blocked=$BLOCKED lanes: b_idle=$BUILD_IDLE(#${BUILD_ISSUE:-_}) q_idle=$QA_IDLE(#${QA_ISSUE:-_}) r_idle=$REVIEW_IDLE(#${REVIEW_ISSUE:-_})"

  if [ "$READY" -eq 0 ] && [ "$BUILDING" -eq 0 ] && [ "$QA" -eq 0 ] && [ "$REVIEW" -eq 0 ] \
     && [ "$BUILD_IDLE" -eq 1 ] && [ "$QA_IDLE" -eq 1 ] && [ "$REVIEW_IDLE" -eq 1 ]; then
    log "✅ all active-pipeline columns empty and all lanes idle — exiting cleanly"
    break
  fi

  if [ "${BLOCK_ALERT_SENT:-0}" -eq 0 ] && [ "$INITIAL_READY" -gt 0 ] && [ "$BLOCK_ALERT_PCT" -gt 0 ]; then
    PCT=$(( BLOCKED * 100 / INITIAL_READY ))
    if [ "$PCT" -ge "$BLOCK_ALERT_PCT" ]; then
      log "⚠ block-rate alert: ${BLOCKED}/${INITIAL_READY} (${PCT}%)"
      BLOCK_ALERT_SENT=1
    fi
  fi

  PROGRESS=0

  can_dispatch() {
    [ "$ACTIVE_WORKERS" -lt "$MAX_WORKERS" ]
  }

  if can_dispatch && [ "$REVIEW" -gt 0 ] && [ "$REVIEW_IDLE" -eq 1 ]; then
    card=$(top_card_in_column "Review")
    if [ -n "${card:-}" ]; then
      dispatch_lane review "$card"
      PROGRESS=1
      ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))
    fi
  fi
  if can_dispatch && [ "$QA" -gt 0 ] && [ "$QA_IDLE" -eq 1 ]; then
    card=$(top_card_in_column "QA")
    if [ -n "${card:-}" ]; then
      dispatch_lane qa "$card"
      PROGRESS=1
      ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))
    fi
  fi
  if can_dispatch && [ "$VARIANT" = "full" ] && [ "$READY" -gt 0 ] && [ "$BUILD_IDLE" -eq 1 ]; then
    card=$(top_build_card)
    if [ -n "${card:-}" ]; then
      dispatch_lane build "$card"
      PROGRESS=1
      ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))
    fi
  fi
  if can_dispatch && [ "$VARIANT" = "qa-only" ] && [ "$READY" -gt 0 ] && [ "$QA_IDLE" -eq 1 ]; then
    card=$(top_build_card)
    if [ -n "${card:-}" ]; then
      dispatch_lane qa "$card"
      PROGRESS=1
      ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))
    fi
  fi

  if [ "$PROGRESS" -eq 0 ]; then
    if [ "$BUILD_IDLE" -eq 0 ] || [ "$QA_IDLE" -eq 0 ] || [ "$REVIEW_IDLE" -eq 0 ]; then
      NO_PROGRESS_TICKS=0
    else
      NO_PROGRESS_TICKS=$((NO_PROGRESS_TICKS + 1))
      if [ "$NO_PROGRESS_TICKS" -ge 3 ]; then
        log "🛑 halt — no card progressed for 3 consecutive real passes while all lanes idle"
        break
      fi
    fi
  else
    NO_PROGRESS_TICKS=0
  fi

  # ── event-driven wait: no GitHub call until something local changes ──────
  # Recompute idle state fresh, since the dispatch attempts above may have
  # just started new workers (or a card may have gone idle with nothing to
  # fill it).
  BUILD_IDLE=1; QA_IDLE=1; REVIEW_IDLE=1
  lane_idle "$BUILD_PID" || BUILD_IDLE=0
  lane_idle "$QA_PID" || QA_IDLE=0
  lane_idle "$REVIEW_PID" || REVIEW_IDLE=0
  ACTIVE_WORKERS=0
  [ "$BUILD_IDLE" -eq 1 ] || ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))
  [ "$QA_IDLE" -eq 1 ] || ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))
  [ "$REVIEW_IDLE" -eq 1 ] || ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))

  if [ "$ACTIVE_WORKERS" -gt 0 ]; then
    # At least one lane is busy. Poll ONLY local process liveness until a
    # lane frees up -- no `gh` call anywhere in this loop, so POLL_SECONDS
    # being small costs nothing.
    PREV_ACTIVE="$ACTIVE_WORKERS"
    while :; do
      sleep "$POLL_SECONDS"
      reap_finished_locks
      CUR_ACTIVE=0
      lane_idle "$BUILD_PID" || CUR_ACTIVE=$((CUR_ACTIVE + 1))
      lane_idle "$QA_PID" || CUR_ACTIVE=$((CUR_ACTIVE + 1))
      lane_idle "$REVIEW_PID" || CUR_ACTIVE=$((CUR_ACTIVE + 1))
      if [ "$CUR_ACTIVE" -lt "$PREV_ACTIVE" ]; then
        break  # a lane just finished -- go run a real pass immediately
      fi
      if [ -f "$WAVE_LOCK" ]; then
        log "🛑 workflow-backend wave appeared mid-wait ($WAVE_LOCK) — halting for mutual exclusion."
        exit 74
      fi
    done
  else
    # Fully idle: nothing local left to react to. A human may have unblocked
    # a card or added work, so fall back to a light periodic recheck.
    sleep "$IDLE_RECHECK_SECONDS"
  fi
done

log "super-board run finished. manifest: $RUN_MANIFEST"
