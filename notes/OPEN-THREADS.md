# Open threads

What is actually open, as of **2026-08-25**, on `41a2427`. Written so nothing here depends
on a session remembering it: every entry carries the command or the path that establishes
it. Delete an entry when it is genuinely closed, not when it is merely in flight. When you
close one, compress it to a line in "Closed" with the evidence that closed it, or delete it
outright — this is a working list, not a changelog.

## In flight right now

Agents hold these files. A suite run touching them proves nothing until they report, and a
red test in this section is not evidence of a defect.

- **`hooks/session-review.sh` lost its first real report.** Dispatched for real for the
  first time on 2026-08-25 at 21:29 and the analysis it paid for never reached the queue.
  Evidence still on disk:
  `~/.claude/skill-compounder/reviews/.stage1-f0feae4c-834a-409b-8e25-9a2894341168.json`
  holds a complete result — `is_error: false`, `total_cost_usd` 0.2221734, and a body
  beginning `VERDICT: CANDIDATE orchestrator-sendmessage-delivery-unreliable` — while
  `ls ~/.claude/skill-compounder/reviews/2026-W35/` is empty and neither `index.jsonl` nor
  `.unread` exists anywhere under `reviews/`. `.last-dispatch` **was** stamped
  (`1787707752`), so the 21h cooldown then suppressed the next run: the failure spends the
  quota and hides itself. An agent holds the file and is fixing it now. The recovered
  verdict is being written to `notes/2026-08-25-first-live-review-verdict.md` (not yet on
  disk as of this writing).
- **`bin/skillreport` counts probes as reuse.** See the next section for the measurement;
  the fix is dispatched and the file is modified in the working tree
  (`git status --porcelain` -> ` M bin/skillreport`).
- **`README.md:380` overstated the no-network claim** while `session-review.sh` dispatches a
  billable API call by default. Being repaired now by another agent. Record it as the shape
  of drift that recurs here: a true sentence about one CLI (`skillreport` really does make
  no network calls) read as a claim about the package, and nothing tested the difference.
  This is what `claim-provenance` exists for, and it did not fire on its own README.

## Open: the reuse evidence is contaminated

The one number this whole package is supposed to produce — does a forged skill get used
again — is currently unusable.

**Method** (re-derived 2026-08-25, independent of the audit that first found it): scan every
`~/.claude/projects/**/*.jsonl` for `tool_use` blocks with `name == "Skill"` whose
`input.skill` is one of the nine shipped skills, and bucket by the record's `cwd`.

**Result: 99 invocations, of which 94 came from probe and test-harness directories**
(`routing-probe-*`, `sac-probe`, `sktest-proj`, `gateproof-*`, `isolated-*`, `shadow-*`, and
scratchpad staging dirs). Five were genuine uses in a real project directory:

|skill|cwd|n|
|-|-|-|
|`claim-provenance`|`/Users/jmanning/claude-skill-compounder`|2|
|`skill-compounder`|`/Users/jmanning/claude-skill-compounder`|1|
|`skill-compounder`|`/Users/jmanning/orchestrator`|1|
|`ai-tell-audit`|`/Users/jmanning/claude-skill-compounder`|1|

Two consequences, both open:

1. **Six of the nine shipped skills have zero real-world uses**: `session-handoff`,
   `no-silent-stub`, `stale-artifact-check`, `destructive-op-preflight`, `contribute-skill`,
   `skill-authoring`. Routing is verified for all nine — live `claude -p` probes, 3/3
   must-fire and 3/3 must-not-fire, sonnet, cli 2.1.245, recorded in
   `notes/2026-08-25-issue9-fix-session.md` §6–8 — so they fire when asked. Whether they
   *help* is unmeasured. Do not report routing verification as evidence of usefulness.
2. **The forge ledger sees a third of the inventory.** `~/.claude/skill-compounder/ledger.jsonl`
   contains records for exactly three names: `ai-tell-audit`, `skill-compounder`,
   `claim-provenance`. `skill-authoring` was built by a Workflow and never entered the
   ledger; the six seed skills predate it. So `skillreport`, which joins the ledger against
   transcript invocations, is structurally blind to six of nine.
   **Undecided and needs deciding:** is that a defect to fix (backfill the ledger, or teach
   `skillreport` to enumerate `skills/` and show unledgered rows) or a documented limit
   ("this reports on what the forge built, by construction")? Record the answer here either
   way — an unstated choice will be rediscovered as a bug.

## Open: unvalidated constants

Four numbers picked by judgement, none settled by data. `bin/skillreport` is the instrument
that would settle the first two, and it needs real usage across several repositories over
real time first. Do not tune any of them before that data exists.

- `CI_EDIT_EVERY=12` and `CI_PROMPT_COOLDOWN=1200` in `hooks/compound-improvement.sh`.
- `REVIEW_COOLDOWN=75600` (21h) in `hooks/session-review.sh:155`. The reasoning in that
  file's header is sound — 24h *ratchets* against someone who works the same hours daily —
  but the resulting 1.7 dispatches/week is arithmetic, not observation.
- `$0.19` per stage-1 review (`hooks/session-review.sh:36`, measured once on 2026-08-25 over
  a 60 KB digest on sonnet). Every weekly-cost figure in that header multiplies this single
  observation.

## Open: stage-2 auto-forge cannot finish its own gate

