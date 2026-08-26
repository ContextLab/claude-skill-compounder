# 2026-08-26: the A-E forging pipeline, the claim gate, and what corrected me

Continuity note. Everything here was verified by running; where a claim is a hypothesis it
says so. Written while two agents were still in flight, so the last section is open.

## What landed

**The forging protocol is now the user's A→B→C→(D↔C)ⁿ→A→E pipeline**, replacing the old
numbered steps outright in `skills/skill-compounder/SKILL.md` (+ new `references/`).
Organising idea, in the user's framing: **the original project is held-out test data.**

- **A** (the main session) is the only agent that sees project content. It pre-registers
  the verbatim trigger, a de-projected framing, scoreable criteria and an acceptance test
  to `~/.claude/skill-compounder/briefs/<name>.md` **before** dispatching anything.
- **B** *is* the orchestrator and has no project content: picks the level, sets the round
  cap, runs the loop. Isolation is a property of B, not a rule B polices.
- **C** builds in a scratch directory with no path into the project, and must build a
  runnable reproduction and run every command it documents. Cannot repro → back to B.
- **D** gets the skill **and nothing else** and infers its own scenario. That inference IS
  the completeness check for de-contextualised references.
- **A** then runs the skill against the real case, scores the pre-registered criteria, and
  runs the routing gate.
- **E** receives the verbatim trigger *separately* and judges whether A's framing matched
  it. Failure → four signed, un-rewritable sections → `~/.claude/skills-archive/`.

Caps fixed at the same time: description 655 → **491** chars, body → **499** lines. Routing
re-probed **3/3 + 3/3 on the first pass**, so the 655 was never buying anything.

**The claim gate** (`hooks/claim-gate.sh`, 56 tests) blocks at `Stop` when a claim in the
final message is unsupported by session evidence, and denies a `git commit` whose message
asserts unsupported numbers. Calibrated on this session's real transcripts: Stop 6/205
turns (4 true, 2 false); commit 3/93 (1 false) — **including a deny on the real commit
carrying "1495 tests across 27 files"**.

**Ledger v2**: `origin`, `use`, `verdict`, `horizon` events; `--trigger`/`--trigger-kind`;
`skillforge backfill`; `hooks/skill-use.sh` recording invocations live.

**Every shipped script is wrapped** in a brace group ending in `exit`, with both ratchets
(`KNOWN_UNWRAPPED`, `HOME_UNGUARDED`) now empty and enforced by
`tests/test_script_wrapping.py`.

## The measured facts worth keeping

- A **failed `Skill` invocation reaches no hook at all** (2.1.245) — neither `PostToolUse`
  nor `PostToolUseFailure`, any matcher — while a failing `Bash` does. So a hook census of
  invocations counts successes only; transcripts remain the source for failures.
- **The model refuses instructions embedded in a `PreToolUse` deny reason** ("tool-result
  text isn't a directive I follow"). A deny reason may only state fact; only a `Stop`
  reason gives guidance.
- `claude -p` **does** load project skills with no flag; `--setting-sources ''` is what
  removes them. The earlier claim that the flag enables them was false in both directions.
- **bash reads a script lazily by byte offset**, so rewriting a running script resumes
  execution mid-garbage; a brace group alone is insufficient without a terminating `exit`.
- `verification-before-completion` has **0 invocations across 1988 transcripts**, with four
  sibling `superpowers` skills appearing 11-25 times each, so the zero is not a broken
  counter.

## What corrected me, and the pattern in it

Five separate agents caught claims of mine that did not survive derivation:

1. `--setting-sources` — I relayed a subagent's platform claim without running it. False.
2. "wrapped in a brace group" as the fix — incomplete; the terminating `exit` is
   load-bearing and I had already told the user the fix was done.
3. "the machinery caught it" — no causal link; published to GitHub, then retracted.
4. "`skill-compounder` is the only skill violating the caps" — only the *description* cap;
   `ai-tell-audit` is over the body ceiling. I checked descriptions across all nine and the
   body for exactly one, then generalised.
5. "six of nine skills have zero genuine uses" as evidence of value — the user caught this.
   A zero conflates *the trigger is broken so it can never fire* with *the situation never
   arose*. Derived correctly, interpreted wrongly.

**The pattern is not arithmetic. It is inference from a correctly-derived number, and
relaying testimony as measurement.** The claim gate reaches the first class only when a
number is present; nothing cheap reaches a causal claim with no number in it.

## Open

- **The missing denominator.** We measure "did it fire", never "should it have fired".
  Without a missed-fire rate neither a zero nor a high count is interpretable, and the
  forging threshold has no evidence to stand on. Candidate instrument: the session-review
  arm already reads whole transcripts with a model and could answer, per skill, "did a
  moment matching this trigger occur, and did the skill fire?"
- **Can an assistant-internal trigger be probed at all?** Every routing probe supplies a
  user prompt. Under test now: whether a headless session can be *seeded* into the state a
  trigger describes. A negative result means those triggers are unverifiable by anything
  this repo has, and must be recorded as such rather than dressed up.
- `CLAIM_GATE` is undocumented in README's knob table — one deliberate red test until the
  hook's wiring lands and its knob set is final.
- The A-E pipeline has **never been run**. It is written, pinned and mirrored; that is not
  the same as working.
