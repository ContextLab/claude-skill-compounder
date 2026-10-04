#!/usr/bin/env python3
"""What one project's session may do to another's lessons, and what a session still owes.

  the automatic move (`promote --to user --auto`): only a lesson git does not track
  names: unique among what a session can see, and a move up that would break that
  status: whether the mod can run and when it last did, what is unsettled, what is open
  captures: their ids, what settles one, and `events --unsettled`
  install: a link the shell can find, or the line that makes it findable
"""

import json
import os
import re
import unittest

from test_support import NOW, REPO, Case, git_ok

DAY = 86400


def read(path):
    with open(path) as handle:
        return handle.read()


class TwoProjects(Case):
    """Project A (`self.a`) holds the lesson; the session runs in project B (`self.b`)."""

    def setUp(self):
        Case.setUp(self)
        self.a = os.path.join(self.box.root, "alpha")
        self.b = self.box.project
        os.makedirs(self.a)

    def lesson_in_a(self, name="shared", body="Run it the right way.\n"):
        self.box.add(name, "Use when it fails.", body, COMPOUND_PROJECT=self.a)
        return os.path.join(self.a, ".claude", "compound", "lessons", name)

    def auto(self, name="shared", *flags):
        return self.box.run("promote", name, "--to", "user", "--auto", "--seen-in", self.b, *flags,
                            COMPOUND_PROJECT=self.a)

    def status(self, **kw):
        proc = self.box.run("status", "--json", **kw)
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        return json.loads(proc.stdout)


class AutomaticMoveTest(TwoProjects):
    def commit_a(self):
        git_ok("init", cwd=self.a)
        git_ok("add", "-A", cwd=self.a)
        git_ok("commit", "-m", "the lesson", cwd=self.a)

    def test_a_lesson_git_tracks_is_never_moved_by_another_project(self):
        directory = self.lesson_in_a()
        self.commit_a()
        before = self.box.snapshot(self.a)
        proc = self.auto()
        self.assertExit(proc, 3)
        self.assertEqual(self.box.snapshot(self.a), before, "the other repository was changed")
        self.assertEqual(git_ok("status", "--porcelain", cwd=self.a), "")
        self.assertTrue(os.path.isfile(os.path.join(directory, "SKILL.md")))
        self.assertFalse(os.path.exists(self.box.lesson_dir("shared", "user")))
        command = "COMPOUND_PROJECT=%s compound promote shared --to user" % self.a
        self.assertIn(command, proc.stderr)
        event = self.box.read_events()[-1]
        self.assertEqual(event, {"ts": "2026-09-21T14:13:20Z", "type": "candidate", "session": "sess-0001-aaaa",
                                 "project": self.b, "lesson": "shared", "from": self.a, "seen_in": self.b})

    def test_the_refusal_as_json_carries_the_command(self):
        self.lesson_in_a()
        self.commit_a()
        proc = self.auto("shared", "--json")
        self.assertExit(proc, 3)
        data = json.loads(proc.stdout)
        self.assertEqual((data["moved"], data["name"], data["from"], data["seen_in"]),
                         (False, "shared", self.a, self.b))
        self.assertEqual(data["command"], "COMPOUND_PROJECT=%s compound promote shared --to user" % self.a)

    def test_a_candidate_is_logged_once_per_pair_of_projects(self):
        self.lesson_in_a()
        self.commit_a()
        self.assertExit(self.auto(), 3)
        self.assertExit(self.auto(), 3)
        self.assertEqual(len([e for e in self.box.read_events() if e["type"] == "candidate"]), 1)

    def test_an_untracked_lesson_in_a_repository_is_moved(self):
        directory = self.lesson_in_a()
        git_ok("init", cwd=self.a)
        proc = self.auto("shared", "--json")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(directory))
        target = self.box.lesson_dir("shared", "user")
        self.assertTrue(os.path.isfile(os.path.join(target, "SKILL.md")))
        self.assertEqual(json.loads(proc.stdout)["moved"], True)
        event = self.box.read_events()[-1]
        self.assertEqual(event, {"ts": "2026-09-21T14:13:20Z", "type": "promote", "session": "sess-0001-aaaa",
                                 "project": self.b, "lesson": "shared", "to": "user", "path": target,
                                 "from": self.a, "auto": True},
                         "the event belongs to the session's project and names the source as `from`")

    def test_an_ignored_lesson_is_moved(self):
        directory = self.lesson_in_a()
        with open(os.path.join(self.a, ".gitignore"), "w") as handle:
            handle.write(".claude/\n")
        git_ok("init", cwd=self.a)
        git_ok("add", "-A", cwd=self.a)
        git_ok("commit", "-m", "ignore it", cwd=self.a)
        self.assertExit(self.auto(), 0)
        self.assertFalse(os.path.exists(directory))

    def test_a_lesson_outside_any_repository_is_moved(self):
        directory = self.lesson_in_a()
        self.assertExit(self.auto(), 0)
        self.assertFalse(os.path.exists(directory))

    def test_the_user_can_still_move_a_tracked_lesson_by_hand(self):
        directory = self.lesson_in_a()
        self.commit_a()
        self.assertExit(self.auto(), 3)
        proc = self.box.run("promote", "shared", "--to", "user", COMPOUND_PROJECT=self.a)
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(directory))

    def test_auto_is_for_the_move_to_user_only(self):
        self.lesson_in_a()
        proc = self.box.run("promote", "shared", "--to", "general", "--auto", COMPOUND_PROJECT=self.a)
        self.assertExit(proc, 2)

    def test_status_lists_the_candidate_with_the_command_until_it_is_moved(self):
        self.lesson_in_a()
        self.commit_a()
        self.assertExit(self.auto(), 3)
        command = "COMPOUND_PROJECT=%s compound promote shared --to user" % self.a
        data = self.status()
        self.assertEqual(data["open"]["candidates"],
                         [{"lesson": "shared", "from": self.a, "seen_in": [self.b], "command": command}])
        opened = self.box.run("status").stdout.split("Open")[1]
        self.assertIn(command, opened)
        self.assertNotIn("nothing open", opened)
        self.assertExit(self.box.run("promote", "shared", "--to", "user", COMPOUND_PROJECT=self.a), 0)
        self.assertEqual(self.status()["open"]["candidates"], [])


