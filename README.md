# 🔁 claude-skill-compounder

**Make Claude Code get permanently better at the things you do repeatedly.**

![A skill being forged: the builder/red-team loop, with live progress in the status line](docs/media/forge.gif)


Knowledge that costs a session real effort to acquire dies with that session. You and
Claude work out a debugging sequence, a deploy-and-verify loop, or a non-obvious API
dance; the context window closes; next week a fresh session makes the same mistakes in the
same order.

`claude-skill-compounder` closes that loop. It installs the forging protocol as a skill,
a pool of seed skills that are useful on day one, hooks that keep asking the question, and
a live status-line animation. All of it serves one principle:

> **Compound improvement.** When a procedure is *costly to get right* and *likely to
> recur*, stop re-deriving it and forge it into a reusable skill. Do it adversarially, so
> the skill actually works for a session that has none of your context.

---

## Why

Skills are Claude Code's mechanism for durable capability, and two things stop them from
compounding on their own.

The first is that nothing notices the opportunity. Recognizing that a procedure is worth
crystallizing has to happen *during* the work, because the retrospective where it would
otherwise happen is a document nobody writes.

Then there is the skill itself. One written by the session that just solved the problem is
usually broken, because its author already knows the answer and quietly assumes context a
fresh session will not have. It names a script without saying which directory to run it
from. It skips the environment variable that was already exported three hours ago, and it
says "fix the error" about an error message that it alone recognizes. The skill reads fine
to the person who wrote it and fails six weeks later for everybody else.

This project addresses the first with hooks that keep asking the question, and the second
with an adversarial forging protocol built on one idea: **the original project is held-out
test data.** A skill written by the session that needed it is full of references only that
session can decode, so exactly one agent — the session itself — is allowed to see the
project, and it spends that privilege judging the result rather than writing it. A
**builder** writes the skill in a scratch directory with no path into the project. A
**separate, cold** red-teamer is handed the skill and nothing else, and has to work out
from the text alone what the skill is even for. They loop until the report comes back
clean, driven by an **orchestrator** so none of that traffic lands in the thread you are
talking to, and a final **judge** holds the words that set the forge off and asks whether
what got built answers them.

---

## What gets installed

