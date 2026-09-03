# 2026-09-03 resume session (after v0.3.1)

Resumed from `notes/2026-09-03-handoff-after-v0.3.1.md` on branch `resume/after-v0.3.1`
at `cec109c` (origin/main was already there; local `main` was 17 commits behind and was
fast-forwarded). `skillforge doctor`: 9 pass, 0 warn, 0 fail.

## Handoff item 1 (#34, a real forge under the diet): threshold applied, no candidate

Every store was checked: `skillinsight pending` empty; `skillrepeat list`'s 11 multi-session
signatures are all harness traffic; the 21 `note` rows show no text written twice against one
project. The strongest dead end (derivation grep narrower than its list, five occasions) fails
the tier gate's routing half, so it became reminder `n2288836221x440` keyed on `hooks/*.sh`,
`bin/*`, `statusline/*.sh`, `install.sh`. Recorded on #34 (comment 5525414232, corrected once:
21 rows not 18, and the six-fold memory row is the read-back measurement, not a retry).

## Landed in `c9150de` (main and resume/after-v0.3.1, both pushed)

- #33: `hooks/remind.sh` prunes other sessions' `remind/` directories on a sampled draw
  (`REMIND_PRUNE_EVERY`, `REMIND_PRUNE_TTL`, existing `REMIND_NOW` clock) and trims
  `hits.jsonl` on write; `PruneTest`, `HitsCapTest`. Close-out comment posted; close on
  green CI.
- repeat-gate E2BIG: mechanism re-measured (sed regex argv, not the command text); the
  hook closes stderr before its first exec (`REPEAT_GATE_STDERR`); `ExecNoiseTest`.
- ShellCheck: all 19 findings cleared, two of them live bugs (backtick executing `start`
  in a skillforge die message; skillnote's glob-in-variable case pattern inert under zsh).
  CI floor is `--severity=warning`; install.sh and uninstall.sh added to both shell steps.
- Docs: derivation counts re-run (126/128 CLAUDE.md, 116 operations.md); OPEN-THREADS
  records the prune policy, the E2BIG mechanism and the lint closure.
- #9 closed against #31 with a verified table. Reminder re-recorded count-free as
  `n195966769x406` (the first, `n2288836221x440`, embedded the stale 120 and is tombstoned).
- Full suite on the quiet tree: 50 files, ALL TESTS PASSED, 2 skips.

## Landed in `47801b6`

- #19 composition half: the three limits on the depth-4 entry were re-measured on 2.1.259
  with 18 sonnet runs (transformation 6/6, ordinary and passive wording 3/3 each, three-way
  discrimination 3/3 in both arms). New entry in `docs/CLAUDE-CODE-BEHAVIOR.md`; comment on
  #19. Raw transcripts were under the session scratchpad (`compose/<condition>/out/*.jsonl`)
  and are not kept; the entry carries the method to regenerate them.

## CI after the push

`c9150de` and `507a6ee` went red on one job, shellcheck (ubuntu-latest): apt's 0.9.0 reports
SC2120 on `bin/skillinsight`'s `record_nudge` (an optional argument no caller passed) where
brew's 0.11.0 is silent. Fixed in `ec6acc0` by dropping the dead parameter, checked locally
with the `shellcheck-py==0.9.0.6` wheel at the warning floor over every script (0 findings).
Recorded as a project note in `.claude/CLAUDE.md`. #33 closes once `ec6acc0` is green.

## Still to do from the handoff

2. Measurement campaign (#30, #37): needs a week of ordinary use; not startable today.
6. #42 fresh-config journey: needs `CLAUDE_CODE_OAUTH_TOKEN` handed in.
7. #19: a two-level composition in the shipped pool (not manufactured; wait for a real one),
   and the "forged skill actually used" half (blocked on #34's second occurrence).
