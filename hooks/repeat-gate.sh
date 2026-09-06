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
# THREE EVENTS ON ONE SCRIPT, AND FOUR RULES ACROSS THEM. It dispatches on
# `.hook_event_name` and takes NO argv.
#
#   PostToolUseFailure -> LEARN.    Record a failure row keyed by signature.
#   PostToolUse        -> RECOVER.  Bind a later success to that signature, so the store
#                                   knows what worked. Two ways in: the first later
#                                   success of the SAME tool, or a success of a DIFFERENT
#                                   tool whose input shares content tokens with the
#                                   failed one (CROSS-TOOL RECOVERY, below). Whichever
#                                   bound it, the arm then SAYS SO once per signature per
#                                   session, through additionalContext.
#   PreToolUse         -> two refusals, and they are different rules on one event:
#                         LESSON.   ON by default. Declines a call while a signature THIS
#                                   session recovered has failed in >= REPEAT_MIN_SESSIONS
#                                   distinct sessions and nothing has been written down
#                                   about it. See THE LESSON GATE below.
#                         REPEAT.   OFF by default. Denies a call whose OWN signature is
#                                   already known broken, naming the error and the agreed
#                                   recovery.
#
# The three are inseparable. A gate that only refuses can only ever say "this failed
# before", which is worth almost nothing: the session already has to rediscover the
# workaround. The recovery arm is what turns the refusal into the answer.
#
# THE REPEAT REFUSAL IS OFF BY DEFAULT (`REPEAT_GATE_REFUSE=1` switches it on). The learn
# and recover arms stay on,
# so the store keeps learning and `skillrepeat`/`skillreport` keep reporting.
# THE REASON IS MEASURED, not a change of heart
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
# THE SAME-TOOL RULE IS NOT EVIDENCE FOR A SHELL, AND THE STORE SAID SO.
#
# `Bash` is a universal shell. Two calls being "the same tool" says nothing whatever about
# whether they are the same operation, so the rule above -- bind the first later success of
# the same TOOL -- binds ANY later command to ANY earlier failure. Measured on the live
# store of 2026-09-03, over the 231 distinct same-tool Bash bindings it had accumulated:
# 52 of them (22.5%) share NOT ONE content token with the failure they were bound to, and
# a further 31 share exactly one, of which 11 share only the word `echo`. The bindings this
# produces read as
#
#   failed:  gh issue view <N> --comments <N>>&<N>
#   worked:  cat notes/OPEN-THREADS.md <N>>&<N>
#
# which is a sentence the recovery arm then STATED to the session that had just done both
# things. That is the arm inventing, in a script whose whole claim is that it reports what
# was measured.
#
# THE COST IS NOT ONLY NOISE, WHICH IS WHY THE ROW IS WITHHELD RATHER THAN MERELY TAGGED.
# A binding CONSUMES its armed failure -- "one recovery per armed failure, then it is
# disarmed" -- so an unrelated success eats the arming, and the genuine fix arriving two
# calls later inside the same window can never be recorded at all. The permissive rule does
# not just add wrong rows; it destroys the right one. On the live store four `gh issue view`
# failures were disarmed by one `cat`.
#
# SO A SHELL'S SAME-TOOL BINDING NOW WANTS WHAT THE CROSS-TOOL ONE WANTS:
# REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS shared content tokens, by the same definition and
# the same comparison. The floor is the same 2 for a plain reason -- nothing here establishes that
# `Bash` following `Bash` is BETTER evidence than one tool following another, and for a
# universal shell it is plainly not -- and the knob exists to say the number is a floor
# rather than a calibration, exactly as REPEAT_RECOVERY_MIN_TOKENS does.
#
# WHAT IT GIVES UP, said plainly: a real fix whose text shares nothing with the failure --
# `gh pr list` recovered by `curl` against the same API, where the URL is masked to `<P>`
# before tokens are taken -- is no longer bound. It degrades to SILENCE, and the refusal
# then says "No recovery was ever recorded for this", which is true. A missed recovery
# costs a fix nobody wrote down; a wrong one is announced to the session as fact. This
# gate errs toward silence everywhere else and errs toward it here.
#
# THE EXACT SELF-RECOVERY IS CARVED OUT and it is not a convenience. A success whose
# normalised call EQUALS the failed one is what the section above builds the refusal's
# self-recovery exclusion on, and short calls carry too few tokens to clear any floor at
# all (`pwd` has one). Binding it unconditionally is what keeps "a signature with ANY
# self-recovery behind it is NEVER REFUSED" true after this change.
#
# WHAT THE FLOOR OF 2 STILL LETS THROUGH, AND WHY IT IS NOT RAISED. The residual case is
# two commands whose only shared tokens are PATH COMPONENTS -- a working directory or a
# file both of them happen to name. A red-team session found this pair, which binds on
# `{remind, hooks}` and is not a fix for anything:
#
#   failed:  <P>/redteam-hooks/... remind ...
#   worked:  sed -n <S> hooks/remind.sh
#
# EXCLUDING SUCH TOKENS WAS TRIED AGAINST THE LIVE STORE AND REJECTED ON THE EVIDENCE.
# The candidate rule -- drop a shared token that occurs only inside slash-bearing words of
# BOTH commands -- was run over every same-tool binding in the store of 2026-09-04 (587
# rows, 254 bindings with a locatable fail row). It would UNBIND 45 of the 254 (17.7%),
# and in 26 of those 45 the two commands name an IDENTICAL path word, which is the
# strongest evidence of relatedness this store carries: `cd <P>/livecd-rootfs && grep -rn
# <S> live-build/` recovered by `cd <P>/livecd-rootfs && sed -n <S> live-build/...` is a
# real fail-then-fix and the rule would drop it. Nothing in the store labels a binding
# true or false, so no precision figure can be computed from it; what CAN be measured is
# the cost, and the cost is a sixth of all bindings with a majority of the sample looking
# correct. The rule is left alone and the false binding above is a KNOWN LIMIT. Raising
# the floor was not considered a substitute: it would drop the same true bindings and
# more.
#
# NON-SHELL TOOLS ARE LEFT ALONE, and `shell_tool()` is the single place that decides
# which is which. `mcp__github__create_issue` names its operation in its own tool name, so
# a success of it after a failure of it is the same operation by construction. `Skill` is
# the unmeasured middle -- one tool name over every skill -- and it is left permissive
# because no store here holds a Skill-to-Skill binding to judge it on. Widening the test is
# a one-line change when one turns up.
#
# ====================================================================================
# A TWO-CHARACTER PROGRAM HAS NO TOKENS, which is how the rule above lost a real fix.
#
# The e2e journey's step 15 fails `ls --nonexistent-flag .` and fixes it with `ls -la .`.
# That is a fail-then-fix in its plainest possible form, and the gate could not see it. A
# content token is three characters or more (CROSS-TOOL RECOVERY below), `ls` is two, every
# other word of the failed call is a flag, and the only thing left is `.`. Zero shared
# tokens against a floor of two, so the store wrote the `fail` row and no `recover` row --
# reproduced against the real hook on 2026-09-05, payloads through stdin.
#
# THE TOKEN RULE IS NOT LOOSENED. Lowering the floor to one would re-admit the 31 bindings
# the section above measured as sharing exactly one token, 11 of them the word `echo`. So a
# SECOND WAY TO EARN THE SAME BINDING is added beside it, and a success binds a `Bash`
# failure when EITHER holds:
#
#   1. the two normalised calls share REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS content tokens
#      (the rule above, unchanged), or
#   2. their first segments name the SAME PROGRAM and share at least one NON-FLAG ARGUMENT
#      WORD -- any length, a flag being a word that starts with `-`.
#
# Rule 2 is `head_arg_bind`, it is tried ONLY where rule 1 found nothing, and the row it
# writes carries `head_arg:true`, so the two kinds of evidence stay countable apart the way
# `cross_tool` already keeps the third apart. `REPEAT_RECOVERY_HEAD_ARG=0` switches it off.
#
# WHAT "FIRST SEGMENT" MEANS HERE, exactly, because every clause of it was paid for. The
# walk takes words off the front of the ALREADY-NORMALISED call and stops at the first
# shell operator, so the rule is about ONE command and `cd <P>/x && rm -rf .` cannot bind
# `cd <P>/x && ls -la .` on the `.` that belongs to two different programs. A leading
# `VAR=value` is stepped over, as `segment_head` steps over one. `<N>`, `<S>` and `<P>` are
# stripped from a word before it is judged, so `<P>build.py` reads as the argument it is
# while `<N>>&<N>` -- what `2>&1` normalises to -- reads as the redirect it is; and a word
# that is nothing BUT a bare mask is no argument at all, since two calls sharing one share
# a number or a string that neither of them contains any more.
#
# `cd` IS STEPPED OVER, AND THE LIVE STORE IS WHY. Written without that clause the rule
# added exactly four bindings to the store of 2026-09-05, and all four were wrong: every
# one had head `cd`, three of them binding on a shared working directory (`<P>/scratchpad`
# twice, `<P>/proj` once) and the fourth on the word `echo`. `cd` names no operation --
# the same objection `shell_tool()` raises against `Bash` one level down -- so `cd` and its
# destination are stepped over, along with the ONE separator that follows them while no
# head has been found yet, and the head is the program that runs after. Stepping over
# rather than refusing is what keeps the dominant shape on this machine,
# `cd <P>/x && <program> ...`, inside the rule at all.
#
# WHAT IT WAS MEASURED TO COST AND TO BUY, on the live store of 2026-09-05: 906 rows, 505
# `fail`, 400 `recover`, 396 of those same-tool `Bash`, and all 396 with a locatable fail
# row by the join the section above describes -- 383 distinct (fail, success) pairs.
#
#   COST. 772 (fail, success) pairs co-occurred in one session and agent within 600
#   seconds carrying DIFFERENT signatures: successes that were really available to an armed
#   failure and did not bind it, which is the only population this store can offer for the
#   question "what would the new rule newly bind". Driven through the real hook, 434 of the
#   772 bind either way and the head-and-argument rule adds ZERO. Before the `cd` clause it
#   added the four above, all false.
#
#   BUY. Over the 396 bindings the store already holds, with the token rule switched off
#   (`REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS=99`), rule 2 alone reproduces 24 of them: a
#   `git add -A && git commit ... && git log --oneline -<N>` recovered by the same three
#   commands under a `cd`, a `grep -c` recovered by a `grep -n`. So it agrees with bindings
#   the older rule already made, rather than only adding a class of its own.
#
# WHAT NEITHER FIGURE IS. Nothing in this store labels a binding true or false, so no
# precision figure comes out of it; and the pairs the rule EXISTS for -- a real fix the old
# rule refused -- are absent by construction, because a success that bound nothing was never
# written down. The e2e pair is exactly that case, which is why it is a test and not a row.
#
# WHAT THE RULE ADMITS, stated rather than left to be discovered. One shared subcommand
# under one program is enough: `gh issue view <N>` binds `gh run view <N>` on `view`, and
# those are different operations on different resources. The token rule declines that pair
# (one shared token against a floor of two), so it is a binding this rule ADDS. It is left
# in, because the 772 real pairs above show the rule adding nothing at all -- tightening
# here would be tuning against a case nobody has met, and every tightening this rule has
# taken so far cost a true binding as well. The test named
# `test_one_shared_subcommand_under_one_program_is_enough_and_that_is_a_limit` is where the
# evidence goes if a real statement ever shows this shape.
#
# THE PAIRS THE RULE IS PINNED AGAINST, each measured through the real hook and each with
# a test of its own in tests/test_repeat_gate.py:
#
#   ls --nonexistent-flag .  -> ls -la .                      BINDS, by rule 2 (`ls`, `.`)
#   git push origin main     -> git status                    no bind: no shared argument
#   gh issue view <N>        -> gh pr list                    no bind: no shared argument
#   gh issue view <N>        -> gh issue view <N> --comments   BINDS, and rule 1 already
#                                                             bound it
#   cat notes/x.md           -> cat notes/y.md                rule 2 DECLINES it -- the
#                                                             only shared word is the head
#                                                             -- while rule 1 binds it on
#                                                             {cat, notes} and always did.
#                                                             The pair binds, and this
#                                                             change did not alter that.
#   python module.py         -> python3 -m module             falls to rule 1, the heads
#                                                             differing; rule 1 finds one
#                                                             shared token against a floor
#                                                             of two, so no bind
#
# ====================================================================================
# CROSS-TOOL RECOVERY, and the whole of the evidence it has.
#
# The same-tool rule above cannot see the shape the maintainer actually described: a
# GitHub MCP tool or a `Skill` call dies, and the session gets the job done with `gh`.
# Two different tools, so nothing binds, so the store never learns that the second one is
# the fix for the first. A failure of tool X followed, within the SAME window, by a
# success of a different tool Y is therefore bound too -- but only when the two calls
# share at least REPEAT_RECOVERY_MIN_TOKENS CONTENT TOKENS, and the row is tagged
# `"cross_tool":true` so a reader can tell the two kinds of evidence apart.
#
# A CONTENT TOKEN IS TAKEN FROM THE NORMALISED CALL, NOT THE RAW ONE, which is what makes
# the comparison cheap and stable: every masking rule above has already run, so a temp
# directory, a body of prose in quotes and a bare number cannot contribute one. The
# normalised text is split on non-word characters and a token is kept when it is at least
# THREE characters and not all digits. The placeholders `<S>`, `<N>`, `<P>` and `<C:`
# survive that split as the single letters S, N, P and C and are dropped by the length
# rule -- deliberately not by a second rule naming them, which would be dead the moment
# the split changed. Tokens are lowercased, deduplicated and the first 60 in sort order
# are kept, so one pasted heredoc cannot make a pending line unbounded.
#
# WHAT THAT BUYS AND WHAT IT COSTS. `mcp__github__create_issue` failing on
# {"owner":"ContextLab","repo":"claude-skill-compounder"} and `gh issue create --repo
# ContextLab/claude-skill-compounder` succeeding share contextlab, claude, skill,
# compounder and repo, and bind. Two commands that merely both mention `json` and `git`
# also bind, and that is the false positive this rule can produce. It is bounded the way
# every other guess here is bounded: by the window, which stops a call twenty steps later
# from being reached at all, and by the plurality rule in the refusal arm, which stops one
# session's wrong candidate from ever being announced as the fix. Two tokens is a floor
# and not a measurement; nothing here has been calibrated against a corpus, and
# REPEAT_RECOVERY_MIN_TOKENS is the knob that says so.
#
# THE MCP HALF OF THAT EXAMPLE IS NOW WIRED FOR, AND IS STILL UNMEASURED. Until 2026-09-03
# the matcher was `Bash|Skill` on all three events, so an `mcp__*` payload was never
# delivered to this script at all and the rule above could only be exercised by driving the
# hook with such a payload by hand. The two events that LEARN now carry
# `Bash|Skill|mcp__.*` (WHAT THE WIRING ADMITS, below), so the platform may deliver one.
# WHAT IS STILL NOT ESTABLISHED IS THAT IT DOES: no MCP tool failure has ever been observed
# arriving at a hook here (docs/CLAUDE-CODE-BEHAVIOR.md), so the third alternative is
# unproven, not proven. A store with no MCP rows in it is therefore the expected sight
# until one turns up, and it does not distinguish "no MCP call failed" from "no MCP call
# was delivered". The store is the only surface that can tell the two apart.
#
# ====================================================================================
# THE RECOVERY WINDOW IS KEYED ON (SESSION, AGENT), AND THE SESSION ALONE IS NOT ENOUGH.
#
# A SUBAGENT SHARES ITS PARENT'S SESSION ID. That is not an inference: it is recorded in
# docs/CLAUDE-CODE-BEHAVIOR.md ("A subagent's file edits are attributed to the parent
# session"), and it is what THE NOT-ARMED EXIT below relies on deliberately -- a subagent
# dispatched by an armed session is refused on the same terms, because dispatching an
# agent is continuing.
#
# For the REFUSAL that is right. For the RECOVERY WINDOW it was a defect, and the defect
# is a wrong row plus a destroyed right one, the same pair the same-tool rule above was
# narrowed for. A parent and every agent it dispatches interleave their tool calls into
# ONE pending file, so a failure inside agent A arms a line that the next token-sharing
# success ANYWHERE in the session binds -- in agent B, or in the parent. Observed live on
# 2026-09-05, in this package's own store: signature c2824570283x405-e2428498712x41 was
# armed by a forge subagent's `cd <P>/watch-ci-run && python3 - <<EOF ... read_text ...`
# and bound to the PARENT's `python3 - <<EOF p='docs/operations.md'; s=open(p).read()
# ...`, two calls that share `python3` and one more token and have nothing else to do
# with each other. Both halves of the cost landed: the parent was told a lesson statement
# about a failure it never made, and the subagent's armed failure was consumed, so its own
# real recovery could no longer bind.
#
# SO THE PENDING FILE IS NAMED FOR THE PAIR. `agent_key()` builds it: `<sid>` for the
# parent, `<sid>+<agent id>` for a dispatched agent. The separator is `+` because it is
# OUTSIDE the identity character class `A-Za-z0-9._-` that both halves are sanitised into,
# so a sanitised session id can never contain one and `<sid>+<aid>` can never collide with
# some other session's `<sid>`. The parent's key is byte-identical to the name this file
# had before, which is what lets a session running across the change keep the failures it
# had already armed.
#
# THE FIELD IS `agent_id`, AND IT IS ON THE POST EVENTS. Measured on this machine, Claude
# Code 2.1.260, macOS 25.6.0, 2026-09-05, with a headless session whose only job was to
# dispatch one general-purpose agent that ran one succeeding and one failing `Bash` call,
# and a hook logging every payload: the agent's success arrived as `PostToolUse` with
# `agent_id` `aafe1443cc49338d5` and `agent_type` `general-purpose`, its failure arrived
# as `PostToolUseFailure` with the SAME `agent_id`, and the parent's own `Bash` and its
# `Agent` call both arrived with NO `agent_id` at all -- all four under one `session_id`.
# n = 1 dispatch, one agent type, one CLI build. The same asymmetry was already recorded
# for `PreToolUse` in docs/CLAUDE-CODE-BEHAVIOR.md at n = 4.
#
# WHAT STAYS PER SESSION, and it is deliberate in both directions. The lesson MARKER
# (`lessons/<sid>`) and the refusal that reads it are per SESSION, so an agent that
# recovers a failure arms the gate for the whole session including its parent -- that is
# the point of the gate, and narrowing it to the agent would let a session walk around a
# refusal by dispatching. The claim markers stay per session too: they are keyed on
# `tool_use_id`, which is unique per call whoever made it.
#
# BOTH ROW TYPES NOW CARRY `agent_id`, null for the parent, so the store can be read per
# agent after the fact. Nothing reads it yet; it is written because a key that cannot be
# recovered from the store is a key nobody can check.
#
# ====================================================================================
# THE LESSON GATE: the first time it is said, the second time it is required.
#
# The maintainer's scenario 2 is "after a failed attempt at doing something, and then
# figuring it out, force claude to write it down before continuing". The recovery arm is
# the moment that is knowable, and until 2026-09-03 it wrote a row and said nothing, so
# the knowledge went into a JSONL file nobody reads mid-session.
#
#   FIRST TIME -- the recovery arm STATES the fact. Which call failed, with the head of
#   its error; which call then worked; and the two commands that exist -- the one that
#   records a lesson, and `skillrepeat dismiss`, named for what it now is: a command for a
#   PERSON at a terminal, which lifts nothing when a model runs it (WHO MAY DISMISS,
#   below). It is a statement and never an instruction, for the reason under PLATFORM
#   FACTS 4, and it is emitted once per signature per session. Nothing is blocked.
#
#   AND WHEN THE RECOVERY WAS A SCRIPT, THE LINE CARRIES `--attach`. The requirement is to
#   write the lesson down "including the relevant contextual information and any associated
#   code or scripts", and on 2026-09-05 three of the 71 `note` rows ever written carried an
#   attachment while this statement and the deny below named `skillnote add --lesson` with
#   no argument but text. `script_attach` reads the RECOVERY's normalised command and
#   answers with a path, a placeholder, or nothing. Its shape detection is
#   hooks/compound-improvement.sh's `mutates_file()` NARROWED TO SCRIPTS and reimplemented
#   rather than imported: that one answers "did this call write a file" for a checkpoint
#   counter, this one answers "is there a file worth keeping beside the note", and the two
#   want opposite things from a `> notes.md`. A `<P>` mask is a directory this script
#   cannot reconstruct, so `<path to the script>` is printed rather than a path that would
#   not open -- silence about WHICH file, never a wrong file. THE DENY GAINS THE SAME
#   CLAUSE ON THE SAME ONE COMMAND and gains nothing else: ONE COMMAND is a measured rule
#   (WHO MAY DISMISS), and an attachment is an argument to that command, not a second one.
#
#   THE CLOSING LINE OF THE STATEMENT NAMES `skillnote skill`, which is what a note becomes
#   when it should be callable rather than read -- "a combination of notes and code that is
#   searchable, findable as a tool in the appropriate future contexts, and callable by
#   agents", in the maintainer's words. It is on the STATEMENT and not on the deny, for the
#   reason `skillrepeat dismiss` is not on the deny either: the deny names one command, and
#   the one it names is the one that lifts it.
#
#   THAT DELIVERY IS MEASURED, and it was measured by accident, which is the only reason
#   it is not still an open question here. `additionalContext` was already established on
#   `PreToolUse`, `UserPromptSubmit` and `SessionStart` (docs/CLAUDE-CODE-BEHAVIOR.md) and
#   NOT on `PostToolUse`; this arm was the first thing in the package to send one. On
#   2026-09-03, Claude Code 2.1.259, macOS 25.6.0, the session BUILDING this arm ran a
#   `bash` call that timed out at 600 s and then got the same information with a plain
#   `cat`. The real hook, wired into that live session, bound the recovery and emitted its
#   statement, and the statement arrived in the session's context labelled
#   `PostToolUse:Bash hook additional context` -- the failed `until ... done` shape, the
#   `Exit code 143` head, the `cat` that worked, and both commands. So it reaches the
#   model, on this version, on this event.
#
#   IT IS STILL WRITTEN TO BE WORTH NOTHING IF IT IS DROPPED, and that is not now a
#   contradiction. One observation on one version is not a guarantee across versions, and
#   the mechanism must not depend on it: the `recover` row is in the store either way,
#   `skillrepeat list` prints the signature as `open` either way, and the SECOND-TIME gate
#   below is a `PreToolUse` deny, which has its own measurement.
#
#   `suppressOutput` is deliberately NOT set, which is the opposite of what every other
#   hook here does. Those are nudges addressed to the model; this one is a record of
#   something the USER's session just did, and the two commands in it are the user's to
#   run. A statement the human cannot see is not a record.
#
#   SECOND TIME -- the lesson gate DECLINES the next call, while three things hold at
#   once: this session bound a recovery for the signature, the signature's fail rows come
#   from at least REPEAT_MIN_SESSIONS distinct sessions COUNTING THIS ONE, and no lesson
#   references it. At the default of 2 that is this session plus one earlier: the second
#   occurrence, which is the one the doctrine names ("the second time that same signature
#   comes round, it declines the next call until the lesson is written down").
#
# THE TWO ARMS COUNT THE CURRENT SESSION DIFFERENTLY, AND THE DIFFERENCE IS THE POINT.
# The repeat arm's count drops every fail row carrying THIS session's id (`.session !=
# $sid` there): its refusal is an INFERENCE FROM HISTORY -- "this call is broken here,
# because it has died in N sessions that were not this one" -- and a session's own
# failures feeding that inference is what BOOTSTRAP DEADLOCK guard 1 exists to stop. The
# lesson arm's count takes the distinct sessions of the fail rows UNIONED with the
# current session (`+ [$cur]` in `lesson_gate`): its refusal is not an inference at all
# but a fact about the session in front of it -- it failed this way, then got it working,
# and wrote nothing down -- plus the one earlier observation that makes the failure
# recurring rather than a fluke. This session IS the second occurrence, so this session
# counts, ONCE. The union rather than a plain count is what keeps guard 1 in substance: a
# session contributes exactly one whatever it does to itself, so a signature that has
# failed only here stands at 1, never reaches the default of 2, and nothing a session
# does to itself can build its own refusal.
#
# WHAT IT DID BEFORE, TWICE OVER, AND WHY NEITHER WAS RIGHT. Until 2026-09-04 this count
# was a plain count of distinct sessions and included the current one by accident, so it
# fired on this session plus one earlier -- the rule stated here, reached by an arm whose
# header, `bin/skillrepeat` and .claude/CLAUDE.md all described the other one; a red-team
# session found it by counting the sessions in the store against the sessions in the
# deny. The 2026-09-04 repair made the header true by excluding the current session on
# both arms, and at the default that put the first refusal in the THIRD session -- two
# EARLIER sessions plus the recovery bound in this one -- one session later than
# README.md, the doctrine in skills/skill-compounder/SKILL.md and the maintainer's request
# of 2026-09-03 all read. The 2026-09-06 repair moved the CODE toward the doctrine rather
# than the doctrine toward the code, on the lesson arm only, and made the inclusion
# deliberate (the union) where it had been incidental (a row). The default of 2 did not
# move and no knob was added: 2 is "this session and one other". `REPEAT_MIN_SESSIONS=1`
# on this arm now means the FIRST occurrence -- a session that fails, recovers and is
# refused on its own evidence -- which is not a trap, since the escape is one command and
# `lesson_cli_head` can never refuse it, and is not a default either.
#
# WHAT LIFTS IT, AND WHO MAY DISMISS. Two things lift it and neither is a deletion:
# `skillnote add --lesson <sig> "<text>"` writes a `note` row carrying `lesson_sig` into
# <state>/ledger.jsonl, and `skillrepeat dismiss <sig> --why "<why>"` appends a `dismiss`
# row to this store. This script READS both and writes neither.
#
# A DISMISSAL LIFTS IT ONLY WHERE A PERSON WROTE IT. The rows honoured here are those
# whose `actor` is `human`, plus every `dismiss` row written before that field existed --
# those predate the model path entirely and carry nothing to tell them apart, so they are
# read as human. `bin/skillrepeat` stamps `actor:"model"` when it runs inside a Claude
# Code session (`CLAUDECODE` or `CLAUDE_CODE_SESSION_ID` in its environment), and such a
# row lifts NOTHING here.
#
# THAT RULE IS MEASURED, and it is why the deny below names ONE command and the statement
# names two. Driven live on 2026-09-04: both of two fresh sessions this gate refused
# answered by running `skillrepeat dismiss <sig> --why "<a reason it invented>"` and
# carrying straight on. The gate had printed its own escape and the escape was free. So a
# LESSON is the only thing a session can do to lift this. A model's dismissal is still
# appended, still printed by `skillrepeat list`, and still evidence of what that session
# wanted to do -- refusing to write the row would have hidden that; refusing to HONOUR it
# is the half that matters.
#
# THE LEDGER IS APPEND-ONLY ON BOTH SIDES OF THAT, so the read is not "is there a row".
# `skillnote remove <id>` appends `{"event":"note","action":"remove","id":...}` and leaves
# the `add` row exactly where it was; a reader matching on `lesson_sig` alone would go on
# reporting a withdrawn lesson as standing while the note itself was gone from the
# CLAUDE.md it was meant to be read from. Adds minus removed ids, and nothing else counts.
#
# ONE LIMIT WORTH KNOWING, and it belongs to the other CLI: `skillnote --lesson` refuses a
# signature whose fail row is not a Bash call, because the reminder half of a lesson is
# keyed on `.tool_input.command` and a Skill or MCP call has none. Such a signature does
# reach this arm: the two learning events are wired `Bash|Skill|mcp__.*`, so a Skill or
# MCP failure is learned and its recovery can deny the next Bash call. The statement
# below names the command anyway -- what it names is the command that records the lesson,
# and for such a signature the answer that command gives, which is to write a note and a
# keyword reminder instead, is the useful one.
#
# SO SAY EXACTLY WHAT LIFTS IT. This paragraph used to end "the refusal is always
# liftable, because `skillrepeat dismiss` has no such restriction", and that stopped
# being true the day a model's dismissal stopped being honoured. TWO things lift the
# refusal and only two: a STANDING LESSON for the signature, adds minus removed ids,
# which `--lesson` is the sole writer of and which is the one route it can refuse; and a
# `dismiss` row a PERSON wrote, which carries no Bash restriction and lifts any
# signature. The third used to be the deny budget running out, and it is gone at the
# default -- see AND IT NO LONGER LETS GO. A dismissal written from inside a session is
# stamped `actor:"model"` and lifts NOTHING -- WHO MAY DISMISS, above -- so for a
# non-Bash signature there is nothing a session can do on its own, and the honest answer
# there is that a person has to type one line. That is why the deny below prints one
# command and marks the other "a person at a terminal only".
#
# AND IT NO LONGER LETS GO. REPEAT_LESSON_MAX_DENIES defaults to `unlimited`, and the two
# exits are a STANDING LESSON on the ledger and a HUMAN's `skillrepeat dismiss`. Nothing
# else ends it -- not waiting, not rewording, not a model's own dismissal.
#
# THE BUDGET WAS THE HOLE AND IT WAS MEASURED TWICE. It shipped at 2, silently, on the
# argument that a wall a session cannot lift is a wall it learns to route around. What was
# measured on 2026-09-05, against the INSTALLED package over 15 real sessions: 2 of 2
# refused sessions spent BOTH denies on the IDENTICAL command -- "Let me try running the
# script directly with a simpler approach", re-issued verbatim -- and then ran it, writing
# no lesson and no dismissal. The silence did not help: it made the wall look like weather
# rather than a decision. On the live store of that day, 2 of the 16 sessions that had ever
# armed a lesson marker reached the cap, and both were that red team; the sentence this
# stanza used to carry, that none had reached two, was false the day it was checked.
#
# WHAT A FALSE POSITIVE NOW COSTS, stated plainly because it is the argument for removing
# the valve rather than raising it: ONE LESSON LINE, once, for that signature forever. A
# standing lesson lifts the refusal for good, and a lesson is allowed to say that the
# failure is EXPECTED -- a red-green test run, a probe whose error is the answer, a store
# whose shape match is stale. The deny text says so in one clause, so a session holding a
# real false positive has a true sentence to write rather than a wall to outwait. Against
# that, a budget buys a session the right to skip the sentence, which is the whole of what
# the gate is for.
#
# THE DENY STILL DOES NOT NAME THE KNOB, and that omission is as deliberate as the one
# about `skillrepeat dismiss`. The reason used to end "It is spent at most 2 times on one
# signature in one session, after which the call goes through whatever this store says",
# and a session red-teaming this gate on 2026-09-04 read that as a schedule. There is now
# no schedule to advertise; a knob that names one is still not offered to the session.
# REPEAT_LESSON_MAX_DENIES=<N> restores a budget of N for anyone who wants the valve back,
# and REPEAT_LESSON_MAX_DENIES=0 means what it always meant, which is never refuse.
#
# THE HEAD ALLOWLISTS DO NOT APPLY TO THIS ARM ANY MORE. See `lesson_cli_head`: the only
# call that runs while a marker is armed is one that reaches for `skillnote` or
# `skillrepeat`, so the command that ends the refusal can never itself be refused, and
# nothing else can be mistaken for it.
#
# IT IS ON BY DEFAULT AND THE REPEAT ARM IS NOT, and the asymmetry is the population each
# one can reach. The repeat arm's population was measured and found empty (issue #27): 81
# sessions, no refusal ever. This one fires only where a failure AND its recovery were
# both observed in the session it is speaking to, which is a fact about the session in
# front of it rather than an inference from history -- and it names the two commands that
# end it. What would turn it off is a measured false-positive rate, which is what
# REPEAT_LESSON_GATE=0 exists to make collectable.
#
# ====================================================================================
# BOOTSTRAP DEADLOCK, and what is done about it. A gate that learns from failures can
# learn to refuse the commands needed to inspect or undo it, and then the session is
# trapped with no way out that does not involve editing settings.json. Four independent
# guards, any one of which is enough:
#   1. Failures recorded by THIS session never count on the repeat arm, and count ONCE
#      on the lesson arm. The repeat refusal needs REPEAT_MIN_SESSIONS distinct EARLIER
#      sessions, so nothing a session does to itself can lock it out mid-flight; the
#      lesson refusal needs REPEAT_MIN_SESSIONS distinct sessions with this one in the
#      union, so a session is one observation however many times it fails, and on its own
#      it never reaches the default.
#   2. Deny-once-per-session-per-signature, above. Every refusal has a next attempt.
# THREE OF THE FOUR BELOW BELONG TO THE REPEAT ARM ONLY. The lesson gate keeps 1 in
# substance -- this session is one observation, never more -- and replaces 2, 3 and 4 with a single exemption
# for the command that ENDS it (`lesson_cli_head`). It has to: the thing it refuses is
# continuing, and `cat`, `git` and `ls` are continuing. What stops it being a trap is that
# the escape is one command, is printed in the refusal, and can never itself be refused.
#
#   3. A HEAD ALLOWLIST, APPLIED TO EVERY SEGMENT AND NOT TO THE FIRST WORD. If the
#      command's every segment head is one of the navigation, inspection, git, jq or
#      skill* commands below, the call is never refused. `cd`, `ls`, `git`, `jq`, `cat`,
#      `grep`, `find` are how a session diagnoses anything at all, and this package's own
#      CLIs are how it reads and clears this store. EVERY head, because reading only the
#      first was a bypass: `cd build && tar -xf ../release.tgz` was exempted on `cd` and
#      `true && <anything>` on `true`, while the bare `tar` was denied (red team,
#      2026-09-04, found unaided on a fifth attempt). `gh issue view 19 | jq .` is still
#      refusable, which is what reading only the first head was trying to protect: `jq`
#      after a pipe no longer exempts anything, because `gh` is a head too.
#   4. Any command mentioning `skillrepeat` anywhere is never refused, so a compound
#      command that clears the store cannot itself be blocked.
#
# WHAT THE WIRING ADMITS, AND WHAT THAT COSTS. It is TWO MATCHERS OVER THREE EVENTS, the
# same pair in BOTH install paths (skill_compounder/installer.py and hooks/hooks.json):
#
#   PostToolUseFailure   `Bash|Skill|mcp__.*`   the two events that LEARN and RECOVER
#   PostToolUse          `Bash|Skill|mcp__.*`
#   PreToolUse           NO MATCHER AT ALL      the one event that REFUSES
#
# THE REFUSING EVENT LOST ITS MATCHER ON 2026-09-05, and it is the same shape as
# hooks/mission.sh's PreToolUse entry, which has never carried one. The reason is measured:
# a session this gate refused on a `Bash` call answered with `Read data/f2.txt` and
# finished the job (red team of the installed package, scenario 6). "Force claude to write
# it down before continuing" is a claim about CONTINUING, and continuing is any tool. So
# the lesson gate now refuses every tool while a marker is armed; see IT REFUSES EVERY
# TOOL below for the one exemption and for what it costs.
#
# A matcher is a REGEX over the tool name, not a substring -- measured 2026-08-26 on
# 2.1.246: of eight matchers on one event, `Bash`, `^Ba`, `Ba.*`, `Bash|mcp__.*`, `*` and
# `.*` each received a `Bash` call, while `Ba` and `as` received nothing
# (docs/CLAUDE-CODE-BEHAVIOR.md, "A hook matcher is a regex over the tool name, not a
# substring"). `Bash|mcp__.*` receiving its `Bash` call is the whole of the evidence that
# adding a third alternative cannot cost the first two. That same probe measured NOTHING
# about whether `mcp__.*` reaches a real MCP tool, and none has been observed arriving
# here, so the MCP half is UNPROVEN rather than proven.
#
# THE LEARNING EVENTS ARE STILL NARROWER THAN THE REFUSING ONE, WHICH IS THE REVERSE OF
# WHAT IT WAS, and the two questions really are different. To LEARN, this script must
# compute a signature, and it has a normalising rule for exactly three payload shapes; a
# `Read` failure keyed by `norm_structured` is a row nothing can act on. To REFUSE, it
# needs no signature for the call in front of it at all -- the signature is the one the
# marker already names -- so there is nothing about a `Read` it cannot judge.
#
# WHAT IT COSTS IS REAL AND IS PAID ON EVERY TOOL CALL. This hook forks a process on every
# delivery, twice over with both wirings active, and the read tools are the high-frequency
# ones. So the not-armed path was cut to FOUR program starts -- `cat`, `jq`, `tr`, `cut` --
# and pinned there by tests/test_repeat_gate.py::ProcessCountTest, which fails on the
# fifth. A session that has bound no recovery has no `lessons/<sid>` directory, and that
# `[ -d ]` is a builtin.
#
# WHAT IT STILL COSTS IS REACH ON THE LEARN SIDE: a Read, a Glob or a Grep that fails the
# same way in session after session is invisible to the store, and always was. There is no
# in-script allowlist for them and there must not be one: a `case "$tool" in Read|Glob|Grep)`
# arm is an EXEMPTION from a refusal, and the refusal is now exactly what those tools are
# meant to receive.
#
# WHAT IS NOT THAT ARM is the shape test at the top of the payload read, and the difference
# is the one to hold on to. It grants no tool an exemption from anything; it declines to
# compute a signature for a payload there is no rule for. See THE SHAPES THIS SCRIPT HAS A
# RULE FOR, below, for why `mcp__.*` is what made that stop being inferrable.
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
# THE STORE is <state>/repeats/index.jsonl, APPEND-ONLY. Four row types:
#   {"t":"fail",   ts, sig, ck, ec, tool, norm, cmd, err, session, tuid}
#   {"t":"recover",ts, sig, ck, tool, norm, cmd, session, tuid[, cross_tool:true]}
#   {"t":"forget", ts, sig, session, why}          <- written only by bin/skillrepeat
#   {"t":"dismiss",ts, sig, session, why, actor}   <- written only by bin/skillrepeat
# `cross_tool` is present only when the recovery was bound by shared content tokens
# rather than by the tool matching, so a reader can weigh the two kinds of evidence
# differently; every reader that does not care about it ignores it, since jq's `//`
# supplies the absent field. A `dismiss` is NOT a tombstone: it suppresses no row and
# changes no count. It is read by the lesson gate and by `skillrepeat list` and by
# nothing else. Its `actor` is `human` or `model`, and the lesson gate honours only the
# first (WHO MAY DISMISS, above); a row with no `actor` at all was written before the
# field existed and is read as human.
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
#   SKILL_COMPOUNDER_REPEAT_GATE (1)  0 disables every arm, both refusals included.
#   REPEAT_GATE_REFUSE            (0) 1 switches the REPEAT refusal on. Any other value is
#                                     off. Off is the default and the paragraph above is
#                                     why. It gates ONLY that refusal: the learn arm, the
#                                     recovery arm, the LESSON gate and
#                                     `--norm-of`/`--eligible-of` are unaffected, so the
#                                     store keeps growing and the instruments keep reading
#                                     it whichever way it is set.
#   REPEAT_GATE_NOW               ()  this script's clock, epoch seconds. Its own, not
#                                     borrowed: pinning another script's does nothing here.
#   REPEAT_MIN_SESSIONS           (2) distinct sessions with a fail row before a refusal,
#                                     and the two arms count the current session
#                                     differently ON PURPOSE. The repeat arm never counts
#                                     it (BOOTSTRAP DEADLOCK guard 1: its refusal is an
#                                     inference from history). The lesson arm counts it
#                                     exactly once, so at 2 the refusal lands on this
#                                     session plus one earlier -- the doctrine's second
#                                     occurrence. THE TWO ARMS COUNT THE CURRENT SESSION
#                                     DIFFERENTLY, above, has the reasoning and the
#                                     history.
#   REPEAT_RECOVERY_MIN_TOKENS    (2) content tokens two normalised calls must share
#                                     before a success of a DIFFERENT tool is bound as a
#                                     recovery. 0 disables cross-tool binding entirely
#                                     and leaves the same-tool rule untouched. A floor,
#                                     not a calibration: see CROSS-TOOL RECOVERY.
#   REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS
#                                 (2) content tokens a success must share with the failed
#                                     call before the SAME-TOOL rule binds it, WHEN THE
#                                     TOOL IS A GENERAL-PURPOSE SHELL (`Bash`). 0 restores
#                                     the unconditional same-tool binding this script
#                                     shipped until 2026-09-03. An EXACT self-recovery --
#                                     the success's normalised call equal to the failed
#                                     one -- binds whatever this is set to, because the
#                                     refusal arm's self-recovery exclusion is built on
#                                     those rows and a short call like `pwd` carries only
#                                     one token. Non-shell tools are unaffected: see
#                                     THE SAME-TOOL RULE IS NOT EVIDENCE FOR A SHELL.
#   REPEAT_RECOVERY_HEAD_ARG      (1) the SECOND way a `Bash` same-tool binding can be
#                                     earned: the same first-segment program plus one
#                                     shared non-flag argument word. Exactly `0` is off;
#                                     every other value, a typo included, is the shipped
#                                     default. Tried only where the token rule found
#                                     nothing, and the row it writes says `head_arg:true`.
#                                     See A TWO-CHARACTER PROGRAM HAS NO TOKENS.
#   REPEAT_LESSON_GATE            (1) 0 switches the lesson refusal off. Exactly `0` is
#                                     off and everything else is on -- the opposite
#                                     spelling from REPEAT_GATE_REFUSE, and deliberately:
#                                     there a typo must not switch a refusal ON, here a
#                                     typo must not silently switch the shipped default
#                                     OFF. Whichever way a value is misspelled, it lands
#                                     on the documented default.
#                                     COST, MEASURED. There are TWO figures and only one
#                                     of them is common. The CHEAP path is a session that
#                                     has bound no recovery: no `lessons/<sid>` directory,
#                                     so the arm leaves on one `[ -d ]` and the two
#                                     REPEAT_GATE_MAX_BYTES figures above did not move when
#                                     it landed. The EXPENSIVE path is a session that HAS
#                                     bound one, which parses the store and the ledger:
#                                     0.33-0.35 s over TEN runs on this machine
#                                     2026-09-03, at 15831 rows / 4190377 B with a
#                                     351780 B ledger -- the same order as the refuse arm
#                                     on the same store, and printed on every run of
#                                       PYTHONPATH=$PWD python3 tests/test_repeat_gate.py \
#                                         CostTest -v
#                                     It is bounded PER SIGNATURE PER SESSION and not per
#                                     tool call, because the marker is removed the moment
#                                     its signature is judged unable to qualify.
#   REPEAT_LESSON_MAX_DENIES
#                         (unlimited) refusals the lesson gate may spend on one signature
#                                     in one session. THE DEFAULT IS NO EXPIRY: only a
#                                     standing lesson or a human's dismissal ends it. See
#                                     AND IT NO LONGER LETS GO for the measurement that
#                                     removed the budget -- 2 of 2 refused sessions spent
#                                     both denies on the identical command and wrote
#                                     nothing. A positive integer restores a budget of
#                                     that many refusals per signature per session, for
#                                     anyone who wants the valve back. `0` means it never
#                                     refuses, which is what REPEAT_LESSON_GATE=0 means as
#                                     well; the two stay separate because one is a switch
#                                     and the other is a budget. Anything else -- a typo,
#                                     an empty export, eleven digits -- lands on
#                                     `unlimited`, the documented default.
#   REPEAT_RECOVERY_WINDOW        (5) successful calls of any tool THIS HOOK IS WIRED FOR
#                                     -- on PostToolUse that is `Bash|Skill|mcp__.*`, and
#                                     nothing else is delivered -- after which an armed
#                                     failure stops looking for its recovery, by either
#                                     rule.
#                                     The stream it counts is therefore far sparser than
#                                     "every tool call", and a recovery five Bash calls
#                                     later binds however many files were read in between.
#                                     The window is counted PER (SESSION, AGENT): a
#                                     subagent's calls do not spend the parent's window
#                                     and cannot bind its failures. See THE RECOVERY
#                                     WINDOW IS KEYED ON (SESSION, AGENT) above.
#   REPEAT_GATE_MAX_BYTES   (4194304) store read budget; a larger store fails OPEN. The
#                                     store is ROTATED at half this, by rename into
#                                     repeats/archive/, so that never happens: an
#                                     append-only store reaches this cap on its own and
#                                     then disables the gate in silence.
#                                     COST, MEASURED rather than assumed. THIS STANZA IS
#                                     THE ONLY PLACE THE REPEAT ARM'S FIGURE IS WRITTEN
#                                     DOWN. The LESSON gate's is a different arm on a
#                                     different path and lives in its own stanza above;
#                                     neither is a copy of the other.
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
#   SKILL_COMPOUNDER_STATE        ()  state root ($HOME/.claude/skill-compounder). Two
#                                     files under it are read: repeats/index.jsonl, which
#                                     this script owns, and ledger.jsonl, which
#                                     bin/skillnote owns and this script never writes.
#
# EVERY failure path exits 0 and prints nothing: no jq, no session id, no tool name, an
# unreadable or oversized store, a malformed payload, an unwritable state directory. The
# only output this script ever produces is deliberate, and there are exactly two kinds:
# a deny on PreToolUse, and one additionalContext statement on PostToolUse when a
# recovery is first bound.
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
MIN_TOKENS="${REPEAT_RECOVERY_MIN_TOKENS:-2}"
# The same floor for the same-tool rule when the tool is a shell, and validated as a number
# where the cross-tool one is not: this value is compared with `-le` on a path that runs for
# every armed failure, and a non-numeric export would put a `[: integer expression expected`
# on a stderr this script closes -- a knob that silently changed the binding rule and said
# nothing. A misspelling lands on the documented default.
SAME_TOKENS="${REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS:-2}"
case "$SAME_TOKENS" in ''|*[!0-9]*) SAME_TOKENS=2 ;; esac
# THE SECOND WAY A SHELL'S SAME-TOOL BINDING CAN BE EARNED, and it ships ON, so exactly
# `0` is off and every other value -- a typo included -- lands on the documented default.
# That is REPEAT_LESSON_GATE's spelling and the reverse of REPEAT_GATE_REFUSE's, for the
# reason both of those give: the state a misspelling reaches has to be the shipped one.
# It exists so the rule can be driven both ways against the live store by ONE script; see
# A TWO-CHARACTER PROGRAM HAS NO TOKENS for what that measured.
HEAD_ARG="${REPEAT_RECOVERY_HEAD_ARG:-1}"
case "$HEAD_ARG" in 0) HEAD_ARG=0 ;; *) HEAD_ARG=1 ;; esac
# EXACTLY `0` IS OFF AND EVERYTHING ELSE IS ON, which is the reverse of REFUSE above and
# is argued in the ENV stanza: this knob ships ON, so the spelling that survives a typo
# has to be the documented default rather than the safest-looking one.
LESSON_GATE="${REPEAT_LESSON_GATE:-1}"
case "$LESSON_GATE" in 0) LESSON_GATE=0 ;; *) LESSON_GATE=1 ;; esac
# THE DEFAULT IS NO EXPIRY, and `unlimited` is spelled out rather than encoded as a
# number. See AND IT NO LONGER LETS GO in the header: a budget the session can outwait is
# a budget the session outwaits, measured twice. `0` keeps the meaning it always had --
# never refuse -- so the two states cannot be confused by a reader of a shell history:
# `0` is off, `unlimited` is the shipped default, and a positive integer is a budget for
# anyone who wants one back. A typo lands on `unlimited`, the documented default, which
# is the same direction REPEAT_LESSON_GATE's guard errs in.
LESSON_MAX="${REPEAT_LESSON_MAX_DENIES:-unlimited}"
MAX_BYTES="${REPEAT_GATE_MAX_BYTES:-4194304}"
ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
DIR="$ROOT/repeats"
STORE="$DIR/index.jsonl"
# READ, NEVER WRITTEN, by this script. bin/skillnote owns it; the lesson gate only asks
# it whether a `note` row carrying this signature exists.
LEDGER="$ROOT/ledger.jsonl"

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
case "$MIN_TOKENS"   in ''|*[!0-9]*) MIN_TOKENS=2 ;; esac
# THREE STATES, NOT TWO, so `LESSON_MAX` stays an integer every arithmetic test below can
# read and `LESSON_UNLIMITED` carries the third. Every arm assigns both, so neither can be
# unset under `set -u`. The magnitude half of the guard is here for the reason the others
# carry it: 23 nines is all digits, so the shape half alone passes it through to `[ -ge ]`.
case "$LESSON_MAX" in
  unlimited)                LESSON_UNLIMITED=1; LESSON_MAX=0 ;;
  ''|*[!0-9]*|???????????*) LESSON_UNLIMITED=1; LESSON_MAX=0 ;;
  *)                        LESSON_UNLIMITED=0 ;;
