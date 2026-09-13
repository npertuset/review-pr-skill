#!/usr/bin/env bash
# Install every skill under skills/ (review-pr, review-plan) for Claude Code
# and Codex on this machine.
#
#   ./install.sh            symlink (git pull keeps both harnesses current)
#   ./install.sh --copy     copy a snapshot instead of linking
#   ./install.sh --uninstall
#
# Only touches installations it created: a symlink pointing into this clone,
# or a copy carrying the marker file below. Anything else at a target path is
# left alone and reported.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKER=".installed-by-review-pr-skill"
SKILLS=()
for d in "$HERE"/skills/*/; do
  [ -f "$d/SKILL.md" ] && SKILLS+=("$(basename "$d")")
done
MODE="link"

case "${1:-}" in
  --copy) MODE="copy" ;;
  --uninstall) MODE="uninstall" ;;
  "") ;;
  *) echo "usage: $0 [--copy|--uninstall]" >&2; exit 2 ;;
esac

# 0 = nothing there, 1 = ours (symlink into this clone or marked copy), 2 = foreign
classify() {
  local target="$1" src="$2"
  if [ -L "$target" ]; then
    local dest
    dest="$(readlink -f "$target" 2>/dev/null || true)"
    [ "$dest" = "$(readlink -f "$src")" ] && return 1
    return 2
  fi
  if [ -e "$target" ]; then
    [ -f "$target/$MARKER" ] && return 1
    return 2
  fi
  return 0
}

status=0
for skill in "${SKILLS[@]}"; do
SRC="$HERE/skills/$skill"
for target in "$HOME/.claude/skills/$skill" "$HOME/.codex/skills/$skill"; do
  parent="$(dirname "$target")"
  set +e; classify "$target" "$SRC"; owned=$?; set -e
  if [ "$owned" = 2 ]; then
    echo "skipping $target — not installed by this script (remove it by hand if you mean to)" >&2
    status=1
    continue
  fi
  case "$MODE" in
    uninstall)
      if [ "$owned" = 1 ]; then
        rm -rf "$target"
        echo "removed $target"
      fi
      ;;
    link|copy)
      mkdir -p "$parent"
      [ "$owned" = 1 ] && rm -rf "$target"
      if [ "$MODE" = link ]; then
        ln -s "$SRC" "$target"
        echo "linked $target -> $SRC"
      else
        cp -r "$SRC" "$target"
        : > "$target/$MARKER"
        echo "copied $SRC -> $target"
      fi
      ;;
  esac
done
done

if [ "$MODE" != uninstall ]; then
  echo
  echo "Installed: ${SKILLS[*]}. Invoke as /<name> in Claude Code or \$<name> in Codex."
  for cli in claude codex gh python3; do
    if command -v "$cli" >/dev/null 2>&1; then
      echo "  ✓ $cli found"
    else
      echo "  ✗ $cli not on PATH (the skill degrades without it)"
    fi
  done
fi
exit "$status"