class NamesTest(TwoProjects):
    def test_one_name_in_two_projects_is_allowed(self):
        self.lesson_in_a("same-name")
        self.box.add("same-name")

    def test_a_move_to_user_is_refused_while_another_project_holds_the_name(self):
        self.lesson_in_a("same-name")
        self.box.add("same-name", "Use when B.", "B's own lesson.\n")
        before = self.box.snapshot()
        proc = self.box.run("promote", "same-name", "--to", "user", COMPOUND_PROJECT=self.a)
        self.assertExit(proc, 2)
        self.assertEqual(self.box.snapshot(), before)
        self.assertIn(self.box.lesson_dir("same-name"), proc.stderr)
        self.assertIn("--as", proc.stderr)
        self.assertExit(self.auto("same-name"), 2)
        after = self.box.snapshot()
        log = os.path.relpath(self.box.events, self.box.root)
        self.assertEqual({key: value for key, value in after.items() if key != log},
                         {key: value for key, value in before.items() if key != log},
                         "an automatic move that is refused changes nothing but the event log")

    def test_the_refusal_prints_the_exact_as_command(self):
        self.lesson_in_a("same-name")
        self.box.add("same-name", "Use when B.", "B's own lesson.\n")
        command = "COMPOUND_PROJECT=%s compound promote same-name --to user --as NEWNAME" % self.a
        proc = self.box.run("promote", "same-name", "--to", "user", COMPOUND_PROJECT=self.a)
        self.assertExit(proc, 2)
        self.assertIn(command, proc.stderr)
        proc = self.auto("same-name", "--json")
        self.assertExit(proc, 2)
        self.assertIn(command, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual((data["moved"], data["candidate"], data["from"], data["command"]),
                         (False, True, self.a, command))
        self.assertEqual(data["conflict"], [self.box.lesson_dir("same-name")])

    def test_an_automatic_move_refused_for_its_name_is_a_candidate_in_open(self):
        self.lesson_in_a("same-name")
        self.box.add("same-name", "Use when B.", "B's own lesson.\n")
        gamma = os.path.join(self.box.root, "gamma")
        os.makedirs(gamma)
        for _ in range(2):
            proc = self.box.run("promote", "same-name", "--to", "user", "--auto", "--seen-in", gamma,
                                COMPOUND_PROJECT=self.a)
            self.assertExit(proc, 2)
        rows = [e for e in self.box.read_events() if e["type"] == "candidate"]
        self.assertEqual(len(rows), 1, "logged once per pair of projects")
        self.assertEqual((rows[0]["lesson"], rows[0]["from"], rows[0]["seen_in"], rows[0]["project"]),
                         ("same-name", self.a, gamma, gamma))
        command = "COMPOUND_PROJECT=%s compound promote same-name --to user --as NEWNAME" % self.a
        data = self.status()
        self.assertEqual(data["open"]["candidates"],
                         [{"lesson": "same-name", "from": self.a, "seen_in": [gamma], "command": command,
                           "conflict": [self.box.lesson_dir("same-name")]}])
        opened = self.box.run("status").stdout.split("Open")[1]
        line = [text for text in opened.splitlines() if "candidate" in text]
        self.assertEqual(len(line), 1, opened)
        self.assertIn(command, line[0])
        self.assertIn(self.box.lesson_dir("same-name"), line[0])
        self.assertNotIn("tracked by git", line[0], "this one was held back by its name, not by git")
        proc = self.box.run("promote", "same-name", "--to", "user", "--as", "alpha-same-name",
                            COMPOUND_PROJECT=self.a)
        self.assertExit(proc, 0)
        self.assertEqual(self.status()["open"]["candidates"], [])

    def test_as_renames_while_moving(self):
        directory = self.lesson_in_a("same-name", "A's lesson.\n")
        self.box.add("same-name", "Use when B.", "B's own lesson.\n")
        data = self.box.json("promote", "same-name", "--to", "user", "--as", "a-build-profile", "--json",
                             COMPOUND_PROJECT=self.a)
        target = self.box.lesson_dir("a-build-profile", "user")
        self.assertEqual((data["name"], data["was"], data["path"]), ("a-build-profile", "same-name", target))
        self.assertFalse(os.path.exists(directory))
        text = read(os.path.join(target, "SKILL.md"))
        self.assertIn("name: a-build-profile\n", text)
        self.assertIn("A's lesson.", text)
        rows = {(row["level"], row["name"]) for row in self.box.json("list", "--json")}
        self.assertEqual(rows, {("project", "same-name"), ("user", "a-build-profile")})
        event = self.box.read_events()[-1]
        self.assertEqual((event["type"], event["lesson"], event["was"]), ("promote", "a-build-profile", "same-name"))
        dup = [row for row in self.status()["health"] if row["check"] == "duplicates"][0]
        self.assertEqual(dup["status"], "PASS")

    def test_as_refuses_a_bad_or_taken_name(self):
        self.lesson_in_a("same-name")
        self.box.add("taken")
        before = self.box.snapshot()
        for new in ("Not A Slug", "taken"):
            proc = self.box.run("promote", "same-name", "--to", "user", "--as", new, COMPOUND_PROJECT=self.a)
            self.assertExit(proc, 2)
        self.assertExit(self.box.run("promote", "same-name", "--to", "general", "--as", "other",
                                     COMPOUND_PROJECT=self.a), 2)
        self.assertEqual(self.box.snapshot(), before)

    def test_add_at_the_user_level_is_refused_while_a_project_holds_the_name(self):
        directory = self.lesson_in_a("same-name")
        before = self.box.snapshot()
        proc = self.box.run("add", "--name", "same-name", "--when", "Use when.", "--level", "user", stdin="Body.\n")
        self.assertExit(proc, 2)
        self.assertIn(directory, proc.stderr)
        self.assertEqual(self.box.snapshot(), before)

    def test_a_project_whose_lesson_is_gone_holds_nothing(self):
        self.lesson_in_a("same-name")
        self.assertExit(self.box.run("rm", "same-name", COMPOUND_PROJECT=self.a), 0)
        self.box.add("same-name", "Use when.", "Body.\n", "--level", "user")

    def test_a_name_visible_at_project_and_user_fails_status_with_both_paths(self):
        self.box.add("twice")
        self.box.write_lesson(self.box.lesson_dir("twice", "user"), "twice")
        data = self.status()
        row = [row for row in data["health"] if row["check"] == "duplicates"][0]
        self.assertEqual(row["status"], "FAIL")
        self.assertIn(self.box.lesson_dir("twice"), row["detail"])
        self.assertIn(self.box.lesson_dir("twice", "user"), row["detail"])


class SameLessonTest(TwoProjects):
    """One lesson, byte for byte, under one name in two projects: alpha commits it, gamma
    holds an untracked copy. It is the same lesson, so a move up takes one copy."""

    def setUp(self):
        TwoProjects.setUp(self)
        self.gamma = os.path.join(self.box.root, "gamma")
        os.makedirs(self.gamma)
        self.in_a = self.lesson_in_a("shared")
        helper = os.path.join(self.in_a, "helper.sh")
        with open(helper, "w") as handle:
            handle.write("#!/bin/sh\necho right\n")
        git_ok("init", cwd=self.a)
        git_ok("add", "-A", cwd=self.a)
        git_ok("commit", "-m", "the lesson", cwd=self.a)
        self.in_gamma = os.path.join(self.gamma, ".claude", "compound", "lessons", "shared")
        import shutil
        shutil.copytree(self.in_a, self.in_gamma)
        self.box.log({"type": "learn", "lesson": "shared", "level": "project", "kind": "lesson",
                      "project": self.gamma, "path": self.in_gamma})
        self.user = self.box.lesson_dir("shared", "user")

    def user_lessons(self):
        return sorted(os.listdir(os.path.join(self.box.chome, "lessons")))

    def test_the_open_command_for_the_committed_copy_runs(self):
        """The automatic move leaves alpha's committed copy and takes gamma's, so nothing
        is left open; moving alpha's by hand afterwards is refused as already done."""
        proc = self.auto("shared", "--json")
        self.assertExit(proc, 0)
        data = json.loads(proc.stdout)
        self.assertEqual((data["moved"], data["from"], data["also"]), (True, self.gamma, [self.a]))
        self.assertTrue(os.path.isfile(os.path.join(self.user, "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.user, "helper.sh")))
        self.assertFalse(os.path.exists(self.in_gamma), "the untracked copy is the one that moved")
        self.assertTrue(os.path.isfile(os.path.join(self.in_a, "SKILL.md")), "the committed copy stays")
        self.assertEqual(git_ok("status", "--porcelain", cwd=self.a), "")
        event = self.box.read_events()[-1]
        self.assertEqual(event, {"ts": "2026-09-21T14:13:20Z", "type": "promote", "session": "sess-0001-aaaa",
                                 "project": self.b, "lesson": "shared", "to": "user", "path": self.user,
                                 "from": self.gamma, "auto": True, "also": [self.a]})
        self.assertEqual([e for e in self.box.read_events() if e["type"] == "candidate"], [])
        self.assertEqual(self.status()["open"]["candidates"], [])
        self.assertEqual(self.user_lessons(), ["shared"])

    def test_moving_the_untracked_copy_records_the_committed_one(self):
        proc = self.box.run("promote", "shared", "--to", "user", "--auto", "--seen-in", self.b,
                            COMPOUND_PROJECT=self.gamma)
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.in_gamma))
        self.assertTrue(os.path.isfile(os.path.join(self.in_a, "SKILL.md")))
        self.assertEqual(self.box.read_events()[-1]["also"], [self.a])

    def test_moving_the_committed_copy_by_hand_removes_the_untracked_one(self):
        proc = self.box.run("promote", "shared", "--to", "user", COMPOUND_PROJECT=self.a)
        self.assertExit(proc, 0)
        self.assertNotIn("--as", proc.stderr)
        self.assertFalse(os.path.exists(self.in_a), "moved by hand, as the user asked")
        self.assertFalse(os.path.exists(self.in_gamma), "the identical untracked copy is not left behind")
        self.assertEqual(self.user_lessons(), ["shared"], "one lesson at the user level, not two")
        event = self.box.read_events()[-1]
        self.assertEqual((event["type"], event["merged"]), ("promote", [self.gamma]))
        self.assertNotIn("also", event)

    def test_the_committed_copy_is_not_a_second_lesson(self):
        self.assertExit(self.auto(), 0)
        for project in (self.a, self.b, self.gamma):
            rows = [(row["level"], row["name"]) for row in self.box.json("list", "--json", COMPOUND_PROJECT=project)]
            self.assertEqual(rows, [("user", "shared")], project)
            data = self.status(COMPOUND_PROJECT=project)
            dup = [row for row in data["health"] if row["check"] == "duplicates"][0]
            self.assertEqual(dup["status"], "PASS", dup)
            row = [row for row in data["lessons"] if row["name"] == "shared"][0]
            self.assertEqual(row["also_in"], [self.a])
            text = self.box.run("status", COMPOUND_PROJECT=project).stdout
            self.assertIn("shared (user) is also committed in %s" % self.a, text)
        # No project offers it to another as a different lesson: nothing is left to move.
        proc = self.box.run("promote", "shared", "--to", "user", COMPOUND_PROJECT=self.a)
        self.assertExit(proc, 2)
        self.assertIn("already at the user level", proc.stderr)

    def test_a_committed_copy_that_was_edited_is_a_different_lesson_again(self):
        self.assertExit(self.auto(), 0)
        with open(os.path.join(self.in_a, "SKILL.md"), "a") as handle:
            handle.write("And one more thing.\n")
        data = self.status(COMPOUND_PROJECT=self.a)
        dup = [row for row in data["health"] if row["check"] == "duplicates"][0]
        self.assertEqual(dup["status"], "FAIL", dup)
        self.assertEqual([row for row in self.status()["lessons"] if row["name"] == "shared"][0]["also_in"], [])

    def test_a_copy_whose_text_differs_is_still_a_conflict(self):
        with open(os.path.join(self.in_gamma, "SKILL.md"), "a") as handle:
            handle.write("Gamma does it another way.\n")
        before = self.box.snapshot(self.gamma)
        proc = self.box.run("promote", "shared", "--to", "user", COMPOUND_PROJECT=self.a)
        self.assertExit(proc, 2)
        self.assertIn("COMPOUND_PROJECT=%s compound promote shared --to user --as NEWNAME" % self.a, proc.stderr)
        self.assertEqual(self.box.snapshot(self.gamma), before)
        self.assertTrue(os.path.isdir(self.in_a))


class KnobTest(Case):
    """A setting the CLI shares with the mod: the process environment, then `env` in the
    Claude directory's settings.json, then the default."""

    def settings_env(self, **env):
        with open(self.box.settings, "w") as handle:
            json.dump({"env": env}, handle)

    def limit(self, **kw):
        self.box.add("flaky") if not os.path.isdir(self.box.lesson_dir("flaky")) else None
        return self.box.json("show", "flaky", "--json", **kw)["recur_limit"]

    def test_the_default(self):
        self.assertEqual(self.limit(), 2)

    def test_the_settings_env_block_is_read(self):
        self.settings_env(COMPOUND_RECUR_LIMIT="3")
        self.assertEqual(self.limit(), 3)

    def test_the_process_environment_comes_first(self):
        self.settings_env(COMPOUND_RECUR_LIMIT="3")
        self.assertEqual(self.limit(COMPOUND_RECUR_LIMIT="5"), 5)

    def test_a_value_of_the_wrong_shape_is_the_default(self):
        self.settings_env(COMPOUND_RECUR_LIMIT="many")
        self.assertEqual(self.limit(), 2)
        self.assertEqual(self.limit(COMPOUND_RECUR_LIMIT="0"), 2)

    def test_settings_that_do_not_read_are_the_default(self):
        with open(self.box.settings, "w") as handle:
            handle.write("{broken")
        self.assertEqual(self.limit(), 2)
        with open(self.box.settings, "w") as handle:
            json.dump({"env": ["not", "an", "object"]}, handle)
        self.assertEqual(self.limit(), 2)

    def test_status_and_the_ineffective_flag_use_the_same_limit(self):
        self.box.add("flaky")
        for offset in (10, 20):
            self.box.log({"type": "recall", "lesson": "flaky"}, COMPOUND_NOW=NOW + offset)
        proc = self.box.run("status", "--json", COMPOUND_NOW=NOW + 30)
        self.assertEqual([row["name"] for row in json.loads(proc.stdout)["open"]["ineffective"]], ["flaky"])
        self.settings_env(COMPOUND_RECUR_LIMIT="3")
        proc = self.box.run("status", "--json", COMPOUND_NOW=NOW + 30)
        self.assertEqual(json.loads(proc.stdout)["open"]["ineffective"], [])

    def test_off_in_the_process_environment_overrides_the_settings(self):
        self.box.plugin()
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin), 0)
        data = json.loads(read(self.box.settings))
        data["env"]["COMPOUND_OFF"] = "1"
        with open(self.box.settings, "w") as handle:
            json.dump(data, handle)

        def mod(**kw):
            proc = self.box.run("status", "--json", **kw)
            return [row for row in json.loads(proc.stdout)["health"] if row["check"] == "mod"][0]

        self.assertEqual(mod()["status"], "WARN")
        self.assertEqual(mod(COMPOUND_OFF="0")["status"], "PASS", "the process environment comes first")


