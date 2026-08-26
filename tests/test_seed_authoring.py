#!/usr/bin/env python3
"""Tests the `skill-authoring` seed skill.

This skill ships no executable, so the document is the program. Its load-bearing
parts are three gates, and a gate that is only read is not a gate. So the tests
below EXTRACT the gate blocks out of SKILL.md at run time and RUN them, against
real skill directories built on disk, one per defect the skill claims to catch.
Delete a check from the shipped block and the fixture for that defect goes green
when it must go red.

Nothing is duplicated as a constant where it could be derived. The portable key
set is read out of the skill's own defect table and checked against the copy
embedded in its own gate script, so dropping a key from either side fails. The
length caps, the body-line ceilings, the Gate B thresholds and the vocabulary rule
are all read out of the sentences that state them and applied to the file that
states them, so deleting a rule deletes the test that enforces it rather than
leaving a stale number behind.

Prose is pinned by polarity, not by keyword. A rule reading "the description is
a summary, never a trigger clause" is the opposite of the shipped rule and has
to fail; a test that only greps for `summary` cannot tell them apart, so the
assertions below quote whole clauses.

What is pinned here:

  1. The frontmatter parses, the description is a quoted string that really does
     contain `: `, and an unquoted version of that same string really raises.
     This skill of all skills cannot ship inert.
  2. The six silent defects are six, each stated with the right polarity, and
     each demonstrated: a fixture exhibiting it is fed to the shipped Gate A
     block and must be rejected. That includes the two defects the block once
     described but no fixture exercised (a non-mapping frontmatter, an
     over-long frontmatter block behind a short description).
  3. The Phase 1 prior-art commands run, and are run against a purpose-built
     tree containing a SYMLINKED skill and a BLOCK-SCALAR description, because
     both were invisible to the commands this file first shipped.
  4. Gate B: three must-fire prompts, three must-not, disjoint, with the
     vocabulary and overlap thresholds read out of Phase 4's own prose.
  5. The hand-back ledger has every field, and says `not run` rather than
     omitting.
  6. Every cross-reference the skill makes to a path in this repository, and
     every reference file it ships, actually exists and is actually linked.
  7. The load-bearing sentences that are not values -- rules with no "current
     setting" to derive -- are pinned VERBATIM in `PINNED` and required word
     for word in SKILL.md, after whitespace is collapsed, `*` is deleted, and
     the text a reader cannot read (HTML comments, strikethrough) is removed,
     so a rule cannot be repealed by hiding its sentence rather than deleting
     it. See the comment above `PINNED` for why a literal, and not a pattern.

No mocks. Real files, real subprocesses, real exit statuses.

WHY PINNING, AND NOT A CLEVERER SCANNER.

`tests/test_doctrine_sync.py` in this repository tried three times to enforce
doctrine by reading prose for meaning, and a fresh reviewer beat each attempt on
first contact -- never by finding a bug in a pattern, always by rewording. Asking
"does this paragraph still MEAN the rule" is deciding a question about natural
language, and the set of paraphrases is not finite, so that arms race has no
terminating round. Requiring the sentence itself is decidable. This file follows
it: everything derivable is derived; what is left is pinned as text.

WHAT THIS FILE DOES NOT CATCH. Every item below was reached by mutating SKILL.md
and running this suite, so each is a measured limit rather than a predicted one.
A reviewer who finds one has found a documented boundary, not a defect; do not
close them by reopening the scanner arms race.

  - A pinned sentence may be present and REPUDIATED in the clause after it, or
    given an ESCAPE HATCH. Nothing here can tell doctrine from a paragraph
    about doctrine. This is the ceiling on what pinning is worth: it stops
    drift, softening, deletion, hiding and relocation; it does not stop an
    author who means to reverse a rule. Measured, all four green:
      * "So this procedure is gates, not advice: ... read the output of. That
        was the old framing and it proved too rigid; treat every phase below as
        a suggestion."
      * "... and the command that puts it back. A skill with no failure mode
        may skip this entirely."
      * a paragraph appended under the fenced Iron Law saying both gates are
        optional for a small skill;
      * "(The prompts are the fixture.) Though in practice rewording one is
        fine." appended to a pinned red flag.
    Where a hatch was inserted BETWEEN two pinned sentences it now fails, because
    three pins (`both-halves-required`, `run-the-test-you-wrote`,
    `the-body-is-not-loaded-when-the-router-decides`) were widened into
    contiguous spans for exactly that reason. That shrinks the surface; it does
    not close the class, and widening every pin into one span is just pinning
    the document. Do not treat the next hatch found here as a defect in the
    guard. `test_doctrine_sync.py` reached the same ceiling independently, with
    a cold reviewer reversing eight pinned rules that way in one pass at exit 0.
  - Only the sentences in `PINNED` are pinned at all. Every other sentence in
    SKILL.md can be reworded or inverted freely. `PINNED` is a floor that grows,
    not a claim of coverage, and adding to it is cheap.
  - Whether a prompt in `## Trigger precision` genuinely belongs in the half it
    is filed under is a judgement, and no assertion here makes it. The
    mechanical parts are checked -- the set sizes, disjointness, the vocabulary
    count, the overlap count and its named owner -- but a must-fire prompt can
    be rewritten into one that should NOT fire while still satisfying every one
    of them, as long as two of the three still carry description vocabulary.
    Measured: replacing "Write a SKILL.md for the release checklist we keep
    redoing by hand" with "Set up the release checklist we keep redoing by
    hand" -- which is a `skill-compounder` threshold question, not this skill --
    leaves the suite green.
  - Prose that is neither a derived value nor pinned can be deleted: the
    rationale sentences under a rule, the evidence in a `Measured:` clause
    beyond the five the defect table is required to carry, the examples under a
    naming rule. The high-value ones are pinned; the long tail is not.
  - Nothing here reads `references/*.md` for polarity. `GateChecksReferenceTest`
    and `WhyTheseRulesTest` run their commands and check their claims against
    the files those claims are about, but the prose around them is unpinned.
  - Two independent checks inside the shipped Gate A block can be swapped --
    the name/directory comparison and the portable-key comparison -- and
    nothing fails. That one is deliberate and not a hole: both still run, both
    still `sys.exit` non-zero, and a fixture carrying both defects is rejected
    either way. Only the message differs. Ordering is pinned where it changes
    behaviour (the `-L`-before-`-d` recovery block, executed by
    `OwnRecoveryBlockTest`) and where it is doctrine (the house shape, the
    numbered steps in each phase), not everywhere.

For the record, the numbers behind those paragraphs. Two rounds of mutation
testing, every edit applied to a scratch copy of the repo, the suite run, and the
copy restored: 175 edits in all, to SKILL.md and to `references/`. Round one was
124 edits written here; 51 survived the suite as it then stood. Round two was 23
edits found by a cold reviewer given the skill and the suite and asked, without
being told what to avoid, for changes that leave it green; all 23 reproduced.
Every one of those 74 is now killed. What survives is the four repudiations
quoted above, the trigger-precision judgement, and the Gate A reordering.
"""

import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True

import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "skill-authoring"
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"

WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}

# The 13 house sections, in the order the body must present them. Prefixes only:
# the Phase headings carry a subtitle that is allowed to be reworded.
HOUSE_SECTIONS = [
    "## The Iron Law",
    "## When this is the wrong skill",
    "## Stop: the six silent defects",
    "## Phase 1",
    "## Phase 2",
    "## Phase 3",
    "## Phase 4",
    "## Phase 5",
    "## Phase 6",
    "## Red flags",
    "## Common rationalizations",
    "## Trigger precision",
    "## Quick reference",
]


