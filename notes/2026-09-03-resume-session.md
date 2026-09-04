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

## Resume command

```bash
cd "/Users/jmanning/claude-skill-compounder"
git checkout main && git pull --ff-only
```

`main` and `resume/after-v0.3.1` are the same commit; the practice is everything on main.
Open issues after this session: #19, #30, #31 (epic), #32, #34, #37, #42. #9 and #33 closed today.

## Still to do from the handoff

2. Measurement campaign (#30, #37): needs a week of ordinary use; not startable today.
6. #42 fresh-config journey: needs `CLAUDE_CODE_OAUTH_TOKEN` handed in.
7. #19: a two-level composition in the shipped pool (not manufactured; wait for a real one),
   and the "forged skill actually used" half (blocked on #34's second occurrence).

## Phase 2: the restated vision (#43)

The maintainer restated the vision (scenario 1: remind with the user's own words at five
moments, into subagents too; scenario 2: force the write-down after a fail-then-fix, with
code attached; levels A/B/C for both search and placement; single source of truth; never
rely on remembering). Research (five agents, all reports verified where a number was reused):
history-surfer stores prompts once per project and searches in 0.2 s; OMC blocks Stop with
`stop_hook_active` guard and re-injects the original prompt on SessionStart; measured on
2.1.259 that SessionStart `source=compact` reaches the model, SubagentStart context reaches
the subagent only, PreToolUse on Agent carries the subagent prompt and `updatedInput`
rewrites it, Stop blocks nine times without a CLI cap. Design:
`notes/2026-09-03-mission-and-lessons-design.md` = issue #43.

Wave 1 in flight, five builders on disjoint files: `hooks/mission.sh` + test;
`hooks/repeat-gate.sh` lesson arms + `bin/skillrepeat dismiss`; `bin/skillnote --lesson
--attach promote`; `bin/skillcontrib propose` + contribute-skill SKILL.md;
installer/hooks.json/doctor + history-surfer dependency. Orchestrator owns every doc.
Wave 2: docs (all), behavior entries for today's measurements (raw logs under the session
scratchpad `research/hookprobe/`), E2E steps, full suite, live verification.

## Wave 1 and wave 2 landed on disk (uncommitted at the time of writing)

Builders (all reports verified where a number was reused): `hooks/mission.sh` (71 tests);
repeat-gate lesson arms + `skillrepeat dismiss` (186 + 38 tests, `--norm-of` byte-identical
over the live store); `skillnote --lesson/--attach/promote` (127 tests); `skillcontrib
propose` + contribute-skill SKILL.md (91 tests); installer + hooks.json + doctor + history-
surfer dependency (installer 82, plugin 27, doctor 69). Matcher widened to
`Bash|Skill|mcp__.*` on the two learning events only (per-event pins). Docs: README,
architecture, measurement, operations (57 knob rows), DESIGN, CLAUDE-CODE-BEHAVIOR (four new
entries from the hook probe), `.claude/CLAUDE.md`, skill-compounder SKILL.md (499/500 lines,
pinned regions byte-identical), e2e docs. Journey: 17/17 PASS, 13 calls, 150.9 s.
Orchestrator fixes: derivation alternation + counts (153/155/22; operations 140), doctor's
mission row folds `dispatch`+`subagent` before counting, `test_install_sh.py` pins the surfer
step off, measurement.md corrected to match.

In flight: a fix agent for the journey's two findings — `install_surfer` must decide on the
TARGET settings.json rather than `which surfer`; `mission.sh` store root must follow
`CLAUDE_HISTORY_SURFER_DIR` then `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/history-surfer`.
Then: full suite on a quiet tree, commit, re-derive the claim-provenance sweep figure
(contribute-skill SKILL.md changed; expected 98, was 116), push, CI, `./install.sh` on this
machine (backs up settings.json), a live check that the five moments fire here, #43 comment.
