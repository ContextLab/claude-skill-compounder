---
name: session-handoff
description: Use when context is about to be lost: the context indicator is low, /compact or /clear is imminent, a usage-limit warning appeared, you are about to suggest restarting Claude, or a session is ending with work unfinished. Writes a resumable handoff (verbatim git state, exact error text, dead ends, one copy-pasteable resume command) to notes/<ISO-date>-<topic>.md. Do NOT use to record a fact, decision, or knowledge-base entry with no context-loss event in play; that is a memory or wiki skill.
---

# Session handoff: write it before the context is gone

## Overview

Compaction is not a save. After a `/compact` the model has the gist and none of the
particulars, and it reasons confidently from the gist. One reporter's summary of the
result: *"It's almost like compact and new are the same thing."* Another, after 59
compactions in 26 days, *"built a complete memory persistence system from scratch because
one didn't exist."*

The fix is not more memory. It is one file on disk, written while the particulars are
still in context, containing what a cold session cannot re-derive: the exact commit, the
exact error string, the things that were tried and failed.

**Core principle: the handoff carries what cannot be re-derived. Everything else is
already in the repo.**

```
A SUMMARY IS NOT A HANDOFF. PASTE THE EXACT OUTPUT, OR WRITE NOTHING.
```

## When NOT to use

- **Saving a fact, convention, or piece of domain knowledge.** No context-loss event is in
  play. That is a memory or wiki skill (`oh-my-claudecode:wiki`, `:remember`), or
  `CLAUDE.md`. Those are knowledge bases indexed by topic; this is an event-triggered
  snapshot indexed by date.
- **A mid-session recap** the user asked for out loud. Answer in chat.
- **A plan or task ledger for work not yet started.** That is planning, not handoff.

**If the user typed `/soft-compact` (or any equivalent "take notes then compact"
command), this skill supplies the content of that command's note-taking step.** It writes
to the same `notes/` folder with the same naming. Never open a second location.

## Phase 1: Recognize the trigger

Five triggers, all of them yours to notice rather than the user's:

1. The context indicator is low, or you are near the model's window.
2. `/compact` or `/clear` is about to run, by you or by the user.
3. A usage-limit or rate-limit warning appeared.
4. You are about to say "restart Claude", "start a fresh session", or "reinstall and try
   again". The advice destroys the context that makes the advice actionable.
5. The session is ending with anything unfinished.

Trigger 4 is the one that gets missed. A user who knew to ask for a handoff before
restarting would not have lost the context in the first place; the responsibility is
yours.

## Phase 2: Collect verbatim state

Run these and keep the raw bytes. Do not read them and paraphrase.

```bash
git rev-parse --abbrev-ref HEAD          # branch
git rev-parse HEAD                       # full commit sha
git status --porcelain                   # exact, machine-shaped
git log --oneline -5
```

For anything broken, capture the **failing test's exact name**, its **exact output**, and
the **exact command that reproduces it**. Re-run the command now and paste what it prints.
An error you retyped from memory is a different error, and the next session will grep for
the string you invented.

## Phase 3: Write the file

Path: `notes/<ISO-date>-<topic>.md`, for example `notes/2026-08-25-lease-expiry.md`.
`mkdir -p notes` if it does not exist. One file per session; do not overwrite yesterday's.

Fill every mandatory section. A section with nothing to report gets the literal word
`None.` so that emptiness is an assertion you made, not an omission the reader has to
guess about.

|Section|What goes in it, and the failure it prevents|
|-|-|
|`## Resume command`|A fenced, copy-pasteable command that lands the next session in the right directory on the right commit. First thing it runs. Prevents ten minutes of orientation.|
|`## State`|A `branch:` line, a `commit:` line with the full SHA, and pasted `git status --porcelain`. Prevents reasoning against the wrong tree.|
|`## Done and verified`|Each item with the command that proved it and the observed output. Prevents inherited false confidence.|
|`## Done but NOT verified`|The honest list. Collapsing this into the section above is how a session inherits a claim as a fact.|
|`## Broken`|Exact test name, pasted error output in a fence, and a `repro:` line. Prevents a rediscovery pass.|
|`## Dead ends`|What was tried, that it failed, and why. The most expensive thing learned this session, and the thing a cold session will otherwise repeat verbatim.|
|`## Corrections to earlier notes`|Named file, quoted stale claim, what is now true. An append-only trail leaves false statements standing.|
|`## Open decisions`|Questions that need the user. A question is not a task and must not be filed as one.|
|`## Next`|Ordered open work. Tasks only.|
|`## Watch out for`|Traps a fresh session would predictably hit here.|

`## Corrections to earlier notes` is not optional politeness. This repository shipped two
notes files that both asserted the forging protocol had never been run end to end, long
after it had been, because every session appended and none corrected.

## Template

````markdown
# <ISO-date> handoff: <topic>

## Resume command

```bash
cd <absolute path to repo> && git checkout <branch> && git rev-parse HEAD
```

## State

branch: <branch>
commit: <full 40-char sha>

```
$ git status --porcelain
<pasted output, or nothing if clean>
```

## Done and verified

- <what changed>. Proved by `<command>`, which printed `<observed output>`.

## Done but NOT verified

- <what changed, and what would prove it>

## Broken

- <exact test name or symptom>

```
<pasted error output, byte for byte>
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

(If this skill lives elsewhere, use `scripts/check-handoff.sh` next to the `SKILL.md` you
are reading.) It exits non-zero and prints one `REJECT <rule>` line per problem. Fix the
handoff and re-run until it exits 0. Do not report the handoff written until it does.

The validator reads the mandatory section list out of the template above, so the two can
never drift.

## Phase 5: On resume

At the start of any session picking up prior work:

```bash
ls -t notes/*.md | head -3
```

Read the newest before doing anything else, then run its `## Resume command`. Treat
`## Done but NOT verified` as unverified, not as done.

## Red flags

Each of these is the same thought. If you catch it, you are about to write an unusable
handoff:

- "I'll just tell them in chat what to do next."
- "Let me summarize the failure."
- "It's roughly this test, they'll find it."
- "The traceback is long, I'll describe it."
- "The git log is in the scrollback."
- "I'll write this up properly at the end." (The trigger already fired. There is no end.)
- "The dead ends are noise."
- "The old note is close enough."

## Common rationalizations

|Excuse|Reality|
|-|-|
|"The compaction summary will carry this."|It carries gist. It does not carry the SHA or the error string, and the model will reason confidently from what survived.|
|"One more fix, then I'll write it."|The trigger fired precisely because there is no budget for one more fix.|
|"Pasting the whole traceback is wasteful."|Cheaper than a rediscovery pass. The next session greps for the exact string.|
|"Dead ends are just failures, skip them."|They are the session's most expensive output. Omitting them buys a guaranteed repeat.|
|"The earlier note already covers most of this."|Then it also still asserts the parts that are now false. Append is not enough; correct it by name.|
|"There is no `notes/` folder here."|`mkdir -p notes`.|
|"Working tree is clean, so State is empty."|Clean is a fact worth recording. Paste an empty fence, plus branch and commit.|
|"The user can just ask me to save context."|If they knew to ask, they would not be losing it. Reference: the whole of issue #39663.|

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
|2. Collect|Run the four git commands, re-run the failing command|Raw output in hand|
|3. Write|`notes/<ISO-date>-<topic>.md`, all ten sections, `None.` where empty|File exists|
|4. Validate|`scripts/check-handoff.sh <file>`|Exit code 0|
|5. Resume|`ls -t notes/*.md \| head -3`, read, run the resume command|On the stated commit|
