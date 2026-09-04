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

## Red-team round 1 (live functional, real config, 10 claude -p calls)

PASS: resume (canary quoted), ambiguity, completion (one block, one row), lesson first time
(one row per tuid, statement = row), lesson refusal lifted by `skillnote add --lesson`,
no binding for `gh issue view 9999` -> `npm run build`, prune, no leaks (13 live jsonl files
parse, 0 hook stderr / non-zero exits across 7 sessions). LIMIT: a subagent receives the
mission and still answers "NOT KNOWN" (third observation). FAIL: FUNNEL arithmetic.

Defects: (1) HIGH the deny text names `skillrepeat dismiss` and 2/2 haiku sessions ran it
with a fabricated `--why`; `bin/skillrepeat` records `session:"cli"`. Decision: a lesson is
the only thing a SESSION can do to lift the gate; dismiss records `actor` (model when
CLAUDECODE/CLAUDE_CODE_SESSION_ID is set) and only a human dismiss lifts. (2) HIGH the
"earlier sessions only" guard does not exist (`repeat-gate.sh:1538` counts the current
session). (3) FUNNEL: ACTED ON 104 vs DELIVERED 69; a lineage with ledger rows but no
delivery is counted nowhere. (4) `skillinsight promote --scope project` writes into the
candidate's originating repo regardless of cwd. (5) residual same-tool binding on path
tokens {remind, hooks}. (6) a Stop block costs one empty assistant turn (platform).
(7) `mission.sh` exits before the prune when the surfer store is absent.

## Red-team round 1 (cold docs-accuracy review) — to fix in the docs touch-up

1. `.claude/CLAUDE.md:219-231` mission moment citations (:344/:353/:349/:609/:356-377/:382/
   :387/:440-441) are off by 110-345 lines; re-derive after the fix wave.
2. README.md:257 "only two env vars install.sh reads" — it reads five; operations.md:483 says
   four. `grep -nE '\$\{(SKILL_COMPOUNDER|CLAUDE_SKILL_COMPOUNDER)[A-Z_]*:-' install.sh`.
3. `hooks/compound-improvement.sh:404` "SessionStart is not among the three events" — eight
   events, SessionStart wired.
4. README.md:224 "2.1.241 through 2.1.259" — the printed command yields 2.1.260.
5. `.claude/CLAUDE.md:289`, `:379` repeat-gate citations off by 64 (REFUSE at 504/694; exec
   2>/dev/null at 688) — re-derive after the fix wave.
6. Stale cross-file cites: `bin/skillnote:161` (installer 206-207), `:265` (repeat-gate
   hashof 1041), `:304` (installer 227); `hooks/mission.sh:41` (skillnote 283, skillforge 1381).
7. docs/development.md:45 "six claude -p calls" — journey is 13 calls / 17 steps.
8. `.claude/CLAUDE.md:24` "every entry names the CLI version" — two behavior entries carry
   none (child-result, SessionStart-before-typing).
9. `.claude/CLAUDE.md:273` recount recipe returns six files (remind.sh:31 comment matches).
10. README.md:52 Status "six sonnet calls, 34.9 s" — current shape 13 calls / 150.9 s / 17.
Verified clean: 20/10/8, 12 skills, 6 CLIs, 11 doctor checks in order, 14 clocks, 22
prefixes, 156/158 names, 53 test files, every header-documented env default, install/
uninstall leaves a user's own SessionStart hook, README five-minute path runs verbatim.

## Fix wave (uncommitted at the time of writing, on top of `807665d`)

- Lesson gate: deny names only `skillnote add --lesson`; `skillrepeat dismiss` writes
  `actor` (model when CLAUDECODE / CLAUDE_CODE_SESSION_ID is set) and the real session; only
  a human dismissal lifts; the gate excludes THIS session's fail rows from the
  REPEAT_MIN_SESSIONS count (the header had promised it; the code did not).
- FUNNEL: single jq pass, a printed partition definition and a `CHECK:` line; 47.9 s -> 5.9 s
  at the writers' caps; live store CHECK 40+973=1013 (later 42+973=1015).
- Sanitiser guard line (`''|.|..` -> `_`) after every session-id sanitiser in 12 scripts,
  pinned by `test_script_wrapping.py::IdentitySanitisationTest`.
- compound-improvement.sh sweep is by counter-file name (was deleting `nudges.jsonl`);
  `CI_PRUNE_EVERY=0` divide-by-zero; magnitude guards on all numeric CI_/MISSION_/REMIND_
  knobs (out of range takes the default; `CI_NOW=abc` used to exit 1 on the second prompt).
- `2>/dev/null` moved BEFORE `>>` at 14 sites (the shell's own redirection error reached
  the user's stderr otherwise).
- mission prune also runs on the missing-store exit; `set_sdir()` is the one sanitising site.
- `skillinsight promote` prints its absolute target first, refuses a missing project dir;
  `skillnote where`. `--from`/`--candidate` refuse `.`/`..`.
- Test isolation: `tests/test_skillrepeat.py::RepeatCliCase.note_cli` was the writer of the
  1970-stamped backups (clock 2_000_000 -> local stamp 19700123-2233xx); byte guards on the
  repo's own `.claude/CLAUDE.md` in test_skillrepeat and test_queue_surfacing.
- Docs touch-up for all of the above and the cold review's ten contradictions; `.claude/
  CLAUDE.md` now cites mission moments by `moment="…"` anchor + grep instead of line numbers.
- `CLAUDECODE` added to `tests/test_doctrine_sync.py` AMBIENT (platform-exported, like
  CLAUDE_CODE_SESSION_ID); the derivation alternation did not need widening.

## Red-team round 2 (live, 6 haiku calls): dismiss fix holds

The denied model wrote the lesson (after one wasted retry) and never reached for dismiss,
even when told to record nothing. New: (1) allowlist bypass — `cd build && tar ...` is
ALLOWed because only the first word is read (a haiku session found it unaided on attempt 5);
(2) the deny advertised its 2-refusal budget and a session waited it out; (3) `skillinsight
promote` writes into the candidate's project regardless of SKILL_COMPOUNDER_STATE (it wrote
into this checkout's CLAUDE.md again; removed with `skillnote remove n1240016210x82`);
(4) note ids hash `<scope word>|<text>`, so identical text in two projects shares one id
(limit, not changed). Fix 3 in flight for (1) and (2).

Suite after the fix wave (smoke, docs agents editing): one failure, the new isolation guard
in test_queue_surfacing tripped by the red-teamer's live promote writing into the checkout
mid-run — the guard working, not the test failing. Authoritative run pending on a quiet tree.
