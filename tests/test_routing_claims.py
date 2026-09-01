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

    Six prompts per section, each submitted `--runs N` times (default 3), one real
    `claude -p --model sonnet --max-turns 3` call per draw, six at a time. ~54 calls per
    run over the nine pinned skills, so ~162 at the default. It is gated so it can never
    fire from `./run_tests.sh` or CI, and the model is hardcoded because personal and
    project skill descriptions were measured ABSENT from the router on haiku.

    ONE DRAW IS NOT A VERDICT. Routing here is stochastic -- one unchanged description
    gave 3/3, then 1/3, then 2/3 -- so the probe aggregates k/N per prompt and a section
    is `verified` only when every prompt won every draw. A prompt that wins some draws
    and loses others is a `SPLIT`, reported and pinned as `partial`. Re-running until a
    green appears certifies the draw, not the claim.
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
    # Emptied 2026-08-25, when skill-compounder's six claims were measured for real and
    # its pin promoted to verified. Re-entered 2026-08-26: the SAME section, unedited,
    # was probed three times at --runs 3 in one day and scored 9/9, 8/9, 9/9. "The skill
    # I just used told me to run it from the wrong directory." fired nothing at all on
    # one draw, so it stands at 8/9 over nine draws and the pin says `partial`.
    #
    # This entry is the debt that verdict creates, not an exemption bought to get a
    # green suite. It clears when the DESCRIPTION changes and the whole section measures
    # clean again -- never by re-running until a pass turns up, which is what pinning
    # the third pass alone would have been.
    #
    # Re-measured 2026-08-31 at CLI 2.1.252: 8/9 again, and the SAME prompt at 2/3. The
    # description has not changed, so the clearing condition has not been met.
    "skill-compounder": "partial",

    # THREE ENTRIES ADDED 2026-08-31, and what created them is a measurement STANDARD,
    # not a regression. All three previously read `verified 3/3 must-fire, 3/3
    # must-not-fire`, pinned 2026-08-25 at CLI 2.1.245. Three draws is ONE run of three
    # prompts: those pins predate the three-run floor and had never been held to it.
    # The first --runs 3 measurement of them, at CLI 2.1.252, puts one prompt of each at
    # 2/3.
    #
    # So this ledger grew, and the growth is the ledger working rather than failing. The
    # dishonest alternative was available and was not taken: leaving a `verified 3/3`
    # pin standing over evidence that contradicts it. A prompt shown at 2/3 has not
    # passed, and these three had simply never been asked the question three times.
    #
    # Each clears the same way as the entry above: change the DESCRIPTION, then measure
    # the whole section clean. Not by re-running until a pass turns up.
    "claim-provenance": "partial",           # 'Our CONTRIBUTING page says broken frontmatter...' 2/3
    "destructive-op-preflight": "partial",   # 'clear the local commits on this branch...' 2/3
    "finish-task": "partial",                # 'Wrap up this branch: get it reviewed...' 2/3

    # `no-silent-stub` was here from 2026-08-28, at 8/9: the split had MOVED rather than
    # cleared, from "just make the suite pass" to "Finish this parser. For the branches
    # you can't do yet, return an empty list.", and a later clean pass does not un-show a
    # prompt already shown unreliable.
    # REMOVED 2026-08-31, on this ledger's own stated clearing condition and not on a
    # re-run: the description CHANGED (it was 572 chars, over the 500 cap, and is now
    # 498), and the whole section then measured 9/9 must-fire and 9/9 must-not-fire at
    # CLI 2.1.252. Left as a comment because this ledger fails in both directions and the
    # entry's removal is the evidence that it was paid, not skipped.
    #
    # `contribute-skill` was here from 2026-08-28 as `unmeasured` -- it shipped with no
    # `## Trigger precision` section at all, so nothing had ever checked when it fires.
    # REMOVED the same day, on a first measurement of 9/9 must-fire and 9/9 must-not-fire
    # draws at CLI 2.1.250. Left as a comment because this ledger fails in both directions
    # and the entry's removal is the evidence that it was paid, not skipped.
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

    def test_a_prompt_wrapped_across_lines_is_still_one_prompt(self):
        """`_QUOTED` matches within one line, so a prompt whose quote opened on one line
        and closed on the next matched nothing and was filed as malformed. Six prompts on
        the page parsed as two, and the skill fell under both three-prompt floors while
        looking complete to anyone reading it. Measured 2026-08-28 on a real installed
        skill that wrapped its prompts at 78 columns.

        Wrapping is ordinary prose formatting, not an authoring error, so the parser is
        what was wrong. A real file on disk, parsed by the real parser."""
        d = Path(self.tmp) / "wrapped"
        d.mkdir()
        (d / "SKILL.md").write_text(
            '---\n'
            'name: wrapped\n'
            'description: "Use when a thing happens. Do NOT use otherwise."\n'
            '---\n\n'
            '# Wrapped\n\n'
            '## Trigger precision\n\n'
            'Prompts that MUST fire this skill:\n\n'
            '1. "I lowered the cap and nothing changed at all — the output is the\n'
            '   same either way."\n'
            '2. "Check that this size limit actually fires before we ship it."\n'
            '3. "This script has a check that is supposed to reject huge files, but\n'
            '   we have never seen it reject anything — can you prove it runs?"\n\n'
            'Prompts that must NOT fire this skill:\n\n'
            '1. "The deploy check fired and blocked my release." (already seen firing)\n'
            '2. "Write a rate limiter capping requests to 100 per minute."\n'
            '3. "My tests crash with a NullPointerException in the parser — help me\n'
            '   track it down." (that territory belongs to systematic debugging)\n')
        c = rc.parse_skill(d / "SKILL.md")
        self.assertEqual(c["unquoted_items"], [],
                         "a wrapped prompt was reported malformed: %r" % c["unquoted_items"])
        self.assertEqual(len(c["must_fire"]), 3, c["must_fire"])
        self.assertEqual(len(c["must_not_fire"]), 3, c["must_not_fire"])
        # The whole prompt, both lines joined -- not the first line alone.
        self.assertEqual(c["must_fire"][0],
                         "I lowered the cap and nothing changed at all — the output is "
                         "the same either way.")
        # And a trailing parenthetical after a closing quote is NOT swallowed into it.
        self.assertEqual(c["must_not_fire"][0],
                         "The deploy check fired and blocked my release.")

    def test_a_skill_with_no_trigger_section_is_reported_not_skipped(self):
        """`lint` skipped a section-less skill under the comment "a skill may legitimately
        ship no routing claims at all". The cost, measured 2026-08-28 over a real installed
        skills directory: the summary read "10 skill(s) with routing claims, 7 finding(s)"
        while FOUR installed skills carried no section and were never named. A reader
        cannot tell that from full coverage."""
        d = Path(self.tmp) / "silent"
        d.mkdir()
        (d / "SKILL.md").write_text(
            '---\nname: silent\ndescription: "Use when X. Do NOT use for Y."\n---\n\n'
            '# Silent\n\nIt does a thing. It never says when it fires.\n')
        findings = rc.lint([rc.parse_skill(d / "SKILL.md")])
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("no `## Trigger precision` section", findings[0])

    def test_a_description_edit_fails_the_pin(self):
        """The measured trigger for this whole mechanism: a four-word description edit
        flipped a routing verdict, and nothing caught it."""
        path = self.copy_skill("stale-artifact-check")
        before = rc.parse_skill(path)
        self.assertEqual(rc.lint([before]), [])
        self.mutate(path, "Use when an edit you made appears",
                    "Use when debugging logic")
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
        self.mutate(path, "Use when an edit you made appears", "Use when X")
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
        # Built synthetically rather than from a shipped unmeasured pin: the last
        # shipped fixture (ai-tell-audit) got measured for real on 2026-08-25, and the
        # rule must outlive every skill graduating out of UNVERIFIED.
        c = copy.deepcopy(claims_for("ai-tell-audit"))
        c["pin"] = dict(c["pin"], measured="never",
                        result="verified 3/3 must-fire, 3/3 must-not-fire")
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