class ModHealthTest(Case):
    def health(self, name, **kw):
        proc = self.box.run("status", "--json", **kw)
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        rows = [row for row in json.loads(proc.stdout)["health"] if row["check"] == name]
        self.assertEqual(len(rows), 1, name)
        return rows[0]

    def installed(self, plugin=True):
        if plugin:
            self.box.plugin()
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin), 0)

    def test_enabled_and_loadable_passes(self):
        self.installed()
        row = self.health("mod")
        self.assertEqual(row["status"], "PASS", row)

    def test_a_checkout_without_its_plugin_files_fails(self):
        self.installed(plugin=False)
        row = self.health("mod")
        self.assertEqual(row["status"], "FAIL", row)
        self.assertIn(os.path.join(self.box.pkg, ".claude-plugin", "plugin.json"), row["detail"])
        self.assertExit(self.box.run("status"), 1)

    def test_a_missing_hooks_file_or_module_fails(self):
        self.installed()
        module = os.path.join(self.box.pkg, "hooks", "register.ts")
        os.unlink(module)
        row = self.health("mod")
        self.assertEqual(row["status"], "FAIL", row)
        self.assertIn(module, row["detail"])
        os.unlink(os.path.join(self.box.pkg, "hooks", "hooks.json"))
        row = self.health("mod")
        self.assertEqual(row["status"], "FAIL", row)
        self.assertIn(os.path.join(self.box.pkg, "hooks", "hooks.json"), row["detail"])

    def test_a_module_the_hooks_import_that_is_missing_fails(self):
        self.installed()
        self.assertEqual(self.health("mod")["status"], "PASS")
        for name in ("render.ts", "safe.ts"):
            module = os.path.join(self.box.pkg, "hooks", name)
            kept = read(module)
            os.unlink(module)
            row = self.health("mod")
            self.assertEqual(row["status"], "FAIL", "%s is imported and missing: %r" % (name, row))
            self.assertIn(module, row["detail"])
            with open(module, "w") as handle:
                handle.write(kept)
        self.assertEqual(self.health("mod")["status"], "PASS")

    def test_the_state_contract_the_hooks_import_that_is_missing_fails(self):
        self.installed()
        self.assertEqual(self.health("mod")["status"], "PASS")
        contract = os.path.join(self.box.pkg, "types", "index.d.ts")
        os.unlink(contract)
        row = self.health("mod")
        self.assertEqual(row["status"], "FAIL", "types/index.d.ts is imported and missing: %r" % (row,))
        self.assertIn(os.path.join(self.box.pkg, "types"), row["detail"])

    def test_switched_off_in_the_settings_env_warns(self):
        self.installed()
        data = json.loads(read(self.box.settings))
        data["env"]["COMPOUND_OFF"] = "1"
        with open(self.box.settings, "w") as handle:
            json.dump(data, handle)
        row = self.health("mod")
        self.assertEqual(row["status"], "WARN", row)
        self.assertIn("switched off", row["detail"])
        self.assertIn(self.box.settings, row["detail"])

    def test_switched_off_in_the_process_env_warns(self):
        self.installed()
        row = self.health("mod", COMPOUND_OFF="1")
        self.assertEqual(row["status"], "WARN", row)
        self.assertIn("switched off", row["detail"])
        self.assertEqual(self.health("mod", COMPOUND_OFF="0")["status"], "PASS")

    def test_last_fired_warns_with_no_event_the_mod_wrote(self):
        row = self.health("mod last fired")
        self.assertEqual(row["status"], "WARN", row)
        self.box.add("only-the-cli-wrote")
        self.assertExit(self.box.run("skip", "--why", "nothing"), 0)
        row = self.health("mod last fired")
        self.assertEqual(row["status"], "WARN", "learn and skip are written by the CLI, not by the mod")

    def test_last_fired_is_the_age_of_the_newest_mod_event(self):
        self.box.log({"type": "guard", "lesson": "x"}, COMPOUND_NOW=NOW - 3 * DAY)
        self.box.log({"type": "reuse", "lessons": ["x"]}, COMPOUND_NOW=NOW - 7200)
        self.box.add("later-and-not-the-mods")
        row = self.health("mod last fired")
        self.assertEqual((row["status"], row["detail"]), ("PASS", "2h ago (reuse)"))

    def test_last_fired_more_than_a_week_ago_warns(self):
        self.box.log({"type": "nudge", "calls": 30}, COMPOUND_NOW=NOW - 8 * DAY)
        row = self.health("mod last fired")
        self.assertEqual(row["status"], "WARN", row)
        self.assertIn("8d ago", row["detail"])


