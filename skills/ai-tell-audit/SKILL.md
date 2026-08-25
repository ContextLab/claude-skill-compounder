---
name: ai-tell-audit
description: "Use when about to publish durable prose other people will read (a README, a GitHub issue or comment, a PR description, release notes, a changelog, a docs page, an announcement, a commit message body of several lines) AND the request is about how the prose reads. A request to fix grammar, typos, spelling or house style in one of those genres is copy-editing and does NOT fire; the request decides, not the file. NOT for chat replies, NOT for code comments, NOT for scratch notes."
---

# AI Tell Audit

**Catalogue reviewed 2026-08-25. Due for review 2027-02-25.** Past that date the rows
below are unchecked against three sources that all move. Run `sources/REFRESH.md` first;
its guarded check against the main source is a single command.

A find-and-fix pass over prose you are about to publish. The patterns are already known and published, so there is nothing to detect and no score to compute.

## The pass, in order

Two sessions given only a catalogue invent two different sequences. This is the sequence.

1. **Decide from the request, not the file.** The genres are in the description; the
   precedence rule is under `When this fires`. If the request is copy-editing, stop here.
2. **Mark the skip regions.** Rule zero, below, before anything is counted or read.
3. **Count the denominator.** `python3 shortlist.py <file>` prints the editable word
   count. Every rate in this file divides by that number.
4. **Build the reading list.** The same command prints the greppable shortlist with
   paragraphs unwrapped. The other eight families have no shortlist, so read each
   paragraph once, in order, asking that family's recognition test of it. The list is
   complete when every paragraph has been read once: there is no search to exhaust, and
   a family with no candidate is recorded as zero rather than as unchecked.
5. **Apply the exemption to each match, one at a time.** A match is a candidate, never a
   finding. In the human corpus none of the sixteen was a finding.
6. **Count what survives**, three ways: per pattern, per family, and document-wide.
7. **Apply the thresholds.** Only a pattern or family at or over its own threshold
   produces an edit. Nothing else is edited, however the document reads.
8. **Edit or report.** Edit in place when the user handed you the document to publish;
   return a list when they asked what you found. If the request says neither, ask before
   writing.

**Output contract.** Whatever the mode, the reply carries: the editable word count; every
pattern and family that fired, with its count and its rate; every edit as a before and an
after; and one line for what was left alone and why. A pass that fired nothing says so
and changes nothing, which is a result and not a failure.

## Literal and terminological use is exempt, everywhere

**Every row in this file is a rule about metaphor. None fires on the literal sense, on a
term of art, or on markup the format requires.** File-wide, so no row repeats it. Four
cases that broke earlier versions:

- `harness` is banned as a corporate verb. A `test harness` is a term of art: sqlite's
  testing page uses it 22 times and needs zero edits.
- `the entire X` is an empty intensifier. `the entire filesystem` names a scope.
- `robust` is an empty adjective. `robust against malicious attack` carries a claim that
  contrasts with "robust in normal use", and flattening it loses the contrast.
- `---` is an AI section divider in Markdown. In reStructuredText it underlines a heading.

When a word carries information no plain synonym carries, keep it, and do not count it.

## Density is the finding

**One instance of a listed pattern is usually fine, and often it is good writing.** Nearly
every pattern below is defended by someone as legitimate craft, and they are right. What
no one defends is the pile-up. A reconciling comment from a discussion board: "Most of
these are valid and useful framing devices... it should, and has been, used in moderation,
which LLMs absolutely do not do."

Apply the exemption first, then count. **The denominator is `python3 shortlist.py <file>`**,
not an estimate: counted by eye, two sessions differ by tens of per cent, and the rate is
what decides. It excludes code fences, indented code, inline code, URLs, frontmatter,
table rows and heading underlines. Headings are prose: counted, and editable. Excluded
regions are excluded from **editing** as well as from counting, except table cells, which
are not counted (their register is not prose) but may be edited once a pattern has fired
somewhere else in the document. **A surviving instance is non-literal, non-quoted,
and not a term of art.** Edit a pattern when it reaches **3 or more surviving instances in
one document**, however long: repeating one metaphor three times is the tic, and a rate
would hide it in a long file. The document as a whole is a finding when surviving
instances **across all patterns reach 6 per thousand words**, even when no single pattern
does: the pile-up is spread rather than concentrated. **The narrower rule always wins.**
A spread finding never licenses editing an instance whose own pattern or family is under
threshold; what it licenses is the note. Say the count, the rate, and the three heaviest
families, and hand it back. Under every figure, fix only what is plainly wrong.

