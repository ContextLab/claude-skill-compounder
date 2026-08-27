#!/usr/bin/env bash
# Refuses a `git push` that carries code changes and no documentation change.
#
# WHY THIS IS A HOOK AND NOT A SKILL, AND WHY IT REFUSES RATHER THAN REMINDS.
# The defect, in the issue author's words (issue #19): "a toolbox or codebase is changed
# and the model forgets to update the documentation. this is a missed opportunity for a
# *deterministic* hook -- before pushing updates, force a subagent to update the
# documentation to make it current." Forgetting is the whole failure mode, so anything
# that has to be REMEMBERED cannot be the fix: a skill must be invoked, and the party who
# would have to invoke it is the party who already believes the work is finished. The same
# argument that put `hooks/claim-gate.sh` on `Stop` and `PreToolUse` puts this one on
# `PreToolUse`, and it is the second component in this package that refuses.
#
# A REMINDER WAS ALREADY TRIED, IN THIS PACKAGE, AND IS ON RECORD AS NOT WORKING.
# `hooks/compound-improvement.sh` emits `additionalContext` nudges; the maintainer's own
# measurement is that they are read past. Only a refusal steers. So this hook emits a
# `permissionDecision:"deny"`, the push does not happen, and the reason names the files.
#
# WIRING (not written by this file):
#   PreToolUse -> "$DIR/doc-gate.sh", matcher "Bash"
# It dispatches on `.hook_event_name` and takes no argv, exactly as claim-gate.sh does.
#
# ====================================================================================
# PLATFORM FACTS THIS RELIES ON. Each was established by running something; none is
# re-derived here. See docs/CLAUDE-CODE-BEHAVIOR.md for the full entries.
#
# 1. A `PreToolUse` deny is stdout
#      {"hookSpecificOutput":{"hookEventName":"PreToolUse",
#                             "permissionDecision":"deny",
#                             "permissionDecisionReason":"<text>"}}
#    with exit status 0. The call does not execute and the model reports the reason.
#    Measured on Claude Code 2.1.245, macOS 25.5.0, 2026-08-25.
#
# 2. THE REASON IS UNTRUSTED TEXT TO THE MODEL, AND IT IS RIGHT TO TREAT IT THAT WAY.
#    Measured in the same probe: an instruction embedded in a deny reason was explicitly
#    refused -- "text that comes back from a blocked tool call isn't a directive I
#    follow." So the reason below is written as a STATEMENT OF FACT about what the push
#    contains and what exists to fix it, never as an imperative. That is a constraint on
#    the author, not a defect, and it is why the reason says "`claim-provenance` exists
#    for exactly this" rather than "run claim-provenance".
#
# 3. BOTH WIRINGS AT ONCE DELIVER EVERY HOOK EVENT TWICE (settings.json plus the plugin
#    manifest). Measured on 2.1.241. Everything this script counts, appends or does once
#    is therefore claimed atomically on an identity the payload already carries. See
#    IDEMPOTENCE below.
#
# ====================================================================================
# WHAT IT DOES, IN ORDER, AND WHERE IT FAILS OPEN
#
#   a. Recognise a real `git push` in `.tool_input.command` (see RECOGNITION).
#   b. Work out which directory that push is about (a leading `cd`, or `git -C <path>`).
#   c. Work out whether the REFSPEC actually sends this branch's commits (see REFSPEC).
#   d. `git rev-list --count @{u}..HEAD` -- the commits about to leave.
#   e. Partition the files those commits touch into CODE, DOC and NEITHER.
#   f. Deny iff there is at least one CODE file and not one DOC file.
#
# FAILING OPEN IS THE DEFAULT EVERYWHERE. Every one of these lets the push through with
# no output at all: the off switch; no `jq`; no `git`; a wrong event or a non-Bash tool;
# no command text; no push in the command; a `--dry-run` push; a working directory that
# does not exist; not a git repository; a detached HEAD; no upstream configured; a
# refspec that sends no commit of this branch (see REFSPEC); a
# `rev-list` that fails or reports zero commits ahead; more than DOC_GATE_MAX_COMMITS
# commits ahead; a diff that names no file; any DOC file present; no CODE file; an
# override; a HEAD already refused once in this session; and an unwritable state
# directory. The reasoning is the same one claim-gate.sh states at length: a gate that
# blocks when it cannot see is a gate that blocks at random, and a gate that blocks
# wrongly gets uninstalled, which is strictly worse than no gate.
#
# THE ONE PLACE THIS ERRS TOWARDS REFUSING, NAMED HONESTLY: a test-only change counts as
# CODE. A test is code, and pretending otherwise would exempt most of the work this
# repository actually does. That will refuse pushes that genuinely need no documentation
# change, which is what the two overrides and DOC_GATE_CODE_EXCLUDE are for --
# `DOC_GATE_CODE_EXCLUDE='^tests?/'` is the first knob to reach for if the default is
# too loud on a given project. It is a real cost and it is not hidden.
#
# ====================================================================================
# RECOGNITION: HOW A `git push` IS TOLD FROM TEXT THAT MENTIONS ONE
#
# THE MATCHER IS THE COMMAND-POSITION ONE FROM `hooks/claim-gate.sh`, REUSED, and the
# reuse is deliberate: that matcher exists because a plain substring match on `git commit`
# refused an issue-comment command whose body merely QUOTED the phrase, blocking
# legitimate work (measured 2026-08-26, and its regression test is in
# tests/test_claim_gate.py). The same mistake is available here -- `grep -rn "git push"`,
# a note being written, a README that documents how to push -- so the same shape of fix
# is used. Three parts, and each earns its place:
#
#   * HEREDOC BODIES ARE CUT OUT FIRST, by the same awk claim-gate.sh uses. A command
#     that writes a document CONTAINING the words `git push` is not a push. claim-gate's
#     first version pounced on the first `<<` anywhere and read every later line as
#     content, denying real work; this one tracks each heredoc to its own delimiter.
#   * THE COMMAND IS SPLIT INTO SEGMENTS on `;`, `&`, `|`, `(` and `)`, so `cd X &&
#     git push` and a push buried in a long `&&` chain are each their own segment, and
#     the matcher can then ANCHOR at the start of a segment instead of hunting for the
#     phrase anywhere in the text.
#   * A SEGMENT IS A PUSH when, ignoring leading `NAME=value` environment assignments, it
#     starts with `git`, then any run of git's own options, then `push` as a whole word.
#     `git commit -m "push"` does not match: `commit` is not an option and is not `push`.
#     THE SEPARATE-ARGUMENT ALLOWANCE IS ENUMERATED, NOT UNIVERSAL, and that is a repaired
#     defect rather than a preference. The first version let EVERY git option swallow an
#     optional following word, which is what makes `git -C /path push` work -- but it also
#     let `--no-pager` swallow a SUBCOMMAND, so `git --no-pager stash push`,
#     `git --no-pager checkout push` and `git --no-pager branch push` all matched and were
#     denied (reproduced 2026-08-26). Only the seven git options that genuinely take a
#     separate argument may take one: `-C`, `-c`, `--git-dir`, `--work-tree`,
#     `--namespace`, `--exec-path`, `--super-prefix`. Their `--opt=value` spellings need no
#     allowance -- they are a single word and match as an ordinary option.
#
# `--dry-run` (and its `-n` spelling) is checked on the matched segment and is NOT a push
# for this purpose: it writes nothing to any remote, so there is nothing to gate.
#
# RESIDUAL LIMIT, INHERENT AND SHARED WITH claim-gate.sh: a push-shaped fragment sitting
# in command position INSIDE a quoted string still matches -- `echo "a; git push now"`
# splits at the `;` and the tail reads as a push. Telling a command from text quoted
# inside a command needs a shell parser, not a regex. The cost is bounded by everything
# downstream: such a "push" is only refused if the working tree really does have code
# commits ahead of its upstream and no documentation among them, and the two overrides
# and SKILL_COMPOUNDER_DOC_GATE=0 are all still available.
#
# ====================================================================================
# REFSPEC: WHETHER THE PUSH SENDS ANY COMMIT OF THIS BRANCH AT ALL
#
# The gate judges `@{u}..HEAD`. That is only a description of the push if the push
# actually sends the current branch. The first version never read the refspec, so a tag
# push, `--tags` and a branch deletion were each denied with a reason stating a falsehood
# about them -- `git push origin v1.0.0` was refused for "1 commit is about to leave this
# repository ... hooks/a.sh" when the tag push carried no commit at all (reproduced
# 2026-08-26). It was also the deny with no cheap way out: the trailer override means
# amending a commit that has nothing to do with the operation being refused.
#
# So the arguments after the `push` word are tokenised on whitespace and read as
# `git push [options] [<remote> [<refspec>...]]`. `--repo`, `-o`, `--push-option`,
# `--receive-pack`, `--exec` and `--recurse-submodules` consume the following word; a
# token starting with `>`, `<` or `N>` ends the argument list. THE ANSWER IS "PASS" UNLESS
# THE PUSH CAN BE SHOWN TO SEND THIS BRANCH, which is the fail-open direction this whole
# file errs in.
#
# THAT LIST OF SIX IS MEASURED, NOT REMEMBERED: `git push <opt> __SENT__ --dry-run`, then
# read what git calls `__SENT__`. These six report it as their own value; every other push
# option reports "'__SENT__' does not appear to be a git repository", which means it
# landed in the REMOTE positional and the option consumed nothing. A seventh word is
# consumed by `--recurse-submodules` and then READ rather than stepped over, because
# `only` changes the answer.
#
# HANDLED, JUDGED (the push sends the current branch):
#   `git push`, `git push origin`      -- no refspec, so the current branch
#   `git push origin HEAD`, `HEAD:refs/heads/x`, `origin <current-branch>`,
#   `origin refs/heads/<current-branch>`, `+<current>:<x>`
#   `origin @`, `@:refs/heads/x`       -- `@` is git's own shorthand for `HEAD`
#   `--follow-tags`                    -- the branch AND its annotated tags, NOT `--tags`
#   `--all`, `--branches`, `--mirror`  -- refs/heads/* includes the current branch
# HANDLED, PASSED (the push sends no commit of this branch):
#   `--delete` / `-d`, not cleared later -- a deletion sends nothing
#   `origin :somebranch`               -- the empty-source deletion spelling
#   `--tags` with no refspec           -- refs/tags/* only, even beside `--follow-tags`
#   `--recurse-submodules=only`        -- submodules only; the superproject stays put
#   `origin v1.0.0`, or any refspec whose source is not HEAD and not the current branch
#
# TWO OF THOSE ROWS ARE REPAIRS, and both were one option name sitting in the wrong list.
# `--follow-tags` was read as `--tags`, which let a code-only `git push --follow-tags`
# through with no override recorded -- the very push this file exists to refuse.
# `--recurse-submodules=only` was read as an ordinary option, so a push that leaves the
# superproject unpushed was DENIED for the code it was never going to carry. Both
# reproduced 2026-08-26; both git behaviours are measured, in the tests, not quoted from
# the manual. The lesson generalises: an option belongs on a list here only after
# answering "does this still send the current branch?" about it specifically.
#
# ====================================================================================
# LAST-WINS: EVERY OPTION ABOVE HOLDS ITS LAST SPELLING, NOT ITS FIRST
#
# The three rows above were read by FIRST-SEEN LATCHES -- one flag per option, set the
# first time a spelling appeared and never cleared. git does not resolve any of them that
# way, and a latch is wrong in whichever direction it sticks:
#
#   * `--recurse-submodules=only --recurse-submodules=on-demand` was ALLOWED while git
#     really did send the superproject. That is the gate failing OPEN on exactly the push
#     it exists to judge, and it was introduced by the fix for the `=only` row itself.
#   * `--tags --no-tags` was PASSED for the same reason, while git sent the branch.
#   * `--delete --no-delete origin main` was PASSED, while git pushed `main`.
#
# HOW THE TABLE BELOW WAS ESTABLISHED: by RUNNING `git push --dry-run` against a real
# local bare remote with the competing spellings in BOTH orders, and reading what git said
# it would send -- never from the manual. git 2.50.1 (Apple Git-155), macOS 25.5.0,
# 2026-08-26. The same runs are in tests/test_doc_gate.py, so the table is re-measured on
# every suite rather than restated here.
#
#   OPTION FAMILY                                      RESOLUTION   EVIDENCE
#   --recurse-submodules=<v> / --recurse-submodules <v>
#     / --no-recurse-submodules                        last wins    `=only =on-demand`
#                                                                   sends `main -> main`;
#                                                                   reversed, `Everything
#                                                                   up-to-date`. Same in
#                                                                   the separate-word and
#                                                                   mixed spellings.
#   --tags / --no-tags                                 last wins    `--tags --no-tags`
#                                                                   sends the branch;
#                                                                   reversed, the tag only
#   --follow-tags / --no-follow-tags                   last wins    and INDEPENDENT of
#                                                                   `--tags`: `--tags
#                                                                   --no-follow-tags`
#                                                                   still sends only the
#                                                                   tag
#   --delete / -d / --no-delete                        last wins    `--delete --no-delete
#                                                                   origin main` reports
#                                                                   `main -> main`;
#                                                                   reversed, `[deleted]`
#   --all / --branches / --no-all / --no-branches      last wins    `--tags --all --no-all`
#                                                                   sends the tag only;
#                                                                   `--no-all --all` is a
#                                                                   fatal combination with
#                                                                   `--tags`, so `--all`
#                                                                   was still set
#   --mirror / --no-mirror                             last wins    AND A SEPARATE
#                                                                   VARIABLE FROM `--all`:
#                                                                   `--mirror --no-all
#                                                                   origin v1.0.0` still
#                                                                   dies "--mirror can't
#                                                                   be combined with
#                                                                   refspecs"
#
# So `--all`/`--branches` and `--mirror` are folded into one answer only at the single
# question this gate asks -- "is refs/heads/* being sent?" -- and never at the parse.
# Collapsing them earlier would let `--no-all` switch off a mirror, which is the same
# family of bug one level down.
#
# QUOTES ARE STRIPPED ONCE, IN THE TOKENISER, NOT AT EACH USE. The tokeniser splits the
# RAW command text, so a word the shell would have unquoted arrives still wearing its
# quotes and `--recurse-submodules "only"` was not read as `only` -- the REFUSING
# direction, a push denied for code it was never going to carry (reproduced 2026-08-26).
# The refspec arm had grown its own stripping at its own use site, which is precisely why
# nobody noticed the option values had none. See `unquote` below for the two shapes.
#
# NOT HANDLED, AND THEREFORE PASSED: a refspec built at runtime (`$BRANCH`); a refspec
#   quoted around whitespace; the revision EXPRESSIONS that also mean HEAD (`@{0}`,
#   `HEAD~0`, `HEAD^0`, `HEAD^{commit}`) -- literal synonyms are matched literally and
#   resolving expressions would need `git rev-parse`, which would also resolve a tag onto
#   HEAD and undo the exemption on the row above; and `--tags` alongside a branch refspec
#   is judged on the branch alone. A tag pointing at a commit the remote does not have
#   DOES carry that commit; this gate deliberately does not treat that as its business,
#   because a tag push is not the shape of change the documentation defect is made of.
#
# ====================================================================================
# CLASSIFICATION: WHAT COUNTS AS CODE, AS DOC, AND AS NEITHER
#
# Three ordered rules, first match wins. The order is the design, not an accident.
#
#   1. NEITHER, checked FIRST so it can override the other two. Lockfiles, binaries and
#      images assert nothing about behaviour; `LICENSE` is not documentation of code; and
#      `notes/` is deliberately here. `notes/` in this repository is a DATED LOG, not a
#      description of current behaviour -- .claude/CLAUDE.md says so in as many words --
#      and it is written on nearly every session. Counting a note as documentation would
#      let this gate pass every push this repository makes, which is the difference
#      between a gate and an ornament.
#      THE NOTES RULE IS ANCHORED TO THE ROOT (`^notes?/`), AND THE ANCHOR IS THE WHOLE
#      RULE. Unanchored as `(^|/)notes?/` it matched the segment at ANY depth, so
#      `docs/notes/architecture.md` -- a real `.md` inside `docs/` -- was classified
#      NEITHER, the push was denied for carrying no documentation, and the reason named
#      the doc file nowhere, so nothing on any surface said why. That is the one outcome
#      this gate must never produce, and it is the same defect class the REFSPEC section
#      below already repaired once. The justification above is about THIS repository's
#      root-level dated log and reaches no further, so neither may the rule. It cut the
#      other way too, silently: `src/notes/parser.py` was excluded before rule 3 could
#      count it as CODE, and undercounting CODE only ever makes the gate more permissive,
#      which is why that half would never have announced itself. Reproduced by a cold
#      reviewer on 2026-08-26 against a real repository and a real bare remote; both
#      directions are pinned in tests/test_doc_gate.py.
#   2. DOC. `.md`/`.rst`/`.adoc`/`.org`/`.texi`/`.1`, anything under a `doc/`, `docs/`,
#      `documentation/` or `man/` path segment, and the conventional bare-name files:
#      README*, CHANGELOG*, CHANGES*, CONTRIBUTING*, HISTORY*, INSTALL*, USAGE*, and the
#      agent-instruction files CLAUDE.md / AGENTS.md.
#   3. CODE. Source extensions, script extensions, config and build files, plus anything
#      under `bin/`, `hooks/`, `scripts/`, `statusline/`, `src/`, `lib/`, `app/`, `cmd/`,
#      `internal/` or `pkg/` -- which is how a shell script with NO extension is caught.
#      It has to be caught by path, because the file may have been DELETED by these
#      commits and there is nothing left on disk to read a shebang out of.
#
# A file matching none of the three counts as neither, and neither triggers the gate nor
# satisfies it. Undercounting CODE only makes this gate more permissive, which is the
# direction it errs in on purpose.
#
# ====================================================================================
# THE ESCAPE HATCH, AND WHY IT IS SHAPED LIKE THIS
#
# A push that genuinely needs no documentation change has to be able to proceed, or the
# gate gets uninstalled. But an escape a session can take WITHOUT NOTICING IT TOOK ONE is
# not an escape, it is a hole. So both overrides cost a deliberate act, both require a
# written REASON, and both append a row to <state>/doc-gate/overrides.jsonl so the escape
# is COUNTED rather than invisible:
#
#   * `Doc-Gate-Override: <reason>` as a trailer in the HEAD commit message. Adding it
#     means writing it, or `git commit --amend`, and it stays in the history.
#   * `DOC_GATE_OVERRIDE="<reason>" git push ...` -- an environment assignment written
#     into the push command itself.
#
# THE INLINE FORM IS READ OUT OF THE COMMAND TEXT, NEVER OUT OF THIS PROCESS'S OWN
# ENVIRONMENT, and that is the load-bearing half of its design. An exported
# DOC_GATE_OVERRIDE in a shell profile would silence this gate forever with nothing on any
# surface to say why, and nobody would notice they had taken the escape -- which is
# exactly the shape this hatch is not allowed to have. Reading the command string means
# the escape is taken once, per push, in writing. The blunt off switch
# SKILL_COMPOUNDER_DOC_GATE=0 IS environment-read, because an off switch is supposed to be
# blunt and permanent, and it writes no row because it is not an escape from a finding --
# it is the gate not running.
#
# ====================================================================================
# IDEMPOTENCE, AND REFUSING A GIVEN HEAD ONLY ONCE PER SESSION
#
# Two separate claims, both atomic `mkdir`, because both wirings deliver every event
# twice (PLATFORM FACTS 3):
#
#   * THE DENY CLAIM is `<state>/doc-gate/denied/<sid>.<head-sha>`. It is taken at the
#     moment of denying, not at entry, so a push that passes leaves no state. Of two
#     racing deliveries exactly one `mkdir` succeeds and exactly one deny is emitted.
#     A session that pushes the SAME HEAD again gets through: the gate exists to force a
#     decision once, not to hold a session hostage, and claim-gate.sh's commit arm relents
#     the same way after MAX_DENY_SAME.
#     IF HEAD MOVED, THE MARKER NAME MOVES WITH IT and the push is judged from scratch --
#     which is the entire point, because the expected response to this deny is a new
#     commit carrying the documentation.
#   * THE OVERRIDE CLAIM is `<state>/doc-gate/claims/<sid>.<event-id>`, and it is
#     RELEASED AGAIN IF THE APPEND FAILS. The id is `.tool_use_id`, falling back to
#     `.prompt_id`, falling back to a `cksum` of the command and the HEAD sha -- which is
#     stable across the two deliveries of one event and so still collapses them.
#     The claim used to be taken BEFORE the append, which is the exact anti-pattern
#     .claude/CLAUDE.md names and which hooks/session-review.sh shipped first: with
#     `overrides.jsonl` present as a DIRECTORY the hook exited 0, wrote no row, and left
#     the claim behind, so repairing the store and re-delivering the identical event
#     wrote no row EVER (reproduced 2026-08-26). Both properties are kept at once by
#     making the claim span exactly the append and nothing else -- build the row into the
#     temp directory first, then `mkdir` the claim, then append, then `rmdir` the claim if
#     and only if the append failed. While the append is in flight the claim exists, so
#     the second delivery of the same event still finds it and writes nothing; once the
#     append has failed the claim is gone, so the event is not burnt.
#
# WHY THE DENY REASON DOES NOT ADVERTISE THE ONCE-PER-HEAD RULE. It is a loop guard, and
# saying "push again and it will go through" would make both overrides pointless while
# teaching the session to ignore the finding. claim-gate.sh sets the precedent in both
# directions: its Stop arm DOES disclose its per-turn cap, because a Stop block can
# genuinely loop a session and the user needs the way out; its PreToolUse arm does NOT
# disclose MAX_DENY_SAME, because a denied tool call cannot loop -- the model must change
# the command. This is a PreToolUse arm.
#
# ====================================================================================
# ENV (defaults in parentheses):
#   SKILL_COMPOUNDER_DOC_GATE  (1)  0 disables everything. Environment-read, on purpose.
#   DOC_GATE_NOW                 ()  epoch seconds; pins the clock for override rows.
#                                   THIS SCRIPT'S OWN CLOCK -- pinning CI_NOW or
#                                   SKILLFORGE_NOW does nothing here.
#   DOC_GATE_MAX_COMMITS      (100)  more commits ahead than this and the gate fails open.
#                                   A first push of an existing history is not the defect
#                                   this gate is for, and naming eight files out of four
#                                   hundred commits is noise rather than a finding.
#   DOC_GATE_CODE_EXCLUDE        ()  ERE; a path matching it is NEITHER rather than CODE.
#                                   Empty by default. `^tests?/` is the common setting.
#   DOC_GATE_MAX_NAMED          (8)  code files named in the deny reason. Floored at 1:
#                                   at 0 the reason listed no file at all and then said
#                                   "... and 1 more", which is a refusal that names
#                                   nothing (reproduced 2026-08-26).
#   DOC_GATE_DEBUG_DUMP          ()  append the raw stdin payload here.
#   DOC_GATE_OVERRIDE                NOT read from the environment -- see THE ESCAPE
#                                   HATCH. It is recognised only when written into the
#                                   push command itself.
#   SKILL_COMPOUNDER_STATE           state root ($HOME/.claude/skill-compounder).
#
# Any internal failure exits 0 and prints nothing. The only output this script ever
# produces is one deliberate deny naming specific files.

