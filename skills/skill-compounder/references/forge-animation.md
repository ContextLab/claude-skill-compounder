# The forge animation: budget, close, and what the ledger can answer

`bin/skillforge` writes one JSON record per forge and the status line repaints it once a
second. Nothing streams, which is what lets a forge animate across subagent dispatches.

## The step budget

`<total-steps>` is fixed at `start` and no command can change it afterwards. Budget it as
`2 + 2 × (planned D rounds)`:

|`skillforge step`|What just happened|
|-|-|
|1|B dispatched C|
|2|C's draft landed and passed the parse gate|
|3, 4|D round 1: review, then revision|
|5, 6|D round 2|
|…|…|

So 12 steps for the usual 5-round cap, 22 for 10. Neither gate takes a number: the parse
check is part of accepting the draft, and the routing probe is part of closing. Dispatching
B is not a step either, because the ledger recovers round counts by inverting this budget —
planned rounds as `(steps - 2) / 2`, completed rounds the same way from the step actually
reached — and one extra step shifts every count.

**The protocol's prose sections and the animation's step numbers do not coincide.** Spell
the mapping out when briefing B rather than saying "the step numbering". An orchestrator
that calls `skillforge step 2..5` against the pasted section headings stalls the bar and
records one round where five happened.

**Overrunning is fine, and for a converging loop it is CORRECT.** `skillforge step 15
"round 7 review"` records 15 against a 12-step budget rather than clamping: the status line
draws `15/12 over` with the bar's last cell marked `»`, and `rounds` counts what was
completed.

**An overrun is not a verdict, and being past the cap triggers nothing.** This sentence used
to read "you are past the cap, so the narrow-or-abandon rule applies", which was the old
doctrine and is now wrong — it survived a rewrite of `SKILL.md` and contradicted it, in the
one file a converging session lands in at exactly the moment it is overrunning. What decides
narrow-or-abandon is the convergence assessment `SKILL.md` runs at EVERY round, on the round
record; a loop that is converging is *supposed* to overrun rather than cut to fit the budget,
and a loop that is not converging was already made to decide, rounds earlier.

Do not free the name by closing the forge first; that records an outcome for work that has
not finished.

## A step is also a heartbeat, and briefing B for phase changes alone is not enough

