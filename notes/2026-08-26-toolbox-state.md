# State of the toolbox, for review

Written 2026-08-26 on branch `issue-19-close-the-gap`, four commits ahead of `origin/main`.
**Every figure here was produced by the command beside it, in this checkout, at the time of
writing.** Re-run them rather than trusting the numbers: this file is a snapshot and the tree
was still moving when it was written (see "In flight" at the end).

## What to run first, if you are reviewing this

```bash
git log --oneline origin/main..HEAD          # the four commits
git diff origin/main...HEAD --stat           # 40 files, +12657 / -313
TEST_TIMEOUT=400 ./run_tests.sh              # ~7 min; last full green run: exit 0
```

## Inventory, derived

|What|Count|Command|
|-|-|-|
|hook scripts|8|`ls hooks/*.sh \| wc -l`|
|CLIs|5|`ls bin \| wc -l`|
|skills|10|`find skills -maxdepth 2 -name SKILL.md \| wc -l`|
|test files|37|`ls tests/test_*.py \| wc -l`|
|our hook entries, installed|12 across 5 events|`jq -r '[.hooks[][] .hooks[] .command] \| map(select(test("claude-skill-compounder"))) \| length' ~/.claude/settings.json`|
|other tools' entries, untouched|2|same, with `\| not`|
|clock pins|9|`grep -rhoE '\b[A-Z][A-Z0-9_]*_NOW\b' hooks/ bin/ statusline/ skill_compounder/ \| sort -u`|

Our twelve entries, by script: `apply-gate` 1, `claim-gate` 2, `compound-improvement` 2,
`doc-gate` 1, `insight-capture` 1, `repeat-gate` 3, `skill-use` 2.

The nine clocks: `APPLY_GATE_NOW`, `CI_NOW`, `DOC_GATE_NOW`, `INSIGHT_NOW`,
`REPEAT_GATE_NOW`, `SKILL_COMPOUNDER_NOW`, `SKILL_COMPOUNDER_REVIEW_NOW`, `SKILLFORGE_NOW`,
`SKILLREPEAT_NOW`.

## What is new in this branch

### Three refusals, because reminders were measured not to work

Issue #19's own thread established it: the edit checkpoint fired at edits 12, 24 and 36 in one
session and was read past every time; 7 of 9 shipped skills never arrived on their own; and
`superpowers:verification-before-completion` had been invoked 0 times in 1,988 transcripts.
So these three refuse rather than remind.

- **`hooks/repeat-gate.sh`** + **`bin/skillrepeat`** — the issue's GitHub example, deterministic
  and with no model in it. Learns a failure signature on `PostToolUseFailure`, learns the call
  that worked instead from the next success, and **denies** the same call in a later session,
  naming the error and the plurality recovery. Denies once per session per signature, so it
  forces a decision rather than trapping anyone. Wired on three events because the thing it
  recognises is a sequence, not a moment.
- **`hooks/doc-gate.sh`** — denies a `git push` whose commits touch code and no documentation,
  naming `claim-provenance`. Its option parser resolves **last-wins**, the way git does,
  derived from about forty measured `git push --dry-run` runs. Escape hatch is read from the
  command text, never the environment, and every override is counted.
- **`hooks/apply-gate.sh`** — blocks the end of a turn that forged a skill and never applied it.

### The forge loop now ends in recorded use

`skillforge done` keeps its ledger contract exactly and additionally writes a **debt** under
`<state>/apply-pending/`. `skillforge apply --name X --outcome used|declined|failed --evidence
"<verbatim>"` discharges it with an `apply` ledger row; `skillforge pending` lists what is owed;
`bin/skillreport` reports the fifth question ("N forges closed, M never applied") and surfaces
the repeat store and the doc-gate override count.

### `skills/finish-task/` — see the section below

### The convergence doctrine in `skills/skill-compounder/SKILL.md`

Rewritten after it misled this session into a plan that would have narrowed a skill in its
final round and shipped the result. Two new pinned doctrines,
`assess-convergence-every-round` and `narrowing-restarts-the-review`, plus a round floor.

