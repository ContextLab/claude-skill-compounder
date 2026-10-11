# Guard study: what text a guard pattern is tested against, and how a pattern is validated

2026-10-11. Part of the usage audit (`notes/2026-10-11-usage-audit.md`, diagnosis 4 and proposals E and F).
Nothing in `bin/compound` or `hooks/` was changed. Nothing is committed.

## Answer

1. **Text.** Test a pattern against the command with every here-document body and comment
   taken out, and count a match only when it **begins in command text**, that is, outside a
   quoted string. A match may run on into a quoted argument (`sed -i 's/a/b/' f`); it may not
   start in one. A string or body handed to a shell (`bash -c '...'`, `eval "..."`,
   `bash <<EOF`) is command text. The function is `guard_search` in
   `notes/2026-10-11-usage-audit/guard_text.py`.
2. **That rule alone is a small part of the problem.** Over the seven lessons whose failure
   prints its own error, precision goes from 48.3% (348 of 720) to 53.5% (344 of 643) and
   recall from 75.0% to 74.1%. Of the 372 false positives of the raw text, 73 go; 299 begin in
   command text and stay, because the pattern is loose, not the text.
3. **The patterns are the larger part.** Three rewrites, measured on the same corpus, take
   those seven lessons to 96.0% precision (286 of 298) at 61.6% recall (286 of 464). Two of the
   three only work under the rule of point 1: "a URL with `?`" matches 2,625 calls on the raw
   text (10 failed) and 7 calls under the rule (7 failed).
4. **The 72 recalls of `zsh-nomatch-glob` are mostly not a text problem and not a pattern
   problem.** 57 of the 72 came after the guard had already refused once in that session, and
   43 of those 57 calls match the pattern as it stands. A guard refuses once a session; after
   that it is silent. 23 of the 72 the pattern does not match.
5. **Validation rule.** "Must match the recorded failing calls, must not match the recorded
   working calls" would have had nothing to test for any of the 19 guards when it was
   written (no guard lesson settles a capture). Tried afterwards on the transcripts: the
   first half discriminates and is worth making a refusal; the second half either rejects
   nothing (working call = the fix) or everything (working call = every call that ran), so it
   has to be a measured rate, not a must.

## Data

```
calls with a result: 38887; in real projects (under the owner's home directory): 36328; of those ran (not stopped, refused, interrupted or sent to the background): 34955
outcomes, all projects: {'ok': 36874, 'error': 1654, 'refused': 196, 'stopped': 163}
events: 1671 2026-10-04T02:50:17Z 2026-10-11T19:53:21Z guard lessons for Bash: 19
```

- Corpus: `guard_corpus.py` reads every `tool_use` of Bash and its `tool_result` from every
  transcript under `~/.claude/projects` (2,981 files, subagent transcripts included), keyed on
  the tool-use id. First call 2026-09-02, last 2026-10-11.
- **Real projects only.** 2,559 calls sit in project folders under temporary and
  scratch directories: journeys, demos and tests that trigger
  guards on purpose (92 of the 163 stopped calls are there). The tables use the 36,328 calls
  of the projects under the owner's home directory. With every project the totals move by about two points and
  the order of the candidates does not change (A 50.7%, P 55.8%).
- **A call counts when it ran.** A call stopped by a guard, refused a permission or
  interrupted has no outcome; a call sent to the background shows its output in a later call.
  34,955 calls ran.
- Lessons: 19 Bash guards (16 user, 3 general). `playwright-mcp-output-dir` names other tools
  with `match-tools` and is not a Bash guard. No project lesson has a `match`.
- **Truncation.** `check` tests the first 20,000 characters; 79 of 38,887 commands are longer.
  The event log keeps 4,000 characters of a text: 7 of 66 `guard` texts and 3 of 144 `recall`
  calls were cut there when counted, and for 3 stops the matching text lies beyond the cut (all three begin
  with a here-document, and are counted as here-document stops below).
- The event log runs into the afternoon of 2026-10-11 and includes the audit's own sessions. Two stops are
  this study's (a `for path in ...` loop in a Python here-document, and `git push` in the
  here-document that wrote `guard_text.py`); both were sent again unchanged.

## Candidates

| | text | 
|-|-|
| A | the raw command (today) |
| B | here-document bodies removed |
| C | B, and the inside of `'...'` removed |
| D | C, and the inside of `"..."` removed (a `$( )` inside it kept) |
| E | each simple command on its own: split at `;` `&` `|` `(` `)` and newlines in command text, pattern tested on each part |
| P | proposed: here-document bodies and comments removed, the match must begin in command text |

All six come from one scanner (`classify` in `guard_text.py`), which labels every character
of a command as command text, single-quoted, double-quoted, here-document body or comment.

## Precision and recall, lessons whose failure prints its own error

True positive: the pattern matches and the result has the lesson's error on a line that
starts with the shell's prefix (`(eval):N:`, `zsh:`; for sed, `sed: N: "...": <message>`).
False positive: it matches and the call ran without that error. Missed: the error is there
and the pattern does not match. "Failures in corpus" is TP + missed.

