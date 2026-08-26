# 2026-08-25 (evening): fixing everything in issue #9

Goal (user): fix ALL problems in issue #9; package fully usable with direct evidence it
works in a real Claude Code session, including the session doing the fixing.

## Fleet map (who owns what — do not double-dispatch)

| Item | State |
|-|-|
| Routing as completion gate (SKILL.md step 4, test_routing_gate.py) | LANDED; verified by running: 14/14 + doctrine 20/20 green |
| skillreport counts failed Skill calls as reuse | agent in flight (bin/skillreport + its tests only) |
| Routing probe, 8 skills, real sonnet calls | running in background, --json to scratchpad/routing-probe.json |
| Deterministic trigger dispatch (hooks/session-review.sh) | agent in flight |
| Forged skills auto-install + hot-reload (bin/skillforge, installer) | agent in flight |
| Cold review: forge install | agent in flight |
| Cold review: claim-provenance (issue #9 known-not-clean) | agent in flight |

## Direct in-session evidence collected so far

1. `Skill(claim-provenance)` succeeded in the driving session (it returned
   `Unknown skill` earlier the same day, before its symlink existed). Install +
   hot-reload confirmed live across a running session.

## Hazards being tracked

- Two agents edit `skills/skill-compounder/SKILL.md` (protocol step 4 vs hot-reload
  section). Diff-check the file when both land.
- `tests/test_forge_close_race.py` red: "anchor for the 'skillforge-legacy'
  reconstruction is gone from bin/skillforge" — belongs to the bin/skillforge holder
  (auto-install agent). Must be green before commit.
- Do NOT run ./run_tests.sh until the tree is quiet. Verify per-file until then.

## Remaining sequence after agents land

1. Verify each agent's work by running (never by report).
2. Read routing-probe.json; write/refresh routing pins for measured skills.
3. Full suite. Fix reds via new subagents.
4. Real-config install (idempotent; user explicitly wants this session usable).
5. In-session evidence pass: hooks fire, statusline, skillforge, skillreport truthful.
6. Commit + push green. Update issue #9 with evidence.

## Evidence log (append-only, each entry observed in the driving session)

2. Fixed `skillreport` run against the real ledger: claim-provenance USES SINCE = 2 —
   failed invocation excluded, successful in-session invocation counted. Headline 100%
   now derived, not inflated.
3. Hot-reload of DESCRIPTION edits observed live: rewritten descriptions for
   no-silent-stub, session-handoff, claim-provenance, ai-tell-audit, skill-authoring,
   stale-artifact-check surfaced in the running session's skill list while the editing
   agents were still working.
4. UserPromptSubmit reminder hook observed firing in the driving session
   ("[skill-compounder] Before starting implementation, check whether an existing
   skill already solves this").
5. Routing probes: session-handoff 6/6, no-silent-stub 6/6 (sonnet, cli 2.1.245,
   2026-08-25), pins stamped; verified by running test_seed_handoff (76 OK),
   test_seed_stub (28 OK).
6. Routing now verified by live probes for 8 of 9 skills (all but skill-compounder,
   whose SKILL.md was held by the auto-install agent): ai-tell-audit, claim-provenance,
   contribute-skill has no pin by design, destructive-op-preflight, no-silent-stub,
   session-handoff, skill-authoring, stale-artifact-check all 3/3 must-fire + 3/3
   must-not-fire, sonnet, cli 2.1.245, 2026-08-25. Two claims honestly rewritten
   rather than gamed (whole-skill authoring defers to writing-skills per doctrine;
   bare release-notes imperative measured as direct-generation).
7. Cold reviews produced real defects on both reviewed components (5 findings on
   claim-provenance incl. one measured-false shell claim; 7 findings on forge
   install incl. two HIGH). All claim-provenance findings fixed and re-verified,
   55/55 + 24/24 green after test reconciliation.
8. skill-compounder itself now verified 3/3 + 3/3 (was "partial" since forging).
   UNVERIFIED debt ledger in test_routing_claims.py is EMPTY as of 2026-08-25 —
   every shipped routing claim has been measured against a real session.
   routing_claims.py lint: 8 skills, 0 findings. Auto-install landed: `skillforge
   done` now links the forged skill (29 real-file tests; 20/22 failed pre-change),
   cold reviewer's 7 findings all fixed + regression-tested; skill-compounder §4
   rewritten to the measured hot-reload behavior (doctrine sync 20/20 green).
