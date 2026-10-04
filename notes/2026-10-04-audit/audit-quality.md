# compound audit: lesson quality, reuse quality, latency

Date 2026-10-04. Read-only audit. No repo file was edited and no store-writing CLI command was run.
Scripts that produced the numbers are beside this file (`bench.py`, `bench2.py`, `replay.py`,
`replay2.py`, `guards.py`, `silent.py`, `pairs.py`, `build.ts`, `runjudge.py`, `chk.py`). The pickled
transcript extract and the judge prompts/replies were deleted after use (they held transcript text).

## 0. What the real data can and cannot say

The mod was installed at `2026-10-04T02:50:08Z` (`~/.claude/compound/install.json`), about 15 hours
before this audit. The organic loop has almost no history, so most rates the brief asked for
cannot be computed from the log. To get evidence anyway I replayed the mod's real patterns and its
real judge prompts over the 2,338 local transcripts (45,185 Bash calls, 2026-08-27 to 2026-10-04).

Event log at the start of the audit (`python3` count over `~/.claude/compound/events.jsonl`):

| type | n | note |
|-|-|-|
| learn | 77 | all from one session `fee13f20`, 02:50:17-02:50:22Z, every lesson `origin: notes kept in CLAUDE.md` (a bulk migration, not captures) |
| reuse | 2 | |
| guard | 1 | in a journey's temp project (`tmp.ylSPuSdkBm`) |
| capture, recall, skip, remind, refuse, nudge, error | 0 | |

During the audit a sibling agent in session `09f47a44` added 3 `guard`, 1 `recall`, 1 `capture`
(86 lines at the end). Those five are the only organic guard/recall/capture events that exist.

Not computable (said plainly): capture -> learn vs skip vs unsettled rates, decline reasons,
ineffective-lesson rate, judge timeout rate. There is one capture, zero skips, zero errors.

Sessions the mod ran in (`ls ~/.claude/compound/claims`): 18. Reuse checks claimed: 13.
Reuse injections logged: 2. Of the 13 checked prompts, 12 are the same scripted prompt
"Review this change for security vulnerabilities." (first user message of each transcript); one
is a prompt the owner typed.

## 1. Measured numbers

### 1a. Latency (`python3 bench.py`, `python3 bench2.py`; medians, this Mac, anaconda python 3.9.13)

| call | median | budget (`hooks/render.ts:169`) |
|-|-|-|
| `python3 -c pass` | 25 ms | |
| `python3 -S -c pass` | 9 ms | |
| `compound check --guards` (the pre-call path, `register.ts:775`), real store, 32 lessons / 7 guards | 44-50 ms (two runs) | 1500 ms |
| same, `python3 -S bin/compound check --guards` | 35 ms | |
| `list --scripts --json` | 72 ms | 5000 ms at a prompt |
| `find --json` + 10 words (two surfer searches) | 124 ms | 5000 ms |
| `events --unsettled --session S --json` (after every tool call while something is owed) | 48 ms | 2000 ms |
| `status --json` | 121 ms | 15000 ms |

Scaling in a scratch `COMPOUND_HOME` (real lessons copied N times, synthetic log):

| store | check | list | events --unsettled |
|-|-|-|-|
| 200 lessons / 2,000 events | 60 ms | 77 ms | 67 ms |
| 1,000 / 20,000 | 122 ms | 216 ms | 187 ms |
| 3,000 / 100,000 | 262 ms | 683 ms | 691 ms |

Real mod timings from the log: guard `"ms":136`, `56`, `66`, `84` (includes the claim `sh`);
reuse `"ms":1119,"gather_ms":237,"judge_ms":880` and `"ms":1022,"gather_ms":220,"judge_ms":799`;
capture judge `"ms":2346`.