class CaptureTest(TwoProjects):
    def capture(self, session="s-one", offset=0, project=None, **fields):
        event = {"type": "capture", "tool": "Bash", "failed": "./build.sh", "error": "a profile is required",
                 "fixed": "./build.sh --profile dev", "session": session}
        if project:
            event["project"] = project
        event.update(fields)
        self.box.log(event, COMPOUND_NOW=NOW + offset)
        return self.box.read_events()[-1]

    def unsettled(self, *flags, **kw):
        kw.setdefault("COMPOUND_NOW", NOW + 1000)
        return self.box.json("events", "--unsettled", "--json", *flags, **kw)

    def test_a_capture_gets_a_short_stable_id(self):
        first = self.capture()
        self.assertRegex(first["id"], r"^[0-9a-f]{8}$")
        again = self.capture()
        self.assertEqual(again["id"], first["id"], "the same capture hashes the same")
        other = self.capture(session="s-two")
        self.assertNotEqual(other["id"], first["id"])
        kept = self.capture(id="abcd1234")
        self.assertEqual(kept["id"], "abcd1234")

    def test_an_unsettled_capture_is_listed(self):
        event = self.capture()
        self.assertEqual(self.unsettled(), [event])

    def test_a_learn_or_a_skip_from_the_same_session_settles_it(self):
        self.capture(session="s-one")
        self.assertExit(self.box.run("skip", "--why", "a typo", CLAUDE_CODE_SESSION_ID="s-one",
                                     COMPOUND_NOW=NOW + 10), 0)
        self.assertEqual(self.unsettled(), [])
        self.capture(session="s-two", offset=20)
        self.box.add("the-lesson", CLAUDE_CODE_SESSION_ID="s-two", COMPOUND_NOW=NOW + 30)
        self.assertEqual(self.unsettled(), [])

    def test_another_session_settles_it_only_by_its_id(self):
        event = self.capture(session="s-one")
        self.assertExit(self.box.run("skip", "--why", "unrelated", CLAUDE_CODE_SESSION_ID="s-two",
                                     COMPOUND_NOW=NOW + 10), 0)
        self.box.add("unrelated-lesson", CLAUDE_CODE_SESSION_ID="s-two", COMPOUND_NOW=NOW + 11)
        self.assertEqual(self.unsettled(), [event])
        proc = self.box.run("skip", "--why", "not worth keeping", "--settles", event["id"],
                            CLAUDE_CODE_SESSION_ID="s-two", COMPOUND_NOW=NOW + 20)
        self.assertExit(proc, 0)
        self.assertEqual(self.box.read_events()[-1]["settles"], event["id"])
        self.assertEqual(self.unsettled(), [])

    def test_add_settles_by_id_and_says_so_in_the_learn_event(self):
        event = self.capture(session="s-one")
        self.box.add("build-profile", "Use when.", "Body.\n", "--settles", event["id"],
                     CLAUDE_CODE_SESSION_ID="s-two", COMPOUND_NOW=NOW + 20)
        learn = self.box.read_events()[-1]
        self.assertEqual((learn["type"], learn["settles"]), ("learn", event["id"]))
        self.assertEqual(self.unsettled(), [])

    def test_a_settlement_before_the_capture_settles_nothing(self):
        self.assertExit(self.box.run("skip", "--why", "earlier", CLAUDE_CODE_SESSION_ID="s-one"), 0)
        event = self.capture(session="s-one", offset=10)
        self.assertEqual(self.unsettled(), [event])

    def test_an_id_that_names_no_unsettled_capture_is_refused(self):
        self.capture()
        before = self.box.snapshot()
        proc = self.box.run("skip", "--why", "x", "--settles", "ffffffff")
        self.assertExit(proc, 2)
        proc = self.box.run("add", "--name", "never-written", "--when", "Use when.", "--settles", "ffffffff",
                            stdin="Body.\n")
        self.assertExit(proc, 2)
        self.assertIn("ffffffff", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)

    def test_unsettled_is_filtered_by_project_and_bounded_to_fourteen_days(self):
        here = self.capture(session="s-one")
        there = self.capture(session="s-two", project=self.a, offset=5)
        old = self.capture(session="s-old", offset=-15 * DAY)
        self.assertEqual([e["id"] for e in self.unsettled()], [here["id"], there["id"]])
        self.assertEqual([e["id"] for e in self.unsettled("--project", self.a)], [there["id"]])
        self.assertEqual([e["id"] for e in self.unsettled("--project", self.b)], [here["id"]])
        self.assertNotIn(old["id"], [e["id"] for e in self.unsettled()])

    def test_status_lists_every_unsettled_capture_under_open(self):
        event = self.capture(session="s-one", offset=-2 * DAY,
                             failed="./build.sh " + "x" * 400, fixed="./build.sh --profile dev")
        data = self.status()
        self.assertEqual(len(data["open"]["unsettled"]), 1)
        row = data["open"]["unsettled"][0]
        self.assertEqual((row["id"], row["age"], row["project"], row["session"]),
                         (event["id"], "2d", self.b, "s-one"))
        opened = self.box.run("status").stdout.split("Open")[1]
        self.assertNotIn("nothing open", opened)
        line = [text for text in opened.splitlines() if event["id"] in text]
        self.assertEqual(len(line), 1, opened)
        self.assertIn("2d", line[0])
        self.assertIn(os.path.basename(self.b), line[0])
        self.assertIn("./build.sh --profile dev", line[0])
        self.assertLess(len(line[0]), 330, "the two commands are truncated")
        self.assertIn("--settles %s" % event["id"], opened)
        self.assertNotIn("...", line[0], "every command in the line can be run as it is printed")
        self.assertIn("/compound:learn settle %s" % event["id"], line[0])
        self.assertIn('compound skip --settles %s --why "<reason>"' % event["id"], line[0])
        self.assertExit(self.box.run("skip", "--why", "no", "--settles", event["id"],
                                     CLAUDE_CODE_SESSION_ID="s-nine"), 0)
        self.assertEqual(self.status()["open"]["unsettled"], [])


