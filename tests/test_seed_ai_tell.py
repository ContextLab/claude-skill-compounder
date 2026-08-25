#!/usr/bin/env python3
"""Tests the `ai-tell-audit` seed skill.

This skill ships no script, so there is no binary to run. What it ships is a
catalogue of writing tells, a disposition for every row, and three rules that
decide when a row fires at all. The document IS the program, and every claim
below is lifted out of `SKILL.md` at run time rather than copied into this file,
so an edit to the document that breaks one of its own load-bearing claims turns
this suite red instead of drifting away from it.

What is pinned here:

  1. Frontmatter parses, and the description is quoted. An unquoted `: ` inside
     a description empties the whole metadata block and the skill then never
     fires, silently.
  2. Every catalogue row carries exactly one disposition, and the disposition
     leads the cell. This is the thing most likely to rot as rows are added.
  3. The literal-exemption rule is file-wide and sits ABOVE the density rule.
     That ordering is what the regression corpus rests on: 13 correct uses of
     `test harness` in one 400-word page is 31 instances per thousand words,
     five times the documented rate, so density applied first would rewrite a
     term of art thirteen times.
  4. A regression corpus of human, pre-2022 technical prose, written for this
     suite in that register. Every catalogue pattern that occurs in it must be
     covered by a named exemption or by a Keep disposition, and the covering
     clause is asserted verbatim. Deleting the `harness` exemption turns this
     red.
  5. Rule zero: a banned-word list and a quoted block of machine prose are
     mentions, not uses, and nothing in them is edited.
  6. The skill does not commit its own tells. The scanner strips backticked
     spans AND quoted spans, because a checker that strips only backticks
     reports a false positive on the line `"It is worth noting that X" means X`.
     That mistake has been made against this file once already, so the scanner
     is itself tested against that line, and against a quotation that wraps
     across two source lines.
  7. Trigger precision: three must-fire prompts, three must-not-fire prompts,
     and no genre word from the description appearing in the must-not set.

No mocks. Real files on disk, read through the same parser in every test.
"""

import os
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "ai-tell-audit"
SKILL_MD = SKILL_DIR / "SKILL.md"
FIXTURES = REPO / "tests" / "fixtures" / "ai-tell-audit"

PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata",
                 "allowed-tools", "version"}

# Human prose. Every catalogue hit in these two must be exempt or Keep.
CORPUS = ["testing-methodology.rst", "submitting-patches.txt"]
# Mentions rather than uses. Every hit must sit inside a list item or a quote.
RULE_ZERO_FIXTURE = "contributing-banned-words.md"

EM_DASH = "\u2014"  # written as an escape so this file passes its own check

# Section headings, referred to by name so a rename fails loudly here.
EXEMPTION = "## Literal and terminological use is exempt, everywhere"
DENSITY = "## Density is the finding"
RULE_ZERO = "## Rule zero: never edit named or borrowed text"
DISPOSITIONS = "## Three dispositions"
KEEP = "## Keep by default"
AUTHORSHIP = "## Never a verdict on authorship"
STRUCTURAL = "## Structural families: what no word search catches"
CURRENCY = "## How to refresh the catalogue"

# Where the covering clause for each corpus pattern has to live.
EXEMPT_REGION, CATALOGUE_REGION, KEEP_REGION = "exemption", "catalogue", "keep"

# Pattern found in the corpus -> (region, the clause that must cover it).
# The clause is quoted verbatim from SKILL.md. Delete the clause, or move it out
# of its region, and the corpus test fails.
COVERAGE = {
    "harness": (EXEMPT_REGION, "A `test harness` is a term of art"),
    "robust": (EXEMPT_REGION, "`robust against malicious attack` carries a claim"),
    "the entire X": (EXEMPT_REGION, "`the entire filesystem` names a scope"),
    "---": (EXEMPT_REGION, "In reStructuredText it underlines a heading"),
    # No bullet of its own: "the file names a script" is the plain metalinguistic
    # verb, and the file-wide sentence is what covers it.
    "names": (EXEMPT_REGION,
              "None fires on the literal sense, on a term of art, or on markup "
              "the format requires."),
    # Exempted inside its own row rather than in the exemption section.
    "When it comes to X": (CATALOGUE_REGION, "(mid-sentence it is ordinary English)"),
    "real": (KEEP_REGION, "claudisms.ai calls this a preference"),
    "a real X": (KEEP_REGION, "collisions with shorter IDs a real possibility"),
}

# The four uses of `names` in the skill's own prose. Each is the metalinguistic
# sense (a phrase names the thing it denotes), which the file-wide rule exempts.
# Pinned as exact text: a fifth use, or a rewording of one of these into the
# knowing-narrator sense, is not covered and fails the self-audit.
SELF_EXEMPT = (
    "names a scope",
    "A document that *names* one of these patterns",
    "fires only when it names a genre above",
    "names genuine versus simulated",
)


def skill_text():
    return SKILL_MD.read_text()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "SKILL.md must open with a YAML frontmatter block"
    return m.group(1)


def body(text):
    return text.split("\n---\n", 1)[1]


def section_span(text, heading):
    """(start, end) character offsets of a `## ` section, heading included."""
    start = text.find("\n" + heading + "\n")
    assert start != -1, "no section %r in SKILL.md" % heading
    start += 1
    nxt = re.search(r"^## ", text[start + len(heading):], re.M)
    end = len(text) if not nxt else start + len(heading) + nxt.start()
    return start, end


def section(text, heading):
    start, end = section_span(text, heading)
    return text[start:end]


def flowed(text):
    """Text with its line wraps removed.

    Every clause this suite quotes out of SKILL.md is prose, and prose in this
    repository is hard-wrapped. Matching a quoted clause against the raw file
    fails the moment someone reflows a paragraph, which is not a defect.
    """
    return re.sub(r"[ \t]*\n[ \t]*", " ", text)


def tables(md):
    """Contiguous runs of `|` lines, in document order."""
    out, current = [], None
    for line in md.splitlines():
        if line.startswith("|"):
            current = current or []
            current.append(line)
        elif current:
            out.append(current)
            current = None
    if current:
        out.append(current)
    return out


def cells(line):
    return [c.strip() for c in line.strip("|").split("|")]


def catalogue_rows(md):
    """(pattern cell, disposition cell) for every two-column catalogue row."""
    rows = []
    for table in tables(md):
        header = cells(table[0])
        if len(header) != 2 or header[1] not in ("Fix", "Disposition"):
            continue
        for line in table[2:]:
            row = cells(line)
            if len(row) == 2:
                rows.append(tuple(row))
    return rows


def backticked(s):
    return re.findall(r"`([^`]+)`", s)


def catalogue_terms(md):
    terms = set()
    for pattern, _ in catalogue_rows(md):
        terms |= set(backticked(pattern))
    return terms


def keep_terms(md):
    """Patterns the `## Keep by default` section rescues without a table row."""
    return set(backticked(section(md, KEEP)))


def term_regex(term):
    """A matcher for one catalogue pattern.

    `X`, `Y`, `Z` and `[verb]` are placeholders and become one-word wildcards.
    A run of spaces becomes `\\s+`, because a phrase wraps across source lines.
    Word boundaries are applied only where the pattern actually ends in a word
    character, so `---` still matches a run of dashes.
    """
    parts = re.split(r"(\[[^\]]*\]|(?<![A-Za-z])[XYZ](?![A-Za-z]))", term)
    pattern = "".join(r"\S+" if i % 2 else re.escape(p).replace(r"\ ", r"\s+")
                      for i, p in enumerate(parts))
    prefix = r"(?<![\w-])" if term[0].isalnum() else ""
    suffix = r"(?![\w-])" if term[-1].isalnum() else ""
    return re.compile(prefix + pattern + suffix, re.IGNORECASE)


def _blank(match):
    """Replace a span with spaces, keeping newlines so line numbers survive."""
    return re.sub(r"[^\n]", " ", match.group(0))


def prose_only(md):
    """The document's own prose: no table rows, no headings, no backticked span,
    no quoted span.

    Quoted spans are removed from the WHOLE document rather than line by line,
    because the skill's quotations wrap. A line-at-a-time strip leaves half a
    quotation standing and reports its contents as the author's own words.
    """
    kept = "\n".join("" if line.startswith(("|", "#")) else line
                     for line in md.splitlines())
    kept = re.sub(r"`[^`]*`", _blank, kept, flags=re.S)
    kept = re.sub(r'"[^"]*"', _blank, kept, flags=re.S)
    return kept


