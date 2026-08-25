## What this skill does

One or two sentences. What procedure does it crystallize, and what did getting it right
cost the first time?

## Red-team evidence (required)

Rounds run: <!-- e.g. 2 -->

Each round used a fresh cold agent, not a fork of the authoring session: <!-- yes / no -->

What the rounds found, and what changed in response:

- Round 1:
- Round 2:
- Final round came back clean: <!-- yes / no -->

## Trigger precision (required)

Three prompts that MUST fire this skill's `description`:

1.
2.
3.

Three related prompts that must NOT fire it:

1.
2.
3.

## Fixture (required)

What did you actually run the skill against? Name the repo, file, or task, and what the
skill produced.

## Local reuse (required)

Where has this been used since it was forged? At least one later invocation doing real
work, with a sentence on what it did.

## Duplicate check

Output of `skillcontrib dedup <skill-name> --description "<description>"`. It probes the
upstream tree, then every pull request in any state, then description overlap:

```
paste the output, including sub-threshold fuzzy rows
```

Exit code: <!-- 0, or 3/4/5/9 with an explanation of why this is not a duplicate -->

## Checklist

- [ ] `skillcontrib preflight <skill-dir>` passes, warnings included or explained
- [ ] Only the six portable frontmatter keys, and the description is quoted
- [ ] Every file in the skill directory is included, not only `SKILL.md`
- [ ] `description` is a "Use when …" clause with the negative scope, at most 500 chars
- [ ] Body at most 500 lines, or a reason it needs more
- [ ] `./run_tests.sh` passes in full
- [ ] No mocks, no em-dashes
