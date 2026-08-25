# Evidence behind the thresholds

Every number in `SKILL.md` traces to this file. It is kept separate because a session
auditing a document needs the rules, not their provenance, and a reader who stops before
the end of `SKILL.md` must not be stopping before a rule. Nothing here is a rule.

## The regression corpus

Measured with `shortlist.py --rows` on four human documents pinned by revision, so every
figure below can be rerun: Linux `submitting-patches.rst` at 83f71fbc66fb, git
`CodingGuidelines` at 570e1e0d0ff6, curl `CONTRIBUTE.md` at 7e1001bcd699, and Linux
`coding-style.rst` at tag v5.15. Together **13,560 editable words** for the first three,
**5717** for the fourth. All four are external to this repository, so a rerun needs the
pull first, and all four are human-authored rather than pre-LLM: curl's `CONTRIBUTE.md`
at that pin carries a section on AI use added well after 2022. The claim is that people
wrote them, which is what the exemption has to survive.

Re-measured in round 5, after the counter changed from strings to rows and began merging
overlapping spans: **24 row matches across the first three, 19 in the fourth, 0 surviving
anywhere**, so none of them fires. Every earlier figure here was higher, for three
reasons since fixed: one occurrence of `It is worth noting` counted twice, a row of eight
synonyms counted as eight rows, and RST heading underlines counted as thematic breaks.

**Two rows clear the per-row figure of 3, in three of the four documents**, and every
instance is exempt before any count: the `names`/`naming` row 16 times in
`coding-style.rst` (14 `names`, 2 `naming`) and 10 in git's `CodingGuidelines`, all the
plain noun or gerund ("function names", "array names", "naming convention"), and the
`useful` row 5 times in `submitting-patches.rst`, each scoped ("useful at this step"),
which that row's own keep clause covers. That is what applying the
exemption first buys, and it is why the exemption is stated above this paragraph rather
than below. sqlite's "How SQLite Is Tested" is the fifth regression document and is
deliberately **not** in these totals: it is HTML with no revision id, and no command here
turns it into text reproducibly.

## Where the structural figures come from

Both counts below are printed by the shipped script, so a reader who pulls the documents
can rerun them. The three revision-pinned human documents in the density section come to
**13,560 editable words**; `shortlist.py --rows` reports **15 candidate
matches**, and read one by one **0 surviving instances: 0.0 per thousand words**.
Fourteen are instructional contrasts of the form `octal escape sequences, not
hexadecimal`, where both halves are things a reader could type; the fifteenth is a grep
artefact. `coding-style.rst` adds 8 more candidates at 1.4 per thousand, every one an
instructional contrast (`comments tell WHAT your code does, not HOW`), and 0 surviving.

**No figure here comes from this repository's own README.** Earlier versions quoted its
word count and its verdict. That file changes for reasons unrelated to this skill, so
every such figure went stale on somebody else's commit and took a test with it. A skill
that grades a moving target grades itself.

The worked verdict below uses `coding-style.rst` instead, pinned at v5.15. It is the
hardest document in the corpus for the structural families: 8 shortlist candidates at 1.4
per thousand, every one an instructional contrast, and five paragraphs of concession and
rebuttal that an earlier version ordered deleted. Nothing fires. No row reaches 3 after
the exemption, no family reaches 4, and the document-wide figure needs the step 4
paragraph read, which no command reproduces. That last point is the honest limit: this
file states no document-wide verdict for any document, because a number nobody can rerun
is the thing the Unsourced precision family is about.

## History


Ten documents written in one day: `load-bearing` 3 times across shipped skill files, the
most frequent tell by a wide margin; `quietly` twice ("quietly assumes context", "quietly
turns a read-only preparation"); `reaching for` twice, `the tell` once, `worth [X]` three
times. `CONTRIBUTING.md` scored highest at 6 hits, all inside its own banned-word list.

A later pass found the opposite failure, and it is the reason for the structural section.
The lexical tables alone cleared a README that two readers, each given the principle and
no list of exclusions, then reported forty constructions in. No count from that document
is quoted anywhere in this skill, for the reason given above. Applying the
exemption, rule zero, and the recognition tests to those forty leaves one family over
threshold and the document-wide figure over threshold, which is a smaller finding than
forty and the correct one: unprimed readers over-flag, and the exemption architecture
exists to stop the skill doing the same. A catalogue of strings still cannot reach a
property of sentence construction.

Five human regression documents, all damaged by earlier versions: Linux
`submitting-patches.rst`, git `CodingGuidelines`, curl `CONTRIBUTE.md`, sqlite's "How
SQLite Is Tested", and Linux `coding-style.rst`. Each must come out with zero edits, and
each does: **43 row matches** (24 across the first three, 19 in `coding-style.rst`) and
**23 shortlist candidates** across the revision-pinned four, 0 surviving either way. sqlite is the hardest,
with `harness` 11 times as a whole word in the text a tag strip produces, which without
the exemption is a dense row aimed straight at the damage. A fifth document joined the
corpus in round 3: Linux `coding-style.rst` at v5.15, whose five concession-and-rebuttal
paragraphs an earlier version of this file ordered deleted.

## Breadth in short documents, and why there is no rule for it

A breadth rule was drafted in round 4 and removed in round 5. It counted distinct rows
with at least one surviving instance and fired at 8 in a document under 1000 words.

It was withdrawn for three reasons, each fatal on its own:

- Its floor came from one 368-word machine-drafted README reported to carry 24 surviving
  distinct rows. No path, no command, and no way to rerun it.
- The counter that produced the human side of the comparison counted **strings**, not
  rows. One row of eight synonyms reported as eight distinct rows, so a 46-word document
  could reach the floor out of a single row of the weakest family in the file. Both sides
  of the calibration were measured with that counter.
- On a twelve-document acceptance corpus the machine-written documents sat at 1 to 3
  distinct rows. The rule would not have fired on them either.

What survives is the measurement of short human prose, which is what the rows have to
stay clear of. Run `shortlist.py --rows` to reproduce any line. The four fixture rows reproduce from
this checkout alone; the rest need the pull first. PEP 465 is measured from the **rendered
page** at `peps.python.org`, not the `.rst` source, which gives 9454 words for the same 41
matches and 8 rows.

| Document | Editable words | Row matches | Distinct rows | Surviving |
|-|-|-|-|-|
| redis `CONTRIBUTING.md` at 7.2.0 | 367 | 0 | 0 | 0 |
| `submitting-patches.txt` fixture | 321 | 0 | 0 | 0 |
| `defined-terms.md` fixture | 196 | 0 | 0 | 0 |
| `concession-rebuttal.rst` fixture | 409 | 1 | 1 | 0 |
| `testing-methodology.rst` fixture | 412 | 19 | 5 | 0 |
| curl `BUGS.md` at 8.4.0 | 2041 | 1 | 1 | 0 |
| git `maintain-git` at v2.42.0 | 2601 | 3 | 2 | 0 |
| PEP 465, rendered page at peps.python.org | 10309 | 41 | 8 | 0 |
| postgres nbtree README at REL_16 | 10758 | 28 | 4 | 0 |

## What is not reproducible

Four figures in this project's history predate the shipped script and **no command here
reproduces any of them**: a 3715-word machine-register file carrying `load-bearing` 3
times; a 264-word PR body at 76 per thousand; a 368-word machine-drafted README reported
at 24 surviving distinct rows, which is why the breadth rule was withdrawn; and a
765-word pull request body at 12 per thousand. They are recorded as history, not as
evidence, and no threshold in `SKILL.md` now rests on any of them.
