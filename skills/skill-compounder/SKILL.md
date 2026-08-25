---
name: skill-compounder
description: "Use when deciding whether a repeatable procedure has earned becoming a skill, when starting a major implementation (to check for an existing skill first), or when a skill you invoked misfired and needs fixing, documenting, or retiring. Runs a builder plus cold red-team subagent loop to a clean report. Do NOT use to author a skill you have already decided on (that is writing-skills), for a one-off script, or for ordinary refactoring."
---

# Compounding: turn hard-won procedures into permanent capability

Every session should leave the toolchain measurably better than it found it, so the same
problem never gets solved from scratch twice. There are three habits to keep up, and a
threshold that keeps the machinery from costing more than it saves.

## 1. Before any major implementation, check for an existing skill

Before writing a plan or the first line of code for anything non-trivial:

1. Scan the skill list injected into this session's prompt.
2. `ls ~/.claude/skills/` (cross-project) and `ls ./.claude/skills/` (project-local).
3. `grep -ril '<keyword>' ~/.claude/skills ./.claude/skills ~/.claude/plugins/cache/*/*/*/skills`
   when the name is not an obvious match.

<!-- doctrine: invoke-do-not-reimplement -->

**If a plausible skill exists, invoke it. Do not reimplement.** If it turns out to be the
wrong tool, that is useful signal: go to section 3.

## 2. During work: is this pattern worth crystallizing?

Keep asking: *is what I am doing right now a repeatable procedure?* Good candidates are a
debugging workflow that finally worked, a deploy-and-verify sequence, a non-obvious API
dance, a project-specific build+test+screenshot loop.

**Threshold (BOTH must hold).** Forging a skill costs several subagent rounds, so be
selective:

- **Costly.** Name the specific dead end, in one sentence, and say what a fresh session
  would have done instead. If you cannot name it, it was not costly; it was just work.
- **Recurring.** Point at the second occurrence. A prior session, an earlier point in this
  one, or an open issue. "It seems like the sort of thing that recurs" is not a second
  occurrence.

<!-- doctrine: both-conditions -->
**Both must hold, or it gets a note rather than a skill.** Both need a **concrete
referent**, not a judgement, because both conditions are otherwise
loose enough to say yes to nearly any non-trivial work, and a threshold that always
resolves to yes is worse than none. Write the two sentences down before deciding; if
either one is hard to write, that is the answer.

These three override a yes, in order: an existing skill already handles it (section 1); a
single sentence of documentation covers it; the procedure is specific to work that is
finishing now. In any of those cases write a note or update the project's `CLAUDE.md`.

**Where it lives:** generalizes across projects → `~/.claude/skills/<name>/SKILL.md`.
Specific to one repo → `<repo>/.claude/skills/<name>/SKILL.md`, committed.

### Forging protocol (an orchestrator, a builder, a red-teamer; adversarial, looped)

<!-- doctrine: announce-the-forge -->
**0. Announce it, and show the work. The user must never discover a forge after the
fact.** Say in plain text what the skill is and why it cleared the threshold, then start the
live status-line animation:

<!-- doctrine: concurrent-forges -->
**Just start it.** Concurrent forges are fine — each gets its own record and its own slot in
the status line, and starting one never disturbs another. There is nothing to check first. If
`skillforge start` exits 2 saying a forge of that name is already live, the name is taken by
a forge that is still running: pick a different name, or close the other one with
`skillforge done --name <forge>`. Do not run the loop unanimated to avoid a collision; that
costs a ledger row and buys nothing. While more than one forge is live, `skillforge step`,
`done` and `fail` refuse to guess which one you mean, so pass `--name <forge>` on every call
after your `start` — with a single forge running, the bare form is still correct.
`skillforge list` shows what is live.

```
skillforge start <name> <total-steps> "<one-line summary>"
```

