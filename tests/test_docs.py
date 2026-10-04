#!/usr/bin/env python3
"""The documents against the code: every name, option and claim the code has is written
down, and nothing is written down that the code does not have."""

import glob
import os
import re
import unittest

from test_support import REPO, Case

JOURNEYS = os.path.join(REPO, "tests", "journeys")


def read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as handle:
        return handle.read()


def table_rows(text, heading):
    """The rows of the first table under `heading`, as lists of cells."""
    section = text.split(heading, 1)[1]
    rows = []
    started = False
    for line in section.splitlines():
        if line.startswith("|"):
            started = True
            # A cell may hold `a\\|b`: an escaped pipe is not a separator.
            cells = [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            rows.append(cells)
        elif started:
            break
    return rows[2:]


class EnvironmentTest(unittest.TestCase):
    NAME = re.compile(r"\bCOMPOUND_[A-Z0-9_]+\b")

    def sources(self):
        files = [os.path.join(REPO, "bin", "compound"), os.path.join(REPO, "install.sh")]
        files += sorted(path for path in glob.glob(os.path.join(REPO, "hooks", "*.ts"))
                        if not path.endswith(".test.ts"))
        self.assertGreater(len(files), 5)
        return files

    def test_every_name_the_code_reads_is_in_the_design_table_and_no_other(self):
        used = {}
        for path in self.sources():
            with open(path, encoding="utf-8") as handle:
                for name in self.NAME.findall(handle.read()):
                    used.setdefault(name, set()).add(os.path.relpath(path, REPO))
        rows = table_rows(read("docs", "design.md"), "## Environment variables")
        listed = {}
        for cells in rows:
            self.assertEqual(len(cells), 4, cells)
            name = cells[0].strip("`")
            self.assertRegex(name, r"^COMPOUND_[A-Z0-9_]+$", cells)
            self.assertNotIn(name, listed, "listed twice")
            listed[name] = cells
        missing = sorted(set(used) - set(listed))
        self.assertEqual(missing, [], "read by the code and not in the table: %s" % {n: sorted(used[n]) for n in missing})
        self.assertEqual(sorted(set(listed) - set(used)), [], "in the table and read by no code")

    def test_the_read_by_column_names_who_reads_it(self):
        rows = table_rows(read("docs", "design.md"), "## Environment variables")
        readers = {"mod": [os.path.join("hooks", "")], "CLI": [os.path.join("bin", "compound")],
                   "installer": ["install.sh"]}
        for cells in rows:
            name = cells[0].strip("`")
            said = [part.strip() for part in cells[2].split(",")]
            for who in said:
                self.assertIn(who, readers, cells)
            for who, prefixes in readers.items():
                reads = False
                for path in self.sources():
                    rel = os.path.relpath(path, REPO)
                    if any(rel.startswith(prefix) for prefix in prefixes):
                        with open(path, encoding="utf-8") as handle:
                            reads = reads or re.search(r"\b%s\b" % name, handle.read()) is not None
                self.assertEqual(who in said, reads, "%s: the table says %s; %s %s it" % (
                    name, cells[2], who, "names" if reads else "does not name"))

    def test_the_readme_table_is_a_subset_that_links_to_the_full_one(self):
        readme = read("README.md")
        settings = readme.split("## Settings", 1)[1].split("\n## ", 1)[0]
        self.assertIn("docs/design.md#environment-variables", settings)
        full = {cells[0].strip("`"): cells for cells in table_rows(read("docs", "design.md"), "## Environment variables")}
        short = table_rows(readme, "## Settings")
        self.assertGreaterEqual(len(short), 5)
        for cells in short:
            name = cells[0].strip("`")
            self.assertIn(name, full)
            self.assertEqual(cells[1], full[name][1], "%s: the two tables give different defaults" % name)


class CliTableTest(Case):
    OPTION = re.compile(r"(?<![A-Za-z0-9-])(--[a-z][a-z0-9-]*)")

    def help(self, *args):
        proc = self.box.run(*(args + ("--help",)))
        self.assertExit(proc, 0)
        return proc.stdout

    def commands(self):
        # One line per subcommand under COMMAND; a long name has its text on the next line.
        listing = self.help().split("COMMAND\n", 1)[1].split("\n\n", 1)[0]
        names = re.findall(r"^    ([a-z]+)(?:\s|$)", listing, re.M)
        self.assertGreaterEqual(len(names), 15, names)
        return names

    def test_every_subcommand_and_option_of_the_parser_is_in_the_design_table(self):
        design = read("docs", "design.md")
        rows = table_rows(design, "## CLI contract")
        by_command = {}
        for cells in rows:
            found = re.match(r"`compound ([a-z]+)", cells[0])
            self.assertIsNotNone(found, cells)
            by_command[found.group(1)] = cells[0]
        self.assertIn("`--json`", design.split("## CLI contract", 1)[1].split("|", 1)[0])
        for name in self.commands():
            self.assertIn(name, by_command, "the subcommand has no row in the CLI table")
            options = set(self.OPTION.findall(self.help(name))) - {"--help", "--json"}
            documented = set(self.OPTION.findall(by_command[name]))
            self.assertEqual(sorted(options - documented), [], "compound %s: options missing from its row" % name)
            self.assertEqual(sorted(documented - options), [], "compound %s: its row names options it does not take" % name)
        self.assertEqual(sorted(set(by_command) - set(self.commands())), [])


class WordingTest(unittest.TestCase):
    def test_one_python_version_everywhere(self):
        self.assertIn("3.9 or later", read("README.md"))
        self.assertRegex(read("bin", "compound").split('"""')[1], r"runs on Python 3\.9 and later")
        design = read("docs", "design.md")
        self.assertIn("the interpreter is 3.9 or later", design)
        self.assertIn("Python 3.9 or later", design)
        for text in (read("README.md"), design, read("bin", "compound"), read("CONTRIBUTING.md")):
            self.assertNotIn("3.8", text)

    def test_every_claim_kind_the_mod_makes_is_in_the_design(self):
        source = read("hooks", "register.ts")
        kinds = set()
        for call in re.findall(r"(?:firstTime|mayRefuse)\(\$, sid, ([`'][^`']+[`'])", source):
            kinds.add(re.match(r"[`']([a-z]+)", call).group(1))
        self.assertGreaterEqual(len(kinds), 7, kinds)
        claims = [line for line in read("docs", "design.md").split("- **Claims**", 1)[1].split("\n- **", 1)[0].splitlines()]
        text = " ".join(claims)
        for kind in sorted(kinds):
            self.assertRegex(text, r"`%s(-<[^>]+>)*`" % kind, "the claim kind %r is not in the design's list" % kind)
        listed = set(re.findall(r"`([a-z]+)(?:-<[^`]+>)?`", text))
        self.assertEqual(sorted(listed - kinds), [], "listed in the design and made nowhere")

    def test_contributing_lists_every_journey_and_measurement_script(self):
        text = read("CONTRIBUTING.md")
        scripts = sorted(name for name in os.listdir(JOURNEYS)
                         if name.endswith(".py") and name != "common.py")
        self.assertGreaterEqual(len(scripts), 12)
        for name in scripts:
            lines = [line for line in text.splitlines() if "`%s`" % name in line or "/%s`" % name in line]
            self.assertEqual(len(lines), 1, "%s needs exactly one line in CONTRIBUTING.md" % name)
            self.assertGreater(len(lines[0].split("|")[2].strip()), 20, "%s: the line says what it does" % name)

    def test_the_readme_defines_its_terms_before_it_uses_them(self):
        readme = read("README.md")
        for term in ("mod", "lesson", "guard", "pattern", "status entry"):
            self.assertIn("**%s**" % term, readme, "%r is not defined" % term)
        for term in ("level", "recalled", "general pool", "prompt log"):
            bold = "**%s**" % term
            self.assertIn(bold, readme, "%r is not defined" % term)
            first = re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(term), readme)
            self.assertEqual(first.start(), readme.index(bold) + 2,
                             "%r is used (%r) before it is defined" % (
                                 term, readme[max(0, first.start() - 40):first.start() + 30]))

    def test_the_readme_says_what_uninstall_leaves(self):
        readme = read("README.md")
        section = readme.split("## Install", 1)[1].split("\n## ", 1)[0]
        for text in ("project lessons", "~/.claude/skills", "~/.claude/compound/app", "--purge"):
            self.assertIn(text, section)

    def test_the_readme_example_is_what_the_mod_adds(self):
        """hooks/render.test.ts pins the text `reuseContext` gives for these sample items;
        the README shows it, shortened only by `...` inside a quoted description."""
        test = read("hooks", "render.test.ts")
        found = re.search(r"const README_EXAMPLE = \[\n(.*?)\n\]\.join\('\\n'\)", test, re.S)
        self.assertIsNotNone(found, "render.test.ts has no README_EXAMPLE")
        lines = [eval(line.strip().rstrip(","), {"__builtins__": {}}) for line in found.group(1).splitlines()]
        readme = read("README.md")
        block = readme.split("[compound] Reuse before building.", 1)[1].split("```", 1)[0]
        shown = ["[compound] Reuse before building."] + [line for line in block.splitlines() if line]
        self.assertEqual(len(shown), len(lines), "the README example has other lines than the mod's text")
        for mine, real in zip(shown, lines):
            if "..." in mine:
                head, tail = mine.split("...", 1)
                self.assertIn('"', head, "only a quoted description is shortened: %r" % mine)
                self.assertTrue(real.startswith(head) and real.endswith(tail), "%r is not a shortening of %r" % (mine, real))
            else:
                self.assertEqual(mine, real)

    def test_no_shipped_file_tells_the_packages_history(self):
        words = re.compile(r"\b(the old (?:mod|package|version|cli|hooks?|scripts?)|previously|used to|formerly|legacy|until the review|was renamed)\b", re.I)
        shipped = ["README.md", "CONTRIBUTING.md", "install.sh", "run_tests.sh", os.path.join("bin", "compound"),
                   os.path.join("docs", "design.md"), os.path.join(".claude", "CLAUDE.md"),
                   os.path.join("skills", "learn", "SKILL.md"), os.path.join("skills", "reuse", "SKILL.md")]
        shipped += [os.path.relpath(path, REPO) for path in glob.glob(os.path.join(REPO, "hooks", "*.ts"))]
        for rel in shipped:
            for number, line in enumerate(read(rel).splitlines(), 1):
                found = words.search(line)
                self.assertIsNone(found, "%s:%d: %s" % (rel, number, line.strip()))

if __name__ == "__main__":
    unittest.main()
