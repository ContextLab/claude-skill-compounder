#!/usr/bin/env python3
"""The general pool: a lesson's platform and shell condition, the per-user switch for one
general lesson, what a general lesson that keeps recurring owes (nothing), one refusal when
a user's own guard and a general one hit the same call, and the lessons this package ships.

The shipped lessons are tested through the real `bin/compound` of this checkout, so its
`general` level is this repository's own `lessons/`; the user level, the event log and the
project are a sandbox.
"""

import json
import os
import sys
import unittest

from test_support import NOW, REPO, SCRIPT, Case

ANCHOR = r"(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)"
ECHO = ANCHOR + r"echo\s+=+"
ZSH = {"SHELL": "/bin/zsh", "COMPOUND_PLATFORM": "darwin"}
BASH_LINUX = {"SHELL": "/bin/bash", "COMPOUND_PLATFORM": "linux"}


def here():
    """The name the CLI gives this machine's platform."""
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform in ("win32", "cygwin", "msys"):
        return "windows"
    return sys.platform


class PoolCase(Case):
    def check(self, command, tool="Bash", script=None, **env):
        kw = dict(env)
        if script:
            kw["script"] = script
        proc = self.box.run("check", "--guards", stdin=json.dumps({"tool": tool, "input": {"command": command}}), **kw)
        self.assertExit(proc, 0)
        return json.loads(proc.stdout)

    def hits(self, command, **env):
        return [hit["name"] for hit in self.check(command, **env)["hits"]]

    def row(self, name, **env):
        rows = [row for row in self.box.json("list", "--json", **env) if row["name"] == name]
        self.assertEqual(len(rows), 1, name)
        return rows[0]

    def ship(self, name, *flags, **kw):
        """A lesson at the general level of the sandbox's package copy: written at the user
        level by the CLI, then moved, as a lesson reaches the pool."""
        self.box.add(name, kw.pop("when", "Use when testing."), kw.pop("body", "The general body.\n"),
                     "--level", "user", *flags)
        target = self.box.lesson_dir(name, "general")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.rename(self.box.lesson_dir(name, "user"), target)
        return target

    def recall(self, name, session=None, ts=NOW + 60, **fields):
        """One recall, in a session of its own unless one is named: a session counts once
        toward ineffective and recurring."""
        stamp = "2026-09-21T14:%02d:00Z" % (15 + (ts - NOW) // 60)
        event = {"type": "recall", "lesson": name, "session": session or "sess-%s" % stamp[11:16], "tool": "Bash",
                 "ts": stamp}
        event.update(fields)
        self.box.log(event)


class ConditionTest(PoolCase):
    def frontmatter(self, name, level="user"):
        with open(os.path.join(self.box.lesson_dir(name, level), "SKILL.md")) as handle:
            return handle.read().split("---\n")[1]

    def test_add_writes_the_condition_into_the_frontmatter(self):
        self.box.add("zsh-thing", "Use when zsh.", "Body.\n", "--level", "user", "--shell", "zsh",
                     "--platform", "darwin", "--platform", "linux")
        head = self.frontmatter("zsh-thing")
        self.assertIn("\nshell: zsh\n", head)
        self.assertIn("\nplatform: darwin, linux\n", head)
        row = self.row("zsh-thing", **ZSH)
        self.assertEqual((row["platform"], row["shell"], row["applies"]), (["darwin", "linux"], ["zsh"], True))

    def test_a_lesson_without_a_condition_applies_everywhere(self):
        self.box.add("plain", "Use when plain.", "Body.\n", "--match", ECHO)
        row = self.row("plain", **BASH_LINUX)
        self.assertEqual((row["platform"], row["shell"], row["applies"]), ([], [], True))
        self.assertEqual(self.hits("echo ====", **BASH_LINUX), ["plain"])
        self.assertEqual(self.hits("echo ====", SHELL=None), ["plain"])

    def test_a_shell_condition_decides_whether_the_guard_is_one(self):
        self.box.add("zsh-eq", "Use when zsh.", "Body.\n", "--match", ECHO, "--shell", "zsh")
        self.assertEqual(self.hits("echo ====", SHELL="/bin/zsh"), ["zsh-eq"])
        self.assertEqual(self.hits("echo ====", SHELL="/opt/homebrew/bin/zsh"), ["zsh-eq"])
        reply = self.check("echo ====", SHELL="/bin/bash")
        self.assertEqual((reply["hits"], reply["guards"], reply["tools"]), ([], 0, []))

    def test_the_shell_is_claude_codes_override_then_the_login_shell_then_unknown(self):
        self.box.add("zsh-eq", "Use when zsh.", "Body.\n", "--match", ECHO, "--shell", "zsh")
        self.assertEqual(self.hits("echo ====", SHELL="/bin/bash", CLAUDE_CODE_SHELL="/bin/zsh"), ["zsh-eq"])
        self.assertEqual(self.hits("echo ====", SHELL="/bin/zsh", CLAUDE_CODE_SHELL="/bin/bash"), [])
        self.assertEqual(self.hits("echo ====", SHELL="/bin/zsh", CLAUDE_CODE_SHELL="bash",
                                   COMPOUND_SHELL="zsh"), ["zsh-eq"])
        # No SHELL at all: the shell is unknown, and a lesson that needs one does not apply.
        self.assertEqual(self.hits("echo ====", SHELL=None), [])
        self.assertFalse(self.row("zsh-eq", SHELL=None)["applies"])

    def test_the_shell_setting_is_read_from_the_settings_file_too(self):
        self.box.add("zsh-eq", "Use when zsh.", "Body.\n", "--match", ECHO, "--shell", "zsh")
        with open(self.box.settings, "w") as handle:
            json.dump({"env": {"COMPOUND_SHELL": "zsh"}}, handle)
        self.assertEqual(self.hits("echo ====", SHELL="/bin/bash"), ["zsh-eq"])

    def test_a_platform_condition_decides_whether_the_guard_is_one(self):
        self.box.add("mac-only", "Use when macOS.", "Body.\n", "--match", ECHO, "--platform", "darwin")
        self.assertEqual(self.hits("echo ====", COMPOUND_PLATFORM="darwin"), ["mac-only"])
        self.assertEqual(self.hits("echo ====", COMPOUND_PLATFORM="linux"), [])
        # With no override it is this machine's platform.
        self.assertEqual(self.hits("echo ===="), ["mac-only"] if here() == "darwin" else [])
        self.box.add("here-only", "Use when here.", "Body.\n", "--match", ECHO, "--platform", here())
        self.assertIn("here-only", self.hits("echo ===="))

    def test_both_conditions_must_hold(self):
        self.box.add("both", "Use when both.", "Body.\n", "--match", ECHO, "--platform", "darwin", "--shell", "zsh")
        self.assertEqual(self.hits("echo ====", **ZSH), ["both"])
        self.assertEqual(self.hits("echo ====", SHELL="/bin/bash", COMPOUND_PLATFORM="darwin"), [])
        self.assertEqual(self.hits("echo ====", SHELL="/bin/zsh", COMPOUND_PLATFORM="linux"), [])

    def test_a_lesson_that_does_not_apply_is_listed_and_marked_and_not_found(self):
        self.box.add("zsh-eq", "Use when a separator fails in zsh.", "Quote the separator.\n", "--shell", "zsh")
        row = self.row("zsh-eq", **BASH_LINUX)
        self.assertFalse(row["applies"])
        listing = self.box.run("list", **BASH_LINUX).stdout
        line = [text for text in listing.splitlines() if "zsh-eq" in text][0]
        self.assertIn("not here", line)
        shown = self.box.run("show", "zsh-eq", **BASH_LINUX)
        self.assertExit(shown, 0)
        self.assertIn("does not apply here: it is for the shell zsh, and this is bash", shown.stdout)
        self.assertIn("Quote the separator.", shown.stdout)
        self.assertFalse(self.box.json("show", "zsh-eq", "--json", **BASH_LINUX)["applies"])
        status = json.loads(self.box.run("status", "--json", **BASH_LINUX).stdout)
        flags = {row["name"]: row["flag"] for row in status["lessons"]}
        self.assertEqual(flags["zsh-eq"], "not here")
        self.assertIn("not here", [text for text in self.box.run("status", **BASH_LINUX).stdout.splitlines()
                                   if text.strip().startswith("zsh-eq")][0])
        found = self.box.json("find", "separator", "zsh", "--json", **BASH_LINUX)
        self.assertEqual(found["items"], [])
        found = self.box.json("find", "separator", "zsh", "--json", **ZSH)
        self.assertEqual([item["name"] for item in found["items"]], ["zsh-eq"])
        # Where it applies nothing marks it.
        self.assertNotIn("not here", self.box.run("list", **ZSH).stdout)
        self.assertNotIn("does not apply", self.box.run("show", "zsh-eq", **ZSH).stdout)

    def test_a_condition_value_must_be_a_name(self):
        for flag, value in (("--platform", "Mac OS"), ("--shell", "/bin/zsh"), ("--platform", ""), ("--shell", "a,b")):
            proc = self.box.run("add", "--name", "bad", "--when", "Use when.", "--body", "B.", flag, value)
            self.assertExit(proc, 2)
            self.assertIn(flag, proc.stderr)
        self.assertEqual(self.box.json("list", "--json"), [])

    def test_update_replaces_a_condition_and_no_condition_drops_it(self):
        self.box.add("cond", "Use when.", "Body.\n", "--shell", "zsh", "--platform", "darwin")
        self.assertExit(self.box.run("add", "--update", "--name", "cond", "--shell", "bash"), 0)
        head = self.frontmatter("cond", "project")
        self.assertIn("\nshell: bash\n", head)
        self.assertIn("\nplatform: darwin\n", head, "a condition --update does not name is kept")
        self.assertExit(self.box.run("add", "--update", "--name", "cond", "--no-condition"), 0)
        head = self.frontmatter("cond", "project")
        self.assertNotIn("shell:", head)
        self.assertNotIn("platform:", head)
        self.assertTrue(self.row("cond", **BASH_LINUX)["applies"])
        proc = self.box.run("add", "--update", "--name", "cond", "--no-condition", "--shell", "zsh")
        self.assertExit(proc, 2)
        self.assertIn("--no-condition", proc.stderr)

    def test_a_condition_that_does_not_read_is_reported_and_applies_nowhere(self):
        directory = self.box.lesson_dir("hand", "user")
        self.box.write_lesson(directory, "hand", extra='match: ["%s"]\nplatform: "Mac OS"\n' % ECHO.replace("\\", "\\\\"))
        self.assertEqual(self.hits("echo ====", **ZSH), [])
        status = json.loads(self.box.run("status", "--json").stdout)
        parse = [row for row in status["health"] if row["check"] == "lessons parse"][0]
        self.assertEqual(parse["status"], "FAIL")
        self.assertIn("platform", parse["detail"])

    def test_a_hand_written_condition_reads_in_the_forms_yaml_allows(self):
        for index, value in enumerate(("zsh", '"zsh"', "[zsh, bash]", "zsh, bash", '["zsh"]')):
            name = "hand-%d" % index
            self.box.write_lesson(self.box.lesson_dir(name, "user"), name, extra="shell: %s\n" % value)
            self.assertIn("zsh", self.row(name, SHELL="/bin/zsh")["shell"], value)
            self.assertTrue(self.row(name, SHELL="/bin/zsh")["applies"], value)
            self.assertFalse(self.row(name, SHELL="/bin/fish")["applies"], value)


class SwitchTest(PoolCase):
    def setUp(self):
        PoolCase.setUp(self)
        self.ship("shipped-guard", "--match", ECHO, when="Use when a separator is echoed.",
                  body="Quote the separator.\n")
        self.switch = os.path.join(self.box.chome, "disabled.json")

    def test_disable_switches_a_general_lesson_off_for_this_user(self):
        self.assertEqual(self.hits("echo ===="), ["shipped-guard"])
        proc = self.box.run("disable", "shipped-guard")
        self.assertExit(proc, 0)
        self.assertIn("disabled shipped-guard", proc.stdout)
        self.assertIn("compound enable shipped-guard", proc.stdout)
        with open(self.switch) as handle:
            self.assertEqual(json.load(handle), ["shipped-guard"])
        reply = self.check("echo ====")
        self.assertEqual((reply["hits"], reply["guards"]), ([], 0))
        row = self.row("shipped-guard")
        self.assertTrue(row["disabled"])
        line = [text for text in self.box.run("list").stdout.splitlines() if "shipped-guard" in text][0]
        self.assertIn("disabled", line)
        status = json.loads(self.box.run("status", "--json").stdout)
        self.assertEqual([row["flag"] for row in status["lessons"] if row["name"] == "shipped-guard"], ["disabled"])
        self.assertIn("disabled", [text for text in self.box.run("status").stdout.splitlines()
                                   if text.strip().startswith("shipped-guard")][0])
        self.assertEqual(self.box.json("find", "separator", "--json")["items"], [])
        self.assertIn("disabled for this user", self.box.run("show", "shipped-guard").stdout)
        # The lesson itself is untouched: the package is not written to.
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("shipped-guard", "general"), "SKILL.md")))

    def test_enable_switches_it_back_on(self):
        self.assertExit(self.box.run("disable", "shipped-guard"), 0)
        proc = self.box.run("enable", "shipped-guard")
        self.assertExit(proc, 0)
        self.assertIn("enabled shipped-guard", proc.stdout)
        self.assertEqual(self.hits("echo ===="), ["shipped-guard"])
        self.assertFalse(self.row("shipped-guard")["disabled"])
        self.assertFalse(os.path.exists(self.switch), "an empty switch file is removed")

    def test_both_are_idempotent_and_say_so(self):
        self.assertExit(self.box.run("disable", "shipped-guard"), 0)
        again = self.box.run("disable", "shipped-guard")
        self.assertExit(again, 0)
        self.assertIn("already disabled", again.stdout)
        self.assertExit(self.box.run("enable", "shipped-guard"), 0)
        again = self.box.run("enable", "shipped-guard")
        self.assertExit(again, 0)
        self.assertIn("not disabled", again.stdout)
        data = self.box.json("disable", "shipped-guard", "--json")
        self.assertEqual((data["name"], data["disabled"], data["changed"]), ("shipped-guard", True, True))

    def test_only_a_general_lesson_has_a_switch(self):
        self.box.add("mine", "Use when mine.", "Body.\n", "--level", "user")
        proc = self.box.run("disable", "mine")
        self.assertExit(proc, 2)
        self.assertIn("compound rm mine", proc.stderr)
        proc = self.box.run("disable", "no-such-lesson")
        self.assertExit(proc, 2)
        self.assertFalse(os.path.exists(self.switch))

    def test_a_name_the_pool_no_longer_ships_can_still_be_enabled(self):
        self.assertExit(self.box.run("disable", "shipped-guard"), 0)
        os.rename(self.box.lesson_dir("shipped-guard", "general"), os.path.join(self.box.root, "gone"))
        proc = self.box.run("enable", "shipped-guard")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.switch))

    def test_rm_refuses_a_general_lesson_and_names_the_switch(self):
        proc = self.box.run("rm", "shipped-guard")
        self.assertExit(proc, 2)
        self.assertIn("compound disable shipped-guard", proc.stderr)
        self.assertTrue(os.path.isdir(self.box.lesson_dir("shipped-guard", "general")))

    def test_a_switch_file_that_does_not_read_disables_nothing_and_is_reported(self):
        os.makedirs(self.box.chome, exist_ok=True)
        with open(self.switch, "w") as handle:
            handle.write("{not json")
        self.assertEqual(self.hits("echo ===="), ["shipped-guard"])
        proc = self.box.run("disable", "shipped-guard")
        self.assertExit(proc, 1)
        self.assertIn("disabled.json", proc.stderr)

    def test_purge_removes_the_switch_file_with_the_home(self):
        self.assertExit(self.box.run("install", "--bin-dir", self.box.bin), 0)
        self.assertExit(self.box.run("disable", "shipped-guard"), 0)
        proc = self.box.run("uninstall", "--purge")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.box.chome))


