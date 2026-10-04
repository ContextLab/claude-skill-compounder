# compound: install / update / uninstall audit

Date: 2026-10-04. Audit only; no repo file was edited. Every run used a sandbox under
the session scratchpad (`$S`), with `--claude-dir`, `--bin-dir`, `COMPOUND_HOME`,
`COMPOUND_CLAUDE_DIR` and `COMPOUND_NO_SURFER=1`; piped runs also had `HOME=$S/<n>`.
The history-surfer step was not exercised. `$REPO` = `/Users/jmanning/claude-skill-compounder`.

Environment: macOS (Darwin 25.6.0), `/usr/bin/python3` 3.9.6, anaconda python 3.9.13,
`claude --version` -> `2.1.289 (Claude Code)`.

Note on versions: while the audit ran, `origin/main` moved to `c5d913c Release 0.4.0`
and tag `v0.4.0` appeared (release published 2026-10-04T17:01:01Z). The local checkout
is behind it (HEAD `4ef77dd`, with `plugin.json` locally modified to 0.4.0 by someone
else). Piped runs below cloned the remote, so they tested `c5d913c`. `install.sh` on
the remote is byte-identical to the local one.

## 1. Transcripts (trimmed)

### A. Fresh install, twice, status, uninstall, reinstall, purge (local checkout)

```
$ python3 $REPO/bin/compound install --claude-dir $S/a/claude --bin-dir $S/a/bin
compound installed from $REPO
  mod      enabled: added $REPO to env.CLAUDE_CODE_PLUGIN_DIRS in $S/a/claude/settings.json
  cli      linked $S/a/bin/compound
  cli      $S/a/bin is not on PATH. Add this line to your shell profile (~/.zshrc for zsh, ~/.bashrc for bash) and open a new shell:
               export PATH="$S/a/bin:$PATH"
  prompts  history-surfer skipped: COMPOUND_NO_SURFER is set
  record   $S/a/home/install.json
Check it with: $S/a/bin/compound status
[exit 0]

settings.json: { "env": { "CLAUDE_CODE_PLUGIN_DIRS": "$REPO" } }

$ (same command again)
  mod      already enabled in $S/a/claude/settings.json
  cli      $S/a/bin/compound already links here
  ...                                              [exit 0]   -> idempotent

$ $S/a/bin/compound status          (bin first on PATH)
Health
  PASS  python          3.9.13
  PASS  mod             enabled in $S/a/claude/settings.json
  WARN  mod last fired  never: the event log holds no event the mod wrote (reuse, guard, recall, capture, remind, refuse, nudge, error)
  PASS  cli             $S/a/bin/compound
  PASS  prompt log      131 prompts in this project
  WARN  last event      no events yet in $S/a/home/events.jsonl
  PASS  duplicates      every name exists once
  PASS  lessons parse   every lesson reads
  PASS  errors          none in the last 7 days

$ $S/a/bin/compound uninstall --claude-dir $S/a/claude
mod      removed $S/a/claude/settings.json, which install had created
cli      removed $S/a/bin/compound
record   removed $S/a/home/install.json
kept     $S/a/home (your lessons and the event log; --purge removes them)
[exit 0]
(left behind: empty $S/a/bin and $S/a/claude directories)

$ uninstall again
no install record at $S/a/home/install.json; nothing to reverse
kept     $S/a/home (your lessons and the event log; --purge removes them)   [exit 0]

$ reinstall -> same output as the fresh install                              [exit 0]

$ $S/a/bin/compound uninstall --claude-dir $S/a/claude --purge
mod      removed $S/a/claude/settings.json, which install had created
cli      removed $S/a/bin/compound
record   removed $S/a/home/install.json
purged   $S/a/home (user lessons, the event log)                             [exit 0]
```

### B. settings.json with unrelated content and another plugin dir

Install appended: `"CLAUDE_CODE_PLUGIN_DIRS": "/some/other/plugin:$REPO"`; `model`,
`env.FOO`, `permissions` kept (file re-indented to 2 spaces). Uninstall restored
`"/some/other/plugin"` and kept everything else. Correct.

### C. Malformed settings.json

```
compound: $S/c/claude/settings.json is not valid JSON (Expecting property name enclosed in double quotes: line 1 column 18 (char 17)); it was left untouched. Fix it and run again
[exit 1]      (nothing else was created; file untouched)
```
A file with a `//` comment is refused the same way.

### D. A foreign `compound` already in the bin dir

```
compound: $S/d/bin/compound exists and is not a link to this package; it was left alone. Remove it or pass --bin-dir
[exit 1]      (nothing was written)
```

