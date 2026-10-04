# Scenes 1 and 2 of docs/media/demo.gif: one real interactive session in acme-api.
# Run it with `dev/demo.sh learn [N]`, which builds the world and fills in the output;
# the header of dev/demo.sh says how the takes become the GIF. The whole session is
# recorded, the model's thinking included; dev/demo.sh join cuts the waits out afterwards.
#
# Scene 1: the request. In the world's shell python3 is the system's 3.9, so the usual first call
# (python3 -c "import tomllib ...") fails; a take where it does not is recorded again.
# Scene 2: the mod says a lesson is owed, the session records it, /compound shows it.
# 1160 x 720 pixels at this font size is a 110 x 32 terminal.

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
Type ". ./env.sh acme-api && clear" Enter
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
Type "Convert config.toml to JSON and save it as config.json." 
Sleep 600ms
Enter
# vhs cannot be made to wait for the band: Wait+Screen never matched its text here, and
# a Wait that times out writes no video at all. So the tape sleeps through the turn
# (failure, fix, the lesson recorded, the closing answer) and the waits are cut later.
Sleep 90s
Type "/compound"
Sleep 1s
Enter
Sleep 12s
Ctrl+C
Ctrl+C
Sleep 2s