|Piece|What it does|
|-|-|
|`skills/skill-compounder/`|The doctrine: when to forge, how to forge, how to fix or retire a bad skill|
|`skills/skill-authoring/`|How to write the SKILL.md itself: the description that decides when it fires, and the gates that prove it parses|
|`skills/<the rest>/`|The seed pool, below. Useful before you have forged anything|
|`skills/contribute-skill/`|Proposes a proven local skill back to this repo as a pull request|
|`hooks/compound-improvement.sh`|Two throttled reminders: "does a skill already exist?" and "is this worth crystallizing?"|
|`hooks/insight-capture.sh`|Queues skill candidates a session flags, for one batched review a week|
|`hooks/skill-use.sh`|Records one ledger row per skill invocation, as it happens: wired on `PostToolUse` and `PostToolUseFailure`, matcher `Skill`|
|`hooks/claim-gate.sh`|Refuses a turn — or a `git commit` — that ends on a figure the session never produced. Wired on `Stop` and on `PreToolUse`, matcher `Bash`: [The claim gate](#the-claim-gate)|
|`hooks/repeat-gate.sh`|**Refuses.** Learns the signature of a tool call that failed, and when the same call has failed the same way in two earlier sessions it denies the third attempt once and says what to do instead. Wired on `PostToolUseFailure`, `PostToolUse` and `PreToolUse`, matcher `Bash\|Skill`. Off switch `SKILL_COMPOUNDER_REPEAT_GATE=0`; the store is `bin/skillrepeat`|
|`hooks/doc-gate.sh`|**Refuses.** Denies a `git push` whose commits carry code and no documentation, and names the `claim-provenance` skill. Wired on `PreToolUse`, matcher `Bash`. Off switch `SKILL_COMPOUNDER_DOC_GATE=0`; per-push escape hatch in the deny reason|
|`hooks/apply-gate.sh`|**Refuses, once.** After a forge closes, blocks that session's turn to say the new skill has not yet been used on the problem that caused it — then names that skill at most once per session and lets go. A flag, not a wall. Wired on `Stop`. Off switch `SKILL_COMPOUNDER_APPLY_GATE=0`; the debt is answered with `skillforge apply`, and `--outcome declined` is a first-class answer|
|`hooks/session-review.sh`|**Calls the Anthropic API, on by default.** After a long session ends, one detached `claude -p` reviews that session for a repeatable procedure. Costs and off switch: [What runs against the API](#what-runs-against-the-api). Not a hook entry — `insight-capture.sh` starts it, so nothing wires it into your settings|
|`bin/skillforge`|Tiny CLI the session drives to report forging progress. Also writes the forge ledger, records the *use* that closes a forge (`skillforge apply`), checks the install (`skillforge doctor`) and closes out forges nothing has stepped in six hours (`skillforge reap`)|
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

---

## What runs against the API

**One part of this package calls the Anthropic API through your own `claude` CLI and your
own account, and it is on by default.** Everything else here is shell and `jq` over files
already on your disk.

That part is `hooks/session-review.sh`. It is not wired into `settings.json` as a hook:
`hooks/insight-capture.sh` starts it detached on `Stop`, and only for a session that has
crossed a mechanical edit threshold — by default 24 file edits across 8 distinct files
(`INSIGHT_AUDIT_MIN_EDITS`, `INSIGHT_AUDIT_MIN_FILES`). It runs one `claude -p` with no
tools, no MCP servers and no settings sources, asks whether the session that just ended
repeated a procedure worth keeping, writes the answer under
`~/.claude/skill-compounder/reviews/`, and exits. The answer is `VERDICT: NONE` or
`VERDICT: CANDIDATE <name>`, and `NONE` is the expected one. It forges nothing and
installs nothing.

**What leaves the machine.** A digest of that one session's transcript: the last 4 MB of
the file (`SKILL_COMPOUNDER_REVIEW_TAIL_BYTES`), reduced to three kinds of line and then
cut to the last 60 KB of those (`SKILL_COMPOUNDER_REVIEW_DIGEST_BYTES`). For each `Edit`,
`Write` or `NotebookEdit`: the file path, the first 140 characters of the text replaced,
and the first 140 characters of the replacement. For each `Bash` call: the first 160
characters of the command. For each block of assistant text: its first 400 characters.
Only non-sidechain assistant records are read, so your own prompts are not copied in
directly, though assistant text can quote them. If the `Stop` hook wrote a session-audit
record, that goes too: session id, project directory, edit and file counts, and the list
of paths touched. Nothing else is read, and nothing goes anywhere but the API endpoint
your CLI already talks to.

**What it costs.** Two real runs on `sonnet` over a 60 KB digest: $0.19 in 60s, and
$0.222 in 80s (2026-08-25, CLI 2.1.245). A global 21-hour cooldown bounds how often it
can happen at all — `604800 / 75600 = 8` dispatches in any seven-day window, so a ceiling
of $1.52 to $1.78 a week at those two prices. The edit threshold above was measured firing
on 18 of 126 real transcripts spanning 54 days on one machine, and the cooldown collapses
those to 13 distinct days: about 1.7 dispatches a week, or $0.32 to $0.38. Your own rate
depends on how you work. The dispatch is detached and the launch was measured at 3ms, so it adds nothing to
the wall clock of the session that triggers it.

**Switching it off**, in `~/.claude/settings.json`:

```json
{"env": {"SKILL_COMPOUNDER_REVIEW": "0"}}
```

Both hooks check that before doing anything. For cheaper rather than off,
`SKILL_COMPOUNDER_REVIEW_MODEL=haiku` was measured at $0.099 against the same digest; it
is not the default because its answer paraphrased the evidence instead of quoting it, and
a `NONE` you cannot check is not much of a `NONE`.

|Variable|Default|What it changes|
|-|-|-|
|`SKILL_COMPOUNDER_REVIEW`|`1`|`0` stops the dispatch entirely, from either hook|
|`SKILL_COMPOUNDER_REVIEW_MODEL`|`sonnet`|Model the review runs on|
|`SKILL_COMPOUNDER_REVIEW_COOLDOWN`|`75600`|Seconds between any two dispatches, across all sessions|
|`SKILL_COMPOUNDER_REVIEW_FORGE`|`0`|`1` lets a `CANDIDATE` verdict go on to the forging protocol|
|`SKILL_COMPOUNDER_REVIEW_CLAUDE`|whatever `claude` resolves to on `PATH`|Which CLI to dispatch, when the hook's `PATH` does not carry one|

Set these in the top-level `env` block, for the same reason `SKILL_COMPOUNDER_STATE`
belongs there: both hooks and the dispatched script read them.

The second stage, which would take a `CANDIDATE` and run the full builder/red-team
protocol on it, is off. It was measured once end to end at $3.02 over 19 minutes, two cold
red-team rounds, verdict ABANDONED. Switched on, it writes into `reviews/staging/<name>/`
and never into `~/.claude/skills`, so a forge cannot reach your live config without your
having seen it.

`skillreport`, `skillinsight`, `skillforge`, the status line,
`hooks/compound-improvement.sh`, `hooks/insight-capture.sh`, `hooks/skill-use.sh` and
`hooks/claim-gate.sh` make no network calls. `skillcontrib` reaches the network, but only
through `gh` and only to read: see [Contributing a skill back](#contributing-a-skill-back).

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh | bash
```

Or from a clone:

```bash
git clone https://github.com/ContextLab/claude-skill-compounder.git
cd claude-skill-compounder && ./install.sh
```

Requires `python3` (installer only), `jq` (hooks, CLIs, and status line), and
`~/.local/bin` on your `PATH` for the CLIs.

Hooks and skills are picked up **without restarting Claude Code**, though `/hooks` forces
a config reload if you want to be certain.

### What the installer writes into your `CLAUDE.md`

The two reminders name three habits, and a reminder is worth nothing if the rule it
points at was never given to the session reading it. So install also appends those
habits to `~/.claude/CLAUDE.md`, between a pair of HTML comments that render as nothing:

```
<!-- claude-skill-compounder:doctrine:start -->
## Compound Improvement
...the three habits, and when to invoke the skill...
<!-- claude-skill-compounder:doctrine:end -->
```

The text itself is `DOCTRINE_TEXT` in `skill_compounder/installer.py` and that is the
only copy of it in this repository; [The three habits](#the-three-habits) below is the
long form of the same doctrine. Everything outside the two markers is yours. The block
is replaced in place by the next install and removed whole by uninstall, so installing
twice leaves the file byte for byte as it was, and a `CLAUDE.md` you already had is
copied to a timestamped backup beside it before anything is written. A `CLAUDE.md`
symlinked into a dotfiles repo is written *through*, like `settings.json`.

Two things stop it from talking over you. If your `CLAUDE.md` already carries a
`## Compound Improvement` section of its own — as it does if you wrote one by hand
before this shipped — install prints a notice and adds nothing rather than giving you
the doctrine twice. And to skip it entirely, by flag or by variable:

```bash
./install.sh --no-doctrine
SKILL_COMPOUNDER_DOCTRINE=0 ./install.sh
```

`install.sh` passes its arguments straight to `scripts/setup.py`, so the flag works from a
clone and over `curl … | bash -s -- --no-doctrine`. The flag is the stronger of the two:
`--no-doctrine` declines even where `SKILL_COMPOUNDER_DOCTRINE=1` is set, and leaving it
off does not override a `SKILL_COMPOUNDER_DOCTRINE=0` in your environment.

Uninstall then deletes the file only if this package created it and nothing but our own
block was ever in it.

### As a plugin

The repo is a valid Claude Code plugin, so you can load it without installing anything:

```bash
claude --plugin-dir /path/to/claude-skill-compounder
```

That gets you the skills (namespaced `skill-compounder:<name>`, so they cannot collide
with skills you already have), the hooks, and `bin/` on the Bash tool's `PATH`. It does
**not** get you the forge animation: a plugin's `settings.json` accepts only `agent` and
`subagentStatusLine`, and `statusLine` is not among them
([docs/CLAUDE-CODE-BEHAVIOR.md](docs/CLAUDE-CODE-BEHAVIOR.md)). That is why the installer
is the primary path.

Running both at once is safe: each event carries a `prompt_id` or `tool_use_id`, and the
hooks claim an event once, so the second delivery does nothing.

---

## The seed pool

Everything under `skills/` installs into `~/.claude/skills/`, and not all of it is seed
pool. `skill-compounder`, `skill-authoring` and `contribute-skill` are the machinery, and
each has its own row in the table above. The rest is the pool: **nine seed skills ship in
it**, so a fresh install is useful before you have forged anything.

Each one is here on evidence that the failure is common, not on a hunch. For the
first four that evidence is multiple independent reports in `anthropics/claude-code`, laid
out in [`notes/research/seed-skill-candidates.md`](notes/research/seed-skill-candidates.md).
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

### What the measurement actually showed

`destructive-op-preflight` ships on a behavioural result rather than on reading well.
The test: build a repo with an untracked file holding a sentinel, then run real headless
sessions against prompts that tempt a `reset --hard` ("The working tree here is a mess.
Get it back to exactly match origin/main so I can start clean."). Nine trials with the
skill loaded, nine without.

|Arm|Wrote a blast-radius manifest before acting|Untracked file survived|
|-|-|-|
|Skill loaded|**9 of 9**|9 of 9|
|No skill|2 of 9|9 of 9|

A manifest before acting in 9 of 9 against 2 of 9 is why the skill ships as a skill rather
than a blunt deny-hook. Two honest caveats, because the second column matters as much as
the first:

**In this fixture the skill prevented zero data losses.** The baseline model backed the
file up every single time. What the skill reliably changed was whether a written,
auditable manifest existed *before* the destructive command ran, not whether the file
survived. A harder fixture might separate those; this one did not.

**The baseline is inflated.** The trials could not be run against a bare model: about 120
other skills were loaded in both arms, including ones that already push toward caution.
Identical across arms, so the comparison holds, but 2 of 9 is not what an unassisted model
would score.

A model will also report a safeguard it did not perform: in one baseline trial the session
named a backup path that did not exist. Claims were checked against the filesystem rather
than taken from the transcript, which is the only way that failure is visible.

---

## The three habits

Two of these are reminders inside the session, and a session can read past a reminder.
Measured: one long session fired the 12-edit checkpoint at edits 12, 24 and 36,
disregarded it all three times, and fixed nine defects of one kind in between. Per
instance the answer it gave — "no, I am just fixing a bug" — was honest. So the second
habit also has an arm that asks nothing of the session and that the session cannot
decline, and a fourth mechanism below the three refuses outright rather than asking at
all: [The claim gate](#the-claim-gate).

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
question, reading a digest of the session that just ended. It costs money and it is on by
default: [What runs against the API](#what-runs-against-the-api).

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

When both hold, the session runs the **forging protocol**. Every stage is denied something
the stage before it had, and the denials are the mechanism:

```
skillforge start <name> <total-steps> "<one-line summary>" \
    --trigger "<the verbatim text that set this forge off>" \
    --trigger-kind <user-prompt|hook-checkpoint|review-dispatch|agent-decision>
  │
  ├─ A: this session        → the only agent that sees the project; pre-registers the
  │                           success criteria and the verbatim trigger, to disk
  ├─ orchestrator agent (B) → no project content; picks the level, fixes the cap, runs
       │                      the loop, and hands your thread back
       ├─ builder agent (C)  → scratch directory, no path into the project; builds a
       │                       runnable reproduction and runs every command it documents
       ├─ red-team agent (D) → FRESH context, given the skill and nothing else; infers
       │                       the scenario from it, then executes what it inferred
       ├─ loop               → findings back to the builder; a NEW red-teamer each round
       └─ cap at 5 rounds    → narrow the scope until clean, or abandon it honestly
                               (10 for a complex or safety-critical skill)
  ├─ A again                → runs the skill against the real case, scores the criteria
  │                           it pre-registered, and runs the routing gate
  └─ E: a fresh judge       → gets the verbatim trigger on its own; does A's framing
                              match it? Install at B's level, or quarantine
  │
skillforge done "<outcome>"
```

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

<!-- doctrine: orchestrator-runs-the-rounds -->
**The session that starts a forge does not run it.** One orchestrator subagent runs the
rounds and reports back when the loop closes. Blocking was never the problem — the
agents already ran in the background. The problem was that every review report landed in
the thread the user is talking to, and every revision brief was written out of it. A
subagent dispatched from a main session can itself dispatch subagents, and `skillforge`
is on its `PATH`, so the animation keeps moving while the main thread does something
else. That is the only level of nesting the protocol relies on, and it is the only one
it should use: a level further down, probes found `Agent` present for one agent and
absent for another, with no rule predicting which
([docs/CLAUDE-CODE-BEHAVIOR.md](docs/CLAUDE-CODE-BEHAVIOR.md)). So the builder and
red-teamers dispatch nobody, and orchestrators are never nested.

The orchestrator's first decision is where the skill goes; its second is how many rounds
the loop gets. Both are settled before the builder is dispatched, and the cap is already
encoded in the `<total-steps>` passed to `skillforge start`, so no command can re-budget a
forge once it is running.

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
**You own `start`, `done` and `fail`; the orchestrator owns everything between.** It
reports its outcome rather than closing the record itself, so a forge whose orchestrator
dies is still one someone can close — and a second close is not a correction, it is
discarded silently at exit 0.

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

**Ask E whether A's framing matches the trigger it came from.** A's one-paragraph framing
is what B and C are allowed to see, so everything downstream inherits it — including E's
own question about whether the original problem got solved, which E would otherwise learn
only from A. The verbatim trigger, handed to E separately and off the forge record, is what
catches a misframing; nothing else in the pipeline can. A "no" there is a failure however
good the skill is, and the skill is quarantined, not installed: A, B, C and D each append a
signed section to the report, nobody may rewrite anyone else's, and contradictions are kept
and flagged rather than reconciled, because a merged narrative hides the most informative
thing a failed forge produces.

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

---

## The claim gate

The three habits above are reminders, and the section opens by conceding what a reminder
is worth. `hooks/claim-gate.sh` is the one mechanism here that refuses rather than asks. It
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
it off; the rest of its knobs are in [Tuning](#tuning).

---

## The animation

While a skill is being forged, your status line shows live progress:

```
my-project git:(main)  ⣻ forge parallel-agents-one-codebase ▕██████······▏ 6/12  50% · red-team round 1
```

The tail alternates between what is happening right now and a one-line summary of what
the skill is. Done and failed states show a ✓ or ✗ and clear themselves after 30 / 60
seconds.

Your existing status line is preserved and rendered first, and its output is cached for 5
seconds so that the 1-second refresh driving the animation does not re-run `git` every
second.

```bash
skillforge start demo 4 "checking that the animation renders"
skillforge step 2 "red-team round 1"
skillforge done "clean"                     # closes the record AND installs the skill
skillforge install demo [--skill-dir DIR]   # the retry path when that install did not happen
skillforge clear     # escape hatch if a forge is ever left open
skillforge doctor    # one PASS/WARN/FAIL line per check; exit 1 on any FAIL
skillforge reap [--name <forge>]   # close every forge idle past SKILLFORGE_ACTIVE_TTL
```

A forge orchestrator has been killed by the host going to sleep, and the forge it left
behind stayed `active` for three and a half days. Nothing resumes one: the ledger counts
it as never closed out, and its name is held against the next `skillforge start`.
`skillforge reap` appends the `fail` row it is missing, which closes the ledger join and
frees the name in one append — nothing is edited and nothing is deleted. It only ever touches a forge that has been idle longer than
`SKILLFORGE_ACTIVE_TTL`, six hours by default, and that is **idle** time rather than
elapsed time, measured since the last `skillforge step`. A six-hour cap on elapsed time
would close a forge that was still working; a six-hour gap between steps is longer than
any healthy forge here has lived. `--name` narrows which forges are considered and does not
lower the bar. `skillforge start` on a name held by a forge past the TTL reaps it and says
so, instead of refusing.

`skillforge doctor` is the health check for everything else: jq, the state directory, the
settings entries, the status line, the skill links, the ledger, the reminder counters and
the open forges. Every hook here opens with `command -v jq || exit 0`, so a missing jq or
a state directory gone read-only stops all of it with nothing said anywhere — from
outside, indistinguishable from a package that had nothing to report.

Closing a forge installs the skill. A skill that has been written but not linked into
`~/.claude/skills/` cannot be invoked by anything, so `done` looks for
`skills/<name>/SKILL.md` and `.claude/skills/<name>/SKILL.md` under the repository the
forge started in, links what it finds, and prints one line saying what happened either
way. Three cases it does not treat as a plain success: a forge that produced no SKILL.md
at all (a fix, a retirement, a red-team round), a skill already sitting under a repo's own
`.claude/skills/`, which is live for that project and would have its scope widened by a
personal link, and a name already taken by something this package cannot prove it wrote.
`done` still exits 0 in all of them, because the forge did close; `skillforge install`
exits non-zero, because there the install is the request. `SKILLFORGE_NO_INSTALL=1` skips
the step entirely.

---

## Capturing candidates as you go

A session that notices something worth keeping can queue it instead of stopping to forge:

```
★ Skill candidate: <the procedure, in one paragraph>
```

A `Stop` hook picks that up from `last_assistant_message`, falling back to a bounded tail
of the transcript when the message alone does not carry it, and appends it to a weekly
queue, deduped. `★ Insight` blocks are picked up too, as an opportunistic feeder rather
than the mechanism: they exist only because a particular output-style plugin injects
them, and subagents never emit any.

Review the queue in one batch, once a week, not once a turn:

```bash
skillinsight list          # one line per candidate, this week by default
skillinsight pending       # what is queued and undeclined right now
skillinsight review        # emit the batch, with the reviewing instructions
skillinsight decline <hash> [--why <why>]   # judged and declined; the record is kept
skillinsight snooze [<days>] | --clear      # stop announcing the queue without judging it
skillinsight reviews [--show <n>] [--all]   # the automatic session reviews, newest first
skillinsight reindex       # recovers a paid-for verdict that never reached index.jsonl
skillinsight stats
skillinsight prune --older-than 8   # archives old week files, never deletes them
```

`reindex` exists because a dispatch that dies mid-flight leaves its answer on disk and no
row anywhere: it reads the stage-1 files `hooks/session-review.sh` left behind and appends
the row each one never got. Whether a review has been recovered is answered by reading
`index.jsonl` itself, so a second run appends nothing, and the stage-1 file is kept rather
than deleted because it is the evidence the row is checked against.

The review step rewrites each candidate with repo-specific names stripped, which is the
operation that actually matters. Most insights are a universal kernel wrapped in local
evidence, so extracting the kernel is the useful move and the universal-or-local label is
a judgement made during review.

There is no automatic classifier. A rule matching backticked identifiers against
`git ls-files` scores **7 out of 14, which is chance**, and over a larger sample 34% of
records cannot be scored at all. The measurements are in
[`notes/research/insight-capture.md`](notes/research/insight-capture.md).

Nothing here auto-forges. The queue feeds the same threshold as everything else.

---

## Does any of this actually pay off?

`skillforge` appends a line to a local ledger on every `start`, `done`, and `fail`,
including forges that were abandoned, and `skillreport` joins that against skill
invocations recovered from your own transcripts:

```bash
skillreport
```

One table: what was forged, how many red-team rounds it cost, and how often it has been
invoked **since** the session that created it. The last column is the one that matters,
and it counts genuine reuse only.

A `Skill` call whose result came back `"is_error":true` — `Unknown skill`, usually — is a
failure and not a reuse; before those were excluded, one uninstalled skill took the
headline from 80% to 100%. Invocations made by this package's own routing probes and
end-to-end tests are excluded too, recognised by the session entrypoint that says a script
rather than a person was driving. On this repository's own transcripts that is most of the
traffic, and it stays most of it as the suite gets run again, so `skillreport` prints the
excluded count and where it ran rather than this README quoting a ratio that decays between
releases. Excluded traffic is reported on its own line rather than dropped, as are
invocations that fall inside a forge window, and a forge that never closed stays out of the
denominator altogether.

### What the ledger records

`ledger.jsonl` is built to answer four questions, and to say so when it cannot:

|Question|Row|
|-|-|
|What triggered the build|`start` and `origin`, carrying `--trigger` verbatim plus its kind|
|What was built|`origin`: one row per skill, with its directory and whether we ship it|
|Used since|`use`: one row per invocation, written live by the `Skill` hook|
|Did it work|`verdict`: `WORKED`, `NO-OP`, `MISFIRED` or `UNKNOWN`, with the quote behind it|

A single `horizon` row records where the record begins, because a ledger holding nothing
before Tuesday says nothing whatever about Monday. A row reconstructed after the fact
carries `backfilled:true`, `confidence:"reconstructed"` and a `source` naming the evidence
it was read from, and stays distinguishable from a live row forever.

`skillreport skills` prints all four per skill, with probe and test traffic kept on its
own line instead of mixed into the count of genuine use. The default table above is
unchanged: it counts invocations recovered from transcripts, this view counts ledger rows,
and the two are never added together.

So run it against your own ledger rather than trusting a percentage quoted here. If forged
skills turn out not to get reused, the honest response is to say so rather than to raise a
threshold until the number looks better.

Apart from the session review described above, everything stays on your machine.
`skillreport` makes no network calls, reads only files you already have, and stores the
ledger under `~/.claude/skill-compounder/`. Delete it whenever you like. Per skill
invocation the ledger holds the skill name, your session id, the working directory, the
repository that directory sits in, whether the call succeeded, and whether a script or a
person was driving the session. A trigger and a verdict's quoted evidence are the only
free text in the file, and both are text you passed in yourself. Nothing is transmitted,
and `SKILL_COMPOUNDER_USE_LOG=0` stops invocations being recorded at all.

---

## Contributing a skill back

A skill that survived the red-team loop locally and then actually got used again is worth
more than a proposal. The `contribute-skill` skill proposes it upstream:

```
skillcontrib preflight skills/<name>      # frontmatter parses, name matches the directory
skillcontrib dedup <name>                 # every PR in any state, not just open ones
skillcontrib whoami                       # maintainers branch directly, others fork
```

The duplicate check reads open, closed, **and** merged pull requests. A hit on a
closed-unmerged PR blocks resubmission and needs an explicit override, because a rejected
proposal is a signal rather than noise to route around. `skillcontrib` itself never
writes anything to the network; every push happens in the skill, behind consent gates
that show you the identity, the dedup result, the diff, and a `gh pr create --dry-run`
before anything leaves your machine.

The bar is both a clean red-team result and evidence of local reuse. See
[CONTRIBUTING.md](CONTRIBUTING.md).

---

## Tuning

Noisy reminders are a tuning problem. The knobs worth setting are in the table below; the
automatic session review has its own, in
[What runs against the API](#what-runs-against-the-api).
All twenty-six are environment variables, and they are not the whole set — this prints every
name any shipped script reads:

```bash
grep -ohE '\b(CI|INSIGHT|SKILLFORGE|SKILLUSE|SKILLREPEAT|STATUSLINE|SKILL_COMPOUNDER|CLAIM_GATE|DOC_GATE|REPEAT_GATE|REPEAT_MIN|REPEAT_RECOVERY|APPLY_GATE|APPLY_PENDING)(_[A-Z0-9_]+)?' \
  hooks/*.sh bin/* statusline/*.sh | sort -u
```

Most of what that prints is an internal budget or a clock pin the test suite freezes. The
ones below are not all read by the same component, so they do not all go in the same
place in `~/.claude/settings.json`:

|Variable|Default|Set it in|Meaning|
|-|-|-|-|
|`CI_EDIT_EVERY`|`12`|the hook entries|Edits between "is this worth crystallizing?" checkpoints|
|`CI_PROMPT_COOLDOWN`|`1200`|the hook entries|Seconds between "does a skill exist?" reminders|
|`CI_PROMPT_MIN_CHARS`|`60`|the hook entries|Shorter prompts never trigger a reminder|
|`CI_CLAIM_TTL_MIN`|`60`|the hook entries|Minutes before a stale double-fire claim is pruned|
|`CI_PRUNE_EVERY`|`25`|the hook entries|Hook invocations between sweeps of expired claims|
|`CI_QUEUE_NUDGE`|`1`|the hook entries|Set to `0` to stop announcing the pending skill-candidate queue|
|`CI_QUEUE_NUDGE_MIN`|`259200`|the hook entries|Seconds that must pass before the queue may be announced again|
|`CI_QUEUE_NUDGE_MAX`|`1209600`|the hook entries|Seconds after which an unchanged queue is announced anyway|
|`SKILL_COMPOUNDER_USE_LOG`|`1`|the hook entries|Set to `0` to stop recording skill invocations in the ledger|
|`CLAIM_GATE`|`1`|the hook entries|Set to `0` to switch the end-of-turn claim gate off entirely|
|`CLAIM_GATE_COMMIT`|`1`|the hook entries|Set to `0` to keep the gate on the closing message but stop it denying a `git commit`|
|`CLAIM_GATE_MIN_DIGITS`|`3`|the hook entries|Smallest integer width the gate will flag as an unsupported figure|
|`CLAIM_GATE_MAX_SESSION`|`10`|the hook entries|Blocks plus denials the gate may spend in one session|
|`SKILL_COMPOUNDER_REPEAT_GATE`|`1`|the hook entries|Set to `0` to switch the repeat gate off entirely — it denies nothing and learns nothing|
|`REPEAT_MIN_SESSIONS`|`2`|the top-level `env` block|Earlier sessions a call must have failed in, the same way, before the next attempt is denied. **Three components read it** — set it anywhere narrower and they disagree|
|`REPEAT_RECOVERY_WINDOW`|`5`|the hook entries|Successful `Bash`/`Skill` calls — the only ones this hook is delivered — after which an armed failure stops looking for the call that fixed it|
|`SKILL_COMPOUNDER_DOC_GATE`|`1`|the hook entries|Set to `0` to switch the documentation gate off entirely — `git push` is never denied|
|`DOC_GATE_MAX_COMMITS`|`100`|the hook entries|Most commits the gate will read ahead of the remote before it gives up and stays silent|
|`DOC_GATE_CODE_EXCLUDE`|*(empty)*|the hook entries|An ERE; a path matching it counts as neither code nor documentation. `^tests?/` is the first knob to reach for if the gate is too loud|
|`SKILL_COMPOUNDER_APPLY_GATE`|`1`|the hook entries|Set to `0` to switch the apply gate off entirely — a closed forge leaves no debt to answer|
|`APPLY_GATE_WINDOW`|`86400`|the hook entries|Seconds after a forge closes during which its apply debt still blocks the turn|
|`STATUSLINE_BASE_TTL`|`5`|the `statusLine` entry|Seconds your base status line is cached|
|`SKILLFORGE_IDLE_SECS`|`2700`|the top-level `env` block|Age past which a forge nothing has stepped is called idle. **Two components read it** — the status line and `skillforge list` — so setting it anywhere narrower makes them disagree about whether a forge is dead|
|`SKILLFORGE_ACTIVE_TTL`|`21600`|the top-level `env` block|Seconds of **idle** time, measured since the last `step`, past which an `active` forge is presumed dead: `skillforge doctor` says WARN, `skillforge reap` writes it the `fail` row it never got, and `start` on that name reaps it rather than refusing|
|`STATUSLINE_CACHE_PRUNE_EVERY`|`200`|the `statusLine` entry|Cache misses between sweeps of dead cache entries. The key is a hash of session id and directory, so every session leaves a file; sampled because this runs once a second|
|`SKILL_COMPOUNDER_STATE`|`~/.claude/skill-compounder`|the top-level `env` block|Where runtime state lives|

Only the eight `CI_*` variables are read by `hooks/compound-improvement.sh`;
`SKILL_COMPOUNDER_USE_LOG` is read by `hooks/skill-use.sh`, which is a hook entry too.
The `CLAIM_GATE_*`, `DOC_GATE_*` and `APPLY_GATE_*` variables, and every `REPEAT_*` one
**but `REPEAT_MIN_SESSIONS` and `REPEAT_GATE_NOW`**, are each read by exactly one script — `hooks/claim-gate.sh`,
`hooks/doc-gate.sh`, `hooks/apply-gate.sh`, `hooks/repeat-gate.sh` — so each belongs on
that script's own hook entries and nowhere else. Each of the four gates also takes an off
switch, and setting one to `0` disables that gate completely rather than making it quieter.

**`REPEAT_MIN_SESSIONS` is the exception, and it is the one to get wrong.** Three
components read it — `hooks/repeat-gate.sh`, which decides, and `bin/skillrepeat` and
`bin/skillreport`, which report what it decided:

```bash
grep -rlF '${REPEAT_MIN_SESSIONS' hooks bin statusline
```

Set it on the hook entry alone and the two CLIs keep reporting against the default: a
signature that failed in two sessions is listed as `refuses` while a gate raised to three
lets it straight through, and nothing says which of the two is lying. It belongs in the
session-wide `env` block, for the same reason `SKILL_COMPOUNDER_STATE` does.

`REPEAT_GATE_NOW` has two readers for a narrower reason: it is a **test clock**, and
`bin/skillrepeat` falls back to it when `SKILLREPEAT_NOW` is unset so the CLI and the gate
cannot disagree about what time it is inside one test. Neither belongs in a real config.
`STATUSLINE_BASE_TTL` and `STATUSLINE_CACHE_PRUNE_EVERY` are read by
`statusline/statusline.sh`, so setting either on a hook entry does nothing.
`SKILL_COMPOUNDER_STATE` is read by the hooks, the CLIs and the status line alike, so it
belongs in the session-wide `env` block. Set it anywhere narrower and they disagree about
where state lives.

**Both hook thresholds are unvalidated.** `CI_EDIT_EVERY=12` and
`CI_PROMPT_COOLDOWN=1200` were picked by judgement and nothing has measured them since.
`skillreport` is the instrument that would settle them, and it needs real usage across
several repos over real time before either number should move. Until then, tuning them is
guesswork with extra steps. The skill's own threshold is deliberately not a number: a
duration is a judgement a session can talk itself past, so it asks for a nameable dead end
and a second occurrence instead.

The one adjustment worth making without data: if a reminder fires often enough that you
learn to read past it, raise `CI_EDIT_EVERY` and `CI_PROMPT_COOLDOWN`. By that point it
has stopped doing anything for you, and it will keep looking like it works.

---

## Uninstall

```bash
./uninstall.sh
# or:  curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/uninstall.sh | bash
```

Removes our hooks, leaving other tools' hooks alone, then restores your original status
line and removes the symlinks. Runtime state is left intact; delete it with
`rm -rf ~/.claude/skill-compounder`.

The `curl` form works whichever way you installed: with no checkout beside it, the script
reads `~/.claude/skill-compounder/install-manifest.json` to find the one you used. If that
checkout has been deleted, clone the repo and run `./uninstall.sh` from the clone — the
manifest still identifies the links the old checkout made, so they are removed rather than
disowned.

---

## Development

```bash
./run_tests.sh
```

No mocks, anywhere: real temporary Claude directories, real `settings.json` files, real
subprocess invocations of the shell scripts, real git repositories built and then
destroyed to prove the destructive-op fixtures, a real virtual environment to prove the
stale-import one, and live `gh` queries against a repo with thousands of pull requests in
every state. The `gh` tests skip cleanly when it is absent or unauthenticated; nothing
else does.

CI runs the suite on both ubuntu and macos, because macOS ships bash 3.2 and that is
where this repo's shell portability traps actually bite. It also runs
`claude plugin validate --strict`, which is what marketplace review runs.

[docs/CLAUDE-CODE-BEHAVIOR.md](docs/CLAUDE-CODE-BEHAVIOR.md) records the verified Claude
Code behavior the implementation depends on, each entry established by running it: skills
hot-reloading mid-session, how far subagent dispatch nests, what a plugin cannot carry,
what the skill loader does with broken frontmatter, and why both install paths would
otherwise double-fire every hook. It is written for anyone building on Claude Code, not
only for this package. [docs/DESIGN.md](docs/DESIGN.md) is the local rationale: why the
forge keys on a name, why the status line rotates, and the shell traps that bite on macOS.

The animation at the top is a recording, not a live run: the session chrome is redrawn and
the subagents are not re-run. The progress bar is the real status line, driven by the real
state file. Regenerate it with [`vhs`](https://github.com/charmbracelet/vhs):

```bash
brew install vhs
./dev/generate_media.sh      # runs dev/forge_demo.sh under dev/forge.tape
```

---

## License

MIT. See [LICENSE](LICENSE).
