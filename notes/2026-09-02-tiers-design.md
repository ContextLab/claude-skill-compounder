# 2026-09-02 — Tier 0 and Tier 1: the note and the reminder

Design for the two cheap compounding tiers named in `notes/2026-09-02-audit-and-replan.md`. Everything below is decided; an implementer needs no further choices. Baselines read at `HEAD` (ee7cef5). Issues: #20 (skillnote), #21 (reminders), #23 (promotion).

## Why these two exist

The audit's diagnosis: one output path (the forge, median 3.3h, 8 agents), and the cheapest forms of compounding have no mechanism at all. `skills/skill-compounder/SKILL.md` says "write a note or update the project's `CLAUDE.md`" and names no path, no CLI and no ledger row; it has been taken zero times. Two paid `CANDIDATE` verdicts produced no artifact. The one thing that both accumulates and fires is the repeat store — content-addressed signatures matched on `PreToolUse`, no model, two integers on disk. Tier 0 and Tier 1 copy that shape.

## What is NOT being built

No model calls anywhere in either tier. No fuzzy matching: keyword matching is lowercase substring containment, path matching is shell globs, command matching is byte equality of a normalised signature. No new state formats: JSONL and a marker block in an existing markdown file. No rewriting of an append-only store from a hook.

---

# TIER 0 — `bin/skillnote`

## CLI

```
skillnote add   --scope project|global|memory "<text>"
                [--why <text>] [--source session|verdict|forge]
                [--project <dir>] [--remind]
                [--keyword <k>]... [--path <glob>]... [--command "<literal cmd>"]...
skillnote list  [--scope project|global|memory|remind] [--json]
skillnote remove <id>
skillnote --help
```

Exit codes follow `bin/skillforge`: `0` success (and success includes "already recorded"), `2` bad argv or a refusal the caller can fix, `3` an environment the caller must fix (the memory slug does not exist).

Refusals, each naming its cause:

- `--remind` with none of `--keyword/--path/--command` → exit 2. A reminder with no match rule never fires and is invisible; that is worse than a note.
- `--remind --scope memory` → exit 2. A memory file is not a reminder store.
- an unknown `--scope` → exit 2, naming the three.
- `add` with empty text → exit 2.

`--project <dir>` sets the project root explicitly instead of inferring it from `$PWD`. This is not a convenience: `hooks/session-review.sh` runs detached, after the session ended, from an unknown working directory, and it is one of the three callers.

## Where each scope writes

**project** → `<project root>/.claude/CLAUDE.md`. Project root is `git rev-parse --show-toplevel` falling back to `$PWD`, the same shape `project_root()` uses in `bin/skillforge`. `.claude/` is created if absent. Deliberately `.claude/CLAUDE.md` and never a root `CLAUDE.md` — a root one fails `claude plugin validate --strict`, which is why this repo's own lives there.

**global** → `<claude dir>/CLAUDE.md`, resolved in the same order as `skills_dest()` in `bin/skillforge` (`bin/skillforge:1159-1166`): `$SKILLNOTE_CLAUDE_DIR`, then `.claude_dir` from `<state>/install-manifest.json`, then `${CLAUDE_CONFIG_DIR:-$HOME/.claude}`. Two resolutions of "where is the Claude directory" that disagree is exactly the drift `skills_dest` was written to avoid.

**memory** → `${SKILL_COMPOUNDER_TRANSCRIPTS:-$HOME/.claude/projects}/<slug>/memory/<name>.md`, plus one index line appended to `MEMORY.md` in that directory.

`<slug>` is the project root with every `/` replaced by `-`. Measured on this machine 2026-09-02: `/Users/jmanning/claude-skill-compounder` → `-Users-jmanning-claude-skill-compounder`; `/private/tmp/claude-501/-Users-.../scratchpad/x` → `-private-tmp-claude-501--Users-...-scratchpad-x` (the doubled `-` comes from a path segment that itself begins with `-`, which confirms the transform is a plain substitution and not a sanitiser). **No path containing a dot or a space was observed**, so the transform for those is unknown. Therefore: if `<transcripts>/<slug>/` does not already exist, `skillnote` refuses with exit 3 and writes nothing, naming the slug it computed. Creating a directory Claude Code will never read is worse than refusing.

