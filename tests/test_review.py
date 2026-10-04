#!/usr/bin/env python3
"""Defects an independent review reproduced, one class per item, each driven through the
real CLI against real files. The numbering follows the review."""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import unittest

from test_support import NOW, Case, git_ok

PLUGIN_ENV = "CLAUDE_CODE_PLUGIN_DIRS"


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def frontmatter_lines(text):
    lines = text.split("\n")
    assert lines[0] == "---", text
    end = lines.index("---", 1)
    return lines[1:end]


PLAIN_START = "\"'[{>|#&*!%@`"


def strict_problem(line):
    """Why a frontmatter line is not strictly valid `key: value`, or None. A value is a
    JSON string, a JSON array, or a plain scalar that holds neither `: ` nor ` #`, does
    not start with a YAML indicator and does not end in a colon."""
    found = re.match(r"^([A-Za-z0-9_-]+): (.+)$", line)
    if not found:
        return "not `key: value`"
    value = found.group(2)
    if value[0] == '"':
        try:
            return None if isinstance(json.loads(value), str) else "not a JSON string"
        except ValueError as exc:
            return "starts with a quote and is not a JSON string: %s" % exc
    if value[0] == "[":
        try:
            return None if isinstance(json.loads(value), list) else "not a JSON array"
        except ValueError as exc:
            return "starts with [ and is not a JSON array: %s" % exc
    if value[0] in PLAIN_START:
        return "plain scalar starts with %r" % value[0]
    if ": " in value or " #" in value or value.endswith(":") or value != value.strip():
        return "plain scalar holds a YAML indicator"
    if value.startswith("- ") or value.startswith("? "):
        return "plain scalar starts like a sequence or a key"
    if value in ("=", "<<", "~", "---", "...") or value.lower() in ("true", "false", "null", "yes", "no", "on", "off"):
        return "plain scalar is a YAML keyword, not a string"
    if re.match(r"^[-+]?\.?[0-9][0-9_.,:eExXoOa-fA-F+-]*$", value) and not re.match(r"^\d{4}-\d\d-\d\d$", value):
        return "plain scalar is a number to a YAML reader"
    return None


def no_traceback(case, proc):
    case.assertNotIn("Traceback", proc.stderr, proc.stderr)
    case.assertNotIn("Traceback", proc.stdout)


def strict_json(text):
    def refuse(name):
        raise ValueError("non-standard JSON constant %s" % name)
    return json.loads(text, parse_constant=refuse)


TRICKY = [
    "Use when: x breaks",
    '"quoted" at the start',
    "[bracket at the start",
    "# hash at the start",
    "ends with a hash #note",
    ">",
    "|",
    '""',
    "- starts like a list",
    "{brace",
    "ends with a colon:",
    "'single' at the start",
    "it's an apostrophe inside",
    "a backslash \\ and a \"quote\" inside",
    "unicode é中  text",
    "*star", "&amp", "!bang", "%percent", "@at", "`tick",
    "=", "<<", "~", "true", "No", "12", "1e3", "0x1f", "-5", ".5", "12:30", "2026-01-01", "...",
]


class FrontmatterIsValidYamlTest(Case):
    """1 and 7: what `add` writes is strictly valid, and reads back as what was given."""

    def test_every_tricky_description_is_written_validly_and_reads_back(self):
        for index, text in enumerate(TRICKY):
            name = "tricky-%02d" % index
            self.box.add(name, text, "Body.\n")
            path = os.path.join(self.box.lesson_dir(name), "SKILL.md")
            for line in frontmatter_lines(read(path)):
                if not line.startswith(("created: ", "updated: ")):
                    self.assertIsNone(strict_problem(line), "%r wrote the line %r" % (text, line))
        rows = {row["name"]: row["description"] for row in self.box.json("list", "--json")}
        for index, text in enumerate(TRICKY):
            self.assertEqual(rows.get("tricky-%02d" % index), " ".join(text.split()), text)
        status = self.box.json("status", "--json")
        parse = [row for row in status["health"] if row["check"] == "lessons parse"][0]
        self.assertEqual(parse["status"], "PASS", parse)

    def test_a_tricky_origin_is_written_validly(self):
        self.box.add("with-origin", "Use when.", "Body.\n", "--origin", "project: x")
        text = read(os.path.join(self.box.lesson_dir("with-origin"), "SKILL.md"))
        for line in frontmatter_lines(text):
            self.assertIsNone(strict_problem(line), line)
        self.assertIn('origin: "project: x"\n', text)

    def test_a_tricky_description_survives_update_show_and_rm(self):
        self.box.add("angle", ">", "Body.\n")
        self.assertExit(self.box.run("add", "--name", "angle", "--update", "--when", "|", stdin=""), 0)
        text = read(os.path.join(self.box.lesson_dir("angle"), "SKILL.md"))
        for line in frontmatter_lines(text):
            self.assertIsNone(strict_problem(line), line)
        self.assertEqual(self.box.json("show", "angle", "--json")["description"], "|")
        self.assertExit(self.box.run("rm", "angle"), 0)
        self.assertEqual(self.box.json("list", "--json"), [])

    def test_a_plain_description_is_still_written_plain(self):
        self.box.add("plain", "Use when plain, with a comma and a (parenthesis).", "Body.\n")
        self.assertIn("description: Use when plain, with a comma and a (parenthesis).\n",
                      read(os.path.join(self.box.lesson_dir("plain"), "SKILL.md")))

    def test_quoted_and_unquoted_forms_are_both_read(self):
        self.box.write_lesson(self.box.lesson_dir("dq"), "dq", description='"Use when: \\"double\\" quoted."')
        self.box.write_lesson(self.box.lesson_dir("sq"), "sq", description="'Use when it''s single quoted.'")
        self.box.write_lesson(self.box.lesson_dir("pl"), "pl", description="Use when plain.")
        rows = {row["name"]: row["description"] for row in self.box.json("list", "--json")}
        self.assertEqual(rows, {"dq": 'Use when: "double" quoted.', "sq": "Use when it's single quoted.",
                                "pl": "Use when plain."})

    def test_a_whitespace_description_is_refused(self):
        for text in ("", "   ", "\n\t"):
            proc = self.box.run("add", "--name", "blank", "--when", text, stdin="Body.\n")
            self.assertExit(proc, 2)
        self.assertFalse(os.path.exists(self.box.lesson_dir("blank")))


