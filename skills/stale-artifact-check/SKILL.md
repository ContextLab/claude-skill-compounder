---
name: stale-artifact-check
description: 'Use before treating any run as evidence about an edit you just made, and whenever a change appears to have had no effect at all. It answers one prior question, whether the artifact you just observed actually contains your edit, and it answers it by requiring an observed canary. Do NOT use it to work out what is wrong with the code, or to investigate a bug, a test failure, or unexpected behavior; that is systematic-debugging.'
---

# Stale artifact check

An edit landed in the source tree. The runtime loaded a different copy. Every observation
after that describes code nobody wrote, and every conclusion drawn from it is void. Sessions
lose hours here, editing correct logic repeatedly because the thing being exercised never
contained the edit. The cure is not more care. It is a proof obligation.

## The Iron Law

```
A RUN THAT HAS NOT PROVEN IT CONTAINS YOUR EDIT IS NOT EVIDENCE OF ANYTHING
```

## When this is the wrong skill

This is not a debugging procedure and it does not compete with one. It establishes a single
fact before debugging starts: is the code you observed yours? Once the answer is yes, this
skill is finished and `systematic-debugging` owns everything after it. Investigating a
failure, reading a stack trace, forming a hypothesis about a defect: none of that is here.

## Phase 1: Plant a canary

The canary is the whole skill. It works on every stack, including ones you have never seen,
because it asks the artifact itself rather than asking a mechanism you had to guess.

**1. Generate a fresh token, every single time.** Reusing one lets a stale file from an
earlier run masquerade as a live observation, and lets parallel agents in a shared tree find
each other's. The `CANARY-` prefix is how Phase 4 finds it later.

```bash
export CANARY="CANARY-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
echo "$CANARY"
```

**2. Insert it on a line the run must execute.**

|Form|Survives a capturing runner|Notes|
|-|-|-|
|`raise RuntimeError(os.environ["CANARY"])`|Yes|The run fails and the traceback carries the token. Strongest, and the default choice|
|`open(os.environ["CANARY"], "a").write("x")`|Yes|Nothing captures the filesystem. Name the file after the token, and delete it before every run|
|`print(token)` or a write to stderr|Only sometimes|A capturing runner shows it for a **failing** test and hides it for a passing one. Measured: a passing `pytest -q` prints it zero times, `pytest -q -s` once|

**3. Run the exact command whose result you were about to trust.** Not a similar one. Delete
any canary file first (`rm -f "$CANARY"`), or the previous run's evidence answers for this
one: a re-prove that executes nothing at all still finds yesterday's line in the file.

**4. Read the result.**

- **Canary observed.** The artifact is current. If nothing rebuilt or reinstalled in
  between, the earlier runs were of your code too. Remove the canary and go debug the logic.
- **Canary absent, on a line you have confirmed executes.** You are not running your code.
  Stop editing logic. Discard every conclusion from previous runs, including the ones that
  looked like progress. Go to Phase 2.

**Absence proves nothing about a line that never runs.** A canary in a function the suite
imports but never calls is silently absent from a passing run of a perfectly current
artifact. Put it where execution is not in question: module scope, which runs on import, or
the line the failing assertion sits on. A canary proves provenance for one path only, so
three edited files need three canaries.

## Phase 2: Find out which copy ran

There is exactly one mechanism check here, because it is the one that has been tested
against real stale installs and is right in every case those fixtures cover. For everything
else, go straight to Phase 3 and let the canary do the deciding.

### Python: which copy of the package the interpreter loads

Set `PKG` to the **import** name, which is not always the distribution name (`pip install
acme-widgets` may import as `acme`, and a submodule needs `ns.sub`). Set `SRC` to the file
you actually edited. Run it with the same interpreter and from the same directory as the
command you were about to trust, because both change the answer.

