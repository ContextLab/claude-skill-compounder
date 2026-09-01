# Open threads

What is actually open, as of **2026-09-01**, on `6b23dd1`. Written so nothing here depends
on a session remembering it: every entry carries the command or the path that establishes
it. Delete an entry when it is genuinely closed, not when it is merely in flight. When you
close one, compress it to a line in "Closed" with the evidence that closed it, or delete it
outright — this is a working list, not a changelog.

The GitHub issues are the other half of this picture and they do not duplicate it:
`gh issue list --repo ContextLab/claude-skill-compounder --state open` is the authority on
what is scoped as work. This file is for what is known and unresolved, including the parts
nobody has opened an issue for.

## Open: `finish-task` shipped narrowed, and what was cut is not covered

The skill went ten full-scope review rounds without converging (blocking counts
2,3,1,2,1,1,2,2,3,4) and was **narrowed** rather than shipped half-working: the tree fingerprint
and the evidence gate built on it were cut, and the question they answered — did the run I am
publishing on contain my change? — handed to `stale-artifact-check`. It reached clean in three
rounds after the cut.

What that means for anyone reading the skill: the fingerprint is gone because **a hash computed
outside a suite cannot enumerate what the suite read**, established by five separate
counterexamples in five separate rounds (a git-ignored file the suite read, a symlinked
directory, `.gitattributes` clean filters, an untracked nested git repository, and earlier
permission-bit and submodule cases). Do not reintroduce one. The reasoning is in
`~/.claude/skill-compounder/briefs/finish-task.NARROWING.md`.

## Open: routing verification is a draw, not a verdict

The routing gate was treated as pass/fail until 2026-08-26, and it is not. Three separate
three-run probes of `skill-compounder`'s own six prompts, same description, nothing edited
between them, read 9/9, then 8/9, then 9/9. The one that lost fired *nothing at all*, so it
was not a neighbouring skill winning the prompt.

What follows, and what is unfinished:

- `scripts/probe_routing_claims.py` now takes `--runs N`, default and floor 3, and folds
  each prompt into a k/N count. `k == N` is PASS; `0 < k < N` is SPLIT and is reported as a
  finding rather than retried until it goes green; a section is `verified` only when every
  prompt won every draw, and `partial` otherwise. Re-run the arithmetic rather than quoting
  a call count: it is `len(prompts_for(claims)) * runs`, so one six-prompt skill is 18 calls
  and the eight pinned skills are 48 prompts, ~144 calls, ~12 minutes at the floor.
- **Eight of the nine shipped skills carry a routing pin** (`grep -l routing-pin
  skills/*/SKILL.md`). `contribute-skill` has none, and has never been probed. That is the
  concrete gap.
- **`skill-compounder`'s own pin says `partial`**, naming the prompt that scored 8/9. It is
  the only pin recording `runs:`; the other seven still read `verified 3/3 must-fire, 3/3
  must-not-fire` from single passes on 2026-08-25 and have not been re-probed at the floor.
  Do not carry any of those seven forward as though three runs were behind them.
- Undecided: whether a `partial` pin should block a forge from being reported clean, or
  whether shipping it named-and-recorded is the honest end state. Record the answer here.

## Open: the reuse evidence is still mostly harness traffic

The one number this whole package is supposed to produce — does a forged skill get used
again — is still dominated by this repository's own tests and probes.

`skillreport`, run 2026-08-26: 4 of 5 finished forges (80%) produced a skill invoked after
the forge that created it, one forge never closed and is excluded from both halves, and
**103 invocations were excluded as harness traffic**, every one of them from a system temp
directory. The exclusion is by session entrypoint (`sdk-cli`), which is what a script
driving the session looks like, not by directory.

Two things follow, both open:

1. **The excluded traffic dwarfs the genuine.** Nothing is wrong with the instrument — it
   reports the exclusion on its own line rather than dropping it — but a ratio computed on
   four counted uses is not evidence about anything. This needs real use in other
   repositories over real time, and until then no percentage from `skillreport` should be
   quoted anywhere as a result.
