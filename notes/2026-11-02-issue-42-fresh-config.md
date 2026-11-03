# Issue #42: journeys under a fresh CLAUDE_CONFIG_DIR (2026-11-02)

Claude Code 2.1.317. Blocker was a credential for an unlogged-in config. The maintainer's
`anthropic-api-key` keychain item works: passed as `ANTHROPIC_API_KEY` for one command,
a fresh config answers a model turn. No token from `claude setup-token` was needed.

## Done

- `tests/journeys/common.py`: `--config fresh` (default) sets `CLAUDE_CONFIG_DIR=<root>/config`
  for every `claude` process and the judge; refuses to start without
  `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`. `--config ambient` = old behaviour.
  `common.parse(ap)` adds it to scripts with their own parser. `World.run_claude`,
  `session(installed=True)` (no `--plugin-dir`, `--setting-sources user,project`).
- `journey_marketplace.py`: marketplace add + install of a copy with a scratch
  `marketplace.json`; 13/13. Plugin root on a directory marketplace is the directory itself
  (not a cache copy); the mod calls `<root>/bin/compound`. Real `~/.claude` settings,
  installed_plugins, known_marketplaces unchanged (sha256).
- Fresh mode also passed: stop 12/12, skills 9/9, recall 23/23, capture 13/13, index 8/8.
- Fixed: capture, index, strengthen left their second world's root behind on success;
  `finish(keep, also=(w2,))`.

## Not done

- The marketplace route is still not shipped or documented for users: no
  `marketplace.json` in the repo (its name, owner and description are the maintainer's
  words), and a GitHub source (versioned cache copy) is untested.
- Not every journey was re-run in fresh mode (guard, general, evidence, compose, repeat,
  reuse, strengthen, unsettled, claims, error, measure_*, probe_injection).
