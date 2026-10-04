#!/bin/sh
# Builds a throwaway world for dev/ui-check.tape and records it with vhs.
#
#   dev/ui-check.sh            record the whole tape; prints where the screenshots are
#   dev/ui-check.sh world      only build the world and print its directory
#
# Nothing here touches the real store or the real settings: the session runs with
# COMPOUND_HOME, COMPOUND_CLAUDE_DIR, COMPOUND_PROJECT and the prompt log in a temporary
# directory, and CLAUDE_CODE_PLUGIN_DIRS empty so no installed copy of the mod loads too.
# It spends model calls. UI_PLUGIN names another copy of the package to load.
set -eu
repo="$(cd "$(dirname "$0")/.." && pwd -P)"
plugin="${UI_PLUGIN:-$repo}"
# pwd -P: the CLI, git and the session must name the project by one path.
world="$(cd "${TMPDIR:-/tmp}" && pwd -P)/compound-ui-check"
rm -rf "$world"
# One project path for every run: Claude Code keeps a trust answer and a transcript folder
# per path under its own directory, and one of each is enough.
project="$world/project"
mkdir -p "$world/home" "$world/claude" "$world/surfer" "$world/shots" "$project"

cat > "$project/deploy.sh" <<'SH'
#!/bin/sh
# The deploy needs a target; there is no default.
if [ "${1:-}" != "--target" ] || [ -z "${2:-}" ]; then
  echo "deploy.sh: error: a target is required, e.g. ./deploy.sh --target staging" >&2
  exit 2
fi
echo "deployed to $2"
SH
chmod +x "$project/deploy.sh"

cat > "$world/env.sh" <<SH
export COMPOUND_HOME="$world/home" COMPOUND_CLAUDE_DIR="$world/claude" COMPOUND_PROJECT="$project"
export CLAUDE_HISTORY_SURFER_DIR="$world/surfer" CLAUDE_CODE_PLUGIN_DIRS=""
export UI_PLUGIN="$plugin" UI_CLI="$plugin/bin/compound" UI_PROJECT="$project" PS1='$ '
unset COMPOUND_OFF COMPOUND_QUIET CLAUDECODE CLAUDE_CODE_SESSION_ID CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT
SH
. "$world/env.sh"

# A guard, and an ordinary lesson for the reuse check to find.
printf 'Echoing GUARDED_MARKER is the mistake this lesson is about: print the value with printf instead.\n' |
  "$UI_CLI" add --name no-marker-echo --when 'Use when a command echoes GUARDED_MARKER.' --match 'echo\s+GUARDED_MARKER' >/dev/null
printf 'Release notes here are one line per change, newest first, each starting with the issue number.\n' |
  "$UI_CLI" add --name release-notes-format --when 'Use when writing or formatting release notes for this project.' >/dev/null

if [ "${1:-}" = world ]; then
  echo "$world"
  exit 0
fi
cd "$world"
vhs "$repo/dev/ui-check.tape"
echo "screenshots: $world/shots"
