#!/usr/bin/env python3
"""The forging protocol must state the routing gate, and state it the way it works.

WHY THIS FILE EXISTS
    Until 2026-08-25 a forge was reported clean when a red-team agent read the
    `## Trigger precision` section and agreed it looked right. Every skill in the seed
    pool cleared that bar. When the prompts were finally run against real sessions,
    three claims were false -- `stale-artifact-check` lost two of three must-fire
    prompts to `superpowers:systematic-debugging`, including its own verbatim example,
    and `session-handoff` and `skill-compounder` each listed a must-fire prompt that
    fires nothing at all. Proposing prompts and judging them are both reading. The gate
    added to `skills/skill-compounder/SKILL.md` requires running them.

WHAT IS ASSERTED HERE, AND IN WHICH OF THE TWO STYLES
    `tests/test_doctrine_sync.py` draws the line: derived facts are extracted from what
    ships and compared, doctrine is pinned as an exact sentence. Both appear below.

    Derived. The probe invocation the protocol prints is checked against the script's
    own gate variable, model and turn limit; the cost figures against the numbers in the
    script's docstring; the must-fire floor against the floor `routing_claims.lint()`
    actually enforces; the pin fields the protocol tells a session to write against what
    `routing_claims.render_pin()` emits and `lint()` accepts. None of these is a
    judgement about wording, and each one catches the drift that has already happened
    twice in this repository: a number that moved in one file and not another.

    Pinned. The three doctrine sentences live in `test_doctrine_sync.py` with the rest of
    the doctrine. What is pinned HERE is narrower and operational: the gate's
    consequence, its model, its failure mode. Those sentences have no "current setting"
    to derive.

WHAT IS NOT ASSERTED
    Nothing here runs a routing probe or decides whether any prompt fires. No static
    check can -- `routing_claims.limits()` carries the disproof. This file checks that
    the protocol TELLS a session to run one, and tells it correctly. The measurement
    itself is `scripts/probe_routing_claims.py`, and only a person spending real quota
    runs it.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import routing_claims as rc  # noqa: E402
import probe_routing_claims as probe  # noqa: E402

SKILL_PATH = ROOT / "skills" / "skill-compounder" / "SKILL.md"
SKILL = SKILL_PATH.read_text()

# The forging protocol only, exactly as test_doctrine_sync.py scopes it: an assertion
# about the protocol must not be satisfiable by a stray match in Troubleshooting.
_forging = re.search(r"### Forging protocol.*?(?=\n## )", SKILL, re.S)
assert _forging, "SKILL.md no longer has a parseable '### Forging protocol' section"
FORGING = _forging.group(0)

PROBE_SCRIPT = "scripts/probe_routing_claims.py"


def flatten(text):
    """Line wrapping collapsed, `*` deleted, dashes normalised.

    The first two match `test_doctrine_sync.flatten`, for the same reason: a pinned
    sentence wraps differently in an indented list item than in a paragraph, and may be
    bolded in one place and plain in another. The third is needed only here, because
    these sentences are compared against a Python docstring that uses ASCII hyphens
    where prose uses an en dash.
    """
    text = text.replace("*", "").replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip()


def steps():
    """The protocol's numbered steps, as {number: body}."""
    parts = re.split(r"\n\*\*(\d+)\. ", "\n" + FORGING)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def gate_step():
    """The one numbered step that tells a session to run the probe.

    Located by what it DOES, not by its number, so renumbering the protocol -- which
    adding this step already required once -- does not silently disarm this file.
    """
    found = [(n, body) for n, body in steps().items() if PROBE_SCRIPT in body]
    assert len(found) == 1, (
        "expected exactly one numbered step in the forging protocol to invoke %s, "
        "found %d: %s. The routing gate is a step in the protocol; if it has been "
        "demoted to a footnote or removed, this whole file needs re-deriving."
        % (PROBE_SCRIPT, len(found), sorted(n for n, _ in found)))
    return found[0]


