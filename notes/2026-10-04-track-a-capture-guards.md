# 2026-10-04: Track A, trustworthy capture and guards

Work on the audit's bugs B1-B4 and proposals P1-P5 (`notes/2026-10-04-audit/audit-quality.md`),
on a worktree branch off `792bb47`. Not pushed, not merged.

## Done

1. Refusals are dropped before the judge. `refusal()` in `hooks/render.ts`; the tool.call hook
   returns before `onFailure` for a permission denial, a safety check, a harness refusal
   (`<tool_use_error>`, worktree isolation) and a hook refusal. `fixPrompt` rules them out too.
2. Guards are for Bash commands. A lesson's patterns are tested against Bash calls only, unless
   its frontmatter carries `match-tools` (`compound add --tool NAME`, repeatable). `check
   --guards` also prints `"tools"`, and the mod makes no `check` before a call of a tool no
   guard applies to.
3. `check` compiles patterns with `re.MULTILINE`. The taught anchor is
   `(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)` (learn skill, guide, design).
4. A Bash result that exited 0 with a shell-error line (`shellError()` in `hooks/render.ts`) is
   a failed call for recall and capture.
5. A recall after the lesson's guard refused in the same session is not counted: `tally` in
   `bin/compound` leaves it out, `show --json` says `guarded_in_session`, the mod writes
   `after_guard` and `ineffective: false`.
6. Every question to the model writes a `judge` event with `ms`; `recall` carries `ms` too.
   `status` Recent and the pane leave `judge` rows out.

## Assertions changed on purpose

- `tests/test_check_find.py`: `check --guards` replies now carry `"tools"`; the Edit guard test
  passes `--tool Edit`.
- `hooks/ui.test.ts`: the logged event types now include `judge` (three assertions).
- `hooks/render.test.ts`: the wording of what a match is tested against (two assertions).
- `hooks/store.test.ts`: `parseShow` answers carry `guarded`.

## Left open

- A Bash command that carries a mistake's text inside a quoted argument (`grep -n '; git commit'
  docs/guide.md`) still matches an unanchored pattern. Telling a quoted argument from a quoted
  command (`bash -c '...'`, `ssh host '...'`) needs a shell parser and a decision.
- The full wording of a user's rejection and of an approval prompt was not on record; the
  classifier matches the phrases the audit lists.
- `judge` events grow the log; `events --unsettled` still reads the whole log.
- The owner's three anchored user lessons keep the old anchor until they are updated:
  `macos-no-timeout`, `zsh-equals-word`, `zsh-function-name-is-alias`.

## Checks at the end

`./run_tests.sh` OK (12 files), `claude plugin validate --strict .` passed, `claude plugin test .`
161 pass. Journeys run once for real: capture 10 of 10, guard 22 of 22, recall 23 of 23.
