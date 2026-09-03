#!/usr/bin/env bash
# One-line installer:
#   curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh | bash
# Pinned to a release (recommended once a tag exists):
#   SKILL_COMPOUNDER_REF=v0.3.0 bash -c "$(curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh)"
# Or from a clone:  ./install.sh
#
# THE WHOLE FILE IS ONE BRACE GROUP AND EVERY PATH ENDS IN `exit`, and here that is
# load-bearing rather than housekeeping. `--update` runs `git` against the very checkout
# this script is being read out of, and bash reads a script lazily by byte offset: rewrite
# the file mid-run and bash resumes at its saved offset in whatever the file now holds.
# The brace group forces a single parse before anything runs, and the closing `exit` on
# every path stops bash resuming past it. Both halves are required.
#
# `set -e` is on, so no branch may be written as `[ cond ] && var=1` at statement level:
# when the test fails the list's status is 1 and the shell exits. Every one of those below
# is an explicit `if` for that reason.
set -euo pipefail
{

REPO_URL="https://github.com/ContextLab/claude-skill-compounder.git"
DEFAULT_HOME="$HOME/.claude/skill-compounder-app"
# The checkout this script manages on the user's behalf. A clone the user made themselves
# is theirs, and the two moving flags below refuse to touch it.
MANAGED_HOME="${CLAUDE_SKILL_COMPOUNDER_APP:-$DEFAULT_HOME}"

# What to check out. `main` for now; the README recommends the pinned form once a tag
# exists. A tag is what makes an install reproducible: `main` is whatever was pushed to it
# this morning, so two people running the same command get different code.
REF="${SKILL_COMPOUNDER_REF:-main}"
REF_GIVEN=0
if [ -n "${SKILL_COMPOUNDER_REF:-}" ]; then REF_GIVEN=1; fi
DO_UPDATE=0
if [ "${SKILL_COMPOUNDER_UPDATE:-0}" = "1" ]; then DO_UPDATE=1; fi
DO_ROLLBACK=0

# Same convention uninstall.sh uses, and for the same reason: `curl … | bash` has no
# checkout around it, so the state directory is where the two scripts agree to look.
STATE_DIR="${CLAUDE_SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
REF_RECORD="install-ref"

# Everything not ours goes on to scripts/setup.py untouched.
PASS=()

usage() {
  cat <<'USAGE'
install.sh [--ref <tag|branch|sha>] [--update] [--rollback] [setup.py options...]

  --ref <r>    check out <r> instead of the default (env: SKILL_COMPOUNDER_REF)
  --update     fetch and move the managed checkout to --ref (env: SKILL_COMPOUNDER_UPDATE=1)
  --rollback   return the managed checkout to the ref recorded before the last update

A plain re-run re-wires the current checkout and does NOT move it. Every other option is
passed straight through to scripts/setup.py: --uninstall, --claude-dir, --bin-dir,
--state-dir, --no-doctrine, --enable-review, --disable-review.

Session review (a detached `claude -p` call after long sessions) is OFF by default, even
piped through bash with no tty. Turn it on explicitly with --enable-review (or
SKILL_COMPOUNDER_ENABLE_REVIEW=1); --disable-review turns it back off.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --ref)
      shift
      if [ $# -eq 0 ]; then echo "error: --ref needs a tag, branch or commit." >&2; exit 2; fi
      REF="$1"; REF_GIVEN=1 ;;
    --ref=*)
      REF="${1#--ref=}"; REF_GIVEN=1
      if [ -z "$REF" ]; then echo "error: --ref needs a tag, branch or commit." >&2; exit 2; fi ;;
    --update)   DO_UPDATE=1 ;;
    --rollback) DO_ROLLBACK=1 ;;
    # Read, not consumed: setup.py still needs it, and so do we, to find the ref record.
    --state-dir)
      shift
      if [ $# -eq 0 ]; then echo "error: --state-dir needs a directory." >&2; exit 2; fi
      STATE_DIR="$1"; PASS[${#PASS[@]}]="--state-dir"; PASS[${#PASS[@]}]="$1" ;;
    --state-dir=*)
      STATE_DIR="${1#--state-dir=}"; PASS[${#PASS[@]}]="$1" ;;
    --help|-h)
      usage; exit 0 ;;
    *)
      PASS[${#PASS[@]}]="$1" ;;
  esac
  shift
done

if [ "$DO_UPDATE" = 1 ] && [ "$DO_ROLLBACK" = 1 ]; then
  echo "error: --update and --rollback ask for opposite things. Pick one." >&2
  exit 2
fi

# Are we running from inside a clone (script sits next to skill_compounder/)?
SELF="${BASH_SOURCE[0]:-$0}"
APP_HOME=""
if [ -f "$SELF" ]; then
  SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
  if [ -d "$SCRIPT_DIR/skill_compounder" ]; then
    APP_HOME="$SCRIPT_DIR"
  fi
fi

# A checkout we made is ours to move. One the user made is not, and moving it would
# discard whatever they had checked out there.
MANAGED=0
if [ -z "$APP_HOME" ]; then
  MANAGED=1
elif [ "$APP_HOME" = "$MANAGED_HOME" ]; then
  MANAGED=1
fi

git_at() { git -C "$APP_HOME" "$@"; }

# The ref as a name a person recognises, falling back to the commit when HEAD is detached
# at something with no name.
current_ref() {
  name="$(git_at symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  if [ -z "$name" ]; then
    name="$(git_at describe --tags --exact-match HEAD 2>/dev/null || true)"
  fi
  if [ -z "$name" ]; then
    name="$(git_at rev-parse --short HEAD 2>/dev/null || true)"
  fi
  printf '%s' "$name"
}

current_sha() { git_at rev-parse HEAD 2>/dev/null || true; }

have_ref() {
  if git_at rev-parse --verify --quiet "refs/tags/$1^{commit}" >/dev/null 2>&1; then return 0; fi
  if git_at rev-parse --verify --quiet "refs/remotes/origin/$1^{commit}" >/dev/null 2>&1; then return 0; fi
  git_at rev-parse --verify --quiet "$1^{commit}" >/dev/null 2>&1
}

# A tag, then the remote-tracking branch, then anything else that resolves. The remote
# branch comes before the bare name so a long-lived clone follows origin rather than a
# stale local branch of the same name.
checkout_ref() {
  if git_at rev-parse --verify --quiet "refs/tags/$1^{commit}" >/dev/null 2>&1; then
    git_at checkout --quiet "refs/tags/$1"
  elif git_at rev-parse --verify --quiet "refs/remotes/origin/$1^{commit}" >/dev/null 2>&1; then
    git_at checkout --quiet -B "$1" "origin/$1"
  elif git_at rev-parse --verify --quiet "$1^{commit}" >/dev/null 2>&1; then
    git_at checkout --quiet "$1"
  else
    return 1
  fi
}

# The managed clone is shallow, so a tag cut after it was made is not in it. Fetch, and
# unshallow only when the ref is still missing: a full history is a cost, not a default.
#
# The refspecs are spelled out rather than left to the remote's configuration, and that is
# the whole reason `--update` reaches anything. `git clone --depth 1 --branch main` is a
# SINGLE-BRANCH clone: it configures `+refs/heads/main:refs/remotes/origin/main` and
# nothing else, so a plain `git fetch --tags` there returns success having seen no other
# branch and no tag. The first version of this failed exactly that way, reporting "could
# not fetch" for a ref that was sitting on the remote.
fetch_ref() {
  if ! git_at fetch --quiet --force origin \
       "+refs/heads/*:refs/remotes/origin/*" "+refs/tags/*:refs/tags/*"; then
    return 1
  fi
  if have_ref "$1"; then return 0; fi
  git_at fetch --quiet --unshallow --force origin \
       "+refs/heads/*:refs/remotes/origin/*" "+refs/tags/*:refs/tags/*" >/dev/null 2>&1 || true
  have_ref "$1"
}

# <state>/install-ref, one line for where the checkout is now and one for where it was
# before the last move. install.sh writes it rather than the installer's manifest, because
# skill_compounder/installer.py records what was LINKED and knows nothing about the
# checkout's git state; adding a key there is a change to a file this script does not own.
read_ref_field() {  # $1 = current|previous, $2 = 1 for the ref name, 2 for the sha
  if [ ! -f "$STATE_DIR/$REF_RECORD" ]; then return 1; fi
  awk -v key="$1" -v col="$2" '$1 == key { print (col == 1 ? $2 : $3); found = 1 }
                               END { exit found ? 0 : 1 }' "$STATE_DIR/$REF_RECORD"
}

write_ref_record() {  # $1 ref now, $2 sha now, $3 ref before, $4 sha before
  if ! mkdir -p "$STATE_DIR" 2>/dev/null; then
    echo "warning: cannot write $STATE_DIR/$REF_RECORD, so --rollback will have nothing" >&2
    echo "         to read. The install itself is unaffected." >&2
    return 0
  fi
  {
    echo "# claude-skill-compounder: which ref the managed checkout is at."
    echo "# Written by install.sh. 'install.sh --rollback' reads the previous line."
    echo "current $1 $2"
    if [ -n "${3:-}" ] || [ -n "${4:-}" ]; then
      echo "previous ${3:-?} ${4:-?}"
    fi
  } > "$STATE_DIR/$REF_RECORD.tmp"
  mv "$STATE_DIR/$REF_RECORD.tmp" "$STATE_DIR/$REF_RECORD"
}

keep_previous() {  # re-state the record without disturbing the rollback target
  write_ref_record "$1" "$2" \
    "$(read_ref_field previous 1 2>/dev/null || true)" \
    "$(read_ref_field previous 2 2>/dev/null || true)"
}

# Rotate only when the checkout really moved. An update that lands on the commit already
# checked out must not overwrite the rollback target with itself.
record_move() {  # $1 = ref before, $2 = sha before
  now_ref="$(current_ref)"
  now_sha="$(current_sha)"
  if [ "$now_sha" = "$2" ]; then
    keep_previous "$now_ref" "$now_sha"
  else
    write_ref_record "$now_ref" "$now_sha" "$1" "$2"
  fi
}

if [ "$MANAGED" = 0 ]; then
  # Their clone, their checkout. Refuse the two that would move it; the third is a
  # selection they already made by running this script from here.
  if [ "$DO_UPDATE" = 1 ] || [ "$DO_ROLLBACK" = 1 ]; then
    echo "error: --update and --rollback only manage the checkout install.sh made at" >&2
    echo "       $MANAGED_HOME" >&2
    echo "       This is your own clone at $APP_HOME, so moving it is yours to do:" >&2
    echo "         git -C \"$APP_HOME\" fetch --tags && git -C \"$APP_HOME\" checkout $REF" >&2
    echo "       Then re-run ./install.sh to re-wire it." >&2
    exit 2
  fi
  if [ "$REF_GIVEN" = 1 ]; then
    echo "note: --ref/SKILL_COMPOUNDER_REF is ignored here; installing $APP_HOME as it stands." >&2
  fi
fi

if [ -z "$APP_HOME" ]; then
  APP_HOME="$MANAGED_HOME"
  if [ -d "$APP_HOME/.git" ]; then
    was_ref="$(current_ref)"
    was_sha="$(current_sha)"
    if [ "$DO_ROLLBACK" = 1 ]; then
      prev_ref="$(read_ref_field previous 1 2>/dev/null || true)"
      prev_sha="$(read_ref_field previous 2 2>/dev/null || true)"
      if [ "$prev_ref" = "?" ]; then prev_ref=""; fi
      if [ "$prev_sha" = "?" ]; then prev_sha=""; fi
      if [ -z "$prev_ref" ] && [ -z "$prev_sha" ]; then
        echo "error: nothing to roll back to." >&2
        echo "       $STATE_DIR/$REF_RECORD records no previous ref, which means this" >&2
        echo "       checkout has not been moved by 'install.sh --update' yet." >&2
        exit 3
      fi
      echo "Rolling $APP_HOME back to ${prev_ref:-$prev_sha} ..."
      fetch_ref "${prev_sha:-$prev_ref}" >/dev/null 2>&1 || true
      # The sha first: it names one commit, and a tag can be moved out from under a name.
      if [ -n "$prev_sha" ] && git_at rev-parse --verify --quiet "$prev_sha^{commit}" >/dev/null 2>&1; then
        git_at checkout --quiet "$prev_sha"
      elif [ -n "$prev_ref" ] && checkout_ref "$prev_ref"; then
        :
      else
        echo "error: ${prev_ref:-$prev_sha} is not in $APP_HOME and could not be fetched." >&2
        exit 3
      fi
      record_move "$was_ref" "$was_sha"
    elif [ "$DO_UPDATE" = 1 ]; then
      echo "Updating $APP_HOME to $REF ..."
      if ! fetch_ref "$REF"; then
        echo "error: could not fetch $REF from $REPO_URL." >&2
        exit 3
      fi
      if ! checkout_ref "$REF"; then
        echo "error: $REF is not a tag, branch or commit in $APP_HOME." >&2
        exit 3
      fi
      # Recorded here and not one line later, because from the checkout onwards the record
      # is the only thing that knows where this checkout came from. There is no `git pull`
      # after this on purpose: `checkout_ref` already put the branch at the tip that
      # `fetch_ref` just brought down, so a pull can add nothing and can misfire. It did:
      # `checkout -B <b> origin/<b>` sets no upstream, so `git pull --ff-only` fell back to
      # the remote's default branch, refused a diverging merge, and -- under `set -e` --
      # took the script out before this line, leaving the record naming a ref the checkout
      # had already left and pointing --rollback at the wrong commit.
      record_move "$was_ref" "$was_sha"
    else
      # A re-run used to `git pull --ff-only` right here, which moved the user's installed
      # code as a side effect of asking to re-wire it. The two asks are now separate.
      echo "Re-using the existing checkout at $APP_HOME (at $was_ref)."
      echo "  It is not moved. To upgrade:  install.sh --update [--ref <tag>]"
      keep_previous "$was_ref" "$was_sha"
    fi
  else
    if [ "$DO_ROLLBACK" = 1 ]; then
      echo "error: there is no checkout at $APP_HOME to roll back." >&2
      exit 3
    fi
    echo "Cloning claude-skill-compounder ($REF) into $APP_HOME ..."
    TMP_CLONE="$APP_HOME.clone.$$"
    if ! git clone --depth 1 --branch "$REF" "$REPO_URL" "$TMP_CLONE" >/dev/null 2>&1; then
      # --branch takes a tag or a branch and not a commit, so a sha lands here.
      rm -rf "$TMP_CLONE"
      git clone --quiet "$REPO_URL" "$TMP_CLONE"
      if ! git -C "$TMP_CLONE" checkout --quiet "$REF"; then
        rm -rf "$TMP_CLONE"
        echo "error: $REF is not a tag, branch or commit in $REPO_URL." >&2
        exit 3
      fi
    fi
    mkdir -p "$(dirname "$APP_HOME")"
    mv "$TMP_CLONE" "$APP_HOME"
    write_ref_record "$(current_ref)" "$(current_sha)" "" ""
  fi
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "warning: jq is not on PATH. The hooks and status line need it." >&2
  echo "         install it with:  brew install jq   (or)   apt-get install jq" >&2
fi

PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "error: python3 is required but not found on PATH." >&2
  exit 1
fi

# Not `exec`, so this script gets to finish: the ref record above describes the checkout's
# git state, which is already true whatever setup.py then does with it. The exit status is
# setup.py's, unchanged. `${PASS[@]+…}` rather than a bare `"${PASS[@]}"`: under `set -u`,
# bash 3.2 -- what macOS ships -- treats an empty array expansion as an unbound variable.
status=0
"$PYTHON" "$APP_HOME/scripts/setup.py" ${PASS[@]+"${PASS[@]}"} || status=$?
exit "$status"

}