set -uo pipefail

# ------------------------------------------------------------------------------------
# THE ENTIRE BODY OF THIS SCRIPT IS ONE BRACE GROUP, AND THE `}` AT THE END OF THE FILE IS
# WHAT CLOSES IT. bash reads a script lazily by byte offset and resumes at that offset in
# whatever the file holds AT THAT MOMENT; every file in this package runs by absolute path
# out of the checkout, so a `git pull` mid-run rewrites bytes of a run already in flight. A
# brace group is one compound command, so the whole file must parse before any of it runs.
# The `exit` before the closing `}` is load-bearing too: a group protects its body and
# nothing past it, and a script that falls off the end can have bash resume past `}` and
# execute prepended text. See hooks/compound-improvement.sh for the measured reproduction
# and docs/DESIGN.md, "Never edit a script that may still be running", for the incident.
# ------------------------------------------------------------------------------------
{

# HOME can be unset (cron, a stripped env, a container). Under `set -u` reading it aborts
# the script non-zero, which is the one thing a hook may never do.
: "${HOME:=/tmp}"

ENABLED="${SKILL_COMPOUNDER_DOC_GATE:-1}"
MAX_COMMITS="${DOC_GATE_MAX_COMMITS:-100}"
CODE_EXCLUDE="${DOC_GATE_CODE_EXCLUDE:-}"
MAX_NAMED="${DOC_GATE_MAX_NAMED:-8}"
ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
STATE_DIR="$ROOT/doc-gate"

# Shape guards. A knob set to prose must not turn into an arithmetic error on stderr.
case "$MAX_COMMITS" in ''|*[!0-9]*) MAX_COMMITS=100 ;; esac
case "$MAX_NAMED" in ''|*[!0-9]*) MAX_NAMED=8 ;; esac
# ALL DIGITS IS NOT ENOUGH: bash's `[ x -lt y ]` prints "integer expected" on stderr for a
# value wider than intmax_t, so a twenty-digit knob is numeric to the guard above and
# still a hook writing to stderr. Measured: `[ 99999999999999999999 -lt 1 ]` -> "bash: [:
# 99999999999999999999: integer expected", status 2. Nine digits is far past any real
# setting of either knob.
[ "${#MAX_COMMITS}" -gt 9 ] && MAX_COMMITS=100
[ "${#MAX_NAMED}" -gt 9 ] && MAX_NAMED=8
# FLOOR OF 1. `head -n 0` prints nothing, so DOC_GATE_MAX_NAMED=0 produced a deny whose
# reason read "...among them:", a blank line, and "... and 1 more." -- a refusal naming no
# file, which is the one thing the reason exists to do. Reproduced 2026-08-26.
[ "$MAX_NAMED" -lt 1 ] && MAX_NAMED=1

