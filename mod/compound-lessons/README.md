# compound-lessons

A Claude Code mod (a plugin of function hooks) that writes a lesson down after a failed
tool call is fixed, and states it back when the same mistake happens again.

## What it does

One `tool.call` hook sees every tool call and its result, in the main session and in
subagents.

1. A failed call is held, per agent loop. `Read`, `Edit`, `Write` and `NotebookEdit`
   failures are skipped.
2. If recorded lessons exist, a model is asked whether one of them describes the failure.
   A match is returned to the agent beside the error.
3. The next two successful calls in that loop are put to a model together with the
   failure. It answers whether the success is a corrected attempt at the same thing, and
   whether an existing lesson already covers it.
4. A new lesson is written by the hook itself, with `skillnote add --scope project`. The
   agent runs no command.
5. A lesson that was written in one project and matches a failure in a second project is
   moved to the global notes with `skillnote promote`.

The judge must quote the part of the error text that names the mistake. `parseFix` in
`hooks/judge.ts` rejects a lesson whose quote is not in the error.

Notes stay where `bin/skillnote` puts them. The mod's own log is
`<state>/mod/events.jsonl`, with one row per `fail`, `judged`, `lesson`, `recur` and
`promote`.

## Requirements

Claude Code 2.1.288 was the version this was built and run on. The mod API is marked
early access in its own type declarations. `skillnote` must be on `PATH`, or
`COMPOUND_SKILLNOTE` must name it.

## Environment

|Name|Effect|
|-|-|
|`COMPOUND_LESSONS=0`|The hook passes every call through untouched|
|`COMPOUND_JUDGE_MODEL`|Model for both questions; the default is `sonnet`|
|`COMPOUND_SKILLNOTE`|Path to `skillnote`|
|`COMPOUND_REPLAY`|A labelled pairs file; the session scores the judge on it and does nothing else|
|`SKILL_COMPOUNDER_STATE`|State directory, as for the rest of this repository|

## Running it

```bash
claude --plugin-dir /path/to/claude-skill-compounder/mod/compound-lessons
```

For every session, name the folder in `CLAUDE_CODE_PLUGIN_DIRS` in the `env` block of
`~/.claude/settings.json`.

## Tests

```bash
claude plugin validate mod/compound-lessons
claude plugin test mod/compound-lessons        # hooks/judge.test.ts, no model calls
python3 mod/compound-lessons/tools/journey.py  # real sessions; run by hand
```

`tools/journey.py` runs five headless sessions against throwaway projects and passes
on outcomes: an uninformed session fails first; a session with the mod fails, fixes, and
a note exists that the agent did not write; a fresh session does not repeat the failure;
a second project gets the lesson back and it moves to the global notes; and the same
happens when the failure is inside a subagent.

The judge is scored against labelled pairs from the repeat store:

```bash
python3 mod/compound-lessons/tools/sample_pairs.py <state>/mod/pairs.jsonl 40
# add "label": "yes" | "no" | "unsure" to each row, then:
COMPOUND_REPLAY=<state>/mod/pairs.jsonl claude -p --plugin-dir mod/compound-lessons <<< hi
python3 mod/compound-lessons/tools/score_replay.py <state>/mod/pairs.jsonl.results.jsonl
```

The pairs carry commands from every project on the machine, so they are kept in the state
directory and not in this repository.

## Measured, 2026-10-03

Two sets of 40 stored pairs, labelled by Claude and not yet reviewed by a person. The
prompt was tuned on the first set; the second was labelled before the judge saw it.

|Set|Judge|Real lessons found|False lessons|
|-|-|-|-|
|tuned|sonnet|4 of 5|1 of 33|
|tuned|haiku|3 of 5|2 of 33|
|held out|sonnet|4 of 5|0 of 32|
|held out|haiku|4 of 5|6 of 32|

The journey passed every check in 6 of 7 runs. One run failed 5 of 13 checks; its
session output was not kept, so the cause is unknown.

## Not covered

- The mission reminders and the status line are still the shell hooks.
- `hooks/repeat-gate.sh`, which did this job before, is no longer wired by `install.sh`
  or the plugin. Its store stops growing, so new pairs for the replay come from
  `events.jsonl`, which holds failures and lessons but not every fail/fix pair.
- Lessons are matched by a model call on each failure, so a failed call waits for that
  call when lessons exist. The wait has not been measured.
