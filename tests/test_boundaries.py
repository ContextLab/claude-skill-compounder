#!/usr/bin/env python3
"""Where the CLI reads and writes, and where it publishes: the edges a link, a name or
the environment could move.

A repository chooses what `<repo>/.claude` is: a directory, or a symbolic link to
anywhere. The project level is read and written inside the project and nowhere else. The
repository that `promote --to general` clones chooses what its `lessons` is. A project
skill carries any name. And the environment says where `promote --to general --yes`
publishes. Each test builds the real files and runs the real CLI.
"""

import json
import os
import subprocess
import sys
import unittest

from test_support import Case, git_ok


def call(command, tool="Bash"):
    return json.dumps({"tool": tool, "input": {"command": command}})


class BoundaryCase(Case):
    def check(self, command):
        proc = subprocess.run([sys.executable, self.box.script, "check", "--guards"], input=call(command),
                              cwd=self.box.project, env=self.box.env(), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, timeout=30)
        self.assertExit(proc, 0)
        return json.loads(proc.stdout)

    def hand_written(self, directory, name, match=None, body="A hand-written body.\n"):
        extra = "" if match is None else "match: %s\n" % json.dumps(match)
        self.box.write_lesson(directory, json.dumps(name), "Use when written by hand.", body, extra)

    def names(self, *flags):
        return [(row["level"], row["kind"], row["name"]) for row in self.box.json("list", "--json", *flags)]

    def parse_check(self):
        status = self.box.run("status", "--json")
        return [row for row in json.loads(status.stdout)["health"] if row["check"] == "lessons parse"][0]