**Decide the round cap here, before you start**, because `<total-steps>` encodes it and
`skillforge` cannot be told later. Budget `<total-steps>` as `2 + 2 × (planned red-team
rounds)`: one step to dispatch the builder, one for its draft, then a review step and a
revision step per planned round. The frontmatter check in step 3 does **not** get its own
number — it is part of accepting the draft, and the budget has no slot for it. So 12 for the usual 5-round cap, or 22 if you have raised
it to 10 (step 6 says when that is justified; say why in the announcement). Dispatching the
orchestrator is **not** a step — the numbering starts at the builder, because
the ledger and `skillreport` both invert this budget to recover round counts — planned
rounds as `(steps - 2) / 2`, and completed rounds the same way from the step actually
reached — so an extra step shifts every count.

The count is a budget, not a prediction, and a forge that comes back clean early simply
stops short; `skillforge done` snaps the bar to full.

**If you run past the budget, keep stepping.** `skillforge step 15 "round 7 review"`
records 15 against a 12-step budget rather than clamping it: the status line draws
`15/12 over` with the bar's last cell marked `»`, and the ledger's `rounds` counts what
you actually completed. The overrun is visible; you do not have to narrate it.

There is still no way to re-budget. `start` is the only command that sets the total, and
it refuses a name that is already live — verified by running it: exit 2, and nothing
written, not a state slot, not a ledger row.

So, when you pass it:

- **Read it as the cap, not as a bookkeeping nuisance.** `<total-steps>` encodes the round
  cap you chose at step 0, so overrunning it means you are past the cap, and step 6
  applies: narrow the scope until it is clean, or abandon it.
- **Do not free the name by closing the forge first.** That records an outcome for work
  that has not finished, which is worse than the overrun.
- Put the real round count in the `done` or `fail` message anyway. `rounds` is derived
  from the step reached, so a round you ran without spending a step on it still will not
  appear, and the message is where a human reads it. The one skill forged end to end here
  did exactly that: its close message reads "shipped after 7 builder rounds and 7 red-team
  rounds" against a `rounds: 5`, because that forge never stepped past its budget.

`skillforge step <n> "<what is happening right now>"` is called at **every** transition —
by the orchestrator once you have dispatched it, so hand it the numbering above. Always
close with `skillforge done "<outcome>"` or `skillforge fail "<why>"`. A forge left open
strands a spinner in the user's status line; `skillforge clear` is the escape hatch, and it
records the forge as abandoned rather than dropping it.

**Nothing about the animation ever needs a session restart.** The bar is a JSON record
repainted once a second, so a wrong or stranded bar is always fixed by a command, never by
restarting and never by editing a file by hand. `skillforge list` shows what is live.

Three commands close a forge, and they are not interchangeable:

|Command|What the bar does|What the ledger records|
|-|-|-|
|`skillforge done "<outcome>"`|shows `✓ forged`, then clears itself|completion|
|`skillforge fail "<why>"`|shows `✗` and the reason, then clears itself|failure|
|`skillforge clear`|disappears immediately|**abandoned**|

**`clear` is not a tidy-up, and picking the honest one matters more than clearing the
bar.** `skillreport` reads that ledger to answer whether forged skills get reused, so
clearing a forge whose work actually finished writes a false abandonment into the only
record of whether this protocol pays for itself. Close finished work with `done` and
blocked work with `fail`; reach for `clear` only when neither is true, such as a forge
stranded by a session that died. Pass `--name <forge>` to any of the three while more than
one forge is live. After `done` or `fail` the record clears itself on its own timer, so
there is nothing to delete and nothing to check.

Every start, done and fail appends to a local ledger, so an abandoned forge is as visible
as a finished one. `skillreport` later joins that against your transcripts to answer the
only question that matters about this protocol: did the skill ever get used again.

<!-- doctrine: orchestrator-runs-the-rounds -->
**1. Hand the loop to an orchestrator, and get your thread back.** The session that starts
a forge does not run it. Dispatch one subagent whose whole job is to run this forge, then return to
whatever you were doing. It reports back when the loop closes.

Running the rounds from the main thread is what makes forging feel expensive, and blocking
is not the reason. The agents already run in the background. The cost is that every report
lands in your context and every revision brief is written out of it, so the thread the user
is talking to fills up with review traffic they did not ask to read. That is what prompted
this change: a multi-round forge in this repo consumed most of a session that way. The
ledger does not record session cost, so treat that as the reported experience it is rather
than a measurement. The findings are not what anyone needed to keep. The finished skill is.

