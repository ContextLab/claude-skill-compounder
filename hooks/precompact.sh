#!/usr/bin/env bash
# Captures skill candidates from the transcript that is ABOUT TO BE SUMMARISED AWAY.
#
# Runs on PreCompact, which fires immediately before a compaction replaces the session's
# context with a summary. `hooks/insight-capture.sh` already captures the same material on
# Stop; this hook exists for the one case that path cannot cover -- a compaction with no
# preceding Stop capture -- and that is exactly the moment the loss matters most, because
# a session only compacts when it is carrying a lot.
#
# WHAT THIS HOOK IS NOT. There is no model in it. Issue #8 measured the alternative: a
# PreCompact hook BLOCKS compaction and has no default timeout, a 300-second hook stalled
# compaction for 300.9 seconds and ran to completion, and setting a timeout instead kills
# the writer mid-write -- a 3-second timeout against a 10-second writer left a CLAUDE.md
# truncated at line 4 of 11, silently, and the next session loaded the truncated file as
# project context without complaint. A Haiku subagent over a 256 KB tail took 54 seconds
# and $0.128, against a median real compaction of 128 seconds. So this hook does string
# extraction and nothing else, and its whole budget is 100 ms -- which is a figure PER jq
# BUILD, met on the system jq and missed by about a quarter on jq-1.6. The table by
# TAIL_BYTES carries both rows and the measurement that says the slow one cannot be made
# to fit.
#
# NEVER WRITE CLAUDE.md FROM A HOOK. This appends to the same weekly queue
# `insight-capture.sh` writes, and `skillinsight` (and `skillnote` behind it) is where a
# human decides what graduates. That decision is not a hook's to make and the write is not
# a hook's to attempt.
#
# ---------------------------------------------------------------------------------------
# THE PAYLOAD, measured on Claude Code 2.1.259, macOS 25.6.0, 2026-09-02 (see
# docs/CLAUDE-CODE-BEHAVIOR.md for the probe):
#
#   {"session_id","transcript_path","cwd","prompt_id","hook_event_name":"PreCompact",
#    "trigger":"manual"|"auto","custom_instructions":null}
#
# Three of those matter here.
#
#   - THERE IS NO `last_assistant_message`. Stop has one and this does not, so the free
#     path insight-capture.sh takes 76% of the time does not exist here. The transcript
#     read is mandatory, not a fallback, which is why the bound below is the single most
#     important constant in this file.
#   - THE FIELD IS `trigger`, NOT `compaction_trigger`. `permission_mode` is absent
#     despite being documented. Nothing here branches on either, deliberately: both
#     values name the same loss.
#   - `custom_instructions` IS NOT ALWAYS null, as of a re-probe on 2.1.260, 2026-09-03
#     (issue #32). A typed `/compact focus on the greeting` puts the argument there
#     VERBATIM as a plain JSON string -- no `/compact` prefix, no surrounding whitespace;
#     a bare `/compact` and every automatic compaction still put `null`. Nothing here
#     reads it and nothing here should: the only channel a PreCompact hook has back is
#     `systemMessage` on stdout, and this hook's first promise is that it never writes to
#     stdout at all. Reading the field would be a process start spent on a value with
#     nowhere to go. tests/test_precompact.py::CustomInstructionsTest pins both halves --
#     that a populated field changes nothing, and that a hostile one reaches no shell.
#
# ---------------------------------------------------------------------------------------
# WHY THIS IS ITS OWN SCRIPT AND NOT A THIRD ARM OF insight-capture.sh.
#
# That script runs `session_audit` and `dispatch_review` unconditionally on load, and both
# are Stop-shaped. The audit's claim key is the session id alone, so firing it here would
# spend the session's ONE audit record at compaction time, mid-session, describing a
# session that had not finished. And `dispatch_review` launches a paid `claude -p` -- from
# inside a hook that compaction is blocked on. Guarding all of that behind an event branch
# would leave a file that is mostly `if this is not PreCompact`, which is a second script
# wearing the first one's name.
#
# The extraction and the queue writer ARE duplicated, on purpose. This package's rule is
# "be idempotent per event", not "call one shared helper": `claim_once()` in
# compound-improvement.sh, the hash claim here and in insight-capture.sh, and the atomic
# mkdir in session-review.sh are four spellings of one idea and none of them reaches
# outside its own file. What must NOT diverge is the DIGEST, because that is the shared
# name two scripts look a record up under. `hash_of` and the `normalise` in the candidate
# scan below are byte-identical to insight-capture.sh's, and tests/test_precompact.py
# proves it the only way that means anything -- by running both hooks over the same
# candidate and asserting the second writes nothing.
#
# ---------------------------------------------------------------------------------------
# THE DOUBLE-QUEUE QUESTION, which is really two questions.
#
#   1. The same compaction delivered twice. With both wirings active (settings.json and
#      hooks/hooks.json) every hook fires twice. The guard is an atomic mkdir on a claim
#      keyed on the payload's own `prompt_id`, taken once candidates are in hand -- see
#      "one capture per compaction" below for why it sits there and not at the top, and
#      for what it actually buys, which is not the queue but the duplicate counter.
#   2. The same TEXT captured here and again at Stop. Nothing extra is needed: the queue
#      is content-addressed, both scripts hash the same normalised text with the same
#      digest, and `queue_record` claims that hash before it appends. Whichever hook gets
#      there first writes the row; the other one counts a duplicate and returns. So the
#      row's `source` records which hook won the race, never how many saw the candidate.
#
# ---------------------------------------------------------------------------------------
# Output is the same deduped weekly JSONL queue insight-capture.sh writes:
#   ${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}/insights/<ISO-week>.jsonl
# with `source: "precompact"`. `skillinsight list --source precompact` selects them and
# `skillinsight decline --source precompact` retires the whole bucket if it turns out to
# be noise. Nothing is ever forged from the queue automatically.
#
# Any failure exits 0 silently and nothing is ever written to stdout: this hook is on the
# critical path of a compaction, and a compaction that fails because a capture failed is a
# far worse outcome than a candidate that was not captured.
#
# Env:
#   PRECOMPACT_TAIL_BYTES  bounded transcript read budget (default 262144)
#   PRECOMPACT_MAX         cap on records appended per compaction (default 20)
#   PRECOMPACT_NOW         pins the clock, so the ISO-week filename is deterministic.
#                          Its own variable and not INSIGHT_NOW: a test that pins one
#                          script's clock must not silently pin another's.
#   PRECOMPACT_DEBUG_DUMP  append the raw stdin payload to this path for inspection
#   SKILL_COMPOUNDER_STATE redirects the state root
set -uo pipefail