| lesson | failures in corpus | candidate | matched | TP | FP | precision | missed | recall |
|-|-|-|-|-|-|-|-|-|
| macos-no-timeout | 58 | A | 44 | 41 | 3 | 93% | 17 | 71% |
| macos-no-timeout | 58 | B | 42 | 41 | 1 | 98% | 17 | 71% |
| macos-no-timeout | 58 | C | 42 | 41 | 1 | 98% | 17 | 71% |
| macos-no-timeout | 58 | D | 42 | 41 | 1 | 98% | 17 | 71% |
| macos-no-timeout | 58 | E | 44 | 43 | 1 | 98% | 15 | 74% |
| macos-no-timeout | 58 | P | 42 | 41 | 1 | 98% | 17 | 71% |
| sed-in-place-bsd | 15 | A | 12 | 8 | 4 | 67% | 7 | 53% |
| sed-in-place-bsd | 15 | B | 9 | 8 | 1 | 89% | 7 | 53% |
| sed-in-place-bsd | 15 | C | 1 | 1 | 0 | 100% | 14 | 7% |
| sed-in-place-bsd | 15 | D | 0 | 0 | 0 | - | 15 | 0% |
| sed-in-place-bsd | 15 | E | 9 | 8 | 1 | 89% | 7 | 53% |
| sed-in-place-bsd | 15 | P | 9 | 8 | 1 | 89% | 7 | 53% |
| zsh-equals-not-found | 27 | A | 29 | 23 | 6 | 79% | 4 | 85% |
| zsh-equals-not-found | 27 | B | 25 | 22 | 3 | 88% | 5 | 81% |
| zsh-equals-not-found | 27 | C | 25 | 22 | 3 | 88% | 5 | 81% |
| zsh-equals-not-found | 27 | D | 25 | 22 | 3 | 88% | 5 | 81% |
| zsh-equals-not-found | 27 | E | 25 | 22 | 3 | 88% | 5 | 81% |
| zsh-equals-not-found | 27 | P | 25 | 22 | 3 | 88% | 5 | 81% |
| zsh-equals-word | 27 | A | 32 | 22 | 10 | 69% | 5 | 81% |
| zsh-equals-word | 27 | B | 29 | 21 | 8 | 72% | 6 | 78% |
| zsh-equals-word | 27 | C | 23 | 21 | 2 | 91% | 6 | 78% |
| zsh-equals-word | 27 | D | 23 | 21 | 2 | 91% | 6 | 78% |
| zsh-equals-word | 27 | E | 30 | 21 | 9 | 70% | 6 | 78% |
| zsh-equals-word | 27 | P | 23 | 21 | 2 | 91% | 6 | 78% |
| zsh-function-name-is-alias | 7 | A | 34 | 7 | 27 | 21% | 0 | 100% |
| zsh-function-name-is-alias | 7 | B | 33 | 7 | 26 | 21% | 0 | 100% |
| zsh-function-name-is-alias | 7 | C | 33 | 7 | 26 | 21% | 0 | 100% |
| zsh-function-name-is-alias | 7 | D | 33 | 7 | 26 | 21% | 0 | 100% |
| zsh-function-name-is-alias | 7 | E | 0 | 0 | 0 | - | 7 | 0% |
| zsh-function-name-is-alias | 7 | P | 33 | 7 | 26 | 21% | 0 | 100% |
| zsh-nomatch-glob | 327 | A | 524 | 246 | 278 | 47% | 81 | 75% |
| zsh-nomatch-glob | 327 | B | 516 | 245 | 271 | 47% | 82 | 75% |
| zsh-nomatch-glob | 327 | C | 513 | 245 | 268 | 48% | 82 | 75% |
| zsh-nomatch-glob | 327 | D | 510 | 245 | 265 | 48% | 82 | 75% |
| zsh-nomatch-glob | 327 | E | 516 | 245 | 271 | 47% | 82 | 75% |
| zsh-nomatch-glob | 327 | P | 510 | 245 | 265 | 48% | 82 | 75% |
| zsh-status-path-variables | 3 | A | 45 | 1 | 44 | 2% | 2 | 33% |
| zsh-status-path-variables | 3 | B | 3 | 0 | 3 | 0% | 3 | 0% |
| zsh-status-path-variables | 3 | C | 3 | 0 | 3 | 0% | 3 | 0% |
| zsh-status-path-variables | 3 | D | 1 | 0 | 1 | 0% | 3 | 0% |
| zsh-status-path-variables | 3 | E | 3 | 0 | 3 | 0% | 3 | 0% |
| zsh-status-path-variables | 3 | P | 1 | 0 | 1 | 0% | 3 | 0% |

Totals, and whether one lesson drives them:

