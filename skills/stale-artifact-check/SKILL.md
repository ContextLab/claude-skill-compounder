---
name: stale-artifact-check
description: 'Use when behavior after an edit is indistinguishable from behavior before it, such as byte-identical test output, the same error text, an unchanged page, or a fix reported as having had no effect. What is running may not contain the edit at all, which voids the evidence rather than the fix. Do NOT use for a bug you have not yet tried to fix, for a failure whose cause the error already names, or as a general debugging procedure; that is systematic-debugging.'
---

# Stale artifact check

An edit landed in the source tree. The runtime loaded a different copy. Every observation
after that point describes code nobody wrote, and every conclusion drawn from it is void.
Sessions lose hours here, editing correct logic repeatedly because the thing being exercised
never contained the edit. The cure is not more care. It is a proof obligation.

## The Iron Law

```
A RUN THAT HAS NOT PROVEN IT CONTAINS YOUR EDIT IS NOT EVIDENCE OF ANYTHING
```

## When this is the wrong skill

This is not a debugging procedure but the narrow check for when the *evidence* looks
impossible rather than the code looking wrong. A first investigation, a cause the error text
already names, or any root-cause hunt belongs to `systematic-debugging`. Come here only when
output that should have changed did not.

## Phase 1: Plant a canary

The canary is the universal proof, and the only step here that works on a stack you have
never seen. Detection commands can only find the mechanism you already thought of.

**1. Generate a token.** Never reuse one from this document, or parallel agents in a shared
tree find each other's. The `CANARY-` prefix is how Phase 4 finds it later.

```bash
export CANARY="CANARY-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
echo "$CANARY"
```

**2. Insert it on a line the run must execute.** Ranked by how little can swallow it:

|Form|Survives a capturing test runner|Cost|
|-|-|-|
|`raise RuntimeError(TOKEN)` / `throw new Error(TOKEN)`|Yes. The traceback is reported because the test fails|Breaks the run, which is the point|
|`open("/tmp/canary.out", "a").write(TOKEN)`|Yes. No runner captures the filesystem|Nothing breaks, so useful mid-suite|
|`print(TOKEN)` or a write to stderr|**No**|Only with capture disabled|

That last row is measured: a passing `pytest -q` whose code writes the token to stderr
prints it zero times, `pytest -q -s` prints it once. Most runners capture by default, so
before you trust a printed canary, find your runner's flag for turning capture off. The file
form needs no flag and is the safer default.

**3. Run the exact command whose result you were about to trust.** Not a similar one. If
you were about to believe a test, run that test.

**4. Read the result, carefully.**

- **Canary observed.** The artifact is current. If nothing rebuilt or reinstalled in
  between, the earlier runs were of your code too. Remove the canary, go back to the logic.
- **Canary absent, and you have confirmed the line executes.** You are not running your
  code. Stop editing logic. Discard every conclusion from previous runs, including any that
  looked like progress. Go to Phase 2.

**Absence proves nothing about a line that never runs.** A canary in a function the suite
imports but never calls is silently absent from a passing run of a perfectly current
artifact, which sends you to Phase 2 for no reason. Put it where execution is not in
question: module scope, which runs on import, or the line the failing assertion sits on. A
canary proves provenance for one path only, so three edited files need three canaries.

## Phase 2: Find the mechanism

Each check below exits `0` when the artifact is current, `1` when it is stale, and `2` when
it cannot tell and you must read the paths it printed. Run each one **with the same
interpreter and from the same directory as the command that produced the result you were
about to trust**, because both change the answer.

All of them resolve symlinks on both sides before comparing paths. Do not hand-roll a
comparison of `$PWD` against a reported path: on macOS `/tmp` and `/var` are symlinks into
`/private`, so an unresolved comparison declares every temp directory stale.

### Python: which copy actually loads

The usual cause is `pip install .` without `-e`, which copies the package into
`site-packages` and leaves the working tree as decoration. Set `SRC` to the file you
actually edited.

