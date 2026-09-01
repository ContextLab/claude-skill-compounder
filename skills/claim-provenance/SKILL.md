---
name: claim-provenance
description: "Use when a claim already written down is checked or carried forward: checking every count and version in a README or doc still matches the repo before a push, a docs test green while the document it asserts is out of date, or a stated behavior nobody measured. Do NOT use for prose being drafted (`ai-tell-audit`), for a completion claim just made (`verification-before-completion`), for a value a function returns (`no-silent-stub`), or a run that may not contain your edit (`stale-artifact-check`)."
---

# Claim provenance

A claim is a sentence that some other commit could make false without touching the file it
sits in. Code has a compiler and a suite; a claim has neither, so it decays in place and
reads exactly as it did the day it was true. The failure is never that somebody lied. It is
that a number was restated from memory, or copied forward from an earlier version of
itself, and nothing between there and the reader ever asked the system again.

**This is not about writing a number well.** Sourcing a figure in prose you are drafting is
`ai-tell-audit`'s Unsourced precision, and it is better at it. This skill starts one step
later, with the number already on the page, and it is mostly about the check that agreed
with it: the test that asserts a document says something rather than that it is so.

## The Iron Law

```
RESTATE NOTHING. RE-DERIVE EVERY CLAIM FROM THE THING IT DESCRIBES, OR DELETE IT
```

## When this is the wrong skill

- **`stale-artifact-check`** answers a different, earlier question: *did the run I just
  observed contain my edit?* Ours is *does this sentence still match the system?* They
  compose rather than compete, and the order matters: if your re-derivation in Phase 3 runs
  code you edited this session, a stale artifact voids it. Run that skill first, then come
  back with an answer you can trust.
- **`no-silent-stub`** owns a **value a function hands a caller**; this skill owns a
  **sentence a reader reads**. The one place they touch is conceded, not argued away: a test
  scored against its own input is its territory, and Phase 5's presence-pinning assertion is
  the same shape, its expected value drawn from the same source as the actual. Two
  differences remain. First, its remedy is to make the code fail loudly; here nothing can be
  made to fail, because the assertion is correct code doing what it says, and the fix is to
  re-point it at the system. Second, only here does the assertion **entrench** the error, so
  that correcting the document turns the suite red. Precedence: writing the assertion now,
  either skill serves; auditing a green suite for assertions that lock a document's claims
  in place, this one.
- **`ai-tell-audit`** owns the draft you are writing now. Its "Unsourced precision" entry
  and this skill's Phase 4 are **not orthogonal, and the earlier claim here that they were
  was wrong**: for an unsourced number in fresh prose they are the same rule reached from
  two directions, and its version is the one to use. Two things are left uncovered, and they
  are why a boundary beats a merge: a claim with **no number in it** (a documented
  behavior), and a claim **already published and being carried forward**, with no draft to
  audit. Precedence, and it lives in the description because the router never reads this
  line: writing it, `ai-tell-audit`; checking what is already written, here.
- **`verification-before-completion`** (shipped by the `superpowers` plugin) is written for
  a **completion claim about work you just did**. This skill fires on a sentence that
  outlived the session that wrote it. **What is not true is that the other moment is
  covered**: that skill has been invoked 0 times in the local transcript corpus (source:
  `Skill` records under `~/.claude/projects`, as of 2026-08-26). Its wording is not the
  reason: the moment offers a router no user prompt to match, leaving only the assistant's
  own election. A `Stop`-hook gate for it is in progress and unproven
  (`notes/2026-08-25-completion-claim-gap.md`). Row 9 below is that unowned moment; rows 1
  through 8 are this skill's.
  **A commit message is not owned or disowned wholesale**, which is why the description does
  not name the genre. A completion claim inside one ("544 tests pass") is that unowned
  moment. A claim you copied into one out of a document is this skill's Phase 6. The genre
  never decides; what the sentence is doing decides.
- **Not a claim at all**: an instruction, a definition, an opinion, a plan. Apply the test
  at the top of Phase 1 before spending any time here.

## The nine, and what they have in common

One day's work in one repository. Every row shipped under a green suite.

