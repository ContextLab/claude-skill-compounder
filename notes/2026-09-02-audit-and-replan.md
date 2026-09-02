# 2026-09-02 — Audit and re-plan

## User's framing (verbatim, this session)

> i'm a little surprised that the skills take SO long to build-- i thought a skill was
> primarily a markdown file, plus some useful scripts? skills can be relatively simple and
> narrowly scoped, as long as they are useful. compounding knowledge can also be as simple
> as making a note in CLAUDE.md (the local or global version), or building a searchable
> reminder document that gets automatically injected into context at the appropriate times.

Asked for: (1) subagent audit of current approach for soundness, gaps, holes, missed
opportunities; (2) careful plan to get it "up and running (fully) as intended";
(3) history-surfer for context; (4) GitHub issues to track tasks. Ultrawork.

## Status

- Branch: issue-19-close-the-gap (clean at start, HEAD ee7cef5)
- Open issues at start: #19, #9, #8
- Five parallel read-only audit agents dispatched at ~15:32 EDT:
  history+issues, soundness, forge-cost, lightweight-compounding gaps, installed-system check.

## Findings

(filled in as agents report)

### Agent 1: prompt history + open issues (done ~15:35)

Vision quotes (prompt ids): seed pool "5--10 skills", each "an hour (or up to 5 hours)" (f0feae4c:2);
"this *is* a skill builder!!" (:22); building "in the background-- subagent drives, another
subagent red-teams" (:19); "triggers... must happen *automatically* rather than by having the main
thread remember" (:44); skills = "plain language AND deterministic scripts", "skills compound and
compose" (#19 body); convergence policy: "if NOT converging, clarify/narrow scope OR abandon" (25a4770c:2).
Frustrations: forge never self-fires (:31, :42); unearned completion claims (:50, :36); "if the
finish-task skill did NOT finish the task, it's a broken skill!"; "do NOT work around it-- FIX IT";
readme out of date (:18); "does claude -p use my max subscription? ... if api credits, don't use it" (:34);
"narrow scope, fully debug, then iteratively widen" (:55); red-team "must not flag" bias (:9).
Open: #19 recognition-during-work absent, nothing USES a new skill on the problem that caused it;
#9 probes prove "answers the question" not "arrives when needed" (stale-artifact-check 1 of 8 organic);
#8 PreCompact capture unbuilt (design settled: no model in hook, <100ms, weekly queue).
OPEN-THREADS: routing verification stochastic; stage-2 auto-forge cannot pass its own gate;
3 skills unversioned in ~/.claude; nothing resumes a dead forge.
Forge duration: finish-task forge = 22-step record, step 4 after 26 min, killed by sleep, wedged
3.5 days; ten full-scope rounds without converging; round-2 repairs create new findings (3 of 7);
one measured dispatched forge: $3.02 / 19 min / ABANDONED. 4 of 12 shipped skills have zero genuine uses.

### Agent 3: why forging is slow (done ~15:38)

Protocol = 12 steps, 28 doctrine gates, B+C+N*D+E = 8 agents at cap 5; 2N serial dispatches.
Real: ai-tell-audit #2 = 7 builder rounds, 13 reviewers; finish-task closed at rounds=16.
Routing gate is NOT the bottleneck: 18 claude -p calls, ~90s/skill, <1% of a median forge.
Measured durations (10 closed forges): 0.60, 0.95, 0.96, 1.75, 3.11, 3.45, 5.36, 5.81, 6.47, 86.4 h.
Median ~3.3h, 6 done / 4 fail. Cost uncorrelated with value: finish-task 1301 lines, 12h+ forging,
0 genuine uses; most-used skills (skill-authoring 15, claim-provenance 10) are ~405 lines.
Ranked cuts: (1) rounds 3-N of C<->D loop ~60% wall clock, default 2 rounds; (2) orchestrator
layer B catches no defect, caused the 86h stuck forge, run D from main thread for <=2-round forges;
(3) stage E judge: two meta findings ever, never a skill defect, fold into step 1 / async;
(4) mandatory runnable repro: no note records it catching anything.
Keep (near-free, each caught an observed failure): parse gate (~2s), routing gate (~90s),
round 1 + one confirming round, non-fork reviewer, brief-on-disk, --trigger, round TSV.
Counter-evidence: cheapest forge (ai-tell-audit, 35 min) shipped a skill broken within the hour,
BUT that defect was found by running it on a real artifact, not by more rounds -> shift budget
from rounds to USE.

