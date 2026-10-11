# 2026-10-11: evidence store, command-text guards, the glob probe

Follows notes/2026-10-11-usage-audit.md. Branch feat/evidence-episodes (off
fix/recall-parse-markdown-reply, which is one commit ahead of main). Nothing pushed.

The user's direction: proceed in a data-driven way, settle ambiguous questions with
red-teaming subagents and experiments, and aim at a searchable, layered store of tools and
skills usable across projects, so that a problem solved well once is never derived again.

## Studies (reports in notes/2026-10-11-usage-audit/)
| Study | Report | Verdict used |
|-|-|-|
| script threshold | threshold-study.md | run count alone does not tell a tool from a probe (3+ runs, same arguments: 1 tool in 15). Rule: outside a repository, not a test, 2 passing runs and takes its input from the call (arguments varied, or reads them): 58% tools, 8% probes of 59 read; misses 9% tools of 65 read. Plus "main loop, 3+ passing runs" for no-argument checks (19 scripts of evidence). |
| guard text | guard-study.md, guard_text.py | drop here-document bodies and comments; a match must begin in command text. Removes 15 of 66 recorded stops, loses 0 of 246 true positives before guards existed. Patterns matter more than text: three rewrites reach 96% precision. 57 of 72 zsh-nomatch-glob recalls came after the session's one refusal. |
| episodes | episode-study.md | red→green is not worth a trigger (1 of 26 reusable). Worth it: T1 tool/machine/harness failure then pass, first meeting only; T2 three failed calls with different texts then a pass (9/12, held out 5/6); T3a hosted check red after local green; T4 typed /compound:learn. Harness refusals belong in T1 (276 calls, no lesson). |
| surfacing | surfacing-study.md | still running when this was written |

## Built (each with tests; ./run_tests.sh 26 files OK, claude plugin test 302 pass, validate --strict passes)
1. Evidence store. `compound evidence note|list|show`; the mod runs `note` after a Bash call
   that may have run a script (not awaited). Snapshot = bytes + runs, id from path and bytes.
   `add --from-evidence ID`, `--attach` recognises recorded bytes and refuses an unrun
   program unless `--unrun`; `.evidence.json` beside the lesson; `skip --evidence ID`.
   Stop refused once per script owed a decision (`refuse` why `evidence`, claim `evidence-<id>`).
   tests/test_evidence.py (27), hooks/evidence.test.ts, tests/journeys/journey_evidence.py
   (real sessions, 14 of 14: the session recorded the script from its copy, at user level,
   after running `compound find` first; in another run it declined a trivial script).
2. Guards read command text (the study's scanner, now in bin/compound). tests/test_command_text.py
   holds 48 commands to what zsh, bash and sh run.
3. Probe `unmatched-glob`: a lesson may name a check of the call against the files. Hit is
   sure, refused per call text. Shipped lesson zsh-no-matches-found names it. tests/test_probe.py
   holds 40 commands to the real zsh; probe_coverage.py: after being confined to the call's directory and the project it reads 41 of 56 recorded failures.
4. Security review findings fixed: no git run in a script's directory (in_repo is read from
   the directories above); a script holding a credential shape is not copied; a snapshot's
   name is a plain file name and never SKILL.md in any case; `--attach` compares SKILL.md
   without case; older `git_tracked` runs with fsmonitor off (config of another project's
   repository can still name other programs: not fully closed).

## Decisions made without asking, and why
- `--attach` of an unrun program is refused (exit 2) unless `--unrun`: the user's rule is
  that a skill's code comes from what ran. 13 existing test calls attach a script as a
  fixture and now pass `--unrun`; three expectations list `.evidence.json`.
- No red→green trigger: measured 1 of 26.
- A script inside a repository is never owed: the repository keeps it.

## Not done / open
- Capture triggers T1, T2, T3a from the episode study; harness refusals; subagent firings
  queue for the parent's stop.
- Pattern rewrites in the user's real store (zsh-nomatch-glob alt 3 is 24% precise;
  macos-no-timeout; zsh-function-name-is-alias; zsh-equals-word duplicates the general one).
- The catalogue the user described: cross-project search, one entry per job, promotion
  when a second project needs it. Waits on the surfacing study.
- `compound status` does not list scripts owed a decision; the pane does not show evidence.
- Study data files (labels with transcript excerpts) were committed locally in ce76596 by a
  broad `git add`; review them for private text before any push.
