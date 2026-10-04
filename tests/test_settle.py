#!/usr/bin/env python3
"""Where a lesson's body comes from, and the one definition of "settled".

  add: `--body TEXT`, `--body-file PATH`, `--body -`; `--update` never reads stdin unless
       `--body -` asks for it; a plain `add` waits a short time for stdin and no longer
  settled: a capture, and a strengthening, as `events --unsettled`, `status` and a bare
       `skip` all read them
"""

import json
import os
import socket
import subprocess
import sys
import time
import unittest

from test_support import NOW, Case

# Longer than the CLI waits for stdin, far shorter than a hang.
PATIENCE = 30


class OpenStdin(Case):
    """Runs the CLI with a stdin that never ends: its write end stays open in the test."""

    def held(self, kind, *args, **kw):
        send = kw.pop("send", b"")
        if kind == "pipe":
            reader, writer = os.pipe()
            child_end, close = reader, lambda: (os.close(reader), os.close(writer))
            if send:
                os.write(writer, send)
        else:
            ours, theirs = socket.socketpair()
            child_end, close = theirs.fileno(), lambda: (ours.close(), theirs.close())
            if send:
                ours.sendall(send)
        began = time.time()
        try:
            proc = subprocess.run([sys.executable, self.box.script] + list(args), stdin=child_end,
                                  cwd=self.box.project, env=self.box.env(**kw), stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, universal_newlines=True, timeout=PATIENCE)
        finally:
            close()
        proc.took = time.time() - began
        return proc

    def text(self, name="held"):
        with open(os.path.join(self.box.lesson_dir(name), "SKILL.md")) as handle:
            return handle.read()


class UpdateNeverWaitsTest(OpenStdin):
    def test_update_with_no_body_returns_at_once_on_a_pipe_and_on_a_socket_that_never_close(self):
        self.box.add("held", "Use when held.", "The first body.\n")
        for index, kind in enumerate(("pipe", "socket")):
            proc = self.held(kind, "add", "--update", "--name", "held", "--match", "danger-%d" % index)
            self.assertExit(proc, 0)
            self.assertLess(proc.took, 5, "it read nothing, so it waited for nothing")
            self.assertIn("The first body.", self.text())
            self.assertIn("danger-%d" % index, self.text())
        learned = [e for e in self.box.read_events() if e["type"] == "learn"]
        self.assertEqual([e["update"] for e in learned], [False, True, True])

    def test_update_takes_a_new_body_from_the_flag_or_a_file_with_stdin_still_open(self):
        self.box.add("held", "Use when held.", "The first body.\n")
        proc = self.held("socket", "add", "--update", "--name", "held", "--body", "The second body.")
        self.assertExit(proc, 0)
        self.assertIn("The second body.\n", self.text())
        self.assertNotIn("The first body.", self.text())
        path = os.path.join(self.box.root, "body.md")
        with open(path, "w") as handle:
            handle.write("The third body,\non two lines.\n")
        proc = self.held("pipe", "add", "--update", "--name", "held", "--body-file", path)
        self.assertExit(proc, 0)
        self.assertTrue(self.text().endswith("---\nThe third body,\non two lines.\n"), self.text())

    def test_update_reads_stdin_when_the_body_is_asked_for_as_a_dash(self):
        self.box.add("held", "Use when held.", "The first body.\n")
        proc = self.box.run("add", "--update", "--name", "held", "--body", "-", stdin="From stdin.\n")
        self.assertExit(proc, 0)
        self.assertTrue(self.text().endswith("---\nFrom stdin.\n"), self.text())

    def test_update_refuses_text_waiting_on_stdin_that_no_flag_asked_for(self):
        """A here-document given without `--body -` must not be dropped in silence."""
        self.box.add("held", "Use when held.", "The first body.\n")
        before = self.box.snapshot()
        path = os.path.join(self.box.root, "heredoc")
        with open(path, "w") as handle:
            handle.write("A body nobody asked for.\n")
        before = self.box.snapshot()
        with open(path) as handle:
            filed = subprocess.run([sys.executable, self.box.script, "add", "--update", "--name", "held", "--when",
                                    "Use when new."], stdin=handle, cwd=self.box.project, env=self.box.env(),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                   timeout=PATIENCE)
        for proc in (filed, self.held("pipe", "add", "--update", "--name", "held", send=b"More of the same.\n"),
                     self.held("socket", "add", "--update", "--name", "held", send=b"And again.\n")):
            self.assertExit(proc, 2)
            self.assertIn("--body -", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)

    def test_the_body_flags_exclude_each_other_and_a_missing_file_is_refused(self):
        self.box.add("held", "Use when held.", "The first body.\n")
        before = self.box.snapshot()
        proc = self.box.run("add", "--update", "--name", "held", "--body", "x", "--body-file", "/nonexistent")
        self.assertExit(proc, 2)
        proc = self.box.run("add", "--update", "--name", "held", "--body-file", "/nonexistent/body.md")
        self.assertExit(proc, 2)
        self.assertIn("--body-file", proc.stderr)
        proc = self.box.run("add", "--update", "--name", "held", "--body", "   ")
        self.assertExit(proc, 2)
        self.assertEqual(self.box.snapshot(), before)


