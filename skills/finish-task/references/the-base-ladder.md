# The base ladder

Phase 0 step 2 derives the base with a ladder rather than asking, and prints a `rung` alongside it.
This file is the evidence behind that shape. Nothing here is a step; the steps are in the body.

## Why the `= HEAD` skip has to be inside the loop

A base equal to HEAD produces an empty `<base>...HEAD` diff and therefore an empty review packet,
which reads like "there is nothing to review". An earlier version of the ladder tested the named
candidates inside the loop and then fell back to the root commit *outside* it. In a one-commit
repository that fallback returned HEAD, printed a confident base, and suppressed the escape hatch
the body gives for `UNDETERMINED`. The skip has to apply to every candidate, the last-resort root
commit included.

## What the root-commit rung actually produces

Measured, running the Phase 0 block verbatim on a five-commit repository, on a fresh `feature`
branch with the work uncommitted:

```
base=1d250e5323a6016294a5abd20df9a8eb6b6523ef rung=ROOT-FALLBACK
```

`git diff <that>...HEAD --name-only` printed `f2.txt f3.txt f4.txt f5.txt` — 472 bytes, four files
that are not the unit of work — and it did **not** contain `work.txt`, which is. Non-empty, so
Phase 1's byte count passes it; wrong in both directions, so Phase 2 would review the repository's
history instead of your change. That is the whole reason the body refuses to build a packet from a
pre-Phase-1 `ROOT-FALLBACK` value.

## What the re-run gives you

The two non-answers are the same fact wearing different clothes: a branch forked from its base with
the work still uncommitted *is* its base, so no named candidate can differ from HEAD. A one-commit
repository has nothing below it and prints `UNDETERMINED`; a repository with history falls through
to `ROOT-FALLBACK`.

Committing in Phase 1 is what separates them. Measured on the same five-commit repository, after
the Phase 1 commit the identical block printed:

```
base=main rung=named
```

This is where most projects actually get their base, which is why the body tells you to run the
block twice and use the second value.

## When the re-run still does not name one

A shallow clone, a detached root, or a branch with genuinely no named base above it can still print
`ROOT-FALLBACK` or `UNDETERMINED` after the commit. Neither is a reason to stop or to guess, and the
body says what to do with each. The principle underneath: a named-and-wrong base is worse than a
recorded gap, because the gap is visible in the record and the wrong name is not visible anywhere.

## Why Phase 2 retypes the base and never writes `"$base"`

Every Bash tool call is a fresh shell, so the variable the ladder set is gone by the time the packet
is built. The failure is silent rather than loud: measured, with `base` unset, `git diff
"$base"...HEAD` prints **nothing on stdout, nothing on stderr, and exits 0**. There is no error to
read past, and an empty packet reads like a change with nothing in it — which is why Phase 1 and
Phase 2 both judge a packet by its byte count and never by its exit status.
