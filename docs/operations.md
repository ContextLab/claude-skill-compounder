# Operations

What you type once the package is installed, and what it keeps on disk while it runs.
[`architecture.md`](architecture.md) says what the pieces are;
[`README.md`](../README.md) covers installing, updating and removing them.

## Checking the install, and closing out a forge

`skillforge doctor` is the command to run first whenever something seems not to be firing.
The rest below it are for a forge that is running, or one that stopped without saying so.

```bash
skillforge start demo 4 "checking that the animation renders"
skillforge step 2 "red-team round 1"
skillforge done "clean"                     # closes the record AND installs the skill
skillforge install demo [--skill-dir DIR]   # the retry path when that install did not happen
skillforge clear     # escape hatch if a forge is ever left open
skillforge doctor    # one PASS/WARN/FAIL line per check; exit 1 on any FAIL
skillforge reap [--name <forge>]   # close every forge idle past SKILLFORGE_ACTIVE_TTL
```

A forge orchestrator has been killed by the host going to sleep, and the forge it left
behind stayed `active` for three and a half days. Nothing resumes one: the ledger counts
it as never closed out, and its name is held against the next `skillforge start`.
`skillforge reap` appends the `fail` row it is missing, which closes the ledger join and
frees the name in one append — nothing is edited and nothing is deleted. It only ever touches a forge that has been idle longer than
`SKILLFORGE_ACTIVE_TTL`, six hours by default, and that is **idle** time rather than
elapsed time, measured since the last `skillforge step`. A six-hour cap on elapsed time
would close a forge that was still working; a six-hour gap between steps is longer than
any healthy forge here has lived. `--name` narrows which forges are considered and does not
lower the bar. `skillforge start` on a name held by a forge past the TTL reaps it and says
so, instead of refusing.

`skillforge doctor` is the health check for everything else, and it runs eleven checks in
one fixed order — jq, state, settings, statusline, skills, surfer, ledger, counters,
forges, mission, review — in the text form and under `--json` alike, so the two cannot
report different counts. Run `bash bin/skillforge doctor` and read the trailing
`N pass, N warn, N fail` line rather than trusting this list. Three of those rows exist for
the mission: `surfer` says whether the dependency `hooks/mission.sh` reads its prompts from
is present, `mission` says whether anything has been delivered, and `review` is the only
surface that reports which way `SKILL_COMPOUNDER_REVIEW` is set.
Every hook here opens with `command -v jq || exit 0`, so a missing jq or
a state directory gone read-only stops all of it with nothing said anywhere — from
outside, indistinguishable from a package that had nothing to report.

Closing a forge installs the skill. A skill that has been written but not linked into
`~/.claude/skills/` cannot be invoked by anything, so `done` looks for
`skills/<name>/SKILL.md` and `.claude/skills/<name>/SKILL.md` under the repository the
forge started in, links what it finds, and prints one line saying what happened either
way. Three cases it does not treat as a plain success: a forge that produced no SKILL.md
at all (a fix, a retirement, a red-team round), a skill already sitting under a repo's own
`.claude/skills/`, which is live for that project and would have its scope widened by a
personal link, and a name already taken by something this package cannot prove it wrote.
`done` still exits 0 in all of them, because the forge did close; `skillforge install`
exits non-zero, because there the install is the request. `SKILLFORGE_NO_INSTALL=1` skips
the step entirely.

## Capturing candidates as you go

A session that notices something worth keeping can queue it instead of stopping to forge:

```
★ Skill candidate: <the procedure, in one paragraph>
```

A `Stop` hook picks that up from `last_assistant_message`, falling back to a bounded tail
of the transcript when the message alone does not carry it, and appends it to a weekly
queue, deduped. `★ Insight` blocks are picked up too, as an opportunistic feeder rather
than the mechanism: they exist only because a particular output-style plugin injects
them, and subagents never emit any.

A second hook reads the same two signals on `PreCompact`, the moment before a compaction
replaces the session's context with a summary. It is there for the case `Stop` cannot
cover: a session that compacts without a `Stop` capture in between loses that turn, and a
session only compacts when it is carrying a lot. Its rows carry `source: precompact`, so
`skillinsight list --source precompact` selects them and `skillinsight decline --source
precompact` retires the lot if they turn out to be noise.

There is no model in it, and the reason was measured. A `PreCompact` hook blocks the
compaction: a 300-second hook stalled one for 300.9 seconds and ran to completion, and
putting a timeout on it instead killed a writer mid-write and left a truncated `CLAUDE.md`
that the next session then loaded as project context with no error. So this hook
tails the transcript, runs the same extractor, appends, and exits.

What it spends is process starts rather than bytes, so **the cost is per `jq` build** and
the budget is stated per build. The two builds on the measuring machine were interleaved
run for run, so a loaded box charged each alike: 400 KB transcript at the default 256 KB
bound, macOS 25.6.0, 2026-09-03, n=25, wall-clock median / p90.

|jq|no candidate|one candidate|
|-|-|-|
|`/usr/bin/jq` (jq-1.7.1-apple)|31.8 / 36.0 ms|84.7 / 87.7 ms|
|anaconda's jq-1.6 on `PATH`|59.1 / 63.5 ms|123.0 / 128.9 ms|

The 100 ms budget holds on the system jq at the median and at p90, and is missed by about
a quarter on jq-1.6, which cannot be made to fit — what was tried, and what it would cost,
is in [measurement.md](measurement.md). Two costs to know either way: the hook fires even
when the compaction is then refused for having too little to compact, and it blocks the
compaction while it runs. Nothing writes `CLAUDE.md` from a hook — that is `skillinsight
promote` and `skillnote`, under your judgement.

Neither hook can double-queue the other's find. The queue is addressed by a hash of the
normalised candidate text and both hooks compute it the same way, so whichever runs first
writes the row and the other counts a duplicate.

Review the queue in one batch, once a week, not once a turn:

```bash
skillinsight list          # one line per candidate, this week by default
skillinsight pending       # what is queued and undeclined right now
skillinsight review        # emit the batch, with the reviewing instructions
skillinsight decline <hash> [--why <why>]   # judged and declined; the record is kept
skillinsight decline --source <src> [--week <ISO-week>] [--dry-run]
                           # the same judgement over every undeclined record from one source
skillinsight promote <hash> --to note|reminder   # write it down now instead of forging it,
                                                 # and print the lineage id it stamps
skillinsight snooze [<days>] | --clear      # stop announcing the queue without judging it
skillinsight reviews [--show <n>] [--all]   # the automatic session reviews, newest first
skillinsight reindex       # recovers a paid-for verdict that never reached index.jsonl
skillinsight stats
skillinsight prune --older-than 8   # archives old week files, never deletes them
```

`reindex` exists because a dispatch that dies mid-flight leaves its answer on disk and no
row anywhere: it reads the stage-1 files `hooks/session-review.sh` left behind and appends
the row each one never got. Whether a review has been recovered is answered by reading
`index.jsonl` itself, so a second run appends nothing, and the stage-1 file is kept rather
than deleted because it is the evidence the row is checked against.