[ "$ENABLED" = "0" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0
command -v git >/dev/null 2>&1 || exit 0

payload="$(cat)"
# `2>/dev/null` FIRST, everywhere in this file. bash applies redirections left to right,
# so with the order reversed a failing `>>` (an unwritable path, a directory where a file
# was expected) is reported on the shell's own stderr BEFORE the suppression exists. That
# was a real leak here: `overrides.jsonl` present as a directory printed "Is a directory"
# out of a hook that is supposed to print nothing but its decision. Reproduced 2026-08-26.
[ -n "${DOC_GATE_DEBUG_DUMP:-}" ] && { printf '%s\n' "$payload" 2>/dev/null >> "$DOC_GATE_DEBUG_DUMP" || :; }

jqr() { printf '%s' "$payload" | jq -r "$1" 2>/dev/null; }

# Dispatch on the event name, not on argv. Same contract as claim-gate.sh: one script,
# one wiring line, nothing positional to get wrong.
event="$(jqr '.hook_event_name // empty')"
[ "$event" = "PreToolUse" ] || exit 0
[ "$(jqr '.tool_name // empty')" = "Bash" ] || exit 0

cmd="$(jqr '.tool_input.command // empty')"
[ -z "$cmd" ] && exit 0

sid="$(jqr '.session_id // empty')"
[ -z "$sid" ] && sid="nosession"
# The IDENTICAL sanitising expression every other script in this package uses. It has to
# be identical: one event sanitised two ways becomes two claims under two spellings, and
# the double delivery then goes through both. Truncation matters as well as the character
# class -- a session id longer than NAME_MAX makes every state write fail ENAMETOOLONG.
sid="$(printf '%s' "$sid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"

cwd="$(jqr '.cwd // empty')"

TMP="$(mktemp -d 2>/dev/null)" || exit 0
cleanup() { [ -n "${TMP:-}" ] && rm -rf "$TMP" 2>/dev/null; }
trap cleanup EXIT

printf '%s' "$cmd" 2>/dev/null > "$TMP/cmd.txt" || exit 0

# ---------------------------------------------------------------- strip heredoc bodies
# A command that WRITES a document mentioning `git push` is not a push. This is the same
# awk claim-gate.sh uses to keep a heredoc body out of a commit message, reduced to the
# half needed here: print the lines OUTSIDE every heredoc body and drop the bodies.
# Each heredoc ends at its OWN delimiter, which is what claim-gate's first version got
# wrong -- it started at the first `<<` and swallowed the rest of the command.
# `<<<` is a here-STRING and opens no body; it is blanked in a same-length probe copy so
# the delimiter match cannot mistake `<<<"$MSG"` for a heredoc named `$MSG"`.
# The quote character is passed in as `q` because `\047` inside an awk regex constant is
# not portable and the program itself is single-quoted.
: 2>/dev/null > "$TMP/outside.txt" || exit 0
awk -v out="$TMP/outside.txt" -v q="'" '
  BEGIN { re = "<<-?[[:space:]]*([\"][^\"]+[\"]|" q "[^" q "]+" q "|[A-Za-z_][A-Za-z0-9_]*)" }
  {
    if (inh) {
      t = $0
      if (dash) sub(/^\t+/, "", t)
      sub(/[[:space:]]+$/, "", t)
      if (t == delim) inh = 0
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
      inh = 1
    }
  }
' "$TMP/cmd.txt" 2>/dev/null || :
[ -s "$TMP/outside.txt" ] || exit 0

# ------------------------------------------------------------------ split into segments
# `;`, `&`, `|`, `(` and `)` all end a command, so each becomes a line break. `&&` and
# `||` become two breaks, which costs nothing -- the empty segment between them matches
# nothing. Splitting is what lets the push matcher ANCHOR at a segment start instead of
# hunting the phrase anywhere in the text, and it is what makes `cd X && git push` and a
# push buried in a long chain both fall out for free.
# tr's set2 is written out in full rather than relying on the shorter-set2 padding rule,
# which differs between implementations.
tr ';&|()' '\n\n\n\n\n' 2>/dev/null < "$TMP/outside.txt" > "$TMP/segments.txt" || exit 0

SQ="'"
DQ='"'
# STRIP QUOTES ONCE, HERE, AND NEVER AT A USE SITE. The tokeniser below is `set --
# $push_seg` over the RAW command text, so a word the shell would have unquoted arrives
# still wearing its quotes: `--recurse-submodules "only"` was not recognised as `only`, and
# that is the REFUSING direction -- a push that was never going to carry the superproject
# was denied for the code it names (reproduced 2026-08-26). Two shapes, one matching pair
# stripped from each: a whole word (`"only"`, `'main'`, `"+main:main"`) and the value half
# of an OPTION word (`--recurse-submodules="only"`). The second is restricted to words
# beginning with `-` on purpose: a refspec may legally contain `=` and splitting one on it
# would maul the branch name. Sets `UQ` rather than printing, so a token costs no fork.
unquote() {
  uq_pre=""
  UQ="$1"
  case "$UQ" in
    -*=*) uq_pre="${UQ%%=*}="; UQ="${UQ#*=}" ;;
  esac
  case "$UQ" in
    "$DQ"*"$DQ"|"$SQ"*"$SQ") UQ="${UQ#?}"; UQ="${UQ%?}" ;;
  esac
  UQ="$uq_pre$UQ"
}
# A leading run of `NAME=value` environment assignments, with the value bare, "double" or
# 'single' quoted. `GIT_SSH_COMMAND="ssh -i k" git push` is a real shape and a bare
# `[^[:space:]]*` would stop at the space inside the quotes.
ASSIGN="[A-Za-z_][A-Za-z0-9_]*=(${DQ}[^${DQ}]*${DQ}|${SQ}[^${SQ}]*${SQ}|[^[:space:]]*)[[:space:]]+"
# One of git's own options. Two alternatives, and the split is the whole point:
#   * the SEVEN options that genuinely take a separate argument, which take one here;
#   * every other option, which takes none.
# The first alternative is what makes `git -C /path push` work -- `-C` and `/path` are two
# tokens, and claim-gate's commit matcher, which only ever needed `git -c k=v commit`,
# does not allow for it. Letting EVERY option take an optional separate argument was the
# obvious generalisation and the wrong one: it let `--no-pager` swallow a SUBCOMMAND, so
# `git --no-pager stash push` matched PUSH_RE and was denied, as did the `checkout` and
# `branch` spellings (reproduced 2026-08-26). `git stash push` and `git -C /tmp/x stash
# push` never matched, which is what made the option the culprit rather than `stash`.
# POSIX matching finds a match if ANY parse yields one, so `git --no-pager push` still
# matches through the second alternative.
GITOPT_ARG="(-C|-c|--git-dir|--work-tree|--namespace|--exec-path|--super-prefix)"
GITOPT="([[:space:]]+${GITOPT_ARG}[[:space:]]+[^[:space:]]+|[[:space:]]+-[^[:space:]]+)"
PUSH_RE="^[[:space:]]*(${ASSIGN})*git${GITOPT}*[[:space:]]+push([[:space:]]|\$)"
CD_RE="^[[:space:]]*cd[[:space:]]+[^[:space:]-]"
DRYRUN_RE="(^|[[:space:]])(--dry-run|-n)([[:space:]]|\$)"

