# Open threads

What is actually open, as of **2026-09-03**, at commit `c9803bc` on `main` (tag `v0.3.0` is
`a2aa2d4`, one install.sh fix behind it). CI is green on both platforms from `cfb2bc6`
onward, the end-to-end journey passed 12/12 on `a2aa2d4`, and the paid review is opt-in.
Issue #31 carries the status table; this file carries the threads behind it.

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
- **All twelve shipped skills now carry a routing pin at the floor** (`grep -l routing-pin
  skills/*/SKILL.md` returns 12, and every one records `runs: 3`). The gap recorded here
  earlier — `contribute-skill` unpinned and never probed, and seven pins carrying single
  passes from 2026-08-25 — is closed.
- **Six of the twelve say `partial`, not `verified`**: `ai-tell-audit`,
  `claim-provenance`, `dead-guard-detection`, `destructive-op-preflight`, `finish-task` and
  `skill-compounder` each read `partial 8/9 must-fire draws, 9/9 must-not-fire draws`. Half
  the pool losing exactly one must-fire draw out of nine is the finding, not six separate
  ones, and it is the same shape as the 9/9-then-8/9-then-9/9 result above. Re-derive the
  split before acting on it (`grep -ho '^result: [a-z]*' skills/*/SKILL.md | sort | uniq -c`
  answers `6 partial`, `6 verified`);
  nothing here is a reason to edit six descriptions.
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

Six numbers picked by judgement, none settled by data. Do not tune any of them before the
data exists.

- `CI_EDIT_EVERY=12` and `CI_PROMPT_COOLDOWN=1200` in `hooks/compound-improvement.sh`.
  **These two now have an instrument and still have no data.** `bin/skillreport` grew a
  `REMINDER CONVERSION` block in Wave 1 (`bin/skillreport:1364`) that divides forges
  started, all time, by the checkpoints the on-disk edit counters imply at the current
  `CI_EDIT_EVERY`; it prints its own caveat, because the numerator covers all time and the
  denominator only the last seven days, so it is a loose upper bound rather than a rate.
  What is missing is the same thing as before: real usage across several repositories over
  real time. Having an instrument is not the same as having read one, and neither number
  should move until `skillreport` has been run against a store that is not this machine's.
- `REMIND_MAX=2` and `REMIND_COOLDOWN=0` (once per session) in `hooks/remind.sh`, added in
  Wave 2. Both are guesses of exactly the same kind as the two above, made the same way and
  with less behind them: the reminder store had existed for hours when they were chosen.
  Nothing has measured whether two reminders per event is one too many, or whether a
  reminder a session ignored once should get a second chance later in the same session.
  `bin/skillreport`'s conversion block counts checkpoints, not reminder deliveries, so it
  does not answer these; the hit log under `<state>/remind/` is where an answer would come
  from.
- `REVIEW_COOLDOWN=75600` (21h) in `hooks/session-review.sh`. The reasoning in that file's
  header is sound — 24h *ratchets* against someone who works the same hours daily — but the
  resulting 1.7 dispatches/week is arithmetic, not observation.
- `$0.19` per stage-1 review, measured once on 2026-08-25 over a 60 KB digest on sonnet.
  Every weekly-cost figure in that header, and in the README, multiplies one observation.

## Open: `hooks/remind.sh` never prunes its own claim and stamp tree

Wave 2 shipped the reminder hook with per-session state and no sweep. `ROOT/remind/<session
id>/` (`hooks/remind.sh:144`, `:224`, `:419`) accumulates one directory per session, holding
a cooldown stamp per reminder that fired and a claim per event, and nothing deletes any of
it. `hooks/compound-improvement.sh:148`'s `prune_stale_state()` does not reach it: that
sweep walks `<state>/reminders/`, a **different** directory whose near-collision with
`reminders.jsonl` is deliberate and pinned by `tests/test_hook.py`, precisely so the sweep
cannot touch the store.

