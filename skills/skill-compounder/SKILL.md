---
name: skill-compounder
description: "Use when a skill you just used misfired — it told you the wrong thing (to run from the wrong directory, an outdated command), or fired when it should not have — so it needs fixing or retiring; when deciding whether a repeatable procedure has earned becoming a skill; or when asking, before implementing something new, 'is there already something for this?'. Do NOT use to author a skill already decided on (that is superpowers:writing-skills), for a one-off script, or ordinary refactoring."
---

# Compounding: turn hard-won procedures into permanent capability

Every session should leave the toolchain measurably better than it found it, so the same
problem never gets solved from scratch twice. Three habits, a threshold that keeps the
machinery from costing more than it saves, and a pipeline that forges what clears it.

## 1. Before any major implementation, check for an existing skill

Before writing a plan or the first line of code for anything non-trivial: scan the skill list
injected into this session's prompt; `ls ~/.claude/skills/` (cross-project) and
`ls ./.claude/skills/` (project-local); and when the name is not an obvious match,
`grep -ril '<keyword>' ~/.claude/skills ./.claude/skills ~/.claude/plugins/cache/*/*/*/skills`.

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

Three things override a yes, in order: an existing skill already handles it (section 1); a
single sentence of documentation covers it; the procedure is specific to work finishing now.
In any of those, write a note or update the project's `CLAUDE.md`.

### Forging protocol: A → B → C → (D↔C)ⁿ → A → E

**The original project is held-out test data.** A skill written by the session that needed it
comes out full of references only that session can decode — an incident table nobody else can
check, a command that runs in one checkout. Any agent that sees the project overfits to it. So
one agent, A, holds it and spends that privilege judging the result rather than writing it;
every other stage is denied something the previous one had, and the denials are the mechanism.

|Stage|Who|What it holds|What it owns|
|-|-|-|-|
|**A**|the session that hit the problem|the project, the transcript, the verbatim trigger|pre-registers criteria, dispatches, runs the finished skill against the real case, closes the forge|
|**B**|one orchestrator subagent|A's generalised brief; no project content|scope level, the round cap, the loop|
|**C**|builder subagent, scratch directory|B's brief; no path into the project|writes the skill, builds a runnable reproduction, runs every command it documents|
|**D**|a **new** cold red-teamer every round|the skill file, and nothing else|infers a scenario from the skill alone and executes it|
|**E**|a fresh judge, never A, B, C or D|the verbatim trigger, A's framing, A's verification|the outcome verdict and the disposal|

The brief to hand each agent, and what each must return, is in
`references/pipeline-stages.md`. Below is what cannot be delegated to a reference file,
because getting it wrong is invisible from the outside.

<!-- doctrine: announce-the-forge -->
**0. Announce it, and show the work. The user must never discover a forge after the fact.** Say
in plain text what the skill is and why it cleared the threshold, then start the animation:

```
skillforge start <name> <total-steps> "<one-line summary>" \
  --trigger "<the verbatim text that set this forge off>" \
  --trigger-kind <user-prompt|hook-checkpoint|review-dispatch|agent-decision>
```

**`--trigger` is not optional in this protocol, even though the CLI only warns.** It is the one
ledger question nothing can recover afterwards, and it carries the quote to stage E on disk,
through a compaction of this thread. Paste it; do not summarise. `--trigger-kind` says who was
asking (`references/forge-animation.md`).

<!-- doctrine: concurrent-forges -->
**Just start it.** Concurrent forges are fine — each gets its own record and its own slot in
the status line, and starting one never disturbs another. `skillforge start` exits 2 when the
name is held by a live forge, and the refusal says how long since it last stepped. Close a dead
one with `skillforge fail --name <forge> <reason>` or `skillforge clear --name <forge>`, never
`done`. With several live, `step`, `done` and `fail` refuse to guess: pass `--name <forge>`.