class GeneralDebtTest(PoolCase):
    def setUp(self):
        PoolCase.setUp(self)
        self.ship("shipped-note", when="Use when pip refuses.", body="Use a virtual environment.\n")

    def test_a_general_lesson_that_recurs_is_counted_and_never_ineffective(self):
        for minute in (1, 2, 3):
            self.recall("shipped-note", ts=NOW + 60 * minute)
        row = self.row("shipped-note")
        self.assertEqual(row["counts"]["recall"], 3)
        self.assertFalse(row["ineffective"])
        self.assertTrue(row["recurring"])
        shown = self.box.json("show", "shipped-note", "--json")
        self.assertEqual((shown["ineffective"], shown["recurring"], shown["recalls_since"]), (False, True, 3))
        line = [text for text in self.box.run("list").stdout.splitlines() if "shipped-note" in text][0]
        self.assertIn("recurring", line)
        self.assertNotIn("ineffective", line)

    def test_status_says_what_a_user_can_do_and_prints_no_command_that_cannot_work(self):
        for minute in (1, 2):
            self.recall("shipped-note", ts=NOW + 60 * minute)
        status = json.loads(self.box.run("status", "--json").stdout)
        self.assertEqual(status["open"]["ineffective"], [])
        self.assertEqual([(row["name"], row["recall"]) for row in status["open"]["recurring"]], [("shipped-note", 2)])
        self.assertEqual([row["flag"] for row in status["lessons"] if row["name"] == "shipped-note"], ["recurring"])
        text = self.box.run("status").stdout
        line = [one for one in text.splitlines() if one.strip().startswith("recurring")]
        self.assertEqual(len(line), 1, text)
        self.assertIn("compound disable shipped-note", line[0])
        self.assertIn("https://github.com/ContextLab/claude-skill-compounder/issues", line[0])
        self.assertNotIn("add --update", text)
        self.assertNotIn("ineffective", text.split("Open", 1)[1])
        # The upstream it names is the one the package proposes to.
        other = self.box.run("status", COMPOUND_UPSTREAM="someone/fork").stdout
        self.assertIn("https://github.com/someone/fork/issues", other)

    def test_a_user_lesson_that_recurs_is_still_ineffective(self):
        self.box.add("mine", "Use when mine.", "Body.\n", "--level", "user")
        for minute in (1, 2):
            self.recall("mine", ts=NOW + 60 * minute)
        row = self.row("mine")
        self.assertTrue(row["ineffective"])
        self.assertFalse(row["recurring"])
        text = self.box.run("status").stdout
        self.assertIn("compound add --update --name mine", text)

    def test_a_general_lesson_is_never_a_strengthening_owed(self):
        """Whatever a `recall` event says, a session owes nothing for a lesson it cannot rewrite."""
        self.box.add("mine", "Use when mine.", "Body.\n", "--level", "user")
        self.recall("shipped-note", "sess-0001-aaaa", ts=NOW + 60, ineffective=True)
        self.recall("mine", "sess-0001-aaaa", ts=NOW + 120, ineffective=True)
        owed = self.box.json("events", "--unsettled", "--session", "sess-0001-aaaa", "--json")
        self.assertEqual([(event["type"], event["lesson"]) for event in owed], [("recall", "mine")])

    def test_update_still_refuses_a_general_lesson_and_names_what_can_be_done(self):
        proc = self.box.run("add", "--update", "--name", "shipped-note", "--match", ECHO)
        self.assertExit(proc, 2)
        self.assertIn("compound disable shipped-note", proc.stderr)

    def test_a_disabled_general_lesson_is_not_listed_as_recurring(self):
        for minute in (1, 2):
            self.recall("shipped-note", ts=NOW + 60 * minute)
        self.assertExit(self.box.run("disable", "shipped-note"), 0)
        status = json.loads(self.box.run("status", "--json").stdout)
        self.assertEqual(status["open"]["recurring"], [])


