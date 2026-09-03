#!/usr/bin/env bash
# Refuses to let a turn end while a skill this session FORGED has never been applied to
# the problem that caused it.
#
# WHY THIS IS A HOOK AND NOT A REMINDER. Issue #19 requirement 4 says the loop ends at
# "and then it solved the thing", and the maintainer's own measurement is that a reminder
# does not get there. The edit checkpoint in hooks/compound-improvement.sh fired at edits
# 12, 24 and 36 in one real session and was read past every time; and of the 9 skills this
# package shipped WHEN THAT WAS MEASURED, 7 never arrived on their own in a live session.
# The count is dated on purpose: it is the size of the population the measurement covered,
# not an inventory of what ships today, and `ls -d skills/*/ | wc -l` is the inventory.
# Refusal is the one
# mechanism in this package that has been observed to steer -- hooks/claim-gate.sh is the
# production precedent, and this file is modelled on its Stop arm, deliberately, down to
# the block shape and the per-key claim.
#
# WIRING (not written by this file):
#   Stop -> "$DIR/apply-gate.sh"
# The script dispatches on `.hook_event_name` and takes no argv, so it is inert on any
# other event.
#
# ====================================================================================
# THE CONTRACT IS A FILE, NOT A FUNCTION CALL.
#
# `skillforge done` writes one marker per closed forge:
#
#   <state>/apply-pending/<safe-name>.json
#     {"name":"<skill name>","forge":"<forge name>","skill_dir":"<abs path or empty>",
#      "trigger":"<verbatim trigger text>","trigger_kind":"<kind>",
#      "summary":"<one-line summary>","closed":<epoch>,"session":"<session id or empty>",
#      "installed":<true|false>}
#
# `skillforge apply --name X --outcome used|declined --evidence "..."` removes it.
# safe-name is the skill name through `tr -c 'A-Za-z0-9._-' '_' | cut -c1-96`, the same
# expression every other script in this package sanitises an identifier with.
#
# This hook never writes a marker and never deletes one. It reads them, and it refuses.
# Everything it needs is in the file, which is also why its tests write the files
# directly rather than driving the CLI: the contract under test is the marker, not the
# writer.
#
# ====================================================================================
# WHY ONLY THIS SESSION'S MARKERS BLOCK, AND NEVER ANOTHER SESSION'S.
#
# The marker carries the session id that closed the forge, and this arm compares it to
# the payload's own `.session_id`. A marker from a DIFFERENT session is skipped outright
# -- not deferred, not counted, skipped -- and is surfaced by
# statusline/skillforge-status.sh instead, which is a surface the user reads without
# being interrupted by it.
#
# The reason is the misfire that would get this hook uninstalled. A forge is closed in
# session A; the user opens session B the next morning to do something unrelated in
# another repository; B's first turn is refused and told to apply a skill it has never
# heard of, for a problem it was not present for, with no evidence available to write
# into `--evidence`. B cannot honestly answer `used`, and answering `declined` to clear
# somebody else's flag is worse than the flag -- it writes a false ledger row. So B has
# no correct move, and a gate with no correct move is a gate people switch off. The
# status line asks nothing of B and can still say the flag is standing.
#
# ====================================================================================
# WHY IT BLOCKS AT MOST ONCE PER SESSION PER SKILL.
#
# A gate that can trap a session in a loop it cannot exit is worse than no gate. Three
# guards, in the order they fire:
#
#   1. `stop_hook_active`. Measured on Claude Code 2.1.245 (see hooks/claim-gate.sh,
#      PLATFORM FACTS 2): false on the first Stop of a turn, true on any Stop that exists
#      only because a Stop hook blocked. Honouring it is sufficient on its own.
#   2. A per-TURN claim on `.session_id` + `.prompt_id`, taken with an atomic `mkdir`.
#      This is also the double-delivery guard -- with settings.json and the plugin
#      manifest both active every hook is delivered TWICE (docs/CLAUDE-CODE-BEHAVIOR.md),
#      so a block must be claimed atomically or the user is interrupted twice for one
#      event. It fails CLOSED: if `mkdir` fails for any reason at all -- a lost race with
#      the duplicate delivery, read-only state, a full disk -- this hook says nothing. A
#      missed block costs one nudge; a doubled block costs the user their turn twice.
#   3. A per-SESSION-per-SKILL claim, same `mkdir`. Once a skill has been named in a
#      block, this session is never refused for that skill again, whatever the session
#      then does about it.
#
# Guard 3 is the one that makes `--outcome declined` honest. A session may legitimately
# decide the forged skill was not applicable to what it ended up doing; that is a real
# outcome and the CLI records it as one. But the session must not be forced to write a
# ledger row it does not believe in order to escape the gate, so the gate lets go after
# it has said its piece ONCE. The worst case is bounded by the number of skills this
# session forged, which is a number the session itself chose.
#
# ====================================================================================
# FAIL OPEN, ALWAYS, AND SILENTLY.
#
# No jq, no session id, no pending directory, an unreadable marker, a marker that is not
# JSON, a marker with no `closed` stamp, an unwritable state directory: every one of them
# ends the turn normally with exit 0 and nothing on stdout. The only thing this script
# ever prints is a deliberate `{"decision":"block","reason":...}`, which is the shape
# measured to reach the model as "Stop hook feedback" rather than as a tool malfunction
# (claim-gate.sh, PLATFORM FACTS 4). Text arriving through that channel is acted on as
# guidance, so the reason below is phrased as guidance; the PreToolUse channel, where the
# model correctly refuses embedded instructions, is not used here.
#
# ====================================================================================
# THE QUOTE IS BOUNDED, AND THE BOUND IS SAID OUT LOUD.
#
# The marker is written by another program. This hook's contract with it is a documented
# file shape, and nothing in that shape bounds the trigger text -- so nothing bounded what
# this hook pasted into the model's context either. Measured, one marker and one Stop
# payload, trigger length -> bytes on stdout:
#
#     100000 -> 101182      800000 ->  801182
#     400000 -> 401182     1030000 -> 1031182
#
# Dead linear, offset a constant 1182: there was no bound at all, only whatever the writer
# of the marker felt like. The same four inputs now render 2526, 2526, 2526 and 2528 bytes
# (re-measured after the byte half of the cap landed, which widened the announcement).
# hooks/claim-gate.sh has capped its own input since it shipped (CLAIM_GATE_MAX_BYTES);
# this file had no equivalent.
#
# Past APPLY_GATE_MAX_TRIGGER the quote is cut AND THE CUT IS ANNOUNCED in the message,
# with both counts. A silently truncated quote is worse than a short one: the whole reason
# the trigger is reproduced verbatim is that it is evidence, and evidence a reader cannot
# tell is partial is evidence they will over-read.
#
# THE CAP IS SPENT IN TWO UNITS AT ONCE -- CODEPOINTS AND BYTES, WHICHEVER CUTS FIRST --
# AND THE BYTE HALF IS THE HALF THAT MAKES IT A BOUND. The first version of this cap
# counted only codepoints, which is what jq's `length` returns, while everything
# downstream counts BYTES. Both knobs have a documented legal ceiling, and at those two
# ceilings together -- MAX_TRIGGER 20000, MAX_NAMED 20 -- 20 x 20000 codepoints of 3-byte
# text is 1200000 bytes of quote out of a cap that believed it had allowed 400000. The
# same input now renders 409452 bytes, with every quote in it inside the 20000-byte budget
# (widest measured: 19998, the last whole glyph that fits). That was the unbounded-quote
# defect arriving back through the cap written to prevent it, from a setting the ENV block
# calls legal -- a flag the user never sees, at the settings the file itself documents.
#
# WHAT THE BYTE HALF IS FOR NOW, AND WHAT IT IS NOT FOR. It was written because the emit
# was an exec -- `jq -n --arg r "$reason"` -- and 1200000 bytes in one argument died with
# E2BIG, so the hook printed nothing at its own documented settings. Measured then: 0 bytes
# on stdout, rc 0, empty stderr, `sess-A.p1.turn` on disk. Capping the bytes did NOT close
# that on Linux, and this is the part the cap alone could not reach: Linux caps a SINGLE
# argument at MAX_ARG_STRLEN, a hard 131072 bytes, and 409452 is 3.1x that. macOS has no
# per-argument cap, so this suite stayed green here while the gate went silent on ubuntu at
# its own documented ceilings. The emit no longer puts the message in argv at all -- it is
# streamed through a file, see EMIT, AND ONLY THEN CLAIM -- so the cap is no longer what
# keeps the exec alive. It is now exactly what its name says: a bound on how much of
# somebody else's file this hook pastes into the model's context, in the unit context is
# measured in. It still fires and the cut is still announced. Do not "simplify" it back to
# a codepoint cap on the strength of the exec having been fixed; they were two defects.
#
# For ASCII the two units are the same number, so nothing about the default behaviour
# moved: a 1200-codepoint budget still shows 1200 ASCII characters. What changed is only
# text where a codepoint is not a byte.
#
# So the whole message is bounded in bytes BY CONSTRUCTION rather than by a check:
# MAX_NAMED x (MAX_TRIGGER bytes of quote + a bounded per-skill boilerplate, the name in it
# capped at 96 codepoints and so at 384 bytes), and both factors have ceilings enforced
# below. There is no separate total-size guard, deliberately -- a guard that can never fire
# is the thing tests/ and skills/dead-guard-detection exist to keep out of this package.
#
# 1200 IS FROM THE LEDGER, NOT FROM TASTE, AND THE SAMPLE IS SMALL. Every trigger recorded
# on this machine (`jq -r '.trigger_verbatim|length' ~/.claude/skill-compounder/ledger.jsonl`)
# measures 359, 359 and 518 codepoints. n=3, one user, one repository -- so the cap is set
# at roughly 2.3x the longest of them rather than snugly above it, and it is an environment
# variable because that sample cannot carry more weight than that.
#
# The NAME is bounded too, at 96 codepoints, and that number is not a new policy: 96 is
# `safe_name`'s own `cut -c1-96` in bin/skillforge, so the marker's FILENAME already holds
# no more than that and two names agreeing to 96 are one marker on disk. The cut is marked
# with `…` there as well, because the name is printed inside a command the reader may run
# and a name silently cut would be a command that silently does the wrong thing.
#
# ====================================================================================
# ENV (defaults in parentheses):
#   SKILL_COMPOUNDER_APPLY_GATE  (1)      0 disables everything.
#   APPLY_GATE_WINDOW        (86400)      seconds after `closed` that a marker can block.
#                                         One day: a forge closed yesterday is still the
#                                         forge this work asked for, and one closed last
#                                         month is an archaeology problem, not a turn's.
#                                         The status line's APPLY_PENDING_TTL defaults to
#                                         the same number on purpose -- see that file.
#   APPLY_GATE_NOW               ()       pins the clock. This script's own clock: pinning
#                                         SKILLFORGE_NOW or CI_NOW does nothing here.
#   APPLY_GATE_MAX_NAMED         (4)      skills named in one block message. Ceilinged at
#                                         20: past that a "block" is not a nudge, it is a
#                                         wall, and it is also how the trigger cap below
#                                         would be defeated -- N unbounded quotes.
#   APPLY_GATE_MAX_TRIGGER    (1200)      budget for the verbatim trigger reproduced in the
#                                         block, per skill, spent as BOTH codepoints and
#                                         bytes -- whichever runs out first does the cut.
#                                         Ceilinged at 20000; see THE QUOTE IS BOUNDED for
#                                         why one number in two units, and for what the
#                                         codepoints-only version did at that ceiling.
#   APPLY_GATE_DEBUG_DUMP        ()       append the raw stdin payload here.
#   SKILL_COMPOUNDER_STATE                state root ($HOME/.claude/skill-compounder).

