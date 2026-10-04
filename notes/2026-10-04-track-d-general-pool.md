# 2026-10-04: Track D, the general pool

Worktree branch off `190b900`. Not pushed, not merged.

## Decisions

1. **Condition.** Frontmatter `platform:` and `shell:` (one name, or names separated by
   commas), written by `compound add --platform NAME --shell NAME` (repeatable), replaced
   by `--update`, dropped by `--update --no-condition`. Both must hold. A lesson whose
   condition does not hold is "not in force": not a guard (`check` neither tests nor counts
   it), not returned by `find`, dropped from the mod's inventory (`parseInventory`), so not
   recalled or offered. `list`/`status` flag it `not here`, `show` says which condition
   failed and what this machine is. A condition that does not read fails `lessons parse`
   and applies nowhere.
   - Platform: `COMPOUND_PLATFORM`, else `sys.platform` as `darwin`/`linux`/`windows`.
   - Shell: file name of `COMPOUND_SHELL`, else `CLAUDE_CODE_SHELL` (the name is in the
     Claude Code 2.1.289 binary), else `SHELL`. Unknown when none is set, and then a lesson
     with a shell does not apply. Limits are written in `docs/design.md`: a login shell
     Claude Code does not run commands in, and commands run through another shell
     (`bash -c`, a `#!/bin/bash` script).
   - Both `COMPOUND_*` names are CLI-only and resolved like `COMPOUND_RECUR_LIMIT`
     (environment, then `env` in settings.json). The real session in the journey showed
     the CLI the mod spawns inherits `SHELL`.
   - Still one CLI call before a tool call. Measured `guard` events: 57-63 ms.
2. **A general lesson is never a debt.** Its recalls are counted; none is marked
   ineffective (mod: `recurred`), `unsettled` leaves out a recall of a shipped lesson
   whatever the event says (CLI), no stop is refused. At `COMPOUND_RECUR_LIMIT` recalls it
   is `recurring`: flagged in `list`/`status`, `recurring: true` in JSON, and listed under
   Open with `compound disable <name>` and `https://github.com/<COMPOUND_UPSTREAM>/issues`.
   `add --update` still refuses a general lesson; its message now names both.
3. **Switch.** `compound disable NAME` / `compound enable NAME`, names kept in
   `<COMPOUND_HOME>/disabled.json` (a JSON array; in `HOME_NAMES`, so `--purge` takes it).
   General lessons only (exit 2 otherwise, naming `compound rm`). No event is logged. `rm`
   of a general lesson names `compound disable`. The mod forgets its guard and inventory
   caches after a `disable`/`enable` the session ran (`changesStore`).
4. **Shipped pool.** Built by `notes/2026-10-04-audit/general-pool/build_shipped.py`: each
   lesson is added at the user level of a throwaway store with the real CLI, and the file
   in `lessons/` is the `skill_md` of `compound promote --to general --json` (no `origin`).

   | Lesson | Form | Condition |
   |-|-|-|
   | `zsh-equals-not-found` | guard | shell zsh |
   | `zsh-status-path-variables` | guard (3 patterns) | shell zsh |
   | `zsh-no-matches-found` | recall | shell zsh |
   | `sed-in-place-bsd` | guard | platform darwin |
   | `macos-gnu-only-commands` | guard on `timeout N`, recall for the rest | platform darwin |
   | `pip-externally-managed` | recall | none |

   Changes to the drafted patterns, beyond the anchor:
   - equals: `={2,}` not `=+` (`echo =` prints `=` in zsh, checked), and `)`/`|` end it.
   - status/path assignment: its own anchor, without a single `&` and without `(`, so
     `curl '...?path=1&status=2'` and `python3 -c "open(path='x')"` are not hits; `{ ` added.
   - `read`: anchored, also after `while`/`until` and `IFS= `.
   - sed: anchored, plus after `xargs`, `-exec`, `sudo`; `-Ei` joined flags (fails on BSD
     sed, checked).
   - **timeout and Homebrew coreutils**: a pattern cannot look at PATH. The guard applies
     on darwin whether or not a `timeout` is installed; its text says to send the call
     again when `command -v timeout` prints a path, the guard refuses once per session, and
     the lesson can be disabled. Same for GNU sed first on PATH. Not made a condition
     because the lesson's other half (`date -d`, `grep -P`, `stat -c`) would go with it.
