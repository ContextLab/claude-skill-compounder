# 2026-10-04: Track G, skills that are seen, requests that come back, skills that compose

Work on the three open items of issue #19 as restated in its newest comment, on a worktree
branch off `3ce3c35`. Not pushed, not merged. Every number below came from a command run in
this session. The session logs were scratch files and are not in the repository; the
journeys that produced them are (`tests/journeys/journey_compose.py`, `journey_repeat.py`).

## G1. A skill that is used is seen

**How a skill invocation reaches a function hook.** Found by a scratch plugin that hooked
`skill.prompt`, `tool.call` and `prompt.submit` and four real `claude -p --model haiku`
sessions (Claude Code 2.1.289):

| invocation | `skill.prompt` | `tool.call` | name the engine gives |
|-|-|-|-|
| Skill tool, plugin skill | once | once, `tool: "Skill"` | `probe:say-kelvorn` |
| typed `/probe:say-kelvorn` | once | none | `probe:say-kelvorn` |
| Skill tool, project skill | once | once | `local-word` |
| typed `/local-word` | once | none | `local-word` |

So `skill.prompt` is the one event that covers both, and the use is counted there and not
in the `tool.call` hook (which would miss a typed `/name` and count a Skill call twice). The
plugin still has one unmatched `tool.call` hook, unchanged. The types say a skill preloaded
into a subagent fires the same event; that case was NOT run.

**What was built.**

- CLI: `compound use NAME` resolves the name (a bare name is a project skill, then a user
  skill; `compound:NAME` is a skill of the package), writes a `use` event (`lesson`,
  `level`, `kind`, `path`) and answers `{"used": true|false, ...}`, exit 0 either way.
  `use` is a fifth entry of `counts`, a total (`totals.used`, `N skills used`), a column of
  `list` and of the `status` table, and counts for `show --json`'s `last`.
- Mod: a `skill.prompt` hook that answers `next(e)` at once and counts behind it
  (`void skillUsed(...)`), so a skill's expansion waits for no CLI call. One CLI call,
  `use`, with `BUDGET.call`. A claim (`use-<skill>-<n>`, 20-second windows) keeps two copies
  of the mod to one count. The band shows `▸ skill used · <name> · <level>`, the status
  entry `used <name>`, and the pane has a fourth counter in Most used, the all-lessons
  view, the lesson view and the totals.
- Decided: `compound:learn` and `compound:reuse` are not counted (they are the mod at
  work). `finish-task` and `verify-assumptions-first` are. A skill of another plugin and a
  name the CLI does not list write nothing. `use` is in `MOD_TYPES`, so it counts for "mod
  last fired".
- A second invocation of the same skill within one 20-second window of one session is
  counted once. That is the price of the claim.

**Real sessions** (`journey_compose.py`, step `made`, run 6 times, haiku twice and sonnet 4
times): a lesson made a skill with `compound skill`, invoked through the Skill tool and as
a typed `/deploy-region`: one `use` event each, 12 of 12. The un-awaited call completes
in a `claude -p` process. In the full runs a `use` event was written for `finish-task` and
`verify-assumptions-first` every time they were invoked, and none for `learn` or `reuse`.

## G2. A request that keeps coming back

**Design.** The reuse judge answers a fourth thing, `repeats`: the earlier requests that
asked for the same kind of work (same steps), each with a quote from the request, read by
the same `fromRequest` check as everything else. An earlier request named as covering the
prompt counts as the same kind too. The mod counts SESSIONS (`askedTimes`): those behind
the named rows, plus the ones the memo saw ask this very request, minus the current one,
plus one. At `COMPOUND_REPEAT_MIN` (3; at least 2) with no item named, the note makes the
offer, once per session per kind (`repeat-<digest>` claim, keyed on the oldest row), and a
`repeat` event is written (`times`, `prompts`). Raw word overlap decides nothing: the rows
the judge sees already passed track F's floor (two rare words and a third of their weight),
and the judge then has to name them.

Three things the CLI had to learn for this:

- `find` de-duplicates prompt-log hits by text, so the same words asked in three sessions
  were one row. A row now carries `sessions`.
- A row with the text of the current prompt was dropped as "this session's own". It is now
  kept when the CLI names another session that asked the same words.
- A memo hit skips the prompt-log search, so a request repeated word for word would never
  be counted again for 7 days. The memo now keeps `repeats` and `asked` (the sessions that
  asked the request; `find --request` adds the asking session when it answers from the
  memo).

