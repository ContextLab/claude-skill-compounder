# A real interactive session, recorded with vhs, to LOOK at the band and the pane.
#
# Run it with dev/ui-check.sh, which builds a throwaway world in $TMPDIR/compound-ui-check
# (a store with one guard and one ordinary lesson and four findings of /insights harvested
# from an invented usage-data tree, a run of /insights due, a project with a deploy.sh that
# fails without its flag) and runs this tape from that directory. It records two sessions:
# the first (0-*) tells the findings alone and starts a run, which fails at once in that
# world, and opens the pane; the second, after an earlier session is made to leave a fix
# unsettled, tells the capture with the findings beside it and goes through the moments
# (1-* to 5-*). The screenshots land in
# $TMPDIR/compound-ui-check/shots; open the PNGs and look. It spends model calls, and the
# session's own pace and wording decide which frame catches which phase: read them, do
# not diff them. vhs writes the screenshots only when the whole tape has run, so the tape
# sleeps and takes many frames rather than waiting for text that may never come.
#
# What it takes to get an interactive `--plugin-dir` session under vhs:
#   - a new folder asks "Is this a project you trust?" with "No, exit" selected:
#     Down, Enter picks "Yes, I trust this folder". Claude Code remembers the answer for
#     that path (in ~/.claude.json), so a second run is not asked; Down, Enter at the
#     empty prompt does nothing, so the tape sends them either way;
#   - `--allowedTools Bash` keeps the session from stopping at a permission prompt;
#   - `--setting-sources project` keeps the user's own hooks out, and
#     CLAUDE_CODE_PLUGIN_DIRS="" (dev/ui-check.sh exports it) keeps an installed copy of
#     the mod from loading beside this one;
#   - run from inside a Claude Code session, the shell inherits CLAUDECODE,
#     CLAUDE_CODE_SESSION_ID and CLAUDE_CODE_CHILD_SESSION; dev/ui-check.sh unsets them,
#     or the recorded session takes itself for a child of that one;
#   - a --plugin-dir plugin loads without a question: hot reloading asks nothing here.
# 1060 pixels at this font size is a 100-column terminal.

Output shots/session.gif
Set Shell bash
Set FontSize 15
Set Width 1060
Set Height 900
Set Padding 10
Set WaitTimeout 60s

Hide
Type ". ./env.sh && cd $UI_PROJECT && clear" Enter
Show

# Session one: the store holds four findings of /insights and no capture owed, and a run of
# /insights is due, so the first prompt tells the findings alone and starts a run, whose
# child is not logged in and fails at once. The notes fade after 8 seconds.
Type "claude --plugin-dir $UI_PLUGIN --model haiku --setting-sources project --allowedTools Bash" Enter
Wait+Screen /trust this folder|Claude Code v/
Sleep 1s
Down
Enter
Sleep 5s
Screenshot shots/00-start.png
Type "Reply with one short sentence saying you are ready. Run no command and use no tool."
Enter
Sleep 300ms
Screenshot shots/0-insights-00.png
Sleep 300ms
Screenshot shots/0-insights-01.png
Sleep 400ms
Screenshot shots/0-insights-02.png
Sleep 500ms
Screenshot shots/0-insights-03.png
Sleep 1000ms
Screenshot shots/0-insights-04.png
Sleep 1500ms
Screenshot shots/0-insights-05.png
Sleep 1500ms
Screenshot shots/0-insights-06.png
Sleep 1500ms
Screenshot shots/0-insights-07.png
Sleep 1500ms
Screenshot shots/0-insights-08.png
Sleep 1500ms
Screenshot shots/0-insights-09.png
Sleep 2000ms
Screenshot shots/0-insights-10.png
Sleep 3000ms
Screenshot shots/0-insights-11.png

