# 2026-08-25 (later) — implementing the whole roadmap

Follows `2026-08-25-roadmap-session.md`, which produced the research and issues #2 to #6.
This session implemented all of them on branch `roadmap-issues-2-6`.

## Shape of the work

Seven builder agents in parallel, partitioned by **file ownership** so they could not
clobber each other in one checkout. That partition held: no agent touched another's files,
and the only collision all session was `run_tests.sh` being rewritten underneath a running
agent (by the orchestrator, mid-suite), which made bash re-read the script and replay the
loop. That is the exact hazard `parallel-agents-one-codebase` exists to prevent, and it
happened anyway because the orchestrator exempted itself from its own partition.

Then cold red-team agents, one per artifact, never forks of the orchestrating session.

## What shipped

|Issue|What landed|
|-|-|
|#5|`.claude-plugin/plugin.json`, `hooks/hooks.json`, CI on ubuntu and macos plus `claude plugin validate --strict`|
|#3|Four seed skills, each with a fixture that fails when the skill's prescription is wrong|
|#6|Forge ledger in `skillforge`, usage rollup in `skillreport`|
|#4|`hooks/insight-capture.sh` and `bin/skillinsight`, with the classifier deliberately not shipped|
|#2|`contribute-skill`, `bin/skillcontrib`, `CONTRIBUTING.md`, a PR template|

## Findings that cost real time, and would cost it again

**Both install paths fire every hook.** With the installer's `settings.json` entries and
the plugin both active, one `Write` delivered `PostToolUse` twice. Nothing errors;
`CI_EDIT_EVERY=12` just silently becomes 6. Found by dumping payloads, not by reading code.
Fixed with `claim_once()`, which claims an event by `.prompt_id` / `.tool_use_id` using
`mkdir` (atomic, so two racing processes cannot both win).

**A root `CLAUDE.md` fails `claude plugin validate --strict`.** The warning says it will not
load as plugin context; `--strict` promotes warnings to errors, and `--strict` is what
marketplace review runs. Moved to `.claude/CLAUDE.md`, which was verified to still load as
project context by putting a token in it and asking a headless session to read it back.

**`${text//[[:space:]]/}` is quadratic on bash 3.2.** Over the roughly 60 KB blob a bounded
transcript read returns, it spun at 100% CPU for minutes with no child processes, which is
what wedged the suite twice. `/usr/bin/env bash` on macOS is 3.2, so this is not exotic. The
fix is a `case *[![:space:]]*` glob. `run_tests.sh` now caps each file with a `perl alarm`
so a hang fails loudly instead of reading as "still running".

**`gh pr list --search` answers `[]` with exit status 0 for a repo that does not exist.** A
typo in the repo name therefore reads as "no duplicate found". `skillcontrib` resolves the
repo with `gh repo view` first, which 404s properly.

**Unmatched globs are fatal in zsh, and `set -- $counts` yields one field there.** Both hit
while testing `skillreport` under both shells.

## Things measured rather than asserted

- The universal-versus-local classifier scored **7/14, chance**, so it is not shipped.
  Kernel extraction replaced it.
- `no-silent-stub`'s scan: precision 1.00, recall 0.89 on the author's fixture. The miss is
  a fallback with no syntactic tell, pinned by a test rather than deleted from the fixture.
- `skillreport` recovered 127 real skill invocations from this machine's transcripts.

## Still open

- ~~**The `destructive-op-preflight` ship gate.**~~ **Measured.** 18 real headless trials,
  9 with the skill and 9 without, against prompts engineered to tempt a `reset --hard`.
  Manifest written before acting: 9/9 with, 2/9 without. It clears the 90% bar, so it ships
  as a skill rather than a deny-hook. Two caveats recorded in the README: the untracked file
  survived 18/18 in **both** arms, so in this fixture the skill prevented no actual loss and
  what it changed was manifest discipline; and the baseline is inflated because no isolated
  environment was reachable (auth is keychain-bound to the default config directory), so all
  18 trials ran with about 120 other skills loaded. The one #34327-style hallucinated
  safeguard occurred in the baseline arm: a reported backup path that did not exist, 52
  seconds off the real one.
- **The four threshold constants** (>15 min, >=2 occurrences, 12 edits, 20 min) are still
  guesses. `skillreport` is the instrument; the data needs elapsed time and installs in other
  repos. Do not tune them before then.
- **Queue growth over a real week** (#4) and **usage across 3+ repos** (#6) both need
  calendar time, not more code.
- `references/servers-and-images.md` in `stale-artifact-check` is the one body of text in the
  seed pool whose commands are not verified by a test, because they need a daemon or a remote
  host. It was moved out of the SKILL.md body for exactly that reason.