push_seg=""
cd_target=""
while IFS= read -r seg; do
  [ -z "$seg" ] && continue
  if printf '%s' "$seg" | grep -qE "$PUSH_RE" 2>/dev/null; then
    # A dry run writes to no remote, so there is nothing to gate and refusing it would
    # only refuse the safest way to look at what a push would do.
    printf '%s' "$seg" | grep -qE "$DRYRUN_RE" 2>/dev/null && continue
    push_seg="$seg"
    break
  fi
  # A `cd` BEFORE the push in the same command decides which repository the push is
  # about. Last one wins, exactly as the shell would have it. Only segments preceding the
  # push are consulted, which is why this loop breaks rather than reading on.
  if printf '%s' "$seg" | grep -qE "$CD_RE" 2>/dev/null; then
    cd_target="$(printf '%s' "$seg" \
      | sed -E "s/^[[:space:]]*cd[[:space:]]+//; s/[[:space:]].*\$//; s/^[${DQ}${SQ}]//; s/[${DQ}${SQ}]\$//")"
  fi
done < "$TMP/segments.txt"

[ -z "$push_seg" ] && exit 0

# ------------------------------------------------------------------ which repository
# `git -C <path>` beats a preceding `cd`, because that is what git does with it.
c_target="$(printf '%s' "$push_seg" \
  | sed -nE "s/.*(^|[[:space:]])-C[[:space:]]+(${DQ}[^${DQ}]*${DQ}|${SQ}[^${SQ}]*${SQ}|[^[:space:]]+).*/\\2/p" \
  | sed -E "s/^[${DQ}${SQ}]//; s/[${DQ}${SQ}]\$//")"
