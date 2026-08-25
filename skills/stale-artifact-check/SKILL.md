---
name: stale-artifact-check
description: Use when an edit appears to have had no effect, when the same failure repeats after a fix, before trusting a passing or failing test as evidence, or before reporting that a fix did not work. The running process, imported package, build output, or deployed image may not contain the edit at all, which voids everything observed. Do NOT use for a first-time failure whose cause is already visible in the error text.
---

# Stale artifact check

An edit landed in the source tree. The runtime loaded a different copy. Every observation
made after that point describes code you did not write, and every conclusion drawn from it
is void. Sessions lose hours here, editing correct logic over and over because the thing
being exercised never contained the edit.

The cure is not more care. It is a proof obligation: before a run counts as evidence, the
running artifact must demonstrate that it contains the change.

## The Iron Law

```
A RUN THAT HAS NOT PROVEN IT CONTAINS YOUR EDIT IS NOT EVIDENCE OF ANYTHING
```

No conclusion, no bug report, no "the fix didn't work", and no green test survives contact
with an unproven artifact. Prove provenance first, then reason.

## Phase 1: Plant a canary

This is the strongest single move, and it works on every stack, including ones you have
never seen. Do not start with detection commands; start with the canary. Detection commands
tell you about the mechanism you thought of. The canary tells you the truth.

1. Pick a line the change must traverse: the function you edited, the handler that serves
   the route, the entry point of the CLI.
2. Insert an unmistakable observable. Strongest first:
   - `raise RuntimeError("CANARY-7f3a")` / `throw new Error("CANARY-7f3a")`. An exception
     cannot be swallowed by a log level, a buffered stream, or a quiet test runner.
   - A unique marker printed to stderr, if an exception is too disruptive.
   Use a random token, not the word `test`. A grep for `test` matches everything.
3. Run the exact command whose result you were about to trust. Not a similar one. If you
   were about to believe a test, run that test. If you were about to believe the app, load
   the app.
4. Read the result:
   - **Canary observed:** the artifact is current, and provided nothing rebuilt or
     reinstalled in between, the earlier runs were of your code too. Remove the canary and
     go back to debugging the logic.
   - **Canary absent:** you are not running your code. Stop editing logic immediately.
     Discard every conclusion from previous runs, including any that looked like progress.
     Go to Phase 2.

A canary that fires proves provenance for one code path only. If you edited three files,
the canary in file one says nothing about files two and three.

## Phase 2: Find the mechanism

Something between the source file and the running process is serving an old copy. Work
down this list until one check fails. Each command below exits `0` when the artifact is
current and non-zero when it is stale.

### Python: a non-editable install

The single most common cause. `pip install .` copies the package into `site-packages`;
`import pkg` then resolves there forever, and the working tree is decoration.

```bash
PKG=mypkg REPO=$PWD python - <<'PY'
import importlib, os, sys
mod = importlib.import_module(os.environ["PKG"])
path = os.path.realpath(mod.__file__)
tree = os.path.realpath(os.environ["REPO"])
print(path)
sys.exit(0 if path.startswith(tree + os.sep) else 1)
PY
```

If it prints a path under `site-packages`, the fix is `pip install -e .` (or
`uv pip install -e .`) into the interpreter that will actually run the code. Verify which
interpreter that is with `which python` and `python -c "import sys; print(sys.prefix)"`;
a project venv that was never activated is the second most common cause.

### Python: a shadowing module in the working directory

`python` and `pytest` put the working directory on `sys.path` ahead of `site-packages`. A
file or directory in cwd whose name matches the package wins, so the same import resolves
to two different files depending on where you launched from. At least one of your runs is
then not running what you think it is. Compare the two resolutions directly:

```bash
export PKG=mypkg
here=$(python -c "import os,importlib; print(importlib.import_module(os.environ['PKG']).__file__)")
there=$(cd / && python -c "import os,importlib; print(importlib.import_module(os.environ['PKG']).__file__)")
if [ "$here" != "$there" ]; then
  echo "SHADOWED: cwd resolves $here, elsewhere resolves $there"
  exit 1
fi
echo "CONSISTENT: $here"
```

### Python: orphaned bytecode

Bytecode invalidation is by source mtime and size, so ordinary edits are safe. What is not
safe is a `.pyc` whose source was deleted or renamed: on a path with no `__init__.py`
guard, or under an older layout, it keeps importing a module that no longer exists in the
tree.

```bash
orphans=0
for p in $(find . -name '*.cpython-*.pyc'); do
  src=$(echo "$p" | sed -E 's#/__pycache__/([^/]+)\.cpython-[0-9]+\.pyc$#/\1.py#')
  if [ ! -f "$src" ]; then
    echo "ORPHAN: $p (source $src is gone)"
    orphans=1
  fi
done
[ "$orphans" -eq 0 ] || exit 1
echo "NO ORPHAN BYTECODE"
```

Clear with `find . -name __pycache__ -type d -exec rm -rf {} +` and re-run the canary.

