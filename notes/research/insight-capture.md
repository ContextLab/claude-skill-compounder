# Automatic insight capture — feasibility investigation

**Date:** 2026-08-24 (machine local; transcript timestamps below are UTC, so the newest
records read `2026-08-25`).
**Machine:** darwin 25.5.0, Claude Code `2.1.243 (Claude Code)`.
**Scope:** can `★ Insight` blocks (or an equivalent signal) be captured automatically from
a Claude Code session, queued as skill candidates, and labelled UNIVERSAL vs LOCAL?

Every number below is from a command run on this machine. Commands and their real output
are reproduced verbatim. Section 8 lists what could **not** be verified.

---

## VERDICT

**Feasible only in a modified form.**

Capture is solidly feasible — the marker is verbatim in the transcript, the exact record
shape is known, and every relevant hook receives `transcript_path` (Stop and SubagentStop
additionally receive `last_assistant_message`, which alone catches 76% of blocks).

The two parts of the spec that do **not** survive contact with the data:

1. **`★ Insight` is not a signal of reusable knowledge.** It is a signal of *any*
   commentary, emitted 2–3 times per code-writing turn by design. 197 unique blocks in 46
   days, and a burst week of **115**. Hand-reading a sample, the large majority are session
   narrative about one repo's bug, not transferable procedure. An auto-forge on this signal
   would be a firehose.