| subset | candidate | matched | TP | FP | precision | missed | recall |
|-|-|-|-|-|-|-|-|
| all | A | 720 | 348 | 372 | 48.3% | 116 | 75.0% |
| all | B | 657 | 344 | 313 | 52.4% | 120 | 74.1% |
| all | C | 640 | 337 | 303 | 52.7% | 127 | 72.6% |
| all | D | 634 | 336 | 298 | 53.0% | 128 | 72.4% |
| all | E | 627 | 339 | 288 | 54.1% | 125 | 73.1% |
| all | P | 643 | 344 | 299 | 53.5% | 120 | 74.1% |
| without zsh-nomatch-glob | A | 196 | 102 | 94 | 52.0% | 35 | 74.5% |
| without zsh-nomatch-glob | B | 141 | 99 | 42 | 70.2% | 38 | 72.3% |
| without zsh-nomatch-glob | C | 127 | 92 | 35 | 72.4% | 45 | 67.2% |
| without zsh-nomatch-glob | D | 124 | 91 | 33 | 73.4% | 46 | 66.4% |
| without zsh-nomatch-glob | E | 111 | 94 | 17 | 84.7% | 43 | 68.6% |
| without zsh-nomatch-glob | P | 133 | 99 | 34 | 74.4% | 38 | 72.3% |
| without zsh-status-path-variables | A | 675 | 347 | 328 | 51.4% | 114 | 75.3% |
| without zsh-status-path-variables | B | 654 | 344 | 310 | 52.6% | 117 | 74.6% |
| without zsh-status-path-variables | C | 637 | 337 | 300 | 52.9% | 124 | 73.1% |
| without zsh-status-path-variables | D | 633 | 336 | 297 | 53.1% | 125 | 72.9% |
| without zsh-status-path-variables | E | 624 | 339 | 285 | 54.3% | 122 | 73.5% |
| without zsh-status-path-variables | P | 642 | 344 | 298 | 53.6% | 117 | 74.6% |
| without either | A | 151 | 101 | 50 | 66.9% | 33 | 75.4% |
| without either | B | 138 | 99 | 39 | 71.7% | 35 | 73.9% |
| without either | C | 124 | 92 | 32 | 74.2% | 42 | 68.7% |
| without either | D | 123 | 91 | 32 | 74.0% | 43 | 67.9% |
| without either | E | 108 | 94 | 14 | 87.0% | 40 | 70.1% |
| without either | P | 132 | 99 | 33 | 75.0% | 35 | 73.9% |
| before 2026-10-04, no guard existed (25779 calls) | A | 476 | 246 | 230 | 51.7% | 77 | 76.2% |
| before 2026-10-04, no guard existed (25779 calls) | B | 452 | 246 | 206 | 54.4% | 77 | 76.2% |
| before 2026-10-04, no guard existed (25779 calls) | C | 446 | 240 | 206 | 53.8% | 83 | 74.3% |
| before 2026-10-04, no guard existed (25779 calls) | D | 442 | 239 | 203 | 54.1% | 84 | 74.0% |
| before 2026-10-04, no guard existed (25779 calls) | E | 441 | 245 | 196 | 55.6% | 78 | 75.9% |
| before 2026-10-04, no guard existed (25779 calls) | P | 449 | 246 | 203 | 54.8% | 77 | 76.2% |
| from 2026-10-04 (9176 calls) | A | 244 | 102 | 142 | 41.8% | 39 | 72.3% |
| from 2026-10-04 (9176 calls) | B | 205 | 98 | 107 | 47.8% | 43 | 69.5% |
| from 2026-10-04 (9176 calls) | C | 194 | 97 | 97 | 50.0% | 44 | 68.8% |
| from 2026-10-04 (9176 calls) | D | 192 | 97 | 95 | 50.5% | 44 | 68.8% |
| from 2026-10-04 (9176 calls) | E | 186 | 94 | 92 | 50.5% | 47 | 66.7% |
| from 2026-10-04 (9176 calls) | P | 194 | 98 | 96 | 50.5% | 43 | 69.5% |

What I read by hand, and what it changed:

- The first sed signature missed sed's message when it quotes a file name and a newline; 4
  of 5 "false positives" were failures. The signature was corrected (the table above uses it).
- The 4 "false positives" of `macos-no-timeout` were calls sent to the background, whose
  error shows up in a later `cat <task output>`; those later calls were 5 of its 17 "misses".
  Background calls were then excluded. The 6 misses left after the rewrite are such readings
  of a log, not calls that made the mistake.
- The 4 true positives P loses (one per lesson: glob, both equals lessons, status) are **one
  call**: `cat > probe.zsh <<'EOF' ... EOF; zsh probe.zsh`, a script written to reproduce these very
  failures while the general pool was being built (2026-10-04). Before 2026-10-04 P loses 0 of
  246 true positives.
- `zsh-status-path-variables`: 44 raw false positives, 41 of them text inside a
  here-document (mostly Python: `for path in ...`, `status=...`; 22 fed to python, 18
  written to a file by `cat`), 2 in double quotes. No call of the corpus failed with
  `read-only variable: status` except three probes and a quoted GitHub issue.
- `zsh-function-name-is-alias`: the 26 remaining false positives define `t()` 8, `q()` 8,
  `r()` 7, `w()` 2, `k()` 1, none an alias on this machine; the 7 failures are `g` 3, `c` 2,
  `h` 1, `u` 1.
- `zsh-nomatch-glob`: see below.
- E scores highest only because two patterns cannot match one simple command at all
  (`zsh-function-name-is-alias` 0 of 7, and see `chain-commit-with-and` 30 to 2 below).

## Every guard, including the ones with no error to look for

Nine lessons are advice about a kind of command (`git push`, a full pytest run, a wait
loop); the call does not fail, so there is no outcome to score. For those the question the
text answers is only "is this the command, or a mention of it". Calls matched, and where the
match began for the calls P drops:

