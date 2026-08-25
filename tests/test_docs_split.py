#!/usr/bin/env python3
"""`docs/` holds two documents with different audiences, and they must not merge back.

`docs/CLAUDE-CODE-BEHAVIOR.md` records verified behavior of Claude Code itself, which is
useful to a project sharing no code with this one. `docs/DESIGN.md` records why this
package is shaped the way it is, and points at the platform file rather than restating a
finding. Both drifts are silent. A restated finding goes stale in one copy while the other
still reads true, which is how the frontmatter entry came to sit in two sections of one
file saying two different things. A pointer to a renamed file just stops resolving, and
markdown does not complain.

WHAT IS ASSERTED, AND HOW MUCH IT IS WORTH.

1. Every `.md` path a shipped document names resolves on disk, and every `#fragment` on a
   local link matches a heading in the file it points at. Decidable, and derived: the
   paths come out of the documents and the headings out of the target file, so renaming
   either end fails here rather than leaving a dead link. A backticked token counts as a
   naming only when it points somewhere inside this repository, which `is_citation`
   decides by asking the disk rather than by carrying a list of exceptions; the two tests
   below hold that rule to both directions.

2. No run of ten consecutive words appears in both `docs/` files. That is a copy-paste
   detector, nothing more. It catches a claim moved back by hand or duplicated by a
   later editor, which is the drift that has actually happened. It does NOT catch a
   paraphrase, and no assertion here is a claim otherwise: a scanner for "do these two
   paragraphs MEAN the same thing" is deciding a question about natural language, and
   `tests/test_doctrine_sync.py` documents at length how that arms race ends. A pointer
   from one file to the other therefore has to be short, which is the shape a pointer
   should have anyway.

3. Each file names the other, so the split cannot be half-undone by deleting the link.

4. Every entry in the platform file that states a finding also says how it was
   established and what it follows from. The whole premise of that file is that each
   entry was run rather than read, and an entry with no method behind it is the one thing
   it must not carry.

Nothing here reads a claim for meaning, and nothing here is a constant copied out of a
document. The word runs, the headings, the file list and the section structure are all
read off disk at runtime.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORM = ROOT / "docs" / "CLAUDE-CODE-BEHAVIOR.md"
DESIGN = ROOT / "docs" / "DESIGN.md"

# Every prose document that ships and may name another one. Globbed, so a new doc or a new
# skill is covered without editing this list.
DOCS = sorted(
    {ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / ".claude" / "CLAUDE.md"}
    | set((ROOT / "docs").glob("*.md"))
    | set((ROOT / "skills").glob("*/SKILL.md"))
    | set((ROOT / "skills").glob("*/references/*.md"))
)

FENCE = re.compile(r"```.*?```", re.S)
# `[text](target)`, and a backticked token that looks like a path to a markdown file.
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TICKED = re.compile(r"`([^`\s]*/[^`\s]*\.md)`")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.M)
COMMENT = re.compile(r"<!--.*?-->", re.S)
WORD = re.compile(r"[a-z0-9]+")

SHINGLE = 10

# A token that is a template, a shell expansion, an absolute path or a home path is not a
# path in this repo and cannot be resolved by looking on disk.
UNRESOLVABLE = ("<", ">", "$", "*", "{", "~")


def body(text):
    """Prose only: fenced code stripped, so a sample command is not read as a citation."""
    return FENCE.sub(" ", text)


def prose(text):
    """`body`, with link targets and HTML comments dropped.

    A URL is an address, not an assertion. Counting one as prose makes a pointer from one
    file to the other look exactly like the restatement the pointer exists to avoid, since
    a heading anchor is the heading with its spaces hyphenated.
    """
    return COMMENT.sub(" ", re.sub(r"\]\([^)\s]+\)", "]", body(text)))


def slug(heading):
    """GitHub's heading anchor: lowercased, non-word characters dropped, spaces hyphened."""
    s = heading.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s.replace("`", ""))
    return s.replace(" ", "-")


def rel(path):
    return path.relative_to(ROOT).as_posix()


