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
