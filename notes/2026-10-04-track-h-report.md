# Track H: `compound report`

Date 2026-10-04. Branch `worktree-agent-abcba5c930d395704`, based on `3ce3c35`.
Issue #30 asked for a figure that says whether what the package injects is acted on, one a
script re-derives. The audit (`notes/2026-10-04-audit/audit-quality.md`, section 0) could
not compute the rates: "Not computable (said plainly): capture -> learn vs skip vs
unsettled rates, decline reasons, ineffective-lesson rate, judge timeout rate."

## What was built

`compound report [--since TS] [--until TS] [--project P] [--json]`, read-only, in its own
block of `bin/compound` (`report_window`, `report_learn`, `report_guards`, `report_recall`,
`report_reuse`, `report_judge`, `report_cost`, `build_report`, `cmd_report`; lines
4749-5326 at the time of writing). Sections: Window, The learn loop, Guards, Recall,
Reuse, The judge, Cost to the user, Not measured.

- Every figure is `{n, of, pct}` in JSON and `n/of (pct%)` in text. `pct`, a median and a
  90th percentile (nearest rank) are null under `REPORT_MIN_N = 10`, and the text says
  `n is too small: <n>`. Ten, because one event moves a rate over fewer than ten by more
  than ten points.
- The events counted are the window's; what followed one (the event that settled a
  capture, the `retry` after a refusal, a later recall) is looked for in the whole log.
