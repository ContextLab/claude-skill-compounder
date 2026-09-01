---
name: skill-authoring
description: "Use when renaming a skill directory or rewriting a SKILL.md's frontmatter: wording the description whose `Use when` and decline clauses decide when it fires, fixing an installed skill that never fires, and running the parse and trigger gates. Do NOT use for judging whether a procedure earned a skill, red-teaming or retiring one (that is skill-compounder), proposing one upstream (that is contribute-skill), a body whose trigger works (that is writing-skills), or ordinary docs and commands."
---

# Authoring a SKILL.md

A skill has to fire on its own. Nobody calls it by name; a router reads its description and
decides. So both ways a skill fails are invisible from the inside: it never loads, or it
loads and never fires. Each leaves a file on disk that reads perfectly and prints no error.
Three of this repository's four original seed skills shipped defective, and the validator
said they were fine. So this procedure is gates, not advice: each one is a command you run
and read the output of.

## The Iron Law

```
A DRAFT YOU HAVE NOT PARSED AND NOT TRIGGER TESTED IS NOT A SKILL
```

## When this is the wrong skill

- **Deciding whether a procedure deserves a skill at all**, red-teaming a draft, or retiring
  one that misfires: that is `skill-compounder`. It owns the threshold, the cold-reviewer
  loop, and the archive protocol. This skill starts after the decision and stops before the
  review. The dividing line when a skill is already installed and behaving badly: if it
  **fired on the wrong prompt**, that is a misfire and `skill-compounder` runs the loop; if
  it **never fires at all**, or fires but the frontmatter is what has to change, that is
  this skill.
- **A skill whose trigger already works and whose body is what needs writing**: that is
  `writing-skills` (shipped by the `superpowers` plugin, so it is installed alongside this
  one and its description covers creating, editing and verifying skills in general). This
  skill takes the strictly smaller situation: the frontmatter, the trigger clause, and the
  two gates. Once the description fires correctly, hand the body back.
- **Proposing a finished local skill to a shared upstream repository**: that is
  `contribute-skill`.
- **Ordinary documentation**: a README, a design doc, a runbook, an agent definition, a slash
  command. None of those are routed by a description, so none of this applies.

## Stop: the six silent defects

Read this table before you write a line. Every row is a defect that ships green.

|Defect|What actually happens|The rule|
|-|-|-|
|Unquoted `: ` inside a scalar|The YAML scalar terminates early and the document fails to parse for every strict consumer: the claude.ai upload, the Agent Skills spec validator, this repository's own suite. Measured: `yaml.safe_load("description: Use when X: do Y")` raises `ScannerError`|Always double-quote the `description` value. It is never optional and it costs two characters|
|Unquoted `#` inside a scalar|Worse than the colon, because nothing raises. A bare `#` opens a YAML comment, so the scalar ends there and the rest of the trigger is gone with no error. Measured: `description: Use when a run is tagged #urgent and needs triage. Do NOT use for ordinary runs...` parsed to the 24-char string `Use when a run is tagged`; the entire decline half vanished and the version of Gate A that tested only for a colon printed `GATE A PASS`. The block in Phase 3 rejects it: `GATE A FAIL: description is a bare YAML scalar`, exit 1|Same rule, same reason: **always** double-quote. Bare `#`, `&`, `*`, `[`, `{`, `%`, `@` and a leading `>` each retype or truncate the value silently. Gate A rejects a bare scalar outright|
|`description` missing, or parsed as a mapping or a list|The skill still lists, so nothing looks broken, but Claude Code substitutes the **H1 heading** of SKILL.md as the listed description. Measured on claude 2.1.245: `description: {trigger: DINGO9900}` listed as `- s-mapping2: Heading ZEBRA1357`. The trigger is now a title, and titles do not describe situations|`description` must be present and a plain string. Write the H1 as a usable fallback anyway|
|`name:` disagreeing with the directory|The **directory name is the identity**. Measured: a skill in `dir-name-here/` with `name: frontmatter-name-here` listed as `dir-name-here`. Every doc, cross-reference and invocation that used the frontmatter name points at nothing, and nothing errors|`name:` must equal the directory name, character for character|
|Any frontmatter key outside the portable six|A hard error for any Agent Skills consumer outside Claude Code, which is where a shipped skill goes|Only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. Nothing else, including `version`|
|Trusting `claude plugin validate --strict`|It checks that a `---` block exists and that a `description:` line is present, and nothing else. Measured on 2.1.245: a skill whose description carried an unquoted colon printed `✔ Validation passed`, exit 0; so did a rogue key; so did a name/directory mismatch|The validator is not a gate. Gate A below is|