```bash
export PKG=mypkg SRC=src/mypkg/core.py
python - <<'PY'
import importlib.util, os, sys, sysconfig
name = os.environ["PKG"]
edited = os.path.realpath(os.environ["SRC"])
cwd = os.path.realpath(os.getcwd())
without = [p for p in sys.path if os.path.realpath(p or ".") != cwd]

def resolve(path):
    saved, sys.path[:] = sys.path[:], path
    importlib.invalidate_caches()
    try:
        spec = importlib.util.find_spec(name)
    except BaseException as exc:
        return "unresolvable (%s: %s)" % (type(exc).__name__, exc)
    finally:
        sys.path[:] = saved
    if spec is None:
        return None
    if not spec.origin or spec.origin == "namespace":
        return "namespace package spanning %s" % list(spec.submodule_search_locations or [])
    return os.path.realpath(spec.origin)

here, there = resolve([cwd] + without), resolve(without)
print("from this directory : %s" % here)
print("from anywhere else  : %s" % there)
print("the file you edited : %s" % edited)
odd = [v for v in (here, there) if isinstance(v, str) and not v.startswith(os.sep)]
if odd:
    print("CANNOT CHECK: %s" % odd[0]); sys.exit(2)
if here is None:
    print("CANNOT CHECK: %r is not importable by this interpreter" % name); sys.exit(2)
if there is not None and here != there:
    print("SPLIT: this directory loads a different copy than the rest of the system does")
    sys.exit(1)
lib = [os.path.realpath(p) for p in (sysconfig.get_paths().get("purelib"),
                                     sysconfig.get_paths().get("platlib")) if p]
if any(here == p or here.startswith(p + os.sep) for p in lib):
    print("STALE: an installed copy is being loaded, not your working tree"); sys.exit(1)
root = os.path.dirname(here)
if edited != here and not edited.startswith(root + os.sep):
    print("STALE: the file you edited is not inside the package that loads"); sys.exit(1)
print("CURRENT: the package that loads contains the file you edited"); sys.exit(0)
PY
```

Three verdicts and what to do about each:

- **STALE**: the interpreter is loading `site-packages`. Fix with `pip install -e .` into
  the interpreter that will run the code, which is not always the one on `PATH`. This is
  decided by asking `sysconfig` where this interpreter puts packages, not by testing whether
  the path sits under the repo, because an in-repo `.venv` is the common case and a `$PWD`
  test calls it current.
- **SPLIT**: a directory in the tree shadows the installed package on `sys.path`, so the
  repo root and anywhere else execute different files. One of your observations is of the
  wrong code. Decide which invocation matters and reproduce that one exactly.
- **CANNOT CHECK**: a namespace package or an unimportable name. Read the printed paths
  yourself, and do not read exit 2 as either verdict.

### Python: sourceless bytecode

A `.pyc` **outside** `__pycache__` imports even with no `.py` beside it, and that is the
only bytecode arrangement that silently serves old code.

```bash
strays=$(find . -name '*.pyc' -not -path '*/__pycache__/*' -print)
if [ -n "$strays" ]; then
  printf 'STALE: these import with no source present\n%s\n' "$strays"
  exit 1
fi
echo "CURRENT: no sourceless bytecode"
```

An orphan *inside* `__pycache__` is harmless, worth knowing because it is what people go
looking for: delete `foo.py` and `import foo` raises `ModuleNotFoundError`, since PEP 3147
bytecode never imports without its source. Clearing `__pycache__` is almost never the fix.

### Any build step: is the output newer than the source

The direct proof is the canary, and it outranks every timestamp:

```bash
if grep -rl "$CANARY" dist/; then
  echo "CURRENT: the canary reached the build output"
else
  echo "STALE: the canary is not in the build output"
  exit 1
fi
```

Only when there is no canary yet is mtime worth asking about. Set `SRC` and `BUILD` for the
stack (`src`/`dist`, `src`/`target/debug`, `lib`/`build`), and run from the package root
rather than a monorepo root.

```bash
export SRC=src BUILD=dist
python3 - <<'PY'
import os, sys
SRC, BUILD = os.environ.get("SRC", "src"), os.environ.get("BUILD", "dist")

def newest(root):
    best, where = -1.0, None
    for base, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(base, f)
            try:
                m = os.lstat(p).st_mtime
            except OSError:
                continue
            if m > best:
                best, where = m, p
    return best, where

for d in (SRC, BUILD):
    if not os.path.isdir(d):
        print("CANNOT CHECK: %r is not a directory under %s; set SRC and BUILD for this "
              "project and run from the package root" % (d, os.path.realpath(os.getcwd())))
        sys.exit(2)
sm, sp = newest(SRC)
bm, bp = newest(BUILD)
if sp is None:
    print("CANNOT CHECK: no files under %r" % SRC); sys.exit(2)
if bp is None:
    print("STALE: %r contains no build output at all" % BUILD); sys.exit(1)
print("newest source : %s" % sp)
print("newest build  : %s" % bp)
if sm > bm:
    print("STALE: a source file is newer than the newest build output"); sys.exit(1)
print("FRESH: the newest build output is newer than every source file"); sys.exit(0)
PY
```

