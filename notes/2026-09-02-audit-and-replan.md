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
- ~17:35 Wave 1 committed 03773ad and pushed (44 files, 1986 tests, 0 failures, 2 documented skips).
- ~17:36 Wave 2 dispatched, three agents, disjoint ownership:
  W2a bin/skillnote (new), tests/test_skillnote.py (new), tests/test_ledger_v2.py,
      hooks/session-review.sh, tests/test_session_review.py, docs/CLAUDE-CODE-BEHAVIOR.md
      (memory read-back measurement) -- tier 0 + reminder writer.
  W2c hooks/remind.sh (new), tests/test_remind.py (new), hooks/repeat-gate.sh (--norm-of),
      tests/test_repeat_gate.py, hooks/hooks.json, installer.py, tests/test_installer.py,
      tests/test_plugin.py, tests/test_hook.py -- tier 1 injection hook, both wirings.
  W2f bin/skillforge, tests/test_skillforge.py, tests/test_forge_rounds.py (new),
      tests/test_skillforge_hardening.py, tests/test_forge_apply.py -- round/escalate/horizon;
      default budget unchanged this wave (docs wave changes cap + docs together).
  Wave 3 after commit: promotion (bin/skillinsight, tests/test_insights.py); forge-diet docs
  rewrite (skills/skill-compounder/**, skills/skill-authoring cross-refs, README, .claude/CLAUDE.md,
  tests/test_doctrine_sync.py, test_routing_gate.py, test_seed_authoring.py, docs/DESIGN.md)
  incl. README tiers section + CLAUDE.md counts; then #19 apply-the-skill, #8, #27, #28.
- ~17:50 cold review #27/#28: repeat-gate FIX (drove real hook on all 10 threshold sigs: 0 denied,
  all allowlisted heads; a synthetic non-allowlisted sig DOES deny, machinery fine, population
  empty; issue's "require recovery" fix is a no-op; concrete fix = default-off REFUSE arm, and
  correct skillreport:325 + skillrepeat GATE column which print "refuses" without applying
  allowlist; cost 0.043s+0.035s per Bash call). doc-gate KEEP (3 real refusals, 3 sessions, all
  wrote docs and pushed; fixes: :533 tr splits quoted DOC_GATE_OVERRIDE reason -> silent bypass;
  :814 NEITHER_RE ^notes?/ is repo-local, caused the only override). skillcontrib RETIRE (47 runs,
  0 reconnaissance; DEFAULT_REPO is its own repo; no PR to any upstream ever; contribute-skill
  skill 0 real uses, archive together) -- second cold opinion dispatched. skillrepeat FIX GATE column.
- ~17:58 second cold opinion on skillcontrib: KEEP (dedup works live, exit 9 on a real
  duplicate; 61 tests OK; no misfire evidence; its precondition, a reused clean skill, only just
  became satisfiable). No concurrence -> not retired. Fix README:783 (promises `gh pr create
  --dry-run`, which the skill forbids and which "may still push") and README:774-776 (demos
  dedup/whoami without --repo; DEFAULT_REPO is this repo).
  #28 resolution: doc-gate keep + 2 fixes; skillcontrib keep + README fixes; skillrepeat fix GATE.
  #27 resolution: default-off the REFUSE arm, keep learning; fix skillreport:325 + skillrepeat.
- ~18:12 W2f done: skillforge round (:2181, exit 3 at cap, no row), escalate (:2261, exit 4
  refused; --converging needs strictly falling blocking; --narrowed once; two grants max ->
  4 rounds), horizon (:2374). `escalate` ledger event. Default budget unchanged. No new env vars.
  40 new tests + owned files green. test_doctrine_sync DerivationCommandTest will fail until
  README's tuning table gains the REMIND_* knobs (W2c's file set does not include README ->
  orchestrator close-out).
- ~18:25 W2c done: hooks/remind.sh (453 lines), repeat-gate --norm-of (exempt from the
  REPEAT_GATE=0 switch), installer REMIND_MARKER on UPS+PreToolUse (14 entries / 8 scripts),
  hooks.json order pinned. Env: SKILL_COMPOUNDER_REMIND, REMIND_MAX=2, REMIND_COOLDOWN=0,
  REMIND_MAX_ROWS=2000, REMIND_NOW. Cost 49-66 ms/event on 500 rows (jq splits() regex trap
  cost 230 ms; pinned in header). 72 new tests. Owed: README:796 + .claude/CLAUDE.md:273
  derivation grep needs REMIND and SKILLNOTE prefixes (predicted third narrow-grep occasion).
  Open decision: remind.sh has no prune of its claim/stamp tree.
- ~18:45 W2a done: bin/skillnote (901 lines; add/remove/list; --remind with --keyword/--path/
  --command; shell twins of installer write discipline; ensure_horizon; ledger event note).
  Memory read-back MEASURED (2.1.258): MEMORY.md injected 3/3; an indexed body is Read 3/3;
  an UNINDEXED memory file is never seen 0/3 -> the index line is load-bearing; ledger records
  readback:"via-index". session-review CANDIDATE now writes a note. 72+55+69 tests green.
- ~18:47 Wave 2 close-out agent dispatched (README grep/tuning/tables, CLAUDE.md counts,
  wrapping ratchet, DESIGN.md, whole suite). Then commit + push, then Wave 3.
- ~19:55 Wave 2 committed 7507a0b, pushed. Suite green (0 failures, 2 documented skips).
- ~19:57 Wave 3 dispatched, three agents, disjoint ownership:
  W3a bin/skillinsight, tests/test_insights.py, tests/test_queue_surfacing.py -- promote (#23),
      drain live backlog (notes into this repo's .claude/CLAUDE.md; memory scope for other repos;
      bulk-decline star-insight noise).
  W3b skills/skill-compounder/**, skills/skill-authoring cross-refs, README, .claude/CLAUDE.md,
      docs/DESIGN.md, installer DOCTRINE_TEXT, tests/test_installer.py, test_doctrine_sync.py,
      test_routing_gate.py, test_seed_authoring.py, bin/skillforge (budget 12->6), test_skillforge,
      test_forge_rounds, test_statusline, test_forge_apply -- the forge diet (#22 docs half).
  W3c hooks/repeat-gate.sh, bin/skillrepeat, bin/skillreport, hooks/doc-gate.sh + their tests --
      #27 (REFUSE arm default-off, instruments apply the allowlist) and #28 (doc-gate two fixes).
  Wave 4 after commit: #8 PreCompact capture; user's hand-written ~/.claude/CLAUDE.md stanza
  (user-owned, installer skips it) must be updated to the new protocol by hand -- report it.
- ~20:25 W3a done: skillinsight promote/promote-review (:676), decline --source bulk (:567),
  judged_json union; live drain: 46 star-insight declined, 7 promoted to memory scope in other
  repos, 2 verdicts, 1 note into this repo's .claude/CLAUDE.md. BUG found in bin/skillnote:
  substring grep counted a prose mention of the marker as a block -> second add refused forever.
  Fixed by orchestrator (grep -x at :395, awk $0==e at :415), regression test added (73 OK),
  .gitignore gains *.bak-skill-compounder-*. W3a resumed to promote the 5 remaining rows.
- ~20:45 W3c done: REPEAT_GATE_REFUSE (default 0) at repeat-gate.sh:379; --eligible-of door
  (:933); skillrepeat GATE column + skillreport GATES block now ask the gate (live copy: 10->0
  "would refuse", matching 0 real denies, pinned by InstrumentAgreementTest). doc-gate: quote-
  aware split (:586), DOC_GATE_NOTES default `doc` (:461). Owed to close-out: README tuning rows
  REPEAT_GATE_REFUSE / DOC_GATE_NOTES; README:806 + CLAUDE.md grep need SKILLREPORT prefix
  (count 103); this repo's .claude/settings.json should set DOC_GATE_NOTES=neither (notes/ is
  a dated log here); README:681 skillinsight promote/decline --source lines.
- ~21:20 W3b done: SKILL.md rewritten (497 lines; steps 0..6; tier block, cheap-branch,
  tier-before-forge, hard-round-cap, verdict-follows-the-apply, forge-runs-in-the-background;
  frontmatter + Trigger precision byte-identical); references rewritten; README two diagrams,
  "Three ways to compound" section, bar 3/6, ledger seven questions, skillcontrib corrections;
  DOCTRINE_TEXT updated; test_doctrine_sync retire/add/rename per spec; bin/skillforge needed no
  edit (no literal default budget; fixtures moved to 6). All owned tests green.
- ~21:22 Wave 3 close-out agent dispatched. Then: commit, push, update user's hand-written
  ~/.claude/CLAUDE.md stanza to DOCTRINE_TEXT (user-owned; installer skips it), Wave 4 = #8.
- ~21:30 user's ~/.claude/CLAUDE.md "## Compound Improvement" stanza replaced with the shipped
  DOCTRINE_TEXT inside the installer's marker block (backup at
  ~/.claude/CLAUDE.md.bak-skill-compounder-20260902-190156). Future installs now manage it.
- ~21:35 ./install.sh run against the real config: 14/14 hook entries (remind.sh on UPS and
  PreToolUse Bash|Write|Edit), 6 CLIs, doctrine block "already current". Mixed counter file
  repaired by hand (36 + 900 x -> 936 x; backup .bak-mixed). `skillforge doctor`: 8 pass, 0 fail.
  Real e2e agent dispatched: tier 0 note read back by a real headless session? tier 1 reminder
  injected on UserPromptSubmit and PreToolUse in a real session? (real config, real state).
- ~22:05 real e2e (CLI 2.1.259): tier 0 note read back 3/3 (and 3/3 with the script deleted, so
  the note was the only source); tier 1 UserPromptSubmit 3/3; tier 1 PreToolUse 0/3 -> two
  package bugs: (1) skillnote SELF from dirname $0 without resolve_link, so the installed
  symlink could not find ../hooks/repeat-gate.sh and refused --command; (2) skillnote stored
  "Bash\n<sig>" while remind.sh compares the bare --norm-of output. Both fixed by orchestrator;
  test_skillnote repinned to the bare form (it had pinned the bug); WriterReaderTest added to
  test_remind driving the real skillnote through a symlink into the real hook. 73 + 73 OK.
  This is the audit's thesis in miniature: two rounds of review passed it, one real use broke it.
- ~22:20 PreToolUse arm re-tested live through the installed symlink (2.1.259): 3/3 hits,
  3/3 replies quote the reminder verbatim; UserPromptSubmit 0/3 (the prompt had no keyword
  row), so the arms are distinct. Tier 1 now works end to end where the user will use it.
- ~22:40 Wave 3 committed 15b3b28, pushed. Suite: 47 files, 0 failures, 2 documented skips.
- ~22:42 Wave 4 dispatched: #8 PreCompact capture (one agent, whole repo, ends with install +
  doctor). Issue-comment agent dispatched for #20-#23, #27, #28, #31, #19.
  After W4: final whole-suite check by orchestrator, commit, push, decide main merge, final report.
- ~23:40 W4 done: #8 built. `hooks/precompact.sh` + `tests/test_precompact.py` (47 tests),
  wired on BOTH paths (installer + hooks.json) with **no matcher** -- `PreCompact`'s matcher
  selects the trigger and `manual`/`auto` name the same loss. Payload re-measured on 2.1.259
  and written up at docs/CLAUDE-CODE-BEHAVIOR.md:510, including the previously unconfirmed
  `"trigger":"auto"`: seven keys, the field is `trigger` and NOT the documented
  `compaction_trigger`, `permission_mode` is absent, and there is **no
  `last_assistant_message`** -- so the bounded transcript read is mandatory here, not the
  fallback it is on Stop. No model in the hook: #8 had measured that a PreCompact hook blocks
  compaction with no default timeout (300 s hook -> 300.9 s stall) and that setting a timeout
  instead truncates the writer mid-write, silently. Cost 27 ms / 86 ms median (no candidate /
  one) on the system jq at the 256 KB bound; the budget is process starts, not bytes, so
  ProcessCountTest pins the exec count instead of a stopwatch.
- ~23:40 Two defects found and fixed in W4, and neither was in the new code's happy path.
  (1) THE TAB-IFS DEFECT, found by a test rather than by review. The four payload fields were
  read with one `IFS=$'\t' read -r a b c d` over an `@tsv` line. **Tab is an IFS whitespace
  character**, so a run of tabs collapses into ONE delimiter: `["s1","","/t","/c"]` puts the
  transcript path in the variable holding the claim key and every field after the empty one
  shifts left. The field most likely to be empty is `prompt_id`, which is undocumented, so
  the failure was "a build stops sending prompt_id -> `[ -f "$tp" ]` tests the cwd -> the
  hook captures nothing, for ever, and nothing looks wrong". Fixed to four `IFS= read` on
  four lines. (2) THE SHARED REGEX. The marker scan's paragraph terminator was a CONSUMING
  group, so it ate the blank line ending each candidate and every SECOND marker was dropped
  -- adjacent markers lost one, three in a row lost the middle. Two markers with prose
  between them were found normally, which is exactly why it survived review of both hooks.
  W4 verified the fix and pinned the defect in both test files rather than applying it; it is
  now APPLIED, as the lookahead `(?=\n[ \t]*\n|\z)`, byte-identically in
  hooks/insight-capture.sh:560 and hooks/precompact.sh:314, each carrying a comment naming
  the twin. Both pinned tests flipped from asserting 1 to asserting 2, and a
  three-marker test added to each -- two adjacent markers alone would pass on a scan that
  still skipped every other one. Measured on jq-1.7.1-apple and jq-1.6.
- ~23:40 Counts after W4, all re-derived rather than carried: **15 hook entries over 6
  events** (`PreCompact` is the sixth; `python3 -c` over hooks/hooks.json, and
  installer.OUR_EVENT_MARKERS agrees), **12 clocks** (`_NOW` names; `PRECOMPACT_NOW`
  deliberately does not fall back to `INSIGHT_NOW`/`CI_NOW`), **116 env names over 18
  prefixes**, **48 test files**. The env-prefix alternation in .claude/CLAUDE.md needed
  PRECOMPACT added or it could not produce its own list -- the fourth time that command has
  been narrower than the paragraph it introduces, and the first time a test
  (test_doctrine_sync) forced it in the same change rather than a later one.
- ~23:45 One claim of ours falsified by our own fix and corrected: .claude/CLAUDE.md:244
  described the extractor defect as "known, pinned in both test files rather than fixed
  here". It is fixed, so that paragraph now states the lookahead as the invariant and names
  the two regression tests that hold it. This is the CLAUDE.md rule applied to CLAUDE.md.

## Session close (2026-09-02, ~23:30 EDT)

Four commits on issue-19-close-the-gap: 03773ad (W1), 7507a0b (W2), 15b3b28 (W3), c06eb6c (W4).
Whole suite green at each commit; the last run had 48 files, 0 failures. Installed for real;
`skillforge doctor` all PASS. main fast-forwarded to c06eb6c if the push succeeded (see git log).
Open (also in OPEN-THREADS.md): remind.sh claim/stamp prune; REMIND_MAX / cooldown unvalidated;
100 ms PreCompact target holds on system jq only; #19 point 4 (deeper composition); #30 to be
re-measured once the tiers have data; ai-tell-audit reports pre-existing README rows over
threshold (`names`, `lives`, bolded-term-colon) outside this session's prose.
Resume: read this note top to bottom, then `gh issue view 31`.

## Review received (2026-09-02, ~23:10 EDT) and response

An external review (pasted by the user) lists: main red in CI (VERIFIED: every `tests` run
since Sep 1 failed on both OS; runs 33704550609/33704537708 for 385624f/c06eb6c); tracker out
of sync with landed work; full user journey unproven; stage-2 auto-forge structurally blocked;
measurement indirect; over-engineered vs evidence; paid review default-on; installer follows
mutable main; docs too large; hygiene (skillreport:57 comment, Python escape warnings,
ShellCheck absent, Node 20 actions, version 0.2.0 unreleased). Priorities P0 CI, P1 tracker,
P2 E2E harness, P3 cautious beta, P4 evidence over weeks.
Plan: P0 triage from real logs, then parallel fixers by file ownership; P1 reconcile via gh
(parallel, no repo files); then P2 E2E harness (tests/e2e/, throwaway config, real claude -p);
then P3 (paid review opt-in, tagged release + pinned installer, doctor --json, quickstart,
supported versions, upgrade/rollback test). P4 cannot be done in a session.
- ~23:25 CI triage (run 33704550609, both OS): 11 failing tests. Product: apply-gate emits
  nothing at its documented ceiling on Linux (single argv > MAX_ARG_STRLEN 131072; fix = stream
  via --rawfile). Portability: `stat -f %m || stat -c %Y` order captures GNU garbage
  (skillinsight:1295, session-review:403; skillnote:298 has no GNU form at all). Invalid tests:
  forge-apply 1<<18 argv pattern; repeat-gate deny padding calibration; dead-guard example
  relies on BSD wc padding (canary vacuous); seed-authoring sweep of live ~/.claude roots.
  CI config: shallow checkout hides eec5d1b and the first commit (fetch-depth 0). Doc:
  claim-provenance cites 40babc1, an object on this laptop only (re-point to a pushed commit).
  Fixers dispatched with disjoint ownership: A+B+G (hooks/apply-gate.sh, bin/skillinsight,
  hooks/session-review.sh, bin/skillnote + their tests, escape warnings); C+D (four test
  files); E+F (ci.yml fetch-depth/action bumps/shellcheck job + .shellcheckrc,
  claim-provenance SKILL.md + its test). E2E harness agent (tests/e2e/, docs/e2e.md) and
  tracker reconciliation agent running in parallel.
- ~23:45 E+F done: ci.yml checkout v7 + fetch-depth 0, setup-python v7, setup-node v7,
  shellcheck job (0.11.0, 67 findings, 0 error-level; SC2016/SC2034/SC2329 suppressed with
  reasons in .shellcheckrc; 19 open at warning/style for follow-up). claim-provenance worked
  example re-pointed 40babc1 -> 83a75b5 (on origin, same number). Fresh full clone: 56/56;
  depth-1 clone: exactly the two shallow failures. doctor --json done (51 tests).
- ~23:55 tracker reconciled: closed #8, #20-#29 with evidence; #19 retitled (remaining: deeper
  composition + forged skill actually used); #30 open as measurement campaign; #31 body is now
  a status table. New: #32 PreCompact residuals, #33 remind prune/constants, #34 no forge has
  run since the diet, #35 CI red (P0), #36 E2E, #37 event attribution, #38 release packaging,
  #39 paid review opt-in, #40 docs split, #41 hygiene. Note: the Python escape warning claim
  did not reproduce on 3.9 (SyntaxWarning only on 3.12+); fixer A+B+G is fixing the docstrings
  anyway.
- ~00:10 (Sep 3) E2E harness done: tests/e2e/journey.py (+README, docs/e2e.md). Real run: all
  11 steps PASS, 6 sonnet calls, 35 s; report at /tmp/skill-compounder-e2e-2026-09-02/REPORT.md.
  Auth limit: a throwaway CLAUDE_CONFIG_DIR cannot authenticate (Keychain), so sessions use
  --settings + --setting-sources '' with HOME intact; routing measured at project scope, n=1.
  Product failures: none. Owed: link docs/e2e.md from README (packaging agent owns README).
- ~00:25 (Sep 3) C+D done (four test files; Linux behaviour simulated with GNU-shaped shims;
  found hooks/repeat-gate.sh:553 sed dies E2BIG at ~890 KB of env, reported not fixed).
  Packaging done: install.sh --ref/--update/--rollback (+ SKILL_COMPOUNDER_REF/UPDATE),
  <state>/install-ref record, plugin.json 0.3.0, README quickstart/supported versions/
  updating sections, docs/releasing.md; two installer defects found and fixed while testing.
  Owed to close-out: .claude/CLAUDE.md derivation grep paths must include install.sh;
  skillforge header now names SKILL_COMPOUNDER_REVIEW (done by orchestrator).
- ~00:40 (Sep 3) A+B+G done. `hooks/apply-gate.sh` no longer puts the block reason in the
  argv: it writes it to `$TMP/reason.txt` and passes `jq -n --rawfile r`, so the message
  size stops being an exec-size question. The bug it fixes is a Linux-only one --
  `MAX_ARG_STRLEN` caps a SINGLE argv element at 131072 bytes and a larger `ARG_MAX` does
  not raise it, so at this file's own documented ceilings (MAX_TRIGGER 20000, MAX_NAMED 20)
  the reason rendered 409452 bytes and the emit died with E2BIG, printing nothing, while
  macOS passed. A shim test reproduces the cap on macOS rather than trusting CI to notice
  next time. The `printf` and the `jq` each keep two levels of subshell, both load-bearing
  under a file-size rlimit; the header records the measurements.
  Three `stat` call sites fixed the same way: query the GNU form first, validate the result
  before accepting it, and only then fall back to BSD. `stat -f %m || stat -c %Y` is wrong
  because GNU's `-f` is `--file-system`, so the bogus format exits 1 while the valid part
  still prints and `$( )` captures it. `bin/skillinsight:1304` and
  `hooks/session-review.sh:410` are mtimes reordered (`-c %Y` then `-f %m`, digits guard
  between); `bin/skillnote:307` is a mode query that had no GNU form at all and gained one
  (`-c '%a'` then `-f '%OLp'`). Docstrings carrying regex escapes made raw, which silences
  the SyntaxWarning on 3.12+; it never reproduced on 3.9.
- ~01:20 (Sep 3) close-out found one red in the whole-suite run and fixed the code, not the
  test: `tests/test_ledger.py::test_neither_script_contains_a_network_call` greps
  `bin/skillforge` and `bin/skillreport` for `curl `, `wget `, `nc `, `https://`, `http://`.
  The `doctor --json` work had introduced `jq -nc` at `bin/skillforge:1506`, whose `-nc `
  matches the netcat needle. Not a network call, but the assertion is the one that must not
  be weakened, so the call site was respelled `jq -n -c` -- identical behaviour and the
  spelling the other seven `jq -n -c` sites in that file already use. `skillforge doctor
  --json` still exits 0 and `test_ledger.py` is 45 tests OK. Worth noting for the next
  agent: this is a substring gate, so any future `-nc`, `-c`-clustered flag or a URL in a
  comment will trip it the same way.
- ~01:05 (Sep 3) CI wave committed 89ca608, pushed to branch and main. Local suite: 48 files,
  2351 tests, 0 failures, 2 documented skips; shellcheck --severity=error clean; plugin
  validate --strict clean. CI watch armed for 89ca608. #39 (paid review opt-in) dispatched;
  #40 (docs split) follows it; tag v0.3.0 per docs/releasing.md once CI is green on both OS.
- ~01:50 (Sep 3) CI for 89ca608 still red (run 33715482451); round-2 triage+fix agent dispatched.
  #39 done: SKILL_COMPOUNDER_REVIEW default 0 (only literal "1" enables), gate 10 refuses
  before any claim/lock/stamp, doctor reports it, README cost median $0.17 (n=6) with the jq
  command; suite 48 files / 2338 tests OK / 2 skips. Owed: tests/test_forge_apply.py:1605
  stale comment says default "1"; install.sh opt-in flag (#39 bullets 2-3) not done.
  Watcher lesson: `gh run list --commit` returned nothing; filter on headSha instead.
- ~02:35 (Sep 3) CI round 2: only one Ubuntu failure remained, the new argv-cap shim test
  itself (execve refused the oversized argument before the shim loaded); fixed with a
  layer-reporting probe and a kernel-refuser variant that runs on macOS. Committed cfb2bc6
  with #39 (review opt-in), pushed to branch and main; CI watch armed on headSha.
  Dispatched: #40 docs split (README -> ~400 lines + docs/architecture, operations,
  measurement, development; tests re-pointed) and #39 install flags (--enable-review /
  --disable-review via installer set_env/unset_env, manifest review_env_set).
  Next: on CI green, tag v0.3.0 per docs/releasing.md, GitHub release, verify pinned install
  into a temp claude dir, --update/--rollback between two refs.
- ~03:10 (Sep 3) CI GREEN on main at cfb2bc6 (run 33719557434), all jobs. First green run since before Sep 1.
- ~03:50 (Sep 3) docs split + install flags committed a2aa2d4, pushed to branch and main.
  README 366 lines; docs/architecture 516, operations 356, measurement 139, development 82.
  CI watch armed. On green: tag v0.3.0, GitHub release, verify pinned install + update/rollback.
- ~04:05 (Sep 3) E2E journey on a2aa2d4: 12/12 PASS, 6 calls, 41 s; plugin validate strict
  exit 0; plugin version 0.3.0. Waiting on CI for a2aa2d4, then tag v0.3.0.
- ~04:40 (Sep 3) CI green on a2aa2d4; v0.3.0 tagged there and released
  (https://github.com/ContextLab/claude-skill-compounder/releases/tag/v0.3.0). README pinned
  line now fetches install.sh from the tag (e77c1b2). Verification of the tag in a throwaway
  config and issue closure (#35, #36, #38, #39, #40, #41) dispatched.
- ~05:20 (Sep 3) tag verification in a throwaway: install/enable/disable/uninstall PASS;
  --update/--rollback PASS from the standalone copy but silently a no-op from the managed
  checkout's own copy (gate read only the curl case). Fixed in c9803bc with a dirty-tree
  refusal by name; docs/releasing.md says which copy to verify with at refs before v0.3.1.
  Plan: CI green on c9803bc -> tag v0.3.1 -> verify update v0.3.0 -> v0.3.1 -> rollback.

## Session close (2026-09-03, ~05:30 EDT)

Since the review: commits 89ca608 (CI wave, E2E, packaging, doctor --json), cfb2bc6 (review
opt-in, argv-cap test), a2aa2d4 (docs split, install flags) = v0.3.0, e77c1b2 (README tag
line), c9803bc (install.sh managed-copy fix). CI green from cfb2bc6. Issues: #8, #20-#29
closed; #32-#41 opened; #35/#36/#38/#39/#40/#41 being closed with evidence.
Open after this session: #19, #30, #32, #33, #34, #37; ShellCheck warning-level findings;
repeat-gate sed E2BIG; REMIND constants unvalidated; stage-2 auto-forge blocked on its own
routing gate; usage evidence is one machine. Resume: this note, then `gh issue view 31`.
- ~06:40 (Sep 3) b43eca7 (offline install.sh test; found and fixed a set -e dead branch in my
  c9803bc patch), b7f6a47 = v0.3.1 (bump + README pinned line). CI green on both. Tagged and
  released v0.3.1. Verified between real tags in a throwaway: v0.3.0 -> v0.3.1 (standalone)
  -> v0.3.0 (rollback from the managed v0.3.1 copy) -> managed v0.3.0 copy no-op as
  documented -> v0.3.1; doctor 9/9; install-ref current v0.3.1 / previous v0.3.0.
