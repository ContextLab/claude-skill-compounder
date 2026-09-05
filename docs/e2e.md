# The end-to-end journey

`tests/e2e/journey.py` walks the whole loop this package exists for — install, use,
notice, forge, route, apply, report, uninstall — once, by hand, against a throwaway
Claude config and state directory, and writes down what it *saw* at each step.

It is not part of the test suite and it must never run in CI. It spends real `claude -p`
calls on your own subscription.

```bash
python3 tests/e2e/journey.py --out /tmp/journey-$(date +%Y%m%d-%H%M%S)
```

`--out` must be a fresh or empty directory. When it finishes it prints the path of
`REPORT.md`, which is the artifact; the exit status is secondary and the report says why.

```bash
python3 tests/e2e/journey.py --out /tmp/dry --no-model   # spends nothing
```

`--no-model` runs every step that needs no model call and records the rest `SKIPPED`.
Use it to check the harness before spending anything.

```bash
claude setup-token                                       # once, prints a token
export CLAUDE_CODE_OAUTH_TOKEN=...                       # the token it printed
python3 tests/e2e/journey.py --check-auth --config-dir fresh          # one call
python3 tests/e2e/journey.py --out /tmp/fresh --config-dir fresh      # thirteen
```

`--config-dir fresh` runs every session under a throwaway `CLAUDE_CONFIG_DIR` instead of
under yours, which needs a credential in the environment; the section below says what it
changes and what it costs. `--check-auth` spends one call on the question and prints the
CLI's own answer. Other flags: `--model` (default `sonnet`), `--claude-timeout`,
`--timeout`, and `--only 1,7,11` for debugging the harness itself.

## Why it is a script and not a test

`run_tests.sh` loops over `tests/test_*.py`, so a file named `journey.py` inside
`tests/e2e/` is picked up by neither that glob nor a recursive one, and nothing imports
it. That is deliberate and it is the whole reason for the directory: a scenario that
spends money must be impossible to trip over.

Everything else in `tests/` asserts one script against files on disk. Nothing there
asserts that a person who clones this repo, installs it and works for an afternoon gets
the loop the README describes. Twelve green unit files and a broken journey is a state
this repo could reach without noticing, and this is the instrument that would notice.

## What it builds

```
<out>/claude       a throwaway CLAUDE dir: settings.json, skills/, CLAUDE.md
<out>/bin          a throwaway bin dir for the six CLIs, and `surfer`
<out>/state        a throwaway state root: ledger, insights, reminders, forges
<out>/project      a scratch git project — the "problem" the journey is about
<out>/transcripts  this journey's own session transcripts, copied in for skillreport
<out>/surfer-store history-surfer's captured prompts, for the mission hook to read
<out>/logs         every command's argv, stdin, stdout, stderr, and every session stream
<out>/REPORT.md    one section per step: what ran, what was seen, PASS/FAIL/SKIPPED
```

The state root and the transcripts root are redirected with `SKILL_COMPOUNDER_STATE` and
`SKILL_COMPOUNDER_TRANSCRIPTS`, which every shipped script reads for exactly this
purpose. Nothing in the run can reach `~/.claude/skill-compounder`.

## The dependency the mission steps need

`hooks/mission.sh` states the user's own prompts back to a session, and it keeps no copy
of them: it reads history-surfer's store. So steps 12-14 need history-surfer wired into
the *throwaway* config, and two things have to be arranged for that.

**The installer's dependency step decides on the target config, not on PATH.** An
operator who already has history-surfer on this machine still gets its two hook entries
written into `<out>/claude/settings.json`, from the checkout that `surfer` resolves into,
with nothing cloned. That was the journey's first finding: the step used to short-circuit
on `shutil.which("surfer")` and the throwaway install came out with the mission hook
inert, and the journey pruned `surfer` from the installer's PATH to get around it. The
installer now reads the target `settings.json` for history-surfer's own markers, so the
workaround is gone and step 1 installs on the real PATH. If a checkout has to be cloned
from GitHub and the machine is offline, the installer says so in one line and the install
still succeeds; steps 12-14 then FAIL carrying that line, rather than reporting silence as
a pass.

