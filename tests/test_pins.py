#!/usr/bin/env python3
"""A lesson is proposed to the general pool with its pins: `compound promote --to general
--pins FILE --summary TEXT`.

The pool's suite holds every shipped lesson to a file that says what it is meant to be
(tests/pool/lessons/<name>.json) and to a row in two tables. These tests publish to a
local bare repository (COMPOUND_UPSTREAM_GIT), so nothing here goes to GitHub, and the
last one publishes into a copy of this checkout and runs that copy's own pool tests on
the branch the proposal made.
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

from test_support import ECHO_PASSES, ECHO_STOPS, REPO, Case, echo_pin_flags, git_ok, pin_flags

ANCHOR = r"(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)"
README = """# A pool

### The lessons that ship with compound

Some words.

| Lesson | Applies | What it does |
|-|-|-|
| `taken-name` | everywhere | the pool's own |

After the table.

| Skill | Claude uses it when | What it has Claude do |
|-|-|-|
| `learn` | a lesson is owed | record it |

## Next
"""
DESIGN = """# Design

## Levels

| Lesson | Form |
|-|-|
| `not-this-table` | x |

## The general pool

| Lesson | Form | Applies where | Stops or answers |
|-|-|-|-|
| `taken-name` | lesson | everywhere | the pool's own |

Words after.