# ------------------------------------------------------------------------------------
# THE ENTIRE BODY OF THIS SCRIPT IS ONE BRACE GROUP, AND THE `}` AT THE END OF THE FILE
# IS WHAT CLOSES IT, with an `exit` as the last statement inside it. Both halves are
# required and neither is decoration: bash reads a script lazily by byte offset, so a
# `git pull` during a run resumes execution inside whatever bytes the file now holds. A
# brace group forces the whole file through the parser in one pass; the trailing `exit`
# stops bash resuming at the offset just past `}`. See the same note in
# hooks/insight-capture.sh, docs/DESIGN.md under "Never edit a script that may still be
# running", and tests/test_script_wrapping.py, which is the ratchet.
# ------------------------------------------------------------------------------------
{

# THE BOUND IS THE COST MODEL, and it is not really about bytes. THE 100 ms BUDGET FROM
# ISSUE #8 IS A PER-jq FIGURE and cannot be anything else; issue #32 settled which of the
# two answers it gets. End-to-end wall-clock over a 400 KB transcript at the default
# 256 KB bound, the two builds interleaved run-for-run so a loaded box costs both arms
# alike, macOS 25.6.0, 2026-09-03, load average 9.5, n=25, median / p90:
#
#                                       no candidate       one candidate
#     /usr/bin/jq (jq-1.7.1-apple)    31.8 / 36.0 ms     84.7 /  87.7 ms
#     anaconda's jq-1.6 on PATH       59.1 / 63.5 ms    123.0 / 128.9 ms
#
# So the budget HOLDS on the system jq, at the median and at p90, and IS MISSED BY ABOUT
# A QUARTER on jq-1.6. Quote the second row to anyone whose PATH resolves jq to a slow
# build. It is still 0.1% of the 128-second median compaction this hook delays, which is
# why the answer was to state the figure rather than block on it.
#
# WHY THE SLOW BUILD CANNOT BE MADE TO FIT, which is the half of #32 that took measuring.
# What this hook spends is PROCESS STARTS -- `jq -n 1` medians 8.2 ms as /usr/bin/jq and
# 21.8 ms as jq-1.6, `shasum` 18 ms, `git rev-parse` 20 ms, `tail -c` 16 ms -- so the
# question is how few programs the candidate path can run. It runs 13 now, three fewer
# than it shipped with (see the `date`, `ensure_queue_dir` and event-claim notes below,
# each of which names the start it dropped), and that bought 20 ms on both builds. It is
# not enough and nothing left is sheddable: on jq-1.6 the NO-candidate path alone costs
# 59 ms, and writing a record cannot cost less than a third `jq` (17 ms), the `hash_of`
# pipeline (`shasum`, `awk`, `tr`; 18 ms), two claim `mkdir`s and a `grep`. That floor is
# above 100 ms. Shedding `git rev-parse` on top was measured too -- 106 ms median, still
# over, and a bash walk-up for `.git` disagrees with `git rev-parse --show-toplevel` on
# every symlinked path, which on macOS includes everything under /tmp. The only remaining
# candidate is `hash_of`, and that one is not on the table: its digest is the shared name
# insight-capture.sh looks a record up under, so changing it would trade 18 ms for a
# silently doubled queue.
#
# The byte count is a detail beside all that, which is why tests/test_precompact.py pins
# the process count and not a stopwatch: an assertion tight enough to catch one added
# `jq` flakes on a loaded machine, and the pin does not.
#
# 256 KB is insight-capture.sh's bound and the "256 KB tail" issue #8 costed, and it is
# what keeps the candidate path under the 100 ms that issue set. Raising it is one
# environment variable for anyone who would rather have the coverage. It is not unbounded
# for the reason insight-capture.sh gives: the largest real transcript measured 663 MB and
# an unbounded read is a hang, which on THIS event means a hung compaction.
TAIL_BYTES="${PRECOMPACT_TAIL_BYTES:-262144}"
MAX_RECORDS="${PRECOMPACT_MAX:-20}"
# HOME can be unset (cron, a stripped env, a container). Under `set -u` reading it then
# aborts the script non-zero, which breaks the one promise a hook has to keep.
: "${HOME:=/tmp}"
ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
DIR="$ROOT/insights"

payload="$(cat)"
[ -n "${PRECOMPACT_DEBUG_DUMP:-}" ] && printf '%s\n' "$payload" >> "$PRECOMPACT_DEBUG_DUMP"

command -v jq >/dev/null 2>&1 || exit 0

case "$TAIL_BYTES" in ''|*[!0-9]*) TAIL_BYTES=262144 ;; esac
[ "$TAIL_BYTES" -lt 1 ] && TAIL_BYTES=262144
case "$MAX_RECORDS" in ''|*[!0-9]*) MAX_RECORDS=20 ;; esac