| lesson | A | B | C | D | E | P | P without shell rule | lost A->P: heredoc | dq | sq | command | gained |
|-|-|-|-|-|-|-|-|-|-|-|-|-|
| brew-doctor-exits-1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| chain-commit-with-and | 30 | 25 | 24 | 23 | 2 | 23 | 23 | 5 | 1 | 1 | 0 | 0 |
| ci-poll-in-background | 11 | 10 | 10 | 10 | 0 | 10 | 10 | 1 | 0 | 0 | 0 | 0 |
| commit-pinned-checks-dry-run-first | 20 | 19 | 19 | 19 | 19 | 19 | 19 | 1 | 0 | 0 | 0 | 0 |
| docs-build-batch-first | 25 | 17 | 17 | 14 | 17 | 14 | 14 | 8 | 3 | 0 | 0 | 0 |
| expected-absence-or-true | 97 | 97 | 97 | 97 | 517 | 97 | 97 | 0 | 0 | 0 | 0 | 0 |
| full-pytest-after-changed-tests | 177 | 141 | 135 | 108 | 143 | 110 | 110 | 36 | 25 | 6 | 0 | 0 |
| gate-commit-on-pass-line | 5 | 5 | 5 | 3 | 2 | 3 | 3 | 0 | 2 | 0 | 0 | 0 |
| gh-run-list-needs-workflow | 19 | 18 | 18 | 18 | 15 | 18 | 18 | 1 | 0 | 0 | 0 | 0 |
| macos-no-timeout | 44 | 42 | 42 | 42 | 44 | 42 | 42 | 2 | 0 | 0 | 0 | 0 |
| plistlib-stdin-not-seekable | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| push-starts-the-ci-clock | 365 | 358 | 357 | 353 | 358 | 353 | 353 | 7 | 4 | 1 | 0 | 0 |
| sed-in-place-bsd | 12 | 9 | 1 | 0 | 9 | 9 | 9 | 3 | 0 | 0 | 0 | 0 |
| wait-loop-needs-deadline | 330 | 329 | 329 | 329 | 0 | 329 | 329 | 1 | 0 | 0 | 1 | 1 |
| zsh-equals-not-found | 29 | 25 | 25 | 25 | 25 | 25 | 24 | 4 | 0 | 0 | 0 | 0 |
| zsh-equals-word | 32 | 29 | 23 | 23 | 30 | 23 | 23 | 3 | 0 | 6 | 0 | 0 |
| zsh-function-name-is-alias | 34 | 33 | 33 | 33 | 0 | 33 | 33 | 1 | 0 | 0 | 0 | 0 |
| zsh-nomatch-glob | 524 | 516 | 513 | 510 | 516 | 510 | 510 | 8 | 3 | 3 | 0 | 0 |
| zsh-status-path-variables | 45 | 3 | 3 | 1 | 3 | 1 | 0 | 42 | 2 | 0 | 0 | 0 |
| ALL | 1799 | 1676 | 1651 | 1608 | 1700 | 1619 | 1617 | 123 | 40 | 17 | 1 | 1 |

Read by hand: a sample of up to 6 of the dropped calls of every lesson (59 calls). None was
a command the call itself ran. Most were mentions: Python and Markdown in here-documents,
`grep` patterns, commit messages, JSON test payloads, lists of test cases. Four were lines
of a shell script being written to a file (one of them a wait script with an unbounded
`while pgrep ...; do sleep` loop): commands, but of a later call. Over all
123 matches dropped from here-document bodies: 43 are fed to python, 54 written by `cat` to
a file that is not a shell script, 21 written to a `.sh` or `.zsh` file, 5 other (see Red
team).

- C and D lose real matches: `sed-in-place-bsd` goes 9, 1, 0 (the pattern reads the quoted
  script), 8 true positives to 1 to 0.
- D adds false positives: 8 calls of `full-pytest-after-changed-tests` match under D and not
  under P, because emptying `"tests/x.py::test_y"` makes a targeted run look like a full one.
- E cannot express a pattern about two commands: `chain-commit-with-and` 30 to 2,
  `wait-loop-needs-deadline` 330 to 0, `ci-poll-in-background` 11 to 0. And a pattern with no
  anchor matches more: `expected-absence-or-true` 97 to 517.
- B to P: 57 more calls dropped (40 begin in double quotes, 17 in single quotes), no true
  positive lost (344 and 344).
- P's known leak: a match that begins in command text and ends in a quoted string. 10 calls of
  `full-pytest-after-changed-tests` match under P and not under D; the 7 read are
  of the shape `RUN=".venv/bin/pytest -q"`, an assignment the pattern takes for a run because
  its `\S*/` prefix swallows `RUN=".venv/bin/`.

## The recorded stops

| where the match began | the next call of the loop | stops |
|-|-|-|
| beyond the 4000-character cut (the text kept begins a here-document) | changed, pattern no longer matches | 2 |
| beyond the 4000-character cut (the text kept begins a here-document) | same call sent again | 1 |
| command text | changed, pattern no longer matches | 36 |
| command text | changed, pattern still matches | 3 |
| command text | no retry logged | 8 |
| command text | same call sent again | 4 |
| here-document body | changed, pattern no longer matches | 4 |
| here-document body | changed, pattern still matches | 3 |
| here-document body | no retry logged | 1 |
| here-document body | same call sent again | 4 |

