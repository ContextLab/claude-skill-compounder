#!/usr/bin/env bash
# States the user's own requests, verbatim, at the five moments a session is most likely
# to have lost them.
#
# THE GAP THIS CLOSES. Everything else in this package is addressed to the session's
# ATTENTION -- a nudge, a queue, a checkpoint -- and nothing carries the CONTENT the
# session lost. A reminder that says "check whether a skill exists" competes with the
# task; a reminder that says "the user asked, verbatim: ..." IS the task. This hook
# delivers THE MISSION: the prompts the user actually typed in this session, oldest
# first, as a record of what was said.
#
# ====================================================================================
# ONE SOURCE OF TRUTH, AND IT IS NOT OURS. The prompts come from claude-history-surfer's
# store, <store root>/projects/<slug>/prompts.jsonl, which already records every
# prompt once per project and filters the harness's pseudo-prompts. This script keeps NO
# copy (principle i of notes/2026-09-03-mission-and-lessons-design.md). If history-surfer
# is not installed, or that project has no store, this hook emits nothing and exits 0 --
# the installer's `skillforge doctor` is the surface that reports the missing dependency,
# not a second capture path that would drift from the first.
#
# THE STORE ROOT IS DERIVED, NEVER HARDCODED, and it is three rungs:
#
#   1. MISSION_SURFER_ROOT          this hook's own override, for tests and for anyone
#                                   whose store is somewhere neither rung below finds.
#   2. CLAUDE_HISTORY_SURFER_DIR    history-surfer's own override
#                                   (`history_surfer/config.py:39-41`).
#   3. ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/history-surfer
#                                   its data directory under the claude dir
#                                   (`history_surfer/config.py:37-42`, whose last rung is
#                                   `claude_dir() / "history-surfer"`).
#
# Rung 3 used to be the literal `$HOME/.claude/history-surfer`, and that was the defect:
# an install into a non-default `--claude-dir` puts the store under THAT directory, so
# this hook read an empty path and went silent with nothing to say why. Found by the E2E
# journey on 2026-09-03, which had to set MISSION_SURFER_ROOT by hand to make its own
# steps measure the hook rather than the gap.
#
# ONE DIVERGENCE FROM history-surfer, STATED RATHER THAN GLOSSED. Its rung 3 reads
# `CLAUDE_HISTORY_SURFER_CLAUDE_DIR` (`history_surfer/config.py:29-34`), NOT
# `CLAUDE_CONFIG_DIR`, which appears nowhere in that repository. `CLAUDE_CONFIG_DIR` is
# what the rest of THIS package falls back to (`bin/skillnote:284`, `bin/skillforge:1381`)
# and it is what Claude Code itself honours, so it is the rung used here. The two agree
# whenever neither variable is set, which is the default on every machine; they diverge
# only for someone who has exported one of them, and MISSION_SURFER_ROOT is the rung that
# settles it for them.
#
# CLAUDE_CONFIG_DIR DOES REACH A HOOK, measured on cli 2.1.259 (2026-09-03) by wiring a
# UserPromptSubmit hook that dumps its own `env`: exported into the environment `claude`
# was started with, it is one of the 77 variables the hook process sees; left unset, it is
# absent and Claude Code does not synthesise one. So the hook process inherits it exactly
# when there is one to inherit, which is what makes rung 3 correct in both directions.
# There is nothing in the JSON PAYLOAD about it -- this is process environment, not
# payload.
#
# THE SLUG IS HISTORY-SURFER'S, REPRODUCED EXACTLY: every non-alphanumeric character of
# `.cwd` becomes `-`, with NO collapsing of runs, empty becoming "unknown"
# (`history_surfer/store.py:slugify_cwd`, which mirrors Claude Code's own scheme). One
# character of difference here reads an empty directory and this hook goes silent with
# nothing to say why.
#
# ROW SHAPE (history-surfer, measured against the live store on 2026-09-03):
#   {"ts":"2026-08-25T02:43:51Z","session_id":"...","cwd":"...","project_slug":"...",
#    "seq":4,"prompt":"...","is_command":false,"text_final":true,"source":"transcript"}
# Rows are keyed (session_id, seq) and the file is append-only, so the same seq can appear
# twice; the winner is chosen the way `store.py:_prefer` chooses it -- a `text_final` row
# beats one without, otherwise the later `ts` wins. `overlay.jsonl`, when present, is
# replayed in `ts` order for its `delete`/`restore`/`edit` events, so a prompt the user
# deleted through `surfer` is not restated here.
#
# ====================================================================================
# FIVE MOMENTS, ONE SCRIPT. It dispatches on `.hook_event_name` and takes NO argv.
#
#   SessionStart     `.source` in compact|resume -> the mission. `startup` emits nothing:
#                    at startup nothing has been asked yet.
#   PreToolUse       tool_name Agent|Task|Workflow -> the mission, before an expensive
#                    dispatch. Any other tool -> the mission again once MISSION_INTERVAL
#                    seconds have passed since this session's last delivery of any kind,
#                    and NEVER inside a subagent (a payload carrying `agent_id`), which
#                    got the mission at SubagentStart.
#   SubagentStart    the mission plus one closing sentence recording that the parent's
#                    instructions to that agent are above it.
#   UserPromptSubmit a prompt of fewer than MISSION_SHORT_WORDS words ("continue", "yes",
#                    "ok do it") is the prompt that relies on memory -> the last
#                    substantive request before it. A longer prompt emits nothing.
#   Stop             a completion claim, at least MISSION_STOP_MIN_TOOLS tool calls in
#                    the turn, and `stop_hook_active` false -> ONE block per prompt_id
#                    whose reason is the mission.
#
# Anything else exits 0 in silence.
#
# THE STOP REGEX, in full, matched case-insensitively against `.last_assistant_message`:
#
#   (^|[^A-Za-z])(done|complete|completed|finished|implemented|landed|all tests pass|all
#   tests passed|all tests passing|ready to merge)([^A-Za-z]|$)
#
# It is deliberately short. A longer list is a longer false-positive surface, and this arm
# spends the user's turn when it is wrong. The bracket classes stand in for `\b`, which is
# a GNU extension `grep -E` does not carry on BSD.
#
# ====================================================================================
# THE EMIT SHAPES ARE MEASURED, NOT ASSUMED (Claude Code 2.1.259, 2026-09-03; the probe
# logs are the twelve runs behind docs/CLAUDE-CODE-BEHAVIOR.md's wave-2 entries):
#
#   SessionStart / SubagentStart:
#     {"hookSpecificOutput":{"hookEventName":"<event>","additionalContext":"<text>"}}
#   PreToolUse / UserPromptSubmit (`suppressOutput`, as hooks/remind.sh emits):
#     {"suppressOutput":true,
#      "hookSpecificOutput":{"hookEventName":"<event>","additionalContext":"<text>"}}
#   Stop:
#     {"decision":"block","reason":"<text>"}
#
# SessionStart's `additionalContext` reaches the model on startup, resume AND compact.
# SubagentStart's reaches the SUBAGENT only, never the parent; UserPromptSubmit's and
# SessionStart's reach the PARENT only. `permissionDecision:"allow"` with a reason reaches
# NOTHING, silently -- do not reach for it here.
#
# WORDING IS PART OF THE MEASUREMENT. Imperative wording in an injected context was
# refused as prompt injection in 2 of 4 runs, and the Stop arm's own probe came back with
# the model quoting the reason and declining the instruction inside it. So every line this
# script emits is a STATEMENT OF FACT -- a record of what was asked and when -- and never
# an instruction. That includes the closing sentences on the SubagentStart and Stop arms.
#
# THE CHANNEL THIS DESIGN DECLINES. `PreToolUse` on `Agent` can rewrite the subagent's
# prompt through `updatedInput`, measured working. It is not used: rewriting a subagent's
# instructions behind the parent's back leaves the parent reading a transcript that does
# not say what the subagent was told. `SubagentStart` says the same thing in the open.
#
# ====================================================================================
# WHAT IT NEVER DOES. It never denies a tool call, never sets `systemMessage`, never
# writes to history-surfer's store, never blocks twice for one prompt_id, and exits 0 on
# every failure path.
#
# IDEMPOTENCE. With both wirings active (settings.json AND hooks/hooks.json) every event
# is delivered twice, so each is claimed once under <state>/mission/<sid>/seen/ with an
# atomic `mkdir`, keyed on `tool_use_id`, `agent_id` or `prompt_id` -- and, when the
# payload carries none of those (a SessionStart with `source:"resume"` carries no id at
# all), on a digest of the payload itself, which is byte-identical across the two
# deliveries because it is the same event. The session id is sanitised with the IDENTICAL
# expression every other script in this package uses; one spelling difference makes a
# single event two claims under two names. The claim is taken only once the delivery is
# really going to happen, which is the bug hooks/session-review.sh shipped first.
#
# THE TURN'S TOOL COUNT is one byte appended to <state>/mission/<sid>/tools/<prompt_id>
# per DISTINCT tool_use_id, claimed separately from the delivery claim, because counting
# happens on every PreToolUse whether or not anything is emitted. A single-byte `>>` is an
# atomic append, so the two wirings cannot lose a count to each other. It counts a
# subagent's own tool calls too: they carry the parent's prompt_id and they are work done
# in the turn. It is a FLOOR -- a tool call this hook never saw is not in it.
#
# PRUNE. <state>/mission/<sid>/ is one directory per session that reached this hook, and
# nothing else sweeps it: `prune_stale_state()` in hooks/compound-improvement.sh walks
# <state>/reminders/ and hooks/remind.sh's own sweep walks <state>/remind/, both of them
# deliberately different directories. So this script sweeps its own tree, in the same shape
# that one does: on a 1-in-MISSION_PRUNE_EVERY draw it removes every session directory
# under <state>/mission/ whose mtime is more than MISSION_PRUNE_TTL seconds behind its own
# clock, and NEVER the current session's, whatever its age. Age is measured against
# MISSION_NOW and not by `find -mtime`, which reads the wall clock and would put the sweep
# beyond a pinned test.
#
# IT RUNS WHERE NOTHING IS DUE. The one call site is the periodic arm's not-yet-due exit --
# the ordinary tool call that delivers nothing, which is by a wide margin the most frequent
# event this hook sees. So every path that is about to emit reaches its `jq` with no `stat`
# in front of it, and the sweep is charged neither to a subagent (that branch has already
# exited on `agent_id`) nor to the first tool call of a session (which seeds `last` and
# exits). It walks ONE level of directories under <state>/mission/ and nothing else, so
# hits.jsonl -- a file, like the `.hits.XXXXXX` a trim leaves behind -- is out of reach by
# construction, and a name that is not a sanitised session id is left alone whatever its
# age.
#
# COST, MEASURED. One `cat` for the payload, one `jq` for the payload's scalars, a
# `tail -c | grep -F | tail -n` pipeline over the store, one `jq` for the render, one
# `tail` to split its first line off, and one `jq` for the emit. On a 200-prompt store:
# see tests/test_mission.py::CostTest, which prints the per-event medians on every run and
# fails above 150 ms. The common case is a missing store, which costs one `cat` and one
# `[ -s ]`.
#
# LIMITS, STATED RATHER THAN HIDDEN.
#   - The store is read as the last MISSION_MAX_BYTES of the file, then the lines matching
#     this session id, then the last MISSION_MAX_ROWS of those. A project store larger
#     than MISSION_MAX_BYTES loses its OLDEST rows, so a very old session in a very large
#     project can lose its first request. 32 MB is roughly 130,000 prompts.
#   - Level B (relevant prompts from OTHER projects) is not read here. `surfer search
#     --all` is one command away through the `history-surfer` skill.
#   - <state>/mission/<sid>/ holds one byte per tool call and one empty directory per
#     claimed event, and the sweep below removes only OTHER sessions' directories, by age.
#     A session that stays live longer than MISSION_PRUNE_TTL keeps its own tree whatever
#     it has grown to, which is the right way round: a claim removed from under a live
#     session re-opens the double delivery, and a tool count removed zeroes the turn the
#     Stop arm is about to judge.
#   - Every constant below is unvalidated, like the other six in this package. Do not tune
#     them before bin/skillreport has real data (docs/measurement.md).
#
# ENVIRONMENT
#   MISSION_ENABLED        (1)        0 disables the whole script.
#   MISSION_SURFER_ROOT    ()         history-surfer's data directory. Rung 1 of three;
#                                     falls through to CLAUDE_HISTORY_SURFER_DIR, then to
#                                     ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/history-surfer.
#                                     See "THE STORE ROOT IS DERIVED" above.
#   MISSION_FIRST_CHARS    (1200)     characters of the first substantive request quoted.
#   MISSION_RECENT         (3)        most recent requests quoted alongside it.
#   MISSION_EACH_CHARS     (400)      characters of each of those.
#   MISSION_MAX_CHARS      (2400)     characters of the whole rendered mission; clamped to
#                                     60000 so the emit cannot approach Linux's 131072
#                                     MAX_ARG_STRLEN.
#   MISSION_INTERVAL       (1200)     seconds between periodic deliveries in one session.
#   MISSION_SHORT_WORDS    (6)        a prompt under this many words is the ambiguity
#                                     proxy, and this is also what "substantive" means.
#   MISSION_STOP_MIN_TOOLS (8)        tool calls in the turn before the Stop arm may fire.
#   MISSION_MAX_ROWS       (2000)     store lines read for one session, and the length
#                                     hits.jsonl is trimmed to on write.
#   MISSION_MAX_BYTES      (33554432) bytes read from the tail of the store.
#   MISSION_PRUNE_TTL      (604800)   seconds a session directory under <state>/mission/
#                                     may go unchanged before a sweep removes it.
#   MISSION_PRUNE_EVERY    (25)       events between sweeps; 0 switches the sweep off.
#   MISSION_NOW            ()         pinned clock, epoch seconds. Its own, not borrowed:
#                                     pinning another script's clock does nothing to this
#                                     one.
#   SKILL_COMPOUNDER_STATE ()         state root ($HOME/.claude/skill-compounder).
set -uo pipefail

