#!/usr/bin/env python3
"""A guard's pattern is tested against command text, and the real shells say what that is.

Each case is a command in which `echo M<n>` appears several times, some as a command and
some as data (in a quoted string, a here-document body, a comment). The command is RUN in
zsh, bash and sh, and the markers a shell printed on a line of their own are the ones that
were commands. `compound check`, with one guard for each marker, must stop the call for
exactly those: a pattern matches where a command runs and nowhere else."""

import json
import re
import shutil
import subprocess
import tempfile
import unittest

from test_support import Case

MARKERS = 4

# (name, command). Every `cat` discards what it reads so only commands print.
CASES = [
    ("heredoc quoted delimiter",
     "echo M1\ncat >/dev/null <<'EOF'\necho M2\n$(echo M3)\nEOF\necho M4"),
    ("heredoc double-quoted delimiter",
     "cat >/dev/null <<\"EOF\"\necho M1\nEOF\necho M2"),
    ("heredoc backslash delimiter",
     "cat >/dev/null <<\\EOF\necho M1\nEOF\necho M2"),
    ("heredoc with tabs stripped",
     "cat >/dev/null <<-EOF\n\techo M1\n\tEOF\necho M2"),
    ("heredoc <<- with a quoted delimiter",
     "cat >/dev/null <<-'END'\n\techo M1\n\t\tEND\necho M2"),
    ("heredoc with expansion: $( ) in the body runs",
     "cat >/dev/null <<EOF\necho M1\n$(echo M2 >&2; echo M3 >&2)\nEOF\necho M4"),
    ("heredoc with expansion: backticks in the body run",
     "cat >/dev/null <<EOF\necho M1 `echo M2 >&2`\nEOF\necho M3"),
    ("heredoc with expansion: an escaped $( does not run",
     "cat >/dev/null <<EOF\n\\$(echo M1 >&2)\nEOF\necho M2"),
    ("heredoc quoted: $( ) in the body does not run",
     "cat >/dev/null <<'EOF'\n$(echo M1 >&2)\n`echo M2 >&2`\nEOF\necho M3"),
    ("command after the heredoc operator on the same line",
     "cat >/dev/null <<'EOF' && echo M1\necho M2\nEOF\necho M3"),
    ("pipe after the heredoc operator",
     "cat <<'EOF' | cat >/dev/null; echo M1\necho M2\nEOF\necho M3"),
    ("two heredocs on one line",
     "cat >/dev/null <<'A'; cat >/dev/null <<'B'\necho M1\nA\necho M2\nB\necho M3"),
    ("the body starts after the first newline that is not inside quotes",
     "cat >/dev/null <<'EOF' && printf %s \"a\necho M1\n\" >/dev/null && echo M2\necho M3\nEOF\necho M4"),
    ("heredoc inside a loop body",
     "for i in 1; do cat >/dev/null <<EOF\necho M1\nEOF\necho M2; done"),
    ("heredoc whose operator has no space and a redirect after it",
     "cat <<EOF>/dev/null\necho M1\nEOF\necho M2"),
    ("a delimiter that only looks closed",
     "cat >/dev/null <<'EOF'\n EOF\necho M1\nEOFX\nEOF\necho M2"),
    ("heredoc fed to bash: the body is commands",
     "bash <<'EOF'\necho M1\nEOF\necho M2"),
    ("heredoc fed to sh -s",
     "sh -s <<EOF\necho M1\nEOF\necho M2"),
    ("heredoc fed to bash, with a heredoc inside it",
     "bash <<'OUT'\necho M1\ncat >/dev/null <<'IN'\necho M2\nIN\necho M3\nOUT\necho M4"),
    ("heredoc fed to python: the body is not commands",
     "python3 - <<'EOF' >/dev/null\nx = 'echo M1'\nEOF\necho M2"),
    ("heredoc fed to a shell that was given -c: the body is its input",
     "bash -c 'cat >/dev/null; echo M1' <<'EOF'\necho M2\nEOF\necho M3"),
    ("here-string",
     "cat >/dev/null <<< 'echo M1'; echo M2"),
    ("here-string fed with a double-quoted word",
     "cat >/dev/null <<<\"x\necho M1\"\necho M2"),
    ("single quotes",
     "printf %s 'a; echo M1' >/dev/null; echo M2"),
    ("single quotes over several lines",
     "printf %s 'a\necho M1\n' >/dev/null\necho M2"),
    ("double quotes",
     "printf %s \"a; echo M1\" >/dev/null; echo M2"),
    ("double quotes over several lines",
     "printf %s \"a\necho M1\n\" >/dev/null\necho M2"),
    ("escaped quotes inside double quotes",
     "printf %s \"a \\\" ; echo M1 \\\" b\" >/dev/null; echo M2"),
    ("escaped quote outside quotes",
     "printf %s \\'x >/dev/null; echo M1; printf %s \\\" >/dev/null; echo M2"),
    ("the '\\'' idiom",
     "printf %s 'it'\\''s; echo M1' >/dev/null; echo M2"),
    ("ANSI-C quotes with an escaped quote",
     "printf %s $'a\\'; echo M1' >/dev/null; echo M2"),
    ("$( ) inside double quotes runs",
     "printf %s \"x $(echo M1 >&2; echo M2 >&2) y\" >/dev/null; echo M3"),
    ("quotes inside $( ) inside double quotes",
     "printf %s \"x $(printf %s \"; echo M1\" >/dev/null; echo M2 >&2) y\" >/dev/null; echo M3"),
    ("single quotes inside $( )",
     "x=$(printf %s '; echo M1'; echo M2 >&2); echo M3"),
    ("backticks",
     "x=`echo M1 >&2`; printf %s \"`echo M2 >&2`\" >/dev/null; echo M3"),
    ("a heredoc inside $( ) inside double quotes (the git commit form)",
     "printf %s \"$(cat <<'EOF'\necho M1\nEOF\n)\" >/dev/null && echo M2"),
    ("comment",
     "echo M1 # ; echo M2\n# echo M3\necho M4"),
    ("a hash that is not a comment",
     "printf %s a#b >/dev/null; echo M1; x=abc; printf %s ${#x} >/dev/null; echo M2"),
    ("bash -c with single quotes: the string is commands",
     "bash -c 'echo M1; printf %s \"; echo M2\" >/dev/null'; echo M3"),
    ("bash -c with double quotes",
     "bash -c \"echo M1; printf %s '; echo M2' >/dev/null\"; echo M3"),
    ("sh -lc and eval",
     "sh -c 'echo M1'; eval 'echo M2'; eval \"echo M3\"; echo M4"),
    ("python -c is not a shell",
     "python3 -c 'x = \"\"\"\necho M1\n\"\"\"'; echo M2"),
    ("arithmetic shift is not a heredoc",
     "x=$((1<<3))\necho M1\nprintf %s $x >/dev/null\necho M2"),
    ("parameter expansion with quotes",
     "x=${UNSET_VAR_FOR_TEST:-\"a; echo M1\"}; printf %s \"$x\" >/dev/null; echo M2"),
    ("subshell and group",
     "(echo M1); { echo M2; }; if true; then echo M3; fi; if false; then :; else echo M4; fi"),
    ("loop body",
     "for i in 1; do echo M1; done; printf %s 'do echo M2' >/dev/null"),
    ("line continuation",
     "printf %s a \\\n  'echo M1' >/dev/null; echo M2"),
    ("an unclosed heredoc runs to the end",
     "echo M1\ncat >/dev/null <<'EOF'\necho M2\necho M3"),
]


