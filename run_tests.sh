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

run_capped() {
  if command -v perl >/dev/null 2>&1; then
    perl -e 'alarm shift @ARGV; exec @ARGV' "$TEST_TIMEOUT" "$@"
  else
    "$@"
  fi
}

fail=0
for t in tests/test_*.py; do
  echo "=== $t ==="
  start=$(date +%s)
  if ! run_capped python3 "$t" -v; then
    rc=$?
    elapsed=$(( $(date +%s) - start ))
    if [ "$rc" -ge 128 ]; then
      echo "!!! $t was killed after ${elapsed}s (cap ${TEST_TIMEOUT}s). Treat a hang as a failure."
    fi
    fail=1
  fi
done
if [ "$fail" -ne 0 ]; then
  echo "SOME TESTS FAILED"
  exit 1
fi
echo "ALL TESTS PASSED"
