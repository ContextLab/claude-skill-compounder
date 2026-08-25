---
name: destructive-op-preflight
description: "Use when about to run a command that can destroy work no commit or backup can bring back: git reset --hard, git checkout -- , git restore --worktree, git clean, git stash drop, push --force or --force-with-lease, rm -rf, a bulk delete or overwrite loop, or a database reset, drop, truncate, or migration rollback. Use when a safety flag has just refused an operation. Do NOT use for ordinary edits, commits, non-force pushes, branch creation, or reversible refactors."
---

# Destructive-op preflight

You are about to run a command whose failure mode is silent and permanent. The cost of
being wrong is not a broken build; it is somebody's afternoon, or their production data.
Enumerate what dies, prove it comes back, and only then run it.

## The Iron Law

```text
NO DESTRUCTIVE COMMAND WITHOUT A WRITTEN BLAST-RADIUS MANIFEST
AND A RECOVERY COMMAND THAT HAS ALREADY BEEN RUN.
```

Written means in the transcript, before the command, listing paths. Already been run means
the stash, branch, copy, or dump exists on disk now and you have inspected its contents.
Intent is not recovery. A plan to be careful is not recovery.

## Phase 1: locate, in one shell invocation

The working directory can differ between Bash calls. Chain the location check to the
command it protects so they cannot drift apart.

```bash safe
pwd && git rev-parse --show-toplevel && git branch --show-current
git rev-parse --abbrev-ref '@{u}' 2>/dev/null || echo 'NO UPSTREAM: every commit here is unpushed'
```

If the toplevel is not the repo you meant, stop. If the branch is not the branch you
meant, stop.

## Phase 2: enumerate the blast radius, do not estimate it

```bash safe
git status --porcelain
git ls-files --others --exclude-standard
git log --oneline '@{u}'..HEAD
git stash list
git clean -nd
```

`git ls-files --others --exclude-standard` is the important one. Those files exist in
exactly one place on Earth. For a filesystem delete, dry-run the target and show a count
plus real sample paths:

```bash safe
find build -type f | wc -l
find build -type f | head -5
git clean -ndx -- build/
```

Then write the manifest. It is short, and it goes in the transcript before the command:

```text
BLAST RADIUS: git reset --hard origin/main && git clean -fd
  repo:        /abs/path (branch main, upstream origin/main)
  unpushed:    1 commit  4e80d28 feature          -> reflog, 90 days
  staged:      src/app.py                          -> blob only, no filename
  unstaged:    README.md                           -> NOTHING
  untracked:   NOTES-DO-NOT-LOSE.md                -> NOTHING
  ignored:     build/ (contains .env.local)        -> NOTHING
RECOVERY:      git stash push --include-untracked -m preflight-<stamp>
               git stash pop --index
```

Every line ends in a recovery source or the word NOTHING. If any line says NOTHING, you
are in Phase 4, not Phase 5.

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

Three traps that have each caused a real loss:

- **`git checkout -- <path>` does not revert a staged mutation.** It restores the working
  tree from the index, and the index is where the bad content already is. Reverting a
  staged change to HEAD takes `git restore --staged --worktree <path>`, which destroys
  both copies at once. Verify which one you mean before typing either.
- **`git clean -fxd -- build/` removes the directory, not just the build output.** It
  takes `.env.local`, the venv, and `node_modules` with it. Scope to files
  (`git clean -fx -- 'build/*.js'`) or accept that the whole tree is gone.
- **`git stash pop` without `--index` restores the content but flattens the staging
  area.** Use `git stash pop --index` when the staged/unstaged split matters.

## Phase 4: make it recoverable, or stop

Never run a command with a NOTHING line in its manifest. Convert the line first. The
escape hatches are cheap:

```bash safe
git stash push --include-untracked -m "preflight-$(date +%Y%m%d-%H%M%S)"
git branch "backup/preflight-$(date +%Y%m%d-%H%M%S)"
cp -a build "build.preflight-bak"
```

Then prove the recovery actually holds what you think it holds. A stash you have not
looked inside is a guess:

```bash safe-seq
git stash push --include-untracked -q -m preflight-proof
git stash show --include-untracked --stat 'stash@{0}'
git stash pop --index -q
```

The listed files must include every path the manifest marked NOTHING. If a path is
missing from that output, the recovery does not cover it and the command does not run.

If you cannot construct a recovery (the target is outside a repo, the disk is full, the
database has no dump), **stop and ask.** Handing the user a one-line question costs a
minute. #23913 cost 2,229 files.

## Phase 5: run it, then re-enumerate

```bash destructive
git stash push --include-untracked -m "preflight-$(date +%Y%m%d-%H%M%S)"
git branch "backup/preflight-$(date +%Y%m%d-%H%M%S)"
git reset --hard origin/main
git stash pop --index
```

The stash carries the working tree, including the untracked files. The backup branch
carries the commits the reset is about to drop, under a name that outlives the reflog.
You need both; neither one covers the other.

Afterwards, re-run the Phase 2 enumeration and report what actually changed against the
manifest. A surprise here is a finding, not noise.

## Never escalate a safety flag that just refused

A rejected safe flag is information. It means your model of the remote or the schema is
wrong. Going around it converts a caught mistake into an uncaught one.

|Refused|Never follow with|Do instead|
|-|-|-|
|`git push --force-with-lease`|`git push --force`|`git fetch`, then read what moved|
|`prisma db push` warning|`--force-reset`|`--accept-data-loss` only after dumping|
|`git clean -n` looks wrong|widening the glob|narrow the path|
|A hook or sandbox denial|disabling the hook|treat the denial as the answer|

## Datastores

For any database reset, drop, truncate, or migration rollback: prove the backup exists,
**and prove it restores**, into a scratch database, before touching the real one. A dump
file nobody has ever restored is a file, not a backup. Per-tool commands (Postgres,
MySQL, SQLite, Prisma, Rails, Alembic, Django) are in
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
- "I'll stash it after, if it turns out to matter."
- "This is urgent enough to skip the confirmation."
- "The safeguard I set up earlier will catch it."
- "`--force-with-lease` failed, so I'll use `--force`."

## Common rationalizations

|Excuse|Reality|
|-|-|
|"It's just a scratch branch"|`git status --porcelain` costs 200ms and tells you. The branch name says nothing about the working tree.|
|"I already checked"|Checked when? Before your last three edits, or after? Re-run the enumeration in the same invocation as the command.|
|"The user asked me to"|The user asked for an outcome. They did not ask to lose the file they never mentioned because it was never in a commit.|
|"I generated these files, so they are disposable"|#23913: "The user said 'scaffolding' and the agent deleted everything matching the file extension." 2,229 untracked files.|
|"Untracked means unimportant"|Untracked means `.env.local`, the migration plan, the notes file. Untracked is the *only* category with no recovery path at all.|
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
|1 Locate|`pwd`, toplevel, branch, upstream, chained to the command|The path and branch are the intended ones|
|2 Enumerate|`git status --porcelain`, `ls-files --others`, `log @{u}..HEAD`, `clean -nd`|A written manifest exists, every line ending in a source or NOTHING|
|3 Classify|Read the recoverability table|You can name where each path comes back from|
|4 Protect|`stash push -u`, `branch backup/...`, `cp -a`, dump and test-restore|The recovery exists on disk and you have listed its contents|
|5 Run and verify|Chain location to command, then re-enumerate|The diff against the manifest is empty|
