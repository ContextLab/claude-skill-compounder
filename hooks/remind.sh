#!/usr/bin/env bash
# Delivers a recorded reminder at the moment it applies, and never at any other moment.
#
# THE GAP THIS CLOSES. `skills/skill-compounder/SKILL.md` says the cheap branch of
# compounding is "write a note or update the project's CLAUDE.md". A note is only read if
# something reads it; a reminder ARRIVES. This hook is the arrival: a row recorded by
# `skillnote add --remind` names what it wants to fire on -- keywords in a prompt, a path
# being written, a command about to run -- and this script matches those and states the
# reminder back. No model, no judgement, no prose generation: a row either matches the
# rule it carries or it does not. Same shape as hooks/repeat-gate.sh, which is the one
# component here that both accumulates and fires.
#
# ====================================================================================
# TWO ARMS ON ONE SCRIPT. It dispatches on `.hook_event_name` and takes NO argv.
#
#   UserPromptSubmit -> keyword match against the prompt.
#   PreToolUse       -> `Bash`: normalised-command match. `Write`/`Edit`: path glob match.
#
# One PreToolUse entry with matcher `Bash|Write|Edit` covers both of the second arm's
# halves; splitting it into two entries would double the deliveries for no gain.
#
# ====================================================================================
# THE EMIT SHAPE IS MEASURED, NOT ASSUMED, and it was the open question this hook waited
# on. docs/CLAUDE-CODE-BEHAVIOR.md, "PreToolUse additionalContext reaches the model; an
# allow reason reaches nothing" (Claude Code 2.1.258, 2026-09-02):
#
#   {"suppressOutput":true,
#    "hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"<text>"}}
#
# reached the model in 3 of 3 runs, labelled `PreToolUse:Bash hook additional context:`.
# The obvious-looking alternative -- `permissionDecision:"allow"` with a reason -- reached
# NOTHING in 0 of 6, silently, with the call still allowed: a hook that looks like it is
# working and is saying nothing to anyone. Do not reach for it here.
#
# WORDING IS PART OF THE MEASUREMENT. The same field with IMPERATIVE wording was refused
# as prompt injection in 2 of 4 runs -- "that's a prompt-injection pattern, not something
# legitimately given to me by you or the system". With a neutral statement of fact it came
# back 3 of 3. So every line this script emits is framed as a record of something that
# happened:
#
#   Reminder recorded on <date> for this project: <text>
#
# and never as an instruction. A reminder whose TEXT is an imperative is still delivered
# inside that frame, which is why the frame is not optional.
#
# ====================================================================================
# WHAT IT NEVER DOES. It never denies, never sets `systemMessage`, never rewrites
# `reminders.jsonl` (removal is a tombstone appended by the CLI, and a hook that rewrote
# an append-only store from under a concurrent writer would lose rows), and exits 0 on
# every failure path with nothing on stdout.
#
# ====================================================================================
# STORE: <state>/reminders.jsonl, append-only, written by `bin/skillnote add --remind`.
#
#   {"id":"n1993847712x61","text":"...","scope":"/Users/j/proj","created":1756838400,
#    "source":"verdict","hits":0,
#    "match":{"keywords":["test","fail"],"paths":["tests/*.py"],"commands":["..."]}}
#
# A tombstone is {"id":"...","t":"remove","ts":...}; a row is skipped when a tombstone for
# its id carries a `ts` at or after its `created`.
#
# THE NAME IS A DELIBERATE NEAR-COLLISION. <state>/reminders/ is the directory
# hooks/compound-improvement.sh keeps its per-session counters in, and its
# `prune_stale_state()` deletes files under it older than seven days. `reminders.jsonl` is
# a SIBLING of that directory, not a file inside it, so the sweep cannot reach the store.
# tests/test_hook.py pins that, because the alternative is a reminder store that silently
# empties itself after a week.
#
# MATCHING, in the order it is applied:
#   1. SCOPE FIRST. A row whose `scope` is not `global` is considered only when the
#      payload's `.cwd` equals it or sits underneath it. A row with no scope at all is
#      treated as `global`.
#   2. KEYWORDS ARE **AND**, NOT OR. Every keyword must appear in the lowercased prompt.
#      OR-matching a two-word rule fires on either word and is worse than not firing: a
#      reminder that arrives when it does not apply teaches the reader to skip the next
#      one. A row with an empty `keywords` array therefore never matches a prompt.
#   3. COMMANDS ARE BYTE EQUALITY OF A NORMALISED SIGNATURE, and the normaliser is NOT
#      reimplemented here -- it is `hooks/repeat-gate.sh --norm-of Bash`, the same code
#      that decides what the repeat gate considers "the same call". Two implementations of
#      that normalisation would drift, and the drift would be invisible: a reminder that
#      simply stops firing. If repeat-gate.sh is not beside this script, command matching
#      is skipped entirely rather than approximated.
#   4. PATHS ARE SHELL GLOBS matched with `case`, against BOTH the absolute path and the
#      path relative to the row's scope, so `tests/*.py` written by a human works and so
#      does an absolute rule.
#
# RANKING AND CAP. score = 100 for a command match, +50 for a path match, +10 per keyword
# in the row. Ties break on fewer live hits first (an unheard reminder outranks one that
# has been delivered), then newer `created`. At most REMIND_MAX rows are emitted, and the
# cap is applied AFTER the cooldown filter: a reminder the cooldown is holding back must
# not consume a slot a fresh one could have used.
#
# COOLDOWN, per reminder per session. <state>/remind/<sid>/<id> holds the epoch it last
# fired, read with `cat` and never with `stat` (BSD and GNU disagree on -c/-f). The
# default REMIND_COOLDOWN=0 means once per session, ever. A positive value re-arms after
# that many seconds, compared on |now - stamp| so a clock that jumped backwards cannot
# silence a reminder forever. THE STAMP IS WRITTEN BEFORE THE EMIT and a reminder whose
# stamp cannot be written is dropped from the emit: a reminder that fires every event
# because its stamp is unwritable is worse than one that does not fire.
#
# HITS. The store is never rewritten, so a delivery appends
# {"id","ts","session","event"} to <state>/remind/hits.jsonl and `skillnote list` derives
# the live count from that log. The log is bounded on WRITE as well as on read: once it
# holds more than REMIND_MAX_ROWS lines it is rewritten to its last REMIND_MAX_ROWS, on
# the delivery path only and atomically (issue #33). It was bounded only on read, which
# kept every reader cheap while the file grew without limit.
#
# PRUNE. <state>/remind/<sid>/ and <state>/remind/<sid>.seen/ are one pair per session
# that heard a reminder, and the sweep in hooks/compound-improvement.sh cannot reach them
# (see the near-collision above). This script sweeps its own tree: on a 1-in-
# REMIND_PRUNE_EVERY draw it removes every session directory whose mtime is more than
# REMIND_PRUNE_TTL seconds behind its own clock, and NEVER the current session's pair,
# whatever their age -- a stamp removed from under a live session re-arms every cooldown
# in it. Age is measured against REMIND_NOW, not by `find -mtime`, which reads the wall
# clock and would put the sweep beyond a pinned test.
#
# COST, MEASURED. One `cat`, two `jq` for payload fields, one `tail` per file, one `jq`
# for selection, one `jq` for the emit, plus -- on a Bash call only -- one fork of
# repeat-gate.sh for the shared normaliser, and -- on a Write/Edit only -- one more `jq`
# and a shell loop for the globs. On a 500-row store (108 KB): 49 ms on a prompt, 60 ms on
# a Bash call, 66 ms on a Write, median of five, macOS, 2026-09-02. Printed by
# tests/test_remind.py::CostTest on every run, so the figure is one that was measured
# rather than guessed. REMIND_MAX_ROWS bounds every read at the last 2000 lines of each
# file. The common case is a missing store, which costs one `cat` and one `[ -s ]`. The
# prune adds one `stat` over the session directories on one event in REMIND_PRUNE_EVERY,
# and the hits cap adds one `wc` per delivery, never per event.
#
# ENVIRONMENT
#   SKILL_COMPOUNDER_REMIND  (1)     0 disables the whole script.
#   REMIND_MAX               (2)     most reminders in one emit.
#   REMIND_COOLDOWN          (0)     seconds before a reminder may fire again; 0 = once
#                                    per session.
#   REMIND_MAX_ROWS          (2000)  lines read from the tail of the store and hits log,
#                                    and the length the hits log is trimmed to on write.
#   REMIND_PRUNE_TTL         (604800) seconds a session directory under <state>/remind/
#                                    may go unchanged before a sweep removes it.
#   REMIND_PRUNE_EVERY       (25)    events between sweeps; 0 switches the sweep off.
#   REMIND_NOW               ()      pinned clock, epoch seconds. Its own, not borrowed:
#                                    pinning another script's clock does nothing to this
#                                    one.
#   SKILL_COMPOUNDER_STATE   ()      state root ($HOME/.claude/skill-compounder).
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