The frontmatter is Claude Code's format, not ours. Read from `/Users/jmanning/.claude/projects/-Users-jmanning-claude-skill-compounder/memory/move-fast-everything-on-main.md`:

```
---
name: <kebab-case-name>
description: "<one line, quoted>"
metadata:
  node_type: memory
  type: project
  originSessionId: <CLAUDE_CODE_SESSION_ID, omitted when unset>
  modified: <ISO-8601 with milliseconds and a Z>
---

<body>
```

`MEMORY.md` indexes them one line each, in this exact shape:

```
- [Move fast, everything on main](move-fast-everything-on-main.md) — no PR ceremony until the prototype has outside users
```

Em dash, not a hyphen. `skillnote` appends one such line and dedups on the `(<filename>.md)` substring. The file name is derived from the note text: lowercase, non-alphanumerics to `-`, runs collapsed, trimmed, capped at 60 characters; `--why` becomes the `description` and the index line's tail.

**This frontmatter is platform behavior and belongs in `docs/CLAUDE-CODE-BEHAVIOR.md`**, with the CLI version it was read on and the command that reads it back — that file's standing rule. Two things there are unmeasured and must be stated as unmeasured rather than promised: whether Claude Code loads `MEMORY.md` automatically, and whether it re-reads a memory file we wrote without its involvement. Until both are measured, the README must not claim the memory scope gets read back.

## Marker block format

One block per file, ever. Idempotent.

```markdown
<!-- skillnote:begin -->
## Notes (skill-compounder)

- **2026-09-02** Kill the runner and re-run the full suite; a filtered re-run hides a cross-file failure. <!-- id:n2847193021x84 source:verdict -->
- **2026-09-02** Check which tests pin a skill's prose before editing it. <!-- id:n1993847712x61 source:session why:"three edits reverted by test_seed_*" -->
<!-- skillnote:end -->
```

Rules:

- If `skillnote:begin` is absent, the block is appended at end of file, preceded by a blank line. If present, the new line is inserted immediately before `skillnote:end`. Never a second block; `add` finds the **first** `skillnote:begin` and refuses (exit 2) if a second one exists, naming both line numbers — a file with two blocks is a merge accident and guessing which to append to loses notes.
- The id lives in a trailing HTML comment so it renders as nothing and greps as a fixed string. `remove <id>` deletes the single line whose comment contains `id:<id>` and touches nothing else, including a user's own prose inside the block.
- `--why`, when given, is appended into the comment as `why:"..."` (quotes escaped), not into the visible line. The line stays one readable sentence.
- Date is `%Y-%m-%d` in local time from the clock below.

**The id.** `id="n$(printf '%s' "$scope|$text" | cksum | awk '{printf "%sx%s", $1, $2}')"` — CRC-32 and byte length, the identical idiom as `hashof()` in `hooks/repeat-gate.sh:520`. Consequences, all wanted: the same text at the same scope always produces the same id, so a second `add` is a no-op that exits 0, prints `skillnote: already recorded (<id>)` and writes **no** ledger row (the same dedup-by-hash stance as `queue_record` in `hooks/insight-capture.sh`); and an id is stable across machines, so a note committed into a repo's `.claude/CLAUDE.md` can be removed from any checkout.

## Backup, atomic write, through-symlink

Identical discipline to `skill_compounder/installer.py`'s `settings.json` handling, reimplemented in shell because `skillnote` is shell + `jq` like the other five CLIs. The four rules, and where each comes from:

