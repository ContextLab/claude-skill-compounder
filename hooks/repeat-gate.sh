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
# ARM 3 IS OFF BY DEFAULT (`REPEAT_GATE_REFUSE=1` switches it on). Arms 1 and 2 stay on,
# so the store keeps learning and `skillrepeat`/`skillreport` keep reporting; what is off
# is the only arm that can block a call. THE REASON IS MEASURED, not a change of heart
# about the design. Issue #27, on the live store of 2026-09-02: 356 rows, 182 distinct
# signatures, 81 distinct sessions, and NO `repeats/denied/` directory at all -- the arm
# had never refused anything in 81 sessions. Ten signatures had reached
# REPEAT_MIN_SESSIONS, and driving this real hook against all ten denied NONE of them:
# every one has a head on the allowlist below, so the population that could ever trigger a
# refusal was empty. A synthetic non-allowlisted signature IS denied, so the machinery
# works; nothing real reaches it. An arm that has never fired cannot be judged by its
# false-positive rate, and the honest default for a refusal nobody has ever seen is off.
# WHAT WOULD TURN IT BACK ON: one non-allowlisted signature reaching the threshold for
# real. `skillrepeat list` and `skillreport` both now apply the head rules below before
# counting, so that number is the one they print -- which is how it would be noticed.
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
#     2. THE PROGRAM AFTER AN EVAL-LIKE FLAG IS KEPT, not masked. A quoted literal that
#        follows `-c`, `-e`, a short cluster ending in one of those (`perl -ne`), or
#        `--command` / `--eval` / `--execute` / `--expression`, is not an argument to the
#        command -- it IS the command. `python3 -c "import boto3"` and
#        `python3 -c "print(1+1)"` share every byte outside that literal, so masking it
#        left the two indistinguishable and the gate DENIED A CALL THAT HAD NEVER FAILED
#        while asserting that it had. Reproduced against the real hook before this rule
#        existed; tests/test_repeat_gate.py::CallkeyCollisionTest is that reproduction.
#        The kept text is wrapped as <C:...> and rules 3-5 still run inside it, so a
#        temp path or a loop bound inside the program does not split the key.
#     3. OTHER '...' and "..." quoted literals -> <S>. The argument text is where the
#        varying part of an otherwise identical call lives, and collapsing it is the
#        feature this gate was built for: `gh issue comment 19 --body "first draft"` and
#        `gh issue comment 4271 --body "quite another message"` are two sessions hitting
#        ONE broken call, and nothing recognises them as one if the body text is kept.
#     4. absolute paths -> <P>, KEEPING THE LAST SEGMENT: `/Users/x/proj/build.py`
#        becomes `<P>/build.py`. The two halves of a path answer different questions. The
#        directory is what legitimately varies between machines, checkouts and temp runs,
#        and a checkout that moved must not look like a new problem -- that is why the
#        rule exists at all. The BASENAME is usually the whole of what distinguishes two
#        calls: `python3 <P> --jobs <N>` collapsed `build.py` and `deploy.py` onto one
#        key, which is the same defect as 2 in a second costume.
#     5. bare integers -> <N>, TWICE. Once is not enough: a regex that consumes its own
#        trailing delimiter sees only every other number in `1 2 3 4`, which is the exact
#        defect hooks/claim-gate.sh documents under TOKENISATION. Digits welded to letters
#        (`sha256`, `x86`, `v2`) are NOT masked -- those are names, not quantities.
#     6. whitespace collapsed, trimmed, capped at 400 characters.
#   any other tool -- which under the current matcher means `Skill`, and it LEARNS here but
#   is never refused; see the stanza above norm_structured:
#     `jq -Sc .tool_input` -- sorted keys, so a re-ordered payload is the same call -- then
#     rules 4, 5 and 6. Quoted literals are NOT masked here, because for a structured tool
#     the strings ARE the call (`{"file_path":"/x/y.py"}` masked to `{<S>}` would collapse
#     every Read onto one signature).
#
# WHAT STILL COLLIDES, AND WHY THAT IS ACCEPTABLE. The callkey is a SHAPE and not a
# command, so more than one literal command still maps to one key. Each of these is pinned
# by a test in CallkeyCollisionTest as deliberate, so that a future reader finds it named
# rather than rediscovering it as a defect:
#   * A QUOTED PROGRAM IN A POSITIONAL SLOT. `ssh box "systemctl restart a"` and
#     `ssh box "rm -rf /tmp/x"` are both `ssh box <S>`; so are two different `awk '...'`
#     programs. Rule 2 keys off a FLAG, and finding the program slot of an arbitrary
#     command needs per-program knowledge this script has no business carrying. Bounded by
#     what it costs: one wrong refusal, which the next attempt in the session goes through.
#   * NESTED QUOTES INSIDE A KEPT PROGRAM. `python3 -c "print('hi')"` and
#     `python3 -c "print('bye')"` are both `python3 -c <C:print(<S>)>`, because rule 3 runs
#     over the kept text. Two programs identical outside their own string literals.
#   * BARE INTEGERS. `sleep 5` and `sleep 9` are one key, by rule 5 and on purpose.
#   * A URL's HOST, which rule 4 masks like any other directory:
#     `curl https://api.github.com/x` and `curl https://example.com/x` are one key.
#   * THE 400-CHARACTER CAP, rule 6. Two calls whose shapes agree for 400 characters and
#     diverge after are one key -- and rule 2 raised the stakes, because a KEPT program is
#     text that counts against the cap where a masked `<S>` was three characters. Verified
#     rather than assumed: two `python3 -c` programs sharing a 400-character prefix do
#     land on one key. A 400-character prefix match is a strong one, and the alternative
#     -- an unbounded key -- puts the store's size at the mercy of one pasted heredoc.
#   * THE CRC. Two distinct shapes whose `cksum` CRC-32 *and* byte length both collide.
# All of them fail in the same direction: a call is refused ONCE, is told what shape
# matched, and goes through on the next attempt. None can make a call unrunnable.
#
# THIS IS WHY THE REFUSAL DOES NOT SAY "this exact call". It used to, and that sentence was
# false for every shape above. The reason text now names what matched as a SHAPE and says
# which parts were masked before comparing, so a session reading it can judge a false
# positive instead of believing the store knows more than it does.
#
# ROWS WRITTEN BEFORE THIS NORMALISER simply stop matching: their callkeys were computed
# under the old rules, so they join nothing and refuse nothing. That is the safe direction
# -- a stale row over-refusing would be the unsafe one -- and they age out or are cleared
# with `skillrepeat forget`.
#
# ERRCLASS: the first TWO non-empty lines of `.error`, masked by rules 4 and 5 -- but with
# the WHOLE path masked to <P>, basename included, which is the one place the two masks
# deliberately differ. A path in a command is usually the thing being run; a path in an
# error message is the incidental subject of a class that is really "no such file", and
# `ls: /a/b: No such file` and `ls: /c/d/e: No such file` have to land in one class or a
# random temp basename gives every session its own. The error class does not need the
# discriminating power either: it is only ever consulted alongside a callkey that already
# has it (sig = <callkey>-<errclass>).
# Two lines and not one, and that deviation is on purpose too: every failing Bash call's
# first line is literally `Exit code <N>` (measured 2026-08-26, see PLATFORM FACTS below),
# so a one-line class would collapse a missing binary, a syntax error and a permissions
# refusal into a single class and the split above would buy nothing.
# Collapsed and capped at 200 characters.
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
#    with exit 0. Whether the model ACTS on that text is not settled: one probe recorded it
#    refusing an embedded instruction as untrusted tool output, a later one in this same
#    branch recorded 4/4 sessions running the exact command a reason named, and
#    docs/CLAUDE-CODE-BEHAVIOR.md reconciles them on COHERENCE rather than grammatical mood.
#    Neither arm may be quoted alone. The reason below is written as a statement of fact and
#    never as a command to run something, which is the rule that is safe under either.
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
#   REPEAT_GATE_REFUSE            (0) 1 switches ARM 3 on. Any other value is off. Off is
#                                     the default and the paragraph above is why. It gates
#                                     ONLY the refusal: the learn arm, the recovery arm and
#                                     `--norm-of`/`--eligible-of` are unaffected, so the
#                                     store keeps growing and the instruments keep reading
#                                     it while nothing is ever blocked.
#   REPEAT_GATE_NOW               ()  this script's clock, epoch seconds. Its own, not
#                                     borrowed: pinning another script's does nothing here.
#   REPEAT_MIN_SESSIONS           (2) distinct EARLIER sessions needed before a refusal.
#   REPEAT_RECOVERY_WINDOW        (5) successful calls of any tool THIS HOOK IS WIRED FOR
#                                     -- `Bash|Skill`, and nothing else is delivered -- after
#                                     which an armed failure stops looking for its recovery.
#                                     The stream it counts is therefore far sparser than
#                                     "every tool call", and a recovery five Bash calls
#                                     later binds however many files were read in between.
#   REPEAT_GATE_MAX_BYTES   (4194304) store read budget; a larger store fails OPEN. The
#                                     store is ROTATED at half this, by rename into
#                                     repeats/archive/, so that never happens: an
#                                     append-only store reaches this cap on its own and
#                                     then disables the gate in silence.
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
#                                     RE-MEASURED after the eval-flag and basename rules
#                                     landed in the normaliser, which added two more sed
#                                     processes per call: ten more runs of that same
#                                     command printed 0.31-0.31 s and 0.31-0.33 s. Both
#                                     sit INSIDE the range above, which is kept as the
#                                     wider of the two rather than narrowed to what these
#                                     ten happened to print -- narrowing it would be the
#                                     very trap the paragraph above is about.
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
#   REPEAT_GATE_STDERR            (0) 1 leaves this script's stderr connected, for `bash -x`
#                                     and for the test that proves the default is doing
#                                     something. Any other value closes it before the first
#                                     exec; the stanza under `set -uo pipefail` says why.
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