# ---------------------------------------------------------------------------------------
# The pinned rules.
#
# Everything a test can DERIVE from the document is derived: the caps, the ceilings, the
# Gate B thresholds, the portable key set, the prompt-set sizes. What is left over is
# doctrine -- a rule with no "current setting" to read off, whose only enforcement is that
# the sentence stating it is still there and still says what it says.
#
# Those are pinned VERBATIM below, and each must appear in SKILL.md word for word, with
# whitespace collapsed, `*` deleted, and the text a reader cannot read (HTML comments,
# strikethrough) removed first, so a rule cannot be repealed by hiding its sentence rather
# than deleting it.
#
# Pinning a literal is the opposite of what the rest of this file does, and it is
# deliberate. Three rounds of pattern-matching prose in a sibling file (see the module
# docstring of `test_doctrine_sync.py`) were each beaten on first contact by paraphrase --
# "does not have to be a fork", "There is no fork restriction" -- because deciding whether
# a paragraph still MEANS a rule is deciding a question about natural language, and the set
# of paraphrases is not finite. Requiring the sentence itself is decidable.
#
# To change a rule: change the sentence here and in SKILL.md, in one commit. To retire one:
# delete the entry and say in the commit message why the rule no longer holds. Both are
# meant to be visible in a diff, not difficult.
#
# Each entry is (id, exact sentence, why it is pinned). Every one of them was verified by
# mutation: the sentence was deleted or inverted in a scratch copy, the suite was run, and
# it went red.
# ---------------------------------------------------------------------------------------
PINNED = (
    ("gates-not-advice",
     "So this procedure is gates, not advice: each one is a command you run and read the "
     "output of.",
     "The premise of the whole file. Softened to advice, every phase below becomes "
     "optional and nothing else in the document objects."),

    ("three-of-four-shipped-defective",
     "Three of this repository's four original seed skills shipped defective, and the "
     "validator said they were fine.",
     "The measurement that justifies distrusting the validator. Without it the six-defect "
     "table is one author's opinion."),

    ("misfire-versus-never-fires",
     "if it **fired on the wrong prompt**, that is a misfire and `skill-compounder` runs "
     "the loop; if it **never fires at all**, or fires but the frontmatter is what has to "
     "change, that is this skill.",
     "The routing rule between this skill and its nearest neighbour. Swapping the two "
     "halves sends every caller to the wrong skill and reads perfectly."),

    ("ordinary-documentation-is-out",
     "None of those are routed by a description, so none of this applies.",
     "The decline clause for READMEs, runbooks and slash commands, and the reason for it."),

    ("yaml-metacharacters",
     "Bare `#`, `&`, `*`, `[`, `{`, `%`, `@` and a leading `>` each retype or truncate the "
     "value silently.",
     "The list is the reason the quoting rule is unconditional. Deleting it leaves `#` as "
     "an anecdote about one character."),

    ("write-the-h1-fallback",
     "Write the H1 as a usable fallback anyway",
     "The only actionable instruction in the row about the H1 substitution."),

    ("hash-measurement",
     "Measured: `description: Use when a run is tagged #urgent and needs triage. Do NOT "
     "use for ordinary runs...` parsed to the 24-char string `Use when a run is tagged`; "
     "the entire decline half vanished and the version of Gate A that tested only for a "
     "colon printed `GATE A PASS`.",
     "An evidence citation. The file's own Phase 5 rule is that an unverified claim is a "
     "defect, so its own measurements have to survive editing."),

    ("h1-fallback-measurement",
     "Measured on claude 2.1.245: `description: {trigger: DINGO9900}` listed as "
     "`- s-mapping2: Heading ZEBRA1357`.",
     "Same: the observation, with the version it was observed on."),

    ("walk-not-glob",
     "Walk for `SKILL.md` rather than globbing a fixed depth: some packages nest a second "
     "level under the version directory, and a fixed-depth glob silently reports a smaller "
     "population than the one you are colliding with.",
     "Explains why the sweep command is shaped the way it is. Without it the command looks "
     "like it could be simplified to a glob, which under-reports with no warning."),

    ("third-root-is-project-scoped",
     "The third root catches project-scoped skills, which are invisible in the other two.",
     "The only justification for the third root; the row that would otherwise be dropped "
     "as redundant."),

    ("why-these-rules-reproduces-the-miss",
     "`references/why-these-rules.md` reproduces the same miss on a fixture, on any "
     "machine, with nothing installed.",
     "The `-L` claim is machine-dependent; this sentence is what makes it checkable by a "
     "reader whose machine has nothing installed."),

    ("read-descriptions-not-names",
     "**2. Read the descriptions, not the names.** The name is a label; the description is "
     "the trigger you might be colliding with.",
     "Phase 1's actual instruction. Inverted, the prior-art sweep compares the one field "
     "the router does not read."),

    ("parse-do-not-grep",
     "Parse the YAML rather than grepping it: a `grep` of `^description:` prints the "
     "literal `description: >-` for a block scalar and reads nothing, and truncating the "
     "line with `cut` throws away the decline half, which is the half that tells you "
     "whether the overlap is real.",
     "Why the sweep ships a Python block instead of the one-line grep every reader will "
     "reach for first."),

    ("name-carries-the-trigger-alone",
     "**The name has to carry the trigger alone.**",
     "The naming rule. Reduced to a convenience, `hf-mem`-shaped names come back."),

    ("descriptions-are-dropped-first",
     "Claude Code drops whole descriptions from the skill listing under context-budget "
     "pressure, least-invoked first, and the name is then all that survives.",
     "The mechanism the naming rule rests on."),

    ("name-the-situation",
     "Name the situation instead: `stale-artifact-check`, `destructive-op-preflight`, "
     "`no-silent-stub`.",
     "The rule with no examples is advice; the examples are what make it followable."),

    ("both-halves-required",
     "Both halves are required: ``` Use when <the situation, concretely, in the words a "
     "user would actually type>.",
     "Softened to `either half will do`, a description ships with no decline clause and "
     "Gate A still passes it."),

    ("no-padding",
     "Padding for safety makes the drop above more likely, not less.",
     "The only thing stopping a reader from treating the 500-character cap as a target."),

    ("run-do-not-read",
     "Run this. Do not read it and conclude it would pass.",
     "The Iron Law restated at the point of use. This is the sentence the defect it "
     "prevents is named after."),

    ("nothing-watches-a-forged-skill",
     "A skill forged into `~/.claude/skills/` has nothing watching it.",
     "The reason Gate A is not redundant with this repository's own suite."),

    ("tree-sweep-lives-in-gate-checks",
     "To run the same checks over a whole tree of existing skills at once, use the sweep "
     "in `references/gate-checks.md`.",
     "One of the two links that keep a shipped reference file from going unread."),

    ("a-read-description-is-untested",
     "A description you have only read is untested prose.",
     "Gate B's premise. Without it, step 1 reads as paperwork."),

    ("five-or-more-letters",
     "take every word of five or more letters from the `Use when` half of the description, "
     "lowercase it, and look for it in the prompt as a whole word, case-insensitively",
     "The mechanical criterion, stated so a cold author and this file reach the same "
     "verdict. The letter count is derived nowhere else, so lowering it silently widens "
     "the vocabulary to include function words -- see the degeneracy control below."),

    ("overlap-prompt-names-its-owner",
     "and that one names the skill that owns it in backticks",
     "The clause that makes the overlap prompt checkable at all. Deleting it deletes the "
     "test that reads it."),

    ("zero-overlap-leaves-precedence-untested",
     "Zero overlap prompts means the precedence rule from Phase 2 is untested.",
     "The floor under the overlap allowance, and the link back to Phase 2."),

    ("prior-art-omits-the-unhappy-path",
     "Prior-art authoring skills omit this entirely, so a draft written from prior art "
     "ships happy-path-only and the first partial failure strands the user.",
     "Why the unhappy-path requirement is stated at all, given no neighbouring skill "
     "states it."),

    ("look-before-you-remove",
     "a symlink you created unlinks safely while a real directory there may be somebody's "
     "only copy",
     "The reason the recovery block tests `-L` before `-d`. The block is executed by "
     "`OwnRecoveryBlockTest`; this is the sentence that says why it is shaped that way."),

    ("remove-the-stale-test-file",
     "A suite that collects its test files by glob \u2014 this repository's does \u2014 picks up "
     "the test for a skill that no longer exists and fails on it, so remove that in the "
     "same breath.",
     "The second half of this skill's own unhappy path. Dropping it leaves an abandoned "
     "run with a red suite and no instruction."),

    ("an-unlinked-reference-is-unread",
     "An unlinked reference is a file nobody opens.",
     "The rule behind `test_every_shipped_reference_is_short_and_linked_from_the_body`."),

    ("read-off-disk-not-constants",
     "Reading the file off disk at run time rather than restating constants, it must:",
     "The instruction that stops the shipped per-skill test from being a list of stale "
     "literals -- which is the failure this very file exists to avoid."),

    ("run-the-test-you-wrote",
     "Run it. A test you wrote and did not run is worth less than no test: it reads as "
     "coverage. **2. Emit the hand-back ledger**",
     "Pinned across the boundary into step 2, so a hatch cannot be inserted between them. "
     "`Reading it through carefully is an acceptable substitute` was appended in exactly "
     "that gap and the suite stayed green."),

    ("ledger-is-verbatim",
     "**2. Emit the hand-back ledger**, verbatim in this shape. Every line is required.",
     "A ledger the author may reshape is not a hand-back format, and the reviewer loses "
     "the one thing that tells them what was not run."),

    ("overlap-is-blocking",
     "There is a similar skill but mine is better.\" (Overlap is blocking. Narrow, or edit "
     "that one.)",
     "Phase 1's blocking finding, restated where a reader looks for permission to skip "
     "it."),

    ("test-never-settles",
     "I will add the test once the skill settles.\" (It is unguarded until then, and it "
     "never settles.)",
     "The rationalization behind the 531-line body that shipped."),

    ("linters-do-not-generalize",
     "Three linters here measured near-perfect on their author's fixture and near-useless "
     "in the field. Ship the doctrine, cut the tool.",
     "The measurement behind Phase 5's ban on shipping a scanner."),

    ("caps-are-per-skill",
     "Per skill, not globally. A new skill is unguarded until its own test exists, which "
     "is how a 534-line body shipped.",
     "Why Phase 6 exists at all."),

    # Found by a cold reviewer given the skill and this suite and asked, neutrally, for
    # edits that leave it green. Every one below was reproduced here before it was pinned.
    ("the-description-itself",
     "Use when a SKILL.md's frontmatter is what you write or fix: naming the directory, "
     "wording the description whose `Use when` and decline clauses decide when it fires, "
     "fixing an installed skill that never fires, and running the parse and trigger "
     "gates. Do NOT use for judging whether a procedure earned a skill, red-teaming or "
     "retiring one (that is skill-compounder), proposing one upstream (that is "
     "contribute-skill), a body whose trigger works (that is writing-skills), or "
     "ordinary docs and commands.",
     "The description IS the skill: it is the only text the router reads, so every other "
     "rule in the file is downstream of it. Pinned whole, and deliberately, because the "
     "three ways to break it are all invisible to a structural test -- swapping which "
     "neighbour owns which situation (`skill-compounder` and `writing-skills` exchanged "
     "routes every caller to the wrong skill), broadening `frontmatter` to `a SKILL.md` "
     "(which re-creates the `writing-skills` overlap Phase 1 calls blocking), and dropping "
     "one deferral clause. All three left this suite green. Rewording the description is "
     "meant to require editing this line."),

    ("the-router-decides",
     "A skill has to fire on its own. Nobody calls it by name; a router reads its "
     "description and decides. So both ways a skill fails are invisible from the inside: "
     "it never loads, or it loads and never fires. Each leaves a file on disk that reads "
     "perfectly and prints no error.",
     "The premise the Iron Law and all six gates rest on. Inverted -- `a skill is normally "
     "invoked by name`, `failures are loud and obvious` -- the document argues against "
     "itself and nothing read the paragraph."),

    ("read-the-table-first",
     "Read this table before you write a line. Every row is a defect that ships green.",
     "The lead-in that makes the table mandatory rather than reference material. "
     "`Skim this table if you have time. Most rows are rough edges` left the suite green."),

    ("double-quote-unconditionally",
     "Always double-quote the `description` value. It is never optional and it costs two "
     "characters",
     "`It is never optional` is the whole rule. An exemption grafted on -- `when it "
     "contains a metacharacter; a plain value is safe bare` -- keeps the words `Always "
     "double-quote` and reverses the rule, which is exactly what the row below it says "
     "goes wrong."),

    ("shipping-the-overlap-is-a-coin-flip",
     "Shipping the overlap and letting the router sort it out is the coin flip this phase "
     "exists to prevent.",
     "The consequence clause under `stop and narrow`. `is usually fine` deletes Phase 1's "
     "only sanction."),

    ("split-by-verifiability",
     "Prose whose commands a test cannot exercise moves to `references/`; executables go "
     "to `scripts/`.",
     "The two destinations are not interchangeable, and swapping them survived a test that "
     "only asserted both words appear."),

    # Modal verbs. Each of these was softened -- `must` to `should ideally`, `is a defect`
    # to `is a rough edge` -- rather than deleted, and the suite stayed green through every
    # one of them. A requirement demoted to a preference reads as a light edit and removes
    # the rule.
    ("description-must-be-a-plain-string",
     "`description` must be present and a plain string.",
     "The requirement behind the H1-substitution defect. Softened, the row describes a "
     "failure mode and asks for nothing."),

    ("the-unhappy-path-is-required",
     "Every skill must say what a session does when a step fails partway through: what a "
     "half-finished run leaves on disk or in the tree, how to tell, and the command that "
     "puts it back.",
     "The one requirement in Phase 5 that no neighbouring authoring skill states, and the "
     "three things it asks for. `should ideally say` left the suite green."),

    ("overlapping-skills-compete",
     "Two skills with overlapping descriptions do not compose; they compete, and the "
     "router picks one.",
     "The mechanism that makes an overlap blocking rather than untidy."),

    ("narrow-or-edit-the-neighbour",
     "Either the new skill takes a strictly smaller situation and says so, or there is no "
     "new skill and the right change is an edit to the neighbour.",
     "The two permitted outcomes of Phase 1. Without them `stop and narrow` has no "
     "definition of narrowed."),

    ("the-sweep-warns-about-nothing",
     "Installers symlink skill directories into `~/.claude/skills`, and `find` does not "
     "descend a symlink, so a sweep without `-L` omits every symlinked skill and prints "
     "no warning that it did.",
     "Why `-L` is required. `and prints no warning that it did` is the half that makes it "
     "a silent defect rather than an inconvenience, and it deleted cleanly on its own."),

    ("titles-do-not-describe-situations",
     "The trigger is now a title, and titles do not describe situations",
     "Why the H1 substitution is a defect at all, rather than a reasonable fallback."),

    ("the-body-is-not-loaded-when-the-router-decides",
     "**2. Judge each prompt against the description alone.** The body is not loaded when "
     "the router decides, so reading the body while judging is the whole way this gate "
     "goes wrong.",
     "The fact Gate B rests on. `partly loaded` makes judging from the body defensible."),

    ("the-clear-cases-stay-clear",
     "The other two must be unambiguous, or the negative set stops exercising the clear "
     "cases.",
     "The ceiling on the overlap allowance is derived from the prose; this is the reason "
     "for it, and the only constraint on the other two must-NOT prompts."),

    ("the-body-earns-its-lines",
     "What is left in the body is always loaded, so it has to earn its lines.",
     "The reason for the split by verifiability, and for the ceiling having no floor."),

    ("an-unverified-claim-is-a-defect",
     "An unverified claim is a defect, not a rough edge",
     "The polarity is the rule. Reversed, the sentence still discusses unverified claims "
     "and excuses them."),

    ("the-ledger-is-handed-to-a-reviewer",
     "Hand that to whoever reviews the draft.",
     "The ledger has an addressee, which is what makes `not run` a disclosure rather than "
     "a note to self."),

    # The quick reference is a promise about the phases above it, and a reader who skips
    # to it gets only this table. Each row is pinned except the numbers in rows 2 and 5,
    # which are derived from the phases that state them by
    # `test_the_quick_reference_repeats_the_caps_the_phases_state`.
    ("quick-reference-row-1",
     "|1. Prior art|Enumerate all three skill roots with `find -L`, parse the "
     "descriptions, name the neighbours in the draft|No neighbour covers your trigger, or "
     "you narrowed|",
     "Row 1 is where `-L` is easiest to drop silently: the two commands above it are "
     "executed by tests, this row is not."),

    ("quick-reference-row-2",
     "|2. Name and description|Name carries the trigger alone; `Use when` + "
     "`Do NOT use for`; precedence clause in the description;",
     "Row 2 restates Phase 2's three rules in one line."),

    ("quick-reference-row-2-done-when",
     "|The description is written and the body is not|",
     "Inverted, the table tells a skimmer to do exactly what Phase 2 forbids."),

    ("quick-reference-row-3",
     "|3. Gate A|Run the parse block|`GATE A PASS` printed|",
     "The exit condition of Gate A, in the one place a skimmer reads."),

    ("quick-reference-row-4",
     "|4. Gate B|Six prompts, judged against the description alone|3 fire, 3 decline, no "
     "rewording|",
     "`no rewording` is the whole of Gate B's discipline, and this row is the only place "
     "it appears outside Phase 4."),

    ("quick-reference-row-5-action",
     "-line ceiling, unhappy path answered, every command run, references linked, no "
     "scanner, no artifacts|The body says what a half-finished run leaves behind|",
     "Row 5 is the checklist for Phase 5; each item names a rule pinned or derived "
     "elsewhere, so dropping one here is how the table and the phase drift apart."),

    ("quick-reference-row-6",
     "|6. Gate C|Write and run the per-skill test at the path the phase names; emit the "
     "ledger|The test runs green and every ledger field is filled or says `not run`|",
     "Both halves of Phase 6 in one row: the test is run, and the ledger declares rather "
     "than omits."),
)


# Where each pinned rule has to LIVE. `PINNED` on its own checks presence anywhere in the
# file, and a cold reviewer used that: the `name has to carry the trigger alone` paragraph
# was cut out of Phase 2 and dropped into a new trailing `## Appendix`, and every assertion
# stayed green. A rule in the wrong phase is a rule the reader meets after the step it
# governs. `""` means the opening, above the first `## ` heading. A rule with no entry here
# is not location-checked.
PINNED_SECTIONS = {
    "the-description-itself": None,      # frontmatter, not the body
    "the-router-decides": "",
    "gates-not-advice": "",
    "three-of-four-shipped-defective": "",
    "misfire-versus-never-fires": "## When this is the wrong skill",
    "ordinary-documentation-is-out": "## When this is the wrong skill",
    "read-the-table-first": "## Stop: the six silent defects",
    "double-quote-unconditionally": "## Stop: the six silent defects",
    "yaml-metacharacters": "## Stop: the six silent defects",
    "write-the-h1-fallback": "## Stop: the six silent defects",
    "hash-measurement": "## Stop: the six silent defects",
    "h1-fallback-measurement": "## Stop: the six silent defects",
    "description-must-be-a-plain-string": "## Stop: the six silent defects",
    "titles-do-not-describe-situations": "## Stop: the six silent defects",
    "walk-not-glob": "## Phase 1",
    "third-root-is-project-scoped": "## Phase 1",
    "why-these-rules-reproduces-the-miss": "## Phase 1",
    "read-descriptions-not-names": "## Phase 1",
    "parse-do-not-grep": "## Phase 1",
    "overlapping-skills-compete": "## Phase 1",
    "narrow-or-edit-the-neighbour": "## Phase 1",
    "the-sweep-warns-about-nothing": "## Phase 1",
    "shipping-the-overlap-is-a-coin-flip": "## Phase 1",
    "name-carries-the-trigger-alone": "## Phase 2",
    "descriptions-are-dropped-first": "## Phase 2",
    "name-the-situation": "## Phase 2",
    "both-halves-required": "## Phase 2",
    "no-padding": "## Phase 2",
    "run-do-not-read": "## Phase 3",
    "nothing-watches-a-forged-skill": "## Phase 3",
    "tree-sweep-lives-in-gate-checks": "## Phase 3",
    "a-read-description-is-untested": "## Phase 4",
    "five-or-more-letters": "## Phase 4",
    "overlap-prompt-names-its-owner": "## Phase 4",
    "zero-overlap-leaves-precedence-untested": "## Phase 4",
    "the-body-is-not-loaded-when-the-router-decides": "## Phase 4",
    "the-clear-cases-stay-clear": "## Phase 4",
    "prior-art-omits-the-unhappy-path": "## Phase 5",
    "look-before-you-remove": "## Phase 5",
    "remove-the-stale-test-file": "## Phase 5",
    "an-unlinked-reference-is-unread": "## Phase 5",
    "the-unhappy-path-is-required": "## Phase 5",
    "the-body-earns-its-lines": "## Phase 5",
    "an-unverified-claim-is-a-defect": "## Phase 5",
    "split-by-verifiability": "## Phase 5",
    "read-off-disk-not-constants": "## Phase 6",
    "ledger-is-verbatim": "## Phase 6",
    "run-the-test-you-wrote": "## Phase 6",
    "the-ledger-is-handed-to-a-reviewer": "## Phase 6",
    "overlap-is-blocking": "## Red flags",
    "test-never-settles": "## Red flags",
    "linters-do-not-generalize": "## Common rationalizations",
    "caps-are-per-skill": "## Common rationalizations",
    "quick-reference-row-1": "## Quick reference",
    "quick-reference-row-2": "## Quick reference",
    "quick-reference-row-2-done-when": "## Quick reference",
    "quick-reference-row-3": "## Quick reference",
    "quick-reference-row-4": "## Quick reference",
    "quick-reference-row-5-action": "## Quick reference",
    "quick-reference-row-6": "## Quick reference",
}

