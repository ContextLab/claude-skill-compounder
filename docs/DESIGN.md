# Design notes

Why each piece of this package is shaped the way it is. The platform behavior these
decisions rest on is recorded separately, in
[CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md): that file holds the findings about
Claude Code itself, which are useful to a project that shares no code with this one. This
file holds the local reasoning, and links there rather than restating a finding.

Everything below was verified by running it, on **macOS 25.5.0** and in CI on ubuntu.
Where a section rests on the platform, that part was run against **Claude Code 2.1.241**
on **2026-08-24**, except where the section names another version. Re-verify before
trusting any of it in a much later version.

---

## Forging pays off in the session that does it

Skills hot-reload mid-session, roughly one tool round-trip after the file is written
([CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md#skills-hot-reload-mid-session)).

**Consequence for the design:** the compounding loop is worth running immediately instead
of deferring to a follow-up session, because the skill it forges is available to the
session that forged it. It is also why the SKILL.md tells sessions not to read the first
`Unknown skill` as a failure.

---

## There are two different session ids

`$CLAUDE_CODE_SESSION_ID` (visible to `Bash`) and the `.session_id` delivered in
hook / status-line stdin JSON were once **different identifiers for the same session**.
Observed in one session: `32c3cd9e-…` in the environment variable, `f2d5c428-…` in the hook
payload.

**They are the same value at CLI 2.1.247, re-measured 2026-08-26.** In one session the
environment variable read `25a4770c-…`, and every claim file `hooks/apply-gate.sh` had
written from the *payload's* `.session_id` was named `25a4770c-….<prompt>.turn`. A cold
reviewer raised the divergence as a live hazard for the apply gate and found the same
equality independently.

**Which means the finding is dated, and the design below is not.** Do not read this section
as "they are the same now, so a session id is safe to key on": what was measured is one
version's behaviour, twice, in opposite directions. `bin/skillforge` writes
`$CLAUDE_CODE_SESSION_ID` into an apply marker and `hooks/apply-gate.sh` compares the
payload's `.session_id` against it, so **that gate is the one component here that depends on
the two being equal** — it works today for that reason, and it would go silently dead, with
nothing on any surface, if they diverged again. That is a known and accepted fragility in a
component whose failure mode is silence, not a claim that the platform guarantees anything.

**Consequence for the design:** `skillforge` keys its state on the **forge name**, never on a
session id. Keying it on the environment variable makes the status line look for a filename
that never exists, so it renders nothing, silently, with no error anywhere. A forge name is
the one identifier both sides can see: the writer is handed it on the command line, and the
reader finds it inside the file it is already reading.

The reminder hook *does* key its counters per session, and that is correct: it both writes
and reads using the payload's `.session_id`, so the two sides agree.

### Why the forge went on a diet

The default forge was five stages and a five-round cap: A, an orchestrator, a builder, a
red-teamer per round, and a judge — eight agents at the cap, over twelve steps and 28 doctrine
gates. The ten forges closed under it took 0.60, 0.95, 0.96, 1.75, 3.11, 3.45, 5.36, 5.81,
6.47 and 86.4 hours (`notes/2026-09-02-audit-and-replan.md`), a median of about 3.3, and six
of the ten closed `done` against four `fail`. Cost was uncorrelated with value: `finish-task`
cost twelve hours and 1301 lines and has zero genuine uses, while the two most-used skills are
around 405 lines each.

The audit could attribute an observed catch to only four cheap pieces — the parse gate (~2s),
the routing gate (~90s per skill, under 1% of a median forge), round 1 plus one confirming
round, and the non-fork reviewer. So those stayed. What went: rounds 3 and beyond, which were
about 60% of the wall clock; the orchestrator layer, which caught no defect in ten forges and
produced the 86.4-hour outlier; the judge, which produced two meta findings ever and never a
skill defect; and the unconditional runnable reproduction, which no note records catching
anything. The judge's first question moved into step 1, where it is one sentence written
beside the verbatim trigger, and the orchestrator and the judge both come back on a forge
whose budget has been raised past two rounds — which is the only kind of forge whose review
traffic was ever big enough to want a layer between it and the user.

The cap became a refusal rather than a number in a doc because three of the ten forges simply
ran past the advisory one. `skillforge round` owns the round record, so it can count what is
really there; `step` still records an overrun rather than refusing it, because a budget is a
plan and a step reached is an observation. See `bin/skillforge`'s own header for that split.

**The counter-evidence, kept here because it is the argument against this change.** The
cheapest forge on record — `ai-tell-audit`, 35 minutes — shipped a skill that was broken
within the hour. A short forge is not a safe forge, and nothing in the diet claims otherwise:
what it claims is that the rounds that were cut were not the rounds doing the catching.

### One file per forge

Several forges run at once. Every agent a forge dispatches runs in the background, so a main
thread that is not tied up for the length of a forge starts a second one cheaply, and does.

`skillforge` writes `forge/<slug>.forge.json`, one file per forge, and reads every `*.json`
in that directory as a slot. `start` never touches another forge's record. The slug is only
a filename: every lookup reads the `name` field *inside* the file, so a sanitized or
truncated slug cannot mislabel anything, and two names that sanitize to the same slug number
off (`my-skill-2.forge.json`).

A slot is claimed with `ln` of the fully-written record, not with a redirect. The file that
appears at a slot path is therefore never a placeholder, which is what lets a concurrent
starter tell an occupied slot from a free one. Claiming with an empty file instead —
`set -o noclobber; : > "$FILE"` — is wrong here, and wrong silently: a racing starter reads
the 0-byte file as an abandoned claim and takes the slot as well, so simultaneous starts
collapse into one and the losers vanish with exit status 0.

**Which forge a command acts on** is resolved in three steps: an explicit `--name`/`-n` (or
`$SKILLFORGE_NAME`); otherwise the single active forge, when exactly one is active;
otherwise the command **refuses** and lists the live names. It never guesses, because the
failure this replaces was software confidently naming the wrong job. The no-argument case is
untouched in the ordinary situation of one forge. Ambiguity is measured over *active* forges
only: a finished record lingers on disk for the status line's clear-out window, and letting
it make every bare command ambiguous for thirty seconds is worse than the problem it would
solve.

`start` refuses a second forge under a name that is already active and exits 2. A finished
record of the same name is replaced in place, so there is exactly one slot per name and the
ledger's start-to-outcome join stays unambiguous. `step`, `done` and `fail` act only on an
active forge: a bare `step` against a closed record rewinds the bar under a green ✓, and a
second `done` appends a second outcome row for one start, which makes the ledger count one
forge twice while its own join hides the duplicate.

### One outcome row per forge

`done`, `fail` and `clear` all end a forge, and all three read the slot, wrote it, then
appended a row. Two at once both read `active` — neither had written yet — so both
appended: 40 of 40 trials for two `done`s, 40 of 40 each for a `fail` and a `clear` racing
a `done`. `skillreport` reads nothing but the ledger, so a duplicate inflates the only
measurement this package makes about itself.

A lock is the wrong instrument. Held across a write where a process can be killed at any
moment, it turns a duplicated row into a forge nobody can close. The outcome is claimed
instead the way a slot is: `ln` of the fully-written closed record onto
`forge/.outcome.<id>.claim`. The link appears atomically or fails because the name is
taken; the winner appends, the losers exit 0; nothing is held. A racing `done` and `fail`
are settled by whoever links first, deliberately — both are true reports, and choosing by
kind would record the outcome that arrived second.

The order is stage, build the line, claim, append, publish. Every fork happens before the
claim — the reasoning that warms `project_root()` ahead of the slot claim — so the gap
between winning and having the row on disk is one `printf` builtin. Killed before the
claim: nothing happened. Killed between claim and append: the row is lost and the ledger
says so, and the next closer heals the slot from the claim's own copy of the record.
Killed before the publish: same heal, row already written. Killed after: nothing left to
do. A claim that cannot be created is bypassed, never waited on.

`<id>` must be injective and bounded, and that is not a detail: two forges sharing a claim
leaves the second unclosable and buries it under the first one's corpse. `tr` sanitizing is
many-to-one and did exactly that; a claim path over NAME_MAX makes `ln` fail with no claim
to show and brings the duplicate back. An `id` that is not already a safe, bounded filename
is replaced, not repaired — by the slot's inode plus its start time, the inode because
`started` repeats under a pinned clock, the start time because inodes are recycled.

Publishing is guarded on the slot still being that forge, in the winner as much as in the
healer: unguarded, a closer stopped between claim and publish and resumed after a
re-`start` replaced a live forge with its corpse.

A claim is reaped after an hour like any temp file — unless the forge it names is still
active, which is the fingerprint of a closer killed before publishing and the only thing
stopping a second row. `reap_temps` now excludes `*.json`: a forge named `build.tmp` has a
slot matching `*.tmp.*`, and was deleted out from under itself an hour in.

### The status line rotates

A status line is one line wide and a forge segment is about seventy columns, so two do not
fit side by side. `statusline/skillforge-status.sh` shows one forge at a time, switching
every `SKILLFORGE_ROTATE_SECS` seconds (6 by default), and stamps every frame `[k/N]`. Both
halves carry weight: showing only the most recently updated forge hides the others, which is
the defect itself, and a counter without rotation says "there are two" while never saying
what the other one is. With one forge the counter is omitted and the segment renders exactly
as it does with no rotation at all.

Display width is constant *within* a rotation window, because the tail is padded to a fixed
column count; it changes *at* a boundary, since the name on screen is a different length.
That is one redraw every six seconds, coinciding with a real change of content, rather than
the once-a-second blink the fixed width exists to prevent. The rotation period is
deliberately not the tail-alternation period (6s against 5s): equal periods lock each forge
to one tail forever, so with three live forges the third would show its summary and never
its phase.

Reaping is per slot, on each slot's own clock, so one forge finishing never clears another
and a lingering ✓ never holds up the forge beside it. `SKILLFORGE_DONE_TTL` is 30s and
`SKILLFORGE_FAIL_TTL` is 60s. The expiry decision is made by the same `jq` call that reads
the file, so the `rm` follows that file's own read immediately. Deciding for all N files and
deleting afterwards is a real bug and not a theoretical one: `skillforge start`, replacing a
finished slot in place, lands inside that window and the reaper deletes the brand-new active
forge — 40 of 40 trials with a dozen expired slots present, and the status line renders once
a second, so "narrow" is no defence. A record with no `finished` falls back to `updated`,
then `started`; with none of the three it is never reaped, because `now - 0` is past every
TTL and would delete a foreign record on sight.

### Reading a directory of slots

Any `*.json` directly under `forge/` that parses and carries `name` and `status` is a forge,
which is how a state file written by an earlier single-file scheme keeps working: it is an
ordinary slot, driven in place, rendered, and reaped on the usual TTL. A file that does not
parse is skipped and left alone — it may be half-written, or from a newer version — and is
never counted, so garbage on disk cannot make every command ambiguous. Temp files are named
`<file>.tmp.<pid>` or `.start.<pid>.<ts>.tmp` and do not end in `.json`, so a render cannot
catch a write in progress.

An `active` forge whose session died has no TTL and keeps every no-argument command ambiguous
until it is cleared. That is deliberate — a real forge can legitimately run for hours — and
the refusal names `skillforge list` and `skillforge clear --name <forge>` for it.

### Idleness is a signal, not a reaper

An `active` forge has no TTL, so a session that stops calling `skillforge step` leaves a
confident, precise, entirely stale phase on screen. Reported after 3h07m at step 11 of 12,
with nothing to distinguish it from a forge stepped a minute earlier.

Past `SKILLFORGE_IDLE_SECS` (2700s) the tail is prefixed with the age of the phase and
turns yellow, the spinner freezes on `⣿` and dims, and the bar stops pulsing. Nothing is
deleted or closed: the no-TTL rule above is unchanged.

The threshold is measured. 33 intervals between consecutive `skillforge` calls, recovered
from Claude Code transcripts across four forges of this repo: median 460s, p90 1211s,
longest working gap 1240s. The next two observations in the sample are 4561s and 11216s,
and 11216s is the reported defect. Any threshold in that empty 21-to-76-minute band
separates the sample identically; 2700s is 2.2× the longest working gap. n=33, one user,
one repository — a defensible floor, not a law, hence the variable.

The marker goes *inside* the padded tail, so crossing the threshold changes no width and
costs the host no redraw.

### A full bar means finished, and only that

`12/12 100%` under a spinner was shown for a forge still running; only the glyph separated
it from a ✓. And `step 14` of a 12-step budget was clamped to 12, so an overrun was
invisible and unrecordable.

While a forge is running the bar stops one cell short and the percentage stops at 99. The
reserved cell names its own reason: `·` still budgeted, `▒` every step spent but not
closed out, `»` past the budget. Over budget the count keeps rising (`14/12`) and the
percentage reads `over`, which is exactly as wide as ` 99%`. Integer division makes
`step * WIDTH / steps` reach WIDTH only at `step >= steps`, so nothing mid-budget moves.

`skillforge step` now stores what it is given. Clamping made an overrun unrepresentable
downstream: `rounds_completed` under-counted it and `skillreport`, which reads only the
ledger, could never report it. `done` raises the step to the budget but never lowers it.

Any status that is not `done` or `failed` is treated as running. Testing `= "active"` let
`status: "paused"` fall through every safeguard at once.

### Width is measured in terminal columns

`jq`'s `length` counts codepoints. A CJK or emoji-presentation codepoint occupies two
cells and a combining mark none, so a Japanese phase padded to 38 codepoints drew 47
columns while the ASCII summary beside it drew 38 — the segment blinked every five seconds
inside one rotation window. `fit()` carries the wide/fullwidth blocks, the emoji that
render double-width from the narrow Miscellaneous Symbols ranges (`✅ ⭐ ⌚`), and the
zero-width marks. The name and terminal-state messages are capped too: unbounded, a
200-character name drew 275 columns and wrapped the line.

### Every tunable is guarded for shape *and* magnitude

`SKILLFORGE_DONE_TTL` and `FAIL_TTL` reach `jq --argjson`: set to a non-number they killed
jq on every slot and blanked the whole segment, exit 0, nothing on stderr. A digits-only
guard is not enough either — `SKILLFORGE_BAR_WIDTH=999999999999999999999999` is all digits
and put `[: integer expected` on stderr four times a second in bash and once in zsh, with
the two shells drawing different things. Six digits is the *shape* guard, and shape is not
the whole problem.

`SKILLFORGE_BAR_WIDTH=999999` is six digits, passes it, and then runs a million
`bar="${bar}·"` appends — still going after twenty seconds, restarted once a second, so
stuck renderers accumulate without bound; `=9999` finishes in about two seconds and emits
a 10,070-column line, and `SKILLFORGE_TAIL_WIDTH=999999` emits a 1,000,044-column one.
So each width knob is additionally bounded by what a terminal can display rather than by
what a number can be: the bar caps at 200 columns and the name and tail at 400, and an
out-of-range value returns to its default rather than clamping to the ceiling, because a
value that far out is a mistake and the default is the only width known to render.

The bound that finally matters is the SEGMENT, not the knob. Each width is legal on its
own and they still sum past the line — `SKILLFORGE_TAIL_WIDTH=400` alone renders 445
columns and 200/400/400 renders 629 — so the three are checked together against one
terminal line (400 columns) plus 23 columns of measured fixed furniture and a margin for
the `[k/N]` counter and a four-digit step field. If they do not fit, all three return to
their defaults; shrinking one to make room would render a geometry nobody asked for and
give no clue why.

`SKILLFORGE_ROTATE_SECS` has its own ceiling, and it bounds how long a forge may be off
screen rather than how large the number may be: too long a period pins
`idx = (now / ROTATE) % n` for that whole period and hides every forge but the current
one, silently, while the `[k/N]` stamp truthfully says there are three. An hour was
neither a small enough bound nor an exclusive one — the guard was `-gt 3600`, so the
documented ceiling value itself passed and hid two of three forges for a full hour. The
ceiling is 60 seconds: a forge is off screen for at most `(n-1) * ROTATE`, so even three
live forges each reappear inside two minutes.

---

## Why the animation is a file and not a process

The status line is the only surface in the terminal UI that updates continuously
([CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md#the-status-line-is-the-only-surface-that-animates)).

**Consequence for the design:** `skillforge` writes a small JSON file and the status line
paints whatever it finds each second. That decoupling is what lets one animation survive
across subagent dispatches: the builder and each red-teamer are separate processes, and
they all update one file.

The refresh would otherwise re-run the user's base status line, typically `git` calls,
once a second, so base output is cached for `STATUSLINE_BASE_TTL` seconds.

---

## Shell portability traps

Each of these fails silently. Nothing errors, and the wrong behaviour looks like the right
one.

**Bash folds multibyte glyphs into variable names.** `bar="$bar▓"` fails with
`bar<mojibake>: unbound variable`, because the UTF-8 bytes of `▓` are parsed as part of
the variable name. Every append must brace the expansion: `bar="${bar}▓"`.

**There is no portable way to index into a string of multibyte glyphs.** `cut -c` is
locale-dependent, bash 3.2 substring indexing (`${v:i:1}`) is byte-based, and zsh arrays
are 1-indexed while bash arrays are 0-indexed. The spinner therefore uses a plain `case`
statement, which is correct under all of them.

**`printf '%s' "…%…"` does not need `%%`.** A literal percent inside an *argument* to
`%s` is not a format string, so escaping it produces a visible `%%`.

**A growable value goes through a file, never through `--arg`.** Linux caps one element of
the argument vector at `MAX_ARG_STRLEN`, which a larger `ARG_MAX` does not raise; macOS has
no per-argument cap at all. A value whose size follows the input -- a rendered block reason,
a transcript excerpt, a file list -- therefore fits on one platform and fails with `E2BIG`
on the other, and a hook that cannot exec prints nothing, which is the failure mode every
gate here is written against. The rule is to put a *path* in the argv and the bytes in a
file: `jq --rawfile`, `grep -f`. That is why `hooks/apply-gate.sh` streams its reason and
why `bin/skillforge`'s backfill and `hooks/remind.sh` do the same, and it is what fixes
jq 1.6 as the package floor `skillforge doctor` asserts. The measured byte counts, the
platform each was taken on and the CI run that caught it are in the header of
`hooks/apply-gate.sh`. They are not in `docs/CLAUDE-CODE-BEHAVIOR.md` and do not belong
there: this is a Linux kernel constant, not behaviour of Claude Code.

**`path` is zsh's array view of `$PATH`.** Same family as `status`, and worth stating
separately because the symptom is not an empty segment but a subtly wrong one. Reading a slot
filename into a variable called `path` replaces the command search path with that one
directory, so every later `jq` in the script is "command not found". The bar still draws — it
needs no `jq` — but the tail loses its padding and the width wobbles once a second, for zsh
users only, with nothing on stderr. `fpath`, `cdpath`, `manpath` and `module_path` are tied
to their scalar twins the same way. The renderer uses `slotfile` and `fstate` for exactly
this reason.

**Tab is IFS whitespace, so `read` collapses runs of it.** An index of tab-separated fields
silently shifts every field after an empty one, and a skill name may contain a tab
(`tests/test_ledger.py` pins this). Both the CLI's slot index and the renderer's field parse
use US (`0x1f`), which is not IFS whitespace and which `start` refuses inside a name.

**Bash reads a script lazily, by byte offset.** It does not parse the file up front, so
rewriting the file while it runs makes bash resume at its saved offset in whatever the file
now holds, and carry on executing in the middle of unrelated text. This is the one entry
here that is not a difference between shells -- every bash does it -- and the only one that
can destroy work already paid for. The reproduction, the incident it cost us, and the shape
of the fix are the section below.

---

## Never edit a script that may still be running

`hooks/session-review.sh` spends sixty to ninety seconds blocked inside a single `claude -p`
call. For that whole window the file on disk is being read, a few bytes at a time, by a live
process. Changing it then does not take effect on the next run. It corrupts the run in
flight.

That is not a worry, it is a bill. On 2026-08-25 at 21:29 this arm made the first real
dispatch it had ever made. The call succeeded and was charged -- one turn on sonnet, 79.8s,
`is_error: false`, $0.2221734 -- and came back with a well-formed candidate. The script was
rewritten on disk while the call was blocked; its mtime is 21:50 and it was uncommitted at
the time. Bash resumed after the call at the offset it had saved, landed inside text that
had not been there when it started, and died. Because the cooldown stamp is written before
the dispatch and this arm's stderr goes to `/dev/null` in production, nothing was indexed,
nothing was announced, no report was composed, and the next qualifying session would have
been suppressed for twenty-one hours. Not one byte of it reached a person. The answer was
recovered by hand out of a staging temp file, and it and the full account are in
[../notes/2026-08-25-first-live-review-verdict.md](../notes/2026-08-25-first-live-review-verdict.md).

**How the shell half was established.** GNU bash 5.3.3(1) on macOS 25.5.0, 2026-08-25,
against Claude Code 2.1.245. Write a twenty-five line script that echoes, sleeps three
seconds, and echoes again; start it; have a second process prepend forty lines of unrelated
prose one second in. Unprotected, the run printed its first line, then
`line 4: non-transferable: command not found`, then executed its own body a second time --
bash had resumed at the byte offset the sleep left it at and found different text sitting
there. Swapping the prepend for a two-line truncation instead gave
``line 4: unexpected EOF while looking for matching `"' `` and exit status 2. The probe is
four lines of shell and runs in ten seconds. Re-run it rather than trusting this paragraph.

**Why the body is wrapped in one brace group.** A brace group is a single compound command,
so bash has to find the matching `}` before it may run any part of it, which forces the
whole file through the parser in one pass. Re-running the probe against a wrapped copy gives
a clean run under the prepend and a clean run under the truncation. A file truncated badly
enough to break the parse then executes *nothing*, which is also the outcome we want: half a
dispatch is worse than no dispatch. The wrapper reads like syntax that does nothing, and an
author who tidies it away re-opens precisely this failure -- which is why the closing brace
is commented and points back at the note just under `set -uo pipefail`, and why `bash -n` is
what proves the brace still closes the file.

**The `exit` before the closing brace is load-bearing too.** A brace group protects its body
and nothing past it. Measured with the same probe: wrapped but with no terminating `exit`,
the body ran correctly to completion, and then bash resumed at the offset just past `}`,
found the prepended text now occupying it, and ran the whole body *again*. So the group is
not sufficient on its own; the script must also never fall off its end. Every path through
`hooks/session-review.sh` ends in `exit`, and the last statement inside the group is
`exit 0`. Nothing mechanical checks that, so it is written down here.

**The standing rule that follows.** Never edit a script that may be running, and count any
script that blocks on a network call as running for a long time. In this package that is not
a rare alignment: every one of these files is executed out of the checkout itself. The hook
and status line entries the installer writes name an absolute path into it, and the CLIs in
`bin/` are symlinked to it, so a `git pull`, a `git checkout`, or one `sed -i` rewrites the
exact bytes a live process is part-way through reading. Stop the process first, or copy the script elsewhere and
edit the copy.

**What was exposed, ranked by window times rate.** Every shipped script now carries both
halves, and `tests/test_script_wrapping.py` enforces it: `REQUIRE_WRAPPED` names the
scripts that must be wrapped, the `KNOWN_UNWRAPPED` ratchet is empty, and a new shipped
script that is neither wrapped nor listed fails the suite. The ranking is kept because it
is the reason the rule exists and the guide for anything added later. Timings are wall
clock on this machine, 2026-08-25.

- `bin/skillcontrib` is the worst of the rest. It blocks on a series of `gh` calls against
  the network, so its window is seconds and set by someone else's latency, and it is run
  from inside this checkout by an agent while other agents may be editing. Same shape as the
  incident, same severity, and the reason it was wrapped first.
- `statusline/skillforge-status.sh` has the highest collision *probability* and the lowest
  cost. Measured at 26ms a run, re-run once a second forever, it occupies roughly 2.6% of
  wall clock; a rewrite of the checkout will eventually land inside one. The damage is a
  garbled status line that heals on the next render.
- `statusline/statusline.sh` is 58 lines, but on a cache miss it blocks on the user's own
  base status line command, so its window is whatever that costs and not what its length
  suggests.
- `hooks/claim-gate.sh` is the only hook here whose window scales with
  the user's history rather than with its own length: it parses up to `CLAIM_GATE_MAX_BYTES`
  of the transcript on every `Stop` and every `Bash` call. Measured 2026-08-26 against this
  session's own 30 MB transcript, three runs: 1202ms, 1242ms, 1234ms. So it is roughly an
  order of magnitude wider than the two below it, on the two most frequent events there are.
- `hooks/insight-capture.sh` (176ms on a 380KB transcript) and `hooks/compound-improvement.sh`
  (120ms) have short windows, but they fire on Stop and on every qualifying tool call, and a
  hook that executes garbage prints it on the channel Claude Code parses. The rule that hooks
  must never break a turn is not enforceable through a file being rewritten underneath one.
- `hooks/skill-use.sh` (283ms cold and 154ms warm on the same transcript, same date) fires
  only on a `Skill` call, which is rare beside the two above. Its exposure is the ledger
  row it appends rather than anything a turn reads.
- `bin/skillforge`, `bin/skillreport` and `bin/skillinsight` are short-lived and local-only.
  They are exposed only in the narrow sense that a `git pull` can land inside one invocation.

---

## Why the red-teamer must be a fresh agent

This one constraint decides whether the red-team loop is worth running at all.

Skills rarely fail on a wrong command. They fail on an *assumed* piece of context: a
directory the author happened to be in, a tool they happened to have installed, an
ordering they knew about and did not write down. The author cannot see those assumptions,
because to them they are not assumptions.

A red-teamer that forks the orchestrating session's context inherits exactly the same
blindness and will report that the skill looks fine. Only an agent with no prior context
can discover that step 1 is unexecutable. For the same reason, each loop iteration spawns
a *new* red-teamer rather than reusing the previous one: after round 1, that agent is no
longer cold.

The retirement check has the same structure for the same reason. Asking a second agent to
"confirm this deletion" is a leading prompt, and it will be rubber-stamped. "Should this
be kept, fixed, or retired?" is a question the agent can actually answer against.

---

## A test cannot read prose for meaning, so `test_doctrine_sync.py` stopped trying

The rule above is mirrored into `docs/architecture.md` and `.claude/CLAUDE.md`, and it
has been
silently deleted from a mirror before, so `tests/test_doctrine_sync.py` guards it. Three
versions of that guard tried to enforce it by scanning the prose for the rule, and each was
defeated on first contact by a fresh reviewer — not by a bug in a pattern, by a rewording:

- `not .{0,20}a fork` certified **"does not have to be a fork"**. The permission passed the
  scan for the prohibition, in all three files at once.
- A rewrite that split prose into clauses and required the negation to govern the verb was
  beaten by "There is **no fork** restriction", by the inflections `forked` and `forks`, by
  pronoun subjects walking through the clause splitter, by an exemption clause phrased in
  the exemption's own words, and by "drive the whole thing itself" where the scan looked
  for the verb `runs`.

Each round ended with the author reporting that every counterexample now failed, which was
true only of the counterexamples tried so far. The set of paraphrases of an English
sentence is not finite, so that loop has no terminating round, and a green suite told three
sessions running that the fork rule was protected when it was not. Reporting safety you do
not provide is worse than reporting none.

What replaced it: each doctrine rule is pinned in `DOCTRINE` as one exact sentence, and
every mirror must contain that sentence verbatim (whitespace collapsed, `*` emphasis
stripped, nothing else). `<!-- doctrine: <id> -->` anchors mark the pinned sentences in
`SKILL.md` and `docs/architecture.md`; they render as nothing and warn the next editor
that the
sentence is pinned. Presence of a known string is decidable; "does this paragraph mean the
rule" is not.

The trade is deliberate and is written into the test's own docstring, and it was measured
rather than assumed: a cold reviewer handed only the documents and the test reversed every
rule pinned at the time -- eight of them -- in a single pass, by keeping each sentence
verbatim and repudiating it in the following clause, with the suite at exit 0. A document can carry its pinned sentence
and contradict it in the next paragraph, and nothing catches that. What
is caught is the drift that has actually happened here: a rule reworded, softened, or
deleted in one document while the others still teach it. Changing a rule now means editing
the pinned sentence in a commit a reviewer can see, which is the point — visible, not
impossible.

---

## Two install paths, and why the installer stays primary

The repo is both a `curl | bash` install and a Claude Code plugin. What the plugin path
carries and what it cannot carry is recorded in
[CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md#what-the-plugin-path-can-and-cannot-carry).
The line that decides this package: a plugin cannot install a `statusLine`.

**The decision: the installer stays the primary path.** A one-line install is a
requirement, and the animation is the most visible thing the package does; losing it
to gain a version pin is a bad trade. The plugin manifest ships alongside so the repo
can be loaded with `--plugin-dir`, submitted to a marketplace, and validated in CI.
`docs/architecture.md` says plainly that the plugin path has no status line.

### Idempotence rather than a rule about running one wiring

With both wirings active every hook event is delivered twice
([CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md#both-wirings-at-once-deliver-every-hook-event-twice)).
Left alone, `CI_EDIT_EVERY=12` silently becomes 6 and every insight is queued twice.

The answer is idempotence rather than a rule telling people not to do it. `claim_once()`
claims an event by creating a directory named for the payload's `.prompt_id` or
`.tool_use_id`. An event with no usable id is always claimed, because losing reminders is
worse than an occasional duplicate.

What every counting hook here needs is that *property*, not that function. `claim_once()`
reaches only inside the script it lives in, and the other two arms had to arrive at it
independently: insight capture keys its record on a hash of the session id, and the review
dispatcher takes an atomic `mkdir` claim in its own state directory. The dispatcher is the
case worth remembering, because it looks exempt and is not — nothing wires it to an event
at all, and it is still delivered twice, since the hook that launches it is itself on both
paths. Detachment is not isolation.

The order of those guards is load-bearing and was wrong first. A claim taken before the
throttle is consulted is spent whether or not the work happens, so a session the cooldown
turned away could never be revisited. Claim last, once the work is certainly going ahead.

### Counting an outcome means wiring two events

A tool that fails is delivered as `PostToolUseFailure`, never as `PostToolUse`
([CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md#posttooluse-fires-only-when-the-tool-succeeded)).
Anything here that tallies what a session did has to subscribe to both, or it reports each
failure as a success — a wrong number rather than a gap. That is not hypothetical: a failed
`Unknown skill: …` invocation was being counted as skill reuse in `bin/skillreport`. The
same trap is waiting for the live invocation ledger, which matches on `Skill`.

### `CLAUDE.md` lives at `.claude/CLAUDE.md`

A root `CLAUDE.md` fails `claude plugin validate --strict`, and `.claude/CLAUDE.md` loads
as project context the same way
([CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md#claudemd-at-a-plugin-root-fails---strict)).
Since `--strict` is what the marketplace review pipeline runs, the file lives there.

---

## An install pins a ref, and updating is a separate ask

The installed package is a git checkout, so "which version am I running" is answered by
whatever `HEAD` happens to be, and until now nothing chose that on purpose. The clone was
`--depth 1` off the default branch, and a re-install ran `git pull --ff-only` before doing
anything else. Two consequences, both of which a user meets rather than reads about.

The first is that two people who ran the same one-liner on the same day could be running
different code, and neither command line says so. `SKILL_COMPOUNDER_REF` and `--ref` fix
that by naming a tag: the same string gives the same commit next month, which is the whole
content of the word "release" for a package with no build step.

The second is that repairing an install and upgrading it were the same gesture. A user
whose hooks stopped firing re-runs the installer, which is the right instinct, and the pull
handed them a different version of the package than the one that had been failing --
so whatever they were about to report is now about code they have never run. `--update`
and `SKILL_COMPOUNDER_UPDATE=1` make the upgrade something asked for, and a plain re-run
re-wires exactly what is already on disk. `--rollback` is the other half: an upgrade nobody
can undo is one people decline to take.

**Where the previous ref is recorded, and why it is not the manifest.** `<state>/install-ref`
is written by `install.sh`, two lines, current and previous. The install manifest would be
the tidier home for it, and it is the wrong one: `skill_compounder/installer.py` records
what was *linked*, is exercised by a suite that never clones anything, and knows nothing
about a checkout's git state. The rotation rule is the part worth keeping -- previous moves
only when the commit really changed, so an `--update` that lands where it already was
cannot quietly overwrite the thing `--rollback` needs.

**Both flags refuse a clone they did not make.** Running `--update` inside your own
checkout would move your branch and discard what you had there, which is the one thing
uninstall has never been willing to do either, so the two moving flags check that the
checkout is the one at `~/.claude/skill-compounder-app` and otherwise print the `git`
commands and stop. `--ref` in that position is a note rather than a refusal: it selects,
and running the script from a checkout is already a selection.

**`install.sh` is now a script that rewrites itself while running.** `--update` runs `git`
against the checkout it is being read out of, which is exactly the lazy-parse hazard the
shell-portability section above describes. It is wrapped in one brace group and every path
ends in `exit`, for the same reason `hooks/session-review.sh` is.

---

## Proving we made a link, when the checkout has moved

`curl | bash` clones to `~/.claude/skill-compounder-app`; the README also documents
installing from your own clone. Doing one and then the other, or simply `mv`-ing the
checkout, used to wedge the package in both directions. Ownership of a link was decided by
`realpath(link)` falling inside the *current* `app_home`, so after the move all thirteen
links failed the test at once: install reported "NOT LINKED, you already have something by
that name" for every one of them and uninstall reported "left in place (not ours)",
leaving nine dangling skill links and four dangling CLI links forever, with the message
blaming the user for them.

Widening the test is the obvious repair and the wrong one. A rule that matches
`<anything>/skills/<name>` adopts the link of someone whose own `no-silent-stub` lives in
their dotfiles, which is the exact failure the narrow rule was written to stop.

Identity is therefore established by **proof of authorship**, and there are four
independent proofs. Any one of them is enough; none of them is a guess about a path shape:

1. `<state>/install-manifest.json`, written at install time, names this destination with
   this target. This is the same move as `installed-statusline.json`, extended from one
   entry to all of them: what we wrote, recorded where a later run can read it.
2. The manifest names this target under some other destination — the config directory
   moved.
3. The target resolves inside the checkout running right now (the original rule, kept).
4. The target's directory contains `skill_compounder/installer.py` **and**
   `skills/skill-compounder/SKILL.md`, and the link sits at the relative path we would
   have linked it from. The file it points at is one of ours by construction, so adopting
   it takes nothing from the user. This is what covers a second clone with no manifest.

A dangling link with no manifest entry satisfies none of the four. It is left exactly
where it is and reported under `attention:`, naming the link and its dead target — ours to
report, not ours to delete.

The manifest also carries `app_home`, which is what lets
`curl … uninstall.sh | bash` find an install made from somebody's own clone instead of
failing with `can't open file …/skill-compounder-app/scripts/setup.py`.

---

## The status line carries a marker, like the hooks do

Recognising our `statusLine` by exact string match against `"<app_home>/statusline/statusline.sh"`
has the same fragility as the link rule: move the checkout, delete the state directory, and
uninstall can no longer prove the entry is ours. It then leaves `statusLine` pointing at a
script that does not exist and exits 0 reporting success, with no way back.

The entry now carries a marker we author ourselves — a trailing `# claude-skill-compounder`
shell comment — which is what the two hooks have always done. It is location-independent,
so the checkout can move; and it cannot collide with a user's path the way the substring
`statusline.sh` collided with their `~/bin/git-statusline.sh` and the directory-qualified
form collided with `$HOME/dotfiles/statusline/statusline.sh`. A status-line command is run
through a shell, so the comment costs nothing
([CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md#a-statusline-command-is-run-through-a-shell)).
The three older recognitions are kept as fallbacks so an entry written before the marker is
still removable.

---

## Check first, or say exactly what landed

A read-only `~/.local/bin` used to raise `PermissionError` *after* the hooks, the status
line and every skill were live. The user read a traceback and "it failed" while
actually holding most of an install with `skillforge` missing from PATH.

Everything install needs is now proven writable before anything is applied, by creating and
deleting a real temp file in each destination rather than by reading mode bits, which lie
on NFS, under ACLs and on read-only mounts. All the problems are reported at once. An
`OSError` that still happens mid-loop is attributed to the name it happened to and surfaced
as `errors:` with a non-zero exit, because half an install plus a traceback tells the user
nothing about which half.

---

## Removability outranks strictness

Malformed shapes are split by direction. **Install** refuses and names the offending key
(`hooks.PostToolUse[0].hooks`), because merging into something we cannot read means
guessing at settings that are not ours. **Uninstall** never refuses: a shape we cannot read
holds no entry of ours anyway, and a `statusLine` that is a plain string — which used to
raise `AttributeError` in both directions — must not be the reason a user is stuck with the
package installed. `hooks: null` is read as "no hooks" rather than as an error.

---

## Two writes that are not what they look like

`os.replace` onto a symlinked `settings.json` deletes the link and leaves a regular file,
silently orphaning a stow / chezmoi dotfiles source with exit 0. Every write resolves the
link first and writes *through* it, with the temp file created beside the resolved target so
the rename stays on one filesystem.

The temp file also gets a unique name per writer: a fixed `settings.json.tmp` lets two
concurrent runs interleave their bytes into one file and then rename the result into place.
And because the backup stamp has second resolution, a second run within the same second
used to overwrite the pre-install backup — the one copy worth keeping. Backups now dedupe
on content, cap at `MAX_BACKUPS`, and suffix rather than clobber.

---

## Uninstall may never refuse

A cold review found that a `settings.json` which does not parse stopped uninstall dead:
exit 1, and all thirteen links still in place. `remove_hooks` had already been written to
tolerate a shape it cannot read, for exactly this reason, but `read_settings` raised a
layer above it. The rule is now uniform and it is worth stating as a rule: **install may
refuse, uninstall never does.** A user whose config was corrupted by anything at all is
precisely the user who most needs to be able to take this package off. Uninstall removes
the links and the state, leaves the file untouched, says which entries are still in it and
why, and exits non-zero so the incompleteness is not mistaken for success.

The same review found five more failures of the same family — a report that did not match
what happened:

- **Enumeration came only from the current checkout.** A skill or CLI renamed upstream was
  invisible to `_skill_dirs` / `_cli_files`, so `git pull` + reinstall + uninstall left a
  dangling `skillreport` on `PATH` while the report said "removed" and exited 0. Both
  commands now also enumerate the names the manifest records for those directories.
  Install removes such a link only once it is dead, so a name still served by another
  checkout is never pulled out from under it.
- **Stale status-line state resurrected a deleted status line.** With no `statusLine` in
  settings there is nothing to restore, so `original-statusline.json` and
  `statusline-base.sh` are deleted at install rather than kept.
- **`_probe_writable` walked up past a dangling symlink**, because `exists()` is false for
  one. A dangling `~/.claude/skills` therefore passed preflight and the install failed
  nine times over, after the hooks and status line were live, with "File exists" as the
  only explanation. The walk now uses `lexists` and names the dead link.
- **"left in place (not ours)" was printed for links that are ours** when the directory was
  read-only at uninstall. A failure to remove is now its own category, `OURS BUT NOT
  REMOVED`, and it sets a non-zero exit.
- **A checkout with no executable bits installed silently.** `cli (none found)`, a
  `statusLine` pointing at a file the shell will not run, exit 0, and next-steps telling
  the user to run `skillforge`. Preflight now refuses, listing the files and the `chmod +x`
  that fixes them.

And two smaller ones: `write_manifest` had the fixed-temp-name race `write_settings` had
just been fixed for, and an empty hook list of the user's (`"PostToolUse": []`) was deleted
by uninstall, so install records which event keys already existed and uninstall puts back
exactly what it found.

---

## The doctrine ships in `CLAUDE.md`, in a marker block

The reminders went out before the rule they refer to did. `hooks/compound-improvement.sh`
tells a session to check for an existing skill and to notice what is costly *and*
recurring; both sentences are shorthand for three habits that, until this landed, existed
in exactly one place on earth -- a stanza the author had typed by hand into his own
`~/.claude/CLAUDE.md`. Everyone who ran `install.sh` got a hook naming a doctrine their
session had never been shown. That is the same defect class as a status line pointing at a
file the shell will not run: wired, plausible, and referring to nothing.

**Why a marker block rather than a file of our own.** A `~/.claude/CLAUDE.md` is loaded as
context for every session on the machine, and it is the user's document. Shipping a
separate file next to it would need the user to include it, which is a step they have to
be told about and can forget; overwriting theirs is out of the question. The block is the
smallest unit that can be found again later without a record on the side: install replaces
what is between the two comments and leaves the rest, uninstall cuts out exactly that
span, and a second install is a no-op because the rendered block is a pure function of the
checkout path. The markers are HTML comments so they render as nothing in every viewer,
and they name the package, so a reader who finds one knows what put it there.

**Why the heading is detected outside the markers.** The first machine this would ever run
on already had the stanza, hand-maintained, with no markers around it. Appending would
have handed that session the doctrine twice, which is worse than not shipping it: two
copies drift, and the reader cannot tell which is current. So install looks for
`## Compound Improvement` in everything *except* our own block, and when it finds one it
prints a notice, records `doctrine: "user-owned"` and writes nothing. Excluding our own
block is not a refinement -- searching the whole file would find the heading we just wrote
and report every install after the first as the user's, so the block could never be
updated again.

**Why not a hook.** A `UserPromptSubmit` hook could inject the doctrine as
`additionalContext` and never touch a file. It was rejected for three reasons. It pays
tokens on every prompt for a rule that changes about twice a year; it is invisible to the
user, who cannot edit, argue with, or grep what the model was told; and it is not durable
across the surfaces that read `CLAUDE.md` but run no hooks of ours. The habits are
standing instructions, not an event response -- and this package already has the event
response, which is the part that was working.

**What uninstall is allowed to delete.** The block, always. The file, only when install
created it, nothing but our block is left in it, and the path is not a symlink -- a link
means the name was pointed at a dotfiles repo after we made the file, and unlinking the
target would take a file we never created. That is the same rule the symlinks obey above:
remove only what we can prove we made.

---

## Why `hooks/skill-use.sh` wires an event that never arrives

The platform side of this is in
[CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md): a skill call that does not run is not
handed to any hook we can register. What follows is why this package wires the failure arm
regardless.

**A dead branch here costs nothing and a missing one costs a wrong number.** The arm is
four lines; if the platform ever starts delivering those events, the recorder is already
correct on the day it happens, with no release of ours in between. The opposite mistake is
not symmetric. A recorder listening only for success writes `ok:true` for everything it
ever sees, which is the defect `skillreport` already had to have fixed once, when a single
uninstalled skill carried its headline from 80% to 100%. A wrong number is worse than an
absent one because nobody goes looking for the source of a plausible figure.

**So the two instruments stay separate rather than being reconciled.** `skillreport skills`
reads ledger rows, which are a live census of invocations that ran. The default table reads
transcripts, which is the only place a refused call leaves a trace at all. Adding the two
would produce a total that is neither, so nothing in `bin/skillreport` adds them, and the
view says on its own first screen which one it is showing.

---

## Why the claim gate is a hook, and why its evidence is defined by subtraction

`skills/claim-provenance` is about this defect class and deliberately hands off the
moment of claiming done. Nothing picked that moment up. The skill written for it ships in
the `superpowers` plugin and has never been invoked here, and the wording is not why: a
skill has to be *chosen*, and the party who would have to choose it is the one who already
believes the work is finished. So the check cannot be something a session elects. It has to
be something a session meets. That is the whole argument for `hooks/claim-gate.sh` being a
hook, and it is the reason the same defect could not be fixed by rewording a description.

**Evidence is what this session's own tools printed, minus what a subagent said.** The
subtraction is the design, not a filter bolted on. Both defects the gate exists for were
figures handed up by a dispatched agent and then repeated as fact — a commit message
asserting 1495 tests where the derived count was 1195, and another asserting 544 passing
tests on a tree that failed one. A rule that accepts any digits appearing anywhere in the
transcript accepts precisely those, because a subagent's report is in the transcript. So
tool results belonging to `Agent` and `Task` calls are removed before the search runs, and
a relayed figure is a finding by construction.

**The window is a latency budget, not a correctness choice, and it should be read as a
recall cost.** The hook is wired with a ten-second timeout, and only the last
`CLAIM_GATE_MAX_BYTES` of the transcript is parsed, so a figure printed early in a very
long session and repeated at the end is judged unsupported. That is a false block, in the
direction this gate is least allowed to err. The obvious repair is to search the part of
the file outside the window for the candidate figures and suppress any that turn up there;
it was built and rejected on measurement, because BSD `grep` has no fast multi-pattern path
and the trial took 21 seconds for four patterns. Do not re-attempt that without a different
tool. The `PostToolUse` accumulator is the path that actually restores full-session recall,
and it is not wired by default.

A refusing mechanism needs a spending limit more than an asking one does, so the gate stops
after `CLAIM_GATE_MAX_SESSION` blocks and denials in a session and lets everything through
afterwards. A reminder that misfires is noise; a refusal that misfires and cannot be
exhausted is a session nobody can finish, and the honest failure mode for a heuristic this
imprecise is to stand down rather than to keep insisting.

---

## Two figures that are records, not measurements

Findings about Claude Code itself have their own file,
[CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md). What follows is local: two facts about
this repo's own ledger, and two numbers from this repo's history that are quoted in the
skill and are not evidence about anything else.

**The ledger's `rounds` means different things on `fail` and on `done`.** Established by
running `start <name> 12` -> `step 8` -> `fail`, which records `rounds: 3` alongside
`rounds_planned: 5`: the completed count derived from the step reached, and the budget.
On `done` the arm RAISES the step to the budget but never lowers it —
`.step = (if .step > .steps then .step else .steps end)` — so the two agree only when the
forge finished at or under its budget, which is the ordinary case and the reason a
completed forge that stayed on plan cannot tell you how many rounds it actually ran. An
OVERRUN survives that arm and is recorded: `start over-one 8` -> `step 14` -> `done` writes
`rounds: 6, rounds_planned: 3`. `bin/skillforge`'s own comment states the intent, "a start
record carries the plan; a done or fail record carries what happened", and it is accurate
for `fail` and for an overrunning `done`; for a `done` at or under budget, `rounds` is the
plan restated. Reading a `done` record's `rounds` as a measurement is the mistake to
avoid; `ai-tell-audit` records 5 against a five-round budget and ran seven.
`skillforge ledger` and `skillreport` now
print the budget beside the completed count whenever the two differ
(`6 of 3 round(s) (over)`, and `6/3` in the ROUNDS column), so an overrun is visible
rather than merely representable.

**The ledger's start-to-outcome join claims each outcome once and reports what it cannot
match.** Walking start records only discarded a `done` whose `start` was lost — the state a
SIGKILL between the `ln` slot claim and `ledger_append` produces, 4 of 60 trials — so
exactly the forges that crashed went unreported. Matching by name alone also let one
`done` be consumed by two starts of the same name, reporting an abandoned forge as
finished with the other one's date, duration and phase.

**From this repository's history, not the platform.** Two figures quoted in
`skills/skill-compounder/SKILL.md` are single observations from forging in this repo, and
are not reproducible platform behaviour: the reviewer-bias A/B, where one file reviewed
against a "do not flag these" brief and against a neutral one produced 1 finding and 4;
and the `ai-tell-audit` round citations used to justify the round cap. Both are honest
records of what happened once. Neither is evidence about how any other repository, or any
other model version, will behave.

---

## Six failures that produce no error
Each of these looks like it works. None of them is caught by anything except running the
code somewhere else, or at a scale nobody has tried, which is what the ubuntu-plus-macos
matrix and the cold red-team agents are for. A seventh failure of the same kind belongs to
the platform rather than to this repo: a frontmatter break can leave a skill loaded, named
and triggerless, which is recorded in
[CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md#the-skill-loader-tolerates-an-unquoted-colon-and-silently-drops-a-lost-description)
and is why `SkillFrontmatterTest` in `tests/test_plugin.py` parses the frontmatter itself
rather than shelling out to the CLI.

**`stat -f` means different things on the two platforms.** On BSD it selects a format; on
GNU coreutils it means "report on the filesystem", so `stat -f %m "$cache"` exits 0 on
Linux and prints a mount point. A `stat -f %m ... || stat -c %Y ...` chain therefore never
reaches the GNU branch, a numeric guard turns the mount point into 0, and the status-line
cache misses on every render, re-running the user's base status line once a second. Try
GNU first and validate that the result is numeric before trusting it.

**`shutil.rmtree` in an installer is a data-loss bug waiting for a name collision.** The
seed pool puts several plausible names into `~/.claude/skills/`, one of which is
`session-handoff`. Replacing whatever sits at the destination destroys a skill the user
already had, and uninstall then removes the link as "ours" and leaves them with nothing.
Install and uninstall both replace or remove only a symlink they can prove they created,
and report the collision otherwise.

**`$?` after `if ! cmd` is the status of the negation.** It is always 0, so
`if ! run_capped ...; then rc=$?` makes any diagnostic below it dead code. Capture the
status directly.

**A trailing `&&` is the script's exit status.** `[ -n "$x" ] && echo …` as the last command
of a case arm makes the whole script exit 1 whenever `$x` is empty. `skillforge start`
printed its forge, wrote its state, appended its ledger row and then exited non-zero purely
because it had nothing extra to say. Nothing errored; a caller checking the status simply
read a healthy forge as a failure. Use `if`/`fi` for a conditional final statement.

**`jq --argjson` turns a huge integer into a float.** `--argjson t 99999999999999999999`
stores `1e+20`, which then fails every integer test downstream: bash prints
`[: integer expected` on stderr and a numeric guard folds it back to 1, so a forge at step 5
renders as a full bar at 100%. Bound the magnitude at input, and clamp rather than fold when
reading a value you did not write.

**A mutation that fails to apply looks exactly like a test that caught nothing.** Mutation
testing is only evidence if the mutation landed. An anchor string that spans a line break
in the file makes the replace a silent no-op, the suite stays green, and the honest reading
of a green suite is "my guard has a hole" — so a working guard gets reported as broken and
then widened for no reason. This has now happened twice in this repository, both times on
text wrapped at the column limit, which is most prose here. Assert that the mutated file
differs from the original before you run anything against it.

## Three gates, and the reason there are now three

`hooks/claim-gate.sh` was for a long time the one component here that refused anything, and
its own header argued that a refusal is a different mechanism from a reminder rather than a
louder one. Issue #19 supplied the measurement that turns that argument into a rule for the
whole package: the edit checkpoint fired at edits 12, 24 and 36 in one session and was read
past every time, seven of the nine skills shipped *at the time of that measurement* never
arrived on their own in real work, and
`superpowers:verification-before-completion` — whose description is an excellent statement
of its own problem — had been invoked zero times in 1,988 transcripts. Wording was never the
variable. A thread absorbed in one fix answers *"is this recurring?"* honestly with *"no"*,
every time, because from inside the fix it is not recurring.

So the three components issue #19 asked for are refusals, not notices, and each refuses at
the only moment its evidence exists.

**The documentation gate refuses at the push, because that is where the diff is knowable.**
A session about to push knows exactly which commits are leaving and exactly which files they
touched. Nowhere earlier is that set decidable, and nowhere later does it matter. What the
gate does not do is audit the prose itself — that is `claim-provenance`'s procedure, and the
deny reason names it. The division is the point: **a hook decides *when*, a skill carries
*how*.** Building the audit into the hook would have meant a second, worse copy of a mature
skill, running in a context with no model in it.

**The escape hatch is read from the command text and never from the environment.** An
exported variable is an escape taken without noticing it was taken — it survives from an
unrelated shell, it applies to every push for the rest of the session, and nothing on any
surface records that it was in force. Requiring `DOC_GATE_OVERRIDE="<reason>" git push …` to
appear in the command, or a `Doc-Gate-Override:` trailer in the commit being pushed, makes
taking the escape a deliberate act with a written reason, and every one of them appends a
row to `<state>/doc-gate/overrides.jsonl`. An escape nobody can count is indistinguishable
from a gate nobody has.

**How `notes/` is classified is a per-repository decision, so it became a knob rather than a
rule.** The original rule counted it as neither code nor documentation, on the argument that
a dated log is not a description of the system and that counting it as documentation would
let every push here satisfy the gate by adding a session note — exactly the shape of
compliance the gate exists to refuse. That argument is sound about *this* repository and
wrong about most others, where `notes/` is where the writing lives; and it was not a
judgement the gate should have been making on anyone's behalf, since a hardcoded path shape
built on one repository's habits is how a gate acquires a reputation for being wrong.
`DOC_GATE_NOTES` states it instead: `doc` by default, because a `notes/` directory is
usually prose someone wrote, and `neither` where it is a log. This repository sets `neither`
in `.claude/settings.json`, which keeps the original behaviour exactly where the original
argument holds. The evidence that this needed to be a knob is that the only
`DOC_GATE_OVERRIDE` in the record was taken against the hardcoded version.

**The repeat gate spans three events because the thing it recognises is a sequence.** A
failure is one event, the call that worked instead is another, and the next attempt at the
failure is a third, in a later session. No single event carries a repeated mistake; only the
join does. `PostToolUseFailure` is the only event that carries both the failing command and
the error text, which is why the learning arm hangs there and not on `PostToolUse` — a
failed `Bash` call fires no `PostToolUse` at all.

**Its signature is split into a call key and an error class, and the split is forced by the
event ordering.** A `PreToolUse` hook is asked to judge a call *before* it has failed, so it
cannot know which error it is about to get; it can only ask whether *any* recorded error
class is attached to this call key. Folding the two into one opaque hash would have made the
gate unable to answer its own question at the moment it is asked. Keeping them separate also
stops a command that failed once for a transient reason — a timeout, a rate limit — from
sharing a signature with the same command failing structurally, which is the difference
between a useful refusal and noise.

**The gate denies once per session per signature, and would be worse if it denied always** —
when it denies at all, which by default it does not (`REPEAT_GATE_REFUSE`; the measurement
is in that script's header and the operational summary in `.claude/CLAUDE.md`).
The recovery it names is a heuristic — the first success of the same tool after a failure,
inside a bounded window, agreed across sessions by plurality — and a heuristic that cannot be
overruled is a trap. One refusal forces a decision; a second attempt in the same session goes
through. That is the same shape the claim gate's per-claim `dfile` has, for the same reason.

**The apply gate exists because "installed" and "used" were two hopes, not one event.** A
forge used to end at `skillforge done`, which links the skill and writes the outcome row.
Nothing then used the skill on the problem that caused it, and nothing could tell the
difference between a skill that solved its case and one that was never tried. `done` keeps
its ledger contract untouched — every existing reader selects `start`/`done`/`fail` by name
and must keep answering as it did — and instead writes a **debt**: a marker under
`<state>/apply-pending/`. `skillforge apply` discharges it with an `apply` row carrying
verbatim evidence, and the `Stop` hook blocks the forging session's turn while the debt
stands — **once per skill per session, and then it lets go**. It is a flag raised where it
cannot be missed, not a wall: describing it as refusing to end the session overstates it in
the direction that makes a reader switch it off, which is the one thing a hook must not
invite.

**Only the forging session is refused, and a marker from another session is shown rather
than blocked on.** Blocking someone's turn over a forge they did not run is the misfire that
gets a hook switched off, and a hook that has been switched off protects nothing. The status
line carries the other case instead, which is where a standing debt belongs: visible,
unignorable, and costing nobody a turn.

**`--outcome declined` is escapable, and has to be.** A session that finds the new skill did
not apply must have a correct move available; the alternative is a session with no way out
of a gate, which is worse than no gate. What is enforced is therefore that *an outcome was
recorded with a reason*, not that the outcome was true. That is a real limit and it is
stated rather than papered over — the ledger can count declines, and a skill declined every
time it comes up is a finding the ledger can surface even though no hook could.

## The reminder store sits beside the counters directory, not inside it

`hooks/compound-improvement.sh` has kept its per-session counters in `<state>/reminders/`
since long before anything recorded a reminder, and it sweeps that directory on a timer.
Tier 1 needed a durable store on the same state root and could not have one under a path
something else deletes from. So the store is `<state>/reminders.jsonl`, a **sibling** of
that directory rather than a file in it, and `hooks/remind.sh` keeps its own claims,
cooldown stamps and hit log under `<state>/remind/`. The two paths differ by one character
on purpose, and a test asserts that the sweep cannot reach the file: renaming either one to
make them read differently would move a path two shipped scripts already agree on.

**Removal is a tombstone, and the asymmetry with a note is deliberate.** A note is one line
in a `CLAUDE.md` that a person reads and edits, so `skillnote remove` deletes its line
outright — a commented-out corpse in prose is litter someone has to read past every time. A
reminder is a row in an append-only file written by a hook nobody is watching, where one bad
expression in a rewrite loses every row at once, so removal appends `{"id":…,"t":"remove"}`
and readers
skip an id a later tombstone covers. That is the rule `skillrepeat forget` already follows,
for the reason it follows it, and it also means the hook never has to open the store for
writing while a CLI may be appending to it.

**Nothing prunes either file yet, and that is a decision rather than an omission.** The
budget that bounds cost is a read bound — `REMIND_MAX_ROWS` reads the tail — so growth costs
disk and not latency, and no reminder becomes wrong merely by getting old. A pruner would
have to decide which rows are dead, and the only honest input to that is hit counts nobody
has yet. Writing one now would mean guessing a retention rule and then measuring against a
store the rule had already shaped.

**Every line the hook emits is framed as a record of something that happened, never as an
instruction.** The wording was measured together with the delivery field, and both results
are in
[CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md#pretooluse-additionalcontext-reaches-the-model-an-allow-reason-reaches-nothing).
The local consequence is what belongs here: the frame `Reminder recorded on <date> for this
project:` is not decoration around the text, it is what makes an arbitrary sentence safe to
deliver. A reminder whose own text is an imperative still arrives inside
that frame, so the frame cannot be dropped for the cases where it looks unnecessary.

## `bin/skillnote` reimplements the installer's file-writing rules in shell

`skill_compounder/installer.py` learned four rules the hard way about writing a file that
may be a symlink into someone's dotfiles repo, and `bin/skillnote` writes exactly that kind
of file: a `CLAUDE.md`. Sharing the code was not available — the CLIs are shell and `jq`,
the installer is Python, and making a CLI shell out to the installer would put a Python
dependency on the one path that has never had one. So the rules are implemented twice, and
`.claude/CLAUDE.md` carries the instruction to change both halves together.

Two of the four are restated locally, because the shell versions can fail in ways the Python
cannot. Resolving a symlink by hand means looping on `readlink`, which needs an iteration
cap or a link pointing at itself hangs the CLI instead of erroring; and a backup
stamped to the second collides with itself when two `add`s land in the same second, so the
second one takes a suffix rather than overwriting the copy taken before the change — the
copy that is the only reason to keep backups at all.

**What is deliberately not shared is the decision to write at all.** The installer writes a
`CLAUDE.md` once, at install time, under a user who is watching. `skillnote` writes one
whenever a session records a lesson, which may be from a detached process after the session
ended. That is why its refusals are wider than the installer's: an unknown scope, an empty
text, a second marker block in one file, and a memory directory that does not already exist
all stop it before anything is opened for writing.

## The paid review is opt-in, because the install is a one-liner

`hooks/session-review.sh` is the only thing here that spends the user's Anthropic quota and
the only thing that sends any part of a transcript off the machine. It shipped defaulting to
on, with the cost and the off switch written up in the README, and that was the wrong trade
for one reason: the advertised install is
`curl -fsSL .../install.sh | bash`. A person who pastes that has agreed to install a package.
They have not necessarily read the README section that says a detached `claude -p` will
start reading their sessions, and they have not been shown a price. Telling someone afterwards what you
already took is disclosure; it is not their agreement, and a default that has to be
retracted is the shape of a default that should never have been set.

So `SKILL_COMPOUNDER_REVIEW` defaults to `0`, and only the literal `1` enables it -- the same
shape `SKILL_COMPOUNDER_REVIEW_FORGE` already had one layer down, though that one is off for
a different reason, and its own block says so: not the money, but a completion gate a
dispatched session cannot reach. The
asymmetry with `SKILL_COMPOUNDER_REPEAT_GATE` and the rest is deliberate: every other switch
in this package turns off something free, so its default costs a user who ignores it nothing
but noise. This one costs money.

**What did not become opt-in is the capture.** `hooks/insight-capture.sh` still writes the
weekly candidate queue, `hooks/precompact.sh` still fills it from a transcript a compaction is
about to replace, and the session audit still runs. None of them asks a model anything; they
are `jq` over files the user already has. Turning those off with the review would have cost
the user the whole feature to save them a bill they were not being charged, and would have
left an installed package that does nothing at all until a variable is set.

**Reading the switch has to be identical in three places, and one of them is a report.** The
launch site in `hooks/insight-capture.sh` decides whether to spawn anything; the first gate in
`hooks/session-review.sh` decides whether the spawned script proceeds; `doctor` in
`bin/skillforge` tells the user which way it is set, and is the only surface that does, since
the script is in neither wiring. A `doctor` that read the default differently from the script
would report a state nothing is in -- which is worse than not reporting, because it is
believed. `tests/test_doctrine_sync.py` derives the documented default from the
`${VAR:-default}` in the scripts, so the fourth copy, the one in prose, cannot drift either.

**The gate stays at position 10, and that is deliberate.** It is still first,
still ahead of the per-session claim, the lock, the cooldown stamp and any read of the
transcript, and `tests/test_session_review.py` asserts that a refusal there leaves nothing
under the reviews directory. A gate that refused after taking the session's one claim would
spend no money and still consume the session, which is the bug the cooldown ordering already
taught us once.

## Why the `PreCompact` capture is a second script and not a third arm of the first

`hooks/insight-capture.sh` already reads the same two signals and writes the same weekly
queue, so a `PreCompact` arm inside it looks like the smaller change. It is not, and three
things decide it.

**That script does two Stop-shaped things unconditionally on load.** `session_audit` keys
its claim on the session id alone, so a `PreCompact` delivery would spend the session's one
audit record mid-session, on a session that had not finished, describing counters still
being written. `dispatch_review` then launches a paid `claude -p` — from inside a hook that
the compaction is blocked on. Both would have to be guarded by an event test, and a file
that is mostly `if this is not PreCompact` is a second script wearing the first one's name.

**The budgets are different by two orders of magnitude.** A `Stop` hook that takes a second
delays a turn. A `PreCompact` hook that takes a second delays the compaction, because
`PreCompact` blocks and has no default timeout: issue #8 measured a 300-second hook holding
a compaction for 300.9 seconds. Giving it a timeout instead is worse, not better — a
3-second timeout against a 10-second writer left a `CLAUDE.md` truncated at line 4 of 11,
and the next session loaded the truncated file as project context with no error. So the
whole design of this hook is "do less", and it starts from a different place than a hook
that gets `last_assistant_message` free.

**The cost model is process starts, not bytes.** Measured against a 5 MB transcript, 15 runs
each, macOS 25.6.0: 27.4 ms with no candidate and 86.3 ms with one, at the default 256 KB
bound with `/usr/bin/jq` (jq-1.7.1-apple). The same hook on a `PATH` whose first `jq` is
anaconda's 1.6 medians 62.4 ms and 147.9 ms. Doubling the bound to 512 KB costs 11 ms;
swapping the jq costs 62 ms. That is why the transcript read and the candidate scan are one
`jq` rather than two, and why `tests/test_precompact.py` pins the number of programs the
hook runs rather than a wall-clock figure: a stopwatch assertion tight enough to catch one
added `jq` flakes on a loaded machine, and one loose enough not to flake catches nothing.
Issue #8's 100 ms holds on the system jq and not on every `PATH`, and the honest way to
state it is with the `PATH` attached.

**Where the per-compaction claim sits, and what it is actually for.** It is taken after the
candidates are in hand, not at the top of the script, and two rules point at that line.
Claiming before the gates that can still refuse is the bug `hooks/session-review.sh` shipped
first. And the queue directory is created on first write and never on load, so a claim taken
at the top would have to create `insights/` on every compaction that captured nothing —
which is most of them — turning "nothing was captured" into something no caller can test
for.

It is also not what keeps the queue clean. The content claim inside `queue_record` already
stops a second delivery writing a second row. What the per-compaction claim protects is the
duplicate **counter**: without it, the second delivery walks every candidate, finds every
content claim held, and bumps `.dedup-count` once per candidate per compaction, so
`skillinsight stats` would report "duplicates skipped" as a count of how many times the hook
is wired. That is the same distortion the `quiet` flag prevents on the session audit,
arriving from the other side.

**What must not diverge between the two scripts is the digest, and nothing else.** They keep
separate claims, separate clocks and separate bounds on purpose. But the normalised
candidate text is hashed to produce the name a record is looked up under, so if `hash_of` or
`normalise` drifted between them the same sentence would get two rows under two digests and
nothing would report it. `tests/test_precompact.py` proves they agree the only way that
means anything: it runs both real hooks over one transcript — with the `Stop` hook given no
`last_assistant_message`, so it takes its own transcript-read path — and asserts the second
one writes nothing.

The payload this is all built on, and the probe that captured it, are in
[CLAUDE-CODE-BEHAVIOR.md](CLAUDE-CODE-BEHAVIOR.md).
