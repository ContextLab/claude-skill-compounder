# 2026-10-04, track M: the documentation pass and the re-recorded media

Base `bef6434`. Worktree branch `worktree-agent-ad148588977a2df10`. Nothing was written to
the real store, the real settings or the main checkout: every CLI run was in a throwaway
home (`HOME`, `COMPOUND_HOME`, `COMPOUND_CLAUDE_DIR`, `COMPOUND_PROJECT`), and the timing
runs used a copy of the user lessons as `COMPOUND_HOME`.

## What was stale, and is fixed

README.md

- The `compound status` sample after install: it had no `Compound interest`, `Levels`,
  `Lessons`, `Recent`, `Open` and the short `mod last fired` text. Replaced with what a
  sandboxed install prints now.
- Cost table: said 45 ms for the guard check and "about 1 second; 0.3 to 0.7" for a prompt.
  Re-measured (below).
- Settings: `COMPOUND_REUSE_FLOOR` and `COMPOUND_SHELL` added (both are things a user
  changes); the sentence on what `compound status` reads from `settings.json` now names
  `COMPOUND_SHELL`.
- Troubleshooting: the third `cli` WARN (`compound` not on PATH and no link recorded;
  `bin/compound` 4591) had no row.
- Band table: `nothing to reuse` fades after 3 s, not 8 (`hooks/view.ts`, design's table).
- "How it works": one paragraph for the two things the chart does not draw (the repeat
  offer, a counted skill use).
- `compound update --ref v0.4.0` in the table became `v0.4.1`: the tracker says v0.4.0's
  own `update` fails on a tag.

docs/guide.md

- Every output regenerated from the real CLI (see `dev/guide_examples.py`): `find` (the
  `matched 1 of 2 words (python)` form; the text spoke of a "bracket"), `list` (four
  counters; the text said `USE/GRD/RCL`; four skills, `no-env-edit`), the `disable` row,
  `skip` with two lessons owed, `events --unsettled`, `events --limit 5` (relative times,
  five columns), the whole `compound status` (it showed a `Store` section, three counters
  and absolute times), the `recurring` row, the report.
- The Open rows table named `unsettled` and `skipped`; `status` prints `owed` and
  `declined` (`bin/compound` 4844-4873).
- The event type table lacked `use` and `repeat`.
- The contents lacked "When a request keeps coming back".
- "your own guard" beside a shipped one: only a user-level guard takes a shipped guard's
  place (`bin/compound` 3232-3238); the guide now says so.
- New section "Every command": each subcommand of `compound --help`, and the four the mod
  runs (`check`, `memo`, `use`, `log`), which the guide did not name at all.

docs/design.md, contradictions between sections (the code decides)

1. The CLI table's `check` row said a general guard yields "beside a project or user
   one"; "Two guards on one call" and "What a repository can write" say a user guard only.
   Code: `nearer = any(guarded[index]["level"] == "user" ...)`, `bin/compound` 3234. The
   row is corrected, and now names `timed_out` and `unchecked` too.
2. "What a lesson file is held to" said a lesson that fails any of the four rules is "not
   used: no guard, not listed". For the `match` rule that is false: a pattern that does
   not compile or is too long is dropped and reported, the lesson is still listed and
   recalled and its other patterns are guards (`_load_item`, `bin/compound` 1323-1336;
   `scan` 1526-1535 skips only `_problem`). Checked by writing such a lesson in the
   sandbox: `list` showed it as a guard, `check` hit on its good pattern, `status` FAILed
   `lessons parse`.
3. "Text output of the CLI" said "the three counters"; there are four.
4. "What a lesson is" said `match` is tested "against the text of a tool call"; moment 2
   says Bash commands only unless `match-tools`. Reworded to agree.
5. "takes about 60 ms ... with thirty guards": not what was measured; now the measured
   figure and its store.
6. "The mod acts at five moments" with a sixth subsection under it: the sentence now names
   the skill use.
7. Tests section: `dev/demo.sh` and `dev/guide_examples.py` added.

Checked and found consistent: shadowed lessons ("What a lesson is", "What a repository can
write", the `list` and `show` rows; `scan` 1549-1552), the event type list (18, as
`EVENT_TYPES`), the Words table (pinned by a test), the pane's views and keys against
`hooks/view.ts` 928-938, the health checks against `bin/compound` 4541-4654.

CONTRIBUTING.md: mechanics only. Added `npx tsc`, `dev/demo.sh`, `dev/guide_examples.py`,
and what `tests/test_docs.py` now holds. No policy text was written.

## Re-measured

Machine: Apple M2 Max, macOS 26.6.2, Python 3.9.13, Claude Code 2.1.289. Store: a copy of
the real user lessons plus the project's and the pool's: 48 entries, 40 lessons, 12 with a
`match`. Prompt log: about 16,000 prompts in 1,992 projects. 20 runs each, median (min,
max), wall clock of the process:

| Call | Median | Min | Max |
|-|-|-|-|
| `check --guards`, `ls -la` | 68.2 ms | 65.0 | 116.7 |
| `check --guards`, a 40-line command | 66.5 ms | 64.4 | 71.2 |
| `list --json` | 73.1 ms | 70.5 | 78.4 |
| `find --request --json`, a request with 2 candidates | 501.3 ms | 475.1 | 544.8 |
| `find --request --json`, a request with none | 691.3 ms | 685.9 | 751.8 |
| `events --unsettled --project P --json` | 63.4 ms | 60.8 | 66.7 |

From `compound report` on the real log (read-only; 209 events, 45 sessions, 2026-10-04):
the judge, reuse question, median 762.5 ms, p90 1385 ms (n=36); recall question, median
690 ms, p90 874 ms (n=16); fix question n=9, too small; a prompt where something was
offered, median 1175 ms, of it gathering 267 ms and the judge 866 ms (n=19). The log's
gathering figure is lower than the direct measurement: most of those prompts were before
track F's `find` (which the tracker measured at 667 ms).

## Links

Relative links and anchors: a test now (`LinkTest`). External addresses, each fetched once,
all 200: `github.com/ContextLab/claude-history-surfer` (and `.git`),
`github.com/ContextLab/claude-skill-compounder.git`, `.../issues`,
`raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh`. The
published `install.sh` is byte for byte the worktree's. The README's one-liners were run
as printed in a throwaway `HOME`: install (cloned v0.4.1), `compound update` ("already the
newest release: v0.4.1"), `compound update --ref main` ("updated v0.4.1 -> main"),
piped `uninstall`, piped `uninstall --purge`. All exit 0, and the home was left empty.

## Tests added (`tests/test_docs.py`)

- `LinkTest`: every relative link and anchor in the four documents resolves.
- `GuideTest`: every subcommand of `compound --help` is in the guide's command table and
  no other; every event type is in the guide's table; the guide names the sections and
  the Open rows `status` prints, and none of the gone ones; the guide names the script
  that prints its examples.
- `PoolTest`: the README and the design list every lesson and skill the pool ships; the
  README's status sample has every health row and section, and Troubleshooting a row for
  each check.

## New file

`dev/guide_examples.py`: runs every command the guide and the README show in a throwaway
world and prints the outputs, with the world's paths shown as `/Users/me`. The events a
session would write are written with `compound log`; the report's log is built the same
way with `COMPOUND_NOW` pinned.

## Media, re-recorded

`dev/demo.sh` ran as it stands (vhs 0.11.0, ffmpeg, real `claude --model sonnet` sessions in
`/tmp/cdemo`, the judge on haiku). Seven `learn` takes were recorded; what each logged:

| Take | What happened | Kept |
|-|-|-|
| learn-3 | the second call failed on a zsh glob, the shipped `zsh-no-matches-found` was recalled, and that dropped the held `tomllib` failure: no capture | no |
| learn-4, learn-5 | the fix judge answered `none` twice ("Module unavailable, not a call syntax error"): no capture | no |
| learn-6 | capture and learn, but a plain lesson (`"guard": false`) | no: scene 3 needs a guard |
| learn-7 | capture, then `python-tomllib-needs-312` recorded as a user-level guard (`platform: darwin`) | yes |

`later-7` (one take): the guard refused `python3 - <<'EOF' import tomllib ...` in
billing-svc, the session sent `/opt/homebrew/bin/python3.12 ...` and it worked. The log
holds the `guard` event (`ms` 97, `watched`) and a `retry` event with `same: false`: the
first `retry` a real session wrote.

Files in `docs/media` (old size, new size):

| File | Shows | Old | New |
|-|-|-|-|
| `demo.gif` | three scenes, 99 s at 8 frames a second, 1000 px wide | 5,364,679 (88 s at 10) | 6,064,594 |
| `demo-0-ready.png` (new) | the ready note at the first prompt | | 50,514 |
| `demo-1-capture.png` | `watching for the fix` and the track at `failed` | 248,900 | 103,416 |
| `demo-1-owed.png` (new) | `lesson owed` with the call that worked | | 135,849 |
| `demo-2-recorded.png` | `lesson recorded`, the name, the track ticked, the toast text in the status area | 276,639 | 166,758 |
| `demo-2-pane.png` | the pane in the second session: key hints, health line, Compound interest, Open, Levels, Most used with four counters and one row, Recent | 221,978 | 104,155 |
| `demo-2-lesson.png` (new) | that lesson opened in the pane | | 113,634 |
| `demo-3-guard.png` | the guard's refusal with the quoted note, and the band | 448,603 | 182,298 |

Every still and a contact sheet of the GIF (one frame every 8 s), its lesson-view frame
and its last frame were looked at. No clipped text. No path beyond `/private/tmp/cdemo`,
no address, no token; the banner reads "Sonnet 5.5 · Claude Max", as the old media did.

Changes to the recording scripts: `dev/demo-later.tape` gives the pane the keyboard
(ctrl+x tab), opens the lesson (Enter) and goes back; `dev/demo.sh` writes stills as
palette PNGs (255 colours, a third of the size) and joins at 8 frames a second by default;
`dev/demo.cuts` holds the times of learn-7 and later-7.

Not done: `dev/ui-check.sh` was not run. The README's media does not come from it, and the
demo takes showed every element it is for.

## Seen on the way, for the owner

- **A recalled failure drops an earlier held one** (`hooks/register.ts` 1168-1169,
  `held.delete(key)`). In learn-3 the `tomllib` failure was held, the next call failed for
  another reason that a shipped lesson describes, and the first failure was forgotten: its
  fix was never judged. One slot per agent loop is the design; with six shipped lessons
  the slot is taken more often than before. Not changed here.
- **The fix judge rejects "a module is missing"** about half the time for this demo
  (takes 4 and 5), as "not a call mistake". The README's own example is that case. Either
  the prompt's rule B should name it, or the docs' example should be another mistake.
- **The band was empty for a few seconds while a failure was still held**: in learn-7,
  `watching for the fix` showed at 19.5 s, the `is this the fix?` spinner at 22 s, and at
  24 s (the judge had answered `none`) the row was blank until `lesson owed` at 27 s. The
  design says a result fades after 8 s. Not investigated.
- **The pane's health line reads `1 warning ... claude code` in the screencast**: in the
  demo world `claude` is a shell function and no `claude` is on PATH, so the check cannot
  ask for a version. True of that world. A link to the real `claude` in the world's `bin`
  would make it pass; that needs the takes recorded again.
- **`compound report` prints `no answer 1/37 (2.7%), in time: 0/37`** for a judge event
  whose `reason` is "no reply in 10000 ms" (the guide's example log): which wording counts
  as "ran out of time" is not in the docs. The mod writes `no answer within 10 s`.
- `.claude/CLAUDE.md` still lists two skills (`skills/learn`, `skills/reuse`) and does not
  name `dev/demo.sh` or `dev/guide_examples.py`. An agent may not edit it.
- The live mod, in the parent session, refused one of my Bash calls (`c() {...}`, the
  user guard `zsh-function-name-is-alias`) and recalled `zsh-nomatch-glob` for an unquoted
  `--include=*.py`. Both were right, both were my mistakes, and neither asked for a lesson
  to be recorded or strengthened. Nothing was added to the real store.
- Policy text: none was needed and none was written.
