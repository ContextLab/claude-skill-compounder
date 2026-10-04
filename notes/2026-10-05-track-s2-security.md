# 2026-10-05 (written 2026-10-04): track S2, security review of `462761d` and fixes

Base `462761d` (track J). Worktree branch `worktree-agent-a2092a3eb75fbfa03`. Not pushed,
not merged. Nothing was written to the real store: every CLI run that writes used a
sandbox, and the only runs against the real store were `compound check --guards`, which
reads. The live mod showed this session no `[compound]` message; no `add` or `skip` was
run against the real store.

A background review of the commit reported five findings by title only. Each candidate
was put to a test with real files and the real CLI (or the mounted hooks) before anything
was changed. How the base failures were shown: the base tree was exported with `git
archive HEAD`, the new test files copied in, and the suites run there. Where a new test
passes the new `--upstream` option, a copy of the file without it was run on the base as
well, so that the failure seen is the finding and not an unknown option.

## Findings

| # | Finding | Severity | Confirmed on base | Test | Fix |
|-|-|-|-|-|-|
| 1 | **The bare name `compound` was exempt on the word of another shell.** The mod asked `sh` whether `compound` on PATH is the package's CLI, once in five minutes, with no working directory given, and exempted a bare `compound ...` call from the guards, recall and capture on a yes. The call is run by the Bash tool's shell | Medium | yes. `hooks/decisions.test.ts`: 3 tests fail on base. Shown with real shells too (below) | `S2: the bare name ... is never exempt, in any shape`, `S2: the bare name is checked like any other call ... and no shell is asked`, `S2: another path to the CLI, and another file called compound, are checked` | The bare name is never exempt. `bareIsOurs`, `BARE_SH` and the five-minute cache are deleted. Exempt is only the absolute path the mod itself runs, compared character for character (`soleCli(command, cli)`) |
| 2a | **A project SKILL took the name of the user's guard.** Shadowing looked at lessons only. `<repo>/.claude/skills/my-guard/SKILL.md` with `match: ["^ls"]` was a guard in force under the user's guard's name (it uses up that name's one refusal per session), and `compound show my-guard` printed the repository's text | High (the same effect as track S finding 5, by another door) | yes, 3 tests | `tests/test_boundaries.py` `ShadowedSkillTest` | `scan`: a project lesson or skill that carries the name of a user or general lesson or skill is `shadowed` |
| 2b | **The credential scan of `promote --to general` read file contents as UTF-8 only.** A token in a file's NAME was published unseen, and a private key in a UTF-16 file was not found | Medium | yes, 2 tests | `PublishScanEdgesTest` | `secret_findings` reads each staged file three ways: UTF-8, the bytes without zero bytes, and the name (reported without repeating it) |
| 2c | **Where `--yes` publishes was the environment's word alone.** With `COMPOUND_UPSTREAM_GIT` (new in track J) or `COMPOUND_UPSTREAM` set, `promote --to general --yes` pushed the lesson there without the destination appearing in the command | Medium | yes: the branch was pushed to the repository only the variable named | `DestinationTest` (6 tests) | A destination that is not the package's own pool is published to only with `--yes --upstream <the same value>`. Without it: exit 2 before anything is cloned, naming the destination, the variable and the command. `--upstream` chooses nothing: a value that differs is exit 2. The plan says so first and carries `confirm` |
| 3a | **The project level followed a symbolic link out of the project.** `<repo>/.claude`, `.claude/compound/lessons` or `.claude/skills` as a link to any directory: its lesson directories were listed and in force as project lessons, `compound rm NAME` deleted a real directory OUTSIDE the project (`shutil.rmtree`), `compound add --level project` wrote outside it, and `compound skill` moved a lesson outside it. Track S checked a lesson directory against its lessons directory, both resolved, so a linked parent passed | High (deletion and creation of directories outside the repository, at a repository's choosing, when the user or the session runs an ordinary command there) | yes, 6 tests | `LinkedStoreTest` (8 tests, 2 controls) | `project_store_problem`: a project store that does not resolve inside the project root is not read (`scan`), not written (`add`, `skill`), and nothing under it is a name `rm` acts on; `lessons parse` names it. One project skill that is a link out is left out. `holders` and `recall_item` hold another project's lesson to its own root. A link that stays inside the project is fine. The user's own store seen as a project's is read once |
| 3b | **`promote --to general --yes` wrote through a link in the clone.** A pool whose `lessons` is a symbolic link had the lesson's files written where the link leads, outside the temporary clone, before `git add` failed | Medium (needs a hostile or mistaken upstream; what is written is the user's lesson, at `<link target>/<name>/`) | yes: `landing/plain-note` was created | `PoolLinkTest` | The lesson is written into a real directory of the clone or not at all; `lexists` in place of `exists` for the name. The dangling-link variant did not write on base either (it failed in `makedirs`); its test is a control |
| 4 | **The fields an event is found by were a way around the mask.** `lesson`, `lessons`, `id`, `session`, `settles`, `kind`, `level`, `path`, `project`, `from`, `seen_in`, `also`, `merged` were written as given, and a value that was no text (an object under `path`) was not looked at | Low (the mod puts nothing free there; another caller of `compound log` could) | yes, 1 test | `FoundByFieldsTest` (1 and a control) | `found_by`: such a field is held to the rules that know a credential by shape alone. In a path: the PEM block and the URL password (not the token forms: a directory may be called `sk-learn-experiments`). Elsewhere those, the bearer token and the token forms. A lesson name that is a slug is kept |
| 5 | `install.sh` accepted a ref part beginning with `-` or `.` (`release/-f`) that the CLI's `ref_ok` refuses | Low: on base the value reached `git checkout`, which refused it as an invalid reference; no option was read | reached git (the test fails on base); no harm shown | `tests/test_arguments.py`, two refs added to the existing list | `*/[!A-Za-z0-9]*` added to the `case` |