def scan(text, terms):
    """[(term, line number, matched text, whole line)] for every hit."""
    lines = text.splitlines()
    hits = []
    for term in sorted(terms):
        for m in term_regex(term).finditer(text):
            n = text[:m.start()].count("\n")
            hits.append((term, n + 1, m.group(0), lines[n] if n < len(lines) else ""))
    return hits


def fixture(name):
    return (FIXTURES / name).read_text()


class FrontmatterTest(unittest.TestCase):
    """An unquoted colon here costs the whole skill, silently."""

    def setUp(self):
        self.text = skill_text()
        self.front = frontmatter(self.text)

    def raw_description(self):
        m = re.search(r"^description: (.*)$", self.front, re.M)
        self.assertIsNotNone(m, "SKILL.md needs a description")
        return m.group(1)

    def description(self):
        raw = self.raw_description()
        return raw[1:-1] if raw[:1] in "\"'" else raw

    def test_frontmatter_parses_as_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml not installed")
        spec = yaml.safe_load(self.front)
        self.assertIsInstance(spec, dict)
        self.assertEqual(spec["name"], SKILL_DIR.name)
        self.assertEqual(spec["description"], self.description())

    def test_only_portable_keys(self):
        keys = set(re.findall(r"^([A-Za-z][A-Za-z0-9_-]*):", self.front, re.M))
        self.assertEqual(keys - PORTABLE_KEYS, set(), "non-portable frontmatter keys")

    def test_name_matches_the_directory(self):
        name = re.search(r"^name: *(\S+)", self.front, re.M).group(1)
        self.assertEqual(name, SKILL_DIR.name)

    def test_description_is_double_quoted(self):
        """House rule, and the test below shows what it buys. An unquoted
        description that acquires a colon fails to parse, and the skill then
        loads with empty metadata and never fires."""
        raw = self.raw_description()
        self.assertEqual(raw[:1], '"', "the description must be double-quoted")
        self.assertEqual(raw[-1:], '"')

    def test_an_unquoted_description_with_a_colon_really_does_break_the_parse(self):
        """The reason for the rule above, demonstrated rather than asserted. A
        description grows a colon the first time someone adds an example prompt,
        and the failure is silent: the skill loads with no metadata."""
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml not installed")
        broken = "name: ai-tell-audit\ndescription: Use when: publishing a README\n"
        with self.assertRaises(yaml.YAMLError):
            yaml.safe_load(broken)
        quoted = broken.replace("Use when:", '"Use when:').replace("README", 'README"')
        self.assertEqual(yaml.safe_load(quoted)["description"],
                         "Use when: publishing a README")

    def test_description_under_500_chars(self):
        self.assertLessEqual(len(self.description()), 500,
                             "description is %d chars" % len(self.description()))

    def test_description_carries_both_halves_of_the_trigger(self):
        d = self.description()
        self.assertTrue(d.startswith("Use when"), d[:40])
        self.assertIn("NOT for", d, "the negative half of the trigger is missing")


class DispositionTest(unittest.TestCase):
    """Every row says exactly one of rewrite, delete, or keep, and says it first."""

    def setUp(self):
        self.text = skill_text()
        self.body = body(self.text)
        self.rows = catalogue_rows(self.body)

    def named_dispositions(self):
        """The three the document itself defines, taken from its own section."""
        found = re.findall(r"^\*\*([A-Z][a-z]+)\*\*",
                           section(self.body, DISPOSITIONS), re.M)
        return [d for d in found if d]

    def test_the_catalogue_actually_parsed(self):
        """A parse that silently finds nothing would pass every test below."""
        self.assertGreaterEqual(len(self.rows), 40,
                                "only %d catalogue rows parsed" % len(self.rows))
        self.assertGreaterEqual(len(catalogue_terms(self.body)), 80)

    def test_the_document_defines_exactly_three_dispositions(self):
        self.assertEqual(self.named_dispositions(), ["Rewrite", "Delete", "Keep"])

    def test_every_row_carries_exactly_one_disposition(self):
        """A row with none is unactionable; a row with two is a coin flip.

        The disposition is the FIRST word of the cell, and no second disposition
        may appear before the first sentence ends. Rows are allowed to name a
        different disposition in a following sentence as an exemption clause,
        which is what `Delete the bare label ... Keep X matters when Y` does.
        """
        vocabulary = self.named_dispositions()
        disposition = re.compile(r"(?<![\w-])(%s)(?![\w-])" % "|".join(vocabulary))
        for pattern, fix in self.rows:
            lead = disposition.match(fix)
            self.assertIsNotNone(
                lead, "no disposition leads the cell for row %r: %r" % (pattern, fix))
            first_sentence = re.split(r"(?<=[.?!])\s", fix)[0]
            found = disposition.findall(first_sentence)
            self.assertEqual(len(found), 1,
                             "row %r gives %d dispositions in one breath: %r"
                             % (pattern, len(found), fix))

    def test_every_row_names_at_least_one_pattern(self):
        for pattern, _ in self.rows:
            self.assertTrue(pattern.strip(), "an empty pattern cell")


class CrossTableConsistencyTest(unittest.TestCase):
    """The fast path summarises the catalogue, so it must not contradict it.

    A term appearing in both tables with opposite lead dispositions gives a reader
    a different answer depending on which table they reached first, and the fast
    path exists precisely so that a hurried reader never reaches the second one.
    """

    def setUp(self):
        self.rows = catalogue_rows(body(skill_text()))

    def lead(self, disposition):
        """The verb a reader acts on: the first disposition word in the cell."""
        low = disposition.lower()
        hits = [(low.find(d), d) for d in ("rewrite", "delete", "keep") if d in low]
        hits = [h for h in hits if h[0] >= 0]
        return min(hits)[1] if hits else None

    def test_a_term_in_two_tables_leads_with_the_same_disposition(self):
        leads = {}
        for pattern, disposition in self.rows:
            verb = self.lead(disposition)
            if verb is None:
                continue
            for term in backticked(pattern):
                key = term.strip().lower()
                leads.setdefault(key, set()).add(verb)
        conflicts = {t: sorted(v) for t, v in leads.items() if len(v) > 1}
        self.assertEqual(
            conflicts, {},
            "these terms lead with different dispositions in different tables: %s"
            % conflicts)


class RuleOrderingTest(unittest.TestCase):
    """The exemption is file-wide and comes first. The regression rests on it."""

    def setUp(self):
        self.text = skill_text()
        self.body = body(self.text)

    def test_the_exemption_precedes_the_density_rule(self):
        exemption, _ = section_span(self.body, EXEMPTION)
        density, _ = section_span(self.body, DENSITY)
        self.assertLess(exemption, density,
                        "density stated before the exemption fires on every "
                        "correct use of a term of art")

    def test_the_exemption_is_stated_as_file_wide(self):
        text = section(self.body, EXEMPTION)
        self.assertIn("File-wide", text)
        self.assertIn("Every row in this file", text)
        self.assertIn("None fires on the literal sense", text)

    def test_the_density_rule_defers_to_the_exemption_explicitly(self):
        """Ordering on the page is not enough: a reader who lands on the density
        section from a link has to be told which runs first."""
        self.assertIn("Apply the exemption first, then count", section(self.body, DENSITY))

    def test_the_worked_exemptions_the_regression_rests_on_are_present(self):
        text = flowed(section(self.body, EXEMPTION))
        for clause in ("A `test harness` is a term of art",
                       "`the entire filesystem` names a scope",
                       "`robust against malicious attack` carries a claim",
                       "robust in normal use",
                       "In reStructuredText it underlines a heading"):
            self.assertIn(clause, text, "missing exemption example: %r" % clause)

    def test_rule_zero_precedes_the_whole_catalogue(self):
        rule_zero, _ = section_span(self.body, RULE_ZERO)
        first_row = self.body.find("\n|-|-|\n")
        self.assertNotEqual(first_row, -1, "no catalogue table found")
        self.assertLess(rule_zero, first_row,
                        "rule zero must be read before any row is applied")

    def test_the_density_thresholds_are_stated_as_numbers(self):
        text = section(self.body, DENSITY)
        per_document = re.search(r"(\d+) or more surviving instances", text)
        per_thousand = re.search(r"(\d+) per thousand words", text)
        self.assertIsNotNone(per_document, "no per-pattern threshold")
        self.assertIsNotNone(per_thousand, "no per-document rate")
        self.assertGreater(int(per_document.group(1)), 1)
        self.assertGreater(int(per_thousand.group(1)), 0)


