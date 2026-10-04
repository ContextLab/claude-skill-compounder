---
name: zsh-status-path-variables
description: "Use when a command fails in zsh with \"read-only variable: status\", or when ls, git and other ordinary commands fail with \"command not found\" after a variable named path was assigned."
match: ["(^\\s*|(?:;|&&|\\|\\|)\\s*|\\b(?:do|then|else)\\s+|\\{\\s+)((local|export|typeset|readonly|declare)\\s+)?(status|path)=", "(^\\s*|[;&|(]\\s*|\\b(?:do|then|else)\\s+)for\\s+(status|path)\\s+in\\b", "(^\\s*|[;&|(]\\s*|\\b(?:do|then|else|while|until)\\s+)(IFS=\\S*\\s+)?read\\s+(-\\w+\\s+)*(status|path)\\b"]
shell: zsh
created: 2026-10-04
---
In zsh two ordinary-looking variable names are taken:

- `status` is read-only (it is `$?`). `status=$(cmd)` or `status=$?` fails with
  "read-only variable: status" and the command line stops there.
- `path` is tied to `PATH`. `path=/tmp/x`, `for path in ...`, `read path` or `local path=...`
  replaces the command search path, so every command after it (`ls`, `git`, `python3`)
  fails with "command not found" until the shell or the function ends.

Use other names: `rc=$?`, `st=$(cmd)`, `file_path=...`, `for p in ...`. Both names are
ordinary variables in bash, so a script that names bash on its first line and is run as a
file is not affected.
