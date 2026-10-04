#!/usr/bin/env python3
"""update: a real upstream repository, a real clone of it, a real `git pull --ff-only`."""

import json
import os
import shutil
import unittest

from test_support import Case, git_ok

LESSON = "---\nname: %s\ndescription: Use when shipped.\n---\n%s\n"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(text)


def read(path):
    with open(path) as handle:
        return handle.read()


class UpdateTest(Case):
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
        return git_ok("rev-parse", "--short", "HEAD", cwd=self.upstream)

    def update(self, *args):
        return self.box.run("update", *args, script=self.script)

    def user_lesson(self, name, body):
        path = os.path.join(self.box.lesson_dir(name, "user"), "SKILL.md")
        write(path, LESSON % (name, body))
        return path

    def test_update_pulls_and_reports_old_and_new(self):
        old = git_ok("rev-parse", "--short", "HEAD", cwd=self.clone)
        write(os.path.join(self.upstream, "lessons", "shipped", "SKILL.md"), LESSON % ("shipped", "Body."))
        new = self.commit("add a general lesson")
        self.assertNotEqual(old, new)
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertIn("updated %s -> %s" % (old, new), proc.stdout)
        self.assertEqual(git_ok("rev-parse", "--short", "HEAD", cwd=self.clone), new)
        self.assertTrue(os.path.isfile(os.path.join(self.clone, "lessons", "shipped", "SKILL.md")))

    def test_update_with_nothing_new_says_so(self):
        sha = git_ok("rev-parse", "--short", "HEAD", cwd=self.clone)
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertIn("already up to date at %s" % sha, proc.stdout)
        data = json.loads(self.update("--json").stdout)
        self.assertEqual((data["old"], data["new"], data["changed"], data["removed"], data["differing"]),
                         (sha, sha, False, [], []))

    def test_a_user_lesson_the_pool_now_carries_is_removed(self):
        mine = self.user_lesson("now-general", "The same text.")
        write(os.path.join(self.box.lesson_dir("now-general", "user"), "helper.sh"), "# attached\n")
        other = self.user_lesson("still-mine", "Only mine.")
        write(os.path.join(self.upstream, "lessons", "now-general", "SKILL.md"), read(mine))
        self.commit("merge the promoted lesson")
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.box.lesson_dir("now-general", "user")),
                         "the pool is the only copy now")
        self.assertTrue(os.path.isfile(other))
        self.assertIn("removed user lesson now-general", proc.stdout)
        rows = json.loads(self.box.run("list", "--json", script=self.script).stdout)
        self.assertEqual([(row["level"], row["name"]) for row in rows if row["kind"] == "lesson"],
                         [("user", "still-mine"), ("general", "now-general")])

    def test_a_same_name_lesson_with_different_text_is_reported_and_kept(self):
        mine = self.user_lesson("diverged", "My wording.")
        write(os.path.join(self.upstream, "lessons", "diverged", "SKILL.md"), LESSON % ("diverged", "Their wording."))
        self.commit("a lesson of the same name")
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertEqual(read(mine), LESSON % ("diverged", "My wording."))
        self.assertIn("kept user lesson diverged", proc.stdout)
        self.assertIn("different text", proc.stdout)
        data = json.loads(self.update("--json").stdout)
        self.assertEqual([row["name"] for row in data["differing"]], ["diverged"])
        self.assertEqual(data["removed"], [])

    def test_a_user_skill_the_pool_now_carries_is_removed_too(self):
        path = os.path.join(self.box.skill_dir("now-shipped", "user"), "SKILL.md")
        write(path, LESSON % ("now-shipped", "Steps."))
        write(os.path.join(self.upstream, "skills", "now-shipped", "SKILL.md"), LESSON % ("now-shipped", "Steps."))
        self.commit("ship the skill")
        self.assertExit(self.update(), 0)
        self.assertFalse(os.path.exists(self.box.skill_dir("now-shipped", "user")))

    def test_a_user_skill_that_is_a_link_into_the_package_is_not_removed(self):
        write(os.path.join(self.upstream, "skills", "linked", "SKILL.md"), LESSON % ("linked", "Steps."))
        self.commit("ship the skill")
        self.assertExit(self.update(), 0)
        os.makedirs(os.path.join(self.box.claude, "skills"))
        link = self.box.skill_dir("linked", "user")
        os.symlink(os.path.join(self.clone, "skills", "linked"), link)
        self.assertExit(self.update(), 0)
        self.assertTrue(os.path.islink(link))
        self.assertTrue(os.path.isfile(os.path.join(self.clone, "skills", "linked", "SKILL.md")))

    def test_a_project_lesson_is_never_touched(self):
        self.box.add("project-copy", "Use when shipped.", "Body.\n", script=self.script)
        text = read(os.path.join(self.box.lesson_dir("project-copy"), "SKILL.md"))
        write(os.path.join(self.upstream, "lessons", "project-copy", "SKILL.md"), text)
        self.commit("same text as a project lesson")
        self.assertExit(self.update(), 0)
        self.assertEqual(read(os.path.join(self.box.lesson_dir("project-copy"), "SKILL.md")), text)

    def test_a_package_that_is_not_a_git_checkout_fails(self):
        proc = self.box.run("update")
        self.assertExit(proc, 1)
        self.assertIn("not a git checkout", proc.stderr)

    def test_a_pull_that_cannot_fast_forward_fails_and_removes_nothing(self):
        mine = self.user_lesson("now-general", "The same text.")
        write(os.path.join(self.upstream, "lessons", "now-general", "SKILL.md"), read(mine))
        self.commit("upstream moves")
        write(os.path.join(self.clone, "local.txt"), "a local commit\n")
        git_ok("add", "-A", cwd=self.clone)
        git_ok("commit", "-q", "-m", "local", cwd=self.clone)
        proc = self.update()
        self.assertExit(proc, 1)
        self.assertIn("git pull --ff-only failed", proc.stderr)
        self.assertTrue(os.path.isfile(mine))


if __name__ == "__main__":
    unittest.main()
