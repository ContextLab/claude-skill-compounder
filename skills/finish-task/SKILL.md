---
name: finish-task
description: "Use when a unit of work is done and the pre-publish sequence still has to run: 'this feature is done, get it ready to push', 'what's left before I can merge?', 'wrap up this branch'. Do NOT use when review, sweep and docs are already done and only merging is left (`superpowers:finishing-a-development-branch`), for doc audits (`claim-provenance`), one completion claim (`superpowers:verification-before-completion`), or a bug under diagnosis (`superpowers:systematic-debugging`)."
---

# Finish task

Between "I think this is done" and the work being publishable there is a fixed sequence that does not vary with the task: an
adversarial review by someone who did not write it, the whole verification sweep rather than the subset you were iterating on,
the durable prose brought back into agreement with the code, a written record, then the integration decision. Every one is
skippable with no immediate consequence, exactly when you most want to be done.

**This is a procedure, not a checklist**, because of two properties a list of boxes cannot carry: **the steps are ordered by
what invalidates what**, so a run that *finds* anything goes **backwards** rather than shipping a sweep that predates the fix it
covers, and **the reviewer must not be the author** nor a *fork* of one (`references/red-flags.md` for what each prevents).

**This skill owns the sequence and nothing else.** Three of its steps are whole procedures with owners of their own; it
**invokes** all three and restates none. What is left is the ordering, the non-fork reviewer, the whole-sweep discipline, the
record, the loop back, two rules about the branch, and the named end state a run stops in when a loop will not converge (Phase
7). Seven files in `references/` sit beside it and none carries a step. **Any failure, in any phase, is a lookup before it is a
decision:** open `unhappy-path.md` the moment anything fails and find its row, which names what the failure voids and which phase
to run *forward* from, the failures that read like success included; `red-flags.md` is for a phase beginning to feel avoidable,
the other five hold measurements. **Every fenced block runs as written**; a `<…>` form appears only in prose. Inside a
block a literal is a value to **retype**, of two kinds. A **guarded** literal — `/tmp/finish-REPLACE`, a sample sha — cannot
survive being left alone: the next line names it and stops. A **free** literal — a commit message, a record path, a branch name —
is valid to every command that reads it, so nothing can reject the value and only a `case` on the literal itself can speak. Each
has one, and it either **refuses** (Phase 1's message, Phase 0's target branch) or **names it and lets the block finish the job it
exists for** (Phase 0 step 3's directory, Phase 5's `git add`). Either way, if a block says a literal survived, retype it.

## When this is the wrong skill

**The three it composes**, each mandatory where its phase names it, invoked and never duplicated here.
**`stale-artifact-check`**: the proof a run contained your change — canary placement, reading, the absent case, and every cause of
a removal that cannot be confirmed (Phase 3). **`claim-provenance`**: the prose-versus-code audit, the trap where an assertion
pins a document's *presence* rather than its *truth* included (Phase 4). **`superpowers:finishing-a-development-branch`**: the
integration decision — its menu, base-branch confirmation, worktree cleanup (Phase 6); never decide it yourself.

**Skills this is not.** `superpowers:requesting-code-review` owns *how* to review — use it **inside** Phase 2.
`superpowers:verification-before-completion` fires on one completion claim; this is the sequence around it, and
`superpowers:systematic-debugging` owns a failure under diagnosis. `session-handoff` owns a record written for lost context.
**`destructive-op-preflight`** owns deleting a scratch directory, and **this skill never deletes one**, so it never invokes it
(`the-scratch-directory.md`); the one file it removes anywhere is Phase 3's own canary marker, by exact name, and that phase says
why no preflight covers it. `oh-my-claudecode:verify` is narrower. **Not worth its own cost:** work nobody else runs or reads.

## The commit rule

Read this once; every phase is bound by it — one rule, not three notes, because the same defect arrived in three phases.

> **A phase's deliverable is not produced until it is committed, by name, on this branch. No phase hands over to the next one
> with an edit of its own still sitting in the working tree.**

| Phase | What it produces | Committed |
|-|-|-|
| 0 | a sentence, a base, a target branch, a path, a directory — no files in the tree | — |
| 1 | the unit of work | at the end of Phase 1, before the reviewer is dispatched |
| 2 | findings, which are prose in your reply. Any **fix** you make is Phase 1's deliverable again | back in Phase 1, before the next dispatch |
| 3 | nothing of its own: the canary is removed, never committed | — |
| 4 | the prose corrections `claim-provenance` produced | at the end of Phase 4, before the re-sweep |
| 5 | the record — a file, or a commit body; never a PR description alone | at the end of Phase 5, in its own commit, then one confirming sweep |
| 6 | nothing; it hands the branch to another skill | — |
| 7 | the fixes for what was already reproduced, and the record naming the disposition | as Phase 1 and Phase 5 say; nothing is published |