**Decide the round cap here**, because `<total-steps>` encodes it and `skillforge` cannot be
told later: budget `2 + 2 × (planned D rounds)`, so **12** at the usual 5-round cap and **22**
at 10. Overrunning is fine and visible — keep stepping past the budget rather than
re-budgeting, which no command can do. What each step number means, how `rounds` is inverted
back out of it, and the overrun display are in `references/forge-animation.md`.

**1. A: pre-register, in writing, before anything is dispatched.** This is what makes
goalpost-moving impossible, and goalpost-moving is the recurring failure this pipeline is
built against. Before dispatching B, write to a file:

- the **verbatim original trigger**: the text passed to `--trigger`, copied, not summarised.
- **A's framing**: the general procedure in one paragraph, with the project taken out of it.
  This is what B and C are allowed to see, and E audits it.
- the **success criteria**: what the finished skill must let a session do, stated so a
  stranger can score each one yes or no. One is standing, on every forge:
  <!-- doctrine: state-the-cost-bound -->
  **The skill must state when it is not worth its own cost.** The reader who already suspects
  they do not need it is the one who abandons it halfway and does not say so, and the exit ramp
  is one sentence.
- the **acceptance test**: the original triggering problem, written out to attempt again
  with the finished skill at step 7.

**On disk, not in context** — `~/.claude/skill-compounder/briefs/<name>.md`, any editor or a
heredoc. A full run can outlive a compaction of this thread, and criteria held only in context
are gone at that moment: the pipeline degrades into "the builder wrote something and it looked
fine", the process it replaced. The file is re-read at step 7.

<!-- doctrine: orchestrator-runs-the-rounds -->
**2. Hand the loop to B, and get your thread back. The session that starts a forge does
not run it.** Dispatch one subagent whose whole job is to run this forge, then return to
whatever you were doing. It reports back when the loop closes.

Running the rounds from the main thread is what makes forging feel expensive, and blocking is
not the reason — the agents already run in the background. The cost is that every report and
every revision brief passes through your context, filling the thread the user is talking to
with review traffic they did not ask to read; the findings are not what anyone needed to keep.

**B is the orchestrator, not a fourth agent.** It decides scope, dispatches C and D, and
confirms every fix by running it rather than trusting the report — builders here have reported
fixes that were not made. A subagent can itself dispatch subagents, but one level further down
availability is inconsistent, so **use exactly one orchestrator layer and never nest them**; C
and D dispatch nobody (`docs/CLAUDE-CODE-BEHAVIOR.md`). Invoking this skill from *inside* a
subagent already puts B in that inconsistent band: run the rounds yourself from step 3.

Do **not** hand B the project, the repository path, or the verbatim trigger; those are the test
set, and the CLI withholds them rather than trusting B to: `skillforge show` and `ledger` omit
`root`, `trigger`, `project` and `trigger_verbatim` without `--full`, naming what they left out.
Hand it: A's framing and the generalised transcript, **dead ends included**; the round cap; the
`skillforge step` numbering **spelled out** (`references/forge-animation.md`); steps 3 to 7
**pasted in full**, so it does not read step 2 and nest a second orchestrator; and one abort
condition: **if it has no `Agent` tool it stops and says so immediately.** An orchestrator that
cannot dispatch but improvises anyway returns a confident "clean" with no adversarial review
behind it — the one failure of this protocol invisible from the outside. If it aborts you already hold an open forge:
run the rounds yourself, or `skillforge fail "orchestrator could not dispatch"` and start again.

<!-- doctrine: standard-is-not-project-content -->
**Isolation withholds the project, never the authoring standard.** Hand B the required sections,
the caps, and that a routing gate runs six declared prompts — as text, never as a path into this
repository. Withholding it cost a forge its gate: a draft with no `## Trigger precision` section
and nothing to run (`references/pipeline-stages.md`).

<!-- doctrine: close-ownership -->
**You own `start`, `done` and `fail`; the orchestrator owns everything between.** You
announce the forge and call `skillforge start`. B calls `skillforge step` as it goes, and
when the loop closes it *reports an outcome to you* — clean, narrowed, or abandoned.

