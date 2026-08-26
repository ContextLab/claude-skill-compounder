#!/usr/bin/env bash
# Refuses a tool call that has already failed the same way in earlier sessions, and says
# what worked instead.
#
# THE DEFECT, in the maintainer's words on issue #19: "the built-in skill for working with
# github isn't connected properly. but each fresh session tries to use that skill, fails,
# then retries with `gh` commands. it means every time github interactions are attempted,
# it takes several extra rounds of trial and error. this compounds to real wasted effort."
#
# WHY THIS IS A HOOK AND NOT A SKILL, AND WHY IT CARRIES NO MODEL. The knowledge that a
# particular call is broken here is not knowledge a fresh session has -- it is knowledge
# the MACHINE has, from having watched the same call die in three previous sessions. A
# skill would have to be invoked by the party that does not yet know it needs it. And a
# model-judged version would spend a call on every tool use to answer a question that is
# already decided by two integers on disk. So: no model, no judgement, no prose. A call
# either matches a signature that failed in >= REPEAT_MIN_SESSIONS distinct earlier
# sessions, or it does not.
#
# ====================================================================================
# THREE ARMS ON ONE SCRIPT. It dispatches on `.hook_event_name` and takes NO argv.
#
#   PostToolUseFailure -> LEARN.    Record a failure row keyed by signature.
#   PostToolUse        -> RECOVER.  Bind the first later success of the same tool to that
#                                   signature, so the store knows what worked.
#   PreToolUse         -> REFUSE.   Deny a call whose signature is already known broken,
#                                   naming the error and the agreed recovery.
#
# The three are inseparable. A gate that only refuses can only ever say "this failed
# before", which is worth almost nothing: the session already has to rediscover the
# workaround. The recovery arm is what turns the refusal into the answer.
#
# ====================================================================================
# THE SIGNATURE IS TWO PARTS, AND THAT IS FORCED BY THE PLATFORM.
#
#   sig = <callkey>-<errclass>
#
# The refusal arm runs BEFORE the call, so it cannot know how the call is about to fail.
# It can only compute the CALLKEY. The failure arm knows both. So the store records the
# full signature and the callkey separately; the refusal arm looks up every signature
# sharing this call's callkey and refuses on the one that has accumulated enough distinct
# sessions. A command that has failed two different ways in two sessions therefore has two
# signatures with one session each and is NOT refused -- which is the point of splitting
# it. A transient failure ("connection reset") and a structural one ("gh: command not
# found") are different facts about the same command, and only the structural one is worth
# refusing a third session over.
#
# CALLKEY NORMALISATION, in order, and each concession is deliberate:
#   Bash:
#     1. newlines and tabs -> spaces (a heredoc and its one-liner form are the same call).
#     2. '...' and "..." quoted literals -> <S>. The argument text is where the varying
#        part of an otherwise identical call lives: `gh issue view 19 --json body` and
#        `gh issue comment 19 --body "..."` differ only there for most of a session.
#     3. absolute paths -> <P>. A checkout that moved must not look like a new problem.
#     4. bare integers -> <N>, TWICE. Once is not enough: a regex that consumes its own
#        trailing delimiter sees only every other number in `1 2 3 4`, which is the exact
#        defect hooks/claim-gate.sh documents under TOKENISATION. Digits welded to letters
#        (`sha256`, `x86`, `v2`) are NOT masked -- those are names, not quantities.
#     5. whitespace collapsed, trimmed, capped at 400 characters.
#   any other tool (NOT REACHABLE under the current matcher -- see WHAT THE WIRING ADMITS):
#     `jq -Sc .tool_input` -- sorted keys, so a re-ordered payload is the same call -- then
#     rules 3, 4 and 5. Quoted literals are NOT masked here, because for a structured tool
#     the strings ARE the call (`{"file_path":"/x/y.py"}` masked to `{<S>}` would collapse
#     every Read onto one signature).
#
# ERRCLASS: the first TWO non-empty lines of `.error`, masked by rules 3 and 4, collapsed,
# capped at 200 characters. Not one line, and the deviation is on purpose: every failing
# Bash call's first line is literally `Exit code <N>` (measured 2026-08-26, see PLATFORM
# FACTS below), so a one-line class would collapse a missing binary, a syntax error and a
# permissions refusal into a single class and the split above would buy nothing.
#
# Both parts are hashed with `cksum` -- POSIX, present under the minimal PATH the test
# harness pins, and deterministic across machines. `md5`/`md5sum`/`shasum` are none of
# those three at once. A CRC-32 plus the byte length is not cryptographic and does not
# need to be: a collision costs one wrong refusal, which the session escapes by retrying.
#
# ====================================================================================
# WHY IT REFUSES ONCE PER SESSION PER SIGNATURE, AND NEVER TWICE.
#
# This gate exists to force a DECISION, not to make a call impossible. An unconditional
# block on a false positive is unrecoverable: the session cannot run the thing, cannot
# prove the gate wrong, and has nothing to do but stop. So the first attempt in a session
# is denied -- with the error and the recovery in the reason -- and a second identical
# attempt is allowed straight through. If the session has read the reason and still wants
# to run it, it is right and this store is stale. `skillrepeat forget <sig>` makes that
# permanent.
#
# ====================================================================================
# A SUCCESS OF THE SAME CALL IS NOT A RECOVERY -- IT IS PROOF THE FAILURE WAS TRANSIENT.
#
# The recovery arm binds the first later success of the same TOOL, because at that moment
# the tool is all it can cheaply match on. So it can bind the very call that just failed: a
# flaky `gh pr list` that dies on a reset connection and works on the retry records
# "gh pr list" as the recovery for "gh pr list", and the refusal then reads "what worked
# instead, in 2 of them: gh pr list". That is the gate naming the blocked call as its own
# cure, in exactly the transient case the two-part signature exists to separate out.
#
# A recovery whose `norm` equals the failing signature's `norm` is therefore a
# SELF-RECOVERY, and it does two things in the refusal arm. It is dropped from the
# plurality, so it can never be announced as the fix. And a signature with ANY
# self-recovery behind it is NEVER REFUSED AT ALL.
#
# The second is the stronger of the two available answers and it is the right one here.
# This gate refuses calls that are BROKEN; an earlier session running the identical call
# and getting it to work is an OBSERVATION that this one is not. Refusing while naming
# nothing would tell a session a call cannot work while the store itself holds the record
# of it working -- and this store's whole value is that it reports what was measured and
# never infers past it. The asymmetry settles what to do about the doubt: a wrong refusal
# traps a session, a missed refusal costs one repeat of a mistake.
#
# It is not a back door either. A self-recovery has to be OBSERVED: the identical call must
# actually have succeeded, in an earlier session, inside the recovery window. A structurally
# broken call cannot produce one.
#
# The comparison is against the norm the FAIL rows recorded, not against the norm of the
# call now being judged, so it stays correct even where two different calls collide onto one
# callkey.
#
# ====================================================================================
# BOOTSTRAP DEADLOCK, and what is done about it. A gate that learns from failures can
# learn to refuse the commands needed to inspect or undo it, and then the session is
# trapped with no way out that does not involve editing settings.json. Four independent
# guards, any one of which is enough:
#   1. Failures recorded by THIS session never count. The refusal needs
#      REPEAT_MIN_SESSIONS distinct EARLIER sessions, so nothing a session does to itself
#      can lock it out mid-flight.
#   2. Deny-once-per-session-per-signature, above. Every refusal has a next attempt.
#   3. A HEAD ALLOWLIST. If the first command-position word of a Bash command is one of
#      the navigation, inspection, git, jq or skill* commands below, the call is never
#      refused. `cd`, `ls`, `git`, `jq`, `cat`, `grep`, `find` are how a session diagnoses
#      anything at all, and this package's own CLIs are how it reads and clears this
#      store. Only the FIRST head is consulted, not every command position: allowing
#      `gh issue view 19 | jq .` because `jq` appears after a pipe would retire the gate
#      for the commonest shape of the exact case it was built for.
#   4. Any command mentioning `skillrepeat` anywhere is never refused, so a compound
#      command that clears the store cannot itself be blocked.
#
# WHAT THE WIRING ADMITS, AND WHAT THAT COSTS. All three events are wired with the matcher
# `Bash|Skill`, in BOTH install paths (skill_compounder/installer.py and hooks/hooks.json).
# A matcher is a REGEX over the tool name, not a substring -- measured 2026-08-26 on
# 2.1.246: of eight matchers on one event, `Bash`, `^Ba`, `Ba.*`, `Bash|mcp__.*`, `*` and
# `.*` each received a `Bash` call, while `Ba` and `as` received nothing. So this script is
# handed Bash and Skill calls and NOTHING ELSE: no Read, no Glob, no Grep, no MCP tool, no
# Write, no Edit.
#
# That bound is deliberate and it is a cost bound: this hook forks a process on every
# delivery, twice over with both wirings active, and the read tools are the high-frequency
# ones. What it costs is reach -- a Read or an MCP call that fails the same way in session
# after session is invisible here, and the store will never carry it.
# It is also the WHOLE of the protection those tools get. There is no in-script allowlist
# for them, and there must not be one: a `case "$tool" in Read|Glob|Grep)` arm under this
# matcher is a guard with no live path, which is precisely the defect
# skills/dead-guard-detection exists to catch. Widening the matcher and re-adding the arm
# are one decision, not two.
#
# ====================================================================================
# PLATFORM FACTS, measured on this machine 2026-08-26 (Claude Code 2.1.245, macOS 25.5.0)
# and recorded in docs/CLAUDE-CODE-BEHAVIOR.md rather than re-derived here:
#
# 1. A FAILED Bash call fires ONLY `PostToolUseFailure`. There is no `PostToolUse` for it.
#    A hook wired only to `PostToolUse` does not merely miss failures, it records each one
#    as a success.
# 2. `PostToolUseFailure` payload keys: cwd, duration_ms, error, hook_event_name,
#    is_interrupt, permission_mode, prompt_id, session_id, tool_input, tool_name,
#    tool_use_id, transcript_path. `.tool_response` is absent. `.error` for a failed Bash
#    reads e.g. "Exit code 1\nls: /x: No such file or directory".
# 3. `PostToolUse` additionally carries `tool_response`, and carries no `entrypoint`.
# 4. A PreToolUse deny is stdout
#      {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",
#       "permissionDecisionReason":"<text>"}}
#    with exit 0. The model treats that text as UNTRUSTED tool output and explicitly
#    refuses instructions embedded in it, so the reason below is written as a statement of
#    fact and never as a command to run something.
# 5. With settings.json and the plugin manifest both wired, EVERY hook event is delivered
#    TWICE. Every arm here therefore claims its event by `mkdir` of a directory named for
#    the payload's own `tool_use_id`, under the sanitised session id -- the identical
#    `tr -c 'A-Za-z0-9._-' '_' | cut -c1-96` expression every other script here uses.
#
# HONEST LIMIT, and it is the issue's own example: a failed `Skill` invocation is
# delivered to NO hook at all -- measured, `Unknown skill: <name>` produces neither event.
# So the gate cannot learn the "github skill isn't connected" failure from the skill call
# itself. What it CAN learn is everything downstream of it: the `gh` invocations that fail
# for a missing binary or a missing token, in session after session. Nothing here should
# be read as covering a broken Skill call directly, and no rule here should be stretched
# to try.
#
# ====================================================================================
# THE STORE is <state>/repeats/index.jsonl, APPEND-ONLY. Three row types:
#   {"t":"fail",   ts, sig, ck, ec, tool, norm, cmd, err, session, tuid}
#   {"t":"recover",ts, sig, ck, tool, norm, cmd, session, tuid}
#   {"t":"forget", ts, sig, session, why}          <- written only by bin/skillrepeat
# A tombstone suppresses rows recorded BEFORE its timestamp, and only those, so forgetting
# is re-armable: a signature that starts failing again after being forgotten accumulates
# fresh sessions and can refuse again. Nothing is ever rewritten or deleted. Rows that do
# not parse, or carry a `t` this script does not know, are skipped and not fatal --
# another tool's file landing here must not disable the gate.
#
# Each row is one `printf` of a single line onto an O_APPEND descriptor, which is why two
# hook processes racing cannot interleave a row; that is a property of the write size, not
# of a lock, and it is why rows are capped rather than allowed to grow.
#
# ====================================================================================
# ENV (defaults in parentheses):
#   SKILL_COMPOUNDER_REPEAT_GATE (1)  0 disables all three arms.
#   REPEAT_GATE_NOW               ()  this script's clock, epoch seconds. Its own, not
#                                     borrowed: pinning another script's does nothing here.
#   REPEAT_MIN_SESSIONS           (2) distinct EARLIER sessions needed before a refusal.
#   REPEAT_RECOVERY_WINDOW        (5) successful calls of any tool THIS HOOK IS WIRED FOR
#                                     -- `Bash|Skill`, and nothing else is delivered -- after
#                                     which an armed failure stops looking for its recovery.
#                                     The stream it counts is therefore far sparser than
#                                     "every tool call", and a recovery five Bash calls
#                                     later binds however many files were read in between.
#   REPEAT_GATE_MAX_BYTES   (4194304) store read budget; a larger store fails OPEN.
#                                     COST, MEASURED rather than assumed. THIS STANZA IS
#                                     THE ONLY PLACE THE GATE'S FIGURE IS WRITTEN DOWN.
#                                     bin/skillrepeat cites it and does not restate it: it
#                                     used to carry its own copy, a bare `0.31 s` against
#                                     the `0.32-0.47 s` written here, neither naming the
#                                     run it came from and both since remeasured.
#                                     It is measured in TWO shapes, because the store's
#                                     SIGNATURE DIVERSITY moves the figure and the cap does
#                                     not bound it: a store whose rows all share one
#                                     signature is the best case for the `.ck==$ck` filter,
#                                     and quoting only that understated the real cost.
#                                     Printed on this machine 2026-08-26 by TEN runs of
#                                       PYTHONPATH=$PWD python3 \
#                                         tests/test_repeat_gate.py CliCostTest -v
#                                     ONE whole PreToolUse invocation of this script --
#                                     fork, jq filter, jq query, the lot -- observed
#                                     min to max, not a mean:
#                                       15831 rows, every signature distinct, 4190377 B:
#                                                                       0.31-0.54 s
#                                       16446 rows, one signature,       4190440 B:
#                                                                       0.31-0.49 s
#                                     The two shapes cost the same here because parsing the
#                                     file dominates the query either way, which is the
#                                     reassuring result rather than the assumed one.
#                                     TEN RUNS AND NOT FIVE, because five gave 0.31-0.37
#                                     and the sixth run printed 0.54: a range quoted from
#                                     too few runs reads as precision the data does not
#                                     carry, and the next reader is the one who finds out.
#                                     These are wall times on a laptop doing other work;
#                                     what actually holds is the assertion, 5 s.
#                                     The gate is NOT locale-sensitive (bin/skillrepeat's
#                                     `list` is, and says so); that harness pins a minimal
#                                     environment, so these are C-locale figures and a
#                                     UTF-8 one measured the same. A hook is wired with a
#                                     10 s timeout and being killed there is silent, so
#                                     the cap is set for headroom, not for fit. Both
#                                     figures are printed on every test run, so neither
#                                     can quietly stop being true.
#   REPEAT_GATE_DEBUG_DUMP        ()  append the raw stdin payload here.
#   SKILL_COMPOUNDER_STATE        ()  state root ($HOME/.claude/skill-compounder).
#
# EVERY failure path exits 0 and prints nothing: no jq, no session id, no tool name, an
# unreadable or oversized store, a malformed payload, an unwritable state directory. The
# only output this script ever produces is one deliberate deny.
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