Verdict: latency is not a problem. Everything is 10-30x inside its budget and stays inside it at
100x the current store. `python3 -X importtime` shows 12 ms of the 25 ms interpreter start is
`site` (8 ms of it one editable-install `.pth` finder in this user's conda env); `-S` is safe for a
stdlib-only CLI and saves about 10 ms per call here. README.md:370 says "about 30 ms" per tool
call; I measured 44-50 ms for the CLI alone. Small, but the README number is optimistic on this machine.

### 1b. Guards replayed over history (`python3 replay2.py`, full outputs; `python3 guards.py`)

"True" = the call's own output carries the error the lesson describes.

| guard | Bash calls matched | true | precision | real occurrences missed by the pattern |
|-|-|-|-|-|
| `macos-no-timeout` `(^|[;&|]\s*)timeout\s+\d` | 62 | 52 | 84% | 12 more are caught once the anchor also allows a line start, `do`/`then`, `(` |
| `zsh-equals-word` `(^|[;&|]\s*)echo\s+=+` | 38 | 21 | 55% | 3 of 7 misses caught by the wider anchor |
| `zsh-function-name-is-alias` `(^|[;&|]\s*)[a-z]\(\)\s*\{` | 15 | 2 | 13% | catches 2 of 8 real failures; names used: q x7, p x2, r x2, n, k (not aliases) vs u, g, h, c (aliases) |
| `chain-commit-with-and` `;\s*git\s+commit\b` | 37 | not measurable by exit status (the harm is a silent wrong commit) | ? | |
| `gate-commit-on-pass-line` | 8 | not measurable | ? | |
| `plistlib-stdin-not-seekable` | 2 | 1 | | |
| `brew-doctor-exits-1` | 0 in 45,185 calls | | | |

Also matched: 6 non-Bash calls (5 `Write`, 1 `SubagentHandback`) whose JSON text contains the pattern.
I do not know why 17 `echo ===`-matched calls show no error; some are quoted remote commands.

### 1c. Failures the mod never sees (`python3 replay2.py`)

Recall and capture fire only on `ran.isError === true` (`hooks/register.ts:1242`).

| zsh error in the call's own output | reported failed | reported OK | hidden |
|-|-|-|-|
| `(eval):N: no matches found` | 55 | 357 | 87% |
| `(eval):N: command not found` | 25 | 111 | 82% |
| any `(eval):N:` shell error | 136 | 511 | 79% |

Of the 52 real `timeout` failures the guard matches, 47 were reported as success (`... | tail -5`).
Caveat: the count includes a few calls that only `cat` an earlier log holding the same text.

### 1d. The judge on real pairs (`pairs.py`, `build.ts`, `runjudge.py`)

24 random real fail -> next-success Bash pairs, the mod's own `fixPrompt`/`recallPrompt` built by
importing `hooks/judge.ts`, the 32 real user lessons as inventory, haiku via an isolated
`claude -p`, parsed with the mod's `parseFix`/`parseRecall`. Labels are mine.

Fix judge: 10 FIX, 4 KNOWN, 10 NONE.
- 5 of the 10 FIX are fixtures of the package's own demos/journeys (`./build.sh` x4, `tac`); correct but synthetic.
- Of the 5 organic FIX: 2 sound (node `Cannot find module 'playwright'` -> `NODE_PATH`; control characters in a command), 2 marginal (git add of ignored paths; an exploratory import), 1 wrong: evidence `"Permission for this action was denied by the Claude Code auto mode classifier. Reason: Blocked by classifier."`
- KNOWN: 3 of 4 right. Wrong: `agent-worktree-check-base` for the harness refusal "This agent is isolated in the worktree ... this command is too complex to verify".

Recall judge, same 24 failures: named a lesson for 9. Right 5 (incl. `heredoc-ends-and-chain`, a
good catch), wrong 3 (`chain-commit-with-and` on a command with no `; git commit`;
`agent-worktree-check-base` as above; `zsh-nomatch-glob` on an error with no "no matches found").
Targeted set of 22 more failures: 14 of 14 that a lesson really describes were named correctly;
of 8 that no lesson describes, 4 got one anyway (`heredoc-ends-and-chain` x2 for
`fatal: Needed a single revision`, `gate-commit-on-pass-line` and `macos-no-timeout` for plain 2-minute timeouts).
Pooled: about 7 of 27 failures with no applicable lesson were given an unrelated one. Small n.

Failure kinds among 1,750 historical failures of judged tools (`python3` over the extract):
1,338 `Exit code N`; 412 (24%) are not command failures: tool-use validation errors and hook
blocks 149, worktree-isolation refusals 50, permission/classifier/user rejections 34, other 179.

Not verified: `claude -p` adds Claude Code's system prompt, `$.model.complete` does not, so these
replies approximate the mod's. Wall times from this replay are process starts and are not used.

### 1e. Reuse on the real prompts

2 injections, 4 things named, 0 relevant by my reading:
- Scripted security-review prompt -> `"lessons":["patch-scripts-match-current-text"]` (a lesson about Python str.replace patch scripts).
- Owner's prompt "first create a new release (v0.4) ... then do a careful (ultrawork) audit of the package" -> `"lessons":["speckit-execute"],"prompts":["b587c98c-...:1","f58c372b-...:3"]`. The two earlier requests are from 2026-09-06 and 2026-09-03 ("The project is up and running locally, but it is not yet fully functional ...", "let's take a step back before continuing. can you help me understand the current approach ..."): neither asked for a release or an audit, and both predate the rewrite that deleted that code.
- The candidate words were `["release","current","version","careful","ultrawork","audit","package","come","few","awesome"]`: the first ten non-stopwords in order (`judge.ts:72-80`), no weighting.

### 1f. The 77 lessons

`python3` summary: 32 user, 45 project, 7 guards, 1 with a script. Body 23-120 words, median 50.
All 77 descriptions start "Use when". 20 of 77 bodies quote an error text. Highest token-Jaccard
between any two is 0.19: no near-duplicates. They are specific and actionable; they were written
by a session from curated notes, so they say nothing about what the capture path will produce.

Defects found:
- `zsh-function-name-is-alias`: pattern matches every one-letter function, 13% precision (1b). Body carries session residue: "Write a small helper script (python3 pg.py URL regex)".
- `macos-no-timeout`: body ends "BSD sed likewise rejects GNU forms such as `sed -1`", which is not a GNU form; description "or using GNU-only coreutils flags" widens the trigger beyond the pattern.
- `gate-commit-on-pass-line` (user level) carries a CDL-bibliography paragraph ("For bibcheck, write the output to a file ...").
- `brew-doctor-exits-1`: a guard for a command that appears 0 times in 45k calls.
- `zsh-nomatch-glob`: the most frequent lesson-covered failure (412 calls, 206 of them `--include=*.ext`) has no guard.
- `sed-substitute-needs-g`: general knowledge; low value.

`compound find` (`chk` probes, `COMPOUND_SURFER=/nonexistent`): the right lesson was in the top 4
for 9 of 10 queries. Miss: `find heredocs chained` does not return `heredoc-ends-and-chain`
(exact tokens, no stemming, `bin/compound:1700-1702`). `find "(eval):1: ==== not found"` ranks
`history-surfer` and `macos-no-timeout` above `zsh-equals-word` (raw overlap, no IDF). Adequate at 77 lessons.

## 2. Bugs

B1. Guard anchors miss multi-line commands. `(^|[;&|]\s*)` is tested with `re.search` and no
`re.M` (`bin/compound:1750`), and `skills/learn/SKILL.md:119,154,176` teach that exact anchor.
`python3 chk.py`: `'timeout 5 ls'` -> `['macos-no-timeout']`; `'cd /tmp\ntimeout 5 ls'` -> `[]`;
`'for f in a b; do timeout 5 ls $f; done'` -> `[]`; `'x=$(timeout 5 ls)'` -> `[]`;
`'cd /tmp\necho ====='` -> `[]`.

B2. Guards fire on text that is not a command. `chk.py`: `Write {"content":"Run the tests; git commit -m done"}`,
`SubagentHandback {"message":"I ran pytest; git commit was not run."}`, `Agent {"prompt":"run the suite; git commit only if green"}`
and `Bash grep -n '; git commit' docs/guide.md` all -> `['chain-commit-with-and']`. `guarded()`
is every tool outside `QUIET` (`hooks/render.ts:61`).

B3. A guard that did its job is counted as failing. Real sequence: `17:02:15Z guard zsh-equals-word`,
then `17:02:26Z recall zsh-equals-word ... "at":"failure","guard":true,"ineffective":false`
(the same call re-sent, a deliberate repro). One more and the lesson is "ineffective" with the text
"the pattern did not catch the call that failed: the call ran, and failed, without being stopped"
(`hooks/render.ts:353`), which would be false. Read from code and one real pair; not driven to the second recall.

B4. Harness refusals are captured as fixes. The only organic capture, id `7cd2f808`: error
"...Do not work around the check by splitting, scripting, or re-issuing the removal through another tool or shell ... What was flagged: Dangerous rm operation detected: '/Users/jmanning/claude-skill-compounder/lessons/*'",
judge evidence "Dangerous rm operation detected: ...". Session `09f47a44` now owes a lesson for it. I left it alone.

Not a bug in code, but a wrong number: README.md:370 "about 30 ms" (measured 44-50 ms).

## 3. Proposals, ranked

### P1. Drop non-command failures before the judge (S)
(a) B4 above; replay pair 9 (classifier denial judged FIX); pair 6 (worktree refusal matched to an unrelated lesson by both judges); 24% of historical failures are of this kind.
(b) In `onFailure`, before any model call, skip a failure whose text does not start with `Exit code` or that matches a short list (`<tool_use_error>`, "denied by the Claude Code auto mode classifier", "requires explicit approval", "This agent is isolated in the worktree", "doesn't want to proceed"). Add the same exclusion as a line under B in `fixPrompt`.
(c) S. `hooks/render.ts` (a pure predicate + test), `hooks/register.ts:877`, `hooks/judge.ts:175-179`, `docs/design.md`.
(d) Not verified: whether the engine reports each of these as `isError` or as `deny` to the hook; the capture event shows at least the rm check arrives as `isError`.

### P2. Make guards match commands, and only commands (S-M)
(a) B1, B2; 12 real `timeout` failures and 3 `echo ===` failures missed; 6 non-Bash matches in history.
(b) Compile patterns with `re.M`; change the taught anchor to `(?m)(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)`; test Bash commands by default and other tools only when a lesson says so (a `tools:` field, or default Bash-only); have `compound add --match` print what the pattern does on the captured failing and fixed calls and refuse a pattern that matches the fixed call.
(c) S for `re.M` + SKILL.md; M with the tool scope. `bin/compound` (`_match_inline`, `cmd_add`), `skills/learn/SKILL.md`, `docs/design.md`, `tests/test_check_find.py`, and the 3 anchored user lessons.
(d) Whether `re.M` changes any existing pattern's meaning: the 7 real ones use `^` only in that anchor and `$` once (`brew doctor\s*$`), which would then match at a line end; I think that is the wanted meaning but did not test it.

### P3. See failures that exit 0 (M)
(a) 1c: 79% of zsh shell errors and 47 of 52 real `timeout` failures are reported as success, so recall and capture never run for the failures the store is mostly about. It happened to me twice in this audit (`no matches found: .../world-*`, exit 0).
(b) After a successful Bash call, test the output with one regex for a shell error (`^\(eval\):\d+: `, `command not found`, `no matches found`); on a hit treat it as a failure for recall (and hold it for capture). No model call unless the regex hits.
(c) M. `hooks/render.ts` (predicate), `hooks/register.ts:1240-1245`, tests, `docs/design.md`, README cost table.
(d) The `(eval):N:` prefix is how this machine's zsh under Claude Code reports; bash and other shells print differently. False-hit rate on outputs that merely quote such text is not measured.

### P4. Evidence gate and correct accounting for recall (M)
(a) 1d: about a quarter of failures with no applicable lesson got one named. `parseRecall` accepts a bare name (`judge.ts:265-271`) while `parseFix` requires a quote found in the error (`judge.ts:275-281`). The judge sees only name + 220 characters of description (`judge.ts:14,29-32`), and only 20 of 77 bodies/descriptions carry the error text. A wrong recall injects a note, counts toward "ineffective" (limit 2) and drops the failure from capture (`register.ts:900`). B3 is the same accounting problem.
(b) Ask for `{"name":...,"evidence":"<exact quote from the call or error>"}` and verify it with `quoted()`; after a hit, confirm once against the lesson body the mod already fetches with `show` (`register.ts:843`); do not count a recall when a `guard` event for the same lesson and session precedes it; ask `compound add` for the error text and store it (an `error:` field shown to the judge).
(c) M. `hooks/judge.ts`, `hooks/register.ts` (`onFailure`, `recurred`), `bin/compound` (`recalls_since`, `cmd_add`), `skills/learn/SKILL.md`, tests, `docs/design.md`.
(d) Whether the confirm step removes the false recalls: not tested. Real recall latency: no data (one event, no `ms` field on `recall`).

### P5. Log every verdict, not only the positive ones (S)
(a) 11 of 13 reuse checks, every held failure and every NONE left no event, so precision, cost and judge latency cannot be measured from the log; this audit had to rebuild them from transcripts. `recall` events carry no `ms`.
(b) One compact `judge` event (or counters in `status`): moment, verdict, `ms`, reason, prompt digest; add `ms` to `recall`; `compound status` then prints per-lesson "guarded N, of which corrected M" by comparing the refused call with the next call of that tool.
(c) S. `hooks/register.ts`, `bin/compound` (event types, `tally`, status), `docs/design.md`, `tests/test_docs.py` will require the doc change.
(d) Log growth: `events --unsettled` reads the whole log (691 ms at 100k events), so this needs the log bounded or the read made incremental; I did not design that.

### P6. Reuse: fewer, better candidates (S-M)
(a) 1e: 0 of 4 named things relevant; 12 of 13 checks spent on one scripted prompt; candidate words are the first ten non-stopwords ("come", "few", "awesome").
(b) Weight candidate words by rarity in the prompt log (surfer already has it) instead of position; add "these come few careful current" class words to `STOPWORDS`; require each named earlier request to come back with the shared deliverable in a few words, and drop it otherwise; skip the check when the same prompt head was judged "nothing" recently.
(c) S for stopwords + memo; M for IDF. `hooks/judge.ts:55-80,118-122`, `hooks/register.ts:reuseJudged`, `bin/compound` (`prompt_hits`).
(d) n = 2 injections. I cannot say the judge is generally imprecise from two events; `tests/journeys/measure_reuse.py` exists for this and I did not run it.

### P7. Quality gate in `compound add` (M)
(a) `cmd_add` checks the slug, an empty body and an exact name only (`bin/compound:1375-1501`); duplicate detection is step 3 of the skill, i.e. left to the model. Residue and scope defects in 1f got through.
(b) At `add`: run the `find` scoring on name + description + body and refuse (exit 2, naming the lesson and `--update`) above a threshold unless `--new`; with `--settles`, require the body to contain a token of the captured failing command or error; warn on session residue (scratchpad paths, session ids) and on a user-level body naming one project.
(c) M. `bin/compound`, `skills/learn/SKILL.md`, tests, `docs/design.md`.
(d) No near-duplicate exists in the real store (max Jaccard 0.19), so the need is argued from the code, not observed. Threshold untested.

### P8. Small items (S each)
- Tighten three real lessons: alias pattern to the user's actual alias names; drop the `sed -1` sentence; move the bibcheck paragraph out of the user-level lesson. These are store edits, for the owner to make.
- A guard for `zsh-nomatch-glob`'s commonest form, unquoted `--include=*.ext` (206 of 412 occurrences).
- Stemming (strip plural/-ing) and IDF in `cmd_find` (`bin/compound:1700-1707`); adequate today at 77 lessons.
- `python3 -S` when the mod spawns the CLI (about 10 ms of 45 here); correct README.md:370.
- Lesson retirement: no evidence yet. 31 of 33 rows in `compound status` read "never used" after 15 hours, which says nothing.

## 4. What I do not know

- How captured lessons (as opposed to migrated ones) read: none exists.
- Skip/decline behaviour, ineffective-lesson handling in practice, judge timeouts: zero events.
- Why 17 calls matching `echo ===` produced no zsh error.
- Whether guard refusals lead to corrected calls: 4 organic refusals, 3 by an agent deliberately reproducing the failures.