# The pane once the worker has failed: the findings under Open, and the insights check
# among the warnings, the failed run's message under the errors; then the report as text,
# whose health rows (the insights WARN among them) scroll above the frame: `compound status`
# run in the world after the recording prints them.
# After a short turn Claude Code may offer "Teach auto mode about your environment?",
# with Yes selected: Escape cancels it, or does nothing at an empty prompt, so the tape
# sends it either way before typing anything more.
Sleep 10s
Escape
Sleep 1s
Type "/compound"
Sleep 1s
Enter
Sleep 8s
Screenshot shots/0-pane.png
Type "/compound status"
Sleep 1s
Enter
Sleep 6s
Screenshot shots/0-status-text.png
Sleep 500ms
Escape
Sleep 500ms
Ctrl+C
Ctrl+C
# What is typed next is a shell command: it must not reach a session that is still open,
# which would run it. Once Claude Code has exited, the last line is the shell's bare prompt.
Wait+Line /^\$ *$/

# Session two: an earlier session left a fix unsettled, so its first prompt tells the
# capture with the findings beside it; the run started minutes ago, so none is due.
Hide
Type "sh $UI_WORLD/later.sh && clear" Enter
Show
Type "claude --plugin-dir $UI_PLUGIN --model haiku --setting-sources project --allowedTools Bash" Enter
Wait+Screen /trust this folder|Claude Code v/
Sleep 1s
Down
Enter
Sleep 5s
Screenshot shots/00-start-2.png

# Moment 1: a substantial prompt is checked for reusable work. As the session's first
# prompt it also tells the capture owed and, beside it, the findings of /insights.
Type "Write the release notes for version 2.1 of this project, which fixes three parser bugs, in the format this project uses, and print them here. Do not create any file."
Enter
Sleep 300ms
Screenshot shots/1-reuse-00.png
Sleep 300ms
Screenshot shots/1-reuse-01.png
Sleep 300ms
Screenshot shots/1-reuse-02.png
Sleep 400ms
Screenshot shots/1-reuse-03.png
Sleep 500ms
Screenshot shots/1-reuse-04.png
Sleep 700ms
Screenshot shots/1-reuse-05.png
Sleep 1500ms
Screenshot shots/1-reuse-06.png
Sleep 2000ms
Screenshot shots/1-reuse-07.png
Sleep 2000ms
Screenshot shots/1-reuse-08.png
Sleep 2000ms
Screenshot shots/1-reuse-09.png
Sleep 3000ms
Screenshot shots/1-reuse-10.png

# Moment 2: a call that matches a guard is refused once.
Type "Run exactly this Bash command first: echo GUARDED_MARKER_42 -- if the call is refused, read the reason and then send the very same command again, unchanged."
Enter
Sleep 1000ms
Screenshot shots/2-guard-00.png
Sleep 1000ms
Screenshot shots/2-guard-01.png
Sleep 1000ms
Screenshot shots/2-guard-02.png
Sleep 1000ms
Screenshot shots/2-guard-03.png
Sleep 1000ms
Screenshot shots/2-guard-04.png
Sleep 1000ms
Screenshot shots/2-guard-05.png
Sleep 2000ms
Screenshot shots/2-guard-06.png
Sleep 2000ms
Screenshot shots/2-guard-07.png
Sleep 3000ms
Screenshot shots/2-guard-08.png
Sleep 3000ms
Screenshot shots/2-guard-09.png
Sleep 4000ms
Screenshot shots/2-guard-10.png

