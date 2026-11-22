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

from test_support import NOW, Case, iso, seed_event

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


FINDING = "in-00000000000000a1"
REPORT_FINDING = "in-00000000000000b2"


class FindingSettling(Settling):
    def finding(self, ident=FINDING, source="facet", offset=0, project=None):
        event = {"ts": iso(NOW + offset), "type": "insight", "session": "insights", "id": ident, "source": source,
                 "text": "It used the wrong flag."}
        if source == "facet":
            event["project"] = project or self.box.project
        seed_event(self.box.events, event)  # as written: box.seed would give a report item a project
        return event

    def remind(self, session, offset):
        self.box.log({"type": "remind", "insights": [FINDING]}, CLAUDE_CODE_SESSION_ID=session,
                     COMPOUND_NOW=NOW + offset)

    def listed(self, **kw):
        return [row for row in self.unsettled(**kw) if row["type"] == "insight"]

    def test_skip_settles_a_finding_by_id(self):
        self.finding()
        proc = self.box.run("skip", "--settles", FINDING, "--why", "not real", COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 0)
        self.assertEqual(self.box.read_events()[-1]["settles"], FINDING)
        self.assertEqual(self.listed(), [])
        (row,) = self.box.json("insights", "--json")["findings"]
        self.assertEqual((row["id"], row["state"]), (FINDING, "settled"))

    def test_add_settles_a_finding_by_id(self):
        self.finding()
        self.box.add("a-lesson", "Use when it matters.", "Body.\n", "--settles", FINDING, COMPOUND_NOW=NOW + 10)
        self.assertEqual(self.box.read_events()[-1]["settles"], FINDING)
        self.assertEqual(self.listed(), [])

    def test_settles_a_finding_while_the_session_has_two_unsettled_captures(self):
        self.finding()
        first, second = self.capture(offset=1), self.capture(offset=2, call="another")
        proc = self.box.run("skip", "--settles", FINDING, "--why", "not real", COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 0)
        self.assertEqual(self.box.read_events()[-1]["settles"], FINDING)
        self.assertEqual(sorted(event["id"] for event in self.unsettled() if event["type"] == "capture"),
                         sorted([first["id"], second["id"]]))
        self.assertEqual(self.listed(), [])

    def test_a_limit_keeps_what_is_owed_before_the_findings(self):
        for index in range(3):
            self.finding("in-00000000000000a%d" % index, offset=index)
        first, second = self.capture(offset=5), self.capture(offset=6, call="another")
        both = self.unsettled("--limit", "2")
        self.assertEqual([event["id"] for event in both], [first["id"], second["id"]])
        one = self.unsettled("--limit", "1")
        self.assertEqual([event["id"] for event in one], [second["id"]])
        three = self.unsettled("--limit", "3")
        self.assertEqual([event["type"] for event in three], ["capture", "capture", "insight"])
        self.assertEqual(three[-1]["id"], "in-00000000000000a2")
        self.assertEqual(len(self.unsettled("--limit", "9")), 5)

    def test_a_finding_shown_three_times_can_still_be_settled(self):
        self.finding()
        for index, session in enumerate(("s-one", "s-two", "s-three")):
            self.remind(session, 1 + index)
        self.assertEqual(self.listed(), [])
        self.assertEqual(self.box.json("insights", "--json", COMPOUND_NOW=NOW + 20)["findings"][0]["state"], "quiet")
        self.assertExit(self.box.run("skip", "--settles", FINDING, "--why", "no", COMPOUND_NOW=NOW + 20), 0)
        self.assertEqual(self.box.json("insights", "--json", COMPOUND_NOW=NOW + 21)["findings"][0]["state"], "settled")

    def remind_headless(self, session, offset):
        self.box.log({"type": "remind", "insights": [FINDING], "headless": True}, CLAUDE_CODE_SESSION_ID=session,
                     COMPOUND_NOW=NOW + offset)

    def state(self, offset=20):
        return self.box.json("insights", "--json", COMPOUND_NOW=NOW + offset)["findings"][0]["state"]

    def test_three_headless_reminds_leave_a_finding_listed(self):
        self.finding()
        for index, session in enumerate(("p-one", "p-two", "p-three")):
            self.remind_headless(session, 1 + index)
        self.assertTrue(all(event.get("headless") is True for event in self.box.read_events()
                            if event["type"] == "remind"), "compound log kept the field")
        self.assertEqual([row["id"] for row in self.listed()], [FINDING])
        self.assertEqual(self.state(), "open")

    def test_three_interactive_reminds_make_a_finding_quiet(self):
        self.finding()
        for index, session in enumerate(("s-one", "s-two", "s-three")):
            self.remind(session, 1 + index)
        self.assertEqual(self.listed(), [])
        self.assertEqual(self.state(), "quiet")

    def test_headless_reminds_count_for_nothing_beside_interactive_ones(self):
        self.finding()
        self.remind("s-one", 1)
        self.remind_headless("p-one", 2)
        self.remind("s-two", 3)
        self.remind_headless("p-two", 4)
        # Two sessions with someone at them, and two without: still open.
        self.assertEqual([row["id"] for row in self.listed()], [FINDING])
        self.assertEqual(self.state(), "open")
        # A session that was headless once and then interactive counts once, as interactive.
        self.remind("p-one", 5)
        self.assertEqual(self.listed(), [])
        self.assertEqual(self.state(), "quiet")

    def test_only_headless_true_is_left_out(self):
        self.finding()
        for index, (session, value) in enumerate((("s-one", False), ("s-two", "true"), ("s-three", 1))):
            self.box.log({"type": "remind", "insights": [FINDING], "headless": value}, CLAUDE_CODE_SESSION_ID=session,
                         COMPOUND_NOW=NOW + 1 + index)
        self.assertEqual(self.state(), "quiet")

    def facet_without_project(self, project):
        """A facet finding whose `project` is `project`, or missing when it is None: the
        harvest writes none, so it is written as it would be, with seed_event."""
        event = {"ts": iso(NOW), "type": "insight", "session": "insights", "id": FINDING, "source": "facet",
                 "text": "It used the wrong flag."}
        if project is not None:
            event["project"] = project
        seed_event(self.box.events, event)
        before = self.box.snapshot()
        proc = self.box.run("add", "--name", "a-lesson", "--when", "Use when it matters.", "--settles", FINDING,
                            stdin="Body.\n", COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 2)
        self.assertIn("names no project", proc.stderr)
        self.assertIn("--level user", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)
        # It is listed in every project, and status shows its command with --level user.
        self.assertEqual([row["id"] for row in self.listed()], [FINDING])
        self.assertIn("--settles %s --level user" % FINDING, self.box.run("status", COMPOUND_NOW=NOW + 10).stdout)
        self.box.add("a-lesson", "Use when it matters.", "Body.\n", "--level", "user", "--settles", FINDING,
                     COMPOUND_NOW=NOW + 10)
        self.assertEqual(self.box.read_events()[-1]["settles"], FINDING)
        self.assertEqual(self.state(11), "settled")

    def test_add_records_a_facet_finding_with_an_empty_project_at_the_user_level_only(self):
        self.facet_without_project("")

    def test_add_records_a_facet_finding_with_no_project_field_at_the_user_level_only(self):
        self.facet_without_project(None)

    def test_add_records_a_facet_finding_whose_project_is_blank_at_the_user_level_only(self):
        self.facet_without_project("   ")

    def test_settles_refuses_an_expired_or_unknown_finding(self):
        self.finding()
        before = self.box.snapshot()
        late = self.box.run("skip", "--settles", FINDING, "--why", "late", COMPOUND_NOW=NOW + 15 * 86400)
        self.assertExit(late, 2)
        self.assertIn("names no unsettled capture or finding", late.stderr)
        unknown = self.box.run("skip", "--settles", "in-ffffffffffffffff", "--why", "who", COMPOUND_NOW=NOW + 10)
        self.assertExit(unknown, 2)
        self.assertIn("--settles", unknown.stderr)
        self.assertEqual(self.box.snapshot(), before)
        self.assertEqual(self.box.json("insights", "--json", COMPOUND_NOW=NOW + 15 * 86400)["findings"][0]["state"],
                         "expired")

    def test_a_skip_aimed_at_a_finding_leaves_the_sessions_ineffective_recall_owed(self):
        self.finding()
        recall = self.weak(session="s-one", offset=1)
        self.assertExit(self.box.run("skip", "--settles", FINDING, "--why", "no", CLAUDE_CODE_SESSION_ID="s-one",
                                     COMPOUND_NOW=NOW + 5), 0)
        self.assertEqual(self.unsettled("--session", "s-one"), [recall])

    def test_a_capture_is_not_settled_by_an_event_that_names_a_finding(self):
        self.finding()
        capture = self.capture(session="s-one", offset=1)
        self.assertExit(self.box.run("skip", "--settles", FINDING, "--why", "no", CLAUDE_CODE_SESSION_ID="s-one",
                                     COMPOUND_NOW=NOW + 5), 0)
        self.assertEqual([row["id"] for row in self.unsettled("--session", "s-one")], [capture["id"]])
        self.assertEqual(self.open_captures()[0]["id"], capture["id"])

    def test_add_refuses_a_report_finding_at_the_project_level(self):
        self.finding(REPORT_FINDING, source="report")
        before = self.box.snapshot()
        proc = self.box.run("add", "--name", "a-lesson", "--when", "Use when it matters.", "--settles",
                            REPORT_FINDING, stdin="Body.\n", COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 2)
        self.assertIn("--level user", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)

    def test_add_records_a_report_finding_at_the_user_level(self):
        self.finding(REPORT_FINDING, source="report")
        self.box.add("a-lesson", "Use when it matters.", "Body.\n", "--level", "user", "--settles", REPORT_FINDING,
                     COMPOUND_NOW=NOW + 10)
        self.assertEqual(self.box.read_events()[-1]["settles"], REPORT_FINDING)
        self.assertEqual(self.listed(), [])

    def other_project(self):
        other = os.path.join(self.box.root, "other-project")
        os.makedirs(other, exist_ok=True)
        return os.path.realpath(other)

    def test_add_refuses_a_finding_of_another_project_at_the_project_level(self):
        other = self.other_project()
        self.finding(project=other)
        before = self.box.snapshot()
        proc = self.box.run("add", "--name", "a-lesson", "--when", "Use when it matters.", "--settles", FINDING,
                            stdin="Body.\n", COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 2)
        self.assertIn(other, proc.stderr)
        self.assertIn("--level user", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)
        self.assertFalse(os.path.exists(os.path.join(self.box.project, ".claude", "compound", "lessons", "a-lesson")))
        self.assertEqual([row["id"] for row in self.box.json("insights", "--json", COMPOUND_NOW=NOW + 11)["findings"]
                          if row["state"] == "open"], [FINDING])

    def test_a_finding_of_another_project_is_recorded_at_the_user_level_from_here(self):
        self.finding(project=self.other_project())
        self.box.add("a-lesson", "Use when it matters.", "Body.\n", "--level", "user", "--settles", FINDING,
                     COMPOUND_NOW=NOW + 10)
        self.assertEqual(self.box.read_events()[-1]["settles"], FINDING)
        self.assertEqual(self.box.json("insights", "--json", COMPOUND_NOW=NOW + 11)["findings"][0]["state"], "settled")

    def test_a_finding_of_another_project_is_declined_from_here(self):
        self.finding(project=self.other_project())
        proc = self.box.run("skip", "--settles", FINDING, "--why", "not real", COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 0)
        self.assertEqual(self.box.read_events()[-1]["settles"], FINDING)

    def test_a_finding_of_this_project_named_by_another_path_to_it_is_recorded_at_the_project_level(self):
        link = os.path.join(self.box.root, "project-link")
        os.symlink(self.box.project, link)
        self.finding(project=link)
        self.box.add("a-lesson", "Use when it matters.", "Body.\n", "--settles", FINDING, COMPOUND_NOW=NOW + 10)
        self.assertEqual(self.box.read_events()[-1]["settles"], FINDING)

    def test_a_skip_that_settles_a_finding_says_finding(self):
        self.finding()
        proc = self.box.run("skip", "--settles", FINDING, "--why", "not real", COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 0)
        self.assertIn("settles finding %s" % FINDING, proc.stdout)
        self.assertNotIn("capture", proc.stdout)


if __name__ == "__main__":
    unittest.main()
