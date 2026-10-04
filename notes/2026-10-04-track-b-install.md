# Track B: install, update, uninstall (2026-10-04)

Base `792bb47`. Work on the worktree branch `worktree-agent-a2678074667e81560`; not pushed.

## Done

1. `install.sh` takes `install` (default) or `uninstall` as its first word. Uninstall finds
   the package through the install record, then `<COMPOUND_HOME>/app`, then the checkout the
   script sits in, and never clones.
2. No `COMPOUND_REF`: the newest tag `vX.Y.Z` >= 0.4.0 (sorted in python, not by git),
   else `main`. `compound update` on a detached HEAD moves to the newest release;
   `compound update --ref REF` moves to a branch or tag. The clone is made with
   `--no-checkout` and then checked out, because `git clone --branch <annotated tag>`
   prints "warning: refs/tags/v0.4.0 ... is not a commit!" (seen against the real repo).
3. `CLAUDE_CODE_MIN` in `bin/compound`; `claude code` health row; a `claude` line at install.
4. Install names another `compound` that comes first on PATH.
5. `dirs_created` in the install record; uninstall `rmdir`s the empty ones.
6. README **Platforms** paragraph.

## To do after merging

- Tag a release that contains this work. The newest release today is `v0.4.0`, whose
  `compound update` still exits 1 on a tag, and the installer now puts people on it. Until
  a newer tag exists, running the installer again is what moves a release install forward.
- The public one-liners fetch `install.sh` from `main`: the piped uninstall works for
  others only once this is on `main`.

## Known limit

- Plain uninstall removes the install record, so a later `--purge` no longer knows which
  directories install created. `~/.local/bin` is handled at the plain uninstall; a
  `~/.claude` that install itself created stays behind, empty, after the later purge.

## Marketplace route: investigated, not shipped

Sandbox: `CLAUDE_CONFIG_DIR=<scratch>/cfg`, a copy of the package with a scratch
`.claude-plugin/marketplace.json` (`"source": "./"`), `COMPOUND_HOME` and
`COMPOUND_CLAUDE_DIR` in the scratch directory, `CLAUDE_CODE_PLUGIN_DIRS=""`. The real
`~/.claude/settings.json`, `installed_plugins.json` and `known_marketplaces.json` had the
same md5 before and after.

Observed (Claude Code 2.1.289):

- `claude plugin marketplace add <dir>` and `claude plugin install compound@scratch-mkt`
  succeed. `settings.json` gets `extraKnownMarketplaces` (source `directory`) and
  `enabledPlugins`. `installed_plugins.json` names a cache path, but the session's `init`
  message lists the plugin with `path` = the marketplace directory itself, source
  `compound@scratch-mkt`. `claude plugin details compound` prints "Hooks (0)".
- A real `claude -p` process with that config, no `--plugin-dir`: the function-hook
  module loaded and its prompt hook ran. Evidence: a `claims/<session id>/unsettled` file
  under the scratch `COMPOUND_HOME`, and, with an unsettled capture seeded, a `remind`
  event in the scratch event log carrying that session's id. A control run with an empty
  config and `--plugin-dir` wrote the same.
- The sandbox config is not logged in ("Not logged in · Please run /login"), so no model
  turn ran. The `tool.call` hooks (guard, recall, capture) and the stop hook were not
  exercised on this route. I did not copy credentials into the sandbox.
- `claude plugin marketplace add file:///...` is refused ("Try: owner/repo, https://...,
  or ./path"), so the GitHub or https source, which is what a user would type and which
  loads from the versioned cache, could not be tested without the manifest on the remote.
- Which `compound` the mod called on this route was not determined.

Not added, because it is not proven: no model turn on the route, and the GitHub source
untested. Still open if it is taken up: the marketplace's name, owner and description
(the owner's words), no `compound` on the user's terminal PATH, `status` and `update` for
a cache copy, both routes at once (`compound@<marketplace>` and `compound@inline`).
