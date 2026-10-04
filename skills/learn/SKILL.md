---
name: learn
description: Use when a "[compound]" message says the session owes a lesson, says an earlier session left one unsettled, says a lesson is ineffective, or asks whether it learned anything, when a failed command was just fixed, or when the user says to remember, record or write down how something was solved. Records one lesson with the compound CLI.
---

# Record a lesson

A lesson is a short note, stored where the next session will meet it, that stops a solved
problem from being solved again. Lessons are written with the `compound` command-line tool.
Never write a lesson file by hand: the tool validates the format and logs the event that
settles the session's debt.

**Which `compound` to run.** The `[compound]` message that brought you here ends with a
line `compound CLI: <absolute path>`. Run that path. If there is no such message, run
`compound` from PATH. Below, `compound` stands for whichever applies.

## 1. Read the evidence. Do not work from memory.

- The failing call, its error and the working call are quoted in the `[compound]` message.
  They are also in the log: `compound events --type capture --session "$CLAUDE_CODE_SESSION_ID" --json`
- When the message says an EARLIER session left a lesson unsettled, it quotes that
  session's failing call, error and working call with an id. Every unsettled one, with its
  id: `compound events --unsettled --json`
- When this skill was invoked as `/compound:learn settle <id>` (the line `compound status`
  prints for an unsettled lesson), the lesson to record is that one: find the id in
  `compound events --unsettled --json` and pass `--settles <id>` in step 6.
- If the lesson is about something else in this session, re-read the tool calls and results
  in the transcript above. Quote the command and the error text exactly.
- For what the user asked for, in their words: `surfer search "<keywords>"` (history-surfer's
  prompt log), when `surfer` is installed.

## 2. If it is unclear what to record, ask the user.

When you cannot tell which of several things is the lesson, whether it is worth keeping,
or which level it belongs at, ask before writing anything. Use the AskUserQuestion tool
if you have it, with the candidates as options; otherwise ask in plain text and stop.
Do not guess, and do not record several lessons to cover the possibilities.

When the evidence shows nothing worth keeping (a one-off typo, a check that correctly
failed, a file that was simply missing), decline and say why:

```bash
compound skip --why "the failure was a typo in a file name, not a recurring mistake"
```

A lesson owed by an earlier session is declined by its id, which the message gives:

```bash
compound skip --settles ab12cd34 --why "a one-off: the file was simply missing"
```

## 3. Look for an existing lesson first.

```bash
compound find "<keywords from the command and the error>"
```

If a lesson or skill already covers this, improve that one with `--update` (step 6). Do
not add a second lesson for the same mistake. `compound show <name>` prints one in full.

## 4. Choose the form.

| Form | Choose it when | How |
|-|-|-|
| lesson | The default. One or two sentences prevent the mistake. | `compound add` |
| guard | The mistake is a recognizable command or tool call. The call is then stopped before it runs. | add `--match '<regex>'` |
| script | The fix is a procedure worth running, not retyping. | add `--attach <file>` and say in the body to run it |
| skill | There are steps to follow in order AND a trigger that can route to them. | record the lesson, then `compound skill <name>` |

A `--match` value is a Python regular expression, tested with `re.search` against the
command of a Bash call (or the JSON of another tool's input). Make it match the wrong form
and not the right one. Test it on both before you rely on it.

## 5. Choose the level.

- `project` (the default): it is about this repository: its build, its scripts, its layout.
- `user`: it is about the machine, the shell or a tool, and would apply in any of this
  user's projects (a zsh quirk, a macOS command that differs from Linux, how `gh` behaves).
- `general` is never chosen here. A lesson reaches the shared pool only through
  `compound promote <name> --to general`, which opens a public pull request. Propose it to
  the user and run it only after the user explicitly says yes.

A lesson exists once, at one level. It is moved when its reach grows, never copied.

## 6. Write it.

The body is read on stdin. Lead with what to do, then the wrong way and the error it
gives, so a reader gets it right the first time. Name the command and the error, nothing
about this session. Never put a password, token or key in a lesson.

A lesson:

```bash
compound add --name build-needs-profile \
  --when "Use when running ./build.sh in this repository." <<'EOF'
Run `./build.sh --profile dev`. A bare `./build.sh` fails with
"error: a profile is required".
EOF
```

A guard, at the user level (the call is stopped once before it runs):

```bash
compound add --name zsh-equals-word --level user \
  --when 'Use when a zsh command line has a bare word starting with "=" (a ===== separator after ";").' \
  --match '(^|[;&|]\s*)echo\s+=+' <<'EOF'
zsh expands a bare word starting with "=" as a command lookup and fails with "not found".
Quote it or use printf '%s\n' '====='.
EOF
```

A lesson with a script attached (the file is copied beside the lesson):

```bash
compound add --name release-checklist \
  --when "Use when cutting a release of this repository." \
  --attach scripts/release-check.sh <<'EOF'
Run release-check.sh (beside this lesson) before tagging. It checks the version
string, the changelog entry and a clean tree, which were each forgotten once.
EOF
```

A lesson an earlier session owed. The `[compound]` message gives the id; `--settles` is
what marks that debt as paid, and without it the debt stays open:

```bash
compound add --name build-needs-profile --settles ab12cd34 \
  --when "Use when running ./build.sh in this repository." <<'EOF'
Run `./build.sh --profile dev`. A bare `./build.sh` fails with
"error: a profile is required".
EOF
```

Improving a lesson that already exists (it is rewritten where it is; flags you leave out
keep their value):

```bash
compound add --update --name build-needs-profile \
  --when "Use when running ./build.sh or make build in this repository." \
  --match '(^|[;&|]\s*)\./build\.sh\s*($|[;&|])' <<'EOF'
Run `./build.sh --profile dev` (or `make build PROFILE=dev`). Without a profile
both fail with "error: a profile is required".
EOF
```

`--name` is a lowercase slug (letters, digits, hyphens), unique among the lessons this
project can see. A user-level lesson also needs a name no other project uses.
`--when` is the description: write it as a trigger, "Use when ...", in the words a
failing call would show. Exit status 2 means the tool refused the input; read its message,
fix the command, and run it again.

## 7. When told a lesson is ineffective

A `[compound]` message that says a lesson was recalled after the failure it describes
means the lesson did not prevent it. The session owes a strengthening, and will not be let
finish until it is done or declined. Strengthen it with `--update`, which keeps every
value you do not give. Do not add a second lesson.

- Add a `--match` so the call is stopped before it runs. This is the strongest form:

  ```bash
  compound add --update --name build-needs-profile --match '(^|[;&|]\s*)\./build\.sh\s*($|[;&|])'
  ```

- If the message says the lesson already has a match pattern that did not catch the call,
  it quotes the call and the pattern. Write a pattern that matches that call and not the
  right form, and pass it the same way (`--match` replaces the patterns the lesson has).
- Or attach a script that does the step correctly (`--attach <file>`, with a body on stdin
  that says to run it), or rewrite `--when` so it names the situation.
- If none is worth doing, decline: `compound skip --why "<reason>"`.

## 8. When told a lesson moved, or could move, to the user level

A `[compound]` message that says a lesson was moved to the user level asks you to reword
it if its text speaks of "this repository": it is now read from every project. Use
`compound add --update --name <name>` with the new `--when` or body.

A message that says a lesson of another project is a candidate for the user level gives a
command that moves it. Do not run it. Tell the user and run it only if they say yes.

## 9. Say what you recorded

Tell the user in one line: the lesson's name, its level, and whether it is a guard.