|Where it lived|What it said|What was true|
|-|-|-|
|1. A rendered status bar|`12/12 100%`, bar full|the forge was still running, and step 14 of 12 rendered identically to step 12|
|2. The same status bar|a phase string, indistinguishable from a live one|the record's `updated` field was three hours old and was never rendered at all|
|3. A `SKILL.md`|a sweep found "103 skills and none of the ten in `~/.claude/skills`"|two of the ten are real directories, and the sweep finds them|
|4. A `SKILL.md`|"across the eight forges this repository has run"|the ledger held three|
|5. A correction of row 4|a smaller number|the ledger's own second line contradicted the correction|
|6. A field's documentation|`rounds` records the planned budget|it records completed rounds on `fail`; the doc described a bug already fixed|
|7. Four files and `CONTRIBUTING.md`|broken frontmatter loads with empty metadata and never fires|it loads with name and description intact and fires; the real failure is narrower and quieter|
|8. A runner's failure line|`SOME TESTS FAILED`|the flag was set without naming the file, so the claim shipped without its own derivation and two sessions could not reproduce it|
|9. A commit message|"544 tests pass"|the tree it described failed one|

**Source, as of 2026-08-25:** all nine were found in this repository, in its working
tree, its git history, and the forge ledger at `~/.claude/skill-compounder/ledger.jsonl`,
except row 9, whose commit was never merged into any branch. `git log --all` does not
list it; it survives only as an unreachable object: `git show 204acb0` prints it, with
"544 tests pass" in its body, and `git fsck --unreachable --no-reflogs` lists it (plain
`--unreachable` can omit it while a reflog entry still reaches it; both measured
2026-08-25, and a `git gc` prune can end even that).
For you they are bucket B, because you cannot re-derive them from where you sit, and the
line you are reading is the source and the as-of date that Phase 4 requires of a bucket B
claim. A table of evidence that skipped its own Phase 4 would be the tenth row.

**The through-line: the check agreed with the state, instead of the state being right.**
Not one of these is a defect in code. Every one is a defect in a stated reason.

## Phase 1: Inventory the claims

Do this on the document you are auditing, and on any paragraph you edited. Substitute your
document for `README.md` in every command below. The placeholder is a real filename on
purpose: a literal `<the file>` inside `$( )` is a syntax error at the `|`. bash 5.3 and
zsh 5.9 refuse the line with a nonzero exit; macOS's `/bin/bash` 3.2 reports the error,
substitutes nothing, exits 0, and appends your inventory to `/tmp/claims-.tsv`, a path
shared with every audit that made the same mistake (all three measured 2026-08-25).

**The test for whether a sentence is a claim**, applied one sentence at a time:

> Could a commit elsewhere in this repository make this sentence false without touching
> this file?

Yes means it is a claim and it needs provenance. No means it is an instruction, a
definition or an opinion, and this skill has nothing to say about it.

Five shapes carry almost all of them. Read for these, then read again for the rest:

- **Counts and measurements.** Any digit. Also any number spelled as a word.
- **Universals.** `none`, `all`, `every`, `only`, `never`, `always`, `cannot`, `no other`.
  A universal is the most expensive shape here, because one counterexample kills it and
  rows 3 and 7 above were both universals.
- **Named behavior.** "X does Y", "if you do X then Y happens", the documented meaning of
  a field or a flag.
- **Names, paths and versions.** A path that moved, a flag that was renamed, a version.
- **Comparatives against a past state.** "this used to", "we fixed", "unlike before".

On a change you just wrote, this narrows the reading:

```bash
git diff HEAD -U0 | grep -E '^\+[^+]' | grep -iE '[0-9]|\b(none|all|every|only|never|always|cannot)\b'
git ls-files --others --exclude-standard | xargs grep -niE '[0-9]|\b(none|all|every|only|never|always|cannot)\b' /dev/null
```

Both lines are load-bearing and each replaces a version that read clean while missing
things. `HEAD` is there because plain `git diff` goes **empty the moment you `git add`**,
and by the time you come back to audit a change you have usually staged it: an empty sweep is
indistinguishable from a clean bill of health, which is this skill's own subject. The
second line is there because a brand-new untracked file is a place claims live and
`git diff` never mentions it. The trailing `/dev/null` keeps `grep` off your terminal when
nothing is untracked. Neither is scoped to markdown, because a test assertion and a commit
message are claims too. The first line sweeps your whole change on purpose; auditing one
document on a dirty tree, scope it with a pathspec, `git diff HEAD -U0 -- README.md`,
because unscoped it returns every hunk in the repository (79,617 bytes on this one while
fifteen files were modified: `git diff HEAD -U0 | wc -c`, as of 2026-08-25) and the
claims you are auditing drown in hunks that are not yours.

**Both of those read a change, and the commoner case here is a document nobody changed
today.** On an unmodified tracked file they print nothing, and nothing is exactly what a
clean bill of health looks like. Measured on this repository, as of 2026-08-31: the diff
sweep over `skills/contribute-skill/SKILL.md` matched 0 lines while the same pattern over the
whole file matched 116. So when the document is not part of your diff, sweep the file:

