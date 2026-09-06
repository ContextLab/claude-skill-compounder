# Cutting a release

An installed copy of this package is a git checkout that hooks and symlinks point into, so
a release is a tag people can pin that checkout to. There is no build and nothing is
published to a registry: the version in `.claude-plugin/plugin.json`, the tag, and the ref
the README tells people to install are three names for the same commit, and the work here
is keeping them equal.

`install.sh` reads that tag through `SKILL_COMPOUNDER_REF` or `--ref`; why an install pins
one at all, and why `--update` is a separate ask, is in
[DESIGN.md](DESIGN.md#an-install-pins-a-ref-and-updating-is-a-separate-ask).

## Before the tag

1. **The suite is green on both operating systems.** Not the local run: the CI matrix in
   `.github/workflows/ci.yml` is `ubuntu-latest` and `macos-latest`, and macOS is where
   the bash 3.2 traps bite. `gh run list --branch main --limit 1` and
   `gh run view <id>` are enough to see it.
2. **`claude plugin validate --strict` passed**, which CI also runs. It is what
   marketplace review runs, and a `CLAUDE.md` at the repo root fails it.
3. **The end-to-end journey passed**, by hand, on the commit you are about to tag:
   `python3 tests/e2e/journey.py --out <a fresh dir>`. It spends real `claude -p` calls,
   so CI cannot run it and nothing else covers what it covers. [e2e.md](e2e.md) says what
   each step proves and what a `SKIPPED` row means.
4. **Every counted claim in `README.md` and under `docs/` still derives.** The
   `claim-provenance` skill is the procedure; the point is that a count in prose has no
   compiler behind it, and several of them ship with their derivation commands beside
   them — the knob counts in `docs/operations.md`, the review costs in `README.md`.
   Re-run those commands rather than reading the numbers.

## Cutting it

Pick the version first and use the same string everywhere. `X.Y.Z` with a leading `v` on
the tag and no `v` in the JSON, which is the split this repository already has.

1. **Bump `.claude-plugin/plugin.json`.** `"version": "X.Y.Z"`. Nothing reads it at
   runtime, so it is a label, and a label that disagrees with the tag is worse than none.
2. **Point the README at the new tag.** The pinned one-liner under `## Install` names a
   version literally, and so does the sentence saying whether it exists yet. Both change.
3. **Commit, push, and wait for CI again.** The bump is a commit like any other and it is
   the commit that gets tagged, so the green run that matters is the one after it.
4. **Tag and release:**

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   gh release create vX.Y.Z --title "vX.Y.Z" --notes "<what changed>"
   ```

   The annotated tag is the artifact; `gh release create` is what puts notes beside it and
   what makes the tarball URL predictable.

## Verifying the tag, in a throwaway config

`tests/test_install_sh.py` runs this sequence offline on every suite. It builds a bare
repository in a temp directory, tags two commits `v0.1` and `v0.2`, aims `install.sh` at it
with `SKILL_COMPOUNDER_REPO_URL`, and asserts that a pinned install lands on the tag, that a
plain re-run leaves HEAD where it was, that `--update` followed by `--rollback` returns the
tree to the first tag's commit, that the managed checkout's own copy moves it too, and that
a dirty checkout is refused with exit 3. What it cannot reach is everything the steps below
add: it clones over `file://` from tags it made itself, so nothing in it exercises the
`https://` URL the README hands people, the tag you actually pushed, or whether
`gh release create` left a release behind. Run the steps by hand against the real origin as
well.

Run `--update` and `--rollback` from the standalone `install.sh` (the copy `curl` fetched, or
`$SCRATCH/install.sh`), not from the copy inside the managed checkout at a ref older than
v0.3.1: through v0.3.0 that copy detected itself as a clone and skipped the move with exit 0
and no message, a defect found in exactly this verification on 2026-09-03. From v0.3.1 both
copies move the checkout, and a managed checkout with local changes is refused by name.


Never against your own `~/.claude`. Every one of these takes a `--claude-dir`, `--bin-dir`
and `--state-dir` under a scratch directory, and `CLAUDE_SKILL_COMPOUNDER_APP` decides
where the managed checkout lands.

```bash
SCRATCH=$(mktemp -d)
export CLAUDE_SKILL_COMPOUNDER_APP="$SCRATCH/app"
export CLAUDE_SKILL_COMPOUNDER_STATE="$SCRATCH/state"
DIRS="--claude-dir $SCRATCH/claude --bin-dir $SCRATCH/bin --state-dir $SCRATCH/state"

# 1. the pinned install the README now recommends, from a copy of the script that has no
#    checkout beside it -- otherwise install.sh installs THAT checkout and never clones.
cp install.sh "$SCRATCH/install.sh"
SKILL_COMPOUNDER_REF=vX.Y.Z bash "$SCRATCH/install.sh" $DIRS
git -C "$SCRATCH/app" describe --tags --exact-match HEAD     # must print vX.Y.Z
cat "$SCRATCH/state/install-ref"                             # current vX.Y.Z <sha>

# 2. a plain re-run must NOT move it
bash "$SCRATCH/install.sh" $DIRS
git -C "$SCRATCH/app" rev-parse HEAD                         # unchanged

# 3. update to the tag before it, then roll back to this one
bash "$SCRATCH/install.sh" --update --ref vX.Y.Z-1 $DIRS     # the previous tag's name
cat "$SCRATCH/state/install-ref"                             # previous vX.Y.Z <sha>
bash "$SCRATCH/install.sh" --rollback $DIRS
git -C "$SCRATCH/app" rev-parse HEAD                         # back at vX.Y.Z's commit

# 4. and uninstall gives the config back
bash uninstall.sh $DIRS
```

Step 3 is the one worth doing carefully, because it is the only step that exercises the
rollback record end to end. It was run between the two real tags on 2026-09-05, from a copy
of `install.sh` outside any checkout into temp directories with `SKILL_COMPOUNDER_NO_SURFER=1`:
`--ref v0.3.0` installed `a2aa2d4`, `--update --ref v0.3.1` moved the managed checkout to
`b7f6a47` and wrote `previous v0.3.0` into `install-ref`, and `--rollback` returned it to
`a2aa2d4` with the record inverted, each step exit 0. Before the second tag existed the same
proof used two branches; do it between tags now.

Two failure shapes to expect rather than debug from scratch. A clone made with
`--depth 1 --branch <ref>` is **single-branch**: its configured refspec names one branch,
so a later `--update` to a different ref has to name the refspecs explicitly, which
`fetch_ref` in `install.sh` does. And `--update` never runs `git pull` after checking a ref
out; the checkout is already at the fetched tip, and a pull there resolved against the
remote's default branch and refused a diverging merge.

## After it is out

- `git ls-remote --tags https://github.com/ContextLab/claude-skill-compounder.git` is what
  the README tells a reader to run to see which tags exist. Run it once yourself, so the
  sentence in the README about what has and has not been cut is true the day it ships.
- Anyone already installed stays where they are, by design. A plain re-run does not move a
  checkout, so upgrading is something they ask for: `install.sh --update --ref vX.Y.Z`.