class RecallsSinceTest(Case):
    def test_show_says_how_often_a_lesson_recurred_since_it_was_last_written(self):
        self.box.add("flaky")
        self.box.log({"type": "recall", "lesson": "flaky"}, COMPOUND_NOW=NOW + 10)
        row = self.box.json("show", "flaky", "--json", COMPOUND_NOW=NOW + 20)
        self.assertEqual((row["recalls_since"], row["recur_limit"], row["ineffective"]), (1, 2, False))
        self.box.log({"type": "recall", "lesson": "flaky"}, COMPOUND_NOW=NOW + 30)
        row = self.box.json("show", "flaky", "--json", COMPOUND_NOW=NOW + 40)
        self.assertEqual((row["recalls_since"], row["ineffective"]), (2, True))
        self.box.add("flaky", "Use when.", "Better.\n", "--update", COMPOUND_NOW=NOW + 50)
        row = self.box.json("show", "flaky", "--json", COMPOUND_NOW=NOW + 60)
        self.assertEqual((row["recalls_since"], row["counts"]["recall"], row["ineffective"]), (0, 2, False))


class InstallLinkTest(Case):
    LINE = 'export PATH="$HOME/.local/bin:$PATH"'

    def test_with_no_bin_directory_on_path_the_link_is_made_and_the_line_is_printed(self):
        proc = self.box.run("install")
        self.assertExit(proc, 0)
        link = os.path.join(self.box.home, ".local", "bin", "compound")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.path.realpath(link), os.path.realpath(self.box.script))
        self.assertEqual(json.loads(read(self.box.manifest))["link"], link)
        self.assertIn(self.LINE, proc.stdout)
        self.assertEqual(proc.stdout.strip().splitlines()[-1], "Check it with: %s status" % link)

    def test_status_gives_the_same_line_while_the_link_is_not_on_path(self):
        self.assertExit(self.box.run("install"), 0)
        proc = self.box.run("status", "--json")
        row = [row for row in json.loads(proc.stdout)["health"] if row["check"] == "cli"][0]
        self.assertEqual(row["status"], "WARN")
        self.assertIn(self.LINE, row["detail"])
        local_bin = os.path.join(self.box.home, ".local", "bin")
        proc = self.box.run("status", "--json", PATH=local_bin + ":/usr/bin:/bin")
        row = [row for row in json.loads(proc.stdout)["health"] if row["check"] == "cli"][0]
        self.assertEqual(row["status"], "PASS", row)

    def test_with_the_directory_on_path_no_line_is_printed_and_the_path_is_still_absolute(self):
        local_bin = os.path.join(self.box.home, ".local", "bin")
        os.makedirs(local_bin)
        proc = self.box.run("install", PATH=local_bin + ":/usr/bin:/bin")
        self.assertExit(proc, 0)
        self.assertNotIn("export PATH", proc.stdout)
        self.assertEqual(proc.stdout.strip().splitlines()[-1],
                         "Check it with: %s status" % os.path.join(local_bin, "compound"))

    def test_uninstall_removes_that_link(self):
        self.assertExit(self.box.run("install"), 0)
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertFalse(os.path.lexists(os.path.join(self.box.home, ".local", "bin", "compound")))


