---
name: destructive-op-preflight
description: "Use when the next command could destroy work that nothing can bring back: it discards uncommitted or untracked changes, drops commits that were never pushed, overwrites what a remote already has, or removes files no version control is tracking. Also use when a safety flag has just refused an operation. Do NOT use for reversible work: ordinary edits, commits, non-force pushes, creating branches, dry runs that only print what would happen, or history edits the reflog can undo."
---

# Destructive-op preflight

You are about to run a command whose failure mode is silent and permanent. The cost of
being wrong is not a broken build; it is somebody's afternoon. Enumerate what dies, prove
it comes back, and only then run it.

This skill covers git and the filesystem. That is the whole scope.

## The Iron Law

```text
NO DESTRUCTIVE COMMAND UNTIL A RECOVERY EXISTS
AND THE WORKING TREE HAS BEEN PROVED EMPTY OF EVERYTHING IT HOLDS.
```

Proved empty means a command printed the residue and the residue was nothing. Not a list
you wrote and checked off: a list git produced after the recovery was taken. Intent is not
recovery, and a stash you have not measured is not coverage.

Code blocks below are tagged. A `safe` block only reads state and can be run as written; a
`destructive` block is the thing this procedure gates. This repository's tests execute
every `safe` block against a real fixture and assert its exit status, so what is written
here is what runs.

## Phase 1: locate, and refuse to start on unstable ground

```bash safe
pwd -P
git rev-parse --is-bare-repository
git rev-parse --show-toplevel 2>/dev/null || echo 'NO WORK TREE: bare repo, or not a repo at all'
git rev-parse --abbrev-ref HEAD
git rev-parse --abbrev-ref '@{u}' 2>/dev/null || echo 'NO UPSTREAM: every commit here is unpushed'
```

Run these as separate commands, not chained with `&&`. In a bare repo
`git rev-parse --show-toplevel` fatals with `this operation must be run in a work tree`, and
a chain would stop there, before the line that tells you why.

Compare `pwd -P`, not `pwd`. On macOS `/tmp` is a symlink to `/private/tmp`, so plain `pwd`
and the toplevel disagree in a way that means nothing.

Read `--is-bare-repository` **first**. A bare repo has no working tree to enumerate, its
destructive surface is refs rather than files, and it reports `HEAD` for the branch, which
would otherwise look like a detached HEAD. In a non-bare repo, a literal `HEAD` from
`--abbrev-ref HEAD` does mean detached, and that is the one place where the reflog is the
only thing holding your commits: create a branch before anything else. If `--show-toplevel`
fatals in a *non*-bare directory, you are not in a repo, and the filesystem procedure under
"Targets git does not cover" is the one that applies.

Then refuse to proceed while git is mid-operation. This check is the script's, not git's:
stopped at a `break` or `edit` during a rebase the index is clean, a stash succeeds, and
`reset --hard` runs to completion at rc=0 with the rebase still in progress.

```bash safe
git rev-parse --git-dir
ls "$(git rev-parse --git-dir)" | grep -E '^(rebase-merge|rebase-apply|MERGE_HEAD|CHERRY_PICK_HEAD|REVERT_HEAD|BISECT_LOG)$' || echo 'no operation in progress'
```

## Phase 2: enumerate everything that is not clean

Do not enumerate the status codes you can think of. `git status` reports only what is *not*
clean, so take every line it prints and subtract nothing. A code nobody anticipated then
fails closed instead of vanishing:

```bash safe
git status --porcelain -z -uall --ignored | tr '\0' '\n'
git ls-files -v | grep -v '^H' || echo 'no index flags set'
git log --oneline '@{u}'..HEAD 2>/dev/null || git log --oneline -20
git stash list
```

Three flags are load-bearing. `-uall` expands directories, so 50 doomed files under
`scaffold/` list individually instead of as the single line `Would remove scaffold/`; the
report behind this skill lost 2,229 untracked files, which a rollup would have described in
one line. `--ignored` adds the `!!` rows, which is where `.env.local` lives. `-z` stops git
quoting paths that contain spaces, and splits a rename into its new and old path on
separate lines rather than the unparseable `old -> new`.