ENABLED="${SKILL_COMPOUNDER_REPEAT_GATE:-1}"
MIN_SESSIONS="${REPEAT_MIN_SESSIONS:-2}"
WINDOW="${REPEAT_RECOVERY_WINDOW:-5}"
MAX_BYTES="${REPEAT_GATE_MAX_BYTES:-4194304}"
ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
DIR="$ROOT/repeats"
STORE="$DIR/index.jsonl"

[ "$ENABLED" = "0" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

# Shape AND magnitude guards on every tunable. A non-numeric value from a typo'd export
# would otherwise reach an arithmetic test and print `[: integer expected` on the user's
# stderr, from a hook, for the rest of the session.
case "$MIN_SESSIONS" in ''|*[!0-9]*) MIN_SESSIONS=2 ;; esac
case "$WINDOW"       in ''|*[!0-9]*) WINDOW=5 ;; esac
case "$MAX_BYTES"    in ''|*[!0-9]*) MAX_BYTES=4194304 ;; esac
[ "$MIN_SESSIONS" -lt 1 ] && MIN_SESSIONS=1
[ "$WINDOW" -lt 1 ] && WINDOW=1

payload="$(cat)"
[ -n "${REPEAT_GATE_DEBUG_DUMP:-}" ] && printf '%s\n' "$payload" >> "$REPEAT_GATE_DEBUG_DUMP"