## Phase 1: Prior-art sweep

An existing skill covering the same trigger is a blocking finding, not a note. Two skills
with overlapping descriptions do not compose; they compete, and the router picks one.

**1. Enumerate the installed population.** Three roots, and `-L`:

```bash
find -L ~/.claude/skills ~/.claude/plugins/cache ./.claude/skills -name SKILL.md 2>/dev/null \
  | sed 's#/SKILL\.md$##; s#.*/##' | sort -u
```

`-L` is load-bearing, not tidiness, and it is not optional. Installers symlink skill directories into
`~/.claude/skills`, and `find` does not descend a symlink, so a sweep without `-L` omits every
symlinked skill and prints no warning that it did. How many that is depends on what is
installed, so it is not a number this file can state for your machine: rerun the command
above with `-L` deleted and `diff` the two outputs, and every line only the `-L` run prints is
a neighbour you would otherwise not have seen. `references/why-these-rules.md` reproduces the
same miss on a fixture, on any machine, with nothing installed. Walk for `SKILL.md`
rather than globbing a fixed depth: some packages nest a second level under the version
directory, and a fixed-depth glob silently reports a smaller population than the one you are
colliding with. The third root catches project-scoped skills, which are invisible in the
other two.

**2. Read the descriptions, not the names.** The name is a label; the description is the
trigger you might be colliding with. Parse the YAML rather than grepping it: a `grep` of
`^description:` prints the literal `description: >-` for a block scalar and reads nothing,
and truncating the line with `cut` throws away the decline half, which is the half that
tells you whether the overlap is real.

```bash
find -L ~/.claude/skills ~/.claude/plugins/cache ./.claude/skills -name SKILL.md 2>/dev/null \
  | python3 -c 'import sys, yaml, pathlib
for line in sys.stdin:
    p = pathlib.Path(line.strip())
    try:
        meta = yaml.safe_load(p.read_text().split("---\n", 2)[1]) or {}
    except Exception as exc:
        meta = {"description": "UNPARSEABLE %s" % type(exc).__name__}
    d = " ".join(str(meta.get("description")).split())
    print("%-34s %s" % (p.parent.name, d[:300]))' | sort -u
```

**3. Name the nearest neighbours in the draft itself**, under `## When this is the wrong
skill`, with the boundary stated. If you cannot name one, you did not look.

**4. If a neighbour already covers your trigger, stop and narrow.** Either the new skill
takes a strictly smaller situation and says so, or there is no new skill and the right change
is an edit to the neighbour. Shipping the overlap and letting the router sort it out is the
coin flip this phase exists to prevent. A neighbour installed by a plugin counts: it is in
the same listing as yours.

## Phase 2: Name and description first

The body is written last: until the name and description are settled there is nothing for a
body to belong to.

**The name has to carry the trigger alone.** Claude Code drops whole descriptions from the
skill listing under context-budget pressure, least-invoked first, and the name is then all
that survives. Observed: several `huggingface-skills` entries list as bare names while their
on-disk files carry full, valid `description:` values. A skill named `hf-mem` is untriggerable
the moment that happens. Name the situation instead: `stale-artifact-check`,
`destructive-op-preflight`, `no-silent-stub`.