### Agent 4: lightweight compounding gaps (done ~15:39)

Knowledge forms: skills (read back via routing); repeat store (auto, content-addressed, FIRES:
356 rows, 182 sigs, 7 actively refusing) -- the only artifact that both accumulates and fires;
insight queue 57 in / 0 out / oldest 7 days (write-only); session reviews 5 dispatched, 2 CANDIDATE
verdicts (kill-and-rerun-full-suite, check-test-pinned-strings-before-editing-skill-prose), 0 acted on;
ledger 772 use rows, read only by human; notes/ read only by human.
NOTHING writes CLAUDE.md. ZERO references to auto-memory in repo. @file imports unused.
Gaps ranked: (1) cheap branch has no mechanism -- SKILL.md:44 "write a note or update CLAUDE.md"
names no path/CLI/ledger row, taken zero times -> `skillnote` CLI appending to a marker block in
CLAUDE.md + `note` ledger row; (2) queue write-only, globally keyed -> index by project+keywords,
inject on UserPromptSubmit like the repeat store; (3) auto-memory unused+unmeasured;
(4) CANDIDATE verdicts produce no artifact; (5) global CLAUDE.md stanza not part of the product
(installer never writes it); (6) @file import could give ledger+queue a read-back path with no hook.
Accumulated: 13 skills linked, 2 forged by this system (finish-task, dead-guard-detection).

### Agent 2: architecture soundness (done ~15:42)

1. `measure` implemented but never invoked: `skillforge verdict` exists (bin/skillforge:1760-1786),
   appears in NO protocol doc; 0 verdict rows in 807. HIGH
2. `use` answered once: 1 apply row, and it records the skill failing. HIGH
3. Package measures itself: 671/772 use rows harness=true; 16 uses across 6 other projects. HIGH
4. skillreport inflates: "7 of 10 forges reused" counts ai-tell-audit 3x for the same 4 uses;
   10 forges = 5 distinct names. HIGH
5. Complexity ~8:1: ~7k lines skill prose vs ~51k machinery+tests; only 2 of 12 skills forged.
   Removable without losing core: repeat-gate.sh (997), doc-gate.sh (980), skillcontrib, skillrepeat. HIGH
6. repeat-gate has never refused (repeats/denied/ absent after 81 sessions); top eligible sigs are
   benign orientation calls (git clean -nd) -> first fire likely false positive. HIGH
7. No health surface: every hook `|| exit 0` on missing jq/state; no `doctor`. HIGH
8. apply-gate rests on a platform equality DESIGN.md concedes could go silently dead. MED
9. "costly AND recurring" gate is prose only; skillforge start takes no --why; README concedes
   checkpoint fired at edits 12/24/36 and was disregarded all three times. HIGH
10. Queue fed by wrong thing: 46/57 rows are star-insight; documented mechanism produced 1 row. MED
11. Round cap advisory: 3 of 10 forges overran. LOW
12. Wording drift SKILL.md:256 vs README:380 vs round-cap.md:56. LOW
Sound: rounds tsv convergence rule worked for let-the-run-finish (honest ABANDON at round 6).

### Agent 5: installed system, empirical (done ~15:52)

Hooks: 12 entries / 7 scripts / 5 events wired, identical to hooks/hooks.json; plugin path NOT
enabled here, so every hook fires once. 12 repo skills linked, 0 dangling. All 7 scripts fire
correctly when hand-run with realistic payloads. Test suite: 43/43 files, 1875 tests, 0 failures,
2 documented skips.
Real conversion rate (1456 transcripts, all projects): 866 sessions nudged, 96 invoked
skill-compounder, 91 both -> 10.5%. This project: 249 nudges, 3 invocations.
DEAD BUT WIRED: skillreport REMINDER CONVERSION can never compute -- hook writes unary 'x' tally
(compound-improvement.sh:521), reader requires digits (skillreport:1159); test pins "30"/"11", a
format the hook never writes. This is the instrument named as settling the 12-edit constant.
PostToolUseFailure+Skill arms never exercised (773/773 use rows ok:true).
5 of 6 closed forges have no apply row. One paid verdict (CANDIDATE
orchestrator-sendmessage-delivery-unreliable, Aug 25) never indexed.
test_routing_claims.py skip text says ~54 calls; real number is 72.