jqr() { printf '%s' "$payload" | jq -r "$1" 2>/dev/null; }

event="$(jqr '.hook_event_name // empty')"
case "$event" in
  PreToolUse|PostToolUse|PostToolUseFailure) ;;
  *) exit 0 ;;
esac

now="${REPEAT_GATE_NOW:-}"
case "$now" in ''|*[!0-9]*) now="$(date +%s 2>/dev/null)" ;; esac
case "$now" in ''|*[!0-9]*) exit 0 ;; esac

# A row with no session cannot be counted per-session, and the whole gate is a count of
# distinct sessions. Fail open rather than invent one.
sid="$(jqr '.session_id // empty')"
[ -z "$sid" ] && exit 0
sid="$(printf '%s' "$sid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"

tool="$(jqr '.tool_name // empty')"
[ -z "$tool" ] && exit 0

tuid="$(jqr '.tool_use_id // empty')"
[ -n "$tuid" ] && tuid="$(printf '%s' "$tuid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"

TMP="$(mktemp -d 2>/dev/null)" || exit 0
cleanup() { [ -n "${TMP:-}" ] && rm -rf "$TMP" 2>/dev/null; }
trap cleanup EXIT

# ------------------------------------------------------------------- normalisation
# Rules 3 and 4 from the header: absolute paths and bare integers. Shared by the call
# normaliser and the error classifier so the two can never drift apart.
#
# The integer rule runs TWICE. `(^|[^A-Za-z0-9_])[0-9]+([^A-Za-z0-9_]|$)` consumes its own
# trailing delimiter, so in `1 2 3 4` a single pass sees 1 and 3 only. Two passes catch
# the rest, because what the first pass left is no longer adjacent to an unconsumed
# neighbour. `<N>` and `<P>` contain no digits, so a placeholder can never be re-masked.
mask_common() {
  sed -E -e 's#(^|[^A-Za-z0-9_])/[A-Za-z0-9_.@+-]+(/[A-Za-z0-9_.@+-]+)*#\1<P>#g' \
    | sed -E -e 's/(^|[^A-Za-z0-9_])[0-9]+([^A-Za-z0-9_]|$)/\1<N>\2/g' \
             -e 's/(^|[^A-Za-z0-9_])[0-9]+([^A-Za-z0-9_]|$)/\1<N>\2/g'
}

