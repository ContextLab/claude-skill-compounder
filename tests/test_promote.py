#!/usr/bin/env python3
"""promote: the move to the user level, the dry run to general, and every refusal.

The `--yes` path to general opens a real pull request, so it is never completed here:
only its refusals are driven, against an upstream name that does not exist.
"""

import json
import os
import unittest

from test_support import Case

NO_UPSTREAM = "compound-test-invalid/no-such-repository"


def read(path):
    with open(path) as handle:
        return handle.read()


class PromoteUserTest(Case):
    def test_a_project_lesson_moves_to_the_user_level(self):
        source = os.path.join(self.box.root, "helper.sh")
        with open(source, "w") as handle:
            handle.write("# helper\n")
        self.box.add("travels", "Use when.", "Body.\n", "--attach", source)
        text = read(os.path.join(self.box.lesson_dir("travels"), "SKILL.md"))
        proc = self.box.run("promote", "travels", "--to", "user")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.box.lesson_dir("travels")), "a move, never a copy")
        target = self.box.lesson_dir("travels", "user")
        self.assertEqual(read(os.path.join(target, "SKILL.md")), text)
        self.assertTrue(os.path.isfile(os.path.join(target, "helper.sh")))
        rows = self.box.json("list", "--json")
        self.assertEqual([(row["level"], row["name"]) for row in rows], [("user", "travels")])
        event = self.box.read_events()[-1]
        self.assertEqual(event, {
            "ts": "2026-09-21T14:13:20Z", "type": "promote", "session": "sess-0001-aaaa",
            "project": self.box.project, "lesson": "travels", "to": "user", "path": target, "from": "project"})

    def test_a_project_skill_moves_to_the_user_skills_directory(self):
        self.box.add("routed")
        self.assertExit(self.box.run("skill", "routed"), 0)
        self.assertExit(self.box.run("promote", "routed", "--to", "user"), 0)
        self.assertFalse(os.path.exists(self.box.skill_dir("routed", "project")))
        self.assertTrue(os.path.isfile(os.path.join(self.box.skill_dir("routed", "user"), "SKILL.md")))

    def test_json_output(self):
        self.box.add("travels")
        data = self.box.json("promote", "travels", "--to", "user", "--json")
        self.assertEqual(data, {"name": "travels", "from": "project", "to": "user", "kind": "lesson",
                                "path": self.box.lesson_dir("travels", "user")})

    def refused(self, *args, **kw):
        before = self.box.snapshot()
        proc = self.box.run(*args, **kw)
        self.assertExit(proc, 2)
        self.assertEqual(self.box.snapshot(), before, "a refused promote changed something")
        return proc.stderr

    def test_already_at_user_is_refused(self):
        self.box.add("settled", "Use when.", "Body.\n", "--level", "user")
        self.assertIn("already at the user level", self.refused("promote", "settled", "--to", "user"))

    def test_a_general_lesson_is_refused(self):
        self.box.write_lesson(self.box.lesson_dir("shipped", "general"), "shipped")
        self.assertIn("already at the general level", self.refused("promote", "shipped", "--to", "user"))

    def test_an_unknown_name_is_refused(self):
        self.assertIn("no lesson or skill named", self.refused("promote", "nothing-here", "--to", "user"))

    def test_to_is_required_and_must_be_a_level_above(self):
        self.box.add("travels")
        self.refused("promote", "travels")
        self.refused("promote", "travels", "--to", "project")

    def test_an_occupied_target_is_refused(self):
        self.box.add("travels")
        os.makedirs(self.box.lesson_dir("travels", "user"))
        self.assertIn("already exists", self.refused("promote", "travels", "--to", "user"))


