# 2026-09-06 — responding to the external review of cb110a9

An external reviewer (pasted into the session, not on GitHub) reviewed HEAD cb110a9 and
left a probe script at /tmp/csc-review-probes.py. Every probe reproduced on HEAD before
any edit (run: `PYTHONPATH=$PWD python3 /tmp/csc-review-probes.py`):

1. Mission renderer quotes first + last 3, so a change of direction between them is
   elided (MISSION_CORRECTION: old_injected true, correction_injected false).
2. A fresh session's "continue" gets no mission (session_id filter) — DESIGN, not a bug.
3. Stop arm claims its per-prompt marker before rendering; a missing store burns it.
4. `skillnote skill` leaves three copies of an attached script (project, lessons/, skill).
   DESIGN question (canonical artifact) — not fixed this session.
5. `skillreport skills` says "No skills recorded yet" after a `skill` ledger row.
6. `--force` backup lands in `<skills>/<slug>.bak-...` — still in the discovery tree.
7. Funnel attributes a note at ts 100 to a nudge delivered at ts 200.
8. README says the lesson refuses "the second time"; the code refuses on the third session
   (REPEAT_MIN_SESSIONS earlier sessions, current excluded, since 2026-09-04).
9. docs/architecture.md:171 still says a renamed skill is invisible to reuse.
10. notes/2026-09-05-reconciliation-plan.md:51 promises scripts "moved" beside the skill;
    the code copies.

## Wave 1 (parallel, exclusive file ownership)

| Agent | Owns | Fix |
|-|-|-|
| M | hooks/mission.sh, tests/test_mission.py | recent slot = substantive requests; Stop claims after render |
| R | bin/skillreport + its 7 test files | `skill` rows in skills view; no exit before funnel; chronology |
| N | bin/skillnote, tests/test_skillnote.py | backup outside discovery tree; failed-replace + race tests |
| G | hooks/repeat-gate.sh, bin/skillrepeat + tests | lesson refusal on second session (this + one earlier) |

Docs/CLAUDE.md/notes: serial pass by the orchestrator after wave 1, from the sentences
each agent reports as made false.

## Left for Jeremy (outward-facing or direction)
- Rewrite #31, retitle #19/#30/#34, reopen the behavioural parts of #43 (GitHub edits).
- Cross-session / cross-project mission continuity (design).
- Canonical lesson artifact vs copies (design).
- Tag a release after the new mission + lightweight-skill code, pin installer, protect main.
- Demo/screencast recentred on the cheap path.
- Diet .claude/CLAUDE.md (history out of always-loaded instructions).
