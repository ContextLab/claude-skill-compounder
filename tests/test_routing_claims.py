#!/usr/bin/env python3
"""The rot guard for every `## Trigger precision` section, and an honest account of
what it cannot guard.

Background, measured 2026-08-25. Eight skills ship routing claims -- prompts that must
fire the skill and prompts that must not. Not one had ever been run against a real
session. Three were then false:

  * `stale-artifact-check` lost two of three must-fire prompts to
    `superpowers:systematic-debugging`, a skill in a DIFFERENT package.
  * `session-handoff` and `skill-compounder` each listed a must-fire prompt that fires
    nothing at all.

And the routing is brutally sensitive: changing `"Use before debugging logic"` to
`"Use before any other debugging step"` in one description flipped a losing prompt to a
winning one. Four words. So a description edit can silently invalidate every routing
claim sitting under it, and until this file existed nothing noticed.

THREE THINGS THIS FILE ASSERTS
    1. Provenance. Every section carries a `<!-- routing-pin` recording the sha256 of
       the description and of the prompt list it was measured against, plus the date,
       the CLI version and the model. Edit either side and the suite goes red with
       instructions to re-measure.
    2. Content-blindness. `routing_claims.lint()` returns the same findings when every
       prompt is replaced with unrelated text. It is structurally incapable of
       certifying wording.
    3. A shrink-only debt ledger of the sections whose claims are still unverified.

THE LIMIT, WHICH IS THE MOST IMPORTANT LINE IN THIS FILE
    NO STATIC CHECK IN THIS REPOSITORY DECIDES WHETHER A PROMPT FIRES, AND A THIRD OF
    THIS ROT ORIGINATES OUTSIDE THIS REPOSITORY ENTIRELY.

    The brief that produced this file asked for a lint flagging a must-fire prompt that
    "names no concrete subject and carries no precondition", to catch the two false
    ones. There is no honest such rule, and `routing_claims.limits()` carries the
    disproof: within `session-handoff`, the measured-false fragment

        "you've hit your usage limit, we'll pick this up tomorrow"

    has no structural separator from the measured-firing

        "we're almost out of context, let's wrap up"

    -- same shape, same absent work object, same dangling reference, and the firing one
    is shorter. Every candidate rule either passes the first or fails the second.
    Separating the `skill-compounder` pair needs a word list, and a word list is exactly
    what the tombstone in `tests/test_seed_stale.py` forbids: "It measured clause
    position, and a router matches on semantics, so it certified wording rather than
    behavior."

    And `stale-artifact-check` lost its prompts to another package. Installing a plugin
    is enough to falsify a claim here with no commit here. No static check sees that day
    arrive. Only `scripts/probe_routing_claims.py` does, by running the prompts for
    real, and only when a person runs it:

        SKILL_ROUTING_PROBE=1 python3 scripts/probe_routing_claims.py

    ~48 `claude -p --model sonnet --max-turns 3` calls, six in parallel, ~15 minutes,
    real quota. It is gated so it can never fire from `./run_tests.sh` or CI, and the
    model is hardcoded because personal and project skill descriptions were measured
    ABSENT from the router on haiku.
"""

import copy
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import routing_claims as rc  # noqa: E402
import probe_routing_claims as probe  # noqa: E402

# Sections whose claims are NOT yet verified against a real session, with why. This is
# a debt ledger, not an exemption list: it may only ever shrink, and the test below
# fails in BOTH directions, so measuring one and forgetting to remove it here is also a
# failure. Do not add a name to buy a green suite; a new unverified section is the
# thing this file exists to stop.
UNVERIFIED = {
    # Pinned, never run.
    "ai-tell-audit": "unmeasured",
    "claim-provenance": "unmeasured",
    "destructive-op-preflight": "unmeasured",
    "no-silent-stub": "unmeasured",
    "skill-authoring": "unmeasured",
    # Pinned; only the fragment their prose quotes as NOT firing was actually run, so
    # the six listed claims are still unverified.
    "session-handoff": "partial",
    "skill-compounder": "partial",
}

# Measured false on 2026-08-25 by running them. Both have since been removed from the
# shipped sections. They are kept here as the regression corpus.
FALSE_CLAIMS = {
    "session-handoff": "you've hit your usage limit, we'll pick this up tomorrow",
    "skill-compounder": ("That took four attempts to get the ordering right, and we hit "
                         "it last week too."),
}