2. **The forge ledger no longer sees only a third of the inventory, and that changed
   quietly.** `jq -r '.skill // .name' ~/.claude/skill-compounder/ledger.jsonl | sort -u`
   now lists 16 names, including every shipped skill plus several forged elsewhere. The
   older thread here recorded three names and asked whether `skillreport`'s blindness to
   the rest was a defect or a documented limit. The blindness is gone; the question was
   never answered, and it should be closed explicitly rather than by attrition — is the
   ledger meant to census the installed pool, or only what the forge built?

## Open: the claim gate's recall is bounded and one arm is unwired

`hooks/claim-gate.sh` ships wired on `Stop` and on `PreToolUse` with matcher `Bash`, in
both install paths. Two known limits, neither a defect to fix blind:

- **The scan window costs recall.** `CLAIM_GATE_MAX_BYTES` is `16777216`. A figure printed
  before the last 16 MiB of a session and restated at the end reads as unsupported. The
  obvious repair — searching outside the window for the candidate figures — was built and
  rejected on measurement (BSD `grep` has no fast multi-pattern path; 21.0s for four
  patterns). The `PostToolUse` accumulator arm is the path that restores full-session
  recall for Tier 1, and **it is not wired in either install path**. Whether to wire it is
  open: it costs a hook invocation on every tool call.
- **The false-positive figures are two, and only one of them generalises.** 6 of 205 (2.9%)
  on the corpus the rules were tuned against; 3 of 88 (3.4%) held out, after the 2026-08-26
  fixes and down from 8.0% before them. An independent reviewer running the same procedure
  over a different draw measured 5.7% before the fixes. Quote the held-out figure and treat
  the pair as agreeing on order of magnitude only. Both corpora are one machine's
  transcripts, so neither is a rate for anyone else.
- The gate cannot see a causal claim with no number in it — "the hook caught this", "this
  fixes the race" — and nothing in it should be stretched to try. That is a stated limit,
  not a backlog item.

## Open: unvalidated constants

Four numbers picked by judgement, none settled by data. `bin/skillreport` is the instrument
that would settle the first two, and it needs real usage across several repositories over
real time first. Do not tune any of them before that data exists.

- `CI_EDIT_EVERY=12` and `CI_PROMPT_COOLDOWN=1200` in `hooks/compound-improvement.sh`.
- `REVIEW_COOLDOWN=75600` (21h) in `hooks/session-review.sh`. The reasoning in that file's
  header is sound — 24h *ratchets* against someone who works the same hours daily — but the
  resulting 1.7 dispatches/week is arithmetic, not observation.
- `$0.19` per stage-1 review, measured once on 2026-08-25 over a 60 KB digest on sonnet.
  Every weekly-cost figure in that header, and in the README, multiplies one observation.

## Open: stage-2 auto-forge cannot finish its own gate

`SKILL_COMPOUNDER_REVIEW_FORGE` ships **off** and has never run in production. The reason is
not cost: it was measured once end to end at $3.02 / 19 minutes / two cold red-team rounds,
verdict ABANDONED. The blocker is that a dispatched forge **cannot complete its own routing
gate** — `claude --version` came back "This command requires approval" at the permission
layer, confirmed independently by a fresh subagent it sent to try. A skill is not finished
until real `claude -p` sessions route to it, so an automatic forge is structurally unable to
finish. Turning it on before that is solved means paying ~$3 a time for forges that cannot
conclude. The stochastic-routing finding above makes this worse, not better: the gate a
dispatched forge cannot run is now a gate that needs three passes.

## Open: three installed skills exist in exactly one place, and it is not a repository

`~/.claude/skills` holds 14 skills. Ten are symlinks into this checkout and one
(`history-surfer`) symlinks into another repository. **Three are real directories that
appear nowhere else on disk**, and `~/.claude` is not a git repository:

