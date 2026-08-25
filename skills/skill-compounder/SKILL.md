---
name: skill-compounder
description: Use when deciding whether a repeatable procedure should become a reusable skill, when starting a major implementation (to check an existing skill first), or when a skill you invoked did not work well (to fix, document, or retire it). Runs a builder + red-team subagent loop, with a live progress animation via `skillforge`. Do NOT use for authoring a one-off script or for ordinary refactoring.
---

# Compounding: turn hard-won procedures into permanent capability

Every session should leave the toolchain measurably better than it found it, so the same
problem never gets solved from scratch twice. There are three habits to keep up, and a
threshold that keeps the machinery from costing more than it saves.

## 1. Before any major implementation, check for an existing skill

Before writing a plan or the first line of code for anything non-trivial:

1. Scan the skill list injected into this session's prompt.
2. `ls ~/.claude/skills/` (cross-project) and `ls ./.claude/skills/` (project-local).
3. `grep -ril '<keyword>' ~/.claude/skills ./.claude/skills ~/.claude/plugins/cache/*/*/*/skills`
   when the name is not an obvious match.

If a plausible skill exists, **invoke it**. Do not reimplement. If it turns out to be the
wrong tool, that is useful signal: go to section 3.

## 2. During work: is this pattern worth crystallizing?

Keep asking: *is what I am doing right now a repeatable procedure?* Good candidates are a
debugging workflow that finally worked, a deploy-and-verify sequence, a non-obvious API
dance, a project-specific build+test+screenshot loop.

**Threshold (BOTH must hold).** Forging a skill costs several subagent rounds, so be
selective:

- **Costly.** It took real effort to get right: roughly >15 minutes of trial-and-error, a
  non-obvious ordering constraint, or an error a fresh session would predictably repeat; AND
- **Recurring.** There is concrete reason to believe it recurs: it has already happened
  at least twice, or it is a standing part of this project's or this user's workflow.

If only one holds, write a note or update the project's `CLAUDE.md` instead. Do **not**
forge a skill for one-off work, for something a single sentence of documentation covers,
or for anything an existing skill already handles.

**Where it lives:** generalizes across projects → `~/.claude/skills/<name>/SKILL.md`.
Specific to one repo → `<repo>/.claude/skills/<name>/SKILL.md`, committed.

### Forging protocol (two agents, adversarial, looped)

**0. Announce it, and show the work.** The user must never discover a forge after the
fact. Say in plain text what the skill is and why it cleared the threshold, then start the
live status-line animation:

```
skillforge start <name> <total-steps> "<one-line summary>"
```

Budget `<total-steps>` as `2 + 2 × (planned red-team rounds)`, so 8 for the usual 3-round
cap. Call `skillforge step <n> "<what is happening right now>"` at **every** transition,
and always close with `skillforge done "<outcome>"` or `skillforge fail "<why>"`. A forge
left open strands a spinner in the user's status line; `skillforge clear` is the escape
hatch.

**1. Builder agent.** Dispatch a subagent that invokes a skill-authoring skill
(`skill-creator`, `writing-skills`, or equivalent) to write the SKILL.md. Give it the
concrete transcript of what worked, and the dead ends too. The dead ends carry the value.

**2. Red-team agent.** Dispatch a **separate, fresh** subagent. Never a fork of your own
context, and never the builder. A forked red-teamer already knows what the skill was
*meant* to say, so it cannot detect the ambiguity that will bite a cold session six weeks
from now. Do not tell it the skill is expected to be good. Its brief: *"Here is a skill at
`<path>`. Try to execute it cold. Where does it fail, mislead, or under-specify?"*

Required eval checklist:

|Check|What it catches|
|-|-|
|**Cold start**|Can step 1 be executed with no prior context and no clarifying question?|
|**Trigger precision**|Propose 3 prompts that SHOULD fire the `description` and 3 that should NOT. Does it discriminate?|
|**Verified claims**|Actually run every command, path, and API call the skill asserts. Unverified claims are defects.|
|**Unhappy path**|What does a session do when a step fails partway through?|
|**Overlap**|Does an existing skill already cover this? If so, that is a blocking finding.|
|**Scope**|Is it doing more than one thing? Split or narrow.|

**3. Loop.** Feed findings back to the builder via `SendMessage` so it keeps its context.
Spawn a **new** red-teamer each round; the whole test depends on the reader being
genuinely cold. Repeat until the report comes back clean.

**4. Cap at 3 rounds.** If it is not clean after 3, do not ship a half-working skill:
either narrow its scope until it *is* clean, or abandon it (`skillforge fail`) and leave
notes explaining what blocked it.

## 3. Fixing, documenting, or retiring a skill that did not work

Never silently work around a skill that misfired; that wastes the same time in every
future session. Escalate in order:

1. **Documentation issue** (procedure right, wording ambiguous): edit the SKILL.md now.
   Add an explicit "Do NOT use this when…" / "Known pitfalls" note naming the exact wrong
   turn taken, so a fresh session cannot repeat it.
2. **Substantive issue** (procedure wrong or outdated): fix it, then **re-run the full
   section 2 red-team loop** on the fix.
3. **Retirement** (obsolete, superseded, or unfixable): requires **independent
   concurrence**.
   - Write the case: what was attempted, why it cannot be fixed, what supersedes it.
   - Dispatch a second fresh subagent and ask a **neutral** question: *"Should this skill
     be kept, fixed, or retired? Justify."* Never ask it to "confirm the deletion". A
     leading prompt defeats the check.
   - Retire only if it independently reaches "retire." If it says keep or fix, do that.
   - Retiring means `mv` to `~/.claude/skills-archive/<name>/` plus a `WHY-ARCHIVED.md`
     recording the date, the case, and the concurring verdict. Never `rm -rf` a skill.
     Spurious deletions must be recoverable.

## 4. Hot-reloading

Skills are hot-reloaded. Writing `~/.claude/skills/<name>/SKILL.md` makes it available to
**this** session and to other already-running sessions, with no restart.

- There is a lag of roughly one tool round-trip. If `Skill` returns `Unknown skill: <name>`
  right after you create it, make any other tool call and retry. Do not conclude it failed.
- Fallback: `cat` the SKILL.md and follow it by path. The content works regardless of
  registry state.
- Consequence: finish and red-team a skill **during** the session that discovered the need
  for it. The benefit propagates immediately, and deferring to "next session" throws that
  benefit away.

## Troubleshooting

- `skillforge: command not found` → the CLI is at `~/.local/bin/skillforge`; ensure that
  directory is on `PATH`, or call it by full path.
- Animation not visible → the status line only renders while a forge is active. Check
  `skillforge show`. If `settings.json` was just installed, the status line picks up
  changes without a restart, but `/hooks` forces a config reload.
- Reminders too frequent or too rare → tune `CI_EDIT_EVERY`, `CI_PROMPT_COOLDOWN`,
  `CI_PROMPT_MIN_CHARS` in the hook entries in `settings.json`. If they are noisy, raise
  the thresholds instead of uninstalling.
