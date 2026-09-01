---
name: ai-tell-audit
description: "Use when about to draft or rewrite prose others will read: run BEFORE drafting (a README or docs page, release notes, a changelog, a GitHub issue or comment, a PR description, an announcement, a multi-paragraph commit body). 'Draft the release notes', 'draft a comment on issue #40', 'rewrite this README section' fire this first. Fixing typos, grammar or comma splices is copy-editing and does NOT fire; the request decides, not the file. NOT for chat replies, code comments, or scratch notes."
---

# AI Tell Audit

**Catalogue reviewed 2026-08-25. Due for review 2027-02-25.** Past that date the rows below
are unchecked against three sources that all move. Run `sources/REFRESH.md` first: its guarded
check against the main source is a short shell block that fails closed and costs a second.

A find-and-fix pass over prose you are about to publish. The patterns are already known and
published, so there is nothing to detect and no score to compute. Depth this file does not
need in order to run is in `references/`.

## The pass, in order

1. **Decide from the request, not the file.** The genres are in the description; the
   precedence rule is under `When this fires`. If the request is copy-editing, stop here.
2. **Mark the skip regions.** Rule zero, below, before anything is counted or read. The
   script has no rule-zero awareness, so pass the line ranges to it: `--skip=120-148`,
   repeatable. Without that, a banned-word list lands in the denominator this file says
   must exclude it. Scan for page furniture here too: a plain-text RFC or a man page
   repeats a running header on every page, and those lines are not prose.
3. **Count the denominator and the rows.** `shortlist.py` sits beside this file. Run
   `python3 <this skill's directory>/shortlist.py --rows --skip=<each range from step 2> <file>`.
   It prints the editable word count, the greppable shortlist, and a count for every
   catalogue row that is a string. Carry the `--skip` ranges from step 2 into this
   command; leaving them off re-admits the region step 2 excluded. If you cannot run it,
   `references/script-notes.md` gives the pass by hand; the reading pass reaches every row.
4. **Read every paragraph once, in order.** The command in step 3 reaches two of the ten
   families and only the rows that are strings. Eight families, and every row that describes
   a construction rather than a string, are found only here. Ask each one's recognition test
   of the paragraph in front of you. The pass is complete when every paragraph has been read
   once: there is no search to exhaust, and a family or row with no candidate is recorded as
   zero rather than as unchecked.
5. **Apply the exemption to each match, one at a time.** A match is a candidate, never a
   finding. Across the four human documents in `sources/EVIDENCE.md`, every candidate was
   exempt and none was a finding. Skipping this step is what damages documents.
6. **Count the survivors**, three ways: per row, per family, and document-wide. Throughout
   this file a **surviving** instance is one that got past step 5 and counts toward a
   threshold; nothing else uses the word.
7. **Apply the thresholds.** Only a pattern or family at or over its own threshold
   produces an edit. Nothing else is edited, however the document reads.
8. **Edit or report.** Edit in place when the user handed you the document to publish; return
   a list when they asked what you found. If the request says neither, ask before writing.

**Output contract.** Whatever the mode, the reply carries, in this order:

- the editable word count, and the `--skip` ranges taken out of it;
- every row that fired, with its **count**; rows have no rate, and the figure of 3 holds
  at any length;
- every family that fired, with its **count and its rate**;
- if the document-wide figure fired, its count, its rate, and the three heaviest families,
  which is what a spread finding owes the reader;
- every edit, as a before and an after;
- one line for what was left alone and why.

A pass that fired nothing says so and changes nothing, which is a result and not a failure.

## Literal and terminological use is exempt, everywhere

**Every row in this file is a rule about a word or a construction used for effect rather
than for meaning. None fires on the literal sense, on a term of art, or on markup the format
requires.** Most rows are about metaphor; `worth [X]`, `robust` and the unnamed-opposition
row are not, and the rule covers them the same way. File-wide, so no row repeats it. Four
cases that broke earlier versions:

- `harness` is banned as a corporate verb. A `test harness` is a term of art: sqlite's
  testing page uses it 11 times in the prose `shortlist.py --rows` counts and needs zero
  edits at any count.