# STDERR IS CLOSED HERE, BEFORE THE FIRST EXEC, AND BY A BUILTIN. The header's promise
# that every failure path prints nothing was false in one band, and it was measured
# rather than reasoned about. `execve` charges the ENVIRONMENT against ARG_MAX along with
# the argument vector, and a hook is launched with whatever environment the session has
# grown. Just under the padding at which this script cannot be launched at all -- a band
# 200 bytes wide, 891800-891960 bytes of environment on macOS 25.6 with ARG_MAX 1 MB --
# it launches, `jq` execs (a 30-byte argv), and every `sed` in the normaliser cannot
# (each carries a 100-250-byte regex program on its argv). bash then writes
# `line NNN: /usr/bin/sed: Argument list too long` to fd 2 for each of them, up to seven
# lines, from a hook that the harness wired to be silent. The exit status stayed 0 at
# every padding and the store query ahead of any deny had already failed open, so no
# turn broke and no deny was lost; what leaked was noise on the user's terminal.
#
# Capping the command text cannot fix it and was tried on paper first: the command
# travels to `sed` through a pipe from a builtin `printf`, never on an argv, and a
# five-byte `gh pr view 7` died in the same band as a 600-byte one. What is on the argv
# is the regex program, which is the normaliser itself. So the fix is the belt: `exec`
# with a redirection and no command is a builtin, costs no process, and moves fd 2 for
# this shell and every child it forks -- the message a forked bash prints when ITS exec
# fails goes to the fd it inherited. A per-pipeline `2>/dev/null` would cover the seven
# lines found and not the eighth someone adds. Nothing here ever wrote to stderr on
# purpose, so nothing is lost; REPEAT_GATE_STDERR=1 leaves it connected for a developer
# running `bash -x` and for tests/test_repeat_gate.py, which drives the same band with
# the knob on and off at an identical environment size and requires the noise back on
# the first run -- a guard nobody has seen fire is the defect the whole package is
# about. `|| :` because a failed redirection makes `exec` return 1, not exit, and this
# script must reach its own `exit 0` whatever /dev/null is on the machine.
case "${REPEAT_GATE_STDERR:-0}" in 1) ;; *) exec 2>/dev/null || : ;; esac

