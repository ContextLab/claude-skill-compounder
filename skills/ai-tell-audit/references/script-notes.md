# The script: what it reaches, and the pass without it

`shortlist.py` ships beside `SKILL.md`. Step 3 runs it. This file is what a reader needs
when the output is confusing, when a label has to be mapped back to a family, or when the
script cannot be run at all.

## What its labels mean

`cleft`, `bare`, `semicolon`, `isnt-about` and `rather-than` are all
negation-then-correction. `comparative` is comparative aphorism. Nothing else maps to a
family, because nothing else is greppable. `rather than` has no negated half, so ask its
recognition test of the rejected alternative instead.

## Why it unwraps the text first

Hard-wrapped prose splits a phrase across lines, so `is worth` and `more than a proposal`
are invisible to a line-based grep. A phrase straddling a blank line, on the other hand,
is two paragraphs and must never match. The script joins the first case and keeps the
second apart.

Every match is still only a candidate. Across the four revision-pinned human documents in
`sources/EVIDENCE.md`, none was a finding.

## The pass with no script

Nothing in the pass depends on the script being runnable. It is faster and it is exact,
and that is all it is. If `python3` is unavailable, if the skill directory is read-only,
or if the file is somewhere the script cannot reach:

1. **Denominator.** Count editable words by hand or with `wc -w` over the file with code
   fences, indented code, inline code, URLs, frontmatter, table rows and heading
   underlines taken out. Say in the output that the count is by eye. An eye count varies
   between sessions by tens of per cent, so a document-wide rate computed from one is
   weak evidence: prefer the per-row and per-family figures, which need no denominator.
2. **Rows.** Do step 4 for every row as well as every family. The reading pass reaches
   every row in the catalogue, including the ones the script matches as strings. It is
   slower and it misses nothing the script would have found.
3. **Say so.** The output contract asks for the editable word count. Report it as
   uncounted rather than reporting a figure the reader will take as measured.

A pass run this way is a complete pass. A pass that runs the script and stops at its
output is not: the script reaches two of the ten families and only the rows that are
strings.
