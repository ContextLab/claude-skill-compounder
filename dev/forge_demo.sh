#!/usr/bin/env bash
# Drives one complete, fabricated forge for the README animation.
#
# Nothing here is simulated except the *decision* and the subagents: the state file
# is written by the real `bin/skillforge`, and every frame of the bottom line is
# rendered by the real `statusline/statusline.sh` — the same code path a user sees.
# The narration above it is what the orchestrating session prints as it works.
#
# Repaints once per second because that is Claude Code's minimum refreshInterval,
# so the pacing of the animation in the GIF is the pacing of the real thing.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
STATE="$(mktemp -d)"
trap 'rm -rf "$STATE"' EXIT
export SKILL_COMPOUNDER_STATE="$STATE"
FORGE="$HERE/bin/skillforge"
LINE="$HERE/statusline/statusline.sh"
PAYLOAD='{"session_id":"demo","workspace":{"current_dir":"'"$HOME"'/my-project"}}'

# A pre-existing status line, to show that ours wraps rather than replaces it.
cat > "$STATE/statusline-base.sh" <<'BASE'
#!/usr/bin/env bash
printf '\033[2m~/my-project\033[0m \033[36mgit:(main)\033[0m'
BASE
chmod +x "$STATE/statusline-base.sh"

D=$'\033[2m'; Y=$'\033[33m'; G=$'\033[32m'; C=$'\033[1;36m'; X=$'\033[0m'

paint() { printf '\r\033[K'; printf '%s' "$PAYLOAD" | "$LINE" 2>/dev/null; }
say()   { printf '\r\033[K%s\n' "$1"; paint; }
hold()  { local n="${1:-1}"; while [ "$n" -gt 0 ]; do sleep 1; paint; n=$(( n - 1 )); done; }
at()    { "$FORGE" "$@" >/dev/null 2>&1; }

printf '\n'
say "${Y}[skill-compounder]${X} Checkpoint after 24 file edits. Is this procedure BOTH costly"
say "${Y}               ${X} to have gotten right AND likely to recur?"
say ""
say "  ${G}costly${X}     ~2h of trial and error; the ordering constraint is not discoverable"
say "  ${G}recurring${X}  third time this month, and every deploy path needs it"
say "  ${C}→ forging${X}  retry-backoff-wrapper"
say ""
at start retry-backoff-wrapper 8 "retry+backoff around the flaky deploy API"
hold 2

say "${D}  builder agent  → drafting SKILL.md from the transcript (incl. the dead ends)${X}"
at step 1 "builder: drafting SKILL.md"
hold 3
at step 2 "builder: draft written"
hold 2

say "${D}  red-team #1    → fresh agent, no context, told only \"execute this cold\"${X}"
at step 3 "red-team round 1 (cold agent)"
hold 3
say "${D}                 ✗ 3 findings: step 1 assumes a cwd · trigger fires on any retry${X}"
say "${D}                   talk · the documented curl was never actually run${X}"
at step 4 "3 findings — back to the builder"
hold 3

at step 5 "builder: applying round-1 findings"
hold 2
say "${D}  red-team #2    → a NEW cold agent (after round 1 the last one is not cold)${X}"
at step 6 "red-team round 2 (new cold agent)"
hold 3
say "${D}                 ${X}${G}✓${X}${D} clean: cold start, triggers discriminate, claims verified${X}"
hold 1

at done "clean on round 2"
say ""
say "  ${G}✓${X} ${C}~/.claude/skills/retry-backoff-wrapper/${X} — hot-reloaded, usable in ${G}this${X} session"
hold 4
printf '\r\033[K\n'
