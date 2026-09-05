#!/usr/bin/env bash
# Renders the README animation: a simulated Claude Code session that pays for a
# lesson the cheap way, then forges the procedure that kept costing it.
#
# The *session* is staged -- the prompt, the assistant's turns, and the subagent
# results are scripted, because a real forge takes minutes and spends real tokens.
# Everything below the input box is real: the state file is written by the real
# bin/skillforge and the status line is rendered by the real statusline/statusline.sh,
# repainted once a second because that is Claude Code's minimum refreshInterval. So
# the animation is the animation, at the speed you would actually see it.
#
# The transcript is REAL, and it is in two parts.
#
#   1. The lesson (tier 1). `gh run list --commit c05d01e` really does return `[]`
#      while the headSha prefix filter really does return that run -- both re-run on
#      2026-09-05 against this repository. The block the checkpoint prints is the
#      literal output of hooks/repeat-gate.sh driven with that fail-then-fix pair,
#      signature and all, and the two `skillnote` lines under it are what
#      `bin/skillnote add --lesson` really printed, note id and reminder id included.
#
#   2. The forge (tier 2) of `watch-ci-run`, as it really happened on this machine
#      under the round diet: SIX steps, so 2 + 2 x rounds gives TWO red-team rounds.
#      Both rounds' counts and every finding shape under them are read verbatim off
#      <state>/rounds/watch-ci-run.tsv, and both rounds returned `6 blocking of 13`.
#
#      That is why the ending is an ESCALATION and not a `done`. Blocking HELD rather
#      than fell, so `skillforge escalate --converging` refuses (exit 4, "which is not
#      a fall") and the only thing that can buy a third round is a narrower skill.
#      `--narrowed` was granted, raising the budget to 8 steps and 3 rounds, and the
#      demo stops there -- with the forge still running, which is where the real one
#      still was when this was recorded. It shows no third round, because the third
#      round had not happened. Do not replace this with a `done` the ledger does not
#      have: the whole claim of this recording is that its transcript is real.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
STATE="$(mktemp -d)"
trap 'rm -rf "$STATE"; printf "\033[r\033[?25h"' EXIT   # \033[r drops the scroll region
export SKILL_COMPOUNDER_STATE="$STATE"
# `skillforge done` INSTALLS the skill it closes, and `skills_dest` falls back to
# $HOME/.claude/skills when the state root holds no install manifest -- so a throwaway
# SKILL_COMPOUNDER_STATE alone does NOT make this script hermetic. It would symlink a
# real skill into the viewer's own config the moment `skills/watch-ci-run/` exists in
# this checkout. Point the install at the throwaway too.
export SKILLFORGE_SKILLS_DIR="$STATE/skills"
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
# when the shorter done-state string finally fits. Under the tape's own settings --
# Width 1440, Height 680, FontSize 14, Padding 20 -- vhs gives cols=152 and lines=35,
# measured 2026-09-05 by running `tput cols; tput lines` inside that exact tape rather
# than carried over from the Width 1120 run this comment used to cite. So the 118 cap is
# what sets the box width here, the transcript has 152 columns, and the widest line it
# prints is 101. Re-measure rather than trusting this if the tape's geometry changes.
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

# ------------------------------------------------------------------ 1. the lesson
# Nobody asks for a skill here, and nobody asks for a note either. The user asked
# for ordinary work; the fail-then-fix is what the session was going to do anyway,
# and the PostToolUse arm of hooks/repeat-gate.sh is what notices. That is the whole
# point, so the demo must not open with a "please make me a skill" prompt.
say "${O}>${X} push it and tell me when CI goes green"
say ""
say "${O}⏺${X} ${B}Bash${X}(until gh run list --commit c05d01e --json status | grep -q completed; do sleep 30; done)"
say "  ${D}⎿  ${R}✗${D} Exit code 143 · Command timed out after 10m 0s${X}"
hold 2
say ""
say "${O}⏺${X} ${D}--commit matched nothing for ten minutes. Filter on the headSha instead:${X}"
say "${O}⏺${X} ${B}Bash${X}(gh run list --limit 30 --json headSha,status,conclusion | jq -c '…startswith(\"c05d01e\")')"
say "  ${D}⎿  [{\"conclusion\":\"success\",\"headSha\":\"c05d01eb3eb18b3b8046…\",\"name\":\"tests\",\"status\":\"completed\"}]${X}"
hold 2
say ""
say "  ${D}${B}[skill-compounder]${X}${D} A call that failed in this session has since succeeded a different${X}"
say "  ${D}                   way, and the store recorded that as its recovery.${X}"
say "  ${D}                     failed:  until gh run list --commit c05d01e --json status | grep…${X}"
say "  ${D}                     error:   Exit code 143 Command timed out after 10m 0s${X}"
say "  ${D}                     worked:  gh run list --limit <N> --json headSha,status,conclusion…${X}"
say "  ${D}                   No lesson references this signature yet.${X}"
say "  ${D}                   A lesson lifts it:${X}"
say "  ${D}                     skillnote add --lesson c2295913779x93-e2265733395x44 \"<what was learned>\"${X}"
say "  ${D}                     skillrepeat dismiss c2295913779x93-e2265733395x44 --why \"<why>\"${X}"
say "  ${D}                       (a person at a terminal only)${X}"
hold 3
say ""
say "${O}⏺${X} ${B}Bash${X}(skillnote add --lesson c2295913779x93-e2265733395x44 \"Poll CI in a background…\")"
say "  ${D}⎿  skillnote: recorded (n2691463010x166) in ~/my-project/.claude/CLAUDE.md${X}"
say "  ${D}   skillnote: reminder (n341313959x237) keyed on the failing call for c2295913779x93-…${X}"
hold 2

