#!/usr/bin/env python3
"""`parallel-agents-one-codebase`, promoted into the seed pool on 2026-09-01.

Like its sibling it arrived from `~/.claude/skills` as the only copy of itself, and it
gets a test before it counts as shipped.

Its description was 780 characters on arrival, 56% over this repository's 500-char cap,
and was cut to fit. Two things in that cut are load-bearing and are pinned below, because
losing either turns a precise skill into one that fires on everything:

  - the trigger is agents WRITING to one tree. A parallel audit, review or search is the
    commonest thing a session does with subagents, and this skill must stay out of it.
  - a worktree or clone per agent needs no partition at all. Without that clause the skill
    fires on the very arrangement that already solves the problem.

The session that promoted it is the evidence for it: two forges edited one checkout, a
test run read a file another agent was mid-write on and reported a failure that did not
exist, and a builder committed a fixture into the real repository. All three are the
symptoms this skill names.
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "parallel-agents-one-codebase" / "SKILL.md"

CORE_PRINCIPLE = ("an agent may only edit files it owns, and reports rather than touches "
                  "anything else")


def text():
    return SKILL.read_text(encoding="utf-8")


def body():
    return text().split("---", 2)[2]


def description():
    m = re.search(r'^description:\s*"(.*)"\s*$', text(), re.M)
    return m.group(1) if m else None


class TheDescriptionKeepsItFromOverFiring(unittest.TestCase):
    """A skill that answers everything displaces the neighbour that should have handled
    it and teaches the session to distrust skill dispatch, which is worse than one that
    occasionally fails to fire. These two clauses are what keep this one narrow."""

    def test_it_declines_read_only_fan_out(self):
        d = description()
        self.assertIsNotNone(d, "description does not parse as a double-quoted scalar")
        low = d.lower()
        self.assertIn("read-only", low,
                      "the description no longer excludes read-only fan-out, which is "
                      "the commonest use of subagents and not this skill's business")
        for word in ("audit", "review", "search"):
            self.assertIn(word, low, "the read-only exclusion no longer names %r" % word)

    def test_it_declines_a_worktree_or_clone_per_agent(self):
        """Separate trees need no partition. Firing there would put a whole ownership
        protocol on top of an arrangement that has already solved the problem."""
        low = description().lower()
        self.assertTrue("worktree" in low or "clone" in low,
                        "the description no longer excuses agents that each have their "
                        "own worktree or clone: %r" % description())

    def test_the_trigger_is_writing_not_reading(self):
        d = description()
        self.assertTrue(any(v in d for v in ("EDIT", "FIX", "REFACTOR")),
                        "the description no longer names the WRITING verbs that are the "
                        "actual trigger: %r" % d)

    def test_it_is_within_budget_and_shaped(self):
        d = description()
        self.assertLessEqual(len(d), 500, "description is %d chars against the 500 cap. "
                                          "It arrived at 780 and was cut once." % len(d))
        self.assertTrue(d.startswith("Use when"), d[:40])
        self.assertIn("Do NOT use", d, "no decline clause")


class ThePrincipleAndTheProcedure(unittest.TestCase):
    def test_the_core_principle_is_stated_word_for_word(self):
        """Everything else in the file is downstream of this one sentence. Pinned whole,
        because a paraphrase that drops `only` or `owns` reads the same and permits the
        opposite."""
        self.assertIn(CORE_PRINCIPLE, body(),
                      "the core principle is gone or reworded; it must read: %r"
                      % CORE_PRINCIPLE)

    def test_the_steps_that_make_it_executable_are_present(self):
        for heading in ("Build the Ownership Table", "Dispatch Prompt Contract"):
            self.assertIn(heading, body(),
                          "%r is missing; without it the principle is advice rather than "
                          "a procedure" % heading)

    def test_it_still_warns_that_a_mid_flight_suite_means_nothing(self):
        """The symptom that actually cost this session time: a whole-suite run against a
        tree other agents were writing to reported a failure that did not exist, and a
        partial log gave a count that was wrong twice."""
        self.assertIn("Global Test Suite Is Meaningless Mid-Flight", body(),
                      "the section on mid-flight suite runs is gone, and it is the one "
                      "symptom of this defect that looks like a real bug report")


class TheCaps(unittest.TestCase):
    def test_the_body_is_within_the_hard_ceiling(self):
        n = len(body().strip().splitlines())
        self.assertLessEqual(n, 500, "body is %d lines" % n)

    def test_the_trigger_contract_has_both_halves(self):
        parts = text().split("## Trigger precision", 1)
        self.assertEqual(len(parts), 2, "no `## Trigger precision` section")
        self.assertGreaterEqual(len(re.findall(r"^\d+\.\s", parts[1], re.M)), 6,
                                "fewer than six prompts: three must fire, three must not")


if __name__ == "__main__":
    unittest.main(verbosity=2)
