# Open threads

What is actually open, as of the **2026-09-03** completion wave for issue #43 (the clock
crossed to 2026-09-04 during it), on `resume/after-v0.3.1` after `adf8a65` (tags
`v0.3.0` = `a2aa2d4`, `v0.3.1` = `b7f6a47`), with that wave's code and docs on the working
tree and not yet committed. CI is green on both platforms from `cfb2bc6`
onward, the end-to-end journey passed 17/17 on 2026-09-03 (thirteen `claude -p` calls,
150.9 s, against CLI 2.1.259; it was 12/12 on `a2aa2d4` before the mission and lesson steps
existed), and the paid review is opt-in.
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

Eleven numbers picked by judgement, none settled by data. Do not tune any of them before the
data exists.

- `CI_EDIT_EVERY=12` and `CI_PROMPT_COOLDOWN=1200` in `hooks/compound-improvement.sh`.
  **These two now have an instrument and still have no data.** `bin/skillreport` grew a
  `REMINDER CONVERSION` block in Wave 1 (`grep -n 'REMINDER CONVERSION' bin/skillreport`)
  that divides forges
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
- `REMIND_PRUNE_TTL=604800` and `REMIND_PRUNE_EVERY=25` in `hooks/remind.sh` (#33), and
  `MISSION_PRUNE_TTL=604800` and `MISSION_PRUNE_EVERY=25` in `hooks/mission.sh` (#43), which
  copied them. A week and a 1-in-25 draw are both round numbers chosen because the tree
  being swept is small and nothing depended on the answer. What would settle them is a
  measurement nobody has: how many session directories a heavy month actually leaves, and
  how long the longest live session runs — the second matters, because a session idle
  longer than the TTL can have another session's sweep reach its stamps.
- `REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS=2` in `hooks/repeat-gate.sh` (#43). This one is
  **better founded than the rest and still not validated**: the floor was picked against
  the live store's own distribution — of 231 distinct same-tool `Bash` bindings, 52 shared
  zero content tokens with their failure, 31 shared exactly one, and 11 of those shared only
  the word `echo` — but that distribution is one machine's store on one day, it grew to 241
  bindings later the same day, and nothing has measured how many of the rejected bindings
  were real recoveries. Re-run the join rather than quoting those figures back. A capped
  floor of `min(2, |fail tokens|)` was tried and rejected: it admitted exactly one more
  binding, on the word `echo`.

## Open: the per-session sweep, answered twice, and its two pairs of constants

Wave 2 shipped the reminder hook with per-session state and no sweep. `ROOT/remind/<session
id>/` (grep `hooks/remind.sh` for `SDIR`) accumulates one directory per session, holding
a cooldown stamp per reminder that fired and a claim per event, and nothing deletes any of
it. `prune_stale_state()` in `hooks/compound-improvement.sh` does not reach it: that
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

**Answered 2026-09-03 (#33): pruned on a sampled invocation.** `prune_stale_sessions()` in
`hooks/remind.sh` runs on a 1-in-`REMIND_PRUNE_EVERY` (25) draw and removes `<sid>/`
and `<sid>.seen/` whose mtime is more than `REMIND_PRUNE_TTL` (604800 s) behind `REMIND_NOW`;
the sweeping session's own pair is never removed, whatever its age, so a claim or stamp
cannot vanish from under a live session, and the sweep walks one level under `<state>/remind/`
only, so `reminders.jsonl` and the counters directory are unreachable by construction.
`hits.jsonl` is trimmed to its last `REMIND_MAX_ROWS` on the delivery path.
`tests/test_remind.py::PruneTest` builds the stale tree from real deliveries and proves a
cooldown is not re-armed in the session that sweeps; `::HitsCapTest` writes past the cap.
**`hooks/mission.sh` now carries the same sweep**, added 2026-09-03 for #43:
`prune_stale_sessions()` there is the same sweep with its own two knobs
(`MISSION_PRUNE_TTL`, `MISSION_PRUNE_EVERY`) and, since the red-team round, TWO call sites
(`grep -n prune_stale_sessions hooks/mission.sh` prints three lines, the definition and
both call sites) — the periodic `PreToolUse` arm's
not-yet-due exit, and the missing-store exit, which is the branch a project whose
history-surfer store was deleted or moved takes on every event afterwards and which would
otherwise have left its trees unswept forever. Both are exits that deliver nothing, so no
delivering event pays for a `stat` over every directory. Two copies of one procedure
now, and they are not shared code; a fix to either belongs in both. The four
`MISSION_PRUNE_*`/`REMIND_PRUNE_*` knobs and the two `CI_*` sweep knobs also gained a
magnitude guard in that round: eleven digits or more takes the default rather than
reaching `[`.
Two limits stated rather than fixed: after the first trim `hits.jsonl` carries mktemp's
`0600`; and a session idle for longer than the TTL whose `REMIND_COOLDOWN` is positive can
have its stamps swept by another session, because rewriting a stamp does not bump the
directory mtime — at the default cooldown of 0 nothing is ever rewritten. What is still
open in #33 is only the two constants, and that waits on data (see "unvalidated constants").

## Open: the user's own `~/.claude/CLAUDE.md` stanza is hand-written and the installer will not touch it

The installer writes the doctrine block between `claude-skill-compounder:doctrine:start` and
`:end` markers. `install_doctrine()` in `skill_compounder/installer.py` has four
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

## Open: level B search was measured, and declined

Level B — "has this user hit this before in another project?" — was scoped as a keyword
search over claude-history-surfer's prompt store, of the kind `surfer search "<keyword>"
--all` already runs. It was measured before it was built, and it was not built.

Two rounds, a haiku judge, 260 calls, against the live store on this machine (1453 project
directories, 7716 non-command prompts). A plain shared-content-token rule reached weighted
precision 0.55 at its best threshold, but 16 of the 17 pairs the judge called RELEVANT
matched on this user's own workflow boilerplate (`subagents`, `goal`, `ultrawork`) rather
than on content, so the number was an artifact. Round 2 restricted the rule to rare tokens
(document frequency under 1% of the store), which removes most of the artifact and does not
save the precision: **at the rare-token rule's best-behaved threshold (k>=4), level B
keyword search has a measured false-positive rate of 0.72 (n=60; precision 0.28, 95% CI
[0.19, 0.41])**. The upper bound of that interval is below 0.6, so no re-run of this rule
clears a 0.6 bar.

Method, both rounds, and the scripts are in `notes/research/level-b-search-measurement.md`
and `notes/research/level-b/`. `skills/skill-compounder/SKILL.md` carries the verdict in one
sentence beside the command, so a session reads the hits and does not act on them. What is
open is whether a different mechanism — embeddings, or the queue's own digest rather than
tokens — clears the bar; nothing here measures that, and this thread is not an argument
that it cannot.

## Open: #37 landed, and what the funnel can and cannot count yet

Event attribution ships: one lineage id, DERIVED from the digest the capture hooks already
share (`c` + 8 chars of a queue record's hash, `v` + 8 for a review verdict) and never
minted, carried through `skillinsight promote` -> `skillnote add --candidate` ->
`reminders.jsonl` -> `remind/hits.jsonl` -> `skillforge start --from` -> the ledger's
`origin`, `apply` and `verdict` rows. `bin/skillreport` grew a `FUNNEL` block that reports
each id as delivered / acted on / outcome, and its `REMINDER CONVERSION` block is now a
counted join on session and order rather than the estimate over mismatched windows it was.

Three limits, none of which a code change can lift:

- **Nothing was backfilled, and it must not be.** Every nudge, reminder and forge recorded
  before 2026-09-03 carries no id. Those rows report `UNATTRIBUTED` rather than being
  dropped, which is the honest thing to do, but it means the funnel's first weeks are mostly that
  column and no ratio taken from them means anything.
- **The join needs real usage.** A funnel over this machine's store measures this machine.
  The same limit the two hook constants have, and for the same reason: the instrument
  exists, nobody has read one against a store that is not this one.
- **A lineage can be real and still unattributed.** `--from` warns and never refuses, on the
  same reasoning as `--trigger`: a CLI that refuses gets stopped being called. So a forge
  started by hand from a candidate nobody passed `--from` for is a true gap in the chain,
  recorded as a gap, and no amount of usage closes it by itself.

## Open: what the red team found in round 1, and what was fixed

Three reviews ran against the #43 completion tree on 2026-09-03: an adversarial read of the
hooks, a live functional stress under the real config on ten `claude -p` calls, and a cold
docs-accuracy pass. The session log is
[`2026-09-03-issue43-completion-session.md`](2026-09-03-issue43-completion-session.md);
this is what is left after the fixes.

**Fixed in the same wave.** The weekly sweep in `hooks/compound-improvement.sh` was
`find "$STATE_DIR" -type f -mtime +7 -delete`, which deleted `reminders/nudges.jsonl` and
took the FUNNEL with it on any install quiet for a week; it now names the eight counter
suffixes it sweeps. `CI_PRUNE_EVERY=0` divided by zero and left the hook exiting 1 on every
event. Every session-id sanitiser let `.` and `..` through, so a payload could have made
the mission prune remove the live session's own claims or write above the state root; one
guard line now follows every one of them, pinned across all shipped scripts by
`tests/test_script_wrapping.py::IdentitySanitisationTest`. `hooks/mission.sh` left before
its prune when the surfer store was missing, so a project that lost its store was never
swept again. The FUNNEL was not a partition in two directions at once. And the lesson
gate's "earlier sessions only" guard was in the header but not in the code.

**The deny text was answered by running the escape it printed.** Two of two haiku sessions
denied by the lesson gate ran `skillrepeat dismiss` with a reason they had invented and
carried on. The refusal now names only `skillnote add --lesson`, and a `dismiss` row carries
`actor` and `session`, with only a human's lifting the gate. Open under it: nobody has
watched a *human* dismissal happen either, so the arm that lifts has been exercised only by
the suite.

**Residual: a same-tool binding can still stand on shared path tokens alone.** The
`REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS` floor of 2 does not exclude tokens that are path
components, so a failure naming `<P>/redteam-hooks/... remind ...` binds to
`sed -n <S> hooks/remind.sh` on `{remind, hooks}` and is not a fix for anything. The
candidate rule — drop a shared token occurring only inside slash-bearing words of *both*
commands — was run over the same-tool bindings in the live store of 2026-09-04: **587 rows,
254 bindings with a locatable fail row, 45 unbound (17.7%), and in 26 of those 45 the two
commands name an identical path word**, which is the strongest evidence of relatedness the
store carries. Nothing in the store labels a binding true or false, so no precision figure
can be computed from it; the cost can be, and it is a sixth of all bindings with a majority
of the sample looking correct. Rejected on that, and recorded here as a known limit. The
header of `hooks/repeat-gate.sh` carries the working; re-run the join rather than quoting
these figures, because the store grows.

**A subagent receives the mission and still answers "NOT KNOWN". Third observation.** The
`SubagentStart` context arrives — the canary is in the subagent's transcript — and the agent
still reports it does not know what the user asked for. Seen in the end-to-end journey, in
the resume-session live check, and again in this round's functional stress. Nothing here
distinguishes a delivery the agent did not read from one it read and discounted, and the
`updatedInput` channel this design declined is the obvious next probe rather than the
obvious next fix.

**A `Stop` block costs one empty assistant turn.** When `hooks/mission.sh` blocks a `Stop`,
the model produces a turn with no tool calls and nothing to say before it stops again. That
is the platform's shape, not this package's, and the block is already once per `prompt_id`;
the cost is one turn per completion claim, recorded so nobody reads it as a defect here.

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
- **`skillinsight promote --scope project` writes into the CANDIDATE's project, not the
  caller's.** The target comes from the queue record's own `project` field, out of whatever
  `SKILL_COMPOUNDER_STATE` names, so promoting from a copied queue still lands a note in the
  repository the candidate came from. That is deliberate — the finding applies where it was
  found — and the only warning is the `skillinsight: target <path>` line it prints before
  writing. A red-team run against a copied queue wrote into this checkout twice on
  2026-09-04. `--project <dir>` is the override.
- **A note id is a hash of `<scope word>|<text>`, so identical text in two projects shares
  one id.** `idof()` in `bin/skillnote` is CRC-32 plus byte length over that string, and the
  scope word is `project`, not the project's path; a ledger join by id therefore conflates
  two projects that recorded the same lesson. Not changed, deliberately: a scheme carrying
  the project would orphan every id already written into a `CLAUDE.md` line, an attachment
  directory and a ledger row.

## Open: what the CI-fix wave found and did not fix

- **Fixed 2026-09-03: `hooks/repeat-gate.sh` closes its stderr before its first exec**
  (grep for `REPEAT_GATE_STDERR`, which set to `1` leaves it attached; the line number this
  entry used to give was 333 lines out by the next wave). The mechanism was not the one
  recorded here earlier. The command text never touches an argv — it reaches `sed` by pipe
  from a builtin `printf`, and a 12-byte command died in the same band as a 600-byte one —
  so a cap on it was a dead guard and was not added. What dies is each `sed` stage's own
  100-250 byte regex argv where `jq`'s 30-byte argv fits: measured at 891800-891960 bytes of
  environment, up to seven `Argument list too long` lines per call, and the payload `cat` at
  the 892000 ceiling. `tests/test_repeat_gate.py::ExecNoiseTest` binary-searches the ceiling
  and drives the real hook at one environment size with the knob off and on; both new tests
  fail against the old script. `--norm-of` was byte-identical over all 435 live store rows.
- **Closed 2026-09-03: the 19 shellcheck findings are gone and the CI floor is `warning`.**
  Each was fixed or given a one-line `# shellcheck disable=` with its reason on the line;
  shellcheck 0.11.0 prints nothing over `hooks/*.sh bin/* statusline/*.sh install.sh
  uninstall.sh` at any severity. The job stops at `warning` rather than `style` because apt
  and brew ship different versions and a note-level check added upstream must not turn it
  red alone. `install.sh` and `uninstall.sh`, which were outside the job's globs, are now in
  both the smoke step and the lint step.
- **`hooks/doc-gate.sh` may carry the same argv shape and nobody has measured it.**
  The override row's file list goes in as `--arg files "$(cat "$TMP/code.txt")"` — grep for
  `--arg files`, not for a line number — and
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
- **#34: two forges have now run under the diet, and both failed at the cap.** This entry
  used to read "no forge has run under the diet ... nothing has measured whether the diet's
  round budget holds." That is answered, on 2026-09-05, by `watch-ci-run` and by its
  re-forge `wait-for-ci` — see the section below for what they exercised, what they did
  not, and why the candidate itself turned out to be a note rather than a skill.

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

## Open: #34 is answered by two forges that FAILED, so half of the diet is still unexercised

`watch-ci-run` is the first forge run end to end under the diet. It ran from `start` at
epoch 1788579995 (2026-09-04 23:46:35 EDT) to `fail` at 1788614898 (2026-09-05 09:28:18
EDT) and closed at the hard cap without shipping a skill. Everything below is re-derivable
from `<state>/rounds/watch-ci-run.tsv`, the ledger
(`grep '"name":"watch-ci-run"' <state>/ledger.jsonl | jq -c '{ts,event,steps,rounds}'` —
anchor on the name, because a bare `grep watch-ci-run` also matches the second forge's
`start` and `fail` rows, whose summaries name the forge they re-forge) and
`<state>/quarantine/watch-ci-run-2026-09-05/WHY-ARCHIVED.md`.

The four rounds went `blocking=6` of 13, `6` of 13, `5` of 13, `7` of 21. `escalate
--converging` was refused after round 2 at exit 4 (6 → 6 is not a fall), `--narrowed` was
granted in its place, `--converging` was granted after round 3 on the strict fall 6 → 5,
and after round 4 both spellings were refused because two grants is the ceiling. The
ledger carries exactly two `escalate` rows for the name. Timing, and it is worth reading
with the caveat: 581.7 minutes elapsed, inside which seven gaps run over ten minutes and
the widest of them, 400.8 minutes (2026-09-05 01:10 to 07:51 EDT), is the monthly spend
limit that killed reviewer D2 mid-round, leaving about 181 minutes active. That is against a 30-minute expectation for a narrow skill — but
this forge escalated twice and ran four rounds, so it never attempted the shape that
expectation describes. `docs/measurement.md` carries the figures and the three reasons
they are not a budget measurement.

**What is now exercised by a real forge rather than by tests alone:** the round cap; both
escalation spellings, granted and refused; the refusal after two grants; closing with
`skillforge fail`; `apply` refusing a forge that produced nothing; and the quarantine, with
a `WHY-ARCHIVED.md` keeping the orchestrator's, the builder's and four cold reviewers'
sections unmerged where they disagree.

**What is NOT exercised, as of this writing:** `skillforge done` followed by `apply` and
`verdict` on a forge that SUCCEEDS. Nothing here has walked that path with a real skill at
the end of it, and it is the half of the loop the ledger's five questions are built around.
The one defect this forge did expose there was found by inspection afterwards rather than
by the cap: `verdict` accepted a row, silently and at exit 0, for a skill that was never
installed. `a06d49c` is the repair — exit 5 when the newest close row is a `fail`, not
liftable by `--force` — and it is tested but has still never run at the end of a successful
forge.

**The second forge, `wait-for-ci`, failed the same way, four minutes after the first one
closed.** It was scoped as exactly the re-forge the first orchestrator asked for: start
from `gh api repos/O/R/commits/<sha>/check-runs`, and compute no verdict of its own. It
ran from `start` at epoch 1788615163 (2026-09-05 09:32:43 EDT) to `fail` at 1788621602
(11:20:02 EDT), and the `fail` row carries the span itself — `duration` 6438 seconds,
**107.3 minutes**, where its `WHY-ARCHIVED.md` says 108 off the wall clock. Three rounds,
three cold readers, none a fork of the orchestrator or of each other, at `blocking=7` of
10, `5` of 9 and `7` of 8 (`cat <state>/rounds/wait-for-ci.tsv`). `escalate --converging`
was GRANTED after round 2 on the strict fall 7 → 5 and REFUSED after round 3 because
5 → 7 is not a fall; the ledger carries exactly one `escalate` row for the name, a refusal
writing none. `--narrowed`, the second grant, was still in hand and was deliberately NOT
spent, and that decision is the finding rather than a shortfall: a narrowing cuts the
subsystem the findings keep naming, and here that subsystem was the deliverable. Closed
with `skillforge fail`, `steps` 6 → 8, no `apply` and no `verdict`, quarantined at
`<state>/quarantine/wait-for-ci-2026-09-05/` with the orchestrator's, the builder's and
three cold reviewers' sections appended unmerged.

**Both forges died in one subsystem, reached from two different endpoints: which checks
count as this commit's CI.** The second forge's three wrong answers were each measured by
a different cold reader against real public repositories. Check-runs plus the combined
status endpoint gave a FALSE GREEN on `cli/cli` `aa72d77c`, where three workflow runs
concluded `failure` but each died before creating a job, so none produced a check-run.
Adding `check-suites` gave a FALSE FAILING on `BurntSushi/ripgrep` main tip `3fce3b5b` —
exit 1, `VERDICT: FAILING (9 of 759)`, the 9 rows being two SCHEDULED re-runs of that same
sha from 2026-08-07 and 2026-08-18. And the runless-suite rule written to bound THAT gave
a third wrong answer in the first direction again, a FALSE GREEN on `home-assistant/core`
`49b9cef7`. Each round's repair of the subsystem produced the next round's finding inside
it, and the blocking count then rose — which is the doctrine's not-converging shape, for
the second forge running.

**What the pair now establishes, beyond what the first one did alone.** The round cap,
both escalation spellings in both directions, closing with `skillforge fail` and the
quarantine have been exercised by a real forge TWICE, on two different escalation paths:
the first spent `--narrowed` and then `--converging` and hit the two-grant ceiling, the
second was granted `--converging` once, refused it once, and left the second grant unspent
by choice. A refusal leaves no ledger row either time, so the count of `escalate` rows is
grants and not attempts — two for `watch-ci-run`, one for `wait-for-ci`.

**What is still NOT exercised, after two forges rather than one:** `skillforge done`
followed by `apply` and `verdict` on a forge that SUCCEEDS. That is unchanged and it is
the half of the loop the ledger's five questions are built around; two failures do not
approach it.

**The tier gate's answer, which is the thing to carry forward.** Two forges, seven
cold-reader rounds and both endpoints later, every blocking finding that closed either one
sat in the same subsystem — so what the evidence supports is not a third design of that
subsystem but the tier rule's own verdict: a candidate whose blocking findings sit in one
subsystem across two forges is a note with a script attached, not a skill. That is what it
became, at the user level rather than in this repo, on 2026-09-05: `skillnote add
--attach` wrote note `n3725829701x412` into the global `~/.claude/CLAUDE.md` with
`~/.claude/lessons/n3725829701x412/ci-checks.sh` beside it — a script that verifies the
push with `git ls-remote`, expands the sha to 40 characters and prints the check-runs and
statuses, computing no verdict at all. Confirm it with `grep -n 'ci-checks.sh'
~/.claude/CLAUDE.md`, not from this line; a second note, `n1566376988x302`, carries the
full-sha rule and the empty-`statuses` `pending` beside it. A third forge of this candidate needs a change of
QUESTION, not a fourth inclusion rule — ask the repository which checks it treats as
authoritative — and until someone has that, there is nothing here for the forge to do.

**Open, and it belongs to `skillreport`: a cold reviewer's routing probe writes `use` rows
for a skill that was never installed.** Every round runs the six trigger-precision prompts
through real `claude -p` sessions, and each draw that fires the draft records a `use` row
against the candidate's name. So both quarantined forges appear in
`bash bin/skillreport skills 2>/dev/null` as a name with uses and nothing to account for
them:

```
wait-for-ci
  origin    NO ORIGIN ROW — this skill has rows here but nothing says where it came from
  uses      0 genuine, 11 harness (a script drove the session)
  applied   NOT APPLICABLE — the forge for this name was abandoned (fail 2026-09-05), so no skill shipped and there is no debt to discharge
  verdict   none recorded
```

`watch-ci-run` prints the same shape with 17 harness uses and one `MISFIRED` verdict.
Three of those four lines are right and one is misleading. The `harness` column is honest — the
rows are marked as script-driven, and `0 genuine` is the true count — and `applied` names
the abandoned forge. But `NO ORIGIN ROW` reads as a hole in the ledger when it is the
fact: nothing was ever installed under either name, so no `origin` row could exist. A
probe of a DRAFT is not a use of a SKILL, and nothing in the ledger distinguishes them
today. Whether the repair is a distinct event name, a flag on the `use` row, or `skills`
reading the newest close row before it reports the name at all is undecided. Do not fix it
by suppressing the rows: they are the only surviving evidence that the routing gate was
run at all.

**The fact the next forge should build on, measured by the FIRST of the two and recorded
in its `WHY-ARCHIVED.md`:** `gh run list --commit <sha>` works with a **full 40-character sha**
and returns **zero rows at exit 0** for a short one — so expand the sha locally before
passing it. The global note `n1407736601x223` says only that `--commit` "returned nothing
here", which reads as the flag being broken; it is not broken, it is exact-match, and a
watcher built on a short sha fails open and silently. The same file records three more:
`git rev-parse origin/<branch>` fails open in three separate ways, a foreground poll loop
dies at SIGTERM with exit 143 and no verdict, and `git ls-remote` is the check that cannot
be stale. None of these depends on the broken part of the artifact.
The second forge's `WHY-ARCHIVED.md` carries nine more of the same kind under **What is
worth keeping**, none of them touching the broken part either — among them that the
combined status endpoint answers `"state": "pending"` with an EMPTY `statuses` array for a
commit that has no statuses at all, so a poller trusting `.state` waits forever on a commit
with nothing to wait for.

The design error that closed the forge was the endpoint, not the wording: three consecutive
rounds found the verdict-selection subsystem, and round 4 showed that `gh run list` answers
"which workflow runs have this sha as their head" while the question is "did CI pass for
this commit", which `gh api repos/O/R/commits/<sha>/check-runs` answers directly. The
artifact must not be installed from the quarantine.

## Open: a headless session cannot apply an edit under `.claude/skills`, so skill-authoring stops at the draft

Observed 2026-09-05 while driving `skill-authoring` with a real `claude -p --model sonnet
--permission-mode acceptEdits` session in a scratch project: Gate A ran and failed on the
planted unquoted colon, the prior-art sweep ran, the corrected description was drafted
(double-quoted, 439 characters, both halves), and the `Edit` into
`<project>/.claude/skills/pdf-extract/SKILL.md` was refused twice with "requested
permissions to write to ...", including after a scratch `settings.local.json` granted the
path. So Gate A was never re-run on the written file, and the skill's "do not report done
until the gate passes" sentence cannot be satisfied headlessly. Nothing in this repo is
wrong; the limit is the platform's permission layer treating `.claude/skills/**` as
protected in headless mode, the same layer that refused `claude --version` inside a
dispatched forge (the stage-2 thread above). It belongs in `docs/CLAUDE-CODE-BEHAVIOR.md`
once it is measured on purpose: n=1 skill, one CLI version (2.1.260), one permission mode;
the measurement is a `claude -p` with `--allowedTools 'Edit(<path>)'` spelled three ways and
the transcript read for the refusal text. The e2e journey sidesteps it by having `skillforge`
write the skill from the CLI rather than the model editing under `.claude/skills`.

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
  re-measured on 2.1.259 and is recorded in `docs/CLAUDE-CODE-BEHAVIOR.md` under
  "`PreCompact` carries seven keys", including
  the previously unconfirmed `"trigger":"auto"`; the field is `trigger`, not the documented
  `compaction_trigger`, and there is no `last_assistant_message`, so the bounded transcript
  read is mandatory rather than a fallback. Its cost, and `custom_instructions`, were both
  settled on 2026-09-03 and are the entry below. Wired on both install paths, which took the
  package to **15 hook entries over 6 events** at the time; `tests/test_precompact.py` is
  52 tests.
- **The PreCompact budget is restated per jq, and `custom_instructions` is probed** (#32,
  closed 2026-09-03). The 100 ms target was met on `/usr/bin/jq` and missed on jq-1.6, and
  the question was whether to restate the number or shed a process. Both: three process
  starts were shed — one `date` instead of two (`%n` in the format), one `mkdir -p` instead
  of two, and the per-compaction claim named by parameter expansion instead of `hash_of`,
  which cost `shasum` + `awk` + `tr` for a name nothing else reads — taking the candidate
  path from 16 programs to **13**. `ProcessCountTest` now pins 13 non-`date` programs on the
  candidate path and **4** on the empty one (`cat`, `jq`, `jq`, `tail`), with `date` bounded
  separately at 1 start on BSD and 2 on GNU and zero slack, verified by mutation.
  Re-measured n=25 interleaved, 400 KB transcript, 256 KB bound,
  macOS 25.6.0, load average 9.5, median / p90 ms:

  |jq|no candidate (before → after)|one candidate (before → after)|
  |-|-|-|
  |`/usr/bin/jq` (jq-1.7.1-apple)|33.8/38.7 → 31.8/36.0|104.2/113.3 → 84.7/87.7|
  |anaconda's jq-1.6|61.9/64.3 → 59.1/63.5|143.5/154.6 → 123.0/128.9|

  **jq-1.6 cannot be made to fit 100 ms**: its no-candidate path alone is 59 ms. Shedding
  `git rev-parse` as well measured 106 ms, and the bash `.git` walk-up that would replace it
  disagrees with `--show-toplevel` on symlinked paths, which on macOS is all of `/tmp`. So
  the budget is stated per jq: 100 ms holds for the system jq at p90; 1.6 is about 125 ms.
  There is no Homebrew jq on this machine, so those two builds are the whole comparison.
  `hash_of`, both `scan(` lines and `normalise` were re-verified byte-identical to
  `hooks/insight-capture.sh`, which was not touched. And `custom_instructions` **is**
  populated: on Claude Code 2.1.260, `/compact focus on the greeting` put `focus on the
  greeting` in it verbatim with no prefix, and a bare `/compact` left it null. The hook
  ignores the field and should — its only return channel is `systemMessage` and it never
  writes one. Both probes answered "Not enough messages to compact." and the hook fired
  anyway, so it pays its cost on compactions that never happen.
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
  exit 3 and records nothing (`grep -n 'round cap reached' bin/skillforge`), and
  `skillforge escalate` is the only
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
- **A throwaway `CLAUDE_CONFIG_DIR` cannot authenticate on this box, re-verified
  2026-09-03 on 2.1.260** (#42). `CLAUDE_CONFIG_DIR=$(mktemp -d) claude -p hi` answers
  `Not logged in · Please run /login` and exits 0, and neither `ANTHROPIC_API_KEY` nor
  `CLAUDE_CODE_OAUTH_TOKEN` is in this shell's environment. That is the mechanism behind the
  e2e report's stated limit — sessions there run on ambient credentials with `--settings`
  plus `--setting-sources ''` — and behind stage-2 auto-forge being unable to run
  `claude --version`. It is a property of how this box is logged in, not of the code, so a
  machine holding an API key in its environment will see something else.
- **How to check this box.** `skillforge doctor` is the whole check, one line per item and
  exit 1 on any FAIL. The branch above is reproducible without touching live state: write
  `36` and 900 `x` bytes into `<dir>/reminders/<id>.edits` and run
  `SKILL_COMPOUNDER_STATE=<dir> skillforge doctor`.
