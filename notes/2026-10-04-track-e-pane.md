# Track E: pane drill-down (2026-10-04)

Audit proposal 4 (`notes/2026-10-04-audit/audit-ui.md`): the `/compound` pane was
read-only, with two Buttons whose hotkeys were shown nowhere. Base: `ba5d77b`.

## What the function-hook API does (found out, not assumed)

Read in the plugin-authoring skill's `reference.md` and `claude-code.d.ts` (build 2.1.289),
then checked in a real interactive session recorded with vhs (a throwaway mod with a pane of
plain Buttons, then this mod):

| Question | Answer | How it was checked |
|-|-|-|
| Do keys reach a pane that was just opened? | No. A pane opened without `focus` has not the keyboard: what is typed goes to the prompt | vhs: typed text appears in the prompt, `isFocused` false |
| How does a pane get the keyboard? | ctrl+x tab (the docs also say a click); Esc hands it back | vhs: ctrl+x tab, then `isFocused` true; Esc, then typing is in the prompt again. A click was not tried: vhs sends no mouse |
| What do hotkeys need? | The pane must hold the keyboard. A hotkey works even when its Button is scrolled out of the window | vhs: `a`, `b`, `r`, `x` press their Buttons only after ctrl+x tab |
| Is there row selection? | Yes: a ring over the Buttons. Tab walks it; Enter presses the ringed Button. The arrows walk it too while the tree fits the window; when the tree is taller the arrows scroll the window instead, and Tab still walks (and brings the Button into the window) | vhs, both cases |
| Where does the ring start? | On the first Button drawn, unless one is drawn `autoFocus`. After the tree is redrawn with other Buttons (a view change) it is on the first Button again, so the mod moves it with `$.ui.focus` | vhs: before the fix the ring sat on `b: back` after a view change |
| How tall is the window? | `scroll.bodyRows` is the rows actually given: as tall as the content when the content is shorter than what `rows` asked, else what the layout spares (12 rows where 14 were asked) | vhs |
| Can a row be pinned at the foot of the pane? | No. The window is the engine's and a taller tree scrolls. Fitting the tree to `bodyRows` cannot be made stable, because `bodyRows` shrinks to the content and so never grows back | vhs, and the reasoning above |
| How is a plain Button drawn? | Its label alone; with a hotkey, `a: label`, the key in the accent colour. The ring inverts it | vhs |

Consequences for the design:

- The pane is opened WITHOUT `focus`, as before: it does not steal typing. The key row says
  `ctrl+x tab for keys` until the person gives it the keyboard.
- The key hints are the FIRST row of every view, not a footer: a footer would be scrolled
  out of sight in any view taller than its window (the dashboard on a real store is).
- Selection is the engine's ring over plain Buttons (lesson names), not a cursor the mod
  keeps: `↑↓ select · enter open` when the view fits, `↑↓ scroll · tab select · enter
  open` when it does not. The row says which is true for the view as drawn.

## What was built

1. Read a lesson from the pane. A lesson's name on a Most used row, on an ineffective
   entry of Open and on every row of the list is a plain Button. Pressing it shows the
   lesson: name, level, kind (`lesson`, `guard`, `skill`), `ineffective` when flagged,
   the three counters, when it last fired, its guard patterns, attached files, path,
   description and text (wrapped, never cut; past 300 lines one line says how many more
   and names `compound show <name>`). `Reading the lesson…` while the CLI is asked; the
   reason when it cannot say. `b` goes back to where it was pressed.
2. All lessons (`a`): every lesson and skill by level from `compound list --json`, each
   row a Button.
3. Open rows are followed by the command that settles them. The CLI gives the text in
   `status --json` (`command`, `decline`) and prints the same text in `compound status`.
   For errors there is no settling command; the pane shows `compound events --type
   error`, which reads them (a constant of `hooks/view.ts`, not from the CLI).
4. The key row.
5. Focus: see above. Tests in `hooks/ui.test.ts` mount the hooks on the terminal and
   desktop surfaces and press the Buttons.

CLI additions (read-only JSON): `status --json` gains `open.unsettled[].command`,
`.decline` and `open.ineffective[].command`; `show --json` gains `body` and `last`.

