# Finishing issue #19: four review rounds, and the loop stopping on a reopening

Written 2026-08-27, covering work begun 2026-08-26. Branch `issue-19-close-the-gap`,
base `origin/main` (`rung=named`). This is the `finish-task` record for that branch.

**Read this before the branch.** It says what was reviewed, what was found, what is still
open, and why the run stopped one phase short of the integration decision.

## The unit of work

Close issue #19: make recognition of a recurring problem deterministic (a repeat gate),
make skills fire because the architecture forces them rather than because a reminder was
read (a documentation gate and an apply gate), scope and compose skills, and close the
forge loop with recorded *use* of the forged skill (`skillforge apply`) — all wired into
both install paths, plus a new `finish-task` skill.

**It is wrong if** any gate refuses work it should pass, any gate is unreachable from
either wiring, or the durable prose disagrees with the code.

## Status: STOPPED WITHOUT CONVERGING, deliberately, at Phase 5 of 6

Phases 0 through 5 completed. **Phase 6 was not run**, and the branch has not been handed
to `superpowers:finishing-a-development-branch`. The reason is in "Why the loop stopped"
below. Two findings are open. Deciding what to do with this branch is a human call.

## Who reviewed it

Four rounds, each by a **fresh cold agent with no history of the authoring session** and
no fork of it — a new one every round, because after round one the previous reviewer is no
longer cold. Each was given the diff, the unit-of-work sentence and the project's
conventions; none was given the author's reasoning or a list of what not to flag.

Rounds 1–3 are the cap `finish-task` documents. **Round 4 was a deliberate overrun**,
announced as one at the time. It was run because neither stopping condition had fired
after three rounds — no fix had reopened an earlier finding, and there was no same-class
recurrence in code changed in response to the previous round — and because stopping at the
cap would have published round 3's fixes to three shipped scripts and the installer with
no review at all.

Round 4 is also the round that ended the loop, by finding a reopening.

## Findings: 21 found, 19 fixed, 2 open

### Round 1 — 3 findings, 3 fixed

1. **HIGH. The repeat gate denied calls that had never failed.** `norm_bash` masked every
   quoted literal to `<S>` and every absolute path to `<P>`, so two sessions failing on
   `python3 -c "import boto3"` denied `python3 -c "print(1+1)"` in a third — under the
   words *"This exact call has already failed."* Same collapse for two different scripts
   under `python3 <P> --jobs <N>`.
   Fixed two ways: a quoted literal after an eval-like flag is kept as the command rather
   than masked as an argument, and an absolute path keeps its last segment. The refusal no
   longer claims exactness; it says it matched a *shape* and names what was masked first.
   Six residual collisions are named in the header and pinned by tests as deliberate.
2. Four counted claims in `.claude/CLAUDE.md` contradicted the branch's own code.
3. The README named none of the three hooks that refuse the user's work, nor their off
   switches.

### Round 2 — 6 findings, 6 fixed

1. **HIGH. The doc gate denied a push that carried documentation.** `(^|/)notes?/` was
   unanchored, so `docs/notes/architecture.md` — a real `.md` inside `docs/` — was
   classified NEITHER and the push refused for carrying no documentation, with the reason
   naming the doc file nowhere. Anchored to `^notes?/`. It cut the other way silently too:
   `src/notes/parser.py` was excluded before it could count as CODE.
2. **The deny claim was taken before the emit, and it was LIVE, not latent.** The reviewer
   marked it unreachable because the reason is bounded. That is true of the message and
   beside the point: `jq -n --arg r` is an exec and the *environment* counts against the
   same `ARG_MAX`. It is only reachable with the reason near its cap — the largest exec
   before the emit is the store query at ~1.3 KB and a typical reason is 895 bytes, so
   `E2BIG` reaches the query first and the hook fails open before claiming. At the cap the
   reason is 2096 bytes and the emit is larger again. Reproduced, then fixed by *releasing*
   the claim on every non-emitting path — not by inverting the order, because this claim is
   what serialises the double delivery.
