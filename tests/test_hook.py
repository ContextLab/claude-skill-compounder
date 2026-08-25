#!/usr/bin/env python3
"""Runs the real reminder hook with real payloads and checks the throttling.

The hook's contract is narrow but strict: emit valid Claude Code hook JSON when it
should fire, emit NOTHING and exit 0 when it should not, and never fail loudly."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "hooks" / "compound-improvement.sh"
LONG_PROMPT = "Please implement the retry-with-backoff wrapper and wire it into the scheduler."


class HookTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, mode, payload, **extra):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state),
               "SKILL_COMPOUNDER_STATE": str(self.state)}
        env.update({k: str(v) for k, v in extra.items()})
        return subprocess.run([str(HOOK), mode], input=json.dumps(payload),
                              capture_output=True, text=True, env=env)

    # -------------------------------------------------------------- edit mode

    def test_edit_fires_only_every_nth_edit(self):
        fired = []
        for i in range(1, 10):
            r = self.run_hook("edit", {"session_id": "s1", "tool_name": "Edit"}, CI_EDIT_EVERY=3)
            self.assertEqual(r.returncode, 0)
            if r.stdout.strip():
                fired.append(i)
        self.assertEqual(fired, [3, 6, 9])

    def test_edit_output_is_valid_hook_json(self):
        r = self.run_hook("edit", {"session_id": "s1"}, CI_EDIT_EVERY=1)
        out = json.loads(r.stdout)
        self.assertTrue(out["suppressOutput"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("skill-compounder", out["hookSpecificOutput"]["additionalContext"])

    def test_edit_counters_are_per_session(self):
        self.run_hook("edit", {"session_id": "a"}, CI_EDIT_EVERY=2)
        r = self.run_hook("edit", {"session_id": "b"}, CI_EDIT_EVERY=2)
        self.assertEqual(r.stdout.strip(), "",
                         "one session's edits must not advance another's counter")

    # ------------------------------------------------------------ prompt mode

    def test_short_prompts_never_fire(self):
        for text in ("yes", "continue", "ok do it", "thanks!"):
            r = self.run_hook("prompt", {"session_id": "s1", "prompt": text})
            self.assertEqual(r.stdout.strip(), "", "short prompt %r must not fire" % text)

    def test_long_prompt_fires_once_then_is_throttled(self):
        payload = {"session_id": "s1", "prompt": LONG_PROMPT}
        first = self.run_hook("prompt", payload, CI_NOW=1000)
        second = self.run_hook("prompt", payload, CI_NOW=1300)
        self.assertNotEqual(first.stdout.strip(), "")
        self.assertEqual(second.stdout.strip(), "", "cooldown must suppress the second")

    def test_cooldown_expires(self):
        payload = {"session_id": "s1", "prompt": LONG_PROMPT}
        self.run_hook("prompt", payload, CI_NOW=1000)
        later = self.run_hook("prompt", payload, CI_NOW=1000 + 1201)
        self.assertNotEqual(later.stdout.strip(), "", "reminder must return after the cooldown")

    def test_prompt_output_is_valid_hook_json(self):
        r = self.run_hook("prompt", {"session_id": "s1", "prompt": LONG_PROMPT})
        out = json.loads(r.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("skill-compounder", out["hookSpecificOutput"]["additionalContext"])

    # ---------------------------------------------------------------- safety

    def test_malformed_payload_is_survivable(self):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state)}
        for mode in ("prompt", "edit"):
            r = subprocess.run([str(HOOK), mode], input="not json at all",
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0,
                             "a bad payload must never break the user's turn (%s)" % mode)

    def test_missing_session_id_is_survivable(self):
        r = self.run_hook("edit", {"tool_name": "Edit"}, CI_EDIT_EVERY=1)
        self.assertEqual(r.returncode, 0)
        self.assertNotEqual(r.stdout.strip(), "")

    def test_unknown_mode_is_a_silent_noop(self):
        r = self.run_hook("nonsense", {"session_id": "s1"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
