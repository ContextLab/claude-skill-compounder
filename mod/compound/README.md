# compound

A Claude Code mod (a plugin of function hooks) with two halves. The lessons half writes a
lesson down after a failed tool call is fixed, and states it back when the same mistake
happens again. The mission half states the user's own requests back, word for word, at the
moments a session tends to lose them.

Built and run on Claude Code 2.1.288. The function-hook API is marked early access in its
own type declarations and may change between releases.

## Enabling it

`install.sh` enables it. By hand, for one session:

```bash
claude --plugin-dir /path/to/claude-skill-compounder/mod/compound
```

and for every session, name the folder in `CLAUDE_CODE_PLUGIN_DIRS` in the `env` block of
`~/.claude/settings.json`. That variable is read whatever `--setting-sources` says.

`skillnote` must be on `PATH`, or `COMPOUND_SKILLNOTE` must name it. The mission reads
history-surfer's prompt store when it holds the session.

## The lessons half (`hooks/lessons.ts`)

One `tool.call` hook sees every tool call and its result, in the main session and in
subagents.

1. A failed call is held, per agent loop. `Read`, `Edit`, `Write` and `NotebookEdit`
   failures are skipped.
2. If recorded lessons exist, a model is asked whether one of them describes the failure.
   A match is returned to the agent beside the error, and that failure is not held.
3. The next two successful calls in that loop are each put to a model together with the
   failure. It answers whether the success is a corrected attempt at the same thing, and
   whether an existing lesson already covers it.
4. A new lesson is written by the hook itself, with `skillnote add --scope project`, at the
   repository root (or where the session started, outside a repository). The agent runs no
   command.
5. A lesson that was written in one project and matches a failure in a second project is
   moved to the global notes with `skillnote promote`. If the note has been removed since,
   it is withdrawn and not stated back.

What keeps a wrong or harmful line out of a file every later session loads:

- **Masking.** `hooks/safe.ts` masks command and error text before it is held, judged or
  logged: assignments and flags whose name says secret, authorization headers, credentials
  in a URL, and several well-known token shapes. This is a lower bound; a secret passed as
  a bare positional argument is not recognised.
- **No command text in the note.** The note line carries the lesson and a fixed `why`. The
  failed and working calls are in the mod's log only, masked.
- **Quoted evidence.** The judge must quote the part of the error that names the mistake.
  `parseFix` in `hooks/judge.ts` rejects a lesson whose quote is not in the error, or is
  only the exit status.
- **One plain line.** A lesson longer than 400 characters is refused. Comment markers and
  newlines are removed, and `skillnote` itself refuses `<!--` and `-->` in note text.

A lesson is worded with the right way first ("Run X instead of Y, which fails with Z"). An
earlier wording that began "When Y fails" was measured in the journey to leave a fresh
session trying Y first.

## The mission half (`hooks/mission.ts`)

|Moment|Event|What is delivered|
|-|-|-|
|ambiguity|`prompt.submit`, a prompt under six words|the last substantive request|
|compact|`session.compact`|the summarizer is told to keep the requests word for word|
|resume|`classic.SessionStart`, source `compact` or `resume`|the mission|
|dispatch|`classic.PreToolUse` on `Agent`, `Task`, `Workflow`|the mission, to the parent|
|subagent|`classic.SubagentStart`|the mission, to the subagent|
|periodic|`classic.PreToolUse`, 1200 s after the last delivery|the mission|
|completion|`classic.Stop`, after 8 tool calls since the user last typed and a completion claim|the mission, once per typed request, as the reason the stop is declined|

