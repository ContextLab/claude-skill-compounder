# 2026-09-03: the mission and the lesson — design

The maintainer restated the vision on 2026-09-03 (issue text quoted in the GitHub issue this
note backs). Two scenarios, three levels, two principles. This note says what exists, what
went wrong, what the platform can do (measured today), and the design that follows, in the
order the implementation waves take it.

## The vision, in the maintainer's words

Scenario 1: "when ambiguities arise, after context compaction, periodically during extended
work sessions, before engaging in an expensive (in time or effort) task like a multi-agent
task or something very complex, and before marking a task as complete: automatically remind
claude (main thread AND/OR subagents) about the exact text of relevant user requests."

Scenario 2: "after a failed attempt at doing something (anything!), and then figuring it out,
force claude to write it down (including the relevant contextual information and any
associated code or scripts) before continuing."

Levels: A project (`./.claude`), B user (`~/.claude`), C general (a pull request upstream,
automated). The levels govern "BOTH where to search for recent prompts AND where skills go".

Principles: (i) a single source of truth, never a second copy across levels; (ii) never rely
on remembering alone — reminders fire automatically, at the right moments, mid-task.

## What exists, and how far it goes

Audited at `733a07b` on 2026-09-03 (agent report, every row read against the file):

|vision item|exists|gap|
|-|-|-|
|1 ambiguity|nothing|no detector, no event|
|1 after compaction|`hooks/precompact.sh` captures candidates on PreCompact|emits nothing to the session; no SessionStart hook anywhere|
|1 periodic|`hooks/compound-improvement.sh` every 12 edits / 20 min|one fixed generic sentence, no task content|
|1 before expensive|nothing; no `Agent`/`Task` matcher|nothing fires before a dispatch|
|1 before completion|`claim-gate.sh`, `apply-gate.sh`, `doc-gate.sh` on Stop and commit|all judge artifacts (digits, markers, docs); none compares the work to the request|
|1 exact request text|`skillforge --trigger`, warns when absent|absent on 5 of 10 forges ever; no hook stores or reads prompts|
|1 subagents|subagent tool calls reach the PreToolUse arm of `remind.sh`|no `SubagentStart` wiring; nothing addressed to a subagent|
|2 fail-then-fix|`hooks/repeat-gate.sh` LEARN on `PostToolUseFailure`, RECOVER binds the next success of the same tool|a failed `Skill` or MCP call followed by a different tool's success is never bound; refuse arm off|
|2 forced write-down|`apply-gate.sh` forces an apply outcome for a forge|nothing blocks until a lesson is written; nothing fires on a `recover` row|
|2 code or scripts attached|only a forged skill directory carries scripts|no attachment at the note or reminder tier|
|findable and callable|reminders keyed on words, paths, command signatures|notes and memory are passive prose; nothing searches past prompts|
|A/B/C placement|`skillnote --scope project\|global\|memory`; C = `contribute-skill`|no route from a note or reminder to C; no move between levels|
|A/B/C search|`remind.sh` scopes rows project-then-global|nothing in the repo searches prompts at any level|
|C automated PR|`skillcontrib` is read-only reconnaissance by design|47 runs, 0 PRs ever|
|principle i|one store per artifact; three doctrine mirrors tested|the hand-written `~/.claude/CLAUDE.md` stanza is a fourth copy|
|principle ii|15 hook entries over 9 scripts, both wirings|delivery is counted, effect is not (10.5% nudge conversion)|

## What went wrong

From `notes/2026-09-02-audit-and-replan.md` (line references there):

- The forge was the only output for ten days: median 3.3 h and 8 agents per skill, one
  dispatched forge $3.02 / 19 min / abandoned, one wedged 3.5 days by a host sleep.
- The candidate queue took in 57 and produced 0; two paid verdicts were never acted on.
- 10.5% of sessions nudged to check for a skill did so; the edit checkpoint fired three
  times in one session and was disregarded three times. A reminder is delivered; nothing
  measures whether it changed anything.
- The measurement layer was dead in three places (unary counter vs digit reader, triple
  counted reuse, `verdict` never invoked).
- Imperative wording in an injected reminder was refused as prompt injection; reminders
  must be statements of fact.
- `--trigger`, the one field meant to carry the verbatim request, was optional and is
  missing on half the record.

The common thread: everything built was addressed to the session's *attention* — a nudge,
a queue, a checkpoint — and nothing carried the *content* the session had lost. A reminder
that says "check whether a skill exists" competes with the task; a reminder that says "the
user asked, verbatim: …" is the task.

## What the platform can do (measured on 2.1.259, 2026-09-03)

