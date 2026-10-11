# Episode study: which solved problems leave something a later session would reuse

2026-10-11. Read-only study of `~/.claude/projects` transcripts, the lesson stores and
`~/.claude/compound/events.jsonl`. Nothing here is implemented and nothing was committed.
Scripts are the `ep_*.py` files beside this note. The labelled set (172 episodes, one
label and a one-line reason each) points into private transcripts and is not published.
Projects other than this repository are called project A to project I; passages from
sessions are described, not quoted.

## Answer in brief

1. **Red→green on the work is not worth a trigger.** A check that fails, files edited, the
   same check passes: 666 candidates in 5.5 weeks (188 a week in the last three). In a
   random sample of 26, 1 left something reusable, 18 were the work itself, 7 were not
   episodes. 250 of the 666 are a test written first on purpose. Of 1,337 pytest node ids
   seen failing, 33 (2.5%) failed again in another session on another day.
2. **What separates reusable from one-off is where the fix landed, not how hard it was.**
   Inside the red→green family (65 real episodes read): when the red was on a hosted check,
   or no file was edited between red and green, 22 of 31 were reusable; otherwise 4 of 34.
   Three or more reds before green: 0 of 10 reusable. In the multi-attempt shape, when a
   failure named the machine or a tool: 12 of 12 reusable; when every failure was the
   session's own assertion: 2 of 5.
3. **Triggers worth shipping** (all computed from calls the mod already sees):
   T1 a tool, shell, machine or harness failure followed by a pass, first meeting of its
   signature only; T2 three or more failed calls with different texts, then a pass;
   T3a a hosted check red after a local green; T3b a check red then green with no file
   edited and an install or config call in between; T4 the user's typed `/compound:learn`.
   Together 30 firings a week in the last three weeks, in 13% of typed turns.
4. **About a quarter to a third of those firings would end in a justified "nothing to
   keep"** (25% pooling every labelled firing, 33% using only the held-out sample). The
   same figure for red→green is about 95%.
5. **The session's own judgement of "one-off" is wrong when the problem has happened
   before, and it cannot know that.** Two real captures were declined for reasons that the
   transcripts contradict (section 6). The evidence bundle has to carry the count of
   earlier meetings.

## 1. Data and method