```bash
ls ~/.claude/skill-compounder/remind/ | wc -l
```

Nothing is broken yet and the growth is small — a few files per session — so this is a
decision rather than a defect: prune on age the way the counters are pruned, prune on a
sampled invocation the way the status-line cache is, or leave it and say so. The trap to
avoid if it is pruned is the one `hooks/session-review.sh` shipped: a claim taken before the
action is really going to happen can never be retried. Record the answer here.

## Open: the user's own `~/.claude/CLAUDE.md` stanza is hand-written and the installer will not touch it

The installer writes the doctrine block between `claude-skill-compounder:doctrine:start` and
`:end` markers. `install_doctrine()` (`skill_compounder/installer.py:400`) has four
outcomes, and `user-owned` is the one that applies here: a `CLAUDE.md` already carrying a
`## Compound Improvement` section written by hand has no markers, and writing the block
anyway would give the reader the doctrine twice, so **nothing is written**. That is correct
behaviour and it is also why Wave 3's rewrite of the protocol did not reach the stanza in
the global file.

`skill_compounder/installer.py`'s `DOCTRINE_TEXT` is what the current protocol says;
`skills/skill-compounder/SKILL.md` and `README.md` are its other two mirrors, and
`tests/test_doctrine_sync.py` keeps those three in step. The global stanza is a fourth copy
that no test can see and no installer will correct. **It has to be updated by hand**, or
deleted so that the next install writes the current text into it. Until one of those
happens, a session reading the global file is being told an older protocol than the one the
skill carries — the three-tier split, the cheap branch, and the round cap are all missing
from it.

## Open: the PreCompact 100 ms target holds on one jq and is unmeasured on the other

`hooks/precompact.sh` ships against issue #8's 100 ms budget and **meets it on
`/usr/bin/jq` only**. Medians over 15 runs against a 5 MB transcript, macOS 25.6.0,
2026-09-02, at the default 256 KB bound:

|jq|no candidate|one candidate|
|-|-|-|
|`/usr/bin/jq` (jq-1.7.1-apple)|27.4 ms|86.3 ms|
|anaconda's jq-1.6|62.4 ms|147.9 ms|

The gap is process starts, not bytes: `jq -n 1` medians 9.6 ms as the system jq and 22.4 ms
as jq-1.6, and this hook runs several programs. So a user whose `PATH` resolves `jq` to a
slow build is over budget on the candidate path, by 48 ms. It is still 0.1% of the
128-second median compaction the hook delays, which is why it shipped rather than blocking;
what is unresolved is whether the 100 ms number should be restated as a system-jq figure or
the hook should shed a process. `tests/test_precompact.py::ProcessCountTest` pins the
process count, so shedding one is a testable change rather than a stopwatch argument.

Second, unrelated gap in the same measurement: **`custom_instructions` has only ever been
observed `null`**. Every probe recorded it empty (docs/CLAUDE-CODE-BEHAVIOR.md:510), so the
populated shape — whether it is a string, and what a `/compact <instructions>` invocation
puts in it — is unprobed. Nothing in `hooks/precompact.sh` reads the field, so this costs
nothing today; it is a gap in the platform record, and the probe is one `/compact` with an
argument against a payload dump.

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

## Open: one installed skill still exists in exactly one place, and it is not a repository

Two of the three are now in this repository. `skills/` holds twelve directories, and
`dead-guard-detection` and `parallel-agents-one-codebase` are among them, both promoted on
2026-09-01 and both re-probed after promotion rather than arriving with a transcribed pin —
`parallel-agents-one-codebase`'s description had to be cut from 780 characters to 489 to
meet the cap, which invalidated the pin it came with, and its result line says so.

**`speckit-execute` is the one left.** It is a real directory under `~/.claude/skills`, it
appears nowhere else on disk, and `~/.claude` is not a git repository:

```bash
for d in ~/.claude/skills/*/; do [ -L "${d%/}" ] || basename "$d"; done
git -C ~/.claude rev-parse --is-inside-work-tree    # fatal: not a git repository
```