```bash
grep -nEi '[0-9]|\b(none|all|every|only|never|always|cannot)\b' README.md
```

Use the diff sweeps when you are auditing a change you made, and this one when you are
auditing a document that was already there. Auditing a change to a document that was
already there needs both.

None of the three is a detector; they are reading aids. None can see a behavior claim
written in plain words, which is the shape that cost the most above, so none ends the
phase.

Write the inventory down outside the repository, one line per claim. Name it after the
document's **path**, not a fixed path and not its basename, and make the path absolute:
`a/SKILL.md` and `b/SKILL.md` share a basename, `SKILL.md` is what this skill audits most
often, and every repository has a `README.md`, so a name built from the relative path
alone lets a second audit, in this checkout or a concurrent session's other one, append
to the first one's list. `$PWD` is what makes the name yours.

```bash
printf '%s\t%s\t%s\n' "<claim>" "<bucket>" "<command or source>" >> "/tmp/claims-$(echo "$PWD"/README.md | tr / -).tsv"
```

## Phase 2: Sort by re-derivability

For each claim, write down the command that would produce it. That single act sorts it.

**Bucket A: re-derivable now**, by a command you can name and run in this session.
Counts (`wc -l`, `find ... | wc -l`, a `jq` over a ledger), presence (`test -e`), the
result of the suite (run it), the behavior of code in this tree (execute it). Go to
Phase 3. "I counted it an hour ago" is not bucket A: you have been editing since.

**Bucket B: re-derivable, but not from here.** A measurement on hardware you do not have,
another repository, an external service's behavior, a run that has already happened. It is
bucket B only if you can name the source you actually read. A source you believe exists is
bucket C.

**Bucket C: not re-derivable at all.** You cannot name any command, file or document that
would produce it. It came from memory. Go to Phase 4 and delete it.

Two rules that decide most of the hard cases:

- **A hedge does not move a claim from C to B.** "roughly eight" and "eight" are the same
  claim wearing different confidence. Row 4 above was wrong either way.
- **A true claim whose source will move under you is B, not A.** Re-deriving a count once
  does not make it stay counted. Either it carries its as-of date and its command, or the
  better move: put the **command** in the document instead of the number. A sentence that
  says "run `X` for the current count" cannot go stale, and it costs the reader one line.

## Phase 3: Re-derive, and read what came back

1. **Run the command. Keep the output.** Not a similar command; the one that produces this
   claim. **The trap is that a similar command returns a number, and a number ends the
   search.** Worked, from this file: the bucket A example in Phase 4 read *"this repository
   ships 10 seed skills"* behind `find skills -maxdepth 2 -name SKILL.md | wc -l`. The count
   was right and the noun was wrong. That command counts `SKILL.md` files; *seed skill* is a
   narrower term this repository defines elsewhere, in the README's seed-pool table, which
   had five rows (`git show 40babc1:README.md`, as of 2026-08-25). That row count is a past
   state, so it is bucket B: it carries the source that reproduces it instead of being
   re-derived from today's README. A fourth reviewer found the noun, and the test that was
   supposed to guard the claim had locked the wrong quantity in place. So before you accept
   the output, say out loud what the command counted, and check that it is the noun in your
   sentence.
2. **The claim is what the command printed**, not what you expected it to print. Where they
   differ the command wins and the sentence is what changes. Rows 6 and 7 above were both
   discovered exactly here, by someone who expected agreement.
3. **Derive from the system, never from another document.** A second file repeating the
   first is not corroboration; it is the same claim twice. Row 7 was four files and a
   `CONTRIBUTING.md` in perfect agreement, all tracing to one assertion nobody had measured.
4. **For a behavior claim, the derivation is an executed one.** Build the smallest artifact
   that exhibits the behavior, run the real consumer against it, and record the output
   verbatim. Grepping the docs for the behavior is Phase 3 step 3's failure, restated.
5. **A correction is a claim and it re-enters Phase 1.** Row 5 above is a correction that
   was itself wrong, and it was wrong against a file that was open at the time.

## Phase 4: Dispose of what you could not re-derive

|Bucket|Disposition|What the sentence looks like after|
|-|-|-|
|A|Re-derive; put the command beside the number|"this repository ships 10 `SKILL.md` files under `skills/` (`find skills -maxdepth 2 -name SKILL.md \| wc -l`, as of 2026-08-26)"|
|A, but the source moves|Replace the number with the command|"run `find skills -maxdepth 2 -name SKILL.md \| wc -l` for the current count"|
|B|Keep it, with its source and its as-of date|"measured on claude 2.1.245: the description listed as the H1"|
|C|Delete the claim and write the sentence without it|"we fixed this in three places" becomes "we fixed this"|

