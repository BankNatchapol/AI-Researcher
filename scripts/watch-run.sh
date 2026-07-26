#!/usr/bin/env bash
# watch-run.sh — live view of the autonomous loop.
#
#   scripts/watch-run.sh            # dashboard, refreshes every 10s
#   scripts/watch-run.sh follow     # stream the newest worker's output
#   scripts/watch-run.sh follow 3   # stream issue #3's worker output
#
# The dispatcher's own log (run.log) only ticks every 120s, so silence there is
# normal. Worker activity lives in .claude/supersaiyan/codex-logs/.

set -uo pipefail
cd "$(dirname "$0")/.."

LOGS=.claude/supersaiyan/codex-logs
PROJECT_NUM="${PROJECT_NUM:-6}"
PROJECT_OWNER="${PROJECT_OWNER:-BankNatchapol}"
REFRESH="${REFRESH:-10}"

newest_log() { ls -t "$LOGS"/issue-*.log 2>/dev/null | head -1; }

# macOS pgrep has no -c count flag (that is GNU); count by piping to wc.
count_workers() { pgrep -f 'codex exec .*lane worker for SuperSaiyan' 2>/dev/null | wc -l | tr -d ' '; }

# ANSI clear works in any modern terminal and needs no TERM, unlike `clear(1)`.
clear_screen() { printf '\033[2J\033[H'; }

if [ "${1:-}" = "follow" ]; then
  if [ -n "${2:-}" ]; then
    f=$(ls -t "$LOGS"/issue-"$2"-*.log 2>/dev/null | head -1)
  else
    f=$(newest_log)
  fi
  [ -z "$f" ] && { echo "No worker logs yet in $LOGS"; exit 1; }
  echo "── following $f ──"
  exec tail -f "$f"
fi

while true; do
  clear_screen
  printf '\033[1m── loop status  %s ──\033[0m\n\n' "$(date +%H:%M:%S)"

  if pgrep -f 'supersaiyan-codex-run.sh' >/dev/null; then
    printf '  dispatcher  \033[32mrunning\033[0m\n'
  else
    printf '  dispatcher  \033[31mnot running\033[0m\n'
  fi

  printf '  workers     %s active\n\n' "$(count_workers)"

  printf '\033[1mBoard\033[0m\n'
  gh project item-list "$PROJECT_NUM" --owner "$PROJECT_OWNER" --format json 2>/dev/null \
  | python3 -c "
import json,sys
from collections import Counter
try: items=json.load(sys.stdin)['items']
except Exception: print('  (board unavailable)'); raise SystemExit
c=Counter(i.get('status','?') for i in items)
order=['Ready','Building','QA','Review','Done','Blocked','Skipped']
print('  ' + '   '.join(f'{k} {c.get(k,0)}' for k in order if c.get(k)))
print()
for i in sorted(items,key=lambda x:x['content'].get('number',0)):
    st=i.get('status','?')
    if st in ('Ready','Done'): continue
    print(f\"  #{i['content'].get('number','?'):>3}  {st:<9} {i['title'][:52]}\")
"
  echo
  printf '\033[1mLatest worker activity\033[0m\n'
  f=$(newest_log)
  if [ -n "$f" ]; then
    printf '  %s  (%s)\n\n' "$(basename "$f")" "$(du -h "$f" | cut -f1)"
    tail -12 "$f" | sed 's/^/  /'
  else
    echo "  (no worker logs yet)"
  fi

  echo
  printf '\033[2m  refresh %ss · follow a worker: scripts/watch-run.sh follow · Ctrl-C to exit\033[0m\n' "$REFRESH"
  sleep "$REFRESH"
done