**Both ends of the store meet at a non-default `--claude-dir` on their own.** history-surfer
derives its data directory from the claude dir it was installed with, so a throwaway install
writes to `<out>/claude/history-surfer`; `hooks/mission.sh` now resolves its store root in
the same order, `MISSION_SURFER_ROOT`, then `CLAUDE_HISTORY_SURFER_DIR`, then
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/history-surfer`, which was the journey's second
finding (it used to be the literal `$HOME/.claude/history-surfer`, and the two did not
meet). Every captured prompt stays inside `<out>`.

**And uninstall is two commands, in the order the first one prints.** Our uninstall
removes only the entries we wrote, so history-surfer's `UserPromptSubmit` and `Stop`
entries survive it and `settings.json` is not yet byte-identical. That is deliberate: the
`surfer` line of the uninstall report names the checkout, says the prompt history is not
ours to delete, and prints the exact `--uninstall` command that removes the entries. Step
11 runs that second command and only then compares, so **byte for byte** stays a claim
about the pair rather than one quietly narrowed to one of them.

## Authentication, and the two `--config-dir` modes

`--config-dir` decides where a session's credential comes from, and that decides how much
of the run is isolated.

### `--config-dir ambient`, the default

`HOME` and `CLAUDE_CONFIG_DIR` are left alone and the configuration is swapped one call at
a time:

```
claude -p --model sonnet --max-turns <small>
         --setting-sources ''            # or `project` where the step needs the project
         --settings <out>/claude/settings.json
         --strict-mcp-config
         < the prompt on stdin
