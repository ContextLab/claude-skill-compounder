#!/usr/bin/env python3
"""Shared test support, and the tests of that support.

Every test drives the real `bin/compound` through `subprocess` against real temporary
directories. The script is COPIED into a temporary package directory first, so the
`general` level a test sees is that empty copy and never this repository's own
`lessons/` and `skills/`.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SCRIPT = os.path.join(REPO, "bin", "compound")
NOW = 1790000000  # 2026-09-21T14:13:20Z
BASE_PATH = "/usr/bin:/bin"


class Sandbox(object):
    """Temp HOME, claude dir, compound home, project and package copy."""

    def __init__(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="compound-test-"))
        self.home = os.path.join(self.root, "home")
        self.claude = os.path.join(self.home, ".claude")
        self.chome = os.path.join(self.claude, "compound")
        self.project = os.path.join(self.root, "project")
        self.pkg = os.path.join(self.root, "pkg")
        self.bin = os.path.join(self.home, ".local", "bin")
        for path in (self.home, self.claude, self.project, os.path.join(self.pkg, "bin")):
            os.makedirs(path)
        self.script = os.path.join(self.pkg, "bin", "compound")
        shutil.copy2(SCRIPT, self.script)
        os.chmod(self.script, 0o755)
        self.events = os.path.join(self.chome, "events.jsonl")
        self.settings = os.path.join(self.claude, "settings.json")
        self.manifest = os.path.join(self.chome, "install.json")

    def plugin(self):
        """Give the package copy the files that make a checkout loadable as the plugin."""
        modules = sorted(name for name in os.listdir(os.path.join(REPO, "hooks"))
                         if name.endswith(".ts") and not name.endswith(".test.ts"))
        # types/index.d.ts is the contract the manifest names and the hooks import their types from.
        for rel in [os.path.join(".claude-plugin", "plugin.json"), os.path.join("hooks", "hooks.json"),
                    os.path.join("types", "index.d.ts")] + [os.path.join("hooks", name) for name in modules]:
            target = os.path.join(self.pkg, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(REPO, rel), target)

    def close(self):
        for base, dirs, _files in os.walk(self.root):
            for name in dirs:
                try:
                    os.chmod(os.path.join(base, name), 0o755)
                except OSError:
                    pass
        shutil.rmtree(self.root, ignore_errors=True)

    def env(self, **extra):
        env = {
            "HOME": self.home,
            "PATH": BASE_PATH,
            "COMPOUND_HOME": self.chome,
            "COMPOUND_CLAUDE_DIR": self.claude,
            "COMPOUND_PROJECT": self.project,
            "COMPOUND_NOW": str(NOW),
            "COMPOUND_NO_SURFER": "1",
            "CLAUDE_CODE_SESSION_ID": "sess-0001-aaaa",
            "GH_CONFIG_DIR": os.path.join(self.home, "gh-config"),
            "XDG_STATE_HOME": os.path.join(self.home, "gh-config", "state"),
            "XDG_DATA_HOME": os.path.join(self.home, "gh-config", "data"),
            "XDG_CACHE_HOME": os.path.join(self.home, "gh-config", "cache"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "LC_ALL": "C",
            # `created` and `updated` are LOCAL dates, so the zone is pinned with the clock.
            "TZ": "UTC",
        }
        for key, value in extra.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = str(value)
        return env

    def run(self, *args, **kw):
        """Run the CLI. stdin is always given, so nothing can block on a terminal."""
        stdin = kw.pop("stdin", "")
        cwd = kw.pop("cwd", self.project)
        script = kw.pop("script", self.script)
        env = self.env(**kw)
        return subprocess.run(
            [sys.executable, script] + list(args), input=stdin, cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=300)

    def json(self, *args, **kw):
        proc = self.run(*args, **kw)
        if proc.returncode != 0:
            raise AssertionError("%r exited %d: %s" % (args, proc.returncode, proc.stderr))
        return json.loads(proc.stdout)

    def add(self, name, when="Use when testing.", body="The lesson body.\n", *flags, **kw):
        proc = self.run("add", "--name", name, "--when", when, *flags, stdin=body, **kw)
        if proc.returncode != 0:
            raise AssertionError("add %s exited %d: %s" % (name, proc.returncode, proc.stderr))
        return proc

    def log(self, event, **kw):
        proc = self.run("log", stdin=json.dumps(event), **kw)
        if proc.returncode != 0:
            raise AssertionError("log exited %d: %s" % (proc.returncode, proc.stderr))
        return proc

    def read_events(self):
        if not os.path.exists(self.events):
            return []
        with open(self.events) as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def lesson_dir(self, name, level="project"):
        if level == "project":
            return os.path.join(self.project, ".claude", "compound", "lessons", name)
        if level == "user":
            return os.path.join(self.chome, "lessons", name)
        return os.path.join(self.pkg, "lessons", name)

    def skill_dir(self, name, level="project"):
        if level == "project":
            return os.path.join(self.project, ".claude", "skills", name)
        if level == "user":
            return os.path.join(self.claude, "skills", name)
        return os.path.join(self.pkg, "skills", name)

    def write_lesson(self, directory, name, description="Use when written by hand.",
                     body="A hand-written body.\n", extra=""):
        os.makedirs(directory)
        with open(os.path.join(directory, "SKILL.md"), "w") as handle:
            handle.write("---\nname: %s\ndescription: %s\n%s---\n%s" % (name, description, extra, body))

    def snapshot(self, top=None):
        """{relative path: bytes, or 'link -> target'} for everything under `top`."""
        top = top or self.root
        seen = {}
        # Apple's system Python keeps its bytecode cache under $HOME/Library/Caches, and
        # any Python may leave a __pycache__. Those are the interpreter's writes, not
        # compound's, so they are outside what a snapshot compares.
        interpreter = os.path.join(self.home, "Library")
        for base, dirs, files in os.walk(top):
            dirs[:] = [name for name in dirs
                       if name != "__pycache__" and os.path.join(base, name) != interpreter]
            for name in dirs + files:
                path = os.path.join(base, name)
                rel = os.path.relpath(path, top)
                if os.path.islink(path):
                    seen[rel] = "link -> " + os.readlink(path)
                elif os.path.isfile(path):
                    with open(path, "rb") as handle:
                        seen[rel] = handle.read()
                else:
                    seen[rel] = "dir"
        return seen


class Case(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.box = Sandbox()
        self.addCleanup(self.box.close)

    def assertExit(self, proc, code):
        self.assertEqual(proc.returncode, code,
                         "exit %d, wanted %d\nstdout: %s\nstderr: %s" % (
                             proc.returncode, code, proc.stdout, proc.stderr))


def git(*args, **kw):
    cwd = kw.pop("cwd", None)
    env = dict(os.environ)
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "-c", "maintenance.auto=false", "-c", "gc.auto=0",
         "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false"] + list(args),
        cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, timeout=120)


def git_ok(*args, **kw):
    proc = git(*args, **kw)
    if proc.returncode != 0:
        raise AssertionError("git %s: %s" % (" ".join(args), proc.stderr))
    return proc.stdout.strip()


SURFER_URL = "https://github.com/ContextLab/claude-history-surfer.git"
_reachable = []


def surfer_reachable():
    """Whether the real history-surfer repository can be cloned from here, asked once."""
    if not _reachable:
        try:
            proc = git("ls-remote", "--heads", SURFER_URL)
            _reachable.append(proc.returncode == 0)
        except (OSError, subprocess.SubprocessError):
            _reachable.append(False)
    return _reachable[0]


class SupportTest(Case):
    def test_the_sandbox_runs_a_copy_and_not_the_checkout(self):
        self.assertTrue(os.path.isfile(self.box.script))
        self.assertNotEqual(os.path.realpath(self.box.script), os.path.realpath(SCRIPT))
        rows = self.box.json("list", "--json")
        self.assertEqual(rows, [], "a fresh sandbox has an empty store, general level included")

    def test_no_command_is_a_usage_error(self):
        proc = self.box.run()
        self.assertExit(proc, 2)
        self.assertIn("usage", proc.stderr)

    def test_an_unknown_command_is_a_usage_error(self):
        proc = self.box.run("frobnicate")
        self.assertExit(proc, 2)

    def test_the_script_is_standard_library_only(self):
        with open(SCRIPT) as handle:
            text = handle.read()
        allowed = {"json", "os", "re", "sys", "time", "datetime", "subprocess", "shutil", "fcntl",
                   "tempfile", "argparse", "select", "stat", "math", "hashlib"}
        import re as _re
        found = set(_re.findall(r"^\s*import (\w+)", text, _re.M))
        found |= set(_re.findall(r"^\s*from (\w+) import", text, _re.M))
        self.assertEqual(found - allowed, set())

    def test_a_reader_that_goes_away_is_not_an_error(self):
        """`compound list | head -1`: the pipe closes under the writer. No traceback and no
        "Exception ignored" line, with or without the help text."""
        for index in range(40):
            self.box.add("lesson-%02d" % index)
        for args in (["--help"], ["list"], ["events", "--json"], ["add", "--help"]):
            reader, writer = os.pipe()
            os.close(reader)
            try:
                proc = subprocess.run([sys.executable, self.box.script] + args, stdin=subprocess.DEVNULL, stdout=writer,
                                      stderr=subprocess.PIPE, cwd=self.box.project, env=self.box.env(),
                                      universal_newlines=True, timeout=60)
            finally:
                os.close(writer)
            self.assertEqual(proc.stderr, "", args)
            self.assertEqual(proc.returncode, 0, args)

    def test_a_bad_pinned_clock_is_refused(self):
        proc = self.box.run("skip", "--why", "x", COMPOUND_NOW="yesterday")
        self.assertExit(proc, 2)
        self.assertIn("COMPOUND_NOW", proc.stderr)
        self.assertEqual(self.box.read_events(), [])


if __name__ == "__main__":
    unittest.main()
