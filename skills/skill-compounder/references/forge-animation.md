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

**Overrunning is fine.** `skillforge step 15 "round 7 review"` records 15 against a 12-step
budget rather than clamping: the status line draws `15/12 over` with the bar's last cell
marked `»`, and `rounds` counts what was completed. Read the overrun as what it is — you
are past the cap, so the narrow-or-abandon rule applies. Do not free the name by closing
the forge first; that records an outcome for work that has not finished.

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