class DrawAggregationTest(unittest.TestCase):
    """A verdict is k/N over N draws, and this is where the counting happens.

    WHY IT IS TESTED THIS HARD. Two defects shipped in this repository as guards that
    never executed -- a `wc -c` value a numeric test read as non-numeric, and a `grep`
    alternation written in basic-regex syntax where the bar is literal. Both looked
    correct and did nothing. So the count is not trusted because the report looks
    plausible: each case below flips a draw DELIBERATELY and asserts the number moves.

    No mocks. `jobs_for`, `won`, `aggregate` and `pin_result` are pure functions called
    for real; only `run_prompt` spends quota, and none of these touch it.
    """

    def draws(self, wins, skill="demo", kind="must-fire", prompt="P", error=None):
        return [{"skill": skill, "kind": kind, "prompt": prompt, "draw": i, "win": w,
                 "fired": [skill] if w else [], "error": error, "seconds": 1.0}
                for i, w in enumerate(wins)]

    def one(self, wins, **kw):
        return probe.aggregate(self.draws(wins, **kw))[0]

    # -- the fan-out is actually N-fold -------------------------------------------

    def test_every_prompt_is_submitted_once_per_run(self):
        """The bug this catches is a `--runs 3` that samples once and reports 3/3."""
        claims = [claims_for("skill-compounder")]
        prompts = probe.prompts_for(claims)
        self.assertEqual(len(prompts), 6, "the section is not 3 + 3 any more")
        for runs in (1, 3, 5):
            jobs = probe.jobs_for(claims, runs)
            self.assertEqual(len(jobs), len(prompts) * runs,
                             "runs=%d produced %d jobs, not %d"
                             % (runs, len(jobs), len(prompts) * runs))
            for key in prompts:
                got = sorted(j[3] for j in jobs if j[:3] == key)
                self.assertEqual(got, list(range(runs)),
                                 "%r was submitted with draw indices %s, not 0..%d"
                                 % (key, got, runs - 1))

    def test_a_run_count_below_one_is_refused_rather_than_silently_zero(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                probe.jobs_for([claims_for("skill-compounder")], bad)

    # -- the count moves when a draw is deliberately failed ------------------------

    def test_flipping_one_draw_moves_the_count_and_the_verdict(self):
        clean = self.one([True, True, True])
        self.assertEqual((clean["wins"], clean["runs"]), (3, 3))
        self.assertEqual(probe.verdict(clean), "PASS")

        rows = self.draws([True, True, True])
        rows[1]["win"] = False
        split = probe.aggregate(rows)[0]
        self.assertEqual((split["wins"], split["runs"]), (2, 3),
                         "flipping a draw did not move the count")
        self.assertEqual(probe.verdict(split), "SPLIT")
        self.assertFalse(split["pass"])
        self.assertTrue(split["split"])

    def test_a_split_is_reported_as_split_and_a_loss_as_fail(self):
        """`0 < k < N` is information; only `k == 0` is the claim being false."""
        self.assertEqual(probe.verdict(self.one([True, False, False])), "SPLIT")
        self.assertEqual(probe.verdict(self.one([False, False, False])), "FAIL")
        self.assertFalse(self.one([False, False, False])["split"])

    def test_an_errored_draw_is_a_lost_draw_not_a_dropped_one(self):
        """Dropping it would shrink the denominator and let 2/2 pass as clean."""
        rows = self.draws([True, True, True])
        rows[1].update(win=probe.won("demo", "must-fire", [], "timed out"),
                       error="timed out", fired=[])
        agg = probe.aggregate(rows)[0]
        self.assertEqual((agg["wins"], agg["runs"]), (2, 3))
        self.assertEqual(agg["errors"], ["timed out"])

    def test_draws_are_grouped_by_skill_kind_and_prompt(self):
        """Two prompts must not collapse into one six-draw row."""
        rows = self.draws([True] * 3, prompt="P") + self.draws([True, False, True],
                                                               prompt="Q")
        agg = probe.aggregate(rows)
        self.assertEqual([(r["prompt"], r["wins"], r["runs"]) for r in agg],
                         [("P", 3, 3), ("Q", 2, 3)])

    # -- the pin the report prints follows the count -------------------------------

    def test_verified_requires_every_draw_and_counts_draws_not_prompts(self):
        rows = (self.draws([True] * 3, prompt="a") + self.draws([True] * 3, prompt="b")
                + self.draws([True] * 3, prompt="c")
                + self.draws([True] * 3, kind="must-not-fire", prompt="x")
                + self.draws([True] * 3, kind="must-not-fire", prompt="y")
                + self.draws([True] * 3, kind="must-not-fire", prompt="z"))
        result = probe.pin_result(probe.aggregate(rows), 3)
        self.assertTrue(result.startswith("verified"), result)
        self.assertIn("9/9 must-fire draws", result)
        self.assertIn("9/9 must-not-fire draws", result)
        # The shape tests/test_routing_gate.py parses out of the shipped pin.
        m = re.search(r"(\d+)/(\d+) must-fire draws", result)
        self.assertEqual(int(m.group(2)), 3 * 3)

    def test_one_flipped_draw_downgrades_verified_to_partial_and_names_the_prompt(self):
        rows = (self.draws([True] * 3, prompt="a") + self.draws([True] * 3, prompt="b")
                + self.draws([True] * 3, prompt="c")
                + self.draws([True] * 3, kind="must-not-fire", prompt="x")
                + self.draws([True] * 3, kind="must-not-fire", prompt="y")
                + self.draws([True] * 3, kind="must-not-fire", prompt="z"))
        clean = probe.pin_result(probe.aggregate(rows), 3)
        # Draws are laid out three per prompt in order a,b,c,x,y,z: index 4 is the
        # second draw of must-fire prompt "b". Asserted below by the counts it moves,
        # so an off-by-three here cannot pass quietly.
        rows[4]["win"] = False
        partial = probe.pin_result(probe.aggregate(rows), 3)
        self.assertNotEqual(clean, partial, "the pin did not move with the count")
        self.assertTrue(partial.startswith("partial"), partial)
        self.assertIn("8/9 must-fire draws", partial)
        self.assertIn("'b' 2/3", partial,
                      "the partial pin does not name WHICH prompt split: %r" % partial)

    def test_the_result_line_survives_the_pin_parser(self):
        """`result:` is one line of a `key: value` block, and a partial result quotes a
        prompt that may itself contain a colon. `parse_pin` splits on the FIRST colon,
        so this has to be checked rather than assumed."""
        rows = self.draws([True, False, True], prompt="fix it: now")
        line = probe.pin_result(probe.aggregate(rows), 3)
        self.assertNotIn("\n", line)
        pin = rc.parse_pin("%s\nresult: %s\n%s" % (rc.PIN_OPEN, line, rc.PIN_CLOSE))
        self.assertEqual(pin["result"], line)
        self.assertEqual(pin["result"].split(":", 1)[0].split()[0], "partial")


class LiveProbeTest(unittest.TestCase):
    """The only test in the repository that verifies a routing claim rather than its
    provenance. Gated: it needs auth and real quota."""

    @unittest.skipUnless(os.environ.get("SKILL_ROUTING_PROBE") == "1",
                         "set SKILL_ROUTING_PROBE=1 to spend ~54 real `claude -p` calls "
                         "per run (~162 at the default --runs 3)")
    def test_every_routing_claim_holds_against_a_real_session(self):
        results = probe.probe(rc.all_skills())
        ok = probe.report(results, probe.cli_version())
        failed = ["%s %s %s %d/%d: %r fired %s"
                  % (r["skill"], probe.verdict(r), r["kind"], r["wins"], r["runs"],
                     r["prompt"], r["fired"])
                  for r in results if not r["pass"]]
        self.assertTrue(ok, "routing claims not verified over %d runs (SPLIT is flaky, "
                            "FAIL is false):\n  " % probe.RUNS + "\n  ".join(failed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
