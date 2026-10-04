# User guide

This guide shows how to use compound by hand: how to record, find, change, move and
remove lessons, and how to read what compound reports. For installing and a first look,
start with the [README](../README.md). For exact rules, see the [design](design.md).

You never have to do any of this. compound works on its own. These are the controls for
when you want to step in.

Contents:

- [Words used here](#words-used-here)
- [Where to type things](#where-to-type-things)
- [A first session, step by step](#a-first-session-step-by-step)
- [Record a lesson yourself](#record-a-lesson-yourself)
- [Find and read what is recorded](#find-and-read-what-is-recorded)
- [The four forms of a lesson](#the-four-forms-of-a-lesson)
- [Change a lesson](#change-a-lesson)
- [Turn a lesson into a skill](#turn-a-lesson-into-a-skill)
- [Move a lesson up a level](#move-a-lesson-up-a-level)
- [Propose a lesson to the general pool](#propose-a-lesson-to-the-general-pool)
- [Decline a lesson](#decline-a-lesson)
- [Settle a lesson an earlier session left open](#settle-a-lesson-an-earlier-session-left-open)
- [Strengthen an ineffective lesson](#strengthen-an-ineffective-lesson)
- [Fix a guard that stops the wrong calls](#fix-a-guard-that-stops-the-wrong-calls)
- [Remove a lesson](#remove-a-lesson)
- [Share lessons with your team](#share-lessons-with-your-team)
- [Switch compound off, or make it quiet](#switch-compound-off-or-make-it-quiet)
- [Read `compound status`](#read-compound-status)
- [Read the event log](#read-the-event-log)

Outputs below are real. Paths are shown for a user named `me` working in a project named
`proj`.

## Words used here

| Word | Meaning |
|-|-|
| mod | a Claude Code plugin made of hooks: code that runs when you submit a prompt, when Claude calls a tool, and when Claude is about to stop |
| lesson | a short note that says how a problem was solved |
| pattern | a regular expression that describes a wrong command |
| guard | a lesson that carries a pattern; a call that matches is refused once, before it runs |
| recalled | a lesson is recalled when a call fails and compound shows Claude the lesson for that failure |
| level | how far a lesson reaches: `project` (one repository), `user` (all your projects) or `general` (everyone) |
| general pool | the lessons and skills that ship inside the compound package |
| owed | a session owes a lesson when a fix was found and the lesson is not yet recorded or declined |
| ineffective | a lesson that was recalled twice since it was last written: the failure keeps coming back |
| prompt log | a searchable record of the prompts you type, kept by [history-surfer](https://github.com/ContextLab/claude-history-surfer) |

## Where to type things

| Looks like | Type it in |
|-|-|
| `/compound`, `/compound:learn` | a Claude Code session |
| `compound status`, `compound find ...` | a terminal |

If your shell cannot find `compound`, run it by its full path, `~/.local/bin/compound`,
or add the line that `compound install` printed to your shell profile.

## A first session, step by step

This is what happens in the screencast in the README.

| Step | What happens | What you see in the band |
|-|-|-|
| 1 | You ask Claude to convert a TOML file. Its Python script fails: this Python has no `tomllib`. | `◌ watching for the fix` |
| 2 | Claude tries again and fails again. | |
| 3 | Claude finds a way that works. compound asks a small model whether this is the fix. | spinner, `is this the fix?` |
| 4 | It is. compound tells Claude to record the lesson. | `● lesson owed` |
| 5 | Claude records it with `compound add`. The lesson is about the machine, so it goes to the user level. | `✔ lesson recorded` |
| 6 | Later, in another project, Claude is about to make the same call. A guard refuses it and quotes the lesson. | `■ guard stopped a call` |
| 7 | Claude makes the right call on its first try. | |

If Claude tries to finish at step 4 without recording or declining the lesson, compound
refuses the stop once and restates what is owed.

## Record a lesson yourself

In a session, type:

```
/compound:learn
```

Claude reads the session and the prompt log, works out what was solved, and records one
lesson. If it cannot tell what you want recorded, it asks you before it writes anything.
You can also say what you mean:

```
/compound:learn the build needs --profile dev
```

From a terminal, use `compound add`. `--when` says when the lesson applies. Write it as a
trigger: "Use when ...". The lesson's text is read from standard input, as below, or given
with `--body "<text>"` or `--body-file <path>`.

```bash
compound add --name build-needs-profile \
  --when "Use when running ./build.sh in this repository." <<'EOF'
Run `./build.sh --profile dev`. A bare `./build.sh` fails with
"error: a profile is required".
EOF
```

```
recorded lesson build-needs-profile (project)
  /Users/me/proj/.claude/compound/lessons/build-needs-profile
```

A name is lowercase letters, digits and hyphens. Never put a password, token or key in a
lesson.

## Find and read what is recorded

Search by words. The search covers lessons, skills, the project's scripts and the prompt
log:

```bash
compound find toml python
```

```
lesson python39-no-tomllib (project) [2/2 words]: Use when reading a TOML file with Python older than 3.11.
  -> /Users/me/proj/.claude/compound/lessons/python39-no-tomllib
prompt log: no earlier request matches
```

List everything. `USE/GRD/RCL` counts how often each one was reused, stopped a call as a
guard, and was recalled:

```bash
compound list
```

```
LEVEL    KIND    NAME                USE/GRD/RCL  FLAG  WHEN
project  lesson  python39-no-tomllib  0/0/0              Use when reading a TOML file with Python older than 3.11.
user     guard   zsh-equals-word     0/0/0              Use when a zsh command line has a bare word starting with "=".
general  skill   learn               0/0/0              Use when a "[compound]" message says the session owes a lesson, says a
general  skill   reuse               0/0/0              Use when starting a substantial task (building a script, tool, skill,
```

`compound list --scripts` adds the project's scripts. `compound list --level user` shows
one level.

Read one lesson:

```bash
compound show python39-no-tomllib
```

```
python39-no-tomllib (project lesson)
/Users/me/proj/.claude/compound/lessons/python39-no-tomllib

---
name: python39-no-tomllib
description: Use when reading a TOML file with Python older than 3.11.
created: 2026-10-04
origin: project proj
---
Python before 3.11 has no `tomllib`. `import tomllib` fails with "ModuleNotFoundError".
Run the script with `python3.11` or later, or `pip install tomli` and `import tomli as tomllib`.
```

A lesson is a directory with one `SKILL.md` file, plus any files attached to it. That is
the same format as a Claude Code skill.

## The four forms of a lesson

| Form | Use it when | How |
|-|-|-|
| lesson | one or two sentences prevent the mistake | `compound add` |
| guard | the mistake is a command you can describe with a pattern | add `--match '<regex>'` |
| lesson with a script | the fix is a procedure worth running | add `--attach <file>` and say in the text to run it |
| skill | there are steps to follow in order | record the lesson, then `compound skill <name>` |

A guard, recorded at the user level:

```bash
compound add --name zsh-equals-word --level user \
  --when 'Use when a zsh command line has a bare word starting with "=".' \
  --match '(^|[;&|]\s*)echo\s+=+' <<'EOF'
zsh expands a bare word starting with "=" as a command lookup and fails with "not found".
Quote it or use printf '%s\n' '====='.
EOF
```

```
recorded guard zsh-equals-word (user)
  /Users/me/.claude/compound/lessons/zsh-equals-word
```

A pattern is a Python regular expression. It is tested against the command of a Bash
call, or against the JSON input of any other tool. Write it so that it matches the wrong
form and not the right one.

## Change a lesson

`--update` rewrites a lesson where it is. Anything you leave out keeps its value.

Add a pattern, which makes the lesson a guard:

```bash
compound add --update --name build-needs-profile \
  --match '(^|[;&|]\s*)\./build\.sh\s*($|[;&|])'
```

```
updated guard build-needs-profile (project)
  /Users/me/proj/.claude/compound/lessons/build-needs-profile
```

Change when it applies with `--when`. Remove the patterns with `--no-match`:

```bash
compound add --update --name build-needs-profile --no-match
```

The text stays as it is unless you give new text. `--update` does not read standard input
on its own, so give the new text in one of these ways:

| Way | Command |
|-|-|
| one line | `compound add --update --name <name> --body "<text>"` |
| a file | `compound add --update --name <name> --body-file <path>` |
| standard input | `compound add --update --name <name> --body -`, then the text |

```bash
compound add --update --name build-needs-profile --body - <<'EOF'
Run `./build.sh --profile dev` (or `make build PROFILE=dev`). Without a profile
both fail with "error: a profile is required".
EOF
```

## Turn a lesson into a skill

A lesson is shown to Claude when a call matches or fails. A skill is something Claude
can pick by its description at any time, and follow as steps.

```bash
compound skill zsh-equals-word
```

```
zsh-equals-word is now a skill (user)
  /Users/me/.claude/skills/zsh-equals-word
```

The directory moves from the lessons directory to the skills directory of the same
level. No copy is left behind.

## Move a lesson up a level

A lesson starts at the project level, or at the user level when it is about your machine,
your shell or a tool.

compound moves a project lesson to the user level on its own, when the lesson matches a
failure in a second project. To move one yourself:

```bash
compound promote python39-no-tomllib --to user
```

```
moved python39-no-tomllib from project to user
  /Users/me/.claude/compound/lessons/python39-no-tomllib
```

Two cases need your decision. `compound status` lists both under `Open`, with the exact
command to run.

| Case | What compound does | What you run |
|-|-|-|
| git tracks the lesson in its repository | leaves it there; it is still recalled in other projects | `COMPOUND_PROJECT=<its project> compound promote <name> --to user` |
| another project has a different lesson of the same name | does not move it | `COMPOUND_PROJECT=<its project> compound promote <name> --to user --as <new-name>` |

`COMPOUND_PROJECT` names the project the lesson is in, so you can run the command from
anywhere.

## Propose a lesson to the general pool

A user-level lesson that would help anyone can be proposed to the general pool. This
opens a public pull request against the compound repository. It happens only when you
ask for it: Claude is told to offer it to you and not to run it.

First look at the plan. This writes nothing:

```bash
compound promote python39-no-tomllib --to general
```

```
Plan (nothing has been written; run again with --yes to do it):
  upstream : ContextLab/claude-skill-compounder
  branch   : compound/lesson-python39-no-tomllib
  from     : /Users/me/.claude/compound/lessons/python39-no-tomllib (user level)
  files    :
    lessons/python39-no-tomllib/SKILL.md
  excluded : nothing
  PR title : Add lesson: python39-no-tomllib
  ...
```

The plan prints every file and the full pull request text. Read it. Then, to fork, push
a branch and open the pull request:

```bash
compound promote python39-no-tomllib --to general --yes
```

## Decline a lesson

Not every fix is worth a lesson. A typo or a missing file is a one-off. When a lesson is
owed and you do not want it, tell Claude so, and it declines with a reason. From a
terminal:

```bash
compound skip --why "a one-off typo"
```

```
declined: a one-off typo
```

Declined lessons are listed by `compound status` under `Open`, with the reason.

Which lesson a decline settles depends on where you run it:

| Where | What `compound skip --why` settles |
|-|-|
| in a session (Claude runs it) | what that session owes |
| in a terminal, with one unsettled lesson in the project | that lesson; the output names its id |
| in a terminal, with several | nothing: it lists their ids, and you name one with `--settles <id>` |

A session that owed the lesson sees it settled at its next tool call: the band stops
showing `● lesson owed`, and the session can finish.

## Settle a lesson an earlier session left open

If a session ends while a lesson is owed, the debt stays. compound raises it at the first
prompt of the next session in that project, and `compound status` lists it under `Open`
with an id, for 14 days.

| To | Do this |
|-|-|
| record it | in a session in that project, type `/compound:learn settle <id>` |
| decline it | `compound skip --settles <id> --why "<reason>"` |
| list them | `compound events --unsettled` |

## Strengthen an ineffective lesson

A lesson that was recalled twice since it was last written has not prevented anything.
compound marks it ineffective. The band shows `▲ lesson ineffective`, and Claude is asked
to strengthen it before it finishes. `compound status` lists it under `Open` until it is
rewritten.

There are three ways to strengthen it, strongest first:

| Way | Command |
|-|-|
| add a pattern, so the call is stopped before it runs | `compound add --update --name <name> --match '<regex>'` |
| attach a script that does the step the right way | `compound add --update --name <name> --attach <file> --body "<text that says to run it>"` |
| rewrite when it applies | `compound add --update --name <name> --when "Use when ..."` |

If none is worth doing, decline: `compound skip --why "<reason>"`. A lesson that is
removed, turned into a skill or moved under a new name is no longer owed a strengthening.

`COMPOUND_RECUR_LIMIT` sets how many recalls make a lesson ineffective. The default is 2.

## Fix a guard that stops the wrong calls

A guard refuses a matching call once per session. Sending the same call again runs it,
so a guard never blocks you for good. If a guard matches calls it should not, give it a
narrower pattern. `--match` replaces the patterns the lesson has:

```bash
compound add --update --name <name> --match '<narrower regex>'
```

Or make it a plain lesson again:

```bash
compound add --update --name <name> --no-match
```

## Remove a lesson

```bash
compound rm build-needs-profile
```

```
removed build-needs-profile (project)
  /Users/me/proj/.claude/compound/lessons/build-needs-profile
```

A skill is removed only with `--force`. Nothing in the general pool can be removed this
way.

## Share lessons with your team

Project lessons are plain files under `<repo>/.claude/compound/lessons/`. Commit them.
Everyone who works on the repository with compound installed then gets them.

A committed lesson stays in its repository. compound never moves or changes a file that
git tracks in another project.

## Switch compound off, or make it quiet

Set these in the `env` block of `~/.claude/settings.json`, then start a new session:

```json
{
  "env": {
    "COMPOUND_QUIET": "1"
  }
}
```

| Setting | Effect |
|-|-|
| `COMPOUND_QUIET` set to `1` | the band is not drawn; the status entry, the toasts and the `/compound` pane stay |
| `COMPOUND_OFF` set to `1` | the mod does nothing and writes no event; `compound status` reports "switched off" |

The [README](../README.md#settings) lists the other common settings, and the
[design](design.md#environment-variables) lists all of them.

## Read `compound status`

`compound status` prints five sections. `/compound status` prints the same report inside
a session, and `/compound` shows it as a pane.

```
Health
  PASS  python          3.9.13
  PASS  mod             enabled in /Users/me/.claude/settings.json
  WARN  mod last fired  never: the event log holds no event the mod wrote (reuse, guard, ...)
  PASS  cli             /Users/me/.local/bin/compound
  PASS  prompt log      0 prompts in this project
  PASS  last event      0s ago (5 events)
  PASS  duplicates      every name exists once
  PASS  lessons parse   every lesson reads
  PASS  errors          none in the last 7 days

Store
  level    lessons  skills  guards
  project  0        0       0
  user     1        1       1
  general  0        2       0

Lessons
  name                level  kind    reuse  guard  recall  flag
  python39-no-tomllib  user   lesson  0      0      0       never used
  zsh-equals-word     user   skill   0      0      0       never used

Recent
  2026-10-04T05:02:13Z learn    -        proj                 python39-no-tomllib (project)
  2026-10-04T05:02:13Z learn    -        proj                 zsh-equals-word (user)
  2026-10-04T05:02:13Z promote  -        proj                 python39-no-tomllib project -> user
  ...

Open
  skipped      2026-10-04T05:02:14Z -: a one-off typo
```

| Section | Shows |
|-|-|
| Health | nine checks; the [README](../README.md#troubleshooting) says what to do for each `WARN` and `FAIL` |
| Store | how many lessons, skills and guards each level holds |
| Lessons | per lesson: times reused, times it stopped a call, times recalled, and a flag |
| Recent | the newest events: time, type, session, project, detail |
| Open | everything that waits for you |

The rows under `Open`:

| Row | Meaning | What to do |
|-|-|-|
| `unsettled` | a session ended while it owed this lesson | [settle it](#settle-a-lesson-an-earlier-session-left-open) |
| `candidate` | a project lesson applied in a second project and was not moved | run the command the row prints, if you want it at the user level |
| `unparseable` | a lesson file does not read | fix the file the row names, or `compound rm <name>` |
| `ineffective` | a lesson keeps being recalled | [strengthen it](#strengthen-an-ineffective-lesson) |
| `skipped` | a lesson was declined, and why | nothing; it is a record |
| `error` | compound itself failed in the last 7 days | read the message; if it repeats, report it |

The command exits 1 when a health check fails. `compound status --json` prints the same
data as JSON.

## Read the event log

Every time compound acts, it appends one line of JSON to
`~/.claude/compound/events.jsonl`. `compound events` prints them in short form:

```bash
compound events --limit 5
```

```
2026-10-04T05:02:13Z learn    -        proj                 python39-no-tomllib (project)
2026-10-04T05:02:13Z learn    -        proj                 zsh-equals-word (user)
2026-10-04T05:02:13Z promote  -        proj                 python39-no-tomllib project -> user
2026-10-04T05:02:13Z skill    -        proj                 zsh-equals-word (user) -> /Users/me/.claude/skills/zsh-equals-word
2026-10-04T05:02:14Z skip     -        proj                 a one-off typo
```

The third column is the start of the session id. It reads `-` for a command typed in a
terminal.

| Type | Written when |
|-|-|
| `reuse` | the reuse check added existing work to a prompt |
| `guard` | a guard refused a call |
| `recall` | a failed call was given its lesson |
| `capture` | a fix was found and a lesson became owed |
| `remind` | a session was told of lessons an earlier session left open |
| `refuse` | a stop was refused |
| `nudge` | after a long turn, Claude was asked whether it learned anything |
| `learn` | a lesson was recorded or rewritten |
| `skip` | a lesson was declined |
| `promote` | a lesson moved up a level or was proposed |
| `candidate` | a lesson could move to the user level and was left in place |
| `skill` | a lesson became a skill |
| `rm` | a lesson or skill was removed |
| `error` | compound itself failed |

Filters: `--type <type>`, `--session <id>`, `--project <path>`, `--since <time>`,
`--unsettled`, `--limit <n>`, and `--json` for the full objects.
