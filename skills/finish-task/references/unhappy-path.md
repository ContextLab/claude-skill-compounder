# Unhappy path

The failure-to-route table. When any phase fails, comes back empty, or prints something the body
did not lead you to expect, find its row here before you act: each one names what the failure
voids and which phase to run forward from. Each row names what the failure voids, where to
resume, and — where there is one — the measurement behind that route.

## Where to re-run from

Go back to the phase in the "Re-run" column and run *forward from there*, not from where you
stopped:

| What happened | Void | Re-run from |
|-|-|-|
| Cold reviewer found something and you fixed it | the sweep, the prose audit, the record | Phase 1 |
| The review packet is 0 bytes, or the suite passes with your change absent | everything | Phase 1 — the work is not in this tree. `git stash list`, `git log --oneline -5`. Never stash the unit of work |
| The dispatch itself left files in the tree | the sweep | Phase 1 step 2 — remove or ignore them, then stage by name. Its writes continue after it returns, so read the state again just before staging |
| You committed what the dispatch left behind (`git add -A`) | the sweep, and the review packet if it was dominated by them | Phase 1 — `git rm -r --cached <path>`, ignore it, commit that; re-dispatch the review if that packet was mostly state |
| Cold reviewer could not be dispatched | nothing | Phase 3, with the gap written into the record and stated in your reply |
| The sweep failed | the sweep, everything after it | Phase 1 — the fix is unreviewed code, and Phase 1 is where it gets committed |
| The sweep failed on a tree `git diff` says is byte-identical to a state you watched go green | nothing yet — **do not go looking for a defect in the code** | Somebody's break-and-revert left a build artifact compiled from source that is no longer on disk — a cold reviewer probing your suite, `claim-provenance`'s test trap. Measured 9 trials in 12: `git diff --stat` empty, suite still red. `stale-artifact-check` owns this; its canary is what tells you, and its Phase 3 is what fixes it |
| Phase 3's canary was absent | the sweep — it is not evidence | `stale-artifact-check` Phase 2 and 3. Come back when it is observed |
| Phase 3's canary was **observed** and the sweep is red anyway, on a tree `git diff` says is unchanged | the sweep | The stale artifact is in a file you did not canary, and the canary cannot see it. Measured: `canary OBSERVED`, `exit=1`, `AssertionError: 11 != 10`, `git diff --stat` empty. `stale-artifact-check` Phase 3 clears the pipeline; re-run the sweep before you go looking for a defect |
| The canary is still absent once `stale-artifact-check` reports the artifact is current | nothing | Nothing in the suite covers your change. Say so in the record, in those words; do not record a green as coverage |
| `claim-provenance` changed prose | the sweep | Commit it in Phase 4, then Phase 3. No other phase will commit it |
| `claim-provenance` changed code, a test, or an assertion | the sweep, the prose audit | Phase 1 |
| The sweep passed and you then edited anything at all | the sweep | Phase 3. The **one** expected post-sweep edit is the record, and Phase 5's confirming sweep is what covers it — that is the only edit this skill answers with a confirming sweep rather than a re-run from Phase 3 |
| The confirming sweep came back red | nothing yet — the record broke the suite by existing, and no code moved | Phase 5 step 2 — fix what the failure names, commit it **by name**, run the confirming sweep again. Measured: a record at `<docs>/notes/rec.md`, under a suite asserting `<docs>/index.md` lists every file under `<docs>/`, gave `AssertionError: 'notes/rec.md' not found`, `exit=1`; the index entry made it `exit=0`. Two repairs without a green means the path is fighting the sweep — move the record to the commit body |
| `cp -a` into the scratch tree printed `Permission denied` on `.git/objects/…` and exited 1 | nothing | Phase 3 — you copied into a destination that already holds a copy, and git's objects are read-only. **The stale copy is still there and `ls` on it looks correct**, which is the danger. `mktemp -d /tmp/finish-REPLACE/scratch-XXXXXX` and copy into that; never `cp -a` twice into one destination |
| `git status --porcelain -uall` lists a tracked file as ` M` or ` D` at a phase boundary | nothing — the sweep still covers it | Commit it by name. Do **not** re-sweep; the tree did not move, only the index and `HEAD`. Measured: a Phase 4 prose correction left uncommitted reached neither the pushed branch nor the merged main, while the record claimed it had been made |
| `git status --porcelain -uall` lists a `??` path you cannot place | nothing | Do not commit it and do not delete it — it is Phase 1 step 2's residue. Say in the record that it is in the tree and not in the branch |
| Phase 6's published list holds a file you cannot name as part of the work | the sweep | Phase 1 — un-track and ignore it, commit that, then forward from Phase 3 |
| You reached Phase 6, or pushed, with the record uncommitted | nothing — but the record reaches no branch | Phase 5 — `git add <record path>` and commit it. Measured: uncommitted, it survived neither the push route nor the merge-and-delete route |
| `git add <record path>` printed `The following paths are ignored` and exited 1 | nothing | Phase 5 — `git add -f <record path>`, once, on the record only. Do **not** re-run the plain `git add`; it will refuse again, and the `git commit` after it says `nothing to commit, working tree clean` while the record is still missing. Phase 0 step 3's check is what catches this before anything is written |
| A block failed with `No such file or directory` on `/tmp/finish-REPLACE/…` | nothing | You missed a retype. Substitute what `mktemp -d` printed in Phase 0 step 4. Do **not** `mkdir` the placeholder: the failure is the guard, and the directory it would create is the one every run shares |
| A cold reviewer re-reported a finding you had dispositioned as deliberately not fixed | nothing | Nothing — this is expected, since each reviewer is new. It does not count as a round's new finding. Two independent reviewers raising it is evidence the disposition is wrong; re-examine it, and record the count either way |
| The base ladder printed `UNDETERMINED` or `rung=ROOT-FALLBACK` before Phase 1 | nothing | Phase 1 — commit, then re-run the ladder. Both are the same expected reading, not a fault. Do **not** build a packet from the root-commit value: measured, it named four files that were not the work and omitted the file that was |
| The base ladder still printed `rung=ROOT-FALLBACK` after the Phase 1 commit | nothing | Nothing — the branch has no named base above it, so the whole-history packet is the honest one. Use it and say so in the record |
| The cold reviewer returned nothing: a 0-byte file, or an answer with no findings and no sentence saying it found none | the round | Phase 2 — re-dispatch. Measured: a real dispatch exited **0** with a **0-byte** review file. An empty answer is not "found nothing"; a second empty answer means no cold reviewer was available, and that goes in the record in those words |
| The project's record convention points at a path the sweep reads | nothing | Phase 0 — prefer a path it does not read, or the commit body. The confirming sweep runs either way; what a swept path adds is that it can come back **red because of the record**, which Phase 5 step 2 repairs. Re-quoting the record into the newest sweep is the move that never terminates and has no fixed point |
| The record exists only as session prose, or only in a PR description you have not opened yet | nothing — but the record reaches no branch | Phase 5 — a file on the branch, or a commit body. Measured against a real bare remote: on the merge-locally route `git log --all -p \| grep -ci record` printed `0`, and two of the three integration options never open a PR at all |
| `finishing-a-development-branch` reported failing tests | the sweep | Phase 1 — your Phase 3 sweep and its Step 1 disagree, and that disagreement is itself a finding |
