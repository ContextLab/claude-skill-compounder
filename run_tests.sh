#!/usr/bin/env bash
# Run the full test suite (stdlib unittest; real files, real scripts, no mocks).
#
# Each file runs under a wall-clock cap in its own process group, and a timeout kills
# the whole group. A test that blocks on stdin or on an unbounded read has wedged this
# suite before, and killing only the direct child is not enough: a surviving grandchild
# keeps the inherited stdout pipe open, so `./run_tests.sh | tail` blocks for the full
# hang even after the runner has exited. GitHub Actions reads stdout through a pipe, so
# that is exactly the job hang the cap exists to prevent.
#
# Override the cap with TEST_TIMEOUT=<seconds>.
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD"
# Importing a module under skills/ writes a __pycache__ beside it, and a seed skill
# asserts its own directory ships no build artifacts. Without this the guard fails
# depending on whether anything imported the module first, which is flakiness, not a
# finding.
export PYTHONDONTWRITEBYTECODE=1
TEST_TIMEOUT="${TEST_TIMEOUT:-300}"

fail=0
for t in tests/test_*.py; do
  echo "=== $t ==="
  start=$(date +%s)
  # Capture the status directly. `if ! cmd; then rc=$?` records the status of the
  # negation, which is always 0, so the diagnostic below would never print.
  python3 - "$TEST_TIMEOUT" python3 "$t" -v <<'RUNNER'
import os, signal, subprocess, sys, time

timeout = float(sys.argv[1])
argv = sys.argv[2:]
# start_new_session puts the child and everything it spawns in one process group, so
# the kill below reaches grandchildren too.
proc = subprocess.Popen(argv, start_new_session=True)
try:
    sys.exit(proc.wait(timeout=timeout))
except subprocess.TimeoutExpired:
    pass

for sig in (signal.SIGTERM, signal.SIGKILL):
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        break
    deadline = time.time() + 5
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    else:
        continue
    break
proc.wait()
sys.exit(142)
RUNNER
  rc=$?
  if [ "$rc" -ne 0 ]; then
    elapsed=$(( $(date +%s) - start ))
    if [ "$rc" -eq 142 ]; then
      echo "!!! $t was killed after ${elapsed}s (cap ${TEST_TIMEOUT}s). A hang is a failure."
    fi
    fail=1
  fi
done
if [ "$fail" -ne 0 ]; then
  echo "SOME TESTS FAILED"
  exit 1
fi
echo "ALL TESTS PASSED"