<!-- doctrine: orchestrator-does-not-close -->
**The orchestrator calls neither `done` nor
`fail`.** You make that call, once E has reported. This is not bookkeeping fussiness: the first
close wins and the second is discarded, silently. Verified by running it — a forge closed with
`done "ok"` and then sent `fail "again"` answers `already closed out (status: done); nothing to
do`, exits **0**, and appends nothing to the ledger. Check `skillforge show` yourself when a
report is slow: an orchestrator that dies mid-loop leaves a forge you can still close.

<!-- doctrine: quiesce-before-reading -->
**Nothing reads a draft while its author is still writing it.** Upward: do not edit B's files,
commit, or read a test run as a verdict while B works. Downward, the half that gets forgotten:
B confirms C is **idle** before any reviewer, gate or acceptance test reads the draft, by
something observable — never by a message claiming so. An acceptance tester once scored a
moving target this way; `references/pipeline-stages.md` carries both halves.

**3. B: place the skill at the highest level it applies to, then set the cap.** The hierarchy
is general > user > project.

<!-- doctrine: highest-applicable-level -->
**A skill belongs at the highest level of the hierarchy to which it applies, and must be
written generally enough to apply beyond the case that prompted it.** A project skill has to
work beyond the specific task; a user skill beyond the specific project; a general skill
beyond both. Placement is a claim about how far the procedure reaches, and it has to survive
being written down.

<!-- doctrine: specialisation-not-baked-in -->
**The specialisation comes from the project's or the user's `CLAUDE.md` and the constraints
already recorded there — never from text baked into the skill.** A skill that hardcodes one
repository's test command has made a project's particulars everyone's; the same skill saying "run
the project's suite" reads that particular out of the `CLAUDE.md` that already states it. B also
fixes the D-loop cap here, and records how routing will be verified at the chosen level, since
where a skill installs decides which router sees it.

**4. C: build it in a scratch directory, and run everything it claims.** Dispatch a subagent
and tell it to invoke **`skill-authoring`**, which ships with this package and is therefore
present wherever this skill is. Name it explicitly: an earlier version of this step said
`skill-creator` and `writing-skills`, and neither bare name resolves — they exist only as
`compound-engineering:skill-creator` and `superpowers:writing-skills`, inside plugins a fresh
install does not carry — so a cold session followed the instruction and found nothing.

**Isolation is structural, not tidiness.** Hand C a scratch directory and no path into the
project: "do not look at the project" is a sentence, and sentences get read past, so what C is
*given* is the enforcement. A builder that can see the held-out case writes to it, and the
skill then works there and nowhere else.
<!-- doctrine: boundary-without-the-address -->
**Where a boundary must still be stated, describe what it encloses and never name what lies
outside it.** "Read nothing outside your scratch directory" is checked exactly the way naming
the path is — grep the transcript, expect zero — while a brief forbidding a path has handed over
the held-out data's address in the act of forbidding it. But C is isolated from the *project*,
never from *execution*: so C **builds a minimal runnable reproduction** from B's brief and
verifies every command it documents against it. If C cannot construct a repro that is a finding
rather than a licence to proceed — the brief was too abstract to be executable.

**Then verify the draft parses, before anyone reviews it.** A skill can pass every review round
on its content and still ship inert, and nothing built in catches it: `claude plugin validate
--strict` **does not read SKILL.md frontmatter at all** — frontmatter raising `yaml.ScannerError`
still gets `✔ Validation passed`, exit 0. Run `skill-authoring` Phase 3's Gate A, or the short
version in `references/pipeline-stages.md`; do not read it and conclude it would pass. The
commonest break is an **unquoted `: ` in the description**, which costs the parser that key and
leaves the skill installed, named, and unable to fire.

**5. D: a cold red-teamer, one per round.** Dispatch a **separate, fresh** subagent, never C.