1. **Resolve the link, write through it.** `_real_settings_path` (`installer.py:140-155`): stow/chezmoi present the file as a symlink into a dotfiles repo, and renaming onto the link deletes it and orphans the source with exit 0 and no warning. Shell version: loop `readlink` (resolving a relative target against the link's directory) with a 40-iteration cap so a symlink loop cannot hang the CLI.
2. **Back up beside the *configured* path, not the resolved one.** `backup_settings` (`installer.py:192-229`). A symlinked `CLAUDE.md` must not sprinkle `.bak-` files through someone's dotfiles git repo. Name: `<path>.bak-skill-compounder-<YYYYmmdd-HHMMSS>`, `BACKUP_PREFIX` matching the installer's. Skip when the newest existing backup is byte-identical (`cmp -s`), so repeated `add`s do not accumulate copies. Second-resolution stamps collide, so a `-2`, `-3` suffix is added rather than clobbering the pre-change copy. Prune to the newest 10, and only files matching our own prefix.
3. **Write atomically, on the same filesystem.** `write_settings` (`installer.py:231-254`). `mktemp` in the *resolved* file's directory (so `mv` is a `rename(2)` and not a copy), write, `chmod` to the existing file's mode or `0600` for a new one, `mv -f`. A `trap` removes the temp on every failure path. A unique temp name per writer: a fixed one lets two concurrent runs interleave bytes and rename the result into place.
4. **Never truncate in place.** A half-written `CLAUDE.md` is silently worse than none.

`skillnote` gets the shell versions of these as four small functions with a comment pointing at the Python originals. Both implementations now exist and must not drift; `.claude/CLAUDE.md` gains a sentence saying so.

## Ledger row

Appended to `${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}/ledger.jsonl`:

```json
{"event":"note","action":"add","ts":1756838400,"id":"n2847193021x84","kind":"note","scope":"project","target":"/Users/j/proj/.claude/CLAUDE.md","text":"...","why":"...","source":"verdict","project":"/Users/j/proj","session":"<CLAUDE_CODE_SESSION_ID>","confidence":"measured","backfilled":false}
```

`kind` is `"note"` or `"reminder"` (Tier 1 writes the same event). `action` is `"add"`, `"remove"` or `"promote"`. Empty optional fields are omitted, the way `ledger_line()` omits them (`bin/skillforge:617-634`).

**Why a new event breaks nothing.** `.claude/CLAUDE.md`: *"The ledger is append-only, and every reader selects its events BY NAME... Add an event type freely; never widen a selector to a negation."* `note` is invisible to every existing selector. `tests/test_ledger_v2.py` already pins both readers against a mixed ledger; add a `note` row to that fixture so the invariant is proved rather than assumed.

**The horizon row.** `ledger_ensure_horizon()` runs before every `skillforge` append and states where the record begins; a ledger whose first row is a `note` with no horizon reads as "complete from here", which is false. Rather than duplicate that function, **add a `skillforge horizon` subcommand**: a four-line case arm that calls `ledger_ensure_horizon` and exits 0. `skillnote` runs it before its append when `skillforge` is executable (found beside `$0`, then on `PATH`); when it is not found, `skillnote` appends anyway, because a note is worth more than a horizon row.

## Clock

`SKILLNOTE_NOW`, epoch seconds, guarded digits-only exactly as `bin/skillforge` guards `SKILLFORGE_NOW` (`bin/skillforge:195-200`). Falls back to `date +%s`. A new script needs its own clock; pinning someone else's does nothing to it.

## Who calls it

**1. The cheap branch of `skills/skill-compounder/SKILL.md`.** The sentence today is *"In any of those, write a note or update the project's `CLAUDE.md`."* — no path, no CLI, no row, taken zero times in ten days. It becomes a command:

```bash
skillnote add --scope project "<the one-line lesson>" --why "<the dead end, in one sentence>" --source forge
# with a trigger, so it arrives instead of waiting to be read:
skillnote add --remind --scope project "<the lesson>" --keyword <k> --command "<the call>" --source forge
```

Wrap it in a `<!-- doctrine: cheap-branch -->` marker so `tests/test_doctrine_sync.py` pins the same words across `SKILL.md`, `README.md` and the installer's global stanza.

**2. `hooks/session-review.sh`, on a `CANDIDATE` verdict.** The write point is `emit_index_and_unread()` (`hooks/session-review.sh:461-484`) — the function that writes the `index.jsonl` row and the `.unread` line, called both on the normal path and from the `EXIT` trap, guarded by `STAGE1_FLUSHED` so it runs once. After the `.unread` append, when `$ei_verdict` is `CANDIDATE` and `$ei_name` is non-empty:

```bash
[ -x "$SKILLNOTE_BIN" ] && "$SKILLNOTE_BIN" add --scope project --project "$PROJECT" \
  --source verdict "session review: candidate '$ei_name'" \
  --why "see $ei_report" >/dev/null 2>&1 || true
```

`--project "$PROJECT"` because the script is detached and its `$PWD` means nothing. Non-fatal on every path. No recursion risk — `skillnote` makes no model call. Idempotent twice over: the flush guard, and `skillnote`'s own id dedup.

**3. `skillinsight promote <hash> --to note|reminder`.** New subcommand in `bin/skillinsight`. It reads the queued record, takes `.text` (first line, whitespace squeezed, capped at 200 characters) and `.project`, calls `skillnote add --source session --project <record .project>`, then appends `{"hash":...,"ts":...,"to":"note","id":"<the note id>"}` to `$DIR/.promoted.jsonl`.

A **dotfile**, for the reason `.declined.jsonl` is one (`bin/skillinsight:167-172`): `all_files()`, `prune` and the capture hook's dedup all glob `*.jsonl`, and a promote record carries a `"hash":"..."` string, so a non-dotted name would make promoting a candidate silently blocklist its hash in the capture hook.

`pending` must treat promoted hashes exactly like declined ones — extend `declined_json()` to a `judged_json()` that unions both files, and have `list` mark them `[promoted]` alongside `[declined]`. `--to reminder` requires at least one `--keyword/--path/--command` and passes them straight through; **it does not derive keywords from the record's prose**.

---

# TIER 1 — the reminder store and its injection hook

## Store

`<state>/reminders.jsonl`, append-only.

```json
{"id":"n1993847712x61","text":"Kill the runner and re-run the full suite; a filtered re-run hides a cross-file failure.","match":{"keywords":["test","fail"],"paths":["tests/*.py"],"commands":["Bash\n./run_tests.sh"]},"scope":"/Users/j/proj","created":1756838400,"source":"verdict","hits":0}
```

- `scope` is an absolute project root or the literal string `global`.
- `keywords[]` are lowercased at write time.
- `paths[]` are shell globs, matched with `case`.
- `commands[]` are **normalised signatures**, not literal commands (see below).
- Removal is a **tombstone**, never a rewrite: `{"id":"...","t":"remove","ts":...}` appended to the same file, and every reader skips an id with a later tombstone. Same doctrine as `skillrepeat forget`. This differs from a `CLAUDE.md` note, which `remove` deletes outright, because that file is human-edited prose. Document the asymmetry.

**Name collision, deliberate and worth a comment.** `<state>/reminders/` is already the directory `hooks/compound-improvement.sh` keeps its per-session counters in (`compound-improvement.sh:87`), and its `prune_stale_state()` sweeps inside it. `reminders.jsonl` is a *sibling* of that directory, not inside it, so the sweep cannot reach it — pin with a test.

## `hooks/remind.sh`

**Shape**, all of it copied from the scripts that already work:

- One brace group opened after `set -uo pipefail`, closing `}` as the last line, and a bare `exit` as the last statement inside it. `tests/test_script_wrapping.py` is a ratchet.
- `: "${HOME:=/tmp}"` before anything reads `HOME`.
- `payload="$(cat)"`, then `command -v jq >/dev/null 2>&1 || exit 0`.
- `ROOT="${SKILL_COMPOUNDER_STATE:-$HOME/.claude/skill-compounder}"`.
- **Exit 0 on every failure path** and emit nothing.
- Clock `REMIND_NOW`, digits-guarded, falling back to `date +%s`.
- Off switch `SKILL_COMPOUNDER_REMIND=0`.
- Dispatches on `.hook_event_name` and takes **no argv** — the `claim-gate.sh` / `repeat-gate.sh` pattern.

**Idempotence per event**, the `claim_once()` shape from `compound-improvement.sh:126-146`: `mkdir` a marker under `<state>/remind/<sid>.seen/<mode>-<id>` keyed on `.tool_use_id // .prompt_id`; fail **open**; an event with no usable id is always acted on. The session id is sanitised with the **identical** expression every other script uses — `tr -c 'A-Za-z0-9._-' '_' | cut -c1-96`.

## Matching

**Scope first.** A row whose `scope` is not `global` is considered only when the payload's `.cwd` equals that scope or is a subdirectory of it.

**UserPromptSubmit** — lowercase `.prompt`; a row matches when **every** keyword in `match.keywords` is a substring of it. AND, not OR. A row with an empty `keywords` array never matches a prompt.

**PreToolUse, `.tool_name == "Bash"`** — compute the normalised signature of `.tool_input.command` and match on **byte equality** against any entry in `match.commands`.

The normaliser is **not reimplemented**. **Add `--norm-of <tool>` to `hooks/repeat-gate.sh`**: reads a command on stdin, prints `norm`, writes nothing to the store, exits. Precedent: `--verdict-of` in `hooks/session-review.sh:319-322`. `remind.sh` and `skillnote --remind --command` both call it. If `repeat-gate.sh` is absent, `remind.sh` skips command matching entirely.

**PreToolUse, `.tool_name` is `Write` or `Edit`** — take `.tool_input.file_path` and match each glob in `match.paths` with `case`, against both the absolute path and the path relative to the row's `scope`.

## Ranking, cap, cooldown

**Cap** `REMIND_MAX`, default **2**. **Ranking**: score = `100` if a command signature matched, `+50` if a path glob matched, `+10 × (number of keywords in the row)`. Ties break on fewer live hits first, then newer `created`.

**Cooldown**, per reminder per session. Stamp file `<state>/remind/<sid>/<id>` holding the epoch it last fired. `REMIND_COOLDOWN` default `0` means *once per session, ever*; a positive value re-arms after that many seconds, compared on `|now - stamp|`. A file whose contents are read with `cat`, not a directory mtime (BSD/GNU `stat` disagree).

**The stamp is written before the emit** and the emit is abandoned if the stamp cannot be written.

## Hits

The hook **never rewrites `reminders.jsonl`**. It appends `{"id":"...","ts":...,"session":"...","event":"UserPromptSubmit"}` to `<state>/remind/hits.jsonl`. The live count is derived by `skillnote list` counting that log.

## Emission shape — measure before wiring

`UserPromptSubmit` carries `additionalContext`; established. **`PreToolUse` carrying `additionalContext` is not established.** Every `PreToolUse` hook in this repo emits `{decision:"block", reason}` or nothing.

So: a measurement spike **before** the PreToolUse arm is wired. Run a probe hook under `claude -p --output-format stream-json`, emit `{suppressOutput:true, hookSpecificOutput:{hookEventName:"PreToolUse", additionalContext:"<token>"}}`, and read the transcript back for the token. Record in `docs/CLAUDE-CODE-BEHAVIOR.md`. If it does not reach the model, the fallback is `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"<the reminder>"}}`. Pick after measuring.

`remind.sh` never sets `systemMessage` and never denies anything.

## Cost

Per event: one `cat`, one `jq` for payload fields, one `jq` for selection, one `jq` for the emit, plus on Bash one fork of `repeat-gate.sh --norm-of`. Target under 100 ms. `REMIND_MAX_ROWS` default `2000`; read the last 2000 lines when longer.

## Both wirings

**One** `PreToolUse` entry, matcher `Bash|Write|Edit`, dispatching on `.tool_name` inside the script.

Installer (`skill_compounder/installer.py`):

- `REMIND_MARKER = "remind.sh"`, `REMIND_MATCHER = "Bash|Write|Edit"`.
- `merge_hooks`: strip `REMIND_MARKER` from `UserPromptSubmit` and `PreToolUse` **before** anything is appended, then append behind `_has_gate(app_home, "remind.sh")`.
- `OUR_EVENT_MARKERS` gains `REMIND_MARKER` under both events.
- Watch the `_pre_wired or pre or "PreToolUse" in hooks` guard: `_strip_marker` returns a **new** list (`installer.py:557-566`).

`hooks/hooks.json` gains the same two entries with `${CLAUDE_PLUGIN_ROOT}` paths and `timeout: 10`.

**Order is load-bearing.** `tests/test_plugin.py` compares matcher lists **positionally**: `UserPromptSubmit` = [compound-improvement `prompt`, remind]; `PreToolUse` = [claim-gate `Bash`, doc-gate `Bash`, repeat-gate `Bash|Skill`, remind `Bash|Write|Edit`].

New totals: **fourteen hook entries over eight scripts**, still five events.

---

# Promotion path

`queue → note → reminder → skill`, one tier per step, recurrence counted the way the repeat store counts it (distinct sessions).

- `skillinsight promote <hash> --to note` → `skillnote add`, `.promoted.jsonl` record, hash stops appearing in `pending`.
- `skillinsight promote <hash> --to reminder` → `skillnote add --remind`, requires an explicit match rule.
- note → reminder: different id (different store), so the two coexist.
- reminder → skill: unchanged. Nothing in the queue is ever forged automatically.

---

# Tests

Every test writes real files, runs the real scripts through `subprocess` with a minimal `PATH` and `HOME` in a temp directory, pins clocks, and reads results back off disk. **No mocks.** Every call against a hook passes `input=`.

**`tests/test_skillnote.py`** (new): one marker block ever, second block refused; same text twice → one line, no second ledger row; stable id, `remove` exact; backup naming/dedup/prune (10, own prefix only); through-symlink (link survives, target holds block, backup beside the link); atomic (no temp left after failure); global resolution order; memory scope writes measured frontmatter + one index line, refuses exit 3 when slug dir absent; ledger rows incl. horizon; refusals; `SKILLNOTE_NOW` pins date and ts.

**`tests/test_remind.py`** (new): keyword AND semantics; command arm proves shared normaliser (`gh issue comment 19 --body "x"` fires for `gh issue comment 4271 --body "y"`, not for `gh pr list`); path arm; scope; cap+ranking names which two; cooldown incl. re-arm; double delivery → one emit, one hits row; fail-open on every path; tombstoned row never fires; 500-row store under 300 ms.

**Extend**: `test_hook.py` (prune never touches sibling `reminders.jsonl`); `test_ledger_v2.py` (a `note` row, counts unchanged); `test_plugin.py` (named both-paths assertion); `test_installer.py` (remind entries install/idempotent/uninstall, user's own survive, checkout without remind.sh installs); `test_repeat_gate.py` (`--norm-of` matches learn arm, writes nothing); `test_insights.py` (promote); `test_doctrine_sync.py` (`cheap-branch` marker); `test_script_wrapping.py` (passes).

---

# `.claude/CLAUDE.md` constraints to update

Each is a **counted claim**; re-derive from code.

1. "five CLIs" → "six CLIs" (two places), adding `skillnote`.
2. "twelve hook entries" → "fourteen"; "twelve entries over seven scripts" → "fourteen entries over eight scripts"; "seven of the eight scripts" → "eight of the nine".
3. "nine clocks" → "eleven clocks", adding `SKILLNOTE_NOW` and `REMIND_NOW`; **the derivation grep must gain `SKILLNOTE` and `REMIND`** (third occasion of the documented narrow-grep defect if forgotten).
4. Ledger paragraph: add `note` to the events invisible to the join.
5. Marker paragraph: `REMIND_MARKER`; the backup/atomic/through-symlink discipline now has two implementations that must not drift.
6. New short paragraph naming the three tiers and where each writes.
7. "The reminder hook does key per session" → name `compound-improvement.sh` explicitly, since `remind.sh` now exists.

# `README.md` sections to add

- What gets installed: `bin/skillnote`, `hooks/remind.sh` rows.
- New section after "The three habits": **"Three ways to compound: note, reminder, skill"** (four-column table; command shapes; promotion path; unmeasured memory read-back stated).
- "The three habits" §2 gets the cheap-branch command under the doctrine marker.
- Tuning table: `REMIND_MAX`, `REMIND_COOLDOWN`, `REMIND_MAX_ROWS`, `SKILL_COMPOUNDER_REMIND`; the "twenty-five environment variables" count and its grep.
- Capturing candidates: `skillinsight promote`.
- Ledger: the `note` row.

# Sequencing

- **W2a — `skillnote`.** `bin/skillnote`, `skillforge horizon`, the `SKILL.md` cheap branch, the `session-review.sh` call site, `tests/test_skillnote.py`, `test_ledger_v2.py` fixture.
- **W2b — measurement spike.** Does `PreToolUse` deliver `additionalContext`? Result into `docs/CLAUDE-CODE-BEHAVIOR.md`. Parallel with W2a.
- **W2c — the reminder.** Depends on W2a and W2b.
- **W2d — promotion.** Depends on W2a.
- **W2e — documentation.** Last.

# Named risks

1. `PreToolUse` + `additionalContext` is unverified. Measure before wiring.
2. Memory-scope read-back is unverified. Say so; do not promise it.
3. Slug transform measured only for paths with no dots or spaces. Refuse on unknown slug.
4. `REMIND_MAX=2` and once-per-session cooldown are guesses; do not tune before hit counts exist.

## Correction, 2026-09-02 evening

The example row above shows `commands: ["Bash\n./run_tests.sh"]`. The shipped form is the
bare output of `hooks/repeat-gate.sh --norm-of Bash` (no tool prefix), because that is what
`hooks/remind.sh` compares. A real headless run found the prefixed form silent; the writer
now stores the bare signature and `tests/test_remind.py::WriterReaderTest` drives both halves.