- `the entire X` is an empty intensifier. `the entire filesystem` names a scope.
- `robust` is an empty adjective. `robust against malicious attack` carries a claim that
  contrasts with "robust in normal use", and flattening it loses the contrast.
- `---` is an AI section divider in Markdown. In reStructuredText it underlines a heading.

When a word carries information no plain synonym carries, keep it, and do not count it.

## Density is the finding

**One instance of a listed pattern is usually fine, and often it is good writing.** Nearly
every pattern below is defended as legitimate craft; what no one defends is the pile-up.

Apply the exemption first, then count. **The denominator is `python3 shortlist.py <file>`**,
not an estimate: counted by eye, two sessions differ by tens of per cent, and the rate is
what decides. It excludes code fences, indented code, inline code, URLs, frontmatter, table
rows and heading underlines. Headings are prose: counted, and editable. Excluded regions are
excluded from **editing** as well as from counting, except table cells, which are not
counted (their register is not prose) but may be edited once a pattern has fired somewhere
else in the document. **A surviving instance is non-literal, non-quoted, and not a term of
art.** Edit a pattern when it reaches **3 or more surviving instances in one document**,
however long: repeating one metaphor three times is the tic, and a rate would hide it in a
long file. The document as a whole is a finding when surviving instances **across all
patterns reach 6 per thousand words in a document of at least 1000 editable words**, even
when no single pattern does: the pile-up is spread rather than concentrated. Below 1000
words a rate is sampling noise, and one bulleted list moves it by several per thousand.
There is a step at the boundary, and it is deliberate: at 999 editable words nothing fires
on rate, at 1000 six instances do. The rows still apply at any length.

**Known limit: short machine-drafted prose can pass.** Under 1000 words the only rules left
are the rows, and a short generated document spreads itself thin across many rows rather
than repeating one. A threshold nobody can rerun is not a threshold; the rule drafted for
this gap and withdrawn is in `sources/EVIDENCE.md`. If it bears on your document, read it.

**The narrower rule always wins.** A spread finding never licenses editing an instance whose
own pattern or family is under threshold. The disposition is the note, not the edit. Say the
count, the rate, and the three heaviest families, and hand it back. **Under every figure, an
instance below threshold is left alone**, even where the plain version would read better.
That is step 7, and it is the whole protection: a licence to fix what looks wrong is a
licence to rewrite anything.

**The margins on good human prose are thin.** PEP 465 stands at 4 on the `worth [X]` row and
at 7 on `useful`, both over the figure of 3, and is saved only by step 5 finding every one
literal. Neither it nor the Go FAQ comes out right by much (`references/margins.md`), which
is the reason for every clause above that says to stop rather than to edit.

The document-wide figure counts every surviving instance, row and family alike. The
per-pattern figure of 3 governs a **row**, whether the row gives a string or describes a
construction. The **headed families** carry their own two figures.

**The row is the unit everywhere**, which is what `shortlist.py --rows` counts. A row listing
several constructions is still one row: two one-sentence paragraphs plus one rhetorical
question is 3 against that row, not 2 and 1 against nothing. A row describing a construction
counts **once per paragraph**, not per sentence or per bullet. Where a row states its own
proportional condition, that runs first and the figure of 3 applies to what survives it.

**A construction can be reachable by both**: `it isn't about X, it's about Y` is a row and
also negation-then-correction; `quietly` is a row and also a knowing aside. **Count each
instance once, and under the row whenever the row's string matches.** The row's figure of 3
is the stricter, so a matching string is judged by the row and not again under the family.

## Never a verdict on authorship

AI-writing detection is widely held to be pseudoscience, with disproportionate harm to ESL
and neurodivergent writers; the figures are in `references/margins.md`. Nothing here
measures authorship. **Use it on a draft that is about to be published, whoever wrote it**,
never to assess who wrote something, never as input to a grade or a moderation decision.
Auditing a colleague's PR description is in scope: a publication is being prepared. Being
asked whether they used a model is not, at any density, on any count.

## Rule zero: never edit named or borrowed text

