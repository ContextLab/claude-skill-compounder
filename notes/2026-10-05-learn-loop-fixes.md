# 2026-10-05 (written 2026-10-04): three fixes in the learn loop

Base `753b8e0` (Release 0.5.0). Worktree branch `worktree-agent-af6e711b2ce5d3cc1`. Not
pushed, not merged. Nothing was written to the real store: every CLI run, journey, probe
and demo take used a throwaway home (`COMPOUND_HOME`, `COMPOUND_CLAUDE_DIR`,
`COMPOUND_PROJECT`). The three bugs are the ones `notes/2026-10-04-track-m-docs-media.md`
lists under "Seen on the way".

## 1. A recalled failure dropped an earlier held one

Root cause: `hooks/register.ts` 1168-1169 on the base, `held.delete(key)` in `onFailure`,
ran for every failure a lesson was recalled for. The key is the agent loop, so it deleted
whatever that loop held, not the failure that was just recalled (which was never held).

Fix (`onFailure`, now `hooks/register.ts` 1195-1204): a recalled failure leaves the held
one held. What "held" means with more than one failure outstanding, now in
`docs/design.md` under moment 3: one failure is held per agent loop; a later failure no
lesson describes takes its place; a later failure a lesson is recalled for takes nothing's
place. One exception: the held call itself, failing again with a lesson now recalled for
it, is let go (the lesson answers it too; holding it would count the lesson's recall twice
at the fix). `FIX_ATTEMPTS` is unchanged: five judged successes of the tool, and a failed
call uses none (tested with seven recalled failures between seven successes: five fix
questions).

## 2. The fix judge and the README's example

Root cause: rule B of `fixPrompt` (`hooks/judge.ts`) defined a call mistake as "HOW the
call was written: a wrong flag, wrong syntax, a missing program, a shell quirk". A missing
module is none of those words, and haiku said so: "Module availability issue, not a call
syntax error", "The failure was legitimate: tomllib doesn't exist in the Python version
being used".

What was reproduced, and what was not. Real haiku calls through the real `fixPrompt` and
`parseFix`, sent with `$.model.complete` exactly as the mod sends them
(`tests/journeys/measure_fix.py` and its one-hook plugin `tests/journeys/fix_probe/`), on
the texts the demo sessions logged (their `capture` events), with the six pool lessons
listed:

- the pair "same script, `tomli` in place of `tomllib`" was rejected on the base prompt in
  clusters: 2, 10, 2, 10, 10, 9 accepted of 10 in six runs (43 of 60);
- the pair "same script under `/opt/homebrew/bin/python3.12`" (the one the task names) was
  accepted 60 of 60 on the base prompt. I could NOT reproduce a rejection of that variant.
  The logs of takes 4 and 5 were not kept, so which variant they sent is not known; the
  reason they logged ("Module unavailable, not a call syntax error") is the reason the
  `tomli` pair gets.

One run of the script is one session, and answers within a run agree far more than answers
across runs (2 of 10 then 10 of 10 on the same prompt). I do not know why. A count from one
run means little; the script's docstring says so.

Fix: rule B now says a call mistake is how the call was written "or what it took for
granted about this machine", names "an interpreter, version or package that lacks what the
call uses", and says `No module named X`, `command not found` and `invalid option` are call
mistakes when the later call does the same job another way. The judge is also given
evidence it did not have:

- **WHAT CHANGED**: the two calls with their shared first and last words left out
  (`changed` in `hooks/judge.ts`): `The failed call had: python3` / `The later call has:
  /opt/homebrew/bin/python3.12`, or "Nothing: the later call is the failed call, word for
  word", or "Everything".
- **CALLS BETWEEN THE TWO**: what the same agent loop ran after the failure and before the
  success, oldest first, `tool: call`, a failed one marked, the newest 8, each one line of
  at most 200 characters, masked (`betweenLine`, `ranBetween` in `hooks/render.ts`; kept on
  the held failure). Read-only and bookkeeping tools and the `compound` CLI are not listed.
  Both sections pass `asData`, and their marks are in `SECTION`.

**The identical retry** (decided with the coordinator): the held call passing unchanged is
not a fix. With nothing run between (`bareRetry`), no model is asked, nothing is owed, no
event is written and the failure is let go. With calls between, the judge is asked with
those calls shown and may say one of them (an install, a setting, a file) is the fix;
whatever it says, the failure is let go once its own call has passed. In `docs/design.md`
under moment 4.

Counts, haiku, every question answered within the 10 s limit (longest 6.2 s; medians 1.3
to 1.7 s). "Before" is the base commit's `hooks/` (`--hooks`), "after" the new prompt.

