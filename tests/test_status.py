#!/usr/bin/env python3
"""status: the health checks, the store counts, the per-lesson table, recent, open."""

import json
import os
import re
import unittest

from test_support import NOW, Case


class StatusTest(Case):
    def status(self, **kw):
        proc = self.box.run("status", "--json", **kw)
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0 if data["ok"] else 1)
        return data

    def health(self, data, name):
        rows = [row for row in data["health"] if row["check"] == name]
        self.assertEqual(len(rows), 1, name)
        return rows[0]

    def test_sections_come_in_the_documented_order(self):
        self.box.add("a-lesson")
        proc = self.box.run("status")
        self.assertExit(proc, 0)
        heads = [line for line in proc.stdout.splitlines() if re.match(r"^[A-Z][a-z]+$", line)]
        self.assertEqual(heads, ["Health", "Levels", "Lessons", "Recent", "Open"])
        # The totals have a two-word heading, between Health and Levels.
        self.assertLess(proc.stdout.index("\nCompound interest\n"), proc.stdout.index("\nLevels\n"))

    def test_health_checks_come_in_the_documented_order(self):
        data = self.status()
        self.assertEqual([row["check"] for row in data["health"]],
                         ["python", "claude code", "mod", "mod last fired", "cli", "prompt log", "last event",
                          "duplicates", "lessons parse", "errors"])
        self.assertTrue(all(row["status"] in ("PASS", "WARN", "FAIL") for row in data["health"]))

    def test_json_carries_the_same_sections(self):
        data = self.status()
        for key in ("ok", "health", "store", "lessons", "recent", "open"):
            self.assertIn(key, data)
        self.assertEqual(sorted(data["open"]), ["candidates", "errors", "ineffective", "skips", "unsettled"])

    def test_a_fresh_sandbox_warns_and_does_not_fail(self):
        data = self.status()
        self.assertTrue(data["ok"])
        self.assertEqual(self.health(data, "python")["status"], "PASS")
        self.assertEqual(self.health(data, "mod")["status"], "WARN")
        self.assertEqual(self.health(data, "mod last fired")["status"], "WARN")
        self.assertEqual(self.health(data, "cli")["status"], "WARN")
        self.assertEqual(self.health(data, "prompt log")["status"], "WARN")
        self.assertEqual(self.health(data, "last event")["status"], "WARN")
        self.assertEqual(self.health(data, "duplicates")["status"], "PASS")
        self.assertEqual(self.health(data, "lessons parse")["status"], "PASS")
        self.assertEqual(self.health(data, "errors")["status"], "PASS")

    def test_python_version_is_reported(self):
        import sys
        self.assertEqual(self.health(self.status(), "python")["detail"], "%d.%d.%d" % sys.version_info[:3])

    def claude(self, text, body=None):
        """A real executable named `claude` that answers `--version` with `text`; the
        directory it is in, for PATH."""
        tools = os.path.join(self.box.root, "tools")
        os.makedirs(tools, exist_ok=True)
        path = os.path.join(tools, "claude")
        with open(path, "w") as handle:
            handle.write(body or "#!/bin/sh\necho '%s'\n" % text)
        os.chmod(path, 0o755)
        return tools + ":/usr/bin:/bin"

    def test_without_claude_on_path_the_claude_code_row_warns(self):
        row = self.health(self.status(), "claude code")
        self.assertEqual(row["status"], "WARN")
        self.assertIn("not on PATH", row["detail"])
        self.assertIn("2.1.288", row["detail"])

    def test_a_claude_code_at_or_above_the_minimum_passes(self):
        for version in ("2.1.288", "2.1.289", "2.2.0", "3.0.1", "2.10.0"):
            row = self.health(self.status(PATH=self.claude("%s (Claude Code)" % version)), "claude code")
            self.assertEqual((row["status"], row["detail"]), ("PASS", version))

    def test_a_claude_code_below_the_minimum_fails_and_says_what_to_do(self):
        for version in ("2.1.287", "2.0.999", "1.9.300"):
            data = self.status(PATH=self.claude("%s (Claude Code)" % version))
            row = self.health(data, "claude code")
            self.assertEqual(row["status"], "FAIL", version)
            self.assertIn(version, row["detail"])
            self.assertIn("2.1.288", row["detail"])
            self.assertIn("claude update", row["detail"])
            self.assertFalse(data["ok"])

    def test_a_claude_that_gives_no_version_warns(self):
        for body in ("#!/bin/sh\necho 'no numbers here'\n", "#!/bin/sh\nexit 3\n"):
            row = self.health(self.status(PATH=self.claude("", body)), "claude code")
            self.assertEqual(row["status"], "WARN", body)
            self.assertIn("2.1.288", row["detail"])

    def test_the_real_claude_code_is_read(self):
        import shutil
        import subprocess
        real = shutil.which("claude")
        if not real:
            self.skipTest("no `claude` on PATH here")
        said = subprocess.run([real, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, timeout=30).stdout
        found = re.search(r"(\d+)\.(\d+)\.(\d+)", said)
        self.assertIsNotNone(found, said)
        row = self.health(self.status(PATH=os.path.dirname(real) + ":/usr/bin:/bin"), "claude code")
        want = "PASS" if tuple(int(part) for part in found.groups()) >= (2, 1, 288) else "FAIL"
        self.assertEqual(row["status"], want, row)
        self.assertIn(found.group(0), row["detail"])

    def test_after_install_mod_and_cli_pass(self):
        self.box.plugin()
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin), 0)
        data = self.status(PATH=self.box.bin + ":/usr/bin:/bin")
        self.assertEqual(self.health(data, "mod")["status"], "PASS")
        self.assertEqual(self.health(data, "cli")["status"], "PASS")

    def test_malformed_settings_fail_the_mod_check_and_the_exit_status(self):
        with open(self.box.settings, "w") as handle:
            handle.write("{not json")
        data = self.status()
        self.assertFalse(data["ok"])
        self.assertEqual(self.health(data, "mod")["status"], "FAIL")
        self.assertExit(self.box.run("status"), 1)

    def test_last_event_age(self):
        self.box.log({"type": "nudge", "calls": 9}, COMPOUND_NOW=NOW - 7200)
        row = self.health(self.status(), "last event")
        self.assertEqual((row["status"], row["detail"]), ("PASS", "2h ago (1 events)"))

    def test_a_log_line_that_does_not_parse_is_counted_as_a_warning(self):
        """Readers skip such a line, so the log still works: a WARN. What cannot work, a
        log that cannot be written, is the FAIL."""
        self.box.log({"type": "nudge", "calls": 9})
        with open(self.box.events, "a") as handle:
            handle.write("{truncated\n")
        data = self.status()
        row = self.health(data, "last event")
        self.assertEqual(row["status"], "WARN")
        self.assertIn("1 line(s)", row["detail"])
        self.assertIn(self.box.events, row["detail"])
        self.assertTrue(data["ok"])

    def test_a_lesson_name_at_two_levels_fails(self):
        self.box.add("twice")
        self.box.write_lesson(self.box.lesson_dir("twice", "user"), "twice")
        data = self.status()
        row = self.health(data, "duplicates")
        self.assertEqual(row["status"], "FAIL")
        self.assertIn(self.box.lesson_dir("twice"), row["detail"])
        self.assertIn(self.box.lesson_dir("twice", "user"), row["detail"])
        self.assertFalse(data["ok"])

    def test_two_skills_of_one_name_only_warn(self):
        self.box.write_lesson(self.box.skill_dir("same", "project"), "same")
        self.box.write_lesson(self.box.skill_dir("same", "user"), "same")
        data = self.status()
        self.assertEqual(self.health(data, "duplicates")["status"], "WARN")
        self.assertTrue(data["ok"])

    def test_unparseable_lessons_fail_and_are_named(self):
        lessons = os.path.join(self.box.project, ".claude", "compound", "lessons")
        cases = {
            "no-frontmatter": "just text\n",
            "not-closed": "---\nname: not-closed\ndescription: Use when.\nbody\n",
            "no-description": "---\nname: no-description\n---\nbody\n",
            "wrong-name": "---\nname: another-name\ndescription: Use when.\n---\nbody\n",
            "bad-match": "---\nname: bad-match\ndescription: Use when.\nmatch: [unquoted]\n---\nbody\n",
            "bad-regex": '---\nname: bad-regex\ndescription: Use when.\nmatch: ["("]\n---\nbody\n',
            "empty-body": "---\nname: empty-body\ndescription: Use when.\n---\n\n",
        }
        for name, text in cases.items():
            os.makedirs(os.path.join(lessons, name))
            with open(os.path.join(lessons, name, "SKILL.md"), "w") as handle:
                handle.write(text)
        os.makedirs(os.path.join(lessons, "no-skill-md"))
        data = self.status()
        row = self.health(data, "lessons parse")
        self.assertEqual(row["status"], "FAIL")
        for name in list(cases) + ["no-skill-md"]:
            self.assertIn(os.path.join(lessons, name), row["detail"])
        self.assertFalse(data["ok"])
        listed = sorted(item["name"] for item in self.box.json("list", "--json"))
        self.assertEqual(listed, ["bad-match", "bad-regex"],
                         "a lesson whose only fault is its match is still listed; the others are not")

    def test_errors_in_the_last_seven_days_warn_and_are_shown(self):
        self.box.log({"type": "error", "where": "judge", "message": "old one"}, COMPOUND_NOW=NOW - 8 * 86400)
        self.box.log({"type": "error", "where": "judge", "message": "answer did not parse"},
                     COMPOUND_NOW=NOW - 86400)
        data = self.status()
        row = self.health(data, "errors")
        self.assertEqual((row["status"], row["detail"]), ("WARN", "1 in the last 7 days"))
        self.assertEqual([(err["where"], err["message"]) for err in data["open"]["errors"]],
                         [("judge", "answer did not parse")])
        self.assertTrue(data["ok"], "an error is a warning, not a failed health check")
        proc = self.box.run("status")
        self.assertIn("judge: answer did not parse", proc.stdout)
        self.assertNotIn("old one", proc.stdout.split("Open")[1])

    def test_store_counts_per_level(self):
        self.box.add("p-one")
        self.box.add("p-guard", "Use when.", "Body.\n", "--match", "danger")
        self.box.add("u-one", "Use when.", "Body.\n", "--level", "user")
        self.box.write_lesson(self.box.skill_dir("u-skill", "user"), "u-skill")
        self.box.write_lesson(self.box.lesson_dir("g-one", "general"), "g-one", extra='match: ["rm -rf /"]\n')
        self.assertEqual(self.status()["store"], {
            "project": {"lessons": 2, "skills": 0, "guards": 1},
            "user": {"lessons": 1, "skills": 1, "guards": 0},
            "general": {"lessons": 1, "skills": 0, "guards": 1}})

    def test_lesson_table_counts_and_flags(self):
        self.box.add("used")
        self.box.add("unused")
        self.box.add("flaky")
        self.box.write_lesson(self.box.skill_dir("quiet-skill", "user"), "quiet-skill")
        self.box.write_lesson(self.box.skill_dir("used-skill", "user"), "used-skill")
        self.box.log({"type": "reuse", "lessons": ["used", "used-skill"]}, COMPOUND_NOW=NOW + 10)
        self.box.log({"type": "guard", "lesson": "used"}, COMPOUND_NOW=NOW + 20)
        self.box.log({"type": "recall", "lesson": "flaky"}, COMPOUND_NOW=NOW + 30)
        self.box.log({"type": "recall", "lesson": "flaky"}, COMPOUND_NOW=NOW + 40)
        data = self.status(COMPOUND_NOW=NOW + 50)
        table = {row["name"]: (row["level"], row["reuse"], row["guard_hits"], row["recall"], row["flag"])
                 for row in data["lessons"]}
        self.assertEqual(table, {
            "used": ("project", 1, 1, 0, ""),
            "unused": ("project", 0, 0, 0, "never used"),
            "flaky": ("project", 0, 0, 2, "ineffective"),
            "used-skill": ("user", 1, 0, 0, ""),
        }, "a skill nothing has touched is left out of the table")
        self.assertEqual([row["name"] for row in data["open"]["ineffective"]], ["flaky"])
        proc = self.box.run("status", COMPOUND_NOW=NOW + 50)
        self.assertExit(proc, 0)
        self.assertRegex(proc.stdout, r"flaky\s+project\s+lesson\s+0\s+0\s+2\s+ineffective")
        # The lessons never used are one line with their count; `compound list` has the rows.
        self.assertIn("\n  1 lesson never used (`compound list` shows it)\n", proc.stdout)
        self.assertNotRegex(proc.stdout.split("\nLessons\n")[1].split("\n\n")[0], r"\bunused\b")
        self.assertRegex(proc.stdout.split("Open")[1], r"ineffective\s+flaky")

    def test_recent_is_the_last_ten_events(self):
        for index in range(13):
            self.box.log({"type": "nudge", "calls": index}, COMPOUND_NOW=NOW + index)
        data = self.status(COMPOUND_NOW=NOW + 20)
        self.assertEqual([event["calls"] for event in data["recent"]], list(range(3, 13)))
        proc = self.box.run("status", COMPOUND_NOW=NOW + 20)
        recent = proc.stdout.split("Recent\n")[1].split("\nOpen")[0].strip().splitlines()
        self.assertEqual(len(recent), 10)

    def test_recent_leaves_the_judges_verdicts_out(self):
        self.box.log({"type": "guard", "lesson": "a-guard"}, COMPOUND_NOW=NOW + 1)
        for index in range(12):
            self.box.log({"type": "judge", "moment": "fix", "verdict": "none", "ms": 700 + index}, COMPOUND_NOW=NOW + 2 + index)
        data = self.status(COMPOUND_NOW=NOW + 20)
        self.assertEqual([event["type"] for event in data["recent"]], ["guard"])
        fired = [row for row in data["health"] if row["check"] == "mod last fired"][0]
        self.assertIn("(judge)", fired["detail"], "a verdict is still the mod firing")

    def test_skips_are_listed_with_their_reasons(self):
        self.assertExit(self.box.run("skip", "--why", "a typo, nothing to keep"), 0)
        data = self.status()
        self.assertEqual([row["why"] for row in data["open"]["skips"]], ["a typo, nothing to keep"])
        self.assertIn("a typo, nothing to keep", self.box.run("status").stdout.split("Open")[1])

    def test_nothing_open_is_said(self):
        self.assertIn("nothing open", self.box.run("status").stdout)

    def test_each_open_row_carries_the_command_the_report_prints_for_it(self):
        """The pane shows what settles an open row: the JSON carries the very text the
        report prints, so the two cannot differ."""
        self.box.add("flaky")
        for offset in (10, 20):
            self.box.log({"type": "recall", "lesson": "flaky"}, COMPOUND_NOW=NOW + offset)
        self.box.log({"type": "capture", "call": "c1", "failed": "./build.sh", "fixed": "./build.sh --profile dev"},
                     COMPOUND_NOW=NOW + 30)
        data = self.status(COMPOUND_NOW=NOW + 40)
        owed = data["open"]["unsettled"][0]
        self.assertEqual(owed["command"], "/compound:learn settle %s" % owed["id"])
        self.assertEqual(owed["decline"], 'compound skip --settles %s --why "<reason>"' % owed["id"])
        weak = data["open"]["ineffective"][0]
        self.assertEqual(weak["command"], "compound add --update --name flaky --match RE")
        opened = self.box.run("status", COMPOUND_NOW=NOW + 40).stdout.split("Open")[1]
        for command in (owed["command"], owed["decline"], weak["command"]):
            self.assertIn(command, opened)

    def test_show_json_carries_the_body_and_when_the_lesson_last_fired(self):
        """What the pane's lesson view draws: the body without its frontmatter, and the
        newest reuse, guard or recall that names the lesson."""
        self.box.add("flaky", "Use when the build fails.", "Pass --profile dev.\n\nIt has no default.\n",
                     "--match", "build\\.sh$")
        shown = self.box.json("show", "flaky", "--json", COMPOUND_NOW=NOW + 5)
        self.assertEqual(shown["body"], "Pass --profile dev.\n\nIt has no default.")
        self.assertNotIn("---", shown["body"])
        self.assertIn("---", shown["text"])
        self.assertIsNone(shown["last"], "recording a lesson is not the lesson firing")
        self.box.log({"type": "guard", "lesson": "flaky"}, COMPOUND_NOW=NOW + 10)
        self.box.log({"type": "reuse", "lessons": ["other", "flaky"]}, COMPOUND_NOW=NOW + 20)
        self.box.log({"type": "recall", "lesson": "other"}, COMPOUND_NOW=NOW + 30)
        last = self.box.json("show", "flaky", "--json", COMPOUND_NOW=NOW + 40)["last"]
        self.assertEqual(last["type"], "reuse")
        self.assertEqual(last["ts"], [e for e in self.box.read_events() if e["type"] == "reuse"][0]["ts"])


if __name__ == "__main__":
    unittest.main()
