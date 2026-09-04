---
name: skill-compounder
description: "Use when a skill you just used misfired — it told you the wrong thing (to run from the wrong directory, an outdated command), or fired when it should not have — so it needs fixing or retiring; when deciding whether a repeatable procedure has earned becoming a skill; or when asking, before implementing something new, 'is there already something for this?'. Do NOT use to author a skill already decided on (that is superpowers:writing-skills), for a one-off script, or ordinary refactoring."
---

# Compounding: turn hard-won procedures into permanent capability

Every session should leave the toolchain measurably better than it found it, so the same
problem never gets solved from scratch twice. Three habits, a threshold that keeps the
machinery from costing more than it saves, and a pipeline that forges what clears it.

## 1. Before any major implementation, check for an existing skill

Before writing a plan or the first line of code for anything non-trivial: scan the skill list injected into
this session's prompt; `ls ~/.claude/skills/` (cross-project) and `ls ./.claude/skills/` (project-local); when
the name is not an obvious match, `grep -ril '<keyword>' ~/.claude/skills ./.claude/skills
~/.claude/plugins/cache/*/*/*/skills`; and beside that grep, `surfer search "<keyword>" --all`, the level B
search, which asks whether this user has hit this before in another project and names the project if so.
Read its hits, never act on one: measured 0.72 false positives at its best threshold (n=60, precision 0.28).

<!-- doctrine: invoke-do-not-reimplement -->
**If a plausible skill exists, invoke it. Do not reimplement.** If it turns out to be the
wrong tool, that is useful signal: go to section 3.

## 2. During work: is this pattern worth crystallizing?

Keep asking: *is what I am doing right now a repeatable procedure?* Good candidates are a
debugging workflow that finally worked, a deploy-and-verify sequence, a non-obvious API dance,
a project build+test+screenshot loop. Forging costs several subagent rounds, so be selective.

**Threshold (BOTH must hold).**

- **Costly.** Name the specific dead end, in one sentence, and say what a fresh session would
  have done instead. If you cannot name it, it was not costly; it was just work.
- **Recurring.** Point at the second occurrence — a prior session, an earlier point in this
  one, an open issue. "It seems like the sort of thing that recurs" is not a second one.

<!-- doctrine: both-conditions -->
**Both must hold, or it gets a note rather than a skill.** Both need a **concrete referent**,
not a judgement, because both are otherwise loose enough to say yes to nearly any non-trivial
work, and a threshold that always resolves to yes is worse than none. Write the two sentences
down before deciding; if either is hard to write, that is the answer.

Three things override a yes, in order: an existing skill already handles it (section 1); a single sentence of
documentation covers it; the procedure is specific to work finishing now.

**Then pick the tier. Only tier 2 is a skill; the last row is the two cheap ones in one command.**

|Tier|What it is|How|
|-|-|-|
|**0 — note**|one dated line of fact, in a marker block of the project's or your `CLAUDE.md`|`skillnote add --scope project "<the line>"`|
|**1 — reminder**|short prose keyed on words, paths or a command signature, injected when a matching prompt or call appears|`skillnote add --remind --keyword <k> "<the line>"`|
|**2 — skill**|a `SKILL.md`, plus scripts where a command is worth shipping, reached by its description|the forging protocol below|
|**0 and 1 — lesson**|a fail-then-fix as one record: the dated line, and a reminder keyed on the call that failed|`skillnote add --lesson <sig> "<text>" [--attach <path>]`|

<!-- doctrine: cheap-branch -->
**The cheap branch is a command, not an intention: `skillnote add` records the note or the reminder, and a
lesson nobody ran a command for was not kept.** Both cheap tiers write a ledger row, so a note that keeps
being rewritten shows up as recurrence rather than as a feeling.