def thresholds():
    text = section(body(skill_text()), DENSITY)
    return (int(re.search(r"(\d+) or more surviving instances", text).group(1)),
            int(re.search(r"(\d+) per thousand words", text).group(1)))


class RegressionCorpusTest(unittest.TestCase):
    """Human technical prose that earlier versions of this skill damaged.

    The corpus is written for this suite in the register of the documents the
    skill names (a testing methodology page, a patch-submission guide). Every
    construction in it is one that broke an earlier version.
    """

    def setUp(self):
        self.body = body(skill_text())
        self.terms = catalogue_terms(self.body) | keep_terms(self.body)

    def hits(self, name):
        return scan(fixture(name), self.terms)

    def test_the_corpus_contains_the_constructions_it_exists_for(self):
        raw = "\n".join(fixture(n) for n in CORPUS)
        # Line wraps are part of the register these documents are written in, and
        # one of the constructions below (`a real possibility`) is only wrapped in
        # the corpus on purpose, so the comparison is made on flowed text.
        joined = re.sub(r"[ \t]*\n[ \t]*", " ", raw)
        for construction in ("test harness", "real name", "a real possibility",
                             "the entire filesystem", "robust against malicious attack",
                             "robust in normal use", "names a script",
                             "when it comes to"):
            self.assertIn(construction, joined,
                          "the corpus no longer exercises %r" % construction)
        self.assertIn("a real\npossibility", raw,
                      "keep one wrapped instance: a matcher that cannot cross a "
                      "line break misses it, and this is the case that proves it")
        self.assertNotIn("\nWhen it comes to", raw,
                         "the corpus must use it mid-sentence, which is the exempt "
                         "case, not as the opener the catalogue deletes")
        self.assertRegex(fixture("testing-methodology.rst"), r"(?m)^-{3,}$",
                         "the RST heading underline case is gone")

    def test_every_pattern_in_the_corpus_is_exempt_or_keep(self):
        """The point of the whole file. A term of art that hits a catalogue row
        and has no covering clause would be rewritten, which is the damage."""
        catalogue = catalogue_terms(self.body)
        keep = keep_terms(self.body)
        regions = {
            EXEMPT_REGION: section(self.body, EXEMPTION),
            KEEP_REGION: section(self.body, KEEP),
            CATALOGUE_REGION: self.body[self.body.find("\n|-|-|\n"):],
        }
        struck = set()
        for name in CORPUS:
            for term, line_no, matched, line in self.hits(name):
                self.assertIn(term, COVERAGE,
                              "%s:%d matches catalogue pattern %r (%r) and nothing "
                              "in SKILL.md exempts it:\n  %s"
                              % (name, line_no, term, matched, line.strip()))
                region, clause = COVERAGE[term]
                self.assertIn(flowed(clause), flowed(regions[region]),
                              "%s:%d relies on %r, whose covering clause is gone "
                              "from the %s section:\n  %s"
                              % (name, line_no, term, region, line.strip()))
                struck.add(term)
                if region is KEEP_REGION:
                    self.assertIn(term, keep, "%r is not a Keep pattern" % term)
                else:
                    self.assertIn(term, catalogue,
                                  "%r is exempted but no longer in the catalogue, so "
                                  "the exemption protects nothing" % term)
        self.assertEqual(set(COVERAGE) - struck, set(),
                         "COVERAGE lists patterns the corpus no longer contains; "
                         "the entry is dead and proves nothing")

    def test_the_exempted_patterns_would_otherwise_be_edited(self):
        """An exemption over a Keep row is a no-op. Each corpus pattern that is
        rescued by an exemption must carry rewrite or delete in the catalogue."""
        rows = catalogue_rows(self.body)
        for term, (region, _) in COVERAGE.items():
            if region is KEEP_REGION:
                continue
            leads = {re.match(r"[A-Za-z]+", fix).group(0)
                     for pattern, fix in rows if term in backticked(pattern)}
            self.assertTrue(leads, "%r is no longer a catalogue row" % term)
            self.assertEqual(leads - {"Rewrite", "Delete"}, set(),
                             "%r is already Keep, so its exemption is idle" % term)

    def test_density_alone_would_fire_on_the_testing_page(self):
        """Why the ordering test above is not bookkeeping. Without the exemption
        applied first, a term of art clears both documented thresholds."""
        per_pattern, per_thousand = thresholds()
        text = fixture("testing-methodology.rst")
        harness = scan(text, {"harness"})
        words = len(text.split())
        rate = 1000.0 * len(harness) / words
        self.assertGreaterEqual(len(harness), per_pattern,
                                "%d uses of a term of art, threshold %d"
                                % (len(harness), per_pattern))
        self.assertGreater(rate, per_thousand,
                           "%.1f per thousand words against a threshold of %d"
                           % (rate, per_thousand))

    def test_the_corpus_is_long_enough_to_measure(self):
        for name in CORPUS:
            self.assertGreater(len(fixture(name).split()), 250,
                               "%s is too short for a rate to mean anything" % name)


class RuleZeroTest(unittest.TestCase):
    """Named, quoted, and listed instances are never edited."""

    def setUp(self):
        self.body = body(skill_text())
        self.terms = catalogue_terms(self.body)
        self.text = fixture(RULE_ZERO_FIXTURE)

    def test_rule_zero_names_the_two_shapes_in_the_fixture(self):
        text = section(self.body, RULE_ZERO)
        for named in ("banned-word lists", "blockquotes", "quoted material",
                      "style guides", "`CONTRIBUTING.md`"):
            self.assertIn(named, text, "rule zero no longer covers %r" % named)
        self.assertIn("mentioned rather than used", text)

    def test_rule_zero_scopes_by_region_and_not_by_filename(self):
        """A cold reader took an earlier wording as a whole-file exemption keyed on
        a filename, which voided the audit of a contribution guide before any count
        and would exempt most of what this skill is pointed at."""
        text = flowed(section(self.body, RULE_ZERO))
        self.assertIn("Skip the region, not the file", text,
                      "rule zero reads as a whole-file exemption")
        self.assertIn("audited in its own prose", text)
        self.assertIn("void the audit before it started", text,
                      "the reason the filename reading is wrong is not recorded")

    def test_the_fixture_is_dense_with_tells(self):
        """It has to be, or the test below proves nothing."""
        per_pattern, _ = thresholds()
        hits = scan(self.text, self.terms)
        self.assertGreaterEqual(len(hits), 3 * per_pattern,
                                "only %d hits; rule zero is not under pressure" % len(hits))

    def test_every_hit_is_a_mention_rather_than_a_use(self):
        for term, line_no, matched, line in scan(self.text, self.terms):
            self.assertTrue(line.lstrip().startswith(("- ", "> ")),
                            "%s:%d has %r (%r) in the fixture's own voice, so this "
                            "fixture no longer tests rule zero:\n  %s"
                            % (RULE_ZERO_FIXTURE, line_no, term, matched, line))

    def test_the_fixture_holds_both_a_list_and_a_quotation(self):
        listed = [l for l in self.text.splitlines() if l.startswith("- ")]
        quoted = [l for l in self.text.splitlines() if l.startswith("> ")]
        self.assertGreaterEqual(len(listed), 8, "no banned-word list left")
        self.assertGreaterEqual(len(quoted), 2, "no quoted machine prose left")


