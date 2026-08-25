#!/usr/bin/env bash
# One-line installer:
#   curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh | bash
# Or from a clone:  ./install.sh
set -euo pipefail

REPO_URL="https://github.com/ContextLab/claude-skill-compounder.git"
DEFAULT_HOME="$HOME/.claude/skill-compounder-app"

# Are we running from inside a clone (script sits next to skill_compounder/)?
SELF="${BASH_SOURCE[0]:-$0}"
APP_HOME=""
if [ -f "$SELF" ]; then
  SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
  if [ -d "$SCRIPT_DIR/skill_compounder" ]; then
    APP_HOME="$SCRIPT_DIR"
  fi
fi

if [ -z "$APP_HOME" ]; then
  APP_HOME="${CLAUDE_SKILL_COMPOUNDER_APP:-$DEFAULT_HOME}"
  if [ -d "$APP_HOME/.git" ]; then
    echo "Updating existing install at $APP_HOME ..."
    git -C "$APP_HOME" pull --ff-only
  else
    echo "Cloning claude-skill-compounder into $APP_HOME ..."
    git clone --depth 1 "$REPO_URL" "$APP_HOME"
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

exec "$PYTHON" "$APP_HOME/scripts/setup.py" "$@"
