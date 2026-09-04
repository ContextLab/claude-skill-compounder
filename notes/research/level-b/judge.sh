#!/bin/bash
D="${LEVELB_DIR:-./levelb}"
mkdir -p "$D/judgements"
pid="$1"; run="$2"
out="$D/judgements/${pid}.r${run}.txt"
[ -s "$out" ] && exit 0
p="$D/prompts/${pid}.txt"
SKILL_COMPOUNDER_DISPATCHED=1 claude -p "$(cat "$p")" \
  --model claude-haiku-4-5-20251001 \
  --strict-mcp-config --setting-sources '' \
  --disallowed-tools Bash Task Agent Write Edit NotebookEdit Read Glob Grep WebFetch WebSearch Skill \
  > "$out" 2>"$out.err"