## Synthesis

The audits agree on one diagnosis. The system has exactly one output path, the forge, and
that path costs a median 3.3 hours and 8 agents per skill while the cheapest forms of
compounding (a line in CLAUDE.md, a reminder injected when a matching prompt or command
appears) have no mechanism at all. SKILL.md line 44 says "write a note or update CLAUDE.md"
and names no path, no CLI, no ledger row. It has been taken zero times in ten days. The
insight queue has 57 candidates in and 0 out. Two paid CANDIDATE verdicts produced nothing.
The one artifact that both accumulates and fires automatically is the repeat store, and it
is the smallest, dumbest, most deterministic piece: a content-addressed signature matched on
PreToolUse. That is the shape the rest should copy.

Second diagnosis: the measurement layer that would tell us whether any of this works is
either dead (reminder-conversion counter cannot parse its own tally), inflated (skillreport
credits the same uses to three forge rows), or never invoked (`skillforge verdict`, 0 rows in
807; 5 of 6 closed forges have no apply row). We cannot tune anything until it reports.

Third: the forge protocol is 12 steps and 28 doctrine gates, and the audit could attribute
observed catches to only four cheap pieces (parse gate, routing gate, round 1 plus one
confirming round, non-fork reviewer). The orchestrator layer catches nothing and caused the
86-hour stuck forge. Stage E has found two meta findings ever. Rounds 3..N are ~60% of wall
clock and the round record shows repairs creating new findings as often as closing them.

## Plan: three tiers of compounding, one promotion path, honest instruments

Tier 0, NOTE. A dated line in a marker block of `./.claude/CLAUDE.md`, `~/.claude/CLAUDE.md`,
or a project memory file. Seconds. Written by `skillnote` (new CLI), which also writes a
`note` ledger row. The forge's "cheap branch" and every CANDIDATE verdict land here.

Tier 1, REMINDER. A searchable store (`<state>/reminders.jsonl`) of short prose keyed on
keywords, paths, or command signatures; a UserPromptSubmit/PreToolUse hook injects matches as
additionalContext. Generalises what repeat-gate already does for command signatures. Written
by `skillnote --remind`, and by the insight queue when a candidate recurs.

Tier 2, SKILL. SKILL.md plus optional scripts, forged by ONE builder and ONE cold reviewer,
default two rounds, parse gate and routing gate kept, orchestrator layer dropped for
two-round forges, judge folded into the brief, repro optional. Target: under 30 minutes for a
narrow skill. Escalate rounds only on a converging record; hard cap.

Promotion: queue -> note -> reminder -> skill, driven by recurrence counted the way the repeat
store counts it. `skillinsight promote` moves a candidate up one tier.

Instruments: fix the unary counter, dedupe skillreport, wire or remove `skillforge verdict`,
index the lost verdict, add `skillforge doctor` and a TTL reaper for stuck forges.