# ------------------------------------------------------------------- 2. the forge
say ""
say "${O}⏺${X} That is the cheap tier: the note is read next session, the reminder fires on"
say "  the call. But this is the third time this week, and it is never one command."
say ""
say "  ${D}${B}[skill-compounder]${X}${D} Checkpoint after 12 file edits. … Is the procedure you are${X}"
say "  ${D}                   working through right now BOTH costly to have gotten right${X}"
say "  ${D}                   AND likely to recur?${X}"
hold 2
say ""
say "${O}⏺${X} ${G}costly${X}     three nameable dead ends: ${B}--commit${X} returns nothing; a foreground until-"
say "             loop dies at the 10-minute cap, exit 143; ${B}git rev-parse origin/<branch>${X}"
say "             fails right after a push that really succeeded"
say "  ${G}recurring${X}  three skillnote lines over two days and two sessions"
hold 2
say ""
at start watch-ci-run 6 "watch a GitHub Actions run for a just-pushed commit" \
   --trigger "three skillnote lines over two days: gh run list --commit returns nothing; a foreground until-loop dies at the 10-minute cap; git rev-parse origin/<branch> fails after a good push" \
   --trigger-kind hook-checkpoint
say "${O}⏺${X} ${B}Bash${X}(skillforge start watch-ci-run 6 …)"
say "  ${D}⎿  forging 'watch-ci-run' (6 steps) — animation live in the status line${X}"
say "  ${D}   6 steps is 2 + 2 × rounds, so the budget is TWO red-team rounds, not three${X}"
hold 2

say ""
say "${O}⏺${X} ${B}Task${X}(builder — write SKILL.md from those three notes and the calls that worked)"
say "  ${D}[mission] The user's requests in this session, verbatim, oldest first. 3 recorded; 2 quoted below.${X}"
at step 1 "builder: drafting SKILL.md"
hold 2
at step 2 "builder: draft written"
say "  ${D}⎿  Done (14 tool uses · 71.2k tokens)${X}"
hold 2

say ""
say "${O}⏺${X} ${B}Task${X}(red-team — a cold agent, no context, running every command in the draft)"
at step 3 "red-team round 1 (cold agent)"
hold 2
at round --name watch-ci-run --blocking 6 --total 13 \
   --subsystems "watch.sh verdict correctness (page-bound guard, --min-runs default); watch.sh signal handling and error-path messages; SKILL.md Phase 1 snippet and invocation examples" \
   --shapes "false green with exit 0 on the recommended path; a guard disabled by the very flag the skill recommends; an undefined variable in the copyable summary block; an example command that cannot resolve from a session's cwd; a documented recovery that does not actually stop the process"
at step 4 "6 blocking of 13 — back to the builder"
say "  ${D}⎿  ${R}✗${D} round 1/2 — 6 blocking of 13 findings, every one run, in five shapes:${X}"
say "  ${D}      · a false green: the watcher exits 0 on the recommended path${X}"
say "  ${D}      · a guard disabled by the very flag the skill recommends${X}"
say "  ${D}      · an undefined variable in the copyable summary block${X}"
say "  ${D}      · an example command that cannot resolve from a session's cwd${X}"
say "  ${D}      · a documented recovery that does not actually stop the process${X}"
hold 4