**Stage by name.** `git add <path> <path>` — **never `git add -A` and never `git add .`**: the tree contains things you did not
write and the reflex commits all of them. Read `git diff --cached --name-only` before committing. **Check the tree at the end of
every phase** with `git status --porcelain -uall` and say which of three things each line is, **by name** — this is the only
`??` rule here and every other mention defers to it. A ` M`, ` D` or `??` path is **your work** (stage it by name and commit it),
**tooling state you can place** (delete it, or `.gitignore` it — prefer deleting, since ignoring changes what later rounds can
see), or **a path you cannot place** (leave it: do not commit it, do not delete it, and name it in the record as in the tree and
not in the branch). **Not a git repository, or a detached `HEAD`? Phase 0 step 2 handles both**, and the integration branch
itself is answered in that same step.

## Phase 0: Fix the boundary, name the base and the target, declare the record, make a scratch directory

**1. Write down, in one sentence, what the unit of work is** and what would count as it being wrong. Everything later is judged
against this sentence. If you cannot write it, you are not finishing; you are stopping.

**2. Check this is a git repository, on a branch, and not on the branch this work would merge into; then name the base by hand
and prove it by its packet.** The base is the commit this work sits on top of; **no ref can be trusted to name it** — a list of
candidate refs broke on a new workflow in three consecutive review rounds (`naming-the-base.md`) — and **the file list is what
proves you named it right**:

```bash
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || echo "NOT A GIT REPOSITORY -- this skill declines here"
git rev-parse -q --verify HEAD >/dev/null 2>&1 && ! git symbolic-ref -q HEAD >/dev/null 2>&1 \
  && echo "DETACHED HEAD -- give the work a branch before anything else"
target=RETYPE-main; cur="$(git branch --show-current)"   # the branch this MERGES INTO. Name it; never derive it.
case "$target" in RETYPE-*) echo "MISSED THE RETYPE: name the branch this work merges into" ;;
  "$cur") echo "ON THE INTEGRATION TARGET ($cur) -- read the paragraph below before anything else" ;; esac
git log --oneline -20                  # find the NEWEST commit that is not part of this unit of work
base=3066977e5cdb                      # RETYPE that sha. Left as-is: 'NOT A COMMIT' below.
git rev-parse --verify --quiet "$base^{commit}" >/dev/null || echo "NOT A COMMIT -- retype the base sha"
h="$(git rev-parse HEAD 2>/dev/null)"   # empty outside a repo, which is why the next line tests it
[ -n "$h" ] && [ "$(git rev-parse "$base" 2>/dev/null)" = "$h" ] \
  && echo "BASE IS HEAD -- correct while this work is uncommitted; wrong if the log above already shows it"
git diff "$base" HEAD --name-only      # the packet's file list. Judge it against step 1's sentence.
```

Run it once to read the log, retype `target` and `base`, run it again. **The last line is the whole check**, and step 1's
sentence makes it decidable: a path that is **not** part of this unit of work means the base is too far back — pick a **newer**
sha; a file of your work **missing** means the base is inside your work — pick an **older** one. **Write the base down as a sha,
never a branch name** (tips move, every Bash call is a fresh shell); `target` is the one branch *name* this skill keeps, never a
diff base, and Phase 6 hands it on.

**An accepted review finding grows the unit of work, so step 1's sentence is amended — out loud, in the record — and the list is
judged against the amended one.** Without that, a fix outside the sentence leaves **no** satisfying sha in either direction
(measured, `naming-the-base.md`). A path you would **not** amend it to cover is no base problem: pick a newer sha, or if it is
inside a commit of your own, leave it and record it as in the branch and not part of the work.

**`BASE IS HEAD` is the expected reading here, not an error**, and an error only in Phase 1, after the commit; treating it as one
here deadlocks (`unhappy-path.md`). If the log does not already show your work, keep that sha and go on with an empty packet.

**`NOT A GIT REPOSITORY` ends the run here, the whole non-git route.** Without `.git` six of the eight phases are impossible —
the base, the packet, both homes of the record, Phase 6's handover, all three Phase 7 dispositions. Say so and stop: `git init`
and commit, or invoke the three owned skills directly; `does not have any commits yet` is the same answer, shorter repair.
**`DETACHED HEAD` is repaired here too, and this is the only place this skill catches it**: all four of Phase 6's checks pass on
one, and checking out away orphans every commit to the reflog. **`git switch -c <a branch name you choose>`, right now**, or this
skill declines, as non-git does.

**`ON THE INTEGRATION TARGET` is repaired here, or the run says plainly that it was not.** Phase 6 hands a branch over and all
three of Phase 7's dispositions park, revert or re-scope one — "Parked on `main`, unmerged" is meaningless. **Uncommitted work:
`git switch -c <a branch name you choose>`** carries it across and is the whole repair. **Already committed there, this skill
cannot move it back** — it issues no `reset` and no history rewrite — so say so, write "the work is already on `<target>`" into
the record, and read Phases 6 and 7 against that fact rather than against a branch that can be parked.

**3. Declare where the record will go** — now, so it is not invented at the end: one real path in your project's convention
(`notes/<yyyy-mm-dd>-what-this-was.md` is the shape, not the answer). **Check that git will accept it, now**, because the
directories a "durable note" convention names are exactly the ones projects ignore:

```bash
record=notes/2026-08-31-what-this-was.md    # RETYPE the path you just declared. A FREE literal: see below.
case "$record" in *what-this-was*)                   # the WORD, not the shipped date: Phase 5 refuses
  echo "STILL THE EXAMPLE PATH -- this is the literal this skill ships, not the one you declared" ;; esac
mkdir -p "$(dirname "$record")"             # or Phase 5's redirect fails: 'No such file or directory'
git check-ignore -q "$record"; case $? in
  0) echo "IGNORED: plain 'git add' REFUSES it -- move it, or 'git add -f' in Phase 5" ;;
  1) echo "ok: git will accept this path" ;;
  *) echo "NOTHING WAS EXAMINED (exit $?) -- you are not in a git repository; see step 2" ;;
esac
```

An ignored path makes `git add` exit **1** while the `git commit` after it reports on the index (Phase 5 says how that reads).
Prefer moving the record over `git add -f`, and prefer a path **outside the trees the suite walks** — a guess that lowers the odds
of a sweep going red *because of the record*, never a reason to skip Phase 5's confirming sweep. **Two homes, and a PR description
is not one** (`where-the-record-lives.md`).

**4. Make this finish's scratch directory.** Phases 1, 2 and 3 redirect logs, snapshots and tree copies there, and **none of
those may be written inside the repository**. **Phase 3's canary is not one of those and needs no exception managed by you**: it
goes inside the repository on purpose — in the source line your change altered, or in its file form as a `?? CANARY-…` path — and
Phase 3 removes both and confirms them gone before the recorded sweep runs, so it is evidence with an owner rather than `??`
residue. **Not `mktemp -d /tmp/finish-XXXXXX`**: `/tmp` is world-writable and a cleanup on that prefix once deleted a live one
out from under a running session (`the-scratch-directory.md`). Per-user, per-run:

```bash
t="${TMPDIR:-/tmp}"; t="${t%/}"                   # macOS TMPDIR ends in '/', which doubles the slash
d="$(mktemp -d "$t/finish-$(date +%Y%m%d-%H%M%S)-$$-XXXXXX")"
echo "$d"   # THIS finish's dir. Retype it wherever a later block says /tmp/finish-REPLACE.
```

**`/tmp/finish-REPLACE` in every later block and every reference recipe is a placeholder that does not exist**: a missed retype
must fail loudly rather than contaminate another finish, so do not `mkdir` it — the error *is* the check. **And nothing here ever
deletes this directory**: Phase 6 and Phase 7 name where it is and leave it.

## Phase 1: Bring your own house to a stop

**Commit — and know what you are committing.** Not the sweep; this is so the Phase 2 reviewer reads a coherent thing rather than
a half-applied edit. Four steps, in order.

**1. Read the whole tree state.** `git status --porcelain -uall`. Without `-uall` git collapses an untracked directory into one
line, and one collapsed line is how thirty files enter a commit.

**2. Subtract what you did not write.** Every round after the first arrives straight out of Phase 2, and **a dispatched reviewer
writes into your repository** — agent state, caches, logs, some carrying absolute paths from your machine. Re-read the tree now
rather than trusting Phase 2's list; the writing does not stop when the answer arrives. Then apply the commit rule's three-way
`??` reading, unchanged.

**3. Stage by name.** `git add <path> <path>`, never `-A`, never `.` — those two are how step 2 gets undone.

**4. Read what is staged, then commit.**

```bash
git status --porcelain -uall                  # 1: the whole state, files not directories
d=/tmp/finish-REPLACE                         # 2: RETYPE what Phase 0 step 4 printed
if [ ! -d "$d" ]; then echo "MISSED THE RETYPE: '$d' is not a directory -- use Phase 0 step 4's path"
elif [ -e "$d/post-dispatch.txt" ]; then diff "$d/pre-dispatch.txt" "$d/post-dispatch.txt"; echo "diff exit=$?"
else echo "round 1: no snapshot pair in '$d' yet -- nothing to subtract"; fi
git add src/thing.py tests/test_thing.py      # 3: RETYPE both with your own paths; never -A, never .
git diff --cached --name-only                 # 4: read every line; each is part of the work
n="$(git diff --cached --name-only | wc -l | tr -d ' ')"
[ "$n" = 0 ] && echo "NOTHING IS STAGED -- step 3 staged nothing, so the grep below proves nothing"
git diff --cached | grep -n "$HOME" || echo "no machine-local absolute paths in the $n staged file(s)"
msg="RETYPE-one line saying what this unit of work is"    # 5: a FREE literal; the case is its only guard
case "$msg" in RETYPE-*) echo "PLACEHOLDER MESSAGE -- retype it. Nothing has been committed." ;;
  *) git commit -m "$msg" ;; esac
```