HAND = (
    "---\n"
    "# written by hand\n"
    "name: hand\n"
    "description: >\n"
    "  Use when the description\n"
    "  is folded.\n"
    "\n"
    "allowed-tools:\n"
    "  - Bash\n"
    "  - Read\n"
    "metadata:\n"
    "  author: someone   # trailing comment\n"
    "  nested:\n"
    "    deep: true\n"
    "license: \"MIT\"\n"
    "---\n"
    "\n"
    "# Hand-written body\n"
    "\n"
    "Step one.\n"
    "\n"
)


class UpdatePreservesFrontmatterTest(Case):
    """2: --update edits only the keys it owns."""

    def hand(self, text=HAND, name="hand"):
        path = os.path.join(self.box.skill_dir(name, "user"), "SKILL.md")
        write(path, text)
        return path

    def test_a_folded_description_is_listed(self):
        self.hand()
        rows = self.box.json("list", "--json")
        self.assertEqual(rows[0]["description"], "Use when the description is folded.")

    def test_a_literal_description_is_listed(self):
        self.hand(HAND.replace("description: >\n", "description: |-\n"))
        self.assertEqual(self.box.json("list", "--json")[0]["description"], "Use when the description is folded.")

    def test_adding_a_match_leaves_every_other_byte(self):
        path = self.hand()
        proc = self.box.run("add", "--name", "hand", "--update", "--match", "danger", stdin="")
        self.assertExit(proc, 0)
        self.assertEqual(read(path), HAND.replace(
            'license: "MIT"\n---\n', 'license: "MIT"\nmatch: ["danger"]\nupdated: 2026-09-21\n---\n'))

    def test_replacing_the_description_replaces_its_whole_block_and_nothing_else(self):
        path = self.hand()
        proc = self.box.run("add", "--name", "hand", "--update", "--when", "Use when: new", stdin="")
        self.assertExit(proc, 0)
        expected = HAND.replace(
            "description: >\n  Use when the description\n  is folded.\n", 'description: "Use when: new"\n'
        ).replace('license: "MIT"\n---\n', 'license: "MIT"\nupdated: 2026-09-21\n---\n')
        self.assertEqual(read(path), expected)
        self.assertEqual(self.box.json("list", "--json")[0]["description"], "Use when: new")

    def test_a_new_body_replaces_the_body_only(self):
        path = self.hand()
        self.assertExit(self.box.run("add", "--name", "hand", "--update", stdin="New body.\n"), 0)
        text = read(path)
        head = HAND.split("\n---\n")[0]
        self.assertTrue(text.startswith(head + "\nupdated: 2026-09-21\n---\n"), text)
        self.assertTrue(text.endswith("---\nNew body.\n"), text)

    def test_no_match_removes_only_the_match_block(self):
        path = self.hand(HAND.replace('license: "MIT"\n', 'match: ["danger"]\nlicense: "MIT"\n'))
        self.assertExit(self.box.run("add", "--name", "hand", "--update", "--no-match", stdin=""), 0)
        self.assertEqual(read(path), HAND.replace('license: "MIT"\n---\n', 'license: "MIT"\nupdated: 2026-09-21\n---\n'))

    def test_a_list_at_column_zero_is_kept(self):
        text = HAND.replace("  - Bash\n  - Read\n", "- Bash\n- Read\n")
        path = self.hand(text)
        self.assertExit(self.box.run("add", "--name", "hand", "--update", "--match", "danger", stdin=""), 0)
        self.assertEqual(read(path), text.replace(
            'license: "MIT"\n---\n', 'license: "MIT"\nmatch: ["danger"]\nupdated: 2026-09-21\n---\n'))

    def test_frontmatter_that_cannot_be_edited_safely_is_refused(self):
        cases = {
            "a line that is not a key": HAND.replace("license:", "this line is not yaml\nlicense:"),
            "a key given twice": HAND.replace('license: "MIT"\n', 'license: "MIT"\ndescription: again\n'),
        }
        for label, text in cases.items():
            path = self.hand(text, name="hand")
            proc = self.box.run("add", "--name", "hand", "--update", "--when", "Use when new.", stdin="")
            self.assertExit(proc, 2)
            self.assertIn("frontmatter", proc.stderr, label)
            self.assertEqual(read(path), text, label)
            shutil.rmtree(os.path.dirname(path))

    def test_crlf_line_endings_are_kept(self):
        text = HAND.replace("\n", "\r\n")
        path = self.hand(text)
        self.assertExit(self.box.run("add", "--name", "hand", "--update", "--match", "danger", stdin=""), 0)
        with open(path, "rb") as handle:
            data = handle.read().decode("utf-8")
        self.assertEqual(data, text.replace(
            'license: "MIT"\r\n---\r\n', 'license: "MIT"\r\nmatch: ["danger"]\r\nupdated: 2026-09-21\r\n---\r\n'))


