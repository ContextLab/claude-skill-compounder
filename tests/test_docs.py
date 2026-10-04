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

    def test_one_claude_code_minimum_everywhere(self):
        """The CLI holds the number; the README and the design say the same one."""
        found = re.search(r"^CLAUDE_CODE_MIN = \((\d+), (\d+), (\d+)\)", read("bin", "compound"), re.M)
        self.assertIsNotNone(found, "bin/compound defines CLAUDE_CODE_MIN")
        version = ".".join(found.groups())
        readme = read("README.md")
        self.assertIn("Claude Code %s or later" % version, readme)
        self.assertIn("Claude Code %s or later" % version, read("docs", "design.md"))
        requirements = [line for line in readme.splitlines() if line.startswith("**Requirements:**")]
        self.assertEqual(len(requirements), 1)
        self.assertEqual(re.findall(r"Claude Code (\d+\.\d+\.\d+) or later", readme), [version] * readme.count(
            "Claude Code %s or later" % version), "the README names another minimum somewhere")
        rows = [line for line in readme.splitlines() if line.startswith("| `claude code` |")]
        self.assertEqual(len(rows), 2, "Troubleshooting has a FAIL and a WARN row for `claude code`")
        for line in rows:
            self.assertEqual(set(re.findall(r"\d+\.\d+\.\d+", line)), {version}, line)

    def test_one_oldest_release_in_the_installer_and_the_cli(self):
        found = re.search(r"^RELEASE_MIN = \((\d+), (\d+), (\d+)\)", read("bin", "compound"), re.M)
        self.assertIsNotNone(found, "bin/compound defines RELEASE_MIN")
        version = ".".join(found.groups())
        self.assertRegex(read("install.sh"), r'(?m)^min_release="%s"$' % re.escape(version))
        self.assertIn("v%s" % version, read("docs", "design.md"))

    def test_the_readme_gives_the_install_and_uninstall_one_liners(self):
        readme = read("README.md")
        section = readme.split("## Install", 1)[1].split("\n## ", 1)[0]
        url = "https://raw.githubusercontent.com/ContextLab/claude-skill-compounder/main/install.sh"
        for line in ("curl -fsSL %s | bash" % url,
                     "curl -fsSL %s | bash -s -- uninstall" % url,
                     "curl -fsSL %s | bash -s -- uninstall --purge" % url):
            self.assertIn(line + "\n", section)
        design = read("docs", "design.md")
        self.assertIn("curl -fsSL %s | bash -s -- uninstall" % url, design)

    def test_the_readme_says_which_platforms_were_tested(self):
        section = read("README.md").split("## Install", 1)[1].split("\n## ", 1)[0]
        self.assertIn("**Platforms:**", section)
        for word in ("macOS", "Linux", "Windows", "not tested"):
            self.assertIn(word, section)

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

    def test_one_word_for_each_event_type_in_the_cli_the_pane_and_the_design(self):
        """The log's type names are the contract; what a person is shown for each is one
        word, the same in `compound status`, on the pane and in the design's table."""
        cli = read("bin", "compound")
        types = re.findall(r'"([a-z]+)"', cli.split("EVENT_TYPES = (", 1)[1].split(")", 1)[0])
        self.assertGreaterEqual(len(types), 14, types)
        in_cli = dict(re.findall(r'"([a-z]+)": "([a-z]+)"', cli.split("EVENT_WORDS = {", 1)[1].split("}", 1)[0]))
        in_pane = dict(re.findall(r"([a-z]+): '([a-z]+)'", read("hooks", "view.ts").split("export const WORDS", 1)[1].split("}", 1)[0]))
        # The table sits in a list item, indented.
        rows = table_rows("\n".join(line.strip() for line in read("docs", "design.md").splitlines()), "- **Words**")
        in_design = {cells[0].strip("`"): cells[1].strip("`") for cells in rows}
        self.assertEqual(sorted(in_cli), sorted(types), "EVENT_WORDS has a word for every type and no other")
        self.assertEqual(in_pane, in_cli)
        self.assertEqual(in_design, in_cli)
        self.assertEqual(len(set(in_cli.values())), len(in_cli), "two types share a word")

    def test_the_design_says_when_text_output_is_coloured_and_how_wide_it_is(self):
        design = read("docs", "design.md")
        section = design.split("- **Text output of the CLI**", 1)[1].split("\n- **", 1)[0]
        for name in ("NO_COLOR", "COLUMNS", "TERM", "--json"):
            self.assertIn(name, section)
            self.assertIn(name, read("bin", "compound"))

    def test_the_documents_use_the_words_the_code_shows(self):
        """A label the band no longer draws is not in the documents."""
        for rel in (("README.md",), ("docs", "design.md")):
            text = read(*rel)
            for gone in ("reusable`", "strengthening owed`", "unsettled from earlier sessions", "USE/GRD/RCL", "lesson or skill`"):
                self.assertNotIn(gone, text, rel)
        view = read("hooks", "view.ts")
        design = read("docs", "design.md")
        labels = re.findall(r"label: '([^']+)'", view.split("export const NOTES", 1)[1].split("export const HINT", 1)[0])
        labels += re.findall(r"export const (?:OWED|WEAK): Look = \{[^}]*label: '([^']+)'", view)
        self.assertGreaterEqual(len(labels), 17, labels)
        for label in labels:
            self.assertIn("`%s`" % label, design, "the band's label %r is not in the design's table" % label)

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
        for term in ("level", "recalled", "general pool", "prompt log", "band", "pane"):
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


