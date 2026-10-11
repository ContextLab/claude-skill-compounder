#!/usr/bin/env python3
"""A probe stops a call that cannot run, and zsh itself says which calls those are.

The lesson `probe: unmatched-glob` reads the command and the directory: a word with an
unquoted `*` or `?` that matches no file is one zsh refuses with "no matches found",
running nothing of the line. Every case here is RUN in the real zsh, in a directory with
known files, and `compound check` must stop exactly the calls zsh refused."""

import json
import os
import shutil
import subprocess
import unittest

from test_support import Case

# Stopped by zsh and by the probe, or by neither. Each command only prints.
CASES = [
    "echo *.nope",
    "echo *.py",
    "ls sub/*.py",
    "ls sub/*.md",
    "echo '*.nope'",
    'echo "*.nope"',
    "echo \\*.nope",
    ": --include=*.rs",
    ": --include='*.rs'",
    "echo https://example.invalid/api?x=1",
    "echo 'https://example.invalid/api?x=1'",
    "echo a?c",
    "echo ?.py",
    "S=sub; echo $S/*.py",
    "S=sub; echo $S/*.md",
    "S=sub; echo \"$S\"/*.py",
    "cd sub && echo *.py",
    "cd sub && echo *.md",
    "true && echo zz*",
    "echo ok; ls q*.txt 2>/dev/null",
    "for f in *.nope; do echo $f; done",
    "for f in *.py; do echo $f; done",
    "cat <<'EOF'\n*.nope\nEOF",
    "echo done # *.nope",
    "x=*.nope; echo set",
    "[[ a.py == *.nope ]] || echo different",
    "case a.py in *.nope) echo yes;; *) echo no;; esac",
    "setopt null_glob; echo *.nope",
    "noglob echo *.nope",
    "echo sp*",
    "echo 'sp ace'*",
    "echo sp\\ ace*",
    "echo 'sp ace'.nope*",
    "printf '%s\\n' a.py *.txt",
    "printf '%s\\n' a.py *.txt *.nope",
    "echo ~/definitely-not-here-*",
    "sh -c 'echo *.nope'",
    "bash -c 'true; echo *.nope' && echo ran",
    "echo before; sh -c \"echo *.nope\"; echo after",
]
# What zsh refuses and the probe leaves alone, because this reading does not follow it. A
# probe's hit is certain; what it is not sure of it does not stop.
LEFT_ALONE = [
    "echo [z]*.nope",
    "echo {a,b}*.nope",
    "(echo *.nope)",
    "echo **/*.nope",
    "echo $UNSET_HERE/*.nope",
    "echo \"$(echo *.nope)\"",
    "zsh -f -c 'echo *.nope'",
]


@unittest.skipUnless(shutil.which("zsh"), "the probe is about zsh, and zsh is not installed here")
class UnmatchedGlobTest(Case):
    def setUp(self):
        super().setUp()
        self.work = os.path.join(self.box.root, "work")
        os.makedirs(os.path.join(self.work, "sub"))
        for name in ("a.py", "b.py", "notes.txt", "sp ace.txt", os.path.join("sub", "c.md")):
            with open(os.path.join(self.work, name), "w") as handle:
                handle.write("x\n")
        self.box.write_lesson(self.box.lesson_dir("glob-matches-nothing", "user"), "glob-matches-nothing",
                              "Use when zsh says no matches found.", "Quote the pattern.\n",
                              extra="shell: zsh\nprobe: unmatched-glob\n")

    def zsh_refuses(self, command):
        out = subprocess.run(["zsh", "-f", "-c", command], cwd=self.work, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True, timeout=20,
                             env={"PATH": "/usr/bin:/bin", "HOME": self.box.home, "UNSET_HERE": ""})
        return "no matches found" in out.stderr

    def check(self, command, cwd=None, **kw):
        call = {"tool": "Bash", "input": {"command": command}}
        if cwd is not False:
            call["cwd"] = cwd or self.work
        kw.setdefault("COMPOUND_SHELL", "zsh")
        return self.box.json("check", stdin=json.dumps(call), **kw)["hits"]

    def test_the_probe_stops_exactly_the_calls_zsh_refuses(self):
        refused = 0
        for command in CASES:
            with self.subTest(command=command):
                wanted = self.zsh_refuses(command)
                refused += wanted
                self.assertEqual(bool(self.check(command)), wanted, command)
        # Both kinds are well represented, or the comparison shows nothing.
        self.assertGreaterEqual(refused, 12)
        self.assertGreaterEqual(len(CASES) - refused, 12)

    def test_what_it_cannot_be_sure_of_it_does_not_stop(self):
        for command in LEFT_ALONE:
            with self.subTest(command=command):
                self.assertTrue(self.zsh_refuses(command) or "UNSET" in command, command)
                self.assertEqual(self.check(command), [], command)

    def test_a_hit_is_sure_and_names_the_words(self):
        hits = self.check("grep -rn TODO --include=*.rs . ; ls q*.txt")
        self.assertEqual([(hit["name"], hit["sure"], hit["words"]) for hit in hits],
                         [("glob-matches-nothing", True, ["--include=*.rs", "q*.txt"])])
        self.assertIn("Quote the pattern.", hits[0]["text"])

    def test_it_reads_the_directory_the_call_runs_in(self):
        self.assertEqual(self.check("echo *.md"), self.check("echo *.md")[:1])
        self.assertTrue(self.check("echo *.md"))
        self.assertEqual(self.check("echo *.md", cwd=os.path.join(self.work, "sub")), [])
        # With no directory given there is nothing to read, and nothing is stopped.
        self.assertEqual(self.check("echo *.nope", cwd=False), [])
        self.assertEqual(self.check("echo *.nope", cwd=os.path.join(self.work, "absent")), [])

    def test_it_applies_where_the_lesson_does(self):
        self.assertEqual(self.check("echo *.nope", COMPOUND_SHELL="bash"), [])
        said = self.box.json("check", "--guards", COMPOUND_SHELL="zsh",
                             stdin=json.dumps({"tool": "Bash", "input": {"command": "true"}, "cwd": self.work}))
        self.assertEqual((said["guards"], said["tools"]), (1, ["Bash"]))

    def test_a_probe_this_version_does_not_have_is_reported_and_stops_nothing(self):
        self.box.write_lesson(self.box.lesson_dir("from-the-future", "user"), "from-the-future",
                              "Use when a later version checks more.", "Body.\n", extra="probe: time-travel\n")
        self.assertEqual([hit["name"] for hit in self.check("echo *.nope")], ["glob-matches-nothing"])
        # A lesson that does not read is a failed health check: status says which and why.
        self.assertIn("time-travel", self.box.run("status", "--json").stdout)


if __name__ == "__main__":
    unittest.main()