squeeze() { sed -E -e 's/[[:space:]]+/ /g' -e 's/^ //' -e 's/ $//'; }

norm_bash() {
  printf '%s' "$1" \
    | tr '\n\t' '  ' \
    | sed -E -e "s/'[^']*'/<S>/g" -e 's/"[^"]*"/<S>/g' \
    | mask_common \
    | squeeze \
    | cut -c1-400
}

# UNREACHABLE ON THE CURRENT WIRING, and kept deliberately. The matcher admits Bash and
# Skill only, and a failed `Skill` call reaches no hook at all (HONEST LIMIT above), so no
# structured `fail` row can be written as things stand. It is kept because widening the
# matcher is ONE STRING IN TWO FILES -- `REPEAT_MATCHER` in skill_compounder/installer.py
# and the three matchers in hooks/hooks.json -- and this is what the gate would need the
# moment it is widened. The code is correct and tested against real payload shapes. What is
# NOT established is the route to it: `mcp__.*` reaching a real MCP tool is UNMEASURED, and
# no MCP tool failure has ever been observed arriving at a hook here. Proven code on an
# unproven route; do not read the tests below it as evidence the path is live.
norm_structured() {
  printf '%s' "$payload" \
    | jq -Sc '.tool_input // {}' 2>/dev/null \
    | mask_common \
    | squeeze \
    | cut -c1-400
}

