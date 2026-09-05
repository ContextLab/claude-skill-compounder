# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code *configuration* package. It installs every skill under `skills/`, six CLIs,
a status-line wrapper, and twenty hook entries into `~/.claude/`. Those twenty span eight
events (`SessionStart`, `SubagentStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
`PostToolUseFailure`, `Stop`, `PreCompact`) and
name ten of the eleven scripts in `hooks/` -- every one but `session-review.sh`, which is
launched rather than wired; derive them from
`OUR_EVENT_MARKERS` in `skill_compounder/installer.py` rather than from this sentence.
There is no runtime service: the "program" is the
set of files the installer wires into someone else's Claude Code config.
`README.md` is the front door only: value, install, cost, the five-minute path, supported
versions, updating and a Status block. It was the whole documentation until the split of
2026-09-03 (issue #40) cut it from 1245 lines to what `wc -l README.md` now reports.
Eight documents under `docs/` carry the rest. Six have an audience of their own and are
listed here; the other two are procedures reached from `docs/development.md`:

- `docs/CLAUDE-CODE-BEHAVIOR.md` is verified behavior of **Claude Code itself**, useful to
  a project that shares no code with this one. Each entry is meant to name the finding, how
  it was established by running something, and the CLI version where it was recorded, and
  as of 2026-09-05 exactly one does not, and it is the one that could not: "SessionStart
  fires before anyone has typed" was established by counting `SessionStart:startup` events
  over 475 stored transcripts spanning every CLI version installed here, so there is no
  single version to name and the entry says so. "A child running and its result arriving
  are separate events" was the other one and now cites 2.1.245. Re-derive the gap
  rather than trusting this sentence:
  `awk '/^## /{if(h!=""&&!v)print h; h=$0; v=0} /2\.1\.2[0-9]+/{v=1} END{if(h!=""&&!v)print h}' docs/CLAUDE-CODE-BEHAVIOR.md`
  (it also prints the "Recorded elsewhere" pointer section, which is not an entry). Add a
  platform finding there, not to `DESIGN.md`, with the version, and carry its measured
  limits with it.
- `docs/DESIGN.md` is the **local rationale**: why each piece of this package is shaped the
  way it is. It links to the platform file rather than restating a finding.
- `docs/architecture.md` is **what the parts are**: the component table, the two install
  paths, the seed pool, the three habits, the forging protocol with its two diagrams, the
  claim gate, the status line, and what the ledger records. It is also the **long-form
  doctrine mirror** — the `<!-- doctrine: <id> -->` anchors moved here from `README.md`,
  so `tests/test_doctrine_sync.py` reads it as `PROTOCOL_DOC`.
- `docs/operations.md` is **what you type**: `skillforge doctor` and `reap`, the candidate
  queue, the installer's `CLAUDE.md` block, the state layout, proposing a skill upstream,
  and the tuning table with every knob. The knob tables and the derivation command that
  claims to print every name a script reads both live here now.
- `docs/measurement.md` is **what is counted and what it is worth**: `skillreport`'s
  blocks, the destructive-op trial, and the three limits on every figure in the repo.
- `docs/development.md` is **working on the repo**: the suite, the rules it is written
  under, and pointers to `docs/e2e.md` and `docs/releasing.md`.

Read the first two before changing anything in `bin/`, `statusline/`, or `hooks/`. Several
of the constraints there look arbitrary. They are not. Nothing may live in both of those
two files: a moved claim that reappears in `DESIGN.md` fails `tests/test_docs_split.py`,
which also asserts that every relative link in every shipped document resolves.

## Commands

```bash
./run_tests.sh                                  # full suite (stdlib unittest)
TEST_TIMEOUT=60 ./run_tests.sh                  # tighter per-file cap while iterating
PYTHONPATH=$PWD python3 tests/test_hook.py -v   # one file
PYTHONPATH=$PWD python3 tests/test_installer.py InstallerTest.test_install_is_idempotent
```

`run_tests.sh` loops over `tests/test_*.py` and runs each as a script, so a new test file
is picked up with no registration. `PYTHONPATH` matters only for `test_installer.py` and
`test_plugin.py` (the others shell out and need no import).

Each file runs in its own process group under a wall-clock cap (`TEST_TIMEOUT`, default
300s), enforced by an inline Python runner that kills the whole group on timeout. Killing
only the direct child is not enough: a surviving grandchild holds the inherited stdout
pipe, so `./run_tests.sh | tail` blocks for the full hang even after the runner exits. A hook script reads its payload with
`payload="$(cat)"`, so **every** `subprocess` call against a hook must pass `input=` or
`stdin=DEVNULL`, or it hangs forever.

Exercising the installer by hand (**never** against your own config):

```bash
python3 scripts/setup.py --claude-dir /tmp/fake-claude --bin-dir /tmp/fake-bin --state-dir /tmp/fake-state
python3 scripts/setup.py --uninstall --claude-dir /tmp/fake-claude --bin-dir /tmp/fake-bin --state-dir /tmp/fake-state
```

`install.sh` / `uninstall.sh` are thin shells that locate the app home and `exec` into
`scripts/setup.py`; the real logic is `skill_compounder/installer.py`.

Requires `jq` (hooks, CLIs, status line) and `python3` (installer only). The `gh` tests in
`test_contribute.py` skip cleanly without `gh` or without auth. **Two tests skip on every
ordinary run** and are the only ones that do. `test_skillreport_rename.py::ItActuallyNeededFixing`
wants `SKILLREPORT_BIN` aimed at an older `bin/skillreport` to contrast against, and proves
nothing pointed at the working copy. And `test_routing_claims.py::LiveProbeTest`, which
is opt-in behind `SKILL_ROUTING_PROBE=1` because it spends 72 real `claude -p` calls (216
at the default `--runs 3`), twelve pinned skills at six prompts each, re-derivable with
`python3 -c "import sys;sys.path.insert(0,'scripts');import routing_claims as rc;
print(sum(len(s['must_fire'])+len(s['must_not_fire']) for s in rc.all_skills()))"`. Derive
the skips by reading the run rather than from this sentence:
`grep -c '\.\.\. skipped' <the run's output>`. `grep -rln skipTest tests/*.py | wc -l` returns
**15** files, most of whose guards never fire; the fifteenth is `tests/test_mission.py`,
whose guard fires only where `surfer` is off the `PATH`. The `*.py` is load-bearing: over `tests/`
the answer depends on which grep you have, because `/usr/bin/grep` counts gitignored
`__pycache__/*.pyc` as source and the ugrep an agent shell gets does not.

Six CLIs ship in `bin/`, all shell + `jq`: `skillforge` (forge state, the ledger, the
red-team round record and the apply debt a closed forge leaves), `skillreport` (ledger
joined against transcript invocations), `skillinsight` (the candidate queue), `skillcontrib`
(contribution reconnaissance, and `propose`, the one command that packages a skill, forks
when the acting account is not a maintainer, pushes a branch and opens the pull request --
bare `skillcontrib` and `recon` stay read-only, and `recon` is `propose --dry-run` byte for
byte), `skillrepeat` (the repeat gate's store of learned
failure signatures), `skillnote` (notes into a `CLAUDE.md` or a memory file, and reminders
into the store `hooks/remind.sh` reads).

**There are three tiers of output, and each writes somewhere different.** Tier 0 is a note:
`bin/skillnote add` puts one dated line under a `<!-- skillnote:begin -->` marker block in a
project `.claude/CLAUDE.md` or a global `CLAUDE.md`, or writes a memory file plus the
`MEMORY.md` index line that gets it read back. Tier 1 is a reminder: `skillnote add
--remind` appends a match rule to `<state>/reminders.jsonl` and no `CLAUDE.md` at all, and
`hooks/remind.sh` states it back when a prompt, a path or a command signature matches. Tier
2 is the forge, which writes a skill directory and the ledger rows around it. A note waits
to be read; a reminder arrives; only the forge costs hours. Both cheap tiers write a `note`
ledger row, so the two of them are counted rather than assumed. **`skillnote add --lesson
<sig>` writes both cheap tiers in ONE command**, which is what a fail-then-fix costs if it
is to cost anything at all: the dated line in the scoped `CLAUDE.md`, a reminder keyed
`--command` on the failing call's normalised signature taken verbatim from that signature's
fail row in `<state>/repeats/index.jsonl`, and one ledger `note` row carrying `lesson_sig`,
`reminder_id` and `attachments`. An unknown signature exits 2 and points at `skillrepeat list`.
`--attach <path>` repeats and is valid without `--lesson`: it copies the file into
`<scope>/lessons/<note id>/`, preserves the executable bit and appends `(attached: <path>)`
to the line, refusing a path outside the working tree or `$HOME` and an occupied
destination before a single byte is copied. **That path is written in whatever form
resolves from where the line is READ**, and `attach_ref()` is the single place a
destination becomes text, so the note, the ledger row and a promoted line cannot spell it
three ways. A project note is read by a session sitting in that repository, so it names
the file relative to the repository root: `.claude/lessons/<id>/<file>`. A global or a
memory note is read from every repository on the machine, where that same string names a
directory in whichever project happens to be open, so those two scopes name it
`~`-anchored -- `~/.claude/lessons/<id>/<file>` -- and a claude directory outside `$HOME`,
which no `~` can name, gets the ABSOLUTE path. Measured 2026-09-05: a session in another
project was handed the relative form and had to run `find ~/.claude` for the file.
`skillnote promote <id> --to global` MOVES a
project note -- the line, its attachments and its reminder's scope together -- and leaves a
one-line tombstone that says where it went; never a copy, and `--to project` exits 2, because
the hierarchy only goes up. It rewrites exactly ONE thing on the line it carries across,
the `(attached: ...)` suffix, through that same `attach_ref`, so a promoted line and a note
added at `--scope global` spell one location one way. **`skillnote remove <id>` takes the
reminder with the note**, which until 2026-09-05 it did not: `--lesson` writes two records
under two ids, and removing the note left the reminder firing a lesson nobody could read
any more. The join is the ledger, which `--lesson` wrote both ids into --
`ledger_reminder_of` reads the LAST ledger row for that note id carrying a `reminder_id`,
so a `promote` row, which carries the id the reminder took at its new scope, answers
instead of the `add` row it superseded and the withdrawal follows the pair wherever it now
lives. The withdrawal is the same append-only tombstone every other removal writes, the id
goes onto the `remove` ledger row as `reminder_id`, and one line of output says so;
`--keep-reminder` leaves it live and says that too.

**`skillnote where` exists so that nothing else has to resolve a scope for itself.** It
prints the absolute path a note or a reminder of a given `--scope` (`project`, `global`,
`memory`, `remind`) would be written to, and nothing else. `skillinsight promote` is its
first caller and the reason it exists: that command writes into the CANDIDATE's own project
rather than the caller's cwd -- which is where the finding applies and is deliberate -- so a
promote run from a scratch directory used to write a note into a repository the caller was
not in and report only "promoted". It now prints `skillinsight: target <abspath>` BEFORE it
writes anything, and refuses outright when the project directory that path sits under does
not exist, since `skillnote` creates `.claude/` but not the project above it and would
otherwise conjure a whole tree for a candidate whose repository has been moved or deleted
(`--project <dir>` is the way out). The path is ASKED of `bin/skillnote` rather than
recomputed: a second copy of the four scope resolutions is exactly the drift this file warns
about elsewhere, and it would be invisible, because both halves would still print something.

## Architecture

**The animation is state-driven, not process-driven.** `bin/skillforge` writes a single
JSON file; `statusline/skillforge-status.sh` renders whatever it finds, once per second.
Nothing streams, which is what lets a forge animate across subagent dispatches.

**That file is deliberately not session-keyed**, and the two session ids are why. Do not
make it session-keyed without reading `docs/DESIGN.md` first. `hooks/compound-improvement.sh`
*does* key its reminder counters per session, which is correct: it both reads and writes the
payload's `.session_id`. So does `hooks/remind.sh`, for its own claims and cooldown stamps --
name the script, because since Wave 2 "the reminder hook" is two of them. Since 2026-09-03
(#33) `hooks/remind.sh` also sweeps that per-session tree itself, in
`prune_stale_sessions()`: on a 1-in-`REMIND_PRUNE_EVERY` draw it removes any other session's
`<sid>/` and `<sid>.seen/` whose mtime is more than `REMIND_PRUNE_TTL` behind `REMIND_NOW`,
and never the sweeping session's own pair, so a claim or a cooldown stamp cannot vanish from
under a live session. It walks one level under `<state>/remind/` only, so `reminders.jsonl`
and the counters directory are out of its reach by construction, and `tests/test_remind.py`'s
`PruneTest` pins both. The same change trims `hits.jsonl` to its last `REMIND_MAX_ROWS` on
the delivery path (`HitsCapTest`); before it the cap bounded only the read.

**Installation is marker-based and surgical.** `installer.py` identifies its own hook
entries by marker substring (`HOOK_MARKER`, `INSIGHT_MARKER`, `REMIND_MARKER`,
`MISSION_MARKER`), and its
status line by `STATUSLINE_MARKER` -- a trailing `# claude-skill-compounder` shell comment
it writes into the command itself. Never a substring like `statusline.sh`, which also matches a user's own
`~/bin/git-statusline.sh`, and never the bare path, which stops matching the moment the
checkout moves; the three location-bound recognitions are kept only as fallbacks for
entries written before the marker. Install is idempotent and uninstall removes only our
entries -- including under `SessionStart` and `SubagentStart`, the two event keys
`OUR_EVENT_MARKERS` gained with `hooks/mission.sh`, where a user's own `SessionStart` hook
is left exactly where it was. Other tools' hooks and an unrelated status line are left
untouched. `settings.json`
is backed up before every write and written atomically, and *through* a symlink rather than
over it, so a dotfiles source is not orphaned; a malformed `settings.json` disables every
setting in it. Malformed shapes split by direction: install refuses and names the offending
key, uninstall never refuses. Read `docs/DESIGN.md` before changing either side of that.

**That backup-atomic-through-symlink discipline now has two implementations, and they must
not drift.** `skill_compounder/installer.py` applies it to `settings.json` and to the global
`CLAUDE.md` stanza; `bin/skillnote` applies it to whichever `CLAUDE.md` a note lands in,
reimplemented in shell because that CLI is shell + `jq` like the other five. The four rules
are the same four in both: resolve the symlink and write through it, back up beside the
*configured* path rather than the resolved one, `mktemp` in the resolved file's own
directory so the `mv` is a `rename(2)`, and never truncate in place. `BACKUP_PREFIX` is the
same string on both sides. Change one and change the other, or a user whose `CLAUDE.md` is
stowed loses it from whichever half was left behind.

**The status line wraps whatever is already there.** Any pre-existing `statusLine` command
is saved to `<state>/statusline-base.sh` (plus `original-statusline.json` for restoration)
and called first by `statusline/statusline.sh`. It lives in the state directory, so
`git pull` cannot clobber it. Base output is cached for `STATUSLINE_BASE_TTL` seconds
because a 1s refresh would otherwise re-run the user's `git` calls every second.

**Hooks must never break a turn.** `hooks/compound-improvement.sh` exits 0 on every failure
path, emits `{suppressOutput:true, hookSpecificOutput:{...additionalContext}}` when it
fires, and emits nothing at all when throttled. Tuning defaults (`CI_EDIT_EVERY=12`,
`CI_PROMPT_COOLDOWN=1200`, `CI_PROMPT_MIN_CHARS=60`) live in the script and are echoed in
the README tuning table. Change both.

**The repo is two install paths at once, and they must not drift.** `install.sh` writes
entries into the user's `settings.json`; `hooks/hooks.json` plus `.claude-plugin/plugin.json`
make the same repo loadable as a plugin. `tests/test_plugin.py` asserts the two wire the same
scripts to the same events with the same matchers, so adding a hook to one and forgetting the
other fails a test. A plugin cannot carry `statusLine`, which is why the installer stays
primary; see `docs/CLAUDE-CODE-BEHAVIOR.md` for what the plugin path does and does not
carry, and `docs/DESIGN.md` for the decision.

**The edit checkpoint counts `Bash`, not just `Write|Edit`.** `mutates_file()` in
`hooks/compound-improvement.sh` inspects `tool_input.command` and counts only commands
that write. Detection from a command string is a lower bound on purpose: a heredoc into
`python3 -` calling `write_text` is caught, a runtime-assembled path is not. Since
2026-09-05 the redirect alternative reads a SEPARATE copy of the command with single- and
double-quoted spans and `<...>` placeholders blanked, so the `>` inside `skillnote add
--lesson <sig> "<what was learned>"` is no longer a redirect and writing a note is no
longer an edit. Only that alternative reads the stripped copy, and the split is the point:
`write_text`, `writeFileSync` and `open(..., 'w')` live INSIDE quotes by construction --
`python3 -c "...write_text(...)..."` -- so running them against it would erase the very
writes this branch was widened to catch. A placeholder is `<...>` with NO whitespace in
it, which is what keeps `cat < a.txt > b.txt` a write; what it concedes is a redirect
written inside quotes (`bash -c "echo x > f"`), which now goes uncounted. Undercounting
delays a checkpoint; counting `ls` teaches the user to ignore it. A second branch fires
`ai-tell-audit` once per durable-prose file per session, because that skill's description
names a README but nothing otherwise connects editing one to invoking it -- and since the
same change it fires only for a PATH-SHAPED token. `durable_prose` blanks quoted spans and
`<...>` placeholders the same way, and what survives has to carry a `/` (`./README`, a
prose file under a `docs/` directory, and every absolute path, which is what the
`Write|Edit` branch passes) or a
prose extension (`README.md`, `.rst`, `.txt`, `.markdown`). A bare `README` inside a
string is a word in a sentence: `echo "see the README" > notes.txt` writes no README, and
it fired the nudge for a file nothing had touched in two sessions on 2026-09-05.

**`hooks/mission.sh` states the user's own requests back, verbatim, at the five moments a
session is most likely to have lost them.** The mission is this session's prompts as the
user typed them, read from claude-history-surfer's store
(`<store root>/projects/<slug>/prompts.jsonl`, the root being `MISSION_SURFER_ROOT`, else
`CLAUDE_HISTORY_SURFER_DIR`, else `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/history-surfer`, the
order history-surfer itself resolves)
filtered on `session_id`, with commands and empty prompts dropped, under a fixed budget:
the first substantive request up to `MISSION_FIRST_CHARS` (1200), the most recent
`MISSION_RECENT` (3) up to `MISSION_EACH_CHARS` (400) each, the whole capped at
`MISSION_MAX_CHARS` (2400). **Each request is rendered as a prefixed block, never inside
double quotes**: a header line `(request N of M, T chars)` and then every line of the text,
the blank ones included, carrying the fixed `> ` prefix -- `PREFIX_LINE` in
`hooks/mission.sh`, an ASCII constant and deliberately not a knob -- with `> [... N more
chars]` on its own prefixed line where the cap cut it. The form it replaced was
`(request 1 of 1) "<text>"`, and it lost the boundary the moment a prompt carried a double
quote of its own: observed on 2026-09-05 in a real subagent block, where the user's own
nested imperative could not be told from the agent's task. A prefix cannot be closed early
by anything the text contains, and a closing quote is one character the user can type; a
prompt that already begins a line with `> ` merely reads as `> > `. The header sentences,
the closing sentence and `chars` (jq's `length`, never `${#CTX}`) are unchanged. It keeps
NO copy of those prompts -- principle i of
`notes/2026-09-03-mission-and-lessons-design.md`, a single source of truth -- so without
history-surfer it emits nothing at all, and the `surfer` row of `skillforge doctor` is the
surface that says why, rather than a second capture path that would drift from the first.
Every line it emits is a statement of fact and never an instruction: an imperative in an
injected context was refused as prompt injection in 2 of 4 measured runs, and the `Stop`
probe had the model quote the reason and decline the instruction inside it.

The five moments are five events, and the script dispatches on `.hook_event_name` the way
`hooks/claim-gate.sh` does, taking no argv. Each arm sets one `moment` name, and the name
is the anchor to grep for rather than a line number: every line number this section carried
had gone stale within a day of being written, and `grep -n 'moment="' hooks/mission.sh`
prints seven lines -- the initialiser, then the six assignments in `case` order, six rather
than five because `PreToolUse` carries two of them.
`SessionStart` with `.source` `compact` or `resume` delivers the mission
(`moment="resume"`); `startup` is silent, because nothing has been asked yet. `PreToolUse`
on `Agent|Task|Workflow` delivers it to the parent before an expensive dispatch
(`moment="dispatch"`), and `SubagentStart` delivers it to the subagent with one closing
sentence recording that the parent's instructions to that agent are above it
(`moment="subagent"`; the sentence is the `The parent's instructions to this agent` line in
the rendered block). Any other `PreToolUse` delivers it again once `MISSION_INTERVAL` (1200)
seconds have passed since this session's last delivery of any kind, and never inside a
subagent, which got the whole mission at `SubagentStart` (`moment="periodic"`).
`UserPromptSubmit` on a prompt of fewer than `MISSION_SHORT_WORDS` (6) words -- "continue",
"yes", "ok do it", the prompt that relies on memory -- delivers the last substantive request
instead (`moment="ambiguity"`). And `Stop`, guarded by `stop_hook_active`, blocks ONCE per
`prompt_id` with the mission as the reason (`moment="completion"`, claimed by the
`mkdir -p "$SDIR/stop"` then `mkdir "$SDIR/stop/$pid"` pair), when `last_assistant_message`
matches a short completion regex and the turn made at least `MISSION_STOP_MIN_TOOLS` (8)
tool calls.

Each event is claimed once under `<state>/mission/<sid>/`, because both wirings deliver it
twice: an atomic `mkdir` under `seen/`, keyed on `tool_use_id`, `agent_id` or `prompt_id`
and, when the payload carries none of those, on a digest of the payload itself, which is
byte-identical across the two deliveries because it is the same event. The turn's tool
count is one byte per distinct `tool_use_id` appended to `tools/<prompt_id>`, claimed
separately because counting happens whether or not anything is emitted. The session id goes
through the IDENTICAL sanitising expression every other script that keys on one uses --
`printf '%s' "$sid" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-96`, in twelve shipped scripts
(`grep -rlF "tr -c 'A-Za-z0-9._-' '_' | cut -c1-96" hooks/ bin/ statusline/ | wc -l`, as of
2026-09-04) -- and one spelling difference would make a single event two claims under two
names. **Every one of those sites is now followed by the same guard line**, at the same
indentation: `case "$sid" in ''|.|..) sid=_ ;; esac`, with only the variable name changing.
An id that sanitises to the empty string, `.` or `..` would otherwise name the parent
directory or the tree itself. `tests/test_script_wrapping.py::IdentitySanitisationTest`
pins both halves across every shipped script -- the `cut -c1-96` and the guard line after it
-- and fails on a sanitisation written in a shape it cannot read rather than skipping it.
`hooks/mission.sh` sanitises the session id in exactly ONE place, `set_sdir()`, which the
two call sites that need `$SDIR` both go through. Every delivery appends a row to
`<state>/mission/hits.jsonl` (`ts`,
`session`, `moment`, `agent_id`, `chars`, `prompt_count`), trimmed to `MISSION_MAX_ROWS`
(2000) on write as well as on read. `chars` comes from jq's `length` and NOT from `${#CTX}`:
bash counts characters only in a UTF-8 locale and bytes otherwise, and these hooks run
under whatever environment the harness hands them, so a column that is codepoints on one
machine and bytes on the next is the dead-measurement shape of 2026-09-02 all over again.
One limit stands. `PreToolUse` on `Agent` can rewrite a subagent's prompt through
`updatedInput`, measured working, and this design declines that channel in favour of
`SubagentStart`, which says the same thing where the parent can read it; the reasoning is
in `docs/DESIGN.md`. The other one closed on 2026-09-03: `<state>/mission/<sid>/` gains one
byte per tool call and one empty directory per claimed event, and it now sweeps itself the
way `hooks/remind.sh` does. `prune_stale_sessions()` removes
ANOTHER session's `<sid>/` whose mtime is more than `MISSION_PRUNE_TTL` (604800) behind
`MISSION_NOW`, on a 1-in-`MISSION_PRUNE_EVERY` (25; `0` switches the sweep off) draw,
walking one level under `<state>/mission/` only -- so `hits.jsonl` is a file the
directory-only glob never lists, the sweeping session's own tree is skipped whatever its
age, and a name outside the sanitiser's own charset was put there by something else and is
left alone. It has TWO call sites (`grep -n prune_stale_sessions hooks/mission.sh` prints
three lines: the definition and both of them), and
both are exits that deliver nothing, so an event about to emit never pays for a `stat` over
every directory. The first is the periodic `PreToolUse` arm's not-yet-due exit, the most
frequent event this hook sees. The second is the **missing-store exit**, and it is there
because `<state>/mission/<sid>/` OUTLIVES the store it was written beside: a project whose
history-surfer store is deleted, moved or renamed leaves on that branch on every event
afterwards, and with the sweep only on the periodic arm its session trees would never be
swept again by anything. That branch checks `[ -d "$DIR" ]` with a builtin first, so a user
who never installed history-surfer still reaches `exit 0` with no process start on that
path -- which is what `tests/test_mission.py::CostTest` measures.
`tests/test_mission.py::PruneTest` drives both exclusions.

Every numeric `MISSION_*` and `REMIND_*` tunable, and the two `CI_*` knobs
`prune_stale_state()` reads, is now taken through a **shape AND magnitude guard** --
`case "$X" in ''|*[!0-9]*|???????????*) X=<default> ;; esac`, the eleven `?` being the
magnitude half. A value that is empty, non-numeric, or eleven digits or more takes the
DEFAULT rather than being clamped or zeroed, because an out-of-range export is a typo and
the default is the only value the header promises. The shape half alone was not enough: 23
nines is all digits, so it passed `*[!0-9]*` untouched and then made `[` print `integer
expression expected` on a stderr that is still the user's terminal. The other half of the
same defect was `CI_PRUNE_EVERY=0`, which reached `$(( RANDOM % PRUNE_EVERY ))` and had
bash report `division by 0` and the hook exit 1 -- a hook breaking a turn, from a knob the
tuning table lists. `0` now switches the sweep off in all three scripts. Re-derive the
covered set with `grep -n '???????????\*)' hooks/*.sh bin/*` rather than from this
sentence; the remaining `CI_*` knobs carry a shape guard or none, which is a gap and not a
claim of coverage.

**Five hooks can refuse a turn; `hooks/claim-gate.sh` is the one whose evidence rule is
an exclusion.** It dispatches on `.hook_event_name` and takes no argv: on `Stop` it judges
`last_assistant_message`, on `PreToolUse` it judges a `git commit` message, and a figure of
`CLAIM_GATE_MIN_DIGITS` digits or more is unsupported unless it appears in what this
session's own tools printed. Tool results belonging to an `Agent` or `Task` call are cut out
of the evidence first, deliberately: a subagent's report is testimony, and relayed testimony
is what both founding defects were made of. The `PreToolUse` arm is not a nicety — a commit
message never reaches `last_assistant_message`, so the `Stop` arm alone cannot see the shape
of defect the gate was written for. The five are `apply-gate.sh`, `claim-gate.sh`,
`doc-gate.sh`, `mission.sh` and `repeat-gate.sh`; the last two are the new ones, one
blocking a `Stop` and one having gained a second refusing arm. Recount them with
`grep -lE 'permissionDecision:"deny"|decision:"block"' hooks/*.sh`, which is the jq
object-literal spelling the emitting `jq -n` actually uses. The looser recipe this line
used to give -- the bare words `permissionDecision` and `decision` -- does not work, in
both directions at once, measured 2026-09-04: `grep -l permissionDecision hooks/*.sh`
answers five files and they are the WRONG five, since `hooks/remind.sh` only explains in a
comment why it does *not* use `permissionDecision:"allow"` while `hooks/apply-gate.sh`
emits `decision:"block"` and is missed; and `grep -lE 'permissionDecision|decision'`
answers eight, picking up `hooks/compound-improvement.sh` and `hooks/precompact.sh` for the
word alone. A recount that reads a header comment as a refusal is a recount of the
documentation.

Two of its constants are worth knowing before touching either. `CLAIM_GATE_MAX_BYTES` is
`16777216`; it was `67108864` and that cap was **dead code on BSD**, because `wc -c < file`
prints a leading-space-padded count and the numeric `case` guard read the space as
non-numeric and zeroed the value. `tr -cd '0-9'` is the fix and the `case` stays as the
belt. And the header's calibration carries **three** rates, not two, and they are BLOCK
rates rather than false-positive rates -- `grep -nE '[0-9]\.[0-9]%' hooks/claim-gate.sh`
prints all of them. On the corpus the rules were tuned against, the `Stop` arm blocked
2.9% (6 of 205 closing messages, of which 4 were relays flagged by design and **2** were
wrong) and the COMMIT arm blocked 3.2% (3 of 93 `git commit` invocations, **1** a clean
false positive) -- the third rate, and the one the two-rate sentence omitted, because the
commit arm is a second arm on a second corpus and not a restatement of the first. Held
out, the `Stop` arm blocked 3.4% (3 of 88), down from 8.0% before the 2026-08-26 fixes.
Quote the held-out figure; the
tuned one was optimistic by roughly threefold, and the arm the tuned corpus recorded as
never firing was the arm carrying the difference. A second independent draw of 88 under
the same rule measured 5.7% before those fixes, so the pair agrees on the order of
magnitude and nothing finer.

**Of the other four, `hooks/repeat-gate.sh` carries two refusals that ship opposite ways
round, and `hooks/doc-gate.sh` is configured differently in this repo.** The repeat refusal
is the older of the two: `hooks/repeat-gate.sh` has three arms -- learn, recover, refuse --
and only the first two run unless `REPEAT_GATE_REFUSE=1` (`REFUSE="${REPEAT_GATE_REFUSE:-0}"`
is the read site; grep for the name, not for a line number). The default
is measured rather than cautious: on the live store of 2026-09-02 the arm had been wired
across 81 distinct sessions and had never refused anything, and driving the real hook
against all ten signatures that had reached `REPEAT_MIN_SESSIONS` denied none of them,
because every one was exempt under the gate's own head rules (issue #27). Those rules were
narrowed on 2026-09-04, so that clause is re-derived rather than carried: driving the
current hook over the live store, all 13 signatures at the threshold are still exempt, 12
by the allowlist and one as a runner. A synthetic
non-allowlisted signature is still denied, so the machinery works and nothing real reaches
it -- and an arm nobody has watched fire cannot be judged by its false-positive rate. Arms
1 and 2 stay on, so the store keeps growing whatever the switch says. What turns it back
on is one non-allowlisted signature reaching the threshold for real, and the reason that
would be noticed is that `bin/skillrepeat` and `bin/skillreport` now apply the same head
rules before counting. They apply them by ASKING the gate, through its `--eligible-of`
door, rather than keeping a second copy. A second copy drifts from the first invisibly, and
the ten signatures those two CLIs printed as `refuses` while the real hook denied none of
them are what that drift looks like from outside: a number nobody can act on. Each CLI finds the gate by following its own symlinks
back to the checkout, since both install paths put a link in the user's bin directory;
`SKILLREPEAT_GATE` and `SKILLREPORT_GATE` override, and are separate names because the two
CLIs install independently of each other.

**The head exemption both refusals share is judged per SEGMENT, and it fails in the
OPPOSITE direction to `hooks/doc-gate.sh`'s splitter.** `split_segments` walks the command
quote-aware in doc-gate's shape, `segment_head` steps over assignments and shell keywords to
the word that names a program, `head_allowlisted` judges one head, and `allowlisted_head`
grants the exemption only when EVERY segment's head is on the list; `runner_head` wants
every head exempt by one of the two lists and at least one of them a runner. Where a missed
split costs doc-gate a deny it never makes, a missed split here GRANTS an exemption, so
`split_segments` FAILS -- and every caller refuses the exemption -- on an unterminated
quote, on a backslash-escaped quote or `$'...'` accompanied by a separator byte, and past
400 walked characters. The same change strips heredoc bodies before reading them as shell,
stops `2>&1` splitting at its `&` into a head of `1`, and stops `do`, `for` and `done`
counting as heads. It is not a tidy-up: over the 310 distinct `fail` commands in the live
store on 2026-09-04, 141 verdicts change and 134 of them lose a head exemption they should
never have had (re-run on a store since grown to 312: 143 and 136). The hole it closes came
from a live red team rather than review -- `cd build && tar -xf ../release.tgz` was ALLOWed
while the bare `tar -xf ../release.tgz` was denied, and a haiku session found it unaided on
its fifth attempt.

**`segment_head` steps over PREFIX RUNNERS as of 2026-09-05, and `source` and `.` left
`head_allowlisted` in the same change.** `env`, `command`, `source` and `.` sat on that list
as inspection commands while every one of them RUNS THE NEXT WORD, so `env python3 x.py`
answered `exempt-allowlist` where the bare `python3 x.py` answered `eligible` -- measured
live against the installed package, and reproducible in one line per command with
`printf '%s' '<cmd>' | bash hooks/repeat-gate.sh --eligible-of Bash`. `segment_head` now
walks past `env`, `command`, `exec`, `nohup`, `builtin`, `nice`, `timeout`, `caffeinate`,
`sudo`, `doas`, `stdbuf`, `setsid` and `ionice` -- through each one's modelled options
(`sh_flag_solo`, `sh_flag_arg`, `sh_runner_opts`) and `timeout`'s duration word -- to the
program they start, and `command -v`/`command -V` start nothing so they are judged as
`command`. `source` and `.` are simply absent from both head lists now, beside `eval`,
`sh -c` and `xargs`, because what they run is in a file the walk may not read. Unlike the
per-segment change above this one moved NOTHING on the live store: driving both versions of
`--eligible-of` over the 429 distinct `fail` commands there on 2026-09-05, 0 verdicts
change, so the hole was real and had never been walked through.

**The same file carries the lesson arms, and they are the refusal that ships ON.**
Cross-tool recovery comes first, because without it the fail-then-fix of scenario 2 is
never even observed: a failure of tool X followed, within `REPEAT_RECOVERY_WINDOW` (5)
later calls, by a success of a DIFFERENT tool whose normalised input shares at least
`REPEAT_RECOVERY_MIN_TOKENS` (2) content tokens with the failed one binds as the recovery
and writes `"cross_tool":true` on the row (`toks_of`, `overlap_count` and the binding in
`hooks/repeat-gate.sh`; the line numbers move, the function names do not). A content token
is a lowercased run of word characters, three or more, not all digits. **The window is keyed
on (session, agent)**: `PostToolUse` and `PostToolUseFailure` inside a subagent carry
`agent_id` (measured on 2.1.260; the parent's own calls carry none), and the pending-failure
file is named `<sid>` for the parent and `<sid>+<agent>` in an agent (`agent_key()`), so a
subagent's failure cannot be bound to the parent's unrelated success -- which is what
happened live on 2026-09-05, when a forge subagent's failed heredoc was "recovered" by the
orchestrator's heredoc two calls later. The lesson marker and the refusal stay per SESSION on
purpose: dispatching an agent is continuing.
`REPEAT_RECOVERY_MIN_TOKENS=0` turns cross-tool binding off.

**The same-tool rule it extends is no longer left alone for a shell.** `Bash` is a universal
shell, so two calls being the same tool says nothing about their being the same operation.
Over the 231 distinct same-tool `Bash` bindings on the live store of 2026-09-03, 52 (22.5%)
shared not one content token with the failure they were bound to and a further 31 shared
exactly one, 11 of those only the word `echo`; and a binding CONSUMES its armed failure, so
an unrelated success does not merely add a wrong row, it destroys the right one -- four
`gh issue view` failures were disarmed by one `cat`. So a same-tool binding now wants
`REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS` (2) shared content tokens whenever `shell_tool()`
(`shell_tool() { [ "$1" = "Bash" ]; }` -- `Bash` and nothing else) says the tool is a shell. **That
store grows, so re-run the join rather than quoting those figures back** -- late on the same
day it stood at 241 bindings. A capped floor of `min(2, |fail tokens|)` was tried against it
and admitted exactly one binding more, on the word `echo`, and was rejected. What WAS added,
on 2026-09-05, is a second way to earn the binding rather than a lower floor: the same
first-segment program plus at least one shared non-flag argument of any length
(`head_args_of`, `head_arg_bind`; `REPEAT_RECOVERY_HEAD_ARG`, `0` off), because the e2e
journey's own fail-then-fix, `ls --nonexistent-flag .` fixed by `ls -la .`, shares no
three-letter token at all. `git push` then `git status` does not bind under it, `cd` and
assignments are stepped over, and replayed on the live store (772 candidate pairs, 434 bound
either way) it added nothing; before its `cd` clause it added four, all false, all under
`cd`. An exact
self-recovery -- a success whose
normalised call EQUALS the failure -- always binds, because the refusal arm's self-recovery
exclusion is built on those rows and `pwd` carries one token. Non-shell tools are unchanged,
and `0` restores the unconditional binding. What it gives up is a real fix sharing no text
with the failure, which now degrades to silence, and silence is the direction this gate errs
in everywhere else.

THE FIRST TIME, IT SAYS IT: when a `recover` row is written, the `PostToolUse` arm emits
`additionalContext` built by `lesson_statement` -- the failed call, the error head, the call
that worked, and the two commands `skillnote add --lesson <sig> "<text>"` and `skillrepeat
dismiss <sig> --why "<why>"`, the second annotated `(a person at a terminal only)` -- once
per signature per session, as fact and not as an instruction. **One row per (signature, `tool_use_id`), and the statement names the call the
row records.** N failures of one signature arm N separate pending lines and one success used
to bind every one of them, writing N byte-identical `recover` rows -- four under a single
`tool_use_id` on the live store -- while the `s-<sig>` marker was written after the loop for
the FIRST bound signature only and overwritten on every later binding, so a signature the
same success also bound was invisible to the lesson gate, and -- observed live on
2026-09-03 -- the session was told `TEST_TIMEOUT=... ./run_tests.sh` while the marker was
rewritten to `cat notes/OPEN-THREADS.md`. First binding wins now. `claim_once`
covers only the duplicate the two wirings deliver; no claim can see a duplicate inside one
event, so the de-duplication is the row's own. THE SECOND TIME, IT REFUSES: `lesson_gate` denies the next call of ANY tool when a
signature recovered in THIS session has fail rows from `REPEAT_MIN_SESSIONS` or more
distinct EARLIER sessions, no dismissal a person wrote, and no standing lesson. EARLIER
means earlier: the count drops rows whose `.session` is this one, on the lesson arm as well
as the repeat arm, so nothing a session does to itself can build its own refusal. It used
to cheat there -- the repeat arm excluded them and this one did not, so a signature that had
failed in ONE earlier session plus this one was refused, a session earlier than the
doctrine's "second occurrence".

**The deny reason names ONE command, and the omission is deliberate.** It says
`skillnote add --lesson <sig> "<what was learned>"` and does not mention `skillrepeat
dismiss`, even though the first-time statement names both. A live red-team round settled
that: 2 of 2 haiku sessions denied by the gate ran the dismiss command the refusal printed,
with a reason they invented, and carried on. So `skillrepeat dismiss` now records WHO ran
it. Every `dismiss` row carries `actor` -- `model` when `CLAUDECODE` or
`CLAUDE_CODE_SESSION_ID` is set in the environment, `human` otherwise -- and `session`, the
real session id or the literal `cli`. **The gate honours only a human's dismissal**
(`(.actor // "human") == "human"`, so rows written before the field existed count as human).
A model's dismissal is not refused and not silently dropped: it is written, it is on the
record, it lifts nothing, and `skillrepeat list` reports that signature's LESSON column as
`dismissed-by-model`. **Nothing else lifts it, because as of 2026-09-05
`REPEAT_LESSON_MAX_DENIES` defaults to `unlimited` and the refusal has no expiry.** It
shipped at 2 per signature per session, first advertised and then silent: the deny text used
to name the budget and say the call then went through, and a session red-teaming this gate
on 2026-09-04 read that as a schedule and retried until it expired. Going silent was not
enough. Against the installed package on 2026-09-05, 2 of 2 refused sessions spent BOTH
denies on the IDENTICAL command and then ran it, writing neither a lesson nor a dismissal --
and on the live store 2 of the 16 sessions that have ever armed a lesson marker reached the
cap, both of them that red team, so the sentence this paragraph used to carry (nine
sessions, one deny ever spent, none reaching two) was false the day it was checked. What a
false positive costs with no expiry is ONE lesson line for that signature forever, and the
deny gained one clause saying a lesson may record that the failure is EXPECTED -- a
red-green test run, a probe whose error is the answer -- so a session holding a real false
positive has a true sentence to write rather than a wall to outwait. A positive integer
restores a budget for anyone who wants the valve back and `0` still means never refuse;
anything else, a typo included, lands on `unlimited`, and the deny names neither the knob
nor the dismissal. **The per-segment head exemptions above do NOT apply to this arm any
more.** Its one exemption is `lesson_cli_head`: a `Bash` call whose every segment head is
`skillnote`, `skillrepeat` or `cd`, at least one of them a CLI -- `cat`, `git` and `ls` are
CONTINUING, and the thing this arm refuses is continuing -- so the gate still can never
refuse the command that ends it.

It is ON by default, and `REPEAT_LESSON_GATE=0` is the only spelling that switches it off --
exactly the reverse of `REPEAT_GATE_REFUSE`, where exactly `1` switches a refusal on. The
asymmetry is the population each one can reach: the repeat arm's was measured and found
empty, while this one fires only where a failure AND its recovery were both observed in the
session it is speaking to, which is a fact about the session in front of it rather than an
inference from history. Whether a lesson stands is read off the ledger as `add` rows minus
the ids a later `remove` row withdrew, never as "is there a row carrying this `lesson_sig`":
`skillnote remove` appends and deletes nothing, so the simpler read would report a withdrawn
lesson as standing forever while the note itself was gone from the `CLAUDE.md` it was to be
read from. The two learning events are wired `Bash|Skill|mcp__.*` (`REPEAT_LEARN_MATCHER` in
`skill_compounder/installer.py`, mirrored in `hooks/hooks.json`), so an `mcp__*` failure can
be learned at all -- and that third alternative is UNPROVEN rather than proven, since no MCP
tool failure has been observed arriving at a hook here and the store is the only surface that
can settle it. The event that refuses carries NO MATCHER AT ALL since 2026-09-05
(`REPEAT_PRE_MATCHER = None` in the installer, and no `matcher` key on the `PreToolUse`
entry in `hooks/hooks.json`), on evidence rather than appetite: a session this gate refused
on a `Bash` call answered with `Read data/f2.txt` and finished the job, and "before
continuing" is a claim about any tool. So the lesson arm's `[ "$tool" = "Bash" ]` came off
with the matcher and it now refuses every tool while a marker is armed for the session,
subagents included, since they share the session id. The repeat arm keeps its own `Bash`
test, because both of ITS escapes live inside that branch. The not-armed path -- what almost
every delivery now pays -- is exactly four process starts (`cat`, `jq`, `tr`, `cut`), pinned
by `ProcessCountTest` in `tests/test_repeat_gate.py`. The limit that
follows from all of it belongs to the other CLI: `bin/skillnote` refuses `--lesson` for a
fail row whose tool is not `Bash`, because `hooks/remind.sh` keys a command reminder on
`.tool_input.command` and a `Skill` or MCP call has none, so a lesson for one of those is a
note plus a keyword reminder rather than a command reminder.

`hooks/repeat-gate.sh` closes its own stderr with a builtin `exec 2>/dev/null` before its
first process start (`case "${REPEAT_GATE_STDERR:-0}" in 1) ;; *) exec 2>/dev/null || : ;; esac`,
so `REPEAT_GATE_STDERR=1` leaves it attached).
`execve` charges the environment against `ARG_MAX`, so in a band of about 200 bytes under
the launch ceiling the hook itself starts, `jq` with its 30-byte argv starts, and every `sed`
in the normaliser, each carrying a 100-250 byte regex argv, dies with `Argument list too
long` on the hook's stderr -- measured at 891800-891960 bytes of environment, with the
payload `cat` dying at the 892000 ceiling. The command text is not the variable: it reaches
`sed` by pipe from a builtin `printf`, and a 12-byte command died in the same band as a
600-byte one, so no cap on it could fix this and none was added.
`tests/test_repeat_gate.py::ExecNoiseTest` drives the band at one environment size with the
knob off and on, and `--norm-of` was byte-identical over all 435 live store rows.

`hooks/doc-gate.sh` classifies a root-level `notes/` path by `DOC_GATE_NOTES`
(`NOTES_CLASS="${DOC_GATE_NOTES:-doc}"` is the read site): `doc`, the default, means a
notes-only push satisfies the gate;
`neither` means such a path neither satisfies nor triggers it. **This repository sets
`neither`**, in `.claude/settings.json` -- `notes/` here is the dated log the "Notes and
open threads" section below describes, not a description of behaviour. Which way round the
default goes, and why it stopped being hardcoded, is in `docs/DESIGN.md`; do not re-argue
it here. Its command splitter is quote-aware as of the same change, so a `;` or `|` inside
a quoted argument no longer ends a segment; a backslash-escaped quote and `$'...'` are
still unmodelled and both fail toward not splitting, which is the direction the whole gate
errs in.

**With both wirings active every hook fires twice**, so anything a hook counts, stamps,
appends to, or does once must survive being handed the same event twice. That includes
work a hook *launches* rather than does itself: `hooks/session-review.sh` is not wired to
either path, but it is started by `hooks/insight-capture.sh`, which is wired to both, so
one `Stop` starts it twice. Being detached buys it nothing.

The guard is idempotence keyed on something the payload already carries, and each script
spells it differently. `claim_once()` in `hooks/compound-improvement.sh` claims a
directory named for the payload's own `tool_use_id` or `prompt_id`, under the session and
the mode; `hooks/insight-capture.sh` claims on a hash derived from the session id;
`hooks/precompact.sh` claims on a hash of the session id and the payload's `prompt_id`,
falling back to the transcript's size when that field is absent, because a session that
compacts twice must not be keyed to one claim; `hooks/mission.sh` claims on whichever of
`tool_use_id`, `agent_id` or `prompt_id` the payload carries, and on a digest of the payload
when it carries none; `hooks/session-review.sh` claims with an atomic `mkdir` under
`<state>/reviews/.claims/`, behind a global `.lock` directory and a cooldown compared on
`|NOW - last|`. So the rule is *"be idempotent per event"*, not *"call `claim_once()`"* --
that function is local to one script and reaches nothing outside it. Two hazards the next
author will meet: the session id must be sanitised with the **identical** expression in
every script, or one event becomes two claims under two spellings; and the claim must be
taken only once the action is really going to happen. Claiming earlier looks tidier and is
the bug `hooks/session-review.sh` shipped first -- a session the cooldown refused had
already burned its claim, so it could never be reviewed at all. The measured double
delivery is in `docs/CLAUDE-CODE-BEHAVIOR.md`; the choice of idempotence over a rule is in
`docs/DESIGN.md`.

**`hooks/precompact.sh` is a second capture on a second event, and it is a separate
script for reasons the file itself lists.** `PreCompact` fires just before a compaction
replaces the context with a summary, and its payload carries no `last_assistant_message`
(measured on 2.1.259; `docs/CLAUDE-CODE-BEHAVIOR.md`), so it reads a bounded tail of
`transcript_path` and runs the same extractor `insight-capture.sh` runs, writing
`source:"precompact"` into the same weekly queue. Three things to know before touching it.
It is wired with **no matcher**, because `PreCompact`'s matcher selects the trigger and
`manual` and `auto` name the same loss. It blocks the compaction while it runs, so its
budget is process starts rather than bytes and `tests/test_precompact.py::ProcessCountTest`
pins the exec count rather than a stopwatch: **13** programs on the candidate path and
**4** on the empty one, `date` bounded separately (1 start on BSD, 2 on GNU), with zero
slack -- verified by mutation, so shedding a program is a test change and adding one fails.
Issue #8's 100 ms figure is now stated **per jq**, because no single number covers both
builds on this machine. At n=25 interleaved over a 400 KB transcript at the default 256 KB
bound (macOS 25.6.0, 2026-09-03) the system jq (jq-1.7.1-apple) runs 31.8 ms median /
36.0 p90 with no candidate and 84.7 / 87.7 with one; anaconda's jq-1.6 runs 59.1 / 63.5 and
123.0 / 128.9, so 100 ms holds for the system jq at p90 and 1.6 is about 125 ms. jq-1.6
cannot be made to fit: its no-candidate path alone is 59 ms, shedding `git rev-parse` as
well measured 106 ms, and a bash `.git` walk-up disagrees with `--show-toplevel` on
symlinked paths, which on macOS is all of `/tmp`. `custom_instructions` **is** populated, on
2.1.260: `/compact focus on the greeting` put that string in it verbatim, with no prefix,
and a bare `/compact` left it null. The hook ignores the field and should -- its only return
channel is `systemMessage`, which it never writes. Both probes answered "Not enough messages
to compact." and the hook fired anyway, so it pays its cost on compactions that never
happen. And what must stay identical to `insight-capture.sh` is
`hash_of` and the `normalise` inside the candidate scan and nothing else -- that digest is
the shared name the two scripts look one record up under, and it is the only thing keeping
Stop and PreCompact from queueing the same sentence twice. The rationale is in
`docs/DESIGN.md`.

That extractor's paragraph terminator is a **lookahead**, `(?=\n[ \t]*\n|\z)`, and the
scan line is byte-identical in the two scripts. It was a consuming group and that was a
defect: it ate the blank line ending each candidate, so the scan resumed with no newline in
front of the next marker, the leading `(?:^|\n)` could not assert, and every SECOND marker
was dropped -- a marker immediately after another vanished, and three in a row lost the
middle one. Two markers with prose between them were found normally, which is why it went
unseen through both hooks' review. Fixed in both scripts together and measured on
jq-1.7.1-apple and jq-1.6; `test_a_marker_immediately_after_another_is_captured` and
`test_three_markers_in_a_row_do_not_lose_the_middle_one` exist in `tests/test_insights.py`
and `tests/test_precompact.py` alike, and the pair is what stops one copy regressing while
the other does not. The three-marker test is not redundant: two adjacent markers alone pass
on a scan that still skips every other one.

**`hooks/session-review.sh` is the one shipped component that spends money, it is
OPT-IN, and it is in neither wiring.** `settings.json` and `hooks/hooks.json` between
them name
`mission.sh` (five times), `repeat-gate.sh` (three times), `compound-improvement.sh`
(twice), `claim-gate.sh` (twice), `skill-use.sh` (twice), `remind.sh` (twice),
`apply-gate.sh`, `doc-gate.sh`,
`insight-capture.sh` and `precompact.sh` -- twenty entries over ten scripts; grep either for
`session-review` and you get nothing. It is launched by `insight-capture.sh` with `nohup`,
detached, never waited on, and only when that turn's session audit actually wrote a
record *and* `SKILL_COMPOUNDER_REVIEW` is exactly `1`. Look for it there, not in a hooks
list. That default is `0`, and the reason is in `docs/DESIGN.md`: the advertised install
is `curl | bash`, so the spend and the transcript digest both need a yes rather than the
absence of a no. Only the literal `1` passes; every other value, unset included, refuses.
Three files read the switch and all three must spell the default the same way --
`hooks/session-review.sh`, `hooks/insight-capture.sh`'s launch site, and `doctor` in
`bin/skillforge`, which is the only surface that reports which way it is set.
Stage 1 is a single `claude -p` with no tools at all -- `--disallowed-tools` over every built-in, `--strict-mcp-config`,
`--setting-sources ''` -- reading a bounded digest of the transcript and answering
`VERDICT: NONE` or `VERDICT: CANDIDATE <name>`.

Its gates all fail closed, and each reports through one `refuse` helper that prints a
single line to stderr — `/dev/null` in production — and exits on that gate's own code, so
a test asserts on the code rather than on prose. The gates run 10 through 20: the opt-in
switch, recursion, CI/test environment, a state root under a temp directory, no `claude` on
`PATH`, bad argv, then the per-session claim, the lock, the 21-hour cooldown, an
unwritable state directory and an empty digest. 21 and 22 are not gates — they report a
verdict that errored or would not parse, after the money has been spent. Nothing here
exits 0 on a refusal, and nothing needs to: the script is detached, so its status reaches
no turn. `SKILL_COMPOUNDER_DISPATCHED` is
the recursion barrier that does the work -- a `claude -p` we launch is a real session
carrying these same hooks, so its own `Stop` would fire this same script; the variable is
exported into every process the script starts and inherited without limit, and the first
gate refuses on it. The lock and the pre-call cooldown stamp would each stop it too.

Stage 2, the forge orchestration, is **off by default** (`SKILL_COMPOUNDER_REVIEW_FORGE`),
and the reason is not the money. A dispatched forge cannot complete the routing gate that
decides whether it worked: the forged skill's must-fire probes need `claude` calls, and a
dispatched session was refused at the permission layer when it tried -- `claude --version`
came back "This command requires approval". A forge that structurally cannot finish its
own completion gate should not run unattended. When it is switched on, the working
directory is what contains it: the session is started with `cd` into
`<state>/reviews/staging/<name>/` under `--permission-mode acceptEdits`, so writes inside
that directory are auto-approved and everything outside it needs an approval that a
headless session never gets. `~/.claude/skills` is held out of reach by the permission
system, not by the prompt.

**`CLAUDE.md` lives at `.claude/CLAUDE.md`, not the repo root.** A root `CLAUDE.md` fails
`claude plugin validate --strict`, which is what marketplace review runs. The `.claude/`
path loads as project context the same way; both were measured, in
`docs/CLAUDE-CODE-BEHAVIOR.md`.

**The installer discovers what to link.** `_skill_dirs()` and `_cli_files()` walk `skills/`
and `bin/`, so adding a seed skill or a CLI needs no installer change, and
`test_installer.py` asserts every shipped one is actually linked. Removal cannot enumerate
from the checkout alone: a skill or CLI *renamed* upstream is invisible to both walks, so
install and uninstall also read the names the manifest recorded for those directories, and
install prunes such a link only once it is dead.

**history-surfer is a dependency now, so install fetches it rather than assuming it.**
`hooks/mission.sh` reads that project's prompt store and keeps no copy of it, so install
clones `https://github.com/ContextLab/claude-history-surfer.git` into
`<app home>/../claude-history-surfer` -- a SIBLING of the managed checkout, which is what
keeps `--update` from touching it -- and runs its own
`scripts/setup.py --claude-dir <dir> --bin-dir <dir>`, recording `{url, home, sha,
installed}` under `surfer` in the manifest. It clones nothing when `surfer` is already on
`PATH`, when that checkout already exists, when the store already holds prompts (an
installation this run cannot see, and a second copy is how one store becomes two), or when
`SKILL_COMPOUNDER_NO_SURFER` is set; `SKILL_COMPOUNDER_SURFER_URL` and
`SKILL_COMPOUNDER_SURFER_HOME` override the two locations. It NEVER fails the install:
offline, the step is one line in the report and everything that does not need prompts
carries on working. Uninstall leaves it in place and prints how to remove it, on the same
judgement as the state directory -- it holds every prompt the user has ever typed at Claude
Code, this package neither created that data nor can put it back.

`skillforge doctor` runs eleven checks now: jq, state, settings, statusline, skills,
surfer, ledger, counters, forges, mission, review, in that order in the text form and the
`--json` form alike, so the two cannot report different counts. The two new rows are the
pair that make a silent mission visible. `doctor_surfer` PASSes with the prompt count
recorded for THIS project, FAILs when `settings.json` wires `hooks/mission.sh` and `surfer`
is absent -- five wirings delivering nothing, silently -- and only WARNs when nothing wires
it yet, since until then nothing is silent. `SKILLFORGE_SURFER_BIN` points that probe at a
chosen executable. `doctor_mission` WARNs when `<state>/mission/` does not exist, FAILs when
it will not accept a real write (the per-event claim lives there, so an unwritable directory
does not stop the mission, it stops the deduplication) or when a line of `hits.jsonl` does
not parse, and otherwise PASSes with the delivery count and how many of the five moments
they cover.

**The ledger is append-only, and every reader selects its events BY NAME.** `start` and
its matching `done` or `fail` are joined into forges; `origin`, `use`, `verdict`,
`horizon`, `note` (written by `bin/skillnote`) and `escalate` (written by `skillforge
escalate`) are invisible to that join. A reader that classified by exclusion -- "anything
that is not a start is an outcome" -- would have folded every `use` row into the forge
count the day ledger v2 landed, so `tests/test_ledger_v2.py` pins both readers against a
mixed ledger. Add an event type freely; never widen a selector to a negation. Rows carry
fields as well as names, and #37 added three: `from` on `start`, `origin`, `apply` and
`verdict`, holding the lineage id the event descends from; `session` on `start`; and
`candidate` on the `note` rows `bin/skillnote` writes. None of them changes how a reader
selects, and `apply` and `verdict` read `from` back off the ledger by name rather than
asking a caller who ran the forge months earlier.

**`verdict` now reads two more things back off it, and refuses on what it finds.**
`ledger_last_close` returns the NEWEST `done`-or-`fail` row for the name -- newest and not
first, because re-forging after a failed round is this protocol's own prescribed workflow,
so one name legitimately carries a `fail` and then a `done` and the last word is what the
name is now -- and a `fail` refuses the verdict at exit 5, which `--force` does NOT lift.
`ledger_has_apply` asks whether the skill was ever put on the problem that caused it, on
the DUAL `.name`-or-`.forge` match `apply_join` in `bin/skillreport` performs, and its
absence refuses at exit 2, which `--force` DOES lift. The asymmetry is the point: a forge
that produced nothing has nothing to judge and no override can invent one, while a use
recorded outside this ledger is an ordinary situation. Both were driven in a throwaway
state directory on 2026-09-05 and both codes observed. The same commit stopped
`ledger_close_line` inferring the round count from the step reached whenever
`<state>/rounds/<name>.tsv` exists: `rounds_count` over that file is the count, and
`rounds_completed` is only the fallback for a forge that recorded no rounds at all. An
escalation buys a round without the forge necessarily reaching the two steps that would
imply it, so the first forge to escalate twice closed with FOUR rounds on the tsv and
`"rounds":3` on its `fail` row.

**`--trigger` warns, it does not refuse.** Refusing does not produce a trigger, it
produces no row at all: every caller written before the flag existed would exit non-zero,
and the cheapest way past a CLI that refuses is to stop calling it. So the gap is recorded
as a gap -- `trigger_kind:"unrecorded"` -- and counted rather than assumed away.
`SKILLFORGE_REQUIRE_TRIGGER=1` turns it into a refusal for anyone whose callers are all
updated.

**Adoption never claims authorship it cannot prove.** Install writes `origin:"adopted"`
for the skills in this checkout's `skills/`, `origin:"unknown"` for a real directory
sitting in the installed skills directory -- which may be one we forged for personal use
or the user's own work, and nothing on disk can tell -- and nothing at all for a symlink
`_link_is_ours` cannot vouch for. Same four-proof judgement uninstall uses, below: a link
that proves nothing is reported, not adopted.

**`skills/skill-compounder/SKILL.md` is prose, but it is the primary deliverable**: it
carries the three-tier decision, the builder/red-team forging protocol and the retirement
protocol. The tier rule comes first and it is a gate, not advice: a procedure earns a skill
only when it has steps a model gets wrong without them AND a trigger a description can route,
and otherwise it gets a note or a reminder from `bin/skillnote`. Ten days with one output path
produced zero notes, which is what a missing cheap branch looks like.
Its doctrine is mirrored in `docs/architecture.md` and in the global `~/.claude/CLAUDE.md`
stanza, which
`skill_compounder/installer.py` now writes from `DOCTRINE_TEXT` — so the third mirror is a
constant in this repo rather than a file on somebody's machine, and
`tests/test_doctrine_sync.py` reads all three. Changing the protocol means updating all three.
The long-form mirror was `README.md` until the docs split moved the protocol out of it; the
mirror set is the same four files it always was, and `PROTOCOL_DOC` in that test file is the
one name to change if it moves again.

## Constraints specific to this repo

**No mocks, ever.** Every test writes real files, runs the real shell scripts through
`subprocess`, and reads results back off disk. Tests pin nondeterminism with environment
variables the scripts read for exactly that purpose. There are **fourteen clocks, not one**,
which is a number to recount rather than trust: `grep -rhoE '\b[A-Z][A-Z0-9_]*_NOW\b'
hooks/ bin/ statusline/ skill_compounder/ | sort -u` printed fourteen names on
2026-09-03 --
`SKILLFORGE_NOW` (`bin/skillforge`), `CI_NOW` (`hooks/compound-improvement.sh`),
`INSIGHT_NOW` (`hooks/insight-capture.sh` and `bin/skillinsight`, which fall back to
`CI_NOW`), `PRECOMPACT_NOW` (`hooks/precompact.sh`, which pointedly does NOT fall back to
either of those: a script whose clock is someone else's is a script a test can freeze
without meaning to), `SKILL_COMPOUNDER_REVIEW_NOW` (`hooks/session-review.sh`),
`SKILL_COMPOUNDER_NOW` (the
installer's backup stamp), `SKILLNOTE_NOW` (`bin/skillnote`, which stamps both the ledger
row and the `%Y-%m-%d` on the note line), `REMIND_NOW` (`hooks/remind.sh`, which stamps the
per-session cooldown the emit is compared against), `MISSION_NOW` (`hooks/mission.sh`, its
own for the same reason `PRECOMPACT_NOW` is its own, and it stamps both the periodic arm's
`|now - last|` and every `hits.jsonl` row), `SKILLCONTRIB_NOW` (`bin/skillcontrib`, which
stamps the `<state>/contrib/<name>-<ts>` work directory a proposal clones into and the
`contrib` ledger row), and one apiece for the three refusing
gates and the store one of them keeps -- `DOC_GATE_NOW` (`hooks/doc-gate.sh`), `REPEAT_GATE_NOW`
(`hooks/repeat-gate.sh`), `APPLY_GATE_NOW` (`hooks/apply-gate.sh`) and `SKILLREPEAT_NOW`
(`bin/skillrepeat`) -- and session-review refuses `CI_NOW` on purpose, because a
frozen `CI_NOW` makes its `|NOW - last|` cooldown zero forever and silences the trigger
permanently with nothing on any surface to say why. Two more redirect what a script reads
and writes, `SKILL_COMPOUNDER_STATE` and `SKILL_COMPOUNDER_TRANSCRIPTS`; two pin the ages
the status line expires on, `SKILLFORGE_DONE_TTL` and `SKILLFORGE_FAIL_TTL`; and one lifts
a refusal, `SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE`, without which `session-review.sh`
declines to spend money from any state root under a temp directory. One more names an
executable rather than a value: `SKILLFORGE_SURFER_BIN` is the `surfer` `skillforge doctor`
probes, so the dependency row can be driven both ways with nothing on the ambient `PATH`. One more is a real
threshold rather than a pin and reads differently for it: `SKILLFORGE_ACTIVE_TTL`
(`bin/skillforge`, 21600) is measured against **idle** time, since that forge's last
`step`, never against elapsed time, so `skillforge doctor` is the surface that says whether
anything here is working at all and `skillforge reap` is the only thing that unwedges a
forge whose orchestrator died -- by appending the `fail` row it never got, never by editing
the ledger (`SKILLFORGE_DOCTOR_JQ_VERSION` beside it is an ordinary pin, for the one
`doctor` branch a jq from 2015 would otherwise be needed to reach). A new script needs its
own clock: pinning someone else's does nothing to it. This list was derived by running
`grep -rhoE '\b(CI|CLAUDE_SKILL_COMPOUNDER|INSIGHT|SKILLFORGE|SKILLNOTE|SKILLUSE|SKILLREPEAT|SKILLREPORT|STATUSLINE|SKILL_COMPOUNDER|CLAIM_GATE|DOC_GATE|REPEAT_GATE|REPEAT_MIN|REPEAT_RECOVERY|REPEAT_LESSON|REMIND|PRECOMPACT|APPLY_GATE|APPLY_PENDING|MISSION|SKILLCONTRIB)_[A-Z0-9_]+'
hooks/ bin/ statusline/ skill_compounder/ install.sh | sort -u` -- **157** names, over
**22** prefixes, re-run 2026-09-04 on the #43 completion tree. A grep
that reads gitignored `.pyc` files as source adds a `Binary file
skill_compounder/__pycache__/installer.cpython-NN.pyc matches` line per cached bytecode
file -- two on this checkout, so `/usr/bin/grep` answers 158 where the ugrep an agent
shell gets answers 156; that is
the same split that makes the `skipTest` count above depend on which grep you have. Each
hit was then read; re-run the command rather than trusting the list above if the two have
drifted. The three names that wave added -- `MISSION_PRUNE_TTL`, `MISSION_PRUNE_EVERY` and
`REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS` -- all sit under prefixes the alternation already
carried, so the alternation did not have to move for them.

**What the same round turned up instead was a name the command cannot print and must not.**
`bin/skillrepeat` now reads `CLAUDECODE` to decide whether a `dismiss` row's `actor` is
`model`. It carries no underscore, so the `_[A-Z0-9_]+` tail cannot match it under any
prefix, and widening the alternation would have been the wrong repair: it is a name Claude
Code exports into every `Bash` tool call, ours to read and never ours to set, so a tuning
table row for it would document somebody else's knob as ours. It went into
`tests/test_doctrine_sync.py`'s `AMBIENT` allowlist instead, beside `CLAUDE_CODE_SESSION_ID`
and `CLAUDE_HISTORY_SURFER_DIR`, on the identical judgement those two got. An ambient name
is exempt from the completeness claim; a knob never is, and the way to tell them apart is
whether this package is entitled to set it. **Five
times now the command has been narrower than the list it introduces**: it named three prefixes when seven were in use,
seven when fourteen were, fourteen when sixteen were, sixteen when seventeen were, and
eighteen when nineteen were, so
on all five occasions it could not produce the list it introduces. The third was Wave 2
adding `SKILLNOTE_NOW`, `SKILLNOTE_CLAUDE_DIR` and the six `REMIND_*` names to scripts
while leaving the alternation at fourteen prefixes; the fourth was Wave 3 adding
`SKILLREPORT_GATE` to `bin/skillreport` and leaving it at sixteen. `PRECOMPACT` broke the
run: `hooks/precompact.sh` and the eighteenth prefix landed in one change, because
`tests/test_doctrine_sync.py` fails the moment a script reads a name this command cannot
print, and it did. That test is the reason, not diligence, which is the argument for
re-running the command instead of reading this paragraph. A prefix added to a new script
has to be added here too. **The paths are the other half of the same defect and the fifth
occasion is both halves at once.** `install.sh` was outside the path list entirely, and
adding it exposed the nineteenth prefix: two of its four knobs are
`SKILL_COMPOUNDER_REF` and `SKILL_COMPOUNDER_UPDATE`, which the alternation already
covered, but the other two are `CLAUDE_SKILL_COMPOUNDER_APP` and
`CLAUDE_SKILL_COMPOUNDER_STATE`, and the leading `\b` cannot match inside
`CLAUDE_SKILL_COMPOUNDER` -- the position before `SKILL` sits between two word
characters. So widening the paths without widening the alternation would have shipped a
completeness claim that was newly false. A new file that reads a knob has to be added
here whether or not its prefix looks new, and `uninstall.sh` and `scripts/` are still
outside both lists, which is why the README's sentence names the four path groups it
covers rather than every script in the repository.
If new behavior is hard to test without a mock, add a pin like those instead. Tests run with a minimal `PATH` and `HOME` pointed at a
temp dir, so scripts must not depend on the ambient environment.

**Shell portability traps that cause silent failures** (details and reasoning in
`docs/DESIGN.md`):

- Appending a multibyte glyph requires braces: `bar="${bar}▓"`, never `bar="$bar▓"`. Bash
  folds the UTF-8 bytes into the variable name.
- No portable way to index a string of multibyte glyphs (`cut -c` is locale-dependent, bash
  3.2 substring indexing is byte-based, zsh arrays are 1-indexed). The spinner uses a `case`
  statement for this reason; keep it.
- A literal `%` inside an *argument* to `printf '%s'` needs no escaping. Doubling it prints
  a visible `%%`.
- `stat -f %m FILE || stat -c %Y FILE` is wrong on GNU: there `-f` means `--file-system`, the
  bogus `%m` exits 1 but the valid part of the format still prints to stdout, `$( )` captures
  it, and the digits guard then silently falls back. Query the GNU form first and validate
  digits, then the BSD form, as `statusline/statusline.sh` does. Three scripts shipped the
  wrong order on 2026-09-02 and CI on Ubuntu was the only thing that noticed.
- Linux caps a **single** argv element at `MAX_ARG_STRLEN`, a hard 131072 bytes that a
  larger `ARG_MAX` does not raise; macOS has no per-argument cap. So a value that can grow
  -- a rendered reason, a transcript excerpt -- travels through a file or stdin
  (`jq --rawfile`, `grep -f`), never `--arg`. `hooks/apply-gate.sh` emitted nothing at its
  own documented ceiling on Ubuntu until it did.
- Bash reads a script lazily, by byte offset. Rewrite the file while it is running and bash
  resumes at its saved offset in whatever the file now holds, executing the middle of
  unrelated text. This cost us a paid-for review verdict, silently.
  **Never edit a script that may be running**, and a script blocked on a network call is
  running for a long time. `hooks/session-review.sh` is wrapped in one brace group so the
  file must parse in a single pass, and every path through it ends in `exit` so bash never
  resumes past the closing brace; both halves are required, and neither is decoration.
  Every shipped script now carries both halves, not only that one, and
  `tests/test_script_wrapping.py` is the ratchet: its `KNOWN_UNWRAPPED` set is empty, so a
  new script under `hooks/`, `bin/` or `statusline/` that is neither wrapped nor excused
  fails the suite. Adding one means wrapping it, not adding it to that set.

**The red-teamer must never be a fork of either layer** — not of the orchestrator that
dispatches it, and not of the session that dispatched the orchestrator. The default forge has
only one of those layers, the session that dispatched the reviewer, and the rule binds on it
exactly as written; the second layer exists only on a forge escalated past two rounds. This
applies to the protocol in `SKILL.md` and to any work in this repo that follows it. A forked reviewer
inherits the author's blindness and reports that the skill looks fine. Each loop round
spawns a *new* cold agent, because after round one the previous one is no longer cold. The
retirement check has the same shape: ask the neutral *"keep, fix, or retire?"*, never
"confirm this deletion".

**Nothing is ever destructively removed.** Uninstall only unlinks symlinks it can prove it
created, and it leaves runtime state intact. `_link_is_ours` wants one of four independent
proofs of authorship, backed by `<state>/install-manifest.json`; `realpath` inside the
current checkout is only one of them, and on its own it wedged install *and* uninstall the
moment the checkout moved. Widening the rule to a path shape is the obvious repair and the
wrong one -- it adopts a user's own link. A link that proves nothing is reported, not
removed.
Retiring a skill means `mv` to an archive with a `WHY-ARCHIVED.md`, never `rm -rf`.

## Notes and open threads

`notes/` is a dated log, not an index of current behaviour: `2026-08-24-origin.md` for
where the idea came from, `2026-08-25-roadmap-session.md` and
`2026-08-25-implementation-session.md` for how the seed pool and the plugin path were
built, `2026-08-25-forging-session.md` for the seed skills being forged through the
builder/red-team loop, `2026-08-25-issue9-fix-session.md` for the parallel-agent session
behind issue #9 (auto-install, the routing gate, and the routing probes measured on cli
2.1.245), `2026-08-25-first-live-review-verdict.md` for the first real session-review
dispatch and the lazy-parse failure that lost its verdict,
`2026-08-25-completion-claim-gap.md` for the argument that a skill cannot catch a
completion claim and a hook can — the reasoning `hooks/claim-gate.sh` was built on —
`2026-08-26-pipeline-and-claim-gate.md` for the A-E pipeline replacing the numbered
protocol and for the gate landing, `2026-08-26-handoff.md` for the resume state of that
work, `2026-08-26-issue19-plan.md` and `2026-08-26-issue19-session.md` for the three
refusing gates and the loop that ends in recorded use, `2026-08-26-toolbox-state.md` for a
review entry point that carries the command behind every figure in it,
`2026-09-02-audit-and-replan.md` for the subagent audit that found one output path and no
cheap tier under it, `2026-09-02-tiers-design.md` for the two cheap tiers it answers with
(the note and the injected reminder, issues #20, #21 and #23),
`2026-09-02-forge-diet-design.md` for cutting the default forge to two agents and two
rounds (issue #22), `2026-09-03-mission-and-lessons-design.md` for the mission and the
lesson -- what the platform was measured to do on 2.1.259, the five moments, the cross-tool
recovery and the two principles they answer -- `2026-09-03-issue43-completion-session.md`
for the wave that closed #43 and #32 and built #37's lineage id, and
`notes/research/` for the evidence behind the seed-pool selection, the
insight queue, the contribution mechanics, and, in
`notes/research/level-b-search-measurement.md`, the two rounds of judged pairs that
measured level B keyword search and kept it out of the skill.
`notes/OPEN-THREADS.md` is the one file
there that tracks current state rather than history, and its last section, "This machine",
is operational debt on the author's box rather than a property of the code — nothing above
that heading is machine-local, and nothing below it should be read as a repo-wide defect.
Read the dated ones for reasoning, not for the current state of the code.

The two hook constants (12 edits, 20 minutes) are unvalidated. `bin/skillreport` is the
instrument that would settle them, and since #37 it counts rather than estimates: its
`REMINDER CONVERSION` block is a join on session and order, and its `FUNNEL` block reports
each lineage id as delivered, acted on and outcome, with rows carrying no id reported
UNATTRIBUTED rather than dropped. **`ACTED ON`, `OUTCOME` and `UNATTRIBUTED` are a
PARTITION of the ledger, and the block prints its own arithmetic on a `CHECK:` line rather
than asserting the property in prose** -- every `note`/`start`/`use`/`apply`/`verdict` row
is attributed to AT MOST ONE lineage, by the first of four tests that holds (its own `from`,
its own `candidate`, a `note` row whose own id is a delivered lineage, or the lineage
delivered FIRST to the session it was written in, ties by id). It was not a partition
twice over and both halves showed on the live store: a row whose `from` named a lineage no
delivery log knew was counted NOWHERE, and a row was counted once for EVERY lineage
delivered to its session, so `ACTED ON` summed to 104 against 69 DELIVERED and no reader
could say what the column totalled. `ACTED ON` is now also BOUNDED rather than open: a row
attributed by its session alone is a sequence and never a cause, and a session that received
two lineages gives its rows to one of them, so that half of the column is a floor. The
per-lineage table shows the first `FUNNEL_SHOW` (25) and folds the rest into one `(+N more)`
row with the counts included, so nothing under it is computed over a subset. Every nudge
written before 2026-09-03 carries no id, so the funnel's first weeks are mostly the
UNATTRIBUTED column. Having the instrument is not having read
one: it needs real usage across several repositories over real time, and neither number
should move before that data exists. That limit, and the two others
on every figure this repo quotes, are written up for a reader in
`docs/measurement.md`; state them there rather than a fourth time somewhere else. The
skill's own threshold is
deliberately not a number — it asks for a nameable dead end and a second occurrence — so
there is nothing there to tune.

<!-- skillnote:begin -->
## Notes (skill-compounder)

- **2026-09-02** Before editing a SKILL.md's prose or a command block inside one, grep the seed test for the literal string it pins; four rewrites in one session were reverted by a pinned substring. <!-- id:n64622848x189 source:verdict why:"see /Users/jmanning/.claude/skill-compounder/reviews/2026-W36/f7ea3931-3879-4f94-b2ed-df4b8186958b.md" -->
- **2026-09-02** A mechanism meant to catch a pattern across a session must write the record itself: a checkpoint that depends on the session noticing it fired three times in one session and was disregarded three times. <!-- id:n735026689x210 source:session why:"marker record, session f0feae4c, 2026-08-25T20:05:19Z" -->
- **2026-09-02** A session audit's 'distinct files touched' is a floor, not a total: most edits here were shell writes the hook records no path for. <!-- id:n1166131302x139 source:session why:"215 of 288 edits had no visible target (skillinsight 2851595b, 2026-08-26T19:12:28Z)" -->
- **2026-09-02** When a writer and a reader share a format (a hook's counter file and the CLI that reads it, a CLI's stored signature and the hook that compares it), the test must drive the real writer into the real reader; a hand-written fixture pins whichever side its author was looking at and lets the other drift. <!-- id:n2647857843x309 source:session why:"twice on 2026-09-02: test_ledger pinned digit counters the hook never writes (skillreport dead for its whole life); test_skillnote pinned a Bash-prefixed signature remind.sh never compares (every command reminder silent)" -->
- **2026-09-03** To watch a GitHub Actions run for a commit, filter 'gh run list --json headSha,status,conclusion' on a headSha prefix; 'gh run list --commit <sha>' returned nothing here and a watcher built on it timed out silently. <!-- id:n1407736601x223 source:session why:"2026-09-03: first CI watcher waited 27 minutes on an empty result; the headSha filter reported the verdict in one poll" -->
- **2026-09-03** CI lints with apt's shellcheck 0.9.0 on Ubuntu and brew's 0.11.0 on macOS, and the two disagree at warning level (0.9.0 reports SC2120 where 0.11.0 is silent); before raising the floor or pushing a lint fix, run 'pip install shellcheck-py==0.9.0.6' into a scratch venv and lint with that binary too. <!-- id:n674753163x307 why:"2026-09-03: the floor rose to warning on a tree clean under brew's 0.11.0 and the Ubuntu job went red on SC2120 from apt's 0.9.0; the 0.9.0.6 wheel reproduced it locally in one call" -->
- **2026-09-03** Before pushing, run the test files touched under a clean environment, env -i HOME=$(mktemp -d) PATH=/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin PYTHONPATH=$PWD python3 tests/<file>, because the CI runner lacks what this box has on PATH and in HOME; a suite green only here has gone red on CI twice in one day. <!-- id:n4188254070x320 why:"twice on 2026-09-03 a green local suite went red on CI because this box carries something the runner lacks: brew shellcheck 0.11.0 vs apt 0.9.0, then history-surfer on PATH satisfying doctor's surfer row" -->
- **2026-09-04** In jq a function argument is evaluated against the input of the function it was passed to, so index(str(.session)) reads .session off the array; bin/skillinsight's pending_tsv and bin/skillreport's funnel both hit it — second occurrence 2026-09-03 <!-- id:n20301053x257 -->
- **2026-09-04** A numeric env knob read without the shape+magnitude case guard (''|*[!0-9]*|???????????*) reached bash arithmetic or [ -ge ] three separate times on 2026-09-04 (CI_PRUNE_EVERY=0 divide-by-zero exit 1, MISSION_PRUNE_* integer-expression stderr, CI_EDIT_EVERY/CI_NOW); add the guard with the knob, and the KnobGuardTest shape beside it, never later. <!-- id:n3159951125x355 -->
- **2026-09-04** Every file:NNN citation in a doc moves with the next code wave: the cold review found seven off by 60-345 lines the same day they were written. Cite a function name, a moment= anchor or a grep, and reserve file:NNN for the script header that lives beside the line. <!-- id:n1788641960x272 -->
- **2026-09-05** Adding a row to the tuning table in docs/operations.md means moving the spelled-out count phrase ('All sixty-one are environment variables') beside it, because tests/test_doctrine_sync.py::TuningTableTest pins that phrase to the row count; second time a row landed without it on 2026-09-05. <!-- id:n2661101721x298 -->
- **2026-09-05** Four command-matching rules in hooks were wrong in the same way on 2026-09-05 and every one was caught by a live session, none by a test: remind.sh matched the whole command byte-for-byte (compound forms silent), claim-gate's CI-runner regex missed gh api .../check-runs, compound-improvement read the > in a "<file>" placeholder as a redirect, and the head allowlist exempted env/command as programs. A rule that matches command text ships only after a real claude -p session has been driven through the shape it is meant to catch and one it is meant to miss. <!-- id:n2151519607x568 -->
<!-- skillnote:end -->
