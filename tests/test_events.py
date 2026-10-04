#!/usr/bin/env python3
"""log, events, skip, the counts read off the log, and ineffective detection."""

import json
import os
import subprocess
import sys
import unittest

from test_support import NOW, Case


class LogTest(Case):
    def test_log_appends_the_event_with_ts_session_and_project_filled_in(self):
        proc = self.box.run("log", stdin='{"type": "guard", "lesson": "zsh-equals-word", "tool": "Bash"}')
        self.assertExit(proc, 0)
        self.assertEqual(proc.stdout, "")
        with open(self.box.events) as handle:
            text = handle.read()
        self.assertEqual(text.count("\n"), 1)
        self.assertEqual(json.loads(text), {
            "ts": "2026-09-21T14:13:20Z", "type": "guard", "session": "sess-0001-aaaa",
            "project": self.box.project, "lesson": "zsh-equals-word", "tool": "Bash"})
        self.assertEqual(list(json.loads(text))[:4], ["ts", "type", "session", "project"])

    def test_fields_the_caller_gives_are_kept(self):
        self.box.log({"type": "reuse", "session": "other-session", "project": "/some/where",
                      "ts": "2026-01-01T00:00:00Z", "lessons": ["a", "b"], "nested": {"k": [1, 2]}})
        event = self.box.read_events()[0]
        self.assertEqual(event, {"ts": "2026-01-01T00:00:00Z", "type": "reuse", "session": "other-session",
                                 "project": "/some/where", "lessons": ["a", "b"], "nested": {"k": [1, 2]}})

    def test_without_a_session_id_the_session_is_empty(self):
        self.box.log({"type": "nudge", "calls": 12}, CLAUDE_CODE_SESSION_ID=None)
        self.assertEqual(self.box.read_events()[0]["session"], "")

    def test_json_flag_prints_the_event_written(self):
        proc = self.box.run("log", "--json", stdin='{"type": "nudge", "calls": 9}')
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout), self.box.read_events()[0])

    def test_non_ascii_text_survives(self):
        self.box.log({"type": "error", "where": "hook", "message": "café ✓"})
        self.assertEqual(self.box.read_events()[0]["message"], "café ✓")

    def test_a_multi_line_value_is_still_one_line_of_the_log(self):
        self.box.log({"type": "error", "where": "hook", "message": "line one\nline two"})
        with open(self.box.events) as handle:
            self.assertEqual(len(handle.read().splitlines()), 1)

    def test_refusals_write_nothing(self):
        for text in ("", "not json", "[]", '"text"', "{}", '{"type": 3}', '{"type": ""}', '{"type": "Has Space"}'):
            proc = self.box.run("log", stdin=text)
            self.assertExit(proc, 2)
            self.assertTrue(proc.stderr.startswith("compound: "), proc.stderr)
        self.assertFalse(os.path.exists(self.box.events))

    def test_twenty_concurrent_appends_all_parse(self):
        env = self.box.env()
        procs = []
        for index in range(20):
            proc = subprocess.Popen(
                [sys.executable, self.box.script, "log"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env, cwd=self.box.project, universal_newlines=True)
            procs.append((proc, json.dumps({"type": "recall", "lesson": "lesson-%02d" % index,
                                            "error": "x" * 3000})))
        for proc, payload in procs:
            proc.stdin.write(payload)
            proc.stdin.close()
        for proc, _payload in procs:
            self.assertEqual(proc.wait(timeout=60), 0, proc.stderr.read())
            proc.stdout.close()
            proc.stderr.close()
        with open(self.box.events) as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), 20)
        events = [json.loads(line) for line in lines]
        self.assertEqual(sorted(event["lesson"] for event in events), ["lesson-%02d" % i for i in range(20)])
        self.assertTrue(all(len(event["error"]) == 3000 for event in events))