Keys: `a` all lessons (dashboard), `b` back (list, lesson), `r` refresh, `x` close; Tab
and the arrows move the ring, Enter opens; ctrl+x tab gives the pane the keyboard, Esc
returns it.

## Existing assertions changed

- `hooks/view.test.ts`, "the pane's data is what the CLI printed": the four
  `board.open.*` assertions compare objects (`{ text, command, more, lesson }`) where they
  compared strings; the texts are the same. The `STATUS` fixture's open rows gained the
  `command` / `decline` fields the CLI now gives (the candidate's `command: 'c'` became a
  real promote command).
- `hooks/ui.test.ts`, "/compound opens the dashboard": `expect(all).toContain(
  'release-notes-format')` (a Text) became a check that a Button keyed
  `open:release-notes-format` carries that label: the name is a Button now. The `STATUS`
  fixture's owed row gained `command` / `decline`.
- The test world of `hooks/ui.test.ts` answers `ui.close`, the pane's `list --json` and
  `show --json` with an exit code and an awaited delay.

No test was removed or weakened.

## Verified, and how

- `./run_tests.sh`, `claude plugin validate --strict .`, `claude plugin test .`,
  `tsc -p . --noEmit`: see the end of this file.
- Real interactive sessions under vhs, screenshots read by eye (throwaway store in
  `$TMPDIR/compound-ui-check`, never the real one): the pane opens without the keyboard and
  typing goes to the prompt; ctrl+x tab gives it the keys and the ring is on the first
  lesson row; Down moves the ring; Enter opens the lesson with the CLI's text; `b` returns
  with the ring on that lesson's row; `a` lists every lesson with the ring on the first
  row; in a list of 34 lessons and skills (taller than the window) the key row says `↑↓ scroll · tab
  select`, Down scrolls, Tab walks, a lesson opened from far down the list opens at its
  top, and `b` returns with that row ringed and in the window; `r` re-reads; Esc returns
  the keyboard; `x` closes.

## Not verified

- A mouse click on a row or on the pane (vhs sends keys only). The engine's docs say a
  click presses a Button and gives the pane the keyboard.
- The desktop surface, beyond the mounted-hook tests: no desktop session was run. There
  the key row is the Buttons alone, with no terminal key named.
- `$.ui.scroll` and `$.ui.focus` cannot be answered in the test kit (`no implementation
  for ui.scroll`, whatever `on('ui.scroll', ...)` the test registers), so the scroll to
  the top and the ring's move are covered by the vhs sessions only. The mod catches both
  calls' failures and goes on.
- The docked placement (fullscreen terminal from 110 columns) was not looked at; the vhs
  terminal is 100 columns, where the pane is inline above the prompt.
- `docs/media/demo-2-pane.png` and `demo.gif` in the README still show the pane as it was.

## The views, rendered from the real store

