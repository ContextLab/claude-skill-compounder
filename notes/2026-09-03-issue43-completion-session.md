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
