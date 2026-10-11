#!/usr/bin/env python3
"""A script a session ran is kept as it ran, and a lesson keeps that copy.

`compound evidence note` is what the mod runs after a Bash call: it reads the command,
finds the script files the command ran, and keeps the bytes of each with the run. `add
--from-evidence` attaches such a copy to a lesson, `add --attach` knows a file whose bytes
were recorded, and a program that never ran is refused unless `--unrun` says so."""

import json
import os
import unittest

from test_support import NOW, Case, git_ok

DAY = 86400


class EvidenceCase(Case):
    def setUp(self):
        super().setUp()
        self.scratch = os.path.join(self.box.root, "scratch")
        os.makedirs(self.scratch)

    def script(self, name, text, directory=None, mode=0o755):
        path = os.path.join(directory or self.scratch, name)
        with open(path, "w") as handle:
            handle.write(text)
        os.chmod(path, mode)
        return os.path.realpath(path)

    def note(self, command, ok=True, **kw):
        run = {"command": command, "ok": ok, "call": kw.pop("call", "toolu_01"), "turn": kw.pop("turn", 1)}
        for key in ("cwd", "agent"):
            if key in kw:
                run[key] = kw.pop(key)
        return self.box.json("evidence", "note", "--json", stdin=json.dumps(run), **kw)["noted"]

    def rows(self, *flags, **kw):
        return self.box.json("evidence", "list", "--json", *flags, **kw)

    def passed(self, path, times, **kw):
        start = kw.pop("COMPOUND_NOW", NOW)
        for index in range(times):
            noted = self.note(path, COMPOUND_NOW=start + index, **kw)
        return noted[0]["id"]


