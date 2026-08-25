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

# `status` is READ-ONLY in zsh: it aliases $?. Assigning to it aborts with
# "read-only variable: status", the eval fails, and the whole forge segment renders
# empty with no error anywhere. The status line is invoked by whatever shell the user
# has, so the name is `fstate` here and nowhere near a shell special.
eval "$(jq -r '@sh "name=\(.name // "skill") summary=\(.summary // "") phase=\(.phase // "") step=\(.step // 0) steps=\(.steps // 1) fstate=\(.status // "active") finished=\(.finished // 0)"' "$FILE" 2>/dev/null)" || exit 0

now="${SKILLFORGE_NOW:-$(date +%s)}"

# Terminal states self-expire so the status line returns to normal unattended.
case "$fstate" in
  done)   [ $(( now - finished )) -gt "${SKILLFORGE_DONE_TTL:-30}" ] && { rm -f "$FILE"; exit 0; } ;;
  failed) [ $(( now - finished )) -gt "${SKILLFORGE_FAIL_TTL:-60}" ] && { rm -f "$FILE"; exit 0; } ;;
esac

M=$'\033[35m'; C=$'\033[1;36m'; G=$'\033[32m'; D=$'\033[2m'; R=$'\033[31m'; X=$'\033[0m'

TAIL_WIDTH="${SKILLFORGE_TAIL_WIDTH:-38}"

# Pad or truncate to an exact number of DISPLAY characters.
# Done in jq because its `length` counts codepoints: bash 3.2 substring indexing
# and printf's %-*.*s are both byte-based, so a multibyte tail would be cut
# mid-character and the width would still wobble.
pad_to() {
  jq -rn --arg s "$1" --argjson w "$2" '
    ($s | gsub("[\n\r\t]"; " ")) as $t
    | ($t | length) as $n
    | if $n > $w then ($t[0:($w - 1)] + "…")
      else $t + ((" " * ($w - $n)) // "")
      end' 2>/dev/null || printf '%s' "$1"
}

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
    if [ $i -eq $(( filled - 1 )) ] && [ "$fstate" = "active" ] && [ $(( now % 2 )) -eq 0 ]; then
      bar="${bar}▓"
    else
      bar="${bar}█"
    fi
  else
    bar="${bar}·"
  fi
  i=$(( i + 1 ))
done

case "$fstate" in
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
    case $(( now % 8 )) in
      # The DENSE braille set, not the light one. ⠋/⠙/⠹ are two or three lit
      # dots in a 2x4 cell: at terminal font sizes they render as a faint speck
      # that reads as a stray punctuation mark next to the words beside it.
      # ⣾/⣽/⣻ light six of eight dots, so the spinner is legible as a spinner.
      # Eight phases rather than ten, because that is the set's natural period.
      0) spin=⣾ ;; 1) spin=⣽ ;; 2) spin=⣻ ;; 3) spin=⢿ ;;
      4) spin=⡿ ;; 5) spin=⣟ ;; 6) spin=⣯ ;; *) spin=⣷ ;;
    esac
    # Alternate the tail: 10s of "what is happening now", 5s of "what the skill is".
    if [ -n "$summary" ] && [ $(( (now / 5) % 3 )) -eq 2 ]; then
      tail="$summary"
    else
      tail="$phase"
    fi
    # The segment MUST keep a constant display width. The tail alternates between
    # two strings of unrelated length, and a status line whose width changes makes
    # the host clear and redraw the whole line -- which reads to the eye as the
    # progress bar disappearing and reappearing on every update. Pad/truncate to a
    # fixed column count so each refresh overwrites in place instead.
    tail="$(pad_to "$tail" "$TAIL_WIDTH")"
    # Same reason, two more places the width would otherwise wobble: 100% is a
    # column wider than 40%, and step 10 is a column wider than step 9.
    step_w=${#steps}
    printf '%s' "${M}${spin} forge${X} ${C}${name}${X} ${G}▕${bar}▏${X} ${D}$(printf "%${step_w}d" "$step")/${steps} $(printf '%3d' "$pct")% · ${tail}${X}"
    ;;
esac