**Deleting is a legitimate outcome, and usually the cheapest one.** A sentence that
survives the deletion of its number was never about the number. Reach for deletion first
and keep the figure only when the reader would act differently for knowing it.

**Then fix every copy.** A behavior claim usually lives in more than one file, and fixing
one leaves the others to re-infect the next reader:

```bash
grep -rn 'empty metadata' --exclude-dir=.git .
```

Do not scope that to markdown. The copy that outlives a fix is the one in a test, a
docstring or a fixture, where nobody thinks to look for prose.

**Then delete the inventory**, on the way out of a pass that succeeded and not only one
that failed: `rm -f "/tmp/claims-$(echo "$PWD"/README.md | tr / -).tsv"`. A list of
claims left at a predictable path is a document making claims of its own, and the next
session has no way to tell which pass it belongs to.

## Phase 5: The test trap, presence against truth

`assertIn("103 skills", text)` and an assertion that checks the count is right look
identical on the page, and both stay green forever. One of them pins the claim's
**presence**. The other pins its **truth**.

**The recognition test, and it costs a minute.** Do not read the assertion. Move the world
underneath it, in two steps, and watch which way it goes.

|Move|Truth-pinning assertion|Presence-pinning assertion|
|-|-|-|
|1. Make the claim false **without touching the document**: change the system it describes, on a scratch copy or a branch|red|green|
|2. Then **correct the document** so it matches the system again|green|red|

Step 1 is the diagnosis: an assertion that does not notice the system moving was never
about the system. Step 2 is the bill. **Presence-pinning is worse than no test, because it
inverts the incentive**: once `assertIn("103 skills", text)` exists, correcting the document
is what turns the suite red, so the next session's cheapest path is to leave the false claim
alone. The assertion has become the reason the error survives. Name it out loud: *an
assertion that makes the truth expensive.*

**Put the system back.** Move 1 edits the thing the claim describes, not the document, so
the unhappy path below does not cover it: `git checkout HEAD -- .` in a scratch clone, or
delete the directory you added. Do move 1 on a copy and there is nothing to undo.

An assertion green through both moves is not testing the claim at all. One red through both
pins presence and truth together, which is acceptable only if you accept editing the test
every time the fact legitimately moves.

**The fix, by shape:**

1. **The document states a count of things in the repository.** Parse the number out of the
   prose, derive the same number, compare:

   ```python
   claimed = int(re.search(r"(\d+) skills are installed", text).group(1))
   actual = len(list(root.glob("*/SKILL.md")))
   self.assertEqual(claimed, actual)
   ```

   Adding a skill now turns the suite red on its own, and correcting the prose turns it
   green again. That is both rows of the table, the right way round.
2. **The document states a behavior.** The test performs the behavior, asserts the observed
   result, and separately asserts that the document's stated result matches what was
   observed. It never asserts the sentence.
3. **The document states something in bucket C.** There is nothing to assert, so the
   assertion should not exist. Delete both, the claim and the test.
4. **You genuinely need a string to be present.** Assert **structure**, not fact.
   `assertIn("## Trigger precision", text)` is a structural assertion and is fine forever.
   The discriminator is the Phase 1 test: a heading does not change when the system changes,
   and a count does.

## Phase 6: Claims you are only copying forward

The commonest source of a false claim is not writing one. It is editing the paragraphs
around somebody else's.

- **Every claim in a paragraph you touched re-enters Phase 1**, whether or not you wrote
  it. Renaming, moving and reformatting all count: the diff shows you touched it.
- **A claim's presence in the file is not evidence for it.** It was written by somebody who
  is not here, and it has had the whole history of the repository to go wrong.
- **A claim you are about to quote into a commit message, an issue or a report is a new
  claim**, even verbatim, because you are the one shipping it this time.

### Unhappy path: what a half-finished pass leaves

A document in a mixed state, some claims re-derived and some not, with nothing on disk
marking which. That is worse than never starting, because the next reader sees a file that
has visibly been audited. To recover, do one of two things and say which in your reply:

```bash
git diff HEAD -- README.md          # read back every paragraph you touched, staged or not
git checkout HEAD -- README.md      # or discard the pass entirely: destructive, see below
```

`HEAD` is not decoration in either line. **`git checkout -- <file>` does not revert a
staged modification**: it exits 0, prints nothing, and leaves the half-finished pass
exactly where it was, which is the failure this section exists to prevent. `git checkout
HEAD --` resets the index and the working tree together. It also destroys uncommitted
work that has nothing to do with this pass, so if anything else in the file is unsaved,
that is `destructive-op-preflight`'s subject and it runs before you type this.

