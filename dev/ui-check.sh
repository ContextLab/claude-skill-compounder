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
#
# The world also holds findings of /insights, harvested from an invented usage-data tree,
# and makes a run of /insights due (COMPOUND_INSIGHTS_MIN_SESSIONS=1), so the first session's
# first prompt starts one. Its `claude -p /insights` is given CLAUDE_CONFIG_DIR=<the world's
# Claude directory>, which is not logged in: the child fails at once and costs nothing, and
# the run's outcome is `failed`, which the insights check shows as a WARN. ui-check.sh
# refuses to record when that directory turns out to be logged in.
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
export CLAUDE_HISTORY_SURFER_DIR="$world/surfer" CLAUDE_CODE_PLUGIN_DIRS="" COMPOUND_INSIGHTS_MIN_SESSIONS=1
export UI_PLUGIN="$plugin" UI_CLI="$plugin/bin/compound" UI_PROJECT="$project" UI_WORLD="$world" PS1='$ '
unset COMPOUND_OFF COMPOUND_QUIET CLAUDECODE CLAUDE_CODE_SESSION_ID CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT
SH
. "$world/env.sh"

# A guard, and an ordinary lesson for the reuse check to find.
printf 'Echoing GUARDED_MARKER is the mistake this lesson is about: print the value with printf instead.\n' |
  "$UI_CLI" add --name no-marker-echo --when 'Use when a command echoes GUARDED_MARKER.' --match 'echo\s+GUARDED_MARKER' >/dev/null
printf 'Release notes here are one line per change, newest first, each starting with the issue number.\n' |
  "$UI_CLI" add --name release-notes-format --when 'Use when writing or formatting release notes for this project.' >/dev/null

# What Claude Code's /insights would have written under the world's Claude directory, all of
# it invented: two sessions of this project with friction, and a report with two
# suggestions. The real harvest turns them into four open findings before any session.
usage="$world/claude/usage-data"
mkdir -p "$usage/facets" "$usage/session-meta"
one=0e0e0e0e-1111-4111-8111-000000000001
two=0e0e0e0e-1111-4111-8111-000000000002
cat > "$usage/facets/$one.json" <<JSON
{"session_id": "$one", "underlying_goal": "Deploy the project to staging",
 "friction_counts": {"wrong_approach": 2},
 "friction_detail": "The deploy script was run with no target three times before its error message was read."}
JSON
cat > "$usage/facets/$two.json" <<JSON
{"session_id": "$two", "underlying_goal": "Write the release notes",
 "friction_counts": {"misunderstood_request": 1},
 "friction_detail": "The release notes were written as one paragraph of bullets although this project lists one change per line, newest first, so they were written twice."}
JSON
for session in "$one" "$two"; do
  printf '{"session_id": "%s", "project_path": "%s"}\n' "$session" "$project" > "$usage/session-meta/$session.json"
done
cat > "$usage/report.html" <<'HTML'
<!doctype html><html><body><section id="section-features">
<div class="claude-md-item"><code class="cmd-code">Run ./deploy.sh with --target staging; it has no default target.</code><div class="cmd-why">Several sessions ran it bare and failed first.</div></div>
<div class="claude-md-item"><code class="cmd-code">Keep release notes to one line per change, newest first.</code><div class="cmd-why">Notes were reformatted after review.</div></div>
</section></body></html>
HTML
"$UI_CLI" insights --harvest >/dev/null

# An earlier session, so that a run of /insights is due at the first prompt
# (COMPOUND_INSIGHTS_MIN_SESSIONS=1 in env.sh): it fixed a call, and the fix was declined.
cap="$(printf '{"type":"capture","session":"ui-earlier-session-1","tool":"Bash","failed":"ls build","error":"ls: build: No such file or directory","fixed":"ls dist"}' |
  "$UI_CLI" log --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
"$UI_CLI" skip --settles "$cap" --why 'The build directory was renamed once; nothing to learn.' >/dev/null

# The tape runs this between its two sessions: a second earlier session that left a fix
# unsettled, so the second session's first prompt tells a capture beside the findings.
cat > "$world/later.sh" <<'SH'
printf '{"type":"capture","session":"ui-earlier-session-2","tool":"Bash","failed":"python3 -m pytest","error":"No module named pytest","fixed":"python3 -m unittest"}' |
  "$UI_CLI" log >/dev/null
SH

if [ "${1:-}" = world ]; then
  echo "$world"
  exit 0
fi
# The run of /insights the first prompt starts must fail, not spend: no key or token in the
# environment, and the world's Claude directory not logged in.
for name in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_OAUTH_TOKEN CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX; do
  if [ -n "$(printenv "$name" || true)" ]; then
    echo "ui-check: $name is set, so the world's /insights run could be a paid one; unset it first" >&2
    exit 1
  fi
done
logged="$(CLAUDE_CONFIG_DIR="$world/claude" claude auth status --json 2>/dev/null |
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("loggedIn") is not False)' 2>/dev/null || echo True)"
if [ "$logged" != False ]; then
  echo "ui-check: $world/claude is logged in (or its state is unreadable), so the world's /insights run could be a paid one" >&2
  exit 1
fi
cd "$world"
vhs "$repo/dev/ui-check.tape"
echo "screenshots: $world/shots"