esac
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
  # ONE jq READ FOR THE FIVE FIELDS THIS SCRIPT DISPATCHES ON, and the reason is the
  # PreToolUse wiring. That event carries NO MATCHER since 2026-09-05 (WHAT THE WIRING
  # ADMITS, below), so this script is now forked for EVERY tool call a session makes,
  # twice over with both wirings active -- a `Read`, a `Glob`, a `TodoWrite`. It used to
  # read `.hook_event_name`, `.session_id`, `.tool_name` and `.tool_use_id` in four
  # separate `jqr` calls, which is four `jq` starts on the commonest path in the package.
  # One `jq` printing all five separated by US answers the same question, and what it
  # buys is measured rather than asserted: tests/test_repeat_gate.py::ProcessCountTest
  # pins the whole not-armed path at FOUR program starts -- `cat`, `jq`, `tr`, `cut` --
  # and fails on the fifth.
  #
  # `read` WITH IFS SET TO US KEEPS EMPTY FIELDS, which is why the separator is a control
  # byte and not whitespace: `a<US><US><US>` assigns one value and three empty strings,
  # where IFS whitespace would collapse them and slide `tool` into `sid`. `agent_id` is
  # the fifth and it is EMPTY on every event the parent session makes -- see THE RECOVERY
  # WINDOW IS KEYED ON (SESSION, AGENT) in the header -- so it is read here rather than in
  # a second jq, and the not-armed path still costs the four programs ProcessCountTest
  # pins: adding a field to a jq already running costs no process at all.
  pfields="$(printf '%s' "$payload" | jq -r '
      [(.hook_event_name // ""), (.session_id // ""), (.tool_name // ""),
       (.tool_use_id // ""), (.agent_id // "")] | join("\u001f")' 2>/dev/null)"
  IFS=$'\037' read -r event sid tool tuid aid <<EOF
$pfields
EOF
  case "$event" in
    PreToolUse|PostToolUse|PostToolUseFailure) ;;
    *) exit 0 ;;
  esac
  # THE REPEAT REFUSAL IS OFF UNLESS REPEAT_GATE_REFUSE=1 -- see the stanza under THREE
  # EVENTS. Tested HERE and not down at the arm so that a PreToolUse costs one fork and
  # one jq read when both refusals are off: no store read, no query, no marker written.
  # THE LESSON GATE IS THE SECOND TERM and it is the one that is ON by default, so the
  # exit is now taken only when BOTH are off. What keeps the default cheap is not this
  # line but the marker directory tested a few lines below.
  if [ "$event" = "PreToolUse" ] && [ "$REFUSE" != "1" ] \
     && [ "$LESSON_GATE" != "1" ]; then exit 0; fi

  # A row with no session cannot be counted per-session, and the whole gate is a count of
  # distinct sessions. Fail open rather than invent one.
  [ -z "$sid" ] && exit 0
  sid="$(printf '%s' "$sid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
  case "$sid" in ''|.|..) sid=_ ;; esac

  # THE NOT-ARMED EXIT, AND IT IS THE PATH ALMOST EVERY DELIVERY TAKES. The lesson gate
  # can do nothing at all for a session that has bound no recovery -- there is no
  # `lessons/<sid>` directory for it to read a signature out of -- so with the repeat arm
  # off (the shipped default) a PreToolUse leaves HERE, before the clock, before the
  # `mktemp` and before the second jq the tuid guard used to cost. Four programs have run
  # by this line and none of them touched the store.
  #
  # SUBAGENTS SHARE THE PARENT'S SESSION ID, so a subagent dispatched by an ARMED session
  # finds the same marker directory and is refused on the same terms. Measured on this
  # machine 2026-09-05, off <state>/mission/hits.jsonl: session
  # f288cf8c-846d-4da7-89b9-f2574362ed2a carries a `dispatch` row with a null `agent_id`
  # and a `subagent` row with `agent_id` ab41a53c274603592 under the SAME `session`, and
  # four other sessions in that file show the same pairing. That is the intended reading
  # of "before continuing": dispatching an agent is continuing.
  if [ "$event" = "PreToolUse" ] && [ "$REFUSE" != "1" ] \
     && [ ! -d "$DIR/lessons/$sid" ]; then exit 0; fi

  [ -z "$tool" ] && exit 0

  now="${REPEAT_GATE_NOW:-}"
  case "$now" in ''|*[!0-9]*) now="$(date +%s 2>/dev/null)" ;; esac
  case "$now" in ''|*[!0-9]*) exit 0 ;; esac

  # THE SHAPES THIS SCRIPT HAS A RULE FOR, and nothing else. `norm_bash` keys a Bash
  # command; `norm_structured` keys a `Skill` or an `mcp__*` payload out of `.tool_input`.
  # Anything else leaves here, before the mktemp and before any arm, so a delivery this
  # script cannot key costs one fork and one jq read and writes nothing at all.
  #
  # IT DOES NOT APPLY TO `PreToolUse` ANY MORE, and that exception is the whole of what
  # widening the refusing matcher required. The lesson gate refuses a call; it does not
  # KEY one, so it needs no normalising rule for the payload in front of it -- it reads a
  # marker directory named for the session and, for a `Bash` call only, the command text.
  # A `Read` under an armed session is exactly the shape the red team of 2026-09-05 used
  # to walk around a Bash refusal (`Read data/f2.txt` after the deny, scenario 6), so a
  # test on `$tool` here would be the hole rather than the guard. The two events that
  # LEARN still leave here, because those two really do have to compute a signature.
  #
  # IT IS A CONTRACT, NOT AN ALLOWLIST, and that is what keeps it off the dead-guard list
  # under WHAT THE WIRING ADMITS. `case "$tool" in Read|Glob|Grep)` is an EXEMPTION -- it
  # spares a named tool a refusal it could never have received. This one names the payload
  # shapes there is a normalising rule for and refuses to invent a signature for the rest;
  # it spares nothing, because the refusal arms below are Bash-only either way.
  #
  # WHY IT WAS NOT NEEDED BEFORE AND IS NOW. Under `Bash|Skill` the else branch in
  # `compute_call` was TOTAL over a closed set: "not Bash" meant `Skill`, both names exact,
  # both deliveries measured. `mcp__.*` is a PATTERN, so the set stopped being closed and
  # stopped being enumerable from the matcher. And the matcher's anchoring rule is NOT
  # established -- `^Ba` fired on `Bash` where `Ba` did not, which
  # docs/CLAUDE-CODE-BEHAVIOR.md records as explained by neither a whole-string match nor a
  # plain search. If `Bash` is anchored only at the front, `BashOutput` is a real tool name
  # that matcher delivers, and
  # `norm_structured` would key it as though it were a Skill. That has NOT been observed
  # and is not claimed here. It is the reason this script now names its own inputs instead
  # of inferring them from a matcher whose semantics nobody here has measured.
  #
  # Written as `[ ]` tests rather than a `case`, for the reason spelled out above
  # `--eligible-of`: tests/test_repeat_gate.py::WiringTest fails the file on any `case`
  # over `$tool` outside a comment.
  if [ "$event" != "PreToolUse" ] \
     && [ "$tool" != "Bash" ] && [ "$tool" != "Skill" ] \
     && [ "${tool#mcp__}" = "$tool" ]; then exit 0; fi

  # THE EMPTINESS TEST IS INSIDE THE `if` AND NOT ON THE ASSIGNMENT LINE, and that is
  # load-bearing twice over. An ABSENT tool_use_id must stay absent -- the lesson gate
  # declines to claim without one, and an unclaimed deny is emitted twice under the
  # double delivery -- so this may not fold empty into `_` the way the guard below does
  # for a `.`. And the one-line `[ -n "$tuid" ] && tuid="$(...)"` shape it replaces is
  # unreadable to tests/test_script_wrapping.py, which is what checks that every id used
  # as a path component carries the `.`/`..` guard on the line after its sanitiser.
  if [ -n "$tuid" ]; then
    tuid="$(printf '%s' "$tuid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
    case "$tuid" in ''|.|..) tuid=_ ;; esac
  fi

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

