# Level B search measurement — scripts

Sanitized copies of the scripts used for `notes/research/level-b-search-measurement.md`.
Absolute paths under the session scratchpad were replaced with `LEVELB_DIR` (default
`./levelb/`); project slugs that would otherwise embed a home directory (history-surfer
names a project by its cwd with `/` -> `-`) are read from `LEVELB_CUR` / `LEVELB_PROJECTS`
/ `LEVELB_TAG` instead of being hardcoded. No prompt text, session id, or stoplist is
included here — see the note for why and how to regenerate them.

Run in this order:

- `load.py` — loads `~/.claude/history-surfer/projects/*/prompts.jsonl`, applies the
  `toks_of`-style tokenizer, and writes `df.json` (per-token document frequency over all
  non-command non-empty prompts).
- `stop.py` — turns `df.json` into stoplists at three document-frequency cutoffs
  (`stoplist_5pct.txt` etc).
- `rank3.py <project-slug> [notmp]` — Round 1: ranks candidate prompts from other projects
  against each session's first substantive prompt in `<project-slug>`, by shared-token
  count (after the stoplist) and by Jaccard; writes a `pairs_*.json` file of top-3 hits per
  query per threshold.
- `sample.py` — stratified-samples 60 pairs across shared-token-count buckets from a
  `pairs_*.json` pair (set `LEVELB_TAG` to match).
- `mkprompts.py` — turns the sample into one judge-prompt file per pair, using the verbatim
  template quoted in the note.
- `judge.sh <pid> <run>` — calls the haiku judge on one prompt file, twice per pair
  (`run` 1 and 2).
- `score.py` — parses the judge transcripts, requires agreement across both runs for
  RELEVANT, and prints the precision tables (also written to `verdicts.json`).
- `rare.py` — exploratory rare-token variant (single project, `LEVELB_CUR`), restricted to
  tokens with `2 <= df < 1%`.
- `rare2.py` — Round 2: the rare-token variant run properly across `LEVELB_PROJECTS`
  (comma-separated slugs), with a project-frequency (`pf`) breakdown and the k>=3/k>=4
  sampling used for the round-2 judged set.
- `judge_rare.sh <pid> <run>` — same judge call, pointed at `prompts_rare/`.

Round 2's `prompts_rare/` was built with the same template as `mkprompts.py` (verbatim in
the note) but pointed at `rare_sample2.json` — that one-line variant was not saved
separately; regenerate by copying `mkprompts.py` with `sample60.json` -> `rare_sample2.json`
and `prompts` -> `prompts_rare`, or edit `mkprompts.py` in place. There is no `score2.py`:
the round-2 numbers in the note came from the same parse-and-agree logic in `score.py`,
run by hand against `judgements_rare/` and `rare_sample2.json` (set `LEVELB_TAG` is not
needed there since round 2 has no `pairs_*.json` population-weighting step — only the raw
per-bucket precision was computed).
