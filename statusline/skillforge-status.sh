#!/usr/bin/env bash
# Renders the live "skill forge" animation segment for the Claude Code status line.
# Reads the status-line payload JSON on stdin; prints one segment, or nothing when
# no forge is active. The animation comes from the status line's refreshInterval
# re-running this roughly once a second.
#
# SEVERAL FORGES CAN BE LIVE AT ONCE (skillforge keeps one file per forge). A status
# line is one line wide and a forge segment is already ~70 columns, so two of them do
# not fit side by side. Instead this ROTATES: it shows one forge at a time, switching
# every SKILLFORGE_ROTATE_SECS seconds, and every frame carries a [k/N] counter so the
# multiplicity is visible even mid-rotation.
#
# Rotating rather than showing only the newest is the whole point of the change: the
# defect being fixed is a status line that named one job while a different one ran, so
# a rendering that can hide a forge is not acceptable however tidy it looks. The
# counter alone would say "there are 2" without ever saying what the other one is.
#
# The segment's display width is constant WITHIN a rotation window (the tail is padded
# to a fixed column count), so the once-a-second refresh still overwrites in place.
# Width can change AT a rotation boundary, because the forge on screen genuinely
# changed and its name is a different length; that is one redraw every N seconds, not
# one per refresh, and it coincides with a real change of content.
#
# TWO THINGS THE BAR MUST NOT SAY.
#
# It must not say a forge is PROGRESSING when nothing has stepped it for a long time.
# The record carries `updated`; when the gap from now to that stamp passes
# SKILLFORGE_IDLE_SECS the tail is prefixed with how old the phase actually is, the tail
# turns yellow, and the bar's leading-edge pulse stops. Below the threshold the segment
# is byte-for-byte what it always was. Nothing is deleted or closed as a result: an
# `active` forge has no TTL by design (docs/DESIGN.md), and this is a visibility signal,
# not a reaper.
#
# It must not say a forge is FINISHED when it is still running. An active forge never
# fills its last bar cell and never shows 100%: a full bar is reserved for `done`. Past
# its budget the reserved cell becomes `»`, the step count keeps rising (`14/12`), and
# the percentage — meaningless once the budget is gone — reads `over`, which is exactly
# as wide as ` 99%` so nothing shifts.
#
# WHEN NOTHING IS FORGING, THE LINE IS NOT NECESSARILY EMPTY. `skillforge done` leaves a
# marker per closed forge under <state>/apply-pending/, and `skillforge apply` clears it.
# While one stands, and no forge is on screen, this prints `⚑ <name> forged · not yet
# used · <age>` instead. A live forge always wins: the flag is only rendered where the
# forge renderer would have printed nothing at all. Details, and why this segment reads
# those markers but never deletes one, are at pending_segment().
#
# SKILLFORGE_NOW pins the clock so the animation can be exercised deterministically.
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

# HOME can be unset (cron, a stripped env, a container, a status line spawned from a
# sanitised environment). Under `set -u` reading it then aborts the script non-zero
# before it has printed anything, and the segment silently goes blank.
: "${HOME:=/tmp}"
STATE_ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
DIR="$STATE_ROOT/forge"
# Markers written by `skillforge done` and cleared by `skillforge apply`; read
# here, never written and never removed. See pending_segment() for why.
PENDING_DIR="$STATE_ROOT/apply-pending"
command -v jq >/dev/null 2>&1 || exit 0

cat >/dev/null 2>&1   # payload is not needed: state is keyed on forge name, not session

now="${SKILLFORGE_NOW:-$(date +%s)}"
# Everything below does arithmetic on it. A non-numeric override would otherwise
# put "[: integer expected" on stderr once a second.
case "$now" in ''|*[!0-9]*) now="$(date +%s)" ;; esac

# Fields are separated by US (0x1f), not by a tab. Tab is IFS whitespace, so `read`
# collapses runs of it and an empty phase or summary would silently shift every field
# after it by one. A non-whitespace separator keeps empty fields empty.
SEP="$(printf '\037')"

# EVERY tunable is guarded before it is used, because two of them are passed straight to
# `--argjson`. `SKILLFORGE_DONE_TTL=abc` made jq fail on every slot, so every record was
# skipped and the whole segment went blank with live forges on disk, exit 0, nothing on
# stderr. A knob set wrong must degrade to the default, never to silence.
#
# MAGNITUDE MATTERS AS MUCH AS SHAPE. `SKILLFORGE_BAR_WIDTH=999999999999999999999999`
# is all digits, so a digits-only guard passed it straight through; bash then printed
# "[: integer expected" four times per render -- once a second, forever -- and drew an
# empty bar, while zsh printed it once and drew something else again. Every knob here
# is at most six digits, so a longer one is not a setting, it is a mistake.
num_or() { # <value> <default>
  case "${1:-}" in
    ''|*[!0-9]*|???????*) printf '%s' "$2" ;;
    *) printf '%s' "$1" ;;
  esac
}

