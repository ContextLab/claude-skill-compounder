---
name: gemini-via-agy-cli
description: Use when calling Gemini from the command line (video, image or text understanding, a second-opinion review), or when the gemini CLI fails with IneligibleTierError / 'This client is no longer supported for Gemini Code Assist'.
match: ["(^\\s*|[;&|(]\\s*|\\b(?:do|then|else)\\s+)gemini(\\s|$)"]
created: 2026-11-19
---
Use the Antigravity CLI `agy` for Gemini, not the `gemini` CLI: `agy --add-dir <dir> --print-timeout 600s -p "<prompt naming the file by absolute path>" </dev/null`. The old `gemini -p ...` exits 1 at login with "IneligibleTierError: This client is no longer supported for Gemini Code Assist for individuals".
