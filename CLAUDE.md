# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code *configuration* package, not an application: it installs a skill, two hooks,
a CLI, and a status-line wrapper into `~/.claude/`. There is no runtime service — the
"program" is the set of files the installer wires into someone else's Claude Code config.
`README.md` is the user-facing description; `docs/DESIGN.md` records the empirically
verified platform behavior every design decision rests on. Read `docs/DESIGN.md` before
changing anything in `bin/`, `statusline/`, or `hooks/` — several constraints there look
arbitrary and are not.

## Commands

```bash
./run_tests.sh                                  # full suite (45 tests, stdlib unittest)
PYTHONPATH=$PWD python3 tests/test_hook.py -v   # one file
PYTHONPATH=$PWD python3 tests/test_installer.py InstallerTest.test_install_is_idempotent
```

`run_tests.sh` loops over `tests/test_*.py` and runs each as a script, so a new test file
is picked up with no registration. `PYTHONPATH` matters only for `test_installer.py`
(the others shell out and need no import).

Exercising the installer by hand — **never** against your own config:

```bash
python3 scripts/setup.py --claude-dir /tmp/fake-claude --bin-dir /tmp/fake-bin --state-dir /tmp/fake-state
python3 scripts/setup.py --uninstall --claude-dir /tmp/fake-claude --bin-dir /tmp/fake-bin --state-dir /tmp/fake-state
```

`install.sh` / `uninstall.sh` are thin shells that locate the app home and `exec` into
`scripts/setup.py`; the real logic is `skill_compounder/installer.py`.

Requires `jq` (hooks, CLI, status line) and `python3` (installer only).

## Architecture

**The animation is state-driven, not process-driven.** `bin/skillforge` writes a single
JSON file; `statusline/skillforge-status.sh` renders whatever it finds, once per second.
Nothing streams. This decoupling is what lets a forge animate across subagent dispatches —
builder and red-teamer are separate processes writing one file.

**That file is deliberately not session-keyed.** `$CLAUDE_CODE_SESSION_ID` (what `Bash`
sees) and `.session_id` (what hooks and the status line receive on stdin) are *different
values for the same session*. State written under one is invisible to the other, silently.
Hence `forge/current.json`, one forge at a time per machine. The reminder hook *does* key
per session — correctly, because it both reads and writes the payload's `.session_id`.

**Installation is marker-based and surgical.** `installer.py` identifies its own entries by
substring (`HOOK_MARKER`, `STATUSLINE_MARKER`), so install is idempotent and uninstall
removes only our entries while leaving other tools' hooks and an unrelated status line
untouched. `settings.json` is backed up before every write and written atomically; a
malformed `settings.json` disables every setting in it. Malformed input raises rather than
being silently discarded.

**The status line wraps rather than replaces.** Any pre-existing `statusLine` command is
saved to `<state>/statusline-base.sh` (plus `original-statusline.json` for restoration) and
called first by `statusline/statusline.sh`. It is saved into the state directory, not the
clone, so `git pull` cannot clobber it. Base output is cached for `STATUSLINE_BASE_TTL`
seconds because a 1s refresh would otherwise re-run the user's `git` calls every second.

**Hooks must never break a turn.** `hooks/compound-improvement.sh` exits 0 on every failure
path, emits `{suppressOutput:true, hookSpecificOutput:{...additionalContext}}` when it
fires, and emits nothing at all when throttled. Tuning defaults (`CI_EDIT_EVERY=12`,
`CI_PROMPT_COOLDOWN=1200`, `CI_PROMPT_MIN_CHARS=60`) live in the script and are echoed in
the README tuning table — change both.

**`skills/skill-compounder/SKILL.md` is content, not code**, but it is the primary
deliverable: it carries the builder/red-team forging protocol and the retirement protocol.
Its doctrine is mirrored in `README.md` and in the user's global `~/.claude/CLAUDE.md`
stanza. Changing the protocol means updating all three.

## Constraints specific to this repo

**No mocks, ever.** Every test writes real files, runs the real shell scripts through
`subprocess`, and reads results back off disk. Tests pin nondeterminism with environment
variables the scripts read for exactly that purpose (`SKILLFORGE_NOW`, `CI_NOW`,
`SKILL_COMPOUNDER_STATE`, `SKILLFORGE_DONE_TTL`). If new behavior is hard to test without a
mock, add a pin like those instead. Tests run with a minimal `PATH` and `HOME` pointed at a
temp dir, so scripts must not depend on the ambient environment.

**Shell portability traps that have already caused silent failures here** (details and
reasoning in `docs/DESIGN.md`):

- Appending a multibyte glyph requires braces: `bar="${bar}▓"`, never `bar="$bar▓"` — bash
  folds the UTF-8 bytes into the variable name.
- No portable way to index a string of multibyte glyphs (`cut -c` is locale-dependent, bash
  3.2 substring indexing is byte-based, zsh arrays are 1-indexed). The spinner uses a `case`
  statement for this reason; keep it.
- A literal `%` inside an *argument* to `printf '%s'` needs no escaping. Doubling it prints
  a visible `%%`.

**The red-teamer must never be a fork of the orchestrating session.** This applies to the
protocol in `SKILL.md` and to any work in this repo that follows it. A forked reviewer
inherits the author's blindness and reports that the skill looks fine. Each loop round
spawns a *new* cold agent — after round one the previous one is no longer cold. The
retirement check has the same shape: ask the neutral *"keep, fix, or retire?"*, never
"confirm this deletion".

**Nothing is ever destructively removed.** Uninstall only unlinks symlinks it can prove it
created (`_unlink_if_ours` compares `realpath`), leaves runtime state intact, and retiring a
skill means `mv` to an archive with a `WHY-ARCHIVED.md` — never `rm -rf`.

## Notes and open threads

`notes/2026-08-24-origin.md` tracks status and open questions. The largest one: the forging
protocol has been written but never run end to end on a real candidate skill, and the
threshold constants (>15 min, ≥2 occurrences, 12 edits, 20 min) are first guesses awaiting
real usage.
