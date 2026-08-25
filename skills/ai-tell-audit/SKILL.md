---
name: ai-tell-audit
description: "Use when about to publish durable prose other people will read (a README, a GitHub issue or comment, a PR description, release notes, a changelog, a docs page, an announcement, a commit message body of several lines) to find where known Claude writing tells pile up and either rewrite them in plain words, delete them, or keep them, but NOT for chat replies, NOT for code comments, NOT for internal scratch notes, and NOT for ordinary grammar or house-style copy-editing."
---

# AI Tell Audit

**Catalogue reviewed 2026-08-25. Due for review 2027-02-25.** Past that date the rows
below are unchecked against three sources that all move. Run the refresh at the foot of
this file first; the check against the main source is a single command.

A find-and-fix pass over prose you are about to publish. The patterns are already known and published, so there is nothing to detect and no score to compute.

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

Apply the exemption first, then count. **The denominator is the prose you could edit**:
skip code fences, table cells, URLs, frontmatter, and everything rule zero skips.
Counting markup moves a rate by several per cent, which is enough to cross a threshold. **A surviving instance is non-literal, non-quoted,
and not a term of art.** Edit a pattern when it reaches **3 or more surviving instances in
one document**, however long: repeating one metaphor three times is the tic, and a rate
would hide it in a long file. Edit the document as a whole when surviving instances
**across all patterns reach 6 per thousand words**. Under both figures, fix only what is
plainly wrong.

Measured: four human documents totalling 19k words produced 33 raw matches and **0**
surviving, so none of them fires. A 3715-word machine-register file carries `load-bearing`
3 times, which fires on the first figure. A 264-word PR body at 76 per thousand fires on
the second.

The document-wide figure counts every surviving instance, string and structural alike.
The per-pattern figure of 3 counts strings only, because a row is a string. The families
below have no string to count and carry their own rule, stated with them.

## Never a verdict on authorship

Automated AI-writing detection is widely held to be pseudoscience: a 27-page human paper
scored 90% AI, a 2010 thesis scored 85%, with disproportionate harm to ESL and
neurodivergent writers. Nothing here measures authorship. **Use it on your own draft
before you publish**, never to assess who wrote something, never as input to a grade or a
moderation decision.

## Rule zero: never edit named or borrowed text

A document that *names* one of these patterns is not committing it. Skip, without
exception: quoted material, blockquotes, log output, error strings; banned-word lists,
style guides, a contribution guide under any of its spellings (`CONTRIBUTING.md`,
`CONTRIBUTE.md`), linter configs, this file; examples labelled as bad,
before/after pairs, test fixtures; code, code fences, identifiers (`surface()` is a
function name). The highest-hit file in the audit behind this skill was a `CONTRIBUTING.md`
with six hits, all inside its own list of forbidden words; editing it would have deleted
the guidance. If the text is mentioned rather than used, leave it alone.

## When this fires

The condition is observable: am I about to publish prose for other people to read? It does
not depend on judging whether the draft reads badly. Not for chat replies, code comments,
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
| A contrast whose negated half is a position nobody took | Rewrite: keep the half that carries the claim, drop the other |
| Three items, or three parallel sentences, where the subject has two | Rewrite: give the count the subject has |
| A trailing clause that re-says the main clause | Delete the clause |

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

Every row above is a word or a fixed phrase. The families here are properties of how a
sentence or a paragraph is built, so no table of strings reaches them, and a pass that
runs only the tables above will clear a document that is thick with them. That has
happened: the lexical tables cleared a 3046-word README, and two readers given only the
principle and no list then reported forty constructions in the same file.

**Counting them.** A family fires at **4 or more surviving instances of one family in
the document** and **2 or more per thousand words**. Both figures, so a 300-word note
with one contrast does not fire, and a long document cannot bury a tic in its length.
The exemption and rule zero run first here, as everywhere. A row in any table above
takes the per-pattern figure of 3, including the rows in the structural-tics table: a row
is a string, wherever it sits. Only the headed families below take the two figures here.

**Where the 2 comes from.** Four human technical documents totalling 21,926 words
(Linux `submitting-patches.rst`, git `CodingGuidelines`, curl `CONTRIBUTE.md`, sqlite's
"How SQLite Is Tested") produced 16 shortlist matches for the first family and, read one
by one, 1 surviving instance: 0.05 per thousand words. The README that the lexical
tables cleared produced 15 matches and 10 surviving, 3.3 per thousand. A threshold of 2
sits forty times above the measured human rate and below the document that failed.
Fifteen of the sixteen human matches were instructional contrasts of the form
`octal escape sequences, not hexadecimal`, which is why the first recognition test asks
what the negated half denotes instead of counting a word.

