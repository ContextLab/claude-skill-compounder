# Third review: ten reproduced defects (2026-10-03, night; uncommitted when written)

Session notes, a log and not a description of behaviour. `docs/design.md` is the contract.

## What was fixed, test or journey first

1. Slow CLI. `guard()` made a listing (15 s budget) before the 1.5 s `check`. Now the
   pre-call path makes one call, `check --guards`, whose reply counts the lessons with a
   `match`; zero means no call at all until the next typed prompt or a store-changing CLI
   call. Budgets are `BUDGET` in `hooks/render.ts` (check 1500, call 2000, claim 2000,
   prompt 5000, command 15000). A subcommand that timed out is `stalled` for the turn.
   CLI failures are logged once per session per subcommand and message.
   Journey: `journey_guard.py`, step `stall` (130.7 s and 8 errors before; see the run).
2. One name in two projects. Identical trees are one lesson (`same_tree`): the untracked
   copy moves, other untracked copies are removed (`merged`), tracked ones stay (`also`),
   `scan` lists a project copy identical to the user lesson once, `status` says "also
   committed in". A differing text is refused with the exact `--as NEWNAME` command, and
   an automatic refusal logs a `candidate`. Tests: `SameLessonTest`, `NamesTest`.
3. `setting()` in `bin/compound`: process environment, then `env` in settings.json, then
   default, for `COMPOUND_RECUR_LIMIT` and `COMPOUND_OFF`. Tests: `KnobTest`.
4. and 5. `storeNews` in `hooks/render.ts`: toasts and status entries follow the events a
   session's own CLI call wrote (`events --session S --since T`), so a plan raises
   nothing; `skill` and `rm` are reported; the four `.catch` handlers set the status entry.
6. `plugin_problem` follows relative imports. 7. the unsettled line is a command pair.
8. uninstall names the clone it keeps; `--purge` removes it. 9. README fallback path.
10. Docs: `tests/test_docs.py` holds `docs/design.md` to the code.

Also fixed on the way: `compound --help | head -1` printed "Exception ignored ...
BrokenPipeError" (`run()` at the bottom of `bin/compound`).

## Chosen differently from the brief

- The "is there any guard" cache is refreshed at every typed prompt as well as after a
  store-changing CLI call, so a guard recorded by another session takes effect at the
  next turn. Cost: one `check` per turn when no lesson has a pattern.
- `check` output is unchanged without `--guards`; the count is opt-in, so the existing
  tests of its exact output stand.
- Judge-model failures are still logged per occurrence (`journey_error.py` step `again`
  requires the second one); only CLI failures are once per session.

## Open

- Toasts and status entries cannot be seen in `claude -p`. They are covered by
  `hooks/render.test.ts` (`storeNews`) and by `journey_skills.py` step `commands`, which
  shows the follow-up read of the log runs clean. Check them in an interactive session.
- `parseLeft` in `hooks/store.ts` is no longer imported by `register.ts` (`parseMoved`
  replaced it); it is kept with its tests.
