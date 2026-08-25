#!/usr/bin/env bash
# Mechanically validate a session handoff against the template in SKILL.md.
#
# Usage: check-handoff.sh [--minimal] <handoff.md> [SKILL.md]
#
#   --minimal   Judge only the two sections the emergency fallback writes (the one holding
#               branch/commit and the one holding the resume command). Sections that are
#               absent are listed on stderr as remaining work rather than rejected, so a
#               handoff written with no context left can still pass.
#
# Exit 0 when the handoff is resumable, 1 with one "REJECT <RULE> <detail>" line per
# problem, 2 when the inputs themselves cannot be read.
#
# Nothing about the document's shape is hardcoded. The mandatory section list, the
# placeholder tokens, and the sections carrying special rules are read out of the SKILL.md
# template, and the special ones are located by marker (state is whichever section holds a
# "branch:" line, broken is whichever holds "repro:"), so a rename carries through.
#
# Parsing is fence-aware at every level, because this document's whole purpose is to hold
# pasted output: a "## " line inside a code fence is content, not a heading. Fences nest by
# length, so a four-backtick block may contain three-backtick blocks.
set -uo pipefail

MINIMAL=0
if [ "${1:-}" = "--minimal" ]; then MINIMAL=1; shift; fi

HANDOFF="${1:-}"
SKILL_MD="${2:-$(cd "$(dirname "$0")/.." && pwd)/SKILL.md}"

if [ -z "$HANDOFF" ] || [ ! -f "$HANDOFF" ]; then
  echo "usage: check-handoff.sh [--minimal] <handoff.md> [SKILL.md]" >&2
  exit 2
fi
if [ ! -f "$SKILL_MD" ]; then
  echo "cannot read SKILL.md at $SKILL_MD" >&2
  exit 2
fi
HANDOFF_DIR="$(cd "$(dirname "$HANDOFF")" && pwd)"

# Shared fence tracker. Returns 1 for a fence delimiter line, and keeps `fence` current.
# A fence closes only on a run of backticks at least as long as the one that opened it.
FENCE_AWK='
function fence_toggle(line,   n) {
  if (match(line, /^`+/)) {
    n = RLENGTH
    if (n < 3) return 0
    if (!fence) { fence = 1; flen = n; return 1 }
    if (n >= flen) { fence = 0; return 1 }
  }
  return 0
}
'

headings_of() {  # file
  awk "$FENCE_AWK"'
    { if (fence_toggle($0)) next
      if (!fence && $0 ~ /^## /) print }
  ' "$1"
}

section_of() {  # file, heading
  awk -v h="$2" "$FENCE_AWK"'
    { isf = fence_toggle($0)
      if (!fence && !isf && !found && $0 == h) { found = 1; next }
      if (found && !fence && !isf && $0 ~ /^## /) exit
      if (found) print }
  ' "$1"
}

# The template is the first fenced block inside the "## Template" section. The outer fence
# is stripped; any shorter fences inside it are kept.
TEMPLATE="$(section_of "$SKILL_MD" '## Template' | awk '
  { if (match($0, /^`+/) && RLENGTH >= 3) {
      n = RLENGTH
      if (!fence) { fence = 1; flen = n; next }
      if (n >= flen) { fence = 0; next }
    }
    if (fence) print }
')"
if [ -z "$TEMPLATE" ]; then
  echo "no template block found in $SKILL_MD" >&2
  exit 2
fi

tmpl() { printf '%s\n' "$TEMPLATE"; }
REQUIRED="$(tmpl | awk "$FENCE_AWK"'{ if (fence_toggle($0)) next; if (!fence && $0 ~ /^## /) print }')"
PLACEHOLDERS="$(tmpl | grep -o '<[^<>]*>' | sort -u || true)"

