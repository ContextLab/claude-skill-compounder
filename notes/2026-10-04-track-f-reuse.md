# 2026-10-04: Track F, reuse precision and lesson hygiene

Work on the audit's proposals P6, P7 and the small items of P8
(`notes/2026-10-04-audit/audit-quality.md`), on a worktree branch off `190b900`. Not pushed, not
merged. Every number below came from a command run in this session; the scripts that produced
them were scratch files and are not in the repository, except `tests/journeys/measure_reuse.py`.

## Done

1. **`find` ranks by the weight of words, not their number.** `stem`, `rarity`, `index_of`,
   `rank_items` in `bin/compound`. Rarity is read from the store (`1 - ln(df) / ln(max(N, 20))`),
   a word of `COMMON_WORDS` counts a tenth, a body-only word half, a whole body at most 1.
   Rows carry `weight` and `matched`; `score` is still the number of words matched.
2. **A floor before the judge.** `compound find --request` (the prompt on stdin) lists only
   candidates: weight >= `COMPOUND_REUSE_FLOOR` (1.5; `--floor`), and >= a third of the best
   candidate's weight. The mod now sends the judge these candidates and not the whole inventory.
   With no candidate and no earlier request, no model is asked.
3. **The judge prompt.** Each name must come with a quote of the request's own words;
   `parseReuse` drops a name whose quote is not in the request and counts it (`unquoted` on the
   `judge` event).
4. **A memo.** `<COMPOUND_HOME>/memo.json`, written by `compound memo`, read by `find --request`.
   Key: project, request text, floor, limit, and the content of every candidate. 200 entries, 7
   days. A hit skips the model and the prompt-log search and writes `judge` and `reuse` events
   with `memo: true`.
5. **`compound add` refuses a copy and session residue** (exit 2; `--new`, `--as-written`).
6. **Small items.** `[n/m words]` is now `[2 of 3 words: a, b]`. `python3 -S` was measured and
   not adopted (below).

Also fixed on the way: `tests/journeys/journey_reuse.py` failed its `other` step on the base
commit too (the step compared every event with `[]`, and a `judge` event is written since track
A). The docstring of `bin/compound` named the `reuse` event's field `keywords`; the mod writes
`words`.

## Rankings, before and after

Fixture: the 18 entries of `tests/test_reuse.py` (real names, texts written for the test in the
shape of the real ones). "Before" is `find` of `190b900` with the ten words its `significantWords`
chose; in the base the judge was shown the whole inventory, not this list.

| request | before (words matched) | after (weight; candidates only) |
|-|-|-|
| the release/audit request | `speckit-execute` 7, three others 1 | `sed-range-from-empty-variable` 2.04 (chance: "range", "results") |
| the scripted security review | `speckit-execute` 3, four others 1 (`patch-scripts-match-current-text`, `shared-tree-no-add-all-no-stash` among them) | none |
| a Python patch script | `patch-scripts-match-current-text` 6, two others 1 | `patch-scripts-match-current-text` 6.88 |
| run the Spec Kit pipeline | `speckit-execute` 9, two others 1 | `speckit-execute` 7.26 |
| search my past prompts | `history-surfer` 6, four others | `history-surfer` 3.55 |
| fill placeholder citations | `cdl-bib-cite` 4, `bib-duplicate-check` 2 | `cdl-bib-cite` 5.84 |
| dispatch subagents in worktrees | `state-no-mocks-in-agent-prompts` 2, `agent-worktree-check-base` 2, `speckit-execute` 2, five others 1 | `state-no-mocks-in-agent-prompts` 2.6, `agent-worktree-check-base` 2.3 |
| a timeout on macOS | six entries tied at 1, `macos-no-timeout` third | `macos-no-timeout` 3.0 |

Search words for the release/audit request. Before: `release current version careful ultrawork
audit package come few awesome`. After: `release version ultrawork audit package slick
improvements interface performance experience`.

The real store (39 entries) and the real prompt log, read-only:

- Release/audit request: one candidate, `sed-range-from-empty-variable` 1.66. Earlier requests:
  only the request itself (which a session drops as its own). The two earlier requests the audit
  found offered (`b587c98c`, `f58c372b`) are no longer candidates.
