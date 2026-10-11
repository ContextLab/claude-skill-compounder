# Threshold study: which written-then-run scripts are worth snapshotting

2026-10-11. Question: the mod will snapshot scripts a session writes and then runs. Which
observable rule picks the ones worth keeping and discards probes?

Every number below is printed by a script in this directory; `ts_output.txt` holds the output
of the run this report was written from. Nothing was committed. Read-only on `~/.claude` and
on every repository.

## Answer

Snapshot a script when all of these hold:

1. the session created the file (Write, or `cat > path <<EOF`), and the file is not inside a
   git work tree, is not a test file, and was not run through pytest / `bun test`;
2. it has **two successful runs**; and
3. **the two runs had different arguments, or the script reads its arguments**
   (`sys.argv`, `argparse`, `$1`, `$@`, `process.argv`, `getopts`, `click`).

Optional second clause, measured on 19 scripts only: a script written by the main agent (not
a subagent) with three successful runs, whatever its arguments.

The number of successful runs alone does not separate tools from probes. Whether the script
was called on more than one input does.

| | hits in 39 days | hand-read | reusable tool (K) | tool or session-bound helper (K+B) | probe (P) |
|-|-|-|-|-|-|
| rule hits | 498 of 2,565 | 59 | 34 (58%) | 54 (92%) | 5 (8%; Wilson 95% 4..18%) |
| rule misses | 2,067 | 65 | 6 (9%) | 12 (18%) | 53 (82%) |

Recall of K, from the blind stratified sample: 62%. Proxy label "a near-copy was written
again later": precision 21.7%, recall 57.8% (108 of 187), against a base rate of 7.3%.

Expected yield: 498 hits in 39 days is 89 a week on average, but the weeks were 1, 22, 2, 301,
64, 108. Without the one fan-out session, 191 hits, about 34 a week. Counting near-copies once,
315 distinct jobs, first seen per week 1, 21, 2, 131, 64, 96. Expected false positives: about
1 hit in 10 is a probe; about 4 in 10 are not reusable as they stand (K is 58 to 60%).

## Data

- `ts_extract.py`: 2,986 transcript files (588 subagent), 2026-09-02 to 2026-10-11. Nothing
  older is on disk. 43,898 Bash/Write/Edit/Agent calls kept, 244 duplicates from resumed
  sessions dropped.
- Of 2,386 sessions, 2,294 are SDK sessions (the mod's own judge calls, journeys, review
  hooks) and 57 are interactive sessions in temporary directories. **35 sessions are real
  interactive work under the home directory.** The study uses those, minus the session that
  ran it: 26 sessions with a created script, 16 projects.
- `ts_shell.py` + `ts_episodes.py`: one record per (session, script file). Variables assigned
  earlier in the command or session are expanded (`$S`, `${S}`, `$_`), `cd` is followed, and
  here-document bodies are never read as commands. A run is OK when `is_error` is false, the
  call was not interrupted, and the output has no traceback / "command not found" / "No such
  file" (a pipe to `tail` hides the exit status).
- 3,148 created scripts. 473 never run. 2,774 were touched only by subagents.

Target population (`ts_rules.py`): scratch or `/tmp`, not a checkout of the repository, not a
test file: **2,565 scripts**, 2,310 run at least once. Left out: 583 scripts in repositories
or worktrees, 478 of them in git history today.

## Ground truth

Built in `ts_labels.py`, from events outside the writing agent's own runs. Sizes in the
target population:

| label | how | n |
|-|-|-|
| redo | a script whose vocabulary overlaps this one's by Jaccard >= .5 (identifiers of 4+ chars, minus tokens in >10% of scripts), same project, created later by another agent or session | 187 |
| redo, other session | same, different session | 2 |
| redone, line-level | difflib ratio >= .6 over lines | 16 |
| reused | run by an agent other than the writer (117) or by a later session (1) | 118 |
| named | basename in a later Agent/SendMessage brief (166) or a later prompt from the user (0) | 166 |
| to_repo | copied to the home directory (25), or its blob (7) or a near-copy (9) is in a repository | 32 |
| KEEP | any of the above | 466 (18.2%) |