say ""
say "${O}⏺${X} ${B}Task${X}(builder — apply round-1 findings)"
at step 5 "builder: applying round-1 findings"
hold 2
say ""
say "${O}⏺${X} ${B}Task${X}(red-team #2 — a NEW cold agent; the last one is no longer cold)"
at step 6 "red-team round 2 (new cold agent)"
hold 2
# ROUND 2's counts are read off the same round record round 1's came from -- and they are
# the SAME counts: 6 blocking of 13 twice over. Blocking HELD rather than fell, which is
# what makes this the honest demonstration of the cap: the escalation that would buy a
# third round is the one the tool refuses.
R2B=6; R2T=13
at round --name watch-ci-run --blocking "$R2B" --total "$R2T" \
   --subsystems "watch.sh listing-completeness (short prefix never passes; --timeout <= --settle exits 0 on an unelapsed settle window); conclusion taxonomy (cancelled/action_required reported as CI failures); Phase 1's stated guarantee and the description that repeats it; two false measured claims (detached-HEAD exit code; finish-task sends you here)" \
   --shapes "the round-1 repair of the page-bound guard produced the next finding in the same subsystem; a refusal on one kind of incomplete evidence and a pass on another kind; a title and a description promising more than the block delivers; a measured exit code that is not the exit code"
say "  ${D}⎿  ${R}✗${D} round 2/2 — $R2B blocking of $R2T again. Round 1's fixes held; these are new:${X}"
say "  ${D}      · the round-1 repair of the page-bound guard produced the NEXT finding${X}"
say "  ${D}        in the same subsystem${X}"
say "  ${D}      · a refusal on one kind of incomplete evidence and a pass on another${X}"
say "  ${D}      · a title and a description promising more than the block delivers${X}"
say "  ${D}      · a measured exit code that is not the exit code${X}"
hold 4
say ""
say "${O}⏺${X} ${B}Bash${X}(skillforge round --name watch-ci-run --blocking $R2B --total $R2T)"
say "  ${D}⎿  round 2/2 recorded — $R2B blocking of $R2T finding(s); that was the last budgeted${X}"
say "  ${D}   round. Another one is earned, not taken: 'skillforge escalate … --converging'${X}"
hold 2
say ""
# Really run, not just printed: it exits 4 and writes nothing, which is the point.
at escalate --name watch-ci-run --converging
say "${O}⏺${X} ${B}Bash${X}(skillforge escalate --name watch-ci-run --converging)"
say "  ${D}⎿  ${R}✗${D} refused: blocking went round 1 = 6 → round 2 = 6, which is not a fall.${X}"
say "  ${D}     A further round is earned by a strictly falling blocking count. Narrow${X}"
say "  ${D}     instead — '--narrowed \"<what you cut>\"' — or close it: skillforge fail${X}"
hold 3
say ""
say "${O}⏺${X} That is the cap doing its job: six blocking twice is not converging, and a"
say "  third round cannot be bought with progress that did not happen. Only a"
say "  ${B}narrower skill${X} can buy one, and the ledger records what it cost."
hold 2
say ""
at escalate --name watch-ci-run --narrowed "CUT: the listing-completeness subsystem -- client-side headSha prefix filtering, the --limit paging machinery and the --settle window. The skill now requires a full 40-character sha (expanded locally with git rev-parse) and asks the server for exactly that sha's runs with gh run list --commit, which is complete by construction."
say "${O}⏺${X} ${B}Bash${X}(skillforge escalate --name watch-ci-run --narrowed \"CUT: the listing-completeness…\")"
say "  ${D}⎿  escalation granted (narrowed) — budget raised to 8 steps, 3 rounds; grant 1 of 2${X}"
say "  ${D}     cut:  client-side headSha prefix filtering · the --limit paging machinery ·${X}"
say "  ${D}           the --settle window. Round 1's page-bound repair produced round 2's${X}"
say "  ${D}           findings in the same subsystem, so the SUBSYSTEM is the cut${X}"
say "  ${D}     kept: a full 40-char sha from git rev-parse, then gh run list --commit —${X}"
say "  ${D}           complete by construction. \"A run created after I looked\" becomes a${X}"
say "  ${D}           documented residual owned by the reader, not machinery in the script${X}"
hold 4
say ""
at step 7 "builder: applying the narrowing"
say "${O}⏺${X} ${B}Task${X}(builder — apply the narrowing, then a third cold agent on the smaller skill)"
say "  ${D}The bar the third round has to clear is the same bar. The skill got smaller;${X}"
say "  ${D}the review did not get shorter.${X}"
# Do NOT tear the block down here. The recording has to end while the session UI
# is still on screen; clearing it would put a bare shell prompt in the last frame
# and give the whole thing away.
hold 20   # must outlast the tape; if the script exits first, the shell prompt prints into the frame
