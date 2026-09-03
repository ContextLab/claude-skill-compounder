# Architecture

What the parts are and what talks to what. [`README.md`](../README.md) is the front door:
install, cost, and the five-minute path. This page is the level below it, and three
sibling pages carry the rest — [`operations.md`](operations.md) for running and tuning an
install, [`measurement.md`](measurement.md) for what gets counted and what those counts
are evidence for, [`development.md`](development.md) for working on the repository itself.
[`DESIGN.md`](DESIGN.md) records why each decision here went the way it did, and
[`CLAUDE-CODE-BEHAVIOR.md`](CLAUDE-CODE-BEHAVIOR.md) records the Claude Code behaviour
those decisions rest on.

The organising idea is three tiers of durable lesson. A **note** is a dated line in a
`CLAUDE.md` or a memory file. A **reminder** is a match rule that a hook states back at
the moment it applies. A **skill** is the expensive tier, forged adversarially and
installed into `~/.claude/skills/`. `bin/skillnote` writes the first two in one command
each, `bin/skillforge` drives the third, and every one of them appends a row to the same
ledger, so how often each tier is taken is a query rather than a guess.

## What gets installed

|Piece|What it does|
|-|-|
|`skills/skill-compounder/`|The doctrine: when to forge, how to forge, how to fix or retire a bad skill|
|`skills/skill-authoring/`|How to write the SKILL.md itself: the description that decides when it fires, and the gates that prove it parses|
|`skills/<the rest>/`|The seed pool, below. Useful before you have forged anything|
|`skills/contribute-skill/`|Proposes a proven local skill back to this repo as a pull request|
|`hooks/compound-improvement.sh`|Two throttled reminders: "does a skill already exist?" and "is this worth crystallizing?"|
|`hooks/insight-capture.sh`|Queues skill candidates a session flags, for one batched review a week|
|`hooks/precompact.sh`|Fills the same weekly queue from the transcript a compaction is about to replace with a summary, so a session that compacts without a `Stop` capture does not lose the turn. No model call and a bounded read; rows carry `source: precompact`. Wired on `PreCompact` with no matcher, so both triggers reach it|
|`hooks/skill-use.sh`|Records one ledger row per skill invocation, as it happens: wired on `PostToolUse` and `PostToolUseFailure`, matcher `Skill`|
|`hooks/claim-gate.sh`|Refuses a turn — or a `git commit` — that ends on a figure the session never produced. Wired on `Stop` and on `PreToolUse`, matcher `Bash`: [The claim gate](#the-claim-gate)|
|`hooks/repeat-gate.sh`|Learns the signature of a tool call that failed, and when the same call has failed the same way in two earlier sessions it can deny the third attempt once and say what to do instead. **That refusal is off by default** (`REPEAT_GATE_REFUSE=1` arms it); learning and recovery run either way. Wired on `PostToolUseFailure`, `PostToolUse` and `PreToolUse`, matcher `Bash\|Skill`. Off switch `SKILL_COMPOUNDER_REPEAT_GATE=0`; the store is `bin/skillrepeat`|
|`hooks/doc-gate.sh`|**Refuses.** Denies a `git push` whose commits carry code and no documentation, and names the `claim-provenance` skill. Wired on `PreToolUse`, matcher `Bash`. Off switch `SKILL_COMPOUNDER_DOC_GATE=0`; per-push escape hatch in the deny reason|
|`hooks/apply-gate.sh`|**Refuses, once.** After a forge closes, blocks that session's turn to say the new skill has not yet been used on the problem that caused it — then names that skill at most once per session and lets go. A flag, not a wall. Wired on `Stop`. Off switch `SKILL_COMPOUNDER_APPLY_GATE=0`; the debt is answered with `skillforge apply`, and `--outcome declined` is a first-class answer|
|`hooks/remind.sh`|Delivers a reminder recorded by `skillnote add --remind` at the moment it applies, and states it rather than instructing. Wired twice: on `UserPromptSubmit`, where it matches keywords against your prompt, and on `PreToolUse`, matcher `Bash\|Write\|Edit`, where it matches a normalised command signature or a path glob. It denies nothing. Off switch `SKILL_COMPOUNDER_REMIND=0`|
|`hooks/session-review.sh`|**Calls the Anthropic API, and is off until you switch it on** with `SKILL_COMPOUNDER_REVIEW=1`. After a long session ends, one detached `claude -p` reviews that session for a repeatable procedure. Costs and how to enable it: [What runs against the API](../README.md#what-runs-against-the-api). Not a hook entry — `insight-capture.sh` starts it, so nothing wires it into your settings|
|`bin/skillforge`|Tiny CLI the session drives to report forging progress. Also writes the forge ledger, records the *use* that closes a forge (`skillforge apply`) and what happened when it was used (`skillforge verdict`), checks the install (`skillforge doctor`) and closes out forges nothing has stepped in six hours (`skillforge reap`). `skillforge round` records one red-team round against the forge's budget and refuses the round past it; `skillforge escalate` is the only way past that refusal, and buys exactly one more round on a falling blocking count or on a skill the forge narrowed; `skillforge horizon` writes the ledger's horizon row on its own, which is how `bin/skillnote` gets one without a second copy of that logic|
|`bin/skillnote`|Writes the lesson down where something will read it, in one command and with no model call: a dated line in a project or global `CLAUDE.md`, or a Claude Code memory file with the `MEMORY.md` index line that gets it read back. With `--remind` it writes a match rule to the reminder store instead, for `hooks/remind.sh` to deliver|
|`bin/skillreport`|Joins the ledger against your transcripts: what got forged, and whether it got used again|
|`bin/skillinsight`|Reads and prunes the candidate queue|
|`bin/skillcontrib`|The read-only reconnaissance behind `contribute-skill`: duplicate check, push-access check, preflight|
|`bin/skillrepeat`|Reads, inspects and clears the repeat gate's store of learned failure signatures|
|`statusline/`|Renders the live forge animation, wrapping any status line you already have|

The hook changes are additive: hooks installed by other tools are left alone, and
uninstall removes only ours. `statusLine` is the one entry that cannot be additive,
because it holds a single command — ours replaces it and calls your previous one first.
The original is saved and restored on uninstall, and sibling keys you set on it, such as
`padding`, are carried across unchanged.

`settings.json` is backed up before every change. If yours is a symlink into a dotfiles
repo, it is written *through* rather than replaced, so the link survives. Symlinks in
`~/.claude/skills` and in the CLI directory are only ever replaced or removed when this
package can prove it created them; anything else of yours at one of those names is
reported and left alone.

## As a plugin

The repo is a valid Claude Code plugin, so you can load it without installing anything:

```bash
claude --plugin-dir /path/to/claude-skill-compounder
```

That gets you the skills (namespaced `skill-compounder:<name>`, so they cannot collide
with skills you already have), the hooks, and `bin/` on the Bash tool's `PATH`. It does
**not** get you the forge animation: a plugin's `settings.json` accepts only `agent` and
`subagentStatusLine`, and `statusLine` is not among them
([CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md)). That is why the installer
is the primary path.

Running both at once is safe: each event carries a `prompt_id` or `tool_use_id`, and the
hooks claim an event once, so the second delivery does nothing.

## The seed pool

Everything under `skills/` installs into `~/.claude/skills/`, and not all of it is seed
pool. `skill-compounder`, `skill-authoring` and `contribute-skill` are the machinery, and
each has its own row in [What gets installed](#what-gets-installed). The rest is the pool: **nine seed skills ship in
it**, so a fresh install is useful before you have forged anything.

Each one is here on evidence that the failure is common, not on a hunch. For the
first four that evidence is multiple independent reports in `anthropics/claude-code`, laid
out in [`notes/research/seed-skill-candidates.md`](../notes/research/seed-skill-candidates.md).
`ai-tell-audit` came from a different place: a published catalogue of Claude-specific
writing tells at [claudisms.ai](https://claudisms.ai), Wikipedia's "Signs of AI writing",
and discussion-board threads where people name what they notice. Ten structural families
sit on top of those word lists, because a word search cannot see sentence construction.
The skill records what each source said at the last pull and ships a guarded command that
reports whether any of them has moved, so the catalogue can be brought forward as those
lists change.

A reviewer who had not seen it ran the whole procedure over twelve documents it was not
built from. It edited none of the eight human ones. Four machine-drafted documents also
came through unedited, which is the error it makes: prose generated as reference material
carries few of these patterns, and the skill states that limit.

`claim-provenance` came from this repository's own defects rather than from the issue
corpus: a test that pinned the literal string `"103 skills"`, and so enforced a claim's
presence instead of its truth; a document claiming eight forges against a ledger holding
three; a ledger field documented as a budget it had stopped being; and a lesson about YAML
frontmatter taught wrongly in four files for months. Every one of them passed a green
suite. It also ships on a different footing from the rest of the pool: it was narrowed
over ten rounds and was **not clean at the end**, with the round-10 fixes verified by
running them but not cold-reviewed. Two independent reviewers were asked whether it should
exist at all and both said keep. It is the one skill here whose final round no fresh agent
signed off.

|Skill|Fires when|The failure it prevents|
|-|-|-|
|`destructive-op-preflight`|Before `reset --hard`, `clean`, `rm -rf`, `--force`, or any bulk delete|Untracked files are not in the reflog. One report lost 2,229 of them; another had `git reset --hard origin/main` run autonomously in the first second of a session, twice|
|`session-handoff`|Context is about to be lost: compaction, a usage limit, the end of a session|A handoff that summarises the error instead of quoting it is not resumable. One user built a whole memory system from scratch rather than keep re-deriving state|
|`stale-artifact-check`|Behavior after an edit is indistinguishable from behavior before it|You are debugging a copy that never contained your change: a non-editable `pip install`, a `.pyc` beside the source, an unrebuilt `dist/`. It hands general debugging to `superpowers:systematic-debugging` rather than compete for that trigger|
|`no-silent-stub`|You are about to return a value you did not compute|A fake that does not look like a failure looks like a pass. One reported evaluation copied the expected answer into the actual answer column and scored 100%|
|`ai-tell-audit`|You are about to publish a README, an issue, a PR description or docs|Prose a model drafted carries recognisable tells. The skill knows them and says, per pattern, whether to rewrite it, delete it, or keep it. It never judges who wrote anything, because automated detection scores human writing as machine-written often enough to be unusable|
|`claim-provenance`|A claim that is already written down is checked or carried forward: a count restated from another document, a documented behaviour nobody measured, a test asserting what a document says rather than whether it is true|A green suite proves the sentence is present, not that it is true. It defers to `ai-tell-audit` for how prose reads, and its description says so, so the two do not race for one trigger|
|`finish-task`|A unit of work is done and the pre-publish sequence still has to run|Every step between "it works" and "it is published" is skippable with no immediate consequence, at the moment the author most wants to be done. It sequences them and owns none of them: the prose check is `claim-provenance`, the did-the-run-contain-my-change check is `stale-artifact-check`, and the merge-or-PR decision is `superpowers:finishing-a-development-branch`|
|`dead-guard-detection`|A cap, limit, validation or early exit is relied on but has never been OBSERVED firing|A dead guard is usually correct in isolation and the program behaves plausibly either way, so no symptom points at it. This repository shipped one: `CLAIM_GATE_MAX_BYTES` was dead code on every macOS, because `wc -c` pads its output and the numeric guard read the leading space as non-numeric|
|`parallel-agents-one-codebase`|Two or more agents will EDIT, FIX or REFACTOR files in one shared working tree|Every read sees every other agent's uncommitted, half-written edits. Measured here while forging these two: a suite run read a file an agent was mid-write on and reported a failure that did not exist, and a builder committed a fixture into the real repository|

**The last two were promoted, not seeded.** They were forged locally, lived in
`~/.claude/skills` as the only copy of themselves, and were brought in on 2026-09-01
after the session that needed the skills above also needed both of these. Their
usage evidence is **none**, and the first draft of this paragraph said otherwise. Checked
row by row: `parallel-agents-one-codebase` has 17 recorded invocations and every one is
`harness=true` in a `routing-probe-*` directory, which is this package measuring itself.
`dead-guard-detection` has 28, of which 27 are the same. Its one non-harness row is stamped
28 seconds after its own forge closed, by the session that forged it, which is a forge
finishing rather than a skill being reused.

So both are here on the strength of the defects they name recurring in this repository, and
on nothing else. By the bar `contribute-skill` sets for proposing a skill upstream -- clean
from the red-team loop **and** used again since it was forged -- neither would qualify
today. That bar governs proposing to strangers rather than shipping to yourself, and the
difference is deliberate, but the gap is recorded here rather than left for a reader to
discover.

**A defect this exposed:** the forge was named `dead-guard-check` and the skill it produced
is `dead-guard-detection`. `skillreport` joins uses to forges BY NAME, so it reports that
forge as having produced a skill invoked 0 times, and would do so however often the skill
were used. A skill renamed between forging and installing is invisible to the reuse half of
the ledger, silently.

The loudest complaint in the corpus is deliberately **not** here:
`superpowers:verification-before-completion` occupies that trigger, and two skills racing
for one trigger is worse than one skill. Occupying is not covering: it has been invoked 0
times in the local transcript corpus (source: `Skill` records under `~/.claude/projects`,
as of 2026-08-26), because the moment it names offers a router no user prompt to match
(`notes/2026-08-25-completion-claim-gap.md`).

## The three habits

Two of these are reminders inside the session, and a session can read past a reminder.
Measured: one long session fired the 12-edit checkpoint at edits 12, 24 and 36,
disregarded it all three times, and fixed nine defects of one kind in between. Per
instance the answer it gave — "no, I am just fixing a bug" — was honest. So the second
habit also has an arm that asks nothing of the session and that the session cannot
decline, and a fourth mechanism below the three refuses outright rather than asking at
all: [The claim gate](#the-claim-gate).

## Three ways to compound: note, reminder, skill

A forge is the expensive answer, and for most of what a session learns it is the wrong one.
Three tiers ship, and the first two cost one command each:

|Tier|What it costs|Where it lives|What reads it back|When to pick it|
|-|-|-|-|-|
|**note**|one command|a marker block in a project or global `CLAUDE.md`, or a Claude Code memory file|Claude Code, on every session that loads that file|the lesson is a fact with no steps: a path, a version, a command that works|
|**reminder**|one command|`reminders.jsonl` in the state directory|`hooks/remind.sh`, when a prompt, a path or a command signature matches|the lesson applies at a moment you can name, and only then|
|**skill**|a builder subagent, a cold reviewer, two rounds|`~/.claude/skills/<name>/` or a project's `.claude/skills/`|the router, when a prompt matches the description|the procedure has steps, and a description can route to it|

```bash
skillnote add --scope project "<the one-line lesson>" --why "<the dead end>" --source forge
skillnote add --remind --scope project "<the lesson>" --keyword <k> --command "<the call>"
skillnote list --scope remind
```

<!-- doctrine: tier-before-forge -->
**A procedure earns a skill only when it has steps a model gets wrong without them AND a
trigger a description can route; otherwise it is a note or a reminder.** Both halves are
checkable before anything is dispatched. A fact has no steps, so forging "the suite is
`./run_tests.sh`" wraps one sentence in eight hundred; and if the moment the procedure
applies is internal to the assistant, with no utterance to match on, no description will
route to it, while a reminder keyed on the tool call or the path will fire.

The tiers promote rather than compete. A note that keeps getting rewritten is a recurrence,
which is half the forging threshold, and both cheap tiers write a `note` row to the same
ledger the forges are recorded in, so "we have written this down four times" is a query
anyone can run. `skillinsight promote <hash> --to note|reminder` takes a queued
candidate the other way, writing it down now instead of forging it or losing it.

**What the memory scope does and does not get you.** `--scope memory` writes a Claude Code
memory file and appends its index line to `MEMORY.md` in the same directory. Measured
2026-09-02 on Claude Code 2.1.258: a memory file that `MEMORY.md` indexes is injected into a
later session, and one it does not index was seen in 0 of 3 runs. The index line is what makes
the read-back happen, so the ledger row for that scope records `readback:"via-index"` and
claims nothing about the file on its own.

### 1. Before implementing, reuse before you build

At the start of a substantive turn, a `UserPromptSubmit` hook reminds the session to check
whether a skill already covers the task, before writing a plan or any code. Throttling
holds it to one reminder per 20 minutes, and it fires only for prompts of 60+ characters,
so `yes` and `continue` never trigger it.

### 2. During work, notice what is worth keeping

Every 12 file edits, a `PostToolUse` hook asks whether a given procedure clears the bar.
It counts `Bash` alongside `Write` and `Edit`, because a session told to edit with `sed`,
heredocs and inline interpreters produces almost no `Write` calls, and the checkpoint then
goes quiet in the long autonomous sessions it exists for. Read-only commands are filtered
out by inspecting the command string, so `ls` never counts toward a checkpoint.

The same question is also asked where no session gets a vote. On `Stop`, once a session
has crossed 24 edits across 8 files, `hooks/insight-capture.sh` writes a session-audit
record from counters that `hooks/compound-improvement.sh` already wrote to disk — nothing
is asked of the session and nothing it said is consulted — and then starts
`hooks/session-review.sh` detached. That is a separate `claude -p` whose only task is this
question, reading a digest of the session that just ended. It costs money, so it runs
only for someone who set `SKILL_COMPOUNDER_REVIEW=1`:
[What runs against the API](../README.md#what-runs-against-the-api).

**That arm analyses and queues. It does not forge.** Its verdict is `NONE` or
`CANDIDATE <name>`, written to `~/.claude/skill-compounder/reviews/` and reported by
`hooks/compound-improvement.sh` the next time you are in a session. Turning a `CANDIDATE`
into a skill is still a decision a person makes: the forging stage is off by default, and
switched on it writes to a staging directory rather than to `~/.claude/skills`.

<!-- doctrine: both-conditions -->
**Both must hold, or it gets a note rather than a skill.**

- **Costly**: name the specific dead end in one sentence, and what a fresh session would
  have done instead. If you cannot name it, it was not costly, it was just work. **And**
- **Recurring**: point at the second occurrence, in a prior session, earlier in this one,
  or an open issue. "It seems like the sort of thing that recurs" is not a second one.

Both want a **concrete referent** rather than a judgement, because both are otherwise
loose enough to say yes to nearly any non-trivial work, and a threshold that always
resolves to yes is worse than none.

<!-- doctrine: cheap-branch -->
**The cheap branch is a command, not an intention: `skillnote add` records the note or the
reminder, and a lesson nobody ran a command for was not kept.**

```bash
skillnote add --scope project "<the one-line lesson>" --why "<the dead end>" --source forge
skillnote add --remind --scope project "<the lesson>" --keyword <k> --command "<the call>"
```

When both conditions hold *and* the procedure has steps a description can route to, the
session runs the **forging protocol**. Every stage is denied something the stage before it
had, and the denials are the mechanism:

```
skillforge start <name> <total-steps> "<one-line summary>" \
    --trigger "<the verbatim text that set this forge off>" \
    --trigger-kind <user-prompt|hook-checkpoint|review-dispatch|agent-decision>
  │
  ├─ A: this session       → the only agent that sees the project; pre-registers the
  │                          success criteria, the level, and the verbatim trigger, to disk
  ├─ builder agent (C)     → scratch directory, no path into the project; runs every
  │                          command it documents, in the background
  ├─ red-team agent (D)    → FRESH context, given the skill and nothing else; infers
  │                          the scenario from it, then executes what it inferred
  ├─ loop (2 rounds)       → findings back to the builder; a NEW red-teamer each round
  ├─ cap at 2 rounds       → `skillforge round` refuses the third; earn it with a falling
  │                          blocking count, or narrow, or abandon it honestly
  └─ A again               → runs the skill against the real case, scores the criteria
                             it pre-registered, and runs the routing gate
  │
skillforge done "<outcome>" ; skillforge apply … ; skillforge verdict …
```

Two dispatched agents and two rounds. A narrow skill should close in under 30 minutes; when
it does not, the scope was wrong rather than the budget. Only a forge that has bought a
third round gets the older, longer shape back — an orchestrator to keep the traffic off
this thread, and a judge at the end:

```
skillforge start <name> <total-steps> "<one-line summary>" --trigger … --trigger-kind …
  │
  ├─ A: this session        → as above, plus the raised budget
  ├─ orchestrator agent (B) → no project content; runs the loop from the granted round on,
       │                      and hands your thread back
       ├─ builder agent (C)  → scratch directory, no path into the project
       ├─ red-team agent (D) → FRESH context, given the skill and nothing else
       ├─ loop               → findings back to the builder; a NEW red-teamer each round
       └─ cap at 2 rounds    → (4 for a complex or safety-critical skill), and never more:
                               two grants is the ceiling, whatever the counts do
  ├─ A again                → the real case, the criteria, the routing gate
  └─ E: a fresh judge       → gets the verbatim trigger on its own; does A's framing
                              match it? Install at A's level, or quarantine
  │
skillforge done "<outcome>" ; skillforge apply … ; skillforge verdict …
```

<!-- doctrine: hard-round-cap -->
**A third round is earned by a falling blocking count, and `skillforge` refuses the round
without one.** `skillforge round` past the budget exits 3 and writes no row; `skillforge
escalate --converging` grants one more round only when the last two rounds show a strictly
falling count of blocking findings, and `--narrowed "<what you cut>"` grants one, once, for
the cold read a narrowed skill owes. Two grants is the ceiling, so the loop terminates at
four rounds however the counts move.

Paste the trigger, do not summarise it: it is the one thing about a forge that nothing can
recover afterwards, because a quote is what a person actually said or what a hook actually
emitted, and by the time anyone reads the row the moment is gone. `--trigger-kind` says who
was asking — `user-prompt` for a human, `hook-checkpoint` for the edit checkpoint,
`review-dispatch` for a session review, `agent-decision` for the session's own initiative.
Whether that field drifts from `agent-decision` towards `user-prompt` over months is the
measurement this package exists to make. A forge started without a trigger still runs and
records `trigger_kind:"unrecorded"`, so the gap can be counted rather than assumed away;
`SKILLFORGE_REQUIRE_TRIGGER=1` turns the warning into a refusal.

<!-- doctrine: routing-gate-on-completion -->
**A forge cannot be reported clean while the skill's own must-fire prompts do not fire
it.** A reviewer reading the draft's `## Trigger precision` section and agreeing it looks
right is not that check. Every skill in the seed pool passed a full builder/red-team loop
that way, and when the prompts were finally run on 2026-08-25 three of the claims were
false: `stale-artifact-check` lost two of its three must-fire prompts to
`superpowers:systematic-debugging`, and `session-handoff` and `skill-compounder` each
listed one that fires nothing at all. So the draft carries at least three prompts that
must fire it and three that must not, each written as the verbatim utterance a user would
type, and the session that started the forge runs them before it closes. The red-teamer
runs them too, as one row of its checklist, but the gate is A's: it is the last thing
checked before the forge is reported clean. When a must-fire prompt loses, what changes is
the description, not the prompt and not the verdict.

<!-- doctrine: must-not-half-is-a-gate -->
**A skill that fires on everything is worse than no skill.** The must-not half is a gate
in the same way: a skill that answers every prompt displaces the neighbour that would have
handled it properly. Read which skill the report says fired, not only its PASS column.

<!-- doctrine: unmeasured-is-not-verified -->
**A probe that could not run is never a pass.** No login, no quota, offline: the skill may
still ship, but it ships marked unmeasured and says so where the next session will read
it. What is forbidden is the silent promotion of an unrun probe to a verified one.

<!-- doctrine: forge-runs-in-the-background -->
**Every agent a forge dispatches runs in the background, and the session that starts one
never blocks on it.** Blocking was never the problem — the agents always ran in the
background. The problem was that every review report landed in the thread the user is
talking to, and every revision brief was written out of it. Two rounds of that traffic,
polled for a marker file rather than relayed message by message, is a cost the shorter
forge can pay; the rounds beyond two are what earned the orchestrator, which is why it
comes back only when the budget does.

`skillforge` is on a subagent's `PATH`, so the animation keeps moving while the main thread
does something else. One level of nesting is all the protocol relies on: a level further
down, probes found `Agent` present for one agent and absent for another, with no rule
predicting which ([CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md)). So the
builder and the red-teamers dispatch nobody, and orchestrators are never nested.

The level the skill installs at and the number of rounds the loop gets are both settled
before the builder is dispatched, in the file A writes to disk. The cap is encoded in the
`<total-steps>` passed to `skillforge start`, and `skillforge escalate` is the only command
that can raise it.

**A skill belongs at the highest level of the hierarchy to which it applies, and must be
written generally enough to apply beyond the case that prompted it.** The hierarchy is
general, then user, then project: a project skill has to work beyond the specific task, a
user skill beyond the specific project, a general skill beyond both. Use runs the other
way, which is what makes the rule cheap — a general skill can still be applied to one
project, so placing it high costs nothing.

**The specialisation comes from the project's or the user's `CLAUDE.md` and the constraints
already recorded there — never from text baked into the skill.** A skill that hardcodes one
repository's test command has made that repository's particulars everyone's; the same skill
saying "run the project's suite" reads the particular out of the `CLAUDE.md` that already
states it.

<!-- doctrine: close-ownership -->
**You own `start`, `done` and `fail`; every agent you dispatch owns everything between.**
They report an outcome rather than closing the record, so a forge whose builder or
orchestrator dies is still one someone can close — and a second close is not a correction,
it is discarded silently at exit 0. A closed forge then records two more rows in the same
turn: `skillforge apply`, for whether the skill was put on the problem that caused it, and
`skillforge verdict`, for what happened when it was.

<!-- doctrine: no-forked-reviewer -->
**The red-teamer must never be a fork of either layer** — not of the orchestrator that
dispatches it, and not of the session that dispatched the orchestrator. A forked
reviewer already knows what the skill was *meant* to say, so it cannot detect the
ambiguity that will bite a cold session six weeks later.

**D is given the skill and nothing else, and must infer for itself what situation the skill
is for.** That inference is the completeness check, and it is the first row of the
checklist: a skill whose scenario cannot be reconstructed from its own text has a hanging
reference in it. The rest of the rows are cold-start executability, trigger precision (3
prompts that should fire, 3 that should not, run rather than read), every asserted command
actually run, portability — does an example need a project the reviewer cannot see? —
unhappy paths, overlap with existing skills, and scope creep.

<!-- doctrine: no-leading-prompt -->
**Never hand a reviewer a list of what not to flag.** Scoping a brief that way reads as
instruction about what the answer should be, and the review narrows to match. Measured on
this repo's own documentation: the same file, reviewed by one agent given a "do not flag
these" list and by one given only the principle, produced **1 finding and 4** — and the
unprimed reviewer defended two passages the primed brief would have condemned.

**On a forge that ran past two rounds, ask E whether A's framing matches the trigger it
came from.** A's one-paragraph framing is what the builder is allowed to see, so everything
downstream inherits it — including E's own question about whether the original problem got
solved, which E would otherwise learn only from A. The verbatim trigger, handed to E
separately and off the forge record, is what catches a misframing. A "no" there is a failure
however good the skill is, and the skill is quarantined, not installed: each agent appends a
signed section to the report, nobody may rewrite anyone else's, and contradictions are kept
and flagged rather than reconciled, because a merged narrative hides the most informative
thing a failed forge produces. At the default budget there is no E, so A writes that
sentence itself at step 1, beside the verbatim trigger, where the answer is still cheap.

### 3. When a skill misfires: fix, document, or retire

<!-- doctrine: no-silent-workaround -->
**Never silently work around a skill that misfired.** The workaround costs the same
time again in every future session. Escalate instead: fix the wording, and if the procedure itself is
wrong, fix that and then re-run the full red-team loop. Retire it only when neither works.

Retirement requires **independent concurrence**.

<!-- doctrine: neutral-retirement-question -->
**Ask a second fresh agent the neutral question, *"should this be kept, fixed, or
retired?"*, never "confirm this deletion".** The second form is a leading prompt, and any
agent will (obligingly) rubber-stamp it.

Retiring archives the skill with a `WHY-ARCHIVED.md`.

<!-- doctrine: archive-the-source -->
**Archive the source, not the link.** Most skills here are symlinks into a checkout, so
moving
`~/.claude/skills/<name>` moves the link, leaves the real directory where the next install
resurrects it, and writes the tombstone into live source. Resolve with `realpath` first,
move the resolved directory, then drop the dangling link.

<!-- doctrine: never-rm-rf -->
**Never `rm -rf` a skill.**

## The claim gate

[The three habits](#the-three-habits) above are reminders, and that section opens by
conceding what a reminder is worth. `hooks/claim-gate.sh` is the one mechanism here that refuses rather than asks. It
reads the closing message of a turn on `Stop`, and the message of a `git commit` on
`PreToolUse`, looks for an integer of `CLAIM_GATE_MIN_DIGITS` digits or more, and checks
whether that figure appears anywhere in what the session's own tools printed. If it does
not, the turn is blocked once with the finding, or the commit is denied.

Two things it deliberately does not count as evidence. A subagent's report — the gate cuts
`Agent` and `Task` tool results out of the evidence before it looks, because relayed
testimony is what produced both of the defects it was written for: a commit message here
claimed 1495 tests when the derived figure was 1195, and an earlier one claimed 544 tests
passing on a tree that failed one. And a verification that has gone stale, which is the
second tier: a figure supported only by a run that predates a later edit to a file that run
covered.

**What it costs you in false blocks.** Replaying real closing messages turn by turn, with
the transcript truncated to each turn's end so nothing was judged against evidence that did
not exist yet: 6 blocks in 205 messages (2.9%) on the session the rules were tuned against,
and 3 in 88 (3.4%) on a held-out draw from 14 transcripts of other projects, measured
2026-08-26. Read the held-out figure, not the tuned one — the tuned corpus was optimistic
by roughly threefold on work the gate had never seen. Of the 3, one is a relayed figure and
is flagged on purpose; the other 2 quote a number in order to dispute it, and no
deterministic rule separates quoting a figure from asserting it. The full calibration,
including the two rule sets that were measured and discarded, is in the script's own
header.

Only the last `CLAIM_GATE_MAX_BYTES` of the transcript is scanned — 16 MiB by default. A
figure printed before that window and restated at the end reads as unsupported, which is a
false block in the one direction this gate is not supposed to err. The window exists
because the hook is wired with a 10-second timeout: 16 MiB parses in about 1.6s against
that budget, and on the machine where this was measured 9 of 419 transcripts (2.1%) were
larger than it. An earlier 64 MiB cap was dead code on every BSD box, because `wc -c` there
prints a leading-space-padded count and the numeric guard read the space as non-numeric and
zeroed the cap.

The gate spends at most `CLAIM_GATE_MAX_SESSION` blocks and denials in one session and
then stands down, so it cannot wedge a session it is wrong about. `CLAIM_GATE=0` switches
it off; the rest of its knobs are in [Tuning](operations.md#tuning).

## The animation

While a skill is being forged, your status line shows live progress:

```
my-project git:(main)  ⣻ forge parallel-agents-one-codebase ▕██████······▏ 3/6  50% · red-team round 1
```

The tail alternates between what is happening right now and a one-line summary of what
the skill is. Done and failed states show a ✓ or ✗ and clear themselves after 30 / 60
seconds.

Your existing status line is preserved and rendered first, and its output is cached for 5
seconds so that the 1-second refresh driving the animation does not re-run `git` every
second.

## What the ledger records

`ledger.jsonl` is built to answer seven questions — the five `skillforge --help` names about
a forge, plus the two the cheap tiers and the round cap added — and to say so when it cannot:

|Question|Row|
|-|-|
|What triggered the build|`start` and `origin`, carrying `--trigger` verbatim plus its kind|
|What was built|`origin`: one row per skill, with its directory and whether we ship it|
|Was it put on the problem that caused it|`apply`: `used`, `declined` or `failed`, with the verbatim evidence, written at step 6 as the forge closes|
|Used since|`use`: one row per invocation, written live by the `Skill` hook|
|Did it work|`verdict`: `WORKED`, `NO-OP`, `MISFIRED` or `UNKNOWN`, with the quote behind it, written at step 6 after the apply|
|What was written down instead of forged|`note`: one row per `skillnote` entry, with its scope, its target file and its id. A second `add` of the same text writes no row|
|What an extra red-team round cost|`escalate`: one row per round bought past a forge's budget, carrying the blocking counts that bought it and the round budget before and after|

`note`, `apply` and `escalate` are invisible to every reader written before them: each reader
picks its events by name, and no selector lists any of the three.

A single `horizon` row records where the record begins, because a ledger holding nothing
before Tuesday says nothing whatever about Monday. A row reconstructed after the fact
carries `backfilled:true`, `confidence:"reconstructed"` and a `source` naming the evidence
it was read from, and stays distinguishable from a live row forever.