### Node and TypeScript: an unrebuilt `dist/`

`main` in `package.json` points at compiled output. Editing `src/` changes nothing until
the build runs. This check is stale-safe: it compares the newest source file against the
newest build output.

```bash
newest_build=$(find dist -type f -exec ls -t {} + 2>/dev/null | head -1)
if [ -z "$newest_build" ] || [ -n "$(find src -type f -newer "$newest_build" -print -quit)" ]; then
  echo "STALE: dist/ is older than src/"
  exit 1
fi
echo "FRESH: $newest_build"
```

The fix is the project's build, then the canary again. Watch mode counts as a build only
if you can see it report a successful recompile after your edit.

### Any compiled language, any build step

Same shape as `dist/`: the binary is older than its inputs. Substitute the output path
(`target/debug/app`, `build/bin/app`, `*.jar`, `*.wasm`) for `dist` and the source root for
`src`. An incremental build that skipped your file because of a bad dependency graph is
indistinguishable from no build at all, so a clean rebuild is the reliable escalation.

### Test runners

A green suite is the most expensive place to be wrong.

- The test imported the installed copy, not the tree. Run the Python check above from
  inside the test process, not from the shell.
- `.pytest_cache`, `.tox`, `node_modules/.cache`, `.next/cache`, and Jest's transform cache
  can all serve prior output. Delete the cache directory rather than reasoning about it.
- A collection error in one file can make a runner report the remaining suite as passing.
  Compare the test count against the previous run before believing an improvement.

### Servers, containers, and remote copies

The deployed copy predates the edit, or an old process still owns the port. Detail and
commands are in `references/servers-and-images.md`; load it when the artifact you are
exercising is served rather than imported.

## Phase 3: Fix the pipeline, then re-prove

Correct the mechanism you found, then run the canary again. Do not skip this. The second
most expensive failure in this class is fixing the wrong pipeline stage, assuming it
worked, and resuming the same phantom hunt with more confidence than before.

Only when the canary is observed may you go back to editing logic.

## Phase 4: Remove the canary

A canary left in the tree is a raised exception in someone's production path.

```bash
git diff | grep -c CANARY-7f3a
```

It must print `0` before you commit. Read the printed count, not the exit status: `grep -c`
exits non-zero precisely when the count is zero, which is the outcome you want. Because the
token is random, the match is exact.

## Red flags

Each of these is the same thought, and each one means stop and go to Phase 1:

- "The fix must not have worked, let me try a different approach."
- "That's strange, it should have changed."
- "Maybe I edited the wrong function." (Maybe. Prove it before rewriting anything.)
- "Let me add some logging to see what's happening." (You will not see the logging either.)
- "The test still fails, so my change was wrong."
- "The test passes now, so my change worked."
- "I'll just restart the server and try again." (Restarting is a fix, not a diagnosis; you
  still do not know what was being served.)
- "It works locally but not in the container."
- "This has to be a caching thing." (Then prove which cache, by name.)

## Common rationalizations

|Excuse|Reality|
|-|-|
|"I literally just saved the file."|Saving proves the file changed. It proves nothing about what the interpreter loaded.|
|"There's no build step in this project."|Then there is an install step, an import path, or a running process. All three go stale.|
|"The editor shows my change."|The editor reads the tree. The runtime may not.|
|"A canary is overkill for a one-line fix."|The canary costs 30 seconds. The phantom hunt it prevents costs an hour, and the one-line fixes are exactly the ones people skip it for.|
|"I'll check the artifact if the next attempt also fails."|The next attempt produces the same unusable evidence. Two void runs are not more informative than one.|
|"The timestamps look fine."|Timestamps are an inference. The canary is an observation.|
|"Restarting fixed it, so it was stale."|Probably, but you do not know which layer was stale, so you cannot prevent it recurring in ten minutes.|
|"pip install . and pip install -e . are basically the same."|One copies, one links. That difference is this entire skill.|

## Trigger precision

Prompts that MUST fire this skill:

- "I fixed the function but it still returns the old value."
- "The same test keeps failing after every fix I make. What am I missing?"
- "The app is still serving the old UI even though I refactored it yesterday."

Prompts that must NOT fire this skill:

- "This test fails with `KeyError: 'user_id'` on line 42. Fix it." (First failure, cause
  visible in the error.)
- "Add retry-with-backoff to the HTTP client." (No claim about a run at all.)
- "Why is this query slow?" (A performance question about code that is demonstrably
  running.)

## Quick reference

|Phase|Action|Done when|
|-|-|-|
|1. Canary|Insert a unique raise or marker on the changed path, run the exact command you were about to trust|Canary observed, or confirmed absent|
|2. Mechanism|Install path, cwd shadowing, bytecode, build output age, runner cache, served copy|One check exits non-zero|
|3. Fix and re-prove|Repair the pipeline stage, run the canary again|Canary observed|
|4. Clean up|Grep the diff for the canary token|The count is `0`|