- Journeys general, guard, stop, capture were started after the changes; results below when in.

## Later the same day

- Probe confined after a review finding: it runs before a call is permitted, so it reads
  only the call's directory and the project and no environment (commits ee3e086, a later one
  for assignments and `cd`). Coverage of recorded failures fell from 49 of 55 to 41 of 56.
- Journeys after the changes: evidence 14 of 14, general 33 of 33 (its glob case now expects
  the stop before the call; its recurring case moved to macos-gnu-only-commands), guard and
  stop pass. **journey_capture fails**: the fix judge answered "none" in 5 of 5 runs here
  ("project-specific required flag; the error message states the fix") and in 1 of 2 runs
  on 579d351, the commit before this work, where the other run failed its `late` case. It
  was 10 of 10 on 2026-10-05. The judged trigger is not stable; not fixed yet.
- Measured a replacement for the judged trigger (recurrence_trigger.py, six weeks): a failed
  call whose error signature was met in an earlier session, then a pass of the same tool
  within six calls, once per signature. 834 signed failures, 330 signatures, 55 met in 2+
  sessions; 49 firings (3, 3, 8, 15, 20 a week), 31 in subagents; the fired signatures were
  met 373 more times afterwards. Read 36: about 26 are a tool, shell or harness rule a
  later session meets again (16 are harness refusals, e.g. "This agent is isolated in the
  worktree", "Blocked: sleep N"); about 8 are noise ("No such file or directory", a
  browser timeout). Not built.
- The user asked about arXiv 2610.12176 (Recursive Self-Improvement through Multi-Agent
  Self-Supervision); only its abstract page was read.
- Surfacing study still running.

## arXiv 2610.12176, read in full (PDF, 39 pages; text in the scratchpad)

Earlier in the session only the abstract page was read, and four "lessons" were given from
it. Read in full, the paper supports two of them, weakens one, and adds four.

Quotes (pdftotext of the PDF):
- "generation, evaluation, and revision share the same learned prior, meaning that
  self-feedback can reinforce rather than correct errors" (introduction).
- "optimizer capacity, rather than the evaluator capacity, can be a bottleneck in the speed
  of RSI"; "Replacing only the evaluator with GPT-5.5 yields less improvement than replacing
  both the evaluator and optimizer" (5.1).
- "The notation Leval(wi, wj) in configuration labels means a comparison of yi and yj, not a
  score of the prompt text" (E.1).
- "The workflow files at iterations 16 and 17 are byte-identical ... the first episode
  completes and wins all six external reporting judgments ... whereas the second halts
  under loop detection and loses all six" (E.3); edit size and verdict change: "|ρedit| ≤
  0.12" (5.1); flips at 0.22 to 0.40 in every edit-size bin (Table 10).
- "roles and instructions become less task-specific, while contracts and hops become more
  task-specific" (4.3).
- "The base already performs the coordination patterns observed after SFT"; under a bare
  prompt delegation is 1/110 for the base and 110/110 with the generic directive (G.2,
  Table 14).
- "The revision replaces force-driven motion with direct repositioning toward the goal ...
  This episode receives five favorable judgments out of six, despite changing the physical
  meaning of success" (G.3); "a supervised revision can contain faulty verification" (G.2).
- Terminal-Bench 2.0 37.5 → 35.2 and SWE-bench Verified 62.6 → 61.1 across the two cycles
  (Figure 3b): the gains are on the research benchmarks, not the coding ones.

Applied: the stop message and the learn skill now ask for a script lesson's body as a
contract (takes, gives back, the call, what was checked), and say that "it ran" is not the
check. Not applied: one retained entry per job with a challenger that must beat it when
run; repeated runs before a lesson is called better or worse; two levels of entry (bounded
tools, and recipes that call them in order).

## Built after the user said "build and change what you think is most promising"

- **A failure met before** (commit a1e1c22). `compound met` gives a failed call's error a
  signature and counts the other sessions that met it; the mod captures the fix of a
  failure met before with no model asked (`why: recurred`), quoting the passing call that
  resembles the failed one, or the last attempt, or at the stop. Rule refusals of the
  harness count. journey_capture went from 0 of 5 passing to 13 of 13 checks.
- **The index** (commit dce2a78), from the surfacing study (surfacing-study.md: 247 real
  sessions). `compound index`; the mod adds it at a session's first prompt, under 9,300
  characters, scripted lessons first, scripted lessons of other projects included;
  `compound show` reaches another project's lesson. journey_index 8 of 8: a session in one
  project ran the script another project recorded, unprompted by name. The first run of
  that journey failed because `show` could not find the other project's lesson; fixed.