<!-- doctrine: no-forked-reviewer -->
**The red-teamer must never be a fork of either layer** — not of the orchestrator that
dispatches it, and not of the session that dispatched the orchestrator. A forked red-teamer
already knows what the skill was *meant* to say, so it cannot detect the ambiguity that will
bite a cold session six weeks from now.

<!-- doctrine: d-infers-the-scenario -->
**D is given the skill and nothing else, and must infer
for itself what situation the skill is for.** Not B's brief, not C's reasoning, not the original
intent. The inference is the completeness check: a skill whose scenario cannot be reconstructed
from its own text has a hanging reference in it, the exact defect this pipeline exists to remove.
A scenario D infers may not match the original intent, and that is a feature rather than a miss —
it is how a skill reaches further than the case that prompted it. D then executes what it
inferred, using the skill, and reports where the skill fails, misleads, or under-specifies.

<!-- doctrine: no-leading-prompt -->
**Never hand a reviewer a list of what not to flag.** Same failure as asking it to "confirm
the deletion", and easier to commit because it feels like helpfulness — the A/B behind that is
in `references/pipeline-stages.md`. State the standard; do not enumerate the exceptions. Asking
for hard verification is fine — "run every command" constrains method, not conclusions.
D's checklist:

|Check|What it catches|
|-|-|
|**Inferred scenario**|Can D say what this skill is for, from the skill alone? A guess it cannot make is a hanging reference.|
|**Cold start**|Can step 1 be executed with no prior context and no clarifying question?|
|**Trigger precision**|**Run** the section's 3 must-fire and 3 must-not-fire prompts through real `claude -p --model sonnet` sessions, per step 7. Nothing has installed the draft yet, so copy it to `<scratch>/.claude/skills/<name>/SKILL.md` and run each prompt with that scratch directory as the working directory: a headless run started there sees a project skill, and only there. A row with no observed `Skill` call behind it is a finding.|
|**Verified claims**|Actually run every command, path, and API call the skill asserts. Unverified claims are defects.|
|**Portability**|Does any example need a project D cannot see? That is the contamination the isolation was for.|
|**Unhappy path**|What does a session do when a step fails partway through?|
|**Overlap**|Does an existing skill already cover this? If so, that is a blocking finding.|
|**Scope**|Is it doing more than one thing? Split or narrow.|

**6. Loop C and D.** Feed findings back to C so it keeps its context and its scratch repro,
and poll for an artifact rather than block on a reply (`references/pipeline-stages.md`).
<!-- doctrine: fresh-reviewer-each-round -->
**Spawn a new red-teamer each round; the whole test depends on the reader being
genuinely cold.** Repeat until the report comes back clean.

**Cap at 5 rounds, or 10 for a skill that is complex or genuinely important**, chosen at step 0
because `<total-steps>` encodes it. Where 5 comes from, and when to raise it, are in
`references/round-cap.md`: a better guess than 3, still a guess.

<!-- doctrine: assess-convergence-every-round -->
**Decide whether the loop is converging at every round, not at the cap.** A cap reached is not
a decision point, it is the moment the budget for making one ran out — narrowing there changes
what the skill is *and* leaves that change with no round left to review it. So B appends one
line per round to `~/.claude/skill-compounder/rounds/<forge>.tsv`, never to `briefs/`:

```
<n>	blocking=<k>	total=<m>	subsystems=<what they named>	shapes=<the finding shapes>
```

`blocking` is **B's** call, one test — would shipping with this make the skill do the wrong
thing for a stranger? — because D is asked for findings, not severities, and a fresh D each
round cannot share a scale with the last.