3. **The item the reviewer cleared was a defect.** They checked `DESIGN.md`'s claim that
   the two session ids differ, measured them equal, and concluded the doc was stale but the
   gate fine. `bin/skillforge` writes `$CLAUDE_CODE_SESSION_ID` into the apply marker while
   `apply-gate.sh` compares the payload's `.session_id`, so the gate *depends* on the
   equality the doc denies. Now a dated finding plus a named, accepted fragility.
4. README said every gate variable has exactly one reader; `REPEAT_MIN_SESSIONS` has three.
5. "9 skills shipped" in four places against a real count of 10.
6. `SKILL.md` said the apply gate "refuses to end the forging session's turn"; it blocks
   once per skill and lets go.

### Round 3 — 6 findings, 6 fixed

1. **The doc gate was case-sensitive**, so `Documentation/` — git's own convention and the
   kernel's — was not documentation. Nor `Docs/`, `Doc/`, `Man/`, `Readme`, `changelog`,
   `guide.MD`. `grep -qiE` on `DOC_RE` and `CODE_RE`.
2. **A red test suite is not a broken call.** Two sessions of a failing `./run_tests.sh`
   denied the third session's first run — and running it is exactly what that session must
   do. Added `runner_head`, a second allowlist with a separate argument from the first.
   Multi-purpose drivers are gated on their *subcommand*, because `npm test` failing means
   the code is broken while `npm install` failing repeatedly is what the gate is for.
3. **A test required a false sentence to stay in the file.** The header called
   `norm_structured` unreachable and an assertion pinned that phrase verbatim, so it would
   have passed unchanged if the behaviour it named had been removed. The claim was false:
   every `Skill` delivery takes that branch. The refuse arm is now Bash-only, because both
   of its escape hatches sit inside the Bash branch and a refused Skill call had no way past
   and no way to retire the signature.
4. **The installer left stale entries pointing at deleted scripts** on `PreToolUse` and
   `Stop`. `_strip_marker` returns a new list and the write-back was guarded on there being
   something to write.
5. Two hook headers asserted an absolute this branch's own later measurement refutes.
6. `.claude/CLAUDE.md` said nothing but `test_contribute.py` skips.

### Round 4 — 10 findings, 8 fixed, 2 open

1. **THE REGRESSION, and the reason the loop stopped.** Round 3's fix (1) also gave
   `NEITHER_RE` a `-i`, to stop a capitalised directory sidestepping the notes exclusion.
   That reintroduced round 2's finding (1) one commit later under a different spelling:
   `Notes/design.md` beside a code file went from **allowed** to **DENIED**, reason naming
   no documentation file. Proved by driving the previous commit's hook and HEAD side by
   side against a real repository and a real bare remote.
   **The trade was backwards.** A sidestepped exclusion costs a *missed* deny, which this
   gate tolerates by design; a case-folded one costs a *wrong* deny of work that carries
   documentation, which the header calls the one outcome it must never produce. And the
   justification is repo-local — this repository's log is `notes/`, lowercase — so folding
   case bought nothing. Reverted; `Notes/x.md` now counts as documentation while
   `notes/x.md` does not, and that asymmetry is pinned by a test with a partner proving the
   exclusion still fires.
2. **OPEN.** `doc-gate` claims its deny marker before emitting.
3. The installer's third write-back site (`PostToolUseFailure`) had no test; the commit
   claimed three sites while the test covered two. Added; it discriminates.
4. `DOC_GATE_CODE_EXCLUDE`'s case-sensitivity was load-bearing and unpinned — mutating its
   grep to `-qiE` left all 77 doc-gate tests green while flipping a real decision.
5. The routing-probe cost was stale in three places, one of them the binding project
   document, where round 3 newly wrote it. 48/144 → **54/162**.
6. `grep -rln skipTest tests/ | wc -l` is **12**, not "fourteen" — and the companion
   command round 3 printed had no operand and would have hung on stdin.
7. `DESIGN.md` and `README.md` still carried the apply-gate sentence round 2 corrected in
   `SKILL.md` and only there.
8. `REPEAT_GATE_NOW` has two readers, not one.
9. The notes index named 9 of 13 files, omitting the review entry point.
10. **OPEN.** `runner_head` misses standard prefixes.