- Security review: two candidates, the scripts `bin/compound` 1.99 and
  `merge-in-a-scratch-worktree` 1.54; no earlier request. `patch-scripts-match-current-text`,
  `zsh-nomatch-glob`, `shared-tree-no-add-all-no-stash` and `state-no-mocks-in-agent-prompts`
  are not candidates.
- `find heredocs chained`: before `gate-commit-on-pass-line` alone; after `heredoc-ends-and-chain`
  first (1.28).
- `find "(eval):1: ==== not found"`: NOT fixed. Before and after, `history-surfer` and
  `macos-no-timeout` stand above or level with `zsh-equals-word` (0.30, 0.29, 0.29). The only
  token that tells the lesson apart is `====`, which is not a word.

## The judge, measured with real haiku calls

**Through the mod, real `claude -p` sessions, the 18-entry store, 11 requests** (5 that nothing
covers, 6 I labelled as covered), three runs of each tree:

| | right thing added | wrong thing added | covered, nothing added | uncovered, nothing added | judge calls |
|-|-|-|-|-|-|
| before (`190b900`) | 15 | 3 | 3 | 12 | 33 of 33 |
| after | 12 | 0 | 6 | 15 | 24 of 33 |

- The 3 wrong additions before are the audit's own: `speckit-execute` for the release/audit
  request, 3 runs of 3.
- The 6 misses after are two requests, 3 runs each, both judged `not-substantial`: "What did I
  ask earlier ... Search my past prompts" (missed before as well, 3 of 3) and "Run the full Spec
  Kit pipeline on the active spec ..." (named before, 3 of 3). The second is a loss against my
  label. By the contract's own rule (a request to run something that exists is not a build
  task) the verdict is consistent. I did not tune the prompt for it.

**`tests/journeys/measure_reuse.py`** (9 lessons, 14 prompts, 5 covered):

| run | right | wrong | covered, nothing | uncovered, nothing | judge calls |
|-|-|-|-|-|-|
| before, 1 run | 5 | 0 | 0 | 9 | 14 of 14 |
| after, run 1 (before the "third of the best" cut and the last wording) | 3 | 1 | 1 | 9 | 6 of 14 |
| after, run 2 | 5 | 0 | 0 | 9 | 6 of 14 |
| after, run 3 (final code) | 5 | 0 | 0 | 9 | 6 of 14 |

Run 1's wrong addition was `brew-doctor-exit` beside `latex-undefined-citations` (weights 1.82
and 6.25); the cut at a third of the best candidate removes it. Run 1's miss was the judge
answering "nothing" for the CSV request. On this small store the base was already right 14 of 14:
what changed is 8 fewer model calls per 14 prompts, and the repeated prompt (`memo: true`, 0 ms).
In runs 2 and 3 the earlier request for the CSV prompt was named without a usable quote
(`unquoted=1`) and dropped, twice of twice; the release one was dropped once of twice.