The titles "allowlist-resolution-differential in hooks/register.ts", "integrity-check-bypass
in bin/compound" and "path-traversal-via-symlink in bin/compound" are taken to be 1, 2a to
2c and 3a to 3b. Which of 2a, 2b, 2c the reviewer meant is not known; all three
reproduced. The two unnamed findings were not identified from the review; 4 and 5 are
this review's own.

### 1, with real shells

`BARE_SH` (`p=$(command -v compound) && [ "$p" -ef "$1" ]`) run by `sh`, against what
`zsh` runs for `compound list`, in a throwaway directory with two files called
`compound`:

- a relative PATH entry (`bin:`): `sh` in one directory answered yes (exit 0); `zsh` in
  the repository's directory ran the repository's `bin/compound`;
- a shell function named `compound`: `sh` yes; `zsh` ran the function;
- an alias: `zsh` ran the alias;
- PATH changed after the answer (the cache held it five minutes): `sh` yes; `zsh` ran the
  other file.

### The choice on the bare name, and its cost

Exempt is the absolute path of the CLI the mod runs, exactly as the mod runs it, and
nothing else. No symlink is resolved on either side and no file is inspected: the task
suggested comparing after resolving links and checking the file, and that was not done,
on purpose. A resolved comparison is a second answer that can differ from the shell's
(a link replaced between check and use); handing the shell the same string the mod
executes has no check to race. So `~/.local/bin/compound list` and `<pkg>/bin/../bin/compound
list` are ordinary calls.

Cost: a session that types `compound add ...` bare gets (a) one refusal when the lesson's
text matches a guard, sent again; (b) a `compound` command that fails (a refused
duplicate, a usage error) treated as a failed call: the judge may be asked, a lesson may
be recalled, and it is held until a call succeeds, which can become a capture. The
`[compound]` messages already end with the path, and now say to run it by that path;
`skills/learn/SKILL.md` says the same and why. Commands the CLI itself prints
(`COMPOUND_PROJECT=... compound promote ...`, `compound add --update --name ...`) still
use the bare name; a session that copies one pays (a) at most. NOT measured: how often a
real session types the bare name despite the message. The three journeys below passed.

Looked at and left: the three assignments allowed in front of an exempt call
(`COMPOUND_HOME`, `COMPOUND_CLAUDE_DIR`, `COMPOUND_PROJECT`) redirect where the CLI
reads and writes. They choose no program, and a debt is not settled by writing to
another home (the mod reads its own log). `COMPOUND_BIN` is read from the mod's
environment only when the package has no CLI of its own, never from the command.

## Looked at, nothing to fix

- **`compound log` and settlement.** `learn`, `skip`, `rm`, `skill`, `promote`,
  `candidate`, `use` are refused; the type pattern cannot be passed with a trailing
  newline (it is then no known type); a line separator inside a string cannot forge a
  line (quotes are escaped, and the log is read line by line on `\n`). `add --settles`
  and `skip --settles` take any unsettled capture's id, from any session: that is the
  documented rule. `seed_event` exists only in `tests/`.
- **`--attach`, `--body-file`** (by reading). An attachment is copied to a temporary file and renamed
  in, so an existing link of that name in the lesson is replaced, not written through.
- **`update` removing user lessons, `uninstall --purge`, `settings.json`.** As track S
  found. `settings.json` is written through a symbolic link deliberately (a dotfiles
  setup); the existing test stays.
- **`memo.json`, `disabled.json`.** Written by rename, so a link there is replaced.
  `events.jsonl` is appended through a link if it is one: it is under `COMPOUND_HOME`,
  the user's own.
- **Claims** (by reading). `find` does not follow a link given on its command line with `-mindepth 1`
  finding nothing; keys pass `safe()`.
- **git and gh arguments.** `ext::`, a leading dash, `..`, `@{`, `.lock`: refused or not
  expressible. `file://` and a local path are ordinary sources.
- **The masking rules themselves** are the mod's, rule for rule; the `between` calls are
  masked by the mod before the judge sees them (`hooks/judge.ts`), and whatever the mod logs is masked again by the CLI.