# The fenced Iron Law, exactly. The shape regex it used to be checked against
# (`^[A-Z ,'-]+$` plus three substrings) admitted
# `... IS NOT A SKILL, BUT SHIP IT ANYWAY`, which passed every assertion here.
IRON_LAW = "A DRAFT YOU HAVE NOT PARSED AND NOT TRIGGER TESTED IS NOT A SKILL"

# The hand-back ledger, exactly as Phase 6 says to emit it -- the phase's own word is
# "verbatim". Checking only that each field NAME is present left `judged from: <description
# | body, which is wrong>` shortenable to `<description | body>`, which is the difference
# between a ledger that discloses a bad judgement and one that offers it as an option.
LEDGER = (
    'SKILL:        <directory name> at <absolute path>\n'
    'Prior art:    <nearest neighbours, or "none found"> | overlap: <none | narrowed how>\n'
    'Gate A:       <pass | fail: message> | <the command you ran>\n'
    'Gate B:       <n>/3 fire, <n>/3 decline | judged from: <description | body, which is '
    'wrong>\n'
    'Budgets:      description <n> chars | frontmatter <n> chars | body <n> lines\n'
    'Test:         <path to the test file> | <n> tests | <pass | fail | not run>\n'
    'Unrun claims: <commands or paths asserted but not executed, or "none">\n'
    'Unhappy path: <one line: what a failed run leaves, and the command that recovers it>\n'
)

# Every red flag and every rationalization, verbatim. Counting them and spot-checking four
# strings left the other six free: `"The description explains what the skill does." (Then
# it does not say when it fires.)` became `(Good: a clear summary is what the router
# matches on.)` with the suite at exit 0. The answer half is the whole value of the row, so
# the whole row is pinned. Adding a row is free; changing one has to show up in a diff.
RED_FLAGS = (
    '- "The frontmatter is obviously fine, it is four lines." (Four lines is the size that '
    'gets eyeballed instead of parsed. Gate A.)',
    '- "`claude plugin validate --strict` passed." (It passes unparseable YAML, exit 0.)',
    '- "There is no colon in my description, so I do not need the quotes." (Then a `#` eats '
    'the second half instead, and nothing raises.)',
    '- "I will write the body first and tighten the description at the end." (The '
    'description is the skill. The body is what happens after it already worked.)',
    '- "The description explains what the skill does." (Then it does not say when it '
    'fires.)',
    '- "It sounds like it would fire on that." (Judge the six prompts against the '
    'description alone, or Gate B did not run.)',
    '- "That prompt is unfair, let me reword it." (The prompts are the fixture.)',
    '- "There is a similar skill but mine is better." (Overlap is blocking. Narrow, or edit '
    'that one.)',
    '- "The sweep found no neighbour." (Did you pass `-L`? Without it every symlinked skill '
    'is invisible.)',
    '- "I will add the test once the skill settles." (It is unguarded until then, and it '
    'never settles.)',
)

RATIONALIZATIONS = (
    '|"The colon rule is superstition, my skill loads fine."|It loads in the CLI in front '
    "of you. It fails `yaml.safe_load`, this repository's suite, the spec validator, and "
    'the claude.ai upload. Portability is the claim, and it is testable.|',
    '|"I quoted the description, so the frontmatter is safe."|The unquoted colon is one of '
    'six. A `#`, a dropped `description`, a rogue key and a name mismatch all ship green '
    'too.|',
    '|"The name is internal, the description does the work."|Descriptions get dropped from '
    'the listing under budget pressure. The name is what remains.|',
    '|"A longer description gives the router more to match."|Longer descriptions are '
    'dropped sooner. Under 500 characters, and every clause a trigger.|',
    '|"I stated the precedence rule in the body."|The router never reads the body. A '
    'body-only precedence clause has already passed a full suite here while stating the '
    'opposite of the frontmatter.|',
    '|"The frontmatter name is the real name."|The directory is the identity. The '
    'frontmatter name is not what gets listed.|',
    '|"I ran the commands earlier, they worked."|Then you have the output. Paste it. '
    'Reports in this loop have described runs that never happened.|',
    '|"A linter would catch these for the next person."|Three linters here measured '
    "near-perfect on their author's fixture and near-useless in the field. Ship the "
    'doctrine, cut the tool.|',
    '|"The existing seed tests already cap body length."|Per skill, not globally. A new '
    'skill is unguarded until its own test exists, which is how a 534-line body shipped.|',
    '|"My sweep found nothing to collide with."|A sweep without `-L` silently omits every '
    'symlinked skill directory, which is how installers put them there. Diff the two '
    'sweeps (`references/why-these-rules.md`): whatever only the `-L` side prints is what '
    'you did not see.|',
)

# The reference files carry conclusions SKILL.md defers to, and nothing read them for
# polarity. A cold reviewer relaxed the colon rule inside `why-these-rules.md` ("quote only
# when it contains a colon"), inverted the padding finding and the linter finding, reversed
# the Gate B worksheet's verdict, and deleted the sentence saying neither shipped test
# watches a skill forged into `~/.claude/skills/`. Every one left the suite green while the
# reference now contradicted the body it supports.
PINNED_REFERENCES = {
    "why-these-rules.md": (
        ("colon-rule-still-stands",
         "The rule still stands, on narrower and firmer ground.",
         "The conclusion of the section that re-examines the colon rule. Reversed, the "
         "reference repeals the rule SKILL.md's first defect row states."),
        ("padding-is-not-insurance",
         "Padding is not free insurance either: a longer description is dropped sooner.",
         "The measurement behind Phase 2's `Padding for safety makes the drop above more "
         "likely, not less`."),
        ("doctrine-shipped-not-the-tool",
         "In every case the prose doctrine shipped and the tool did not.",
         "The evidence behind Phase 5's ban on shipping a scanner."),
    ),
    "gate-checks.md": (
        ("neither-watches-a-forged-skill",
         "Neither watches a skill written directly into `~/.claude/skills/`.",
         "The gap that makes the shipped gates necessary rather than redundant."),
        ("citing-the-body-means-the-gate-did-not-run",
         'A "because" cell that cites the body rather than a clause of the description '
         "means the gate",
         "The worksheet's verdict rule. Reversed, the worksheet certifies exactly the "
         "judgement Phase 4 calls the whole way this gate goes wrong."),
    ),
}


def skill_text():
    return SKILL_MD.read_text()


def frontmatter(text=None):
    text = skill_text() if text is None else text
    assert text.startswith("---\n"), "SKILL.md does not open with a frontmatter block"
    return text.split("---\n", 2)[1]


def body(text=None):
    text = skill_text() if text is None else text
    return text.split("---\n", 2)[2]


def flat(text):
    return " ".join(text.split())


COMMENT = re.compile(r"<!--.*?-->", re.S)
STRIKE = re.compile(r"~~.*?~~", re.S)


def flatten(text):
    """Line wrapping collapsed and every `*` deleted; nothing else.

    A pinned sentence is a sentence, so it wraps differently in a table cell
    than in a paragraph, and it may be bolded in one place and plain in
    another. Those are the only two differences tolerated, which is what keeps
    the comparison decidable rather than a judgement about wording. Deleting
    every asterisk is blunter than "strip emphasis" and deliberate: a rule
    about which asterisks are emphasis is a rule about markdown parsing.
    """
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


def visible(text):
    """`flatten`, minus the text a reader does not read.

    A substring check is satisfied by a sentence nobody can see, and markdown
    offers two ways to leave one on the page while repealing it: an HTML
    comment renders as nothing, and `~~struck through~~` is how a document
    says "this used to be the rule". Both are removed rather than matched,
    because removal needs no judgement about what the surrounding prose means.
    """
    return flatten(COMMENT.sub(" ", STRIKE.sub(" ", text)))


def heading_pos(text, heading):
    """Offset of a `## ` heading, anchored to the start of a line.

    Phase 5 quotes every house heading inline while describing the house shape,
    so an unanchored `str.index` finds the prose copy and every section lookup
    silently returns the wrong region. That mistake made four tests here green
    against text they were not reading.
    """
    m = re.search(r"^%s" % re.escape(heading), text, re.M)
    assert m is not None, "no %r heading in the body" % heading
    return m.start()


def section(text, heading):
    """Text from a `## ` heading up to the next one."""
    start = heading_pos(text, heading)
    nxt = re.search(r"^## ", text[start + len(heading):], re.M)
    return text[start:] if nxt is None else \
        text[start: start + len(heading) + nxt.start()]


def fences(text, lang=""):
    return re.findall(r"^```%s\n(.*?)^```" % lang, text, re.S | re.M)


def write_skill(root, name, frontmatter_lines, h1="# A heading"):
    d = Path(root) / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\n%s\n---\n\n%s\n\nBody.\n"
                                % ("\n".join(frontmatter_lines), h1))
    return d


def strip_routing_pin(text):
    """Drop the `<!-- routing-pin ... -->` block. It is provenance metadata, not prose."""
    return re.sub(r"\n*<!-- routing-pin\b.*?-->\n*", "\n\n", text, count=1, flags=re.S)


class GateRunner:
    """Extracts the shipped Gate A block and runs it, unmodified except for the
    one placeholder line the document tells the reader to fill in."""

    PLACEHOLDER = "SKILL_DIR=<path to the skill directory>"

    def __init__(self, testcase):
        phase3 = section(body(), "## Phase 3")
        blocks = fences(phase3, "bash")
        testcase.assertEqual(len(blocks), 1, "Phase 3 must ship exactly one bash block")
        self.raw = blocks[0]
        testcase.assertIn(self.PLACEHOLDER, self.raw,
                          "Gate A no longer takes the skill directory as $SKILL_DIR")
        self.script = self.raw.replace(self.PLACEHOLDER, 'SKILL_DIR="$1"')

    def run(self, skill_dir, cwd=None):
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
            fh.write(self.script)
            path = fh.name
        try:
            return subprocess.run(["bash", path, str(skill_dir)],
                                  capture_output=True, text=True, cwd=cwd,
                                  stdin=subprocess.DEVNULL, timeout=60)
        finally:
            os.unlink(path)


class FrontmatterTest(unittest.TestCase):
    """The inert-skill trap, on this skill's own file."""

    def setUp(self):
        self.text = skill_text()
        self.front = frontmatter(self.text)

    def raw_description(self):
        m = re.search(r"^description: (.*)$", self.front, re.M)
        self.assertIsNotNone(m, "SKILL.md needs a description")
        return m.group(1)

    def test_frontmatter_really_parses_as_yaml(self):
        import yaml
        meta = yaml.safe_load(self.front)
        self.assertIsInstance(meta, dict)
        self.assertEqual(meta["name"], SKILL_DIR.name)
        self.assertIsInstance(meta["description"], str)
        self.assertTrue(meta["description"].strip())

    def test_the_description_contains_a_colon_and_is_therefore_quoted(self):
        """The quote is load-bearing here rather than decorative: this
        description really does carry `: `, so removing the quotes makes the
        document unparseable. The next test runs that experiment."""
        import yaml
        desc = yaml.safe_load(self.front)["description"]
        self.assertIn(": ", desc, "if the colon ever goes, this test is why")
        raw = self.raw_description()
        self.assertEqual(raw[:1], '"', "a description containing `: ` must be quoted")
        self.assertEqual(raw[-1:], '"')

    def test_unquoting_this_very_description_really_breaks_the_parse(self):
        import yaml
        with self.assertRaises(yaml.YAMLError):
            yaml.safe_load("name: %s\ndescription: %s\n"
                           % (SKILL_DIR.name, self.raw_description()[1:-1]))

    def test_name_matches_the_directory(self):
        self.assertEqual(re.search(r"^name: *(\S+)", self.front, re.M).group(1),
                         SKILL_DIR.name)

    def test_the_description_obeys_the_caps_it_states(self):
        """Caps derived from the sentence in Phase 2 that states them, so a
        deleted rule takes its own enforcement with it instead of leaving a
        stale number in this file."""
        import yaml
        m = re.search(r"Description at most (\d+) characters; the whole frontmatter\s+"
                      r"block at most (\d+)", body(self.text))
        self.assertIsNotNone(m, "Phase 2 no longer states the description/frontmatter caps")
        desc_cap, front_cap = int(m.group(1)), int(m.group(2))
        self.assertEqual((desc_cap, front_cap), (500, 1024))
        desc = yaml.safe_load(self.front)["description"]
        self.assertLessEqual(len(desc), desc_cap, "description is %d chars" % len(desc))
        self.assertLessEqual(len(self.front), front_cap)

    def test_the_description_carries_both_halves_of_the_trigger(self):
        import yaml
        desc = yaml.safe_load(self.front)["description"]
        self.assertTrue(desc.startswith("Use when"), desc[:40])
        self.assertIn("Do NOT use for", desc, "the negative half of the trigger is missing")

    def deferrals(self):
        import yaml
        desc = yaml.safe_load(self.front)["description"]
        return set(re.findall(r"that is ([a-z][a-z0-9-]+)", desc))

    def test_every_skill_the_description_defers_to_has_a_stated_boundary(self):
        """A trigger that hands a case to a skill it never bounds is a dead end.

        The earlier version of this test demanded that every deferral be a
        directory under `REPO/skills`, which made it structurally impossible to
        name the nearest neighbour when that neighbour ships in a plugin. That
        is exactly the collision Phase 1 exists to surface, so the requirement
        is now the one that carries the meaning: whatever the description
        defers to must be bounded in `## When this is the wrong skill`.
        """
        deferred = self.deferrals()
        self.assertTrue(deferred, "the description names no owner for the cases it declines")
        wrong = section(body(self.text), "## When this is the wrong skill")
        for name in deferred:
            self.assertIn(name, wrong,
                          "the description defers to %r without bounding it in "
                          "`## When this is the wrong skill`" % name)

    def test_the_boundary_reaches_outside_this_repository(self):
        """The blocking finding this skill shipped with: its nearest neighbour
        was an installed plugin skill whose description covers the same three
        cases, and nothing in the draft named it, because the draft only ever
        looked at siblings in this repository. A deferral set drawn entirely
        from `REPO/skills` is the signature of a prior-art sweep that never
        left home."""
        outside = sorted(n for n in self.deferrals()
                         if not (REPO / "skills" / n).is_dir())
        self.assertTrue(outside,
                        "every skill the description defers to ships in this repository, "
                        "so the prior-art sweep never looked at the installed population")
        wrong = flat(section(body(self.text), "## When this is the wrong skill"))
        for name in outside:
            self.assertIn("`%s`" % name, wrong)
        self.assertIn("strictly smaller", wrong,
                      "the narrowing that resolves the overlap is no longer stated")

    def test_at_least_one_deferral_ships_here_and_really_exists(self):
        inside = [n for n in self.deferrals() if (REPO / "skills" / n).is_dir()]
        self.assertTrue(inside, "no deferral names a skill this repository actually ships")