def claims_for(name):
    for c in rc.all_skills():
        if c["name"] == name:
            return c
    raise AssertionError("no skill named %s" % name)


def sections():
    return [c for c in rc.all_skills() if c["section"]]


class ParseTest(unittest.TestCase):
    """The parser has to be right before anything built on it means anything."""

    def test_every_section_yields_three_and_three(self):
        found = sections()
        self.assertGreaterEqual(len(found), 8)
        for c in found:
            self.assertGreaterEqual(len(c["must_fire"]), 3, c["name"])
            self.assertGreaterEqual(len(c["must_not_fire"]), 3, c["name"])

    def test_prose_quoting_a_rejected_fragment_is_not_collected_as_a_claim(self):
        """Three sections carry a paragraph quoting the very prompt measured NOT to
        fire. Collecting it as a claim would invert the file's meaning, and an earlier
        parser did exactly that by splitting on the heading text as a substring."""
        for name, fragment in FALSE_CLAIMS.items():
            c = claims_for(name)
            # The prose wraps, so the fragment spans a line break on disk. Matching the
            # raw text would fail for a reason that has nothing to do with the claim.
            flat = re.sub(r"\s+", " ", c["section"])
            self.assertIn(re.sub(r"\s+", " ", fragment), flat,
                          "%s no longer records the fragment it measured false" % name)
            self.assertNotIn(fragment, c["must_fire"], name)
            self.assertNotIn(fragment, c["must_not_fire"], name)

    def test_the_heading_is_anchored_not_substring_matched(self):
        """`claim-provenance` and `skill-authoring` quote "## Trigger precision" inside
        their prose. Substring splitting silently returned zero claims for both, which
        is a lint that passes everything."""
        for name in ("claim-provenance", "skill-authoring"):
            c = claims_for(name)
            self.assertEqual(len(c["must_fire"]), 3, name)

    def test_no_list_item_lacks_a_quoted_prompt(self):
        for c in sections():
            self.assertEqual(c["unquoted_items"], [], c["name"])


class PinTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="routing-pin-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def copy_skill(self, name):
        dest = Path(self.tmp) / name
        dest.mkdir()
        shutil.copy(rc.SKILLS / name / "SKILL.md", dest / "SKILL.md")
        return dest / "SKILL.md"

    def mutate(self, path, old, new):
        """Replace and PROVE the replacement landed.

        An anchor that spans a line break makes the replace a silent no-op, and that has
        already produced two false results in this repository. A no-op mutation makes a
        negative test pass for the wrong reason, so it is an error here, not a skip."""
        text = path.read_text()
        self.assertIn(old, text, "anchor %r not present; mutation would be a no-op" % old)
        after = text.replace(old, new, 1)
        self.assertNotEqual(after, text, "mutation did not change the file")
        path.write_text(after)
        self.assertIn(new, path.read_text(), "mutation is not on disk")
        return after

    # -- the pin holds when nothing has moved -------------------------------------

    def test_shipped_pins_agree_with_their_descriptions_and_prompts(self):
        for c in sections():
            if c["pin"] is None:
                self.assertIn(c["name"], UNVERIFIED)
                continue
            self.assertEqual(c["pin"]["description-sha256"], rc.sha256(c["description"]),
                             "%s: pin does not match its own description" % c["name"])
            self.assertEqual(
                c["pin"]["prompts-sha256"],
                rc.prompts_digest(c["must_fire"], c["must_not_fire"]),
                "%s: pin does not match its own prompt list" % c["name"])

    def test_lint_is_clean_apart_from_the_recorded_gap(self):
        findings = rc.lint(rc.all_skills())
        unexpected = [f for f in findings if not f.startswith("claim-provenance:")]
        self.assertEqual(unexpected, [], "\n\n".join(unexpected))

    # -- the pin breaks when something has ----------------------------------------

    def test_a_description_edit_fails_the_pin(self):
        """The measured trigger for this whole mechanism: a four-word description edit
        flipped a routing verdict, and nothing caught it."""
        path = self.copy_skill("stale-artifact-check")
        before = rc.parse_skill(path)
        self.assertEqual(rc.lint([before]), [])
        self.mutate(path, "Use before any other debugging step",
                    "Use before debugging logic")
        after = rc.parse_skill(path)
        self.assertNotEqual(after["description"], before["description"],
                            "the description on disk did not actually change")
        findings = rc.lint([after])
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("the description has changed since the routing claims were "
                      "measured", findings[0])

    def test_the_failure_message_demands_a_re_measurement_not_a_new_hash(self):
        """A message that only reports a hash mismatch invites pasting the new hash in
        and moving on, which re-certifies nothing."""
        path = self.copy_skill("stale-artifact-check")
        self.mutate(path, "Use before any other debugging step", "Use before X")
        message = rc.lint([rc.parse_skill(path)])[0]
        self.assertIn("Re-measure, do not re-hash", message)
        self.assertIn("SKILL_ROUTING_PROBE=1", message)
        self.assertIn("probe_routing_claims.py stale-artifact-check", message)
        self.assertIn("EVERY claim", message)
        self.assertIn("--model sonnet", message)

    def test_editing_a_prompt_fails_the_pin(self):
        path = self.copy_skill("stale-artifact-check")
        self.mutate(path, "I added a console.log at the top of the handler",
                    "I added a print at the top of the handler")
        findings = rc.lint([rc.parse_skill(path)])
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("the prompt list has changed since it was measured", findings[0])

    def test_reordering_prompts_fails_the_pin(self):
        """The recorded result counts prompts positionally, so order is part of it."""
        c = claims_for("stale-artifact-check")
        shuffled = copy.deepcopy(c)
        shuffled["must_fire"] = list(reversed(shuffled["must_fire"]))
        findings = rc.lint([shuffled])
        self.assertTrue(any("prompt list has changed" in f for f in findings), findings)

    def test_adding_a_prompt_that_was_never_measured_fails_the_pin(self):
        """This is how the mechanism catches the two claims that were found false: both
        were listed with nothing behind them. The lint cannot READ them -- see the
        module docstring -- but it can refuse an unmeasured claim, which is what they
        were on the day they shipped."""
        for name, false_prompt in FALSE_CLAIMS.items():
            c = copy.deepcopy(claims_for(name))
            if c["pin"] is None:
                continue
            self.assertEqual(rc.lint([claims_for(name)]), [], name)
            c["must_fire"].append(false_prompt)
            findings = rc.lint([c])
            self.assertTrue(any("prompt list has changed" in f for f in findings),
                            "%s accepted an unmeasured claim: %s" % (name, findings))

    def test_a_missing_pin_fails_and_prints_the_block_to_paste(self):
        c = copy.deepcopy(claims_for("stale-artifact-check"))
        c["pin"] = None
        findings = rc.lint([c])
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("no `<!-- routing-pin` block", findings[0])
        self.assertIn("description-sha256: " + rc.sha256(c["description"]), findings[0])

    def test_a_haiku_measurement_is_rejected(self):
        """Personal and project skill descriptions were measured absent from the router
        on haiku, so a haiku run proves nothing about routing."""
        c = copy.deepcopy(claims_for("stale-artifact-check"))
        c["pin"] = dict(c["pin"], model="haiku")
        findings = rc.lint([c])
        self.assertTrue(any("haiku" in f for f in findings), findings)

    def test_a_measurement_with_no_cli_version_is_rejected(self):
        """A claim can go false with no local edit at all, so the version it held under
        is part of the claim."""
        c = copy.deepcopy(claims_for("stale-artifact-check"))
        c["pin"] = dict(c["pin"], cli="n/a")
        findings = rc.lint([c])
        self.assertTrue(any("no `cli` version" in f for f in findings), findings)

    def test_a_date_and_a_verdict_must_travel_together(self):
        c = copy.deepcopy(claims_for("ai-tell-audit"))
        self.assertEqual(c["pin"]["measured"], "never")
        c["pin"] = dict(c["pin"], result="verified 3/3 must-fire, 3/3 must-not-fire")
        findings = rc.lint([c])
        self.assertTrue(any("travel together" in f for f in findings), findings)