<!-- doctrine: the-assessment-binds-from-round-three -->
**The assessment binds from round 3 and not before**, because every signal below needs three
points and a rule that fires on one round is a licence to quit after one. *Converging* — a
falling blocking count over rounds naming **different** subsystems — means continue at full
scope and overrun the cap rather than cut to fit it. Anything else is *not converging*: the
count flat or rising across three rounds, one subsystem producing findings whatever gets
patched, one finding **shape** recurring under different wordings, or a trajectory answering
to none of these. Then the design is wrong rather than the wording, and the choice is due at
once: **narrow**, cutting the subsystem the findings keep naming and preferring a skill that
already owns that question, or **abandon**, with notes on what blocked it. B reports
"abandoned" and the reason to you, and does not call `fail` itself.

<!-- doctrine: narrowing-restarts-the-review -->
**A narrowed skill is a new skill for review purposes: the rounds already spent certify a
skill that no longer exists.** So a narrowed draft **re-enters the loop at step 4**: C cuts
it, a **new** cold D reviews the result, and B may not report it clean until a D that saw the
narrowed skill says so. **B writes that cost into the round record before cutting** — narrowing
without rounds left for it is abandoning with extra steps, and saying so on the record is what
stops it being decided by whoever is most tired. How to read the record for either verdict, and
a worked case, are in `references/round-cap.md`.

**Step 7 is a scope cut too**, and B is gone by then, so the rule reads differently there:
retiring a must-fire claim narrows what the skill owns, so **A** re-runs the routing gate *and*
dispatches one fresh cold reader against the narrowed trigger contract before closing.

**7. A: run the skill against the real case, and score the pre-registered criteria.** You alone
have seen both the project and the finished skill, so this is the only place "did it actually
solve the thing that started this" can be asked. Re-read the step-1 file, not your memory, and:

- **move the clean draft into place first**: it is still in C's scratch directory, and `done`
  looks only under `<repo>/skills/<name>/`, `<repo>/.claude/skills/<name>/`, or `--skill-dir`
  from `start`. B reports that path and never learns the destination, so the copy is yours;
- **attempt the original triggering problem again, with the skill**, and say what happened;
- score each success criterion as written — one that now looks wrong is a finding for E,
  never a criterion to edit;
- keep this verification in your notes and out of the SKILL.md: it is evidence about this
  forge, not instruction for a stranger.

<!-- doctrine: routing-gate-on-completion -->
**A forge cannot be reported clean while the skill's own must-fire prompts do not fire
it.** A reviewer reading the section and agreeing it looks right is not this check: every seed
skill here passed a full loop that way and three of their claims turned out false when the
prompts were finally run (`references/routing-gate.md`). So the draft needs at least three
prompts that must fire it and three that must not, each the verbatim utterance a user would
type — a paraphrase cannot be run — and then they get run. Inside a checkout of this:

```bash
SKILL_ROUTING_PROBE=1 python3 scripts/probe_routing_claims.py <skill>
```

Anywhere else the script cannot help — it reads only that tree — so run each prompt yourself
in an empty directory and look for a `Skill` call naming the skill:

```bash
claude -p --model sonnet --max-turns 3 --output-format stream-json --verbose "<prompt>" \
  | grep -o '"name":"Skill","input":{[^}]*}'
```

**A non-zero exit is not a failed measurement:** `--max-turns` exhaustion and a denied
permission both exit 1, after the routing decision. **`--model sonnet`, never haiku** —
personal and project skill descriptions were measured absent from the router on haiku. Cost
is one call per prompt per draw: one six-prompt skill is 18 calls at the floor, and the ten
pinned skills are 60 prompts, so **180 calls** and ~12 minutes. Measured 2026-08-31, CLI
2.1.252, over that whole 180-draw pass: 7-72s a draw, median 22s, 688s wall, six in parallel.

**One run is one draw, and a draw is not a verdict.** Routing is stochastic: one unchanged
description here gave 3/3, then 1/3, then 2/3, and this skill's own six prompts, probed three
times in one day with nothing edited between, gave 9/9, then 8/9, then 9/9. So the gate is
**at least three runs of the whole section**, a floor for *detecting* that spread rather than
a score that earns `verified`. The pin records `runs: N` and a k/N per prompt; `partial` names any prompt that
split, and a prompt at 2/3 has not passed, it has been shown unreliable.

