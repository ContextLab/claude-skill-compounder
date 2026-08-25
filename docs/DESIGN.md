# Design notes

Platform behavior this implementation depends on, and why each piece is shaped the way it
is. Everything below was verified by running it on **Claude Code 2.1.243, macOS 25.5.0,
2026-08-24**. Re-verify before relying on any of it in a much later version.

---

## Skills hot-reload mid-session

Writing `~/.claude/skills/<name>/SKILL.md` makes the skill available to the
**already-running** session, and to other live sessions, with no restart.

There is a lag of roughly one tool round-trip. The observed sequence:

1. Write the SKILL.md.
2. `Skill(hotreload-probe)` → `Unknown skill: hotreload-probe`.
3. Make any other tool call. A system reminder announces the new skill.
4. `Skill(hotreload-probe)` → succeeds.

**Consequence for the design:** a skill forged mid-session pays off *in that session*.
That is why the compounding loop is worth running immediately instead of deferring to a
follow-up session. It is also why the SKILL.md tells sessions not to treat the first
`Unknown skill` as a failure.

---

## There are two different session ids

`$CLAUDE_CODE_SESSION_ID` (visible to `Bash`) and the `.session_id` delivered in
hook / status-line stdin JSON are **different identifiers for the same session**. Observed
in one session: `32c3cd9e-…` in the environment variable, `f2d5c428-…` in the hook payload.

**Consequence for the design:** `skillforge` writes to a single `forge/current.json`
rather than a session-keyed file. The first implementation keyed state on the environment
variable, so the status line looked for a filename that never existed and rendered
nothing, silently, with no error anywhere.

The reminder hook *does* key its counters per session, and that is correct: it both writes
and reads using the payload's `.session_id`, so the two sides agree.

The tradeoff is that only one forge runs at a time per machine. Forging is rare and
deliberate, so this is acceptable; if it ever needs to change, the fix is for the status
line to key on something both sides can see.

---

## The status line is the only animatable surface

Claude Code re-renders the status line on an interval (`refreshInterval`, minimum 1s).
Nothing else in the terminal UI updates continuously:

- `Bash` tool output is not reliably shown to the user.
- Writing to `/dev/tty` fights the TUI for the screen and risks corrupting it.
- Hook `systemMessage` output is discrete, arriving one message at a time.

**Consequence for the design:** the animation is **state-driven, not process-driven**.
`skillforge` writes a small JSON file; the status line paints whatever it finds each
second. That decoupling is what lets the animation survive across subagent dispatches.
The builder and each red-teamer are separate processes, but they all update one file.

A 1-second refresh would otherwise re-run the user's base status line (typically `git`
calls) every second, so base output is cached for `STATUSLINE_BASE_TTL` seconds.

---

## Shell portability traps hit while building this

Each of these produced a real, silent failure during development.

**Bash folds multibyte glyphs into variable names.** `bar="$bar▓"` fails with
`bar<mojibake>: unbound variable`, because the UTF-8 bytes of `▓` are parsed as part of
the variable name. Every append must brace the expansion: `bar="${bar}▓"`.

**There is no portable way to index into a string of multibyte glyphs.** `cut -c` is
locale-dependent, bash 3.2 substring indexing (`${v:i:1}`) is byte-based, and zsh arrays
are 1-indexed while bash arrays are 0-indexed. The spinner therefore uses a plain `case`
statement, which is correct under all of them.

**`printf '%s' "…%…"` does not need `%%`.** A literal percent inside an *argument* to
`%s` is not a format string, so escaping it produces a visible `%%`.

---

## Why the red-teamer must be a fresh agent

This one constraint decides whether the red-team loop is worth running at all.

Skills rarely fail on a wrong command. They fail on an *assumed* piece of context: a
directory the author happened to be in, a tool they happened to have installed, an
ordering they knew about and did not write down. The author cannot see those assumptions,
because to them they are not assumptions.

A red-teamer that forks the orchestrating session's context inherits exactly the same
blindness and will report that the skill looks fine. Only an agent with no prior context
can discover that step 1 is unexecutable. For the same reason, each loop iteration spawns
a *new* red-teamer rather than reusing the previous one: after round 1, that agent is no
longer cold.

The retirement check has the same structure for the same reason. Asking a second agent to
"confirm this deletion" is a leading prompt, and it will be rubber-stamped. "Should this
be kept, fixed, or retired?" is a question the agent can actually answer against.

---

## Two install paths, and what each one cannot do