class PromoteGeneralTest(Case):
    def setUp(self):
        Case.setUp(self)
        source = os.path.join(self.box.root, "fix.sh")
        with open(source, "w") as handle:
            handle.write("#!/bin/sh\necho fixed\n")
        self.box.add("zsh-equals-word", "Use when a zsh line has a bare equals word.", "Quote the word.\n",
                     "--level", "user", "--match", r"echo\s+=+", "--attach", source)

    def test_the_dry_run_prints_the_plan_and_writes_nothing_anywhere(self):
        before = self.box.snapshot()
        proc = self.box.run("promote", "zsh-equals-word", "--to", "general")
        self.assertExit(proc, 0)
        self.assertEqual(self.box.snapshot(), before, "the dry run wrote something")
        self.assertFalse(any(event["type"] == "promote" for event in self.box.read_events()))
        out = proc.stdout
        self.assertIn("nothing has been written", out)
        self.assertIn("ContextLab/claude-skill-compounder", out)
        self.assertIn("compound/lesson-zsh-equals-word", out)
        self.assertIn("lessons/zsh-equals-word/SKILL.md", out)
        self.assertIn("lessons/zsh-equals-word/fix.sh", out)
        self.assertIn("Add lesson: zsh-equals-word", out)
        self.assertIn("Use when a zsh line has a bare equals word.", out)
        self.assertIn("Quote the word.", out)
        self.assertIn("SKILL.md as it will be published:\n    ---\n    name: zsh-equals-word\n", out,
                      "the plan shows the file exactly as it would be published")
        self.assertNotIn("origin:", out, "the origin names a private project and session; it is not published")
        self.assertNotIn("sess-000", out)
        self.assertIn("origin: project project, session sess-000\n",
                      read(os.path.join(self.box.lesson_dir("zsh-equals-word", "user"), "SKILL.md")),
                      "the local lesson keeps its origin")
        self.assertIn("--yes", out)

    def test_the_dry_run_as_json(self):
        before = self.box.snapshot()
        plan = self.box.json("promote", "zsh-equals-word", "--to", "general", "--json")
        self.assertEqual(self.box.snapshot(), before)
        self.assertEqual(plan["upstream"], "ContextLab/claude-skill-compounder")
        self.assertEqual(plan["branch"], "compound/lesson-zsh-equals-word")
        self.assertEqual(plan["files"], ["lessons/zsh-equals-word/SKILL.md", "lessons/zsh-equals-word/fix.sh"])
        self.assertEqual(plan["title"], "Add lesson: zsh-equals-word")
        self.assertIn("Quote the word.", plan["body"])
        self.assertIn("`echo\\s+=+`", plan["body"])
        self.assertEqual((plan["from"], plan["to"], plan["dry_run"]), ("user", "general", True))
        self.assertEqual(plan["source"], self.box.lesson_dir("zsh-equals-word", "user"))

    def test_the_upstream_comes_from_the_environment(self):
        plan = self.box.json("promote", "zsh-equals-word", "--to", "general", "--json",
                             COMPOUND_UPSTREAM="someone/their-fork")
        self.assertEqual(plan["upstream"], "someone/their-fork")

    def test_an_upstream_that_is_not_owner_repo_is_refused(self):
        for bad in ("not-a-repo", "https://github.com/a/b", "a/b/c", "a b/c"):
            proc = self.box.run("promote", "zsh-equals-word", "--to", "general", COMPOUND_UPSTREAM=bad)
            self.assertExit(proc, 2)
            self.assertIn("COMPOUND_UPSTREAM", proc.stderr)

    def test_a_skill_is_proposed_under_skills(self):
        self.assertExit(self.box.run("skill", "zsh-equals-word"), 0)
        plan = self.box.json("promote", "zsh-equals-word", "--to", "general", "--json")
        self.assertEqual(plan["branch"], "compound/skill-zsh-equals-word")
        self.assertEqual(plan["files"], ["skills/zsh-equals-word/SKILL.md", "skills/zsh-equals-word/fix.sh"])
        self.assertEqual(plan["title"], "Add skill: zsh-equals-word")

    def test_a_project_lesson_can_be_proposed_too(self):
        self.box.add("local-one")
        plan = self.box.json("promote", "local-one", "--to", "general", "--json")
        self.assertEqual(plan["from"], "project")

    def test_a_lesson_already_general_is_refused(self):
        self.box.write_lesson(self.box.lesson_dir("shipped", "general"), "shipped")
        before = self.box.snapshot()
        for flags in ((), ("--yes",)):
            proc = self.box.run("promote", "shipped", "--to", "general", *flags)
            self.assertExit(proc, 2)
            self.assertIn("already in the general pool", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)

    def test_an_unknown_name_is_refused_with_and_without_yes(self):
        for flags in ((), ("--yes",)):
            self.assertExit(self.box.run("promote", "nothing-here", "--to", "general", *flags), 2)

    def test_yes_without_a_usable_gh_fails_and_changes_nothing(self):
        """No gh on the minimal PATH (macOS), or a gh with no login under the temporary
        HOME (CI). Either way: exit 1, the lesson stays, no promote event. The upstream
        named here does not exist, so no pull request could be opened even by a gh that
        was somehow logged in."""
        before = self.box.snapshot()
        proc = self.box.run("promote", "zsh-equals-word", "--to", "general", "--yes",
                            COMPOUND_UPSTREAM=NO_UPSTREAM, GH_TOKEN=None, GITHUB_TOKEN=None)
        self.assertExit(proc, 1)
        self.assertRegex(proc.stderr, r"`gh` is not (on PATH|authenticated)|cannot read")
        after = self.box.snapshot()
        after.pop(os.path.relpath(os.path.join(self.box.home, "gh-config"), self.box.root), None)
        self.assertEqual({key: value for key, value in after.items() if "gh-config" not in key}, before)
        self.assertFalse(any(event["type"] == "promote" for event in self.box.read_events()))
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("zsh-equals-word", "user"), "SKILL.md")))

    def test_yes_with_an_empty_path_names_gh(self):
        proc = self.box.run("promote", "zsh-equals-word", "--to", "general", "--yes",
                            COMPOUND_UPSTREAM=NO_UPSTREAM, PATH="")
        self.assertExit(proc, 1)
        self.assertIn("`gh` is not on PATH", proc.stderr)


if __name__ == "__main__":
    unittest.main()