# Heading of the template section containing a line matching the regex. Ambiguity is a
# template defect, not something to resolve by picking the first match.
template_section_matching() {
  local hits
  hits="$(tmpl | awk -v re="$1" "$FENCE_AWK"'
    { isf = fence_toggle($0)
      if (!fence && !isf && $0 ~ /^## /) { h = $0; next }
      if (h != "" && $0 ~ re) { print h; h = "" } }')"
  local n; n="$(printf '%s' "$hits" | grep -c . || true)"
  if [ "$n" -gt 1 ]; then
    echo "template in $SKILL_MD has $n sections carrying a '$1' marker; it must be unique" >&2
    exit 2
  fi
  printf '%s' "$hits"
}

STATE_SECTION="$(template_section_matching '^branch:')" || exit 2
RESUME_SECTION="$(template_section_matching '^cd ')" || exit 2
BROKEN_SECTION="$(template_section_matching '^repro:')" || exit 2
for pair in "branch:|$STATE_SECTION" "cd |$RESUME_SECTION" "repro:|$BROKEN_SECTION"; do
  if [ -z "${pair#*|}" ]; then
    echo "template in $SKILL_MD has no section carrying a '${pair%%|*}' marker" >&2
    exit 2
  fi
done

rc=0
reject() { rc=1; echo "REJECT $1 $2"; }

PRESENT="$(headings_of "$HANDOFF")"
have() { printf '%s\n' "$PRESENT" | grep -Fxq "$1"; }
body_of() { section_of "$HANDOFF" "$1"; }
has_content() { printf '%s\n' "$1" | grep -q '[^[:space:]]'; }

prose_lines() {  # non-blank lines outside fences
  printf '%s\n' "$1" | awk "$FENCE_AWK"'
    { if (fence_toggle($0)) next
      if (!fence && $0 ~ /[^[:space:]]/) print }'
}

fenced_lines() {  # non-blank, non-comment lines inside fences
  printf '%s\n' "$1" | awk "$FENCE_AWK"'
    { if (fence_toggle($0)) next
      if (fence && $0 ~ /[^[:space:]]/ && $0 !~ /^[[:space:]]*#/) print }'
}

canonical_prose() {
  prose_lines "$1" \
    | sed -e 's/^[[:space:]]*[-*][[:space:]]*//' -e 's/^[[:space:]]*[0-9][0-9]*\.[[:space:]]*//' \
    | tr -d '[:space:]' | tr 'A-Z' 'a-z' | sed 's/[.,;:!?]*$//'
}

NON_ANSWERS="tbd todo n/a na seeabove seebelow asabove asbefore sameasbefore unknown nothing ? - various misc pending"

# --- sections present, non-empty, and actually answered ---------------------------
missing_for_later=""
while IFS= read -r heading; do
  [ -n "$heading" ] || continue
  if ! have "$heading"; then
    if [ "$MINIMAL" -eq 1 ] && [ "$heading" != "$STATE_SECTION" ] && [ "$heading" != "$RESUME_SECTION" ]; then
      missing_for_later="$missing_for_later  $heading"$'\n'
    else
      reject MISSING_SECTION "$heading"
    fi
    continue
  fi
  body="$(body_of "$heading")"
  if ! has_content "$body"; then
    reject EMPTY_SECTION "$heading"
    continue
  fi
  canon="$(canonical_prose "$body")"
  if [ -n "$canon" ]; then
    for na in $NON_ANSWERS; do
      [ "$canon" = "$na" ] || continue
      reject NON_ANSWER "$heading says '$canon'; write the answer or the literal None."
      break
    done
  fi
done <<< "$REQUIRED"

while IFS= read -r ph; do
  [ -n "$ph" ] || continue
  grep -Fq "$ph" "$HANDOFF" && reject PLACEHOLDER "$ph"
done <<< "$PLACEHOLDERS"

if grep -Eniq '\(truncated\)|\[truncated\]|\.\.\. *\(|\[snip\]|<snip>|snipped|elided|output omitted|rest omitted|and so on|etc\.' "$HANDOFF"; then
  reject TRUNCATED_OUTPUT "an elision marker appears; paste the output in full"
fi
if grep -Eq '^[[:space:]]*(\.\.\.|…)[[:space:]]*$' "$HANDOFF"; then
  reject TRUNCATED_OUTPUT "a bare ellipsis line appears; paste the output in full"
fi

# --- resolve the working directory the resume command names ------------------------
# Everything about the recorded commit is judged against this directory, so it is
# resolved first. "unreachable" is a rejection, never a reason to skip a check.
repo_kind="none"; abs_path=""; resume_cmds=""
if have "$RESUME_SECTION"; then
  resume_cmds="$(fenced_lines "$(body_of "$RESUME_SECTION")")"
  if [ -z "$resume_cmds" ]; then
    reject NO_RESUME_COMMAND "$RESUME_SECTION needs a fenced command, not prose or a comment"
  else
    repo_path="$(printf '%s\n' "$resume_cmds" \
      | sed -n 's/^[[:space:]]*cd[[:space:]][[:space:]]*//p' | head -1 \
      | sed -e 's/[[:space:]]*&&.*//' -e 's/[[:space:]]*;.*//' \
            -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//" -e 's/\\ / /g')"
    if [ -z "$repo_path" ]; then
      reject RESUME_NOT_ANCHORED "$RESUME_SECTION must start by cd-ing to the working directory"
    else
      case "$repo_path" in
        /*)   abs_path="$repo_path" ;;
        "~"*) abs_path="${HOME}${repo_path#\~}" ;;
        *)    abs_path="" ;;
      esac
      if [ -z "$abs_path" ]; then
        reject RESUME_PATH_NOT_ABSOLUTE "the resume command cd's to '$repo_path'; a relative path depends on where it is pasted, so write the absolute one"
      elif [ ! -d "$abs_path" ]; then
        reject UNREACHABLE_REPO "the resume command cd's to '$repo_path', which does not exist"
      elif ! git -C "$abs_path" rev-parse --git-dir >/dev/null 2>&1; then
        repo_kind="notrepo"
      elif git -C "$abs_path" rev-parse --verify --quiet HEAD >/dev/null 2>&1; then
        repo_kind="repo"
      else
        repo_kind="unborn"
      fi
    fi
  fi
else
  reject MISSING_SECTION "$RESUME_SECTION"
fi

# --- the recorded state must match what that directory actually is -----------------
if have "$STATE_SECTION"; then
  state="$(body_of "$STATE_SECTION")"
  branch="$(printf '%s\n' "$state" | sed -n 's/^branch:[[:space:]]*//p' | head -1)"
  sha="$(printf '%s\n' "$state" | sed -n 's/^commit:[[:space:]]*//p' | head -1)"
  uncommitted="$(printf '%s\n' "$state" | sed -n 's/^uncommitted:[[:space:]]*//p' | head -1)"

  if [ -z "$branch" ]; then
    reject NO_BRANCH "$STATE_SECTION needs a 'branch: <name>' line"
  elif [ "$branch" = "HEAD" ]; then
    reject BRANCH_IS_HEAD "branch: HEAD means detached; record 'branch: (detached)' instead"
  elif [ "$repo_kind" = "notrepo" ] && [ "$branch" != "none (not a git repository)" ]; then
    reject BRANCH_CONTRADICTS_REPO "'$repo_path' is not a git repository, so branch: must be 'none (not a git repository)', not '$branch'"
  elif [ "$repo_kind" = "repo" ] && [ "$branch" = "none (not a git repository)" ]; then
    reject BRANCH_CONTRADICTS_REPO "'$repo_path' is a git repository, so branch: cannot be 'none (not a git repository)'"
  fi

  if [ -z "$sha" ]; then
    reject NO_SHA "$STATE_SECTION needs a 'commit: <sha>' line"
  elif printf '%s' "$sha" | grep -Eq '^[0-9a-f]{40}$|^[0-9a-f]{64}$'; then
    case "$repo_kind" in
      repo)
        git -C "$abs_path" cat-file -e "${sha}^{commit}" 2>/dev/null \
          || reject UNKNOWN_COMMIT "$sha is not a commit in '$repo_path'"
        printf '%s\n' "$resume_cmds" | grep -Fq "$sha" \
          || reject RESUME_MISSING_SHA "the resume command must name $sha; a branch name moves"
        printf '%s\n' "$resume_cmds" | grep -E 'git[[:space:]]+(checkout|switch|reset)' | grep -Fq "$sha" \
          || reject RESUME_DOES_NOT_CHECKOUT "the resume command must git checkout or git switch to $sha, not merely mention it"
        ;;
      *)
        reject UNVERIFIABLE_COMMIT "commit: $sha cannot be checked because '$repo_path' is not a reachable git repository; a sha nobody can verify is not state"
        ;;
    esac
  elif [ "$sha" = "none (not a git repository)" ]; then
    [ "$repo_kind" = "notrepo" ] \
      || reject UNVERIFIABLE_COMMIT "commit: says '$sha' but '$repo_path' is a git repository"
  elif [ "$sha" = "none (no commits yet)" ]; then
    [ "$repo_kind" = "unborn" ] \
      || reject UNVERIFIABLE_COMMIT "commit: says '$sha' but '$repo_path' has commits, or is not a repository"
  else
    reject NO_SHA "commit: '$sha' is not a full 40-char sha, 'none (not a git repository)', or 'none (no commits yet)'"
  fi

  # The uncommitted work is the one thing a fresh clone cannot re-derive.
  if [ -z "$uncommitted" ]; then
    reject NO_UNCOMMITTED_LINE "$STATE_SECTION needs an 'uncommitted: <patch file>' line, or 'uncommitted: none'"
  elif [ "$uncommitted" = "none" ]; then
    printf '%s\n' "$resume_cmds" | grep -q 'git[[:space:]]\+apply' \
      && reject STRAY_PATCH_APPLY "the resume command applies a patch, but uncommitted: says none"
  else
    case "$uncommitted" in
      /*) patch_abs="$uncommitted" ;;
      *)  patch_abs="$HANDOFF_DIR/$(basename "$uncommitted")" ;;
    esac
    [ -f "$patch_abs" ] \
      || reject MISSING_PATCH "uncommitted: names '$uncommitted', which is not beside this handoff"
    printf '%s\n' "$resume_cmds" | grep -q 'git[[:space:]]\+apply' \
      || reject NO_PATCH_APPLY "uncommitted work was saved to '$uncommitted' but the resume command never applies it"
  fi
else
  reject MISSING_SECTION "$STATE_SECTION"
fi

# --- a broken thing is reported verbatim, not summarised ---------------------------
if [ "$MINIMAL" -eq 0 ] || have "$BROKEN_SECTION"; then
  if have "$BROKEN_SECTION"; then
    broken="$(body_of "$BROKEN_SECTION")"
    if [ "$(canonical_prose "$broken")" != "none" ]; then
      [ -n "$(fenced_lines "$broken")" ] \
        || reject SUMMARISED_ERROR "$BROKEN_SECTION needs the error output pasted in a fence"
      repro="$(printf '%s\n' "$broken" | sed -n 's/^repro:[[:space:]]*//p' | head -1)"
      if [ -z "$repro" ]; then
        reject NO_REPRO "$BROKEN_SECTION needs a 'repro: <command>' line"
      else
        case "$repro" in
          true|false|:|"exit 0"|echo\ *)
            reject TRIVIAL_REPRO "repro: '$repro' does not reproduce anything" ;;
        esac
      fi
    fi
  fi
fi

if [ "$MINIMAL" -eq 1 ] && [ -n "$missing_for_later" ]; then
  printf 'minimal handoff accepted. Still to write, in this order:\n%s' "$missing_for_later" >&2
fi

exit $rc