- 66 stops: 51 in command text, 15 in a here-document body (12 seen, 3 beyond the cut), 0 in
  a quoted string. P removes the 15 and keeps the 51.
- After a stop in command text the pattern no longer matched the next call 36 times of 43.
- `same: false` is not proof that a stop applied. Of the 14 here-document stops with a retry,
  9 are "changed". Reading the 9: 5 retries begin with the same here-document (what changed
  is past the 4,000 cut, or elsewhere in the call while the matched text stayed), 4 are a
  different command altogether (the file was written another way, or the next step came).

## Why zsh-nomatch-glob was recalled 72 times

| lesson | when | raw | proposed | recalls |
|-|-|-|-|-|
| chain-commit-with-and | no refusal yet in the session | does not match | does not match | 2 |
| ci-poll-in-background | no refusal yet in the session | does not match | does not match | 1 |
| expected-absence-or-true | guard had already refused once in the session | does not match | does not match | 1 |
| expected-absence-or-true | no refusal yet in the session | does not match | does not match | 2 |
| expected-absence-or-true | no refusal yet in the session | matches | matches | 1 |
| macos-no-timeout | guard had already refused once in the session | does not match | does not match | 3 |
| macos-no-timeout | guard had already refused once in the session | matches | matches | 1 |
| zsh-equals-not-found | no refusal yet in the session | matches | matches | 3 |
| zsh-equals-word | guard had already refused once in the session | does not match | does not match | 1 |
| zsh-equals-word | guard had already refused once in the session | matches | matches | 3 |
| zsh-equals-word | no refusal yet in the session | matches | matches | 2 |
| zsh-function-name-is-alias | guard had already refused once in the session | matches | matches | 2 |
| zsh-nomatch-glob | guard had already refused once in the session | does not match | does not match | 14 |
| zsh-nomatch-glob | guard had already refused once in the session | matches | matches | 43 |
| zsh-nomatch-glob | no refusal yet in the session | does not match | does not match | 9 |
| zsh-nomatch-glob | no refusal yet in the session | matches | matches | 6 |
| zsh-status-path-variables | guard had already refused once in the session | does not match | does not match | 1 |

- 72 recalls in 17 sessions; 15 stops in 15 sessions. 57 recalls in 8 sessions came after
  that session's one refusal; five sessions account for 59 recalls (9, 9, 12, 13, 16).
- Of the 15 recalls with no refusal yet, 6 match today's pattern. Three of them are at the
  minute of a `learn --update` of the lesson (on 10-04, 10-08 and 10-09): the
  failure that made the session add an alternative. The lesson was updated four times in six
  days, each time for one call; the other three predate the alternative that matches them.
- The 23 recall calls the pattern misses: 11 are a glob with nothing after it that the
  pattern looks for (of the shape `wc -l src/pkg/*.py`), 12 a glob behind a variable (of the shape `$DIR/page-*.png`) or
  a call cut at 4,000 characters.

What the three alternatives of its pattern do, and what a text pattern can reach:

| lesson | pattern | text | matched | TP | FP | precision | missed | recall |
|-|-|-|-|-|-|-|-|-|
| zsh-nomatch-glob | existing | A | 524 | 246 | 278 | 47% | 81 | 75% |
| zsh-nomatch-glob | existing | P | 510 | 245 | 265 | 48% | 82 | 75% |
| zsh-nomatch-glob | existing alt 1 alone: --include=* | A | 181 | 168 | 13 | 93% | 159 | 51% |
| zsh-nomatch-glob | existing alt 1 alone: --include=* | P | 170 | 167 | 3 | 98% | 160 | 51% |
| zsh-nomatch-glob | existing alt 3 alone: glob then 2>/dev/null | A | 344 | 81 | 263 | 24% | 246 | 25% |
| zsh-nomatch-glob | existing alt 3 alone: glob then 2>/dev/null | P | 343 | 81 | 262 | 24% | 246 | 25% |
| zsh-nomatch-glob | new alt alone: a URL with ? | A | 2625 | 10 | 2615 | 0% | 317 | 3% |
| zsh-nomatch-glob | new alt alone: a URL with ? | P | 7 | 7 | 0 | 100% | 320 | 2% |
| zsh-nomatch-glob | REWRITE: --include/--exclude glob, URL with ?, gh api ? | A | 2808 | 179 | 2629 | 6% | 148 | 55% |
| zsh-nomatch-glob | REWRITE: --include/--exclude glob, URL with ?, gh api ? | P | 179 | 176 | 3 | 98% | 151 | 54% |
| zsh-nomatch-glob | any * (upper bound on recall from text) | A | 10367 | 317 | 10050 | 3% | 10 | 97% |
| zsh-nomatch-glob | any * (upper bound on recall from text) | P | 2929 | 309 | 2620 | 11% | 18 | 94% |

`grep --include=*.py` fails every time (the word is the glob); `ls src/*.py 2>/dev/null`
fails only when nothing matches, which the text does not say. 262 of that alternative's 343
stops would have been of calls that ran. Any pattern that reaches the rest of the failures
stops ten calls for each one it saves (`any *`: 11% precision). The remaining failures need
the file system, not a better regex: the check knows the working directory and could expand
the glob. Not measured here; the transcripts do not hold the file system.

## Patterns to rewrite

