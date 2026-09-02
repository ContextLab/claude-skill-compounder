# 2026-09-02 — The forge diet: a concrete edit plan

Baseline: HEAD `ee7cef5`. Input: `notes/2026-09-02-audit-and-replan.md` ("Agent 3: why forging is slow", Tier 2 of the plan). Issue #22.

## 0. What the diet is

Default forge = **A dispatches C, D reviews, C repairs, a new D reviews, A gates and closes.** Two agents besides A, two rounds, everything dispatched in the background. Target: under 30 minutes for a narrow skill (median today: 3.3 h over ten closed forges; 4 of 10 failed).

Kept because each caught an observed failure: parse gate (~2s), routing gate (~90s/skill), round 1 plus one confirming round, the non-fork reviewer, the brief on disk, the round record, `--trigger`.

Cut from the default: the orchestrator layer B (caught no defect; caused the 86-hour stuck forge), stage E (two meta findings ever, never a skill defect), the mandatory runnable repro (no note records it catching anything), rounds 3..N (~60% of wall clock).

B and E return, together, **only when the round budget exceeds 2**, i.e. only on a forge the CLI has granted an escalation.

## 1. `skills/skill-compounder/SKILL.md`, section by section

Line numbers are HEAD's.

| Lines | Section | Verdict |
|-|-|-|
| 1–4 | frontmatter | **KEEP, byte-for-byte.** Touching `description` invalidates the routing pin (216 calls, ~15 min to re-measure). The diet is a body rewrite. |
| 6–21 | intro, habit 1 | KEEP |
| 23–41 | habit 2, threshold | KEEP. `both-conditions` stays pinned and verbatim. |
| 42–44 | "Three things override a yes… write a note or update `CLAUDE.md`" | **REWRITE** → the three-tier block (§2). Names no path, no CLI, no ledger row; taken zero times in ten days. |
| 46–65 | protocol header + stage table | **REWRITE** (§3) |
| 66–93 | step 0, announce + budget | KEEP prose; budget numbers 12/22 → **6/10**; add the sentence that the cap is enforced. |
| 94–114 | step 1, pre-register | KEEP + **ABSORB** stage E's three questions and B's level/specialisation decision (§4). |
| 116–168 | step 2, hand the loop to B | **CUT from the default.** ~35 lines move into "When the budget exceeds two rounds"; the rest goes. |
| 169–186 | step 3, B sets level and cap | **CUT**, folded into step 1. The two pinned sentences (`highest-applicable-level`, `specialisation-not-baked-in`) move with it, anchors and all. |
| 187–214 | step 4, C builds | **RENUMBER to 2**; rewrite the repro paragraph as optional (§5). |
| 215–249 | step 5, D | **RENUMBER to 3**; add one sentence on what "either layer" means in a one-layer forge. |
| 250–298 | step 6, loop and cap | **RENUMBER to 4 and rewrite** (§6): `skillforge round`, the refusal, the escalation rule. |
| 299–374 | step 7, apply + routing gate | **RENUMBER to 5. Move intact.** Every sentence `test_routing_gate.py` pins lives here. Only edit: the checklist cross-reference. |
| 375–406 | step 8, E | **CUT from the default**; ~14 lines move into the escalation block. |
| — | new | **ADD step 6**: close, then `apply` and `verdict` (§7). |
| — | new | **ADD** "When the budget exceeds two rounds" (§8), unnumbered so `steps()` does not read it as a step. |
| 407–432 | fix/document/retire | KEEP |
| 433–443 | §3.5 candidates | KEEP; add one line that a queued candidate is a tier-0 note until it recurs. |
| 445–469 | hot-reload, `done` | KEEP; the apply bullet now points at step 6. |
| 471–499 | Trigger precision | **KEEP, byte-for-byte** (the pin covers description + prompt list). |
| 501–505 | Troubleshooting | KEEP; add `skillnote` to the CLI list. |

