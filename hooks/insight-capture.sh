#!/usr/bin/env bash
# Captures skill candidates from a finished turn and queues them for weekly review.
#
# Runs on Stop. It also accepts SubagentStop without exploding, but do not expect
# anything from it: 1428 subagent transcripts on the research machine contained zero
# `★ Insight` blocks, because the output-style plugin's SessionStart injection never
# reaches a subagent. An explicit marker written by a subagent is still captured.
# See notes/research/insight-capture.md.
#
# Two candidate signals, in order of trust:
#
#   1. THE EXPLICIT MARKER (primary). A line of the form
#          ★ Skill candidate: <one or more sentences>
#      or  SKILL-CANDIDATE: <one or more sentences>
#      and the text that follows it to the end of the paragraph (the next blank line,
#      or the end of the message). The session writes this when it means it, so it
#      survives any output style and any plugin being disabled.
#
#   2. `★ Insight` BLOCKS (opportunistic feeder). These exist only because the
#      learning-output-style plugin injects the instruction at SessionStart. Their
#      absence is normal and is never an error.
#
# Input path. `.last_assistant_message` is present on Stop and SubagentStop and alone
# catches 76% of blocks at zero I/O, so it is tried first. Only if it is absent or
# yields nothing does the hook fall back to a BOUNDED tail of `.transcript_path`.
# The bound is not optional: the largest real transcript measured 663 MB, and an
# unbounded read is a hang. The fallback also filters to `.type=="assistant"` records
# and `content[].type=="text"` parts, because 584 of 854 raw marker hits in the wild
# were the plugin's own injection echoed back inside `attachment` records. Ingesting
# those means the queue fills with our own instruction text.
#
#   3. THE SESSION AUDIT (`source:"session-audit"`), which asks the session nothing at
#      all. The other two signals both require the session to write something; a session
#      that reads the checkpoint and disregards it leaves no trace, and that is the
#      failure this arm exists for. Measured: one long session fired the 12-edit
#      checkpoint at edits 12, 24 and 36 and disregarded it all three times, while fixing
#      nine defects of one kind -- because the checkpoint asks about the procedure being
#      worked on RIGHT NOW, and per-instance the honest answer is always "no, I am just
#      fixing a bug". So this arm stops asking. Once a session has crossed a purely
#      mechanical threshold it writes ONE record stating what was observed, whether or
#      not the session ever read a word of it. Recurrence across instances is then judged
#      at `skillinsight review`, by someone reading the whole set cold, which is the only
#      vantage point from which the cross-instance question is answerable.
#
#      It records; it never classifies. A hook cannot tell that nine fixes were "of the
#      same kind" -- that is exactly the judgement that failed -- so it does not guess a
#      category. It states edits counted, files touched, checkpoints fired, and which
#      forges (if any) were started, all of which are true without interpretation.
#
# Output is a deduped weekly JSONL queue at
#   ${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}/insights/<ISO-week>.jsonl
# Nothing is ever forged from it automatically. `skillinsight review` is the next step.
#
# Any failure exits 0 silently, and nothing is written to stdout ever: a capture must
# never break the user's turn.
#
# Env:
#   INSIGHT_TAIL_BYTES   bounded transcript read budget (default 262144)
#   INSIGHT_MAX_PER_TURN cap on records appended per turn (default 20)
#   INSIGHT_AUDIT_MIN_EDITS  session-audit edit threshold (default 24; 0 disables the arm)
#   INSIGHT_AUDIT_MIN_FILES  session-audit distinct-file threshold (default 8)
#   INSIGHT_AUDIT_MAX_PATHS  paths listed inline in the record (default 40)
#   INSIGHT_NOW / CI_NOW pin the clock, so the ISO-week filename is deterministic
#   INSIGHT_DEBUG_DUMP   append the raw stdin payload to this path for inspection
set -uo pipefail