| lesson | pattern | text | matched | TP | FP | precision | missed | recall |
|-|-|-|-|-|-|-|-|-|
| macos-no-timeout | existing | A | 44 | 41 | 3 | 93% | 17 | 71% |
| macos-no-timeout | existing | P | 42 | 41 | 1 | 98% | 17 | 71% |
| macos-no-timeout | REWRITE: the word timeout and a number | A | 63 | 52 | 11 | 83% | 6 | 90% |
| macos-no-timeout | REWRITE: the word timeout and a number | P | 54 | 52 | 2 | 96% | 6 | 90% |
| zsh-function-name-is-alias | existing | A | 34 | 7 | 27 | 21% | 0 | 100% |
| zsh-function-name-is-alias | existing | P | 33 | 7 | 26 | 21% | 0 | 100% |
| zsh-function-name-is-alias | REWRITE: only names that are aliases here (c e g h l u) | A | 7 | 7 | 0 | 100% | 0 | 100% |
| zsh-function-name-is-alias | REWRITE: only names that are aliases here (c e g h l u) | P | 7 | 7 | 0 | 100% | 0 | 100% |
| zsh-equals-word | existing (user lesson) | A | 32 | 22 | 10 | 69% | 5 | 81% |
| zsh-equals-word | existing (user lesson) | P | 23 | 21 | 2 | 91% | 6 | 78% |
| zsh-equals-word | existing (general lesson zsh-equals-not-found) | A | 29 | 23 | 6 | 79% | 4 | 85% |
| zsh-equals-word | existing (general lesson zsh-equals-not-found) | P | 25 | 22 | 3 | 88% | 5 | 81% |
| zsh-equals-word | a word of two or more = anywhere | A | 2003 | 25 | 1978 | 1% | 2 | 93% |
| zsh-equals-word | a word of two or more = anywhere | P | 31 | 23 | 8 | 74% | 4 | 85% |
| sed-in-place-bsd | existing | A | 12 | 8 | 4 | 67% | 7 | 53% |
| sed-in-place-bsd | existing | P | 9 | 8 | 1 | 89% | 7 | 53% |
| zsh-status-path-variables | existing | A | 45 | 1 | 44 | 2% | 2 | 33% |
| zsh-status-path-variables | existing | P | 1 | 0 | 1 | 0% | 3 | 0% |

| lesson | now | measured better pattern (JSON string escaping not shown) |
|-|-|-|
| zsh-nomatch-glob | three alternatives, 48% | `--(include|exclude)=[^\s'"]*[*?\[]`, `\bhttps?://[^\s'"<>|;&)]*\?`, `gh api [^\s'"]*\?`: 176 of 179 (98%), recall 54%. Needs P: on raw text the URL alternative matches 2,625 calls. Drop "glob then `2>/dev/null`" (24%). |
| macos-no-timeout | `(^|[;&|]\s*)timeout\s+\d`, misses `VAR=x timeout 60`, `(timeout 60` | `(?<![\w=./-])timeout\s+(?:-\w+\s+\S+\s+)*\d`: 52 of 54 (96%), recall 71% to 90%. On raw text 83%. |
| zsh-function-name-is-alias | `[a-z]\(\)`, 21% | name the aliases of the machine: `(?:c|e|g|h|l|u)\s*\(\)` behind the taught anchor: 7 of 7, 0 false. The list is `zsh -ic alias` on this machine and belongs to a user lesson. |
| zsh-equals-word | duplicates the general `zsh-equals-not-found` | keep one: 21 of 23 (91%) and 22 of 25 (88%) under P, nearly the same calls. `compound disable zsh-equals-not-found` or `rm` the user's. |
| zsh-status-path-variables | fine under P (45 matches to 1) | no rewrite; it has no organic failure in 34,955 calls. |
| plistlib-stdin-not-seekable | matches Python text, 0 calls in the corpus | under P it can never match (its text is always inside quotes or a here-document). Begin it at the command: `python3?\b[^\n]*-c\s+["'][\s\S]*?plistlib\.load\(sys\.stdin\.buffer\)`. |

Seven signature lessons, existing patterns on raw text: 348 of 720 (48.3%), recall 75.0%.
Rewritten patterns under P: 286 of 298 (96.0%), recall 61.6% (286 of 464). The recall given
up is the "glob then `2>/dev/null`" alternative: 81 failures bought with 262 stops of calls
that ran. A stop costs one round trip and so does a failure, so an alternative under 50%
precision costs more than it saves; that is an assumption about cost, not a measurement.

## The validation rule

"A new or changed pattern must match the failing calls recorded for that lesson and must
not match the recorded working calls."

**At the time each guard was written: nothing to test.** No `learn` event of a guard lesson
has `settles` (of the 16 user guards, 10 are lessons imported from notes on 2026-10-04 and 6
are from 2026-10-10; 3 guards ship in the package). The 13 captures in the log settled 5 lessons, none a guard.

