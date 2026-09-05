---
name: session-handoff
description: "Use when context is about to be lost with work unfinished: 'we're almost out of context', 'I'm going to run /compact now', 'you've hit your usage limit, we'll pick this up tomorrow' mid-refactor with tests still red, anyone suggests restarting Claude, or the session ends mid-task. Write a resumable handoff (verbatim git state, exact errors, dead ends, one resume command) to notes/<ISO-date>-<topic>.md. Do NOT use for a mid-session recap or to record a fact when no context loss is near."
---

# Session handoff: write it before the context is gone

**Core principle: the handoff carries what cannot be re-derived. Everything else is
already in the repo.**

```
A SUMMARY IS NOT A HANDOFF. PASTE THE EXACT OUTPUT, OR WRITE NOTHING.
```

## If you have almost no context left, start here

```bash
mkdir -p notes
if git rev-parse --git-dir >/dev/null 2>&1; then
  git symbolic-ref --quiet --short HEAD || echo "(detached)"
  git rev-parse --verify --quiet HEAD || echo "none (no commits yet)"
  git status --porcelain
else
  echo "none (not a git repository)"
fi
```

Paste that into `## State` in `notes/<ISO-date>-<topic>.md`, write `## Resume command`
from the template below, and keep going down the section list in order. **This handoff
does not preserve uncommitted work.** If the tree is dirty and the work matters, commit it
to a `wip/<topic>` branch or `git stash push -m <topic>` now, and record which you did
under `## Next`. Nothing else here will carry it.

The validator will not pass until every section is written, and that is correct: the
sections most often skipped under pressure (dead ends, what is broken, what is next) are
the ones that cannot be re-derived from the repository.

## When NOT to use

- **A mid-session recap the user asked for out loud.** Answer in chat.
- **Saving a fact, convention, or piece of domain knowledge.** No context-loss event is in
  play. That is a memory or wiki skill (`oh-my-claudecode:wiki`, `:remember`) or
  `.claude/CLAUDE.md`. Those are knowledge bases indexed by topic; this is an
  event-triggered snapshot indexed by date.
- **A plan for work not yet started.** That is planning, not handoff.

**Neighbouring commands.** A "take notes then compact" command
(`~/.claude/commands/soft-compact.md`) does not reference this skill and will not load it;
when one runs, invoke this skill yourself to produce its note. That command commits and
pushes *after* the note, which invalidates the sha and porcelain output you just recorded,
so write the handoff after the commit or re-run phase 2 once it exists. On the other side,
a session-start command (`/wakeup`) covers the same ground as phase 5; if one runs, let it
drive and supply the newest note rather than duplicating the search.

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

Run the block above and keep the raw bytes. Do not paraphrase. Four things it gets right
that the obvious commands get wrong:

- **It is an `if`, not `A && B || C`.** In a bare repository `rev-parse --git-dir`
  succeeds but `git status` fails, so the `||` branch fires *as well*, and the state block
  reports a branch, a sha, and "not a git repository" together.
- **It guards on `rev-parse --git-dir` first.** In a directory that is not a repository,
  `git symbolic-ref ... || echo "(detached)"` prints `(detached)`, because every git
  command there exits 128. A non-repository then gets recorded as a detached checkout.
- **Detached HEAD:** `git rev-parse --abbrev-ref HEAD` returns the literal `HEAD`, and a
  resume command built from that reads `git checkout HEAD`, which goes nowhere.
  `symbolic-ref` fails instead, so the fallback records `branch: (detached)`.
- **A repository with no commits:** `git rev-parse HEAD` prints the literal string `HEAD`
  on **stdout** while exiting 128, so `2>/dev/null || echo ...` records both `HEAD` and
  the fallback. `--verify --quiet` is the form that actually stays silent.

**Uncommitted work is not part of the handoff.** `git status --porcelain` records
filenames, not content, and this skill deliberately does not try to serialise the
difference: every mechanism for that (a patch file, an implicit stash) fails silently on
binary files, mode changes, or a single conflicting hunk, and restores nothing while
appearing to work. Commit it to a `wip/` branch or stash it by hand, and say which under
`## Next`. That is the honest boundary of what a text file can carry.

For anything broken, capture the **exact test name**, its **exact output**, and the
**exact command that reproduces it**. Re-run the command now and paste what it prints.
Never abbreviate. An error you retyped or trimmed is a different error, and the next
session will grep for the string you invented.

