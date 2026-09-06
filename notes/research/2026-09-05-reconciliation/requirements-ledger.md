# Requirements ledger — claude-skill-compounder

Built 2026-09-05 from the maintainer's own prompts via `surfer`, plus `gh issue view 43` and
`gh issue view 19`. Every status was checked against the working tree at `603e61a`
(branch `resume/after-v0.3.1`) and against the live state under
`~/.claude/skill-compounder/`, not against `notes/`. Read-only: no repo file was edited.

Status vocabulary: **live** = implemented-and-live-verified (a command run here shows it
working on real data); **unver** = implemented-unverified (code exists, no live record);
**partial**; **missing**; **declined** = declined-with-reason.

## The ledger

|id|verbatim quote (prompt)|level|status|evidence (run here unless noted)|
|-|-|-|-|-|
|R1|"automatically remind claude (main thread AND/OR subagents) about the exact text of relevant user requests" (f58c372b:3)|n/a|live|`jq -r .moment .../mission/hits.jsonl \| sort \| uniq -c` → 380 rows: dispatch 136, subagent 135, periodic 69, completion 21, ambiguity 10, resume 9|
|R2|"when ambiguities arise, after context compaction, periodically during extended work sessions, before engaging in an expensive … task …, and before marking a task as complete" (f58c372b:3)|n/a|live|`grep -n 'moment="' hooks/mission.sh` → 7 lines (init + 6 assignments); `skillforge doctor --json` mission row: "380 delivery/deliveries … across 5 of the five moments"|
|R3|"(main thread AND/OR subagents)" (f58c372b:3)|n/a|live|`settings.json` wires `hooks/mission.sh` on SessionStart, SubagentStart, PreToolUse, UserPromptSubmit, Stop; 135 `subagent` rows in hits.jsonl|
|R4|"we can also search over those prompts to find things relevant to the current scenario" (f58c372b:3)|B|declined|`docs/DESIGN.md:1705` "## Level B search stays a command a session runs, and not a mechanism"; measurement in `notes/research/level-b-search-measurement.md`|
|R5|"after a failed attempt at doing something (anything!), and then figuring it out, force claude to write it down … before continuing" (f58c372b:3)|n/a|live|repeat store `repeats/index.jsonl`: 916 rows — 510 `fail`, 405 `recover`, 1 `dismiss`. The lesson statement fired at me during this very session (signature `c3195642170x339-e588438501x44`). `skillrepeat list` shows GATE=`refuses` on 2 signatures|
|R6|"including the relevant contextual information and any associated code or scripts" (f58c372b:3)|n/a|partial|`skillnote add --attach` exists (`skillnote --help`); live use is thin: 3 of 71 ledger `note` rows carry attachments, one attachment dir on disk (`~/.claude/lessons/n3725829701x412`)|
|R7|"the 'writing it down' piece is what i've been calling a 'skill' -- a combination of notes and code that is searchable, findable as a tool in the appropriate future contexts, and callable by agents" (f58c372b:3)|n/a|partial (different form)|**Met in a different shape.** The one artifact the vision describes is split across three tiers. A note is a dated line in `.claude/CLAUDE.md` (searchable, read passively — not a tool, not callable). A reminder is an injected sentence from `hooks/remind.sh` (findable in context — still not callable). `--attach` gives a *file path in prose*, not an invocable entry point. Only the forge tier produces something "findable as a tool … callable by agents", and that is the expensive path R14 is about. 10 of 71 note rows carry `lesson_sig`|
|R8|"these affect BOTH of the above (where to search for recent prompts AND where skills 'go' when they are created)" (f58c372b:3)|A/B/C|partial|Placement half is live: `skillnote where --scope project` → `/Users/jmanning/claude-skill-compounder/.claude/CLAUDE.md`, `--scope global` → `/Users/jmanning/.claude/CLAUDE.md`; reminders scope project-then-global. Search half is not built at any level (R4)|
|R9|"submitting new skills should be automated (i.e., automatically package the skill, fork the repo, push to the fork, then submit a pull request to the upstream repo)" (f0feae4c:2 #3; restated f58c372b:3 level C)|C|unver|`bin/skillcontrib:1040` `propose) cmd_propose "$@"`. Never exercised: `jq -c 'select(.event=="contrib")' ledger.jsonl \| wc -l` → 0; `gh pr list --state all` returns one PR (#7, by jeremymanning, MERGED), none from `skillcontrib`|
|R10|"always maintain a single source of truth" (f58c372b:3, principle i)|n/a|live|`hooks/mission.sh` keeps no copy of prompts — `skillforge doctor` surfer row reads history-surfer's store ("88 prompt(s) recorded for this project"); doctrine mirrors are generated from `DOCTRINE_TEXT` and pinned by `tests/test_doctrine_sync.py`|
|R11|"`skillnote promote <id> --to global` **moves** a project lesson to the user level … never a copy (principle i)" (issue #43 body)|A→B|unver|`skillnote promote` is in `skillnote --help`; `grep -c 'promoted\|tombstone' ledger.jsonl` → 0. No promotion has ever run|
|R12|"reminders are triggered *automatically* (WITHOUT requiring an agent to specifically invoke them)" (f58c372b:3, principle ii)|n/a|live|`skillforge doctor` settings row: "20/20 hook entries wired"; funnel block: "447 logged delivery(ies) across 12 delivered lineage(s)"|
|R13|"don't forget to also update ALL documentation" (f58c372b:3)|n/a|live|`wc -l README.md docs/*.md` → README 460 lines + 8 docs; `tests/test_docs_split.py` asserts no claim lives in two files and every relative link resolves|
|R14|"i'm a little surprised that the skills take SO long to build … skills can be relatively simple and narrowly scoped, as long as they are useful" (dae248bd:1)|n/a|partial|Diet landed — `skills/skill-compounder/SKILL.md:98` "Two dispatched agents, two rounds. A narrow skill should close in **under 30 minutes**". Target never met: forge durations from the ledger are 0.60, 0.95, 0.96, 1.75, 1.79, 3.11, 3.45, 5.36, 5.81, 6.47, 9.70 and 86.40 hours. The three most recent all ended in `fail`|
|R15|"compounding knowledge can also be as simple as making a note in CLAUDE.md (the local or global version), or building a searchable reminder document that gets automatically injected into context at the appropriate times" (dae248bd:1)|A/B|live|`skillnote add` / `add --remind`; 71 `note` rows in the ledger; `hooks/remind.sh` wired on UserPromptSubmit and PreToolUse in `settings.json`|
|R16|"main is red in CI. … Restore trustworthy build status" (dae248bd:2, P0)|n/a|live|`gh run list --branch main --limit 3` → `success` on 603e61a, 74b431a, cc2051b|
|R17|"Add ShellCheck to CI with narrow, explained suppressions" (dae248bd:2, P0.6)|n/a|live|`.github/workflows/ci.yml:113` `shellcheck:` job on both runners, `--severity=warning`, `.shellcheckrc` disables listed with reasons|
|R18|"Remove fixed-commit/shallow-history assumptions from tests" (dae248bd:2, P0.3)|n/a|live|`.github/workflows/ci.yml:29` `fetch-depth: 0`|
|R19|"Fix the apply-gate ARG_MAX behavior" (dae248bd:2, P0.2)|n/a|live|`hooks/apply-gate.sh:575` `jq -n --rawfile r "$TMP/reason.txt"` — the reason travels by file, not argv|
|R20|"Protect main from merging when either OS job is red" (dae248bd:2, P0.7)|n/a|**missing**|`gh api repos/ContextLab/claude-skill-compounder/branches/main/protection` → `{"message":"Branch not protected", "status":"404"}`|
|R21|"Close completed #20–#29 issues where acceptance is met … Convert #31 into a concise status table" (dae248bd:2, P1)|n/a|live|`gh issue list --state open` → 5 open: #42, #34, #31, #30, #19|
|R22|"Build one canonical E2E harness … using a throwaway Claude config. It should retain artifacts and produce a readable report" (dae248bd:2, P2)|n/a|partial|`tests/e2e/journey.py` + `docs/e2e.md` (313 lines) exist and describe `<out>/REPORT.md`. No REPORT.md artifact is on this machine (`find /private/tmp -name 'REPORT.md' -path '*journey*'` → nothing); the 17/17 result is recorded only in `notes/2026-09-04-finish-and-install-session.md:180`|
|R23|"Tag a release" (dae248bd:2, P3)|n/a|live|`gh release list` → v0.3.1 (2026-09-03, latest), v0.3.0|
|R24|"Pin the one-line installer to releases" (dae248bd:2, P3)|n/a|partial|`install.sh:35` `REF="${SKILL_COMPOUNDER_REF:-main}"` — the default still follows `main`, and `README.md:98`'s headline one-liner uses `/main/install.sh`. A pinned form is documented one line below (`README.md:104`, `v0.3.1`). The automatic `git pull --ff-only` the review objected to is gone (`install.sh:308` comment)|
|R25|"Make paid/networked review opt-in during the alpha/beta period" (dae248bd:2, P3/§7)|n/a|live|`skillforge doctor --json` review row: "review: disabled (opt in with SKILL_COMPOUNDER_REVIEW=1 …)"|
|R26|"Add skillforge doctor --json" (dae248bd:2, P3)|n/a|live|`./bin/skillforge doctor --json` returns 11 checks, all PASS|
|R27|"Add a five-minute quickstart around notes and reminders, not forging" (dae248bd:2, P3)|n/a|live|`README.md:150` "### Five-minute quickstart", opening "Nothing has to be forged for any of this to pay for itself", then `skillnote add` and `skillnote add --remind`|
|R28|"State supported Claude Code, Bash, jq, Python, macOS, and Linux versions" (dae248bd:2, P3)|n/a|unver|`README.md:226` "### Supported versions"; contents not audited against the machine|
|R29|"Test upgrade and rollback between two tagged versions" (dae248bd:2, P3)|n/a|live|`tests/test_install_sh.py:187` `test_pinned_install_then_update_then_rollback_and_back` drives `--ref v0.1` → `--update --ref v0.2` → `--rollback` → back. Different from the words in one way: the two tags are built in a synthetic local repo, not the real `v0.3.0`/`v0.3.1`|
|R30|"For several weeks, measure across several real repositories" (dae248bd:2, P4)|n/a|partial|Instrument exists and counts (`skillreport` FUNNEL: 447 deliveries / 12 lineages). Population does not: ledger rows by project — 173 this repo, 26 hypertools, 20 `/private/tmp/dgc-gate`, 11 cdl-linux, the rest session scratchpads|
|R31|"I would resist adding any new gate or subsystem until: CI is green, one complete end-to-end scenario is repeatable, usage is measured across several repositories, and an existing component is retired or simplified" (dae248bd:2, §6)|n/a|**missing**|Since the review (2026-09-03) a whole new subsystem was added — `hooks/mission.sh` on five events — plus the lesson-gate refusal in `hooks/repeat-gate.sh`. Nothing was retired: `find . -name WHY-ARCHIVED.md` inside the repo returns nothing (the two that exist are quarantined *forge outputs* under `~/.claude/skill-compounder/quarantine/`, not retired components)|
|R32|"explicitly define the product as: > Automatic capture and surfacing; human-approved promotion; assisted skill construction" (dae248bd:2, §4)|n/a|**missing**|`grep -n 'human-approved promotion\|assisted skill construction\|Automatic capture' README.md docs/*.md` → no match|
|R33|"assign stable IDs to candidates, notes, reminders, skills, and delivery events so promotion can be traced" (dae248bd:2, §5)|n/a|live|`skillreport` FUNNEL block, "counted joins on the lineage id — no estimate anywhere in this block", 12 lineages with DELIVERED/ACTED ON/OUTCOME columns|
|R34|"Split the documentation into: README … docs/architecture.md … operations.md … measurement.md … development.md" (dae248bd:2, §8)|n/a|live|`ls docs/` → architecture, operations, measurement, development, DESIGN, CLAUDE-CODE-BEHAVIOR, e2e, releasing; README down to 460 lines|
|R35|"bin/skillreport:57 describes edit counters as integers, while the implementation correctly treats them as unary x tallies" (dae248bd:2, §9)|n/a|live|`sed -n '55,60p' bin/skillreport` → "a unary tally, one 'x' byte per edit"|
|R36|"Python 3.14 emits invalid-escape warnings in test_insights.py and test_precompact.py" (dae248bd:2, §9)|n/a|live|`python3 -W error::SyntaxWarning` compiling every `tests/*.py` → no output, no failure|
|R37|"GitHub Actions warns that the selected action versions target deprecated Node 20 runtimes" (dae248bd:2, §9)|n/a|live|`actions/checkout@v7` (ci.yml:20, 98, 123), `actions/setup-python@v7` (ci.yml:31)|
|R38|"leaving skills unversioned and only in ~/.claude doesn't seem like a good solution" (f7ea3931:2)|B/C|live|`ls -la ~/.claude/skills/` → 12 symlinks into the git checkout; doctor skills row "12 link(s) into this checkout, all resolve"|
|R39|"build up the core skill pool … at least 4 tried and tested (and red-teamed via subagents) skills that are genuinely useful" (f7ea3931:4)|C|live|`ls skills/` → 12 directories; `skillreport` REUSE: "5 of 8 finished forges (62%) produced a skill that was invoked at least once"|
|R40|"fix the skillreport name-mismatch so renames don't hide reuse" (f7ea3931:4)|n/a|live|`skillreport` prints "4 of the 12 forge row(s) … share a name with a row above and are folded into it"; `tests/test_skillreport_rename.py`|
|R41|"when you say 'thin usage evidence' do either of the skills have *any* usage evidence?" (f7ea3931:3)|n/a|live|`use` rows by skill: ai-tell-audit 108, skill-compounder 90, finish-task 85, claim-provenance 84, stale-artifact-check 64, skill-authoring 58 …; `skillreport` separately excludes 391 `sdk-cli` probe invocations|
|R42|"when claude generates 'insights' those should be automatically considered for skill building, and classified as universal (relevant to MANY projects) or local (relevant specifically to *this* project)" (f0feae4c:2 #1)|A/B|partial + declined|Capture is live (insight queue, `hooks/insight-capture.sh` + `precompact.sh`). The classifier is declined with a measurement: `bin/skillinsight:23-28` "One was built and measured. The rule … scored 7/14 against hand-read labels, which is chance on a binary label … Its errors ran LOCAL -> UNIVERSAL … It was dropped for that reason."|
|R43|"a pool of 5--10 skills to seed … installed and made available by default to anyone who installs this package" (f0feae4c:2 #2)|C|live|12 shipped skill dirs, 12 installed links (above); `_skill_dirs()` in `skill_compounder/installer.py` discovers them|
|R44|"if it is deemed especially useful AND it is not already in an existing pull request (open OR closed)" (f0feae4c:2 #3)|C|unver|Duplicate check is in `bin/skillcontrib` (recon path); never exercised end to end — see R9|
|R45|"the history surfer documentation … includes a nice animation as a demo-- let's create one for this repo's readme too" (f0feae4c:2)|n/a|live|`docs/media/forge.gif`, 2 477 789 bytes, mtime 2026-09-05 08:14, referenced at `README.md:5`|
|R46|"I want users to be able to easily install with a 1 liner they can cut and paste into a terminal" (f0feae4c:3)|n/a|live|`README.md:98` `curl -fsSL …/main/install.sh \| bash`|
|R47|"the skill building should happen in the background-- subagent drives, another subagent red-teams, so that it doesn't take over the primary (main) thread" (f0feae4c:19)|n/a|live|`skills/skill-compounder/SKILL.md:95,98`; live round records `~/.claude/skill-compounder/rounds/*.tsv` carry per-round blocking counts from cold reviewers (e.g. `watch-ci-run.tsv`: 6, 6, 5, 7)|
|R48|"don't make the authoring skill optional-- that MUST be part of this package … This *is* a skill builder!!" (f0feae4c:22)|C|live|`skills/skill-authoring/` ships and is linked; 58 `use` rows; invoked from `skills/skill-compounder/SKILL.md:158`|
|R49|"before a new [skill] is counted as complete, the red team review must verify that it can actually trigger under the proper circumstances" (f0feae4c:44)|n/a|live|Routing gate enforced in the live record: `rounds/watch-ci-run.tsv` round 4 lists "ROUTING: must-fire prompt 3 made no Skill call", and that forge was closed `fail` and quarantined rather than installed|
|R50|"the ledger should reflect: what triggered the build / what was built / when it has been used since / whether the skill worked as intended" (f0feae4c:49)|n/a|partial|First three are live (`start`/`done`/`fail`/`use` rows, `trigger_kind` on the newer starts: `agent-decision`, `user-prompt`, `review-dispatch`; the first six forges have none). The fourth is nearly empty: `jq -c 'select(.event=="verdict")'` → **1** row in 1153 (watch-ci-run, `MISFIRED`)|
|R51|"your should make the default outcome not depend on you noticing" (f0feae4c:32)|n/a|live|20/20 hook entries wired; the lesson gate refuses a call rather than asking; 380 mission deliveries none of which a session requested|
|R52|"the 'claim-provenance' skill *should* catch this, but clearly it's not working correctly, or it's not firing when it should" (f0feae4c:50)|n/a|live|Answered with a hook, not a skill: `hooks/claim-gate.sh` on Stop and on `git commit`; the skill itself now has 84 `use` rows|
|R53|"if the tool is converging, continue (with full scope). if the tool is NOT converging, clarify/narrow scope OR abandon the effort" (25a4770c:2)|n/a|live|`skillforge` grants a third round only on a falling blocking count; live proof both ways — `finish-task` was narrowed after ten rounds, and `watch-ci-run` (blocking 6, 6, 5, 7 — not falling) was abandoned to `~/.claude/skill-compounder/quarantine/watch-ci-run-2026-09-05/` with a `WHY-ARCHIVED.md` saying "must not be installed from here"|
|R54|"skills can call *other* skills as part of their operation … skills compound and compose" (issue #19 §3)|A/B/C|partial|`skills/skill-compounder/SKILL.md:158` invokes `skill-authoring`; `finish-task` and `claim-provenance` reference neighbours. Issue #19 is still open ("Deeper skill composition, and the last step of the loop")|
|R55|"the user receives a clear and obvious notification … then … a notification that the new skill is now avaiable (and skills hot reload) … then … a notice that the skill is now being used" (issue #19 §4)|n/a|partial|Only the first is built: the status line renders the running forge and a `✓` at `done`, plus an apply-pending marker (`statusline/skillforge-status.sh`, `PENDING_DIR="$STATE_ROOT/apply-pending"`). `grep -n 'additionalContext\|systemMessage' bin/skillforge hooks/skill-use.sh` → no match, so nothing tells the thread a skill is ready or in use|
|R56|"fix ALL skills and verify they work as advertised w/ real calls" (25a4770c:7)|n/a|partial|`tests/test_routing_claims.py::LiveProbeTest` makes 72 real `claude -p` calls over twelve pinned skills, but is opt-in behind `SKILL_ROUTING_PROBE=1` and skips on an ordinary run|
|R57|"install locally" (f288cf8c:3)|n/a|live|`./bin/skillforge doctor --json` → 11 checks, all PASS (jq, state, settings 20/20, statusline, skills 12, surfer, ledger 1153 rows, counters, forges, mission, review)|
|R58|"make sure documentation (including screen cast!) is fully up to date too" (f288cf8c:3)|n/a|live|`docs/media/forge.gif` re-recorded 2026-09-05; `README.md:51` cites CI run 33984720135 against 74b431a|
|R59|"have you properly tested the full pipeline with actual production runs, and also tested the resulting skills and examined quality of the output carefully?" (f288cf8c:6)|n/a|partial|The pipeline **was** driven in production twice on 2026-09-04/05 and the output **was** examined closely — and both runs failed. `watch-ci-run` (9.70 h) and `wait-for-ci` (1.79 h) are both `fail` rows, both quarantined with `WHY-ARCHIVED.md`, and the single `verdict` row in the ledger reads `MISFIRED` with evidence "'…-> PASSED … exit 0' while 'gh api …/check-runs' reported '10 failure'". No production forge has yet produced an installable skill|
|R60|"for ANYTHING problematic or unresolved you notice … do NOT work around it-- FIX IT RIGHT THEN" (f0feae4c:24)|n/a|partial|Mechanised for the fail-then-fix case only: the lesson arm states the fix at the moment it happens and refuses the next call on the second occurrence (`hooks/repeat-gate.sh`). 10 lesson notes recorded; the general case is still a `CLAUDE.md` instruction|

## Counts

|status|n|
|-|-|
|implemented-and-live-verified|38|
|partial|14|  (12 `partial`, 1 `partial (different form)` = R7, 1 `partial + declined` = R42)
|implemented-unverified|4|
|missing|3|
|declined-with-reason|1|
|total rows|60|

Derived from the table itself:
`awk -F'|' '/^\|R[0-9]+\|/ {print $5}' <this file> | sort | uniq -c` -> 38 live, 12 partial,
1 partial (different form), 1 partial + declined, 4 unver, 3 missing, 1 declined; 60 rows.

## Not fully met (partial, unverified, missing, declined), ordered by centrality to the vision prompt (f58c372b:3)

1. **R7** — "the 'writing it down' piece is what i've been calling a 'skill' -- a combination
   of notes and code that is searchable, findable as a tool in the appropriate future
   contexts, and callable by agents." *Partial, and met in a different shape.* The single
   artifact is split three ways; the two cheap tiers are read or injected, never *called*.
   An `--attach`ed script is a path in a sentence, not an entry point.
2. **R6** — "including the relevant contextual information and any associated code or
   scripts." 3 of 71 note rows carry an attachment; one attachment directory exists.
3. **R8** — "these affect BOTH … where to search for recent prompts AND where skills 'go'."
   Placement is built; per-level *search* is not built at any level.
4. **R4** — "we can also search over those prompts to find things relevant to the current
   scenario." Declined with a measurement (level B search), which is the honest half of R8.
5. **R9 / R44** — "automatically package the skill, fork the repo, push to the fork, then
   submit a pull request." Code exists; 0 `contrib` rows, 0 PRs. Level C has never run.
6. **R11** — `skillnote promote … --to global` **moves** a lesson between levels. 0 uses.
7. **R14** — "i'm a little surprised that the skills take SO long to build." Every recorded
   forge took 0.60 h to 86.40 h against a stated 30-minute target.
8. **R59** — "have you properly tested the full pipeline with actual production runs …?"
   Two production runs, both failed and quarantined; the one verdict is `MISFIRED`.
9. **R50** — "whether the skill worked as intended." 1 `verdict` row in 1153 ledger rows.
10. **R55** — "a notification that the new skill is now avaiable … a notice that the skill
    is now being used." Only the forge-running notification exists.
11. **R54** — "skills can call *other* skills." One real instance; #19 still open.
12. **R56** — "verify they work as advertised w/ real calls." The live probe is opt-in.
13. **R60** — "do NOT work around it-- FIX IT RIGHT THEN." Mechanised for fail-then-fix only.
14. **R30** — "for several weeks, measure across several real repositories." One repo
    dominates; two others have small counts.
15. **R22** — the E2E harness exists; no run artifact is on this machine.
16. **R24** — "pin the one-line installer to releases." The advertised default is still
    `main`; pinning is the second, opt-in form.
17. **R31 (missing)** — "resist adding any new gate or subsystem until … an existing
    component is retired or simplified." A five-event subsystem and a new refusal were added
    after the review; nothing was retired.
18. **R32 (missing)** — "explicitly define the product as: Automatic capture and surfacing;
    human-approved promotion; assisted skill construction." No such sentence anywhere.
19. **R28 (unverified)** — "State supported Claude Code, Bash, jq, Python, macOS, and Linux
    versions." The section exists; its contents were not audited here.
20. **R20 (missing)** — "Protect main from merging when either OS job is red." `main` is not
    a protected branch.
