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

import re
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
                self.assertNotIn(EM_DASH, path.read_text(), "em dash in %s" % path)


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

    def test_no_must_not_prompt_carries_the_trigger_vocabulary(self):
        """A negative example containing a genre from the description asks the
        router to fire and not fire on the same words."""
        for prompt in self.prompts("Must NOT fire:"):
            for word in self.genre_words():
                self.assertNotRegex(prompt.lower(), r"(?<![\w-])%s(?![\w-])" % word,
                                    "must-NOT prompt %r contains the trigger word %r"
                                    % (prompt, word))

    def test_the_must_fire_prompts_do_carry_it(self):
        vocabulary = self.genre_words()
        carrying = [p for p in self.prompts("Must fire:")
                    if any(re.search(r"(?<![\w-])%s(?![\w-])" % w, p.lower())
                           for w in vocabulary)]
        self.assertGreaterEqual(len(carrying), 2,
                                "the must-fire prompts share no vocabulary with the "
                                "description: %r" % self.prompts("Must fire:"))


if __name__ == "__main__":
    unittest.main()