ENABLED="${SKILL_COMPOUNDER_REPEAT_GATE:-1}"
# Exactly `1` switches the refuse arm on; a typo, an empty export or a `true` is OFF. The
# permissive spelling would be the wrong way round for a knob whose ON state can block a
# tool call the session is waiting on.
REFUSE="${REPEAT_GATE_REFUSE:-0}"
case "$REFUSE" in 1) ;; *) REFUSE=0 ;; esac
MIN_SESSIONS="${REPEAT_MIN_SESSIONS:-2}"
WINDOW="${REPEAT_RECOVERY_WINDOW:-5}"
MAX_BYTES="${REPEAT_GATE_MAX_BYTES:-4194304}"
ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
DIR="$ROOT/repeats"
STORE="$DIR/index.jsonl"

# THE OFF SWITCH STOPS THE GATE, NOT THE SHARED READ-ONLY DOORS. `--norm-of` and
# `--eligible-of` are pure functions of their stdin -- they read no store, write no row
# and deny nothing -- and other components call them: hooks/remind.sh asks `--norm-of`
# whether a command matches a reminder, and bin/skillreport and bin/skillrepeat ask
# `--eligible-of` what this gate's head rules say about a stored command. A user who turns
# this gate off must not silently turn off command matching in a DIFFERENT hook, or make
# two instruments start reporting a different number, with nothing on any surface to say
# why it changed.
case "${1:-}" in
  --norm-of|--eligible-of) ;;
  *) [ "$ENABLED" = "0" ] && exit 0 ;;
esac
command -v jq >/dev/null 2>&1 || exit 0

