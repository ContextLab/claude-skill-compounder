# Verifying every skill on this machine with real calls

2026-08-28. Triggered by: *"if the finish-task skill did NOT finish the task, it's a broken
skill!"* and the goal *"fix ALL skills and verify they work as advertised w/ real calls."*

Two separate pieces of work came out of that. This file is the **verification** half. The
repair of `finish-task` itself is a forge running under the `skill-compounder` protocol and
is recorded separately.

## The headline

Before today, **4 of the 14 skills installed on this machine could not be verified at all**,
and **nothing said so**. Three defects in the verifying instrument, not in any skill, made
"verify every skill" impossible to even attempt.

After: 14 of 14 carry a trigger contract, every one has been run against real
`claude -p --model sonnet` sessions at the CLI version actually installed, and every result
is pinned with its k/N.

## The three instrument defects, in the order they had to be fixed

**1. The verifier could not see most of the machine's skills.** `scripts/routing_claims.py`
hardcoded `SKILLS = REPO / "skills"`. A routing claim is only ever true of an *installed*
skill — the router reads `~/.claude/skills`, and this machine carries four skills no
checkout contains (forged for personal use, or symlinked in from another repository). They
had never been probed because no instrument could reach them. Fixed with
`SKILL_ROUTING_ROOT`.

**2. `lint` excused the skills it could not check.** A skill with no `## Trigger precision`
section hit `continue` under the comment *"a skill may legitimately ship no routing claims
at all"*. The cost, measured: linting the installed directory printed

    10 skill(s) with routing claims, 7 finding(s).

over a directory of **14**. That sentence is true and reads as full coverage; the four it
does not mention are precisely the four nothing can check. Silence about an unverifiable
skill reads as a pass — the same failure `unmeasured-is-not-verified` names for a probe that
could not run. A section-less skill is now a finding, and the summary prints the
denominator:

    14 skill(s) scanned in /Users/jmanning/.claude/skills: 14 with routing claims, 0 with none, 0 finding(s).

There is no legitimate case behind the old comment. A skill exists to fire; one with no
claim about when it fires has never had that checked by anything.

**3. The parser silently dropped any prompt that wrapped a line.** `_QUOTED` matches within
one line, so a prompt whose quote opened on one line and closed on the next was filed as
malformed rather than read. `dead-guard-detection` had **six prompts on the page and two
parsed**, sat under both three-prompt floors, and looked complete to anyone reading the file.
Wrapping is ordinary prose formatting, not an authoring error, so the parser was what was
wrong: list-item continuation lines are now joined before the quote is sought.

**The safety check that made that fix committable**: every shipped skill's `prompts_digest`
was recorded before the change and compared after. Byte-identical for all of them, so no
existing pin was silently invalidated by the repair. A parser change that moved a digest
would have broken pins without touching a description.

## What the real calls found

**234 real `claude -p --model sonnet --max-turns 3` calls**, three passes, all at CLI
**2.1.250** — the version actually installed. Every pin in the repo had been measured on
2.1.245 or 2.1.247.

### Three skills were advertising falsely

|Skill|Before|Losing prompt|After|
|-|-|-|-|
|`ai-tell-audit`|3/9|"Draft the release notes for v2.1, they go out to users today." fired **nothing, 0/3**|**9/9**|
|`skill-authoring`|6/9|"Rename the skill directory and rewrite the frontmatter…" fired **nothing, 0/3**|**9/9**|
|`no-silent-stub`|8/9|"…Just make the suite pass." 2/3|8/9, split moved|

The first two are the instructive ones. **Both descriptions named the losing prompt almost
verbatim and it still did not fire.** `ai-tell-audit` listed *"write the release notes"* as a
trigger; `skill-authoring` said *"naming the directory"*. What fixed both was moving the
trigger into the opening clause instead of leaving it in a mid-sentence list —
`ai-tell-audit` now opens "Use BEFORE drafting or rewriting…". This is the same
sensitivity `references/routing-gate.md` already records, where four words flipped a verdict.

Almost every loss was **"fired nothing at all"** rather than a neighbour winning the prompt.
The failure mode is a description the router does not match, not a boundary dispute.

### The `no-silent-stub` split MOVED rather than cleared

