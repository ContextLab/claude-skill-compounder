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
Use it to check the harness before spending anything. Other flags: `--model` (default
`sonnet`), `--claude-timeout`, `--timeout`, and `--only 1,7,11` for debugging the harness
itself.

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
<out>/bin          a throwaway bin dir for the five CLIs
<out>/state        a throwaway state root: ledger, insights, reminders, forges
<out>/project      a scratch git project — the "problem" the journey is about
<out>/transcripts  this journey's own session transcripts, copied in for skillreport
<out>/logs         every command's argv, stdin, stdout, stderr, and every session stream
<out>/REPORT.md    one section per step: what ran, what was seen, PASS/FAIL/SKIPPED
```

The state root and the transcripts root are redirected with `SKILL_COMPOUNDER_STATE` and
`SKILL_COMPOUNDER_TRANSCRIPTS`, which every shipped script reads for exactly this
purpose. Nothing in the run can reach `~/.claude/skill-compounder`.

## Authentication, and the limit it puts on the whole scenario

The obvious isolation — point `CLAUDE_CONFIG_DIR` at `<out>/claude` — does not work.
`docs/CLAUDE-CODE-BEHAVIOR.md` records that a fresh config directory costs the run its
credentials, because on macOS the subscription credential lives in the Keychain and is
reached through the ambient environment. **Step 0 re-measures that rather than trusting
it**, and prints this machine's own answer into the report. Measured on 2026-09-02, CLI
2.1.259:

> `Not logged in · Please run /login`

So every later session takes the fallback path:

```
claude -p --model sonnet --max-turns <small>
         --setting-sources ''            # or `project` where the step needs the project
         --settings <out>/claude/settings.json
         --strict-mcp-config
         < the prompt on stdin
```

with `SKILL_COMPOUNDER_DISPATCHED=1` exported, `HOME` and `CLAUDE_CONFIG_DIR` untouched.
`--setting-sources ''` is what removes your hooks, skills, plugins and `CLAUDE.md`;
`--settings` is what puts the *throwaway* ones back. Three consequences, all of which the
report states plainly:

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

If you have a `CLAUDE_CODE_OAUTH_TOKEN`, the primary path becomes available and step 0
will say so; the fallback still proves a superset of what it would.

## What it does, step by step

| step | what it proves |
|-|-|
| 0 | the environment, and which authentication path this machine allows |
| 1 | a fresh install wires hooks, links every shipped skill and CLI, and `skillforge doctor` is clean — into a `settings.json` that already had an unrelated hook and status line |
| 2 | an ordinary session runs under the throwaway wiring, and the reminder and checkpoint hooks say **nothing** on a trivial prompt |
| 3 | a tier-0 note written by `skillnote` is answered from by a later session |
| 4 | a tier-1 reminder fires on a prompt keyword **and** a second one on a real `Bash` command |
| 5 | a `★ Skill candidate:` marker emitted by a session is captured into the queue |
| 6 | `skillinsight promote --to note` turns that candidate into a note and empties the queue |
| 7 | the forge CLI: `start --trigger`, two `round` rows, a third round refused with **exit 3**, `done` closing and installing, and the pending-apply debt it leaves |
| 8 | the forged skill routes — a `Skill` tool call in the stream, not a mention in prose |
| 9 | `skillforge apply` discharges the debt and `skillforge verdict` records the judgement |
| 10 | `skillreport` answers the five questions for that skill: trigger, built, applied, used, worked |
| 11 | uninstall restores `settings.json` **byte for byte** and leaves the runtime state intact |

## What it costs

Six `claude -p` calls: one authentication probe and five sessions (steps 2, 3, 4, 5, 8),
all `--model sonnet` with a small `--max-turns`. Two runs on 2026-09-02 against CLI
2.1.259 took **38.5 s** and **34.9 s** end to end, six calls each, twelve steps PASS both
times.

The forge step is the reason it is cheap. It drives the **CLI half only** — no builder
agents, no red-team agents, a hand-written 20-line `SKILL.md` — so step 7 takes about
a second against a 30-minute target, where a real forge is a median 3.3 hours and eight
agents. That is the deliberate trade in the next section.

## What it proves, and what it does not

**It proves** that the eleven pieces connect: that install is surgical and uninstall is
reversible against a `settings.json` that was not empty; that the hooks are wired and
quiet when they should be quiet and loud when they should be loud; that a note, a
reminder, a candidate, a promotion, a forge, a routing, an apply, a verdict and a report
are one continuous chain rather than eleven features that each work alone.

**It does not prove:**

- **That the forging protocol works.** Step 7 exercises the *ledger and cap mechanics*,
  not `skills/skill-compounder/SKILL.md`'s builder/red-team loop. A red-team round here
  is two integers on a command line. Nothing in this file says a forged skill is any
  good.
- **That the skill would route for anyone else.** Step 8 is **n = 1**: one prompt, one
  model tier, one CLI build, project scope, with a nonsense trigger token nothing can
  compete with. `scripts/routing_claims.py` and `tests/test_routing_claims.py::LiveProbeTest`
  are the instrument for the real question, at 72 calls.
- **Anything about a personal-scope skill roster**, for the credential reason above.
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