class CheckNeverHangsTest(Case):
    """3: a wall-clock budget, a cap on the tested text, and no match-everything guard."""

    def check(self, command, **kw):
        started = time.time()
        proc = self.box.run("check", stdin=json.dumps({"tool": "Bash", "input": {"command": command}}), **kw)
        return proc, time.time() - started

    def slow_store(self):
        self.box.add("a-fast", "Use when.", "Fast body.\n", "--match", "aaa")
        self.box.add("slow-guard", "Use when.", "Slow body.\n", "--match", "(a+)+$")
        self.box.add("z-later", "Use when.", "Later body.\n", "--match", "aab")

    def test_a_backtracking_guard_is_abandoned_at_the_budget(self):
        self.slow_store()
        proc, took = self.check("a" * 30 + "b")
        self.assertExit(proc, 0)
        no_traceback(self, proc)
        self.assertLess(took, 5.0, "check took %.1fs" % took)
        data = json.loads(proc.stdout)
        self.assertEqual([hit["name"] for hit in data["hits"]], ["a-fast"], "the hits found before the expiry")
        self.assertEqual(data["timed_out"], ["slow-guard"])
        self.assertEqual(data["unchecked"], ["z-later"])

    def test_the_budget_is_configurable(self):
        self.slow_store()
        slow = []
        for budget, ceiling in (("100", 2.0), ("1500", 4.0)):
            proc, took = self.check("a" * 30 + "b", COMPOUND_CHECK_BUDGET_MS=budget)
            self.assertExit(proc, 0)
            self.assertLess(took, ceiling)
            slow.append(took)
        self.assertGreater(slow[1], 1.4, "a 1500 ms budget was not waited for")
        proc, took = self.check("a" * 30 + "b", COMPOUND_CHECK_BUDGET_MS="banana")
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout)["timed_out"], ["slow-guard"])

    def test_a_timeout_is_logged_and_status_flags_it(self):
        self.slow_store()
        self.check("a" * 30 + "b")
        errors = [event for event in self.box.read_events() if event["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["where"], "check")
        self.assertEqual(errors[0]["lesson"], "slow-guard")
        self.assertIn("slow-guard", errors[0]["message"])
        status = self.box.json("status", "--json")
        row = [check for check in status["health"] if check["check"] == "errors"][0]
        self.assertEqual(row["status"], "WARN")
        self.assertIn("slow-guard", self.box.run("status").stdout.split("Open")[1])

    def test_without_a_timeout_the_output_is_hits_alone(self):
        self.slow_store()
        proc, _took = self.check("aab")
        self.assertEqual(sorted(json.loads(proc.stdout)), ["hits"])
        self.assertFalse(any(event["type"] == "error" for event in self.box.read_events()))

    def test_the_tested_text_is_capped(self):
        self.box.add("needle-guard", "Use when.", "Body.\n", "--match", "needle")
        proc, _ = self.check("x" * 19000 + " needle")
        self.assertEqual(len(json.loads(proc.stdout)["hits"]), 1)
        proc, _ = self.check("x" * 50000 + " needle")
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout)["hits"], [])

    def test_a_match_that_fires_on_everything_is_refused_at_add(self):
        for pattern in (".", r"\w", "[a-z]", r"\S+", "^."):
            proc = self.box.run("add", "--name", "greedy", "--when", "Use when.", "--match", pattern, stdin="Body.\n")
            self.assertExit(proc, 2)
            self.assertIn("--match", proc.stderr)
        self.assertFalse(os.path.exists(self.box.lesson_dir("greedy")))
        self.box.add("narrow", "Use when.", "Body.\n", "--match", "ls")
        self.box.add("narrow-git", "Use when.", "Body.\n", "--match", r"git\s+status")

    def test_a_stored_match_everything_guard_never_fires(self):
        self.box.write_lesson(self.box.lesson_dir("dot"), "dot", extra='match: ["."]\n')
        proc, _ = self.check("ls -la")
        self.assertEqual(json.loads(proc.stdout), {"hits": []})


class NoTracebackTest(Case):
    """4: nothing exits with a traceback."""

    def run_bytes(self, args, data, **kw):
        return subprocess.run([sys.executable, self.box.script] + list(args), input=data, cwd=self.box.project,
                              env=self.box.env(**kw), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)

    def test_check_on_invalid_utf8(self):
        self.box.add("a-guard", "Use when.", "Body.\n", "--match", "danger")
        proc = self.run_bytes(["check"], b'{"tool":"Bash","input":{"command":"danger \xff\xfe"}}')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(b"Traceback", proc.stderr)
        self.assertEqual([hit["name"] for hit in json.loads(proc.stdout.decode("utf-8"))["hits"]], ["a-guard"])
        proc = self.run_bytes(["check"], b"\xff\xfe\x00")
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn(b"Traceback", proc.stderr)

    def test_check_on_deeply_nested_json_fails_open(self):
        self.box.add("a-guard", "Use when.", "Body.\n", "--match", "danger")
        for extra in ((), ("--json",)):
            proc = self.box.run("check", *extra, stdin='{"tool":"X","input":' + "[" * 5000 + "]" * 5000 + "}")
            self.assertExit(proc, 0)
            no_traceback(self, proc)
            data = json.loads(proc.stdout)
            self.assertEqual(data["hits"], [])
            if sys.version_info < (3, 12):
                self.assertIn("RecursionError", data["error"])

    def test_log_with_a_lone_surrogate(self):
        proc = self.box.run("log", "--json", stdin='{"type":"error","where":"x","message":"\\ud800"}')
        self.assertExit(proc, 0)
        no_traceback(self, proc)
        events = self.box.read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["message"], "\ud800")
        for args in (("status",), ("status", "--json"), ("events",), ("events", "--json")):
            proc = self.box.run(*args)
            self.assertIn(proc.returncode, (0,), proc.stderr)
            no_traceback(self, proc)

    def test_status_with_timestamps_that_are_not_the_documented_string(self):
        self.box.add("named")
        lines = [
            '{"ts": 1e999, "type": "recall", "lesson": "named"}',
            '{"ts": -1e999, "type": "recall", "lesson": "named"}',
            '{"ts": NaN, "type": "recall", "lesson": "named"}',
            '{"ts": [1], "type": "error", "where": "x", "message": "m"}',
            '{"ts": {"a": 1}, "type": "skip", "why": "w"}',
            '{"ts": null, "type": "error", "where": "x", "message": "m"}',
            '{"ts": true, "type": "nudge", "calls": 3}',
            '{"ts": "yesterday", "type": "nudge", "calls": 3}',
            '{"ts": "%s", "type": "recall", "lesson": "named"}' % ("9" * 400),
            '{"ts": 1e300, "type": "error", "where": "x", "message": "m"}',
            '{"ts": "9999-12-31T23:59:59+00:00", "type": "recall", "lesson": "named"}',
            '{"ts": "0001-01-01T00:00:00-23:59", "type": "recall", "lesson": "named"}',
            '{"type": "error", "where": {"a": NaN}, "message": [Infinity]}',
            '{"ts": 1e999, "type": 7, "session": {"x": 1}, "project": 9}',
        ]
        with open(self.box.events, "a") as handle:
            handle.write("\n".join(lines) + "\n")
        for args in (("status",), ("events",), ("list",), ("show", "named"), ("find", "named")):
            proc = self.box.run(*args)
            self.assertExit(proc, 0)
            no_traceback(self, proc)
        for args in (("status", "--json"), ("events", "--json"), ("list", "--json"), ("show", "named", "--json"),
                     ("events", "--json", "--since", "2026-01-01")):
            proc = self.box.run(*args)
            self.assertExit(proc, 0)
            no_traceback(self, proc)
            strict_json(proc.stdout)

    def test_a_pinned_clock_out_of_range_is_refused(self):
        for bad in ("99999999999999999999", "1e999", "999999999999", "-5", "nan"):
            for args, stdin in ((("skip", "--why", "x"), ""), (("status",), ""), (("list",), ""),
                                (("add", "--name", "n1", "--when", "w"), "Body.\n"), (("log",), '{"type":"nudge"}')):
                proc = self.box.run(*args, stdin=stdin, COMPOUND_NOW=bad)
                no_traceback(self, proc)
                self.assertIn(proc.returncode, (0, 2), "%r %r: %s" % (bad, args, proc.stderr))
            proc = self.box.run("skip", "--why", "x", COMPOUND_NOW=bad)
            self.assertExit(proc, 2)
            self.assertIn("COMPOUND_NOW", proc.stderr)
        self.assertEqual(self.box.read_events(), [])
        self.assertFalse(os.path.exists(self.box.lesson_dir("n1")))

    def test_an_unexpected_exception_is_one_line_and_exit_1(self):
        proc = self.box.run("log", stdin="[" * 100000 + "]" * 100000)
        no_traceback(self, proc)
        if sys.version_info < (3, 12):
            self.assertExit(proc, 1)
            self.assertRegex(proc.stderr, r"^compound: internal error: RecursionError: .*\n$")
        self.assertEqual(self.box.read_events(), [])