A subagent dispatched by the main session can itself dispatch subagents: probed three
times, it had the `Agent` tool every time and its children ran. `skillforge` is on its
`PATH` in every probe too, so the orchestrator drives the animation while it works. Note
that a child *running* and its result *arriving* are separate things — in one probe two
children ran to completion but neither result was ever delivered, and the answers had to be
recovered from the task output files. Build in a way to check on a child that goes quiet
rather than assuming it died.

That one level is the whole requirement — the orchestrator dispatches; its builder and
red-teamers dispatch nobody. The probes behind this paragraph, and their limits, are
recorded in `docs/CLAUDE-CODE-BEHAVIOR.md` in the `claude-skill-compounder` repo.

**One level further down, availability is inconsistent.** Probing depth two, one agent had
`Agent` and dispatched a child successfully; another reported the identical tool list
*minus* `Agent`, with no dispatch tool loaded or deferred. No rule was found that predicts
which. So: **use exactly one orchestrator layer, and never nest orchestrators.** The
orchestrator runs the rounds itself; it does not hand the loop on again.

The same caution applies if you are invoking this skill from *inside* a subagent already —
your orchestrator would start one level deeper, in the inconsistent band. Do not assume the
hand-off works: run the rounds yourself from step 2, keeping the announcement and the close
where they are.

Hand it:

- the skill's name and target path, and the concrete transcript of what worked, dead ends
  included
- how many rounds it may spend, and **the animation numbering, spelled out**. The numbered
  headings in this section are prose sections, not `skillforge step` numbers, and since the
  renumber they no longer coincide — do not hand over "the step numbering" and hope. Write
  it out: `step 1` when the builder is dispatched, `step 2` when its draft lands and has
  passed the frontmatter check, then `step 3`/`step 4` for the first review and revision,
  `step 5`/`step 6` for the second, and so on. Note the collision this invites: protocol
  step 3 is the frontmatter check, but `skillforge step 3` is the first red-team review.
  They are different numbers in different sequences, which is why you spell the animation
  one out instead of saying "the step numbers". An orchestrator that instead calls `skillforge step 2..5` after the pasted
  section headings stalls the bar and makes `(step - 2) / 2` record one round where five
  happened.
- steps 2 to 6 below, **pasted in full** rather than referenced. Do not tell it to "follow
  skill-compounder": it would read step 1, try to hand off again, and nest a second
  orchestrator into the band where `Agent` may not exist. They are its instructions rather
  than yours, minus the closing calls, which stay with you (see below).
- an explicit abort condition: **if it has no `Agent` tool, it stops and says so
  immediately.** It must not write the skill itself, and it must not review its own draft.
  An orchestrator that cannot dispatch but improvises anyway returns a confident "clean"
  with no adversarial review behind it, and you would call `skillforge done` on nothing.
  This is the one failure of this protocol that is invisible from the outside.
  **If it does abort, you already hold an open forge**, so do not leave it: either run the
  rounds yourself from step 2 and close normally, or `skillforge fail "orchestrator could
  not dispatch"` and start again. Do not re-dispatch a second orchestrator hoping for a
  better draw — availability was not random in any probe, and you would be guessing.
- one standing rule: it confirms a fix by running it, never by trusting the report that
  claims it. Builders in this loop have reported fixes that were not made, and figures that
  did not reproduce. Observed while forging this very section: an agent asked to probe a
  platform behaviour reported a child's answer verbatim, with timing stats, before that
  child had replied, and retracted the whole thing as fabricated when asked again. A report
  is a claim about the world, and the orchestrator's job is to check it against the world.

<!-- doctrine: close-ownership -->
**You own `start`, `done` and `fail`; the orchestrator owns everything between.** You
announce the forge and call `skillforge start`. The orchestrator calls `skillforge step`
as it goes, and when the loop closes it *reports an outcome to you* — clean, narrowed, or
abandoned.