[ -n "$c_target" ] && cd_target="$c_target"

workdir="$cwd"
if [ -n "$cd_target" ]; then
  case "$cd_target" in
    /*) workdir="$cd_target" ;;
    '~'*) workdir="" ;;   # not expanded here; an unexpanded ~ would name a literal dir
    *) workdir="$cwd/$cd_target" ;;
  esac
fi
[ -n "$workdir" ] && [ -d "$workdir" ] || exit 0

g() { git -C "$workdir" "$@" 2>/dev/null; }

# ------------------------------------------------------------ what is about to leave
# Every one of these failing means the gate cannot see, and a gate that blocks when it
# cannot see blocks at random.
g rev-parse --git-dir >/dev/null 2>&1 || exit 0
g symbolic-ref -q HEAD >/dev/null 2>&1 || exit 0          # detached HEAD
g rev-parse --verify -q '@{u}' >/dev/null 2>&1 || exit 0  # no upstream configured

# The branch the gate is about to judge. Needed by the refspec reading below, which asks
# whether the push sends THIS branch; a push of some other branch is judged by nothing
# `@{u}..HEAD` can see, so it is not this gate's business.
branch="$(g symbolic-ref --short -q HEAD)"
[ -z "$branch" ] && exit 0

# ----------------------------------------------------- does the refspec send a commit?
# See REFSPEC in the header for the shapes handled and the ones deliberately not. The
# invariant: `sends=0` unless the push can be SHOWN to carry the current branch.
sends=1
tail_seen=0; skipnext=0; npos=0; nrefs=0
# EVERY OPTION BELOW HOLDS THE VALUE OF THE LAST SPELLING SEEN, BECAUSE THAT IS HOW GIT
# RESOLVES THEM. See LAST-WINS in the header for the table and for how it was measured.
# These were one-way latches, and a latch is wrong in whichever direction it sticks: the
# `only` latch let `--recurse-submodules=only --recurse-submodules=on-demand` through
# while git really did send the superproject, and the `--tags` latch did the same for
# `--tags --no-tags` (both reproduced 2026-08-26).
# `--all`/`--branches` and `--mirror` are TWO variables, not one, which is also measured:
# `--no-all` leaves `--mirror` set.
v_delete=0; v_tags=0; v_branches=0; v_mirror=0; v_rs=""
rs_next=0
: 2>/dev/null > "$TMP/refspecs.txt" || exit 0
# `set -f` first: without it the shell would glob a `*` inside the segment against the
# working directory and turn one token into many. `set --` is safe here because this
# script is invoked with no positional parameters of its own.
set -f
# shellcheck disable=SC2086  # deliberate word splitting: this is the tokeniser
set -- $push_seg
set +f
for tok in "$@"; do
  unquote "$tok"; tok="$UQ"
  if [ "$tail_seen" -eq 0 ]; then
    # The first bare `push` word ends the option run PUSH_RE already matched. `-c
    # push.default=simple` is not it, and neither is an assignment like `X=push`.
    [ "$tok" = "push" ] && tail_seen=1
    continue
  fi
  if [ "$skipnext" -eq 1 ]; then
    skipnext=0
    # The ONE consumed word that is not merely stepped over. `--recurse-submodules` takes
    # its value as a separate word as well as with `=` -- measured on git 2.50.1:
    # `git push --recurse-submodules --dry-run` dies with "bad recurse-submodules
    # argument: --dry-run", so the following word really is eaten -- and `only` is the
    # value that leaves the superproject unpushed. Discarding it the way the other five
    # consumed words are discarded would lose the one bit that matters and would ALSO
    # shift the positional count, reading the remote as a refspec. It is ASSIGNED, not
    # OR-ed: a later spelling must be able to overwrite an earlier `only`.
    if [ "$rs_next" -eq 1 ]; then
      rs_next=0
      v_rs="$tok"
    fi
    continue
  fi
  case "$tok" in
    '>'*|'<'*|[0-9]'>'*) break ;;   # a redirection ends the argument list
    --) continue ;;
    --delete|-d) v_delete=1 ;;
    --no-delete) v_delete=0 ;;
    --tags) v_tags=1 ;;
    --no-tags) v_tags=0 ;;
    # `--follow-tags` IS NOT `--tags`, AND LUMPING THEM TOGETHER OPENED A HOLE STRAIGHT
    # THROUGH THIS GATE. `--tags` pushes refs/tags/* INSTEAD of the branch;
    # `--follow-tags` pushes the branch AND its reachable annotated tags. Measured on git
    # 2.50.1 with one commit ahead and one annotated tag: `git push --tags --dry-run`
    # prints only `v1.0.0 -> v1.0.0`, `git push --follow-tags --dry-run` prints
    # `main -> main` AND the tag. So a code-only push spelled `git push --follow-tags`
    # was allowed with no override recorded -- exactly the push this file exists to
    # refuse (reproduced 2026-08-26). It is judged as a bare `git push` is, and it is
    # named here rather than left to the `-*` arm below so it cannot drift back.
    # `--tags` ALONGSIDE `--follow-tags` still sends only tags, in either order (measured
    # the same way), which is why `--tags` keeps its own arm rather than both being
    # dropped. The two families are INDEPENDENT, also measured: `--tags --no-follow-tags`
    # still sends only the tag, so `--no-follow-tags` is not a way to clear `--tags`.
    --follow-tags|--no-follow-tags) ;;
    # `--recurse-submodules=only` pushes the submodules and leaves the SUPERPROJECT
    # unpushed, so no commit of this branch leaves. Measured on git 2.50.1: with one
    # commit ahead, `--dry-run` prints `Everything up-to-date` -- with no refspec, with
    # `origin main`, with `origin HEAD` and alongside `--all`. The other three values
    # (`check`, `on-demand`, `no`) and `--no-recurse-submodules` all DO send the
    # superproject, and any of them coming after `only` wins.
    --recurse-submodules=*) v_rs="${tok#--recurse-submodules=}" ;;
    --recurse-submodules) skipnext=1; rs_next=1 ;;
    --no-recurse-submodules) v_rs="" ;;
    --all|--branches) v_branches=1 ;;
    --no-all|--no-branches) v_branches=0 ;;
    --mirror) v_mirror=1 ;;
    --no-mirror) v_mirror=0 ;;
    # The five options that consume the following word, measured rather than assumed: run
    # `git push <opt> __SENT__ --dry-run` and read what git calls `__SENT__`. These five
    # report it as their own value; every other push option reports "'__SENT__' does not
    # appear to be a git repository", which means it landed in the REMOTE positional and
    # the option ate nothing.
    --repo|-o|--push-option|--receive-pack|--exec) skipnext=1 ;;
    -*) ;;
    *)
      npos=$((npos + 1))
      # `git push [<remote> [<refspec>...]]` -- the first positional is the remote.
      if [ "$npos" -gt 1 ]; then
        nrefs=$((nrefs + 1))
        printf '%s\n' "$tok" 2>/dev/null >> "$TMP/refspecs.txt" || :
      fi
      ;;
  esac
done

# The verdict inputs, derived from the LAST value of each option rather than from whether
# a spelling was ever seen. `--all`/`--branches` and `--mirror` are folded together only
# HERE, at the one question this gate asks of them -- "is refs/heads/* being sent?" --
# because git keeps them apart and `--no-all` must not switch off a mirror.
f_delete="$v_delete"
f_tags="$v_tags"
f_nosuper=0
[ "$v_rs" = "only" ] && f_nosuper=1
f_allrefs=0
[ "$v_branches" -eq 1 ] && f_allrefs=1
[ "$v_mirror" -eq 1 ] && f_allrefs=1

if [ "$f_delete" -eq 1 ]; then
  sends=0                                   # a deletion sends no commit
elif [ "$f_nosuper" -eq 1 ]; then
  sends=0                                   # submodules only; the superproject stays put
elif [ "$nrefs" -eq 0 ]; then
  # No refspec: `--tags` alone pushes refs/tags/* and nothing else. Anything else is the
  # default push of the current branch, which is exactly what `@{u}..HEAD` describes.
  [ "$f_tags" -eq 1 ] && [ "$f_allrefs" -eq 0 ] && sends=0
else
  sends=0
  while IFS= read -r rs; do
    [ -z "$rs" ] && continue
    rs="${rs#+}"                            # `+src:dst` is a forced push of src
    src="${rs%%:*}"
    # NO QUOTE STRIPPING HERE: `unquote` did it once, in the tokeniser, before the token
    # was ever written to this file. Stripping at each use is what left the `only`
    # detection quoted-out while the refspec arm happened to have its own sed.
    [ -z "$src" ] && continue               # `:branch` is the deletion spelling
    # `@` is git's documented shorthand for `HEAD` (gitrevisions: "@ alone is a shortcut
    # for HEAD"), so `git push origin @` and `@:refs/heads/x` are pushes of this branch
    # and were escaping the gate. Compared with `=`, not a pattern: a branch may legally
    # be NAMED `@foo` (`git check-ref-format` accepts it) and that is a different ref.
    # THE LIMIT IS ENUMERATED, NOT SILENT. The revision EXPRESSIONS that also resolve to
    # HEAD -- `@{0}`, `HEAD~0`, `HEAD^0`, `HEAD^{commit}` -- are NOT handled and pass.
    # Resolving them would mean handing `$src` to `git rev-parse` and comparing shas, and
    # that is not a bigger version of this test, it is a different one: it would resolve
    # `v1.0.0` to HEAD too and start judging the tag push that HANDLED, PASSED above
    # deliberately exempts. Literal synonyms are matched literally; expressions are left
    # to the fail-open direction this whole file errs in.
    if [ "$src" = "HEAD" ] || [ "$src" = "@" ] || \
       [ "$src" = "$branch" ] || [ "$src" = "refs/heads/$branch" ]; then
      sends=1
      break
    fi
  done < "$TMP/refspecs.txt"
  # `--all`/`--mirror` push refs/heads/*, which contains the current branch whatever else
  # was named alongside them.
  [ "$f_allrefs" -eq 1 ] && sends=1
fi
[ "$sends" -eq 0 ] && exit 0

head_sha="$(g rev-parse HEAD)"
case "$head_sha" in ''|*[!0-9a-f]*) exit 0 ;; esac

ahead="$(g rev-list --count '@{u}..HEAD')"
case "$ahead" in ''|*[!0-9]*) exit 0 ;; esac
[ "$ahead" -eq 0 ] && exit 0
# A first push of an existing history is not the defect this gate is for.
[ "$ahead" -gt "$MAX_COMMITS" ] && exit 0

# THREE DOTS, NOT TWO. `@{u}...HEAD` diffs the merge base against HEAD, so a diverged
# upstream (someone else pushed while this branch was being written) does not drag their
# files into this push's file list. Two dots would.
base="$(g merge-base '@{u}' HEAD)"
case "$base" in ''|*[!0-9a-f]*) exit 0 ;; esac
# `-z`, AND THE READ BELOW IS NUL-SEPARATED TO MATCH. Without it `git diff --name-only`
# C-QUOTES any path holding a non-ASCII byte: `docs/café.md` comes back as the eleven
# characters `"docs/caf\303\251.md"`, surrounding double quotes included. Those quotes
# defeat both of DOC_RE's anchors -- `(^|/)` cannot see past the leading `"` and `$`
# cannot see past the trailing one -- so a REAL documentation file was classified NEITHER
# and the push was denied for carrying no documentation. That is the one outcome this gate
# must never produce, and it was reproduced on 2026-08-26. `-z` disables the quoting
# entirely rather than only for non-ASCII, so a path containing a quote, a backslash or a
# newline survives it too; `core.quotePath=false` would have fixed only the first of those.
g diff -z --name-only "$base" HEAD 2>/dev/null > "$TMP/files.txt" || exit 0
[ -s "$TMP/files.txt" ] || exit 0

# ------------------------------------------------------------------- classification
# See CLASSIFICATION in the header for why the order is NEITHER, DOC, CODE and why
# `notes/` is where it is.
NEITHER_RE='^notes?/|(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|Gemfile\.lock|go\.sum|composer\.lock)$|\.(png|jpg|jpeg|gif|svg|ico|pdf|zip|gz|tgz|bz2|xz|woff2?|ttf|otf|eot|mp4|mp3|wav|bin|so|dylib|dll|exe|class|jar|pyc)$|(^|/)\.(gitignore|gitattributes|editorconfig)$|(^|/)LICEN[CS]E([.-][^/]*)?$'
DOC_RE='(^|/)(README|CHANGELOG|CHANGES|CONTRIBUTING|HISTORY|INSTALL|USAGE|CLAUDE|AGENTS)([.-][^/]*)?$|\.(md|markdown|rst|adoc|asciidoc|org|texi|1)$|(^|/)(docs?|documentation|man|manpages)/'
CODE_RE='\.(py|pyi|js|jsx|mjs|cjs|ts|tsx|sh|bash|zsh|fish|rb|go|rs|c|h|cc|cpp|cxx|hpp|hh|java|kt|kts|swift|m|mm|cs|php|pl|pm|lua|r|jl|scala|clj|ex|exs|erl|hs|sql|vim|el|tf|proto|gradle|cmake|bat|ps1)$|\.(json|ya?ml|toml|ini|cfg|conf|properties|env)$|(^|/)(Makefile|makefile|GNUmakefile|Dockerfile|Containerfile|Justfile|justfile|Rakefile|Gemfile|Procfile|CMakeLists\.txt|setup\.py|setup\.cfg)$|(^|/)(bin|hooks|scripts|statusline|src|lib|app|cmd|internal|pkg)/'

: 2>/dev/null > "$TMP/code.txt" || exit 0
n_doc=0
# `read -d ''` reads to the next NUL, matching the `-z` above. LC_ALL=C on every classifier
# so the regexes match BYTES: under a UTF-8 locale BSD grep aborts on a path that is not
# valid UTF-8, and a failed `grep -q` on DOC_RE would silently unclassify a real doc file
# and deny the push -- the same wrong direction the C-quoting bug took.
while IFS= read -r -d '' f; do
  [ -z "$f" ] && continue
  printf '%s' "$f" | LC_ALL=C grep -qE "$NEITHER_RE" 2>/dev/null && continue
  if printf '%s' "$f" | LC_ALL=C grep -qE "$DOC_RE" 2>/dev/null; then
    n_doc=$((n_doc + 1))
    continue
  fi
  if [ -n "$CODE_EXCLUDE" ]; then
    printf '%s' "$f" | LC_ALL=C grep -qE "$CODE_EXCLUDE" 2>/dev/null && continue
  fi
  printf '%s' "$f" | LC_ALL=C grep -qE "$CODE_RE" 2>/dev/null && printf '%s\n' "$f" 2>/dev/null >> "$TMP/code.txt"
done < "$TMP/files.txt"

# One documentation file anywhere in the push is enough. This gate asks whether the
# session THOUGHT about the documentation, not whether it wrote enough of it -- judging
# sufficiency needs a model, and a deterministic hook that pretends to do it would be
# refusing on a guess.
[ "$n_doc" -gt 0 ] && exit 0
n_code="$(grep -c . "$TMP/code.txt" 2>/dev/null | tr -cd '0-9')"
case "$n_code" in ''|*[!0-9]*) n_code=0 ;; esac
[ "$n_code" -eq 0 ] && exit 0

# ------------------------------------------------------------------- the escape hatch
# Both forms require a non-empty reason, and both are recorded. See THE ESCAPE HATCH in
# the header for why the inline form is read out of the command text and never out of
# this process's own environment.
ov_kind=""
ov_reason=""

trailer="$(g log -1 --format=%B \
  | grep -iE '^[[:space:]]*Doc-Gate-Override:[[:space:]]*[^[:space:]]' \
  | tail -1 \
  | sed -E 's/^[[:space:]]*[^:]*:[[:space:]]*//; s/[[:space:]]+$//')"