- An event of a type the report does not read (track G's `use`, anything else) is counted
  under `window.unread` and nowhere else. `tests/test_report.py` appends a `use` line by
  hand and checks that.
- Declines of captures are grouped by the reason up to its first colon, semicolon or full
  stop (`reason_key`). "The lesson does not describe the failure" is recognised by text
  (`WRONG_LESSON_RE`: "does not describe", or "not the failure ... describes"). Both are
  heuristics on free text and the design says so.

## Logging added

One thing the log did not hold: what a session did after a guard refused a call. The
`guard` event carried the refused text and nothing was written for the next call.

- `guard` events now carry `watched: true` (`hooks/register.ts:960`), and the mod keeps the
  refused text per agent loop and tool (`refusedCalls`, `hooks/register.ts:961`).
- The first call of that tool the same loop sends afterwards, a call of the `compound` CLI
  aside, writes one `retry` event: `lessons`, `tool`, `same` (the text is the refused
  call's, `sameCall` in `hooks/render.ts`), `text` (`refusedBefore`,
  `hooks/register.ts:971`).
- It is written after that call has run, or just before that call is itself refused by
  another guard. Nothing is added before a tool call: the pre-call path is still the one
  `check`.
- `retry` is a new event type: `EVENT_TYPES`, `MOD_TYPES`, `EVENT_WORDS` (`retried`),
  `hooks/view.ts` `WORDS`, the design's Words table. Like `judge` it is left out of
  `status`'s Recent and of the pane's timeline, and counted for no lesson.
- A refusal logged without `watched` is reported as `unwatched` and in none of
  changed/same/none. All 6 refusals in today's log are of that kind.

Not added, and why: an event for a reuse check that finds no candidate. Without it the
number of checks made is not in the log (the return at `hooks/register.ts:813` writes
nothing). I wrote it and took it out: `hooks/ui.test.ts:1121-1126` asserts "no model call
and no event" for that case, and track G is editing the reuse path. The report prints
`checks made: not measurable` and `reuse.checks` is null. If the owner wants the figure,
the change is one `judge` event there (I used the verdict `no-candidates` with
`gather_ms`), and that test's last assertion has to change with it.

## A bug the report showed, fixed here

Two recalls in the log (19:09:50Z `background-task-exit-is-last-command`, 19:11:02Z
`chain-commit-with-and`) are for the error "This Bash command contains multiple
operations. The following part requires approval: ...". That is the harness holding a
command for approval, not a failed call; `REFUSALS` had "requires explicit approval" and
not this wording. Added at `hooks/render.ts:89`, tested in `hooks/measure.test.ts` with
the text from the log, named in `docs/design.md` (Recall, "refused before it ran").

Docstring gaps closed while reading it: `guard.ms`, the `capture` fields `evidence`,
`call`, `agent`, `ms`, and the `refuse` fields `debts`, `lessons`, `calls` were written by
the mod and absent from the table at the top of `bin/compound`.

## The real log

Caveat first. The mod has been installed since `2026-10-04T02:50:08Z`, about 17 hours.
Most events come from development sessions on this package: session `09f47a44` (the
session that dispatched the tracks) and its agents, journeys, and scripted review
sessions. 77 of the 80 `learn` events are one bulk migration (session `fee13f20`). The
figures below describe a day of the package being worked on, not a user's use of it.

`COLUMNS=100 bin/compound report`, run from this worktree against `~/.claude/compound`
(read-only) at about 19:59Z:

```
Window
  2026-10-04T02:50:17Z to 2026-10-04T19:55:58Z (oldest 17h, newest 4m)
  194 events in 38 sessions
  A percentage, a median and a 90th percentile are printed for 10 or more; fewer says "n is too
  small". What followed an event is looked for in the whole log.

The learn loop
  captures                 3
  a lesson recorded        1/3 (n is too small: 3)
  declined                 1/3 (n is too small: 3)
    1  one-off exploratory script guessed the shape of ledger batch documents (dicts, n
  still unsettled          1/3 (n is too small: 3)
  expired (over 14 days)   0/3 (n is too small: 3)
  capture to settlement    n is too small: 2
  lessons recorded         79 new, 1 rewritten
  stops refused            debt 1, strengthen 2, nudge 0
  asked after a long turn  0
  reminded of unsettled    2
  moved                    0, 0 candidates left in place

Guards
  refusals                                   6
  then a different call                      0/0 (n is too small: 0)
  then the same call again                   0/0 (n is too small: 0)
  then no call of that tool                  0/0 (n is too small: 0)
  the lesson's failure later in the session  2/6 (n is too small: 6)
  6 refusals carry no `watched` field, so the call that followed was not logged for them.
  lesson                 refused  watched  different  same  none  failed after
  zsh-equals-word              2        0          0     0     0             1
  zsh-nomatch-glob             2        0          0     0     0             1
  chain-commit-with-and        1        0          0     0     0             0
  macos-no-timeout             1        0          0     0     0             0

Recall
  recalls                               24
  after the lesson's guard refused      4/24 (16.7%)
  the same lesson recalled again later  13/24 (54.2%)
  marked ineffective                    12/24 (50.0%)
  stronger lessons owed                 6
    rewritten                                           2/6 (n is too small: 6)
    declined                                            3/6 (n is too small: 6)
    declined: the lesson does not describe the failure  3/6 (n is too small: 6)
    lesson removed or moved                             0/6 (n is too small: 6)
    nothing done                                        1/6 (n is too small: 6)
  lesson                                recalled  after guard  again  ineffective  wrong lesson
  agent-worktree-check-base                    9            0      8            8             2
  zsh-nomatch-glob                             6            1      4            4             1
  zsh-equals-word                              3            3      0            0             0
  zsh-equals-not-found                         2            0      1            0             0
  background-task-exit-is-last-command         1            0      0            0             0
  chain-commit-with-and                        1            0      0            0             0
  ci-poll-in-background                        1            0      0            0             0
  patch-scripts-match-current-text             1            0      0            0             0

Reuse
  checks made: not measurable. A check that finds no candidate writes no event.
  checks with a candidate  29
  put to the judge         29/29 (100.0%)
  answered from the memo   0/29 (0.0%)
  verdicts
    named            13/29 (44.8%)
    nothing          8/29 (27.6%)
    not substantial  8/29 (27.6%)
    unanswered       0/29 (0.0%)
    unreadable       0/29 (0.0%)
  offers made  19, with 21 earlier requests
  item                              offered
  patch-scripts-match-current-text        7
  bin/compound                            3
  shared-tree-no-add-all-no-stash         1
  speckit-execute                         1
  state-no-mocks-in-agent-prompts         1
  zsh-nomatch-glob                        1
  whether an offered item was then used: not measurable from the events this report reads.

The judge
  model calls        52
  latency            median 798 ms, p90 1749 ms (n=52)
  no answer          0/52 (0.0%), in time: 0/52 (0.0%)
  unreadable answer  0/52 (0.0%)
  reuse   29  median 800 ms, p90 2574 ms (n=29)
    named            13/29 (44.8%)
    nothing          8/29 (27.6%)
    not substantial  8/29 (27.6%)
    unanswered       0/29 (0.0%)
    unreadable       0/29 (0.0%)
  recall  14  median 690 ms, p90 839 ms (n=14)
    named       10/14 (71.4%)
    none        4/14 (28.6%)
    unanswered  0/14 (0.0%)
    unreadable  0/14 (0.0%)
  fix      9  n is too small: 9
    fix         2/9 (n is too small: 9)
    known       0/9 (n is too small: 9)
    none        7/9 (n is too small: 9)
    unanswered  0/9 (n is too small: 9)
    unreadable  0/9 (n is too small: 9)

Cost to the user
  at a prompt, something offered  median 1175 ms, p90 1581 ms (n=19)
    of it gathering               median 267 ms, p90 324 ms (n=19)
    of it the judge               median 866 ms, p90 1340 ms (n=19)
  at a prompt, the judge alone    median 800 ms, p90 2574 ms (n=29)
  a refused call's check          n is too small: 6
  after a failed call, the judge  median 690 ms, p90 839 ms (n=14)
  after a fix, the judge          n is too small: 9
  errors                          0

Not measured
  time or tokens saved: no duration of a failed call or of its fix is logged
  whether an offered item was then used: no event this report reads says that an offered lesson,
  skill, script or earlier request was opened or run
  what followed a refusal whose `guard` event carries no `watched` field: the next call of that tool
  was not logged for it
  how many reuse checks were made: a check that finds no candidate writes no event, so only the
  checks that reached the judge or the memo are counted
  the time a reuse check took when the judge named nothing: only the judge's `ms` is logged for it
```

## What it shows

Each point quotes the log. I read the events with a scratch script, not from memory.

1. **Half the recalls were marked ineffective, and at least half of those debts were the
   wrong lesson.** 12/24 recalls carry `ineffective: true`. They make 6 debts (one per
   session and settling event); 3/6 were declined with a reason that says the lesson does
   not describe the failure, 2/6 ended in a rewrite, 1/6 is open. Six is too small for a
   rate. The skips, word for word: "the recalled lesson does not describe this failure:
   wc -l was given a glob that matched a directory ..."; "the recalled lesson does not
   describe this failure: the failing call was a track agent's inline Python patch of a
   test file inside its worktree, not a worktree based on the wrong commit ..."; "Not the
   failure agent-worktree-check-base describes: the worktree base was right. The harness
   refused a long 'cd && python3 heredoc' command ...".
2. **`agent-worktree-check-base` was recalled 9 times, 8 marked ineffective, all for one
   harness refusal.** Every one of the nine has the error "This agent is isolated in the
   worktree ...", between 17:29:12Z and 17:42:12Z. That wording is in `REFUSALS` now
   (`hooks/render.ts:90`), so a mod at this commit would not judge those calls at all. I
   did not check which commit the running mod was at when they were logged.
3. **A second harness wording was still being recalled** (fixed above, `hooks/render.ts:89`).
4. **A lesson became "ineffective" from two agents failing one second apart.**
   `zsh-nomatch-glob`: 17:28:26Z `ineffective: false`, 17:28:27Z `ineffective: true`, same
   session `09f47a44`, two different calls whose outputs name two different worktrees
   (`worktree-agent-ab04c55fbee53eabd`, `worktree-agent-a0198f33ca9da0709`). Two subagents
   started at once, each ran its first command, each failed. Neither had seen the lesson
   before its call, so the lesson did not fail to prevent anything, yet the limit of 2
   (`recalls_since`, `bin/compound:1802`; `recurred`, `hooks/register.ts`) was reached and
   a stop was refused for it ("refuse ... strengthen ... zsh-nomatch-glob", 17:28:28Z).
   Recurrences are counted per lesson across agent loops and sessions with no regard to
   whether the failing loop had been given the lesson. Not fixed here: it is a change to
   what "ineffective" means, and both skips say the lesson was the wrong one anyway.
5. **The recall judge names a lesson for most failures it is asked about**: named 10/14
   (71.4%), none 4/14 (28.6%). Read beside point 1, that is consistent with the audit's
   finding that it names a lesson where none applies. `judge` events of the recall
   question exist only from 18:03Z on; the 14 earlier recalls have none.
6. **Guards: nothing can be said about corrected against overridden yet.** 6 refusals, 0
   watched. What the log does hold: for 2/6 the lesson was recalled beside a failure later
   in the same session (`zsh-equals-word` 17:02:15Z then 17:02:26Z; `zsh-nomatch-glob`
   18:50:26Z then 18:51:05Z). The first of those was a deliberate reproduction (audit, B3).
7. **Reuse: 13/29 (44.8%) of the checks that had a candidate named something.** 19 `reuse`
   events against 13 `named` verdicts: 6 offers are older than the `judge` event. One
   lesson, `patch-scripts-match-current-text`, is 7 of the 19 offers, in 7 different
   sessions with 7 different `prompt_id`s. The audit read the first of them as not
   relevant; I did not read the prompts of the others. No check was answered from the
   memo (0/29). Whether anything offered was used is not in the log.
8. **Latency.** The judge: median 798 ms, p90 1749 ms over 52 calls, no timeouts, no
   unreadable answers. A reuse check that offered something added a median of 1175 ms to
   the prompt (p90 1581 ms, n=19), 267 ms of it gathering. The reuse judge's slowest calls
   are 2574, 3129 and 3144 ms. Zero `error` events in the log.
9. **The learn loop has 3 captures.** One recorded, one declined, one unsettled. The
   unsettled one is from this track: a typo in a scratch script of mine failed and its
   corrected run was captured by the live mod in session `09f47a44`. I was told not to
   write to the real store, so I neither recorded nor declined it. It is a one-off and can
   be declined.

## Tests

`tests/test_report.py`: 26 tests, real logs built with `compound log`, `add --settles`,
`add --update` and `skip` in a sandbox: the empty log, each section with the JSON asserted
exactly and the key text lines, a log with unparseable lines, events with missing fields,
a `use` event, control characters, the window options, the width, and that the command
writes nothing. `hooks/measure.test.ts`: 7 tests, the `retry` event through the mod's
hooks (a different call, the same call, a CLI call or another tool in between, a call
refused by a second guard), the pane leaving it out, and the new refusal wording.

At the end: `./run_tests.sh` 18 files OK; `claude plugin test .` 224 pass, 0 fail;
`claude plugin validate --strict .` passed; `npx tsc --noEmit -p .` no output. The
worktree had no `.claude-plugin/types/` (the engine lays it beside a loaded mod and git
ignores it), so `tsc` could not run until I copied that directory from the main checkout.

## Not verified

- No real session has written a `retry` event: the hook path is tested through
  `claude plugin test`, not through a journey. `tests/journeys/journey_guard.py` would
  show one and I did not run it (it spends model calls).
- Merge with track G: both tracks add an event type to the same tuples and tables in
  `bin/compound`, `hooks/view.ts` and `docs/design.md`.