def ran(shell, command):
    with tempfile.TemporaryDirectory() as tmp:
        out = subprocess.run([shell, "-c", command], cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, timeout=20)
    lines = (out.stdout + "\n" + out.stderr).split("\n")
    return sorted(line for line in lines if re.fullmatch(r"M\d+", line))


class CommandTextTest(Case):
    def setUp(self):
        super().setUp()
        for number in range(1, MARKERS + 1):
            self.box.add("marker-%d" % number, "Use when the marker %d is echoed." % number,
                         "The marker %d ran as a command.\n" % number, "--level", "user",
                         "--match", r"echo M%d\b" % number, "--new")

    def stopped(self, command):
        hits = self.box.json("check", stdin=json.dumps({"tool": "Bash", "input": {"command": command}}))["hits"]
        return sorted("M" + hit["name"].split("-")[1] for hit in hits)

    def test_every_case_in_every_shell(self):
        shells = [shell for shell in ("zsh", "bash", "sh") if shutil.which(shell)]
        self.assertIn("bash", shells)
        differ = 0
        for name, command in CASES:
            got = self.stopped(command)
            differ += got != sorted(set("M" + n for n in re.findall(r"echo M(\d+)\b", command)))
            for shell in shells:
                if shell == "sh" and ("<<<" in command or "$'" in command):
                    continue  # not in POSIX sh
                with self.subTest(case=name, shell=shell):
                    self.assertEqual(ran(shell, command), got, "%s\n%s" % (name, command))
        # Each case has a marker that is data, or it tests nothing.
        self.assertGreaterEqual(differ, 30)

    def test_a_match_may_run_into_a_quoted_argument_and_may_not_start_in_one(self):
        self.box.add("sed-in-place", "Use when sed -i has no suffix.", "Pass a suffix.\n", "--level", "user",
                     "--match", r"(^\s*|[;&|(]\s*)sed\s+-i\s+['\"]?s/", "--new")
        self.box.add("commit-after-semicolon", "Use when a commit follows a semicolon.", "Chain with &&.\n",
                     "--level", "user", "--match", r";\s*git\s+commit\b", "--new")

        def names(command):
            hits = self.box.json("check", stdin=json.dumps({"tool": "Bash", "input": {"command": command}}))["hits"]
            return [hit["name"] for hit in hits]

        self.assertEqual(names("sed -i 's/a/b/' f.txt"), ["sed-in-place"])
        self.assertEqual(names("echo 'run: sed -i s/a/b/ f.txt'"), [])
        self.assertEqual(names("git commit -m \"fix\n\nsed -i 's/a/b/' was wrong\""), [])
        self.assertEqual(names("pytest -q; git commit -m x"), ["commit-after-semicolon"])
        self.assertEqual(names("grep '; git commit' notes.md"), [])
        self.assertEqual(names("cat >> notes.md <<'EOF'\npytest; git commit\nEOF"), [])
        self.assertEqual(names("bash -c 'pytest -q; git commit -m x'"), ["commit-after-semicolon"])
        self.assertEqual(names("ls # ; git commit"), [])

    def test_another_tools_input_is_tested_as_it_is(self):
        """The reading of command text is for a Bash command. A lesson that names another
        tool is tested against the JSON of that tool's input, quotes and all."""
        self.box.add("env-file", "Use when an .env file is written.", "Do not write .env.\n", "--level", "user",
                     "--match", r'"file_path": "[^"]*\.env"', "--tool", "Write", "--new")
        hits = self.box.json("check", stdin=json.dumps({"tool": "Write", "input": {"file_path": "/p/.env", "content": "x"}}))
        self.assertEqual([hit["name"] for hit in hits["hits"]], ["env-file"])

    def test_a_command_the_scanner_cannot_follow_is_still_answered(self):
        for command in ["'", '"', "$(", "`", "<<", "<<'", "cat <<EOF", "a)b)c)", "${", "((", "\\", "x <<- \n",
                        "$((", "\"$(", "case x in a) echo M1;; esac", "(" * 3000]:
            proc = self.box.run("check", stdin=json.dumps({"tool": "Bash", "input": {"command": command}}))
            self.assertExit(proc, 0)
            self.assertIn("hits", json.loads(proc.stdout))


if __name__ == "__main__":
    unittest.main()
