#!/usr/bin/env bash
# Mechanically validate a session handoff against the template in SKILL.md.
#
# Usage: check-handoff.sh <handoff.md> [SKILL.md]
#
# Exit 0 when the handoff is resumable, 1 with one "REJECT <RULE> <detail>" line per
# problem, 2 when the inputs themselves cannot be read.
#
# Nothing about the document's shape is hardcoded here. The mandatory section list, the
# placeholder tokens, and the names of the sections carrying special rules are all read
# out of the SKILL.md template. Sections are located by marker (the state section is
# whichever one holds a "branch:" line; the broken section is whichever holds "repro:"),
# so renaming a section in the template renames it here too.
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
HANDOFF_DIR="$(cd "$(dirname "$HANDOFF")" && pwd)"

# The template is fenced with four backticks so its own three-backtick fences survive.
TEMPLATE="$(awk '
  /^## Template[ \t]*$/ && !fence { intpl = 1; next }
  intpl && /^````/      { fence = !fence; next }
  intpl && !fence && /^## / { intpl = 0 }
  intpl && fence        { print }
' "$SKILL_MD")"
if [ -z "$TEMPLATE" ]; then
  echo "no template block found in $SKILL_MD" >&2
  exit 2
fi

REQUIRED="$(printf '%s\n' "$TEMPLATE" | grep '^## ' || true)"
PLACEHOLDERS="$(printf '%s\n' "$TEMPLATE" | grep -o '<[^<>]*>' | sort -u || true)"

# Heading of the template section containing a line matching the given regex.
template_section_matching() {
  printf '%s\n' "$TEMPLATE" | awk -v re="$1" '
    /^## / { h = $0; next }
    h != "" && $0 ~ re { print h; exit }
  '
}

STATE_SECTION="$(template_section_matching '^branch:')"
RESUME_SECTION="$(template_section_matching '^cd ')"
BROKEN_SECTION="$(template_section_matching '^repro:')"
for pair in "branch:|$STATE_SECTION" "cd |$RESUME_SECTION" "repro:|$BROKEN_SECTION"; do
  if [ -z "${pair#*|}" ]; then
    echo "template in $SKILL_MD has no section carrying a '${pair%%|*}' marker" >&2
    exit 2
  fi
done

rc=0
reject() { rc=1; echo "REJECT $1 $2"; }

section_body() {
  awk -v h="$1" '
    $0 == h { found = 1; next }
    found && /^## / { exit }
    found { print }
  ' "$HANDOFF"
}

has_content() { printf '%s\n' "$1" | grep -q '[^[:space:]]'; }

# Non-blank lines outside fenced code blocks.
prose_lines() {
  printf '%s\n' "$1" | awk '
    /^```/ { fence = !fence; next }
    !fence && /[^[:space:]]/ { print }
  '
}

# Non-blank, non-comment lines inside fenced code blocks.
fenced_lines() {
  printf '%s\n' "$1" | awk '
    /^```/ { fence = !fence; next }
    fence && /[^[:space:]]/ && $0 !~ /^[[:space:]]*#/ { print }
  '
}

# Whole prose content of a section, reduced to one comparable token.
canonical_prose() {
  prose_lines "$1" \
    | sed -e 's/^[[:space:]]*[-*][[:space:]]*//' -e 's/^[[:space:]]*[0-9][0-9]*\.[[:space:]]*//' \
    | tr -d '[:space:]' | tr 'A-Z' 'a-z' | sed 's/[.,;:!?]*$//'
}

NON_ANSWERS="tbd todo n/a na seeabove seebelow asabove asbefore sameasbefore unknown nothing ? - various misc pending"

# --- every mandatory section present, non-empty, and actually answered ------------
while IFS= read -r heading; do
  [ -n "$heading" ] || continue
  if ! grep -Fxq "$heading" "$HANDOFF"; then
    reject MISSING_SECTION "$heading"
    continue
  fi
  body="$(section_body "$heading")"
  if ! has_content "$body"; then
    reject EMPTY_SECTION "$heading"
    continue
  fi
  canon="$(canonical_prose "$body")"
  if [ -n "$canon" ]; then
    for na in $NON_ANSWERS; do
      if [ "$canon" = "$na" ]; then
        reject NON_ANSWER "$heading says '$canon'; write the answer or the literal None."
        break
      fi
    done
  fi
done <<< "$REQUIRED"

