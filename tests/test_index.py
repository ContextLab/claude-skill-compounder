#!/usr/bin/env python3
"""`compound index`: the lessons a session of a project could use, as rows. The lessons in
force here, and the lessons of the user's other projects that carry a script, the ones
with a script first."""

import json
import os
import unittest

from test_support import NOW, Case


class IndexTest(Case):
    def index(self, **kw):
        return json.loads(self.box.run("index", **kw).stdout)

    def tool(self, name="tool.sh"):
        path = os.path.join(self.box.root, name)
        with open(path, "w") as handle:
            handle.write("#!/bin/sh\necho ok\n")
        os.chmod(path, 0o755)
        return path

    def test_an_empty_store_is_an_empty_list(self):
        self.assertEqual(self.index(), [])

    def test_lessons_with_a_script_come_first_then_the_projects_own_then_the_users(self):
        self.box.add("zz-plain-project", "Use when plain in the project.", "Body.\n")
        self.box.add("aa-plain-user", "Use when plain for the user.", "Body.\n", "--level", "user")
        self.box.add("mm-tool-user", "Use when the user's tool is needed.", "Run tool.sh.\n", "--level", "user",
                     "--attach", self.tool(), "--unrun")
        self.box.add("yy-tool-project", "Use when the project's tool is needed.", "Run tool.sh.\n",
                     "--attach", self.tool(), "--unrun")
        notes = os.path.join(self.box.root, "table.csv")
        with open(notes, "w") as handle:
            handle.write("a,b\n")
        self.box.add("bb-data-project", "Use when reading the table.", "See table.csv.\n", "--attach", notes)
        rows = self.index()
        self.assertEqual([(row["name"], row["level"], row["script"]) for row in rows], [
            ("yy-tool-project", "project", True), ("mm-tool-user", "user", True),
            ("bb-data-project", "project", False), ("zz-plain-project", "project", False),
            ("aa-plain-user", "user", False)])
        self.assertEqual(rows[0]["description"], "Use when the project's tool is needed.")
        self.assertEqual(rows[0]["path"], self.box.lesson_dir("yy-tool-project"))
        self.assertNotIn("project", rows[0])

    def test_another_projects_lesson_is_listed_when_it_carries_a_script_and_only_then(self):
        other = os.path.join(self.box.root, "other-project")
        os.makedirs(other)
        self.box.add("check-built-site", "Use when the docs site was rebuilt.", "Run tool.sh on the build.\n",
                     "--attach", self.tool(), "--unrun", COMPOUND_PROJECT=other, cwd=other)
        self.box.add("other-plain", "Use when in the other project.", "Body.\n", COMPOUND_PROJECT=other, cwd=other)
        self.box.add("here-plain", "Use when here.", "Body.\n")
        rows = self.index()
        self.assertEqual([(row["name"], row.get("project")) for row in rows],
                         [("check-built-site", other), ("here-plain", None)])
        self.assertEqual(rows[0]["path"], os.path.join(other, ".claude", "compound", "lessons", "check-built-site"))
        # Seen from the other project it is its own, and this project's plain lesson is not listed there.
        there = self.index(COMPOUND_PROJECT=other, cwd=other)
        self.assertEqual([(row["name"], row.get("project")) for row in there],
                         [("check-built-site", None), ("other-plain", None)])

    def test_show_prints_another_projects_lesson_by_the_name_the_index_gave(self):
        other = os.path.join(self.box.root, "other-project")
        os.makedirs(other)
        self.box.add("check-built-site", "Use when the docs site was rebuilt.", "Run tool.sh on the build.\n",
                     "--attach", self.tool(), "--unrun", COMPOUND_PROJECT=other, cwd=other)
        directory = os.path.join(other, ".claude", "compound", "lessons", "check-built-site")
        proc = self.box.run("show", "check-built-site")
        self.assertExit(proc, 0)
        self.assertIn(directory, proc.stdout)
        self.assertIn("a lesson of another project, %s" % other, proc.stdout)
        self.assertIn("attached: tool.sh", proc.stdout)
        self.assertIn("Run tool.sh on the build.", proc.stdout)
        shown = self.box.json("show", "check-built-site", "--json")
        self.assertEqual((shown["project"], shown["path"], shown["files"]), (other, directory, ["tool.sh"]))
        # It is read, not adopted: it is no lesson of this project, and nothing here changes.
        self.assertEqual(self.box.json("list", "--json"), [])
        self.assertExit(self.box.run("rm", "check-built-site"), 2)
        self.assertExit(self.box.run("show", "no-such-lesson-anywhere"), 2)
        self.assertExit(self.box.run("show", "../../etc"), 2)

    def test_a_name_this_project_holds_is_not_listed_twice_and_a_gone_project_is_passed_over(self):
        other = os.path.join(self.box.root, "other-project")
        os.makedirs(other)
        self.box.add("shared-name", "Use when in the other project.", "Run tool.sh.\n", "--attach", self.tool(),
                     "--unrun", COMPOUND_PROJECT=other, cwd=other)
        self.box.add("shared-name", "Use when here.", "Body.\n")
        self.assertEqual([(row["name"], row.get("project")) for row in self.index()], [("shared-name", None)])
        gone = os.path.join(self.box.root, "gone-project")
        os.makedirs(gone)
        self.box.add("left-behind", "Use when gone.", "Run tool.sh.\n", "--attach", self.tool(), "--unrun",
                     COMPOUND_PROJECT=gone, cwd=gone)
        import shutil
        shutil.rmtree(gone)
        self.assertEqual([row["name"] for row in self.index()], ["shared-name"])

    def test_a_skill_and_a_lesson_not_in_force_are_not_listed(self):
        self.box.add("for-linux", "Use when on linux.", "Body.\n", "--platform", "linux")
        self.box.add("becomes-skill", "Use when a skill.", "Step one.\n")
        self.assertExit(self.box.run("skill", "becomes-skill"), 0)
        self.box.add("stays", "Use when it stays.", "Body.\n")
        self.assertEqual([row["name"] for row in self.index(COMPOUND_PLATFORM="darwin")], ["stays"])
        self.assertEqual(sorted(row["name"] for row in self.index(COMPOUND_PLATFORM="linux")), ["for-linux", "stays"])

    def test_it_writes_nothing(self):
        self.box.add("stays", "Use when it stays.", "Body.\n")
        before = self.box.snapshot()
        self.index(COMPOUND_NOW=NOW + 60)
        self.assertEqual(self.box.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
