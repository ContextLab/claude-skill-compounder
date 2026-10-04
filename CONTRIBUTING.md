# Contributing

## Proposing a lesson or skill to the general pool

The general pool is `lessons/` and `skills/` in this repository. Everything in it is
installed for every user. From a machine where the lesson already exists at the user
level:

```bash
compound promote <name> --to general        # prints the plan, writes nothing
compound promote <name> --to general --yes  # forks, pushes a branch, opens the pull request
```

Read the plan before adding `--yes`: it prints the files and the pull request text that
will be published.

## Working on the package

```bash
./run_tests.sh                 # CLI suite: stdlib unittest, real files, no mocks
python3 tests/test_store.py    # one file
claude plugin validate --strict .
claude plugin test .           # hooks/*.test.ts: prompt building, parsing, rendering
python3 tests/journeys/journey_guard.py   # one real session; spends model calls
```

To try a checkout without installing it:

```bash
claude --plugin-dir /path/to/claude-skill-compounder
```

To exercise `install` and `uninstall`, point them at throwaway directories and never at
your own configuration:

```bash
T=$(mktemp -d)
bin/compound install --claude-dir "$T/claude" --bin-dir "$T/bin"
```

Rules the code is written under:

- `bin/compound` is the only code that reads or writes lessons, the event log and the
  install. The mod calls it for every store operation.
- Tests use no mocks. The CLI tests run the real CLI against temporary directories. The
  journeys run real Claude Code sessions with `COMPOUND_HOME` and `COMPOUND_PROJECT`
  pointed at temporary directories.
- Documentation describes what the package does now.
