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

    def test_with_neither_bin_dir_on_path_the_mod_is_enabled_and_no_link_is_made(self):
        proc = self.box.run("install")
        self.assertExit(proc, 0)
        self.assertIn("not linked", proc.stdout)
        self.assertEqual(self.settings(), {"env": {PLUGIN_ENV: self.box.pkg}})
        self.assertIsNone(json.loads(read(self.box.manifest))["link"])
        self.assertFalse(os.path.exists(self.box.bin))

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

    def test_an_element_that_was_there_before_install_stays(self):
        write(self.box.settings, json.dumps({"env": {PLUGIN_ENV: self.box.pkg}}))
        self.install()
        self.assertExit(self.box.run("uninstall"), 0)
        self.assertEqual(json.loads(read(self.box.settings)), {"env": {PLUGIN_ENV: self.box.pkg}})

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


if __name__ == "__main__":
    unittest.main()
