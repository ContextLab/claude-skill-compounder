#!/usr/bin/env bash
# Renders the live "skill forge" animation segment for the Claude Code status line.
# Reads the status-line payload JSON on stdin; prints one segment, or nothing when
# no forge is active. The animation comes from the status line's refreshInterval
# re-running this roughly once a second.
#
# SKILLFORGE_NOW pins the clock so the animation can be exercised deterministically.
set -uo pipefail

DIR="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}/forge"
command -v jq >/dev/null 2>&1 || exit 0

cat >/dev/null 2>&1   # payload is not needed: state is a single file, not session-keyed

FILE="$DIR/current.json"
[ -f "$FILE" ] || exit 0

eval "$(jq -r '@sh "name=\(.name // "skill") summary=\(.summary // "") phase=\(.phase // "") step=\(.step // 0) steps=\(.steps // 1) status=\(.status // "active") finished=\(.finished // 0)"' "$FILE" 2>/dev/null)" || exit 0

now="${SKILLFORGE_NOW:-$(date +%s)}"

# Terminal states self-expire so the status line returns to normal unattended.
case "$status" in
  done)   [ $(( now - finished )) -gt "${SKILLFORGE_DONE_TTL:-30}" ] && { rm -f "$FILE"; exit 0; } ;;
  failed) [ $(( now - finished )) -gt "${SKILLFORGE_FAIL_TTL:-60}" ] && { rm -f "$FILE"; exit 0; } ;;
esac

M=$'\033[35m'; C=$'\033[1;36m'; G=$'\033[32m'; D=$'\033[2m'; R=$'\033[31m'; X=$'\033[0m'

WIDTH="${SKILLFORGE_BAR_WIDTH:-12}"
[ "$steps" -lt 1 ] && steps=1
[ "$step" -gt "$steps" ] && step=$steps
filled=$(( step * WIDTH / steps ))
pct=$(( step * 100 / steps ))
bar=""
i=0
while [ $i -lt "$WIDTH" ]; do
  if [ $i -lt $filled ]; then
    # Pulse the leading edge so the bar reads as live even between steps.
    # NOTE: braces are required — bash folds the multibyte glyph into the var name.
    if [ $i -eq $(( filled - 1 )) ] && [ "$status" = "active" ] && [ $(( now % 2 )) -eq 0 ]; then
      bar="${bar}▓"
    else
      bar="${bar}█"
    fi
  else
    bar="${bar}·"
  fi
  i=$(( i + 1 ))
done

case "$status" in
  done)
    printf '%s' "${G}✓${X} ${M}forge${X} ${C}${name}${X} ${G}▕${bar}▏${X} ${D}forged · ${phase}${X}"
    ;;
  failed)
    printf '%s' "${R}✗${X} ${M}forge${X} ${C}${name}${X} ${D}▕${bar}▏${X} ${R}abandoned${X} ${D}· ${phase}${X}"
    ;;
  *)
    # A case, not an array or `cut -c`: braille glyphs are multibyte, cut -c is
    # locale-dependent, bash 3.2 substring indexing is byte-based, and zsh arrays
    # are 1-indexed. A case statement is correct under every one of those.
    case $(( now % 10 )) in
      0) spin=⠋ ;; 1) spin=⠙ ;; 2) spin=⠹ ;; 3) spin=⠸ ;; 4) spin=⠼ ;;
      5) spin=⠴ ;; 6) spin=⠦ ;; 7) spin=⠧ ;; 8) spin=⠇ ;; *) spin=⠏ ;;
    esac
    # Alternate the tail: 10s of "what is happening now", 5s of "what the skill is".
    if [ -n "$summary" ] && [ $(( (now / 5) % 3 )) -eq 2 ]; then
      tail="$summary"
    else
      tail="$phase"
    fi
    printf '%s' "${M}${spin} forge${X} ${C}${name}${X} ${G}▕${bar}▏${X} ${D}${step}/${steps} ${pct}% · ${tail}${X}"
    ;;
esac
