# 🔁 claude-skill-compounder

**Make Claude Code get permanently better at the things you do repeatedly.**

![A fail-then-fix written down as a lesson, then a skill being forged under the two-round cap: the builder/red-team loop, with live progress in the status line](docs/media/forge.gif)

Knowledge that costs a session real effort to acquire dies with that session. You and
Claude work out a debugging sequence, a deploy-and-verify loop, or a non-obvious API
dance; the context window closes; next week a fresh session makes the same mistakes in the
same order.

`claude-skill-compounder` closes that loop. It installs the forging protocol as a skill,
a pool of seed skills that are useful on day one, hooks that keep asking the question, and
a live status-line animation.

Two of those hooks carry back the content a session lost.

**The mission** states your own requests back, verbatim, at five moments where a session
has most likely drifted from them: after a compaction or a resume, before it dispatches a
subagent or a workflow, once every twenty minutes of a long session, on a prompt too short
to stand on its own ("continue", "yes, do that"), and on a completion claim the turn has
not earned. It reaches the subagent as well as the thread that dispatched it, so an agent
working three levels down knows what you actually asked for. The prompts are read from
[claude-history-surfer](https://github.com/ContextLab/claude-history-surfer), which install
sets up for you; this package keeps no second copy of them.

**The lesson** watches for a tool call that failed and then worked, including when the fix
came from a different tool. The first time, it states the failure, the fix, and the one
command that records both. The second time that same signature comes round, it declines the
next call until the lesson is written down. A person can dismiss the signature instead; a
model cannot, and its dismissal is recorded rather than refused. Neither answer deletes
anything: both are rows.

All of it serves one principle:

> **Compound improvement.** When a procedure is *costly to get right* and *likely to
> recur*, stop re-deriving it and forge it into a reusable skill. Do it adversarially, so
> the skill actually works for a session that has none of your context.

---

## Status

What is built, what has been shown by running it, and what is still open. Each line carries
the command that re-derives it, because every one of these answers moves.

|Area|Where it stands|
|-|-|
|The package|Implemented and in use. There is no runtime service: what ships is the set of skills, hooks, CLIs and the status line that `install.sh` wires into `~/.claude/`. It wires **20 hook entries over 10 scripts and 8 events**; count them yourself with `jq '[.hooks\|to_entries[]\|.value[].hooks[]]\|length' hooks/hooks.json`|
|Releases|`v0.3.1` is the latest tag. The plain one-liner still takes `main`, so pin a ref to get the same code twice. `git ls-remote --tags https://github.com/ContextLab/claude-skill-compounder.git` lists what exists right now|
|CI|`.github/workflows/ci.yml` runs the suite on ubuntu and macos, `shellcheck` on both, and `claude plugin validate --strict`. All five jobs passed on run `33984720135` (2026-09-05), against `74b431a`, the tree that carries the day's production-run fixes, the lesson gate's final shape and the re-recorded screencast. Read the current one rather than this line: `gh run list --repo ContextLab/claude-skill-compounder --limit 1`|
|Dependencies|`jq` and `python3`, plus [claude-history-surfer](https://github.com/ContextLab/claude-history-surfer), which the mission hook reads its prompts from. Install fetches and wires it when `surfer` is not already on your `PATH`, never fails the install if it cannot, and uninstall leaves it where it is: [Install](#install)|
|End to end|`tests/e2e/journey.py` walks install, note, reminder, capture, forge, route, apply, report, three of the mission's five moments, the lesson's statement and the record that answers it, and uninstall against a throwaway config. Seventeen steps (`grep -c '^def step' tests/e2e/journey.py`); the run of 2026-09-05 against CLI 2.1.260 was thirteen `claude -p` calls in 130.5 s, every step PASS, on the tree that carries that day's hook changes. The six-call, twelve-step figure this row used to carry was the same scenario without the mission and lesson steps. Since 2026-09-05 it also takes `--config-dir fresh`, a throwaway `CLAUDE_CONFIG_DIR` that needs a token handed in through `CLAUDE_CODE_OAUTH_TOKEN`, and that mode has not yet been run with a real token. Run by hand, never in CI: [docs/e2e.md](docs/e2e.md)|
|Automatic session review|Ships **off**, and switching it on spends your quota: [What runs against the API](#what-runs-against-the-api). Stage 1 has been paid for six times. Stage 2, which would forge from a `CANDIDATE` verdict, is off for a structural reason rather than a price: a dispatched forge cannot finish its own routing gate, because `claude --version` inside one came back "This command requires approval" at the permission layer|
|Usage evidence|One machine. `skillreport` counts genuine reuse and reports probe and test traffic on a separate line, and on this repository that traffic is most of the total. What each figure is and is not evidence for: [docs/measurement.md](docs/measurement.md)|
|The two hook thresholds|`CI_EDIT_EVERY=12` and `CI_PROMPT_COOLDOWN=1200` were picked by judgement, and `skillreport` needs usage across several repositories before either should move|
|The mission and the lesson|Landed 2026-09-03, verified live against the installed package on 2026-09-05, and **every constant in both is unvalidated**, the two hook thresholds included: the mission's budget, its twenty-minute interval, its six-word ambiguity proxy and its eight-tool completion floor, and the lesson gate's two-token overlap. The lesson refusal has no expiry since 2026-09-05: three live red-team rounds showed the model taking every exit the deny text offered, so only a written lesson or a person's dismissal ends it. What each one counts, and why none of it is a result yet: [docs/measurement.md](docs/measurement.md)|
|The forge under the diet|Two real forges ran on 2026-09-05 and both closed with `fail` at the hard cap, on the same subsystem from two endpoints; the cap refused, granted and refused again exactly as written, and the candidate became a note with a script. `done`, `apply` and `verdict` on a successful diet forge remain unexercised: [docs/measurement.md](docs/measurement.md)|

Everything known and unresolved, including the parts with no issue open for them, is in
[`notes/OPEN-THREADS.md`](notes/OPEN-THREADS.md).

---

## Why

Skills are Claude Code's mechanism for durable capability, and two things stop them from
compounding on their own.

The first is that nothing notices the opportunity. Recognizing that a procedure is worth
crystallizing has to happen *during* the work, because the retrospective where it would
otherwise happen is a document nobody writes.

Then there is the skill itself. One written by the session that just solved the problem is
usually broken, because its author already knows the answer and quietly assumes context a
fresh session will not have. It names a script without saying which directory to run it
from. It skips the environment variable that was already exported three hours ago, and it
says "fix the error" about an error message that it alone recognizes. The skill reads fine
to the person who wrote it and fails six weeks later for everybody else.

This project addresses the first with hooks that keep asking the question, and the second
with an adversarial forging protocol built on one idea: **the original project is held-out
test data.** A skill written by the session that needed it is full of references only that
session can decode, so exactly one agent — the session itself — is allowed to see the
project, and it spends that privilege judging the result rather than writing it. A
**builder** writes the skill in a scratch directory with no path into the project. A
**separate, cold** red-teamer is handed the skill and nothing else, and has to work out
from the text alone what the skill is even for. Both run in the background, so none of that
traffic lands in the thread you are talking to, and the loop is capped at two rounds: a
third has to be earned from a falling count of blocking findings, and the CLI refuses it
otherwise.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh | bash
```

Pinned to a release, which is the form to prefer once a tag exists:

```bash
curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/v0.3.1/install.sh | SKILL_COMPOUNDER_REF=v0.3.1 bash
```

`v0.3.1` is the latest tag (v0.3.0 was cut on 2026-09-03 from `a2aa2d4`; v0.3.1 fixes
`install.sh --update` from the managed checkout's own copy);
`git ls-remote --tags https://github.com/ContextLab/claude-skill-compounder.git` lists the
tags that exist right now. With `SKILL_COMPOUNDER_REF` unset the installer takes `main`,
which is whatever was last pushed to it, so two people running the plain one-liner on the
same day can end up on different code. `--ref v0.3.1` is the flag form, and over the pipe
it needs `bash -s -- --ref v0.3.1`.

Or from a clone:

```bash
git clone https://github.com/ContextLab/claude-skill-compounder.git
cd claude-skill-compounder && ./install.sh
```

Requires `python3` (installer only), `jq` (hooks, CLIs, and status line), and
`~/.local/bin` on your `PATH` for the CLIs.

**It also installs one thing it did not write.** The mission hook states your own prompts
back, and the only place those exist as data is
[claude-history-surfer](https://github.com/ContextLab/claude-history-surfer), a sibling
project that records every prompt once per project as JSONL and searches it from a `surfer`
CLI. Keeping a second copy here would break the rule the whole package is built on, so it
is a dependency: when `surfer` is not already on your `PATH`, install
clones it beside its own checkout and runs its installer. Four things that follows from.
It never fails the install. No network, no `git`, a `python3` that errors, and you get one
line in the report and everything else wired as usual, with only the mission gone quiet.
It never clones twice, so a `surfer` you already have is left to be the one you have.
Uninstall never removes it, because it holds every prompt you have ever typed and this
package neither created that data nor can put it back; it prints where the checkout is and
the command that removes it. And `skillforge doctor` has a `surfer` row, which is where a
mission hook wired against a store that is not there stops being silent.
`SKILL_COMPOUNDER_NO_SURFER=1` on the install command declines all of it.

Hooks and skills are picked up **without restarting Claude Code**, though `/hooks` forces
a config reload if you want to be certain. Install also appends the three habits to
`~/.claude/CLAUDE.md`, between a pair of comments that render as nothing, and
`--no-doctrine` declines that:
[what the installer writes into your `CLAUDE.md`](docs/operations.md#what-the-installer-writes-into-your-claudemd).
The repo is also a valid Claude Code plugin, which gets you the skills and the hooks
without installing anything but not the forge animation:
[as a plugin](docs/architecture.md#as-a-plugin).

### Five-minute quickstart

Nothing has to be forged for any of this to pay for itself. The two cheap tiers cost one
command each, and one more command says whether the install took.

Write a lesson down where a later session will read it:

```bash
skillnote add --scope project "the suite is ./run_tests.sh, not pytest" \
  --why "pytest collects nothing here"
```

That appends a dated line to this project's `.claude/CLAUDE.md`, inside a
`skillnote:begin`/`skillnote:end` marker block, and writes a `note` row to the ledger.
`--scope global` puts it in `~/.claude/CLAUDE.md`; `--scope memory` writes a Claude Code
memory file plus the `MEMORY.md` index line that gets it read back.

A lesson that applies only at one moment is a reminder rather than a note. Give it the
words, the path or the command that should bring it back:

```bash
skillnote add --remind --scope project "run the migration before the seed script" \
  --keyword migration --command "python manage.py loaddata"
```

`hooks/remind.sh` states that back when your prompt carries the keyword, or when a `Bash`,
`Write` or `Edit` call matches the command signature. It denies nothing.
`skillnote list --scope remind` shows what is armed, and `skillnote remove <id>` disarms
one. Removing a lesson note withdraws the reminder written beside it as well, so neither
outlives the other; `--keep-reminder` leaves it armed.

When the lesson gate declines a call, it hands you the signature and the one command that
answers it. That command writes both cheap tiers at once:

```bash
skillnote add --lesson <sig> "gh needs --json headSha to find a run for a commit" \
  --attach scripts/watch-ci.sh
```

The dated line goes in the `CLAUDE.md` for the scope, the reminder is keyed on the failing
call's own signature so the fix arrives before that command runs again, and the ledger gets
one `note` row tying the two together. `--attach` copies the script or file beside the note
and links it from the line, which is the "and any associated code" half; it works without
`--lesson` too. `skillrepeat dismiss <sig> --why "..."` is the answer for a person who has
decided the signature needs no lesson, and it is **not** the other half of a pair: the
refusal names only the `skillnote` command, and a dismissal written from inside a session is
recorded and lifts nothing. Two of two model sessions handed the older refusal ran the
dismissal it printed with a reason they had invented, so the row now carries who wrote it.

A lesson that turns out to apply beyond one repository moves up a level:

```bash
skillnote promote <id> --to global
```

That takes the line, its attachments and its reminder to `~/.claude/CLAUDE.md` and leaves a
one-line tombstone behind. It is a move, never a copy, so there is still exactly one of it.

Then check the wiring:

```bash
skillforge doctor
```

Eleven checks, one line each, and exit 1 if any of them failed: `jq`, the state directory,
the hook entries in your `settings.json`, the status line marker, the skill and CLI
symlinks, `surfer`, the ledger, the counters, any forge left running, the mission's
delivery log, and which way the paid review is switched. Run it first whenever something
seems not to be firing. The `surfer` row is the one that turns a silent mission hook into a
`FAIL`: wired against a store that is not there, all five moments deliver nothing and
nothing else says so.

Forging is the expensive tier and it comes later, once a note has been rewritten often
enough to count as a recurrence:
[Three ways to compound](docs/architecture.md#three-ways-to-compound-note-reminder-skill).

### Supported versions

|What|What is supported|Where that comes from|
|-|-|-|
|Claude Code CLI|2.1.241 through 2.1.260|the range every entry in `docs/CLAUDE-CODE-BEHAVIOR.md` was measured against: `grep -ohE '2\.1\.2[0-9]+' docs/CLAUDE-CODE-BEHAVIOR.md \| sort -uV \| sed -n '1p;$p'`|
|`bash`|3.2 and newer|macOS ships 3.2 (`/bin/bash --version`), and the shell rules in `docs/DESIGN.md` are written against it. The ubuntu runner ships a much newer one; both print theirs in the `bash --version \| head -1` step of `.github/workflows/ci.yml`|
|`zsh`|parsed, not pinned|every shipped script must pass `zsh -n` as well as `bash -n`, on both runners, in that same step|
|`jq`|1.6 and newer|`skillforge doctor` fails below it and says why: `skillforge backfill` passes `--rawfile`, which jq did not have before 1.6|
|`python3`|3.9|what CI installs (`grep python-version .github/workflows/ci.yml`). The installer is the only thing here that uses it|
|macOS and Ubuntu|both|the CI matrix (`grep -m1 'os: \[' .github/workflows/ci.yml`)|

A tag is cut only once the suite is green on both of those operating systems and the
end-to-end journey has passed against a throwaway config:
[docs/e2e.md](docs/e2e.md). The rest of the release procedure is
[docs/releasing.md](docs/releasing.md).

### Updating and rolling back

The `curl` one-liner clones into `~/.claude/skill-compounder-app` and installs from there.
Re-running it **re-wires that checkout without moving it**. Moving it is a separate ask:

```bash
./install.sh --update                 # fetch and move to SKILL_COMPOUNDER_REF (default main)
./install.sh --update --ref v0.3.1    # or to a tag you name
./install.sh --rollback               # back to the ref recorded before that update
```

`--update` used to be implicit: a re-run ran `git pull --ff-only` on its way through, so
asking to repair a broken install could hand you a different version of the package than
the one that was broken. The two asks are now separate, and the reasoning is in
[docs/DESIGN.md](docs/DESIGN.md#an-install-pins-a-ref-and-updating-is-a-separate-ask).

`install.sh` writes the ref it checked out to `<state>/install-ref` along with the one
before it, and `--rollback` reads that. With no previous ref recorded it refuses and says
so rather than guessing. `SKILL_COMPOUNDER_UPDATE=1` is the environment form of `--update`,
for the `curl` pipeline where a flag needs `bash -s --`.

Those two are the ones you would set on purpose: `SKILL_COMPOUNDER_REF` (default `main`)
chooses the ref, and `SKILL_COMPOUNDER_UPDATE` (unset by default; `1` turns it on) asks for
the move. `install.sh` reads five distinct environment variables in all — run
`grep -nE '\$\{(SKILL_COMPOUNDER|CLAUDE_SKILL_COMPOUNDER)[A-Z_]*:-' install.sh` for the
current list, which prints six lines because `SKILL_COMPOUNDER_REF` is read twice. The other three redirect where it works rather than what it installs:
`SKILL_COMPOUNDER_REPO_URL` is the clone source (the GitHub repository by default, and what
`tests/test_install_sh.py` points at a local bare repository instead),
`CLAUDE_SKILL_COMPOUNDER_APP` is the managed checkout's location, and
`CLAUDE_SKILL_COMPOUNDER_STATE` is the state directory — the last spelled the same way
`uninstall.sh` spells it, because `curl … | bash` has no checkout around it and the two
scripts have to agree on where to look. All five are read at install time only, so none
belongs in the [Tuning](docs/operations.md#tuning) table or in `~/.claude/settings.json` — set
them on the command that runs the installer, or use `--ref` and `--update`.

All three manage only the checkout `install.sh` cloned. Run them from a clone you made
yourself and they refuse, naming the `git` commands to run instead: that checkout is
yours, and moving it would discard whatever you had in it.

---

## What runs against the API

**One part of this package can call the Anthropic API through your own `claude` CLI
and your own account, and it is off until you switch it on.** Everything else here is
shell and `jq` over files already on your disk, and runs either way. The advertised
install is a `curl | bash` one-liner, which is why: a command pasted from a web page
should not start spending your quota on its own.

That part is `hooks/session-review.sh`. It is not wired into `settings.json` as a hook:
`hooks/insight-capture.sh` starts it detached on `Stop`, and only when
`SKILL_COMPOUNDER_REVIEW` is set to exactly `1` and the session has crossed a
mechanical edit threshold — by default 24 file edits across 8 distinct files
(`INSIGHT_AUDIT_MIN_EDITS`, `INSIGHT_AUDIT_MIN_FILES`). It runs one `claude -p` with no
tools, no MCP servers and no settings sources, asks whether the session that just ended
repeated a procedure worth keeping, writes the answer under
`~/.claude/skill-compounder/reviews/`, and exits. The answer is `VERDICT: NONE` or
`VERDICT: CANDIDATE <name>`, and `NONE` is the expected one. It forges nothing and
installs nothing.

**What leaves the machine.** A digest of that one session's transcript: the last 4 MB of
the file (`SKILL_COMPOUNDER_REVIEW_TAIL_BYTES`), reduced to three kinds of line and then
cut to the last 60 KB of those (`SKILL_COMPOUNDER_REVIEW_DIGEST_BYTES`). For each `Edit`,
`Write` or `NotebookEdit`: the file path, the first 140 characters of the text replaced,
and the first 140 characters of the replacement. For each `Bash` call: the first 160
characters of the command. For each block of assistant text: its first 400 characters.
Only non-sidechain assistant records are read, so your own prompts are not copied in
directly, though assistant text can quote them. If the `Stop` hook wrote a session-audit
record, that goes too: session id, project directory, edit and file counts, and the list
of paths touched. Nothing else is read, and nothing goes anywhere but the API endpoint
your CLI already talks to.

**What it costs.** Two real runs on `sonnet` over a 60 KB digest: $0.19 in 60s, and
$0.222 in 80s (2026-08-25, CLI 2.1.245). Six dispatches have since accumulated on one
machine, median $0.17, range $0.042 to $0.222 (as of 2026-09-03). Once you have your own,
`skillinsight reviews --all` lists them with their prices, and this prints the same three
figures from the index those rows are read out of:

```bash
jq -s 'map(.cost_usd|tonumber)|sort|{n:length,min:.[0],max:.[-1],
        median:(if length%2==1 then .[length/2|floor]
                else (.[length/2-1]+.[length/2])/2 end)}' \
  ~/.claude/skill-compounder/reviews/index.jsonl
```

A global 21-hour cooldown bounds how often it
can happen at all — `604800 / 75600 = 8` dispatches in any seven-day window, so a ceiling
of $1.52 to $1.78 a week at those two prices. The edit threshold above was measured firing
on 18 of 126 real transcripts spanning 54 days on one machine, and the cooldown collapses
those to 13 distinct days: about 1.7 dispatches a week, or $0.32 to $0.38. Your own rate
depends on how you work. The dispatch is detached and the launch was measured at 3ms, so it adds nothing to
the wall clock of the session that triggers it.

**Switching it on.** The installer will do it, and prints the data boundary and the
measured median cost before it writes anything:

```bash
./install.sh --enable-review     # or: SKILL_COMPOUNDER_ENABLE_REVIEW=1 ./install.sh
./install.sh --disable-review    # and back off again
```

That writes `SKILL_COMPOUNDER_REVIEW=1` into the top-level `env` block of
`~/.claude/settings.json` and records in the install manifest that this package set
it, so `--disable-review` and uninstall only ever remove a value they wrote. A
`SKILL_COMPOUNDER_REVIEW` you set yourself is left alone and reported, the same
judgement install makes for a doctrine stanza you wrote by hand. Or set it by hand,
beside the hook entries, so both the hook that launches the review and the detached
script that runs it see it:

```json
{"env": {"SKILL_COMPOUNDER_REVIEW": "1"}}
```

Or export it in the shell you start `claude` from, which turns it on for that terminal
only:

```bash
export SKILL_COMPOUNDER_REVIEW=1
```

Only the literal `1` enables it: unset, empty, `true` and a typo all leave it off, and
the script refuses at its first gate — before it claims the session, takes its lock,
writes a cooldown stamp or reads a byte of any transcript. To turn it back off, set it
to `0` or delete the line. `skillforge doctor` prints which way it is set, since
nothing else surfaces the answer. For cheaper rather than off,
`SKILL_COMPOUNDER_REVIEW_MODEL=haiku` was measured at $0.099 against the same digest; it
is not the default because its answer paraphrased the evidence instead of quoting it, and
a `NONE` you cannot check is not much of a `NONE`.

|Variable|Default|What it changes|
|-|-|-|
|`SKILL_COMPOUNDER_REVIEW`|`0`|`1` opts in to the paid review; every other value stops the dispatch entirely, from either hook|
|`SKILL_COMPOUNDER_REVIEW_MODEL`|`sonnet`|Model the review runs on|
|`SKILL_COMPOUNDER_REVIEW_COOLDOWN`|`75600`|Seconds between any two dispatches, across all sessions|
|`SKILL_COMPOUNDER_REVIEW_FORGE`|`0`|`1` lets a `CANDIDATE` verdict go on to the forging protocol|
|`SKILL_COMPOUNDER_REVIEW_CLAUDE`|whatever `claude` resolves to on `PATH`|Which CLI to dispatch, when the hook's `PATH` does not carry one|

Set these in the top-level `env` block, for the same reason `SKILL_COMPOUNDER_STATE`
belongs there: both hooks and the dispatched script read them, and
`SKILL_COMPOUNDER_REVIEW` has a third reader in `skillforge doctor`, which is what
tells you which way it ended up set.

The second stage, which would take a `CANDIDATE` and run the full builder/red-team
protocol on it, is off. It was measured once end to end at $3.02 over 19 minutes, two cold
red-team rounds, verdict ABANDONED. Switched on, it writes into `reviews/staging/<name>/`
and never into `~/.claude/skills`, so a forge cannot reach your live config without your
having seen it.

`skillreport`, `skillinsight`, `skillforge`, `skillnote`, `skillrepeat`, the status line,
`hooks/mission.sh`, `hooks/repeat-gate.sh`, `hooks/compound-improvement.sh`,
`hooks/insight-capture.sh`, `hooks/skill-use.sh` and `hooks/claim-gate.sh` make no network
calls. `skillcontrib` reaches the network through `gh`, and every subcommand but one only
reads. The exception is `skillcontrib propose`, which forks, pushes and opens a pull
request: running it without `--dry-run` is the consent, and it prints every network write
on a `WRITE:` line before it makes it. See
[Contributing a skill back](docs/operations.md#contributing-a-skill-back).

Install is the other thing that reaches the network, to clone this repository and, unless
`SKILL_COMPOUNDER_NO_SURFER=1`, `claude-history-surfer` beside it.

---

## How it fits together

Three tiers of durable lesson, and the machinery that feeds them. A **note** is a dated
line in a `CLAUDE.md` or a memory file. A **reminder** is a match rule that a hook states
back at the moment it applies. A **skill** is the expensive tier, forged through a
builder/red-team loop and installed into `~/.claude/skills/`. `skillnote` writes the first
two in one command each, or both at once with `--lesson`; `skillforge` drives the third.
Nine seed skills ship, so a fresh install is useful before you have forged anything. A
lesson moves up a level with `skillnote promote`, and a skill goes the last level with
`skillcontrib propose`, which opens the pull request.

The ten wired scripts divide into three kinds. Three carry something into the session and
can be read past: the checkpoint that asks whether a skill already covers this, the
reminder hook, and four of the mission's five moments. Five can refuse: the claim gate and
the documentation gate outright, the apply gate once per session, the lesson gate on every
tool until the lesson is written down, and the mission once per prompt on a completion claim. The repeat
gate's older arm can too, and ships off. Three only record: a ledger row per skill
invocation, and a queue row per candidate, written at the end of a session and again from
whatever a compaction is about to discard.

|Where to look|What is there|
|-|-|
|[docs/architecture.md](docs/architecture.md)|What gets installed, the seed pool, the mission, the lesson, the three levels a lesson can live at, the forging protocol and the doctrine it is pinned to, the claim gate, the status line, and what the ledger records|
|[docs/operations.md](docs/operations.md)|`skillforge doctor` and `reap`, the weekly candidate queue, the state directory and how to recover it, proposing a skill upstream, and the tuning table with every knob, its default and which component reads it|
|[docs/measurement.md](docs/measurement.md)|What is counted, what each block of `skillreport` prints, and the limits on every figure here|
|[docs/development.md](docs/development.md)|The suite, the rules it is written under, the end-to-end journey, and releasing|
|[docs/DESIGN.md](docs/DESIGN.md)|Why each piece of this package is shaped the way it is|
|[docs/CLAUDE-CODE-BEHAVIOR.md](docs/CLAUDE-CODE-BEHAVIOR.md)|Verified behavior of Claude Code itself, written for anyone building on it and not only for this package|

---

## Uninstall

```bash
./uninstall.sh
# or:  curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/uninstall.sh | bash
```

Removes our hooks, leaving other tools' hooks alone, then restores your original status
line and removes the symlinks. Runtime state is left intact; delete it with
`rm -rf ~/.claude/skill-compounder`.

`claude-history-surfer` is left in place too, and for the stronger version of the same
reason: its store is your prompt history, which this package did not create. Uninstall
prints the checkout it made and the command that takes it off.

The `curl` form works whichever way you installed: with no checkout beside it, the script
reads `~/.claude/skill-compounder/install-manifest.json` to find the one you used. If that
checkout has been deleted, clone the repo and run `./uninstall.sh` from the clone — the
manifest still identifies the links the old checkout made, so they are removed rather than
disowned.

---

## License

MIT. See [LICENSE](LICENSE).
