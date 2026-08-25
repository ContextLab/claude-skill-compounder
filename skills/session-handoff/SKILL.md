---
name: session-handoff
description: "Use when context is about to be lost: the indicator is low, /compact or /clear is imminent, a usage-limit warning appeared, you or the user suggests restarting Claude, or a session ends with work unfinished. Writes a resumable handoff (verbatim git state, exact error text, dead ends, one resume command) to notes/<ISO-date>-<topic>.md. Do NOT use for a mid-session recap the user asked for, or to record a fact, decision, or wiki entry when no context-loss event is in play."
---

# Session handoff: write it before the context is gone

**Core principle: the handoff carries what cannot be re-derived. Everything else is
already in the repo.**

```
A SUMMARY IS NOT A HANDOFF. PASTE THE EXACT OUTPUT, OR WRITE NOTHING.
```

## If you have almost no context left, do only this

```bash
mkdir -p notes
git symbolic-ref --quiet --short HEAD || echo "(detached)"   # branch, or (detached)
git rev-parse HEAD                                            # full sha
git status --porcelain
```

Write `notes/<ISO-date>-<topic>.md` with two sections: `## State`, holding a `branch:`
line, a `commit:` line, and the pasted porcelain output; and `## Resume command`, holding
one fenced line `cd <abs path> && git checkout <that sha> && git status --short`.

Fill in the rest if there is room. Phase 4's validator lists what is still missing, and
that list is your to-do order for whatever budget remains. Two sections beat none.

## When NOT to use

- **A mid-session recap the user asked for out loud.** Answer in chat.
- **Saving a fact, convention, or piece of domain knowledge.** No context-loss event is in
  play. That is a memory or wiki skill (`oh-my-claudecode:wiki`, `:remember`) or
  `.claude/CLAUDE.md`. Those are knowledge bases indexed by topic; this is an
  event-triggered snapshot indexed by date.
- **A plan for work not yet started.** That is planning, not handoff.

**Composition with `/soft-compact`.** A "take notes then compact" command
(`~/.claude/commands/soft-compact.md`) does not reference this skill and will not load it.
When one runs, invoke this skill yourself to produce its note: same folder, same naming,
one file.

## Phase 1: Recognize the trigger

Five triggers, all of them yours to notice rather than the user's:

1. The context indicator is low, or you are near the model's window.
2. `/compact` or `/clear` is about to run.
3. A usage-limit or rate-limit warning appeared.
4. **Anyone** says "restart Claude", "start fresh", or "reinstall and try again". Yours or
   the user's, that advice destroys the context that makes it actionable. This is the
   trigger that gets missed: a user who knew to ask first would not be losing context.
5. The session is ending with anything unfinished.

## Phase 2: Collect verbatim state

Run these and keep the raw bytes. Do not read them and paraphrase.

```bash
git symbolic-ref --quiet --short HEAD || echo "(detached)"
git rev-parse HEAD
git status --porcelain
git log --oneline -5
```

- **Detached HEAD:** `git rev-parse --abbrev-ref HEAD` returns the literal `HEAD`, and a
  resume command built from that reads `git checkout HEAD`, which goes nowhere. Use
  `symbolic-ref` as above and record `branch: (detached)`.
- **Not a git repository:** all four commands exit 128. Record `none (not a git
  repository)` for both `branch:` and `commit:`, and make the resume command `cd <abs
  path>` plus whatever re-enters the work (the dev server, the failing script).

For anything broken, capture the **exact test name**, its **exact output**, and the
**exact command that reproduces it**. Re-run the command now and paste what it prints.
Never abbreviate the output. An error you retyped or trimmed is a different error, and the
next session will grep for the string you invented.

## Phase 3: Write the file

Path: `notes/<ISO-date>-<topic>.md`, for example `notes/2026-08-25-lease-expiry.md`.
`mkdir -p notes` if absent. One file per session; never overwrite yesterday's.

Fill every mandatory section. A section with nothing to report gets the literal word
`None.` so emptiness is an assertion you made, not an omission the reader must guess at.
`TBD`, `see above`, and `various` are rejected: they are omissions wearing a word.

## What each section carries

|Section|What goes in it, and the failure it prevents|
|-|-|
|`## Resume command`|A fenced command that `cd`s to the repo and checks out **the recorded sha, not the branch**. Branch tips move. Prevents landing on a commit the handoff never described.|
|`## State`|`branch:` (or `(detached)`), `commit:` with the full sha, and pasted `git status --porcelain`. Prevents reasoning against the wrong tree.|
|`## Done and verified`|Each item with the command that proved it and the observed output. Prevents inherited false confidence.|
|`## Done but NOT verified`|The honest list. Collapsing it upward is how a session inherits a claim as a fact.|
|`## Broken`|Exact test name, pasted error output in a fence, and a `repro:` line. Prevents a rediscovery pass.|
|`## Dead ends`|What was tried, that it failed, and why. The session's most expensive output, and the thing a cold session will otherwise repeat verbatim.|
|`## Corrections to earlier notes`|Named file, quoted stale claim, what is now true. An append-only trail leaves false statements standing.|
|`## Open decisions`|Questions that need the user. A question is not a task and must not be filed as one.|
|`## Next`|Ordered open work. Tasks only.|
|`## Watch out for`|Traps a fresh session would predictably hit here.|