Step 2 is the one that looks skippable: measured, one dispatch left 32 files, `git add -A` took all of them, and the next packet
was **98.7%** state nobody wrote. **Both guards there fail loudly rather than into a reassuring branch, because both once did the
opposite** — a file test an unretyped placeholder can never satisfy, and a `grep … || echo` that reassures over an empty index,
which is why `n` is counted and named in the line (`what-a-dispatch-leaves-behind.md`); a third guard of this shape anywhere here
is a defect. **Step 5's guard is a different shape**, because a message is a *free* literal — every command accepts one, so no
check can reject the value: `git commit -m "..."` run unretyped *committed itself* at exit 0, `%s` reading back `...`. Step 3's
two paths are free too, which is why step 4 reads the staged list back before step 5 is reached. And **never stash the unit of
work**: it *removes the change from the tree*, so everything downstream measures its absence and reports health.

**Then read Phase 0's file list again** — same base sha, same command. The commit is what puts your work into that list, so this
is where the base is finally provable, and it catches a stash, a base retyped as HEAD, and a commit on the wrong branch:

```bash
base=3066977e5cdb   # RETYPE the sha you named in Phase 0. Left as-is: 'fatal: bad object'.
git rev-parse --verify --quiet "$base^{commit}" >/dev/null || echo "NOT A COMMIT -- retype the base sha"
h="$(git rev-parse HEAD 2>/dev/null)"   # empty outside a repo; the next line must not compare empty to empty
[ -n "$h" ] && [ "$(git rev-parse "$base" 2>/dev/null)" = "$h" ] \
  && echo "BASE IS HEAD -- an error HERE: the commit above moved HEAD, so pick the commit below your work"
git diff "$base" HEAD --name-only; git diff "$base" HEAD | wc -c; git diff HEAD | wc -c
```

**Now the list must hold every file of the unit of work as step 1's sentence now stands, and nothing else** — both of Phase 0's
readings, the "missing" half decidable at last. **`BASE IS HEAD` reads the opposite way here to the way it read in Phase 0**,
which is why it is printed twice: after the commit moved `HEAD` past your base it can only mean you named `HEAD`'s own sha. If
both counts are 0 read that first — not lost work; otherwise find it (`git stash list`, `git branch --contains`).

**Finally, know the suite's status before you spend a review round.** Not the sweep — run the full suite and read the exit status.
**Never dispatch a cold reviewer onto a suite you know is red**: the round's findings become a subset of what the runner prints
for free. **Fix it here — a red test is Phase 1's, whatever its subject**, and repairing the claim it named is not Phase 4's.

## Phase 2: Adversarial review, by an agent that is not a fork of you

**First, take the pre-dispatch snapshot**, before the reviewer runs — a path-set bracket, unconditionally, on every round:

```bash
d=/tmp/finish-REPLACE   # RETYPE what Phase 0 step 4 printed.
if [ ! -d "$d" ]; then echo "MISSED THE RETYPE: '$d' is not a directory -- use Phase 0 step 4's path"; else
if [ -e "$d/post-dispatch.txt" ]; then         # a finished pair from the round before: archive it
  mv "$d/pre-dispatch.txt" "$d/pre-$(date +%s).txt"; mv "$d/post-dispatch.txt" "$d/post-$(date +%s).txt"
fi
if [ ! -e "$d/pre-dispatch.txt" ]; then
  git status --porcelain -uall --ignored | LC_ALL=C sort > "$d/pre-dispatch.txt"
  echo "PRE-DISPATCH SNAPSHOT TAKEN -- now dispatch the reviewer, as the rest of this phase says, then"
  echo "run this same block AGAIN once it has returned, before you edit anything."
else
  git status --porcelain -uall --ignored | LC_ALL=C sort > "$d/post-dispatch.txt"
  diff "$d/pre-dispatch.txt" "$d/post-dispatch.txt"  # '>' appeared while it ran; '!!' is an ignored path
fi; fi
```

**One block, run twice, and it cannot take both snapshots in one pass** — that is the whole reason for the `if`. A backgrounded
`Agent` returns inline and the harness invites you to keep working, so a version that took the pair in one run bracketed nothing:
measured mid-dispatch, it printed `diff exit=0` while the reviewer was still writing. Every path only in the second list appeared
while the dispatch ran, and is a candidate Phase 1 step 2 acts on. **`--ignored` is on this command and on no other**
(`what-a-dispatch-leaves-behind.md`: without it, round 2 reported 0 paths against 10).

**Then dispatch a fresh, cold reviewer.** Not yourself in another frame of mind, not a subagent seeded with your reasoning, not a
fork or continuation of this session, and not a fork of whatever session dispatched *you*: a reviewer carrying your context reads
the code as confirmation of an intention it shares. Give it:

- **A new agent with no conversation history** (the `Task`/subagent tool), a separate `claude -p`, or a human — never wrapped in
  `timeout`, which is not on the default macOS `PATH` and exits **127** into an empty review file.
- **Artifacts, not narration**: the diff, the Phase 0 sentence, the project's conventions — never your reasoning, and never "I
  think this is fine but check X", which transplants your blind spot.
