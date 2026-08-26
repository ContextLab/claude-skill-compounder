# Claude Code platform behavior

Findings about Claude Code itself, kept separate from this package so that a project
sharing no code with it can still use them. Every entry was established by running
something and reading the result. Nothing here was taken from published documentation, and
several entries exist because the documentation says otherwise.

Each entry gives the finding, how it was established, and what it means for anything built
on top. The CLI version is named where it was recorded; where it was not, the entry says
so instead of guessing. Re-run the probe before relying on any of this in a much later
version.

Rationale for this package's own components lives in [DESIGN.md](DESIGN.md). Full hook
payload captures live in [../notes/research/insight-capture.md](../notes/research/insight-capture.md).

---

## Skills hot-reload mid-session

**Finding.** Writing `~/.claude/skills/<name>/SKILL.md` makes the skill available to the
**already-running** session, and to other live sessions, with no restart. The new skill
arrives about one tool round-trip late.

**How established.** Claude Code 2.1.241, macOS 25.5.0, 2026-08-24. The observed sequence:

1. Write the SKILL.md.
2. `Skill(hotreload-probe)` returns `Unknown skill: hotreload-probe`.
3. Make any other tool call. A system reminder announces the new skill.
4. `Skill(hotreload-probe)` succeeds.

**What it means.** A skill written mid-session is usable in that same session, so there is
no reason to defer authoring one to a follow-up session. The lag has to be written into
whatever prose tells a session to invoke a freshly written skill, because the first
`Unknown skill` is not a failure and a session that treats it as one gives up one call too
early.

---

## The status line is the only surface that animates

**Finding.** Claude Code re-renders the status line on a timer (`refreshInterval`, minimum
1s). Nothing else in the terminal UI updates continuously:

- `Bash` tool output is not reliably shown to the user.
- Writing to `/dev/tty` fights the TUI for the screen and risks corrupting it.
- Hook `systemMessage` output is discrete, arriving one message at a time.

**How established.** Claude Code 2.1.241, macOS 25.5.0, 2026-08-24, by driving each
surface in turn and watching the terminal.

**What it means.** Continuous feedback has to be **state-driven rather than
process-driven**: something writes a small file, and a status-line script paints whatever
it finds on each refresh. Nothing streams, which is what lets progress keep moving across
a subagent dispatch, where the process that started the work is not the process doing it.
The cost is that a 1s refresh re-runs whatever the status line calls once a second, so a
status line that shells out to `git` needs a cache.

---

## A `statusLine` command is run through a shell

**Finding.** The `command` of a `statusLine` entry in `settings.json` is handed to a shell
rather than executed directly, so ordinary shell syntax in it is honoured. A trailing `#`
comment is therefore inert: the status line renders exactly what it rendered without it.

**How established.** By appending `# claude-skill-compounder` to the exact command already
configured and reading the rendered status line back: an ordinary frame, unchanged. Claude
Code 2.1.241, macOS 25.5.0, 2026-08-25. The half of it that can be re-run without a live
session is `printf '%s' '<payload>' | sh -c '"…/statusline.sh"  # claude-skill-compounder'`,
which returns the same frame and exits 0.

**What it means.** A tool that writes a `statusLine` into somebody else's settings can stamp
that entry as its own with a trailing comment, the way it would stamp a hook command. Every
alternative is bound to a location or to a name: matching the full path stops recognising the
entry as soon as the tool's files move, and matching on the script's filename adopts an
unrelated status line that happens to end in the same word. A stamp the tool authors is
neither, and removing the entry later needs no state on disk to prove authorship.

---

## A subagent can dispatch subagents at one level down, and inconsistently below that

**Finding.** Agents dispatched by the main session had the `Agent` tool in **three of three
probes**, and their children ran. One level below that the result split: one agent had
`Agent` and dispatched a child successfully, another reported the identical tool list with
`Agent` absent, neither loaded nor deferred. **No predictor was found** for which an agent
gets.

**How established.** By probing: asking agents at each depth to report their tool list and
then to dispatch a child. macOS 25.5.0, 2026-08-25; the CLI version was not recorded, and
the sessions of that day ran between 2.1.241 and 2.1.245. One caveat belongs with this
entry: during the same session a probe agent fabricated a child agent's result twice,
complete with timing statistics, and retracted both when pressed, which is why the depth-1
count is stated as probes run rather than as a general rule.

**What it means.** One orchestrator layer is safe to rely on; two are not. Anything that
fans out should put the dispatcher at the first level below the main session and have the
agents it dispatches dispatch nobody. Code that assumes a nested dispatcher works will
fail for some agents and not others, with no error and no way to predict which run breaks.

## A subagent's file edits are attributed to the parent session

**Finding.** A `Write` performed by a subagent arrives as an ordinary `PostToolUse` event
carrying the **parent session's** `session_id`, not an id of its own. `Stop` for that
parent carries the identical `session_id`, so a counter written at edit time is readable
at stop time under the same key.

**How established.** By running real payloads through a hook on CLI 2.1.245 and comparing
the `session_id` field across `PostToolUse` from a subagent's write and the parent's
`Stop`.

