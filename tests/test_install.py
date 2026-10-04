#!/usr/bin/env python3
"""install, uninstall and install.sh, always against temporary directories."""

import json
import os
import shutil
import subprocess
import unittest

from test_support import REPO, Case, SURFER_URL, git_ok, surfer_reachable

PLUGIN_ENV = "CLAUDE_CODE_PLUGIN_DIRS"


def read(path):
    with open(path) as handle:
        return handle.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(text)


class InstallTest(Case):
    def install(self, *args, **kw):
        proc = self.box.run("install", "--bin-dir", self.box.bin, *args, **kw)
        self.assertExit(proc, 0)
        return proc

    def settings(self):
        return json.loads(read(self.box.settings))

    def test_install_creates_settings_link_and_record(self):
        proc = self.install()
        self.assertEqual(self.settings(), {"env": {PLUGIN_ENV: self.box.pkg}})
        link = os.path.join(self.box.bin, "compound")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.path.realpath(link), os.path.realpath(self.box.script))
        record = json.loads(read(self.box.manifest))
        self.assertEqual(record["package"], self.box.pkg)
        self.assertEqual(record["settings"], self.box.settings)
        self.assertEqual(record["link"], link)
        self.assertEqual((record["plugin_dir_added"], record["link_created"], record["settings_created"]),
                         (True, True, True))
        self.assertEqual(record["surfer"]["status"], "skipped")
        self.assertIn(link, proc.stdout)

    def test_the_installed_link_runs(self):
        self.install()
        proc = subprocess.run([os.path.join(self.box.bin, "compound"), "list", "--json"],
                              env=self.box.env(), cwd=self.box.project, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), [])

    def test_the_package_is_found_through_the_link(self):
        """general is the checkout the link resolves to, not the directory the link is in."""
        self.box.write_lesson(self.box.lesson_dir("shipped", "general"), "shipped")
        self.install()
        proc = subprocess.run([os.path.join(self.box.bin, "compound"), "list", "--json"],
                              env=self.box.env(), cwd=self.box.project, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual([(row["level"], row["name"]) for row in json.loads(proc.stdout)], [("general", "shipped")])

    def test_install_twice_changes_nothing(self):
        self.install()
        before = self.box.snapshot()
        stamps = {path: os.stat(os.path.join(self.box.root, path)).st_mtime_ns
                  for path in before if os.path.isfile(os.path.join(self.box.root, path))}
        second = self.install(COMPOUND_NOW="2027-01-01T00:00:00Z")
        self.assertEqual(self.box.snapshot(), before)
        for path, stamp in stamps.items():
            self.assertEqual(os.stat(os.path.join(self.box.root, path)).st_mtime_ns, stamp,
                             "%s was rewritten by a second install" % path)
        self.assertEqual(self.settings()["env"][PLUGIN_ENV].split(os.pathsep).count(self.box.pkg), 1)
        self.assertIn("already", second.stdout)

    def test_every_other_setting_and_plugin_dir_is_kept(self):
        original = {
            "model": "opus",
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo done"}]}]},
            "env": {"OTHER": "1", PLUGIN_ENV: os.pathsep.join(["/some/mod", "/another/mod"])},
            "statusLine": {"type": "command", "command": "~/bin/statusline.sh"},
        }
        write(self.box.settings, json.dumps(original, indent=4))
        self.install()
        after = self.settings()
        self.assertEqual(after["env"][PLUGIN_ENV].split(os.pathsep), ["/some/mod", "/another/mod", self.box.pkg])
        after["env"][PLUGIN_ENV] = original["env"][PLUGIN_ENV]
        self.assertEqual(after, original)
        self.assertEqual(list(self.settings()), list(original), "key order is kept")

    def test_a_package_already_in_the_list_is_not_added_again(self):
        write(self.box.settings, json.dumps({"env": {PLUGIN_ENV: self.box.pkg}}))
        before = read(self.box.settings)
        self.install()
        self.assertEqual(read(self.box.settings), before)
        self.assertFalse(json.loads(read(self.box.manifest))["plugin_dir_added"])

    def test_install_writes_through_a_symlinked_settings_file(self):
        dotfiles = os.path.join(self.box.root, "dotfiles", "claude-settings.json")
        write(dotfiles, json.dumps({"model": "opus"}))
        os.chmod(dotfiles, 0o600)
        os.symlink(dotfiles, self.box.settings)
        self.install()
        self.assertTrue(os.path.islink(self.box.settings), "the symlink was replaced by a file")
        self.assertEqual(os.readlink(self.box.settings), dotfiles)
        self.assertEqual(json.loads(read(dotfiles)), {"model": "opus", "env": {PLUGIN_ENV: self.box.pkg}})
        self.assertEqual(os.stat(dotfiles).st_mode & 0o777, 0o600, "the file's mode is kept")
        self.assertEqual(os.listdir(os.path.dirname(dotfiles)), ["claude-settings.json"], "no temp file is left")
        self.assertEqual(sorted(name for name in os.listdir(self.box.claude) if name.startswith(".")), [])

    def test_uninstall_through_the_symlink(self):
        dotfiles = os.path.join(self.box.root, "dotfiles", "claude-settings.json")
        write(dotfiles, json.dumps({"model": "opus"}, indent=2) + "\n")
        os.symlink(dotfiles, self.box.settings)
        self.install()
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertTrue(os.path.islink(self.box.settings))
        self.assertEqual(json.loads(read(dotfiles)), {"model": "opus"})

    def refused(self, text, needle):
        write(self.box.settings, text)
        before = self.box.snapshot()
        proc = self.box.run("install", "--bin-dir", self.box.bin)
        self.assertExit(proc, 1)
        self.assertIn(needle, proc.stderr)
        self.assertIn(self.box.settings, proc.stderr)
        self.assertEqual(self.box.snapshot(), before, "a refused install wrote something")
        self.assertEqual(read(self.box.settings), text)

    def test_malformed_settings_are_refused_and_never_overwritten(self):
        self.refused('{"model": "opus",', "not valid JSON")

    def test_settings_that_are_not_an_object_are_refused(self):
        self.refused('["a", "list"]', "not an object")

    def test_an_env_that_is_not_an_object_is_refused(self):
        self.refused('{"env": "PATH=/x"}', "`env` is not an object")

    def test_a_plugin_dirs_value_that_is_not_a_string_is_refused(self):
        self.refused(json.dumps({"env": {PLUGIN_ENV: ["/a"]}}), "is not a string")

    def test_a_file_in_the_way_of_the_link_refuses_before_anything_is_written(self):
        write(os.path.join(self.box.bin, "compound"), "#!/bin/sh\necho someone else's compound\n")
        write(self.box.settings, '{"model": "opus"}')
        before = self.box.snapshot()
        proc = self.box.run("install", "--bin-dir", self.box.bin)
        self.assertExit(proc, 1)
        self.assertIn("is not a link to this package", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)

    def test_an_empty_settings_file_is_treated_as_an_empty_object(self):
        write(self.box.settings, "")
        self.install()
        self.assertEqual(self.settings(), {"env": {PLUGIN_ENV: self.box.pkg}})

    def test_the_bin_dir_is_the_first_of_local_bin_and_bin_on_path(self):
        local_bin = os.path.join(self.box.home, ".local", "bin")
        home_bin = os.path.join(self.box.home, "bin")
        os.makedirs(local_bin)
        os.makedirs(home_bin)
        proc = self.box.run("install", PATH=home_bin + ":/usr/bin:/bin")
        self.assertExit(proc, 0)
        self.assertTrue(os.path.islink(os.path.join(home_bin, "compound")))
        self.assertFalse(os.path.lexists(os.path.join(local_bin, "compound")))
        self.assertExit(self.box.run("uninstall"), 0)
        proc = self.box.run("install", PATH=home_bin + ":" + local_bin + ":/usr/bin:/bin")
        self.assertExit(proc, 0)
        self.assertTrue(os.path.islink(os.path.join(local_bin, "compound")), "~/.local/bin comes first")
        self.assertFalse(os.path.lexists(os.path.join(home_bin, "compound")))

    def test_with_neither_bin_dir_on_path_the_mod_is_enabled_and_the_link_goes_to_local_bin(self):
        proc = self.box.run("install")
        self.assertExit(proc, 0)
        self.assertIn("is not on PATH", proc.stdout)
        self.assertEqual(self.settings(), {"env": {PLUGIN_ENV: self.box.pkg}})
        link = os.path.join(self.box.bin, "compound")
        self.assertEqual(json.loads(read(self.box.manifest))["link"], link)
        self.assertTrue(os.path.islink(link))

    def test_claude_dir_flag_names_the_directory(self):
        other = os.path.join(self.box.root, "other-claude")
        os.makedirs(other)
        proc = self.box.run("install", "--claude-dir", other, "--bin-dir", self.box.bin)
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(read(os.path.join(other, "settings.json"))), {"env": {PLUGIN_ENV: self.box.pkg}})
        self.assertFalse(os.path.exists(self.box.settings))

    def test_json_output_is_the_record(self):
        proc = self.install("--json")
        self.assertEqual(json.loads(proc.stdout), json.loads(read(self.box.manifest)))

    def test_a_history_surfer_that_cannot_be_fetched_is_one_line_and_not_a_failure(self):
        proc = self.install(COMPOUND_NO_SURFER=None,
                            COMPOUND_SURFER_URL=os.path.join(self.box.root, "no-such-repository"))
        lines = [line for line in proc.stdout.splitlines() if "history-surfer" in line]
        self.assertEqual(len(lines), 1, proc.stdout)
        self.assertIn("failed", lines[0])
        record = json.loads(read(self.box.manifest))
        self.assertEqual(record["surfer"]["status"], "failed")
        self.assertTrue(record["plugin_dir_added"])
        self.assertFalse(os.path.exists(os.path.join(self.box.chome, "history-surfer")))

    def test_a_surfer_already_on_path_is_left_alone(self):
        """A real executable named surfer on PATH: install must not clone anything."""
        tools = os.path.join(self.box.root, "tools")
        os.makedirs(tools)
        os.symlink("/bin/echo", os.path.join(tools, "surfer"))
        proc = self.install(COMPOUND_NO_SURFER=None, PATH=tools + ":/usr/bin:/bin",
                            COMPOUND_SURFER_URL=os.path.join(self.box.root, "no-such-repository"))
        self.assertEqual(json.loads(read(self.box.manifest))["surfer"]["status"], "present")
        self.assertIn("history-surfer present", proc.stdout)

    def program(self, directory, name, text):
        """A real executable `name` in `directory` that prints `text`."""
        path = os.path.join(directory, name)
        write(path, "#!/bin/sh\necho '%s'\n" % text)
        os.chmod(path, 0o755)
        return path

    def test_another_compound_earlier_on_path_is_reported(self):
        tools = os.path.join(self.box.root, "tools")
        other = self.program(tools, "compound", "another compound")
        proc = self.install(PATH=tools + ":" + self.box.bin + ":/usr/bin:/bin")
        lines = [line for line in proc.stdout.splitlines() if other in line]
        self.assertEqual(len(lines), 1, proc.stdout)
        self.assertIn("first on PATH", lines[0])
        self.assertTrue(os.path.islink(os.path.join(self.box.bin, "compound")), "the link is still made")
        self.assertEqual(read(other), "#!/bin/sh\necho 'another compound'\n", "the other program is left alone")

    def test_no_shadow_is_reported_when_the_link_is_what_path_finds(self):
        os.makedirs(self.box.bin)
        proc = self.install(PATH=self.box.bin + ":/usr/bin:/bin")
        self.assertNotIn("first on PATH", proc.stdout)

    def claude_lines(self, proc):
        return [line for line in proc.stdout.splitlines() if line.strip().startswith("claude ")]

    def test_a_claude_code_older_than_the_minimum_is_a_warning_and_not_a_failure(self):
        tools = os.path.join(self.box.root, "tools")
        self.program(tools, "claude", "2.1.100 (Claude Code)")
        proc = self.install(PATH=tools + ":/usr/bin:/bin")
        lines = self.claude_lines(proc)
        self.assertEqual(len(lines), 1, proc.stdout)
        self.assertIn("2.1.100", lines[0])
        self.assertIn("2.1.288", lines[0])
        self.assertIn("claude update", lines[0])
        self.assertTrue(os.path.isfile(self.box.manifest), "the install went through")

    def test_a_claude_code_at_the_minimum_is_one_quiet_line(self):
        tools = os.path.join(self.box.root, "tools")
        self.program(tools, "claude", "2.1.288 (Claude Code)")
        proc = self.install(PATH=tools + ":/usr/bin:/bin")
        lines = self.claude_lines(proc)
        self.assertEqual(len(lines), 1, proc.stdout)
        self.assertIn("2.1.288", lines[0])
        self.assertNotIn("older", lines[0])

    def test_without_claude_on_path_install_says_the_version_was_not_checked(self):
        proc = self.install()
        lines = self.claude_lines(proc)
        self.assertEqual(len(lines), 1, proc.stdout)
        self.assertIn("not on PATH", lines[0])
        self.assertIn("2.1.288", lines[0])

    def test_the_record_names_the_directories_install_created(self):
        other = os.path.join(self.box.root, "fresh", "claude")
        proc = self.box.run("install", "--claude-dir", other, "--bin-dir", self.box.bin, COMPOUND_HOME=None)
        self.assertExit(proc, 0)
        record = json.loads(read(os.path.join(other, "compound", "install.json")))
        self.assertEqual(sorted(record["dirs_created"]), sorted([
            os.path.join(self.box.root, "fresh"), other, os.path.join(other, "compound"),
            os.path.join(self.box.home, ".local"), self.box.bin]))
        again = self.box.run("install", "--claude-dir", other, "--bin-dir", self.box.bin, COMPOUND_HOME=None)
        self.assertExit(again, 0)
        self.assertEqual(json.loads(read(os.path.join(other, "compound", "install.json"))), record,
                         "a second install keeps the list")

    def test_the_real_history_surfer_is_cloned_and_set_up(self):
        if not surfer_reachable():
            self.skipTest("history-surfer cannot be cloned from here (%s)" % SURFER_URL)
        self.install(COMPOUND_NO_SURFER=None)
        record = json.loads(read(self.box.manifest))
        self.assertEqual(record["surfer"]["status"], "installed", record["surfer"])
        home = os.path.join(self.box.chome, "history-surfer")
        self.assertEqual(record["surfer"]["home"], home)
        self.assertTrue(os.path.isfile(os.path.join(home, "scripts", "setup.py")))
        surfer = os.path.join(self.box.bin, "surfer")
        self.assertTrue(os.path.exists(surfer))
        settings = self.settings()
        self.assertEqual(settings["env"][PLUGIN_ENV], self.box.pkg)
        self.assertIn("hooks", settings, "history-surfer wires its own hooks into the same settings.json")
        before = self.box.snapshot()
        self.install(COMPOUND_NO_SURFER=None)
        self.assertEqual(self.box.snapshot(), before, "a second install changed something")

        self.assertExit(self.box.run("uninstall"), 0)
        self.assertTrue(os.path.isdir(home), "uninstall leaves history-surfer in place")
        self.assertTrue(os.path.exists(surfer))
        self.assertNotIn(PLUGIN_ENV, json.dumps(self.settings()))


