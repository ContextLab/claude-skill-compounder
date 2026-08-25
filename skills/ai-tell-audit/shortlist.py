#!/usr/bin/env python3
"""Count the editable words in a document, and shortlist its greppable tells.

Two numbers in SKILL.md are otherwise computed by eye, and two sessions counting
by eye differ by tens of per cent:

  1. The denominator for every rate in the file. Markup is not prose, so code
     fences, inline code, URLs, frontmatter and table rows are excluded. Headings
     are prose: they are counted, and the Question-as-heading family edits them.
  2. The negation-then-correction shortlist. The greps in SKILL.md are line
     based, and technical prose hard wraps, so `is worth\\nmore than` never
     matches on the raw file. Paragraphs are unwrapped here before matching, and
     every match is reported against the line it starts on.

A match is a candidate to READ, never a finding. In 21,024 editable words of
human technical prose, all sixteen matches were correct writing.

    python3 shortlist.py README.md
    python3 shortlist.py --words-only README.md
"""

import os
import re
import sys

# Applied to UNWRAPPED text, and matching intra-line whitespace only. That pairing
# is what makes the unwrap load bearing: a wrapped phrase matches because unwrap
# turned its newline into a space, and a phrase straddling a blank line never
# matches because the paragraph break survives as a newline. Using `\s+` here
# would match across both and the unwrap would be decoration. Deliberately loose: the recognition test
# in SKILL.md decides, this only builds the reading list.
SHORTLIST = [
    (r"(?<![\w-])not[ \t]+(?:just|only|merely|simply)\b[^.;\n]{0,80}?\b(?:but|it's)\b", "cleft"),
    (r",[ \t]+not[ \t]+(?!only|just|merely|simply|to\b|be\b)", "bare"),
    (r"(?<![\w-])rather[ \t]+than(?![\w-])", "rather-than"),
    (r"(?<![\w-])is[ \t]+not[ \t]+\w[^.;\n]{0,60};[ \t]*it[ \t]+is(?![\w-])", "semicolon"),
    (r"(?<![\w-])isn't[ \t]+about\b[^.\n]{0,60}\bit's[ \t]+about\b", "isnt-about"),
    # Comparative aphorism. Included because it is the other greppable family and
    # because it is the case that proves the unwrap: the README this skill was
    # built against carries `is worth\nmore than a proposal` across a line break,
    # which no line-based grep can see.
    (r"(?<![\w-])is[ \t]+(?:worse|better)[ \t]+than(?![\w-])", "comparative"),
    (r"(?<![\w-])is[ \t]+worth[ \t]+(?:more|less)[ \t]+than(?![\w-])", "comparative"),
]


