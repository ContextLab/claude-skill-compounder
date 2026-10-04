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

1. [running] CLI agent: `bin/compound`, `tests/test_*.py`, `install.sh`, `run_tests.sh`, CI.
2. [running] Mod agent: `.claude-plugin/`, `hooks/`, `skills/learn`, `skills/reuse`, `tests/journeys/`.
3. Integrate: full suite, `claude plugin validate/test`, journeys.
4. Red team with cold agents (not forks): CLI, mod, docs-as-a-new-user.
5. Docs: `README.md`, `docs/`, `.claude/CLAUDE.md`, `CONTRIBUTING.md`, all present tense.
6. Install on this machine, migrate the notes, verify live in a real session.
7. Push; update project memory.

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