```bash
export PKG=mypkg SRC=src/mypkg/core.py
python3 - <<'PY'
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
    print("UNDECIDABLE: %s" % odd[0]); sys.exit(2)
if here is None:
    print("UNDECIDABLE: %r is not importable by this interpreter" % name); sys.exit(2)
if there is not None and here != there:
    print("UNDECIDABLE: two copies exist and the directory you run from picks between them")
    sys.exit(2)
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

Exit `0` is current, `1` is stale, `2` is undecidable and never means either.

- **STALE.** The interpreter is loading `site-packages`. Reinstall as `pip install -e .`
  into the interpreter that will run the code, which is not always the one on `PATH`. The
  verdict comes from asking `sysconfig` where this interpreter puts packages, not from
  testing whether the path sits under the repo: an in-repo `.venv` is the common case, and a
  `$PWD` test calls it current.
- **UNDECIDABLE, two copies.** A directory in the tree shadows an installed package, so this
  directory and every other directory load different files. Neither is wrong yet. Decide
  which invocation the result you care about came from, then reproduce that one exactly.
- **UNDECIDABLE, namespace or unimportable.** Read the printed paths and judge them yourself.

Every path here is compared after resolving symlinks. Do not hand-roll a comparison of
`$PWD` against a reported path: on macOS `/tmp` and `/var` are symlinks into `/private`, so
an unresolved comparison declares every temp directory stale.

## Phase 3: Force a clean pipeline, then re-prove

Nothing below is a diagnosis. Each is a way to remove a whole class of stale copy at once,
and the canary in Phase 1 is what tells you whether it worked. That is deliberate: a remedy
you verify beats a detector you trust.

- **Installed package**: reinstall editable, into the interpreter that runs the code.
- **Python bytecode**: `find . -name __pycache__ -type d -exec rm -rf {} +` and delete any
  `.pyc` outside `__pycache__`. Bytecode compiled with `--invalidation-mode unchecked-hash`
  is never revalidated, and a source whose mtime and size were restored exactly (a restore
  from archive, an rsync preserving times) is not revalidated either. Both serve old code
  while `mod.__file__` points at your edited source, so no path check can see them. Deleting
  the directory fixes both, which is why this is a remedy and not a check.
- **Build output**: a clean rebuild, not an incremental one. Then
  `grep -rl "$CANARY" dist/` to confirm the canary reached the output, which beats every
  timestamp comparison and has none of their false positives.
- **A running server**: find the process holding the port, confirm its working directory is
  this project and that it started after your edit, then kill that specific PID. Never
  blanket-kill by process name.
- **Containers, deployed copies, edge**: rebuild without the layer cache, confirm the
  container was recreated and not reused, and grep for the canary inside the running copy
  rather than comparing timestamps.

Re-run the canary after each. Only when it is observed may you edit logic again.

## Phase 4: Remove your canary, and only yours

A canary left behind is a raised exception in someone's production path, and an interrupted
session leaves them behind by definition.

```bash
: "${CANARY:?set CANARY to your own token first}"
mine=$(grep -rIn --exclude-dir=.git "$CANARY" .)
others=$(grep -rIn --exclude-dir=.git "CANARY-" . | grep -v -F "$CANARY")
[ -z "$others" ] || printf 'ANOTHER SESSION HAS A CANARY OUT, leave it alone:\n%s\n' "$others"
if [ -n "$mine" ]; then
  printf 'YOUR CANARY IS STILL IN THE TREE:\n%s\n' "$mine"
  exit 1
fi
echo "CLEAN: none of your canaries are left"
```

Two things this gets right that the obvious version does not. It greps the working tree
rather than `git diff`, which reports nothing for a staged file, nothing for an untracked
file, and nothing at all outside a repository. And it removes only your token: another
agent's canary in a shared checkout is live evidence in someone else's run, so report it and
leave it.

## Red flags

Each of these means stop and go to Phase 1:

- "The fix must not have worked, let me try a different approach."
- "That is strange, it should have changed."
- "Let me add some logging to see what is happening." (You will not see the logging either.)
- "I added a print and nothing printed."
- "The test still fails, so my change was wrong."
- "The test passes now, so my change worked."
- "I will just restart the server and try again." (Restarting is a remedy, so re-prove after.)

## Common rationalizations

|Excuse|Reality|
|-|-|
|"I literally just saved the file."|Saving proves the file changed. It proves nothing about what the interpreter loaded.|
|"There is no build step in this project."|Then there is an install step, an import path, or a running process. All three go stale.|
|"A canary is overkill for a one-line fix."|The canary costs 30 seconds. The phantom hunt costs an hour, and one-line fixes are exactly the ones people skip it for.|
|"I will check the artifact if the next attempt also fails."|The next attempt produces the same unusable evidence. Two void runs are not more informative than one.|
|"The timestamps look fine."|Timestamps are an inference, and a wrong one in both directions. The canary is an observation.|
|"The venv is inside the repo, so the path is under my project."|So is `site-packages`. That is why the check asks `sysconfig`, not the path prefix.|
|"The canary file has the token in it, so it ran."|Not if you did not delete the file first. That token may be from the run before.|
|"git diff came back clean, so the canary is gone."|Not if it was staged, in a new file, or outside a repo. Grep the tree.|

## Trigger precision

Prompts that MUST fire this skill:

- "I rewrote that function and reran the suite, and the output is character for character what it was before."
- "Third time applying this fix and the page renders exactly the same. Is it even picking up my changes?"
- "I added a console.log at the top of the handler and nothing prints."

Prompts that must NOT fire this skill:

- "The totals are off by one somewhere. Track it down." (A defect hunt, which is `systematic-debugging`.)
- "This test fails with `KeyError` on line 42. Fix it." (A failure to diagnose, with no edit of yours in question.)
- "Add retry-with-backoff to the HTTP client." (No run, and no claim about one.)

## Quick reference

|Phase|Action|Done when|
|-|-|-|
|1. Canary|Fresh token, on a line that certainly executes, running the exact command you were about to trust|Observed, or absent from a line you confirmed runs|
|2. Which copy|Python import provenance|Exit 0 current, 1 stale, 2 undecidable|
|3. Clean and re-prove|Reinstall editable, clear bytecode, clean rebuild, kill the old process, rebuild the image|The canary is observed|
|4. Clean up|Grep the tree for your token, report other sessions' tokens without touching them|Yours is gone|
