#!/usr/bin/env bash
# Record the README animation. Requires `vhs` (brew install vhs).
# The transcript it records is REAL: dev/forge_demo.sh replays the actual forge of
# `parallel-agents-one-codebase`, including the findings each red-team round
# returned. The session chrome around it is redrawn rather than captured, and the
# subagents are not re-run. The status line is rendered by the real
# statusline/statusline.sh from state written by the real bin/skillforge.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v vhs >/dev/null || { echo "install vhs first: brew install vhs"; exit 1; }
command -v jq  >/dev/null || { echo "jq is required by skillforge and the status line"; exit 1; }
mkdir -p docs/media
vhs dev/forge.tape          # `Output` in the tape is relative to this cwd

# The tape records at 6fps because the status line only changes once a second --
# anything faster just stores duplicate frames. gifsicle then drops the rest:
# scrolling the transcript forces full-frame deltas, which is most of the weight.
if command -v gifsicle >/dev/null; then
  before=$(wc -c < docs/media/forge.gif)
  gifsicle -O3 --lossy=55 --colors 96 docs/media/forge.gif -o docs/media/forge.gif
  echo "gifsicle: $((before / 1024))K -> $(( $(wc -c < docs/media/forge.gif) / 1024 ))K"
else
  echo "note: install gifsicle to shrink the GIF (brew install gifsicle)"
fi
echo "wrote docs/media/forge.gif"