TAIL_BYTES="${INSIGHT_TAIL_BYTES:-262144}"
MAX_PER_TURN="${INSIGHT_MAX_PER_TURN:-20}"
# HOME can be unset (cron, a stripped env, a container). Under `set -u` reading it then
# aborts the script non-zero, which breaks the one promise a hook has to keep.
: "${HOME:=/tmp}"
ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
DIR="$ROOT/insights"
# Written by hooks/compound-improvement.sh on PostToolUse. Same state root, same session
# id: verified on CLI 2.1.245 that PostToolUse and Stop carry an identical `.session_id`,
# which is what lets a Stop-time audit read counters an edit-time hook wrote. (The OTHER
# session id, $CLAUDE_CODE_SESSION_ID, differs from both -- see docs/DESIGN.md. Neither
# side here touches it.)
#
# DELEGATING TO A SUBAGENT DOES NOT ESCAPE THE COUNT. Measured on 2.1.245, macOS
# 25.5.0, 2026-08-25, by running a headless session whose only instruction was to
# dispatch a subagent to write a file, with a hook dumping every payload: the
# subagent's `Write` arrived as an ordinary PostToolUse carrying the PARENT session's
# `.session_id` (plus an `agent_id` the parent's own events lack). So a session that
# fans its edits out to subagents still accumulates them against one set of counters,
# and the audit still sees them. This was worth measuring rather than assuming --
# had it carried the subagent's own id, every counter would have been split across
# ids that no Stop ever names, and the arm would have been silently dead for exactly
# the delegating sessions it most needs to cover.
REMINDERS="$ROOT/reminders"
AUDIT_MIN_EDITS="${INSIGHT_AUDIT_MIN_EDITS:-24}"
AUDIT_MIN_FILES="${INSIGHT_AUDIT_MIN_FILES:-8}"
AUDIT_MAX_PATHS="${INSIGHT_AUDIT_MAX_PATHS:-40}"

payload="$(cat)"
[ -n "${INSIGHT_DEBUG_DUMP:-}" ] && printf '%s\n' "$payload" >> "$INSIGHT_DEBUG_DUMP"

command -v jq >/dev/null 2>&1 || exit 0

now="${INSIGHT_NOW:-${CI_NOW:-$(date -u +%s 2>/dev/null)}}"
case "$now" in ''|*[!0-9]*) exit 0 ;; esac

# BSD date wants -r <seconds>, GNU date wants -d @<seconds>. Try both, in that order.
stamp() { date -u -r "$now" "+$1" 2>/dev/null || date -u -d "@$now" "+$1" 2>/dev/null; }
ts="$(stamp %Y-%m-%dT%H:%M:%SZ)"
week="$(stamp %G-W%V)"
[ -z "$ts" ] && exit 0
[ -z "$week" ] && exit 0

sid="$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null)"
[ -z "$sid" ] && sid="nosession"

cwd="$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)"
[ -z "$cwd" ] && cwd="$PWD"
project="$(cd "$cwd" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$project" ] && project="$cwd"

# ------------------------------------------------------------- the queue writer
# Hoisted above the text extraction because the session audit below writes a record
# on turns that produce no candidate text at all -- which is most of them, and is
# exactly the case the audit exists to cover.
# Sanitising here rather than at each call site is load-bearing: the digest doubles as
# a claim DIRECTORY NAME and as a grep needle, and two call sites that sanitise
# differently would look for the same record under two names -- which fails silently, by
# writing a duplicate.  shasum gives hex and cksum gives digits, so today this changes
# nothing; it is here so that a future digest change cannot.
hash_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 1
  elif command -v sha1sum >/dev/null 2>&1; then sha1sum
  else cksum
  # awk printf, not print: `tr -c` would otherwise turn the trailing newline into a `_`
  # and silently change every digest, orphaning every claim already on disk.
  fi | awk '{printf "%s", $1; exit}' | tr -c 'A-Za-z0-9' '_'
}

file="$DIR/$week.jsonl"
dupes="$DIR/.dedup-count"
# One directory per captured hash, used purely as an atomic claim. Cheap to create and
# pruned with the queue, so it never needs its own lifecycle.
CLAIMS="$DIR/.claims"

# The queue directory is created on FIRST WRITE, never on load. Creating it up here
# instead is a silent contract break: most turns capture nothing, and a hook that
# leaves a directory behind on every one of them turns "nothing was captured" into
# something a caller can no longer test for. tests/test_insights.py pins it.
ensure_queue_dir() {
  [ -d "$CLAIMS" ] && return 0
  mkdir -p "$DIR" 2>/dev/null || return 1
  if mkdir -p "$DIR/.claims" 2>/dev/null; then
    CLAIMS="$DIR/.claims"
  else
    CLAIMS="$DIR"
  fi
  return 0
}

