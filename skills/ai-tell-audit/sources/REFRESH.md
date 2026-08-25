# Refreshing the catalogue

Read this when the review date in `SKILL.md` has passed, or when a new model
generation ships. It is not part of an audit: an audit fires on "about to publish",
this fires on a date, and keeping it out of `SKILL.md` keeps it out of every audit.

Three sources feed the catalogue and all three move. What each said at the last pull
is recorded here, so the next reader can tell whether anything has changed without
reading any of them.

| Source | Pulled | Version stamp at pull |
|-|-|-|
| `https://claudisms.ai/claudisms.json`, a CC0 "living banlist" | 2026-08-25 | `updated` 2026-08-08, `count` 120 |
| Wikipedia, "Signs of AI writing" | 2026-08-25 | revision 1371235958 |
| Discussion boards, searched through `hn.algolia.com` | 2026-08-25 | no stamp; read for how a pattern is defended, not for new rows |

## Fail closed, at every step

**An empty pull is not an empty banlist.** `curl -s <unreachable> | jq -r '.updated, .count'`
prints nothing and exits 0. Fall through to the diff on that and the empty list against
the 120-id snapshot reports every id as removed upstream, which would empty the
catalogue. Measured: 0 ids pulled, 120 reported removed.

So the pull is guarded, and every guard stops the pass rather than continuing with a
degraded answer:

    set -o pipefail
    curl -fsS https://claudisms.ai/claudisms.json -o pull.json || exit 1
    jq -e '(.updated|type=="string") and (.count|type=="number")
           and (.terms|type=="array") and (.terms|length) > 0
           and all(.terms[]; .id|type=="string")' pull.json > /dev/null || exit 1
    jq -r '.updated, .count' pull.json

**Stop and change nothing** if `curl` exits non-zero, if `jq -e` exits non-zero, if the
output is empty, or if `.count` disagrees with `(.terms|length)`. Record the date you
tried and the failure. A refresh that did not happen is a known state; a refresh that
half happened is not.

**If `.terms[].id` is gone**, the shape has changed and no substitute key may be
improvised: an id derived from a display string is unstable, so the next diff would
report churn that did not happen. Record the new shape in this file, rebuild the
snapshot from whatever stable key the source now offers, and diff nothing on this pass.

## The check

Run the guarded pull above. If it prints `2026-08-08` and `120`, that source has not
moved: write a new pair of dates into the banner at the top of `SKILL.md` and stop. The
refresh costs a second when nothing has changed, which is what keeps six months usable
as an interval. Six months is a convention, not a measurement; the command is the real
trigger and can be run any day.

## The diff

The 120 ids from the last pull are stored beside this file, one per line, in
`claudisms-ids-2026-08-25.txt`. When the stamp has moved:

    jq -r '.terms[].id' pull.json | sort > pulled-ids.txt
    diff claudisms-ids-2026-08-25.txt pulled-ids.txt

The ids are stable, so the diff is exactly the entries added and removed. Write the new
list to `claudisms-ids-<pull date>.txt` and leave the old one in place, so the next
reader inherits the same check.

For Wikipedia, compare the section headings of the current revision against the family
headings in `SKILL.md`; a heading with no family there is a candidate. Search discussion
boards last, and only for how a pattern is defended, because the density rules rest on
that defence rather than on any pattern being rare.

## What to do with what the diff shows

**A pattern that is newly common.** Add it only if it can occur in the genres the skill
declares, and only if no row already covers it under another wording. A lexical pattern
becomes a row in the table its family belongs to. A structural one has to arrive with a
heading, a recognition test phrased as a question a reader can answer, a disposition, and
a worked before and after, or it cannot be applied. Source the worked example from
somewhere other than a document the skill has been validated against.

**A pattern that has gone stale.** Fading, not deleted: move it to the list below with
the date it was demoted, and treat it as flag-only from then on. Deleting a row loses the
record that the pattern was ever considered, and a later model generation can revive one
that faded.

**Fading, demoted 2026-08-25.** Several 2023-era markers, and `delve` with them. They
stay in the generic-vocabulary table, which already says that section is a weak signal.

## What was never carried

Not carried from the CC0 source: the spoken-word section (cross-voice echo, sprinkled
disfluency, synthetic-speaker biography), which applies to audio scripts; two items its
author marked retired or house-specific (`stakes of their seat`, preferring "articles"
over "essays"); the outright bans on em dashes and emoji, demoted in `SKILL.md`; and
about twenty personal-essay tells that cannot occur in the declared genres: `sit with`,
`arriving at`, `where I landed`, `I can't stop thinking about`, `hit a nerve`,
`the thing that got me`, `in my chest`, `what stays yours`, `dispatches from`,
`bumped into`, `quieter`/`louder`, `carry this with you`, `rides along`,
`we've seen this movie before`, `hits hardest`, and the discovery-arc, false-singularity
and reader-direction families. For a personal essay, read the source page.

Eight patterns are not on that page and came from independent review of human
discussion-board threads: one-sentence paragraphs, contentless openers and closers,
self-interviewing, argument-free fluff, unnamed critics, trailing engagement questions,
bare significance assertion, the section-ending joke.

The ten structural families came from two independent reviews of one document, then
checked against the Wikipedia page, which carries the first as "Negative parallelisms"
and the third as "Rule of three".
