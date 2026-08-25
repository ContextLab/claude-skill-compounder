# Contributing a skill

This repo ships a seed pool of skills. A contribution is welcome when the skill has
already proven itself somewhere real. The review is cheap when the evidence arrives with
the pull request and expensive when it does not, so the requirements below are about
evidence, not ceremony.

## The bar

A proposed skill must clear **both** of these:

1. **A clean red-team result.** Run the `skill-compounder` forging loop. The final round
   has to come back clean from a red-teamer that was a fresh, cold agent, never a fork of
   the session that wrote the skill. A forked reviewer inherits the author's blindness and
   reports that the skill looks fine.
2. **Evidence of local reuse.** At least one invocation after the one that forged it,
   doing real work. A skill nobody has re-run is a prediction, not a capability.

One without the other is a reason to keep the skill local for now, not a reason to open a
pull request. Say so in the issue tracker if you want a second opinion on whether it is
ready.

## Before you open anything

Use the `contribute-skill` skill. It runs the steps below in order and stops for your
confirmation before any network write. If you would rather do it by hand, the same checks
are available directly:

```bash
skillcontrib preflight <path-to-skill-dir>     # frontmatter and size limits
skillcontrib whoami                            # maintainer path or fork path
skillcontrib dedup <skill-name> --description "<the description line>"
```

`skillcontrib` never writes anything to the network. It reads.

**Take the duplicate check seriously.** Exit code 3 means possible duplicates were found
and a human has to look. Exit 4 means the contribution already exists. Exit 5 means a
maintainer already declined an equivalent proposal, and reopening it without reading that
review first wastes everyone's time. The check reads GitHub's search index, which lags
pull request creation by a few minutes, so it can miss something opened moments ago.

## Skill format

Only the six portable frontmatter keys: `name`, `description`, `license`,
`compatibility`, `metadata`, `allowed-tools`. Custom keys do not survive outside Claude
Code, and a seed skill should.

- `description` is a trigger clause, at most 500 characters. Write it as "Use when …",
  and put the negative scope in the same sentence ("Do NOT use for …"). It is not a
  summary of the skill; it is the sentence that decides whether the skill fires.
- Frontmatter total at most 1024 characters.
- Body at most 500 lines. The median skill in the surveyed ecosystem is 200. Anything
  longer than that usually wants a bundled reference file instead.
- One skill does one thing. If the red-teamer says it is doing two, split it.

## Prose style

Plain declarative sentences. No em-dashes anywhere; use periods, colons, parentheses, or
semicolons, and vary the repair rather than swapping every dash for a colon. Avoid
"leverage", "robust", "seamless", "comprehensive", "delve", and "it's worth noting".

## Tests

Every test in this repo runs the real thing: real files, real scripts through
`subprocess`, real network calls where the behavior under test is a network behavior.
There are no mocks, and a contribution that adds one will be sent back. Where a test
needs determinism, pin it with an environment variable the script reads for exactly that
purpose, the way `SKILLFORGE_NOW` and `CI_NOW` already do. Where a test needs the network,
guard it with `unittest.skipUnless` so a token-less CI run still passes, and let it
genuinely hit the network when credentials are present.

```bash
./run_tests.sh
```

All of it has to pass, including the tests you did not touch.

## The pull request

Fill in `.github/PULL_REQUEST_TEMPLATE.md`. It asks for the red-team rounds and what they
found, the three prompts that must fire the skill and the three that must not, the
fixture you exercised it against, and where it has been reused. That is the whole review,
so a filled-in template usually gets a fast answer and an empty one gets questions.