## Later
"""


class PinCase(Case):
    def setUp(self):
        Case.setUp(self)
        self.git_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
                        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
        self.box.add("zsh-equals-word", "Use when a zsh line has a bare equals word.", "Quote the word.\n",
                     "--level", "user", "--match", r"echo\s+=+", "--shell", "zsh")
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user")

    def pool(self, name="upstream", build=None, documents=True):
        seedrepo = os.path.join(self.box.root, name + "-seed")
        os.makedirs(os.path.join(seedrepo, "lessons", "taken-name"))
        self.write(seedrepo, "lessons/taken-name/SKILL.md",
                   "---\nname: taken-name\ndescription: Use when taken.\n---\nThe pool's own.\n")
        if documents:
            self.write(seedrepo, "README.md", README)
            self.write(seedrepo, "docs/design.md", DESIGN)
        if build:
            build(seedrepo)
        git_ok("init", cwd=seedrepo)
        git_ok("add", "-A", cwd=seedrepo)
        git_ok("commit", "-m", "the pool", cwd=seedrepo)
        upstream = os.path.join(self.box.root, name + ".git")
        git_ok("clone", "--bare", seedrepo, upstream)
        return upstream

    def write(self, base, rel, text):
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def promote(self, name, upstream, *flags):
        return self.box.run("promote", name, "--to", "general", "--yes", "--upstream", upstream, *flags,
                            COMPOUND_UPSTREAM_GIT=upstream, **self.git_env)

    def branches(self, upstream):
        return sorted(git_ok("branch", "--list", "--format=%(refname:short)", cwd=upstream).split())

    def published(self, upstream, branch, rel):
        return subprocess.run(["git", "show", "%s:%s" % (branch, rel)], cwd=upstream, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True).stdout.decode("utf-8")

    def zsh_flags(self, **pins):
        return echo_pin_flags(self.box.root, shell=["zsh"], **pins)


class PinsAreAskedForTest(PinCase):
    def test_the_plan_says_a_lesson_without_pins_is_not_proposable(self):
        plan = self.box.json("promote", "plain-note", "--to", "general", "--json")
        self.assertEqual(plan["unpinned"], ["it has no pins (--pins FILE)",
                                            "it has no one-line summary for the pool's tables (--summary TEXT)"])
        self.assertEqual((plan["pins"], plan["summary"]), (None, None))
        self.assertEqual(plan["files"], ["lessons/plain-note/SKILL.md"])
        out = self.box.run("promote", "plain-note", "--to", "general").stdout
        self.assertIn("NOT PROPOSABLE as it is: it has no pins (--pins FILE)", out)
        self.assertIn('"stops"', out, "the plan says what a pin file is")

    def test_yes_without_pins_or_without_a_summary_sends_nothing(self):
        upstream = self.pool()
        pins, path, _summary, text = pin_flags(self.box.root)
        for flags, words in (((), "it has no pins"), ((pins, path), "it has no one-line summary"),
                             (("--summary", text), "it has no pins")):
            proc = self.promote("plain-note", upstream, *flags)
            self.assertExit(proc, 2)
            self.assertIn(words, proc.stderr)
            self.assertIn("Nothing was sent", proc.stderr)
        self.assertEqual(self.branches(upstream), ["main"])
        self.assertFalse(any(event["type"] == "promote" for event in self.box.read_events()))

    def test_a_file_that_is_not_a_pin_file_is_refused_with_what_is_wrong(self):
        whole = {"kind": "guard", "platform": [], "shell": ["zsh"], "stops": ECHO_STOPS, "passes": ECHO_PASSES}

        def without(key):
            return dict((k, v) for k, v in whole.items() if k != key)

        cases = [
            ("[]", "it is not a JSON object"),
            ("{not json", "does not read as JSON"),
            (json.dumps(without("passes")), "it lacks `passes`"),
            (json.dumps(dict(whole, summary="x")), "it has keys a pin file does not: summary"),
            (json.dumps(dict(whole, kind="probe")), '`kind` is neither "lesson" nor "guard"'),
            (json.dumps(dict(whole, shell="zsh")), "`shell` is not a list of non-empty strings"),
            (json.dumps(dict(whole, stops=ECHO_STOPS + [""])), "`stops` is not a list of non-empty strings"),
            (json.dumps(dict(whole, passes=ECHO_PASSES + ["pwd"])), "`passes` names one entry twice"),
            (json.dumps(dict(whole, stops=ECHO_STOPS[:4])), "a guard needs at least 5 `stops` and it has 4"),
            (json.dumps(dict(whole, passes=ECHO_PASSES[:7])), "a guard needs at least 8 `passes` and it has 7"),
            (json.dumps(dict(whole, kind="lesson")), "a lesson with no pattern stops nothing"),
        ]
        for text, words in cases:
            path = self.write(self.box.root, "bad.json", text)
            for flags in ((), ("--yes",)):
                proc = self.box.run("promote", "zsh-equals-word", "--to", "general", "--pins", path, "--summary", "s",
                                    *flags)
                self.assertExit(proc, 2)
                self.assertIn(words, proc.stderr, text)
        proc = self.box.run("promote", "zsh-equals-word", "--to", "general", "--pins",
                            os.path.join(self.box.root, "absent.json"), "--summary", "s")
        self.assertExit(proc, 2)
        self.assertIn("cannot be read", proc.stderr)

    def test_a_summary_that_cannot_be_a_table_cell_is_refused(self):
        flags = pin_flags(self.box.root)[:2]
        for summary, words in (("  ", "it is empty"), ("two\nlines", "it is more than one line"),
                               ("a | b", "it holds a `|`"), ("x" * 301, "it is 301 characters long")):
            proc = self.box.run("promote", "plain-note", "--to", "general", "--summary", summary, *flags)
            self.assertExit(proc, 2)
            self.assertIn(words, proc.stderr)

    def test_pins_go_with_a_lesson_proposed_to_general_only(self):
        flags = pin_flags(self.box.root)
        self.box.add("project-note", "Use when in the project.", "Body.\n")
        proc = self.box.run("promote", "project-note", "--to", "user", *flags)
        self.assertExit(proc, 2)
        self.assertIn("--pins and --summary go with --to general only", proc.stderr)
        self.assertTrue(os.path.isdir(self.box.lesson_dir("project-note", "project")))
        skill = os.path.join(self.box.claude, "skills", "my-skill")
        os.makedirs(skill)
        self.write(skill, "SKILL.md", "---\nname: my-skill\ndescription: Use when testing a skill.\n---\nDo it.\n")
        proc = self.box.run("promote", "my-skill", "--to", "general", *flags)
        self.assertExit(proc, 2)
        self.assertIn("is a skill", proc.stderr)
        # A skill is proposed as before, with none.
        plan = self.box.json("promote", "my-skill", "--to", "general", "--json")
        self.assertEqual((plan["unpinned"], plan["files"]), ([], ["skills/my-skill/SKILL.md"]))


class PinsAreCheckedAgainstTheLessonTest(PinCase):
    def refused(self, name, flags, *words):
        upstream = self.pool("pool-%d" % len(os.listdir(self.box.root)))
        plan = self.box.json("promote", name, "--to", "general", "--json", *flags)
        proc = self.promote(name, upstream, *flags)
        self.assertExit(proc, 2)
        for one in words:
            self.assertIn(one, proc.stderr)
            self.assertTrue(any(one in problem for problem in plan["unpinned"]), (one, plan["unpinned"]))
        self.assertEqual(self.branches(upstream), ["main"])

    def test_the_kind_is_the_lessons(self):
        self.refused("zsh-equals-word", pin_flags(self.box.root, shell=["zsh"]),
                     "the pins say `lesson` and the lesson is a guard: it has a `match`")
        self.refused("plain-note", echo_pin_flags(self.box.root),
                     "the pins say `guard` and the lesson is a lesson: it has no `match`")

    def test_the_condition_is_the_lessons(self):
        self.refused("zsh-equals-word", echo_pin_flags(self.box.root),
                     'the pins say `shell` [] and the lesson\'s header says ["zsh"]')
        self.refused("plain-note", pin_flags(self.box.root, platform=["darwin"]),
                     'the pins say `platform` ["darwin"] and the lesson\'s header says []')

    def test_every_command_the_pins_name_does_what_they_say(self):
        self.refused("zsh-equals-word", self.zsh_flags(stops=ECHO_STOPS + ["echo done"]),
                     'the pins say it stops "echo done" and its pattern does not')
        self.refused("zsh-equals-word", self.zsh_flags(passes=ECHO_PASSES + ["x=1; echo ==="]),
                     'the pins say "x=1; echo ===" runs and its pattern stops it')
        # A mention of the command is not a call of it: `check` reads it so, and so do the pins.
        self.refused("zsh-equals-word", self.zsh_flags(stops=ECHO_STOPS + ["git commit -m 'echo ==== fails'"]),
                     "the pins say it stops \"git commit -m 'echo ==== fails'\" and its pattern does not")


class PublishedWithItsPinsTest(PinCase):
    def test_the_branch_holds_the_lesson_its_pins_and_a_row_in_each_table(self):
        upstream = self.pool()
        flags = self.zsh_flags(summary="stops `echo ====`, which zsh reads as a command to look up")
        plan = self.box.json("promote", "zsh-equals-word", "--to", "general", "--json", *flags)
        self.assertEqual(plan["unpinned"], [])
        self.assertEqual(plan["files"], ["lessons/zsh-equals-word/SKILL.md", "tests/pool/lessons/zsh-equals-word.json"])
        self.assertIn("- `tests/pool/lessons/zsh-equals-word.json`", plan["body"])
        self.assertIn("In the pool's tables: stops `echo ====`", plan["body"])
        self.assertIn('"kind": "guard"', plan["body"])
        proc = self.promote("zsh-equals-word", upstream, "--json", *flags)
        self.assertExit(proc, 0)
        done = json.loads(proc.stdout)
        self.assertEqual(done["tables"], ["README.md", "docs/design.md"])
        branch = "compound/lesson-zsh-equals-word"
        self.assertEqual(self.branches(upstream), [branch, "main"])
        pins = {"kind": "guard", "platform": [], "shell": ["zsh"], "stops": ECHO_STOPS, "passes": ECHO_PASSES}
        text = self.published(upstream, branch, "tests/pool/lessons/zsh-equals-word.json")
        self.assertEqual(text, json.dumps(pins, indent=2, ensure_ascii=False) + "\n")
        self.assertEqual(list(json.loads(text)), ["kind", "platform", "shell", "stops", "passes"])
        row = "stops `echo ====`, which zsh reads as a command to look up"
        self.assertEqual(self.published(upstream, branch, "README.md"), README.replace(
            "| `taken-name` | everywhere | the pool's own |\n",
            "| `taken-name` | everywhere | the pool's own |\n| `zsh-equals-word` | zsh | %s |\n" % row))
        self.assertEqual(self.published(upstream, branch, "docs/design.md"), DESIGN.replace(
            "| `taken-name` | lesson | everywhere | the pool's own |\n",
            "| `taken-name` | lesson | everywhere | the pool's own |\n"
            "| `zsh-equals-word` | guard | `shell: zsh` | %s |\n" % row))
        tree = git_ok("ls-tree", "-r", "--name-only", branch, cwd=upstream).splitlines()
        self.assertEqual(sorted(tree), ["README.md", "docs/design.md", "lessons/taken-name/SKILL.md",
                                        "lessons/zsh-equals-word/SKILL.md", "tests/pool/lessons/zsh-equals-word.json"])
        self.assertEqual(git_ok("rev-list", "--count", "main..%s" % branch, cwd=upstream), "1")

    def test_the_cells_say_where_a_lesson_applies(self):
        self.box.add("mac-note", "Use when on a Mac in zsh.", "Body.\n", "--level", "user",
                     "--platform", "darwin", "--shell", "zsh")
        upstream = self.pool()
        for name, pins, readme, design in (
                ("plain-note", {}, "everywhere", "everywhere"),
                ("mac-note", {"platform": ["darwin"], "shell": ["zsh"]}, "macOS, zsh",
                 "`platform: darwin`, `shell: zsh`")):
            self.assertExit(self.promote(name, upstream, *pin_flags(self.box.root, summary="recalled then", **pins)), 0)
            branch = "compound/lesson-" + name
            self.assertIn("| `%s` | %s | recalled then |\n" % (name, readme), self.published(upstream, branch, "README.md"))
            self.assertIn("| `%s` | lesson | %s | recalled then |\n" % (name, design),
                          self.published(upstream, branch, "docs/design.md"))

    def test_a_pool_with_no_such_tables_gets_the_lesson_and_the_pins(self):
        upstream = self.pool(documents=False)
        proc = self.promote("plain-note", upstream, "--json", *pin_flags(self.box.root))
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout)["tables"], [])
        tree = git_ok("ls-tree", "-r", "--name-only", "compound/lesson-plain-note", cwd=upstream).splitlines()
        self.assertEqual(sorted(tree), ["lessons/plain-note/SKILL.md", "lessons/taken-name/SKILL.md",
                                        "tests/pool/lessons/plain-note.json"])

    def test_a_credential_in_the_pins_or_the_summary_is_not_published(self):
        key = "ghp_" + "A1b2C3d4E5" * 3
        upstream = self.pool()
        with_key = self.zsh_flags(passes=ECHO_PASSES + ["curl -H 'Authorization: token %s' https://h" % key])
        in_summary = self.zsh_flags(name="other.json", summary="uses %s" % key)
        for flags, label in ((with_key, "the pins: "), (in_summary, "the summary: ")):
            plan = self.box.json("promote", "zsh-equals-word", "--to", "general", "--json", *flags)
            self.assertEqual(len(plan["secrets"]), 1, plan["secrets"])
            self.assertTrue(plan["secrets"][0].startswith(label), plan["secrets"])
            proc = self.promote("zsh-equals-word", upstream, *flags)
            self.assertExit(proc, 2)
            self.assertNotIn(key, proc.stderr)
        self.assertEqual(self.branches(upstream), ["main"])

    def test_a_pool_whose_pin_directory_is_a_link_gets_nothing_written_through_it(self):
        landing = os.path.join(self.box.root, "landing")
        os.makedirs(landing)

        def build(seedrepo):
            os.makedirs(os.path.join(seedrepo, "tests", "pool"))
            os.symlink(landing, os.path.join(seedrepo, "tests", "pool", "lessons"))

        upstream = self.pool(build=build)
        proc = self.promote("plain-note", upstream, *pin_flags(self.box.root))
        self.assertExit(proc, 1)
        self.assertIn("a symbolic link", proc.stderr)
        self.assertEqual(os.listdir(landing), [])
        self.assertEqual(self.branches(upstream), ["main"])

    def test_a_pool_whose_tests_is_a_link_gets_no_directory_made_through_it(self):
        """Not even an empty one: each part of the path is looked at before it is made."""
        for depth, parts in enumerate((("tests",), ("tests", "pool"))):
            landing = os.path.join(self.box.root, "landing-%d" % depth)
            os.makedirs(landing)

            def build(seedrepo, parts=parts, landing=landing):
                os.makedirs(os.path.join(seedrepo, *parts[:-1]), exist_ok=True)
                os.symlink(landing, os.path.join(seedrepo, *parts))

            upstream = self.pool("linked-%d" % depth, build=build)
            proc = self.promote("zsh-equals-word", upstream, *self.zsh_flags())
            self.assertExit(proc, 1)
            self.assertIn("a symbolic link", proc.stderr)
            self.assertEqual(os.listdir(landing), [], "something was made where the link leads")
            self.assertEqual(self.branches(upstream), [ "main"])

    def test_pins_of_the_pool_behind_a_link_are_not_read(self):
        """A pool cannot have this command read a file from elsewhere on the machine as
        its pins and repeat a command from it."""
        elsewhere = os.path.join(self.box.root, "elsewhere")
        self.write(elsewhere, "ordinary.json", json.dumps(["echo ==== zzmarker"]))

        def build(seedrepo):
            os.makedirs(os.path.join(seedrepo, "tests"))
            os.symlink(elsewhere, os.path.join(seedrepo, "tests", "pool"))

        upstream = self.pool(build=build)
        proc = self.promote("zsh-equals-word", upstream, *self.zsh_flags())
        self.assertExit(proc, 1)
        self.assertNotIn("zzmarker", proc.stderr + proc.stdout)
        self.assertEqual(sorted(os.listdir(elsewhere)), ["ordinary.json"])


class PinsFitThePoolTest(PinCase):
    """What the pool's own suite would refuse is refused before anything is pushed."""

    def misfit(self, build, *words):
        upstream = self.pool(build=build)
        proc = self.promote("zsh-equals-word", upstream, *self.zsh_flags())
        self.assertExit(proc, 2)
        for one in words:
            self.assertIn(one, proc.stderr)
        self.assertIn("Nothing was pushed", proc.stderr)
        self.assertEqual(self.branches(upstream), ["main"])
        self.assertFalse(any(event["type"] == "promote" for event in self.box.read_events()))

    def test_a_pattern_that_stops_an_everyday_command_of_the_pool(self):
        self.misfit(lambda seedrepo: self.write(seedrepo, "tests/pool/ordinary.json",
                                                json.dumps(["git status", "make && echo ==== && make test"])),
                    'its pattern stops "make && echo ==== && make test", an everyday command of the pool')

    def test_a_pattern_that_stops_a_command_another_lessons_pins_hold(self):
        other = {"kind": "lesson", "platform": [], "shell": [], "stops": [], "passes": []}
        guard = dict(other, kind="guard", stops=["a", "b", "c", "d", "e"],
                     passes=["1", "2", "3", "4", "5", "6", "7", "echo ====== ok"])

        def build(seedrepo):
            self.write(seedrepo, "tests/pool/lessons/taken-name.json", json.dumps(other))
            self.write(seedrepo, "tests/pool/lessons/their-guard.json", json.dumps(guard))

        self.misfit(build, 'its pattern stops "echo ====== ok", a command the pins of `their-guard` hold')

    def test_a_command_of_the_pins_that_a_guard_of_the_pool_stops(self):
        def build(seedrepo):
            self.write(seedrepo, "lessons/no-pwd/SKILL.md",
                       "---\nname: no-pwd\ndescription: Use when pwd is called.\nmatch: [\"%spwd\"]\n---\nNo.\n"
                       % ANCHOR.replace("\\", "\\\\"))

        self.misfit(build, 'the pool\'s `no-pwd` stops "pwd", a command of these pins')

    def test_the_pool_is_read_and_never_run(self):
        """A file of the clone that is not what it should be is passed over, and nothing in
        the clone is executed: a pool's test files are data to this command."""
        marker = os.path.join(self.box.root, "ran")

        def build(seedrepo):
            self.write(seedrepo, "tests/pool/ordinary.json", "{broken")
            self.write(seedrepo, "tests/pool/lessons/odd.json", "[1, 2]")
            self.write(seedrepo, "tests/test_general_pool.py", "open(%r, 'w').close()\n" % marker)
            self.write(seedrepo, "conftest.py", "open(%r, 'w').close()\n" % marker)

        upstream = self.pool(build=build)
        self.assertExit(self.promote("zsh-equals-word", upstream, *self.zsh_flags()), 0)
        self.assertFalse(os.path.exists(marker))