# Shape AND magnitude guards on every tunable. A non-numeric value from a typo'd export
# would otherwise reach an arithmetic test and print `[: integer expected` on the user's
# stderr, from a hook, for the rest of the session.
case "$MIN_SESSIONS" in ''|*[!0-9]*) MIN_SESSIONS=2 ;; esac
case "$WINDOW"       in ''|*[!0-9]*) WINDOW=5 ;; esac
case "$MAX_BYTES"    in ''|*[!0-9]*) MAX_BYTES=4194304 ;; esac
# DERIVED, not its own knob, so the two cannot drift apart: rotate at half the read
# budget and the live half always fits inside it.
ROTATE_BYTES=$(( MAX_BYTES / 2 ))
[ "$ROTATE_BYTES" -lt 1 ] && ROTATE_BYTES=1

# ROTATION, so the read budget above is never actually reached. The store is append-only
# and was measured growing 32,702 bytes a day (173 rows over 5.21 days) on the machine
# this was written on. At that rate it crosses REPEAT_GATE_MAX_BYTES in about four
# months, after which the read path fails OPEN and this gate silently stops matching
# history with nothing on any surface to say why. Failing open is right for a transient
# over-budget and wrong as a permanent terminal state nothing recovers from.
#
# Rotation is a RENAME, never a rewrite. A rewrite has to read the file and write it
# back, and a racing hook appending between those two steps loses its row outright.
# `mv` is one operation: a racing append either lands in the file being archived, where
# it is preserved, or recreates the live store, where it is kept. Nothing is deleted.
# The pid is in the name because two hooks crossing the threshold in the same second
# would otherwise archive over each other.
rotate_store() {
  [ -f "$STORE" ] || return 0
  rs="$(wc -c < "$STORE" 2>/dev/null | tr -cd '0-9')"
  case "$rs" in ''|*[!0-9]*) return 0 ;; esac
  [ "$rs" -lt "$ROTATE_BYTES" ] && return 0
  mkdir -p "$DIR/archive" 2>/dev/null || return 0
  mv "$STORE" "$DIR/archive/index-$now-$$.jsonl" 2>/dev/null || return 0
}
[ "$MIN_SESSIONS" -lt 1 ] && MIN_SESSIONS=1
[ "$WINDOW" -lt 1 ] && WINDOW=1

payload="$(cat)"
[ -n "${REPEAT_GATE_DEBUG_DUMP:-}" ] && printf '%s\n' "$payload" >> "$REPEAT_GATE_DEBUG_DUMP"

jqr() { printf '%s' "$payload" | jq -r "$1" 2>/dev/null; }

# ------------------------------------------------------------------ --norm-of
# THE NORMALISER, REACHABLE ON ITS OWN. Precedent: `--verdict-of` in
# hooks/session-review.sh, which exists so a test can drive a parser with real text.
# This one exists for a second reason as well: hooks/remind.sh matches a `commands`
# rule by BYTE EQUALITY against a signature, and a second implementation of these
# five masking rules would drift from this one invisibly -- the symptom is a reminder
# that quietly stops firing, with both copies looking correct.
#
# Usage: the raw command (Bash) or the tool_input JSON (any other tool) on STDIN,
#        the tool name as the argument. Prints the norm and exits. Touches no store.
#
# It is read from `payload` because that is what already holds stdin: the arm sits
# below the normalisers it calls, and moving those above the payload read would put
# 90 lines of reasoning about the five rules in front of the first thing the script
# does. The four guards between here and there are skipped rather than satisfied with
# invented values, so nothing downstream can read a session id or an event name this
# mode never had.
# TWO ARGV MODES, ONE VARIABLE. `ARGV_MODE` is what every guard below tests, so adding a
# third door means adding one `case` arm here and not hunting four `[ -z "$NORM_OF" ]`
# tests that each had to be found and changed by hand.
ARGV_MODE=""
ARGV_TOOL=""
case "${1:-}" in
  --norm-of)     ARGV_MODE="norm";     ARGV_TOOL="${2:-}"; [ -z "$ARGV_TOOL" ] && exit 2 ;;
  --eligible-of) ARGV_MODE="eligible"; ARGV_TOOL="${2:-Bash}" ;;
esac

if [ -z "$ARGV_MODE" ]; then
  event="$(jqr '.hook_event_name // empty')"
  case "$event" in
    PreToolUse|PostToolUse|PostToolUseFailure) ;;
    *) exit 0 ;;
  esac
  # ARM 3 IS OFF UNLESS REPEAT_GATE_REFUSE=1 -- see the stanza under THREE ARMS. Tested
  # HERE and not down at arm 3 so that a PreToolUse costs one fork and two jq reads when
  # the arm is off: no store read, no query, and no `denied/` marker written.
  if [ "$event" = "PreToolUse" ] && [ "$REFUSE" != "1" ]; then exit 0; fi
fi

