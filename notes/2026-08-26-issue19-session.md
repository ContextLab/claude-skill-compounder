# Issue #19 — closing the gap: what was measured, built, and refused

Session of 2026-08-26, starting from `b10638f`. The plan of record is
`notes/2026-08-26-issue19-plan.md`; this file is the evidence log. Read it for what was
actually run, not for the current state of the code.

## The premise in issue #19 that turned out to be false

> when the tool is built and ready for use, the user receives a notification that the new
> skill is now avaiable (and skills hot reload so that it can be used)

Skills **do** hot reload, and the parenthesis is right — but the first `Skill` call after
creating one fails about half the time, and an earlier probe in this session concluded from
that that hot reload was broken entirely. Both the false negative and an earlier false
positive came from the same mistake, which is now the most transferable thing measured here:
**a probe that scores a skill invocation on whether a marker string appears in the session's
prose is measuring nothing.** A session that has *read* a SKILL.md reproduces its marker
without ever launching it. Only `Launching skill:` versus `Unknown skill:` in
`--output-format stream-json` is evidence.

Controlled re-measurement, 4 runs per arm, CLI 2.1.246, `claude-haiku-4-5-20251001`:

```
run 1  USE → Unknown skill   USE → Launching skill   USE → Launching skill
run 2  USE → Unknown skill   USE → Launching skill   USE → Launching skill
run 3  USE → Launching skill USE → Launching skill   USE → Launching skill
run 4  USE → Launching skill USE → Launching skill   USE → Launching skill
subagent runs 1-4   USE → Launching skill   (first attempt, every time)
```

The subagent arm is the useful half: **a subagent dispatched after the install has no lag at
all**, 4/4, which is what makes closing a forge loop with a subagent reliable rather than
racy.

## The forge that was refused before it started

`documentation-sync` was pre-registered, briefed, and then **not forged**, because section 1
of `skill-compounder` says to invoke an existing skill rather than reimplement one, and
`claim-provenance` already owns every phase the brief asked for — including the diff-driven
entry that was supposed to be the new skill's distinguishing feature. The record is
`~/.claude/skill-compounder/briefs/documentation-sync.REFUSED.md`.

Two things changed because of that refusal. `hooks/doc-gate.sh`'s deny reason names
`claim-provenance`, a skill that exists and has been red-teamed, rather than one forged the
same hour. And issue #19's composition requirement is now demonstrated across *packages* —
`finish-task` invoking `claim-provenance` and `superpowers:finishing-a-development-branch` —
which is stronger evidence than two skills forged together calling each other.

## The repeat gate, fired for real

Four real headless sessions in one scratch project sharing one state directory. Sessions 2
and 3 ran `gh zzz-not-a-real-subcommand --sync`, which failed identically in both; session 2
also ran the workaround. Session 4 attempted the same command and **the call never ran**:

```
USE  gh zzz-not-a-real-subcommand --sync
RES  This exact call has already failed in 2 earlier sessions, the same way each time.
       the call:  gh zzz-not-a-real-subcommand --sync
       the error: Exit code 1
                  unknown command "zzz-not-a-real-subcommand" for "gh"
     what worked instead, in 1 of them:
       echo WORKAROUND-USE-GH-API
     Nothing ran and nothing was written.
```

Session 4's own account of it, unprompted: *"the system has a gate tracking this exact failed
call across sessions … If you want to run it again anyway, you can use `skillrepeat forget
c2220971637x40-e2612515451x66`."* No model in the gate, no judgement, two integers on disk.

**The first attempt at this test failed, and the reason is worth keeping.** Session 1 declined
to run anything at all — it read "run a command that will fail, then run a workaround" as
suspicious and asked a clarifying question instead. So only one earlier session had failed
when session 3 ran, one short of `REPEAT_MIN_SESSIONS=2`, and session 3 was correctly allowed
through. The gate was right and the test was wrong. A live trigger test that needs N distinct
sessions has to **verify N actually happened** before reading the absence of a refusal as a
failure.

## What is on the sealed acceptance key

Ten claims in this repository that the issue-#19 change made false, written down before the
finished `finish-task` skill was run against them, at
`<scratchpad>/acceptance-key.md`. Sealing it first is the only way the run can be scored
rather than rationalised.

## The documentation gate, fired for real

A scratch repository with a real bare remote, a real upstream, and `hooks/doc-gate.sh` wired
on `PreToolUse`/`Bash`. One headless session, told only *"Push this repository to its
remote."* It spent a while linting, committed a code-only change, and then:

```
USE  git push origin main
RES  This push carries code changes and no documentation change.
     2 commits are about to leave this repository, touching these code files and not one
     documentation file among them:
         - .claude/settings.json
         - lib.py
     The `claim-provenance` skill exists for exactly this. Its Iron Law is RESTATE
     NOTHING, RE-DERIVE EVERY CLAIM FROM THE THING IT DESCRIBES, OR DELETE IT ...
```

The session then edited `README.md`, amended the commit, pushed again, and the push went
through — the remote moved from `a215fe3` to `83b3e5b`. Nothing was overridden; the
overrides file was never created, which is what "no exception was taken" looks like.

That is issue #19's requirement 2 end to end: a refusal, a documentation change, and a push
that then succeeds. No reminder was involved and none would have worked — the same session
had already run six linters and written a notes file without once looking at the README.

## A defect this found in our own work

The gate's deny reason named a skill called `documentation-sync`. That skill was
pre-registered and then deliberately never forged, because `claim-provenance` already owned
the ground — so the refusal was sending sessions somewhere that does not exist, which is
worse than naming nothing. Fixed, and `tests/test_doc_gate.py` now asserts the *class*
rather than the string: whatever skill the reason names must have a `SKILL.md` on disk,
either in this checkout or installed.

## State of the work, as of the last full suite run

`TEST_TIMEOUT=400 ./run_tests.sh` → **ALL TESTS PASSED**, exit 0, over 40 test files. That was
after the first fix round and before the consolidation round below, so re-run it rather than
quoting it once the tree settles.

### What is on disk and uncommitted

New: `hooks/repeat-gate.sh`, `hooks/doc-gate.sh`, `hooks/apply-gate.sh`, `bin/skillrepeat`,
and five test files (`test_repeat_gate.py`, `test_doc_gate.py`, `test_apply_gate.py`,
`test_forge_apply.py`, `test_skillreport_apply.py`).
Modified: `bin/skillforge` (the `apply`/`pending` subcommands and the pending-apply marker),
`bin/skillreport` (the fifth ledger question and the two gate surfaces), `bin/skillinsight`
(sanitisation drift), `statusline/skillforge-status.sh` (the pending segment and a `fit`
fallback that had inverted above ARG_MAX), `skill_compounder/installer.py` and
`hooks/hooks.json` (12 entries across 5 events, both paths agreeing),
`tests/test_script_wrapping.py` (the new identity-sanitisation invariant),
`tests/test_doctrine_sync.py` (`CLAUDE_CODE_SESSION_ID` is ambient), `scripts/setup.py` (the
CLI list is derived, not restated), `docs/CLAUDE-CODE-BEHAVIOR.md`, `docs/DESIGN.md`.

### Deliberately NOT yet done, and why

`README.md`, `.claude/CLAUDE.md` and `skills/skill-compounder/SKILL.md` carry ten claims the
change made false. They are listed in a **sealed scoring key** written before the finished
`finish-task` skill was run against them, so that the acceptance test can be scored rather
than rationalised. Leaving them stale is the experiment, not an oversight. The key is at
`<scratchpad>/acceptance-key.md`; if the scratchpad is gone, the ten rows are recoverable by
re-deriving them (`grep -n 'seven hook entries\|only component here that refuses\|Four CLIs\|five clocks' .claude/CLAUDE.md README.md`).

### The cold-review record, which is the substance of this session

Five components went through build → cold review → fix → **independent** cold re-verification.
Every reviewer was a fresh agent, never a fork. Reproduced defects, by component: doc-gate 7,
apply-gate + status line 3, `skillforge apply` 6, repeat-gate + `skillrepeat` 6, `skillreport`
5 (one of them a **pre-existing fatal**: a single well-formed non-object ledger line made both
parses raise, jq exit 5, and collapsed the whole report to "no forges recorded yet" over a
full ledger).

Two patterns worth carrying forward:

1. **Re-verification is not optional.** `skillforge apply`'s D2 — a failed ledger append that
   still deleted the debt and printed "recorded … The loop is closed" — was reported fixed and
   was not: the same false-success arrives by two other paths. Only a second cold agent found
   that.
2. **Four of five repeat-gate residuals were stated numbers that did not reproduce.** Figures
   written into a script header decay exactly like figures in a README, and nothing in the
   suite reads them. That is `claim-provenance`'s subject appearing in code comments.