# --- no template placeholder survived ---------------------------------------------
while IFS= read -r ph; do
  [ -n "$ph" ] || continue
  grep -Fq "$ph" "$HANDOFF" && reject PLACEHOLDER "$ph"
done <<< "$PLACEHOLDERS"

# --- nothing was trimmed ----------------------------------------------------------
if grep -Eniq '\(truncated\)|\[truncated\]|\.\.\. *\(|\[snip\]|<snip>|snipped|elided|output omitted|rest omitted|and so on|etc\.' "$HANDOFF"; then
  reject TRUNCATED_OUTPUT "an elision marker appears; paste the output in full"
fi
if grep -Eq '^[[:space:]]*(\.\.\.|…)[[:space:]]*$' "$HANDOFF"; then
  reject TRUNCATED_OUTPUT "a bare ellipsis line appears; paste the output in full"
fi

# --- the recorded state names a real branch and a real commit ---------------------
state="$(section_body "$STATE_SECTION")"
branch="$(printf '%s\n' "$state" | sed -n 's/^branch:[[:space:]]*//p' | head -1)"
sha="$(printf '%s\n' "$state" | sed -n 's/^commit:[[:space:]]*//p' | head -1)"

if [ -z "$branch" ]; then
  reject NO_BRANCH "$STATE_SECTION needs a 'branch: <name>' line"
elif [ "$branch" = "HEAD" ]; then
  reject BRANCH_IS_HEAD "branch: HEAD means detached; record 'branch: (detached)' instead"
fi

verify_sha=""
if [ -z "$sha" ]; then
  reject NO_SHA "$STATE_SECTION needs a 'commit: <sha>' line"
elif printf '%s' "$sha" | grep -Eq '^[0-9a-f]{7,40}$'; then
  verify_sha="$sha"
elif [ "$sha" != "none (not a git repository)" ]; then
  reject NO_SHA "commit: '$sha' is neither a 7-40 char hex sha nor 'none (not a git repository)'"
fi

# --- the resume command is anchored, runnable, and lands on the recorded sha -------
resume="$(section_body "$RESUME_SECTION")"
resume_cmds="$(fenced_lines "$resume")"
if [ -z "$resume_cmds" ]; then
  reject NO_RESUME_COMMAND "$RESUME_SECTION needs a fenced command, not prose or a comment"
else
  repo_path="$(printf '%s\n' "$resume_cmds" \
    | sed -n 's/^[[:space:]]*cd[[:space:]][[:space:]]*//p' | head -1 \
    | sed -e 's/[[:space:]]*&&.*//' -e 's/[[:space:]]*;.*//' -e 's/^"//' -e 's/"$//' \
          -e "s/^'//" -e "s/'\$//")"
  if [ -z "$repo_path" ]; then
    reject RESUME_NOT_ANCHORED "$RESUME_SECTION must start by cd-ing to the working directory"
  else
    case "$repo_path" in
      /*) abs_path="$repo_path" ;;
      ~*) abs_path="${repo_path/#\~/$HOME}" ;;
      *)  abs_path="$HANDOFF_DIR/$repo_path" ;;
    esac
    if [ ! -d "$abs_path" ]; then
      reject UNREACHABLE_REPO "the resume command cd's to '$repo_path', which does not exist"
    elif [ -n "$verify_sha" ]; then
      if ! printf '%s\n' "$resume_cmds" | grep -Fq "$verify_sha"; then
        reject RESUME_MISSING_SHA "the resume command must check out $verify_sha; a branch name moves"
      fi
      if git -C "$abs_path" rev-parse --git-dir >/dev/null 2>&1; then
        git -C "$abs_path" cat-file -e "${verify_sha}^{commit}" 2>/dev/null \
          || reject UNKNOWN_COMMIT "$verify_sha is not a commit in $repo_path"
      fi
    fi
  fi
fi

# --- a broken thing is reported verbatim, not summarised ---------------------------
broken="$(section_body "$BROKEN_SECTION")"
if [ "$(canonical_prose "$broken")" != "none" ]; then
  if [ -z "$(fenced_lines "$broken")" ]; then
    reject SUMMARISED_ERROR "$BROKEN_SECTION needs the error output pasted in a fence"
  fi
  printf '%s\n' "$broken" | grep -Eq '^repro:[[:space:]]*[^[:space:]]+' \
    || reject NO_REPRO "$BROKEN_SECTION needs a 'repro: <command>' line"
fi

exit $rc