Twelve headless runs with canary strings, logs kept under the session scratchpad
(`research/hookprobe/`), to be written into `docs/CLAUDE-CODE-BEHAVIOR.md` by wave 2:

- `SessionStart` fires with `source` ∈ {`startup`, `resume`, `compact`}; `additionalContext`
  reaches the model in every case, and `compact` is reachable headlessly with
  `claude -p --resume <sid> <<< '/compact'`. The compact payload carries `model` and
  `prompt_id` and no context size; `resume` carries `context_tokens`.
- `SubagentStart` fires with `agent_id`, `agent_type`, no prompt; its `additionalContext`
  reaches the **subagent only**, never the parent. `UserPromptSubmit` and `SessionStart`
  context reach the **parent only**.
- `PreToolUse` on the `Agent` tool carries the subagent's `prompt` in `tool_input`, and
  `updatedInput` rewrites it — a write channel into the subagent the parent cannot see.
- A subagent's own tool calls fire the project's hooks, with `agent_id` and `agent_type`.
- `Stop` carries `stop_hook_active` and `last_assistant_message`; `decision: "block"` with
  a `reason` makes the model continue; nine consecutive blocks were accepted, so the cap is
  ours to impose. The model quotes the reason and declines any instruction in it — the
  reason must be a statement.
- `PreCompact` honours `systemMessage` only; it cannot write into the summary.

And from the sibling project: `claude-history-surfer` already stores every prompt once,
per project, as JSONL under `~/.claude/history-surfer/projects/<slug>/prompts.jsonl`
(`ts`, `session_id`, `cwd`, `project_slug`, `seq`, `prompt`, `is_command`), filters the
harness's pseudo-prompts, and searches with `surfer search --json` across 6480 prompts in
0.2 s. It has no reminder path. It is pure stdlib Python, installed by a marker-based
installer of the same shape as this one.

## Design

Two new mechanisms and one rule about levels. Nothing here replaces a working piece; each
reuses one.

### 1. The mission: `hooks/mission.sh`

One script, dispatching on `hook_event_name` the way `claim-gate.sh` does, wired on five
events. Its content is always the same object, **the mission**: the user's own prompts in
this session, verbatim, read from history-surfer's `prompts.jsonl` filtered on
`session_id`, commands and noise excluded. Rendered as a statement of fact, never an
instruction, under a fixed budget: the first substantive prompt in full up to
`MISSION_FIRST_CHARS`, the most recent `MISSION_RECENT` prompts up to
`MISSION_EACH_CHARS` each, whole text capped at `MISSION_MAX_CHARS`.

|moment|event and matcher|what happens|
|-|-|-|
|after compaction|`SessionStart`, `source` in `compact`,`resume`|`additionalContext` = the mission|
|before an expensive task|`PreToolUse` on `Agent\|Task\|Workflow`|`additionalContext` to the parent = the mission; and `SubagentStart` → `additionalContext` to the subagent = the mission plus the one line "the parent's instructions to you are above"|
|periodic|`PreToolUse` on `Bash\|Write\|Edit\|Agent`|once per `MISSION_INTERVAL` seconds since the last delivery in this session, the mission again|
|ambiguity|`UserPromptSubmit`|a prompt under `MISSION_SHORT_WORDS` words ("continue", "yes", "ok do it") is the prompt that relies on memory: deliver the last substantive request|
|before completion|`Stop`|when `last_assistant_message` reads as a completion claim and the turn made at least `MISSION_STOP_MIN_TOOLS` tool calls, block **once per `prompt_id`** with a reason that is the mission verbatim, guarded by `stop_hook_active`; never a second block for the same prompt|

