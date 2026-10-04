# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

compound: a Claude Code mod plus a CLI. The repository root is the plugin. Read
`docs/design.md` before changing anything; it is the contract both halves are built to.

| Path | What |
|-|-|
| `.claude-plugin/plugin.json`, `hooks/hooks.json` | the plugin manifest and the hooks module's name |
| `hooks/register.ts` | every hook; the only file that touches the engine interface `$` |
| `hooks/judge.ts`, `render.ts`, `store.ts`, `knobs.ts`, `safe.ts`, `view.ts` | pure logic, each with a `*.test.ts`; `view.ts` is what the band and the `/compound` pane show |
| `hooks/ui.test.ts` | the band and the pane mounted through the hooks on the terminal and desktop surfaces |
| `types/index.d.ts` | the contract for the values the mod keeps in `$.state`; `plugin.json` names it |
| `bin/compound` | the CLI: one Python file, standard library only, runs on Python 3.9 |
| `skills/learn`, `skills/reuse` | the two procedures the mod sends Claude to |
| `lessons/`, `skills/` | the general pool shipped to every user |
| `tests/test_*.py` | CLI tests |
| `tests/journeys/` | real-session drivers, run by hand |
| `dev/ui-check.sh`, `dev/ui-check.tape` | a recorded interactive session (vhs) with a screenshot of each phase, for looking at the band and the pane |

## Commands

```bash
./run_tests.sh
claude plugin validate --strict .
claude plugin test .
python3 tests/journeys/journey_<name>.py
```

## Rules

- One implementation of each thing. The mod never reads or writes a lesson file or the
  event log; it calls `bin/compound`. Event field names are defined once, in the
  docstring at the top of `bin/compound`.
- No mocks. A test writes real files and runs the real CLI. A journey runs a real
  session.
- Never run `bin/compound install`, `uninstall` or `update` against the real `~/.claude`
  while developing. Pass `--claude-dir` and `--bin-dir`, or set `COMPOUND_HOME` and
  `COMPOUND_CLAUDE_DIR`.
- A hook must never break a turn: every failure is caught, logged as an `error` event
  and reported, and the turn goes on.
- The function-hook API allows a plugin one unmatched `tool.call` hook, requires literal
  names in `$.env.get`, and keeps a module's variables for the life of the process, so
  per-session state is keyed on the session id.
- A render hook draws from `$.state` and answers `next(e)` on any failure. The band's one
  timer runs only while a spinner turns or a result fades. The pane's CLI reads are never
  made on a path a tool call waits on.
- A Bash call is exempt from the guards, recall and capture only when `soleCliShape` in
  `hooks/render.ts` proves it is one simple `compound ...` invocation. It is an allowlist
  and fails closed: add to it only what can be proved, with a case in
  `hooks/decisions.test.ts` in each direction.
- Whether a recall counts toward ineffective is decided in the CLI (`recall_verdict`), when
  `compound log` writes the event. The mod reads the reply and predicts nothing.
- `compound log` takes only the types the mod writes. A test that needs an event a command
  writes uses `seed_event` in `tests/test_support.py`, which refuses a store that is not
  in a temporary directory.
- Before a tool call the mod makes one CLI call, `check`, and no listing. Every CLI call
  the mod makes takes its budget from `BUDGET` in `hooks/render.ts`: 2 s at most while a
  tool call or a stop waits, 5 s at most at a typed prompt.
- What the user is told about a `compound` command the session ran follows the event the
  command wrote, never the command's text.
- Documentation describes what the package does now, for a reader who has never seen it.
  A new `COMPOUND_*` name, subcommand, option or claim kind goes into `docs/design.md` in
  the same change; `tests/test_docs.py` fails otherwise.
- `notes/` holds dated session notes. It is a log, not a description of behaviour.
