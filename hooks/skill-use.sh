#!/usr/bin/env bash
# Records every Skill invocation in the forge ledger, as it happens.
#
# argv[1] = which event delivered this:
#   ok    -> PostToolUse,        matcher "Skill". The invocation ran.
#   fail  -> PostToolUseFailure, matcher "Skill". The invocation did not run.
#
# WHY BOTH EVENTS ARE WIRED. `PostToolUse` fires only when the tool SUCCEEDED; a failure
# is delivered as a separate `PostToolUseFailure` event (measured on CLI 2.1.245: a Bash
# call that died on a shell parse error arrived as `PostToolUseFailure:Bash`, carrying
# tool_name, tool_use_id, session_id and transcript_path, with `tool_response: null`).
# A hook wired only to `PostToolUse` therefore sees a stream of successes and would write
# `ok:true` for every one of them -- the exact defect `skillreport` had to have fixed,
# where one uninstalled skill moved a headline from 80% to 100%.
#
# MEASURED LIMIT, AND IT IS A REAL ONE. The one Skill failure that can be produced on
# demand -- `Unknown skill: <name>` -- is delivered to NO hook at all. Verified twice on
# 2.1.245 (2026-08-26) in headless sessions whose hooks dump every payload: with
# `PostToolUse` and `PostToolUseFailure` both wired, once with matcher "Skill" and once
# with no matcher at all, a bogus skill name produced a `tool_result` carrying
# `is_error:true` in the transcript and not one hook delivery, while a failing `Bash` call
# in the same session was delivered normally. So the `fail` arm below is correct and
# currently near-silent: it exists because wiring only the success event would be wrong
# the moment that changes, and because it costs nothing. Do not read an absence of
# `ok:false` rows as an absence of failed invocations. The transcript's `is_error` flag
# remains the only reliable census of those, which is what `skillreport` reads.
#
# GENUINE VERSUS HARNESS, AT WRITE TIME. This package's own probes and end-to-end tests
# invoke these very skills through `claude -p`, and on the machine this was written on
# they were 93 of 98 recorded invocations. The discriminator is who drove the session,
# and Claude Code stamps it on every transcript record as `.entrypoint` ("sdk-cli" for a
# program, "cli" for a person at a terminal). The hook payload does NOT carry that field
# (measured: the PostToolUse payload holds session_id, transcript_path, cwd, prompt_id,
# permission_mode, effort, hook_event_name, tool_name, tool_input, tool_response,
# tool_use_id, duration_ms -- and no entrypoint), so it is read out of a bounded head of
# the transcript the payload names. The first few records can carry a null entrypoint, so
# the first NON-NULL one wins. When it cannot be read the field is OMITTED rather than
# defaulted: the row then carries the session id, which is what a reader needs to classify
# it later, and a `harness` value that was guessed is worse than one that is absent.
#
# IDEMPOTENT PER EVENT. With the installer's wiring and the plugin both active every hook
# is delivered twice (measured on 2.1.241), so each event is claimed once by `mkdir` of a
# directory named for its `tool_use_id` -- the same scheme, in the same state directory,
# as hooks/compound-improvement.sh, so its prune sweeps these markers too. The ledger
# writer refuses a `tool_use_id` it already holds as well, which is the guard that still
# works an hour later when the marker has aged out.
#
# ANY FAILURE EXITS 0 SILENTLY, and nothing is ever written to stdout: a hook must never
# break the user's turn, and this one runs after every skill anyone invokes.
#
# Env:
#   SKILL_COMPOUNDER_USE_LOG=0   do not record invocations at all
#   SKILLUSE_HEAD_BYTES          transcript bytes read to find the entrypoint (65536)
#   SKILLUSE_FORGE               path to the skillforge CLI (default: ../bin/skillforge)
#   SKILLUSE_DEBUG_DUMP          append the raw stdin payload to this path
set -uo pipefail

# ------------------------------------------------------------------------------------
# THE ENTIRE BODY OF THIS SCRIPT IS ONE BRACE GROUP, AND THE `}` AT THE END OF THE FILE
# IS WHAT CLOSES IT, for the reason spelled out at length in hooks/compound-improvement.sh:
# bash reads a script lazily by byte offset, this file is executed by absolute path out of
# a checkout, and a `git pull` mid-run would otherwise resume in whatever bytes now sit at
# that offset. A brace group forces the whole file through the parser in one pass. The
# `exit 0` before the closing `}` is load-bearing too -- a group protects its body and
# nothing past it.
# ------------------------------------------------------------------------------------
{

: "${HOME:=/tmp}"
ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
STATE_DIR="$ROOT/reminders"
HEAD_BYTES="${SKILLUSE_HEAD_BYTES:-65536}"
case "$HEAD_BYTES" in ''|*[!0-9]*) HEAD_BYTES=65536 ;; esac