Measured, on one pinned pull (2026-08-25) of four human documents at 21,926 words
raw and **20,099 editable**, which is the denominator every rate in this file uses:
Linux `submitting-patches.rst` at 83f71fbc66fb, git `CodingGuidelines` at 570e1e0d0ff6,
curl `CONTRIBUTE.md` at 7e1001bcd699, and sqlite's "How SQLite Is Tested", which carries
no revision id. 271 raw matches, **0** surviving, so none of them fires. 227 of the 271
are `---` under an RST heading, 11 are `harness`, and both are exempt before any count.
The closest call is `useful` five times in one Linux document, over the per-pattern
figure of 3: every one is scoped ("useful at this step"), which that row's own keep clause
covers. That is what applying the exemption first buys.

Two other figures in this file, a 3715-word machine-register file carrying `load-bearing`
3 times and a 264-word PR body at 76 per thousand, come from documents that are not in
this repository and are **not reproducible from it**. They are recorded as history, not as
evidence.

The document-wide figure counts every surviving instance, row and family alike. The
per-pattern figure of 3 governs a **row**, whether the row gives a string or describes a
construction. The **headed families** below carry their own two figures. No construction
is governed by both: a family has no row, and a row has no family.

## Never a verdict on authorship

Automated AI-writing detection is widely held to be pseudoscience: a 27-page human paper
scored 90% AI, a 2010 thesis scored 85%, with disproportionate harm to ESL and
neurodivergent writers. Nothing here measures authorship. **Use it on your own draft
before you publish**, never to assess who wrote something, never as input to a grade or a
moderation decision.

## Rule zero: never edit named or borrowed text

A document that *names* one of these patterns is not committing it. Skip, without
exception: quoted material, blockquotes, log output, error strings; banned-word lists,
style guides, linter configs, this file; examples labelled as bad, before/after pairs,
test fixtures; code, code fences, identifiers (`surface()` is a function name).

**Skip the region, not the file.** A contribution guide under any of its spellings
(`CONTRIBUTING.md`, `CONTRIBUTE.md`, `CodingGuidelines`) is skipped **where it lists
forbidden words or quotes a bad example**, and audited in its own prose like anything
else. Reading the filename as a whole-file exemption would void the audit before it
started, and would exempt exactly the documents this skill is most often pointed at. The
highest-hit file in the audit behind this skill was a `CONTRIBUTING.md` with six hits,
all inside its own list of forbidden words; editing those would have deleted the
guidance, and editing its surrounding prose would have been an ordinary audit. If the
text is mentioned rather than used, leave it alone.

## When this fires

The condition is observable: am I about to publish prose for other people to read? It does
not depend on judging whether the draft reads badly.

**Precedence: the request decides, not the file.** A genre from the description is
necessary and never sufficient, because the two halves of the trigger overlap on purpose.
"Fix the typos in the README before I merge" gives a genre and asks for correctness, so
the copy-editing clause wins and this does not fire. "The README reads like a machine
wrote it" gives the same genre and asks about how it reads, so it fires. A drafted
announcement fires; the chat message announcing it does not, because the artifact that
gets published is the draft. When both clauses match and the request is genuinely
unclear, ask. Never edit somebody's prose on a guess about what they meant. Not for chat replies, code comments,
scratch notes, one-line commit subjects, or grammar and house-style copy-editing. Two edge
calls: an internal team wiki page is durable prose other people read, so it fires; "this
section sounds stilted, tighten it" fires only when it names a genre above, since bare
"tighten this" is copy-editing.

## Three dispositions

**Rewrite** when the sentence makes a claim: say the same claim in plain words.
**Delete** when the pattern carries no claim: "It is worth noting that X" means X.
**Keep** when the plain version would lose information, when the usage is literal rather
than metaphorical, or when the instance is isolated. Keep is a first-class outcome; a pass
that changes nothing on a good document succeeded.

**A rewrite that changes what the sentence claims is a failed rewrite.** If the plain
version cannot state the same claim, keep the original. **Vary the repairs.** Turning every em dash into a colon swaps one tic for another. No
substitution twice in a row: six dashes get a period, a comma, a parenthesis, a rebuilt
clause, a colon, and one dash kept.

## Fast path

