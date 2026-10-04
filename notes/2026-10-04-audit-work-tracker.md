# Audit work tracker (started 2026-10-04)

The owner said: do all six proposals from `2026-10-04-release-and-audit.md`, in the order
the session thinks best, and keep notes. Base commit for the work: `54340ba` on `main`.
Evidence for every item: `notes/2026-10-04-audit/`.

How it is run: each track is an agent in its own git worktree (the live mod loads from
the main checkout, so half-edited hooks must not sit there). The session merges each
branch into `main`, runs `./run_tests.sh`, `claude plugin validate --strict .` and
`claude plugin test .`, then pushes. Status is updated here after each merge.

## Wave 1 (parallel)

| Track | Proposal | Scope | Status |
|-|-|-|-|
| A | 1. trustworthy capture and guards | non-command failures dropped before the judge; guards match commands only, multi-line anchor; exit-0 shell errors count as failures; no recurrence after a guard refusal; verdicts logged with `ms` | MERGED (a1ddff4), notes in `2026-10-04-track-a-capture-guards.md` |
| B | 3. install and uninstall | curl-able uninstall; default to the newest release tag; `update` moves between tags; Claude Code version check; shadowed `compound` on PATH reported; marketplace route only if a real session shows the hooks load | MERGED (0dd8d4a), notes in `2026-10-04-track-b-install.md`; marketplace NOT shipped (tool-call and stop hooks unproven: the sandbox was not logged in) |
| C | 4. indicators | names instead of counts; totals line; once-per-session ready note; relative times; one vocabulary; pane at 40 columns; CLI text polish | MERGED (a31d48b, merge ba5d77b); renders in `2026-10-04-audit/track-c-renders.md`. README screenshots and demo.gif no longer match and are NOT re-recorded yet |

## Wave 2 (after wave 1 is merged)

| Track | Proposal | Scope | Status |
|-|-|-|-|
| D | 2. general pool | platform and shell condition on a lesson; a general lesson can be strengthened locally or switched off; ship the six drafts (four as guards) | MERGED (df69796, merge 509c35a); notes in `2026-10-04-track-d-general-pool.md` |
| E | 5. pane drill-down | open a lesson from the pane; settling command on Open rows; all-lessons view | dispatched on base ba5d77b |
| F | 6. reuse precision | rarity-weighted words; memo for repeated prompts; stemming in `find`; duplicate gate in `add` | dispatched |
| S | security review of a commit (arrived 2026-10-04 as a background notice; 4 findings, 2 named) | 1. a lesson's `name` is validated as a slug only at `add`/`promote`, not when a lesson file is loaded, and `hooks/render.ts` puts the name (and a project path) into commands it tells the model to run (`add --update --name <name>`, `COMPOUND_PROJECT=<from> ... promote <name>`): a lesson file committed in a repository can carry a hostile name. Confirmed by reading `bin/compound` (SLUG_RE used at 1377 and 1985 only) and `render.ts` 349-401. 2. a slow pattern in a project lesson can use up the 1.5 s guard budget so user guards go unchecked (`check` has `timed_out`/`unchecked`; what the mod does with them is to be read). 3-4. not named in the notice: run a fresh security review to find them. | dispatched on base after 509c35a. Third finding, from a second notice: untrusted tool output reaches the LLM judge (lesson poisoning) in `hooks/register.ts` |

## Wave 3 (from the open-issue audit, 2026-10-04)

The owner asked for the open issues to be audited: anything relevant goes on this list,
the rest is closed with a comment. #30, #31, #34 closed (they track the implementation
removed in `88a6c3e`). #19 and #42 stay open, each restated against the rewrite.

| Track | From | Scope | Status |
|-|-|-|-|
| G1 | #19 point 4 | a `use` event when a skill made from a lesson (or any recorded skill) is invoked, with its notice on the band and its count in `status` and the pane | waits on F (same reuse path in `register.ts`) |
| G2 | #19 point 1 | notice a repeated request (the same procedure asked for several times, from the prompt log) and propose making it a skill | waits on F |
| G3 | #19 point 3 | a skill in the shipped pool that composes other skills. Which skill is a product choice: ASK THE OWNER | not started |
| H | #30 | after some weeks of ordinary use, a sweep of the log: capture to lesson / skip / unsettled rates, guard refusals corrected vs re-sent, recall precision, reuse relevance. A `compound` report that prints them | not started; needs elapsed time for the data, the report can be built now |
| I | #42 | a credential for sessions in a throwaway `CLAUDE_CONFIG_DIR` (`claude setup-token`, `CLAUDE_CODE_OAUTH_TOKEN`), then prove the marketplace install route and run the journeys fully isolated. ONLY THE OWNER can create the token | blocked on the owner |

## Not to do without the owner

- Any text that states policy for the project (what belongs in the general pool, in
  CONTRIBUTING or README): draft it and ask.
- Rewriting the owner's own user lessons in `~/.claude/compound/lessons`.
- Running `install`, `uninstall` or `update` against the real `~/.claude`.

## Log

- 2026-10-04: tracker written, wave 1 dispatched.
- 2026-10-04: a background security review of a commit reported 4 findings; track S added.
- 2026-10-04: tracks A and B merged, all checks green; released v0.4.1 (the installer on main
  installs the newest tag, and v0.4.0's update fails on a tag). Public install, update and
  piped uninstall run in a sandbox against v0.4.1.
- 2026-10-04: a second security notice: untrusted tool output reaches the LLM judge
  (persistent lesson poisoning) in `hooks/register.ts`. Given to track S.
- 2026-10-04: wave 2 tracks D, F, S dispatched on base v0.4.1. C still running; E waits on C.
- Left by track A for the owner: three `compound add --update --match` commands for the
  owner's guards (in the track A notes), and an unanchored pattern still hits
  `grep -n '; git commit' file`.
- 2026-10-04: track C merged (conflicts with A in view.ts, register.ts imports, design.md
  command table; the `judge` event got its display word `judged`). All checks green: 13
  test files, 171 plugin tests. Track E dispatched. Running now: D, E, F. Held: S.
- Still to do after the tracks: re-record README screenshots and demo.gif (dev/demo.sh,
  dev/ui-check.sh); decide with the owner on the stand-in `claude` executables in track
  B's version tests (no-mocks rule); final release.
- 2026-10-04: a third security notice, after the track C merge: prompt injection through
  unvalidated persisted state reaching the model's context, in `hooks/register.ts`. No
  detail given. For track S: trace every value read back from `$.state`, the claims, the
  event log and the store that ends up in text added to a prompt or a stop message.
- 2026-10-04: track D merged, all checks green (14 test files, 173 plugin tests).
  The merge was done in the main checkout and its conflict markers broke the live mod for
  a few minutes (guard checks failed with SyntaxError). Recorded as project lesson
  `merge-in-a-scratch-worktree`: remaining merges are done in a scratch worktree and
  fast-forwarded.
- 2026-10-04: open issues audited; wave 3 added above. Track S dispatched. Running: E, F, S.
