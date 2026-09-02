#!/usr/bin/env python3
"""`skillforge list` has to say when a forge stopped moving.

The defect these pin: staleness was COMPUTED and then thrown away. The status line has
rendered `idle 3d13h` since it was written, and no other surface consumed that signal,
so a forge whose orchestrator was killed (a laptop closing its lid is enough) sat
`active` for three and a half days, held its own name against every new forge, and the
one command a person runs to ask "what is running?" printed a phase and no age.

`list` closes and deletes nothing. An idle forge may still be live work and the decision
to end one belongs to a person; the first half of this file pins only that the age is
REPORTED, that the mark is reserved for forges that can actually be stale, and that the
advice printed alongside it is not the advice that would record a dead forge as completed.

THE SECOND HALF IS THE REAPER, and it is a different threshold doing a different job.
`SKILLFORGE_IDLE_SECS` (45 minutes) marks a row and a person looks. `SKILLFORGE_ACTIVE_TTL`
(six hours) is the point past which a forge is presumed DEAD and a `fail` row is written
for it without anybody being asked, which is a much stronger claim and needs a much longer
wait -- one knob for both would make the reaper as eager as the marker. Six hours is
measured against IDLE time and not elapsed time, and that distinction is the whole safety
of it: the median real forge runs 3.3 hours and the longest healthy one ran 6.5, so a
six-hour ELAPSED cap would close a forge that was still working, while a six-hour gap
BETWEEN STEPS is longer than any healthy forge has ever lived.

Real CLI, real state directory, real files. The clock is pinned with SKILLFORGE_NOW,
which is the knob `bin/skillforge` reads for exactly this purpose.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"

T0 = 1000000000          # when every forge below starts
MINUTE, HOUR, DAY = 60, 3600, 86400
DEFAULT_IDLE = 2700      # bin/skillforge and the renderer share this default
ACTIVE_TTL = 21600       # SKILLFORGE_ACTIVE_TTL: six hours of IDLE, presumed dead
REAP_REASON = "reaped: exceeded SKILLFORGE_ACTIVE_TTL"


class StalenessCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, now=None, idle_secs=None, active_ttl=None, **extra):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state),
               "SKILL_COMPOUNDER_STATE": str(self.state)}
        if now is not None:
            env["SKILLFORGE_NOW"] = str(now)
        if idle_secs is not None:
            env["SKILLFORGE_IDLE_SECS"] = str(idle_secs)
        if active_ttl is not None:
            env["SKILLFORGE_ACTIVE_TTL"] = str(active_ttl)
        env.update({k: str(v) for k, v in extra.items()})
        return subprocess.run([str(CLI), *args], capture_output=True, text=True, env=env)

    def ledger_rows(self):
        led = self.state / "ledger.jsonl"
        if not led.exists():
            return []
        rows = []
        for line in led.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
        return rows

    def outcomes(self, name):
        return [r for r in self.ledger_rows()
                if r.get("event") in ("done", "fail") and r.get("name") == name]

    def status_of(self, name):
        for slot in sorted((self.state / "forge").glob("*.json")):
            rec = json.loads(slot.read_text())
            if rec.get("name") == name:
                return rec.get("status")
        return None

    def start(self, name="demo-skill", steps=22, now=T0):
        r = self.run_cli("start", name, str(steps), "a demo forge",
                         "--trigger", "a test started this",
                         "--trigger-kind", "agent-decision", now=now)
        self.assertEqual(r.returncode, 0, "start failed: %s" % r.stderr)
        return r

    def listing(self, now, idle_secs=None):
        """The TABLE only. The advisory footer goes to stderr on purpose, so that stdout
        stays a surface a parser can read; three tests that read `list` as a table broke
        when it was briefly on stdout, and they were right to."""
        r = self.run_cli("list", now=now, idle_secs=idle_secs)
        self.assertEqual(r.returncode, 0, "list failed: %s" % r.stderr)
        return r.stdout

    def advisory(self, now, idle_secs=None):
        r = self.run_cli("list", now=now, idle_secs=idle_secs)
        self.assertEqual(r.returncode, 0, "list failed: %s" % r.stderr)
        return r.stderr


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
        self.assertNotIn("have not stepped", self.advisory(T0 + 10 * MINUTE),
                         "the advisory fired on a fresh forge")

    def test_a_forge_idle_past_the_threshold_is_marked_and_explained(self):
        self.start()
        at = T0 + 3 * DAY + 14 * HOUR
        out = self.listing(at)
        self.assertIn("3d14h!", out, "a 3d14h-idle forge is not marked: %r" % out)
        self.assertIn("have not stepped", self.advisory(at),
                      "nothing on stderr explains the mark")
        self.assertNotIn("have not stepped", out,
                         "the advisory is on stdout, which is the table a parser reads")

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
        at = T0 + 30 * DAY
        out = self.listing(at)
        if "demo-skill" in out:
            self.assertNotIn("!", out, "a closed forge was marked stale: %r" % out)
            self.assertNotIn("have not stepped", self.advisory(at))


class TheRefusalNamesTheStaleness(StalenessCase):
    """THE REFUSAL NOW HAS A CEILING, and these two tests moved under it deliberately.

    They used to start a second forge at 3d14h and at 3d, and both of those are past
    SKILLFORGE_ACTIVE_TTL, where `start` reaps the corpse and takes the name instead of
    refusing (see StartReapsTheCorpseHoldingItsName). So the ages here are five hours: past
    the 45-minute mark that puts a `!` in `list`, and inside the six hours after which a
    forge is presumed dead. That window is exactly where the refusal still has a job -- a
    forge that has stopped moving but might not be dead -- and it is the window the wording
    below has to be right for.
    """

    def test_starting_a_wedged_name_reports_how_long_it_has_been_dead(self):
        """This refusal is where a wedged name is actually met. Without the age it reads
        like ordinary contention with a colleague rather than a forge that died."""
        self.start()
        r = self.run_cli("start", "demo-skill", "22", "second attempt",
                         "--trigger", "t", "--trigger-kind", "agent-decision",
                         now=T0 + 5 * HOUR)
        self.assertNotEqual(r.returncode, 0, "a live name was not refused")
        self.assertIn("5h00m", r.stderr, "the refusal does not say how stale it is: %r" % r.stderr)

    def test_the_refusal_does_not_advise_done(self):
        """`done` records a forge that never finished as COMPLETED and installs it. The
        message advised exactly that, in both refusal paths, for as long as it existed."""
        self.start()
        r = self.run_cli("start", "demo-skill", "22", "second attempt",
                         "--trigger", "t", "--trigger-kind", "agent-decision",
                         now=T0 + 5 * HOUR)
        self.assertIn("skillforge fail --name", r.stderr, r.stderr)
        self.assertIn("skillforge clear --name", r.stderr, r.stderr)
        self.assertNotIn("Close it with 'skillforge done", r.stderr,
                         "still advising the close that records it as completed")

    def test_the_footer_does_not_advise_done_either(self):
        self.start()
        err = self.advisory(T0 + 3 * DAY)
        self.assertIn("skillforge fail --name", err, err)
        self.assertIn("skillforge clear --name", err, err)
        self.assertNotIn("skillforge done", err,
                         "the advisory names the close that records it as completed")


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




# ---------------------------------------------------------------------------- the reaper
#
# WHAT THIS IS FOR, in one incident. On 2026-08-28 a forge for finish-task was killed with
# its session -- a laptop closing its lid is enough -- and sat `status:"active"` for three
# and a half days. Nothing expires `active`, so it held its own name against every attempt
# to re-forge it, and the only surfaces that could see it (`list` and the status line) both
# said what they always say about a running forge. The name was the wedge: `start` refuses
# a live name, correctly, and there was no way to tell a live forge from a dead one.


class ReapWritesTheOutcomeTheForgeNeverGot(StalenessCase):
    def test_a_forge_past_the_ttl_gets_a_fail_row_naming_the_knob_that_wrote_it(self):
        """The row is the point, not the freed name. A `start` with no outcome is invisible
        to the ledger's join for as long as the ledger exists; one appended row closes the
        join AND frees the name. And it says a CLOCK judged it, not a person -- a row
        reading 'abandoned' claims a judgement nobody made."""
        self.start()
        r = self.run_cli("reap", now=T0 + 7 * HOUR)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.outcomes("demo-skill")
        self.assertEqual(len(rows), 1, "no fail row was appended: %r" % self.ledger_rows())
        self.assertEqual(rows[0]["event"], "fail")
        self.assertEqual(rows[0].get("phase"), REAP_REASON,
                         "the reason does not name the knob: %r" % rows[0])

    def test_the_ledger_is_appended_to_and_never_rewritten(self):
        """Append-only is the property every reader of this file depends on, and a reaper
        that 'corrected' the start row would break all of them at once."""
        self.start()
        before = (self.state / "ledger.jsonl").read_text()
        self.run_cli("reap", now=T0 + 7 * HOUR)
        after = (self.state / "ledger.jsonl").read_text()
        self.assertTrue(after.startswith(before),
                        "the existing rows were rewritten, not appended to")

    def test_the_name_is_free_afterwards(self):
        """The wedge is the whole reason this exists: until the name is free the one thing
        a person wants to do -- re-forge that skill -- is the one thing they cannot do."""
        self.start()
        self.run_cli("reap", now=T0 + 7 * HOUR)
        r = self.run_cli("start", "demo-skill", "22", "second attempt",
                         "--trigger", "t", "--trigger-kind", "agent-decision",
                         now=T0 + 7 * HOUR + 60)
        self.assertEqual(r.returncode, 0, "the name was still wedged: %s" % r.stderr)

    def test_a_forge_inside_the_ttl_is_never_touched(self):
        """Non-vacuity, and the only property that makes the rest of this safe. A reaper
        that could close a forge that stepped a minute ago writes a `fail` row over live
        work, and the forge has no way to say it was working."""
        self.start()
        r = self.run_cli("reap", now=T0 + 5 * HOUR)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.outcomes("demo-skill"), [],
                         "a forge inside the TTL was reaped")
        self.assertIn("nothing reaped", r.stdout, r.stdout)
        self.assertEqual(self.status_of("demo-skill"), "active")

    def test_the_boundary_is_the_ttl_itself(self):
        self.start()
        self.assertEqual(self.outcomes("demo-skill"), [])
        self.run_cli("reap", now=T0 + ACTIVE_TTL - 1)
        self.assertEqual(self.outcomes("demo-skill"), [], "reaped one second early")
        self.run_cli("reap", now=T0 + ACTIVE_TTL)
        self.assertEqual(len(self.outcomes("demo-skill")), 1, "not reaped at the TTL")

    def test_the_ttl_knob_is_honoured(self):
        self.start()
        self.run_cli("reap", now=T0 + 2 * MINUTE)
        self.assertEqual(self.outcomes("demo-skill"), [])
        self.run_cli("reap", now=T0 + 2 * MINUTE, active_ttl=60)
        self.assertEqual(len(self.outcomes("demo-skill")), 1,
                         "SKILLFORGE_ACTIVE_TTL=60 did not reap a two-minute-idle forge")

    def test_a_junk_ttl_falls_back_instead_of_reaping_everything(self):
        """`[ x -ge y ]` with a non-number prints 'integer expected' and takes the meaning
        of every reap decision with it. Falling back to six hours is the safe reading;
        treating the comparison as true would close every live forge on the machine."""
        self.start()
        r = self.run_cli("reap", now=T0 + HOUR, active_ttl="not-a-number")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("integer expected", r.stderr)
        self.assertEqual(self.outcomes("demo-skill"), [],
                         "a junk TTL reaped a one-hour-old forge")

    def test_name_narrows_the_set_and_does_not_lower_the_bar(self):
        self.start(name="stale-one")
        self.start(name="also-stale")
        r = self.run_cli("reap", "--name", "stale-one", now=T0 + 7 * HOUR)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.outcomes("stale-one")), 1, r.stdout)
        self.assertEqual(self.outcomes("also-stale"), [],
                         "--name did not narrow the set")

    def test_a_named_forge_inside_the_ttl_is_still_refused(self):
        self.start()
        r = self.run_cli("reap", "--name", "demo-skill", now=T0 + HOUR)
        self.assertEqual(self.outcomes("demo-skill"), [],
                         "--name talked the reaper past its own threshold")
        self.assertIn("demo-skill", r.stdout, r.stdout)

    def test_a_record_whose_age_cannot_be_read_is_never_reaped(self):
        """Never guess. The alternative is reading an unreadable stamp as 'old' and
        closing somebody's live forge on that reading."""
        self.start()
        slot = sorted((self.state / "forge").glob("*.json"))[0]
        rec = json.loads(slot.read_text())
        rec.pop("updated", None)
        slot.write_text(json.dumps(rec))
        r = self.run_cli("reap", now=T0 + 30 * DAY)
        self.assertEqual(self.outcomes("demo-skill"), [],
                         "a record with no readable 'updated' was reaped anyway")
        self.assertIn("age unknown", r.stderr,
                      "it was skipped silently, which wedges the name with no surface "
                      "saying why: %r" % r.stderr)


