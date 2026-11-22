# 2026-11-21: automatic `/insights` runs, session notes

Asked: use Claude Code's `/insights` periodically, at appropriate times, as a further source
of candidate lessons. The user required it to be fully automatic.

Design: `notes/2026-11-21-insights-design.md`. Plan: `notes/2026-11-21-insights-plan.md`.

## State at the end of the session

- Built in five tasks by subagents, each reviewed, then one whole-branch review, one fix
  wave and one scoped re-review (clean). Commits 43b6ed7..b271942.
- Tasks 1 to 3 (CLI: harvest, listing and settling, scheduling) are on `main` (bb328e9).
  Tasks 4 and 5 and the fix wave are on branch `worktree-agent-a80d451542a7c62d8`
  (b271942), held back on purpose: the live install loads the plugin from the main
  checkout, and merging makes the first typed prompt of the next new session start a real
  paid run.
- Checks at b271942: `./run_tests.sh` 29 files, `claude plugin validate --strict .` passed,
  `claude plugin test .` 364 pass.
- Also fixed on the way: the hook test fixtures for Claude Code 2.1.330 (7e28456), which
  had both plugin checks failing before this work.

## Later the same day

- The user asked for the journey to run with the Claude CLI's own login, not an API key.
  It gained `--config ambient` and passed 26 of 26 on its second real run (the first failed
  on a fault in the script); see `notes/2026-11-21-insights-journey.md`.
- `main` was fast-forwarded to b957788 after all three checks were run again at that
  commit. Not pushed. The feature is live in an install that loads the plugin from this
  checkout: the next new session's first typed prompt starts a real run when one is due.

## Open

1. The push waits for the user.
2. `--config fresh` of the journey was only dry-checked (it needs a credential in the
   environment). No real finding was about the journey's own scratch project, so showing a
   finding was proven with report findings only. The whole journey was run again after the
   follow-up (26 of 26, leg e's `headless` check included).
3. The plugin directory's ICON_MISSING warning needs artwork: a square PNG, 512 to 2048 px,
   under 2 MB, at `.claude-plugin/icon.png` or named by `icon` in `plugin.json`. Left to the
   user.

## Closed on 21 Nov (follow-up)

- Headless sessions: a `remind` carries `headless: true` when the prompt's origin is `sdk`
  and `$.session.surfaces()` is empty; `insight_states` does not count it.
- `isCollapsed`: the band's timer stops while no surface shows the band, and the drawing
  that expands it starts it again. No minimum version change.
- `COMPOUND_INSIGHTS_TIMEOUT` (default 900). The kill now SIGKILLs what is left of the group
  even after `claude` itself exited. `journey_insights.py --leg timeout` ran once for real
  under ambient: 15 of 15, 9 s, one child group of 3 processes, none left.
- The kill now has an automated test, `tests/test_stop_group.py`: `stop_group` against real
  `/bin/sh` groups (all obey SIGTERM; a child ignores it, killed by the SIGKILL after 5 s; a
  child outlives its exited leader; a dead or finished group stopped again), and
  `insights_timeout` parsing in a child interpreter. Passed on macOS, in ubuntu:24.04 with
  `--init`, and in python:3.9-slim. Without an init that reaps orphans (a container run with
  no `--init`) the killed children stay zombies, `killpg(pgid, 0)` still succeeds on Linux,
  four of its tests fail and `stop_group` waits its full 5 s; nothing is left running.
- `running` under 60 s old is not reported `interrupted` with the lock free.
- `add --settles` of a facet finding with no project: user level only.
- `HIDDEN_CHARS` and the other invisible literals in `bin/compound` written as escapes; a
  test compares the sets with `hooks/safe.ts` and `hooks/render.ts`.
- The harvest's lock test proves the wait from the open lock file and the order of appends.
- `dev/ui-check.sh` recorded once after the mod changes: the reuse result keeps
  "1 owed, 4 candidates from /insights" beside it; the band collapsed (ctrl+x ctrl+a) shows
  "plugin panel hidden", and expanded again redraws the note; both sessions' `remind`
  events carry no `headless`. Nothing drawn wrong.
- CI installs Claude Code with the native installer and runs both plugin checks: in an
  ubuntu:24.04 container (aarch64, non-root, not logged in) both ran and passed.
- The journey's real-store guard no longer requires the real `insights.json` to be absent
  (it exists once a run has happened); it compares size and mtime.

## Measured

- One headless `/insights` on this machine: 47 s, $1.73 at list price, 50 facets and 199
  session-metadata files written, 10 facets with friction, 3 suggested CLAUDE.md additions.
- A harvest of a copy of that output into a temporary store (by the final reviewer): 10
  facet findings and 3 report findings, none skipped, 0.18 s.

## Decisions taken during the build

- Findings stay out of Recent in `compound status`; they are listed under Open.
- The starter releases the lock before it spawns the worker, and the worker waits up to
  30 s for the lock. The design note had the order the other way round, which could lose a
  week's run without a word.
- `--run` and `--harvest` typed by hand run whatever `COMPOUND_OFF` says.
- A state of `running` with a free lock is reported as `interrupted`.
- The reminder's wording is what the code prints; the design note's example was corrected.
- Hook tests answer `process.run` in the test, as every hook test in the repository does:
  the plugin test kit gives a test no process access.
- A facet finding is recorded at the project level only in its own project. A report
  finding is recorded at the user level only.
- A harvest records at most 100 findings, the report's items first.
- With no `claude` on `PATH` the worker tries `~/.local/bin/claude`.
- The worker does not inherit the starting session's id.