set -uo pipefail

# ------------------------------------------------------------------------------------
# THE ENTIRE BODY OF THIS SCRIPT IS ONE BRACE GROUP, AND THE `}` AT THE END OF THE FILE
# IS WHAT CLOSES IT. bash reads a script lazily by byte offset and resumes at that offset
# in whatever the file holds AT THAT MOMENT; every file in this package runs by absolute
# path out of the checkout, so a `git pull` mid-run rewrites bytes of a run already in
# flight. A brace group is one compound command, so the whole file must parse before any
# of it runs. The `exit` before the closing `}` is load-bearing too: a group protects its
# body and nothing past it, and a script that falls off the end can have bash resume past
# `}` and execute prepended text. tests/test_script_wrapping.py reproduces both halves
# against a live process.
# ------------------------------------------------------------------------------------
{

# HOME can be unset (cron, a stripped env, a container). Under `set -u` reading it aborts
# the script non-zero, which is the one thing a hook may never do.
: "${HOME:=/tmp}"

ENABLED="${SKILL_COMPOUNDER_APPLY_GATE:-1}"
WINDOW="${APPLY_GATE_WINDOW:-86400}"
MAX_NAMED="${APPLY_GATE_MAX_NAMED:-4}"
MAX_TRIGGER="${APPLY_GATE_MAX_TRIGGER:-1200}"
ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
PENDING_DIR="$ROOT/apply-pending"
STATE_DIR="$ROOT/apply-gate"

[ "$ENABLED" = "0" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

payload="$(cat)"
[ -n "${APPLY_GATE_DEBUG_DUMP:-}" ] && printf '%s\n' "$payload" >> "$APPLY_GATE_DEBUG_DUMP"

jqr() { printf '%s' "$payload" | jq -r "$1" 2>/dev/null; }

# Absent means Stop, which is the only event this file is wired to; anything else is a
# wiring the author of that wiring has to think about, so it exits rather than guesses.
event="$(jqr '.hook_event_name // empty')"
[ -z "$event" ] && event="Stop"
[ "$event" = "Stop" ] || exit 0

# Guard 1. Without it, a session that keeps ending without applying loops forever.
[ "$(jqr '.stop_hook_active // false')" = "true" ] && exit 0

# The RAW session id is what the marker records and what is compared; the sanitised one
# is what names state on disk. Both are needed and they are not interchangeable. With no
# session id nothing can be attributed to this session, and this gate blocks only on what
# it can attribute -- so it says nothing at all.
sid_raw="$(jqr '.session_id // empty')"
[ -n "$sid_raw" ] || exit 0
sid="$(printf '%s' "$sid_raw" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"

# This script's own clock. Every other script here has one, and pinning a different
# script's does nothing to this one -- that is why the list in .claude/CLAUDE.md exists.
now="${APPLY_GATE_NOW:-$(date +%s)}"
case "$now" in ''|*[!0-9]*) now="$(date +%s)" ;; esac
# A knob set to nonsense must degrade to the default, never to silence and never to an
# arithmetic error printed on a hook's stderr once per turn.
case "$WINDOW" in ''|*[!0-9]*) WINDOW=86400 ;; esac
case "$MAX_NAMED" in ''|*[!0-9]*|0) MAX_NAMED=4 ;; esac
case "$MAX_TRIGGER" in ''|*[!0-9]*|0) MAX_TRIGGER=1200 ;; esac
# SHAPE FIRST, THEN MAGNITUDE, AND THE SHAPE GUARD IS NOT OPTIONAL: `[ 99999999999999999999
# -gt 20 ]` is all digits and still aborts bash with "integer expression expected" on
# stderr, once per turn, which a hook may not do. Seven digits or more is not a setting.
# Out of range falls back to the DEFAULT rather than clamping to the ceiling, the same
# argument statusline/skillforge-status.sh's col_or makes: a value this far out is a
# mistake, and the default is the only value known to behave.
case "$MAX_NAMED"   in ???????*) MAX_NAMED=4 ;; esac
case "$MAX_TRIGGER" in ???????*) MAX_TRIGGER=1200 ;; esac
[ "$MAX_NAMED"   -gt 20 ]    && MAX_NAMED=4
[ "$MAX_TRIGGER" -gt 20000 ] && MAX_TRIGGER=1200