`skillforge list` marks an active forge whose last step is older than `SKILLFORGE_IDLE_SECS`
(2700 by default, the renderer's own knob). That mark answers "has anything happened
lately?", which is the only question an outside observer can ask, and it is deliberately not
a claim that the forge is dead.

**So the mark is only as useful as the stepping cadence, and that is on the brief.** Measured
on 2026-09-01: an orchestrator briefed to step on PHASE CHANGES dispatched its builder,
the builder spent 51 minutes constructing runnable reproductions for five findings, and the
forge crossed the stale threshold while working correctly. The record on disk and the record
of a forge whose session died were identical from outside, which is exactly the ambiguity the
mark exists to remove.

Raising the threshold is the wrong repair: it buys quiet by making a real death take longer
to notice. Brief B to step **whenever a stage runs long**, not only when the stage changes,
so that silence past the threshold means something. A step costs one append.

Two things follow for anyone reading a marked forge:

- **Check for a completion or failure notification before concluding anything.** A dispatched
  agent that died reports it. A marked forge with no such report is slow, not dead.
- **Never close a forge on the strength of the mark alone.** `skillforge fail` writes a
  reason into the ledger that a later reader will take at face value, and "it looked idle"
  is not a cause of death.

## Closing: three commands, not interchangeable

|Command|What the bar does|What the ledger records|
|-|-|-|
|`skillforge done "<outcome>"`|shows `✓ forged`, then clears itself|completion|
|`skillforge fail "<why>"`|shows `✗` and the reason, then clears itself|failure|
|`skillforge clear`|disappears immediately|**abandoned**|

`clear` is not a tidy-up. `skillreport` reads that ledger to answer whether forged skills
get reused, so clearing a forge whose work actually finished writes a false abandonment
into the only record of whether this protocol pays for itself. Close finished work with
`done`, blocked work with `fail`, and reach for `clear` only when neither is true — a forge
stranded by a session that died. Pass `--name <forge>` to any of the three while more than
one forge is live. After `done` or `fail` the record clears itself on its own timer.

**The first close wins and the second is discarded, silently.** Verified by running it: a
forge closed with `done "ok"` and then sent `fail "again"` answers `already closed out
(status: done); nothing to do`, exits **0**, and appends nothing. That is why exactly one
party owns the close.

Nothing about the animation ever needs a session restart. A wrong or stranded bar is fixed
by a command. `skillforge list` shows what is live; `skillforge show` prints one record.

## Reading `rounds`, and what it cannot tell you

`rounds` is always derived from the step, as `(step - 2) / 2`.

- On a `fail` it is the rounds actually completed, overrun included: abandoned at step 8 of
  12 records `rounds: 3, rounds_planned: 5`; abandoned at step 14 of 12 records `rounds: 6`
  against the same plan.
- On a `done` it carries an overrun the same way, because `done` raises the step to the
  total but never lowers it — but a forge that finished *inside* its budget records `rounds`
  equal to `rounds_planned` whatever it really took. So a clean forge cannot tell you how
  many rounds it really took. Put the real count in the close message, which is where a
  human reads it.

## The trigger, and the origin row

`start` takes `--trigger "<verbatim text>"` and `--trigger-kind
<user-prompt|hook-checkpoint|review-dispatch|agent-decision>`. Without them a forge still
runs and records `trigger_kind:"unrecorded"`, so the gap is countable rather than silent;
`SKILLFORGE_REQUIRE_TRIGGER=1` turns the warning into a refusal.

`done` writes the skill's `origin` row: what was built, where its directory is, the trigger
recorded at `start`, and the commit it was built on. It is written once per skill, ever, so
a re-forge does not produce a second answer to "how did this skill get here".

## Did the skill get used again?

`skillreport skills` prints all four ledger questions per skill. The usage half is fed by
`use` rows that `hooks/skill-use.sh` writes per invocation.

**That census counts successes only.** A *failed* invocation — `Unknown skill: <name>` — is
delivered to no hook at all on CLI 2.1.245, so transcripts remain the source for failures.
Do not write, or read, the ledger as a record of every invocation.

## Troubleshooting the display

- **Nothing visible.** The status line only renders while a forge is active; check
  `skillforge show`. If `settings.json` was just installed the status line picks up changes
  without a restart, but `/hooks` forces a config reload.
- **`skillforge: command not found`.** The CLIs install to `~/.local/bin/`; put it on
  `PATH` or call them by full path. Loaded as a plugin they are already on the Bash tool's
  `PATH`.
- **Reminders too frequent or too rare.** Tune `CI_EDIT_EVERY`, `CI_PROMPT_COOLDOWN` and
  `CI_PROMPT_MIN_CHARS` in the hook entries in `settings.json`. Raise the thresholds rather
  than uninstalling.

## What each step number in the budget means

`<total-steps>` is `2 + 2 × (planned D rounds)`:

- **step 1** when B is dispatched;
- **step 2** when C's draft lands and has passed the parse gate;
- then **one review step and one revision step per planned round**.

Neither gate gets a number of its own, and dispatching B is not a step. That is not
arbitrary: the ledger inverts this budget to recover the round count as `(steps - 2) / 2`,
so an extra number anywhere makes every recorded `rounds` wrong by half of it.

Overrunning is fine and is meant to be visible. Keep stepping past the budget; no command can
re-budget a live forge, and a forge that ran long should read as one that ran long.

## The held-out fields, and the step numbering B needs spelled out

**The CLI withholds the test set rather than trusting the orchestrator to.** `skillforge show`
and `skillforge ledger` omit `root`, `trigger`, `project` and `trigger_verbatim` unless you
pass `--full`, and they name what they left out so nobody reads a redacted record as a
complete one. The record on disk keeps every field; only the default view is reduced.

**Spell the step numbering out when briefing B**, because the numbers do not coincide with the
prose headings and an orchestrator that guesses stalls the bar:

- `step 1` on dispatching C;
- `step 2` when C's draft lands and passes the parse gate;
- `step 3` and `step 4` for the first D round — review, then revision;
- two more per round after that.

## What `done` looks for, and what the close row records

`done` looks under `<repo>/skills/<name>/` and `<repo>/.claude/skills/<name>/`, or wherever
`--skill-dir <dir>` said at `start`. The name that answers is the **directory's**, and a
destination held by something this package cannot prove it created is refused rather than
overwritten.

The close row records `skill: present` or `skill: missing` either way, so a forge that shipped
nothing stays countable after the terminal line has scrolled away.

**Scope follows placement.** A skill written to `<repo>/.claude/skills/` stays project-scoped
and `done` leaves it there rather than widening a placement its author chose. A headless
`claude -p` started in that repository sees it; one that narrows `--setting-sources` does not.
Both measured, in `docs/CLAUDE-CODE-BEHAVIOR.md`.

**The lag, measured.** A skill created mid-session became invocable in that session in 4 of 4
runs, but 2 of those 4 answered `Unknown skill` on the first `Skill` call and launched on the
second. A **subagent** dispatched after the install saw it first-try in 4 of 4. So retrying is
correct in the main thread, and handing the job to a subagent removes the race.

## Why `--trigger` is mandatory in the protocol though the CLI only warns

The ledger asks what set a forge off, what got built, when it has been used since, whether it
worked, and whether it was applied to the problem that caused it. **The first is the only one
nothing can reconstruct later.** A trigger is what a person actually said or what a hook
actually emitted; by the time anyone reads the row, the moment is gone and a summary written
from memory is not the same artifact.

`--trigger-kind` says who was asking. Whether that field moves towards `user-prompt` over time
is the measurement this whole package exists to make: a forge started because a human asked is
a different event from one a hook nagged into existence.

The CLI warns rather than refuses because refusing produces no row at all, and the cheapest
way past a CLI that refuses is to stop calling it. A gap recorded as `trigger_kind:"unrecorded"`
is countable; a missing row is not. `SKILLFORGE_REQUIRE_TRIGGER=1` turns the warning into a
refusal once every caller is updated.

## What the apply debt demands, and what it does not

`skillforge done` leaves a marker, and until `skillforge apply` answers it the forge is closed
but not finished. A `Stop` hook reads that marker and blocks the turn — **once per skill per
session**. It then records that it has named that skill and lets go, so the same session is not
stopped twice for the same debt however many turns it runs. The block message says so itself.
It is a flag raised where it cannot be missed, not a wall, and describing it as refusing to end
the session overstates it in the direction that makes a reader switch it off.

**`declined` is a first-class outcome, not a failure row.** The question the debt asks is
*"was this used on the problem that caused it?"*, and `no` is a real answer to it — the skill
turned out to be the wrong tool, the problem dissolved, the session ended somewhere else. What
the ledger is measuring is how often a forge closes the loop, and a `declined` row is data about
that; a debt quietly left unanswered is not. Answer it either way and the forge is finished.

The window is `APPLY_GATE_WINDOW`, 86400 seconds by default: a forge closed yesterday is still
the forge this work asked for, and one closed last month is an archaeology problem rather than a
turn's. Past the window the marker stops blocking and `skillforge pending` still lists it.