ENABLED="${SKILL_COMPOUNDER_REMIND:-1}"
ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
STORE="$ROOT/reminders.jsonl"
DIR="$ROOT/remind"
HITS="$DIR/hits.jsonl"
MAX="${REMIND_MAX:-2}"
COOLDOWN="${REMIND_COOLDOWN:-0}"
MAX_ROWS="${REMIND_MAX_ROWS:-2000}"
PRUNE_TTL="${REMIND_PRUNE_TTL:-604800}"
PRUNE_EVERY="${REMIND_PRUNE_EVERY:-25}"
# One reminder is one sentence. The cap bounds what a single malformed row can push into
# the model's context, and it is applied in jq so a multibyte text is cut on codepoints.
TEXT_CAP=300

[ "$ENABLED" = "0" ] && exit 0

# Shape AND magnitude guards on every tunable, so a typo'd export cannot reach an
# arithmetic test and print `[: integer expected` on the user's stderr from a hook.
# THE MAGNITUDE HALF WAS MISSING and the shape half cannot stand in for it: a value
# of 23 nines is all digits, so it passed `*[!0-9]*` untouched and then blew up in
# `[ "$PRUNE_EVERY" -ge 1 ]`, which is bash reporting `integer expression expected`
# on a stderr that is still the user's terminal. `???????????*` is 11 `?`, so anything of 11
# digits or more is out of range and takes the DEFAULT -- not zero, and not a clamp
# to the ceiling: an out-of-range export is a typo, and the documented default is
# the only value this header promises. bin/skillforge:327 spells it the same way.
case "$MAX"      in ''|*[!0-9]*|???????????*) MAX=2 ;; esac
case "$COOLDOWN" in ''|*[!0-9]*|???????????*) COOLDOWN=0 ;; esac
case "$MAX_ROWS" in ''|*[!0-9]*|???????????*) MAX_ROWS=2000 ;; esac
case "$PRUNE_TTL"   in ''|*[!0-9]*|???????????*) PRUNE_TTL=604800 ;; esac
case "$PRUNE_EVERY" in ''|*[!0-9]*|???????????*) PRUNE_EVERY=25 ;; esac
[ "$MAX" -lt 1 ] && exit 0
[ "$MAX_ROWS" -lt 1 ] && MAX_ROWS=1