class StartReapsTheCorpseHoldingItsName(StalenessCase):
    def test_start_past_the_ttl_reaps_and_proceeds(self):
        """The refusal is where a wedged name is actually MET, and the caller is usually a
        subagent that reads 'already live' as 'somebody else is on it' and stops. Past the
        TTL, refusing sends it away from the one thing it should do."""
        self.start()
        r = self.run_cli("start", "demo-skill", "22", "second attempt",
                         "--trigger", "t", "--trigger-kind", "agent-decision",
                         now=T0 + 7 * HOUR)
        self.assertEqual(r.returncode, 0, "still refusing a dead name: %s" % r.stderr)
        self.assertEqual(len(self.outcomes("demo-skill")), 1,
                         "no fail row for the forge it displaced")
        self.assertEqual(self.outcomes("demo-skill")[0].get("phase"), REAP_REASON)

    def test_it_says_so_on_stderr_and_not_on_stdout(self):
        """A reap is something that happened TO the caller, not an answer to what it
        asked, and stdout is the line a caller may be reading."""
        self.start()
        r = self.run_cli("start", "demo-skill", "22", "second attempt",
                         "--trigger", "t", "--trigger-kind", "agent-decision",
                         now=T0 + 7 * HOUR)
        self.assertIn("reaped", r.stderr, r.stderr)
        self.assertIn("SKILLFORGE_ACTIVE_TTL", r.stderr,
                      "the message does not name the knob that decided it")
        self.assertNotIn("reaped", r.stdout,
                         "the reap notice is on stdout, which a caller parses")

    def test_a_live_forge_inside_the_ttl_is_still_refused(self):
        """Non-vacuity for the whole class. If this stopped refusing, two forges would run
        under one name and both the animation and the ledger join would stop meaning
        anything -- which is the defect the multi-slot scheme exists to prevent."""
        self.start()
        r = self.run_cli("start", "demo-skill", "22", "second attempt",
                         "--trigger", "t", "--trigger-kind", "agent-decision",
                         now=T0 + 5 * HOUR)
        self.assertNotEqual(r.returncode, 0, "a live name was taken")
        self.assertEqual(self.outcomes("demo-skill"), [], "a live forge was reaped")

    def test_a_record_with_no_readable_age_is_refused_rather_than_reaped(self):
        self.start()
        slot = sorted((self.state / "forge").glob("*.json"))[0]
        rec = json.loads(slot.read_text())
        rec.pop("updated", None)
        slot.write_text(json.dumps(rec))
        r = self.run_cli("start", "demo-skill", "22", "second attempt",
                         "--trigger", "t", "--trigger-kind", "agent-decision",
                         now=T0 + 30 * DAY)
        self.assertNotEqual(r.returncode, 0,
                            "an unreadable stamp was read as 'old' and reaped")
        self.assertEqual(self.outcomes("demo-skill"), [])

    def test_the_new_forge_is_the_one_that_is_live_afterwards(self):
        self.start()
        self.run_cli("start", "demo-skill", "22", "second attempt",
                     "--trigger", "t", "--trigger-kind", "agent-decision",
                     now=T0 + 7 * HOUR)
        out = self.listing(T0 + 7 * HOUR)
        self.assertIn("active", out, out)
        self.assertNotIn("!", out, "the replacement forge is marked stale: %r" % out)
        starts = [r for r in self.ledger_rows()
                  if r.get("event") == "start" and r.get("name") == "demo-skill"]
        self.assertEqual(len(starts), 2, "the second start was not recorded")