A lesson is that pair in one command, keyed on the failing call so the fix is in context before that command
runs again; `--attach <path>` carries the script the fix needed, and one recorded again from a second project
moves up with `skillnote promote <id> --to global`, which moves it and never copies it. Remembering to run it
is not your job: the repeat gate states the command the first time it sees a failure recovered, and on a
signature that has now failed in a second session it refuses the next tool call until either that command or
`skillrepeat dismiss <sig> --why "<why>"`, a row rather than a delete, has run.

### The mission is delivered, not remembered

The mission is the user's own requests in this session, verbatim. A hook restates them after a compaction or
a resume, before a dispatch and again inside every subagent, periodically through long work, on a prompt too
short to carry its own referent, and once before a completion claim. Read the requests against the work in
front of you and say what does not match: the text is a statement of fact, not an instruction. It reads
history-surfer's store and keeps no second copy, so with no `surfer` installed it delivers nothing at all,
and `skillforge doctor` is what reports which of the two you have.

<!-- doctrine: tier-before-forge -->
**A procedure earns a skill only when it has steps a model gets wrong without them AND a trigger a description
can route; otherwise it is a note or a reminder.** Both are checkable before anything is dispatched. *Steps a
model gets wrong*: name the step and the wrong turn taken without it — a fact has no steps, and forging "the
suite is `./run_tests.sh`" wraps one sentence in eight hundred. *A trigger a description can route*: write the
sentence a user would type. If the moment is internal and no utterance marks it, nothing routes it, and a
reminder keyed on the tool call or the path fires where a skill would not.

### Forging protocol: A → C → (D → C)² → A

**The original project is held-out test data.** A skill written by the session that needed it comes out full
of references only that session can decode. Any agent that sees the project overfits to it. So one agent, A,
holds it and spends that privilege judging the result rather than writing it; every other stage is denied
something the previous one had, and the denials are the mechanism.

|Stage|Who|What it holds|What it owns|
|-|-|-|-|
|**A**|the session that hit the problem|the project, the transcript, the verbatim trigger|the brief, the dispatches, the round record, the gates, the close|
|**C**|one builder subagent, in a scratch directory|A's generalised brief; no path into the project|writes the skill and runs every command it documents|
|**D**|a **new** cold red-teamer every round|the skill file, and nothing else|infers a scenario from the skill alone and executes it|

Two dispatched agents, two rounds. A narrow skill should close in **under 30 minutes**; if it has not, the
scope is wrong rather than the budget. An orchestrator (B) and a judge (E) exist only on a forge whose round
budget has been raised past 2, below. Each agent's brief is in `references/pipeline-stages.md`.

<!-- doctrine: announce-the-forge -->
**0. Announce it, and show the work. The user must never discover a forge after the fact.** Say in plain text
what the skill is and why it cleared the threshold, then start the animation:

```
skillforge start <name> <total-steps> "<one-line summary>" \
  --trigger "<the verbatim text that set this forge off>" \
  --trigger-kind <user-prompt|hook-checkpoint|review-dispatch|agent-decision>
```

**`--trigger` is not optional in this protocol, even though the CLI only warns.** It is the one ledger
question nothing can recover afterwards. Paste it; do not summarise. `--trigger-kind` says who was asking
(`references/forge-animation.md`).

<!-- doctrine: concurrent-forges -->
**Just start it.** Concurrent forges are fine — each gets its own record and its own slot in the status
line, and starting one never disturbs another. `skillforge start` exits 2 when the name is held by a live
forge. Close a dead one with `skillforge fail
--name <forge> <reason>` or `skillforge clear --name <forge>`, never `done`. With several live, `step`, `done`
and `fail` refuse to guess: pass `--name <forge>`.

**Decide the round cap here**, because `<total-steps>` encodes it and cannot be changed later: budget `2 + 2
× (planned D rounds)`, **6** at the default cap and **10** at the escalated 4. `skillforge escalate` is the
only way to raise it (step 4); what each step number means is in `references/forge-animation.md`.