class GateIsAStepTest(unittest.TestCase):
    """The gate is a numbered step, not an aside.

    Step 3 (`Verify the draft parses`) is a numbered step for a stated reason: a skill
    can pass every red-team round on its content and still ship inert. The routing gate
    is the same claim about reachability rather than loading, so it earns the same
    standing. A footnote is what the old `Trigger precision` checklist row was.
    """

    def test_the_protocol_carries_a_numbered_routing_gate(self):
        number, body = gate_step()
        self.assertGreater(number, 0, "step 0 is the announcement")
        self.assertIn("must-fire", flatten(body))

    def test_the_step_numbers_are_contiguous_from_zero(self):
        """Inserting the gate renumbered three later steps. A gap or a duplicate is the
        signature of that renumbering half-applied."""
        numbers = sorted(steps())
        self.assertEqual(numbers, list(range(len(numbers))),
                         "forging protocol step numbers are not 0..n: %s" % numbers)

    def test_every_cross_reference_names_a_step_that_exists(self):
        """`step 6 applies: narrow the scope` pointed at the cap before the renumber and
        at the loop after it. A reference to a step that does not exist is the cheaper
        half of the same failure and is decidable.

        Two other numbering sequences share the word. The animation's -- `skillforge
        step 3` -- is always written in code, so code spans and fenced blocks come out
        first; the ledger's is always `step 8 of 12`, so a following `of` is excluded.
        What is left is the protocol's own prose references.
        """
        numbers = set(steps())
        prose = re.sub(r"```.*?```", " ", FORGING, flags=re.S)
        prose = re.sub(r"`[^`]*`", " ", prose)
        cited = (re.findall(r"\bstep (\d+)\b(?! of )", prose)
                 + [n for pair in re.findall(r"\bsteps (\d+) to (\d+)\b", prose)
                    for n in pair])
        self.assertTrue(cited, "the forging protocol no longer cross-references any step")
        for c in cited:
            self.assertIn(int(c), numbers,
                          "the forging protocol refers to step %s, which does not exist"
                          % c)


class DerivedFromTheProbeTest(unittest.TestCase):
    """The invocation the protocol prints has to be the invocation that works."""

    def body(self):
        return gate_step()[1]

    def test_the_printed_command_carries_the_scripts_own_gate_variable(self):
        self.assertIn("%s=1 python3 %s" % (probe.GATE, PROBE_SCRIPT), self.body(),
                      "the protocol prints a probe invocation that does not set the "
                      "script's own gate variable, so a session following it gets "
                      "`REFUSING TO RUN`")

    def test_the_protocol_names_the_model_the_probe_hardcodes(self):
        body = self.body()
        self.assertEqual(probe.MODEL, "sonnet")
        self.assertIn("--model %s" % probe.MODEL, body,
                      "the protocol's hand-run command does not pass the model")
        self.assertRegex(
            flatten(body), r"`--model %s`, never haiku" % probe.MODEL,
            "the protocol no longer forbids haiku. Personal and project skill "
            "descriptions were measured ABSENT from the router on haiku, so a haiku "
            "probe proves nothing and a session told only `--model sonnet` will "
            "substitute the cheaper model when quota is short")

    def test_the_hand_run_command_matches_the_probes_own_turn_limit(self):
        """A skill forged outside a `claude-skill-compounder` checkout cannot use the
        script -- it reads only that tree -- so the protocol prints the raw call. If the
        two drift, the hand-run stops measuring the same thing."""
        self.assertIn("--max-turns %s" % probe.MAX_TURNS, self.body())

    def test_the_stated_cost_matches_the_probes_measured_cost(self):
        """The user is choosing to make every forge more expensive. The number they read
        in the protocol has to be the number the script recorded, not a recollection."""
        doc = flatten(probe.__doc__)
        m = re.search(r"is ~(\d+) calls and ~(\d+) minutes", doc)
        self.assertIsNotNone(m, "probe_routing_claims.py no longer records its own cost")
        calls, minutes = m.groups()
        body = flatten(self.body())
        self.assertIn("~%s calls and ~%s minutes" % (calls, minutes), body,
                      "the protocol states a probe cost the script does not")
        self.assertIn("30-90s", body,
                      "the protocol drops the per-prompt latency the script measured")

    def test_a_non_zero_exit_is_documented_as_not_a_failed_measurement(self):
        """The script says so in a comment because discarding those runs threw away a
        correct measurement on the first real call made against it. A hand-run has no
        such comment, so the protocol has to carry it."""
        body = flatten(self.body())
        self.assertIn("A non-zero exit is not a failed measurement", body)
        self.assertIn("--max-turns` exhaustion", body)


