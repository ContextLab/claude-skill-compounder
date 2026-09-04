# 2026-09-03 (evening) — completing #43, closing the open issues, red-team

Branch `resume/after-v0.3.1` at `977f434` (= `main`). Doctor at start: 11 pass. Mission
store at start: 18 deliveries across all five moments. Repeat store: 546 rows (311 fail,
235 recover, 0 cross_tool).

## The ask (verbatim in surfer; session f288cf8c)

Review #43 with all comments; refresh on notes; ultrawork to achieve the plan; goal: a
complete working version — code, prompts/content, all docs, address or close every open
issue, red-team the final version. Subagents for as much as possible.

## Plan (waves)

Wave 1 (code, disjoint ownership, all in flight at the time of writing):
- A `hooks/mission.sh` + `tests/test_mission.py`: prune of `<state>/mission/<sid>/`
  (the one piece #43's landing comment lists as missing).
- B `hooks/repeat-gate.sh`, `bin/skillrepeat` + tests: a live false binding seen in THIS
  session — `gh issue view ... --comments` exited 1 (GraphQL deprecation warning) and the
  same-tool rule bound an unrelated later Bash call; three identical `recover` rows for one
  tuid; the lesson statement named a different call than the row.
- C read-only: measure keyword-overlap level-B search precision on the live surfer store
  (the design note says a measured FP rate is what earns it).
- D #32: `hooks/precompact.sh` + test: jq-1.6 vs 1.7 timing, probe `custom_instructions`.
- E #37: attribution id through skillnote/skillinsight/skillforge/skillreport/remind.sh/
  insight-capture.sh/compound-improvement.sh + `tests/test_attribution.py`.

Wave 2: docs (every document, one agent per file group), knob table + derivation counts,
`.claude/CLAUDE.md`, SKILL.md mirrors; then full suite, clean-env run, commit, push, CI.
Wave 3: red-team — cold doc-accuracy review (claim-provenance), live functional stress of
the five moments and the lesson gate under the real config, adversarial hook review.
Then: fix wave, suite again, install here, issue comments/closures, notes, memory.

## Issue disposition (from the digest agent, verified against each issue)

- #19 leave open: applied-skill half blocked on #34; composition half not urgent.
- #30 leave open: blocked on #37 for the join; the sweep script is buildable.
- #31 epic: refresh the status table (#9, #33 closed); stays open while sub-issues do.
- #32 do work then close (D).
- #34 leave open: policy-blocked on a real recurring candidate.
- #37 do work then close (E).
- #42 leave open: verified today — fresh `CLAUDE_CONFIG_DIR` says "Not logged in"; no
  `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` in the environment.
- #43: close after the tail lands (prune, level B decision, measurement now possible).

## Dead ends this session
- `timeout` is not on macOS PATH (coreutils' `gtimeout` would be); the probe ran without it.

## Wave 1 + docs landed: `3d7a5cd` (code + docs groups 1-2), `7482254` (CLAUDE.md, OPEN-THREADS, SKILL.md)

Clock crossed midnight mid-wave; later stamps read 2026-09-04. Authoritative suite on the
quiet tree after wave 1: ALL TESTS PASSED, 53 files, 2 skips. Level B search measured twice
(plain and rare-token rules, haiku judge, 260 calls) and declined: FPR 0.72 at n=60, note in
`notes/research/level-b-search-measurement.md`. #32 resolved (13/4 programs, per-jq budget,
`custom_instructions` populated on 2.1.260). #37 built (lineage id derived from the queue
digest; FUNNEL; counted conversion; `tests/test_attribution.py`).

## Red-team round 1 (adversarial hook review) — to fix

1. HIGH `hooks/compound-improvement.sh`: `find $STATE_DIR -type f -mtime +7 -delete` (:165)
   deletes `reminders/nudges.jsonl` (:279); the FUNNEL dies silently after a week.
2. HIGH `bin/skillreport`: FUNNEL omits lineages whose ledger rows carry `from` but have no
   delivery row, and does not count them as unattributed either.
3. MED-HIGH `bin/skillreport`: funnel join O(lineages x rows), 50.5 s at the writers' caps.
4. MED sanitiser lets `.`/`..` through in every script; mission prune then removes the live
   session's own claims (`.`), or writes into the state root (`..`). Hardening.
5. MED `2>/dev/null` placed after `>>` in remind.sh:508/512, mission.sh:768 (+ others),
   so the shell error reaches the user's stderr; log_nudge's comment claims otherwise.
6. LOW-MED MISSION_PRUNE_* knobs lack the magnitude guard (huge value -> `[: integer
   expression expected` on stderr).
7. LOW `--from ..` / `--candidate ..` accepted.
Also: `tests/test_precompact.py:382-388` docstring carries pre-#32 medians; two
`.claude/CLAUDE.md.bak-skill-compounder-19700123-*` backups (Sep 3 09:09 and 12:53, before
this session) mean something ran skillnote against the REAL project CLAUDE.md with a pinned
clock — find the test that lacks cwd isolation.

Held up: end-to-end lineage, dedup, payload fuzz (10 hooks x 7 events), 200 KB commands,
log_nudge concurrency and trim, precompact, env hostility, prune symlink/charset/future
mtime, CLI id validation.

In flight: live functional stress (18 haiku calls, real config); cold docs-accuracy review.