Mtime lies in both directions. A `touch` with no content change reports STALE, a
reproducible build with pinned output timestamps reports STALE forever, and an incremental
build that skipped your file reports FRESH. When the verdict and your judgement disagree,
the canary settles it. Avoid the shell idiom `find dist -type f -exec ls -t {} + | head -1`
here: `-exec +` runs in batches and sorts each separately, so it can name the wrong file.

### Servers, containers, and remote copies

When the artifact reaches you over a socket rather than through an import, the old copy
hides somewhere else: an orphaned process on the port, an unrebuilt image, a release that
was uploaded but never symlinked. Commands are in `references/served-artifacts.md`.

## Phase 3: Fix the pipeline, then re-prove

Repair the mechanism, then run the canary again. The second most expensive failure in this
class is fixing the wrong stage, assuming it worked, and resuming the same phantom hunt with
more confidence than before. Only once the canary is observed may you edit logic again.

## Phase 4: Remove every canary

A canary left behind is a raised exception in someone's production path, and an interrupted
session leaves them behind by definition. Search the working tree by prefix, not the diff.

```bash
if grep -rn --exclude-dir=.git --exclude-dir=node_modules "CANARY-" . ; then
  echo "STALE CANARY: remove these before committing"
  exit 1
fi
echo "CLEAN: no canary left in the tree"
```

`git diff | grep` is not a substitute and passes while the canary is still there, reporting
nothing for a staged file, an untracked new file, or anything outside a repository. The tree
grep catches all three, and the shared `CANARY-` prefix also finds tokens an earlier session
left without recording.

## Red flags

Each of these means stop and go to Phase 1:

- "The fix must not have worked, let me try a different approach."
- "That is strange, it should have changed."
- "Let me add some logging to see what is happening." (You will not see the logging either.)
- "The test still fails, so my change was wrong."
- "The test passes now, so my change worked."
- "I will just restart the server and try again." (Restarting is a fix, not a diagnosis.)
- "This has to be a caching thing." (Then name the cache.)

## Common rationalizations

|Excuse|Reality|
|-|-|
|"I literally just saved the file."|Saving proves the file changed. It proves nothing about what the interpreter loaded.|
|"There is no build step in this project."|Then there is an install step, an import path, or a running process. All three go stale.|
|"A canary is overkill for a one-line fix."|The canary costs 30 seconds. The phantom hunt costs an hour, and one-line fixes are exactly the ones people skip it for.|
|"I will check the artifact if the next attempt also fails."|The next attempt produces the same unusable evidence. Two void runs are not more informative than one.|
|"The timestamps look fine."|Timestamps are an inference, and a wrong one in both directions. The canary is an observation.|
|"The venv is inside the repo, so the path is under my project."|So is `site-packages`. That is why the check asks `sysconfig`, not the path prefix.|
|"pip install . and pip install -e . are basically the same."|One copies, one links. That difference is this entire skill.|
|"git diff came back clean, the canary is gone."|Not if it was staged, in a new file, or outside a repo. Grep the tree.|

## Trigger precision

Prompts that MUST fire this skill:

- "I rewrote that function and reran the suite, and the output is character for character what it was before."
- "Third time applying this fix and the page renders exactly the same. Before I write it up as not working, is it even picking up my changes?"
- "The error message is identical after the patch, down to the line number."

Prompts that must NOT fire this skill:

- "This test fails with `KeyError` on line 42. Fix it." (First failure, cause in the error.)
- "The totals are off by one somewhere. Track it down." (A root-cause hunt, which is `systematic-debugging`.)
- "Add retry-with-backoff to the HTTP client." (No claim about a run at all.)

## Quick reference

|Phase|Action|Done when|
|-|-|-|
|1. Canary|Generate a token, put it where execution is certain, run the exact command you were about to trust|Observed, or absent from a line you confirmed runs|
|2. Mechanism|Which copy imports, sourceless bytecode, build output age, served copy|A check exits 1, or exit 2 sends you to read the paths|
|3. Fix and re-prove|Repair the stage, run the canary again|Canary observed|
|4. Clean up|Grep the whole tree for the `CANARY-` prefix|Nothing found|