**1. A: pre-register, in writing, before anything is dispatched.** This is what makes goalpost-moving
impossible. Before dispatching anyone, write to a file:

- the **verbatim original trigger**: the text passed to `--trigger`, copied, not summarised.
- **A's framing**: the general procedure in one paragraph, with the project taken out of it —
  all C is allowed to see — and, adjacent to the trigger, **one sentence saying what the framing
  generalises and what it drops.** That is the framing check, made here rather than audited
  later: a misframing has every later check certifying the wrong thing, and the judge that used
  to catch it found two meta findings in ten forges and never a skill defect.
- **the level, and what is deferred to `CLAUDE.md`.** The hierarchy is general > user > project.
  <!-- doctrine: highest-applicable-level -->
  **A skill belongs at the highest level of the hierarchy to which it applies, and must be
  written generally enough to apply beyond the case that prompted it.**
  <!-- doctrine: specialisation-not-baked-in -->
  **The specialisation comes from the project's or the user's `CLAUDE.md` and the constraints
  already recorded there — never from text baked into the skill.** A skill that hardcodes one
  repository's test command has made a project's particulars everyone's. Record here how routing
  will be verified: where a skill installs decides which router sees it.
- the **success criteria**: what the finished skill must let a session do, stated so a
  stranger can score each one yes or no. One is standing, on every forge:
  <!-- doctrine: state-the-cost-bound -->
  **The skill must state when it is not worth its own cost.** The reader who already suspects
  they do not need it is the one who abandons it halfway and does not say so, and the exit ramp
  is one sentence.
- the **acceptance test**: the original triggering problem, written out to attempt again
  with the finished skill at step 5.

**On disk, not in context** — `~/.claude/skill-compounder/briefs/<name>.md`. A run can outlive a compaction
of this thread, and criteria held only in context are gone at that moment. Re-read at step 5.

**2. C: build it in a scratch directory, and run everything it claims.** Dispatch a subagent and tell it to
invoke **`skill-authoring`**, which ships here. An earlier version said `skill-creator` and
`writing-skills`, and neither bare name resolves — they exist only as `compound-engineering:skill-creator`
and `superpowers:writing-skills`, in plugins a fresh install lacks.

<!-- doctrine: forge-runs-in-the-background -->
**Every agent a forge dispatches runs in the background, and the session that starts one never blocks on it.**
Dispatch C and go back to what you were doing; watch for its marker file rather than waiting on a message. The
cost was review traffic landing in the thread the user is talking to, and two rounds of it, polled rather than
relayed, is a cost this shape can pay.

**Isolation is structural, not tidiness.** Hand C a scratch directory and no path into the project: what C is
*given* is the enforcement. <!-- doctrine: boundary-without-the-address --> **Where a boundary must still be
stated, describe what it encloses and never name what lies outside it.** "Read nothing outside your scratch
directory" is checked exactly the way naming the path is — grep the transcript, expect zero — while a brief
forbidding a path hands over the held-out data's address in the act of forbidding it. <!-- doctrine:
standard-is-not-project-content --> **Isolation withholds the project, never the authoring standard.** Hand C
the required sections, the caps, and that a routing gate runs six declared prompts — as text, never as a path
into this repository. Withholding it once cost a forge its gate: a draft with no `## Trigger precision`
section and nothing to run.

**A runnable reproduction where the skill has an executable surface, and only there.** If the draft documents
a command, a script, a file format or an API call, C builds the smallest thing in its scratch directory that
exhibits the situation and runs every command the draft asserts against it; where it documents none — steps
that are judgements about prose — there is nothing to reproduce. **C states which of the two it is, in one
sentence, in the round record**, which is what keeps "no executable surface" from becoming the default answer;
a repro that is owed and cannot be built is a finding about the brief (`references/pipeline-stages.md`).

