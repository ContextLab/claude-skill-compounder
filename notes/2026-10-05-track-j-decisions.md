# 2026-10-05 (written 2026-10-04): track J, the settled design decisions

Base `40bd569`. Worktree branch `worktree-agent-a4a700ea4876136a8`. Not pushed, not merged.
The spec is `notes/2026-10-04-decisions.md`. Nothing was written to the real store: every
CLI run that writes used a sandbox (`COMPOUND_HOME`, `COMPOUND_CLAUDE_DIR`,
`COMPOUND_PROJECT`), and the only runs against the real store were `compound check
--guards`, which reads.

Three sets of findings arrived from the coordinator while the track was in progress (a
background security review, titles only). They are at the end, each with what reproduced.

## What was done, by decision

Line numbers are of this branch.

| # | Decision | Where | Done |
|-|-|-|-|
| D1 | no guard yields | `bin/compound` `cmd_check` 3521 (the `yielded` branch is gone); `hooks/render.ts` `guardReason` 637, `GUARD_QUOTED` 629 | yes |
| D2 | a project lesson named like a user or general one is shadowed | unchanged code; pinned by `tests/test_decisions.py` `KeptDecisionsTest`; `docs/design.md` "What a lesson is" now says there is no override | kept, confirmed |
| D3 | a directory that is no slug, or differs from its name, is reported and unused | unchanged code; pinned by the same class; design "A repository cannot stand in for the user" | kept, confirmed |
| D4 | the credential refusal of `promote --to general --yes` has no override | unchanged rule; pinned by the same class; design "What is published is read first" says "No option overrides the refusal" | kept, confirmed |
| D5 | `compound log` takes only the mod's types | `bin/compound` `CLI_WRITES` 481, `cmd_log` 4175; `tests/test_support.py` `seed_event` 56, `Sandbox.seed` 165, `Sandbox.put` 181 | yes |
| D6 | the CLI exemption is narrow | `hooks/render.ts` `soleCliShape` 266, `soleCli` 340; `hooks/register.ts` `ownCall` 220, `bareIsOurs` 206, used at 1602-1604 | yes, and tightened to an allowlist (see the third set of findings) |
| D7 | `macos-gnu-only-commands` is recall-only | `lessons/macos-gnu-only-commands/SKILL.md`, rebuilt by `notes/2026-10-04-audit/general-pool/build_shipped.py` | yes |
| D8 | one recall per lesson, per revision, per session counts | `bin/compound` `counted_recalls` 2082, `recall_verdict` 2136, `cmd_log`; `hooks/register.ts` `written` 639, `recurred` 1136-1195; `hooks/store.ts` `parseLogged` 271 | yes |
| D9 | an identical retry is not a fix | done by the learn-loop fixes; `docs/design.md` moment 4, "The failed call sent again unchanged is not a fix" | confirmed stated |
| - | recurrence by lesson, not by name | `bin/compound` `event_home` 1958, `about` 1980, `tally` 2007 | yes |
| - | one `learn` or `skip` settles one capture | `bin/compound` `settled_by` 2172, `settling` 2247; `hooks/render.ts` `stopDebt` 810, `captureContext` 769; `skills/learn/SKILL.md` steps 2 and 6 | yes |
| - | the promote scan | `bin/compound` `stage_files` 3704, `secret_findings` 3754, `PUBLISH_BYTES` 3701, `cmd_promote` | yes |

### D1

`check` returns every guard in force that matched. One refusal says how many matched and
names them in its first line, quotes the first four in full (each cut at the length one
note always was) and says the others are named above with `compound show <name>`. With one
hit the text is word for word what it was. When a user guard and a general guard both hit,
the last line names `<cli> disable <general name>` and says the choice is the user's. The
mod never read `yielded`; nothing to remove there.

### D5

Refused by `log`, each with the command that writes it: `learn` (`add`), `skip`, `rm`,
`skill`, `promote`, `candidate` (`promote`), `use`. `candidate` and `use` are not in the
spec's list; the event table gives both to a CLI command, so they are refused too.
`seed_event` appends the line itself and raises unless the log is named `events.jsonl`,
lies in a temporary directory after links are followed, and is not under the real
`~/.claude` (found from the password database, not from `HOME`). `dev/guide_examples.py`
uses it for the `report` part's `learn` and `skip` events.

### D6

What existed: `cliCall` exempted a call in which ANY simple command was the CLI, by a
loose match on a program named `compound` or any path ending in `/compound`. The variable
form (`C=/path/compound; $C add ...`) was never exempt: `mentionsCli` only has the log
read afterwards. That is kept as it was, and it is two commands, so it is not exempt.
`cliCall` is kept as the hint that turns the "recording" spinner and has the log read; it
exempts nothing now.