class NoteTest(EvidenceCase):
    def test_a_script_run_by_its_path_is_kept_byte_for_byte_with_the_run(self):
        text = "#!/bin/sh\necho 'checking the bibliography'\n"
        path = self.script("validate.sh", text)
        noted = self.note("%s --all" % path)
        self.assertEqual([(one["name"], one["path"]) for one in noted], [("validate.sh", path)])
        directory = os.path.join(self.box.chome, "evidence", noted[0]["id"])
        with open(os.path.join(directory, "validate.sh")) as handle:
            self.assertEqual(handle.read(), text)
        self.assertTrue(os.access(os.path.join(directory, "validate.sh"), os.X_OK))
        shown = self.box.json("evidence", "show", noted[0]["id"], "--json")
        self.assertEqual((shown["ok"], shown["failed"], shown["text"], shown["path"]), (1, 0, text, path))
        self.assertEqual(shown["runs"][0]["command"], "%s --all" % path)
        self.assertEqual(shown["runs"][0]["session"], "sess-0001-aaaa")
        self.assertEqual(shown["runs"][0]["call"], "toolu_01")

    def test_the_same_bytes_are_one_snapshot_and_an_edit_is_a_new_version_of_the_same_script(self):
        path = self.script("build.sh", "#!/bin/sh\nexit 1\n")
        first = self.note(path, ok=False)[0]["id"]
        self.assertEqual(self.note(path, ok=False, COMPOUND_NOW=NOW + 1)[0]["id"], first)
        self.script("build.sh", "#!/bin/sh\nexit 0\n")
        second = self.note(path, COMPOUND_NOW=NOW + 2)[0]["id"]
        self.assertNotEqual(first, second)
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["id"], row["ok"], row["failed"], row["versions"], row["ok_this"], row["failed_first"]),
                         (second, 1, 2, 2, 1, True))
        self.assertEqual(row["scratch"], True)

    def test_what_counts_as_running_a_script(self):
        path = self.script("job.py", "print('ok')\n", mode=0o644)
        tool = self.script("tool.sh", "#!/bin/sh\ntrue\n")
        ran = [
            "python3 %s" % path,
            "python3 -u -W ignore %s --fast" % path,
            "uv run %s" % path,
            "nohup timeout 30 python3 %s > out.log 2>&1 &" % path,
            "S=%s; python3 $S/job.py" % self.scratch,
            "S=%s\npython3 \"${S}/job.py\" | tail -3" % self.scratch,
            "cd %s && python3 job.py" % self.scratch,
            "cd %s && ./tool.sh" % self.scratch,
            "export S=%s && bash $S/tool.sh" % self.scratch,
            "git status; (cd %s && FOO=1 ./tool.sh)" % self.scratch,
        ]
        for command in ran:
            self.assertEqual(len(self.note(command)), 1, command)
        not_run = [
            "cat %s" % path,
            "wc -l %s && git add %s" % (path, path),
            "pytest %s -x" % path,
            "python3 -m pytest %s" % path,
            "python3 -c 'import runpy' %s" % path,
            "python3 - <<'EOF'\nimport os\nos.system('python3 %s')\nEOF" % path,
            "cat > /dev/null <<EOF\n%s\nEOF" % tool,
            "echo 'python3 %s'" % path,
            "python3 $UNSET_NAME_OF_NOTHING/job.py",
            "python3 %s" % os.path.join(self.scratch, "absent.py"),
        ]
        for command in not_run:
            self.assertEqual(self.note(command), [], command)

    def test_a_relative_path_is_read_from_the_directory_the_mod_gives(self):
        self.script("here.py", "print(1)\n", mode=0o644)
        self.assertEqual(self.note("python3 here.py"), [])
        self.assertEqual(len(self.note("python3 here.py", cwd=self.scratch)), 1)

    def test_what_is_not_the_sessions_work_is_not_kept(self):
        vendored = os.path.join(self.scratch, "node_modules", "pkg")
        os.makedirs(vendored)
        self.assertEqual(self.note("node %s" % self.script("cli.js", "console.log(1)\n", vendored)), [])
        self.assertEqual(self.note("%s list" % self.box.script), [])
        self.assertEqual(self.note("/bin/sh -n /bin/sh"), [])
        big = self.script("big.py", "x = 1\n" * 60000)
        self.assertEqual(self.note("python3 %s" % big), [])
        binary = self.script("blob.sh", "")
        with open(binary, "wb") as handle:
            handle.write(b"#!/bin/sh\n\0\0\0")
        self.assertEqual(self.note(binary), [])

    def test_a_credential_in_the_command_is_masked_where_the_run_is_kept(self):
        path = self.script("push.sh", "#!/bin/sh\ntrue\n")
        ident = self.note("API_TOKEN=abcdef0123456789 %s --password hunter2secret" % path)[0]["id"]
        shown = json.dumps(self.box.json("evidence", "show", ident, "--json")["runs"])
        self.assertNotIn("abcdef0123456789", shown)
        self.assertNotIn("hunter2secret", shown)

    def test_a_script_that_holds_a_credential_is_not_copied(self):
        token = "ghp_" + "a1B2c3D4e5" * 4
        path = self.script("deploy.sh", "#!/bin/sh\ncurl -H 'Authorization: token %s' https://example.invalid\n" % token)
        self.assertEqual(self.note(path), [])
        self.assertFalse(os.path.isdir(os.path.join(self.box.chome, "evidence")) and any(
            token in open(os.path.join(base, name), errors="replace").read()
            for base, _dirs, names in os.walk(os.path.join(self.box.chome, "evidence")) for name in names))

    def test_a_snapshot_whose_record_names_another_file_is_not_read(self):
        """meta.json is a file on disk: a name written into it by hand can name no file
        outside the snapshot and can never stand in for a lesson's SKILL.md."""
        ident = self.passed(self.script("validate.sh", "#!/bin/sh\ntrue\n"), 1)
        meta_path = os.path.join(self.box.chome, "evidence", ident, "meta.json")
        with open(meta_path) as handle:
            meta = json.load(handle)
        victim = os.path.join(self.box.root, "victim.txt")
        with open(victim, "w") as handle:
            handle.write("not a script\n")
        for name in ("SKILL.md", "skill.md", "Skill.MD", "../../../victim.txt", victim, ".evidence.json", "a/b.sh", ""):
            with open(meta_path, "w") as handle:
                json.dump(dict(meta, name=name), handle)
            proc = self.box.run("add", "--name", "taken-over", "--when", "Use when.", "--from-evidence", ident,
                                stdin="Body.\n")
            self.assertExit(proc, 2)
            self.assertFalse(os.path.exists(self.box.lesson_dir("taken-over")), name)
            self.assertEqual(self.rows(), [], name)

    def test_a_file_whose_name_is_a_lessons_own_is_not_kept(self):
        self.assertEqual(self.note("sh %s" % self.script("SKILL.md", "#!/bin/sh\ntrue\n")), [])
        self.assertEqual(self.note("sh %s" % self.script(".hidden.sh", "#!/bin/sh\ntrue\n")), [])
        # On a file system that ignores case, `skill.md` beside a lesson IS its SKILL.md.
        other = os.path.join(self.scratch, "lower")
        os.makedirs(other)
        lower = self.script("skill.md", "#!/bin/sh\ntrue\n", other)
        self.assertEqual(self.note("sh %s" % lower), [])
        proc = self.box.run("add", "--name", "lower-case", "--when", "Use when.", "--attach", lower, "--unrun",
                            stdin="Body.\n")
        self.assertExit(proc, 2)
        self.assertIn("SKILL.md", proc.stderr)

    def test_git_is_not_run_in_the_directory_a_script_ran_in(self):
        """The directory a script ran in may be a repository with a config of its own, and a
        config can name a program for git to start (here, its fsmonitor). Whether the file
        is in a repository is read from the directories above it, and git is not run."""
        repo = os.path.join(self.box.root, "cloned")
        os.makedirs(repo)
        git_ok("init", "-q", repo)
        marker = os.path.join(self.box.root, "ran-by-git")
        hook = self.script("fsmonitor.sh", "#!/bin/sh\ntouch %s\n" % marker)
        git_ok("config", "core.fsmonitor", hook, cwd=repo)
        path = self.script("tool.sh", "#!/bin/sh\ntrue\n", repo)
        git_ok("add", "tool.sh", cwd=repo)
        # `git add` itself asked the monitor: that is this test's own git, not the CLI's.
        if os.path.exists(marker):
            os.remove(marker)
        self.assertEqual(len(self.note(path)), 1)
        self.assertEqual([row["in_repo"] for row in self.rows() if row["name"] == "tool.sh"], [True])
        self.assertFalse(os.path.exists(marker))

    def test_input_that_is_not_a_run_is_refused(self):
        for stdin in ("", "[]", '{"command": "x"}', '{"command": 3, "ok": true}'):
            self.assertExit(self.box.run("evidence", "note", stdin=stdin), 2)
        self.assertExit(self.box.run("evidence", "show", "0123456789abcdef"), 2)
        self.assertExit(self.box.run("evidence", "show", "../../etc/passwd"), 2)


