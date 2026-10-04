#!/usr/bin/env python3
"""A skill that is used is counted, and a request that keeps coming back is counted.

`compound use NAME` is what the mod runs when a session invokes a skill; the `use` event
it writes is the fourth counter. `find --request` says in which sessions an earlier
request was made, and the memo keeps which sessions asked a request it holds a verdict
for: together they are how often a request was made."""

import json
import os
import subprocess
import unittest

from test_support import NOW, Case, surfer_reachable


class UseTest(Case):
    def skill(self, name, level="project", description="Use when the journey says so."):
        self.box.write_lesson(self.box.skill_dir(name, level), name, description)

    def use(self, name, **kw):
        return self.box.json("use", name, "--json", **kw)

    def test_a_skill_made_from_a_lesson_is_counted_when_it_is_used(self):
        self.box.add("deploy-region", "Use when deploying.", "Run ./deploy.sh --region us-east-1.\n")
        self.assertExit(self.box.run("skill", "deploy-region"), 0)
        said = self.use("deploy-region", COMPOUND_NOW=NOW + 60)
        self.assertEqual((said["used"], said["name"], said["level"]), (True, "deploy-region", "project"))
        event = self.box.read_events()[-1]
        self.assertEqual((event["type"], event["lesson"], event["level"], event["kind"], event["session"]),
                         ("use", "deploy-region", "project", "skill", "sess-0001-aaaa"))
        self.assertEqual(event["path"], self.box.skill_dir("deploy-region"))
        row = [row for row in self.box.json("list", "--json") if row["name"] == "deploy-region"][0]
        self.assertEqual(row["counts"]["use"], 1)

    def test_a_skill_of_the_user_level_and_one_of_the_general_pool_are_counted(self):
        self.skill("history-search", "user")
        self.skill("finish-task", "general")
        self.assertEqual(self.use("history-search")["level"], "user")
        # A skill of the package is invoked under the plugin's name.
        said = self.use("compound:finish-task")
        self.assertEqual((said["used"], said["name"], said["level"]), (True, "finish-task", "general"))
        self.assertEqual([(e["lesson"], e["level"]) for e in self.box.read_events() if e["type"] == "use"],
                         [("history-search", "user"), ("finish-task", "general")])

    def test_the_two_procedures_that_make_and_find_lessons_are_not_uses_of_recorded_work(self):
        self.skill("learn", "general")
        self.skill("reuse", "general")
        for name in ("compound:learn", "compound:reuse"):
            said = self.use(name)
            self.assertFalse(said["used"], said)
            self.assertIn("own", said["reason"])
        self.assertEqual(self.box.read_events(), [])

    def test_a_skill_compound_does_not_list_writes_nothing(self):
        self.skill("finish-task", "general")
        self.box.add("only-a-lesson")
        for name in ("superpowers:brainstorming", "no-such-skill", "only-a-lesson", "other:finish-task", "finish-task",
                     "compound:", ":x", "a\x1b[31mb", "x" * 300):
            proc = self.box.run("use", name, "--json")
            self.assertExit(proc, 0)
            self.assertFalse(json.loads(proc.stdout)["used"], name)
        self.assertEqual([e["type"] for e in self.box.read_events()], ["learn"])

    def test_a_project_skill_is_the_one_a_bare_name_means(self):
        self.skill("shared-name", "user")
        self.skill("shared-name", "project")
        self.assertEqual(self.use("shared-name")["level"], "project")

    def test_the_text_output_says_what_was_counted_on_one_clean_line(self):
        self.skill("local-word")
        proc = self.box.run("use", "local-word")
        self.assertExit(proc, 0)
        self.assertEqual(proc.stdout, "used local-word (project)\n")
        proc = self.box.run("use", "nope\x1b]0;title\x07")
        self.assertExit(proc, 0)
        self.assertNotIn("\x1b", proc.stdout)
        self.assertIn("not counted", proc.stdout)

    def test_the_count_is_a_fourth_counter_wherever_the_three_are(self):
        self.skill("local-word")
        self.box.add("a-lesson")
        self.use("local-word", COMPOUND_NOW=NOW + 10)
        self.use("local-word", COMPOUND_NOW=NOW + 20)
        self.box.log({"type": "reuse", "lessons": ["local-word"]}, COMPOUND_NOW=NOW + 30)
        status = self.box.json("status", "--json", COMPOUND_NOW=NOW + 40)
        self.assertEqual(status["totals"]["used"], 2)
        row = [row for row in status["lessons"] if row["name"] == "local-word"][0]
        self.assertEqual((row["reuse"], row["use"], row["flag"]), (1, 2, ""))
        text = self.box.run("status", COMPOUND_NOW=NOW + 40).stdout
        self.assertRegex(text, r"name\s+level\s+kind\s+reused\s+guarded\s+recalled\s+used\s+flag")
        self.assertRegex(text, r"local-word\s+project\s+skill\s+1\s+0\s+0\s+2")
        self.assertIn("2 skills used", text)
        self.assertRegex(text, r"(?m)^\s+\S+\s+used\s+project\s+local-word \(project\)$")
        listing = self.box.run("list").stdout
        self.assertRegex(listing.splitlines()[0], r"^LEVEL\s+KIND\s+NAME\s+REUSED\s+GUARDED\s+RECALLED\s+USED\s+FLAG\s+WHEN$")
        self.assertRegex(listing, r"project\s+skill\s+local-word\s+1\s+0\s+0\s+2")
        shown = self.box.json("show", "local-word", "--json", COMPOUND_NOW=NOW + 40)
        self.assertEqual(shown["counts"]["use"], 2)
        self.assertEqual(shown["last"]["type"], "reuse")

    def test_a_skill_that_was_only_used_is_in_the_status_table_and_was_last_used(self):
        self.skill("local-word")
        self.use("local-word", COMPOUND_NOW=NOW + 10)
        status = self.box.json("status", "--json", COMPOUND_NOW=NOW + 40)
        self.assertEqual([(row["name"], row["use"], row["flag"]) for row in status["lessons"]], [("local-word", 1, "")])
        self.assertEqual(self.box.json("show", "local-word", "--json")["last"]["type"], "use")
        self.assertIn("1 skill used", self.box.run("status", COMPOUND_NOW=NOW + 40).stdout)

    def test_a_use_is_an_event_the_mod_brought_about(self):
        self.skill("local-word")
        self.use("local-word", COMPOUND_NOW=NOW - 30)
        status = self.box.json("status", "--json")
        fired = [row for row in status["health"] if row["check"] == "mod last fired"][0]
        self.assertEqual((fired["status"], fired["detail"]), ("PASS", "30s ago (use)"))

    def test_the_log_takes_a_use_and_a_repeat_event(self):
        self.box.log({"type": "repeat", "times": 3, "prompts": ["s1:1", "s2:1"], "prompt_id": "0badcafe"})
        self.box.log({"type": "use", "lesson": "x-skill", "level": "user"})
        self.assertEqual([e["type"] for e in self.box.read_events()], ["repeat", "use"])
        recent = [line for line in self.box.run("status").stdout.split("\nRecent\n")[1].split("\n\n")[0].splitlines()]
        self.assertEqual([line.split()[1] for line in recent], ["repeated", "used"])
        self.assertIn("asked 3 times", recent[0])