**Then verify the draft parses, before anyone reviews it.** A skill can pass every review round and still
ship inert, and nothing catches it: `claude plugin validate --strict` **does not read SKILL.md frontmatter
at all** — frontmatter raising `yaml.ScannerError` still gets `✔ Validation passed`. Run `skill-authoring`
Phase 3's Gate A, or its short version in `references/pipeline-stages.md`. The commonest break is an
**unquoted `: ` in the description**, which leaves the skill installed, named and unable to fire.

<!-- doctrine: quiesce-before-reading -->
**Nothing reads a draft while its author is still writing it.** Confirm C is **idle** before any reviewer,
gate or acceptance test reads the draft, by something observable — a marker file and an unchanged checksum —
never by a message claiming so. An acceptance tester once scored a moving one.

**3. D: a cold red-teamer, one per round.** Dispatch a **separate, fresh** subagent, never C.

<!-- doctrine: no-forked-reviewer -->
**The red-teamer must never be a fork of either layer** — not of the orchestrator that dispatches it, and not
of the session that dispatched the orchestrator. In the default forge there is one layer, the session that
dispatched the reviewer, and the rule binds on it as written. A forked red-teamer already knows what the skill
was *meant* to say, so it cannot detect the ambiguity that will bite a cold session six weeks from now.

<!-- doctrine: d-infers-the-scenario -->
**D is given the skill and nothing else, and must infer for itself what situation the skill is for.** Not A's
framing, not C's reasoning, not the original intent. The inference is the completeness check: a skill whose
scenario cannot be reconstructed from its own text has a hanging reference in it, and one D infers wider than
the original is a skill that generalised. D then executes what it inferred, using the skill, and reports where
the skill fails, misleads, or under-specifies.

<!-- doctrine: no-leading-prompt -->
**Never hand a reviewer a list of what not to flag.** Same failure as asking it to "confirm the deletion", and
easier to commit because it feels like helpfulness — the A/B behind it is in `references/pipeline-stages.md`.
State the standard; do not enumerate the exceptions. Asking for hard verification is fine: "run every command"
constrains method, not conclusions. D's checklist:

|Check|What it catches|
|-|-|
|**Inferred scenario**|Can D say what this skill is for, from the skill alone? A guess it cannot make is a hanging reference.|
|**Cold start**|Can step 1 be executed with no prior context and no clarifying question?|
|**Trigger precision**|**Run** the section's 3 must-fire and 3 must-not-fire prompts through real `claude -p --model sonnet` sessions, per step 5. Nothing has installed the draft yet, so copy it to `<scratch>/.claude/skills/<name>/SKILL.md` and run each prompt with that scratch directory as the working directory: a headless run started there sees a project skill, and only there. A row with no observed `Skill` call behind it is a finding.|
|**Verified claims**|Actually run every command, path, and API call the skill asserts. Unverified claims are defects.|
|**Portability**|Does any example need a project D cannot see? That is the contamination the isolation was for.|
|**Unhappy path**|What does a session do when a step fails partway through?|
|**Overlap**|Does an existing skill already cover this? If so, that is a blocking finding.|
|**Scope**|Is it doing more than one thing? Split or narrow.|

**4. Record the round, and let the CLI decide whether there is another.** After each D report, classify every
finding on one test — would shipping with this make the skill do the wrong thing for a stranger? — and record
the round:

```bash
skillforge round --name <forge> --blocking <k> --total <m> \
  --subsystems "<what the blocking findings named>" --shapes "<the finding shapes>"
```

`blocking` is **your** call, not D's: D is asked for findings, not severities, and a fresh D cannot share a
scale with the last. The row lands in `~/.claude/skill-compounder/rounds/<forge>.tsv`, never in `briefs/`.

<!-- doctrine: fresh-reviewer-each-round -->
**Spawn a new red-teamer each round; the whole test depends on the reader being genuinely cold.** Feed
findings back to C, which keeps its context and its scratch repro, and poll for an artifact rather than block
on a reply (`references/pipeline-stages.md`).