now="${PRECOMPACT_NOW:-$(date -u +%s 2>/dev/null)}"
case "$now" in ''|*[!0-9]*) exit 0 ;; esac

# BSD date wants -r <seconds>, GNU date wants -d @<seconds>. Try both, in that order.
stamp() { date -u -r "$now" "+$1" 2>/dev/null || date -u -d "@$now" "+$1" 2>/dev/null; }
# ONE `date`, not two. Both values come from the same instant, so a second start bought
# nothing but 2-5 ms -- see the table by TAIL_BYTES, where the cost model is process
# starts. `%n` is strftime's newline and is honoured by BSD and GNU date alike, so the two
# values arrive on two lines and are read the way the payload's four fields are read
# below: one `IFS= read` each, initialised first, for the same reason given there.
ts=""; week=""
{ IFS= read -r ts; IFS= read -r week; } <<STAMP_EOF
$(stamp '%Y-%m-%dT%H:%M:%SZ%n%G-W%V')
STAMP_EOF
[ -z "$ts" ] && exit 0
[ -z "$week" ] && exit 0

# One jq over the payload rather than four, because a jq start is 10-22 ms here and the
# budget is 100 ms. The four values come back on FOUR LINES, one `read` each, and that is
# the shape rather than one tab-separated line for a reason that cost a test to find:
#
#   TAB IS AN IFS WHITESPACE CHARACTER, so `IFS=$'\t' read -r a b c d` collapses a run of
#   tabs into ONE delimiter. `@tsv` of ["s1", "", "/t", "/c"] is `s1\t\t/t\t/c`, and that
#   read puts `/t` in b and `/c` in c -- every field after the empty one shifts left. The
#   payload field most likely to be empty is `prompt_id`, which is undocumented, so the
#   failure mode was: a build stops sending `prompt_id`, the transcript path lands in the
#   variable holding the claim key, `[ -f "$tp" ]` tests the cwd, and the hook silently
#   captures nothing for ever. Nothing about it would look wrong.
#
# `IFS=` on each read keeps a path with leading or trailing spaces intact, and the four
# variables are initialised first because `read` at end-of-input leaves the rest of them
# holding whatever they held before.
sid=""; pid=""; tp=""; cwd=""
{ IFS= read -r sid; IFS= read -r pid; IFS= read -r tp; IFS= read -r cwd; } <<PAYLOAD_EOF
$(printf '%s' "$payload" | jq -r '
  def f: (. // "") | tostring | gsub("[\t\n\r]"; " ");
  (.session_id|f), (.prompt_id|f), (.transcript_path|f), (.cwd|f)' 2>/dev/null)
PAYLOAD_EOF

[ -z "$sid" ] && sid="nosession"
[ -n "$tp" ] || exit 0
[ -f "$tp" ] || exit 0

file="$DIR/$week.jsonl"
dupes="$DIR/.dedup-count"
CLAIMS="$DIR/.claims"

# Byte-identical to hash_of in hooks/insight-capture.sh, and that is the point: the two
# scripts must look a record up under the SAME name or the content dedup between them is
# a no-op that fails silently, by writing a duplicate. awk printf, not print: `tr -c`
# would otherwise turn the trailing newline into a `_` and change every digest.
hash_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 1
  elif command -v sha1sum >/dev/null 2>&1; then sha1sum
  else cksum
  fi | awk '{printf "%s", $1; exit}' | tr -c 'A-Za-z0-9' '_'
}

# The queue directory is created on FIRST WRITE, never on load -- the same contract
# insight-capture.sh keeps, so "nothing was captured" stays testable. The per-compaction
# claim below needs the directory in order to claim anything at all, which is the second
# reason it is taken only once candidates are in hand rather than at the top of the file.
# `mkdir -p "$DIR/.claims"` makes BOTH directories, so the common path is ONE start and
# not two. The fallback is unchanged and still costs two: if `.claims` cannot be made, try
# `$DIR` alone before giving up, which is the case where the queue directory exists but is
# read-only. Ordering it the other way round -- $DIR first, then .claims -- charged every
# ordinary compaction for the failure path.
ensure_queue_dir() {
  [ -d "$CLAIMS" ] && return 0
  if mkdir -p "$DIR/.claims" 2>/dev/null; then
    CLAIMS="$DIR/.claims"
  else
    mkdir -p "$DIR" 2>/dev/null || return 1
    CLAIMS="$DIR"
  fi
  return 0
}

note_duplicate() {
  n=0; [ -f "$dupes" ] && n="$(cat "$dupes" 2>/dev/null || echo 0)"
  case "$n" in ''|*[!0-9]*) n=0 ;; esac
  printf '%s' "$(( n + 1 ))" > "$dupes" 2>/dev/null
}

