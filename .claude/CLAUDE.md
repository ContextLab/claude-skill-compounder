# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code *configuration* package. It installs seven skills, three hook wirings, four
CLIs, and a status-line wrapper into `~/.claude/`. There is no runtime service: the "program" is the
set of files the installer wires into someone else's Claude Code config.
`README.md` is the user-facing description. `docs/DESIGN.md` records the empirically
verified platform behavior every design decision rests on. Read `docs/DESIGN.md` before
changing anything in `bin/`, `statusline/`, or `hooks/`. Several of the constraints there
look arbitrary. They are not.

## Commands

```bash
./run_tests.sh                                  # full suite (stdlib unittest)
TEST_TIMEOUT=60 ./run_tests.sh                  # tighter per-file cap while iterating
PYTHONPATH=$PWD python3 tests/test_hook.py -v   # one file
PYTHONPATH=$PWD python3 tests/test_installer.py InstallerTest.test_install_is_idempotent
```

`run_tests.sh` loops over `tests/test_*.py` and runs each as a script, so a new test file
is picked up with no registration. `PYTHONPATH` matters only for `test_installer.py` and
`test_plugin.py` (the others shell out and need no import).

Each file runs in its own process group under a wall-clock cap (`TEST_TIMEOUT`, default
300s), enforced by an inline Python runner that kills the whole group on timeout. Killing
only the direct child is not enough: a surviving grandchild holds the inherited stdout
pipe, so `./run_tests.sh | tail` blocks for the full hang even after the runner exits. A hook script reads its payload with
`payload="$(cat)"`, so **every** `subprocess` call against a hook must pass `input=` or
`stdin=DEVNULL`, or it hangs forever.

Exercising the installer by hand (**never** against your own config):

```bash
python3 scripts/setup.py --claude-dir /tmp/fake-claude --bin-dir /tmp/fake-bin --state-dir /tmp/fake-state
python3 scripts/setup.py --uninstall --claude-dir /tmp/fake-claude --bin-dir /tmp/fake-bin --state-dir /tmp/fake-state
```

`install.sh` / `uninstall.sh` are thin shells that locate the app home and `exec` into
`scripts/setup.py`; the real logic is `skill_compounder/installer.py`.

Requires `jq` (hooks, CLIs, status line) and `python3` (installer only). The `gh` tests in
`test_contribute.py` skip cleanly without `gh` or without auth; nothing else skips.

Four CLIs ship in `bin/`, all shell + `jq`: `skillforge` (forge state and the ledger),
`skillreport` (ledger joined against transcript invocations), `skillinsight` (the candidate
queue), `skillcontrib` (read-only contribution reconnaissance).

## Architecture

**The animation is state-driven, not process-driven.** `bin/skillforge` writes a single
JSON file; `statusline/skillforge-status.sh` renders whatever it finds, once per second.
Nothing streams, which is what lets a forge animate across subagent dispatches.

**That file is deliberately not session-keyed**, and the two session ids are why. Do not
make it session-keyed without reading `docs/DESIGN.md` first. The reminder hook *does* key
per session, which is correct: it both reads and writes the payload's `.session_id`.

**Installation is marker-based and surgical.** `installer.py` identifies its own hook
entries by marker substring (`HOOK_MARKER`, `INSIGHT_MARKER`), and its status line by an
**exact** command match against `STATUSLINE_RECORD`, because a substring like
`statusline.sh` also matches a user's own `~/bin/git-statusline.sh`. Install is idempotent
and uninstall removes only our entries. Other tools' hooks and an unrelated status line are left
untouched. `settings.json` is backed up before every write and written atomically; a
malformed `settings.json` disables every setting in it. Malformed input raises rather than
being silently discarded.

**The status line wraps whatever is already there.** Any pre-existing `statusLine` command
is saved to `<state>/statusline-base.sh` (plus `original-statusline.json` for restoration)
and called first by `statusline/statusline.sh`. It lives in the state directory, so
`git pull` cannot clobber it. Base output is cached for `STATUSLINE_BASE_TTL` seconds
because a 1s refresh would otherwise re-run the user's `git` calls every second.

**Hooks must never break a turn.** `hooks/compound-improvement.sh` exits 0 on every failure
path, emits `{suppressOutput:true, hookSpecificOutput:{...additionalContext}}` when it
fires, and emits nothing at all when throttled. Tuning defaults (`CI_EDIT_EVERY=12`,
`CI_PROMPT_COOLDOWN=1200`, `CI_PROMPT_MIN_CHARS=60`) live in the script and are echoed in
the README tuning table. Change both.