class SilentDefectsTest(unittest.TestCase):
    """The table above the fold, and the gate that has to back it up."""

    HEADING = "## Stop: the six silent defects"

    def setUp(self):
        self.body = body()
        self.section = section(self.body, self.HEADING)
        self.rows = [[c.strip() for c in ln.strip().strip("|").split("|")]
                     for ln in self.section.splitlines()
                     if ln.startswith("|") and not re.match(r"^\|[-|]+\|$", ln)]

    def row(self, needle, where=0):
        hits = [r for r in self.rows[1:] if needle in r[where]]
        self.assertEqual(len(hits), 1,
                         "%d rows match %r in column %d" % (len(hits), needle, where))
        return hits[0]

    def test_the_table_sits_above_the_fold(self):
        """A defect table nobody reaches is decoration."""
        lines = skill_text().splitlines()
        idx = [i for i, ln in enumerate(lines, 1) if ln.startswith(self.HEADING)]
        self.assertEqual(len(idx), 1, idx)
        self.assertLessEqual(idx[0], 60, "the defect table starts at line %d" % idx[0])

    def test_the_heading_count_matches_the_row_count(self):
        """The heading says a number out loud. It has to be the right one."""
        m = re.search(r"^## Stop: the (\w+) silent defects", self.body, re.M)
        self.assertIsNotNone(m, "the defect table heading is gone")
        self.assertEqual(WORDS[m.group(1)], len(self.rows) - 1)

    def test_the_section_is_one_table_and_almost_no_prose(self):
        prose = [ln for ln in self.section.splitlines()[1:]
                 if ln.strip() and not ln.startswith("|")]
        self.assertLessEqual(len(prose), 2,
                             "the defect table has grown prose around it: %r" % prose)

    def test_there_are_exactly_six_defects_each_with_a_rule(self):
        header, rows = self.rows[0], self.rows[1:]
        self.assertEqual(len(header), 3, header)
        self.assertEqual(len(rows), 6, "%d defect rows" % len(rows))
        for row in rows:
            self.assertEqual(len(row), 3, row)
            for cell in row:
                self.assertTrue(cell, "empty cell in row %r" % (row,))

    def test_the_portable_six_in_the_table_match_the_gate_that_enforces_them(self):
        """Two independent statements of the same set, in one document. Drop a
        key from either and they stop agreeing."""
        row = self.row("portable")
        listed = set(re.findall(r"`([a-z-]+)`", row[2]))
        listed -= {"version"}   # named in that cell as the key NOT to ship
        self.assertEqual(len(listed), 6, sorted(listed))
        gate = fences(section(self.body, "## Phase 3"), "bash")[0]
        embedded = set(re.findall(r'"([a-z-]+)"',
                                  re.search(r"PORTABLE = \{(.*?)\}", gate, re.S).group(1)))
        self.assertEqual(listed, embedded,
                         "the defect table and the Gate A block disagree on the six")

    def test_the_rogue_key_row_still_calls_it_an_error(self):
        """A mutation softening this cell to `Harmless everywhere` used to
        survive, because nothing read the middle column."""
        row = self.row("portable")
        self.assertIn("hard error", row[1],
                      "the rogue-key row no longer says a rogue key is an error: %r" % row[1])
        self.assertIn("Nothing else", row[2])

    def test_the_colon_row_demands_the_quotes_unconditionally(self):
        """`Double-quote it whenever it can contain \\`: \\`` is a conditional,
        and a conditional lets the `#` defect through: an author who sees no
        colon leaves the scalar bare."""
        row = self.row("Unquoted `: `")
        self.assertIn("Always double-quote", row[2],
                      "the colon rule has gone conditional again: %r" % row[2])
        self.assertIn("ScannerError", row[1])

    def test_the_hash_row_is_present_and_says_nothing_raises(self):
        row = self.row("Unquoted `#`")
        self.assertIn("nothing raises", row[1],
                      "the `#` row no longer says the failure is silent: %r" % row[1])
        self.assertIn("always", row[2].lower())
        self.assertIn("bare scalar", row[2])

    def test_the_h1_fallback_defect_names_the_h1(self):
        """The measured behavior, not the documented one: a missing or
        non-string description is replaced by the H1, not the first paragraph."""
        row = self.row("H1", where=1)
        self.assertIn("plain string", row[2])

    def test_the_directory_row_demands_an_exact_match(self):
        row = self.row("`name:` disagreeing")
        self.assertIn("must equal the directory name, character for character", row[2],
                      "the identity rule has been softened: %r" % row[2])
        self.assertIn("directory name is the identity", row[1])

    def test_the_validator_row_says_it_passes_broken_yaml(self):
        row = self.row("validate")
        self.assertRegex(row[1], r"exit 0")
        self.assertIn("not a gate", row[2])


