#!/usr/bin/env python3
"""Tests of guard_text against the real shells. No mocks.

Each case is a command in which `echo M<n>` appears several times, some as a command
and some as data (in a quoted string, a here-document body, a comment). The command is
RUN in zsh and in bash, and the markers the shell printed on a line of their own are the
ones that were commands. guard_text must name exactly those: a pattern anchored where a
command starts, searched with guard_search, finds those markers and no other.

    python3 notes/2026-10-11-usage-audit/guard_text_test.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_text as g  # noqa: E402

# No anchor: where a command starts is the classifier's to say, and that is what is tested.
MARK = re.compile(r"()echo (M\d+)\b", re.MULTILINE)

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
        out = subprocess.run([shell, "-c", command], cwd=tmp, capture_output=True, text=True, timeout=20)
    lines = (out.stdout + "\n" + out.stderr).split("\n")
    return sorted(line for line in lines if re.fullmatch(r"M\d+", line))


def found(command):
    text, kinds = g.guard_view(command)
    return sorted(m.group(2) for m in MARK.finditer(text) if g.starts_in_command(m, kinds))


class Differential(unittest.TestCase):
    def test_every_case_in_every_shell(self):
        shells = [s for s in ("zsh", "bash", "sh") if shutil.which(s)]
        self.assertIn("zsh", shells)
        self.assertIn("bash", shells)
        for name, command in CASES:
            got = found(command)
            for shell in shells:
                if shell == "sh" and ("<<<" in command or "$'" in command):
                    continue  # not in POSIX sh
                with self.subTest(case=name, shell=shell):
                    self.assertEqual(ran(shell, command), got, "%s\n%s\n%s" % (name, command, g.classify(command)))

    def test_cases_are_not_trivial(self):
        """Each case has a marker that is data, or it tests nothing; the raw text is
        wrong on it."""
        differ = 0
        for name, command in CASES:
            raw = sorted(m.group(2) for m in MARK.finditer(command))
            differ += raw != found(command)
        self.assertGreaterEqual(differ, 30)


class Views(unittest.TestCase):
    def test_view_drops_bodies_and_comments_only(self):
        command = "cat > f <<'EOF'\nbody 'q'\nEOF\necho \"kept $(date)\" 'kept' # gone\nls"
        text, kinds = g.guard_view(command)
        self.assertEqual(text, "cat > f <<'EOF'\n\necho \"kept $(date)\" 'kept' \nls")
        self.assertEqual(len(text), len(kinds))

    def test_match_may_run_into_a_quoted_argument(self):
        sed = re.compile(r"(^\s*|[;&|(]\s*)sed\s+-i\s+['\"]?s/", re.MULTILINE)
        self.assertIsNotNone(g.guard_search(sed, "sed -i 's/a/b/' f.txt"))
        self.assertIsNone(g.guard_search(sed, "echo 'run: sed -i s/a/b/ f.txt'"))
        self.assertIsNone(g.guard_search(sed, "git commit -m \"fix\n\nsed -i 's/a/b/' was wrong\""))

    def test_match_inside_a_quoted_argument_does_not_count(self):
        commit = re.compile(r";\s*git\s+commit\b", re.MULTILINE)
        self.assertIsNotNone(g.guard_search(commit, "pytest -q; git commit -m x"))
        self.assertIsNone(g.guard_search(commit, "grep '; git commit' notes.md"))
        self.assertIsNone(g.guard_search(commit, "cat >> notes.md <<'EOF'\npytest; git commit\nEOF"))

    def test_simple_commands(self):
        self.assertEqual(g.simple_commands("a 'x; y' && b | c\n(d; e) # f"),
                         ["a 'x; y'", "b", "c", "d", "e"])

    def test_never_raises(self):
        for command in ["'", '"', "$(", "`", "<<", "<<'", "cat <<EOF", "a)b)c)", "${", "((", "\\",
                        "x <<- \n", "$((", "\"$(", "case x in a) echo;; esac", "(" * 3000]:
            g.classify(command)
            g.guard_view(command)
            g.simple_commands(command)


if __name__ == "__main__":
    unittest.main(verbosity=1)
