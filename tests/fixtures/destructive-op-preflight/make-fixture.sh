#!/usr/bin/env bash
# Build a real git repo in the exact state that burned anthropics/claude-code #34746 and
# #34327: a bare origin, one unpushed commit, a staged mutation, an unstaged mutation, an
# untracked file with no object behind it, and an ignored file holding a secret.
#
# Usage: make-fixture.sh <target-dir>
# Creates <target-dir>/origin.git (bare) and <target-dir>/repo (the working clone).
# No ambient git config is required; identity is passed per invocation.
set -euo pipefail

target="${1:?usage: make-fixture.sh <target-dir>}"
mkdir -p "$target"
target="$(cd "$target" && pwd)"

g() {
  git -c user.email=fixture@example.invalid \
      -c user.name=fixture \
      -c init.defaultBranch=main \
      -c commit.gpgsign=false \
      -c protocol.file.allow=always \
      "$@"
}

g init -q --bare "$target/origin.git"
g clone -q "$target/origin.git" "$target/repo" 2>/dev/null
cd "$target/repo"

# --- the baseline that origin knows about ---
mkdir -p src
echo 'print("app v1")' > src/app.py
echo '# project' > README.md
printf 'build/\n' > .gitignore
g add -A
g commit -qm 'base'
g push -q origin main

# --- one commit that exists only here (reflog-recoverable, until gc) ---
echo 'def feature(): return 1' > src/feature.py
g add src/feature.py
g commit -qm 'feature'

# --- a staged mutation (blob written, no commit) ---
echo 'print("app v2")' > src/app.py
g add src/app.py

# --- an unstaged mutation (no object anywhere) ---
echo '## edited section' >> README.md

# --- the file that dies: untracked, never added, no git object ---
printf 'PRECIOUS PLAN: do not lose this\n' > NOTES-DO-NOT-LOSE.md

# --- ignored, and holding a credential ---
mkdir -p build
echo 'API_TOKEN=sk-not-a-real-token' > build/.env.local
echo 'compiled' > build/out.js

echo "$target/repo"