class SelfAuditTest(unittest.TestCase):
    """The skill audited against its own catalogue."""

    def setUp(self):
        self.body = body(skill_text())
        self.terms = catalogue_terms(self.body)

    def test_the_scanner_does_not_fire_on_a_quoted_mention(self):
        """The false positive this checker has already produced once. `"It is
        worth noting that X" means X` is the document defining a pattern, not
        using it, and a checker that strips only backticks reports it."""
        line = 'Delete when the pattern carries no claim: '\
               '"It is worth noting that X" means X.\n'
        self.assertEqual(scan(prose_only(line), self.terms), [],
                         "the quoted mention was read as the author's own words")
        naive = re.sub(r"`[^`]*`", " ", line)
        self.assertTrue(scan(naive, self.terms),
                        "precondition: without the quote strip this line does hit")

    def test_the_scanner_strips_a_quotation_that_wraps_across_lines(self):
        """The skill quotes a discussion board across a line break. Stripping
        quotes line by line leaves the second half standing."""
        doc = ('A reconciling comment: "Most of these are valid and useful\n'
               'framing devices, used in moderation."\n')
        self.assertEqual(scan(prose_only(doc), self.terms), [])
        per_line = "\n".join(re.sub(r'"[^"]*"', " ", l) for l in doc.splitlines())
        self.assertTrue(scan(per_line, self.terms),
                        "precondition: a line-at-a-time strip does miss the wrap")

    def test_the_scanner_still_catches_a_bare_tell(self):
        """Otherwise the two tests above would pass on a scanner that finds
        nothing at all."""
        doc = "At the end of the day the parser is seamless and robust.\n"
        found = {term for term, _, _, _ in scan(prose_only(doc), self.terms)}
        self.assertEqual(found, {"at the end of the day", "seamless", "robust"})

    def test_the_skill_commits_none_of_its_own_tells(self):
        unexpected = []
        for term, line_no, matched, line in scan(prose_only(self.body), self.terms):
            if any(quote in line for quote in SELF_EXEMPT):
                continue
            unexpected.append("line %d: %r in %r" % (line_no, matched, line.strip()))
        self.assertEqual(unexpected, [],
                         "SKILL.md uses patterns it tells other documents to fix:\n"
                         + "\n".join(unexpected))

    def test_the_self_exemptions_are_still_real_lines_of_the_file(self):
        """An allowlist that stops matching anything has become a blanket."""
        for quote in SELF_EXEMPT:
            self.assertIn(quote, self.body,
                          "%r is no longer in SKILL.md; drop the exemption" % quote)
        per_pattern, _ = thresholds()
        self.assertLessEqual(
            len(SELF_EXEMPT), per_pattern + 1,
            "the literal-use allowlist has grown past the skill's own density "
            "threshold, which is the point at which the skill says to edit")

    def test_no_em_dashes_anywhere(self):
        for path in sorted(SKILL_DIR.rglob("*")) + sorted(FIXTURES.rglob("*")) \
                + [Path(__file__)]:
            if path.is_file():
                self.assertNotIn(EM_DASH.encode(), path.read_bytes(),
                                 "em dash in %s" % path)

    def test_the_skill_directory_ships_no_build_artifacts(self):
        """The directory is symlinked whole into the user's config, so anything
        left in it ships. A stray `__pycache__` also broke the sweep above."""
        stray = [p for p in SKILL_DIR.rglob("*")
                 if p.name == "__pycache__" or p.suffix in (".pyc", ".pyo")]
        self.assertEqual(stray, [], "build artifacts in the skill directory: %s"
                         % [str(p) for p in stray])


class TriggerPrecisionTest(unittest.TestCase):

    def setUp(self):
        self.text = skill_text()
        self.body = body(self.text)

    def prompts(self, marker):
        tail = self.body.split(marker, 1)
        self.assertEqual(len(tail), 2, "no %r block in SKILL.md" % marker)
        block = re.split(r"\n(?:Must|## )", tail[1], 1)[0]
        return re.findall(r'^\d+\. "(.+?)"', block, re.M)

    def genre_words(self):
        """The genres named in the description's own parenthetical."""
        description = re.search(r'^description: "(.*)"$', self.text, re.M).group(1)
        listed = re.search(r"\((a README.*?)\)", description).group(1)
        words = []
        for item in listed.split(","):
            item = re.sub(r"^\s*(a|an|the)\s+", "", item.strip())
            words.append(item.split()[0].lower().strip(".,"))
        return words

    def test_the_section_exists(self):
        self.assertIn("\n## Trigger precision\n", self.body)

    def test_three_must_fire_prompts(self):
        self.assertEqual(len(self.prompts("Must fire:")), 3, self.prompts("Must fire:"))

    def test_three_must_not_fire_prompts(self):
        self.assertEqual(len(self.prompts("Must NOT fire:")), 3,
                         self.prompts("Must NOT fire:"))

    def test_the_two_sets_are_disjoint(self):
        self.assertEqual(set(self.prompts("Must fire:"))
                         & set(self.prompts("Must NOT fire:")), set())

    def test_the_description_lists_the_genres_it_fires_on(self):
        words = self.genre_words()
        self.assertGreaterEqual(len(words), 6, words)
        self.assertIn("readme", words)

    def test_the_ambiguous_class_is_documented_and_resolved(self):
        """The genres and the copy-editing exclusion overlap: "fix the typos in
        the README" matches both halves of the description. The earlier version of
        this test forbade any must-NOT prompt from carrying a genre word, which
        structurally prevented the file from documenting that collision at all.

        The rule is now stronger, not weaker. At most one must-NOT prompt may sit
        in the overlap, and only when the file states which clause wins; the rest
        must still be unambiguous. A precedence rule with no worked collision is
        untested, and a collision with no precedence rule is a coin flip.
        """
        vocabulary = self.genre_words()
        overlapping = [p for p in self.prompts("Must NOT fire:")
                       if any(re.search(r"(?<![\w-])%s(?![\w-])" % w, p.lower())
                              for w in vocabulary)]
        self.assertLessEqual(len(overlapping), 1,
                             "more than one must-NOT prompt sits in the overlap, so "
                             "the negative set no longer shows the unambiguous cases: "
                             "%r" % overlapping)
        fires = section(self.body, "## When this fires")
        self.assertIn("Precedence: the request decides, not the file", fires,
                      "no precedence rule, so the two halves of the trigger tie")
        if overlapping:
            self.assertIn("copy-editing", flowed(fires),
                          "the precedence rule does not say which clause wins")
            self.assertIn("ask", flowed(fires),
                          "no instruction for the case that stays unclear")
        else:
            self.fail("the must-NOT set no longer exercises the overlap, so the "
                      "precedence rule above is untested")

    def test_the_must_fire_prompts_do_carry_it(self):
        vocabulary = self.genre_words()
        carrying = [p for p in self.prompts("Must fire:")
                    if any(re.search(r"(?<![\w-])%s(?![\w-])" % w, p.lower())
                           for w in vocabulary)]
        self.assertGreaterEqual(len(carrying), 2,
                                "the must-fire prompts share no vocabulary with the "
                                "description: %r" % self.prompts("Must fire:"))


class AuthorshipTest(unittest.TestCase):
    """The one claim this skill must never make.

    A catalogue of tells is one short step from a detector, and detectors of this
    kind are pseudoscience with a known victim list. The disclaimer is not
    decoration: it is the clause that keeps the file on the author's own side of
    the desk, so it is pinned rather than left to survive edits by luck.
    """

    def setUp(self):
        self.section = section(body(skill_text()), AUTHORSHIP)

    def test_the_section_survives(self):
        for clause in ("Nothing here measures authorship",
                       "never to assess who wrote something",
                       "never as input to a grade or a moderation decision"):
            self.assertIn(clause, flowed(self.section),
                          "the authorship disclaimer lost %r" % clause)

    def test_it_names_the_population_that_gets_hurt(self):
        self.assertIn("ESL", self.section)