`SKILL_COMPOUNDER_REVIEW_FORGE` ships **off** and has never run in production. The reason is
not cost: it was measured once end to end at $3.02 / 19 minutes / two cold red-team rounds,
verdict ABANDONED (`hooks/session-review.sh:44-47`). The blocker is that a dispatched forge
**cannot complete its own routing gate** — `claude --version` came back "This command
requires approval" at the permission layer, confirmed independently by a fresh subagent it
sent to try (`hooks/session-review.sh:718-724`). A skill is not finished until a real
`claude -p` session routes to it, so an automatic forge is structurally unable to finish.
Turning it on before that is solved means paying ~$3 a time for forges that cannot conclude.

## Known tree-state dependency — do not "fix" it

`tests/test_seed_claim_provenance.py::test_the_measured_sweep_figures_are_re_derived_not_restated`
(line 726) runs the skill's own diff sweep with `git diff HEAD -U0` against
`skills/ai-tell-audit/SKILL.md`, and the skill states that sweep matched **0** lines. True of
a committed tree, false of a dirty one: while that file has uncommitted changes the sweep
matches them and the test fails.

The `0` is correct. If you find this red, check whether `skills/ai-tell-audit/SKILL.md` is
modified before changing any number — committing resolves it. The whole-file figure beside
it (currently 121) is a different kind of claim and does move permanently when that file
grows.

## Known limits, deliberately open

- **`tests/test_doctrine_sync.py` has a measured ceiling.** A cold reviewer defeated the
  verbatim-pinning guards by keeping each pinned sentence and repudiating it in the next
  clause, exit 0. Recorded as measured fact in the module docstring (line 50). The guard
  catches drift, deletion, softening and truncation; it does not catch repudiation. Do not
  report it as catching more than that.
- **Every scope measurement used `--model sonnet`.** The frontmatter findings in
  `docs/CLAUDE-CODE-BEHAVIOR.md` now cover all three scopes (see Closed, below), but the
  model tier is a remaining limit stated in that file, not a closed question.

## Still wanted: end-to-end testing the way a user meets it

Partly addressed by `edc2f60` ("Test the package as a user meets it, and fix what that
found") and by the live routing probes, but not finished. The remaining gap: install the
package into a throwaway config directory, run real `claude -p` sessions against it, and
watch the state files, the ledger and the weekly queue *while they run*, evaluating the
outputs critically rather than checking exit codes. Never against the real `~/.claude`.

## Closed

Kept as one line each so a returning session does not reopen them.

- **`claim-provenance` forge.** Shipped. `README.md:157` carries its row; `PYTHONPATH=$PWD
  python3 tests/test_doctrine_sync.py` -> Ran 20 tests, OK.
- **Concurrent `skillforge done` race.** Fixed by the `.outcome.<id>.claim` scheme in
  `bin/skillforge` (see the header comment at line 40 and the claim path at line 513);
  `tests/test_forge_close_race.py`.
- **Personal-scope skill loading.** Measured on 2026-08-25 and recorded in
  `docs/CLAUDE-CODE-BEHAVIOR.md` ("Run at all three scopes: **project**, `--plugin-dir`
  **plugin**, and, on 2026-08-25, **personal**"). `CLAUDE_CONFIG_DIR` alone broke auth; the
  missing piece was handing the OAuth token in through `CLAUDE_CODE_OAUTH_TOKEN`. All three
  scopes agreed. *This file previously asserted both that it was measured and that it was
  unmeasured, in two different sections; the unmeasured claim was the stale one and is gone.*
- **`204acb0`'s false commit message** ("544 tests pass"). Reworded by rebase.
  `git merge-base --is-ancestor 204acb0 HEAD` exits 1 — that commit is no longer reachable —
  and its successor is `83a75b5`, whose message states the actual result.
- **Commit everything as one tree.** Done; the tree with `skill-authoring`, its README row
  and `tests/test_doctrine_sync.py` landed together.
- **Status-line honesty and the overrun record.** Landed, and the prose that was owed has
  been applied: `docs/DESIGN.md:183-192` and `:544-552` describe the 99%-with-reason and
  `over` rendering, and `skills/skill-compounder/SKILL.md:95` now reads "The overrun is
  visible; you do not have to narrate it" rather than documenting a workaround for a
  display defect.
- **`docs/CLAUDE-CODE-BEHAVIOR.md` split** out of `docs/DESIGN.md`, guarded by
  `tests/test_docs_split.py`.
- **`skill-authoring` mutation gaps** (`tests/test_seed_authoring.py`) and the
  **deterministic insight record** (`hooks/insight-capture.sh` writes the queue on Stop;
  `hooks/compound-improvement.sh:17-27` surfaces it on the first prompt of a session;
  `bin/skillinsight` ships).

## The failure that produced this file

A checkpoint hook fired at edits 12, 24 and 36 in one session and was disregarded every
time, because it asks whether "the procedure you are working through right now" is
recurring — a per-instance question, asked while absorbed in a single fix. Nine defects of
one kind were fixed in that session without the pattern being noticed. The lesson is not
"read the reminders": it is that a mechanism whose output depends on someone noticing will
fail exactly when it is most needed. Prefer mechanisms that produce their record whether or
not anyone reads anything.

The lost session review at the top of this file is the same failure in a new place. That
mechanism *did* produce its record without anyone noticing — and then dropped it on the
floor between the model call and the queue, while stamping the cooldown that stopped it from
trying again. Producing the record is necessary. It is not sufficient; the handoff has to be
verified too.
