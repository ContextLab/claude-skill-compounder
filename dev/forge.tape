# dev/forge.tape -- the README animation.
# Records dev/forge_demo.sh: a simulated Claude Code session in which a procedure
# clears the bar and is forged into a skill. The bottom block is painted by the
# real statusline/statusline.sh from state written by the real bin/skillforge.
Output docs/media/forge.gif
Set FontSize 14
Set Width 1440
Set Height 680
Set Padding 20
Set Framerate 6
Set TypingSpeed 40ms

# Hide the invocation: the recording should look like a session, not a script.
Hide
Type "clear && ./dev/forge_demo.sh"
Enter
Sleep 2s
Show
# The demo's own holds sum to 59s (three red-team rounds, then the narrowing).
# Leave headroom so the last frame is the finished session, not a truncated one.
Sleep 61s
