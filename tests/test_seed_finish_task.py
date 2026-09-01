#!/usr/bin/env python3
"""`finish-task` had no test of its own, and it is the largest skill here.

That gap is not incidental. This skill's own sibling doctrine says so:

    caps-are-per-skill: Per skill, not globally. A new skill is unguarded until its
    own test exists, which is how a 534-line body shipped.

Every other shipped skill has a file like this one. `finish-task` did not, and the cost
was measured twice on 2026-09-01. A builder deleted Phase 3's rule 3 during its own
reflow while Phase 7 still cited it, and nothing noticed. A cold reviewer then found
Phase 2 printing `PRE-DISPATCH SNAPSHOT TAKEN` and exiting 0 having created nothing --
the third instance of a guard shape this skill's own text calls a defect.

So these tests pin the defect CLASSES that actually recurred across two forges and
eleven review rounds, not a general notion of quality:

  1. the reassuring-branch guard, which is what both live incidents were made of
  2. the destructive command, which deleted a live directory on 2026-08-28
  3. cross-references, which is how a silently deleted rule stayed invisible
  4. the caps, which are the only thing standing between a body and unbounded growth

Nothing here reruns the skill. `tests/test_routing_claims.py` owns its pin, and the
routing probe owns whether it fires.
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "finish-task"
SKILL = SKILL_DIR / "SKILL.md"
REFS = SKILL_DIR / "references"

PLACEHOLDER = "/tmp/finish-REPLACE"
RETYPE_MESSAGE = "MISSED THE RETYPE"


def text():
    return SKILL.read_text(encoding="utf-8")


def body():
    return text().split("---", 2)[2]


def description():
    m = re.search(r'^description:\s*"(.*)"\s*$', text(), re.M)
    return m.group(1) if m else None


def bash_blocks(doc):
    """Every fenced bash block in a document, as (index, source)."""
    return list(enumerate(re.findall(r"```bash\n(.*?)```", doc, re.S)))


def all_docs():
    yield SKILL, text()
    for p in sorted(REFS.glob("*.md")):
        yield p, p.read_text(encoding="utf-8")


class TheReassuringBranch(unittest.TestCase):
    """The defect that shipped twice, in two different phases, and was found both times
    by running the block rather than by reading it.

    A guard whose check cannot be satisfied by an unretyped placeholder, and which then
    falls through to a success message, tells the reader the step happened when nothing
    happened. Phase 1 carried it until 2026-09-01 (`round 1 -- no dispatch yet, nothing
    to subtract`, exit 0). Phase 2 carried it until later the same day
    (`PRE-DISPATCH SNAPSHOT TAKEN`, exit 0, nothing created).
    """

    def test_every_block_using_the_placeholder_says_missed_the_retype(self):
        """The established repair, in the skill's own words. A block that acts on the
        placeholder without this message has no way to tell the reader they skipped a
        step, which is the whole failure."""
        checked = 0
        for path, doc in all_docs():
            for i, block in bash_blocks(doc):
                if "d=" + PLACEHOLDER not in block:
                    continue
                checked += 1
                self.assertIn(
                    RETYPE_MESSAGE, block,
                    "%s bash block %d assigns the placeholder and never says %r, so a "
                    "missed retype is silent there:\n%s"
                    % (path.name, i, RETYPE_MESSAGE, block))
        self.assertGreaterEqual(
            checked, 3,
            "expected at least three blocks to assign the placeholder; found %d. If the "
            "placeholder was renamed, this test is now checking nothing." % checked)

    def test_the_retype_is_announced_no_later_than_the_first_action(self):
        """Order is the whole defect, and the SHAPE of the guard is not the invariant.
        Phase 2's block did test the directory -- two conditionals later, after the
        branch that printed the reassurance. A `[ -d ]` test and a
        `mktemp ... || echo "MISSED THE RETYPE"` are both correct; a test that demanded
        one of them would have rejected a guard that works. What must hold is that the
        reader is told BY THE TIME anything touches `$d`."""
        for path, doc in all_docs():
            for i, block in bash_blocks(doc):
                if "d=" + PLACEHOLDER not in block:
                    continue
                lines = block.splitlines()
                first_use = next((n for n, l in enumerate(lines) if '"$d/' in l), None)
                if first_use is None:
                    continue
                announced = next((n for n, l in enumerate(lines)
                                  if RETYPE_MESSAGE in l), None)
                self.assertIsNotNone(
                    announced,
                    "%s block %d acts on $d and never announces a missed retype:\n%s"
                    % (path.name, i, block))
                self.assertLessEqual(
                    announced, first_use,
                    "%s block %d touches \"$d/\" on line %d but only announces a missed "
                    "retype on line %d, so an unretyped placeholder reaches the action "
                    "first:\n%s" % (path.name, i, first_use + 1, announced + 1, block))

    def test_the_skill_still_states_the_rule_against_this_shape(self):
        """Pinned because it is the sentence that makes the next instance a defect
        rather than an oversight. Deleting it would make this whole class arguable."""
        self.assertIn("a third guard of this shape anywhere here", text(),
                      "the rule naming this defect shape is gone from the skill")


class NoDestructiveCommand(unittest.TestCase):
    """On 2026-08-28 an `rm -rf` over a shared, guessable `/tmp/finish-*` prefix deleted
    a live scratch directory belonging to another run, taking a full-suite log, three
    routing-probe result files and three script backups. The 2026-09-01 forge cut the
    cleanup outright rather than guarding it. This keeps it cut."""

    def test_no_bash_block_issues_rm_rf(self):
        for path, doc in all_docs():
            for i, block in bash_blocks(doc):
                self.assertNotIn(
                    "rm -rf", block,
                    "%s bash block %d issues `rm -rf`. This skill deletes nothing: the "
                    "cleanup was removed after it destroyed another run's evidence. "
                    "Prose ABOUT the hazard is fine; a command is not:\n%s"
                    % (path.name, i, block))

    def test_no_bash_block_makes_a_scratch_dir_under_a_shared_prefix(self):
        """`mktemp -d /tmp/finish-XXXXXX` is safe on creation and unsafe on cleanup: it
        is what made one run's directory matchable by another run's glob."""
        for path, doc in all_docs():
            for i, block in bash_blocks(doc):
                self.assertNotRegex(
                    block, r"mktemp\s+-d\s+/tmp/finish-",
                    "%s bash block %d creates a scratch dir under the shared /tmp/finish- "
                    "prefix:\n%s" % (path.name, i, block))


class TheCrossReferencesResolve(unittest.TestCase):
    """A builder deleted Phase 3's rule 3 in its own reflow while Phase 7 still cited
    it. Nothing in the suite read this skill, so nothing noticed."""

    def test_every_reference_the_skill_cites_exists(self):
        """`the-base-ladder.md` was deleted by a narrowing round. A citation left behind
        would send the reader to a file that is not there.

        Only reference-SHAPED names count. The skill also prints record paths like
        `notes/<date>-what-this-was.md`, which are examples the reader replaces, not
        files that must exist -- reading those as citations is how the first version of
        this test failed."""
        cited = set(re.findall(r"\b([a-z][a-z-]*\.md)\b", text()))
        cited = {c for c in cited if "what-this-was" not in c}
        missing = sorted(c for c in cited if not (REFS / c).is_file())
        self.assertEqual(missing, [],
                         "the skill cites reference files that do not exist: %s" % missing)

    def test_every_reference_file_is_cited_somewhere(self):
        """An orphan is the other half of the same defect: a file added by one round and
        wired in by none, or one left behind after the section that used it was cut."""
        doc = text() + "".join(p.read_text(encoding="utf-8") for p in sorted(REFS.glob("*.md")))
        orphans = [p.name for p in sorted(REFS.glob("*.md")) if p.name not in doc]
        self.assertEqual(orphans, [],
                         "reference files exist that nothing mentions: %s" % orphans)


class TheCaps(unittest.TestCase):
    """Per skill, not globally, which is the doctrine that made this file necessary."""

    def test_the_description_is_within_the_documented_budget(self):
        d = description()
        self.assertIsNotNone(d, "the description does not parse as a double-quoted scalar")
        self.assertLessEqual(len(d), 500, "description is %d chars against the 500 cap" % len(d))
        self.assertTrue(d.startswith("Use when"), d[:40])
        self.assertIn("Do NOT use", d, "no decline clause: %r" % d)

    def test_the_body_is_within_the_hard_ceiling(self):
        n = len(body().strip().splitlines())
        self.assertLessEqual(n, 500, "body is %d lines against the 500-line hard ceiling" % n)

    def test_the_trigger_contract_has_both_halves(self):
        section = text().split("## Trigger precision", 1)
        self.assertEqual(len(section), 2, "no `## Trigger precision` section")
        s = section[1]
        must = len(re.findall(r"^\d+\.\s", s, re.M))
        self.assertGreaterEqual(must, 6,
                                "fewer than six prompts in the trigger contract; three "
                                "must fire and three must not")


if __name__ == "__main__":
    unittest.main(verbosity=2)
