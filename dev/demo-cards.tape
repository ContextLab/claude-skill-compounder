# The three title cards of docs/media/demo.gif, printed by a real shell: each is on
# screen for three seconds, at 1-4 s, 5-8 s and 9-12 s of the take. `dev/demo.sh cards`.

Output "@OUT@"
Set Shell bash
Set FontSize 16
Set Width 1160
Set Height 720
Set Padding 14
Set Framerate 20
Set TypingSpeed 40ms
Set Theme { "name": "demo", "background": "#0d1117", "foreground": "#e6edf3", "cursor": "#e6edf3", "selection": "#264f78", "black": "#484f58", "red": "#ff7b72", "green": "#3fb950", "yellow": "#d29922", "blue": "#58a6ff", "magenta": "#bc8cff", "cyan": "#39c5cf", "white": "#b1bac4", "brightBlack": "#6e7681", "brightRed": "#ffa198", "brightGreen": "#56d364", "brightYellow": "#e3b341", "brightBlue": "#79c0ff", "brightMagenta": "#d2a8ff", "brightCyan": "#56d4dd", "brightWhite": "#ffffff" }

Hide
Type ". ./cards.sh" Enter
Sleep 1s
Show
Hide
Type "card 1 'A request goes wrong, then right' 'compound watches a failed command, and the one that fixes it'" Enter
Show
Sleep 4s
Hide
Type "card 2 'The lesson is recorded' 'Claude writes down what it learned; /compound shows it'" Enter
Show
Sleep 4s
Hide
Type "card 3 'A new session, a different project' 'the mistake is stopped before it is made again'" Enter
Show
Sleep 4s