class TruncatedLogTest(Case):
    """5: a truncated last line costs that line and nothing after it."""

    def test_an_append_after_a_truncated_line_starts_on_its_own_line(self):
        self.box.log({"type": "nudge", "calls": 1})
        with open(self.box.events, "a") as handle:
            handle.write('{"ts":"2026-09-21T14:13:20Z","type":"nudge","cal')
        self.box.log({"type": "nudge", "calls": 2})
        self.assertExit(self.box.run("skip", "--why", "third"), 0)
        proc = self.box.run("events", "--json")
        self.assertExit(proc, 0)
        self.assertEqual([(event["type"], event.get("calls")) for event in json.loads(proc.stdout)],
                         [("nudge", 1), ("nudge", 2), ("skip", None)])
        self.assertIn("1 line(s)", proc.stderr)
        with open(self.box.events) as handle:
            self.assertEqual(len(handle.read().splitlines()), 4)

    def test_a_well_formed_log_gets_no_blank_lines(self):
        for index in range(3):
            self.box.log({"type": "nudge", "calls": index})
        text = read(self.box.events)
        self.assertEqual(text.count("\n"), 3)
        self.assertNotIn("\n\n", text)

    def test_status_reports_the_unparseable_count_as_a_warning(self):
        self.box.log({"type": "nudge", "calls": 1})
        with open(self.box.events, "a") as handle:
            handle.write("{truncated\nalso not json\n")
        data = json.loads(self.box.run("status", "--json").stdout)
        row = [check for check in data["health"] if check["check"] == "last event"][0]
        self.assertEqual(row["status"], "WARN")
        self.assertIn("2 line(s)", row["detail"])
        self.assertTrue(data["ok"])


LESSON = "---\nname: %s\ndescription: Use when shipped.\n---\n%s\n"