# Moments 4 and 5: a failure, its fix, a lesson owed, and the lesson recorded.
Type "Deploy this project: first run ./deploy.sh exactly like that, with no arguments, and go on from what it prints. Tell me the one line it prints on success. Do not read or print deploy.sh."
Enter
Sleep 1500ms
Screenshot shots/3-learn-00.png
Sleep 1500ms
Screenshot shots/3-learn-01.png
Sleep 1500ms
Screenshot shots/3-learn-02.png
Sleep 1500ms
Screenshot shots/3-learn-03.png
Sleep 1500ms
Screenshot shots/3-learn-04.png
Sleep 1500ms
Screenshot shots/3-learn-05.png
Sleep 1500ms
Screenshot shots/3-learn-06.png
Sleep 1500ms
Screenshot shots/3-learn-07.png
Sleep 1500ms
Screenshot shots/3-learn-08.png
Sleep 1500ms
Screenshot shots/3-learn-09.png
Sleep 1500ms
Screenshot shots/3-learn-10.png
Sleep 1500ms
Screenshot shots/3-learn-11.png
Sleep 1500ms
Screenshot shots/3-learn-12.png
Sleep 1500ms
Screenshot shots/3-learn-13.png
Sleep 1500ms
Screenshot shots/3-learn-14.png
Sleep 1500ms
Screenshot shots/3-learn-15.png
Sleep 1500ms
Screenshot shots/3-learn-16.png
Sleep 1500ms
Screenshot shots/3-learn-17.png
Sleep 1500ms
Screenshot shots/3-learn-18.png
Sleep 1500ms
Screenshot shots/3-learn-19.png
Sleep 1500ms
Screenshot shots/3-learn-20.png
Sleep 1500ms
Screenshot shots/3-learn-21.png
Sleep 1500ms
Screenshot shots/3-learn-22.png
Sleep 1500ms
Screenshot shots/3-learn-23.png
Sleep 1500ms
Screenshot shots/3-learn-24.png
Sleep 1500ms
Screenshot shots/3-learn-25.png
Sleep 1500ms
Screenshot shots/3-learn-26.png
Sleep 1500ms
Screenshot shots/3-learn-27.png
Sleep 1500ms
Screenshot shots/3-learn-28.png
Sleep 1500ms
Screenshot shots/3-learn-29.png
Sleep 1500ms
Screenshot shots/3-learn-30.png
Sleep 1500ms
Screenshot shots/3-learn-31.png
Sleep 1500ms
Screenshot shots/3-learn-32.png
Sleep 1500ms
Screenshot shots/3-learn-33.png
Sleep 1500ms
Screenshot shots/3-learn-34.png
Sleep 1500ms
Screenshot shots/3-learn-35.png
Sleep 1500ms
Screenshot shots/3-learn-36.png
Sleep 1500ms
Screenshot shots/3-learn-37.png
Sleep 1500ms
Screenshot shots/3-learn-38.png
Sleep 1500ms
Screenshot shots/3-learn-39.png
Sleep 1500ms
Screenshot shots/3-learn-40.png
Sleep 1500ms
Screenshot shots/3-learn-41.png
Sleep 1500ms
Screenshot shots/3-learn-42.png
Sleep 1500ms
Screenshot shots/3-learn-43.png
Sleep 1500ms
Screenshot shots/3-learn-44.png
Sleep 1500ms
Screenshot shots/3-learn-45.png
Sleep 1500ms
Screenshot shots/3-learn-46.png
Sleep 1500ms
Screenshot shots/3-learn-47.png
Sleep 1500ms
Screenshot shots/3-learn-48.png
Sleep 1500ms
Screenshot shots/3-learn-49.png

# The dashboard, and the report as text.
Type "/compound"
Sleep 1s
Enter
Sleep 8s
Screenshot shots/4-pane.png

# The pane's keys. Opened, it has not the keyboard: what is typed goes to the prompt.
# ctrl+x tab gives it the keys: the ring starts on the first lesson row, the arrows walk
# the rows, Enter opens the one ringed, `b` goes back, `a` lists every lesson, Esc hands
# the keyboard back to the prompt.
Type "typed"
Sleep 1s
Screenshot shots/4-pane-typing-goes-to-the-prompt.png
Backspace 5
Sleep 500ms
Ctrl+X
Tab
Sleep 1500ms
Screenshot shots/4-pane-with-the-keys.png
Enter
Sleep 3s
Screenshot shots/4-pane-lesson.png
Type "b"
Sleep 2s
Screenshot shots/4-pane-back.png
Type "a"
Sleep 3s
Screenshot shots/4-pane-all-lessons.png
Down
Sleep 1s
Enter
Sleep 3s
Screenshot shots/4-pane-lesson-from-the-list.png
Type "b"
Sleep 2s
Screenshot shots/4-pane-back-to-the-list.png
Type "b"
Sleep 2s
Escape
Sleep 1s
Type "/compound status"
Sleep 1s
Enter
Sleep 6s
Screenshot shots/5-status-text.png
Sleep 500ms
Ctrl+C
Ctrl+C
Sleep 1s