<!-- doctrine: orchestrator-does-not-close -->
**The orchestrator calls neither `done` nor `fail`.** You make that call. This is not
bookkeeping fussiness: the first close wins and the second is discarded, silently.
Verified by running it — a forge closed with `done "ok"` and then sent `fail "again"`
answers `already closed out (status: done); nothing to do`, exits **0**, and appends
nothing to the ledger, so the second party's outcome is gone with no error anywhere and an
exit status that reads like success. Check `skillforge show` yourself when a report is
slow: an orchestrator that dies mid-loop leaves a forge you can still close, instead of a
spinner nobody owns.

**Do not edit its files, do not commit, and do not read a test run as a verdict, while
the orchestrator is working.** This is the cost of getting your thread back: you are now
free to do things the old blocking loop made impossible, and three of them are traps. The
first is the plainest — "return to whatever you were doing" does not include the files the
orchestrator was sent to change. It is editing that SKILL.md and its tests between rounds;
touching them from the main thread produces torn reads in both directions and silently
reverted edits. Pick up work elsewhere in the tree, or wait. The orchestrator is editing
the working tree between its rounds, so a commit made before its report captures
half-finished edits — worse if a second agent is also mid-edit, which is exactly when a
freed-up main thread is likely to have started one. A suite run started before the
orchestrator finishes proves nothing about the tree it will leave behind; a green run is
not evidence, and a red one may be a file caught mid-write. Wait for the report, then test,
then commit.

Nesting multiplies cost: every round is now an agent inside an agent. That is the trade for
a usable main thread, and it is why the threshold in section 2 is worth enforcing.

**2. Builder agent.** Dispatch a subagent to write the SKILL.md, and tell it to invoke
**`skill-authoring`**, which ships with this package and is therefore present wherever this
skill is. Name it explicitly rather than saying "a skill-authoring skill": the earlier
version of this step named `skill-creator` and `writing-skills`, neither of which resolves
on a fresh Claude Code install, so a cold session followed the instruction and found
nothing. Hand the builder the concrete transcript of what worked, **and the dead ends** —
the dead ends carry the value, because they are what a fresh session would otherwise repeat.

**3. Verify the draft parses, before anyone reviews it.** This is a numbered step and not
a footnote, because a skill can pass every red-team round on its content and still ship
inert. Nothing built into Claude Code catches it: `claude plugin validate --strict`
checks the plugin manifest and **does not read SKILL.md frontmatter at all** — a skill
whose frontmatter raises `yaml.ScannerError` still gets `✔ Validation passed`, exit 0.

What breaks: a SKILL.md opens with a `---` fenced YAML block carrying `name` and
`description`, and something in it makes the block fail strict YAML — most often an
**unquoted `: ` inside the description**, since a description is the one field that wants a
colon (`Use when X: do Y`). Claude Code's own loader is lenient about that particular case
(measured on 2.1.245: the skill loads with its description intact and triggers normally),
but your parse step is not optional, because a break that costs the parser the
`description` key — a stray indent, a bad indicator character — leaves the skill
**installed, named, and visible on disk with a fallback description scraped from the
body**: the trigger clause is gone, it never fires, and nothing is printed anywhere. Strict
YAML is also what the upstream skills validator requires. Quote the description and both
problems disappear. Three of this repository's four original seed skills shipped with
unparseable frontmatter. What was measured on each loader path, and what was not, is in
`docs/CLAUDE-CODE-BEHAVIOR.md` in the `claude-skill-compounder` repo.

```bash
python3 - "$SKILL_PATH" <<'EOF'
import sys, yaml
raw = open(sys.argv[1]).read()
if not raw.startswith("---"):
    sys.exit("no frontmatter block")
meta = yaml.safe_load(raw.split("---", 2)[1])     # raises on the unquoted-colon case
for field in ("name", "description"):
    if not (meta or {}).get(field):
        sys.exit("missing or empty: " + field)
print("frontmatter ok:", meta["name"])
EOF
```

