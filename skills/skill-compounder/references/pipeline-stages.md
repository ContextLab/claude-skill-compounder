# The A–E pipeline, stage by stage

`SKILL.md` carries the protocol. This file carries the briefs: what each agent is handed,
what it must return, and the failures each hand-off is there to prevent. Read it when you
are about to dispatch, not before you have decided to forge.

The governing idea, stated once so every brief below can refer to it: **the project that
produced the problem is held-out test data.** A is the only stage that may see it. Every
other stage is denied it, and the skill's quality is measured by how well an agent that
never saw the project can build for it and use it.

Two corollaries, both learned by running this pipeline rather than by reading it. Neither
is obvious from the rule above, and each cost something on the first end-to-end run.

**Describe the boundary by what it encloses, never by naming what lies outside it.** A brief
that says *"do not read anything under `/Users/x/the-project`"* hands the orchestrator the
address of the held-out data in the act of forbidding it. *"Read nothing outside your scratch
directory"* is enforced by exactly the same mechanical check — grep the agent's transcript for
the project's name, expect zero tool calls and zero mentions — and leaves nothing to grep for.
On the first run the orchestrator did not go there, verified that way; the design leaked
anyway, and a design that depends on the agent declining an address it was handed is
instruction with a map attached, not isolation.

**What is withheld is the project, never the authoring standard.** The required section
shape, the caps, and the fact that a routing gate will run and needs six declared prompts are
general knowledge about writing skills in this environment. They belong to no project, so
withholding them buys no test-set purity — and on the first run it cost the forge its gate:
the draft came back with no `## Trigger precision` section, so there was nothing to run, and
stage A had to catch it at step 7. Neither cold reviewer could have. **A stranger cannot audit
a convention they were never told**, which is the same reason D is never handed a list of what
not to flag: a reviewer can only hold an artifact to a standard it knows about.

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
   applied" is. **One criterion is standing, on every forge: the skill must state when it is
   not worth its own cost.** A reader who already suspects they do not need the procedure is
   the reader most likely to abandon it halfway and least likely to say so, and the first
   forge run through this pipeline shipped with no such bound — the blind acceptance tester
   said it would have been faster without the skill, and the criteria A had pre-registered
   gave nobody a place to record that. An exit ramp costs one sentence in the body and it is
   scoreable by a stranger, which is what makes it a criterion rather than an aspiration.
4. **The acceptance test.** The original triggering problem written out as a task to
   attempt again, with the finished skill, at step 7.

**Why a file and not a message.** A full run of this pipeline can outlive a compaction of
the main thread. Criteria that live only in context are lost at that moment, and the
recovery a session actually makes is to reconstruct them from the draft it now has — which
is goalpost-moving with extra steps, and it leaves no trace.

**Sequenced after the builder is quiet, never alongside it.** A's acceptance test reads the
skill file; if C is still applying fixes, A is scoring a moving target and its score means
nothing. See the quiesce rule under B.

**Returns at step 7:** the result of running the finished skill against the real case, and
a score per criterion. This is the one project-contaminated artifact the pipeline produces
on purpose, and it stays in A's notes and out of the SKILL.md.

## B — the orchestrator

**Holds:** A's framing, the generalised transcript including dead ends, the round cap, the
step numbering, and the general authoring standard below. **Never** the project path, the
repository, or the verbatim trigger.

**Handed explicitly, because B and C cannot go and read it.** This is the authoring standard,
and it is not project content:

- the frontmatter budgets — description at most 500 characters, frontmatter block at most
  1024, body at most 500 lines — and that depth over the ceiling goes in `references/`;
- the required `## Trigger precision` section, carrying at least three verbatim must-fire
  prompts and three must-not-fire prompts, each the utterance a user would actually type;
- that those six prompts are **run** at step 7 against a real router, over at least three
  runs, and that a forge cannot be reported clean while its own must-fire prompts do not
  fire it — so a draft without the section cannot be gated at all;
- the parse gate below, and that `claude plugin validate --strict` is not a substitute.

Hand these as text, not as a path into this repository. A brief that says "follow the
authoring standard in `<repo>/skills/skill-authoring/`" has re-created the leak the
corollary above is about, and a brief that says nothing leaves C free to invent a shape.