class DerivedFromTheLintTest(unittest.TestCase):
    """The floor and the pin fields the protocol quotes are enforced elsewhere."""

    def synthetic(self, n_fire, n_not):
        c = {"name": "synthetic", "section": "x",
             "description": "d", "unquoted_items": [],
             "must_fire": ["f%d" % i for i in range(n_fire)],
             "must_not_fire": ["n%d" % i for i in range(n_not)]}
        c["pin"] = dict(
            zip(rc.PIN_FIELDS,
                [rc.sha256(c["description"]),
                 rc.prompts_digest(c["must_fire"], c["must_not_fire"]),
                 "never", "n/a", "n/a", "unmeasured"]))
        return c

    def enforced_floor(self):
        """The smallest must-fire count `lint()` accepts, found by running it."""
        for n in range(1, 12):
            if not any("must-fire prompts" in f
                       for f in rc.lint([self.synthetic(n, n)])):
                return n
        self.fail("routing_claims.lint() rejects every must-fire count up to 11")

    def test_the_protocol_states_the_floor_the_lint_enforces(self):
        floor = self.enforced_floor()
        self.assertEqual(floor, 3, "the enforced floor moved; the sentence below moves too")
        body = flatten(gate_step()[1])
        self.assertIn("at least three prompts that must fire it and three that must not",
                      body,
                      "the protocol's stated floor and the floor routing_claims.lint() "
                      "enforces (%d) have drifted" % floor)
        self.assertIn("the floor of three must-fire prompts that actually fire is not "
                      "negotiable", body)

    def test_the_unmeasured_pin_the_protocol_dictates_is_what_lint_accepts(self):
        """The protocol tells a session that could not run the probe to write four exact
        field values. If `lint()` rejected them, that instruction would strand the
        honest path and the dishonest one would be the only green one."""
        c = self.synthetic(3, 3)
        self.assertEqual(rc.lint([c]), [], "lint rejects the unmeasured pin")
        body = flatten(gate_step()[1])
        for field in ("`measured: never`", "`model: n/a`", "`cli: n/a`",
                      "`result: unmeasured`"):
            self.assertIn(field, body,
                          "the protocol does not tell a blocked session to write %s"
                          % field)
        rendered = flatten(rc.render_pin(c))
        for field in ("measured: never", "model: n/a", "cli: n/a",
                      "result: unmeasured"):
            self.assertIn(field, rendered,
                          "render_pin() no longer emits %r, so the protocol quotes a pin "
                          "the tooling does not produce" % field)

    def test_the_debt_ledger_the_protocol_names_exists_and_is_a_set_of_names(self):
        ledger = ROOT / "tests" / "test_routing_claims.py"
        body = gate_step()[1]
        self.assertIn("UNVERIFIED", body)
        self.assertIn("tests/test_routing_claims.py", body)
        self.assertRegex(ledger.read_text(),
                         re.compile(r"^UNVERIFIED = \{", re.M))


class PinnedGateSentenceTest(unittest.TestCase):
    """Operational rules with no setting to derive, pinned verbatim.

    The three doctrine sentences -- the gate's consequence, the must-not half, and the
    unmeasured record -- are pinned in `tests/test_doctrine_sync.py` alongside the rest
    of the doctrine, with `<!-- doctrine: -->` anchors. These are the sentences that
    carry the reasoning behind them, and they are pinned here so that softening the
    reasoning is as visible as softening the rule.
    """

    PINNED = (
        ("the description is what changes on a loss",
         "When a must-fire prompt loses, the description is what changes.",
         "A session that instead deletes the prompt, or edits it until it passes, ends "
         "with a skill that still does not fire and a section that no longer claims it "
         "does."),
        ("the four-word sensitivity",
         'changing `"Use before debugging logic"` to `"Use before any other debugging '
         'step"` flipped a losing prompt to a winning one. Four words.',
         "The measured reason the description is the lever, and the reason a re-run is "
         "cheap enough to be mandatory."),
        ("re-run after the last description edit",
         "Re-run it after the last description edit.",
         "A gate run against a draft that the red team then rewrote certifies text "
         "nobody ships."),
        ("the gate expires",
         "The gate proves a claim at a moment; it cannot keep it true.",
         "`stale-artifact-check` lost its prompts to a skill in a DIFFERENT package, so "
         "installing a plugin falsifies a claim here with no commit here. A gate "
         "presented as permanent invites exactly the complacency it replaced."),
    )

    def test_each_pinned_sentence_is_stated_in_the_gate(self):
        body = flatten(gate_step()[1])
        for rule_id, text, why in self.PINNED:
            self.assertIn(
                flatten(text), body,
                "the routing gate no longer states %r, word for word.\n"
                "  expected: %s\n  why it is pinned: %s\n"
                "If the rule itself changed, update PINNED in %s in the same commit."
                % (rule_id, flatten(text), why, Path(__file__).name))


class RedTeamChecklistTest(unittest.TestCase):
    """The checklist row that produced the three false claims."""

    def row(self):
        m = re.search(r"^\|\*\*Trigger precision\*\*\|(.*)\|$", FORGING, re.M)
        self.assertIsNotNone(
            m, "the red-team checklist no longer has a Trigger precision row")
        return m.group(1)

    def test_the_row_requires_running_the_prompts(self):
        row = flatten(self.row())
        self.assertIn("Run", self.row(),
                      "the Trigger precision row does not tell the reviewer to run "
                      "anything: %r" % row)
        self.assertRegex(row, r"claude -p --model %s" % probe.MODEL)
        self.assertIn("step %d" % gate_step()[0], row,
                      "the checklist row does not point at the gate step")

    def test_the_row_that_shipped_three_false_claims_is_gone(self):
        """Pinned as a literal, in the shape of `RETIRED_WORDING` in
        test_doctrine_sync.py: this catches its return by revert or copy-paste, and no
        paraphrase whatsoever. That is the entire claim."""
        retired = ("Propose 3 prompts that SHOULD fire the `description` and 3 that "
                   "should NOT. Does it discriminate?")
        self.assertNotIn(
            retired, SKILL,
            "SKILL.md carries the retired Trigger precision instruction. Proposing "
            "prompts and judging them are both reading, which is how three false "
            "routing claims shipped for months.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
