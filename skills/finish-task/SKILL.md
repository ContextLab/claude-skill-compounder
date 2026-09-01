---
name: finish-task
description: "Use when a unit of work is done and the pre-publish sequence still has to run: 'this feature is done, get it ready to push', 'what's left before I can merge?', 'wrap up this branch'. Do NOT use when review, sweep and docs are already done and only merging is left (`superpowers:finishing-a-development-branch`), for doc audits (`claim-provenance`), one completion claim (`superpowers:verification-before-completion`), or a bug under diagnosis (`superpowers:systematic-debugging`)."
---

# Finish task

Between "I think this is done" and the work being publishable there is a fixed sequence that does not vary with
the task: an adversarial review by someone who did not write it, the whole verification sweep rather than the
subset you were iterating on, the durable prose brought back into agreement with the code, a written record,
and only then the integration decision. Every one is skippable with no immediate consequence, exactly when you
most want to be done, so all are skipped by default.

**What makes this a procedure and not a checklist** is two properties a list of boxes cannot carry:

1. **The steps are ordered by what invalidates what.** Fixing a review finding invalidates the sweep; changing
   code invalidates the prose. So a run that *finds* anything goes **backwards**. A checklist ticked top to
   bottom ships a green sweep that predates the fix it covers.
2. **The reviewer must not be the author**, and must not be a *fork* of the author either — that is what makes
   an adversarial step return "looks fine" every time.

**This skill owns the sequence and nothing else.** Three of its steps are whole procedures with owners of
their own; it **invokes** all three and restates none. What is left is the ordering, the non-fork reviewer,
the whole-sweep discipline, the record, the loop back, one rule about the branch, and the named end state a
run stops in when the loop will not converge (Phase 7). Six files in `references/` sit beside it and none
carries a step. **Any failure, in any phase, is a lookup before it is a decision:** open `unhappy-path.md`
the moment anything fails and find its row — it names what the failure voids and which phase to run *forward*
from, the failures that read like success included. `red-flags.md` is the companion for a phase that has begun
to feel avoidable, and `the-base-ladder.md`, `where-the-record-lives.md`, `what-a-dispatch-leaves-behind.md`
and `proving-the-sweep-ran-your-code.md` hold the measurement behind a rule stated here.

## When this is the wrong skill

**The three it composes**, each mandatory where its phase names it and none of them duplicated here.
**`stale-artifact-check`** owns the proof that a run contained your change — the observed canary, its
placement, its reading, the absent case, its removal (Phase 3). **`claim-provenance`** owns the
prose-versus-code audit — the sweep over a document, the re-derivability sort, the disposal of what cannot
be re-derived, and the trap where an assertion pins a document's *presence* rather than its *truth*
(Phase 4). **`superpowers:finishing-a-development-branch`** owns the integration decision — the merge/PR/keep
menu, base-branch confirmation, worktree cleanup, the confirmation path for discarding work (Phase 6); do not reproduce its menu or decide integration yourself.

**Skills this is not.** `superpowers:requesting-code-review` owns *how* to review — use it **inside** Phase 2.
`superpowers:verification-before-completion` fires on a single completion claim; this is the sequence around
it. `superpowers:systematic-debugging` owns a failure under diagnosis. `session-handoff` owns a record written
because context is about to be lost; Phase 5's is written because the task is *ending*.
`oh-my-claudecode:verify`, if you have it, is a deliberately narrow check, not this.

**When this is not worth its own cost:** a unit of work nobody else will run or read — a throwaway spike, a
scratch experiment, an edit to a file no test, no document and no other person depends on.

## The commit rule

Read this once; every phase below is bound by it. It is one rule rather than three notes because the same
defect arrived in three separate phases.

> **A phase's deliverable is not produced until it is committed, by name, on this branch. No phase hands over
> to the next one with an edit of its own still sitting in the working tree.**

| Phase | What it produces | Committed |
|-|-|-|
| 0 | a sentence, a base, a path, a directory — no files in the tree | — |
| 1 | the unit of work | at the end of Phase 1, before the reviewer is dispatched |
| 2 | findings, which are prose in your reply. Any **fix** you make is Phase 1's deliverable again | back in Phase 1, before the next dispatch |
| 3 | nothing of its own: the canary is removed, never committed | — |
| 4 | the prose corrections `claim-provenance` produced | at the end of Phase 4, before the re-sweep |
| 5 | the record — a file, or a commit body; never a PR description alone | at the end of Phase 5, in its own commit, then one confirming sweep |
| 6 | nothing; it hands the branch to another skill | — |
| 7 | the fixes for what was already reproduced, and the record naming the disposition | as Phase 1 and Phase 5 say; nothing is published |