class ContentBlindnessTest(unittest.TestCase):
    """The regression guard on the doctrine, in the shape of the tombstone in
    tests/test_seed_stale.py: a router matches on semantics, so any check that reads a
    prompt certifies wording rather than behavior. `lint()` must be incapable of it."""

    def test_lint_returns_the_same_findings_for_unrelated_prompt_text(self):
        real = claims_for("stale-artifact-check")
        self.assertEqual(rc.lint([real]), [])
        gibberish = copy.deepcopy(real)
        gibberish["must_fire"] = ["lorem ipsum dolor", "sit amet", "consectetur"]
        gibberish["must_not_fire"] = ["adipiscing elit", "sed do", "eiusmod tempor"]
        gibberish["pin"] = dict(
            gibberish["pin"],
            **{"prompts-sha256": rc.prompts_digest(gibberish["must_fire"],
                                                   gibberish["must_not_fire"])})
        self.assertEqual(rc.lint([gibberish]), [],
                         "lint judged prompt content; that certifies wording, not "
                         "behavior")

    def test_the_disproof_is_carried_in_the_code_not_only_in_a_note(self):
        text = rc.limits()
        for fragment in ("we're almost out of context, let's wrap up",
                         "you've hit your usage limit, we'll pick this up tomorrow",
                         "certified wording rather than behavior",
                         "NOT IN THIS REPOSITORY AT ALL"):
            self.assertIn(fragment, text)


class DebtLedgerTest(unittest.TestCase):

    def test_the_unverified_set_is_exactly_what_is_recorded(self):
        """Fails in both directions on purpose. A newly unverified section fails because
        it is not listed; a newly verified one fails because it still is."""
        actual = {}
        for c in sections():
            if c["pin"] is None:
                actual[c["name"]] = "no routing-pin block"
                continue
            verdict = c["pin"]["result"].split(":", 1)[0].split()[0]
            if verdict != "verified":
                actual[c["name"]] = verdict
        self.assertEqual(actual, UNVERIFIED,
                         "the ledger and the shipped pins disagree; update UNVERIFIED "
                         "deliberately, and only after running the probe")

    def test_at_least_one_section_is_actually_verified(self):
        """A ledger that swallowed every section would be an exemption list."""
        verified = [c["name"] for c in sections()
                    if c["pin"] and c["pin"]["result"].startswith("verified")]
        self.assertIn("stale-artifact-check", verified)


class ProbeGateTest(unittest.TestCase):
    """The probe spends real quota, so the gate is load-bearing."""

    def run_probe(self, env_extra):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "HOME": os.environ.get("HOME", "/tmp")}
        env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "probe_routing_claims.py"),
             "--help-is-not-a-flag-here"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            env=env, timeout=60)

    def test_it_refuses_without_the_environment_variable(self):
        proc = self.run_probe({})
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("REFUSING TO RUN", proc.stderr)
        self.assertIn("SKILL_ROUTING_PROBE=1", proc.stderr)

    def test_it_refuses_when_the_variable_is_set_to_anything_else(self):
        for value in ("0", "true", "yes", ""):
            proc = self.run_probe({"SKILL_ROUTING_PROBE": value})
            self.assertEqual(proc.returncode, 2, value)

    def test_nothing_in_the_default_paths_sets_the_gate(self):
        for path in [REPO / "run_tests.sh",
                     REPO / ".github" / "workflows" / "ci.yml"]:
            self.assertNotIn("SKILL_ROUTING_PROBE", path.read_text(), str(path))

    def test_the_model_is_hardcoded_to_sonnet(self):
        self.assertEqual(probe.MODEL, "sonnet")
        source = (REPO / "scripts" / "probe_routing_claims.py").read_text()
        self.assertNotIn("haiku\"", source.replace(probe.__doc__ or "", ""))
        self.assertIn("ABSENT from the router on haiku", probe.__doc__)


class LiveProbeTest(unittest.TestCase):
    """The only test in the repository that verifies a routing claim rather than its
    provenance. Gated: it needs auth and real quota."""

    @unittest.skipUnless(os.environ.get("SKILL_ROUTING_PROBE") == "1",
                         "set SKILL_ROUTING_PROBE=1 to spend ~48 real `claude -p` calls")
    def test_every_routing_claim_holds_against_a_real_session(self):
        results = probe.probe(rc.all_skills())
        ok = probe.report(results, probe.cli_version())
        failed = ["%s %s: %r fired %s" % (r["skill"], r["kind"], r["prompt"], r["fired"])
                  for r in results if not r["pass"]]
        self.assertTrue(ok, "routing claims measured FALSE:\n  " + "\n  ".join(failed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
