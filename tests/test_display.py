#!/usr/bin/env python3
"""What the text reports say to a person: the totals, the words, the times, the widths
and the colours. `--json` is the mod's and keeps every raw value."""

import json
import os
import pty
import re
import select
import subprocess
import sys
import unittest

from test_support import NOW, Case

ESC = "\x1b["


class TotalsTest(Case):
    def test_status_totals_what_the_log_holds_and_since_when(self):
        self.box.add("a-lesson", COMPOUND_NOW=NOW - 40 * 86400)
        self.box.add("a-guard", "Use when.", "Body.\n", "--match", "danger", COMPOUND_NOW=NOW - 86400)
        self.assertExit(self.box.run("add", "--name", "a-lesson", "--update", "--when", "Use when rewritten.",
                                     COMPOUND_NOW=NOW - 3000), 0)
        self.box.log({"type": "reuse", "lessons": ["a-lesson", "a-guard"]}, COMPOUND_NOW=NOW - 2000)
        self.box.log({"type": "reuse", "lessons": ["a-lesson"]}, COMPOUND_NOW=NOW - 1900)
        self.box.log({"type": "reuse", "lessons": [], "prompts": ["p1"]}, COMPOUND_NOW=NOW - 1800)
        self.box.log({"type": "guard", "lesson": "a-guard"}, COMPOUND_NOW=NOW - 1000)
        self.box.log({"type": "recall", "lesson": "a-lesson"}, COMPOUND_NOW=NOW - 500)
        data = self.box.json("status", "--json")
        # A reuse is one offer, however many items it named; a rewrite records no new lesson.
        self.assertEqual(data["totals"], {"reused": 3, "guarded": 1, "recalled": 1, "recorded": 2,
                                          "since": "2026-08-12T14:13:20Z"})
        text = self.box.run("status").stdout
        block = text.split("Compound interest\n", 1)[1].split("\n\n", 1)[0]
        self.assertEqual(block, "  3 reuses offered · 1 call stopped by a guard · 1 lesson recalled · "
                                "2 lessons recorded · since 12 Aug")
        # The log holds no duration of a failed call or of its fix: nothing is claimed saved.
        self.assertNotRegex(text, r"(?i)\b(saved|tokens|minutes)\b")

    def test_an_empty_log_totals_nothing(self):
        data = self.box.json("status", "--json")
        self.assertEqual(data["totals"], {"reused": 0, "guarded": 0, "recalled": 0, "recorded": 0, "since": None})
        text = self.box.run("status").stdout
        self.assertIn("Compound interest\n  nothing yet: the log holds no reuse, guard, recall or lesson\n", text)


class WordsTest(Case):
    def test_levels_say_that_guards_are_among_the_lessons(self):
        self.box.add("only-guard", "Use when.", "Body.\n", "--match", "danger")
        self.box.add("u-one", "Use when.", "Body.\n", "--level", "user")
        self.box.add("u-two", "Use when.", "Body.\n", "--level", "user")
        text = self.box.run("status").stdout
        self.assertNotIn("\nStore\n", text)
        block = text.split("\nLevels\n", 1)[1].split("\n\n", 1)[0].splitlines()
        self.assertEqual(block, ["  project  1 lesson   (1 guard)   0 skills",
                                 "  user     2 lessons  (0 guards)  0 skills",
                                 "  general  0 lessons  (0 guards)  0 skills"])

    def test_the_counters_are_named_reused_guarded_recalled_everywhere(self):
        self.box.add("used")
        self.box.log({"type": "reuse", "lessons": ["used"]})
        status = self.box.run("status").stdout
        self.assertRegex(status, r"name\s+level\s+kind\s+reused\s+guarded\s+recalled\s+flag")
        listing = self.box.run("list").stdout
        self.assertRegex(listing.splitlines()[0], r"^LEVEL\s+KIND\s+NAME\s+REUSED\s+GUARDED\s+RECALLED\s+FLAG\s+WHEN$")
        self.assertNotIn("USE/GRD/RCL", listing)
        self.assertRegex(listing.splitlines()[1], r"^project\s+lesson\s+used\s+1\s+0\s+0\s")

    def test_recent_shows_the_display_word_of_each_event_and_events_shows_the_log_type(self):
        self.box.log({"type": "capture", "id": "c1", "failed": "./x", "fixed": "./x --y"})
        self.box.log({"type": "guard", "lesson": "the-guard"})
        self.box.log({"type": "recall", "lesson": "the-guard"})
        self.box.log({"type": "reuse", "lessons": ["the-guard"]})
        self.box.add("the-guard")
        self.assertExit(self.box.run("skip", "--why", "nothing to keep"), 0)
        recent = self.box.run("status").stdout.split("Recent\n", 1)[1].split("\n\n", 1)[0].splitlines()
        self.assertEqual([line.split()[1] for line in recent], ["owed", "guarded", "recalled", "reused", "recorded", "declined"])
        # `events` reads the log: its types are the names `--type` takes.
        events = self.box.run("events").stdout.splitlines()
        self.assertEqual([line.split()[1] for line in events], ["capture", "guard", "recall", "reuse", "learn", "skip"])

    def test_what_is_owed_is_called_owed_under_open(self):
        self.box.log({"type": "capture", "id": "c1", "failed": "./x", "fixed": "./x --y"}, CLAUDE_CODE_SESSION_ID="other")
        opened = self.box.run("status").stdout.split("\nOpen\n", 1)[1]
        self.assertRegex(opened, r"^  owed\s+c1 ")
        self.assertNotIn("unsettled", opened)
        self.assertIn("/compound:learn settle c1", opened)