class AddWaitsBrieflyTest(OpenStdin):
    def test_a_plain_add_with_a_stdin_that_never_speaks_gives_up_and_names_the_flags(self):
        for kind in ("pipe", "socket"):
            proc = self.held(kind, "add", "--name", "never", "--when", "Use when never.")
            self.assertExit(proc, 2)
            self.assertLess(proc.took, 10)
            self.assertIn("--body", proc.stderr)
            self.assertIn("--body-file", proc.stderr)
        self.assertFalse(os.path.exists(self.box.lesson_dir("never")))
        self.assertEqual(self.box.read_events(), [])

    def test_a_plain_add_whose_stdin_speaks_and_then_never_ends_gives_up_too(self):
        proc = self.held("pipe", "add", "--name", "never", "--when", "Use when never.", send=b"Half a body")
        self.assertExit(proc, 2)
        self.assertLess(proc.took, 10)
        self.assertFalse(os.path.exists(self.box.lesson_dir("never")))

    def test_a_plain_add_still_reads_its_body_on_stdin(self):
        self.box.add("piped", "Use when piped.", "Piped in.\n")
        self.assertTrue(self.text("piped").endswith("---\nPiped in.\n"))
        path = os.path.join(self.box.root, "body.md")
        with open(path, "w") as handle:
            handle.write("From a file on stdin.\n")
        with open(path) as handle:
            proc = subprocess.run([sys.executable, self.box.script, "add", "--name", "filed", "--when", "Use when."],
                                  stdin=handle, cwd=self.box.project, env=self.box.env(), stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, universal_newlines=True, timeout=PATIENCE)
        self.assertExit(proc, 0)
        self.assertTrue(self.text("filed").endswith("---\nFrom a file on stdin.\n"))

    def test_a_plain_add_takes_its_body_from_the_flag_or_a_file_with_stdin_open(self):
        proc = self.held("socket", "add", "--name", "flagged", "--when", "Use when flagged.", "--body", "By flag.")
        self.assertExit(proc, 0)
        self.assertLess(proc.took, 5)
        self.assertTrue(self.text("flagged").endswith("---\nBy flag.\n"))
        path = os.path.join(self.box.root, "body.md")
        with open(path, "w") as handle:
            handle.write("By file.\n")
        proc = self.held("pipe", "add", "--name", "filed", "--when", "Use when filed.", "--body-file", path)
        self.assertExit(proc, 0)
        self.assertTrue(self.text("filed").endswith("---\nBy file.\n"))


class Settling(Case):
    def capture(self, session="s-one", offset=0, **fields):
        event = {"type": "capture", "tool": "Bash", "failed": "./build.sh", "error": "a profile is required",
                 "fixed": "./build.sh --profile dev", "session": session, "call": "call-%s-%d" % (session, offset)}
        event.update(fields)
        self.box.log(event, COMPOUND_NOW=NOW + offset)
        return self.box.read_events()[-1]

    def weak(self, name="flaky", session="s-one", offset=0):
        self.box.log({"type": "recall", "lesson": name, "tool": "Bash", "call": "./flaky.sh", "error": "boom",
                      "ineffective": True, "session": session}, COMPOUND_NOW=NOW + offset)
        return self.box.read_events()[-1]

    def unsettled(self, *flags, **kw):
        kw.setdefault("COMPOUND_NOW", NOW + 1000)
        return self.box.json("events", "--unsettled", "--json", *flags, **kw)

    def open_captures(self):
        return self.box.json("status", "--json", COMPOUND_NOW=NOW + 1000)["open"]["unsettled"]


class TerminalDeclineTest(Settling):
    def test_a_bare_skip_outside_a_session_settles_the_one_capture_the_project_has(self):
        event = self.capture()
        proc = self.box.run("skip", "--why", "a one-off", CLAUDE_CODE_SESSION_ID=None, COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 0)
        self.assertIn("declined", proc.stdout)
        self.assertIn(event["id"], proc.stdout)
        skip = self.box.read_events()[-1]
        self.assertEqual((skip["type"], skip["session"], skip["settles"]), ("skip", "", event["id"]))
        self.assertEqual(self.unsettled(), [])
        self.assertEqual(self.unsettled("--session", "s-one"), [])
        self.assertEqual(self.open_captures(), [])

    def test_with_several_it_is_refused_and_the_ids_are_listed(self):
        first = self.capture(offset=0)
        second = self.capture(session="s-two", offset=5)
        before = self.box.snapshot()
        proc = self.box.run("skip", "--why", "which one?", CLAUDE_CODE_SESSION_ID=None, COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 2)
        self.assertIn(first["id"], proc.stderr)
        self.assertIn(second["id"], proc.stderr)
        self.assertIn("--settles", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)

    def test_a_capture_of_another_project_is_not_this_project_s_to_decline(self):
        elsewhere = os.path.join(self.box.root, "elsewhere")
        os.makedirs(elsewhere)
        other = self.capture(session="s-two", project=elsewhere)
        mine = self.capture(offset=5)
        proc = self.box.run("skip", "--why", "mine only", CLAUDE_CODE_SESSION_ID=None, COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 0)
        self.assertEqual(self.box.read_events()[-1]["settles"], mine["id"])
        self.assertEqual([e["id"] for e in self.unsettled()], [other["id"]])

    def test_with_none_a_bare_skip_is_still_a_decline_on_record(self):
        proc = self.box.run("skip", "--why", "nothing owed", CLAUDE_CODE_SESSION_ID=None)
        self.assertExit(proc, 0)
        self.assertNotIn("settles", self.box.read_events()[-1])

    def test_a_decline_by_id_from_no_session_is_what_the_session_is_told(self):
        """What the mod's stop check asks: `events --unsettled --session S`."""
        event = self.capture()
        self.assertEqual([e["id"] for e in self.unsettled("--session", "s-one")], [event["id"]])
        self.assertEqual(self.unsettled("--session", "s-two"), [])
        self.assertExit(self.box.run("skip", "--settles", event["id"], "--why", "no", CLAUDE_CODE_SESSION_ID=None,
                                     COMPOUND_NOW=NOW + 10), 0)
        self.assertEqual(self.unsettled("--session", "s-one"), [])
        self.assertEqual(self.open_captures(), [])