That last one matters more than it looks. A staged rename carrying an unstaged edit is code
`RM`, and any hand-written list of "the dirty codes" misses it, along with `UU`, `AA`, ` T`,
`MD` and `AD`. Two hours of work in a renamed file reads as an empty blast radius.

`git ls-files -v` covers the blind spot that `status` cannot see at all. A file marked
**assume-unchanged** is invisible to `status`, and a local edit to it is destroyed with no
object anywhere and nothing in `fsck --lost-found`. Two measured facts make it worse than an
ordinary unstaged edit.

The invariant: it is **never captured by `git stash push --all`**, and never written as a
git object at all (0 out of 34 runs, sequential and under load). Whatever else happens, no
recovery you take contains it.

The hazard: whether any given command clobbers the working copy is **unspecified**. Git
trusts the cached stat data for these files and only sometimes re-reads them, so
`stash push` and `reset --hard` destroyed the edit in every sequential run measured here and
spared it in a few runs under concurrent load. Do not reason about which. Check **before**
the stash, because that is the last moment the edit exists and it is not going into the
recovery. Read the first column:

|Flag|Meaning|Fatal?|
|-|-|-|
|`H`|normal|no, this is every ordinary file|
|lowercase (`h`)|assume-unchanged|**yes**: invisible to status, never stashed, and clobbered unpredictably|
|`S`|skip-worktree|no: verified to survive `reset --hard`, even across commits|

Only the lowercase rows are a stop condition. Clear the bit with
`git update-index --no-assume-unchanged <path>` and the file becomes ordinary, visible to
`status`, and covered by the stash like anything else. `S` is not a stop condition: a
skip-worktree edit was verified to survive `reset --hard`, even across commits, and a gate
that fails on it is a gate people learn to route around.

One enumeration caveat, stated because it is easy to assume otherwise: `-uall` expands
untracked *directories*, but a nested git repository still prints as the single line
`?? nested/`. That is not a hole in the gate, because `git stash push --all` reports
`Ignoring path nested/` and leaves it in the residue, so the check fails closed. It is a
hole in the manifest, so look at it by hand.

For a filesystem target, count symlinks too. `find -type f` reports `1` for a tree whose
only entry is a symlink to somebody else's data:

```bash safe
find build \( -type f -o -type l \) | wc -l
find build \( -type f -o -type l \) | head -5
```

The manifest is one line per path from that output, plus one line per unpushed commit. Not
per category: a five-line rollup satisfies every wording of "write a manifest" and tells you
nothing.

