# Naming the base

Phase 0 step 2 makes you name the base commit by hand and then prove it by the file list
`git diff <base> HEAD --name-only` prints. This file is why it is a hand-naming rather than a
derivation, what the file list catches, and why every later block retypes the sha and checks that
it resolves. Nothing here is a step; the steps are in the body.

## Why no ref can name it

Until 2026-09-01 Phase 0 *derived* the base from an ordered list of candidate refs — the upstream,
`origin/HEAD`, `origin/main`, `origin/master`, `main`, `master`, the root commit — resolved through
`git merge-base`, and printed a confidence label beside the answer. Three consecutive rounds of cold
review each produced a blocking finding against it, each against a new counterexample, each after the
previous one was patched:

- a named candidate was a branch *tip*, not a fork point, so the packet carried the base branch's
  later commits as deletions;
- `git merge-base` returns HEAD itself when the work is already published, so a confident base was
  printed over a 0-byte packet and the body then read the work as lost;
- a branch cut from `develop` in a clone that also carries `origin/main` resolves against
  `origin/main` and builds a packet holding a colleague's commits; a repository whose default branch
  is `trunk` matches no candidate at all, falls through to the root commit, and builds a
  whole-history packet.

The list can never be closed — `main`, `master`, `develop`, `trunk`, a release branch, a fork's
upstream, no remote at all are all real workflows — so a reading built on it can never be trusted.
This is the same shape as the tree fingerprint cut from Phase 3 on 2026-08-26: **a set of guesses
that has to enumerate every case cannot be finished.** What replaced it is the one check that
produced no finding in any round: name the sha, and let the file list judge it.

## The five worlds, measured

Built with `worlds.sh` in the round-3 reproduction directory, each with `work.txt` as the whole unit
of work. "derived" is the pre-2026-09-01 block run verbatim; "hand-named" is Phase 0 step 2 as it
now stands, with the sha a reader would pick from `git log --oneline -20`.

|world|derived packet|hand-named packet|
|-|-|-|
|`feature` cut from the tip of `main`|`work.txt`|`work.txt`|
|`feature` cut from `origin/develop`, `origin/main` also present|`d1.txt d2.txt d3.txt work.txt`|`work.txt`|
|default branch `trunk`, no remote|`b.txt c.txt work.txt`|`work.txt`|
|work committed **and pushed**, HEAD `==` `origin/main`|no base named at all|`work.txt`|
|work pushed, then a teammate pushed on top|no base named at all|`work.txt`|

Three of the five are wrong or absent under the derivation and honest under the hand-naming, and the
two the derivation got right the hand-naming also gets right.

## What the file list catches, and in which direction

The check is decidable because Phase 0 step 1 has already written down what the unit of work is.
Measured in the `trunk` world:

```
base = the root commit          -> packet: b.txt c.txt work.txt   # holds files that are not the work
base = HEAD                     -> BASE IS HEAD  (an error HERE: this world's work IS committed)
base = the first of two work commits -> packet: work2.txt          # work.txt is MISSING
base = 3066977e5cdb (unretyped) -> NOT A COMMIT -- retype the base sha
```

So the two readings point opposite ways, and the body says both:

- **an extra path** — one that is not part of this unit of work — means the base is **too far
  back**. Pick a **newer** sha, further up `git log --oneline -20`.
- **a missing file** — one of yours that is not listed — means the base is **inside your own work**.
  Pick an **older** sha, further down.

Before Phase 1's commit the second reading is not available: the work is uncommitted, so it is
missing from the list by construction and every finish would read it as "too new". That is why
Phase 1 reads the same list again after the commit, and why Phase 0 says only the first reading is
decidable yet.

**`BASE IS HEAD` inherits the same split, and until 2026-09-01 it did not.** The transcript above
was taken in a world where the work is already committed, and there naming `HEAD` is an error. In
the ordinary world — Phase 0, work still uncommitted — the newest commit that is *not* your work is
`HEAD`, so the honest base **is** `HEAD` and the packet is empty by construction. The round-3 text
printed the error wording in both, and that is a deadlock rather than a warning: obeying it means
going one commit further back, which in a real branch is somebody else's commit (measured: a packet
of `.ci/config.yml`), whereupon the "too far back" reading sends you to a newer sha and the only
newer sha is `HEAD`. The body now prints two different readings from two different blocks, and
Phase 1's is the one that means an error.

## A review finding outside the boundary sentence, and why the sentence is what moves

The file list is decidable only against step 1's sentence, so a fix that lands outside that sentence
makes the check unsatisfiable rather than merely wrong. Measured on a four-commit branch whose
sentence read *"add `mul()` to `calc.py` with a test"*, where round 2 of the review demanded a fix to
`run_tests.sh` — a path the sentence does not name:

```
base=8301c86 (below the work) -> calc.py run_tests.sh test_mul.py   # extra path  -> "pick a NEWER sha"
base=065b433 (first work commit) -> run_tests.sh test_mul.py        # calc.py missing -> "pick an OLDER sha"
base=c21641f (second work commit) -> run_tests.sh                   # both work files missing
base=7928421 (HEAD)           -> (empty)                            # BASE IS HEAD, an error post-commit
```

Every sha is refused by one reading or the other, and the two readings point in opposite directions,
so no amount of walking the log terminates. Neither reading is wrong: the packet really does hold a
path the sentence does not cover, and the newer shas really do drop work.

What moves is the sentence. **An accepted review finding grows the unit of work**, so step 1's
sentence is amended to say so — *"...and make `run_tests.sh` run it"* — and the list is judged
against the amended sentence, under which `8301c86` is correct and the whole ladder terminates. The
amendment is not a private reinterpretation: Phase 5 puts it in the record, so the next reader sees
the same boundary the file list was judged against. And this is the reason the diff base has to
survive a growing unit at all — the diff it produces **is** the review packet, so the base cannot be
cut the way the tree fingerprint and the ref ladder were.

**Where it does not close, stated plainly.** A path that is genuinely neither the work nor tooling
you would amend the sentence to cover has no base that both accepts your work and excludes it. Pick
a newer sha if one exists; where none does — the path is inside a commit of your own, mixed with
work — this skill has no repair, because the alternative is rewriting history, which it never does.
Leave it, and name it in the record as in the branch and not part of the work.

## Two dots for `log`, and never three

The forms are not interchangeable across commands, and the mistake inverts between them. For `diff`,
three dots means "from the merge base"; for `log`, two dots means "commits reachable from HEAD but
not from the base" — what you want — while three dots is the *symmetric difference* and pulls the
other side's commits back in. Measured on a repository where `main` gained two commits after
`feature` branched off it:

```
git log --name-only --pretty=format: main..HEAD  | sort -u  ->  work.txt
git log --name-only --pretty=format: main...HEAD | sort -u  ->  m3.txt m4.txt work.txt
```

Phase 6 check 4 is a `git log`, so it takes two dots. With a sha rather than a branch name in hand
the distinction stops mattering for `diff`: `git diff <base sha> HEAD` and `git diff <branch>...HEAD`
are the same diff.

## Why every later block re-assigns the sha and checks that it resolves

Every Bash tool call is a fresh shell, so a variable set in Phase 0 is gone by the time the packet is
built. The failure is silent rather than loud: measured, with `base` unset, `git diff "$base"...HEAD`
prints **nothing on stdout, nothing on stderr, and exits 0**. There is no error to read past, and an
empty packet reads like a change with nothing in it — which is why Phase 1 and Phase 2 both judge a
packet by its byte count and never by its exit status.

Retyping the value inline does not fix this on its own, because the natural way to write a
placeholder is `<base>..HEAD`, and `<` and `>` are shell redirects. Measured: pasted verbatim into a
real repository, `git log --name-only --pretty=format: <base>..HEAD | sort -u` printed nothing and
exited **0** — bash aborted the command on a failed input redirect from a file named `base`, and the
pipe supplied `sort`'s status. Read as an answer it says the record is not published. So the blocks
assign a literal sha and then check it:

```bash
base=3066977e5cdb
git rev-parse --verify --quiet "$base^{commit}" >/dev/null || echo "NOT A COMMIT -- retype the base sha"
```

Left unretyped the sha is not a commit in your repository and the check says so; left unset,
`"$base^{commit}"` is `^{commit}`, which does not resolve either. Both mistakes are loud.

## The two worlds where there is no base to name

A directory that is not a git repository at all, and a repository with no commits yet, used to print
the same confident non-answer with exit **0**. Both are now loud and separate. Measured:

```
no .git:     git rev-parse --is-inside-work-tree -> NOT A GIT REPOSITORY -- this skill declines here
             git log --oneline -20 -> fatal: not a git repository (or any of the parent directories): .git
no commits:  git rev-parse --is-inside-work-tree -> it IS a repo
             git log --oneline -20 -> fatal: your current branch 'main' does not have any commits yet
```

The same silence used to reach the packet proof: in a directory with no `.git`,
`git diff main...HEAD | wc -c` prints `0` and exits **0**, because git's usage dump goes to stderr and
the pipe hands you `wc`'s status. That is why the repository check happens in Phase 0 and not when a
later block comes back quiet.