class StrengtheningTest(Settling):
    def setUp(self):
        Settling.setUp(self)
        self.box.add("flaky", "Use when flaky.", "Run it twice.\n", COMPOUND_NOW=NOW - 100)

    def owed(self, session="s-one"):
        return [(e["type"], e.get("lesson")) for e in self.unsettled("--session", session)]

    def test_an_ineffective_recall_is_owed_by_its_session_once_per_lesson(self):
        self.weak(offset=1)
        newest = self.weak(offset=2)
        self.assertEqual(self.unsettled("--session", "s-one"), [newest])
        self.assertEqual(self.owed("s-two"), [])
        self.box.log({"type": "recall", "lesson": "fine", "session": "s-one", "ineffective": False})
        self.assertEqual(self.owed(), [("recall", "flaky")])

    def test_a_rewrite_settles_it_and_a_plain_recording_of_another_lesson_does_not(self):
        self.weak(offset=1)
        self.box.add("another", CLAUDE_CODE_SESSION_ID="s-one", COMPOUND_NOW=NOW + 2)
        self.assertEqual(self.owed(), [("recall", "flaky")])
        self.assertExit(self.box.run("add", "--update", "--name", "flaky", "--match", "flaky\\.sh$",
                                     CLAUDE_CODE_SESSION_ID="s-one", COMPOUND_NOW=NOW + 3), 0)
        self.assertEqual(self.owed(), [])
        self.weak(offset=4)
        self.assertEqual(self.owed(), [("recall", "flaky")], "a recall after the rewrite is owed again")

    def test_a_skip_from_the_session_settles_it_and_one_from_another_session_does_not(self):
        self.weak(offset=1)
        self.assertExit(self.box.run("skip", "--why", "x", CLAUDE_CODE_SESSION_ID="s-two", COMPOUND_NOW=NOW + 2), 0)
        self.assertEqual(self.owed(), [("recall", "flaky")])
        self.assertExit(self.box.run("skip", "--why", "x", CLAUDE_CODE_SESSION_ID="s-one", COMPOUND_NOW=NOW + 3), 0)
        self.assertEqual(self.owed(), [])

    def test_removing_the_lesson_settles_it(self):
        self.weak(offset=1)
        self.assertExit(self.box.run("rm", "flaky", CLAUDE_CODE_SESSION_ID=None, COMPOUND_NOW=NOW + 2), 0)
        self.assertEqual(self.owed(), [])

    def test_making_it_a_skill_settles_it(self):
        self.weak(offset=1)
        self.assertExit(self.box.run("skill", "flaky", COMPOUND_NOW=NOW + 2), 0)
        self.assertEqual(self.owed(), [])

    def test_moving_it_under_a_new_name_settles_it(self):
        self.weak(offset=1)
        self.assertExit(self.box.run("promote", "flaky", "--to", "user", "--as", "flaky-anywhere",
                                     COMPOUND_NOW=NOW + 2), 0)
        self.assertEqual(self.box.read_events()[-1]["was"], "flaky")
        self.assertEqual(self.owed(), [])

    def test_both_debts_are_listed_together_and_one_rewrite_from_the_session_settles_both(self):
        capture = self.capture(offset=1)
        recall = self.weak(offset=2)
        self.assertEqual(self.unsettled("--session", "s-one"), [capture, recall])
        self.assertExit(self.box.run("add", "--update", "--name", "flaky", "--when", "Use when it flakes.",
                                     CLAUDE_CODE_SESSION_ID="s-one", COMPOUND_NOW=NOW + 3), 0)
        self.assertEqual(self.unsettled("--session", "s-one"), [])

    def test_status_still_lists_only_captures_as_unsettled(self):
        self.weak(offset=1)
        self.assertEqual(self.open_captures(), [])


if __name__ == "__main__":
    unittest.main()