One `rm -rf` loses it, no test in this repository reads it, and nothing is scheduled to
re-run its pin. Moving it here is **not** a tidy-up: `main` is public, so importing someone's
personal skill is a publication decision, and unlike the other two it was not forged by this
package. The decision is the owner's; the risk is recorded here so it is not discovered by
losing it.

## Open: a dispatched orchestrator does not survive the host sleeping

Established by losing one. A forge orchestrator was killed by clamshell sleep on
2026-08-28 and its record sat `active` for three and a half days
(`notes/2026-08-31-stuck-forge-audit.md`, `docs/CLAUDE-CODE-BEHAVIOR.md`). `caffeinate`
does not prevent it and one was running at the time.

What is fixed: the staleness is now reported rather than only computed, by an `IDLE` column
and a `!` in `skillforge list`, and the refusal that used to advise `skillforge done` —
which would have recorded the dead forge as completed — now advises `fail` or `clear`.

Also fixed, in Wave 1: the ledger half. A forge idle past `SKILLFORGE_ACTIVE_TTL` (21600s,
idle time since its last `step`) is reported WARN by `skillforge doctor`, closed by
`skillforge reap` with an appended `fail` row naming the TTL, and reaped by `skillforge
start` on the same name rather than refusing it. So a dead forge no longer counts as never
closed out and no longer holds its name. `tests/test_forge_staleness.py` and
`tests/test_doctor.py` cover it.

What is **not** fixed, and is the open part: nothing resumes a forge, and nothing notices
on its own — `doctor` and `reap` are both commands somebody has to run. The mitigation in
use is that briefs and round records go to disk at the moment they are decided, which is
what made the second attempt cheap. A forge whose orchestrator dies still costs its rounds.

## Open: the `PostToolUseFailure` and `Skill` arms have never been exercised in the wild

`hooks/skill-use.sh` and `hooks/repeat-gate.sh` are both wired on `PostToolUseFailure`, and
the repeat gate's matcher is `Bash\|Skill`. Every `use` row in the ledger carries
`ok:true`, so the failure arm of the skill path has never fired on a real event — only in
tests. Re-derive it rather than quoting a total, because the ledger grows: it was 773 rows
when `notes/2026-09-02-audit-and-replan.md` measured it and 876 the same day.

```bash
jq -r 'select(.event=="use") | (.ok|tostring)' ~/.claude/skill-compounder/ledger.jsonl \
  | sort | uniq -c
```

Two things follow: no live evidence that a failing `Skill` invocation is
delivered as `PostToolUseFailure` at all (the platform finding in
`docs/CLAUDE-CODE-BEHAVIOR.md` records a Skill failure that was *not* delivered), and no
live evidence that the gate's learned signature for a `Skill` call is ever populated. Do
not quote either arm as working until a real failure lands in the ledger.

## Open: the reminder-to-invocation conversion baseline is 10.5%, and that is the baseline

Issue #30. Measured across 1456 transcripts, all projects: 866 sessions were nudged, 96
invoked `skill-compounder`, 91 did both — 10.5%. In this repository alone, 249 nudges
produced 3 invocations. The measurement is in `notes/2026-09-02-audit-and-replan.md`.

This is a baseline, not a verdict: nothing has been changed against it yet, and a nudge a
session correctly ignores is a correct outcome, so the ceiling is unknown and 100% would be
wrong. What is open is what the number should be compared against, and re-running it after
Wave 2 lands so the two are measured the same way.

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

## Open: what the CI-fix wave found and did not fix