- **A packet you have checked is not empty** — a reviewer handed nothing reports nothing, and that reads like approval:

  ```bash
  base=3066977e5cdb   # RETYPE the sha you named in Phase 0
  git rev-parse --verify --quiet "$base^{commit}" >/dev/null || echo "NOT A COMMIT -- retype the base sha"
  git diff "$base" HEAD; git diff HEAD; git status --porcelain -uall   # committed, uncommitted, untracked
  ```

  **Re-assign `base` at the top of every block and check that it resolves**; unset, it is silent (`naming-the-base.md`).
  Judge the packet by its bytes, never its status, and read its file list: un-track and ignore generated files and caches.
- **Findings with a failure scenario each**, a plain statement when it finds none, and **a new reviewer every round**.

**Measure what came back before you read it as a verdict** — bytes for a review file, the finding count for an inline answer.
*An empty review reads exactly like a reviewer that found nothing*: a real dispatch returned exit 0 with a 0-byte file, and an
answer with no findings and no sentence saying so is the same. Re-dispatch; empty twice is "no cold reviewer was available".

**A good reviewer probes your suite in your tree, and that is it doing its job** — and **a path set cannot see a rewrite of a
path already in it**, the bracket's second blind spot: break → red → revert restores the source, not what the red run compiled
(measured, the `diff` printed nothing while the `.pyc` beside it changed sha and mtime). So do not forbid the probing and add no
instrument for it — Phase 3 handles it by observation, and its canary certifies only the path it is on.

**If you cannot dispatch a cold reviewer**, this step did **not** happen: say so in the record and in your reply, in those words
— a self-review recorded as an adversarial review is worse than a skipped one. **Every finding you fix sends you back to Phase
1**, where the fix gets committed, and it voids any sweep; if the fix reaches a path Phase 0's sentence does not name, amend that
sentence before you judge any file list against it.

## Phase 3: The whole verification sweep, proven to have run your code

**Run the project's full suite — every test file, every linter, every type check, every docs build — as the project's own
documentation defines them.** Read `CLAUDE.md`, `README.md`, `CONTRIBUTING.md`, the CI workflow or the task runner, in that
order, to find what "full" means *here*. **Before it runs, nothing of yours may be uncommitted** — the commit rule again: `git
status --porcelain -uall`, stage by name, commit. Three rules, each there because of a way the step fails:

1. **Whole, not the subset you were iterating on**, which is what you already know passes, chosen by the filter that let the
   defect through. The whole run catches the docs-consistency test that goes red *after* the code lands.
2. **Quote the output; never summarise it.** Paste the runner's own lines and capture the status with `echo "exit=$?"` on the
   very next line — a banner and a non-zero exit read as green together. **Never through a pipe:** `./run_tests.sh | tail` gives
   `tail`'s status, and a tail is the *last file's* counts when the runner loops. Quote the **aggregate** line, or every
   per-file line, counted.
3. **A single failure ends the phase.** Fix it and go back to Phase 1, where the fix — unreviewed code — gets committed.

### Prove the run contained your change — invoke `stale-artifact-check`

**This is mandatory, and it is the step that makes the sweep evidence rather than a claim.** A green suite proves something about
*some* tree; only an observation inside the run proves it was yours. `stale-artifact-check` owns that proof: invoke it, follow it,
and **do not hand-roll a canary from memory** (a `print()` on the changed line was swallowed by a passing `pytest -q`).

**Prefer the line your change actually altered** — one observation there proves both that the run loaded your source and that the
suite exercises what you changed; where that narrowing and the owned skill's rule disagree, **the owned skill wins**, and an
absent changed-line canary is re-placed at module scope **of a file this change touched**. Where the change touched no source at
all, Phase 4's prose row says what the re-sweep proves and forbids that fallback. **What it must prove is the project's full
suite**; **still absent once that skill reports the artifact current means nothing covers your change** — record that, plainly.

**Then remove your canary and confirm it is gone — and removing it means removing everything the canary CREATED.** That last
part is **finish-task's own step, because the delegation cannot answer it**: the default form `open("CANARY-…","a").write("x")`
leaves a marker **file**, and that skill's Phase 4 check looks for the file as well as the text while nothing in it deletes one.
Measured, with the source line already gone and the tree otherwise clean, its check printed `YOUR CANARY IS STILL HERE:
./CANARY-1788251186-7b0c0e67`, exit 1 — no exit anywhere on its default path. So delete the artifact yourself, by its **exact**
name — `rm -f ./CANARY-1788251186-7b0c0e67`, with your own token retyped — and **never through a `CANARY-*` glob**, which also
matches another session's live canary. That command is deliberately *not* a fenced block: no fenced block in this skill deletes
anything, and this one is meant to be retyped by hand rather than pasted. It is the only file this skill removes, and it needs no
`destructive-op-preflight` for the reason that skill would give — this run made the file minutes ago, it holds one byte, it is
named exactly, and nothing else can be lost. **Every other cause
that check names is still that skill's** (a token in bytecode, in build output, in an installed copy) and this one enumerates
none. Follow it until its check prints `CLEAN`, then run the full suite once more with nothing else changed. **A run whose
removal was never confirmed does not reach Phase 6**, and **that last, canary-free run is the recorded sweep** — quote its
command, the verbatim tail of its output and its exit status, and beside them the canary observation from the run *before* it.
Redirect it into this finish's scratch directory, substituting what the project's docs call full
(`references/proving-the-sweep-ran-your-code.md`).

