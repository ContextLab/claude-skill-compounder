#!/usr/bin/env python3
"""Runs the real status-line scripts and inspects what they actually print.

The clock is pinned with SKILLFORGE_NOW so the animation is deterministic."""

import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"
RENDER = REPO / "statusline" / "skillforge-status.sh"
WRAPPER = REPO / "statusline" / "statusline.sh"
PAYLOAD = json.dumps({"session_id": "abc", "workspace": {"current_dir": str(REPO)}})
ANSI = re.compile(r"\033\[[0-9;]*m")


ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\ufeff"}


def cell_width(ch):
    """Terminal cells for one codepoint.

    A combining mark or a zero-width joiner advances the cursor by nothing, and a CJK
    or emoji-presentation codepoint by two. Counting a combining mark as one is the
    same mistake the renderer had, so this helper must not repeat it -- a checker that
    shares the bug it is checking for proves nothing.
    """
    if unicodedata.combining(ch) or ch in ZERO_WIDTH or 0xFE00 <= ord(ch) <= 0xFE0F:
        return 0
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def columns(text):
    return sum(cell_width(c) for c in ANSI.sub("", text))


class StatusLineTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra):
        e = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
             "HOME": str(self.state),
             "SKILL_COMPOUNDER_STATE": str(self.state)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def forge(self, *args):
        subprocess.run([str(CLI), *args], capture_output=True, text=True, env=self.env())

    def render(self, script=RENDER, **extra):
        return ANSI.sub("", self.raw(script=script, **extra))

    def raw(self, script=RENDER, **extra):
        r = subprocess.run([str(script)], input=PAYLOAD, capture_output=True,
                           text=True, env=self.env(**extra))
        self.assertEqual(r.stderr, "", "the renderer wrote to stderr")
        return r.stdout

    # ------------------------------------------------------------------ quiet

    def test_nothing_rendered_when_no_forge_is_active(self):
        self.assertEqual(self.render(), "")

    def test_wrapper_is_silent_with_no_forge_and_no_base(self):
        self.assertEqual(self.render(script=WRAPPER), "")

    # ----------------------------------------------------------------- active

    def test_active_forge_shows_name_progress_and_phase(self):
        self.forge("start", "my-skill", "8", "a one line summary")
        self.forge("step", "4", "red-team round 1")
        # The tail cycles, so assert each window at a timestamp inside it:
        # (t/5) % 3 == 2 shows the summary, otherwise the current phase.
        phase_frame = self.render(SKILLFORGE_NOW=1005)     # 201 % 3 == 0 -> phase
        summary_frame = self.render(SKILLFORGE_NOW=1000)   # 200 % 3 == 2 -> summary
        for out in (phase_frame, summary_frame):
            self.assertIn("my-skill", out)
            self.assertIn("4/8", out)
            self.assertIn("50%", out)
        self.assertIn("red-team round 1", phase_frame)
        self.assertIn("a one line summary", summary_frame)

    def test_bar_is_a_constant_width_and_fills_with_progress(self):
        """The last cell is reserved: an ACTIVE forge at step 4 of 4 draws 11 of 12,
        not 12 of 12. A full bar is the strongest completion signal the segment has and
        it belongs to `done` alone. Everything below the budget is untouched."""
        self.forge("start", "s", "4", "summary")
        widths, fills = set(), []
        for step in (0, 1, 2, 3, 4):
            self.forge("step", str(step), "phase")
            out = self.render(SKILLFORGE_NOW=1001)   # odd -> no pulse glyph
            bar = out.split("▕")[1].split("▏")[0]
            widths.add(len(bar))
            fills.append(bar.count("█"))
        self.assertEqual(widths, {12}, "bar width must not change as it fills")
        self.assertEqual(fills, [0, 3, 6, 9, 11])

    def test_spinner_advances_with_the_clock(self):
        self.forge("start", "s", "4", "summary")
        frames = [self.render(SKILLFORGE_NOW=1000 + i).strip()[0] for i in range(16)]
        self.assertEqual(len(set(frames)), 8, "all 8 spinner frames must be distinct")
        self.assertEqual(frames[:8], frames[8:], "the spinner must cycle with period 8")

    def test_tail_alternates_between_phase_and_summary(self):
        self.forge("start", "s", "4", "THE-SUMMARY")
        self.forge("step", "1", "THE-PHASE")
        seen = {("summary" if "THE-SUMMARY" in self.render(SKILLFORGE_NOW=t) else "phase")
                for t in range(1000, 1030)}
        self.assertEqual(seen, {"summary", "phase"},
                         "both the summary and the current phase must appear over time")

    # --------------------------------------------------------------- terminal

    def test_done_state_shows_a_full_bar_and_a_check(self):
        self.forge("start", "s", "4", "summary")
        self.forge("done", "clean pass")
        out = self.render()
        self.assertIn("✓", out)
        self.assertIn("clean pass", out)
        self.assertNotIn("·", out.split("▕")[1].split("▏")[0])

    def test_failed_state_shows_a_cross_and_the_reason(self):
        self.forge("start", "s", "4", "summary")
        self.forge("step", "1", "x")
        self.forge("fail", "could not be hardened")
        out = self.render()
        self.assertIn("✗", out)
        self.assertIn("abandoned", out)
        self.assertIn("could not be hardened", out)

    def test_done_state_expires_and_deletes_its_state_file(self):
        self.forge("start", "s", "4", "summary")
        self.forge("done", "clean")
        state_files = list((self.state / "forge").glob("*.json"))
        self.assertEqual(len(state_files), 1)
        far_future = 10 ** 12
        self.assertEqual(self.render(SKILLFORGE_NOW=far_future), "")
        self.assertFalse(state_files[0].exists(),
                         "an expired forge must clean up after itself")

    # ------------------------------------------------------------ several at once

    def slot_files(self):
        return sorted((self.state / "forge").glob("*.json"))

    def frames(self, span=range(1000, 1030), **extra):
        return [self.render(SKILLFORGE_NOW=t, **extra) for t in span]

    def test_a_single_forge_carries_no_counter(self):
        """The [k/N] marker is the multiplicity signal. Showing [1/1] on the common
        case would make it noise, and nothing about one forge has changed."""
        self.forge("start", "only-one", "4", "summary")
        self.assertNotIn("[1/1]", self.render(SKILLFORGE_NOW=1000))

    def test_both_live_forges_are_named_over_time(self):
        """The reported defect: the bar named one job while a different one ran. A
        rendering that can hide a live forge is not acceptable, so assert that BOTH
        names actually reach the screen."""
        self.forge("start", "alpha", "8", "the alpha summary")
        self.forge("start", "beta", "12", "the beta summary")
        out = "".join(self.frames())
        self.assertIn("alpha", out)
        self.assertIn("beta", out)

    def test_every_frame_announces_how_many_are_live(self):
        self.forge("start", "alpha", "8", "one")
        self.forge("start", "beta", "12", "two")
        for f in self.frames():
            self.assertRegex(f, r"\[[12]/2\]",
                             "a frame that shows one of two forges must say so")

    def test_each_frame_shows_exactly_one_forge_and_its_own_numbers(self):
        """A frame must never mix forge A's name with forge B's progress: that is the
        precise shape of the bug (the bar said 11/12 for the wrong job)."""
        self.forge("start", "alpha", "8", "one")
        self.forge("start", "beta", "12", "two")
        self.forge("step", "--name", "alpha", "2", "alpha phase")
        self.forge("step", "--name", "beta", "9", "beta phase")
        for f in self.frames():
            if "alpha" in f:
                self.assertIn("2/8", f)
                self.assertNotIn("beta", f)
            else:
                self.assertIn("beta", f)
                self.assertIn("9/12", f)
                self.assertNotIn("alpha", f)

    def test_rotation_is_stable_within_a_window_and_moves_between_them(self):
        self.forge("start", "alpha", "8", "one")
        self.forge("start", "beta", "12", "two")
        who = lambda t: ("alpha" if "alpha" in self.render(SKILLFORGE_NOW=t) else "beta")
        first = [who(t) for t in range(1002, 1006)]
        self.assertEqual(len(set(first)), 1, "the shown forge must not flicker every second")
        self.assertNotEqual(who(1002), who(1008), "6s later a different forge must show")

    def test_a_third_forge_joins_the_rotation(self):
        for name, steps in (("aaa", "4"), ("bbb", "6"), ("ccc", "8")):
            self.forge("start", name, steps, "summary for " + name)
        out = "".join(self.frames(span=range(1000, 1040)))
        for name in ("aaa", "bbb", "ccc"):
            self.assertIn(name, out)
        self.assertRegex(out, r"\[3/3\]")

    def test_segment_width_is_constant_within_a_rotation_window(self):
        """Constant width is what stops the host clearing and redrawing the line every
        second, which reads to the eye as the bar blinking."""
        self.forge("start", "alpha", "8", "one")
        self.forge("start", "beta", "12", "two")
        widths = {len(self.render(SKILLFORGE_NOW=t)) for t in range(1002, 1006)}
        self.assertEqual(len(widths), 1, "width wobbled inside one rotation window")

    def test_one_forge_expiring_does_not_disturb_the_other(self):
        self.forge("start", "keeper", "8", "still going")
        self.forge("start", "goner", "4", "about to finish")
        self.forge("done", "--name", "goner", "shipped")
        self.assertEqual(len(self.slot_files()), 2)
        out = self.render(SKILLFORGE_NOW=10 ** 12)
        self.assertIn("keeper", out, "the live forge must survive its neighbour's reaping")
        self.assertNotIn("goner", out)
        self.assertNotIn("[1/2]", out, "one live forge, so no counter")
        left = [p.name for p in self.slot_files()]
        self.assertEqual(len(left), 1, "only the expired slot may be removed")

    def test_a_finished_forge_still_shows_its_check_beside_a_live_one(self):
        self.forge("start", "keeper", "8", "still going")
        self.forge("start", "finished", "4", "done already")
        self.forge("done", "--name", "finished", "clean pass")
        out = "".join(self.frames())
        self.assertIn("✓", out)
        self.assertIn("finished", out)
        self.assertIn("keeper", out)

    def test_an_unreadable_slot_file_is_skipped_not_fatal(self):
        self.forge("start", "healthy", "8", "summary")
        junk = self.state / "forge" / "zz-broken.json"
        junk.write_text('{"name":"trunc', encoding="utf-8")
        out = self.render(SKILLFORGE_NOW=1000)
        self.assertIn("healthy", out)
        self.assertNotIn("[1/2]", out, "garbage must not be counted as a forge")
        self.assertTrue(junk.exists(), "the renderer must not delete what it cannot read")

    def test_an_empty_phase_does_not_shift_the_other_fields(self):
        """Fields are read with a separator. Tab is IFS whitespace, so an empty field
        collapses and every later field shifts by one.

        The summary must be NON-empty and the phase empty: with both blank -- they are
        the last two fields -- nothing can shift, and this test passed against a build
        whose separator had been mutated back to a tab. With a summary present, the
        tab build reads it into `phase` and prints it in a window where the phase
        belongs."""
        forge_dir = self.state / "forge"
        forge_dir.mkdir(parents=True, exist_ok=True)
        (forge_dir / "blank.forge.json").write_text(
            '{"name":"blankish","summary":"SUMMARY-TEXT","phase":"","step":2,'
            '"steps":4,"status":"active","started":900,"updated":900}', encoding="utf-8")
        # (t/5) % 3 != 2 is a phase window: the phase is empty, so nothing but padding
        # may follow the percentage.
        phase_frame = self.render(SKILLFORGE_NOW=1005)
        self.assertIn("blankish", phase_frame)
        self.assertIn("2/4", phase_frame)
        self.assertNotIn("SUMMARY-TEXT", phase_frame,
                         "the summary was read into the phase field")
        self.assertIn("SUMMARY-TEXT", self.render(SKILLFORGE_NOW=1000),
                      "and it must still appear in its own window")

    def test_a_terminal_record_with_no_finished_time_is_not_destroyed_at_once(self):
        """`now - 0` is past every TTL, so treating a missing `finished` as 0 deleted a
        hand-written or foreign `done` record on its very first render, whatever its
        age. The clock falls back to `updated`, then `started`."""
        forge_dir = self.state / "forge"
        forge_dir.mkdir(parents=True, exist_ok=True)
        f = forge_dir / "nofin.forge.json"
        f.write_text('{"name":"nofin","summary":"s","phase":"p","step":4,"steps":4,'
                     '"status":"done","started":900}', encoding="utf-8")
        self.assertIn("nofin", self.render(SKILLFORGE_NOW=905),
                      "a fresh record was reaped on its first render")
        self.assertTrue(f.exists())
        self.assertEqual(self.render(SKILLFORGE_NOW=10 ** 12), "",
                         "and it must still expire once it is genuinely old")
        self.assertFalse(f.exists())

    def test_a_terminal_record_with_no_clock_at_all_is_never_reaped(self):
        """With no finished, updated or started there is no age to measure, and the
        renderer must not destroy state it cannot reason about."""
        forge_dir = self.state / "forge"
        forge_dir.mkdir(parents=True, exist_ok=True)
        f = forge_dir / "timeless.forge.json"
        f.write_text('{"name":"timeless","phase":"p","step":4,"steps":4,'
                     '"status":"done"}', encoding="utf-8")
        self.render(SKILLFORGE_NOW=10 ** 12)
        self.assertTrue(f.exists(), "a record with no clock was deleted anyway")

    def test_a_record_falls_back_to_updated_when_finished_is_absent(self):
        forge_dir = self.state / "forge"
        forge_dir.mkdir(parents=True, exist_ok=True)
        f = forge_dir / "upd.forge.json"
        f.write_text('{"name":"upd","summary":"s","phase":"p","step":4,"steps":4,'
                     '"status":"done","started":900,"updated":900}', encoding="utf-8")
        self.assertIn("upd", self.render(SKILLFORGE_NOW=910), "within the TTL")
        self.assertEqual(self.render(SKILLFORGE_NOW=1000), "", "past the TTL")
        self.assertFalse(f.exists())

    def test_a_nonsense_step_budget_does_not_render_as_complete(self):
        """jq stores 99999999999999999999 as the float 1e+20. A numeric guard in the
        shell folded that back to 1, so a forge at step 5 drew a full bar at 100%."""
        forge_dir = self.state / "forge"
        forge_dir.mkdir(parents=True, exist_ok=True)
        (forge_dir / "huge.forge.json").write_text(
            '{"name":"huge","summary":"s","phase":"p","step":5,"steps":1e+20,'
            '"status":"active","started":900,"updated":900}', encoding="utf-8")
        out = self.render(SKILLFORGE_NOW=1001)
        self.assertIn("huge", out)
        self.assertNotIn("100%", out, "an unusable step budget must not read as done")
        bar = out.split("\u2595")[1].split("\u258f")[0]
        self.assertNotIn("\u2588", bar, "and it must not draw a filled bar")

    def test_the_reaper_does_not_delete_a_forge_that_start_just_recreated(self):
        """Deciding expiry for all N files and deleting afterwards let `skillforge
        start`, reusing a finished slot in place, land inside the window: the reaper
        then deleted the brand-new active forge. Measured at 40 of 40 trials."""
        forge_dir = self.state / "forge"
        forge_dir.mkdir(parents=True, exist_ok=True)
        stale = ('{"name":"old%d","summary":"s","phase":"p","step":4,"steps":4,'
                 '"status":"done","started":100,"finished":100}')
        for i in range(12):
            (forge_dir / ("old%d.forge.json" % i)).write_text(stale % i, encoding="utf-8")
        (forge_dir / "zz.forge.json").write_text(
            '{"name":"zz","summary":"s","phase":"p","step":4,"steps":4,'
            '"status":"done","started":100,"finished":100}', encoding="utf-8")
        # stdin=DEVNULL, not a pipe: the renderer consumes its payload first, so a pipe
        # left open would hold it at the `cat` until after `start` had finished and no
        # race could occur at all. It has to be reading slots WHILE start writes one.
        render = subprocess.Popen([str(RENDER)], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  env=self.env(SKILLFORGE_NOW=99999))
        started = subprocess.run([str(CLI), "start", "zz", "8", "restarted"],
                                 capture_output=True, text=True, env=self.env())
        render.wait()
        self.assertEqual(started.returncode, 0, started.stderr)
        alive = subprocess.run([str(CLI), "show", "--name", "zz"],
                               capture_output=True, text=True, env=self.env())
        self.assertEqual(alive.returncode, 0,
                         "the reaper deleted the forge start had just created")
        self.assertEqual(json.loads(alive.stdout)["status"], "active")

    # ------------------------------------------------------------- completion

    def hand_write(self, name, **fields):
        """A forge record placed on disk directly, so a state the CLI will not produce
        (a foreign or older record) can still be rendered."""
        d = self.state / "forge"
        d.mkdir(parents=True, exist_ok=True)
        rec = {"name": name, "summary": "the summary", "phase": "the phase",
               "step": 1, "steps": 12, "status": "active",
               "started": 900, "updated": 900}
        rec.update(fields)
        (d / (name + ".forge.json")).write_text(json.dumps(rec), encoding="utf-8")

    def bar_of(self, out):
        return out.split("▕")[1].split("▏")[0]

    def test_an_active_forge_at_the_end_of_its_budget_is_not_shown_as_finished(self):
        """The reported defect: `12/12 100%` with a full bar, while the forge was still
        running. Only the spinner separated it from a ✓."""
        self.forge("start", "s", "12", "summary")
        self.forge("step", "12", "still working")
        out = self.render(SKILLFORGE_NOW=1001)
        self.assertIn("12/12", out)
        self.assertNotIn("100%", out, "an active forge must never read 100%")
        self.assertIn("99%", out)
        self.assertEqual(self.bar_of(out)[-1], "▒",
                         "the last cell is reserved: `▒` is spent, not finished")
        self.assertNotEqual(self.bar_of(out).count("█"), 12)

    def test_an_overrun_is_visible_rather_than_clamped_away(self):
        self.forge("start", "s", "12", "summary")
        self.forge("step", "14", "beyond budget")
        out = self.render(SKILLFORGE_NOW=1001)
        self.assertIn("14/12", out, "the step reached must keep rising past the budget")
        self.assertIn("over", out)
        self.assertNotIn("100%", out)
        self.assertIn("»", self.bar_of(out), "the reserved cell must say why")

    def test_an_overrun_and_a_forge_at_its_budget_do_not_render_alike(self):
        self.forge("start", "s", "12", "summary")
        self.forge("step", "12", "at the budget")
        at_budget = self.render(SKILLFORGE_NOW=1001)
        self.forge("step", "14", "past the budget")
        past = self.render(SKILLFORGE_NOW=1001)
        self.assertNotEqual(at_budget, past,
                            "step 14 of 12 rendered identically to step 12 of 12")

    def test_done_is_the_only_state_that_fills_the_bar(self):
        self.forge("start", "s", "12", "summary")
        self.forge("step", "12", "still working")
        active = self.bar_of(self.render(SKILLFORGE_NOW=1001))
        self.forge("done", "shipped")
        finished = self.render(SKILLFORGE_NOW=1001)
        self.assertNotIn("·", self.bar_of(finished))
        self.assertNotIn("»", self.bar_of(finished))
        self.assertEqual(self.bar_of(finished).count("█"), 12)
        self.assertNotEqual(active, self.bar_of(finished))
        self.assertIn("✓", finished)

    def test_done_after_an_overrun_still_fills_the_bar(self):
        self.forge("start", "s", "12", "summary")
        self.forge("step", "14", "beyond budget")
        self.forge("done", "shipped late")
        out = self.render(SKILLFORGE_NOW=1001)
        self.assertIn("✓", out)
        self.assertEqual(self.bar_of(out).count("█"), 12)

    def test_a_one_step_budget_still_distinguishes_running_from_finished(self):
        """With steps == 1 there is no "one below full" in budget terms, but the bar has
        12 cells whatever the budget, so the distinction is still drawable."""
        self.forge("start", "s", "1", "summary")
        self.forge("step", "1", "the only step")
        active = self.render(SKILLFORGE_NOW=1001)
        self.assertNotIn("100%", active)
        self.assertEqual(self.bar_of(active)[-1], "▒")
        self.forge("done", "shipped")
        self.assertEqual(self.bar_of(self.render(SKILLFORGE_NOW=1001)).count("█"), 12)

    def test_a_step_field_wide_enough_for_the_overrun_keeps_the_width_constant(self):
        self.hand_write("wide", step=100, steps=9)
        widths = {len(ANSI.sub("", self.render(SKILLFORGE_NOW=t))) for t in range(1001, 1005)}
        self.assertEqual(len(widths), 1, "the step field wobbled inside one window")
        self.assertIn("100/9", self.render(SKILLFORGE_NOW=1001))

    # ------------------------------------------------------------------ idle

    def test_a_forge_stepped_seconds_ago_renders_exactly_as_it_always_did(self):
        self.forge("start", "s", "12", "summary")
        self.forge("step", "4", "red-team round 1")
        for t in range(1000, 1012):
            out = self.render(SKILLFORGE_NOW=t)
            self.assertNotIn("idle", out, "a fresh forge must not be marked idle")

    def test_a_forge_below_the_threshold_is_not_marked_idle(self):
        self.hand_write("fresh", updated=1000)
        # One second under the default 2700s threshold.
        self.assertNotIn("idle", self.render(SKILLFORGE_NOW=1000 + 2699))

    def test_a_forge_at_the_threshold_reports_its_idle_time(self):
        self.hand_write("quiet", updated=1000)
        out = self.render(SKILLFORGE_NOW=1000 + 2700)
        self.assertIn("idle 45m", out)

    def test_the_reported_defect_reads_as_three_hours_stale(self):
        """3h07m at step 11 of 12, which is what the user was looking at."""
        self.hand_write("skill-compounder", step=11, updated=1000,
                        phase="round 5: authoring gap, unreachable check")
        out = self.render(SKILLFORGE_NOW=1000 + 11220)
        self.assertIn("idle 3h07m", out)

    def test_a_days_old_forge_does_not_hand_the_tail_a_huge_number(self):
        self.hand_write("ancient", updated=1)
        out = self.render(SKILLFORGE_NOW=10 ** 12)
        self.assertIn("999d+", out)
        self.assertLessEqual(len(ANSI.sub("", out)), 120)

    def test_the_idle_report_does_not_change_the_segment_width(self):
        """Crossing the threshold must cost the host no clear-and-redraw: the marker is
        folded INTO the padded tail, not appended beside it."""
        self.hand_write("quiet", updated=1000)
        fresh = len(ANSI.sub("", self.render(SKILLFORGE_NOW=1001)))
        idle = {len(ANSI.sub("", self.render(SKILLFORGE_NOW=1000 + n)))
                for n in (2700, 3600, 7200, 90000, 900000)}
        self.assertEqual(idle, {fresh}, "the idle marker changed the segment width")

    def test_an_idle_forge_stops_pulsing_its_leading_edge(self):
        self.hand_write("quiet", step=4, updated=1000)
        fresh = {self.bar_of(self.render(SKILLFORGE_NOW=1000 + n)) for n in (1, 2, 3, 4)}
        self.assertIn("▓", "".join(fresh), "a live forge pulses")
        quiet = {self.bar_of(self.render(SKILLFORGE_NOW=1000 + 2700 + n))
                 for n in (1, 2, 3, 4)}
        self.assertEqual(len(quiet), 1, "a quiet forge must not shimmer")
        self.assertNotIn("▓", "".join(quiet))

    def test_the_threshold_is_tunable(self):
        self.hand_write("quiet", updated=1000)
        self.assertIn("idle", self.render(SKILLFORGE_NOW=1100, SKILLFORGE_IDLE_SECS=60))
        self.assertNotIn("idle", self.render(SKILLFORGE_NOW=1100,
                                             SKILLFORGE_IDLE_SECS=999999))

    def test_a_nonsense_threshold_falls_back_to_the_default(self):
        self.hand_write("quiet", updated=1000)
        self.assertNotIn("idle", self.render(SKILLFORGE_NOW=1100,
                                             SKILLFORGE_IDLE_SECS="banana"))

    def test_a_record_with_no_updated_stamp_is_never_called_idle(self):
        """Never claim a forge is stale on the strength of a stamp that is missing."""
        d = self.state / "forge"
        d.mkdir(parents=True, exist_ok=True)
        (d / "nostamp.forge.json").write_text(
            '{"name":"nostamp","summary":"s","phase":"p","step":4,"steps":12,'
            '"status":"active","started":900}', encoding="utf-8")
        out = self.render(SKILLFORGE_NOW=10 ** 9)
        self.assertIn("nostamp", out)
        self.assertNotIn("idle", out)

    def test_a_malformed_updated_stamp_is_never_called_idle(self):
        for bad in ('"yesterday"', "null", "true", "-5", "1e+30", "[]"):
            with self.subTest(updated=bad):
                d = self.state / "forge"
                d.mkdir(parents=True, exist_ok=True)
                (d / "bad.forge.json").write_text(
                    '{"name":"badstamp","summary":"s","phase":"p","step":4,"steps":12,'
                    '"status":"active","started":900,"updated":%s}' % bad,
                    encoding="utf-8")
                out = self.render(SKILLFORGE_NOW=10 ** 9)
                self.assertIn("badstamp", out)
                self.assertNotIn("idle", out)

    def test_a_stamp_in_the_future_is_not_an_idle_forge(self):
        self.hand_write("skewed", updated=10 ** 9)
        self.assertNotIn("idle", self.render(SKILLFORGE_NOW=1000))

    def test_a_terminal_record_is_never_marked_idle(self):
        """A done record inside its clear-out window must render as it always has."""
        for state, ttl in (("done", "SKILLFORGE_DONE_TTL"), ("failed", "SKILLFORGE_FAIL_TTL")):
            with self.subTest(state=state):
                self.hand_write("closed", status=state, step=12,
                                updated=1000, finished=1000)
                out = self.render(SKILLFORGE_NOW=1020, **{ttl: 10 ** 9})
                self.assertIn("closed", out)
                self.assertNotIn("idle", out)

    def test_each_rotating_forge_reports_its_own_idle_time(self):
        self.hand_write("alpha", updated=1000)
        self.hand_write("bravo", updated=11900)     # ~20 min, the observed p90
        self.hand_write("chuck", updated=13000)     # under two minutes
        seen = {}
        for t in range(1000 + 12100, 1000 + 12100 + 30):
            out = ANSI.sub("", self.render(SKILLFORGE_NOW=t))
            self.assertRegex(out, r"\[\d/3\]", "the rotation counter must survive")
            for name in ("alpha", "bravo", "chuck"):
                if name in out:
                    seen.setdefault(name, set()).add("idle" in out)
        self.assertEqual(sorted(seen), ["alpha", "bravo", "chuck"],
                         "every live forge must still take its turn")
        self.assertEqual(seen["alpha"], {True}, "3h20m idle and not reported")
        self.assertEqual(seen["bravo"], {False}, "20m idle and reported as stale")
        self.assertEqual(seen["chuck"], {False}, "under 2m idle and reported as stale")

    def test_rotation_width_stays_constant_with_a_mix_of_idle_and_live(self):
        self.hand_write("alpha", updated=1)
        self.hand_write("bravo", updated=1000 + 12000)
        for window in (range(12102, 12106), range(12108, 12112)):
            widths = {len(ANSI.sub("", self.render(SKILLFORGE_NOW=1000 + t)))
                      for t in window}
            self.assertEqual(len(widths), 1, "width wobbled inside one rotation window")

    # ------------------------------------------------------- width in columns

    def test_a_wide_glyph_phase_does_not_wobble_the_segment(self):
        """The tail was padded to a count of CODEPOINTS. A CJK codepoint is two
        terminal cells, so a Japanese phase drew 86 columns while the ASCII summary
        beside it drew 77, and the segment oscillated every five seconds inside one
        rotation window -- the exact blink the padding exists to prevent."""
        self.forge("start", "jp", "12", "ascii summary")
        self.forge("step", "5", "スキルを鍛える段階")
        widths = {columns(self.render(SKILLFORGE_NOW=t)) for t in range(1000, 1030)}
        self.assertEqual(len(widths), 1, "wide glyphs wobbled the segment: %s" % widths)

    def test_an_emoji_phase_does_not_wobble_the_segment(self):
        self.forge("start", "em", "12", "ascii summary")
        self.forge("step", "5", "🔥🔥🔥 forging 🔥🔥🔥")
        widths = {columns(self.render(SKILLFORGE_NOW=t)) for t in range(1000, 1030)}
        self.assertEqual(len(widths), 1, "emoji wobbled the segment: %s" % widths)

    def test_a_very_long_name_cannot_wrap_the_line(self):
        self.forge("start", "x" * 200, "12", "summary")
        out = self.render(SKILLFORGE_NOW=1001)
        self.assertLess(columns(out), 120, "a long name wrapped the status line")
        self.assertIn("…", out)

    def test_a_very_long_close_message_cannot_wrap_the_line(self):
        self.forge("start", "s", "12", "summary")
        self.forge("done", "Q" * 300)
        self.assertLess(columns(self.render(SKILLFORGE_NOW=1001)), 120)
        self.forge("start", "t", "12", "summary")
        self.forge("fail", "Z" * 300)
        self.assertLess(columns(self.render(SKILLFORGE_NOW=1001)), 120)

    # ------------------------------------------------- knobs must not silence it

    def test_a_nonsense_tunable_falls_back_instead_of_blanking_the_segment(self):
        """DONE_TTL and FAIL_TTL go straight to `--argjson`. Set to a non-number they
        killed jq on every slot, so every record was skipped and the whole segment went
        blank with live forges on disk -- exit 0, nothing on stderr."""
        self.forge("start", "s", "12", "summary")
        self.forge("step", "5", "phase")
        good = columns(self.render(SKILLFORGE_NOW=1001))
        for knob in ("SKILLFORGE_DONE_TTL", "SKILLFORGE_FAIL_TTL", "SKILLFORGE_TAIL_WIDTH",
                     "SKILLFORGE_BAR_WIDTH", "SKILLFORGE_ROTATE_SECS",
                     "SKILLFORGE_IDLE_SECS", "SKILLFORGE_NAME_WIDTH"):
            for value in ("abc", " ", "-1", "1e5", "", "0",
                          "999999999999999999999999", "9" * 40):
                with self.subTest(knob=knob, value=value):
                    out = self.render(SKILLFORGE_NOW=1001, **{knob: value})
                    self.assertIn("forge", out,
                                  "%s=%r blanked the segment" % (knob, value))
                    self.assertEqual(columns(out), good,
                                     "%s=%r changed the width" % (knob, value))

    def test_a_nameless_record_neither_blanks_nor_counts(self):
        """`[ -n "$name" ] || exit 0` printed NOTHING, so one nameless record blanked
        the segment outright and stole one frame in N from the rotation."""
        d = self.state / "forge"
        d.mkdir(parents=True, exist_ok=True)
        (d / "empty.forge.json").write_text(
            '{"name":"","summary":"s","phase":"p","step":4,"steps":12,'
            '"status":"active","started":900,"updated":900}', encoding="utf-8")
        self.forge("start", "real", "12", "summary")
        for t in range(1000, 1020):
            out = self.render(SKILLFORGE_NOW=t)
            self.assertIn("real", out, "a nameless record blanked the segment")
            self.assertNotIn("[", out, "a nameless record was counted as a forge")
        self.assertTrue((d / "empty.forge.json").exists(),
                        "the renderer must not delete what it will not draw")

    # ------------------------------------------- an unrecognised state is RUNNING

    def test_an_unrecognised_status_is_never_rendered_as_finished(self):
        """`status: "paused"` fell through every safeguard at once: a full bar at 100%
        under a spinner, never reported idle, and an overrun with no marker."""
        for status in ('"paused"', '"Active"', "123", '"running"'):
            with self.subTest(status=status):
                d = self.state / "forge"
                d.mkdir(parents=True, exist_ok=True)
                (d / "odd.forge.json").write_text(
                    '{"name":"odd","summary":"s","phase":"p","step":14,"steps":12,'
                    '"status":%s,"started":900,"updated":900}' % status,
                    encoding="utf-8")
                out = self.render(SKILLFORGE_NOW=900 + 11220)
                self.assertIn("odd", out)
                self.assertNotIn("100%", out)
                self.assertNotIn("✓", out)
                self.assertIn("»", self.bar_of(out), "the overrun went unmarked")
                self.assertIn("idle 3h07m", out, "an unknown state was never called idle")

    # ------------------------------------------------ the four states are distinct

    def test_behind_at_budget_over_budget_and_done_all_draw_different_bars(self):
        self.forge("start", "s", "12", "summary")
        bars = {}
        for step, label in ((11, "behind"), (12, "at budget"), (14, "over")):
            self.forge("step", str(step), "phase")
            bars[label] = self.bar_of(self.render(SKILLFORGE_NOW=1001))
        self.forge("done", "shipped")
        bars["done"] = self.bar_of(self.render(SKILLFORGE_NOW=1001))
        self.assertEqual(len(set(bars.values())), 4,
                         "two of these four states draw the same bar: %s" % bars)
        self.assertEqual(bars["behind"][-1], "·")
        self.assertEqual(bars["at budget"][-1], "▒")
        self.assertEqual(bars["over"][-1], "»")
        self.assertEqual(bars["done"][-1], "█")

    def test_an_idle_forge_freezes_its_spinner(self):
        """A spinner still turning beside the words "idle 3h07m" contradicts itself,
        and motion is what the reported defect was misread as."""
        self.hand_write("quiet", updated=1000)
        live = {self.render(SKILLFORGE_NOW=1000 + n).strip()[0] for n in (1, 2, 3, 4)}
        self.assertGreater(len(live), 1, "a live forge must still spin")
        quiet = {self.render(SKILLFORGE_NOW=1000 + 2700 + n).strip()[0]
                 for n in (1, 2, 3, 4)}
        self.assertEqual(len(quiet), 1, "the spinner kept turning on a quiet forge")

    def test_a_live_forge_carries_no_idle_colouring_at_all(self):
        """Not just the visible text: a normally-stepped forge must emit the same
        escape sequences it always did, so nothing about the segment changes."""
        self.forge("start", "s", "12", "summary")
        self.forge("step", "5", "phase")
        raw = self.raw(SKILLFORGE_NOW=1001)
        self.assertNotIn("\033[33m", raw)
        self.assertEqual(raw.count("\033[0m"), 4,
                         "an extra escape seam appeared in a live forge's segment")

    def test_a_huge_rotation_period_cannot_hide_a_forge(self):
        """All digits, so a shape-only guard passed it. `idx = (now / ROTATE) % n` was
        then pinned at 0 and forges two and three were never shown -- silently, while
        the [k/N] stamp truthfully said there were three. One typo from the exact
        defect rotation was built to prevent."""
        for name in ("alpha", "bravo", "chuck"):
            self.forge("start", name, "12", "summary for " + name)
        seen = set()
        for t in range(1000, 1040):
            out = self.render(SKILLFORGE_NOW=t, SKILLFORGE_ROTATE_SECS="999999999")
            seen.update(n for n in ("alpha", "bravo", "chuck") if n in out)
        self.assertEqual(seen, {"alpha", "bravo", "chuck"},
                         "a huge rotation period hid a live forge")

    def test_emoji_presentation_glyphs_are_measured_as_two_cells(self):
        """✅ ⭐ ⌚ live in the narrow Miscellaneous Symbols ranges but render double
        width. Counted as one, the segment blinked every five seconds."""
        for text in ("✅✅✅ all checks passed", "⭐⌚⭐ mixed", "🔥⚡🎉 done"):
            with self.subTest(text=text):
                for f in (self.state / "forge").glob("*.json"):
                    f.unlink()
                self.forge("start", "g", "12", text)
                self.forge("step", "5", "an ascii phase")
                widths = {columns(self.render(SKILLFORGE_NOW=t))
                          for t in range(1000, 1030)}
                self.assertEqual(len(widths), 1, "%r wobbled: %s" % (text, widths))

    def test_combining_marks_are_measured_as_no_cells(self):
        decomposed = unicodedata.normalize("NFD", "café näive résumé")
        self.forge("start", "c", "12", "an ascii summary")
        self.forge("step", "5", decomposed)
        widths = {columns(self.render(SKILLFORGE_NOW=t)) for t in range(1000, 1030)}
        self.assertEqual(len(widths), 1, "combining marks wobbled: %s" % widths)

    def test_the_leading_edge_stops_pulsing_once_the_budget_is_spent(self):
        """`▓` beside the reserved `▒` reads as an antialiasing artifact, not as two
        states."""
        self.forge("start", "s", "12", "summary")
        self.forge("step", "12", "at the budget")
        bars = {self.bar_of(self.render(SKILLFORGE_NOW=t)) for t in range(1000, 1010)}
        self.assertEqual(len(bars), 1, "the bar shimmered against its own marker")
        self.assertNotIn("▓", bars.pop())

    # ---------------------------------------------------------------- wrapper

    def test_wrapper_composes_base_then_forge(self):
        base = self.state / "statusline-base.sh"
        base.write_text('#!/usr/bin/env bash\ncat >/dev/null\nprintf "MYBASE"\n', encoding="utf-8")
        base.chmod(0o755)
        self.assertEqual(self.render(script=WRAPPER), "MYBASE")

        self.forge("start", "forged-thing", "4", "summary")
        out = self.render(script=WRAPPER, SKILLFORGE_NOW=1001)
        self.assertTrue(out.startswith("MYBASE"), "the user's own status line must come first")
        self.assertIn("forged-thing", out)

    def test_wrapper_caches_the_base_segment(self):
        base = self.state / "statusline-base.sh"
        counter = self.state / "base-calls"
        base.write_text(
            '#!/usr/bin/env bash\ncat >/dev/null\n'
            'echo x >> "%s"\nprintf "BASE"\n' % counter, encoding="utf-8")
        base.chmod(0o755)
        for _ in range(5):
            self.render(script=WRAPPER)
        calls = len(counter.read_text(encoding="utf-8").split())
        self.assertEqual(calls, 1, "base must be cached, not re-run on every refresh")


