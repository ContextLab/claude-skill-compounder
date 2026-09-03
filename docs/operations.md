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

`skillforge doctor` is the health check for everything else: jq, the state directory, the
settings entries, the status line, the skill links, the ledger, the reminder counters and
the open forges. Every hook here opens with `command -v jq || exit 0`, so a missing jq or
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
tails the transcript, runs the same extractor, appends, and exits. Against a 5 MB
transcript it medians 27.4 ms when it finds nothing and 86.3 ms when it queues a
candidate, over 15 runs on macOS 25.6.0 with `/usr/bin/jq`; on a `PATH` that resolves `jq`
to a slower build those become 62.4 ms and 147.9 ms, because what it spends is process
starts rather than bytes. Nothing writes `CLAUDE.md` from a hook — that is `skillinsight
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
skillinsight promote <hash> --to note|reminder   # write it down now instead of forging it
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

Nothing here auto-forges. The queue feeds the same threshold as everything else.

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
  and `reminders/` the per-session edit and prompt counters the checkpoint hook keeps.
- `repeats/` holds the repeat gate's learned failure signatures; `claim-gate/`,
  `doc-gate/`, `apply-gate/` and `apply-pending/` hold each gate's per-session budget and
  the debt a closed forge leaves behind.

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
more than a proposal. The `contribute-skill` skill proposes it upstream:

```
skillcontrib preflight skills/<name>                  # frontmatter parses, name matches the directory
skillcontrib dedup <name> --repo <owner/repo>         # every PR in any state, not just open ones
skillcontrib whoami --repo <owner/repo>               # maintainers branch directly, others fork
```

`--repo` defaults to `ContextLab/claude-skill-compounder`, which is almost never the repo
you mean: aimed at the wrong tree, the duplicate check answers "clean" for free. Pass it.

The duplicate check reads open, closed, **and** merged pull requests. A hit on a
closed-unmerged PR blocks resubmission and needs an explicit override, because a rejected
proposal is a signal rather than noise to route around. `skillcontrib` itself never
writes anything to the network; every push happens in the skill, behind consent gates that
show you the identity, the dedup result, the diff, and the filled-in pull request body with
the exact `gh pr create` command that would open it, before anything leaves your machine.
Not `--dry-run`: its own help says it "May still push git changes", so it is not a read-only
preview and the skill forbids it there.

The bar is both a clean red-team result and evidence of local reuse. See
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Tuning

Noisy reminders are a tuning problem. The knobs worth setting are in the table below; the
automatic session review has its own, in
[What runs against the API](../README.md#what-runs-against-the-api).
All thirty-four are environment variables, and they are not the whole set — this
prints every name the hooks, the six CLIs, the status line and `install.sh` read, 112 of
them as of 2026-09-03 (`uninstall.sh` and `scripts/` are outside it):

```bash
grep -ohE '\b(CI|CLAUDE_SKILL_COMPOUNDER|INSIGHT|SKILLFORGE|SKILLNOTE|SKILLUSE|SKILLREPEAT|SKILLREPORT|STATUSLINE|SKILL_COMPOUNDER|CLAIM_GATE|DOC_GATE|REPEAT_GATE|REPEAT_MIN|REPEAT_RECOVERY|REMIND|PRECOMPACT|APPLY_GATE|APPLY_PENDING)(_[A-Z0-9_]+)?\b' \
  hooks/*.sh bin/* statusline/*.sh install.sh | sort -u
```

`install.sh` is in that list and its four names are the exception to everything below it.
`SKILL_COMPOUNDER_REF`, `SKILL_COMPOUNDER_UPDATE`, `CLAUDE_SKILL_COMPOUNDER_APP` (where
the managed checkout goes) and `CLAUDE_SKILL_COMPOUNDER_STATE` (where the state directory
goes; `uninstall.sh` reads the same two) are read at **install time**, before any of this
is wired up — so none has a row in the table and none has any place in
`~/.claude/settings.json`, where setting them does nothing. Set them on the command that
runs the installer. The first two are documented where they are used, under
[Updating and rolling back](../README.md#updating-and-rolling-back).

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
|`CI_EDIT_EVERY`|`12`|the hook entries|Edits between "is this worth crystallizing?" checkpoints|
|`CI_PROMPT_COOLDOWN`|`1200`|the hook entries|Seconds between "does a skill exist?" reminders|
|`CI_PROMPT_MIN_CHARS`|`60`|the hook entries|Shorter prompts never trigger a reminder|
|`CI_CLAIM_TTL_MIN`|`60`|the hook entries|Minutes before a stale double-fire claim is pruned|
|`CI_PRUNE_EVERY`|`25`|the hook entries|Hook invocations between sweeps of expired claims|
|`CI_QUEUE_NUDGE`|`1`|the hook entries|Set to `0` to stop announcing the pending skill-candidate queue|
|`CI_QUEUE_NUDGE_MIN`|`259200`|the hook entries|Seconds that must pass before the queue may be announced again|
|`CI_QUEUE_NUDGE_MAX`|`1209600`|the hook entries|Seconds after which an unchanged queue is announced anyway|
|`SKILL_COMPOUNDER_USE_LOG`|`1`|the hook entries|Set to `0` to stop recording skill invocations in the ledger|
|`CLAIM_GATE`|`1`|the hook entries|Set to `0` to switch the end-of-turn claim gate off entirely|
|`CLAIM_GATE_COMMIT`|`1`|the hook entries|Set to `0` to keep the gate on the closing message but stop it denying a `git commit`|
|`CLAIM_GATE_MIN_DIGITS`|`3`|the hook entries|Smallest integer width the gate will flag as an unsupported figure|
|`CLAIM_GATE_MAX_SESSION`|`10`|the hook entries|Blocks plus denials the gate may spend in one session|
|`SKILL_COMPOUNDER_REPEAT_GATE`|`1`|the hook entries|Set to `0` to switch the repeat gate off entirely — it denies nothing and learns nothing|
|`REPEAT_GATE_REFUSE`|`0`|the top-level `env` block|Set to `1` to arm the refusal. Off by default: across 81 recorded sessions it refused nothing, and every signature that reached the threshold was one the gate's own head rules exempt anyway ([#27](https://github.com/ContextLab/claude-skill-compounder/issues/27)). Learning and recovery are unaffected either way. **Two components read it** — the gate, and `bin/skillrepeat`, which says on its own output whether the arm is armed|
|`REPEAT_MIN_SESSIONS`|`2`|the top-level `env` block|Earlier sessions a call must have failed in, the same way, before the next attempt is denied. **Three components read it** — set it anywhere narrower and they disagree|
|`REPEAT_RECOVERY_WINDOW`|`5`|the hook entries|Successful `Bash`/`Skill` calls — the only ones this hook is delivered — after which an armed failure stops looking for the call that fixed it|
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
|`REMIND_MAX_ROWS`|`2000`|the hook entries|Lines read from the tail of the reminder store and of the hit log|
|`STATUSLINE_BASE_TTL`|`5`|the `statusLine` entry|Seconds your base status line is cached|
|`SKILLFORGE_IDLE_SECS`|`2700`|the top-level `env` block|Age past which a forge nothing has stepped is called idle. **Two components read it** — the status line and `skillforge list` — so setting it anywhere narrower makes them disagree about whether a forge is dead|
|`SKILLFORGE_ACTIVE_TTL`|`21600`|the top-level `env` block|Seconds of **idle** time, measured since the last `step`, past which an `active` forge is presumed dead: `skillforge doctor` says WARN, `skillforge reap` writes it the `fail` row it never got, and `start` on that name reaps it rather than refusing|
|`STATUSLINE_CACHE_PRUNE_EVERY`|`200`|the `statusLine` entry|Cache misses between sweeps of dead cache entries. The key is a hash of session id and directory, so every session leaves a file; sampled because this runs once a second|
|`SKILL_COMPOUNDER_STATE`|`~/.claude/skill-compounder`|the top-level `env` block|Where runtime state lives|

Only the eight `CI_*` variables are read by `hooks/compound-improvement.sh`;
`SKILL_COMPOUNDER_USE_LOG` is read by `hooks/skill-use.sh`, which is a hook entry too.
The `CLAIM_GATE_*`, `DOC_GATE_*` and `APPLY_GATE_*` variables, and every `REPEAT_*` one
**but `REPEAT_MIN_SESSIONS`, `REPEAT_GATE_REFUSE` and `REPEAT_GATE_NOW`**, are each read
by exactly one script — `hooks/claim-gate.sh`,
`hooks/doc-gate.sh`, `hooks/apply-gate.sh`, `hooks/repeat-gate.sh` — so each belongs on
that script's own hook entries and nowhere else. Each of the four gates also takes an off
switch, and setting one to `0` disables that gate completely rather than making it quieter.
`REMIND_MAX`, `REMIND_COOLDOWN`, `REMIND_MAX_ROWS` and `SKILL_COMPOUNDER_REMIND` follow the
same rule, with `hooks/remind.sh` as their only reader, so they go on both of its entries —
the `UserPromptSubmit` one and the `PreToolUse` one — and nowhere else.

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
cannot disagree about what time it is inside one test. Neither belongs in a real config.
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
