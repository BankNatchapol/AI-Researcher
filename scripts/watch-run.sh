#!/usr/bin/env bash
# watch-run.sh — live board view for the autonomous loop.
#
#   scripts/watch-run.sh            # Kanban + PRs, refreshing
#   scripts/watch-run.sh once       # render once and exit
#   scripts/watch-run.sh follow     # stream the newest worker's output
#   scripts/watch-run.sh follow 3   # stream issue #3's worker output
#
# The Kanban, worker table, block reasons, and health come from SuperSaiyan's
# own `super-board-status.py` — the same renderer `/supersaiyan status` uses.
# This wrapper adds a pull-request section and refreshes on a loop.
#
# Read-only: never mutates GitHub, locks, worktrees, or the manifest. Safe to
# run against a live dispatcher.

set -uo pipefail
cd "$(dirname "$0")/.."

SLUG="${1:-}"
case "$SLUG" in once|follow) SLUG="" ;; esac
[ -z "$SLUG" ] && SLUG=$(cat .claude/supersaiyan/active 2>/dev/null || echo ai-researcher)

CONFIG=".claude/supersaiyan/configs/${SLUG}.json"
BACKEND=$(jq -r '.worker_backend // "workflow"' "$CONFIG" 2>/dev/null || echo workflow)
case "$BACKEND" in
  cursor-agent) LOGS=.claude/supersaiyan/cursor-logs ;;
  *)            LOGS=.claude/supersaiyan/codex-logs ;;
esac

# Rendering queries GitHub Projects v2, so keep the default aligned with the
# dispatcher's low-frequency poll interval. Override explicitly for short,
# supervised debugging sessions only.
REFRESH="${REFRESH:-600}"

# The status renderer ships with the plugin; prefer the installed cache, fall
# back to the marketplace clone.
find_status_script() {
  local c
  for c in \
    "$HOME"/.claude/plugins/cache/supersaiyan/supersaiyan/*/scripts/super-board-status.py \
    "$HOME"/.claude/plugins/marketplaces/supersaiyan/scripts/super-board-status.py
  do [ -f "$c" ] && { echo "$c"; return 0; }; done
  return 1
}
STATUS_PY=$(find_status_script) || true

newest_log() { ls -t "$LOGS"/issue-*.log 2>/dev/null | head -1; }

# ── follow mode ───────────────────────────────────────────────────────────
if [ "${1:-}" = "follow" ]; then
  if [ -n "${2:-}" ]; then f=$(ls -t "$LOGS"/issue-"$2"-*.log 2>/dev/null | head -1)
  else f=$(newest_log); fi
  [ -z "$f" ] && { echo "No worker logs yet in $LOGS"; exit 1; }
  echo "── following $f ──"
  exec tail -f "$f"
fi

render() {
  if [ -n "$STATUS_PY" ]; then
    python3 "$STATUS_PY" "$SLUG" 2>&1
  else
    echo "⚠ super-board-status.py not found — is the SuperSaiyan plugin installed?"
  fi

  # PRs: the one thing the bundled renderer does not show.
  echo
  echo "▎Pull requests"
  local prs
  prs=$(gh pr list --state all --limit 8 \
        --json number,title,state,isDraft,headRefName,mergedAt \
        --jq '.[] | "\(.number)\t\(.state)\t\(.isDraft)\t\(.title)"' 2>/dev/null)
  if [ -z "$prs" ]; then
    echo "   (none yet)"
  else
    printf '%s\n' "$prs" | while IFS=$'\t' read -r num state draft title; do
      case "$state" in
        MERGED) icon="✅" ;;
        CLOSED) icon="🚫" ;;
        OPEN)   [ "$draft" = "true" ] && icon="📝" || icon="🔀" ;;
        *)      icon="  " ;;
      esac
      printf '   %s #%-4s %-7s %s\n' "$icon" "$num" "$state" "${title:0:52}"
    done
  fi

  # Runtime: what the board cannot tell you.
  echo
  echo "▎Runtime"
  echo "   backend: $BACKEND   logs: $LOGS"
  local disp_running=0 workers=0
  case "$BACKEND" in
    cursor-agent)
      pgrep -f 'supersaiyan-cursor-run\.sh' >/dev/null 2>&1 && disp_running=1
      workers=$(pgrep -f 'agent -p .*lane worker for SuperSaiyan' 2>/dev/null | wc -l | tr -d ' ')
      ;;
    codex-exec)
      pgrep -f 'supersaiyan-codex-run\.sh' >/dev/null 2>&1 && disp_running=1
      workers=$(pgrep -f 'codex exec .*lane worker for SuperSaiyan' 2>/dev/null | wc -l | tr -d ' ')
      ;;
    *)
      pgrep -f 'super-board-run\.sh' >/dev/null 2>&1 && disp_running=1
      workers=$(pgrep -f 'claude -p .*super-board run' 2>/dev/null | wc -l | tr -d ' ')
      ;;
  esac
  if [ "$disp_running" -eq 1 ]; then
    printf '   dispatcher: running'
  else
    printf '   dispatcher: STOPPED'
  fi
  printf '   workers: %s' "${workers:-0}"
  local f; f=$(newest_log)
  [ -n "$f" ] && printf '   newest log: %s (%s)' "$(basename "$f")" "$(du -h "$f" 2>/dev/null | cut -f1)"
  echo
}

if [ "${1:-}" = "once" ]; then render; exit 0; fi

while true; do
  out=$(render)
  printf '\033[2J\033[H%s\n' "$out"
  printf '\033[2m  refresh %ss · follow a worker: scripts/watch-run.sh follow · Ctrl-C to exit\033[0m\n' "$REFRESH"
  sleep "$REFRESH"
done