class DueTest(EvidenceCase):
    def test_a_script_is_owed_a_decision_after_three_passing_runs(self):
        path = self.script("validate.sh", "#!/bin/sh\ntrue\n")
        self.passed(path, 2)
        self.assertEqual(self.rows("--due"), [])
        ident = self.passed(path, 1, COMPOUND_NOW=NOW + 5)
        self.assertEqual([row["id"] for row in self.rows("--due")], [ident])
        self.assertEqual(self.rows("--due", "--session", "another-session"), [])
        self.assertEqual([row["id"] for row in self.rows("--due", "--session", "sess-0001-aaaa")], [ident])

    def test_the_number_of_runs_is_a_setting(self):
        path = self.script("validate.sh", "#!/bin/sh\ntrue\n")
        self.passed(path, 1)
        self.assertEqual(len(self.rows("--due", COMPOUND_EVIDENCE_MIN_RUNS="1")), 1)
        self.assertEqual(self.rows("--due", COMPOUND_EVIDENCE_MIN_RUNS="2"), [])
        self.assertEqual(self.rows("--due", COMPOUND_EVIDENCE_MIN_RUNS="nonsense"), [])

    def test_the_newest_version_must_be_one_that_passed(self):
        path = self.script("validate.sh", "#!/bin/sh\ntrue\n")
        self.passed(path, 3)
        self.script("validate.sh", "#!/bin/sh\nfalse\n")
        self.note(path, ok=False, COMPOUND_NOW=NOW + 9)
        self.assertEqual(self.rows("--due"), [])

    def test_a_script_in_a_repository_is_the_repositorys_to_keep(self):
        git_ok("init", "-q", self.box.project)
        inside = self.script("release.sh", "#!/bin/sh\ntrue\n", self.box.project)
        outside = self.script("probe.sh", "#!/bin/sh\ntrue\n")
        self.passed(inside, 3)
        self.passed(outside, 3)
        rows = dict((row["name"], row) for row in self.rows())
        self.assertEqual((rows["release.sh"]["in_repo"], rows["release.sh"]["due"]), (True, False))
        self.assertEqual((rows["probe.sh"]["in_repo"], rows["probe.sh"]["due"]), (False, True))

    def test_a_script_that_takes_its_input_from_the_call_is_owed_after_two_passing_runs(self):
        """A tool is told from a probe by how it is used, not by how often: given different
        arguments, or written to read them."""
        fixed = self.script("probe.py", "print(open('/etc/hosts').read()[:10])\n")
        self.passed("python3 %s" % fixed, 2, agent="worker-1")
        varied = self.script("render.py", "import os\nprint(os.environ.get('PAGE'))\n")
        self.note("python3 %s chapter1.md" % varied, agent="worker-1")
        self.note("python3 %s chapter2.md" % varied, agent="worker-1", COMPOUND_NOW=NOW + 1)
        reads = self.script("fill.sh", "#!/bin/sh\nsed \"s/NAME/$1/\" template.txt\n")
        self.passed("sh %s" % reads, 2, agent="worker-1")
        once = self.script("once.py", "import sys\nprint(sys.argv[1:])\n")
        self.passed("python3 %s a" % once, 1, agent="worker-1")
        rows = dict((row["name"], row) for row in self.rows())
        self.assertEqual([(name, rows[name]["varied"], rows[name]["reads_args"], rows[name]["due"])
                          for name in ("probe.py", "render.py", "fill.sh", "once.py")],
                         [("probe.py", False, False, False), ("render.py", True, False, True),
                          ("fill.sh", False, True, True), ("once.py", False, True, False)])

    def test_runs_alone_count_only_when_the_main_loop_made_them(self):
        path = self.script("progress.sh", "#!/bin/sh\ndate\n")
        self.passed(path, 5, agent="worker-1")
        self.assertEqual((self.rows()[0]["ok"], self.rows()[0]["ok_main"], self.rows()[0]["due"]), (5, 0, False))
        self.passed(path, 3, COMPOUND_NOW=NOW + 20)
        self.assertEqual((self.rows()[0]["ok_main"], self.rows()[0]["due"]), (3, True))

    def test_a_test_file_and_a_script_tied_to_a_scratch_directory_are_not_owed(self):
        test = self.script("test_parser.py", "import sys\nprint(sys.argv)\n")
        bound = self.script("collect.py", "import sys\nOUT = '/private/tmp/claude-501/x/scratchpad/out.json'\nprint(sys.argv, OUT)\n")
        for path in (test, bound):
            self.passed("python3 %s" % path, 4)
        rows = dict((row["name"], row) for row in self.rows())
        self.assertEqual((rows["test_parser.py"]["test"], rows["test_parser.py"]["due"]), (True, False))
        self.assertEqual((rows["collect.py"]["bound"], rows["collect.py"]["due"]), (True, False))

    def test_a_snapshot_nothing_holds_goes_after_thirty_days_and_a_lessons_stays(self):
        kept = self.passed(self.script("kept.sh", "#!/bin/sh\necho kept\n"), 3)
        gone = self.passed(self.script("gone.sh", "#!/bin/sh\necho gone\n"), 3)
        self.box.add("kept-script", "Use when keeping.", "Run kept.sh.\n", "--from-evidence", kept)
        later = NOW + 31 * DAY
        self.passed(self.script("new.sh", "#!/bin/sh\necho new\n"), 1, COMPOUND_NOW=later)
        left = sorted(name for name in os.listdir(os.path.join(self.box.chome, "evidence")) if not name.startswith("."))
        self.assertIn(kept, left)
        self.assertNotIn(gone, left)
        self.assertEqual(len(left), 2)


