#!/usr/bin/env bash
# Install the review-pr skill for Claude Code and Codex on this machine.
#
#   ./install.sh            symlink (git pull keeps both harnesses current)
#   ./install.sh --copy     copy a snapshot instead of linking
#   ./install.sh --uninstall
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/skills/review-pr"
TARGETS=("$HOME/.claude/skills/review-pr" "$HOME/.codex/skills/review-pr")
MODE="link"

case "${1:-}" in
  --copy) MODE="copy" ;;
  --uninstall) MODE="uninstall" ;;
  "") ;;
  *) echo "usage: $0 [--copy|--uninstall]" >&2; exit 2 ;;
esac

for target in "${TARGETS[@]}"; do
  parent="$(dirname "$target")"
  case "$MODE" in
    uninstall)
      if [ -L "$target" ] || [ -d "$target" ]; then
        rm -rf "$target"
        echo "removed $target"
      fi
      ;;
    link|copy)
      mkdir -p "$parent"
      if [ -e "$target" ] && [ ! -L "$target" ]; then
        echo "refusing to overwrite non-symlink $target — remove it first" >&2
        exit 1
      fi
      rm -rf "$target"
      if [ "$MODE" = link ]; then
        ln -s "$SRC" "$target"
        echo "linked $target -> $SRC"
      else
        cp -r "$SRC" "$target"
        echo "copied $SRC -> $target"
      fi
      ;;
  esac
done

if [ "$MODE" != uninstall ]; then
  echo
  echo "Installed. Invoke as /review-pr in Claude Code or \$review-pr in Codex."
  for cli in claude codex gh; do
    if command -v "$cli" >/dev/null 2>&1; then
      echo "  ✓ $cli found"
    else
      echo "  ✗ $cli not on PATH (the skill degrades without it)"
    fi
  done
fi
