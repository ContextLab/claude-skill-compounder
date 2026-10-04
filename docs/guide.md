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
- [A lesson for one platform or shell](#a-lesson-for-one-platform-or-shell)
- [Change a lesson](#change-a-lesson)
- [Turn a lesson into a skill](#turn-a-lesson-into-a-skill)
- [When a request keeps coming back](#when-a-request-keeps-coming-back)
- [Move a lesson up a level](#move-a-lesson-up-a-level)
- [Propose a lesson to the general pool](#propose-a-lesson-to-the-general-pool)
- [Decline a lesson](#decline-a-lesson)
- [Settle a lesson an earlier session left open](#settle-a-lesson-an-earlier-session-left-open)
- [Strengthen an ineffective lesson](#strengthen-an-ineffective-lesson)
- [Fix a guard that stops the wrong calls](#fix-a-guard-that-stops-the-wrong-calls)
- [Remove a lesson](#remove-a-lesson)
- [Switch off a lesson that ships with compound](#switch-off-a-lesson-that-ships-with-compound)
- [Share lessons with your team](#share-lessons-with-your-team)
- [Switch compound off, or make it quiet](#switch-compound-off-or-make-it-quiet)
- [Read `compound status`](#read-compound-status)
- [Read `compound report`](#read-compound-report)
- [Read the event log](#read-the-event-log)
- [Every command](#every-command)

Outputs below are real: `python3 dev/guide_examples.py` runs every command shown here in
a throwaway store and prints what the CLI answers. Paths are shown for a user named `me`
working in a project named `proj`, with compound installed at `~/.claude/compound/app`.
Where a session would have written an event (a guard's refusal, a recall, a lesson owed),
that script writes it with `compound log`, which takes the events the mod writes. A time such as `1s` is how long ago the event
was. `...` marks lines left out.

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
| ineffective | a lesson that was recalled in two sessions since it was last written: the failure keeps coming back |
| recurring | the same, for a lesson of the general pool: it is counted, and nothing is asked of Claude |
| not here | a lesson whose platform or shell is not this machine's; it is listed and does nothing |
| shadowed | a project lesson that carries the name of one of your own lessons or of a general one; it is listed and does nothing |
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
| 1 | You ask Claude to convert a TOML file. It is the session's first prompt. | `◇ ready` |
| 2 | Its Python call fails: this Python has no `tomllib`. compound asks a small model whether a recorded lesson describes the failure. None does. | spinner, `matching a recorded lesson`, then `◌ watching for the fix` |
| 3 | Claude looks at which Pythons and modules are installed. That call works, and compound asks whether it is the fix. It is not. | spinner, `is this the fix?` |
| 4 | Claude runs the conversion with a newer Python. compound asks again, and this time it is the fix. compound tells Claude to record the lesson. | `● lesson owed` |
| 5 | Claude records it with `compound add`, with a pattern, so it is a guard. The lesson is about the machine, so it goes to the user level. | `✔ lesson recorded` |
| 6 | Later, in another project, Claude is about to run Python's `tomllib` with the old Python again. The guard refuses the call and quotes the lesson. | `■ guard stopped a call` |
| 7 | Claude sends the corrected call, and it works. | |
| 8 | `/compound` shows one call stopped by a guard, and opens the lesson. | |

If Claude tries to finish at step 4 without recording or declining the lesson, compound
refuses the stop once and restates what is owed. What a real session does varies: the
model that answers compound's questions may decide a fix is not worth a lesson, and
Claude may record a plain lesson, which is recalled beside the failure instead of
stopping the call.

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
lesson python3-no-tomllib-use-tomli (project): Use when reading a TOML file with Python older than 3.11.
  -> /Users/me/proj/.claude/compound/lessons/python3-no-tomllib-use-tomli
lesson pip-externally-managed (general), matched 1 of 2 words (python): Use when pip install fails with "error: externally-managed-environment" (PEP 668: the Python of Homebrew, Debian, Ubuntu or Fedora).
  -> /Users/me/.claude/compound/app/lessons/pip-externally-managed
prompt log: no earlier request matches
```

An entry that holds only some of your words says how many, and which: `matched 1 of 2
words (python)`. Entries are ranked by how rare those words are among everything
recorded, not by how many match: a word one lesson carries outweighs several that most of
them carry. Word forms match, so `installs` finds `installing`. A lesson that is not in
force on this machine (see `not here`, `disabled` and `shadowed` above) is left out.

List everything. The four counters say how often each one was offered for reuse
(`REUSED`), stopped a call as a guard (`GUARDED`), was recalled beside a failure
(`RECALLED`) and, for a skill, was invoked in a session (`USED`):

```bash
compound list
```

```
LEVEL    KIND    NAME                          REUSED  GUARDED  RECALLED  USED  FLAG  WHEN
project  lesson  build-needs-profile           0       0        0         0           Use when running ./build.sh in this repository.
project  guard   no-env-edit                   0       0        0         0           Use when editing a .env file.
project  lesson  python3-no-tomllib-use-tomli  0       0        0         0           Use when reading a TOML file with Python older than 3.11.
user     guard   zsh-equals-word               0       0        0         0           Use when a zsh command line has a bare word starting with "=".
general  lesson  macos-gnu-only-commands       0       0        0         0           Use when a command fails on macOS with "command not found: timeout", …
general  lesson  pip-externally-managed        0       0        0         0           Use when pip install fails with "error: externally-managed-environmen…
general  guard   sed-in-place-bsd              0       0        0         0           Use when sed -i fails on macOS or BSD with an error that quotes the f…
general  guard   zsh-equals-not-found          0       0        0         0           Use when a command fails in zsh with "==== not found" or "=word not f…
general  lesson  zsh-no-matches-found          0       0        0         0           Use when a command fails in zsh with "no matches found:" (an unquoted…
general  guard   zsh-status-path-variables     0       0        0         0           Use when a command fails in zsh with "read-only variable: status", or…
general  skill   finish-task                   0       0        0         0           Use when a change is done, or thought to be done, and has to be wrapp…
general  skill   learn                         0       0        0         0           Use when a "[compound]" message says the session owes a lesson, says …
general  skill   reuse                         0       0        0         0           Use when starting a substantial task (building a script, tool, skill,…
general  skill   verify-assumptions-first      0       0        0         0           Use when starting a large effort, such as a build of several files, a…
```

In a terminal the table is coloured and fitted to its width; piped, as here, a
description is cut at 70 characters. `compound list --scripts` adds the project's
scripts. `compound list --level user` shows one level. The `FLAG` column says `ineffective`, `recurring`, `not here` (the lesson is
for another platform or shell), `disabled` (you switched it off) or `shadowed` (a project
lesson with the name of a user or general lesson, which is the one in force).

Read one lesson:

```bash
compound show python3-no-tomllib-use-tomli
```

```
python3-no-tomllib-use-tomli (project lesson)
/Users/me/proj/.claude/compound/lessons/python3-no-tomllib-use-tomli

---
name: python3-no-tomllib-use-tomli
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
  --match '(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)echo\s+=+' <<'EOF'
zsh expands a bare word starting with "=" as a command lookup and fails with "not found".
Quote it or use printf '%s\n' '====='.
EOF
```

```
recorded guard zsh-equals-word (user)
  /Users/me/.claude/compound/lessons/zsh-equals-word
```

A pattern is a Python regular expression, tested against the command of a Bash call. `^`
and `$` match at the start and end of every line of the command. Write it so that it
matches the wrong form and not the right one. The group that opens the pattern above,
`(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)`, is the anchor for "a command starts here": the start
of a line, after `;`, `&&`, `||`, `|` or `(` (which covers `$(`), and after `do`, `then`
or `else`. Without it a pattern also matches the command's name inside an argument.

A pattern is not tested against the calls of any other tool, so a file being written or
an agent's prompt that mentions the mistake is not stopped. A lesson about another tool
names it with `--tool` (repeatable), and its patterns are then tested against the JSON of
that tool's input and not against Bash commands unless `--tool Bash` is given too:

```bash
compound add --name no-env-edit --when "Use when editing a .env file." \
  --match '"file_path": "[^"]*\.env"' --tool Edit --tool Write --body "Never edit .env; change .env.example."
```

```
recorded guard no-env-edit (project)
  /Users/me/proj/.claude/compound/lessons/no-env-edit
```

## A lesson for one platform or shell

A lesson about a shell or an operating system is wrong advice everywhere else. Say where
it holds with `--platform` (`darwin`, `linux`, `windows`) and `--shell` (`zsh`, `bash`).
Each can be given more than once, and a lesson with both needs both to hold:

```bash
compound add --name zsh-function-name-is-alias --level user --shell zsh \
  --when 'Use when defining a function in zsh fails with "defining function based on alias".' \
  --body 'Name the function something that is not an alias, or write `function name {`.'
```

```
recorded lesson zsh-function-name-is-alias (user)
  /Users/me/.claude/compound/lessons/zsh-function-name-is-alias
```

On a machine where the condition does not hold, the lesson is not a guard, is not
recalled and is not offered for reuse. It is still listed, flagged `not here`, and
`compound show` says why. With bash as the shell:

```bash
compound show zsh-equals-not-found
```

```
zsh-equals-not-found (general lesson)
/Users/me/.claude/compound/app/lessons/zsh-equals-not-found
  does not apply here: it is for the shell zsh, and this is bash
...
```

The platform is the one the `compound` command runs on. The shell is the one Claude
Code's Bash tool uses, which compound infers: `CLAUDE_CODE_SHELL` when you set it, else
your login shell (`SHELL`). If that is not the shell your commands run in, set
`COMPOUND_SHELL` (for example to `bash`) in the `env` block of `~/.claude/settings.json`.

`compound add --update --name <name> --shell bash` replaces a condition, and `compound add
--update --name <name> --no-condition` drops both.

## Change a lesson

`--update` rewrites a lesson where it is. Anything you leave out keeps its value.

Add a pattern, which makes the lesson a guard:

```bash
compound add --update --name build-needs-profile \
  --match '(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)\./build\.sh\s*($|[;&|)])'
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

From then on compound sees the skill being used. Each time a session invokes it (Claude
through the Skill tool, or you by typing `/zsh-equals-word`), the band shows `skill used`
with its name, an event of type `use` is written, and the count appears as `used` beside
the skill in `compound list`, in `compound status` and on the `/compound` pane. The same
holds for every skill in your `~/.claude/skills` and in the project's `.claude/skills`,
and for the `finish-task` and `verify-assumptions-first` skills compound ships.
`compound:learn` and `compound:reuse` are not counted.

## When a request keeps coming back

At every typed request of some length, compound's reuse check reads your earlier
requests. If the same kind of request was made in three sessions, this one included, and
no lesson, skill or script covers it, the note Claude gets says so and offers to make it
a skill: once the work is done, record how it was done (`compound add`) and turn the
lesson into a skill (`compound skill <name>`). Claude does the work first, then tells you
the offer stands. The band shows `asked before`, and the event has the type `repeat`:

```bash
compound events --type repeat
```

The offer is made once per session for one kind of request. "The same kind" is decided
by the model that answers compound's questions, from the requests that share the rare
words of yours: the same procedure asked for again counts, the same topic or file does
not. `COMPOUND_REPEAT_MIN` sets how many sessions it takes (3; at least 2).

## Move a lesson up a level

A lesson starts at the project level, or at the user level when it is about your machine,
your shell or a tool.

compound moves a project lesson to the user level on its own, when the lesson matches a
failure in a second project. To move one yourself:

```bash
compound promote python3-no-tomllib-use-tomli --to user
```

```
moved python3-no-tomllib-use-tomli from project to user
  /Users/me/.claude/compound/lessons/python3-no-tomllib-use-tomli
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
compound promote python3-no-tomllib-use-tomli --to general
```

```
Plan (nothing has been written; run again with --yes to do it):
  upstream : ContextLab/claude-skill-compounder
  branch   : compound/lesson-python3-no-tomllib-use-tomli
  from     : /Users/me/.claude/compound/lessons/python3-no-tomllib-use-tomli (user level)
  files    :
    lessons/python3-no-tomllib-use-tomli/SKILL.md
  excluded : nothing
  PR title : Add lesson: python3-no-tomllib-use-tomli
  ...
```

The plan prints every file and the full pull request text. Read it. Then, to fork, push
a branch and open the pull request:

```bash
compound promote python3-no-tomllib-use-tomli --to general --yes
```

## Decline a lesson

Not every fix is worth a lesson. A typo or a missing file is a one-off. When a lesson is
owed and you do not want it, tell Claude so, and it declines with a reason. From a
terminal:

```bash
compound skip --why "a one-off typo"
```

With one lesson owed in the project, that settles it. With two, it settles nothing and
lists them (exit 2):

```
compound: 2 captures are unsettled in this project; name the one being declined with --settles ID:
  b898b8d3  `./deploy.sh --target staging` worked
  2450d7a3  `make docs` worked
```

```bash
compound skip --settles 2450d7a3 --why "a one-off typo"
```

```
declined: a one-off typo
  settles capture 2450d7a3
```

Declined lessons are listed by `compound status` under `Open`, with the reason.

Which lesson a decline settles depends on where you run it:

| Where | What `compound skip --why` settles |
|-|-|
| in a session that owes one lesson (Claude runs it) | that lesson, and any strengthening the session owes |
| in a session that owes several | nothing: it lists their ids, and one is named with `--settles <id>`. One decline settles one lesson |
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

```bash
compound events --unsettled
```

```
0s  capture  1f0c2a9e  proj  ./deploy.sh --target staging
0s  capture  7b3d5e42  proj  make docs
```

Each row is a lesson owed: how long ago, the start of the session's id, the project and
the call that worked. `compound status` prints the id each one is settled by.

## Strengthen an ineffective lesson

A lesson that was recalled in two sessions since it was last written has not prevented
anything. Several recalls in one session count once.
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

`COMPOUND_RECUR_LIMIT` sets how many recalls, one for a session, make a lesson ineffective. The default is 2.

A lesson of the general pool is not rewritten on your machine (`compound add --update`
refuses it), so it is never ineffective and Claude is never asked to strengthen it.
`compound status` lists it under `Open` as `recurring`, with what you can do:

```
Open
  recurring    pip-externally-managed (general): recalled 2 times and the failure came back. It ships with the package and is not rewritten here. Switch it off for yourself (compound disable pip-externally-managed) or report it at https://github.com/ContextLab/claude-skill-compounder/issues
```

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
way: it is switched off.

## Switch off a lesson that ships with compound

The general pool's lessons are listed by `compound list --level general`. To switch one
off for yourself:

```bash
compound disable sed-in-place-bsd
```

```
disabled sed-in-place-bsd (general): for this user it is no guard and is not recalled or offered
  switch it back on: compound enable sed-in-place-bsd
```

`compound list --level general` then flags it:

```
LEVEL    KIND    NAME                       REUSED  GUARDED  RECALLED  USED  FLAG      WHEN
...
general  guard   sed-in-place-bsd           0       0        0         0     disabled  Use when sed -i fails on macOS or BSD with an error that quotes the f…
...
```

```bash
compound enable sed-in-place-bsd
```

```
enabled sed-in-place-bsd (general)
```

The choice is kept in `~/.claude/compound/disabled.json`, outside the package, so
`compound update` does not undo it. Only a lesson of the general pool has a switch; one
of your own is removed with `compound rm`.

When you have a guard at the user level for a mistake a shipped guard also covers, a call
both match is stopped once, by yours. The shipped one stays in force for calls yours
misses. A project guard does not take a shipped guard's place: a call both match is
stopped once, and the message quotes both.

`compound rm` does not remove a shipped lesson. It exits 2 and names `compound disable`.

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

`compound status` prints six sections. `/compound status` prints the same report inside
a session, and `/compound` shows it as a pane. This is the store of this guide after two
sessions worked in it:

```
Health
  PASS  python          3.9.6
  PASS  claude code     2.1.289
  PASS  mod             enabled in /Users/me/.claude/settings.json
  PASS  mod last fired  0s ago (recall)
  PASS  cli             /Users/me/.local/bin/compound
  PASS  prompt log      0 prompts in this project
  PASS  last event      0s ago (18 events)
  PASS  duplicates      every name exists once
  PASS  lessons parse   every lesson reads
  PASS  errors          none in the last 7 days

Compound interest
  1 reuse offered · 1 call stopped by a guard · 2 lessons recalled · 1 skill used · 5 lessons recorded · since 4 Oct

Levels
  project  2 lessons  (1 guard)   0 skills
  user     2 lessons  (1 guard)   1 skill
  general  6 lessons  (3 guards)  4 skills

Lessons
  name                          level    kind    reused  guarded  recalled  used  flag
  python3-no-tomllib-use-tomli  user     lesson  1       0        0         0
  zsh-equals-word               user     skill   0       0        0         1
  pip-externally-managed        general  lesson  0       0        2         0     recurring
  zsh-equals-not-found          general  guard   0       1        0         0
  7 lessons never used (`compound list` shows them)

Recent
  1s  skill     proj  zsh-equals-word (user) -> /Users/me/.claude/skills/zsh-equals-word
  1s  moved     proj  python3-no-tomllib-use-tomli project -> user
  1s  reused    proj  python3-no-tomllib-use-tomli
  1s  guarded   proj  zsh-equals-not-found
  0s  recalled  proj  pip-externally-managed
  0s  recalled  proj  pip-externally-managed
  0s  owed      proj  ./deploy.sh --target staging
  0s  owed      proj  make docs
  0s  used      proj  zsh-equals-word (user)
  0s  declined  proj  a one-off typo

Open
  owed         b898b8d3 0s proj: `./deploy.sh` failed, `./deploy.sh --target staging` worked. Record it in a session there: /compound:learn settle b898b8d3  Or decline it: compound skip --settles b898b8d3 --why "<reason>"
  recurring    pip-externally-managed (general): recalled 2 times and the failure came back. It ships with the package and is not rewritten here. Switch it off for yourself (compound disable pip-externally-managed) or report it at https://github.com/ContextLab/claude-skill-compounder/issues
  declined     0s -: a one-off typo
```

| Section | Shows |
|-|-|
| Health | ten checks; the [README](../README.md#troubleshooting) says what to do for each `WARN` and `FAIL` |
| Compound interest | the totals, counted from the event log: reuses offered, calls a guard stopped, lessons recalled, skills used, lessons recorded, and the day of the log's first event |
| Levels | how many lessons and skills each level holds; the guards are counted among the lessons |
| Lessons | each lesson or skill that was used: times reused, times it stopped a call, times recalled, times used (a skill a session invoked), and a flag (`ineffective`, `recurring`, `not here`, `disabled`, `shadowed`). The ones never used are counted in one line |
| Recent | the last ten events: how long ago, the word for the event, the project, what it was about |
| Open | everything that waits for you |

The rows under `Open`:

| Row | Meaning | What to do |
|-|-|-|
| `owed` | a fix was found and its lesson is not recorded or declined; it stays for 14 days, also after its session ended | [settle it](#settle-a-lesson-an-earlier-session-left-open) with one of the two commands the row prints |
| `candidate` | a project lesson applied in a second project and was not moved | run the command the row prints, if you want it at the user level |
| `unparseable` | a lesson file does not read | fix the file the row names, or `compound rm <name>` |
| `ineffective` | a lesson keeps being recalled | [strengthen it](#strengthen-an-ineffective-lesson) |
| `recurring` | a lesson of the general pool keeps being recalled | [switch it off](#switch-off-a-lesson-that-ships-with-compound), or report it at the address the row prints |
| `declined` | a lesson was declined, and why | nothing; it is a record |
| `error` | compound itself failed in the last 7 days | read the message; if it repeats, report it |

The command exits 1 when a health check fails. `compound status --json` prints the same
data as JSON, with a row for every lesson, the ones never used included. In a terminal
the report is coloured (set `NO_COLOR` to turn that off) and each line is fitted to the
width.

## Read `compound report`

`compound status` says what is recorded and what is open. `compound report` says what the
event log shows compound did with it: how captures ended, what a session sent after a
guard refused a call, how often a recalled lesson was the wrong one, what the reuse check
answered and what all of it cost in time. It reads the log and writes nothing. The log
behind this example was written for this guide by `dev/guide_examples.py`; your own
report has your figures.

```
$ compound report
Window
  2026-09-20T16:00:00Z to 2026-10-02T19:00:00Z (oldest 20 Sep, newest 9h)
  100 events in 50 sessions
  A percentage, a median and a 90th percentile are printed for 10 or more; fewer says "n is too small". What followed an event is looked for in the whole log.

The learn loop
  captures                 11
  a lesson recorded        6/11 (54.5%)
  declined                 3/11 (27.3%)
    3  a one-off
  still unsettled          2/11 (18.2%)
  expired (over 14 days)   0/11 (0.0%)
  capture to settlement    n is too small: 9
  lessons recorded         6 new, 1 rewritten
  stops refused            debt 0, strengthen 0, nudge 0
  asked after a long turn  0
  reminded of unsettled    0
  moved                    0, 0 candidates left in place

Guards
  refusals                                   12
  then a different call                      8/12 (66.7%)
  then the same call again                   2/12 (16.7%)
  then no call of that tool                  2/12 (16.7%)
  the lesson's failure later in the session  0/12 (0.0%)
  lesson                refused  watched  different  same  none  failed after
  zsh-equals-not-found        8        8          5     2     1             0
  sed-in-place-bsd            4        4          3     0     1             0

Recall
  recalls                               13
  after the lesson's guard refused      0/13 (0.0%)
  the same lesson recalled again later  9/13 (69.2%)
  marked ineffective                    3/13 (23.1%)
  stronger lessons owed                 3
    rewritten                                           1/3 (n is too small: 3)
    declined                                            1/3 (n is too small: 3)
    declined: the lesson does not describe the failure  1/3 (n is too small: 3)
    lesson removed or moved                             0/3 (n is too small: 3)
    nothing done                                        1/3 (n is too small: 3)
  lesson                        recalled  after guard  again  ineffective  wrong lesson
  pip-externally-managed               5            0      4            0             0
  build-needs-profile                  4            0      3            1             0
  python3-no-tomllib-use-tomli         3            0      2            1             1
  lesson-03                            1            0      0            1             0

Reuse
  checks made: not measurable. A check that finds no candidate writes no event.
  checks with a candidate  14
  put to the judge         13/14 (92.9%)
  answered from the memo   1/14 (7.1%)
  verdicts
    named            4/14 (28.6%)
    nothing          6/14 (42.9%)
    not substantial  3/14 (21.4%)
    unanswered       1/14 (7.1%)
    unreadable       0/14 (0.0%)
  offers made  4, with 1 earlier request
  item                  offered
  release-notes-format        4
  scripts/notes.py            1
  whether an offered item was then used: not measurable from the events this report reads.

The judge
  model calls        37
  latency            median 798 ms, p90 1105 ms (n=37)
  no answer          1/37 (2.7%), in time: 0/37 (0.0%)
  unreadable answer  0/37 (0.0%)
  reuse   13  median 970 ms, p90 1195 ms (n=13)
    named            3/13 (23.1%)
    nothing          6/13 (46.2%)
    not substantial  3/13 (23.1%)
    unanswered       1/13 (7.7%)
    unreadable       0/13 (0.0%)
  recall  13  median 710 ms, p90 820 ms (n=13)
    named       13/13 (100.0%)
    none        0/13 (0.0%)
    unanswered  0/13 (0.0%)
    unreadable  0/13 (0.0%)
  fix     11  median 815 ms, p90 955 ms (n=11)
    fix         11/11 (100.0%)
    known       0/11 (0.0%)
    none        0/11 (0.0%)
    unanswered  0/11 (0.0%)
    unreadable  0/11 (0.0%)

Cost to the user
  at a prompt, something offered  n is too small: 4
    of it gathering               n is too small: 4
    of it the judge               n is too small: 4
  at a prompt, the judge alone    median 970 ms, p90 1195 ms (n=13)
  a refused call's check          median 73 ms, p90 82 ms (n=12)
  after a failed call, the judge  median 710 ms, p90 820 ms (n=13)
  after a fix, the judge          median 815 ms, p90 955 ms (n=11)
  errors                          1
    1  reuse.judge

Not measured
  time or tokens saved: no duration of a failed call or of its fix is logged
  whether an offered item was then used: no event this report reads says that an offered lesson, skill, script or earlier request was opened or run
  what followed a refusal whose `guard` event carries no `watched` field: the next call of that tool was not logged for it
  how many reuse checks were made: a check that finds no candidate writes no event, so only the checks that reached the judge or the memo are counted
  the time a reuse check took when the judge named nothing: only the judge's `ms` is logged for it
```

How to read it:

- Every figure is a count over what it is counted among: `8/12 (66.7%)` is 8 of the 12
  refusals. A percentage, a median and a 90th percentile are printed only for 10 or
  more. For fewer the line says `n is too small` and gives the n.
- **Window** says which events were counted. `--since <time>` and `--until <time>` (an
  ISO 8601 time or epoch seconds) and `--project <path>` narrow it. What followed a
  counted event, such as the lesson that settled a capture, is looked for in the whole
  log.
- **The learn loop**: each capture ended with a lesson recorded, was declined (the
  reasons are grouped by their opening words), is still unsettled, or expired after 14
  days.
- **Guards**: what the session sent next with the same tool after a refusal: a different
  call, the same call again, or nothing. This is known only for a refusal whose `guard`
  event carries `watched`; the report says how many do not. `failed after` counts the
  refusals after which the lesson was recalled beside a failure in the same session.
- **Recall**: `again` counts the recalls after which the same lesson was recalled once
  more. A lesson marked ineffective is a stronger lesson owed, and the lines under it say
  how each debt ended. `wrong lesson` counts the debts declined with a reason that says
  the lesson does not describe the failure.
- **Reuse**: only the checks that had a candidate are in the log, so the number of checks
  made is not printed. Nothing in the log says whether an offered item was opened or run.
- **The judge** and **Cost to the user**: the model calls and the milliseconds they took,
  and compound's own errors by where they happened.
- **Not measured** lists what the log cannot support. No time or tokens saved is claimed.

`compound report --json` prints the same data; each figure is `{"n": 8, "of": 12, "pct":
66.7}`, with `pct` null where n is too small.

## Read the event log

Every time compound acts, it appends one line of JSON to
`~/.claude/compound/events.jsonl`. `compound events` prints them in short form:

```bash
compound events --limit 5
```

```
1s  capture  1f0c2a9e  proj  ./deploy.sh --target staging
1s  capture  7b3d5e42  proj  make docs
1s  use      7b3d5e42  proj  zsh-equals-word (user)
1s  skip     -         proj  a one-off typo
1s  rm       -         proj  build-needs-profile (project)
```

The columns are how long ago the event was, its type, the start of the session id (`-`
for a command typed in a terminal), the project, and what the event was about.
`compound events --json` prints the stored objects, each with its full `ts`.

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
| `use` | a session invoked a skill compound lists |
| `repeat` | a request made in several sessions was offered a skill |
| `rm` | a lesson or skill was removed |
| `error` | compound itself failed |
| `judge` | a question was put to the judge model: which question, its verdict and the milliseconds it took |
| `retry` | the first call of a tool after a guard refused one, and whether it is the same call |

Filters: `--type <type>`, `--session <id>`, `--project <path>`, `--since <time>`,
`--unsettled`, `--limit <n>`, and `--json` for the full objects.

## Every command

`compound --help` lists them, and `compound <command> --help` every option of one. The
[design](design.md#cli-contract) has the exact contract of each.

| Command | What it is for | Shown in |
|-|-|-|
| `compound add` | record or rewrite a lesson | [Record a lesson yourself](#record-a-lesson-yourself), [Change a lesson](#change-a-lesson) |
| `compound list` | every lesson and skill | [Find and read what is recorded](#find-and-read-what-is-recorded) |
| `compound show` | one lesson | the same section |
| `compound find` | search lessons, skills, scripts and the prompt log | the same section |
| `compound skill` | turn a lesson into a skill | [Turn a lesson into a skill](#turn-a-lesson-into-a-skill) |
| `compound promote` | move a lesson up a level, or propose it | [Move a lesson up a level](#move-a-lesson-up-a-level), [Propose a lesson to the general pool](#propose-a-lesson-to-the-general-pool) |
| `compound rm` | remove a lesson | [Remove a lesson](#remove-a-lesson) |
| `compound disable`, `compound enable` | switch a shipped lesson off and on | [Switch off a lesson that ships with compound](#switch-off-a-lesson-that-ships-with-compound) |
| `compound skip` | decline a lesson that is owed | [Decline a lesson](#decline-a-lesson) |
| `compound events` | read the event log | [Read the event log](#read-the-event-log) |
| `compound status` | health, totals and what is open | [Read `compound status`](#read-compound-status) |
| `compound report` | what the event log says compound did | [Read `compound report`](#read-compound-report) |
| `compound install`, `compound update`, `compound uninstall` | set the package up, move it to a newer version, take it out | the [README](../README.md#install) |

Four commands exist for the mod, which runs them itself. You never need them:

| Command | The mod runs it |
|-|-|
| `compound check` | before a tool call, to test the call against every guard; it reads `{"tool", "input"}` on standard input |
| `compound memo` | after a reuse check, to keep the verdict on a request so the same request is not judged twice |
| `compound use` | when a session invokes a skill, to count the use |
| `compound log` | to append one event to the event log. It takes the events the mod writes; `learn`, `skip`, `rm`, `skill`, `promote` and `use` are written only by their own commands |
