#!/usr/bin/env python3
"""What `compound add` refuses to write: a second copy of a lesson the session can
already see, and a text that only made sense in the session that wrote it."""

import os
import unittest

from test_support import Case

WHEN = "Use when a zsh command has an unquoted glob that may match nothing."
BODY = ("zsh stops with `no matches found` before the command runs, and the rest of the chain is lost. "
        "Quote the glob, as in grep --include='*.py', or set the nullglob option for that one command.\n")


class DuplicateTest(Case):
    def setUp(self):
        Case.setUp(self)
        self.box.add("zsh-nomatch-glob", WHEN, BODY, "--level", "user")

    def refused(self, proc, name="zsh-nomatch-glob"):
        self.assertExit(proc, 2)
        self.assertIn(repr(name), proc.stderr)
        self.assertIn("--update", proc.stderr)
        self.assertIn("--new", proc.stderr)

    def add(self, name, when, body, *flags, **kw):
        return self.box.run("add", "--name", name, "--when", when, *flags, stdin=body, **kw)

    def test_the_same_text_under_another_name_is_refused(self):
        before = self.box.snapshot()
        proc = self.add("glob-matches-nothing", WHEN, BODY)
        self.refused(proc)
        self.assertIn("compound add --update --name zsh-nomatch-glob", proc.stderr)
        self.assertIn(self.box.lesson_dir("zsh-nomatch-glob", "user"), proc.stderr)
        self.assertEqual(self.box.snapshot(), before, "nothing is written and no event is logged")

    def test_case_spacing_and_punctuation_do_not_make_it_another_lesson(self):
        proc = self.add("glob-matches-nothing", "use when a ZSH command has an unquoted glob, that may match nothing",
                        "  " + BODY.upper().replace(". ", ".\n\n").replace(",", " ;"), "--level", "user")
        self.refused(proc)

    def test_a_light_rewording_is_refused(self):
        proc = self.add("glob-matches-nothing",
                        "Use when a zsh command line has an unquoted glob that might match nothing.",
                        "zsh stops with `no matches found` before the command runs and the rest of the chain is "
                        "then lost. Quote the glob, as in grep --include='*.py', or set the nullglob option for "
                        "that single command.\n")
        self.refused(proc)

    def test_the_same_guard_under_another_name_is_refused(self):
        self.box.add("no-timeout-on-macos", "Use when wrapping a command in timeout on macOS.",
                     "macOS ships no timeout command. Use gtimeout from coreutils.\n", "--match", r"\btimeout\s+\d")
        proc = self.add("macos-timeout-missing", "Use when wrapping a command in timeout on macOS",
                        "The timeout program is absent from a stock Mac, so the call is not found. Install "
                        "coreutils and call gtimeout, or use the tool's own limit.\n", "--match", r"\btimeout\s+\d")
        self.refused(proc, "no-timeout-on-macos")
        proc = self.add("macos-timeout-missing", "Use when wrapping a command in timeout on macOS",
                        "The timeout program is absent from a stock Mac.\n", "--match", r"\bgtimeout\s+--foreground")
        self.assertExit(proc, 0)

    def test_new_records_it_anyway(self):
        proc = self.add("glob-matches-nothing", WHEN, BODY, "--new")
        self.assertExit(proc, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("glob-matches-nothing"), "SKILL.md")))
        self.assertEqual([e["lesson"] for e in self.box.read_events() if e["type"] == "learn"][-1], "glob-matches-nothing")

    def test_another_lesson_about_the_same_subject_is_accepted(self):
        for name, when, body in (
            ("zsh-equals-word", "Use when a zsh command line prints a separator with a bare word starting with =.",
             "zsh expands the word as a command lookup and stops with `not found`, and the rest of the chain is "
             "lost. Quote the separator, or print it with printf.\n"),
            ("zsh-glob-in-include", "Use when grep is given --include with an unquoted glob in zsh.",
             "grep --include=*.py is expanded by zsh before grep runs. Quote the pattern: --include='*.py'.\n"),
            ("bash-nullglob", "Use when a bash loop runs over a glob that may match nothing.",
             "bash passes the pattern through unchanged, so the loop runs once with the pattern itself. Set "
             "nullglob, or test that the file exists inside the loop.\n"),
        ):
            self.assertExit(self.add(name, when, body), 0)

    def test_the_same_description_with_another_body_is_accepted(self):
        proc = self.add("zsh-nomatch-rm", WHEN,
                        "rm -f dir/*.tmp fails the whole call when the directory holds no such file. Use find "
                        "dir -name '*.tmp' -delete, which exits 0 either way.\n")
        self.assertExit(proc, 0)

    def test_short_texts_are_not_compared(self):
        """Two lessons of a few words cannot be told to be one lesson."""
        self.box.add("first-short", "Use when testing.", "The lesson body.\n")
        self.box.add("second-short", "Use when testing.", "The lesson body.\n")
        self.box.add("first-guard", "Use when.", "Body.\n", "--match", "danger-1")
        self.box.add("second-guard", "Use when.", "Body.\n", "--match", "danger-1")

    def test_update_is_not_a_duplicate_of_itself(self):
        proc = self.box.run("add", "--update", "--name", "zsh-nomatch-glob", "--body", BODY + "It is the same in a script.\n")
        self.assertExit(proc, 0)
        proc = self.box.run("add", "--update", "--name", "zsh-nomatch-glob", "--when", WHEN)
        self.assertExit(proc, 0)

    def test_only_what_the_session_can_see_is_compared(self):
        other = os.path.join(self.box.root, "other-project")
        os.makedirs(other)
        self.assertExit(self.add("timeout-in-ci", "Use when the CI job of this repository is killed after ten minutes.",
                                 "The runner kills a job that prints nothing for ten minutes. Print a line from the "
                                 "long test every minute, or raise the limit in the workflow file.\n",
                                 COMPOUND_PROJECT=other), 0)
        same = self.add("ci-job-killed", "Use when the CI job of this repository is killed after ten minutes.",
                        "The runner kills a job that prints nothing for ten minutes. Print a line from the long "
                        "test every minute, or raise the limit in the workflow file.\n")
        self.assertExit(same, 0)
        again = self.add("ci-job-killed-again", "Use when the CI job of this repository is killed after ten minutes.",
                         "The runner kills a job that prints nothing for ten minutes. Print a line from the long "
                         "test every minute, or raise the limit in the workflow file.\n")
        self.refused(again, "ci-job-killed")

    def test_a_copy_of_a_general_lesson_is_refused_without_naming_update(self):
        self.box.write_lesson(self.box.lesson_dir("pipeline-status", "general"), "pipeline-status",
                              description="Use when a pipeline hides the exit status of its first command.",
                              body="A pipeline exits with the status of its last command, so a failing first "
                                   "command is reported as success. Read PIPESTATUS, or write to a file first.\n")
        proc = self.add("pipe-hides-status", "Use when a pipeline hides the exit status of its first command.",
                        "A pipeline exits with the status of its last command, so a failing first command is "
                        "reported as success. Read PIPESTATUS, or write to a file first.\n")
        self.assertExit(proc, 2)
        self.assertIn("'pipeline-status'", proc.stderr)
        self.assertIn("general", proc.stderr)
        self.assertIn("--new", proc.stderr)
        self.assertNotIn("--update", proc.stderr)