- **`hooks/repeat-gate.sh:553` dies `E2BIG` at about 890 KB of hook environment.**
  `norm_bash`'s first `sed` is the hook's first `exec`, and `execve` counts the
  environment as well as the argument vector, so in a narrow band just under the padding
  at which the hook cannot be launched at all it launches and that `sed` cannot: bash
  writes `/usr/bin/sed: Argument list too long` to the hook's stderr, which the hook does
  not redirect and cannot suppress. **Measured at 891800 bytes of environment**, one unit
  under the launch ceiling, while calibrating the deny-emit test in
  `tests/test_repeat_gate.py` (`_probe_the_real_hook`, the `noisy` band). The exit status
  was 0 at every padding — no turn was broken — so it was classified and stepped over
  rather than repaired. The fix is to stop making a fresh `exec` of the whole `sed`
  pipeline per call: bound what `norm_bash` hands out, or do the normalisation without
  spawning under a large environment.
- **19 shellcheck findings at warning/style.** Zero at `--severity=error`, which is where
  the CI job's floor sits; the 19 are the ones left after the three codes `.shellcheckrc`
  disables with reasons. Both counts and the path to raising the floor are in the "Lint
  every shell script" step of `.github/workflows/ci.yml` and in `.shellcheckrc`'s
  comments; re-derive with
  `shellcheck -f gcc hooks/*.sh bin/* statusline/*.sh | grep -oE 'SC[0-9]+' | sort | uniq -c`.
  **`install.sh` is not in that job's file list**, and it is now a script users pipe
  straight into `bash`. Linted by hand on 2026-09-02 it has 0 findings at every severity
  (`shellcheck -f gcc install.sh | wc -l` → 0), so adding it to the CI globs costs nothing
  today and stops the next edit going unchecked. `uninstall.sh` is outside it too.
- **`hooks/doc-gate.sh:966` may carry the same argv shape and nobody has measured it.**
  The override row's file list goes in as `--arg files "$(cat "$TMP/code.txt")"`, and
  `code.txt` grows with the number of changed code files across up to
  `DOC_GATE_MAX_COMMITS` (100) commits. The jq program truncates to `.[0:8]`, but that
  happens *after* the exec, so the truncation does not bound the argument. On Linux that
  is one argv element against `MAX_ARG_STRLEN` (131072 bytes) — the same shape
  `hooks/apply-gate.sh` was just fixed for. **Unmeasured**: no run has been observed
  failing, and the ceiling is roughly two thousand paths, which no commit range here has
  reached. Check it before assuming it is fine, and the fix is the one now written up in
  `docs/DESIGN.md`'s portability section — `--rawfile` against `$TMP/code.txt`, which is
  already on disk. Note the comment above that call says `--arg` is used to stay off
  jq 1.6; `--rawfile` there would move this file onto the 1.6 floor the rest of the
  package already sits on, so the two decisions have to be made together.
- **#34: no forge has run under the diet.** The rewritten protocol has never been
  executed end to end by a real forge, so nothing has measured whether the diet's round
  budget holds.

**CI green-ness is unverified until the push.** Everything above was fixed against
GNU-shaped shims and a local run on macOS. No Ubuntu runner has seen this tree. Do not
record CI as green on the strength of the local suite; read the run.

Next after this: **#39**, the paid session review's default (it is on by default and
spends money, and stage 2 cannot finish its own gate — see above), then **#40**, the docs
split. #39 landed on 2026-09-03 (the review ships off, and `install.sh --enable-review`
is the explicit opt-in). #40 landed the same day: `README.md` is the front door and
`docs/architecture.md`, `docs/operations.md`, `docs/measurement.md` and
`docs/development.md` carry what it used to. The one thing to know before editing any of
them is that the doctrine anchors moved to `docs/architecture.md`, which
`tests/test_doctrine_sync.py` now reads as `PROTOCOL_DOC`.

## Closed

Kept as one line each so a returning session does not reopen them.

