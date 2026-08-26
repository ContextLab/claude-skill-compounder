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

## A symlinked skill hot-reloads too, and the lag is not fixed

**Finding.** The reload above is not limited to a file written in place. A *symlink*
dropped into a watched skills directory mid-session is picked up the same way, and the
lag is not a constant: in one run the skill answered on the very next `Skill` call, and
in another it took one further tool call before it did. A first `Unknown skill: <name>`
is therefore not evidence that the link failed.

**How established.** Claude Code 2.1.245, macOS 25.5.0, 2026-08-25, by linking a skill
directory into the live skills directory from inside a running session and calling
`Skill` straight afterwards. Two runs; one of them was `claim-provenance`, which had
answered `Unknown skill` earlier the same day, before its symlink existed, and answered
normally once it did. The in-session record is in
[../notes/2026-08-25-issue9-fix-session.md](../notes/2026-08-25-issue9-fix-session.md).
**Remaining limit:** two runs show that the lag varies. They do not bound it.

**What it means.** Anything that installs a skill by symlink into a running session must
tell its caller to make one more tool call and try again before concluding the install
failed. One intervening call is the largest delay anyone has actually seen here, which is
not the same as a ceiling.

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
attempt was missing; the entry below on credentials is why a fresh config directory cannot
authenticate on its own. With the token in the environment the same subscription works
normally, and
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

## A changed `HOME` or `CLAUDE_CONFIG_DIR` costs a CLI run its credentials

**Finding.** `claude -p` answers `Not logged in · Please run /login` when either `HOME` or
`CLAUDE_CONFIG_DIR` points somewhere fresh. It is not a settings problem, and copying files
into the new directory does not repair it: on macOS the credential lives in the Keychain,
which a subscription login reaches only through the ambient environment, or else the token
has to be handed in through `CLAUDE_CODE_OAUTH_TOKEN`.

**How established.** Claude Code 2.1.245, macOS 25.5.0, 2026-08-25. Three runs of one
one-word prompt with `--setting-sources ''`: `HOME` pointed at an empty temp directory,
`CLAUDE_CONFIG_DIR` pointed at an empty temp directory, and the ambient environment as a
control. The first two refused; the control answered.

**What it means.** A test harness that isolates itself by moving `HOME` -- the normal way
to keep a suite off a real config -- has also taken away its ability to call the CLI. A
suite arranged that way cannot spend money by accident and cannot exercise a real model
call either; the two goals are in direct conflict, and the environment decides which one
is had. It follows that anything which does succeed in calling `claude` from inside a hook
is running on the user's ambient credentials, since those are the only ones present, and
that a launcher setting either variable "helpfully" turns every dispatched call into
`Not logged in` with no other symptom.

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

## `PostToolUse` fires only when the tool succeeded

**Finding.** A tool call that fails does not arrive as `PostToolUse` with an error inside
it. It arrives as a separate event, `PostToolUseFailure`, matched on the tool name the same
way. A hook wired only to `PostToolUse` therefore sees a stream of successes and has no way
to know that anything failed.

**How established.** Claude Code 2.1.245, macOS 25.5.0, 2026-08-25, observed live in a
session whose hooks announce themselves. A `Bash` call that died on a shell parse error was
delivered as `PostToolUseFailure:Bash`, carrying `Tool "Bash" failed. Analyze the error,
fix the issue, and continue working.`; every `Bash` call that succeeded in the same session
was delivered as `PostToolUse:Bash`. That much was read off the delivery labels and their
text rather than a captured payload; the failure event's own field shape was captured on
2026-08-26 and is recorded in the entry below on failed `Skill` calls. The measured
`PostToolUse` payload shape is in
[../notes/research/insight-capture.md](../notes/research/insight-capture.md).

**Open question, not a finding.** Whether a `Skill` invocation made inside a *subagent* is
delivered to these hooks at all, and if it is, whose `session_id` it carries. A subagent's
file edits were measured to carry the parent session's id, recorded above, and that result
must not be extended to skill invocations without measuring them.

