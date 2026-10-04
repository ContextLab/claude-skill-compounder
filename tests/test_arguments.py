#!/usr/bin/env python3
"""A value from outside is never read as an option by a program the package runs.

The CLI and install.sh pass values from the environment, the command line, a repository
and the prompt to `git`, `gh` and `surfer`. Each is an element of an argument vector (no
shell), a value that would begin with `-` is refused before the program is started, and
refs and names are held to a strict pattern.
"""

import json
import os
import shutil
import subprocess
import unittest

from test_support import REPO, Case, git_ok


def read(path):
    with open(path) as handle:
        return handle.read()


class InstallShArgumentsTest(Case):
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

    def piped(self, **kw):
        env = self.box.env(PATH=os.environ.get("PATH", "/usr/bin:/bin"), **kw)
        return subprocess.run(["bash", "-s", "--", "--bin-dir", self.box.bin], env=env, cwd=self.box.root,
                              input=read(os.path.join(REPO, "install.sh")), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, timeout=300)

    def test_a_ref_that_is_an_option_is_refused_before_git_is_run(self):
        """`COMPOUND_REF=-f` reached `git checkout --detach -f`, which succeeded: the
        install went through at whatever HEAD was, with the value read as an option."""
        origin = self.origin()
        for ref in ("-f", "--detach", "--orphan=x", "release;id", "release name", "a..b", "$(id)", "@{-1}"):
            proc = self.piped(COMPOUND_REPO=origin, COMPOUND_REF=ref)
            self.assertEqual(proc.returncode, 1, (ref, proc.stdout, proc.stderr))
            self.assertIn("COMPOUND_REF", proc.stderr, ref)
            self.assertFalse(os.path.exists(os.path.join(self.box.chome, "app")), "nothing was cloned for %r" % ref)
            self.assertFalse(os.path.exists(self.box.settings), ref)

    def test_a_repository_that_is_an_option_is_refused_before_git_is_run(self):
        marker = os.path.join(self.box.root, "marker")
        for repo in ("--upload-pack=touch %s" % marker, "-c", "--config=core.fsmonitor=touch %s" % marker):
            proc = self.piped(COMPOUND_REPO=repo, COMPOUND_REF="release")
            self.assertEqual(proc.returncode, 1, (repo, proc.stderr))
            self.assertIn("COMPOUND_REPO", proc.stderr, repo)
            self.assertNotIn("git clone failed", proc.stderr, "git was run with it")
        self.assertFalse(os.path.exists(marker))
        self.assertFalse(os.path.exists(os.path.join(self.box.chome, "app")))

    def test_an_ordinary_ref_and_repository_still_install(self):
        proc = self.piped(COMPOUND_REPO=self.origin(), COMPOUND_REF="release")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.box.chome, "app", "bin", "compound")))


