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

**32 row matches across the first three, 19 in the fourth, 0 surviving anywhere**, so
none of them fires. Four rows individually clear the per-row figure of 3, and every one is
exempt before any count: `names` 14 times in `coding-style.rst` and 10 in git as the plain
noun ("function names"), and `useful` 5 times in one Linux document, each scoped ("useful
at this step"), which that row's own keep clause covers. That is what applying the
exemption first buys, and it is why the exemption is stated above this paragraph rather
than below. sqlite's "How SQLite Is Tested" is the fifth regression document and is
deliberately **not** in these totals: it is HTML with no revision id, and no command here
turns it into text reproducibly.

Two older figures survive in this file, a 3715-word machine-register file carrying
`load-bearing` 3 times and a 264-word PR body at 76 per thousand. They come from
documents that are not in this repository and **no command here reproduces them**. They
are recorded as history, not as evidence.

## Where the structural figures come from

**Where the figures come from.** Both counts below are printed by the shipped script, so
a reader can rerun them. The three revision-pinned human documents in the density section
come to **13,560 editable words**; `shortlist.py --rows` reports **15 candidate
matches**, and read one by one **0 surviving instances: 0.0 per thousand words**.
Fourteen are instructional contrasts of the form `octal escape sequences, not
hexadecimal`, where both halves are things a reader could type; the fifteenth is a grep
artefact. `coding-style.rst` adds 8 more candidates at 1.4 per thousand, every one an
instructional contrast (`comments tell WHAT your code does, not HOW`), and 0 surviving.

The README those tables cleared has **2354 editable words** and the same **16 candidate
matches**. Read one by one, 4 are negation-then-correction and 3 are comparative
aphorism. So negation-then-correction fires at 4 instances and 1.7 per thousand, and
comparative aphorism does not, standing at 3 against a floor of 4. What the other eight
families add to that document is deliberately **not stated here**: reaching it needs the
step 4 paragraph read, and no command reproduces a paragraph read. A number nobody can
rerun is the thing the Unsourced precision family is about.

## History


Ten documents written in one day: `load-bearing` 3 times across shipped skill files, the
most frequent tell by a wide margin; `quietly` twice ("quietly assumes context", "quietly
turns a read-only preparation"); `reaching for` twice, `the tell` once, `worth [X]` three
times. `CONTRIBUTING.md` scored highest at 6 hits, all inside its own banned-word list.

A later pass found the opposite failure, and it is the reason for the structural section.
The lexical tables alone cleared a README of 2356 editable words. Two readers, each given
the principle and no list of exclusions, reported forty constructions in it. Applying the
exemption, rule zero, and the recognition tests to those forty leaves one family over
threshold and the document-wide figure over threshold, which is a smaller finding than
forty and the correct one: unprimed readers over-flag, and the exemption architecture
exists to stop the skill doing the same. A catalogue of strings still cannot reach a
property of sentence construction.

Five human regression documents, all damaged by earlier versions: Linux
`submitting-patches.rst`, git `CodingGuidelines`, curl `CONTRIBUTE.md`, sqlite's "How
SQLite Is Tested", and Linux `coding-style.rst`. Each must come out with zero edits, and
each does: 51 row matches and 23 shortlist candidates across the revision-pinned four, 0
surviving either way. sqlite is the hardest,
with `harness` 11 times as a term of art in the text a tag strip produces, which without
the exemption is a dense row aimed straight at the damage. A fifth document joined the
corpus in round 3: Linux `coding-style.rst` at v5.15, whose five concession-and-rebuttal
paragraphs an earlier version of this file ordered deleted.

## Breadth in short documents

Measured with `shortlist.py --rows`, counting **distinct** catalogue rows rather than
total matches, because breadth is the signal a short generated document gives.

| Document | Editable words | Matches | Distinct rows | Surviving distinct rows |
|-|-|-|-|-|
| redis `CONTRIBUTING.md` at 7.2.0 | 367 | 0 | 0 | 0 |
| Linux `submitting-patches` excerpt | 321 | 0 | 0 | 0 |
| `concession-rebuttal.rst` (coding-style v5.15) | 409 | 1 | 1 | 0 |
| `testing-methodology.rst` | 412 | 19 | 5 | 0 |
| curl `BUGS.md` at 8.4.0 | 2041 | 1 | 1 | 0 |
| git `maintain-git` at v2.42.0 | 2601 | 3 | 2 | 0 |
| PEP 465 | 10309 | 41 | 9 | 0 |
| postgres nbtree README at REL_16 | 10758 | 39 | 6 | 0 |
| machine-drafted README (round 4 review) | 368 | 24 | 24 | **24** |

The highest surviving breadth in any human document measured is **0**, and the highest
raw distinct-row count under 1000 words is 5, every one exempt. The machine-drafted
short README carries 24 surviving distinct rows in 368 words. The floor of 8 in
`SKILL.md` sits above every human figure and at a third of the machine one.

The round-2 case that produced the 1000-word floor, a 765-word pull request body at 12
per thousand, was 9 instances concentrated in a single bulleted list, so its distinct-row
count is low and the breadth rule leaves it clean. That is the discrimination: breadth,
not depth.

## What is not reproducible

Two figures predate the shipped script and no command here reproduces them: a 3715-word
machine-register file carrying `load-bearing` 3 times, and a 264-word PR body at 76 per
thousand. They are recorded as history, not as evidence.