# CRC-32 plus byte length. BSD and GNU `cksum` agree on both fields for stdin, and both
# print them whitespace-separated, which is why awk reads them rather than `cut`.
hashof() { printf '%s' "$1" | cksum 2>/dev/null | awk '{printf "%sx%s", $1, $2}'; }

# Populates: cmd (the raw call, capped, for display) and norm (the normalised call).
# Returns 1 when there is nothing to key on, which every caller treats as fail-open.
compute_call() {
  if [ "$tool" = "Bash" ]; then
    cmd="$(jqr '.tool_input.command // empty')"
    [ -z "$cmd" ] && return 1
    cmd="$(printf '%s' "$cmd" | cut -c1-500)"
    norm="$(norm_bash "$cmd")"
  else
    # Not reachable under `Bash|Skill`; see the note on norm_structured above.
    cmd="$(printf '%s' "$payload" | jq -c '.tool_input // {}' 2>/dev/null | cut -c1-500)"
    norm="$(norm_structured)"
  fi
  [ -z "$norm" ] && return 1
  ck="c$(hashof "$tool
$norm")"
  [ "$ck" = "c" ] && return 1
  return 0
}

# ------------------------------------------------------------------- double delivery
# Claim an event exactly once per session, whichever wiring delivered it. Fail OPEN, like
# hooks/compound-improvement.sh: mkdir failing because the marker exists is a duplicate and
# must be dropped, while mkdir failing for any other reason (read-only state, a full disk)
# must not silently stop the gate learning for the rest of the session. The two are told
# apart by testing the marker afterwards. A payload with no tool_use_id cannot be claimed
# at all, and is always acted on -- a duplicated row costs a wasted line, a dropped one
# costs the whole observation.
claim_once() {
  cdir="$DIR/claims/$sid"
  mkdir -p "$cdir" 2>/dev/null || return 0
  [ -z "$tuid" ] && return 0
  if mkdir "$cdir/$1-$tuid" 2>/dev/null; then return 0; fi
  [ -d "$cdir/$1-$tuid" ] && return 1
  return 0
}

# TWO SWEEPS, NOT ONE, AND THE SPLIT IS ABOUT WHICH ARM PAYS FOR WHICH TREE. This was a
# single function called from the LEARN arm and the REFUSE arm, which put the CLAIMS sweep
# on the PreToolUse deny path -- in front of a tool call the session is blocked on. The
# justification written here was that a refusal is rare. That is true and it is not an
# answer: the cost of a sweep scales with the TREE IT WALKS, not with how often it is
# started, and `claims/` is the big tree -- one marker per tool call, hundreds a session,
# kept two days -- so the rare refusal was the event paying the most for it. Each arm now
# sweeps only the tree it is a writer of.
#
# prune_claims: the claim markers, LEARN ARM ONLY. Nothing else can start this tree.
# claim_once() creates `claims/<sid>` from the LEARN arm and the RECOVER arm, but RECOVER
# claims only when a pending file already exists, and only a LEARN in the same session can
# have written one -- so every directory RECOVER can create was already swept on the way
# in, and the REFUSE arm never touches `claims/` at all.
#
# Markers are per tool call and there are hundreds a session; a week of them makes every
# mkdir walk a directory nobody reads. Two days is far longer than any session.
prune_claims() {
  find "$DIR/claims" -mindepth 2 -depth -type d -mtime +2 -exec rmdir {} + 2>/dev/null
  find "$DIR/claims" -mindepth 1 -maxdepth 1 -type d -mtime +2 -empty -exec rmdir {} + 2>/dev/null
  return 0
}

# prune_denied: the deny markers, from BOTH the LEARN and the REFUSE arms, and it has to be
# both. It used to be one call at the end of the LEARN arm -- but the REFUSE arm is the ONLY
# writer of `denied/<sid>`, so a machine that refuses without ever recording a failure of
# its own swept nothing at all, and these two lines were dead for exactly the sessions that
# created the work. Measured: an aged `denied/oldsid` survived a PreToolUse and a
# PostToolUse and was collected only by a PostToolUseFailure.
prune_denied() {
  find "$DIR/denied" -mindepth 2 -depth -type d -mtime +7 -exec rmdir {} + 2>/dev/null
  # ...and the `denied/<sid>` the markers lived in, which nothing else ever removes: one
  # empty directory per denied session, accumulating forever. This line CANNOT collect what
  # the line above just emptied, and that is not an oversight: removing a marker RESETS the
  # parent's mtime, so a directory emptied a microsecond ago is brand new to `-mtime +7` and
  # survives this pass. It is collected by a LATER pass -- a later failure OR a later
  # refusal, which is why the caller list above is two and not one -- once seven days have
  # gone by with nothing written into it. A bounded lag, not a leak -- and the age test is what makes it
  # safe, because a bare `-empty` sweep could rmdir the directory a concurrent PreToolUse
  # had just created and was about to write its deny marker into.
  find "$DIR/denied" -mindepth 1 -maxdepth 1 -type d -mtime +7 -empty -exec rmdir {} + 2>/dev/null
  return 0
}