**Decides, and records before dispatching C:**

- **The level.** General, user, or project — the highest one the procedure genuinely
  reaches. The test is whether the skill can be written to apply beyond the case that
  prompted it: beyond the task for a project skill, beyond the project for a user skill,
  beyond both for a general one. If it cannot, the level is wrong, not the skill. The
  direction of *use* runs the other way, which is what makes the rule cheap: a user-level
  skill may still be applied project-specifically, and a general skill user- or
  project-specifically.
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

**Standing rule: nothing reads the draft while the builder is still writing it.** Before B
dispatches a reviewer, runs the routing gate, or hands the draft back to A, C must be
confirmed idle — and confirmed by something **observable**, never by a message saying so:

- C writes a marker file as the literal last action of a round, e.g. `printf 'round 3 done\n'
  > <scratch>/ROUND-DONE`, and B waits for that file to appear;
- B then reads the draft's checksum twice, a few seconds apart, and proceeds only if the two
  agree: `shasum <skill> && sleep 5 && shasum <skill>`.

Both halves are needed. The marker says the builder believes it is finished; the stable
checksum says nothing is still landing on disk. On the first end-to-end run the acceptance
tester reported the skill file changing underneath it mid-review, because the builder was
applying fixes concurrently — so that review scored a file nobody shipped. This repository
already documents the same hazard from the other side, in `docs/DESIGN.md`: never edit a
script that may still be running. A reviewer reading a file being written is that hazard
with the roles swapped.

**Standing rule: watch for artifacts, do not block on messages.** Findings go to C by
`SendMessage` so it keeps its context and its scratch repro, but delivery is not something to
depend on: on 2026-08-26, messages sent from a *resumed background* builder back to the
orchestrator were observed looping back to the sender instead of arriving, and the loop
stalled until a human relayed them. The reliable substitute, adopted mid-run and used for the
rest of it: agree a grep-able marker file per round, and watch for it in the background
(`until [ -f <scratch>/ROUND-DONE ]; do sleep 20; done`) rather than waiting on a reply. It is
the same artifact the quiesce rule needs, so one convention serves both.

**Standing rule.** B confirms a fix by running it, never by trusting the report that claims
it. This is not suspicion for its own sake: builders in this loop have reported fixes that
were not made, and an agent asked to probe a platform behaviour once reported a child's
answer verbatim, with timing statistics, before that child had replied — and retracted the
whole thing as fabricated when asked a second time.

**Returns:** clean, narrowed, or abandoned, with the reason. Never a `done` or a `fail`.

## C — the builder, in a scratch directory

**Holds:** B's brief, the authoring standard, and a scratch working directory. **No path into
the project**, because an instruction not to look is a sentence and sentences get read
past. What C is given is the enforcement. Where a sentence is still wanted — belt and
braces — it names the enclosure and not the exclusion: *"read nothing outside your scratch
directory"*, never the project's path.

**Signals the end of every round with a file, not a message.** The last action of a round is
to write the marker B is watching for; see the two standing rules under B for why a message
is not enough and why B will not read the draft until that file exists and the checksum has
settled.

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

**E audits the criteria, not only the skill against them.** A wrote them before anything was
built, which is what makes them honest and also what makes them incomplete: A could not know
what the forge would turn up. Gaps E finds are findings about this pipeline, and they belong
in the close report even when the skill passes. That is how the standing cost-bound criterion
above and the ceded-territory record in the routing gate both got written down — E raised
them on the first run, against criteria that had not asked for either.

## The failure report

Four sections, appended in order by A, B, C and D. Each signs its own: who it was, what it
was given, what it concluded. **Nobody edits anyone else's section.** Where two sections
contradict each other, the contradiction is flagged and kept — the disagreement between an
author who thought the brief was clear and a builder who could not execute it is the most
informative thing a failed forge produces, and a merged narrative destroys exactly that.

The report and the skill are archived together, under `~/.claude/skills-archive/<name>/`,
with the report as that directory's `WHY-ARCHIVED.md`. Same convention as retirement, in
`skills/skill-compounder/references/retirement.md`; nothing is ever deleted.