## The two open findings

Both change how a hook refuses the user's work. Making unreviewed behaviour changes to a
refusing hook is precisely what produced round 4's regression, and the loop had stopped, so
neither was fixed.

**1. `doc-gate` claims its deny marker before emitting.** This is the defect the branch
already fixed in `apply-gate.sh` and `repeat-gate.sh`. `hooks/doc-gate.sh` takes the marker
and then emits with a bare `jq -n --arg r "$reason" ... || exit 0` — no render-to-file, no
subshell, no release. `DOC_GATE_MAX_NAMED` has a floor of 1 but **no ceiling**, unlike
`apply-gate`'s, which is capped at 20 specifically because unbounded quoting defeats the
cap. Reported consequences: at ~2900 code files the emit dies, stdout is empty, the marker
is taken, the push proceeds silently and that HEAD can never be judged again in the
session; at ~700 files it instead emits a very large deny reason straight into the model's
context. `grep -n "ARG_MAX\|E2BIG" tests/*.py` names `test_apply_gate.py`,
`test_forge_apply.py` and `test_repeat_gate.py` — not `test_doc_gate.py`.

**Provenance, stated because it matters:** the two figures above (~2900 files, and the size
of the oversized reason) are the round-4 reviewer's measurements. **I did not reproduce
them.** The *shape* of the defect I did verify by reading `hooks/doc-gate.sh` against the
two sibling gates. A commit message on this branch quotes those figures as flat assertions
without this attribution, which is itself a `claim-provenance` Phase 6 miss and is recorded
here rather than silently corrected.

**2. `runner_head` misses standard prefixes.** `bash run_tests.sh`, `sh ./run_tests.sh` and
`timeout 600 ./run_tests.sh` are all still refusable while `./run_tests.sh` is not.
`bash`/`sh`/`zsh` are absent from the interpreter arm (which carries
`python|ruby|node|perl|php`), and `timeout`/`nice`/`sudo` are stepped over by neither
allowlist though `env` is. These are ordinary ways to run a suite. The header already
discloses that the list is a lower bound; this is a near-miss of the case the function was
written for, which is different from the disclosed tail.

## The sweep

```
TEST_TIMEOUT=400 ./run_tests.sh
```

Result, verbatim tail:

```

OK
ALL TESTS PASSED
exit=0
```

**37 test files, exit 0.** `run_tests.sh` loops over files and **prints no aggregate
count**; the 1822 figure below is the sum of its 37 per-file `Ran N tests` lines
(`grep -E '^Ran [0-9]+ test' <output> | awk '{s+=$2} END {print s}'`), not something the
runner reported. One test skipped: `test_routing_claims.py::LiveProbeTest`, opt-in behind
`SKILL_ROUTING_PROBE=1`.

### Proof the sweep ran this code

A canary token minted at epoch 1787810688 (suffix `d7c110de`; the full token is not
reproduced here, for the reason in the paragraph below), planted via `stale-artifact-check`
on **the line the
change actually altered** — the `NEITHER_RE` classifier inside `hooks/doc-gate.sh`'s
per-file loop, where execution is not in question.

**OBSERVED**, 148 bytes: the changed line executed 148 times during the run.

That canary run came back **red**, in two independent and correct ways, which is itself the
provenance evidence — a stale artifact would have produced neither:

- `test_doc_gate.py::test_no_redirection_in_the_script_suppresses_stderr_too_late` — the
  gate's own guard against redirections in the script caught the canary's `>>`.
- `test_seed_stale.py::CanaryCleanupTest::test_r3_b4_the_sweep_is_silent_on_this_repository`
  — the `stale-artifact-check` seed skill's own test, asserting this repository carries no
  canary token, found the token in `hooks/doc-gate.sh`.

Canary removed, that skill's Phase 4 sweep reports `CLEAN` with no orphans from other
sessions, and the recorded sweep above is the clean re-run with nothing else changed.