class PoolProcedureTest(Case):
    def test_the_packages_procedures_are_not_offered_as_existing_work(self):
        for name, text in (("finish-task", "Use when a change is done: review the change, run every check, update the "
                                           "docs and notes, then commit."),
                           ("verify-assumptions-first", "Use when starting a large effort: state the assumptions the "
                                                        "plan rests on and check each with a real call.")):
            self.box.write_lesson(self.box.skill_dir(name, "general"), name, text)
        request = "Finish the task: review the change, run every check, update the docs and notes, and commit it."
        data = self.box.json("find", "--request", "--json", "--floor", "0", stdin=request)
        self.assertEqual(data["items"], [])
        data = self.box.json("find", "assumptions", "commit", "--json")
        self.assertEqual(data["items"], [])
        # They are listed, like every skill.
        self.assertEqual(sorted(row["name"] for row in self.box.json("list", "--json")),
                         ["finish-task", "verify-assumptions-first"])


class AskedTest(Case):
    """The memo keeps which sessions asked a request it holds a verdict for."""
    REQUEST = "Write the weekly digest of merged pull requests and post it to the team channel."

    def find(self, **kw):
        return self.box.json("find", "--request", "--json", stdin=self.REQUEST, **kw)

    def test_the_sessions_that_asked_a_remembered_request_are_kept(self):
        key = self.find(CLAUDE_CODE_SESSION_ID="s-one")["memo_key"]
        row = {"id": "s-zero:1", "ts": "2026-09-01", "project": "p", "session": "s-zero", "prompt": "write the digest",
               "sessions": ["s-zero", "s-older"]}
        proc = self.box.run("memo", stdin=json.dumps({"key": key, "verdict": "nothing", "items": [], "prompts": [],
                                                      "repeats": [row]}), CLAUDE_CODE_SESSION_ID="s-one")
        self.assertExit(proc, 0)
        memo = self.find(CLAUDE_CODE_SESSION_ID="s-two")["memo"]
        self.assertEqual(memo["asked"], ["s-one", "s-two"])
        self.assertEqual(memo["repeats"], [row])
        memo = self.find(CLAUDE_CODE_SESSION_ID="s-two")["memo"]
        self.assertEqual(memo["asked"], ["s-one", "s-two"], "a session is kept once")
        memo = self.find(CLAUDE_CODE_SESSION_ID="s-three")["memo"]
        self.assertEqual(memo["asked"], ["s-one", "s-two", "s-three"])
        # A request asked outside a session adds nothing.
        self.assertEqual(self.find(CLAUDE_CODE_SESSION_ID=None)["memo"]["asked"], ["s-one", "s-two", "s-three"])

    def test_a_memo_without_repeats_reads_as_none(self):
        key = self.find()["memo_key"]
        self.assertExit(self.box.run("memo", stdin=json.dumps({"key": key, "verdict": "nothing"})), 0)
        memo = self.find()["memo"]
        self.assertEqual((memo["repeats"], memo["asked"]), ([], ["sess-0001-aaaa"]))
        proc = self.box.run("memo", stdin=json.dumps({"key": key, "verdict": "nothing", "repeats": "x"}))
        self.assertExit(proc, 2)