class LinkedStoreTest(BoundaryCase):
    """The project level is inside the project. A `.claude`, a `.claude/compound/lessons`
    or a `.claude/skills` that is a symbolic link out of the repository is not read, not
    written through and not removed through."""

    def setUp(self):
        BoundaryCase.setUp(self)
        # A directory that is not the project's: another checkout, a plugin's skills, a
        # folder of the user's. It holds one well-formed lesson directory.
        self.outside = os.path.join(self.box.root, "outside")
        self.victim = os.path.join(self.outside, "victim-note")
        self.hand_written(self.victim, "victim-note", match=["danger"])
        with open(os.path.join(self.victim, "keep.txt"), "w") as handle:
            handle.write("the user's own file\n")

    def link(self, rel, target=None):
        path = os.path.join(self.box.project, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(target or self.outside, path)
        return path

    def assert_outside_untouched(self, extra=()):
        self.assertEqual(sorted(os.listdir(self.outside)), sorted(["victim-note"] + list(extra)))
        self.assertEqual(sorted(os.listdir(self.victim)), ["SKILL.md", "keep.txt"])

    def test_a_lessons_directory_that_is_a_link_out_of_the_project_is_not_read(self):
        link = self.link(os.path.join(".claude", "compound", "lessons"))
        self.assertEqual(self.names(), [])
        reply = self.check("run danger now")
        self.assertEqual((reply["hits"], reply["guards"]), ([], 0))
        self.assertExit(self.box.run("show", "victim-note"), 2)
        self.assertEqual(self.box.json("find", "written", "hand", "--json")["items"], [])
        row = self.parse_check()
        self.assertEqual(row["status"], "FAIL")
        self.assertIn(link, row["detail"])
        self.assertIn("leaves the project", row["detail"])

    def test_nothing_is_removed_through_such_a_link(self):
        self.link(os.path.join(".claude", "compound", "lessons"))
        for flags in ((), ("--force",)):
            proc = self.box.run("rm", "victim-note", *flags)
            self.assertExit(proc, 2)
            self.assert_outside_untouched()
        self.assertFalse(any(event["type"] == "rm" for event in self.box.read_events()))

    def test_nothing_is_written_through_such_a_link(self):
        link = self.link(os.path.join(".claude", "compound", "lessons"))
        proc = self.box.run("add", "--name", "new-note", "--when", "Use when new.", "--level", "project",
                            stdin="A body.\n")
        self.assertExit(proc, 2)
        self.assertIn(link, proc.stderr)
        self.assertIn("leaves the project", proc.stderr)
        self.assert_outside_untouched()
        self.assertEqual(self.box.read_events(), [])

    def test_a_claude_directory_that_is_a_link_out_is_the_same(self):
        store = os.path.join(self.outside, "compound", "lessons", "far-note")
        self.hand_written(store, "far-note", match=["danger"])
        self.link(".claude")
        self.assertEqual(self.names(), [])
        self.assertEqual(self.check("run danger now")["hits"], [])
        self.assertExit(self.box.run("rm", "far-note"), 2)
        self.assertTrue(os.path.isfile(os.path.join(store, "SKILL.md")))
        proc = self.box.run("add", "--name", "new-note", "--when", "Use when new.", "--level", "project",
                            stdin="A body.\n")
        self.assertExit(proc, 2)
        self.assertEqual(os.listdir(os.path.join(self.outside, "compound", "lessons")), ["far-note"])

    def test_a_skills_directory_that_is_a_link_out_is_not_read_and_takes_no_lesson(self):
        self.box.add("real-note", "Use when real.", "Body.\n", "--level", "project")
        self.link(os.path.join(".claude", "skills"))
        self.assertEqual(self.names(), [("project", "lesson", "real-note")])
        self.assertEqual(self.check("run danger now")["hits"], [])
        self.assertExit(self.box.run("rm", "victim-note", "--force"), 2)
        proc = self.box.run("skill", "real-note")
        self.assertExit(proc, 2)
        self.assertIn("leaves the project", proc.stderr)
        self.assert_outside_untouched()
        self.assertTrue(os.path.isdir(self.box.lesson_dir("real-note")))

    def test_one_project_skill_that_is_a_link_out_is_not_read_and_its_target_is_never_removed(self):
        os.makedirs(os.path.join(self.box.project, ".claude", "skills"))
        os.symlink(self.victim, self.box.skill_dir("victim-note"))
        self.assertEqual(self.names(), [])
        self.assertEqual(self.check("run danger now")["hits"], [])
        self.box.run("rm", "victim-note", "--force")
        self.assert_outside_untouched()
        proc = self.box.run("promote", "victim-note", "--to", "user")
        self.assertExit(proc, 2)
        self.assert_outside_untouched()
        self.assertFalse(os.path.lexists(self.box.skill_dir("victim-note", "user")))

    def test_a_link_that_stays_inside_the_project_is_the_projects_own(self):
        """Control: the rule is about leaving the project, not about links."""
        shared = os.path.join(self.box.project, "shared-lessons")
        self.hand_written(os.path.join(shared, "inside-note"), "inside-note", match=["danger"])
        self.link(os.path.join(".claude", "compound", "lessons"), shared)
        self.assertEqual(self.names(), [("project", "lesson", "inside-note")])
        self.assertEqual([hit["name"] for hit in self.check("run danger now")["hits"]], ["inside-note"])
        self.box.add("second-note", "Use when second.", "Body.\n", "--level", "project")
        self.assertTrue(os.path.isfile(os.path.join(shared, "second-note", "SKILL.md")))
        self.assertEqual(self.parse_check()["status"], "PASS")

    def test_the_user_store_seen_as_a_project_is_still_one_store(self):
        """Control: from the home directory the 'project' store is the user's own, also when
        `~/.claude` is itself a link (a dotfiles checkout). It is read once, as the user's,
        and nothing is reported."""
        dotfiles = os.path.join(self.box.root, "dotfiles-claude")
        os.rename(self.box.claude, dotfiles)
        os.symlink(dotfiles, self.box.claude)
        self.box.add("home-note", "Use when at home.", "Body.\n", "--level", "user", COMPOUND_PROJECT=self.box.home)
        rows = self.box.json("list", "--json", COMPOUND_PROJECT=self.box.home)
        self.assertEqual([(row["level"], row["name"]) for row in rows], [("user", "home-note")])
        status = json.loads(self.box.run("status", "--json", COMPOUND_PROJECT=self.box.home).stdout)
        row = [one for one in status["health"] if one["check"] == "lessons parse"][0]
        self.assertEqual(row["status"], "PASS", row)


class ShadowedSkillTest(BoundaryCase):
    """A project SKILL is a file in the repository like a project lesson. One that takes the
    name of a user or general lesson or skill is shadowed: no guard, and not what `show`
    prints for the name."""

    def project_skill(self, name, match):
        self.hand_written(self.box.skill_dir(name), name, match=match, body="The repository's text.\n")

    def test_a_project_skill_named_like_the_users_guard_is_no_guard(self):
        self.box.add("my-guard", "Use when mine.", "Mine.\n", "--level", "user", "--match", "danger")
        self.project_skill("my-guard", ["^ls"])
        reply = self.check("ls")
        self.assertEqual(reply["hits"], [], "the repository's skill refused a call under the user's guard's name")
        self.assertEqual(reply["guards"], 1)
        self.assertEqual([(hit["level"], hit["name"]) for hit in self.check("run danger now")["hits"]],
                         [("user", "my-guard")])
        shown = self.box.run("show", "my-guard")
        self.assertExit(shown, 0)
        self.assertIn("Mine.", shown.stdout)
        self.assertNotIn("The repository's text.", shown.stdout)
        rows = {(row["level"], row["kind"]): row for row in self.box.json("list", "--json") if row["name"] == "my-guard"}
        self.assertTrue(rows[("project", "skill")].get("shadowed"))
        self.assertFalse(rows[("user", "lesson")].get("shadowed"))

    def test_a_project_lesson_named_like_a_users_skill_is_shadowed_too(self):
        self.box.add("my-steps", "Use when mine.", "Mine.\n", "--level", "user", "--match", "danger")
        self.assertExit(self.box.run("skill", "my-steps"), 0)
        self.hand_written(self.box.lesson_dir("my-steps"), "my-steps", match=["^ls"], body="The repository's text.\n")
        self.assertEqual(self.check("ls")["hits"], [])
        self.assertEqual([(hit["level"], hit["name"]) for hit in self.check("run danger now")["hits"]],
                         [("user", "my-steps")])
        self.assertIn("Mine.", self.box.run("show", "my-steps").stdout)

    def test_a_project_skill_named_like_a_general_lesson_is_shadowed(self):
        self.hand_written(self.box.lesson_dir("pool-guard", "general"), "pool-guard", match=["danger"])
        self.project_skill("pool-guard", ["^ls"])
        self.assertEqual(self.check("ls")["hits"], [])
        self.assertEqual([(hit["level"], hit["name"]) for hit in self.check("run danger now")["hits"]],
                         [("general", "pool-guard")])

    def test_a_project_skill_with_a_name_of_its_own_is_a_guard_as_before(self):
        """Control."""
        self.box.add("my-guard", "Use when mine.", "Mine.\n", "--level", "user", "--match", "danger")
        self.project_skill("repo-steps", ["^ls"])
        self.assertEqual([(hit["level"], hit["name"]) for hit in self.check("ls")["hits"]], [("project", "repo-steps")])


class PoolCase(BoundaryCase):
    """A pool to publish to: a local bare repository, so nothing here goes to GitHub."""

    KEY = "ghp_" + "A1b2C3d4E5" * 3

    def setUp(self):
        BoundaryCase.setUp(self)
        self.git_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
                        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}

    def pool(self, name, build):
        seedrepo = os.path.join(self.box.root, name + "-seed")
        os.makedirs(seedrepo)
        build(seedrepo)
        git_ok("init", cwd=seedrepo)
        git_ok("add", "-A", cwd=seedrepo)
        git_ok("commit", "-m", "the pool", cwd=seedrepo)
        upstream = os.path.join(self.box.root, name + ".git")
        git_ok("clone", "--bare", seedrepo, upstream)
        return upstream

    def plain_pool(self, name="upstream"):
        def build(seedrepo):
            os.makedirs(os.path.join(seedrepo, "lessons"))
            with open(os.path.join(seedrepo, "lessons", ".gitkeep"), "w") as handle:
                handle.write("")
        return self.pool(name, build)

    def branches(self, upstream):
        return git_ok("branch", "--list", "--format=%(refname:short)", cwd=upstream).split()

    def attach(self, name, data):
        path = os.path.join(self.box.root, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path


class PoolLinkTest(PoolCase):
    """The repository that is cloned chooses what its `lessons` is. A pool whose `lessons`
    (or `skills`) is a symbolic link takes nothing: the lesson is not written where the
    link leads."""

    def test_a_pool_whose_lessons_is_a_link_out_of_the_clone_gets_nothing_written_through_it(self):
        landing = os.path.join(self.box.root, "landing")
        os.makedirs(landing)
        upstream = self.pool("hostile", lambda seedrepo: os.symlink(landing, os.path.join(seedrepo, "lessons")))
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user")
        proc = self.box.run("promote", "plain-note", "--to", "general", "--yes", "--upstream", upstream,
                            COMPOUND_UPSTREAM_GIT=upstream, **self.git_env)
        self.assertEqual(os.listdir(landing), [], "the lesson was written outside the clone")
        self.assertExit(proc, 1)
        self.assertIn("symbolic link", proc.stderr)
        self.assertEqual(self.branches(upstream), ["main"])
        self.assertFalse(any(event["type"] == "promote" for event in self.box.read_events()))

    def test_a_pool_whose_lesson_name_is_a_dangling_link_gets_nothing_written_through_it(self):
        landing = os.path.join(self.box.root, "landing")

        def build(seedrepo):
            os.makedirs(os.path.join(seedrepo, "lessons"))
            os.symlink(landing, os.path.join(seedrepo, "lessons", "plain-note"))
        upstream = self.pool("dangling", build)
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user")
        proc = self.box.run("promote", "plain-note", "--to", "general", "--yes", "--upstream", upstream,
                            COMPOUND_UPSTREAM_GIT=upstream, **self.git_env)
        self.assertFalse(os.path.lexists(landing), "the lesson was written where the link leads")
        self.assertExit(proc, 1)
        self.assertEqual(self.branches(upstream), ["main"])


class DestinationTest(PoolCase):
    """Where `promote --to general --yes` publishes is the package's own pool unless the
    environment names another place, and the environment alone is not enough: a
    destination that is not the default is published to only when the command line names
    it too, word for word."""

    def test_a_destination_from_the_environment_alone_is_not_published_to(self):
        upstream = self.plain_pool()
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user")
        proc = self.box.run("promote", "plain-note", "--to", "general", "--yes", COMPOUND_UPSTREAM_GIT=upstream,
                            **self.git_env)
        self.assertEqual(self.branches(upstream), ["main"], "it was published where only the environment said")
        self.assertExit(proc, 2)
        self.assertIn(upstream, proc.stderr)
        self.assertIn("--upstream", proc.stderr)
        self.assertIn("COMPOUND_UPSTREAM_GIT", proc.stderr)
        self.assertFalse(any(event["type"] == "promote" for event in self.box.read_events()))

    def test_the_same_holds_for_an_owner_and_repository_from_the_environment(self):
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user")
        proc = self.box.run("promote", "plain-note", "--to", "general", "--yes", COMPOUND_UPSTREAM="someone/their-fork",
                            PATH="")
        self.assertExit(proc, 2)
        self.assertIn("someone/their-fork", proc.stderr)
        self.assertIn("--upstream someone/their-fork", proc.stderr)
        self.assertNotIn("`gh` is not on PATH", proc.stderr, "it went on toward publishing")

    def test_named_on_the_command_line_too_it_is_published_there(self):
        upstream = self.plain_pool()
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user")
        proc = self.box.run("promote", "plain-note", "--to", "general", "--yes", "--upstream", upstream, "--json",
                            COMPOUND_UPSTREAM_GIT=upstream, **self.git_env)
        self.assertExit(proc, 0)
        self.assertEqual(sorted(self.branches(upstream)), ["compound/lesson-plain-note", "main"])
        self.assertEqual(json.loads(proc.stdout)["url"], "%s#compound/lesson-plain-note" % upstream)

    def test_a_command_line_that_names_another_place_than_the_environment_is_refused(self):
        upstream = self.plain_pool()
        other = self.plain_pool("other")
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user")
        for flags, env in ((("--upstream", other), {"COMPOUND_UPSTREAM_GIT": upstream}),
                           (("--upstream", "someone/their-fork"), {})):
            proc = self.box.run("promote", "plain-note", "--to", "general", "--yes", *flags,
                                **dict(self.git_env, **env))
            self.assertExit(proc, 2)
            self.assertIn("--upstream", proc.stderr)
        self.assertEqual((self.branches(upstream), self.branches(other)), (["main"], ["main"]))

    def test_the_plan_says_where_and_how_to_confirm_it(self):
        upstream = self.plain_pool()
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user")
        plan = self.box.json("promote", "plain-note", "--to", "general", "--json", COMPOUND_UPSTREAM_GIT=upstream)
        self.assertEqual((plan["upstream"], plan["confirm"]), (upstream, ["--upstream", upstream]))
        text = self.box.run("promote", "plain-note", "--to", "general", COMPOUND_UPSTREAM_GIT=upstream).stdout
        self.assertIn("NOT the package's own pool", text)
        self.assertIn("--upstream", text)
        plain = self.box.json("promote", "plain-note", "--to", "general", "--json")
        self.assertEqual((plain["upstream"], plain["confirm"]), ("ContextLab/claude-skill-compounder", []))

    def test_upstream_goes_with_general_only(self):
        self.box.add("proj-note", "Use when in the project.", "Body.\n", "--level", "project")
        proc = self.box.run("promote", "proj-note", "--to", "user", "--upstream", "someone/their-fork")
        self.assertExit(proc, 2)
        self.assertTrue(os.path.isdir(self.box.lesson_dir("proj-note")))


class PublishScanEdgesTest(PoolCase):
    """What the credential scan of `promote --to general` reads beyond a file's UTF-8 text:
    the name of each file, which is published too, and text in a two-byte encoding."""

    PEM = "-----BEGIN OPENSSH " + "PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH " + "PRIVATE KEY-----\n"

    def refused(self, name, label):
        plan = self.box.json("promote", name, "--to", "general", "--json")
        self.assertEqual(len(plan["secrets"]), 1, plan["secrets"])
        self.assertIn(label, plan["secrets"][0])
        self.assertNotIn(self.KEY, json.dumps(plan["secrets"]))
        upstream = self.plain_pool()
        proc = self.box.run("promote", name, "--to", "general", "--yes", "--upstream", upstream,
                            COMPOUND_UPSTREAM_GIT=upstream, **self.git_env)
        self.assertExit(proc, 2)
        self.assertIn("credential", proc.stderr)
        self.assertNotIn(self.KEY, proc.stderr)
        self.assertEqual(self.branches(upstream), ["main"])

    def test_a_credential_in_a_file_name_is_found(self):
        helper = self.attach("notes-%s.txt" % self.KEY, b"nothing in the file itself\n")
        self.box.add("named-note", "Use when named.", "Body.\n", "--level", "user", "--attach", helper)
        self.refused("named-note", "an API token")

    def test_a_private_key_in_utf16_is_found(self):
        for index, encoding in enumerate(("utf-16", "utf-16-le", "utf-16-be")):
            name = "wide-note-%d" % index
            helper = self.attach("key-%d.txt" % index, self.PEM.encode(encoding))
            self.box.add(name, "Use when wide %d." % index, "Body number %d.\n" % index, "--level", "user",
                         "--attach", helper, "--new")
            plan = self.box.json("promote", name, "--to", "general", "--json")
            self.assertEqual(plan["secrets"], ["key-%d.txt: a private key" % index], encoding)

    def test_a_binary_file_with_no_credential_is_still_publishable(self):
        """Control: zero bytes alone are nothing."""
        helper = self.attach("table.bin", bytes(range(256)) * 64)
        self.box.add("binary-note", "Use when binary.", "Body.\n", "--level", "user", "--attach", helper)
        plan = self.box.json("promote", "binary-note", "--to", "general", "--json")
        self.assertEqual((plan["secrets"], plan["unpublishable"]), ([], []))


class FoundByFieldsTest(BoundaryCase):
    """The fields an event is found by are written as they are, so that an event is not
    lost to the mask. They are not a way around it: a credential's shape in one of them is
    masked like anywhere else."""

    TOKEN = "ghp_" + "Z9y8X7w6V5" * 3
    PASSWORD = "hunter2" + "Secret9"

    def logged(self, event):
        proc = self.box.run("log", "--json", stdin=json.dumps(event))
        self.assertExit(proc, 0)
        with open(self.box.events, encoding="utf-8") as handle:
            text = handle.read()
        return json.loads(proc.stdout), text

    def test_a_token_in_a_field_an_event_is_found_by_is_masked(self):
        url = "https://deploy:%s@git.example.invalid/team/repo" % self.PASSWORD
        printed, text = self.logged({"type": "error", "where": "x", "message": "m", "lesson": self.TOKEN,
                                     "lessons": ["fine-name", self.TOKEN], "id": self.TOKEN, "session": self.TOKEN,
                                     "settles": self.TOKEN, "kind": self.TOKEN, "level": self.TOKEN,
                                     "path": url, "project": url, "from": url, "seen_in": url,
                                     "also": [url], "merged": [url]})
        for secret in (self.TOKEN, self.PASSWORD):
            self.assertNotIn(secret, text)
            self.assertNotIn(secret, json.dumps(printed))
        self.assertEqual(printed["lessons"][0], "fine-name")

    def test_what_such_a_field_ordinarily_holds_is_written_as_it_is(self):
        """Control: a path, a lesson's name, an id and a session are not free text, and a
        name that only looks like the start of a key is a name."""
        project = os.path.join(self.box.root, "sk-" + "learn-experiments-2026", "my_KEY=value dir")
        name = "sk-" + "learn-pipeline-pickle"  # in halves: no key-shaped literal in the repository
        event = {"type": "recall", "lesson": name, "lessons": [name],
                 "level": "project", "path": os.path.join(project, ".claude", "compound", "lessons", "x-note"),
                 "project": project, "session": "0d5c9f1e-7a42-4b8e-9c1d-3f2a91c0b6e4", "from": "project",
                 "seen_in": project, "also": [project], "merged": [project], "id": "ab12cd34", "settles": "ab12cd34",
                 "kind": "lesson", "tool": "Bash", "call": "x", "error": "e"}
        printed, _text = self.logged(event)
        for key in ("lesson", "lessons", "level", "path", "project", "session", "from", "seen_in", "also", "merged",
                    "id", "settles", "kind"):
            self.assertEqual(printed[key], event[key], key)


if __name__ == "__main__":
    unittest.main()