**Cap at 2 rounds, or 4 for a skill that is complex or safety-critical**, chosen at step 0 because
`<total-steps>` encodes it. Where 2 comes from, and when to raise it, are in `references/round-cap.md`.

<!-- doctrine: hard-round-cap -->
**A third round is earned by a falling blocking count, and `skillforge` refuses the round without one.**
`skillforge round` for a round past the budget exits **3** and writes no row, naming the two most recent
blocking counts and the two ways past it:

```bash
skillforge escalate --name <forge> --converging
skillforge escalate --name <forge> --narrowed "<the subsystem cut, and who owns it now>"
```

`--converging` exits **4** unless the last two recorded rounds show a strictly falling `blocking`;
`--narrowed` is granted once per forge. Either raises the budget by exactly 2 — one round — and appends an
`escalate` ledger row carrying both counts and the reason. A third is refused, bounding the loop at 4
rounds. With neither: `skillforge fail --name <forge> "not converging: <what kept coming back>"`.

<!-- doctrine: assess-convergence-every-round -->
**Decide whether the loop is converging at every round, not at the cap.** A cap reached is not a decision
point, it is the moment the budget for making one ran out.
<!-- doctrine: the-assessment-binds-from-round-two -->
**The assessment binds from round 2, where the first comparison exists, and never from round 1.** One data
point cannot match the converging definition, and a rule that fires on one round licenses quitting after
one; the CLI grants round 2 unconditionally. *Converging* — a falling blocking count over rounds naming
**different** subsystems — is what buys a third; the not-converging shapes are in `references/round-cap.md`.
When it is not, the design is wrong rather than the wording and the choice is due at once: **narrow**,
cutting the subsystem the findings keep naming, or **abandon**, noting what blocked it.

<!-- doctrine: narrowing-restarts-the-review -->
**A narrowed skill is a new skill for review purposes: the rounds already spent certify a skill that no longer
exists.** So a narrowed draft **re-enters the loop at step 2**: C cuts it, a **new** cold D reviews the
result, and the forge is not clean until a D that saw the narrowed skill says so. That round is the one
`--narrowed` grants. How to read the record for either verdict, and a worked case, are in
`references/round-cap.md`.

**Step 5 is a scope cut too**: retiring a must-fire claim narrows what the skill owns, so A re-runs the
routing gate *and* dispatches one fresh cold reader against the narrowed trigger contract before closing.

**5. A: run the skill against the real case, and score the pre-registered criteria.** You alone have seen both
the project and the finished skill, so this is the only place "did it actually solve the thing that started
this" can be asked. Re-read the step-1 file, not your memory, and:

- **move the clean draft into place first**: `done` looks in the repo or at `--skill-dir` from `start`, and
  C reports its scratch path but never learns the destination, so the copy is yours;
- **attempt the original triggering problem again, with the skill**, and say what happened;
- score each success criterion as written — one that now looks wrong is a finding to record, never a
  criterion to edit;
- keep this verification in your notes and out of the SKILL.md: it is evidence about this forge, not
  instruction for a stranger.

<!-- doctrine: routing-gate-on-completion -->
**A forge cannot be reported clean while the skill's own must-fire prompts do not fire it.** A reviewer
reading the section and agreeing it looks right is not this check: every seed skill here passed a full loop
that way and three of their claims turned out false when the prompts were run (`references/routing-gate.md`).
So the draft needs at least three prompts that must fire it and three that must not, each the verbatim
utterance a user would type, and then they get run. Inside a checkout of this:

```bash
SKILL_ROUTING_PROBE=1 python3 scripts/probe_routing_claims.py <skill>
```

Anywhere else the script cannot help — it reads only that tree — so run each prompt yourself in an empty
directory and look for a `Skill` call naming the skill:

```bash
claude -p --model sonnet --max-turns 3 --output-format stream-json --verbose "<prompt>" \
  | grep -o '"name":"Skill","input":{[^}]*}'
```