For a GitHub comment, a PR description, or anything short. Density still applies.
The headed structural families are deliberately not summarised here: they are counted by
a different rule, and a row that repeated one would give a hurried reader a second,
looser threshold for the same construction.

| Tell | Fix |
|-|-|
| `load-bearing` | Rewrite: name what depends on what |
| `quietly` | Delete the adverb, or say who missed it |
| `reaching for`, `reaches for` | Rewrite: "tries for", "wants" |
| `worth [X]`, all of it | Delete. "Worth noting that X" is X |
| `the tell`, `that's the tell` | Rewrite: say what the thing shows |
| `lives`, `shape`, `surface` as a verb | Rewrite: "is", "structure", "report" |
| `delve`, `dive into` | Rewrite: "look at", or cut the sentence whole |
| `robust`, `seamless`, `comprehensive` | Rewrite: name the property |
| `underscoring the importance of` | Delete the trailing clause |
| `not just X but Y` and other clefts | Rewrite: drop the cleft, keep both claims plainly |
| `Here's the thing:`, `Let that sink in.`, `Nobody talks about this.` | Delete. No content |
| One-sentence paragraphs throughout | Rewrite: rejoin into real paragraphs |
| A bolded lead-in on every bullet | Rewrite: bold the two that need it, or none |
| A rhetorical question you then answer | Rewrite as a statement |
| A trailing engagement question | Delete |
| `Most people I've talked to`, `everyone I've worked with` | Delete the sentence. You cannot name and link people you did not talk to |
| `Some would say`, `critics argue`, any unnamed opposition | Rewrite: name them and link, or delete the sentence |

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
| `useful`, `what's useful`, `this matters`, `and that matters` | Delete the bare label or assertion. Keep `X matters when Y`, which scopes a claim rather than asserting one |
| `It cannot be overstated`, `Great question`, a joke at the end of a section | Delete |

### Manufactured focal points
| Pattern | Disposition |
|-|-|
| `the whole game`, `the whole point`, `the entire X`, `the only thing that matters` | Delete the intensifier |
| `the only thing that changed`, `the only X that [verb]` | Rewrite: "what differed was Y". The singular claim is often false |
| `the most interesting part`, `the best thing you can do is`, `the one that pays off most` | Delete the judgement, or give the reason instead of the ranking |

The construction is the pattern, not the nouns: `the whole lesson` and `the whole job` are the same move with a new word in the slot, and no text search catches them.

### Knowing-narrator tics
| Pattern | Disposition |
|-|-|
| `quietly` ("quietly assumes context", "quietly dropped support") | Delete the adverb, or say what happened and who missed it |
| `a question we thought was settled`; `names`, `naming` as a verb | Rewrite: "this raises a new question about X", "says directly", "spells out" |
| `the tell`, `that's the tell`; `reaching for`, `reaches for` | Rewrite: say what the thing shows; "wants", "tries for" |
| `honestly`, `the honest version is`, false-modest asides ("I want to be careful here") | Delete. Qualifying your own claim implies the others were not qualified; the aside signals lean-out rather than care |

### Invented experience and unsourced claims

Softening does not fix these, so they delete.
| Pattern | Disposition |
|-|-|
| `most people I've talked to`, `everyone I've worked with`, `nobody I know` | Delete the sentence, or make the point with no population behind it |
| `in my experience, most teams`, `a lot of folks`, `critics argue`, `some would say`, any unnamed opposition | Rewrite: name them and link, or delete the sentence |
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

Weaker signal: corpus studies of all models, not Claude specifically. Defaults to avoid, never proof.
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
| A bolded term plus a colon plus an explanation on every bullet; `---` between sections | Rewrite: bold the two that need it or none; use a heading (Markdown only) |
| A bolded full-sentence declarative opening a paragraph, three times or more | Rewrite: unbold it and let the sentence carry itself, or promote it to a heading |
| `Let's explore`, `Now let's turn to`, announcing the structure, restating the question before answering it, `In today's rapidly evolving X` | Delete. Make the points |
| A closing one-liner restating the thesis, or a question to the reader | Delete. Sometimes a document just ends |
| Vague stakes ("the reckoning will come"), `the gap will become more visible` | Rewrite: name the event, or who is affected and what breaks |
| Catastrophizing verbs (`wreck`, `shatter`, `obliterate`) for a bounded effect | Rewrite: match the verb to the size |

## Structural families: what no word search catches

