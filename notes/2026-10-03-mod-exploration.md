# 2026-10-03: does it work, and would a mod do it better

Session e7609af7. Exploration only; no shipped code changed. Branch `resume/after-v0.3.1`.

## The requests this was checked against (surfer ids)

- f58c372b:3 (2026-09-03), scenario 1: "automatically remind claude (main thread AND/OR subagents) about the exact text of relevant user requests".
- f58c372b:3, scenario 2: "after a failed attempt at doing something (anything!), and then figuring it out, force claude to write it down ... before continuing".
- f58c372b:3, principles: "always maintain a single source of truth"; "never rely on remembering alone".
- f0feae4c:32 (2026-08-25): "make the default outcome not depend on you noticing".
- dae248bd:1 (2026-09-02): "skills can be relatively simple and narrowly scoped, as long as they are useful".

## Measured on the live state (~/.claude/skill-compounder), 2026-10-03

- `skillforge doctor`: 11 pass. Everything is wired and delivering.
- Repeat store, archive + live: 1222 fail rows, 1071 recover rows, 17 lesson notes on the ledger.
- Signatures recurring across >=2 sessions: 17 of 754 distinct (archive), 0 of 393 (live, 09-25..10-02).
  The lesson gate needs a recurring signature, so it is almost unreachable.
- 379 of 398 live fail rows carry an agent_id (subagents).
- Global CLAUDE.md holds the zsh `===` lesson three times (09-03, 09-04, 09-04).
- Mission: 1857 deliveries, all five moments. No outcome measure exists.
- Ledger: 12 forge starts, 6 done, 6 fail, 1 apply, 1 verdict; 2 `skill` rows (both bib skills,
  another project); 1 promote; 0 contrib.
- Size: 21,885 lines in hooks/ + bin/, 52,352 lines of tests, .claude/CLAUDE.md 92 KB.
- Three lesson statements fired in this session; one was a false binding (a for-loop whose
  last `[ -n ] &&` returned 1), one a real lesson, one a one-off typo.

## Mod spike (CLI 2.1.288; the spike itself was replaced by mod/compound-lessons the same day)

Run: `printf '%s' "<prompt>" | claude -p --model haiku --plugin-dir <mod dir> --allowedTools Bash`
(the prompt goes on stdin: `--allowedTools` is variadic and swallows a trailing prompt argument).

Observed:
- a mod loads under `claude -p --plugin-dir`; session.start, prompt.submit, tool.call, turn.complete fired;
- one `tool.call` hook saw the failure (`isError:true`) and the later success;
- `$.model.complete({model:"haiku"})` answered in-process;
- one hooks.json carrying both `modules` and a classic command hook validates, and both fired.

Not observed: the `context` return reaching the model (the judge answered NO on
`ls --nonexistent-flag .` -> `ls -la`, so that branch never ran); anything inside a subagent;
`session.compact`, `prompt.compose`, `$.ui.status`; an installed (non --plugin-dir) mod.

## Proposed test design

1. Labelled replay: label ~100 of the stored fail/recover pairs (real fix or not, lesson text);
   score any detector against them. Free, deterministic, no session needed.
2. Outcome journeys under `claude -p`, pass criterion on the outcome and never on delivery,
   N runs each, with and without the mod.
3. Live counter: failures of a lesson's kind in sessions after the lesson was written.

## Built the same day: mod/compound-lessons

User: "ok, continue: build it!". What exists (see its README for the commands):

- `hooks/register.ts`: one tool.call hook. Failure held per agent loop; recall question at
  the failure when lessons exist; fix question on the next two successes; a new lesson is
  written by the hook through `skillnote add --scope project`; a lesson from another
  project that matches here is moved with `skillnote promote`.
- `hooks/judge.ts`: both prompts and their parsers. A LESSON needs three true checks and a
  quote that is really in the error text (enforced in `parseFix`).
- `hooks/judge.test.ts`: 8 tests under `claude plugin test`, no model calls.
- `tools/journey.py`: control, A, B, C, S. 15 checks.
- `tools/sample_pairs.py`, `tools/score_replay.py`: the labelled replay.

Results:

- Replay, 40 tuned + 40 held-out pairs, labels mine and unreviewed
  (`~/.claude/skill-compounder/mod/pairs-labelled.jsonl`, `heldout-labelled.jsonl`):
  sonnet 4 of 5 real / 1 of 33 false (tuned), 4 of 5 / 0 of 32 (held out);
  haiku 3 of 5 / 2 of 33, 4 of 5 / 6 of 32. Default judge is sonnet for that reason.
- First judge prompt (no checks, 1200-char truncation): 3 of 5 real, 14 of 33 false. The
  false ones mostly read a truncated command as a broken one.
- Journey: 6 of 7 runs passed every check. One run failed 5 of 13 (sessions B and C logged
  no failure and no build result); streams were not kept then, cause unknown. Streams are
  kept now (`<root>/*.stream`).

Open:

- ENABLED 2026-10-03 on the user's say-so ("yes, switch on real sessions", "unwire old lesson
  hook"): `~/.claude/settings.json` now has `env.CLAUDE_CODE_PLUGIN_DIRS` naming
  `mod/compound-lessons`, and its three `repeat-gate.sh` entries (PreToolUse, PostToolUse,
  PostToolUseFailure) are removed. Backup beside it:
  `settings.json.bak-compound-lessons-20261003-123510`. Verified with a plain `claude -p`
  (no --plugin-dir) under a scratch state: the mod logged the failure and no repeat store
  was created.