**When a must-fire prompt loses, the description is what changes.** Not the prompt and not the
verdict; routing is brutally sensitive to the opening clause, so this is usually a small edit
with a large effect — changing `"Use before debugging logic"` to `"Use before any other debugging
step"` flipped a losing prompt to a winning one. Four words. Retiring a claim is allowed only when the
prompt names a trigger this skill should not own *and* the skill that beat it is the right
owner; the floor of three must-fire prompts that actually fire is not negotiable, and retiring
one is a scope cut that owes the cold read step 6 requires. **Record what is ceded, at the
moment it is ceded: the must-not-fire half names the neighbour that now owns
the prompt, and the pin's `result:` says which claim was dropped and to whom.** Territory given
up silently is given up twice. **Re-run it after the last description edit.** `python3
scripts/routing_claims.py lint` fails until the pinned sha256 of the description and prompt
list match disk; the repair is to measure again, never to paste a fresh hash in.

<!-- doctrine: must-not-half-is-a-gate -->
**A skill that fires on everything is worse than no skill.** The must-not half is a gate the
same way: one that answers every prompt displaces the neighbour that would have handled it,
teaching the session to distrust skill dispatch. Read what the report says *fired*, not just
its PASS column — clean means this skill stays out and the neighbour the section names wins.

<!-- doctrine: unmeasured-is-not-verified -->
**A probe that could not run is never a pass.** No login, no quota, offline: the skill may
still ship, but marked unmeasured, where the next session will read it — the pin records
`measured: never`, `model: n/a`, `cli: n/a`, `runs: 0`, `result: unmeasured`; the close
message names it; and here the name goes into `UNVERIFIED` in `tests/test_routing_claims.py`,
a debt ledger that may only shrink. What is forbidden is the silent promotion. **The gate proves a claim at a moment; it cannot keep it true.** A claim can
go false with no commit anywhere near it — `stale-artifact-check` lost its prompts to a skill
in a *different package* — or with nothing changed at all, so the pin records a date and a CLI
version, re-running is the only detection, and a clean gate is a reading, not a property.

**8. E: judge the outcome, and dispose of it.** Dispatch one more fresh agent — never A, B, C or
any D — and hand it the finished skill, A's step-1 file, A's step-7 verification, and,
separately, **the verbatim original trigger on its own**, off the forge record.

<!-- doctrine: e-checks-the-framing -->
**Ask E whether A's framing matches the trigger it came from.** Everything downstream of step 1
inherits that framing, so a misframing has every later check certifying the wrong thing —
including E's own "did this fix the original issue?", which E would otherwise learn only from A.
Handing E the trigger verbatim is the one place that error can surface. Its three questions:

1. Does A's framing match the verbatim trigger, or has the problem drifted?
2. Does the skill meet the pre-registered criteria as written?
3. Would a stranger, given only this skill, get through the acceptance test?

A "no" to question 1 is a failure however good the skill is, and the note saying so is what
stops the same misframing being forged again next month.

**On success, install at B's level**, and let `skillforge done` do the linking (section 4):
general and user land in `~/.claude/skills/<name>/`, project in `<repo>/.claude/skills/<name>/`,
committed.

**Proposing it upstream is a separate decision, later.** `contribute-skill` owns that flow; do
not rebuild any of it. Its bar is clean from this loop **and used again since it was forged**, so
it cannot be met on the day: E records "propose upstream" as a recommendation.

**On failure — including a forge abandoned mid-loop, which never reaches E — quarantine the
skill with a report neither agent may rewrite.** A, B, C and D each **append a signed
section**, edited by nobody else, and contradictions are kept and flagged rather than
reconciled: a merged narrative hides disagreement, the most informative thing a failed forge
produces. Then archive the pair the way section 3 archives a retirement
(`references/retirement.md`).

## 3. Fixing, documenting, or retiring a skill that did not work

