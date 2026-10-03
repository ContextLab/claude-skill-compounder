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
- Consequences not yet dealt with: `skillforge doctor` reports 17 of 20 entries and FAILs
  its settings row; `install.sh` or an update would wire `repeat-gate.sh` back, because the
  installer and `hooks/hooks.json` still carry it; and the repeat store stops growing, so
  new pairs for labelling come only from the mod's own `events.jsonl`.
- Labels need the user's review.
- Mission (scenario 1) as a mod is not started. `session.compact` and `prompt.compose`
  are the hooks to try; only read in the types so far.
- `/tmp/compound-sub-Pdl1` is a leftover probe directory; the removal was blocked because
  it was the shell's working directory at the time.