**A non-zero exit is not a failed measurement:** `--max-turns` exhaustion and a denied permission both exit 1,
after the routing decision. **`--model sonnet`, never haiku** — personal and project skill descriptions were
measured absent from the router on haiku. Cost is one call per prompt per draw: one six-prompt skill is 18
calls at the floor, and the twelve pinned skills are 72 prompts, so **216 calls** and ~15 minutes. Measured
2026-09-01, CLI 2.1.252, over that whole 216-draw pass: 7-76s a draw, median 23s, 924s wall, six in parallel.

**One run is one draw, and a draw is not a verdict.** Routing is stochastic: one unchanged description here
gave 3/3, then 1/3, then 2/3, and this skill's own six prompts, probed three times in one day with nothing
edited between, gave 9/9, then 8/9, then 9/9. So the gate is **at least three runs of the whole section**, a
floor for *detecting* that spread rather than a score that earns `verified`. The pin records `runs: N` and a
k/N per prompt; `partial` names any prompt that split, and a prompt at 2/3 has not passed, it has been shown
unreliable.

**When a must-fire prompt loses, the description is what changes.** Not the prompt and not the verdict;
routing is brutally sensitive to the opening clause, so this is usually a small edit with a large effect —
changing `"Use before debugging logic"` to `"Use before any other debugging step"` flipped a losing prompt to
a winning one. Four words. Retiring a claim is allowed only when the prompt names a trigger this skill should
not own *and* the skill that beat it is the right owner; the floor of three must-fire prompts that actually
fire is not negotiable, and retiring one is a scope cut that owes the cold read step 4 requires. **Record what
is ceded, at the moment it is ceded: the must-not-fire half names the neighbour that now owns the prompt, and
the pin's `result:` says which claim was dropped and to whom.** Territory given up silently is given up twice.
**Re-run it after the last description edit.** `python3 scripts/routing_claims.py lint` fails until the pinned
sha256 of the description and prompt list match disk; the repair is to measure again, never to paste a fresh
hash in.

<!-- doctrine: must-not-half-is-a-gate -->
**A skill that fires on everything is worse than no skill.** The must-not half is a gate the same way: one
that answers every prompt displaces the neighbour that would have handled it, teaching the session to distrust
skill dispatch. Read what the report says *fired*, not just its PASS column — clean means this skill stays out
and the neighbour the section names wins.

<!-- doctrine: unmeasured-is-not-verified -->
**A probe that could not run is never a pass.** No login, no quota, offline: the skill may still ship, but
marked unmeasured, where the next session will read it — the pin records `measured: never`, `model: n/a`,
`cli: n/a`, `runs: 0`, `result: unmeasured`; the close message names it; and here the name goes into
`UNVERIFIED` in `tests/test_routing_claims.py`, a debt ledger that may only shrink. What is forbidden is the
silent promotion. **The gate proves a claim at a moment; it cannot keep it true.** A claim can go false with
no commit anywhere near it — `stale-artifact-check` lost its prompts to a skill in a *different package* — so
the pin records a date and a CLI version, and a clean gate is a reading, not a property.

**6. Close it, then answer the two questions that make the forge countable.** `skillforge done "<outcome>"`
closes the record and links the skill at the level step 1 chose (section 4). It leaves a debt; pay it in the
same turn, from the same evidence:

```bash
skillforge apply   --name <skill> --outcome used|declined --evidence "<verbatim>"
skillforge verdict --name <skill> --verdict WORKED|NO-OP|MISFIRED --evidence "<verbatim>" \
  --use-session "$CLAUDE_CODE_SESSION_ID"
```

`apply` says the skill was put on the problem that caused it; `verdict` says what happened when it was.
**WORKED**: the acceptance test got through and you can quote the line. **NO-OP**: followed, and changed
nothing a session would not have done anyway. **MISFIRED**: it told you something wrong, which is section 3's
input. `--evidence` is mandatory for all three, and `--outcome declined` is a first-class answer.