Body is 501 lines against `skill-authoring`'s 500-line ceiling (`SkillBudgetTest`). The diet removes ~120 and adds ~50; expect ~430.

## 2. New text — the three-tier decision (replaces lines 42–44)

> Three things override a yes, in order: an existing skill already handles it (section 1); a single sentence of documentation covers it; the procedure is specific to work finishing now.
>
> **Then pick the tier. Only the third one is a skill.**
>
> |Tier|What it is|How|
> |-|-|-|
> |**0 — note**|one dated line of fact, in a marker block of the project's or your `CLAUDE.md`|`skillnote add --scope project "<the line>"`|
> |**1 — reminder**|short prose keyed on words, paths or a command signature, injected when a matching prompt or call appears|`skillnote add --remind --keyword <k> "<the line>"`|
> |**2 — skill**|a `SKILL.md`, plus scripts where a command is worth shipping, reached by its description|the forging protocol below|
>
> <!-- doctrine: tier-before-forge -->
> **A procedure earns a skill only when it has steps a model gets wrong without them AND a trigger a description can route; otherwise it is a note or a reminder.** Both halves are checkable before a single agent is dispatched, and both fail loudly. *Steps a model gets wrong*: name the step and the wrong turn taken without it. A fact has no steps: "the suite is `./run_tests.sh`" is a note, and forging it wraps one sentence in eight hundred. *A trigger a description can route*: write the sentence a user would actually type. If the moment is internal to the assistant and no utterance marks it, nothing will route it, and a reminder keyed on the tool call or the path will fire where a skill would not.
>
> Both tiers write a ledger row, so a note that keeps getting rewritten is visible as recurrence rather than as a feeling.

**Sequencing:** this text may not ship before `bin/skillnote` does, and the flag spelling must be read off the shipped CLI (see `notes/2026-09-02-tiers-design.md`), not from this note.

## 3. New text — protocol header (replaces 46–65)

Heading: `### Forging protocol: A → C → (D → C)² → A` (the `_forging` regex only needs the `### Forging protocol` prefix).

> **The original project is held-out test data.** *(paragraph 48–52 kept verbatim)*
>
> |Stage|Who|What it holds|What it owns|
> |-|-|-|-|
> |**A**|the session that hit the problem|the project, the transcript, the verbatim trigger|the brief, the dispatches, the round record, the gates, the close|
> |**C**|one builder subagent, in a scratch directory|A's generalised brief; no path into the project|writes the skill and runs every command it documents|
> |**D**|a **new** cold red-teamer every round|the skill file, and nothing else|infers a scenario from the skill alone and executes it|
>
> Two dispatched agents and two rounds. A narrow skill should close in **under 30 minutes**; if it has not, the scope is wrong, not the budget. An orchestrator (B) and a judge (E) exist only on a forge whose round budget has been raised past 2; see *When the budget exceeds two rounds*. The briefs are in `references/pipeline-stages.md`.

## 4. Step 1 absorbs the judge and the placement (adds to 94–114)

Two additions to the on-disk brief at `~/.claude/skill-compounder/briefs/<name>.md`:

> - **the framing check, made here rather than audited later.** Write the verbatim trigger and A's framing adjacent, then one sentence saying what the framing generalises and what it drops. This is stage E's first question, asked at the moment the answer can still be cheap: a misframing has every later check certifying the wrong thing, and the judge that used to catch it found two meta findings in ten forges and never a skill defect.
> - **the level, and what is deferred to `CLAUDE.md`.** *(the two pinned sentences and their anchors move here unchanged from step 3)*

E's remaining questions are answered by parties that already exist. Q2 (does it meet the criteria as written?) is A's score at step 5 against the file, not memory. Q3 (would a stranger get through?) is what D already does.

## 5. Step 2 — the repro becomes conditional (replaces the paragraph at 198–205)