- Not built from the surfacing study: the tool-time advisory (9 of 9 surfaced, but 4 of 10
  false activations on controls and it arrives after the hand work for "use the script"
  lessons).
- Repeated journey runs were started (index x4, capture x3, and one each of evidence,
  guard, stop, general, recall, unsettled, strengthen); results in the scratchpad's
  final.done when they finish.

## Leftovers a subagent reported
- A smoke session of the surfacing study wrote copies of five lessons to a directory under
  the home directory. The subagent's `rm` was refused by the permission system; it was
  left for the user to delete.
- Temporary directories from the study's docs sessions.

## Repeated journeys, and what they showed (all real sessions, haiku)

| Journey | Runs | Result |
|-|-|-|
| index | 6 before the trust rule, 1 on the final code | every run 8 of 8 (one run made while the rule was half changed got 4 of 8 and is superseded) |
| capture | 4 | every run 13 of 13 |
| evidence, guard, general, unsettled, strengthen | 1 each | all checks passed |
| recall | 2 | 21 of 23, then 23 of 23: the journey's filter dropped a call whose path held the word "compound" |
| stop | see below | |

The stop journey, check "after the refusal it settled the debt":
- prompt forbids recording, index shown (first wording): settled 1 of 5.
- same prompt, index switched off in a copy of the mod: settled 4 of 4.
- same prompt, index reworded to scope "quoted" to the list: settled 2 of 5.
- prompt also says "if your attempt to finish is refused, do what the refusal asks": 2 of 4.
- prompt no longer forbids recording: 5 of 5.
In the runs that did not settle the session said it left the lesson unrecorded because the
user had said not to record one. So: the refusal works; a session told by its user not to
record takes the user's word in about half the runs once the index is in its context, and
always complied without it. The debt stays open and is raised at the next session. The
journey's prompt no longer forbids recording. Not explained: why the index moves that
arbitration.

## Trust rule for what crosses projects (after four review findings)
A learn event carries `files` (SHA-256 by name) only for what the command itself wrote or
an earlier learn vouched for unchanged; an update's in-place edits count only over vouched
text; a file attached to itself counts for nothing; `.evidence.json` cannot be attached;
only a lesson whose programs have a recorded passing run crosses. No lesson recorded
before today crosses until it is removed and added again from a recorded run.

## Changes to the user's real store (~/.claude/compound), reversible
Old and new patterns are in notes/2026-10-11-usage-audit/guard_rewrites_applied.json.
- zsh-nomatch-glob: three measured patterns (98% of 179 matches failed) in place of the old
  one (48%), and `probe: unmatched-glob`. The general lesson that ships the probe is in this
  user's disabled.json, so without this the probe was off on this machine.
- macos-no-timeout: `(?<![\w=./-])timeout\s+(?:-\w+\s+\S+\s+)*\d` (recall 71% to 90%).
- zsh-function-name-is-alias: only the machine's own one-letter aliases (7 of 7, was 7 of 33).
- zsh-no-word-split-of-command-variable: a guard pattern, added when the stop hook asked.
- claude-mod-test-kit-shapes: two facts about the mod test kit.
`compound add` gained `--probe NAME`.

## Seen in the live store on the first day, and fixed
- An installed SDK's own command-line tool, run three times, was asked about at a stop: only a file in the
  project or a temporary directory is kept now, and older snapshots are held to that when read.
- A JUnit `<testsuite ... failures="0">` line became a failure signature: markup is passed over.
- Two `check` errors ("the 500 ms budget ran out with 19 guards not yet tested") at 21:52
  and 21:55 UTC in other projects, while this session ran batches of real sessions. The
  scanner itself takes 0.12 ms at the median and 60 ms at worst over 39,389 real commands,
  and a whole check on the real store 82 ms, so load is the likely cause; not confirmed.

## Where it stood at the end of 2026-10-11 (all journeys: real sessions, haiku)

