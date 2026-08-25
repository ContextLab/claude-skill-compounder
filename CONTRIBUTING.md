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
skillcontrib preflight <path-to-skill-dir>              # does it load and is it addressable
skillcontrib whoami --repo <owner>/<repo>               # maintainer path or fork path
skillcontrib dedup <skill-name> --repo <owner>/<repo> \
  --description "<the description line>"
```

Pass `--repo` every time. It defaults to this repo, and a duplicate check aimed at the
wrong repo answers "clean" for free.

`skillcontrib` never writes anything to the network. It reads.

**Take the duplicate check seriously.** Exit 9 means the skill already exists in the
upstream tree. Exit 4 means an equivalent contribution is already open or merged. Exit 5
means a pull request that added this skill was closed without merging, which may be a
rejection or a revision the author superseded: read it before deciding. Exit 3 means
possible duplicates were found and a human has to look. Exit 19 means the upstream tree
listing was truncated, so a clean result cannot be certified and you have to check by hand. The pull request probes read
GitHub's search index, which lags creation by a few minutes, so they can miss something
opened moments ago.

## Skill format

**What is actually checked.** `skillcontrib preflight <skill-dir>` enforces four things,
and they are the four that stop a skill from working: `SKILL.md` exists, the frontmatter
parses with a real YAML parser (PyYAML, or ruby's psych as a fallback), `name` matches the
directory name, and `description` is present and non-empty (a skill without one never
fires). Claude Code addresses a skill by its directory, so a mismatch makes it
unreachable. Everything in the rest of this section is review guidance, weighed by a human,
not a gate.

An earlier version of the checker also enforced key portability and length limits. Measured
against the 156 skills installed on one developer machine it hard-failed 46 of them,
including four shipped by Anthropic, while an independent parse found 0 of 156 unparseable.
Those checks were removed rather than re-tuned, because none of them is what a contribution
is gated on. Please do not add them back to the gate.

**Quote the description** when it contains a colon followed by a space, or use a YAML block
scalar. An unquoted `: ` inside a plain scalar makes the frontmatter fail to parse, after
which the skill loads with empty metadata and silently never fires. CI runs
`claude plugin validate --strict`, which catches it.

Review guidance, with where each number comes from:

|Guidance|Value|Basis|
|-|-|-|
|`description`|Aim under 500 chars; 1024 is the cap the upstream skills repo validates against (anthropics/skills #1635)|29 of 156 installed skills exceed 500, so it is a target, not a rule|
|Frontmatter total|Under 1024 chars|Measured truncation of `description` plus `when_to_use` starts at 1536|
|Body|Aim near 200 lines, under 500|Median of 105 surveyed skills is 200; 86% are under 500, and the ones above it are reference-heavy|
|Frontmatter keys|Prefer `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`|Only these are portable outside Claude Code. Others work in Claude Code and 44 installed skills use them|

`description` is a trigger clause, not a summary: write it as "Use when …" and put the
negative scope in the same sentence ("Do NOT use for …"). It is the sentence that decides
whether the skill fires. One skill does one thing; if the red-teamer says it is doing two,
split it.

Everything else in the skill directory travels with it. `scripts/`, `references/`,
`examples/`, and `LICENSE.txt` are part of the contribution, so copy the directory, not
just the `SKILL.md`.

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
