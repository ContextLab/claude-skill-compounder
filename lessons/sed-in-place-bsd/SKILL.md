---
name: sed-in-place-bsd
description: Use when sed -i fails on macOS or BSD with an error that quotes the file name ("invalid command code", "undefined label", "unterminated substitute pattern", "expects \ followed by text", "extra characters at the end of"), or leaves a stray file ending in -e.
match: ["(?:(^\\s*|[;&|(]\\s*|\\b(?:do|then|else)\\s+)|\\b(?:xargs|exec|sudo)\\s(?:[^;&|\\n]*?\\s)?)sed\\s+(-[A-Za-hj-z]+\\s+)*-[A-Za-hj-z]*i\\s+(-[A-Za-z]+\\s+)*['\\\"]?(s[/|#,@:]|\\d|/|\\$)"]
platform: darwin
created: 2026-10-04
---
BSD sed (macOS) takes the argument after `-i` as a backup suffix. In
`sed -i 's/a/b/' file` the script is read as the suffix and the file name as the script,
so the error quotes the FILE NAME and depends on its first letter: "invalid command code
m" (main.py), "undefined label 'est.txt'" (test.txt), "unterminated substitute pattern"
(src.txt), "command c expects \ followed by text" (config.json), "extra characters at the
end of d command" (d.txt). The file is not changed.

- Works on GNU and BSD alike: attach a suffix and remove the backup,
  `sed -i.bak 's/a/b/' file && rm file.bak`, or use `perl -pi -e 's/a/b/' file`.
- `sed -i '' 's/a/b/' file` works on BSD only; `sed -i 's/a/b/' file` on GNU only.
- `sed -i -e 's/a/b/' file` does not fail on BSD: it edits the file and leaves a backup
  named `file-e` beside it. Remove that file.

If the `sed` on PATH here is GNU sed (`sed --version` prints "GNU sed"), `sed -i 's/a/b/'
file` was right: send it again.