**What it means.** Anything that counts tool outcomes has to wire both events. Wiring only
`PostToolUse` does not merely miss the failures, it records each one as a success, which is
a wrong number rather than a missing one.

---

## A failed `Skill` invocation is delivered to no hook at all

**Finding.** `Unknown skill: <name>` produces neither `PostToolUse` nor
`PostToolUseFailure`. A failing `Bash` call in the same session arrives as
`PostToolUseFailure` normally, so the event itself is working; the skill failure simply
never reaches the hook layer. The failure is visible only in the transcript, as a
`tool_result` carrying `is_error: true` and the text
`<tool_use_error>Unknown skill: …</tool_use_error>`.

**How established.** Claude Code 2.1.245, macOS 25.5.0, 2026-08-26. One headless
`claude -p` run under a `--settings` file whose only hooks append every payload they
receive to a file, wired on `PostToolUse` and on `PostToolUseFailure`, each with a group
matched on `Skill` and a second group carrying no matcher. The session was told to make
three calls in order: a real skill, a bogus skill name, and `Bash` with the command
`for(`. Exactly two payloads were captured. `PostToolUse` for the real skill, with
`tool_response: {"success":true,"commandName":"claim-provenance"}`, which proves the
`Skill`-matched success group was live. `PostToolUseFailure` for the Bash call, with
`tool_name: "Bash"`, no `tool_response` key at all, and instead
`error: "Exit code 1\n(eval):1: bad pattern: for("` plus `is_interrupt: false` — and since
no `Skill` matcher can match `Bash`, that delivery proves the matcher-less failure group
was live too. For the bogus skill: nothing, on either event, from either group.
**Remaining limits:** two `PostToolUse` groups matched the successful skill call and only
one delivery arrived, so this run cannot say which of the two produced it. And
`Unknown skill` is the only `Skill` failure mode that can be provoked on demand, so it is
the only one measured.

**Also measured, in the same run.** The `PostToolUse` payload for a `Skill` call carries
exactly these keys: `session_id`, `transcript_path`, `cwd`, `prompt_id`,
`permission_mode`, `effort`, `hook_event_name`, `tool_name`, `tool_input`,
`tool_response`, `tool_use_id`, `duration_ms`. There is **no `entrypoint`**, so a hook
that needs to know whether a person or a script was driving has to read it out of the
transcript the payload names. The skill's name arrives as `tool_input.skill`.
Separately, a `hooks.json` declaring `PostToolUseFailure` passes
`claude plugin validate --strict` on the same version, checked by validating a manifest
and that hooks file on their own in an otherwise empty directory.

**What it means.** A hook census of skill invocations is a census of *successful* ones.
An absence of failure rows is not evidence that nothing failed, and any consumer of such
rows has to say so where the number is read, not only where it is written. The
transcript's `is_error` flag stays the only dependable count of failures.

---

## A `Stop` hook is handed the closing message already extracted, and can block twice

**Finding.** The `Stop` payload carries exactly these keys: `session_id`,
`transcript_path`, `cwd`, `prompt_id`, `permission_mode`, `effort`, `hook_event_name`,
`stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`.
`last_assistant_message` is a plain string holding the whole final assistant text of the
turn, so a hook that judges what the turn said needs no transcript parsing to find it.

Two separate mechanisms stop the turn and they are not interchangeable.
`{"decision":"block","reason":"…"}` on stdout with status 0 reaches the model as a user
record marked `isMeta`, reading `Stop hook feedback:` followed by the reason. Text on
stderr with status 2 reaches the model too, but the CLI staples the script's absolute path
into it and renders it as a blocking *error* from a command, which reads to the model as a
malfunctioning tool rather than as a finding about the turn.