class LessonTest(EvidenceCase):
    def test_from_evidence_attaches_the_bytes_that_ran_and_says_where_they_came_from(self):
        text = "#!/bin/sh\necho 'the version that worked'\n"
        path = self.script("validate.sh", text)
        ident = self.passed(path, 3)
        # The file changes after its last run: the lesson keeps what ran, not what is there now.
        self.script("validate.sh", "#!/bin/sh\necho 'edited afterwards, never run'\n")
        proc = self.box.add("validate-bib", "Use when validating the bibliography.",
                            "Run validate.sh, beside this lesson.\n", "--from-evidence", ident)
        self.assertIn("validate.sh is the script that ran (evidence %s, passed 3)" % ident, proc.stdout)
        directory = self.box.lesson_dir("validate-bib")
        with open(os.path.join(directory, "validate.sh")) as handle:
            self.assertEqual(handle.read(), text)
        with open(os.path.join(directory, ".evidence.json")) as handle:
            proof = json.load(handle)
        self.assertEqual([(row["name"], row["id"], row["ok"], row["path"], row["command"])
                          for row in proof["attachments"]], [("validate.sh", ident, 3, path, path)])
        self.assertEqual(proof["unrun"], [])
        event = self.box.read_events()[-1]
        self.assertEqual((event["type"], event["lesson"], event["evidence"]), ("learn", "validate-bib", [ident]))
        shown = self.box.json("show", "validate-bib", "--json")
        self.assertEqual([row["id"] for row in shown["evidence"]], [ident])
        self.assertIn("the script as it ran: passed 3", self.box.run("show", "validate-bib").stdout)
        row = [row for row in self.rows() if row["id"] == ident][0]
        self.assertEqual((row["lesson"], row["due"]), ("validate-bib", False))

    def test_attach_knows_a_file_whose_bytes_ran(self):
        path = self.script("validate.sh", "#!/bin/sh\ntrue\n")
        ident = self.passed(path, 1)
        out = json.loads(self.box.add("by-path", "Use when attaching by path.", "Run validate.sh.\n",
                                      "--attach", path, "--json").stdout)
        self.assertEqual(out["evidence"], [ident])
        self.assertNotIn("unrun", out)

    def test_a_program_that_never_ran_is_refused_and_unrun_keeps_it_and_says_so(self):
        path = self.script("guess.sh", "#!/bin/sh\necho 'should work'\n")
        proc = self.box.run("add", "--name", "a-guess", "--when", "Use when guessing.", "--attach", path,
                            stdin="Run guess.sh.\n")
        self.assertExit(proc, 2)
        self.assertIn("no recorded passing run", proc.stderr)
        self.assertIn("--unrun", proc.stderr)
        self.assertFalse(os.path.exists(self.box.lesson_dir("a-guess")))
        self.assertEqual(self.box.read_events(), [])
        out = json.loads(self.box.add("a-guess", "Use when guessing.", "Run guess.sh.\n", "--attach", path,
                                      "--unrun", "--json").stdout)
        self.assertEqual(out["unrun"], ["guess.sh"])
        self.assertIn("kept without a recorded run", self.box.run("show", "a-guess").stdout)
        self.assertNotIn("evidence", self.box.read_events()[-1])

    def test_the_proof_file_is_the_commands_to_write_and_cannot_be_attached(self):
        forged = os.path.join(self.scratch, ".evidence.json")
        with open(forged, "w") as handle:
            handle.write('{"attachments": [{"name": "x.sh", "ok": 9}], "unrun": []}')
        for name in (forged,):
            proc = self.box.run("add", "--name", "forged-proof", "--when", "Use when.", "--attach", name,
                                stdin="Body.\n")
            self.assertExit(proc, 2)
            self.assertIn(".evidence.json", proc.stderr)
        self.assertFalse(os.path.exists(self.box.lesson_dir("forged-proof")))

    def test_a_file_that_is_not_a_program_needs_no_run(self):
        notes = os.path.join(self.scratch, "table.csv")
        with open(notes, "w") as handle:
            handle.write("a,b\n1,2\n")
        self.box.add("with-data", "Use when reading the table.", "See table.csv.\n", "--attach", notes)
        self.assertEqual(sorted(os.listdir(self.box.lesson_dir("with-data"))), ["SKILL.md", "table.csv"])

    def test_a_script_whose_every_run_failed_is_not_a_solution(self):
        path = self.script("broken.sh", "#!/bin/sh\nexit 3\n")
        ident = self.note(path, ok=False)[0]["id"]
        for flags in (("--from-evidence", ident), ("--attach", path)):
            proc = self.box.run("add", "--name", "broken", "--when", "Use when broken.", *flags, stdin="Run it.\n")
            self.assertExit(proc, 2)
        self.assertFalse(os.path.exists(self.box.lesson_dir("broken")))
        self.assertExit(self.box.run("add", "--name", "broken", "--when", "Use when broken.", "--from-evidence",
                                     "0123456789abcdef", stdin="Run it.\n"), 2)

    def test_update_attaches_a_recorded_script_to_a_lesson_that_exists(self):
        self.box.add("grows", "Use when it grows.", "A body.\n")
        ident = self.passed(self.script("step.py", "print('step')\n", mode=0o644), 1,
                            cwd=self.scratch)
        self.assertExit(self.box.run("add", "--name", "grows", "--update", "--from-evidence", ident), 0)
        self.assertEqual(sorted(os.listdir(self.box.lesson_dir("grows"))), [".evidence.json", "SKILL.md", "step.py"])
        event = self.box.read_events()[-1]
        self.assertEqual((event["update"], event["evidence"]), (True, [ident]))