class ShellPortabilityTest(unittest.TestCase):
    """The status line runs under whatever shell the user has.

    `status` is read-only in zsh, where it aliases $?. Assigning to it aborted the eval
    and the whole forge segment rendered empty, with no error anywhere: every zsh user
    saw nothing while the tests, running under bash, passed.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"

    def tearDown(self):
        self.tmp.cleanup()

    def render_with(self, shell, forges=(("portable", "4", "rendering under both shells"),)):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": self.tmp.name,
               "SKILL_COMPOUNDER_STATE": str(self.state),
               "SKILLFORGE_NOW": "1000"}
        for name, steps, summary in forges:
            forge = subprocess.run([str(APP / "bin" / "skillforge"), "start",
                                    name, steps, summary],
                                   capture_output=True, text=True, env=env)
            self.assertEqual(forge.returncode, 0, forge.stderr)
        out = subprocess.run([shell, str(APP / "statusline" / "skillforge-status.sh")],
                             input='{"session_id":"x"}', capture_output=True, text=True,
                             env=env)
        self.assertEqual(out.returncode, 0, "%s: %s" % (shell, out.stderr))
        return out.stdout

    TWO = (("portable", "4", "rendering under both shells"),
           ("second-forge", "12", "the neighbouring forge"))

    def test_bash_and_zsh_render_the_same_segment(self):
        if shutil.which("zsh") is None:
            self.skipTest("zsh is not installed here; CI installs it")
        under_bash = self.render_with("bash")
        self.assertIn("portable", under_bash)
        self.setUp()
        under_zsh = self.render_with("zsh")
        self.assertEqual(under_bash, under_zsh,
                         "the forge segment must render identically under both shells")

    def test_bash_and_zsh_agree_with_several_forges_live(self):
        """`path` is zsh's array view of $PATH. Reading a slot filename into a variable
        called `path` replaced the command search path with that one directory, so every
        later `jq` in the renderer was "command not found": the bar still drew, but the
        tail lost its padding and the width wobbled once a second, for zsh users only.
        Nothing errored. This is the same family as the `status` trap above."""
        if shutil.which("zsh") is None:
            self.skipTest("zsh is not installed here; CI installs it")
        under_bash = self.render_with("bash", forges=self.TWO)
        self.setUp()
        under_zsh = self.render_with("zsh", forges=self.TWO)
        self.assertEqual(under_bash, under_zsh,
                         "multi-forge rendering diverged between the two shells")
        self.assertIn("/2]", under_bash, "two live forges must show a counter")


if __name__ == "__main__":
    unittest.main(verbosity=2)