class UpdateRemovesOnlyIdenticalTreesTest(Case):
    """6 and the update half of 12."""

    def setUp(self):
        Case.setUp(self)
        self.upstream = os.path.join(self.box.root, "upstream")
        os.makedirs(os.path.join(self.upstream, "bin"))
        shutil.copy2(self.box.script, os.path.join(self.upstream, "bin", "compound"))
        git_ok("init", "-q", self.upstream)
        git_ok("checkout", "-q", "-b", "main", cwd=self.upstream)
        self.commit("first")
        self.clone = os.path.join(self.box.root, "clone")
        git_ok("clone", "-q", self.upstream, self.clone)
        self.script = os.path.join(self.clone, "bin", "compound")

    def commit(self, message):
        git_ok("add", "-A", cwd=self.upstream)
        git_ok("commit", "-q", "-m", message, cwd=self.upstream)

    def update(self, *args):
        return self.box.run("update", *args, script=self.script)

    def test_a_directory_holding_another_file_is_kept_and_reported(self):
        mine = self.box.lesson_dir("now-general", "user")
        write(os.path.join(mine, "SKILL.md"), LESSON % ("now-general", "Same."))
        write(os.path.join(mine, "my-notes.txt"), "mine alone\n")
        write(os.path.join(self.upstream, "lessons", "now-general", "SKILL.md"), LESSON % ("now-general", "Same."))
        self.commit("the lesson")
        proc = self.update("--json")
        self.assertExit(proc, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["removed"], [])
        self.assertEqual([row["name"] for row in data["differing"]], ["now-general"])
        self.assertEqual(read(os.path.join(mine, "my-notes.txt")), "mine alone\n")
        self.assertIn("kept user lesson now-general", self.update().stdout)

    def test_a_file_whose_bytes_differ_keeps_the_directory(self):
        mine = self.box.lesson_dir("now-general", "user")
        write(os.path.join(mine, "SKILL.md"), LESSON % ("now-general", "Same."))
        write(os.path.join(mine, "sub", "fix.sh"), "echo mine\n")
        write(os.path.join(self.upstream, "lessons", "now-general", "SKILL.md"), LESSON % ("now-general", "Same."))
        write(os.path.join(self.upstream, "lessons", "now-general", "sub", "fix.sh"), "echo theirs\n")
        self.commit("the lesson")
        self.assertExit(self.update(), 0)
        self.assertEqual(read(os.path.join(mine, "sub", "fix.sh")), "echo mine\n")

    def test_an_identical_tree_is_removed(self):
        mine = self.box.lesson_dir("now-general", "user")
        for base in (mine, os.path.join(self.upstream, "lessons", "now-general")):
            write(os.path.join(base, "SKILL.md"), LESSON % ("now-general", "Same."))
            write(os.path.join(base, "sub", "fix.sh"), "echo same\n")
        self.commit("the lesson")
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(mine))
        self.assertIn("removed user lesson now-general", proc.stdout)

    def test_nothing_under_the_claude_skills_directory_is_ever_removed(self):
        mine = self.box.skill_dir("now-shipped", "user")
        write(os.path.join(mine, "SKILL.md"), LESSON % ("now-shipped", "Steps."))
        for sub in ("skills", "lessons"):
            write(os.path.join(self.upstream, sub, "now-shipped", "SKILL.md"), LESSON % ("now-shipped", "Steps."))
        self.commit("ship it")
        proc = self.update("--json")
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout)["removed"], [])
        self.assertTrue(os.path.isfile(os.path.join(mine, "SKILL.md")))

    def test_a_dirty_checkout_is_said_before_the_pull(self):
        write(os.path.join(self.upstream, "tracked.txt"), "one\n")
        self.commit("a tracked file")
        self.assertExit(self.update(), 0)
        write(os.path.join(self.clone, "tracked.txt"), "edited locally\n")
        write(os.path.join(self.upstream, "other.txt"), "two\n")
        self.commit("upstream moves")
        proc = self.update()
        self.assertExit(proc, 0)
        lines = proc.stdout.splitlines()
        self.assertIn("uncommitted changes", lines[0])
        self.assertTrue(any(line.startswith("updated ") for line in lines[1:]))
        self.assertTrue(json.loads(self.update("--json").stdout)["dirty"])
        self.assertEqual(read(os.path.join(self.clone, "tracked.txt")), "edited locally\n")

    def test_a_clean_checkout_is_not_called_dirty(self):
        proc = self.update()
        self.assertNotIn("uncommitted", proc.stdout)
        self.assertFalse(json.loads(self.update("--json").stdout)["dirty"])

    def test_a_detached_checkout_is_one_clear_line(self):
        git_ok("checkout", "-q", "--detach", cwd=self.clone)
        proc = self.update()
        self.assertExit(proc, 1)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1, proc.stderr)
        self.assertIn("detached", proc.stderr)
        self.assertIn(self.clone, proc.stderr)
        self.assertEqual(proc.stdout, "")


class BrickedLessonTest(Case):
    """7: a lesson that does not parse is shown, with its path, and can be removed."""

    def brick(self):
        lessons = os.path.join(self.box.project, ".claude", "compound", "lessons")
        write(os.path.join(lessons, "bricked", "SKILL.md"), "---\nname: bricked\ndescription: >\ncreated: 2026-09-21\n---\nBody.\n")
        os.makedirs(os.path.join(lessons, "hollow"))
        return lessons

    def test_list_names_it_as_unparseable_with_its_path(self):
        lessons = self.brick()
        self.box.add("fine")
        proc = self.box.run("list")
        self.assertExit(proc, 0)
        for name in ("bricked", "hollow"):
            line = [row for row in proc.stdout.splitlines() if os.path.join(lessons, name) in row]
            self.assertEqual(len(line), 1, proc.stdout)
            self.assertIn("unparseable", line[0])
        proc = self.box.run("list", "--json")
        self.assertExit(proc, 0)
        self.assertEqual([row["name"] for row in json.loads(proc.stdout)], ["fine"])
        self.assertIn(os.path.join(lessons, "bricked"), proc.stderr)
        self.assertIn("unparseable", proc.stderr)

    def test_list_with_only_unparseable_lessons_still_shows_them(self):
        lessons = self.brick()
        proc = self.box.run("list")
        self.assertIn(os.path.join(lessons, "bricked"), proc.stdout)

    def test_status_carries_them_as_unparseable(self):
        lessons = self.brick()
        proc = self.box.run("status", "--json")
        data = json.loads(proc.stdout)
        self.assertEqual(sorted((row["name"], row["path"]) for row in data["unparseable"]),
                         [("bricked", os.path.join(lessons, "bricked")), ("hollow", os.path.join(lessons, "hollow"))])
        text = self.box.run("status").stdout
        self.assertRegex(text.split("Open")[1], r"unparseable\s+bricked")

    def test_rm_removes_it_by_directory_name(self):
        lessons = self.brick()
        for name in ("bricked", "hollow"):
            proc = self.box.run("rm", name, "--json")
            self.assertExit(proc, 0)
            self.assertEqual(json.loads(proc.stdout)["removed"], os.path.join(lessons, name))
            self.assertFalse(os.path.exists(os.path.join(lessons, name)))
        self.assertExit(self.box.run("rm", "bricked"), 2)

    def test_rm_never_removes_an_unparseable_general_lesson(self):
        directory = self.box.lesson_dir("shipped-broken", "general")
        write(os.path.join(directory, "SKILL.md"), "no frontmatter\n")
        self.assertExit(self.box.run("rm", "shipped-broken"), 2)
        self.assertTrue(os.path.isdir(directory))

    def test_a_bom_at_the_start_still_parses(self):
        directory = self.box.lesson_dir("with-bom")
        os.makedirs(directory)
        with open(os.path.join(directory, "SKILL.md"), "wb") as handle:
            handle.write(b"\xef\xbb\xbf---\nname: with-bom\ndescription: Use when a BOM leads.\nmatch: [\"danger\"]\n---\nBody.\n")
        rows = self.box.json("list", "--json")
        self.assertEqual([(row["name"], row["description"], row["match"]) for row in rows],
                         [("with-bom", "Use when a BOM leads.", ["danger"])])
        self.assertExit(self.box.run("add", "--name", "with-bom", "--update", "--when", "Use when updated.", stdin=""), 0)
        with open(os.path.join(directory, "SKILL.md"), "rb") as handle:
            data = handle.read()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf---\nname: with-bom\ndescription: Use when updated.\n"), data)