class ResidueTest(Case):
    WHEN = "Use when a page must be fetched and searched from a Bash call."

    def add(self, body, *flags, **kw):
        return self.box.run("add", "--name", kw.pop("name", "fetch-and-search"), "--when", kw.pop("when", self.WHEN),
                            *flags, stdin=body, **kw)

    def refused(self, proc, quoted):
        self.assertExit(proc, 2)
        self.assertIn(quoted, proc.stderr)
        self.assertIn("--as-written", proc.stderr)
        self.assertFalse(os.path.exists(self.box.lesson_dir("fetch-and-search")))
        self.assertEqual(self.box.read_events(), [])

    def test_a_scratch_path_of_the_session_is_refused(self):
        for path in ("/private/tmp/claude-501/-Users-someone-project/0a1b2c3d-1111-2222-3333-444455556666/scratchpad/pg.py",
                     "/tmp/claude-501/-Users-someone-project/scratchpad/pg.py",
                     "/var/folders/zz/abc123/T/tmp.Xy12/pg.py",
                     "/Users/someone/project/.claude/worktrees/agent-a0198f33ca9da0709/pg.py"):
            self.refused(self.add("Fetch the page with the helper at %s and pass it the regular expression.\n" % path), path)

    def test_a_session_id_is_refused(self):
        sid = "09f47a44-bbcb-4125-a53e-ba217729c8cb"
        self.refused(self.add("The helper was written in %s; run it with the address and the pattern.\n" % sid), sid)

    def test_text_about_this_session_is_refused(self):
        for phrase in ("earlier in this session", "In this conversation"):
            self.refused(self.add("%s the page was fetched with curl and searched with a small script.\n" % phrase),
                         phrase)

    def test_the_description_is_read_too(self):
        proc = self.add("Fetch it with curl -s and search the output with grep -o.\n",
                        when="Use when the helper from earlier in this session is missing.")
        self.refused(proc, "earlier in this session")

    def test_as_written_records_it(self):
        proc = self.add("In this session the page was fetched with curl.\n", "--as-written")
        self.assertExit(proc, 0)
        self.assertTrue(os.path.isdir(self.box.lesson_dir("fetch-and-search")))

    def test_what_a_lesson_may_say_is_accepted(self):
        """Each of these is in a real lesson, or is what one says about a temporary file."""
        for index, body in enumerate((
            "Write the program to a .py file in the scratchpad and run that.\n",
            "`path` is tied to PATH in zsh: `path=/tmp/x` empties it. Name the variable something else.\n",
            "Write the output to /tmp/out.log and grep that file for the pass line.\n",
            "A permission granted for one session does not reach its subagents.\n",
            "Screenshots written under a scratchpad path are denied; give the tool a directory in the repository.\n",
            "The commit 0a1b2c3d4e5f60718293a4b5c6d7e8f901234567 is the base; a uuid4() names each run.\n",
        )):
            proc = self.add(body, name="accepted-%d" % index)
            self.assertExit(proc, 0)

    def test_an_update_with_a_new_body_is_read_and_one_without_is_not(self):
        self.assertExit(self.add("Fetch it with curl -s and search the output with grep -o.\n"), 0)
        proc = self.box.run("add", "--update", "--name", "fetch-and-search", "--body",
                            "Earlier in this session the helper pg.py did this.\n")
        self.assertExit(proc, 2)
        self.assertIn("--as-written", proc.stderr)
        proc = self.box.run("add", "--update", "--name", "fetch-and-search", "--match", r"\bcurl\s+-s\b")
        self.assertExit(proc, 0)
        proc = self.box.run("add", "--update", "--name", "fetch-and-search", "--as-written", "--body",
                            "Earlier in this session the helper pg.py did this.\n")
        self.assertExit(proc, 0)

    def test_a_lesson_written_by_hand_with_residue_can_still_be_given_a_guard(self):
        """--update without a new body does not read the text it keeps."""
        self.box.write_lesson(self.box.lesson_dir("by-hand"), "by-hand", description="Use when written by hand.",
                              body="In this session it was /tmp/claude-501/x/scratchpad/a.py.\n")
        proc = self.box.run("add", "--update", "--name", "by-hand", "--match", "danger")
        self.assertExit(proc, 0)


if __name__ == "__main__":
    unittest.main()
