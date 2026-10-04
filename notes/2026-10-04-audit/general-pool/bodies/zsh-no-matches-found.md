zsh stops the whole command line with "no matches found: <pattern>" when an unquoted
word containing `*`, `?` or `[...]` matches no file. The program never runs (not even
`rm -f`), and nothing after it on the line runs either. bash would have passed the word
through unchanged.

- A pattern or text meant for the program: quote it. `grep -r --include='*.py' foo .`,
  `find . -name '*.py'`, `pip install 'requests[socks]'`, `curl 'https://host/api?x=1'`.
- Files that may be absent: `find build -name '*.o' -delete` instead of `rm -f build/*.o`,
  or name the file without a pattern.