### D7

The pattern is gone and the body's last paragraph, which said a call of `timeout` is
stopped, now says a Mac with Homebrew's coreutils has one. The other five files came out
of the rebuild byte for byte as they were (`git status` showed one file changed).

### D8

`compound log` fills in `counted` and `ineffective` on a `recall` that does not carry
them and prints the event with `--json`; the mod sends neither and reads `ineffective`
from the reply. That is the `log` call a recall made already, so no call was added. The
mod's `since + 1` prediction and its `recurLimit` knob are gone: `COMPOUND_RECUR_LIMIT`
is read by the CLI alone now (the design table says so). A reply that does not read
asks for nothing. A recall with no session counts by itself, as before.

### Recurrence by lesson

A `recall` event now carries the lesson's `level` and `path` (docstring, event table). A
project lesson counts the events of its own project; a user or general lesson counts
every event of its name except one that names a project lesson still at that path, so a
lesson that moved to the user level keeps its history. All five counters go through the
same rule. `compound report` still groups by name: it reads the log and nothing else.

### Settlement

An event with `settles` settles that capture and no other (before, it also settled every
capture of its session). An event without it settles what its session owed, and `add`
and `skip` refuse to write one while the session has more than one unsettled capture of
the last 14 days. `add --update` is held to the same rule.

### Promote

`COMPOUND_UPSTREAM_GIT` is new: a git URL or path the branch is pushed to with git alone.
The task said the tests publish to a local bare repository "as the existing promote tests
do"; the existing tests never completed `--yes` (they drove its refusals against an
upstream that does not exist), so there was no way to test that the staged bytes are the
published bytes without a real path that needs no GitHub. It is in the design's table.

## Assertions changed in existing tests

Each is a deliberate change of behaviour. No test was deleted.

D1 (a general guard is a hit beside a user guard; no `yielded` key):
1. `tests/test_check_find.py` `test_guards_at_all_three_levels_are_tested`: hits gain `("general", "g-guard")`; `assertNotIn("yielded")`.
2. `tests/test_security.py` `GuardsStayOnTest`, four tests: `trusted_hits` is `[user my-guard, general pool-guard]`; one `yielded` equality became `assertNotIn`.
3. `tests/test_security.py` `test_a_general_guard_yields_to_the_users_guard_and_never_to_a_projects`, renamed `..._yields_to_no_guard_a_projects_or_the_users`: the last hits gain the general guard.
4. `tests/test_general_pool.py` `test_the_users_own_guard_wins_over_a_general_one_on_the_same_call`, renamed `...are_both_hits...`: both hit; then `disable` leaves the user's.
5. `tests/test_general_pool.py` `test_a_users_own_lesson_for_the_same_mistake_is_the_one_that_refuses`, renamed `...refuses_beside_the_shipped_one`: `echo =====` hits both.

D7:
6. `tests/test_general_pool.py` `GUARDS`: the `macos-gnu-only-commands` entry is removed; its eight calls it "must stop" are in `GNU_ONLY` with three more and are now asserted to hit nothing (`test_the_gnu_only_lesson_is_recalled_and_stops_no_call`). Its fourteen "must let through" calls are no longer run for that lesson (it has no pattern); five of them are in `ORDINARY` still.
7. `SHIPPED["macos-gnu-only-commands"]` is `lesson`; the general level has 3 guards, not 4.
8. `test_no_shipped_guard_applies_where_its_command_is_right`: bash on macOS is shown by `sed -i`; `timeout 5 make` hits nothing.
9. item 5 above: `timeout -k 5 30 ./run.sh` hits nothing.

D8 (the recalls of a test are now in different sessions; the assertions are unchanged unless said):
10. `tests/test_events.py` `IneffectiveTest.recall`: a session of its own per recall; the after-guard test names its session; its last two recalls are in two sessions.
11. `tests/test_general_pool.py` `PoolCase.recall`: the same; `test_a_general_lesson_is_never_a_strengthening_owed` names its session.
12. `tests/test_reach.py` `test_status_and_the_ineffective_flag_use_the_same_limit`, `test_show_says_how_often_a_lesson_recurred...`; `tests/test_status.py` two tests: the second recall is in a second session.
13. `hooks/knobs.test.ts`, three tests: `recurLimit` is no knob (expected objects lose it; one test now asserts it is absent).
14. `hooks/ui.test.ts`: the world answers `log --json` for a recall with the CLI's verdict (`w.verdict`); four tests set it where they relied on the mod's own arithmetic.