if [ -z "$ARGV_MODE" ]; then
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
else
  tool="$ARGV_TOOL"
  # The arm dispatch below tests `$event`, and under `set -u` an unset one aborts the
  # script. An argv call has no event and must fall past arms 1 and 2 to reach the
  # functions the `--eligible-of` door needs, so it is set empty rather than left unbound.
  event=""
fi

# ------------------------------------------------------------------- normalisation
# Rule 5 from the header: bare integers, and it runs TWICE.
# `(^|[^A-Za-z0-9_])[0-9]+([^A-Za-z0-9_]|$)` consumes its own trailing delimiter, so in
# `1 2 3 4` a single pass sees 1 and 3 only. Two passes catch the rest, because what the
# first pass left is no longer adjacent to an unconsumed neighbour. `<N>`, `<P>` and `<C:`
# contain no digits, so a placeholder can never be re-masked.
mask_ints() {
  sed -E -e 's/(^|[^A-Za-z0-9_])[0-9]+([^A-Za-z0-9_]|$)/\1<N>\2/g' \
         -e 's/(^|[^A-Za-z0-9_])[0-9]+([^A-Za-z0-9_]|$)/\1<N>\2/g'
}

# THE ERROR CLASSIFIER's path rule: the WHOLE path, basename included, becomes <P>. The
# call normaliser's rule below keeps the basename and this one must not, and the header's
# ERRCLASS stanza is where that asymmetry is argued. In short: a basename in a command is
# usually what is being run, a basename in an error message is incidental, and the error
# class is only ever read alongside a callkey that already discriminates.
mask_common() {
  sed -E -e 's#(^|[^A-Za-z0-9_])/[A-Za-z0-9_.@+-]+(/[A-Za-z0-9_.@+-]+)*#\1<P>#g' \
    | mask_ints
}

# THE CALL NORMALISER's path rule, rule 4: the DIRECTORY becomes <P> and the last segment
# survives, so `/Users/a/proj/build.py` and `/Users/b/other/build.py` are one call while
# `.../deploy.py` is a different one. The trailing `(/[...]+)` is a separate group from the
# `*` before it precisely so a backreference can name the last segment; POSIX ERE and BSD
# sed agree on which segment lands in \3, and the tests read it back rather than assume it.
# A single-segment absolute path (`/tmp`, `/usr`) has no directory part that could vary
# between machines, so it is left alone rather than reduced to a bare `<P>`.
mask_call_paths() {
  sed -E -e 's#(^|[^A-Za-z0-9_])/[A-Za-z0-9_.@+-]+(/[A-Za-z0-9_.@+-]+)*(/[A-Za-z0-9_.@+-]+)#\1<P>\3#g'
}

# Rule 2: the flags after which a quoted literal is the COMMAND and not an argument. The
# short form is a CLUSTER ending in c, e or E so `perl -ne`, `sed -Ee` and `python3 -c`
# are all caught by one alternative. Over-matching here is the safe direction: it makes a
# key MORE specific, and a key that is too specific only ever costs a refusal that does not
# happen. Under-matching is what produced the defect this rule exists for.
EVAL_FLAGS='-[A-Za-z]*[ceE]|--command|--eval|--execute|--expression'

squeeze() { sed -E -e 's/[[:space:]]+/ /g' -e 's/^ //' -e 's/ $//'; }

# Every stage past the builtin `printf` is an exec carrying a regex on its argv, and
# under a near-ARG_MAX environment each of them can be the one that cannot launch;
# the `exec 2>/dev/null` at the top of the brace group is what keeps that silent.
norm_bash() {
  printf '%s' "$1" \
    | tr '\n\t' '  ' \
    | sed -E -e "s/(^|[[:space:]])($EVAL_FLAGS)[[:space:]]+'([^']*)'/\1\2 <C:\3>/g" \
             -e "s/(^|[[:space:]])($EVAL_FLAGS)[[:space:]]+\"([^\"]*)\"/\1\2 <C:\3>/g" \
    | sed -E -e "s/'[^']*'/<S>/g" -e 's/"[^"]*"/<S>/g' \
    | mask_call_paths \
    | mask_ints \
    | squeeze \
    | cut -c1-400
}