class ProposalPassesThePoolsOwnSuiteTest(PinCase):
    def test_a_guard_proposed_into_a_copy_of_this_checkout_passes_its_pool_and_docs_tests(self):
        """The whole of it: this checkout is the pool, a guard that applies everywhere is
        proposed to it, and the branch the proposal made passes the two test files that
        hold a shipped lesson to its pins and to the tables."""
        seedrepo = os.path.join(self.box.root, "this-seed")
        listed = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=REPO,
                                stdout=subprocess.PIPE, check=True).stdout.decode("utf-8").split("\0")
        for rel in listed:
            source = os.path.join(REPO, rel)
            if rel and os.path.isfile(source) and not os.path.islink(source):
                os.makedirs(os.path.dirname(os.path.join(seedrepo, rel)), exist_ok=True)
                shutil.copy2(source, os.path.join(seedrepo, rel))
        git_ok("init", cwd=seedrepo)
        git_ok("add", "-A", cwd=seedrepo)
        git_ok("commit", "-m", "the pool", cwd=seedrepo)
        upstream = os.path.join(self.box.root, "this.git")
        git_ok("clone", "--bare", seedrepo, upstream)

        self.box.add("frobnicate-is-retired", "Use when calling the frobnicate command line.",
                     "Call `frob2`; `frobnicate` exits 1 at login.\n", "--level", "user",
                     "--match", ANCHOR + r"frobnicate(\s|$)")
        flags = pin_flags(
            self.box.root, kind="guard",
            stops=["frobnicate -p hello", "cd /tmp && frobnicate", "ls; frobnicate x", "out=$(frobnicate -p q)",
                   "if true; then frobnicate -p x; fi"],
            passes=["frob2 -p hello", "echo frobnicate", "grep -rn frobnicate src/", "git commit -m 'drop frobnicate'",
                    "frobnicate2 run", "which frob2", "cat frobnicate.md", "pip install frobnicate-sdk"],
            summary="stops a call to `frobnicate`, which no longer logs in; `frob2` takes its place")
        proc = self.promote("frobnicate-is-retired", upstream, "--json", *flags)
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout)["tables"], ["README.md", "docs/design.md"])

        checkout = os.path.join(self.box.root, "proposed")
        git_ok("clone", "--branch", "compound/lesson-frobnicate-is-retired", upstream, checkout)
        env = dict((key, os.environ[key]) for key in ("PATH", "HOME", "TMPDIR", "LANG") if key in os.environ)
        for test in ("test_general_pool.py", "test_docs.py"):
            ran = subprocess.run([sys.executable, os.path.join("tests", test)], cwd=checkout, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=900)
            self.assertEqual(ran.returncode, 0, "%s on the proposed branch:\n%s" % (test, ran.stdout[-4000:]))
        # Without its pins the same lesson fails that suite: the pins are what the suite holds it to.
        os.remove(os.path.join(checkout, "tests", "pool", "lessons", "frobnicate-is-retired.json"))
        ran = subprocess.run([sys.executable, os.path.join("tests", "test_general_pool.py"),
                              "ShippedPoolTest.test_every_shipped_lesson_parses_and_is_the_kind_and_condition_meant"],
                             cwd=checkout, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True, timeout=900)
        self.assertNotEqual(ran.returncode, 0)


if __name__ == "__main__":
    unittest.main()
