---
name: destructive-op-preflight
description: "Use when about to run a command that can destroy work no commit or backup can bring back: git reset --hard, checkout -f, checkout -- , restore --worktree, clean, stash drop, branch -D, rebase, reflog expire, gc --prune=now, filter-repo, push --force, rm -rf, a bulk delete or overwrite loop, or a database reset, drop, truncate, or migration rollback. Use when a safety flag has just refused. Do NOT use for ordinary edits, commits, non-force pushes, branch creation, or reversible refactors."
---

# Destructive-op preflight

You are about to run a command whose failure mode is silent and permanent. The cost of
being wrong is not a broken build; it is somebody's afternoon, or their production data.
Enumerate what dies, prove it comes back, and only then run it.

## The Iron Law

```text
NO DESTRUCTIVE COMMAND WITHOUT A PER-PATH BLAST-RADIUS MANIFEST
AND A RECOVERY WHOSE CONTENTS YOU HAVE DIFFED AGAINST IT.
```

Per-path means one line per file, never one line per category. Diffed means a command
printed the difference between what is at risk and what the recovery holds, and it printed
nothing. Intent is not recovery. A stash you have not listed is not recovery.

## Phase 1: locate

```bash safe
pwd -P && git rev-parse --show-toplevel && git rev-parse --abbrev-ref HEAD
git rev-parse --abbrev-ref '@{u}' 2>/dev/null || echo 'NO UPSTREAM: every commit here is unpushed'
```

Compare `pwd -P`, not `pwd`. On macOS `/tmp` is a symlink to `/private/tmp`, so plain `pwd`
and the toplevel disagree in a way that means nothing. If the resolved paths still differ,
you are in a subdirectory, which is fine; if the toplevel is not the repo you meant, stop.

Read the branch with `rev-parse --abbrev-ref HEAD`, not `branch --show-current`: on a
detached HEAD the latter prints an empty line, and a detached HEAD is the one place where
the reflog is the *only* reference holding your commits. If it prints `HEAD`, you are
detached: create a branch before anything else.

If either command fatals you are not in a work tree. `git rev-parse --is-bare-repository`
returns `true` for a bare repo, where there is no working tree to enumerate and the only
destructive surface is refs. For a target outside any repo, skip to
"Targets git does not cover".

## Phase 2: enumerate every path, do not summarize

```bash safe
git -c core.quotePath=false status --porcelain -uall --ignored
git log --oneline '@{u}'..HEAD 2>/dev/null || git log --oneline -20
git stash list
```

`-uall` is load-bearing. Without it, 50 doomed files under `scaffold/` print as the single
line `Would remove scaffold/`, and `git clean -nd` has the same defect. The report this
skill exists to prevent lost 2,229 untracked files; a directory rollup would have described
that as one line. `--ignored` adds the `!!` rows, which is where `.env.local` lives.

Read the status codes as risk classes: `??` untracked and `!!` ignored have no git object
at all, ` M` and ` D` are unstaged and have none either, and `M ` or `A ` are staged, so
only their content survives. Capture the at-risk set now, while the tree still has it:

```bash safe
git -c core.quotePath=false status --porcelain -uall --ignored | grep -E '^(\?\?|!!| M| D|MM|AM)' | cut -c4- | sort > "${TMPDIR:-/tmp}"/preflight-at-risk.txt
git -c core.quotePath=false status --porcelain -uall --ignored | grep -cE '^(\?\?|!!| M| D|MM|AM)'
```

For a filesystem target, count symlinks too. `find -type f` reports `1` for a tree whose
only entry is a symlink to somebody else's data:

```bash safe
find build \( -type f -o -type l \) | wc -l
find build \( -type f -o -type l \) | head -5
```

The manifest is one line per path from that output, plus one line per unpushed commit. Not
per category. A five-line rollup satisfies every wording of "write a manifest" and tells
you nothing:

```text
BLAST RADIUS: git reset --hard origin/main && git clean -fdx
  branch main @ /abs/path, upstream origin/main
  commit  4e80d28 feature                     -> reflog + backup branch
  M  src/app.py            (staged)           -> dangling blob, content only
   M README.md             (unstaged)         -> NOTHING
  ?? NOTES-DO-NOT-LOSE.md  (untracked)        -> NOTHING
  !! build/.env.local      (ignored)          -> NOTHING
COVERAGE GATE: comm -23 at-risk covered  =>  must print nothing
```

