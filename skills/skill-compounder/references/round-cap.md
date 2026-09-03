# Where the round cap comes from

The cap is 2 rounds, or 4 for a skill that is complex or safety-critical, and `skillforge`
enforces it: `skillforge round` refuses a round past the budget, and `skillforge escalate` is
the only way to raise it. Both numbers are guesses. This file says how good a guess, and how
the record this file describes is now the file the CLI reads.

## It is not a measurement

The ledger cannot supply one. What it can supply is the shape of every forge recorded here,
and one command puts the whole basis in front of you:

```bash
jq -r 'select(.event != "start")
       | [.name, .event, .rounds, .rounds_planned, .phase] | @tsv' \
  ~/.claude/skill-compounder/ledger.jsonl
```

Run it before trusting the rest of this file.

## What the record showed when 5 was chosen, and why 5 became 2

Three closed forges, two of which wanted more than three rounds.

- The first `ai-tell-audit` attempt ran a three-round budget to its last step and was
  abandoned there — `fail`, `rounds: 3` of `rounds_planned: 3`, "wrong artifact: built a
  statistical detector, the need is a pattern-list editor".
- The third was budgeted five rounds and closed "shipped after 7 builder rounds and 7
  red-team rounds".
- The one forge that closed inside three rounds is the second, and it is less a
  counterexample than the receipt for the first: a re-scoped retry, budgeted two rounds
  because the expensive discovery had already been paid for.
- The change that moved this loop off the main thread did not come back clean after three
  rounds either.

**That was the case against 3, not for it.** One forge did meet a three-round cap, so the
objection was never that nothing meets it. It was that the two forges with anything hard to do
both hit three rounds with blocking findings still arriving, and a cap that binds exactly when
the work is hard guarantees that anything hard ships narrowed.

**Ten forges later the failure had moved.** Median wall clock across the ten closed forges was
3.3 hours and four of the ten failed; rounds 3 and beyond accounted for roughly 60% of that
wall clock, and three of the ten simply ran past an advisory cap that refused nothing
(`notes/2026-09-02-audit-and-replan.md`). A budget nothing enforces is a suggestion, and the
answer is not a bigger number: it is a small one that a third round has to be *earned* past.
Round 2 is granted unconditionally, because one round is one data point and no trajectory can
be read off it. A third is granted only on a strictly falling blocking count, or once per
forge on a narrowing, and never more than twice — so the loop terminates at 4 rounds whatever
the counts do.

What arrives late is the argument. Two examples, written up in
`notes/2026-08-25-forging-session.md`: a rule that would have deleted Linus's rationale for
eight-character indentation from Linux's `coding-style.rst`, and a contamination that
survived two relocations — round 5 removed a pre-stated verdict from a `SKILL.md`, round 6
found the same measurement pinned in that skill's `sources/EVIDENCE.md`.

## What would settle it

Rounds-to-clean recorded per forge, which the ledger can carry but does not yet derive
reliably: on a `done` inside budget, `rounds` equals `rounds_planned` whatever the forge
really took. The `escalate` row now records every round bought past a budget, with the
blocking counts that bought it, so the question "how often is 2 not enough?" becomes
countable rather than argued. Until that data exists, treat 2 the way the other thresholds in
this package are treated — as unvalidated.

## Raising it

The cap is chosen at step 0, before `skillforge start`, because `<total-steps>` encodes it: a
budget of `2 + 2 × rounds`, so 6 at the default and 10 at 4. A skill that is complex or
safety-critical — one carrying a scanner or a validator, or one whose failure mode is silent —
is budgeted for 4 at the start rather than escalated into it later.

Past the budget the only door is `skillforge escalate`. `--converging` exits 4 unless the last
two recorded rounds show a strictly falling `blocking`; `--narrowed "<what you cut>"` is
granted once per forge, and buys the cold round a narrowed skill owes. Either grant raises the
budget by exactly one round and writes an `escalate` ledger row. A third grant is refused.

## Reading the round record for a converging-or-not verdict

`SKILL.md` sends you here for this, so it lives here rather than in the body.

**The record has to exist before it can be read, and the CLI now reads it too.** One line per
round lands in `~/.claude/skill-compounder/rounds/<forge>.tsv`, written by `skillforge round`
in the tab-separated format the protocol used to write by hand:

```
<n>	blocking=<k>	total=<m>	subsystems=<what they named>	shapes=<the finding shapes>
```

That file is what the cap is enforced against: `skillforge round` counts the rows, compares
them with the rounds the budget planned, and `skillforge escalate --converging` reads the
`blocking` column of the last two. A judgement held only in context is gone at the first
compaction, which is why it was on disk before anything read it.

`blocking` is the dispatching session's classification, not D's. D is asked for findings, not
severities, and each round is a different agent with its own vocabulary; asking strangers to
agree on a scale produces a number that means nothing across rounds. **Read each report and
decide which findings block**, using one test: would shipping with this defect present make
the skill do the wrong thing for a stranger? That keeps the scale in one head across the loop.

### The two verdicts

**Converging** — `blocking` trending down AND successive rounds naming *different*
subsystems. A long procedure has many independent surfaces, and a cold reviewer executing it
end to end hits whatever it reaches first, so a falling count over changing subjects is
discovery being used up. Continue at full scope, and buy the next round with
`skillforge escalate --converging`, which grants it only on a strictly falling count.

**Not converging** — any one of:

- `blocking` flat or rising from one round to the next;
- one subsystem named by the blocking findings whatever gets patched;
- one finding *shape* recurring under different wordings — the strongest signal of the three,
  because it says the mechanism cannot be made complete rather than that a case was missed.

### Neither

A trajectory matching neither definition — a count that falls then flattens, or falls while
naming a subsystem already seen — is **treated as not converging**, and the reason is
asymmetry rather than caution. Reading it as converging costs another round on a design that
may be wrong; reading it as not converging costs a scope decision that can be made and
recorded and, if it turns out to have been premature, argued with on the record. The cheap
error is the one that leaves evidence.

### A worked case

`finish-task`, 2026-08-26, ten rounds — a forge that could no longer happen:

|round|1|2|3|4|5|6|7|8|9|10|
|-|-|-|-|-|-|-|-|-|-|-|
|blocking|2|3|1|2|1|1|2|2|3|4|

Flat then rising across the last four, which is the first signal. What settled it was the
third: `counterexample to a stated LIMIT` recurred in four separate rounds against four
different counterexamples — a git-ignored file the suite read, a symlinked directory,
`.gitattributes` clean filters, and earlier permission-bit and submodule cases. Each round the
limits paragraph was corrected and the next round found a new counterexample, because a
fingerprint computed outside the suite cannot enumerate what the suite read. The subsystem was
cut and its question handed to a skill that already owned it.

**The decision was still taken late.** It was available from round 7 on the first signal, and
the rounds between were spent patching a mechanism that could not be completed.

**Under the cap this file now describes, it stops at round 2.** Blocking went 2 then 3 — it
rose — so `skillforge escalate --converging` exits 4 and no third round is granted. The forge
either narrows, spending its one `--narrowed` grant on the subsystem the findings kept naming,
or it is closed with `skillforge fail`. Eight rounds of patching a mechanism that could not be
completed is the cost the cap exists to refuse.