| | |
|-|-|
| Transcripts parsed | 2,981 files (2,395 sessions, 586 subagent files), 2026-09-02 to 2026-10-11; nothing older is on disk |
| Left out | 1,534 transcript files under temporary directories (the package's own journeys, judge probes, demos) |
| Tool calls in what remains | about 53,000, of which 36,000 in subagents; 424 typed prompts in 130 working sessions |
| By project | project A 26,887 calls, project B 8,282, claude-skill-compounder 3,542, project C 2,427, project D 2,286, the rest smaller |
| Positive set | 42 lessons recorded by working sessions since 10-04 (54 `learn` events less updates and the one import session) |

Method: `ep_parse.py` joins every tool call to its result. `ep_detect.py` finds candidates
of seven shapes by code. `ep_show.py` renders a candidate from the transcript for reading.
I drew stratified random samples (fixed seeds, a cap per project), read each episode and
labelled it reusable-procedure, reusable-script, reusable-fact, one-off-fix or
not-an-episode with a one-line reason. After the rules in section 5 were written I drew a
second, held-out sample of 29 rule firings and labelled those too.

Detector shapes:

| Code | Shape | Definition used |
|-|-|-|
| RG | red→green with edits | a check command red, one or more file edits, the same check green |
| RGE | red→green without edits | the same, no file edited, the passing call not the failing call word for word (or an install/config call between) |
| MA | several approaches | three or more failed calls of one tool inside twelve calls, two or more different texts, then a pass |
| ENV | tool or machine failure | a failed call whose error names the machine, the shell, a tool or the harness, then a pass within six calls |
| DX | diagnostic chain | five or more look-only calls with no edit, ending in prose that names a cause |
| UC | user correction | a typed prompt matching correction words (no, don't, instead, again, always, ...) |
| SCR | repeated script | a script written in the session and run successfully three or more times |

A check command is recognised only in command position (a `sed -n` call that prints lines
of a file named like a checker reads a file and runs nothing); here-document bodies and
quoted text are removed first. Both mistakes were in the first version of the detector and
produced 7 of the first 26 RG candidates.

## 2. Per shape: how often, and what share is reusable

Counts are detector candidates. "Per week" is the mean of ISO weeks 39 to 41 (Sep 21 to
Oct 11), which hold 80% of the tool calls.

| Shape | Corpus | Per week | Main / sub | Read | Reusable | One-off | Not an episode | Reusable among real episodes |
|-|-|-|-|-|-|-|-|-|
| RG, random | 666 | 188 | 264 / 402 | 26 | 1 | 18 | 7 | 5% |
| RG, hard subset (3+ reds, a cause in prose, or 10+ look-only calls) | 123 of the 416 unplanned | | | 12 | 3 | 6 | 3 | 33% |
| RG, a cause named in prose | 28 | | | 10 | 2 | 6 | 2 | 25% |
| RG/RGE on a hosted check | 16 | 5 | all main | 8 | 7 | 1 | 0 | 88% |
| RGE, random | 87 | 26 | 29 / 58 | 20 | 8 | 4 | 8 | 67% |
| MA, random | 31 | 9 | 7 / 24 | 12 | 9 | 2 | 1 | 82% |
| ENV, random (5 harness, 10 machine) | 698 | 199 | 160 / 538 | 15 | 10 | 2 | 3 | 83% |
| DX, random | 33 | 8 | 24 / 9 | 12 | 3 | 5 | 4 | 38% |
| UC, random | 84 | 25 | 84 / 0 | 16 | 5 | 1 | 10 | 83% |
| SCR, random | 402 | 123 | 47 / 355 | 12 | 3 | 9 | 0 | 25% |

Notes on the rows:

- **RG.** The one reusable episode was not in the diff. The session committed after a red
  test and afterwards noted that a here-document inside the commit chain had let a commit
  through with stale outputs. The hard subset did not help: the three reusable ones there
  were all hosted or cross-worktree reds (below), and a long struggle on the work was
  still the work.
- **Hosted check.** Seven of eight, and the same episodes account for six of the owner's
  42 lessons (section 4). Examples: a first hosted run green on macOS and red on Ubuntu
  from one test, because the Ubuntu runner has `gh` on its minimal `PATH` and `gh` wrote
  its own state files under the sandbox home; hosted runners with no git user name or
  email, which the local machine's configuration had hidden; a hosted run installing a
  newer ruff than the local one.
- **RGE.** The eight not-an-episode cases are three deliberate baselines (old code
  restored to show a test fails without the fix) and five detector artifacts. The real
  ones are environment facts: a `ModuleNotFoundError: No module named` for a package a
  project's checker script needs, `error: unrecognized arguments: -n` from pytest, and a
  hosted run that listed a directory a sparse local worktree had left out (a fact the
  session had already recorded as a lesson).
- **MA.** The two one-off cases are assertions of the session's own build script on its own
  data. The nine reusable are tool and machine facts: vhs writes nothing when a wait times
  out; a virtual environment whose `pyvenv.cfg` is empty; weasyprint needs
  `DYLD_FALLBACK_LIBRARY_PATH` set; the harness cannot create an agent worktree outside a
  git repository; a macOS screenshot file name holds a narrow no-break space and has to be
  matched with a glob.
- **ENV.** Ten of fifteen, but they are seven distinct facts: four of the ten are the
  same harness refusal. Without deduplication this shape is 199 firings a week.
- **DX.** The prose marker (the session naming a cause or a root cause) fires on defects
  in the work and on code reviews. The three reusable rows are one procedure caught by
  accident: a fresh agent ran a notebook in Google Colab through Playwright three times in
  one day (73, 32 and 87 events), each working the upload dialog out again.
- **UC.** Word matching finds instructions and design answers. Three of the five reusable
  ones are the user's own `/compound:learn`. Of the 38 typed prompts with a stronger
  marker (always, never, in general, again, ...), 10 are `/compound:learn` (one of them
  twice, in a forked session) and about 8 of the other 28 state something general (for
  example, that a thing should be described once and linked to from elsewhere, or that
  everything has to pass locally first).
- **SCR.** Three runs do not make a script reusable: nine of twelve were one-task helpers
  with throwaway names. See section 3 for the part of this shape the data does support.

### One project?

Project A holds half of all calls. Reusable share of real episodes, that project
against every other:

| Family | Project A | Other projects |
|-|-|-|
| RG (all three RG samples) | 2 of 9 | 4 of 27 |
| Hosted check and RGE | 7 of 10 | 13 of 19 |
| MA | 4 of 7 | 10 of 10 |
| ENV | 5 of 5 | 9 of 13 |

The ordering of shapes is the same on both sides. The volume is not: 57 of the 112
firings of the shipped rules are in project A, 32 of them in one session (a fleet of
several hundred research subagents).

## 3. Cross-session recurrence: where a lesson was owed

`ep_recurrence.py` folds each failed call's error line into a signature. Of 1,182 failed
calls with a signature, 761 (64%) belong to 79 signatures met in two or more parent
sessions. `ep_recur_families.py` names the families and checks the lesson store:

| Family | Failed calls | Sessions | Projects | First to last | Lesson |
|-|-|-|-|-|-|
| "This agent is isolated in the worktree ... Refusing to run it" | 276 | 4 | 3 | 09-11 to 10-09 | none |
| "Blocked: sleep N followed by: ..." | 77 | 14 | 8 | 09-11 to 10-09 | none quotes it (`wait-loop-needs-deadline`, 10-10, covers the habit) |
| zsh "no matches found" | 59 | 24 | 11 | 09-04 to 10-11 | `zsh-nomatch-glob` (10-03); 28 calls in 16 sessions after it |
| HTTP 429 Too Many Requests | 43 | 5 | 4 | 09-11 to 10-11 | none |
| auto mode classifier denied or gave no verdict | 29 | 10 | 6 | 09-23 to 10-11 | none (not learnable when it is an outage) |
| Playwright MCP "outside allowed roots" | 25 | 9 | 5 | 09-02 to 10-10 | `playwright-mcp-output-dir` (10-03, a guard since 10-10) |
| Read "exceeds maximum allowed tokens" | 22 | 9 | 2 | 09-11 to 10-02 | none (the message states the remedy) |
| "No module named ..." | 21 | 9 | 6 | 09-04 to 10-08 | none per module |
| "can't be checked before it runs" / "cannot be statically resolved" | 12 | 12 | 4 | 10-04 to 10-10 | `rm-glob-after-cd-denied` (10-04); 9 calls after it |
| zsh "parse error near" | 9 | 5 | 4 | 09-24 to 10-11 | none |
| "command not found: timeout" | 9 | 5 | 5 | 09-09 to 10-10 | `macos-no-timeout` (10-03); 1 call after it |
| "Subagents should return findings as text, not write report files" | 7 | 4 | 3 | 09-11 to 10-11 | none |

Every family on this list is a tool, shell, machine or harness fact. None is a failing
test of the work. Six families that a lesson could address and that have none (the
isolation refusal, the sleep block, 429, Read size, parse error, report files) cover 434
failed calls.

Problems solved twice, found while reading, each a direct case of a lesson owed:

| Problem | First | Again | What happened the second time |
|-|-|-|-|
| zsh reads a colon after a variable as a modifier | 09-09, project E: the session noticed zsh had taken the text after the colon as a modifier and that braces were needed | 10-08, project A: a `git show` of a revision held in a variable failed the same way | captured; lesson `zsh-colon-after-variable-is-a-modifier` written |
| zsh does not split a command held in a variable | 09-25, project F: the session recognised it as a trap already in its notes | 10-08, project A | captured; lesson `zsh-no-word-split-of-command-variable` written |
| macOS screenshot names hold U+202F | 09-23, project I: a copy of a screenshot by its typed name found no such file | 10-06, project H: a file-not-found error on a screenshot name | named in a `compound skip` reason for another lesson; never recorded |
| a project's checker script needs its own environment | 09-14, project E: two missing packages, one after the other | 10-05, project D: a third missing package | capture declined on the ground that recreating the environment was the obvious fix |
| a venv under a temp directory is reaped | 09-14, project A: the session moved the venv somewhere stable because the temp directory would keep doing it | 10-05, project D: a scratch venv had been cleared by the temp cleanup | same declined capture |
| `pytest -n` without pytest-xdist | 10-07, project A; lesson recorded at project level | 10-09, project B: `error: unrecognized arguments: -n` | not recalled: the lesson belongs to the other project |
| a test green locally and red on the hosted runner | 10-01 project A (git identity) | 10-04 this repository (gh state files), 10-06 and 10-07 project A, 10-09 project B (twice), 10-10 project G | `linux-container-before-first-ci` on 10-06, after the third |

**Scripts.** By file name, 165 script names were written in two or more sessions, but the
contents match (3-token shingle overlap of 0.30 or more) for 4 of them: the shared names
are generic ones for a probe, a runner or a patch. By content regardless of name
(`ep_script_clusters.py`), 73 of 399 run-three-times scripts fall in 18 clusters written
by two or more agents, 11 of them by three or more, and every one of the 14 largest is
inside a single parent session: twelve agents each wrote the same batch-append helper,
nine the same text checker, five the same query against a public search service. So "a
procedure repeated" is supported inside a fan-out session, where the remedy is to hand
later agents the helper the first one wrote.

Across sessions the data shows three cases. In project B on 10-08 a session rewrote a
pipeline script because the old one had not survived. The Colab procedure (section 2). And
in project A, 15 agents in 4 parent sessions between 09-27 and 10-08 each wrote a short
script (30 lines or fewer, 16 scripts) that runs pytest with an environment variable the
suite needs, taken from a cache in the main checkout. Their texts differ, so the content
clustering does not link them: what recurred was the fact that the suite needs that
variable and where to get it, not a script.

### Do the labels agree with recurrence?

For the 135 labelled RG, RGE, MA and ENV windows (`ep_label_checks.py`): 18 hold a
specific failure signature that recurs in another session, and 11 of those I had labelled
reusable (4 not-an-episode, 3 one-off). Of windows I labelled one-off, 3 of 39 hold a
recurring signature; of those labelled reusable, 11 of 40. The agreement is in the right
direction and it is weak evidence: most windows hold no failed call with a specific
signature at all (red checks usually exit 0 through a pipe).

## 4. The positive set: what produced the 42 lessons

What stood in the event log just before each `learn`:

| Last compound event before the learn | Lessons |
|-|-|
| a `refuse` with reason `nudge` (the end-of-turn question) | 23 |
| a `recall` (not necessarily its cause) | 9 |
| the user's typed `/compound:learn` within the previous twelve events | 5 |
| `settles` a capture | 5 |

The episode behind each lesson, classified by reading the transcript around its
`compound add` call and the lesson's own text:

| Episode shape | Lessons | Which |
|-|-|-|
| The user said it (a typed `/compound:learn`, a correction, or a design task the user set) | 15 | status-needs-fresh-reading, keychain-before-no-credentials, ask-decisions-with-the-question-tool, american-english-spelling, commit-pinned-checks-dry-run-first, shorten-the-loop-before-iterating, end-of-turn-inflight-check, audit-before-the-next-fix, one about shipping a fix that was shown to work, a project-level lesson about checking every page of a documentation site, and the five guards one subagent wrote on 10-10 |
| A check red in one place and green in another (hosted runner, full suite, another worktree, the committed copy) | 6 | urlopen-keeps-first-proxies, linux-container-before-first-ci, http-server-backlog-resets-on-linux, and three project-level lessons: hosted tests read the committed code, a type check one project's suite enforces, and a sparse worktree that differs from the hosted checkout |
| One mis-written command or a harness refusal (today's capture) | 6 | rm-glob-after-cd-denied, script-named-like-stdlib-module, zsh-no-word-split-of-command-variable, zsh-colon-after-variable-is-a-modifier, venv-without-pip-use-uv, and a project-level lesson about pytest without pytest-xdist |
| Several approaches at one tool before one worked | 4 | claude-mod-test-kit-shapes, gh-actions-full-job-log, claude-mod-real-session-tmux, rtd-resync-after-moved-tag |
| A procedure or script built and used in the session | 5 | claude-mod-real-terminal-check, reformat-prove-output-unchanged, and three project-level lessons about a canary run and a replay benchmark |
| An incident noticed with no failing call | 5 | openpyxl-dump-exact-values, worktree-branch-switch-kills-running-suite, split-a-metric-by-cause-before-designing, and two project-level lessons about merging in a scratch worktree and fast-forwarding an agent's worktree first |
| Edits that did not turn a red check green | 1 | a project-level lesson about trims that did not reduce a page overflow |

Plain red→green with edits accounts for one lesson of 42, and that lesson is about why the
edits were not working. Two things in this set limit what any call-based trigger can see:
five lessons have no failing call at all, and `gh-actions-full-job-log` was four
approaches of which none was marked as an error (two forms of `gh run view` with a log
option returned a log cut off partway, and the API's log endpoint called without the
needed flag wrote only a notice about terminal escape sequences).

## 5. The trigger rules

`ep_triggers.py` runs these over the corpus.

| Rule | Fires when | Per week | Reusable, first samples | Reusable, held out |
|-|-|-|-|-|
| T1 | a failed call whose error line names the machine, shell, a tool or the harness (the classes in `T1CLASS`), then a pass of the same tool within six calls; **only the first meeting of the signature**, later meetings are recalls | 8.3 | ENV sample 10 of 15, before the class and first-meeting filters | 4 of 9 as first tested; the 4 that the final class filter keeps are the 4 reusable |
| T2 | three or more failed calls of one tool inside twelve calls, two or more different texts, then a pass; not when every failure is a check's own red | 9.0 | 9 of 12 | 5 of 6 |
| T3a | a hosted check (`gh run view`, `gh pr checks`, `gh run watch`) reports a failure after this session saw a local test runner pass | 5.3 | 10 of 11 | 2 of 4 |
| T3b | a check red then green, no file edited in between, at most 15 events apart, an install or config call in between, neither call a baseline (`git show REV:file >`, `git stash`, a `.bak` restore) | 4.3 (15.7 without the install/config condition) | every labelled firing: 6 of 8 with the condition, 2 of 7 without | 3 of 7, drawn before the condition was added |
| T4 | the user types `/compound:learn` | 3.3 | all 10 became lessons | |

Not rules: RG; DX; word-matched corrections; any script run three times.
T5 (a helper written a second time, by content) is real inside fan-out sessions (18
clusters) but 1 of 3 held out was reusable; it is better served by a snapshot than by a
debt (section 7).

Three corrections to the current design that these rules imply:

- **Harness refusals belong in T1.** Section 4 of `docs/design.md` says "a call that was
  refused" is not a fix. The most repeated failure in the corpus is a refusal: 276 calls,
  three projects, a month, no lesson. Each subagent starts fresh, writes a here-document
  that names git, is refused, and rewrites it with the Write tool.
- **`is_error` is not enough.** `pytest -n` through `| tail` exits 0. T3 reads the check's
  output for its red; T1 and T2 as measured here undercount for the same reason.
- **Three or more reds is a counter-signal** (0 of 10 reusable), so "hard episodes" in the
  earlier miner (`>=3 red runs first`) is the wrong filter.

### Cost

| | Now (events.jsonl, 10-04 to 10-11) | Proposed, weeks 39 to 41 |
|-|-|-|
| Model calls for capture | 276 fix-judge calls (10-04 to 10-11, 19:56 UTC), 12 said fix | none at trigger time; one at a stop that has a queue: 17.7 typed turns a week hold a firing, of about 130 |
| Debts raised | 13 captures, 8 settled by skip | 30 firings a week before the stop-time judge |
| Share ending in "nothing to keep" | 262 of 276 judge calls said none; 8 of 13 captures were skipped (audit note) | 25% pooled over all labelled firings, 33% on held-out firings only |
| Firings in one turn | | median 1, 90th percentile 5, maximum 11 |

Half of the firings (55 of 112) are in subagents. A subagent cannot settle a debt (one
`skip` in the log gives as its reason that the subagent was read-only and editing the
lesson store was outside its scope), so its firings have to queue for the parent's stop.

The flood risk is the fan-out session: 32 firings in one session. The first-meeting filter
is what keeps T1 at 38 firings for the corpus instead of 448; T2 has no such filter and
18 of its 31 firings are in one week of that session. T2 should take the same signature
filter (untested here).

## 6. What to snapshot

What each reusable episode needed in order to be written down without guessing, from the
five worked examples below and the 66 reusable labels:

| Evidence | Why | Needed by |
|-|-|-|
| The failing call or calls word for word, with exit status and the first and last 2 KB of output | the error text is the lesson's trigger | all |
| The passing call word for word | it is the lesson's body | all |
| The calls between, one line each, edits and install/config calls marked | shows what changed; already built for the fix judge (`changed`, calls between) | all |
| The assistant's own sentences between the first failure and the pass | the cause is stated there and nowhere else (for example, that a venv's `pyvenv.cfg` was empty) | T2, T3 |
| Where each reading was taken | hosted run id and job name for the red, the local command for the green; or the two interpreters, the two worktrees | T3 |
| `git diff --stat` between red and green, and at most 200 lines of the diff | to show that tracked files did not change (T3b), or to carry the one test-side fix (T3a) | T3 |
| The signature and **how often it was met before**: sessions, projects, dates | changes the verdict; see below | T1, T2 |
| A script's bytes, sha256, run count and command lines at its latest passing run | the scratch directory goes with the session | scripts |

The full diff of the work is not on the list. In 22 of the 26 reusable red→green episodes
the red was hosted or no file was edited; the diff either does not exist or is one line in
a test helper.

The count of earlier meetings is the piece no session can supply. On 10-05 a session
settled a capture with a `compound skip` whose reason was that a scratch venv had been
cleared by the temp cleanup and that recreating it was the obvious fix, not a reusable
lesson. The same loss had cost another session four failed calls on 09-14, and the same
missing dependencies of the same checker script had been worked out in a third project
that day. On 10-06 a session wrote the U+202F fact into a skip reason and moved on;
another project had met it on 09-23. A stop-time judge given "met in 2 sessions, 2
projects, first 09-14" would not have accepted either skip.

### Five lessons written from transcript text only

For each of five episodes a lesson was drafted using only text present in the transcript:
the failing calls, the passing call and the session's own sentences between them. The
drafts quote private sessions and are not reproduced; what follows is the kind of episode
and the kind of lesson each gave.

1. **T2, project A, 2026-09-14.** A virtual environment under a temp directory failed
   twice with different import errors for packages it had installed; the session found its
   marker file empty and files missing, and rebuilt the environment inside the repository.
   The lesson: when a venv under a temp directory reports installed packages as missing,
   check its `pyvenv.cfg`, and build the environment somewhere the system does not clean.
2. **T3a, this repository, 2026-10-04.** A hosted run was red on Ubuntu and green on
   macOS from one test that snapshots a sandbox home; a three-line change to a test helper
   turned it green. The lesson: `gh` writes state outside its configuration directory, so
   a sandbox has to set the XDG state, data and cache directories as well. Evidence: the
   small diff and the two hosted readings.
3. **T3b, project E, 2026-09-14, met again in project D on 2026-10-05.** A project's
   checker script failed on one missing package after another and passed after installs,
   with no file edited; a later session in another project met a further missing package.
   The lesson: give that script its own environment with the full list of packages before
   the first run. It carries a count of earlier meetings: 2 sessions, 2 projects.
4. **T1 (harness), project A, a subagent, 2026-10-05.** A worktree-isolated agent tried to
   create a script with a here-document and was refused because the command was too
   complex to verify; writing the same content with the Write tool and running it as one
   plain command passed. The lesson: a worktree-isolated agent creates scripts with the
   Write tool and runs git as its own plain command. Met before: 276 failed calls, 4
   sessions, 3 projects, 2026-09-11 to 2026-10-09.
5. **T1 (machine), project I, 2026-09-23, met again in project H on 2026-10-06.** A copy
   of a macOS screenshot by its typed name found no such file; a glob over the name
   passed. The lesson: the name holds a narrow no-break space (U+202F) before the AM or PM
   mark, so match it with a glob. Met before: 2 sessions, 2 projects.

## 7. Red team

**Are the labels my taste?** One reader, no second rater. Three checks that do not depend
on me: (a) recurrence, section 3: weak agreement, and the recurrence families are all of
the kind I labelled reusable; (b) the owner's 42 lessons, section 4: 1 from red→green with
edits, 6 from differential reds, 6 from single-command failures, 4 from multi-attempt, 15
from the user's own words, which is the same ordering as the labelled shares; (c) failing
tests do not come back: 33 of 1,337 node ids. What the checks cannot settle is the
boundary inside "reusable-fact": I counted a missing command-line tool and the fact that
grep on this machine is a different implementation as reusable; a stricter reader would
not, and ENV and RGE shares would fall by a few rows. The held-out sample came out lower
than the first samples for T3a (2 of 4 against 10 of 11) and T1 (4 of 9 before the class
filter), which is what tuning on the first samples predicts.

**Is one project driving it?** The volume, yes (project A: 51% of firings, one
session 29%). The ranking of shapes, no (section 2 table). The script-cluster finding is
one session (the content clusters) and one project (the environment-variable wrapper) and
should not be generalised.

**Would it flood sessions?** Unfiltered, yes: ENV alone is 199 a week and RG 188. With the
rules as written, 13% of typed turns hold a firing and the median such turn holds one. The
tail is the fan-out session (11 firings in one turn). Two things keep the cost down and
both are assumptions about the implementation, not measurements: firings queue with their
snapshot and cost no model call until the stop, and the stop asks once for the whole
queue.

**What the detectors cannot see.** Failures that exit 0 (the `gh` log episode, `pytest -n`
through a pipe); incidents with no failing call (5 of 42 lessons); corrections the user
makes in ordinary words (about 8 in 5.5 weeks). The end-of-turn question produced 23 of the
42 lessons and nothing here replaces it.

**Uncertain.**
- Rates are from 5.5 weeks of one user; week 39 alone holds 42% of the tool calls.
- T1's final class filter and T3b's install/config condition were chosen after reading the
  held-out sample; neither has been tested on fresh data. T3a's hosted-check rule rests on
  15 labelled firings that are about 10 distinct episodes.
- "Reusable" means a later session would plausibly use it. Only the recurrence table shows
  actual repetition, and `zsh-nomatch-glob` shows a recorded lesson does not by itself stop
  it (28 failed calls in 16 sessions after it was written).
- Whether a subagent's firing can be settled by its parent without the subagent's context
  is untested.
- Transcripts older than 2026-09-02 are gone, so nothing can be said about recurrence over
  months.

## 8. Reproducing

```bash
cd notes/2026-10-11-usage-audit
export EP_CACHE=/some/scratch/dir            # holds sessions.pkl, about 200 MB
python3 ep_parse.py "$EP_CACHE"              # every transcript to a normalised event list
python3 ep_detect.py ep_candidates.jsonl     # candidates of the seven shapes
python3 ep_show.py ep_candidates.jsonl --sample MA 12 --seed 20261011 --per-project 5
python3 ep_show.py ep_candidates.jsonl --id <candidate id>
python3 ep_recurrence.py 75; python3 ep_recur_families.py; python3 ep_script_clusters.py
python3 ep_triggers.py                       # the rules, their volume and their cost
python3 ep_label_checks.py; python3 ep_positive_recall.py; python3 ep_stats.py
```

`ep_common.py` defaults `EP_CACHE` to the scratch directory of the session that wrote
this, which will not exist later. A candidate id is shape, session, agent and first event
index, so it is stable only for one version of `ep_detect.py`. `ep_candidates.jsonl` is
the detector output the tables were computed from. Seeds: 20261011 for the first samples,
77 for the targeted RG and second RGE samples, 99 for the held-out sample.
