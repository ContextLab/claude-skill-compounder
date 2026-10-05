# Audit work tracker (started 2026-10-04)

The owner said: do all six proposals from `2026-10-04-release-and-audit.md`, in the order
the session thinks best, and keep notes. Base commit for the work: `54340ba` on `main`.
Evidence for every item: `notes/2026-10-04-audit/`.

How it is run: each track is an agent in its own git worktree (the live mod loads from
the main checkout, so half-edited hooks must not sit there). The session merges each
branch into `main`, runs `./run_tests.sh`, `claude plugin validate --strict .` and
`claude plugin test .`, then pushes. Status is updated here after each merge.

## Wave 1 (parallel)

| Track | Proposal | Scope | Status |
|-|-|-|-|
| A | 1. trustworthy capture and guards | non-command failures dropped before the judge; guards match commands only, multi-line anchor; exit-0 shell errors count as failures; no recurrence after a guard refusal; verdicts logged with `ms` | MERGED (a1ddff4), notes in `2026-10-04-track-a-capture-guards.md` |
| B | 3. install and uninstall | curl-able uninstall; default to the newest release tag; `update` moves between tags; Claude Code version check; shadowed `compound` on PATH reported; marketplace route only if a real session shows the hooks load | MERGED (0dd8d4a), notes in `2026-10-04-track-b-install.md`; marketplace NOT shipped (tool-call and stop hooks unproven: the sandbox was not logged in) |
| C | 4. indicators | names instead of counts; totals line; once-per-session ready note; relative times; one vocabulary; pane at 40 columns; CLI text polish | MERGED (a31d48b, merge ba5d77b); renders in `2026-10-04-audit/track-c-renders.md`. README screenshots and demo.gif no longer match and are NOT re-recorded yet |

## Wave 2 (after wave 1 is merged)

| Track | Proposal | Scope | Status |
|-|-|-|-|
| D | 2. general pool | platform and shell condition on a lesson; a general lesson can be strengthened locally or switched off; ship the six drafts (four as guards) | MERGED (df69796, merge 509c35a); notes in `2026-10-04-track-d-general-pool.md` |
| E | 5. pane drill-down | open a lesson from the pane; settling command on Open rows; all-lessons view | MERGED (c2e048a, merge 2ce0262); renders in `2026-10-04-track-e-pane.md`. Mouse clicks, a real desktop session and the docked placement are unverified |
| F | 6. reuse precision | rarity-weighted words; memo for repeated prompts; stemming in `find`; duplicate gate in `add` | MERGED (36c6b93, merge 1e9c8cf); notes in `2026-10-04-track-f-reuse.md`. Known cost: `find --request` 667 ms on the real prompt log (was 120 ms) |
| S | security review of a commit (arrived 2026-10-04 as a background notice; 4 findings, 2 named) | 1. a lesson's `name` is validated as a slug only at `add`/`promote`, not when a lesson file is loaded, and `hooks/render.ts` puts the name (and a project path) into commands it tells the model to run (`add --update --name <name>`, `COMPOUND_PROJECT=<from> ... promote <name>`): a lesson file committed in a repository can carry a hostile name. Confirmed by reading `bin/compound` (SLUG_RE used at 1377 and 1985 only) and `render.ts` 349-401. 2. a slow pattern in a project lesson can use up the 1.5 s guard budget so user guards go unchecked (`check` has `timed_out`/`unchecked`; what the mod does with them is to be read). 3-4. not named in the notice: run a fresh security review to find them. | MERGED (1e355c4, ef2fba9, merge e3e6ba8); notes in `2026-10-04-track-s-security.md`; 8 findings fixed. Third finding, from a second notice: untrusted tool output reaches the LLM judge (lesson poisoning) in `hooks/register.ts` |

## Wave 3 (from the open-issue audit, 2026-10-04)

The owner asked for the open issues to be audited: anything relevant goes on this list,
the rest is closed with a comment. #30, #31, #34 closed (they track the implementation
removed in `88a6c3e`). #19 and #42 stay open, each restated against the rewrite.

