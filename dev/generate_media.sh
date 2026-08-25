#!/usr/bin/env bash
# Record the README animation. Requires `vhs` (brew install vhs).
# The forge it records is fabricated (dev/forge_demo.sh) — no real transcript,
# path, or skill name is ever captured.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v vhs >/dev/null || { echo "install vhs first: brew install vhs"; exit 1; }
command -v jq  >/dev/null || { echo "jq is required by skillforge and the status line"; exit 1; }
mkdir -p docs/media
vhs dev/forge.tape          # `Output` in the tape is relative to this cwd
echo "wrote docs/media/forge.gif"