Sweep of all 14 journeys on the code of that evening, then repeats of what failed:
| Journey | Result |
|-|-|
| index | 6 of 6 runs pass on the final wording (3 of 7 on the wording with the quoted-text statement next to the list; 7 of 7 on the two before it) |
| stop | 3 of 3 (plus 5 of 5 earlier on the neutral prompt) |
| capture | 5 of 5 across the evening |
| evidence | 3 of 3 |
| guard, recall, general, unsettled, strengthen, skills, repeat | pass |
| claims | pass once given an earlier meeting of the failure |
| error | 3 of 3 after its second prompt was given a candidate for the reuse check; it failed the same two checks on 579d351 |
| reuse | 12 of 14 in 3 of 3 runs: the judge names the lesson and not the earlier request from the prompt log. On 579d351 the same check passed in 1 of 4 runs. NOT FIXED: it is the reuse judge's calibration (its prompt says "nearly always the answer is an empty list"), and changing that prompt needs tests/journeys/measure_reuse.py, not a guess. |

Open:
- the reuse judge and earlier requests (above).
- a security review holds that the index's wording weakens the framing of quoted text; the
  no-authority statement is present, and its place (before the mod's instruction, not
  beside the list) is what the 6 of 6 against 3 of 7 rests on. The user was told.
- the branch's earlier commits hold the audit's raw rows: squash or filter before a push.
- directories left by a study subagent (above), for the user.
- lessons recorded before `learn` events carried `files` do not cross projects until
  recorded anew from a recorded run.
- `compound status` and the pane do not show scripts owed a decision or failures met.

## Final state, 2026-10-11 late evening

Every journey passes on the final code in one sweep (real sessions, haiku; compose on
sonnet): index 8/8, stop 12/12, capture 13/13, evidence 14/14, guard 22/22, recall 23/23,
general 33/33, unsettled 12/12, strengthen 10/10, claims 10/10, error 9/9, reuse 14/14,
skills 9/9, repeat 21/21, compose 40/40. ./run_tests.sh: 28 files OK. claude plugin test:
323 pass. claude plugin validate --strict passes.

What closed the items left open earlier:
- Reuse judge: the paragraph on earlier requests no longer says the answer is nearly always
  empty, gives one example of the same deliverable in other words, and says an inventory
  entry does not stand in for an earlier request. measure_reuse.py before: lessons 5 of 5,
  wrong 0, earlier requests 0 of 2. After, two runs: lessons 5 of 5 and 5 of 5, wrong 0 and
  0, earlier requests 2 of 2 and 1 of 2. journey_reuse: its earlier-request checks 5 of 5
  (one run failed on the session's own wording of its answer).
- Index wording: the statement that the list is quoted is made before the mod's
  instruction and again after the list. journey_index 8 of 8, journey_stop 3 of 3.
- Crossing projects: a lesson is recorded anew by `add --update` with its whole text and
  its script from a recorded run; an unvouched SKILL.md is then written anew (no line, no
  free text and no pattern of the old file kept), and the proof file is kept only when the
  log vouched for it.
- `status` and the pane list scripts owed a decision; `report` counts failures met,
  captures that came back, lessons recorded with a script, and sessions shown the index.
- The directories a study subagent left were deleted after the user said to fix what
  was surfaced.
- Branch history rewritten (git filter-branch over 579d351..HEAD): no commit of
  feat/evidence-episodes holds the audit's raw rows. The old commits are still reachable
  from backup/evidence-episodes-with-rows and refs/original: local only, not to be pushed.

Still true:
- No lesson recorded before `learn` events carried `files` crosses projects until recorded
  anew; on this machine that is one project-level lesson in another project.
- Two `check` budget errors at 21:52 and 21:55 UTC were not reproduced; the one command
  traced takes 0.1 ms to scan. Load from the journey batches is the likely cause, unconfirmed.
- Not merged to main and not pushed.

## Before landing on main, 2026-10-11

The repository is public, and the audit's reports and scripts were written from private
session transcripts. Before the branch goes to `main` they were redacted: other projects
are named by letter (project A to I), session and agent ids, transcript pointers and
paths are gone, and every excerpt of a session (typed prompts, the assistant's prose,
commands, lesson texts, decline reasons) is replaced by a description in other words.
Generic messages of public tools and the harness are kept. Counts, tables, rules and
conclusions are unchanged. Scripts that held hand-labelled rows now load them from an
untracked local file, and project-specific names in them come from the environment.

Every commit of the branch was rewritten so that each audit file holds its redacted text
from the commit that first adds it; no earlier version is reachable from the branch. The
raw rows stay ignored and on the machine. The pre-rewrite commits are still reachable
locally through the `backup/evidence-episodes-*` branches and `refs/original`; none of
them is to be pushed.
