In zsh two ordinary-looking variable names are taken:

- `status` is read-only (it is `$?`). `status=$(cmd)` or `status=$?` fails with
  "read-only variable: status" and the command line stops there.
- `path` is tied to `PATH`. `path=/tmp/x`, `for path in ...`, `read path` or `local path=...`
  replaces the command search path, so every command after it (`ls`, `git`, `python3`)
  fails with "command not found" until the shell or the function ends.

Use other names: `rc=$?`, `st=$(cmd)`, `file_path=...`, `for p in ...`. Both names are
ordinary variables in bash, so a script that names bash on its first line and is run as a
file is not affected.