```bash
for d in ~/.claude/skills/*/; do [ -L "${d%/}" ] || basename "$d"; done
git -C ~/.claude rev-parse --is-inside-work-tree    # fatal: not a git repository
```

`dead-guard-detection` (15257 bytes), `parallel-agents-one-codebase` (12825) and
`speckit-execute` (9295). The first is the whole output of a completed five-round forge:
`skillforge ledger` carries `dead-guard-check ... done` for 2026-08-26. One `rm -rf` loses
all three, no test in this repository reads them, and their pins are dated 2026-08-28 with
nothing scheduled to re-run.

Moving them here is **not** a tidy-up. `main` is public, so importing someone's personal
skills is a publication decision, and `parallel-agents-one-codebase` carries a 780-character
description against the 500 cap, so it would fail `test_doctrine_sync.py` on arrival and its
pin would need re-measuring after the cut. The decision is the owner's; the risk is recorded
here so it is not discovered by losing them.

## Open: a dispatched orchestrator does not survive the host sleeping

Established by losing one. A forge orchestrator was killed by clamshell sleep on
2026-08-28 and its record sat `active` for three and a half days
(`notes/2026-08-31-stuck-forge-audit.md`, `docs/CLAUDE-CODE-BEHAVIOR.md`). `caffeinate`
does not prevent it and one was running at the time.

What is fixed: the staleness is now reported rather than only computed, by an `IDLE` column
and a `!` in `skillforge list`, and the refusal that used to advise `skillforge done` —
which would have recorded the dead forge as completed — now advises `fail` or `clear`.

What is **not** fixed, and is the open part: nothing resumes a forge, and nothing notices
without a person looking. The mitigation in use is that briefs and round records go to disk
at the moment they are decided, which is what made the second attempt cheap. A forge whose
orchestrator dies still costs its rounds.

## Known tree-state dependency — do not "fix" it

`tests/test_seed_claim_provenance.py::test_the_measured_sweep_figures_are_re_derived_not_restated`
runs `skills/claim-provenance/SKILL.md`'s own diff sweep with `git diff HEAD -U0` against
`skills/contribute-skill/SKILL.md`, and the skill states that sweep matched **0** lines. True
of a committed tree, false of a dirty one: while that file has uncommitted changes the sweep
matches them and the test fails.

The `0` is correct. If you find this red, check whether `skills/contribute-skill/SKILL.md` is
modified before changing any number — committing resolves it. The whole-file figure beside it
(currently 103) is a different kind of claim and does move permanently when that file grows.
Both numbers are re-derived by that test rather than pinned, so neither can be corrected by
editing the prose alone.

## Known limits, deliberately open

- **`tests/test_doctrine_sync.py` has a measured ceiling.** A cold reviewer defeated the
  verbatim-pinning guards by keeping each pinned sentence and repudiating it in the next
  clause, exit 0. Recorded as measured fact in the module docstring. The guard catches
  drift, deletion, softening and truncation; it does not catch repudiation. Do not report it
  as catching more than that.
- **`tests/test_docs_split.py` detects copying, not restating.** Its overlap check is a
  ten-word shingle intersection between the two `docs/` files. A paraphrase moved by hand
  passes it, and the docstring says so. The split is maintained by the rule, not by the test.
- **Every scope and routing measurement used `--model sonnet`.** The frontmatter findings in
  `docs/CLAUDE-CODE-BEHAVIOR.md` cover all three scopes; the model tier is a remaining limit
  stated in that file, and the same limit applies to every routing pin in `skills/`.

## Still wanted: end-to-end testing the way a user meets it

