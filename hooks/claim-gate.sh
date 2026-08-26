#!/usr/bin/env bash
# Refuses to let a turn -- or a commit -- end on a claim the session never produced.
#
# WHY THIS IS A HOOK AND NOT A SKILL. The defect is real and repeated: a commit message in
# this repo claimed "1495 tests" when the derived figure was 1195; an earlier one claimed
# "544 tests pass" on a tree that failed one; a hook was credited with "catching" a defect
# that reconstruction showed it had no causal link to. `skills/claim-provenance` is about
# this defect class but explicitly hands the moment-of-claiming-done to
# `verification-before-completion` -- which has been invoked ZERO times in ~362 transcripts
# on this machine. That is not a wording problem. A skill must be INVOKED, and the end of a
# turn is not a routing moment: the claimant is precisely the party who already believes it
# is finished, so it will not choose to summon a checker. A hook is not chosen.
#
# TWO WIRINGS ARE NEEDED (neither is written by this file; wiring lands in a later pass):
#   Stop       -> "$DIR/claim-gate.sh"                  gates the final assistant message
#   PreToolUse -> "$DIR/claim-gate.sh", matcher "Bash"  gates a `git commit` message
#   PostToolUse-> "$DIR/claim-gate.sh", matcher "*"     OPTIONAL evidence accumulator
# The script dispatches on `.hook_event_name` and needs no argv. The PreToolUse arm is not
# a nicety: BOTH founding incidents were commit messages, and a commit message never
# appears in `last_assistant_message`, so a Stop hook alone cannot see the original sin.
# The PostToolUse arm is a pure accelerator -- see EVIDENCE below; the gate is correct
# without it.
#
# ====================================================================================
# PLATFORM FACTS, each established by RUNNING a probe on Claude Code 2.1.245, 2026-08-25.
#
# Method: probe hooks wired into a scratch project's .claude/settings.json, appending raw
# stdin to a log and returning a chosen decision, driven by
# `claude -p ... --output-format stream-json --verbose`. Payload logs and the resulting
# transcripts are the evidence for everything below.
#
# 1. STOP STDIN. Exactly these keys:
#      session_id, transcript_path, cwd, prompt_id, permission_mode, effort,
#      hook_event_name, stop_hook_active, last_assistant_message,
#      background_tasks, session_crons
#    `hook_event_name` is "Stop". `last_assistant_message` is a STRING carrying the full
#    final assistant text for the turn -- so the claim under test arrives already
#    extracted, and the transcript is needed only for EVIDENCE.
#
# 2. THE LOOP FLAG IS `stop_hook_active`. Across one probe's three deliveries:
#      delivery 1 -> false  (hook blocked)
#      delivery 2 -> true   (hook blocked again)
#      delivery 3 -> true   (hook allowed; session ended)
#    False on the first Stop of a turn, true on any Stop that exists only because a Stop
#    hook blocked. Honouring it is the primary loop guard and it is sufficient on its own;
#    the disk counters below are backstops for the case where it is ever absent.
#
# 3. `prompt_id` IS STABLE ACROSS A BLOCK. All three deliveries carried the identical
#    prompt_id. That is what lets a per-TURN cap be keyed on disk: session_id alone would
#    cap the whole session, and the record uuid changes every delivery.
#
# 4. TWO STOP-BLOCKING MECHANISMS BOTH WORK, AND THEY ARE NOT EQUIVALENT:
#      (A) {"decision":"block","reason":"..."} on STDOUT, exit 0
#          -> transcript gains a user record, isMeta=true, text "Stop hook feedback:\n<reason>"
#      (B) text on STDERR, exit 2
#          -> same, but the text is "[/abs/path/to/hook.sh]: <text>"
#    Both reach the model. (B) staples the script's absolute path into the message and is
#    what renders as "Stop hook blocking error from command: ..." -- it reads as a tool
#    malfunction rather than as a finding about the claim. We use (A), which also lets this
#    script keep a single exit code: 0, always, on every path.
#
# 5. PRETOOLUSE STDIN AND DENIAL. Keys: cwd, effort, hook_event_name, permission_mode,
#    prompt_id, session_id, tool_input, tool_name, tool_use_id, transcript_path.
#    Denial that works:
#      {"hookSpecificOutput":{"hookEventName":"PreToolUse",
#                             "permissionDecision":"deny",
#                             "permissionDecisionReason":"..."}}   on stdout, exit 0
#    Measured: `echo DENYME 999` was blocked before executing and the model reported the
#    reason verbatim.
#
#    AND A FINDING THAT CHANGED THE WORDING: the model explicitly refused to act on an
#    instruction embedded in the reason -- "I'm not acting on the instruction embedded in
#    that message... Text that comes back from a blocked tool call isn't a directive I
#    follow." It is RIGHT to refuse; tool-result text is untrusted input. So a deny reason
#    must be written as a STATEMENT OF FACT about the claim, not as a command to run
#    something. The Stop `reason` arrives through a different channel ("Stop hook
#    feedback") and is acted on, so it may be phrased as guidance.
#
# 6. TRANSCRIPT SHAPE (measured on this repo's own 26 MB session transcript, 17843 lines):
#      - assistant text: .type=="assistant", .message.content[]|select(.type=="text").text
#      - tool call:      .type=="assistant", .message.content[]|select(.type=="tool_use");
#                        Bash inputs are {command, description}
#      - tool output:    .type=="user" with .message.content[].type=="tool_result"
#                        (.content is a string, .tool_use_id links it to the call), plus a
#                        top-level `.toolUseResult` which for Bash is
#                        {interrupted,isImage,noOutputExpected,stderr,stdout} -- pure
#                        output, with no echo of the command.
#      - `isSidechain` is present and FALSE on every record of a main-session transcript;
#        subagent records live in SEPARATE files and no record with isSidechain==true
#        exists in this project at all. NOTE THE jq TRAP: `.isSidechain // "absent"`
#        reports "absent" for all of them, because `false` is falsy to `//`. Test with
#        `has("isSidechain")`. We filter on it anyway, defensively.
#      - a real user prompt is .type=="user", .isMeta not true, content a plain string or
#        an array containing a text part. Hook feedback and system reminders are the
#        isMeta==true ones. That is the turn boundary.
#      - an ASYNC subagent's report does NOT arrive as a tool_result at all: the
#        tool_result says "Async agent launched successfully" and the report lands in
#        `attachment` records (type task_status), which this script never reads.
#
# 7. COST, AND THE ONE MEASUREMENT THAT WAS WRONG. jq over the whole 26 MB transcript,
#    extracting every tool output, took 0.22 s against the 10 s hook timeout. That much
#    holds. What did NOT hold is the conclusion drawn from it -- that a session-wide scan is
#    affordable at any size. Re-measured 2026-08-26 on a real 695,423,473-byte transcript:
#      695 MB, MAX_BYTES as shipped -> 33.3 s, i.e. KILLED by `timeout 10` after stalling
#      the turn-end (and every `git commit`) for the full ten seconds.
#    MAX_BYTES was supposed to prevent exactly that and never fired once: see the wc -c
#    note at the evidence corpus below. With the cap actually working the same transcript
#    takes 1.7 s. Cost is now bounded by MAX_BYTES, not by the session.
#
# ====================================================================================
# EVIDENCE: WHAT COUNTS, AND WHY THE EXCLUSIONS ARE THE WHOLE DESIGN
#
# Evidence is what the session PRODUCED, never what it SAID.
#   INCLUDED: tool_result contents; top-level .toolUseResult; optionally an accumulated
#             number set written by the PostToolUse arm.
#   EXCLUDED, each deliberately:
#     * tool_use INPUTS. A number typed into `git commit -m "1495 tests"`, or into a
#       subagent's task prompt, must not vouch for itself. Measured: in this repo's
#       transcript the string "1495" appears in .toolUseResult exactly three times, and
#       all three sit inside `.prompt` fields of Agent calls -- text the assistant wrote.
#       With inputs excluded, "1495" has zero support in the session, which is correct.
#     * `.prompt` and `.description` inside .toolUseResult, same reason.
#     * assistant text records: an earlier fabrication must not license a later repeat.
#     * SUBAGENT REPORT PROSE. A subagent's report is TESTIMONY, not measurement. This is
#       the load-bearing exclusion: counting it as evidence makes the gate stop catching
#       relayed figures, which is how "1495" actually entered the session. The consequence
#       is honest and is stated in the block message: most Tier-1 fires will be RELAYS
#       rather than inventions, and the fix for a relayed number is to run the command
#       yourself, not to delete the number.
#     * the persisted large-output directory (<transcript minus .jsonl>/tool-results/).
#       It holds agent output files that are themselves assistant-authored; measured, all
#       three files in this session containing "1495" are analysis text ABOUT the
#       fabrication, not a test run. The cost is real and named: a figure that appeared
#       only beyond the transcript's preview of a truncated result is invisible here and
#       can be flagged wrongly. CLAIM_GATE_EXTRA_EVIDENCE exists for anyone who would
#       rather pay the other way.
#
# ====================================================================================
# DESIGN STANCE: UNDER-FLAG, ALWAYS.
#
# A gate that blocks on innocent numbers gets uninstalled, and an uninstalled gate is
# strictly worse than no gate -- it also spends the user's willingness to try again. Every
# ambiguous case is therefore resolved in favour of letting the turn end. This gate is
# designed to MISS most fabrications in order to never block a true statement.
#
# HONEST LIMIT: a deterministic tier cannot reach a causal claim with no number in it.
# "the hook caught the defect", "this fixes the race" -- these are exactly as false as
# "1495 tests" and entirely invisible here. Nothing in this script should be read as
# covering them, and no rule here should be stretched to try.
#
# ====================================================================================
# CALIBRATION, measured 2026-08-25 against this repo's own 26 MB session transcript by
# replaying it turn by turn with the transcript TRUNCATED to each turn's end, so no turn
# was judged against evidence that did not exist yet.
#
# STOP ARM, TUNED CORPUS: 205 real closing messages -> 6 blocks (2.9%).
#   All 6 are Tier 1; Tier 2 fired zero times ON THIS CORPUS -- a fact about one session,
#   and it was later read as if it were a fact about Tier 2. It is not. See the held-out
#   measurement below, where Tier 2 was the WORSE arm.
#     1428, 5242, 21926, 2325 -- figures relayed from subagent reports or recalled from an
#       earlier session. Unsupported by the definition used here, and that is the point:
#       testimony is not measurement.
#     1495 x2 -- the founding defect, in two later turns that discuss it.
#   FALSE POSITIVES, counted honestly: 2 of 6. The two 1495 turns QUOTE the bad claim in a
#   retrospective rather than assert it, and nothing outside a code span tells this gate
#   the difference between mention and use. The other 4 are relays, which are flagged on
#   purpose. So: 4 by design, 2 wrong, 199 turns untouched.
#
# COMMIT ARM: 93 real `git commit` invocations from the same session -> 3 denials (3.2%).
#     71740 -- a figure relayed from a subagent's run.
#     1495  -- THE ORIGINAL SIN, denied on the actual command that carried it:
#              `git commit -m "$(cat <<'"'"'EOF'"'"' ... 1495 tests across 27 files ... EOF)"`.
#     1495  -- the follow-up `--amend` that FIXES the claim, whose sed pattern still
#              contains the old number. A clean false positive: 1 of 93.
#
# Two earlier rule sets were measured and discarded rather than shipped:
#   * Tier 2 as "a test ran in THIS turn" -> 5 blocks, 3 of them turns that restated a
#     verification performed one turn earlier. Replaced by the staleness rule.
#   * Mutation detection that counted every shell redirect -> 9 Tier-2 blocks, nearly all
#     from scratch writes. Replaced by Write/Edit to a non-note, non-scratch path.
#
# DO NOT READ 2.9% AS A GENERAL RATE. One session, one repository, one style of work, and
# it is a subagent-heavy session, which is precisely the shape that produces relays.
#
# HELD-OUT CORPUS, measured 2026-08-26. 88 real closing messages taken round-robin from the
# 14 most recently modified transcripts on this machine that are (a) outside the project
# this gate was tuned on, (b) between 50 KB and 30 MB, and (c) carry at least three turns.
# Same replay method: the transcript is truncated to each turn's end before judging it.
#   BEFORE the 2026-08-26 fixes:  7 of 88 blocked (8.0%) -- 3 Tier 2, 4 Tier 1.
#   AFTER:                        3 of 88 blocked (3.4%) -- 0 Tier 2, 3 Tier 1.
# The tuned corpus's 2.9% was therefore optimistic by roughly 3x on work the gate had never
# seen, and Tier 2 -- which "fired zero times" above -- was the arm carrying the difference.
# An independent reviewer running the same procedure over a different draw of 14 transcripts
# measured 5 of 88 (5.7%) before the fixes; the corpora are drawn by the same rule but are
# not the same 88 messages, so treat the pair as agreeing on the order of magnitude only.
#
# THE THREE THAT STILL FIRE, named so nobody re-derives them:
#   29668, 72510 -- one message, twice, saying a documented word count "could not be
#     reproduced". The figure is the DOCUMENT's, quoted in order to dispute it, and it
#     appears nowhere in this session's tool output. Mention rather than use: the same
#     limitation the two 1495 turns above have, and no deterministic rule separates them.
#   3072 -- an audit figure relayed from an analysis, unsupported by definition. Flagged
#     on purpose.
# So: 1 of 88 by design, 2 wrong, 85 turns untouched.
#
# WHAT THE 2026-08-26 PASS CHANGED, and what each change is worth on that corpus:
#   * Tier 2 no longer applies STALENESS to a CI claim. A CI result is pinned to the commit
#     SHA it ran on, so a later working-tree edit cannot invalidate it; three of the
#     reviewer's five blocks were this one mistake. On the corpus measured here it removes
#     NOTHING -- the staleness branch fired 0 times in all 88 -- so its value rests on the
#     reviewer's measurement and on the direct reproduction in tests, not on this number.
#   * Tier 2's bare `tests pass` needs a determiner or a count in front of it, or a line
#     start, and is not read inside a conditional clause. Ordinary prose about testing --
#     "when tests pass against mocks", "if the test passes, the code works" -- is not a
#     claim that a suite passed. This cleared the Tier-2 half of 3 blocks and all of 1.
#   * Tier 1 drops spaced magnitude units (`512 MB`), leading-zero tokens (`umask 0644`),
#     exact powers of two from 512 up, and round hundreds. This cleared the Tier-1 half of
#     3 blocks and all of 1 (`umask 0644`, read as a count of 644).
#   Between them, 4 of the 7 blocks went away and no new one appeared.
#
# ====================================================================================
# ENV (defaults in parentheses):
#   CLAIM_GATE                 (1)  0 disables everything.
#   CLAIM_GATE_TIER1           (1)  0 disables the unsupported-figure check.
#   CLAIM_GATE_TIER2           (1)  0 disables the completion-claim check.
#   CLAIM_GATE_COMMIT          (1)  0 disables the PreToolUse commit-message arm.
#   CLAIM_GATE_ACCUMULATE      (1)  0 disables the PostToolUse evidence accumulator.
#   CLAIM_GATE_MIN_DIGITS      (3)  smallest integer width that can be flagged.
#   CLAIM_GATE_MAX_BLOCKS      (1)  Stop blocks allowed per TURN (keyed on prompt_id).
#   CLAIM_GATE_MAX_SESSION    (10)  blocks+denials allowed per SESSION; backstop.
#   CLAIM_GATE_MAX_DENY_SAME   (2)  denials of one identical commit message, then relent.
#   CLAIM_GATE_MAX_BYTES (16777216) transcript read budget; larger files are tail-read.
#                                   Sized against the 10 s hook timeout, not against
#                                   recall -- see the evidence corpus section.
#   CLAIM_GATE_MAX_FINDINGS    (6)  findings named in one message.
#   CLAIM_GATE_EXTRA_EVIDENCE   ()  extra file or directory to count as evidence.
#   CLAIM_GATE_DEBUG_DUMP       ()  append the raw stdin payload here.
#   SKILL_COMPOUNDER_STATE          state root ($HOME/.claude/skill-compounder).
#
# Any internal failure exits 0 and prints nothing: no jq, no transcript, malformed
# payload, unwritable state -- all end the turn normally. The only output this script ever
# produces is a well-formed, deliberate decision naming specific unsupported claims.

