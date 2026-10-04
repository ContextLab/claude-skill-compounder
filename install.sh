#!/usr/bin/env bash
# Install compound: use the checkout this script sits in, or fetch one, then hand over
# to `bin/compound install`. Works piped: curl -fsSL <url>/install.sh | bash
#
#   COMPOUND_HOME   where the package and its state live (default ~/.claude/compound)
#   COMPOUND_REF    branch to install when fetching (default main)
#   COMPOUND_REPO   repository to fetch (default the ContextLab one)
#
# Arguments are passed to `compound install` (--claude-dir D, --bin-dir D).
{
set -eu

say() { printf '%s\n' "$*" >&2; }
die() { say "install.sh: $*"; exit 1; }

repo="${COMPOUND_REPO:-https://github.com/ContextLab/claude-skill-compounder.git}"
ref="${COMPOUND_REF:-main}"

python=""
for candidate in python3 /usr/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1; then python="$candidate"; break; fi
done
[ -n "$python" ] || die "python3 is required and was not found on PATH"

# Piped into bash there is no script file, so BASH_SOURCE is empty and we fetch.
here=""
src="${BASH_SOURCE[0]:-}"
if [ -n "$src" ] && [ -f "$src" ]; then
  here="$(cd "$(dirname "$src")" && pwd -P)"
fi

if [ -n "$here" ] && [ -f "$here/bin/compound" ]; then
  app="$here"
else
  command -v git >/dev/null 2>&1 || die "git is required to fetch the package"
  home="${COMPOUND_HOME:-$HOME/.claude/compound}"
  app="$home/app"
  if [ -d "$app/.git" ]; then
    say "updating $app ($ref)"
    git -C "$app" fetch --quiet origin "$ref" || die "git fetch failed in $app"
    git -C "$app" checkout --quiet "$ref" || die "cannot check out $ref in $app"
    git -C "$app" pull --quiet --ff-only origin "$ref" || die "git pull --ff-only failed in $app"
  elif [ -e "$app" ]; then
    die "$app exists and is not a git checkout; move it away and run again"
  else
    say "cloning $repo ($ref) to $app"
    mkdir -p "$home"
    git clone --quiet --branch "$ref" "$repo" "$app" || die "git clone failed"
  fi
  [ -f "$app/bin/compound" ] || die "$app has no bin/compound (is $ref the right branch?)"
fi

exec "$python" "$app/bin/compound" install "$@"
}