mode="${1:-ok}"
payload="$(cat)"
[ -n "${SKILLUSE_DEBUG_DUMP:-}" ] && printf '%s\n' "$payload" >> "$SKILLUSE_DEBUG_DUMP"

[ "${SKILL_COMPOUNDER_USE_LOG:-1}" = "0" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

# The tool name is checked even though the matcher already selects it. A user (or a
# future us) can wire this script with no matcher at all, and a `use` row naming Bash
# would be a false record rather than a missing one.
tool="$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null)"
[ "$tool" = "Skill" ] || exit 0

# The Skill tool's argument has been spelled `skill`, `command` and `name` across
# versions, so take whichever string is present rather than pinning one.
skill="$(printf '%s' "$payload" | jq -r '
  .tool_input // {} | (.skill // .command // .name // .skill_name // empty)
  | select(type == "string" and length > 0)' 2>/dev/null | head -1)"
[ -n "$skill" ] || exit 0

sid="$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null)"
[ -z "$sid" ] && sid="nosession"
# The identical expression hooks/compound-improvement.sh applies, for the identical
# reason: every path below is "$STATE_DIR/$sid.<something>", and an id longer than
# NAME_MAX makes each of those fail with ENAMETOOLONG. The two MUST stay in agreement or
# one of them claims events under a name the other never looks at.
sid_safe="$(printf '%s' "$sid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"

tuid="$(printf '%s' "$payload" | jq -r '.tool_use_id // empty' 2>/dev/null)"
cwd="$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)"
transcript="$(printf '%s' "$payload" | jq -r '.transcript_path // empty' 2>/dev/null)"

# Claim this event exactly once, whichever wiring delivered it. An event with no usable
# id is always claimed: a duplicated row is visible and removable, while suppressing an
# unidentifiable event would lose invocations silently on any future payload shape that
# drops the field. The ledger writer deduplicates on the id as well, so a duplicate that
# does carry one still cannot land twice.
if [ -n "$tuid" ]; then
  claim_id="$(printf '%s' "$tuid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
  claim_dir="$STATE_DIR/$sid_safe.seen"
  if mkdir -p "$claim_dir" 2>/dev/null; then
    if ! mkdir "$claim_dir/use-$claim_id" 2>/dev/null; then
      # Fail OPEN, exactly as compound-improvement.sh does: mkdir failing because the
      # marker is there is a duplicate, and mkdir failing because the state directory is
      # read-only is not. Treating the two the same would silently stop recording for the
      # rest of the session.
      [ -d "$claim_dir/use-$claim_id" ] && exit 0
    fi
  fi
fi

# WHO DROVE THE SESSION. Read from a bounded head of the transcript, never the whole
# file: the largest real transcript measured on this machine was 663 MB, and an unbounded
# read inside a hook is a hang. The first records of a session can carry a null
# entrypoint, so the first non-null string wins.
entrypoint=""
if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  entrypoint="$(head -c "$HEAD_BYTES" "$transcript" 2>/dev/null | jq -R -r '
    (fromjson? // empty) | (.entrypoint // empty)
    | select(type == "string" and length > 0)' 2>/dev/null | head -1)"
fi

FORGE="${SKILLUSE_FORGE:-}"
if [ -z "$FORGE" ]; then
  # Resolved relative to this script, following symlinks: both install paths run it from
  # the checkout, and `skillforge` may not be on the PATH a hook inherits.
  self="$0"; hops=0
  while [ -L "$self" ] && [ "$hops" -lt 32 ]; do
    link="$(readlink "$self")"
    case "$link" in /*) self="$link" ;; *) self="$(dirname "$self")/$link" ;; esac
    hops=$(( hops + 1 ))
  done
  FORGE="$(cd "$(dirname "$self")/.." 2>/dev/null && pwd)/bin/skillforge"
fi
[ -x "$FORGE" ] || exit 0

set -- use --name "$skill" --session "$sid" --recorded live
# `if`, not `a && b || c`: with the && form, a `set` that ever returned non-zero would run
# the || arm as well and the row would carry both --failed and --ok.
if [ "$mode" = "fail" ]; then set -- "$@" --failed; else set -- "$@" --ok; fi
[ -n "$cwd" ]        && set -- "$@" --cwd "$cwd"
[ -n "$entrypoint" ] && set -- "$@" --entrypoint "$entrypoint"
[ -n "$tuid" ]       && set -- "$@" --tool-use-id "$tuid"

"$FORGE" "$@" >/dev/null 2>&1
exit 0

# Closes the brace group opened just under `set -uo pipefail`. See the note there.
}
