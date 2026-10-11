# 2026-10-11: usage audit across all projects and levels

Asked: why the compounder is not working in practice; how to make triggers reliable,
automate instead of remind, and make skills come from solutions actually found.
Status: audit done, design proposed to the user, nothing implemented. Branch at the time:
fix/recall-parse-markdown-reply (unrelated; these notes are uncommitted).

## Sources
- ~/.claude/compound/events.jsonl: 1,629 events, 432 session ids, 2026-10-04 to 10-11.
- 121 lessons: 61 user, 54 across 10 projects, 6 general.
- ~/.claude/projects transcripts changed since 10-04: 1,117 files, 93 with >= 10 tool calls.
  Counted by notes/2026-10-11-usage-audit/mine_transcripts.py (regex heuristics, a lower bound).

## Numbers
Capture (failed call, then a working call of the same tool):
- fix judge asked 261 times: fix 12, known 2, none 247. 13 capture events.
- Those settled by 5 learns and 8 skips (the reasons given: a one-off, or a slip in a scratch script).
- design.md section 4 rules out "a test that failed on the work" and "an edit to the work
  itself", so a solution reached by editing code is outside the trigger by definition.

Where lessons came from (129 learn events, 15 sessions):
- 77 from one import session (origin "notes kept in CLAUDE.md").
- 38 written in sessions since. Event just before a learn: nudge refusal 20, recall 10,
  capture 4. 22 nudges in all (25 calls a turn, 1800 s cooldown shared by every session).

What a lesson holds:
- 0 of 121 have a fenced code block. 4 have an attached file. Median body 65 words.
- 1 `skill` event. Every learn has kind "lesson".

How lessons were met again:
- 77 of 121 were never surfaced by any trigger (reuse named, recall, guard, use); 75 never offered.
- reuse judge: 464 verdicts, named 41, nothing 347, not-substantial 76.
- recall: 144, of which zsh-nomatch-glob 71. Its guard stopped 14 calls. 142 of 144 recalls came
  at the failure, 2 at the fix. 37 flagged ineffective, 12 strengthen refusals.
- use: 6 events.
- In this audit session 3 guards fired, all on text inside a here-document (a grep glob that
  did match, the word pytest in a Python string, sphinx-build in a regex). 0 of 3 applied.

What sessions did that nothing recorded (transcripts):
- 42 scripts in a scratch directory ran successfully 3 or more times, then went with the
  session: a validation script 69 runs (project A); a gallery build 14, a release sequence
  12, a pipeline check 9 and a spelling converter 8 (project B); an audit script 6 (project G).
- One project-level lesson in project B tells the session to write a scratch script; the
  script it describes was written and run 9 to 12 times and is not attached.
- 29 episodes where a check failed, files were edited and the same check passed (8 sessions).
- 184 of 4,961 Bash calls returned an error.

## Diagnosis
1. The unit captured is one mis-written command. The unit wanted is a solved problem with its
   working code. The trigger cannot see the second, so lessons are shell trivia or prose
   written from recall at a nudge.
2. Nothing takes the working artifact. `--attach` exists and depends on the model choosing it.
3. A lesson without a match reaches a session only through a typed prompt of 80+ characters
   that a model judges substantial. Nothing surfaces it mid-task. Lessons are not native skills.
4. Guards are regexes written by hand, tested against the whole command including
   here-document bodies: they miss the real failure and stop unrelated calls.

## Proposed (not built)
A. Episode triggers worked out by the mod from calls it already sees: (1) a script written in
   the session that ran successfully N times; (2) a check that failed, edits, same check passed.
B. Snapshot evidence at that moment through the CLI (bytes of the script, the command, exit
   status, sha256, session and call id), before the scratch directory goes.
C. `compound add --from-evidence ID`: the attachment is the snapshot. A script or skill lesson
   whose attachment has no evidence record of a passing run is refused.
D. A `verify` command kept with the lesson and rerun by the CLI.
E. Triggers derived from the evidence (the command and file names that ran) instead of an
   authored regex; a match must hit the recorded failing calls and miss the recorded fixes.
F. Strip here-document bodies and quoted strings before a guard pattern is tested.
G. Replace the open nudge with a specific one naming the evidence.

## Open
- Thresholds for A, and whether evidence-backed lessons become native skills automatically.
- Waiting on the user's go-ahead and choice of first slice.