class SameSubjectTest(PoolCase):
    """A user who already has a lesson for a mistake the pool also covers: no guard yields,
    so both are hits of the one refusal, and `compound disable` keeps only the user's."""

    def setUp(self):
        PoolCase.setUp(self)
        self.ship("zsh-equals-not-found", "--match", ECHO, body="The pool's text.\n")

    def test_the_users_own_guard_and_the_general_one_are_both_hits_on_the_same_call(self):
        self.box.add("zsh-equals-word", "Use when mine.", "My text.\n", "--level", "user", "--match", ANCHOR + r"echo\s+={4,}")
        reply = self.check("ls; echo =====")
        self.assertEqual([(hit["name"], hit["level"]) for hit in reply["hits"]],
                         [("zsh-equals-word", "user"), ("zsh-equals-not-found", "general")])
        self.assertNotIn("yielded", reply)
        self.assertEqual(reply["guards"], 2)
        # The user who keeps only their own switches the general one off.
        self.assertExit(self.box.run("disable", "zsh-equals-not-found"), 0)
        reply = self.check("ls; echo =====")
        self.assertEqual([(hit["name"], hit["level"]) for hit in reply["hits"]], [("zsh-equals-word", "user")])

    def test_a_project_guard_does_not_silence_the_general_one(self):
        """A project lesson is a file in a repository, which anyone who can commit to it can
        write: it never takes the place of a guard the package ships. Both are quoted."""
        self.box.add("local-equals", "Use when here.", "Project text.\n", "--match", ECHO)
        reply = self.check("echo =====")
        self.assertEqual([hit["level"] for hit in reply["hits"]], ["project", "general"])
        self.assertNotIn("yielded", reply)

    def test_the_general_guard_still_refuses_a_call_the_users_pattern_misses(self):
        self.box.add("zsh-equals-word", "Use when mine.", "My text.\n", "--level", "user", "--match", ANCHOR + r"echo\s+={4,}")
        reply = self.check("echo ==")
        self.assertEqual([(hit["name"], hit["level"]) for hit in reply["hits"]], [("zsh-equals-not-found", "general")])
        self.assertNotIn("yielded", reply)

    def test_two_general_guards_on_one_call_are_both_returned(self):
        self.ship("second-general", "--match", ECHO, body="Another.\n")
        self.assertEqual(self.hits("echo ===="), ["second-general", "zsh-equals-not-found"])