class StructuralFamilyTest(unittest.TestCase):
    """The families a word-level table cannot hold.

    The lexical catalogue passed a document two independent readers then found
    forty tells in, because every one of those tells was a property of sentence
    or paragraph construction rather than of a word. Each family here therefore
    has to carry a recognition test a reader can actually run, which is why the
    test below insists the recognition line be a question: a description of a
    pattern is not a procedure for finding one.
    """

    # Every construction the two reviews reported, by the name this file gives it.
    REPORTED = (
        "Negation-then-correction",
        "Comparative aphorism",
        "Rule of three",
        "Sentence-final restatement",
        "Grand summary pivot",
        "Question as heading",
        "Knowing aside",
        "Self-certifying candour",
        "Repeated signature phrase",
        "Unsourced precision",
    )

    def setUp(self):
        self.body = body(skill_text())
        self.section = section(self.body, STRUCTURAL)

    def families(self):
        """{name: block} for every `### ` block in the structural section."""
        parts = re.split(r"^### (.+)$", self.section, flags=re.M)[1:]
        return dict(zip(parts[0::2], parts[1::2]))

    def test_the_section_exists_and_parsed(self):
        self.assertGreaterEqual(len(self.families()), len(self.REPORTED),
                                "only %d families parsed" % len(self.families()))

    def test_every_construction_the_reviewers_found_has_a_family(self):
        names = " | ".join(self.families())
        for reported in self.REPORTED:
            self.assertIn(reported, names,
                          "no family covers %r, which both reviews reported"
                          % reported)

    def test_every_family_carries_all_four_parts(self):
        for name, block in self.families().items():
            for label in ("**Recognition test.**", "**Disposition.**",
                          "**Before.**", "**After.**"):
                self.assertIn(label, block, "family %r is missing %s" % (name, label))

    def test_every_recognition_test_is_a_question_a_reader_can_run(self):
        """A structural pattern cannot be grepped, so the recognition test IS the
        implementation. A family that only describes itself is unactionable."""
        for name, block in self.families().items():
            line = flowed(re.search(r"\*\*Recognition test\.\*\*(.+?)\n\*\*",
                                    block, re.S).group(1))
            self.assertIn("?", line,
                          "family %r describes itself instead of asking the reader "
                          "something they can answer: %r" % (name, line.strip()))
            self.assertGreater(len(line.split()), 8,
                               "family %r has a recognition test too short to apply"
                               % name)

    def test_every_family_leads_with_exactly_one_disposition(self):
        vocabulary = re.findall(r"^\*\*([A-Z][a-z]+)\*\*",
                                section(self.body, DISPOSITIONS), re.M)
        self.assertEqual(vocabulary, ["Rewrite", "Delete", "Keep"])
        verb = re.compile(r"(?<![\w-])(%s)(?![\w-])" % "|".join(vocabulary))
        for name, block in self.families().items():
            text = re.search(r"\*\*Disposition\.\*\*\s*(.+)", block).group(1)
            self.assertIsNotNone(verb.match(text),
                                 "family %r does not lead with a disposition: %r"
                                 % (name, text))
            first = re.split(r"(?<=[.?!])\s", text)[0]
            self.assertEqual(len(verb.findall(first)), 1,
                             "family %r gives two dispositions in one breath: %r"
                             % (name, first))

    def test_every_family_shows_a_repair_that_changes_something(self):
        for name, block in self.families().items():
            before = backticked(re.search(r"\*\*Before\.\*\*(.+?)\n\*\*After",
                                          block, re.S).group(1))
            after = backticked(re.search(r"\*\*After\.\*\*(.+)", block, re.S).group(1))
            self.assertTrue(before, "family %r has no worked before" % name)
            self.assertTrue(after, "family %r has no worked after" % name)
            self.assertNotEqual(before[0].strip(), after[0].strip(),
                                "family %r shows the same text twice" % name)

    def test_the_worked_examples_are_quoted_so_rule_zero_covers_them(self):
        """A before/after pair is a mention. Left bare it would be a use, and the
        file's own self-audit would report it."""
        for name, block in self.families().items():
            pair = block[block.find("**Before.**"):]
            bare = prose_only(pair)
            self.assertEqual(" ".join(bare.replace("*", "").replace(".", "").split()),
                             "Before After",
                             "family %r has worked-example text outside backticks, "
                             "so it reads as the file's own voice" % name)


class StructuralDensityTest(unittest.TestCase):
    """Antithesis and the rule of three are ordinary technical prose in ones and
    twos. The finding is the rate, so the rule has to be a rate, and the rate has
    to be justified against something measured rather than picked.
    """

    def setUp(self):
        self.section = section(body(skill_text()), STRUCTURAL)

    def numbers(self):
        floor = re.search(r"(\d+) or more surviving instances of one family",
                          self.section)
        rate = re.search(r"(\d+) or more per thousand words", self.section)
        self.assertIsNotNone(floor, "no per-family floor")
        self.assertIsNotNone(rate, "no per-family rate")
        return int(floor.group(1)), int(rate.group(1))

    def test_the_rule_has_both_a_floor_and_a_rate(self):
        """Either alone is wrong. A rate alone fires on a 200-word note with one
        antithesis; a count alone fires on a long document that is not dense."""
        floor, rate = self.numbers()
        self.assertGreaterEqual(floor, 4, "a floor of %d is not a pile-up" % floor)
        self.assertGreaterEqual(rate, 1)
        self.assertIn("Both figures", flowed(self.section),
                      "the rule must say the two figures are joint, not either/or")

    def test_the_rate_is_justified_against_a_measurement(self):
        text = flowed(self.section)
        for evidence in ("21,024 editable words", "0.0 per thousand"):
            self.assertIn(evidence, text,
                          "the structural rate cites no measurement: missing %r"
                          % evidence)

    def test_the_measured_human_baseline_sits_under_the_threshold(self):
        """The number is only defensible if the human corpus clears it."""
        _, rate = self.numbers()
        measured = float(re.search(r"surviving instances?: ([\d.]+) per thousand",
                                   flowed(self.section)).group(1))
        self.assertLess(measured, rate,
                        "the threshold %d is at or under the measured human rate "
                        "%.2f, so human prose would fire" % (rate, measured))

    def test_the_threshold_stays_consistent_with_the_file_own_worked_verdict(self):
        """Raising the rate to 9 survived every test: nothing asserted that a
        threshold must still let anything through. The file states that one family
        fires on a named document at a named rate, so a threshold above that rate
        contradicts the file, and a floor above that count does too."""
        floor, rate = self.numbers()
        text = flowed(self.section)
        m = re.search(r"fires at (\d+) instances and ([\d.]+) per thousand", text)
        self.assertIsNotNone(m, "the file states no worked verdict to check against")
        surviving, stated = int(m.group(1)), float(m.group(2))
        self.assertLessEqual(
            rate, stated,
            "the rate is %d per thousand but the file says a family fires on its "
            "worked document at %.1f, so nothing would fire" % (rate, stated))
        self.assertLessEqual(
            floor, surviving,
            "the floor is %d but the file's own worked verdict counts %d surviving"
            % (floor, surviving))

    def test_the_human_corpus_figures_are_internally_consistent(self):
        """Inflating the corpus match count survived every test."""
        text = flowed(self.section)
        candidates = int(re.search(r"reports \*\*(\d+)\s*candidate matches", text).group(1))
        surviving = int(re.search(r"\*\*(\d+) surviving instances", text).group(1))
        words = int(re.search(r"\*\*([\d,]+) editable words\*\*",
                              text).group(1).replace(",", ""))
        explained = int(re.search(r"(?:^|\W)(\w+) are instructional contrasts",
                                  text).group(1).replace("Fifteen", "15"))
        self.assertLessEqual(surviving, candidates)
        self.assertEqual(candidates, explained + 1,
                         "%d candidates but only %d are accounted for" %
                         (candidates, explained))
        self.assertEqual(
            float(re.search(r"\*\*\d+ surviving instances: ([\d.]+) per thousand",
                            text).group(1)),
            round(1000.0 * surviving / words, 1),
            "the stated human rate is not surviving instances over editable words")

    def test_the_shortlist_is_not_sold_as_a_detector(self):
        self.assertIn("shortlist", flowed(self.section).lower())
        self.assertIn("not a detector", flowed(self.section).lower())


