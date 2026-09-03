# 2026-09-03 handoff: after v0.3.1

## Resume command

```bash
cd "/Users/jmanning/claude-skill-compounder"
git stash push --message "before resuming 2026-09-03" || true
git checkout -B resume/after-v0.3.1 ad9857770a28e5c6d186898ab7b7831ee32c7c15
```

Then, before anything else: read `notes/2026-09-02-audit-and-replan.md` (the audit, the
plan, and the execution log of every wave), then `gh issue view 31` (the status table),
then `notes/OPEN-THREADS.md`. `main` and `issue-19-close-the-gap` were both at this sha
when this note was written; the practice is everything on main, fast-forwarded after each
green commit, no PRs.

## State

branch: issue-19-close-the-gap
commit: ad9857770a28e5c6d186898ab7b7831ee32c7c15
uncommitted work: none

```
$ git status --porcelain
```

Tags: `v0.3.0` = a2aa2d4, `v0.3.1` = b7f6a47, both released on GitHub. CI green on both
platforms for every commit from cfb2bc6 onward (last checked run 33731348166 on b7f6a47).
The live install on this machine points at this checkout (`git describe --tags` printed
`v0.3.1-1-gad98577`); `skillforge doctor` printed `9 pass, 0 warn, 0 fail`.

## Done and verified

- Three compounding tiers exist and work in real headless sessions. Proved by
  `python3 tests/e2e/journey.py --out <dir>` on a2aa2d4, which printed a 12-step table, all
  `PASS`, 6 sonnet calls, 40.8 s (REPORT.md under the session scratchpad, since deleted;
  re-run to regenerate).
- CI is green on Ubuntu and macOS. Proved by
  `gh run list --json headSha,name,status,conclusion`, which printed
  `tests:completed:success` for cfb2bc6, a2aa2d4, c9803bc and b7f6a47, and
  `gh run view <id> --json jobs` listing every job `success`.
- The whole suite passes locally. Proved by `TEST_TIMEOUT=300 ./run_tests.sh`, last tail
  `ALL TESTS PASSED`, 48 files, exactly 2 skips (`LiveProbeTest`, `ItActuallyNeededFixing`,
  the two `.claude/CLAUDE.md` documents).
- Update and rollback between the two real tags work. Proved in a throwaway config on
  2026-09-03: install pinned at v0.3.0 (`git describe --tags` → `v0.3.0`), standalone
  `install.sh --update --ref v0.3.1` → `v0.3.1`, `--rollback` from the managed v0.3.1 copy
  → `v0.3.0`, the managed v0.3.0 copy's `--update` → still `v0.3.0` (the bug v0.3.1 fixes,
  documented in docs/releasing.md), standalone `--update` → `v0.3.1`; doctor `9 pass`;
  `install-ref` printed `current v0.3.1 b7f6a47…` / `previous v0.3.0 a2aa2d4…`.
- Paid session review is opt-in. Proved by `grep -n 'SKILL_COMPOUNDER_REVIEW:-0'
  hooks/session-review.sh hooks/insight-capture.sh` (both readers) and
  `tests/test_session_review.py` (76 OK, incl. `OptInTest`).
- The tracker matches the code. Proved by `gh issue list --state open`, which printed
  exactly: #9, #19, #30, #31, #32, #33, #34, #37, #42.

## Done but NOT verified

