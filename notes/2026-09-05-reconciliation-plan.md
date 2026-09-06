# 2026-09-05: reconciliation against the maintainer's requests, and the plan

Inputs, all from this session's scratchpad and re-derivable: a 60-row requirements ledger
built from `surfer show` over every prompt in this project (38 verified live, 14 partial,
4 implemented-unverified, 3 missing, 1 declined with a measurement), and a census of use,
mechanisms, complexity, level C and release state (`census-2026-09-05.md`). Quotes below
are the maintainer's words.

## What stands

- Scenario 1, the mission ("automatically remind claude ... about the exact text of
  relevant user requests"): five moments, into subagents, verified live twice against the
  installed package; journey 17 of 17 on the final tree.
- Scenario 2, the forced write-down ("force claude to write it down ... before
  continuing"): hardened by three live red teams to its final shape; the loop across
  sessions verified 5 of 5, including a session in an unrelated project finding an attached
  script through the global note and running it.
- Levels A and B placement, principle i (the mission keeps no copy of the prompts;
  `promote` moves), principle ii (everything fires from hooks).
- The review's P0 (CI green, 5 of 5), P1 (tracker reconciled), P2 (one repeatable E2E),
  review opt-in, `doctor --json`, supported versions, the docs split, the screencast.

## What does not, in the maintainer's words

|row|quote|state|
|-|-|-|
|R7|"the 'writing it down' piece is what i've been calling a 'skill' -- a combination of notes and code that is searchable, findable as a tool in the appropriate future contexts, and callable by agents"|Met in a different shape. A note is a CLAUDE.md line, a reminder is injected text, an attachment is a path in prose. The only thing Claude Code ROUTES on is a forged skill, and the forge is hours. There is no cheap path from a lesson to a SKILL.md.|
|R6|"including the relevant contextual information and any associated code or scripts"|3 of 71 note rows carry an attachment. The hook's statement and deny name `skillnote add --lesson` and never `--attach`, even when the fix was a script.|
|R14|"i'm a little surprised that the skills take SO long to build"|Every forge in the ledger ran 0.6 to 86 hours against a 30-minute target; both forges this session failed at the cap after about 3 hours each.|
|R9/R44|level C: "automatically package the skill, fork the repo, push to the fork, then submit a pull request"|Code exists, has never run: 0 `contrib` rows, 0 PRs ever. `recon` on this checkout answers ALREADY UPSTREAM because this IS the upstream, so exercising it needs a second repository.|
|R31|"resist adding any new gate or subsystem until ... an existing component is retired or simplified to make room"|Violated: core scripts +6248 lines (+34%) in two days, nothing retired, no `WHY-ARCHIVED.md` in the repo.|
|R32|"explicitly define the product as: Automatic capture and surfacing; human-approved promotion; assisted skill construction"|Not stated anywhere.|
|R20|"Protect main from merging when either OS job is red"|Branch not protected (404).|
|R24|"pin the one-line installer to releases"|`install.sh` follows `main`; 56 commits unreleased since v0.3.1; the upgrade/rollback test runs over synthetic tags only.|
|R55|"notification that the new skill is now available"|Only the status line during a forge; nothing tells the session a skill it can call now exists.|
|R59|"tested the resulting skills and examined quality of the output"|5 of 12 seed skills judged (3 correct, 2 partial, fixed); 7 not yet. 7 of 12 have zero genuine use outside this repository; `contribute-skill` zero anywhere.|
|R42|"never rely on remembering alone ... triggered automatically at the appropriate times"|The prompt-arm nudge converts 9.6% over all sessions but 63.2% over the 19 human-driven ones; the two hook thresholds are still unvalidated.|

The central finding: the tier model is note, reminder, forge. The design is note, reminder,
lightweight skill (markdown plus scripts, routable, callable, at level A or B), with the
builder/red-team forge as the hardening step a skill gets only when it goes upstream (C).

## The plan

Waves are dependency-ordered. Each has an acceptance test that is a real run, not a unit.

**Wave 1, the missing tier (starts now).**
- `skillnote skill <note id> --name <slug> [--scope project|global]`: from a note (its line,
  its attachments, its lesson signature) write `<scope>/skills/<slug>/SKILL.md` with a
  double-quoted description in the `Use when ... Do NOT use for ...` shape, the note text as
  the body, attached scripts moved beside it and referenced by relative path (as shipped
  on 2026-09-05 they are COPIED into `<slug>/scripts/`, the lesson directory keeps its
  copy, and the SKILL.md says so; see `notes/2026-09-06-review-response-session.md`), a `skill`
  ledger row carrying `from`/`candidate`, and a printed line saying the skill is callable
  now (R55). No forge. Gate A from `skill-authoring` (frontmatter parses, description under
  the cap) runs as part of the command. Accept: a lesson from a real session becomes a skill
  that a fresh `claude -p` session invokes through the Skill tool for its must-fire prompt.
- The lesson statement and deny say `--attach <path>` when the recovery wrote or ran a
  script (the recover row knows the command), and name `skillnote skill` as the next step
  after the note. Accept: a real session's lesson carries the script.
- Docs: the tier table gains the fourth row; `skills/skill-compounder/SKILL.md`'s tier rule
  says when a lightweight skill is enough and when a forge is owed (level C only).

**Wave 2, judge the rest of the pool (parallel with wave 1).** Drive the remaining seven
seed skills with real tasks and planted defects the way the first five were; fix sentences;
for each skill with zero genuine use outside this repository, put the neutral "keep, fix, or
retire?" question to a fresh agent with the census row. Accept: a verdict per skill with a
quoted reason; retirements only with concurrence and a `WHY-ARCHIVED.md`.

**Wave 3, retire to make room (needs the maintainer's yes per item).** Candidates and the
measurement each rests on: the repeat REFUSAL arm (`REPEAT_GATE_REFUSE`; never fired in its
life, every live signature exempt); the paid session review's stage 2 (structurally cannot
finish; keep stage 1 opt-in); seed skills wave 2 votes to archive. NOT the prompt-arm nudge:
63% on human sessions says it earns its place; narrow its trigger instead of removing it.
Each retirement is `mv` to an archive with `WHY-ARCHIVED.md`, never `rm -rf`.

**Wave 4, level C for real (needs a second repository).** Run `skillcontrib propose` end
to end against a fork of this repository under the maintainer's account, from a checkout
whose origin is the fork: package, push, open the PR, then close it. Accept: one `contrib`
row and one PR, both real. Creating the fork is an outward action; it waits for a yes.

**Wave 5, release (after 1 to 4).** State the product sentence (R32) in the README; tag
v0.4.0; make the headline one-liner pin the latest tag (R24) with `main` the explicit
opt-in; run the upgrade/rollback test over the two real tags; protect `main` on both CI
jobs (R20, needs the maintainer or a token with admin scope); re-record the screencast so
the headline is the cheap path (lesson, note with script, `skillnote skill`, the skill
invoked) and the forge is the coda.

**Wave 6, measure (weeks, not this session).** `scripts/reminder_conversion.py` and
`skillreport` across several repositories; the two hook thresholds and the mission's four
constants move only on that data (#30).

**Needs the maintainer:** a token for the fresh-config journey (#42: `claude setup-token`);
a yes on each wave-3 retirement; a yes to create the fork for wave 4; a yes on the tag and
the installer pin; branch protection.
