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

A match is a candidate to READ, never a finding. In 21,926 words of human
technical prose, fifteen of sixteen matches were correct writing.

    python3 shortlist.py README.md
    python3 shortlist.py --words-only README.md
"""

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
    text = re.sub(r"(?m)^(?: {4,}|\t).*$", blank, text)            # indented code
    text = re.sub(r"`[^`\n]*`", blank, text)                       # inline code
    text = re.sub(r"<[^>\n]+>", blank, text)                       # html and rst roles
    text = re.sub(r"https?://\S+", blank, text)                    # urls
    text = re.sub(r"(?m)^\|.*$", blank, text)                      # table rows
    text = re.sub(r"(?m)^[=~^`'\"*+#_-]{3,}\s*$", blank, text)     # rules, underlines
    return text


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


def report(path, words_only=False):
    text = open(path, encoding="utf-8", errors="replace").read()
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


def main(argv):
    words_only = "--words-only" in argv
    paths = [a for a in argv[1:] if not a.startswith("--")]
    if not paths:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    for path in paths:
        report(path, words_only)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
