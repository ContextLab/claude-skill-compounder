#!/usr/bin/env python3
"""The forging doctrine is stated in three places. They must not drift apart.

`.claude/CLAUDE.md` carries the rule in prose: "Its doctrine is mirrored in README.md and
in the user's global ~/.claude/CLAUDE.md stanza. Changing the protocol means updating all
three." That rule has been violated twice, both times the same way: the skill changed and
the prose describing it did not, so the README documented a round cap and a duration
threshold the skill no longer had. A fresh session reading the README would have applied
a rule that does not exist.

Prose cannot enforce prose. Every assertion here derives the expected value from
`skills/skill-compounder/SKILL.md` (the deliverable) or from `hooks/*.sh` (the code) at
runtime, so the docs are checked against the thing they describe rather than against a
constant duplicated into this file.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / "skills" / "skill-compounder" / "SKILL.md").read_text()
README = (ROOT / "README.md").read_text()
REPO_CLAUDE = (ROOT / ".claude" / "CLAUDE.md").read_text()
HOOK = (ROOT / "hooks" / "compound-improvement.sh").read_text()

# Vars matching these are deliberately undocumented: they exist so tests can pin
# nondeterminism, and the repo names them by convention (CI_NOW, INSIGHT_NOW,
# SKILLFORGE_NOW, CI_DEBUG_DUMP, INSIGHT_DEBUG_DUMP). See CLAUDE.md, "No mocks, ever".
PIN = re.compile(r"_(NOW|DEBUG_DUMP)$")


class RoundCapTest(unittest.TestCase):
    """The cap moved 3 -> 5 in the skill and stayed 3 in the README for a full release."""

    def cap(self):
        m = re.search(r"Cap at (\d+) rounds", SKILL)
        self.assertIsNotNone(m, "SKILL.md no longer states a round cap in a parseable form")
        return int(m.group(1))

    def test_readme_states_the_same_cap(self):
        self.assertRegex(
            README, r"cap at %d rounds" % self.cap(),
            "README's forging diagram disagrees with SKILL.md about the round cap",
        )

    def test_escalated_cap_agrees(self):
        """Both name the same number for a complex or important skill."""
        skill_hi = re.search(r"or (\d+) for a skill that is complex", SKILL)
        self.assertIsNotNone(skill_hi, "SKILL.md no longer states an escalated cap")
        self.assertIn(
            "(%s for a complex" % skill_hi.group(1), README,
            "README and SKILL.md disagree about the escalated round cap",
        )

    def test_status_line_example_budgets_the_documented_cap(self):
        """SKILL.md budgets steps as 2 + 2 x rounds. The README's example must show that."""
        m = re.search(r"▕[█·]+▏ (\d+)/(\d+)", README)
        self.assertIsNotNone(m, "README's status-line example is no longer parseable")
        self.assertEqual(
            int(m.group(2)), 2 + 2 * self.cap(),
            "README's example forge budgets a step count that is not 2 + 2 x the cap",
        )


class OrphanedConstantTest(unittest.TestCase):
    """A doc must not attribute a threshold constant to a skill that has dropped it."""

    def test_no_doc_cites_a_duration_the_skill_does_not_have(self):
        pattern = re.compile(r">\s?(\d+)\s?min")
        for name, text in (("README.md", README), (".claude/CLAUDE.md", REPO_CLAUDE)):
            for cited in pattern.findall(text):
                self.assertRegex(
                    SKILL, r">\s?%s\s?min" % cited,
                    "%s cites a >%s min threshold that SKILL.md does not define"
                    % (name, cited),
                )