`hooks/view.ts` under bun, given this machine's `compound status --json`, `events --json
--limit 80`, `list --json` and `show zsh-equals-word --json` (read-only calls). A Button
with a hotkey is written as the terminal draws it (`a: all lessons`). Colour is not shown.

```
=== dashboard (pane without the keyboard) at 100 columns ===
+----------------------------------------------------------------------------------------------------+
|ctrl+x tab for keys  a: all lessons  r: refresh  x: close                                           |
|▲ 2 warnings  10 checks  mod, cli                                                                   |
|                                                                                                    |
|Compound interest  since 3 Oct                                                                      |
|  ◆ 11 reuses offered  ■ 4 calls stopped by a guard  ↺ 17 lessons recalled  ✔ 79 lessons recorded   |
|                                                                                                    |
|Open                                                                                                |
|  ▲ 2 ineffective lessons                                                                           |
|    agent-worktree-check-base (recalled 9 times)                                                    |
|      compound add --update --name agent-worktree-check-base --match RE                             |
|    zsh-nomatch-glob (recalled 4 times)                                                             |
|      compound add --update --name zsh-nomatch-glob --match RE                                      |
|  ○ 4 lessons declined                                                                              |
|                                                                                                    |
|Levels                                                                                              |
|  project   0 lessons (0 guards)  0 skills                                                          |
|  user     33 lessons (7 guards)  4 skills                                                          |
|  general   0 lessons (0 guards)  2 skills                                                          |
|                                                                                                    |
|Most used                       ◆ reused     ■ guarded    ↺ recalled                                |
|  agent-worktree-check-base     0            0            9 ▇▇▇▇▇▇                                  |
|  zsh-equals-word               0            2 ▇          3 ▇▇                                      |
|  zsh-nomatch-glob              1 ▇          0            4 ▇▇▇                                     |
|  patch-scripts-match-current…  4 ▇▇▇        0            0                                         |
|  chain-commit-with-and         0            1 ▇          0                                         |
|  ci-poll-in-background         0            0            1 ▇                                       |
|                                                                                                    |
|Recent                                                                                              |
|  13m ✔ recorded merge-in-a-scratch-worktree                                                        |
|  16m ◆ reused   1 earlier request                                                                  |
|  16m ◆ reused   2 earlier requests                                                                 |
|  21m ◆ reused   2 earlier requests                                                                 |
|  25m ↺ recalled zsh-nomatch-glob (ineffective)                                                     |
|  27m ↺ recalled zsh-nomatch-glob (ineffective)                                                     |
|  40m ↺ recalled zsh-equals-word                                                                    |
|  41m ◆ reused   1 earlier request                                                                  |
+----------------------------------------------------------------------------------------------------+

=== dashboard (pane without the keyboard) at 60 columns ===
+------------------------------------------------------------+
|ctrl+x tab for keys  a: all lessons  r: refresh  x: close   |
|▲ 2 warnings  10 checks  mod, cli                           |
|                                                            |
|Compound interest  since 3 Oct                              |
|  ◆ 11 reuses offered  ■ 4 calls stopped by a guard         |
|  ↺ 17 lessons recalled  ✔ 79 lessons recorded              |
|                                                            |
|Open                                                        |
|  ▲ 2 ineffective lessons                                   |
|    agent-worktree-check-base (recalled 9 times)            |
|      compound add --update --name agent-worktree-check-base|
|      --match RE                                            |
|    zsh-nomatch-glob (recalled 4 times)                     |
|      compound add --update --name zsh-nomatch-glob --match |
|      RE                                                    |
|  ○ 4 lessons declined                                      |
|                                                            |
|Levels                                                      |
|  project   0 lessons (0 guards)  0 skills                  |
|  user     33 lessons (7 guards)  4 skills                  |
|  general   0 lessons (0 guards)  2 skills                  |
|                                                            |
|Most used               ◆ reused     ■ guarded    ↺ recalled|
|  agent-worktree-chec…  0            0            9 ▇▇▇▇▇▇  |
|  zsh-equals-word       0            2 ▇          3 ▇▇      |
|  zsh-nomatch-glob      1 ▇          0            4 ▇▇▇     |
|  patch-scripts-match…  4 ▇▇▇        0            0         |
|  chain-commit-with-a…  0            1 ▇          0         |
|  ci-poll-in-backgrou…  0            0            1 ▇       |
|                                                            |
|Recent                                                      |
|  13m ✔ recorded merge-in-a-scratch-worktree                |
|  16m ◆ reused   1 earlier request                          |
|  16m ◆ reused   2 earlier requests                         |
|  21m ◆ reused   2 earlier requests                         |
|  25m ↺ recalled zsh-nomatch-glob (ineffective)             |
|  27m ↺ recalled zsh-nomatch-glob (ineffective)             |
|  40m ↺ recalled zsh-equals-word                            |
|  41m ◆ reused   1 earlier request                          |
+------------------------------------------------------------+