class ADoctorAgreesWithTheReaper(StalenessCase):
    def test_doctor_warns_at_the_same_threshold_reap_acts_on(self):
        """Two thresholds would have `doctor` call a forge healthy while `reap` closes it,
        which is worse than either surface alone."""
        self.start()
        fresh = self.run_cli("doctor", now=T0 + ACTIVE_TTL - 1)
        stale = self.run_cli("doctor", now=T0 + ACTIVE_TTL)
        self.assertNotIn("WARN  forges", fresh.stdout, fresh.stdout)
        self.assertIn("WARN  forges", stale.stdout, stale.stdout)

    def test_doctor_stops_warning_once_the_forge_is_reaped(self):
        self.start()
        self.assertIn("WARN  forges", self.run_cli("doctor", now=T0 + 7 * HOUR).stdout)
        self.run_cli("reap", now=T0 + 7 * HOUR)
        after = self.run_cli("doctor", now=T0 + 7 * HOUR)
        self.assertIn("PASS  forges", after.stdout, after.stdout)
        self.assertEqual(after.returncode, 0, after.stdout)


class AReapedForgeStopsAnimating(StalenessCase):
    """The status line renders from the record on disk, once a second, and a `fail` row in
    the ledger would not by itself stop the spinner: the renderer never reads the ledger.
    What stops it is that `reap` writes `status:"failed"` into the record, which the
    renderer draws as a terminal ✗ and then expires on SKILLFORGE_FAIL_TTL. Both halves are
    pinned here, because a reaped forge still spinning is a person being told a dead job is
    running -- exactly the report the reaper exists to end."""

    RENDER = REPO / "statusline" / "skillforge-status.sh"
    PAYLOAD = '{"session_id": "abc"}'

    def render(self, now, fail_ttl=60):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state),
               "SKILL_COMPOUNDER_STATE": str(self.state),
               "SKILLFORGE_NOW": str(now),
               "SKILLFORGE_FAIL_TTL": str(fail_ttl)}
        r = subprocess.run([str(self.RENDER)], input=self.PAYLOAD, capture_output=True,
                           text=True, env=env)
        self.assertEqual(r.stderr, "", "the renderer wrote to stderr")
        import re
        return re.sub(r"\033\[[0-9;]*m", "", r.stdout)

    def test_the_spinner_is_replaced_by_a_terminal_mark(self):
        self.start()
        running = self.render(T0 + 7 * HOUR)
        self.assertIn("demo-skill", running, "the forge was not being rendered at all")
        self.assertNotIn("✗", running, "it was already terminal before the reap")
        self.run_cli("reap", now=T0 + 7 * HOUR)
        reaped = self.render(T0 + 7 * HOUR + 5)
        self.assertIn("✗", reaped, "a reaped forge is still animating: %r" % reaped)
        self.assertIn("abandoned", reaped, reaped)

    def test_it_leaves_the_status_line_entirely_once_the_fail_ttl_passes(self):
        self.start()
        self.run_cli("reap", now=T0 + 7 * HOUR)
        self.assertEqual(self.render(T0 + 7 * HOUR + 90, fail_ttl=60), "",
                         "the reaped forge outlived SKILLFORGE_FAIL_TTL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
