#!/usr/bin/env python3
"""A failure met before. `compound met` reduces a failed call's error to its signature,
says in how many other sessions that signature was met, and writes the meeting down. The
mod asks it when a call fails and no lesson describes the failure: a failure an earlier
session met too is one a lesson is owed for."""

import json
import unittest

from test_support import NOW, Case


class MetCase(Case):
    def met(self, error, session="sess-0001-aaaa", **kw):
        return json.loads(self.box.run("met", stdin=json.dumps({"tool": "Bash", "call": "x", "error": error}),
                                       CLAUDE_CODE_SESSION_ID=session, **kw).stdout)


class SignatureTest(MetCase):
    def test_what_differs_between_two_meetings_is_folded_away(self):
        first = self.met("Exit code 127\n(eval):1: command not found: timeout")
        second = self.met("Exit code 127\n(eval):14: command not found: timeout", session="sess-0002-bbbb")
        self.assertEqual(first["sig"], "command not found: timeout")
        self.assertEqual(second["sig"], first["sig"])
        pairs = [
            ("This agent is isolated in the worktree /Users/a/p/.claude/worktrees/agent-a1b2c3d4e5f6 but this command "
             "names git in a form too complex to verify",
             "This agent is isolated in the worktree /Users/b/q/.claude/worktrees/agent-0f9e8d7c6b5a but this command "
             "names git in a form too complex to verify"),
            ("Exit code 1\n(eval):1: no matches found: build/*.o", "Exit code 1\n(eval):3: no matches found: /tmp/x-*.png"),
            ("ModuleNotFoundError: No module named 'tomllib'", "ModuleNotFoundError: No module named 'tomli'"),
            ("<tool_use_error>Blocked: sleep 45 followed by: cat /a/b/c.output tail -3. To wait for a condition, use "
             "Monitor</tool_use_error>",
             "<tool_use_error>Blocked: sleep 100 followed by: cat /d/e/f.output tail -20. To wait for a condition, use "
             "Monitor</tool_use_error>"),
            ("error: unrecognized arguments: --profile 3", "error: unrecognized arguments: --profile 12"),
        ]
        for one, other in pairs:
            self.assertEqual(self.met(one)["sig"], self.met(other)["sig"], one)
            self.assertTrue(self.met(one)["sig"], one)
        self.assertNotEqual(self.met("zsh: command not found: timeout")["sig"],
                            self.met("zsh: command not found: gsed")["sig"])

    def test_an_error_that_says_nothing_about_the_call_has_no_signature_and_writes_nothing(self):
        for error in (
            "Exit code 1\nTraceback (most recent call last):\n  File \"t.py\", line 3, in <module>\nAssertionError: 3 != 4",
            "FAILED tests/test_x.py::test_y - assert 1 == 2\n1 failed, 3 passed in 0.2s",
            "ls: /a/b/c.txt: No such file or directory",
            "TimeoutError: browserBackend.callTool: Timeout 5000ms exceeded.",
            "ImportError: cannot import name 'x' from 'y' (/a/b/c/y.py)",
            "KeyError: 'info'",
            "Exit code 1",
            "",
            "everything was fine",
        ):
            self.assertEqual(self.met(error), {"sig": None, "sessions": 0, "captured": False}, error)
        self.assertEqual(self.box.read_events(), [])

    def test_a_credential_in_the_error_is_not_in_the_signature(self):
        said = self.met("error: invalid option --token=ghp_" + "a1B2c3D4e5" * 4)
        self.assertNotIn("ghp_", json.dumps(said))
        self.assertNotIn("ghp_", json.dumps(self.box.read_events()))


class MeetingsTest(MetCase):
    ERROR = "Exit code 127\n(eval):1: command not found: timeout"

    def test_the_sessions_counted_are_the_other_ones(self):
        self.assertEqual(self.met(self.ERROR)["sessions"], 0)
        # The same session meeting it again has met it in no OTHER session.
        self.assertEqual(self.met(self.ERROR, COMPOUND_NOW=NOW + 5)["sessions"], 0)
        self.assertEqual(self.met(self.ERROR, session="sess-0002-bbbb")["sessions"], 1)
        self.assertEqual(self.met(self.ERROR, session="sess-0003-cccc")["sessions"], 2)
        self.assertEqual(self.met(self.ERROR, session="sess-0003-cccc")["sessions"], 2)
        rows = [event for event in self.box.read_events() if event["type"] == "met"]
        self.assertEqual([(row["sig"], row["tool"], row["sessions"]) for row in rows],
                         [("command not found: timeout", "Bash", n) for n in (0, 0, 1, 2, 2)])

    def test_a_failure_a_lesson_was_owed_for_once_is_not_owed_again(self):
        self.met(self.ERROR)
        self.assertFalse(self.met(self.ERROR, session="sess-0002-bbbb")["captured"])
        self.box.log({"type": "capture", "tool": "Bash", "failed": "timeout 5 x", "error": "command not found: timeout",
                      "fixed": "gtimeout 5 x", "why": "recurred", "sig": "command not found: timeout", "met": 1,
                      "call": "toolu_01"}, CLAUDE_CODE_SESSION_ID="sess-0002-bbbb")
        said = self.met(self.ERROR, session="sess-0003-cccc")
        self.assertEqual((said["sessions"], said["captured"]), (2, True))
        # Declined or recorded, it stays captured: the signature is asked about once.
        self.assertExit(self.box.run("skip", "--why", "a one-off", CLAUDE_CODE_SESSION_ID="sess-0002-bbbb"), 0)
        self.assertTrue(self.met(self.ERROR, session="sess-0004-dddd")["captured"])

    def test_only_the_command_writes_a_meeting(self):
        proc = self.box.run("log", stdin=json.dumps({"type": "met", "sig": "command not found: timeout"}))
        self.assertExit(proc, 2)
        self.assertIn("compound met", proc.stderr)
        for stdin in ("", "[]", '{"tool": "Bash"}', '{"error": 3}'):
            self.assertExit(self.box.run("met", stdin=stdin), 2)

    def test_a_meeting_is_left_out_of_recent_and_counted_for_no_lesson(self):
        self.met(self.ERROR)
        status = self.box.run("status")
        self.assertNotIn("command not found: timeout", status.stdout)


if __name__ == "__main__":
    unittest.main()