# SIX DIGITS CONSTRAINS SHAPE, NOT MAGNITUDE, AND SHAPE IS NOT WHAT HURTS HERE. The
# width knobs are COLUMN COUNTS, so the only bound that means anything is what a
# terminal can actually show. `SKILLFORGE_BAR_WIDTH=999999` is six digits, passes the
# guard above, and then runs a million `bar="${bar}·"` appends: still going after 20
# seconds, once a second, so stuck renderers pile up without bound. `=9999` "succeeds"
# in ~2s and emits a 10,070-column line. `SKILLFORGE_TAIL_WIDTH=999999` emits a single
# 1,000,044-column line in a quarter of a second, exit 0, nothing on stderr.
#
# Both break the rule this file already holds itself to everywhere else -- never wrap
# the line -- and the bar one also breaks the once-a-second refresh outright.
#
# SEGMENT_MAX is a generous ceiling on a real terminal: 400 columns is wider than any
# window anyone renders a status line into, and every knob is a fraction of one line.
# An out-of-range value falls back to the default rather than clamping to the ceiling,
# for the same reason the guard above does: a value this far out is not a setting, it
# is a mistake, and the default is the only value known to render.
SEGMENT_MAX=400
BAR_MAX=200
col_or() { # <value> <default> <min> <max>
  c_v="$(num_or "${1:-}" "$2")"
  if [ "$c_v" -lt "$3" ] || [ "$c_v" -gt "$4" ]; then printf '%s' "$2"
  else printf '%s' "$c_v"; fi
}
DONE_TTL="$(num_or "${SKILLFORGE_DONE_TTL:-}" 30)"
FAIL_TTL="$(num_or "${SKILLFORGE_FAIL_TTL:-}" 60)"
# Not a reaper. This one only decides how long the ⚑ segment is SHOWN; the marker
# behind it belongs to hooks/apply-gate.sh and to `skillforge apply`. 86400 is the
# gate's APPLY_GATE_WINDOW default, deliberately -- see pending_segment().
PENDING_TTL="$(num_or "${APPLY_PENDING_TTL:-}" 86400)"
TAIL_WIDTH="$(col_or "${SKILLFORGE_TAIL_WIDTH:-}" 38 2 "$SEGMENT_MAX")"
NAME_WIDTH="$(col_or "${SKILLFORGE_NAME_WIDTH:-}" 32 2 "$SEGMENT_MAX")"
WIDTH="$(col_or "${SKILLFORGE_BAR_WIDTH:-}" 12 1 "$BAR_MAX")"

# THE BOUND THAT MATTERS IS THE SEGMENT, NOT THE KNOB. Each width above is legal on its
# own and they still sum past the line: SKILLFORGE_TAIL_WIDTH=400 alone renders 445
# columns, and 200/400/400 renders 629. So they are checked TOGETHER, against what one
# terminal line can hold. SEGMENT_CHROME is measured, not guessed: with the name, bar
# and tail subtracted, the fixed furniture (spinner, the word `forge`, the bar's
# brackets, `step/steps`, the percentage, the separators) is 23 columns, and the two
# things that widen it are the `[k/N]` counter and a four-digit step field, which is
# where the rest of the margin goes.
#
# If they do not fit, ALL THREE return to their defaults. Shrinking one of them to make
# room would render a geometry nobody asked for and give no clue why.
SEGMENT_CHROME=40
if [ $(( NAME_WIDTH + WIDTH + TAIL_WIDTH + SEGMENT_CHROME )) -gt "$SEGMENT_MAX" ]; then
  NAME_WIDTH=32; WIDTH=12; TAIL_WIDTH=38
fi

M=$'\033[35m'; C=$'\033[1;36m'; G=$'\033[32m'; D=$'\033[2m'; R=$'\033[31m'; X=$'\033[0m'
Y=$'\033[33m'

# The hard byte bound `fit` trims every input to before it reaches an exec. Not a knob:
# it is not a display choice, it is the distance between this script and E2BIG, and there
# is no value of it a user could want to change. Derived in the comment above fit().
FIT_MAX_BYTES=8192

