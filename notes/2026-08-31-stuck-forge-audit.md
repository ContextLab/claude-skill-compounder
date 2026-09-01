# The forge that was not running: audit of a 3.5 day "active" state

2026-08-31. Triggered by: *"the skill compounder has been running for a long time ... is it
stuck? still making good progress? working as intended? broken in ways we can fix?"*

## The headline

It was stuck, and it had been stuck since **2026-08-28 09:07 EDT**. Nothing was running.
The status line was telling the truth and nobody was reading it.

## Root cause, established from the transcript

The forge orchestrator was a subagent of session
`25a4770c-9345-41df-8233-be90b0a2b48a`. That session's own transcript carries the death:

```
2026-08-28T13:31:31.720Z
Agent "Orchestrate the finish-task repair forge" failed: Agent terminated early due to an
API error: API Error: Your computer went to sleep mid-response.
```

Corroborated in `pmset -g log`:

```
2026-08-28 09:07:21 -0400 Sleep    Entering Sleep state due to 'Clamshell Sleep'
2026-08-28 09:31:31 -0400 DarkWake DarkWake from Deep Idle ... 45 secs
```

The lid closed at 09:07. The forge's last recorded step was 08:58. The error surfaced on
the 09:31 DarkWake, which is the 13:31Z stamp above. The session then produced exactly one
more assistant turn, at 15:26Z, and it was `API Error: Can't reach the API server`. It never
recovered.

**`caffeinate` was running the whole time** (PID 19958 held `PreventUserIdleSystemSleep` for
140 hours). It did not help and could not: clamshell sleep is not idle sleep. Anyone running
a long forge on a laptop should know that `caffeinate` alone is not the mitigation.

## What that left behind

|Artifact|State found|
|-|-|
|`forge/finish-task.forge.json`|`status:"active"`, step 4/22, `updated` 2026-08-28 08:58, 85h stale|
|`ledger.jsonl`|a `start` row at ts 1787920015 with **no** matching `done` or `fail`|
|working tree|11 files modified, all mtimes 08:32 to 08:58, uncommitted for 3.5 days|
|branch|`issue-19-close-the-gap`, 11 commits, **never pushed**, no upstream|

The status line was correct throughout. It computes idleness
(`SKILLFORGE_IDLE_SECS`, default 2700) and was rendering
`idle 3d13h` in yellow with the pulse stopped. That "3d13h" is what prompted the question.
It was never claiming progress.

## The real gap: staleness is computed and then thrown away

Nothing consumes the idle signal. Confirmed by reading the code:

- `bin/skillforge` has 12 subcommands and **no reaper**. Neither CLI contains the string
  `idle`. `list` prints no age.
- There is no TTL for `active`. `SKILLFORGE_DONE_TTL` (30s) and `SKILLFORGE_FAIL_TTL` (60s)
  reach only terminal states; `active` falls through to `false` and is immortal.
- The ledger readers are **honest**: an unmatched start reports as `no outcome` and
  `skillreport` excludes it from both halves of its reuse fraction rather than miscounting.
  So the numbers were never wrong, but the forge was parked in a third bucket with no path
  out.
- A stale `active` forge **wedges its own name**: `skillforge start finish-task` dies with
  "a forge named 'finish-task' is already live". The user could not have re-run it.
- `skills/skill-compounder/SKILL.md` is advisory only: it says an orchestrator that dies
  mid-loop "leaves a forge you can still close", and nothing detects or resumes.

Its refusal message also advises `skillforge done --name <forge>`, which would record a dead
forge as **completed**. `clear` or `fail` is correct. Two occurrences, lines 1396 and 1465.

## The uncommitted work was not what it looked like

The forge's phase said "round 1 revision: dispatching C to fix placeholder notation, base
ladder, scratch lifecycle". Of the six blocking round-1 findings, **only `cross-ref` was
actually fixed**. `placeholder-notation`, `base-ladder`, `scratch-dir-lifecycle`,
`phase5-red-loop` and `non-git-route` are all byte-identical to HEAD. The scratch directory
still uses `mktemp -d /tmp/finish-XXXXXX` and `rm -rf /tmp/finish-REPLACE`, which is the
shared-guessable-prefix hazard that destroyed a live scratch directory on 2026-08-28.