**Stage by name.** `git add <path> <path>` — **never `git add -A` and never `git add .`**. The tree contains
things you did not write, and the reflex commits all of them; read `git diff --cached --name-only` before
committing, and every path must be one you can name as part of the work. **Check the tree at the end of every
phase** with `git status --porcelain -uall`: every ` M`, ` D` or `??` line is work of yours to commit or
tooling state to leave alone, and you must be able to say which, by name. **If this is not a git repository**
the rule holds in the only form available — the deliverables are files in a tree, your reply must name where
each is, and Phase 1's packet becomes whatever diff you can produce.

## Phase 0: Fix the boundary, name the base, declare the record, make a scratch directory

**1. Write down, in one sentence, what the unit of work is** and what would count as it being wrong. Everything
later is judged against this sentence. If you cannot write it, you are not finishing; you are stopping.

**2. Name the base** — the commit or branch this work forked from, derived without asking. The ladder takes the
first candidate that exists and is **not HEAD itself**, the root commit included:

```bash
root="$(git rev-list --max-parents=0 HEAD 2>/dev/null | tail -1)"; base=""
for cand in "$(git rev-parse --abbrev-ref '@{u}' 2>/dev/null)" \
            "$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)" \
            origin/main origin/master main master "$root"; do
  [ -n "$cand" ] || continue
  git rev-parse --verify --quiet "$cand^{commit}" >/dev/null 2>&1 || continue
  [ "$(git rev-parse "$cand")" = "$(git rev-parse HEAD)" ] && continue   # never HEAD itself
  base="$cand"; break
done
if   [ -z "$base" ];                           then echo "base=UNDETERMINED rung=none"
elif [ "$(git rev-parse "$base")" = "$root" ]; then echo "base=$base rung=ROOT-FALLBACK"
else                                                echo "base=$base rung=named"; fi
```

**Only `rung=named` is a fork point.** Before Phase 1, `ROOT-FALLBACK` and `UNDETERMINED` are both wrong in
**both** directions at once, so **do not write either down and do not build a packet from one**; a
named-and-wrong base is worse than a gap. **Run the block again at the end of Phase 1** and use that value;
if it still is not `named`, `references/the-base-ladder.md` says what to dispatch on and what to record.
**Write the printed value down, with its `rung`**: `base` is a shell variable and **every Bash tool call is a
fresh shell**, so Phase 2 retypes it literally, never `"$base"`.

**3. Declare where the record will go** — now, so it is not invented at the end: one real path in your
project's convention (`notes/<yyyy-mm-dd>-what-this-was.md` is the shape, not the answer). **Check that git
will accept it, now**, because the directories a "durable note" convention names are exactly the ones
projects ignore:

```bash
git check-ignore -q notes/<yyyy-mm-dd>-what-this-was.md \
  && echo "IGNORED: plain 'git add' REFUSES it -- move it, or plan on 'git add -f' in Phase 5" || echo ok
```

An ignored path makes `git add` exit **1** while the `git commit` after it reports a clean tree (Phase 5 says
how that reads). Prefer moving the record over `git add -f`, and **prefer a path the sweep does not read** so
the confirming sweep cannot come back red *because of the record*. **The record has two homes and the PR
description is not one of them** — a file on the branch, or a commit body on it — because two of the three
integration options never open a pull request, and the human picks (`references/where-the-record-lives.md`).

**4. Make this finish's scratch directory.** Phases 1, 2 and 3 write logs and snapshots, and none may be
written inside the repository. A fixed `/tmp` path is shared with every finish this machine has run, so make
one that cannot already exist:

```bash
mktemp -d /tmp/finish-XXXXXX   # THIS finish's dir. Retype it wherever a later block says /tmp/finish-REPLACE.
```