class CatalogueCurrencyTest(unittest.TestCase):
    """The catalogue is a snapshot of three moving sources.

    Before this section the file said only to fetch the source again, which is a
    wish rather than a procedure: it named no command, no comparison, no place to
    write the answer down, and no way for a reader to tell that the file was
    already out of date.
    """

    ISO = r"(\d{4})-(\d{2})-(\d{2})"

    def setUp(self):
        self.body = body(skill_text())
        self.pointer = section(self.body, CURRENCY)
        self.section = (SKILL_DIR / "sources" / "REFRESH.md").read_text()

    def test_skill_md_still_points_at_the_moved_procedure(self):
        """Moving it out must not lose it. The pointer carries the filename and
        the reason it is not inline: it fires on a date, not on a publish."""
        self.assertIn("sources/REFRESH.md", self.pointer)
        self.assertIn("fails closed", flowed(self.pointer))

    def test_the_pull_is_guarded_against_an_unreachable_source(self):
        """Measured: `curl -s <unreachable> | jq -r ...` prints nothing and exits
        0, and the empty list against the snapshot reports all 120 ids as removed
        upstream. The guard is the difference between a stopped pass and an
        emptied catalogue."""
        text = flowed(self.section)
        self.assertIn("curl -fsS", text, "the pull is not guarded")
        self.assertIn("jq -e", text, "the payload shape is not checked")
        self.assertIn("Stop and change nothing", text)
        self.assertIn("0 ids pulled, 120 reported removed", text,
                      "the failure this guards is not recorded")

    def test_a_changed_payload_shape_stops_rather_than_improvises(self):
        self.assertIn("If `.terms[].id` is gone", flowed(self.section))
        self.assertIn("diff nothing on this pass", flowed(self.section))

    def banner(self):
        m = re.search(r"\*\*Catalogue reviewed %s\. Due for review %s\.\*\*"
                      % (self.ISO, self.ISO), self.body)
        self.assertIsNotNone(m, "no currency banner in SKILL.md")
        return m

    def dates(self):
        import datetime
        g = [int(x) for x in self.banner().groups()]
        return (datetime.date(*g[:3]), datetime.date(*g[3:]))

    def test_the_banner_is_the_first_thing_under_the_title(self):
        """Staleness a reader has to go looking for is staleness nobody sees."""
        first_section = self.body.find("\n## ")
        self.assertLess(self.banner().start(), first_section,
                        "the currency banner is buried below a section heading")

    def test_the_review_date_is_in_the_future_of_the_pull(self):
        reviewed, due = self.dates()
        self.assertGreater(due, reviewed)

    def test_the_interval_matches_the_one_the_file_states(self):
        reviewed, due = self.dates()
        self.assertIn("six months", flowed(self.section),
                      "the file states no review interval")
        self.assertTrue(150 <= (due - reviewed).days <= 200,
                        "banner spans %d days but the file says six months"
                        % (due - reviewed).days)

    def test_the_banner_says_what_an_overdue_reader_does(self):
        self.assertIn("Past that date", flowed(self.body))

    def test_every_source_is_named_with_a_url_a_date_and_a_version_stamp(self):
        rows = [cells(l) for t in tables(self.section) for l in t[2:]
                if not set(l) <= set("|-")]
        self.assertGreaterEqual(len(rows), 3,
                                "fewer than three sources recorded: %r" % rows)
        for row in rows:
            self.assertEqual(len(row), 3, "source row %r is not name/pulled/stamp" % row)
            self.assertRegex(row[1], self.ISO, "source %r has no pull date" % row[0])
            self.assertTrue(row[2].strip(), "source %r has no version stamp" % row[0])
        joined = " ".join(" ".join(r) for r in rows)
        for url in ("claudisms.ai", "Signs of AI writing", "hn.algolia.com"):
            self.assertIn(url, joined, "source %r is not recorded" % url)

    def test_the_procedure_gives_a_command_rather_than_an_intention(self):
        text = flowed(self.section)
        self.assertIn("jq -r '.updated, .count'", text,
                      "no runnable check against the source's own version stamp")
        self.assertIn(".terms[].id", text, "no way to diff term by term")

    def test_the_procedure_covers_both_directions_of_drift(self):
        text = flowed(self.section)
        self.assertIn("Fading, not deleted", text,
                      "no rule for a pattern that has gone stale")
        self.assertIn("newly common", text,
                      "no rule for a pattern that is newly common")

    def test_a_retired_pattern_is_archived_rather_than_dropped(self):
        """Repo constraint: nothing is ever destructively removed. A deleted row
        loses the record that the pattern was ever considered."""
        self.assertIn("Fading", self.section)
        self.assertRegex(self.section,
                         r"(?s)Fading, not deleted.*%s" % self.ISO,
                         "a demoted pattern carries no date")

    def test_the_recorded_id_list_exists_and_matches_the_recorded_count(self):
        """The diff step is only runnable if the previous pull is on disk. A
        procedure that says `diff against the last pull` with no last pull is the
        same wish this section replaced."""
        m = re.search(r"`(claudisms-ids-\d{4}-\d{2}-\d{2}\.txt)`", self.section)
        self.assertIsNotNone(m, "the diff step names no stored id list")
        snapshot = SKILL_DIR / "sources" / m.group(1)
        self.assertTrue(snapshot.exists(), "%s is named but absent" % m.group(1))
        ids = [l for l in snapshot.read_text().splitlines() if l.strip()]
        self.assertEqual(len(ids), len(set(ids)), "duplicate ids in the snapshot")
        stamp = int(re.search(r"`count` (\d+)", self.section).group(1))
        self.assertEqual(len(ids), stamp,
                         "the snapshot holds %d ids but the recorded stamp says %d"
                         % (len(ids), stamp))
        self.assertEqual(sorted(ids), ids, "the snapshot is not sorted, so a diff "
                                           "against a sorted pull is all noise")

    def test_the_source_that_was_already_here_is_still_credited(self):
        self.assertIn("https://claudisms.ai", self.section)
        self.assertIn("CC0", flowed(self.section))



