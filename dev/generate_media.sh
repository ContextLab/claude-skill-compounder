#!/usr/bin/env bash
# Record the README animation. Requires `vhs` (brew install vhs).
# The transcript it records is REAL, in two parts: dev/forge_demo.sh opens on a
# fail-then-fix that the lesson arm of hooks/repeat-gate.sh really caught -- the
# `gh run list --commit` dead end, the headSha filter that worked, the block the hook
# prints and the two lines `skillnote add --lesson` printed back -- and then replays
# the forge of `watch-ci-run` under the round diet: six steps, so TWO red-team rounds,
# both of which returned `6 blocking of 13` -- read off that forge's own round record.
# Blocking held rather than fell, so the recording ends on `skillforge escalate`
# refusing `--converging` and granting `--narrowed`, with the forge still open; there is
# no `done` because the ledger has none. The session chrome around it is redrawn rather
# than captured, and the subagents are not re-run.
# The status line is rendered by the real statusline/statusline.sh from state written
# by the real bin/skillforge, into a throwaway SKILL_COMPOUNDER_STATE.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v vhs >/dev/null || { echo "install vhs first: brew install vhs"; exit 1; }
command -v jq  >/dev/null || { echo "jq is required by skillforge and the status line"; exit 1; }
mkdir -p docs/media
vhs dev/forge.tape          # `Output` in the tape is relative to this cwd

# `Set Framerate 6` in the tape governs vhs's own capture, NOT the file it writes: the raw
# GIF comes out at about 25fps regardless (1355 frames over 54.2s on one run, 2026-09-05).
# gifsicle is what actually collapses it -- identical frames merge into longer delays, and
# a 61.2s recording goes 5193K/~1500 frames -> 2102K/73. Scrolling the transcript forces
# full-frame deltas, and that is where nearly all the remaining weight sits.
#
# `--lossy=55 --colors 96` was the setting until the recording grew, and it is worth
# knowing how fast that budget moves: on a 61.2s cut, 55/96 gave 2654K and 80/64 gave
# 2102K; on the 63.2s cut that actually shipped, 80/64 gave 2734K -- still over. 100/48
# is what fits, and the frames were read back at THAT setting: the transcript, the box and
# the status line are all legible. Check a frame, not just the number, before touching
# either value, and re-check the size after any change that lengthens the recording --
# gifsicle runs in place, so getting this wrong costs a whole re-record.
if command -v gifsicle >/dev/null; then
  before=$(wc -c < docs/media/forge.gif)
  gifsicle -O3 --lossy=100 --colors 48 docs/media/forge.gif -o docs/media/forge.gif
  echo "gifsicle: $((before / 1024))K -> $(( $(wc -c < docs/media/forge.gif) / 1024 ))K"
else
  echo "note: install gifsicle to shrink the GIF (brew install gifsicle)"
fi
echo "wrote docs/media/forge.gif"