Every row above is a row: a string, or one named construction, counted at 3 per document.
The families here are properties of how a sentence or a paragraph is built. No table of
strings reaches them, and a pass that runs only the tables above will clear a document
that is thick with them. That happened: the lexical tables cleared a 2356-word README,
and two readers given only the principle and no exemptions reported forty constructions
in the same file.

**Counting them.** A family fires at **4 or more surviving instances of one family in the
document** and **1 or more per thousand words**. Both figures. They cross at 4000 words,
so neither is idle: below that the floor of 4 binds, above it the rate does. The
exemption and rule zero run first here, as everywhere, and no construction is governed by
both a row and a family.

**A worked example is not a licence.** The before and after under each family show what
the repair looks like. They are not edits this file endorses making on a single instance.
Nothing is edited until its family reaches both figures.

**Where the figures come from.** Four human technical documents, pinned at the revisions
in the density section, come to 20,099 editable words. `shortlist.py` finds 16 candidate
matches in them. Read one by one, **0 surviving instances: 0.0 per thousand words**.
Fifteen are instructional contrasts of the form `octal escape sequences, not hexadecimal`,
where both halves are things a reader could type; the sixteenth is a grep artefact. The
README those tables cleared has 2356 editable words and the same 16 candidate matches,
of which 4 survive: 1.7 per thousand. So negation-then-correction fires there and
comparative aphorism does not, standing at 3 against a floor of 4. The document-wide
figure in the density section fires as well, which is what a spread pile-up looks like.

**A shortlist is not a detector.** `python3 shortlist.py <file>` prints the
editable word count and the candidate matches for the two greppable families, with
paragraphs unwrapped first. Unwrapping is load bearing in two directions: this
repository hard wraps at about 90 characters, so `is worth` and `more than a proposal`
fall on separate lines where no line-based grep sees them, while a phrase straddling a
blank line is two paragraphs and must never match. The script joins the first and keeps
the second apart, and reports each match at the line it starts on. Every match still has to be
read, because in the human corpus none of the 16 was a finding. The other eight families
have no shortlist at all: read the paragraphs.

### Negation-then-correction

**Recognition test.** Look at the negated half on its own. Can you point at it? It
survives when the negated half is something named elsewhere in the document, or something a
reader could actually do or type. It fires when the negated half exists only to be
rejected: an abstraction that appears nowhere else (`a hunch`, `noise`, `a wish`,
`guesswork`), which leaves the positive half saying itself twice.
**Disposition.** Rewrite: keep the half that carries the claim and drop the other. Keep
the pair when both halves denote something concrete, which is the ordinary case in
reference prose and was 15 of 16 in the human corpus.
**Before.** `Workers are scheduled on queue depth, not on guesswork.`
**After.** `Workers are scheduled on queue depth.`

### Comparative aphorism

**Recognition test.** The sentence ranks two things (`is worse than`, `is worth more
than`) or asserts an equivalence. Has the document measured the two sides, or shown one?
If no measurement, example, or consequence follows within a sentence or two, the ranking
is standing in for the argument the reader came for.
**Disposition.** Rewrite: give the consequence that makes one side worse, or delete the
sentence and let the example after it do the ranking.
**Before.** `A queue that silently drops jobs is worse than a queue that refuses them.`
**After.** `A dropped job leaves no record, so the caller waits forever; a refused job
returns an error the caller can handle.`

### Rule of three

**Recognition test.** Count the items in each list and the parallel sentences in each
paragraph. Is three the count the subject has, or the count the sentence wanted? Was a
fourth dropped, or a second padded up? Three consecutive sentences opening on the same
subject are the same move at paragraph scale.
**Disposition.** Rewrite: give the count the subject has, and break one of the three
parallel sentences so the cadence stops.
**Before.** `The scheduler is fast, reliable, and easy to reason about.`
**After.** `The scheduler dispatches in under a millisecond, with one queue per priority.`

### Sentence-final restatement

**Recognition test.** Cover everything after the final comma or dash. Does the sentence
still make its claim? A trailing clause that re-says the main clause in other words has
added nothing. One that adds a condition or a cause has, so it stays.
**Disposition.** Delete the trailing clause. Rewrite instead when it carries a claim the
main clause does not.
**Before.** `The broker acknowledges only after the write commits, which is the only way
durability is guaranteed.`
**After.** `The broker acknowledges only after the write commits.`

### Grand summary pivot

**Recognition test.** Does a sentence announce one unifying idea before giving it? Delete
the announcement and state the idea straight. What was lost?
**Disposition.** Delete the announcement and keep the idea as the sentence.
**Before.** `All of it comes down to one idea: every job must be safe to run twice.`
**After.** `Every job must be safe to run twice.`