### W. A foreign `compound` EARLIER on PATH, in a different directory

```
compound installed from $REPO
  mod      enabled: ...
  cli      linked $S/w/.local/bin/compound
  prompts  ...
Check it with: $S/w/.local/bin/compound status
[exit 0]
```
Install says nothing about the shadowing program; only `status` would
(`WARN cli  `compound` on PATH is ..., not this package's`).

### P. The real flow: `cat install.sh | bash -s -- ...` with a sandboxed HOME, `~/.local/bin` absent

```
cloning https://github.com/ContextLab/claude-skill-compounder.git (main) to $S/p/.claude/compound/app
compound installed from $S/p/.claude/compound/app
  mod      enabled: added $S/p/.claude/compound/app to env.CLAUDE_CODE_PLUGIN_DIRS in $S/p/.claude/settings.json
  cli      linked $S/p/.local/bin/compound
  cli      $S/p/.local/bin is not on PATH. Add this line to your shell profile (~/.zshrc for zsh, ~/.bashrc for bash) and open a new shell:
               export PATH="$HOME/.local/bin:$PATH"
  prompts  history-surfer skipped: COMPOUND_NO_SURFER is set
  record   $S/p/.claude/compound/install.json
Check it with: $S/p/.local/bin/compound status
[exit 0]

$ PATH=/usr/bin:/bin compound status
bash: compound: command not found                     <- what README's "compound status" gives this user

$ PATH=/usr/bin:/bin $S/p/.local/bin/compound status
  PASS  python          3.9.6
  PASS  mod             enabled in $S/p/.claude/settings.json
  WARN  mod last fired  never: ...
  WARN  cli             $S/p/.local/bin/compound is linked, and $S/p/.local/bin is not on PATH. Add this line to your shell profile: export PATH="$HOME/.local/bin:$PATH"
  WARN  prompt log      history-surfer's `surfer` is not on PATH; reuse checks see no earlier prompts
  WARN  last event      no events yet in ...
  -> four WARN rows on a correct fresh install

$ piped again           -> "updating .../app (main)", everything "already"    [exit 0]
$ compound update       -> "already up to date at c5d913c"                    [exit 0]
$ compound uninstall
  ...
  kept     $S/p/.claude/compound (your lessons and the event log; --purge removes them)
  kept     $S/p/.claude/compound/app (the package clone; --purge removes it)
  -> `compound` is now gone from the bin dir; the output does not say how to purge later
$ piped again after uninstall -> reinstalls from the kept clone               [exit 0]
$ compound uninstall --purge  -> "purged ... (user lessons, the event log and the package clone)"
```

Purging later, after a plain uninstall, works only by the clone path (verified):
```
$ python3 $S/t4/.claude/compound/app/bin/compound uninstall --claude-dir ... --purge
no install record at .../install.json; nothing to reverse
purged   $S/t4/.claude/compound (user lessons, the event log and the package clone)
```

### T. Pinned to a tag

```
$ COMPOUND_REF=v0.4.0 ... | bash
cloning ... (v0.4.0) to .../app
warning: refs/tags/v0.4.0 1dfab59... is not a commit!
Note: switching to 'c5d913c...'.
You are in 'detached HEAD' state. You can look around, ... (12 more lines of git advice)
compound installed from .../app                                               [exit 0]
$ rerun pinned -> "updating ... (v0.4.0)", fine                               [exit 0]
$ compound update
compound: .../app is on a detached HEAD (at c5d913c), not on a branch, so there is nothing to pull; check out a branch there (git -C .../app switch main) and run update again
[exit 1]
$ rerun unpinned -> moves the clone back to main                              [exit 0]

$ COMPOUND_REF=v0.3.1 ... | bash
install.sh: .../app has no bin/compound (is v0.3.1 the right branch?)         [exit 1]
(the clone is left at .../app; a rerun with the same ref fails the same way)
```
`v0.3.0` and `v0.3.1` predate the rewrite and carry no `bin/compound`.

### G / N / X / truncation

```
no git on PATH:       install.sh: git is required to fetch the package        [exit 1]
empty PATH:           install.sh: git is required to fetch the package        [exit 1]
                      (python was "found" through the hard-coded /usr/bin/python3 candidate)
app dir not a clone:  install.sh: .../app exists and is not a git checkout; move it away and run again  [exit 1]
first 900 bytes only: bash: line 25: syntax error: unexpected end of file from `{' command on line 10   [exit 2]
                      (nothing created: the { } wrapper works as a partial-download guard)
```

### URL

```
$ curl -fsSI https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh
HTTP/2 200
content-type: text/plain; charset=utf-8
```
Body is identical to the local `install.sh` and ends with `}\n`.

### Claude Code plugin system (sandboxed with `CLAUDE_CONFIG_DIR=$S/cfg`)

Real `~/.claude/plugins/installed_plugins.json`, `known_marketplaces.json` and
`~/.claude/settings.json` had identical md5 before and after.

Scratch clone of the remote + a new `.claude-plugin/marketplace.json`:
```json
{ "name": "contextlab", "owner": { "name": "..." },
  "plugins": [ { "name": "compound", "source": "./", "description": "..." } ] }