command -v jq >/dev/null 2>&1 || exit 0

# stdin must be drained whatever happens next: a hook that exits without reading its
# payload can leave the caller writing into a closed pipe.
payload="$(cat)"

# THE COMMON CASE, and it is deliberately the cheapest path in the script: no store means
# no reminders, and that is true for every user who has never run `skillnote --remind`.
[ -s "$STORE" ] || exit 0

now="${REMIND_NOW:-}"
case "$now" in ''|*[!0-9]*) now="$(date +%s 2>/dev/null)" ;; esac
case "$now" in ''|*[!0-9]*) exit 0 ;; esac

jqr() { printf '%s' "$payload" | jq -r "$1" 2>/dev/null; }

# US (0x1f), and NOT a tab. A tab is IFS *whitespace*, so a run of them delimits ONE
# field and `read` collapses `a<TAB><TAB>b` into two fields rather than three -- which
# silently shifted every field after the first empty one. A UserPromptSubmit payload has
# no `.tool_name`, so that empty field is the common case, not the corner: it put the cwd
# into `tool` and left `cwd` empty, and every project-scoped reminder stopped matching
# while the two arms with no empty field ahead of them kept working. A non-whitespace IFS
# character delimits exactly one field each time, empty or not.
SEP="$(printf '\037')"