# ------------------------------------------------------------------------------------
# THE ENTIRE BODY OF THIS SCRIPT IS ONE BRACE GROUP, AND THE `}` AT THE END OF THE FILE IS
# WHAT CLOSES IT. bash reads a script LAZILY, by byte offset, and resumes at that offset in
# whatever the file holds AT THAT MOMENT; every file in this package runs by absolute path
# out of the checkout, so one `git pull` rewrites the bytes of a run already in flight. A
# brace group is a single compound command, so the whole file must parse in ONE pass before
# any of it runs. The `exit` before the closing `}` is load-bearing too: a group protects
# its body and nothing past it, and a script that falls off its end can have bash resume
# past `}` and execute prepended text -- measured, running the whole body a SECOND time.
# tests/test_script_wrapping.py enforces both halves; docs/DESIGN.md has the reproduction.
# ------------------------------------------------------------------------------------
{

# HOME can be unset (cron, a stripped env, a container). Under `set -u` reading it aborts
# the script non-zero, which is the one thing a hook may never do.
: "${HOME:=/tmp}"

ENABLED="${MISSION_ENABLED:-1}"
[ "$ENABLED" = "0" ] && exit 0

ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
DIR="$ROOT/mission"
HITS="$DIR/hits.jsonl"
# The store root, three rungs, header above. `:-` and not `-` at every rung: an exported
# but EMPTY variable is a typo, not a choice, and taking it would silence the hook.
SURFER_ROOT="${MISSION_SURFER_ROOT:-}"
[ -n "$SURFER_ROOT" ] || SURFER_ROOT="${CLAUDE_HISTORY_SURFER_DIR:-}"
[ -n "$SURFER_ROOT" ] || SURFER_ROOT="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/history-surfer"

FIRST_CHARS="${MISSION_FIRST_CHARS:-1200}"
RECENT="${MISSION_RECENT:-3}"
EACH_CHARS="${MISSION_EACH_CHARS:-400}"
MAX_CHARS="${MISSION_MAX_CHARS:-2400}"
INTERVAL="${MISSION_INTERVAL:-1200}"
SHORT_WORDS="${MISSION_SHORT_WORDS:-6}"
STOP_MIN_TOOLS="${MISSION_STOP_MIN_TOOLS:-8}"
MAX_ROWS="${MISSION_MAX_ROWS:-2000}"
MAX_BYTES="${MISSION_MAX_BYTES:-33554432}"
PRUNE_TTL="${MISSION_PRUNE_TTL:-604800}"
PRUNE_EVERY="${MISSION_PRUNE_EVERY:-25}"

# Shape AND magnitude guards on every tunable, so a typo'd export cannot reach an
# arithmetic test and print `[: integer expected` on the user's stderr from a hook.
# THE MAGNITUDE HALF WAS MISSING and the shape half cannot stand in for it: a value
# of 23 nines is all digits, so it passed `*[!0-9]*` untouched and then blew up in
# `[ "$PRUNE_EVERY" -ge 1 ]`, which is bash reporting `integer expression expected`
# on a stderr that is still the user's terminal. `???????????*` is 11 `?`, so anything of 11
# digits or more is out of range and takes the DEFAULT -- not zero, and not a clamp
# to the ceiling: an out-of-range export is a typo, and the documented default is
# the only value this header promises. bin/skillforge:327 spells it the same way.
case "$FIRST_CHARS"    in ''|*[!0-9]*|???????????*) FIRST_CHARS=1200 ;; esac
case "$RECENT"         in ''|*[!0-9]*|???????????*) RECENT=3 ;; esac
case "$EACH_CHARS"     in ''|*[!0-9]*|???????????*) EACH_CHARS=400 ;; esac
case "$MAX_CHARS"      in ''|*[!0-9]*|???????????*) MAX_CHARS=2400 ;; esac
case "$INTERVAL"       in ''|*[!0-9]*|???????????*) INTERVAL=1200 ;; esac
case "$SHORT_WORDS"    in ''|*[!0-9]*|???????????*) SHORT_WORDS=6 ;; esac
case "$STOP_MIN_TOOLS" in ''|*[!0-9]*|???????????*) STOP_MIN_TOOLS=8 ;; esac
case "$MAX_ROWS"       in ''|*[!0-9]*|???????????*) MAX_ROWS=2000 ;; esac
case "$MAX_BYTES"      in ''|*[!0-9]*|???????????*) MAX_BYTES=33554432 ;; esac
case "$PRUNE_TTL"      in ''|*[!0-9]*|???????????*) PRUNE_TTL=604800 ;; esac
case "$PRUNE_EVERY"    in ''|*[!0-9]*|???????????*) PRUNE_EVERY=25 ;; esac
[ "$MAX_CHARS" -lt 1 ] && MAX_CHARS=1
# The emitted text travels in ONE argv element to `jq --arg`. Linux caps a single argv
# element at MAX_ARG_STRLEN, a hard 131072 bytes that a larger ARG_MAX does not raise, so
# an unbounded MISSION_MAX_CHARS would emit nothing on Ubuntu and everything on macOS.
[ "$MAX_CHARS" -gt 60000 ] && MAX_CHARS=60000
[ "$FIRST_CHARS" -gt "$MAX_CHARS" ] && FIRST_CHARS="$MAX_CHARS"
[ "$EACH_CHARS" -gt "$MAX_CHARS" ] && EACH_CHARS="$MAX_CHARS"
[ "$MAX_ROWS" -lt 1 ] && MAX_ROWS=1
[ "$MAX_BYTES" -lt 1 ] && MAX_BYTES=1