The repo is both a `curl | bash` install and a Claude Code plugin. Verified on
**Claude Code 2.1.241, macOS 25.5.0, 2026-08-25** by loading it with
`claude --plugin-dir` and reading what the hooks actually received.

What the plugin path gives you for free:

- `hooks/hooks.json` fires. `UserPromptSubmit`, `PostToolUse` with the
  `Write|Edit` matcher, and `Stop` all reached the scripts. Validation passing is not
  the same as a hook running, so this was checked by dumping the payloads.
- `bin/` lands on the Bash tool's `PATH`. A probe binary that existed only inside the
  plugin resolved from there, which is the test that actually proves it (a name the
  user has already installed proves nothing).
- Skills are namespaced `skill-compounder:<name>`, so the seed pool cannot collide
  with a skill the user already has.

What it cannot do: a plugin's `settings.json` supports only `agent` and
`subagentStatusLine`. **`statusLine` is not among them**, so the forge animation
cannot ship as a plugin at all.

**The decision: the installer stays the primary path.** A one-line install is a
requirement, and the animation is the most visible thing the package does; losing it
to gain a version pin is a bad trade. The plugin manifest ships alongside so the repo
can be loaded with `--plugin-dir`, submitted to a marketplace, and validated in CI.
The README says plainly that the plugin path has no status line.

### Running both wirings at once double-fires every hook

With the installer's `settings.json` entries and the plugin both active, one `Write`
delivered `PostToolUse` to the hook **twice**. Nothing errors. `CI_EDIT_EVERY=12`
silently becomes 6, and every insight is queued twice.

The fix is idempotence rather than a rule telling people not to do it. `UserPromptSubmit`
carries `.prompt_id` and `PostToolUse` carries `.tool_use_id`, both confirmed present in
real payloads. `claim_once()` claims an event by creating a directory named for that id:
`mkdir` either succeeds or fails, atomically, so of two racing hook processes exactly one
proceeds. An event with no usable id is always claimed, because losing reminders is worse
than an occasional duplicate.

### `CLAUDE.md` cannot sit at the plugin root

`claude plugin validate .` passes with a warning that a root `CLAUDE.md` is not loaded as
plugin context, and `--strict` turns that warning into a failure. Since `--strict` is what
the marketplace review pipeline runs, the file moved to `.claude/CLAUDE.md`. That path
still loads as project context: verified by putting a token in it, asking a headless
session for the token, and getting it back.

---

## Four things that were silently wrong, and how they were found

None of these produced an error. Each looked like it worked.

**An unquoted colon empties a skill.** `description: Use when X: do Y` is not valid YAML.
The scalar ends at the first `: `, the remainder parses as a mapping, the document fails,
and Claude Code loads the skill with **no metadata at all**: no name, no description, no
trigger. The skill is installed, listed on disk, and inert. Three of the four seed skills
shipped that way. Worse, the locally installed `claude plugin validate --strict` (2.1.241)
passed all three; the version CI installs from npm rejects them. So the check lives in the
test suite now, not in whichever CLI happens to be present.

**`stat -f` means different things on the two platforms.** On BSD it selects a format; on
GNU coreutils it means "report on the filesystem". So `stat -f %m "$cache"` exits 0 on
Linux and prints a mount point. The chain `stat -f %m ... || stat -c %Y ...` therefore
never reached the GNU branch, the numeric guard turned the mount point into 0, and the
status-line cache missed on every render. Every Linux user was re-running their base
status line, usually a `git` call, once a second. The fix is to try GNU first and validate
that the result is numeric before trusting it.

**`shutil.rmtree` in an installer is a data-loss bug waiting for a name collision.** While
the package shipped one skill and one CLI, replacing whatever sat at the destination looked
harmless. A seed pool makes it ten plausible names, one of which is `session-handoff`.
A user who already had a skill by that name lost it on install, and uninstall then removed
our link as "ours" and left them with nothing. Install now replaces only a symlink it can
prove it made, and reports the collision instead. This is the same rule uninstall already
followed; install had simply never been held to it.

**`$?` after `if ! cmd` is the status of the negation.** It is always 0, so
`if ! run_capped ...; then rc=$?` made the timeout diagnostic in `run_tests.sh` dead code.
Capture the status directly.

The pattern is worth naming: all four were invisible on the machine they were written on
and visible the moment they ran somewhere else, or at a scale nobody had tried. That is
what the ubuntu-plus-macos CI matrix and the cold red-team agents are for, and both earned
their cost on the first run.