D5:
15. `tests/test_reach.py` `test_every_documented_type_is_accepted`, renamed `..._the_mod_writes_is_accepted_and_no_other`: a type the table gives to the mod is exit 0, one it gives to a command is exit 2 naming the command. Its regular expression missed `candidate` (one space in the table); it now reads all 18 rows.
16. `tests/test_use.py` `test_the_log_takes_a_use_and_a_repeat_event`, renamed `...holds...`: `log` refuses `use`, which is seeded.
17. Moved to the seeding helper with no assertion changed: `tests/test_reach.py` `SameLessonTest.setUp` (`learn`), `tests/test_security.py` `TerminalTest` (`promote`, `candidate`, `skip`), `tests/test_report.py` `ReportCase.ev` (`learn`, `skip` through `Sandbox.put`).

## Timings

`compound check --guards` on the real store, read-only, 20 runs, Apple M2 Max, one Bash
call on stdin: median 60.7 ms before (58.6 to 64.2; 12 guards), 64.6 ms after (62.4 to
68.1; 11 guards, the macOS lesson being none now). The masking rules are compiled when
first used, so `check` does not pay for them (66.5 ms before that was done).

The exemption adds one `sh` process before a tool call, at most once in five minutes, and
only for a call that is otherwise proved to be one bare `compound ...` invocation; budget
`BUDGET.claim`, 2000 ms. A `recall` costs what it did: the `log` that writes it now also
scans the store and reads the log (it runs after the tool call, under `BUDGET.call`). Its
time was not measured separately.

## Checks at the end

`./run_tests.sh`: OK, 22 files (three new: `test_decisions.py` 38 tests, `test_arguments.py`
9, `test_redaction.py` 7). `claude plugin validate --strict .`: passed. `claude plugin
test .`: 280 pass, 0 fail (260 before; `hooks/decisions.test.ts` is new). `npx tsc
--noEmit -p .`: no `error TS`. `python3 dev/guide_examples.py` ran to the end; the README
and the guide were changed where its output differs (3 guards, the macOS row).

Written first and failing before the change: `tests/test_decisions.py` 27 of the 37 it then held failed on
the base (the ten that passed are D2 to D4 and behaviour that is kept);
`tests/test_arguments.py` 5 of 9; `tests/test_redaction.py` 6 of 7.
`hooks/decisions.test.ts` did not load on the base (it imports what did not exist).

## Journeys, run once each for real (haiku)

| Journey | Result |
|-|-|
| `journey_guard.py` | 22 of 22 |
| `journey_general.py` | 33 of 33 (changed for D7: `timeout` is sent, no guard refuses it, and on this Mac, which has no `timeout`, the lesson was recalled) |
| `journey_stop.py` | 12 of 12 |
| `journey_unsettled.py` | 12 of 12 |
| `journey_capture.py` | 10 of 10 |
| `journey_recall.py` | 23 of 23 |

They were run before the last two small changes (the lazy compile of the masking rules
and this file); the four check suites were run again after them.

## Findings sent by the coordinator during the track

### 1. Argument injection in `bin/compound` and `install.sh`

