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