**What it means.** Delegating work to subagents does not escape a per-session edit count,
and a session that does all its work through agents is counted the same as one that edits
directly. Anything that accumulates per-session facts at edit time and reads them at
`Stop` can rely on the two agreeing. It also means a plausible-sounding explanation for a
quiet counter — "the work moved to subagents, so nothing was counted" — is wrong, and was
measured to be wrong rather than argued away.

---

## A child running and its result arriving are separate events

**Finding.** A dispatched child can run to completion without its result being delivered
to the parent.

**How established.** In one probe, two children ran to completion and neither result was
delivered. The answers were still recoverable: they had to be read out of the task output
files.

**What it means.** Do not treat a missing result as a child that did not run. Anything
that depends on a child's answer needs a path to that answer that does not go through
delivery, and anything that counts completed work by counting returned results will
undercount.

---

## `claude plugin validate --strict` does not read `SKILL.md` frontmatter

**Finding.** The validator checks the plugin manifest and nothing below it. A plugin whose
skill frontmatter is genuinely unparseable passes.

**How established.** By building a plugin whose skill frontmatter raises
`ScannerError: mapping values are not allowed here` under `yaml.safe_load`, using an
unquoted `: ` inside the description, and running the validator against it:
`✔ Validation passed`, exit 0. Measured at 2.1.241 and again at 2.1.245.

**What it means.** The CLI validator is not a frontmatter gate and cannot be used as one.
A project that ships skills needs its own parse step, in its own test suite, where the
check does not depend on which CLI happens to be installed.

---

## The skill loader tolerates an unquoted colon, and silently drops a lost `description`

**Finding.** Two different frontmatter breaks have opposite outcomes.

An unquoted `: ` inside a description is invalid under strict YAML: the scalar ends at the
first `: ` and the remainder parses as a mapping. Claude Code's loader is **lenient** about
this case. The skill loads with its name and its full description intact, and it triggers
normally.

A break that costs the parser the `description` key itself, such as a tab-indented
`description:` line, is **not** survivable. The skill loads, keeps its name, and gets a
fallback description derived from the body (in the measured case, the H1 heading of
`SKILL.md`). The trigger clause is gone, so the skill is listed, looks installed, and never
fires. Nothing is printed anywhere.

**How established.** Measured on 2.1.245 by writing each broken skill and asking a session
to list it and then to trigger it. Run at all three scopes: **project**, `--plugin-dir`
**plugin**, and, on 2026-08-25, **personal**.

Personal scope was isolated by pointing `CLAUDE_CONFIG_DIR` at a temp directory and handing
the OAuth token in through `CLAUDE_CODE_OAUTH_TOKEN`. That last part is what the earlier
attempt was missing: a fresh config directory does not reach the credential the macOS
Keychain holds, so the CLI answers `Not logged in · Please run /login` no matter what else
is copied in. With the token in the environment the same subscription works normally, and
`<tempdir>/skills/` becomes a personal skill directory nobody else is using. Three skills
went in there — the two breaks, plus a valid control carrying a nonsense trigger token, so
that a skill failing to fire could be told apart from the scope failing to load at all.

The three scopes agreed. Listed verbatim, the unquoted-colon skill returned its whole
description; the tab-indented one returned only its H1. Asked about the trigger token, the
control fired, the unquoted-colon skill fired, and the tab-indented one did not fire on
either of two attempts, the second of which named the skill's own topic and still produced
no `Skill` call. **Remaining limit:** every run used `--model sonnet` (see the model-tier
entry below), and one CLI build.

**What it means.** Write strict YAML regardless of what the loader tolerates: quote every
frontmatter value that could contain a colon, or use a block scalar. Anything that parses
the file itself, including the upstream skills validator and any `yaml.safe_load` in a
build step, is not lenient. And the dangerous failure is the quiet one: a skill can be
present, named, and listed while its trigger has been replaced, so a project that ships
skills should assert on the parsed `description`, not on the skill appearing in a list.

---

## What the plugin path can and cannot carry

**Finding.** Loading a repo as a plugin gets you:

- **Hooks fire.** `UserPromptSubmit`, `PostToolUse` with a `Write|Edit|Bash` matcher, and
  `Stop` all reached the scripts named in `hooks/hooks.json`.
- **`bin/` lands on the Bash tool's `PATH`.**
- **Skills are namespaced** `<plugin>:<name>`, so a plugin's skills cannot collide with a
  skill the user already has.

What it cannot carry: a plugin's `settings.json` supports only `agent` and
`subagentStatusLine`. **`statusLine` is not among them.** A plugin cannot install a status
line at all.

**How established.** Claude Code 2.1.241, macOS 25.5.0, 2026-08-25, by loading a plugin
with `claude --plugin-dir` and dumping what the hooks actually received. Validation passing
is not the same as a hook running, which is why the payloads were dumped rather than
inferred. The `PATH` claim was checked with a probe binary that existed only inside the
plugin, since a name the user has already installed resolves either way and proves nothing.