> **A runnable reproduction where the skill has an executable surface, and only there.** If the draft documents a command, a script, a file format or an API call, C builds the smallest thing in its scratch directory that exhibits the situation and runs every command the draft asserts against it. If the draft documents no executable surface, a procedure whose steps are judgements about prose, or about what to do next, there is nothing to reproduce, and demanding one buys a scratch repo nobody reads. **C states which of the two it is, in one sentence, in the round record**; that sentence is what keeps "no executable surface" from becoming the default answer. Where a repro is owed and cannot be built, that is a finding about the brief, not a licence to proceed on description alone.

Everything else in the step stays: the `skill-authoring` hand-off by name, `boundary-without-the-address`, `standard-is-not-project-content`, the parse gate. **Exactly one numbered step may contain the string `skill-authoring`** (`test_routing_gate.HandOffNamesAgreeTest` asserts `len(step) == 1`).

## 6. Step 4 — the hard cap, and what enforces it

The audit found 3 of 10 forges overran an advisory cap. `skillforge` already derives `rounds` as `(step − 2) / 2`.

**The refusal does not go on `skillforge step`.** Three tests in `tests/test_skillforge.py` pin `step`'s overrun behaviour at exit 0 (`test_step_records_an_overrun_instead_of_clamping_it`, `test_done_does_not_rewind_a_forge_that_ran_past_its_budget`, `test_the_ledger_counts_the_rounds_an_overrun_actually_completed`), and they are right: a budget is a plan, the step reached is an observation.

It goes on a new pair of subcommands that own the round record:

```
skillforge round --name <forge> --blocking <k> --total <m> \
  --subsystems "<what the blocking findings named>" --shapes "<the finding shapes>"
skillforge escalate --name <forge> --converging
skillforge escalate --name <forge> --narrowed "<the subsystem cut, and who owns it now>"
```

- `round` appends one line to `~/.claude/skill-compounder/rounds/<forge>.tsv` in the existing format, and exits **0** while budgeted rounds remain.
- Calling `round` for a round past the budget exits **3** without writing a row:
  `round cap reached (2 of 2 planned). A third round is earned, not taken: 'skillforge escalate --name <forge> --converging' needs blocking to have fallen (round 2 = 3, round 1 = 2: it rose), '--narrowed "<what you cut>"' buys the cold round a narrowed skill owes. Otherwise close it: skillforge fail --name <forge> "not converging: <what kept coming back>".`
- `escalate --converging` exits **4** unless the last two rows show a strictly falling `blocking`. `--narrowed` is granted **once per forge**. Either grant raises `steps` by exactly 2 (one round) and appends an `escalate` ledger row carrying both counts and the reason; a **third** grant is refused outright.

Why this is a real cap: `--converging` requires a strictly decreasing sequence of non-negative integers, which terminates; the two-grant ceiling bounds it at 4 rounds regardless.

New body text:

> **4. Record the round, and let the CLI decide whether there is another.** After each D report, classify every finding on one test (would shipping with this make the skill do the wrong thing for a stranger?) and record it with `skillforge round`. `blocking` is **your** call, not D's: D is asked for findings, not severities, and a fresh D each round cannot share a scale with the last.
>
> <!-- doctrine: hard-round-cap -->
> **A third round is earned by a falling blocking count, and `skillforge` refuses the round without one.** *(then the escalation block above)*
>
> <!-- doctrine: assess-convergence-every-round -->
> **Decide whether the loop is converging at every round, not at the cap.** *(kept verbatim)*
>
> <!-- doctrine: the-assessment-binds-from-round-two -->
> **The assessment binds from round 2, where the first comparison exists, and never from round 1.** One data point cannot match the converging definition, and a rule that fires on one round is a licence to quit after one, which is why the CLI grants round 2 unconditionally and refuses only after it.
>
> <!-- doctrine: narrowing-restarts-the-review -->
> **A narrowed skill is a new skill for review purposes…** *(kept verbatim; the round it costs is now the round `--narrowed` grants)*