# REACHED BY EVERY `Skill` CALL, and since 2026-09-03 by every `mcp__*` one the platform
# delivers, and this stanza said the opposite until 2026-08-27. The
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
# THE MCP ROUTE IS NOW WIRED AND STILL UNMEASURED: the two learning events carry
# `mcp__.*` as of 2026-09-03, but `mcp__.*` reaching a real MCP tool has never been observed
# here, so what arrives on it is unproven. The matcher lives in TWO FILES and is TWO STRINGS
# -- `REPEAT_LEARN_MATCHER` and `REPEAT_PRE_MATCHER` in skill_compounder/installer.py, and
# the three matchers in hooks/hooks.json -- and the two files must agree per event, which
# tests/test_plugin.py compares positionally.
norm_structured() {
  printf '%s' "$payload" \
    | jq -Sc '.tool_input // {}' 2>/dev/null \
    | mask_call_paths \
    | mask_ints \
    | squeeze \
    | cut -c1-400
}

# ------------------------------------------------------------------- content tokens
# The token set of an ALREADY-NORMALISED call, for cross-tool recovery. See CROSS-TOOL
# RECOVERY in the header for what a token is and why the placeholders need no rule of
# their own. Output is space-separated with a trailing space and no leading one, sorted
# and unique, so the membership test below can be a single glob.
toks_of() {
  printf '%s' "$1" \
    | tr -c 'A-Za-z0-9_' '\n' \
    | tr 'A-Z' 'a-z' \
    | awk 'length($0) >= 3 && $0 !~ /^[0-9]+$/' \
    | sort -u \
    | head -60 \
    | tr '\n' ' '
}