## Phase 3: what is actually recoverable

|State|`reset --hard`|`clean -fd`|`checkout --`|Recoverable from|
|-|-|-|-|-|
|Pushed commits|dropped|survives|survives|the remote|
|Unpushed commits|dropped|survives|survives|reflog, until gc|
|Staged changes|destroyed|survives|**survives**|a dangling blob, content only, no filename|
|Unstaged changes|destroyed|survives|destroyed|nothing|
|Untracked files|survives|**destroyed**|survives|nothing, ever|
|Ignored files|survives|survives (`-x` destroys)|survives|nothing, ever|

The reflog covers commits. It does not cover the working tree. `git add` does write a blob,
so staged content survives a `reset --hard` as a dangling object you can find with
`git fsck --lost-found` and read with `git cat-file -p` (the path is not stored; you match
it by content). An untracked file was never added, so it has no object at all. After
`git clean -fd`, no reflog entry, no `fsck --lost-found`, and no `fsck --unreachable` will
produce it, because there is nothing to produce.

Five traps that have each caused a real loss:

- **`git stash push --include-untracked` does not stash ignored files.** It takes `??` and
  leaves `!!` on disk, so a `clean -fdx` after it still destroys `.env.local`. Only
  `git stash push --all` covers both. Verified: with `build/` ignored, `-u` stashed one
  file and left `build/.env.local` sitting on disk.
- **`git checkout -- <path>` does not revert a staged mutation.** It restores the working
  tree from the index, and the index is where the bad content already is. Reverting a
  staged change to HEAD takes `git restore --staged --worktree <path>`, which destroys
  both copies at once. Verify which one you mean before typing either.
- **`git clean -fxd -- build/` removes the directory, not just the build output.** It
  takes `.env.local`, the venv, and `node_modules` with it. Scope to files
  (`git clean -fx -- 'build/*.js'`) or accept that the whole tree is gone.
- **A trailing slash on a symlink makes `rm -rf` follow it out of the tree.** Verified:
  `rm -rf tree/link/` where `link -> ../outside` deleted the contents of `outside`, which
  no enumeration of `tree` ever mentioned. Resolve the target with `realpath` first and
  never write the trailing slash.
- **An unset variable makes `rm -rf "${VAR}/build"` into `rm -rf /build`.** Set
  `set -u`, or test the variable (`[ -n "${VAR:-}" ] || exit 1`) in the same invocation.
  This is the most famous instance of this whole failure class.

## Phase 4: make it recoverable, then prove the coverage

```bash safe
git stash push --all -m "preflight-$(date +%Y%m%d-%H%M%S)"
git branch "backup/preflight-$(date +%Y%m%d-%H%M%S)"
cp -a build "build.preflight-bak"
```

`--all` on a repo with an ignored `node_modules` or `.venv` is slow and large. Scope it
(`git stash push --all -- src/ config/`) or copy those paths aside instead, but then say
in the manifest which ignored paths you chose not to cover and why.

Listing a stash is not proof of coverage; the coverage gate is a diff, and it must print
nothing:

```bash safe-seq
git -c core.quotePath=false status --porcelain -uall --ignored | grep -E '^(\?\?|!!| M| D|MM|AM)' | cut -c4- | sort > "${TMPDIR:-/tmp}"/preflight-at-risk.txt
git stash push --all -q -m preflight-proof
git stash show --include-untracked --name-only 'stash@{0}' | sort > "${TMPDIR:-/tmp}"/preflight-covered.txt
comm -23 "${TMPDIR:-/tmp}"/preflight-at-risk.txt "${TMPDIR:-/tmp}"/preflight-covered.txt > "${TMPDIR:-/tmp}"/preflight-uncovered.txt
test ! -s "${TMPDIR:-/tmp}"/preflight-uncovered.txt
git stash pop --index -q
```

