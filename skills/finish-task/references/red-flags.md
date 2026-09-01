# Red flags and rationalizations

Two tables of thoughts that arrive right before a step gets skipped, each paired with what is
actually true. Nothing here is new procedure: every row points back at a phase in the body. Read
this when a phase feels avoidable, and read the phase it names.

## Why it is a procedure and not a checklist

The body states the two properties in one sentence; this is what each one prevents.

**The steps are ordered by what invalidates what.** Fixing a review finding invalidates the sweep,
because the fix is code no sweep has seen; changing code invalidates the prose audit, because the
audit read the old code. So a run that *finds* anything goes **backwards** to the phase that owns
committing the fix, and forward again from there. A checklist ticked top to bottom cannot express
that: it ships a green sweep that predates the fix it is quoted as covering, and every box is
ticked truthfully.

**The reviewer must not be the author, nor a fork of one.** A reviewer carrying your context reads
the code as confirmation of an intention it already shares, so the adversarial step returns "looks
fine" every time and costs a round to learn nothing. Cold means no conversation history and no
narration from you — artifacts only. This is the property a checklist cannot carry either, because
"get it reviewed" is satisfiable by asking yourself.

## Red flags

Each of these means you are about to skip a step. Stop and re-read the phase.

| The thought | The reality |
|-|-|
| "I know this code better than any reviewer would." | That is the argument for a cold one. A reviewer who shares your model of the code cannot see the gap between it and the code. |
| "I'll just have a subagent look at it, and tell it what I was going for." | Telling it what you were going for is the fork. Send the diff and the requirement; send nothing else. |
| "The reviewer said it looks fine." | Did it get artifacts, or your narration? A reviewer handed your reasoning returns your reasoning. |
| "I only need to run the tests for the files I touched." | The test that catches you is in a file you did not touch. That is what "whole" is for. |
| "The suite passed, I'll just fix this one small thing first." | Then the suite that passed is not the tree you are shipping. Re-run it. |
| "The suite is green, so the sweep covered my change." | Green describes some tree. `stale-artifact-check`'s canary is what says it was yours, and it is one command. |
| "I'll skip the canary — I can see my edit in the file." | Saving proves the file changed. It proves nothing about what the run loaded, and the reviewer in Phase 2 just ran and probed your suite in this tree. |
| "I'll hash the tree before and after instead; it's cheaper than a canary." | Ten rounds of review killed exactly that. A hash taken outside the suite cannot enumerate what the suite read, and its list of exceptions never closes. Observe the run instead. |
| "The docs are almost certainly fine." | Invoke `claim-provenance`. That sentence is the one that precedes the red documentation test. |
| "Correcting the README would turn a test red, so the README is probably right." | `claim-provenance` names this exactly. The assertion is the defect. |
| "CI is green on this branch." | CI ran a commit. Which one, and did anything prove it contained your edit? |
| "`git add -A` after the review, then commit." / "Those state files are junk, they're harmless in a commit." | Phase 1 steps 1–3: read `git status -uall`, subtract the dispatch's files, stage by name. Measured, one dispatch left 32 state files and `-A` committed all of them, one carrying an absolute home path — into the branch you publish, where Phase 6's published list is the last thing that looks. |
| "The record is written, so Phase 5 is done." / "It's just my notes, it does not belong in the commit." | Written where nobody will look. Until it is on the branch it is an untracked file on one machine — measured, it reached neither the pushed branch nor the merged history. The next person reads the branch, and Phase 6 expects the record in the published list. |
| "`git add` said nothing to commit, so the record must already be in." | Read the `git add` status, not the `git commit` line. An ignored record path makes `git add` exit 1 and the commit then reports on the index — measured, `nothing to commit, working tree clean` with nothing else untracked, `nothing added to commit but untracked files present` with something. `git add -f`, on the record only. |
| "It was broken to probe a test and put back, so the tree is exactly as it was." — whether the reviewer did it or you did | The source is. What the red run compiled is not: measured, a restored byte-identical tree ran `exit=1` with `AssertionError: 'abl' != 'ABL'` about source that says `.upper()`. Phase 3 handles the reviewer's case without your having to remember it happened; do your own move-and-restore experiments in a `cp -a` copy outside the tree. |
| "I'll stash this while I get the tree tidy." | Then the work is not in the tree, and every phase after it measures its absence. Measured: 0-byte packet, green suite, no change shipped. Commit instead. |
| "The packet is 0 bytes, so the work must be lost." | Check the base sha against `HEAD` before you go hunting. A base that **is** HEAD gives a guaranteed-empty packet and no error — measured, on work that was committed, pushed, and sitting in the tree the whole time. Phase 1's block prints `BASE IS HEAD`: pick the commit below your work and retype. |
| "The canary removal check still refuses, so I'll delete the line again / edit the source once more." | The source is already clean, so a second edit changes nothing and the check refuses again. **Read the path it lists first.** If it is a `CANARY-…` *file*, that is the artifact your canary created and removing it is finish-task's own step — `rm -f ./CANARY-<your token>`, exact name, never a glob; measured, the default canary form leaves it and nothing in `stale-artifact-check` deletes it, so that path has no exit until you do. Every *other* cause belongs to that skill, and this one lists none of them on purpose — two rounds of review each found one the previous list did not cover. Follow it until its check prints `CLEAN`. |
| "The canary is `OBSERVED`, so this prose correction is proven." | Read which file it is on. A README-only change with the canary re-placed at module scope in `src/shapes.py` comes back `OBSERVED` and certifies a file the change never touched — a true statement offered as proof of something else, which is worse than no proof. Phase 4's prose row: canary in the changed prose file if the suite reads it, otherwise record that nothing covers the change. |
| "I'm on `main` but the branch does not matter, everything else checks out." | Then Phase 6 has no branch to hand over that is not the target, and Phase 7's three dispositions all say "on its own branch" — "Parked on `main`, unmerged" is meaningless. Phase 0 step 2 names the target and refuses the match. Uncommitted, `git switch -c` is the whole repair; already committed there, this skill cannot move it back and the record has to say so. |
| "The block ran and exited 0, so the placeholder must have been fine." | Not for a **free** literal. A commit message, a record path and a branch name are valid values to every command that reads them, so exit 0 says nothing: measured, `git commit -m "..."` gave `[feature/perimeter 95855b4] ...` at exit 0 and `git log -1 --format=%s` read back `...`. Each now stands behind a `case` on its own literal — read what the block *printed*, not what it exited. |
| "The record block printed a warning but it committed anyway, so the warning was noise." | It committed because landing the record is what that block is for, and `git log` now carries `RETYPE-THE-PHASE-0-SENTENCE` where a reader will see it. A refusal there would leave Phase 5 with no deliverable; a marker leaves it with an obviously unfinished one. Amend the message. |
| "I'll delete the `RETYPE-` prefix, that is what it is there for." | That restores a literal this document ships, which is the round-4 defect in `the-scratch-directory.md` arriving at a new site. Type the value you actually mean. |
| "I'll run the pre- and post-dispatch snapshot in one go while the reviewer works." | A backgrounded `Agent` returns inline, so both halves would run before the review exists. Measured, a two-command version printed `diff exit=0` while the reviewer was still writing — a bracket around nothing, reported as "the dispatch wrote nothing". The block is one `if` for that reason: run it, dispatch, run it again. |
| "The packet is empty but it exited 0, so there is nothing to review." | `git diff "$base" HEAD` with the variable dead is a plain working-tree diff, and the `<base>..HEAD` a placeholder tempts you to write is a shell redirect that prints nothing and exits 0. Re-assign the base sha, check it resolves, and count the bytes. |
| "There are several `finish-*` directories lying around; I'll clean them up." | Not as part of a finish. You cannot tell from a name which run owns one or whether its session is still running, and four rounds of cold review could not write an ownership check this document does not itself satisfy — so the check was cut rather than patched a fifth time (`the-scratch-directory.md`). This skill deletes none of them, and the one that is yours is named in the record.|
| "It's only a scratch dir under /tmp; `rm -rf` is fine, I don't need a whole preflight for that." | The last thing to think that deleted a full-suite log, three routing-probe results and three script backups. Nothing under `/tmp` is tracked, stashed, or in any reflog. This skill therefore issues no such command at all; if *you* decide to, that is your own command and `destructive-op-preflight` fires on its own trigger.|
| "Phase 0 says `BASE IS HEAD`, so I have the wrong sha and must go one commit further back." | Not before Phase 1's commit. There the newest commit that is not your work usually *is* `HEAD`, and going back one gives you a packet holding somebody else's file — measured, a colleague's `.ci/config.yml` — after which "pick a newer sha" walks you straight back. Keep the sha, go on with an empty packet, and let Phase 1's commit make it provable. In Phase 1 the same line **is** an error. |
| "`HEAD` is detached but everything checks out, so I can hand this over." | All four of Phase 6's checks pass on a detached `HEAD`, which is exactly why they are not the test. There is no branch to hand over, Phase 7's dispositions all say "on its own branch", and checking out away orphans the commits to the reflog. `git switch -c <name>` at Phase 0, before anything else. |
| "It printed `nothing to subtract`, so there was nothing the dispatch wrote." | Only if the directory in that block is the one `mktemp -d` printed. Until 2026-09-01 an unretyped placeholder produced that exact reassurance and exit 0, on round 2 of a real loop, skipping the step measured at 98.7% contamination. The repaired block says `MISSED THE RETYPE` first; if you did not see that line, the reading is real. |
| "The `grep` for `$HOME` found nothing, so nothing machine-local is staged." | Check the count on the line above it. An empty index makes that grep find nothing and print the same reassurance — the second guard of the shape the first one was repaired for. |
| "This is not a git repo, but I can still do the review and the sweep." | Then you are not running this skill. Six of its eight phases are impossible without `.git`, including both homes of the record and every end state. Phase 0 step 2 declines; take the owned skills directly instead. |
| "`/tmp/finish-REPLACE` does not exist; I'll create it." | Then every finish on this machine shares it. Measured: a stale snapshot from a different repo made this skill report paths that did not exist in the tree being finished. Run `mktemp -d` and retype what it printed. |
| "The new reviewer raised the same thing I already decided not to fix, so the loop is not converging." | It cannot know you decided that, and it must not be told. A re-report is not a new finding. If two cold reviewers independently call it a defect, re-examine the decision, not the loop. |
| "The confirming sweep is greener than the one in the record; I'll update the record to quote it." | Then you have edited a path the sweep may read and owe another sweep, and another record edit. Measured: eight iterations, MISMATCH every time, no fixed point — and eight runs of one unchanged suite printed two different elapsed times, so there is nothing byte-stable to converge on. The record lags by one sweep on purpose. |
| "The record is just a note file under `notes/`; the suite obviously cannot read it — no confirming sweep needed." | You cannot know that from outside the suite, and that assumption is precisely the one ten rounds of review killed in this skill's fingerprint. One run settles it. Measured elsewhere: a record file *did* turn a suite red by existing. |
| "I'll `cp -a` into the scratch tree again for the second experiment." | It exits 1 on git's read-only objects and leaves the **first** copy sitting there looking correct. Fresh `mktemp -d` destination every time. |
| "The record can live in the PR description." | Two of the three integration options never open a PR, and the human picks. Measured: `grep -ci record` over the whole published history printed `0`. |
| "It's obvious this should just be merged to main." | That decision is not yours. Phase 6. |
| "Three rounds is the cap and I have done three, so these two findings ship as they are." | The cap bounds *dispatches*, not repairs. A fix after the cap costs no round, because a fix is not a dispatch. Phase 7 step 1 fixes everything with a reproduced failure scenario before any disposition is chosen. |
| "The loop stopped converging, so I'll report where things stand and leave it there." | That report *is* the state this skill calls worse than a run never started. A stop ends in **Parked**, **Withdrawn** or **Re-scoped**, named in one sentence at the top of the record. Phase 7 step 3. |

