# Git recoverability, in detail

Everything here was verified against git 2.50.1 on a real repository. Load it when the
Phase 3 table in `SKILL.md` is not enough: something is already lost, or you need to know
whether a specific state has an object behind it.

## The one question that decides everything

**Did git ever write an object for this content?** `git add` writes a blob.
`git commit` writes a tree and a commit. Editing a file in your editor writes nothing.
Creating a new file writes nothing.

|Content|Object written when|Findable after destruction by|
|-|-|-|
|Pushed commit|`git commit`|`git fetch` from the remote|
|Local commit|`git commit`|`git reflog`, `git fsck --unreachable`|
|Staged edit|`git add`|`git fsck --lost-found` (blob, no filename)|
|Stash entry|`git stash push`|`git fsck --unreachable` after a drop|
|Unstaged edit|never|nothing|
|Untracked file|never|nothing|

Everything with an object survives until `git gc` prunes it. The default grace period is
90 days for reachable-from-reflog objects and 2 weeks for unreachable ones, but `gc` can
run automatically after many git commands, so "it is still in the object store" is a race,
not a guarantee. Recover immediately.

## Recovering a dropped commit

```bash
git reflog                                  # every HEAD position, most recent first
git reflog show <branch>                    # per-branch history, including deleted tips
git fsck --unreachable --no-reflogs 2>/dev/null | awk '/commit/{print $3}'
git log -1 --format='%h %s' <sha>           # identify a candidate before restoring
git branch recovered/<name> <sha>           # name it so it stops being unreachable
```

`git reflog` is per-clone and per-worktree. A commit made in another worktree or another
clone is not in this reflog.

## Recovering a staged edit destroyed by `reset --hard`

The blob is there; the filename is not. You match by content.

```bash
git fsck --lost-found 2>/dev/null | awk '/dangling blob/{print $3}' | while read -r o; do
  echo "=== $o"; git cat-file -p "$o" | head -20
done
git cat-file -p <sha> > src/app.py          # write it back under the name you recognize
```

Verified: staging `STAGED_CONTENT` into `f.txt` and then running `git reset --hard` leaves
exactly one dangling blob whose contents are `STAGED_CONTENT`.

## Recovering a dropped stash

`git stash drop` removes the ref, not the commits.

```bash
git fsck --unreachable 2>/dev/null | awk '/commit/{print $3}' | while read -r c; do
  echo "$c  $(git log -1 --format=%s "$c")"
done
git stash apply <sha>                       # once you have identified the right one
```

A stash made with `--include-untracked` is three commits: the work, the index state
(`<sha>^2`), and the untracked files (`<sha>^3`). Inspect the third one specifically:

```bash
git cat-file -p '<sha>^3^{tree}'
```

## What has no recovery at all

- An unstaged edit destroyed by `git checkout -- <path>`, `git restore --worktree`, or
  `git reset --hard`. There is no object. Issue #81508 lost roughly two hours of finished
  work exactly this way.
- An untracked file destroyed by `git clean -fd`, `rm`, or being overwritten. It was never
  an object. #23913 lost 2,229 of them.
- An ignored file destroyed by `git clean -fxd`. Same reason, and this is where
  `.env.local` and local credentials live.
- Any of the above inside a directory removed wholesale. `git clean -fxd -- build/`
  removes `build/` itself, not merely the build products in it. Verified.

For each of these, the only defense is upstream of the command:
`git stash push --all` before it runs.

## Which stash flag covers what

Verified on the fixture in `tests/fixtures/destructive-op-preflight/`:

|Flag|Tracked changes|Untracked (`??`)|Ignored (`!!`)|
|-|-|-|-|
|`git stash push`|yes|no|no|
|`git stash push --include-untracked`|yes|yes|**no**|
|`git stash push --all`|yes|yes|yes|

`--include-untracked` is the flag most people reach for, and it leaves `!!` files sitting
on disk. A `git clean -fdx` after it still destroys `.env.local`. Use `--all`, and prove
coverage by measuring the residue rather than by diffing path lists:

```bash
git stash push --all -m "preflight-$$"
git status --porcelain -uall --ignored     # must print nothing at all
```

Path-list comparison looks more precise and is strictly worse. `git status` quotes paths
containing spaces and `git stash show --name-only` does not, so a legitimate path reads as
uncovered; a rename arrives as `old -> new`, which is not a path; and any status code the
list did not anticipate contributes nothing to either side, so the comparison passes while
the data is unprotected. The residue check has none of those failure modes because git
computes both halves.

`--all` is expensive when an ignored `node_modules` or `.venv` is in the tree. Scope it
with a pathspec (`git stash push --all -- src/ config/`) and record in the manifest which
ignored paths you left uncovered.

## Not covered by any of this

- **Submodules.** UNTESTED here. A `git clean -fdx` in a superproject can remove an
  uninitialized submodule directory, and a submodule's own untracked files are invisible
  to the superproject's `status` unless you pass `--recurse-submodules`. Enumerate inside
  each submodule separately before trusting a superproject manifest.
- **Files held open by another process.** `git stash push` fails on an unreadable path
  with `Cannot save the untracked files`, exit 1, having stashed nothing. That is why the
  Phase 5 script checks the exit status instead of chaining blindly.

## Force-push recovery

The old remote tip is not gone the instant you force-push, but you need its sha, and
nothing on your machine necessarily has it.

```bash
git reflog show origin/<branch>             # only if this clone fetched the old tip
git ls-remote origin                        # current state, after the fact
```

On GitHub, the overwritten commits stay reachable through the events API and through
`https://github.com/<owner>/<repo>/commit/<sha>` for a while, but only if you know the
sha. Capture it *before* the push:

```bash
git rev-parse origin/<branch> | tee /tmp/pre-force-push-tip.txt
```

When `--force-with-lease` is refused, the refusal already told you the remote moved. Fetch
and read what moved before doing anything else (#70378).

## `git clean` flag reference

|Flag|Effect|
|-|-|
|`-n`|dry run, prints "Would remove ..." and changes nothing|
|`-f`|actually remove (required unless `clean.requireForce=false`)|
|`-d`|recurse into untracked directories, and remove the directories themselves|
|`-x`|also remove ignored files (`.env.local`, `node_modules`, `.venv`)|
|`-X`|remove *only* ignored files, keeping other untracked ones|
|`-e <pat>`|add an exclusion on top of `.gitignore`|

`git clean -nd` before `git clean -fd`, every time. The dry run costs nothing and its
output is the manifest you were going to have to write anyway.
