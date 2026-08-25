# 🔁 claude-skill-compounder

**Make Claude Code get permanently better at the things you do repeatedly.**

![A skill being forged: the builder/red-team loop, with live progress in the status line](docs/media/forge.gif)


Every session, you and Claude solve some problem that took real effort to get right — a
debugging sequence, a deploy-and-verify loop, a non-obvious API dance. Then the session
ends and that knowledge evaporates. Next week a fresh session makes the same mistakes in
the same order.

`claude-skill-compounder` closes that loop. It installs a skill, two hooks, and a live
status-line animation that together implement one principle:

> **Compound improvement** — when a procedure is *costly to get right* and *likely to
> recur*, stop re-deriving it and forge it into a reusable skill. Do it adversarially, so
> the skill actually works for a session that has none of your context.

---

## Why

Skills are Claude Code's mechanism for durable capability. Two things stop them from
compounding on their own:

1. **Nothing notices the opportunity.** Recognizing "this is worth crystallizing" has to
   happen *during* the work, not in a retrospective that never gets written.
2. **A skill written by the session that just solved the problem is usually broken.** It
   is written by an author who already knows the answer, so it quietly assumes context a
   fresh session will not have. It looks fine, and then it fails six weeks later.

This project addresses (1) with hooks that keep asking the question, and (2) with an
adversarial forging protocol: a **builder** agent writes the skill, and a **separate,
cold** red-team agent tries to execute it with no context and reports where it breaks.
They loop until the red-team report comes back clean.

---

## What gets installed

|Piece|What it does|
|-|-|
|`skills/skill-compounder/SKILL.md`|The doctrine: when to forge, how to forge, how to fix or retire a bad skill|
|`hooks/compound-improvement.sh`|Two throttled reminders — "does a skill already exist?" and "is this worth crystallizing?"|
|`bin/skillforge`|Tiny CLI the session drives to report forging progress|
|`statusline/`|Renders the live forge animation, wrapping any status line you already have|

Nothing is destructive. Existing hooks from other tools are preserved, your current
status line is preserved and restored on uninstall, and `settings.json` is backed up
before every change.

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

Hooks and skills are picked up **without restarting Claude Code**. `/hooks` forces a
config reload if you want to be certain.

---

## The three habits

### 1. Before implementing — reuse before you build

At the start of a substantive turn, a `UserPromptSubmit` hook reminds the session to check
whether a skill already covers the task, before writing a plan or any code. Throttled to
one reminder per 20 minutes, and only for prompts of 60+ characters, so `yes` and
`continue` never trigger it.

### 2. During work — notice what is worth keeping

Every 12 file edits, a `PostToolUse` hook asks whether the current procedure clears the
bar. **Both** conditions must hold:

- **Costly** — >15 minutes of trial-and-error, a non-obvious ordering constraint, or an
  error a fresh session would predictably repeat, **and**
- **Recurring** — it has already happened twice, or it is a standing part of the workflow.

One without the other gets a note, not a skill. Forging is expensive; the bar is what
keeps it worth paying for.

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
already knows what the skill was *meant* to say, which is exactly the blindness being
tested for. Its checklist: cold-start executability, trigger precision (3 prompts that
should fire, 3 that should not), every asserted command actually run, unhappy paths,
overlap with existing skills, and scope creep.

### 3. When a skill misfires — fix, document, or retire

Never silently work around a bad skill; that pays the same cost in every future session.
Escalate: fix the wording → fix the procedure and re-run the full red-team loop → retire.

Retirement requires **independent concurrence**: a second fresh agent is asked the
*neutral* question *"should this be kept, fixed, or retired?"* — never "confirm this
deletion", which is a leading prompt any agent will rubber-stamp. Retiring moves the skill
to `~/.claude/skills-archive/` with a `WHY-ARCHIVED.md`. Nothing is ever `rm -rf`'d.

---

## The animation

While a skill is being forged, your status line shows live progress:

```
my-project git:(main)  ⠹ forge retry-backoff-wrapper ▕█████▓······▏ 4/8 50% · red-team round 1
```

The tail alternates between what is happening right now and a one-line summary of what the
skill is, so you can see both without leaving the status line. Done and failed states show
a ✓ or ✗ and clear themselves after 30 / 60 seconds.

Your existing status line is preserved and rendered first. Its output is cached for 5
seconds, so the 1-second refresh that drives the animation does not re-run `git` every
second.

```bash
skillforge start demo 4 "checking that the animation renders"
skillforge step 2 "red-team round 1"
skillforge done "clean"
skillforge clear     # escape hatch if a forge is ever left open
```

---

## Tuning

Noise is a tuning problem, not a reason to uninstall. Set these in the hook entries in
`~/.claude/settings.json`:

|Variable|Default|Meaning|
|-|-|-|
|`CI_EDIT_EVERY`|`12`|Edits between "is this worth crystallizing?" checkpoints|
|`CI_PROMPT_COOLDOWN`|`1200`|Seconds between "does a skill exist?" reminders|
|`CI_PROMPT_MIN_CHARS`|`60`|Shorter prompts never trigger a reminder|
|`STATUSLINE_BASE_TTL`|`5`|Seconds your base status line is cached|
|`SKILL_COMPOUNDER_STATE`|`~/.claude/skill-compounder`|Where runtime state lives|

---

## Uninstall

```bash
./uninstall.sh
# or:  curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/uninstall.sh | bash
```

Removes our hooks (leaving other tools' hooks alone), restores your original status line,
and removes the symlinks. Runtime state is left intact; delete it with
`rm -rf ~/.claude/skill-compounder`.

---

## Development

```bash
./run_tests.sh
```

45 tests, no mocks: real temporary Claude directories, real `settings.json` files, real
subprocess invocations of the shell scripts. See [docs/DESIGN.md](docs/DESIGN.md) for the
verified platform behavior the implementation depends on.

The animation at the top is recorded from a fabricated forge — no real transcript, path,
or skill name is ever captured. Regenerate it with [`vhs`](https://github.com/charmbracelet/vhs):

```bash
brew install vhs
./dev/generate_media.sh      # runs dev/forge_demo.sh under dev/forge.tape
```

---

## License

MIT — see [LICENSE](LICENSE).
