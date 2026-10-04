---
name: macos-gnu-only-commands
description: "Use when a command fails on macOS with \"command not found: timeout\", \"date: illegal option -- d\", \"grep: invalid option -- P\", \"stat: illegal option -- c\", or another GNU-only command or flag."
match: ["(^\\s*|[;&|(]\\s*|\\b(?:do|then|else)\\s+)timeout\\s+(-\\S+\\s+)*\\d"]
platform: darwin
created: 2026-10-04
---
macOS ships the BSD versions of the standard tools and no GNU coreutils, so a GNU-only
command or flag fails there. What works on a stock Mac:

| GNU form | on macOS |
|-|-|
| `timeout 60 cmd` | not installed, and `cmd` NEVER RAN: do not read the empty output as its result. Use the Bash tool's own timeout or run_in_background, or `perl -e 'alarm shift; exec @ARGV' 60 cmd` |
| `date -d yesterday +%F` | `date -v-1d +%F` |
| `date -d @1700000000` | `date -r 1700000000` |
| `grep -P '\d+'` | `grep -E '[0-9]+'`, or `perl -ne 'print if /\d+/'` |
| `stat -c %s file` (size), `stat -c %Y file` (mtime) | `stat -f %z file`, `stat -f %m file` |

When the same line must run on Linux too, `python3 -c` or `perl` behaves the same on
both. `gtimeout` and `gdate` exist only where Homebrew's coreutils is installed, and
`gsed` only with its gnu-sed.

A call of `timeout` is stopped before it runs on macOS. If this Mac does have a
`timeout` on PATH (`command -v timeout` prints a path), the call was right: send it again.