# How many of $2's tokens are in $1's set. $1 is the haystack WITH a leading and a
# trailing space; $2 is a plain space-separated list.
#
# NO FORKS AND NO `for t in $2`. bash 3.2 has no associative arrays, so the obvious
# implementations are a `grep -f` per pending line -- a process start on the recovery
# path for every armed failure a busy session is carrying -- or an unquoted expansion in
# a `for`, which is a globbing hazard even where the token alphabet forbids it. Peeling
# the list apart with parameter expansion is neither.
overlap_count() {
  oc_n=0
  oc_rest="$2"
  while [ -n "$oc_rest" ]; do
    oc_rest="${oc_rest# }"
    [ -z "$oc_rest" ] && break
    oc_t="${oc_rest%% *}"
    oc_rest="${oc_rest#"$oc_t"}"
    case "$1" in *" $oc_t "*) oc_n=$(( oc_n + 1 )) ;; esac
  done
  printf '%s' "$oc_n"
}

# ---------------------------------------------------------------- head and arguments
# THE SECOND WAY A SHELL'S SAME-TOOL BINDING CAN BE EARNED. See A TWO-CHARACTER PROGRAM
# HAS NO TOKENS in the header for what it is for and what it was measured to add. Splits
# an ALREADY-NORMALISED, one-lined command into two globals:
#
#   hd_head   the first segment's head word -- the program being run -- or empty
#   hd_args   that segment's non-flag argument words, space-delimited AND space-wrapped
#             so `overlap_count`'s glob membership test reads it unchanged
#
# THE WALK STOPS AT THE FIRST SHELL OPERATOR, which is what keeps this rule about ONE
# command rather than about a pipeline: `cd <P>/x && rm -rf .` and `cd <P>/y && ls .` must
# not bind on the `.` that belongs to two different programs. Stopping early can only
# SHRINK the argument set, so every misjudgement this walk can make costs a binding rather
# than inventing one -- the direction the whole gate errs in.
#
# A BARE MASK IS NOT AN ARGUMENT. `<N>`, `<S>` and `<P>` are what the normaliser writes
# where an integer, a quoted string and a directory used to be, so two commands sharing
# one share nothing: `gh issue view <N>` and `gh run view <N>` would otherwise bind on a
# number neither of them contains any more. The masks are stripped from the word before
# the operator test, so `<P>build.py` reads as the argument it is while `<N>>&<N>` -- what
# `2>&1` normalises to -- reads as the redirect it is and ends the segment.
head_args_of() {
  hd_head=""; hd_args=" "; ha_skip=0; ha_cd=0
  ha_rest="$1"
  while [ -n "$ha_rest" ]; do
    ha_rest="${ha_rest# }"
    [ -z "$ha_rest" ] && break
    ha_w="${ha_rest%% *}"
    ha_rest="${ha_rest#"$ha_w"}"
    # The word with every bare mask removed, used ONLY for the operator test and for the
    # emptiness test below. `$ha_w` itself is what is compared and stored.
    ha_b="$ha_w"
    while :; do
      case "$ha_b" in
        *'<N>'*) ha_b="${ha_b%%'<N>'*}${ha_b#*'<N>'}" ;;
        *'<S>'*) ha_b="${ha_b%%'<S>'*}${ha_b#*'<S>'}" ;;
        *'<P>'*) ha_b="${ha_b%%'<P>'*}${ha_b#*'<P>'}" ;;
        *) break ;;
      esac
    done
    case "$ha_b" in
      *';'*|*'|'*|*'&'*|*'('*|*')'*|*'{'*|*'}'*|*'<'*|*'>'*)
        # THE ONE SEPARATOR THE WALK CROSSES is the one after a `cd` that has not yet
        # produced a head: `cd <P>/x && <program> ...` is one operation with a preamble,
        # and it is the dominant shape on this machine. Every other separator ends the
        # segment, so the rule stays about ONE command and `cd <P>/x && rm -rf .` cannot
        # bind `cd <P>/x && ls -la .` on the `.` that belongs to two different programs.
        if [ -z "$hd_head" ] && [ "$ha_cd" = "1" ]; then ha_cd=0; ha_skip=0; continue; fi
        break ;;
    esac
    if [ -z "$hd_head" ]; then
      # A leading `VAR=value` is not the program. `env` IS one, and is left alone here for
      # the same reason `segment_head` treats it as a head: naming it would be a rule about
      # one spelling, and this rule already errs toward binding nothing.
      case "$ha_w" in *=*) continue ;; esac
      # `cd` NAMES NO OPERATION, AND ON THE LIVE STORE THAT WAS THE WHOLE OF THE COST. It
      # is the same objection `shell_tool()` raises against `Bash` one level down: a
      # command whose head is `cd` says only where it ran, so two of them bind on a
      # working directory. Every one of the four bindings this rule added to the live
      # store of 2026-09-05 before this clause had head `cd`, and all four were wrong --
      # three sharing `<P>/scratchpad` or `<P>/proj` and one sharing `echo`. So `cd` and
      # its destination are STEPPED OVER rather than refused, and the head is the program
      # that runs after it. Stepping over keeps the dominant shape on this machine --
      # `cd <P>/x && <program> ...` -- inside the rule, where refusing `cd` outright would
      # have put every such command outside it.
      if [ "$ha_skip" = "1" ]; then ha_skip=0; continue; fi
      case "$ha_w" in cd|pushd) ha_skip=1; ha_cd=1; continue ;; popd) ha_cd=1; continue ;; esac
      hd_head="$ha_w"
      continue
    fi
    case "$ha_w" in -*) continue ;; esac
    [ -z "$ha_b" ] && continue
    case "$hd_args" in *" $ha_w "*) ;; *) hd_args="$hd_args$ha_w " ;; esac
  done
}

# Does the head-and-argument rule bind these two normalised calls? $1 the failed one, $2
# the one that just succeeded. Both heads must be the SAME PROGRAM and the two must share
# at least one non-flag argument word. Returns 0 when it binds.
#
# NO FORKS: this runs for every armed failure the token rule did not already bind, which on
# a busy session is every pending line on every successful call.
head_arg_bind() {
  head_args_of "$1"; hab_h="$hd_head"; hab_a="$hd_args"
  [ -z "$hab_h" ] && return 1
  head_args_of "$2"
  [ "$hab_h" = "$hd_head" ] || return 1
  # One shared word is enough because the heads already agree; `overlap_count` counts the
  # rest for nobody, so the test stops at the first hit.
  hab_rest="$hd_args"
  while [ -n "$hab_rest" ]; do
    hab_rest="${hab_rest# }"
    [ -z "$hab_rest" ] && break
    hab_t="${hab_rest%% *}"
    hab_rest="${hab_rest#"$hab_t"}"
    case "$hab_a" in *" $hab_t "*) return 0 ;; esac
  done
  return 1
}

# WHICH TOOLS THE TOOL NAME IS EVIDENCE ABOUT, and the only place that decides it. See
# THE SAME-TOOL RULE IS NOT EVIDENCE FOR A SHELL in the header: `Bash` names no operation,
# so its same-tool binding is content-tested; every other tool name does, so it is not.
shell_tool() { [ "$1" = "Bash" ]; }

# ONE LINE, so it can travel through the pending file's US-separated record. The error
# head is deliberately multi-line where it is stored in the row; here it is a label in a
# sentence and its newlines would end the record.
oneline() { printf '%s' "$1" | tr '\n\t' '  ' | squeeze; }

# RS (0x1e), the one control byte the pending record does not already spend: US (0x1f)
# separates its fields and the newline terminates its rows.
LESSON_RS=$'\036'

# THE ERROR HEAD WITH ITS LINE STRUCTURE INTACT, and that is the whole of the difference
# from `oneline` above. A Python traceback names the class of the failure on its LAST line,
# and one-lining the head threw that boundary away before anything could look for it -- see
# THE ERROR IS A FIRST LINE AND A LAST LINE below for the real statement that cost.
errline() { printf '%s' "$1" | tr '\t' ' ' | tr '\n' "$LESSON_RS"; }

# Truncation that SAYS SO. $1 the text, $2 the budget. A field that was cut and a field
# that ended look identical without the ellipsis, and a reader who cannot tell them apart
# reads a truncated command as the whole command -- which is exactly how a statement of
# 2026-09-05 reported two different calls as the same one.
#
# `cut -c` counts characters under a UTF-8 locale and bytes otherwise (docs/DESIGN.md,
# shell portability traps). That is why this function's budget is a SHAPE and the byte cap
# is enforced once, by measurement, over the assembled block.
cap() {
  cap_s="$(printf '%s' "$1" | cut -c1-"$2")"
  if [ "$cap_s" = "$1" ]; then printf '%s' "$cap_s"; else printf '%s…' "$cap_s"; fi
}

# THE COMMON LEADING WORDS OF TWO CALLS, and each one's tail from the first word where
# they differ. Sets `sc_pre`, `sc_a` and `sc_b`.
#
# WORD-WISE AND NOT CHARACTER-WISE, for two reasons. A divergence reported in the middle of
# a token tells a reader less than one reported at the argument that changed; and there is
# no portable way to index a string of glyphs (docs/DESIGN.md), while there is a portable
# way to peel a word off the front of one.
split_common() {   # $1 failed, $2 worked
  sc_pre=""; sc_a="$1"; sc_b="$2"
  while [ -n "$sc_a" ] && [ -n "$sc_b" ]; do
    sc_wa="${sc_a%% *}"; sc_wb="${sc_b%% *}"
    [ "$sc_wa" = "$sc_wb" ] || break
    case "$sc_a" in *" "*) sc_a="${sc_a#* }" ;; *) sc_a="" ;; esac
    case "$sc_b" in *" "*) sc_b="${sc_b#* }" ;; *) sc_b="" ;; esac
    sc_pre="$sc_pre$sc_wa "
  done
}

# THE ERROR IS A FIRST LINE AND A LAST LINE, because a traceback puts the answer on the
# last one. A real statement of 2026-09-05 read
#
#   error:   Exit code 1 Traceback (most recent call last): File "/private/tmp/clau
#
# -- three lines joined into one by `oneline` and then cut at 70 characters, so the
# `ImportError:` naming what was actually wrong never reached the session it was written
# for. The lines arrive RS-separated from `errline`; a head carrying no RS is one line and
# is printed once rather than as `x … x`. A pending file written by an OLDER version
# carries a space-joined head, which has no RS either and reads as that single line: the
# old behaviour, for the one session such a file can live.
lesson_error() {
  le_first=""; le_last=""; le_rest="$1"
  while [ -n "$le_rest" ]; do
    case "$le_rest" in
      *"$LESSON_RS"*) le_l="${le_rest%%"$LESSON_RS"*}"; le_rest="${le_rest#*"$LESSON_RS"}" ;;
      *) le_l="$le_rest"; le_rest="" ;;
    esac
    le_l="${le_l# }"; le_l="${le_l% }"
    [ -z "$le_l" ] && continue
    [ -z "$le_first" ] && le_first="$le_l"
    le_last="$le_l"
  done
  if [ -z "$le_first" ]; then
    :
  elif [ "$le_first" = "$le_last" ]; then
    cap "$le_first" 200
  else
    printf '%s … %s' "$(cap "$le_first" 100)" "$(cap "$le_last" 100)"
  fi
}

