#!/usr/bin/env bash
# Symlink SuperSaiyan skills into ~/.cursor/skills for the Cursor dispatcher.
# Safe to re-run. See docs/supersaiyan/cursor-runner.md.

set -euo pipefail

DEST="${CURSOR_SKILLS_DIR:-$HOME/.cursor/skills}"
PLUGIN_ROOT="${SUPERSAIYAN_SKILLS_ROOT:-}"

# Find the installed SuperSaiyan plugin skills directory.
if [ -z "$PLUGIN_ROOT" ]; then
  for candidate in \
    "$HOME"/.claude/plugins/cache/supersaiyan/supersaiyan/*/skills \
    "$HOME"/.claude/plugins/marketplaces/supersaiyan/skills
  do
    if [ -d "$candidate/super-build" ]; then
      PLUGIN_ROOT="$candidate"
      break
    fi
  done
fi

if [ -z "${PLUGIN_ROOT:-}" ] || [ ! -d "$PLUGIN_ROOT/super-build" ]; then
  echo "🛑 SuperSaiyan skills not found under ~/.claude/plugins/." >&2
  echo "    Install the SuperSaiyan plugin in Claude Code first, or set" >&2
  echo "    SUPERSAIYAN_SKILLS_ROOT to the skills directory." >&2
  exit 69
fi

mkdir -p "$DEST"
for s in super-build super-qa super-review super-board supersaiyan \
         test-driven-development verification-before-completion \
         refining-spec writing-board-tasks; do
  if [ ! -d "$PLUGIN_ROOT/$s" ]; then
    echo "⚠ missing skill: $PLUGIN_ROOT/$s — skipping" >&2
    continue
  fi
  ln -sfn "$PLUGIN_ROOT/$s" "$DEST/$s"
  echo "linked $DEST/$s -> $PLUGIN_ROOT/$s"
done

echo
echo "Done. Skills dir: $DEST"
echo "Next: agent login && agent status && agent models"
echo "Then: CURSOR_MAX_PARALLEL=1 scripts/supersaiyan-cursor-run.sh ai-researcher"
