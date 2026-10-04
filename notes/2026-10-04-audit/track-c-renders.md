# Track C renders (2026-10-04)

What the band, the pane and the CLI's text print after the "more informative indicators"
change, rendered for real: the pane and the band by `hooks/view.ts` under bun
(`boardFrom` given this machine's `compound status --json` and `compound events --json
--limit 20`), the CLI by running it. Colour is not shown here: a terminal gets it, a
file does not.

## Before and after

```
band, reuse      before  ◆ compound reuse found · 2 lessons and skills, 1 earlier request
                 after   ◆ compound reuse found · bibdupcheck.py, cdl-bib-cite · 1 earlier request
band, owed       before  ● compound lesson owed   ✓ failed → ✓ fixed → ● owed → ○ recorded
                 after   ● compound lesson owed · ./deploy.sh --target staging   ✓ failed → ✓ fixed → ● owed → ○ recorded
band, guard      before  ■ compound guard stopped a call · zsh-equals-word
                 after   ■ compound guard stopped a call · zsh-equals-word  echo ==== separator ====
band, idle       before  (a blank row after the spinner)
                 after   ◇ compound nothing to reuse          (dim, 3 s)
band, first run  before  (nothing)
                 after   ◇ compound ready · 34 lessons (7 guards)  /compound opens the dashboard
status entry     before  compound: 2 reusable          after  compound: reuse bibdupcheck.py +1
                 before  compound: lesson owed         after  compound: lesson owed: ./deploy.sh --target staging
toast            before  lesson zsh-equals-word moved to the user level
                 after   lesson moved to the user level: zsh-equals-word
totals           before  (none)
                 after   3 reuses offered · 4 calls stopped by a guard · 12 lessons recalled · 78 lessons recorded · since 3 Oct
levels           before  user   1 lesson   1 guard   0 skills
                 after   user   1 lesson  (1 guard)  0 skills
pane, recent     before  12:58 ◆ reuse    1 lesson or skill, 2 earlier requests
                 after      2m ◆ reused   speckit-execute · 2 earlier requests
```

## The pane and the band

```
=== pane at 100 columns ===
+----------------------------------------------------------------------------------------------------+
|▲ 2 warnings  9 checks  mod, cli                                                                    |
|                                                                                                    |
|Compound interest  since 3 Oct                                                                      |
|  ◆ 7 reuses offered  ■ 4 calls stopped by a guard  ↺ 14 lessons recalled  ✔ 78 lessons recorded    |
|                                                                                                    |
|Open                                                                                                |
|  ▲ 3 ineffective lessons                                                                           |
|    agent-worktree-check-base (recalled 9 times)                                                    |
|    zsh-equals-word (recalled 2 times)                                                              |
|    zsh-nomatch-glob (recalled 2 times)                                                             |
|  ○ 4 lessons declined                                                                              |
|                                                                                                    |
|Levels                                                                                              |
|  project   0 lessons (0 guards)  0 skills                                                          |
|  user     33 lessons (7 guards)  4 skills                                                          |
|  general   0 lessons (0 guards)  2 skills                                                          |
|                                                                                                    |
|Most used                       ◆ reused     ■ guarded    ↺ recalled                                |
|  agent-worktree-check-base     0            0            9 ▇▇▇▇▇▇                                  |
|  patch-scripts-match-current…  4 ▇▇▇        0            0                                         |
|  zsh-equals-word               0            2 ▇          2 ▇                                       |
|  zsh-nomatch-glob              1 ▇          0            2 ▇                                       |
|  chain-commit-with-and         0            1 ▇          0                                         |
|  ci-poll-in-background         0            0            1 ▇                                       |
|                                                                                                    |
|Recent                                                                                              |
|  25s ↺ recalled zsh-equals-word                                                                    |
|   1m · judge                                                                                       |
|   4m ◆ reused   compound                                                                           |
|   4m · judge                                                                                       |
|   4m ↺ recalled ci-poll-in-background                                                              |
|   5m ◆ reused   state-no-mocks-in-agent-prompts · 2 earlier requests                               |
|   6m ◆ reused   patch-scripts-match-current-text · 1 earlier request                               |
|   7m ◆ reused   patch-scripts-match-current-text · 1 earlier request                               |
+----------------------------------------------------------------------------------------------------+

=== pane at 60 columns ===
+------------------------------------------------------------+
|▲ 2 warnings  9 checks  mod, cli                            |
|                                                            |
|Compound interest  since 3 Oct                              |
|  ◆ 7 reuses offered  ■ 4 calls stopped by a guard          |
|  ↺ 14 lessons recalled  ✔ 78 lessons recorded              |
|                                                            |
|Open                                                        |
|  ▲ 3 ineffective lessons                                   |
|    agent-worktree-check-base (recalled 9 times)            |
|    zsh-equals-word (recalled 2 times)                      |
|    zsh-nomatch-glob (recalled 2 times)                     |
|  ○ 4 lessons declined                                      |
|                                                            |
|Levels                                                      |
|  project   0 lessons (0 guards)  0 skills                  |
|  user     33 lessons (7 guards)  4 skills                  |
|  general   0 lessons (0 guards)  2 skills                  |
|                                                            |
|Most used               ◆ reused     ■ guarded    ↺ recalled|
|  agent-worktree-chec…  0            0            9 ▇▇▇▇▇▇  |
|  patch-scripts-match…  4 ▇▇▇        0            0         |
|  zsh-equals-word       0            2 ▇          2 ▇       |
|  zsh-nomatch-glob      1 ▇          0            2 ▇       |
|  chain-commit-with-a…  0            1 ▇          0         |
|  ci-poll-in-backgrou…  0            0            1 ▇       |
|                                                            |
|Recent                                                      |
|  25s ↺ recalled zsh-equals-word                            |
|   1m · judge                                               |
|   4m ◆ reused   compound                                   |
|   4m · judge                                               |
|   4m ↺ recalled ci-poll-in-background                      |
|   5m ◆ reused   state-no-mocks-in-agent-prompts            |
|   6m ◆ reused   patch-scripts-match-current-text           |
|   7m ◆ reused   patch-scripts-match-current-text           |
+------------------------------------------------------------+

=== pane at 40 columns ===
+----------------------------------------+
|▲ 2 warnings  9 checks  mod, cli        |
|                                        |
|Compound interest  since 3 Oct          |
|  ◆ 7 reuses offered                    |
|  ■ 4 calls stopped by a guard          |
|  ↺ 14 lessons recalled                 |
|  ✔ 78 lessons recorded                 |
|                                        |
|Open                                    |
|  ▲ 3 ineffective lessons               |
|    agent-worktree-check-base (recalled…|
|    zsh-equals-word (recalled 2 times)  |
|    zsh-nomatch-glob (recalled 2 times) |
|  ○ 4 lessons declined                  |
|                                        |
|Levels lessons (guards) skills          |
|  project    0      (0)      0          |
|  user      33      (7)      4          |
|  general    0      (0)      2          |
|                                        |
|Most used            ◆      ■      ↺    |
|  agent-worktree-c…  0      0      9 ▇▇▇|
|  patch-scripts-ma…  4 ▇    0      0    |
|  zsh-equals-word    0      2 ▇    2 ▇  |
|  zsh-nomatch-glob   1 ▇    0      2 ▇  |
|  chain-commit-wit…  0      1 ▇    0    |
|  ci-poll-in-backg…  0      0      1 ▇  |
|                                        |
|Recent                                  |
|  25s ↺ recalled zsh-equals-word        |
|   1m · judge                           |
|   4m ◆ reused   compound               |
|   4m · judge                           |
|   4m ↺ recalled ci-poll-in-background  |
|   5m ◆ reused   state-no-mocks-in-agen…|
|   6m ◆ reused   patch-scripts-match-cu…|
|   7m ◆ reused   patch-scripts-match-cu…|
+----------------------------------------+

=== pane at 30 columns ===
+------------------------------+
|▲ 2 warnings  9 checks  mod,  |
|  cli                         |
|                              |
|Compound interest  since 3 Oct|
|  ◆ 7 reuses offered          |
|  ■ 4 calls stopped by a guard|
|  ↺ 14 lessons recalled       |
|  ✔ 78 lessons recorded       |
|                              |
|Open                          |
|  ▲ 3 ineffective lessons     |
|    agent-worktree-check-base…|
|    zsh-equals-word (recalled…|
|    zsh-nomatch-glob (recalle…|
|  ○ 4 lessons declined        |
|                              |
|Levels lessons (guards) skills|
|  project    0      (0)      0|
|  user      33      (7)      4|
|  general    0      (0)      2|
|                              |
|Most used   ◆      ■      ↺   |
|  agent-w…  0      0      9 ▇…|
|  patch-s…  4 ▇    0      0   |
|  zsh-equ…  0      2 ▇    2 ▇ |
|  zsh-nom…  1 ▇    0      2 ▇ |
|  chain-c…  0      1 ▇    0   |
|  ci-poll…  0      0      1 ▇ |
|                              |
|Recent                        |
|  25s ↺ zsh-equals-word       |
|   1m · judge                 |
|   4m ◆ compound              |
|   4m · judge                 |
|   4m ↺ ci-poll-in-background |
|   5m ◆ state-no-mocks-in-age…|
|   6m ◆ patch-scripts-match-c…|
|   7m ◆ patch-scripts-match-c…|
+------------------------------+

=== band at 100 columns ===
◇ compound ready · /compound opens the dashboard                                                       <- first prompt, short
◇ compound ready · 34 lessons (7 guards)  /compound opens the dashboard                                <- first reuse check, nothing found
◇ compound nothing to reuse                                                                            <- later reuse check, nothing found (dim, 3 s)
⣾ compound checking for reusable work                                                                  <- reuse check running
◆ compound reuse found · bibdupcheck.py, cdl-bib-cite  34 lessons (7 guards) ready                     <- first reuse check, found
◆ compound reuse found · bibdupcheck.py, cdl-bib-cite, bib-duplicate-check +1 · 2 earlier requests     <- reuse found, with earlier requests
■ compound guard stopped a call · zsh-equals-word  echo ==== separator ====                            <- guard
↺ compound lesson recalled · python3-no-tomllib-use-tomli                                              <- recall
◌ compound watching for the fix   ● failed → ○ fixed → ○ owed → ○ recorded                             <- a call failed
● compound lesson owed · python3 -c "import tomli; print(tomli.__version__)"   ✓ ✓ ● owed ○            <- lesson owed
✔ compound lesson recorded · python3-no-tomllib-use-tomli   ✓ failed → ✓ fixed → ✓ owed → ✔ recorded   <- lesson recorded
● compound owed from earlier sessions · 2 lessons  ./deploy.sh --target staging                        <- owed from earlier sessions
▲ compound lesson to strengthen · zsh-nomatch-glob                                                     <- ineffective, then to strengthen
✖ compound 1 compound error · Claude is told at the next prompt  ● 1 owed                              <- error with a debt

=== band at 60 columns ===
◇ compound ready · /compound opens the dashboard               <- first prompt, short
◇ compound ready · 34 lessons (7 guards)                       <- first reuse check, nothing found
◇ compound nothing to reuse                                    <- later reuse check, nothing found (dim, 3 s)
⣾ compound checking for reusable work                          <- reuse check running
◆ compound reuse found · bibdupcheck.py, cdl-bib-cite          <- first reuse check, found
◆ compound reuse found · bibdupcheck.py, cdl-bib-cite +2       <- reuse found, with earlier requests
■ compound guard stopped a call · zsh-equals-word              <- guard
↺ compound lesson recalled · python3-no-tomllib-use-tomli      <- recall
◌ compound watching for the fix   ● failed ○ ○ ○               <- a call failed
● compound lesson owed · python3 -c "import tomli; print(to…   <- lesson owed
✔ compound lesson recorded · python3-no-tomllib-use-tomli      <- lesson recorded
● compound owed from earlier sessions · 2 lessons              <- owed from earlier sessions
▲ compound lesson to strengthen · zsh-nomatch-glob             <- ineffective, then to strengthen
✖ compound 1 compound error · Claude is told at the next pr…   <- error with a debt

=== band at 40 columns ===
◇ compound ready                           <- first prompt, short
◇ compound ready · 34 lessons (7 guards)   <- first reuse check, nothing found
◇ compound nothing to reuse                <- later reuse check, nothing found (dim, 3 s)
⣾ compound checking for reusable work      <- reuse check running
◆ compound reuse found · bibdupcheck.py…   <- first reuse check, found
◆ compound reuse found · bibdupcheck.py…   <- reuse found, with earlier requests
■ compound guard stopped a call · zsh-e…   <- guard
↺ compound lesson recalled · python3-no…   <- recall
◌ compound watching for the fix            <- a call failed
● compound lesson owed · python3 -c "im…   <- lesson owed
✔ compound lesson recorded · python3-no…   <- lesson recorded
● compound owed from earlier sessions      <- owed from earlier sessions
▲ compound lesson to strengthen · zsh-n…   <- ineffective, then to strengthen
✖ compound 1 compound error · Claude is…   <- error with a debt

=== band at 30 columns ===
◇ compound ready                 <- first prompt, short
◇ compound ready · 34 lessons…   <- first reuse check, nothing found
◇ compound nothing to reuse      <- later reuse check, nothing found (dim, 3 s)
⣾ compound checking for reusa…   <- reuse check running
◆ compound reuse found · bibd…   <- first reuse check, found
◆ compound reuse found · bibd…   <- reuse found, with earlier requests
■ compound guard stopped a ca…   <- guard
↺ compound lesson recalled       <- recall
◌ compound watching for the f…   <- a call failed
● compound lesson owed · pyth…   <- lesson owed
✔ compound lesson recorded       <- lesson recorded
● compound owed from earlier …   <- owed from earlier sessions
▲ compound lesson to strength…   <- ineffective, then to strengthen
✖ compound 1 compound error      <- error with a debt
```

## `compound status` (COLUMNS=100)

```
Health
  (nine rows: PASS/WARN/FAIL, the check, its detail)

Compound interest
  7 reuses offered · 4 calls stopped by a guard · 14 lessons recalled · 78 lessons recorded · since 3 Oct

Levels
  project   0 lessons  (0 guards)  0 skills
  user     33 lessons  (7 guards)  4 skills
  general   0 lessons  (0 guards)  2 skills

Lessons
  name                              level  kind    reused  guarded  recalled  flag
  agent-worktree-check-base         user   lesson  0       0        9         ineffective
  chain-commit-with-and             user   guard   0       1        0
  ci-poll-in-background             user   lesson  0       0        1
  macos-no-timeout                  user   guard   0       1        0
  patch-scripts-match-current-text  user   lesson  4       0        0
  shared-tree-no-add-all-no-stash   user   lesson  1       0        0
  state-no-mocks-in-agent-prompts   user   lesson  1       0        0
  zsh-equals-word                   user   guard   0       2        2         ineffective
  zsh-nomatch-glob                  user   lesson  1       0        2         ineffective
  speckit-execute                   user   skill   1       0        0
  24 lessons never used (`compound list` shows them)

Recent
  24m  declined  agent-a0198f33ca9da0709  Not the failure agent-worktree-check-base describes: the …
  17m  recalled  claude-skill-compounder  agent-worktree-check-base
   7m  reused    claude-skill-compounder  patch-scripts-match-current-text
   6m  reused    claude-skill-compounder  patch-scripts-match-current-text
   5m  reused    claude-skill-compounder  state-no-mocks-in-agent-prompts
   4m  recalled  claude-skill-compounder  ci-poll-in-background
   4m  judge     claude-skill-compounder
   4m  reused    claude-skill-compounder  bin/compound
   1m  judge     claude-skill-compounder
  25s  recalled  claude-skill-compounder  zsh-equals-word

Open
  ineffective  agent-worktree-check-base (user): recalled 9 times and the failure came back. Add a match (compound add --update --name agent-worktree-check-base --match RE), attach a script or rewrite the description
  ineffective  zsh-equals-word (user): recalled 2 times and the failure came back. Add a match (compound add --update --name zsh-equals-word --match RE), attach a script or rewrite the description
  ineffective  zsh-nomatch-glob (user): recalled 2 times and the failure came back. Add a match (compound add --update --name zsh-nomatch-glob --match RE), attach a script or rewrite the description
  declined     31m 09f47a44: the recalled lesson does not describe this failure: wc -l was given a glob that matched a directory (notes/2026-10-04-audit/general-pool), which is 'Is a directory', not zsh's 'no matches found'; a guard cannot know which globs match nothing, so no pattern would be right
  declined     31m 09f47a44: The failed call was not a zsh no-match glob: every glob matched; wc exited 1 because one match (notes/2026-10-04-audit/general-pool) is a directory. The lesson does not describe this failure.
  declined     25m 09f47a44: the recalled lesson does not describe this failure: the failing call was a track agent's inline Python patch of a test file inside its worktree, not a worktree based on the wrong commit; the lesson is about which commit a new worktree starts from
  declined     24m 09f47a44: Not the failure agent-worktree-check-base describes: the worktree base was right. The harness refused a long 'cd && python3 heredoc' command as too complex to verify it stays in the worktree; the fix is to write the script to a file and run it with a plain command.
```

## `compound list` (COLUMNS=120, first rows)

```
LEVEL    KIND    NAME                                  REUSED  GUARDED  RECALLED  FLAG         WHEN
user     lesson  agent-not-finished-until-handback     0       0        0                      Use when a subagent's ta…
user     lesson  agent-worktree-check-base             0       0        9         ineffective  Use when dispatching an …
user     lesson  artifact-publish-refuses-ufffd        0       0        0                      Use when publishing an A…
user     lesson  background-task-exit-is-last-command  0       0        0                      Use when reading the com…
user     guard   brew-doctor-exits-1                   0       0        0                      Use when brew doctor is …
user     guard   chain-commit-with-and                 0       1        0                      Use when a Bash tool com…
user     lesson  ci-checks-for-commit                  0       0        0                      Use when asked whether C…
```

## `compound list` (COLUMNS=70, first rows: the description has a line of its own)

```
LEVEL    KIND    NAME                                  REUSED  GUARDED  RECALLED  FLAG
user     lesson  agent-not-finished-until-handback     0       0        0
    Use when a subagent's task notification says it stopped with back…
user     lesson  agent-worktree-check-base             0       0        9         ineffective
    Use when dispatching an Agent with isolation 'worktree'.
user     lesson  artifact-publish-refuses-ufffd        0       0        0
    Use when publishing an Artifact page that embeds record data (nam…
```

## `compound find zsh glob python` (COLUMNS=100)

```
lesson inline-python-in-zsh-quotes (user), matched 2 of 3 words: Use when writing an inline python3…
  -> /Users/jmanning/.claude/compound/lessons/inline-python-in-zsh-quotes
lesson zsh-nomatch-glob (user), matched 2 of 3 words: Use when a zsh command has an unquoted glob t…
  -> /Users/jmanning/.claude/compound/lessons/zsh-nomatch-glob
skill cdl-bib-cite (user), matched 2 of 3 words: Use when filling a placeholder citation or adding …
  -> /Users/jmanning/.claude/skills/cdl-bib-cite
```

## `compound events --limit 8` (COLUMNS=100)

```
 7m  reuse   08894c50  claude-skill-compounder  patch-scripts-match-current-text
 6m  reuse   47056f73  claude-skill-compounder  patch-scripts-match-current-text
 5m  reuse   64e09bb1  claude-skill-compounder  state-no-mocks-in-agent-prompts
 4m  recall  09f47a44  claude-skill-compounder  ci-poll-in-background
 4m  judge   31a13997  claude-skill-compounder
 4m  reuse   31a13997  claude-skill-compounder  bin/compound
 1m  judge   e0a87221  claude-skill-compounder
26s  recall  09f47a44  claude-skill-compounder  zsh-equals-word
```

(`judge` is an event type another branch writes; a type this CLI has no word for is
shown by its name.)

## A recorded session (dev/ui-check.sh, vhs, 100 columns)

Run once on this change; 76 screenshots, looked at by eye. What they showed:

```
◆ compound reuse found · release-notes-format  2 lessons (1 guard) ready
      status entry: compound: reuse release-notes-format
■ compound guard stopped a call · no-marker-echo  echo GUARDED_MARKER_42
      status entry: compound: guard no-marker-echo
● compound lesson owed · ./deploy.sh --target staging   ✓ failed → ✓ fixed → ● owed → ○ recorded
      status entry: compound: lesson owed: ./deploy.sh --target staging
pane:
  ▲ 2 warnings  9 checks  mod, cli
  Compound interest  since 4 Oct
    ◆ 1 reuse offered  ■ 1 call stopped by a guard  ↺ 0 lessons recalled  ✔ 3 lessons recorded
  Open  nothing waits for anyone
  Levels
    project  3 lessons (1 guard)   0 skills
```

## Not verified, and what no longer matches

- The greeting at a short first prompt and the dim `nothing to reuse` close were seen only
  in `hooks/ui.test.ts` (the hooks mounted on the terminal and desktop surfaces), not in a
  recorded session: the tape's first prompt finds something.
- The desktop surface was exercised only through `claude plugin test`.
- `docs/media/demo-1-capture.png`, `demo-2-pane.png` and `demo.gif` in the README show the
  band and the pane as they were (no subject on `lesson owed`, the old Levels row, times
  of day in Recent, no totals). They were not re-recorded.
- `compound install` still ends without saying what a session will show (audit proposal
  3c): left to the install track.
- Existing assertions changed because the text they pinned changed on purpose:
  `tests/test_status.py` (section `Store` is `Levels`; the never-used row is one counted
  line), `tests/test_review.py` (Recent shows `removed`/`refused`, not `rm`/`refuse`),
  `hooks/view.test.ts`, `hooks/render.test.ts`, `hooks/ui.test.ts` (reuse names, owed
  subject, labels, toast order, Levels row, Recent words).
