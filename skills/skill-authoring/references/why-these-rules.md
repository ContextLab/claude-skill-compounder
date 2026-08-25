# Why these rules

Overflow from `../SKILL.md`. Nothing here is a step; it is the evidence behind steps that
otherwise read as arbitrary.

## Why the validator is not a gate

`claude plugin validate --strict` checks that a `---` block exists and that a `description:`
line is present. Probed on claude 2.1.245: a plugin whose only skill carried an unquoted
colon printed `✔ Validation passed`, exit 0. So did a non-portable key, and so did a `name:`
disagreeing with the directory. Only a missing frontmatter block (`No frontmatter block
found`, exit 1) and a missing `description:` line failed — the two defects nobody makes.
Two third-party packaging scripts behaved the same way on the same file: both reported the
colon-broken skill valid and one packaged it into a distributable zip.

## Why the description gets dropped, and what that costs

The skill listing is budgeted at roughly 1% of the context window, and descriptions are dropped
least-invoked-first when it overflows. Observable: several `huggingface-skills` entries appear
in a live listing as bare names, while their on-disk SKILL.md files carry full, valid,
parseable descriptions. For `stale-artifact-check` that is survivable; for `hf-mem` it is
total. Padding is not free insurance either: a longer description is dropped sooner.

## Why an unquoted colon is a portability rule, not a load-failure rule

An earlier version of this repository's doctrine claimed that an unquoted `: ` makes Claude
Code load the skill with empty metadata. Re-probed on claude 2.1.245 in both the plugin and
the project path, that does not reproduce: the description came back verbatim, colon and all.
The rule still stands, on narrower and firmer ground.
`yaml.safe_load` raises `ScannerError` on it, so the file is rejected by the Agent Skills
spec validator, by the claude.ai upload, and by this repository's own suite. Quote it for
portability, not because your CLI will choke. The distinction matters twice over: a skill
that teaches an unreproducible mechanism gets disbelieved wholesale the first time a reader
tests a claim and it holds up fine. Claim only what the reader can re-run.

## Why the quoting rule has no "unless"

The colon is the loud half. The quiet half is `#`, and it is worse, because nothing raises.
Measured on python 3.9.13: the frontmatter line `description: Use when a run is tagged
#urgent and needs triage. Do NOT use for ordinary runs, that is another skill entirely
here.` parses to the 24-character string `Use when a run is tagged`. The decline half is
gone, the skill still lists, and the version of Gate A that only tested for a colon printed
`GATE A PASS: hash-demo | description 24 chars`. So the gate now rejects a bare scalar
outright rather than testing for the characters an author happened to use today.

## Why the sweep needs `-L`

`find` does not descend a symlink without `-L`, and installers put skill directories into
`~/.claude/skills` as symlinks, so a sweep without it reports a smaller population than exists,
and reports it as a clean result. How much smaller is a property of the machine, not of the
rule, so no total is stated here. The mechanism reproduces anywhere, with nothing installed:

```bash
d=$(mktemp -d); mkdir -p "$d/root/real" "$d/away/linked"
printf -- '---\nname: n\n---\n' | tee "$d"/root/real/SKILL.md "$d"/away/linked/SKILL.md >/dev/null
ln -s "$d/away/linked" "$d/root/linked"
echo "without -L: $(find "$d/root" -name SKILL.md | wc -l | tr -d ' ')"
echo "with -L: $(find -L "$d/root" -name SKILL.md | wc -l | tr -d ' ')"
rm -r "$d"
```

That prints `without -L: 1` and `with -L: 2`: the symlinked skill is the one that vanishes.
On a real machine the same check is the Phase 1 sweep diffed against itself with `-L` deleted,
and what only the `-L` run prints is what a sweep without it missed.

## Why no scanner ships

Three detectors written in this repository measured near-perfect on their author's own fixture
and near-useless in the field. One scored precision 1.00 on its fixture; a cold agent measured
about 4% on real libraries and a second 8% on a different corpus, with 0 of 5 recall on the
commonest shape. A general skill linter rejected 46 of 156 real installed skills,
including four of Anthropic's own — recorded in `notes/2026-08-25-implementation-session.md`,
and the one number here a reader cannot re-run, because the linter was cut. The failure is structural: a detector tuned against examples the
author wrote encodes the author's model of the defect, and the field contains the defects the
author could not imagine. In every case the prose doctrine shipped and the tool did not.

## Why the caps need a per-skill test

The description and body caps are asserted in each skill's own `tests/test_seed_<name>.py`,
not in one global test. The gap has already bitten: `ai-tell-audit` ships a 531-line body,
over the documented 500-line ceiling, because its test caps the description and not the body.
A new skill with no test of its own is not partially guarded. It is unguarded.

## Why the precedence rule goes in the description

Measured here, quoted from the test that now pins it: flipping a precedence clause to its
opposite in the frontmatter "passed every test, because both trigger tests read the body."
The router sees the description and nothing else. A precedence rule stated only in the body
applies after the decision it was supposed to make.