```

with `SKILL_COMPOUNDER_DISPATCHED=1` exported. `--setting-sources ''` removes your hooks,
skills, plugins and `CLAUDE.md`; `--settings` puts the *throwaway* ones back.

The reason this mode exists is that a throwaway `CLAUDE_CONFIG_DIR` holds no login: on
macOS the subscription credential is in the Keychain, reached through the ambient
environment, which `docs/CLAUDE-CODE-BEHAVIOR.md` records. **Step 0 re-measures that rather
than trusting it** and prints this machine's own answer into the report. Measured
2026-09-02 on CLI 2.1.259 and again 2026-09-03 and 2026-09-04 on CLI 2.1.260:

> `Not logged in · Please run /login`

Three consequences follow, all of which the report states plainly:

1. **Sessions run on your ambient credentials.** The run is isolated in configuration,
   not in identity.
2. **Claude Code writes their transcripts into the real
   `~/.claude/projects/<slug-of-scratch-project>/`.** That is the one place outside
   `<out>` the run leaves anything. The journey copies its own transcripts into
   `<out>/transcripts` and points `SKILL_COMPOUNDER_TRANSCRIPTS` there, so `skillreport`
   reads the journey's sessions and no others.
3. **The throwaway *personal* skills directory is on no session's roster**, because only
   `CLAUDE_CONFIG_DIR` would put it there. Step 7 still installs the forged skill into it
   — that path is exercised — but step 8 measures routing at **project** scope, from the
   scratch project's `.claude/skills/`.

### `--config-dir fresh`, which needs a token handed in

This is the isolation
[issue #42](https://github.com/ContextLab/claude-skill-compounder/issues/42) asks for.
`CLAUDE_CONFIG_DIR` points at `<out>/claude` for every process the journey starts, no
`--settings` and no `--setting-sources` flag is passed to any session, and the credential
arrives in the environment instead of from the Keychain:

```bash
claude setup-token
export CLAUDE_CODE_OAUTH_TOKEN=...
python3 tests/e2e/journey.py --check-auth --config-dir fresh
python3 tests/e2e/journey.py --out /tmp/fresh-journey --config-dir fresh
```

`claude setup-token --help` on 2.1.260 prints `Set up a long-lived authentication token
(requires Claude subscription)` and takes no options but `-h`. Without
`CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` in the environment the harness refuses
before it builds anything or spends anything:

```
error: --config-dir fresh needs a credential in the environment and found neither
CLAUDE_CODE_OAUTH_TOKEN nor ANTHROPIC_API_KEY: run `claude setup-token` and export the
result as CLAUDE_CODE_OAUTH_TOKEN (or set ANTHROPIC_API_KEY), because a throwaway
CLAUDE_CONFIG_DIR has no stored login and answers `Not logged in · Please run /login`.
```

(one line on the terminal; wrapped here)

The value is never printed, logged or written into the report; the report names the
variable and nothing else.

**That a fresh config directory consults those two variables at all was measured, with
deliberately invalid values, so no real credential was involved.** Each probe was
`CLAUDE_CONFIG_DIR=$(mktemp -d) claude -p --model sonnet --max-turns 1 --setting-sources ''
--strict-mcp-config`, on CLI 2.1.260, 2026-09-04, and each answer came back on stdout with
an empty stderr and an exit status of 1:

| in the environment | what the CLI answered |
|-|-|
| neither variable | `Not logged in · Please run /login` |
| `CLAUDE_CODE_OAUTH_TOKEN=invalid-for-probe` | `Failed to authenticate. API Error: 401 Invalid bearer token` |
| `ANTHROPIC_API_KEY=invalid-for-probe` | `Invalid API key · Fix external API key` |

Both variables are consulted, so either one can carry a real credential into a fresh
config directory. One exit status covers all three answers, which is why step 0 and every
`claude` call in the harness judge on the string and never on the status.

**What the mode is designed to remove, and what has actually been checked.** All three
consequences above are what it targets: the identity is the handed-in token rather than
your Keychain (1), Claude Code writes the transcripts under `<out>/claude/projects/`
because that follows `CLAUDE_CONFIG_DIR`, and the journey reads them from there (2), and
step 8 measures routing from the throwaway **personal** roster with no copy into the
scratch project, which is the one measurement the mode changes (3).

**None of that has been observed. As of 2026-09-04 no run has been made with a real
token**, because no scoped credential has been handed in on this machine and reading the
stored one is out of bounds. What has been run is the harness around it: the refusal above
exits 2 and builds nothing; `--config-dir fresh --no-model` reaches the same five
non-model steps `PASS` that the default mode does; and a deliberately invalid
`CLAUDE_CODE_OAUTH_TOKEN` makes step 0 `FAIL` with the CLI's answer quoted and records the
other sixteen steps `SKIPPED` after one call, rather than spending twelve more to be told
the same thing. Whether the three consequences are gone is a question for the first run
with a working token, and issue #42 stays open until then.

## What it does, step by step

Seventeen steps, and they **run in the order `STEPS` lists, not in number order**. Steps
12-16 were added after 11 was numbered and this page cites the numbers, so the numbers
stayed where they were and the run order is 0-10, 12-16, 11: step 11 tears the install
down, and everything that needs the wiring has to happen before it.

| step | what it proves |
|-|-|
| 0 | the environment, and which authentication path this machine allows |
| 1 | a fresh install wires hooks, links every shipped skill and CLI, installs history-surfer, and `skillforge doctor` is clean — into a `settings.json` that already had an unrelated hook and status line |
| 2 | an ordinary session runs under the throwaway wiring, and the reminder and checkpoint hooks say **nothing** on a trivial prompt |
| 3 | a tier-0 note written by `skillnote` is answered from by a later session |
| 4 | a tier-1 reminder fires on a prompt keyword **and** a second one on a real `Bash` command |
| 5 | a `★ Skill candidate:` marker emitted by a session is captured into the queue |
| 6 | `skillinsight promote --to note` turns that candidate into a note and empties the queue |
| 7 | the forge CLI: `start --trigger`, two `round` rows, a third round refused with **exit 3**, `done` closing and installing, and the pending-apply debt it leaves |
| 8 | the forged skill routes — a `Skill` tool call in the stream, not a mention in prose; at project scope by default, at personal scope under `--config-dir fresh` |
| 9 | `skillforge apply` discharges the debt and `skillforge verdict` records the judgement |
| 10 | `skillreport` answers the five questions for that skill: trigger, built, applied, used, worked |
| 12 | the mission survives a compaction: a session says a distinctive phrase, `/compact` replaces its context, and the resumed session quotes the phrase back with a `moment:"resume"` row in `<state>/mission/hits.jsonl` behind it |
| 13 | the mission reaches a **subagent** that was told nothing: a `moment:"subagent"` row with a non-null `agent_id`, and the injection itself in the subagent's own transcript |
| 14 | the mission is stated **once** at a completion claim: the session claims "done" after `MISSION_STOP_MIN_TOOLS` tool calls, the stream carries another assistant turn after it, and exactly one `moment:"completion"` row |
| 15 | a failed `Bash` call and the corrected one are bound as a recovery, and the session is handed the statement naming `skillnote add --lesson` |
| 16 | `skillnote add --lesson … --attach` writes the note line, the reminder row and the ledger row at once, and the next session's failing command gets the reminder |
| 11 | uninstall restores `settings.json` **byte for byte** and leaves the runtime state intact |

## What it costs

Thirteen `claude -p` calls in either mode: one authentication probe and twelve sessions —
steps 2, 3, 4, 5 and 8 one apiece, step 12 three (open, `/compact`, resume), and steps 13,
14, 15 and 16 one apiece — all `--model sonnet` with a small `--max-turns`. `--check-auth`
is one call and no journey, which is what it is for: under `--config-dir fresh` a stale
token would otherwise be found by step 0 and cost the twelve after it nothing but time. One run on 2026-09-03
against CLI 2.1.259 took **150.9 s**, thirteen calls, seventeen steps PASS. The six-call,
twelve-step shape this file described before is the same scenario without steps 12-16; two
runs of it on 2026-09-02 took 38.5 s and 34.9 s.

The forge step is the reason it is cheap. It drives the **CLI half only** — no builder
agents, no red-team agents, a hand-written 20-line `SKILL.md` — so step 7 takes about
a second against a 30-minute target, where a real forge is a median 3.3 hours and eight
agents. That is the deliberate trade in the next section.

`MISSION_STOP_MIN_TOOLS` is turned down to 2 for step 14's call alone. The shipped default
is 8, and eight tool calls to reach one Stop is seven of them spent on nothing; the arm
under test is the same one at either setting, and the hook reads the knob from the
environment for exactly this.

## What it proves, and what it does not

**It proves** that the pieces connect: that install is surgical and uninstall is
reversible against a `settings.json` that was not empty; that the hooks are wired and
quiet when they should be quiet and loud when they should be loud; that a note, a
reminder, a candidate, a promotion, a forge, a routing, an apply, a verdict and a report
are one continuous chain rather than a set of features that each work alone. Steps 12-14
add that the mission arrives at three moments a session cannot fake — after a compaction,
inside a subagent, at a completion claim — and 15-16 that a failure, its recovery, the
lesson written from it and the reminder that states it back are one chain too.

**It does not prove:**

- **That the forging protocol works.** Step 7 exercises the *ledger and cap mechanics*,
  not `skills/skill-compounder/SKILL.md`'s builder/red-team loop. A red-team round here
  is two integers on a command line. Nothing in this file says a forged skill is any
  good.
- **That the skill would route for anyone else.** Step 8 is **n = 1**: one prompt, one
  model tier, one CLI build, project scope, with a nonsense trigger token nothing can
  compete with. `scripts/routing_claims.py` and `tests/test_routing_claims.py::LiveProbeTest`
  are the instrument for the real question, at 72 calls.
- **Anything about a personal-scope skill roster**, in the default mode, for the
  credential reason above. `--config-dir fresh` is built to measure it and has not been
  run with a real token, so nothing has been proved about it either way.
- **That a subagent ACTS on the mission it is handed.** Step 13 measures arrival, in the
  subagent's own transcript, because arrival is the part this package controls. On both runs
  so far, and again in the live red-team of 2026-09-04, the subagent was handed the mission
  and still answered `NOT KNOWN` when asked what the user was working on. That is now three
  independent observations of the same thing, so read it as the expected outcome rather than
  as a flake: delivery is necessary and it is demonstrably not sufficient. The hook's own
  header records the same class of result from the other direction — imperative wording
  refused as prompt injection in 2 of 4 runs — and a statement of fact can be read and set
  aside just as easily.
- **That the recovery arm binds a failure to its fix in general.** Step 15 tells the
  session to run the two commands one at a time, and the prompt says so because it has to:
  issued as parallel tool calls in one assistant message, the success came back before the
  failure and nothing bound. `hooks/repeat-gate.sh` arms on a failure and binds a later
  success, so a recovery that arrives first is not one.
- **That the `Stop` block is free.** It costs one empty assistant turn: the blocked turn
  comes back carrying `Your previous response had no visible output`, and only then does the
  session act on the mission it was handed as the block's reason. Step 14 asserts that
  another assistant turn follows the block, so the cost is inside what the step already
  measures — but it is a real turn spent, and the arm is budgeted at one block per
  `prompt_id` partly because of it.
- **Anything statistical.** Every step is one observation. A PASS here means it happened
  once, in this environment, on this build — which is exactly what the report's quoted
  lines let you check.

## Reading the report

Every step carries the command that ran, the output it produced, and a **decisive line**:
one quoted string that the verdict rests on. A step is never PASS because something
exited zero. A step the environment could not run is `SKIPPED` with the reason, never
silently dropped.

The report also records the repo's `HEAD` at the start and at the end of the run. If they
differ, someone edited the checkout mid-run — every hook here executes by absolute path
out of it, so a run that straddles a commit is a run whose result is worth re-taking.