**The description is a trigger clause, never a summary.** It answers *when do I fire*, not
*what do I do*. Both halves are required:

```
Use when <the situation, concretely, in the words a user would actually type>.
Do NOT use for <the neighbouring situations>, that is <the skill that owns them>.
```

**Put the precedence rule in the description**, not only in the body. When two clauses can
both match one prompt, the description is the only text the router sees, so a precedence
rule that lives in the body is a rule the router never reads. This has been measured here:
inverting a body-only precedence clause passed every test in its suite.

**Budgets.** Description at most 500 characters; the whole frontmatter block at most 1024.
Padding for safety makes the drop above more likely, not less. Write the description, then go
straight to Gate A. Do not write the body yet.

## Phase 3: Gate A — parse

Run this. Do not read it and conclude it would pass.

```bash
SKILL_DIR=<path to the skill directory>
python3 - "$SKILL_DIR" <<'EOF'
import pathlib, sys, yaml
PORTABLE = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
d = pathlib.Path(sys.argv[1]).resolve()
raw = (d / "SKILL.md").read_text()
if not raw.startswith("---\n"):
    sys.exit("GATE A FAIL: no frontmatter block")
front = raw.split("---\n", 2)[1]
meta = yaml.safe_load(front)               # raises on the unquoted-colon case
if not isinstance(meta, dict):
    sys.exit("GATE A FAIL: frontmatter is not a mapping, it is %r" % type(meta).__name__)
desc = meta.get("description")
if not isinstance(desc, str) or not desc.strip():
    sys.exit("GATE A FAIL: description is %r, so the listing falls back to the H1" % (desc,))
line = next((l for l in front.splitlines() if l.startswith("description:")), "")
if line[12:].lstrip()[:1] not in ('"', "'", ">", "|"):
    sys.exit("GATE A FAIL: description is a bare YAML scalar, so a `#` or a `: ` truncates "
             "it with no error. Double-quote it")
if meta.get("name") != d.name:
    sys.exit("GATE A FAIL: name %r does not match directory %r" % (meta.get("name"), d.name))
extra = sorted(set(meta) - PORTABLE)
if extra:
    sys.exit("GATE A FAIL: non-portable frontmatter keys %s" % extra)
if len(desc) > 500 or len(front) > 1024:
    sys.exit("GATE A FAIL: description %d chars, frontmatter %d chars" % (len(desc), len(front)))
print("GATE A PASS: %s | description %d chars | frontmatter %d chars"
      % (meta["name"], len(desc), len(front)))
EOF
```

Anything other than `GATE A PASS` sends you back to Phase 2. A traceback counts as a
failure; that is the unquoted colon, and it is the commonest defect here.
`SkillFrontmatterTest` in `tests/test_plugin.py` covers part of this for skills shipped from
this repository — it parses, matches `name` to the directory and restricts the keys — but it
accepts a bare scalar and checks neither budget, so it is not this gate. `skill-compounder`
step 3 runs a parse of its own; both are local to where they live. A skill forged into `~/.claude/skills/` has nothing watching it.
To run the same checks over a whole tree of existing skills at once, use the sweep in
`references/gate-checks.md`.

## Phase 4: Gate B — trigger discrimination

A description you have only read is untested prose. Write the collisions down and judge them.
The worksheet that forces a written reason per prompt is in `references/gate-checks.md`.

**1. Write six prompts** into a `## Trigger precision` section of the draft: three that MUST
fire, three that must NOT, phrased the way a user would actually type them, and no prompt in
both sets. Constraints that make the set worth having, each with the test that decides it:

- At least two must-fire prompts use the description's own vocabulary. The criterion is
  mechanical, so that your test and the reviewer's agree: take every word of five or more
  letters from the `Use when` half of the description, lowercase it, and look for it in the
  prompt as a whole word, case-insensitively. Stems, synonyms and plurals do not count. A
  must-fire set that shares no such word with the description is testing your intent, not
  the text.