<!-- doctrine: no-silent-workaround -->
**Never silently work around a skill that misfired.** That wastes the same time in every future
session. Escalate in order:

1. **Documentation issue** (procedure right, wording ambiguous): edit the SKILL.md now, with
   an explicit "Do NOT use this when…" note naming the exact wrong turn taken.
2. **Substantive issue** (procedure wrong or outdated): fix it, then **re-run the full
   pipeline** on the fix — A re-registers criteria for the repair, and D is cold as ever.
3. **Retirement** (obsolete, superseded, or unfixable): write the case, then get
   **independent concurrence**.
   <!-- doctrine: neutral-retirement-question -->
   **Ask a second fresh agent the neutral question, *"should this be kept, fixed, or
   retired?"*, never "confirm this deletion".** A leading prompt defeats the check: it tells
   the reviewer what the answer should be, and it will oblige. Retire only on an independent
   "retire"; on keep or fix, do that.
   <!-- doctrine: archive-the-source -->
   **Archive the source, not the link.** Most skills here are symlinks, so moving
   `~/.claude/skills/<name>` moves the link and leaves the source for the next install to
   resurrect.
   <!-- doctrine: never-rm-rf -->
   **Never `rm -rf` a skill.** Spurious deletions must be recoverable. The `realpath`
   sequence, the `git` follow-up and the plugin-cache case are in
   `references/retirement.md`.

## 3.5 Candidates you are not ready to forge yet

Not every good idea clears the threshold when it arrives. Rather than losing it or forging
something premature, write the marker:

```
★ Skill candidate: <the procedure, and what made it costly, in one paragraph>
```

A `Stop` hook queues that, deduped, for one batched review a week (`skillinsight review`). The
queue feeds this same threshold, never bypasses it, and nothing in it is forged automatically.

## 4. Hot-reloading, and the record `done` writes

A skill is usable the moment it is linked into the skills directory Claude Code reads.
`skillforge done` does that linking, so **closing the forge is what makes the skill live** —
the skill is usable in the session that forged it, which is the whole reason to forge it there.
Closing also writes the skill's `origin` row, once per skill ever, so a re-forge gives no
second answer to "how did this get here".

- `done` prints what it installed and where. **Read that line.** Anything else — a name taken,
  a directory it could not write, no `SKILL.md` found — means the skill is *not* live, and
  `skillforge install <name> --skill-dir <dir>` is the retry.
- **Lag.** If `Skill` answers `Unknown skill: <name>` right after `done`, make any other tool
  call and retry rather than concluding it failed; a subagent dispatched after the install sees
  it with no lag at all. Fallback: `cat` the SKILL.md and follow it by path.
- **Did it get used again?** `skillreport skills` prints the ledger's questions per skill. A
  *failed* invocation reaches no hook, so it counts successes only.
- **Was it used on the problem that caused it?** That is a fifth question and a separate row:
  `skillforge apply --name <skill> --outcome used|declined --evidence "<verbatim>"`. Until it is
  answered the forge carries a debt, `skillforge pending` lists it, and a `Stop` hook blocks the
  forging session's turn **once per skill, then lets go** — a flag you cannot miss, not a wall.
- Run the pipeline **during** the session that discovered the need for it; deferring to
  "next session" throws the benefit away.

Where `done` looks, what the close row records, the project-scope case, the measured lag, and
what the apply debt does and does not demand are in `references/forge-animation.md`.

## Trigger precision

<!-- routing-pin
description-sha256: 7978c6efd2caca28bd8881f136175ef901f0cc558dd79dce6f65abd761630059
prompts-sha256: b0d3fb4da0e6c09f8453979d51221df6812e8d508da59c7ed43cba5e2dccb40d
measured: 2026-08-31
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

`skillforge: command not found` → the CLIs (`skillforge`, `skillreport`, `skillinsight`,
`skillcontrib`) install to `~/.local/bin/`; put that on `PATH` or call them by full path (as a
plugin they are already on it). Animation or reminder trouble → `references/forge-animation.md`.