The mission is the first substantive request and the three most recent substantive ones,
each as a block of `> `-prefixed lines (`hooks/render.ts`). Prompts come from
history-surfer's store when it has this session, and otherwise from the prompts the running
process saw submitted in that session, which do not survive a new process. Slash commands,
harness frames that arrive on the prompt channel (a subagent's hand-back, a task notice),
and a prompt the store recorded twice are not counted as requests.

A completion claim is read from the last sentence of the closing message: one that
negates, waits or asks is not a claim. A short prompt that arrives within ten seconds of
another statement is not answered a second time. The block a subagent receives opens by
saying it is context and not a task for that agent.

## Environment

|Name|Effect|
|-|-|
|`COMPOUND_LESSONS=0`|The lessons half passes every call through untouched|
|`COMPOUND_MISSION=0`|The mission half delivers nothing|
|`COMPOUND_JUDGE_MODEL`|Model for both lesson questions; the default is `sonnet`|
|`COMPOUND_SKILLNOTE`|Path to `skillnote`|
|`COMPOUND_MISSION_INTERVAL`|Seconds between periodic deliveries; the default is 1200|
|`COMPOUND_MISSION_STOP_MIN_TOOLS`|Tool calls a turn needs before a completion claim is answered; the default is 8|
|`COMPOUND_REPLAY`|A labelled pairs file; the session scores the judge on it and the lessons half does nothing else. A path that does not exist is logged and ignored|
|`MISSION_SURFER_ROOT`, `CLAUDE_HISTORY_SURFER_DIR`|Where history-surfer's store is, in that order|
|`SKILL_COMPOUNDER_STATE`|State directory, as for the rest of this repository|

## Logs

`<state>/mod/events.jsonl`, the lessons half, one row per event:

|`ev`|Written when|
|-|-|
|`fail`|a call failed; `recalled` is the lesson matched to it, if any, and `ms` the recall question's time|
|`judged`|a later success was judged and held no lesson; carries the reason, the quoted evidence and `ms`|
|`lesson`|a lesson was written; carries its id, project, text, the masked calls, the evidence and `ms`|
|`recur`|a failure or a fix matched a recorded lesson|
|`promote`, `promote-failed`|a lesson from another project was moved to the global notes, or could not be|
|`gone`|a lesson from another project had been removed, and was withdrawn|
|`write-failed`|`skillnote add` refused or failed|
|`replay-failed`|`COMPOUND_REPLAY` named a file that does not exist|

`<state>/mod/mission.jsonl`, the mission half: `ts`, `session`, `moment`, `agent`, `chars`.

`<state>/mod/claims/<session>/` holds one empty directory per event an instance acted on.
The repository can be loaded twice at once, as a plugin whose `hooks/hooks.json` names this
module and through `CLAUDE_CODE_PLUGIN_DIRS`, and then every hook runs in two environments.
Each instance claims an event with an atomic `mkdir` and the loser does nothing. Before the
claim, one fail-then-fix loaded that way wrote two lessons. Nothing prunes that directory.

`tools/report.py` prints the lessons log as counts and, for each lesson, how many later
failures were matched to it.

## Tests

```bash
claude plugin validate mod/compound
claude plugin test mod/compound                   # parsers, masking, rendering; no model calls
python3 mod/compound/tools/journey_lessons.py     # real sessions; run by hand
python3 mod/compound/tools/journey_mission.py     # real sessions; run by hand
```

`journey_lessons.py` passes on outcomes, each read from the session's own stream and from
files on disk:

|Step|What must be true afterwards|
|-|-|
|control|a session with the mod off fails the build first, and writes nothing|
|A|a session fails, fixes, and a project note exists that the agent did not write|
|B|a fresh session in that project runs the build with no failed call|
|C|a second project fails once, gets the lesson back, and the lesson moves to the global notes|
|S|the same write-down when the failure and the fix are inside a subagent|
|N|a check that legitimately fails, fixed by changing the work, writes no note|
|X|a command carrying a secret: the secret is in no note, log or ledger|
|D|the shell has `cd`'d into a subdirectory: the note is at the repository root|
|G|a lesson removed by hand is not stated back, and the second project gets its own note|
|W|with the mod loaded twice at once, one fail-then-fix writes one lesson|

`journey_mission.py` labels each step as an outcome or as delivery only:

|Step|Kind|What must be true|
|-|-|-|
|subagent|outcome, with a control|a subagent told nothing states a phrase only the user's prompt held; without the mod it cannot|
|compact|outcome, control also passes|the phrase is quoted back after `/compact`. In a two-message session it survives without the mod too, so this step shows delivery and not benefit|
|clear|outcome|after `/clear`, a short prompt is told nothing from the cleared session|
|scope|outcome|in three sessions, a subagent given a small task does that task and dispatches nothing|
|ambiguity, dispatch, completion, periodic|delivery|the moment is logged and the event happened; a resumed short prompt is told the request once|

The judge is scored against labelled pairs from the store `hooks/repeat-gate.sh` kept:

```bash
python3 mod/compound/tools/sample_pairs.py <state>/mod/pairs.jsonl 40
# add "label": "yes" | "no" | "unsure" to each row, then:
COMPOUND_REPLAY=<state>/mod/pairs.jsonl claude -p --plugin-dir mod/compound <<< hi
python3 mod/compound/tools/score_replay.py <state>/mod/pairs.jsonl.results.jsonl
```

The pairs carry commands from every project on the machine, so they are kept in the state
directory and not in this repository.

## Measured, 2026-10-03

Two sets of 40 stored pairs, labelled by Claude and not yet reviewed by a person. The
prompt was tuned on the first set; the second was labelled before the judge saw it. These
are the figures for the judge as it is now, after the red-team fixes.

|Set|Judge|Real lessons found|False lessons|
|-|-|-|-|
|tuned|sonnet|4 of 5|1 of 33|
|held out|sonnet|4 of 5|0 of 32|

Before the red-team fixes Haiku was scored on the same sets: 3 of 5 and 2 of 33 on the
tuned set, 4 of 5 and 6 of 32 on the held-out set. That is why the default is `sonnet`.

One judge call took a median of 2.4 s in those two replays (80 calls, four at a time;
the slowest took 7.5 s). A failed call waits for one such call when lessons exist, and each
of the next two successes waits for one.

Two cold reviewers red-teamed the mod on 2026-10-03, one half each, in real sessions.

The lessons half, 19 sessions: it reproduced a secret being copied into `CLAUDE.md`, a
removed lesson still being stated back, a note landing in a subdirectory, and comment
markers hiding notes from `skillnote list`. Steps X, G and D and the `skillnote` refusal
answer those. Injected instructions in error text were not recorded as advice in 3 of 3
attempts.

The mission half, 15 sessions: it reproduced the cleared session's request being stated
after `/clear`, and one subagent in five taking the mission block for its own task and
redoing the user's whole request. It also reproduced a prompt quoted twice from the store,
a request that begins with a path being dropped, and a completion statement firing on a
negated or interim message. The `clear` and `scope` steps and the unit tests in
`hooks/render.test.ts` answer those.

Neither half has been reviewed again since its fixes.

## Not covered

- The mod has run in ordinary work for less than a day (enabled 2026-10-03). Whether lessons stop recurrences,
  and whether the mission changes what a session does, are not known yet;
  `tools/report.py` is the instrument.
- The journeys use one contrived trap, a build script that needs a flag, and a `Bash`
  failure. No journey step fails a non-shell tool.
- Two parallel tool calls in one agent loop share one held failure.
- The scope step passed 3 of 3 after the subagent block was reworded; the defect it answers
  appeared 1 time in 5 before, so three sessions do not show it is gone.
- The compaction instruction and the default 1200 s interval have not been observed in a
  long real session.
- Identical lesson text gets the same note id in two projects, because `skillnote` derives
  the id from the text.