command -v jq >/dev/null 2>&1 || exit 0

# stdin must be drained whatever happens next: a hook that exits without reading its
# payload can leave the caller writing into a closed pipe.
payload="$(cat)"
[ -n "$payload" ] || exit 0

now="${MISSION_NOW:-}"
case "$now" in ''|*[!0-9]*) now="$(date +%s 2>/dev/null)" ;; esac
case "$now" in ''|*[!0-9]*) exit 0 ;; esac

jqr() { printf '%s' "$payload" | jq -r "$1" 2>/dev/null; }

# US (0x1f), and NOT a tab. A tab is IFS *whitespace*, so a run of them delimits ONE field
# and `read` collapses `a<TAB><TAB>b` into two fields rather than three -- which silently
# shifts every field after the first EMPTY one, and most of these fields are empty on most
# events. A non-whitespace IFS character delimits exactly one field each time.
SEP="$(printf '\037')"

head_line="$(jqr '[(.hook_event_name//""),(.session_id//""),(.cwd//""),(.source//""),
                   (.tool_name//""),(.tool_use_id//""),(.agent_id//""),(.prompt_id//""),
                   (if (.stop_hook_active // false) then "1" else "0" end)]
                  | map(tostring | gsub("[\n\t\r]";" ")) | join("")')"
[ -z "$head_line" ] && exit 0
IFS="$SEP" read -r event sid_raw cwd source tool tuid aid pid_raw stopactive <<EOF
$head_line
EOF

case "$event" in
  SessionStart|UserPromptSubmit|PreToolUse|SubagentStart|Stop) ;;
  *) exit 0 ;;
esac

# ------------------------------------------------------------------- the store
# history-surfer's slug, reproduced exactly: every non-alphanumeric becomes `-`, runs are
# NOT collapsed, and an empty cwd is "unknown". `tr -c` complements the set, and `printf
# '%s'` emits no trailing newline for it to translate into one more `-`.
if [ -n "$cwd" ]; then
  slug="$(printf '%s' "$cwd" | tr -c 'A-Za-z0-9' '-')"
else
  slug=""
fi
[ -z "$slug" ] && slug="unknown"

STORE="$SURFER_ROOT/projects/$slug/prompts.jsonl"
OVERLAY="$SURFER_ROOT/projects/$slug/overlay.jsonl"

# ------------------------------------------------------------------- prune
# Sampled, and with TWO call sites, neither of which is about to emit anything: the
# periodic arm's not-yet-due exit, and the missing-store exit above ("PRUNE" and "IT RUNS
# WHERE NOTHING IS DUE" in the header). The second one is what sweeps a project whose store
# has gone away, which the first can never reach because the script has already exited.
# It walks ONE level of directories under $DIR and nothing else -- hits.jsonl and
# the `.hits.XXXXXX` a trim leaves behind are files, which the directory-only glob never
# lists, and $ROOT's other trees are siblings of $DIR and out of reach by construction.
#
# The current session's own <sid>/ is skipped whatever its age. `seen/` is what stops the
# second wiring delivering the same event twice and `tools/<pid>` is the count the Stop arm
# reads; removing either from under a live session is the trap hooks/session-review.sh
# shipped in the other direction, a record whose absence is indistinguishable from
# never-fired.
#
# A name that is not a sanitised session id is left alone. Every directory this script
# creates under $DIR is named by `tr -c 'A-Za-z0-9._-' '_' | cut -c1-96`, so anything
# outside that charset, or longer than that, was put there by something else and is not
# ours to remove.
#
# One `stat` over every directory, GNU form first and VALIDATED, then BSD: on GNU `-f`
# means --file-system, the bogus `%m` there still prints the valid part of the format, and
# a bare `A || B` chain would capture it (statusline/statusline.sh has the same note). A
# directory whose mtime does not parse is left alone, and so is one from the future.
prune_stale_sessions() {
  [ "$PRUNE_EVERY" -ge 1 ] || return 0
  [ $(( ${RANDOM:-0} % PRUNE_EVERY )) -eq 0 ] || return 0
  [ -d "$DIR" ] || return 0
  set -- "$DIR"/*/
  [ -d "$1" ] || return 0
  ps_lines="$(stat -c '%Y %n' "$@" 2>/dev/null)"
  ps_first="${ps_lines%% *}"
  case "$ps_first" in
    ''|*[!0-9]*) ps_lines="$(stat -f '%m %N' "$@" 2>/dev/null)" ;;
  esac
  [ -n "$ps_lines" ] || return 0
  printf '%s\n' "$ps_lines" | while read -r ps_m ps_p; do
    case "$ps_m" in ''|*[!0-9]*) continue ;; esac
    ps_p="${ps_p%/}"
    case "$ps_p" in "$DIR"/*) ;; *) continue ;; esac
    [ "$ps_p" = "$SDIR" ] && continue
    ps_b="${ps_p##*/}"
    case "$ps_b" in ''|*[!A-Za-z0-9._-]*) continue ;; esac
    [ "${#ps_b}" -le 96 ] || continue
    ps_age=$(( now - ps_m ))
    [ "$ps_age" -gt "$PRUNE_TTL" ] || continue
    rm -rf "$ps_p" 2>/dev/null
  done
  return 0
}

