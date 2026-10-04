# compound

A Claude Code mod that makes each session start from what earlier sessions already built
and learned.

- **Before a substantial task**, it looks for skills, lessons, scripts and earlier
  requests that already cover it, and tells Claude to reuse or broaden those before
  building anything new.
- **After a problem is solved**, it has the lesson written down where the next session
  will meet it. A mistake made once is stopped before it is made again.

Both happen from hooks. Neither you nor Claude has to remember to do anything.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh | bash
```

Then start a new Claude Code session. Check that it is working:

```bash
compound status
```

Requirements: Claude Code 2.1.288 or later, `python3` (3.9 or later), `git`. The installer
also installs [history-surfer](https://github.com/ContextLab/claude-history-surfer), the
searchable log of your prompts that compound reads, unless you already have it.

The mod is built on Claude Code's function-hook API, which is early access and may change
between releases.

| To | Run |
|-|-|
| update | `compound update` |
| uninstall, keeping your lessons | `compound uninstall` |
| uninstall and delete your user-level lessons | `compound uninstall --purge` |

Install adds one path to `env.CLAUDE_CODE_PLUGIN_DIRS` in `~/.claude/settings.json`, links
`compound` into `~/.local/bin` or `~/bin`, and records both in
`~/.claude/compound/install.json`. Uninstall reverses exactly that. Skills you made with
`compound skill` are yours and stay in `~/.claude/skills`; project lessons stay in their
repositories.

## What you will see

A few terms first. A **mod** is a Claude Code plugin made of hooks: code that runs when a
prompt is submitted, a tool is called or Claude is about to stop. A **lesson** is a short
note recorded after a problem was solved. A **guard** is a lesson that carries a
**pattern**, a regular expression tested against a tool call before it runs. The **status
entry** is a short line Claude Code shows in its status area.

compound sets a status entry each time it acts, so a firing is never silent.

**You type a request to build something substantial.** compound gathers the lessons,
skills and scripts already recorded, and earlier requests of yours that share its words,
and asks a small model which of them cover part of the request. What it names is added to
the prompt:

```
[compound] Reuse before building.
Existing work that may cover part of this request (kind, name, level, path):
- skill cdl-bib-cite (user) ~/.claude/skills/cdl-bib-cite: "fills a placeholder citation ..."
- script scripts/release.sh (project): "tags and publishes a release"
Earlier requests like this one, quoted from the prompt log (id, date, project):
- 3f2a91c0:4 2026-09-14 paper-draft: "add the missing citations ..."
Where an entry does cover part of this request, use it, or broaden it so it also covers
this case. Build new only what none covers.
```

A short prompt, a request to run a command, or a request nothing covers adds nothing.

**A command fails, and a later one fixes it.** compound quotes both back to Claude and
tells it to record the lesson. If Claude tries to finish without recording or declining
it, the stop is refused once. A lesson still unrecorded when the session ends is listed
by `compound status` and raised again at the start of the next session in that project.

**The same mistake is about to happen again.** If the lesson is a guard, the call is
refused once with the lesson quoted as the reason; sending the same call again runs it.
If a call fails anyway, the matching lesson is returned beside the error.

**A lesson keeps recurring.** A lesson that is recalled twice after the same failure has
not prevented anything. compound marks it ineffective, and Claude must strengthen it (add
a pattern, attach a script, or rewrite it) or say why not before it can finish.

**Something in compound itself breaks.** The error is logged, shown in the status entry
and reported to Claude at the next prompt. A broken check never blocks your work.

Recorded text is always shown to Claude as a quoted note to weigh, never as an
instruction.

To record a lesson yourself at any time, type `/compound:learn`. If it is unclear what
you want recorded, Claude asks.

## Where lessons live

A lesson lives at exactly one of three levels. It is moved when its reach grows and is
never copied.

| Level | Applies to | Location |
|-|-|-|
| project | this repository | `<repo>/.claude/compound/lessons/` |
| user | two or more of your projects, or your machine and tools | `~/.claude/compound/lessons/` |
| general | anyone | `lessons/` and `skills/` in this package |

A lesson starts at the project level. One that matches a failure in a second project is
moved to the user level automatically, unless git tracks it in its own repository: a
committed lesson stays where it is, is still recalled, and is listed by `compound status`
with the command that moves it. One that would help anyone can be proposed to the
general pool, which opens a pull request against this repository:

```bash
compound promote <name> --to general        # prints the plan, writes nothing
compound promote <name> --to general --yes  # forks, pushes, opens the pull request
```

Project lessons are plain files in the repository. Commit them and everyone who works on
it with compound installed gets them.

A lesson is a directory with a `SKILL.md`, the same format as a Claude Code skill, plus
any scripts it needs. `compound skill <name>` moves one into the skills directory of its
level, which makes it a skill Claude can route to by description.

## What is working and what is not

```
$ compound status