class TuningTableTest(unittest.TestCase):
    """Every knob the hook actually reads has to be findable in the README."""

    def hook_vars(self):
        found = {v for v in re.findall(r"CI_[A-Z_]+", HOOK) if not PIN.search(v)}
        self.assertTrue(found, "no tunable CI_* variables found in the hook")
        return found

    def table_rows(self):
        m = re.search(r"\|Variable\|Default\|Set it in\|Meaning\|\n\|-\|-\|-\|-\|\n((?:\|.*\n)+)", README)
        self.assertIsNotNone(m, "README tuning table is missing or reshaped")
        return re.findall(r"^\|`([^`]+)`\|", m.group(1), re.M)

    def test_every_tunable_the_hook_reads_is_documented(self):
        for var in sorted(self.hook_vars() - set(self.table_rows())):
            self.fail("hooks/compound-improvement.sh reads %s but the README "
                      "tuning table does not list it" % var)

    def test_no_documented_tunable_is_imaginary(self):
        """A row for a variable nothing reads is worse than no row."""
        readable = HOOK + (ROOT / "statusline" / "statusline.sh").read_text()
        for var in self.table_rows():
            if var.startswith("CI_"):
                self.assertIn(var, readable,
                              "README documents %s but no script reads it" % var)

    def test_stated_counts_match_the_table(self):
        rows = self.table_rows()
        total = re.search(r"All (\w+) are environment variables", README)
        self.assertIsNotNone(total, "README no longer states how many tunables there are")
        words = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10}
        self.assertEqual(words.get(total.group(1)), len(rows),
                         "README says there are %s tunables; the table lists %d"
                         % (total.group(1), len(rows)))
        ci = re.search(r"Only the (\w+) `CI_\*` variables", README)
        self.assertIsNotNone(ci, "README no longer states how many CI_* vars the hook reads")
        self.assertEqual(words.get(ci.group(1)),
                         len([r for r in rows if r.startswith("CI_")]),
                         "README's CI_* count disagrees with its own table")


class RedTeamDoctrineTest(unittest.TestCase):
    """Two rules the skill treats as load-bearing must survive into the README."""

    def test_reviewer_is_never_a_fork(self):
        for name, text in (("README.md", README), (".claude/CLAUDE.md", REPO_CLAUDE)):
            self.assertIn("fork", text.lower(),
                          "%s no longer warns that the red-teamer must not be a fork" % name)

    def test_leading_prompt_rule_is_mirrored(self):
        if "Never hand a reviewer a list of what not to flag" not in SKILL:
            self.skipTest("SKILL.md no longer carries the leading-prompt rule")
        self.assertIn("Never hand a reviewer a list of what not to flag", README,
                      "SKILL.md carries the leading-prompt rule and the README does not")

    def test_retirement_archives_the_source_not_the_link(self):
        if "realpath" not in SKILL:
            self.skipTest("SKILL.md no longer describes symlink-aware retirement")
        self.assertIn("realpath", README,
                      "SKILL.md resolves symlinks before archiving; the README describes "
                      "the naive move that leaves the real directory in place")



class SeedPoolTest(unittest.TestCase):
    """Adding a skill to skills/ without adding its README row is the same drift.

    It happened: `ai-tell-audit` shipped, and the README kept describing four seed skills
    and a pool that did not contain it.
    """

    def shipped(self):
        return sorted(d.name for d in (ROOT / "skills").iterdir()
                      if (d / "SKILL.md").is_file())

    def table_rows(self):
        m = re.search(r"\|Skill\|Fires when\|The failure it prevents\|\n\|-\|-\|-\|\n((?:\|.*\n)+)",
                      README)
        self.assertIsNotNone(m, "README seed-pool table is missing or reshaped")
        return re.findall(r"^\|`([^`]+)`\|", m.group(1), re.M)

    def test_every_shipped_skill_is_documented(self):
        """Not necessarily in the pool table: `skill-compounder` and `contribute-skill`
        have their own sections. But a skill nobody mentions is a skill nobody finds."""
        for name in self.shipped():
            # assertIn would print the whole README on failure. A 20 KB dump for a
            # one-word finding is output nobody reads.
            self.assertTrue(name in README,
                            "skills/%s ships but the README never names it" % name)

    def test_no_row_describes_a_skill_that_does_not_ship(self):
        shipped = set(self.shipped())
        for name in self.table_rows():
            self.assertIn(name, shipped,
                          "README documents a seed skill `%s` that does not ship" % name)

    def test_the_stated_pool_size_matches(self):
        m = re.search(r"(\w+) skills ship with the package", README)
        self.assertIsNotNone(m, "README no longer states the seed-pool size")
        words = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10}
        self.assertEqual(words.get(m.group(1).lower()), len(self.table_rows()),
                         "README says %s skills ship; the table lists %d"
                         % (m.group(1), len(self.table_rows())))


if __name__ == "__main__":
    unittest.main(verbosity=2)