Then delete the Phase 1 inventory (`rm -f "/tmp/claims-$(echo "$PWD"/README.md | tr / -).tsv"`),
or it becomes a stale artifact making claims of its own. Never leave a partial pass unannounced.

## Red flags

Each of these means stop and go back to Phase 1:

- "That number was right last time I looked."
- "It is in the README, so it must be right."
- "I will just put 'roughly' in front of it."
- "The test is green, so the document is right."
- "I am only reformatting this section."
- "Four files say the same thing, so it is well established."
- "I know how this works." (Then name the command that shows it.)
- "Correcting it would break a test." (That is the entrenchment, out loud.)
- "It is only a commit message, nobody re-reads it." (Which is the problem.)
- "The exact number does not matter here." (Then delete it.)

## Common rationalizations

|Excuse|Reality|
|-|-|
|"I counted this earlier in the session."|You have been editing the tree since. Bucket A means re-derive now, not once.|
|"Adding 'roughly' makes it safe."|A hedge changes the confidence, not the claim. Row 4 was wrong either way.|
|"The suite passes, so the document is checked."|Move the system so the claim is false and leave the document alone. If the suite stays green, it was checking the string and never the fact.|
|"Correcting the doc would break a test, so the doc is probably right."|That is the entrenchment stated as a reason. The assertion is the defect; re-point it at the system.|
|"Four files agree, so it is established."|One unmeasured claim copied four times. Corroboration is a second derivation, never a second copy.|
|"I did not write the claim, it was already there."|You are shipping it. A claim in a paragraph you touched is yours now.|
|"It is a commit message, not documentation."|If it is a completion claim, the skill that names that moment has never fired on it (see the boundary section), so verify it yourself. If you copied it out of a document, it is Phase 6, and it is now the least-edited prose in the repository.|
|"There is no command that produces this number."|Then it is bucket C. Delete it; the sentence usually reads better without.|
|"I re-derived it, so the document is durable."|Only until the source moves. Give it an as-of date, or ship the command instead of the number.|
|"The correction is obviously right."|A correction is a claim. Row 5 was a correction contradicted by the second line of the file it was correcting.|

## Trigger precision

The rule the prompts below exercise: Use when a claim already written down is checked or
carried forward: a count or behavior restated from a document, a behavior nobody
measured, or a test asserting what a document says rather than whether it is true, which
beats `no-silent-stub`. The description restates this in the router's vocabulary, because
the router reads nothing else; the pin records that wording's measurement.

<!-- routing-pin
description-sha256: 9d480e2d11caf9fb99a3746bdaca048b40dbb5a110b3e5f8554fee1981ce3f91
prompts-sha256: 1e763f03fd8b977bc88c973a2df89bb6b533a07eca5b34669bd7c3e304f70744
measured: 2026-08-31
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: partial 8/9 must-fire draws, 9/9 must-not-fire draws over 3 runs; not clean: 'Our CONTRIBUTING page says broken frontmatter makes a skill load with empty metadata. Has anyone actually measured that, or did we copy it forward?' 2/3
-->

Prompts that MUST fire this skill:

1. "Update the README's architecture section, and check every count and version in it still matches the repo before I push."
2. "Our docs tests are green but the architecture document is out of date. How is that passing?"
3. "Our CONTRIBUTING page says broken frontmatter makes a skill load with empty metadata. Has anyone actually measured that, or did we copy it forward?"

Prompts that must NOT fire this skill:

1. "Write the release notes for v2.1 and I'll ship them today." (Fresh prose whose figures
   need sourcing, which `ai-tell-audit` owns. This skill starts once they are published and
   someone is checking them.)
2. "Refactor this 300-line function into smaller ones."
3. "This test fails with a `KeyError` on line 42. Work out why."

## Quick reference

|Phase|Action|Done when|
|-|-|-|
|1. Inventory|Ask of each sentence whether another commit could falsify it; sweep the five shapes; write the list down outside the repo|Every claim in the draft is on the list|
|2. Sort|Name the command that would produce each one|Each claim is A, B or C, and a hedge moved nothing|
|3. Re-derive|Run it, keep the output, believe the output; derive from the system, never from a second document|The sentence matches what the command printed|
|4. Dispose|Command beside the number, or command instead of the number, or source plus as-of date, or delete|No claim left with no provenance; every copy fixed|
|5. Tests|Move the system so the claim is false, then correct the document; re-point every assertion that did not notice|No assertion in the suite makes correcting a document expensive|
|6. Copy-forward|Re-run Phase 1 over every paragraph you touched, including ones you only reformatted|Nothing shipped that you inherited unchecked|