## Common rationalizations

| Excuse | Reality |
|-|-|
| "This change is too small for the whole sequence." | Size predicts nothing here. What bites is a test or a document *elsewhere* in the repository that your change falsified, and its distance from your diff is unrelated to your diff's size. Use the body's "not worth its own cost" test — nobody runs it, nobody reads it — not a line count. |
| "I already reviewed it as I wrote it." | Review while writing is the author's review. The property this phase requires is not thoroughness, it is a reader who does not already know the intent. |
| "A subagent is a fresh context, so it is cold by construction." | Only if the prompt is cold. A subagent seeded with your framing is your session with a new id. |
| "The reviewer found nothing, so I can skip the sweep." | Different failures. Review catches what you meant wrongly; the sweep catches what the rest of the repository disagrees with. |
| "The full suite takes too long." | It takes exactly as long as it will take the next person, plus a review round nobody needed. If it is genuinely too long to run once at the end, that is a finding about the suite, and it goes in the record. |
| "All tests pass." / "I'll summarise the output; it's just a wall of dots." | The runner's aggregate line and the exit status are not a wall — that is the whole quotation, and a summary you typed is a claim, not evidence. If the runner loops over files it prints no aggregate line; say so and quote the exit status and the per-file lines. |
| "The canary is overkill; that is a lot of suite runs." | Two of them buy you which tree the green describes, and one more — the confirming sweep — buys the fact that the record is itself an edit made after the sweep. The alternative is a mechanism that has to enumerate everything the suite reads, which is the thing that failed. |
| "The prose step is `claim-provenance`'s job, so I can note it as a follow-up." | Phase 4 is invoking it, now. A follow-up is a skipped step wearing a due date. |
| "Only the docs changed after the sweep, so the green still stands." | Not if a docs test or docs build is in the sweep — and you cannot know it is not without checking. Re-run. |
| "It was a one-sentence prose fix; committing it is a formality." | The sweep reads the working tree. The branch does not. Measured: the sequence completed and both integration routes published the uncorrected sentence, under a record that said it had been corrected. |
| "I'll do the notes and the integration in one step." | The record is what survives if the integration is refused, deferred, or goes wrong. Write it first — and commit it, or it survives nothing. |
| "The loop keeps finding things, so I'll fix the last one and ship." | The last one you fixed is unreviewed and unswept. Either go round again or stop and report — those are the two moves. |