- At most one must-NOT prompt sits in a documented overlap with a neighbour, and that one
  names the skill that owns it in backticks. A prompt counts as sitting in the overlap when
  it names a skill, a `SKILL.md`, or a neighbouring skill by name. The other two must be
  unambiguous, or the negative set stops exercising the clear cases. Zero overlap prompts
  means the precedence rule from Phase 2 is untested.

**2. Judge each prompt against the description alone.** The body is not loaded when the
router decides, so reading the body while judging is the whole way this gate goes wrong.
Print the description by itself and work from that:

```bash
python3 -c "import sys,yaml,pathlib; print(yaml.safe_load(pathlib.Path(sys.argv[1]).read_text().split('---\n',2)[1])['description'])" "$SKILL_DIR/SKILL.md"
```

**3. Any prompt landing on the wrong side returns you to Phase 2.** Rewriting the prompt so
it passes is the failure mode this gate exists for: the prompts are the fixture, and the
description is what changes.

## Phase 5: Body and unhappy path

Only now write the body. The house shape, in this order:

`# H1` and a short opening, `## The Iron Law` (fenced, one line, capitals), `## When this is
the wrong skill`, numbered `## Phase N` sections, `## Red flags`, `## Common
rationalizations`, `## Trigger precision`, `## Quick reference`. **Hard ceiling: 500 body
lines**, and a working ceiling of 400. The body is a token cost paid on every turn after the
skill loads, so there is no floor: a draft that covers every phase in half the lines is the
better skill, not a thinner one.

**Answer the unhappy path.** Every skill must say what a session does when a step fails
partway through: what a half-finished run leaves on disk or in the tree, how to tell, and the
command that puts it back. Prior-art authoring skills omit this entirely, so a draft written
from prior art ships happy-path-only and the first partial failure strands the user.

**This skill's own, since it is subject to its own rule.** *Where the draft lives until it is
finished:* not under a skill root. The three roots in Phase 1 are the roots because that is
where the router looks, and nothing in the frontmatter marks a file as unfinished — the
portable six have no draft key — so a half-written `SKILL.md` sitting in a root is
indistinguishable from a finished one and can fire on a user's prompt. Observed here: all ten
directory entries in `~/.claude/skills` appear in this session's skill listing, and this
skill, which exists only in a repository whose installer has not linked it there, does not.
Draft outside all three roots — a repository's own skills directory before its installer
runs, or `/tmp/skill-draft-<name>/` — and put it in a root only after Gate C. Whether a
session already running notices a directory that appears under a root mid-session is not
tested here; assume the next session does.

*If the run is abandoned partway:* a draft outside the roots is inert, so leave it or delete
it. A draft that already reached a root is live, so take it back out — and look before you
remove, because a symlink you created unlinks safely while a real directory there may be
somebody's only copy:

```bash
SKILLS=~/.claude/skills; NAME=<the draft>
if [ -L "$SKILLS/$NAME" ]; then rm "$SKILLS/$NAME"
elif [ -d "$SKILLS/$NAME" ]; then mv "$SKILLS/$NAME" "${TMPDIR:-/tmp}/skill-draft-$NAME"
else echo "not live"; fi
```

The other thing a partial run leaves is the Phase 6 test file. A suite that collects its test
files by glob — this repository's does — picks up the test for a skill that no longer exists
and fails on it, so remove that in the same breath.

**Every command the draft asserts, you have run, and you kept the output.** Paths, versions,
flags, exit codes. An unverified claim is a defect, not a rough edge, and this loop has
received builder reports describing runs that never happened. A cross-reference is a claim
too: every repository path this file names has to exist.

**Split by verifiability.** Prose whose commands a test cannot exercise moves to
`references/`; executables go to `scripts/`. What is left in the body is always loaded, so it
has to earn its lines. Link every reference file from the body: `references/gate-checks.md`
holds the tree sweep and the Gate B worksheet, `references/why-these-rules.md` holds the
measurements. An unlinked reference is a file nobody opens.

