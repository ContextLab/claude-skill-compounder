# tests/e2e — the scenario that spends money

Nothing in here is part of the test suite.

`run_tests.sh` globs `tests/test_*.py`. `journey.py` matches neither that glob nor a
recursive one, and nothing imports it. **That is the entire reason this directory
exists**: a scenario that spends real `claude -p` calls on the operator's subscription
must be impossible to trip over. Do not rename `journey.py` to `test_journey.py`, and do
not add a `test_*.py` file here.

```bash
python3 tests/e2e/journey.py --out /tmp/journey-$(date +%Y%m%d-%H%M%S)   # ~6 model calls
python3 tests/e2e/journey.py --out /tmp/dry --no-model                   # free
```

The artifact is `<out>/REPORT.md`, not the exit status.

`docs/e2e.md` is the guide: what it costs, what it proves, what it does not, and why the
throwaway config authenticates the way it does.