**A fourth catch, by the same test, from this record.** The first version of the paragraph
above quoted the token in full. `CanaryCleanupTest` then found it *in this file* and failed
with "documentation placeholders must never read as canaries" — a live canary and a
citation of a dead one are the same eight hex digits, and nothing but the shape
distinguishes them. So the token is written here in a form that cannot match
`CANARY-[0-9]{10}-[0-9a-f]{8}`. This is the case `finish-task` Phase 5 anticipates as *the
record broke the suite by existing*, and it is why every finish owes a confirming sweep
after the record is committed rather than treating the recorded sweep as the last word.

## What `claim-provenance` changed: nothing

Every bucket A claim re-derived from the system and matched: 5 CLIs, 12 hook entries over 5
events naming 7 of 8 scripts, 9 clocks, 10 skill directories, 12 files containing
`skipTest`, 54 routing prompts over 9 pinned skills. The README's "read by exactly one
script" universal holds as written — only `REPEAT_MIN_SESSIONS` (3 readers) and
`REPEAT_GATE_NOW` (2) exceed it. All six new `docs/CLAUDE-CODE-BEHAVIOR.md` entries carry
"How established" and a date.

Two observations, neither corrected:

- **A presence-pinning assertion survives.**
  `test_the_header_describes_the_wiring_it_actually_has` asserts the string
  ``"REACHED BY EVERY `Skill` CALL"`` is in the header. Confirmed presence-pinning by
  moving the system rather than reading the assertion: with `compute_call` altered so
  `Skill` takes the Bash branch, that assertion stayed **green** while the behavioural test
  `test_a_structured_tool_gets_a_signature_too` went **red**. The fact is therefore
  truth-pinned elsewhere and this is redundant rather than entrenching — a session that
  moved the system would hit the red behavioural test first. Re-pointing it is a test
  change, which sends the run back to Phase 1, so it was left.
- **The commit-message attribution miss** described under open finding 1.

## An unverified platform lead, deliberately not written to the platform doc

The round-4 reviewer reports measuring that **a `PreToolUse` deny fires neither
`PostToolUse` nor `PostToolUseFailure`** — so the repeat gate cannot learn from its own
refusals and there is no feedback loop. If true this is load-bearing and recorded nowhere.

It is **not** in `docs/CLAUDE-CODE-BEHAVIOR.md`, on purpose. That file's standard is that
every entry names how it was established *by running something*, and I did not run this.
Adding relayed testimony there would break the file's own rule — the same rule
`hooks/claim-gate.sh` enforces by cutting subagent tool results out of its evidence. It
belongs here as a lead for someone with a real `claude -p` and hooks wired.

## Why the loop stopped, and what that means for the branch

`finish-task` says to stop immediately if a round's fix **reopens** something an earlier
round fixed. Round 4 finding 1 is exactly that: round 3's fix reopened round 2's defect. No
judgement call was involved; the condition fired.

The honest reading of four rounds: **three of the four found defects in code the previous
round had touched or written.** Round 4's ten included two in `runner_head`, written an
hour earlier in response to round 3. This is not a sign the gates are wrong in some deep
way — it is that string-driven classifiers have a long tail, and each fix lands in ground
the next reviewer probes harder. That is a reason for a human to decide the next step, not
for the author to keep going.

## What was left undone

- **Phase 6 was not run.** No integration decision, no merge, no PR, no worktree cleanup.
- The two open findings above.
- `skillforge apply --name finish-task` is **not** answered. The debt from forging
  `finish-task` still stands (`skillforge pending` lists it). Answering it needs an outcome
  this run does not have: the skill was used on the problem that caused it, and it worked —
  it caught five regressions before a reviewer saw them, a red suite before a review round
  was spent, and a stale artifact question with a canary — but the run it was used on did
  not finish. Recording `used` now would claim a completed application that did not happen.
  It should be answered when someone closes this branch out.

## For whoever picks this up

The branch is 5 commits ahead of `origin/main` on `issue-19-close-the-gap`, 44 files
changed, +13930/−341, tree clean, suite green on the exact tree described above.

Start with the two open findings. Then decide whether a fifth review round is worth it —
and if you run one, give the reviewer the commit messages as *claims to check rather than
history to trust*, which is what made round 4 the most productive of the four.