class MutationGuardTest(unittest.TestCase):
    """Mutations that survived an earlier version of this suite.

    Each test below corresponds to one edit that broke the skill and left all
    tests green. They are grouped so the reason each exists stays attached to it.
    """

    # A fast-path row and the fuller row it summarises. Two of the four cannot be
    # matched by substring, which is why the pairing is written down.
    FAST_PATH_PROSE = {
        "One-sentence paragraphs throughout": "four short declaratives in a row",
        "A rhetorical question you then answer": "or a rhetorical question you then answer",
        "A bolded lead-in on every bullet": "A bolded term plus a colon plus an explanation",
        "A trailing engagement question": "or a question to the reader",
    }

    # Family -> a string that must be in its Before and must NOT be in its After.
    # Swapping the pair was previously invisible: only inequality was asserted.
    DIRECTION = {
        "Negation-then-correction": ", not on guesswork",
        "Comparative aphorism": "is worse than",
        "Rule of three": "reliable, and",
        "Sentence-final restatement": "so an acknowledgement",
        "Grand summary pivot": "comes down to one idea",
        "Question as heading": "Why does any of this",
        "Knowing aside": "(inevitably)",
        "Self-certifying candour": "To be completely transparent",
        "Repeated signature phrase": "same jobs going quiet on the wire",
        "Unsourced precision": "roughly",
    }

    HOSTS = {"claudisms.ai", "en.wikipedia.org", "hn.algolia.com"}

    def setUp(self):
        self.body = body(skill_text())
        self.rows = catalogue_rows(self.body)

    def lead(self, fix):
        return re.match(r"[A-Za-z]+", fix).group(0)

    def test_a_prose_fast_path_row_cannot_contradict_the_row_it_summarises(self):
        """CrossTableConsistencyTest compares backticked terms only, so flipping
        the disposition on a row written as prose was invisible. Nine rows in this
        file carry no backticked term."""
        by_pattern = {}
        for pattern, fix in self.rows:
            by_pattern.setdefault(pattern, self.lead(fix))
        for summary, full in self.FAST_PATH_PROSE.items():
            self.assertIn(summary, by_pattern,
                          "the fast path no longer carries %r" % summary)
            matches = [(p, self.lead(f)) for p, f in self.rows if full in p]
            self.assertTrue(matches, "no catalogue row contains %r any more" % full)
            for pattern, verb in matches:
                self.assertEqual(
                    by_pattern[summary], verb,
                    "the fast path says %s for %r but the catalogue says %s for %r; "
                    "a hurried reader never reaches the second one"
                    % (by_pattern[summary], summary, verb, pattern))

    def test_no_catalogue_table_can_be_deleted_unnoticed(self):
        """A floor of 40 rows against 60 shipped means a whole table could go."""
        subsections = re.findall(r"^### (.+)$", self.body, re.M)
        tabled = [h for h in subsections
                  if catalogue_rows(section(self.body, "### " + h))]
        self.assertGreaterEqual(len(tabled), 8,
                                "only %d catalogue tables left: %r" % (len(tabled), tabled))
        for heading in tabled:
            rows = catalogue_rows(section(self.body, "### " + heading))
            self.assertGreaterEqual(len(rows), 3,
                                    "table %r is down to %d rows" % (heading, len(rows)))

    def test_a_familys_before_and_after_cannot_be_swapped(self):
        families = dict(zip(*[iter(re.split(r"^### (.+)$",
                                            section(self.body, STRUCTURAL),
                                            flags=re.M)[1:])] * 2))
        for name, marker in self.DIRECTION.items():
            self.assertIn(name, families, "family %r is gone" % name)
            block = families[name]
            before = re.search(r"\*\*Before\.\*\*(.+?)\n\*\*After", block, re.S).group(1)
            after = re.search(r"\*\*After\.\*\*(.+)", block, re.S).group(1)
            self.assertIn(marker, flowed(before),
                          "%r no longer demonstrates the construction it flags" % name)
            self.assertNotIn(marker, flowed(after),
                             "%r shows the construction in its AFTER, so the pair is "
                             "swapped or the repair does not repair" % name)

    def test_no_after_invents_a_fact_the_before_did_not_carry(self):
        """The harm this skill exists to prevent, once committed in its own
        examples: `(inevitably) be wrong for your workload` was repaired into an
        invented worker count and an invented throughput figure, a rewrite that
        changes what the sentence claims and trips the file's own Unsourced
        precision family. A marker string being absent does not catch that."""
        families = dict(zip(*[iter(re.split(r"^### (.+)$",
                                            section(self.body, STRUCTURAL),
                                            flags=re.M)[1:])] * 2))
        invented = re.compile(r"\d+|[\w-]+\.(?:py|sh|md|txt|json)\b|/")
        for name, block in families.items():
            before = re.search(r"\*\*Before\.\*\*(.+?)\n\*\*After", block, re.S).group(1)
            after = re.search(r"\*\*After\.\*\*(.+)", block, re.S).group(1)
            for token in set(invented.findall(flowed(after))):
                self.assertIn(token, flowed(before),
                              "the AFTER for %r introduces %r, which the BEFORE does "
                              "not carry: a rewrite that adds a fact is a fabrication"
                              % (name, token))

    def test_the_file_forbids_an_after_that_invents_a_fact(self):
        text = flowed(section(self.body, STRUCTURAL))
        self.assertIn("No After invents a fact", text)
        self.assertIn("the disposition is keep, not rewrite", text,
                      "no instruction for the case where the plain version needs a "
                      "fact the author does not have")

    def test_the_stated_measurements_are_reproducible_from_this_repository(self):
        """Changing `16 shortlist matches` to 1600 survived every test. The README
        figures are recomputed here from the shipped script; the human-corpus
        figures cannot be, and the file has to say so rather than imply otherwise."""
        text = flowed(section(self.body, STRUCTURAL))
        readme = REPO / "README.md"
        if not readme.is_file():
            self.skipTest("no README.md to measure")
        import subprocess
        out = subprocess.run(
            [sys.executable, str(SKILL_DIR / "shortlist.py"), str(readme)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, check=True).stdout
        words = int(re.search(r"(\d+) editable words", out).group(1))
        matches = int(re.search(r"(\d+) shortlist matches", out).group(1))
        stated_words = int(re.search(r"has \*\*(\d+) editable words\*\*", text).group(1))
        stated_matches = int(re.search(r"the same \*\*(\d+)\s*candidate\s*matches\*\*",
                                       text).group(1))
        self.assertEqual(stated_words, words,
                         "the file states %d editable words for the README; the "
                         "shipped script says %d" % (stated_words, words))
        self.assertEqual(stated_matches, matches,
                         "the file states %d candidate matches for the README; the "
                         "shipped script says %d" % (stated_matches, matches))
        surviving = int(re.search(r"fires at (\d+) instances", text).group(1))
        words = stated_words
        self.assertLessEqual(surviving, matches)
        self.assertEqual(
            float(re.search(r"instances and ([\d.]+) per thousand", text).group(1)),
            round(1000.0 * surviving / words, 1),
            "the stated README rate is not surviving instances over editable words")
        self.assertIn("not stated here", text,
                      "the file states a document-wide verdict for a document whose "
                      "paragraph read no command reproduces")
        self.assertIn("no command here reproduces them", flowed(self.body),
                      "figures from documents outside this repository are presented "
                      "as if a reader could check them")

    def test_every_url_points_at_a_source_this_file_actually_names(self):
        """Repointing the pull at example.invalid survived every test."""
        text = skill_text() + (SKILL_DIR / "sources" / "REFRESH.md").read_text()
        hosts = set(re.findall(r"https?://([^/\s`\)\]]+)", text))
        self.assertTrue(hosts, "no URLs at all")
        self.assertEqual(hosts - self.HOSTS, set(),
                         "unrecognised source hosts: %s" % (hosts - self.HOSTS))

    def test_when_this_fires_still_says_when_it_fires(self):
        """Replacing the section with `Use judgement.` survived every test."""
        fires = flowed(section(self.body, "## When this fires"))
        for clause in ("chat replies", "code comments", "scratch notes",
                       "one-line commit subjects", "copy-editing",
                       "Precedence: the request decides, not the file"):
            self.assertIn(clause, fires, "`When this fires` lost %r" % clause)
        self.assertGreater(len(fires.split()), 120,
                           "`When this fires` has been reduced to a slogan")
        self.assertRegex(fires, r"Two edge calls",
                         "the worked edge cases are gone, so only the slogan is left")



class ProcedureTest(unittest.TestCase):
    """Both cold reviewers reported the same gap: no step 1.

    A catalogue plus scattered rules leaves the sequence to be invented, and two
    sessions invent two. The ordering here is load bearing in one specific way:
    the exemption is applied to each match BEFORE anything is counted.
    """

    HEADING = "## The pass, in order"

    def setUp(self):
        self.body = body(skill_text())
        self.section = section(self.body, self.HEADING)

    def steps(self):
        return re.findall(r"^(\d+)\. \*\*(.+?)\*\*", self.section, re.M)

    def test_the_procedure_is_numbered_and_ordered(self):
        numbers = [int(n) for n, _ in self.steps()]
        self.assertGreaterEqual(len(numbers), 6, "only %d steps" % len(numbers))
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)),
                         "the steps are not consecutively numbered: %r" % numbers)

    def test_it_runs_before_the_catalogue(self):
        procedure, _ = section_span(self.body, self.HEADING)
        self.assertLess(procedure, self.body.find("\n|-|-|\n"),
                        "the sequence sits after the rows it sequences")

    def test_the_exemption_is_applied_before_anything_is_counted(self):
        titles = [t for _, t in self.steps()]
        joined = " | ".join(titles).lower()
        exempt = next(i for i, t in enumerate(titles) if "exemption" in t.lower())
        count = next(i for i, t in enumerate(titles) if "what survives" in t.lower())
        self.assertLess(exempt, count,
                        "counting is ordered before the exemption: %s" % joined)

    def test_it_states_an_output_contract(self):
        text = flowed(self.section)
        self.assertIn("Output contract", text)
        for element in ("editable word count", "count and its rate",
                        "before and an\nafter".replace("\n", " "),
                        "left alone and why"):
            self.assertIn(element, text, "the output contract omits %r" % element)

    def test_it_says_whether_the_session_edits_or_proposes(self):
        text = flowed(self.section)
        self.assertIn("Edit in place", text)
        self.assertIn("ask before", text,
                      "no instruction for a request that says neither")


class WorkedExampleProvenanceTest(unittest.TestCase):
    """The families were validated against one README, and an earlier version of
    this file took its worked examples out of that same README. A skill whose
    examples are the answers to its own test case demonstrates nothing about a
    document it has not seen. This keeps them apart mechanically.
    """

    def setUp(self):
        self.section = section(body(skill_text()), STRUCTURAL)

    def examples(self):
        out = []
        for label in ("Before", "After"):
            for m in re.finditer(r"\*\*%s\.\*\*\s*`([^`]+)`" % label, self.section):
                out.append(" ".join(m.group(1).split()))
        return out

    def test_the_examples_parsed(self):
        self.assertGreaterEqual(len(self.examples()), 20,
                                "only %d worked examples" % len(self.examples()))

    def test_no_worked_example_comes_from_the_document_the_skill_was_tested_on(self):
        readme = REPO / "README.md"
        if not readme.is_file():
            self.skipTest("no README.md to compare against")
        prose = " ".join(readme.read_text().split())
        for example in self.examples():
            for fragment in [example, example.rstrip(".")]:
                self.assertNotIn(fragment, prose,
                                 "worked example %r is lifted verbatim from the "
                                 "document this skill was validated against" % example)