The review step rewrites each candidate with repo-specific names stripped, which is the
operation that actually matters. Most insights are a universal kernel wrapped in local
evidence, so extracting the kernel is the useful move and the universal-or-local label is
a judgement made during review.

There is no automatic classifier. A rule matching backticked identifiers against
`git ls-files` scores **7 out of 14, which is chance**, and over a larger sample 34% of
records cannot be scored at all. The measurements are in
[`notes/research/insight-capture.md`](../notes/research/insight-capture.md).

**`promote` says where the note is going before it writes it.** A candidate is recorded
against the project it was noticed in, and that is the project it promotes into — which is
very often not the directory you are standing in. Until it said so, a promote run from a
scratch directory wrote a note into a repository the caller was not in and reported only
"promoted". The first line of output is now `skillinsight: target <absolute path>`, and the
path is asked of `skillnote where` rather than recomputed, because a second copy of the four
scope resolutions would drift from the first and both halves would still print something.

It also refuses rather than creating a tree nobody will read. `skillnote` creates the
`.claude/` directory but not the project above it, so a candidate recorded against a project
that has since been deleted or moved would otherwise have that whole path conjured up around
a note nobody will ever load. Promote exits non-zero naming the missing directory, and
`--project <dir>` is the way out — it overrides the recorded project for that run.

```bash
skillnote where [--scope project|global|memory|remind] [--project <dir>]
```

`skillnote where` is the read-only half of that: it prints the one path a note or reminder at
that scope would land in and creates nothing. It exists so the two CLIs answer the question
once, in the CLI that does the writing.

Nothing here auto-forges. The queue feeds the same threshold as everything else.

## Following one candidate through

A queue record, the note it becomes, the reminder that delivers that note, the forge that
follows and the verdict on it all carry **one id**. Before it existed, no figure in this
package could say which delivery produced which outcome: anything spanning two stores was
reconstructed by counting one of them and dividing.

The id is derived rather than minted — `c` and the first eight characters of the queue
record's hash, or `v` and eight for a session-review verdict — so a record queued before any
of this shipped already has one, and nothing was backfilled. `skillinsight promote` prints
it and stamps it on the note and the reminder it writes:

```bash
skillinsight promote <hash> --to note                       # prints: lineage c1a2b3c4
skillnote add --candidate c1a2b3c4 "<what was learned>"     # by hand, the same id
skillforge start <name> <steps> "<summary>" --from c1a2b3c4 [--session <id>]
skillforge origin --name <skill> --origin forged --from c1a2b3c4
```

**A missing `--from` warns and is never refused**, on `--trigger`'s argument: a CLI that
refuses is one callers stop calling, and most forges descend from nothing at all because
nobody queued them. A forge started without one is recorded as carrying none and counted
as `UNATTRIBUTED`. An id that is *malformed* is a different case and does exit non-zero —
the charset is `[A-Za-z0-9._-]` and the length 64 — because the id is only ever compared
for equality, so one carrying a space or a quote joins to nothing and reports as a lineage
that was delivered and never acted on.

`--session` defaults to `$CLAUDE_CODE_SESSION_ID`. Neither `skillforge apply` nor
`skillforge verdict` needs the id typed again — `apply` never takes one and `verdict` falls
back when none is given, and both read it off the forge's own `start` or `origin` row.
A verdict written by hand months later is the moment nobody remembers which record began
it, and a field a caller has to retype is a field that goes unrecorded.

Two blocks of `skillreport` read the chain back. **FUNNEL** prints one line per lineage —
`DELIVERED`, `ACTED ON`, `OUTCOME` — and prints its own definition under the table rather
than leaving it here to drift:

```
DELIVERED counts rows in the two delivery logs. ACTED ON and OUTCOME PARTITION the
ledger: every note/start/use/apply/verdict row is attributed to AT MOST ONE lineage,
by the first of these that holds — its own `from`, its own `candidate`, a note row
whose own id is a delivered lineage, or the lineage delivered FIRST to the session it
was written in (ties by id). ACTED ON counts the note/start/use/apply rows so
attributed; OUTCOME counts the verdict rows.
```

**A partition is a checkable claim, so the block checks it and prints the arithmetic.** The
last line is a `CHECK:` reading `<n> row(s) in the table + <n> unattributed = <n>
note/start/use/apply/verdict row(s)`, and when those do not balance it says `CHECK FAILED`
and names itself as the defect rather than the ledger. It was not a partition twice over, and
both halves showed on the live store: a row whose `from` named a lineage no delivery log knew
was excluded from `UNATTRIBUTED` for carrying an id and excluded from the table for not being
a delivered lineage, so it was counted nowhere; and a row was counted once for *every*
lineage delivered to its session, so `ACTED ON` summed to 104 against 69 `DELIVERED` — the
figures `bin/skillreport`'s header records from the live store — and no reader could say
what the column totalled. Listing every lineage any store names, with
`DELIVERED 0` where nothing delivered it, fixes the first; attributing each row exactly once
fixes the second. The table shows the first 25 lineages and folds the rest into a
`(+n more)` row carrying their counts, so nothing below it is computed over a subset.

The session clause is the weak one and is labelled where it prints: a session that was
reminded and then forged is evidence of a sequence, not of a cause, and a session that
received two lineages gives its rows to whichever was delivered there first, which makes that
half of `ACTED ON` a floor for the other lineage. **REMINDER CONVERSION** is
counted now instead of reconstructed: `hooks/compound-improvement.sh` writes every nudge it
delivers to `<state>/reminders/nudges.jsonl`, and one converts when a `start` row exists in
the same session at or after that delivery. The old edit-counter estimate is still printed
below the line, labelled as the deliveries made before the log existed, and it is not added
in.

## The mission