def strip_markup(text):
    """Blank every region that is markup rather than prose, keeping newlines so
    line numbers survive. Blanking rather than deleting is what lets the caller
    report a match against its line in the original file."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))

    text = re.sub(r"\A---\n.*?\n---\n", blank, text, flags=re.S)   # frontmatter
    text = re.sub(r"```.*?```", blank, text, flags=re.S)           # fenced code
    text = _blank_indented_code(text, blank)                       # indented code
    text = re.sub(r"`[^`\n]*`", blank, text)                       # inline code
    text = re.sub(r"<[^>\n]+>", blank, text)                       # html and rst roles
    text = re.sub(r"https?://\S+", blank, text)                    # urls
    text = re.sub(r"(?m)^\|.*$", blank, text)                      # table rows
    text = re.sub(r"(?m)^[=~^`'\"*+#_-]{3,}\s*$", blank, text)     # rules, underlines
    return text


LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")


def _blank_indented_code(text, blank):
    """Blank indented CODE blocks without blanking indented LIST CONTINUATIONS.

    A four-space indent means a code block only outside a list. Inside one it is
    a nested bullet or a continuation paragraph, and blanking those deletes real
    prose from the denominator: a 22-word file of nested bullets counted 13 words,
    a 41% undercount, and every rate divides by this number.

    A list is open from its first marker until a non-blank line appears at column
    zero that is not itself a marker. RST literal blocks (a line ending in `::`)
    open a code block even inside a list.
    """
    out, in_list, literal = [], False, False
    for line in text.split("\n"):
        stripped = line.strip()
        indented = bool(re.match(r"[ \t]", line)) and line[:4].strip() == ""
        if not stripped:
            out.append(line)
            continue
        if LIST_ITEM.match(line):
            in_list, literal = True, line.rstrip().endswith("::")
        elif not indented:
            in_list, literal = False, stripped.endswith("::")
        if indented and (literal or not in_list):
            out.append(re.sub(r"[^\n]", " ", line))
        else:
            out.append(line)
    return "\n".join(out)


def editable_words(text):
    return len(strip_markup(text).split())


def unwrap(text):
    """Join wrapped lines inside a paragraph, keeping a line number per character.

    Returns (flowed text, list giving the source line of each character). A blank
    line ends a paragraph and is preserved, so paragraph boundaries still stop a
    match from running across them.
    """
    chunks = []            # (text, source line)
    previous_blank = True
    for n, line in enumerate(text.split("\n"), 1):
        blank_line = not line.strip()
        if chunks:
            chunks.append(("\n" if blank_line or previous_blank else " ", n))
        chunks.append((line, n))
        previous_blank = blank_line
    flowed = "".join(c for c, _ in chunks)
    per_char = []
    for chunk, n in chunks:
        per_char.extend([n] * len(chunk))
    return flowed, per_char


def shortlist(text):
    """[(label, line number, matched text, context)] over unwrapped, stripped text."""
    flowed, per_char = unwrap(strip_markup(text))
    hits = []
    for pattern, label in SHORTLIST:
        for m in re.finditer(pattern, flowed, re.I):
            line = per_char[m.start()] if m.start() < len(per_char) else 0
            context = flowed[max(0, m.start() - 60):m.end() + 45]
            hits.append((label, line, m.group(0), " ".join(context.split())))
    return sorted(hits, key=lambda h: h[1])


def catalogue_rows(skill_md):
    """Every backticked pattern in a two-column table of SKILL.md.

    Parsed out of the document rather than copied here, so the counts this mode
    reports are the counts of the rows the reader is actually applying.
    """
    terms, in_table = set(), False
    for line in skill_md.split("\n"):
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 2 and cells[1] in ("Fix", "Disposition"):
            in_table = True
            continue
        if in_table and len(cells) == 2:
            terms |= set(re.findall(r"`([^`]+)`", cells[0]))
    return sorted(terms)


def row_regex(term):
    """`X`, `Y`, `Z` and `[verb]` are placeholders and match one word."""
    parts = re.split(r"(\[[^\]]*\]|(?<![A-Za-z])[XYZ](?![A-Za-z]))", term)
    body = "".join(r"\S+" if i % 2 else re.escape(p).replace(r"\ ", r"[ \t]+")
                   for i, p in enumerate(parts))
    prefix = r"(?<![\w-])" if term[0].isalnum() else ""
    suffix = r"(?![\w-])" if term[-1].isalnum() else ""
    return re.compile(prefix + body + suffix, re.IGNORECASE)


def rows(text, skill_md):
    """[(term, line, matched)] for every catalogue row string in the document."""
    flowed, per_char = unwrap(strip_markup(text))
    hits = []
    for term in catalogue_rows(skill_md):
        for m in row_regex(term).finditer(flowed):
            line = per_char[m.start()] if m.start() < len(per_char) else 0
            hits.append((term, line, m.group(0)))
    return sorted(hits, key=lambda h: h[1])


def apply_skips(text, skips):
    """Blank the line ranges rule zero says to skip, before anything is counted.

    Step 2 of the procedure is otherwise inert: the denominator would include a
    banned-word list that the same file says must be excluded.
    """
    lines = text.split("\n")
    for spec in skips:
        first, _, last = spec.partition("-")
        first = int(first)
        last = int(last or first)
        for n in range(first, min(last, len(lines)) + 1):
            lines[n - 1] = ""
    return "\n".join(lines)


def report(path, words_only=False, skips=(), skill_md=None):
    text = open(path, encoding="utf-8", errors="replace").read()
    if skips:
        text = apply_skips(text, skips)
    words = editable_words(text)
    print("%s: %d editable words" % (path, words))
    if words_only:
        return
    hits = shortlist(text)
    rate = 1000.0 * len(hits) / words if words else 0.0
    print("%s: %d shortlist matches, %.1f per thousand words (candidates to read, "
          "not findings)" % (path, len(hits), rate))
    for label, line, matched, context in hits:
        print("  L%-5d %-11s %s" % (line, label, context))
    if skill_md is None:
        return
    found = rows(text, skill_md)
    counted = {}
    for term, line, matched in found:
        counted.setdefault(term, []).append((line, matched))
    print("%s: %d row matches across %d catalogue rows (candidates to read, "
          "not findings)" % (path, len(found), len(counted)))
    for term in sorted(counted, key=lambda k: -len(counted[k])):
        where = ", ".join("L%d" % line for line, _ in counted[term][:6])
        print("  %-24s %3d  %s" % (term, len(counted[term]), where))


def main(argv):
    words_only = "--words-only" in argv
    skips = [a.split("=", 1)[1] for a in argv[1:] if a.startswith("--skip=")]
    skill_md = None
    for arg in argv[1:]:
        if arg.startswith("--rows="):
            skill_md = open(arg.split("=", 1)[1], encoding="utf-8").read()
        elif arg == "--rows":
            beside = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "SKILL.md")
            skill_md = open(beside, encoding="utf-8").read()
    paths = [a for a in argv[1:] if not a.startswith("--")]
    if not paths:
        print("usage: python3 shortlist.py [--words-only] [--rows[=SKILL.md]] "
              "[--skip=A-B] FILE...")
        return 2
    for path in paths:
        report(path, words_only, skips, skill_md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
