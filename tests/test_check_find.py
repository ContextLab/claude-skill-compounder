#!/usr/bin/env python3
"""check (guards against a tool call) and find (word overlap, then the prompt log)."""

import json
import os
import re
import subprocess
import sys
import time
import unittest

from test_support import Case, SURFER_URL, git_ok, surfer_reachable


def call(tool, payload):
    return json.dumps({"tool": tool, "input": payload})


class CheckTest(Case):
    def hits(self, tool, payload, **kw):
        proc = self.box.run("check", stdin=call(tool, payload), **kw)
        self.assertExit(proc, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(list(data), ["hits"])
        return data["hits"]

    def test_guards_flag_adds_how_many_guards_there_are(self):
        """The mod asks with --guards, so one `check` also tells it whether any lesson
        carries a pattern at all, and it never needs a listing before a tool call."""
        proc = self.box.run("check", "--guards", stdin=call("Bash", {"command": "ls"}))
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout), {"hits": [], "guards": 0, "tools": []})
        self.box.add("plain-lesson")
        self.box.add("a-guard", "Use when.", "Body.\n", "--match", "echo\\s+GUARDED")
        self.box.add("another", "Use when.", "Body.\n", "--level", "user", "--match", "rm -rf /tmp/x")
        proc = self.box.run("check", "--guards", stdin=call("Bash", {"command": "ls"}))
        self.assertEqual(json.loads(proc.stdout), {"hits": [], "guards": 2, "tools": ["Bash"]})
        proc = self.box.run("check", "--guards", stdin=call("Bash", {"command": "echo  GUARDED"}))
        data = json.loads(proc.stdout)
        self.assertEqual(([hit["name"] for hit in data["hits"]], data["guards"]), (["a-guard"], 2))
        proc = self.box.run("check", "--guards", stdin=call("Bash", {"command": ""}))
        self.assertEqual(json.loads(proc.stdout), {"hits": [], "guards": 2, "tools": ["Bash"]},
                         "an empty call is still counted")
        self.box.add("no-env-edit", "Use when.", "Body.\n", "--match", "\\.env", "--tool", "Edit", "--tool", "Write")
        proc = self.box.run("check", "--guards", stdin=call("Read", {"file_path": "/x"}))
        self.assertEqual(json.loads(proc.stdout), {"hits": [], "guards": 3, "tools": ["Bash", "Edit", "Write"]},
                         "the tools any guard applies to, so the mod need not ask before a call of another tool")
        self.assertEqual(self.hits("Bash", {"command": "ls"}), [], "without the flag the answer is the hits alone")

    def test_a_guard_matches_a_bash_command(self):
        self.box.add("zsh-equals-word", "Use when.", "Quote the separator.\n\nSecond paragraph.\n",
                     "--match", r"(^|[;&|]\s*)echo\s+=+")
        hits = self.hits("Bash", {"command": "ls; echo ====="})
        self.assertEqual(hits, [{
            "name": "zsh-equals-word", "level": "project",
            "path": self.box.lesson_dir("zsh-equals-word"),
            "text": "Quote the separator.\n\nSecond paragraph."}])

    def test_a_command_that_does_not_match_has_no_hits(self):
        self.box.add("zsh-equals-word", "Use when.", "Body.\n", "--match", r"(^|[;&|]\s*)echo\s+=+")
        self.assertEqual(self.hits("Bash", {"command": "printf '%s\\n' '====='"}), [])

    def test_a_lesson_without_match_is_never_a_hit(self):
        self.box.add("plain", "Use when echo is used.", "echo echo echo\n")
        self.assertEqual(self.hits("Bash", {"command": "echo ====="}), [])

    def test_bash_is_tested_on_the_command_not_on_the_json(self):
        self.box.add("anchored", "Use when.", "Body.\n", "--match", r"^git push --force")
        self.assertEqual(len(self.hits("Bash", {"command": "git push --force", "description": "x"})), 1)
        self.box.add("on-description", "Use when.", "Body.\n", "--match", "push the branch")
        hits = self.hits("Bash", {"command": "git status", "description": "push the branch"})
        self.assertEqual(hits, [])

    def test_other_tools_are_tested_on_the_json_of_the_input(self):
        self.box.add("no-env-edit", "Use when.", "Never edit .env.\n", "--match", r'"file_path": "[^"]*\.env"',
                     "--tool", "Edit")
        hits = self.hits("Edit", {"file_path": "/repo/.env", "old_string": "a", "new_string": "b"})
        self.assertEqual([hit["name"] for hit in hits], ["no-env-edit"])
        self.assertEqual(self.hits("Edit", {"file_path": "/repo/main.py", "old_string": "a", "new_string": "b"}), [])

    def test_a_guard_is_for_bash_commands_unless_its_lesson_names_other_tools(self):
        """Text that is not a command is not guarded: a file's content, an agent's prompt
        and a hand-back that merely mention the mistake run. The calls are the ones the
        audit of 2026-10-04 reproduced."""
        self.box.add("chain-commit-with-and", "Use when.", "Chain the commit with &&.\n",
                     "--match", r";\s*git\s+commit\b")
        self.assertEqual(len(self.hits("Bash", {"command": "pytest -q; git commit -m done"})), 1)
        for tool, payload in (
                ("Write", {"file_path": "/repo/notes.md", "content": "Run the tests; git commit -m done"}),
                ("SubagentHandback", {"message": "I ran pytest; git commit was not run."}),
                ("Agent", {"prompt": "run the suite; git commit only if green"}),
                ("Edit", {"file_path": "/repo/a.md", "old_string": "x", "new_string": "ok; git commit"})):
            self.assertEqual(self.hits(tool, payload), [], tool)
        # A lesson that names a tool is tested on that tool's input, and on no other's.
        self.box.add("no-commit-in-notes", "Use when.", "Body.\n", "--match", r";\s*git\s+commit\b", "--tool", "Write")
        hits = self.hits("Write", {"file_path": "/repo/notes.md", "content": "Run the tests; git commit -m done"})
        self.assertEqual([hit["name"] for hit in hits], ["no-commit-in-notes"])
        self.assertEqual([hit["name"] for hit in self.hits("Bash", {"command": "pytest -q; git commit -m done"})],
                         ["chain-commit-with-and"])
        self.assertEqual(self.hits("Agent", {"prompt": "run the suite; git commit only if green"}), [])

    def test_a_call_that_names_no_tool_is_tested_against_nothing(self):
        self.box.add("danger", "Use when.", "Body.\n", "--match", "danger")
        proc = self.box.run("check", stdin=json.dumps({"input": "danger"}))
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout), {"hits": []})

    def test_a_caret_matches_at_the_start_of_every_line(self):
        """Patterns are compiled with re.MULTILINE: a command on the second line of a call
        starts a line. The commands are the audit's."""
        self.box.add("macos-no-timeout", "Use when.", "Body.\n", "--match", r"(^|[;&|]\s*)timeout\s+\d")
        for command in ("timeout 5 ls", "cd /tmp\ntimeout 5 ls", "cd /tmp &&\n  ls;\ntimeout 5 ls", "ls; timeout 5 ls"):
            self.assertEqual(len(self.hits("Bash", {"command": command})), 1, command)
        for command in ("echo timeout 5", "cd /tmp\necho no timeout 5 here", "grep -c timeout 5.log"):
            self.assertEqual(self.hits("Bash", {"command": command}), [], command)
        self.box.add("brew-doctor-exits-1", "Use when.", "Body.\n", "--match", r"brew doctor\s*$")
        self.assertEqual(len(self.hits("Bash", {"command": "brew doctor\necho done"})), 1, "$ is a line's end")

    def test_the_anchor_the_learn_skill_teaches_finds_a_command_wherever_one_starts(self):
        repo = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        anchor = r"(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)"
        for rel in (os.path.join("skills", "learn", "SKILL.md"), os.path.join("docs", "guide.md")):
            with open(os.path.join(repo, rel)) as handle:
                text = handle.read()
            self.assertIn("--match '%secho\\s+=+'" % anchor, text, rel)
            self.assertNotIn(r"(^|[;&|]\s*)", text, rel)
        self.box.add("macos-no-timeout", "Use when.", "Body.\n", "--match", anchor + r"timeout\s+\d")
        for command in ("timeout 5 ls", "cd /tmp\ntimeout 5 ls", "cd /tmp\n  timeout 5 ls",
                        "for f in a b; do timeout 5 ls $f; done", "x=$(timeout 5 ls)",
                        "if true; then timeout 5 ls; else timeout 6 ls; fi", "ls && timeout 5 ls", "ls | timeout 5 cat"):
            self.assertEqual(len(self.hits("Bash", {"command": command})), 1, command)
        for command in ("echo timeout 5", "grep -n 'timeout 5' run.sh", "git commit -m 'undo timeout 5'",
                        "gtimeout 5 ls", "./timeout 5"):
            self.assertEqual(self.hits("Bash", {"command": command}), [], command)

    def test_guards_at_all_three_levels_are_tested(self):
        self.box.add("p-guard", "Use when.", "P.\n", "--match", "danger")
        self.box.add("u-guard", "Use when.", "U.\n", "--level", "user", "--match", "danger")
        self.box.write_lesson(self.box.lesson_dir("g-guard", "general"), "g-guard", body="G.\n",
                              extra='match: ["danger"]\n')
        self.box.write_lesson(self.box.skill_dir("s-guard", "user"), "s-guard", body="S.\n",
                              extra='match: ["danger"]\n')
        # A guard of the general pool yields to a nearer one that hits the same call.
        proc = self.box.run("check", stdin=json.dumps({"tool": "Bash", "input": {"command": "run danger now"}}))
        self.assertExit(proc, 0)
        data = json.loads(proc.stdout)
        self.assertEqual([(hit["level"], hit["name"]) for hit in data["hits"]],
                         [("project", "p-guard"), ("user", "u-guard"), ("user", "s-guard")])
        self.assertEqual(data["yielded"], ["g-guard"])
        self.assertExit(self.box.run("rm", "p-guard"), 0)
        self.assertExit(self.box.run("rm", "u-guard"), 0)
        self.assertExit(self.box.run("rm", "s-guard", "--force"), 0)
        hits = self.hits("Bash", {"command": "run danger now"})
        self.assertEqual([(hit["level"], hit["name"]) for hit in hits], [("general", "g-guard")])

    def test_a_lesson_with_two_matching_patterns_is_one_hit(self):
        self.box.add("twice", "Use when.", "Body.\n", "--match", "dan", "--match", "ger")
        self.assertEqual(len(self.hits("Bash", {"command": "danger"})), 1)

    def test_any_one_of_several_patterns_is_enough(self):
        self.box.add("either", "Use when.", "Body.\n", "--match", "alpha", "--match", "beta")
        self.assertEqual(len(self.hits("Bash", {"command": "run beta"})), 1)

    def test_a_stored_pattern_that_cannot_be_used_is_skipped_not_fatal(self):
        self.box.write_lesson(self.box.lesson_dir("broken-re"), "broken-re", extra='match: ["(", "x*", "danger"]\n')
        hits = self.hits("Bash", {"command": "ls"})
        self.assertEqual(hits, [], "a pattern matching the empty string must never fire")
        self.assertEqual([hit["name"] for hit in self.hits("Bash", {"command": "danger"})], ["broken-re"])

    def test_stdin_that_is_not_json_is_a_usage_error(self):
        for text in ("", "not json", "[1, 2]", '"a string"'):
            proc = self.box.run("check", stdin=text)
            self.assertExit(proc, 2)
            self.assertIn("stdin", proc.stderr)

    def test_a_call_with_no_input_has_no_hits(self):
        self.box.add("a-guard", "Use when.", "Body.\n", "--match", "danger")
        proc = self.box.run("check", stdin='{"tool": "Bash"}')
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout), {"hits": []})

    def test_check_does_not_read_the_event_log(self):
        self.box.add("a-guard", "Use when.", "Body.\n", "--match", "danger")
        with open(self.box.events, "a") as handle:
            handle.write("this line is not JSON\n")
        os.chmod(self.box.events, 0)
        try:
            self.assertEqual(len(self.hits("Bash", {"command": "danger"})), 1)
        finally:
            os.chmod(self.box.events, 0o644)

    def test_check_writes_nothing(self):
        self.box.add("a-guard", "Use when.", "Body.\n", "--match", "danger")
        before = self.box.snapshot()
        self.hits("Bash", {"command": "danger"})
        self.assertEqual(self.box.snapshot(), before)

    def test_check_starts_no_git_even_without_the_project_override(self):
        """With an empty PATH there is no git to start; the project is still found by
        walking up to the .git entry."""
        repo = os.path.join(self.box.root, "repo")
        os.makedirs(os.path.join(repo, "deep"))
        git_ok("init", "-q", repo)
        self.box.write_lesson(os.path.join(repo, ".claude", "compound", "lessons", "repo-guard"), "repo-guard",
                              extra='match: ["danger"]\n')
        for override in ({"COMPOUND_PROJECT": None}, {"COMPOUND_PROJECT": repo}):
            hits = self.hits("Bash", {"command": "danger"}, cwd=os.path.join(repo, "deep"), PATH="", **override)
            self.assertEqual([hit["name"] for hit in hits], ["repo-guard"])

    def test_check_is_fast(self):
        for index in range(40):
            self.box.add("guard-%02d" % index, "Use when.", "Body.\n", "--match", "danger-%02d" % index)
        self.hits("Bash", {"command": "warm"})
        started = time.time()
        for _ in range(5):
            self.hits("Bash", {"command": "ls -la"})
        each = (time.time() - started) / 5
        self.assertLess(each, 1.0, "check took %.3fs a call over forty guards" % each)