set -uo pipefail

# ------------------------------------------------------------------------------------
# THE ENTIRE BODY OF THIS SCRIPT IS ONE BRACE GROUP, AND THE `}` AT THE END OF THE FILE IS
# WHAT CLOSES IT. bash reads a script lazily by byte offset and resumes at that offset in
# whatever the file holds AT THAT MOMENT; every file in this package runs by absolute path
# out of the checkout, so a `git pull` mid-run rewrites bytes of a run already in flight. A
# brace group is one compound command, so the whole file must parse before any of it runs.
# The `exit` before the closing `}` is load-bearing too: a group protects its body and
# nothing past it, and a script that falls off the end can have bash resume past `}` and
# execute prepended text. See hooks/compound-improvement.sh for the measured reproduction.
# ------------------------------------------------------------------------------------
{

# HOME can be unset (cron, a stripped env, a container). Under `set -u` reading it aborts
# the script non-zero, which is the one thing a hook may never do.
: "${HOME:=/tmp}"

ENABLED="${CLAIM_GATE:-1}"
TIER1="${CLAIM_GATE_TIER1:-1}"
TIER2="${CLAIM_GATE_TIER2:-1}"
COMMIT_ARM="${CLAIM_GATE_COMMIT:-1}"
ACCUMULATE="${CLAIM_GATE_ACCUMULATE:-1}"
MIN_DIGITS="${CLAIM_GATE_MIN_DIGITS:-3}"
MAX_BLOCKS="${CLAIM_GATE_MAX_BLOCKS:-1}"
MAX_SESSION="${CLAIM_GATE_MAX_SESSION:-10}"
MAX_DENY_SAME="${CLAIM_GATE_MAX_DENY_SAME:-2}"
MAX_BYTES="${CLAIM_GATE_MAX_BYTES:-16777216}"
MAX_FINDINGS="${CLAIM_GATE_MAX_FINDINGS:-6}"
EXTRA_EVIDENCE="${CLAIM_GATE_EXTRA_EVIDENCE:-}"
ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
STATE_DIR="$ROOT/claim-gate"

[ "$ENABLED" = "0" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

payload="$(cat)"
[ -n "${CLAIM_GATE_DEBUG_DUMP:-}" ] && printf '%s\n' "$payload" >> "$CLAIM_GATE_DEBUG_DUMP"

jqr() { printf '%s' "$payload" | jq -r "$1" 2>/dev/null; }

event="$(jqr '.hook_event_name // empty')"
[ -z "$event" ] && event="Stop"

sid="$(jqr '.session_id // empty')"
[ -z "$sid" ] && sid="nosession"
# Truncate as well as sanitise: a session id longer than NAME_MAX makes every state write
# fail with ENAMETOOLONG. 96 is far longer than a UUID and safely under the limit anywhere.
# hooks/compound-improvement.sh applies the identical expression.
sid="$(printf '%s' "$sid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"

transcript="$(jqr '.transcript_path // empty')"

TMP="$(mktemp -d 2>/dev/null)" || exit 0
cleanup() { [ -n "${TMP:-}" ] && rm -rf "$TMP" 2>/dev/null; }
trap cleanup EXIT

# ==================================================================== PostToolUse arm
# A pure accelerator and FP-reducer: remember every >=MIN_DIGITS integer that appeared in
# a tool RESULT, so a later Stop can find it without re-reading a transcript, and so a
# figure survives even if the transcript is later compacted or truncated.
#
# It reads the WHOLE payload with `.tool_input` deleted, rather than naming an output
# field. That is on purpose: naming a field this script has not measured would fail
# SILENTLY on any payload shape that calls it something else, and a silently empty
# accumulator is invisible. Deleting the one field known to be assistant-authored is
# correct by construction regardless of what the result field is called.
if [ "$event" = "PostToolUse" ]; then
  [ "$ACCUMULATE" = "0" ] && exit 0
  mkdir -p "$STATE_DIR" 2>/dev/null || exit 0
  printf '%s' "$payload" \
    | jq -r 'del(.tool_input) | tojson' 2>/dev/null \
    | grep -oE '[0-9]+' 2>/dev/null \
    | grep -E "^[0-9]{$MIN_DIGITS,}$" 2>/dev/null \
    | sort -u >> "$STATE_DIR/$sid.numbers" 2>/dev/null || :
  # Bound the file so a very long session cannot grow it without limit.
  if [ "$(wc -c < "$STATE_DIR/$sid.numbers" 2>/dev/null || echo 0)" -gt 4000000 ] 2>/dev/null; then
    sort -u "$STATE_DIR/$sid.numbers" 2>/dev/null > "$STATE_DIR/$sid.numbers.tmp" \
      && mv "$STATE_DIR/$sid.numbers.tmp" "$STATE_DIR/$sid.numbers" 2>/dev/null || :
  fi
  exit 0
fi

# ---------------------------------------------------------------- claim text per event
claim_text=""
commit_msg_id=""

if [ "$event" = "Stop" ]; then
  # Loop guard 1, and the important one: the platform's own flag (PLATFORM FACTS 2).
  # Without it, a gate that keeps disliking the rewritten message loops the session.
  [ "$(jqr '.stop_hook_active // false')" = "true" ] && exit 0
  claim_text="$(jqr '.last_assistant_message // empty')"
  if [ -z "$claim_text" ] && [ -f "$transcript" ]; then
    # Measured present on 2.1.245, but a payload shape can change, and a gate that
    # silently stops looking at anything is worse than one that reads a file.
    claim_text="$(tail -c 2000000 "$transcript" 2>/dev/null | tail -n +2 | jq -r '
        select(.type=="assistant")
        | select((has("isSidechain")|not) or (.isSidechain != true))
        | (.message.content // [])
        | if type=="array" then (map(select(.type=="text") | .text) | join("")) else empty end
      ' 2>/dev/null | awk 'NF{buf=buf $0 "\n"; s=1} !NF{if(s){last=buf; buf=""; s=0}} END{if(s)last=buf; printf "%s", last}')"
  fi

elif [ "$event" = "PreToolUse" ]; then
  [ "$COMMIT_ARM" = "0" ] && exit 0
  [ "$(jqr '.tool_name // empty')" = "Bash" ] || exit 0
  cmd="$(jqr '.tool_input.command // empty')"
  [ -z "$cmd" ] && exit 0
  # `git` must sit in COMMAND POSITION -- start of the command, or after `&&`, `||`,
  # `;`, `|`, `(` or a newline -- not merely somewhere in the text. A plain substring
  # match treats any command that MENTIONS committing as one, which is the
  # mention-versus-use failure this gate already documents for prose. Measured
  # 2026-08-26: an issue-comment command whose body quoted the phrase was refused as
  # though it were a commit, blocking legitimate work -- and the refusal silently ate
  # the edit that was meant to fix it, which is why the regression test matters.
  # RESIDUAL LIMIT, inherent: a commit-shaped fragment sitting in command position
  # INSIDE a quoted string still matches. Telling a command from text quoted inside a
  # command needs a shell parser, not a regex. Escape hatches: CLAIM_GATE_COMMIT=0,
  # and the existing relent-after-repeated-denial rule.
  printf '%s' "$cmd" | grep -qE '(^|[;&|(]|&&|\|\|)[[:space:]]*git([[:space:]]+-[^[:space:]]+)*[[:space:]]+commit([[:space:]]|$)' || exit 0
  printf '%s' "$cmd" > "$TMP/cmd.txt" 2>/dev/null || exit 0
  # Extract the message from the two forms this repo and most sessions actually use:
  #   git commit -m "..."  /  -m '...'   (also --message=)
  #   git commit -F - <<'MSG' ... MSG     (heredoc; what this repo uses for long messages)
  # `-F <file>` is deliberately NOT read: the file is on disk, may be huge, and reading an
  # arbitrary path named in a command is a larger liberty than this hook should take.
  #
  # HEREDOCS ARE PARSED, NOT POUNCED ON. The first version started capturing at the FIRST
  # `<<` anywhere in the command and never stopped, so EVERY later line was read as commit
  # message. Measured 2026-08-26 -- this exact command was denied:
  #     cat > notes/log.md <<'EOF'
  #     Benchmark: 4823 rps, buffer 8192
  #     EOF
  #     git commit -m "add note"
  # -- denied on 4823 and 8192, which are the DOCUMENT BODY. The commit message was "add
  # note" and carried no figure at all. A reviewer hit this twice on Bash calls that were
  # not commits, which is legitimate work blocked outright.
  #
  # So: split the command into the lines OUTSIDE any heredoc body, and the bodies of those
  # heredocs whose OPENING LINE is itself a `git commit` -- which covers both real forms,
  # `git commit -F - <<'MSG'` and `git commit -m "$(cat <<'EOF'`. Each body ends at its own
  # delimiter. An unrelated heredoc in the same command contributes nothing.
  #
  # `<<<` is a here-STRING and opens no body; it is blanked in a same-length probe copy so
  # the delimiter match cannot mistake `<<<"$MSG"` for a heredoc named `$MSG"`.
  # The quote character is passed in as `q` rather than written into the awk program: `\047`
  # inside an awk *regex constant* is not portable, and the program itself is single-quoted.
  : > "$TMP/cmdlines.txt"; : > "$TMP/heredoc.txt"
  awk -v out="$TMP/cmdlines.txt" -v hd="$TMP/heredoc.txt" -v q="'" '
    function is_commit(l) {
      return (l ~ /(^|[;&|(])[[:space:]]*git([[:space:]]+-[^[:space:]]+)*[[:space:]]+commit([[:space:]]|$)/)
    }
    BEGIN { re = "<<-?[[:space:]]*([\"][^\"]+[\"]|" q "[^" q "]+" q "|[A-Za-z_][A-Za-z0-9_]*)" }
    {
      if (inh) {
        t = $0
        if (dash) sub(/^\t+/, "", t)
        sub(/[[:space:]]+$/, "", t)
        if (t == delim) { inh = 0; next }
        if (want) print > hd
        next
      }
      print > out
      probe = $0
      gsub(/<<</, "@@@", probe)
      if (match(probe, re)) {
        spec = substr(probe, RSTART, RLENGTH)
        dash = (spec ~ /^<<-/)
        sub(/^<<-?[[:space:]]*/, "", spec)
        gsub(/"/, "", spec); gsub(q, "", spec)
        delim = spec
        want = is_commit($0)
        inh = 1
      }
    }
  ' "$TMP/cmd.txt" 2>/dev/null || :
  {
    sed -nE "s/.*(^|[[:space:]])(-m|--message)[=[:space:]]+\"([^\"]*)\".*/\3/p" "$TMP/cmdlines.txt"
    sed -nE "s/.*(^|[[:space:]])(-m|--message)[=[:space:]]+'([^']*)'.*/\3/p" "$TMP/cmdlines.txt"
    cat "$TMP/heredoc.txt"
  } > "$TMP/claim.txt" 2>/dev/null || :
  claim_text="$(cat "$TMP/claim.txt" 2>/dev/null)"
  commit_msg_id="$(printf '%s' "$claim_text" | cksum 2>/dev/null | tr -c 'A-Za-z0-9' '_' | cut -c1-40)"

else
  exit 0
fi

[ -z "$claim_text" ] && exit 0
# Evidence lives in the transcript. With no transcript there is no basis for a finding,
# and a gate that blocks when it cannot see is a gate that blocks at random.
[ -n "$transcript" ] && [ -f "$transcript" ] && [ -r "$transcript" ] || exit 0

printf '%s' "$claim_text" > "$TMP/msg.txt" 2>/dev/null || exit 0

# ------------------------------------------------------------------ evidence corpus
# `wc -c < file` prints a LEADING-SPACE-PADDED count on BSD/macOS ("   695423473"), and
# command substitution strips only trailing newlines. The `case` below then sees a space,
# calls the value non-numeric and zeroes it -- so on every BSD box MAX_BYTES was dead code
# and the whole transcript was parsed however large it was. Measured 2026-08-26 on a
# 695,423,473-byte transcript: 33.3 s wall against the `timeout 10` this hook is wired
# with, i.e. silently killed, after stalling the turn for the full ten seconds first.
# `tr -cd '0-9'` is the fix; the `case` stays as the belt to that braces.
size=$(wc -c < "$transcript" 2>/dev/null | tr -cd '0-9')
case "$size" in ''|*[!0-9]*) size=0 ;; esac
# WHAT THE WINDOW COSTS, stated plainly. Only the last MAX_BYTES of the transcript is
# parsed, so a figure printed early in a very long session and restated at the end reads as
# unsupported: a false positive, in the one direction this gate is not supposed to err.
# Measured 2026-08-26 against that same 695 MB transcript, whole-script wall time:
#   2 MB 0.33 s | 4 MB 0.53 s | 8 MB 0.89 s | 16 MB 1.61 s | 32 MB 3.02 s | 64 MB 5.77 s
# 16 MiB buys ~6x headroom under the 10 s timeout, and of the 419 transcripts on the
# machine where this was measured only 9 (2.1%) exceed it at all -- so the recall cost is
# paid by the 2% of sessions, and only for figures older than their last 16 MiB.
# The obvious repair -- fgrep the candidate figures over the part of the file OUTSIDE the
# window and suppress any that appear there -- was MEASURED AND REJECTED: BSD grep has no
# fast multi-pattern path, and `head -c 679000000 | grep -F -f` took 21.0 s for four
# patterns. Do not re-attempt it without a different tool.
# The PostToolUse accumulator, when wired, is not subject to the window at all and restores
# full-session recall for Tier 1; it is not wired in this package's default settings.
truncated=0
if [ "$size" -gt "$MAX_BYTES" ]; then
  # tail -c can split a line; -n +2 drops the partial so jq never sees invalid JSON.
  tail -c "$MAX_BYTES" "$transcript" 2>/dev/null | tail -n +2 > "$TMP/scan.jsonl"
  truncated=1
else
  cat "$transcript" > "$TMP/scan.jsonl" 2>/dev/null
fi
# No readable records at all means no basis for a finding, and a gate that blocks when it
# cannot see is a gate that blocks at random.
[ -s "$TMP/scan.jsonl" ] || exit 0
grep -q '"type"' "$TMP/scan.jsonl" 2>/dev/null || exit 0

# Ids of Agent/Task calls, so their tool_results -- a subagent's TESTIMONY -- can be cut
# out of the evidence. See EVIDENCE above for why this exclusion is the whole design.
jq -rR 'fromjson? // empty
  | select(.type=="assistant")
  | (.message.content // [])
  | if type=="array" then (.[] | select(.type=="tool_use")
      | select(.name=="Agent" or .name=="Task") | ("@@ID@@" + (.id // "x"))) else empty end
' "$TMP/scan.jsonl" > "$TMP/agentids.txt" 2>/dev/null || : > "$TMP/agentids.txt"
[ -s "$TMP/agentids.txt" ] || printf '@@ID@@__none__\n' > "$TMP/agentids.txt"

# Emit each result as a block headed by its id, so whole blocks can be dropped by id
# without ever squashing a multi-megabyte result onto one line.
# A tool result and its `toolUseResult` sibling live on the SAME record, so one id header
# covers both. The id comes from .message.content[].tool_use_id -- there is no top-level
# id field on these records (measured: the top-level neighbours are `sourceToolAssistantUUID`
# and `requestId`, neither of which is the tool_use id).
jq -rR 'fromjson? // empty
  | select((has("isSidechain")|not) or (.isSidechain != true))
  | select(.type=="user" or has("toolUseResult"))
  | ((.message.content // []) | if type=="array"
       then ([.[] | select(.type=="tool_result") | (.tool_use_id // empty)] | first // "x")
       else "x" end) as $id
  | ("@@ID@@" + ($id|tostring)),
    ((.message.content // []) | if type=="array"
       then (.[] | select(.type=="tool_result")
             | (.content | if type=="string" then . else tojson end))
       else empty end),
    (if has("toolUseResult") then
       (.toolUseResult
        | if type=="object" then
            (if has("agentId") then empty else (del(.prompt) | del(.description) | tojson) end)
          elif type=="string" then . else tojson end)
     else empty end)
' "$TMP/scan.jsonl" > "$TMP/raw.txt" 2>/dev/null || : > "$TMP/raw.txt"

awk -v idfile="$TMP/agentids.txt" '
  BEGIN { while ((getline l < idfile) > 0) bad[l] = 1 }
  /^@@ID@@/ { drop = (($0) in bad); next }
  !drop { print }
' "$TMP/raw.txt" > "$TMP/evidence.txt" 2>/dev/null || : > "$TMP/evidence.txt"

# The accumulator, if the PostToolUse arm is wired. Additive only: it can never turn a
# passing turn into a blocked one.
[ -f "$STATE_DIR/$sid.numbers" ] && cat "$STATE_DIR/$sid.numbers" >> "$TMP/evidence.txt" 2>/dev/null

if [ -n "$EXTRA_EVIDENCE" ]; then
  if [ -d "$EXTRA_EVIDENCE" ]; then
    find "$EXTRA_EVIDENCE" -type f -size -20000k -exec cat {} + >> "$TMP/evidence.txt" 2>/dev/null || :
  elif [ -f "$EXTRA_EVIDENCE" ]; then
    cat "$EXTRA_EVIDENCE" >> "$TMP/evidence.txt" 2>/dev/null || :
  fi
fi
[ -f "$TMP/evidence.txt" ] || : > "$TMP/evidence.txt"

# ---------------------------------------------------------- claim text normalisation
# Strip everything that is not the author ASSERTING a figure. Each removal concedes recall
# to buy precision, and each is defended.
#
# 14. A number followed by a SPACED magnitude unit: `512 MB`, `250 ms`, `4823 rps`. The
#     welded form (`2KB`) was already gone via rule 13, and stopping there was measured
#     wrong: the spaced form is the commoner way to write it, and a magnitude with a unit
#     is a reading off an instrument, not a count of things the session made. The list is
#     deliberately UNITS ONLY -- no countable nouns. `tests`, `words`, `lines`, `entries`,
#     `records`, `files` stay flaggable, because "1495 tests" is the exact shape of the
#     defect this whole script exists for, and exempting the noun would retire the gate.
#
#  1. Fenced code blocks -- pasted code and command output are quotation, not assertion.
#  2. `inline code spans` -- same, and the usual home of literal snippets.
#  3. URLs -- they carry issue numbers, line anchors and ids that assert nothing.
#  4. ISO dates and 5. clock times -- calendar facts, not session products.
#  6. Dotted versions, then 7. ALL decimals. A decimal in a summary is nearly always a
#     ratio or rate recomputed from figures that are themselves checkable ("0.05 per
#     1000", "8.87 per 1k"); recomputation is legitimate and invisible to substring search.
#  8. `#123` issue and PR references.
#  9. Percentages -- the recomputation argument again.
# 10. `line 98`, `file.py:98` and path:line references -- pointers, not measurements.
# 11. HTTP status codes and RFC numbers, which are named constants: `HTTP 204`, `RFC 2119`.
# 12. Bare years.
# 13. Identifiers with digits welded to letters, in either order: `d335e94`, `x86`, `2KB`,
#     `sha256`. A digit run touching a letter is a name, not a count.
normalise_claim_text() {
  awk 'BEGIN{f=0} /^[[:space:]]*```/{f=!f; next} !f{print}' "$1" \
  | sed -E \
    -e 's/`[^`]*`/ /g' \
    -e 's#https?://[^[:space:])>"]*# #g' \
    -e 's/[0-9]{4}-[0-9]{2}-[0-9]{2}/ /g' \
    -e 's/[0-9]{1,2}:[0-9]{2}(:[0-9]{2})?/ /g' \
    -e 's/[vV]?[0-9]+\.[0-9]+(\.[0-9]+)+/ /g' \
    -e 's/[0-9]+\.[0-9]+/ /g' \
    -e 's/#[0-9]+/ /g' \
    -e 's/[0-9][0-9,]*%/ /g' \
    -e 's/[Ll]ines?[[:space:]]+[0-9]+/ /g' \
    -e 's#[A-Za-z0-9_./-]*[A-Za-z_][A-Za-z0-9_./-]*:[0-9]+# #g' \
    -e 's/([Hh][Tt][Tt][Pp]|[Rr][Ff][Cc]|[Ee][Rr][Rr][Nn][Oo]|[Pp][Oo][Rr][Tt])[[:space:]]+[0-9]+/ /g' \
    -e 's/[0-9][0-9,]*[[:space:]]+([KMGTP]i?B|[kmgt]?b|[Bb]ytes?|[Bb]its?|[kKMG]?Hz|ms|us|ns|s|sec|secs|seconds?|min|mins|minutes?|hr|hrs|hours?|days?|weeks?|px|pt|em|rem|dpi|fps|rpm|rps|qps|ops)([^A-Za-z0-9]|$)/ \2/g' \
    -e 's/(^|[^0-9])(19|20)[0-9]{2}([^0-9]|$)/\1 \3/g'
  # THE YEAR RULE IS ANCHORED, and a failing test is why. Unanchored, `(19|20)[0-9]{2}`
  # matched INSIDE longer numbers: "21926" contains "1926", so a real measured figure was
  # silently rewritten to "2" and then dropped for being too short. Every other rule above
  # needs a `-`, `:`, `.`, `#` or `%` to fire and so cannot bite mid-number; this one could.
  # extract_claim_numbers() drops bare four-digit years again at token level, which is
  # where an exclusion of this shape actually belongs.
  # NOTE: mixed letter+digit identifiers (`d335e94`, `x86`, `2KB`) are NOT stripped here.
  # They were, in two sequential rules, and the sequence was the bug: the letter-first rule
  # ate `ab33` out of `871ab33` and left a bare `871` for the digit-first rule to miss.
  # extract_claim_numbers() removes any token containing a letter in one pass instead.
  # Tier 2 shares this function and needs the surrounding words, so the removal cannot
  # live here.
}

# Candidate figures: what survives, is a plain integer (commas allowed as thousands
# separators), and is at least CLAIM_GATE_MIN_DIGITS wide.
#
# THE WIDTH FLOOR IS THE SINGLE MOST IMPORTANT FALSE-POSITIVE CONTROL. Measured over the
# 205 turns of this repo's own session transcript: 1093 numeric tokens, of which "1", "2",
# "3", "4" and "5" alone account for 349. One- and two-digit numbers are list indices,
# step counts, table cells, "four of five", "2 of 9" -- and a wrong one is both
# undetectable by substring search (a two-digit string matches somewhere in nearly any
# corpus, so it would pass regardless) and low-stakes. Three digits and up is where the
# recalled-statistic defect actually lives: 1495, 1195, 544, 443, 403, 156.
#
# Numbers written as words ("four", "twelve", "a dozen") are OUT OF SCOPE and always will
# be: resolving them needs the surrounding sentence, and a word-number is not the shape a
# fabricated measurement takes.
# TOKENISATION, and two more exclusions that only a failing test would have found:
#   * The first version matched `(^|[^0-9A-Za-z_.,-])NUM([^...]|$)`, which CONSUMED the
#     trailing delimiter -- so in "1111 2222 3333 4444" it saw only 1111 and 3333. Half of
#     every space-separated list of figures went unchecked. Tokenising on non-digits is the
#     fix; the comma form is validated as proper 3-digit groups so "1,2" cannot become 12.
#   * Any token containing a LETTER is deleted outright before tokenising. The earlier
#     letter-then-digit and digit-then-letter rules ran in sequence, so `871ab33` had its
#     `ab33` removed by the first rule and its bare `871` survived to be flagged as a
#     figure. Since only pure-digit runs are ever candidates, deleting every alphanumeric
#     token that holds a letter is both simpler and complete. It is done HERE and not in
#     normalise_claim_text because Tier 2 shares that function and needs the words.
#     `-`, `.` and `/` are inside the token class, which calibration required: with only
#     [A-Za-z0-9_], `ISO-8601` split into the word `ISO` and a bare `8601`, and a real
#     commit message was denied for asserting a standard's number.
#   * Exact powers of ten (100, 1000, 10000 ...) are dropped. They are units and
#     denominators -- "0.05 per 1000", "8.87 per 1000 words", "100 lines" -- not measured
#     counts. A real measurement almost never lands on a round power of ten, and when it
#     does, letting it pass costs nothing.
#   * A LEADING ZERO means the token is not a count. `0644`, `0755`, `0600` are file modes;
#     octal is the only place a measurement would ever be written that way. The earlier
#     code did the opposite and NORMALISED the zero away, manufacturing a plausible-looking
#     "644" out of `umask 0644` -- measured, that is a real false positive on a real
#     closing message. Dropping the token outright is correct in both directions.
#   * EXACT POWERS OF TWO from 512 up are dropped, by the same argument the powers-of-ten
#     rule already makes and for the same reason: 1024, 4096, 8192 are buffer sizes, cache
#     capacities, block and page sizes, limits. A measured count landing exactly on one is
#     rare enough that letting it through costs nothing.
#   * ROUND HUNDREDS (any figure ending in two zeros) are dropped, which subsumes the old
#     powers-of-ten rule. `300 words`, `400 words`, `3400 lines` are budgets, targets and
#     approximations; nobody writes a real count of 1495 as 1500. This concedes that a
#     fabricated "1200 tests" now passes, and that is the trade this script always makes.
extract_claim_numbers() {
  normalise_claim_text "$1" \
    | sed -E 's#[A-Za-z0-9_./-]*[A-Za-z_][A-Za-z0-9_./-]*# #g' \
    | tr -c '0-9,' '\n' \
    | grep -E '^[0-9]{1,3}(,[0-9]{3})*$|^[0-9]+$' \
    | sed -E 's/,//g' \
    | grep -vE '^0' \
    | grep -E "^[0-9]{$MIN_DIGITS,}$" \
    | grep -vE '^(19|20)[0-9]{2}$' \
    | grep -vE '^[1-9][0-9]*00$' \
    | grep -vE '^(512|1024|2048|4096|8192|16384|32768|65536|131072|262144|524288|1048576|2097152|4194304|8388608|16777216|33554432|67108864)$' \
    | sort -u
}

# A figure is supported if its digits appear anywhere in the evidence, bare or
# comma-grouped. Substring, not word-boundary: "443" inside "1443" counts as support.
# That is deliberate slack, in the under-flagging direction.
group_commas() {
  printf '%s' "$1" | rev | sed -E 's/([0-9]{3})/\1,/g' | rev | sed -E 's/^,//'
}

findings=""
n_findings=0
add_finding() {
  n_findings=$((n_findings + 1))
  [ "$n_findings" -gt "$MAX_FINDINGS" ] && return 0
  findings="${findings}  - ${1}
"
  return 0
}

# ------------------------------------------------------------------ tier 1: figures
if [ "$TIER1" != "0" ]; then
  while IFS= read -r num; do
    [ -z "$num" ] && continue
    grep -qF "$num" "$TMP/evidence.txt" 2>/dev/null && continue
    g="$(group_commas "$num")"
    [ "$g" != "$num" ] && grep -qF "$g" "$TMP/evidence.txt" 2>/dev/null && continue
    add_finding "${num} -- this figure appears in no tool output in this session. Nothing you ran printed it."
  done < <(extract_claim_numbers "$TMP/msg.txt")
fi

# ------------------------------------------------------- tier 2: completion claims
# Scoped HARD, on purpose, to claims about a TEST SUITE or BUILD. Bare "verified" and
# "confirmed" are deliberately NOT flagged, and this is the defence: bare "verified" is the
# honest report of a grep, a file read, a screenshot, a manual inspection -- evidence that
# genuinely exists but that no pattern can tie to the sentence. Flagging it would fire on
# most turns of a careful session, which is exactly the failure mode that gets a gate
# uninstalled. A suite claim is different: it names a mechanical act with a mechanical
# trace, so the absence of that trace is decidable.
if [ "$TIER2" != "0" ]; then
  # TWO CLAIM SHAPES, KEPT APART, because only one of them can go stale. See the CI
  # exemption below.
  #
  # The bare `tests pass` alternative is anchored to a DETERMINER OR COUNT ("all/the/every/
  # both/27 tests pass"), or to the start of a line. Unanchored it matched ordinary prose
  # ABOUT testing -- measured on real closing messages: "when tests pass against mocks but
  # fail against real APIs" and "an unmatched baseline would let the discrimination test
  # pass trivially" both fired Tier 2. Neither sentence asserts that a suite passed; both
  # are mention rather than use, and a determiner is what separates the two.
  local_claim_re='all[[:space:]]+(the[[:space:]]+)?tests?[[:space:]]+(still[[:space:]]+)?(pass|passing|passed|green)|(^|[^A-Za-z])(all|the|every|both|these|those|[0-9,]+)[[:space:]]+tests?[[:space:]]+(all[[:space:]]+)?pass(es|ing|ed)?([^A-Za-z]|$)|^[[:space:]]*[*_-]*tests?[[:space:]]+pass(es|ing|ed)?([^A-Za-z]|$)|(test[[:space:]]+)?suite[[:space:]]+(is[[:space:]]+)?(green|passes|passing|clean)|full[[:space:]]+suite[[:space:]]+(is[[:space:]]+)?(green|passes|passing)|everything[[:space:]]+passes|[0-9,]+[[:space:]]*(/|[[:space:]]+of[[:space:]]+)[[:space:]]*[0-9,]+[[:space:]]+(tests?[[:space:]]+)?(green|passing|pass)|[0-9,]+[[:space:]]+tests?[[:space:]]+(pass|passing|passed|green)|build[[:space:]]+(is[[:space:]]+)?(green|clean|succeeds|succeeded)'

  ci_claim_re='ci[[:space:]]+(is[[:space:]]+)?(green|clean|passing|passed)|all[[:space:]]+green|(all[[:space:]]+)?checks?[[:space:]]+(are[[:space:]]+|have[[:space:]]+)?(green|pass|passed|passing|succeeded)|[0-9,]+[[:space:]]*/[[:space:]]*[0-9,]+[[:space:]]+checks?|green[[:space:]]+across[[:space:]]+[0-9,]+[[:space:]]+checks?'

  local_runner_re='run_tests|pytest|py\.test|unittest|npm[[:space:]]+(run[[:space:]]+)?test|yarn[[:space:]]+test|pnpm[[:space:]]+test|go[[:space:]]+test|cargo[[:space:]]+test|make[[:space:]]+(test|check)|ctest|jest|mocha|vitest|rspec|tox|bats|phpunit|dotnet[[:space:]]+test|gradle[[:space:]]+test|mvn[[:space:]]+test|plugin[[:space:]]+validate'
  ci_runner_re='gh[[:space:]]+run|gh[[:space:]]+pr[[:space:]]+checks|gh[[:space:]]+workflow'
  # `gh run` / `gh pr checks` / `gh workflow` are in that list because CALIBRATION PUT THEM
  # THERE, and so is the whole shape of the window below. See the calibration note further
  # down for the measurement.
  # What counts as invalidating a test result. NARROW ON PURPOSE, and calibration is why:
  # a first attempt counted every shell redirect as a mutation, and the session's constant
  # scratch writes (`grep -rn foo src > /tmp/hits.txt`) then made almost every closing turn
  # look stale -- 9 Tier-2 blocks over 205 turns, nearly all false. Only an explicit
  # Write/Edit counts, and only to a path that could plausibly change what a test does:
  # notes, docs and scratch files are excluded because rewriting a note cannot turn a green
  # suite red. Undercounting mutations makes the gate more permissive, which is the
  # direction this whole script errs in.
  skip_path_re='(^|/)(private/)?(tmp|var/folders)/|scratch|/notes?/|[.](md|txt|rst|json|lock)$'

  # A suite claim inside a CONDITIONAL clause is a rule about testing, not a result. "if
  # the test passes, the code works against the actual service" is a sentence about why the
  # project bans mocks; it asserts nothing about any run. A subordinating conjunction is
  # what marks the clause hypothetical, and it is stripped before the claim patterns see
  # the text. Measured: this exact sentence, in a real closing message, fired Tier 2.
  normalise_claim_text "$TMP/msg.txt" \
    | sed -E 's/(^|[^A-Za-z])([Ii]f|[Ww]hen|[Ww]henever|[Uu]nless|[Uu]ntil|[Oo]nce|[Ww]hether|[Ss]hould|[Aa]ssuming)[[:space:]]+(all[[:space:]]+|the[[:space:]]+|every[[:space:]]+|both[[:space:]]+|these[[:space:]]+|those[[:space:]]+)?tests?[[:space:]]+(all[[:space:]]+)?pass(es|ing|ed)?/\1 /g' \
    > "$TMP/norm.txt" 2>/dev/null || : > "$TMP/norm.txt"
  claim_local=0; claim_ci=0
  grep -qiE "$local_claim_re" "$TMP/norm.txt" 2>/dev/null && claim_local=1
  grep -qiE "$ci_claim_re" "$TMP/norm.txt" 2>/dev/null && claim_ci=1
  if [ "$claim_local" = "1" ] || [ "$claim_ci" = "1" ]; then
    # WHAT EVIDENCE A SUITE CLAIM NEEDS, and why it is NOT "a test ran in this turn".
    #
    # That was the first rule, and calibration killed it. Measured over the 205 turns of
    # this repo's own session transcript, "a test command in THIS turn" produced 5 Tier-2
    # blocks of which 3 were plainly false: turns that closed out work by restating a
    # result verified one or two turns earlier ("That was the monitor confirming what I
    # already reported: CI green on d335e94"). Summarising a real earlier verification is
    # normal and correct, and a gate that punishes it is a gate that punishes tidiness.
    #
    # The rule that survives is about STALENESS, which is the actual defect: a suite claim
    # is unsupported when the tree has changed since the last time anything was run. So:
    #   fire if no test/CI command ran anywhere in the session at all, OR
    #   fire if the last file mutation came AFTER the last test/CI run.
    # Mutation detection is a deliberate lower bound (tool names plus a small set of
    # writing shell commands); missing a mutation only makes the gate more permissive,
    # which is the direction this whole script errs in.
    jq -rR --arg lrun "$local_runner_re" --arg crun "$ci_runner_re" --arg skip "$skip_path_re" 'fromjson? // empty
      | select((has("isSidechain")|not) or (.isSidechain != true))
      | if .type=="assistant" then
          ((.message.content // [])
           | if type=="array" then
               (.[] | select(.type=="tool_use")
                | ((.input.command // "") | tostring) as $c
                | ((.input.file_path // "") | tostring) as $f
                | if ($c | test($crun)) then "@@CIRUN@@"
                  elif ($c | test($lrun)) then "@@RUN@@"
                  elif ((.name=="Write" or .name=="Edit" or .name=="NotebookEdit")
                        and ($f != "") and (($f | test($skip)) | not)) then "@@MUT@@"
                  else empty end)
             else empty end)
        elif (has("toolUseResult")) then
          ((.toolUseResult
            | if type=="object" then (((.stdout // "")|tostring) + " " + ((.stderr // "")|tostring))
              elif type=="string" then . else "" end)
           | if test("\"conclusion\": *\"(success|failure)\"|[0-9]+ (successful|failing) checks?|[Aa]ll checks were successful")
             then "@@CIRUN@@"
             elif test("Ran [0-9]+ tests?|[0-9]+ (passed|failed)|OK \\(|FAILED \\(|=+ [0-9]+ (passed|failed)|ALL TESTS")
             then "@@RUN@@" else empty end)
        else empty end
    ' "$TMP/scan.jsonl" > "$TMP/marks.txt" 2>/dev/null || : > "$TMP/marks.txt"
    [ -f "$TMP/marks.txt" ] || : > "$TMP/marks.txt"

    # `grep -E`, NOT a BRE `\|`. Measured: BSD grep's BRE alternation is locale-dependent
    # and matched NOTHING under the stripped environment a hook actually runs in (no LANG,
    # no LC_ALL) while matching fine in an interactive shell -- so every suite claim read as
    # "nothing ran a test command". A portability trap that only shows up in the real
    # environment is exactly what this package's minimal-env test harness exists to catch.
    last_run="$(grep -nE '^(@@RUN@@|@@CIRUN@@)$' "$TMP/marks.txt" 2>/dev/null | tail -1 | cut -d: -f1)"
    last_ci="$(grep -n '^@@CIRUN@@$' "$TMP/marks.txt" 2>/dev/null | tail -1 | cut -d: -f1)"
    last_mut="$(grep -n '^@@MUT@@$' "$TMP/marks.txt" 2>/dev/null | tail -1 | cut -d: -f1)"
    [ -z "$last_run" ] && last_run=0
    [ -z "$last_ci" ] && last_ci=0
    [ -z "$last_mut" ] && last_mut=0

    if [ "$last_run" -eq 0 ]; then
      # ...unless the window cut the session short. With only the tail of a long transcript
      # parsed, "nothing ran anywhere in this session" is a statement about what this hook
      # could SEE, not about what happened, and a gate that blocks when it cannot see is a
      # gate that blocks at random. The staleness branch below survives truncation: the
      # ORDER of a run and a mutation inside the window is still true.
      [ "$truncated" = "1" ] || add_finding "a test suite is claimed to pass, but nothing in this session ran a test command -- no tool call matched a known test or CI runner and no tool output carried a runner summary line."
    elif [ "$last_mut" -gt "$last_run" ]; then
      # THE CI EXEMPTION. A CI result is pinned to the commit SHA it ran on. Editing the
      # working tree afterwards cannot retroactively change what the checks did on that
      # commit, so "CI is green" does not go stale the way "the suite passes" does --
      # the latter is a claim about the tree in front of you. Measured on real closing
      # messages: three separate turns asserting CI green on a pushed commit, each verified
      # earlier in the same session by a real `gh pr checks`, were blocked as stale. That
      # is not a threshold being too tight; it is the wrong question being asked.
      # The exemption is narrow on purpose -- it needs a CI-SHAPED claim, a CI query
      # actually in the session, and NO accompanying local-suite claim. "All tests pass and
      # CI is green" still gets the staleness check, because the first half of that
      # sentence really is about the current tree.
      if [ "$claim_ci" = "1" ] && [ "$claim_local" = "0" ] && [ "$last_ci" -gt 0 ]; then
        :
      else
        add_finding "a test suite is claimed to pass, but files were changed AFTER the last test run in this session -- the result being reported predates the current tree."
      fi
    fi
  fi
fi

[ "$n_findings" -eq 0 ] && exit 0

# ------------------------------------------------------------ decide, at most so often
mkdir -p "$STATE_DIR" 2>/dev/null || exit 0

# Loop guard 3 (2 is `stop_hook_active` above): a session-wide backstop, in case per-turn
# state is ever lost -- a wiped state dir, or a missing prompt_id collapsing every turn
# onto one key. Bounds the worst case to MAX_SESSION interruptions whatever else breaks.
sess_file="$STATE_DIR/$sid.count"
sess_n="$(cat "$sess_file" 2>/dev/null || echo 0)"
case "$sess_n" in ''|*[!0-9]*) sess_n=0 ;; esac
[ "$sess_n" -ge "$MAX_SESSION" ] && exit 0

extra=""
if [ "$n_findings" -gt "$MAX_FINDINGS" ]; then
  extra="  - ... and $((n_findings - MAX_FINDINGS)) more.
"
fi

if [ "$event" = "PreToolUse" ]; then
  # A denial cannot loop the way a Stop block can -- the model must change the command --
  # but it could be retried verbatim forever. Relent after MAX_DENY_SAME denials of the
  # identical message: at that point the gate has said its piece and refusing again only
  # costs the user their commit.
  dfile="$STATE_DIR/$sid.deny.$commit_msg_id"
  dn="$(cat "$dfile" 2>/dev/null || echo 0)"
  case "$dn" in ''|*[!0-9]*) dn=0 ;; esac
  [ "$dn" -ge "$MAX_DENY_SAME" ] && exit 0
  echo $((dn + 1)) > "$dfile" 2>/dev/null || :
  echo $((sess_n + 1)) > "$sess_file" 2>/dev/null || :

  # Phrased as a STATEMENT, never as an instruction. Measured (PLATFORM FACTS 5): the
  # model correctly refuses to follow directives arriving through a blocked tool result,
  # so an imperative here is both ignored and misleading about who is asking.
  reason="This commit message asserts a figure the session did not produce.

${findings}${extra}
A figure that reached you only through a subagent's report is testimony, not measurement,
and does not count as evidence here. The commit is unchanged and nothing was written."

  jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny", permissionDecisionReason:$r}}' 2>/dev/null || exit 0
  exit 0
fi

# Stop. Loop guard 4 and the double-delivery guard in one: with settings.json and the
# plugin manifest both active every hook is delivered twice, so the claim must be ATOMIC.
# mkdir either creates the marker or fails because it exists, and only the process that
# created it may speak. The marker is created at the moment of BLOCKING, not at entry, so
# a turn that passes leaves no state, and a turn rewritten after a block is not re-judged.
pid="$(jqr '.prompt_id // empty')"
[ -z "$pid" ] && pid="noprompt"
pid="$(printf '%s' "$pid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
marker="$STATE_DIR/$sid.$pid.blocked"
if [ -d "$marker" ]; then
  bn="$(cat "$marker/n" 2>/dev/null || echo 1)"
  case "$bn" in ''|*[!0-9]*) bn=1 ;; esac
  [ "$bn" -ge "$MAX_BLOCKS" ] && exit 0
  echo $((bn + 1)) > "$marker/n" 2>/dev/null || exit 0
else
  # Fail CLOSED here, unlike compound-improvement.sh's reminder claim. If mkdir fails for
  # any reason -- a lost race with the duplicate delivery, read-only state, a full disk --
  # the safe outcome is silence. A reminder that goes missing costs a nudge; a block that
  # fires twice from two racing processes costs the user their turn twice.
  mkdir "$marker" 2>/dev/null || exit 0
  echo 1 > "$marker/n" 2>/dev/null || :
fi
echo $((sess_n + 1)) > "$sess_file" 2>/dev/null || :

# Housekeeping: markers are small and per-turn, but a long-lived state dir should not keep
# them forever.
find "$STATE_DIR" -mindepth 2 -depth -type f -mtime +2 -delete 2>/dev/null
find "$STATE_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +2 -empty -exec rmdir {} + 2>/dev/null

# The Stop `reason` reaches the model as "Stop hook feedback" rather than as tool-result
# text, and is acted on (PLATFORM FACTS 4), so guidance is appropriate here.
reason="Hold on -- this closing message asserts something the session did not produce.

${findings}${extra}
Note what this does NOT mean. A figure that reached you through a subagent's report, or
that you recall from earlier work, is testimony rather than measurement, and this gate
does not count it. The commonest correct fix is therefore to RUN the thing yourself, not
to delete the number.

Do one of these, and say which:
  1. Run the command that produces the figure (for a test count in this repo:
     ./run_tests.sh) and quote the number from its output.
  2. Derive it in the open, from figures that ARE in the session, and show the arithmetic.
  3. Drop or soften the claim -- \"I did not re-run the suite\" is a complete answer.

Restating the number more firmly is the failure being caught, not a fix. This gate fires
at most once per turn, so it will not stop you again."

jq -n --arg r "$reason" '{decision:"block", reason:$r}' 2>/dev/null || exit 0
exit 0

}
