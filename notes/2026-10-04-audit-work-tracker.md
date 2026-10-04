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
| A | 1. trustworthy capture and guards | non-command failures dropped before the judge; guards match commands only, multi-line anchor; exit-0 shell errors count as failures; no recurrence after a guard refusal; verdicts logged with `ms` | dispatched |
| B | 3. install and uninstall | curl-able uninstall; default to the newest release tag; `update` moves between tags; Claude Code version check; shadowed `compound` on PATH reported; marketplace route only if a real session shows the hooks load | dispatched |
| C | 4. indicators | names instead of counts; totals line; once-per-session ready note; relative times; one vocabulary; pane at 40 columns; CLI text polish | dispatched |

## Wave 2 (after wave 1 is merged)

| Track | Proposal | Scope | Status |
|-|-|-|-|
| D | 2. general pool | platform and shell condition on a lesson; a general lesson can be strengthened locally or switched off; ship the six drafts (four as guards) | waiting on A |
| E | 5. pane drill-down | open a lesson from the pane; settling command on Open rows; all-lessons view | waiting on C |
| F | 6. reuse precision | rarity-weighted words; memo for repeated prompts; stemming in `find`; duplicate gate in `add` | waiting on A |

## Not to do without the owner

- Any text that states policy for the project (what belongs in the general pool, in
  CONTRIBUTING or README): draft it and ask.
- Rewriting the owner's own user lessons in `~/.claude/compound/lessons`.
- Running `install`, `uninstall` or `update` against the real `~/.claude`.

## Log

- 2026-10-04: tracker written, wave 1 dispatched.