# Every scalar this script needs from the payload, in ONE jq call. The separator and both
# newline forms are squeezed out of each field first so the line cannot be mis-split; a
# real cwd or file_path containing one of those is pathological, and mis-parsing it is
# worse than not matching it.
head_line="$(jqr '[(.hook_event_name//""),(.session_id//""),(.tool_use_id//.prompt_id//""),
                   (.tool_name//""),(.cwd//""),(.tool_input.file_path//"")]
                  | map(tostring | gsub("[\n\t\r\u001f]";" ")) | join("\u001f")')"
[ -z "$head_line" ] && exit 0
IFS="$SEP" read -r event sid eid tool cwd fpath <<EOF
$head_line
EOF

# `mode` is both the arm and half of the claim marker's name, so a PreToolUse and a
# UserPromptSubmit carrying the same id cannot claim each other.
case "$event" in
  UserPromptSubmit) mode="prompt" ;;
  PreToolUse)
    case "$tool" in
      Bash)       mode="command" ;;
      Write|Edit) mode="path" ;;
      *) exit 0 ;;
    esac
    ;;
  *) exit 0 ;;
esac

# The session id is sanitised with the IDENTICAL expression every other script in this
# package uses. One spelling difference makes a single event two claims under two names,
# which is the whole point of claiming it. 96 characters is far longer than a UUID and
# safely under NAME_MAX everywhere.
[ -z "$sid" ] && sid="nosession"
sid="$(printf '%s' "$sid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
case "$sid" in ''|.|..) sid=_ ;; esac
if [ -n "$eid" ]; then
  eid="$(printf '%s' "$eid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
  case "$eid" in ''|.|..) eid=_ ;; esac
fi

SDIR="$DIR/$sid"

# ------------------------------------------------------------------- prune
# Sampled, the way hooks/compound-improvement.sh and the status-line cache sample theirs,
# because this runs before every Bash, Write and Edit call. It walks ONE level of
# directories under $DIR and nothing else: <state>/reminders.jsonl and <state>/reminders/
# are siblings of $DIR and out of reach by construction -- tests/test_remind.py pins that
# the way tests/test_hook.py pins the same relationship from the other side -- and
# hits.jsonl is a file, which the directory-only glob never lists.
#
# The current session's own <sid>/ and <sid>.seen/ are skipped whatever their age. The
# stamp is what "once per session" means, and the claim is what stops the second wiring
# delivering the same event twice; removing either from under a live session is the trap
# hooks/session-review.sh shipped in the other direction, a record whose absence is
# indistinguishable from never-fired.
#
# One `stat` over every directory, GNU form first and VALIDATED, then BSD: on GNU `-f`
# means --file-system, the bogus `%m` there still prints the valid part of the format,
# and a bare `A || B` chain would capture it (statusline/statusline.sh has the same note).
# A directory whose mtime does not parse is left alone, and so is one from the future.
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
    [ "$ps_p" = "$SDIR.seen" ] && continue
    ps_age=$(( now - ps_m ))
    [ "$ps_age" -gt "$PRUNE_TTL" ] || continue
    rm -rf "$ps_p" 2>/dev/null
  done
  return 0
}
prune_stale_sessions

TMP="$(mktemp -d 2>/dev/null)" || exit 0
cleanup() { [ -n "${TMP:-}" ] && rm -rf "$TMP" 2>/dev/null; }
trap cleanup EXIT

# Both reads are bounded by REMIND_MAX_ROWS. `tail` on a missing hits log is not an
# error worth failing on -- an empty file means every candidate has zero hits, which is
# the correct answer before anything has ever fired.
tail -n "$MAX_ROWS" "$STORE" > "$TMP/store" 2>/dev/null || exit 0
[ -s "$TMP/store" ] || exit 0
tail -n "$MAX_ROWS" "$HITS" > "$TMP/hits" 2>/dev/null || : > "$TMP/hits"
[ -f "$TMP/hits" ] || : > "$TMP/hits"

