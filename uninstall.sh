#!/usr/bin/env bash
# Uninstaller (leaves your forge/reminder state intact):
#   curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/uninstall.sh | bash
# Or from a clone:  ./uninstall.sh
set -euo pipefail

DEFAULT_HOME="$HOME/.claude/skill-compounder-app"
SELF="${BASH_SOURCE[0]:-$0}"
APP_HOME=""
if [ -f "$SELF" ]; then
  SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
  if [ -d "$SCRIPT_DIR/skill_compounder" ]; then
    APP_HOME="$SCRIPT_DIR"
  fi
fi
[ -z "$APP_HOME" ] && APP_HOME="${CLAUDE_SKILL_COMPOUNDER_APP:-$DEFAULT_HOME}"

PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "error: python3 is required but not found on PATH." >&2
  exit 1
fi

# Where the install recorded itself. `curl ... | bash` has no checkout around it and
# assumes the default clone path, which is wrong for anyone who installed from their own
# clone -- that used to fail with a raw "can't open file .../scripts/setup.py".
STATE_DIR="${CLAUDE_SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"
prev=""
for arg in "$@"; do
  if [ "$prev" = "--state-dir" ]; then STATE_DIR="$arg"; fi
  case "$arg" in --state-dir=*) STATE_DIR="${arg#--state-dir=}" ;; esac
  prev="$arg"
done

if [ ! -f "$APP_HOME/scripts/setup.py" ]; then
  FOUND="$("$PYTHON" - "$STATE_DIR" <<'PY' || true
import json, os, sys
path = os.path.join(sys.argv[1], "install-manifest.json")
try:
    with open(path) as fh:
        home = (json.load(fh) or {}).get("app_home") or ""
except Exception:
    home = ""
if home and os.path.isfile(os.path.join(home, "scripts", "setup.py")):
    print(home)
PY
)"
  if [ -n "$FOUND" ]; then APP_HOME="$FOUND"; fi
fi

if [ ! -f "$APP_HOME/scripts/setup.py" ]; then
  echo "error: no claude-skill-compounder checkout to uninstall from." >&2
  echo "       looked at: $APP_HOME" >&2
  echo "       and at the install record in: $STATE_DIR" >&2
  echo "       Clone the repo and run ./uninstall.sh from the clone. It will still" >&2
  echo "       recognise and remove the links an earlier checkout created." >&2
  exit 1
fi

exec "$PYTHON" "$APP_HOME/scripts/setup.py" --uninstall "$@"