# REACHED BY EVERY `Skill` CALL, and this stanza said the opposite until 2026-08-27. The
# branch in `compute_call` is `if [ "$tool" = "Bash" ]`, and `Skill` is not `Bash`, so every
# Skill delivery on all three events lands here. A cold reviewer demonstrated a LIVE deny of
# a Skill call by seeding two `fail` rows under the callkey this function produces. The old
# text called the branch unreachable on the current wiring, in capitals, and a test in
# tests/test_repeat_gate.py REQUIRED that sentence to stay in this file -- the two together
# made a falsehood load-bearing, and the assertion would have passed unchanged if the
# behaviour it named had been removed, which is the one thing a test must never do. That
# assertion is now inverted, which is why the phrase itself does not appear here.
#
# WHAT WAS TRUE IN IT, and is narrower than it sounded: no `fail` row for a Skill call has
# been observed, because `Unknown skill: <name>` reaches no hook (HONEST LIMIT above). That
# measurement covers the only Skill failure mode provokable on demand, so it bounds what has
# been SEEN and not what can arrive. Any Skill failure that does deliver writes a row here.
#
# WHICH IS WHY THE REFUSE ARM IS BASH-ONLY. Both of that arm's escape hatches -- the
# `*skillrepeat*` guard and `allowlisted_head` -- sit inside `if [ "$tool" = "Bash" ]`, so a
# refused Skill call had no way past and no way to retire the signature. Learn broadly,
# refuse narrowly: a Skill failure is still recorded, because it is data `skillreport` wants,
# and it never denies. Refusing a `Skill` call would also block the one mechanism this whole
# package exists to promote, on a signature whose provenance is unestablished.
#
# An MCP route remains UNMEASURED: `mcp__.*` reaching a real MCP tool has never been
# observed here, and widening the matcher is ONE STRING IN TWO FILES -- `REPEAT_MATCHER` in
# skill_compounder/installer.py and the three matchers in hooks/hooks.json.
norm_structured() {
  printf '%s' "$payload" \
    | jq -Sc '.tool_input // {}' 2>/dev/null \
    | mask_call_paths \
    | mask_ints \
    | squeeze \
    | cut -c1-400
}

# CRC-32 plus byte length. BSD and GNU `cksum` agree on both fields for stdin, and both
# print them whitespace-separated, which is why awk reads them rather than `cut`.
hashof() { printf '%s' "$1" | cksum 2>/dev/null | awk '{printf "%sx%s", $1, $2}'; }

# The `--norm-of` arm, below every function it uses and above every line that writes.
# The 500-character cap is `compute_call`'s, applied here for the same reason: the
# caller must get the signature this gate WOULD have computed, cap included, or byte
# equality against a stored one is a coin flip on long commands.
if [ "$ARGV_MODE" = "norm" ]; then
  if [ "$tool" = "Bash" ]; then
    printf '%s\n' "$(norm_bash "$(printf '%s' "$payload" | cut -c1-500)")"
  else
    # A structured tool's signature is computed from `.tool_input`, so stdin is that
    # object and it is wrapped into the shape norm_structured reads. Invalid JSON
    # leaves `payload` empty, which prints nothing -- the same silence every other
    # unusable input in this script produces.
    payload="$(printf '%s' "$payload" | jq -c '{tool_input: .}' 2>/dev/null)"
    [ -n "$payload" ] && printf '%s\n' "$(norm_structured)"
  fi
  exit 0
fi