`hooks/mission.sh` states your own requests back, verbatim, at the moments a session is
most likely to be working from a summary of them instead of from what you typed. It reads
them out of claude-history-surfer's per-project store and keeps no copy of its own, so on
a machine without `surfer` it emits nothing at all and
[the dependency section](#history-surfer-the-one-dependency) below is where to look.

Five events, and six values in the `moment` field of the delivery log:

|moment|event|what arrives|
|-|-|-|
|`resume`|`SessionStart` with `source` `compact` or `resume`|the mission, to the parent. Startup is silent, because nothing has been asked yet|
|`dispatch`|`PreToolUse` on `Agent`, `Task` or `Workflow`|the mission, to the parent, before the expensive call|
|`subagent`|`SubagentStart`|the mission, to the subagent, plus one line recording that the parent's own instructions to it are above|
|`periodic`|any other `PreToolUse`, once per `MISSION_INTERVAL` seconds|the mission again. Never inside a subagent, which got it at `SubagentStart`|
|`ambiguity`|`UserPromptSubmit`, on a prompt under `MISSION_SHORT_WORDS` words|the last substantive request before it. "continue", "yes", "ok do it" are the prompts that lean on memory|
|`completion`|`Stop`, on a completion claim after at least `MISSION_STOP_MIN_TOOLS` tool calls in the turn|one block, once per `prompt_id`, whose reason is the mission|

`dispatch` and `subagent` are one moment reached from two events, "before an expensive
task", which is why `skillforge doctor` counts five of them and the log carries six.

Every delivery appends one row to `<state>/mission/hits.jsonl`, carrying `ts`, `session`,
`moment`, `agent_id`, `chars` and `prompt_count`. That is the only record that any of this
landed, so it is the file to read when the answer to "is the mission firing?" is not
obvious:

```bash
tail -5 ~/.claude/skill-compounder/mission/hits.jsonl | jq -c .
jq -r .moment ~/.claude/skill-compounder/mission/hits.jsonl | sort | uniq -c
```

`skillforge doctor` reports two rows for it. `surfer` PASS names the executable it probed
and how many prompts are recorded for this project; it is FAIL when `settings.json` wires
the hook and no `surfer` can be found, because then five wirings deliver nothing and say
nothing, and WARN when nothing wires it, because a machine that never installed it is not
broken. `mission` is WARN with no `<state>/mission/` at all, FAIL when that directory
refuses a write or `hits.jsonl` has lines that do not parse, and otherwise PASS with the
delivery count and how many moments it spans.

To silence the whole thing, `MISSION_ENABLED=0`. To make it quieter without switching it
off, raise `MISSION_INTERVAL`, which governs the only arm that fires on an ordinary tool
call. Nothing here is validated: every constant in the table below was picked by
judgement, like the two hook thresholds, and [`measurement.md`](measurement.md) says what
would have to exist before any of them should move.

## history-surfer, the one dependency

The mission hook reads prompts it does not store, so install makes sure something stores
them. When `surfer` is not on `PATH` it clones
[claude-history-surfer](https://github.com/ContextLab/claude-history-surfer) beside the
managed checkout, a sibling so that `install.sh --update` cannot trip over it, runs that
project's own `scripts/setup.py` against the same `--claude-dir` and `--bin-dir`, and
records the url, the checkout and the sha in `install-manifest.json`.

It is skipped, silently and without prejudice, in four cases: `surfer` is already on
`PATH`, a checkout is already sitting where this would put one, the store under the Claude
directory already holds captured prompts, or `SKILL_COMPOUNDER_NO_SURFER` is set. It never
fails the install either: no network, a `git` that refuses, a `python3` that errors all
produce one line in the report and nothing else, and `skillforge doctor` is where the
consequence shows up afterwards.

Uninstall never removes it. That checkout holds every prompt you have ever typed at Claude
Code, which this package did not create and cannot put back, so uninstall prints where it
is and the two commands that would remove it, and leaves it alone.

## The lesson

A failure followed by a fix is the one thing a session knows that the next session does
not. `hooks/repeat-gate.sh` already learned the failure; it now also binds the fix and
asks for it in writing.

**A recovery no longer has to be the same tool.** A failure of one tool followed, within
`REPEAT_RECOVERY_WINDOW` later calls, by a success of a *different* tool whose normalised
input shares at least `REPEAT_RECOVERY_MIN_TOKENS` content tokens with the failed one is
bound as its recovery, and the row is tagged `"cross_tool":true`, which records that the
fix was found somewhere other than where the failure was. That is the shape of "the GitHub
skill failed and `gh` worked", which nothing bound before.

**And a same-tool recovery has to earn it too, once the tool is a shell.** `Bash` names no
operation, so two calls being the same tool was never evidence that they were the same
work. Over the 231 distinct same-tool `Bash` bindings on this machine's store on
2026-09-03, 52 shared not one content token with the failure they were filed under, and a
binding *consumes* its armed failure, so an unrelated success ate the arming the real fix
needed (the counts are in `hooks/repeat-gate.sh`'s header, under THE SAME-TOOL RULE IS NOT
EVIDENCE FOR A SHELL). A same-tool binding for a shell now wants
`REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS` shared tokens, the floor and the comparison the
cross-tool rule already used. Two carve-outs: a success whose normalised call equals the
failed one binds whatever that is set to, because the refusal's self-recovery exclusion
rests on those rows and `pwd` carries one token; and every other tool is untouched, since
`mcp__github__create_issue` names its operation in its own name. What the change gives up
is a real fix sharing no text with the failure, which now degrades to silence rather than
to a sentence the gate made up.

**The first time, it is stated.** When a recovery is bound, the `PostToolUse` arm states
the failed call, the error, the call that worked, and the two commands that record what
was learned. Once per signature per session, as a record of what happened rather than an
instruction.

**The second time, it is required.** The `PreToolUse` arm declines the next call of any
tool when a signature recovered in *this* session also has `fail` rows from
`REPEAT_MIN_SESSIONS` distinct **earlier** sessions and no lesson has been written down
about it. Earlier means earlier: rows carrying this session's own id are dropped from that
count, on both refusing arms. Until 2026-09-04 this arm counted the current session too, so
at the default of 2 one earlier failure was enough and the code was a session stricter than
every document describing it. What the fix costs is stated rather than glossed — at the
default the refusal now arrives on the third occurrence, and `REPEAT_MIN_SESSIONS=1` is the
one export that spells "refuse on the second".

```bash
skillrepeat list      # LESSON: open, recorded, dismissed, dismissed-by-model, -
skillrepeat show <sig>   # each dismiss row's actor=, and which recoveries were cross-tool
skillnote add --lesson <sig> "<what was learned>" [--attach <path>]...
skillrepeat dismiss <sig> --why "<why it needs no lesson>"   # a person at a terminal
```

**Writing the lesson down is the only thing a session can do to lift it, and that is
measured.** Driven live on 2026-09-04, both of two fresh sessions the gate refused answered
by running the `skillrepeat dismiss` the deny text had printed, with a reason they invented,
and carried on — so the refusal cost them nothing. `skillrepeat dismiss` now stamps `actor`
on the row: `model` when it runs inside a Claude Code session (`CLAUDECODE` or
`CLAUDE_CODE_SESSION_ID` is exported into one), `human` otherwise. Only a human's dismissal
lifts the gate, along with every row written before the field existed, since those predate
the model path and carry nothing to tell apart. A model's dismissal is still recorded, still
printed by `show` as `actor=model`, and reported by `list` as `dismissed-by-model` — it is
on the record and it lifts nothing. The deny text names `skillnote add --lesson` and nothing
else, because a refusal advertising an escape that no longer works is worse than one that
omits it; the statement the recovery emits still names both, with the dismissal labelled for
a person at a terminal.

`skillnote add --lesson` writes one record in three places: the dated line in the scoped
`CLAUDE.md`, a reminder in `<state>/reminders.jsonl` keyed on the failing call's signature
so the fix arrives *before* that command runs again, and one ledger `note` row carrying
`lesson_sig`, `reminder_id` and `attachments`. A signature the store has no `fail` row for
is refused, exit 2, naming `skillrepeat list`.

`--attach <path>` is the "code or scripts" half and is valid with or without `--lesson`.
The file is copied, executable bit and all, into `<scope>/lessons/<note id>/`, and the
note line gains a ` (attached: <rel>)` suffix so the script that finally worked is
reachable from the sentence saying what it was for. Two refusals, both exit 2 and both
before a byte is copied: a source outside the working tree or `$HOME`, and a destination
that already exists.

`skillnote promote <id> --to global` moves a project lesson up a level once it turns out
not to be about that project. The line, the attachments and the reminder's scope all
move, and the project block keeps a one-line tombstone naming where it went. It is a move
and never a copy, and `--to project` exits 2, because the hierarchy only goes up.

Two limits are worth knowing. The refusal is no longer `Bash`-only. Since 2026-09-05 its
`PreToolUse` entry carries no matcher at all, so while a marker is armed a call of ANY
tool is refused — a session refused on a `Bash` call had answered with a `Read` and
finished the job, and continuing is any tool. The single exemption is `lesson_cli_head`: a
`Bash` command whose every segment head is `skillnote`, `skillrepeat` or `cd`, at least
one of them a CLI, so the call that lifts the refusal can never itself be refused. The
head allowlists — every segment's head on one of the gate's two lists, `cd build && tar
-xf x` not exempt for its `cd`, a command whose quoting the splitter cannot model not
exempt at all — belong to the repeat arm, which stays `Bash`-only. And `skillnote
--lesson` refuses a signature whose `fail` row is
not a `Bash` call, because the reminder half is keyed on `.tool_input.command` and a
`Skill` or MCP call carries none; for those, the lesson is an ordinary note plus a keyword
reminder. A session that meets that refusal has nothing left of its own: a dismissal it
writes itself lifts nothing, and the refusal no longer expires, so a person has to type
the one line.

Unlike the repeat gate's refusal, this one ships **on**, and it does not let go.
`REPEAT_LESSON_GATE=0` is the only thing that switches it off, and
`REPEAT_LESSON_MAX_DENIES` defaults to `unlimited`: the two exits are a standing lesson on
the ledger and a `dismiss` row a person wrote. A positive integer restores a budget of
that many refusals per signature per session for anyone who wants the valve back.

## What the installer writes into your `CLAUDE.md`

The two reminders name three habits, and a reminder is worth nothing if the rule it
points at was never given to the session reading it. So install also appends those
habits to `~/.claude/CLAUDE.md`, between a pair of HTML comments that render as nothing:

```
<!-- claude-skill-compounder:doctrine:start -->
## Compound Improvement
...the three habits, and when to invoke the skill...
<!-- claude-skill-compounder:doctrine:end -->
```

The text itself is `DOCTRINE_TEXT` in `skill_compounder/installer.py` and that is the
only copy of it in this repository; [The three habits](architecture.md#the-three-habits) is the
long form of the same doctrine. Everything outside the two markers is yours. The block
is replaced in place by the next install and removed whole by uninstall, so installing
twice leaves the file byte for byte as it was, and a `CLAUDE.md` you already had is
copied to a timestamped backup beside it before anything is written. A `CLAUDE.md`
symlinked into a dotfiles repo is written *through*, like `settings.json`.

Two things stop it from talking over you. If your `CLAUDE.md` already carries a
`## Compound Improvement` section of its own — as it does if you wrote one by hand
before this shipped — install prints a notice and adds nothing rather than giving you
the doctrine twice. And to skip it entirely, by flag or by variable:

```bash
./install.sh --no-doctrine
SKILL_COMPOUNDER_DOCTRINE=0 ./install.sh
```

`install.sh` handles `--ref`, `--update` and `--rollback` itself and passes every other
argument straight to `scripts/setup.py`, so the flag works from a clone and over
`curl … | bash -s -- --no-doctrine`. The flag is the stronger of the two:
`--no-doctrine` declines even where `SKILL_COMPOUNDER_DOCTRINE=1` is set, and leaving it
off does not override a `SKILL_COMPOUNDER_DOCTRINE=0` in your environment.

Uninstall then deletes the file only if this package created it and nothing but our own
block was ever in it.

## State, and recovering a bad one

Everything the package remembers sits under `~/.claude/skill-compounder/`, or wherever
`SKILL_COMPOUNDER_STATE` points. Outside that directory, install writes the hook entries
and the `statusLine` into `~/.claude/settings.json` and the doctrine block into
`~/.claude/CLAUDE.md` — taking a timestamped backup beside each before it touches
either — and it creates symlinks in `~/.claude/skills/` and in the CLI directory
(`~/.local/bin` unless `--bin-dir` says otherwise). Those are every path install and
uninstall touch; `skill_compounder/installer.py`'s `install()` reports each one it wrote.

- `ledger.jsonl` is the append-only record: every forge, every note, every skill
  invocation, every apply and every verdict. Nothing edits it and nothing deletes from it.
- `forge/` holds one `<slug>.forge.json` per live forge, which is the file the status line
  renders once a second.
- `briefs/` and `rounds/` hold what a forge wrote to disk as it ran, which is what makes a
  second attempt at a dead one cheap.
- `install-manifest.json` records what install linked and wrote. Uninstall reads it, so a
  link this package cannot attribute to itself is reported and left alone.
- `statusline-base.sh`, `original-statusline.json` and `installed-statusline.json` hold the
  status line you had before, saved so uninstall can put it back, plus a cache under
  `statusline-cache/`.
- `insights/` holds the weekly candidate queue, one `<ISO-week>.jsonl` per week, and
  `reviews/` holds the session-review verdicts and their `index.jsonl`.
- `reminders.jsonl` holds the reminder rules, `remind/` their per-session delivery log,
  and `reminders/` the per-session edit and prompt counters the checkpoint hook keeps,
  plus `reminders/nudges.jsonl`, one row per nudge that hook actually delivered — its
  lineage id, when, and both session ids. It is what `skillreport` counts the conversion
  from; the counters beside it are what the estimate it replaced was made of.
- `repeats/` holds the repeat gate's learned failure signatures, and `repeats/lessons/`
  the per-session markers the lesson arm arms and spends; `claim-gate/`, `doc-gate/`,
  `apply-gate/` and `apply-pending/` hold each gate's per-session budget and the debt a
  closed forge leaves behind.
- `mission/` holds one directory per session of the mission hook's per-event claims and
  its per-turn tool counts, plus `hits.jsonl`, the one record that a delivery happened. A
  sampled sweep removes the session directories once they have gone `MISSION_PRUNE_TTL`
  unchanged, and never the running session's own, whatever its age: a claim removed from
  under a live session re-opens the double delivery, and a tool count removed zeroes the
  turn the `Stop` arm is about to judge. It walks one level of directories and nothing
  else, so `hits.jsonl` is out of its reach by construction. It runs at **two** exits, both
  of which were going to emit nothing anyway: the periodic arm when its interval is not yet
  up, and the early return taken when the prompt store is absent. The second was the gap —
  a machine with no history-surfer left before reaching the sweep, so its session trees
  accumulated and nothing ever removed them. Behind a `[ -d ]` builtin, so the user who has
  no `mission/` directory still exits with no process start on that path.
- `contrib/` holds one work tree per `skillcontrib propose`, named `<name>-<timestamp>`.
  It is a clone of the upstream repository with the branch that was pushed, kept so a run
  that failed part way through can be looked at rather than guessed about.

Two directories a lesson writes to are deliberately **not** under here, because a lesson
is meant to be read and committed rather than kept in runtime state. `--attach` copies
into `<project>/.claude/lessons/<note id>/` for a project note and
`<claude dir>/lessons/<note id>/` for a global one, beside the `CLAUDE.md` whose line
links to it; the memory scope puts them beside the memory file.

Two things to check here before you go looking anywhere else, and `skillforge doctor`
reports both. The first is the silent stop described under
[checking the install](#checking-the-install-and-closing-out-a-forge). The second is a
counter file written in one form and appended to in another, which neither reader can
add up; `doctor` reports that rather than repairing it, because the correct total is a
judgement and a command that guessed would destroy the evidence.

To start over without touching anything else, `rm -rf ~/.claude/skill-compounder` and
re-run `skillforge doctor`. That discards the ledger, which is the record this package
exists to produce, so it is a last resort rather than a repair.

## Contributing a skill back

A skill that survived the red-team loop locally and then actually got used again is worth
more than a proposal. Two commands take it upstream:

```bash
skillcontrib recon <name> [--upstream <owner/repo>]     # read-only: what a real run would do
skillcontrib propose <name> [--upstream <owner/repo>]   # the same run, carried out
skillcontrib propose <name> --dry-run                   # byte for byte what recon prints
```

`recon` locates the skill through its install symlink, parse-checks it, reads its routing
pin, runs the duplicate check against the upstream tree and every pull request in any
state, decides maintainer or fork, and prints what the remaining steps would clone,
commit, push and open. `propose` without `--dry-run` then forks if it has to,
shallow-clones into `<state>/contrib/<name>-<timestamp>/`, branches `skill/<name>`, copies
the whole skill directory, commits with the routing pin's `measured:` line, pushes, opens
the pull request, prints its URL and appends one `contrib` row to the ledger.

**Running `propose` without `--dry-run` is the consent, and it is the only consent.**
There is no second prompt. That is a deliberate replacement rather than a relaxation: the
hand-walked seven-gate procedure it retired was run 47 times and opened no pull request at
all ([the September audit](../notes/2026-09-02-audit-and-replan.md)). What stands in for
the gates is disclosure. Every network write is printed first on a line beginning
`WRITE:`, so a transcript can be swept for them afterwards, and the run stops at the first
failure with that step's own exit code.

`--upstream` defaults to `ContextLab/claude-skill-compounder`, which is almost never the
repo you mean: aimed at the wrong tree, the duplicate check answers "clean" for free.
Pass it. `--repo` is accepted as a spelling of the same flag.

Two refusals are worth knowing before the first run, and both are liftable. A pull request
that proposed this skill and was closed unmerged blocks resubmission, exit 5, until
`--override-rejected`, because a rejection is a signal rather than noise to route around.
A routing pin nothing has measured is refused, exit 22, until `--allow-unmeasured`. The
rest of the codes are listed at the top of `bin/skillcontrib`: 0 clean, 2 usage, 6 and 7
for `gh` and its authentication, 8 for a failed read-only lookup, 3, 4, 5, 9, 18 and 19
from the duplicate check, 10 to 12 and 17 from preflight, 20 and 21 for a missing or
unparseable pin, and 23, 24 and 25 for the fork, a git step and a `gh pr create` that
returned no URL.

So this CLI is no longer read-only as a whole. Bare `skillcontrib`, `dedup`, `whoami`,
`preflight` and `recon` still are; `propose` is the one subcommand that writes anything
anywhere.

The bar is both a clean red-team result and evidence of local reuse. See
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Tuning

Noisy reminders are a tuning problem. The knobs worth setting are in the table below; the
automatic session review has its own, in
[What runs against the API](../README.md#what-runs-against-the-api).
All sixty are environment variables, and they are not the whole set — this
prints every name the hooks, the six CLIs, the status line and `install.sh` read, 143 of
them as of 2026-09-04 (`uninstall.sh` and `scripts/` are outside it):

```bash
grep -ohE '\b(CI|CLAUDE_SKILL_COMPOUNDER|INSIGHT|SKILLFORGE|SKILLNOTE|SKILLUSE|SKILLREPEAT|SKILLREPORT|STATUSLINE|SKILL_COMPOUNDER|CLAIM_GATE|DOC_GATE|REPEAT_GATE|REPEAT_MIN|REPEAT_RECOVERY|REPEAT_LESSON|REMIND|PRECOMPACT|APPLY_GATE|APPLY_PENDING|MISSION|SKILLCONTRIB)(_[A-Z0-9_]+)?\b' \
  hooks/*.sh bin/* statusline/*.sh install.sh | sort -u
```

`install.sh` is in that list and its five names are the exception to everything below it
(`grep -nE '\$\{(SKILL_COMPOUNDER|CLAUDE_SKILL_COMPOUNDER)[A-Z_]*:-' install.sh`).
`SKILL_COMPOUNDER_REPO_URL` (what is cloned), `SKILL_COMPOUNDER_REF`,
`SKILL_COMPOUNDER_UPDATE`, `CLAUDE_SKILL_COMPOUNDER_APP` (where the managed checkout goes)
and `CLAUDE_SKILL_COMPOUNDER_STATE` (where the state directory goes; `uninstall.sh` reads
the same two) are read at **install time**, before any of this is wired up — so none has a
row in the table and none has any place in `~/.claude/settings.json`, where setting them
does nothing. Set them on the command that runs the installer. `SKILL_COMPOUNDER_REF` and
`SKILL_COMPOUNDER_UPDATE` are documented where they are used, under
[Updating and rolling back](../README.md#updating-and-rolling-back).

**One name the command cannot print, and it is not an omission.** `CLAUDECODE` is read by
`bin/skillrepeat`, which stamps `actor:"model"` on a dismiss row written from inside a
session — the fact that stops a model's own dismissal lifting the lesson gate. It carries
none of the prefixes above, and the leading `\b` could not match inside a longer name even
if it did, so it is allowlisted in `tests/test_doctrine_sync.py` as `AMBIENT` rather than
added to the alternation. That list is for names **Claude Code exports and this package only
reads**, which is also where `CLAUDE_CODE_SESSION_ID` sits: ours to read, never ours to set,
so neither belongs in a tuning table nobody could act on.

**A numeric knob set out of range takes the default, in the three hooks that guard.** A
non-numeric or absurd value reaches `[ "$X" -ge 1 ]`, which is bash printing `integer
expression expected` on a stderr that is still your terminal — a hook breaking a turn, from
a knob this table lists. `hooks/mission.sh`, `hooks/remind.sh` and
`hooks/compound-improvement.sh` therefore guard every numeric knob they read (eleven, five
and eight respectively) with one `case` that tests shape and magnitude together: eleven
digits or more is out of range and takes the **documented default**, not zero and not a
clamp to the ceiling, because an out-of-range export is a typo and the default is the only
value the header promises. Where `0` already meant "off" it still does; the guard only
rejects what was never a setting.

The third hook earned its guards on 2026-09-04, twice. `CI_PRUNE_EVERY=0` reached
`$(( RANDOM % PRUNE_EVERY ))` and bash reported `division by 0`, leaving the hook exiting 1
on every event that ran to the end. Then, driving the real hook with a throwaway state
directory after that fix, `CI_EDIT_EVERY=0` still printed `n % EDIT_EVERY : division by 0`
on every counted edit and `CI_PROMPT_MIN_CHARS=abc` printed `[: abc: integer expression
expected`, both with exit 0, and an unguarded `CI_NOW=abc` made the second prompt of a
session exit 1 on an unbound variable. All eight numeric reads are guarded now, pinned by
`tests/test_hook.py::KnobGuardTest` and `SweepKnobTest`, each of which reproduces its
failure on a guard-stripped copy under `/bin/bash` 3.2. `CI_EDIT_EVERY=0` takes the default
of 12 rather than switching the checkpoint off, because nothing in the header ever promised
`0` as an off switch there; that hook's only off switch, `CI_QUEUE_NUDGE`, says so in
words.

`skill_compounder/installer.py` is outside that command's paths as well, and it reads
six names of its own, all at install time — `grep -n 'os.environ.get'
skill_compounder/installer.py` printed six read sites on 2026-09-05; re-run it rather than
trusting this count. Four are about the history-surfer dependency.
`SKILL_COMPOUNDER_NO_SURFER=1` skips the step, leaving the mission hook inert until
`surfer` arrives some other way. `SKILL_COMPOUNDER_SURFER_URL` changes what is cloned,
and exists so the suite can clone a real local checkout with no network at all.
`SKILL_COMPOUNDER_SURFER_HOME` changes where the checkout goes. `CLAUDE_HISTORY_SURFER_DIR`
is not ours at all: `_surfer_store()` reads it because that is how history-surfer's own
installer resolves its data directory, and the check for an existing store has to look
where the other project would have put one. The remaining two are neither install-time
options nor about the dependency. `SKILL_COMPOUNDER_NOW` pins the clock on the backup
stamp, one of the fourteen clocks the suite freezes; `SKILL_COMPOUNDER_DOCTRINE` set to
`0`, `no`, `off` or `false` suppresses the doctrine stanza the installer writes into the
global `CLAUDE.md`, and an explicit argument beats it. Set them on the command
that runs the installer; `~/.claude/settings.json` is read by nothing at install time.

`CLAUDE_SKILL_COMPOUNDER` is in the alternation for those two names alone, and it has to
be: the leading `\b` cannot match inside `CLAUDE_SKILL_COMPOUNDER`, because the position
before `SKILL` sits between two word characters, so the `SKILL_COMPOUNDER` branch does not
reach them.

The closing `\b` arrived with `REMIND`, and it is not decoration. The suffix group is
optional, so without it a bare prefix also matches the start of a longer word: `$REMINDERS`
in `hooks/insight-capture.sh` printed `REMIND`, and `$INSIGHTS_DIR` in
`hooks/compound-improvement.sh` had been printing `INSIGHT` the whole time. Neither is a
name any script reads.

Most of what that prints is an internal budget or a clock pin the test suite freezes. The
ones below are not all read by the same component, so they do not all go in the same
place in `~/.claude/settings.json`:

|Variable|Default|Set it in|Meaning|
|-|-|-|-|
|`CI_EDIT_EVERY`|`12`|the hook entries|Edits between "is this worth crystallizing?" checkpoints; `0`, non-numeric or 11+ digits takes the default|
|`CI_PROMPT_COOLDOWN`|`1200`|the hook entries|Seconds between "does a skill exist?" reminders; out of range takes the default|
|`CI_PROMPT_MIN_CHARS`|`60`|the hook entries|Shorter prompts never trigger a reminder; out of range takes the default|
|`CI_CLAIM_TTL_MIN`|`60`|the hook entries|Minutes before a stale double-fire claim is pruned|
|`CI_PRUNE_EVERY`|`25`|the hook entries|Hook invocations between sweeps of expired claims|
|`CI_QUEUE_NUDGE`|`1`|the hook entries|Set to `0` to stop announcing the pending skill-candidate queue|
|`CI_QUEUE_NUDGE_MIN`|`259200`|the hook entries|Seconds that must pass before the queue may be announced again; out of range takes the default|
|`CI_QUEUE_NUDGE_MAX`|`1209600`|the hook entries|Seconds after which an unchanged queue is announced anyway; out of range takes the default|
|`SKILL_COMPOUNDER_USE_LOG`|`1`|the hook entries|Set to `0` to stop recording skill invocations in the ledger|
|`CLAIM_GATE`|`1`|the hook entries|Set to `0` to switch the end-of-turn claim gate off entirely|
|`CLAIM_GATE_COMMIT`|`1`|the hook entries|Set to `0` to keep the gate on the closing message but stop it denying a `git commit`|
|`CLAIM_GATE_MIN_DIGITS`|`3`|the hook entries|Smallest integer width the gate will flag as an unsupported figure|
|`CLAIM_GATE_MAX_SESSION`|`10`|the hook entries|Blocks plus denials the gate may spend in one session|
|`SKILL_COMPOUNDER_REPEAT_GATE`|`1`|the hook entries|Set to `0` to switch the repeat gate off entirely — it denies nothing and learns nothing|
|`REPEAT_GATE_REFUSE`|`0`|the top-level `env` block|Set to `1` to arm the refusal. Off by default: across 81 recorded sessions it refused nothing, and every signature that reached the threshold was one the gate's own head rules exempt anyway ([#27](https://github.com/ContextLab/claude-skill-compounder/issues/27)) — re-derived after those rules were narrowed to a per-segment test on 2026-09-04, when 13 signatures stood at the threshold and all 13 were still exempt. Learning and recovery are unaffected either way. **Two components read it** — the gate, and `bin/skillrepeat`, which says on its own output whether the arm is armed|
|`REPEAT_MIN_SESSIONS`|`2`|the top-level `env` block|Distinct **earlier** sessions a call must have failed in, the same way, before an attempt is denied. Both refusing arms drop rows carrying the current session's id, so nothing a session does to itself can lock it out; the lesson arm counted this session too until 2026-09-04, which made it one session stricter than its own documentation. At the default the lesson refusal therefore lands on the third occurrence, and `1` is the spelling of "refuse on the second". **Three components read it** — set it anywhere narrower and they disagree|
|`REPEAT_RECOVERY_WINDOW`|`5`|the hook entries|Successful calls of a tool this hook is wired for, after which an armed failure stops looking for the call that fixed it, by either the same-tool rule or the cross-tool one|
|`REPEAT_RECOVERY_MIN_TOKENS`|`2`|the hook entries|Content tokens two normalised calls must share before a success of a **different** tool binds as the recovery. `0` disables cross-tool binding and leaves the same-tool rule untouched. A floor, not a calibration|
|`REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS`|`2`|the hook entries|The same floor for a success of the **same** tool, applied only where that tool is a general-purpose shell (`Bash`), which names no operation of its own. `0` restores the unconditional same-tool binding this script shipped until 2026-09-03. A success whose normalised call equals the failed one binds whatever this is set to, and no other tool is affected|
|`REPEAT_LESSON_GATE`|`1`|the hook entries|Set to `0` to switch the lesson refusal off. On by default, which is the reverse of `REPEAT_GATE_REFUSE`, because this arm fires only where a failure and its recovery were both seen in the session it is speaking to. Exactly `0` is off and any other value is on, so a typo lands on the shipped default|
|`REPEAT_LESSON_MAX_DENIES`|`unlimited`|the hook entries|Refusals the lesson arm may spend on one signature in one session. The default is no expiry: only a standing lesson or a human's `skillrepeat dismiss` ends the refusal. A positive integer restores a budget of that many refusals per signature per session; `0` means it never refuses. Anything else lands on `unlimited`|
|`REPEAT_GATE_STDERR`|`0`|the hook entries|Set to `1` to leave the repeat gate's stderr connected, for `bash -x`. By default the gate closes it with a builtin `exec` before its first process start: `execve` charges the environment against `ARG_MAX`, and in a 200-byte band of environment size just under the one at which the hook cannot launch at all, `jq` launched and every `sed` in the normaliser could not, so bash printed `Argument list too long` up to seven times per tool call on the terminal. Exit status and the store are unaffected either way|
|`SKILLREPEAT_GATE`|*(resolved from the CLI's own path)*|the top-level `env` block|Where `bin/skillrepeat` finds `hooks/repeat-gate.sh`, so its `GATE` column asks the gate which calls it would exempt instead of keeping a second copy of the rules. Resolved by following the CLI's own symlinks to the checkout; set it only where that fails|
|`SKILLREPORT_GATE`|*(resolved from the CLI's own path)*|the top-level `env` block|The same, for `bin/skillreport`'s `GATES` block. Separately named because the two CLIs install independently of each other|
|`SKILL_COMPOUNDER_DOC_GATE`|`1`|the hook entries|Set to `0` to switch the documentation gate off entirely — `git push` is never denied|
|`DOC_GATE_MAX_COMMITS`|`100`|the hook entries|Most commits the gate will read ahead of the remote before it gives up and stays silent|
|`DOC_GATE_CODE_EXCLUDE`|*(empty)*|the hook entries|An ERE; a path matching it counts as neither code nor documentation. `^tests?/` is the first knob to reach for if the gate is too loud|
|`DOC_GATE_NOTES`|`doc`|the hook entries|How a root-level `notes/` path counts: `doc` satisfies the gate, `neither` neither satisfies nor triggers it. Set `neither` where `notes/` is a dated log written every session rather than a description of behaviour — this repo does, in `.claude/settings.json`|
|`SKILL_COMPOUNDER_APPLY_GATE`|`1`|the hook entries|Set to `0` to switch the apply gate off entirely — a closed forge leaves no debt to answer|
|`APPLY_GATE_WINDOW`|`86400`|the hook entries|Seconds after a forge closes during which its apply debt still blocks the turn|
|`SKILL_COMPOUNDER_REMIND`|`1`|the hook entries|Set to `0` to switch reminder delivery off entirely — recorded reminders stay on disk and nothing states them back|
|`REMIND_MAX`|`2`|the hook entries|Most reminders delivered in one event, highest-scoring first|
|`REMIND_COOLDOWN`|`0`|the hook entries|Seconds before a reminder that has fired may fire again in the same session. `0` means once per session|
|`REMIND_MAX_ROWS`|`2000`|the hook entries|Lines read from the tail of the reminder store and of the hit log, and the length the hit log is trimmed back to when a delivery pushes it past that|
|`REMIND_PRUNE_TTL`|`604800`|the hook entries|Seconds a session's cooldown-stamp or delivery-claim directory under `remind/` may go unchanged before a sweep removes it. The sweeping session's own pair is never removed, whatever its age|
|`REMIND_PRUNE_EVERY`|`25`|the hook entries|Hook invocations between sweeps of `remind/`. `0` switches the sweep off|
|`MISSION_ENABLED`|`1`|the hook entries|Set to `0` to switch the mission off entirely: no moment fires and nothing is recorded|
|`MISSION_SURFER_ROOT`|unset; the hook then reads `CLAUDE_HISTORY_SURFER_DIR`, and failing that `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/history-surfer`|the hook entries|Where claude-history-surfer keeps its per-project prompt store. Rung 1 of three, and the only one this package owns. Rung 2 is history-surfer's own override, read by its `data_dir()`, so setting it moves the writer and this reader together. Rung 3 is where the two DIVERGE, and the hook's header says so: history-surfer's `claude_dir()` keys on `CLAUDE_HISTORY_SURFER_CLAUDE_DIR` and reads `CLAUDE_CONFIG_DIR` nowhere, while this hook reads `CLAUDE_CONFIG_DIR`, which is what the rest of this package falls back to and what Claude Code itself honours. They agree whenever neither variable is set, which is every default machine; export one of them and rung 1 is what settles it. The hook reads that store and writes nothing to it|
|`MISSION_FIRST_CHARS`|`1200`|the hook entries|Characters of the session's first substantive request quoted in full|
|`MISSION_RECENT`|`3`|the hook entries|Most recent requests quoted alongside it|
|`MISSION_EACH_CHARS`|`400`|the hook entries|Characters of each of those|
|`MISSION_MAX_CHARS`|`2400`|the hook entries|Characters of the whole rendered mission, clamped to 60000 so the emit stays clear of Linux's 131072-byte cap on one argument|
|`MISSION_INTERVAL`|`1200`|the hook entries|Seconds between periodic deliveries in one session. The knob to raise first if the mission is too loud|
|`MISSION_SHORT_WORDS`|`6`|the hook entries|A prompt under this many words is the ambiguity proxy, and this is also what "substantive" means when the first request is chosen|
|`MISSION_STOP_MIN_TOOLS`|`8`|the hook entries|Tool calls the turn must have made before the `Stop` arm may block a completion claim|
|`MISSION_MAX_ROWS`|`2000`|the hook entries|Store lines read for one session, and the length `hits.jsonl` is trimmed back to on write|
|`MISSION_MAX_BYTES`|`33554432`|the hook entries|Bytes read from the tail of the prompt store. A larger store loses its oldest rows, so a very old session in a very large project can lose its first request|
|`MISSION_PRUNE_TTL`|`604800`|the hook entries|Seconds a session's claim-and-tool-count directory under `mission/` may go unchanged before a sweep removes it. The sweeping session's own directory is never removed, whatever its age|
|`MISSION_PRUNE_EVERY`|`25`|the hook entries|Hook invocations between sweeps of `mission/`. `0` switches the sweep off. It runs at two sites, the periodic arm's not-yet-due exit and the early return when the prompt store is absent, so no event that is about to deliver pays for it|
|`SKILLCONTRIB_GH`|`gh`|the top-level `env` block|The `gh` executable every GitHub call goes through. It exists so the write half of `propose` can be exercised against a stand-in rather than opening real pull requests|
|`SKILLCONTRIB_UPSTREAM_URL`|*(derived from the repo name)*|the top-level `env` block|Where the clone comes from. Unset in normal use; the tests point it at a local bare repository so a clone, branch, commit and push all happen for real with no network|
|`SKILLCONTRIB_FORK_URL`|*(derived from the repo name)*|the top-level `env` block|The same, for where the branch is pushed|
|`SKILLCONTRIB_FORK_TRIES`|`30`|the top-level `env` block|Polls for a freshly created fork to become visible before `propose` gives up with exit 23|
|`SKILLCONTRIB_FORK_SLEEP`|`2`|the top-level `env` block|Seconds between those polls|
|`SKILLFORGE_SURFER_BIN`|*(the `surfer` on your `PATH`)*|the top-level `env` block|The executable `skillforge doctor` probes for the prompt store. Set it only where `surfer` is installed somewhere `PATH` does not reach|
|`STATUSLINE_BASE_TTL`|`5`|the `statusLine` entry|Seconds your base status line is cached|
|`SKILLFORGE_IDLE_SECS`|`2700`|the top-level `env` block|Age past which a forge nothing has stepped is called idle. **Two components read it** — the status line and `skillforge list` — so setting it anywhere narrower makes them disagree about whether a forge is dead|
|`SKILLFORGE_ACTIVE_TTL`|`21600`|the top-level `env` block|Seconds of **idle** time, measured since the last `step`, past which an `active` forge is presumed dead: `skillforge doctor` says WARN, `skillforge reap` writes it the `fail` row it never got, and `start` on that name reaps it rather than refusing|
|`STATUSLINE_CACHE_PRUNE_EVERY`|`200`|the `statusLine` entry|Cache misses between sweeps of dead cache entries. The key is a hash of session id and directory, so every session leaves a file; sampled because this runs once a second|
|`SKILL_COMPOUNDER_STATE`|`~/.claude/skill-compounder`|the top-level `env` block|Where runtime state lives|

Only the eight `CI_*` variables in the table above are read by
`hooks/compound-improvement.sh` as settings, and eight is not how many `CI_*` names that
script mentions: `grep -ohE '\bCI_[A-Z0-9_]+\b' hooks/compound-improvement.sh | sort -u`
printed ten on 2026-09-05. The two with no row are not knobs. `CI_NOW` is the test clock,
and no `_NOW` name has a row for the reason given further down. `CI_DEBUG_DUMP` is a path
the script appends its raw stdin payload to when it is set, for looking at a payload by
hand; it changes no behaviour, and a row for it would invite someone to carry a debug sink
in `settings.json`.
`SKILL_COMPOUNDER_USE_LOG` is read by `hooks/skill-use.sh`, which is a hook entry too.
The `CLAIM_GATE_*`, `DOC_GATE_*` and `APPLY_GATE_*` variables, and every `REPEAT_*` one
**but `REPEAT_MIN_SESSIONS`, `REPEAT_GATE_REFUSE` and `REPEAT_GATE_NOW`**, are each read
by exactly one script — `hooks/claim-gate.sh`,
`hooks/doc-gate.sh`, `hooks/apply-gate.sh`, `hooks/repeat-gate.sh` — so each belongs on
that script's own hook entries and nowhere else. Each of the four gates also takes an off
switch, and setting one to `0` disables that gate completely rather than making it quieter.
`REMIND_MAX`, `REMIND_COOLDOWN`, `REMIND_MAX_ROWS`, `REMIND_PRUNE_TTL`, `REMIND_PRUNE_EVERY`
and `SKILL_COMPOUNDER_REMIND` follow the same rule, with `hooks/remind.sh` as their only reader, so they go on both of its entries —
the `UserPromptSubmit` one and the `PreToolUse` one — and nowhere else.

Every `MISSION_*` variable follows it too, with `hooks/mission.sh` as the only reader, so
they belong on that script's own entries. There are five of those rather than two, one per
event, and a value set on some of them is a mission that behaves differently depending on
which moment reached it, which is the one failure here nothing reports. The session-wide
`env` block is the safer place for anything you actually want to change.

The `SKILLCONTRIB_*` variables are read by `bin/skillcontrib` and nothing else, and
`SKILLFORGE_SURFER_BIN` by `bin/skillforge` and nothing else. Both are CLIs rather than
hooks, so a hook entry is the one place setting them does nothing at all.

**`REPEAT_MIN_SESSIONS` is the exception, and it is the one to get wrong.** Three
components read it — `hooks/repeat-gate.sh`, which decides, and `bin/skillrepeat` and
`bin/skillreport`, which report what it decided:

```bash
grep -rlF '${REPEAT_MIN_SESSIONS' hooks bin statusline
```

Set it on the hook entry alone and the two CLIs keep reporting against the default: a
signature that failed in two sessions is listed as `refuses` while a gate raised to three
lets it straight through, and nothing says which of the two is lying. It belongs in the
session-wide `env` block, for the same reason `SKILL_COMPOUNDER_STATE` does.

`REPEAT_GATE_REFUSE` is the second exception, and it is the milder one: `bin/skillrepeat`
reads it only to print whether the arm is armed, so setting it on the hook entry alone
costs you a footnote rather than a wrong number. Put it in the `env` block anyway and the
two cannot disagree at all.

`REPEAT_GATE_NOW` has two readers for a narrower reason: it is a **test clock**, and
`bin/skillrepeat` falls back to it when `SKILLREPEAT_NOW` is unset so the CLI and the gate
cannot disagree about what time it is inside one test. Neither belongs in a real config,
and neither do `MISSION_NOW` and `SKILLCONTRIB_NOW`, which are the same thing for the
mission hook and for `bin/skillcontrib`. Each of those two is its own, borrowed from
nobody: a script whose clock is another script's is a script a test can freeze without
meaning to. That is why no `_NOW` name has a row in the table above.
`SKILLREPEAT_GATE` and `SKILLREPORT_GATE` are not gate variables despite the name: each is
read by one CLI, to find `hooks/repeat-gate.sh` when following its own symlinks back to the
checkout has not worked. Setting either on a hook entry does nothing.
`STATUSLINE_BASE_TTL` and `STATUSLINE_CACHE_PRUNE_EVERY` are read by
`statusline/statusline.sh`, so setting either on a hook entry does nothing.
`SKILL_COMPOUNDER_STATE` is read by the hooks, the CLIs and the status line alike, so it
belongs in the session-wide `env` block. Set it anywhere narrower and they disagree about
where state lives.

**Both hook thresholds are unvalidated.** `CI_EDIT_EVERY=12` and
`CI_PROMPT_COOLDOWN=1200` were picked by judgement and nothing has measured them since.
`skillreport` is the instrument that would settle them, and it needs real usage across
several repos over real time before either number should move. Until then, tuning them is
guesswork with extra steps. The skill's own threshold is deliberately not a number: a
duration is a judgement a session can talk itself past, so it asks for a nameable dead end
and a second occurrence instead.

The one adjustment worth making without data: if a reminder fires often enough that you
learn to read past it, raise `CI_EDIT_EVERY` and `CI_PROMPT_COOLDOWN`. By that point it
has stopped doing anything for you, and it will keep looking like it works.