class InstallIsAllOrNothingTest(Case):
    """8 and the settings half of 12."""

    def refused(self, *args, **kw):
        before = self.box.snapshot()
        proc = self.box.run("install", *args, **kw)
        self.assertExit(proc, 1)
        no_traceback(self, proc)
        self.assertEqual(self.box.snapshot(), before, "a failed install left something behind")
        return proc

    def test_a_bin_dir_under_a_file_is_refused_before_anything_is_written(self):
        blocker = os.path.join(self.box.root, "a-file")
        write(blocker, "x\n")
        self.refused("--bin-dir", os.path.join(blocker, "sub"))
        write(self.box.settings, json.dumps({"model": "opus"}))
        proc = self.refused("--bin-dir", os.path.join(blocker, "sub"))
        self.assertIn(blocker, proc.stderr)

    def test_a_compound_home_that_is_a_file_is_refused_before_anything_is_written(self):
        blocker = os.path.join(self.box.root, "home-file")
        write(blocker, "x\n")
        proc = self.refused("--bin-dir", self.box.bin, COMPOUND_HOME=blocker)
        self.assertIn(blocker, proc.stderr)
        self.refused("--bin-dir", self.box.bin, COMPOUND_HOME=os.path.join(blocker, "deeper"))

    def test_a_failure_after_the_first_write_is_rolled_back(self):
        """A directory name longer than the file system allows passes every check that
        can be made beforehand and fails when the directory is made."""
        long_dir = os.path.join(self.box.root, "b" * 300)
        self.refused("--bin-dir", long_dir)
        write(self.box.settings, json.dumps({"model": "opus"}) + "\n")
        self.refused("--bin-dir", long_dir)

    def test_a_good_install_after_a_failed_one_is_fully_reversible(self):
        blocker = os.path.join(self.box.root, "a-file")
        write(blocker, "x\n")
        self.refused("--bin-dir", os.path.join(blocker, "sub"))
        self.refused("--bin-dir", os.path.join(self.box.root, "b" * 300))
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin), 0)
        self.assertTrue(json.loads(read(self.box.manifest))["plugin_dir_added"])
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertFalse(os.path.exists(self.box.settings))

    def test_uninstall_removes_our_element_whatever_the_record_says(self):
        write(self.box.settings, json.dumps({"model": "opus", "env": {PLUGIN_ENV: "/other/mod:" + self.box.pkg}}))
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin), 0)
        self.assertFalse(json.loads(read(self.box.manifest))["plugin_dir_added"])
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertEqual(json.loads(read(self.box.settings)), {"model": "opus", "env": {PLUGIN_ENV: "/other/mod"}})

    def test_a_read_only_settings_file_is_refused_and_not_replaced(self):
        write(self.box.settings, json.dumps({"model": "opus"}) + "\n")
        os.chmod(self.box.settings, 0o444)
        inode = os.stat(self.box.settings).st_ino
        proc = self.refused("--bin-dir", self.box.bin)
        self.assertIn("read-only", proc.stderr)
        self.assertEqual(os.stat(self.box.settings).st_ino, inode)
        self.assertEqual(os.stat(self.box.settings).st_mode & 0o777, 0o444)

    def test_uninstall_does_not_replace_a_settings_file_made_read_only(self):
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin), 0)
        os.chmod(self.box.settings, 0o444)
        before = read(self.box.settings)
        proc = self.box.run("uninstall")
        self.assertExit(proc, 1)
        self.assertIn("read-only", proc.stderr)
        self.assertEqual(read(self.box.settings), before)
        self.assertTrue(os.path.isfile(self.box.manifest))


class PromotePublishesNoOriginTest(Case):
    """9."""

    def setUp(self):
        Case.setUp(self)
        source = os.path.join(self.box.root, "fix.sh")
        write(source, "#!/bin/sh\necho fixed\n")
        self.box.add("zsh-equals-word", "Use when a zsh line has a bare equals word.", "Quote the word.\n",
                     "--level", "user", "--match", r"echo\s+=+", "--attach", source)
        self.dir = self.box.lesson_dir("zsh-equals-word", "user")
        write(os.path.join(self.dir, ".env"), "TOKEN=secret\n")
        write(os.path.join(self.dir, ".hidden", "inner.txt"), "hidden\n")
        os.symlink("/etc/hosts", os.path.join(self.dir, "hosts-link"))
        os.symlink(self.box.home, os.path.join(self.dir, "home-link"))

    def test_the_json_plan_carries_the_published_text_without_origin(self):
        local = read(os.path.join(self.dir, "SKILL.md"))
        self.assertIn("origin: project project, session sess-000\n", local)
        before = self.box.snapshot()
        plan = self.box.json("promote", "zsh-equals-word", "--to", "general", "--json")
        self.assertEqual(self.box.snapshot(), before, "the local lesson is unchanged")
        self.assertEqual(plan["skill_md"], local.replace("origin: project project, session sess-000\n", ""))
        self.assertNotIn("origin", plan["skill_md"])
        self.assertNotIn("sess-000", json.dumps(plan))
        self.assertEqual(plan["files"], ["lessons/zsh-equals-word/SKILL.md", "lessons/zsh-equals-word/fix.sh"])
        self.assertEqual(plan["excluded"], [".env", ".hidden", "home-link", "hosts-link"])

    def test_the_text_plan_shows_the_published_text_and_what_was_excluded(self):
        out = self.box.run("promote", "zsh-equals-word", "--to", "general").stdout
        self.assertNotIn("origin:", out)
        self.assertNotIn("sess-000", out)
        published = out.split("SKILL.md as it will be published:\n")[1]
        self.assertIn("    name: zsh-equals-word\n", published)
        self.assertIn("    Quote the word.\n", published)
        excluded = out.split("excluded")[1].split("PR title")[0]
        for name in (".env", ".hidden", "home-link", "hosts-link"):
            self.assertIn(name, excluded)
        self.assertNotIn(".env", out.split("files")[1].split("excluded")[0])

    def test_an_origin_spanning_lines_is_removed_whole(self):
        path = os.path.join(self.dir, "SKILL.md")
        text = read(path).replace("origin: project project, session sess-000\n",
                                  "origin: >\n  project secret-project,\n  session abc\n")
        write(path, text)
        plan = self.box.json("promote", "zsh-equals-word", "--to", "general", "--json")
        self.assertNotIn("secret-project", json.dumps(plan))
        self.assertNotIn("origin", plan["skill_md"])