### Question as heading

**Recognition test.** Is any heading a question the section then answers? A rhetorical
question inside a paragraph stays a row above, counted at 3; this family is headings only,
because a contents list built from questions reads as an interview and the two are not
the same construction.
**Disposition.** Rewrite the heading as the answer it gives.
**Before.** `Why does any of this matter for throughput?`
**After.** `What queue depth does to throughput`

### Knowing aside

**Recognition test.** A parenthetical or an adverb that comments on the sentence instead
of adding to it. Remove it: is any fact gone? If only a shared wink is gone, the narrator
had stepped into frame.
**Disposition.** Delete the aside, or rewrite it into the claim it hints at.
**Before.** `The default worker count will (inevitably) be wrong for your workload.`
**After.** `The default worker count is 4, which is too low above 200 jobs a second.`

### Self-certifying candour

**Recognition test.** Does the text label its own candour? Strip the label. Has anything
changed but the badge? A badge on one passage implies the surrounding text was not candid,
which is a claim the author did not mean to make.
**Disposition.** Delete the label and keep the caveat.
**Before.** `To be completely transparent, the throughput number came from a single run.`
**After.** `The throughput number came from a single run.`

### Repeated signature phrase

**Recognition test.** Does an unusual phrase appear more than once in one document? A
phrase a reader would quote back as characteristic is a signature; ordinary terms are not.
Search the draft for its own vivid phrases. Each occurrence after the first counts as one
instance, so a phrase used twice is one and seven phrases used twice are seven.
**Disposition.** Rewrite the second occurrence in plain words, or delete it.
**Before.** `jobs go quiet on the wire ... six paragraphs later, the same jobs going quiet
on the wire`
**After.** `jobs stop acknowledging ... six paragraphs later, the same jobs time out`

### Unsourced precision

**Recognition test.** Take every number in the draft. Where was it measured, and does the
document say? A number with a stated method or a linked run is fine; a number with
`roughly` in front of it and nothing behind it is decoration.
**Disposition.** Rewrite: give the method or the run that produced the number, or drop the
number and make the claim without it.
**Before.** `roughly 40% faster than the previous scheduler`
**After.** `12,000 jobs a second against 8,500, from bench/throughput.sh on one 8-core
machine`

## Keep by default

Flag at most; do not enforce.

**`real`, `a real X`, `the real problem`.** claudisms.ai calls this a preference, and in
technical prose it usually carries information no synonym does. Three cases broken by
rewriting: "your real name (sorry, no pseudonyms)" lost its requirement as "your actual
name"; "collisions with shorter IDs a real possibility" became "a possibility" and
understated the risk; "real temporary directories" names genuine versus simulated.

**The em dash is a weak signal**, the most-cited tell on discussion boards and also the
most defended, since many humans have always used it heavily. claudisms.ai bans it; that
is house style, not evidence. A paragraph thick with em dashes is a prompt to read the
prose, never a finding. Same for emoji and for two dashes in a sentence.

## Worked example

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

Four human regression documents, all damaged by earlier versions: Linux
`submitting-patches.rst`, git `CodingGuidelines`, curl `CONTRIBUTE.md`, sqlite's "How
SQLite Is Tested". Each must come out with zero edits. sqlite is the hardest: `harness`
appears 22 times as a term of art, which without the exemption is maximal density aimed
straight at the damage.

## Trigger precision

Must fire:

1. "Write the release notes for v2.1 and I'll ship them today."
2. "Draft a comment on issue #40 explaining why we rejected the approach."
3. "Rewrite this README section so it doesn't sound machine-written."

Must NOT fire:

1. "Fix the typos and comma splices in the README before I merge." Gives a genre, asks
   for correctness: the precedence rule sends it to ordinary copy-editing.
2. "Add explanatory comments to this parser." Code comments are out of scope.
3. "Summarise what you found in the logs." A chat reply, not a published document.

## How to refresh the catalogue

The procedure moved to `sources/REFRESH.md`, with the source table, the guarded pull, the
120-id diff, and the rules for a pattern that is newly common or fading. It fires on a
date, not on "about to publish", so keeping it there keeps it out of every audit.

Read it when the review date in the banner has passed, or when a new model generation
ships. It fails closed at every step: an unreachable source stops the pass rather than
reporting the whole catalogue as retired upstream.