# Populates: cmd (the raw call, capped, for display) and norm (the normalised call).
# Returns 1 when there is nothing to key on, which every caller treats as fail-open.
compute_call() {
  if [ "$tool" = "Bash" ]; then
    cmd="$(jqr '.tool_input.command // empty')"
    [ -z "$cmd" ] && return 1
    cmd="$(printf '%s' "$cmd" | cut -c1-500)"
    norm="$(norm_bash "$cmd")"
  else
    # Reached by every `Skill` call; see the stanza above norm_structured.
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
  rotate_store
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

# A SECOND ALLOWLIST, AND IT IS A DIFFERENT ARGUMENT FROM THE ONE ABOVE. `allowlisted_head`
# holds commands whose failure is nobody's bug -- a `cd` into a path that is not there. This
# one holds TEST AND BUILD RUNNERS, whose failure is the POINT: a red suite means the code
# is broken, not that the call is, and running it again is exactly what the next session
# must do. Two sessions of a failing `./run_tests.sh` is the commonest shape there is of
# "failed the same way twice", and refusing the third session's first run lands squarely on
# the loop the user's own CLAUDE.md mandates -- "when tests fail repeatedly ... fix the code
# so the existing tests succeed". Found by a cold reviewer on 2026-08-27, driving the real
# hook: `./run_tests.sh` red in two sessions denied the third, and `python3 -m pytest tests/`
# reproduced it identically.
#
# THE LIST IS A LOWER BOUND AND CANNOT BE OTHERWISE. There is no way to tell a test runner
# from any other command by looking at a string, so a project's own wrapper under a name not
# below is still refusable. That fails in the tolerated direction -- one refusal, once per
# session, which the next attempt goes through -- and the self-recovery rule closes it for
# good the moment the suite goes green: the identical call succeeding in an earlier session
# disarms the signature permanently. Both halves matter; neither alone would be enough.
#
# Matched on the HEAD as `allowlisted_head` leaves it -- assignments stepped over, directory
# stripped -- so `./run_tests.sh`, `/abs/path/run_tests.sh` and `CI=1 pytest` all reach here
# as their bare basename. The `*test*`/`*spec*` script patterns are what catch a repository's
# own runner without naming it.
runner_head() {
  h="$(printf '%s' "$1" | tr '\n\t' '  ' | squeeze)"
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
  # Runners whose whole purpose is to run a suite or a build: unconditional.
  case "$h" in
    pytest|tox|nox|nose2|jest|mocha|vitest|karma|ava|rspec|minitest|phpunit)
      return 0 ;;
    make|cmake|ctest|ninja|bazel|buck|gradle|gradlew|mvn|ant|sbt|rake|just|dune)
      return 0 ;;
    *test*|*spec*|*check*|*lint*|*build*)
      return 0 ;;
  esac
  # MULTI-PURPOSE DRIVERS ARE GATED ON THEIR SUBCOMMAND, and that distinction is the point
  # rather than fussiness. `npm test` failing means the code is broken; `npm install`
  # failing repeatedly is a broken call and is EXACTLY what this gate exists to catch.
  # Allowlisting the whole driver would trade away the gate's best cases for its worst one.
  sub="${1#*"$h"}"; sub="${sub# }"; sub="${sub%% *}"
  case "$h" in
    npm|pnpm|yarn|bun|npx|deno)
      case "$sub" in test|run|build|lint|check|start) return 0 ;; esac ;;
    go)
      case "$sub" in test|build|vet) return 0 ;; esac ;;
    cargo)
      case "$sub" in test|build|check|clippy|bench) return 0 ;; esac ;;
    dotnet|swift|stack|mix|rebar3|lein)
      case "$sub" in test|build) return 0 ;; esac ;;
  esac
  # `python -m pytest` / `python3 -m unittest` and the like: the runner is the MODULE, and
  # the head is only an interpreter. Read the `-m` argument rather than the first word.
  case "$h" in
    python|python2|python3|python3.*|ruby|node|perl|php)
      case " $1 " in
        *" -m "*)
          m="${1#* -m }"; m="${m%% *}"; m="${m%%.*}"
          case "$m" in
            pytest|unittest|nose2|tox|nox|compileall|build|pip) return 0 ;;
          esac ;;
      esac ;;
  esac
  return 1
}

# ------------------------------------------------------------------ --eligible-of
# THE HEAD EXEMPTIONS, REACHABLE ON THEIR OWN, and for the same reason `--norm-of` is.
# bin/skillreport and bin/skillrepeat each report what this gate WOULD refuse, and each
# answered it from the session count alone, with no head exemption applied at all. On the
# live store that made both of them print ten signatures the real hook denies none of
# (issue #27). A second copy of the two lists above, kept in a CLI, would drift from these
# invisibly, and the symptom is precisely that: a number nobody can act on.
#
# Usage: the raw command on STDIN, the tool name as the argument (default Bash). Prints
#        ONE token and exits 0. It reads no store, writes nothing and denies nothing, and
#        it answers the same whether or not REPEAT_GATE_REFUSE is set -- the question is
#        "do the head rules exempt this call", not "is the gate refusing today". A caller
#        that wants the second question has to ask it separately, which is right: the two
#        have different answers and folding them would hide the first.
#
#   eligible          nothing here exempts it; the session count alone would decide.
#   exempt-tool       not a Bash call, and the refuse arm is Bash-only.
#   exempt-empty      no command to judge.
#   exempt-cli        guard 4: the command reaches for this store's own CLI.
#   exempt-allowlist  guard 3: `allowlisted_head`.
#   exempt-runner     `runner_head`: a test or build runner, whose failure is the point.
#
# THE ORDER IS THE REFUSE ARM'S OWN, below, because a caller counting exemption KINDS
# would otherwise attribute one to the wrong rule.
#
# WRITTEN AS `[ ... != Bash ]` AND NOT AS A `case "$tool" in`, which is what it was first.
# tests/test_repeat_gate.py::WiringTest fails the file on any `case` over `$tool` outside a
# comment, because under the `Bash|Skill` matcher such an arm is the dead guard
# skills/dead-guard-detection exists to catch. This one is reachable -- a CLI passes the
# tool as an argument, and a `Skill` signature really does reach it -- but a rule that has
# to distinguish the two by reading the surrounding code is a rule that stops holding.
if [ "$ARGV_MODE" = "eligible" ]; then
  if [ "$tool" != "Bash" ]; then printf 'exempt-tool\n'; exit 0; fi
  [ -z "$payload" ] && { printf 'exempt-empty\n'; exit 0; }
  case "$payload" in *skillrepeat*) printf 'exempt-cli\n'; exit 0 ;; esac
  allowlisted_head "$payload" && { printf 'exempt-allowlist\n'; exit 0; }
  runner_head "$payload" && { printf 'exempt-runner\n'; exit 0; }
  printf 'eligible\n'
  exit 0
