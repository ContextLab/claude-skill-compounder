# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

compound: a Claude Code mod plus a CLI. The repository root is the plugin. Read
`docs/design.md` before changing anything; it is the contract both halves are built to.

| Path | What |
|-|-|
| `.claude-plugin/plugin.json`, `hooks/hooks.json` | the plugin manifest and the hooks module's name |
| `hooks/register.ts` | every hook; the only file that touches the engine interface `$` |
| `hooks/judge.ts`, `render.ts`, `store.ts`, `knobs.ts`, `safe.ts` | pure logic, each with a `*.test.ts` |
| `bin/compound` | the CLI: one Python file, standard library only, runs on Python 3.9 |
| `skills/learn`, `skills/reuse` | the two procedures the mod sends Claude to |
| `lessons/`, `skills/` | the general pool shipped to every user |
| `tests/test_*.py` | CLI tests |
| `tests/journeys/` | real-session drivers, run by hand |

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
- Documentation describes what the package does now, for a reader who has never seen it.
- `notes/` holds dated session notes. It is a log, not a description of behaviour.