<!-- doctrine: verdict-follows-the-apply -->
**A verdict is recorded after the skill has been applied to the problem that caused it, never before.** A
verdict written from the draft judges a text; written after the application it judges an event, with a quote
behind it.

**Proposing it upstream is a separate decision, later.** `contribute-skill` owns that flow, running
`skillcontrib recon <name>` for the dry run and then `skillcontrib propose <name>`, which does level C end to
end. Its bar is clean from this loop **and used again since it was forged**, so it cannot be met on the day.

**On failure — including a forge abandoned mid-loop — quarantine the skill with a report neither agent may
rewrite.** A, C and D each **append a signed section** (B and E too, on a raised budget), and contradictions
are kept and flagged rather than reconciled: a merged narrative hides the most informative thing a failed
forge produces. Archive the pair the way section 3 archives a retirement (`references/retirement.md`).

**When the budget exceeds two rounds: the orchestrator and the judge.** A forge granted a third round is one
whose review traffic is about to fill this thread, and a long forge drifts in ways a two-round forge cannot.
Two stages come back, and only then; both briefs are in `references/pipeline-stages.md`.

**B takes the loop from the granted round on.** Hand it A's framing and the generalised transcript, dead ends
included; the raised budget; the `skillforge step` numbering spelled out; steps 2 to 5 pasted in full; and one
abort condition: **if it has no `Agent` tool it stops and says so immediately**, because an orchestrator that
improvises without one returns a confident "clean" with nothing behind it. Never nest orchestrators; C and D
dispatch nobody.

Do **not** hand a dispatched agent the project, the repository path, or the verbatim trigger; those are the
test set, and the CLI withholds them rather than trusting an agent to: `skillforge show` and `ledger` omit
`root`, `trigger`, `project` and `trigger_verbatim` without `--full`, naming what they left out.

<!-- doctrine: close-ownership -->
**You own `start`, `done` and `fail`; every agent you dispatch owns everything between.** That rule binds on
every forge: at the default budget you call `skillforge step` yourself, and with B in the loop B calls it and
reports an outcome to you — clean, narrowed, or abandoned — when the loop closes.
<!-- doctrine: dispatched-agents-do-not-close -->
**A dispatched agent calls neither `done` nor `fail`.** You make that call. The first close wins and the
second is discarded, silently: a forge closed with `done "ok"` and then sent `fail "again"` answers `already
closed out (status: done); nothing to do`, exits **0**, and appends nothing to the ledger. Check `skillforge
show` yourself when a report is slow.

**E judges the outcome.** Dispatch one more fresh agent — never A, B, C or any D — and hand it the finished
skill, A's step-1 file, A's step-5 verification and, separately, **the verbatim original trigger**, off the
forge record.

<!-- doctrine: e-checks-the-framing -->
**Ask E whether A's framing matches the trigger it came from.** Everything downstream of step 1 inherits that
framing, so a misframing has every later check certifying the wrong thing — including E's own "did this fix
the original issue?", which E would otherwise learn only from A. A "no" there is a failure however good the
skill is. Its other two questions are in `references/pipeline-stages.md`.

## 3. Fixing, documenting, or retiring a skill that did not work

<!-- doctrine: no-silent-workaround -->
**Never silently work around a skill that misfired.** That wastes the same time in every future session.
Escalate in order:

1. **Documentation issue** (procedure right, wording ambiguous): edit the SKILL.md now, with an
   explicit "Do NOT use this when…" note naming the exact wrong turn taken.
2. **Substantive issue** (procedure wrong or outdated): fix it, then **re-run the full pipeline** on
   the fix — A re-registers criteria for the repair, and D is cold as ever.