**A shortlist is not a detector.** Grep builds a reading list for the first family only:
`, not `, ` rather than `, `not only`, `isn't about`. Every match then has to be read,
because in the human corpus fifteen of sixteen were correct writing. The other families
have no shortlist at all; read the paragraph.

### Negation-then-correction

**Recognition test.** Delete the negated half. Does a claim disappear, or only a cadence?
The contrast survives when the negated half denotes something a reader could have taken
to be the case, or something the document considers elsewhere. It fires when the negated
half is a position nobody took and the positive half again in inverted words.
**Disposition.** Rewrite: keep the half that carries the claim and drop the other. Keep
the pair when the two halves denote different concrete things, which is the ordinary
case in reference prose.
**Before.** `Each one is here on evidence that the failure is common, not on a hunch.`
**After.** `Each one is here on evidence that the failure is common.`

### Comparative aphorism

**Recognition test.** The sentence ranks two things (`worse than`, `worth more than`,
`beats`) or asserts an equivalence (`A that does not look like B looks like C`). Has the
document measured the two sides? If no measurement, example, or consequence follows
within a sentence or two, the ranking is standing in for the argument.
**Disposition.** Rewrite: give the consequence that makes one side worse, or delete the
sentence and let the example after it carry the point.
**Before.** `Two skills racing for one trigger is worse than one skill.`
**After.** `When two skills match one trigger, the router loads whichever it reaches
first, so the newer one may never fire.`

### Rule of three

**Recognition test.** Count the items in each list and the parallel sentences in each
paragraph. Is three the count the subject has, or the count the sentence wanted? Ask
whether a fourth item was dropped or a second was padded up. Three consecutive sentences
opening on the same subject are the same move at paragraph scale.
**Disposition.** Rewrite: give the count the subject has, and break one of the three
parallel sentences so the rhythm stops.
**Before.** `a debugging sequence, a deploy-and-verify loop, or a non-obvious API dance`
**After.** `a debugging sequence or a deploy-and-verify loop`

### Sentence-final restatement

**Recognition test.** Cover everything after the final comma or dash. Does the sentence
still make its claim? A trailing `which is the only way that ...` or `so that ...` clause
that re-says the main clause in other words has added nothing; one that adds a condition
or a cause has.
**Disposition.** Delete the trailing clause. Rewrite instead when it carries a claim the
main clause does not.
**Before.** `Claims were checked against the filesystem, which is the only way that
failure is visible.`
**After.** `Claims were checked against the filesystem.`

### Grand summary pivot

**Recognition test.** Does a sentence announce one unifying idea before giving it
(`All of it serves one principle:`, `It comes down to this:`)? Delete the announcement
and state the idea straight. What was lost?
**Disposition.** Delete the announcement and keep the idea as the sentence.
**Before.** `All of it serves one principle: a skill has to earn its trigger.`
**After.** `A skill has to earn its trigger.`

### Question as heading

**Recognition test.** Is any heading a question the section then answers? The catalogue
already rewrites a rhetorical question inside a paragraph; a heading is the same move
with more weight, and a contents list built from them reads as an interview.
**Disposition.** Rewrite the heading as the answer it gives.
**Before.** `Does any of this actually pay off?`
**After.** `What the ledger showed after four weeks`

### Knowing aside

**Recognition test.** A parenthetical or an adverb that comments on the sentence instead
of adding to it (`(obligingly)`, `(predictably)`, `quietly`). Remove it: is any fact
gone? If only a shared wink is gone, the narrator had stepped into frame.
**Disposition.** Delete the aside, or rewrite it into the claim it hints at.
**Before.** `any agent will (obligingly) rubber-stamp the deletion`
**After.** `every agent asked to confirm the deletion confirmed it, in 9 of 9 runs`

### Self-certifying candour

**Recognition test.** Does the text label its own candour (`two honest caveats`,
`to be fair`, `abandon it honestly`)? Strip the label. Has anything changed but the
badge? A badge on one passage implies the surrounding text was not candid.
**Disposition.** Delete the label and keep the caveat.
**Before.** `Two honest caveats, because the sample is small.`
**After.** `Two caveats. The sample is nine runs.`

### Repeated signature phrase

**Recognition test.** Does an unusual phrase appear more than once in one document
(`six weeks later`, `the second occurrence`)? A phrase a reader would quote back as
characteristic is a signature; ordinary terms are not. Search the draft for its own
vivid phrases. Each occurrence after the first counts as one instance, so a phrase used
twice is one and seven phrases used twice are seven.
**Disposition.** Rewrite the second occurrence in plain words, or delete it.
**Before.** `fails six weeks later for everybody else ... a skill you wrote six weeks
ago`
**After.** `fails six weeks later for everybody else ... a skill you wrote in March`