If it raises, fix it and re-run before dispatching the red-teamer; a reviewer reads the
text in front of it and cannot see that the description Claude Code ended up with is not
the one on the page. In *this*
repository the same check is enforced for shipped skills by `SkillFrontmatterTest` in
`tests/test_plugin.py`, so a broken one cannot be committed. That guard is repo-local: a
skill forged into `~/.claude/skills/` has nothing equivalent watching it, which is exactly
why the forge has to run the check itself.

`/skill-doctor` and `claude plugin eval` cover more ground, but both are early-access and
org-gated — absent in this session. Treat them as a bonus if you have them, never as the
plan.

**4. Red-team agent.** Dispatch a **separate, fresh** subagent. Never the builder.

<!-- doctrine: no-forked-reviewer -->
**The red-teamer must never be a fork of either layer** — not of the orchestrator that
dispatches it, and not of the session that dispatched the orchestrator. The extra layer
adds a way to get this wrong, not a way around it. A forked red-teamer already knows what
the skill was *meant* to say, so it cannot detect the ambiguity that will bite a cold
session six weeks from now. Do not tell it the skill is expected to be good. Its brief: *"Here is a skill at
`<path>`. Try to execute it cold. Where does it fail, mislead, or under-specify?"*

<!-- doctrine: no-leading-prompt -->
**Never hand a reviewer a list of what not to flag.** This is the same failure as asking it
to "confirm the deletion", and it is easier to commit because it feels like helpfulness. A
brief that pre-classifies the allowed cases converts the review into a search for the
findings you already expect, and you get your own judgement back with a second name on it.
Observed once in this repository's own history (a single A/B on one file, not a platform
measurement): the same file, reviewed by one agent given a "do not flag these" list and by
one given only the principle, produced **1 finding and 4**.
The neutral reviewer also *defended* two passages the biased brief would have condemned,
which is the half you lose entirely.

State the standard. Do not enumerate the exceptions. If you believe a class of case is
legitimate, that belief is exactly what needs testing, so let the reviewer reach it or
reject it. Where a judgement call is genuinely open, say so and ask the reviewer to draw
the line and defend it, rather than drawing it for them.

Asking for hard verification is different and is fine: "run every command", "check every
number against its source" constrains method, not conclusions.

Required eval checklist:

|Check|What it catches|
|-|-|
|**Cold start**|Can step 1 be executed with no prior context and no clarifying question?|
|**Trigger precision**|Propose 3 prompts that SHOULD fire the `description` and 3 that should NOT. Does it discriminate?|
|**Verified claims**|Actually run every command, path, and API call the skill asserts. Unverified claims are defects.|
|**Unhappy path**|What does a session do when a step fails partway through?|
|**Overlap**|Does an existing skill already cover this? If so, that is a blocking finding.|
|**Scope**|Is it doing more than one thing? Split or narrow.|

**5. Loop.** Feed findings back to the builder via `SendMessage` so it keeps its context.
<!-- doctrine: fresh-reviewer-each-round -->
**Spawn a new red-teamer each round; the whole test depends on the reader being
genuinely cold.** Repeat until the report comes back clean.

**6. Cap at 5 rounds, or 10 for a skill that is complex or genuinely important.** The cap
is chosen at step 0, before `skillforge start`, because the step budget encodes it — raise
it deliberately and say why in the announcement, rather than discovering at round 6 that
you would like more. A safety-critical skill, one with a scanner or a validator, or one
whose failure is silent all justify the higher cap.

<!-- doctrine: narrow-or-abandon-at-the-cap -->
**If it is not clean at the cap, do not ship a half-working skill: narrow its scope
until it is clean, or abandon it.** Leave notes explaining what blocked it. An
orchestrator reports "abandoned" and the reason back to the dispatching session; the
orchestrator does not call `fail` itself, and the dispatching session makes that call.

**Where 5 comes from.** Not from a measurement; the ledger cannot supply one (next
paragraph). What it can supply is the shape of every forge recorded here, and one command
puts the whole basis for this number in front of you:

```bash
jq -r 'select(.event != "start")
       | [.name, .event, .rounds, .rounds_planned, .phase] | @tsv' \
  ~/.claude/skill-compounder/ledger.jsonl
```

