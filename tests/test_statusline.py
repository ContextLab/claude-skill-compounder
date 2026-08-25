#!/usr/bin/env python3
"""Runs the real status-line scripts and inspects what they actually print.

The clock is pinned with SKILLFORGE_NOW so the animation is deterministic."""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"
RENDER = REPO / "statusline" / "skillforge-status.sh"
WRAPPER = REPO / "statusline" / "statusline.sh"
PAYLOAD = json.dumps({"session_id": "abc", "workspace": {"current_dir": str(REPO)}})
ANSI = re.compile(r"\033\[[0-9;]*m")


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
        r = subprocess.run([str(script)], input=PAYLOAD, capture_output=True,
                           text=True, env=self.env(**extra))
        return ANSI.sub("", r.stdout)

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
        self.forge("start", "s", "4", "summary")
        widths, fills = set(), []
        for step in (0, 1, 2, 3, 4):
            self.forge("step", str(step), "phase")
            out = self.render(SKILLFORGE_NOW=1001)   # odd -> no pulse glyph
            bar = out.split("▕")[1].split("▏")[0]
            widths.add(len(bar))
            fills.append(bar.count("█"))
        self.assertEqual(widths, {12}, "bar width must not change as it fills")
        self.assertEqual(fills, [0, 3, 6, 9, 12])

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
        state_file = self.state / "forge" / "current.json"
        self.assertTrue(state_file.exists())
        far_future = 10 ** 12
        self.assertEqual(self.render(SKILLFORGE_NOW=far_future), "")
        self.assertFalse(state_file.exists(), "an expired forge must clean up after itself")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