if [ -n "$trailer" ]; then
  ov_kind="trailer"
  ov_reason="$trailer"
else
  inline="$(printf '%s' "$push_seg" \
    | sed -nE "s/.*DOC_GATE_OVERRIDE=(${DQ}([^${DQ}]*)${DQ}|${SQ}([^${SQ}]*)${SQ}|([^[:space:]]*)).*/\\2\\3\\4/p" \
    | head -1 | sed -E 's/[[:space:]]+$//')"
  if [ -n "$inline" ]; then
    ov_kind="inline"
    ov_reason="$inline"
  fi
fi

now="${DOC_GATE_NOW:-$(date +%s)}"
case "$now" in ''|*[!0-9]*) now="0" ;; esac

if [ -n "$ov_kind" ]; then
  # jq -n builds the row FIRST, into the temp directory, so a reason containing a quote,
  # a newline or a backslash cannot produce a line that no reader can parse -- and so
  # that nothing is claimed on behalf of a row that could not even be built.
  # The file list goes in through `--arg` and a command substitution rather than
  # `--rawfile`, which jq did not gain until 1.6; nothing else in this package needs
  # 1.6, and a hook that silently stops recording on an older jq is the failure mode
  # this whole file is written against.
  jq -n -c \
    --arg ts "$now" --arg session "$sid" --arg head "$head_sha" \
    --arg kind "$ov_kind" --arg reason "$ov_reason" --arg cwd "$workdir" \
    --arg commits "$ahead" --arg code "$n_code" \
    --arg files "$(cat "$TMP/code.txt" 2>/dev/null)" \
    '{ts:($ts|tonumber), event:"override", session:$session, head:$head,
      kind:$kind, reason:$reason, cwd:$cwd,
      commits:($commits|tonumber), code_files:($code|tonumber),
      files:($files|split("\n")|map(select(length>0))|.[0:8])}' \
    2>/dev/null > "$TMP/row.json" || exit 0
  [ -s "$TMP/row.json" ] || exit 0

  # Claim the EVENT, not the push, so the two deliveries of one event write one row.
  # `.tool_use_id` is present on every measured PreToolUse payload; the cksum fallback is
  # for a payload shape that ever drops it, and it is stable across both deliveries of
  # the same event because it is derived from the command and the sha rather than from
  # anything per-delivery.
  eid="$(jqr '.tool_use_id // .prompt_id // empty')"
  [ -z "$eid" ] && eid="ck$(printf '%s%s' "$cmd" "$head_sha" | cksum 2>/dev/null | tr -c 'A-Za-z0-9' '_')"
  eid="$(printf '%s' "$eid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96)"
  mkdir -p "$STATE_DIR/claims" 2>/dev/null || exit 0
  claim="$STATE_DIR/claims/$sid.$eid"
  mkdir "$claim" 2>/dev/null || exit 0
  # BOTH PROPERTIES AT ONCE -- idempotent under the double delivery, and not burnt by a
  # failed append -- because the claim spans EXACTLY the append and nothing else. While
  # the append is in flight the claim exists, so the duplicate delivery finds it and
  # writes nothing; if the append fails the claim is removed again, so repairing the store
  # and re-delivering the identical event still records the override. Taking it before the
  # row was even built is the anti-pattern .claude/CLAUDE.md names and the bug
  # hooks/session-review.sh shipped first: with `overrides.jsonl` present as a DIRECTORY
  # the event was burnt and could never be recorded (reproduced 2026-08-26).
  # An append of a single line under the pipe buffer is atomic enough for two racing
  # processes, and the claim means there should not be two.
  if ! cat "$TMP/row.json" 2>/dev/null >> "$STATE_DIR/overrides.jsonl"; then
    rmdir "$claim" 2>/dev/null || :
  fi
  exit 0