class SessionsTest(Case):
    """An earlier request says in which sessions it was made, against the real history-surfer."""

    def test_the_same_request_made_in_three_sessions_is_one_row_that_names_them(self):
        if not surfer_reachable():
            self.skipTest("history-surfer cannot be cloned from here")
        box = self.box
        box.plugin()
        self.assertExit(box.run("install", "--bin-dir", box.bin, COMPOUND_NO_SURFER=None), 0)
        surfer = os.path.join(box.bin, "surfer")
        other = os.path.join(box.root, "other-project")
        os.makedirs(other)
        asked = "write the weekly digest of merged pull requests and post it to the team channel"
        with open(os.path.join(box.claude, "history.jsonl"), "w") as handle:
            for seq, (session, project, prompt) in enumerate((
                    ("s-a", box.project, asked), ("s-b", other, asked), ("s-c", other, asked), ("s-c", other, asked),
                    ("s-d", other, "rename the digest module"))):
                handle.write(json.dumps({"display": prompt, "pastedContents": {}, "timestamp": 1789000000000 + seq * 100000,
                                         "project": project, "sessionId": session}) + "\n")
        env = box.env(PATH=box.bin + ":/usr/bin:/bin")
        seeded = subprocess.run([surfer, "import-history"], env=env, cwd=box.project, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(seeded.returncode, 0, seeded.stderr)
        data = box.json("find", "--request", "--json", stdin="Write the weekly digest of merged pull requests and post "
                        "it to the team channel.", PATH=box.bin + ":/usr/bin:/bin")
        self.assertEqual(data["surfer"], "ok")
        rows = [row for row in data["prompts"] if row["prompt"] == asked]
        self.assertEqual(len(rows), 1, data["prompts"])
        self.assertEqual(sorted(rows[0]["sessions"]), ["s-a", "s-b", "s-c"])
        self.assertIn(rows[0]["session"], rows[0]["sessions"])


if __name__ == "__main__":
    unittest.main()