class GateAExecutionTest(unittest.TestCase):
    """The shipped Gate A block, run against one fixture per defect.

    These are the tests that make the table above load-bearing. If a check is
    deleted from the block, the fixture that exercises it stops failing.
    """

    def setUp(self):
        self.gate = GateRunner(self)
        self.tmp = tempfile.TemporaryDirectory(prefix="skill-authoring-gate-")
        self.addCleanup(self.tmp.cleanup)

    def assertRejected(self, skill_dir, needle):
        r = self.gate.run(skill_dir)
        self.assertNotEqual(r.returncode, 0,
                            "Gate A accepted %s\n%s" % (skill_dir.name, r.stdout))
        self.assertIn(needle, r.stdout + r.stderr)

    def test_it_accepts_the_skill_that_ships_it(self):
        r = self.gate.run(SKILL_DIR)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("GATE A PASS", r.stdout)
        self.assertIn(SKILL_DIR.name, r.stdout)

    def test_it_accepts_a_minimal_well_formed_skill(self):
        d = write_skill(self.tmp.name, "good-skill",
                        ['name: good-skill', 'description: "Use when X: do Y."'])
        self.assertEqual(self.gate.run(d).returncode, 0)

    def test_it_accepts_the_skill_directory_named_as_a_dot(self):
        """`SKILL_DIR=.`, typed from inside the skill directory, is the shortest
        way to run the block and the one a reader reaches for.

        `pathlib.Path(".").name` is the empty string, so without the
        `.resolve()` the shipped block carries, the name check compares
        `good-skill` against `''` and the gate REJECTS a skill that is fine --
        a false failure that sends the author back to Phase 2 for nothing.
        Deleting `.resolve()` left every other test in this file green.
        """
        d = write_skill(self.tmp.name, "dot-skill",
                        ['name: dot-skill', 'description: "Use when X: do Y."'])
        r = self.gate.run(".", cwd=str(d))
        self.assertEqual(r.returncode, 0,
                         "Gate A rejected its own directory named as `.`\n%s%s"
                         % (r.stdout, r.stderr))
        self.assertIn("GATE A PASS: dot-skill", r.stdout)

    def test_it_accepts_a_block_scalar_description(self):
        """A folded scalar is not the defect; a bare one is. The gate must not
        reject the safe alternative it names."""
        d = Path(self.tmp.name) / "folded-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: folded-skill\ndescription: >-\n"
            "  Use when X happens. Do NOT use for Y.\n---\n\n# H\n\nBody.\n")
        r = self.gate.run(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_defect_1_unquoted_colon(self):
        d = write_skill(self.tmp.name, "colon-skill",
                        ["name: colon-skill", "description: Use when X: do Y."])
        self.assertRejected(d, "ScannerError")

    def test_defect_2_unquoted_hash_is_rejected_before_it_can_truncate(self):
        """The sixth defect. Every other check in the block passes this file:
        it parses, the description is a non-empty string, the name matches, the
        keys are portable and both budgets are met. Only the bare-scalar check
        stands between it and `GATE A PASS`."""
        import yaml
        desc = ("Use when a run is tagged #urgent and needs triage. "
                "Do NOT use for ordinary runs, that is another skill.")
        d = write_skill(self.tmp.name, "hash-skill",
                        ["name: hash-skill", "description: %s" % desc])
        parsed = yaml.safe_load(frontmatter((d / "SKILL.md").read_text()))["description"]
        self.assertLess(len(parsed), len(desc) // 2,
                        "the fixture no longer demonstrates silent truncation")
        self.assertNotIn("Do NOT", parsed)
        self.assertRejected(d, "bare YAML scalar")

    def test_defect_3a_description_that_parses_as_a_mapping(self):
        d = write_skill(self.tmp.name, "mapping-skill",
                        ["name: mapping-skill", "description: {trigger: X}"])
        self.assertRejected(d, "H1")

    def test_defect_3b_description_absent(self):
        d = write_skill(self.tmp.name, "nodesc-skill", ["name: nodesc-skill"])
        self.assertRejected(d, "H1")

    def test_defect_3c_frontmatter_that_is_not_a_mapping_at_all(self):
        """The block has always carried this check and nothing ever exercised
        it, so deleting the two lines survived the whole suite."""
        d = write_skill(self.tmp.name, "sequence-skill",
                        ["- name: sequence-skill", "- description: Use when X."])
        self.assertRejected(d, "not a mapping")

    def test_defect_4_name_disagrees_with_the_directory(self):
        d = write_skill(self.tmp.name, "dir-name-here",
                        ['name: frontmatter-name-here', 'description: "Use when X."'])
        self.assertRejected(d, "does not match directory")

    def test_defect_5_a_non_portable_key(self):
        d = write_skill(self.tmp.name, "rogue-key-skill",
                        ['name: rogue-key-skill', 'description: "Use when X."',
                         "version: 1.0.0"])
        self.assertRejected(d, "non-portable")

    def test_it_rejects_a_file_with_no_frontmatter_at_all(self):
        d = Path(self.tmp.name) / "bare-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("# Bare\n\nNo frontmatter here.\n")
        self.assertRejected(d, "no frontmatter block")

    def test_it_rejects_an_over_long_description(self):
        d = write_skill(self.tmp.name, "windy-skill",
                        ['name: windy-skill', 'description: "Use when %s."' % ("x " * 300)])
        self.assertRejected(d, "chars")

    def test_it_rejects_an_over_long_frontmatter_behind_a_short_description(self):
        """The second half of the budget check. With only the description
        fixture above, raising the frontmatter cap tenfold survived the suite:
        every rejection came from the description length."""
        d = write_skill(self.tmp.name, "padded-skill",
                        ['name: padded-skill', 'description: "Use when X."',
                         "metadata:", '  note: "%s"' % ("y" * 1100)])
        r = self.gate.run(d)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        m = re.search(r"description (\d+) chars, frontmatter (\d+) chars",
                      r.stdout + r.stderr)
        self.assertIsNotNone(m, r.stdout + r.stderr)
        self.assertLessEqual(int(m.group(1)), 500,
                             "this fixture is meant to fail on the frontmatter cap alone")
        self.assertGreater(int(m.group(2)), 1024)

    def test_the_validator_really_does_not_catch_what_the_gate_catches(self):
        """The claim in the table's last row, re-run rather than repeated.

        Skipped, never faked, when the CLI is absent: a green run here has to
        mean the probe actually happened."""
        which = subprocess.run(["which", "claude"], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL)
        if which.returncode != 0:
            self.skipTest("claude CLI not on PATH")
        root = Path(self.tmp.name) / "probe-plugin"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text(
            '{"name": "probe-plugin", "version": "0.0.1", '
            '"description": "Probe.", "author": {"name": "probe"}}\n')
        broken = write_skill(root / "skills", "colon-skill",
                             ["name: colon-skill", "description: Use when X: do Y."])
        self.assertRejected(broken, "ScannerError")
        r = subprocess.run(["claude", "plugin", "validate", str(root), "--strict"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=180)
        self.assertEqual(r.returncode, 0,
                         "the validator now catches the unquoted colon; the table's "
                         "last row needs rewriting:\n%s%s" % (r.stdout, r.stderr))

    def test_the_caveat_about_test_plugin_matches_what_test_plugin_does(self):
        """Phase 3 used to say `SkillFrontmatterTest` "enforces the same
        assertions". It does not: it accepts a bare scalar, its portable key
        set admits `version`, and it checks neither budget. The correction is
        read back out of that file, so it has to be rewritten if the file ever
        catches up."""
        other = REPO / "tests" / "test_plugin.py"
        self.assertTrue(other.is_file(), other)
        src = other.read_text()
        start = src.index("class SkillFrontmatterTest")
        cls = src[start:]
        end = cls.find("\nclass ")
        cls = cls if end < 0 else cls[:end]
        self.assertIn('"version"', cls,
                      "test_plugin now rejects `version`, so the caveat is stale")
        self.assertNotIn("500", cls,
                         "test_plugin now checks a budget, so the caveat is stale")
        f = flat(section(body(), "## Phase 3"))
        self.assertIn("accepts a bare scalar and checks neither budget", f,
                      "Phase 3 overstates what tests/test_plugin.py enforces")


class PriorArtTest(unittest.TestCase):
    """Phase 1 has to enumerate the population that actually exists.

    Two of these run the shipped commands against a tree built here rather than
    against `~/.claude`, because the two defects that shipped in this phase are
    only visible in a tree you control: a skill reachable ONLY through a
    symlink, which `find` without `-L` cannot see, and a description written as
    a block scalar, which a `grep` of `^description:` reads as the literal text
    `description: >-`.
    """

    ROOTS = "~/.claude/skills ~/.claude/plugins/cache ./.claude/skills"

    DECLINE_TOKEN = "QUOKKA4471"
    FOLDED_TOKEN = "NARWHAL8823"

    def setUp(self):
        self.section = section(body(), "## Phase 1")
        self.blocks = fences(self.section, "bash")
        self.assertEqual(len(self.blocks), 2, "Phase 1 ships two commands")

    def run_block(self, block, roots=None):
        if roots is not None:
            self.assertIn(self.ROOTS, block, "the documented roots have changed")
            block = block.replace(self.ROOTS, roots)
        return subprocess.run(["bash", "-c", block], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=120)

    def build_tree(self):
        tmp = tempfile.TemporaryDirectory(prefix="skill-authoring-priorart-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        real = root / "elsewhere"
        write_skill(real, "linked-only-skill",
                    ["name: linked-only-skill",
                     'description: "Use when %s. Do NOT use for anything else, '
                     'that is %s."' % ("x " * 90, self.DECLINE_TOKEN)])
        folded = root / "visible" / "folded-skill"
        folded.mkdir(parents=True)
        (folded / "SKILL.md").write_text(
            "---\nname: folded-skill\ndescription: >-\n"
            "  Use when %s happens.\n---\n\n# H\n\nBody.\n" % self.FOLDED_TOKEN)
        os.symlink(str(real / "linked-only-skill"),
                   str(root / "visible" / "linked-only-skill"))
        return root / "visible"

    def test_all_three_trees_are_enumerated(self):
        joined = "\n".join(self.blocks)
        self.assertIn("~/.claude/skills", joined)
        self.assertIn("~/.claude/plugins/cache", joined,
                      "plugin skills are invisible in the first tree")
        self.assertIn("./.claude/skills", joined,
                      "project-scoped skills are invisible in the other two")

    def test_both_commands_follow_symlinks(self):
        for block in self.blocks:
            self.assertRegex(block, r"find -L ",
                             "a `find` without -L sees none of the symlinked skills")

    def test_the_prose_still_says_the_flag_is_required(self):
        """The commands and the sentence explaining them can drift apart: with
        `-L` still in both blocks, rewording the prose to call it optional left
        the whole suite green."""
        f = flat(self.section)
        self.assertIn("`-L` is load-bearing", f,
                      "Phase 1 no longer says why the flag is there")
        self.assertIn("not optional", f,
                      "Phase 1 no longer says the flag is required")

    def test_the_enumeration_block_runs(self):
        r = self.run_block(self.blocks[0])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")

    def test_the_enumeration_sees_a_skill_reachable_only_by_symlink(self):
        """Installers put skill directories into `~/.claude/skills` as
        symlinks, and `find` does not descend one without `-L`.

        Both halves are run, so this asserts the rule rather than the shipped
        flag: the block as shipped finds the symlinked skill, and the same
        block with `-L` deleted does not. The doctrine is re-derived here every
        run instead of being pinned to a total measured on one machine.
        """
        visible = self.build_tree()
        r = self.run_block(self.blocks[0], str(visible))
        self.assertEqual(r.returncode, 0, r.stderr)
        names = r.stdout.split()
        self.assertIn("linked-only-skill", names,
                      "the sweep misses symlinked skills: %r" % names)
        self.assertIn("folded-skill", names)

        without = self.blocks[0].replace("find -L ", "find ")
        self.assertNotEqual(without, self.blocks[0])
        r2 = self.run_block(without, str(visible))
        self.assertEqual(r2.returncode, 0, r2.stderr)
        names2 = r2.stdout.split()
        self.assertNotIn("linked-only-skill", names2,
                         "`-L` no longer makes any difference, so the rule the skill "
                         "states about it is no longer true: %r" % names2)
        self.assertIn("folded-skill", names2,
                      "the negative control found nothing at all, so it proves nothing")

    def test_the_enumeration_finds_every_installed_skill(self):
        """Compared against an independent walk of the real cache rather than
        trusted. Some packages nest a second level under the version
        directory, which a fixed-depth glob missed."""
        cache = Path.home() / ".claude" / "plugins" / "cache"
        if not cache.is_dir():
            self.skipTest("no plugin cache on this machine")
        walked = {p.parent.name for p in cache.rglob("skills/*/SKILL.md")}
        if not walked:
            self.skipTest("plugin cache holds no skills")
        r = self.run_block(self.blocks[0])
        listed = set(r.stdout.split())
        self.assertTrue(walked <= listed,
                        "the documented enumeration misses %d installed skills, e.g. %r"
                        % (len(walked - listed), sorted(walked - listed)[:3]))

    def test_the_description_listing_returns_whole_descriptions(self):
        """Both halves of the trigger, and a block scalar resolved rather than
        printed as `description: >-`. Truncating with `cut -c1-160` threw away
        the decline half, which is the half that decides whether an overlap is
        real."""
        visible = self.build_tree()
        r = self.run_block(self.blocks[1], str(visible))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        self.assertIn(self.DECLINE_TOKEN, r.stdout,
                      "the decline half of a long description is being truncated away")
        self.assertIn(self.FOLDED_TOKEN, r.stdout,
                      "a block-scalar description is not being parsed")
        self.assertNotIn("description: >-", r.stdout)

    def test_the_description_listing_runs_against_the_real_trees(self):
        r = self.run_block(self.blocks[1])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        self.assertNotIn("UNPARSEABLE", r.stdout.split("\n")[0])

    def test_overlap_is_a_stop_not_a_note(self):
        text = flat(self.section)
        self.assertIn("is a blocking finding, not a note", text,
                      "the polarity of the overlap rule has been inverted")
        self.assertIn("stop and narrow", text)
        self.assertIn("A neighbour installed by a plugin counts", text,
                      "nothing says a plugin neighbour is a neighbour")

    def test_naming_the_neighbours_is_still_required(self):
        self.assertIn("If you cannot name one, you did not look", flat(self.section))


class ProsePolarityTest(unittest.TestCase):
    """Whole clauses, not keywords.

    Every assertion here failed a mutation that a keyword grep let through: the
    Iron Law with its `NOT`s removed, `the description is a summary, never a
    trigger clause`, `a traceback counts as a pass`, `reword the prompt until it
    passes`. A rule that can be inverted without failing a test is a rule the
    file does not really hold.
    """

    def setUp(self):
        self.body = body()

    def test_the_iron_law_still_says_not(self):
        law = re.search(r"## The Iron Law\n\n```\n(.+?)\n```", self.body).group(1)
        self.assertRegex(law, r"^[A-Z ,'-]+$")
        self.assertIn("HAVE NOT PARSED", law)
        self.assertIn("NOT TRIGGER TESTED", law)
        self.assertIn("IS NOT A SKILL", law)

    def test_phase_2_writes_the_description_before_the_body(self):
        p2 = flat(section(self.body, "## Phase 2"))
        self.assertIn("The body is written last", p2)
        self.assertIn("The description is a trigger clause, never a summary", p2)
        self.assertIn("Do not write the body yet", p2)

    def test_phase_2_puts_the_precedence_rule_where_the_router_reads_it(self):
        """The lesson `references/why-these-rules.md` says was measured here.
        Deleting the whole paragraph used to survive the suite."""
        p2 = flat(section(self.body, "## Phase 2"))
        self.assertIn("Put the precedence rule in the description", p2)
        self.assertIn("a precedence rule that lives in the body is a rule the router "
                      "never reads", p2)

    def test_phase_3_treats_a_traceback_as_a_failure(self):
        p3 = flat(section(self.body, "## Phase 3"))
        self.assertIn("Anything other than `GATE A PASS` sends you back to Phase 2", p3)
        self.assertIn("A traceback counts as a failure", p3)

    def test_phase_4_keeps_the_prompts_as_the_fixture(self):
        p4 = flat(section(self.body, "## Phase 4"))
        self.assertIn("the prompts are the fixture, and the description is what changes", p4)
        self.assertIn("Rewriting the prompt so it passes is the failure mode", p4)
        self.assertIn("no prompt in both sets", p4)

    def test_phase_5_forbids_build_artifacts_and_unrun_claims(self):
        p5 = flat(section(self.body, "## Phase 5"))
        self.assertIn("Ship no build artifacts", p5)
        self.assertIn("symlinked whole into the user's config", p5)
        self.assertIn("you have run, and you kept the output", p5)
        self.assertIn("every repository path this file names has to exist", p5)

    def test_phase_6_makes_the_author_run_the_test(self):
        p6 = flat(section(self.body, "## Phase 6"))
        self.assertIn("Run it. A test you wrote and did not run is worth less than no test",
                      p6)

    def test_the_red_flags_cover_the_defects_the_table_names(self):
        """The count is a floor, not a target. It was 8 against a section of
        10, so two flags could be deleted without failing anything -- and
        mutation testing deleted them one at a time, green each time. Adding a
        flag is free; dropping one has to be deliberate. Two flags whose rules
        appear nowhere else (`Overlap is blocking`, `it never settles`) are
        pinned verbatim in `PINNED` as well, so replacing a row rather than
        removing it does not slip past the count."""
        flags = re.findall(r'^- "(.+?)"', section(self.body, "## Red flags"), re.M)
        self.assertGreaterEqual(len(flags), 10, "%d red flags" % len(flags))
        joined = " ".join(flags)
        self.assertIn("validate --strict", joined)
        self.assertIn("let me reword it", joined)
        self.assertIn("no colon in my description", joined)
        self.assertIn("sweep found no neighbour", joined)

    def test_the_rationalizations_are_populated_and_answered(self):
        """Same floor, same reason: 8 against a table of 10 left two rows
        deletable in silence, and the two that carry rules stated nowhere else
        (the linter measurement, the per-skill cap) are pinned verbatim in
        `PINNED` on top of the count."""
        rows = [ln for ln in section(self.body, "## Common rationalizations").splitlines()
                if ln.startswith("|") and not re.match(r"^\|[-|]+\|$", ln)]
        self.assertGreaterEqual(len(rows) - 1, 10, "%d rationalizations" % (len(rows) - 1))
        joined = " ".join(rows)
        self.assertIn("The router never reads the body", joined)
        self.assertIn("The directory is the identity", joined)


class GateBTest(unittest.TestCase):
    """Trigger discrimination, and the section that records it.

    The thresholds and the word-matching rule are read out of Phase 4 rather
    than restated here. Before that, lowering `At least two` to `At least one`
    in the prose changed nothing, because this file carried its own hardcoded
    2 - which is the inverse of what the suite claims to do.
    """

    def setUp(self):
        self.body = body()
        self.text = skill_text()
        self.precision = section(self.body, "## Trigger precision")
        self.phase4 = section(self.body, "## Phase 4")

    def set_sizes(self):
        f = flat(self.phase4)
        total = re.search(r"Write (\w+) prompts\*\*", f)
        halves = re.search(r"(\w+) that MUST fire, (\w+) that must NOT", f)
        self.assertIsNotNone(total, "Phase 4 no longer says how many prompts to write")
        self.assertIsNotNone(halves, "Phase 4 no longer splits the prompts into two sets")
        n_fire, n_decline = WORDS[halves.group(1)], WORDS[halves.group(2)]
        self.assertEqual(WORDS[total.group(1)], n_fire + n_decline,
                         "the two halves do not add up to the total Phase 4 states")
        return n_fire, n_decline

    def thresholds(self):
        f = flat(self.phase4)
        vocab = re.search(r"At least (\w+) must-fire prompts use the description", f)
        overlap = re.search(r"At most (\w+) must-NOT prompt sits in a documented overlap", f)
        self.assertIsNotNone(vocab, "Phase 4 no longer states the vocabulary threshold")
        self.assertIsNotNone(overlap, "Phase 4 no longer states the overlap threshold")
        return WORDS[vocab.group(1)], WORDS[overlap.group(1)]

    def test_the_thresholds_phase_4_states_still_bind(self):
        """Derived from the prose, and then checked for degeneracy against the
        set sizes the same prose states, because deriving alone is not enough:
        softening `At least two` to `At least one` changed no assertion, it
        just stopped the assertion meaning anything.

        A vocabulary threshold has to bind a majority of the must-fire set, or
        one coincidental word satisfies it. An overlap allowance has to be a
        minority of the must-NOT set, or the negative set stops testing the
        clear cases, and it has to be at least one, or the precedence rule from
        Phase 2 is never exercised.
        """
        n_fire, n_decline = self.set_sizes()
        need, allowed = self.thresholds()
        self.assertGreater(need * 2, n_fire,
                           "a vocabulary threshold of %d out of %d does not bind: one "
                           "coincidental word satisfies it" % (need, n_fire))
        self.assertLessEqual(need, n_fire)
        self.assertGreaterEqual(allowed, 1,
                                "zero overlap prompts leaves the precedence rule untested")
        self.assertLess(allowed * 2, n_decline,
                        "an overlap allowance of %d out of %d lets the negative set stop "
                        "testing the clear cases" % (allowed, n_decline))

    def min_word_length(self):
        m = re.search(r"every word of (\w+) or more letters", flat(self.phase4))
        self.assertIsNotNone(m, "Phase 4 no longer defines what counts as a shared word")
        return WORDS[m.group(1)]

    def prompts(self, marker):
        tail = self.precision.split(marker, 1)
        self.assertEqual(len(tail), 2, "no %r block" % marker)
        block = re.split(r"\n(?:Prompts|## )", tail[1], 1)[0]
        return re.findall(r'^\d+\. "(.+?)"', block, re.M)

    def fire(self):
        return self.prompts("Prompts that MUST fire this skill:")

    def decline(self):
        return self.prompts("Prompts that must NOT fire this skill:")

    def vocabulary(self):
        """Content words the positive half of the description actually uses,
        by the rule Phase 4 states."""
        import yaml
        desc = yaml.safe_load(frontmatter())["description"]
        positive = desc.split("Do NOT use for")[0]
        n = self.min_word_length()
        return {w.lower().strip(".,")
                for w in re.findall(r"[A-Za-z][A-Za-z.]{%d,}" % (n - 1), positive)}

    def test_the_positive_half_is_separable_from_the_negative_half(self):
        """`Do NOT use for` must appear exactly once, or the split above
        silently truncates the vocabulary to a handful of words."""
        import yaml
        desc = yaml.safe_load(frontmatter())["description"]
        self.assertEqual(desc.count("Do NOT use for"), 1, desc)

    def test_the_prompt_sets_are_the_size_phase_4_asks_for_and_disjoint(self):
        n_fire, n_decline = self.set_sizes()
        self.assertEqual(len(self.fire()), n_fire, self.fire())
        self.assertEqual(len(self.decline()), n_decline, self.decline())
        self.assertEqual(set(self.fire()) & set(self.decline()), set())

    def test_enough_must_fire_prompts_use_the_descriptions_vocabulary(self):
        need, _ = self.thresholds()
        vocab = self.vocabulary()
        self.assertGreaterEqual(len(vocab), 10, sorted(vocab))
        carrying = [p for p in self.fire()
                    if any(re.search(r"(?<![\w-])%s(?![\w.-])" % re.escape(w), p.lower())
                           for w in vocab)]
        self.assertGreaterEqual(len(carrying), need,
                                "the must-fire prompts share almost no vocabulary with the "
                                "description: %r" % self.fire())

    def test_the_overlap_prompt_count_matches_the_rule_and_names_its_owner(self):
        """A negative set with no skill-shaped prompt never tests the boundary
        this skill's description spends half its length drawing. A negative set
        that is all skill-shaped prompts stops testing the clear cases."""
        _, allowed = self.thresholds()
        block = self.precision.split("Prompts that must NOT fire this skill:", 1)[1]
        items = re.findall(r'^\d+\. "(.+?)"(.*)$', block, re.M)
        self.assertEqual(len(items), 3, items)
        overlapping = [(p, note) for p, note in items
                       if re.search(r"\bskills?\b|SKILL\.md", p, re.I)]
        self.assertEqual(len(overlapping), allowed,
                         "%d must-NOT prompts sit in the overlap: %r"
                         % (len(overlapping), [p for p, _ in overlapping]))
        _, note = overlapping[0]
        owners = re.findall(r"`([a-z][a-z0-9-]+)`", note)
        self.assertTrue(owners, "the overlap prompt names no owning skill: %r" % note)
        wrong_skill = section(self.body, "## When this is the wrong skill")
        for owner in owners:
            self.assertIn(owner, wrong_skill,
                          "%r owns a must-NOT prompt but is not in the boundary section"
                          % owner)

    def test_gate_b_judges_from_the_description_alone(self):
        f = flat(self.phase4)
        self.assertIn("against the description alone", f)
        self.assertIn("Phase 2", f, "a failing prompt must send the author back")

    def test_gate_b_states_a_mechanical_criterion_and_points_at_the_worksheet(self):
        """`Judge each prompt` with no rubric is not a gate. A cold author and
        the shipped test have to be able to reach the same verdict."""
        f = flat(self.phase4)
        self.assertIn("The criterion is mechanical", f)
        self.assertIn("as a whole word, case-insensitively", f)
        self.assertIn("Stems, synonyms and plurals do not count", f)
        self.assertIn("names a skill, a `SKILL.md`, or a neighbouring skill by name", f)
        self.assertIn("references/gate-checks.md", f,
                      "Phase 4 no longer points at the worksheet that runs it")

    def test_the_gate_b_command_prints_the_description_and_nothing_else(self):
        blocks = fences(self.phase4, "bash")
        self.assertEqual(len(blocks), 1, blocks)
        script = blocks[0].replace('"$SKILL_DIR/SKILL.md"', '"%s"' % SKILL_MD)
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        import yaml
        self.assertEqual(r.stdout.strip(),
                         yaml.safe_load(frontmatter())["description"].strip())


class LedgerTest(unittest.TestCase):
    """Phase 6 hands back a fixed shape, or it hands back nothing."""

    def setUp(self):
        self.phase6 = section(body(), "## Phase 6")
        blocks = fences(self.phase6)
        self.assertEqual(len(blocks), 1, "Phase 6 must ship exactly one ledger block")
        self.ledger = blocks[0]

    def test_the_ledger_has_a_field_for_every_gate_and_budget(self):
        labels = [m.group(1) for m in re.finditer(r"^([A-Z][A-Za-z ]*):", self.ledger, re.M)]
        for wanted in ("SKILL", "Prior art", "Gate A", "Gate B", "Budgets", "Test",
                       "Unrun claims", "Unhappy path"):
            self.assertIn(wanted, labels, "the ledger dropped %r: %r" % (wanted, labels))

    def test_a_field_not_done_is_declared_rather_than_omitted(self):
        f = flat(self.phase6)
        self.assertIn("not run", f)
        self.assertIn("omitting it reads as done", f)

    def test_phase_6_says_where_the_test_file_goes_in_both_cases(self):
        """`Write tests/test_seed_<name>.py` is relative to nothing when the
        skill was forged straight into `~/.claude/skills/`, and a cold author
        had to invent a location."""
        f = flat(self.phase6)
        self.assertIn("relative to that repository's root", f)
        self.assertIn("there is no `~/.claude/tests`", f)
        self.assertIn("~/.claude/skills/<name>/tests/test_<name>.py", f)

    def test_phase_6_demands_the_checks_and_says_why(self):
        f = flat(self.phase6)
        self.assertIn("not globally", f,
                      "the reason the caps need a per-skill test is gone")
        for demand in ("re-run Gate A", "re-run Gate B", "build artifacts",
                       "a quoted rather than bare scalar"):
            self.assertIn(demand, f, "Phase 6 no longer demands %r" % demand)

    def test_phase_6_states_both_caps_as_numbers(self):
        f = flat(self.phase6)
        self.assertIn("description at most 500 characters and body at most 500 lines", f,
                      "the bullet that names both caps is gone")

    def test_the_review_is_handed_off_rather_than_dispatched(self):
        f = flat(self.phase6)
        self.assertIn("not a fork", f)
        self.assertIn("skill-compounder", f)


class BodyAndUnhappyPathTest(unittest.TestCase):

    def setUp(self):
        self.phase5 = section(body(), "## Phase 5")
        # Everything below the heading line. The heading itself carries the words
        # "unhappy path", so searching the whole section let a mutation that
        # deleted the directive and kept the heading pass this suite.
        self.flat = flat(self.phase5.split("\n", 1)[1])

    def test_the_unhappy_path_is_required_and_specific(self):
        self.assertRegex(self.flat, r"\*\*[^*]*[Uu]nhappy path[^*]*\*\*",
                         "Phase 5 no longer carries a directive about the unhappy path")
        for demand in ("partway through", "leaves on disk", "puts it back"):
            self.assertIn(demand, self.flat,
                          "the unhappy-path clause no longer asks for %r" % demand)

    def test_unverifiable_prose_goes_to_references_and_executables_to_scripts(self):
        self.assertIn("`references/`", self.flat)
        self.assertIn("`scripts/`", self.flat)

    def test_no_scanner_ships_without_an_external_corpus(self):
        self.assertIn("real external corpus", self.flat)
        self.assertIn("your own fixture", self.flat)

    def test_the_skill_answers_its_own_unhappy_path(self):
        """Phase 5 requires every skill it produces to answer this, and this
        skill shipped without answering its own: a draft abandoned partway and
        left in a skill root is already a listing candidate, so a half-written
        SKILL.md can fire. The clause has to name where a draft lives instead,
        and it has to name a root to be exempt from."""
        for claim in ("not under a skill root", "abandoned partway",
                      "/tmp/skill-draft-", "only after Gate C"):
            self.assertIn(claim, self.flat,
                          "the skill's own unhappy path no longer states %r" % claim)

    def test_the_draft_location_is_outside_every_root_phase_1_sweeps(self):
        """Derived rather than asserted: the roots are counted out of Phase 1's
        own command, so adding a fourth root there and leaving Phase 5 saying
        "all three" fails here."""
        phase1 = section(body(), "## Phase 1")
        roots = [r for r in ("~/.claude/skills", "~/.claude/plugins/cache",
                             "./.claude/skills") if r in phase1]
        self.assertEqual(len(roots), 3, "Phase 1 no longer sweeps three roots: %r" % roots)
        self.assertIn("outside all three roots", self.flat,
                      "Phase 5 no longer sends the draft outside every root Phase 1 sweeps")
        self.assertIn("/tmp/skill-draft-", self.flat,
                      "no concrete location outside the roots is named")

    def test_it_claims_no_reload_behaviour_it_did_not_test(self):
        """The one thing here that cannot be tested from a test process is when
        a running session notices a new directory. So the file must decline to
        claim it rather than assert it."""
        self.assertIn("is not tested here", self.flat,
                      "an untested claim about when a skill goes live has been asserted")


class OwnRecoveryBlockTest(unittest.TestCase):
    """The recovery command in Phase 5 is run, against all three states a
    half-finished run can leave in a skill root, because a recovery step that
    was only read is the shape of failure this whole skill is about."""

    HEADER = "SKILLS=~/.claude/skills; NAME=<the draft>"

    def setUp(self):
        blocks = fences(section(body(), "## Phase 5"), "bash")
        self.assertEqual(len(blocks), 1, "Phase 5 must ship exactly one recovery block")
        self.block = blocks[0]
        self.assertIn(self.HEADER, self.block,
                      "the recovery block no longer takes the root and the name up front")
        tmp = tempfile.TemporaryDirectory(prefix="skill-authoring-recovery-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "skills"
        self.root.mkdir()
        self.dest = self.tmp / "moved"
        self.dest.mkdir()

    def run_recovery(self, name):
        script = self.block.replace(self.HEADER,
                                    'SKILLS="%s"; NAME="%s"' % (self.root, name))
        env = dict(os.environ, TMPDIR=str(self.dest))
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60, env=env)

    def test_a_draft_linked_into_the_root_is_unlinked_and_its_target_survives(self):
        real = write_skill(self.tmp / "elsewhere", "half-written",
                           ["name: half-written", 'description: "Use when unfinished."'])
        os.symlink(str(real), str(self.root / "half-written"))
        r = self.run_recovery("half-written")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(str(self.root / "half-written")),
                         "the live link is still there")
        self.assertTrue((real / "SKILL.md").is_file(),
                        "recovery deleted the draft it was only supposed to unlink")

    def test_a_real_draft_directory_is_moved_out_rather_than_deleted(self):
        d = write_skill(self.root, "half-written",
                        ["name: half-written", 'description: "Use when unfinished."'])
        r = self.run_recovery("half-written")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(d.exists(), "the draft is still live in the root")
        moved = self.dest / "skill-draft-half-written"
        self.assertTrue((moved / "SKILL.md").is_file(),
                        "the only copy of the draft was destroyed, not moved: %s"
                        % sorted(p.name for p in self.dest.iterdir()))

    def test_nothing_in_the_root_says_so_and_touches_nothing(self):
        r = self.run_recovery("never-linked")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("not live", r.stdout)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), [])