# ==================================================================== arm 1: LEARN
if [ "$event" = "PostToolUseFailure" ]; then
  err_raw="$(jqr '.error // empty')"
  # An interrupt is the user changing their mind, not the tool being broken. Recording it
  # would teach the gate to refuse whatever was interrupted, in every later session.
  [ "$(jqr '.is_interrupt // false')" = "true" ] && exit 0
  [ -z "$err_raw" ] && exit 0
  compute_call || exit 0

  # First two non-empty lines: see ERRCLASS in the header for why not one.
  ecl="$(printf '%s' "$err_raw" | grep -v '^[[:space:]]*$' | head -2 | tr '\n' ' ' \
          | mask_common | squeeze | cut -c1-200)"
  [ -z "$ecl" ] && exit 0
  ec="e$(hashof "$ecl")"
  sig="$ck-$ec"

  # The verbatim head, for the refusal to quote back. Three lines is enough to carry the
  # actual message under the `Exit code N` wrapper and short enough to read in a deny.
  err_head="$(printf '%s' "$err_raw" | head -3 | cut -c1-400)"

  mkdir -p "$DIR/pending" 2>/dev/null || exit 0
  # Claimed HERE and not at entry: a claim taken before the action is really going to
  # happen burns the event for a path that then did nothing, which is the bug
  # hooks/session-review.sh shipped first.
  claim_once "f" || exit 0

  row="$(jq -nc --arg ts "$now" --arg sig "$sig" --arg ck "$ck" --arg ec "$ecl" \
    --arg tool "$tool" --arg norm "$norm" --arg cmd "$cmd" --arg err "$err_head" \
    --arg session "$sid" --arg tuid "$tuid" \
    '{t:"fail", ts:($ts|tonumber), sig:$sig, ck:$ck, ec:$ec, tool:$tool, norm:$norm,
      cmd:$cmd, err:$err, session:$session, tuid:$tuid}' 2>/dev/null)" || exit 0
  [ -z "$row" ] && exit 0
  printf '%s\n' "$row" >> "$STORE" 2>/dev/null || exit 0

  # Arm the recovery window for this session. US (0x1f) rather than a tab: tab is IFS
  # whitespace, so `read` collapses runs of it and an empty field silently shifts every
  # field after it (docs/DESIGN.md, shell portability traps).
  pf="$DIR/pending/$sid"
  printf '%s\037%s\037%s\037%s\n' "$sig" "$ck" "$tool" "$WINDOW" >> "$pf" 2>/dev/null || :
  # A session that fails hundreds of times must not grow this without bound; the oldest
  # armed failures are also the ones whose window has long since run out.
  if [ "$(wc -l < "$pf" 2>/dev/null | tr -cd '0-9')" -gt 200 ] 2>/dev/null; then
    tail -50 "$pf" > "$pf.tmp.$$" 2>/dev/null && mv "$pf.tmp.$$" "$pf" 2>/dev/null || :
  fi
  prune_claims
  prune_denied
  exit 0
fi

# ==================================================================== arm 2: RECOVER
# The first success of the SAME tool after a recorded failure, within a window of
# REPEAT_RECOVERY_WINDOW successful calls of any tool THIS HOOK IS WIRED FOR, is that
# signature's candidate recovery. The wiring is `Bash|Skill` (see WHAT THE WIRING ADMITS),
# so the window is spent by Bash and Skill successes and by nothing else: twenty Reads
# between the failure and the fix consume none of it. The window is what stops an unrelated command twenty steps later from being
# recorded as the fix; the plurality rule in the refusal arm is what stops a single wrong
# candidate from being announced as one. Neither is a guess about intent -- both are
# bounds on how much noise one session may contribute.
if [ "$event" = "PostToolUse" ]; then
  pf="$DIR/pending/$sid"
  [ -f "$pf" ] || exit 0
  compute_call || exit 0
  claim_once "s" || exit 0

  : > "$TMP/pending.new" 2>/dev/null || exit 0
  while IFS=$'\037' read -r psig pck ptool prem; do
    [ -z "${psig:-}" ] && continue
    case "${prem:-}" in ''|*[!0-9]*) continue ;; esac
    if [ "${ptool:-}" = "$tool" ] && [ "$prem" -gt 0 ]; then
      rrow="$(jq -nc --arg ts "$now" --arg sig "$psig" --arg ck "$pck" --arg tool "$tool" \
        --arg norm "$norm" --arg cmd "$cmd" --arg session "$sid" --arg tuid "$tuid" \
        '{t:"recover", ts:($ts|tonumber), sig:$sig, ck:$ck, tool:$tool, norm:$norm,
          cmd:$cmd, session:$session, tuid:$tuid}' 2>/dev/null)"
      [ -n "$rrow" ] && printf '%s\n' "$rrow" >> "$STORE" 2>/dev/null
      continue          # bound: one recovery per armed failure, then it is disarmed
    fi
    prem=$((prem - 1))
    [ "$prem" -le 0 ] && continue
    printf '%s\037%s\037%s\037%s\n' "$psig" "$pck" "$ptool" "$prem" >> "$TMP/pending.new"
  done < "$pf"

  # Rewrite next to the store, not across a filesystem: $TMP may be on another device and
  # a partial copy would leave a truncated pending file behind.
  if [ -s "$TMP/pending.new" ]; then
    cat "$TMP/pending.new" > "$pf.tmp.$$" 2>/dev/null && mv "$pf.tmp.$$" "$pf" 2>/dev/null || :
  else
    rm -f "$pf" 2>/dev/null || :
  fi
  exit 0