## Phase 3: Write the file

Path: `notes/<ISO-date>-<topic>.md`. `mkdir -p notes` if absent. One file per session;
never overwrite yesterday's.

Fill every mandatory section. A section with nothing to report gets the literal word
`None.` so emptiness is an assertion you made, not an omission the reader must guess at.
`TBD`, `see above`, and `various` are rejected: they are omissions wearing a word.

## What each section carries

|Section|What goes in it, and the failure it prevents|
|-|-|
|`## Resume command`|Three lines: `cd` to the repo by **absolute, quoted** path, park whatever is in the tree with `git stash push` (findable afterwards in `git stash list`), then `git checkout -B` onto **the recorded sha**. Prevents an aborted checkout on a dirty tree, a surprise detached HEAD, and landing on a branch tip that has moved. Two more lines when `## State` records `uncommitted work: stashed as NAME`, and delete those two otherwise: `git stash list \| grep -F` the NAME, then `git stash pop` the ref it printed. Keyed on the message and never on `stash@{0}`, because the `git stash push` on line 2 takes position 0 and moves NAME to `stash@{1}`.|
|`## State`|`branch:`, `commit:` with the full 40-character sha, pasted `git status --porcelain`, and `uncommitted work:` naming where the dirty tree went. Prevents reasoning against the wrong tree. The validator rejects `uncommitted work: none` when the tree is in fact dirty, because that is the one loss nothing else here can undo.|
|`## Done and verified`|Each item with the command that proved it and the observed output. Prevents inherited false confidence.|
|`## Done but NOT verified`|The honest list. Collapsing it upward is how a session inherits a claim as a fact.|
|`## Broken`|Exact test name, pasted error output in a fence, and a `repro:` line that actually reproduces it. Prevents a rediscovery pass.|
|`## Dead ends`|What was tried, that it failed, and why. The session's most expensive output, and the thing a cold session will otherwise repeat verbatim.|
|`## Corrections to earlier notes`|Named file, quoted stale claim, what is now true. An append-only trail leaves false statements standing.|
|`## Open decisions`|Questions that need the user. A question is not a task and must not be filed as one.|
|`## Next`|Ordered open work, including where any uncommitted work was parked. Tasks only.|
|`## Watch out for`|Traps a fresh session would predictably hit here.|

## Template

````markdown
# <ISO-date> handoff: <topic>

## Resume command

```bash
cd "<absolute path to the repo>"
git stash push --message "before resuming <ISO-date>" || true
git checkout -B resume/<topic> <full 40-char sha>
git stash list | grep -F "<the NAME recorded under uncommitted work>"
git stash pop "<the stash@{N} ref that grep printed>"
```

## State

branch: <branch name, or (detached), or none (not a git repository)>
commit: <full 40-char sha, or none (no commits yet), or none (not a git repository)>
uncommitted work: <none, or where you put it: stashed as NAME, committed to wip/BRANCH, or left in the tree>

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
this skill fires. Run the validator instead. It lives in `scripts/` beside the `SKILL.md`
you are reading; if you do not know that path:

```bash
find -L ~/.claude ~/.config/claude . -maxdepth 6 -name check-handoff.sh 2>/dev/null | head -1
```

`-L` is required because the standard install makes the installed skill directory a
symlink into a checkout and `find` will not descend into a symlink without it, so the
unfollowed form prints nothing and the gate two paragraphs down gets skipped as
unavailable.

Then `check-handoff.sh notes/<your-file>.md`. It exits non-zero and prints one
`REJECT <rule>` line per problem. Fix and re-run until it exits 0. Do not report the
handoff written until it does.

It proves rather than pattern-matches. The directory the resume command `cd`s into must
exist; what it *is* then decides what `commit:` may say. A real repository means the sha
must be 40 hex characters, must pass `git cat-file -e`, and must be the argument of a
`git checkout` or `git switch` in the resume block. A directory that is not a repository
means `commit:` must say so too, so a fabricated sha has nowhere to hide. Section names
come from markers rather than titles (state is whichever template section holds `branch:`,
broken is whichever holds `repro:`), so renaming or adding a section carries through.
Parsing is fence-aware, so pasted output containing a `## ` line stays output.

