#!/usr/bin/env python3
"""`skillforge list` has to say when a forge stopped moving.

The defect these pin: staleness was COMPUTED and then thrown away. The status line has
rendered `idle 3d13h` since it was written, and no other surface consumed that signal,
so a forge whose orchestrator was killed (a laptop closing its lid is enough) sat
`active` for three and a half days, held its own name against every new forge, and the
one command a person runs to ask "what is running?" printed a phase and no age.

Nothing here closes or deletes anything. An idle forge may still be live work and the
decision to end one belongs to a person; these tests pin only that the age is REPORTED,
that the mark is reserved for forges that can actually be stale, and that the advice
printed alongside it is not the advice that would record a dead forge as completed.

Real CLI, real state directory, real files. The clock is pinned with SKILLFORGE_NOW,
which is the knob `bin/skillforge` reads for exactly this purpose.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"

T0 = 1000000000          # when every forge below starts
MINUTE, HOUR, DAY = 60, 3600, 86400
DEFAULT_IDLE = 2700      # bin/skillforge and the renderer share this default


class StalenessCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, now=None, idle_secs=None):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state),
               "SKILL_COMPOUNDER_STATE": str(self.state)}
        if now is not None:
            env["SKILLFORGE_NOW"] = str(now)
        if idle_secs is not None:
            env["SKILLFORGE_IDLE_SECS"] = str(idle_secs)
        return subprocess.run([str(CLI), *args], capture_output=True, text=True, env=env)

    def start(self, name="demo-skill", steps=22, now=T0):
        r = self.run_cli("start", name, str(steps), "a demo forge",
                         "--trigger", "a test started this",
                         "--trigger-kind", "agent-decision", now=now)
        self.assertEqual(r.returncode, 0, "start failed: %s" % r.stderr)
        return r

    def listing(self, now, idle_secs=None):
        r = self.run_cli("list", now=now, idle_secs=idle_secs)
        self.assertEqual(r.returncode, 0, "list failed: %s" % r.stderr)
        return r.stdout


class ListReportsAge(StalenessCase):
    def test_the_listing_has_an_idle_column(self):
        """Without it the reader cannot tell a forge that stepped a minute ago from one
        whose session died days back, which is the whole failure."""
        self.start()
        out = self.listing(T0 + 10 * MINUTE)
        self.assertIn("IDLE", out, "no IDLE column in the header: %r" % out)
        self.assertIn("10m", out, "the age of a 10-minute-old forge is not reported: %r" % out)

    def test_a_fresh_forge_carries_no_stale_mark_and_no_footer(self):
        """Non-vacuity for every assertion below: the mark has to be absent when the
        forge is fine, or a listing that always warns teaches the reader to ignore it."""
        self.start()
        out = self.listing(T0 + 10 * MINUTE)
        self.assertNotIn("!", out, "a 10-minute-old forge was flagged stale: %r" % out)
        self.assertNotIn("have not stepped", out, "footer fired on a fresh forge: %r" % out)

    def test_a_forge_idle_past_the_threshold_is_marked_and_explained(self):
        self.start()
        out = self.listing(T0 + 3 * DAY + 14 * HOUR)
        self.assertIn("3d14h!", out, "a 3d14h-idle forge is not marked: %r" % out)
        self.assertIn("have not stepped", out, "no footer explaining the mark: %r" % out)

    def test_the_boundary_is_the_threshold_itself(self):
        """One second under is fresh, exactly at it is stale. A guard nobody has watched
        flip is a guard nobody has watched at all."""
        self.start()
        self.assertNotIn("!", self.listing(T0 + DEFAULT_IDLE - 1))
        self.assertIn("!", self.listing(T0 + DEFAULT_IDLE))

    def test_the_threshold_knob_is_honoured(self):
        """It has to be the renderer's own knob, or the two surfaces drift and one calls
        a forge idle while the other calls it healthy."""
        self.start()
        at = T0 + 10 * MINUTE
        self.assertNotIn("!", self.listing(at), "stale at the default 45m after 10m")
        self.assertIn("!", self.listing(at, idle_secs=60),
                      "SKILLFORGE_IDLE_SECS=60 did not make a 10-minute forge stale")

    def test_a_junk_threshold_falls_back_instead_of_erroring(self):
        """`[ x -ge y ]` prints 'integer expected' and the listing loses its meaning; the
        same class of defect the renderer already carries a guard for."""
        self.start()
        r = self.run_cli("list", now=T0 + 10 * MINUTE, idle_secs="not-a-number")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("integer expected", r.stderr)
        self.assertNotIn("!", r.stdout)


class OnlyActiveCanBeStale(StalenessCase):
    def test_a_closed_forge_is_never_marked_however_old(self):
        """A `failed` record is old on purpose and is reaped on its own TTL. Flagging it
        would put a `!` beside every terminal row and train the reader to ignore it."""
        self.start()
        r = self.run_cli("fail", "--name", "demo-skill", "its orchestrator died", now=T0 + HOUR)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.listing(T0 + 30 * DAY)
        if "demo-skill" in out:
            self.assertNotIn("!", out, "a closed forge was marked stale: %r" % out)
            self.assertNotIn("have not stepped", out)


class TheRefusalNamesTheStaleness(StalenessCase):
    def test_starting_a_wedged_name_reports_how_long_it_has_been_dead(self):
        """This refusal is where a wedged name is actually met. Without the age it reads
        like ordinary contention with a colleague rather than a forge that died."""
        self.start()
        r = self.run_cli("start", "demo-skill", "22", "second attempt",
                         "--trigger", "t", "--trigger-kind", "agent-decision",
                         now=T0 + 3 * DAY + 14 * HOUR)
        self.assertNotEqual(r.returncode, 0, "a live name was not refused")
        self.assertIn("3d14h", r.stderr, "the refusal does not say how stale it is: %r" % r.stderr)

    def test_the_refusal_does_not_advise_done(self):
        """`done` records a forge that never finished as COMPLETED and installs it. The
        message advised exactly that, in both refusal paths, for as long as it existed."""
        self.start()
        r = self.run_cli("start", "demo-skill", "22", "second attempt",
                         "--trigger", "t", "--trigger-kind", "agent-decision",
                         now=T0 + 3 * DAY)
        self.assertIn("skillforge fail --name", r.stderr, r.stderr)
        self.assertIn("skillforge clear --name", r.stderr, r.stderr)
        self.assertNotIn("Close it with 'skillforge done", r.stderr,
                         "still advising the close that records it as completed")

    def test_the_footer_does_not_advise_done_either(self):
        self.start()
        out = self.listing(T0 + 3 * DAY)
        self.assertIn("skillforge fail --name", out, out)
        self.assertIn("skillforge clear --name", out, out)


class AnUnreadableStampIsNotAFreshOne(StalenessCase):
    def test_a_record_with_no_usable_updated_reports_unknown(self):
        """Never guess. Reporting a missing stamp as age zero would render the exact
        forge nobody can account for as the healthiest row in the table."""
        self.start()
        slots = sorted((self.state / "forge").glob("*.json"))
        self.assertTrue(slots, "no slot file was written")
        import json
        rec = json.loads(slots[0].read_text())
        rec.pop("updated", None)
        slots[0].write_text(json.dumps(rec))
        out = self.listing(T0 + 3 * DAY)
        self.assertIn("?", out, "a record with no `updated` did not report unknown: %r" % out)
        self.assertNotIn("!", out, "an unknown age was asserted to be stale: %r" % out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
