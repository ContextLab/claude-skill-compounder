#!/bin/bash
D="${LEVELB_DIR:-./levelb}"
mkdir -p "$D/judgements_rare"
out="$D/judgements_rare/$1.r$2.txt"; [ -s "$out" ] && exit 0
SKILL_COMPOUNDER_DISPATCHED=1 claude -p "$(cat "$D/prompts_rare/$1.txt")" \
  --model claude-haiku-4-5-20251001 --strict-mcp-config --setting-sources '' \
  --disallowed-tools Bash Task Agent Write Edit NotebookEdit Read Glob Grep WebFetch WebSearch Skill \
  > "$out" 2>"$out.err"
