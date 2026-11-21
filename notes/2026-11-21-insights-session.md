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

## Open

1. `tests/journeys/journey_insights.py` has never been run for real (dry run only: 9 of 9).
   It needs an API key in the environment; the agent's read of the keychain item was
   refused, so the user runs it. Until it runs, nothing has exercised a real session's
   first prompt starting a run, the child's environment, or the freshness check on
   `report.html`. The 900 s timeout kill has no test at all.
2. The merge of b271942 into `main`, and the push, wait for the user.
3. Parked: headless `claude -p` sessions count toward a finding's three showings.
4. Noted, not changed: the mod ignores `isCollapsed`, so the band's timer runs while the
   band is collapsed.

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