- **End-to-end certification the way a user meets it is done** (the "Still wanted" entry
  that stood here, and issue #36). `tests/e2e/journey.py` walks install → use → forge →
  apply → uninstall in a throwaway config, bin and state directory, with a scratch git
  project as the problem, and records the decisive line it saw at each step rather than an
  exit code. First real run 2026-09-02: **all steps PASS, 6 sonnet calls, 34.9 s**, report
  at `/tmp/skill-compounder-e2e-2026-09-02/REPORT.md`, and it found no product failures.
  The report's own summary line reads `12 PASS` — the steps are numbered 0 through 11, so
  "11 steps" (as the audit note first recorded it) is the last index, not the count.
  It is not globbed by `run_tests.sh` and must never run in CI — it spends real calls;
  `--no-model` exercises the harness for free. Operator's guide is `docs/e2e.md`. One limit
  stays and is stated in the report: a throwaway `CLAUDE_CONFIG_DIR` cannot authenticate,
  so sessions run on ambient credentials with `--settings` plus `--setting-sources ''`,
  which puts the routing measurement at project scope with n=1. The three issues this
  entry used to point at — #10, #14 and #15 — are all closed as of 2026-09-02
  (`gh issue view <n> --repo ContextLab/claude-skill-compounder --json state`), so #36 is
  the only tracker item left here and it is closable on this run.

- **`#8` PreCompact capture is built.** It was "settled design, nothing written" through
  three waves. `hooks/precompact.sh` now captures skill candidates from the transcript
  about to be summarised away and appends them to the same weekly queue
  `hooks/insight-capture.sh` writes, with `source:"precompact"`. No model call, string
  extraction only — issue #8 measured why: a `PreCompact` hook blocks compaction and has no
  default timeout, and a timeout instead kills the writer mid-write. The payload was
  re-measured on 2.1.259 and is recorded at `docs/CLAUDE-CODE-BEHAVIOR.md:510`, including
  the previously unconfirmed `"trigger":"auto"`; the field is `trigger`, not the documented
  `compaction_trigger`, and there is no `last_assistant_message`, so the bounded transcript
  read is mandatory rather than a fallback. Cost is 27 ms with no candidate and 86 ms with
  one, median, on the system jq — the jq-1.6 figures and the unprobed `custom_instructions`
  are open above. Wired on both install paths, which takes the package to **15 hook entries
  over 6 events**; `tests/test_precompact.py` is 47 tests.
- **The cheap branch has a mechanism.** `SKILL.md` used to say "write a note or update
  CLAUDE.md" and name no path, no CLI and no ledger row, so the branch was taken zero
  times. `bin/skillnote` is that path: `add`/`remove`/`list` against a marker block in a
  project or global `CLAUDE.md`, `--remind` with `--keyword`/`--path`/`--command` for the
  reminder store, and a `note` event in the ledger, so a note taken instead of a forge is
  now counted rather than invisible. The three-tier split (note / reminder / skill) is step
  0 of the rewritten protocol.
- **The insight queue is drained and no longer write-only.** It sat 57 in, 0 out, oldest
  seven days. `skillinsight promote` writes a queued candidate down through `bin/skillnote`
  and takes it out of the queue; `decline --source <src>` applies one judgement across every
  undeclined record from a source in one pass. The Wave 3 log records the live drain: 46
  `star-insight` records declined, 7 promoted to memory scope in other repositories, 2
  verdicts promoted and 1 note written into this repository's `.claude/CLAUDE.md`.
- **A CANDIDATE verdict now produces an artifact.** Five reviews had been dispatched and two
  returned `CANDIDATE`, and nothing consumed either. `hooks/session-review.sh` writes a note
  on a CANDIDATE verdict, and `skillinsight promote --verdict <session-id>` (alias
  `promote-review`) promotes one by hand; the protocol wires the verdict in at step 6, so
  the paid-for answer lands somewhere a later session reads.
- **The forge has a hard round cap.** `skillforge round` refuses at the budgeted count with
  exit 3 and records nothing (`bin/skillforge:2239`), and `skillforge escalate` is the only
  way past it: `--converging` requires blocking findings to have strictly fallen,
  `--narrowed "<what was cut>"` may be used once, and two grants is the ceiling, so four
  rounds is the most any forge can reach. The measurement behind it is that rounds 3..N of
  the builder/reviewer loop were about 60% of a median forge's wall clock and produced no
  finding that round 1 and one confirming round had not.
- **The repeat gate keeps its refusal arm, switched off** (issue #27). Driving the real hook
  against all ten signatures that had reached the threshold denied none of them, because
  every one had an allowlisted head; a synthetic non-allowlisted signature is denied, so the
  machinery works and the population that could reach it was empty. `REPEAT_GATE_REFUSE`
  defaults to `0`; the learn and recovery arms are untouched. `bin/skillrepeat` and
  `bin/skillreport` were the other half of the defect — both printed `refuses` without
  applying the head rules — and both now ask the gate through `--eligible-of` instead of
  keeping a copy.
- **The doc gate is kept, with two fixes** (issue #28). Three real refusals across three
  sessions, and all three ended in documentation written and pushed, so it is doing what it
  was built for. Fixed: the command splitter cut inside a quoted `DOC_GATE_OVERRIDE` reason
  and silently bypassed the gate, and the `^notes?/` classification that caused the only
  override in the record is now `DOC_GATE_NOTES`, defaulting to `doc` and set to `neither`
  by this repository in `.claude/settings.json`.
- **`skillcontrib` is kept, after a split review.** The first cold read said retire: 47 runs
  and zero reconnaissance against any upstream, `DEFAULT_REPO` pointing at this repository,
  and no PR ever opened anywhere. A second cold opinion said keep, on evidence the first had
  not looked for — deduplication works live, exiting 9 on a real duplicate, 61 tests pass,
  there is no misfire on record, and its precondition (a skill that has been red-teamed
  clean and then reused) only just became satisfiable. The retirement protocol needs
  independent concurrence and did not get it, so nothing was archived. Two README claims it
  exposed were corrected instead.
- **The lost session-review report.** The lazy-parse cause is written up in
  `notes/2026-08-25-first-live-review-verdict.md` and in `docs/DESIGN.md`; every shipped
  script is now wrapped in one brace group and ends in `exit`, ratcheted by
  `tests/test_script_wrapping.py` with an empty `KNOWN_UNWRAPPED`. Live confirmation
  arrived: three dispatches, in the entry below. **And the lost verdict itself is
  recoverable** — Wave 1 added `skillinsight reindex`, which reads the `.stage1-*.json` the
  dispatcher left behind and appends the row it never got, keyed for idempotence on
  `index.jsonl` rather than on a stamp of its own, deleting nothing. Session `f0feae4c` has
  been recovered: `index.jsonl` now carries its `CANDIDATE` row with
  `reindexed_at: 2026-09-02T20:07:54Z`, eight days after the call that paid for it.
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

## This machine

Operational debt on the author's box, kept apart from everything above so that a reader
does not take a local mess for a property of the code. Nothing above this heading is
machine-local; nothing below it should be read as a repo-wide defect.

- **The mixed counter file is repaired.** One session's `.edits` counter held `36` and then
  900 `x` bytes — a decimal count written by one form of the hook and appended to as a
  unary tally by the next — so neither reader could add the halves up and 936 edits were
  lost to every count that used them. `doctor` reported it rather than guessing, because
  the correct total is a judgement about which half is which. It is now 936 bytes of `x`
  and nothing else, and `skillforge doctor` reports `PASS counters` (2026-09-03:
  `tr -d x < ~/.claude/skill-compounder/reminders/f0feae4c-834a-409b-8e25-9a2894341168.edits | wc -c`
  prints 0). What stays open is the general question, and it is in the list above, not
  here: whether anything should ever write the other form again.
- **How to check this box.** `skillforge doctor` is the whole check, one line per item and
  exit 1 on any FAIL. The branch above is reproducible without touching live state: write
  `36` and 900 `x` bytes into `<dir>/reminders/<id>.edits` and run
  `SKILL_COMPOUNDER_STATE=<dir> skillforge doctor`.