**The offer does not wait on `substantial`.** First version: only for a substantial build
task. The real judge called "red-team the change, run the full test suite, update the notes
and commit" not substantial (a request to run things), which is the very request the issue
names. Now `parseReuse` reads `repeats` whatever `substantial` says, and the judge prompt
says so.

**Real haiku calls through the real path** (`journey_repeat.py`: a prompt log seeded per
case, a real `claude -p` session, the mod's own `$.model.complete` judge). Seven cases,
three that should be offered and four that should not:

| version | runs per case | right | offered wrongly | missed |
|-|-|-|-|-|
| first prompt wording; the request carried a sentence about "earlier requests" (a fault of the journey) | 3 (one run, then two) | 17 of 21 | 0 | 4: digest 2 of 3, routine 2 of 3 |
| quote rule restated, the journey's sentence replaced | 3 | 16 of 21 | 0 | 5: digest 3 of 3, routine 2 of 3 |
| final: repeats judged apart from `substantial`, "name every one" | 3 | 20 of 21 | 0 | 1: digest 1 of 3 |

Per case, final version: digest 2/3, routine 3/3, report 3/3 offered; topic, twice, covered
and words 0/3 each. Across all 63 case-runs of the three versions no offer was made that
should not have been (0 of 36 runs of the four cases that should get none).

The soft check "the session, asked, says what the note offered" failed whenever the offer
was not made, and once when it was (the session ignored the question).

An isolated look at the judge alone (`claude -p --model haiku` with the mod's prompt, an
approximation, 5 replies per case): digest named both earlier requests 4 of 5, routine all
three 5 of 5, topic and words named none 10 of 10.

**Not regressed, and one thing found.** `measure_reuse.py`, one run each, same day:

| tree | right | wrong | covered, nothing | uncovered, nothing | judge calls |
|-|-|-|-|-|-|
| base `3ce3c35` | 4 | 1 | 0 | 9 | 5 of 14 |
| this branch | 3 | 1 | 1 | 9 | 5 of 14 |

The wrong addition is the same in both: `brew-doctor-exit` beside `latex-undefined-citations`.
Track F's notes say the cut at a third of the best candidate removes it (1.82 against 6.25).
With the six general lessons in the store the weights are 1.79 against 5.24, a third of
which is 1.75, so it is a candidate again and haiku names it. This is on `main` now, not
from this track; it was NOT fixed here (it is track F's threshold, and track H is editing
`bin/compound`). The one miss on this branch is the docker-compose prompt, which track F
recorded as its recurring false negative. One run each: the difference between 4 and 3 is
not evidence.

## G3. Two skills in the pool that compose others

`skills/finish-task` and `skills/verify-assumptions-first`. `verify-assumptions-first`
calls `compound:reuse` first and `compound:finish-task` last; `finish-task` calls
`compound:learn`. So the pool now holds a two-level chain (verify, finish, learn).
None of the four pool skills is a reuse candidate (`OWN_SKILLS` in `bin/compound`, the same
set in `hooks/render.ts`).

**Baseline, without the two skills** (`journey_compose.py --baseline`, sonnet, one run):

- finish: the session fixed the code and ran the tests. It did not run the second check,
  left the README saying what the change made false, and committed nothing ("I haven't
  committed anything").
- verify: the session invoked `compound:reuse` by itself, read the real file first and
  said which assumptions were false, then wrote the whole build in one call. So for this
  model the skill's measurable additions are the order (prove one path, then build out),
  not the reading of the file.

**With the skills** (sonnet; each run is six sessions):

| run | skill text | checks | what failed |
|-|-|-|-|
| 1 | first | 36 of 40 | verify did not call reuse and wrote everything in one call; two faults of the journey's own checks |
| 2 | step 1 and 5 tightened | 38 of 40 | both faults of the journey's checks (a commit read as an edit; a heredoc read as a write) |
| 3 | same | 39 of 40 | a fault of the journey's check (it ran the first script in the call that wrote it) |
| 4 | final | 40 of 40 | none |

What the sessions did, read from the calls: finish-task was invoked 4 of 4 from "Finish the
task"; the test file was never changed; both checks passed at the end; the README was
corrected and the work committed 4 of 4; nothing was pushed. In runs 2 to 4 (where the
prompt forbids reading `check.sh`, so its plain invocation fails) the session invoked
`compound:learn` from the skill's step 6 and recorded a lesson, 3 of 3, with no `capture`
from the mod: the failed call was `./check.sh; echo exit=$?`, which exits 0. In run 1 it
read the script, nothing failed, and it said so and recorded nothing. A question did not
invoke finish-task, 4 of 4.

verify-assumptions-first was invoked 4 of 4 from the large-build prompt and 0 of 4 from the
one-line fix. It called `compound:reuse` 3 of 4 (not in run 1; after the first tightening,
3 of 3, once after another Bash call). It read the real file before writing 4 of 4, said
which assumption was false 4 of 4, built one path and ran it before the rest 3 of 4, and
went on to `compound:finish-task` 4 of 4. It did NOT write its list of assumptions as a
message before checking them in the one run where that was looked for (run 4): step 2 is
followed in substance (each is checked and reported) and not in form.

**haiku sessions, one run (36 of 39 checks):** finish-task: invoked, all 11 of its checks
passed, `compound:learn` invoked. verify-assumptions-first: NOT invoked by haiku for the
large-build prompt. It went straight to building, read the file first, wrote four files
before running any, and its final message was about lessons it recorded and did not say
which assumption was false: the three failed checks. So the routing of
verify-assumptions-first is 4 of 4 on sonnet and 0 of 1 on haiku. The description was not
tuned for haiku.

## Assertions changed on purpose

- `counts` has a fifth key `use`: `tests/test_events.py` (2), `tests/test_review.py`,
  `tests/test_store.py` (2).
- The fourth counter in text output: `tests/test_display.py` (totals dict twice, the totals
  line, the two table headers, one row), `tests/test_status.py` (one row).
- `hooks/knobs.test.ts`: the defaults hold `repeatMin: 3` (2).
- `hooks/judge.test.ts`: the reply shape names `repeats`; three `parseReuse` results carry
  `repeats: []`.
- `hooks/store.test.ts`: a memo carries `repeats` and `asked`.
- `hooks/view.test.ts`: a lesson row and the totals carry `use`/`used`; the totals line has
  `▸ 0 skills used` and wraps at 100 columns (it is asserted whole at 120); the Most used
  legend at 60 columns is glyphs only (four columns with words need 61) and its row is the
  compact one; the legend and rows of the all-lessons view and of the lesson view have the
  fourth counter; the all-lessons row at 60 columns; "nothing was reused, guarded, recalled
  or used yet"; the glyph list of the column test.
- `hooks/ui.test.ts`: the lesson view's counters line and the all-lessons rows.
- `tests/journeys/common.py`: `session()` takes `denied` (default as before).

No test was removed or weakened. New: `tests/test_use.py` (14 tests, all failing on the
base before the CLI change), and 15 hook tests (27 of the hook tests fail when the new and
changed test files are run against the base tree).

## Checks at the end

`./run_tests.sh`: 18 files, 564 tests, OK. `claude plugin validate --strict .`: passed.
`claude plugin test .`: 235 pass, 0 fail. `npx tsc --noEmit -p .`: no `error TS` (the
worktree has no `.claude-plugin/types/`; it was copied from the main checkout, and is
ignored by git).

## Left open, and not verified

- A skill preloaded into a subagent: said by the types to fire `skill.prompt`; not run.
- The band, the pane and the status entry for a used skill and for an offer were checked
  through the mounted hooks (`hooks/ui.test.ts`), not looked at in an interactive session.
  `dev/ui-check.sh` was not run, and the README's screenshots do not show the fourth
  counter.
- The docked pane at widths between 40 and 60 columns: Most used keeps counts and drops
  bars below 38 columns with one-digit counts. Tested by `view.test.ts` at 36 to 140.
- `docs/guide.md`'s `compound status` example was already out of date before this track
  (it shows `Store` and three counters) and was not rewritten; only its Lessons row was
  corrected.
- `.claude/CLAUDE.md`'s table still names two skills. An agent may not edit it.
- G2 on the owner's real prompt log: not run. The earlier requests the judge sees are at
  most five, so the offer needs the same kind of request among the best five hits.
- G2 recall on paraphrases is about two in three for the one paraphrase case (digest).
  Precision: 0 wrong offers in 63 case-runs, on seven hand-made cases.
- The memo's `asked` is written by `find --request`, which makes that read a writer; two
  at once can lose one session id.
- `brew-doctor-exit` offered for the LaTeX prompt of `measure_reuse.py`, on `main` (above).
- `journey_reuse.py` (14 of 14) and `journey_skills.py` (9 of 9) were rerun on the final code,
  haiku. The other journeys were not.
