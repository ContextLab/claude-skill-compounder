#!/bin/bash
# Adds the six drafts to a SANDBOX store with the real CLI. Never touches ~/.claude.
set -eu
S=/private/tmp/claude-501/-Users-jmanning-claude-skill-compounder/09f47a44-bbcb-4125-a53e-ba217729c8cb/scratchpad/general-pool
CLI=/Users/jmanning/claude-skill-compounder/bin/compound
for v in $(env | grep -o '^COMPOUND_[A-Z_]*' || true); do unset "$v"; done
unset CLAUDE_CODE_SESSION_ID || true
export COMPOUND_HOME=$S/sandbox/home COMPOUND_CLAUDE_DIR=$S/sandbox/claude COMPOUND_PROJECT=$S/sandbox/proj
cd $S/sandbox/proj
O="general pool draft, 2026-10-04"
set -x
$CLI add --level user --origin "$O" --name zsh-no-matches-found --body-file $S/bodies/zsh-no-matches-found.md \
  --when 'Use when a command fails in zsh with "no matches found:" (an unquoted glob or bracket that matched no file: rm -f build/*.o, grep --include=*.py, pip install pkg[extra], a URL with "?").'
$CLI add --level user --origin "$O" --name zsh-equals-not-found --body-file $S/bodies/zsh-equals-not-found.md \
  --when 'Use when a command fails in zsh with "==== not found" or "=word not found" (a bare word starting with "=", such as echo ===== printed as a separator).'
$CLI add --level user --origin "$O" --name zsh-status-path-variables --body-file $S/bodies/zsh-status-path-variables.md \
  --when 'Use when a command fails in zsh with "read-only variable: status", or when ls, git and other ordinary commands fail with "command not found" after a variable named path was assigned.'
$CLI add --level user --origin "$O" --name sed-in-place-bsd --body-file $S/bodies/sed-in-place-bsd.md \
  --when 'Use when sed -i fails on macOS or BSD with an error that quotes the file name ("invalid command code", "undefined label", "unterminated substitute pattern", "expects \ followed by text", "extra characters at the end of"), or leaves a stray file ending in -e.'
$CLI add --level user --origin "$O" --name pip-externally-managed --body-file $S/bodies/pip-externally-managed.md \
  --when 'Use when pip install fails with "error: externally-managed-environment" (PEP 668: the Python of Homebrew, Debian, Ubuntu or Fedora).'
$CLI add --level user --origin "$O" --name macos-gnu-only-commands --body-file $S/bodies/macos-gnu-only-commands.md \
  --when 'Use when a command fails on macOS with "command not found: timeout", "date: illegal option -- d", "grep: invalid option -- P", "stat: illegal option -- c", or another GNU-only command or flag.'
$CLI list
$CLI status || true