# Pad or truncate to an exact number of TERMINAL COLUMNS.
#
# Done in jq because bash 3.2 substring indexing and printf's %-*.*s are both
# byte-based, so a multibyte tail would be cut mid-character.
#
# COLUMNS, NOT CODEPOINTS. jq's `length` counts codepoints, and a CJK or emoji
# codepoint occupies TWO terminal cells. A phase of "スキルを鍛える段階" padded to 38
# codepoints therefore drew 47 columns while the summary beside it drew 38, and the
# segment oscillated by nine columns every five seconds -- inside a single rotation
# window, which is exactly the blink the padding exists to prevent. Measured: 86 columns
# against 77 on alternating frames. The width table below is the standard wide/fullwidth
# set; anything outside it counts as one, which is right for Latin, the block-drawing
# glyphs, the braille spinner and `…`.
#
# <string> <columns> <pad|nopad>. `nopad` truncates but does not extend: a terminal
# state prints once and holds still, so it needs a ceiling, not a fixed width.
#
# ================================================================================
# THE WIDTH CAP USED TO INVERT ON EXACTLY THE INPUT IT EXISTS FOR, AND THE REPAIR IS
# BELOW THE jq, NOT AROUND IT.
#
# `jq -rn --arg s "$1"` is an EXEC, and the string travels in the argument vector. Past
# ARG_MAX (1048576 here, `getconf ARG_MAX`) the exec fails, `2>/dev/null` hides it, and
# the `|| printf '%s' "$1"` fallback then printed the RAW, UNCAPPED string -- so the
# larger the input, the less the cap did, and past a megabyte it did nothing at all.
# Measured through a marker written to <state>/apply-pending/: a 2000000-byte `name`
# rendered 2000064 bytes into a 32-COLUMN budget, and the same shape through a forge slot
# rendered 2000132. Control, same run: a 500000-byte name rendered 98 bytes, capped
# correctly. That is a guard whose only failure mode is the case it was written for.
#
# THE FIX IS IN `fit` AND NOT AT THE CALL SITE, deliberately. Every caller feeds it a
# string read out of a file some other program wrote -- the forge slot's `name`, `phase`
# and `summary`, and the pending marker's `name` -- so the exposure is `fit`'s, not any
# one caller's. Repairing it at pending_segment() would have left the forge-name path
# (measured above at 2000132 bytes) broken in the identical way.
#
# Two halves, and both are needed:
#
#   1. TRIM BEFORE THE EXEC, so the exec cannot fail. `printf '%.*s'` is bytes in bash
#      under both C and UTF-8 locales (measured; `${s:0:n}` is NOT -- it is codepoints
#      under a UTF-8 locale), so this is a hard byte bound however the user's locale is
#      set. 8192 bytes is ~5x the largest string that could survive the widest budget any
#      caller may pass -- SEGMENT_MAX is 400 columns, and 400 columns of 4-byte
#      codepoints is 1600 bytes -- so nothing that could legitimately have been shown is
#      lost, and the jq below still marks the cut with `…` because 8192 is far past every
#      budget. A byte trim can sever a UTF-8 sequence; jq accepts the broken tail and
#      substitutes U+FFFD (measured on jq 1.6), and the column truncation discards it.
#   2. BOUND THE FALLBACK, so it cannot be worse than the path it stands in for. It now
#      cuts to $2-1 BYTES and appends `…`, which is at most $2 columns because a UTF-8
#      string never has fewer bytes than terminal columns. It is compared rather than
#      measured so the `…` appears only when something was actually dropped.
fit() {
  f_s="$(printf '%.*s' "$FIT_MAX_BYTES" "$1")"
  jq -rn --arg s "$f_s" --argjson w "$2" --arg mode "${3:-pad}" '
    # Zero first, then two, then one. Combining marks, variation selectors and the
    # zero-width joiner advance the cursor by nothing; counting them as one made an
    # NFD-decomposed "café näive résumé" measure 73 columns against a padded 77.
    def cw: if   (. >= 768   and . <= 879)    or (. >= 6832  and . <= 6911)
              or (. >= 7616  and . <= 7679)   or (. >= 8400  and . <= 8447)
              or (. >= 65024 and . <= 65039)  or (. >= 65056 and . <= 65071)
              or (. >= 8203  and . <= 8207)   or (. >= 8288  and . <= 8303)
            then 0
            # The wide/fullwidth blocks, plus the emoji that render double-width
            # despite living in the narrow Miscellaneous Symbols ranges. Without the
            # second group a summary of "✅✅✅ all checks passed" drew 80 columns while
            # the ASCII phase beside it drew 77, and the segment blinked every 5s.
            elif (. >= 4352  and . <= 4447)   or (. >= 11904 and . <= 42191)
              or (. >= 44032 and . <= 55203)  or (. >= 63744 and . <= 64255)
              or (. >= 65040 and . <= 65049)  or (. >= 65072 and . <= 65135)
              or (. >= 65280 and . <= 65376)  or (. >= 65504 and . <= 65510)
              or (. >= 127744 and . <= 129791) or (. >= 129792 and . <= 130041)
              or (. >= 131072 and . <= 262141)
              or (. >= 8986  and . <= 8987)   or (. >= 9193  and . <= 9196)
              or . == 9200 or . == 9203
              or (. >= 9725  and . <= 9726)   or (. >= 9748  and . <= 9749)
              or (. >= 9800  and . <= 9811)   or . == 9855 or . == 9875
              or . == 9889 or (. >= 9898 and . <= 9899)
              or (. >= 9917  and . <= 9918)   or (. >= 9924 and . <= 9925)
              or . == 9934 or . == 9940 or . == 9962
              or (. >= 9970  and . <= 9971)   or . == 9973 or . == 9978
              or . == 9981 or . == 9989 or (. >= 9994 and . <= 9995)
              or . == 10024 or . == 10060 or . == 10062
              or (. >= 10067 and . <= 10069) or . == 10071
              or (. >= 10133 and . <= 10135) or . == 10160 or . == 10175
              or (. >= 11035 and . <= 11036) or . == 11088 or . == 11093
            then 2 else 1 end;
    ($s | gsub("[\n\r\t]"; " ")) as $t
    | ($t | explode) as $cps
    | ([foreach $cps[] as $c (0; . + ($c | cw))]) as $cum
    | ($cum | last // 0) as $total
    | if $total <= $w then
        (if $mode == "pad" then $t + ((" " * ($w - $total)) // "") else $t end)
      else
        # $cum rises monotonically, so the codepoints under the budget are a prefix.
        ([range(0; ($cps | length)) | select($cum[.] <= ($w - 1))] | length) as $k
        | (($cps[0:$k] | implode) + "…") as $cut
        | (if $k == 0 then 0 else $cum[$k - 1] end) as $used
        | (if $mode == "pad" then $cut + ((" " * ($w - 1 - $used)) // "") else $cut end)
      end' 2>/dev/null || {
    # jq refused the string it was handed (a program error; the exec itself can no longer
    # fail, see 1 above). Bytes, not columns, and no padding: this path exists because the
    # thing that measures columns is unavailable, so it may only promise a CEILING.
    f_cut="$(printf '%.*s' "$(( $2 - 1 ))" "$f_s")"
    if [ "$f_cut" = "$f_s" ]; then printf '%s' "$f_s"; else printf '%s…' "$f_cut"; fi
  }
}
pad_to() { fit "$1" "$2" pad; }

# "45m", "3h07m", "2d03h". Bounded above so a foreign record with a year-zero stamp
# cannot hand the tail a twenty-digit number.
fmt_idle() {
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

# ------------------------------------------------------------------ pending applies
#
# A forge that closed is not a forge that finished. `skillforge done` leaves a marker at
# <state>/apply-pending/<safe-name>.json for every skill it forged, and
# `skillforge apply` is what removes it. Until then the skill exists and has never been
# used on the problem that caused it, which is the state issue #19 requirement 4 exists
# to make visible. hooks/apply-gate.sh refuses to end a turn on one of these -- but ONLY
# for the session that forged it, because refusing a session that was not present for
# the forge leaves it no honest move. The flag has to live somewhere the OTHER sessions
# can see it without being interrupted, and that is here.
#
# THIS SEGMENT NEVER DELETES A MARKER, and that is the difference between
# APPLY_PENDING_TTL and the DONE_TTL / FAIL_TTL beside it. Those two reap: a terminal
# forge record has no consumer left once it has been on screen for half a minute, so the
# renderer that shows it is also the right thing to remove it. A pending-apply marker has
# two other consumers -- the Stop gate and `skillforge apply` -- so a renderer that
# deleted one would silently disarm a refusal, which is a liberty no display may take.
# APPLY_PENDING_TTL therefore governs SHOWING only; the marker outlives it untouched.
#
# THE DEFAULT IS THE GATE'S WINDOW, 86400, and the two are meant to move together. A flag
# on the line that the gate will no longer act on is decoration, and a refusal about
# something the line never showed is an ambush. One day is also the honest span: a forge
# closed yesterday is still the forge this work asked for; one closed last month is
# archaeology, and the ledger is where archaeology belongs.
#
# `num_or` rejects anything over six digits, so the largest settable TTL is 999999s
# (~11.6 days). That is a shape guard, not a policy: a longer value is a typo, and the
# ledger already holds the long-run record.
#
# A single frame is rendered even when several markers are pending, with `[N]` for the
# count, and the one shown is the MOST RECENTLY closed. There is no rotation here on
# purpose: a live forge rotates because each frame carries a bar that is genuinely
# changing, whereas these frames would differ only in a name and would blink for no new
# information. The most recent is shown rather than the oldest because it is the one the
# session in front of you most likely just made.
pending_segment() {
  [ -d "$PENDING_DIR" ] || return 1
  ps_n=0
  ps_name=""
  ps_closed=-1
  ps_list="$(find "$PENDING_DIR" -maxdepth 1 -type f -name '*.json' 2>/dev/null \
             | LC_ALL=C sort | while IFS= read -r pf; do
    # Same skip-never-repair rule the forge reader uses: a marker that does not parse, or
    # that carries no usable name or no numeric `closed`, produces nothing and is left
    # exactly where it is. A stamp in the future is a clock disagreeing with itself, so
    # its age is floored at zero rather than being treated as expired.
    jq -r --arg sep "$SEP" --argjson now "$now" --argjson ttl "$PENDING_TTL" '
      def clean: (. // "") | tostring | gsub("[[:cntrl:]]"; " ");
      select(type == "object")
      | select((.name | clean | gsub("^ +| +$"; "")) != "")
      | select((.closed | type) == "number")
      | (if .closed > $now then 0 else ($now - (.closed | floor)) end) as $age
      | select($age <= $ttl)
      | [ ((.closed | floor) | tostring), ($age | tostring), (.name | clean) ]
      | join($sep)' "$pf" 2>/dev/null
  done)"
  [ -n "$ps_list" ] || return 1
  while IFS="$SEP" read -r ps_c ps_a ps_nm; do
    [ -n "${ps_nm:-}" ] || continue
    ps_n=$(( ps_n + 1 ))
    case "$ps_c" in ''|*[!0-9]*) ps_c=0 ;; esac
    case "$ps_a" in ''|*[!0-9]*) ps_a=0 ;; esac
    if [ "$ps_c" -ge "$ps_closed" ]; then
      ps_closed=$ps_c; ps_name="$ps_nm"; ps_age=$ps_a
    fi
  done <<PENDLIST
$ps_list
PENDLIST
  [ "$ps_n" -gt 0 ] || return 1
  [ -n "$ps_name" ] || return 1
  # Capped, not padded, by the same argument the terminal forge states make: this segment
  # is not animated, so it prints once and then holds still until something changes. It
  # needs a ceiling, not a fixed width.
  ps_name="$(fit "$ps_name" "$NAME_WIDTH" nopad)"
  ps_count=""
  [ "$ps_n" -gt 1 ] && ps_count="${D}[${ps_n}]${X} "
  # ⚑ is a single-column glyph in the width table `fit` uses, and the whole segment is
  # NAME_WIDTH + 33 columns at most (2 for the flag and its space, 24 for the fixed
  # words and separators, up to 6 for the age, plus the optional counter), which is
  # comfortably narrower than the forge segment it stands in for.
  printf '%s' "${ps_count}${Y}⚑${X} ${C}${ps_name}${X} ${D}forged · not yet used · $(fmt_idle "${ps_age:-0}")${X}"
  return 0
}

# One jq per slot file. Everything the renderer needs -- including whether the record
# has expired -- comes out of that one call. Control characters are stripped from the
# free-text fields inside jq, which is what makes the line-and-field parse below safe
# no matter what a caller passed to `skillforge step`.
#
# A file that does not parse, or that lacks name/status, is SKIPPED and left alone. It
# may be a half-written state file, or one from a newer version. Temp files are named
# "<file>.tmp.<pid>" and do not end in .json, so a render cannot catch a write in
# progress in the first place.
#
# `find` rather than a glob: zsh treats a glob that matches nothing as a fatal error,
# and the status line runs under whatever shell the user has.
# Terminal states self-expire so the status line returns to normal unattended, and the
# expiry decision is made by the SAME jq call that reads the file, so the `rm` follows
# its own read immediately.
#
# Deciding for all N files first and deleting afterwards was a real bug, not a
# theoretical one: `skillforge start` reusing a finished slot in place landed inside
# that window and the reaper deleted the brand-new active forge. Measured at 40 out of
# 40 trials with a dozen expired slots present, and the status line renders once a
# second, so "narrow" was never a defence.
#
# A record with no `finished` falls back to `updated`, then `started`. With none of the
# three it is NEVER reaped: `now - 0` is always past any TTL, so the old code deleted a
# hand-written or foreign `done` record on its first render. Nothing here may destroy
# state it does not fully understand.
#
# `steps` and `step` are normalised inside jq. `--argjson t 99999999999999999999`
# stores the float 1e+20, and a numeric guard in the shell folded that back to 1, so a
# forge at step 5 of 1e+20 rendered as a full bar at 100%.
reap_and_read() {
  find "$DIR" -maxdepth 1 -type f -name '*.json' 2>/dev/null | LC_ALL=C sort | \
  while IFS= read -r f; do
    line="$(jq -r --arg f "$f" --arg sep "$SEP" --argjson now "$now" \
                 --argjson dttl "$DONE_TTL" --argjson fttl "$FAIL_TTL" '
      def clean: (. // "") | tostring | gsub("[[:cntrl:]]"; " ");
      # An out-of-range budget is CLAMPED, not folded to 1. Folding 1e+20 to 1 made a
      # forge at step 5 render as a full bar at 100%, which is a confident lie; clamping
      # to the ceiling renders it as barely started, which is at least honest about not
      # knowing. `start` refuses such values now, so only a foreign file can be here.
      def steps_of: if type == "number"
                    then (if . < 1 then 1 elif . > 999999999 then 999999999 else floor end)
                    else 1 end;
      def step_of:  if type == "number"
                    then (if . < 0 then 0 elif . > 999999999 then 999999999 else floor end)
                    else 0 end;
      # A blank name used to reach the shell, where `[ -n "$name" ] || exit 0` printed
      # NOTHING -- so one nameless record blanked the segment outright, and in a
      # rotation it stole one frame in N every six seconds. Skipped here instead, so it
      # is not counted either. Skipped, never deleted: it is state we do not understand.
      select((has("name")) and (has("status"))
             and ((.name | clean | gsub("^ +| +$"; "")) != ""))
      | (.finished // .updated // .started) as $fin
      | (if $fin == null or ($fin | type) != "number" then false
         elif .status == "done"   then ($now - $fin) > $dttl
         elif .status == "failed" then ($now - $fin) > $fttl
         else false end) as $expired
      # `updated` is emitted separately from $fin: $fin falls back through finished
      # and started, and an idle report must be about the last STEP and nothing else.
      # Out of range means "no usable stamp" (0), which suppresses the idle report --
      # never claim a forge is stale on the strength of a number that makes no sense.
      | ((.updated) | if type == "number" and . > 0 and . < 99999999999
                      then floor else 0 end) as $upd
      # $fin is NORMALISED to a number before it is joined. `//` only replaces null and
      # false, so an `updated` of [] or {} reached `join` as a container, jq errored, and
      # the whole record -- an ACTIVE forge included -- vanished from the status line
      # with nothing on stderr. Found by the malformed-stamp test below.
      | (if ($fin | type) == "number" then $fin else 0 end) as $fin
      | [ (if $expired then "X" else "-" end),
          (.started // 0), $f, (.status // "active"), $fin,
          (.step // 0 | step_of), (.steps // 1 | steps_of), $upd,
          (.name | clean), (.phase | clean), (.summary | clean) ]
      | join($sep)' "$f" 2>/dev/null)"
    [ -n "$line" ] || continue
    case "$line" in
      X"$SEP"*) rm -f "$f" 2>/dev/null; continue ;;
    esac
    printf '%s\n' "${line#-$SEP}"
  done | sort -t"$SEP" -k1,1n -k2,2
}

# Each slot is reaped on its own clock: one forge finishing must never clear another
# one, and a lingering ✓ must never hold up the forge still running beside it.
live=""
n=0
while IFS="$SEP" read -r s_started s_path s_state s_finished s_step s_steps s_updated s_name s_phase s_summary; do
  [ -n "${s_path:-}" ] || continue
  live="$live$s_started$SEP$s_path$SEP$s_state$SEP$s_finished$SEP$s_step$SEP$s_steps$SEP$s_updated$SEP$s_name$SEP$s_phase$SEP$s_summary
"
  n=$(( n + 1 ))
done <<SLOTS
$(reap_and_read)
SLOTS

# A LIVE FORGE ALWAYS WINS THE LINE. The pending flag is only reached when the forge
# renderer would otherwise print nothing at all -- no active forge, and no terminal
# record still inside its DONE_TTL / FAIL_TTL. That covers the rotation case for free:
# with N forges on disk this branch is never taken, so a ⚑ can never displace a bar, and
# the line never carries two segments competing for the same width budget.
#
# The handoff it produces is the intended one. A forge closes, the ✓ holds the line for
# DONE_TTL seconds saying it was forged, the ✓ is reaped, and the ⚑ takes its place
# saying it has still not been used. Requirement 4's third and fourth notifications, in
# that order, on the one surface a user actually watches.
if [ "$n" -eq 0 ]; then
  pending_segment
  exit 0
fi

# Which one is on screen right now. With a single forge this is always the only one, so
# nothing about the common case changes.
# A rotation period longer than a working day pins `idx` at 0 and hides every forge but
# the first -- silently, and while the [k/N] stamp truthfully says there are three. That
# is the exact defect rotation exists to prevent, one typo away. An hour is the ceiling.
# THE CEILING IS HOW LONG A FORGE MAY BE OFF SCREEN, NOT HOW LARGE A NUMBER MAY BE. An
# hour was neither: `-gt 3600` let 3600 itself through, and 3600 hides every forge but
# one for a full hour while `[2/3]` truthfully reports three -- the precise defect
# rotation exists to prevent, reached by the documented ceiling value. A minute is the
# bound now. A forge is off screen for at most (n-1) * ROTATE seconds, so at the
# ceiling even three live forges each reappear within two minutes, which is a window a
# person watching the line will actually see through. Anything longer is a typo.
ROTATE="$(col_or "${SKILLFORGE_ROTATE_SECS:-}" 6 1 60)"
idx=$(( (now / ROTATE) % n ))
# Rotation period (6s) is deliberately NOT the tail-alternation period (5s). Equal
# periods would lock each forge to one tail forever: with three live forges the third
# would show its summary and never its phase.
pick="$(printf '%s\n' "$live" | sed -n "$(( idx + 1 ))p")"

# Two zsh parameter traps, both of which fail silently and both of which this line
# would otherwise walk straight into. The status line is invoked by whatever shell the
# user has, so neither is hypothetical.
#
#   `status` is READ-ONLY in zsh: it aliases $?. Assigning to it aborts the read, and
#   the whole forge segment renders empty with no error anywhere. Hence `fstate`.
#
#   `path` is zsh's array view of $PATH. Assigning a filename to it REPLACES the
#   command search path with that one directory, so every later `jq` in this script is
#   "command not found" -- the bar still renders, but unpadded, and the width wobbles
#   once a second for zsh users only. Hence `slotfile`. `fpath`, `cdpath`, `manpath`
#   and `module_path` are tied the same way; do not name a variable any of them.
IFS="$SEP" read -r started slotfile fstate finished step steps updated name phase summary <<PICK
$pick
PICK
# Defensive: the reader already skips nameless records, so reaching here means a slot
# shape nothing understands. Printing nothing is right for the forge, but "nothing" is
# also what a pending flag would have filled, so it gets the line rather than the
# segment going blank for a reason no surface explains.
if [ -z "${name:-}" ]; then
  pending_segment
  exit 0
fi

case "$steps"   in ''|*[!0-9]*) steps=1 ;; esac
case "$step"    in ''|*[!0-9]*) step=0 ;; esac
case "$updated" in ''|*[!0-9]*) updated=0 ;; esac

# The name is not padded -- a short name must not grow trailing space -- but it IS
# capped. Nothing bounded it before: `skillforge start "$(printf 'x%.0sx' {1..200})"`
# produced a 275-column segment that wrapped the line and defeated in-place overwrite
# entirely. 32 columns clears every skill name in the seed pool (the longest,
# `parallel-agents-one-codebase`, is 28).
name="$(fit "$name" "$NAME_WIDTH" nopad)"

# Anything that is not `done` or `failed` is a RUNNING forge, whatever it calls itself.
# Testing `= "active"` let a record with `status: "paused"` (or `"Active"`, or 123) fall
# through every safeguard at once: it drew a full bar at 100% under a spinner, was never
# reported idle, and showed an overrun with no marker. A state we do not recognise is
# the LAST thing that should be rendered as finished.
running=1
case "$fstate" in done|failed) running=0 ;; esac

# ------------------------------------------------------------------------ idleness
#
# How long since the last `skillforge step`. Only ACTIVE forges are asked: a done or
# failed record has finished and is reaped on its own short TTL.
#
# THE THRESHOLD IS MEASURED, NOT CHOSEN BY TASTE. 33 real intervals between consecutive
# skillforge calls, recovered from this machine's Claude Code transcripts across four
# forges of this repo, run: median 460s, p90 1211s, largest genuinely-working gap 1240s
# (20.7 min). The next two observations in the whole sample are 4561s and 11216s -- and
# 11216s is the 3h07m the reported defect was sitting at. So the data has an empty band
# from 21 to 76 minutes, and every threshold inside it separates the sample identically.
# 2700s (45 min) sits in that band at roughly 2.2x the longest observed working interval
# and 3.7x p90. Caveat, stated plainly: n=33, one user, one repository, one week. It is
# a defensible floor, not a law, which is why it is an environment variable.
IDLE_SECS="$(num_or "${SKILLFORGE_IDLE_SECS:-}" 2700)"

idle=0
is_idle=0
if [ "$running" -eq 1 ] && [ "$updated" -gt 0 ]; then
  idle=$(( now - updated ))
  # A stamp in the future is a clock that disagrees with itself, not a stale forge.
  [ "$idle" -lt 0 ] && idle=0
  if [ "$idle" -ge "$IDLE_SECS" ]; then is_idle=1; fi
fi

# [k/N] whenever more than one forge is live, and nothing at all when only one is, so
# a single forge renders exactly as it always did.
count=""
[ "$n" -gt 1 ] && count="${D}[$(( idx + 1 ))/${n}]${X} "

[ "$steps" -lt 1 ] && steps=1

# A forge past its budget is a real state and it is not the same state as "finished".
# The stored step is NO LONGER CLAMPED by `skillforge step`, so it can exceed the
# budget; only the geometry of the bar is clamped.
over=0
[ "$step" -gt "$steps" ] && over=1
bstep=$step
[ "$bstep" -gt "$steps" ] && bstep=$steps
filled=$(( bstep * WIDTH / steps ))
[ "$filled" -gt "$WIDTH" ] && filled=$WIDTH
pct=$(( bstep * 100 / steps ))

# THE LAST CELL IS RESERVED FOR "FINISHED". A full bar and 100% are the strongest
# completion signal the segment has, and they were being shown for a forge that was
# still running: at step 12 of 12 the only thing separating working from finished was
# the spinner glyph against the ✓. So while `active` the bar stops one cell short and
# the percentage stops at 99. Nothing below step == steps moves: integer division makes
# step * WIDTH / steps reach WIDTH only when step >= steps, so a mid-budget forge is
# byte-for-byte unchanged.
if [ "$running" -eq 1 ] && [ "$filled" -ge "$WIDTH" ]; then filled=$(( WIDTH - 1 )); fi
if [ "$running" -eq 1 ] && [ "$pct" -gt 99 ]; then pct=99; fi

bar=""
i=0
while [ $i -lt "$WIDTH" ]; do
  if [ $i -lt $filled ]; then
    # Pulse the leading edge so the bar reads as live even between steps -- and stop
    # pulsing once the forge is quiet, so the shimmer never outlives the stepping.
    # NOTE: braces are required — bash folds the multibyte glyph into the var name.
    # No pulse once the budget is spent: the leading edge then sits directly beside
    # the reserved `▒`, and `▓▒` adjacent reads as an antialiasing artifact rather
    # than as two states. Nothing is lost -- the spinner still carries liveness.
    if [ $i -eq $(( filled - 1 )) ] && [ "$running" -eq 1 ] && [ "$is_idle" -eq 0 ] \
       && [ "$step" -lt "$steps" ] && [ $(( now % 2 )) -eq 0 ]; then
      bar="${bar}▓"
    else
      bar="${bar}█"
    fi
  elif [ "$running" -eq 1 ] && [ $i -eq $(( WIDTH - 1 )) ] && [ "$step" -ge "$steps" ]; then
    # The reserved cell says WHY it is reserved. `·` is work still budgeted; `▒` is
    # "as full as running can make it" -- every step spent, not yet closed out; `»` is
    # past the budget. Without `▒`, step 11 of 12 and step 12 of 12 drew the identical
    # bar and only the counter told them apart.
    if [ "$over" -eq 1 ]; then bar="${bar}»"; else bar="${bar}▒"; fi
  else
    bar="${bar}·"
  fi
  i=$(( i + 1 ))
done

# A close message is unbounded at the CLI and was unbounded here: a 300-character
# `skillforge done` message drew a 335-column segment that wrapped the terminal. It is
# capped, not padded -- a terminal record prints once and then holds still.
if [ "$running" -eq 0 ]; then phase="$(fit "$phase" "$TAIL_WIDTH" nopad)"; fi

case "$fstate" in
  done)
    printf '%s' "${count}${G}✓${X} ${M}forge${X} ${C}${name}${X} ${G}▕${bar}▏${X} ${D}forged · ${phase}${X}"
    ;;
  failed)
    printf '%s' "${count}${R}✗${X} ${M}forge${X} ${C}${name}${X} ${D}▕${bar}▏${X} ${R}abandoned${X} ${D}· ${phase}${X}"
    ;;
  *)
    # A case, not an array or `cut -c`: braille glyphs are multibyte, cut -c is
    # locale-dependent, bash 3.2 substring indexing is byte-based, and zsh arrays
    # are 1-indexed. A case statement is correct under every one of those.
    case $(( now % 8 )) in
      # The DENSE braille set, not the light one. ⠋/⠙/⠹ are two or three lit
      # dots in a 2x4 cell: at terminal font sizes they render as a faint speck
      # that reads as a stray punctuation mark next to the words beside it.
      # ⣾/⣽/⣻ light six of eight dots, so the spinner is legible as a spinner.
      # Eight phases rather than ten, because that is the set's natural period.
      0) spin=⣾ ;; 1) spin=⣽ ;; 2) spin=⣻ ;; 3) spin=⢿ ;;
      4) spin=⡿ ;; 5) spin=⣟ ;; 6) spin=⣯ ;; *) spin=⣷ ;;
    esac
    # Alternate the tail: 10s of "what is happening now", 5s of "what the skill is".
    if [ -n "$summary" ] && [ $(( (now / 5) % 3 )) -eq 2 ]; then
      tail="$summary"
    else
      tail="$phase"
    fi
    # The segment MUST keep a constant display width. The tail alternates between
    # two strings of unrelated length, and a status line whose width changes makes
    # the host clear and redraw the whole line -- which reads to the eye as the
    # progress bar disappearing and reappearing on every update. Pad/truncate to a
    # fixed column count so each refresh overwrites in place instead.
    # A quiet forge says so IN the tail, not beside it. Prefixing rather than
    # appending keeps the segment's display width byte-for-byte identical -- the tail
    # is padded to TAIL_WIDTH either way -- so crossing the threshold costs the host
    # no clear-and-redraw at all. What it costs is the end of a phase string that is,
    # by construction, hours out of date.
    # A spinning spinner beside the words "idle 3h07m" contradicts itself, and motion
    # is what the reported defect was misread as in the first place. So the spinner
    # FREEZES on a full braille cell and goes dim, the tail turns yellow, and the bar
    # stops pulsing: nothing on the segment moves except the rotation.
    #
    # `seam` is empty unless the forge is quiet, so a normally-stepped forge is
    # byte-for-byte identical to what this printed before -- escape sequences included,
    # not merely the visible text.
    seam=""
    spinc="$M"
    if [ "$is_idle" -eq 1 ]; then
      tail="idle $(fmt_idle "$idle") · $tail"
      spin=⣿
      spinc="$D"
      seam="${X}${Y}"
    fi
    tail="$(pad_to "$tail" "$TAIL_WIDTH")"
    # Same reason, two more places the width would otherwise wobble: 100% is a
    # column wider than 40%, and step 10 is a column wider than step 9. An overrun
    # can carry more digits than the budget, so the field is as wide as whichever is
    # longer; it grows once, at a real change of content, never once a second.
    step_w=${#steps}
    [ "${#step}" -gt "$step_w" ] && step_w=${#step}
    # `over` is exactly as wide as ` 99%`, so the overrun report shifts nothing. A
    # percentage of a budget that has already been spent is not a quantity worth
    # printing; the honest reading is in the `14/12` beside it.
    if [ "$over" -eq 1 ]; then pctf="over"; else pctf="$(printf '%3d' "$pct")%"; fi
    printf '%s' "${count}${spinc}${spin} forge${X} ${C}${name}${X} ${G}▕${bar}▏${X} ${D}$(printf "%${step_w}d" "$step")/${steps} ${pctf} · ${seam}${tail}${X}"
    ;;
esac

exit

# Closes the brace group opened just under `set -uo pipefail`. See the note there.
}
