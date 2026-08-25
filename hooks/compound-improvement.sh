#!/usr/bin/env bash
# Keeps the compounding habits live during long sessions.
#
# A skill only helps if something remembers to invoke it, and instructions in a
# memory file drift out of attention as context fills. These two hooks are the
# part that does not drift: they nudge the session back to the `skill-compounder`
# skill at the two moments that matter.
#
# argv[1] = mode:
#   prompt  -> UserPromptSubmit. "Does a skill already solve this?" Throttled to one
#              reminder per CI_PROMPT_COOLDOWN seconds, and only for prompts of at
#              least CI_PROMPT_MIN_CHARS characters, so "yes" / "continue" never fire it.
#   edit    -> PostToolUse on Write|Edit. "Is this pattern worth crystallizing?" Fires
#              every CI_EDIT_EVERY file modifications.
#
# Any failure exits 0 silently: a reminder must never break the user's turn.
# Set CI_DEBUG_DUMP=<path> to append the raw stdin payload for inspection.
#
# This script is wired twice on purpose: once by the installer into settings.json,
# and once by hooks/hooks.json for anyone loading the repo as a plugin. A machine
# with both active delivers every event to it twice, which would silently halve
# CI_EDIT_EVERY and double every cooldown stamp. claim_once() below makes each
# event idempotent, so running both paths is harmless rather than quietly wrong.
set -uo pipefail

# HOME can be unset (cron, a stripped env, a container). Under `set -u` that aborted the
# script with an unbound-variable error and a non-zero exit, which breaks the one promise
# a hook has to keep. Default it before anything reads it.
: "${HOME:=/tmp}"

MODE="${1:-edit}"
EDIT_EVERY="${CI_EDIT_EVERY:-12}"
PROMPT_COOLDOWN="${CI_PROMPT_COOLDOWN:-1200}"
PROMPT_MIN_CHARS="${CI_PROMPT_MIN_CHARS:-60}"
STATE_DIR="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}/reminders"

payload="$(cat)"
[ -n "${CI_DEBUG_DUMP:-}" ] && printf '%s\n' "$payload" >> "$CI_DEBUG_DUMP"

command -v jq >/dev/null 2>&1 || exit 0
mkdir -p "$STATE_DIR" 2>/dev/null || exit 0

sid="$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null)"
[ -z "$sid" ] && sid="nosession"
sid="$(printf '%s' "$sid" | tr -c 'A-Za-z0-9._-' '_')"

now="${CI_NOW:-$(date +%s)}"

# Claim an event exactly once per session, whichever wiring delivered it.
# UserPromptSubmit carries .prompt_id and PostToolUse carries .tool_use_id; both were
# confirmed present on CLI 2.1.241. mkdir is the claim because it is atomic: two hook
# processes racing on the same event, one from settings.json and one from the plugin,
# cannot both succeed. Returns 0 for the first caller and 1 for every later one.
# An event with no usable id is always claimed, since suppressing an unidentifiable
# event would lose reminders on any future payload shape that drops these fields.
claim_once() {
  local id dir marker
  id="$(printf '%s' "$payload" | jq -r '.tool_use_id // .prompt_id // empty' 2>/dev/null)"
  [ -z "$id" ] && return 0
  # Truncate as well as sanitise. A pathologically long id would exceed NAME_MAX, mkdir
  # would fail with ENAMETOOLONG, and the hook would read that as "already claimed" and
  # go silent forever. 96 characters is far longer than any real id and safely under the
  # limit everywhere.
  id="$(printf '%s' "$id" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
  dir="$STATE_DIR/$sid.seen"
  mkdir -p "$dir" 2>/dev/null || return 0
  marker="$dir/$1-$id"
  # Fail OPEN, not closed. mkdir failing because the marker exists is a duplicate; mkdir
  # failing for any other reason (read-only state, a full disk) must not silently disable
  # every reminder for the rest of the session. Distinguish the two by testing the marker.
  if mkdir "$marker" 2>/dev/null; then
    return 0
  fi
  [ -d "$marker" ] && return 1
  return 0
}