fi

# ==================================================================== arm 3: REFUSE
# Guard 3 from the header: the head allowlist. Only the FIRST command-position word is
# consulted, and leading `VAR=value` assignments are stepped over so `FOO=1 ls` reads as
# `ls`. Everything about this is a lower bound on refusing and an upper bound on trapping
# the session.
allowlisted_head() {
  h="$(printf '%s' "$1" | tr '\n\t' '  ' | squeeze)"
  # Step over leading `NAME=value` assignments. The name is validated rather than matched
  # loosely: a pattern like `[A-Za-z_]*=*` also matches `git commit -m x=y`, whose first
  # word is not an assignment at all, and stepping over it would drop `git` off the front
  # of a command this gate must never refuse.
  while :; do
    first="${h%% *}"
    case "$first" in
      *=*) ;;
      *) break ;;
    esac
    name="${first%%=*}"
    case "$name" in
      ''|*[!A-Za-z0-9_]*) break ;;
    esac
    [ "$h" = "$first" ] && break
    h="${h#* }"
  done
  h="${h%% *}"
  h="${h##*/}"
  case "$h" in
    cd|ls|pwd|echo|printf|cat|head|tail|less|wc|grep|egrep|fgrep|rg|find|which|command|type|env|export|git|jq|sed|awk|sort|uniq|diff|stat|file|date|true|:|source|.|skillrepeat|skillforge|skillinsight|skillreport|skillcontrib)
      return 0 ;;
  esac
  return 1
}

if [ "$tool" = "Bash" ]; then
  bcmd="$(jqr '.tool_input.command // empty')"
  [ -z "$bcmd" ] && exit 0
  # Guard 4: never refuse a command that is reaching for this store's own CLI.
  case "$bcmd" in *skillrepeat*) exit 0 ;; esac
  allowlisted_head "$bcmd" && exit 0
fi

[ -f "$STORE" ] && [ -r "$STORE" ] || exit 0
# `wc -c < file` prints a LEADING-SPACE-PADDED count on BSD, and a numeric `case` guard
# reads that space as non-numeric and zeroes the value -- which is how hooks/claim-gate.sh
# shipped a cap that was dead code on every macOS. `tr -cd '0-9'` is the fix and the `case`
# stays as the belt.
ssize="$(wc -c < "$STORE" 2>/dev/null | tr -cd '0-9')"
case "$ssize" in ''|*[!0-9]*) ssize=0 ;; esac
[ "$ssize" -gt "$MAX_BYTES" ] && exit 0
[ "$ssize" -eq 0 ] && exit 0

compute_call || exit 0

# Malformed and foreign lines are dropped here, once, so the query below can be written
# against clean records. `fromjson? // empty` swallows anything that is not an object.
jq -Rc 'fromjson? // empty | select(type=="object")' "$STORE" > "$TMP/rows.json" 2>/dev/null || exit 0
[ -s "$TMP/rows.json" ] || exit 0