**Against what was recorded since** (`recall` events, T3): `zsh-nomatch-glob` 49 of 72,
`macos-no-timeout` 1 of 4, `expected-absence-or-true` 1 of 4, `chain-commit-with-and` 0 of 2,
`zsh-status-path-variables` 0 of 1, `ci-poll-in-background` 0 of 1: rejected. `zsh-equals-word` 5 of 6: rejected.
`zsh-equals-not-found` 3 of 3, `zsh-function-name-is-alias` 2 of 2: accepted. But the
recorded calls are not all the lesson's failure: reading the misses, the recall judge named
`macos-no-timeout` beside an ffmpeg option error, `chain-commit-with-and` beside two
permission prompts, `zsh-equals-word` beside a probe script. "Must match **all**" would
refuse a correct pattern because of the judge's mistakes.

**Against pairs from the transcripts** (a failing call and the next Bash call that ran
without the error):

| lesson | pattern | pairs | failing call matched (raw / proposed) | next working call matched (raw / proposed) | both: failing matched and working not (raw / proposed) |
|-|-|-|-|-|-|
| macos-no-timeout | existing | 57 | 40 / 40 | 0 / 0 | 40 / 40 |
| macos-no-timeout | rewritten | 57 | 51 / 51 | 0 / 0 | 51 / 51 |
| sed-in-place-bsd | existing | 15 | 8 / 8 | 0 / 0 | 8 / 8 |
| zsh-equals-not-found | existing | 25 | 21 / 20 | 0 / 0 | 21 / 20 |
| zsh-equals-word | existing | 25 | 20 / 19 | 0 / 0 | 20 / 19 |
| zsh-function-name-is-alias | existing | 7 | 7 / 7 | 0 / 0 | 7 / 7 |
| zsh-function-name-is-alias | rewritten | 7 | 7 / 7 | 0 / 0 | 7 / 7 |
| zsh-nomatch-glob | existing | 316 | 238 / 237 | 10 / 9 | 228 / 228 |
| zsh-nomatch-glob | rewritten | 316 | 175 / 172 | 8 / 0 | 168 / 172 |
| zsh-status-path-variables | existing | 3 | 1 / 0 | 0 / 0 | 1 / 0 |

- The first half works. It separates patterns by what they miss, and the rewrite of
  `macos-no-timeout` goes from 40 to 51 of 57.
- The second half says nothing: the next working call is almost never matched, for the 21%
  pattern (`zsh-function-name-is-alias`, 0 of 7) as for the 98% one. A fix is a different
  call; the false positives are other calls entirely.
- Taken strictly against every call that ran, the second half rejects every pattern that
  matches anything except the alias rewrite (the 98% `--include` pattern has 3).

**Verdict.** Keep the idea, change its form:

1. Refuse a pattern that does not match the failing call it is written for (the capture's
   `failed`, or a call given on the command line). One named call, not "all recorded".
2. Refuse a pattern that matches the capture's `fixed` call. Cheap; rarely fires.
3. Replay the pattern over the Bash calls the transcripts hold and print, do not refuse:
   calls it would have stopped, and how many of those showed the lesson's error. That is the
   number that told the 98% alternative from the 24% one, and the fix pair cannot give it.
   The event log cannot give it either: it holds only calls that failed or were stopped, cut
   at 4,000 characters.
4. Report the coverage of the lesson's `recall` calls as a number.

Open: the threshold at which 3 should refuse. The alternatives measured here fall at 88% or
more or at 24% or less (one I tried and do not propose, "a word of two or more `=`", is at
74%), so any line from 50% to 70% sorts today's patterns the same way.

## The function

`guard_text.py`: `classify`, `guard_view`, `guard_search`, `simple_commands`. Standard
library, Python 3.9, no state. Median 0.12 ms a call over the corpus, 99th percentile
0.8 ms, worst 3.6 ms (20,000 characters).

`guard_text_test.py` runs 48 commands in zsh, bash and sh and compares what the shell
executed with what the scanner calls command text (no mocks: the shell is the oracle).
Cases: `<<'EOF'`, `<<"EOF"`, `<<\EOF`, `<<-EOF` with tabs, `<<EOF` with `$( )` and
backticks that run, an escaped `\$(` that does not, a quoted delimiter where they do not,
a command after the operator on the same line, a pipe after it, two here-documents on one
line, a body that starts after a quoted string spanning lines, a here-document in a loop
and inside `"$(cat <<'EOF' ...)"`, an unclosed one, `bash <<EOF`, `sh -s <<EOF`, a
here-document inside one fed to bash, `python3 - <<EOF`, `bash -c '...' <<EOF`, here-strings
`<<<`, single, double and ANSI-C quotes over one and several lines, `\"` inside double
quotes, `\'` outside, the `'\''` idiom, `$( )` and backticks inside double quotes with
quotes inside them, comments and `#` that is not one, `bash -c`, `sh -c`, `eval`,
`python3 -c`, `$((1<<3))`, `${x:-"a; b"}`, subshells, loops, line continuation.

Against the corpus: the scan ends with no quote or bracket left open on all 36,063 calls
with outcome ok or error. A line-based here-document finder written separately marks no
line as command that the scanner marks as body, and differs the other way on 42 of 8,082
calls. By the first differing line: in 21 the operator's line continues through a quoted
string that spans lines and the body starts after it (the scanner is right; now a test
case); 18 are the closing word of an inner here-document inside an outer body (an artefact
of the comparison); 3 are a `$( )` line in an unquoted body or the line that closes a quoted
string (the scanner is right).

