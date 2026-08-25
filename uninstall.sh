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

exec "$PYTHON" "$APP_HOME/scripts/setup.py" --uninstall "$@"