Read it before trusting the rest of this paragraph. At the time of writing it holds three
closed forges, and two of them wanted more than three rounds. The first `ai-tell-audit`
attempt ran a three-round budget to its last step and was abandoned there — `fail`,
`rounds: 3` of `rounds_planned: 3`, "wrong artifact: built a statistical detector, the need
is a pattern-list editor". The third was budgeted five rounds and closed "shipped after 7
builder rounds and 7 red-team rounds". The one forge that did close inside three rounds is
the second, and it is not a counterexample so much as the receipt for the first: a
re-scoped retry, budgeted two rounds because the expensive discovery had already been paid
for. The change that moved this loop off the main thread did not come back clean after
three rounds either.

**That is the case against 3, not for it.** One forge here did meet a three-round cap, so
the honest objection is not that nothing meets it. It is that the two forges which had
anything hard to do both hit three rounds with blocking findings still arriving, and a cap
that binds exactly when the work is hard is a guarantee that anything hard ships narrowed. What arrives late is the argument, and those findings are
written up in `notes/2026-08-25-forging-session.md`: a rule that would have deleted Linus's
rationale for eight-character indentation from Linux's `coding-style.rst`, and a
contamination that survived two relocations — round 5 removed a pre-stated verdict from
`SKILL.md`, round 6 found the same measurement pinned in `skills/ai-tell-audit/sources/EVIDENCE.md`.

How to read the ledger's `rounds` field, and what it cannot tell you. It is always derived
from the step, as `(step - 2) / 2`. On a `fail` that is the rounds actually completed, an
overrun included — a forge abandoned at step 8 of 12 records `rounds: 3, rounds_planned: 5`,
and one abandoned at step 14 of 12 records `rounds: 6` against the same plan. On a `done`
it carries an overrun the same way, because `done` raises the step to the total but never
lowers it — but a forge that finished inside its budget records `rounds` equal to
`rounds_planned` whatever it really took, and therefore cannot tell you how many rounds it
really took: `ai-tell-audit` records 5 against a five-round budget and its own close
message says seven.

Five is a better guess and still a guess. What would settle it is rounds-to-clean recorded
per forge, which the ledger can carry; until that exists, treat this number the way the
other thresholds in this package are treated, as unvalidated.

## 3. Fixing, documenting, or retiring a skill that did not work

<!-- doctrine: no-silent-workaround -->
**Never silently work around a skill that misfired.** That wastes the same time in
every future session. Escalate in order:

1. **Documentation issue** (procedure right, wording ambiguous): edit the SKILL.md now.
   Add an explicit "Do NOT use this when…" / "Known pitfalls" note naming the exact wrong
   turn taken, so a fresh session cannot repeat it.
2. **Substantive issue** (procedure wrong or outdated): fix it, then **re-run the full
   section 2 red-team loop** on the fix.
3. **Retirement** (obsolete, superseded, or unfixable): requires **independent
   concurrence**.
   - Write the case: what was attempted, why it cannot be fixed, what supersedes it.
   - <!-- doctrine: neutral-retirement-question -->
     **Ask a second fresh agent the neutral question, *"should this be kept, fixed, or
     retired?"*, never "confirm this deletion".** A leading prompt defeats the check: it
     tells the reviewer what the answer should be, and it will oblige.
   - Retire only if it independently reaches "retire." If it says keep or fix, do that.
   - <!-- doctrine: archive-the-source -->
     **Archive the source, not the link.** Most skills here are symlinks into a checkout,
     so `mv ~/.claude/skills/<name> ...` moves the link and leaves the real directory in
     place, where the next install resurrects it. Worse, writing `WHY-ARCHIVED.md` into
     the moved directory writes into the live source. Resolve first:

     ```bash
     src="$(realpath ~/.claude/skills/<name>)"          # follow the link
     mkdir -p ~/.claude/skills-archive
     mv "$src" ~/.claude/skills-archive/<name>          # move the real directory
     rm -f ~/.claude/skills/<name>                      # then drop the dangling link
     ```
     Write `WHY-ARCHIVED.md` inside the archived copy afterwards, recording the date, the
     case, and the concurring verdict. If the source lives in a git repo, remove it there
     too, or the next `git pull` brings it back.
   - A skill inside a plugin cache cannot be archived this way at all. Disable the plugin,
     or narrow the skill's `description` so it stops firing, and record why.
   - <!-- doctrine: never-rm-rf -->
     **Never `rm -rf` a skill.** Spurious deletions must be recoverable.

