# 🔁 claude-skill-compounder

**Make Claude Code get permanently better at the things you do repeatedly.**

![A skill being forged: the builder/red-team loop, with live progress in the status line](docs/media/forge.gif)


Knowledge that costs a session real effort to acquire dies with that session. You and
Claude work out a debugging sequence, a deploy-and-verify loop, or a non-obvious API
dance; the context window closes; next week a fresh session makes the same mistakes in the
same order.

`claude-skill-compounder` closes that loop by installing a skill, two hooks, and a live
status-line animation. All three serve one principle:

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

This project addresses the first with hooks that keep asking the question, and the second with an
adversarial forging protocol: a **builder** agent writes the skill, and a **separate,
cold** red-team agent tries to execute it with no context and reports where it breaks.
They loop until the red-team report comes back clean.

---

## What gets installed

|Piece|What it does|
|-|-|
|`skills/skill-compounder/SKILL.md`|The doctrine: when to forge, how to forge, how to fix or retire a bad skill|
|`hooks/compound-improvement.sh`|Two throttled reminders: "does a skill already exist?" and "is this worth crystallizing?"|
|`bin/skillforge`|Tiny CLI the session drives to report forging progress|
|`statusline/`|Renders the live forge animation, wrapping any status line you already have|

All of the changes are additive, so hooks installed by other tools are left alone. Your
current status line is preserved and restored on uninstall, and `settings.json` is backed
up before every change.

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

Requires `python3` (installer only), `jq` (hooks and status line), and `~/.local/bin` on
your `PATH` for the `skillforge` CLI.

Hooks and skills are picked up **without restarting Claude Code**, though `/hooks` forces
a config reload if you want to be certain.

---

## The three habits

### 1. Before implementing, reuse before you build

At the start of a substantive turn, a `UserPromptSubmit` hook reminds the session to check
whether a skill already covers the task, before writing a plan or any code. Throttling
holds it to one reminder per 20 minutes, and it fires only for prompts of 60+ characters,
so `yes` and `continue` never trigger it.

### 2. During work, notice what is worth keeping

Every 12 file edits, a `PostToolUse` hook asks whether a given procedure clears the bar.
**Both** conditions must hold:

- **Costly**, meaning >15 minutes of trial-and-error, a non-obvious ordering constraint,
  or an error a fresh session would predictably repeat, **and**
- **Recurring**, meaning it has already happened twice, or it is a standing part of the
  workflow.

One without the other gets a note, not a skill. Forging costs several subagent rounds.

When both hold, the session runs the **forging protocol**:

```
skillforge start <name> <total-steps> "<one-line summary>"
  │
  ├─ builder agent      → writes SKILL.md (given the transcript, including dead ends)
  ├─ red-team agent     → FRESH context, tries to execute it cold, reports failures
  ├─ loop               → findings back to the builder; a NEW red-teamer each round
  └─ cap at 3 rounds    → narrow the scope until clean, or abandon it honestly
  │
skillforge done "<outcome>"
```

The red-teamer must never be a fork of the orchestrating session. A forked reviewer
already knows what the skill was *meant* to say, so it cannot detect the ambiguity that
will bite a cold session six weeks later. Its checklist: cold-start executability, trigger
precision (3 prompts that should fire, 3 that should not), every asserted command actually
run, unhappy paths, overlap with existing skills, and scope creep.

### 3. When a skill misfires: fix, document, or retire

Never silently work around a bad skill, because the workaround costs the same time again
in every future session. Escalate instead: fix the wording, and if the procedure itself is
wrong, fix that and then re-run the full red-team loop. Retire it only when neither works.

Retirement requires **independent concurrence**. Ask a second fresh agent the *neutral*
question, *"should this be kept, fixed, or retired?"* Never "confirm this deletion", which
is a leading prompt any agent will (obligingly) rubber-stamp. Retiring moves the skill to
`~/.claude/skills-archive/` with a `WHY-ARCHIVED.md`. Nothing is ever `rm -rf`'d.

---

## The animation

While a skill is being forged, your status line shows live progress:

```
my-project git:(main)  ⣻ forge parallel-agents-one-codebase ▕██████······▏ 4/8  50% · red-team round 1
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
skillforge done "clean"
skillforge clear     # escape hatch if a forge is ever left open
```

---

## Tuning

Noisy reminders are a tuning problem. All five are environment variables, but they are not
all read by the same component, so they do not all go in the same place in
`~/.claude/settings.json`:

|Variable|Default|Set it in|Meaning|
|-|-|-|-|
|`CI_EDIT_EVERY`|`12`|the hook entries|Edits between "is this worth crystallizing?" checkpoints|
|`CI_PROMPT_COOLDOWN`|`1200`|the hook entries|Seconds between "does a skill exist?" reminders|
|`CI_PROMPT_MIN_CHARS`|`60`|the hook entries|Shorter prompts never trigger a reminder|
|`STATUSLINE_BASE_TTL`|`5`|the `statusLine` entry|Seconds your base status line is cached|
|`SKILL_COMPOUNDER_STATE`|`~/.claude/skill-compounder`|the top-level `env` block|Where runtime state lives|

Only the three `CI_*` variables are read by the hook. `STATUSLINE_BASE_TTL` is read by
`statusline/statusline.sh`, so setting it on a hook entry does nothing. `SKILL_COMPOUNDER_STATE`
is read by all four components, so it belongs in the session-wide `env` block or the hooks and
the status line will disagree about where state lives.

The defaults are first guesses; nobody measured them. If a reminder fires often enough
that you learn to read past it, raise `CI_EDIT_EVERY` and `CI_PROMPT_COOLDOWN`, because by
that point it has stopped doing anything for you and you will not notice that it has.

---

## Uninstall

```bash
./uninstall.sh
# or:  curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/uninstall.sh | bash
```

Removes our hooks, leaving other tools' hooks alone, then restores your original status
line and removes the symlinks. Runtime state is left intact; delete it with
`rm -rf ~/.claude/skill-compounder`.

---

## Development

```bash
./run_tests.sh
```

45 tests, no mocks: real temporary Claude directories, real `settings.json` files, real
subprocess invocations of the shell scripts. See [docs/DESIGN.md](docs/DESIGN.md) for the
verified platform behavior the implementation depends on: mid-session hot-reloading, the
two different session ids, and so on.

The animation at the top replays a real forge of `parallel-agents-one-codebase`, which
took three red-team rounds, and the findings it shows are the ones the cold agents
actually returned. The session chrome around it is redrawn for the recording and the
subagents are not re-run, but the progress bar is the real status line driven by the real
state file. Regenerate it with [`vhs`](https://github.com/charmbracelet/vhs):

```bash
brew install vhs
./dev/generate_media.sh      # runs dev/forge_demo.sh under dev/forge.tape
```

---

## License

MIT. See [LICENSE](LICENSE).