**What it means.** Anything whose visible output is a status line cannot ship as a plugin,
whatever else the plugin path gives it. That is a packaging decision to make before writing
the thing, not after.

---

## Both wirings at once deliver every hook event twice

**Finding.** With a repo wired into `settings.json` **and** loaded as a plugin, one `Write`
delivers `PostToolUse` to the hook **twice**. Nothing errors.

**How established.** By running with both wirings active and counting the hook's own
invocations. Claude Code 2.1.241, macOS 25.5.0, 2026-08-25.

**What it means.** Any hook that counts, throttles, or appends has to be idempotent per
event, because telling users not to run both wirings does not stop them. The identity to
key on is already in the payload: `UserPromptSubmit` carries `.prompt_id` and `PostToolUse`
carries `.tool_use_id`, both confirmed present in real payloads on 2.1.241. Claiming an
event by `mkdir` of a directory named for that id works because `mkdir` either succeeds or
fails atomically, so of two racing hook processes exactly one proceeds. Decide in advance
what an event with no usable id should do; for a reminder, always claiming it is better,
because a lost reminder costs more than a duplicate one.

---

## `CLAUDE.md` at a plugin root fails `--strict`

**Finding.** `claude plugin validate .` passes with a warning that a root `CLAUDE.md` is
not loaded as plugin context, and `--strict` turns that warning into a failure. The same
file at `.claude/CLAUDE.md` loads as project context.

**How established.** By running both forms of the validator, and by putting a token in
`.claude/CLAUDE.md`, asking a headless session for the token, and getting it back. Claude
Code 2.1.241, macOS 25.5.0, 2026-08-25.

**What it means.** A repo that is both a project and a plugin should keep its instructions
at `.claude/CLAUDE.md`. `--strict` is what marketplace review runs, so a root `CLAUDE.md`
is a review failure and not just a warning.

---

## Hook payload fields diverge from the documented ones

**Finding.** Several hook payloads do not match their published shape. The `PreCompact`
payload is the clearest case: the field is **`trigger`**, not the documented
`compaction_trigger`; `permission_mode` is **absent** despite being documented; and
`prompt_id` and `custom_instructions` are **present and undocumented**. `SessionEnd` has
the same shape of divergence.

**How established.** By capturing real payloads from every hook event and diffing them
against the documented fields. `PreCompact` was captured on 2.1.243 by triggering
compaction headlessly with `claude -p "/compact"`, macOS 25.5.0, 2026-08-25.

**What it means.** Read the payload before writing a hook that branches on a field. A hook
reading `compaction_trigger` to tell an automatic compaction from a manual one gets `null`
and cannot tell them apart, and nothing reports the mistake.

**Field-by-field captures**, per event, are recorded once in
[../notes/research/insight-capture.md](../notes/research/insight-capture.md) section 2 and
are not repeated here.

---

## Recorded elsewhere, not repeated here

- The **two session ids** visible in one session, and what a writer and a reader can
  therefore agree on: [DESIGN.md](DESIGN.md).
- Every **hook payload** capture, event by event:
  [../notes/research/insight-capture.md](../notes/research/insight-capture.md).

## Model tier decides whether personal and project skills are routable

**Finding.** With `--model haiku`, the descriptions of personal and project-scope skills
were absent from the router: a control skill whose description alone matched the prompt did
not fire, and the session answered that no skill covered the topic. The identical prompt and
skill on `--model sonnet` fired immediately.

**How established.** By running `claude -p` from a project directory carrying its own
`.claude/skills/`, with a control skill (`plimwax-nine`) whose description was the only
possible match, on 2026-08-25 against CLI 2.1.245. Eight haiku calls and twenty-six sonnet
calls. The control is a single skill, so the boundary is established for haiku versus sonnet
and not mapped across every tier.

**What it means.** A subagent or hook running on haiku sees none of the personal or project
skill pool, so anything that depends on a skill firing must not be dispatched to haiku.
Routing results measured on one tier do not carry to another, and a skill that appears not
to fire may only be being asked on the wrong model.

## A hook reaches the model and the person through different fields

**Finding.** `additionalContext` in a hook's JSON output is delivered to the model only.
`systemMessage` is what the person sees, arriving as
`{"type":"system","subtype":"informational","content":"UserPromptSubmit says: …"}`. Two JSON
objects emitted on one stdout both land.

**How established.** By running a `UserPromptSubmit` hook headlessly on CLI 2.1.245 and
reading both the model-visible context and the terminal output.

**What it means.** A hook meant to tell the user something must use `systemMessage`; one
that only sets `additionalContext` is talking to the model while the human sees nothing.

## SessionStart fires before anyone has typed

**Finding.** `SessionStart` with subtype `startup` fired in 339 of 475 real sessions,
before any prompt was entered.

**How established.** By counting `SessionStart:startup` events against sessions carrying at
least one user prompt, across 475 transcripts on this machine, 2026-08-25.

**What it means.** Anything spent at `SessionStart` — an announcement, a query, a token
cost — is spent on sessions that are then abandoned without a single prompt. Work that
needs a person present belongs on the first `UserPromptSubmit` instead.