A document that *names* one of these patterns is not committing it. Skip, without exception:
quoted material, blockquotes, log output, error strings; banned-word lists, style guides,
linter configs, this file; examples labelled as bad, before/after pairs, test fixtures;
code, code fences, identifiers (`surface()` is a function name); ASCII diagrams, tables
drawn in characters, and anything else whose layout carries the meaning; **page furniture**,
meaning running headers and footers, page numbers, tables of contents and boilerplate the
format repeats rather than the author. An RFC in plain text carries the same running header
27 times, and counted as prose it feeds Repeated signature phrase a signature nobody wrote.

**Skip the region, not the file.** A contribution guide under any of its spellings
(`CONTRIBUTING.md`, `CONTRIBUTE.md`, `CodingGuidelines`) is skipped **where it lists
forbidden words or quotes a bad example**, and audited in its own prose like anything else.
Reading the filename as a whole-file exemption would void the audit before it started, and
would exempt exactly the documents this skill is most often pointed at; the file that proved
it is in `references/margins.md`. If the text is mentioned rather than used, leave it alone.

## When this fires

The condition is observable: am I about to publish prose for other people to read? It does
not depend on judging whether the draft reads badly.

**A document you did not draft.** Step 1 asks whether you are about to publish, and most of
what this skill is handed is somebody else's file. The condition is the publication, not the
authorship: a review before merge, a PR you are about to open, a docs page you were asked to
get ready all fire, because a draft is being prepared for readers. So does a request to
compose one of the genres from scratch ("write the release notes", "draft a comment on the
issue"): the draft you produce is about to be published, so the pass runs on it before it is
handed back. What does not fire is being asked to judge the document or its author: editing
prose to prepare it and rendering a verdict on who wrote it are different acts.

**Precedence: the request decides, not the file.** A genre from the description is necessary
and never sufficient, because the two halves of the trigger overlap on purpose. "Fix the
typos in the README before I merge" gives a genre and asks for correctness, so the
copy-editing clause wins and this does not fire. "The README reads like a machine wrote it"
gives the same genre and asks about how it reads, so it fires. A drafted announcement fires;
the chat message announcing it does not, because the artifact that gets published is the
draft. When both clauses match and the request is genuinely unclear, ask. Never edit
somebody's prose on a guess about what they meant. Not for chat replies, code comments,
scratch notes, one-line commit subjects, or grammar and house-style copy-editing.

**Scope: argued prose, not generated reference.** Every row and family here is a rhetorical
construction, so it has purchase where a document argues, explains or persuades. It has
almost none on generated reference: API listings, changelogs, machine-written vulnerability
reports and templated status pages come out clean whether a person or a model wrote them.
That is a limit of the catalogue, not a verdict on the document (counts in
`references/margins.md`). Do not read a clean pass on generated reference as evidence of
anything.

Two edge calls: an internal team wiki page is durable prose other people read, so it fires;
"this section sounds stilted, tighten it" fires only when it names a genre above, since
bare "tighten this" is copy-editing.

## Three dispositions

**Rewrite** when the sentence makes a claim: say the same claim in plain words.
**Delete** when the pattern carries no claim: "It is worth noting that X" means X.
**Keep** when the plain version would lose information, when the usage is literal rather
than metaphorical, or when the instance is isolated. Keep is a first-class outcome; a pass
that changes nothing on a good document succeeded.

**A rewrite that changes what the sentence claims is a failed rewrite.** If the plain
version cannot state the same claim, keep the original. **Vary the repairs.** Turning every
em dash into a colon swaps one tic for another; no substitution twice in a row.

## Keep by default

Flag at most; do not enforce.

**`real`, `a real X`, `the real problem`.** claudisms.ai calls this a preference, and in
technical prose it usually carries information no synonym does. Rewriting "collisions with
shorter IDs a real possibility" into "a possibility" understated the risk; "real temporary
directories" names genuine versus simulated. A third case is in `references/margins.md`.

**Concession and rebuttal.** A belief the reader may actually carry, stated in the reader's
own terms and then answered, is the backbone of a rationale document. It is not an invented
adversary, and it is usually the argument the paragraph exists to make.

Recognition test: **read the next three sentences. Do they give a reason the view is wrong
that a reader could check?** A mechanism, a measurement, a counterexample, or a rule all
count. If they do, keep the opening, and do not count it. What fires is the adversary raised
and dropped: a position stated so vaguely that nothing could rebut it (`critics argue`,
`some would say`, with no content), or one the document never returns to. A second question
separates them when the first is close: could a reader say whether they agree? `some people
will claim that having 8-character indentations makes the code move too far to the right` is a
position a reader can check against. `Some would say this is controversial` is not.

**What this test does not do.** It separates answered from unanswered, never real from
invented. A document that manufactures four adversaries and answers each with a measurement
clears completely, deliberately: no test a reader can run tells an invented belief from a
common one, and prose arguing a position with checkable reasons gives the reader what they
came for. If the opposition is fabricated **and** unanswered, the row above catches it; if
it is fabricated and answered, this skill does not, and does not pretend to.

Linux `coding-style.rst` at v5.15 opens five paragraphs this way; an earlier version ordered
all five deleted. They are kept in `tests/fixtures/ai-tell-audit/concession-rebuttal.rst`,
and the correct output on that file is zero edits.

**The em dash is a weak signal**: the most-cited tell anywhere and also the most defended,
since many humans have always used it heavily. claudisms.ai bans it, which is house style,
not evidence. A paragraph thick with em dashes is a prompt to read the prose, never a
finding. Same for emoji and for two dashes in a sentence.

## The catalogue

Rows, grouped by family. Every one is counted at 3 per document, and every one runs after
the exemption and rule zero. Density still applies. The headed structural families are
further down and are counted by a different rule.

### Placement and borrowed-domain metaphors
| Pattern | Disposition |
|-|-|
| `load-bearing` | Rewrite: "remove the ordering and the install breaks" |
| `lives` as a verb ("the risk lives in the parser"), `shape` as a noun ("the shape of the trend") | Rewrite: "is", "happens in", "structure", "direction" |
| `the engine`, `the physics of`, `turns on`, `compounds`, `compounding` | Rewrite: name the mechanism, "how it works", "depends on", "builds", "adds up" |
| `surface` as a verb; `hold`, `holding` a thought or a tension | Rewrite: "show", "report", "believing both at once" |
| `doing the work`, `doing the heavy lifting` | Rewrite: say what happens. Test: could a reader draw it? If a noun is employed in labour, no |
| Machinery given intent: software that notices, races, bites, wants, or goes quiet | Rewrite: give the action to whoever or whatever performs it. Test: can you point at the statement the verb describes? |

### Value-claim filler

Each tells the reader what to think before showing them anything.
| Pattern | Disposition |
|-|-|
| `worth noting`, `worth asking`, `worth considering`, any `worth [X]`, `the point is` | Delete |
| `Here's the thing:`, `Let that sink in.`, `Nobody talks about this.`, `Here's where it gets interesting` | Delete. No semantic content under any of them |
| `the right question`, `the right way`, `the right tool`, `a mature setup` | Rewrite: say why this one fits, or what the improved state does differently. Exempt when the sentence asks rather than asserts, whatever its punctuation |
| `useful`, `what's useful`, `this matters`, `and that matters` | Delete the bare label or assertion (`this is useful`, `and that matters`). Keep any use scoped to a named context, reader or noun: `X matters when Y`, `useful at this step`, `useful for debugging`, `useful display hooks`. The scope is the test, not the word |
| `It cannot be overstated`, `Great question`, a joke at the end of a section | Delete |

### Manufactured focal points
| Pattern | Disposition |
|-|-|
| `the whole game`, `the whole point`, `the entire X`, `the only thing that matters` | Delete the intensifier |
| `the only thing that changed`, `the only X that [verb]` | Rewrite: "what differed was Y". The singular claim is often false |
| `the most interesting part`, `the best thing you can do is`, `the one that pays off most` | Delete the judgement, or give the reason instead of the ranking |

**File-wide, for every table: the construction is the pattern, not the nouns.** `the whole
lesson` and `the whole job` are the same move as `the whole game` with a new word in the
slot; so are `the right thing to do` and `the right place to start` for `the right
question`. No text search catches them, which is why step 4 reads paragraphs.

### Knowing-narrator tics
| Pattern | Disposition |
|-|-|
| `quietly` ("quietly assumes context", "quietly dropped support") | Delete the adverb, or say what happened and who missed it |
| `a question we thought was settled`; `names`, `naming` as a verb | Rewrite: "this raises a new question about X", "says directly", "spells out" |
| `the tell`, `that's the tell`; `reaching for`, `reaches for` | Rewrite: say what the thing shows; "wants", "tries for" |
| `honestly`, `the honest version is`, false-modest asides ("I want to be careful here") | Delete. Qualifying your own claim implies the others were not qualified; the aside signals lean-out rather than care |

### Invented experience and unsourced claims

Softening does not fix these, so they delete. **The exception is concession and rebuttal**,
under Keep by default: a real view, stated plainly and then answered, is not invented
opposition and is not counted here.
| Pattern | Disposition |
|-|-|
| `most people I've talked to`, `everyone I've worked with`, `nobody I know` | Delete the sentence, or make the point with no population behind it |
| `in my experience, most teams`, `a lot of folks`, `critics argue`, `some would say`, unnamed opposition unanswered within three sentences | Rewrite: name them and link, or delete the sentence. Read the next three sentences first: if they give a reason the view is wrong, this row does not apply. That window is the same one Keep by default uses |
| A paragraph with no argument under it | Delete. Not rewritable |

### Corporate and consultant register
| Pattern | Disposition |
|-|-|
| `at the end of the day`, `lessons learned`, `paradigm shift`, `throughline` | Delete |
| `leverage`, `lean into`, `lean out`, `come along` as verbs | Rewrite: plain verb |
| `seat` as metaphor, `best operators`, `top practitioners`, `pressure-test`, `right-size`, `north star` | Rewrite: name the group plainly, "test", "resize", "goal" |
| `three things to know`, `key takeaways`, a tidy bullet summary at the end | Delete if it restates the body |
| `first wave of a multi-year transition`, `strategic imperative` | Rewrite: claim only what you can support |

### Generic AI vocabulary

Weaker signal: corpus studies of all models, not Claude specifically. Defaults, never proof.
| Pattern | Disposition |
|-|-|
| `delve`, `dive into` | Rewrite: "look at", or cut the throat-clearing sentence whole |
| `underscore`, `underscoring the importance of` | Delete the trailing clause |
| `robust`, `seamless`, `intricate`, `comprehensive`, `holistic` | Rewrite: say the property. "Robust" often means "handles bad input" |
| `transformative`, `game-changing`, `groundbreaking`, `cutting-edge`, `pivotal` | Delete, or state the role |
| `navigate`, `landscape`, `realm`, `testament`, `foster`, `harness`, `shed light on`, `pave the way` | Rewrite: "area", "field", "shows", "support", "use", "explain", "prepare for" |
| `When it comes to X` **as a sentence opener** (mid-sentence it is ordinary English), `At its core`, `This is where X comes in`, `Reflecting a broader trend toward` | Delete the opener |

### Structural tics

Weightier than any word row, because a structure repeats where a word does not.
| Pattern | Disposition |
|-|-|
| `not just X but Y`, `it isn't about X, it's about Y`, `No X. No Y. Just Z.` | Rewrite: drop the cleft, keep both claims as plain statements. In technical prose both halves are usually true, so do not discard one |
| One-sentence paragraphs throughout, four short declaratives in a row, or a rhetorical question you then answer | Rewrite: rejoin, join two, or make it a statement. Isolated ones are fine. Count the paragraphs before acting: the first fires only when under a quarter of them run to more than one sentence, since a document that mixes both lengths is varying its rhythm |
| A bolded term plus a colon plus an explanation on every bullet; `---` on its own line between sections | Rewrite: bold the two that need it or none; use a heading. Only when the `---` follows a blank line: directly under a line of text it is a setext H2 underline in Markdown, and deleting it silently demotes the heading |
| A bolded full-sentence declarative opening a paragraph, three times or more | Rewrite: unbold it and let the sentence carry itself, or promote it to a heading |
| `Let's explore`, `Now let's turn to`, announcing the structure, restating the question before answering it, `In today's rapidly evolving X` | Delete. Make the points |
| A closing one-liner restating the thesis, or a question to the reader | Delete. Sometimes a document just ends |
| Vague stakes ("the reckoning will come"), `the gap will become more visible` | Rewrite: name the event, or who is affected and what breaks |
| Catastrophizing verbs (`wreck`, `shatter`, `obliterate`) for a bounded effect | Rewrite: match the verb to the size |

## Structural families: what no word search catches

These are properties of how a sentence or a paragraph is built, so no table of strings
reaches them, and a pass that runs only the rows above will clear a document thick with
them. That has happened. Counts in `sources/EVIDENCE.md`.

**Step 5 is where the damage is prevented, and step 4 is where the finding is made.** Skipping
step 4 changed no verdict across a twelve-document corpus. Skipping step 5, the one-at-a-time
exemption call, damages human prose outright. The `names`/`naming` and `useful` rows stand far
over the figure of 3 in Linux's `coding-style.rst`, git's `CodingGuidelines` and PEP 465, and
every instance is literal (counts in `references/margins.md`). Step 5 is the only thing
standing between those documents and a rewrite. **The script cannot reach a verdict.**
`shortlist.py` covers two of the ten families and only the rows that are strings. Every family
below except the first two is found only by reading. A pass that runs the command and stops
has not audited anything; it has approved everything.

**Counting them.** A family fires at **4 or more surviving instances of one family in the
document** and **1 or more per thousand words**. Both figures. They cross at 4000 words, so
neither is idle: below that the floor of 4 binds, above it the rate does. The exemption and
rule zero run first here, and no construction is governed by both a row and a family.

**A worked example is not a licence**, and **no After invents or drops a fact.** The pairs
below show what a repair looks like, not an edit to make on a single instance: nothing is
edited until its family reaches both figures. Every after is reachable from its before by
plainer wording, or by deleting what the disposition says to delete. It introduces no number,
filename, measurement or name the before did not carry, and **drops no claim the before
made**: breaking a rule of three does not licence deleting its third item, and a rewrite that
loses a true claim is a failed rewrite by this file's own rule. If the plain version needs a
fact you do not have, the disposition is keep, not rewrite.

**Reading the script's output.** Its labels map to only two families. Every match is still only
a candidate: across the four revision-pinned human documents in `sources/EVIDENCE.md`, none was
a finding. `references/script-notes.md` has the label mapping, why the script unwraps the text
first, and the pass to run when you cannot run it at all.

### Negation-then-correction

**Recognition test.** Look at the negated half on its own. Can you point at it?
**Keep it** when the negated half is something named elsewhere in the document, or something
a reader could actually do or type. **It fires** when the negated half exists only to be
rejected: an abstraction that appears nowhere else (`a hunch`, `noise`, `a wish`,
`guesswork`), which leaves the positive half saying itself twice.
**Disposition.** Rewrite: keep the half that carries the claim and drop the other. Keep the
pair when both halves denote something concrete, which is the ordinary case in reference
prose and was 15 of 15 across the three revision-pinned documents.
**Before.** `Workers are scheduled on queue depth, not on guesswork.`
**After.** `Workers are scheduled on queue depth.`

### Comparative aphorism

**Recognition test.** The sentence ranks two things (`is worse than`, `is worth more than`)
or asserts an equivalence. Has the document measured the two sides, or shown one? If no
measurement, example, or consequence follows within a sentence or two, the ranking is
standing in for the argument the reader came for.
**Disposition.** Rewrite: give the consequence that makes one side worse, or delete the
sentence and let the example after it do the ranking.
**Before.** `A queue that silently drops jobs is worse than a queue that refuses them.`
**After.** `A queue that silently drops jobs gives the caller no error to handle; one that
refuses them does.`

### Rule of three

**Recognition test.** Count the items in each list and the parallel sentences in each
paragraph. Is three the count the subject has, or the count the sentence wanted? Was a
fourth dropped, or a second padded up? Three consecutive sentences opening on the same
subject are the same move at paragraph scale.
**Disposition.** Rewrite: give the count the subject has, and break one of the three
parallel sentences so the cadence stops.
**Before.** `The scheduler is fast, reliable, and easy to reason about.`
**After.** `The scheduler is fast and reliable, and it is easy to reason about.`

### Sentence-final restatement

**Recognition test.** Cover everything after the final comma or dash. Does the sentence
still make its claim? A trailing clause that re-says the main clause in other words has
added nothing. One that adds a condition or a cause has, so it stays.
**Disposition.** Delete the trailing clause. Rewrite instead when it carries a claim the
main clause does not.
**Before.** `The broker acknowledges only after the write commits, so an acknowledgement
means the write has committed.`
**After.** `The broker acknowledges only after the write commits.`

### Grand summary pivot

**Recognition test.** Does a sentence announce one unifying idea before giving it? Delete
the announcement and state the idea straight. What was lost?
**Disposition.** Delete the announcement and keep the idea as the sentence.
**Before.** `All of it comes down to one idea: every job must be safe to run twice.`
**After.** `Every job must be safe to run twice.`

### Question as heading

**Recognition test.** Is any heading a question the section then answers, and is it the
author's question rather than the reader's? The family is a document interviewing itself. A
rhetorical question inside a paragraph stays a row above, counted at 3.
**Exempt, and not counted:** an FAQ, a Q&A section, an interview transcript, a
troubleshooting list, and any run of headings a reader scans to find the question they
arrived with. Ask whose question it is: if a reader would type it into a search box, it is
theirs, and it stays (`Frequently Raised Objections` in PEP 572 is three of them).
**Disposition.** Rewrite the heading as the answer it gives.
**Before.** `Why does any of this matter for throughput?`
**After.** `How this matters for throughput`

### Knowing aside

**Recognition test.** A parenthetical or an adverb that comments on the sentence instead of
adding to it. Remove it: is any fact gone? If only a shared wink is gone, the narrator had
stepped into frame.
**Disposition.** Delete the aside, or rewrite it into the claim it hints at.
**Before.** `The default worker count will (inevitably) be wrong for your workload.`
**After.** `The default worker count will be wrong for your workload.`

### Self-certifying candour

**Recognition test.** Does the text label its own candour? Strip the label. Has anything
changed but the badge? A badge on one passage implies the surrounding text was not candid,
which is a claim the author did not mean to make.
**Disposition.** Delete the label and keep the caveat.
**Before.** `To be completely transparent, the throughput number came from a single run.`
**After.** `The throughput number came from a single run.`

### Repeated signature phrase

**Recognition test.** Does an unusual phrase appear more than once in one document? A phrase
a reader would quote back as characteristic is a signature; ordinary terms are not.
**Exempt, and not counted:** a term the document defines, and any term used in a consistent
technical sense. A specification that coins four terms and uses each twice is doing what a
specification is for, and varying them is the damage. Ask whether swapping in a synonym
would change what a reader has to look up: if it would, it is terminology. Each occurrence
after the first counts as one instance, so a phrase used twice is one.
**Disposition.** Rewrite the second occurrence in plain words, or delete it.
**Before.** `jobs go quiet on the wire ... later, the same jobs going quiet on the wire`
**After.** `jobs go quiet on the wire ... later, the same jobs stop acknowledging`

### Unsourced precision

**Recognition test.** Take every number in the draft. Where was it measured, and does the
document say? A number with a stated method or a linked run is fine; a number with `roughly`
in front of it and nothing behind it is decoration.
**Disposition.** Rewrite: give the method or the run that produced the number, or drop the
number and make the claim without it.
**Before.** `roughly 40% faster than the previous scheduler`
**After.** `faster than the previous scheduler`

## Trigger precision

<!-- routing-pin
description-sha256: da8d54d2cf19a14ccb134165a3f628111c6600bed4dbc83da776319678ada044
prompts-sha256: 7a6241737c1f04075950f822beb9cd0bd5f5df8427f55aae406f8f535db4a0b0
measured: 2026-09-01
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: partial 8/9 must-fire draws, 9/9 must-not-fire draws over 3 runs; not clean: 'Draft a comment on issue #40 explaining why we rejected the approach.' 2/3
-->

Must fire:

1. "Draft the release notes for v2.1, they go out to users today."
2. "Draft a comment on issue #40 explaining why we rejected the approach."
3. "Rewrite this README section so it doesn't sound machine-written."

Must NOT fire:

1. "Fix the typos and comma splices in the README before I merge." A genre plus a request for
   correctness: the precedence rule sends it to ordinary copy-editing.
2. "Add explanatory comments to this parser." Code comments are out of scope.
3. "Summarise what you found in the logs." A chat reply, not a published document.