# THE ONE PLACE THAT KNOWS THE BYTE COUNT. Every budget above is in `cut -c` units, which
# are characters under a UTF-8 locale and bytes otherwise, so a block of multibyte glyphs
# can pass every field budget and still run past the cap. This measures what was actually
# assembled and shrinks it until it fits, and it is where the stated cap becomes true.
#
# `wc -c` PADS ITS COUNT WITH LEADING SPACES ON BSD, which is the defect that made
# CLAIM_GATE_MAX_BYTES dead code for the life of that constant: a numeric guard read the
# space as non-numeric and zeroed the value. `tr -cd '0-9'` is the fix and the `case` is
# the belt, here as there.
fit_bytes() {   # $1 text, $2 byte budget -> stdout
  fb_s="$1"; fb_i=0
  while [ "$fb_i" -lt 4 ]; do
    fb_n="$(printf '%s' "$fb_s" | wc -c | tr -cd '0-9')"
    case "$fb_n" in ''|*[!0-9]*) break ;; esac
    [ "$fb_n" -le "$2" ] && break
    fb_c="$(printf '%s' "$fb_s" | wc -m | tr -cd '0-9')"
    case "$fb_c" in ''|*[!0-9]*|0) break ;; esac
    fb_c=$(( fb_c * ( $2 - 8 ) / fb_n ))
    [ "$fb_c" -lt 40 ] && fb_c=40
    fb_s="$(printf '%s' "$fb_s" | cut -c1-"$fb_c")…"
    fb_i=$(( fb_i + 1 ))
  done
  printf '%s' "$fb_s"
}

# DID THE RECOVERY WRITE OR RUN A SCRIPT, AND WHICH ONE. Answers with a path, with the
# literal placeholder when a script is certain and its path is not, or with nothing at all.
# See AND WHEN THE RECOVERY WAS A SCRIPT in the header for why the answer exists.
#
# IT READS THE NORMALISED COMMAND, not the raw one, and that is what makes the "outside
# quotes" rule free: rule 3 of the normaliser has already collapsed every quoted literal to
# `<S>`, so a `>` or a `fix.sh` inside an argument is gone before this function sees it.
# What it concedes with the same stroke is a script written from inside a KEPT program
# (`python3 -c "...open('f.sh','w')..."`, which normalises to `<C:...>`): those bytes
# survive, but no rule below can fire on them, because `-c` is neither a bare `-` nor a
# script path. Silence, which is the direction this whole gate errs in.
#
# FOUR SHAPES FIRE, and each is a narrowing of one alternative in `mutates_file()`:
#   a. a redirect whose target ends in a script extension -- `cat > x.sh`, and a heredoc
#      into a file is this shape with a `<<` in front of it.
#   b. an interpreter handed a script path or a bare `-` (a heredoc or a pipe into stdin):
#      `bash x.sh`, `python3 x.py`, `python3 - <<EOF`. NOT `python3 -m pytest`, which runs
#      a module, and not `bash -c`, which is the concession above.
#   c. a script path AT THE HEAD OF A SEGMENT, which is `./fix.sh` -- the commonest shape
#      of all and the one this function missed in its first draft, because a file made
#      executable is run by its own name and no interpreter appears anywhere in the line.
#      THE HEAD IS LOAD-BEARING: `grep -n foo fix.sh` names the same file in an argument
#      slot and reads it rather than running it, so a rule matching a script path ANYWHERE
#      would report every `wc -l build.py` as a script the session ran.
#   d. `chmod +x`, which is a file being made runnable and is never anything else.
# A `> notes.md` fires NONE of them, on purpose: the sentence this decides is "the recovery
# ran a script", and a heredoc into prose would make that sentence false.
script_attach() {   # $1 normalised recovery command -> path, placeholder, or empty
  printf '%s' "$1" | grep -qE \
    '>[[:space:]]*[^[:space:];&|>]*\.(sh|py|js|rb|pl)([^A-Za-z0-9_.]|$)|(^|[[:space:];&|(])(bash|sh|zsh|python|python2|python3|node|ruby|perl)[[:space:]]+(-[[:space:]]|-$|[^[:space:];&|]*\.(sh|py|js|rb|pl)([^A-Za-z0-9_.]|$))|(^|[;&|(][[:space:]]*)[^[:space:];&|]*\.(sh|py|js|rb|pl)([^A-Za-z0-9_.]|$)|(^|[[:space:];&|(])chmod[[:space:]]+([^[:space:]]+[[:space:]]+)*\+x' \
    || return 0
  # THE PATH IS A WHOLE TOKEN OR IT IS NOTHING. `<P>/fix.sh` carries a real basename and a
  # directory that was masked BECAUSE it varies between machines, so the tail alone
  # (`/fix.sh`) is a path that would not open -- which is worse than saying nothing. A
  # token holding `<`, `>` or `$` is a mask or an unexpanded variable and is skipped for
  # the same reason; so is a flag, and so is anything over 80 characters, which is not a
  # path a person is going to read back off one line.
  sa_p="$(printf '%s' "$1" | tr ' ' '\n' \
            | grep -E '^[^<>$-][^<>$]*\.(sh|py|js|rb|pl)$' | head -1)"
  [ "${#sa_p}" -gt 80 ] && sa_p=""
  if [ -n "$sa_p" ]; then printf '%s' "$sa_p"; else printf '%s' "<path to the script>"; fi
}

# THE FACTS the recovery arm emits and the lesson gate quotes back, built in one place and
# stored ONCE in the marker file, so the two can never say different things about which
# call failed or which one worked.
#
# THE STATEMENT IS UNDER 1200 BYTES, and that is a MEASURED cap rather than the sum of the
# field budgets: `fit_bytes` weighs what was actually assembled, because `cut -c` counts
# characters under a UTF-8 locale and bytes otherwise. tests/test_repeat_gate.py drives it
# with input that saturates both normalisers rather than trusting this sentence.
#
# THE BUDGET IS 1200 MINUS THE TAIL, AND THE TAIL IS MEASURED TOO. It used to be the
# constant 950, which held while the command block was a fixed six lines; it stopped
# holding the day that block grew a conditional `--attach` clause and a closing line, and a
# constant that is right for one of two shapes is a cap that is wrong for the other. The
# tail is built and weighed by `facts_budget` before the facts are, so the assembled
# statement is under 1200 whichever shape it took -- and the facts shrink rather than the
# commands, because a truncated command is a command nobody can run.
#
# IT WAS 90 CHARACTERS A COMMAND AND 70 FOR THE ERROR UNTIL 2026-09-05, and two real
# statements that day are why it is not. A statement is delivered ONCE per signature per
# session, so those budgets were buying nothing and costing the whole content of the arm:
#
#   THE TWO COMMANDS CAME OUT IDENTICAL. A long `failed:` and a long `worked:` were both
#   cut at 90 characters into the same bytes, ending `--output wa`, while the change the
#   recovery was ABOUT -- `--strategy incremental` becoming `--strategy full` -- sat past
#   the cut. The arm reported a call recovering itself. So the budgets are raised, a field
#   that was cut now says so with a visible ellipsis, and where the two truncations would
#   still be identical the shared head is stated ONCE on a `both:` line and each call is
#   quoted FROM THE WORD WHERE THEY DIVERGE.
#
#   THE ERROR LOST ITS EXCEPTION. `error:` was a `head -3` joined into one line and cut at
#   70 characters, which on a Python traceback reads
#     Exit code 1 Traceback (most recent call last): File "/private/tmp/clau
#   -- three lines of banner and no `ImportError:` at all. The error now carries its LINE
#   STRUCTURE through the pending record (`errline`) and is quoted as `first … last` when
#   those differ; the LEARN arm fetches the last non-empty line separately, because
#   `head -3` had already thrown it away.
#
# THE FACTS ARE SHARED; THE COMMAND BLOCK IS NOT, and that split is the whole of the
# 2026-09-04 change. The statement names both commands, because a person reading their
# own session's transcript is entitled to know that `skillrepeat dismiss` exists. The DENY
# names only the one a session can act on. What is quoted back byte for byte is the part
# that could otherwise disagree, which was never the command list.
lesson_facts() {   # $1 failed norm, $2 err (RS lines), $3 what worked, $4 byte budget
  ls_e="$(lesson_error "$2")"
  ls_f="$(cap "$1" 220)"
  ls_w="$(cap "$3" 220)"
  if [ "$ls_f" = "$ls_w" ] && [ "$1" != "$3" ]; then
    # THE TWO CALLS SURVIVED TRUNCATION AS THE SAME LINE, and that is not a cosmetic
    # defect: a statement of 2026-09-05 quoted a `failed:` and a `worked:` that were byte
    # for byte identical, both ending `--output wa`, while the change the recovery was
    # ABOUT -- `--strategy incremental` becoming `--strategy full` -- sat past the cut. The
    # arm reported a call recovering itself. So where the head is shared it is stated ONCE
    # and each call is quoted FROM THE WORD WHERE THEY DIVERGE, which is the only part of
    # either one a reader needs in order to see what changed.
    split_common "$1" "$3"
    ls_body="  both:    $(cap "$sc_pre" 200)
  failed:  …$(cap "$sc_a" 200)
  error:   $ls_e
  worked:  …$(cap "$sc_b" 200)"
  else
    ls_body="  failed:  $ls_f
  error:   $ls_e
  worked:  $ls_w"
  fi
  # WHATEVER IS LEFT OF 1200 ONCE THE COMMAND BLOCK HAS BEEN WEIGHED -- `facts_budget`,
  # above -- with 950 the ceiling and the default for a caller that passes nothing. The
  # number is enforced, not asserted (see `fit_bytes`), and tests/test_repeat_gate.py
  # measures the assembled statement against saturating input in both shapes rather than
  # trusting this sentence.
  fit_bytes "A call that failed in this session has since succeeded a different way, and
the store recorded that as its recovery.

$ls_body

No lesson references this signature yet." "${4:-950}"
}

# EVERYTHING THE STATEMENT ADDS AFTER THE FACTS, in one function because two callers need
# its LENGTH before either needs its text: `facts_budget` weighs it, and `lesson_statement`
# prints it. Building it twice in two places is how the two would come to disagree about a
# byte count nobody would ever see disagree.
#
# FACT ONLY, and every label is a fact too: a model that runs `skillrepeat dismiss` writes
# `actor:"model"` and lifts nothing (WHO MAY DISMISS in the header); `--attach` copies a
# file; `skillnote skill` makes a note callable. An imperative here is both ignored and
# misleading about who is asking (PLATFORM FACTS 4).
lesson_tail() {   # $1 sig, $2 attach (empty = the recovery ran no script)
  lt_a=""
  [ -n "$2" ] && lt_a=" --attach $2"
  printf '%s' "
A lesson lifts it:
  skillnote add --lesson $1 \"<what was learned>\"$lt_a
  skillrepeat dismiss $1 --why \"<why>\"  (a person at a terminal only)"
  [ -n "$2" ] && printf '%s' "
The recovery ran a script; --attach copies it beside the note so the next session can call it."
  printf '%s' "
A note that should be callable as a tool becomes one with: skillnote skill <note id> --name <slug>"
}

# THE BYTE BUDGET THE FACTS GET, which is 1200 less what the tail above will cost. 1190
# rather than 1200 leaves the slack `fit_bytes` needs to land under rather than on the cap,
# 950 is the ceiling the facts had when the tail was fixed, and 300 is the floor: below
# that the facts stop naming both calls, and a statement that cannot say what worked is not
# worth emitting at any length.
facts_budget() {   # $1 sig, $2 attach -> a byte budget for lesson_facts
  fb_t="$(lesson_tail "$1" "$2" | wc -c | tr -cd '0-9')"
  case "$fb_t" in ''|*[!0-9]*) fb_t=500 ;; esac
  fb_b=$(( 1190 - fb_t ))
  [ "$fb_b" -gt 950 ] && fb_b=950
  [ "$fb_b" -lt 300 ] && fb_b=300
  printf '%s' "$fb_b"
}