class ShortlistScriptTest(unittest.TestCase):
    """The script the counting rules delegate to. Real files, real subprocess."""

    SCRIPT = SKILL_DIR / "shortlist.py"

    def run_on(self, text, *args):
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write(text)
            path = fh.name
        try:
            return subprocess.run([sys.executable, str(self.SCRIPT), path] + list(args),
                                  capture_output=True, text=True,
                                  stdin=subprocess.DEVNULL, check=True).stdout
        finally:
            os.unlink(path)

    def test_the_script_ships(self):
        self.assertTrue(self.SCRIPT.is_file(), "shortlist.py is gone")

    def test_it_finds_a_match_that_wraps_across_a_line_break(self):
        """The documented reason it exists. This repository hard wraps, so the
        line-based grep in an earlier version could not see this at all."""
        doc = "A skill that got used again is worth\nmore than a proposal.\n"
        out = self.run_on(doc)
        self.assertIn("comparative", out,
                      "the wrapped match was missed, which is the bug this "
                      "script exists to fix:\n%s" % out)
        self.assertNotIn("is worth more than", doc,
                         "precondition: the phrase must be split in the source")

    def test_a_candidate_never_matches_across_a_paragraph_break(self):
        """The other half of what the unwrap buys. Matching with `\\s+` over raw
        text would join two unrelated paragraphs into one false candidate."""
        doc = "the run ends here, not\n\nstarting a new paragraph.\n"
        out = self.run_on(doc)
        self.assertIn("0 shortlist matches", out,
                      "a match was reported across a blank line:\n%s" % out)
        joined = doc.replace("\n\n", " ")
        self.assertIn("1 shortlist matches", self.run_on(joined),
                      "precondition: the same words in one paragraph do match")

    def test_it_reports_the_line_the_match_starts_on(self):
        doc = "filler\n\nsecond para\n\nWorkers run on depth, not on guesswork.\n"
        self.assertIn("L5", self.run_on(doc))

    def test_markup_is_excluded_from_the_denominator(self):
        prose = "one two three four five six seven eight nine ten\n"
        fenced = prose + "\n```\n" + " ".join(["code"] * 50) + "\n```\n"
        bare = int(re.search(r"(\d+) editable", self.run_on(prose)).group(1))
        with_code = int(re.search(r"(\d+) editable", self.run_on(fenced)).group(1))
        self.assertEqual(bare, with_code,
                         "a fenced block moved the denominator from %d to %d"
                         % (bare, with_code))

    def test_a_table_row_and_a_url_are_excluded(self):
        prose = "one two three four five\n"
        noisy = prose + "|`a`|b c d e f g h|\nhttps://example.com/a/b/c\n"
        self.assertEqual(int(re.search(r"(\d+) editable", self.run_on(prose)).group(1)),
                         int(re.search(r"(\d+) editable", self.run_on(noisy)).group(1)))

    def test_rows_mode_works_through_a_symlinked_install(self):
        """The installer symlinks the whole skill directory into the user's
        config, so `--rows` finds SKILL.md relative to the symlink, not the
        checkout. A real symlink, because that is the shape it ships in."""
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "ai-tell-audit"
            link.symlink_to(SKILL_DIR, target_is_directory=True)
            out = subprocess.run(
                [sys.executable, str(link / "shortlist.py"), "--rows",
                 str(SKILL_DIR / "SKILL.md")],
                capture_output=True, text=True, stdin=subprocess.DEVNULL)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("row matches across", out.stdout,
                          "--rows cannot find SKILL.md from the installed path")

    def test_skip_ranges_leave_the_denominator_smaller(self):
        """Step 2 says to mark the rule-zero regions before counting. Without the
        flag that step changes nothing and a banned-word list lands in the
        denominator the same file says must exclude it."""
        doc = "alpha beta gamma delta epsilon\n- banned\n- words\n- here\nzeta eta theta\n"
        full = int(re.search(r"(\d+) editable", self.run_on(doc)).group(1))
        cut = int(re.search(r"(\d+) editable",
                            self.run_on(doc, "--skip=2-4")).group(1))
        self.assertLess(cut, full, "--skip did not change the denominator")
        self.assertEqual(full - cut, 6, "skipped 3 list lines should drop 6 tokens")

    def test_the_script_and_this_suite_count_the_same_rows(self):
        """Two implementations of one rule drift, and the shipped one is what a
        reader runs while this suite guards the other. They are pinned to each
        other on the fixture built for exactly these patterns."""
        import subprocess
        fixture = FIXTURES / "testing-methodology.rst"
        out = subprocess.run(
            [sys.executable, str(self.SCRIPT), "--rows", str(fixture)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            check=True).stdout
        script_counts = {}
        for line in out.splitlines():
            m = re.match(r"^  (.+?)\s\s+(\d+)\s+L", line)
            if m:
                script_counts[m.group(1).strip()] = int(m.group(2))
        terms = catalogue_terms(body(skill_text()))
        suite_counts = {}
        for term, _, _, _ in scan(fixture.read_text(), terms):
            suite_counts[term] = suite_counts.get(term, 0) + 1
        self.assertTrue(script_counts, "the script reported no rows:\n%s" % out)
        shared = set(script_counts) & set(suite_counts)
        self.assertGreaterEqual(len(shared), 3,
                                "the two scanners share almost nothing: %r vs %r"
                                % (sorted(script_counts), sorted(suite_counts)))
        for term in sorted(shared):
            self.assertEqual(
                script_counts[term], suite_counts[term],
                "the shipped script counts %r %d times and this suite counts it %d; "
                "the reader and the guard disagree"
                % (term, script_counts[term], suite_counts[term]))

    def test_the_script_docstring_agrees_with_the_skill(self):
        """A cold reader found the script claiming 21,926 words where SKILL.md
        claimed 21,024. Two figures for one measurement, and the one inside the
        tool is the one a reader trusts while running it."""
        doc = (SKILL_DIR / "shortlist.py").read_text()
        stated = re.search(r"In ([\d,]+) editable words", doc)
        self.assertIsNotNone(stated, "the script no longer cites the corpus")
        self.assertIn(stated.group(1), flowed(body(skill_text())),
                      "the script cites %r words of human prose and SKILL.md does "
                      "not state that figure anywhere" % stated.group(1))

    def test_it_never_calls_a_match_a_finding(self):
        out = self.run_on("Workers run on depth, not on guesswork.\n")
        self.assertIn("candidates to read, not findings", out)



class LoadBearingClaimTest(unittest.TestCase):
    """The sentences that change the verdict, pinned verbatim.

    Eleven mutations survived an earlier suite: `narrower` to `broader`, `never
    licenses editing` to `licenses editing`, `Flag at most; do not enforce` to
    `Enforce these rows like any other`, `never a finding` to `is a finding`, and
    so on. Every one of them flipped a claim while leaving its arithmetic
    self-consistent, because the numeric tests only checked that a ratio matched
    itself. A claim is pinned by its words or it is not pinned.
    """

    CLAIMS = (
        # Which way a conflict resolves.
        "**The narrower rule always wins.**",
        "A spread finding never licenses editing an instance whose own pattern or "
        "family is under threshold",
        "Count each instance once, and under the row whenever the row's string matches.",
        "Under every figure, an instance below threshold is left alone",
        # What is advisory and what is enforced.
        "Flag at most; do not enforce.",
        "A paragraph thick with em dashes is a prompt to read the prose, never a finding.",
        "Density still applies.",
        "Headings are prose: counted, and editable.",
        # What a repair may not do.
        "A rewrite that changes what the sentence claims is a failed rewrite.",
        "No After invents a fact.",
        "the disposition is keep, not rewrite",
        # What the tooling can and cannot settle.
        "The script cannot reach a verdict, and step 4 is where the finding is.",
        "A pass that runs the command and stops has not audited anything; it has "
        "approved everything.",
        # Scope of rule zero and of the exemption.
        "Skip the region, not the file.",
        # The FAQ exemption. Without it the family orders every question heading in
        # a genuine FAQ rewritten into a statement, which is prose damage.
        "**Exempt, and not counted:** an FAQ, a Q&A section, an interview transcript",
        "Ask whose question it is",
        "Nothing here measures authorship",
        # The thresholds, in words rather than as digits alone.
        "counted at 3 per document",
        "They cross at 4000 words",
        "in a document of at least 1000 editable words",
        # The measured claims about human prose.
        "**52 row matches, 0 surviving**",
        "**21,024 editable words**",
    )

    def setUp(self):
        self.body = flowed(body(skill_text()))

    def test_every_load_bearing_claim_is_present_verbatim(self):
        missing = [c for c in self.CLAIMS if c not in self.body]
        self.assertEqual(missing, [],
                         "these claims are gone or reworded, and each one changes "
                         "what the skill does:\n  " + "\n  ".join(missing))

    def test_the_negations_have_not_been_flipped(self):
        """A mutation that reverses a claim usually leaves its length alone, so
        the pin above catches it only if the polarity words are in the pinned
        span. These are the spans where a single word carries the direction."""
        for phrase, forbidden in (
            ("narrower rule always wins", "broader rule always wins"),
            ("never licenses editing", "always licenses editing"),
            ("do not enforce", "enforce these rows like any other"),
            ("never a finding", "is always a finding"),
            ("is left alone", "is edited anyway"),
        ):
            self.assertIn(phrase, self.body, "missing %r" % phrase)
            self.assertNotIn(forbidden, self.body.lower(),
                             "the claim %r has been inverted" % phrase)



if __name__ == "__main__":
    unittest.main()