Partly addressed by `edc2f60` ("Test the package as a user meets it, and fix what that
found") and by the live routing probes, but not finished; this is issue #10. The remaining
gap: install the package into a throwaway config directory, run real `claude -p` sessions
against it, and watch the state files, the ledger and the weekly queue *while they run*,
evaluating the outputs critically rather than checking exit codes. Never against the real
`~/.claude`. Issue #14 (run the A-E pipeline end to end on a real trigger) and issue #15
(trigger each of the nine skills from a real session) are the two concrete pieces of it.

## Closed

Kept as one line each so a returning session does not reopen them.

- **The lost session-review report.** The lazy-parse cause is written up in
  `notes/2026-08-25-first-live-review-verdict.md` and in `docs/DESIGN.md`; every shipped
  script is now wrapped in one brace group and ends in `exit`, ratcheted by
  `tests/test_script_wrapping.py` with an empty `KNOWN_UNWRAPPED`. Live confirmation is
  still owed and is its own open thread above.
- **The issue-19 branch is merged and its three deliberate gaps are all closed.** The
  branch fast-forwarded `main` to `6b23dd1` on 2026-09-01 after a 39-file, 1841-test run
  in an isolated worktree. The ten counted claims were corrected in `12e44a8`; the
  repeat-gate `norm_bash` defect in `54200a0`; and `skillforge pending` now answers
  "nothing is waiting to be applied", so the apply debt is discharged rather than assumed.
- **The session review now delivers end to end.** The thread above asked for a live
  dispatch as evidence; there have been three. `reviews/index.jsonl` and both week
  directories carry 2026-08-26 `NONE`, 2026-08-28 `CANDIDATE kill-and-rerun-full-suite`
  and 2026-08-31 `NONE`, each with its cost and duration. The 2026-08-28 candidate was
  forged on 2026-09-01, which closes the loop the package exists for: hook, paid review,
  candidate, forge.
- **`bin/skillreport` counted probes as reuse.** Fixed; harness traffic is excluded by
  session entrypoint and reported on its own line.
- **The README's no-network claim.** Corrected; `## What runs against the API` now states
  plainly that `hooks/session-review.sh` bills by default, and the no-network sentence
  enumerates the components it actually covers.
- **The forging protocol is the A-E pipeline** (`d1a8f62`), replacing the numbered steps in
  `skills/skill-compounder/SKILL.md`.
- **The completion-claim gap has a mechanism** (issue #16): `hooks/claim-gate.sh`, wired on
  `Stop` and `PreToolUse` in both install paths, calibrated on a tuned and a held-out corpus.
  Its remaining limits are an open thread above.
- **`stale-artifact-check`'s organic routing** (issue #11), **`ai-tell-audit` under the body
  ceiling** (issue #12), and **the missed-fire denominator** (issue #13,
  `scripts/probe_missed_fires.py`, `tests/test_missed_fire_probe.py`).
- **Cold red-team of the protocol, the skills and the hooks** (issue #17). Three claim-gate
  defects it found are fixed in `6df980a`, two of them dead guards.
- **`claim-provenance` forge**, **the concurrent `skillforge done` race**
  (`tests/test_forge_close_race.py`), **personal-scope skill loading**, **`204acb0`'s false
  commit message**, **status-line honesty and the overrun record**, the
  **`docs/CLAUDE-CODE-BEHAVIOR.md` split**, **`skill-authoring` mutation gaps** and the
  **deterministic insight record**. Each has its evidence in `docs/`, in a test file named
  above, or in the dated notes.

## The failure that produced this file

A checkpoint hook fired at edits 12, 24 and 36 in one session and was disregarded every
time, because it asks whether "the procedure you are working through right now" is
recurring — a per-instance question, asked while absorbed in a single fix. Nine defects of
one kind were fixed in that session without the pattern being noticed. The lesson is not
"read the reminders": it is that a mechanism whose output depends on someone noticing will
fail exactly when it is most needed. Prefer mechanisms that produce their record whether or
not anyone reads anything.

The lost session review was the same failure in a new place. That mechanism *did* produce
its record without anyone noticing — and then dropped it on the floor between the model call
and the queue, while stamping the cooldown that stopped it from trying again. Producing the
record is necessary. It is not sufficient; the handoff has to be verified too, and until a
live dispatch shows one arriving, it has not been.