## Accepted or open, for the owner

- **A `recall` handed to `compound log` with `ineffective` or `counted` already set keeps
  it.** Existing tests rely on it (`test_an_event_that_says_ineffective_itself_is_kept_as_it_is`).
  The mod sends neither. Now stated in the design's "does not defend against".
- **The environment is trusted**, including `COMPOUND_NOW` (a test seam in the CLI: with
  it set far ahead, `add --update` stamps a lesson so that no later recall counts) and
  `COMPOUND_HOME`. I did not verify whether Claude Code applies the `env` block of a
  project's own `.claude/settings.json`; if it does, a repository the user has trusted
  can set these. The design now says the environment is trusted and names the one thing
  a variable cannot do alone (choose where a lesson is published).
- **`COMPOUND_UPSTREAM_GIT` stays** as a variable (the tests publish through it), behind
  `--upstream`. Whether it should exist outside tests is the owner's call.
- **zsh global aliases** (`alias -g`) can rewrite any word of an exempt call. Stated.
- **A lowercase token that is a valid slug** (`xoxb-...` in lowercase) in a `lesson`
  field is kept as a name. A token shape inside a path is not masked.
- **A recall event's `path`** makes `log` read `<root>/.claude/.../<name>/SKILL.md`
  wherever the event says (now held inside that root). It yields only `counted`.
- **A project skill that is a link out of the project** is no longer listed by compound.
  Claude Code itself may still load it as a skill. A user who keeps such a link on
  purpose loses its row in `compound list`; `lessons parse` says why.
- **Mixed-encoding or encoded secrets** (base64, UTF-32, a secret split across files)
  are not found by the publish scan. A lower bound, as before.

## Assertions changed in existing tests

1. `hooks/decisions.test.ts`: the table of exempt shapes is now `SHAPES`; `EXEMPT` is each
   shape with the program written as the package's path, and `BARE` (the 15 shapes typed
   with the bare name) is asserted NOT exempt. `soleCli` takes two arguments.
2. `hooks/decisions.test.ts` `D6: only the package's own CLI qualifies...`: the bare-name
   assertions are gone (`soleCli('compound list', 'compound', true)` was `'list'`);
   `soleCliShape` returns no `bare`; other paths to the same file are asserted not exempt.
3. `hooks/decisions.test.ts` `D6: the bare name is exempt only while ...` is replaced by
   `S2: the bare name is checked like any other call ...` (it asserted one `sh` question;
   now none).
4. `hooks/decisions.test.ts`, the here-document test and the failed-call test: the CLI is
   called by the package's path; assertions unchanged.
5. `hooks/measure.test.ts` `... or of the CLI to read the lesson ...`: `show` is called by
   the package's path (bare, it is now the call that follows a refusal).
6. `hooks/ui.test.ts` `no check is made before a call of a tool no guard applies to`: the
   `add --update` is called by the package's path; the count stays 4.
7. `hooks/render.test.ts` (2 places), `README.md`, `docs/design.md` (2): the last line of a
   message reads `(run it by this path: a call by any other name, \`compound\` on PATH
   included, is checked like any other command)`.
8. `tests/test_decisions.py` `PublishScanTest`: the seven `--yes` runs add `--upstream
   self.upstream`; assertions unchanged.
9. `tests/test_promote.py`: the two `--yes` runs against `NO_UPSTREAM` add `--upstream
   NO_UPSTREAM`; assertions unchanged.
10. `tests/test_arguments.py`: two refs added to a list of refused refs.

No test was removed or weakened.

## Measured

`compound check --guards`, real store read-only (11 guards), 20 runs, Apple M2 Max:
median 65.2 ms before (62.1 to 68.1), 65.3 ms after (63.3 to 67.2). `scan` gained a few
`realpath` calls. Before a tool call the mod now starts no `sh` at all (it started one
at most every five minutes for a bare `compound` call).

## Checks at the end

`./run_tests.sh`: OK, 23 files, 680 tests (22 files, 655 before; `tests/test_boundaries.py`
is new, 25 tests; 18 do not pass on base, one of them, the dangling link in a pool, only because the base has no `--upstream`). `claude plugin validate --strict .`: passed.
`claude plugin test .`: 282 pass, 0 fail (280 before). `npx tsc --noEmit -p .`: no `error
TS`. `python3 dev/guide_examples.py`: output identical to the base's, so no example in the
guide or the README changed.

Journeys, run once each for real (haiku), after the changes:

| Journey | Result |
|-|-|
| `journey_guard.py` | 22 of 22 |
| `journey_capture.py` | 10 of 10 |
| `journey_stop.py` | 12 of 12 |

## Files

`hooks/render.ts`, `hooks/register.ts`, `bin/compound`, `install.sh`,
`skills/learn/SKILL.md`, `docs/design.md`, `docs/guide.md`, `README.md`,
`tests/test_boundaries.py` (new), and the test files listed above.
