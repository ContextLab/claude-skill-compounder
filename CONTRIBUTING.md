# Contributing

There are two ways to contribute: propose a lesson you recorded, or work on the package.

## Proposing a lesson or skill to the general pool

The general pool is `lessons/` and `skills/` in this repository. Everything in it is
installed for every user. You propose a lesson from a machine where it already exists at
the user level. If it is still a project lesson, move it first with `compound promote
<name> --to user`. Then:

```bash
compound promote <name> --to general        # prints the plan, writes nothing
compound promote <name> --to general --yes  # forks, pushes a branch, opens the pull request
```

Read the plan before adding `--yes`: it prints the files and the pull request text that
will be published. The [user guide](docs/guide.md#propose-a-lesson-to-the-general-pool)
shows a plan.

## Working on the package

You need Claude Code, `python3` (3.9 or later) and `git`. Clone the repository and run
these from its root:

```bash
./run_tests.sh                 # CLI suite: stdlib unittest, real files, no mocks
python3 tests/test_store.py    # one file
claude plugin validate --strict .
claude plugin test .           # hooks/*.test.ts: prompt building, parsing, rendering, the band and the pane
python3 tests/journeys/journey_guard.py   # real sessions; spends model calls
```

The journeys are in `tests/journeys/`. Each runs real `claude -p` sessions against a
throwaway store, prints one PASS or FAIL line per check and exits non-zero when one
fails. They spend model calls, so they are run by hand and never by `run_tests.sh`.
`--model` names the session's model and `--keep` keeps the throwaway directory.

| Script | What it drives |
|-|-|
| `journey_reuse.py` | Moment 1: a substantial prompt is given the existing work and earlier requests that cover it, a prompt nothing covers is given nothing, and the first prompt sent again in a new session is given the same from the memo, with no model asked. |
| `journey_guard.py` | Moment 2: a call matching a guard is refused once and runs when sent again; a slow `check`, or a slow `list` and `events`, costs the turn one budget each and one `error` each. |
| `journey_recall.py` | Moment 3: a failed call is given its recorded lesson, and a lesson met in a second project is moved to the user level or left in place when git tracks it. |
| `journey_capture.py` | Moments 4 and 5: a fix after a failure makes the session owe a lesson, and the stop is refused until it is recorded. |
| `journey_stop.py` | Moment 5: an owed lesson refuses one stop, declining it settles it, and a long turn is asked once whether it learned anything. |
| `journey_strengthen.py` | A lesson recalled after its failure came back is marked ineffective, and the session must strengthen it or decline before it stops. |
| `journey_unsettled.py` | A capture an earlier session left unsettled is raised at the next session's first prompt and settled by its id. |
| `journey_claims.py` | With a claims directory that cannot be made, the mod refuses nothing and logs one `error`. |
| `journey_error.py` | A failure of the mod itself is logged, reported at the next prompt, each failure once; `COMPOUND_OFF=1` writes nothing. |
| `journey_general.py` | The lessons the package ships, on macOS with zsh: each shipped guard refuses its wrong form once, the recall lessons are given to their failures, a general lesson recalled past the limit raises no debt, and a disabled or not-applying lesson does nothing. |
| `journey_skills.py` | The plugin's surface in a headless session: the `compound:learn` and `compound:reuse` skills and the `/compound` command are listed, and `compound:learn`, invoked through the Skill tool, writes a lesson. |
| `journey_compose.py` | The two shipped skills that call other skills, on small real projects: `finish-task` fixes a failing change without touching the test, runs every check, updates the stale README and commits without pushing; `verify-assumptions-first` calls `compound:reuse`, reads the real input before it writes and says which stated assumption was false. Neither is invoked for a question or a one-line fix. A lesson made a skill is counted (`use`) when it is invoked through the Skill tool and as a typed `/name`. `--baseline` runs the two projects without the two skills. Its default model is `sonnet`. |
| `journey_repeat.py` | A request that keeps coming back: seven cases, each with a prompt log of its own. Three kinds of request made in three or more sessions are offered a skill (a `repeat` event); a shared topic, a request made in one other session, a request a recorded lesson covers and two requests that share rare words are not. `--runs N` repeats every case and prints the counts. |

Two more scripts there measure and assert nothing:

| Script | What it measures |
|-|-|
| `measure_reuse.py` | How noisy the reuse check is: over fourteen ordinary prompts, how many got something added, how many of those additions were relevant, how many covered prompts got nothing, how many prompts were put to the judge at all and how long it took; and that a prompt sent a second time asks no model. |
| `probe_injection.py` | What a session does with a planted lesson whose text gives orders, met as a guard, as a recalled lesson and in the reuse check: whether the quoted note is weighed or obeyed. |

`common.py` is what they share: the throwaway world, the session runner and the checks.

To try a checkout without installing it:

```bash
claude --plugin-dir /path/to/claude-skill-compounder
```

To look at the band and the `/compound` pane as a person sees them:

```bash
dev/ui-check.sh    # needs vhs; spends model calls
```

It records a real interactive session in a throwaway store and project and writes a
screenshot of each phase to `$TMPDIR/compound-ui-check/shots`. Open the PNGs and look:
the session's own pace decides which frame catches which phase. The header of
`dev/ui-check.tape` says what it takes to get an interactive session running under vhs.

To exercise `install` and `uninstall`, point them at throwaway directories and never at
your own configuration:

```bash
T=$(mktemp -d)
bin/compound install --claude-dir "$T/claude" --bin-dir "$T/bin"
```

## The documentation

| Page | For | Holds |
|-|-|-|
| `README.md` | a new user | what compound does, install, how to see it working, the common commands |
| `docs/guide.md` | a user who wants to step in | each manual command with its real output |
| `docs/design.md` | a contributor | the technical contract: every command, option, event and environment variable |

Every command shown in the documentation runs as written, and every output shown is real
output, shortened only with `...`. To get real output without touching your own
configuration, run the CLI in a throwaway home directory:

```bash
export HOME=$(mktemp -d) COMPOUND_NO_SURFER=1
```

The two diagrams in `README.md` are Mermaid. After changing one, render it and look at
it in a light and a dark theme:

```bash
npx -y @mermaid-js/mermaid-cli -i diagram.mmd -o diagram.png
npx -y @mermaid-js/mermaid-cli -i diagram.mmd -o diagram-dark.png -t dark -b '#0d1117'
```

## Rules the code is written under

- `bin/compound` is the only code that reads or writes lessons, the event log and the
  install. The mod calls it for every store operation.
- Tests use no mocks. The CLI tests run the real CLI against temporary directories. The
  journeys run real Claude Code sessions with `COMPOUND_HOME` and `COMPOUND_PROJECT`
  pointed at temporary directories.
- Documentation describes what the package does now, for a reader who is new to it.
  `tests/test_docs.py` fails when `docs/design.md` lacks a `COMPOUND_*` name, a
  subcommand, an option or a claim kind that the code has, when this file lacks a journey
  script, and when `README.md` uses one of its terms before defining it.
