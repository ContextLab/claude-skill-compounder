# tests/e2e — the scenario that spends money

Nothing in here is part of the test suite.

`run_tests.sh` globs `tests/test_*.py`. `journey.py` matches neither that glob nor a
recursive one, and nothing imports it. **That is the entire reason this directory
exists**: a scenario that spends real `claude -p` calls on the operator's subscription
must be impossible to trip over. Do not rename `journey.py` to `test_journey.py`, and do
not add a `test_*.py` file here.

```bash
python3 tests/e2e/journey.py --out /tmp/journey-$(date +%Y%m%d-%H%M%S)   # 13 model calls
python3 tests/e2e/journey.py --out /tmp/dry --no-model                   # free
```

The artifact is `<out>/REPORT.md`, not the exit status.

## The two `--config-dir` modes

`--config-dir ambient`, the default, leaves `HOME` and `CLAUDE_CONFIG_DIR` alone and hands
each session the throwaway configuration through `--settings` with `--setting-sources`,
because a throwaway config directory has no stored login and answers `Not logged in ·
Please run /login`. Three consequences follow and `docs/e2e.md` lists them.

`--config-dir fresh` points `CLAUDE_CONFIG_DIR` at `<out>/claude` for every process,
passes neither flag, and takes the credential from the environment:

```bash
claude setup-token                                        # once; prints a token
export CLAUDE_CODE_OAUTH_TOKEN=...
python3 tests/e2e/journey.py --check-auth --config-dir fresh           # 1 call
python3 tests/e2e/journey.py --out /tmp/fresh --config-dir fresh       # 13 calls
```

Without `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` the run refuses in one line
naming `claude setup-token`, before it builds or spends anything. The token's value is
never logged or written into the report. **No run has been made with a real token yet**
(2026-09-04), so which of the three consequences the mode removes is what it is designed
for rather than what has been seen; `docs/e2e.md` says so at more length, and issue #42
is open on it.

`--check-auth` spends one call, prints the CLI's own answer to a one-word prompt, and
exits 0 or 3. Run it first: the journey is thirteen calls, and none of the other twelve
says anything new about a stale token.

Seventeen steps, numbered 0-16, and they run in the order `STEPS` lists rather than in
number order: 12-16 (the mission hook and the lesson loop) were added after 11 (uninstall)
was numbered, and uninstall has to be last, so the run order is 0-10, 12-16, 11. The
report says so at the top of its summary.

The install this makes also installs **history-surfer**, because `hooks/mission.sh` reads
the user's prompts out of its store and keeps no copy. The installer decides on the
throwaway `settings.json`, not on PATH, so a machine that already has `surfer` gets the
hooks wired from its existing checkout with nothing cloned, and the store lands under
`<out>/claude/history-surfer`, where the mission hook looks by default.

`docs/e2e.md` is the guide: what it costs, what it proves, what it does not, and why the
throwaway config authenticates the way it does.