| Pair | Wanted | Before | After |
|-|-|-|-|
| interpreter (python3 -> python3.12) | FIX | 60 of 60 | 60 of 60 |
| module (tomllib -> tomli) | FIX | 43 of 60 | 60 of 60 |
| program (docker-compose -> docker compose) | FIX | 50 of 50 | 60 of 60 |
| installed (same call, `brew install jq` between) | FIX | 0 of 60 | 60 of 60 |
| shipped (grep -P; the pool's lesson covers it) | KNOWN | 20 of 20 | 20 of 20 |
| unrelated (`ls -la`) | NONE | 9 of 9 | 9 of 9 |
| diagnostic (which interpreters are there) | NONE | 9 of 9 | 9 of 9 |
| other-task (another python job) | NONE | 9 of 9 | 9 of 9 |
| flake (same call, nothing between) | NONE | 9 of 9 | 9 of 9 |
| flake-after (same call, `ls` and `git status` between) | NONE | 9 of 9 | 9 of 9 |
| work-bug (test fails, code edited, test passes) | NONE | 9 of 9 | 9 of 9 |
| search (grep finds nothing, wider grep finds it) | NONE | 9 of 9 | 9 of 9 |
| own-module (script's own import fixed by an edit) | NONE | 6 of 6 | 6 of 6 |

Confusion: before, a fix rejected 77 of 230 (17 `module`, 60 `installed`), a non-fix
accepted 0 of 69; after, a fix rejected 0 of 240, a non-fix accepted 0 of 69. Caveats: the
base prompt is not shown the calls between, so `installed` could not pass there; the first
"after" run (10 of each FIX pair, 3 of each NONE pair) was on a prompt whose WHAT CHANGED
last line was worded "(the N other words are the same in both)", since reworded; the first
"before" run had a `flag` pair (grep -P) that turned out to be KNOWN and was renamed
`shipped`, and no `program` or `own-module` pair.

The judge is still asked after the tool call has run, on the same path as before, with the
same `COMPOUND_JUDGE_TIMEOUT`. The prompt is longer by the new rule text and the two
sections; how much that costs in tokens was not measured.

## 3. The band went blank while a failure was held

Root cause, two places. `unfixed` (`hooks/view.ts` 216-219 on the base) set the track to
`null` when the judge said a success was no fix, though its comment said "the track goes
back to the failure": that is the blank at 24 s in learn-7. And `trackPhase`
(`hooks/view.ts` 275-280 on the base) faded a `failed` track like any result after 8 s.
The band's state had no record of what the hook held, so it could not know better.

Fix: the band's state carries `held`, since when a failure is held
(`types/index.d.ts`). `watch` (`hooks/register.ts` 357) sets and clears it from the hook's
own `held` map wherever that map changes (`watched` in `hooks/view.ts` 226), and `trackOf`
(`hooks/view.ts` 293) draws the track at `failed` while it is set: bold, plain, then dim,
and never gone. The row lets go when the mod does: fix captured (the track is then the
owed lesson's), a recorded lesson answered it, five attempts used, its own call passed
unchanged, the second typed prompt after it, or the module loaded again
(`session.start`). The timer runs only while it brightens or dims: `motion` is `still`
once it is dim (tested: an hour passes with no CLI call and no redraw). `COMPOUND_QUIET`
still hides it (`paint` writes no band state).

Seen in a real session (demo take learn-9, frames every half second): after the judge's
`none` the row reads `watching for the fix ● failed → ...`, then the spinner, then
`lesson owed`. No empty row. Between a spinner ending and its verdict being drawn the row
reads `learn loop ✓ failed → ● fixed` for about half a second, as before.

## Tests

New: `hooks/learn.test.ts` (10 tests through the mounted hooks; on the base commit, with
only this file copied in, 9 fail on an assertion and the `COMPOUND_QUIET` control passes),
and 8 tests of the pure functions in `hooks/judge.test.ts`, `hooks/render.test.ts`,
`hooks/view.test.ts`.

Changed in an existing test: `hooks/render.test.ts`, two `Held` fixtures gained
`between: [], skipped: 0` (the type grew). No assertion was changed, weakened or removed.

## Journeys and the demo, run once each for real

- `journey_capture.py`: 10 of 10.
- `journey_recall.py`: 23 of 23.
- `journey_stop.py`: 12 of 12.
- `dev/demo.sh learn`, twice, in a world of its own (`DEMO_WORLD=/private/tmp/cdemo-fix`,
  takes 8 and 9, both deleted afterwards; `/tmp/cdemo` and the README media untouched):
  captured and recorded both times. Take 8 fixed it with `python3.13` (a plain lesson),
  take 9 with `tomli` (a guard). In both the first success after the failure was a look at
  the interpreters, judged `none`, and the failure stayed held.

## Checks at the end

`./run_tests.sh` OK (19 files); `claude plugin validate --strict .` passed;
`claude plugin test .` 260 pass, 0 fail; `npx tsc --noEmit -p .` no error.

## Unverified, and left open

- A rejection of the interpreter-swap pair was not reproduced (see above).
- Why the judge's answers cluster by run.
- Bug 1 was not seen fixed in a real session: no take hit a recalled failure between the
  failure and its fix. It is covered by the mounted-hook tests only.
- The negative pairs are 6 to 9 questions each: enough to see no gross change, not enough
  to bound a false-accept rate below about one in ten.
- A bare retry writes no event, so `compound report` cannot count them.
- A lesson settled while another failure is still held: the row shows the held failure
  again after the result fades (tested in `view.test.ts`), but `settledBy` still ends the
  track at `recorded` first.
- The live mod in the parent session recalled `zsh-nomatch-glob` twice for my own unquoted
  globs. Both were right. It asked for nothing to be recorded, and nothing was added to
  the real store.