- The reminder hook's defaults (`REMIND_MAX=2`, once-per-session cooldown) were chosen,
  not measured. What would prove them: hit counts from `~/.claude/skill-compounder/remind/
  hits.jsonl` across several real repos over time (#33, #30).
- The forge diet has never run a real forge end to end since it landed (#34). The CLI half
  (`skillforge round` refusing round 3 with exit 3, `escalate`, `apply`, `verdict`) is
  exercised by tests and by the E2E journey's step 7, but no skill has been forged under
  the two-round default by a live session. What would prove it: one narrow real forge,
  timed against the 30-minute target, closing with `apply` and `verdict`.
- Linux behaviour of the four platform-dependent tests fixed in 89ca608 was simulated with
  GNU-shaped shims on macOS, then confirmed only by the Ubuntu CI job going green. No
  Linux machine was used directly (no docker here).

## Broken

None.

## Dead ends

- Tried watching CI with `gh run list --commit <sha>`. It returned nothing and the watcher
  timed out after 27 minutes. Filter `gh run list --json headSha,...` on a `startswith`
  of the sha instead (recorded as a project note in `.claude/CLAUDE.md`).
- Tried asking a `Plan`-type subagent to write a design file. That agent type has no Write
  tool; the whole spec came back as chat text and had to be re-saved by hand (twice). Use
  `general-purpose` when the deliverable is a file (recorded in project memory).
- Tried testing the installer's managed-copy fix by copying the fixed `install.sh` into the
  managed clone. That dirtied the clone and the checkout was refused; `git stash` then
  restored the OLD script, so the "clean" run tested the unfixed code and looked like a
  failure. Commit the file under test inside the clone instead (what
  `tests/test_install_sh.py` now does with `git archive` plus an overlay).
- Tried `cr=$?` after `checkout_ref "$REF"` under `set -e`. A non-zero return aborts the
  shell before `cr` is read, so both branches were dead and the exit code was wrong by
  luck. The form that works is `cr=0; checkout_ref "$REF" || cr=$?`.
- Tried pinning a writer/reader contract with a hand-written fixture on one side (twice:
  the edit counter, the command signature). Both drifted silently. The test must drive the
  real writer into the real reader (`tests/test_remind.py::WriterReaderTest` is the shape).
- Tried `[splits("\n")]` in jq to split lines. It is the regex split and cost 230 ms per
  hook event; `split("\n")` is the same value at 50 ms.

## Corrections to earlier notes

- `notes/2026-09-02-audit-and-replan.md` (agent 2 finding 4) says "10 forges = 5 distinct
  names". Re-derived while filing #24: 10 `start` rows carry **6** distinct names.
- `notes/2026-09-02-audit-and-replan.md` (agent 4, gap 4) says the two CANDIDATE verdicts
  produced nothing. That is no longer true: `skillinsight promote --verdict` wrote both
  into notes on 2026-09-02, and `hooks/session-review.sh` now writes a note on every future
  CANDIDATE.
- `notes/2026-09-02-tiers-design.md` shows `commands: ["Bash\n./run_tests.sh"]`. The
  shipped form is the bare `--norm-of` output with no tool prefix (correction appended to
  that note on 2026-09-02).
- `notes/OPEN-THREADS.md` earlier said "#8 PreCompact capture is still unbuilt". It
  landed in c06eb6c; the file's header and Closed section were updated on 2026-09-03.
- The review pasted on 2026-09-02 says "Python 3.14 emits invalid-escape warnings" in two
  test files. On Python 3.9 (CI's floor) nothing is emitted; the two docstrings were made
  raw anyway in 89ca608, and `python3 -W error::SyntaxWarning` over `tests/*.py` exits 0.
- The review says the README is "over a thousand lines". It was 1245; it is 366 since
  a2aa2d4, with the rest under `docs/`.

## Open decisions

- Should the reminder hook prune its per-session claim and stamp tree (`<state>/remind/`)?
  A TTL sweep would re-arm a cooldown mid-session; leaving it grows without bound (#33).
  Needs a choice of policy, not a fix.
- Should `install.sh --rollback` run twice toggle forward again (current, pinned by test as
  observed behaviour) or refuse the second time? The record holds one `previous`.
- Should stage-two automatic forging stay off until a dispatched session can run its own
  routing gate, or should the routing gate be made runnable without `claude` permission
  approval? The block is at the permission layer (OPEN-THREADS, "stage 2").

## Next

1. Run one real, narrow forge under the diet on a genuine recurring dead end, timed, ending
   with `skillforge apply` and `skillforge verdict` in the same turn (#34). Read
   `skills/skill-compounder/SKILL.md` steps 0..6 first; do not raise the round cap.
2. Start the measurement campaign (#30, #37): after a week of ordinary use across several
   repos, run `skillreport`, `skillnote list --scope remind` (derived hit counts), and count
   note read-backs; compare against the 10.5% nudge-to-skill baseline. Do not tune
   `REMIND_MAX`, `REMIND_COOLDOWN`, `CI_EDIT_EVERY` or `CI_PROMPT_COOLDOWN` before that
   data exists.
3. Decide the `remind/` prune policy (#33) and implement it with a test that proves a
   cooldown is not re-armed mid-session.
4. Close the ShellCheck follow-up: 19 findings at warning/style listed in
   `.github/workflows/ci.yml`'s step comment; fix them and raise `--severity` to warning.
5. `hooks/repeat-gate.sh:553`: `sed` dies E2BIG at ~890 KB of hook environment; cap what
   `norm_bash` hands it or feed it via stdin (OPEN-THREADS).
6. #42: rerun `tests/e2e/journey.py` under a genuinely fresh `CLAUDE_CONFIG_DIR` once a
   token can be handed in (`CLAUDE_CODE_OAUTH_TOKEN`), so routing is measured at personal
   scope.
7. #19: the composition half (a forged skill that composes deeper than one level), and the
   "forged skill actually used" half now that `apply`/`verdict` exist.
8. #9 is the old retrospective issue; read it and either close it against #31 or narrow it.

## Watch out for

- `run_tests.sh` globs `tests/test_*.py` non-recursively; `tests/e2e/journey.py` and
  `tests/e2e/README.md` are deliberately outside that glob because the journey spends real
  `claude -p` calls. Never set `SKILL_ROUTING_PROBE=1` casually: it is 72 calls per run,
  216 at `--runs 3`.
- Hooks run in every live session on this machine, including this checkout's scripts via
  symlinks. Never edit a `hooks/` or `bin/` script in place: write a temp file in the same
  directory and `mv` over it. `hooks/session-review.sh` is detached and paid; check `ps`
  before replacing it.
- Every counted claim in `README.md`, `docs/operations.md` and `.claude/CLAUDE.md` is
  re-derived by a test (`tests/test_doctrine_sync.py`, `DerivationCommandTest`, the
  tuning-table test). Adding an env var to any script means adding its prefix to the
  derivation grep in BOTH files and re-running the count; this has gone wrong five times.
- Doctrine sentences are pinned verbatim across `skills/skill-compounder/SKILL.md`,
  `docs/architecture.md`, `.claude/CLAUDE.md` and the installer's `DOCTRINE_TEXT`. Change
  one and `test_doctrine_sync.py` fails until all four match; the anchors
  (`<!-- doctrine: id -->`) must move with their sentences.
- The frontmatter and `## Trigger precision` block of `skills/skill-compounder/SKILL.md`
  are byte-pinned by the routing pin; touching either invalidates it and costs a re-probe.
- The user's `~/.claude/CLAUDE.md` doctrine stanza is now inside the installer's marker
  block, so `./install.sh` rewrites it; a backup of the hand-written version is at
  `~/.claude/CLAUDE.md.bak-skill-compounder-20260902-190156`.
- `.claude/settings.json` in this repo sets `DOC_GATE_NOTES=neither` because this repo's
  `notes/` is a dated log; the shipped default is `doc`.
- Parallel agents editing this tree need disjoint file ownership (the
  `parallel-agents-one-codebase` skill); a whole-suite run while agents are mid-edit
  produces failures that mean nothing, and an agent told to "fix every failure" will chase
  them. Run the suite only on a quiet tree.
- Subagent notifications can arrive several times for one finished agent (stale
  background waiters); a repeat carries nothing new.