# ---------------------------------------------------------------------------- the shipped pool

GUARDS = {
    "zsh-equals-not-found": (
        ["echo =====", "ls; echo ====== ; pwd", "make && echo ==== && make test", "echo -e ====\nls",
         "cd /tmp\necho ==========\nls", "for f in a b; do echo ====; cat $f; done", "x=$(echo ===)",
         "if true; then echo ==; fi", "true || echo ===="],
        ["echo '====='", "echo \"=== done ===\"", "printf '%s\\n' '====='", "echo a=b", "FOO==bar echo hi",
         "grep -c '^echo ==' file", "echo --- step 2", "python3 -c 'print(1 == 2)'", "echo =", "echo = done",
         "bash -c 'echo ====='", "git commit -m 'echo ==== fails in zsh'", "grep -rn 'echo ====' notes/"]),
    "zsh-status-path-variables": (
        ["status=$?", "make; status=$?; echo $status", "path=/tmp/x && ls $path",
         "for path in a b; do echo $path; done", "f(){ local path=$1; cat $path; }", "echo /tmp | read -r path",
         "if true; then status=1; fi", "make\nstatus=$?\necho $status", "export path=/tmp/x",
         "find . -name '*.py' | while read -r path; do wc -l \"$path\"; done",
         "while IFS= read -r path; do echo \"$path\"; done < files.txt", "make || status=1",
         "ls | while read status; do echo $status; done"],
        ["git status", "exit_status=$?", "file_path=/tmp/x", "PATH=/usr/bin:$PATH ls",
         "curl 'https://h/x?path=1&status=2'", "./configure --path=/usr --status=ok",
         "rc=$?; echo $rc", "for p in a b; do echo $p; done", "python3 -c \"import os; print(os.path)\"",
         "kubectl get pods -o jsonpath='{.status}'", "python3 -c \"open(path='x')\"",
         "echo 'please read path docs'", "grep -n 'for path in' build.sh", "gh pr view --json status=1",
         "docker ps --filter status=running", "while read -r line; do echo $line; done < f"]),
    "sed-in-place-bsd": (
        ["sed -i 's/foo/bar/' f.txt", "sed -i \"s|a|b|g\" src/*.py", "find . -name '*.md' | xargs sed -i 's/x/y/'",
         "sed -E -i 's/a+/b/' f", "sed -i '3d' f.txt", "sed -i -e 's/a/b/' f", "sed -i '/^#/d' f",
         "cd src\nsed -i 's/a/b/' f", "find . -name '*.txt' -exec sed -i 's/a/b/' {} +", "sed -Ei 's/a+/b/' f",
         "ls *.md | xargs -n 1 sed -i 's/x/y/'", "git ls-files | xargs -I {} sed -i 's/x/y/' {}",
         "sudo sed -i 's/a/b/' /etc/hosts"],
        ["sed -i '' 's/foo/bar/' f.txt", "sed -i.bak 's/foo/bar/' f.txt", "sed -n '1,5p' f", "sed 's/a/b/' f > g",
         "sed -E 's/-i s/x/' f", "gsed -i 's/a/b/' f", "perl -pi -e 's/a/b/' f", "echo 'used -i s/x/y/'",
         "sed -i'' -e 's/a/b/' f", "sed -i \"\" 's/a/b/' f", "grep -n \"sed -i 's/a/b/'\" notes.md",
         "git commit -m \"do not run sed -i 's/a/b/' on macOS\"", "sed -E -i '' 's/a+/b/' f",
         "sed -i.bak -e 's/a/b/' f && rm f.bak"]),
}