class EventsTest(Case):
    def setUp(self):
        Case.setUp(self)
        self.box.log({"type": "reuse", "lessons": ["alpha"]}, COMPOUND_NOW=NOW, CLAUDE_CODE_SESSION_ID="s-one")
        self.box.log({"type": "guard", "lesson": "alpha"}, COMPOUND_NOW=NOW + 100, CLAUDE_CODE_SESSION_ID="s-one")
        self.box.log({"type": "recall", "lesson": "beta"}, COMPOUND_NOW=NOW + 200, CLAUDE_CODE_SESSION_ID="s-two")
        self.box.log({"type": "error", "where": "judge", "message": "did not parse"},
                     COMPOUND_NOW=NOW + 300, CLAUDE_CODE_SESSION_ID="s-two")

    def types(self, *args):
        return [event["type"] for event in self.box.json("events", "--json", *args)]

    def test_everything_in_order(self):
        self.assertEqual(self.types(), ["reuse", "guard", "recall", "error"])

    def test_type_filter(self):
        self.assertEqual(self.types("--type", "guard"), ["guard"])
        self.assertEqual(self.types("--type", "promote"), [])

    def test_session_filter(self):
        self.assertEqual(self.types("--session", "s-two"), ["recall", "error"])

    def test_since_takes_an_iso_time_or_epoch_seconds_and_is_inclusive(self):
        self.assertEqual(self.types("--since", "2026-09-21T14:15:00Z"), ["guard", "recall", "error"])
        self.assertEqual(self.types("--since", str(NOW + 200)), ["recall", "error"])
        self.assertEqual(self.types("--since", "2026-09-22"), [])

    def test_filters_combine(self):
        self.assertEqual(self.types("--session", "s-two", "--type", "error", "--since", str(NOW)), ["error"])

    def test_limit_keeps_the_newest(self):
        self.assertEqual(self.types("--limit", "2"), ["recall", "error"])

    def test_a_bad_since_is_a_usage_error(self):
        proc = self.box.run("events", "--since", "last tuesday")
        self.assertExit(proc, 2)
        self.assertIn("--since", proc.stderr)

    def test_human_output_is_one_line_an_event(self):
        proc = self.box.run("events")
        self.assertExit(proc, 0)
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertIn("guard", lines[1])
        self.assertIn("alpha", lines[1])
        self.assertIn("judge: did not parse", lines[3])

    def test_no_log_is_an_empty_list(self):
        os.unlink(self.box.events)
        self.assertEqual(self.box.json("events", "--json"), [])

    def test_a_line_that_does_not_parse_is_skipped_and_said(self):
        with open(self.box.events, "a") as handle:
            handle.write("{truncated\n")
        proc = self.box.run("events", "--json")
        self.assertExit(proc, 0)
        self.assertEqual(len(json.loads(proc.stdout)), 4)
        self.assertIn("1 line(s)", proc.stderr)


class SkipTest(Case):
    def test_skip_logs_the_reason(self):
        proc = self.box.run("skip", "--why", "a one-off typo,\nnothing to keep")
        self.assertExit(proc, 0)
        self.assertEqual(self.box.read_events(), [{
            "ts": "2026-09-21T14:13:20Z", "type": "skip", "session": "sess-0001-aaaa",
            "project": self.box.project, "why": "a one-off typo, nothing to keep"}])

    def test_skip_without_a_reason_is_refused(self):
        self.assertExit(self.box.run("skip"), 2)
        proc = self.box.run("skip", "--why", "  ")
        self.assertExit(proc, 2)
        self.assertIn("--why", proc.stderr)
        self.assertFalse(os.path.exists(self.box.events))


class CountsTest(Case):
    def counts(self, name):
        return [row for row in self.box.json("list", "--json", "--scripts") if row["name"] == name][0]["counts"]

    def test_counts_read_lesson_and_lessons_by_type_name(self):
        self.box.add("alpha")
        self.box.add("beta")
        for event in (
            {"type": "reuse", "lessons": ["alpha", "beta"]},
            {"type": "reuse", "lessons": ["alpha"]},
            {"type": "reuse", "lesson": "alpha"},
            {"type": "guard", "lesson": "alpha"},
            {"type": "recall", "lesson": "beta"},
            {"type": "recall", "lessons": ["alpha", "beta"]},
            {"type": "capture", "lesson": "alpha"},
            {"type": "error", "lesson": "alpha", "message": "x"},
            {"type": "something-new", "lesson": "alpha"},
            {"type": "reuse", "lessons": "alpha"},
            {"type": "reuse", "lesson": ["alpha"]},
            {"type": "reuse", "lesson": "alpha", "lessons": ["alpha"]},
        ):
            self.box.log(event)
        self.assertEqual(self.counts("alpha"), {"reuse": 4, "guard": 1, "recall": 1, "learn": 1})
        self.assertEqual(self.counts("beta"), {"reuse": 1, "guard": 0, "recall": 2, "learn": 1})

    def test_a_script_is_counted_under_its_listed_name(self):
        os.makedirs(os.path.join(self.box.project, "scripts"))
        with open(os.path.join(self.box.project, "scripts", "release.sh"), "w") as handle:
            handle.write("# Cut a release.\n")
        self.box.log({"type": "reuse", "lessons": ["scripts/release.sh"]})
        self.assertEqual(self.counts("scripts/release.sh")["reuse"], 1)


