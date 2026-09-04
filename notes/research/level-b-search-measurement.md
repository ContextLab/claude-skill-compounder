# Level B keyword search — measured false-positive rate

**Date:** 2026-09-03 (machine local).
**Machine:** darwin, live `~/.claude/history-surfer/projects` store on this user's account.
**Scope:** does a shared-content-token rule over the prompt-history store — the kind of
"surface a related past prompt" search a Level B mechanism would run — clear a usable
precision bar, and if not, what does the false-positive rate actually measure.

Two measurement rounds were run today with a haiku judge
(`claude -p --model claude-haiku-4-5-20251001`, no tools, 2 runs per pair, disagreement
counted IRRELEVANT). 260 judge calls total across the two rounds.

---

## VERDICT

**No threshold tried reaches precision 0.6 at a defensible n. Level B keyword search stays
a documented limit.**

Round 1 (plain shared-token count after a document-frequency stoplist) looked promising at
first glance — weighted precision rose to 0.55 at k>=6 — but 16 of the 17 pairs the judge
called RELEVANT matched on the user's own workflow boilerplate (`subagents`, `goal`,
`comments`, `ultrawork`, `orchestrate` — words this user's prompts use constantly across
unrelated projects), not on content. Round 2 restricted the shared-token rule to *rare*
tokens (document frequency under 1% of the store) specifically to test whether that removes
the boilerplate artifact. It does remove most of it (14 of 19 RELEVANT pairs in round 2 are
content matches, by a mechanical PF<=5 rule below) — and the precision still does not clear
the bar: **k>=4 pooled precision is 0.28, 95% Wilson [0.19, 0.41], n=60**. The upper bound
of that interval (0.41) is below 0.6, so no plausible re-run of this rule clears it.

**The one sentence a doc should quote:** at the rare-token rule's best-behaved threshold
(k>=4), Level B keyword search has a measured false-positive rate of 0.72 (n=60; precision
0.28, 95% CI [0.19, 0.41]).

---

## 1. Method

### 1.1 The store

```
1453 project dirs, 8301 prompt records, 7716 non-command non-empty prompts
```
Read via `~/.claude/history-surfer/projects/*/prompts.jsonl` (one project slug per
directory, one JSON record per line: `prompt`, `is_command`, `session_id`, `seq`,
`project_slug`, `ts`). Records with `is_command:true` or an empty `prompt` are dropped
before anything else.

### 1.2 Token definition — identical to `toks_of` in `hooks/repeat-gate.sh`

```
hooks/repeat-gate.sh:975-983
toks_of() {
  printf '%s' "$1" \
    | tr -c 'A-Za-z0-9_' '\n' \
    | tr 'A-Z' 'a-z' \
    | awk 'length($0) >= 3 && $0 !~ /^[0-9]+$/' \
    | sort -u \
    | head -60 \
    | tr '\n' ' '
}
```
i.e. lowercased runs of `[A-Za-z0-9_]`, length >= 3, not all digits. The measurement scripts
(`load.py`, `rank3.py`, `rare.py`, `rare2.py`) implement the same rule in Python
(`re.compile(r'[A-Za-z0-9_]+')`, `len(w)>=3 and not w.isdigit()`) with one divergence worth
flagging: the shell function caps at 60 tokens (`head -60`); the Python token sets used for
this measurement are uncapped. A prompt with more than 60 distinct qualifying tokens would
therefore score differently under the real hook than it did in this measurement — untested
how often that happens in the store.

### 1.3 Stoplist derivation (round 1)

`load.py` computes document frequency `df[token]` = number of the 7716 non-command
non-empty prompts containing that token, then `stop.py` writes a stoplist of every token
whose `df` exceeds a document-frequency percentage `X` of `N=7716`:

```
X=30%  ... X=20% ... X=15% ... X=10%  size=50  ... X=5%  size=261  ... X=3%  size=528  ... X=1%
```