class CliArgumentsTest(Case):
    def test_update_refuses_a_ref_that_is_an_option_or_not_a_ref_name(self):
        for ref in ("-f", "--upload-pack=x", "a b", "a;b", "$(id)", "a..b", "x@{1}", "/abs", "a//b", "trailing/", "x.lock"):
            proc = self.box.run("update", "--ref=" + ref, PATH=os.environ.get("PATH", "/usr/bin:/bin"))
            self.assertExit(proc, 2)
            self.assertIn("--ref", proc.stderr)

    def test_an_upstream_that_begins_with_a_dash_is_not_owner_repo(self):
        """`-x/y` matched the owner/repo pattern and would have been `gh repo clone -x/y`."""
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user")
        for bad in ("-x/y", "x/-y", "--repo/x", ".x/y", "x/.."):
            for flags in ((), ("--yes",)):
                proc = self.box.run("promote", "plain-note", "--to", "general", *flags, COMPOUND_UPSTREAM=bad)
                self.assertExit(proc, 2)
                self.assertIn("COMPOUND_UPSTREAM", proc.stderr)

    def test_a_git_upstream_that_is_an_option_is_refused_and_git_is_not_run(self):
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user")
        marker = os.path.join(self.box.root, "marker")
        for bad in ("--upload-pack=touch %s" % marker, "-c", "--config=core.fsmonitor=touch %s" % marker,
                    "ext::sh -c 'touch %s'" % marker, "line\nbreak"):
            for flags in ((), ("--yes",)):
                proc = self.box.run("promote", "plain-note", "--to", "general", *flags, COMPOUND_UPSTREAM_GIT=bad,
                                    PATH=os.environ.get("PATH", "/usr/bin:/bin"))
                self.assertExit(proc, 2)
                self.assertIn("COMPOUND_UPSTREAM_GIT", proc.stderr)
        self.assertFalse(os.path.exists(marker))
        self.assertFalse(any(event["type"] == "promote" for event in self.box.read_events()))

    def test_a_surfer_url_that_is_an_option_is_refused_and_git_is_not_run(self):
        marker = os.path.join(self.box.root, "marker")
        for bad in ("--upload-pack=touch %s" % marker, "-c", "ext::sh -c 'touch %s'" % marker):
            proc = self.box.run("install", "--bin-dir", self.box.bin, COMPOUND_NO_SURFER=None, COMPOUND_SURFER_URL=bad)
            if "history-surfer present" in proc.stdout:
                self.skipTest("a `surfer` is on this machine's PATH, so install fetches nothing")
            self.assertExit(proc, 0)
            record = json.loads(read(self.box.manifest))["surfer"]
            self.assertEqual(record["status"], "failed")
            self.assertIn("COMPOUND_SURFER_URL", record["detail"])
            self.assertNotIn("git clone", record["detail"], "git was run with it")
        self.assertFalse(os.path.exists(marker))
        self.assertFalse(os.path.exists(os.path.join(self.box.chome, "history-surfer")))

    def recorder(self):
        """A real program in the surfer's place that writes down the arguments it is given."""
        path = os.path.join(self.box.root, "surfer")
        self.seen = os.path.join(self.box.root, "surfer-argv")
        with open(path, "w") as handle:
            handle.write("#!/bin/sh\nfor a in \"$@\"; do printf '%%s\\n' \"$a\" >> '%s'; done\n"
                         "printf '%%s\\n' '---' >> '%s'\nprintf '[]\\n'\n" % (self.seen, self.seen))
        os.chmod(path, 0o755)
        return path

    def test_the_words_of_a_request_never_reach_the_prompt_log_search_as_an_option(self):
        surfer = self.recorder()
        hostile = "--all -rf --project /etc --exec=id -x ; $(id) `id` deploy the release notes please"
        self.assertExit(self.box.run("find", "--request", "--json", stdin=hostile, COMPOUND_SURFER=surfer), 0)
        self.assertExit(self.box.run("find", "--json", "--", "--all", "-rf", "--exec=id", "deploy",
                                     COMPOUND_SURFER=surfer), 0)
        calls = [call.strip().split("\n") for call in read(self.seen).split("---\n") if call.strip()]
        self.assertGreaterEqual(len(calls), 2)
        for argv in calls:
            self.assertEqual(argv[0], "search")
            self.assertFalse(argv[1].startswith("-"), argv)
            self.assertRegex(argv[1], r"^[a-z0-9|\\]+$", "the pattern is words of letters and digits, escaped and joined")
            self.assertEqual(argv[2:6], ["--regex", "--json", "--limit", "200"])
            self.assertIn(argv[6:], (["--project", self.box.project], ["--all"]))

    def test_a_name_that_is_an_option_is_no_lesson_for_any_command(self):
        """`show`, `rm`, `skill`, `promote`, `disable` and `use` take a name: one that
        begins with a dash is a usage error or no lesson, and nothing is run or written."""
        self.box.add("real-one")
        before = self.box.snapshot()
        for args in (("show", "--", "-rf"), ("rm", "--", "--force"), ("skill", "--", "-x"),
                     ("promote", "--to", "user", "--", "--yes"), ("disable", "--", "-x"),
                     ("promote", "real-one", "--to", "user", "--as", "-x"),
                     ("promote", "real-one", "--to", "user", "--as=--force")):
            proc = self.box.run(*args)
            self.assertExit(proc, 2)
        self.assertEqual(self.box.snapshot(), before)
        used = self.box.json("use", "--json", "--", "--force")
        self.assertFalse(used["used"])


if __name__ == "__main__":
    unittest.main()