class NeverUsedTest(Case):
    def test_status_collapses_the_lessons_never_used_into_one_line(self):
        self.box.add("used")
        for index in range(4):
            self.box.add("idle-%d" % index)
        self.box.log({"type": "reuse", "lessons": ["used"]})
        text = self.box.run("status").stdout
        block = text.split("\nLessons\n", 1)[1].split("\n\n", 1)[0].splitlines()
        self.assertEqual(len(block), 3, block)
        self.assertRegex(block[1], r"^  used\s+project\s+lesson\s+1\s+0\s+0$")
        self.assertEqual(block[2], "  4 lessons never used (`compound list` shows them)")
        self.assertNotIn("idle-0", "\n".join(block))
        # The JSON still carries every row.
        names = [row["name"] for row in self.box.json("status", "--json")["lessons"]]
        self.assertEqual(sorted(names), ["idle-0", "idle-1", "idle-2", "idle-3", "used"])

    def test_one_lesson_never_used_is_singular_and_no_empty_table_is_drawn(self):
        self.box.add("idle")
        block = self.box.run("status").stdout.split("\nLessons\n", 1)[1].split("\n\n", 1)[0].splitlines()
        self.assertEqual(block, ["  1 lesson never used (`compound list` shows it)"])


class TimesTest(Case):
    def setUp(self):
        Case.setUp(self)
        # NOW is 2026-09-21 14:13:20 UTC, and the sandbox pins TZ to UTC.
        for age, kind in ((400 * 86400, "nudge"), (5 * 86400, "guard"), (86400 + 3600, "recall"), (3 * 3600, "reuse"),
                          (120, "refuse"), (5, "error")):
            self.box.log({"type": kind, "lesson": "x", "lessons": ["x"], "why": "debt", "calls": 3,
                          "where": "judge", "message": "m"}, COMPOUND_NOW=NOW - age)

    def test_events_and_status_show_relative_ages(self):
        for args in (["events"], ["status"]):
            text = self.box.run(*args).stdout
            if args == ["status"]:
                text = text.split("Recent\n", 1)[1].split("\n\n", 1)[0]
            ages = [line.strip().split("  ")[0] for line in text.splitlines()]
            self.assertEqual(ages, ["17 Aug 2025", "16 Sep", "yesterday", "3h", "2m", "5s"], args)
            self.assertNotRegex(text, r"\d{4}-\d\d-\d\dT")

    def test_json_keeps_the_raw_timestamps(self):
        stamps = [event["ts"] for event in self.box.json("events", "--json")]
        self.assertTrue(all(re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", ts) for ts in stamps), stamps)
        self.assertEqual(stamps[-1], "2026-09-21T14:13:15Z")
        recent = self.box.json("status", "--json")["recent"]
        self.assertEqual([event["ts"] for event in recent], stamps)

    def test_yesterday_is_the_calendar_day_before_and_never_less_than_a_day_ago(self):
        os.unlink(self.box.events)
        # 00:30 the day before: thirty-seven hours ago and still yesterday.
        self.box.log({"type": "nudge", "calls": 2}, COMPOUND_NOW=NOW - 37 * 3600 - 2600)
        # 23:00 the evening before, seen at 14:13: fifteen hours, said in hours.
        self.box.log({"type": "nudge", "calls": 1}, COMPOUND_NOW=NOW - 15 * 3600 - 800)
        lines = self.box.run("events").stdout.splitlines()
        self.assertEqual([line.split()[0] for line in lines], ["yesterday", "15h"])


class WidthTest(Case):
    LONG = "Use when a very long description goes on and on about the situation the lesson applies in, well past any terminal."

    def test_list_fits_the_terminal_it_is_told_of_and_ends_a_cut_with_an_ellipsis(self):
        self.box.add("a-lesson", self.LONG)
        for columns in (60, 80, 120):
            lines = self.box.run("list", COLUMNS=columns).stdout.splitlines()
            self.assertTrue(all(len(line) <= columns for line in lines), (columns, lines))
            cut = [line for line in lines if "Use when a very long" in line]
            self.assertEqual(len(cut), 1, lines)
            self.assertTrue(cut[0].endswith("…"), cut[0])
            # With no room beside the columns the description has a line of its own.
            self.assertEqual(lines[0].endswith("WHEN"), columns == 120, lines[0])
            self.assertEqual(len(lines), 2 if columns == 120 else 3, lines)
        wide = self.box.run("list", COLUMNS=400).stdout.splitlines()[1]
        self.assertTrue(wide.endswith("any terminal."), wide)
        # Piped with no width given, the description keeps its fixed cut.
        piped = self.box.run("list").stdout.splitlines()[1]
        self.assertIn(self.LONG[:69], piped)
        self.assertTrue(piped.endswith("…"))

    def test_status_recent_and_events_fit_the_terminal(self):
        self.box.log({"type": "error", "where": "judge", "message": "m " * 200})
        for args in (["events"], ["status"]):
            for columns in (60, 100):
                text = self.box.run(*args, COLUMNS=columns).stdout
                line = [one for one in text.splitlines() if "judge: m m" in one][0]
                self.assertTrue(len(line) <= columns and line.endswith("…"), (args, columns, line))


class FindTest(Case):
    def test_find_says_how_many_words_matched_only_when_not_all_did(self):
        self.box.add("zsh-equals", "Use when zsh reads an equals sign as a command.")
        every = self.box.run("find", "zsh", "equals").stdout.splitlines()[0]
        self.assertEqual(every, "lesson zsh-equals (project): Use when zsh reads an equals sign as a command.")
        some = self.box.run("find", "zsh", "xylophone", "equals").stdout.splitlines()[0]
        self.assertEqual(some, "lesson zsh-equals (project), matched 2 of 3 words (zsh, equals): Use when zsh reads an equals sign as a command.")
        self.assertNotIn("words]", every + some)
        # The score is still in the JSON.
        self.assertEqual(self.box.json("find", "zsh", "xylophone", "--json")["items"][0]["score"], 1)

    def test_find_clips_a_description_to_the_terminal(self):
        self.box.add("long-one", "Use when zsh " + "and more " * 60)
        lines = self.box.run("find", "zsh", COLUMNS=70).stdout.splitlines()
        self.assertTrue(len(lines[0]) <= 70 and lines[0].endswith("…"), lines[0])
        self.assertTrue(lines[1].startswith("  -> "))


class ColourTest(Case):
    def on_a_terminal(self, *args, **kw):
        """The CLI's output with its stdout a real terminal (a pty)."""
        master, slave = pty.openpty()
        try:
            proc = subprocess.Popen([sys.executable, self.box.script] + list(args), stdin=subprocess.DEVNULL, stdout=slave,
                                    stderr=subprocess.PIPE, cwd=self.box.project, env=self.box.env(**kw))
            os.close(slave)
            slave = None
            chunks = []
            while True:
                ready, _, _ = select.select([master], [], [], 30)
                if not ready:
                    break
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
            proc.wait(timeout=30)
            proc.stderr.close()
        finally:
            if slave is not None:
                os.close(slave)
            os.close(master)
        return b"".join(chunks).decode("utf-8").replace("\r\n", "\n")

    def setUp(self):
        Case.setUp(self)
        self.box.add("used")
        self.box.add("idle")
        self.box.log({"type": "reuse", "lessons": ["used"]})
        self.box.log({"type": "guard", "lesson": "used"})

    def test_a_terminal_gets_colour(self):
        status = self.on_a_terminal("status", TERM="xterm-256color")
        self.assertIn(ESC + "33mWARN" + ESC + "0m", status)
        self.assertIn(ESC + "32mPASS" + ESC + "0m", status)
        self.assertIn(ESC + "1mHealth" + ESC + "0m", status)
        # Without the escapes it is the piped report, line for line.
        plain = re.sub(r"\x1b\[[0-9;]*m", "", status)
        piped = self.box.run("status", COLUMNS=80).stdout
        self.assertEqual([line.rstrip() for line in plain.splitlines()], [line.rstrip() for line in piped.splitlines()])
        for args in (["list"], ["events"], ["find", "used"]):
            self.assertIn(ESC, self.on_a_terminal(*args, TERM="xterm-256color"), args)

    def test_no_colour_when_piped_when_NO_COLOR_is_set_on_a_dumb_terminal_or_in_json(self):
        for args in (["status"], ["list"], ["events"], ["find", "used"]):
            self.assertNotIn(ESC, self.box.run(*args).stdout, args)
            self.assertNotIn(ESC, self.on_a_terminal(*args, TERM="xterm-256color", NO_COLOR="1"), args)
            self.assertNotIn(ESC, self.on_a_terminal(*args, TERM="dumb"), args)
            out = self.on_a_terminal(*(args + ["--json"]), TERM="xterm-256color")
            self.assertNotIn(ESC, out, args)
            json.loads(out)


if __name__ == "__main__":
    unittest.main()