```
```
$ claude plugin validate <clone>
  ❯ description: No marketplace description provided. ...
✔ Validation passed with warnings          (--strict fails on that one warning)

$ claude plugin marketplace add <clone>
✔ Successfully added marketplace: contextlab (declared in user settings)
$ claude plugin install compound@contextlab
✔ Successfully installed plugin: compound@contextlab (scope: user)

installed_plugins.json: installPath .../cfg/plugins/cache/contextlab/compound/0.4.0, version 0.4.0, gitCommitSha c5d913c...
settings.json: extraKnownMarketplaces.contextlab + enabledPlugins {"compound@contextlab": true}
cache dir holds the whole repo, including bin/, hooks/, tests/, notes/, docs/ (no .git)

$ claude plugin details compound
Component inventory
  Skills (2)  learn, reuse
  Agents (0)
  Hooks (0)            <- the function-hook module is not counted here
  ...

$ claude plugin list     (with CLAUDE_CODE_PLUGIN_DIRS also set, as after install.sh)
  compound@contextlab ... enabled
Session-only plugins (--plugin-dir / --plugin-url):
  ❯ compound@inline  Path: /Users/jmanning/claude-skill-compounder  Status: ✔ loaded
  -> both routes at once = the plugin is present twice

$ python3 <cache>/bin/compound status
  WARN  mod   .../settings.json does not exist; run `compound install` (or the package is loaded as a plugin)
  WARN  cli   `compound` is not on PATH; the mod cannot call it by name
$ python3 <cache>/bin/compound update
compound: <cache> is not a git checkout: fatal: not a git repository ...