| What | Severity | Reproduced | Fix |
|-|-|-|-|
| `COMPOUND_REF=-f` to `install.sh` | low (the user's own environment) | yes: the install went through, `-f` read by `git checkout --detach` as an option | the ref is held to a pattern before git runs; `--` after it |
| `COMPOUND_REPO=--upload-pack=...` to `install.sh` | low | the option reached `git clone`, which then failed; no command ran | refused when it begins with `-` or names a remote helper; `--` before it |
| `COMPOUND_UPSTREAM=-x/y` | low | yes: accepted as owner/repo, and would have been `gh repo clone -x/y` | `UPSTREAM_RE`: both parts start with a letter, digit (or `_` for the repository) |
| `COMPOUND_UPSTREAM_GIT` beginning with `-` | low; new in this track | yes | `git_source_problem`; `--` before it |
| `COMPOUND_SURFER_URL` beginning with `-` | low | the test was skipped in the run on the unfixed code (a `surfer` was on that PATH), so this one was NOT seen failing first; the code path was the same shape as the one above | `git_source_problem`; `--` before it |
| `update --ref` | low | `-f` was refused already; `a..b`, `x@{1}`, `x.lock` reached git and failed there (exit 1) | `ref_ok`, exit 2 |
| the words of a request to `surfer search` | - | did not reproduce: the pattern is escaped words of letters and digits (a real program in the surfer's place recorded its arguments) | none; the test stays |
| a name beginning with `-` to `show`, `rm`, `skill`, `promote`, `disable`, `use`, `--as` | - | did not reproduce: each is exit 2 or no lesson, nothing written | none; the test stays |
| `claude --version`, the pattern child, `git -C <dir> ls-files` | - | read, not tested: fixed argument vectors, a fork with no exec, a value after `-C` | none |

Not changed: the mod passes a lesson's or skill's name to `compound show NAME --json`
without `--`. A skill directory named like an option reaches the CLI as one; the CLI has
no option that does harm, and the call fails. Left as it is; the pane's tests read the
name at `argv[2]`.

### 2. Sensitive data to the log

Severity medium: the log and the memo are plain files under `~/.claude`, read back into
sessions and printed by `status`, `events` and `report`.

Reproduced, with a bearer header in a curl call, `AWS_SECRET_ACCESS_KEY=...` before a
command, a `https://user:pass@host` URL and a GitHub token: all four reached
`events.jsonl` through `compound log` when the sender had not masked them, the reason of
`compound skip --why` was written and printed unmasked, and the memo kept earlier requests
as the prompt log had them. The mod itself masks what it logs; the CLI did not.

Fixed: `redact` in `bin/compound` (1765) is the mod's rule set, rule for rule (the cases
of `hooks/safe.test.ts` are run through it); `append_event` masks every text of every
event and cuts it at 8000 characters, a list at 200 elements; `write_memo` masks what it
quotes. The fields an event is found by are written as they are. Not done: a line already
in a log is not rewritten, so a secret logged before this change is still there, and
`events --json` prints stored values. The masking is a lower bound, as the mod's is.

### 3. The D6 exemption (five findings; three named)

All were in the first version of the recogniser in this track, which followed the shell's
grammar and allowed what it could not see through. It was replaced, not patched:
`soleCliShape` is an allowlist that fails closed.

| Finding | Severity | Reproduced | Now |
|-|-|-|-|
| redirection to any file (`compound list > ~/.zshrc`, `&>`, `2>&1`) was exempt | medium: an exempt call could write a file unchecked | yes (my own tests asserted `> /tmp/list.json` and `2>&1` exempt) | no redirection but one quoted here-document |
| an unquoted here-document was exempt unless its body held `$(` or a backtick (`${...}`, `$((...))` passed) | medium | yes | only a quoted delimiter |
| `$'...'`, `\;`, an escaped quote in double quotes, a continuation inside a word: read one way here and another by the shell | medium | by reading; each is a table row now | a backslash only between words; no `$'...'`; no backslash in double quotes |
| any path ending in `/compound` was the CLI (`/tmp/x/compound`, `./compound`) | medium | yes | the package's own absolute path, exactly, or the bare name while PATH resolves it to that file |
| `PATH=` behind a quoted assignment (`FOO="a b" PATH=/evil compound`) passed; any assignment was allowed (`LD_PRELOAD=`, a variable naming a program) | medium | yes for the first | only `COMPOUND_PROJECT`, `COMPOUND_HOME`, `COMPOUND_CLAUDE_DIR` |
| variables, globs, braces, `~`, `=cmd`, comments in a word | low | by reading | none is in the allowlist |
| control characters, NUL, very long input | low | by reading | refused |

The last two unnamed findings were not identified from their titles; the four rows after
the first three are what my own review of the diff found. The variable form was never
exempt and is not now. What an exempt call skips is the guards, recall, capture and the
"calls between" list, as before. `hooks/decisions.test.ts` holds 19 exempt shapes and 91
that are not, each also sent through the mounted hook.

## Unverified, and for the owner

- **A lesson unrelated to what is owed.** With two captures unsettled in a session, a
  plain `compound add` is refused, also for a lesson that is about neither, and
  `add --update` for a strengthening needs `--settles` too. The spec asks for exactly
  this. There is no honest id to give for an unrelated lesson; whether that case wants a
  way through is not decided here.
- **Old log lines.** An earlier `learn` or `skip` with `--settles X` from a session that
  owed X and Y settled both; under the new rule Y is owed again if it is younger than 14
  days. `compound events --unsettled` on the real store will show whether any is.
- **`COMPOUND_UPSTREAM_GIT`** is a new name nobody asked for by name (see Promote).
- **The bare name.** `compound` typed bare is exempt while PATH resolves it to the
  package's CLI. An alias or shell function named `compound` cannot be seen from the mod.
  The design says so.
- **The owner's own store, with D1** (not run): `zsh-equals-word`, `zsh-nomatch-glob` and
  `macos-no-timeout` now refuse beside the shipped lessons on the same mistakes. The
  decisions note lists the three `compound disable` commands.
- `compound report` counts recalls by name, not by lesson.
- The live mod in the parent session: it recalled `zsh-equals-word` and
  `zsh-equals-not-found` for two `echo =====` separators of mine (right), its guard
  `zsh-status-path-variables` refused one call whose here-document held Python text with
  `for path in` (not a shell command; sent again), and it recalled
  `macos-gnu-only-commands` for a `cut: Illegal byte sequence` (does not describe it; a
  general lesson, so nothing was owed). No `add` or `skip` was run against the real store.
