#!/usr/bin/env bash
# Claude Code status line: whatever status line you already had, plus the live
# skill-forge animation when a skill is being forged.
#
# The installer saves your previous statusLine command to
# ~/.claude/skill-compounder/statusline-base.sh and points settings.json here. If you had no status line, base output is empty and you
# see only the forge segment while one is active.
#
# refreshInterval is 1s so the forge animates. Base output is cached for BASE_TTL
# seconds because a typical base segment shells out to git, and once a second is too
# often for that.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
STATE="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
# The previous status line is saved into state, not into the clone, so a `git pull`
# never clobbers it and the repo stays free of generated files.
BASE="$STATE/statusline-base.sh"
FORGE="$HERE/skillforge-status.sh"
BASE_TTL="${STATUSLINE_BASE_TTL:-5}"
CACHE_DIR="$STATE/statusline-cache"

payload="$(cat 2>/dev/null)"

base=""
if [ -x "$BASE" ]; then
  key="$(printf '%s' "$payload" | jq -r '"\(.session_id // "s")|\(.workspace.current_dir // "d")"' 2>/dev/null \
        | cksum | tr -d ' ' | tr -c 'A-Za-z0-9' '_')"
  cache="$CACHE_DIR/${key:-fallback}"
  now="$(date +%s)"
  if [ -f "$cache" ]; then
    # GNU stat must be tried FIRST and the result validated. `stat -f` on GNU
    # coreutils means "report on the filesystem", not "use this format", so
    # `stat -f %m` there exits 0 and prints a mount point. A plain `A || B` chain
    # therefore never reaches the GNU branch, the numeric guard zeroes the mtime,
    # and the cache misses on every single render. On Linux that silently reran the
    # user's base status line (usually a git call) once a second, which is the exact
    # thing this cache exists to prevent. BSD stat has no -c, so it fails cleanly.
    mtime="$(stat -c %Y "$cache" 2>/dev/null)"
    case "$mtime" in ''|*[!0-9]*) mtime="$(stat -f %m "$cache" 2>/dev/null)" ;; esac
    case "$mtime" in ''|*[!0-9]*) mtime=0 ;; esac
    [ $(( now - mtime )) -lt "$BASE_TTL" ] && base="$(cat "$cache" 2>/dev/null)"
  fi
  if [ -z "$base" ]; then
    base="$(printf '%s' "$payload" | "$BASE" 2>/dev/null)"
    mkdir -p "$CACHE_DIR" 2>/dev/null && printf '%s' "$base" > "$cache" 2>/dev/null
  fi
fi

forge="$(printf '%s' "$payload" | "$FORGE" 2>/dev/null)"

if [ -n "$forge" ] && [ -n "$base" ]; then
  printf '%s  %s' "$base" "$forge"
elif [ -n "$forge" ]; then
  printf '%s' "$forge"
else
  printf '%s' "$base"
fi
