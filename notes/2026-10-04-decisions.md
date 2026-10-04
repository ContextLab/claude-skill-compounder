# 2026-10-04: design decisions, settled with codex as second reviewer

The owner asked for the open decisions to be settled by this session together with codex
(`codex exec -s read-only`, codex-cli 0.160.0). Codex's answer, unedited, is in
`2026-10-04-decisions-codex-answer.md`. Where the two reviewers differ it is said.

| # | Question | Decision | Agreed? |
|-|-|-|-|
| D1 | which guard wins when a general and another guard match one call | No guard yields. Every guard that matches is quoted in the one refusal. A user who keeps their own lesson for a mistake switches the general one off with `compound disable NAME`. | Partly. Codex: a user-declared "this lesson replaces that general one", else quote both. This session: `disable` already is that declaration, so no new key. Codex's point that today a matching user guard hides every general guard, related or not (`bin/compound` 3232-3238), is the bug this removes. |
| D2 | a project lesson with the name of a user or general one | Keep: shadowed, not in force. No per-repository override, no rename on load. | yes |
| D3 | a lesson directory that is not a slug or differs from its name | Keep: reported and unused. | yes |
| D4 | `promote --to general --yes` and credential-like text | Keep the refusal with no override. | yes |
| D5 | `compound log` accepts a forged `learn` or `skip` | `log` accepts only the types the mod writes. `learn`, `skip`, `rm`, `skill`, `promote` are written only by their own commands. Tests seed a log through a helper in `tests/` that refuses a store that is not a sandbox. Not a defence against a same-user process, which can edit the file; the design says so. | yes |
| D6 | a Bash command naming `compound` skips the guards | Exempt only a call that is one simple `compound ...` invocation: no `;`, `&&`, `\|`, substitution, backticks, subshell or newline outside a here-document body. Anything else is checked as usual. Today any simple command naming the CLI exempts the whole call, and also skips recall and capture (`hooks/render.ts` 212-218). | yes |
| D7 | the shipped `timeout` guard on macOS fires when Homebrew's `timeout` exists | Recall only: `macos-gnu-only-commands` loses its pattern. No PATH condition is added. | yes |
| D8 | parallel failures make a lesson ineffective | At most one recall per lesson, per revision of the lesson, per session counts toward ineffective. Every recall is still logged. The CLI decides whether a recall counts; the mod stops predicting it. | yes |
| D9 | a flaky command that passes on an identical retry | Not a fix; nothing is owed; the held failure is closed as recovered. A retry after a call that plausibly changed the circumstances may still be a fix if the judge is shown that call. | yes; given to the agent fixing the judge |

Also raised by codex, and adopted:

- `promote --to general` scans attachments only to 1 MiB and ignores read errors, then
  copies whole files: scan a frozen staging tree in full, publish those bytes, refuse what
  cannot be read.
- One `learn` or `skip` settles every earlier capture of its session: with more than one
  unsettled capture in the session, `--settles ID` is required and the stop message gives
  the ids.
- Recurrence is counted by lesson name alone: count by level and path, so two project
  lessons of one name in different repositories do not share a count.

For the owner's own store (not run): with D1, `zsh-equals-word`, `zsh-nomatch-glob` and
`macos-no-timeout` sit beside the shipped lessons on the same mistakes. To keep only your
own: `compound disable zsh-equals-not-found`, `compound disable zsh-no-matches-found`,
`compound disable macos-gnu-only-commands`.