class FindTest(Case):
    def setUp(self):
        Case.setUp(self)
        self.box.add("zsh-equals-word", "Use when a zsh command has a bare equals word.",
                     "zsh expands the word as a command lookup. Quote it.\n")
        self.box.add("pipeline-status", "Use when a pipeline hides a failing exit status.",
                     "A pipeline exits with the last command. Check the first.\n", "--level", "user")
        self.box.write_lesson(self.box.skill_dir("cite-paper", "user"), "cite-paper",
                              description="Use when filling a placeholder citation.",
                              body="Search the bibliography, then verify the entry.\n")
        os.makedirs(os.path.join(self.box.project, "scripts"))
        with open(os.path.join(self.box.project, "scripts", "release.sh"), "w") as handle:
            handle.write("#!/bin/sh\n# Cut a release: tag, build, verify.\n")

    def test_items_are_ranked_by_word_overlap(self):
        data = self.box.json("find", "zsh", "command", "pipeline", "--json")
        self.assertEqual(data["words"], ["zsh", "command", "pipeline"])
        self.assertEqual([(row["name"], row["score"]) for row in data["items"]],
                         [("zsh-equals-word", 2), ("pipeline-status", 2)])

    def test_ties_go_to_the_item_with_more_of_the_words_in_its_name_and_description(self):
        data = self.box.json("find", "zsh", "lookup", "--json")
        self.assertEqual([row["name"] for row in data["items"]], ["zsh-equals-word"])
        data = self.box.json("find", "command", "--json")
        self.assertEqual([row["name"] for row in data["items"]], ["zsh-equals-word", "pipeline-status"],
                         "'command' is in one description and only in the other's body")

    def test_the_body_is_searched_and_case_is_ignored(self):
        data = self.box.json("find", "BIBLIOGRAPHY", "--json")
        self.assertEqual([(row["kind"], row["name"]) for row in data["items"]], [("skill", "cite-paper")])

    def test_scripts_are_found(self):
        data = self.box.json("find", "release", "tag", "--json")
        self.assertEqual([(row["kind"], row["name"]) for row in data["items"]], [("script", "scripts/release.sh")])

    def test_one_quoted_argument_is_split_into_words(self):
        data = self.box.json("find", "Verify the  release", "--json")
        self.assertEqual(data["words"], ["verify", "release"])
        self.assertEqual({row["name"] for row in data["items"]}, {"scripts/release.sh", "cite-paper"})

    def test_items_carry_the_list_fields(self):
        row = self.box.json("find", "citation", "--json")["items"][0]
        for key in ("level", "kind", "name", "description", "path", "match", "counts", "score"):
            self.assertIn(key, row)

    def test_nothing_matching_is_not_an_error(self):
        proc = self.box.run("find", "xylophone")
        self.assertExit(proc, 0)
        self.assertIn("no lesson, skill or script matches", proc.stdout)

    def test_a_missing_surfer_is_said_and_is_not_an_error(self):
        proc = self.box.run("find", "zsh")
        self.assertExit(proc, 0)
        self.assertIn("prompt log: not searched", proc.stdout)
        data = self.box.json("find", "zsh", "--json")
        self.assertEqual((data["surfer"], data["prompts"]), ("missing", []))

    def test_a_named_surfer_that_does_not_exist_is_missing(self):
        data = self.box.json("find", "zsh", "--json", COMPOUND_SURFER=os.path.join(self.box.root, "no-such-surfer"))
        self.assertEqual(data["surfer"], "missing")

    def test_no_words_is_a_usage_error(self):
        self.assertExit(self.box.run("find"), 2)
        proc = self.box.run("find", "!!!", "--")
        self.assertExit(proc, 2)

    def test_limit(self):
        data = self.box.json("find", "use", "when", "--json", "--limit", "2")
        self.assertEqual(len(data["items"]), 2)


