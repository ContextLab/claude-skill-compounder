---
name: zsh-equals-not-found
description: Use when a command fails in zsh with "==== not found" or "=word not found" (a bare word starting with "=", such as echo ===== printed as a separator).
created: 2026-10-04
origin: general pool draft, 2026-10-04
---
zsh takes a bare word that starts with "=" as the name of a command to look up, so
`echo =====` fails with "==== not found" and the rest of the command line is lost: what
followed the separator never ran. bash prints the word.

Quote the word (`echo '====='`), print it with `printf '%s\n' '====='`, or use a
separator that does not start with "=" (`echo "--- step 2"`).