# THE STATEMENT: the facts, then the tail.
lesson_statement() {   # $1 sig, $2 facts, $3 attach
  printf '%s' "$2$(lesson_tail "$1" "${3:-}")"
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
    # Reached by every `Skill` call and every `mcp__*` one; see the stanza above
    # norm_structured. Any other tool left at the shape test above, so this branch is
    # never handed a payload it has no rule for.
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

# THE NAME OF THE PENDING FILE, AND NOTHING ELSE. Sets `akey` -- `<sid>` for the parent,
# `<sid>+<agent id>` inside a dispatched agent -- for the two arms that arm and consume a
# recovery window. The reasoning is THE RECOVERY WINDOW IS KEYED ON (SESSION, AGENT) in
# the header; the two things to keep here are that `+` is outside the identity class both
# halves are sanitised into, so the two shapes cannot collide, and that the parent's key
# is the OLD name unchanged.
#
# CALLED FROM THE TWO POST ARMS ONLY, never on the PreToolUse path. The refusal is per
# session by design and needs no agent, and this costs two program starts (`tr`, `cut`)
# that tests/test_repeat_gate.py::ProcessCountTest pins the not-armed path against.
# A parent pays none of them: the sanitiser runs only when `agent_id` was non-empty, the
# same shape the `tool_use_id` guard above uses and for the same reason.
agent_key() {
  akey="$sid"
  [ -z "${aid:-}" ] && return 0
  asafe="$(printf '%s' "$aid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
  case "$asafe" in ''|.|..) asafe=_ ;; esac
  akey="$sid+$asafe"
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

# prune_lessons: the per-session lesson markers the RECOVER arm writes, swept from the
# LEARN arm for the same reason prune_claims is -- a session that never fails never
# starts this tree, so no arm that cannot create it has to pay for it. These are FILES
# under `lessons/<sid>/` and a `deny/<sig>/<tuid>` tree beside them, so the sweep takes
# two shapes where prune_claims takes one.
prune_lessons() {
  find "$DIR/lessons" -mindepth 2 -type f -mtime +2 -exec rm -f {} + 2>/dev/null
  find "$DIR/lessons" -mindepth 2 -depth -type d -mtime +2 -exec rmdir {} + 2>/dev/null
  find "$DIR/lessons" -mindepth 1 -maxdepth 1 -type d -mtime +2 -empty \
    -exec rmdir {} + 2>/dev/null
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

  # `agent_id` IS ALWAYS PRESENT AND IS null FOR THE PARENT, rather than absent there.
  # It is the key half the row would otherwise not record, so a reader asking which agent
  # a failure belongs to can answer it off the store instead of guessing from the session.
  # `cross_tool` on the recover row goes the other way -- written only when true -- and
  # the difference is that this one is a KEY and that one is a claim about evidence.
  row="$(jq -nc --arg ts "$now" --arg sig "$sig" --arg ck "$ck" --arg ec "$ecl" \
    --arg tool "$tool" --arg norm "$norm" --arg cmd "$cmd" --arg err "$err_head" \
    --arg session "$sid" --arg tuid "$tuid" --arg aid "${aid:-}" \
    '{t:"fail", ts:($ts|tonumber), sig:$sig, ck:$ck, ec:$ec, tool:$tool, norm:$norm,
      cmd:$cmd, err:$err, session:$session, tuid:$tuid,
      agent_id:(if $aid == "" then null else $aid end)}' 2>/dev/null)" || exit 0
  [ -z "$row" ] && exit 0
  rotate_store
  printf '%s\n' "$row" >> "$STORE" 2>/dev/null || exit 0

  # Arm the recovery window for THIS SESSION AND THIS AGENT -- `agent_key` names the
  # file, and the header section THE RECOVERY WINDOW IS KEYED ON (SESSION, AGENT) says
  # why the session alone was not enough. US (0x1f) rather than a tab: tab is IFS
  # whitespace, so `read` collapses runs of it and an empty field silently shifts every
  # field after it (docs/DESIGN.md, shell portability traps).
  #
  # SEVEN FIELDS SINCE 2026-09-03, and the three new ones are all carried so that the
  # RECOVER arm never has to read the store. Its tokens are what cross-tool binding
  # compares against; the failed shape and the error head are what the statement it emits
  # quotes, and re-deriving those from the store would put a whole-file parse on the
  # success path of every armed session. A pending file written by an OLDER version has
  # four fields, so the three read back empty: no cross-tool binding and no statement,
  # which is the safe direction for a file that lives one session.
  #
  # THE LAST NON-EMPTY LINE OF THE ERROR TRAVELS WITH IT, and the `head -3` above is
  # exactly why it has to be fetched separately. A Python traceback spends its first three
  # lines on `Exit code 1`, the `Traceback (most recent call last):` banner and the first
  # stack frame; the line that says WHAT went wrong is the LAST one. On 2026-09-05 a real
  # statement quoted those three, cut them at 70 characters, and lost the `ImportError:`
  # that was the whole content of the failure.
  #
  # THE ROW'S `err` FIELD IS LEFT ALONE. It is a display field two CLIs already print, and
  # widening it would change every stored row to repair a statement. Only the pending
  # record -- which lives one session and feeds nothing but the statement -- carries the
  # tail. `tail -40` bounds the scan: an error can be megabytes, and a last line worth
  # quoting is never 40 lines from the end of one.
  err_last="$(printf '%s' "$err_raw" | tail -40 | grep -v '^[[:space:]]*$' | tail -1 \
               | cut -c1-200)"
  err_rec="$err_head"
  [ -n "$err_last" ] && err_rec="$err_head
$err_last"
  agent_key
  pf="$DIR/pending/$akey"
  printf '%s\037%s\037%s\037%s\037%s\037%s\037%s\n' \
    "$sig" "$ck" "$tool" "$WINDOW" "$(toks_of "$norm")" "$(oneline "$norm")" \
    "$(errline "$err_rec")" >> "$pf" 2>/dev/null || :
  # A session that fails hundreds of times must not grow this without bound; the oldest
  # armed failures are also the ones whose window has long since run out.
  if [ "$(wc -l < "$pf" 2>/dev/null | tr -cd '0-9')" -gt 200 ] 2>/dev/null; then
    tail -50 "$pf" > "$pf.tmp.$$" 2>/dev/null && mv "$pf.tmp.$$" "$pf" 2>/dev/null || :
  fi
  prune_claims
  prune_denied
  prune_lessons
  exit 0
fi

# ==================================================================== arm 2: RECOVER
# The first later success BY THE SAME AGENT to satisfy EITHER rule, within a window of
# REPEAT_RECOVERY_WINDOW successful calls of any tool THIS HOOK IS WIRED FOR, is that
# signature's candidate recovery: the same TOOL, or a different tool sharing
# REPEAT_RECOVERY_MIN_TOKENS content tokens with the failed call (CROSS-TOOL RECOVERY in
# the header). One binding per armed failure whichever rule found it, and the row says
# which. The wiring on this event is `Bash|Skill|mcp__.*` (see WHAT THE WIRING ADMITS),
# so the window is spent by Bash, Skill and MCP successes and by nothing else: twenty Reads
# between the failure and the fix consume none of it. The window is what stops an unrelated command twenty steps later from being
# recorded as the fix; the plurality rule in the refusal arm is what stops a single wrong
# candidate from being announced as one. Neither is a guess about intent -- both are
# bounds on how much noise one session may contribute.
if [ "$event" = "PostToolUse" ]; then
  # The pending file of THIS agent, not of this session: a success inside a dispatched
  # agent may not bind a failure its parent armed, nor the other way round. `agent_key`
  # is two program starts inside an agent and none in a parent, and it runs before the
  # `-f` test because the test is what it names.
  agent_key
  pf="$DIR/pending/$akey"
  [ -f "$pf" ] || exit 0
  compute_call || exit 0
  claim_once "s" || exit 0

  : > "$TMP/pending.new" 2>/dev/null || exit 0
  # Both computed at most once, and only if a pending line actually needs them: a session
  # whose every binding is a non-shell same-tool one pays no extra process at all.
  ctoks=""; ctoks_done=0
  snorm=""; snorm_done=0
  # ONE ROW PER SIGNATURE PER SUCCESS. N failures of one signature arm N SEPARATE pending
  # lines, and one success binds every one of them -- which wrote N BYTE-IDENTICAL
  # `recover` rows, four of them under a single tool_use_id on the live store of
  # 2026-09-03. The pending lines are still consumed one at a time, because each really is
  # a separate armed failure; what is de-duplicated is the ROW, so `(sig, tuid)` is unique
  # in the store and a reader counting rows counts recoveries rather than arming events.
  # `claim_once` above handles the OTHER duplicate, the one both wirings deliver; this one
  # is inside a single event and no claim can see it.
  #
  # A signature is matched as a QUOTED case pattern, so a foreign pending line carrying a
  # glob character is compared literally rather than matched as a pattern.
  done_sigs=" "
  # The first binding of this event, kept for the statement below. `read` runs in this
  # shell -- the loop is fed by a redirection and not a pipe -- so what it sets survives.
  bound_sig=""; bound_bsig=""
  ldir="$DIR/lessons/$sid"
  while IFS=$'\037' read -r psig pck ptool prem ptoks pfnorm pferr; do
    [ -z "${psig:-}" ] && continue
    case "${prem:-}" in ''|*[!0-9]*) continue ;; esac
    [ "$prem" -gt 0 ] || continue
    bind=""; hbind=""
    if [ "${ptool:-}" = "$tool" ]; then
      # THE SAME-TOOL RULE IS NOT EVIDENCE FOR A SHELL (header). For `Bash` the tool
      # matching means nothing, so the content test the cross-tool rule uses is applied
      # here too -- with the exact self-recovery carved out, since the refusal arm's
      # self-recovery exclusion is built on those rows and `pwd` carries one token.
      if ! shell_tool "$tool" || [ "$SAME_TOKENS" -le 0 ]; then
        bind="same"
      else
        if [ "$snorm_done" = "0" ]; then snorm="$(oneline "$norm")"; snorm_done=1; fi
        if [ -n "${pfnorm:-}" ] && [ "$pfnorm" = "$snorm" ]; then
          bind="same"
        else
          if [ -n "${ptoks:-}" ]; then
            if [ "$ctoks_done" = "0" ]; then ctoks=" $(toks_of "$norm")"; ctoks_done=1; fi
            if [ "$(overlap_count "$ctoks" "$ptoks")" -ge "$SAME_TOKENS" ]; then bind="same"; fi
          fi
          # A TWO-CHARACTER PROGRAM HAS NO TOKENS (header). The token rule above cannot
          # see `ls --nonexistent-flag .` recovered by `ls -la .` -- `ls` is two characters
          # and every other shared word is a flag or a `.` -- so the head-and-argument rule
          # is the SECOND way the same binding can be earned. It is tried only where the
          # token rule found nothing, and the row records which rule found it, because a
          # measurement that cannot separate the two cannot be re-run.
          if [ -z "$bind" ] && [ "$HEAD_ARG" = "1" ] && [ -n "${pfnorm:-}" ] \
             && head_arg_bind "$pfnorm" "$snorm"; then
            bind="same"; hbind="head"
          fi
        fi
      fi
    elif [ -n "${ptoks:-}" ] && [ "$MIN_TOKENS" -gt 0 ]; then
      if [ "$ctoks_done" = "0" ]; then ctoks=" $(toks_of "$norm")"; ctoks_done=1; fi
      if [ "$(overlap_count "$ctoks" "$ptoks")" -ge "$MIN_TOKENS" ]; then bind="cross"; fi
    fi
    if [ -n "$bind" ]; then
      case "$done_sigs" in
        *" $psig "*) ;;   # this success already recorded a recovery for this signature
        *)
          # `cross_tool` is written only when it is true. An absent field and a `false` one
          # read the same through jq's `//`, and the store is read by three programs; a key
          # that appears on every row to say `no` is a key every one of them has to explain.
          rrow="$(jq -nc --arg ts "$now" --arg sig "$psig" --arg ck "$pck" --arg tool "$tool" \
            --arg norm "$norm" --arg cmd "$cmd" --arg session "$sid" --arg tuid "$tuid" \
            --arg x "$bind" --arg h "${hbind:-}" --arg aid "${aid:-}" \
            '{t:"recover", ts:($ts|tonumber), sig:$sig, ck:$ck, tool:$tool, norm:$norm,
              cmd:$cmd, session:$session, tuid:$tuid,
              agent_id:(if $aid == "" then null else $aid end)}
             + (if $x == "cross" then {cross_tool:true} else {} end)
             + (if $h == "head" then {head_arg:true} else {} end)' 2>/dev/null)"
          [ -n "$rrow" ] && printf '%s\n' "$rrow" >> "$STORE" 2>/dev/null
          done_sigs="$done_sigs$psig "
          # THE MARKER IS WRITTEN BESIDE THE ROW, FOR EVERY SIGNATURE THIS SUCCESS BOUND,
          # and that is the second half of the same defect. It used to be written once,
          # after the loop, for the FIRST bound signature only -- so a success that bound
          # two signatures wrote two rows and left the second invisible to the lesson gate,
          # which reads its signatures off these filenames and can never refuse one that
          # has no marker.
          #
          # AND AN EXISTING MARKER IS NEVER OVERWRITTEN. It used to be, on every later
          # binding of the same signature, while `said-` below stopped the session being
          # told a second time -- so the store held a statement naming one command and the
          # session had been told another. Observed live on 2026-09-03: the session was
          # told `TEST_TIMEOUT=... ./run_tests.sh` and the marker was rewritten to
          # `cat notes/OPEN-THREADS.md`. First binding wins, because the first binding is
          # the one the session was actually told about.
          if [ -n "${pfnorm:-}" ]; then
            bsig="$(printf '%s' "$psig" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
            case "$bsig" in ''|.|..) bsig=_ ;; esac
            if mkdir -p "$ldir" 2>/dev/null && [ ! -f "$ldir/s-$bsig" ]; then
              # THE ATTACHMENT IS DECIDED HERE, BESIDE THE FACTS, AND STORED IN ITS OWN
              # MARKER. The gate quotes the facts back byte for byte and appends a
              # DIFFERENT command block (THE FACTS ARE SHARED; THE COMMAND BLOCK IS NOT),
              # so the one thing both blocks need -- which file, if any -- has to survive
              # next to them. Recomputing it there is not an option: the gate runs on a
              # later call and has no copy of the command that recovered anything. It
              # follows the s- marker's first-binding-wins rule by sharing its guard.
              batt="$(script_attach "$norm")"
              [ -n "$batt" ] && printf '%s' "$batt" > "$ldir/a-$bsig" 2>/dev/null
              printf '%s' "$(lesson_facts "$pfnorm" "${pferr:-}" "$norm" \
                               "$(facts_budget "$psig" "$batt")")" \
                > "$ldir/s-$bsig" 2>/dev/null || :
            fi
            [ -z "$bound_sig" ] && { bound_sig="$psig"; bound_bsig="$bsig"; }
          fi
          ;;
      esac
      continue          # bound: one recovery per armed failure, then it is disarmed
    fi
    prem=$((prem - 1))
    [ "$prem" -le 0 ] && continue
    printf '%s\037%s\037%s\037%s\037%s\037%s\037%s\n' \
      "$psig" "$pck" "$ptool" "$prem" "${ptoks:-}" "${pfnorm:-}" "${pferr:-}" \
      >> "$TMP/pending.new"
  done < "$pf"

  # Rewrite next to the store, not across a filesystem: $TMP may be on another device and
  # a partial copy would leave a truncated pending file behind.
  if [ -s "$TMP/pending.new" ]; then
    cat "$TMP/pending.new" > "$pf.tmp.$$" 2>/dev/null && mv "$pf.tmp.$$" "$pf" 2>/dev/null || :
  else
    rm -f "$pf" 2>/dev/null || :
  fi

  # THE FIRST TIME: SAY IT. Everything above this line is unchanged in spirit -- a row in
  # a file nobody reads mid-session. This is the part that reaches the session that just
  # did the work, at the one moment it knows both halves.
  #
  # THE MARKER FILE IS WRITTEN WHETHER OR NOT THE STATEMENT IS EMITTED, and it is what the
  # lesson gate tests before it reads anything. It carries the statement so that gate does
  # not rebuild it from a store it would otherwise not have to open. It is written up in
  # the loop now, next to the row it belongs to, and this block only decides whether to
  # SAY it.
  [ -z "$bound_sig" ] && exit 0
  bsig="$bound_bsig"
  # ONCE PER SIGNATURE PER SESSION, claimed with mkdir so it is decided by the filesystem
  # and not by a read-then-write. The duplicate delivery both wirings produce never
  # reaches here -- claim_once above dropped it -- so what this actually bounds is a
  # SECOND, genuinely different recovery of the same signature later in the session.
  mkdir "$ldir/said-$bsig" 2>/dev/null || exit 0
  # THE FACTS ARE READ BACK OFF THE MARKER, NOT REBUILT. The file is the single copy of
  # them, so what the session is told here and what the lesson gate quotes back later are
  # the same bytes by construction rather than by two builders agreeing. That is the whole
  # of the fix for the two disagreeing about which call worked. The command block is
  # appended here and a DIFFERENT one is appended by the gate, on purpose: see THE FACTS
  # ARE SHARED; THE COMMAND BLOCK IS NOT.
  facts="$(cat "$ldir/s-$bsig" 2>/dev/null)"
  [ -z "$facts" ] && exit 0
  # READ BACK, NOT RECOMPUTED, for the reason the facts are: the marker written at the
  # first binding is the single copy, so what this says and what the gate says later cannot
  # drift. An absent a- marker is the ordinary case and means the recovery ran no script.
  stmt="$(lesson_statement "$bound_sig" "$facts" "$(cat "$ldir/a-$bsig" 2>/dev/null)")"
  [ -z "$stmt" ] && exit 0
  ( jq -nc --arg c "$stmt" \
      '{hookSpecificOutput:{hookEventName:"PostToolUse", additionalContext:$c}}' \
      > "$TMP/say.json" ) 2>/dev/null
  [ -s "$TMP/say.json" ] && cat "$TMP/say.json" 2>/dev/null
  exit 0
fi

