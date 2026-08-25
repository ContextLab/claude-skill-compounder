#!/usr/bin/env bash
# Run the full test suite (stdlib unittest; real files, real scripts, no mocks).
#
# Each file gets a wall-clock cap. A test that blocks on stdin or on an unbounded
# read has wedged this suite before, and a hang reads as "still running" in CI until
# the job times out with no useful output. A killed file fails loudly instead.
# Override with TEST_TIMEOUT=<seconds>. perl provides the alarm because macOS has no
# `timeout` and GNU coreutils is not a dependency here.
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD"
TEST_TIMEOUT="${TEST_TIMEOUT:-300}"

if command -v perl >/dev/null 2>&1; then
  run_capped() { perl -e 'alarm shift @ARGV; exec @ARGV' "$TEST_TIMEOUT" "$@"; }
else
  echo "WARNING: perl is not installed, so test files run UNCAPPED. A hang will not be" >&2
  echo "         reported as a failure; it will just look like the suite is still going." >&2
  run_capped() { "$@"; }
fi

fail=0
for t in tests/test_*.py; do
  echo "=== $t ==="
  start=$(date +%s)
  # Capture the status directly. `if ! cmd; then rc=$?` records the status of the
  # negation, which is always 0, so the timeout diagnostic below never printed.
  run_capped python3 "$t" -v
  rc=$?
  if [ "$rc" -ne 0 ]; then
    elapsed=$(( $(date +%s) - start ))
    if [ "$rc" -ge 128 ]; then
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