**The literal `/tmp/finish-REPLACE` in every later block is a placeholder that does not exist**, and that is
the second half of the guard: a missed retype fails loudly (`>` into it exits **1**) instead of contaminating
another finish. Do not `mkdir` it to silence the error; the error *is* the check. After a handoff run
`mktemp -d` again; Phase 6 removes it.

## Phase 1: Bring your own house to a stop

**Commit — and know what you are committing.** Not the sweep; this is so the Phase 2 reviewer reads a
coherent thing rather than a half-applied edit. Four steps, in order.

**1. Read the whole tree state.** `git status --porcelain -uall`. Without `-uall` git collapses an
entire untracked directory into one line, and one collapsed line is how thirty files enter a commit.

**2. Subtract what you did not write.** Every round after the first arrives straight out of Phase 2, and **a
dispatched reviewer writes into your repository** — agent state, caches, logs, some carrying absolute paths
from your machine. Phase 2 named that set by bracketing the dispatch; re-read the tree now rather than trusting
the list, because the writing does not stop when the answer arrives (11 new paths at return, 32 by the next
command). Delete or `.gitignore` what you know to be tooling state — **prefer deleting**, since ignoring
permanently changes what later rounds can see — and **leave anything you cannot place** unstaged.

**3. Stage by name.** `git add <path> <path>`, never `-A`, never `.` — those two are how step 2 gets undone.

**4. Read what is staged, then commit.**

```bash
git status --porcelain -uall                  # 1: the whole state, files not directories
# 2: what appeared while Phase 2's dispatch ran. Guarded because round 1 has had no dispatch.
if [ -f /tmp/finish-REPLACE/post-dispatch.txt ]; then
  diff /tmp/finish-REPLACE/pre-dispatch.txt /tmp/finish-REPLACE/post-dispatch.txt
else echo "round 1 -- no dispatch yet, nothing to subtract"; fi
git add src/thing.py tests/test_thing.py      # 3: by name; never -A, never .
git diff --cached --name-only                 # 4: read every line; each is part of the work
git diff --cached | grep -n "$HOME" || echo "no machine-local absolute paths staged"
git commit -m "..."
```

Step 2 is the one that looks skippable: measured, one dispatch left 32 files, `git add -A` took all of them,
and the next packet was **98.7%** state nobody wrote (`references/what-a-dispatch-leaves-behind.md`). And **do
not stash the unit of work — not here, not anywhere in this skill**: `git stash` *removes the change from the
tree*, so everything downstream measures a tree the work is not in and reports health — walked end to end,
that gave a green suite and a written record for a change that shipped nowhere
(`references/proving-the-sweep-ran-your-code.md`).

**Then run Phase 0's base ladder again** and use the value it prints now; this re-run is where most projects
get their base. **Then prove the packet is not empty** — the one check that catches a stash, a base still
equal to HEAD, and a commit on the wrong branch:

```bash
git diff main...HEAD | wc -c; git diff HEAD | wc -c; git diff main...HEAD --name-only   # base retyped
```

If both counts are 0 and the ladder named a base, the work is not in this tree: find it (`git stash list`,
`git log --oneline -5`, `git branch --contains`) before going further. Read the file list too: files that
predate this work mean your base is the root-commit rung, not a fork point.

**Finally, know the suite's status before you spend a review round.** Not the sweep — just run the full suite
and read the exit status. **Never dispatch a cold reviewer onto a suite you know is red**, because a red suite
makes the round's findings a subset of what the runner would have printed for free. Fix it here and stay in
Phase 1; if the suite is genuinely too slow to run every round, run it before the *first* dispatch only.

## Phase 2: Adversarial review, by an agent that is not a fork of you

**Dispatch a fresh, cold reviewer.** Not yourself in a different frame of mind, not a subagent seeded with your
reasoning, not a fork or continuation of this session, and not a fork of whatever session dispatched *you*. A
reviewer carrying your context reads the code as confirmation of an intention it shares, so the one place a
defect can hide from the author is the one place it cannot look. Coldness is the mechanism. Give it:

- **A new agent with no conversation history** (the `Task`/subagent tool), a separate `claude -p`, or a human.
  `timeout` is not on the default macOS `PATH` and exits **127**, leaving an empty review file.
- **Artifacts, not narration.** The diff, the Phase 0 requirement sentence, the project's conventions. Not
  your reasoning, and not "I think this is fine but check X" — each transplants your blind spot and un-colds it.
