#!/usr/bin/env python3
"""update: a real upstream repository, a real clone of it, a real `git pull --ff-only`."""

import json
import os
import shutil
import unittest

from test_support import Case, git, git_ok

LESSON = "---\nname: %s\ndescription: Use when shipped.\n---\n%s\n"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(text)


def read(path):
    with open(path) as handle:
        return handle.read()


class UpstreamCase(Case):
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


class UpdateTest(UpstreamCase):
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
        write(os.path.join(self.upstream, "lessons", "now-general", "helper.sh"), "# attached\n")
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

    def test_a_user_skill_the_pool_now_carries_is_never_removed(self):
        """Until the review of 2026-10-03 it was removed. <claude dir>/skills holds the
        user's own skills and other tools' too, so nothing under it is a candidate."""
        path = os.path.join(self.box.skill_dir("now-shipped", "user"), "SKILL.md")
        write(path, LESSON % ("now-shipped", "Steps."))
        write(os.path.join(self.upstream, "skills", "now-shipped", "SKILL.md"), LESSON % ("now-shipped", "Steps."))
        self.commit("ship the skill")
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertEqual(read(path), LESSON % ("now-shipped", "Steps."))
        self.assertNotIn("removed", proc.stdout)

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


class ReleaseUpdateTest(UpstreamCase):
    """A checkout at a release tag moves to the newest release; a branch keeps pulling."""

    def release(self, tag, text=None):
        write(os.path.join(self.upstream, "VERSION"), "%s\n" % (text or tag or "tip"))
        sha = self.commit(tag or "not a release")
        if tag:
            git_ok("tag", tag, cwd=self.upstream)
        return sha

    def at(self, ref):
        """Put the clone where install.sh leaves it for a tag: fetched, detached at it."""
        git_ok("fetch", "-q", "--tags", "origin", cwd=self.clone)
        git_ok("-c", "advice.detachedHead=false", "checkout", "-q", "--detach", ref, cwd=self.clone)

    def version(self):
        return read(os.path.join(self.clone, "VERSION")).strip()

    def head(self):
        return git_ok("rev-parse", "--short", "HEAD", cwd=self.clone)

    def test_on_a_release_tag_update_moves_to_the_newest_release(self):
        """Compared as numbers: 0.10.0 is newer than 0.9.0. Not vX.Y.Z, or older than 0.4.0:
        never picked. main's tip, which is past the last release, is not used."""
        old = self.release("v0.4.0")
        self.at("v0.4.0")
        self.release("v0.10.0")
        new = git_ok("rev-parse", "--short", "HEAD", cwd=self.upstream)
        for tag in ("v0.9.0", "v1.0.0-rc1", "nightly", "v0.3.9"):
            self.release(tag)
        self.release(None)
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(self.version(), "v0.10.0")
        self.assertEqual(self.head(), new)
        self.assertIn("updated v0.4.0 -> v0.10.0 (%s -> %s)" % (old, new), proc.stdout)
        code = git("symbolic-ref", "-q", "HEAD", cwd=self.clone).returncode
        self.assertNotEqual(code, 0, "the checkout stays at a tag, on no branch")

    def test_on_the_newest_release_update_says_so(self):
        sha = self.release("v0.4.0")
        self.release(None)
        self.at("v0.4.0")
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertEqual(proc.stderr, "")
        self.assertIn("already the newest release: v0.4.0 (%s)" % sha, proc.stdout)
        data = json.loads(self.update("--json").stdout)
        self.assertEqual((data["old"], data["new"], data["changed"], data["old_ref"], data["ref"]),
                         (sha, sha, False, "v0.4.0", "v0.4.0"))

    def test_json_names_the_release_it_moved_from_and_to(self):
        self.release("v0.4.0")
        self.at("v0.4.0")
        self.release("v0.4.1")
        data = json.loads(self.update("--json").stdout)
        self.assertEqual((data["old_ref"], data["ref"], data["changed"]), ("v0.4.0", "v0.4.1", True))

    def test_an_annotated_release_tag_is_followed(self):
        self.release("v0.4.0")
        self.at("v0.4.0")
        self.release(None, "annotated")
        git_ok("tag", "-a", "v0.5.0", "-m", "release 0.5.0", cwd=self.upstream)
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertEqual(self.version(), "annotated")
        self.assertIn("v0.4.0 -> v0.5.0", proc.stdout)
        self.assertIn("already the newest release: v0.5.0", self.update().stdout)

    def test_a_user_lesson_the_new_release_carries_is_removed(self):
        self.release("v0.4.0")
        self.at("v0.4.0")
        mine = self.user_lesson("now-general", "The same text.")
        write(os.path.join(self.upstream, "lessons", "now-general", "SKILL.md"), read(mine))
        self.release("v0.4.1")
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(mine))
        self.assertIn("removed user lesson now-general", proc.stdout)

    def test_on_a_branch_update_keeps_pulling_and_ignores_releases(self):
        self.release("v0.4.0")
        self.assertExit(self.update(), 0)
        tip = self.release(None, "past the release")
        proc = self.update()
        self.assertExit(proc, 0)
        self.assertEqual(self.version(), "past the release")
        self.assertIn("-> %s" % tip, proc.stdout)
        self.assertEqual(git_ok("symbolic-ref", "--short", "HEAD", cwd=self.clone), "main")

    def test_ref_main_leaves_the_releases_for_the_tip_and_update_then_pulls(self):
        self.release("v0.4.0")
        self.at("v0.4.0")
        self.release(None, "the tip")
        proc = self.update("--ref", "main")
        self.assertExit(proc, 0)
        self.assertEqual(self.version(), "the tip")
        self.assertEqual(git_ok("symbolic-ref", "--short", "HEAD", cwd=self.clone), "main")
        self.assertIn("v0.4.0 -> main", proc.stdout)
        self.release("v0.4.1")
        self.release(None, "a newer tip")
        self.assertExit(self.update(), 0)
        self.assertEqual(self.version(), "a newer tip", "on a branch, update follows the branch")

    def test_ref_names_a_release_to_move_to(self):
        self.release("v0.4.0")
        self.release("v0.4.1")
        self.release(None)
        proc = self.update("--ref", "v0.4.0")
        self.assertExit(proc, 0)
        self.assertEqual(self.version(), "v0.4.0")
        self.assertIn("main -> v0.4.0", proc.stdout)
        # From there a plain update follows the releases.
        self.assertExit(self.update(), 0)
        self.assertEqual(self.version(), "v0.4.1")

    def test_a_ref_that_origin_does_not_have_fails_and_moves_nothing(self):
        self.release("v0.4.0")
        self.at("v0.4.0")
        before = self.head()
        proc = self.update("--ref", "no-such-ref")
        self.assertExit(proc, 1)
        self.assertIn("no-such-ref", proc.stderr)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1)
        self.assertEqual(self.head(), before)

    def test_detached_with_no_release_to_move_to_says_how_to_follow_a_branch(self):
        self.release("v0.3.1")
        self.at("v0.3.1")
        proc = self.update()
        self.assertExit(proc, 1)
        self.assertIn("--ref main", proc.stderr)
        self.assertIn("0.4.0", proc.stderr)
        self.assertEqual(self.version(), "v0.3.1")


if __name__ == "__main__":
    unittest.main()