# ------------------------------------------------------------------- ids and state
# ONE sanitising site, called from two places: here and the missing-store exit below, which
# sweeps before it leaves. Duplicating the expression is how the two spellings of an id
# that .claude/CLAUDE.md warns about get made, so the second caller calls this instead.
#
# The session id is sanitised with the IDENTICAL expression every other script in this
# package uses. 96 characters is far longer than a UUID and safely under NAME_MAX. `.` and
# `..` are inside that character class, so the sanitiser passes them through unchanged and
# `$DIR/$sid` then names $DIR itself or its PARENT -- the state root, beside ledger.jsonl.
# The guard is one line, byte-identical in every script here that keys on an id, and it
# subsumes the `nosession` default this block used to carry: every caller has already
# tested `sid_raw`, so the '' arm is the belt.
set_sdir() {
  sid="$(printf '%s' "$sid_raw" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
  case "$sid" in ''|.|..) sid=_ ;; esac
  SDIR="$DIR/$sid"
}

# THE COMMON CASE, and deliberately the cheapest path in the script: no history-surfer
# store means no mission, and that is true for every user who has not installed it. The
# hook keeps no fallback capture of its own -- `skillforge doctor` reports the missing
# dependency instead.
#
# IT SWEEPS BEFORE IT LEAVES, because <state>/mission/<sid>/ OUTLIVES the store. A project
# whose history-surfer store is deleted, moved, or renamed under it exits here on every
# event afterwards, and until this branch existed that meant its session trees -- one byte
# per tool call and one empty directory per claimed event -- were never swept again by
# anything. `[ -d "$DIR" ]` is a shell builtin and the sweep is sampled behind it, so the
# user who never installed history-surfer, and therefore has no $DIR either, still reaches
# `exit 0` with no process start on this path at all: that is what
# tests/test_mission.py::CostTest measures and it is unchanged.
if [ ! -s "$STORE" ]; then
  if [ -d "$DIR" ] && [ -n "$sid_raw" ]; then
    set_sdir
    prune_stale_sessions
  fi
  exit 0