class FindPromptLogTest(Case):
    """Against the real history-surfer, cloned by the real `compound install`."""

    def test_prompt_log_hits_follow_the_items_project_first_then_every_project(self):
        if not surfer_reachable():
            self.skipTest("history-surfer cannot be cloned from here (%s)" % SURFER_URL)
        box = self.box
        box.plugin()  # status fails its mod check for a checkout that cannot load as the plugin
        proc = box.run("install", "--bin-dir", box.bin, COMPOUND_NO_SURFER=None)
        self.assertExit(proc, 0)
        surfer = os.path.join(box.bin, "surfer")
        self.assertTrue(os.path.exists(surfer), proc.stdout + proc.stderr)

        other = os.path.join(box.root, "other-project")
        os.makedirs(other)
        rows = [
            ("s1", 1789000000000, box.project, "please fix the zsh separator bug in the release script"),
            ("s1", 1789000100000, box.project, "now write the changelog"),
            ("s2", 1789000200000, other, "the zsh separator fails again, and the pipeline too"),
            ("s2", 1789000300000, other, "zsh question"),
            ("s2", 1789000400000, other, "unrelated request about figures"),
        ]
        with open(os.path.join(box.claude, "history.jsonl"), "w") as handle:
            for session, stamp, project, text in rows:
                handle.write(json.dumps({"display": text, "pastedContents": {}, "timestamp": stamp,
                                         "project": project, "sessionId": session}) + "\n")
        env = box.env(PATH=box.bin + ":/usr/bin:/bin")
        seeded = subprocess.run([surfer, "import-history"], env=env, cwd=box.project, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(seeded.returncode, 0, seeded.stderr)

        data = box.json("find", "zsh", "separator", "pipeline", "--json", PATH=box.bin + ":/usr/bin:/bin")
        self.assertEqual(data["surfer"], "ok")
        self.assertEqual([(hit["scope"], hit["score"], hit["prompt"]) for hit in data["prompts"]], [
            ("project", 2, "please fix the zsh separator bug in the release script"),
            ("all", 3, "the zsh separator fails again, and the pipeline too"),
            ("all", 1, "zsh question"),
        ])
        self.assertEqual(data["prompts"][0]["project"], box.project)
        self.assertTrue(all(hit["id"] and hit["ts"] for hit in data["prompts"]))
        self.assertEqual([hit["session"] for hit in data["prompts"]], ["s1", "s2", "s2"],
                         "each row carries the session it was typed in, so a caller can leave out its own")
        self.assertTrue(all(re.match(r"^\d{4}-\d\d-\d\dT", hit["ts"]) for hit in data["prompts"]))

        named = box.json("find", "changelog", "--json", COMPOUND_SURFER=surfer, PATH="/usr/bin:/bin")
        self.assertEqual([hit["prompt"] for hit in named["prompts"]], ["now write the changelog"])

        human = box.run("find", "zsh", "separator", PATH=box.bin + ":/usr/bin:/bin")
        self.assertExit(human, 0)
        self.assertIn("earlier requests:", human.stdout)
        self.assertIn("please fix the zsh separator bug", human.stdout)

        many = [("s3", 1789001000000 + i, other, "zsh prompt number %d" % i) for i in range(12)]
        with open(os.path.join(box.claude, "history.jsonl"), "a") as handle:
            for session, stamp, project, text in many:
                handle.write(json.dumps({"display": text, "pastedContents": {}, "timestamp": stamp,
                                         "project": project, "sessionId": session}) + "\n")
        subprocess.run([surfer, "import-history"], env=env, cwd=box.project, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        capped = box.json("find", "zsh", "--json", PATH=box.bin + ":/usr/bin:/bin")
        self.assertEqual(len(capped["prompts"]), 5)
        self.assertEqual(len({hit["id"] for hit in capped["prompts"]}), 5)

        status = box.json("status", "--json", PATH=box.bin + ":/usr/bin:/bin")
        row = [check for check in status["health"] if check["check"] == "prompt log"][0]
        self.assertEqual(row["status"], "PASS", row)
        self.assertRegex(row["detail"], r"^\d+ prompts? in this project$", "the real `surfer stats` is read as a count")


if __name__ == "__main__":
    unittest.main()