Execution waves (independent within a wave):
  W1 foundation: measurement fixes; doctor + reaper; installer writes global stanza; trivia.
  W2 tiers: skillnote (T0); reminder store + inject hook (T1); forge diet rewrite of SKILL.md,
     README, global stanza (T2).
  W3 close the loop: promotion path; apply-the-skill-to-the-triggering-problem (#19);
     PreCompact (#8); keep/fix/retire for repeat-gate, doc-gate, skillcontrib, skillrepeat.

## Execution log

- ~15:58 issue-filing agent dispatched (12 issues + epic; comments on #19, #8).
- ~16:00 Wave 1 dispatched, four agents, disjoint ownership:
  W1a hooks/compound-improvement.sh, bin/skillreport, tests/test_ledger.py, test_hook.py,
      test_skillreport_*.py -- unary counter + reuse double-count.
  W1b bin/skillforge, statusline/skillforge-status.sh, tests/test_skillforge*.py,
      test_forge_staleness.py, test_statusline.py, NEW tests/test_doctor.py -- doctor + reap.
  W1c skill_compounder/installer.py, tests/test_installer*.py, README.md, docs/DESIGN.md
      -- doctrine stanza under marker in <claude-dir>/CLAUDE.md.
  W1d bin/skillinsight, tests/test_insights.py, test_queue_surfacing.py,
      test_routing_claims.py -- `skillinsight reindex` (recover lost verdict), skip text.
  Rule: no commits until all four return; then one authoritative ./run_tests.sh.
- ~16:06 issues filed: epic #31; W1 = #24 (measurement), #25 (doctor/reaper), #26 (installer
  stanza), #29 (trivia), #30 (conversion baseline); W2 = #20 (skillnote), #21 (reminders),
  #22 (forge diet); W3 = #23 (promotion), #27 (repeat-gate), #28 (keep/fix/retire), + #19, #8.
  Corrections vs. audit: 10 starts = 6 distinct names (not 5); all 7 repeat-gate signatures
  at threshold have allowlisted heads (git, pwd) at repeat-gate.sh:721, so none could refuse.
- ~16:35 W1c done: installer.py doctrine block (markers claude-skill-compounder:doctrine:start/end,
  manifest keys doctrine=installed|user-owned|declined|left-alone, doctrine_created), README:181,
  DESIGN.md:663, 15 new tests (38 OK). Orchestrator TODO after wave: scripts/setup.py needs
  --no-doctrine flag (env opt-out SKILL_COMPOUNDER_DOCTRINE=0 already works).
- ~16:47 W1a done: counter format = unary tally (hook's >> is load-bearing; insight-capture reads
  siblings with wc -c), reader now counts bytes (skillreport:1239); reuse deduped per name
  (representative row = latest done, then latest closed) -> "5 of 6 (83%)" on the real ledger.
  Cross-owner repairs owed to orchestrator after wave: tests/test_skillforge_hardening.py:530
  writes s.edits="60" -> must be "x"*60 (W1b owns that file; tell W1b or do serially).
  W1b's new env vars SKILLFORGE_DOCTOR_JQ_VERSION, SKILLFORGE_ACTIVE_TTL must be documented as
  knobs (test_forge_apply knob test) -- W1b's job.
- ~16:52 W2b spike done (CLI 2.1.258): PreToolUse additionalContext reaches the model 3/3
  (labelled "PreToolUse:Bash hook additional context:"); permissionDecision allow+reason 0/6;
  imperative wording obeyed only 2/4 (refused as prompt-injection) -> reminders must be
  statements of fact, never imperatives. Entry at docs/CLAUDE-CODE-BEHAVIOR.md:774-849.
  Trap: injected text is not a stream-json record; grep the model's reply, not the tool_result.
- ~16:58 W1d done: `skillinsight reindex` recovered the Aug-25 CANDIDATE
  orchestrator-sendmessage-delivery-unreliable into index.jsonl (second run no-op); `reviews`
  now sorts by ts; skip message derived from probe.prompts_for (72 / 216). Incident: an
  undecorated test spent two live probe runs (~18 min + ~2 min) before being killed; now
  pinned by test_the_live_probe_is_gated_and_says_what_it_will_cost. Owed: README ~617-624
  skillinsight subcommand list lacks `reindex` (orchestrator, after wave).
- ~17:03 W1b done: doctor (:1350-1710), reap, start auto-reaps past-TTL corpse; TTL idle-based
  (since last step), default 21600s; env SKILLFORGE_ACTIVE_TTL, SKILLFORGE_DOCTOR_JQ_VERSION;
  help range bug fixed (:3120). Live doctor: all PASS except counters (f0feae4c edits file
  holds "36" + 900 x bytes: mixed forms, needs hand repair). 41+30+58+31+65 tests OK.
- ~17:05 Wave 1 close-out agent dispatched (knobs set, setup.py --no-doctrine, README lines,
  CLAUDE.md, OPEN-THREADS, whole suite). Then commit.