# Both duplicate paths, the atomic claim and the queue grep, report through here, so the
# count stays honest whichever one caught it.
note_duplicate() {
  n=0; [ -f "$dupes" ] && n="$(cat "$dupes" 2>/dev/null || echo 0)"
  case "$n" in ''|*[!0-9]*) n=0 ;; esac
  printf '%s' "$(( n + 1 ))" > "$dupes" 2>/dev/null
}

# queue_record <source> <text-to-hash> <record-text-as-a-JSON-string> [quiet]
# 0 = a record was appended, 1 = duplicate or unbuildable, 2 = the queue file is
# unwritable. The caller decides what a 2 means; for the candidate loop it ends the
# turn, because every later append would fail the same way.
#
# `quiet` suppresses the duplicate counter. `skillinsight stats` reports that number as
# "duplicates skipped", meaning candidates seen more than once -- and a caller that
# deliberately re-offers the same key on every turn, as the session audit does, would
# otherwise turn that statistic into a turn counter.
#
# Dedup is against the whole queue, not just this week, and the record is appended
# before the next candidate is hashed, so a repeat inside one turn is caught too.
# Claim the hash with mkdir before the grep. mkdir is atomic; grep-then-append is a
# read-then-write, and this hook runs on Stop, which BOTH install paths deliver. Twelve
# concurrent identical payloads produced six records against a wanted one. The claim
# settles the race; the grep below still catches repeats across earlier weeks, and a
# claim that cannot be written falls through to the grep rather than dropping the
# candidate.
# Undo a claim this call created, so a write that never happened does not permanently
# retire the key. Only ever removes a directory this invocation made: a claim that was
# already there belongs to whoever wrote the record it protects.
release_claim() {
  [ -n "${qr_claimed:-}" ] && rmdir "$qr_claimed" 2>/dev/null
  qr_claimed=""
  return 0
}