def is_citation(citation, path):
    """Whether a backticked path token points somewhere inside this repository.

    A markdown link is unambiguously a pointer. A backticked token is not: prose also
    explains rules ABOUT paths, and `a/SKILL.md` and `b/SKILL.md` in `claim-provenance`
    are two placeholders standing for "two different directories", not two files anyone
    can open. Reading them as citations reports a dead link that was never a link.

    The discriminator is derived rather than listed, so a new document needs no entry
    anywhere: a path into this repository begins with a directory this repository has,
    either at the root or beside the citing document (which is how a skill's own
    `references/` reads). Nothing can ever live under `a/`, so `a/SKILL.md` names nothing
    that could go dead. Exempting the file instead would have switched the guard off for
    the one skill in the tree that is about claims decaying.

    What this deliberately does not catch, stated rather than papered over: renaming a
    top-level DIRECTORY takes every citation through it out of sight at the same moment it
    breaks them. It is renamed and moved DOCUMENTS the guard exists for, and those stay
    caught, because the directory they sat in is still there. A directory rename is also
    not silent: the installer walks `skills/`, `run_tests.sh` globs `tests/`, and both
    fail loudly. `test_the_illustration_rule_never_drops_a_path_that_resolves` pins the
    other direction, so the rule cannot quietly grow to cover a live pointer.
    """
    return (ROOT / citation.split("/")[0]).is_dir() or \
        (path.parent / citation.split("/")[0]).is_dir()


def cited_paths(path, text):
    """(citation, resolved Path) for every markdown file this document names."""
    out = []
    for target in MD_LINK.findall(text):
        if "://" in target or target.startswith("#"):
            continue
        base, _, frag = target.partition("#")
        if not base.endswith(".md") or any(c in base for c in UNRESOLVABLE):
            continue
        out.append((target, (path.parent / base).resolve(), frag))
    for target in TICKED.findall(text):
        if any(c in target for c in UNRESOLVABLE) or target.startswith("/"):
            continue
        if not is_citation(target, path):
            continue
        # A backticked path is written from the repo root; fall back to the file's own
        # directory, which is how a sibling under `docs/` reads.
        resolved = (ROOT / target)
        if not resolved.exists():
            resolved = (path.parent / target)
        out.append((target, resolved.resolve(), ""))
    return out