fi

# ------------------------------------------------------------------------ deny, once
# Fail OPEN if the state directory cannot be written. The alternative -- denying without
# a marker -- refuses the same push on every retry with no way out but the off switch,
# which is a hook breaking the user's work rather than steering it.
mkdir -p "$STATE_DIR/denied" 2>/dev/null || exit 0
marker="$STATE_DIR/denied/$sid.$head_sha"
# Fail CLOSED on the mkdir itself, exactly as claim-gate.sh does at its Stop block: mkdir
# failing because the marker exists means either the duplicate delivery or a second push
# of this same HEAD, and both must stay silent. mkdir failing for any other reason lands
# here too, and silence is the safe answer for that as well.
mkdir "$marker" 2>/dev/null || exit 0
printf '%s\n' "$now" 2>/dev/null > "$marker/at" || :

# Housekeeping: markers are tiny and per-HEAD, but a long-lived state directory should
# not accumulate them forever.
find "$STATE_DIR/denied" -mindepth 2 -depth -type f -mtime +7 -delete 2>/dev/null
find "$STATE_DIR/denied" -mindepth 1 -maxdepth 1 -type d -mtime +7 -empty -exec rmdir {} + 2>/dev/null
find "$STATE_DIR/claims" -mindepth 1 -maxdepth 1 -type d -mtime +7 -empty -exec rmdir {} + 2>/dev/null