2. **UNIVERSAL/LOCAL cannot be decided by identifier matching.** I built the proposed rule
   (does the insight name tokens that exist in the current repo's `git ls-files`?) and
   scored it against 14 hand-read insights: **7/14 correct — chance.** The failures are
   overwhelmingly LOCAL-scored-as-UNIVERSAL, the dangerous direction.

The modified form that *is* supportable: a **cheap, style-independent, transcript-derived
candidate queue** that never forges on its own, plus an **explicit marker the session
calls** for the high-signal path. Design in section 7.

---

## 1. Where assistant output lives on disk

```
$ ls -d ~/.claude/projects/*/ | head -5
/Users/jmanning/.claude/projects/-Users-jmanning-alzheimers-case-study/
/Users/jmanning/.claude/projects/-Users-jmanning-autoresearch/
/Users/jmanning/.claude/projects/-Users-jmanning-claude-history-surfer/
/Users/jmanning/.claude/projects/-Users-jmanning-claude-skill-compounder/
/Users/jmanning/.claude/projects/-Users-jmanning-clustrix/

$ ls -d ~/.claude/projects/*/ | wc -l
      31
$ find ~/.claude/projects -name '*.jsonl' | wc -l
    1447
$ du -sh ~/.claude/projects
2.4G	/Users/jmanning/.claude/projects
```

One directory per project, named by the cwd with `/` → `-`. One `<session-uuid>.jsonl` per
session, plus a sibling `<session-uuid>/subagents/agent-*.jsonl` directory for subagent
transcripts. Files are large: the biggest single transcript here is **663 MB**.

```
$ find ~/.claude/projects -name '*.jsonl' -size +5M -exec ls -lh {} \; | awk '{print $5,$9}' | sort -rh | head -3
663M /Users/jmanning/.claude/projects/-Users-jmanning-hypertools/7e6531b3-...jsonl
188M /Users/jmanning/.claude/projects/-Users-jmanning-llmXive/4df702ee-...jsonl
81M  /Users/jmanning/.claude/projects/-Users-jmanning-orchestrator/d754cb98-...jsonl
```

### Record types in one real transcript

```
$ jq -r '.type' f0feae4c-834a-409b-8e25-9a2894341168.jsonl | sort | uniq -c
  10 ai-title
  61 assistant
  16 atis-latch
 200 attachment
  16 bridge-session
   1 file-history-delta
   2 file-history-snapshot
  16 last-prompt
  16 mode
  16 permission-mode
   4 queue-operation
   2 system
  37 user
```

### Exact record shape for assistant text

```
$ jq -c 'select(.type=="assistant") | keys' <transcript> | head -1
["attributionSkill","cwd","effort","entrypoint","gitBranch","isSidechain","message",
 "parentUuid","requestId","sessionId","session_id","timestamp","type","userType","uuid","version"]

$ jq -c 'select(.type=="assistant") | .message | keys' <transcript> | head -1
["content","diagnostics","id","model","role","stop_details","stop_reason","stop_sequence","type","usage"]

$ jq -r 'select(.type=="assistant") | .message.content[]?.type' <transcript> | sort | uniq -c
   5 text
  23 thinking
  33 tool_use
```

**The load-bearing path is `.message.content[] | select(.type=="text") | .text`** on records
where `.type == "assistant"`. Useful siblings on the same record: `.timestamp` (ISO-8601
UTC), `.cwd`, `.gitBranch`, `.isSidechain`, `.sessionId`, `.uuid`, `.parentUuid`.

---

## 2. Can a hook see it?

I captured **real** payloads by running two headless sessions against a throwaway settings
file whose hooks dump stdin. Not from memory — these are the measured key sets on CLI
2.1.243.

```
$ claude -p "Run the bash command 'echo hello-hooktest' and then reply with exactly: DONE" \
    --settings .../settings.json --permission-mode bypassPermissions --model haiku
DONE
```

Measured payload keys (`transcript_path` present in **every** event):

| Event | Measured keys |
|-|-|
| `SessionStart` | `cwd, hook_event_name, session_id, source, transcript_path` |
| `UserPromptSubmit` | `cwd, hook_event_name, permission_mode, prompt, prompt_id, session_id, transcript_path` |
| `PostToolUse` | `cwd, duration_ms, hook_event_name, permission_mode, prompt_id, session_id, tool_input, tool_name, tool_response, tool_use_id, transcript_path` |
| `Stop` | `background_tasks, cwd, hook_event_name, **last_assistant_message**, permission_mode, prompt_id, session_crons, session_id, stop_hook_active, transcript_path` |
| `SubagentStart` | `agent_id, agent_type, cwd, hook_event_name, prompt_id, session_id, transcript_path` |
| `SubagentStop` | `agent_id, **agent_transcript_path**, agent_type, background_tasks, cwd, hook_event_name, **last_assistant_message**, permission_mode, prompt_id, session_crons, session_id, stop_hook_active, transcript_path` |
| `SessionEnd` | `cwd, hook_event_name, prompt_id, **reason**, session_id, transcript_path` |

Sample verbatim `Stop` payload (redacted to keys + a few values):

```json
{"EVENT":"Stop","keys":["background_tasks","cwd","hook_event_name","last_assistant_message",
 "permission_mode","prompt_id","session_crons","session_id","stop_hook_active","transcript_path"],
 "transcript_path":"/Users/jmanning/.claude/projects/-private-tmp-.../2172061a-....jsonl",
 "cwd":"/private/tmp/.../hooktest","session_id":"2172061a-63c3-4cdc-900c-811fb8f4e489",
 "hook_event_name":"Stop","stop_hook_active":false,"permission_mode":"bypassPermissions"}
```

### Official docs (https://code.claude.com/docs/en/hooks)

Docs confirm and add:

> "Hooks that need the final assistant text of the current turn should use
> `last_assistant_message` on Stop and SubagentStop instead of reading the transcript"

`PreCompact` documented input:

```json
{"session_id":"abc123","transcript_path":"...","cwd":"...","permission_mode":"default",
 "hook_event_name":"PreCompact","compaction_trigger":"auto"}
```

### Two measured discrepancies with the docs — trust the measurement

- **`SessionEnd`**: docs show `session_end_reason`; the CLI 2.1.243 payload I captured has
  **`reason`** (value `"other"`). A hook reading `session_end_reason` would get `null`.
- **`SubagentStop`**: docs do not list `agent_transcript_path`; the real payload has it.
  It points at the subagent's own `.../subagents/agent-*.jsonl`.

`PreCompact` was **not** captured empirically (see section 8).

---

## 3. Do `★ Insight` blocks appear verbatim? — YES

```
$ grep -rl '★ Insight' ~/.claude/projects/ | wc -l
      27
$ grep -roh '★ Insight' ~/.claude/projects/ | wc -l
     854
```

But the raw 854 is misleading. Broken down by the record that carries the string:

```
$ for f in $(grep -rl '★ Insight' ~/.claude/projects/); do
    jq -rc 'select(.. | strings? | test("★ Insight")) |
      [.type,(.message.role//"-"),((.message.content?|if type=="array" then [.[].type]|join("+") else type end)//"-"),(.isSidechain//false)]|@tsv' "$f"
  done | sort | uniq -c | sort -rn
 584 attachment	-	null	false
 265 assistant	assistant	text	false
   3 assistant	assistant	tool_use	true
   1 user	user	tool_result	false
   1 user	user	string	true
   1 assistant	assistant	tool_use	false
```

The 584 `attachment` records are **not** insights — they are the output-style plugin's own
SessionStart injection being echoed back:

```
$ ... | jq -r '.attachment.type'          →  323 hook_success / 261 hook_additional_context
$ ... | jq -r '[.attachment.hookName,.attachment.hookEvent]|@tsv'
 261 SessionStart	SessionStart
 231 SessionStart:compact	SessionStart
  62 SessionStart:resume	SessionStart
  24 SessionStart:startup	SessionStart
   6 SessionStart:clear	SessionStart
```

**Any capture implementation MUST filter to `.type=="assistant"` + `content[].type=="text"`
or it will re-ingest its own instruction text 2–3× per session.**

### Verbatim format

```
$ python3 ... print(repr(text_around_marker))
"...This is the highest-leverage change in Phase 1.\n\n
 `★ Insight ─────────────────────────────────────`\n
 **PEP 562** lets a *module* define `__getattr__`, called only when an attribute isn't
 found normally....\n
 `─────────────────────────────────────────────────`"
```

Opener and closer are **backtick-wrapped** lines:

- open:  `` `★ Insight ─────…` `` (U+2605 star, U+2500 box-drawing run)
- close: `` `─────…` `` (backtick + U+2500 run + backtick), length not fixed

Working regex (used for every count in this document):

```python
OPEN  = re.compile(r"`?★ Insight[ ─]*`?\n")
CLOSE = re.compile(r"\n`?─{5,}`?")
```

### Where the marker comes from — and it IS style-dependent

```
$ jq '.outputStyle' ~/.claude/settings.json                 → NOT SET
$ python3 -c "... ~/.claude.json ..."
top-level outputStyle: None
per-project outputStyle: [(None, 293)]
$ ls ~/.claude/output-styles                                → No such file or directory
```

No output style is configured anywhere. The marker instead comes from an enabled **plugin**:

```
$ grep -o '"[a-z-]*output-style[^"]*"[^,}]*' ~/.claude/settings.json
"learning-output-style@claude-plugins-official": true
```

whose SessionStart hook injects the instruction as `additionalContext`:

```
$ cat ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/explanatory-output-style/hooks-handlers/session-start.sh
# Output the explanatory mode instructions as additionalContext
# This mimics the deprecated Explanatory output style
... "## Insights\nIn order to encourage learning, before and after writing code, always
provide brief educational explanations about implementation choices using (with backticks):
\"`★ Insight ─────────────────────────────────────`\n[2-3 key educational points]\n
`─────────────────────────────────────────────────`\"" ...
```

**Plainly: if that plugin is disabled, the signal disappears entirely.** It is enabled
globally on this machine today, which is why every project shows insights. The classic
`Explanatory`/`Learning` output styles are described in that file as *deprecated*.

Second hard limit — **subagents never emit them**:

```
$ find ~/.claude/projects -path '*/subagents/*.jsonl' | wc -l
    1428
$ python3 ... count assistant-text insights in subagent transcripts ...
subagent transcripts with assistant-text insights: 0 blocks: 0
```

1428 subagent transcripts, **zero** insight blocks. The SessionStart injection does not
reach subagents. A `SubagentStop`-based capture would harvest nothing.

---

## 4. Volume / noise reality check

```
$ python3 extract2.py
total insight blocks: 266
unique bodies: 197
body chars: min 247  median 611  mean 621  max 1214
date range: 2026-07-11 -> 2026-08-25
span days: 46 | unique per day: 4.3 | unique per 7-day week: 30.0
busiest actual 7-day window: 115
sidechain(subagent) share: 0 / 197
```

Turn-level density:

```
$ python3 ... segment turns ...
turns containing >=1 insight: 224
  of those, final assistant text of the turn contains an insight: 203 (91%)
insight blocks total: 267 | located in the turn's final assistant text: 204 (76%)

$ python3 ... count real (non-tool-result) user turns across all transcripts ...
real (non-tool-result) user turns: 4651
```

**The real number: ~30 unique insights per week on average, 115 in the busiest real
7-day window.** 224 / 4651 = **4.8%** of turns produce one.

That settles the architecture question in the brief: at 30–115/week this **must be a
filtered queue reviewed in batch, not an auto-forge**. Forging even 10% of them would
produce 3–11 skills a week, which is faster than any human can red-team or than the skill
list can absorb.

Two derived facts that matter for the hook design:

- `last_assistant_message` on `Stop` catches **204/267 = 76%** of blocks and **203/224 =
  91%** of insight-bearing turns — with **zero** transcript I/O.
- The remaining 24% are mid-turn (the instruction says "Do not wait until the end"), and
  need a transcript read to recover.

Transcript read cost is not a problem:

```
$ full grep scan of 663MB: 0.03s     (warm page cache)
$ tail 500KB scan: 0.041s
```

---

## 5. Are the insights actually reusable knowledge? (read, not assumed)

Six random unique insights, verbatim opening lines:

1. `/Users/jmanning/clustrix` — "The failure mode here is worth generalizing: pytest didn't
   warn, because from its perspective nothing was wrong … finding a config file stops the
   search, so the valid config sitting in `pyproject.toml` became unreachable."
2. `/Users/jmanning/contextlab.github.io` — "`people.html` is **auto-generated** from
   `data/people.xlsx` (CLAUDE.md: never hand-edit it)."
3. `/Users/jmanning/orchestrator` — "Every authority denial test picks a grant form
   (`out/`, `elsewhere/`, `example.com`) that happens to lack a trailing `*` …"
4. `/Users/jmanning` — "The sidebar isn't Finder's data — Finder is just a client of
   `sharedfilelistd`, which owns the favorites list and only reads the `.sfl4` file at
   startup."
5. `/Users/jmanning/hypertools` — "The mechanism is aliasing, not copying.
   `xform_data = copy.copy(xform)` is a *shallow* list copy …"
6. `/Users/jmanning/llmXive` — "`standard_generation` carries `max_candidates=8`, but the
   other five profiles still default to `4`."

Reading these: #1 and #4 are genuinely portable. #2 and #6 are pure project trivia. #3 and
#5 are a **universal kernel wrapped in local evidence** — "a test suite can be correlated
with the implementation's assumptions"; "shallow copy plus rebinding leaves an alias".

That third category is the majority, and it is why a *binary* UNIVERSAL/LOCAL label on the
raw text is the wrong question. The right question is *"is there a universal kernel here,
and what is it once the repo names are stripped?"* — and answering it requires rewriting
the text, which is an LLM operation, not a string operation.

---

## 6. UNIVERSAL vs LOCAL — the proposed cheap rule, built and measured

### The rule as sketched in the brief

1. Extract every backticked span from the insight body (plus dotted/slashed sub-tokens).
2. Build a repo index: `git -C <cwd> rev-parse --show-toplevel` → `git ls-files`, indexing
   full paths, basenames, stems, and every path segment, lowercased.
3. `frac = |identifiers found in index| / |identifiers|`.
4. `frac >= 0.34` → LOCAL, else UNIVERSAL.

Implemented in full (`classify.py` in scratch, not committed per instructions).

### Bulk output

```
$ python3 classify.py
classification over 197 unique insights: {'UNIVERSAL': 162, 'LOCAL': 35} | cwd not a git repo: 66
```

**66 of 197 (34%) could not be scored at all** — the recorded `cwd` is a git worktree, a
scratchpad under `/private/tmp`, or a non-repo directory, so `git ls-files` returns
nothing and the rule silently defaults to UNIVERSAL. That alone disqualifies it.

### Accuracy against hand-read labels

I hand-labelled 14 insights by reading them in full, then scored the rule.

Batch A (seed 11, 8 insights) — 5/8 agreement. Batch B (seed 101, 6 insights):

```
MISS heuristic=LOCAL     hand=UNIVERSAL idhits=1/1 repo=/Users/jmanning/clustrix
OK   heuristic=LOCAL     hand=LOCAL     idhits=3/3 repo=/Users/jmanning/contextlab.github.io
MISS heuristic=UNIVERSAL hand=LOCAL     idhits=0/4 repo=/Users/jmanning/orchestrator
OK   heuristic=UNIVERSAL hand=UNIVERSAL idhits=0/2 repo=None
MISS heuristic=UNIVERSAL hand=LOCAL     idhits=0/3 repo=/Users/jmanning/hypertools
MISS heuristic=UNIVERSAL hand=LOCAL     idhits=0/6 repo=/Users/jmanning/llmXive
agreement: 2/6
```

**Total: 7/14 = 50%, i.e. chance on a binary label.**

The failure modes are diagnostic, not tunable:

- **Generic filenames poison the index.** The clustrix insight was scored LOCAL because it
  says `` `pyproject.toml` `` and clustrix has a `pyproject.toml`. Every Python repo does.
  The insight is about pytest's config-discovery semantics and is fully portable.
- **Local insights that name no files score UNIVERSAL.** #3 and #6 above are about one
  repo's bug and one repo's config profiles; they reference concepts and issue numbers
  (`#433`), not tracked paths. Errors run **LOCAL → UNIVERSAL**, which is the direction
  that pollutes the global skill set.
- **A third of records have no usable repo at all** (worktrees, scratchpads).

Raising the threshold trades one failure for the other; there is no operating point that
fixes both, because the feature (does the text name a tracked path?) is nearly orthogonal
to the label (is the lesson portable?).

**Conclusion: no, this cannot be done by string matching against the repo. It needs a
model — or it needs to not be a classification problem at all (see 7.3).**

---

## 7. Recommended design

### 7.1 The three candidate signals, honestly compared

| Option | Style-independent? | Cost | Precision | Verdict |
|-|-|-|-|-|
| **A. `★ Insight` scrape** | **No** — dies if `learning-output-style` is disabled; never fires in subagents (0/1428) | ~0 (76% free on `last_assistant_message`) | Low: 30–115/wk, majority local narrative | Use as an *opportunistic* feeder only |
| **B. Explicit marker the session calls** (`skillforge note "…"` or a `LEARNED:` line) | **Yes** | ~0 | High — the session only calls it when it means it | **Primary signal** |
| **C. Stop-hook LLM classification pass** | Yes | 1 model call per turn × 4651 turns/46d ≈ **100/day**; at ~2k in/200 out on Haiku this is real money and real latency on *every* turn | Best, but 95% of calls see no insight | Reject as a per-turn hook; acceptable as a **batched weekly triage** over the queue |
| **D. Transcript heuristics** (error→fix cycles, repeated tool failures, "the trap was…") | Yes | ~0 | Untested here — see section 8 | Interesting, unproven; do not build on it yet |

### 7.2 Recommended architecture — a queue, not a forge

```
  Stop hook (already exists as compound-improvement.sh)
        │  read $.last_assistant_message  → 76% of blocks, zero I/O
        │  if the marker count in it < the count in the turn, tail -c 2M the
        │  transcript and recover the mid-turn ones (24%)
        ▼
  append JSONL to ~/.claude/skill-compounder/insights/<YYYY-WW>.jsonl
        {ts, session_id, cwd, git_toplevel, git_branch, body, sha, source:"insight"|"marker"}
        dedupe by sha1(body); cap the file; never block the turn (exit 0 always)
        ▼
  `skillforge review`  — an explicit, human/agent-initiated batch pass
        one LLM call over the *week's* queue (not per turn), which:
          (a) drops pure session narrative,
          (b) for survivors, rewrites the universal kernel with repo names stripped,
          (c) emits UNIVERSAL / LOCAL / DISCARD *with the rewritten kernel as evidence*
        ▼
  survivors become skill-compounder candidates and go through the existing
  builder/red-team loop. Nothing is ever forged automatically.
```

Why this shape:

- The per-turn hot path stays free (a string count on a field already in the payload).
- The LLM cost lands on ~30–115 items **once a week**, not on 4651 turns.
- UNIVERSAL/LOCAL stops being a pre-filter on raw text and becomes an *output* of the same
  pass that already has to rewrite the kernel — which is the only way the mixed majority
  can be handled at all.

### 7.3 The classification rule, restated so it is answerable

Do not ask "is this text universal?". Ask the reviewer, per candidate:

1. Rewrite the lesson with every repo-specific name replaced by a role
   (`compiler/schema_validator.py` → "a second validator module").
2. If the rewrite still states something actionable → **UNIVERSAL**, and *the rewrite* is
   the skill candidate, not the original text.
3. If the rewrite collapses to a tautology or to nothing → **LOCAL**; file it into that
   repo's `CLAUDE.md` / notes instead of the global skill set.
4. If it collapses entirely → **DISCARD**.

The cheap `git ls-files` overlap is still worth computing — not as the label, but as a
*sort key* so the reviewer reads the most-likely-universal candidates first, and as the
routing target for step 3 (which repo's notes does a LOCAL item belong to).

### 7.4 Implementation notes that will otherwise be rediscovered painfully

- **Filter to `.type=="assistant"` and `content[].type=="text"`.** 584 of the 854 raw
  marker hits are the plugin's own SessionStart injection. Naive `grep` self-ingests.
- **The delimiters are backtick-wrapped and variable-length.** `^─{3,}$` does not match;
  use `` `?★ Insight[ ─]*`?\n `` … `` \n`?─{5,}`? ``.
- **`SessionEnd` gives `reason`, not the documented `session_end_reason`** on 2.1.243.
- **Never attach capture to `SubagentStop`** — 0 blocks in 1428 subagent transcripts.
- **Timestamps are UTC**; weekly bucketing on local dates will split sessions.
- **`cwd` is often a worktree or `/private/tmp` scratchpad** (34% of records). Resolve to
  `git rev-parse --show-toplevel` and store both, or provenance is lost.
- **Transcripts reach 663 MB.** Never read one whole in a hook; `tail -c` a bounded window.
- The existing `hooks/compound-improvement.sh` already has the right skeleton — per-session
  state under `$SKILL_COMPOUNDER_STATE/reminders`, `exit 0` on every failure path,
  `CI_DEBUG_DUMP` for payload inspection. Capture should reuse it, not duplicate it.

---

## 8. What I could NOT verify

1. **`PreCompact` payload, empirically.** I could not trigger compaction from a headless
   `claude -p` run. The field list in section 2 for `PreCompact` is from the official docs
   only — and given that the docs were *wrong* about `SessionEnd.reason` on this CLI
   version, `compaction_trigger` should be re-checked against a live payload before any
   code depends on it.
2. **Whether the `outputStyle` key in `settings.json` still works.** I passed
   `{"outputStyle":"Explanatory"}` via `--settings` and the run produced no insight blocks —
   but the model was Haiku on a trivial task, so this is not evidence either way. The
   plugin's own file calls the built-in styles "deprecated". Unresolved.
3. **Option D (style-independent transcript heuristics).** I did not build or measure any
   error→fix-cycle detector. The "untested" verdict in the table is exactly that; I have no
   precision/recall numbers for it.
4. **Whether 30/week generalizes.** All 197 insights are from one user on one machine over
   46 days. The 115-per-week burst came from two projects (`orchestrator`, `hypertools`).
5. **Cold-cache transcript scan time.** The 0.03 s for 663 MB was measured with a warm page
   cache; I did not purge and re-measure.
6. **Hand labels are mine alone.** The 7/14 accuracy figure rests on 14 insights I labelled
   by reading. A second labeller would likely disagree on the "mixed" cases — which is
   itself part of the finding that the binary label is ill-posed.
7. **`Stop` fired twice** in the subagent test run for a single `-p` prompt. I did not
   determine why (Task-tool inner loop?). Any per-turn counter must be idempotent.

---

## Appendix: reproduction

Scratch scripts used (deliberately not committed to this repo):
`extract2.py` (marker extraction + volume stats), `classify.py` (the identifier heuristic),
`hooktest/dump.sh` + `settings.json` (real hook payload capture). All under
`/private/tmp/claude-501/-Users-jmanning-claude-skill-compounder/<session>/scratchpad/`.
Regenerate with the commands quoted inline above.