What it does not check: whether your prose is true. It can prove the sha exists; it cannot
prove your dead ends are the real ones.

## Phase 5: On resume

```bash
ls -t notes 2>/dev/null | head -3
```

Avoid `ls notes/*.md`: under zsh an unmatched glob is a shell error that a redirect cannot
suppress. If the listing is empty there is no handoff, and you must not invent one from
the git log. Otherwise read the newest before anything else, then run its
`## Resume command`. Treat `## Done but NOT verified` as unverified, not as done.

If `git checkout -B` fails with "already used by worktree", another checkout holds that
branch: `git worktree list` finds it, and either work there or resume onto a different
name (`git checkout -B resume/<topic>-2 <sha>`). It fails without moving HEAD, so nothing
is lost.

## Known limitations

- **Uncommitted work is not carried.** Stated above, and the validator will not let you
  claim otherwise, but no part of this skill moves that work for you.
- **In a bare repository `mkdir -p notes` lands inside the git directory.** Bare repos
  have no working tree; write the note in the checkout you were actually working in.
- The validator checks structure and recorded state. It cannot check whether the prose is
  true, and a `repro:` line that runs is not proof that it reproduces the failure.

## Why this exists

Compaction is not a save. Afterwards the model has the gist, none of the particulars, and
full confidence: *"It's almost like compact and new are the same thing."* One reporter,
after 59 compactions in 26 days, *"built a complete memory persistence system from scratch
because one didn't exist."*

Corrections are not optional politeness. An append-only trail leaves false claims standing:
two notes can both assert something that stopped being true months ago, each as confidently
as the line below it, because every session appended and none corrected.

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
|"Checking out the branch is the same thing."|Only until the tip moves, and it moves the moment anyone pushes. Check out the sha.|
|"The dirty tree will still be there tomorrow."|Probably, and nothing here guarantees it. Commit it to a `wip/` branch or stash it, then say so under `## Next`.|
|"Pasting the whole traceback is wasteful."|Cheaper than a rediscovery pass. The next session greps for the exact string.|
|"Dead ends are just failures, skip them."|They are the session's most expensive output. Omitting them buys a guaranteed repeat.|
|"The earlier note already covers most of this."|Then it also still asserts the parts that are now false. Correct it by name.|
|"The user can just ask me to save context."|If they knew to ask, they would not be losing it.|

## Trigger precision

<!-- routing-pin
description-sha256: ec6749f499df8f781b2f165532f44bab8843a8f48410e12d991c357f9a87f2b8
prompts-sha256: de09a9bf1705ada1ed41359171480a179ee23b29daecab78882153d33d9d4e85
measured: 2026-09-01
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: verified 9/9 must-fire draws, 9/9 must-not-fire draws (3/3 each prompt over 3 runs)
-->

### Must fire (3)

- "we're almost out of context, let's wrap up"
- "I'm going to run /compact now"
- "We're halfway through the migration refactor and three tests are still red. You've hit your usage limit, we'll pick this up tomorrow."

Every one of these carries unfinished work, and the third one says so out loud because
it has to. All measurements here are real `claude -p --model sonnet` sessions checked for
an actual `Skill` tool call. Under the pre-2026-08-25 description, the bare fragment
*"you've hit your usage limit, we'll pick this up tomorrow"*, with no work in view, fired
nothing at all; the description now quotes that fragment verbatim, and a 2026-08-25 run
measured the bare fragment firing this skill. That trade is deliberate: a handoff for
zero work is a file of `None.` lines, which is cheap, while a missed handoff for real
work is unrecoverable. Phase 3, not the router, is where an empty session gets its
honest empty note.

### Must NOT fire (3)

- "remember that we always deploy with make release"
- "add a note to the wiki about how the auth flow works"
- "summarize the three changes you just made"

## Quick reference

|Phase|Do|Proof it happened|
|-|-|-|
|1. Recognize|Notice the trigger yourself, especially "restart Claude"|You said what triggered it|
|2. Collect|Run the guarded state block, re-run the failing command, park any dirty tree by hand|Raw output in hand|
|3. Write|`notes/<ISO-date>-<topic>.md`, every section, `None.` where empty|File exists|
|4. Validate|`check-handoff.sh <file>`|Exit code 0|
|5. Resume|`ls -t notes 2>/dev/null \| head -3`, read, run the resume command|On the recorded sha|