# ==================================================================== arm 3: REFUSE
# ------------------------------------------------------------------ segments
# SPLIT BEFORE JUDGING A HEAD, because an exemption read off the first word alone is an
# exemption on `cd` that carries every command after the `&&` in with it. A red-team
# session found it unaided on its fifth attempt on 2026-09-04:
# `cd build && tar -xf ../release.tgz` was ALLOWED where the bare `tar -xf ../release.tgz`
# was denied, and `true && <anything>` is the same hole with no pretext at all.
#
# THE WALK IS hooks/doc-gate.sh's, IN BUILTINS RATHER THAN awk. `;`, `&`, `|`, `(` and `)`
# end a segment when they are OUTSIDE quotes, and quote state is tracked so a `&&` inside
# an argument -- `git commit -m "fix a && b"` -- ends nothing. `&&` and `||` produce an
# empty segment between their two breaks, which costs nothing: an empty segment has no
# head and is skipped. A NEWLINE separates two commands as surely as a `;` does, so
# newlines are folded to `;` BEFORE the walk rather than to a space, which is what this
# function used to do -- a two-line `cd build<newline>tar -xf x` read as one command whose
# head was `cd`, the same hole spelled without an operator.
#
# THE FAIL DIRECTION IS THE OPPOSITE OF doc-gate's, AND THAT IS THE WHOLE POINT OF SAYING
# SO. There a missed split costs a missed deny, which that gate tolerates by design; here
# a missed split GRANTS AN EXEMPTION, so an unsplit compound must be treated as NOT
# exempt. Concretely: when the walk cannot model the text `split_segments` FAILS, and
# every caller below refuses the exemption rather than granting it.
#
# WHAT IT DOES NOT MODEL is the pair doc-gate names: a backslash-escaped quote and
# `$'...'`. Either can leave the tracker inside a quote where the shell is not, or outside
# one where the shell is. Two things follow from the fail direction, and neither is a
# claim to model them:
#   * A WALK THAT ENDS INSIDE A QUOTE never closed, so nothing after the opening quote was
#     tested for a separator at all. The exemption is refused.
#   * A COMMAND CARRYING ONE OF THOSE SHAPES **AND** ANY SEPARATOR BYTE is refused its
#     exemption outright. That conjunction is exact rather than cautious: with no `;`,
#     `&`, `|`, `(` or `)` anywhere in the text there is ONE segment however the quotes
#     parse, so the head is unambiguous and the exemption stands -- `sed 's/\"//' f` keeps
#     it. With one present, that byte is exactly what a mis-tracked quote can hide.
#
# HEREDOC BODIES ARE STRIPPED FIRST, with hooks/doc-gate.sh's own awk pass. A body is not
# shell: `python3 - <<'PY'` followed by Python whose lines begin `import`, `print`, `def`
# yields a head per line, none of them on any list, and the exemption is refused for a
# command that is only writing a file.
#
# IT CHANGED NO VERDICT ON THE LIVE STORE AND IS KEPT ANYWAY, which is worth saying
# plainly rather than dressing up. Over the 310 distinct fail commands of 2026-09-04 the
# strip moved 0 of them, because a command writing a heredoc here is nearly always
# `python3 - <<PY` or `bash -c`, whose own head is on no list either way. What it does
# move is the shape that is exempt for a real reason -- `cd repo && cat > f <<'EOF'` with
# a `&&` or a `;` inside the body -- and that is the shape a session writing a note
# reaches for. The fork is paid for by a `case` test, so a command with no `<<` in it
# costs nothing, and this function still forks LESS than the `printf | tr | sed` pipeline
# it replaced.
#
# BOUNDED AT 400 separator-or-quote characters walked; past that the answer is "could not
# model", which is again the non-exempt direction. The cap is a literal and not a knob on
# purpose: a tunable would have to be carried into two documented tables and a doctrine
# test for a number no caller has had a reason to move.
#
# Sets SEGS to the segments, newline-separated. Returns 1 when it could not model the
# text, and SEGS is not to be read in that case.
split_segments() {
  SEGS=""
  sg_bsl='\'
  sg_sq="'"
  sg_dq='"'
  sg_t="$1"
  # THE STRIP RUNS ON THE TEXT WITH ITS NEWLINES STILL IN IT, because a heredoc body is
  # delimited by lines; the fold to `;` below is what comes after. Each heredoc ends at
  # its OWN delimiter -- starting at the first `<<` and swallowing the rest is the defect
  # hooks/claim-gate.sh's first version shipped. `<<<` is a here-STRING and opens no body,
  # so it is blanked in a same-length probe copy before the delimiter is matched. The
  # quote character reaches awk as `q` because `\047` inside an awk regex constant is not
  # portable and the program itself is single-quoted.
  case "$sg_t" in
    *'<<'*)
      sg_t="$(printf '%s' "$sg_t" | awk -v q="'" '
        BEGIN { re = "<<-?[[:space:]]*([\"][^\"]+[\"]|" q "[^" q "]+" q "|[A-Za-z_][A-Za-z0-9_]*)" }
        {
          if (inh) {
            t = $0
            if (dash) sub(/^\t+/, "", t)
            sub(/[[:space:]]+$/, "", t)
            if (t == delim) inh = 0
            next
          }
          print
          probe = $0
          gsub(/<<</, "@@@", probe)
          if (match(probe, re)) {
            spec = substr(probe, RSTART, RLENGTH)
            dash = (spec ~ /^<<-/)
            sub(/^<<-?[[:space:]]*/, "", spec)
            gsub(/"/, "", spec); gsub(q, "", spec)
            delim = spec
            inh = 1
          }
        }' 2>/dev/null)"
      # An awk that could not run leaves nothing to judge, and nothing to judge is not an
      # exemption -- the fail direction of this whole function.
      [ -n "$sg_t" ] || return 1
      ;;
  esac
  sg_t="${sg_t//$'\n'/;}"
  sg_t="${sg_t//$'\t'/ }"
  case "$sg_t" in
    *"$sg_bsl$sg_sq"*|*"$sg_bsl$sg_dq"*|*'$'"$sg_sq"*)
      case "$sg_t" in *[\;\&\|\(\)]*) return 1 ;; esac ;;
  esac
  sg_rest="$sg_t"
  sg_cur=""
  sg_n=0
  while [ -n "$sg_rest" ]; do
    sg_n=$((sg_n + 1))
    [ "$sg_n" -gt 400 ] && return 1
    # ONE PARAMETER EXPANSION PER INTERESTING BYTE, not per character. A character loop
    # over a pasted heredoc is O(n^2) in string copies and this hook runs on PreToolUse.
    sg_run="${sg_rest%%[;\&|\(\)\'\"]*}"
    if [ "$sg_run" = "$sg_rest" ]; then
      sg_cur="$sg_cur$sg_rest"
      sg_rest=""
      break
    fi
    sg_cur="$sg_cur$sg_run"
    sg_rest="${sg_rest#"$sg_run"}"
    sg_c="${sg_rest%"${sg_rest#?}"}"
    sg_rest="${sg_rest#?}"
    # A REDIRECTION IS NOT A SEPARATOR, and `2>&1` is why this is a test rather than
    # something left to the fail direction. Over the 310 distinct fail commands in the
    # live store of 2026-09-04 the bare byte rule produced the segment head `1` a hundred
    # and twenty-four times, every one of them the tail of a `2>&1` somebody wrote to keep
    # stderr -- a head on no list, refusing the exemption of every command wearing one.
    # `>&`, `<&` and `&>` are one redirection each and `>|` is the clobber form; `&&`,
    # `||`, a lone `&` and a lone `|` are the real separators and are left exactly where
    # they were. `|&` is a PIPE and is deliberately not in here.
    sg_prev="${sg_cur#"${sg_cur%?}"}"
    sg_next="${sg_rest%"${sg_rest#?}"}"
    case "$sg_c$sg_prev$sg_next" in
      '&>'*|'&<'*) sg_cur="$sg_cur$sg_c"; continue ;;
      '&'?'>') sg_cur="$sg_cur$sg_c"; continue ;;
      '|>'*) sg_cur="$sg_cur$sg_c"; continue ;;
    esac
    case "$sg_c" in
      \'|\")
        sg_in="${sg_rest%%"$sg_c"*}"
        [ "$sg_in" = "$sg_rest" ] && return 1
        sg_cur="$sg_cur$sg_c$sg_in$sg_c"
        sg_rest="${sg_rest#"$sg_in"}"
        sg_rest="${sg_rest#?}"
        ;;
      *)
        SEGS="$SEGS$sg_cur
"
        sg_cur=""
        ;;
    esac
  done
  SEGS="$SEGS$sg_cur
"
  return 0
}

# The head of ONE segment, into SEG_HEAD. Three things are stepped over or past before the
# first word is read, and each of them was a wrong answer once the split existed:
#
#   * LEADING `VAR=value` ASSIGNMENTS, so `FOO=1 ls` reads as `ls`. The name is validated
#     rather than matched loosely: a pattern like `[A-Za-z_]*=*` also matches
#     `git commit -m x=y`, whose first word is not an assignment at all, and stepping over
#     it would drop `git` off the front of a command this gate must never refuse.
#   * THE KEYWORDS THAT PRECEDE A COMMAND -- `if`, `then`, `do`, `while` and the rest. A
#     segment reading ` do echo "== $f =="` has the command `echo` in it and the head `do`,
#     which is on no list; over the live store of 2026-09-04 that alone refused the
#     exemption of 9 commands whose every real head was `echo`, `cat` or `ls`.
#   * THE WORDS THAT CARRY NO PROGRAM AT ALL -- a loop or `case` HEADER, a terminator, and
#     the two condition forms. `for f in docs/*` runs nothing, `done 2>/dev/null` runs
#     nothing, and `[ -f x ]` cannot run anything else. SEG_HEAD is left EMPTY for these
#     and the caller skips the segment. That is not a hole: anything a `for` header
#     actually executes is a `$(...)`, and `(` and `)` are separators, so it arrives as a
#     segment of its own and is judged there.
#
# Empty when the segment holds no word at all, which is the `&&` case above. It sets a
# variable rather than printing one, because a fork per segment is a fork this arm cannot
# afford on PreToolUse.
#
# ====================================================================================
# PREFIX RUNNERS, AND THEY WERE A HOLE IN THE ALLOWLIST RATHER THAN A GAP IN IT.
#
# `env`, `command`, `source` and `.` sat on `head_allowlisted` as though they were
# inspection commands. They are not: each of them RUNS THE NEXT WORD. Measured live on
# 2026-09-05 against the installed package, session 8449d34a: `python3
# scripts/count_words.py --file data/f2.txt` was DENIED and `env python3
# scripts/count_words.py --file data/f2.txt` RAN. Free to reproduce against this file --
#   printf 'env python3 x.py' | bash hooks/repeat-gate.sh --eligible-of Bash
# answered `exempt-allowlist`, and `command python3 x.py`, `source x.sh` and `. x.sh`
# answered the same.
#
# THE TWO REPAIRS GO IN OPPOSITE DIRECTIONS AND BOTH ARE THE SAME RULE: judge the program
# that will actually run, and where that cannot be judged, refuse the exemption.
#
#   STEPPED OVER, to the program they run: `env`, `command`, `exec`, `nohup`, `builtin`,
#   `nice`, `timeout`, `caffeinate`, `sudo`, `doas`, `stdbuf`, `setsid`, `ionice`. Each
#   carries its own option shape and only the options named in `sh_flag_solo` and
#   `sh_flag_arg` are modelled; `timeout` additionally eats one DURATION word. `time` was
#   already stepped over as a shell keyword and stays there.
#
#   NOT EXEMPT, EVER, because what they run is not a word this function can read:
#   `source`, `.`, `eval`, and `sh -c` / `bash -c` / `zsh -c`. All four are simply absent
#   from both head lists, so their head is judged and lands on neither -- and `source`
#   and `.` were REMOVED from `head_allowlisted` to make that true. `xargs` is left the
#   same way and deliberately: it takes its program from stdin, so no walk over the
#   argv can name it.
#
# ANYTHING UNMODELLED FAILS TOWARD NOT EXEMPT, which is this whole function's direction:
# when `sh_runner_opts` meets a flag it does not know, SEG_HEAD is set to that word, and
# a word that is not a program name is on no list.

# Flags one prefix runner takes that consume NO further word.
sh_flag_solo() {
  case "$1:$2" in
    env:-i|env:-0|env:--ignore-environment|env:--null|env:-v|env:--debug) return 0 ;;
    env:-u*|env:--unset=*|env:-C*|env:--chdir=*) return 0 ;;
    command:-p) return 0 ;;
    nice:-[0-9]*|nice:--[0-9]*) return 0 ;;
    sudo:-n|sudo:-E|sudo:-H|sudo:-b|sudo:-S|sudo:-k|sudo:-A) return 0 ;;
    doas:-n|doas:-s) return 0 ;;
    timeout:--preserve-status|timeout:--foreground|timeout:-v|timeout:--verbose) return 0 ;;
    timeout:--signal=*|timeout:--kill-after=*) return 0 ;;
    caffeinate:-d|caffeinate:-i|caffeinate:-m|caffeinate:-s|caffeinate:-u) return 0 ;;
    setsid:-f|setsid:-w|setsid:-c) return 0 ;;
    stdbuf:-i*|stdbuf:-o*|stdbuf:-e*) return 0 ;;
    ionice:-c*|ionice:-n*|ionice:-t) return 0 ;;
    *:--) return 0 ;;
  esac
  return 1
}

# Flags that consume the NEXT word as their argument.
sh_flag_arg() {
  case "$1:$2" in
    env:-u|env:-C) return 0 ;;
    nice:-n) return 0 ;;
    sudo:-u|sudo:-g|sudo:-p|sudo:-C|sudo:-r|sudo:-t) return 0 ;;
    doas:-u|doas:-C) return 0 ;;
    timeout:-s|timeout:-k) return 0 ;;
    ionice:-c|ionice:-n|ionice:-p) return 0 ;;
  esac
  return 1
}

# Steps the GLOBAL `h` past one prefix runner's own options, leaving its first word at the
# program that runner will execute. Returns 1 when it meets something it cannot model, and
# leaves `h` starting at the word that stopped it so the caller can name it as the head.
sh_runner_opts() {
  sh_r="$1"
  sh_skip=0
  while :; do
    case "$h" in ' '*) h="${h# }"; continue ;; esac
    [ -z "$h" ] && return 1
    sh_w="${h%% *}"
    if [ "$sh_skip" = "1" ]; then
      sh_skip=0
      [ "$h" = "$sh_w" ] && return 1
      h="${h#* }"
      continue
    fi
    # `command -v` / `command -V` RUN NOTHING -- they are a lookup, and the word after
    # them is a name being asked about rather than a program about to start. Answering 2
    # tells the caller to judge `command` itself, which is where a plain `which` lands.
    # Without this `command -v podman colima orb` was judged as `podman`, which is the
    # ONE verdict the live-store join moved before this arm existed.
    case "$sh_r:$sh_w" in
      command:-v|command:-V) return 2 ;;
    esac
    case "$sh_w" in
      -*)
        if sh_flag_arg "$sh_r" "$sh_w"; then
          sh_skip=1
        else
          sh_flag_solo "$sh_r" "$sh_w" || return 1
        fi
        [ "$h" = "$sh_w" ] && return 1
        h="${h#* }"
        continue ;;
    esac
    break
  done
  # `timeout` puts a DURATION between its options and the program it runs, and nothing
  # else here does. A word that is not a duration means the walk has lost its place.
  if [ "$sh_r" = "timeout" ]; then
    sh_w="${h%% *}"
    case "$sh_w" in
      *[!0-9.smhd]*|'') return 1 ;;
      *[0-9]*) ;;
      *) return 1 ;;
    esac
    [ "$h" = "$sh_w" ] && return 1
    h="${h#* }"
  fi
  return 0
}

segment_head() {
  h="$1"
  SEG_HEAD=""
  while :; do
    case "$h" in ' '*) h="${h# }"; continue ;; esac
    first="${h%% *}"
    [ -z "$first" ] && return 0
    case "$first" in
      'fi'|'done'|'esac'|'}'|';;'|'for'|'case'|'select'|'in'|'['|'[['|']]'|'test')
        return 0 ;;
      'if'|'then'|'elif'|'else'|'do'|'while'|'until'|'!'|'time'|'{')
        [ "$h" = "$first" ] && return 0
        h="${h#* }"
        continue ;;
    esac
    # A PREFIX RUNNER WITH NOTHING AFTER IT is that word and no more -- a bare `env`
    # prints the environment and runs nothing -- so it breaks out and is judged on its
    # own name like any other head.
    case "${first##*/}" in
      env|command|exec|nohup|builtin|caffeinate|nice|timeout|sudo|doas|stdbuf|setsid|ionice)
        [ "$h" = "$first" ] && break
        sh_run="${first##*/}"
        h="${h#* }"
        sh_runner_opts "$sh_run"
        sh_rc=$?
        [ "$sh_rc" = "0" ] && continue
        # 2: the runner runs nothing after all, so IT is the head. 1: unmodelled, and the
        # word that stopped the walk is the head -- a word that is not a program name is
        # on no list, which is the direction every failure in this file goes.
        if [ "$sh_rc" = "2" ]; then SEG_HEAD="$sh_run"; return 0; fi
        h="${h#"${h%%[! ]*}"}"
        SEG_HEAD="${h%% *}"
        [ -z "$SEG_HEAD" ] && SEG_HEAD="$sh_run"
        return 0 ;;
    esac
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
  SEG_HEAD="${h##*/}"
}

# Guard 3 from the header, on ONE head.
#
# `source` AND `.` WERE REMOVED FROM THIS LIST ON 2026-09-05 and they are not coming back.
# Both RUN A FILE, so `. x.sh` was exempt while everything x.sh contains was invisible to
# every rule here -- the same defect as `env` in a shorter costume, and `--eligible-of`
# answered `exempt-allowlist` for both. There is no repair that keeps them: what they run
# is in a file this function may not read. `env` and `command` stay, because `segment_head`
# now steps over them to the program they run and only a BARE `env` or `command`, which
# runs nothing, reaches here under either name.
head_allowlisted() {
  case "$1" in
    cd|ls|pwd|echo|printf|cat|head|tail|less|wc|grep|egrep|fgrep|rg|find|which|command|type|env|export|git|jq|sed|awk|sort|uniq|diff|stat|file|date|true|:|skillrepeat|skillforge|skillinsight|skillreport|skillcontrib)
      return 0 ;;
  esac
  return 1
}

# THE ONLY EXEMPTION THE LESSON GATE HAS, and it is not `head_allowlisted`. That list is
# guard 3 of BOOTSTRAP DEADLOCK -- the commands a session diagnoses with -- and the repeat
# arm keeps it. The lesson gate cannot: the thing it is refusing is CONTINUING, and `cat`,
# `git` and `ls` are continuing. Measured live 2026-09-05, scenario 6: a session refused on
# a `Bash` call answered with `Read data/f2.txt` and finished the job, so a gate that
# spares the inspection commands spares the bypass with them.
#
# So exactly one shape runs: a command that reaches for one of the two CLIs that END the
# refusal. EVERY segment head must be `skillnote`, `skillrepeat` or `cd`, and at least one
# must be a CLI -- `cd` because the deny prints a command the session has to be able to run
# from wherever it is standing, and `cd repo && skillnote add --lesson ...` is that shape.
# A bare `cd` alone is not exempt, which is the `rh_any` rule of `runner_head` written for
# two names instead of one.
#
# THE FALLBACK IS THE OLD SUBSTRING TEST AND ONLY WHERE THE SPLIT FAILED. A lesson's text
# is free prose the model writes, and `split_segments` refuses to model a backslash-escaped
# quote next to a separator byte -- so the one command that lifts this could be refused by
# the quoting of its own argument, which would be a trap with no way out at all. Where the
# walk cannot model the text, a command MENTIONING either CLI is exempt. That is weaker
# than the head test and it is bounded by never being reached for a command the walk can
# read: `echo skillnote; python3 x.py` splits cleanly and is refused.
lesson_cli_head() {
  if split_segments "$1"; then
    lc_any=0
    while IFS= read -r lc_seg; do
      segment_head "$lc_seg"
      [ -z "$SEG_HEAD" ] && continue
      case "$SEG_HEAD" in
        skillnote|skillrepeat) lc_any=1 ;;
        cd) ;;
        *) return 1 ;;
      esac
    done <<EOF
$SEGS
EOF
    [ "$lc_any" = "1" ] || return 1
    return 0
  fi
  case "$1" in *skillnote*|*skillrepeat*) return 0 ;; esac
  return 1
}

