# Where the record lives

The record has two homes — a file on the branch, or a commit body on the branch — and Phase 0
step 3 makes you pick before anything is written. This file is the evidence for each part of that
decision, and for why the record's quotation of the sweep deliberately lags by one run.

## An ignored record path, and what git says while the record goes missing

Measured, with `notes/` in `.gitignore`: `git add notes/2026-08-26-thing.md` printed
`The following paths are ignored by one of your .gitignore files` and exited **1**, and the
`git commit` on the next line then reported on the index and exited 1 — a reassurance line at the
exact moment the deliverable is missing. **Which** reassurance depends on the rest of the tree, and
both were measured on the same fixture: with nothing else untracked, `nothing to commit, working
tree clean`; with one unrelated untracked file present, `nothing added to commit but untracked files
present (use "git add" to track)`. Neither mentions the record. That is why the body tells you to
read `git add`'s status and not the `git commit` line after it.

`git add -f` does land it, exits 0, and leaves the exclusion intact for every other file in that
directory: measured, a second file written there afterwards did not appear in
`git status --porcelain -uall` at all. So the force-add is a one-path repair, not a loosening of
the ignore rule — and the directories a "durable note" convention names (`notes/`, `scratch/`,
`drafts/`) are exactly the ones projects ignore, which is why the check runs in Phase 0 rather
than being discovered in Phase 5.

## A record on a path the sweep reads

Measured, on a repo whose suite asserts that `<docs>/index.md` lists every file under `<docs>/`,
committing the record at `<docs>/notes/rec.md` turned the confirming sweep red:

```
AssertionError: 'notes/rec.md' not found in '# index\n- guide.md\n'
exit=1
```

Adding the index entry made it `exit=0`. So a swept path is repairable, and Phase 5 step 2 says
how — what the Phase 0 preference buys is that the confirming sweep cannot come back red *because
of the record* in the first place. The commit-body route avoids the question outright, being on
the branch by construction and not a file in the tree at all.

## Both routes, walked

Swept path: recorded sweep `exit=0`, record committed at `<docs>/notes/rec.md`, confirming sweep
`exit=1` with the assertion above, one repair committed by name, confirming sweep `exit=0`,
nothing edited after it, a further run `exit=0`.

Unswept path: recorded sweep `exit=0`, record committed at `notes/<yyyy-mm-dd>-08-26-perim.md`, confirming
sweep `exit=0` first time.

Both ended with `git status --porcelain -uall` clean and the record never re-quoted.

## The PR description is not a home

Walked against a real bare remote, with the record held as session prose and the integration route
being merge-to-main-locally and delete the branch: `git log --all -p | grep -ci record` printed
`0`. Two of the three integration options `superpowers:finishing-a-development-branch` offers never
open a pull request at all, and the human picks which one. A record that exists only in a PR
description therefore exists nowhere on the routes where no PR is opened.

## The commit-body route survives the same walk

Verified against a real bare remote: after merging to `main` locally, pushing and deleting the
branch, `git log --all --format=%B` on the remote still contained the record text; on the
keep-the-branch route it is on the retained branch. Write it with
`git commit --allow-empty -m "record: ..."` (or amend Phase 1's commit message) and read it back
with `git log -1 --format=%B`.

## Why the record lags the last sweep by one run, on purpose

Updating the record to quote the confirming sweep edits a path the sweep may read, which
invalidates that sweep, which demands another, which must be quoted. Walked mechanically on a repo
whose docs build hashes `<docs>/**.md` with the record at `<docs>/notes/rec.md`: eight iterations, and
on every one the value the record quoted differed from the value the next run printed — MISMATCH
eight times out of eight, no fixed point in sight.

There is a second reason, and it holds even where nothing in the sweep reads the record: **a
suite's own output is not byte-stable across runs.** Measured, eight consecutive runs of one
unchanged suite on an unchanged tree printed `Ran 2 tests in 0.002s` seven times and
`Ran 2 tests in 0.003s` once. A record chasing the newest run is chasing a moving target, not
converging on one.