$ claude plugin uninstall compound@contextlab   -> ✔ Successfully uninstalled
$ claude plugin marketplace remove contextlab   -> ✔ Successfully removed
```

`claude plugin --help` lists `install`, `uninstall`, `update`, `marketplace add|list|remove|update`,
`validate`, `tag` ("Create a {name}--v{version} git tag for a plugin release"), `test [dir]` ("Run a mod's tests").
`marketplace add <source>`: "Add a marketplace from a URL, path, or GitHub repo".

Docs (https://code.claude.com/docs/en/plugins-reference, fetched 2026-10-04), word for word:
- "Executables | `bin/` | Files here are on the Bash tool's `PATH` while the plugin is enabled, so Claude runs them as bare commands. claude.ai and Cowork don't install a plugin that has this directory"
- "`version` ... Setting it keeps users on that version until you change it"
- "`types` | Path | A `.d.ts` file that declares the `$.state` values and `$` nouns of a mod"

## 2. Answers to the six questions

1. **Curl-able uninstall.** There is none. `install.sh` ends with
   `exec "$python" "$app/bin/compound" install "$@"` (install.sh:54) and README:78 gives
   only `compound uninstall`. For a user whose `~/.local/bin` is not on PATH that
   command fails with `command not found` (verified in P). After a plain uninstall the
   link is gone and nothing prints how to purge later. There should be one: proposal 1.
2. **Plugin system.** Verified: a `marketplace.json` validates, `claude plugin
   marketplace add` + `claude plugin install compound@<name>` succeed from a shell,
   the copy lands in a versioned cache with `bin/` present, and uninstall is clean.
   Verified in code: the mod prefers its own CLI,
   ``const own = `${$.plugin.root}/bin/compound` `` (hooks/register.ts:159), falling back
   to `COMPOUND_BIN`, then `compound` on PATH (register.ts:164). Verified in docs: a
   plugin's `bin/` is on the Bash tool's PATH (Claude's shell calls), not the user's
   terminal. Inferred: `$.plugin.root` is the cache path, so the mod finds its CLI.
   I don't know: whether a function-hook module is loaded at all from a marketplace
   install (`details` shows "Hooks (0)", and I did not start a session against the
   sandbox config), or whether early access gates it. What would have to change is in
   proposal 5.
3. **URL.** Resolves, HTTP 200, same bytes as the local file.
4. **Unpinned main.** A concern: every push to `main` is live for the next
   `curl | bash` and `compound update`, and `COMPOUND_REF` is documented as a branch
   (install.sh:6 "branch to install when fetching (default main)"). A tag installs but
   `compound update` then exits 1 (transcript T). See proposal 3.
5. **Security/robustness.** Good: `{ ... }` wrapper stops a truncated download
   (verified), `set -eu`, variables quoted, `git ... || die`, a foreign `compound` in
   the bin dir is refused before anything is written, malformed settings are never
   overwritten, install rolls back. Gaps: no check that python is >= 3.9 before
   running; a `compound` earlier on PATH is not mentioned at install (W); a failed ref
   leaves the clone behind; nothing is pinned or verified (main HEAD is executed);
   `/usr/bin/python3` is accepted by `command -v` even where it is Apple's
   install-the-developer-tools stub (inferred, not reproduced).
6. **Post-install.** The installer's last line is `Check it with: <path> status`
   (bin/compound:2687). Nothing in `bin/compound` says to start a new session (grep for
   "restart|new session" finds nothing); only README:29 does. `compound status` is the
   doctor. On a correct fresh install with `~/.local/bin` off PATH and no surfer it
   shows four WARN rows; README:70 says "The two `WARN` rows are expected on a new
   install", so the screen reads as broken to someone who did not read that sentence.
   Nothing checks the Claude Code version: "2.1.288" appears only at README:31.

## 3. Proposals, ranked

### 1. A curl-able uninstall (and an uninstall that says what is left) — S

(a) Observed: README:78 `| uninstall and keep everything you recorded | `compound uninstall` |`;
P transcript: `bash: compound: command not found`. After plain uninstall:
`kept     .../compound/app (the package clone; --purge removes it)` with no command to run.
(b) `install.sh` takes a first word: `install` (default), `uninstall`, `update`, and
passes the rest through. It finds the CLI at `$COMPOUND_HOME/app/bin/compound`, else the
`package` in `install.json`, and never clones for uninstall.
```
curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh | bash -s -- uninstall
curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh | bash -s -- uninstall --purge
```
Plain uninstall ends with the exact later-purge and reinstall commands, and one line:
"Open Claude Code sessions keep the mod until they are restarted."
(c) S. `install.sh`, `bin/compound` (uninstall report), README, `docs/design.md`,
`tests/test_install.py`.
(d) Not verified: what an already-open session does when `--purge` deletes the clone
its hooks were loaded from.

### 2. A "what now" ending for install, and a calm first `status` — S

(a) Observed: last line `Check it with: $S/p/.local/bin/compound status`; no restart
hint; fresh status prints `WARN  mod last fired  never: the event log holds no event the
mod wrote (reuse, guard, recall, capture, remind, refuse, nudge, error)` and
`WARN  last event      no events yet in ...`.
(b) Install ends with numbered next steps: 1. the one copyable PATH command for the
user's shell (`echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc`), only when
needed; 2. "Start a new Claude Code session (open ones do not load the mod)";
3. "Type /compound there, or run `<full path> status`". In `status`, when
`install.json` is younger than the newest mod event could be (no mod event yet), the two
rows read as a neutral state, e.g. `NEW   mod last fired  not yet: start a new Claude
Code session`, instead of WARN. Install also warns when `shutil.which("compound")` is a
different program (case W).
(c) S. `bin/compound` (`cmd_install` report, `build_status` rows), README sample output
and Troubleshooting table, `docs/design.md` health table, tests.
(d) Whether a new row state fits the mod's pane (`hooks/view.ts` reads the status
JSON); not checked.

### 3. Install the latest release, and let `update` move between releases — M

(a) Observed: install.sh:17 `ref="${COMPOUND_REF:-main}"`; with a tag,
`compound: ... is on a detached HEAD (at c5d913c), not on a branch, so there is nothing
to pull` [exit 1], plus 14 lines of git detached-HEAD advice during install.
(b) Default ref = newest `v*` tag >= 0.4.0 from `git ls-remote --tags --sort=-v:refname`
(fall back to `main` when none); clone with `-c advice.detachedHead=false`. `compound
update` on a detached HEAD at a tag fetches tags and checks out the newest; on a branch
it keeps pulling. `compound update --ref main` for people who want the tip. One-liner is
unchanged; a pin is:
```
curl -fsSL https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/v0.4.0/install.sh | COMPOUND_REF=v0.4.0 bash
```
(c) M. `install.sh`, `cmd_update`, README, `docs/design.md` (COMPOUND_REF row says
"branch"), tests.
(d) `git ls-remote --sort` needs git >= 2.18; not tested on an old git. Tags v0.3.x
have no `bin/compound` and must be excluded (verified they fail).

### 4. Check the Claude Code version at install and in status — S

(a) Observed: README:31 "**Requirements:** Claude Code 2.1.288 or later"; `grep -rn
"2\.1\.288"` over the repo finds that line only. On an older Claude Code install would
print `PASS mod enabled` and nothing would ever happen.
(b) `install` and `status` run `claude --version` (prints `2.1.289 (Claude Code)` here)
with a short timeout: a `claude code` health row, FAIL below 2.1.288 with "update with:
claude update", WARN "claude is not on PATH" otherwise. Same place: `install.sh` checks
`python3 -c 'import sys; sys.exit(sys.version_info < (3,9))'` before cloning.
(c) S. `bin/compound`, `install.sh`, README table, `docs/design.md`, tests.
(d) I did not test against an older Claude Code or an older python; what an old Claude
Code does with `CLAUDE_CODE_PLUGIN_DIRS` and a `modules` hooks file is unknown to me.

### 5. A marketplace route as a second install path — M/L, with an open question

(a) Observed: no `.claude-plugin/marketplace.json` in the repo; install edits
`env.CLAUDE_CODE_PLUGIN_DIRS` by hand. In the sandbox the plugin route installed and
uninstalled cleanly (transcript above).
(b) Add `.claude-plugin/marketplace.json` (name, owner and description are the owner's
call; they are public statements). The user types:
```
claude plugin marketplace add ContextLab/claude-skill-compounder && claude plugin install compound@<marketplace-name>
claude plugin uninstall compound@<marketplace-name>
```
or `/plugin marketplace add ContextLab/claude-skill-compounder` inside a session.
What must change for it to be whole: `status` mod row must recognise a plugin install
(today: `WARN ... run `compound install``); `compound update` must say "run `claude
plugin update compound@...`" instead of `is not a git checkout`; the user's terminal
gets no `compound` (docs: `bin/` is on the Bash tool's PATH only), so a `compound
install --link-only` or a printed alias is needed; history-surfer is not fetched; a
guard against both routes at once (verified they coexist as `compound@contextlab` and
`compound@inline`); the cache copies `tests/`, `notes/`, `docs/`, `dev/`.
(c) M for the manifest + docs + status/update messages; L with link-only and the
double-load guard. `.claude-plugin/marketplace.json`, `bin/compound`, README,
`docs/design.md`, tests, CI (`claude plugin validate --strict .` currently wants a
marketplace description).
(d) I don't know whether a function-hook mod loads from a marketplace install on
2.1.289: `claude plugin details` reported "Hooks (0)" and I did not run a session
against the sandbox config. The GitHub-shorthand `add ContextLab/...` form was read from
`--help` ("a URL, path, or GitHub repo"), tested only with a local path. Until a real
session confirms the mod fires, this should stay behind proposal 1-4.

### 6. State the supported platforms — S

(a) Observed: `grep -i "windows|wsl|linux|macos"` over README, design.md and guide.md
finds no platform statement. The installer is bash, the link is `os.symlink`, the PATH
advice names `~/.zshrc`/`~/.bashrc`.
(b) One Requirements line (owner's wording) saying which of macOS, Linux, WSL and
native Windows are supported, and `install.sh` dying early with a clear line on an
unsupported `uname`.
(c) S. README, `install.sh`.
(d) Nothing here was run on Linux, WSL or Windows.

## 4. Outright bugs

1. `COMPOUND_REF` set to a release tag installs, then `compound update` exits 1
   ("detached HEAD"), and install prints git's full detached-HEAD advice. Tags are the
   only way to pin.
2. A ref without `bin/compound` (v0.3.0, v0.3.1) fails after cloning and leaves
   `$COMPOUND_HOME/app` behind; `install.sh` reports "(is v0.3.1 the right branch?)".
3. The Claude Code minimum (README:31, 2.1.288) is enforced nowhere.
4. Install never tells the user to start a new session; only README does.
5. Install is silent when another `compound` earlier on PATH shadows the new link.
6. README:70 says "The two `WARN` rows are expected"; a user without `~/.local/bin` on
   PATH and without surfer sees four.
7. Uninstall leaves the empty bin and Claude directories install created (cosmetic).
8. `install.sh` does not check the python version; `/usr/bin/python3` is taken on sight.

## 5. Not verified

- The history-surfer install/uninstall step (skipped by design of this audit).
- Any behaviour inside a live Claude Code session (mod loading, open sessions, purge
  under a running session).
- Linux, WSL, Windows, python < 3.9, Claude Code < 2.1.288, a Mac without developer tools.