prune_stale_state() {
  # Claim markers are directories, and they nest: <sid>.seen/<mode>-<id>/. An earlier
  # version matched only '*.seen*', which left the inner markers in place, so the parent
  # was never empty, rmdir always failed, and one inode leaked per edit forever. -depth
  # visits children before parents, so a single pass empties the markers and then removes
  # the directory that held them.
  #
  # Markers age out after CI_CLAIM_TTL_MIN minutes, not seven days: a duplicate delivery
  # arrives within milliseconds of the first, and keeping a week of them means find walks
  # tens of thousands of directories.
  #
  # This runs on the throttled paths too, not only when a reminder is emitted. Behind the
  # emit it would have fired about once in EDIT_EVERY * PRUNE_EVERY events, roughly 300,
  # rather than the one in 25 the sampling claims.
  CLAIM_TTL_MIN="${CI_CLAIM_TTL_MIN:-60}"
  PRUNE_EVERY="${CI_PRUNE_EVERY:-25}"
  [ $(( ${RANDOM:-0} % PRUNE_EVERY )) -eq 0 ] || return 0
  find "$STATE_DIR" -type f -mtime +7 -delete 2>/dev/null
  find "$STATE_DIR" -mindepth 2 -depth -type d -mmin "+$CLAIM_TTL_MIN" -exec rmdir {} + 2>/dev/null
  # No -mmin on this pass: removing the markers above just reset the parent's mtime.
  find "$STATE_DIR" -mindepth 1 -maxdepth 1 -type d -name '*.seen' -empty -exec rmdir {} + 2>/dev/null
  return 0
}

emit() { # $1 = context text, $2 = hookEventName
  jq -n --arg ctx "$1" --arg ev "$2" \
    '{suppressOutput:true, hookSpecificOutput:{hookEventName:$ev, additionalContext:$ctx}}'
}

case "$MODE" in
  prompt)
    claim_once prompt || exit 0
    text="$(printf '%s' "$payload" | jq -r '.prompt // ""' 2>/dev/null)"
    [ "${#text}" -lt "$PROMPT_MIN_CHARS" ] && exit 0
    stamp="$STATE_DIR/$sid.prompt"
    # An absent or unreadable stamp means "never reminded in this session", which
    # must always fire. Defaulting it to 0 instead would silently suppress the very
    # first reminder whenever the clock value is smaller than the cooldown.
    last=""
    [ -f "$stamp" ] && last="$(cat "$stamp" 2>/dev/null || true)"
    case "$last" in ''|*[!0-9]*) last="" ;; esac
    if [ -n "$last" ] && [ $(( now - last )) -lt "$PROMPT_COOLDOWN" ]; then
      prune_stale_state
      exit 0
    fi
    printf '%s' "$now" > "$stamp"
    emit "[skill-compounder] Before starting implementation, check whether an existing skill already solves this — the session skill list, ~/.claude/skills/, ./.claude/skills/. Invoke the 'skill-compounder' skill for the full check. Disregard if this turn is not implementation work." "UserPromptSubmit"
    ;;
  edit)
    claim_once edit || exit 0
    # One byte appended per edit, and the count is the file size. A read-modify-write
    # loses events under concurrency, and edits arrive in bursts: measured at 4-way
    # parallelism the old counter recorded 12 of 60, so a 12-edit checkpoint fired about
    # five times too rarely and skillreport's conversion denominator was inflated to
    # match. An O_APPEND write of one byte is atomic, so nothing is lost.
    counter="$STATE_DIR/$sid.edits"
    printf 'x' >> "$counter" 2>/dev/null || exit 0
    n="$(wc -c < "$counter" 2>/dev/null | tr -d ' ')"
    case "$n" in ''|*[!0-9]*) exit 0 ;; esac
    if [ $(( n % EDIT_EVERY )) -ne 0 ]; then
      prune_stale_state
      exit 0
    fi
    emit "[skill-compounder] Checkpoint after $n file edits. (a) Is the procedure you are working through right now BOTH costly to have gotten right AND likely to recur? (b) Did a skill you invoked this session misfire? If either is yes, invoke the 'skill-compounder' skill and follow it. If neither, disregard." "PostToolUse"
    ;;
  *) exit 0 ;;
esac

prune_stale_state
exit 0