Escalation rule, stated once and identically in all mirrors: **a third round only if round 2's blocking count is strictly lower than round 1's; otherwise narrow, or abandon.**

## 7. Step 6 — wiring `measure` (new)

`skillforge verdict` exists at `bin/skillforge:1760–1786`, is named in no protocol doc, and has 0 rows in 807. Five of six closed forges also have no `apply` row. Both debts close in one place, because this is the only moment anyone holds both the skill and the problem (issue #19's gap).

> **6. Close it, then answer the two questions that make the forge countable.** `skillforge done "<outcome>"` closes the record and links the skill. It leaves a debt. Pay it in the same turn, from the same evidence:
>
> ```bash
> skillforge apply   --name <skill> --outcome used|declined --evidence "<verbatim>"
> skillforge verdict --name <skill> --verdict WORKED|NO-OP|MISFIRED --evidence "<verbatim>" \
>   --use-session "$CLAUDE_CODE_SESSION_ID"
> ```
>
> `apply` says the skill was put on the problem that caused it. `verdict` says what happened when it was. **WORKED**: the acceptance test got through and you can quote the line where it did. **NO-OP**: it was followed and changed nothing a session would not have done anyway; that is data, not a failure. **MISFIRED**: it told you something wrong, which is section 3's input. `--evidence` is mandatory for all three; `UNKNOWN` is the only verdict the CLI writes bare, and `--outcome declined` is a first-class answer.
>
> <!-- doctrine: verdict-follows-the-apply -->
> **A verdict is recorded after the skill has been applied to the problem that caused it, never before.** A verdict written from the draft judges a text; written after the application it judges an event, with a quote behind it.

The failure path keeps quarantine, with **A, C and D** appending signed sections (B and E only where they existed).

## 8. New text — "When the budget exceeds two rounds"

Unnumbered heading, after step 6:

> **When the budget exceeds two rounds: the orchestrator and the judge.** A forge granted a third round is one whose review traffic is about to fill this thread, and a long forge drifts in ways a two-round forge cannot. Two stages come back, and only then.
>
> **B takes the loop from the granted round on.** Hand it A's framing and the generalised transcript, dead ends included; the raised budget; the `skillforge step` numbering spelled out (`references/forge-animation.md`); steps 2 to 5 pasted in full; and one abort condition: **if it has no `Agent` tool it stops and says so immediately.** Never nest orchestrators; C and D dispatch nobody.
>
> Do **not** hand a dispatched agent the project, the repository path, or the verbatim trigger; those are the test set, and the CLI withholds them rather than trusting an agent to: `skillforge show` and `ledger` omit `root`, `trigger`, `project` and `trigger_verbatim` without `--full`, naming what they left out.
>
> <!-- doctrine: close-ownership -->
> **You own `start`, `done` and `fail`; every agent you dispatch owns everything between.**
> <!-- doctrine: dispatched-agents-do-not-close -->
> **A dispatched agent calls neither `done` nor `fail`.** The first close wins and the second is discarded, silently, at exit 0.
>
> **E judges the outcome.** *(the three questions, and `e-checks-the-framing` with its anchor, moved unchanged)*

And in step 2, replacing the retired `orchestrator-runs-the-rounds` paragraph:

> <!-- doctrine: forge-runs-in-the-background -->
> **Every agent a forge dispatches runs in the background, and the session that starts one never blocks on it.** Dispatch C in the background and go back to what you were doing; watch for its marker file rather than waiting on a message. Blocking was never the cost; the agents already ran in the background. The cost was review traffic landing in the thread the user is talking to, and two rounds of it, polled rather than relayed, is a cost the diet can pay.

`quiesce-before-reading` moves with this.

## 9. Doctrine mirrors

`.claude/CLAUDE.md`: the protocol "is mirrored in `README.md` and in the user's global `~/.claude/CLAUDE.md` stanza. Changing the protocol means updating all three."

### README.md — exact sections

1. **`## What gets installed`** (l. 53): add a `bin/skillnote` row (tiers 0 and 1); extend the `bin/skillforge` row to name `round`, `escalate`, `apply`, `verdict`.
2. **`### 2. During work, notice what is worth keeping`** (l. 328–490):
   - after the `both-conditions` block (l. 351–361): insert the three-tier table and the `tier-before-forge` anchored sentence;
   - **the ASCII diagram** (l. 364–390): replace with the default shape (`A: this session`, then `├─ builder agent (C)`, `├─ red-team agent (D)`, `├─ loop (2 rounds)`, `└─ cap at 2 rounds` as direct children of the session) and add a **second** diagram below it for the escalated shape, keeping the orchestrator with builder / red-team / loop nested beneath it;
   - `cap at 2 rounds` and `(4 for a complex or safety-critical skill)`;
   - add the hard-cap sentence and the escalation rule beside the cap line;
   - **l. 424–437**, the orchestrator paragraph → `forge-runs-in-the-background`;
   - **l. 453–457**, `close-ownership` reworded;
   - keep verbatim: `routing-gate-on-completion`, `must-not-half-is-a-gate`, `unmeasured-is-not-verified`, `no-forked-reviewer`, the D-checklist paragraph, `no-leading-prompt`, `highest-applicable-level`, `specialisation-not-baked-in`;
   - the E paragraph (l. 483–490) is prefixed "on a forge that ran past two rounds";
   - one new sentence: a closed forge now records `apply` and `verdict` in the same turn.
3. **`## The animation`** (l. 562): the bar example moves from `▕██████······▏ 6/12` to a 6-step budget, e.g. `▕███···▏ 3/6`. Every bar in the README must satisfy `total == 2 + 2 × cap`.
4. **`### What the ledger records`** (l. 666): "four questions" becomes five, and the table gains the `apply` row; the `verdict` row gains "written at step 6, after the apply".
5. **`## Does any of this actually pay off?`** (l. 641): one sentence: the last two columns are no longer structurally empty.

### `.claude/CLAUDE.md`

Only one DOCTRINE sentence mirrors here (`no-forked-reviewer`) and it is **kept verbatim**, with one sentence added after it: in the default one-layer forge the only layer is the session that dispatched the reviewer. Also: the CLI-count sentences ("five CLIs") move when `skillnote` ships, and the paragraph naming `SKILL.md` as the primary deliverable gains the tier rule.

### The global stanza (installer marker block)

W1c is adding the stanza now; the diet fixes its content. Lines that must be present:

```
Compounding: keep what a session learned at the cheapest tier that holds it.
- note:     skillnote add --scope project "<line>"
- reminder: skillnote add --remind --keyword <k> "<line>"
- skill:    forge it, and only when the procedure has steps a model gets wrong
            without them AND a trigger a description can route.
Both must hold, or it gets a note rather than a skill.
The forge is one builder subagent and one cold reviewer, dispatched in the background,
two rounds, hard-capped: `skillforge round` refuses a third without a falling blocking count.
The red-teamer must never be a fork of either layer — not of the orchestrator that
dispatches it, and not of the session that dispatched the orchestrator.
A forge cannot be reported clean while the skill's own must-fire prompts do not fire it.
Close with `skillforge done`, then `skillforge apply` and `skillforge verdict` in the same turn.
```

### What `test_doctrine_sync.py` checks, and the hole to close

It checks **derived facts** (the cap, the step budget, the bar arithmetic, the knob table, the CLI's real behaviour, run) and **doctrine** (exact sentences in `DOCTRINE`, present verbatim in every listed mirror, each preceded by its `<!-- doctrine: id -->` anchor in `SKILL.md` and `README.md`). Its module docstring records that the third mirror, the global stanza, is unchecked because the repo neither ships nor installs it. **Once W1c ships the stanza that is false**: add the installer's stanza constant as a fourth entry in `MIRRORS` (excluded from `ANCHORED`, like `.claude/CLAUDE.md`), list it as a mirror for `no-forked-reviewer`, `both-conditions`, `tier-before-forge`, `hard-round-cap` and `routing-gate-on-completion`, and update the docstring's "holes open by design" list.

## 10. Tests that pin strings this rewrite changes

`tests/test_doctrine_sync.py`

| Test | Why it breaks | Replacement assertion |
|-|-|-|
| `DoctrineMirrorTest.test_every_pinned_rule_is_stated_in_every_file_that_carries_it` | four `DOCTRINE` entries change | retire `orchestrator-runs-the-rounds`; add `forge-runs-in-the-background` = "Every agent a forge dispatches runs in the background, and the session that starts one never blocks on it." (SKILL, README, stanza); `close-ownership` → "You own `start`, `done` and `fail`; every agent you dispatch owns everything between." (SKILL, README); `orchestrator-does-not-close` → id `dispatched-agents-do-not-close`, "A dispatched agent calls neither `done` nor `fail`." (SKILL); `the-assessment-binds-from-round-three` → id `the-assessment-binds-from-round-two`, "The assessment binds from round 2, where the first comparison exists, and never from round 1." (SKILL). Add `tier-before-forge`, `hard-round-cap`, `verdict-follows-the-apply`. Every `why` string records the retirement reason. |
| `DoctrineMirrorTest.test_each_pinned_sentence_is_anchored_where_the_doctrine_is_written_out` | anchors move with sentences | no code change; anchors relocated in the same commit |
| `DoctrineMirrorTest.test_no_document_carries_an_anchor_for_a_rule_that_is_not_pinned` | retired anchors would remain | delete `<!-- doctrine: orchestrator-runs-the-rounds -->` from `SKILL.md` and `README.md`; rename the two renamed anchors |
| `ForgeDiagramTest.test_the_diagram_nests_the_loop_under_the_orchestrator` | the default diagram has no orchestrator | **split in two.** `test_the_default_diagram_hangs_the_builder_and_reviewer_off_the_session`: parse the **first** `skillforge start` diagram, require `builder` and `red-team` at the same indent as `A: this session`'s children and require the word `orchestrator` absent from it. `test_the_escalated_diagram_still_nests_the_loop_under_the_orchestrator`: the current method body, verbatim, applied to the **second** diagram, plus an assertion that `FORGING` states the condition (`re.search(r"budget exceeds (\d+) rounds", FORGING)` equals the derived cap). Coverage goes up, not down. |
| `HeldOutIsConstructionNotInstructionTest.sentence()` | regex `Do \*\*not\*\* hand B the project.*?\n\n` | `Do \*\*not\*\* hand a dispatched agent the project.*?\n\n`; the four field assertions and the `--full` assertion unchanged |
| `OrphanedConstantTest.test_no_doc_cites_a_duration_the_skill_does_not_have` | vacuous today; the 30-minute target is a new duration claim in two files | widen the pattern to `(?:>|under )\s?(\d+)\s?min`, so README's "under 30 minutes" must be defined in `SKILL.md` |

Derived and **not** to be edited (they must go green on the doc change alone): `RoundCapTest.*` (cap 5→2, escalated 10→4, bars `N/6`), `SkillBudgetTest.*`, `SeedPoolTest.*`, `SkillforgeContractTest.*`, `TuningTableTest.*`, `DerivationCommandTest.*`, `RetiredWordingTest.*`.

`tests/test_routing_gate.py`

| Test | Why | Replacement |
|-|-|-|
| `HandOffNamesAgreeTest.test_step_four_says_why_the_bare_names_do_not_work` | the builder step is 2 now; the test **name** and docstring assert "step four" | rename to `test_the_builder_step_says_why_the_bare_names_do_not_work`; assertions unchanged |
| `GateIsAStepTest` docstring | says "Step 3", already stale at HEAD | correct to the derived number |

Not edited, load-bearing on the renumber: `gate_step()` (exactly one step invoking `scripts/probe_routing_claims.py`), `test_the_step_numbers_are_contiguous_from_zero` (**steps must be 0..6**), `test_every_cross_reference_names_a_step_that_exists`, `RedTeamChecklistTest.test_the_row_requires_running_the_prompts` (**the Trigger precision row must say "step 5"**), `DerivedFromTheProbeTest.*` (the `216 calls` / `18 calls` / `7-76s a draw, median 23s` strings must survive the move), all of `PinnedGateSentenceTest.PINNED`, `OneRunIsOneDrawTest.*`.

`tests/test_seed_authoring.py`

| Test | Why | Replacement |
|-|-|-|
| `test_it_points_at_the_enforcement_rather_than_restating_it` (l. 1940) | pins `` `skill-compounder` step 3 `` in `skills/skill-authoring/references/gate-checks.md`; the parse gate becomes step 2 | derive it: parse `skill-compounder`'s forging section with the same step split, find the single step whose body names the parse gate (`Gate A`), assert `gate-checks.md` names **that** number. |

Collateral in the same commit: `skills/skill-authoring/SKILL.md:394` "`skill-compounder` step 2 invokes it by name" (true again), and `:176` "`skill-compounder` step 3 runs a parse of its own" → step 2.

`tests/test_skillforge.py`, `tests/test_statusline.py`: **not edited.** New coverage goes in a new file, `tests/test_forge_rounds.py`: the second round is granted and the third refused (exit 3, no row written); `--converging` refused on a flat or rising count (exit 4); `--converging` granted on a strictly falling one, raising `steps` by exactly 2 and writing an `escalate` ledger row; `--narrowed` granted once and refused twice; a third grant refused; and a derived check that the cap `SKILL.md` states is the cap the CLI enforces, by running it.

## 11. Wording drift, fixed while here

`SKILL.md:256` "complex or genuinely important" / `README:380` "complex or safety-critical" / `round-cap.md:3` "genuinely important" against `:56` "A safety-critical skill…". **Standardise on "complex or safety-critical"** in all four places. `RoundCapTest` reads `or (\d+) for a skill that is complex` from `SKILL.md` and `(%s for a complex` from README, so both regexes still match.

## 12. Reference files

- **`round-cap.md`**: rewrite the numbers (5/10 → 2/4) and the not-converging list. Keep the `finish-task` worked case and add one line: under this cap it stops at round 2 (blocking 2 → 3, rising), not round 10. Say the CLI now reads this file's format.
- **`forge-animation.md`**: the step table (6 at the default), and rewrite "Overrunning is fine, and for a converging loop it is CORRECT": an overrun is now a *granted* escalation with a row behind it. Add `round`, `escalate` and the exit codes; add `verdict` beside `apply` in "the apply debt".
- **`pipeline-stages.md`**: B and E sections move under a "only past two rounds" heading; C's "Must build a runnable reproduction" becomes the conditional rule; A's section gains the framing check and the level decision. Every `.md` path it names must still resolve (`test_docs_split.py`).
- **`routing-gate.md`**, **`retirement.md`**: untouched.
- **`docs/DESIGN.md:61`** ("The loop runs in a background orchestrator"): one-line correction.

## 13. Order of work

1. `bin/skillnote` ships (W2a) → then the tier text may name it.
2. `skillforge round` / `escalate` ship with `tests/test_forge_rounds.py` → then `SKILL.md` may claim the refusal.
3. `SKILL.md` + `references/` + `README.md` + `.claude/CLAUDE.md` + the two `skill-authoring` cross-references + the test edits, **in one commit**.
4. `./run_tests.sh` whole-suite, once, at the end.

Do not re-run the routing probe: the description and the six prompts are untouched, so the pin stays valid. If either does change, the gate is 18 calls for this skill at the three-run floor and the pin must be re-measured, never re-hashed.