```text
BLAST RADIUS: git reset --hard origin/main && git clean -fdx
  branch main @ /abs/path, upstream origin/main
  commit  4e80d28 feature                     -> reflog + backup branch
  RM report.md -> FINAL-REPORT.md  (staged rename, unstaged edit) -> NOTHING
   M README.md             (unstaged)         -> NOTHING
  ?? NOTES-DO-NOT-LOSE.md  (untracked)        -> NOTHING
  !! build/.env.local      (ignored)          -> NOTHING
RESIDUE GATE: git status after the stash must print nothing at all
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
  `git stash push --all` covers both.
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
- **An unset variable makes `rm -rf "${VAR}/build"` into `rm -rf /build`.** Use `set -u`,
  or test it (`[ -n "${VAR:-}" ] || exit 1`) in the same invocation. This is the most
  famous instance of the whole failure class.

## Phase 4: take the recovery, then measure the residue

`git stash push --all` is the default move: it covers tracked, untracked and ignored files
in one object. For commits, a named branch outlives the reflog. For a path git does not
track, the copy is the recovery.

Then prove coverage by subtraction rather than by comparing path lists. Path lists look
more precise and are strictly worse: `status` quotes paths with spaces and
`stash show` does not, renames arrive as `old -> new`, and an unanticipated status code
silently contributes nothing to compare. The residue check has none of those failure modes,
because git computes both sides:

```bash safe-seq
test -z "$(git ls-files -v | grep '^[a-z]' || true)"
git stash push --all -q -m "preflight-proof-$$"
RESIDUE=$(git status --porcelain -uall --ignored)
git stash pop --index -q
printf '%s\n' "$RESIDUE"
test -z "$RESIDUE"
```

Two checks in order, and the order is the point. The index-flag test comes first because an
assume-unchanged file is destroyed by the stash itself, so checking afterwards reports a
clean residue over data that is already gone. The residue test comes second, and it captures
and pops *before* asserting, so a failed check hands the tree back instead of leaving it
stashed with no explanation. If the residue is empty, everything that was not clean is inside
the stash. If anything remains, the stash does **not** cover it and the destructive command
does not run.
This is what catches the cases nobody enumerated: a submodule-only change, for instance,
makes `stash push --all` exit 0 having created no entry at all, and the residue check fails
closed on the ` M sub` line still sitting there.

Two things this cannot see. Empty directories, because git does not track them and `status`
never reports them: if the target's structure matters, copy it aside. And a submodule whose
`.gitmodules` carries `submodule.<name>.ignore = dirty`, which hides its dirty state from
`status` and so empties the residue. Check `git config -f .gitmodules --get-regexp ignore`
when a submodule is in the blast radius. The risk is small (`clean -ffdx` was verified not
to touch an initialized submodule) but the gate cannot see it for you.

If you cannot construct a recovery, **stop and ask.** A one-line question costs a minute.
The incident behind this skill cost 2,229 files.

### The exit ramp for reproducible artifacts

`rm -rf node_modules && npm ci`, `rm -rf .venv && uv sync`, `rm -rf target dist` when every
byte is regenerated from a committed lockfile: enumerate once to confirm nothing else is in
there, then go. The test is whether a committed file regenerates it byte-for-byte. It fails
the moment the directory also holds `.env.local`, a downloaded model, or a data volume,
which is why Phase 2 lists ignored files instead of assuming.

## Phase 5: run it as one guarded script

Unchained lines are the bug, not the fix. Mid-merge, `git stash push` exits 1 with
`could not write index`, and an unchained `git reset --hard` on the next line runs anyway
with no recovery in existence. Every failure after the stash must also say where the work
went, or the user is left with an emptied tree and no idea it is recoverable.

```bash destructive
set -euo pipefail
TARGET="${TARGET:?set TARGET to the commit you are resetting to}"
STAMP="preflight-$(date +%Y%m%d-%H%M%S)-$$-${RANDOM}"
ours() { git stash list --format='%gd %gs' | grep -E "${STAMP}\$" | head -1 | cut -d' ' -f1; }
trap 'rc=$?; [ "$rc" -eq 0 ] && exit 0
      echo "ABORTED rc=$rc: the destructive command did not complete." >&2
      w=$(ours || true); if [ -n "$w" ]; then
        echo "YOUR WORK IS IN THE STASH $w (message $STAMP). Restore: git stash pop --index $w" >&2
      else echo "No preflight stash exists; the tree is as you left it." >&2; fi' EXIT
GITDIR=$(git rev-parse --git-dir)
for f in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG; do
  [ -e "$GITDIR/$f" ] && { echo "ABORTED: $f exists, an operation is in progress." >&2; exit 1; }