**Ship no scanner, linter, or detector** unless it has been measured against a real external
corpus rather than your own fixture. A confident wrong linter is worse than none; ship the
prose doctrine and cut the tool.
**Ship no build artifacts** either: the directory is symlinked whole into the user's config,
so a stray `__pycache__` or `.pyc` ships with it.

## Phase 6: Gate C — ship the test and the ledger

**1. Write the per-skill test.** The caps and the gates are enforced per skill, not
globally, so a new skill has no guard at all until you write one: `ai-tell-audit` shipped a
534-line body, over the documented 500-line ceiling, until 2026-08-26
(`git show eec5d1b:skills/ai-tell-audit/SKILL.md`), because its own test file capped the
description and not the body. It was brought under by moving depth into `references/`.

Where it goes, because there is no default: if the skill lives in a repository, the file is
`tests/test_seed_<name>.py` **relative to that repository's root**, run the way that
repository runs its suite. A skill forged straight into `~/.claude/skills/<name>/` has no
repository and no suite — there is no `~/.claude/tests` — so either move the skill into a
repository first or write the test to `~/.claude/skills/<name>/tests/test_<name>.py` and
record in the ledger how it is run. Reading the file off disk at run time rather than
restating constants, it must:

- re-run Gate A: parse, string-typed non-empty description, a quoted rather than bare
  scalar, `name` equal to the directory, keys within the portable six;
- re-run Gate B: the six prompts, disjoint, with the vocabulary and overlap constraints;
- assert both caps, description at most 500 characters and body at most 500 lines;
- assert the skill directory ships no build artifacts.

Run it. A test you wrote and did not run is worth less than no test: it reads as coverage.

**2. Emit the hand-back ledger**, verbatim in this shape. Every line is required. A field you
did not do is declared `not run`; omitting it reads as done.

```
SKILL:        <directory name> at <absolute path>
Prior art:    <nearest neighbours, or "none found"> | overlap: <none | narrowed how>
Gate A:       <pass | fail: message> | <the command you ran>
Gate B:       <n>/3 fire, <n>/3 decline | judged from: <description | body, which is wrong>
Budgets:      description <n> chars | frontmatter <n> chars | body <n> lines
Test:         <path to the test file> | <n> tests | <pass | fail | not run>
Unrun claims: <commands or paths asserted but not executed, or "none">
Unhappy path: <one line: what a failed run leaves, and the command that recovers it>
```

Hand that to whoever reviews the draft. The reviewer is a fresh agent that is not a fork of
yours, and it is not yours to dispatch; `skill-compounder` owns the review rounds.

## Red flags

Each of these means stop and go back to a gate:

- "The frontmatter is obviously fine, it is four lines." (Four lines is the size that gets eyeballed instead of parsed. Gate A.)
- "`claude plugin validate --strict` passed." (It passes unparseable YAML, exit 0.)
- "There is no colon in my description, so I do not need the quotes." (Then a `#` eats the second half instead, and nothing raises.)
- "I will write the body first and tighten the description at the end." (The description is
  the skill. The body is what happens after it already worked.)
- "The description explains what the skill does." (Then it does not say when it fires.)
- "It sounds like it would fire on that." (Judge the six prompts against the description alone, or Gate B did not run.)
- "That prompt is unfair, let me reword it." (The prompts are the fixture.)
- "There is a similar skill but mine is better." (Overlap is blocking. Narrow, or edit that one.)
- "The sweep found no neighbour." (Did you pass `-L`? Without it every symlinked skill is invisible.)
- "I will add the test once the skill settles." (It is unguarded until then, and it never settles.)

## Common rationalizations