class HouseShapeTest(unittest.TestCase):

    def setUp(self):
        self.text = skill_text()
        self.body = body(self.text)

    def line_rules(self):
        m = re.search(r"Hard ceiling: (\d+) body\s+lines\*\*,\s+and a working ceiling of "
                      r"(\d+)", self.body)
        self.assertIsNotNone(m, "Phase 5 no longer states a hard and a working ceiling")
        return int(m.group(1)), int(m.group(2))

    def test_the_house_sections_are_present_in_order(self):
        found = [heading_pos(self.body, s) for s in HOUSE_SECTIONS]
        self.assertEqual(found, sorted(found), HOUSE_SECTIONS)

    def test_the_iron_law_is_fenced_and_alone(self):
        self.assertRegex(self.body, r"## The Iron Law\n\n```\n[A-Z ,'-]+\n```")

    def test_the_body_obeys_the_ceilings_it_states(self):
        """Read out of the prose, and only ever downward.

        An earlier version of this test enforced the bottom of a stated `250 to
        400` range, which made a body FAIL for being short. That is an
        incentive to pad, and it contradicts the same sentence's reason for the
        ceiling: the body is a token cost paid on every turn. There is no floor
        now, in the file or here.
        """
        ceiling, working = self.line_rules()
        self.assertEqual(ceiling, 500)
        self.assertLessEqual(
            working, ceiling - ceiling // 10,
            "a working ceiling of %d under a hard ceiling of %d leaves no room to work in, "
            "which is the same as deleting it. `assertLess` alone admitted 499, and did."
            % (working, ceiling))
        lines = len(self.body.strip().splitlines())
        self.assertLessEqual(lines, working,
                             "body is %d lines, over the working ceiling it states" % lines)

    def test_no_floor_on_body_length_is_stated_or_enforced(self):
        """The rule and its test have to come off together. If prose reinstating
        a floor lands, this fails; if this assertion is deleted, so has the
        sentence that justifies its absence."""
        f = flat(self.body)
        self.assertIn("there is no floor", f,
                      "Phase 5 no longer says the ceiling has no matching floor")
        self.assertNotRegex(f, r"\d+ to \d+ is the range",
                            "a body-length range is back; a floor rewards padding")

    def test_the_wrong_skill_section_names_the_neighbours_and_the_boundary(self):
        wrong = section(self.body, "## When this is the wrong skill")
        for name in ("skill-compounder", "contribute-skill", "writing-skills"):
            self.assertIn(name, wrong, "%r is no longer bounded" % name)
        f = flat(wrong)
        self.assertIn("starts after the decision and stops before the review", f,
                      "the boundary with skill-compounder is no longer stated")
        self.assertIn("fired on the wrong prompt", f,
                      "nothing separates a misfire from a skill that never fires")
        self.assertIn("never fires at all", f)

    def test_the_quick_reference_covers_every_phase(self):
        quick = section(self.body, "## Quick reference")
        for n in range(1, 7):
            self.assertRegex(quick, r"\|%d\. " % n, "phase %d missing from the table" % n)

    def test_every_shipped_reference_is_short_and_linked_from_the_body(self):
        """An unlinked reference is a file nobody opens. `gate-checks.md`
        shipped unreferenced: the only artifact that operationalizes Gate B,
        and `grep -c gate-checks SKILL.md` returned 0."""
        shipped = sorted(p.name for p in REFERENCES.glob("*.md"))
        self.assertEqual(shipped, ["gate-checks.md", "why-these-rules.md"])
        for name in shipped:
            lines = len((REFERENCES / name).read_text().strip().splitlines())
            self.assertLessEqual(lines, 90, "%s is %d lines" % (name, lines))
            self.assertIn("references/%s" % name, self.body,
                          "references/%s is shipped but never linked" % name)

    def test_every_repository_path_the_skill_names_really_exists(self):
        """A cross-reference is a claim. Repointing one at
        `tests/test_frontmatter.py`, which does not exist, used to survive."""
        checked = 0
        for path in [SKILL_MD] + sorted(REFERENCES.glob("*.md")):
            text = path.read_text()
            for ref in set(re.findall(r"`((?:tests|skills|bin|hooks|scripts)/[\w./-]+)`",
                                      text)):
                if "<" in ref or ref.endswith("/"):
                    continue
                checked += 1
                self.assertTrue((REPO / ref).exists(),
                                "%s names %r, which does not exist" % (path.name, ref))
        self.assertGreaterEqual(checked, 2, "no repository cross-references were checked")

    def test_the_skill_directory_ships_no_build_artifacts(self):
        stray = [str(p) for p in SKILL_DIR.rglob("*")
                 if p.name == "__pycache__" or p.suffix in (".pyc", ".pyo")]
        self.assertEqual(stray, [], "build artifacts in the skill directory: %s" % stray)


