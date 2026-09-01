# Proving the sweep ran your code

Phase 3 delegates the proof to `stale-artifact-check` and records an observed canary. This file is
why the proof is an observation made inside the run rather than anything computed from outside it,
what the canary does and does not cover, and how to read a runner that prints no aggregate line.

## The mechanism that failed: fingerprinting the tree

An earlier draft answered the same question by hashing every file before and after the sweep and
refusing to publish if the digest moved. Ten rounds of cold review killed it, and the reason
generalises past the implementation: **a fingerprint computed from outside the suite cannot
enumerate what the suite actually read.**

Every round produced a new counterexample to the previous round's stated limits — a git-ignored
file the suite reads, a fixture reached through a symlinked directory, a `.gitattributes` clean
filter, EOL normalisation, a permission bit, a submodule — and that list can never be closed, so a
refusal built on it can never be trusted. An observation made *inside the run* needs no such list:
the canary either executed or it did not. If you find yourself hashing anything in this skill, you
are rebuilding the thing that failed.

The same finding is why Phase 5 refuses to let you reason your way out of the confirming sweep by
deciding the suite cannot possibly read a file under `notes/`.

## Why you use that skill's canary form and not one you remember

Measured while walking this skill: a hand-rolled `print()` canary on the changed line ran, the
suite passed, and the token appeared **zero** times in the output, because a passing `pytest -q`
captures stdout and stderr. Read as an absence it says "nothing covers your change", which was
false. `stale-artifact-check`'s default canary form is a file write for exactly this reason, and
its table names which forms are hidden by what.

## How much the canary covers

Measured on a tree deliberately poisoned with stale bytecode: with the canary on the changed line,
the recorded run came back `canary OBSERVED, exit=0, ALL CHECKS PASSED` — planting the canary
changed the file's size, the stale bytecode was invalidated, and the run carrying the canary is the
honest one.

Poison the same way in a file you did **not** canary and the run comes back `canary OBSERVED` and
`exit=1`, `AssertionError: 11 != 10`, on a tree `git diff` calls unchanged. So the canary certifies
the run it is in, for the path it is on. A red sweep on a tree you watched go green is the other
half of the same problem; the unhappy path has a row for it and it routes to the same skill.

## Break-and-revert leaves something behind

A good reviewer runs your suite and probes it in your tree. One wrote, verbatim: *"I appended a
fake `bogus(w, h)` bullet to the README and reran it… I reverted the probe and confirmed the tree
is clean."* Break → red → revert restores the source and does not restore what the red run
compiled.

Reproduced deterministically: break one character in a source file, run the suite red, write the
original bytes back and restore the mtime the compile saw — `git diff --stat` empty, and the next
full run still `exit=1` with `AssertionError: 'abl' != 'ABL'` about source that plainly says
`.upper()`. Measured 9 trials in 12.

This is why Phase 2 does not forbid the probing and adds no clean-up step for it: a reviewer that
only reads is a weaker reviewer, and Phase 3 handles the consequence by observation rather than by
your remembering that it happened.

## A tail is not the suite's counts when the runner loops over files

The last lines are then the *last file's* counts, and quoting them under-reports by however many
files ran before it. Measured: a `tail -5` of a runner that runs each `tests/test_*.py` in its own
process and then lints returned `Ran 3 tests in 0.000s / OK / === lint === / ALL CHECKS PASSED` —
the last file's 3 assertions, from a suite of 4 tests across 2 files.

The count-lines grep in Phase 3 is a reading aid across the common runners, not a rule. Walked on a
`pytest -q` loop it printed `2:3 passed in 0.00s` and `4:2 passed in 0.00s`, which is two files and
five tests; the bare `tail -5` covering the same run showed the same two lines with nothing saying
they were two different files.

The exit status is always aggregate, which is why it is never the optional half of the quotation.

## A green suite on a tree the work is not in

`git stash` is the other move that looks like making the tree describable, and it removes the change
from the tree. Everything downstream then measures a tree the work is not in, and reports health.

Walked end to end: after `git stash -u`, the base ladder printed `UNDETERMINED`, the review packet
was **0 bytes**, the suite passed on a tree with no `diagonal()` in it, and the record was written —
a complete clean finish of nothing, with every phase reporting success. This is the same failure
class the canary exists for, arriving from the other direction: the run was honest, the tree was not
the one being published.

## The sweep command, written out literally

Phase 3 tells you to substitute what this project's own documentation calls full. The shape it has
in mind, writing to this finish's scratch directory:

```bash
./run_tests.sh > /tmp/finish-REPLACE/sweep.txt 2>&1; echo "exit=$?"
tail -20 /tmp/finish-REPLACE/sweep.txt      # the aggregate line, if this runner prints one
grep -nEi 'ran [0-9]+ test|[0-9]+ (passed|failed|error)|^(OK|FAILED|ERROR)' \
     /tmp/finish-REPLACE/sweep.txt          # one line per file, if it does not. Count them.
```

Two things that shape is protecting. If "full" is more than one command, put the commands in a
script **file** outside the repository and run that file — a shell variable holding several commands
word-splits. And the `grep` is a reading aid across the common runners, not a rule; the section above
has what it printed on a `pytest -q` loop, and why the bare `tail` under-reported the same run.