The first pass had "The tests need an API key we don't have. Just make the suite pass." at
2/3, so the description was edited to name that phrasing. The re-measure put that prompt at
3/3 and left **"Finish this parser. For the branches you can't do yet, return an empty
list."** at 2/3 — a prompt the earlier pass had won outright.

Two readings and nothing here separates them: the edit shifted the description's emphasis
off the second prompt, or routing variance landed differently. Either way one prompt has
been *shown* unreliable, a later clean pass does not un-show it, and the honest pin is
`partial`. It is in the debt ledger in `tests/test_routing_claims.py`.

### Four skills measured for the first time ever

|Skill|Result|
|-|-|
|`contribute-skill`|**verified** 9/9 — shipped with no trigger section at all|
|`history-surfer`|**verified** 9/9|
|`speckit-execute`|**verified** 9/9|
|`dead-guard-detection`|partial 8/9 — one prompt 2/3|
|`parallel-agents-one-codebase`|partial 8/9 — one prompt 2/3|

`speckit-execute` is worth a note: its description carries **no `Use when` clause and no
decline clause** — it states what the skill does, never when it fires — and every prompt won
every draw anyway. Do not read that as licence to drop those clauses; it is one skill whose
verbs happen to be unusually distinctive.

The two 8/9s already name their losing prompt near-verbatim, so unlike the two repaired
above there is no obvious wording lever. 2/3 sits inside the spread this repository has
already measured on *unchanged* descriptions (3/3, then 1/3, then 2/3).

### Nothing over-fires

**Every must-not-fire prompt, on all 14 skills, scored 9/9.** That is the result worth
saying out loud: a skill that answers everything displaces the neighbour that should have
handled it and teaches the session to distrust skill dispatch, which is worse than a skill
that occasionally fails to fire.

## What is NOT established

- **Four pins are stale relative to evidence that was held and lost.**
  `claim-provenance`, `destructive-op-preflight`, `session-handoff` and
  `stale-artifact-check` each measured 9/9 at 2.1.250 in the first pass, but their pins still
  read 2026-08-25 at 2.1.245. The raw probe log was destroyed mid-session (below), and a pin
  is supposed to be backed by an artifact rather than by a figure someone remembers reading.
  They are being re-probed rather than transcribed. The current pins are older, not false.
- **No suite guards the four skills installed outside this repository.** The instrument can
  now reach them; nothing re-runs it on a schedule. Their pins live in `~/.claude/skills`,
  which no test in this checkout reads.
- **A pin is a reading, not a property.** Every figure here is one day, one CLI version, one
  model. `stale-artifact-check` once lost its prompts to a skill in a *different package*,
  with no commit anywhere near this repository.

## The scratch directory was destroyed mid-session, and that is a finding

While the repair forge was running, the scratch directory this session was using —
`/tmp/finish-ahxczY`, holding a full-suite log, three routing-probe result files, path
snapshots and three backup copies of shipped scripts — **was deleted while in use**. This
session did not delete it, and afterwards `ls -d /tmp/finish-*` matched nothing.

The only thing on this machine documenting a destructive command against a path of that
shape is `skills/finish-task/SKILL.md`, whose Phase 6 reads `rm -rf /tmp/finish-REPLACE`, and
cold agents were executing that skill at the time. **The attribution is unproven** — it would
need a transcript this session could not load — **but the defect does not depend on the
attribution**:

> The skill tells every run to create its scratch directory under a shared, guessable prefix
> in a world-writable location, and to remove it with `rm -rf`. It reasoned about concurrency
> and solved only half: *"A fixed /tmp path is shared with every finish this machine has run,
> so make one that cannot already exist"* prevents **collision on creation** and says nothing
> about **destruction on cleanup**. The skill's own warning — "never with a trailing `/*`" —
> shows the author saw the shape of this and stopped one character short.

It matters more than an ordinary bug because of *what* lives there: the skill designates that
directory as the home for sweep logs, canary evidence and dispatch snapshots — the evidence a
finish needs in order to be defensible. A procedure whose scratch convention lets one run
destroy another's evidence has a failure mode aimed at its own deliverable.

Reported to the forge orchestrator as a round finding, with the note that
`destructive-op-preflight` is an installed skill that already owns this class of command and
should be *invoked* rather than restated.

**What was actually lost**: re-runnable logs, and the raw probe output. The measurement
*results* survived, because the pins are written into the skill files. That is the pin
mechanism doing exactly what it was designed for, on a day nobody planned to test it.