class PurgeOnlyWhatIsOursTest(Case):
    """10 and 14."""

    def test_a_directory_of_someone_elses_files_is_refused(self):
        documents = os.path.join(self.box.home, "Documents")
        write(os.path.join(documents, "thesis.txt"), "years of work\n")
        write(os.path.join(documents, "events.jsonl"), "")
        before = self.box.snapshot()
        proc = self.box.run("uninstall", "--purge", COMPOUND_HOME=documents)
        self.assertExit(proc, 1)
        self.assertIn("--purge refused", proc.stderr)
        self.assertIn("thesis.txt", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)

    def test_a_directory_holding_only_our_names_is_purged_without_a_record(self):
        home = os.path.join(self.box.root, "elsewhere")
        self.box.add("a-lesson", "Use when.", "Body.\n", "--level", "user", COMPOUND_HOME=home)
        os.makedirs(os.path.join(home, "claims", "sess-1"))
        os.makedirs(os.path.join(home, "app"))
        os.makedirs(os.path.join(home, "history-surfer"))
        self.assertEqual(sorted(os.listdir(home)), ["app", "claims", "events.jsonl", "history-surfer", "lessons"])
        proc = self.box.run("uninstall", "--purge", COMPOUND_HOME=home)
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(home))

    def test_a_directory_with_our_install_record_is_purged(self):
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin), 0)
        write(os.path.join(self.box.chome, "something-else.txt"), "x\n")
        proc = self.box.run("uninstall", "--purge")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.box.chome))

    def test_an_install_json_that_is_not_ours_does_not_vouch_for_the_directory(self):
        documents = os.path.join(self.box.home, "Documents")
        write(os.path.join(documents, "install.json"), json.dumps({"name": "some other tool"}))
        write(os.path.join(documents, "thesis.txt"), "years of work\n")
        proc = self.box.run("uninstall", "--purge", COMPOUND_HOME=documents)
        self.assertExit(proc, 1)
        self.assertTrue(os.path.isfile(os.path.join(documents, "thesis.txt")))

    def test_status_ignores_the_claims_directory(self):
        self.box.add("a-lesson", "Use when.", "Body.\n", "--level", "user")
        before = self.box.json("status", "--json")
        write(os.path.join(self.box.chome, "claims", "sess-1", "prompt-1"), "")
        self.assertEqual(self.box.json("status", "--json"), before)
        self.assertEqual(len(self.box.json("list", "--json")), 1)


class EventLogCannotBeWrittenTest(Case):
    """11."""

    def test_add_succeeds_with_a_warning_when_the_log_is_a_directory(self):
        os.makedirs(self.box.events)
        proc = self.box.run("add", "--name", "kept", "--when", "Use when.", stdin="Body.\n")
        self.assertExit(proc, 0)
        self.assertIn("event log", proc.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("kept"), "SKILL.md")))
        status = self.box.run("status", "--json")
        self.assertExit(status, 1)
        row = [check for check in json.loads(status.stdout)["health"] if check["check"] == "last event"][0]
        self.assertEqual(row["status"], "FAIL")
        self.assertIn(self.box.events, row["detail"])
        self.assertNotIn("no events yet", row["detail"])

    def test_add_succeeds_with_a_warning_when_the_log_is_read_only(self):
        self.box.log({"type": "nudge", "calls": 1})
        os.chmod(self.box.events, 0o444)
        proc = self.box.run("add", "--name", "kept", "--when", "Use when.", stdin="Body.\n")
        self.assertExit(proc, 0)
        self.assertIn("event log", proc.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("kept"), "SKILL.md")))
        status = self.box.run("status", "--json")
        self.assertExit(status, 1)
        row = [check for check in json.loads(status.stdout)["health"] if check["check"] == "last event"][0]
        self.assertEqual(row["status"], "FAIL")

    def test_skill_rm_and_promote_succeed_with_a_warning_too(self):
        self.box.add("one")
        self.box.add("two")
        self.box.add("three")
        os.chmod(self.box.events, 0o444)
        for args in (("skill", "one"), ("rm", "two"), ("promote", "three", "--to", "user")):
            proc = self.box.run(*args)
            self.assertExit(proc, 0)
            self.assertIn("event log", proc.stderr)

    def test_skip_still_fails_because_the_event_is_the_whole_of_it(self):
        os.makedirs(self.box.events)
        proc = self.box.run("skip", "--why", "nothing to keep")
        self.assertExit(proc, 1)
        no_traceback(self, proc)


