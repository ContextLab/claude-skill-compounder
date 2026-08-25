#!/usr/bin/env bash
# Mechanically validate a session handoff against the template in SKILL.md.
#
# Usage: check-handoff.sh <handoff.md> [SKILL.md]
#
# Exit 0 when the handoff is resumable. Exit 1 otherwise, printing one
# "REJECT <RULE> <detail>" line per problem. The mandatory section list and the
# placeholder tokens are both read out of the SKILL.md template, so the validator
# and the documented template cannot drift apart.
set -uo pipefail

HANDOFF="${1:-}"
SKILL_MD="${2:-$(cd "$(dirname "$0")/.." && pwd)/SKILL.md}"

if [ -z "$HANDOFF" ] || [ ! -f "$HANDOFF" ]; then
  echo "usage: check-handoff.sh <handoff.md> [SKILL.md]" >&2
  exit 2
fi
if [ ! -f "$SKILL_MD" ]; then
  echo "cannot read SKILL.md at $SKILL_MD" >&2
  exit 2
fi

# The template block is fenced with four backticks so the inner three-backtick
# fences survive. Toggle only on four.
template_block() {
  awk '
    /^## Template[ \t]*$/ && !fence { intpl = 1; next }
    intpl && /^````/      { fence = !fence; next }
    intpl && !fence && /^## / { intpl = 0 }
    intpl && fence        { print }
  ' "$SKILL_MD"
}

TEMPLATE="$(template_block)"
if [ -z "$TEMPLATE" ]; then
  echo "no template block found in $SKILL_MD" >&2
  exit 2
fi

REQUIRED="$(printf '%s\n' "$TEMPLATE" | grep '^## ' || true)"
PLACEHOLDERS="$(printf '%s\n' "$TEMPLATE" | grep -o '<[^<>]*>' | sort -u || true)"

rc=0
reject() { rc=1; echo "REJECT $1 $2"; }

# Body of one section of the handoff: everything between its heading and the next.
section_body() {
  awk -v h="$1" '
    $0 == h { found = 1; next }
    found && /^## / { exit }
    found { print }
  ' "$HANDOFF"
}

has_content() { printf '%s\n' "$1" | grep -q '[^[:space:]]'; }

# Non-blank content lines that are not part of a fenced code block.
prose_lines() {
  printf '%s\n' "$1" | awk '
    /^```/ { fence = !fence; next }
    !fence && /[^[:space:]]/ { print }
  '
}

# Non-blank lines inside fenced code blocks.
fenced_lines() {
  printf '%s\n' "$1" | awk '
    /^```/ { fence = !fence; next }
    fence && /[^[:space:]]/ { print }
  '
}

# --- R1 / R2: every mandatory section present and non-empty ------------------
while IFS= read -r heading; do
  [ -n "$heading" ] || continue
  if ! grep -Fxq "$heading" "$HANDOFF"; then
    reject MISSING_SECTION "$heading"
    continue
  fi
  body="$(section_body "$heading")"
  if ! has_content "$body"; then
    reject EMPTY_SECTION "$heading"
  fi
done <<< "$REQUIRED"

# --- R3: no template placeholder survived ------------------------------------
while IFS= read -r ph; do
  [ -n "$ph" ] || continue
  if grep -Fq "$ph" "$HANDOFF"; then
    reject PLACEHOLDER "$ph"
  fi
done <<< "$PLACEHOLDERS"

# --- R4 / R5: State carries a real branch and a real commit ------------------
state="$(section_body '## State')"
printf '%s\n' "$state" | grep -Eq '^branch: *[^[:space:]]+' \
  || reject NO_BRANCH "## State needs a 'branch: <name>' line"
printf '%s\n' "$state" | grep -Eq '^commit: *[0-9a-f]{7,40} *$' \
  || reject NO_SHA "## State needs a 'commit: <sha>' line with a 7-40 char hex sha"

# --- R6: the resume command is an actual runnable command --------------------
resume="$(section_body '## Resume command')"
if [ -z "$(fenced_lines "$resume")" ]; then
  reject NO_RESUME_COMMAND "## Resume command needs a fenced, copy-pasteable command"
fi

# --- R7: a broken thing is reported verbatim, not summarised -----------------
broken="$(section_body '## Broken')"
if [ "$(prose_lines "$broken" | tr -d '[:space:]')" != "None." ]; then
  if [ -z "$(fenced_lines "$broken")" ]; then
    reject SUMMARISED_ERROR "## Broken needs the error output pasted in a fence"
  fi
  printf '%s\n' "$broken" | grep -Eq '^repro: *[^[:space:]]+' \
    || reject NO_REPRO "## Broken needs a 'repro: <command>' line"
fi

exit $rc