fi

# THE REFUSE ARM IS BASH-ONLY, and the two guards below are why. Both escape hatches --
# the `*skillrepeat*` reach-for-the-CLI guard and `allowlisted_head` -- live inside this
# branch, so a refused `Skill` call had neither, no way past the refusal and no way to
# retire the signature that caused it. The learn arm still records a Skill failure, because
# that is data `skillreport` wants; only the refusal is withheld. See the stanza above
# `norm_structured` for the measurement that makes a Skill fail row's provenance uncertain.
if [ "$tool" = "Bash" ]; then
  bcmd="$(jqr '.tool_input.command // empty')"
  [ -z "$bcmd" ] && exit 0
  # Guard 4: never refuse a command that is reaching for this store's own CLI.
  case "$bcmd" in *skillrepeat*) exit 0 ;; esac
  allowlisted_head "$bcmd" && exit 0
  runner_head "$bcmd" && exit 0
else
  exit 0
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

# AND RELEASED AGAIN ON EVERY PATH OUT OF HERE THAT DOES NOT EMIT. `hooks/apply-gate.sh`
# argues EMIT, AND ONLY THEN CLAIM at length, and this arm CANNOT take that ordering: the
# claim is what serialises the duplicate delivery both wirings produce, and two refusals
# racing out for one call is the outcome the paragraph above ranks as worse than a missed
# one. Releasing gives the same property the sibling's ordering buys -- a refusal nobody
# saw does not silence the signature for the rest of the session -- without giving up the
# race.
#
# THE WINDOW IS REAL AND WAS MEASURED, not reasoned about. `jq -n --arg r` is an exec, and
# the ENVIRONMENT counts against the same ARG_MAX as the argument vector; no cap in this
# file has any say over it. A cold reviewer judged this unreachable because the reason is
# bounded, which is true of the message and beside the point. It is only reachable with the
# reason NEAR its cap -- the biggest exec before this point is the store query, whose jq
# program is about 1.3 KB, and a typical reason is smaller (895 bytes for `gh pr list
# --state open --limit 20`), so E2BIG reaches the QUERY first and the hook fails open
# before ever claiming. At the cap the reason measures 2096 bytes and the emit is the
# larger exec again. tests/test_repeat_gate.py::DenyEmitFailureTest reproduces exactly
# that, and carries a non-vacuity partner because it asserts on SILENCE.
release_claim() { rmdir "$DIR/denied/$sid/$sig" 2>/dev/null || :; }

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
[ "$n" -lt 1 ] && { release_claim; exit 0; }

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
#
# AND IT SAYS "MATCHES A SHAPE", NOT "THIS EXACT CALL". The store holds callkeys, and a
# callkey is a normalised shape that more than one literal command can share -- see WHAT
# STILL COLLIDES in the header for the five ways. "This exact call has already failed" was
# the sentence here, and against `python3 -c <C:...>`-shaped input it was simply untrue:
# the gate denied a command that had never run while asserting that it had. Either the key
# justifies the sentence or the sentence follows the key, and the key is the thing that has
# to stay coarse for the gate to work at all. So the reason names the shape, says which
# parts were masked out before comparing, and lets the session judge for itself.
reason="A call matching this one has already failed in $n earlier sessions, the same way
each time. The match is on the NORMALISED SHAPE below and not on the literal text: ordinary
quoted arguments, the directory part of an absolute path, and bare numbers are all masked
out before comparing, so a call that differs from the failed one only in those matches too.

  the shape: $what
  the error: $err_disp

$fixline

Nothing ran and nothing was written. This gate declines a given call once per session, so
the same call attempted again in this session goes through -- if this store is stale, that
is the way past it. The full record, and the way to retire it permanently:

  skillrepeat show $sig
  skillrepeat forget $sig"

# RENDERED TO A FILE FIRST, so "did the deny actually reach stdout" is a question with an
# answer. THE SUBSHELL IS NOT DECORATION and `2>/dev/null` on the jq alone is not enough:
# when the emit dies from a SIGNAL rather than an exit status, the message is printed by
# the shell that REAPS the child, not by the child, so the child's own redirect cannot
# catch it -- and a hook may never speak on stderr. `hooks/apply-gate.sh` carries the
# measured reproduction of that.
( jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny", permissionDecisionReason:$r}}' > "$TMP/deny.json" ) 2>/dev/null
[ -s "$TMP/deny.json" ] || { release_claim; exit 0; }
cat "$TMP/deny.json" 2>/dev/null || { release_claim; exit 0; }
exit 0

}
