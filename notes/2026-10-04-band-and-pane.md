# 2026-10-04: the band above the prompt and the /compound pane

What was built, for whoever picks this up next. Nothing here is committed.

- `hooks/view.ts` (pure, `view.test.ts`): glyphs, colours, labels, the spinner frames,
  the fade phases, the learn-loop track, the band's reducers, and the pane's lines.
- `hooks/register.ts`: three atoms in `$.state` (`band`, `frame`, `board`; contract in
  `types/index.d.ts`, named by `plugin.json`), `paint` to change the band, one timer
  (`animate`/`tick`), `refreshBoard`/`boardStale` for the pane, and two `ui.render` hooks
  written with `h(...)` so the module stays `.ts`.
- `hooks/ui.test.ts`: the band and the pane mounted on `terminal` and `desktop`.
- `/compound` opens the pane; `/compound status` prints the report; `/compound close`.
- `COMPOUND_QUIET=1` turns the band off.
- `dev/ui-check.sh` + `dev/ui-check.tape`: a vhs recording of a real session;
  screenshots in `$TMPDIR/compound-ui-check/shots`.

Found on the way:

- vhs writes its screenshots only when the whole tape ran: a `Wait` that times out loses
  every frame. The tape sleeps and takes many frames instead.
- A shell inside a Claude Code session exports `CLAUDECODE`, `CLAUDE_CODE_SESSION_ID` and
  `CLAUDE_CODE_CHILD_SESSION`; a `claude` started from it says "Transcript saving is off".
  `dev/ui-check.sh` unsets them.
- A test's hooks beneath the plugin answer `{ value }` for a `$` call, `{ result, text,
  isError }` for `tool.call`, and must all be registered before the test's first call on
  `$`. `mock.clock` owns `clock.now`; a second hook on it fails the load.
- `tests/test_support.py`'s `plugin()` fixture lists the files that make the package
  loadable; `types/index.d.ts` is one of them now, and `compound status`'s `mod` check
  fails without it.
- The status entry reads `compound: compound: lesson owed` in the terminal: the engine
  puts the plugin's name before the text the mod sets. Left as it is; the entry's text
  is pinned by the docs and by `render.test.ts`.
- Open: on the desktop surface the colours (`cyan`, `magenta`, theme keys) were validated
  by the test kit as a tree, never looked at.