# THE QUERY, and every clause in it is one of the rules above:
#   .session != $sid            -- guard 1: this session's own failures never count.
#   ts > tombstone              -- a `forget` suppresses what came before it, and only that.
#   distinct sessions >= $min   -- the refusal threshold.
#   recoveries grouped by norm  -- plurality: the candidate with the most distinct sessions
#                                  wins, and a TIE names nothing. A tie means the sessions
#                                  disagreed about the fix, and announcing one of them as
#                                  "what worked" would be an invention.
#   selfn == 0                  -- no earlier session recovered by re-running the IDENTICAL
#                                  call. One that did is proof the failure was transient,
#                                  and this whole hit is dropped.
#
# It rescans $rows once per signature, which is quadratic in general and flat here: the two
# filters above it cut the store to the rows sharing ONE callkey, and a callkey carries a
# handful of signatures at most. bin/skillrepeat cannot make that cut -- it reports the
# whole store -- so it groups instead, and must not be "fixed" to look like this.
jq -s -c --arg ck "$ck" --arg sid "$sid" --argjson min "$MIN_SESSIONS" '
  . as $rows
  | [ $rows[] | select(.t=="forget") ] as $tomb
  | [ $rows[] | select(.t=="fail" and .ck==$ck and .session!=$sid) ] as $f
  | [ ($f | map(.sig) | unique)[] as $s
      | (([ $tomb[] | select(.sig==$s) | (.ts // 0) ] | max) // -1) as $cut
      | [ $f[] | select(.sig==$s and ((.ts // 0) > $cut)) ] as $rr
      | [ $rows[] | select(.t=="recover" and .sig==$s and ((.ts // 0) > $cut)) ] as $rec
      | (($rr[-1].norm // "")) as $fn
      | [ $rec[] | select((.norm // "") == $fn) ] as $self
      | ([ [ $rec[] | select((.norm // "") != $fn) ] | group_by(.norm)[]
           | {cmd: (.[-1].cmd // .[-1].norm // ""), c: (map(.session) | unique | length)} ]
         | sort_by(-.c)) as $g
      | { sig: $s,
          selfn: ($self | map(.session) | unique | length),
          n: ($rr | map(.session) | unique | length),
          err: ($rr[-1].err // ""),
          norm: ($rr[-1].norm // ""),
          tool: ($rr[-1].tool // ""),
          fix: (if ($g|length) == 0 then ""
                elif ($g|length) == 1 then $g[0].cmd
                elif $g[0].c > $g[1].c then $g[0].cmd
                else "" end),
          fixn: (if ($g|length) == 0 then 0 else $g[0].c end),
          tie: (($g|length) > 1 and $g[0].c == $g[1].c) }
    ]
  | map(select(.n >= $min and .selfn == 0))
  | sort_by(-.n)
  | (.[0] // empty)
' "$TMP/rows.json" > "$TMP/hit.json" 2>/dev/null || exit 0
[ -s "$TMP/hit.json" ] || exit 0

hitr() { jq -r "$1 // empty" "$TMP/hit.json" 2>/dev/null; }
sig="$(hitr '.sig')"
[ -z "$sig" ] && exit 0
sig="$(printf '%s' "$sig" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"

# Deny once per session per signature, and fail CLOSED here -- the opposite of the learn
# arm's claim. If mkdir fails for any reason at all (a lost race with the duplicate
# delivery, read-only state, a full disk) the safe outcome is silence: a missed refusal
# costs one repeat of a mistake, while two refusals from two racing processes cost the
# session a call it was told twice it could not make.
mkdir -p "$DIR/denied/$sid" 2>/dev/null || exit 0
mkdir "$DIR/denied/$sid/$sig" 2>/dev/null || exit 0

# Swept HERE, and only once the deny is really going to happen. `denied/` and NOT `claims/`:
# this arm is the only writer of `denied/`, so no other arm can collect it, while `claims/`
# is written by arms that sweep it themselves and is the larger tree of the two. A deny path
# blocks a tool call the session is waiting on, so what it may sweep is decided by what it
# owes, not by how rarely it runs. The marker just created is safe from the sweep: both
# lines carry an age test and this one is seconds old. tests/test_repeat_gate.py has all
# three halves -- an aged `denied/` collected by a refusal, a live one that survives, and an
# aged `claims/` that a refusal leaves alone.
prune_denied

n="$(hitr '.n')"
err="$(hitr '.err')"
what="$(hitr '.norm')"
fix="$(hitr '.fix')"
fixn="$(hitr '.fixn')"
tie="$(hitr '.tie')"
case "$n" in ''|*[!0-9]*) n=0 ;; esac
[ "$n" -lt 1 ] && exit 0

# The error head is verbatim and usually multi-line ("Exit code 127" then the real
# message). Indenting its continuation lines to the width of the label is the difference
# between a refusal that reads as a report and one that reads as a crash.
err_disp="$(printf '%s' "$err" | sed -e '2,$s/^/             /')"

if [ -n "$fix" ]; then
  case "$fixn" in ''|*[!0-9]*) fixn=1 ;; esac
  fixline="what worked instead, in $fixn of them:
  $fix"
elif [ "$tie" = "true" ]; then
  fixline="No recovery is named: those sessions recorded different commands afterwards and
none of them is agreed."
else
  fixline="No recovery was ever recorded for this, so nothing here says what works."
fi

# Phrased as a STATEMENT OF FACT, never as an instruction. Measured (PLATFORM FACTS 4):
# the model treats text arriving through a blocked tool call as untrusted and explicitly
# refuses directives embedded in it, so an imperative here is both ignored and misleading
# about who is asking.
reason="This exact call has already failed in $n earlier sessions, the same way each time.

  the call:  $what
  the error: $err_disp

$fixline

Nothing ran and nothing was written. This gate declines a given call once per session, so
the same call attempted again in this session goes through -- if this store is stale, that
is the way past it. The full record, and the way to retire it permanently:

  skillrepeat show $sig
  skillrepeat forget $sig"

jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny", permissionDecisionReason:$r}}' 2>/dev/null || exit 0
exit 0

}