Round 1 used the `X=5%` list (261 tokens, `stoplist_5pct.txt`) subtracted from each prompt's
token set before intersecting query and candidate.

### 1.4 Rare-token filter (round 2)

`rare2.py` instead *restricts* to rare tokens: a token counts toward the shared-token score
only if `2 <= df(token) < 0.01 * N` (den <1% of the 7716 non-command prompts; the `>=2`
floor drops hapax legomena, which are usually typos or one-off strings that shouldn't carry
a "this recurred" signal). No stoplist subtraction is used in round 2 — the rarity cutoff
does that job directly, and does it against document frequency computed over the *whole*
prompt-record set (`N` in `rare2.py` counts all `is_command:false`-with-text records,
8301-ish before the non-empty/word-count filters, not the 7716 used in round 1 — see
`rare2_stats.json` for the exact per-project counts this produced).

### 1.5 Queries and candidates

Round 1: the query set is the first substantive (>=6 words) non-command prompt of each
session in one project, truncated to 1200 chars; candidates are substantive prompts from
every *other* project slug (scratchpad slugs under `-private-tmp` excluded). Round 2:
queries are *every* substantive prompt (not just the first-of-session) across three
projects (`skill-compounder` 118 queries, `hypertools` 730, `mapper` 610), scored against
candidates from the other two plus the rest of the store (still excluding `-private-tmp`).

### 1.6 Judge prompt (verbatim, from `mkprompts.py`)

```
Two prompts a developer typed at a coding assistant, from two different projects.

PROMPT A (the request being worked on now):
<<<
{a}
>>>

PROMPT B (an older prompt from a different project):
<<<
{b}
>>>

Would seeing prompt B while working on the request in prompt A help avoid repeating a
mistake or forgetting a constraint? Answer RELEVANT or IRRELEVANT and one sentence.
```
`{a}` and `{b}` are each truncated to 1200 chars. Both rounds used this same template
(round 2's `prompts_rare/` directory was built the same way, pointed at the round-2 sample
instead of the round-1 one — see `level-b/README.md` for the exact regeneration steps,
since that one-line variant of `mkprompts.py` was not saved separately). The judge call
(`judge.sh` / `judge_rare.sh`) runs `claude -p` with `--disallowed-tools` covering every
built-in tool, `--strict-mcp-config`, `--setting-sources ''`, and
`SKILL_COMPOUNDER_DISPATCHED=1` set so this session's own hooks recognize it as a dispatched
sub-call rather than a live session. A pair is scored RELEVANT only if **both** of 2
independent runs answer RELEVANT; any disagreement, or any run whose output could not be
parsed for one of the two labels, counts the pair IRRELEVANT.

---

## 2. Round 1 results — plain shared tokens after the 5% stoplist

60 pairs judged (130 haiku calls: 120 for the sample + 10 extra), stratified 10 per
shared-token-count bucket (`n2`=2, `n3`, `n4`, `n5`, `n6_9`, `n10+`). Run-to-run agreement
49/60.

| bucket | n | relevant | precision |
|-|-|-|-|
| n2 | 10 | 1 | 0.10 |
| n3 | 10 | 0 | 0.00 |
| n4 | 10 | 1 | 0.10 |
| n5 | 10 | 4 | 0.40 |
| n6_9 | 10 | 6 | 0.60 |
| n10+ | 10 | 5 | 0.50 |

Weighted by the true population of surfaced (top-3-per-query) pairs at each threshold, not
just the sample:

| threshold | weighted precision | judged n |
|-|-|-|
| k>=2 | 0.30 | 60 |
| k>=3 | 0.37 | 50 |
| k>=4 | 0.45 | 40 |
| k>=5 | 0.53 | 30 |
| k>=6 | 0.55 | 20 |

Fire rate (fraction of first-of-session queries that surface at least one candidate) was
roughly 86-100% at every k tested, with 68-805 raw candidates per query before any cap.
Jaccard-threshold framing: `jaccard >= 0.15` fires on 4 of 7 sampled sessions, precision
0.38 (n=8).