fi
[ -n "$sid_raw" ] || exit 0
set_sdir

pid="$pid_raw"
[ -z "$pid" ] && pid="noprompt"
pid="$(printf '%s' "$pid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
case "$pid" in ''|.|..) pid=_ ;; esac

# Nothing outside this script looks a record up under this digest, so unlike
# hooks/precompact.sh's `hash_of` it carries no cross-script contract -- but the idiom is
# the same one, and for the same reason: `awk printf` rather than `print`, because `tr -c`
# would otherwise fold the trailing newline into the digest.
hash_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 1
  elif command -v sha1sum >/dev/null 2>&1; then sha1sum
  else cksum
  fi | awk '{printf "%s", $1; exit}' | tr -c 'A-Za-z0-9' '_'
}

eid=""
case "$event" in
  PreToolUse)       eid="$tuid" ;;
  SubagentStart)    eid="$aid" ;;
  UserPromptSubmit) eid="$pid_raw" ;;
  Stop)             eid="$pid_raw" ;;
  SessionStart)     eid="$pid_raw" ;;
esac
# A SessionStart with `source:"resume"` carries no id of any kind. Both wirings receive the
# SAME payload bytes for one event, so a digest of the payload is a stable event key; a
# machine with none of the three digest tools falls back to no key, which acts every time
# rather than never.
if [ -z "$eid" ]; then
  eid="$(printf '%s' "$payload" | hash_of 2>/dev/null)"
fi
if [ -n "$eid" ]; then
  eid="$(printf '%s' "$eid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
  case "$eid" in ''|.|..) eid=_ ;; esac
fi

# Fail OPEN, like hooks/compound-improvement.sh's reminder claim: `mkdir` failing because
# the marker exists is a duplicate and must be dropped, while `mkdir` failing for any other
# reason (a read-only state directory, a full disk) must not silence the mission for the
# rest of the session. The two are told apart by testing the marker afterwards.
claim_once() {
  co_dir="$SDIR/seen"
  mkdir -p "$co_dir" 2>/dev/null || return 0
  [ -z "$2" ] && return 0
  if mkdir "$co_dir/$1-$2" 2>/dev/null; then return 0; fi
  [ -d "$co_dir/$1-$2" ] && return 1
  return 0
}

# ------------------------------------------------------------------- the turn's tool count
# Counting happens on EVERY PreToolUse, delivery or not, so its claim is taken here rather
# than beside the delivery claim: they are two different actions and one must not consume
# the other's marker. One byte per distinct tool_use_id; a single-byte append is atomic, so
# the duplicate delivery cannot lose a count to a read-modify-write race.
if [ "$event" = "PreToolUse" ]; then
  if claim_once "count" "$eid"; then
    if mkdir -p "$SDIR/tools" 2>/dev/null; then
      printf 'x' 2>/dev/null >> "$SDIR/tools/$pid" || :
    fi
  fi
fi