release_claim() {
  [ -n "${qr_claimed:-}" ] && rmdir "$qr_claimed" 2>/dev/null
  qr_claimed=""
  return 0
}

# queue_record <source> <text-to-hash> <record-text-as-a-JSON-string>
# 0 = appended, 1 = duplicate or unbuildable, 2 = the queue file is unwritable.
# The claim-then-grep order, the subshell around the append, and the release on a failed
# append are all insight-capture.sh's, for the reasons documented there.
queue_record() {
  qr_h="$(printf '%s' "$2" | hash_of 2>/dev/null)"
  [ -z "$qr_h" ] && return 1
  ensure_queue_dir || return 2
  qr_claimed=""
  if mkdir "$CLAIMS/$qr_h" 2>/dev/null; then
    qr_claimed="$CLAIMS/$qr_h"
  elif [ -d "$CLAIMS/$qr_h" ]; then
    note_duplicate
    return 1
  fi
  if grep -F -q "\"hash\":\"$qr_h\"" "$DIR"/*.jsonl 2>/dev/null; then
    note_duplicate
    return 1
  fi
  qr_rec="$(jq -c -n --arg ts "$ts" --arg week "$week" --arg source "$1" \
    --arg session "$sid" --arg project "$project" --argjson text "$3" --arg hash "$qr_h" \
    '{ts:$ts, week:$week, source:$source, session:$session, project:$project, text:$text, hash:$hash}' 2>/dev/null)" \
    || { release_claim; return 1; }
  if [ -z "$qr_rec" ]; then release_claim; return 1; fi
  # The subshell is what keeps stderr quiet: `>> "$file" 2>/dev/null` does not, because
  # the shell reports a failed redirect before it applies the 2>/dev/null on the same
  # command.
  if ( printf '%s\n' "$qr_rec" >> "$file" ) 2>/dev/null; then
    return 0
  fi
  release_claim
  return 2
}

# ------------------------------------------------- the transcript and the candidates
# ONE jq, not two, and the reason is a stopwatch. An `exec` on the machine this was
# measured on costs 10-22 ms before the program starts -- see the table by TAIL_BYTES --
# so on a hook with a 100 ms budget the process COUNT is the cost model and the byte
# count is a detail. Reading the transcript in one
# process and scanning it in another was a whole jq start of pure overhead for nothing.
#
# The two halves are still the two halves insight-capture.sh runs. The SCANNER is copied
# verbatim; the reader is the same filter re-expressed to run in the same process:
#
#   - The reader. `tail -c` leaves a truncated first line; `fromjson? // empty` drops it.
#     The type filter is what keeps the learning-output-style plugin's own injected
#     instruction out of the queue: 584 of 854 raw marker hits in the wild rode in
#     `attachment` records, never in assistant text. `[inputs] | join("\n")` is the one
#     re-expression, and it reproduces exactly what `$(jq -R -r ...)` produced when this
#     was a pipeline -- compared byte-for-byte against both a 5 MB transcript and a
#     three-record fixture before the merge landed, and held to it afterwards by
#     test_both_hooks_reading_the_same_transcript_agree.
#   - The scanner, `normalise` included, because the normalised text is what gets hashed
#     and the hash is the name insight-capture.sh looks the same record up under. Change
#     one and you must change the other, or one sentence gets two rows under two digests.
#     tests/test_precompact.py proves the two agree by running both hooks over one
#     transcript and asserting the second writes nothing.
# THE PARAGRAPH TERMINATOR IS A LOOKAHEAD, `(?=\n[ \t]*\n|\z)`, AND MUST STAY ONE.
# As a consuming group it ate the blank line that ended each candidate, so `scan` resumed
# with no newline in front of the NEXT marker and the leading `(?:^|\n)` could not assert:
# a marker immediately after another was silently dropped, and three in a row lost the
# middle one. Two markers with prose between them were found normally, which is why it
# went unseen. Measured on jq-1.7.1-apple and jq-1.6, 2026-09-02.
#
# THIS SCAN IS THE SAME CODE TWICE. Its twin is in hooks/insight-capture.sh, and the two must
# never diverge: the normalised text is what gets hashed, the hash is the name each hook
# looks the other's record up under, and one sentence scanned two ways becomes two rows
# under two digests instead of one row and a counted duplicate. Change one, change both.
candidates="$(tail -c "$TAIL_BYTES" "$tp" 2>/dev/null | jq -R -r -n '
  def normalise: gsub("\\s+"; " ") | sub("^ +"; "") | sub(" +$"; "") | sub("\\.$"; "");
  def injected:
    test("key educational points"; "i")
    or test("In order to encourage learning"; "i")
    or test("brief educational explanations about implementation choices"; "i");
  def emit(src):
    (sub("^\\s+"; "") | sub("\\s+$"; "")) as $raw
    | ($raw | normalise) as $n
    | select(($n | length) >= 24 and (($n | injected) | not))
    | src + "\t" + $n + "\t" + ($raw | @json);
  ( [ inputs
      | (fromjson? // empty)
      | select(.type == "assistant")
      | select((.isSidechain // false) | not)
      | .message.content[]?
      | select(.type == "text")
      | (.text // "") ] | join("\n") ) as $t
  | ( [ $t | scan("(?:^|\\n)[ \\t]*(?:★ Skill candidate:|SKILL-CANDIDATE:)[ \\t]*([\\s\\S]*?)(?=\\n[ \\t]*\\n|\\z)") | .[0] ]
      | .[] | emit("marker") ),
    ( [ $t | scan("`?★ Insight[ ─]*`?\\n([\\s\\S]*?)\\n`?─{5,}`?") | .[0] ]
      | .[] | emit("star-insight") )
  ' 2>/dev/null)"

[ -z "$candidates" ] && exit 0

# ------------------------------------------------------- one capture per compaction
# THE CLAIM IS TAKEN HERE, once the work is really going to happen, and not at the top of
# the script. Two independent reasons point at this line and no earlier one.
#
#   - Claiming before the gates is the bug hooks/session-review.sh shipped first: a run
#     the later gates refused had already burned its claim, so it could never run at all.
#     Everything above this line can still refuse.
#   - The queue directory is created on FIRST WRITE, never on load. A claim taken at the
#     top would have to create `insights/` on every compaction that captured nothing,
#     which is most of them, and would turn "nothing was captured" into something no
#     caller can test for. insight-capture.sh keeps the same contract and
#     tests/test_insights.py pins it there.
#
# The key is the payload's own `prompt_id`, unique per compaction and present on both
# triggers (measured, 2.1.259). A payload without one falls back to the session id plus
# the transcript's size, so a session that compacts twice is still two keys -- the bare
# session id would silently capture only the FIRST compaction of a long session, which is
# the opposite of what this hook is for.
#
# The content claim inside queue_record would already stop the second delivery writing a
# second row, so this is not what keeps the queue clean. What it keeps honest is the
# COUNTER: without it the second delivery walks every candidate, finds every content claim
# held, and bumps `.dedup-count` once per candidate per compaction -- turning "duplicates
# skipped", which `skillinsight stats` reports as candidates seen more than once, into a
# count of how many times the hook was wired. That is the same distortion insight-capture's
# `quiet` flag exists to prevent, arriving from the other direction.
#
# THIS KEY IS NOT HASHED, and that is the one place this hook deliberately does not reach
# for `hash_of`. A hash is a SHARED NAME -- it exists so insight-capture.sh can look the
# same candidate up under it -- and nothing outside this file ever looks an event claim
# up. Paying for one is three process starts (`shasum`, `awk`, `tr`; ~18 ms on jq-1.6's
# machine, and `shasum` on macOS is a perl script) for a name only this script reads. So
# the key is built with bash parameter expansion, which forks nothing: every character
# outside `[A-Za-z0-9._-]` becomes `_`, and the result is capped well under the 255-byte
# filename limit. Session and prompt ids are UUIDs, so the cap is slack rather than a
# truncation anyone will meet.
#
# It cannot collide with a content claim in the same directory. `hash_of` ends in
# `tr -c 'A-Za-z0-9' '_'`, so a content name can only ever hold letters, digits and
# underscores -- while every event name starts with the literal `precompact-event-`, and
# that hyphen is a character no content name can contain.
#
# One upgrade effect, and it is bounded: a compaction claimed under the old hashed name is
# not recognised under the new one. The content claim inside queue_record still stops a
# second row, so the only thing that can double is `.dedup-count`, once, for a compaction
# in flight across the upgrade.
if [ -n "$pid" ]; then
  ev_key="${sid}-${pid}"
else
  ev_size="$(wc -c < "$tp" 2>/dev/null | tr -cd '0-9')"
  [ -z "$ev_size" ] && ev_size=0
  ev_key="${sid}-${ev_size}"
fi
ev_h="precompact-event-${ev_key//[!A-Za-z0-9._-]/_}"
ev_h="${ev_h:0:200}"
# No `[ -n "$ev_h" ]` guard: it was there because `hash_of` could fail and hand back an
# empty name, and the expansion above cannot -- it always carries the literal prefix. A
# guard that can no longer fire is a guard nobody can test, so it is gone rather than
# kept for symmetry.
ensure_queue_dir || exit 0
# Both placements, because ensure_queue_dir falls back to $DIR when .claims cannot be
# made; checking only the preferred one would re-capture on every delivery in that case.
if [ -d "$CLAIMS/$ev_h" ] || [ -d "$DIR/$ev_h" ]; then exit 0; fi
mkdir "$CLAIMS/$ev_h" 2>/dev/null || exit 0

# Only now is the project worth resolving. `git rev-parse` is a fork and most compactions
# carry no candidate, so paying for it up front would be ~8 ms spent on nothing.
[ -z "$cwd" ] && cwd="$PWD"
project="$(cd "$cwd" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$project" ] && project="$cwd"

# The signal that found each candidate (`marker` or `star-insight`) is deliberately NOT
# folded into the source. `source` answers "which hook wrote this row", and one bucket is
# what makes `skillinsight decline --source precompact` able to retire this experiment in
# a single command if it turns out to be noise.
written=0
while IFS="$(printf '\t')" read -r src norm json; do
  [ -z "$src" ] && continue
  [ -z "$json" ] && continue
  [ "$written" -ge "$MAX_RECORDS" ] && break
  queue_record "precompact" "$norm" "$json"
  rc=$?
  # 2 means the queue file itself could not be appended to. Every later candidate would
  # fail identically, so stop rather than spin -- and stop at 0, because a capture never
  # breaks a compaction.
  [ "$rc" -eq 2 ] && exit 0
  [ "$rc" -eq 0 ] && written=$(( written + 1 ))
done <<CANDIDATES_EOF
$candidates
CANDIDATES_EOF

exit 0

# Closes the brace group opened just under `set -uo pipefail`. See the note there.
}