Any path `comm` prints is at risk and uncovered, and the destructive command does not run
until it is covered or the user has said to abandon it. The gate fires on absence rather
than trusting you: if Phase 2 never ran, the at-risk file does not exist,
`comm` exits non-zero, and the gate fails. Skipping the enumeration cannot look like
passing it.

If you cannot construct a recovery (the target is outside a repo, the disk is full, the
database has no dump), **stop and ask.** Handing the user a one-line question costs a
minute. #23913 cost 2,229 files.

### The exit ramp for reproducible artifacts

`rm -rf node_modules && npm ci`, `rm -rf .venv && uv sync`, `rm -rf target dist build` when
every byte is regenerated by a committed lockfile: enumerate once to confirm nothing else is
in there, then go. The test is whether a committed file regenerates it byte-for-byte. It
fails the moment the directory also holds `.env.local`, a downloaded model, or a data
volume, which is why Phase 2 lists ignored files instead of assuming.

## Phase 5: run it as one guarded script

Four unchained lines is the bug, not the fix. Mid-merge, `git stash push` exits 1 with
`could not write index`, and the unchained `git reset --hard` on the next line then runs
with no recovery in existence. Chain it, check it, and say so when it aborts:

```bash destructive
set -euo pipefail
STAMP=$(date +%Y%m%d-%H%M%S)
BEFORE=$(git rev-parse -q --verify refs/stash || true)
git stash push --all -m "preflight-$STAMP" || { echo "ABORTED: stash failed, no recovery exists, destructive command NOT run" >&2; exit 1; }
AFTER=$(git rev-parse -q --verify refs/stash || true)
if [ -n "$AFTER" ] && [ "$AFTER" != "$BEFORE" ]; then MINE=yes; else MINE=no; fi
if [ "$MINE" = yes ]; then git stash show --include-untracked --name-only 'stash@{0}'; fi
git branch "backup/preflight-$STAMP"
git reset --hard origin/main
if [ "$MINE" = yes ]; then git stash pop --index; else echo "no preflight stash of ours; nothing to restore"; fi
```

`BEFORE`/`AFTER` is not ceremony. On a clean tree `git stash push` prints
`No local changes to save` and exits **0**, so an unguarded `git stash pop` at the end pops
somebody else's older stash: it injects last week's content into the tree and destroys the
recovery artifact Phase 2 just told the user to enumerate. Comparing the ref proves the
stash on top is the one this run created.

The stash carries the working tree, including untracked and ignored files. The backup
branch carries the commits the reset is about to drop, under a name that outlives the
reflog. You need both; neither covers the other.

Afterwards, re-run the Phase 2 enumeration and diff it against the manifest. A surprise
here is a finding, not noise.

## Targets git does not cover

Outside a work tree there is no stash and no reflog, so the copy *is* the recovery:

```bash safe
realpath build
cp -a build "${TMPDIR:-/tmp}/preflight-$(date +%Y%m%d-%H%M%S)-build"
```

Resolve the path with `realpath` before deleting it, confirm the resolved parent is inside
the tree you meant, and copy before removing. In a bare repo, the destructive surface is
refs rather than files: `git for-each-ref` is the enumeration and a bundle
(`git bundle create`) is the recovery.

## Never escalate a safety flag that just refused

A rejected safe flag is information. It means your model of the remote or the schema is
wrong. Going around it converts a caught mistake into an uncaught one.

|Refused|Never follow with|Do instead|
|-|-|-|
|`git push --force-with-lease`|`git push --force`|`git fetch`, then read what moved|
|`prisma db push` warning|`--force-reset`|`--accept-data-loss` only after dumping|
|`git stash push` non-zero|running the command anyway|fix the merge or unreadable file first|
|A hook or sandbox denial|disabling the hook|treat the denial as the answer|

## Datastores

For any database reset, drop, truncate, or migration rollback: prove the backup exists,
**and prove it restores into an empty scratch database with the same row count**, before
touching the real one. A restore into a scratch database that already has rows can report
success and a plausible count while having applied nothing. Per-tool commands and their
verification status are in
[references/datastore-preflight.md](references/datastore-preflight.md). Longer git
recovery material is in
[references/git-recoverability.md](references/git-recoverability.md).