What it does not do: follow `case` patterns' lone `)` inside `$( )`, aliases, `ssh host
'...'` (remote, where a lesson's platform and shell may not hold), a script file's content.

## Red team

**Does dropping here-document bodies lose true positives?** In this corpus, one call, and it
is a deliberate reproduction (above). The reason is what the bodies are:

```
calls with a here-document body: 8120 of 34955; calls where a string or body is fed to a shell (bash -c, eval, bash <<): 34
8836 here-documents: [('python', 5556), ('cat', 3026), ('git', 147), ('other', 97), ('compound', 8), ('node', 1), ('zsh', 1)]
```

Of 8,836 here-documents none is fed to `bash`, `sh` or `zsh` (the one counted under zsh is a
here-string inside `zsh -c`). 63% go to Python, 34% to `cat` (2,062 `.py`, 468 `.md`, 112
`.sh` files), 147 to git (commit messages). So "keep a body fed to a shell, drop one fed to
python or cat" is right in principle, costs nothing, is tested against the real shells, and
is **unsupported by any observed case**: the shell rule changes 2 matched calls of 1,619.
`bash -c` and `eval` strings appear in 34 calls.

**A mistake inside a script written by a here-document** (`cat > script.sh <<'EOF'`, 112 `.sh`
files) is not seen. 21 of the 123 matches dropped from here-document bodies are in a `.sh` or
`.zsh` file being written (6 `full-pytest-after-changed-tests`, 2 `docs-build-batch-first`,
2 `sed-in-place-bsd`, the rest the zsh lessons, several in the reproduction scripts of
2026-10-04). Those are commands of a later call, and for the advice lessons the advice may
apply when the script runs. It is also not seen when the
same script is written with the Write tool, or when it is run (`zsh script.sh`). The design
says guards match commands, not file content; P makes the here-document form consistent
with that. If scripts should be guarded, that is `match-tools`, not the command text.

**A mistake inside inline Python** (`python3 - <<EOF`, `python3 -c "..."`). One of 19 guards
is of that kind (`plistlib-stdin-not-seekable`) and it matches 0 calls. Under P it needs to
begin at `python3` (possible for `-c`, not for a here-document). A lesson key that asks for
the raw text would cover it; with one lesson and no call, there is no evidence it is needed.

**An unquoted delimiter runs `$( )` in the body.** Kept as command text and tested. Not
observed to matter.

**Is the gain one lesson?** Yes for the text rule: 43 of the 73 false positives it removes
are `zsh-status-path-variables`. Without that lesson precision moves 51.4% to 53.6%.
Without `zsh-nomatch-glob`, whose false positives are in command text (265 of 278), it moves
52.0% to 74.4%. Without both, 66.9% to 75.0%. The direction holds in every subset and
before and after 2026-10-04; the size depends on which lessons exist. Over all 19 guards
the rule drops 180 of 1,799 matched calls (10%); `full-pytest-after-changed-tests` is 67 of
them, `zsh-status-path-variables` 44.

**Is the gain from rewriting one lesson?** Mostly: `zsh-nomatch-glob` is 524 of the 720 raw
matches. The alias and timeout rewrites are 34 and 44 calls.

**Selection.** After 2026-10-04 guards stopped some calls and the model rewrote them, so the
later corpus under-counts both true and false positives of the existing patterns. The
before-10-04 rows are free of that and say the same.

**Labels.** A signature is a regex on the result. Two were wrong on first reading and were
fixed (sed, background calls). The `zsh-nomatch-glob` cells were read in samples of 12 per
cell, not in full. A true positive means the error appeared in a call the pattern matched,
not that the matched text caused it.

## Uncertain

- Whether a file-system check of a glob is worth its time inside the 1,500 ms budget, and
  what it would do to the 151 glob failures no precise text pattern reaches.
- The precision of the nine advice lessons (`push-starts-the-ci-clock` 353 calls,
  `wait-loop-needs-deadline` 329): the calls do not fail, so the corpus cannot score them. Of
  15 retries after their stops in command text, 4 were the same call sent again and 11 changed.
- Whether refusing more than once a session (the 57 recalls) helps or annoys. With a 48%
  pattern it would double the noise; with a 98% one it would not. Not tested.
- One user, one machine, six weeks, zsh on macOS. The alias list, the share of Python
  here-documents and the absence of `bash <<EOF` are this user's habits.
- The cost model (a stop costs what a failure costs).

## Files

All under `notes/2026-10-11-usage-audit/`. The corpus and the match tables are pickles in the
session scratch directory, not in the repository (they hold private command text).

| file | what |
|-|-|
| `guard_text.py` | the proposed function |
| `guard_text_test.py` | 48 cases against zsh, bash and sh; `python3 guard_text_test.py` |
| `guard_corpus.py OUT.pkl` | builds the corpus from the transcripts |
| `guard_measure.py CORPUS HITS` | every pattern, every call, every candidate (about 2 minutes) |
| `guard_analyze.py CORPUS HITS [--all-projects]` | the precision and recall table |
| `guard_tables.py CORPUS HITS` | the other tables (stops, recalls, all guards, subsets, rewrites, here-documents) |
| `guard_pairs.py CORPUS HITS` | the validation rule on failing and working pairs |
| `guard_lab.py` | a pattern against the corpus under A and P (module) |
| `guard_show.py CORPUS HITS LESSON CAND CELL` | prints the calls of one cell for reading |
