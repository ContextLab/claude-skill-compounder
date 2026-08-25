#!/usr/bin/env bash
# Build real git repositories in the states that burned anthropics/claude-code #34746,
# #34327 and #23913, plus the three states that broke the first draft of this skill.
#
# Usage: make-fixture.sh <target-dir> [mode]
#   standard        (default) bare origin, one unpushed commit, a staged mutation, an
#                   unstaged mutation, an untracked file with no object behind it, and an
#                   ignored file holding a credential.
#   merge-conflict  mid-merge with an unmerged path, where `git stash push` exits 1.
#   stranger-stash  clean tree with somebody else's older stash already on the stack.
#   scaffold50      50 untracked files under one directory, which a rollup hides.
#
# Creates <target-dir>/origin.git (bare) and <target-dir>/repo (the working clone).
# No ambient git config is required; identity is passed per invocation.
set -euo pipefail

target="${1:?usage: make-fixture.sh <target-dir> [mode]}"
mode="${2:-standard}"
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

# --- the baseline that origin knows about, shared by every mode ---
mkdir -p src
echo 'print("app v1")' > src/app.py
echo '# project' > README.md
printf 'build/\n' > .gitignore
g add -A
g commit -qm 'base'
g push -q origin main

case "$mode" in
standard)
  # one commit that exists only here (reflog-recoverable, until gc)
  echo 'def feature(): return 1' > src/feature.py
  g add src/feature.py
  g commit -qm 'feature'
  # a staged mutation (blob written, no commit)
  echo 'print("app v2")' > src/app.py
  g add src/app.py
  # an unstaged mutation (no object anywhere)
  echo '## edited section' >> README.md
  # the file that dies: untracked, never added, no git object
  printf 'PRECIOUS PLAN: do not lose this\n' > NOTES-DO-NOT-LOSE.md
  # ignored, and holding a credential
  mkdir -p build
  echo 'API_TOKEN=sk-not-a-real-token' > build/.env.local
  echo 'compiled' > build/out.js
  ;;

merge-conflict)
  # An unmerged path makes `git stash push` exit 1 with "could not write index".
  g checkout -qb other
  echo 'print("other")' > src/app.py
  g commit -qam 'other'
  g checkout -q main
  echo 'print("mine")' > src/app.py
  g commit -qam 'mine'
  g merge other >/dev/null 2>&1 || true
  printf 'PRECIOUS PLAN: do not lose this\n' > NOTES-DO-NOT-LOSE.md
  mkdir -p build
  echo 'API_TOKEN=sk-not-a-real-token' > build/.env.local
  ;;

stranger-stash)
  # A clean tree, and somebody else's stash already on the stack. `git stash push`
  # exits 0 having saved nothing, so an unguarded pop steals this one.
  echo 'LAST WEEKS UNRELATED WORK' >> README.md
  g stash push -q -m 'old-unrelated-work'
  ;;

scaffold50)
  mkdir -p scaffold
  i=1
  while [ "$i" -le 50 ]; do
    echo "generated $i" > "scaffold/f$i.txt"
    i=$((i + 1))
  done
  ;;

*)
  echo "unknown mode: $mode" >&2
  exit 2
  ;;
esac

echo "$target/repo"