class NonGoalsTest(unittest.TestCase):
    """The three things a builder subagent at nesting depth two cannot do."""

    def setUp(self):
        self.body = body()

    def test_no_step_asks_the_user_a_question(self):
        """The builder is dispatched non-interactively, so an interview stalls."""
        offenders = [ln for ln in self.body.splitlines()
                     if re.search(r"\bask (the user|them)\b", ln, re.I)]
        self.assertEqual(offenders, [], offenders)

    def test_no_step_dispatches_a_subagent(self):
        """The Agent tool is not reliably present one level below the builder."""
        offenders = [ln for ln in self.body.splitlines()
                     if re.search(r"\b(dispatch|spawn) (a|another|your own) "
                                  r"(sub)?agent\b", ln, re.I)]
        self.assertEqual(offenders, [], offenders)

    def test_nothing_depends_on_a_third_party_plugin(self):
        for path in sorted(SKILL_DIR.rglob("*.md")):
            text = path.read_text()
            for bad in ("superpowers:", "compound-engineering:", "REQUIRED BACKGROUND",
                        "see ../", "](../../"):
                self.assertNotIn(bad, text, "%s depends on %r" % (path.name, bad))

    def test_no_linter_or_scanner_ships_with_this_skill(self):
        self.assertFalse((SKILL_DIR / "scripts").exists(),
                         "this skill ships prose doctrine, not a tool")
        self.assertEqual(sorted(p.name for p in SKILL_DIR.iterdir()),
                         ["SKILL.md", "references"])


class GateChecksReferenceTest(unittest.TestCase):
    """The sweep in references/ is a real program, so it is really run."""

    def setUp(self):
        self.text = (REFERENCES / "gate-checks.md").read_text()
        self.block = fences(self.text, "bash")[0]

    def run_sweep(self, roots=None):
        block = self.block
        if roots is not None:
            old = "~/.claude/skills ~/.claude/plugins/cache"
            self.assertIn(old, block, "the documented roots have changed")
            block = block.replace(old, roots)
        return subprocess.run(["bash", "-c", block], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=180)

    def test_it_points_at_the_enforcement_rather_than_restating_it(self):
        self.assertIn("`skill-compounder` step 3", self.text)
        self.assertIn("tests/test_plugin.py", self.text)
        self.assertNotIn("GATE A PASS", self.text,
                         "the reference has started duplicating the Phase 3 block")

    def test_the_sweep_runs_and_reports_per_skill(self):
        r = self.run_sweep()
        self.assertEqual(r.stderr, "", r.stderr)
        self.assertRegex(r.stdout, r"(?m)^\d+ failing$")
        self.assertRegex(r.stdout, r"(?m)^(ok|warn|FAIL)")

    def test_the_sweep_finds_the_same_skills_the_gate_accepts(self):
        r = self.run_sweep(str(REPO / "skills") + "/..")
        self.assertRegex(r.stdout, r"(?m)^ok   skill-authoring", r.stdout)
        self.assertEqual([ln for ln in r.stdout.splitlines()
                          if ln.startswith("FAIL") and "skill-authoring" in ln], [])

    def test_the_sweep_walks_through_symlinks(self):
        """`rglob("skills/*/SKILL.md")` matched the plugin-cache layout and
        returned 0 under `~/.claude/skills`, where every entry is a symlink."""
        tmp = tempfile.TemporaryDirectory(prefix="skill-authoring-sweep-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        write_skill(root / "elsewhere", "linked-only-skill",
                    ["name: linked-only-skill", 'description: "Use when X: do Y."'])
        (root / "visible").mkdir()
        os.symlink(str(root / "elsewhere" / "linked-only-skill"),
                   str(root / "visible" / "linked-only-skill"))
        r = self.run_sweep(str(root / "visible"))
        self.assertIn("linked-only-skill", r.stdout, r.stdout)
        self.assertNotIn("FAIL", r.stdout)
        self.assertIn("0 failing", r.stdout)

    def test_the_sweep_warns_on_a_bare_scalar_without_counting_it_as_a_failure(self):
        tmp = tempfile.TemporaryDirectory(prefix="skill-authoring-warn-")
        self.addCleanup(tmp.cleanup)
        write_skill(tmp.name, "bare-scalar-skill",
                    ["name: bare-scalar-skill", "description: Use when X happens."])
        r = self.run_sweep(tmp.name)
        self.assertRegex(r.stdout, r"(?m)^warn bare-scalar-skill", r.stdout)
        self.assertIn("0 failing", r.stdout)
        self.assertEqual(r.returncode, 0)

    def test_the_worksheet_forces_a_reason_per_prompt(self):
        self.assertIn("because <clause", self.text)
        self.assertIn("need >= 2", self.text)
        self.assertIn("need exactly 1", self.text)
        self.assertIn("it feels like it would", self.text,
                      "the caveat that names the way this worksheet gets faked is gone")

    def test_the_worksheet_states_the_same_criteria_phase_4_states(self):
        self.assertIn("5+ letters", self.text)
        self.assertIn("whole word, case-insensitive", self.text)
        self.assertIn("names a skill, a `SKILL.md`, or a neighbour by name", self.text)


