#!/usr/bin/env python3
"""`dead-guard-detection`, promoted into the seed pool on 2026-09-01.

It arrived from `~/.claude/skills`, where it had lived as the only copy of a completed
five-round forge. Per this repository's own rule -- a skill is unguarded until its own
test exists -- it gets one before it counts as shipped.

The valuable test here is the last one, and it is not a style check. The skill's headline
worked example claims that a cap guard can be DEAD: that `wc -l < file` pads its count
with leading spaces on BSD, that `[[ "$n" =~ ^[0-9]+$ ]]` therefore fails, and that the
whole comparison is skipped while the program behaves plausibly. This repository has that
exact defect in its own history -- `CLAIM_GATE_MAX_BYTES` was dead code on every macOS for
the same reason -- so the claim is load-bearing rather than illustrative.

So it is RUN, not read. Reading the example proves nothing: a dead guard is usually
correct in isolation, which is the skill's whole point.
"""

import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "dead-guard-detection" / "SKILL.md"


def text():
    return SKILL.read_text(encoding="utf-8")


def body():
    return text().split("---", 2)[2]


def description():
    m = re.search(r'^description:\s*"(.*)"\s*$', text(), re.M)
    return m.group(1) if m else None


class TheWorkedExampleIsTrue(unittest.TestCase):
    """Every command the skill documents, executed. The skill says its outputs are real;
    this is what makes that a claim rather than a decoration."""

    GUARD = textwrap.dedent("""\
        #!/bin/bash
        # refuse files longer than CAP lines
        CAP="${CAP:-100}"
        n=$(wc -l < "$1")
        if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -gt "$CAP" ]; then
          echo "REFUSED: $1 has $n lines (cap $CAP)" >&2
          exit 1
        fi
        echo "processing $1"
        """)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "big.txt").write_text("".join("%d\n" % i for i in range(1, 501)))
        (self.d / "small.txt").write_text("a\nb\nc\n")
        self.guard = self.d / "capcheck.sh"
        self.guard.write_text(self.GUARD)
        self.guard.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

    def run_guard(self, target, cap=None):
        env = {"PATH": self.PATH}
        if cap is not None:
            env["CAP"] = str(cap)
        return subprocess.run([str(self.guard), target], cwd=self.d, env=env,
                              capture_output=True, text=True, timeout=60)

    def wc_raw(self):
        """The exact bytes `wc -l <` prints for the 500-line file, here, measured.

        UNDER THE GUARD'S OWN PATH, not the ambient one. The skill this tests says to
        probe "the exact binary the program resolves, not the one you assume"; a `wc`
        earlier on the developer's PATH than the guard's `/usr/bin` would answer a
        question about a different program.
        """
        with open(self.d / "big.txt", "rb") as fh:      # `wc -l <file`, without a shell
            r = subprocess.run(["wc", "-l"], stdin=fh, capture_output=True, text=True,
                               env={"PATH": self.PATH}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def wc_pads(self):
        """Whether this `wc` LEFT-pads. `lstrip()`, never `strip()`: see below."""
        raw = self.wc_raw()
        return raw != raw.lstrip()

    def require_padding(self):
        """The two cases below demonstrate a DEAD guard, and a guard is only dead where
        the premise holds. Where it does not, the example is not wrong -- it is out of
        scope, and `SKILL.md` says so itself: "Every line below runs as printed, in an
        empty directory, on macOS/BSD with bash on PATH"."""
        if not self.wc_pads():
            self.skipTest("`wc -l <` prints %r here: no leading pad, so this is not the "
                          "BSD wc the skill's worked example is scoped to and the guard "
                          "in it is alive rather than dead (see the biconditional in "
                          "test_the_count_really_is_padded, which runs on both)"
                          % self.wc_raw())

    def test_the_count_really_is_padded(self):
        """The boundary fact the whole example rests on -- and the CONSEQUENCE it
        claims, pinned in both directions, so neither platform gets a free pass.

        THIS TEST WAS VACUOUS, AND ITS SILENCE IS WHY THE TWO CASES BELOW WENT RED ON
        UBUNTU WITH NO WARNING. It compared `stdout` against `stdout.strip()`, which
        also removes the trailing newline, so the two differ on every platform ever
        built: GNU coreutils, which pads nothing, passed it. `lstrip()` asks the
        question that was meant.

        The claim is not "wc pads" -- that is platform trivia. It is "the padding is
        what kills the guard", so both halves are asserted together: where the count is
        padded the 500-line file must slip past a cap of 100, and where it is not, the
        same file and the same guard must be REFUSED. A future `wc` that stops padding
        does not quietly turn the example into fiction; it moves this test to its other
        branch and skips the two cases that no longer apply.
        """
        raw = self.wc_raw()
        refused = self.run_guard("big.txt").returncode == 1
        self.assertEqual(
            self.wc_pads(), not refused,
            "the boundary bytes and the guard's behaviour disagree: `wc -l <` printed "
            "%r and 500 lines against a cap of 100 %s -- one of the two readings is "
            "wrong, and the worked example rests on their agreement"
            % (raw, "was REFUSED" if refused else "was processed"))

    def test_the_guard_ships_dead(self):
        """500 lines against a cap of 100, and it processes the file. No symptom points
        at the guard: the program looks like it is working."""
        self.require_padding()
        r = self.run_guard("big.txt")
        self.assertEqual(r.returncode, 0)
        self.assertIn("processing big.txt", r.stdout)
        self.assertNotIn("REFUSED", r.stderr)

    def test_the_mutation_probe_exposes_it(self):
        """Step 1 of the skill. A cap of 0 must refuse everything; if forcing the guard
        to a state that MUST change behaviour changes nothing, it never runs."""
        self.require_padding()
        r = self.run_guard("small.txt", cap=0)
        self.assertIn("processing small.txt", r.stdout,
                      "the mutation probe changed behaviour, so this guard was not dead "
                      "and the example no longer demonstrates what it claims")

    def test_the_documented_fix_brings_both_branches_to_life(self):
        """Step 5: fix at the boundary, then RE-PROBE. Both branches, not just the one
        that was broken -- a fix that only ever refuses is its own dead guard."""
        src = self.guard.read_text().replace(
            'n=$(wc -l < "$1")', 'n=$(wc -l < "$1"); n=$((n))')
        self.guard.write_text(src)

        refused_small = self.run_guard("small.txt", cap=0)
        self.assertEqual(refused_small.returncode, 1)
        self.assertIn("REFUSED: small.txt has 3 lines (cap 0)", refused_small.stderr)

        refused_big = self.run_guard("big.txt")
        self.assertEqual(refused_big.returncode, 1)
        self.assertIn("REFUSED: big.txt has 500 lines (cap 100)", refused_big.stderr)

        passed = self.run_guard("small.txt")
        self.assertEqual(passed.returncode, 0, "the repaired guard refuses everything")
        self.assertIn("processing small.txt", passed.stdout)


class TheProcedureIsIntact(unittest.TestCase):
    def test_every_step_of_the_procedure_is_present_and_ordered(self):
        """The steps are the skill. A reflow that drops one leaves a procedure that reads
        fine and cannot be followed -- which is how a rule went missing from a sibling
        skill on the same day this one was promoted."""
        wanted = ["Step 0", "Step 1", "Step 2", "Step 3", "Step 4", "Step 5"]
        at = [body().find("### %s" % s) for s in wanted]
        for name, pos in zip(wanted, at):
            self.assertNotEqual(pos, -1, "%s is missing from the procedure" % name)
        self.assertEqual(at, sorted(at), "the steps are out of order: %s" % at)

    def test_it_says_what_a_dead_guard_is(self):
        self.assertIn("observed", body().lower(),
                      "the skill no longer rests on an OBSERVED firing, which is its "
                      "entire distinction from reading the code")


class TheCaps(unittest.TestCase):
    def test_the_description_is_within_budget_and_shaped(self):
        d = description()
        self.assertIsNotNone(d, "description does not parse as a double-quoted scalar")
        self.assertLessEqual(len(d), 500, "description is %d chars" % len(d))
        self.assertTrue(d.startswith("Use when"), d[:40])
        self.assertIn("Do NOT use", d, "no decline clause")

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