# ------------------------------------------------------------------- moment selection
# `moment` is both the arm and half of the claim marker's name, so two events carrying the
# same id cannot claim each other.
moment=""
render_mode="full"
case "$event" in
  SessionStart)
    # `startup` emits nothing: at startup nothing has been asked yet, and a mission read
    # from a previous session in the same project would be a statement about work the user
    # is not doing.
    case "$source" in
      compact|resume) moment="resume" ;;
      *) exit 0 ;;
    esac
    ;;
  SubagentStart)
    moment="subagent"
    ;;
  PreToolUse)
    case "$tool" in
      Agent|Task|Workflow)
        moment="dispatch"
        ;;
      *)
        # The periodic arm never fires inside a subagent: it got the whole mission at
        # SubagentStart, and a second copy partway through is noise addressed to a session
        # that already has it.
        [ -n "$aid" ] && exit 0
        last_st=""
        [ -f "$SDIR/last" ] && last_st="$(tr -cd '0-9' < "$SDIR/last" 2>/dev/null)"
        case "$last_st" in
          ''|*[!0-9]*)
            # No delivery yet in this session. The interval's clock starts at the first
            # event we see rather than at zero, so a fresh session does not get the mission
            # restated one tool call after the prompt that set it.
            mkdir -p "$SDIR" 2>/dev/null && printf '%s\n' "$now" > "$SDIR/last" 2>/dev/null
            exit 0
            ;;
        esac
        # Compared on |now - last|, so a clock that jumped backwards cannot silence the
        # periodic arm for the rest of the session.
        d=$(( now - last_st ))
        [ "$d" -lt 0 ] && d=$(( 0 - d ))
        # One of the sweep's TWO call sites: this event delivers nothing, and it is the
        # most frequent one this hook sees. An event that IS due falls through to the
        # render with no `stat` in front of it. The other site is the early return taken
        # when the prompt store is absent -- without it, a machine with no history-surfer
        # left before reaching the sweep and its session trees were never swept at all.
        [ "$d" -gt "$INTERVAL" ] || { prune_stale_sessions; exit 0; }
        moment="periodic"
        ;;
    esac
    ;;
  UserPromptSubmit)
    moment="ambiguity"
    render_mode="last"
    ;;
  Stop)
    [ "$stopactive" = "1" ] && exit 0
    moment="completion"
    ;;
esac

[ -n "$moment" ] || exit 0

TMP="$(mktemp -d 2>/dev/null)" || exit 0
cleanup() { [ -n "${TMP:-}" ] && rm -rf "$TMP" 2>/dev/null; }
trap cleanup EXIT

# ------------------------------------------------------------------- event-specific reads
# The current prompt, on the ambiguity arm only. history-surfer's own UserPromptSubmit hook
# writes the row for THIS prompt on THIS event, and hook ordering within one event is not
# defined, so the row may or may not be in the store by the time we read it. Excluding it
# by text covers both orders, which is what "never include the current prompt twice" means.
CUR=""
if [ "$event" = "UserPromptSubmit" ]; then
  CUR="$(jqr '(.prompt // "") | tostring | .[0:20000]')"
  [ -n "$CUR" ] || exit 0
  # Word count with no fork and no glob: `set -f` first, or a prompt containing `*` would
  # be counted as a directory listing.
  set -f
  # shellcheck disable=SC2086  # unquoted on purpose: this IS the word split
  set -- $CUR
  words=$#
  set +f
  set --
  [ "$words" -lt "$SHORT_WORDS" ] || exit 0
fi

if [ "$event" = "Stop" ]; then
  # The turn's tool count, from the bytes the PreToolUse arm appended. BSD `wc` pads its
  # count with spaces and a numeric guard reads a space as non-numeric -- the defect that
  # made hooks/claim-gate.sh's byte cap dead code -- so the padding is stripped first.
  tools_n=0
  if [ -f "$SDIR/tools/$pid" ]; then
    tools_n="$(wc -c < "$SDIR/tools/$pid" 2>/dev/null | tr -cd '0-9')"
  fi
  case "$tools_n" in ''|*[!0-9]*) tools_n=0 ;; esac
  [ "$tools_n" -ge "$STOP_MIN_TOOLS" ] || exit 0

  # The claim is only worth reading if the message looks like a completion claim. Sliced
  # from the END: a closing claim is at the end of a closing message, and an unbounded
  # slice would put a very long message into a shell variable for nothing.
  msg="$(jqr '(.last_assistant_message // "") | tostring | .[-20000:]')"
  [ -n "$msg" ] || exit 0
  STOP_RE='(^|[^A-Za-z])(done|complete|completed|finished|implemented|landed|all tests pass|all tests passed|all tests passing|ready to merge)([^A-Za-z]|$)'
  printf '%s\n' "$msg" | grep -qiE "$STOP_RE" 2>/dev/null || exit 0

  # One block per prompt_id, ever. `stop_hook_active` is the platform's own loop flag and
  # is checked above; this is the belt, and it fails CLOSED like hooks/claim-gate.sh's:
  # a reminder that goes missing costs a nudge, a block that fires twice from two racing
  # processes costs the user their turn twice.
  mkdir -p "$SDIR/stop" 2>/dev/null || exit 0
  mkdir "$SDIR/stop/$pid" 2>/dev/null || exit 0
fi

# ------------------------------------------------------------------- read the store
# Bounded three ways, cheapest first: the tail of the file in bytes, then the lines
# carrying this session id, then the last MISSION_MAX_ROWS of those. `grep -F -e` because
# a session id beginning with `-` would otherwise be read as an option; jq re-filters on
# the real field, so a substring hit costs nothing but a line.
tail -c "$MAX_BYTES" "$STORE" 2>/dev/null \
  | grep -F -e "$sid_raw" 2>/dev/null \
  | tail -n "$MAX_ROWS" > "$TMP/prompts" 2>/dev/null
[ -s "$TMP/prompts" ] || exit 0

: > "$TMP/overlay"
if [ -s "$OVERLAY" ]; then
  tail -c "$MAX_BYTES" "$OVERLAY" 2>/dev/null \
    | grep -F -e "$sid_raw" 2>/dev/null \
    | tail -n "$MAX_ROWS" > "$TMP/overlay" 2>/dev/null