queue_record() {
  qr_h="$(printf '%s' "$2" | hash_of 2>/dev/null)"
  [ -z "$qr_h" ] && return 1
  ensure_queue_dir || return 2
  qr_claimed=""
  if mkdir "$CLAIMS/$qr_h" 2>/dev/null; then
    qr_claimed="$CLAIMS/$qr_h"
  elif [ -d "$CLAIMS/$qr_h" ]; then
    [ "${4:-}" = "quiet" ] || note_duplicate
    return 1
  fi
  if grep -F -q "\"hash\":\"$qr_h\"" "$DIR"/*.jsonl 2>/dev/null; then
    [ "${4:-}" = "quiet" ] || note_duplicate
    return 1
  fi
  qr_rec="$(jq -c -n --arg ts "$ts" --arg week "$week" --arg source "$1" \
    --arg session "$sid" --arg project "$project" --argjson text "$3" --arg hash "$qr_h" \
    '{ts:$ts, week:$week, source:$source, session:$session, project:$project, text:$text, hash:$hash}' 2>/dev/null)" \
    || { release_claim; return 1; }
  if [ -z "$qr_rec" ]; then release_claim; return 1; fi
  # The subshell is what keeps stderr quiet. `>> "$file" 2>/dev/null` does not: the
  # shell reports a failed redirect (a directory at that path, say) BEFORE it applies
  # the 2>/dev/null on the same command, so the message reaches the terminal and the
  # hook stops being silent. Redirecting the subshell's stderr happens first.
  if ( printf '%s\n' "$qr_rec" >> "$file" ) 2>/dev/null; then
    return 0
  fi
  # RELEASE THE CLAIM. The claim is taken before the append so two racing hooks cannot
  # both write; if the append then fails -- a full disk, a read-only queue -- keeping it
  # would retire the key forever. That is survivable for a candidate, which recurs, and
  # permanent for the session audit, whose key is the session id and is offered once.
  release_claim
  return 2
}

# ------------------------------------------------------------- the session audit
# THE ONE ARM THAT ASKS THE SESSION NOTHING. See the header for why it exists.
#
# It reads only what hooks/compound-improvement.sh already wrote on PostToolUse, and
# the skillforge ledger. Every number below is a count of something on disk. Nothing
# here interprets, categorises, or guesses what the session was doing, because the
# judgement this replaces is precisely the one that answered "no" nine times running.
#
# Exactly ONE record per session, ever. The claim is the hash, which is derived from
# the session id alone, so re-firing on every later Stop -- and the second delivery
# from the other install path -- lands on an existing claim and writes nothing.
# Measured rate on 97 real main-session transcripts on this machine, spanning 23.8
# days: 13 sessions cross edits>=24 AND distinct-files>=8, i.e. about 3.8 records a
# week against an existing queue rate of roughly 30 a week. That count is a LOWER
# bound, because it counted Write/Edit tool calls only and the hook also counts
# file-writing Bash. A queue that fires constantly gets switched off, which is worse
# than one that misses; a queue that never fires on the case it was built for is what
# we have today.
#
# Failure is silent and total: any unreadable or absent piece of state means no audit,
# and the two reminder arms are unaffected.
session_audit() {
  case "$AUDIT_MIN_EDITS" in ''|*[!0-9]*) return 0 ;; esac
  [ "$AUDIT_MIN_EDITS" -eq 0 ] && return 0
  case "$AUDIT_MIN_FILES" in ''|*[!0-9]*) return 0 ;; esac
  case "$AUDIT_MAX_PATHS" in ''|*[!0-9]*) sa_max=40 ;; *) sa_max="$AUDIT_MAX_PATHS" ;; esac
  [ "$sa_max" -lt 1 ] && sa_max=1

  # compound-improvement.sh sanitises the session id before using it in a filename.
  # This must sanitise identically or the audit looks at a file that never exists --
  # and it would fail SILENTLY, finding no counters and concluding the session did
  # nothing. Keep the two expressions the same.
  sa_sid="$(printf '%s' "$sid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"

  # The claim key is the session id and nothing else, so it is known before any state
  # is read. Checking it FIRST is what keeps this arm off the per-turn hot path: a
  # session that already has its record does one directory test per Stop and stops,
  # instead of re-counting its files and re-grepping every queue file in the directory.
  # The wording of the record below is deliberately not part of the key -- changing the
  # prose in a later version must not re-issue records for sessions already audited.
  sa_key="$(printf 'session-audit\t%s' "$sa_sid")"
  sa_h="$(printf '%s' "$sa_key" | hash_of 2>/dev/null)"
  # Tests both placements a claim can have, and creates neither: ensure_queue_dir falls
  # back to $DIR itself when .claims cannot be made. Checking only the preferred one
  # would re-audit every turn in that degraded case.
  if [ -n "$sa_h" ] && { [ -d "$CLAIMS/$sa_h" ] || [ -d "$DIR/$sa_h" ]; }; then
    return 0
  fi

  sa_edits_f="$REMINDERS/$sa_sid.edits"
  [ -f "$sa_edits_f" ] || return 0
  sa_edits="$(wc -c < "$sa_edits_f" 2>/dev/null | tr -d ' ')"
  case "$sa_edits" in ''|*[!0-9]*) return 0 ;; esac
  [ "$sa_edits" -ge "$AUDIT_MIN_EDITS" ] || return 0

  sa_paths_f="$REMINDERS/$sa_sid.paths"
  sa_files=0
  if [ -f "$sa_paths_f" ]; then
    sa_files="$(sort -u "$sa_paths_f" 2>/dev/null | grep -c '[^[:space:]]' 2>/dev/null | tr -d ' ')"
  fi
  case "$sa_files" in ''|*[!0-9]*) sa_files=0 ;; esac

  # Edits whose target the hook could not see -- shell writes through a heredoc, a
  # redirect or an inline interpreter, which arrive as a command string with no
  # file_path. The gate adds them to the visible-file count, which is an UPPER bound on
  # the number of distinct sites and not a measurement of it -- twenty-four `sed -i` on
  # one README is twenty-four opaque edits and one site. That is fine for a threshold
  # and would be a lie in the record, so the record prints the two component numbers
  # and never their sum. Refusing to count them at all silences precisely the long
  # autonomous sessions
  # this record exists for: in this machine's 97 transcripts, six sessions passed 24
  # edits with fewer than 8 visible paths, one of them 356 shell writes against 4.
  #
  # STATED PLAINLY, BECAUSE THE OPPOSITE IS THIS PACKAGE'S OWN FAILURE MODE: on those
  # 97 transcripts the breadth gate below fires on exactly the same 22 sessions as no
  # breadth gate at all (6.5 records a week either way). It is filtering nothing on
  # real data. It is kept because it does express a real exclusion -- forty edits to
  # two files is one task iterated, not many tasks -- which this sample happens not to
  # contain. Do not describe it as a filter until something measures it filtering.
  sa_opaque=0
  [ -f "$REMINDERS/$sa_sid.opaque" ] && \
    sa_opaque="$(wc -c < "$REMINDERS/$sa_sid.opaque" 2>/dev/null | tr -d ' ')"
  case "$sa_opaque" in ''|*[!0-9]*) sa_opaque=0 ;; esac

  [ $(( sa_files + sa_opaque )) -ge "$AUDIT_MIN_FILES" ] || return 0

  sa_cps=0
  [ -f "$REMINDERS/$sa_sid.checkpoints" ] && \
    sa_cps="$(wc -c < "$REMINDERS/$sa_sid.checkpoints" 2>/dev/null | tr -d ' ')"
  case "$sa_cps" in ''|*[!0-9]*) sa_cps=0 ;; esac

  # Which forges, if any, this session started -- stated as an observation, never as a
  # gate. A session that forged one thing can still have missed eight others, so the
  # record is written either way and the reviewer decides what the fact means.
  sa_since=0
  [ -f "$REMINDERS/$sa_sid.first" ] && sa_since="$(cat "$REMINDERS/$sa_sid.first" 2>/dev/null || echo 0)"
  case "$sa_since" in ''|*[!0-9]*) sa_since=0 ;; esac
  sa_forges=""
  if [ -f "$ROOT/ledger.jsonl" ]; then
    # -R plus `fromjson?` rather than a plain stream read: a half-written final line
    # makes plain jq abort with a parse error and lose every record before it.
    sa_forges="$(jq -R -r --argjson since "$sa_since" --arg proj "$project" '
      (fromjson? // empty)
      | select(type == "object")
      | select(.event == "start")
      | select(((.ts // 0) | if type == "number" then . else 0 end) >= $since)
      | select((.project // "") == $proj)
      | (.name // empty)' "$ROOT/ledger.jsonl" 2>/dev/null \
      | sort -u | tr '\n' ' ' | sed 's/  *$//')"
  fi
  [ -z "$sa_forges" ] && sa_forges="none"

  sa_shown="$sa_files"
  [ "$sa_shown" -gt "$sa_max" ] && sa_shown="$sa_max"

  sa_text="$(
    printf 'SESSION AUDIT. Written by the hook itself, from state on disk. The session\n'
    printf 'was not asked and did not consent; this record exists whether or not any\n'
    printf 'reminder was read.\n\n'
    printf '  session                 %s\n' "$sid"
    printf '  project                 %s\n' "$project"
    printf '  file edits counted      %s\n' "$sa_edits"
    printf '  distinct files touched  %s\n' "$sa_files"
    printf '  edits with no visible target  %s\n' "$sa_opaque"
    printf '  checkpoints fired       %s\n' "$sa_cps"
    printf '  forges started here     %s\n' "$sa_forges"
    if [ "$sa_opaque" -gt 0 ]; then
      printf '\nThe file list below is INCOMPLETE. %s of the %s edits were shell\n' "$sa_opaque" "$sa_edits"
      printf 'commands writing through a heredoc, a redirect or an inline interpreter,\n'
      printf 'and the hook payload for those carries a command string and no path. It\n'
      printf 'did not guess. Read the distinct-file count as a floor, never a total.\n'
    fi
    printf '\nFiles touched (%s of %s, as of this record):\n' "$sa_shown" "$sa_files"
    sort -u "$sa_paths_f" 2>/dev/null | grep '[^[:space:]]' | head -n "$sa_max" | sed 's/^/  /'
    if [ -f "$sa_paths_f" ]; then
      printf '\nLive list, which may have grown since:\n  %s\n' "$sa_paths_f"
    fi
    printf '\nFOR THE REVIEWER -- the question the session could not answer.\n'
    printf 'Read these edits as ONE set, from outside the session that made them.\n'
    printf 'Were two or more of them fixes of the SAME KIND? Repeated fixes of a kind\n'
    printf 'are a recurrence even when every single one felt self-contained at the time.\n'
    printf 'Asked per instance, mid-fix, the honest answer is always "no, I am just\n'
    printf 'fixing a bug", which is why this record is not a question put to the session.\n'
    printf 'If yes: the KIND is the skill candidate, not any one of the fixes.\n'
    printf 'If no: skillinsight decline %s\n' "PLACEHOLDER_HASH"
    printf '\nThis hook did not classify anything above. It counted edits and files.\n'
  )"

  # The decline hint has to name the record's own hash, so the hash cannot be taken
  # over the body. It is taken over sa_key above instead.
  [ -n "$sa_h" ] && sa_text="$(printf '%s' "$sa_text" | sed "s/PLACEHOLDER_HASH/$sa_h/")"

  sa_json="$(printf '%s' "$sa_text" | jq -Rs . 2>/dev/null)"
  [ -z "$sa_json" ] && return 0
  queue_record "session-audit" "$sa_key" "$sa_json" quiet
  return 0
}

session_audit

# ------------------------------------------------------------------ the text
# Never test emptiness with ${text//[[:space:]]/}. On bash 3.2, which is what
# /usr/bin/env bash finds on macOS, that substitution over a 60 KB transcript blob
# spins for minutes. A case glob answers the same question and returns at the first
# non-space character.
has_text() { case "$1" in *[![:space:]]*) return 0 ;; *) return 1 ;; esac; }
# last_assistant_message is documented as a string, but normalise defensively so a
# richer shape cannot silently yield nothing.
text="$(printf '%s' "$payload" | jq -r '
  def astext:
    if type == "string" then .
    elif type == "object" then (((.text // .content) // "") | astext)
    elif type == "array" then ([.[] | astext] | join("\n"))
    else "" end;
  (.last_assistant_message // "") | astext' 2>/dev/null)"

if ! has_text "$text"; then
  tp="$(printf '%s' "$payload" | jq -r '.transcript_path // empty' 2>/dev/null)"
  if [ -n "$tp" ] && [ -f "$tp" ]; then
    # tail -c leaves a truncated first line; `fromjson? // empty` drops it. The type
    # filter below is the one that keeps the plugin's own injected instruction text
    # out of the queue: it rides in `attachment` records, never in assistant text.
    # Records are joined with newlines, which in principle lets an unclosed block in
    # one record pair with a closer in the next. Real blocks are always complete
    # within a single text part, so this has no observed effect.
    text="$(tail -c "$TAIL_BYTES" "$tp" 2>/dev/null | jq -R -r '
      (fromjson? // empty)
      | select(.type == "assistant")
      | select((.isSidechain // false) | not)
      | .message.content[]?
      | select(.type == "text")
      | (.text // "")' 2>/dev/null)"
  fi
fi

has_text "$text" || exit 0

# ------------------------------------------------------------ the candidates
# Extraction runs in jq rather than awk or sed because the delimiters are multibyte
# (U+2605 star, U+2500 box drawing) and variable length, and jq's regex engine is the
# only one here that is reliably UTF-8 aware. Output is one candidate per line:
#   <source> TAB <normalised text, for hashing> TAB <original text as a JSON string>
candidates="$(jq -r -n --arg t "$text" '
  def normalise: gsub("\\s+"; " ") | sub("^ +"; "") | sub(" +$"; "") | sub("\\.$"; "");
  # The plugin injects its instruction verbatim, placeholder text and all. If a copy
  # of that instruction ever reaches assistant text, it is not an insight.
  def injected:
    test("key educational points"; "i")
    or test("In order to encourage learning"; "i")
    or test("brief educational explanations about implementation choices"; "i");
  def emit(src):
    (sub("^\\s+"; "") | sub("\\s+$"; "")) as $raw
    | ($raw | normalise) as $n
    | select(($n | length) >= 24 and (($n | injected) | not))
    | src + "\t" + $n + "\t" + ($raw | @json);
  ( [ $t | scan("(?:^|\\n)[ \\t]*(?:★ Skill candidate:|SKILL-CANDIDATE:)[ \\t]*([\\s\\S]*?)(?:\\n[ \\t]*\\n|\\z)") | .[0] ]
    | .[] | emit("marker") ),
  ( [ $t | scan("`?★ Insight[ ─]*`?\\n([\\s\\S]*?)\\n`?─{5,}`?") | .[0] ]
    | .[] | emit("star-insight") )
  ' 2>/dev/null)"

[ -z "$candidates" ] && exit 0

written=0
while IFS="$(printf '\t')" read -r src norm json; do
  [ -z "$src" ] && continue
  [ -z "$json" ] && continue
  [ "$written" -ge "$MAX_PER_TURN" ] && break
  queue_record "$src" "$norm" "$json"
  rc=$?
  # 2 means the queue file itself could not be appended to. Every later candidate this
  # turn would fail identically, so stop rather than spin -- and stop at 0, because a
  # capture never breaks the turn.
  [ "$rc" -eq 2 ] && exit 0
  [ "$rc" -eq 0 ] && written=$(( written + 1 ))
done <<CANDIDATES_EOF
$candidates
CANDIDATES_EOF

exit 0
