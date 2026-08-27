# What a dispatch leaves behind

Phase 2 brackets every reviewer dispatch with a path-set snapshot, and Phase 1 step 2 subtracts
what that snapshot names before anything is staged. Both look like bookkeeping until you see what
a dispatch actually writes into your repository. This file is that evidence, plus the reasoning
behind the scratch directory those snapshots live in.

## What one dispatch wrote

Measured, in a repository one cold `claude -p` review was dispatched into: the dispatch left 32
files under a single untracked directory, the reflexive `git add -A && git commit` tracked all 32,
and the next review packet was 41,489 bytes across 33 files — **98.7%** of its bytes state nobody
wrote. Dispatched, that packet bought one finding, and the finding was the state itself, not the
code.

The writing does not stop when the answer arrives. Measured on the same dispatch: **11** new paths
existed at the moment it returned its review and **32** by the next command, from jobs that outlive
it. That is why Phase 1 step 2 says to re-read the tree state rather than trusting the list Phase 2
handed you.

## Why the check has no condition on it

An earlier version conditioned the same check on *"if something moved and you did not edit
anything"*. That is false by construction after round 1, since looping back means you edited
something, so the condition silenced the check exactly when the residue was accumulating fastest.
A path-set diff taken *around* the dispatch needs no condition at all: during the dispatch, you
edit nothing, so every path only in the second list appeared while it ran.

## Why the bracket carries `--ignored`

Plain `git status` lists nothing git ignores, and Phase 1 step 2's remedy for tooling state is to
ignore it — so round 1 names the residue, you ignore it, and from round 2 the instrument reports
silence about the very paths it taught you to ignore.

Measured: round 1's bracket found 5 new `.omc/` paths, `.omc/` went into `.gitignore`, and round
2's plain bracket reported **0** while 10 more files were written. The same bracket with
`--ignored` reported all **10**, as `!!`. Pre-existing ignored trees cancel in the diff, so the
extra output stays bounded.

The remaining blind spot: a reviewer that *edits a tracked file* shows as a modification you must
recognise, not as a new path.

## Why the scratch directory comes from `mktemp -d`

A fixed path under `/tmp` is shared with every finish this machine has ever run, and last week's
leftovers are readable and indistinguishable from your own. Measured: a stale snapshot from a
*different repository* made Phase 1 step 2 report `.omc/` paths as things "the dispatch wrote" in a
tree where `ls -d .omc` answers `No such file or directory`.

An earlier version defended a fixed `/tmp/finish-1` with a bare `mkdir` that refused when it
existed. On any machine that has run this skill before, **refusal is the normal branch**, and
`mkdir` guards only the creation: every later block writes with `>`, which succeeds silently into
the other run's directory the moment one retype is missed. `mktemp -d` never returns a directory
that already exists, so there is no refusal branch to take.

The placeholder is the other half of the guard. Measured, `>` into the literal
`/tmp/finish-REPLACE` exits **1** and `diff` on it exits **2** — a missed retype fails loudly
instead of contaminating someone else's finish.

## Why you never `cp -a` twice into one destination

Measured on macOS BSD `cp`: a repeat `cp -a . "$st"` into a destination that already holds a copy
printed `Permission denied` for every `.git/objects/…` path and exited **1**, because git's objects
are read-only — *and left the first, now stale, copy in place*, where `ls` on it looks exactly
right.

A second experiment is the normal case, not an exotic one: Phase 4 sends prose changes back to
Phase 3 and code changes back to Phase 1, so any run that loops reaches a second Phase 4, and its
test trap then runs against a tree that predates the change it is meant to test.

## Never dispatch onto a suite you already know is red

A red suite makes a round's findings a subset of what the runner would have printed for free.
Measured in this skill's own walk: a round-1 reviewer's single finding was a stale count in
`README.md:5`, and running `./run_tests.sh` on the exact tree it reviewed took under a second and
printed `exit=1`, `AssertionError: 2 != 3` — the same finding, paid for at the price of a review
round. Phase 1's cheap status check is what makes that unnecessary.

## When a dispatch returns nothing

An empty review file reads exactly like a reviewer that found nothing, and two different causes
produce it.

A wall-clock wrapper that is not installed: `timeout` is not on the default macOS `PATH`, and
`timeout 300 claude -p …` exits **127** leaving an empty file behind.

A wrapper that returns before the reviewer does: measured, a real dispatch returned **exit 0** with a
**0-byte** review file. Nothing about the status says the round did not happen, which is why Phase 2
counts the bytes rather than reading the status, and why a second empty answer is recorded as "no
cold reviewer was available" rather than as a clean review.