=== dashboard (pane without the keyboard) at 40 columns ===
+----------------------------------------+
|ctrl+x tab: keys  a: all  r: refresh    |
|x: close                                |
|▲ 2 warnings  10 checks  mod, cli       |
|                                        |
|Compound interest  since 3 Oct          |
|  ◆ 11 reuses offered                   |
|  ■ 4 calls stopped by a guard          |
|  ↺ 17 lessons recalled                 |
|  ✔ 79 lessons recorded                 |
|                                        |
|Open                                    |
|  ▲ 2 ineffective lessons               |
|    agent-worktree-check-base (recalled…|
|      compound add --update --name      |
|      agent-worktree-check-base --match |
|      RE                                |
|    zsh-nomatch-glob (recalled 4 times) |
|      compound add --update --name      |
|      zsh-nomatch-glob --match RE       |
|  ○ 4 lessons declined                  |
|                                        |
|Levels lessons (guards) skills          |
|  project    0      (0)      0          |
|  user      33      (7)      4          |
|  general    0      (0)      2          |
|                                        |
|Most used            ◆      ■      ↺    |
|  agent-worktree-c…  0      0      9 ▇▇▇|
|  zsh-equals-word    0      2 ▇    3 ▇  |
|  zsh-nomatch-glob   1 ▇    0      4 ▇  |
|  patch-scripts-ma…  4 ▇    0      0    |
|  chain-commit-wit…  0      1 ▇    0    |
|  ci-poll-in-backg…  0      0      1 ▇  |
|                                        |
|Recent                                  |
|  13m ✔ recorded merge-in-a-scratch-wor…|
|  16m ◆ reused   1 earlier request      |
|  16m ◆ reused   2 earlier requests     |
|  21m ◆ reused   2 earlier requests     |
|  25m ↺ recalled zsh-nomatch-glob (inef…|
|  27m ↺ recalled zsh-nomatch-glob (inef…|
|  40m ↺ recalled zsh-equals-word        |
|  41m ◆ reused   1 earlier request      |
+----------------------------------------+

=== dashboard key row, pane with the keyboard, taller than its window at 100 columns ===
+----------------------------------------------------------------------------------------------------+
|↑↓ scroll · tab select · enter open · esc to the prompt  a: all lessons  r: refresh  x: close       |
+----------------------------------------------------------------------------------------------------+

=== dashboard key row, pane with the keyboard, taller than its window at 60 columns ===
+------------------------------------------------------------+
|↑↓ scroll · tab select · enter open · esc prompt  a: all    |
|r: refresh  x: close                                        |
+------------------------------------------------------------+

=== dashboard key row, pane with the keyboard, taller than its window at 40 columns ===
+----------------------------------------+
|↑↓ scroll · tab select · enter open     |
|esc prompt  a: all  r: refresh  x: close|
+----------------------------------------+

=== all lessons (pane with the keyboard) at 100 columns ===
+----------------------------------------------------------------------------------------------------+
|↑↓ scroll · tab select · enter open · esc to the prompt  b: back  r: refresh  x: close              |
|All lessons  33 lessons (7 guards)  6 skills  ◆ reused  ■ guarded  ↺ recalled                       |
|                                                                                                    |
|project  nothing recorded                                                                           |
|                                                                                                    |
|user  33 lessons (7 guards)  4 skills                                                               |
|  agent-not-finished-until-handba…  lesson  ◆ 0  ■ 0  ↺ 0  Use when a subagent's task notification …|
|  agent-worktree-check-base         lesson  ◆ 0  ■ 0  ↺ 9  Use when dispatching an Agent with isola…|
|  artifact-publish-refuses-ufffd    lesson  ◆ 0  ■ 0  ↺ 0  Use when publishing an Artifact page tha…|
|  background-task-exit-is-last-co…  lesson  ◆ 0  ■ 0  ↺ 0  Use when reading the completion notifica…|
|  brew-doctor-exits-1               guard   ◆ 0  ■ 0  ↺ 0  Use when brew doctor is the last step of…|
|  chain-commit-with-and             guard   ◆ 0  ■ 1  ↺ 0  Use when a Bash tool command runs a patc…|
|  ci-checks-for-commit              lesson  ◆ 0  ■ 0  ↺ 0  Use when asked whether CI passed for a c…|
|  ci-poll-in-background             lesson  ◆ 0  ■ 0  ↺ 1  Use when waiting for a GitHub Actions ru…|
|  codex-exec-usage-limit            lesson  ◆ 0  ■ 0  ↺ 0  Use when running a long codex exec revie…|
|  expected-absence-or-true          lesson  ◆ 0  ■ 0  ↺ 0  Use when running ls or grep to show that…|
|  gate-commit-on-pass-line          guard   ◆ 0  ■ 0  ↺ 0  Use when a git commit is chained after a…|
|  gmail-mcp-read-attachment         lesson  ◆ 0  ■ 0  ↺ 0  Use when a detail exists only in a PDF a…|
|  gpt2-last-hidden-state-has-ln-f   lesson  ◆ 0  ■ 0  ↺ 0  Use when building a logit lens over Hugg…|
|  heredoc-ends-and-chain            lesson  ◆ 0  ■ 0  ↺ 0  Use when a Bash command has a heredoc (c…|
|  inline-python-in-zsh-quotes       lesson  ◆ 0  ■ 0  ↺ 0  Use when writing an inline python3 -c pr…|
|  kill-script-leaves-children       lesson  ◆ 0  ■ 0  ↺ 0  Use when stopping a long-running shell s…|
|  macos-no-timeout                  guard   ◆ 0  ■ 1  ↺ 0  Use when wrapping a command in timeout, …|
|  patch-scripts-match-current-text  lesson  ◆ 4  ■ 0  ↺ 0  Use when editing files with a Python pat…|
|  pgrep-pattern-matches-own-shell   lesson  ◆ 0  ■ 0  ↺ 0  Use when a command uses pkill -f or pgre…|
|  playwright-mcp-output-dir         lesson  ◆ 0  ■ 0  ↺ 0  Use when taking screenshots or doing bro…|
|  plistlib-stdin-not-seekable       guard   ◆ 0  ■ 0  ↺ 0  Use when reading a plist from stdin with…|
|  read-agent-figures-from-output    lesson  ◆ 0  ■ 0  ↺ 0  Use when reporting a count or figure tha…|
|  rm-glob-after-cd-denied           lesson  ◆ 0  ■ 0  ↺ 0  Use when an rm -rf of a relative glob or…|
|  sed-range-from-empty-variable     lesson  ◆ 0  ■ 0  ↺ 0  Use when computing a sed -n line range f…|
|  sed-substitute-needs-g            lesson  ◆ 0  ■ 0  ↺ 0  Use when deriving a script from another …|
|  shared-tree-no-add-all-no-stash   lesson  ◆ 1  ■ 0  ↺ 0  Use when running git add or git stash in…|
|  state-no-mocks-in-agent-prompts   lesson  ◆ 1  ■ 0  ↺ 0  Use when dispatching a subagent to write…|
|  verify-push-with-ls-remote        lesson  ◆ 0  ■ 0  ↺ 0  Use when checking that a git push reache…|
|  watcher-grep-phrase-not-in-prom…  lesson  ◆ 0  ■ 0  ↺ 0  Use when writing a watcher that greps an…|
|  zsh-equals-word                   guard   ◆ 0  ■ 2  ↺ 3  Use when a zsh command line prints a sep…|
|  zsh-function-name-is-alias        guard   ◆ 0  ■ 0  ↺ 0  Use when defining a short inline shell f…|
|  zsh-no-word-split                 lesson  ◆ 0  ■ 0  ↺ 0  Use when a zsh command passes several wo…|
|  zsh-nomatch-glob                  lesson  ◆ 1  ■ 0  ↺ 4  Use when a zsh command has an unquoted g…|
|  bib-duplicate-check               skill   ◆ 0  ■ 0  ↺ 0  Use when adding entries to an existing B…|
|  cdl-bib-cite                      skill   ◆ 0  ■ 0  ↺ 0  Use when filling a placeholder citation …|
|  history-surfer                    skill   ◆ 0  ■ 0  ↺ 0  Use when the user wants to recall, searc…|
|  speckit-execute                   skill   ◆ 1  ■ 0  ↺ 0  Run the full Spec Kit pipeline (plan → t…|
|                                                                                                    |
|general  0 lessons (0 guards)  2 skills                                                             |
|  learn                             skill   ◆ 0  ■ 0  ↺ 0  Use when a "[compound]" message says the…|
|  reuse                             skill   ◆ 0  ■ 0  ↺ 0  Use when starting a substantial task (bu…|
+----------------------------------------------------------------------------------------------------+

=== all lessons (pane with the keyboard) at 60 columns ===
+------------------------------------------------------------+
|↑↓ scroll · tab select · enter open · esc prompt  b: back   |
|r: refresh  x: close                                        |
|All lessons  33 lessons (7 guards)  6 skills  ◆ reused      |
|  ■ guarded  ↺ recalled                                     |
|                                                            |
|project  nothing recorded                                   |
|                                                            |
|user  33 lessons (7 guards)  4 skills                       |
|  agent-not-finished-until-handba…  lesson  ◆ 0  ■ 0  ↺ 0   |
|  agent-worktree-check-base         lesson  ◆ 0  ■ 0  ↺ 9   |
|  artifact-publish-refuses-ufffd    lesson  ◆ 0  ■ 0  ↺ 0   |
|  background-task-exit-is-last-co…  lesson  ◆ 0  ■ 0  ↺ 0   |
|  brew-doctor-exits-1               guard   ◆ 0  ■ 0  ↺ 0   |
|  chain-commit-with-and             guard   ◆ 0  ■ 1  ↺ 0   |
|  ci-checks-for-commit              lesson  ◆ 0  ■ 0  ↺ 0   |
|  ci-poll-in-background             lesson  ◆ 0  ■ 0  ↺ 1   |
|  codex-exec-usage-limit            lesson  ◆ 0  ■ 0  ↺ 0   |
|  expected-absence-or-true          lesson  ◆ 0  ■ 0  ↺ 0   |
|  gate-commit-on-pass-line          guard   ◆ 0  ■ 0  ↺ 0   |
|  gmail-mcp-read-attachment         lesson  ◆ 0  ■ 0  ↺ 0   |
|  gpt2-last-hidden-state-has-ln-f   lesson  ◆ 0  ■ 0  ↺ 0   |
|  heredoc-ends-and-chain            lesson  ◆ 0  ■ 0  ↺ 0   |
|  inline-python-in-zsh-quotes       lesson  ◆ 0  ■ 0  ↺ 0   |
|  kill-script-leaves-children       lesson  ◆ 0  ■ 0  ↺ 0   |
|  macos-no-timeout                  guard   ◆ 0  ■ 1  ↺ 0   |
|  patch-scripts-match-current-text  lesson  ◆ 4  ■ 0  ↺ 0   |
|  pgrep-pattern-matches-own-shell   lesson  ◆ 0  ■ 0  ↺ 0   |
|  playwright-mcp-output-dir         lesson  ◆ 0  ■ 0  ↺ 0   |
|  plistlib-stdin-not-seekable       guard   ◆ 0  ■ 0  ↺ 0   |
|  read-agent-figures-from-output    lesson  ◆ 0  ■ 0  ↺ 0   |
|  rm-glob-after-cd-denied           lesson  ◆ 0  ■ 0  ↺ 0   |
|  sed-range-from-empty-variable     lesson  ◆ 0  ■ 0  ↺ 0   |
|  sed-substitute-needs-g            lesson  ◆ 0  ■ 0  ↺ 0   |
|  shared-tree-no-add-all-no-stash   lesson  ◆ 1  ■ 0  ↺ 0   |
|  state-no-mocks-in-agent-prompts   lesson  ◆ 1  ■ 0  ↺ 0   |
|  verify-push-with-ls-remote        lesson  ◆ 0  ■ 0  ↺ 0   |
|  watcher-grep-phrase-not-in-prom…  lesson  ◆ 0  ■ 0  ↺ 0   |
|  zsh-equals-word                   guard   ◆ 0  ■ 2  ↺ 3   |
|  zsh-function-name-is-alias        guard   ◆ 0  ■ 0  ↺ 0   |
|  zsh-no-word-split                 lesson  ◆ 0  ■ 0  ↺ 0   |
|  zsh-nomatch-glob                  lesson  ◆ 1  ■ 0  ↺ 4   |
|  bib-duplicate-check               skill   ◆ 0  ■ 0  ↺ 0   |
|  cdl-bib-cite                      skill   ◆ 0  ■ 0  ↺ 0   |
|  history-surfer                    skill   ◆ 0  ■ 0  ↺ 0   |
|  speckit-execute                   skill   ◆ 1  ■ 0  ↺ 0   |
|                                                            |
|general  0 lessons (0 guards)  2 skills                     |
|  learn                             skill   ◆ 0  ■ 0  ↺ 0   |
|  reuse                             skill   ◆ 0  ■ 0  ↺ 0   |
+------------------------------------------------------------+

=== all lessons (pane with the keyboard) at 40 columns ===
+----------------------------------------+
|↑↓ scroll · tab select · enter open     |
|esc prompt  b: back  r: refresh         |
|x: close                                |
|All lessons  33 lessons (7 guards)      |
|  6 skills                              |
|                                        |
|project  nothing recorded               |
|                                        |
|user  33 lessons (7 guards)  4 skills   |
|  agent-not-finished-until-hand…  lesson|
|  agent-worktree-check-base       lesson|
|  artifact-publish-refuses-ufffd  lesson|
|  background-task-exit-is-last-…  lesson|
|  brew-doctor-exits-1             guard |
|  chain-commit-with-and           guard |
|  ci-checks-for-commit            lesson|
|  ci-poll-in-background           lesson|
|  codex-exec-usage-limit          lesson|
|  expected-absence-or-true        lesson|
|  gate-commit-on-pass-line        guard |
|  gmail-mcp-read-attachment       lesson|
|  gpt2-last-hidden-state-has-ln…  lesson|
|  heredoc-ends-and-chain          lesson|
|  inline-python-in-zsh-quotes     lesson|
|  kill-script-leaves-children     lesson|
|  macos-no-timeout                guard |
|  patch-scripts-match-current-t…  lesson|
|  pgrep-pattern-matches-own-she…  lesson|
|  playwright-mcp-output-dir       lesson|
|  plistlib-stdin-not-seekable     guard |
|  read-agent-figures-from-output  lesson|
|  rm-glob-after-cd-denied         lesson|
|  sed-range-from-empty-variable   lesson|
|  sed-substitute-needs-g          lesson|
|  shared-tree-no-add-all-no-sta…  lesson|
|  state-no-mocks-in-agent-promp…  lesson|
|  verify-push-with-ls-remote      lesson|
|  watcher-grep-phrase-not-in-pr…  lesson|
|  zsh-equals-word                 guard |
|  zsh-function-name-is-alias      guard |
|  zsh-no-word-split               lesson|
|  zsh-nomatch-glob                lesson|
|  bib-duplicate-check             skill |
|  cdl-bib-cite                    skill |
|  history-surfer                  skill |
|  speckit-execute                 skill |
|                                        |
|general  0 lessons (0 guards)  2 skills |
|  learn                           skill |
|  reuse                           skill |
+----------------------------------------+

=== lesson zsh-equals-word (pane with the keyboard) at 100 columns ===
+----------------------------------------------------------------------------------------------------+
|esc to the prompt  b: back  r: refresh  x: close                                                    |
|zsh-equals-word                                                                                     |
|user · guard                                                                                        |
|◆ 0 reused  ■ 2 guarded  ↺ 3 recalled                                                               |
|last fired 40m ago (recalled)                                                                       |
|guard pattern                                                                                       |
|  (^|[;&|]\s*)echo\s+=+                                                                             |
|/Users/jmanning/.claude/compound/lessons/zsh-equals-word                                            |
|                                                                                                    |
|Use when a zsh command line prints a separator with a bare word starting with "=" (echo ====== after|
|";" or "&&").                                                                                       |
|                                                                                                    |
|Print a separator with printf '%s\n' '=====' (or '----'), or single-quote it, or omit it.           |
|zsh expands a bare word starting with "=" as an =command path lookup, so `echo ======`              |
|in a compound command fails with "not found" and the rest of the chain is lost.                     |
+----------------------------------------------------------------------------------------------------+

=== lesson zsh-equals-word (pane with the keyboard) at 60 columns ===
+------------------------------------------------------------+
|esc to the prompt  b: back  r: refresh  x: close            |
|zsh-equals-word                                             |
|user · guard                                                |
|◆ 0 reused  ■ 2 guarded  ↺ 3 recalled                       |
|last fired 40m ago (recalled)                               |
|guard pattern                                               |
|  (^|[;&|]\s*)echo\s+=+                                     |
|/Users/jmanning/.claude/compound/lessons/zsh-equals-word    |
|                                                            |
|Use when a zsh command line prints a separator with a bare  |
|word starting with "=" (echo ====== after ";" or "&&").     |
|                                                            |
|Print a separator with printf '%s\n' '=====' (or '----'), or|
|single-quote it, or omit it.                                |
|zsh expands a bare word starting with "=" as an =command    |
|path lookup, so `echo ======`                               |
|in a compound command fails with "not found" and the rest of|
|the chain is lost.                                          |
+------------------------------------------------------------+

=== lesson zsh-equals-word (pane with the keyboard) at 40 columns ===
+----------------------------------------+
|esc prompt  b: back  r: refresh         |
|x: close                                |
|zsh-equals-word                         |
|user · guard                            |
|◆ 0 reused  ■ 2 guarded  ↺ 3 recalled   |
|last fired 40m ago (recalled)           |
|guard pattern                           |
|  (^|[;&|]\s*)echo\s+=+                 |
|/Users/jmanning/.claude/compound/lessons|
|/zsh-equals-word                        |
|                                        |
|Use when a zsh command line prints a    |
|separator with a bare word starting with|
|"=" (echo ====== after ";" or "&&").    |
|                                        |
|Print a separator with printf '%s\n'    |
|'=====' (or '----'), or single-quote it,|
|or omit it.                             |
|zsh expands a bare word starting with   |
|"=" as an =command path lookup, so `echo|
|======`                                 |
|in a compound command fails with "not   |
|found" and the rest of the chain is     |
|lost.                                   |
+----------------------------------------+

=== lesson, while the CLI is asked at 60 columns ===
+------------------------------------------------------------+
|ctrl+x tab for keys  b: back  r: refresh  x: close          |
|zsh-equals-word                                             |
|Reading the lesson…                                         |
+------------------------------------------------------------+

=== lesson, when the CLI cannot show it at 60 columns ===
+------------------------------------------------------------+
|ctrl+x tab for keys  b: back  r: refresh  x: close          |
|gone                                                        |
|✖ compound show exit 1: compound: no lesson or skill named  |
|  'gone'                                                    |
+------------------------------------------------------------+
```

## The recorded session (dev/ui-check.sh, vhs, 100 columns)

The tape now types into the prompt with the pane open, gives the pane the keyboard, opens
a lesson, goes back, opens the list, opens a lesson from it and goes back. Run once on the
final code; 82 screenshots, the `4-pane-*` ones read by eye. What they showed:

```
4-pane-with-the-keys      row 1: ↑↓ select · enter open · esc to the prompt  a: all lessons  r: refresh  x: close
                          the ring on the first Most used row (no-marker-echo)
4-pane-lesson             esc to the prompt  b: back  r: refresh  x: close
                          no-marker-echo / project · guard / ◆ 0 reused  ■ 1 guarded  ↺ 0 recalled
                          last fired 1m ago (guarded) / guard pattern / echo\s+GUARDED_MARKER / path / when / text
4-pane-all-lessons        All lessons  3 lessons (2 guards)  2 skills  ◆ reused  ■ guarded  ↺ recalled
                          project: deploy-needs-target (ringed), no-marker-echo, release-notes-format; general: learn, reuse
5-status-text             after Esc the prompt took `/compound status`; the pane's row 1 is `ctrl+x tab for keys ...` again
```

## Checks on the final code

```
./run_tests.sh                       OK: 13 test files
claude plugin validate --strict .    Validation passed
claude plugin test .                 189 pass, 0 fail (7 files)
tsc -p . --noEmit                    no output
```
