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
both. `gtimeout`, `gdate`, `gsed` exist only where Homebrew's coreutils is installed.