## 3.5 Candidates you are not ready to forge yet

Not every good idea clears the threshold in the moment it arrives. Rather than losing it
or forging something premature, write the marker:

```
★ Skill candidate: <the procedure, and what made it costly, in one paragraph>
```

A `Stop` hook queues that, deduped, for one batched review a week (`skillinsight review`).
The queue feeds this same threshold; it never bypasses it, and nothing in it is forged
automatically.

## 4. Hot-reloading

Skills are hot-reloaded. Writing `~/.claude/skills/<name>/SKILL.md` makes it available to
**this** session and to other already-running sessions, with no restart.

- There is a lag of roughly one tool round-trip. If `Skill` returns `Unknown skill: <name>`
  right after you create it, make any other tool call and retry. Do not conclude it failed.
- Fallback: `cat` the SKILL.md and follow it by path. The content works regardless of
  registry state.
- Consequence: finish and red-team a skill **during** the session that discovered the need
  for it. The benefit propagates immediately, and deferring to "next session" throws that
  benefit away.

## Trigger precision

<!-- routing-pin
description-sha256: 9c6016f91d31ec94812df4edc9791993046f649d43985821fcc9c0b349f6b4fd
prompts-sha256: b0d3fb4da0e6c09f8453979d51221df6812e8d508da59c7ed43cba5e2dccb40d
measured: 2026-08-25
cli: 2.1.245 (Claude Code)
model: sonnet
result: partial: the six claims here are unverified
note: only the rejected fragment quoted in the prose below was run
cli-note: taken from the installed CLI on that date, not from the run itself
-->

Should fire:

- "That took four attempts to get the migration ordering right, and we hit the same thing last week on a different table."
- "Before I write this deploy script, is there already something for it?"
- "The skill I just used told me to run it from the wrong directory."

Should NOT fire:

- "Write a skill that does X." That is `superpowers:writing-skills`, which owns authoring.
  This skill decides *whether* to author, and runs the adversarial loop around it.
- "Refactor this module." Ordinary work, no repeatable procedure in view.
- "Write a one-off script to rename these files."

**A remark with no referent does not fire this, and should not.** Measured on 2026-08-25
by running real `claude -p --model sonnet` sessions and checking for an actual `Skill` tool
call: *"That took four attempts to get the ordering right, and we hit it last week too."*,
with no subject named, produces clarifying questions and no skill. Naming the subject fires
it. That is the right behaviour rather than a miss, because the threshold in section 2 wants
a concrete referent for both conditions, and a prompt that supplies neither cannot be
assessed against it. The trigger prompt above therefore names one.

Habit 1 (check before implementing) has no reliable lexical hook: "let's build the
ingestion pipeline" contains nothing a `description` can match. That habit is carried by
the `UserPromptSubmit` reminder hook and the `CLAUDE.md` stanza, not by this trigger. If
those are not installed, habit 1 will not fire on its own.

## Troubleshooting

- `skillforge: command not found` → the CLIs (`skillforge`, `skillreport`, `skillinsight`,
  `skillcontrib`) install to `~/.local/bin/`; ensure that directory is on `PATH`, or call
  them by full path. Loaded as a plugin instead, they are on the Bash tool's `PATH`
  already.
- Animation not visible → the status line only renders while a forge is active. Check
  `skillforge show`. If `settings.json` was just installed, the status line picks up
  changes without a restart, but `/hooks` forces a config reload.
- Reminders too frequent or too rare → tune `CI_EDIT_EVERY`, `CI_PROMPT_COOLDOWN`,
  `CI_PROMPT_MIN_CHARS` in the hook entries in `settings.json`. If they are noisy, raise
  the thresholds instead of uninstalling.