**Any move-and-restore experiment belongs in a copy of the tree, never in the tree you are finishing**: restoring the source puts
back neither what the red run wrote nor what it compiled. Use the guarded `cp -a` pair in `what-a-dispatch-leaves-behind.md`.

## Phase 4: Reconcile the prose with the code — invoke `claim-provenance`

**Invoke the `claim-provenance` skill. This is mandatory, not conditional on your sense that the docs are probably fine** — that
sense is what precedes the red documentation test. Run it over the durable prose your change could have falsified: the README, the
docs tree, any `CLAUDE.md`, any paragraph your diff touched, then **act on its result**. **Do not audit claims yourself, and do
not lift one command out of it:** its greps are reading aids. A claim a **red test** already named is not this phase's — Phase 1
fixed it. **Its presence-versus-truth test moves your tree**: run it on a **fresh** scratch copy, the pair Phase 3 points at.

**Then commit what it changed, by name, before you go anywhere.** This is the phase the commit rule was written for: a prose
correction is small, feels like part of the re-sweep, and no other phase picks it up — uncommitted, the sequence publishes the
*uncorrected* sentence under a record that says otherwise. **What it changed decides where you go next:**

| What Phase 4 changed | Where you go |
|-|-|
| Nothing | Phase 5 |
| Prose only | commit it here, then **Phase 3** — a docs build or a link check is part of the sweep, so editing a document invalidates the sweep exactly as editing code does. **What that re-sweep proves is narrower, and Phase 3's canary has no object here:** put the canary in the changed prose file only if the suite reads that file, and if it stays `ABSENT` record, in those words, that nothing in the suite covers the prose change. **Never fall back to module scope in a source file** — measured, a README-only correction with the canary moved into `src/shapes.py` came back `OBSERVED`, certifying a file the change never touched, which is proof of the wrong thing and worse than none |
| Any code, test, or assertion — including re-pointing an assertion at the system | **Phase 1**, which commits it and sends it to a cold reviewer |

## Phase 5: Write the record

Write, at the record path you declared in Phase 0:

- The Phase 0 sentence: what the unit of work was, and every amendment a review finding made to it.
- Who reviewed it and how they were dispatched — or **that no cold reviewer was available**.
- Every finding and what you did about each, the ones you decided not to fix and why included, and how many independent
  reviewers raised each.
- The recorded sweep: its command, its verbatim result, its exit status, and **the proof it ran your code** — Phase 3's canary
  observation, or the statement that nothing in the suite covers the change. Then what `claim-provenance` changed, what is open,
  and anything you deliberately left undone.
- **The absolute path of this finish's scratch directory**, what Phase 0 step 4 printed; nothing deletes it.

**Then commit it, by name, in its own commit — writing it is not the deliverable, landing it on the branch is.**

```bash
record=notes/2026-08-31-what-this-was.md   # RETYPE your declared path, by name; never -A
msg="record: RETYPE-THE-PHASE-0-SENTENCE"  # FREE literals, both: nothing rejects either, so both are MARKED
git add "$record"; a=$?; echo "add exit=$a"  # 1 = an ignore rule covers it (below); 128 = no such file
case "$record$msg" in *what-this-was*|*RETYPE-*) echo "A SHIPPED LITERAL SURVIVED -- retype path and message" ;; esac
[ "$a" = 0 ] && git commit -m "$msg"       # never commit when the add failed: something else is staged
git log --name-only --pretty=format: -1 | grep -F "$record"; echo "grep exit=$?   # 0 = it is on the branch"
```

