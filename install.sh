#!/usr/bin/env bash
# Install or uninstall compound. Works piped:
#
#   curl -fsSL <url>/install.sh | bash                            install
#   curl -fsSL <url>/install.sh | bash -s -- uninstall            uninstall, keep what was recorded
#   curl -fsSL <url>/install.sh | bash -s -- uninstall --purge    uninstall and delete COMPOUND_HOME
#
# Install uses the checkout this script sits in, or fetches one, then hands over to
# `bin/compound install`. Uninstall finds the installed package and hands over to its
# `bin/compound uninstall`; it never fetches anything.
#
#   COMPOUND_HOME        where the package and its state live (default <claude dir>/compound)
#   COMPOUND_CLAUDE_DIR  the Claude Code directory (default ~/.claude)
#   COMPOUND_REF         branch or tag to install when fetching (default: the newest
#                        release tag vX.Y.Z, or main when the repository has none)
#   COMPOUND_REPO        repository to fetch (default the ContextLab one)
#
# The first argument may be `install` (the default) or `uninstall`. The rest are passed
# to `compound install` (--claude-dir D, --bin-dir D) or `compound uninstall`
# (--claude-dir D, --purge).
{
set -eu

say() { printf '%s\n' "$*" >&2; }
die() { say "install.sh: $*"; exit 1; }

repo="${COMPOUND_REPO:-https://github.com/ContextLab/claude-skill-compounder.git}"
ref="${COMPOUND_REF:-}"
home="${COMPOUND_HOME:-${COMPOUND_CLAUDE_DIR:-$HOME/.claude}/compound}"
app="$home/app"
# A value from the environment is never read by git as an option: the repository may not
# begin with "-" or name a remote helper ("<helper>::"), and the ref is a branch or tag
# name of letters, digits, ".", "_", "-" and "/", starting with a letter or digit.
case "$repo" in
  -*|*::*) die "COMPOUND_REPO is not a repository git can be given: $repo" ;;
esac
if [ -n "$ref" ]; then
  case "$ref" in
    [!A-Za-z0-9]*|*[!A-Za-z0-9._/-]*|*..*|*//*|*/|*.lock) die "COMPOUND_REF is not the name of a branch or a tag: $ref" ;;
  esac
fi
# The oldest release that can be installed: earlier tags hold no bin/compound.
min_release="0.4.0"

action="install"
case "${1:-}" in
  install|uninstall) action="$1"; shift ;;
esac

python=""
found=""
for candidate in python3 /usr/bin/python3; do
  command -v "$candidate" >/dev/null 2>&1 || continue
  found="$candidate"
  if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then python="$candidate"; break; fi
done
[ -n "$found" ] || die "python3 is required and was not found on PATH"
[ -n "$python" ] || die "python 3.9 or later is required; $found is $("$found" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo older)"

# Piped into bash there is no script file, so BASH_SOURCE is empty.
here=""
cloned=""
src="${BASH_SOURCE[0]:-}"
if [ -n "$src" ] && [ -f "$src" ]; then
  here="$(cd "$(dirname "$src")" && pwd -P)"
fi

if [ "$action" = "uninstall" ]; then
  # The installed package: the one the install record names, else the clone under
  # COMPOUND_HOME, else the checkout this script sits in.
  recorded="$("$python" -c 'import json, sys
try:
    with open(sys.argv[1]) as handle:
        value = json.load(handle).get("package")
except Exception:
    value = None
print(value if isinstance(value, str) else "")' "$home/install.json")"
  cli=""
  for candidate in "$recorded" "$app" "$here"; do
    if [ -n "$candidate" ] && [ -f "$candidate/bin/compound" ]; then cli="$candidate/bin/compound"; break; fi
  done
  if [ -z "$cli" ]; then
    say "compound is not installed: there is no install record at $home/install.json and no package at $app. Nothing was changed."
    if [ -d "$home" ]; then
      say "$home exists and was left as it is; delete that directory to remove what it holds."
    fi
    exit 0
  fi
  exec "$python" "$cli" uninstall "$@"
fi

# The newest release among the `git ls-remote --tags` lines on stdin: the highest
# vX.Y.Z, compared as numbers, that is not older than $min_release. Prints nothing when
# there is none. Sorted here because `git ls-remote --sort` needs git 2.18.
newest_release() {
  "$python" -c 'import re, sys
low = tuple(int(part) for part in sys.argv[1].split("."))
best = None
for line in sys.stdin:
    found = re.search(r"refs/tags/v(\d+)\.(\d+)\.(\d+)(\^\{\})?$", line.strip())
    if found:
        version = tuple(int(part) for part in found.group(1, 2, 3))
        if version >= low and (best is None or version > best):
            best = version
if best:
    print("v%d.%d.%d" % best)' "$min_release"
}

if [ -n "$here" ] && [ -f "$here/bin/compound" ]; then
  app="$here"
else
  command -v git >/dev/null 2>&1 || die "git is required to fetch the package"
  if [ -d "$app/.git" ]; then
    if [ -z "$ref" ]; then
      ref="$( (git -C "$app" ls-remote --tags origin 2>/dev/null || true) | newest_release)"
      [ -n "$ref" ] || ref="main"
    fi
    say "updating $app ($ref)"
    git -C "$app" fetch --quiet --tags origin || die "git fetch failed in $app"
  elif [ -e "$app" ]; then
    die "$app exists and is not a git checkout; move it away and run again"
  else
    if [ -z "$ref" ]; then
      ref="$( (git ls-remote --tags -- "$repo" 2>/dev/null || true) | newest_release)"
      [ -n "$ref" ] || ref="main"
    fi
    say "cloning $repo ($ref) to $app"
    mkdir -p "$home"
    git clone --quiet --no-checkout -- "$repo" "$app" || die "git clone failed"
    cloned=1
  fi
  # A clone this run made and cannot use is not left in the way of the next run.
  unusable() {
    if [ -n "$cloned" ] && [ -d "$app/.git" ]; then rm -rf "$app"; fi
    die "$*"
  }
  # A branch of origin is checked out and pulled. Anything else is a tag: the clone is
  # put at it, on no branch.
  if git -C "$app" show-ref --verify --quiet "refs/remotes/origin/$ref"; then
    git -C "$app" checkout --quiet "$ref" -- || unusable "cannot check out $ref in $app"
    if [ -z "$cloned" ]; then
      git -C "$app" pull --quiet --ff-only origin "$ref" || die "git pull --ff-only failed in $app"
    fi
  else
    git -C "$app" -c advice.detachedHead=false checkout --quiet --detach "$ref" -- \
      || unusable "cannot check out $ref (is $ref a branch or tag of $repo?)"
  fi
  if [ ! -f "$app/bin/compound" ]; then
    unusable "$ref of $repo has no bin/compound (is $ref the right branch or tag?)"
  fi
fi

exec "$python" "$app/bin/compound" install "$@"
}