**Why round 1's apparent 0.55 at k>=6 is not usable:** 16 of the 17 pairs the judge called
RELEVANT under the plain-token rule matched on this user's own recurring workflow
vocabulary — words like `subagents`, `goal`, `comments`, `ultrawork`, `orchestrate` that
appear across nearly every project this user works in — rather than on any topical overlap.
Only one matched on actual shared content. A stoplist tuned at the document-frequency level
(5% of *all* prompts) does not remove a phrase that is common *for this one user* but still
under that global threshold.

---

## 3. Round 2 results — rare-token variant, judged properly

65 pairs judged (130 more haiku calls, 260 total across both rounds). Queries were *every*
substantive prompt (not just first-of-session) across three of this user's projects.
Agreement 59/65.

| metric | value |
|-|-|
| k>=4 pooled precision | 0.28, 95% Wilson [0.19, 0.41], n=60 |
| k>=3 pooled precision | 0.29, 95% Wilson [0.20, 0.41], n=65 |
| rank-1-only precision (k>=4) | 0.24, 95% Wilson [0.14, 0.36], n=55 |

Per project, k>=4:

| project | precision | 95% Wilson CI | n |
|-|-|-|-|
| skill-compounder | 0.50 | [0.30, 0.70] | 20 |
| hypertools | 0.20 | [0.08, 0.42] | — |
| mapper | 0.15 | [0.05, 0.36] | — |

Fire rate (fraction of all substantive queries in that project that surface >=1 candidate)
and mean hits per firing query:

| project | fire rate k>=3 | fire rate k>=4 | queries | mean hits/firing query (k>=4) |
|-|-|-|-|-|
| skill-compounder | 31% | 13% | 118 | 7.9 |
| hypertools | 62% | 46% | 730 | 3.4 |
| mapper | 21% | 11% | 610 | 6.6 |

**Content share of RELEVANT pairs:** decided mechanically — a RELEVANT pair counts as
CONTENT if at least one of its shared tokens appears in <=5 distinct projects
(project-frequency, `PF`, computed over non-`-private-tmp` slugs). 14 of 19 RELEVANT pairs
under the rare-token rule are content matches by this rule (versus 1 of 17 under round 1's
plain rule) — the rarity restriction does what it was meant to do. It still does not buy
enough precision: **k>=4 precision 0.28 [0.19, 0.41] fails the 0.6 bar by a wide margin**,
and the 95% upper bound (0.41) rules out the bar being cleared by a larger sample of the
same rule.

Round 1's apparent 3/5 precision at high thresholds (`n10+` bucket, small early sample) was
one project's phrasing and one-tenth the eventual sample size — not representative once the
sample grew and the rule was corrected for boilerplate.

---

## 4. Limits

1. **Judge is Haiku.** `claude-haiku-4-5-20251001`, chosen for cost (260 calls across both
   rounds); its RELEVANT/IRRELEVANT calls were not cross-checked against a stronger model
   or a human on this sample. Run-to-run agreement (49/60 round 1, 59/65 round 2) puts a
   ceiling on how much the reported precision could be trusted even taken at face value —
   roughly 1 in 6-8 pairs got a different label on a second identical call.
2. **"Relevant" is the judge's reading of one templated prompt, not a human's.** The
   template asks whether prompt B "would help avoid repeating a mistake or forgetting a
   constraint" — a specific framing that may under- or over-count relevance compared to
   other reasonable definitions (e.g. "is this about the same topic").
3. **One user's store, on one machine.** All 8301 records are this user's own prompts
   across their own projects; nothing here says whether the false-positive rate looks the
   same on a different user's store, project mix, or prompting style.
4. **Small n.** 60-65 judged pairs per round is enough to place a Wilson interval but not
   enough to distinguish, say, 0.28 from 0.35 with confidence. The per-project breakdown
   (n=20 for skill-compounder) is smaller still.