# ------------------------------------------------------------------- the shared prelude
# `parse` is deliberately line-by-line with `fromjson?`: `jq -s` over a store with one
# malformed line fails the WHOLE read, and a store that stops working because something
# once wrote half a line is a store that silently forgets everything.
#
# `split("\n")` AND NOT `[splits("\n")]`, which computes the same value. `splits` is the
# REGEX form: it compiles and runs an Oniguruma match over the whole file, and on a
# 500-row store that one character cost 230 ms of the hook's 270 -- measured, by running
# the two side by side on the same input. This hook runs before every Bash, Write and
# Edit call, so that is 230 ms per tool call.
#
# `live` drops tombstoned rows, rows with no text, and -- this one matters -- rows whose
# id is not usable as a filename. The id names the cooldown stamp under
# <state>/remind/<sid>/, so an id carrying a slash would write outside that directory. An
# id we cannot honour a cooldown for is one we must not fire.
#
# A row with a missing or empty `scope` is normalised to `global` HERE rather than at each
# use, because the naive spelling (`.scope // "global"`) leaves an empty string in place
# and `$cwd | startswith("" + "/")` is true for every absolute path -- a project-scoped
# rule with a lost scope would fire in every repository on the machine.
JQ_PRELUDE='
def parse: split("\n") | map(select(length > 0)) | map(fromjson? // empty);
def live:
  . as $rows
  | ([ $rows[] | select((.t // "") == "remove") | {id: (.id // ""), ts: (.ts // 0)} ]) as $dead
  | [ $rows[]
      | select((.t // "") != "remove")
      | select(((.id // "") | tostring) | test("^[A-Za-z0-9._-]{1,96}$"))
      | select(((.text // "") | tostring | length) > 0)
      | .scope = (if (((.scope // "") | tostring | length) == 0) then "global" else (.scope | tostring) end)
      | . as $r
      | select(([ $dead[] | select(.id == $r.id and (.ts >= ($r.created // 0))) ] | length) == 0) ];
def inscope($cwd):
  map(. as $r
      | select( ($r.scope == "global")
                or ($r.scope == $cwd)
                or ((($cwd | length) > 0) and ($cwd | startswith($r.scope + "/"))) ));
'

# ------------------------------------------------------------------- the path arm
# Globs are matched by the SHELL, with `case`, because that is what a shell glob means.
# Converting `tests/*.py` into a regex to match it in jq would be a second glob
# implementation with its own bugs, and the rule a user writes is a shell one.
#
# jq emits one `id<US>candidate-path<US>glob` line per (row, glob, candidate) triple --
# the same US separator and for the same reason as the payload line above:
# the absolute path and, for a project-scoped row, the path relative to that scope.
PATHIDS=""
if [ "$mode" = "path" ] && [ -n "$fpath" ]; then
  jq -R -s -r --arg cwd "$cwd" --arg fp "$fpath" "$JQ_PRELUDE"'
    parse | live | inscope($cwd) | .[]
    | . as $r
    | ((($r.match.paths // []) | map(tostring | gsub("[\n\t\r\u001f]";" ")) | map(select(length > 0)))[]) as $g
    | ([$fp] + (if ($r.scope == "global") then [] else [($fp | ltrimstr($r.scope + "/"))] end))[]
    | "\($r.id)\u001f\(.)\u001f\($g)"
  ' "$TMP/store" > "$TMP/globs" 2>/dev/null
  if [ -s "$TMP/globs" ]; then
    while IFS="$SEP" read -r g_id g_path g_glob; do
      [ -z "$g_id" ] && continue
      [ -z "$g_glob" ] && continue
      # UNQUOTED on purpose: an unquoted variable in a `case` pattern is expanded AS a
      # pattern, which is the only portable way to match a glob held in a variable.
      # shellcheck disable=SC2254  # the glob is the point; quoting it would match literally
      case "$g_path" in
        $g_glob) PATHIDS="$PATHIDS $g_id" ;;
      esac
    done < "$TMP/globs"
  fi
fi

# ------------------------------------------------------------------- the command arm
# The normaliser lives in hooks/repeat-gate.sh and is called, not copied. `--norm-of Bash`
# reads the raw command on stdin and prints exactly the signature `compute_call` would
# have produced for it, touching no store. When that script is not beside this one --
# a checkout predating it, or a partial install -- command matching is skipped rather
# than approximated, because an approximate signature matches the wrong reminders.
NORM=""
if [ "$mode" = "command" ]; then
  RG="$(dirname "$0")/repeat-gate.sh"
  if [ -x "$RG" ]; then
    RG_CMD="$(jqr '.tool_input.command // empty')"
    if [ -n "$RG_CMD" ]; then
      NORM="$(printf '%s' "$RG_CMD" | "$RG" --norm-of Bash 2>/dev/null)"
      NORM="$(printf '%s' "$NORM" | tr -d '\n\r')"
    fi
  fi
fi

# ------------------------------------------------------------------- selection
PROMPT=""
if [ "$mode" = "prompt" ]; then
  PROMPT="$(jqr '(.prompt // "") | tostring | .[0:20000]')"
fi

# The date is emitted as ONE token (`-` when the row has no usable `created`) because the
# line is read back with `read -r id date kind text` and the text is everything after the
# third field. gmtime/strftime is used rather than `date`, which needs -r on BSD and -d on
# GNU for the same job; the cost is that the date is UTC.
jq -R -s -r --arg cwd "$cwd" --arg event "$event" --arg prompt "$PROMPT" \
   --arg norm "$NORM" --arg pathids "$PATHIDS" --rawfile hitsraw "$TMP/hits" \
   "$JQ_PRELUDE"'
  ($prompt | ascii_downcase) as $P
  | ([ ($hitsraw | parse)[] | (.id // empty) ]) as $HIDS
  | ($pathids | split(" ") | map(select(length > 0))) as $PIDS
  | [ (parse | live | inscope($cwd))[]
      | . as $r
      | ((($r.match.keywords // []) | map(tostring | ascii_downcase) | map(select(length > 0)))) as $kw
      | ((($r.match.commands // []) | map(tostring))) as $cm
      | (($event == "UserPromptSubmit") and (($kw | length) > 0)
         and (all($kw[]; . as $k | $P | contains($k)))) as $mkw
      | ((($norm | length) > 0) and (($cm | index($norm)) != null)) as $mcmd
      | ((($PIDS | index($r.id)) != null)) as $mpath
      | select($mkw or $mcmd or $mpath)
      | {id: $r.id,
         score: ((if $mcmd then 100 else 0 end) + (if $mpath then 50 else 0 end)
                 + (10 * ($kw | length))),
         hits: ([ $HIDS[] | select(. == $r.id) ] | length),
         created: (if (($r.created | type) == "number") then $r.created else 0 end),
         kind: (if ($r.scope == "global") then "global" else "project" end),
         date: (if (($r.created | type) == "number")
                then ($r.created | gmtime | strftime("%Y-%m-%d")) else "-" end),
         cand: (((($r.candidate // "") | tostring)
                 | select(test("^[A-Za-z0-9._-]{1,64}$"))) // "-"),
         text: ($r.text | tostring | gsub("[\n\t\r\u001f]"; " ") | .[0:'"$TEXT_CAP"'])}
    ]
  | sort_by([(-.score), .hits, (-.created)])[]
  | "\(.id) \(.date) \(.kind) \(.cand) \(.text)"
' "$TMP/store" > "$TMP/ranked" 2>/dev/null

[ -s "$TMP/ranked" ] || exit 0

# ------------------------------------------------------------------- cooldown
# Applied BEFORE the cap, so a reminder the cooldown is holding back does not consume one
# of REMIND_MAX slots that a reminder which has never fired could have used.
picked=0
: > "$TMP/pick" 2>/dev/null || exit 0
while IFS=" " read -r r_id r_date r_kind r_cand r_text; do
  [ -z "$r_id" ] && continue
  [ "$picked" -ge "$MAX" ] && break
  if [ -f "$SDIR/$r_id" ]; then
    # REMIND_COOLDOWN=0 is "once per session, ever", so the stamp EXISTING is the whole
    # answer and its contents are not consulted. That also makes a stamp whose contents
    # were lost behave as fired rather than as never-fired.
    [ "$COOLDOWN" -eq 0 ] && continue
    r_st="$(cat "$SDIR/$r_id" 2>/dev/null | tr -cd '0-9')"
    case "$r_st" in
      ''|*[!0-9]*) ;;
      *)
        r_d=$(( now - r_st ))
        [ "$r_d" -lt 0 ] && r_d=$(( 0 - r_d ))
        [ "$r_d" -lt "$COOLDOWN" ] && continue
        ;;
    esac
  fi
  printf '%s %s %s %s %s\n' "$r_id" "$r_date" "$r_kind" "$r_cand" "$r_text" >> "$TMP/pick"
  picked=$(( picked + 1 ))
done < "$TMP/ranked"

[ "$picked" -gt 0 ] || exit 0
[ -s "$TMP/pick" ] || exit 0

# ------------------------------------------------------------------- double delivery
# With both wirings active (settings.json AND the plugin) every event is delivered twice.
# Claim it once. Fail OPEN, like hooks/compound-improvement.sh: mkdir failing because the
# marker exists is a duplicate and must be dropped, while mkdir failing for any other
# reason (a read-only state directory, a full disk) must not silence every reminder for
# the rest of the session; the two are told apart by testing the marker afterwards. An
# event carrying no id at all is always acted on.
#
# THE CLAIM IS TAKEN HERE, not earlier, and that placement is the bug hooks/session-review.sh
# shipped first: an event whose selection came back empty would have burned its claim, so
# the second delivery -- the one that might have matched after a concurrent write -- could
# never fire.
claim_once() {
  c_dir="$DIR/$sid.seen"
  mkdir -p "$c_dir" 2>/dev/null || return 0
  [ -z "$eid" ] && return 0
  if mkdir "$c_dir/$1-$eid" 2>/dev/null; then return 0; fi
  [ -d "$c_dir/$1-$eid" ] && return 1
  return 0
}
claim_once "$mode" || exit 0

# ------------------------------------------------------------------- stamp, hit, emit
mkdir -p "$SDIR" 2>/dev/null || exit 0
CTX=""
while IFS=" " read -r p_id p_date p_kind p_cand p_text; do
  [ -z "$p_id" ] && continue
  # The stamp is written BEFORE the emit and a reminder whose stamp cannot be written is
  # dropped: firing every event because the cooldown cannot be recorded is worse than not
  # firing at all.
  printf '%s\n' "$now" > "$SDIR/$p_id" 2>/dev/null || continue
  # Hand-built JSON, and safe because every field is drawn from a charset already
  # validated: `id` passed ^[A-Za-z0-9._-]{1,96}$ in `live`, `sid` came through the
  # sanitiser above, `now` is digits-only, and `event` is one of two literals matched by
  # the case above. Nothing here can carry a quote or a backslash.
  # THE LINEAGE ID RIDES ALONG. `id` names which reminder fired; `candidate` names the
  # thing the reminder descends from -- the queue record a `skillinsight promote` turned
  # into this note, carried here through bin/skillnote's reminder row. It is what makes
  # bin/skillreport's FUNNEL a join rather than an estimate. A row whose reminder has no
  # lineage is written exactly as before and reported as UNATTRIBUTED, never guessed at.
  # `-` is the ranked line's placeholder for "none", chosen because the ranked format is
  # space-separated and an empty field would silently shift `text` into `cand`.
  if [ -n "$p_cand" ] && [ "$p_cand" != "-" ]; then
    printf '{"id":"%s","ts":%s,"session":"%s","event":"%s","candidate":"%s"}\n' \
      "$p_id" "$now" "$sid" "$event" "$p_cand" 2>/dev/null >> "$HITS" || true
  else
    printf '{"id":"%s","ts":%s,"session":"%s","event":"%s"}\n' \
      "$p_id" "$now" "$sid" "$event" 2>/dev/null >> "$HITS" || true
  fi
  if [ "$p_kind" = "global" ]; then
    if [ "$p_date" = "-" ]; then p_line="Reminder recorded for this machine: $p_text"
    else p_line="Reminder recorded on $p_date for this machine: $p_text"; fi
  else
    if [ "$p_date" = "-" ]; then p_line="Reminder recorded for this project: $p_text"
    else p_line="Reminder recorded on $p_date for this project: $p_text"; fi
  fi
  if [ -z "$CTX" ]; then CTX="$p_line"; else CTX="$CTX
$p_line"; fi
done < "$TMP/pick"

# ------------------------------------------------------------------- hits cap
# Bounded on write as well as on read. One `wc` per emit -- this is the delivery path,
# reached once per reminder per session, never once per event -- and when the log holds
# more than REMIND_MAX_ROWS lines it is rewritten to its last REMIND_MAX_ROWS the way
# bin/skillnote rewrites a CLAUDE.md: mktemp in the log's OWN directory so the `mv` is a
# rename(2), never a truncate in place. A concurrent appender can lose one row to that
# rename, and that row is one delivery's count rather than a rule; the store itself is
# still never rewritten. The spaces are stripped because BSD `wc` pads its count with
# them and the numeric guard would read a space as non-numeric -- the defect that made
# hooks/claim-gate.sh's byte cap dead code -- and stripped with a parameter expansion
# rather than `tr`, which would be one more exec on a path measured in milliseconds.
hits_n="$(wc -l < "$HITS" 2>/dev/null)"
hits_n="${hits_n// /}"
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

[ -n "$CTX" ] || exit 0

jq -n --arg ev "$event" --arg ctx "$CTX" \
  '{suppressOutput:true, hookSpecificOutput:{hookEventName:$ev, additionalContext:$ctx}}' \
  2>/dev/null || exit 0

exit 0

# Closes the brace group opened just under `set -uo pipefail`. See the note there.
}