### Unsourced precision

**Recognition test.** Take every number in the draft. Where was it measured, and does
the document say? `about 120 other skills were loaded` and `1 finding and 4`
are numbers with no instrument behind them. A number with a stated method or a linked
run is fine; a number with `about` in front of it and nothing behind it is decoration.
**Disposition.** Rewrite: give the method or the run that produced the number, or drop
the number and make the claim without it.
**Before.** `about 120 other skills were loaded in both arms`
**After.** `both arms ran the same skill install; the list is in the transcript linked
above`

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

A later pass found the opposite failure. The lexical tables alone cleared a 3046-word
README; two readers, each given the principle and no list of exclusions, reported forty
constructions in it, ten of them negation-then-correction and four comparative
aphorisms, the rest spread across the other families above. A catalogue of strings
cannot reach a property of sentence construction, which is what the structural section
exists for.

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

1. "Fix the grammar and comma splices in this post." Ordinary copy-editing. Just edit it.
2. "Add explanatory comments to this parser." Code comments are out of scope.
3. "Summarise what you found in the logs." A chat reply, not a published document.

## How to refresh the catalogue

Three sources feed this file and all three move. What each said at the last pull is
recorded here, so the next reader can tell whether anything has changed without reading
any of them.

| Source | Pulled | Version stamp at pull |
|-|-|-|
| `https://claudisms.ai`, a CC0 "living banlist" | 2026-08-25 | `updated` 2026-08-08, `count` 120 |
| Wikipedia, "Signs of AI writing" | 2026-08-25 | revision 1371235958 |
| Discussion boards, searched through `hn.algolia.com` | 2026-08-25 | no stamp; read for how a pattern is defended, not for new rows |

**The check.** Run `curl -s https://claudisms.ai/claudisms.json | jq -r '.updated, .count'`.
If it still prints `2026-08-08` and `120`, that source has not moved: write a new pair of
dates into the banner at the top of this file and stop. The whole refresh costs a second
when nothing has changed, which is what keeps six months usable as an
interval. Six months is a convention, not a measurement; the command above is the actual
trigger and can be run any day.

**The diff.** The 120 ids from the last pull are stored beside this file, one per line,
in `sources/claudisms-ids-2026-08-25.txt`. When the stamp has moved, run
`curl -s https://claudisms.ai/claudisms.json | jq -r '.terms[].id' | sort` and diff the
output against that file. The ids are stable, so the diff is exactly the entries added
and removed. Write the new list to `sources/claudisms-ids-<pull date>.txt` and leave the
old one in place, so the next reader inherits the same check. For Wikipedia, compare the section headings of
the current revision against the family headings in this file; a heading with no family
here is a candidate. Search discussion boards last, and only for how a pattern is
defended, because the density rules rest on that defence rather than on any pattern
being rare.

**A pattern that is newly common.** Add it only if it can occur in the genres this skill
declares, and only if no row already covers it under another wording. A lexical pattern
becomes a row in the table its family belongs to. A structural one has to arrive with a
heading, a recognition test phrased as a question a reader can answer, a disposition,
and a worked before and after, or it cannot be applied.

**A pattern that has gone stale.** Fading, not deleted: move it to the list below with
the date it was demoted, and treat it as flag-only from then on. Deleting a row loses
the record that the pattern was ever considered, and a later model generation can revive
one that faded.

**Fading, demoted 2026-08-25.** Several 2023-era markers, and `delve` with them. They
stay in the generic-vocabulary table, which already says that section is a weak signal.

Not carried from the CC0 source: the spoken-word section (cross-voice echo, sprinkled
disfluency, synthetic-speaker biography), which applies to audio scripts; two items its
author marked retired or house-specific (`stakes of their seat`, preferring "articles"
over "essays"); the outright bans on em dashes and emoji, demoted above; and about
twenty personal-essay tells that cannot occur in the declared genres: `sit with`,
`arriving at`, `where I landed`, `I can't stop thinking about`, `hit a nerve`,
`the thing that got me`, `in my chest`, `what stays yours`, `dispatches from`,
`bumped into`, `quieter`/`louder`, `carry this with you`, `rides along`,
`we've seen this movie before`, `hits hardest`, and the discovery-arc,
false-singularity and reader-direction families. For a personal essay, read the source
page.

Eight patterns are not on that page and came from independent review of human
discussion-board threads: one-sentence paragraphs, contentless openers and closers,
self-interviewing, argument-free fluff, unnamed critics, trailing engagement questions,
bare significance assertion, the section-ending joke. The ten structural families were
built from two independent reviews of one document, then checked against the Wikipedia
page, which carries the first family as "Negative parallelisms" and the third as
"Rule of three".
