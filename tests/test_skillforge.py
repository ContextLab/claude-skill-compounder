#!/usr/bin/env python3
"""Runs the real skillforge CLI as a subprocess against a real state directory."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"


class SkillforgeTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.file = self.state / "forge" / "current.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([str(CLI), *args], capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                                   "HOME": str(self.state),
                                   "SKILL_COMPOUNDER_STATE": str(self.state)})

    def state_json(self):
        return json.loads(self.file.read_text(encoding="utf-8"))

    def test_start_writes_complete_state(self):
        r = self.run_cli("start", "my-skill", "8", "does", "a", "useful", "thing")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.state_json()
        self.assertEqual(s["name"], "my-skill")
        self.assertEqual(s["steps"], 8)
        self.assertEqual(s["step"], 0)
        self.assertEqual(s["status"], "active")
        self.assertEqual(s["summary"], "does a useful thing")
        self.assertIsInstance(s["started"], int)

    def test_step_advances_and_records_phase(self):
        self.run_cli("start", "s", "6", "summary")
        r = self.run_cli("step", "3", "red-team round 1")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.state_json()
        self.assertEqual(s["step"], 3)
        self.assertEqual(s["phase"], "red-team round 1")
        self.assertIn("[3/6]", r.stdout)

    def test_step_clamps_to_total(self):
        self.run_cli("start", "s", "4", "summary")
        self.run_cli("step", "99", "overshoot")
        self.assertEqual(self.state_json()["step"], 4)

    def test_done_fills_the_bar(self):
        self.run_cli("start", "s", "5", "summary")
        self.run_cli("step", "2", "midway")
        self.run_cli("done", "clean red-team pass")
        s = self.state_json()
        self.assertEqual(s["status"], "done")
        self.assertEqual(s["step"], s["steps"])
        self.assertEqual(s["phase"], "clean red-team pass")
        self.assertIn("finished", s)

    def test_fail_records_reason_without_filling_the_bar(self):
        self.run_cli("start", "s", "5", "summary")
        self.run_cli("step", "2", "midway")
        self.run_cli("fail", "3 rounds, still ambiguous")
        s = self.state_json()
        self.assertEqual(s["status"], "failed")
        self.assertEqual(s["step"], 2, "a failed forge must not show a full bar")
        self.assertEqual(s["phase"], "3 rounds, still ambiguous")

    def test_clear_removes_state(self):
        self.run_cli("start", "s", "3", "summary")
        self.run_cli("clear")
        self.assertFalse(self.file.exists())

    # ------------------------------------------------------------- validation

    def test_summary_is_required(self):
        r = self.run_cli("start", "s", "3")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("summary is required", r.stderr)
        self.assertFalse(self.file.exists())

    def test_non_numeric_steps_rejected(self):
        r = self.run_cli("start", "s", "many", "summary")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("positive integer", r.stderr)

    def test_zero_steps_rejected(self):
        r = self.run_cli("start", "s", "0", "summary")
        self.assertNotEqual(r.returncode, 0)

    def test_step_without_start_is_an_error(self):
        r = self.run_cli("step", "1", "phase")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no active forge", r.stderr)

    def test_unknown_command_is_an_error(self):
        r = self.run_cli("frobnicate")
        self.assertNotEqual(r.returncode, 0)

    def test_done_without_start_is_a_silent_noop(self):
        r = self.run_cli("done")
        self.assertEqual(r.returncode, 0, "closing an absent forge must not error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
