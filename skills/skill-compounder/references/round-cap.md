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
