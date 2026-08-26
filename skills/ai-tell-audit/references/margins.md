# What was measured, and on what

`SKILL.md` carries the rules a pass executes. This file carries the measurements behind
them: the corpus counts that set the thresholds, the cases that broke earlier versions of
a row, and the two documents that came closest to a wrong verdict. Read it when you want
to know why a figure is what it is, or when a row looks wrong and you are about to change
it. A pass does not need this file.

Provenance for the catalogue itself, and the full corpus numbers, are in
`sources/EVIDENCE.md`. This file is the subset that used to sit in `SKILL.md` and made a
reader absorb an argument before reaching a rule.

## Why density rather than presence

Nearly every pattern in the catalogue is defended by someone as legitimate craft, and they
are right. A reconciling comment from a discussion board: "Most of these are valid and
useful framing devices... it should, and has been, used in moderation, which LLMs
absolutely do not do." Nothing in the catalogue is a defect on its own. The pile-up is.

## The two documents that nearly came out wrong

The Go FAQ's "We understand that this is a point of contention" reads like an invented
adversary and is saved by the count alone.

PEP 465 stands at 4 on the `worth [X]` row and at 7 on `useful`, both over the figure of
3, and is saved only by step 5 reading each instance and finding every one literal.

Neither comes out right by much. That thinness is the reason for every clause in `SKILL.md`
that says to stop rather than to edit.

## Rows that stand far over the figure of 3 on human prose

Every instance below is literal, and step 5 is the only thing that keeps these documents
from being rewritten:

| Row | Document | Count |
|-|-|-|
| `names`, `naming` | Linux `coding-style.rst` | 16 (14 `names`, 2 `naming`) |
| `names`, `naming` | git `CodingGuidelines` | 10 |
| `useful` | Linux `submitting-patches.rst` | 5 |
| `useful` | PEP 465 | 7 |
| `harness` | sqlite testing page | 11 as a whole word, 22 counting `harnesses` and the like |

The sqlite figure is the exemption's worked case: a `test harness` is a term of art and
needs zero edits at any count.

Negation-then-correction was concrete on both halves in 15 of 15 instances across the
three revision-pinned documents, which is the ordinary case in reference prose.

## Rule zero: the file that proved it

The highest-hit file in the audit behind this skill was a `CONTRIBUTING.md` with six hits,
all inside its own list of forbidden words. Editing those would have deleted the guidance.
Editing its surrounding prose would have been an ordinary audit. That is the whole of
"skip the region, not the file": reading the filename as a whole-file exemption would void
the audit before it started, and would exempt exactly the documents this skill is most
often pointed at.

## Generated reference documentation

Three of four self-disclosed machine-written reference documents passed with one row match
between them. That is a limit of the catalogue, which is a list of rhetorical
constructions, and not a verdict on those documents.

## `real`: three rewrites that lost information

The `real` row is flagged and never enforced because rewriting it broke all three of these:

- "your real name (sorry, no pseudonyms)" lost its requirement as "your actual name";
- "collisions with shorter IDs a real possibility" became "a possibility", understating
  the risk;
- "real temporary directories" names genuine versus simulated.

## The repair that invented facts

An earlier version of `SKILL.md` repaired `(inevitably) be wrong for your workload` into
an invented worker count and an invented throughput figure. The file existed to prevent
exactly that harm and committed it in its own examples. It is the reason for the rule that
no After introduces a number, filename, measurement or name the Before did not carry, and
drops no claim the Before made.

## Detection is pseudoscience: the figures

Automated AI-writing detection is widely held to be unreliable. A 27-page human paper
scored 90% AI. A 2010 thesis, written before the models existed, scored 85%. The harm
falls disproportionately on ESL and neurodivergent writers. `SKILL.md` measures nothing
about authorship, and the rule there is not a caution but a boundary.
