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
