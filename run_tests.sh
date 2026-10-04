#!/usr/bin/env bash
# Run every tests/test_*.py as its own process; exit non-zero if any fails.
#   PYTHON=/usr/bin/python3 ./run_tests.sh    choose the interpreter
set -u
cd "$(dirname "$0")" || exit 1
python="${PYTHON:-python3}"
failed=0
ran=0
for file in tests/test_*.py; do
  [ -f "$file" ] || continue
  ran=$((ran + 1))
  printf '== %s\n' "$file"
  if ! "$python" "$file"; then
    failed=$((failed + 1))
    printf 'FAILED %s\n' "$file"
  fi
done
if [ "$ran" -eq 0 ]; then
  printf 'no test files found\n'
  exit 1
fi
if [ "$failed" -ne 0 ]; then
  printf 'FAILED: %d of %d test files\n' "$failed" "$ran"
  exit 1
fi
printf 'OK: %d test files\n' "$ran"
