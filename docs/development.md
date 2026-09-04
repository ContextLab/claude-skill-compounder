# Development

Working on this repository rather than using the package.
[`architecture.md`](architecture.md) is what the code does;
[`DESIGN.md`](DESIGN.md) is why it does it that way.

## Running the suite

```bash
./run_tests.sh
```

`run_tests.sh` loops over `tests/test_*.py` and runs each as its own process, so a new file
needs no registration; there are 53 of them (`ls tests/test_*.py | wc -l`).

**A suite green here has gone red on CI twice in one day**, both times because this machine
carries something the runner does not. So run at least the files you touched under a clean
environment before pushing:

```bash
env -i HOME=$(mktemp -d) PATH=/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin \
  PYTHONPATH=$PWD python3 tests/test_doctrine_sync.py
```

That `python3` is `/usr/bin/python3`, which has no PyYAML. The one place that parsed
frontmatter with it unguarded — the description-budget test in `test_doctrine_sync.py` —
now falls back to `scripts/routing_claims.py`'s stdlib parser instead of erroring, which is
the same reader the routing gate reads the description with. The two other `yaml` users,
in `test_contribute.py` and `test_plugin.py`, skip when the wheel is absent; a budget the
routing gate enforces is checked rather than skipped.

No mocks, anywhere: real temporary Claude directories, real `settings.json` files, real
subprocess invocations of the shell scripts, real git repositories built and then
destroyed to prove the destructive-op fixtures, a real virtual environment to prove the
stale-import one, and live `gh` queries against a repo with thousands of pull requests in
every state. The `gh` tests skip cleanly when it is absent or unauthenticated; nothing
else does. `tests/test_install_sh.py` drives `install.sh` itself rather than
`scripts/setup.py`: it builds a tagged bare repository in a temp directory, points the
installer at it with `SKILL_COMPOUNDER_REPO_URL`, and exercises `--ref`, `--update` and
`--rollback` with no network.

The suite never spends a model call. The acceptance journey that does — one pass through
install, note, reminder, capture, forge, route, apply, report and uninstall against a
throwaway Claude config — is a script you run by hand, never in CI:
`python3 tests/e2e/journey.py --out <a fresh dir>`, six `claude -p` calls on your own
subscription, or `--no-model` to rehearse it for nothing. It is the gate a release tag
waits on: [e2e.md](e2e.md).

CI runs the suite on both ubuntu and macos, because macOS ships bash 3.2 and that is
where this repo's shell portability traps actually bite. It also runs
`claude plugin validate --strict`, which is what marketplace review runs.

[CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md) records the verified Claude
Code behavior the implementation depends on, each entry established by running it: skills
hot-reloading mid-session, how far subagent dispatch nests, what a plugin cannot carry,
what the skill loader does with broken frontmatter, and why both install paths would
otherwise double-fire every hook. It is written for anyone building on Claude Code, not
only for this package. [DESIGN.md](DESIGN.md) is the local rationale: why the
forge keys on a name, why the status line rotates, and the shell traps that bite on macOS.

The animation at the top of [`README.md`](../README.md) is a recording, not a live run:
the session chrome is redrawn and
the subagents are not re-run. The progress bar is the real status line, driven by the real
state file. Regenerate it with [`vhs`](https://github.com/charmbracelet/vhs):

```bash
brew install vhs
./dev/generate_media.sh      # runs dev/forge_demo.sh under dev/forge.tape
```

## The rules the suite is written under

Three of them are in `.claude/CLAUDE.md` at length, and each has bitten somebody here:

- **No mocks, ever.** Nondeterminism is pinned with environment variables the scripts read
  for exactly that purpose, and there are fourteen such clocks rather than one — a new
  script needs its own, because pinning someone else's does nothing to it. `.claude/CLAUDE.md`
  names all of them and carries the `grep` that re-derives the list; run it rather than
  trusting the list if the two have drifted.
- **Shell portability traps.** Appending a multibyte glyph needs braces, there is no
  portable way to index a string of them, and bash reads a script lazily by byte offset, so
  editing a script that is running resumes it in the middle of whatever the file now holds.
  [`DESIGN.md`](DESIGN.md) has the details and the reasoning; `tests/test_script_wrapping.py`
  is the ratchet that keeps every shipped script wrapped against the last of those.
- **Both install paths at once.** `install.sh` writes entries into `settings.json` and
  `hooks/hooks.json` makes the same repo loadable as a plugin, so `tests/test_plugin.py`
  asserts the two wire the same scripts to the same events. With both active every hook is
  delivered twice, so anything a hook counts, stamps or does once has to survive being
  handed the same event twice.

Exercising the installer by hand goes against a throwaway config and never your own:

```bash
python3 scripts/setup.py --claude-dir /tmp/fake-claude --bin-dir /tmp/fake-bin --state-dir /tmp/fake-state
python3 scripts/setup.py --uninstall --claude-dir /tmp/fake-claude --bin-dir /tmp/fake-bin --state-dir /tmp/fake-state
```

## Releasing

A tag waits on the suite being green on both operating systems and on the end-to-end
journey passing against a throwaway config. The journey is [e2e.md](e2e.md); the rest of
the procedure, including what to check after the tag is out, is
[releasing.md](releasing.md).