done
FLAGGED=$(git ls-files -v | grep '^[a-z]' || true)
test -z "$FLAGGED" || { echo "ABORTED: assume-unchanged files are invisible to status and are overwritten by the stash itself:" >&2; printf '%s\n' "$FLAGGED" >&2; echo "Clear with: git update-index --no-assume-unchanged <path>" >&2; exit 1; }
git rev-parse --verify --quiet "$TARGET^{commit}" >/dev/null || { echo "ABORTED: '$TARGET' does not resolve." >&2; exit 1; }
git stash push --all -m "$STAMP" || { echo "ABORTED: stash failed, no recovery exists." >&2; exit 1; }
MINE=$(ours || true)
RESIDUE=$(git status --porcelain -uall --ignored)
test -z "$RESIDUE" || { echo "ABORTED: these are not in the stash:" >&2; printf '%s\n' "$RESIDUE" >&2; exit 1; }
git branch "backup-$STAMP"
git reset --hard "$TARGET"
if [ -n "$MINE" ]; then git stash pop --index "$(ours || true)"; else echo "Nothing was stashed; nothing to restore."; fi
trap - EXIT
```

Five details are load-bearing, each of them a way this script fails without it:

- **Check the index flags before the stash, not after.** An assume-unchanged file is never
  captured by `git stash push --all`, and whether the stash also clobbers it in place is
  timing-dependent. Either way a gate placed after the stash reports an empty residue over
  an edit the recovery never took. This is the one precondition where the recovery step is
  the last moment the data still exists.
- **Resolve `TARGET` before the stash.** With no remote, `git reset --hard origin/main`
  fatals; checking it first means the abort happens while the tree is still intact rather
  than after it has been emptied.
- **Identify your stash by its unique message, anchored, never by position.** On a clean
  tree `git stash push` prints `No local changes to save` and exits **0**, creating nothing.
  Comparing the top of `refs/stash` before and after only proves the top changed: if
  another process stashes in between, that comparison says the entry is yours and you pop
  and delete somebody else's work. Matching `$STAMP` re-resolves correctly even when a
  concurrent push shifts your entry from `stash@{0}` to `stash@{1}`. The `\$` anchor is
  load-bearing: an unanchored `grep -F` also matches a concurrent `${STAMP}-continued`, and
  then the script pops and drops that stranger's entry, injects its content, and exits 0
  with your own work still stashed.
- **`backup-$STAMP`, not `backup/$STAMP`.** A pre-existing branch named `backup` makes the
  slashed form fail with `cannot lock ref`, and that failure lands after the tree is
  already stashed.
- **The `EXIT` trap covers every abort path**, including the ones `set -e` takes silently.
  It is the difference between "aborted" and "aborted, and here is where your work is".

Afterwards, re-run the Phase 2 enumeration and diff it against the manifest. A surprise
here is a finding, not noise.

## Targets git does not cover

Outside a work tree there is no stash and no reflog, so the copy *is* the recovery:

```bash safe
realpath build
cp -a build "${TMPDIR:-/tmp}/preflight-$(date +%Y%m%d-%H%M%S)-build"
```

Resolve with `realpath` before deleting, confirm the resolved parent is the tree you meant,
and copy before removing. In a bare repo the surface is refs: `git for-each-ref` enumerates
and `git bundle create` is the recovery. For a SQLite file, the same discipline needs a
census rather than a row count, and the procedure is in
[references/sqlite-preflight.md](references/sqlite-preflight.md). Longer git recovery
material is in [references/git-recoverability.md](references/git-recoverability.md).

Other databases are deliberately out of scope. Advice about wiping a production database
that nobody has executed is worse than no advice, so this skill does not offer any.

## Never escalate a safety flag that just refused

A rejected safe flag is information: your model of the remote or the tree is wrong. Going
around it converts a caught mistake into an uncaught one.

|Refused|Never follow with|Do instead|
|-|-|-|
|`git push --force-with-lease`|`git push --force`|`git fetch`, then read what moved|
|`git stash push` non-zero|running the command anyway|fix the merge or unreadable file first|
|An in-progress rebase or merge|stashing past it|finish or abort the operation|
|A hook or sandbox denial|disabling the hook|treat the denial as the answer|

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
|"It's just a scratch branch"|`git status` costs 200ms and tells you. The branch name says nothing about the working tree.|
|"I already checked"|Checked when? Before your last three edits, or after? Enumerate in the same invocation as the command.|
|"The stash succeeded"|Did you read its exit status, or only notice the next line ran? Mid-merge it exits 1 and stashes nothing; on a clean tree it exits 0 and stashes nothing. Measure the residue instead of trusting it.|
|"The manifest was empty, so nothing is at risk"|An empty manifest more often means the enumeration missed a status code. A staged rename with an edit is `RM`, which every hand-written code list omits.|
|"The user asked me to"|The user asked for an outcome. They did not ask to lose the file they never mentioned because it was never in a commit.|
|"I generated these files, so they are disposable"|#23913: the user said "scaffolding", and the agent deleted everything matching the file extension. 2,229 untracked files.|
|"Untracked means unimportant"|Untracked means `.env.local`, the migration plan, the notes file. Untracked and ignored are the only categories with no recovery path at all.|
|"It's under /tmp so nothing matters"|`/tmp` is where the copy you just took lives. It is also a symlink on macOS, so your path comparisons are comparing different strings.|
|"I'm in a worktree, the main tree is safe"|Worktrees share one object store and one `refs/stash`. `gc --prune=now` and `reflog expire` reach every tree, and `stash pop` here pops a stash pushed there.|
|"The tests will catch it"|Tests exercise tracked code. No suite has ever failed because an untracked file was deleted, which is exactly the category with no recovery.|
|"It's all committed"|Committed is not pushed, and staged is not committed. Both die to `reset --hard`.|
|"I put a safeguard in place"|#34327: Claude claimed it had written a git hook to block `reset --hard`. The hook did not exist on disk. Assert the file, do not assert the memory.|
|"The reflog has my back"|The reflog covers commits. Your untracked file was never an object. It has no reflog entry and never will.|
|"`--force-with-lease` failed, so `--force`"|#70378. The lease failed because the remote moved. Forcing does not resolve that; it overwrites it.|
|"Stopping to ask is slower"|One question costs a minute. #32938 cost 11 hours of inference output.|

## Trigger precision

<!-- routing-pin
description-sha256: 5ed8cdc4d1fc8c6608ac4072db2e8bcbdf25bfe929910fe4af1921bff54df49d
prompts-sha256: 5a42fa5841d8fc005fd7c133ff9c09cd1e120367bd928b6f5e83d9b5c7347d83
measured: never
cli: n/a
model: n/a
result: unmeasured
-->

MUST fire:
1. "start fresh, blow away everything not checked in"
2. "clear the local commits on this branch and sync to origin/main"
3. "delete the scaffolding files you generated, I only want the real source"

MUST NOT fire:
1. "run `git clean -nd` and tell me what it would remove"
2. "squash my last three commits with an interactive rebase before I push"
3. "commit these changes and push them to my feature branch"

The first must-fire names no command at all, and the first two must-nots name commands this
skill cares about deeply. That is the point: the trigger is the irreversibility of the
outcome, not the vocabulary. A dry run prints and changes nothing. An interactive rebase of
unpushed commits stays in the reflog.

## Sources

Every issue number cited here and in `references/git-recoverability.md` (#23913, #32938,
#34327, #70378, #81508) is recorded with its URL and a verbatim quote in
`notes/research/seed-skill-candidates.md` in this repository.
Check the numbers there rather than treating them as folklore.

## Quick reference

|Phase|Do|Done when|
|-|-|-|
|1 Locate|`pwd -P`, toplevel, bare check, `rev-parse --abbrev-ref HEAD`, in-progress check|Right repo, HEAD understood, no rebase or merge underway|
|2 Enumerate|`status --porcelain -z -uall --ignored`, `ls-files -v`, unpushed log, `find \( -type f -o -type l \)`|A manifest with one line per path, taken from what git printed|
|3 Classify|The recoverability table and the five traps|Every path has a named recovery source or the word NOTHING|
|4 Protect|`ls-files -v` check first, then `stash push --all`, `branch`, `cp -a`|No lowercase index flags before stashing, and `git status` empty after|
|5 Run|One guarded script: target resolved first, stash matched by message, `EXIT` trap|The abort path names where the work is, and re-enumeration matches|