def shingles(text):
    words = WORD.findall(prose(text).lower())
    return {" ".join(words[i:i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


class DocPathTest(unittest.TestCase):
    def test_every_markdown_path_a_document_names_exists(self):
        checked = 0
        for path in DOCS:
            text = body(path.read_text())
            for citation, resolved, _frag in cited_paths(path, text):
                checked += 1
                self.assertTrue(
                    resolved.is_file(),
                    "%s cites `%s`, which resolves to %s and is not there. A moved or "
                    "renamed document leaves every pointer to it silently dead."
                    % (rel(path), citation, resolved))
        self.assertGreater(checked, 0, "no document cites another; this test is vacuous")

    def test_an_illustration_is_not_read_as_a_citation(self):
        """`a/SKILL.md` explains a rule about paths; it points at nothing, so there is
        nothing for it to point at wrongly. The synthetic document is never written: only
        its directory is used, which is what a real citation would be resolved against."""
        doc = ROOT / "docs" / "SYNTHETIC.md"
        found = [c for c, _r, _f in cited_paths(
            doc, "keyed on the path, because `a/SKILL.md` and `b/SKILL.md` share a name")]
        self.assertEqual(found, [], "a placeholder is not a pointer: %r" % (found,))

    def test_a_dead_citation_into_a_real_directory_still_fails(self):
        """The rule must not become a way to write a broken pointer. `docs/` exists, so a
        citation through it is a citation whether or not the file at the end is there."""
        doc = ROOT / "docs" / "SYNTHETIC.md"
        found = [(c, r.is_file()) for c, r, _f in cited_paths(
            doc, "the reasoning is in `docs/NO-SUCH-DOCUMENT.md`, which is the point")]
        self.assertEqual(found, [("docs/NO-SUCH-DOCUMENT.md", False)],
                         "a dead pointer into a directory this repo has must still reach "
                         "the assertion above: %r" % (found,))

    def test_renaming_a_document_a_shipped_file_cites_still_fails(self):
        """The defect the guard is for, reproduced against a citation that is live right
        now: take one that resolves, rename its target the way a real rename would, and
        the guard must see it. The citation is taken off disk, not written down here."""
        live = [(path, c) for path in DOCS
                for c, r, _f in cited_paths(path, body(path.read_text()))
                if "/" in c and r.is_file()]
        self.assertTrue(live, "no shipped document cites another by path; nothing to rename")
        path, citation = live[0]
        renamed = citation.replace(".md", "-RENAMED.md")
        found = [(c, r.is_file()) for c, r, _f in cited_paths(path, "see `%s`" % renamed)]
        self.assertEqual(found, [(renamed, False)],
                         "renaming %s would leave %s pointing at nothing, and the guard "
                         "must still be looking: %r" % (citation, rel(path), found))

    def test_the_illustration_rule_never_drops_a_path_that_resolves(self):
        """The other direction, over every shipped document: whatever the rule does, a
        token that names a file that is really there must stay inside the guard. Without
        this, a later loosening of `is_citation` could exempt live pointers silently."""
        checked = 0
        for path in DOCS:
            text = body(path.read_text())
            kept = {c for c, _r, _f in cited_paths(path, text)}
            for token in TICKED.findall(text):
                if any(ch in token for ch in UNRESOLVABLE) or token.startswith("/"):
                    continue
                resolved = ROOT / token
                if not resolved.exists():
                    resolved = path.parent / token
                if not resolved.is_file():
                    continue
                checked += 1
                self.assertIn(token, kept,
                              "%s names `%s`, which is a real file, and the citation rule "
                              "dropped it. The rule may only ever exclude a path nothing "
                              "in this repository could be at" % (rel(path), token))
        self.assertGreater(checked, 0, "no backticked path resolves anywhere; vacuous")

    def test_every_link_fragment_names_a_heading_that_exists(self):
        checked = 0
        for path in DOCS:
            text = body(path.read_text())
            for citation, resolved, frag in cited_paths(path, text):
                if not frag or not resolved.is_file():
                    continue
                checked += 1
                anchors = {slug(h) for h in HEADING.findall(body(resolved.read_text()))}
                self.assertIn(
                    frag, anchors,
                    "%s links to `%s`, and %s has no heading with that anchor. Retitling "
                    "a section breaks every deep link into it, and nothing reports it.\n"
                    "  anchors there: %s"
                    % (rel(path), citation, rel(resolved), ", ".join(sorted(anchors))))
        self.assertGreater(checked, 0, "no document deep-links into another; vacuous")


class DocsSplitTest(unittest.TestCase):
    def test_no_claim_lives_in_both_docs_files(self):
        """A ten-word run in both files is a claim that was moved and then restated."""
        both = shingles(PLATFORM.read_text()) & shingles(DESIGN.read_text())
        self.assertEqual(
            sorted(both)[:3], [],
            "%d word runs appear in both %s and %s. Platform behavior belongs in the "
            "first and local rationale in the second; a claim in both goes stale in one "
            "copy while the other still reads true. Point at it instead of restating "
            "it.\n  first offender: %r"
            % (len(both), rel(PLATFORM), rel(DESIGN), sorted(both)[:1]))

    def test_each_docs_file_points_at_the_other(self):
        for a, b in ((PLATFORM, DESIGN), (DESIGN, PLATFORM)):
            self.assertTrue(
                b.name in a.read_text(),
                "%s never names %s, so a reader who lands on one has no route to the "
                "other and the split just hides half the record" % (rel(a), rel(b)))

    def test_every_platform_finding_says_how_it_was_established(self):
        sections = re.split(r"\n(?=## )", body(PLATFORM.read_text()))
        stated = [s for s in sections if "**Finding.**" in s]
        self.assertGreater(len(stated), 1,
                           "%s no longer marks its entries with `**Finding.**`, so this "
                           "test is checking nothing" % rel(PLATFORM))
        for section in stated:
            title = section.splitlines()[0].lstrip("# ").strip()
            for required in ("**How established.**", "**What it means.**"):
                self.assertIn(
                    required, section,
                    "%s entry %r states a finding without %s. Every entry in that file "
                    "claims to have been run rather than read; an entry that does not say "
                    "what was run cannot be re-run or trusted."
                    % (rel(PLATFORM), title, required))


if __name__ == "__main__":
    unittest.main(verbosity=2)
