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