named="$(head -n "$MAX_NAMED" "$TMP/code.txt" 2>/dev/null | sed 's/^/    - /')"
more=""
if [ "$n_code" -gt "$MAX_NAMED" ]; then
  more="
    ... and $((n_code - MAX_NAMED)) more."
fi
# The whole clause, not just the noun: an earlier version pluralised `commit` and left
# `are` hardcoded, so a single-commit push read "1 commit are about to leave". The test
# that was supposed to cover it asserted only the substring "1 commit", which the broken
# string also contains -- a real reminder that an assertion loose enough to pass either
# way is not a test. The sentence continues with a participle rather than a second finite
# verb for the same reason: "They touch" would have been wrong for one commit too.
lead="$ahead commits are"
[ "$ahead" -eq 1 ] && lead="1 commit is"

# PHRASED AS A STATEMENT, NEVER AS AN INSTRUCTION. Measured (PLATFORM FACTS 2): the model
# correctly refuses to follow directives arriving through a blocked tool call, so an
# imperative here is both ignored and misleading about who is asking. The remedy is named
# as a fact about what exists -- which is the register that survived the probe.
reason="This push carries code changes and no documentation change.

$lead about to leave this repository, touching these code files and not one
documentation file among them:
${named}${more}

The \`claim-provenance\` skill exists for exactly this. Its Iron Law is RESTATE NOTHING,
RE-DERIVE EVERY CLAIM FROM THE THING IT DESCRIBES, OR DELETE IT, and its first phase turns
a diff into a bounded list of prose claims the change could have made false. A push made
after it has run carries a documentation change and this gate does not see it.

If this push genuinely needs no documentation change, there are two ways to say so, and
both are recorded in $STATE_DIR/overrides.jsonl so the exception is counted rather than
invisible:
  * a \`Doc-Gate-Override: <reason>\` trailer in the HEAD commit message, or
  * running the push as \`DOC_GATE_OVERRIDE=\"<reason>\" git push ...\`.

Nothing was pushed and nothing was written."

jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny", permissionDecisionReason:$r}}' 2>/dev/null || exit 0
exit 0

}