ORDINARY = [
    "git status", "git log --oneline -5", "git diff --stat HEAD~1", "git commit -m 'Fix the status path'",
    "ls -la", "ls src/*.py", "grep -rn 'timeout' src/", "grep -E '^path=' config.ini",
    "curl -s 'https://example.com/api?path=1&status=2'", "curl -fsSL https://example.com/install.sh | bash",
    "sed -i '' 's/foo/bar/' file.txt", "sed -i.bak 's/foo/bar/' file.txt", "sed -n '1,20p' README.md",
    "gtimeout 5 ./run.sh", "cat <<'EOF' > notes.md\nA note that mentions timeout 30 and sed -i in passing.\nEOF",
    "python3 -m pytest tests/ --timeout 60", "python3 -c \"import os; print(os.path.join('a', 'b'))\"",
    "npm test -- --timeout=10000", "echo '====='", "echo \"=== done ===\"", "printf '%s\\n' '====='",
    "echo done", "export PATH=\"$HOME/.local/bin:$PATH\"", "rc=$?; echo $rc", "for f in *.md; do wc -l \"$f\"; done",
    "find . -name '*.py' -newer setup.py", "pip install 'requests[socks]'", "python3 -m venv .venv",
    "make test && make lint", "docker ps --filter status=exited", "kubectl get pods -o jsonpath='{.items[*].status.phase}'",
    "cd /tmp && pwd", "mkdir -p build/out", "rm -f build/out.o", "cat package.json | head -20",
    "date +%F", "stat -f %z file.txt", "wc -l < file.txt", "tar -czf out.tgz src", "ssh host 'uptime'",
    "gh pr view 12 --json state,statusCheckRollup", "jq '.status' result.json", "./run_tests.sh",
    "while read -r line; do echo \"$line\"; done < file.txt", "PATH=/usr/bin:/bin ls",
    "test -f status.txt && cat status.txt", "awk -F= '/^path/ {print $2}' config.ini",
]