class SmallThingsTest(Case):
    def test_log_refuses_a_type_it_does_not_know(self):
        proc = self.box.run("log", stdin='{"type": "recal", "lesson": "x"}')
        self.assertExit(proc, 2)
        self.assertIn("recal", proc.stderr)
        self.assertIn("recall", proc.stderr, "the known types are named")
        self.assertFalse(os.path.exists(self.box.events))

    def test_every_documented_type_is_accepted(self):
        with open(self.box.script) as handle:
            doc = handle.read().split('"""')[1]
        table = doc.split("Fields per type.")[1].split("A line that does not parse")[0]
        types = re.findall(r"^        ([a-z]+) {2,}(?:mod|CLI|`)", table, re.M)
        self.assertGreaterEqual(len(types), 13, types)
        for kind in types:
            self.assertExit(self.box.run("log", stdin=json.dumps({"type": kind})), 0)

    def surfer(self, text, code=0):
        path = os.path.join(self.box.root, "surfer")
        with open(path, "w") as handle:
            handle.write("#!/bin/sh\ncat <<'EOF'\n%s\nEOF\nexit %d\n" % (text, code))
        os.chmod(path, 0o755)
        proc = self.box.run("status", "--json", COMPOUND_SURFER=path)
        return [row for row in json.loads(proc.stdout)["health"] if row["check"] == "prompt log"][0]

    def test_the_prompt_log_row_is_a_count(self):
        row = self.surfer("113 prompt(s) across current project.\n   113  2026-08-25..2026-10-04  -Users-me-proj")
        self.assertEqual((row["status"], row["detail"]), ("PASS", "113 prompts in this project"))
        row = self.surfer("1 prompt(s) across current project.")
        self.assertEqual(row["detail"], "1 prompt in this project")

    def test_a_stats_line_that_is_not_a_count_is_reachable(self):
        row = self.surfer("the store is fine")
        self.assertEqual((row["status"], row["detail"]), ("PASS", "reachable"))

    def test_the_general_pool_directory_ships_with_the_package(self):
        self.assertTrue(os.path.isfile(os.path.join(REPO, "lessons", ".gitkeep")))

    def test_the_design_documents_what_this_file_drives(self):
        design = read(os.path.join(REPO, "docs", "design.md"))
        for text in ("--no-match", "compound rm N [--force]", "--settles", "--as NEWNAME", "--auto",
                     "events [--since TS] [--type T] [--session S] [--project P] [--unsettled]",
                     "mod last fired", "candidate"):
            self.assertIn(text, design)
        purge = design.split("compound uninstall")[-1]
        self.assertIn("--purge", purge)
        self.assertIn("user-level lessons", purge)
        self.assertRegex(purge, r"skills in\s+`<claude dir>/skills`")


if __name__ == "__main__":
    unittest.main()