- **A packet you have checked is not empty**, since a reviewer handed nothing reports nothing and that reads
  like approval:

  ```bash
  git diff main...HEAD; git diff HEAD; git status --porcelain -uall   # committed, uncommitted, untracked
  ```

  **Retype the base literally; never write `"$base"`** — the variable died with the shell that set it, and the
  mistake is silent: nothing printed, exit 0. Judge the packet by its bytes, never its status. **Then read its
  file list** (`--name-only` on both diffs): every path must be one you can name as part of the work, so
  un-track and ignore generated files, agent state, caches and vendored output, commit that, and rebuild it.
- **A request for findings with a failure scenario each**, and for a plain statement when it finds none. A
  reviewer that must produce findings invents them.
- **A new reviewer every round.** After round one the previous one has formed your expectations.

**Count the bytes of what came back before you read it as a verdict.** *An empty review file reads exactly like
a reviewer that found nothing*, and a real dispatch returned exit 0 with a 0-byte file; an inline answer with
no findings and no sentence saying it found none is the same empty. Re-dispatch, and if it is empty twice treat
it as "no cold reviewer was available".

**Bracket the dispatch with a path-set snapshot**, unconditionally, on every round:

```bash
git status --porcelain -uall --ignored | LC_ALL=C sort > /tmp/finish-REPLACE/pre-dispatch.txt
# ... dispatch the reviewer, and wait for it to return ...
git status --porcelain -uall --ignored | LC_ALL=C sort > /tmp/finish-REPLACE/post-dispatch.txt
diff /tmp/finish-REPLACE/pre-dispatch.txt /tmp/finish-REPLACE/post-dispatch.txt
# '>' lines appeared while the dispatch ran. '!!' marks an ignored path.
```

You edit nothing while the reviewer runs, so every path only in the second list appeared while the dispatch
ran; read it as candidates, and Phase 1 step 2 acts on it. **`--ignored` is on this command and on no other:**
Phase 1's remedy for tooling state is to ignore it and plain `git status` lists nothing git ignores, so from
round 2 the instrument would report silence about the very paths it taught you to ignore — 0 against 10.

**A good reviewer probes your suite in your tree, and that is it doing its job.** Break → red → revert restores
the source and not what the red run compiled, so do not forbid the probing and do not clean up after it here;
Phase 3 handles it by observation, and the canary certifies only the path it is on.

**If you cannot dispatch a cold reviewer**, this step did **not** happen: say so in the record and in your
reply, in those words, because a self-review recorded as an adversarial review is worse than a skipped one.
**Every finding you fix sends you back to Phase 1**, where the fix gets committed, and it voids any sweep.

## Phase 3: The whole verification sweep, proven to have run your code

**Run the project's full suite — every test file, every linter, every type check, every docs build — as the
project's own documentation defines them.** Read `CLAUDE.md`, `README.md`, `CONTRIBUTING.md`, the CI workflow
or the task runner, in that order, to find what "full" means *here*. Three rules, each there because of a
specific way the step fails:

1. **Whole, not the subset you were iterating on.** The subset is what you already know passes, chosen by what
   you were thinking about — the same filter that let the defect through. What it catches is the
   documentation-consistency test that goes red only *after* the code lands.
2. **Quote the output; never summarise it.** Paste the runner's own lines and capture the status with
   `echo "exit=$?"` on the very next line, because a banner and a non-zero exit read as green together.
   **Never through a pipe:** `./run_tests.sh | tail` gives you `tail`'s status. And a tail is not the suite's
   counts when the runner loops over files — those are the *last file's*. Quote the **aggregate** line if there
   is one; if not, quote **every** per-file summary line, count them, and say in the record that this runner
   prints no total.
3. **A single failure ends the phase.** Fix it and go back to Phase 1: the fix is unreviewed code, and
   Phase 1 is where it gets committed. Do not fix it and continue from here.

**Before the sweep: nothing of yours may be uncommitted** — the commit rule again: read
`git status --porcelain -uall`, stage by name, commit.

### Prove the run contained your change — invoke `stale-artifact-check`

**This is mandatory, and it is the step that makes the sweep evidence rather than a claim.** A green suite
proves something about *some* tree; only an observation inside the run proves it was yours.
`stale-artifact-check` owns that proof: invoke it, follow it, and **do not hand-roll a canary from memory** —
a `print()` on the changed line was swallowed whole by a passing `pytest -q`.