# What `macos-gnu-only-commands` is about. It is recalled when one of them fails and stops
# none of them: on a Mac with Homebrew's coreutils `timeout` is there, and the call is right.
GNU_ONLY = ["timeout 60 npm test", "cd x && timeout 10s make", "out=$(timeout 5 curl -s http://h)",
            "timeout -k 5 30 ./run.sh", "ls |timeout 3 cat", "cd /tmp\ntimeout 30 ./run.sh",
            "for i in 1 2; do timeout 5 ./try.sh; done", "timeout --signal=KILL 10 ./run.sh",
            "date -d yesterday +%F", "grep -P '\\d+' f", "stat -c %s f"]

SHIPPED = {
    "macos-gnu-only-commands": ("lesson", ["darwin"], []),
    "pip-externally-managed": ("lesson", [], []),
    "sed-in-place-bsd": ("guard", ["darwin"], []),
    "zsh-equals-not-found": ("guard", [], ["zsh"]),
    "zsh-no-matches-found": ("lesson", [], ["zsh"]),
    "zsh-status-path-variables": ("guard", [], ["zsh"]),
}


class ShippedPoolTest(PoolCase):
    """This checkout's own lessons/, read by this checkout's own bin/compound."""

    def pool(self, **env):
        kw = dict(ZSH)
        kw.update(env)
        rows = self.box.json("list", "--level", "general", "--json", script=SCRIPT, **kw)
        return {row["name"]: row for row in rows if row["kind"] == "lesson"}

    def shipped_hits(self, command, **env):
        kw = dict(ZSH)
        kw.update(env)
        reply = self.check(command, script=SCRIPT, **kw)
        self.assertNotIn("timed_out", reply, command)
        self.assertNotIn("error", reply, command)
        return [hit["name"] for hit in reply["hits"]]

    def test_every_shipped_lesson_parses_and_is_the_kind_and_condition_meant(self):
        directories = sorted(name for name in os.listdir(os.path.join(REPO, "lessons")) if not name.startswith("."))
        self.assertEqual(directories, sorted(SHIPPED))
        pool = self.pool()
        self.assertEqual(sorted(pool), sorted(SHIPPED), "a shipped lesson does not read")
        for name, (kind, platform, shell) in SHIPPED.items():
            row = pool[name]
            self.assertEqual(("guard" if row["match"] else "lesson", row["platform"], row["shell"]),
                             (kind, platform, shell), name)
            self.assertTrue(row["applies"], name)
            self.assertTrue(row["description"].startswith("Use when "), name)
        status = json.loads(self.box.run("status", "--json", script=SCRIPT, **ZSH).stdout)
        parse = [row for row in status["health"] if row["check"] == "lessons parse"][0]
        self.assertEqual((parse["status"], parse["detail"]), ("PASS", "every lesson reads"))
        duplicates = [row for row in status["health"] if row["check"] == "duplicates"][0]
        self.assertEqual(duplicates["status"], "PASS")
        self.assertEqual(status["store"]["general"]["lessons"], 6)
        self.assertEqual(status["store"]["general"]["guards"], 3)

    def test_a_shipped_lesson_carries_no_origin_and_is_as_the_cli_writes_it(self):
        """The file is what `compound promote --to general` publishes: rewriting it at the
        user level with the CLI and publishing it again gives the same bytes."""
        for name in sorted(SHIPPED):
            source = os.path.join(REPO, "lessons", name, "SKILL.md")
            with open(source, encoding="utf-8") as handle:
                text = handle.read()
            self.assertNotIn("\norigin:", text.split("---\n")[1], name)
            self.assertEqual(os.listdir(os.path.dirname(source)), ["SKILL.md"], name)
            target = self.box.lesson_dir(name, "user")
            os.makedirs(target)
            with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as handle:
                handle.write(text)
            plan = self.box.json("promote", name, "--to", "general", "--json")
            self.assertEqual(plan["skill_md"], text, name)

    def test_each_shipped_guard_stops_the_wrong_form_and_not_the_right_one(self):
        self.assertEqual(sorted(GUARDS), sorted(name for name, row in SHIPPED.items() if row[0] == "guard"))
        wrong = []
        for name, (yes, no) in sorted(GUARDS.items()):
            self.assertGreaterEqual(len(yes), 5, name)
            self.assertGreaterEqual(len(no), 8, name)
            for command in yes:
                if self.shipped_hits(command) != [name]:
                    wrong.append("%s should match and be the only hit: %r -> %r" % (name, command, self.shipped_hits(command)))
            for command in no:
                if self.shipped_hits(command) != []:
                    wrong.append("%s should not match: %r -> %r" % (name, command, self.shipped_hits(command)))
        self.assertEqual(wrong, [])

    def test_the_gnu_only_lesson_is_recalled_and_stops_no_call(self):
        """D7: it carries no pattern, so `timeout N cmd` runs, on a Mac with Homebrew's
        coreutils as on any other. It is still found for the failure it describes."""
        row = self.pool()["macos-gnu-only-commands"]
        self.assertEqual((row["match"], row["platform"], row["applies"]), ([], ["darwin"], True))
        self.assertGreaterEqual(len(GNU_ONLY), 8)
        for command in GNU_ONLY:
            self.assertEqual(self.shipped_hits(command), [], command)
        found = self.box.json("find", "command", "not", "found", "timeout", "--json", script=SCRIPT, **ZSH)
        self.assertIn("macos-gnu-only-commands", [row["name"] for row in found["items"]])
        with open(os.path.join(REPO, "lessons", "macos-gnu-only-commands", "SKILL.md"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("\nmatch:", text)
        self.assertNotIn("stopped before it runs", text, "the text must not say it is a guard")
        for form in ("timeout 60 cmd", "date -d", "grep -P", "stat -c"):
            self.assertIn(form, text)

    def test_no_shipped_pattern_hits_an_ordinary_command(self):
        self.assertGreaterEqual(len(ORDINARY), 25)
        wrong = [(command, self.shipped_hits(command)) for command in ORDINARY if self.shipped_hits(command)]
        self.assertEqual(wrong, [])

    def test_no_shipped_guard_applies_where_its_command_is_right(self):
        """bash on Linux: every call the guards stop on macOS and zsh runs unrefused."""
        reply = self.check("echo ====", script=SCRIPT, **BASH_LINUX)
        self.assertEqual((reply["hits"], reply["guards"]), ([], 0))
        for name, (yes, _no) in sorted(GUARDS.items()):
            for command in yes:
                self.assertEqual(self.shipped_hits(command, **BASH_LINUX), [], command)
        pool = self.pool(**BASH_LINUX)
        self.assertEqual(sorted(name for name, row in pool.items() if row["applies"]), ["pip-externally-managed"])
        # zsh on Linux: the zsh guards apply, the macOS ones do not.
        self.assertEqual(self.shipped_hits("echo ====", COMPOUND_PLATFORM="linux"), ["zsh-equals-not-found"])
        self.assertEqual(self.shipped_hits("timeout 5 make", COMPOUND_PLATFORM="linux"), [])
        self.assertEqual(self.shipped_hits("sed -i 's/a/b/' f", COMPOUND_PLATFORM="linux"), [])
        # bash on macOS: the macOS guard applies, the zsh ones do not.
        self.assertEqual(self.shipped_hits("sed -i 's/a/b/' f", SHELL="/bin/bash"), ["sed-in-place-bsd"])
        self.assertEqual(self.shipped_hits("timeout 5 make", SHELL="/bin/bash"), [])
        self.assertEqual(self.shipped_hits("status=$?", SHELL="/bin/bash"), [])

    def test_a_users_own_lesson_for_the_same_mistake_refuses_beside_the_shipped_one(self):
        self.box.add("zsh-equals-word", 'Use when a zsh command line has a bare word starting with "=".',
                     "Quote it.\n", "--level", "user", "--match", ANCHOR + r"echo\s+=+", script=SCRIPT, **ZSH)
        self.box.add("macos-no-timeout", "Use when timeout is called on macOS.", "Not installed.\n",
                     "--level", "user", "--match", ANCHOR + r"timeout\s+\d", script=SCRIPT, **ZSH)
        self.assertEqual(self.shipped_hits("ls; echo ====="), ["zsh-equals-word", "zsh-equals-not-found"])
        # `timeout` is no shipped guard: the user's own lesson is the only one that refuses.
        self.assertEqual(self.shipped_hits("timeout 5 make"), ["macos-no-timeout"])
        self.assertEqual(self.shipped_hits("timeout -k 5 30 ./run.sh"), [])
        # Switched off, the shipped lesson leaves the user's alone on the call.
        self.assertExit(self.box.run("disable", "zsh-equals-not-found", script=SCRIPT, **ZSH), 0)
        self.assertEqual(self.shipped_hits("ls; echo ====="), ["zsh-equals-word"])

    def test_one_shipped_lesson_can_be_switched_off(self):
        self.assertExit(self.box.run("disable", "sed-in-place-bsd", script=SCRIPT, **ZSH), 0)
        self.assertEqual(self.shipped_hits("sed -i 's/a/b/' f"), [])
        self.assertEqual(self.shipped_hits("echo ===="), ["zsh-equals-not-found"])
        self.assertTrue(self.pool()["sed-in-place-bsd"]["disabled"])

    def test_the_pool_is_checked_inside_the_pre_call_budget(self):
        import time
        began = time.time()
        for command in ORDINARY[:10]:
            self.shipped_hits(command)
        self.assertLess((time.time() - began) / 10, 1.5, "one check of the shipped pool takes longer than its budget")


if __name__ == "__main__":
    unittest.main()
