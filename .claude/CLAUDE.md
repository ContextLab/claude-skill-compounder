# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code *configuration* package. It installs every skill under `skills/`, five CLIs,
a status-line wrapper, and twelve hook entries into `~/.claude/`. Those twelve span five
events (`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `Stop`) and
name seven of the eight scripts in `hooks/` -- every one but `session-review.sh`, which is
launched rather than wired; derive them from
`OUR_EVENT_MARKERS` in `skill_compounder/installer.py` rather than from this sentence.
There is no runtime service: the "program" is the
set of files the installer wires into someone else's Claude Code config.
`README.md` is the user-facing description. The two documents under `docs/` are split by
audience, and the split is load-bearing:

- `docs/CLAUDE-CODE-BEHAVIOR.md` is verified behavior of **Claude Code itself**, useful to
  a project that shares no code with this one. Every entry names the finding, how it was
  established by running something, and the CLI version where it was recorded. Add a
  platform finding there, not to `DESIGN.md`, and carry its measured limits with it.
- `docs/DESIGN.md` is the **local rationale**: why each piece of this package is shaped the
  way it is. It links to the platform file rather than restating a finding.

Read both before changing anything in `bin/`, `statusline/`, or `hooks/`. Several of the
constraints there look arbitrary. They are not. Nothing may live in both files: a moved
claim that reappears in `DESIGN.md` fails `tests/test_docs_split.py`.

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
**13** files, most of whose guards never fire. The `*.py` is load-bearing: over `tests/`
the answer depends on which grep you have, because `/usr/bin/grep` counts gitignored
`__pycache__/*.pyc` as source and the ugrep an agent shell gets does not.

Five CLIs ship in `bin/`, all shell + `jq`: `skillforge` (forge state, the ledger, and the
apply debt a closed forge leaves), `skillreport` (ledger joined against transcript
invocations), `skillinsight` (the candidate queue), `skillcontrib` (read-only contribution
reconnaissance), `skillrepeat` (the repeat gate's store of learned failure signatures).

## Architecture

**The animation is state-driven, not process-driven.** `bin/skillforge` writes a single
JSON file; `statusline/skillforge-status.sh` renders whatever it finds, once per second.
Nothing streams, which is what lets a forge animate across subagent dispatches.

**That file is deliberately not session-keyed**, and the two session ids are why. Do not
make it session-keyed without reading `docs/DESIGN.md` first. The reminder hook *does* key
per session, which is correct: it both reads and writes the payload's `.session_id`.

**Installation is marker-based and surgical.** `installer.py` identifies its own hook
entries by marker substring (`HOOK_MARKER`, `INSIGHT_MARKER`), and its status line by
`STATUSLINE_MARKER` -- a trailing `# claude-skill-compounder` shell comment it writes into
the command itself. Never a substring like `statusline.sh`, which also matches a user's own
`~/bin/git-statusline.sh`, and never the bare path, which stops matching the moment the
checkout moves; the three location-bound recognitions are kept only as fallbacks for
entries written before the marker. Install is idempotent and uninstall removes only our
entries. Other tools' hooks and an unrelated status line are left untouched. `settings.json`
is backed up before every write and written atomically, and *through* a symlink rather than
over it, so a dotfiles source is not orphaned; a malformed `settings.json` disables every
setting in it. Malformed shapes split by direction: install refuses and names the offending
key, uninstall never refuses. Read `docs/DESIGN.md` before changing either side of that.

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
`python3 -` calling `write_text` is caught, a runtime-assembled path is not. Undercounting
delays a checkpoint; counting `ls` teaches the user to ignore it. A second branch fires
`ai-tell-audit` once per durable-prose file per session, because that skill's description
names a README but nothing otherwise connects editing one to invoking it.

**`hooks/claim-gate.sh` is the only component here that refuses, and its evidence rule is
an exclusion.** It dispatches on `.hook_event_name` and takes no argv: on `Stop` it judges
`last_assistant_message`, on `PreToolUse` it judges a `git commit` message, and a figure of
`CLAIM_GATE_MIN_DIGITS` digits or more is unsupported unless it appears in what this
session's own tools printed. Tool results belonging to an `Agent` or `Task` call are cut out
of the evidence first, deliberately: a subagent's report is testimony, and relayed testimony
is what both founding defects were made of. The `PreToolUse` arm is not a nicety — a commit
message never reaches `last_assistant_message`, so the `Stop` arm alone cannot see the shape
of defect the gate was written for.

Two of its constants are worth knowing before touching either. `CLAIM_GATE_MAX_BYTES` is
`16777216`; it was `67108864` and that cap was **dead code on BSD**, because `wc -c < file`
prints a leading-space-padded count and the numeric `case` guard read the space as
non-numeric and zeroed the value. `tr -cd '0-9'` is the fix and the `case` stays as the
belt. And the header's calibration carries **two** false-positive rates, not one: 2.9% on
the corpus the rules were tuned against and 3.4% held out. Quote the held-out figure; the
tuned one was optimistic by roughly threefold, and the arm the tuned corpus recorded as
never firing was the arm carrying the difference.

**With both wirings active every hook fires twice**, so anything a hook counts, stamps,
appends to, or does once must survive being handed the same event twice. That includes
work a hook *launches* rather than does itself: `hooks/session-review.sh` is not wired to
either path, but it is started by `hooks/insight-capture.sh`, which is wired to both, so
one `Stop` starts it twice. Being detached buys it nothing.

The guard is idempotence keyed on something the payload already carries, and each script
spells it differently. `claim_once()` in `hooks/compound-improvement.sh` claims a
directory named for the payload's own `tool_use_id` or `prompt_id`, under the session and
the mode; `hooks/insight-capture.sh` claims on a hash derived from the session id; `hooks/session-review.sh` claims with an atomic `mkdir` under
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

**`hooks/session-review.sh` is a shipped component that spends money, and it is in
neither wiring.** `settings.json` and `hooks/hooks.json` between them name
`repeat-gate.sh` (three times), `compound-improvement.sh` (twice), `claim-gate.sh` (twice),
`skill-use.sh` (twice), `apply-gate.sh`, `doc-gate.sh` and
`insight-capture.sh` -- twelve entries over seven scripts; grep either for
`session-review` and you get nothing. It is launched by `insight-capture.sh` with `nohup`,
detached, never waited on, and only when that turn's session audit actually wrote a
record. Look for it there, not in a hooks list. Stage 1 is a single `claude -p` with no
tools at all -- `--disallowed-tools` over every built-in, `--strict-mcp-config`,
`--setting-sources ''` -- reading a bounded digest of the transcript and answering
`VERDICT: NONE` or `VERDICT: CANDIDATE <name>`.

Its gates all fail closed, and each reports through one `refuse` helper that prints a
single line to stderr — `/dev/null` in production — and exits on that gate's own code, so
a test asserts on the code rather than on prose. The gates run 10 through 20: off switch,
recursion, CI/test environment, a state root under a temp directory, no `claude` on
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

**The ledger is append-only, and every reader selects its events BY NAME.** `start` and
its matching `done` or `fail` are joined into forges; `origin`, `use`, `verdict` and
`horizon` are invisible to that join. A reader that classified by exclusion -- "anything
that is not a start is an outcome" -- would have folded every `use` row into the forge
count the day ledger v2 landed, so `tests/test_ledger_v2.py` pins both readers against a
mixed ledger. Add an event type freely; never widen a selector to a negation.

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
carries the builder/red-team forging protocol and the retirement protocol.
Its doctrine is mirrored in `README.md` and in the user's global `~/.claude/CLAUDE.md`
stanza. Changing the protocol means updating all three.

## Constraints specific to this repo

**No mocks, ever.** Every test writes real files, runs the real shell scripts through
`subprocess`, and reads results back off disk. Tests pin nondeterminism with environment
variables the scripts read for exactly that purpose. There are **nine clocks, not one** --
`SKILLFORGE_NOW` (`bin/skillforge`), `CI_NOW` (`hooks/compound-improvement.sh`),
`INSIGHT_NOW` (`hooks/insight-capture.sh` and `bin/skillinsight`, which fall back to
`CI_NOW`), `SKILL_COMPOUNDER_REVIEW_NOW` (`hooks/session-review.sh`),
`SKILL_COMPOUNDER_NOW` (the
installer's backup stamp), and one apiece for the three refusing gates and the store one
of them keeps -- `DOC_GATE_NOW` (`hooks/doc-gate.sh`), `REPEAT_GATE_NOW`
(`hooks/repeat-gate.sh`), `APPLY_GATE_NOW` (`hooks/apply-gate.sh`) and `SKILLREPEAT_NOW`
(`bin/skillrepeat`) -- and session-review refuses `CI_NOW` on purpose, because a
frozen `CI_NOW` makes its `|NOW - last|` cooldown zero forever and silences the trigger
permanently with nothing on any surface to say why. Two more redirect what a script reads
and writes, `SKILL_COMPOUNDER_STATE` and `SKILL_COMPOUNDER_TRANSCRIPTS`; two pin the ages
the status line expires on, `SKILLFORGE_DONE_TTL` and `SKILLFORGE_FAIL_TTL`; and one lifts
a refusal, `SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE`, without which `session-review.sh`
declines to spend money from any state root under a temp directory. One more is a real
threshold rather than a pin and reads differently for it: `SKILLFORGE_ACTIVE_TTL`
(`bin/skillforge`, 21600) is measured against **idle** time, since that forge's last
`step`, never against elapsed time, so `skillforge doctor` is the surface that says whether
anything here is working at all and `skillforge reap` is the only thing that unwedges a
forge whose orchestrator died -- by appending the `fail` row it never got, never by editing
the ledger (`SKILLFORGE_DOCTOR_JQ_VERSION` beside it is an ordinary pin, for the one
`doctor` branch a jq from 2015 would otherwise be needed to reach). A new script needs its
own clock: pinning someone else's does nothing to it. This list was derived by running
`grep -rhoE '\b(CI|INSIGHT|SKILLFORGE|SKILLUSE|SKILLREPEAT|STATUSLINE|SKILL_COMPOUNDER|CLAIM_GATE|DOC_GATE|REPEAT_GATE|REPEAT_MIN|REPEAT_RECOVERY|APPLY_GATE|APPLY_PENDING)_[A-Z0-9_]+'
hooks/ bin/ statusline/ skill_compounder/ | sort -u` and reading each hit; re-run it rather
than trusting the list if the two have drifted. **Twice now the command has been narrower
than the list it introduces**: it named three prefixes when seven were in use, and seven
when fourteen were, so on both occasions it could not produce the list it introduces. A
prefix added to a new script has to be added here too. If new behavior is hard to test without a mock, add a pin like
those instead. Tests run with a minimal `PATH` and `HOME` pointed at a
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
dispatches it, and not of the session that dispatched the orchestrator. This applies to the
protocol in `SKILL.md` and to any work in this repo that follows it. A forked reviewer
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
rounds (issue #22), and
`notes/research/` for the evidence behind the seed-pool selection, the
insight queue, and the contribution mechanics. `notes/OPEN-THREADS.md` is the one file
there that tracks current state rather than history. Read the dated ones for reasoning,
not for the current state of the code.

The two hook constants (12 edits, 20 minutes) are unvalidated. `bin/skillreport` is the
instrument that would settle them, and it needs real usage across several repositories
over real time. Do not tune them before that data exists. The skill's own threshold is
deliberately not a number — it asks for a nameable dead end and a second occurrence — so
there is nothing there to tune.