class MinorTest(Case):
    """12."""

    def test_created_and_updated_use_the_local_date(self):
        self.box.add("east", TZ="Pacific/Kiritimati")
        self.assertIn("created: 2026-09-22\n", read(os.path.join(self.box.lesson_dir("east"), "SKILL.md")))
        self.box.add("west", TZ="UTC")
        self.assertIn("created: 2026-09-21\n", read(os.path.join(self.box.lesson_dir("west"), "SKILL.md")))
        self.assertExit(self.box.run("add", "--name", "west", "--update", "--when", "Use when later.", stdin="",
                                     TZ="Pacific/Kiritimati"), 0)
        self.assertIn("updated: 2026-09-22\n", read(os.path.join(self.box.lesson_dir("west"), "SKILL.md")))

    def test_project_level_from_the_home_directory_is_refused(self):
        before = self.box.snapshot()
        for kw in ({"COMPOUND_PROJECT": self.box.home}, {"COMPOUND_PROJECT": None, "cwd": self.box.home}):
            proc = self.box.run("add", "--name", "stray", "--when", "Use when.", stdin="Body.\n", **kw)
            self.assertExit(proc, 2)
            self.assertIn("--level user", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)
        proc = self.box.run("add", "--name", "stray", "--when", "Use when.", "--level", "user", stdin="Body.\n",
                            COMPOUND_PROJECT=self.box.home)
        self.assertExit(proc, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("stray", "user"), "SKILL.md")))

    def test_project_level_from_the_parent_of_the_claude_dir_is_refused(self):
        parent = os.path.join(self.box.root, "dotfiles")
        claude = os.path.join(parent, ".claude")
        os.makedirs(claude)
        proc = self.box.run("add", "--name", "stray", "--when", "Use when.", stdin="Body.\n",
                            COMPOUND_PROJECT=parent, COMPOUND_CLAUDE_DIR=claude, COMPOUND_HOME=None)
        self.assertExit(proc, 2)
        self.assertIn("--level user", proc.stderr)
        self.assertEqual(os.listdir(claude), [])


class NewEventsTest(Case):
    """The design change, and 13."""

    def test_skill_logs_an_event(self):
        self.box.add("routed")
        self.assertExit(self.box.run("skill", "routed"), 0)
        self.assertEqual(self.box.read_events()[-1], {
            "ts": "2026-09-21T14:13:20Z", "type": "skill", "session": "sess-0001-aaaa",
            "project": self.box.project, "lesson": "routed", "level": "project",
            "path": self.box.skill_dir("routed")})

    def test_rm_logs_an_event(self):
        self.box.add("doomed")
        self.assertExit(self.box.run("rm", "doomed"), 0)
        self.assertEqual(self.box.read_events()[-1], {
            "ts": "2026-09-21T14:13:20Z", "type": "rm", "session": "sess-0001-aaaa",
            "project": self.box.project, "lesson": "doomed", "level": "project"})

    def test_a_refused_skill_or_rm_logs_nothing(self):
        self.assertExit(self.box.run("skill", "nothing"), 2)
        self.assertExit(self.box.run("rm", "nothing"), 2)
        self.assertEqual(self.box.read_events(), [])

    def test_status_recent_renders_skill_rm_and_refuse(self):
        self.box.add("routed")
        self.box.add("doomed")
        self.assertExit(self.box.run("skill", "routed"), 0)
        self.assertExit(self.box.run("rm", "doomed"), 0)
        self.box.log({"type": "refuse", "why": "debt"})
        self.box.log({"type": "refuse", "why": "nudge"})
        recent = self.box.run("status").stdout.split("Recent\n")[1].split("\nOpen")[0].splitlines()
        by_type = {}
        for line in recent:
            by_type.setdefault(line.split()[1], []).append(line)
        self.assertRegex(by_type["skill"][0], r"routed \(project\) -> .*/\.claude/skills/routed$")
        self.assertRegex(by_type["rm"][0], r"doomed \(project\)$")
        self.assertRegex(by_type["refuse"][0], r"debt$")
        self.assertRegex(by_type["refuse"][1], r"nudge$")

    def test_counts_are_untouched_by_the_new_types(self):
        self.box.add("routed")
        self.assertExit(self.box.run("skill", "routed"), 0)
        self.box.log({"type": "refuse", "why": "debt", "lesson": "routed"})
        row = self.box.json("list", "--json")[0]
        self.assertEqual(row["counts"], {"reuse": 0, "guard": 0, "recall": 0, "learn": 1})

    def test_the_docstring_documents_the_three_types(self):
        text = read(self.box.script).split('"""')[1]
        for pattern in (r"\n\s+skill\s+CLI `skill`\s+lesson", r"\n\s+rm\s+CLI `rm`\s+lesson",
                        r"\n\s+refuse\s+mod\s+why", r"COMPOUND_CHECK_BUDGET_MS"):
            self.assertRegex(text, pattern)


class FindLeavesOutThePackagesOwnSkillsTest(Case):
    """15."""

    def test_learn_and_reuse_are_listed_and_never_found(self):
        for name in ("learn", "reuse"):
            self.box.write_lesson(self.box.skill_dir(name, "general"), name,
                                  description="Use when a zsh lesson is to be recorded or reused.",
                                  body="zsh zsh zsh reuse learn.\n")
        self.box.write_lesson(self.box.skill_dir("shipped", "general"), "shipped",
                              description="Use when zsh ships.")
        self.box.add("zsh-word", "Use when zsh expands a word.", "Quote it.\n")
        os.makedirs(os.path.join(self.box.claude, "skills"))
        os.symlink(self.box.skill_dir("learn", "general"), self.box.skill_dir("learn", "user"))
        listed = sorted(row["name"] for row in self.box.json("list", "--json"))
        self.assertEqual(listed, ["learn", "reuse", "shipped", "zsh-word"])
        for words in (("zsh",), ("learn",), ("reuse", "zsh", "lesson")):
            found = [row["name"] for row in self.box.json("find", *words, "--json")["items"]]
            self.assertNotIn("learn", found)
            self.assertNotIn("reuse", found)
        self.assertEqual(sorted(row["name"] for row in self.box.json("find", "zsh", "--json")["items"]),
                         ["shipped", "zsh-word"])

    def test_a_users_own_lesson_named_learn_is_still_found(self):
        self.box.add("learn", "Use when zsh is learned.", "Body.\n")
        self.assertEqual([row["name"] for row in self.box.json("find", "zsh", "--json")["items"]], ["learn"])


if __name__ == "__main__":
    unittest.main()
