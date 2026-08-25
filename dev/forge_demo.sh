#!/usr/bin/env bash
# Renders the README animation: a simulated Claude Code session in which a
# procedure clears the bar and gets forged into a skill.
#
# The *session* is staged -- the prompt, the assistant's turns, and the subagent
# results are scripted, because a real forge takes minutes and spends real tokens.
# Everything below the input box is real: the state file is written by the real
# bin/skillforge and the status line is rendered by the real statusline/statusline.sh,
# repainted once a second because that is Claude Code's minimum refreshInterval. So
# the animation is the animation, at the speed you would actually see it.
#
# The transcript is REAL: this is the forge of `parallel-agents-one-codebase`,
# including the five blocking findings red-team round 1 actually returned.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
STATE="$(mktemp -d)"
trap 'rm -rf "$STATE"; printf "\033[r\033[?25h"' EXIT   # \033[r drops the scroll region
export SKILL_COMPOUNDER_STATE="$STATE"
FORGE="$HERE/bin/skillforge"
LINE="$HERE/statusline/statusline.sh"
PAYLOAD='{"session_id":"demo","workspace":{"current_dir":"'"$HOME"'/my-project"}}'

# A status line that was already configured before this package was installed,
# to show that ours wraps it rather than replacing it.
cat > "$STATE/statusline-base.sh" <<'BASE'
#!/usr/bin/env bash
printf '\033[2m~/my-project\033[0m \033[36mgit:(main)\033[0m'
BASE
chmod +x "$STATE/statusline-base.sh"

O=$'\033[38;5;215m'   # the assistant bullet
B=$'\033[1m'; D=$'\033[2m'; G=$'\033[32m'; R=$'\033[31m'; C=$'\033[36m'; X=$'\033[0m'

# Derive the width from the terminal instead of assuming one. A box even ONE
# column too wide wraps, which pushes the pinned block down a row and leaves the
# overflow of the status line sitting on the last row -- it reads as garbage
# characters in the corner, and it hides the progress bar until the very end,
# when the shorter done-state string finally fits. Measured inside vhs at
# Width 1120 / FontSize 14: cols=117, lines=35.
COLS="$(tput cols 2>/dev/null || echo 100)"
W=$(( COLS - 2 ))
[ "$W" -gt 118 ] && W=118
rule() { local ch="$1" n=$(( W - 2 )) s=""; while [ "${#s}" -lt "$n" ]; do s="${s}${ch}"; done; printf '%s' "$s"; }
TOP="${D}╭$(rule ─)╮${X}"
BOT="${D}╰$(rule ─)╯${X}"
MID="$(printf "${D}│${X} ${O}>${X}%*s${D}│${X}" $(( W - 4 )) "")"

# The bottom block is pinned with a DEC scroll region, not with cursor arithmetic.
# Cursor-relative positioning works only while the transcript fits on screen: as
# soon as it is long enough to scroll, every saved offset is off by the number of
# lines that rolled off the top, and the block starts eating the transcript. So
# rows 1..ROWS-H become the scrolling transcript and the last H rows are ours
# alone -- printing in one region cannot disturb the other.
#
# The block is written with a SINGLE printf. Clear-then-redraw is what makes the
# progress bar blink out and back on every refresh; each line instead ends with
# \033[K so it overwrites in place, and the cursor is saved (\0337) and restored
# (\0338) around the whole thing so the transcript never loses its place.
H=5                                        # rows reserved at the bottom
ROWS="$(tput lines 2>/dev/null || echo 40)"
TOPZONE=$(( ROWS - H ))
BLOCK=$(( TOPZONE + 1 ))

paint() {
  local status
  status="$(printf '%s' "$PAYLOAD" | "$LINE" 2>/dev/null)"
  printf '\0337\033[%d;1H\033[K\033[%d;1H%s\033[K\033[%d;1H%s\033[K\033[%d;1H%s\033[K\033[%d;1H  %s\033[K\0338' \
    "$BLOCK" "$(( BLOCK + 1 ))" "$TOP" "$(( BLOCK + 2 ))" "$MID" \
    "$(( BLOCK + 3 ))" "$BOT" "$(( BLOCK + 4 ))" "$status"
}
say()  { printf '%s\033[K\n' "$1"; paint; }
hold() { local n="${1:-1}"; while [ "$n" -gt 0 ]; do sleep 1; paint; n=$(( n - 1 )); done; }
at()   { "$FORGE" "$@" >/dev/null 2>&1; }

# Reserve the bottom H rows, then park the cursor at the top of the transcript.
printf '\033[2J\033[1;%dr\033[1;1H' "$TOPZONE"
printf '\033[?25l'   # hide the cursor; it would sit in the middle of the block
paint

# Nobody asks for a skill here. The user asked for ordinary work; the PostToolUse
# checkpoint fires on its own after CI_EDIT_EVERY edits, and the session is the
# one that notices. That is the whole point, so the demo must not open with a
# "please make me a skill" prompt.
say "${O}>${X} the agents keep clobbering each other on that refactor, sort it out"
say ""
say "${O}⏺${X} ${B}Edit${X}(worker_pool.py) ${D}· ${B}Edit${X}${D}(dispatch.py) · ${B}Edit${X}${D}(merge_queue.py)${X}"
say "  ${D}⎿  3 files changed${X}"
hold 2
say ""
say "  ${D}${B}[skill-compounder]${X}${D} checkpoint after 24 edits — is this procedure BOTH${X}"
say "  ${D}                   costly to have gotten right AND likely to recur?${X}"
hold 2
say ""
say "${O}⏺${X} ${B}Grep${X}(parallel|subagent · ~/.claude/skills, plugins/*/skills)"
say "  ${D}⎿  dispatching-parallel-agents — \"no shared state between investigations\"${X}"
hold 2
say ""
say "${O}⏺${X} That is the opposite case: ours all ${B}write${X} to one tree. Not covered."
say "  ${G}costly${X}     4 dead ends today — one agent read another's live mutation"
say "             as a defect, a torn read, a fabricated repro, shell-less agents"
say "  ${G}recurring${X}  standing workflow; it happened three times in one session"
say ""
at start parallel-agents-one-codebase 8 "parallel agents editing ONE repo, partitioned by file ownership"
say "${O}⏺${X} ${B}Bash${X}(skillforge start parallel-agents-one-codebase 8 …)"
say "  ${D}⎿  forging 'parallel-agents-one-codebase' (8 steps) — live in the status line${X}"
hold 2

