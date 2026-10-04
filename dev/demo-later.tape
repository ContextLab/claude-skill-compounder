# Scene 3 of docs/media/demo.gif: a NEW real session in another project, billing-svc,
# over the store the kept `learn` take left. Run it with `dev/demo.sh later [N]`.
# With the lesson a guard, the first mistaken call is refused once before it runs; with a
# plain lesson, it is recalled beside the error. Either way the band shows it. The tape
# ends in the shell with the lesson's row of `compound status`.

Output "@OUT@"
Set Shell bash
Set FontSize 16
Set Width 1160
Set Height 720
Set Padding 14
Set Framerate 20
Set TypingSpeed 40ms
Set Theme { "name": "demo", "background": "#0d1117", "foreground": "#e6edf3", "cursor": "#e6edf3", "selection": "#264f78", "black": "#484f58", "red": "#ff7b72", "green": "#3fb950", "yellow": "#d29922", "blue": "#58a6ff", "magenta": "#bc8cff", "cyan": "#39c5cf", "white": "#b1bac4", "brightBlack": "#6e7681", "brightRed": "#ffa198", "brightGreen": "#56d364", "brightYellow": "#e3b341", "brightBlue": "#79c0ff", "brightMagenta": "#d2a8ff", "brightCyan": "#56d4dd", "brightWhite": "#ffffff" }
Set WaitTimeout 60s

Hide
Type ". ./env.sh billing-svc && clear" Enter
Sleep 500ms
Show
Sleep 800ms
Type "ls" Enter
Sleep 1200ms
Type "claude --model sonnet" Enter
Wait+Screen /trust this folder|Claude Code v/
Sleep 1s
Down
Enter
Sleep 4s
# Under 80 characters, so the reuse check (COMPOUND_PROMPT_MIN_CHARS) leaves it alone and
# the lesson is met at the call. A longer request is told of the lesson up front instead
# (band: "reuse found"), and the session then avoids the mistake without being stopped.
Type "Use Python to merge defaults.toml and local.toml and print the result as JSON."
Sleep 600ms
Enter
Sleep 75s
Type "/compound"
Sleep 1s
Enter
Sleep 10s
Ctrl+C
Ctrl+C
Sleep 2s
Type "clear" Enter
Type "compound status | sed -n '/^Lessons/,/^Open/p'" Enter
Sleep 6s