Three things about *this* use of it, which are the parts this skill owns:

- **Prefer the line your change actually altered**: one observation there proves both that the run loaded your
  source and that the suite exercises what you changed. That narrows the owned skill's own rule, and **where
  the two disagree the owned skill wins** — if the changed-line canary is absent, re-place it at module scope
  *before* routing into that skill's Phase 2 or 3.
- **The command it must prove is the project's full suite**, not a single test file or a faster proxy.
- **Read an absent canary the way that skill tells you to, then read what is left.** If it is still absent once
  that skill reports the artifact is current, the line never ran: nothing in the suite covers your change, and
  that is a finding for the record rather than something to wave through.

Then, as that skill's Phase 4 requires, **remove your canary and confirm it is gone**, and run the full suite
once more with nothing else changed. That clean run is the one you record: quote its command, the verbatim tail
of its output and its exit status, with the canary observation from the run before it. **Never fingerprint the
tree instead** — ten rounds of cold review killed that, because a fingerprint computed from outside the suite
cannot enumerate what the suite read (`references/proving-the-sweep-ran-your-code.md`).

Redirect the sweep into this finish's scratch directory and read it from there. Substitute what this
project's own docs call full, written out literally; `references/proving-the-sweep-ran-your-code.md`
has the command's shape, why several commands go into a script *file* rather than a shell variable,
and how to read a runner that prints no aggregate line.

**Any move-and-restore experiment belongs in a copy of the tree, never in the tree you are finishing**,
because restoring the source puts back neither what the red run wrote nor what it compiled. Make the
copy with the `mktemp -d` + `cp -a` pair in `references/what-a-dispatch-leaves-behind.md`, into a
destination that did not exist a moment ago — never a second `cp -a` into one that already holds a copy.

## Phase 4: Reconcile the prose with the code — invoke `claim-provenance`

**Invoke the `claim-provenance` skill. This is mandatory, not conditional on your sense that the docs are
probably fine** — that sense is what precedes the red documentation test. Run it over the durable prose your
change could have falsified: the README, the docs tree, any `CLAUDE.md` or architecture document, and any
paragraph your diff touched. Then **act on its result**; the corrections are edits like any other.

**Do not audit claims yourself, and do not lift one command out of it:** its greps are reading aids. And
**its presence-versus-truth test moves your tree**, so run that on a **fresh** scratch copy — the
`mktemp -d` + `cp -a` pair Phase 3 points at.

**Then commit what it changed, by name, before you go anywhere.** This is the phase the commit rule was written
for: a prose correction is small, it feels like part of the re-sweep, and no other phase picks it up —
uncommitted, the sequence completes and publishes the *uncorrected* sentence under a record that says
otherwise, measured on both integration routes. **Whatever it changed decides where you go next**, and the
middle row is the one that gets skipped:

| What Phase 4 changed | Where you go |
|-|-|
| Nothing | Phase 5 |
| Prose only | commit it here, then **Phase 3** — a docs build or a link check is part of the sweep, so editing a document invalidates the sweep exactly as editing code does |
| Any code, test, or assertion — including re-pointing an assertion at the system | **Phase 1**, which commits it and sends it to a cold reviewer |

## Phase 5: Write the record

Write, at the record path you declared in Phase 0:

- The Phase 0 sentence: what the unit of work was.
- Who reviewed it and how they were dispatched — or **that no cold reviewer was available**.
- Every finding and what you did about each — the ones you decided not to fix and why included — and how many independent reviewers raised each.
- The sweep: the command, the verbatim result, and the exit status.
- **The proof that the sweep ran your code**: Phase 3's canary observation, or the statement that nothing in the suite covers the change.
- What `claim-provenance` changed, what is still open, and anything you deliberately left undone.

**Then commit it, by name, in its own commit — writing it is not the deliverable, landing it on the branch is.**

```bash
git add notes/<yyyy-mm-dd>-what-this-was.md   # your declared path, by name; never -A
echo "add exit=$?"                          # 1 means an ignore rule covers it -- see below
git commit -m "record: <the Phase 0 sentence>"
git log --name-only --pretty=format: -1 | grep -F notes/<yyyy-mm-dd>-what-this-was.md
```