## Evidence: what was actually observed, not argued

|Claim|How it was established|
|-|-|
|the repeat gate refuses a real session|four real headless sessions sharing one state dir; sessions 2 and 3 failed `gh zzz-not-a-real-subcommand --sync`; **session 4's call never ran** and the deny named the error and the workaround learned in a different session|
|the doc gate refuses a real push|scratch repo, real bare remote, one headless session told only "Push this repository to its remote": push denied, session wrote the README, second push moved the remote `a215fe3 → 83b3e5b`|
|the apply gate refuses a real turn|it blocked **this** session's Stop, quoting the verbatim trigger `skillforge start` recorded hours earlier|
|`finish-task` routes|18 real `claude -p --model sonnet` calls: 3/3 on each must-fire prompt, 0/3 on each must-not-fire, each declining to the neighbour it names|
|skills compose 4 deep|`--output-format stream-json`, every level a real `Skill` tool call, 3/3 at depth 3 and 3/3 at depth 4|

Seven platform findings are written up in `docs/CLAUDE-CODE-BEHAVIOR.md`, two of which
**corrected earlier claims of our own**: hot reload (which works, with a lag that is not
constant, and which a subagent does not have to survive at all) and whether a deny reason's
instruction is acted on (it is, when the remediation is coherent; an arbitrary imperative is
often refused — the two earlier findings are now reconciled rather than contradictory).

## The review record, which is the substance

Every component went build → cold review → fix → **independent** cold re-verification, with a
fresh agent each time and never a fork of the author. Reproduced defects, by component:
doc-gate 10, repeat-gate + `skillrepeat` 12, `skillforge apply` 10, apply-gate + status line 5,
`skillreport` 10 — including one **pre-existing fatal**: a single well-formed non-object ledger
line made both parses raise, jq exit 5, and collapsed the entire report to "no forges recorded
yet" over a full ledger.

Two patterns worth carrying into the review:

1. **Re-verification is not optional.** `skillforge apply`'s worst defect — a failed ledger
   append that still deleted the debt and printed "recorded … The loop is closed" — was
   reported fixed and was not; the same false success arrived by two further paths. Only a
   second cold agent found that.
2. **A fix can open a hole while closing two.** The doc gate's refspec fix closed a tag-push
   and a non-ASCII-path defect and let `git push --follow-tags` escape the gate entirely. The
   reviewer that found it was the one asked to construct the *complement* of the fix.

## Known open, and deliberately so

- **The ten stale claims are still stale.** `.claude/CLAUDE.md` says "seven hook entries"
  (twelve), "only component that refuses" (three do), "four CLIs" (five), "five clocks" (nine);
  `README.md` mentions none of the three new hooks, the new CLI, or their off switches. This is
  the **held-out test** for the `finish-task` run's Phase 4, scored against a key written before
  the skill existed. A cold reviewer found them independently, which is corroboration, not a
  reason to fix them early.
- **`contribute-skill` still has no routing pin** and has never been probed — pre-existing.
- **`skillforge apply` is unrecorded.** The loop is open on purpose: recording `used` before the
  application finishes is the false completion claim this package refuses.
- The unvalidated constants (`CI_EDIT_EVERY=12`, `CI_PROMPT_COOLDOWN=1200`, the 21-hour review
  cooldown, `$0.19` a review) are untouched and still unvalidated.

## In flight when this was written

A cold reviewer found a **high-severity** defect in `hooks/repeat-gate.sh`: `norm_bash` masks
quoted literals, absolute paths and integers before hashing, so every `python3 -c "…"` collapses
onto one callkey — two sessions failing `python3 -c "import boto3"` cause a third session's
`python3 -c "print(1+1)"` to be **denied**, with the reason asserting it "has already failed in
2 earlier sessions". A gate refusing what it must not. The fix and its independent
re-verification were running when this file was written; `hooks/repeat-gate.sh`,
`bin/skillrepeat` and `tests/test_repeat_gate.py` were dirty in the tree for that reason.

**Do not read the last green suite as covering that fix.**