say ""
say "${O}⏺${X} ${B}Task${X}(builder — write SKILL.md from this transcript, dead ends included)"
at step 1 "builder: drafting SKILL.md"
hold 3
at step 2 "builder: draft written"
say "  ${D}⎿  Done (3 tool uses · 84.9k tokens)${X}"
hold 2

say ""
say "${O}⏺${X} ${B}Task${X}(red-team — fresh agent, no context, execute it cold)"
at step 3 "red-team round 1 (cold agent)"
hold 3
at step 4 "5 blocking findings — back to the builder"
say "  ${D}⎿  ${R}✗${D} 5 blocking — it ran every command against real scratch repos:${X}"
say "  ${D}      · \"git checkout -- the other\" — in ONE tree that destroys BOTH${X}"
say "  ${D}        agents' edits. Measured: AGENT_A_FIX and AGENT_B_FIX both gone${X}"
say "  ${D}      · git show HEAD:<new file> exits 128 → empty grep → reads as${X}"
say "  ${D}        \"symbol absent\" → the agent retracts a REAL finding${X}"
say "  ${D}      · git checkout -- leaves an untracked file in place, then the${X}"
say "  ${D}        skill calls the still-dirty tree clean${X}"
say "  ${D}      · step 1 cites /tmp/owned_paths.txt, a file it never defines${X}"
say "  ${D}      · the trigger also matches \"…each in its own worktree\"${X}"
hold 5

say ""
say "${O}⏺${X} ${B}Task${X}(builder — apply round-1 findings)"
at step 5 "builder: applying round-1 findings"
hold 3
say "  ${D}⎿  git stash push keeps both edits · ls-files --error-unmatch gate before${X}"
say "  ${D}      git show · git clean for untracked · owned.txt format defined${X}"
say ""
say "${O}⏺${X} ${B}Task${X}(red-team #2 — a NEW cold agent; the last one is no longer cold)"
at step 6 "red-team round 2 (new cold agent)"
hold 3
at step 7 "round 2 found 3 more — builder applying"
say "  ${D}⎿  ${R}✗${D} DO-NOT-SHIP. Round-1 fixes verified — and 3 new blocking:${X}"
say "  ${D}      · the disjointness check now CERTIFIES a broken partition:${X}"
say "  ${D}        git ls-files returns many paths, the agent tag lands on only${X}"
say "  ${D}        the first, so sort -k2 never makes the duplicate adjacent${X}"
say "  ${D}      · cleanup no-ops on a STAGED mutation: git checkout -- exits 0${X}"
say "  ${D}        and reverts nothing; needs git restore --staged --worktree${X}"
say "  ${D}      · \"run agents in parallel on this repo\" is write-agnostic, so${X}"
say "  ${D}        it fires on the read-only fan-out the skill excludes${X}"
hold 5
say ""
say "${O}⏺${X} A check that quietly blesses a bad partition is worse than none."
say "  Round 3, and the cap is 3 — after this it gets narrowed or abandoned."
say ""
say "${O}⏺${X} ${B}Task${X}(red-team #3 — another new cold agent)"
at step 8 "red-team round 3 (new cold agent)"
hold 3
say "  ${D}⎿  ${G}✓${D} discipline verified: triggers 6/6, no duplication, all four${X}"
say "  ${D}      tracked overlap forms caught, dirty-state table correct${X}"
say "  ${D}    ${R}✗${D} still 4 blocking, all in the shell machinery:${X}"
say "  ${D}      · \$RUN=\$(mktemp -d) cannot survive — Bash calls do not share${X}"
say "  ${D}        shell state, so every later command targets /${X}"
say "  ${D}      · git clean -fxd -- build/ removes the DIRECTORY, so it would${X}"
say "  ${D}        delete .env.local, the venv, node_modules${X}"
hold 5
say ""
say "${O}⏺${X} That is the cap. The rule is narrow or abandon — never ship a"
say "  half-working skill. The discipline passed every round; the bespoke"
say "  script failed all three. So the script goes."
say ""
at done "narrowed at the cap: discipline kept, machinery cut"
hold 2
say "  ${D}⎿  cut: the \$RUN pipeline · ls-files --error-unmatch · clean -fxd${X}"
say "  ${D}    kept: ownership partition · the four dirty states · report-don't-edit${X}"
say "  ${D}          · one authoritative suite run · every command round 3 verified${X}"
hold 1

say ""
say "${O}⏺${X} Forged ${C}~/.claude/skills/parallel-agents-one-codebase/${X} — hot-reloaded,"
say "  so it is usable in ${G}this${X} session, not the next one."
# Do NOT tear the block down here. The recording has to end while the session UI
# is still on screen; clearing it would put a bare shell prompt in the last frame
# and give the whole thing away.
hold 20   # must outlast the tape; if the script exits first, the shell prompt prints into the frame