class DeclineTest(EvidenceCase):
    def test_a_declined_script_is_not_asked_about_again_and_settles_no_capture(self):
        self.box.log({"type": "capture", "tool": "Bash", "failed": "x", "error": "boom", "fixed": "x --flag",
                      "call": "toolu_09"})
        path = self.script("probe.sh", "#!/bin/sh\ntrue\n")
        ident = self.passed(path, 3)
        proc = self.box.run("skip", "--evidence", ident, "--why", "a probe of one API response")
        self.assertExit(proc, 0)
        self.assertIn("not asked about again", proc.stdout)
        event = self.box.read_events()[-1]
        self.assertEqual((event["type"], event["evidence"]), ("skip", ident))
        self.assertNotIn("settles", event)
        self.assertEqual(self.rows("--due"), [])
        self.assertEqual(self.rows()[0]["declined"], "a probe of one API response")
        owed = self.box.json("events", "--unsettled", "--json")
        self.assertEqual([one["type"] for one in owed], ["capture"])
        # An edit of a declined script is still that script.
        self.script("probe.sh", "#!/bin/sh\ntrue # again\n")
        self.passed(path, 3, COMPOUND_NOW=NOW + 50)
        self.assertEqual(self.rows("--due"), [])

    def test_a_decline_names_one_thing(self):
        ident = self.passed(self.script("probe.sh", "#!/bin/sh\ntrue\n"), 1)
        self.assertExit(self.box.run("skip", "--evidence", ident, "--settles", "ab12cd34", "--why", "both"), 2)
        self.assertExit(self.box.run("skip", "--evidence", "0123456789abcdef", "--why", "nothing there"), 2)


if __name__ == "__main__":
    unittest.main()