class UninstallTest(Case):
    def install(self, **kw):
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin, **kw), 0)

    def test_uninstall_reverses_install_and_keeps_lessons(self):
        self.install()
        self.box.add("kept-lesson", "Use when.", "Body.\n", "--level", "user")
        proc = self.box.run("uninstall")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.box.settings), "install created settings.json, so uninstall removes it")
        self.assertFalse(os.path.lexists(os.path.join(self.box.bin, "compound")))
        self.assertFalse(os.path.exists(self.box.manifest))
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("kept-lesson", "user"), "SKILL.md")))
        self.assertTrue(os.path.isfile(self.box.events))
        self.assertIn("--purge", proc.stdout)

    def test_uninstall_leaves_unrelated_settings_untouched(self):
        original = {
            "model": "opus",
            "env": {"OTHER": "1", PLUGIN_ENV: os.pathsep.join(["/some/mod", "/another/mod"])},
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo done"}]}]},
        }
        write(self.box.settings, json.dumps(original, indent=2) + "\n")
        before = read(self.box.settings)
        self.install()
        self.assertNotEqual(read(self.box.settings), before)
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertEqual(json.loads(read(self.box.settings)), original)
        self.assertEqual(read(self.box.settings), before, "byte for byte what it was")

    def test_an_env_install_created_is_removed_and_one_it_found_is_kept(self):
        write(self.box.settings, json.dumps({"model": "opus"}))
        self.install()
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertEqual(json.loads(read(self.box.settings)), {"model": "opus"})

        write(self.box.settings, json.dumps({"env": {}}))
        self.install()
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertEqual(json.loads(read(self.box.settings)), {"env": {}})

    def test_an_element_that_was_there_before_install_goes_too(self):
        """The element that names this package is this package's, whoever the record says
        added it: a record written after a failed install says "not us" about an element
        an earlier run added."""
        write(self.box.settings, json.dumps({"env": {PLUGIN_ENV: self.box.pkg}}))
        self.install()
        self.assertFalse(json.loads(read(self.box.manifest))["plugin_dir_added"])
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertEqual(json.loads(read(self.box.settings)), {"env": {}},
                         "the env object was there before install, so it stays")

    def test_settings_added_after_install_survive_uninstall(self):
        self.install()
        data = json.loads(read(self.box.settings))
        data["model"] = "sonnet"
        data["env"][PLUGIN_ENV] += os.pathsep + "/added/later"
        write(self.box.settings, json.dumps(data))
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertEqual(json.loads(read(self.box.settings)), {"model": "sonnet", "env": {PLUGIN_ENV: "/added/later"}})

    def test_a_link_that_now_points_elsewhere_is_left_alone(self):
        self.install()
        link = os.path.join(self.box.bin, "compound")
        os.unlink(link)
        os.symlink("/bin/echo", link)
        proc = self.box.run("uninstall")
        self.assertExit(proc, 0)
        self.assertEqual(os.readlink(link), "/bin/echo")
        self.assertIn("left alone", proc.stdout)

    def test_a_link_install_did_not_create_is_left_alone(self):
        os.makedirs(self.box.bin)
        os.symlink(self.box.script, os.path.join(self.box.bin, "compound"))
        self.install()
        self.assertFalse(json.loads(read(self.box.manifest))["link_created"])
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertTrue(os.path.islink(os.path.join(self.box.bin, "compound")))

    def test_uninstall_without_a_record_changes_nothing(self):
        write(self.box.settings, json.dumps({"env": {PLUGIN_ENV: self.box.pkg}}))
        before = self.box.snapshot()
        proc = self.box.run("uninstall")
        self.assertExit(proc, 0)
        self.assertIn("no install record", proc.stdout)
        self.assertEqual(self.box.snapshot(), before)

    def test_malformed_settings_at_uninstall_are_reported_and_the_record_is_kept(self):
        self.install()
        write(self.box.settings, "{broken")
        proc = self.box.run("uninstall", "--purge")
        self.assertExit(proc, 1)
        self.assertIn("not valid JSON", proc.stderr)
        self.assertEqual(read(self.box.settings), "{broken")
        self.assertTrue(os.path.isfile(self.box.manifest), "the record stays so uninstall can be run again")
        self.assertTrue(os.path.isdir(self.box.chome), "--purge does not run past a failure")
        write(self.box.settings, json.dumps({"env": {PLUGIN_ENV: self.box.pkg}}))
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertFalse(os.path.exists(self.box.manifest))

    def test_purge_removes_compound_home(self):
        self.install()
        self.box.add("lost-lesson", "Use when.", "Body.\n", "--level", "user")
        self.box.add("project-lesson")
        proc = self.box.run("uninstall", "--purge")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.box.chome))
        self.assertTrue(os.path.isdir(self.box.claude), "only COMPOUND_HOME goes")
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("project-lesson"), "SKILL.md")),
                        "a project's lessons are the project's")

    def test_purge_refuses_a_home_that_is_not_compounds_own(self):
        for bad in (self.box.home, self.box.claude):
            proc = self.box.run("uninstall", "--purge", COMPOUND_HOME=bad)
            self.assertExit(proc, 1)
            self.assertIn("--purge refused", proc.stderr)
            self.assertTrue(os.path.isdir(self.box.claude))

    def test_empty_directories_install_created_are_removed(self):
        """~/.local/bin and ~/.local were made by install and hold nothing else: they go.
        The Claude directory was there before install: it stays."""
        self.assertFalse(os.path.exists(os.path.join(self.box.home, ".local")))
        self.install()
        self.assertTrue(os.path.isdir(self.box.bin))
        proc = self.box.run("uninstall")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(os.path.join(self.box.home, ".local")), proc.stdout)
        self.assertFalse(os.path.exists(self.box.chome), "an empty COMPOUND_HOME install made goes too")
        self.assertTrue(os.path.isdir(self.box.claude))
        self.assertIn("removed  %s" % self.box.bin, proc.stdout)
        self.assertNotIn("kept ", proc.stdout, "nothing is said to be kept in a directory that is gone")

    def test_a_directory_install_created_that_now_holds_something_stays(self):
        self.install()
        write(os.path.join(self.box.bin, "other-tool"), "#!/bin/sh\n")
        self.box.add("kept-lesson", "Use when.", "Body.\n", "--level", "user")
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertEqual(os.listdir(self.box.bin), ["other-tool"])
        self.assertTrue(os.path.isdir(self.box.chome))

    def test_a_directory_that_was_there_before_install_stays_even_when_empty(self):
        os.makedirs(self.box.bin)
        self.install()
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertEqual(os.listdir(self.box.bin), [])

    def test_a_claude_directory_install_created_is_removed_with_purge(self):
        other = os.path.join(self.box.root, "fresh", "claude")
        env = {"COMPOUND_HOME": None, "COMPOUND_CLAUDE_DIR": other}
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin, **env), 0)
        self.assertTrue(os.path.isfile(os.path.join(other, "settings.json")))
        self.assertExit(self.box.run("uninstall", "--purge", **env), 0)
        self.assertFalse(os.path.exists(os.path.join(self.box.root, "fresh")))

    def test_plain_uninstall_prints_the_command_that_purges_later(self):
        self.install()
        self.box.add("kept-lesson", "Use when.", "Body.\n", "--level", "user")
        proc = self.box.run("uninstall")
        self.assertExit(proc, 0)
        line = [text for text in proc.stdout.splitlines() if "uninstall --purge" in text]
        self.assertEqual(len(line), 1, proc.stdout)
        self.assertIn(self.box.script, line[0])
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("kept-lesson", "user"), "SKILL.md")))
        argv = line[0].split(": ", 1)[1].split()
        later = subprocess.run(argv, env=self.box.env(), cwd=self.box.root, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(later.returncode, 0, later.stderr)
        self.assertFalse(os.path.exists(self.box.chome), "the printed command purges")

    def test_json_output(self):
        self.install()
        data = self.box.json("uninstall", "--json")
        self.assertEqual(data["problems"], [])
        self.assertTrue(any("removed" in line for line in data["report"]))


class InstallShTest(Case):
    def checkout(self):
        """A copy of the shipped files, as a checkout install.sh can sit in."""
        shutil.copy2(os.path.join(REPO, "install.sh"), os.path.join(self.box.pkg, "install.sh"))
        return self.box.pkg

    def sh(self, argv, stdin=None, **kw):
        env = self.box.env(**kw)
        return subprocess.run(argv, env=env, cwd=self.box.root, input=stdin if stdin is not None else "",
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=300)

    def test_from_inside_a_checkout_it_installs_that_checkout(self):
        pkg = self.checkout()
        proc = self.sh(["bash", os.path.join(pkg, "install.sh"), "--bin-dir", self.box.bin])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(read(self.box.settings)), {"env": {PLUGIN_ENV: pkg}})
        self.assertEqual(os.path.realpath(os.path.join(self.box.bin, "compound")),
                         os.path.join(pkg, "bin", "compound"))
        self.assertFalse(os.path.exists(os.path.join(self.box.chome, "app")), "nothing is cloned")

    def test_piped_into_bash_it_clones_the_package_and_installs_the_clone(self):
        origin = os.path.join(self.box.root, "origin")
        os.makedirs(os.path.join(origin, "bin"))
        shutil.copy2(self.box.script, os.path.join(origin, "bin", "compound"))
        shutil.copy2(os.path.join(REPO, "install.sh"), os.path.join(origin, "install.sh"))
        git_ok("init", "-q", origin)
        git_ok("checkout", "-q", "-b", "release", cwd=origin)
        git_ok("add", "-A", cwd=origin)
        git_ok("commit", "-q", "-m", "package", cwd=origin)
        script = read(os.path.join(REPO, "install.sh"))
        proc = self.sh(["bash", "-s", "--", "--bin-dir", self.box.bin], stdin=script,
                       COMPOUND_REPO=origin, COMPOUND_REF="release")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        app = os.path.join(self.box.chome, "app")
        self.assertTrue(os.path.isfile(os.path.join(app, "bin", "compound")))
        self.assertEqual(json.loads(read(self.box.settings)), {"env": {PLUGIN_ENV: app}})
        self.assertEqual(os.path.realpath(os.path.join(self.box.bin, "compound")),
                         os.path.join(app, "bin", "compound"))

        with open(os.path.join(origin, "VERSION"), "w") as handle:
            handle.write("2\n")
        git_ok("add", "-A", cwd=origin)
        git_ok("commit", "-q", "-m", "second", cwd=origin)
        again = self.sh(["bash", "-s", "--", "--bin-dir", self.box.bin], stdin=script,
                        COMPOUND_REPO=origin, COMPOUND_REF="release")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(read(os.path.join(app, "VERSION")), "2\n", "a second run pulls the clone")
        self.assertEqual(json.loads(read(self.box.settings)), {"env": {PLUGIN_ENV: app}})

    def origin(self):
        origin = os.path.join(self.box.root, "origin")
        os.makedirs(os.path.join(origin, "bin"))
        shutil.copy2(self.box.script, os.path.join(origin, "bin", "compound"))
        shutil.copy2(os.path.join(REPO, "install.sh"), os.path.join(origin, "install.sh"))
        git_ok("init", "-q", origin)
        git_ok("checkout", "-q", "-b", "release", cwd=origin)
        git_ok("add", "-A", cwd=origin)
        git_ok("commit", "-q", "-m", "package", cwd=origin)
        return origin

    def test_on_a_clean_home_the_closing_line_is_a_command_that_runs(self):
        """No bin directory on PATH and none named: the link goes to ~/.local/bin, and the
        last line names it by its absolute path, which runs with PATH as it is."""
        script = read(os.path.join(REPO, "install.sh"))
        proc = self.sh(["bash", "-s"], stdin=script, COMPOUND_REPO=self.origin(), COMPOUND_REF="release")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        link = os.path.join(self.box.home, ".local", "bin", "compound")
        last = proc.stdout.strip().splitlines()[-1]
        self.assertEqual(last, "Check it with: %s status" % link)
        check = self.sh(last[len("Check it with: "):].split())
        self.assertIn(check.returncode, (0, 1), check.stderr)
        self.assertIn("Health", check.stdout)
        readme = read(os.path.join(REPO, "README.md"))
        self.assertIn("~/.local/bin/compound status", readme,
                      "the README's check step gives the path that works before PATH is edited")

    def test_uninstall_keeps_the_clone_and_says_where_and_purge_removes_it(self):
        script = read(os.path.join(REPO, "install.sh"))
        argv = ["bash", "-s", "--", "--bin-dir", self.box.bin]
        proc = self.sh(argv, stdin=script, COMPOUND_REPO=self.origin(), COMPOUND_REF="release")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        app = os.path.join(self.box.chome, "app")
        cli = os.path.join(app, "bin", "compound")
        proc = self.box.run("uninstall", script=cli)
        self.assertExit(proc, 0)
        self.assertTrue(os.path.isfile(cli), "plain uninstall leaves the clone")
        line = [text for text in proc.stdout.splitlines() if app in text and "clone" in text]
        self.assertEqual(len(line), 1, proc.stdout)
        self.assertIn("--purge", line[0])

        proc = self.sh(argv, stdin=script, COMPOUND_REPO=os.path.join(self.box.root, "origin"), COMPOUND_REF="release")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = self.box.run("uninstall", "--purge", script=cli)
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(app), "--purge removes the clone")
        self.assertFalse(os.path.exists(self.box.chome))
        self.assertIn("the package clone", proc.stdout)

    def test_a_tag_installs_without_gits_detached_head_advice(self):
        origin = self.origin()
        git_ok("tag", "v9.9.9", cwd=origin)
        script = read(os.path.join(REPO, "install.sh"))
        for run in ("first", "second"):
            proc = self.sh(["bash", "-s", "--", "--bin-dir", self.box.bin], stdin=script,
                           COMPOUND_REPO=origin, COMPOUND_REF="v9.9.9")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("detached HEAD", proc.stderr, "%s run" % run)
            self.assertNotIn("detached HEAD", proc.stdout, "%s run" % run)
        self.assertTrue(os.path.isfile(os.path.join(self.box.chome, "app", "bin", "compound")))

    def test_a_ref_without_the_cli_is_refused_and_its_clone_is_not_left_behind(self):
        origin = self.origin()
        git_ok("checkout", "-q", "-b", "empty", cwd=origin)
        git_ok("rm", "-q", "-r", "bin", cwd=origin)
        git_ok("commit", "-q", "-m", "no cli", cwd=origin)
        script = read(os.path.join(REPO, "install.sh"))
        proc = self.sh(["bash", "-s"], stdin=script, COMPOUND_REPO=origin, COMPOUND_REF="empty")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("has no bin/compound", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.box.chome, "app")))
        self.assertFalse(os.path.exists(self.box.settings))
        # The next run, with a ref that has the CLI, is not blocked by what the first left.
        again = self.sh(["bash", "-s", "--", "--bin-dir", self.box.bin], stdin=script,
                        COMPOUND_REPO=origin, COMPOUND_REF="release")
        self.assertEqual(again.returncode, 0, again.stderr)

    def test_install_says_to_start_a_new_session(self):
        proc = self.sh(["bash", os.path.join(self.checkout(), "install.sh"), "--bin-dir", self.box.bin])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Start a new Claude Code session", proc.stdout)

    def test_a_clone_that_fails_exits_non_zero_and_installs_nothing(self):
        script = read(os.path.join(REPO, "install.sh"))
        proc = self.sh(["bash", "-s"], stdin=script, COMPOUND_REPO=os.path.join(self.box.root, "nowhere"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("git clone failed", proc.stderr)
        self.assertFalse(os.path.exists(self.box.settings))

    def test_a_directory_in_the_way_of_the_clone_is_refused(self):
        os.makedirs(os.path.join(self.box.chome, "app", "something"))
        script = read(os.path.join(REPO, "install.sh"))
        proc = self.sh(["bash", "-s"], stdin=script, COMPOUND_REPO=os.path.join(self.box.root, "nowhere"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not a git checkout", proc.stderr)
        self.assertTrue(os.path.isdir(os.path.join(self.box.chome, "app", "something")))

    # ---- the piped uninstall ----

    def piped(self, *args, **kw):
        return self.sh(["bash", "-s", "--"] + list(args), stdin=read(os.path.join(REPO, "install.sh")), **kw)

    def test_piped_uninstall_finds_the_clone_with_no_compound_on_path(self):
        proc = self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=self.origin(), COMPOUND_REF="release")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        app = os.path.join(self.box.chome, "app")
        link = os.path.join(self.box.bin, "compound")
        self.assertTrue(os.path.islink(link))
        self.assertIsNone(shutil.which("compound", path=self.box.env()["PATH"]), "compound is not on PATH here")

        proc = self.piped("uninstall")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.lexists(link))
        self.assertFalse(os.path.exists(self.box.settings))
        self.assertFalse(os.path.exists(self.box.manifest))
        self.assertTrue(os.path.isfile(os.path.join(app, "bin", "compound")), "plain uninstall keeps the clone")
        self.assertIn("removed", proc.stdout)

        # Later, with the record gone, the clone is still found and --purge removes it.
        proc = self.piped("uninstall", "--purge")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.exists(self.box.chome))
        self.assertIn("purged", proc.stdout)

    def test_piped_uninstall_with_compound_on_path(self):
        os.makedirs(self.box.bin)
        path = self.box.bin + ":/usr/bin:/bin"
        proc = self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=self.origin(), COMPOUND_REF="release", PATH=path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIsNotNone(shutil.which("compound", path=path))
        proc = self.piped("uninstall", "--purge", PATH=path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.lexists(os.path.join(self.box.bin, "compound")))
        self.assertFalse(os.path.exists(self.box.chome))
        self.assertFalse(os.path.exists(self.box.settings))

    def test_piped_uninstall_finds_a_checkout_elsewhere_through_the_install_record(self):
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin), 0)
        self.assertFalse(os.path.exists(os.path.join(self.box.chome, "app")), "installed from a checkout, no clone")
        proc = self.piped("uninstall")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.lexists(os.path.join(self.box.bin, "compound")))
        self.assertFalse(os.path.exists(self.box.settings))
        self.assertTrue(os.path.isfile(self.box.script), "the checkout itself is never removed")

    def test_piped_uninstall_honours_compound_claude_dir_for_the_default_home(self):
        other = os.path.join(self.box.root, "other-claude")
        env = {"COMPOUND_HOME": None, "COMPOUND_CLAUDE_DIR": other}
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin, **env), 0)
        self.assertTrue(os.path.isfile(os.path.join(other, "compound", "install.json")))
        proc = self.piped("uninstall", **env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(other, "compound", "install.json")))
        self.assertFalse(os.path.lexists(os.path.join(self.box.bin, "compound")))

    def test_piped_uninstall_when_nothing_is_installed_says_so_and_changes_nothing(self):
        before = self.box.snapshot()
        for args in (["uninstall"], ["uninstall", "--purge"]):
            proc = self.piped(*args)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("compound is not installed", proc.stderr)
            self.assertIn(self.box.manifest, proc.stderr)
            self.assertEqual(self.box.snapshot(), before)

    def test_piped_uninstall_never_clones(self):
        proc = self.piped("uninstall", COMPOUND_REPO=self.origin(), COMPOUND_REF="release")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.exists(self.box.chome))

    def test_the_word_install_is_accepted(self):
        proc = self.piped("install", "--bin-dir", self.box.bin, COMPOUND_REPO=self.origin(), COMPOUND_REF="release")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.islink(os.path.join(self.box.bin, "compound")))

    # ---- releases ----

    def released(self, *tags):
        """An origin on `main` with one commit per tag, in the order given, and one more
        commit on main after the last tag."""
        origin = os.path.join(self.box.root, "origin")
        os.makedirs(os.path.join(origin, "bin"))
        shutil.copy2(self.box.script, os.path.join(origin, "bin", "compound"))
        git_ok("init", "-q", origin)
        git_ok("checkout", "-q", "-b", "main", cwd=origin)
        for tag in tags:
            self.release(origin, tag)
        self.release(origin, None)
        return origin

    def release(self, origin, tag, text=None):
        write(os.path.join(origin, "VERSION"), "%s\n" % (text or tag or "tip"))
        git_ok("add", "-A", cwd=origin)
        git_ok("commit", "-q", "-m", tag or "not a release", cwd=origin)
        if tag:
            git_ok("tag", tag, cwd=origin)

    def version(self):
        return read(os.path.join(self.box.chome, "app", "VERSION")).strip()

    def test_with_no_ref_the_newest_release_is_installed(self):
        """Versions are compared as numbers (0.10.0 is newer than 0.9.0), a release older
        than 0.4.0 or a tag that is not vX.Y.Z is never picked, and main's tip is not used."""
        origin = self.released("v0.3.9", "v0.4.0", "v0.10.0", "v0.9.0", "v1.0.0-rc1", "nightly")
        proc = self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=origin)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.version(), "v0.10.0")
        self.assertIn("v0.10.0", proc.stderr)
        self.assertNotIn("detached HEAD", proc.stderr)

    def test_an_annotated_release_tag_is_found(self):
        origin = self.released("v0.4.0")
        self.release(origin, None, "annotated")
        git_ok("tag", "-a", "v0.5.0", "-m", "release 0.5.0", cwd=origin)
        self.release(origin, None)
        proc = self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=origin)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.version(), "annotated")
        self.assertNotIn("warning", proc.stderr, "git's 'is not a commit' warning for an annotated tag is not shown")

    def test_a_ref_the_repository_does_not_have_is_refused_and_its_clone_is_not_left_behind(self):
        origin = self.released("v0.4.0")
        proc = self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=origin, COMPOUND_REF="v9.9.9")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot check out v9.9.9", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.box.chome, "app")))
        self.assertFalse(os.path.exists(self.box.settings))

    def test_with_no_release_main_is_installed(self):
        origin = self.released("v0.3.0", "v0.3.1")
        proc = self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=origin)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.version(), "tip")
        self.assertEqual(git_ok("symbolic-ref", "--short", "HEAD", cwd=os.path.join(self.box.chome, "app")), "main")

    def test_a_second_run_moves_the_clone_to_a_newer_release(self):
        origin = self.released("v0.4.0")
        self.assertEqual(self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=origin).returncode, 0)
        self.assertEqual(self.version(), "v0.4.0")
        self.release(origin, "v0.4.1")
        self.release(origin, None)
        proc = self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=origin)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.version(), "v0.4.1")
        self.assertNotIn("detached HEAD", proc.stderr)

    def test_compound_ref_main_follows_the_tip(self):
        origin = self.released("v0.4.0")
        proc = self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=origin, COMPOUND_REF="main")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.version(), "tip")
        self.release(origin, "v0.4.1")
        self.release(origin, None, "newer tip")
        proc = self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=origin, COMPOUND_REF="main")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.version(), "newer tip")

    def test_installed_from_a_release_compound_update_moves_to_the_next_one(self):
        origin = self.released("v0.4.0")
        self.assertEqual(self.piped("--bin-dir", self.box.bin, COMPOUND_REPO=origin).returncode, 0)
        self.release(origin, "v0.4.1")
        self.release(origin, None)
        proc = self.box.run("update", script=os.path.join(self.box.chome, "app", "bin", "compound"))
        self.assertExit(proc, 0)
        self.assertEqual(self.version(), "v0.4.1")
        self.assertIn("v0.4.0 -> v0.4.1", proc.stdout)


if __name__ == "__main__":
    unittest.main()