# Guard 3, on a whole command: EVERY segment's head, and a command that cannot be split
# into segments is not exempt. Everything about this is a lower bound on refusing and an
# upper bound on trapping the session, which is why the empty command is not exempt
# either -- `ah_any` is what says a head was actually judged.
allowlisted_head() {
  split_segments "$1" || return 1
  ah_any=0
  while IFS= read -r ah_seg; do
    segment_head "$ah_seg"
    [ -z "$SEG_HEAD" ] && continue
    head_allowlisted "$SEG_HEAD" || return 1
    ah_any=1
  done <<EOF
$SEGS
EOF
  [ "$ah_any" = "1" ] || return 1
  return 0
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
head_runner() {   # $1 = the segment, $2 = its head as `segment_head` left it
  h="$2"
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

# The runner exemption on a whole command, and the rule is NOT "every head is a runner".
# `cd repo && ./run_tests.sh` is the ordinary shape of running a suite, and `cd` is not a
# runner; requiring every head to be one would take the runner exemption away from it and
# land back on the loop the user's own CLAUDE.md mandates. So: EVERY head must be exempt
# by one of the two lists, and AT LEAST ONE must be a runner -- which is what keeps this
# answering `exempt-runner` where `allowlisted_head` already answered `exempt-allowlist`,
# so the two verdicts `--eligible-of` prints stay distinguishable.
runner_head() {
  split_segments "$1" || return 1
  rh_any=0
  while IFS= read -r rh_seg; do
    segment_head "$rh_seg"
    [ -z "$SEG_HEAD" ] && continue
    if head_runner "$rh_seg" "$SEG_HEAD"; then
      rh_any=1
      continue
    fi
    head_allowlisted "$SEG_HEAD" || return 1
  done <<EOF
$SEGS
EOF
  [ "$rh_any" = "1" ] || return 1
  return 0
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
# comment, because under any of these matchers such an arm is the dead guard
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

# ==================================================================== the LESSON gate
# Reached by PreToolUse only: arms 1 and 2 and both argv doors exit above. See THE LESSON
# GATE in the header for what it is for and why its session count includes this session.
#
# IT REFUSES EVERY TOOL, AND THAT IS THE WHOLE OF WHAT CHANGED ON 2026-09-05. It was
# Bash-only, on the argument that a refused `Skill` call has no escape hatch. The argument
# was answered by a measurement: a session refused on a `Bash` call ran `Read data/f2.txt`
# instead and finished the job (red team of the installed package, scenario 6). A gate
# that refuses one tool refuses nothing; the user's word is "before continuing", and
# continuing is any tool. So the matcher lost its narrowing (WHAT THE WIRING ADMITS) and
# the `[ "$tool" = "Bash" ]` test here went with it.
#
# THE ESCAPE HATCH IS NOT A TOOL, WHICH IS WHY REFUSING A `Skill` IS SAFE NOW. What lifts
# this is `skillnote add --lesson`, a Bash command, and `lesson_cli_head` exempts it
# whatever else is refused. Nothing else is needed to write a lesson down.
#
# WHAT IT COSTS WHEN IT DOES NOTHING, which is the case that matters because it now runs
# on every tool call: FOUR program starts and a builtin `[ -d ]`, pinned by
# ProcessCountTest. A session that has bound a recovery pays a `find`, one jq read of the
# command on a Bash call only, the head test, and then one parse of the store and one of
# the ledger -- and the marker is REMOVED as soon as its signature is judged unable to
# qualify, so that parse happens a bounded number of times per signature per session
# rather than on every tool call for the rest of it.
# A SIGNATURE THIS SESSION CAN NO LONGER BE REFUSED OVER, forgotten in ONE `rm` because
# the marker is now a PAIR: the facts and, when the recovery ran a script, the path beside
# them. Two removals in three places is two removals one of which will be forgotten.
lg_forget() {   # $1 sanitised signature
  rm -f "$lg_dir/s-$1" "$lg_dir/a-$1" 2>/dev/null || :
}

lesson_gate() {
  [ "$LESSON_GATE" = "1" ] || return 0
  if [ "$LESSON_UNLIMITED" != "1" ] && [ "$LESSON_MAX" -lt 1 ]; then return 0; fi
  # CHEAPEST TEST FIRST, ALL THE WAY DOWN, because this arm ships ON and most calls it
  # sees have nothing for it to do: a directory test, two string tests, then a fork.
  lg_dir="$DIR/lessons/$sid"
  [ -d "$lg_dir" ] || return 0
  # A payload with no tool_use_id cannot be claimed, and an unclaimed deny is emitted
  # TWICE under the double delivery both wirings produce. The learn arm can afford that
  # -- a duplicated row costs a line -- and a refusal cannot.
  [ -n "$tuid" ] || return 0
  lg_files="$(find "$lg_dir" -mindepth 1 -maxdepth 1 -type f -name 's-*' 2>/dev/null \
               | head -20)"
  [ -z "$lg_files" ] && return 0
  # EVERY TOOL, AND ONLY A `Bash` CALL HAS AN EXEMPTION. See IT REFUSES EVERY TOOL in the
  # header: a `Read` is the shape the red team walked around a Bash refusal with, and the
  # only reason to let a call through here is that it is the call that ENDS the refusal.
  # `.tool_input.command` exists on a `Bash` payload and nowhere else, so the jq below is
  # paid for by Bash calls alone; every other tool falls straight through to the store
  # read with one fewer fork than a Bash call costs.
  if [ "$tool" = "Bash" ]; then
    lg_cmd="$(jqr '.tool_input.command // empty')"
    [ -z "$lg_cmd" ] && return 0
    lesson_cli_head "$lg_cmd" && return 0
  fi

  [ -f "$STORE" ] && [ -r "$STORE" ] || return 0
  lg_size="$(wc -c < "$STORE" 2>/dev/null | tr -cd '0-9')"
  case "$lg_size" in ''|*[!0-9]*) return 0 ;; esac
  [ "$lg_size" -gt "$MAX_BYTES" ] && return 0
  [ "$lg_size" -eq 0 ] && return 0

  # THE SIGNATURES ARE READ OFF THE MARKER FILENAMES, which the recover arm sanitised the
  # same way every other name here is sanitised. They go to jq as a JSON array so ONE
  # parse of the store answers for all of them; a loop of one parse each is what a busy
  # session would pay twenty times over.
  lg_names=""
  while IFS= read -r lg_f; do
    [ -z "$lg_f" ] && continue
    lg_b="${lg_f##*/}"
    lg_names="$lg_names${lg_b#s-}
"
  done <<EOF
$lg_files
EOF
  [ -z "$lg_names" ] && return 0
  lg_want="$(printf '%s' "$lg_names" \
    | jq -R -s -c 'split("\n") | map(select(length > 0))' 2>/dev/null)"
  [ -z "$lg_want" ] && return 0

  # ONE pass, and it answers both halves of clause (a) and half of clause (b): how many
  # distinct sessions have failed this way, THIS ONE COUNTED ONCE, and whether a dismissal
  # a person wrote has been recorded.
  # THE CURRENT SESSION IS UNIONED IN, `+ [$cur]`, where the repeat arm excludes it. It
  # has a fail row by construction -- a marker under lessons/<sid>/ means a recovery was
  # bound here -- and the union rather than the row is what makes "once" a property of
  # the query instead of the store: a `forget` cutting this session's own row out, or a
  # session that failed five times, both leave it at exactly one. A row with no session
  # is nobody's observation and is dropped. See THE TWO ARMS COUNT THE CURRENT SESSION
  # DIFFERENTLY in the header.
  # ONLY A HUMAN'S DISMISSAL COUNTS. `.actor` is `human`, `model`, or absent on a row
  # written before the field existed -- and absent reads as human, because those rows
  # predate the model path and there is nothing in them to tell apart.
  # THE TOMBSTONE CUTOFF APPLIES TO THE FAIL ROWS AND NOT TO THE DISMISSAL. A `forget`
  # says "these observations no longer count"; a `dismiss` says "this decision was made",
  # and a decision is not un-made by forgetting the rows that prompted it.
  jq -Rc 'fromjson? // empty | select(type=="object")' "$STORE" > "$TMP/lrows.json" \
    2>/dev/null || return 0
  [ -s "$TMP/lrows.json" ] || return 0
  jq -s -r --argjson want "$lg_want" --arg cur "$sid" '
    . as $rows
    | $want[] as $s
    | (([ $rows[] | select(.t=="forget" and .sig==$s) | (.ts // 0) ] | max) // -1) as $cut
    | [ $s,
        (([ $rows[] | select(.t=="fail" and .sig==$s and ((.ts // 0) > $cut))
                    | (.session // "") | select(. != "") ] + [$cur])
          | unique | length | tostring),
        (if ([ $rows[] | select(.t=="dismiss" and .sig==$s)
                       | select((.actor // "human") == "human") ] | length) > 0
         then "yes" else "no" end) ]
    | join("\u001f")' "$TMP/lrows.json" > "$TMP/lsigs" 2>/dev/null || return 0
  [ -s "$TMP/lsigs" ] || return 0

  # THE LEDGER IS bin/skillnote's FILE AND THIS ONLY READS IT. An unreadable or oversized
  # one means the fact that lifts the refusal cannot be checked, so nothing is refused:
  # every failure here fails CLOSED ON DENYING, which is the opposite direction from the
  # store reads above and is right for the same reason -- a refusal whose escape cannot
  # be verified is a trap.
  lg_noted=" "
  if [ -f "$LEDGER" ]; then
    [ -r "$LEDGER" ] || return 0
    lg_lsize="$(wc -c < "$LEDGER" 2>/dev/null | tr -cd '0-9')"
    case "$lg_lsize" in ''|*[!0-9]*) return 0 ;; esac
    [ "$lg_lsize" -gt "$MAX_BYTES" ] && return 0
    # AN `add` ROW WHOSE NOTE WAS LATER REMOVED IS NOT A LESSON. `bin/skillnote remove`
    # appends `{"event":"note","action":"remove","id":...}` and DELETES NOTHING, which is
    # the same append-only discipline `forget` and `dismiss` follow -- so a reader that
    # matched on `lesson_sig` alone would report a withdrawn lesson as standing, forever,
    # with the note itself gone from the CLAUDE.md it was supposed to be read from. The
    # add rows are collected, the removed ids are subtracted, and only what survives
    # counts. `.action // "add"` because rows written before that field existed carry no
    # action and are adds.
    lg_noted=" $(jq -R -s -r --argjson want "$lg_want" '
        [ split("\n")[] | select(length > 0) | (fromjson? // empty)
          | select(type=="object") | select(.event == "note") ] as $n
        | ([ $n[] | select((.action // "add") == "remove")
             | (.id? // "") | select(. != "") ] | unique) as $gone
        # THE ID IS BOUND BEFORE THE LOOKUP. `$gone | index(.id)` evaluates `.id` with
        # `.` already rebound to $gone -- an array, which has no .id -- so the whole
        # expression errors and jq drops the row. Bind, then look up.
        | [ $n[] | select((.action // "add") == "add")
            | ((.id? // "")) as $rid
            | select(($gone | index($rid)) == null)
            | (.lesson_sig? // "") | select(. != "") ]
        # `.[] as $ls | f` ITERATES BUT DOES NOT RESET `.`: inside f the input is still
        # the ARRAY, so a `select` there emits the whole array once per element. Written
        # that way this printed `[ "<sig>" ]` and the substring test below never matched,
        # so a recorded lesson lifted nothing. `.[] | select(...)` is the form that walks.
        | unique | .[]
        | select(. as $ls | ($want | index($ls)) != null)' "$LEDGER" 2>/dev/null \
      | tr '\n' ' ')"
  fi

  while IFS="$(printf '\037')" read -r lg_sig lg_n lg_dis; do
    [ -z "${lg_sig:-}" ] && continue
    case "${lg_n:-}" in ''|*[!0-9]*) continue ;; esac
    lg_safe="$(printf '%s' "$lg_sig" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
    case "$lg_safe" in ''|.|..) lg_safe=_ ;; esac
    # SPENT MARKERS ARE REMOVED, and that is a cost decision rather than a cleanup one.
    # Leaving one makes every later tool call in the session re-parse the store and the
    # ledger to reach the same answer, at the figure the REPEAT_LESSON_GATE stanza prints.
    #
    # TWO OF THE THREE VERDICTS REALLY CANNOT CHANGE inside one session: the distinct
    # session count is fixed once this session's own fail row is in, and nothing
    # un-dismisses a signature. THE THIRD ONE CAN -- `skillnote remove <id>` withdraws a
    # lesson -- so a lesson written and then withdrawn later in the SAME session is not
    # noticed until a later session binds a recovery for that signature and arms a fresh
    # marker. That limit is asserted, not left to be found:
    # tests/test_repeat_gate.py::LessonGateTest
    # ::test_a_lesson_withdrawn_after_the_gate_saw_it_does_not_re_arm_this_session, whose
    # second half shows the next session is armed again. A delay of one session against a
    # store parse on every remaining tool call is the trade, and the deny budget is two
    # either way.
    if [ "${lg_dis:-no}" = "yes" ] || [ "$lg_n" -lt "$MIN_SESSIONS" ]; then
      lg_forget "$lg_safe"
      continue
    fi
    case "$lg_noted" in *" $lg_sig "*) lg_forget "$lg_safe"; continue ;; esac
    # AND IT DOES NOT LET GO, unless somebody set a budget. Counted before it is claimed,
    # so the duplicate delivery cannot spend two of the budget on one event: the second
    # delivery finds the same tuid already claimed and leaves without emitting. The whole
    # block is skipped at the shipped default, which also saves the `find`, the `wc` and
    # the `tr` on every refusal.
    if [ "$LESSON_UNLIMITED" != "1" ]; then
      lg_spent="$(find "$lg_dir/deny/$lg_safe" -mindepth 1 -maxdepth 1 -type d 2>/dev/null \
                   | wc -l | tr -cd '0-9')"
      case "$lg_spent" in ''|*[!0-9]*) lg_spent=0 ;; esac
      if [ "$lg_spent" -ge "$LESSON_MAX" ]; then
        lg_forget "$lg_safe"
        continue
      fi
    fi
    mkdir -p "$lg_dir/deny/$lg_safe" 2>/dev/null || return 0
    mkdir "$lg_dir/deny/$lg_safe/$tuid" 2>/dev/null || return 0
    lg_stmt="$(cat "$lg_dir/s-$lg_safe" 2>/dev/null)"
    [ -z "$lg_stmt" ] && return 0
    # THE ATTACHMENT RIDES ON THE ONE COMMAND AND ADDS NO SECOND ONE. See AND WHEN THE
    # RECOVERY WAS A SCRIPT in the header: the requirement is that the write-down carry the
    # script, and the rule that this text names exactly one command is measured. An
    # argument to that command satisfies both; a line saying "and also run X" satisfies
    # neither.
    lg_att=""
    [ -f "$lg_dir/a-$lg_safe" ] \
      && lg_att="$(cat "$lg_dir/a-$lg_safe" 2>/dev/null)"
    [ -n "$lg_att" ] && lg_att=" --attach $lg_att"
    # ONE COMMAND, AND BOTH OMISSIONS ARE THE POINT. `skillrepeat dismiss` is not named
    # here: measured 2026-09-04, two of two refused sessions ran it with an invented
    # reason and carried on, so naming it made the refusal free. A dismissal a model
    # writes is recorded and does not lift this (WHO MAY DISMISS in the header), and a
    # deny that advertised an escape which no longer works would be worse than one that
    # omits it. THE BUDGET IS NOT NAMED EITHER, for the reason the AND IT NO LONGER LETS GO stanza
    # in the header gives (a budget is now opt-in): this text used to end by saying how often it could be
    # spent and that the call then went through, and a session read that as a schedule
    # and retried until it expired without writing anything down. What is left is the
    # refusal, the fail-then-fix facts, and the one command that lifts it -- statements
    # of fact, no instruction among them.
    lg_reason="$lg_stmt

Nothing ran and nothing was written. Fail rows for this signature come from $lg_n distinct
sessions, this one among them, and the recovery above was bound here. Writing the lesson
down is what lifts this, and in this session it is the only thing that does:

  skillnote add --lesson $lg_sig \"<what was learned>\"$lg_att

  skillrepeat show $lg_sig

A lesson may record that this failure is EXPECTED -- a red-green test run, a probe whose
error is the answer, a shape matched by a store that is stale -- and such a lesson lifts
this exactly as any other one does."
    ( jq -n --arg r "$lg_reason" \
        '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny",
          permissionDecisionReason:$r}}' > "$TMP/ldeny.json" ) 2>/dev/null
    # THE CLAIM IS RELEASED WHEN THE EMIT DID NOT HAPPEN, exactly as the repeat arm's is
    # and for the identical reason: a refusal nobody saw must not spend a budget.
    if [ -s "$TMP/ldeny.json" ] && cat "$TMP/ldeny.json" 2>/dev/null; then
      return 1
    fi
    rmdir "$lg_dir/deny/$lg_safe/$tuid" 2>/dev/null || :
    return 0
  done < "$TMP/lsigs"
  return 0
}

# THE INVERSION IS DELIBERATE AND IT IS THE ONLY ONE IN THIS FILE: `lesson_gate` returns
# 1 when it has ALREADY EMITTED a deny, so `|| exit 0` is what stops the repeat arm from
# emitting a second one for the same call. A 0 means it decided nothing and the arm below
# gets its turn.
lesson_gate || exit 0

# EVERYTHING BELOW IS THE REPEAT ARM, WHICH IS OFF UNLESS REPEAT_GATE_REFUSE=1. Tested
# again here and not only at the dispatch above, because the dispatch now falls through
# whenever EITHER refusal is armed and the lesson gate is the one that ships on.
[ "$REFUSE" = "1" ] || exit 0

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
case "$sig" in ''|.|..) sig=_ ;; esac

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