## Template

````markdown
# <ISO-date> handoff: <topic>

## Resume command

```bash
cd <absolute path to repo> && git checkout <full 40-char sha> && git status --short
```

## State

branch: <branch, or (detached)>
commit: <full 40-char sha>

```
$ git status --porcelain
<pasted output, or nothing if the tree is clean>
```

## Done and verified

- <what changed>. Proved by `<command>`, which printed `<observed output>`.

## Done but NOT verified

- <what changed, and what would prove it>

## Broken

- <exact test name or symptom>

```
<pasted error output, byte for byte, never trimmed>
```

repro: <exact command that reproduces the above>

## Dead ends

- Tried <approach>. Failed because <reason>. Do not retry it.

## Corrections to earlier notes

- `<notes file>` says "<stale claim>". That is no longer true: <what is true now>.

## Open decisions

- <question that needs the user, not a task>

## Next

1. <first task>

## Watch out for

- <trap a fresh session would hit>
````

Sections with nothing to report take the literal line `None.`

## Phase 4: Validate mechanically

A checklist you eyeball is exactly what fails under context pressure, which is the moment
this skill fires. Run the validator instead:

```bash
~/.claude/skills/session-handoff/scripts/check-handoff.sh notes/<your-file>.md
```

(If this skill lives elsewhere, use the `scripts/check-handoff.sh` next to the `SKILL.md`
you are reading.) It exits non-zero and prints one `REJECT <rule>` line per problem. Fix
and re-run until it exits 0. Do not report the handoff written until it does.

It proves rather than pattern-matches: the recorded sha must appear in the resume command,
the directory that command `cd`s into must exist, and `git cat-file -e` must confirm the
sha is a real commit there. A fabricated sha, a resume command naming only a branch, and a
`branch: HEAD` left from a detached checkout are all rejected. Section names come from
markers, not titles (state is whichever template section holds `branch:`, broken is
whichever holds `repro:`), so renaming or adding a section carries through.

## Phase 5: On resume

```bash
ls -t notes/*.md 2>/dev/null | head -3
```

If that prints nothing, there is no handoff; do not invent one from the git log. Otherwise
read the newest before anything else, then run its `## Resume command`. Treat
`## Done but NOT verified` as unverified, not as done.

## Why this exists

Compaction is not a save. Afterwards the model has the gist, none of the particulars, and
full confidence: *"It's almost like compact and new are the same thing."* One reporter,
after 59 compactions in 26 days, *"built a complete memory persistence system from scratch
because one didn't exist."*

Corrections are not optional politeness. This repository shipped two notes files both
asserting the forging protocol had never been run end to end, long after it had, because
every session appended and none corrected.

## Red flags

Each of these is the same thought, and each precedes an unusable handoff:

- "I'll just tell them in chat what to do next."
- "Let me summarize the failure."
- "It's roughly this test, they'll find it."
- "The traceback is long, I'll trim it."
- "I'll write this up properly at the end." (The trigger already fired. There is no end.)
- "The dead ends are noise."
- "The old note is close enough."

## Common rationalizations

|Excuse|Reality|
|-|-|
|"The compaction summary will carry this."|It carries gist. Not the sha, not the error string. The model then reasons confidently from what survived.|
|"One more fix, then I'll write it."|The trigger fired precisely because there is no budget for one more fix.|
|"Checking out the branch is the same thing."|Only until the tip moves, and it moves the moment anyone else pushes. Check out the sha.|
|"Pasting the whole traceback is wasteful."|Cheaper than a rediscovery pass. The next session greps for the exact string.|
|"Dead ends are just failures, skip them."|They are the session's most expensive output. Omitting them buys a guaranteed repeat.|
|"The earlier note already covers most of this."|Then it also still asserts the parts that are now false. Correct it by name.|
|"Working tree is clean, so State is empty."|Clean is a fact worth recording: branch, commit, and an empty fence.|
|"The user can just ask me to save context."|If they knew to ask, they would not be losing it.|

## Trigger precision

### Must fire (3)

- "we're almost out of context, let's wrap up"
- "I'm going to run /compact now"
- "you've hit your usage limit, we'll pick this up tomorrow"

### Must NOT fire (3)

- "remember that we always deploy with make release"
- "add a note to the wiki about how the auth flow works"
- "summarize the three changes you just made"

## Quick reference

|Phase|Do|Proof it happened|
|-|-|-|
|1. Recognize|Notice the trigger yourself, especially "restart Claude"|You said what triggered it|
|2. Collect|`symbolic-ref`, `rev-parse HEAD`, `status --porcelain`, re-run the failing command|Raw output in hand|
|3. Write|`notes/<ISO-date>-<topic>.md`, every section, `None.` where empty|File exists|
|4. Validate|`scripts/check-handoff.sh <file>`|Exit code 0|
|5. Resume|`ls -t notes/*.md 2>/dev/null \| head -3`, read, run the resume command|On the recorded sha|