5. **Same subject, two names.** In `check`, a general guard that hits beside a project or
   user guard yields: it is named under `"yielded"` and is not a hit. So the user's own
   lesson refuses, once. A call only the general guard matches is refused by it. Recall
   names one lesson by construction (`parseRecall`), so there is never a double recall;
   which of two the judge names is the model's choice and was not changed.

## Tests

- `tests/test_general_pool.py`, 38 tests. Shipped guards through the real
  `bin/compound check --guards` of the checkout, on zsh + darwin: 43 calls that must be
  stopped by exactly their lesson, 57 that must not be, 47 ordinary commands that no
  pattern may hit; on bash + linux no guard is counted or hits.
- `hooks/`: 3 new tests (inventory drops lessons not in force; a general lesson past the
  limit owes nothing and refuses no stop; `disable`/`enable` change the store).
- Assertions changed on purpose:
  - `tests/test_check_find.py` `test_guards_at_all_three_levels_are_tested`: the general
    guard yields beside nearer ones, and is the hit once they are removed.
  - `tests/test_status.py`: `open` has a `recurring` key.
  - `tests/test_store.py`: `list --json` rows carry `platform`, `shell`, `applies`,
    `disabled`, `recurring`.
  - `hooks/render.test.ts`: `changesStore` is true for `disable` and `enable`.
- End state: `./run_tests.sh` OK (13 files), `claude plugin validate --strict .` passed,
  `claude plugin test .` 163 pass.

## Journey (`tests/journeys/journey_general.py`, haiku, macOS 25.6 + zsh, run twice)

Second run 33 of 33. First run 32 of 33; the one failure was a check of mine that looked
for the recalled text in the stream, where the mod's added context never appears.

- guards: all four wrong forms refused once, quoting `level=general` and the package path;
  the session then ran `echo '====='`, `st=$(echo 7)`, `sed -i.bak ... && rm`, and dropped
  `timeout`.
- glob: `rm -f build/*.journeyobj` recalled `zsh-no-matches-found`. In run 2 the session
  tried two quoting variants that still failed (three recalls) before using `find`.
- pip: recalled `pip-externally-managed` in both runs. Run 1 (free to act): the next call
  was `python3 -m venv .venv && .venv/bin/python -m pip install cowsay`, no
  `--break-system-packages`. `PIP_DRY_RUN=1`, set to keep the machine clean, then sent that
  session through 15 more calls, so the step was changed: run 2 asks what it would run next
  and it answered with the venv pair. Two sessions, one model: not evidence that the
  earlier weakness is gone.
- twice: recalled in three sessions with `COMPOUND_RECUR_LIMIT=2`, no recall ineffective,
  no `strengthen` refusal, nothing owed, `status` shows the `recurring` row.
- off: with `zsh-equals-not-found` disabled and `COMPOUND_PLATFORM=linux`, no guard event
  and neither lesson recalled. **In both runs the judge then gave the `==== not found`
  failure the lesson `zsh-no-matches-found`**, which is the wrong lesson.

## Not verified, not done

- Linux, bash-as-login-shell, Windows: only simulated through `SHELL` and
  `COMPOUND_PLATFORM` in the CLI tests. No session was run on another platform.
- `CLAUDE_CODE_SHELL`: its meaning is taken from its name in the binary; no session was
  run with it set.
- Known false hits, each one refusal per session: a heredoc or inline script whose line
  starts with the wrong form (`timeout 30 ./run` written into a script for Linux;
  `python3 -c "x=1; path='a'"`), and prose after `sudo`/`xargs`/`exec` that quotes `sed -i`.
- The `/compound` pane does not list `recurring` lessons under Open (the text report and
  `status --json` do).
- A stale `ineffective: true` recall of a name that later becomes a general lesson is
  dropped from what is owed, by name.
- While this was written, the live mod in the parent session raised a strengthening for
  the owner's real `zsh-nomatch-glob` after two of this agent's own Bash calls (one a real
  unmatched glob, one a `cat` of journey output that held a `(eval):1: no matches found`
  line). Nothing was run against the real store; that debt is the parent session's.