| Track | From | Scope | Status |
|-|-|-|-|
| G1 | #19 point 4 | a `use` event when a skill made from a lesson (or any recorded skill) is invoked, with its notice on the band and its count in `status` and the pane | MERGED (75e55e0, merge 2ae8d96); notes in `2026-10-04-track-g-skills.md` |
| G2 | #19 point 1 | notice a repeated request (the same procedure asked for several times, from the prompt log) and propose making it a skill | MERGED (75e55e0, merge 2ae8d96); notes in `2026-10-04-track-g-skills.md` |
| G3 | #19 point 3 | a skill in the shipped pool that composes other skills. The owner chose (2026-10-04): BOTH `finish-task` (review the change, run every check, update docs and notes, commit; calls compound:learn when something failed and was fixed) and `verify-assumptions-first` (check base assumptions with real calls before a large effort, then an MVP, then the full build; calls compound:reuse first) | MERGED (75e55e0, merge 2ae8d96); notes in `2026-10-04-track-g-skills.md` |
| H | #30 | after some weeks of ordinary use, a sweep of the log: capture to lesson / skip / unsettled rates, guard refusals corrected vs re-sent, recall precision, reuse relevance. A `compound` report that prints them | MERGED (bb49a91, merge 21552d4): `compound report`; a `retry` event after a guard refusal. Notes in `2026-10-04-track-h-report.md`. The sweep itself needs weeks of data |
| I | #42 | a credential for sessions in a throwaway `CLAUDE_CONFIG_DIR` (`claude setup-token`, `CLAUDE_CODE_OAUTH_TOKEN`), then prove the marketplace install route and run the journeys fully isolated. ONLY THE OWNER can create the token | blocked on the owner |

## Not to do without the owner

- Any text that states policy for the project (what belongs in the general pool, in
  CONTRIBUTING or README): draft it and ask.
- Rewriting the owner's own user lessons in `~/.claude/compound/lessons`.
- Running `install`, `uninstall` or `update` against the real `~/.claude`.

## Log

