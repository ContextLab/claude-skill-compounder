# Rewrite session, 2026-10-03

Resume point for the ground-up rewrite. The contract is `docs/design.md`.

## Request (verbatim source)

Prompt `fee13f20-8842-494d-9ab6-546e5889cecc:1` in the prompt log (`surfer show` it).
The three levels are defined in prompt `f58c372b-1ab6-4d3d-b72c-5311471c9690:3`:
A project (`.claude` in the repo), B user (`~/.claude`), C general (this package's
repository, reached by an automated fork and pull request).

## Done

- Old install removed from this machine: `./uninstall.sh`, then by hand the state
  directory `~/.claude/skill-compounder`, 61 `*.bak-skill-compounder-*` /
  `*.bak-compound-*` files across `~/.claude` and nine project `.claude` directories, and
  `~/.claude/skills-archive`. `~/.claude/settings.json` now names only history-surfer and
  the iTerm status hook.
- Old tree removed in commit `88a6c3e`. Last commit of the old implementation: `ee0d596`.
- `docs/design.md` written.

## Kept on purpose, to migrate

- The `<!-- skillnote:begin -->` note blocks in `~/.claude/CLAUDE.md` and in twelve
  project `.claude/CLAUDE.md` files (list: `grep -l 'skillnote:begin' ~/*/.claude/CLAUDE.md`).
- `~/.claude/lessons/n3725829701x412/ci-checks.sh` and
  `~/.claude/lessons/n3821833834x409/bibdupcheck.py`, which two of those notes name.
- User skills `bib-duplicate-check` and `cdl-bib-cite` in `~/.claude/skills`.

Migration plan: once `bin/compound` exists, convert each note to a lesson at the level
its block sits at (`compound add`), move the two scripts in as attachments, then delete
the blocks and `~/.claude/lessons`.

## Task list

1. [done] CLI: `bin/compound`, `tests/test_*.py`, `install.sh`, `run_tests.sh`, CI.
2. [done] Mod: `.claude-plugin/`, `hooks/`, `skills/learn`, `skills/reuse`, `tests/journeys/`.
3. [done] Two cold red-team rounds (CLI, mod, then a new-user pass) and their fixes.
4. [done] Installed on this machine with `./install.sh`; a live `claude -p` session wrote a
   `guard` event for `zsh-equals-word` through the installed path.
5. [done] 99 old notes converted to 77 lessons (32 user, 45 project) with
   `compound add`; plan and scripts were in the session scratchpad.
6. [blocked, needs Jeremy] Deleting the old `<!-- skillnote:begin -->` blocks from
   `~/.claude/CLAUDE.md` and eleven project `.claude/CLAUDE.md` files, and
   `~/.claude/lessons/`. The permission classifier refused it. Until it is done each
   lesson exists twice (the old note and the new lesson).
7. [open] The status entry and toasts have been seen by no one: `claude -p` cannot show
   them. Check in an interactive session.
8. [open] The 45 project lessons are untracked files in eleven other repositories;
   nothing there is committed.
9. [open] Ubuntu: the suite has only run on macOS; CI runs on the first push.

## Open question for Jeremy

The twelve seed skills the old package shipped (`ai-tell-audit`, `session-handoff`, ...)
are not in the new general pool. They are in git at `ee0d596:skills/`. Which, if any,
should come back?

## Second review: fixes A to H (2026-10-03, late; uncommitted when written)

Eight reviewed defects fixed, test or journey first. Not committed: the working tree
holds them (`git status`). `README.md` was left alone on purpose.

- A: `promote --to user --auto [--seen-in P]` moves only a lesson git does not track;
  tracked is exit 3 plus a `candidate` event; status Open lists the command.
- B: a name is unique among what a session sees; a move or add at the user level is
  refused while another project known to the log holds the name; `--as NEWNAME`.
- C: status `mod` row checks the plugin files and `COMPOUND_OFF`; new `mod last fired` row.
- D: `capture.id`, `--settles ID` on add and skip, `events --unsettled [--project P]`,
  status Open lists unsettled captures, and a once-per-session `remind` at the first prompt.
- E: an ineffective recall (`recall.ineffective`) owes a strengthening; the stop is refused
  once (`refuse` why `strengthen`). `show --json` gained `recalls_since`, `recur_limit`.
- F: install always links (creates `~/.local/bin`) and prints the PATH line.
- G: `log` refuses unknown types; prompt-log row is a count; `lessons/.gitkeep`; design.
- H: the reuse judge is told that running a named command is not a build task.

New: `tests/test_reach.py`, `tests/journeys/journey_strengthen.py`,
`tests/journeys/journey_unsettled.py`. Event types added: `remind`, `candidate`.

Observed in the journeys: with the stronger wording a session usually strengthens the
lesson at once, so the stop refusal is reached only when it tries to finish first. One
session wrote a `--match` from the ERROR text, which never matches a call; the messages
now say what a match is tested against.

## 2026-10-04: third review, band and pane, screencast, docs

- Third cold review: nothing blocking; its findings fixed in `af53c7d`.
- Band above the prompt and `/compound` pane: `76f556b` (`hooks/view.ts`, `notes/2026-10-04-band-and-pane.md`).
- Screencast: `docs/media/demo.gif` and three stills, recorded from real sonnet sessions by
  `dev/demo.sh`. Scene 1-2 produced a recorded lesson in 8 of 40 takes, so re-recording is slow.
- The recording exposed a bug: Claude ran the CLI through a variable (`C=...; $C add`), the mod
  did not see it, and the band and status entry stayed on "lesson owed" after the lesson was
  recorded. Fixed with `mentionsCli` in `hooks/render.ts`. The GIF predates the fix, so its
  scene 2 does not show the "recorded" flash; `demo-2-pane.png` is cropped above the stale entry.
- README rewritten, `docs/guide.md` added, Mermaid flowchart and levels diagram, logo.
- Old note blocks removed from twelve CLAUDE.md files; backups in the local `~/.claude`
  repository at `c704723`. Eleven zero-byte project `.claude/CLAUDE.md` files remain (their
  deletion was refused by the permission classifier).

Open: re-record scenes 1-2 to show the recorded flash; look at the band and pane on the
desktop surface; eight project repositories each hold one unpushed local commit.

## 2026-10-04, later: fourth review and the re-recorded screencast

- Fourth cold review: nothing blocking; fixes in `3b4ea05` (one definition of "settled" in
  the CLI, the display follows the event log, `add` never hangs on stdin).
- Screencast re-recorded on the fixed code: scene 2 shows the recorded flash and the status
  entry clearing. The lesson in it is `python3-no-tomllib-use-tomli`. Prompt wording
  "Use Python to ..." fails reliably (11 of 15 headless); scenes hit 2 of 2.
- Toast texts no longer start with `compound: ` (the engine adds the plugin name). The GIF
  predates that one change, so its toast reads `compound: compound: lesson recorded`.
- A demo session pip-installed `tomli` into `~/Library/Python/3.9`
  (`/usr/bin/python3 -m pip uninstall tomli` removes it).
- `journey_strengthen.py` accepts either outcome (strengthened before the stop, or refused
  once then strengthened).

Open: the band and pane on the desktop surface are unseen; eleven zero-byte project
`.claude/CLAUDE.md` files; eight project repositories each hold one unpushed commit.