class IneffectiveTest(Case):
    def row(self, name="flaky", **kw):
        return [row for row in self.box.json("list", "--json", **kw) if row["name"] == name][0]

    def recall(self, offset, name="flaky"):
        self.box.log({"type": "recall", "lesson": name, "tool": "Bash", "error": "boom"}, COMPOUND_NOW=NOW + offset)

    def test_two_recalls_after_the_lesson_was_written_make_it_ineffective(self):
        self.box.add("flaky")
        self.assertFalse(self.row()["ineffective"])
        self.recall(60)
        self.assertFalse(self.row()["ineffective"], "one recurrence is under the default limit of 2")
        self.recall(120)
        self.assertTrue(self.row()["ineffective"])

    def test_rewriting_the_lesson_clears_the_flag_and_later_recalls_set_it_again(self):
        self.box.add("flaky")
        self.recall(60)
        self.recall(120)
        self.assertTrue(self.row()["ineffective"])
        proc = self.box.run("add", "--name", "flaky", "--update", "--match", "the-bad-command", stdin="",
                            COMPOUND_NOW=NOW + 500)
        self.assertExit(proc, 0)
        row = self.row()
        self.assertFalse(row["ineffective"])
        self.assertEqual(row["counts"]["recall"], 2, "the count is over the whole log; only the flag resets")
        self.recall(600)
        self.assertFalse(self.row()["ineffective"])
        self.recall(700)
        self.assertTrue(self.row()["ineffective"])

    def test_recalls_older_than_the_lesson_do_not_count(self):
        self.recall(-500)
        self.recall(-400)
        self.box.add("flaky")
        self.assertFalse(self.row()["ineffective"])

    def test_the_limit_is_configurable(self):
        self.box.add("flaky")
        self.recall(60)
        self.assertTrue(self.row(COMPOUND_RECUR_LIMIT="1")["ineffective"])
        self.recall(120)
        self.assertFalse(self.row(COMPOUND_RECUR_LIMIT="3")["ineffective"])
        self.recall(180)
        self.assertTrue(self.row(COMPOUND_RECUR_LIMIT="3")["ineffective"])

    def test_a_limit_that_is_not_a_positive_number_takes_the_default(self):
        self.box.add("flaky")
        self.recall(60)
        for bad in ("0", "", "many", "-1", "9" * 23):
            self.assertFalse(self.row(COMPOUND_RECUR_LIMIT=bad)["ineffective"], bad)
        self.recall(120)
        for bad in ("0", "", "many", "-1"):
            self.assertTrue(self.row(COMPOUND_RECUR_LIMIT=bad)["ineffective"], bad)

    def test_only_recall_events_count_and_only_for_the_named_lesson(self):
        self.box.add("flaky")
        self.box.add("steady")
        self.recall(60)
        self.box.log({"type": "guard", "lesson": "flaky"}, COMPOUND_NOW=NOW + 70)
        self.box.log({"type": "reuse", "lessons": ["flaky"]}, COMPOUND_NOW=NOW + 80)
        self.recall(90, "steady")
        self.assertFalse(self.row("flaky")["ineffective"])
        self.assertFalse(self.row("steady")["ineffective"])

    def test_a_skill_can_be_ineffective_too(self):
        self.box.add("flaky")
        self.assertExit(self.box.run("skill", "flaky"), 0)
        self.recall(60)
        self.recall(120)
        row = self.row()
        self.assertEqual((row["kind"], row["ineffective"]), ("skill", True))

    def test_a_hand_edit_of_the_file_clears_the_flag(self):
        self.box.add("flaky")
        self.recall(60)
        self.recall(120)
        path = os.path.join(self.box.lesson_dir("flaky"), "SKILL.md")
        os.utime(path, (NOW + 300, NOW + 300))
        self.assertFalse(self.row()["ineffective"])


if __name__ == "__main__":
    unittest.main()