**The repo is two install paths at once, and they must not drift.** `install.sh` writes
entries into the user's `settings.json`; `hooks/hooks.json` plus `.claude-plugin/plugin.json`
make the same repo loadable as a plugin. `tests/test_plugin.py` asserts the two wire the same
scripts to the same events with the same matchers, so adding a hook to one and forgetting the
other fails a test. A plugin cannot carry `statusLine`, which is why the installer stays
primary; see `docs/DESIGN.md`.

**The edit checkpoint counts `Bash`, not just `Write|Edit`.** `mutates_file()` in
`hooks/compound-improvement.sh` inspects `tool_input.command` and counts only commands
that write. Detection from a command string is a lower bound on purpose: a heredoc into
`python3 -` calling `write_text` is caught, a runtime-assembled path is not. Undercounting
delays a checkpoint; counting `ls` teaches the user to ignore it. A second branch fires
`ai-tell-audit` once per durable-prose file per session, because that skill's description
names a README but nothing otherwise connects editing one to invoking it.

**With both wirings active every hook fires twice**, so any new hook that counts or
throttles needs the `claim_once()` guard in `hooks/compound-improvement.sh`. Reasoning in
`docs/DESIGN.md`.

**`CLAUDE.md` lives at `.claude/CLAUDE.md`, not the repo root.** A root `CLAUDE.md` fails
`claude plugin validate --strict`, which is what marketplace review runs. The `.claude/`
path loads as project context the same way.

**The installer discovers what to link.** `_skill_dirs()` and `_cli_files()` walk `skills/`
and `bin/`, so adding a seed skill or a CLI needs no installer change, and
`test_installer.py` asserts every shipped one is actually linked.

**`skills/skill-compounder/SKILL.md` is prose, but it is the primary deliverable**: it
carries the builder/red-team forging protocol and the retirement protocol.
Its doctrine is mirrored in `README.md` and in the user's global `~/.claude/CLAUDE.md`
stanza. Changing the protocol means updating all three.

## Constraints specific to this repo

**No mocks, ever.** Every test writes real files, runs the real shell scripts through
`subprocess`, and reads results back off disk. Tests pin nondeterminism with environment
variables the scripts read for exactly that purpose (`SKILLFORGE_NOW`, `CI_NOW`,
`SKILL_COMPOUNDER_STATE`, `SKILLFORGE_DONE_TTL`). If new behavior is hard to test without a
mock, add a pin like those instead. Tests run with a minimal `PATH` and `HOME` pointed at a
temp dir, so scripts must not depend on the ambient environment.

**Shell portability traps that cause silent failures** (details and reasoning in
`docs/DESIGN.md`):

- Appending a multibyte glyph requires braces: `bar="${bar}▓"`, never `bar="$bar▓"`. Bash
  folds the UTF-8 bytes into the variable name.
- No portable way to index a string of multibyte glyphs (`cut -c` is locale-dependent, bash
  3.2 substring indexing is byte-based, zsh arrays are 1-indexed). The spinner uses a `case`
  statement for this reason; keep it.
- A literal `%` inside an *argument* to `printf '%s'` needs no escaping. Doubling it prints
  a visible `%%`.

**The red-teamer must never be a fork of the orchestrating session.** This applies to the
protocol in `SKILL.md` and to any work in this repo that follows it. A forked reviewer
inherits the author's blindness and reports that the skill looks fine. Each loop round
spawns a *new* cold agent, because after round one the previous one is no longer cold. The
retirement check has the same shape: ask the neutral *"keep, fix, or retire?"*, never
"confirm this deletion".

**Nothing is ever destructively removed.** Uninstall only unlinks symlinks it can prove it
created (`_unlink_if_ours` compares `realpath`), and it leaves runtime state intact.
Retiring a skill means `mv` to an archive with a `WHY-ARCHIVED.md`, never `rm -rf`.

## Notes and open threads

`notes/` is a dated log, not an index of current behaviour: `2026-08-24-origin.md` for
where the idea came from, `2026-08-25-roadmap-session.md` and
`2026-08-25-implementation-session.md` for how the seed pool and the plugin path were
built, and `notes/research/` for the evidence behind the seed-pool selection, the insight
queue, and the contribution mechanics. Read them for reasoning, not for the current state
of the code.

The two hook constants (12 edits, 20 minutes) are unvalidated. `bin/skillreport` is the
instrument that would settle them, and it needs real usage across several repositories
over real time. Do not tune them before that data exists. The skill's own threshold is
deliberately not a number — it asks for a nameable dead end and a second occurrence — so
there is nothing there to tune.