Line-level similarity found almost nothing because the same job is re-coded differently each
time: 62 agents each wrote their own script for the same lookup by identifier against one
public service, and 42 wrote one for a second service. Hand check of the vocabulary threshold on 16 pairs: 4 of 4 the same job at >= .55, 2 to 3 of 4 at .4 to .55,
1 of 4 at .3 to .4, 0 to 1 of 4 at .2 to .3.

**The proxies are weak, and I do not rest the answer on them.** In the blind sample, proxy
KEEP was no better than chance at finding a reusable tool (9 of 22 with the label were K or B,
19 of 48 without). "Named in a brief" picks up generated-data scripts (a build script holding one
batch's entries); "run by another agent" picks up patches replayed in a worktree. Only redo
agrees with reading: weighted K precision 78%.

## Hand reading

124 scripts read in three samples (`ts_sample.py`, `ts_sample2.py`, `ts_sample3.py`; verdicts
in `ts_hand.py`). K = reusable tool: takes input, or a re-runnable check or build not bound to
one datum. B = general logic bound to one batch, worktree or temp directory. P = probe, repro,
one-off patcher, generated data.

Sample 1, 70 scripts, stratified, read blind (no run counts, labels or stratum shown):

| stratum | size | read | K | B | P |
|-|-|-|-|-|-|
| arguments varied between OK runs | 440 | 20 | 13 | 5 | 2 |
| >= 3 OK runs, same arguments | 115 | 15 | 1 | 1 | 13 |
| 2 OK runs, same arguments | 228 | 10 | 2 | 3 | 5 |
| 1 OK run | 1,425 | 20 | 2 | 0 | 18 |
| no OK run | 357 | 5 | 1 | 0 | 4 |

Estimated tools in the target population: 553 (21.6%).

Sample 2, not blind to bucket: 12 more with varied arguments (K 8, B 4, P 0); 14 with the same
arguments and OK runs in two or more user turns (K 0, B 1, P 13: eleven were numbered
string-replacement patch scripts replayed by a second agent).

Sample 3, outside project A: 22 rule hits (K 10, B 11, P 1); 10 with >= 3 OK runs on the
same arguments and no argv (K 3, B 3, P 4; the 3 K were all written by the main agent).

What the hits were: lookups by identifier against public services, fetch-and-cache helpers,
pytest wrappers for a worktree, contact-sheet and frame extractors, scanners that take a
root. What the misses were: numbered string-replacement patch scripts, build and generator
files holding one batch's data, probe and debug scripts, UI drivers for one bug,
simulations.

## Each candidate signal

Stratum-weighted hand estimates (`ts_hand.py`), then the proxy label redo (`ts_rules.py`,
signals from the writing agent only). Hits count every run in the session. Base rates: K 21.6%,
redo 7.3%.

| rule | hits | K precision | K recall | redo precision | redo recall |
|-|-|-|-|-|-|
| arguments varied between OK runs | 440 | 66% | 52% | 23.6% | 52.9% |
| reads its arguments, >= 2 OK runs | 484 | 67% | 62% | 21.9% | 54.0% |
| **either of the two (shipped)** | 498 | 65% | 62% | 21.7% (all runs) | 57.8% |
| >= 2 OK runs | 783 | 44% | 62% | 14.9% | 57.2% |
| >= 3 OK runs | 422 | 44% | 29% | 17.1% | 35.3% |
| >= 3 OK runs, same arguments | 115 | 7% | 1% | 3.9% | 2.1% |
| failure before first success | 172 | 21% | 5% | 13.9% | 12.3% |
| rewritten after a run | 305 | 21% | 14% | 9.7% | 12.3% |
| >= 40 lines, >= 1 OK run | 687 | 1% | 2% | 0.1% | 0.5% |
| OK runs in >= 2 user turns | 57 | (0 of 14 read) | | 7.0% | 2.1% |
| first to last OK run >= 1 h | 41 | not read | | 0.0% | 0.0% |
| reads its arguments, >= 1 OK run | 790 | 56% | 87% | 18.7% | 78.6% |

- Run count: adds nothing once argument variation is known. Three or more runs on the same
  arguments is the probe bucket.
- Failure before first success, and rewrites: at the base rate.
- Length: a negative signal. All 19 K in sample 1 were under 40 lines. Tools are short.
- More than one turn, and time span: leaks. With every run in the session counted, "OK in >= 2
  turns" scores 66.0% on KEEP and "span >= 1 h" 73.3%; counting only the writer's runs they
  fall to 15.8% and 14.6%. The lift was other agents running the file, which is the label.
- Scratch versus repository: defines the population, it does not rank within it.
- Probe-like names (`probe`, `chk`, `patch`, one or two letters): no use; the most-repeated
  tools had two-letter names.

## Red team

**One session drives the proxy result.** One session (project A, 241 subagents)
holds 912 of the 2,565 target scripts, 307 of the 498 hits and 185 of the 187 redo labels.
Without it (`ts_rules.py --drop <session id prefix>`), no rule beats the base rate on any proxy: KEEP
9.6% base, 9.3% for >= 2 OK runs, 9.0% for varied arguments. Outside that session the rule is
supported only by the 25 hits read by hand in other projects (K 52%, K+B 96%, P 4%) against
33 misses (K 15%).

**The hand verdict leans on the same feature as the static half of the rule.** I called a
script a tool largely when it took input, which is what "reads its arguments" detects: of 30
scripts in sample 1 that read their arguments 19 were K, of 40 that do not 0 were. The
behavioural half (arguments actually differed) was not visible when I read, and scores the
same 66%. One reader, no second rater.

**A simpler rule.** ">= 2 OK runs" has the same recall at 44% precision. "Reads its arguments,
>= 1 OK run" has recall 87% at 56%, but rests on 5 scripts read in the one-run stratum (2 K);
I would not ship it on that.

**Tests and source files.** The shipped rule fires on 29 of 209 non-test scripts created in
repositories that are in git today, on 41 of 87 in-repository scripts not in git (all under
one directory of project A, untracked at the time), on 27 of 271 test files and
on 2 of 16 scratch checkouts. A run-count rule would be far worse: >= 3 OK runs fires on 167
of the 271 test files. Exclude with: path inside a git work tree (`git rev-parse` from the
file's directory), test names (`test_*`, `*_test.*`, `*.test.*`, `conftest`, a `tests/`
directory), and runs through pytest or `bun test`. Without the fan-out session, 143 of 153
in-repository scripts are in git, so skipping the work tree loses little.

**The scripts the audit named.** The rule fires on a validation script (both copies), a
gallery build script, a pipeline verification script (one of two copies), a text-normalising
script and an audit script. It is silent on a release sequence script (6 OK runs, no
arguments), and also on a figure audit script (48 OK runs in 15 turns) and a progress script
(10 in 6 turns). All three were written by the main agent. Of the
19 main-agent scripts with >= 3 OK runs, the rule fires on 13; reading one line of each, about
12 look like tools. That is the case for the optional clause, and it is 19 scripts.

## Uncertain

- 39 days, 26 sessions, 16 projects. The weekly yield ranged from 1 to 301.
- 474 of the 498 hits were written by subagents. If the mod's hooks do not see subagent tool
  calls, the yield is 24 in 39 days, about 4 a week. I did not test this.
- 20 of the 54 good hits are B: bound to a worktree or scratch path. A snapshot keeps them;
  turning one into a lesson needs the path lifted out.
- Input through stdin is invisible: one script was run 19 times with a different here-document
  each time and counts as "same arguments".
- Parser artefacts: a gallery build script shows 6 argument sets because of `( ... &)`; a loop
  variable counts as one set. The mod should compare arguments from its own parse.
- to_repo has 32 members; the rule finds 7 of them. Scripts that end in the repository are
  longer (median 46 lines), mostly written by the main agent (19 of the 32) and run once or
  never (23 of the 32). No rule here predicts them.
- Whether a snapshotted tool would have been reused is not measured. redo shows the job
  recurred, not that the later agent would have taken the earlier script.

## Reproduce

    C=<a directory outside the repository>   # holds script bodies and prompts
    python3 ts_extract.py $C && python3 ts_episodes.py $C && python3 ts_labels.py $C
    python3 ts_rules.py $C; python3 ts_rules.py $C --drop <session id prefix> --section rules
    python3 ts_sample.py $C; python3 ts_sample2.py $C; python3 ts_sample3.py $C
    python3 ts_hand.py $C; python3 ts_checks.py $C

Transcripts keep growing, so counts drift on a rerun, and the hand verdicts in `ts_hand.py`
are keyed to the samples drawn on 2026-10-11.
