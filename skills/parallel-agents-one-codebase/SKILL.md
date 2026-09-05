---
name: parallel-agents-one-codebase
description: "Use when two or more agents, subagents or separate Claude sessions, will EDIT, FIX or REFACTOR files in one shared working tree: 'fan out subagents to fix these modules', 'parallelize this refactor across the codebase', 'have agents fix these test failures at once', two sessions on one checkout. It prevents torn reads and agents reporting each other's half-written edits as bugs. Do NOT use for read-only fan-out (audit, review, search), or when each agent has its own worktree or clone."
---

# Parallel Agents, One Codebase

## Overview

Agents editing one working tree share mutable state: every read sees every other agent's uncommitted, possibly half-written edits. Partition the tree by exclusive file ownership, or the agents corrupt each other's evidence.

**Core principle: an agent may only edit files it owns, and reports rather than touches anything else.**

## When to Use

Use when agents will **write** to a shared checkout: parallel fixes across modules, parallel refactors, parallel test-failure repair. Two humans' Claude sessions on one checkout count.

**Read-only research fan-out?** Use `superpowers:dispatching-parallel-agents`.

**Separate trees?** If each agent gets its own worktree or clone (`superpowers:using-git-worktrees`), there is no shared state — skip this skill. Prefer that whenever the work is long-running and separable.

**Relationship to `superpowers:dispatching-parallel-agents`:** this skill **layers on top of** it for the shared-write case. Keep using it for prompt construction and domain decomposition, which this skill does not cover; add the partition here.

## Step 1: Build the Ownership Table

Derive the file set before the work reveals it — do not ask agents what they will touch:

1. For each task, locate its entry point (`git grep -ln '<symbol>'`, the failing test's target module).
2. Add every file that must change with it: the module, its direct tests, its fixtures.
3. `git log --format= --name-only -n 50 -- <file> | sort -u` shows what has historically changed alongside it — those are your likely collisions.

Render the table in full in your own reply before you dispatch anything, then check it for
disjointness by reading the rendered table, and only then copy each agent's row into that
agent's prompt:

```
| Agent | Owns (exclusive)                          | Task                          |
|-|-|-|
| A     | src/admission.py, tests/test_admission.py | Fix lease-expiry off-by-one   |
| B     | src/metrics.py, tests/test_metrics.py     | Add admission_checked counter |
| C     | src/capabilities.py, tests/test_caps.py   | Restore revoked-token check   |
```

**Check disjointness by reading the table.** A set of per-agent owned-file lists scattered across the dispatch prompts is not a table: with nothing rendered in one place, there is nothing to read for overlap, and the check is reported done without being performed. List concrete file paths, not directories or globs — then overlap is visible by eye. This is a judgment step, not a scripted one: any check you script must run inside a SINGLE shell block, because separate Bash calls do not share shell state and a variable set in one block is empty in the next.

**Test files:** give each agent the tests covering only its modules — it cannot prove a fix without them. A test file covering two owned modules cannot be split: assign it to ONE agent and have the other report failures in it, or give both modules to a single agent.

**Files discovered mid-wave:** the agent stops and reports the path; it does not claim it. The orchestrator either extends that agent's ownership (if no one else holds it) or defers it. Never let an agent widen its own scope.

## Step 2: The Dispatch Prompt Contract

Every agent prompt contains these four clauses verbatim:

1. **YOU OWN EXACTLY THESE FILES: `<list>`. Do not edit any other file.** Not to fix a test, not to add an import, not "just one line."
2. **Other agents are editing this repo right now.** Files you do not own may be mid-write or transiently broken.
3. **Check the committed baseline before reporting anything odd in a file you do not own.**
   ```bash
   git cat-file -e HEAD:src/capabilities.py 2>/dev/null \
     && git show HEAD:src/capabilities.py | grep -n 'RevokedTokenCache' \
     || echo "NO BASELINE - file is not in HEAD, it is another agent's work in progress"
   ```
   **Warning:** `git show HEAD:<path>` exits 128 for a file not in HEAD, and piping it straight to `grep` swallows that into an empty result that reads as "symbol absent" — which makes an agent retract a real finding. Guard it as above. If baseline and working tree disagree, it is an in-flight edit, not a defect.
4. **If you broke another module's test, REPORT it — do not edit their files.** Name the test, name your change, stop.

All four clauses are copied into every prompt as they are written above, not paraphrased and not summarised, and counting them in each prompt before dispatch is part of writing it: a prompt missing clause 3 leaves that agent unable to verify any cross-file observation it makes, so anything it reports about a file it does not own arrives unverified.

Add the API contract when one agent's output is another's input (see Wave Sequencing).

## Agents Without a Shell

Clause 3 requires running git commands. Before dispatching, check the agent type's tool list: analysis-only types (e.g. `code-analyzer`) have no Bash and **cannot perform the baseline check at all** — every cross-file observation they make is unverifiable by construction.

- Give shared-tree agents an agent type with Bash.
- Cannot change the type? Restrict it to files it owns, accept only code-reading conclusions, and run the baseline checks yourself.

For general agent-honesty discipline (fabricated output, unverified claims), see `superpowers:verification-before-completion` — out of scope here.

## Wave Sequencing

Sequence, do not parallelize, when one agent's change defines an API another consumes. State the contract in both prompts so the dependent agent codes against the contract instead of blocking:

> Contract: `metrics` derives all counts from `admission_checked` events; the kernel MUST emit one per admission decision. Wave 1 (kernel) emits; Wave 2 (metrics) consumes.

Wave 1 completes and is committed. Then Wave 2 dispatches.

## What File-Level Ownership Cannot Partition

Some things have no single owner: a shared module both agents import, a lockfile every dependency change regenerates, generated code, formatter-touched files. Untracked files are another gap — two agents can each plan to create the same new file and no table review catches it unless you list intended new paths explicitly.

**These are serial work, not parallel work.** Deferring them "to a later wave" does not make them parallel — it converts that portion into a serial step, so plan for the cost rather than discovering it. Preferably the orchestrator makes the change before dispatch.

## The Global Test Suite Is Meaningless Mid-Flight

While N agents work, the whole-suite failure count measures other agents' RED tests, not your correctness. In one session it read 12 → 29 → 17 purely from in-flight work.

- **Agents:** run only the tests for files you own — `pytest tests/test_admission.py`, `npm test -- src/admission.test.ts`, `go test ./admission/...`. Never report a whole-suite count.
- **Orchestrator:** one authoritative run after every agent has returned and the tree is clean. If the repo has no single whole-suite command (monorepo, per-package suites), run the suite of every package touched in this wave and treat any package you did not run as unverified rather than passing.

## Orchestrator Discipline

**Never commit mid-flight.** `git add -A` sweeps other agents' half-finished files into your commit.

Committing only your own paths is safer but **not sufficient**: a whole-tree pre-commit hook (formatter, linter with `--fix`) mutates unowned files during a scoped commit, including ones being written right now. If the repo has such a hook, do not commit while agents run — wait, or bypass it for that one commit with `git commit --no-verify` and re-run the hook properly afterwards.

Before any commit:

```bash
git status --porcelain     # WHOLE tree, not just src/ - a scoped status hides
                           # stray edits to pyproject.toml, package.json, .env
git status --porcelain --ignored   # adds !! lines; ignored files are invisible
                                   # to every other porcelain form
```

Then run the authoritative test command. Re-verify every load-bearing claim yourself, by execution — an agent's report is a hypothesis until you have run the command.

## Cleaning the Four Dirty States

Read BOTH porcelain columns: column 1 is the index, column 2 the worktree.

| Porcelain | State | Fix |
|-|-|-|
| ` M path` | unstaged edit | `git checkout -- <path>` |
| `M  path` | staged edit | `git restore --staged --worktree -- <path>`. `git checkout --` exits 0 here and reverts NOTHING — the mutation stays. |
| `MM path` | staged AND unstaged | `git restore --staged --worktree -- <path>` (clears both columns) |
| `?? path` | untracked leftover | `git clean -n -- <path>` to preview, then `git clean -f -- <path>`. `git checkout --` fails on it, and a `??` line is a DIRTY tree, not a clean one. |
| `!! path` | ignored | **Visibility only.** Do NOT run `git clean` with `-x`: `git clean -fxd -- build/` removes the whole directory, so it will destroy `.env.local`, virtualenvs, and `node_modules`. Removing an ignored file is a manual, per-path decision the orchestrator makes. |

After any fix, re-run `git status --porcelain` and require an empty line for that path.

## Unhappy Paths

**Two agents edited the same file.** There is only ONE version on disk, containing both edits interleaved. There is no "other version" to recover, and `git checkout -- <file>` reverts to HEAD and destroys BOTH agents' work irrecoverably. Preserve first, always:

```bash
cp src/metrics.py /tmp/conflicted-metrics.py   # snapshot the interleaved state
git stash push -- src/metrics.py               # tree back to HEAD, work recoverable
# ...inspect /tmp/conflicted-metrics.py; restore with: git stash pop
```

Then fix the partition and re-dispatch the two agents **sequentially** against the clean file. Never hand-merge two agents' uncommitted edits into a state neither agent has tested.

| Situation | Do this |
|-|-|
| Agent reports a failure in a file it does not own | Do not act on it. Re-run the check yourself once the tree settles. Most such reports are transient. |
| Agent reports a defect a later grep cannot find | It read a torn or mid-write file. Retract it and re-check against the baseline. |
| Agent needs a file it does not own changed | It reports the request; the orchestrator makes the edit, or it becomes a serial step. |
| An agent must mutate shared files in place (mutate → test → revert) | It runs **alone**, with no concurrent agents. Never concurrent. |

## Red Flags

- A dispatch prompt without an explicit owned-file list
- Two agents' owned lists that intersect anywhere, including tests
- An agent reporting a whole-suite failure count
- A cross-file finding reported with no baseline check
- `git checkout --` proposed as the fix for a two-agent collision (it destroys both) or for a staged change (it does nothing)
- `git add -A` or `git commit -am` while agents run
- Treating `??` lines in porcelain as a clean tree

## Common Mistakes

- **Splitting `src/` but sharing `tests/`.** The agent cannot prove its fix. Give it its tests.
- **Piping `git show HEAD:<path>` straight into grep.** It exits 128 for files not in HEAD, and the empty result reads as a false "symbol absent".
- **Scoping the pre-commit status check to source directories.** Config and lockfile drift stays invisible.
- **Treating "another agent broke it" as license to fix their file.** It is a reason to report and stop.

## Trigger precision

<!-- routing-pin
description-sha256: 22027714d2707fde2e52f3e75162c15712878c789dea91b16d818d5ab57b43dd
prompts-sha256: 0838eb792d28a6e7a72055b0cbd2369e8dfec8f7c5df8c77f2b85595731d8575
measured: 2026-09-01
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: verified 9/9 must-fire draws, 9/9 must-not-fire draws (3/3 each prompt over 3 runs) FIRST measurement in this repository. Promoted from ~/.claude/skills on 2026-09-01, where it was the only copy of itself. Its description was cut from 780 chars to 489 to meet the cap, which invalidated the pin it arrived with, so this is a fresh measurement of the new wording rather than a transcription.
-->

Prompts that MUST fire this skill:

1. "Fan out subagents to fix these four failing modules."
2. "Parallelize this refactor across the codebase."
3. "Have three agents fix these test failures at once."

Prompts that must NOT fire this skill:

1. "Fan out agents to research how these three libraries handle retries." (Read-only research fan-out: nothing writes to the tree, so there is nothing to partition.)
2. "Give each agent its own git worktree and let them work." (Separate trees need no partition; that is the alternative to this skill, not a use of it.)
3. "Review this pull request." (One agent, no concurrent writes.)
