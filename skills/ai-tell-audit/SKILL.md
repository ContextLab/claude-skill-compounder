---
name: ai-tell-audit
description: "Use when about to publish durable prose other people will read (a README, a GitHub issue or comment, a PR description, release notes, a changelog, a docs page, an announcement, a commit message body of several lines) to find where known Claude writing tells pile up and either rewrite them in plain words, delete them, or keep them, but NOT for chat replies, NOT for code comments, NOT for internal scratch notes, and NOT for ordinary grammar or house-style copy-editing."
---

# AI Tell Audit

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

Apply the exemption first, then count. **A surviving instance is non-literal, non-quoted,
and not a term of art.** Edit a pattern when it reaches **3 or more surviving instances in
one document**, however long: repeating one metaphor three times is the tic, and a rate
would hide it in a long file. Edit the document as a whole when surviving instances
**across all patterns reach 6 per thousand words**. Under both figures, fix only what is
plainly wrong.

Measured: four human documents totalling 19k words produced 33 raw matches and **0**
surviving, so none of them fires. A 3715-word machine-register file carries `load-bearing`
3 times, which fires on the first figure. A 264-word PR body at 76 per thousand fires on
the second.

## Never a verdict on authorship

Automated AI-writing detection is widely held to be pseudoscience: a 27-page human paper
scored 90% AI, a 2010 thesis scored 85%, with disproportionate harm to ESL and
neurodivergent writers. Nothing here measures authorship. **Use it on your own draft
before you publish**, never to assess who wrote something, never as input to a grade or a
moderation decision.

## Rule zero: never edit named or borrowed text

A document that *names* one of these patterns is not committing it. Skip, without
exception: quoted material, blockquotes, log output, error strings; banned-word lists,
style guides, `CONTRIBUTING.md`, linter configs, this file; examples labelled as bad,
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

### Placement and borrowed-domain metaphors
| Pattern | Disposition |
|-|-|
| `load-bearing` | Rewrite: "remove the ordering and the install breaks" |
| `lives` ("the risk lives in the parser"), `shape` ("the shape of the trend") | Rewrite: "is", "happens in", "structure", "direction" |
| `the engine`, `the physics of`, `turns on`, `compounds`, `compounding` | Rewrite: name the mechanism, "how it works", "depends on", "builds", "adds up" |
| `surface` as a verb; `hold`, `holding` a thought or a tension | Rewrite: "show", "report", "believing both at once" |
| `doing the work`, `doing the heavy lifting` | Rewrite: say what happens. Test: could a reader draw it? If a noun is employed in labour, no |

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
| One-sentence paragraphs throughout, four short declaratives in a row, or a rhetorical question you then answer | Rewrite: rejoin, join two, or make it a statement. Isolated ones are fine |
| A bolded term plus a colon plus an explanation on every bullet; `---` between sections | Rewrite: bold the two that need it or none; use a heading (Markdown only) |
| `Let's explore`, `Now let's turn to`, announcing the structure, restating the question before answering it, `In today's rapidly evolving X` | Delete. Make the points |
| A closing one-liner restating the thesis, or a question to the reader | Delete. Sometimes a document just ends |
| Vague stakes ("the reckoning will come"), `the gap will become more visible` | Rewrite: name the event, or who is affected and what breaks |
| Catastrophizing verbs (`wreck`, `shatter`, `obliterate`) for a bounded effect | Rewrite: match the verb to the size |

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

## The list decays, and what is not in it

Several 2023-era markers are stale and `delve` is fading with them. The catalogue was
taken from **https://claudisms.ai** on 2026-08-25, a maintained CC0 page describing itself
as "a living banlist" that "grows as new ones are caught". Fetch it again before trusting
this file on a new model generation.

Not carried from that source: the spoken-word section (cross-voice echo, sprinkled
disfluency, synthetic-speaker biography), which applies to audio scripts; two items its
author marked retired or house-specific (`stakes of their seat`, preferring "articles"
over "essays"); the outright bans on em dashes and emoji, demoted above; and about twenty
personal-essay tells that cannot occur in the declared genres: `sit with`, `arriving at`,
`where I landed`, `I can't stop thinking about`, `hit a nerve`, `the thing that got me`,
`in my chest`, `what stays yours`, `dispatches from`, `bumped into`, `quieter`/`louder`,
`carry this with you`, `rides along`, `we've seen this movie before`, `hits hardest`, and
the discovery-arc, false-singularity and reader-direction families. For a personal essay,
read the source page.

Eight patterns are not on that page and came from independent review of human
discussion-board threads: one-sentence paragraphs, contentless openers and closers,
self-interviewing, argument-free fluff, unnamed critics, trailing engagement questions,
bare significance assertion, the section-ending joke.
