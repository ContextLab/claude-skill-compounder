# dev/forge.tape -- the README animation.
# Records dev/forge_demo.sh: a simulated Claude Code session that first pays for a
# lesson the cheap way -- a real `gh run list --commit` dead end, the headSha filter
# that worked, and `skillnote add --lesson` writing the note and the reminder in one
# command -- and then forges `watch-ci-run` under the round diet: two red-team rounds,
# both returning 6 blocking of 13, so `--converging` is refused and only a narrowed
# skill buys a third. The bottom block is painted by the real statusline/statusline.sh
# from state written by the real bin/skillforge.
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
# SET THIS FROM THE DEMO'S MEASURED WALL TIME, NEVER FROM ITS HOLDS. Summing the holds
# under-counts by about a third: `say` repaints the block, and each repaint runs the real
# statusline (jq and all) at ~109ms, so 87 lines plus twelve `skillforge` calls add ~18s that
# no `hold` accounts for. A tape cut to the hold total ends mid-forge -- measured once,
# with the round-2 line on screen and `skillforge done` never reached.
#
# Re-derive it by running the demo with its final hold zeroed and timing it:
#   sed -E 's/^hold 20 .*$/hold 0/' dev/forge_demo.sh > dev/.t.sh
#   time bash dev/.t.sh >/dev/null 2>&1 </dev/null ; rm dev/.t.sh
# That printed 61.8s on 2026-09-05 (holds sum to 44s + a final 20s). Recording starts 2s
# after Enter (the Hide block), so the last line lands at GIF t=59.8s and 64s leaves a few
# seconds of the finished frame.
# It must also stay UNDER the demo's final `hold 20`, or forge_demo.sh exits first and a
# bare shell prompt is what the recording ends on.
Sleep 64s
