# The A–E pipeline, stage by stage

`SKILL.md` carries the protocol. This file carries the briefs: what each agent is handed,
what it must return, and the failures each hand-off is there to prevent. Read it when you
are about to dispatch, not before you have decided to forge.

The governing idea, stated once so every brief below can refer to it: **the project that
produced the problem is held-out test data.** A is the only stage that may see it. Every
other stage is denied it, and the skill's quality is measured by how well an agent that
never saw the project can build for it and use it.

## A — the session that hit the problem

**Holds:** the project, the working tree, the transcript of what actually happened, the
user's exact words.

**Produces, before dispatching anything:** one file, at
`~/.claude/skill-compounder/briefs/<name>.md`, containing

1. **The verbatim trigger.** The user's words, or the tool output, character for character.
   The same string goes to `skillforge start --trigger`. Two copies is deliberate: the
   ledger row is durable and machine-readable, the brief is what a human reads.
2. **A's framing.** One paragraph naming the general procedure. Everything that identifies
   the project comes out here — repository names, file paths, ticket numbers, the specific
   library version — and what is left is the shape of the problem. This paragraph is the
   only thing about the original case that B and C are allowed to see, and E audits it
   against the verbatim trigger precisely because it is where the drift can happen.
3. **Success criteria.** Numbered, each scoreable yes/no by someone who was not here.
   "Handles errors well" is not a criterion. "Says what to do when the migration is half
   applied" is.
4. **The acceptance test.** The original triggering problem written out as a task to
   attempt again, with the finished skill, at step 7.

**Why a file and not a message.** A full run of this pipeline can outlive a compaction of
the main thread. Criteria that live only in context are lost at that moment, and the
recovery a session actually makes is to reconstruct them from the draft it now has — which
is goalpost-moving with extra steps, and it leaves no trace.

**Returns at step 7:** the result of running the finished skill against the real case, and
a score per criterion. This is the one project-contaminated artifact the pipeline produces
on purpose, and it stays in A's notes and out of the SKILL.md.

## B — the orchestrator

**Holds:** A's framing, the generalised transcript including dead ends, the round cap, the
step numbering. **Never** the project path, the repository, or the verbatim trigger.

**Decides, and records before dispatching C:**

- **The level.** General, user, or project — the highest one the procedure genuinely
  reaches. The test is whether the skill can be written to apply beyond the case that
  prompted it: beyond the task for a project skill, beyond the project for a user skill,
  beyond both for a general one. If it cannot, the level is wrong, not the skill.
- **What specialisation is deferred.** Anything true only of one project or one user is
  not written into the skill; it is read at use time from that project's or that user's
  `CLAUDE.md`. A skill saying "run `./run_tests.sh`" has taken one repository's particular
  and made it everyone's. A skill saying "run the project's suite" has not.
- **The cap.** 5 rounds for a straightforward skill, 10 for a complex or genuinely
  important one. Fixed here because `skillforge` encodes it in `<total-steps>` at `start`
  and no command can re-budget afterwards.
- **How routing will be verified**, given the level, and honestly if it cannot be. Every
  probe supplies a *user prompt*, so a skill whose real trigger is an assistant-internal
  moment cannot be measured that way, and the pin has to say so rather than record a pass.

**Standing rule.** B confirms a fix by running it, never by trusting the report that claims
it. This is not suspicion for its own sake: builders in this loop have reported fixes that
were not made, and an agent asked to probe a platform behaviour once reported a child's
answer verbatim, with timing statistics, before that child had replied — and retracted the
whole thing as fabricated when asked a second time.

**Returns:** clean, narrowed, or abandoned, with the reason. Never a `done` or a `fail`.

## C — the builder, in a scratch directory

**Holds:** B's brief, `skill-authoring`, and a scratch working directory. **No path into
the project**, because an instruction not to look is a sentence and sentences get read
past. What C is given is the enforcement.

**Must build a runnable reproduction.** Not a description of one. C constructs, in its
scratch directory, the smallest thing that exhibits the situation B described — a repo with
two commits, a failing test, a file with the wrong permissions — and then runs every command
the draft documents against it. This is what makes isolation compatible with the rule that
unverified claims are defects: C cannot check the original case, so it builds a case it can
check.

**If C cannot build a repro, that is the finding.** It means B's brief was abstract enough
to be unexecutable, which is a defect in the brief. It goes back to B. It is never a reason
for C to proceed on description alone, and it is never a reason to go looking for the real
project.

**The parse gate, minimally.** `skill-authoring` Phase 3 has the full Gate A, with the
budgets and the bare-scalar check. The minimum C must run before anything is reviewed:

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

Run it. Do not read it and conclude it would pass. `claude plugin validate --strict` is not
a substitute: it checks the plugin manifest and does not read SKILL.md frontmatter at all,
so a skill whose frontmatter raises `yaml.ScannerError` still gets `✔ Validation passed`
and exit 0.

## D — the cold red-teamer, one per round

**Holds:** the skill file. Nothing else. Not B's brief, not C's reasoning, not A's framing,
not the original intent, and not a list of what not to flag.

**First task: infer the scenario.** Before executing anything, D says in its own words what
situation this skill is for and what it expects to happen. That inference is the
completeness check, and it is the check that catches the defect this whole pipeline exists
to remove: a skill carrying a reference only its author can resolve produces an inference
that is vague, wrong, or impossible, and the gap is visible immediately.

**A mismatch with the original intent is not automatically a defect.** If D infers a
broader situation than the one that prompted the forge, the skill has generalised, which is
the outcome the level rule in B is aiming at. Report the mismatch; let B judge it. What is
always a defect is an inference D *cannot* make.

**Second task: execute the inferred scenario, using the skill**, in D's own scratch
directory, and report where it fails, misleads, or under-specifies. A review that reads the
skill and offers an opinion has not run this check.

**Each round gets a new D.** After round one the previous reviewer is no longer cold; it
now knows what the skill was meant to say, which is the same defect as forking the author.

## E — the judge

**Holds:** the finished skill, A's brief file, A's step-7 verification, and — handed
separately, and emphasised as separate — the verbatim trigger, recoverable from the forge
record written by `skillforge start --trigger` even if this thread has compacted.

E answers three questions and one of them is not about the skill at all:

1. **Does A's framing match the verbatim trigger?** Everything after step 1 inherits that
   framing. If A misframed the problem, C built the wrong thing correctly, D reviewed the
   wrong thing thoroughly, and A verified the wrong thing against its own criteria. This is
   the only place in the pipeline where that class of error can surface, and it can only
   surface because E holds the trigger independently of A's account of it.
2. **Does the skill meet the pre-registered criteria as written?** As written — not as they
   would have been written knowing what the skill turned out to be.
3. **Would a stranger, given only this skill, get through the acceptance test?**

A "no" to question 1 fails the forge however good the skill is. The failure report is what
stops the same misframing being forged again next month.

## The failure report

Four sections, appended in order by A, B, C and D. Each signs its own: who it was, what it
was given, what it concluded. **Nobody edits anyone else's section.** Where two sections
contradict each other, the contradiction is flagged and kept — the disagreement between an
author who thought the brief was clear and a builder who could not execute it is the most
informative thing a failed forge produces, and a merged narrative destroys exactly that.

The report and the skill are archived together, under `~/.claude/skills-archive/<name>/`,
with the report as that directory's `WHY-ARCHIVED.md`. Same convention as retirement, in
`skills/skill-compounder/references/retirement.md`; nothing is ever deleted.