- Repo matched to that the same day (user: "yes"): `hooks/hooks.json` and the installer no
  longer wire `repeat-gate.sh`; the installer constant is `REPEAT_GATE_RETIRED`, strip-only,
  and deliberately not named `*_MARKER` because `skillforge doctor` reads every such line
  as a script that must be wired. 17 entries over 9 scripts; doctor passes 17/17 live.
  `tests/e2e/journey.py` lost steps 15 and 16 (fifteen steps now; `--no-model` run passes,
  the model steps have not been run on this tree). The repeat store stops growing.
- Not done: the long descriptions of the repeat gate in `.claude/CLAUDE.md`, `docs/DESIGN.md`,
  `docs/architecture.md` and `docs/operations.md` are still there, each now under a line
  saying the script is not wired. `bin/skillrepeat`, the `REPEAT_*` knobs and
  `tests/test_repeat_gate.py` still exist for a script nothing wires; whether to retire
  them is undecided.
- Labels need the user's review.
- Mission (scenario 1) as a mod is not started. `session.compact` and `prompt.compose`
  are the hooks to try; only read in the types so far.
- `/tmp/compound-sub-Pdl1` is a leftover probe directory; the removal was blocked because
  it was the shell's working directory at the time.

## Later the same day: one mod, both halves, live

User: "all of those steps need to be complete", then `/goal complete the refactor; continue
working until it is 100% operational, tested (including quality checks, red-teaming), and
documented (including all animations updated), and live and running`.

What changed after the section above (commits eff14cf, 84b75cc, b781f1e, 03ec73f, 288457c,
c991230 and the ones after):

- `mod/compound-lessons` and `mod/compound-mission` became ONE plugin, `mod/compound`
  (`hooks/lessons.ts`, `mission.ts`, `judge.ts`, `safe.ts`, `render.ts`, `calls.ts`). A
  plugin may register only one unmatched `tool.call` hook, so `lessons.ts` owns it and
  `calls.ts` carries the two facts the mission needs from it.
- `hooks/mission.sh` is unwired like `repeat-gate.sh`. `hooks/hooks.json`: 12 entries over
  8 scripts on 6 events, plus `modules`. `install.sh` adds `<app>/mod/compound` to
  `env.CLAUDE_CODE_PLUGIN_DIRS` and strips an older install's entries. Installer constants:
  `MISSION_RETIRED`, `REPEAT_GATE_RETIRED`, `MOD_DIR`, `MOD_ENV_KEY`.
- LIVE: `python3 scripts/setup.py` was run against the real config on 2026-10-03. Settings
  backup `settings.json.bak-skill-compounder-20261003-184736` (and two earlier ones named
  `.bak-compound-lessons-...` and `.bak-compound-...`). `skillforge doctor`: 11 pass.
- Two cold red teams, one per half (19 and 15 real sessions). Findings and fixes are listed
  in `mod/compound/README.md` under "Measured". Neither half was re-reviewed after its fixes.
- Found while verifying the docs: with both install paths active the module loads twice
  and one fail-then-fix wrote two lessons. Fixed with an atomic `mkdir` claim under
  `<state>/mod/claims/<session>/`; journey step W.
- `bin/skillnote add` refuses `<!--` / `-->` in text or --why and flattens newlines.
- README animation re-recorded (`dev/forge_demo.sh` scene 1; `docs/media/forge.gif`).
- Docs rewritten by a subagent against the tree, then spot-checked: README, docs/*.md,
  `.claude/CLAUDE.md`. `docs/CLAUDE-CODE-BEHAVIOR.md` gained eleven 2.1.288 entries.

Test record on the final code (all 2026-10-03, CLI 2.1.288):

- `claude plugin test mod/compound`: 34 pass.
- `journey_lessons.py`: 26 of 26 twice in a row before step W was added. Earlier runs
  failed on the journey's own premises (a session reading the script first; a subagent
  told only to "execute and capture"; my check reading `ls ./check.sh` as the check), each
  fixed in the journey, and once on a real regression (a lesson worded "When X fails..."
  left a fresh session trying X first; the wording now leads with the right way).
- `journey_mission.py`: 15 of 15, three times since the red-team fixes.
- Legacy `tests/e2e/journey.py`: 12 of 12, six calls, 37.8 s.
- Replay, Sonnet judge after the red-team fixes: 4 of 5 real and 1 of 33 false (tuned set),
  4 of 5 and 0 of 32 (held out). Median judge call 2.4 s, slowest 7.5 s.

NOT DONE, and not doable in one day:

- Real-use evidence. The mod was enabled on 2026-10-03; `<state>/mod/events.jsonl` held no
  real-session rows when this was written. `python3 mod/compound/tools/report.py` reads it.
- The labels behind the replay are Claude's, unreviewed by Jeremy.
- No second red-team round after the fixes.
- `bin/skillrepeat`, the `REPEAT_*` and `MISSION_*` knobs and the two scripts' tests still
  exist for scripts nothing wires. Whether to retire them is Jeremy's call.
- history-surfer itself stores a subagent hand-back as a prompt, stores one prompt twice
  and flags a path-led prompt as a command. The mod filters all three; the store is not fixed.
- `/tmp/compound-sub-Pdl1` and the red team's memory files under
  `~/.claude/projects/...rt-mVfrPM-projF/memory/` are leftovers a person should delete.
