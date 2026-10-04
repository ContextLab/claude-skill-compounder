zsh takes a bare word that starts with "=" as the name of a command to look up, so
`echo =====` fails with "==== not found" and the rest of the command line is lost: what
followed the separator never ran. bash prints the word.

Quote the word (`echo '====='`), print it with `printf '%s\n' '====='`, or use a
separator that does not start with "=" (`echo "--- step 2"`).