fi
[ -f "$TMP/overlay" ] || : > "$TMP/overlay"

# ------------------------------------------------------------------- render
# `split("\n")` AND NOT `[splits("\n")]`, which computes the same value: `splits` is the
# REGEX form and compiles an Oniguruma match over the whole file. On a 500-row store that
# one character cost hooks/remind.sh 230 ms of its 270.
#
# `words` is built from LITERAL splits for the same reason: a regex word split runs once
# per prompt, and this runs before every tool call.
#
# The budget is applied by rendering every candidate -- the first substantive request alone,
# then with one recent request, then two, up to MISSION_RECENT -- and taking the longest
# that fits inside MISSION_MAX_CHARS. Dropping the OLDEST of the recent block first keeps
# the two things a session most needs: what was originally asked, and what was asked last.
JQ_RENDER='
def parse: split("\n") | map(select(length > 0)) | map(fromjson? // empty);
def words: tostring | split("\t") | join(" ") | split("\r") | join(" ")
           | split("\n") | join(" ") | split(" ") | map(select(length > 0)) | length;

($fc | tonumber) as $FC
| ($ec | tonumber) as $EC
| ($rc | tonumber) as $R
| ($mx | tonumber) as $MX
| ($sw | tonumber) as $SW
| ($promptsraw | parse | map(select(((.session_id // "") | tostring) == $sid))) as $rows
| ($overlayraw | parse | map(select(((.session_id // "") | tostring) == $sid))) as $ovr
| (reduce ($ovr | sort_by((.ts // "") | tostring))[] as $e ({};
     (($e.seq // 0) | tostring) as $k
     | .[$k] = ((.[$k] // {deleted: false, edited: null})
         | if ($e.op == "delete") then (.deleted = (($e.value // false) != false))
           elif ($e.op == "restore") then (.deleted = false)
           elif ($e.op == "edit") then (.edited = ($e.value))
           else . end))) as $OV
| (reduce $rows[] as $r ({};
     (($r.seq // 0) | tostring) as $k
     | if (.[$k] == null) then (.[$k] = $r)
       else ((.[$k]) as $c
             | ((($r.text_final // false) != false)) as $nf
             | ((($c.text_final // false) != false)) as $cf
             | if ($nf != $cf) then (if $nf then (.[$k] = $r) else . end)
               elif ((($r.ts // "") | tostring) >= (($c.ts // "") | tostring)) then (.[$k] = $r)
               else . end)
       end)) as $BY
| ([ $BY[] ] | sort_by(.seq // 0)) as $ord
| ([ $ord[]
     | . as $r
     | (($OV[(($r.seq // 0) | tostring)]) // {deleted: false, edited: null}) as $o
     | select((($o.deleted // false) != true))
     | select((($r.is_command // false) != true))
     | (if (($o.edited // null) != null) then ($o.edited | tostring)
        else (($r.prompt // "") | tostring) end) as $t
     | select(($t | length) > 0)
     | select((($cur | length) == 0) or ($t != $cur))
     | {seq: (($r.seq // 0)), t: $t} ]) as $P
| ($P | length) as $N
| if $N == 0 then empty
  else
    ([ range(0; $N) | select((($P[.].t) | words) >= $SW) ]) as $subs
    | if $mode == "last" then
        (if ($subs | length) > 0 then $subs[-1] else ($N - 1) end) as $li
        | ($P[$li].t) as $t
        | (if ($t | length) > $FC then ($t[0:$FC]) else $t end) as $s
        | ("The user'"'"'s last substantive request in this session, verbatim (request "
           + (($li + 1) | tostring) + " of " + ($N | tostring) + "):\n\"" + $s + "\""
           + (if ($t | length) > $FC
              then " (the first " + ($FC | tostring) + " of "
                   + (($t | length) | tostring) + " characters)"
              else "" end)) as $TXT
        | ($TXT[0:$MX]) as $OUT
        | "\($N) \($OUT | length)\n" + $OUT
      else
        (if ($subs | length) > 0 then $subs[0] else 0 end) as $fi
        | ([ range(0; $N) ] | (if $N > $R then .[($N - $R):] else . end)
           | map(select(. != $fi))) as $ri
        | ([ $P[] | (.t | length) ] | add // 0) as $TOT
        | ([ range(0; ($ri | length) + 1)
             | . as $k
             | ($ri[(($ri | length) - $k):]) as $rk
             | ((([$fi] + $rk)) | unique) as $sh
             | ([ $sh[]
                  | . as $i
                  | (if $i == $fi then $FC else $EC end) as $cap
                  | ($P[$i].t) as $t
                  | (if ($t | length) > $cap then ($t[0:$cap]) else $t end) as $s
                  | "(request " + (($i + 1) | tostring) + " of " + ($N | tostring)
                    + ") \"" + $s + "\""
                    + (if ($t | length) > $cap
                       then " (the first " + ($cap | tostring) + " of "
                            + (($t | length) | tostring) + " characters)"
                       else "" end) ]) as $lines
             | ([ $sh[]
                  | . as $i
                  | (if $i == $fi then $FC else $EC end) as $cap
                  | (($P[$i].t) | length)
                  | (if . > $cap then $cap else . end) ] | add // 0) as $shown
             | ($TOT - $shown) as $CUT
             | (if $CUT > 0
                then ("[... " + ($CUT | tostring)
                      + " characters of this session'"'"'s requests are not quoted here ...]")
                else "" end) as $mark
             | (if ($mark | length) == 0 then $lines
                elif ($lines | length) > 1 then ([$lines[0], $mark] + $lines[1:])
                else ($lines + [$mark]) end) as $body
             | ("The user'"'"'s requests in this session, verbatim, oldest first. "
                + ($N | tostring) + " recorded; " + (($sh | length) | tostring)
                + " quoted below.\n" + ($body | join("\n"))) ]) as $CAND
        | ([ $CAND[] | select((. | length) <= $MX) ]) as $fit
        | (if ($fit | length) > 0 then ($fit | max_by(length)) else ($CAND[0][0:$MX]) end) as $OUT
        | "\($N) \($OUT | length)\n" + $OUT
      end
  end
'

jq -n -r --rawfile promptsraw "$TMP/prompts" --rawfile overlayraw "$TMP/overlay" \
   --arg sid "$sid_raw" --arg cur "$CUR" --arg mode "$render_mode" \
   --arg fc "$FIRST_CHARS" --arg ec "$EACH_CHARS" --arg rc "$RECENT" \
   --arg mx "$MAX_CHARS" --arg sw "$SHORT_WORDS" \
   "$JQ_RENDER" > "$TMP/render" 2>/dev/null

[ -s "$TMP/render" ] || exit 0

# The count of this session's recorded prompts AND the rendered length ride on the FIRST
# line, so the render costs one jq rather than two. `read` is a builtin; `tail -n +2` is
# the one exec.
#
# THE LENGTH COMES FROM jq, NOT FROM `${#CTX}`, and that is not fussiness: bash counts
# characters only in a UTF-8 locale and BYTES otherwise, and these hooks run under
# whatever environment the harness hands them -- the suite's own minimal env has no LANG
# at all. A `chars` column that is codepoints on one machine and bytes on the next is a
# number nobody can act on, which is the failure mode the dead measurement layer of
# 2026-09-02 was made of. jq's `length` on a string is codepoints everywhere.
NPROMPTS=0
MCHARS=0
IFS=" " read -r NPROMPTS MCHARS < "$TMP/render" || exit 0
case "$NPROMPTS" in ''|*[!0-9]*) exit 0 ;; esac
case "$MCHARS" in ''|*[!0-9]*) exit 0 ;; esac
[ "$NPROMPTS" -ge 1 ] || exit 0
CTX="$(tail -n +2 "$TMP/render" 2>/dev/null)"
[ -n "$CTX" ] || exit 0

# ------------------------------------------------------------------- the closing sentences
# Both are STATEMENTS OF FACT. An imperative here was refused as prompt injection in 2 of 4
# measured runs, and the Stop arm's own probe had the model quote the reason and decline the
# instruction inside it.
SUFFIX=""
case "$moment" in
  subagent)
    SUFFIX="

The parent's instructions to this agent appear above these requests; they are what the
parent made of them."
    ;;
  completion)
    SUFFIX="

The message that ends this turn is the one the user will read against those requests. This
gate blocks at most once for this turn."
    ;;
esac
if [ -n "$SUFFIX" ]; then
  CTX="$CTX$SUFFIX"
  # Both suffixes are pure ASCII, so `${#}` is codepoints and bytes at once here.
  MCHARS=$(( MCHARS + ${#SUFFIX} ))
fi

# ------------------------------------------------------------------- claim, stamp, emit
# THE CLAIM IS TAKEN HERE, not earlier: an event whose render came back empty would
# otherwise have burned its claim, so the second delivery -- the one that might have matched
# after a concurrent write -- could never fire. That placement is the bug
# hooks/session-review.sh shipped first.
claim_once "$moment" "$eid" || exit 0

mkdir -p "$SDIR" 2>/dev/null || exit 0
printf '%s\n' "$now" > "$SDIR/last" 2>/dev/null || :

# Hand-built JSON, safe because every field is drawn from a charset already validated:
# `sid` and `aid` came through the sanitiser, `moment` is one of six literals set by the
# case above, and the three numbers are digits only. Nothing here can carry a quote or a
# backslash.
aid_json="null"
if [ -n "$aid" ]; then
  aid_safe="$(printf '%s' "$aid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
  case "$aid_safe" in ''|.|..) aid_safe=_ ;; esac
  aid_json="\"$aid_safe\""
fi
mkdir -p "$DIR" 2>/dev/null || :
printf '{"ts":%s,"session":"%s","moment":"%s","agent_id":%s,"chars":%s,"prompt_count":%s}\n' \
  "$now" "$sid" "$moment" "$aid_json" "$MCHARS" "$NPROMPTS" 2>/dev/null >> "$HITS" || :

# Bounded on write as well as on read, the way hooks/remind.sh bounds its hits log: one
# `wc` per DELIVERY, never per event, and the rewrite goes through a `mktemp` in the log's
# OWN directory so the `mv` is a rename(2) rather than a truncate in place. The spaces are
# stripped because BSD `wc` pads its count with them.
hits_n="$(wc -l < "$HITS" 2>/dev/null | tr -cd '0-9')"
case "$hits_n" in
  ''|*[!0-9]*) ;;
  *)
    if [ "$hits_n" -gt "$MAX_ROWS" ]; then
      hits_tmp="$(mktemp "$DIR/.hits.XXXXXX" 2>/dev/null)" || hits_tmp=""
      if [ -n "$hits_tmp" ]; then
        if tail -n "$MAX_ROWS" "$HITS" > "$hits_tmp" 2>/dev/null; then
          mv -f "$hits_tmp" "$HITS" 2>/dev/null || rm -f "$hits_tmp" 2>/dev/null
        else
          rm -f "$hits_tmp" 2>/dev/null
        fi
      fi
    fi
    ;;
esac

if [ "$moment" = "completion" ]; then
  jq -n --arg r "$CTX" '{decision:"block", reason:$r}' 2>/dev/null || exit 0
  exit 0
fi

case "$event" in
  SessionStart|SubagentStart)
    jq -n --arg ev "$event" --arg ctx "$CTX" \
      '{hookSpecificOutput:{hookEventName:$ev, additionalContext:$ctx}}' 2>/dev/null || exit 0
    ;;
  *)
    jq -n --arg ev "$event" --arg ctx "$CTX" \
      '{suppressOutput:true,
        hookSpecificOutput:{hookEventName:$ev, additionalContext:$ctx}}' 2>/dev/null || exit 0
    ;;
esac

exit 0

# Closes the brace group opened just under `set -uo pipefail`. See the note there.
}