- 2026-10-04: tracker written, wave 1 dispatched.
- 2026-10-04: a background security review of a commit reported 4 findings; track S added.
- 2026-10-04: tracks A and B merged, all checks green; released v0.4.1 (the installer on main
  installs the newest tag, and v0.4.0's update fails on a tag). Public install, update and
  piped uninstall run in a sandbox against v0.4.1.
- 2026-10-04: a second security notice: untrusted tool output reaches the LLM judge
  (persistent lesson poisoning) in `hooks/register.ts`. Given to track S.
- 2026-10-04: wave 2 tracks D, F, S dispatched on base v0.4.1. C still running; E waits on C.
- Left by track A for the owner: three `compound add --update --match` commands for the
  owner's guards (in the track A notes), and an unanchored pattern still hits
  `grep -n '; git commit' file`.
- 2026-10-04: track C merged (conflicts with A in view.ts, register.ts imports, design.md
  command table; the `judge` event got its display word `judged`). All checks green: 13
  test files, 171 plugin tests. Track E dispatched. Running now: D, E, F. Held: S.
- Still to do after the tracks: re-record README screenshots and demo.gif (dev/demo.sh,
  dev/ui-check.sh); decide with the owner on the stand-in `claude` executables in track
  B's version tests (no-mocks rule); final release.
- 2026-10-04: a third security notice, after the track C merge: prompt injection through
  unvalidated persisted state reaching the model's context, in `hooks/register.ts`. No
  detail given. For track S: trace every value read back from `$.state`, the claims, the
  event log and the store that ends up in text added to a prompt or a stop message.
- 2026-10-04: track D merged, all checks green (14 test files, 173 plugin tests).
  The merge was done in the main checkout and its conflict markers broke the live mod for
  a few minutes (guard checks failed with SyntaxError). Recorded as project lesson
  `merge-in-a-scratch-worktree`: remaining merges are done in a scratch worktree and
  fast-forwarded.
- 2026-10-04: open issues audited; wave 3 added above. Track S dispatched. Running: E, F, S.
- 2026-10-04: track E merged in a scratch worktree and fast-forwarded (main 70f4f84). All
  checks green: 14 test files, 191 plugin tests, tsc clean.
- 2026-10-04: the owner chose to remove the stand-in `claude` executables from track B's
  version tests. Done: the check is tested against the real Claude Code only; the
  below-minimum branch has no test.
- 2026-10-04: a fourth security notice, "terminal-escape-injection in hooks/view.ts", sent
  to the running track S agent, with the instruction to merge origin/main (track E's lesson
  view) before its final commit.
- Running: F, S. Then: G1, G2, G3 (one track), H (the report), re-record README media,
  final release. Blocked on the owner: I (the token).
- 2026-10-04: tracks F and S merged in a scratch worktree and fast-forwarded (main 5376e31).
  All checks green: 17 test files, 217 plugin tests, tsc clean. Merge fixes: tracks E and S
  each added a `clean` function to view.ts (E's is now `cleanLine`); find's text row is
  `, matched 2 of 3 words (a, b)`.
- Pre-call `check --guards` is now about 60 ms on this machine (guards run in a child
  process); README still says 45 ms: fix in the final docs pass.
- OWNER DECISIONS left by track S (safe defaults are in): (1) a general guard yields to a
  user guard only, not to a project guard; (2) a project lesson with the name of a user or
  general one is `shadowed` and not in force; (3) a lesson directory whose name is not a
  slug is unused; (4) `promote --to general --yes` refuses text that looks like a
  credential, with no override; (5) open: `compound log` accepts a forged `learn`/`skip`;
  a Bash command that starts with `compound` skips the guards.
- 2026-10-04: tracks G (G1, G2, G3) and H dispatched on base after 5376e31.
- After G and H: re-record README media, final docs pass (latency, screenshots), release.
- 2026-10-04: track H merged (no conflicts), all checks green: 18 test files, 224 plugin
  tests, tsc clean. No real session has written a `retry` event yet.
- FOR THE OWNER: at 18:42Z session 4e5c26de (not this session; a track agent or one of its
  test sessions, answering the mod's "owes a stronger lesson" stop) ran `add --update` on
  the owner's REAL user lesson `zsh-nomatch-glob`, adding `match: ["--(include|exclude)=\\*"]`.
  The agents were told not to write to the real store. The pattern is the one the quality
  audit proposed, and it has refused 2 calls since. To undo:
  `compound add --update --name zsh-nomatch-glob --no-match`.
- What the first report shows that needs work: `agent-worktree-check-base` was recalled 9
  times, all for one harness refusal (track H made that wording a refusal); two parallel
  agents failing 1 s apart made `zsh-nomatch-glob` ineffective; one lesson is 7 of 19
  reuse offers.
- Running: G. Then media, docs pass, release.
- 2026-10-04: track G merged, all checks green: 19 test files, 242 plugin tests, tsc clean
  (main 2ae8d96). The pool now ships 4 skills (learn, reuse, finish-task,
  verify-assumptions-first) and 6 lessons. Known: haiku did not route to
  verify-assumptions-first (0 of 1; sonnet 4 of 4); `measure_reuse.py` still offers
  `brew-doctor-exit` wrongly for the LaTeX prompt.
- 2026-10-04: track M dispatched: docs pass (README Cost table re-measured, guide examples
  regenerated from real output) and re-recorded README media. Then the release (v0.5.0).
- 2026-10-04: track M merged (b10c312, fast-forward): documents checked against the code,
  every example regenerated (`dev/guide_examples.py`), README media re-recorded. All checks
  green: 19 test files, 242 plugin tests, tsc clean. Released as v0.5.0.
- Found by track M while recording, NOT fixed: a recalled failure drops an earlier held
  one (`hooks/register.ts` 1168-1169), which cost a capture in one take; the fix judge
  rejected "module missing" in 2 of 4 takes, which is the README's own example; the band
  went blank for about 3 s while a failure was still held; the demo pane shows a
  `claude code` warning because the demo world has no `claude` on PATH.
- STILL OPEN after v0.5.0: the four items above; the owner decisions from track S; the
  guard an agent added to the owner's `zsh-nomatch-glob`; #42 (the token, then the
  marketplace route); #19's composition is shipped but haiku did not route to
  `verify-assumptions-first`; `find --request` at 500-690 ms; parallel agents can make a
  lesson ineffective; `measure_reuse.py` offers `brew-doctor-exit` for the LaTeX prompt;
  the effectiveness sweep once there are weeks of data (`compound report`).
- 2026-10-04: the owner approved the guard on `zsh-nomatch-glob`; `--shell zsh` added to it.
- 2026-10-04: a bug-fix agent is running on base 753b8e0: the dropped held failure, the fix
  judge rejecting the README's example, the blank band. Notes will be `2026-10-05-learn-loop-fixes.md`.
- 2026-10-04: the open decisions were settled with codex: `2026-10-04-decisions.md`. To
  implement after the bug-fix agent merges (track J): D1, D5, D6, D7, D8, the promote scan,
  the settlement scope, recurrence by level and path. Then release v0.5.1.
- 2026-10-04: learn-loop fixes merged (b620d5f, merge 40bd569); 19 test files, 260 plugin
  tests, tsc clean. Track J (the decisions) dispatched on that base.
- 2026-10-04: a fifth security notice (titles only): "argument-injection /
  command-execution in bin/compound" and "sensitive-data-to-log in bin/compound". Sent to
  the running track J agent to confirm with a failing test and fix.
- 2026-10-04: track J merged as one commit, 462761d (notes in `2026-10-05-track-j-decisions.md`).
  The first push was refused by GitHub push protection: the redaction tests held
  key-shaped literals (the AWS documentation's example key). The fixtures are now built
  from halves and the merge was redone as a fresh commit on origin/main, so the refused
  commit never reached GitHub. All checks green on main: 22 test files, 280 plugin tests,
  tsc clean.
- The agent for track J added three rules to `.claude/CLAUDE.md` (the exemption allowlist,
  where a recall is counted, what `compound log` takes). They state what the code does;
  the owner has not read them yet.
- 2026-10-04: a seventh security notice on that commit (5 findings, 3 named):
  allowlist-resolution-differential in hooks/register.ts, integrity-check-bypass in
  bin/compound, path-traversal-via-symlink in bin/compound. Track S2 dispatched on 462761d
  to confirm and fix them. v0.5.1 is held until it merges.
- After track J, on the owner's real store (nothing was changed): four user lessons show as
  ineffective from today's agent sessions (agent-worktree-check-base, chain-commit-with-and,
  heredoc-ends-and-chain, zsh-nomatch-glob), and `echo =====` is now refused by both
  `zsh-equals-word` and the shipped `zsh-equals-not-found`.
- 2026-10-04: the owner ran (through this session) `compound disable` for
  zsh-equals-not-found, zsh-no-matches-found and macos-gnu-only-commands: their own three
  guards now refuse alone.
- 2026-10-04: track S2 merged (1c9f0ad, merge 5f471a1; notes in
  `2026-10-05-track-s2-security.md`). The bare name `compound` is never exempt: only the
  exact absolute path the mod runs. A project skill can no longer take a user lesson's
  name; links out of a project are refused; `promote --yes` to a non-default destination
  needs `--upstream DEST`. The two findings the review did not name were not identified.
- 2026-10-04: the live log held one error: a session whose PATH had no `sh` lost its claims
  ("nothing is refused in this session"). The mod now runs `/bin/sh` by its path.
- Released v0.5.1. All checks green: 23 test files, 282 plugin tests, tsc clean.
- OPEN after v0.5.1: `compound log` keeps a caller-supplied `ineffective`; the CLI's own
  printed commands use the bare name `compound`; whether a project `settings.json` `env`
  block can set `COMPOUND_HOME`/`COMPOUND_NOW` for the mod is unverified; `compound report`
  counts recalls by name; a bare retry writes no event; bug 1 of the learn-loop fixes was
  verified with mounted hooks only; #42 (the token, then the marketplace route); haiku and
  `verify-assumptions-first`; `find --request` at 500-690 ms; Linux, bash, WSL and Windows
  are simulated only; the three rules an agent added to `.claude/CLAUDE.md` await the
  owner's reading; four of the owner's lessons show as ineffective from today's sessions.