What the 590 changed lines actually are: a new Phase 7 (non-convergence to
Parked/Withdrawn/Re-scoped), a reflow to ~110 columns, two code blocks moved into
`references/`, and three description rewrites.

**It also left the suite red in 7 files / 14 tests**, where HEAD was green but for one:

|Failure|Cause|
|-|-|
|`test_no_em_dashes_anywhere`|2 em-dashes added in contribute-skill's new Trigger precision section|
|`test_every_description_is_inside_the_documented_budget`|ai-tell-audit 493 to 513 chars|
|`test_frontmatter_is_portable_and_within_limits`|no-silent-stub 492 to 572 chars|
|`test_the_description_obeys_the_caps_it_states`, `test_it_accepts_the_skill_that_ships_it`|skill-authoring 499 to 612 chars|
|`test_every_pinned_rule_is_still_*` (x2)|skill-authoring broadened `frontmatter` to `a skill itself`, the exact change its own pinned rule forbids|
|`TriggerPrecisionTest` (x3, ERRORs)|ai-tell-audit dropped the `(a README ...)` genre list a test parses|
|`test_the_stated_call_count_is_derived_from_the_prompts_that_exist`|prompts went 54 to 60; docstring and CLAUDE.md still said 54/162|
|`test_the_measured_sweep_figures_are_re_derived_not_restated`|claim-provenance says 103 candidate lines, actual 116|

### The conflict the forge walked into and never saw

`ai-tell-audit`'s measured routing repair was to **open** the description with
`Use BEFORE drafting or rewriting`. But `tests/test_seed_ai_tell.py` asserts
`d.startswith("Use when")`. The two cannot both hold. The forge made the routing change,
never ran the suite, and died. Any wording that satisfies the test is therefore
**unmeasured** and has to be re-probed, not assumed.

## Growth gaps found while auditing state

- `repeats/index.jsonl` is append-only by explicit design ("Nothing is ever rewritten or
  deleted") and is parsed in full by `jq` on every eligible `Bash`/`Skill` event. Measured
  32,702 bytes/day over a 5.21 day span. It reaches the 4 MB cap at
  `hooks/repeat-gate.sh:799` in **123 days, about 2027-01-01**, after which that arm
  `exit 0`s and the gate silently stops learning with nothing on any surface to say why.
  Failing open is right for a transient over-budget; it is wrong as a permanent terminal
  state reached with no prune and no signal.
- `statusline-cache/` has **no pruning code anywhere in the repo**. Key is a hash of
  `session_id|cwd`, so every new session leaves a permanent file. 51 files in 7 days.

Everything else prunes: `reminders/` (`-mtime +7`, sampled 1/25), `claim-gate` (`+2`),
`doc-gate` (`+7`), `forge` (`reap_temps`/`reap_claims` at 60 min).

## Pipeline health

Session review is **alive**, not broken: last dispatch 2026-08-31 14:17, verdict NONE,
indexed correctly. It is inside its own 21h cooldown. Three reviews ever run: NONE,
CANDIDATE, NONE.

Unactioned: the CANDIDATE `kill-and-rerun-full-suite` (2026-08-28) has zero ledger rows and
was never forged, and the insight queue holds 42 pending candidates, 0 declined, oldest 6
days.

## Resume state

Done: forge closed with a truthful reason (`skillforge fail`), ledger start now joined,
name un-wedged, status line clear. `scripts/probe_routing_claims.py` call count is now
derived rather than restated.

Next: land the four description repairs, fix the derived figures in `.claude/CLAUDE.md`,
`skills/skill-compounder/SKILL.md` and `skills/claim-provenance/SKILL.md`, re-probe all 10
skills for real (180 calls) and rewrite every pin whose description or prompt list moved,
then commit, push and merge to `main`.

Note the ordering trap: `test_the_measured_sweep_figures_are_re_derived_not_restated` pins
`claimed_diff` at 0, which only holds on a **clean tree**. The suite can only be fully green
after committing.