`stop_hook_active` is the loop flag, and `prompt_id` is what makes a per-turn budget
possible. Across one probe's three deliveries the flag went false, true, true: false on the
first `Stop` of a turn, true on any `Stop` that exists only because a `Stop` hook blocked
the previous one. All three deliveries carried an identical `prompt_id`, while the record
uuid changed every time.

**How established.** Claude Code 2.1.245, macOS 25.5.0, 2026-08-25. Probe hooks were wired
into a scratch project's `.claude/settings.json`, each appending its raw stdin to a log and
returning a chosen decision, driven by
`claude -p … --output-format stream-json --verbose`; the payload logs and the resulting
transcripts are the record. Both blocking mechanisms were exercised in turn and the
resulting transcript records compared.

**What it means.** Anything that gates the end of a turn should read
`last_assistant_message` and honour `stop_hook_active`, which is sufficient on its own as a
loop guard; disk counters are a backstop for its absence, not a substitute. Prefer the
stdout `block` form, because the stderr form's framing invites the model to treat a
deliberate refusal as a broken hook. And key a per-turn allowance on `prompt_id`:
`session_id` caps the whole session instead of the turn, and the record uuid caps nothing.

---

## A `PreToolUse` denial reaches the model as untrusted text, and is treated that way

**Finding.** A `PreToolUse` hook denies a call by emitting
`{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"…"}}`
on stdout with status 0. The call does not execute and the model reports the reason
verbatim. Its payload keys are `cwd`, `effort`, `hook_event_name`, `permission_mode`,
`prompt_id`, `session_id`, `tool_input`, `tool_name`, `tool_use_id`, `transcript_path`.

The part that changed how we write these: an instruction placed inside the reason was
explicitly refused. The model answered that it was not acting on an instruction embedded in
that message, because text coming back from a blocked call is not a directive it follows.
That is correct behaviour — tool-result text is untrusted input — and it is a constraint on
the author, not a defect.

**How established.** Claude Code 2.1.245, macOS 25.5.0, 2026-08-25, in the same probe
harness as the entry above: a denying hook wired on `PreToolUse`, a session told to run
`echo DENYME 999`, and the transcript read back for whether the command ran and what the
model did with the reason text.

**What it means.** Write a denial reason as a statement about what is wrong, never as a
command to run something — the imperative form is the one shape the model is right to
ignore. The `Stop` channel is different: its `reason` arrives labelled as hook feedback
rather than as tool output, and is acted on, so guidance is legitimate there. A hook that
gates both events needs two registers for the same finding.

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

## `claude -p` does load project skills; narrowing `--setting-sources` is what removes them

**Finding.** A headless `claude -p` started in a project directory can route that
project's `.claude/skills/` with no flag at all. Passing `--setting-sources
user,project,local` explicitly changes nothing. Passing `--setting-sources ''` is what
takes the pool away. So the flag does not switch project skills on; narrowing it switches
them off.

**How established.** Claude Code 2.1.245, macOS 25.5.0, 2026-08-25, on sonnet. A throwaway
project directory holding one control skill (`plimwax-nine`) whose description was the only
possible match for the prompt, then `claude -p` from that directory with
`--strict-mcp-config` and every built-in tool except `Skill` disallowed, so the skill
roster was the only place the name could have come from. Three arms: no flag (named the
control 3 of 3), `--setting-sources user,project,local` (named it 1 of 1), and
`--setting-sources ''` (answered NONE 3 of 3). **Remaining limit:** one model tier, one CLI
build, and a single control skill, so this establishes the direction of the flag and not a
map of every scope combination.

**What it means.** A headless run is a fair place to probe whether a project-scoped skill
routes, because by default it loads the pool the interactive session loads. The inverse is
the half that bites: `--setting-sources ''` is how a dispatched call is given no project or
personal skills, no plugins, no output styles and no `CLAUDE.md`, so a probe that narrows
the sources for isolation has silently taken away the skill it meant to measure.

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