**Read `git add`'s exit status, and do not read the `git commit` after it.** If an ignore rule covers the record
path, `git add` exits 1 and the `git commit` then reports `nothing to commit, working tree clean`: a line about
the index, not about your record. The repair is `git add -f <record path>` **once, on the record path only**,
and the `git log … | grep` line is the confirmation Phase 6 repeats.

### The confirming sweep — on every route, not only on a swept path

**Writing the record is an edit made after the sweep, on every route there is**, so every finish owes one
confirming sweep, and no version of this skill has the recorded sweep as the last thing that ran. Do not reason
your way out by deciding the suite cannot read a file under `notes/`: **what a suite reads cannot be enumerated
from outside it**. Three steps, in order:

1. Commit the record as above, quoting the **Phase 3** sweep. Call that one the **recorded sweep**.
2. Run the full suite once more on the committed tree — the **confirming sweep** — and **read its exit status**.
   It needs no canary: the code has not moved since the recorded sweep proved the run contained it, and what
   this run proves is that the record did not break the suite. **Green → step 3. Red → the record broke the
   suite by existing:** fix what the failure names, commit that by name, and sweep again. If **two** repairs
   have not made it green, stop repairing — move the record to the commit body or to a path the suite does not
   read, commit that, and sweep once more.
3. **Do not put the confirming sweep into the record**, nor the repairs from step 2. Report them in your reply,
   and say in the record, before you commit it, that a confirming sweep follows. Then stop. Re-quoting edits a
   path the sweep may read, which demands another sweep: walked mechanically it mismatched eight times out of
   eight, and a suite's own output is not byte-stable anyway. The record lags by exactly one sweep, on purpose,
   and Phase 6's check 2 expects that (`references/where-the-record-lives.md`).