**Read `git add`'s exit status, and do not read the `git commit` after it** — `[ "$a" = 0 ]` is what saves you from having to.
Unguarded, an ignore rule over the record path makes `git add` exit 1 and the `git commit` report on the index instead — measured,
`nothing to commit, working tree clean`, or `nothing added to commit but untracked files present`. Both read as reassurance,
neither is about the record, and one of them commits whatever else was staged under the record's message. Repair with `git add -f
<record path>` **once, on the record only**. **`add exit=128` is different**: the record is unwritten, or its directory is gone.

### The confirming sweep — on every route, not only on a swept path

**Writing the record is an edit made after the sweep, on every route there is**, so every finish owes one confirming sweep. **What
a suite reads cannot be enumerated from outside it**, so a path under `notes/` is no exemption. Three steps, in order:

1. Commit the record as above, quoting the **Phase 3** sweep. Call that one the **recorded sweep**.
2. Run the full suite once more on the committed tree — the **confirming sweep** — and **read its exit status**. It needs no
   canary: the code has not moved since the recorded sweep proved the run contained it, and this proves the record did not break
   the suite. **Green → step 3. Red → the record broke the suite by existing:** fix what the failure names, commit it by name,
   sweep again. After **two** repairs without a green, move the record to the commit body, commit, sweep once more; **red again
   ends the run in Phase 7**, by its second entrance. Never a third pass through here.
3. **Do not put the confirming sweep into the record**, nor step 2's repairs — report them in your reply, and say in the record,
   before committing it, that one follows. Re-quoting has no fixed point, so the record lags a sweep, as Phase 6's check 2 expects.

**On the commit-body route** the record is the body of a real commit, so no file in the tree moved — write it with `git commit
--allow-empty -m "record: RETYPE-THE-PHASE-0-SENTENCE"`, retyped, or amend Phase 1's message, then check `git log -1 --format=%B`
reads it back. The `"..."` that stood here was a free literal: run unretyped it committed itself at exit 0 with `%s` reading back
`...`, which is why the marker replaces it. Take the confirming sweep here too — `HEAD` moved. **No PR route exists.**

## Phase 6: Hand the integration decision to `superpowers:finishing-a-development-branch`

**Before you hand over, four things must be true.** Each is a re-read of something already written down, not a new instrument:

1. **Nothing of yours is uncommitted.** `git status --porcelain -uall` — every remaining line is tooling state you can name and
   no line is a deliverable, the commit rule's last check.
2. **Two runs describe the tree you are publishing, in this order.** The **recorded sweep** — Phase 3 names which run that is,
   and this check does not restate it — came back green and is quoted in the record beside Phase 3's canary observation; Phase
   5's **confirming sweep** ran *after* the record was committed and came back **green**; and **nothing has been edited since**.
   If anything moved after the confirming sweep, go back to Phase 3 — never re-quote a lagging record.
3. **Every review finding is dispositioned** — fixed, or recorded as deliberately not fixed with the reason — and the
   record says which. If any is neither, you are in Phase 7, not here.
4. **What you are about to publish holds only files you can name, and the record is in it.** Assign the base sha and **check it
   resolves first**, as every fenced block does — `base=<the sha from Phase 0>`, then `git rev-parse --verify --quiet
   "$base^{commit}" >/dev/null || echo "NOT A COMMIT -- retype the base sha"` — because what follows is a pipe, and a pipe hides
   the failure: measured, a mistyped sha makes `git log --name-only --pretty=format: "$base"..HEAD | sort -u` print nothing at
   **exit 0**, which reads as "the record is not published". Then run that `git log`, **two dots and never three** (`A...HEAD` is
   the symmetric difference), and judge the list by Phase 0's rule against step 1's sentence as amended. The commit-body route
   reads `git log "$base"..HEAD --format=%B`. Neither showing the record → Phase 5; agent state in it → Phase 1.

Then invoke `superpowers:finishing-a-development-branch` and follow it. Give it the target branch you named in Phase 0 step 2 — a
branch *name* is what that skill needs, and Phase 0's "never a branch name" rule is about the diff base only — and the fact the
suite is green on this exact tree, then **do what it says**: do not decide merge-versus-PR yourself, abbreviate its menu, or
pre-empt its confirmations. Expect it to run the full suite again; if that run disagrees with Phase 3's, that is a finding.

**Then say where this finish's scratch directory is** — the absolute path Phase 0 step 4 printed, in your reply, the same one
Phase 5 put in the record. **Do not delete it, and do not delete any other.** The whole cost is that they accumulate under
`$TMPDIR` until the OS reclaims them; wanting the space back is your own command, outside this skill.

## Phase 7: When the loop does not converge, the stop is a disposition

**Review rounds (review → fix → sweep) are capped at three.** Stop earlier, immediately, if a round's fix **reopens** something
an earlier round fixed, or if two consecutive rounds produce findings of the same class in the same code **both times in code you
changed in response to the round before** — the design being the finding. **The cap bounds dispatches and nothing else**: no
fourth cold read, and "the loop has stopped" is never why a reproduced finding ships unfixed — a fix costs no round.

**A finding you decided not to fix comes back every round**: each reviewer is new, cannot know the last one raised it, and must
not be told. That is not non-convergence, and **each round counts only what is new** — but two independent reviewers calling one
thing a defect is the strongest signal the disposition is wrong.

**A stop is an end state, not a pause and not a report.** "Partially reviewed, some findings open, nothing decided" is worse than
a run never started. Phase 6 is off the table, so the run ends here and ends *fully*: same commit rule, sweep and record.

**1. Fix everything already reproduced.** Every open finding carrying a failure scenario you can run gets fixed now, committed by
name under Phase 1's rule. One exception, the early-stop trigger itself: a finding whose repair is what the loop kept reopening
stays unfixed and is named as such. Do not dispatch a reviewer for them — none of the three end states publishes anything.

**2. Bring the branch to a known state.** Run Phase 3's sweep on what you now have: whole suite, canary, exit status quoted.
**Phase 3's rule 3 does not apply here** — a red sweep is no reason to keep editing. Record it red, with the failure it named.

**3. Choose the disposition from this closed list.** Exactly one is true when you stop and none is "shipped"; **none is an
integration decision either**, since each leaves the published branch untouched. All three assume Phase 0 step 2's check passed
and the work is on a branch that is not the target; where it is not — the already-committed case Phase 0 cannot repair — say so
in the same sentence, because "Parked, unmerged" would be false:

| Disposition | What it means | Choose it when |
|-|-|-|
| **Parked** | The work stays on its own branch, committed and unmerged, with the record on that branch naming every open finding | the default, and the answer whenever the work may still be worth landing |
| **Withdrawn** | The work commits are `git revert`ed on their own branch, so both the reversal and the history stay readable, because the findings say the design is wrong. The branch is kept; nothing is deleted | the early-stop trigger fired on the design, and nobody should build on this |
| **Re-scoped** | The unit is redrawn around the part no round disputed, and that is a **new** Phase 0 — new boundary sentence, new record, fresh round budget. The part you cut out is Parked or Withdrawn in its own right. Not a fourth round under another name: if the new boundary sentence is the old one with a caveat, it is the old unit and the honest disposition is Parked | a nameable subset is genuinely undisputed and you can write its boundary sentence without mentioning the disputed part |

**4. Write and commit the record — Phase 5 in full, confirming sweep included** — with the disposition as its **first sentence**:
*"Parked on `feature/x`, unmerged: two findings open (…), suite green at `<sha>`."* Then, as well as Phase 5's list: which phase
you stopped in and after how many rounds; every open finding with its failure scenario; what each round changed; why it did not
converge. **Say that first sentence in your reply**, say Phase 6 did not run, then name where the scratch directory is, as Phase
6 does, and leave it.

**Abandoning is not one of the three.** Out of context, out of budget, interrupted partway: say which phases completed and which
did not, in your reply and in the record, leave the scratch directory where it is, invoke `session-handoff`.

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
| 0. Boundary | One sentence for the unit of work; check for a repo, a branch, **and that the branch is not the integration target you name**; name the base sha by hand from `git log --oneline -20`; declare a record path `git check-ignore` does not match and `mkdir -p` its directory; make the scratch dir | The base sha is written down and `git diff <base> HEAD --name-only` holds no path that is not this unit of work. `NOT A GIT REPOSITORY` ends the run here; `DETACHED HEAD` gets a branch here or the run declines; `ON THE INTEGRATION TARGET` is repaired here or recorded as unrepaired | — |
| 1. Stop | `git status -uall`; **subtract what the dispatch wrote**, and a missed retype says `MISSED THE RETYPE`, never `nothing to subtract`; stage by name (never `-A`); read `--cached --name-only` and count it; **commit behind the message guard**; never stash the work; read the base's file list again; fix a red suite here, whatever the test is about | Only files you can name are committed, and the list holds every file of the work and nothing else | any later fix |
| 2. Cold review | **Pre-dispatch snapshot first** (`--ignored`), then a new agent, no history, artifacts not narration, a new reviewer each round; never dispatch onto a suite you know is red; read the packet's file list; post-dispatch snapshot **in its own block, after the reviewer returns**; count the bytes that come back | Findings dispositioned, or the gap recorded; the dispatch's files removed or ignored; a fix outside Phase 0's sentence amended it | any code change |
| 3. Whole sweep | Commit anything you arrived with; **invoke `stale-artifact-check`** for an observed canary on the changed line, from the full suite; **remove the line AND `rm -f` the marker file it created**; sweep again — **Phase 3 names which run the record quotes**; experiments go in a fresh `cp -a` copy | Canary observed, everything it created removed and its check printing `CLEAN`, then the recorded run's own lines quoted, exit 0 | any edit at all, the record included |
| 4. Prose | Invoke `claim-provenance`; run its test trap in a copy; **commit what it changed, here**; a prose-only change re-sweeps with **no source-file canary** | Nothing left to re-derive and its corrections are on the branch | — |
| 5. Record | Unit of work, reviewer, findings, sweep output, canary, what is open — **commit it by name** or write it as a commit body, never a PR description; then **one confirming sweep**, never re-quoted. Red after two repairs *and* the move → **Phase 7** | `git log --name-only <base sha>..HEAD` shows the file, or `git log -1 --format=%B` reads the body back, and the confirming sweep is green | — |
| 6. Integrate | Four re-reads: nothing of yours uncommitted; the record quotes the recorded sweep and its canary observation **and** the confirming sweep is the last run and green; findings dispositioned; the published list — behind a checked base sha — holds only files you can name. Then `superpowers:finishing-a-development-branch`, given Phase 0's target branch; afterwards **name** the scratch dir and leave it | It has been handed the decision | — |
| 7. Stop without converging | **Instead of** Phase 6. Fix every finding with a reproduced failure scenario — the cap bounds dispatches, not repairs; sweep; pick **Parked**, **Withdrawn** or **Re-scoped**, and say so plainly if the work is already on the target branch | The disposition is one sentence someone else could act on, and nothing was published | — |
