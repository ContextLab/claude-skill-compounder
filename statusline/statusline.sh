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

# ------------------------------------------------------------------------------------
# THE ENTIRE BODY OF THIS SCRIPT IS ONE BRACE GROUP, AND THE `}` AT THE END OF THE FILE
# IS WHAT CLOSES IT. It is not style and it is not decoration.
#
# bash reads a script LAZILY, by byte offset, and resumes at that offset in whatever the
# file holds AT THAT MOMENT. Every file in this package is executed by absolute path out
# of the checkout -- the installer writes those paths into settings.json and symlinks the
# CLIs -- so one `git pull`, `git checkout` or `sed -i` rewrites the bytes of a run that
# is already in flight. Measured on GNU bash 5.3.3(1): prepending forty lines to a live
# 25-line script produced `line 4: non-transferable: command not found` and then a second
# execution of the body; truncating it produced `unexpected EOF` and exit 2.
#
# A brace group is a single compound command, so bash must find the matching `}` before
# it may run any part of it: the file goes through the parser in ONE pass and nothing
# written to disk afterwards can be executed. A file truncated badly enough to break the
# parse then runs NOTHING, which is also the answer we want here -- half a hook is worse
# than no hook.
#
# THE `exit` BEFORE THE CLOSING `}` IS LOAD-BEARING TOO. A brace group protects its body
# and nothing past it: measured, a wrapped script that fell off its end had bash resume
# at the offset just past `}`, find prepended text sitting there, and run the whole body
# a SECOND time. So the group is not sufficient on its own.
#
# Consequences when editing:
#   - the closing `}` must stay the last line, and `bash -n` is what proves it.
#   - the last statement inside the group must be an `exit`. tests/test_script_wrapping.py
#     checks that across every shipped script and reproduces the hazard against a live
#     process.
#   - `exit` still exits the script, traps are still global, and functions and variables
#     defined inside are still global. Nothing about the semantics changes.
#
# The incident this came out of, and the reproduction, are in docs/DESIGN.md under
# "Never edit a script that may still be running".
# ------------------------------------------------------------------------------------
{

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# `set -u` aborts on an unset HOME, which renders a blank status line and no error. The
# other shipped scripts carry the same default; tests/test_script_wrapping.py pins it.
: "${HOME:=/tmp}"
STATE="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
# The previous status line is saved into state, not into the clone, so a `git pull`
# never clobbers it and the repo stays free of generated files.
BASE="$STATE/statusline-base.sh"
FORGE="$HERE/skillforge-status.sh"
BASE_TTL="${STATUSLINE_BASE_TTL:-5}"
CACHE_DIR="$STATE/statusline-cache"
# Renders between sweeps of dead cache entries. The cache key is a hash of session id
# and working directory, so EVERY session that ever drew a status line leaves a file
# here and nothing in this repository deleted one. Sampled rather than swept every
# render because this script runs once a second, and a `find` at that rate would cost
# more than the cache it is protecting saves.
CACHE_PRUNE_EVERY="${STATUSLINE_CACHE_PRUNE_EVERY:-200}"
case "$CACHE_PRUNE_EVERY" in ''|*[!0-9]*) CACHE_PRUNE_EVERY=200 ;; esac
[ "$CACHE_PRUNE_EVERY" -lt 1 ] && CACHE_PRUNE_EVERY=1

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
    # A week is far beyond any possible use: an entry is only ever READ within
    # STATUSLINE_BASE_TTL seconds of being written, so a file untouched for seven days
    # belongs to a session that is long over. Pruned here, on the miss path, because a
    # hit does not touch the directory at all.
    if [ $(( ${RANDOM:-0} % CACHE_PRUNE_EVERY )) -eq 0 ]; then
      find "$CACHE_DIR" -type f -mtime +7 -delete 2>/dev/null || :
    fi
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

exit

# Closes the brace group opened just under `set -uo pipefail`. See the note there.
}