class WhyTheseRulesTest(unittest.TestCase):

    def setUp(self):
        self.text = (REFERENCES / "why-these-rules.md").read_text()

    def test_it_does_not_repeat_the_unreproducible_claim_as_current(self):
        """The `unquoted colon => empty metadata` mechanism does not reproduce on
        claude 2.1.245. It may only appear here as a retracted claim."""
        for m in re.finditer(r"empty metadata", self.text):
            window = self.text[max(0, m.start() - 260): m.end() + 260]
            self.assertRegex(window, r"does not reproduce|earlier version",
                             "an unretracted empty-metadata claim: %r" % window)

    def test_the_colon_rule_stands_on_portability(self):
        f = flat(self.text)
        self.assertIn("portability", f)
        self.assertIn("ScannerError", f)

    def test_the_measurements_the_body_defers_to_are_actually_here(self):
        f = flat(self.text)
        self.assertIn("46 of 156", f)

    def test_the_one_unrepeatable_number_carries_its_source(self):
        """`46 of 156` cannot be re-derived: the linter that produced it was
        cut. A number a reader cannot re-run and cannot trace is exactly what
        this skill forbids, so the sentence cites the note it came from and
        this checks the note really says it."""
        f = flat(self.text)
        self.assertIn("cannot re-run", f,
                      "the file no longer flags its one unrepeatable measurement")
        note = REPO / "notes" / "2026-08-25-implementation-session.md"
        self.assertIn("`%s`" % note.relative_to(REPO), f,
                      "the unrepeatable measurement no longer cites its source")
        self.assertTrue(note.is_file(), "%s does not exist" % note)
        self.assertIn("46 of 156", note.read_text(),
                      "%s does not record the measurement the reference attributes to it"
                      % note.name)

    def test_the_symlink_fixture_runs_and_prints_what_the_prose_claims(self):
        """This replaces a test that pinned the literal string `103 skills`.

        That assertion enforced the claim's PRESENCE, not its truth, and the
        claim it protected ("103 skills and none of the ten in
        `~/.claude/skills`") was false when re-measured: two of those ten are
        ordinary directories and are found without `-L`. Any total there is a
        property of whichever machine ran the sweep, so the file states none.
        It states the mechanism and ships a fixture, and this runs the fixture
        and reads the numbers out of BOTH the output and the prose. Change
        either and they stop agreeing.
        """
        blocks = [b for b in fences(self.text, "bash") if "mktemp" in b]
        self.assertEqual(len(blocks), 1,
                         "the reproducible `-L` fixture is gone from the reference")
        r = subprocess.run(["bash", "-c", blocks[0]], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = dict(re.findall(r"(with(?:out)? -L):\s*(\d+)", r.stdout))
        self.assertEqual(got, {"without -L": "1", "with -L": "2"},
                         "the fixture no longer shows a symlinked skill being missed "
                         "without -L: %r" % r.stdout)
        f = flat(self.text)
        for label, n in got.items():
            self.assertIn("`%s: %s`" % (label, n), f,
                          "the prose quotes an output the fixture does not produce")

    def test_the_l_rule_quotes_no_total_from_one_machine(self):
        """A count of installed skills is not reproducible off the machine that
        produced it, so it is not evidence a reader can check. The section says
        so, and says it where the next author will be tempted to add one back."""
        sec = section(self.text, "## Why the sweep needs `-L`")
        f = flat(sec)
        self.assertIn("a property of the machine", f,
                      "the section no longer says why it states no total")
        self.assertNotRegex(f, r"\b\d{2,} skills\b",
                            "a machine-specific skill total is back in the `-L` section")

    def test_the_ai_tell_audit_line_count_is_the_measured_one(self):
        """Both files quote a number for a file that ships in this repository,
        so the number is checked against the file rather than against itself.
        It was off by one in both places."""
        other = REPO / "skills" / "ai-tell-audit" / "SKILL.md"
        self.assertTrue(other.is_file(), other)
        # The `<!-- routing-pin` block is machine-readable provenance for the routing
        # claims (tests/test_routing_claims.py), not body prose, and the cited number is
        # a claim about how much prose the file makes a reader absorb.
        # The claim is now HISTORY: ai-tell-audit was brought under the ceiling on
        # 2026-08-26, so pinning it against the current file would assert something
        # false. It is pinned against the commit the prose itself cites, which makes
        # this a claim about the system rather than about the sentence -- correcting
        # the prose must never be what turns this red.
        for path in (REFERENCES / "why-these-rules.md", SKILL_MD):
            # Flattened: prose wraps, so a citation can span a line break on disk and a
            # raw match would fail for a reason that has nothing to do with the claim.
            text = re.sub(r"\s+", " ", path.read_text())
            m = re.search(r"`ai-tell-audit` shipped a\s+(\d+)-line body", text)
            self.assertIsNotNone(m, "%s no longer cites the ai-tell-audit body" % path.name)
            ref = re.search(r"git show ([0-9a-f]{7,40}):skills/ai-tell-audit/SKILL\.md", text)
            self.assertIsNotNone(ref, "%s cites a line count with no commit to check it "
                                      "against" % path.name)
            was = subprocess.run(["git", "show",
                                  "%s:skills/ai-tell-audit/SKILL.md" % ref.group(1)],
                                 cwd=str(REPO), capture_output=True, text=True)
            self.assertEqual(was.returncode, 0,
                             "%s cites commit %s, which this repository does not have"
                             % (path.name, ref.group(1)))
            measured = len(strip_routing_pin(body(was.stdout)).strip().splitlines())
            self.assertEqual(int(m.group(1)), measured,
                             "%s says %s lines; commit %s holds %d"
                             % (path.name, m.group(1), ref.group(1), measured))
            self.assertGreater(measured, 500,
                               "the cautionary example was never over the cap")


class PinnedRuleTest(unittest.TestCase):
    """Every rule in `PINNED`, word for word, in the document that states it.

    This checks PRESENCE, not meaning, and the difference matters. A document
    that carries its sentence and repudiates it in the next clause passes here,
    and nothing in this class is a claim otherwise; see the module docstring
    for where that boundary lies. What it does catch is what mutation testing
    showed the rest of this file missing: a load-bearing sentence deleted,
    softened, reordered, or inverted, with the suite then staying green.
    """

    def setUp(self):
        self.visible = visible(skill_text())

    def test_every_pinned_rule_is_still_stated_word_for_word(self):
        for rule_id, text, why in PINNED:
            wanted = flatten(text)
            self.assertIn(
                wanted, self.visible,
                "SKILL.md no longer states the pinned rule %r, word for word.\n"
                "  expected: %s\n"
                "  why it is pinned: %s\n"
                "If the rule itself changed, update PINNED in %s in the same commit, so "
                "the change is visible in the diff."
                % (rule_id, wanted, why, Path(__file__).name))

    def test_no_pinned_rule_is_left_visible_only_to_a_grep(self):
        """A pinned sentence commented out or struck through has been repealed.

        `visible()` strips both before the search. This asserts the stripping is
        load-bearing rather than decorative: every rule must survive it, so a
        sentence that exists in the raw file and not in the visible text fails
        here with the reason named.
        """
        raw = flatten(skill_text())
        checked = 0
        for rule_id, text, _why in PINNED:
            wanted = flatten(text)
            if wanted not in raw:
                continue  # deleted outright; the test above is the one that names it
            checked += 1
            self.assertIn(
                wanted, self.visible,
                "%r survives in the raw file but not in the visible text, so it has been "
                "commented out or struck through rather than deleted" % rule_id)
        self.assertGreater(checked, 0, "no pinned rule is present in the raw file at all")

    def test_every_pinned_rule_is_still_in_the_section_that_owns_it(self):
        """Presence anywhere is not enough.

        A cold reviewer cut `**The name has to carry the trigger alone.**` out of Phase 2,
        appended it under a new trailing `## Appendix`, and every assertion in this file
        stayed green -- including the pin, which only asked whether the sentence was in the
        file somewhere. A rule filed after the phase it governs is a rule the reader meets
        too late.
        """
        text = skill_text()
        opening = visible(body(text).split("\n## ", 1)[0])
        for rule_id, rule_text, _why in PINNED:
            if rule_id not in PINNED_SECTIONS:
                continue
            heading = PINNED_SECTIONS[rule_id]
            wanted = flatten(rule_text)
            if heading is None:
                where = visible(frontmatter(text))
                name = "the frontmatter"
            elif heading == "":
                where = opening
                name = "the opening, above the first `## ` heading"
            else:
                where = visible(section(body(text), heading))
                name = heading
            self.assertIn(
                wanted, where,
                "the pinned rule %r is no longer in %s. If it moved on purpose, update "
                "PINNED_SECTIONS in %s in the same commit."
                % (rule_id, name, Path(__file__).name))

    def test_pinned_sections_names_only_rules_that_are_pinned(self):
        """A stale entry here advertises a location check for a rule nobody pins."""
        known = {r[0] for r in PINNED}
        for rule_id in PINNED_SECTIONS:
            self.assertIn(rule_id, known,
                          "PINNED_SECTIONS locates %r, which PINNED does not pin" % rule_id)

    def test_the_body_grows_no_section_the_house_shape_does_not_name(self):
        """The `## Appendix` half of the relocation above.

        `test_the_house_sections_are_present_in_order` checks the house sections are all
        there and in order; it says nothing about a fourteenth. A section the house shape
        does not name is where a rule goes to be filed away.
        """
        heads = re.findall(r"^## .+", body(), re.M)
        for head in heads:
            self.assertTrue(
                any(head.startswith(prefix) for prefix in HOUSE_SECTIONS),
                "%r is not one of the house sections. If the shape changed, update "
                "HOUSE_SECTIONS and Phase 5's own sentence together." % head)
        self.assertEqual(
            len(heads), len(HOUSE_SECTIONS),
            "%d `## ` sections against %d house sections: %r"
            % (len(heads), len(HOUSE_SECTIONS), heads))


    def test_the_pinned_ids_are_unique_and_each_carries_its_reason(self):
        ids = [r[0] for r in PINNED]
        self.assertEqual(sorted(ids), sorted(set(ids)))
        for rule_id, _text, why in PINNED:
            self.assertTrue(why.strip(), "%r is pinned with no stated reason" % rule_id)


class DerivedConsistencyTest(unittest.TestCase):
    """Cross-checks between two places in the document that state one fact.

    Nothing here restates a number. Each assertion reads a claim out of the
    section that owns it and applies it to the section that repeats it, so a
    change made in one place and not the other fails rather than drifting.
    """

    def setUp(self):
        self.body = body()

    # -- the house shape Phase 5 prescribes vs. the shape the body has --

    def house_shape(self):
        """The `## ` headings Phase 5 names, in the order it names them."""
        m = re.search(r"The house shape, in this order:\s*\n\n(.+?)\n\n",
                      section(self.body, "## Phase 5"), re.S)
        self.assertIsNotNone(m, "Phase 5 no longer prescribes a house shape")
        named = re.findall(r"`(## [^`]+)`", flat(m.group(1)))
        self.assertGreaterEqual(len(named), 6, named)
        return named

    def test_the_house_shape_phase_5_prescribes_is_the_order_the_body_uses(self):
        """Phase 5 lists the sections a skill must have, in order, and this file
        is subject to its own rule. Reordering that sentence -- moving
        `## Red flags` after `## Common rationalizations`, say -- left the suite
        green while the prose and the document it describes disagreed.

        `## Phase N` is the placeholder for the numbered phases, so it resolves
        to Phase 1. Headings this file adds beyond the house shape
        (`## Stop: the six silent defects`) are not named in the sentence and
        are not required to be: the check is that the prescribed headings appear
        as a subsequence, in the prescribed order.
        """
        positions = []
        for heading in self.house_shape():
            if heading == "## Phase N":
                heading = "## Phase 1"
            positions.append((heading, heading_pos(self.body, heading)))
        offsets = [off for _h, off in positions]
        self.assertEqual(
            offsets, sorted(offsets),
            "Phase 5 prescribes %r, but the body runs them in a different order"
            % [h for h, _o in positions])

    # -- the numbered steps inside a phase --

    def test_every_phase_numbers_its_steps_from_one_without_a_gap(self):
        """Renumbering `**1. Enumerate` to `**2. Enumerate` leaves two step twos
        and no step one, and every assertion about Phase 1 stayed green: they
        look their steps up by text, never by number."""
        for phase in ("## Phase 1", "## Phase 4", "## Phase 6"):
            steps = re.findall(r"^\*\*(\d+)\. ", section(self.body, phase), re.M)
            self.assertTrue(steps, "%s no longer numbers its steps" % phase)
            self.assertEqual(
                [int(n) for n in steps], list(range(1, len(steps) + 1)),
                "%s numbers its steps %s" % (phase, steps))

    # -- the quick reference vs. the phases it summarises --

    def caps(self):
        m = re.search(r"Description at most (\d+) characters; the whole frontmatter block "
                      r"at most (\d+)", flat(section(self.body, "## Phase 2")))
        self.assertIsNotNone(m, "Phase 2 no longer states both budgets")
        return int(m.group(1)), int(m.group(2))

    def test_the_quick_reference_repeats_the_caps_the_phases_state(self):
        """The two numbers in row 2 and the one in row 5 are the only figures in
        the table, and each is stated authoritatively in a phase above it. Read
        them from the phase and require the row to agree, rather than pinning
        the row and freezing the same number in two places."""
        quick = section(self.body, "## Quick reference")
        desc_cap, front_cap = self.caps()
        row2 = next(ln for ln in quick.splitlines() if ln.startswith("|2. "))
        self.assertIn("%d / %d" % (desc_cap, front_cap), row2,
                      "row 2 states caps Phase 2 does not: %r" % row2)
        m = re.search(r"Hard ceiling: (\d+) body\s+lines", self.body)
        self.assertIsNotNone(m, "Phase 5 no longer states a hard ceiling")
        row5 = next(ln for ln in quick.splitlines() if ln.startswith("|5. "))
        self.assertIn("%s-line ceiling" % m.group(1), row5,
                      "row 5 states a ceiling Phase 5 does not: %r" % row5)

    def test_every_find_the_skill_prints_follows_symlinks(self):
        """`references/why-these-rules.md` ships a deliberate `find` without
        `-L`, as half of a before/after demonstration, so this reads SKILL.md
        only. Inside SKILL.md there is no reason for a bare `find`."""
        found = re.findall(r"find (\S+)", skill_text())
        self.assertGreaterEqual(len(found), 3, found)
        for first in found:
            self.assertEqual(
                first.strip("`,."), "-L",
                "SKILL.md prints `find %s`, which skips every symlinked skill directory"
                % first)

    def test_the_defect_table_still_cites_its_measurements(self):
        """Five of the six rows carry a `Measured:` observation, and they are
        what separates the table from an opinion -- the file's own Phase 5 rule
        is that an unverified claim is a defect. A floor: adding a measurement
        is free, quietly dropping one is not."""
        rows = [ln for ln
                in section(self.body, "## Stop: the six silent defects").splitlines()
                if ln.startswith("|") and not re.match(r"^\|[-|]+\|$", ln)][1:]
        cited = [r for r in rows if "Measured" in r]
        self.assertGreaterEqual(
            len(cited), 5,
            "%d of %d defect rows cite a measurement" % (len(cited), len(rows)))


class VocabularyRuleBindsTest(unittest.TestCase):
    """Phase 4's word-length criterion, checked for degeneracy by running it.

    The criterion is derived from the prose -- deliberately, so that softening
    it cannot leave a stale constant behind here. But deriving alone is not
    enough: lowering `five or more letters` to `three or more letters` admits
    `the`, `and`, `but`, `you` and `use` into the description's vocabulary, at
    which point any English sentence satisfies the must-fire rule and the gate
    stops discriminating. The suite stayed green through exactly that edit.

    So the threshold is checked the way the rest of this file checks things:
    with a fixture. A control prompt made of nothing but function words must
    share NO vocabulary with the description. At five letters it shares none;
    at four or three it shares several.
    """

    #: Not a stoplist for the skill to use -- a probe. These words appear in the
    #: description purely as grammar, and a vocabulary rule that admits any of
    #: them is matching sentence structure rather than subject matter.
    FUNCTION_WORDS = ("the", "and", "but", "for", "you", "use", "its", "are",
                      "not", "that", "what", "when", "with", "this", "your")

    def setUp(self):
        self.gate_b = GateBTest(
            "test_the_positive_half_is_separable_from_the_negative_half")
        self.gate_b.setUp()

    def test_the_derived_vocabulary_contains_no_function_words(self):
        vocab = self.gate_b.vocabulary()
        leaked = sorted(w for w in vocab if w in self.FUNCTION_WORDS)
        self.assertEqual(
            leaked, [],
            "Phase 4's word-length criterion admits the function words %s into the "
            "description's vocabulary, so a must-fire prompt satisfies the rule by "
            "containing ordinary English. Raise the letter count Phase 4 states."
            % leaked)

    def test_a_prompt_of_pure_grammar_carries_none_of_the_vocabulary(self):
        """The same check, run rather than reasoned about: the criterion is
        applied to a control prompt exactly as `GateBTest` applies it to the
        real ones."""
        vocab = self.gate_b.vocabulary()
        control = " ".join(self.FUNCTION_WORDS)
        hits = sorted(w for w in vocab
                      if re.search(r"(?<![\w-])%s(?![\w.-])" % re.escape(w), control))
        self.assertEqual(
            hits, [],
            "the control prompt %r, which is nothing but grammar, satisfies Phase 4's "
            "must-fire vocabulary rule via %s" % (control, hits))


class VerbatimBlockTest(unittest.TestCase):
    """Blocks the skill says are fixed, checked as fixed.

    Three of these were checked field by field, or line-count by line-count, and a cold
    reviewer edited inside every one of them without failing anything: the Iron Law grew a
    tail, the ledger lost the clause that makes one of its fields a disclosure, and half
    the red flags and rationalizations had their answers inverted while the counts held.
    """

    def setUp(self):
        self.body = body()

    def test_the_iron_law_is_exactly_the_law(self):
        """`A DRAFT ... IS NOT A SKILL, BUT SHIP IT ANYWAY` satisfies a shape regex of
        `^[A-Z ,'-]+$` and every substring the polarity test looks for."""
        m = re.search(r"## The Iron Law\n\n```\n(.+?)\n```", self.body, re.S)
        self.assertIsNotNone(m, "the Iron Law is no longer a one-line fenced block")
        self.assertEqual(m.group(1), IRON_LAW)

    def test_the_ledger_is_the_ledger_line_for_line(self):
        phase6 = section(self.body, "## Phase 6")
        blocks = [b for b in fences(phase6) if b.startswith("SKILL:")]
        self.assertEqual(len(blocks), 1, "Phase 6 must ship exactly one ledger block")
        self.assertEqual(blocks[0], LEDGER)

    def test_every_red_flag_is_stated_word_for_word(self):
        flags = section(self.body, "## Red flags")
        for line in RED_FLAGS:
            self.assertIn(flatten(line), visible(flags),
                          "the red flag %r has been reworded or removed" % line[:60])

    def test_every_rationalization_is_answered_word_for_word(self):
        rows = section(self.body, "## Common rationalizations")
        for line in RATIONALIZATIONS:
            self.assertIn(flatten(line), visible(rows),
                          "the rationalization %r has been reworded or removed"
                          % line[:60])

    def test_run_this_comes_before_the_block_it_is_about(self):
        """Moved below the fence, `Run this. Do not read it and conclude it would pass.`
        is advice about a block the reader has already skipped. The pin does not care
        where in Phase 3 it sits, so the order is checked here."""
        phase3 = section(self.body, "## Phase 3")
        instruction = phase3.index("Run this. Do not read it and conclude it would pass.")
        fence = phase3.index("```bash")
        self.assertLess(instruction, fence,
                        "Phase 3 tells the reader to run the block after printing it")


class PinnedReferenceTest(unittest.TestCase):
    """The conclusions in `references/` that SKILL.md defers to.

    The body sends the reader to these files for the measurements behind three of its
    rules. Nothing read them for polarity, so a reference could relax the rule its own
    body states -- and one round of review did exactly that, in five places, green.
    """

    def test_every_pinned_reference_conclusion_is_still_stated(self):
        for name, rules in PINNED_REFERENCES.items():
            path = REFERENCES / name
            self.assertTrue(path.is_file(), "%s is no longer shipped" % name)
            seen = visible(path.read_text())
            for rule_id, text, why in rules:
                self.assertIn(
                    flatten(text), seen,
                    "references/%s no longer states %r, word for word.\n"
                    "  expected: %s\n  why it is pinned: %s"
                    % (name, rule_id, flatten(text), why))

    def test_no_reference_contradicts_the_rule_the_body_states(self):
        """Not a general contradiction check -- there is no such thing for prose.

        One specific pairing, because it is the one that was attacked: SKILL.md's first
        defect row says the quoting rule is never optional, and `why-these-rules.md` is
        where a reader goes for the evidence. If the reference has grown a `quote only
        when` clause, the two documents now teach different rules.
        """
        text = visible((REFERENCES / "why-these-rules.md").read_text())
        self.assertNotIn("quote only when", text.lower())
        self.assertNotIn("safe bare", text.lower())


class GateAAcceptsNoBareScalarTest(unittest.TestCase):
    """The bare-scalar check, exercised by a scalar with nothing wrong in it yet.

    Every fixture for this check carried a `#` or a `: `, so making the check conditional
    -- `and ("#" in line or ": " in line[12:])` -- passed all of them. That mutation turns
    the rule the table calls unconditional into the rule the table's own rationalization
    row calls superstition, and it is invisible until the day someone adds a `#`.
    """

    def setUp(self):
        self.gate = GateRunner(self)
        self.tmp = tempfile.TemporaryDirectory(prefix="skill-authoring-bare-")
        self.addCleanup(self.tmp.cleanup)

    def test_a_bare_scalar_with_no_metacharacter_in_it_is_still_rejected(self):
        d = write_skill(self.tmp.name, "plain-bare",
                        ["name: plain-bare",
                         "description: Use when a plain value looks harmless"])
        r = self.gate.run(d)
        self.assertNotEqual(
            r.returncode, 0,
            "Gate A accepted a bare scalar because it happened to contain no `#` and no "
            "`: `. The rule is unconditional: the next edit to that line is what breaks "
            "it.\n%s" % r.stdout)
        self.assertIn("bare YAML scalar", r.stdout + r.stderr)

    def test_the_same_value_quoted_is_accepted(self):
        """The control. Without it the test above passes for any reason at all."""
        d = write_skill(self.tmp.name, "plain-quoted",
                        ["name: plain-quoted",
                         'description: "Use when a plain value looks harmless"'])
        self.assertEqual(self.gate.run(d).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