## Red flags

Each of these is a thought, not an observation. If you notice one, you are in Phase 2:

- "It's just a scratch branch."
- "I already checked, there's nothing important there."
- "The user asked me to, so it's authorized."
- "I created these files, so they are mine to delete."
- "It's all committed anyway."
- "The stash succeeded, so I'm covered."
- "It's under /tmp, so nothing there matters."
- "I'm in a worktree, the main tree is safe."
- "The tests will catch it if I broke something."
- "This is urgent enough to skip the confirmation."
- "The safeguard I set up earlier will catch it."
- "`--force-with-lease` failed, so I'll use `--force`."

## Common rationalizations

|Excuse|Reality|
|-|-|
|"It's just a scratch branch"|`git status --porcelain` costs 200ms and tells you. The branch name says nothing about the working tree.|
|"I already checked"|Checked when? Before your last three edits, or after? Re-run the enumeration in the same invocation as the command.|
|"The stash succeeded"|Did you read its exit status, or the fact that the next line ran? Mid-merge it exits 1 and stashes nothing, and on a clean tree it exits 0 and stashes nothing. Compare `refs/stash` before and after.|
|"The user asked me to"|The user asked for an outcome. They did not ask to lose the file they never mentioned because it was never in a commit.|
|"I generated these files, so they are disposable"|#23913: "The user said 'scaffolding' and the agent deleted everything matching the file extension." 2,229 untracked files.|
|"Untracked means unimportant"|Untracked means `.env.local`, the migration plan, the notes file. Untracked and ignored are the only categories with no recovery path at all.|
|"It's under /tmp so nothing matters"|`/tmp` is where the dump you just took lives, and where editors keep unsaved buffers. It is also a symlink on macOS, so your path checks are comparing different strings.|
|"I'm in a worktree, the main tree is safe"|Worktrees share one object store and one `refs/stash`. `gc --prune=now` and `reflog expire` reach every tree, and `stash pop` here pops a stash pushed there.|
|"The tests will catch it"|Tests exercise tracked code. No test suite has ever failed because an untracked file was deleted, which is precisely the category with no recovery.|
|"It's all committed"|Committed is not pushed, and staged is not committed. Both die to `reset --hard`.|
|"I put a safeguard in place"|#34327: Claude claimed it had written a git hook to block `reset --hard`. The hook did not exist on disk. Assert the file, do not assert the memory.|
|"The reflog has my back"|The reflog covers commits. Your untracked file was never an object. It has no reflog entry and never will.|
|"`--force-with-lease` failed, so `--force`"|#70378. The lease failed because the remote moved. Forcing does not resolve that; it overwrites it.|
|"Resetting the dev database is harmless"|#36183: `prisma db push --force-reset`, run in the background, wiped production. Confirm which database the connection string points at.|
|"Stopping to ask is slower"|One question costs a minute. #32938 cost 11 hours of inference output.|

## Trigger precision

MUST fire:
1. "clear the local commits on this branch and sync to origin/main"
2. "delete the scaffolding files you generated, I only want the real source"
3. "the migration is stuck, just reset the dev database and re-run it"

MUST NOT fire:
1. "commit these changes and push them to my feature branch"
2. "make a branch called spike/retry-logic and switch to it"
3. "refactor this function into two smaller ones and update the callers"

## Quick reference

|Phase|Do|Done when|
|-|-|-|
|1 Locate|`pwd -P`, toplevel, `rev-parse --abbrev-ref HEAD`, upstream|Paths resolve to the intended repo and HEAD is not detached|
|2 Enumerate|`status --porcelain -uall --ignored`, `log @{u}..HEAD`, `find \( -type f -o -type l \)`|A manifest with one line per path, and the at-risk list saved to a file|
|3 Classify|Read the recoverability table and the five traps|Every at-risk path has a named recovery source or the word NOTHING|
|4 Protect|`stash push --all`, `branch backup/...`, `cp -a`, dump and test-restore|`comm -23 at-risk covered` printed nothing|
|5 Run|One guarded script: chained, exit-checked, `refs/stash` compared|The abort path is explicit and the re-enumeration matches the manifest|