Health
  PASS  python          3.9.13
  PASS  mod             enabled in ~/.claude/settings.json
  PASS  mod last fired  9s ago (guard)
  PASS  cli             ~/.local/bin/compound
  PASS  prompt log      113 prompts in this project
  PASS  last event      9s ago (78 events)
  PASS  duplicates      every name exists once
  PASS  lessons parse   every lesson reads
  PASS  errors          none in the last 7 days

Store
  level    lessons  skills  guards
  project  6        1       2
  user     32       4       7
  general  0        2       0

Lessons
  name             level  kind    reuse  guard  recall  flag
  zsh-equals-word  user   guard   0      4      0
  ci-checks        user   lesson  3      0      2       ineffective
  ...
```

`Recent` lists the last ten events and `Open` lists what needs attention: ineffective
lessons, lessons owed and not yet recorded, lessons Claude declined to record and why,
lessons that could move up a level, and errors. The command exits 1 when a health check
fails. Inside a session,
`/compound` prints the same report. Every event is one line of JSON in
`~/.claude/compound/events.jsonl`.

## Commands

| Command | Does |
|-|-|
| `compound status` | health, counts, per-lesson use, recent events, what is open |
| `compound list` | every lesson and skill at every level |
| `compound find <words>` | lessons, skills, scripts and earlier prompts matching the words |
| `compound show <name>` | one lesson |
| `compound add --name <n> --when <trigger>` | record a lesson; the text is read on stdin |
| `compound skill <name>` | turn a lesson into a skill |
| `compound promote <name> --to user\|general` | move a lesson up a level |
| `compound rm <name>` | remove a lesson (`--force` for a skill) |

`compound <command> --help` lists every option. [docs/design.md](docs/design.md) has the
full contract.

## Settings

Environment variables, read by the mod. Set them in the `env` block of
`~/.claude/settings.json`.

| Variable | Default | Meaning |
|-|-|-|
| `COMPOUND_OFF` | unset | `1` switches the mod off |
| `COMPOUND_PROMPT_MIN_CHARS` | 80 | shortest prompt the reuse check looks at |
| `COMPOUND_TURN_MIN_CALLS` | 25 | tool calls in a turn before Claude is asked whether it learned anything |
| `COMPOUND_NUDGE_COOLDOWN` | 1800 | seconds between those questions |
| `COMPOUND_RECUR_LIMIT` | 2 | recurrences before a lesson is ineffective |
| `COMPOUND_MODEL` | `haiku` | model that answers the mod's questions |
| `COMPOUND_JUDGE_TIMEOUT` | 10 | seconds to wait for it |

## Cost

The mod asks a small model one question per substantial prompt, one per failed tool
call, and one for each of the next successes of the same tool, five at most, until one
is the fix. Measured on Claude Code 2.1.289, the prompt check (a search of the prompt log
and the model call) adds about one second to a prompt. The guard adds about 30 ms to a
tool call when any lesson carries a pattern and nothing otherwise; a check that has not
answered within 1.5 seconds is abandoned and the call runs. The calls use the same
account as the session.

## How it works

[docs/design.md](docs/design.md) describes the parts, the five moments the mod acts at,
the lesson format, the CLI contract and the tests. [CONTRIBUTING.md](CONTRIBUTING.md)
covers working on the package and proposing a lesson to the general pool.

## License

See [LICENSE](LICENSE).
