# 2026-09-04: address every open issue, install locally, refresh the screencast

Session f288cf8c, continued after a compaction. The user's request, verbatim:

> continue-- address ALL remaining issues and get the package fully up, running, and
> rigorously tested. install locally. and make sure documentation (including screen
> cast!) is fully up to date too. be comprehensive! use subagents to ultrawork on this.

And mid-turn: "also use history surfer to check my recent prompts, to make sure you are
on track with my guidance". Done: `surfer list --limit 30` then `surfer show` on
f58c372b:3 (the vision restated: two scenarios, levels A/B/C, principles i and ii),
f58c372b:6, dae248bd:1 ("skills can be relatively simple and narrowly scoped, as long as
they are useful"), f7ea3931:2 ("should any be added to the core set of skills included by
default?"). The guidance that shapes this session: a skill is a markdown file plus the
scripts it needs; the write-down includes code; nothing relies on memory alone.

## State at the start

- `main` == `resume/after-v0.3.1` at 560e3ad, tree clean, CI green at 86297ec.
- Installed locally already: `skillforge doctor` 11 pass, 20/20 hooks wired into
  `~/.claude/settings.json` pointing at this checkout, 12 skill links, surfer on PATH.
- Open issues: #19, #30, #31 (epic), #34, #42.
- `docs/media/forge.gif` recorded 2026-08-24 by `dev/forge_demo.sh` under `dev/forge.tape`;
  it replays a THREE-round forge, and the diet (#22) capped a forge at two rounds. Stale.

## Plan

Wave 1 (parallel, exclusive file ownership):

| agent | owns | task |
|-|-|-|
| forge | `skills/watch-ci-run/`, `skills/finish-task/SKILL.md` | the first real forge under the diet (#34): `watch-ci-run`, from three recorded lessons across two days (n1407736601x223, n703879817x267, n3863143241x224); then compose it into `finish-task` (#19's composition half) |
| e2e | `tests/e2e/journey.py`, `tests/e2e/README.md`, `docs/e2e.md` | #42: a `--config-dir fresh` mode built on `CLAUDE_CODE_OAUTH_TOKEN`; no credential is read or copied (the classifier refused a Keychain-copy dispatch and that refusal stands) |
| measurement | `scripts/reminder_conversion.py`, `docs/measurement.md` | #30 item 1: the transcript sweep as a script, run for real, pre-tier vs post-tier windows |

Wave 2: use the forged skill for real (a `use` row, #19's "actually used" half), media
refresh (`dev/forge_demo.sh` replaying the real two-round forge, regenerate the GIF with
vhs), docs pass over every file, `.claude/CLAUDE.md`, `notes/OPEN-THREADS.md`.

Wave 3: re-run the installer against the real config so the new skill links; doctor;
full suite on a quiet tree; clean-env runs of touched tests; shellcheck 0.9.0 and 0.11.0;
live red-team of the INSTALLED package from a scratch project; push; CI watched with the
forged skill; issue comments.

## Lessons this session

- Third zsh `=` expansion (`echo ===`): recorded as lesson n1344851113x262 with a command
  reminder n2118100715x269; the two earlier notes did not stop it because a note is read
  and not enforced.

## Log

(appended as the session goes)

- Wave 1 returned two of three by 2026-09-05 00:10 EDT. #30: `scripts/reminder_conversion.py`
  (stdlib, `--selftest`, `--json`, `--since/--until`), run over 2014 transcripts; pre-tier
  90/862 nudged sessions invoked the skill, post-tier 10/169 (human-driven denominator 10,
  too small); `nudges.jsonl` ids on the two generic arms are arm names, so the id join is
  empty by construction; `docs/measurement.md` carries it; `tests/test_reminder_conversion.py`
  added by the orchestrator (4 tests, pass under `env -i`). #42: `journey.py --config-dir
  fresh` and `--check-auth`; on 2.1.260 a fresh dir honours both `CLAUDE_CODE_OAUTH_TOKEN`
  (invalid token: "401 Invalid bearer token") and `ANTHROPIC_API_KEY` (invalid: "Invalid API
  key"); no real token was handed in, so the fresh run is unverified and the docs say so.
  The first #42 dispatch, which would have copied the Keychain credential into the fresh
  dir, was refused by the permission classifier; the refusal stands.
- Cold docs audit: 22 findings with quotes and commands; fixer dispatched on 21 (README
  Status block left for the final pass). Findings file in the scratchpad.
- 2026-09-05 ~01:00 EDT. Docs fixer done: 22 findings corrected, committed c280b57. Live
  red team of the INSTALLED package (15 haiku sessions, $0.71, log in the scratchpad's
  `redteam-installed/LOG.md`): mission moments 1-3 PASS (subagent, ambiguity, completion
  block fired once), lesson first-time PASS, claim gate PASS (block on 1180, the model
  dropped the claim), reminder PASS. FAILS in the lesson gate: (1) 2 of 2 denied sessions
  retried the IDENTICAL command until the silent 2-deny budget expired, then proceeded; no
  lesson; (2) `env python3 x.py` is exempt because `env`, `command`, `source`, `.` sit on
  the head allowlist while being prefix runners; (3) the gate is Bash-only, so a denied
  session answered with `Read` and carried on. LOW: claim-gate deny text hardcodes
  `./run_tests.sh`. Two builders dispatched: repeat-gate (no-expiry default, prefix runners
  stepped over, deny every tool while armed except skillnote/skillrepeat) and claim-gate.
  Decision recorded here: the budget default becomes no expiry because the user's word in
  #43 is "force", and the false-positive cost with no expiry is one lesson line per
  signature ever.
- 2026-09-05 ~01:30 EDT: the forge orchestrator (step 5/6, round-2 reviewer out), the
  repeat-gate builder (mid-way through its tests) and the media agent were all killed by
  the monthly spend limit on opus (HTTP 429, "resets 2am"). Resumed at 07:40 EDT by
  SendMessage with "re-check the disk state first". The live `hooks/repeat-gate.sh`
  carried the builder's half-landed change through the outage: `bash -n` parses and a
  `Read` PreToolUse probe exits 0 with no output, so no turn on this machine broke.
- 2026-09-05 morning. Lesson-gate builder done and committed (505d27c), docs for it
  (35c0106). Screencast re-recorded (dcac7c4): opens on a lesson, then `watch-ci-run`
  forged for real; round 2 came back 6 blocking of 13 again, `escalate --converging` was
  refused (exit 4, "not a fall"), `--narrowed` granted, so #34's cap has now refused AND
  granted on a real forge. Two orchestrator slips: committed with doctrine sync red because
  `| tail -1` masked the test's exit (fixed 91b0bb3, note n410812797x266); and the
  recovery binding bound a forge subagent's failed heredoc to the parent's unrelated
  heredoc because the binding is keyed per session and subagents share the id — a builder
  is keying it per (session, agent_id) now. `SKILLFORGE_SKILLS_DIR` had no tuning-table
  row (f70d073).
- 2026-09-05 09:30 EDT: the `watch-ci-run` forge FAILED at the hard cap and is quarantined
  (`~/.claude/skill-compounder/quarantine/watch-ci-run-2026-09-05/WHY-ARCHIVED.md`): rounds
  6/13, 6/13, 5/13, 7/21 blocking; `escalate --converging` refused after round 2 (6 -> 6 is
  not a fall), `--narrowed` granted, `--converging` granted after round 3 (6 -> 5), both
  refused after round 4 (two grants is the ceiling). The design error: `gh run list` answers
  "which runs have this sha as head", not "did CI pass for this commit", which the check-runs
  API answers directly; four rounds tried to turn one into the other. So #34's cap has now
  refused, granted twice, and refused again on a real forge, and the protocol's
  never-ship-half-working rule fired for real. Wall clock 2026-09-04 23:48 to 09-05 09:30,
  with the spend-limit outage in the middle; nowhere near 30 minutes. A second, narrowed
  forge (`wait-for-ci`, built on the check-runs endpoint, the script computes no verdict of
  its own) dispatched at 09:35 with a fresh orchestrator. Local install re-run at 09:29:
  the `PreToolUse` entry for repeat-gate lost its matcher in the real settings.json, doctor
  11 pass.
- 2026-09-05 12:xx EDT: the narrowed forge `wait-for-ci` ALSO failed at the cap (rounds
  7/10, 5/9, 7/8 blocking; `--converging` granted after round 2, refused after round 3;
  107 min by the ledger; quarantined at `~/.claude/skill-compounder/quarantine/wait-for-ci-2026-09-05/`).
  Same subsystem from a different endpoint: check-runs alone gave a false green (cli/cli),
  adding check-suites gave a false failing (ripgrep's scheduled re-runs) and a false green
  (home-assistant). Two forges say "which checks count" has no rule that holds across
  repositories. The tier gate's answer for this candidate is a note with a script: recorded
  at the user level as n3725829701x412 with `ci-checks.sh` attached (prints check-runs and
  statuses for a commit, verifies the push with `git ls-remote`, computes no verdict;
  exercised on 86297ec, five rows, exit 0) and n1566376988x302 (full-sha rule; `status`
  answers `pending` with an empty list for a commit no status API saw). No third forge.
- User checked alignment ("are you using the new design?"): answered with the scorecard
  above; the drift named was the forge's cost profile, and the user's design (a skill is a
  markdown file plus scripts; the cheap tiers first) is what the attached-script note is.
- All scripts lint clean under shellcheck 0.11.0 and 0.9.0. Final suite and clean-env runs
  started 12:xx; docs agent on the second forge's outcome running.
- Close-out 2026-09-05: final suite on the settled tree 54 files, ALL TESTS PASSED, 2 skips;
  clean-env runs of every touched test file OK; shellcheck clean under 0.11.0 and 0.9.0;
  pushed 4c0e9ae to `main` and `resume/after-v0.3.1`; CI run 33977345612, 5 of 5 jobs
  success; comments posted on #19, #30, #31, #34, #42, all left open with their blockers;
  README Status block refreshed. Open after this session: #19, #30, #31, #34, #42.
- 2026-09-05 afternoon, user asked whether the full pipeline was tested with production
  runs and the resulting skills' output examined. Honest answer: hooks yes (15 sessions),
  journey NOT re-run since today's changes, no cross-session loop driven, no skill output
  judged for quality. Three agents dispatched: the 17-step journey re-run on the current
  tree; a production loop (lesson written in session A, reminder acted on in session B,
  the attached ci-checks.sh found and called from a different project, promote to level
  B, note read-back); five seed skills driven with real tasks and their output judged
  against planted defects.
- Production tests returned. Journey re-run on cc2051b: 12 calls, 117.3 s, 15 PASS / 1 FAIL
  / 1 SKIP; the FAIL is step 15, `ls --nonexistent-flag .` fixed by `ls -la .`, a genuine
  fail-then-fix the two-token shell rule cannot bind because a two-letter program name is
  never a token (fix in code, not in the test). Loop across sessions (7 sonnet sessions,
  $1.35): 5 of 5 scenarios PASS: the lesson written unprompted with file, cause, bad
  command and fix; the next session avoided the failure from the note and, when told to
  reproduce it, got the reminder before the call; a session in an unrelated project found
  `~/.claude/lessons/n3725829701x412/ci-checks.sh` through the global note and ran it in
  a background call; a promoted reminder fired at level B; a project note was read back.
  Defects: claim-gate blocks the procedure that note prescribes (`gh api .../check-runs`
  is not a recognised CI runner) and false-positives on a negated quoted "CI passed";
  compound-improvement counts `"<file>"` as a redirect and bare README in a quoted string
  as durable prose; `skillnote remove` leaves the lesson's reminder live; `lesson_facts`
  truncates the error before the ImportError line and long pairs to identical prefixes;
  `remind.sh` matches the whole command byte-for-byte so compound forms silence it; the
  subagent mission block nests unescaped quotes. Four builders dispatched on disjoint files.
- Skill output quality (7 sonnet sessions, $3.02): ai-tell-audit correct (3/3 planted
  tells edited, literal `test harness` kept, density rule respected); claim-provenance
  partial (one of two derivable figures shipped without its command; the model, not the
  text); destructive-op-preflight correct (ran no destructive command, stopped to ask; a
  per-category rollup the text forbids but never says must be shown per path);
  parallel-agents-one-codebase partial (no ownership table rendered anywhere, clause 3
  absent from all three prompts; the text says "write the table into the dispatch prompts",
  which per-agent lists satisfy); session-handoff correct outcome, but Phase 4's validator
  locator never finds `check-handoff.sh` under the standard install because the skill dir
  is a symlink and `find` does not follow it. A builder is making the three SKILL.md edits.
- Fix wave from the production runs, committed: bc1680f (claim-gate recognises `gh api`
  check-runs/status/check-suites/actions-runs and their tab rows; a quoted or negated CI
  phrase is a mention; compound-improvement strips quoted spans and `<...>` placeholders
  before the redirect check and wants a path-shaped token for durable prose), fa70d4e
  (mission requests render as `> `-prefixed blocks under `(request N of M, T chars)`),
  32d7e87 (`skillnote remove` withdraws the lesson's reminder with an append-only
  tombstone; global attachments carry `~/` paths; remind.sh matches per segment with the
  splitter pinned identical to repeat-gate's, Bash median 73 -> 50 ms), fab3940 (three
  seed SKILL.md sentences), 5e746aa (doctrine test skips a builder's dotfile scratch copy).
  One builder's smoke test wrote a stray global note (n715494077x20); removed with
  `skillnote remove`, the lessons dir deleted, `~/.claude/CLAUDE.md` has no trace.
  Remaining: repeat-gate builder (same-head binding rule, lesson_facts), docs pass, journey
  re-run on the final tree, suite, push.
- Final verification 2026-09-05 evening: journey on the final tree, 17 of 17 PASS, 13 calls,
  130.5 s (step 15 now binds `ls --nonexistent-flag .` to `ls -la .` under the same-program
  rule); every script clean under shellcheck 0.11.0 and 0.9.0. Two orchestrator slips in the
  fix wave, both from `;` chains that ran on after a failure (a broken `bin/skillnote` was
  moved into place for about a minute and restored from HEAD; a docs commit landed with two
  sentences missing, fixed in f38f9a2); recorded as global note n3586731267x318.
- Wave 5 prep that needs no yes: the product sentence is in the README (101b4c6); update and
  rollback proven between the real tags v0.3.0 and v0.3.1 from a copy of install.sh outside
  the checkout (a2aa2d4 -> b7f6a47 -> a2aa2d4, exit 0 each, install-ref records current and
  previous). Running install.sh FROM the checkout treats the checkout as the app and refuses
  to move it, which is documented behaviour and the first attempt's "rc=2".