DOCUMENTS = (("README.md",), ("docs", "guide.md"), ("docs", "design.md"), ("CONTRIBUTING.md",))


def prose(text):
    """A document without its fenced blocks: what is in one is an example, not a link or a heading."""
    return re.sub(r"(?ms)^```.*?^```[^\n]*$", "", text)


def anchors(text):
    """The anchors GitHub gives the headings of a Markdown document."""
    seen = {}
    out = set()
    for title in re.findall(r"(?m)^#{1,6} +(.+?)\s*$", prose(text)):
        slug = re.sub(r"[^a-z0-9 _-]", "", title.lower()).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        out.add(slug if count == 0 else "%s-%d" % (slug, count))
    return out


class LinkTest(unittest.TestCase):
    LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)|(?:src|href)=\"([^\"]+)\"")

    def test_every_relative_link_and_anchor_in_the_documents_resolves(self):
        checked = 0
        for rel in DOCUMENTS:
            text = read(*rel)
            base = os.path.dirname(os.path.join(REPO, *rel))
            for found in self.LINK.finditer(prose(text)):
                target = found.group(1) or found.group(2)
                if re.match(r"[a-z]+:", target):
                    continue  # an external address: fetched by hand, not by a test
                path, _, anchor = target.partition("#")
                where = os.path.normpath(os.path.join(base, path)) if path else os.path.join(REPO, *rel)
                self.assertTrue(os.path.exists(where), "%s links to %s, which does not exist" % ("/".join(rel), target))
                if anchor:
                    self.assertTrue(where.endswith(".md"), "%s: an anchor into a file that is not Markdown: %s" % ("/".join(rel), target))
                    with open(where, encoding="utf-8") as handle:
                        self.assertIn(anchor, anchors(handle.read()),
                                      "%s links to %s, and that file has no such heading" % ("/".join(rel), target))
                checked += 1
        self.assertGreaterEqual(checked, 40, "the link pattern found too few links to be reading the documents")

    def test_the_anchor_rule_is_githubs(self):
        self.assertEqual(anchors("# A\n## Read `compound status`\n### 1. Reuse before building\n## A\n```\n# not one\n```\n"),
                         {"a", "read-compound-status", "1-reuse-before-building", "a-1"})


