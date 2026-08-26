# Where the round cap comes from

The cap is 5 rounds, or 10 for a skill that is complex or genuinely important. Both numbers
are guesses. This file says how good a guess, so that nobody re-argues it from memory.

## It is not a measurement

The ledger cannot supply one. What it can supply is the shape of every forge recorded here,
and one command puts the whole basis in front of you:

```bash
jq -r 'select(.event != "start")
       | [.name, .event, .rounds, .rounds_planned, .phase] | @tsv' \
  ~/.claude/skill-compounder/ledger.jsonl
```

Run it before trusting the rest of this file.

## What the record showed when 5 was chosen

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

**That is the case against 3, not for it.** One forge here did meet a three-round cap, so
the honest objection is not that nothing meets it. It is that the two forges with anything
hard to do both hit three rounds with blocking findings still arriving, and a cap that binds
exactly when the work is hard guarantees that anything hard ships narrowed.

What arrives late is the argument. Two examples, written up in
`notes/2026-08-25-forging-session.md`: a rule that would have deleted Linus's rationale for
eight-character indentation from Linux's `coding-style.rst`, and a contamination that
survived two relocations — round 5 removed a pre-stated verdict from a `SKILL.md`, round 6
found the same measurement pinned in that skill's `sources/EVIDENCE.md`.

## What would settle it

Rounds-to-clean recorded per forge, which the ledger can carry but does not yet derive
reliably: on a `done` inside budget, `rounds` equals `rounds_planned` whatever the forge
really took. Until that exists, treat 5 the way the other thresholds in this package are
treated — as unvalidated.

## Raising it

The cap is chosen at step 0, before `skillforge start`, because `<total-steps>` encodes it.
Raise it deliberately and say why in the announcement, rather than discovering at round 6
that you would like more. A safety-critical skill, one carrying a scanner or a validator, or
one whose failure mode is silent, all justify 10.

## Reading the round record for a converging-or-not verdict

`SKILL.md` sends you here for this, so it lives here rather than in the body.

**The record has to exist before it can be read.** B keeps one line per round, on disk beside
the step-1 brief, because the judgement spans rounds and a judgement held only in context is
gone at the first compaction — the same reason the criteria are on disk:

```
round <n>  blocking=<k>  total=<m>  subsystems=<what the blocking findings named>
```

`blocking` is B's classification, not D's. D is asked for findings, not severities, and each
round is a different agent with its own vocabulary; asking strangers to agree on a scale
produces a number that means nothing across rounds. **B reads each report and decides which
findings block**, using one test: would shipping with this defect present make the skill do
the wrong thing for a stranger? That keeps the scale in one head across the whole loop.

### The two verdicts

**Converging** — `blocking` trending down AND successive rounds naming *different*
subsystems. A long procedure has many independent surfaces, and a cold reviewer executing it
end to end hits whatever it reaches first, so a falling count over changing subjects is
discovery being used up. Continue at full scope; overrun the cap.

**Not converging** — any one of:

- `blocking` flat or rising over **three consecutive rounds** (three data points, not three
  transitions);
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

`finish-task`, 2026-08-26, ten rounds:

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
the rounds between were spent patching a mechanism that could not be completed. Read the
record every round, not when it starts to bother you.