|Excuse|Reality|
|-|-|
|"The colon rule is superstition, my skill loads fine."|It loads in the CLI in front of you. It fails `yaml.safe_load`, this repository's suite, the spec validator, and the claude.ai upload. Portability is the claim, and it is testable.|
|"I quoted the description, so the frontmatter is safe."|The unquoted colon is one of six. A `#`, a dropped `description`, a rogue key and a name mismatch all ship green too.|
|"The name is internal, the description does the work."|Descriptions get dropped from the listing under budget pressure. The name is what remains.|
|"A longer description gives the router more to match."|Longer descriptions are dropped sooner. Under 500 characters, and every clause a trigger.|
|"I stated the precedence rule in the body."|The router never reads the body. A body-only precedence clause has already passed a full suite here while stating the opposite of the frontmatter.|
|"The frontmatter name is the real name."|The directory is the identity. The frontmatter name is not what gets listed.|
|"I ran the commands earlier, they worked."|Then you have the output. Paste it. Reports in this loop have described runs that never happened.|
|"A linter would catch these for the next person."|Three linters here measured near-perfect on their author's fixture and near-useless in the field. Ship the doctrine, cut the tool.|
|"The existing seed tests already cap body length."|Per skill, not globally. A new skill is unguarded until its own test exists, which is how a 534-line body shipped.|
|"My sweep found nothing to collide with."|A sweep without `-L` silently omits every symlinked skill directory, which is how installers put them there. Diff the two sweeps (`references/why-these-rules.md`): whatever only the `-L` side prints is what you did not see.|

## Trigger precision

<!-- routing-pin
description-sha256: f08886748dc04dc8bd670a535a3b64d69c485534f6fa0b02c63cf938d6ed9ad7
prompts-sha256: e3500966bcaac0ffe4e9ceffd2d8bf220d31166fab4082d87ae88cbfdcbb9281
measured: 2026-08-31
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: verified 9/9 must-fire draws, 9/9 must-not-fire draws (3/3 each prompt over 3 runs) Re-measured after the description was rescoped on 2026-08-31: the 2026-08-28 wording broadened 'frontmatter' to 'a skill itself', the exact break its own pinned rule names, and blew the 500-char cap. The new opening names renaming and frontmatter without widening scope.
-->

Prompts that MUST fire this skill:

1. "Draft the frontmatter for this new SKILL.md: pick the directory name and word the description; the body can wait."
2. "The deploy-checklist skill is installed but it never fires. Fix its description so the router picks it up."
3. "Rename the skill directory and rewrite the frontmatter so it stops colliding with stale-artifact-check."

Prompts that must NOT fire this skill:

1. "We have hit this deploy footgun three times now. Does that deserve a skill?" (A threshold judgement, which is `skill-compounder`. This skill starts once the answer is yes.)
2. "Write the README for this repository."
3. "Add a slash command that runs the test suite."

A bare "write a SKILL.md for X" request is deliberately not claimed here. Measured on
2026-08-25, it routes to `writing-skills` where that plugin is installed, and this
description claims the strictly smaller frontmatter situation on purpose (Phase 1 calls
that overlap blocking; see `## When this is the wrong skill`). A referent-free "this
skill never fires" also went unclaimed when measured: with no skill named, the router
fired nothing, so must-fire 2 names one. Inside the forging loop this skill is not
routed at all: `skill-compounder` step 2 invokes it by name.

## Quick reference

|Phase|Action|Done when|
|-|-|-|
|1. Prior art|Enumerate all three skill roots with `find -L`, parse the descriptions, name the neighbours in the draft|No neighbour covers your trigger, or you narrowed|
|2. Name and description|Name carries the trigger alone; `Use when` + `Do NOT use for`; precedence clause in the description; 500 / 1024|The description is written and the body is not|
|3. Gate A|Run the parse block|`GATE A PASS` printed|
|4. Gate B|Six prompts, judged against the description alone|3 fire, 3 decline, no rewording|
|5. Body|House shape, 500-line ceiling, unhappy path answered, every command run, references linked, no scanner, no artifacts|The body says what a half-finished run leaves behind|
|6. Gate C|Write and run the per-skill test at the path the phase names; emit the ledger|The test runs green and every ledger field is filled or says `not run`|
