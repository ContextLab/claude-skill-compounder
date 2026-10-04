# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code *configuration* package. It installs every skill under `skills/`, six CLIs,
a status-line wrapper, twelve hook entries and one mod into `~/.claude/`. The twelve span
six events (`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `Stop`,
`PreCompact`) and name eight of the eleven scripts in `hooks/` -- every one but
`session-review.sh`, which is launched rather than wired, and `repeat-gate.sh` and
`mission.sh`, whose jobs moved on 2026-10-03 to the function hooks in `mod/compound/`.
Derive the counts from `hooks/hooks.json` rather than from this sentence:
`jq '[.hooks|to_entries[]|.value[].hooks[]]|length' hooks/hooks.json` and
`jq '.hooks|keys|length' hooks/hooks.json`. `OUR_EVENT_MARKERS` in
`skill_compounder/installer.py` still spans eight events, because it also lists the two
retired scripts so that an install over an older one strips their entries.
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
byte), `skillrepeat` (the store of failure signatures `hooks/repeat-gate.sh` kept while it
was wired, which nothing wired adds to now), `skillnote` (notes into a `CLAUDE.md` or a memory file, reminders
into the store `hooks/remind.sh` reads, and a routable skill written from either).

**There are FOUR tiers of output, and each writes somewhere different.** Tier 0 is a note:
`bin/skillnote add` puts one dated line under a `<!-- skillnote:begin -->` marker block in a
project `.claude/CLAUDE.md` or a global `CLAUDE.md`, or writes a memory file plus the
`MEMORY.md` index line that gets it read back. Tier 1 is a reminder: `skillnote add
--remind` appends a match rule to `<state>/reminders.jsonl` and no `CLAUDE.md` at all, and
`hooks/remind.sh` states it back when a prompt, a path or a command signature matches. Tier
2 is a skill and costs ONE COMMAND: `skillnote skill <note id> --name <slug>` writes
`<scope skills dir>/<slug>/SKILL.md` from a note already recorded, copies its attachments
into `<slug>/scripts/`, runs Gate A on what it wrote and removes the directory on a failure,
and appends one `skill` ledger row. `--force` moves an existing skill of that slug into
`<parent of the skills dir>/skills-archive/<slug>.bak-skill-compounder-<ts>/` -- at global
scope `~/.claude/skills-archive/`, the retirement archive -- and never into the skills
directory itself, because Claude Code lists every `<skills dir>/*/SKILL.md` and a backup
left there was a second routable copy of the same skill under another name (measured
2026-09-06, the day it moved). A directory that appears at the slug between the check and
the write is refused, exit 2 without `--force` and exit 3 when the rename would have landed
inside it, and is neither nested into nor overwritten; a replacement that fails after the
previous skill has moved puts it back. Tier 3 is the forge, which writes the same kind of
directory with a builder and cold red-team rounds behind it, and is owed only where a skill
goes upstream or a real session has shown its steps wrong. A note waits to be read; a
reminder arrives; a tier-2 skill is CALLABLE, which is the thing the first two are not; only
the forge costs hours. Both cheap tiers write a `note` ledger row, so the two of them are
counted rather than assumed. `skillnote add` refuses note text or a `--why` that contains
`<!--` or `-->` and turns a newline in either into a space (2026-10-03): a note line is
read back by its trailing comment, so a marker inside the text ends the block for `list`
or forges an id. **`skillnote add --lesson
<sig>` writes both cheap tiers in ONE command**, for a signature already in the repeat
store (the mod does not use it; it writes a plain project note): the dated line in the scoped `CLAUDE.md`, a reminder keyed
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
prints the absolute path a note, a reminder or a skill of a given `--scope` (`project`,
`global`, `memory`, `remind`, `skill`, `skill-global`) would be written to, and nothing
else. The last two are the skills directories `skillnote skill` writes into, and they are
two names rather than one because `skill` is under the project the caller is in and
`skill-global` is under the claude directory. `skillinsight promote` is its
first caller and the reason it exists: that command writes into the CANDIDATE's own project
rather than the caller's cwd -- which is where the finding applies and is deliberate -- so a
promote run from a scratch directory used to write a note into a repository the caller was
not in and report only "promoted". It now prints `skillinsight: target <abspath>` BEFORE it
writes anything, and refuses outright when the project directory that path sits under does
not exist, since `skillnote` creates `.claude/` but not the project above it and would
otherwise conjure a whole tree for a candidate whose repository has been moved or deleted
(`--project <dir>` is the way out). The path is ASKED of `bin/skillnote` rather than
recomputed: a second copy of the six scope resolutions is exactly the drift this file warns
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
entries by marker substring (`HOOK_MARKER`, `INSIGHT_MARKER`, `REMIND_MARKER` and the
other `*_MARKER` constants), and its
status line by `STATUSLINE_MARKER` -- a trailing `# claude-skill-compounder` shell comment
it writes into the command itself. Never a substring like `statusline.sh`, which also matches a user's own
`~/bin/git-statusline.sh`, and never the bare path, which stops matching the moment the
checkout moves; the three location-bound recognitions are kept only as fallbacks for
entries written before the marker. Install is idempotent and uninstall removes only our
entries. Two constants are strip-only: `REPEAT_GATE_RETIRED` and `MISSION_RETIRED` name
scripts install no longer wires, and install and uninstall still remove an entry an older
install wrote for either, `SessionStart` and `SubagentStart` included, where a user's own
hook is left exactly where it was. They are named `_RETIRED` and not `_MARKER` on purpose:
`skillforge doctor` and `tests/test_doctor.py` read every `*_MARKER = "...sh"` line of the
installer as a script that must be wired. The mod is enabled by one element of a path
list, not by a hook entry: install appends `<app home>/mod/compound` (`MOD_DIR`) to
`env.CLAUDE_CODE_PLUGIN_DIRS` (`MOD_ENV_KEY`), keeps every element already there, and
uninstall removes only ours. Other tools' hooks and an unrelated status line are left
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
other fails a test. The mod is the one thing neither hook list can carry: the plugin path
names its MODULE (`"modules": ["../mod/compound/hooks/register.ts"]` in `hooks/hooks.json`)
and the settings path names its DIRECTORY, and `test_both_paths_enable_the_same_mod`
asserts the two resolve to one file. A plugin cannot carry `statusLine`, which is why the installer stays
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

**The package's two in-session jobs are one mod, `mod/compound/`.** A mod is a Claude Code
plugin of TypeScript function hooks. `mod/compound/README.md` is its authoritative
description: the moments, the environment table, the log rows, the journeys' steps and the
measurements. Read it before touching anything under `mod/`, and link to it rather than
restating its tables. It was built and run on Claude Code 2.1.288 only, and the
function-hook API is marked early access in its own type declarations.

`hooks/register.ts` registers two halves. The lessons half (`hooks/lessons.ts`, with the
prompts and parsers in `hooks/judge.ts` and the masking in `hooks/safe.ts`) is one
`tool.call` hook: it holds a failed call per agent loop, asks a model whether a recorded
lesson matches the failure, asks about each of the next two successes whether it is the
fix, and writes a new lesson itself through `skillnote add --scope project` at the
repository root. A lesson that matches in a second project is moved with `skillnote
promote`. It keeps no copy of any note. The mission half (`hooks/mission.ts`, rendering in
`hooks/render.ts`) states the user's own requests back on `prompt.submit`,
`session.compact`, `classic.SessionStart`, `classic.SubagentStart`, `classic.PreToolUse`
and `classic.Stop`, reading history-surfer's store when it holds the session and otherwise
the prompts the running process saw submitted.

Four things about the platform shape that code, each recorded in
`docs/CLAUDE-CODE-BEHAVIOR.md` on 2.1.288. A plugin gets ONE unmatched `tool.call` hook, so
the lessons half owns it and `hooks/calls.ts` carries the two facts the mission needs from
that stream: the tool calls since the user last typed, and which calls are inside a
subagent. `$.env.get` takes a literal name. A module's variables are per process and
survive `/clear`, so anything remembered about a session is keyed on the session id.
And a subagent's hand-back and a task notice arrive on the prompt channel, so
`typedByUser` in `hooks/render.ts` drops them before anything is counted as a request.

Each install path enables it in its own way, as the two paragraphs above say: `install.sh`
through `env.CLAUDE_CODE_PLUGIN_DIRS`, the plugin through `modules` in `hooks/hooks.json`.
It logs to `<state>/mod/events.jsonl` (lessons) and `<state>/mod/mission.jsonl` (mission),
and `mod/compound/tools/report.py` prints the first. `COMPOUND_LESSONS=0` and
`COMPOUND_MISSION=0` switch off one half each. The `COMPOUND_*` names are documented in
the mod's README and nowhere else: `mod/` is outside the knob-derivation command below,
and they have no rows in the pinned tuning table.

Testing it:

```bash
claude plugin validate mod/compound
claude plugin validate --strict .                 # the root plugin, which names the module
claude plugin test mod/compound                   # judge.test.ts, render.test.ts, safe.test.ts; no model calls
python3 mod/compound/tools/journey_lessons.py     # real sessions; by hand, never in CI
python3 mod/compound/tools/journey_mission.py     # real sessions; by hand, never in CI
```

The judge is scored by a replay of labelled pairs sampled from the repeat store:
`tools/sample_pairs.py`, then `COMPOUND_REPLAY=<pairs> claude -p --plugin-dir mod/compound
<<< hi`, then `tools/score_replay.py`. The pairs carry commands from every project on the
machine, so they stay under `<state>/mod/` and never in the repository. Both journeys set
`CLAUDE_CODE_PLUGIN_DIRS=""` in every session's environment, because `--setting-sources`
does not keep out a mod enabled in the user's own settings, and a control session that
loads the mod is not a control. `run_tests.sh` covers the wiring only
(`tests/test_installer.py`, `tests/test_plugin.py`, `tests/test_doctor.py`); nothing in
the suite starts a session with the mod loaded.

**`hooks/mission.sh` is in the repository and wired by neither path.** It is the shell
hook that stated the mission until 2026-10-03, reading the same history-surfer store and
logging to `<state>/mission/hits.jsonl`. `tests/test_mission.py` drives it directly, the
`MISSION_*` knobs configure it and nothing else but `MISSION_SURFER_ROOT`, which the mod
also reads, and the installer's `MISSION_RETIRED` strips its old entries. Its header is the
description of its arms.

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

**Three wired hooks can refuse a turn; `hooks/claim-gate.sh` is the one whose evidence
rule is an exclusion.** It dispatches on `.hook_event_name` and takes no argv: on `Stop` it judges
`last_assistant_message`, on `PreToolUse` it judges a `git commit` message, and a figure of
`CLAIM_GATE_MIN_DIGITS` digits or more is unsupported unless it appears in what this
session's own tools printed. Tool results belonging to an `Agent` or `Task` call are cut out
of the evidence first, deliberately: a subagent's report is testimony, and relayed testimony
is what both founding defects were made of. The `PreToolUse` arm is not a nicety — a commit
message never reaches `last_assistant_message`, so the `Stop` arm alone cannot see the shape
of defect the gate was written for. The three are `apply-gate.sh`, `claim-gate.sh` and
`doc-gate.sh`. `grep -lE 'permissionDecision:"deny"|decision:"block"' hooks/*.sh` answers
five files, because `mission.sh` and `repeat-gate.sh` also carry a refusal and neither is
wired; that pattern is the jq object-literal spelling the emitting `jq -n` actually uses.
The mod refuses no tool call, and its mission half declines one stop per typed request
through `classic.Stop`. The looser recipe this line
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

**`hooks/repeat-gate.sh` is in the repository and wired by neither path.** It is the shell
hook that learned failure signatures, bound recoveries and carried two refusals, the
repeat arm and the lesson gate, until 2026-10-03. Three things still use it.
`bin/skillrepeat` and `bin/skillreport` ask it for its head rules through `--eligible-of`
rather than keeping a second copy, each finding it by following its own symlinks back to
the checkout (`SKILLREPEAT_GATE` and `SKILLREPORT_GATE` override). `hooks/remind.sh`
carries a byte-for-byte copy of its command splitter, which
`tests/test_remind.py::SplitterSyncTest` pins. And `tests/test_repeat_gate.py` drives the
script directly. Its store, `<state>/repeats/`, no longer grows; `bin/skillrepeat` reads
it, `skillnote add --lesson <sig>` takes its signatures, and
`mod/compound/tools/sample_pairs.py` samples the judge's replay pairs from it. The
`REPEAT_*` knobs configure the script and, for `REPEAT_MIN_SESSIONS` and
`REPEAT_GATE_REFUSE`, the two CLIs. Its header and `docs/DESIGN.md` are the record of its
arms and of how each was arrived at. Whether to retire the script's remaining surface --
`bin/skillrepeat`, the `REPEAT_*` knobs, `tests/test_repeat_gate.py` -- is recorded as
undecided in `notes/2026-10-03-mod-exploration.md`.

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
compacts twice must not be keyed to one claim; `hooks/session-review.sh` claims with an atomic `mkdir` under
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
`compound-improvement.sh`
(twice), `claim-gate.sh` (twice), `skill-use.sh` (twice), `remind.sh` (twice),
`apply-gate.sh`, `doc-gate.sh`,
`insight-capture.sh` and `precompact.sh` -- twelve entries over eight scripts; grep either for
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

**history-surfer is a dependency, so install fetches it rather than assuming it.**
The mod's mission half reads that project's prompt store and keeps no copy of it, so install
clones `https://github.com/ContextLab/claude-history-surfer.git` into
`<app home>/../claude-history-surfer` -- a SIBLING of the managed checkout, which is what
keeps `--update` from touching it -- and runs its own
`scripts/setup.py --claude-dir <dir> --bin-dir <dir>`, recording `{url, home, sha,
installed}` under `surfer` in the manifest. A checkout already on the machine, at that
path or wherever a `surfer` on `PATH` resolves back to, is reused and not cloned again, and
what decides that there is nothing left to wire is history-surfer's own hook entries being
in the TARGET `settings.json`, never `shutil.which("surfer")`. It clones nothing when the
store already holds prompts (an installation this run cannot see, and a second copy is how
one store becomes two), or when `SKILL_COMPOUNDER_NO_SURFER` is set;
`SKILL_COMPOUNDER_SURFER_URL` and `SKILL_COMPOUNDER_SURFER_HOME` override the two
locations. It NEVER fails the install: offline, the step is one line in the report and
the mod falls back to the prompts the running process saw submitted. Uninstall leaves it
in place and prints how to remove it, on the same judgement as the state directory -- it
holds every prompt the user has ever typed at Claude Code, this package neither created
that data nor can put it back. The four rules are written out above `SURFER_URL` in
`skill_compounder/installer.py`.

`skillforge doctor` runs eleven checks: jq, state, settings, statusline, skills,
surfer, ledger, counters, forges, mission, review, in that order in the text form and the
`--json` form alike, so the two cannot report different counts. Two rows are about the
mod, and both turn on `mission_wired()`, which is true when `env.CLAUDE_CODE_PLUGIN_DIRS`
in `settings.json` has an element equal to or ending in `/mod/compound`.
`doctor_surfer` PASSes with the prompt count recorded for THIS project, WARNs when `surfer`
is not on `PATH` or `surfer stats` exits non-zero, with a clause saying whether the mod is
enabled and what it then falls back to, and FAILs only when `SKILLFORGE_SURFER_BIN` names
something that is not an executable file. `doctor_mission` WARNs when the mod is not
enabled, which is also what it reports when the repo is loaded as a plugin, since that
cannot be seen from `settings.json`. It WARNs when `<state>/mod/` does not exist, FAILs
when that directory will not accept a real write or when a line of `mission.jsonl` does
not parse, and otherwise PASSes with the delivery count and how many of five moments they
cover, folding `subagent` into `dispatch` and `compact` into `resume`.

**The ledger is append-only, and every reader selects its events BY NAME.** `start` and
its matching `done` or `fail` are joined into forges; `origin`, `use`, `verdict`,
`horizon`, `note` and `skill` (both written by `bin/skillnote`, the second by `skillnote
skill`) and `escalate` (written by `skillforge escalate`) are invisible to that join. The
forge join still ignores `skill`; since 2026-09-06 `bin/skillreport`'s skills view selects
it by name, so a skill built from a note without a forge is listed with the note id as its
trigger and `COVERAGE` carries a `skills from a note, no forge` line. Until then that view
answered `No skills recorded yet` over a ledger holding a `skill` row. A reader that classified by exclusion -- "anything
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
carries the four-tier decision, the builder/red-team forging protocol and the retirement
protocol. The tier rule comes first and it is a gate, not advice: a procedure earns a skill
only when it has steps a model gets wrong without them AND a trigger a description can route,
and otherwise it gets a note or a reminder from `bin/skillnote`. Since 2026-09-05 that rule
carries a second sentence, and it is the one that moved: a skill is ONE COMMAND by default
(`skillnote skill`), and a forge is owed only where the skill goes upstream or a real session
has shown its steps wrong. Ten days with one output path
produced zero notes, which is what a missing cheap branch looks like; the live ledger since
then reads 73 `note` rows against 12 forges, 7 of which ended in `fail`.
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
hooks/ bin/ statusline/ skill_compounder/ install.sh | sort -u` -- **156** names, over
**22** prefixes, re-run 2026-10-03; it was 157 before the installer's two retired markers
were renamed. `mod/` is outside those paths, so no `COMPOUND_*` name is in the count. A grep
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
for the wave that closed #43 and #32 and built #37's lineage id,
`2026-10-03-mod-exploration.md` for the live-state measurements of the shell lesson and
mission, the mod spike on 2.1.288 and the build that followed it, and
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
UNATTRIBUTED rather than dropped. Both blocks are functions, `print_funnel` and
`print_reminder_conversion`, and since 2026-09-06 the default view prints them on every
exit path, a ledger with no `start` row included; until then both sat past the `no forges
recorded yet` exit, so a machine that had only taken the cheap tiers was told nothing about
them. **`ACTED ON`, `OUTCOME` and `UNATTRIBUTED` are a
PARTITION of the ledger, and the block prints its own arithmetic on a `CHECK:` line rather
than asserting the property in prose** -- every `note`/`start`/`use`/`apply`/`verdict` row
is attributed to AT MOST ONE lineage, by the first of four tests that holds (its own `from`,
its own `candidate`, a `note` row whose own id is a delivered lineage, or the lineage
delivered FIRST to the session it was written in, counting only a delivery stamped AT OR
BEFORE the row's own `ts`, ties by id). A row earlier than every delivery to its session is
UNATTRIBUTED, because a nudge cannot have been acted on before it arrived; until 2026-09-06
the fourth clause read no timestamp and credited a note at ts 100 to a nudge delivered at
ts 200. It was not a partition twice over and both halves showed on the live store: a row whose `from` named a lineage no
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
- **2026-09-06** A block on skillreport's default view that is printed inline after an early exit goes missing on the exit path (APPLIED headline before #37, FUNNEL and REMINDER CONVERSION on a ledger with no start rows, 2026-09-06); a default-view block is a function called on every exit path, and its test drives the no-start-rows ledger. <!-- id:n559137653x332 -->
- **2026-10-03** claude -p with --allowedTools (variadic) swallows a trailing prompt argument and exits with 'Input must be provided'; pass the prompt on stdin: printf '%s' "<prompt>" | claude -p --allowedTools Bash. <!-- id:n445841543x207 source:session why:"2026-10-03: the first headless mod probe failed on it; mod/compound/tools/journey.py passes the task on stdin for this reason" -->
<!-- skillnote:end -->