[ -d "$PENDING_DIR" ] || exit 0

TMP="$(mktemp -d 2>/dev/null)" || exit 0
cleanup() { [ -n "${TMP:-}" ] && rm -rf "$TMP" 2>/dev/null; }
trap cleanup EXIT

# Fields are separated by US (0x1f), not by a tab. Tab is IFS whitespace, so `read`
# collapses runs of it and an empty trigger would silently shift every field after it by
# one. A non-whitespace separator keeps empty fields empty. Control characters are
# stripped from the free-text fields inside jq, which is what makes this parse safe no
# matter what text a caller handed `skillforge done`.
SEP="$(printf '\037')"

# ------------------------------------------------------------------ candidate markers
# One jq per marker. A file that does not parse, or that lacks a usable name, session or
# `closed` stamp, produces no output and is SKIPPED -- never repaired, never deleted. It
# may be half-written, or written by a newer version of the CLI than this hook.
#
# `closed` in the future is a clock disagreeing with itself, not a marker from tomorrow:
# its age is floored at 0, which keeps it inside the window rather than silently
# discarding a real flag.
#
# EVERY FIELD LEAVES THIS jq ALREADY BOUNDED, and that is the point of doing it here
# rather than in the shell. The unbounded string must never reach a shell variable that
# then travels somewhere with a limit on it. It is pasted into the model's context; and
# until the emit was changed to stream (see EMIT, AND ONLY THEN CLAIM) it was also handed
# to `jq -n --arg r` as ONE argument, where Linux's per-argument MAX_ARG_STRLEN (131072
# bytes, hard) killed the exec outright while macOS's much larger ARG_MAX let it through.
# Bounding at the read is what keeps every later step under a ceiling by construction
# rather than by a check nobody has watched fire.
#
# THE CLAIM KEY IS COMPUTED HERE TOO, from the FULL name, for the same reason: the shell
# must not touch the untruncated string, so it cannot be the thing that sanitises it. The
# expression is the same sanitisation every script here uses -- everything outside
# [A-Za-z0-9._-] to `_`, first 96 -- but over CODEPOINTS rather than the `tr`/`cut -c`
# pipeline's BYTES. That is strictly finer, never coarser: two names differing at byte b
# < 96 differ at codepoint index <= b < 96 as well, so nothing the marker filename keeps
# apart gets folded together here. It names a directory under <state>/apply-gate/ and
# nothing else, so it does not have to agree with any other file on disk -- only with
# itself, across the two deliveries of one event.
: > "$TMP/cand.txt"
find "$PENDING_DIR" -maxdepth 1 -type f -name '*.json' 2>/dev/null | LC_ALL=C sort | \
while IFS= read -r f; do
  jq -r --arg sid "$sid_raw" --arg sep "$SEP" --argjson now "$now" --argjson win "$WINDOW" \
        --argjson tmax "$MAX_TRIGGER" '
    def clean: (. // "") | tostring | gsub("[[:cntrl:]]"; " ");
    # 96 is bin/skillforge safe_name()'"'"'s own cut, so the marker FILENAME already carries
    # no more; `…` marks the cut because this name is printed inside a command.
    def shortname: if (length > 96) then (.[0:95] + "…") else . end;
    # THE CUT FIRES ON CODEPOINTS OR ON BYTES, WHICHEVER COMES FIRST, and the byte half
    # is not a refinement -- it is the half that makes the cap a cap. jq'"'"'s `length` counts
    # CODEPOINTS; everything this text is measured against downstream counts BYTES. At the
    # two knobs'"'"' own documented ceilings -- MAX_TRIGGER 20000, MAX_NAMED 20 -- 20 x 20000
    # codepoints of 3-byte text is 1200000 bytes of quote out of a cap that believed it had
    # allowed 400000. While the emit still passed the message as one argv element, that
    # died with E2BIG and the hook printed nothing at all: measured, exactly that input,
    # 0 bytes on stdout, rc 0, empty stderr. The emit streams through a file now, so this
    # cap bounds the model'"'"'s context rather than an exec -- see THE QUOTE IS BOUNDED.
    #
    # So $tmax is spent as a codepoint budget AND as a byte budget. For ASCII the two are
    # the same number and nothing changes; for multibyte text the byte budget bites first.
    # The total message is then bounded in bytes by construction:
    # MAX_NAMED x ($tmax + the per-skill boilerplate), both factors ceilinged above.
    #
    # bytecut is a binary search over the CODEPOINT index, so it can never cut a character
    # in half -- a truncated UTF-8 sequence would not survive being handed back through jq
    # as JSON. Each probe slices a string already cut to $tmax, so the search is bounded by
    # the cap rather than by the marker'"'"'s size.
    def bytecut($bmax):
      if (utf8bytelength <= $bmax) then .
      else . as $s
           | [0, ($s | length)]
           | until((.[1] - .[0]) <= 1;
               ((((.[0] + .[1]) / 2) | floor) as $m
                | if ($s[0:$m] | utf8bytelength) <= $bmax
                  then [$m, .[1]] else [.[0], $m] end))
           | $s[0:(.[0])]
      end;
    # The cut is announced with BOTH counts in BOTH units, so a reader can see how much was
    # dropped, in the unit that did the dropping, and where the whole text still is.
    # Announcing it is the requirement; cutting it is only the mechanism.
    def shorttrigger:
      . as $full
      | ($full | length) as $tc
      | ($full | utf8bytelength) as $tb
      | ($full[0:$tmax] | bytecut($tmax)) as $cut
      | if ($cut | length) >= $tc then $full
        else ($cut + " […cut here: \($cut | length) of \($tc) characters shown "
              + "(\($cut | utf8bytelength) of \($tb) bytes); the whole trigger is in "
              + "this skill'"'"'s marker under <state>/apply-pending/]")
        end;
    select(type == "object")
    | select((.name | clean | gsub("^ +| +$"; "")) != "")
    | select(((.session // "") | tostring) == $sid)
    | select((.closed | type) == "number")
    | (if .closed > $now then 0 else ($now - (.closed | floor)) end) as $age
    | select($age <= $win)
    | [ ($age | tostring),
        (.name | clean | gsub("[^A-Za-z0-9._-]"; "_") | .[0:96]),
        (.name | clean | shortname),
        (.trigger | clean | shorttrigger) ]
    | join($sep)' "$f" 2>/dev/null
done > "$TMP/cand.txt" 2>/dev/null || :
[ -s "$TMP/cand.txt" ] || exit 0

# ------------------------------------------------------------------- claim, then speak
mkdir -p "$STATE_DIR" 2>/dev/null || exit 0

# Guard 2: at most one block per Stop EVENT. `prompt_id` is stable across a block
# (claim-gate.sh, PLATFORM FACTS 3), so this keys the turn rather than the delivery.
#
# WHAT IT BUYS THAT GUARD 3 DOES NOT, because the answer is not obvious and removing it
# broke no test until one was written for exactly this. Guard 3's per-skill `mkdir`
# already silences a duplicate delivery whenever both deliveries see the same markers:
# the loser claims nothing and says nothing. What it does not bound is the PARTITIONED
# case -- two deliveries racing over two fresh markers can each win one and each print,
# so one Stop event interrupts the user twice with half the list each time. This claim is
# what holds that at one. The deterministic stand-in for the race, and the regression
# test, is a marker appearing between two deliveries of the same event.
#
# A payload with no prompt_id degrades to one key for the whole session, so the gate can
# then block once per session rather than once per turn. That is the safe direction --
# fewer refusals, never more -- and it is the reason the fallback is a constant rather
# than something derived from the clock, which would key nothing at all.
pid="$(jqr '.prompt_id // empty')"
[ -z "$pid" ] && pid="noprompt"
pid="$(printf '%s' "$pid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
mkdir "$STATE_DIR/$sid.$pid.turn" 2>/dev/null || exit 0

# Claim markers are small, but a long-lived state root should not keep them forever.
# Same shape as hooks/claim-gate.sh's housekeeping, and the same reason.
find "$STATE_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +2 -exec rmdir {} + 2>/dev/null

# "45m", "3h07m", "2d03h". Bounded above so a marker with a year-zero stamp cannot put a
# twenty-digit number into the message.
fmt_age() {
  f_m=$(( ${1:-0} / 60 ))
  if   [ "$f_m" -lt 60 ];   then printf '%dm' "$f_m"
  elif [ "$f_m" -lt 2880 ]; then printf '%dh%02dm' $(( f_m / 60 )) $(( f_m % 60 ))
  else
    f_d=$(( f_m / 1440 ))
    if [ "$f_d" -gt 999 ]; then printf '999d+'
    else printf '%dd%02dh' "$f_d" $(( (f_m % 1440) / 60 ))
    fi
  fi
}

# GUARD 3 DECIDES HERE AND CLAIMS AT THE BOTTOM OF THE FILE, AND THE SPLIT IS THE WHOLE
# POINT. The `mkdir` used to be both at once, in this loop, which read as one clean
# mechanism and shipped the exact defect hooks/session-review.sh shipped first: the claim
# was burnt before the action it was claiming had happened.
#
# HOW IT FAILED, MEASURED. A marker carrying a 2 MB trigger, one Stop payload: stdout 0
# bytes, exit 0, and BOTH `sess-A.named.big-skill` and `sess-A.p1.turn` already on disk.
# `jq -n --arg r "$reason"` was an exec and the reason was over ARG_MAX (1048576 here), so
# it died with E2BIG into `2>/dev/null` and the `|| exit 0` swallowed it -- while the claim
# said the skill had been named. Every later turn of that session was then silent: the
# flag was gone from the gate without ever having been on anyone's screen. That is the
# thing the comment at the end of this block forbids, done by the code above it.
#
# THE EXEC ROUTE TO THAT SILENCE IS CLOSED NOW AND THE ORDERING STILL MATTERS. The reason
# is streamed through a file, so no legal setting can fail the emit on size. What can
# still fail it is everything else an exec and a write can fail on -- jq gone, a full or
# read-only /tmp, a signal mid-write -- and every one of those routes ends in the same
# place: a claim that says a skill was named in a message nobody ever saw. The ordering is
# the guard against the OUTCOME, not against the one input that used to produce it.
#
# So: the `[ -d ]` test is the DECISION (has this session already been told about this
# skill?), and the `mkdir` is the CLAIM, taken only once the block is actually on stdout.
# The `-d` was a dead guard when the `mkdir` sat beside it; it is the live guard now.
#
# THE TURN CLAIM ABOVE IS DELIBERATELY NOT MOVED WITH IT. Guard 2 exists to stop the
# duplicate delivery of ONE event from interrupting the user twice, and only an atomic
# claim taken BEFORE the work can do that -- moved after the emit, both deliveries race
# and both print, which is the failure it was written for. Its cost when an emit does fail
# is bounded to that one event: the next turn carries a new prompt_id and blocks again,
# whereas a burnt per-skill claim was for the life of the session. Different claims,
# different failure costs, different placement.
#
# The `-d` test also still decides the overflow count -- whether a skill counts toward
# "... and N more still pending". A skill already named must not be counted there, or the
# message overstates what is outstanding. Reachable: name one skill, close two more
# forges, and on the next turn the already-named one sorts ahead of a fresh one past
# MAX_NAMED. Tested.
#
# The block message names EVERY skill it claims, so the claims and the message cannot
# disagree: a skill silenced for this session but never shown to the user is a flag that
# disappeared without being read.
named=0
extra=0
body=""
claims=""
while IFS="$SEP" read -r p_age p_safe p_name p_trigger; do
  [ -n "${p_name:-}" ] || continue
  [ -n "${p_safe:-}" ] || continue
  # Already said once this session, for this skill. Neither named again nor counted as
  # outstanding: the session has heard about it and the gate has let go.
  [ -d "$STATE_DIR/$sid.named.$p_safe" ] && continue
  if [ "$named" -ge "$MAX_NAMED" ]; then
    extra=$(( extra + 1 ))
    continue
  fi
  named=$(( named + 1 ))
  claims="${claims}${p_safe}
"
  case "$p_age" in ''|*[!0-9]*) p_age=0 ;; esac
  p_when="$(fmt_age "$p_age")"
  # The trigger is reproduced VERBATIM, because it is the whole argument for applying the
  # skill: it is the dead end that was named when the forge was started, in the words
  # that were used then. Paraphrasing it here would turn the one piece of evidence in the
  # message into another summary. Truncated past APPLY_GATE_MAX_TRIGGER, never
  # paraphrased, and the truncation announces itself -- see THE QUOTE IS BOUNDED above.
  if [ -n "$p_trigger" ]; then
    p_why="      it exists because: $p_trigger
"
  else
    p_why="      no trigger text was recorded for it.
"
  fi
  body="${body}  - ${p_name}  (forged ${p_when} ago, in this session)
${p_why}      close the loop with ONE of:
        skillforge apply --name ${p_name} --outcome used --evidence \"<what happened>\"
        skillforge apply --name ${p_name} --outcome declined --evidence \"<why not>\"

"
done < "$TMP/cand.txt"

# Every candidate lost its claim race (the duplicate delivery got there first) or was
# already named. Nothing to say, and nothing was written.
[ "$named" -eq 0 ] && exit 0

more=""
if [ "$extra" -gt 0 ]; then
  more="  ... and $extra more still pending; they will be named on a later turn.

"
fi

reason="Hold on -- this session forged a skill and the loop is still open.

A forge is not finished when the skill exists. It is finished when the skill has been
applied to the problem that caused it, or explicitly declined for it. Nothing has
recorded either outcome yet:

${body}${more}\`declined\` is a complete and honest answer: if the work went somewhere the skill did
not fit, say so and say why. What is not an answer is leaving it unrecorded -- an
unapplied skill is the failure mode this whole package exists to catch, and it is
invisible unless somebody writes down what happened.

If neither is true yet because the work itself is unfinished, run the \`declined\` form
with that as the evidence and pick the skill up again next session.

This gate names each forged skill at most once per session, so it will not stop you
again for the ones above."

# EMIT, AND ONLY THEN CLAIM. The message is rendered to a file first so that "did the
# block actually reach stdout" is a question with an answer: an exec that dies (jq gone,
# a full /tmp, a signal mid-write) writes nothing while still exiting 0 through the `||`.
# Rendering, checking, and only then copying it out is what lets the claims below be
# conditional on the block having really happened.
#
# Failure here is silence, as everywhere else in this file -- and now silence with the
# flag intact, so the next turn tries again instead of the skill being gone for good.
#
# THE REASON IS STREAMED THROUGH A FILE, NOT HANDED TO jq AS AN ARGUMENT, AND THAT IS A
# PORTABILITY FIX, NOT A TIDY-UP. `jq -n --arg r "$reason"` put the whole message into
# ONE element of the argument vector. Linux caps a single argument at MAX_ARG_STRLEN,
# which is a hard 131072 bytes (32 pages, `include/uapi/linux/binfmts.h`) and is NOT
# raised by a larger ARG_MAX -- the total on Linux is a quarter of the stack rlimit,
# typically 2 MB, so the total was never the binding limit. At this file's own documented
# ceilings (MAX_TRIGGER 20000, MAX_NAMED 20) the reason renders 409452 bytes, so on Linux
# the emit died with E2BIG and the gate printed nothing AT ITS OWN DOCUMENTED SETTINGS,
# while macOS (no per-argument cap, ARG_MAX 1048576) passed. That is a green suite on one
# platform hiding a silent gate on the other, and it is what turned CI red on ubuntu.
# `--rawfile` puts a PATH in the argv and the bytes in a file, so the message size stops
# being an exec-size question on either platform. It needs jq >= 1.6, which
# `skillforge doctor` already asserts as this package's floor for exactly this reason.
#
# THE `printf` IS WRAPPED IN TWO SUBSHELLS AND BOTH LEVELS ARE LOAD-BEARING. `printf` is
# a BUILTIN, so the shell that runs it is the shell the kernel signals: under a file-size
# rlimit it takes SIGXFSZ itself and dies, and whoever REAPS it prints the diagnostic.
# One level of subshell moves the death to the subshell and the diagnostic to the MAIN
# shell, whose stderr a hook may never write to. Measured, both spellings, `ulimit -f 1`:
#   ( printf ... >f; w=$?; exit "$w" ) 2>/dev/null
#       -> "Filesize limit exceeded: 25" on the hook's stderr, rc 0
#   ( ( printf ... >f ); w=$?; exit "$w" ) 2>/dev/null
#       -> nothing on stderr, the `if` sees 153, rc 0
# The inner subshell dies; the middle one reaps it and prints into its OWN redirected
# stderr, then exits with a NORMAL status, so the main shell has nothing to report. Do
# not flatten either level.
#
# THE SUBSHELL IS NOT DECORATION AND `2>/dev/null` ON THE jq ALONE IS NOT ENOUGH. When the
# emit dies from a SIGNAL rather than an exit status -- `ulimit -f 1` and jq takes SIGXFSZ
# partway through the write, which is how this branch is exercised for real -- the message
# is printed by the SHELL THAT REAPS THE CHILD, not by the child, so the child's own
# redirect cannot catch it. Measured, before the subshell was added:
#   apply-gate.sh: line 449: 31595 Filesize limit exceeded: 25   jq -n --arg r ...
# on the hook's stderr, which is the one thing this file may never put there. Redirecting
# a subshell makes the subshell the reaper and takes its diagnostics with it -- but ONLY
# if a real subshell exists. `( jq ... ) 2>/dev/null` around a SINGLE command is optimised
# away: bash execs jq in place of the fork, so the outer shell is still the reaper and the
# message still lands. Measured, both spellings, `ulimit -f 1`:
#   ( cat big > f ) 2>/dev/null            -> "Filesize limit exceeded" on stderr
#   ( cat big > f; e=$?; exit "$e" ) 2>...  -> nothing
# The two extra statements are what make the subshell real. Do not "simplify" them away.
#
# The EXIT STATUS is what decides, not `[ -s ]` on its own: a jq killed mid-write leaves a
# non-empty, half-written file, and half a JSON decision on stdout is worse than none.
if ( ( printf '%s' "$reason" >"$TMP/reason.txt" ); w_rc=$?; exit "$w_rc" ) 2>/dev/null \
   && ( jq -n --rawfile r "$TMP/reason.txt" '{decision:"block", reason:$r}' >"$TMP/block.json"
        emit_rc=$?; exit "$emit_rc" ) 2>/dev/null \
   && [ -s "$TMP/block.json" ] && cat "$TMP/block.json" 2>/dev/null; then
  # Guard 3's claim. Atomic per skill, so it is still correct under the double delivery
  # of one event -- though guard 2 has already made that unreachable for the SAME event;
  # this is what holds across the turns of one session. A claim that cannot be written
  # (read-only state) costs one extra nudge next turn, which is the safe direction.
  printf '%s' "$claims" | while IFS= read -r c_key; do
    [ -n "$c_key" ] && mkdir "$STATE_DIR/$sid.named.$c_key" 2>/dev/null
  done
fi
exit 0

# Closes the brace group opened just under `set -uo pipefail`. See the note there.
}