3. **Retirement** (obsolete, superseded, or unfixable): write the case, then get **independent
   concurrence**.
   <!-- doctrine: neutral-retirement-question -->
   **Ask a second fresh agent the neutral question, *"should this be kept, fixed, or retired?"*,
   never "confirm this deletion".** A leading prompt defeats the check: it tells the reviewer what
   the answer should be, and it will oblige. Retire only on an independent "retire".
   <!-- doctrine: archive-the-source -->
   **Archive the source, not the link.** Most skills here are symlinks, so moving
   `~/.claude/skills/<name>` moves the link and leaves the source for the next install to resurrect.
   <!-- doctrine: never-rm-rf -->
   **Never `rm -rf` a skill.** Spurious deletions must be recoverable. The `realpath` sequence, the
   `git` follow-up and the plugin-cache case are in `references/retirement.md`.

## 3.5 Candidates you are not ready to forge yet

An idea that has not cleared the threshold yet is not lost. Write the marker:

```
★ Skill candidate: <the procedure, and what made it costly, in one paragraph>
```

A `Stop` hook queues that, deduped, for one batched review a week (`skillinsight review`). The queue feeds
this same threshold, never bypasses it, and nothing in it is forged automatically. **A queued candidate is a
tier-0 note until it recurs** — `skillinsight promote <hash> --to note|reminder` writes it down now, and the
forge waits for the second occurrence.

## 4. Hot-reloading, and the record `done` writes

A skill is usable the moment it is linked into the skills directory Claude Code reads. `skillforge done` does
that linking, so **closing the forge is what makes the skill live**, and it writes the skill's `origin` row
once per skill ever, so a re-forge gives no second answer to "how did this get here". **Read the line `done`
prints.** Anything but an install — a name taken, a directory it could not write, no `SKILL.md` found — means
the skill is *not* live, and `skillforge install <name> --skill-dir <dir>` is the retry; an `Unknown skill:
<name>` straight after it is lag, so make any other tool call and retry rather than concluding it failed.
`skillreport skills` says whether the skill has been used again, and the `apply` row step 6 owes stays a debt
`skillforge pending` lists until it is answered. Run the pipeline **during** the session that discovered the
need for it.

Where `done` looks, what the close row records, the project-scope case, the measured lag and the fallback
when a name will not resolve, why that census counts successes only, and what the apply debt does and does
not demand, including the `Stop` hook that raises it once per skill and then lets go, are in
`references/forge-animation.md`.

## Trigger precision

<!-- routing-pin
description-sha256: 7978c6efd2caca28bd8881f136175ef901f0cc558dd79dce6f65abd761630059
prompts-sha256: b0d3fb4da0e6c09f8453979d51221df6812e8d508da59c7ed43cba5e2dccb40d
measured: 2026-09-01
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: partial 8/9 must-fire draws, 9/9 must-not-fire draws over 3 runs; not clean: 'The skill I just used told me to run it from the wrong directory.' 2/3
-->

Should fire:

- "That took four attempts to get the migration ordering right, and we hit the same thing last week on a different table."
- "Before I write this deploy script, is there already something for it?"
- "The skill I just used told me to run it from the wrong directory."

Should NOT fire:

- "Write a skill that does X." That is `superpowers:writing-skills`, which owns authoring.
  This skill decides *whether* to author, and runs the adversarial pipeline around it.
- "Refactor this module." Ordinary work, no repeatable procedure in view.
- "Write a one-off script to rename these files."

**A remark with no referent does not fire this, and should not.** *"That took four attempts
to get the ordering right, and we hit it last week too."*, with no subject named, fires
nothing; naming it fires this. `references/routing-gate.md` carries the measurements, what
each description edit changed, and what one passing run does and does not establish.

## Troubleshooting

`skillforge: command not found` → the CLIs (`skillforge`, `skillnote`, `skillreport`, `skillinsight`,
`skillcontrib`, `skillrepeat`) install to `~/.local/bin/`; put that on `PATH` or call them by full path (as
a plugin they are already on it). Animation or reminder trouble → `references/forge-animation.md`.