**On the commit-body route** the record is the body of a real commit, so no file in the tree moved — write it
with `git commit --allow-empty -m "record: ..."` (or amend Phase 1's message) and check `git log -1 --format=%B`
reads it back. Take the confirming sweep here too: the tree did not change but `HEAD` did. **There is no
PR-description route.** Phase 0 says why.

## Phase 6: Hand the integration decision to `superpowers:finishing-a-development-branch`

**Before you hand over, four things must be true.** Each is a re-read of something already written down, not a
new instrument:

1. **Nothing of yours is uncommitted.** `git status --porcelain -uall` — every remaining line is tooling state
   you can name, and no line is a deliverable — the commit rule's last check.
2. **Two runs describe the tree you are publishing, in this order.** The sweep you recorded carried an
   **observed canary**; Phase 5's **confirming sweep** ran *after* the record was committed and came back
   **green**; and **nothing at all has been edited since**. Every finish has both runs, on every route, so the
   recorded sweep being the last thing that ran is not the passing condition and never was. If anything moved
   after the confirming sweep, go back to Phase 3 — and do **not** repair a lagging record by re-quoting.
3. **Every review finding is dispositioned** — fixed, or recorded as deliberately not fixed with the reason —
   and the record says which. If any is neither, and the loop is what stopped you, you are in Phase 7, not here.
4. **What you are about to publish contains only files you can name, and the record is in it.**
   `git log --name-only --pretty=format: <base>..HEAD | sort -u`, retyping the base; on the commit-body route
   read `git log <base>..HEAD --format=%B` instead. If neither shows the record it is on your machine only — go
   back to Phase 5. Agent state, caches and build output arrive by `git add -A`; if one is there, go back to
   Phase 1, `git rm -r --cached <path>`, ignore it, commit that, re-sweep, and re-dispatch the review if that
   packet was dominated by it.

On the non-git path there is no branch: name the record's path and the changed files in your reply.

Then invoke `superpowers:finishing-a-development-branch` and follow it. Give it the base branch and the fact
that the suite is green on this exact tree, and then **do what it says** — do not decide merge-versus-PR
yourself, do not abbreviate its menu, do not pre-empt its confirmations. If the human picks an option that
opens a pull request, hand it the record's full text for the PR body. Expect it to run the full suite again as
its own first step; if that run disagrees with your Phase 3 run, the disagreement is a finding.

**Then remove this finish's scratch directory**, and only then — the only `rm -rf` in this skill:
`rm -rf /tmp/finish-REPLACE`, on exactly the path `mktemp -d` printed, never with a trailing `/*` and never
inside the repository. Everything in it is evidence until the four checks pass, so do this **after** the
handoff; if you abandon the run partway, leave it and say so.

## Phase 7: When the loop does not converge, the stop is a disposition

**Review rounds (review → fix → sweep) are capped at three.** Stop earlier, immediately, if a round's fix
**reopens** something an earlier round fixed, or if two consecutive rounds produce findings of the same
class in the same code **both times in code you changed in response to the round before** — that is the
design being the finding.

**The cap bounds dispatches and nothing else.** A round is one cold read you paid for; the cap says you may not
buy a fourth. It says nothing about repair, and it is not grounds for leaving a defect in place. "The loop has
stopped" is **never** the reason a finding with a reproduced failure scenario goes unfixed; a reader who cites
the cap to ship one has read it backwards. Fixing after the cap costs no round, because a fix is not a dispatch.

**A finding you decided not to fix will come back every round**, because each reviewer is new and cold by
requirement and cannot know the last one raised it; that is not non-convergence, and the answer is not to
explain the disposition to the next reviewer. **Count each round on what it produced that is new**, and treat a
repeat as evidence about the disposition rather than the loop: two cold reviewers with no contact between them
calling the same thing a defect is the strongest available signal that the disposition is wrong.

**A stop is an end state, not a pause and not a report.** "Partially reviewed, some findings open, nothing
decided" is the state this skill calls worse than a run never started, and it is exactly what a stop leaves
unless you finish it. Phase 6 is off the table — you have no converged review to hand it — so the run ends here
instead, and it ends *fully*: the same commit rule, the same sweep, the same record. Four steps.

**1. Fix everything already reproduced.** Every open finding that carries a failure scenario you can run gets
fixed now, and committed by name under Phase 1's rule. One exception, and it is the early-stop trigger itself:
a finding whose repair is what the loop kept reopening stays unfixed, and is named as such in the record. Do
not dispatch a reviewer for these fixes — the loop is over, by the cap or by the early-stop trigger — and their
being unreviewed is safe here precisely because none of the three end states below publishes anything.

**2. Bring the branch to a known state.** Run Phase 3's sweep on what you now have: whole suite, canary, exit
status quoted. **Phase 3's rule 3 does not apply here:** a red sweep is not a reason to keep editing or to loop
back. Record it red, with the failure it named, and go on to step 3.

**3. Choose the disposition from this closed list.** Exactly one of the three is true when you stop, and none
of them is "shipped". **None is an integration decision either** — each leaves the published branch untouched,
so `superpowers:finishing-a-development-branch` still gets the choice, from whoever picks the record up:

| Disposition | What it means | Choose it when |
|-|-|-|
| **Parked** | The work stays on its own branch, committed and unmerged, with the record on that branch naming every open finding | the default, and the answer whenever the work may still be worth landing |
| **Withdrawn** | The work commits are `git revert`ed on their own branch, so both the reversal and the history stay readable, because the findings say the design is wrong. The branch is kept; nothing is deleted | the early-stop trigger fired on the design, and nobody should build on this |
| **Re-scoped** | The unit is redrawn around the part no round disputed, and that is a **new** Phase 0 — new boundary sentence, new record, fresh round budget. The part you cut out is Parked or Withdrawn in its own right | a nameable subset is genuinely undisputed and you can write its boundary sentence without mentioning the disputed part |

Re-scoping is not a fourth round bought under another name. If the new boundary sentence is the old one
with a caveat, it is the old unit, and the honest disposition is Parked.

**4. Write and commit the record — Phase 5 in full, confirming sweep included** — with the disposition as its
**first sentence**, in this shape: *"Parked on `feature/x`, unmerged: two findings open (…), suite green at
`<sha>`."* Then, as well as Phase 5's list: which phase you stopped in and after how many rounds; every open
finding with its failure scenario; what each round changed; and your best account of *why* it did not converge.
**Say that same first sentence in your reply**, say that Phase 6 did not run, then remove the scratch directory
as Phase 6 does — the run ended in a named state and its evidence is in the record.

**Abandoning is not one of the three.** Out of context, out of budget, interrupted partway: say which phases
completed and which did not, in your reply and in the record, leave the scratch directory where it is, and
invoke `session-handoff`.

## Trigger precision

<!-- routing-pin
description-sha256: c9d56fb902e4b2ab4b97ee33ba2fb50ffec8466a05546bfd0cd44d18213c05ba
prompts-sha256: 5231c9570adecc209567bb4fe3c7c53eddb377c08caeb3d590b5051983096767
measured: 2026-08-31
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: partial 8/9 must-fire draws, 9/9 must-not-fire draws over 3 runs; not clean: 'Wrap up this branch: get it reviewed, run everything, make sure the docs still match, and then we'll decide what to do with it.' 2/3
-->

Prompts that MUST fire this skill:

1. "I think this feature is done — get it ready to push."
2. "The tests I've been running pass. What's left before I can merge this?"
3. "Wrap up this branch: get it reviewed, run everything, make sure the docs still match, and then we'll decide what to do with it."

Prompts that must NOT fire this skill:

1. "Check that every count and version in the README still matches the repo." (`claim-provenance` owns auditing what a document already claims; no unit of work is being finished.)
2. "I've already had this reviewed, run the whole suite, and updated the docs — now merge it to main." (`superpowers:finishing-a-development-branch` owns the integration decision, and the sequence this skill sequences has already run.)
3. "This test fails with a `KeyError` on line 42. Work out why." (`superpowers:systematic-debugging` owns a failure under diagnosis; nothing is finished.)

## Quick reference

| Phase | Do | Done when | Invalidated by |
|-|-|-|-|
| 0. Boundary | One sentence for the unit of work; derive the base with the ladder; pick a record path the sweep does not read and `git check-ignore -q` does not match; `mktemp -d /tmp/finish-XXXXXX` and retype what it prints wherever a block says `/tmp/finish-REPLACE` | The sentence is written, the base is named with `rung=named` (or the fallback is recorded knowingly), the record path is on the branch and one git will accept, the scratch dir came from `mktemp -d` | — |
| 1. Stop | Read `git status -uall`; **subtract what the dispatch wrote**; stage by name (never `-A`); read `git diff --cached --name-only`; **commit** — never stash the unit of work; re-run the base ladder; prove the packet is not 0 bytes | Only files you can name are committed, nothing of yours is left in the tree; the base is named; the work is demonstrably in the tree | any later fix |
| 2. Cold review | New agent, no history, artifacts not narration; new reviewer each round; never dispatch onto a suite you know is red; read the packet's `--name-only` list before sending; snapshot the path set (`--ignored`) before and after the dispatch; count the bytes of what came back | Findings dispositioned, or the gap recorded; the dispatch's files removed or ignored | any code change |
| 3. Whole sweep | Commit anything you arrived with; **invoke `stale-artifact-check`** and get an observed canary on the changed line from the project's full suite; remove the canary; run the full suite once more — that is the run you record; quote its output and exit status; do move-and-restore experiments in a fresh `mktemp -d` + `cp -a` copy | Canary observed, canary removed, runner's own lines quoted, exit 0 | any edit at all — the record included, which is what Phase 5's confirming sweep is for |
| 4. Prose | Invoke `claim-provenance`; run its test trap in a copy; **commit what it changed, here** | It reports nothing left to re-derive and its corrections are on the branch | — |
| 5. Record | Unit of work, reviewer, findings, sweep output, the canary observation, what changed, what is open — then **commit it by name**, or write it as a commit body; never a PR description alone; then **one confirming sweep, on every route**, and do not re-quote it | Written **on the branch**: `git log --name-only <base>..HEAD` shows the file, or `git log -1 --format=%B` reads the body back — and the confirming sweep is green on the committed tree | — |
| 6. Integrate | Four re-reads: nothing of yours uncommitted; the recorded sweep carried an observed canary **and** Phase 5's confirming sweep is the last run and green; findings dispositioned; the published file list holds only files you can name. Then invoke `superpowers:finishing-a-development-branch`, follow it, and only afterwards `rm -rf` this finish's scratch directory | It has been handed the decision | — |
| 7. Stop without converging | **Instead of** Phase 6, never as well as it. Fix every finding with a reproduced failure scenario — the cap bounds dispatches, not repairs; sweep; pick **Parked**, **Withdrawn** or **Re-scoped**; write it as the record's first sentence and say it in your reply | The disposition is one sentence someone else could act on, and nothing was published | — |
