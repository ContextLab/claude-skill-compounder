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
#   INSIGHT_NOW / CI_NOW pin the clock, so the ISO-week filename is deterministic
#   INSIGHT_DEBUG_DUMP   append the raw stdin payload to this path for inspection
set -uo pipefail

TAIL_BYTES="${INSIGHT_TAIL_BYTES:-262144}"
MAX_PER_TURN="${INSIGHT_MAX_PER_TURN:-20}"
DIR="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}/insights"

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

hash_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 1
  elif command -v sha1sum >/dev/null 2>&1; then sha1sum
  else cksum
  fi | awk '{print $1}'
}

mkdir -p "$DIR" 2>/dev/null || exit 0
file="$DIR/$week.jsonl"
dupes="$DIR/.dedup-count"

written=0
while IFS="$(printf '\t')" read -r src norm json; do
  [ -z "$src" ] && continue
  [ -z "$json" ] && continue
  [ "$written" -ge "$MAX_PER_TURN" ] && break
  h="$(printf '%s' "$norm" | hash_of 2>/dev/null)"
  [ -z "$h" ] && continue
  # Dedup is against the whole queue, not just this week, and the record is appended
  # before the next candidate is hashed, so a repeat inside one turn is caught too.
  if grep -F -q "\"hash\":\"$h\"" "$DIR"/*.jsonl 2>/dev/null; then
    n=0; [ -f "$dupes" ] && n="$(cat "$dupes" 2>/dev/null || echo 0)"
    case "$n" in ''|*[!0-9]*) n=0 ;; esac
    printf '%s' "$(( n + 1 ))" > "$dupes" 2>/dev/null
    continue
  fi
  rec="$(jq -c -n --arg ts "$ts" --arg week "$week" --arg source "$src" \
    --arg session "$sid" --arg project "$project" --argjson text "$json" --arg hash "$h" \
    '{ts:$ts, week:$week, source:$source, session:$session, project:$project, text:$text, hash:$hash}' 2>/dev/null)" || continue
  [ -z "$rec" ] && continue
  printf '%s\n' "$rec" >> "$file" 2>/dev/null || exit 0
  written=$(( written + 1 ))
done <<CANDIDATES_EOF
$candidates
CANDIDATES_EOF

exit 0