5. **Population-weighted precision (round 1's table in section 2) mixes a 60-pair judged
   sample with an unsampled population count** (`pop[bucket]` from the full `pairs_*.json`
   file) — the weighting itself was not judged, only the per-bucket precision rates were.

---

## 5. What would change the verdict

- **A human-labelled subsample** (even 20-30 pairs) cross-checked against the haiku
  verdicts, to bound how much of the 0.28 vs. an assumed "true" precision is judge noise
  versus a real ceiling.
- **A larger n at k>=4 specifically** — the current 95% CI is wide enough ([0.19, 0.41])
  that ruling out 0.6 is solid but the true value inside that range is not pinned down.
- **A combined rule** (rare-token count AND a minimum Jaccard, or rare-token count AND a
  minimum project-frequency gap between query and candidate project) was not tried as a
  single joint threshold in round 2 — only each dimension separately. It's possible a
  conjunction clears more of the boilerplate/content confound than either alone, at some
  cost to fire rate.
- **A second user's store** would settle whether 0.28 is specific to this user's prompting
  style (verbose, workflow-heavy) or general.
- **A stronger judge model** re-run on the same 65 pairs, to separate judge-noise
  disagreement from a genuine precision ceiling.

None of these were run; this is the specific set of follow-ups that would change today's
verdict rather than just restate it.

---

## Appendix: reproduction

Sanitized copies of the scripts used are in `notes/research/level-b/` (`load.py`,
`stop.py`, `rank3.py`, `sample.py`, `mkprompts.py`, `judge.sh`, `rare.py`, `rare2.py`,
`judge_rare.sh`, `score.py`), each with a one-line description in that directory's
`README.md`. Absolute session-scratchpad paths were replaced with a `LEVELB_DIR`
environment variable, and project-slug arguments (which otherwise embed this machine's
home directory, since history-surfer names a project by its cwd with `/` -> `-`) were
moved to `LEVELB_CUR` / `LEVELB_PROJECTS` / `LEVELB_TAG` env vars instead of being
hardcoded.

**The raw judgements, prompt pairs, stoplists, and every intermediate JSON file (`df.json`,
`pairs_*.json`, `sample60.json`, `rare_sample2.json`, `verdicts.json`, `verdicts_rare.json`,
the `judgements/` and `judgements_rare/` directories, `stoplist_5pct.txt`) lived under the
session scratchpad for today's run and are not kept anywhere in this repo** — they contain
this user's actual prompt text. Regenerate with:

```
export LEVELB_DIR=./levelb   # or wherever you want the scratch files
mkdir -p "$LEVELB_DIR"
python3 level-b/load.py                       # writes df.json, prints stoplist sizes
python3 level-b/stop.py                       # writes stoplist_5pct.txt etc from df.json

# round 1 (plain shared tokens after the 5% stoplist), for one project slug:
LEVELB_TAG=<slug>_all python3 level-b/rank3.py <project-slug> notmp
QMODE=first LEVELB_TAG=<slug>_first python3 level-b/rank3.py <project-slug> notmp
python3 level-b/sample.py                     # LEVELB_TAG must match rank3.py's tag
python3 level-b/mkprompts.py
for f in "$LEVELB_DIR"/prompts/*.txt; do
  pid=$(basename "$f" .txt)
  LEVELB_DIR="$LEVELB_DIR" level-b/judge.sh "$pid" 1
  LEVELB_DIR="$LEVELB_DIR" level-b/judge.sh "$pid" 2
done
python3 level-b/score.py

# round 2 (rare-token variant, all substantive prompts, three projects):
LEVELB_PROJECTS=<slug1>,<slug2>,<slug3> python3 level-b/rare2.py
# then build prompts_rare/ from rare_sample2.json the same way mkprompts.py builds
# prompts/ from sample60.json (see level-b/README.md), and run judge_rare.sh the same
# way as judge.sh above, then re-run the parse/agree logic in score.py against
# judgements_rare/ and rare_sample2.json.
```