**The prompt wording alone, same candidates, `claude -p --model haiku` with no plugin** (14
pairs: 7 that should match, 7 that should not; an approximation, since `claude -p` adds Claude
Code's system prompt and `$.model.complete` does not):

| prompt | TP | FN | FP | TN |
|-|-|-|-|-|
| base wording, 2 rounds | 12 | 2 | 0 | 14 |
| new wording, 5 rounds (2 of them with the final text) | 30 | 5 | 0 | 35 |

Every FN is the `docker-compose` pair. With the full 18-entry inventory the base wording also gave
0 FP in 22 calls there. So: **the tightened wording shows no measurable gain in precision by
itself.** The false positives were reproduced only through the mod with the whole inventory, and
what removes them is the floor. The quote requirement is a check that can be verified, not a
measured improvement.

Judge time through the mod, fixture runs: before, 33 calls, median 677 ms, slowest 2812 ms;
after, 24 calls, median 842 ms, 578 to 3230 ms. The reply is longer now (it carries the quotes),
and the median call is about 165 ms slower. The three slowest after (2487, 3117, 3230 ms) are all
the security-review request. Nothing reached 5 s.

## Timings

`find` against the real store and prompt log (median of 7): base `find` with ten words 120 ms;
`find --request` 667 ms (71 ms with no prompt log). The difference is the prompt-log search
across every project (`surfer search --all`, 415 to 517 ms, 200 rows, 1.6 to 2 MB): the base
stopped after the project search whenever five prompts of the project matched any word, and a
request now needs hits that carry a third of the words' weight, so the wider search runs more
often. A memo hit skips both searches.

`check --guards`, 32 lessons / 7 guards, 20 runs, median ms, on an otherwise idle machine. Two
pairs of runs: the first before the documentation was added to the script, the second on the
final code.

| python | base | branch | base `-S` | branch `-S` |
|-|-|-|-|-|
| `/usr/bin/python3` 3.9.6 | 61.7, 67.5 | 63.6, 70.4 | 62.0, 65.5 | 64.1, 69.8 |
| anaconda 3.9.13 | 47.7, 50.1 | 52.2, 54.5 | 37.9, 40.0 | 43.7, 43.4 |
| Homebrew 3.14.7 | 57.2, 60.1 | 62.0, 66.5 | 60.1, 62.2 | 59.4, 66.6 |

**This track makes every CLI call slower by about 2 to 6 ms, `check` included.** The one-file
script is compiled on every call (13.7 ms at the base, 16.4 ms on the branch, anaconda 3.9), and
the branch adds about 485 lines to it. The patterns and the `math` import the new code needs are
loaded only when `add` or `find` runs; what is left is the size of the file. A launcher that
imports a cached module would save more than `-S` does, and needs the one-file rule changed; I
did not do it.

**`python3 -S`: not adopted.** Nothing the CLI needs is lost: run with `-S` on each of the three
interpreters, the suite's only failures were the three documentation tests that failed without
`-S` at that commit too (the design table was not yet written). But it saves 0 to 2 ms on the
system Python, nothing measurable on Homebrew (between 3 ms saved and 3 ms lost over the pairs
above) and about 10 ms on this anaconda, whose `site` loads an editable-install finder. And
each way to adopt it gives something up: a shebang `env -S python3 -S` fails where `env` has no
`-S` (GNU coreutils before 8.30), and having the mod run `python3 -S <cli>` breaks a
`bin/compound` that is not a Python file (the journeys' slow copy is a shell wrapper).

## Assertions changed on purpose

- `hooks/judge.test.ts`: the reply shape in the reuse prompt; every `parseReuse` call takes the
  request and names come with quotes; answers carry `unquoted`. The two tests of
  `significantWords`, `STOPWORDS` and `candidateFloor` are gone with those functions: the CLI
  chooses the words now (`tests/test_reuse.py`, `test_the_search_words_are_the_rare_ones`,
  `RequestPromptLogTest`).
- `hooks/ui.test.ts`: the judge's reply names the lesson with a quote (three places), and the
  world's `find` answers with the one candidate (it answered with none).
- `tests/test_support.py`: `math` and `hashlib` are allowed standard-library imports.
- `tests/journeys/journey_reuse.py`: the `other` step leaves `judge` events out of "nothing".

No test in `tests/test_check_find.py` or `tests/test_review.py` needed a change.

## Left open, and not verified

- A chance candidate still reaches the judge when two uncommon words coincide
  (`sed-range-from-empty-variable` for "a wide range of users ... better results"). The judge
  declined it 8 of 8 times (3 through the mod, 5 in the isolated rounds).
- The memo is not locked: two writers at once can lose one entry.
- "In this session" as residue comes from the brief, not from the audit's evidence; no real
  lesson holds it, a path through `/scratchpad/`, a `/tmp/claude-` path or a UUID (33 user
  lessons and the general-pool drafts checked). The audit's own example of residue ("python3
  pg.py URL regex") is not something a pattern can find.
- The duplicate gate's 80% was not tuned on real duplicates: none exists.
- `tests/journeys/probe_injection.py` and the other journeys were not run. A planted lesson now
  has to share words with a request to reach the judge at all.
- Not measured on a store of hundreds of entries.