Idempotence keyed on `prompt_id`, `tool_use_id`, `agent_id` under `<state>/mission/<sid>/`,
because both wirings deliver every event twice. Every delivery appends one row to
`<state>/mission/hits.jsonl` (`moment`, `session`, `agent_id`, `chars`), so the next
measurement can count deliveries per moment and join them to outcomes (#37). Cooldown and
budget constants are unvalidated, like the other six, and say so.

The `Stop` arm uses `updatedInput` nowhere: the subagent channel is `SubagentStart`, which
the parent can read in the transcript. Rewriting a subagent's prompt behind the parent's
back is the one measured channel this design declines, and the reason is recorded here.

Level B search (relevant prompts from other projects) is not in this wave. The reminder
tier already scopes project-then-global, and `surfer search --all` is one command away
through the `history-surfer` skill. What would earn it: a keyword-overlap trigger with a
measured false-positive rate. Stated as a limit, not built.

### 2. The lesson: a fail-then-fix that must be written down

`hooks/repeat-gate.sh` already learns a failure signature on `PostToolUseFailure` and binds
the next success of the same tool as its recovery. Two extensions and one gate:

- **Cross-tool recovery.** A failure of tool X (an MCP tool, a `Skill`, a `Bash` command)
  followed within `REPEAT_RECOVERY_WINDOW` calls (the existing default of 5 was kept when this
  landed; the issue text says 6) by a success of tool Y whose input shares
  content tokens with the failed input (a repo name, a path, a URL) is bound as a recovery
  too, tagged `cross_tool`. This is what "the GitHub skill fails, `gh` works" looks like on
  the wire, and today it is never bound.
- **The first time: say it.** When a `recover` row is written, the `PostToolUse` arm emits
  `additionalContext`: the failure and the fix, verbatim, and the one command that records
  the lesson. A statement, delivered at the moment the fix happened.
- **The second time: refuse until it is written.** When the recovered signature has been
  seen in `REPEAT_MIN_SESSIONS` or more sessions (the store already counts this) and no
  lesson references it, the `PreToolUse` arm denies the next tool call with the same text.
  That is "before continuing", made deterministic, and it fires on the second occurrence —
  the doctrine's own threshold. `skillnote add --lesson <sig> "<text>"` or
  `skillrepeat dismiss <sig> --why "<why>"` lifts it; the dismissal is a row, not a delete.

`skillnote add --lesson <sig>` writes **one** record that is both a note (the dated line in
the scoped `CLAUDE.md`) and a reminder keyed on the failing command signature, so the next
time that command is about to run, the fix is in context before the failure. `--attach
<path>` copies a script or file into `<scope>/.claude/lessons/<id>/` and the line links to
it; that is the "code or scripts" the vision asks for, callable by path, and the thing a
lesson grows into a skill from.

### 3. Levels: where a thing lives, and how it moves

The rule already in `SKILL.md` — highest applicable level — gets a mechanism:

- `skillnote promote <id> --to global` **moves** a project lesson to the user level and
  leaves a one-line tombstone pointing at it; never a copy (principle i). `skillinsight`
  proposes the move when the same signature is recorded from a second project.
- `skillcontrib propose <skill>` does level C end to end: package, duplicate check against
  upstream and every open PR (already built), fork if not a maintainer, push, `gh pr
  create`. One command is the consent; the network writes happen only inside it, and it
  prints each before it runs. The read-only reconnaissance stays as `skillcontrib` bare.
- The installer installs history-surfer when `surfer` is absent (its installer is the same
  marker-based shape), wires `SessionStart`, `SubagentStart`, the `Agent|Task|Workflow`
  matcher and the lesson arms, mirrors them into `hooks/hooks.json`, and `skillforge doctor`
  reports `surfer` and the mission store. Without history-surfer the mission hook is inert
  and doctor says FAIL, rather than the hook keeping a second copy of the prompts.

### What is deliberately not built

- No semantic search; substring and regex over history-surfer are what exist.
- No detector of "ambiguity" beyond the short-prompt proxy; a better one needs a measured
  false-positive rate first.
- No rewriting of a subagent's prompt (`updatedInput`), for the reason above.
- No automatic forge from a lesson; the forge threshold stands, and a lesson that recurs
  across projects is the evidence it asks for.

## Waves

Wave 1, five builders on disjoint files:

- `hooks/mission.sh` + `tests/test_mission.py` (reads history-surfer's JSONL; a fixture is
  a real file written in that format, and the test also drives the real `surfer` hooks
  when present).
- `hooks/repeat-gate.sh` cross-tool recovery, lesson arms, `skillrepeat dismiss` +
  tests.
- `bin/skillnote --lesson`, `--attach`, `promote` + tests.
- `bin/skillcontrib propose` + `skills/contribute-skill/SKILL.md` + tests against a local
  bare upstream (the shape `tests/test_install_sh.py` uses).
- `skill_compounder/installer.py` (history-surfer install, new entries, doctor) +
  `hooks/hooks.json` + tests.

Wave 2: every document — README, `docs/architecture.md`, `docs/operations.md` (knob rows and
the derivation count), `docs/DESIGN.md` (the declined channel), `docs/measurement.md`
(mission and lesson deliveries), `docs/CLAUDE-CODE-BEHAVIOR.md` (today's measurements),
`.claude/CLAUDE.md`, `skills/skill-compounder/SKILL.md` and its mirrors — then the E2E
journey gains a compaction step and a subagent step, the full suite, and one live session
on this machine that shows each moment firing.
