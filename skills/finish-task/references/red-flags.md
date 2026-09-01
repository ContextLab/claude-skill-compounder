# Red flags and rationalizations

Two tables of thoughts that arrive right before a step gets skipped, each paired with what is
actually true. Nothing here is new procedure: every row points back at a phase in the body. Read
this when a phase feels avoidable, and read the phase it names.

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
| "`git add` said nothing to commit, so the record must already be in." | Read the `git add` status, not the `git commit` line. An ignored record path makes `git add` exit 1 and the commit then report a clean tree — measured. `git add -f`, on the record only. |
| "It was broken to probe a test and put back, so the tree is exactly as it was." — whether the reviewer did it or you did | The source is. What the red run compiled is not: measured, a restored byte-identical tree ran `exit=1` with `AssertionError: 'abl' != 'ABL'` about source that says `.upper()`. Phase 3 handles the reviewer's case without your having to remember it happened; do your own move-and-restore experiments in a `cp -a` copy outside the tree. |
| "I'll stash this while I get the tree tidy." | Then the work is not in the tree, and every phase after it measures its absence. Measured: 0-byte packet, green suite, no change shipped. Commit instead. |
| "The packet is empty but it exited 0, so there is nothing to review." | `git diff "$base"...HEAD` with the variable dead prints nothing and exits 0. Retype the base and count the bytes. |
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
