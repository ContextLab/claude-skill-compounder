# Open threads

Written so nothing here depends on a session remembering it. Delete an entry when it is
genuinely closed, not when it is merely in flight.

## In flight right now

Agents hold these files; a suite run touching them proves nothing until they report.
A red test in this list is not evidence of a defect.

- (landed) status-line honesty: a running forge stops at 99% with a reserved last cell
  naming its reason, an overrun renders `14/12 over` and reaches the ledger, and a forge
  idle past `SKILLFORGE_IDLE_SECS` (2700s, measured from 33 real intervals) dims without
  being reaped.
- `skills/claim-provenance/**`, `tests/test_seed_claim_provenance.py` — a forge, running
  the full builder plus cold red-team loop. **`tests/test_doctrine_sync.py` fails while
  this runs, correctly:** the builder has written `skills/claim-provenance/SKILL.md` and
  the README does not mention it. Do not fix that by adding a README row and do not relax
  the assertion — the forge may conclude this belongs inside an existing skill instead, in
  which case the directory goes away and the failure resolves itself. The guard is doing
  what it was built for.
- `skills/skill-authoring/**`, `tests/test_seed_authoring.py` — closing mutation gaps a
  reviewer found and left open.
- `hooks/**`, `bin/skillinsight` — making the compound-improvement trigger deterministic,
  so the record is written whether or not a session reads the reminder.

## Landed since this file was written

- Status-line honesty and the overrun record, above.

- `docs/CLAUDE-CODE-BEHAVIOR.md` — Claude Code platform behaviour split out of
  `docs/DESIGN.md`, which keeps this package's own design rationale. Guarded by
  `tests/test_docs_split.py`, proven by breaking it five ways.

## In flight — commit and push when both are green

Two fixes dispatched for items previously left open in this file. When both report and
`./run_tests.sh` is green on the resulting tree, commit and push. Do not commit a tree
either agent is still editing, and do not read a suite run started before they finish as a
verdict.

- **The concurrent `done` race.** Two simultaneous `skillforge done` calls both wrote an
  outcome row, 40/40 trials, inflating the only evidence anyone has about whether forging
  pays off. Previously left unfixed for a good reason: a lock held across a write can leave
  a forge nobody can close, which is worse. The brief points at the `ln`-claim pattern the
  slot allocator already uses -- atomic, nothing held, loser exits -- and requires the
  design to state what happens if a process dies at each step.
- **Personal-scope skill loading.** The frontmatter findings in
  `docs/CLAUDE-CODE-BEHAVIOR.md` are measured for project and `--plugin-dir` scope only;
  `~/.claude/skills/` was never tested because `CLAUDE_CONFIG_DIR` broke auth. If it cannot
  be isolated safely the answer is "could not determine" and the file's existing
  "not measured" wording stays exactly as it is.

## Known tree-state dependency — do not "fix" it

`tests/test_seed_claim_provenance.py::test_the_measured_sweep_figures_are_re_derived_not_restated`
runs the skill's own diff sweep with `git diff HEAD -U0` against
`skills/ai-tell-audit/SKILL.md`, and the skill states that sweep matched **0** lines. That
is true of a committed tree and false of a dirty one: while that file has uncommitted
changes the sweep matches them and the test fails.

The `0` is correct. If you find this red, check whether `skills/ai-tell-audit/SKILL.md` is
modified before changing any number — committing resolves it. The whole-file figure beside
it (currently 121) is a different kind of claim and does move permanently when that file
grows.

## Next, in order

1. **Commit everything as one tree** the moment the `claim-provenance` forge closes and no
   agent holds a file. It must go together: `README.md`, `skills/skill-compounder/SKILL.md`
   and `tests/test_doctrine_sync.py` all reference `skill-authoring`, and the doctrine test
   fails on a tree where a documented skill does not ship.
2. **Reword `204acb0`** by rebase — its message claims "544 tests pass" for a tree that
   fails one. Unpushed, so history is still clean to fix.
3. **Rigorous end-to-end testing, by subagents, with real calls.** Not more unit tests:
   install the package into a throwaway config directory, run real `claude -p` sessions
   against it, watch the state files and the ledger and the weekly queue while they run,
   and evaluate the outputs critically rather than checking exit codes. The gap being
   closed: every test in this repo exercises a script through `subprocess`, and none
   exercises the package the way a user does — installed, with Claude Code actually
   loading the skills and firing the hooks. Never against the real `~/.claude`.

## Blocked on a free working tree

- **`204acb0` has a false commit message.** It says "544 tests pass; plugin validate
  --strict clean". Verified by checking out that tree: 120 tests, 1 failure
  (`2354 != 2468`). It is UNPUSHED, so the fix is a rebase reword. A rebase rewrites the
  working tree, so it must wait until no agent is mid-edit. This is the last item before
  the branch is honest.
- **Everything commits together.** `README.md`, `skills/skill-compounder/SKILL.md` and
  `tests/test_doctrine_sync.py` all reference `skill-authoring`. A commit without
  `skills/skill-authoring/` documents a skill that does not ship and fails its own tests
  on a fresh clone.

## Prose written and verified, waiting to be applied

- `docs/DESIGN.md` — the status-line agent owes replacement prose for the percentage and
  overrun rendering.
- `skills/skill-compounder/SKILL.md` — the budget-overrun rule shrinks or disappears once
  the renderer stops clamping to 100%. Current text is a documented workaround for a
  display defect.

## Known limits, deliberately open

- **`tests/test_doctrine_sync.py` has a measured ceiling.** A cold reviewer defeated the
  verbatim-pinning guards by keeping each pinned sentence and repudiating it in the next
  clause, exit 0. Recorded in the docstring as measured fact. The guard catches drift,
  deletion, softening and truncation; it does not catch repudiation. Do not report it as
  catching more than that.
- **Personal-scope skill loading is unmeasured.** The frontmatter finding covers project
  and `--plugin-dir` plugin scope. Isolating `~/.claude/skills` needs `CLAUDE_CONFIG_DIR`,
  which broke auth. Debug output shows one loader for all scopes, so it probably carries.
  Probably is not measured.
- **Both hook thresholds are still unvalidated.** `CI_EDIT_EVERY=12` and
  `CI_PROMPT_COOLDOWN=1200` were picked by judgement. `bin/skillreport` is the instrument
  that would settle them and needs real usage across several repos first.

## The failure that produced this file

A checkpoint hook fired at edits 12, 24 and 36 in one session and was disregarded every
time, because it asks whether "the procedure you are working through right now" is
recurring — a per-instance question, asked while absorbed in a single fix. Nine defects of
one kind were fixed in that session without the pattern being noticed. The lesson is not
"read the reminders": it is that a mechanism whose output depends on someone noticing will
fail exactly when it is most needed. Prefer mechanisms that produce their record whether
or not anyone reads anything.