class GuideTest(Case):
    def subcommands(self):
        listing = self.box.run("--help").stdout.split("COMMAND\n", 1)[1].split("\n\n", 1)[0]
        names = re.findall(r"^    ([a-z]+)(?:\s|$)", listing, re.M)
        self.assertGreaterEqual(len(names), 20, names)
        return names

    def test_every_subcommand_is_in_the_guide(self):
        guide = read("docs", "guide.md")
        section = guide.split("## Every command", 1)[1]
        for name in self.subcommands():
            self.assertIn("`compound %s`" % name, section, "the guide's command table lacks `compound %s`" % name)
        for name in re.findall(r"`compound ([a-z]+)`", section):
            self.assertIn(name, self.subcommands(), "the guide's command table names a command the CLI does not have")

    def test_every_event_type_is_in_the_guides_table(self):
        cli = read("bin", "compound")
        types = re.findall(r'"([a-z]+)"', cli.split("EVENT_TYPES = (", 1)[1].split(")", 1)[0])
        rows = table_rows(read("docs", "guide.md"), "The columns are how long ago the event was")
        self.assertEqual(sorted(cells[0].strip("`") for cells in rows), sorted(types))

    def test_the_guide_names_the_rows_and_sections_status_prints(self):
        guide = read("docs", "guide.md")
        cli = read("bin", "compound")
        status = guide.split("## Read `compound status`", 1)[1].split("\n## ", 1)[0]
        for title in re.findall(r'head\("([A-Z][a-z ]+)"\)', cli.split("def cmd_status(", 1)[1].split("\ndef cmd_", 1)[0]):
            self.assertIn("| %s |" % title, status, "the guide's table of sections lacks %r" % title)
        labels = [cells[0].strip("`") for cells in table_rows(status, "The rows under `Open`:")]
        self.assertGreaterEqual(len(labels), 7)
        for label in labels:
            self.assertRegex(cli, r'out\("  %s +%%s|paint\("%s", RED\)' % (label, label),
                             "the guide names an Open row %r that `status` does not print" % label)
        for gone in ("USE/GRD/RCL", "| `skipped` |", "| `unsettled` |", "\nStore\n"):
            self.assertNotIn(gone, guide)

    def test_the_guides_examples_can_be_printed_again(self):
        """The guide says which script prints its outputs; the script exists and names no real directory."""
        guide = read("docs", "guide.md")
        self.assertIn("dev/guide_examples.py", guide)
        script = read("dev", "guide_examples.py")
        self.assertIn("--claude-dir", script)
        self.assertNotIn("expanduser", script)


class PoolTest(unittest.TestCase):
    def test_the_readme_and_the_design_list_everything_the_pool_ships(self):
        lessons = sorted(name for name in os.listdir(os.path.join(REPO, "lessons")) if not name.startswith("."))
        skills = sorted(name for name in os.listdir(os.path.join(REPO, "skills")) if not name.startswith("."))
        self.assertGreaterEqual(len(lessons), 6)
        self.assertGreaterEqual(len(skills), 4)
        readme = read("README.md").split("### The lessons that ship with compound", 1)[1].split("\n## ", 1)[0]
        design = read("docs", "design.md").split("## The general pool", 1)[1].split("\n## ", 1)[0]
        def named(text, header):
            # The table whose header row starts with `header`: its first column.
            return sorted(cells[0].strip("`") for cells in table_rows(text.replace(header, "TABLE\n" + header, 1), "TABLE\n"))

        for text, name in ((readme, "README.md"), (design, "docs/design.md")):
            self.assertEqual(named(text, "| Lesson |"), lessons, name)
            self.assertEqual(named(text, "| Skill |"), skills, name)

    def test_the_readme_shows_every_health_row(self):
        readme = read("README.md")
        checks = [cells[0].strip("`") for cells in table_rows(read("docs", "design.md"), "The health checks, in order:")]
        self.assertEqual(len(checks), 10, checks)
        sample = readme.split("Right after install, the report looks like this", 1)[1].split("```", 2)[1]
        trouble = readme.split("## Troubleshooting", 1)[1].split("\n## ", 1)[0]
        for name in checks:
            self.assertRegex(sample, r"(?m)^  (PASS|WARN|FAIL)  %s  " % re.escape(name))
            self.assertIn("| `%s` |" % name, trouble)
        for title in ("Health", "Compound interest", "Levels", "Lessons", "Recent", "Open"):
            self.assertRegex(sample, r"(?m)^%s$" % title)


if __name__ == "__main__":
    unittest.main()
