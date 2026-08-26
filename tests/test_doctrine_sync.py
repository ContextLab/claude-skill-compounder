#!/usr/bin/env python3
"""The forging doctrine is stated in three places. They must not drift apart.

`.claude/CLAUDE.md` carries the rule in prose: "Its doctrine is mirrored in README.md and
in the user's global ~/.claude/CLAUDE.md stanza. Changing the protocol means updating all
three." That rule has been violated twice, both times the same way: the skill changed and
the prose describing it did not, so the README documented a round cap and a duration
threshold the skill no longer had. A fresh session reading the README would have applied
a rule that does not exist.

WHAT THIS FILE ENFORCES, AND WHAT IT DOES NOT.

There are two kinds of assertion here and they are worth different amounts.

1. Derived facts. A number, a filename, an environment variable, an exit status, a table
   row: extracted from the deliverable (`skills/skill-compounder/SKILL.md`), from the
   scripts (`hooks/*.sh`, `statusline/*.sh`), or from RUNNING `bin/skillforge`, then
   compared against what the docs write down. These are decidable. Nothing about them
   requires reading a sentence for meaning, and they catch the drift that actually
   happened: a cap that moved in one file and not another.

2. Doctrine. Rules that are not values and have no "current setting" to derive -- the
   red-teamer is never a fork, the orchestrator never closes the forge, and so on. These
   are pinned as EXACT SENTENCES in `DOCTRINE` below, and each mirror must contain its
   sentence verbatim -- whitespace collapsed and markdown emphasis stripped, with the
   text a reader cannot read (HTML comments, strikethrough) removed before the search, so
   that a rule cannot be repealed by hiding the sentence rather than deleting it.

Pinning the literal in a test is the opposite of what rule 1 does, and it is deliberate.
A round cap is a setting; it is expected to change, so the test derives it. A doctrine
rule is an invariant of the design; changing one should require editing this file, in a
commit where a reviewer can see it happen.

THREE EARLIER VERSIONS OF THIS FILE TRIED TO ENFORCE DOCTRINE BY READING PROSE, and each
was defeated on first contact by a fresh reviewer. Not by a bug in a pattern -- by a
rewording. `not .{0,20}a fork` certified "does not have to be a fork". A rewrite that
split prose into clauses and demanded the negation govern the verb was beaten by "There
is no fork restriction", by the inflections `forked` and `forks`, by pronoun subjects, by
an exemption clause that used the exemption's own words to hand the rule away, and by
"drive the whole thing itself" in place of the scanned verb `runs`. Each round ended with
the author reporting that every counterexample now failed, which was true only of the
counterexamples already tried. A scanner for "does this paragraph MEAN the rule" is
deciding a question about natural language, and the set of paraphrases is not finite, so
the arms race has no terminating round. That machinery is gone. It was reporting safety it
did not provide, which is worse than reporting none.

So, explicitly, THE HOLES THAT REMAIN OPEN BY DESIGN. Do not re-open the arms race to
close them; a reviewer who finds one has found a documented limit, not a defect:

  - A document may carry its pinned sentence and REPUDIATE it in the next paragraph
    ("that was the old rule, and it was wrong"). Nothing here can tell doctrine from a
    paragraph about doctrine. This is measured, not predicted: a cold reviewer given only
    these documents and this file reversed every rule pinned at the time -- eight of
    them -- that way in a single pass, with the suite at exit 0. Read that as the ceiling on what this file is worth. It
    stops drift and deletion. It does not stop an author who means to reverse a rule, and
    no test of prose can.
  - A document may carry its pinned sentence and state the opposite elsewhere, in any
    wording. Only the pinned sentences are read.
  - Only the rules in `DOCTRINE` are pinned at all. Every other sentence in these
    documents can be inverted freely, and the same reviewer did invert a dozen of them.
    Adding a rule here is cheap; the list is a floor that grows, not a claim of coverage.
  - Whoever changes a rule may change the pinned sentence here to match. That is the
    point: it makes the change visible in the diff, not impossible.
  - The user's global `~/.claude/CLAUDE.md` stanza is the third mirror named in the rule
    quoted above. It is hand-maintained on each machine and this repo neither ships nor
    installs it, so nothing here can check it. The repo's own `.claude/CLAUDE.md` is what
    is checked.

`<!-- doctrine: <id> -->` anchors mark the pinned sentences in the two documents that
state the doctrine at length. They render as nothing, and they tell a human editing the
paragraph that the next sentence is pinned verbatim. `.claude/CLAUDE.md` is a condensed
stanza and carries the sentences without anchors.
"""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / "skills" / "skill-compounder" / "SKILL.md").read_text()
README = (ROOT / "README.md").read_text()
REPO_CLAUDE = (ROOT / ".claude" / "CLAUDE.md").read_text()
HOOK = (ROOT / "hooks" / "compound-improvement.sh").read_text()
DESIGN = (ROOT / "docs" / "DESIGN.md").read_text()
# Both files under `docs/` are scanned for retired wording and for forge state
# filenames. The split between them is enforced by `tests/test_docs_split.py`; a
# claim that migrates from one to the other must not escape these checks on the way.
PLATFORM = (ROOT / "docs" / "CLAUDE-CODE-BEHAVIOR.md").read_text()

# Every shipped script, concatenated. A cold reviewer defeated the two assertions below by
# documenting `STATUSLINE_SPINNER_MS`, a variable nothing reads: they scanned the hook and
# `statusline.sh` only, and skipped any row whose name did not start with `CI_`. Read the
# whole of what ships instead, so a row for an imaginary knob has nowhere to hide.
SCRIPTS = "".join(f.read_text() for d in ("bin", "hooks", "statusline")
                  for f in sorted((ROOT / d).iterdir()) if f.is_file())

# The forging protocol only. Assertions about it must not be satisfiable by a stray match
# in Troubleshooting further down the file -- that is exactly how the first version of
# `test_the_single_forge_constraint_is_stated` came to pass against text that predated it.
_forging = re.search(r"### Forging protocol.*?(?=\n## )", SKILL, re.S)
assert _forging, "SKILL.md no longer has a parseable '### Forging protocol' section"
FORGING = _forging.group(0)

# Vars matching these are deliberately undocumented: they exist so tests can pin
# nondeterminism, and the repo names them by convention (CI_NOW, INSIGHT_NOW,
# SKILLFORGE_NOW, CI_DEBUG_DUMP, INSIGHT_DEBUG_DUMP). See CLAUDE.md, "No mocks, ever".
PIN = re.compile(r"_(NOW|DEBUG_DUMP)$")

# The progress bar as `statusline/skillforge-status.sh` actually draws it. Hardcoding the
# glyphs was defeated: the class was `[█·]`, the renderer also emits `▓` for the partly
# filled cell, and a README example written with `▓` was invisible to the budget check that
# claims to read every bar. Derive the set from the renderer's own `bar="${bar}<glyph>"`.
_glyphs = set(re.findall(r'bar="\$\{bar\}(.)"',
                         (ROOT / "statusline" / "skillforge-status.sh").read_text()))
assert _glyphs, ("skillforge-status.sh no longer builds its bar with `bar=\"${bar}<glyph>\"`, "
                 "so nothing here knows which characters a README example may use")
BAR = re.compile("▕[%s]+▏ (\\d+)/(\\d+)" % "".join(sorted(_glyphs)))

SKILL_PATH = "skills/skill-compounder/SKILL.md"
MIRRORS = {SKILL_PATH: SKILL, "README.md": README, ".claude/CLAUDE.md": REPO_CLAUDE}

# Where an anchor comment is required alongside the sentence. `.claude/CLAUDE.md` is
# excluded on purpose: see the module docstring.
ANCHORED = (SKILL_PATH, "README.md")


def flatten(text):
    """Line wrapping collapsed and every `*` deleted; nothing else.

    Deleting every asterisk is blunter than "strip markdown emphasis" -- it also eats a
    literal `*` in prose -- and it is deliberate: a rule about which asterisks are emphasis
    is a rule about markdown parsing, and no pinned sentence contains one.

    A pinned sentence is a sentence, so it wraps differently in a 90-column README than in
    an indented list item, and it may be bolded in one file and plain in another. Those are
    the only two differences tolerated. Every other character has to match, which is what
    makes the comparison decidable rather than a judgement about wording.
    """
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


COMMENT = re.compile(r"<!--.*?-->", re.S)
STRIKE = re.compile(r"~~.*?~~", re.S)


def visible(text):
    """`flatten`, minus the text a reader does not read.

    A substring check is satisfied by a sentence nobody can see, and markdown offers two
    ways to leave one on the page while repealing it. `<!-- The red-teamer must never be a
    fork ... -->` renders as nothing at all; `~~The red-teamer must never be a fork ...~~`
    renders struck through, which is how a document says "this used to be the rule". Both
    passed the first version of the presence check below, both were found by attacking it,
    and both are removed here rather than matched, because removal needs no judgement about
    what the surrounding prose intends.
    """
    return flatten(COMMENT.sub(" ", STRIKE.sub(" ", text)))


ANCHOR = "<!-- doctrine: %s -->"

# ---------------------------------------------------------------------------------------
# The pinned doctrine. Each entry is (id, exact sentence, files that must carry it).
#
# To change a rule: change the sentence here and in every file listed, in one commit. To
# retire a rule: delete the entry AND the anchors, and say in the commit message why the
# invariant no longer holds. Both are meant to be visible, not difficult.
# ---------------------------------------------------------------------------------------
DOCTRINE = (
    ("no-forked-reviewer",
     "The red-teamer must never be a fork of either layer — not of the orchestrator that "
     "dispatches it, and not of the session that dispatched the orchestrator.",
     (SKILL_PATH, "README.md", ".claude/CLAUDE.md"),
     "A fresh reviewer is the one thing the loop cannot work without: a fork already knows "
     "what the skill was meant to say."),

    ("orchestrator-runs-the-rounds",
     "The session that starts a forge does not run it.",
     (SKILL_PATH, "README.md"),
     "The loop moved off the main thread so review traffic stops landing in the user's "
     "context. A README that does not say so teaches the old shape."),

    ("close-ownership",
     "You own `start`, `done` and `fail`; the orchestrator owns everything between.",
     (SKILL_PATH, "README.md"),
     "Exactly one party may close a forge; the CLI discards the second close at exit 0."),

    ("orchestrator-does-not-close",
     "The orchestrator calls neither `done` nor `fail`.",
     (SKILL_PATH,),
     "The same rule named from the other side. A rule that only says someone does not "
     "close the forge can be read either way."),

    ("no-leading-prompt",
     "Never hand a reviewer a list of what not to flag.",
     (SKILL_PATH, "README.md"),
     "A brief that pre-classifies the allowed cases returns your own judgement with a "
     "second name on it."),

    ("neutral-retirement-question",
     'Ask a second fresh agent the neutral question, "should this be kept, fixed, or '
     'retired?", never "confirm this deletion".',
     (SKILL_PATH, "README.md"),
     "The retirement check has the same shape as the red-team check, and a leading prompt "
     "defeats both."),

    ("archive-the-source",
     "Archive the source, not the link.",
     (SKILL_PATH, "README.md"),
     "Skills are symlinks into a checkout: moving the link leaves the real directory for "
     "the next install to resurrect, and writes the tombstone into live source."),

    ("both-conditions",
     "Both must hold, or it gets a note rather than a skill.",
     (SKILL_PATH, "README.md"),
     "Costly OR recurring says yes to nearly any non-trivial work, and a threshold that "
     "always resolves to yes is worse than none."),

    ("invoke-do-not-reimplement",
     "If a plausible skill exists, invoke it. Do not reimplement.",
     (SKILL_PATH,),
     "The first of the three standing habits. Without it the package forges skills nobody "
     "then reaches for."),

    ("announce-the-forge",
     "The user must never discover a forge after the fact.",
     (SKILL_PATH,),
     "A forge spends subagent rounds on the user's behalf; doing that unannounced is the "
     "thing that makes the machinery feel like it is running away with the session."),

    ("fresh-reviewer-each-round",
     "Spawn a new red-teamer each round; the whole test depends on the reader being "
     "genuinely cold.",
     (SKILL_PATH,),
     "After round one the previous reviewer is no longer cold, so reusing it is the fork "
     "problem with extra steps."),

    ("narrow-or-abandon-at-the-cap",
     "If it is not clean at the cap, do not ship a half-working skill: narrow its scope "
     "until it is clean, or abandon it.",
     (SKILL_PATH,),
     "A cap with no consequence is not a cap; without this the loop just runs longer."),

    ("no-silent-workaround",
     "Never silently work around a skill that misfired.",
     (SKILL_PATH, "README.md"),
     "The workaround costs the same time again in every future session, and nothing "
     "records that the skill is broken."),

    ("never-rm-rf",
     "Never `rm -rf` a skill.",
     (SKILL_PATH, "README.md"),
     "Retirement can be wrong, so it has to be recoverable."),

    ("routing-gate-on-completion",
     "A forge cannot be reported clean while the skill's own must-fire prompts do not "
     "fire it.",
     (SKILL_PATH, "README.md"),
     "Every seed skill passed a full red-team loop on a `## Trigger precision` section "
     "nobody ran; three of the claims were then false. A reviewer agreeing a description "
     "reads well is not a measurement of the router."),

    ("must-not-half-is-a-gate",
     "A skill that fires on everything is worse than no skill.",
     (SKILL_PATH, "README.md"),
     "Half a routing gate is not a gate: a skill that wins every prompt displaces the "
     "neighbour that would have handled it, which is the failure `stale-artifact-check` "
     "suffered from the other side."),

    ("unmeasured-is-not-verified",
     "A probe that could not run is never a pass.",
     (SKILL_PATH, "README.md"),
     "Without this the gate degrades to nothing the first time there is no auth or no "
     "quota: an unrun probe silently promoted to verified is the exact record this gate "
     "exists to end."),

    ("highest-applicable-level",
     "A skill belongs at the highest level of the hierarchy to which it applies, and must "
     "be written generally enough to apply beyond the case that prompted it.",
     (SKILL_PATH,),
     "Placement decided by where the file happened to be written is how a procedure that "
     "generalises ends up locked to one repository."),

    ("specialisation-not-baked-in",
     "The specialisation comes from the project's or the user's `CLAUDE.md` and the "
     "constraints already recorded there — never from text baked into the skill.",
     (SKILL_PATH,),
     "The other half of the placement rule. Without it, `highest-applicable-level` is "
     "satisfied by a general skill with one repository's test command hardcoded in it."),

    ("d-infers-the-scenario",
     "D is given the skill and nothing else, and must infer for itself what situation the "
     "skill is for.",
     (SKILL_PATH,),
     "The inference IS the completeness check: a skill carrying a reference only its "
     "author can resolve produces an inference that is vague, wrong, or impossible. Hand "
     "the reviewer a scenario and that signal is gone."),

    ("e-checks-the-framing",
     "Ask E whether A's framing matches the trigger it came from.",
     (SKILL_PATH,),
     "Everything after step 1 inherits A's framing, including E's own question about "
     "whether the original issue was fixed. Only a verbatim trigger held independently of "
     "A's account of it can surface a misframing."),

    ("concurrent-forges",
     "Concurrent forges are fine — each gets its own record and its own slot in the status "
     "line, and starting one never disturbs another.",
     (SKILL_PATH,),
     "The retired doctrine told a session to check for a live forge and wait. It now pays "
     "for a collision that cannot happen."),
)


class DoctrineMirrorTest(unittest.TestCase):
    """Each pinned sentence, verbatim, in each file that must carry it.

    This checks MIRRORING, not meaning. A file that carries its sentence and contradicts it
    two paragraphs later passes, and no assertion in this class is a claim otherwise. What
    it does catch is the failure that has actually occurred here more than once: a rule
    reworded, softened, or deleted in one document while the others still teach it.
    """

    def test_every_pinned_rule_is_stated_in_every_file_that_carries_it(self):
        for rule_id, text, files, why in DOCTRINE:
            wanted = flatten(text)
            for name in files:
                self.assertIn(
                    wanted, visible(MIRRORS[name]),
                    "%s no longer states the pinned rule %r, word for word.\n"
                    "  expected: %s\n"
                    "  why it is pinned: %s\n"
                    "If the rule itself changed, update DOCTRINE in %s and every mirror "
                    "listed there in the same commit."
                    % (name, rule_id, wanted, why, Path(__file__).name))

    def test_each_pinned_sentence_is_anchored_where_the_doctrine_is_written_out(self):
        """The anchor must sit against its own sentence, not merely somewhere in the file.

        An anchor that has drifted away from the sentence it names is worse than none: the
        next person to edit that paragraph gets no warning that the wording is pinned.
        """
        for rule_id, text, files, _why in DOCTRINE:
            anchor = flatten(ANCHOR % rule_id)
            wanted = flatten(text)
            for name in files:
                if name not in ANCHORED:
                    continue
                flat = flatten(MIRRORS[name])
                self.assertEqual(
                    flat.count(anchor), 1,
                    "%s must carry exactly one %s comment, immediately before the pinned "
                    "sentence" % (name, anchor))
                after = flat[flat.index(anchor) + len(anchor):]
                self.assertIn(
                    wanted, after[:len(wanted) + 120],
                    "%s has the %s anchor, but the pinned sentence does not follow it. An "
                    "anchor names the sentence it precedes; move it back against %r"
                    % (name, anchor, wanted))

    def test_no_document_carries_an_anchor_for_a_rule_that_is_not_pinned(self):
        """A stray anchor advertises a guard nobody is running."""
        known = {rule_id for rule_id, _t, _f, _w in DOCTRINE}
        for name, text in MIRRORS.items():
            for found in re.findall(r"<!--\s*doctrine:\s*([\w-]+)\s*-->", text):
                self.assertIn(
                    found, known,
                    "%s anchors a doctrine rule %r that DOCTRINE in %s does not pin, so "
                    "the anchor promises a check that does not exist"
                    % (name, found, Path(__file__).name))
            for rule_id, _t, files, _w in DOCTRINE:
                if name not in files:
                    self.assertNotIn(
                        ANCHOR % rule_id, text,
                        "%s anchors %r but DOCTRINE does not list it as a mirror for that "
                        "rule" % (name, rule_id))


class RoundCapTest(unittest.TestCase):
    """The cap moved 3 -> 5 in the skill and stayed 3 in the README for a full release."""

    def cap(self):
        m = re.search(r"Cap at (\d+) rounds", SKILL)
        self.assertIsNotNone(m, "SKILL.md no longer states a round cap in a parseable form")
        return int(m.group(1))

    def test_readme_states_the_same_cap(self):
        self.assertRegex(
            README, r"cap at %d rounds" % self.cap(),
            "README's forging diagram disagrees with SKILL.md about the round cap",
        )

    def test_escalated_cap_agrees(self):
        """Both name the same number for a complex or important skill."""
        skill_hi = re.search(r"or (\d+) for a skill that is complex", SKILL)
        self.assertIsNotNone(skill_hi, "SKILL.md no longer states an escalated cap")
        self.assertIn(
            "(%s for a complex" % skill_hi.group(1), README,
            "README and SKILL.md disagree about the escalated round cap",
        )

    def test_status_line_example_budgets_the_documented_cap(self):
        """SKILL.md budgets steps as 2 + 2 x rounds. The README's examples must show that.

        Defeated twice. First: `re.search` took the FIRST bar in the file, so adding a
        second example with a different budget ("the usual 5-round cap is a 6-step forge")
        left the suite green while the README taught the wrong arithmetic. Then: "every
        bar" was a lie, because the hardcoded glyph class `[█·]` did not include `▓`, which
        is what the renderer draws for the partly filled cell -- an example written with
        the real glyph was not a bar as far as this test was concerned. `BAR` is built from
        the renderer now.
        """
        bars = BAR.findall(README)
        self.assertTrue(bars, "README's status-line example is no longer parseable")
        for step, total in bars:
            self.assertEqual(
                int(total), 2 + 2 * self.cap(),
                "a README example forge budgets %s steps, which is not 2 + 2 x the "
                "%d-round cap SKILL.md states" % (total, self.cap()))


class OrphanedConstantTest(unittest.TestCase):
    """A doc must not attribute a threshold constant to a skill that has dropped it."""

    def test_no_doc_cites_a_duration_the_skill_does_not_have(self):
        pattern = re.compile(r">\s?(\d+)\s?min")
        for name, text in (("README.md", README), (".claude/CLAUDE.md", REPO_CLAUDE)):
            for cited in pattern.findall(text):
                self.assertRegex(
                    SKILL, r">\s?%s\s?min" % cited,
                    "%s cites a >%s min threshold that SKILL.md does not define"
                    % (name, cited),
                )


# --------------------------------------------------------------------- counted claims
# A README sentence may state how many knobs there are. The check that reads those
# sentences used to carry a `words` map that stopped at "ten", which made a true sentence
# unwritable the moment a second table pushed the real total to fifteen: the cheap way out
# was to leave the new rows out of every assertion in this file rather than state a number
# the map could not hold. So parse the numeral instead of enumerating the ones expected.
_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
          "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
          "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}


def count_word(word):
    """The integer a README numeral denotes, or None if it does not denote one.

    Digits are read too, so *any* count is expressible however large; spelled numbers are
    read to ninety-nine, which is far past any table this repo will grow. A count this
    cannot read is a test failure with a message saying so, never a silent pass -- the map
    it replaces returned None for "fifteen" and compared that None against a row count.
    """
    w = word.strip().lower().replace("‑", "-").replace("–", "-")
    if re.fullmatch(r"\d+", w):
        return int(w)
    if w in _UNITS:
        return _UNITS[w]
    if w in _TENS:
        return _TENS[w]
    if "-" in w:
        tens, _, units = w.partition("-")
        if tens in _TENS and units in _UNITS and 1 <= _UNITS[units] <= 9:
            return _TENS[tens] + _UNITS[units]
    return None


# Every numeral the parser above can read, longest alternative first so that `twenty-one`
# is not matched as `twenty`. Built from the same two maps, so widening the parser widens
# the scan and the two cannot drift.
_NUMERAL = "|".join(
    sorted((["%s-%s" % (t, u) for t in _TENS for u in _UNITS if 1 <= _UNITS[u] <= 9]
            + list(_TENS) + list(_UNITS) + [r"\d+"]),
           key=len, reverse=True))
COUNTED_CLAIM = re.compile(
    r"\b(%s)\s+(?:\w+\s+){0,2}?(knobs?|tunables?|environment variables?|variables?)\b"
    % _NUMERAL, re.I)

# A table of knobs, wherever in the README it sits: the two leading columns are the
# signature. Anything matching this is checked, so a third table needs no test edit.
VAR_TABLE = re.compile(r"^\|Variable\|Default\|[^\n]*\n\|(?:-\|)+\n((?:\|[^\n]*\n)+)", re.M)


class TuningTableTest(unittest.TestCase):
    """Every knob the hook actually reads has to be findable in the README."""

    def hook_vars(self):
        found = {v for v in re.findall(r"CI_[A-Z_]+", HOOK) if not PIN.search(v)}
        self.assertTrue(found, "no tunable CI_* variables found in the hook")
        return found

    def tables(self):
        """Every knob table in the README, as (position, rows), rows being (var, default).

        Not just the one under `## Tuning`. The session review documents its knobs beside
        the disclosure that says it calls an API and is on by default, which is the only
        place its off switch is any use; merging them into the tuning table would move
        that switch three screens away from the paragraph a reader needs it in. The
        document keeps the shape it needs and the test follows it, rather than the five
        review rows sitting outside every assertion here because one table was all this
        knew how to read.
        """
        out = []
        for m in VAR_TABLE.finditer(README):
            rows = re.findall(r"^\|`([^`|]+)`\|([^|]*)\|", m.group(1), re.M)
            self.assertEqual(
                len(rows), len(m.group(1).strip().splitlines()),
                "a README knob table has a row this cannot read: every row must open "
                "`|`NAME`|` and its default cell must not contain a `|`")
            out.append((m.start(), rows))
        self.assertTrue(out, "README has no |Variable|Default| knob table")
        return out

    def all_rows(self):
        return [row for _, rows in self.tables() for row in rows]

    def table_rows(self):
        """Just the names, from every table."""
        return [var for var, _ in self.all_rows()]

    def section_of(self, pos):
        """The `##` section containing `pos`, as (start, end)."""
        starts = [m.start() for m in re.finditer(r"^## ", README, re.M)]
        lo = max([s for s in starts if s <= pos], default=0)
        hi = min([s for s in starts if s > pos], default=len(README))
        return lo, hi

    def tables_near(self, pos):
        """Rows of every knob table in the same `##` section as `pos`."""
        lo, hi = self.section_of(pos)
        return [rows for start, rows in self.tables() if lo <= start < hi]

    def test_every_tunable_the_hook_reads_is_documented(self):
        for var in sorted(self.hook_vars() - set(self.table_rows())):
            self.fail("hooks/compound-improvement.sh reads %s but no README "
                      "tuning table lists it" % var)

    def test_no_documented_tunable_is_imaginary(self):
        """A row for a variable nothing reads is worse than no row.

        Defeated before: this skipped every row whose name did not begin with `CI_`, so a
        row for `STATUSLINE_SPINNER_MS` -- a knob that has never existed -- passed. Every
        row, checked against everything that ships. Defeated a second way, without anyone
        editing this method: a second table was added and only the first was read, so five
        `SKILL_COMPOUNDER_REVIEW_*` rows were exempt. `tables()` reads them all now.
        """
        for var in self.table_rows():
            # Word-boundary, not `in`: a substring test passes a documented
            # `SKILL_COMPOUNDER_REVIEW_COOLDOWN` against a script that has since renamed it
            # to `..._COOLDOWN_SECS`, which is the exact drift this is here to catch.
            self.assertIsNotNone(
                re.search(r"\b%s\b" % re.escape(var), SCRIPTS),
                "README documents %s but nothing in bin/, hooks/ or statusline/ "
                "reads it" % var)

    def test_no_knob_is_documented_in_two_places(self):
        """One row per knob, across all tables: two rows are two defaults to keep in step,
        and the one nobody edits is the one a reader finds first."""
        seen = self.table_rows()
        for var in sorted(set(seen)):
            self.assertEqual(seen.count(var), 1,
                             "%s has %d README rows; a knob gets exactly one"
                             % (var, seen.count(var)))

    def test_documented_defaults_are_the_defaults(self):
        """A row naming the right variable and the wrong number is drift with a citation.

        `.claude/CLAUDE.md` says the defaults "live in the script and are echoed in the
        README tuning table. Change both." Nothing checked the numbers: a cold reviewer
        rewrote all three README defaults to values the hook has never used and the suite
        stayed green. Derive each one from the script's own `${VAR:-default}`.

        A default cell that is not a single backticked literal is prose, and prose is only
        honest where the script has no value to state (`${VAR:-}`). Otherwise a row could
        put its number beyond reach by describing it in words.
        """
        for var, cell in self.all_rows():
            real = re.search(r"\$\{%s:-([^}]*)\}" % re.escape(var), SCRIPTS)
            self.assertIsNotNone(
                real, "README documents a default for %s but no script defaults it" % var)
            literal = re.fullmatch(r"`([^`]+)`", cell.strip())
            if literal is None:
                self.assertEqual(
                    real.group(1), "",
                    "README describes %s's default in prose (%r) but the script defaults "
                    "it to %r; state a real default as a backticked literal"
                    % (var, cell.strip(), real.group(1)))
                continue
            # `$HOME/x` and `~/x` are the same path written two ways; everything else
            # has to match character for character.
            norm = lambda s: s.replace("$HOME", "~").replace("${HOME}", "~")
            self.assertEqual(
                norm(literal.group(1)), norm(real.group(1)),
                "README says %s defaults to %s; the script defaults it to %s"
                % (var, literal.group(1), real.group(1)))

    def test_stated_counts_match_the_table(self):
        tables = self.tables()
        total = re.search(r"All ([\w-]+) are environment variables", README)
        self.assertIsNotNone(total, "README no longer states how many tunables there are")
        stated = count_word(total.group(1))
        self.assertIsNotNone(
            stated, "README states a tunable count as %r, which is not a number "
            "`count_word` can read" % total.group(1))
        local = self.tables_near(total.start())
        self.assertEqual(len(local), 1,
                         "the sentence stating how many tunables there are is no longer in "
                         "a section with exactly one knob table, so nothing knows which "
                         "table it counts")
        self.assertEqual(stated, len(local[0]),
                         "README says there are %s tunables; the table in that section "
                         "lists %d" % (total.group(1), len(local[0])))
        ci = re.search(r"Only the ([\w-]+) `CI_\*` variables", README)
        self.assertIsNotNone(ci, "README no longer states how many CI_* vars the hook reads")
        local = self.tables_near(ci.start())
        self.assertEqual(len(local), 1,
                         "the CI_* count sentence is no longer in a section with exactly "
                         "one knob table")
        self.assertEqual(count_word(ci.group(1)),
                         len([v for v, _ in local[0] if v.startswith("CI_")]),
                         "README's CI_* count disagrees with the table beside it")
        # Defeated before: both counts above are pinned to one sentence each, so a THIRD
        # sentence with a different number ("Six knobs actually do anything") contradicted
        # the table with the suite green. Any counted claim about the knobs has to agree
        # with the table in its own section -- and with some real count anywhere else,
        # which is the weaker half of this and the reason a claim about knobs belongs in
        # the section whose table it counts.
        every = [len(rows) for _, rows in tables]
        for m in COUNTED_CLAIM.finditer(README):
            stated = count_word(m.group(1))
            self.assertIsNotNone(stated, "unreadable numeral %r" % m.group(1))
            local = self.tables_near(m.start())
            allowed = ([len(rows) for rows in local] if local
                       else every + [sum(every)])
            self.assertIn(
                stated, allowed,
                "README says %s %s; the knob table(s) it is counting list %s rows"
                % (m.group(1), m.group(2), " or ".join(str(n) for n in sorted(set(allowed)))))


class DerivationCommandTest(unittest.TestCase):
    """The README hands the reader a command and claims it prints every name any shipped
    script reads. That is a completeness claim, and unlike a claim about prose it is
    decidable: run the command the README actually carries -- not a copy retyped here --
    and compare it against the names the scripts really read.

    This is what stands in for listing every knob in the tables. The tables are explicitly
    not the whole set; the command is, so the command is what gets checked.
    """

    # Read by a shipped script, owned by something else: the shell, or a tool the script
    # shells out to. Everything not on this list is ours and must be findable by the
    # documented command. The list is short and deliberately hand-maintained, so adopting
    # a new prefix means editing it in a commit a reviewer can see -- the same reason the
    # doctrine sentences above are pinned rather than derived.
    AMBIENT = {"HOME", "PATH", "PWD", "SHELL", "TMPDIR", "RANDOM", "IFS", "LANG", "LC_ALL",
               "CLAUDE_CONFIG_DIR", "GH_TOKEN", "GITHUB_TOKEN"}

    def command(self):
        i = README.find("prints every")
        self.assertNotEqual(
            i, -1, "README no longer offers a command that prints every name a script reads")
        m = re.search(r"```bash\n(.*?)```", README[i:], re.S)
        self.assertIsNotNone(m, "the README's derivation command is no longer in a "
                                "```bash fence right after the sentence promising it")
        return m.group(1)

    def test_the_documented_command_runs_and_prints_names(self):
        out = subprocess.run(["bash", "-c", self.command()], cwd=str(ROOT),
                             capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(out.returncode, 0,
                         "the README's derivation command fails from the repo root: %s"
                         % out.stderr.strip())
        self.assertTrue(out.stdout.split(), "the README's derivation command prints nothing")

    def printed(self):
        out = subprocess.run(["bash", "-c", self.command()], cwd=str(ROOT),
                             capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return set(out.stdout.split())

    def test_the_documented_command_finds_every_knob_a_script_reads(self):
        """`${VAR:-...}` is a read with a default, which is what a knob is. A name also
        assigned somewhere in the scripts is a local, not a knob."""
        read = set(re.findall(r"\$\{([A-Z][A-Z0-9_]{2,}):-", SCRIPTS))
        assigned = set(re.findall(r"(?<![\w$\"'])([A-Z][A-Z0-9_]{2,})=(?!=)", SCRIPTS))
        knobs = {n for n in read - assigned if n not in self.AMBIENT}
        self.assertTrue(knobs, "no knobs found in the shipped scripts at all")
        for name in sorted(knobs - self.printed()):
            self.fail("the README says its command prints every name any shipped script "
                      "reads, but %s is read by a script and the command does not print "
                      "it" % name)

    def test_the_documented_command_finds_every_documented_knob(self):
        printed = self.printed()
        for var in TuningTableTest("test_no_documented_tunable_is_imaginary").table_rows():
            self.assertIn(var, printed,
                          "README documents %s in a table but the command it offers as the "
                          "full list does not print it" % var)


class ForgeDiagramTest(unittest.TestCase):
    """The README's forging diagram is structure, not prose, so its shape is decidable.

    This is the only guard in this file that reads the README's account of the protocol
    beyond a pinned sentence, and it can be, because ASCII tree indentation has a parse.
    The first version of the test asserted only that the word "orchestrator" appeared
    somewhere in the README, which passes against a diagram that still hangs the builder
    off the main session. Bind the nesting instead.
    """

    def test_the_diagram_nests_the_loop_under_the_orchestrator(self):
        if "orchestrator" not in FORGING:
            self.fail("SKILL.md no longer hands the loop to an orchestrator, so this whole "
                      "test and the `orchestrator-runs-the-rounds` rule need re-deriving")
        diagram = re.search(r"```\nskillforge start.*?```", README, re.S)
        self.assertIsNotNone(diagram, "README's forging diagram is no longer parseable")
        lines = diagram.group(0).splitlines()

        def line_of(role):
            for i, line in enumerate(lines):
                if re.search(r"[├└]─ %s" % re.escape(role), line):
                    return i
            self.fail("the README diagram omits %r" % role)

        orch_i = line_of("orchestrator")
        orch = len(lines[orch_i]) - len(lines[orch_i].lstrip())
        # Indentation alone is not parentage either: a diagram can park the orchestrator as
        # a dead-end leaf and hang the builder off some *other* node at a deeper indent, and
        # a bare `indent >` comparison accepts it. Require an unbroken descent -- every
        # child must follow the orchestrator with no line at or above its indent between.
        for role in ("builder", "red-team", "loop"):
            i = line_of(role)
            self.assertGreater(
                i, orch_i,
                "the README diagram must place %r after the orchestrator that dispatches "
                "it" % role)
            child = len(lines[i]) - len(lines[i].lstrip())
            self.assertGreater(
                child, orch,
                "the README diagram must nest %r *under* the orchestrator: SKILL.md no "
                "longer lets the main session dispatch it directly" % role)
            for between in lines[orch_i + 1:i]:
                if not between.strip():
                    continue
                depth = len(between) - len(between.lstrip())
                self.assertGreater(
                    depth, orch,
                    "the README diagram breaks out of the orchestrator's subtree before "
                    "reaching %r, so %r hangs off something else: %r"
                    % (role, role, between.strip()))


# A json filename as the docs write it, inside backticks: `forge/<slug>.forge.json`,
# `current.json`, `*.json`. The bare word `.json` (as in "does not end in `.json`") is not
# a filename and must not be read as one, which is why a leading name character is required.
JSON_FILE = re.compile(r"`(?:[^`]*/)?([\w*<>][\w.*<>-]*\.json)`")


def sentences(text):
    """Rough sentence split, for LOCALITY only -- never to decide what a sentence means.

    The one thing it is used for is keeping an identifier next to the claim that cites it:
    a `.json` filename mentioned in a sentence that is about `skillforge`. Fenced blocks
    are dropped because a command line is not a claim about anything.
    """
    flat = re.sub(r"```.*?```", " ", text, flags=re.S).replace("\n", " ")
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", flat) if s.strip()]


class SkillforgeContractTest(unittest.TestCase):
    """The docs are checked against what `bin/skillforge` DOES, by running it.

    `skillforge` used to keep one `current.json`, so the skill told sessions to check for a
    live forge and to wait if they found one. It now writes one slot per forge and several
    run at once. The guard that replaced that rule was gated on `"current.json" in
    bin/skillforge`, so when the string left the script the test began skipping
    permanently -- a green report from an assertion nobody was running. Everything below
    derives its expectation from the CLI's own output instead, which is both the house rule
    (no mocks) and the only way the docs get checked against behaviour rather than against a
    constant copied out of it.
    """

    @classmethod
    def setUpClass(cls):
        """Two concurrent forges, a duplicate of the first, and a double close. One run,
        since nothing here mutates it, and every expectation below is read off the result."""
        cls._tmp = tempfile.TemporaryDirectory()
        state = Path(cls._tmp.name)
        cls.state = state

        def cli(*args):
            return subprocess.run(
                [str(ROOT / "bin" / "skillforge"), *args],
                capture_output=True, text=True, stdin=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                     "HOME": str(state), "SKILL_COMPOUNDER_STATE": str(state)})

        cls.first = cli("start", "alpha-forge", "8", "the first one")
        cls.second = cli("start", "beta-forge", "8", "a concurrent one")
        cls.duplicate = cli("start", "alpha-forge", "8", "the same name again")
        cls.slots = sorted(p.name for p in (state / "forge").glob("*.json"))
        cls.first_after = cli("show", "--name", "alpha-forge")
        # The double close, which is what `close-ownership` exists to prevent.
        cls.closed = cli("done", "--name", "alpha-forge", "the outcome that counts")
        cls.reclosed = cli("fail", "--name", "alpha-forge", "the outcome that is lost")
        cls.ledger = [json.loads(l) for l in
                      (state / "ledger.jsonl").read_text().splitlines() if l.strip()]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_two_forges_run_at_once(self):
        """The premise behind the `concurrent-forges` rule, established by running.

        If this ever stops holding -- if a second `start` under a different name starts
        failing, or stops leaving the first record alone -- then that pinned rule is
        guarding the wrong doctrine and should be retired with it.
        """
        self.assertEqual(self.first.returncode, 0, self.first.stderr)
        self.assertEqual(self.second.returncode, 0, self.second.stderr)
        self.assertEqual(len(self.slots), 2,
                         "two concurrent forges no longer occupy two slots: %s" % self.slots)
        self.assertEqual(self.first_after.returncode, 0, self.first_after.stderr)
        first = json.loads(self.first_after.stdout)
        self.assertEqual(first["name"], "alpha-forge")
        self.assertEqual(first["status"], "active",
                         "starting a second forge closed or clobbered the first")

    def test_a_second_close_is_discarded_silently(self):
        """The premise behind `close-ownership` and `orchestrator-does-not-close`.

        Exactly one party may close a forge, and the reason is measurable: the second close
        neither records an outcome nor reports a failure. If the CLI ever starts rejecting
        it loudly, or recording both, the doctrine is cheaper than it looks and the pinned
        rules should be revisited rather than left standing on a stale rationale.
        """
        self.assertEqual(self.closed.returncode, 0, self.closed.stderr)
        outcomes = [e for e in self.ledger
                    if e.get("name") == "alpha-forge" and e.get("event") != "start"]
        self.assertEqual(
            [e["event"] for e in outcomes], ["done"],
            "a forge closed twice no longer records exactly one outcome: %r" % outcomes)
        self.assertEqual(
            outcomes[0]["phase"], "the outcome that counts",
            "the ledger no longer keeps the FIRST close, so which party owns the close "
            "matters differently than the docs say")
        self.assertEqual(
            self.reclosed.returncode, 0,
            "a second close now fails loudly; it used to exit 0, which is why the docs "
            "warn that the loser's outcome vanishes with no error anywhere")

    def test_the_duplicate_name_refusal_is_documented_as_it_behaves(self):
        """What `start` does on a name that is already live, and what the skill says it
        does, have to be the same thing -- including the exit status, which is the only
        signal a scripted caller sees."""
        rc = self.duplicate.returncode
        self.assertNotEqual(rc, 0,
                            "`skillforge start` no longer refuses a duplicate active name; "
                            "re-derive this rule from what it does instead")
        self.assertEqual(len(self.slots), 2,
                         "the refused duplicate left a third slot behind: %s" % self.slots)
        self.assertRegex(
            FORGING, r"\bexits? %d\b" % rc,
            "`skillforge start` exits %d on a name that is already live; the forging "
            "protocol must state that number, or a session reads the refusal as a crash "
            "and abandons a forge that was never in trouble" % rc)

        # The recovery the skill offers must be the one the CLI itself names. Both tokens
        # are taken from the refusal message at runtime, so renaming the flag or the
        # subcommand fails here rather than leaving the skill quietly pointing at neither.
        msg = self.duplicate.stderr
        for token in ("skillforge done", "--name"):
            self.assertIn(token, msg,
                          "the refusal message no longer names %r, so this assertion is "
                          "checking the docs against nothing" % token)
            self.assertIn(
                token, FORGING,
                "`skillforge start` tells the user to recover with %r and the forging "
                "protocol does not mention it" % token)

    def test_no_doc_names_a_forge_state_file_the_cli_does_not_write(self):
        """The retired doctrine was built on a single shared `current.json`. The file is
        gone; a doc that still names it teaches a mechanism that no longer exists.

        The expected shape is derived from the slot the CLI actually wrote for a known
        forge name, not spelled out here, so renaming the slot updates this test for free.
        """
        self.assertIn("alpha-forge.forge.json", self.slots,
                      "the slot filename no longer derives from the forge name: %s"
                      % self.slots)
        suffix = "alpha-forge.forge.json"[len("alpha-forge"):]

        for name, text in ((SKILL_PATH, SKILL), ("docs/DESIGN.md", DESIGN),
                           ("docs/CLAUDE-CODE-BEHAVIOR.md", PLATFORM),
                           ("README.md", README)):
            for sentence in sentences(text):
                if not re.search(r"skillforge|forge/", sentence, re.I):
                    continue
                for cited in JSON_FILE.findall(sentence):
                    if cited.startswith("*"):
                        continue  # `*.json`, the glob the reader is told to expect
                    self.assertTrue(
                        cited.endswith(suffix),
                        "%s names a forge state file `%s`; `skillforge` writes one slot "
                        "per forge, named `<slug>%s`, and nothing shared: %r"
                        % (name, cited, suffix, sentence))


# The exact sentences the retired single-forge doctrine used, taken from the diffs that
# removed them. This catches ONLY their literal return -- a copy-paste out of git history,
# or a revert -- and no paraphrase whatsoever. That is the entire claim. An earlier version
# of this file tried to scan for the *idea* of telling a session to wait, and was defeated
# by rewording, twice; see the module docstring.
RETIRED_WORDING = (
    "If one is live, **wait**",
    "a second `start` overwrites the first",
    "One forge at a time",
)


class RetiredWordingTest(unittest.TestCase):
    def test_no_doc_reverts_to_a_retired_sentence(self):
        for name, text in ((SKILL_PATH, SKILL), ("docs/DESIGN.md", DESIGN),
                           ("docs/CLAUDE-CODE-BEHAVIOR.md", PLATFORM),
                           ("README.md", README), (".claude/CLAUDE.md", REPO_CLAUDE)):
            for retired in RETIRED_WORDING:
                self.assertNotIn(
                    retired, text,
                    "%s carries %r, a sentence from the retired single-forge doctrine. "
                    "Forges are concurrent; a session that obeys it stalls, or drops its "
                    "animation and its ledger row, for a collision that cannot happen"
                    % (name, retired))


class SeedPoolTest(unittest.TestCase):
    """Adding a skill to skills/ without adding its README row is the same drift.

    It happened: `ai-tell-audit` shipped, and the README kept describing four seed skills
    and a pool that did not contain it.
    """

    def shipped(self):
        return sorted(d.name for d in (ROOT / "skills").iterdir()
                      if (d / "SKILL.md").is_file())

    def table_rows(self):
        m = re.search(r"\|Skill\|Fires when\|The failure it prevents\|\n\|-\|-\|-\|\n((?:\|.*\n)+)",
                      README)
        self.assertIsNotNone(m, "README seed-pool table is missing or reshaped")
        return re.findall(r"^\|`([^`]+)`\|", m.group(1), re.M)

    def install_table_rows(self):
        """The `skills/<name>/` entries in the "What gets installed" table."""
        m = re.search(r"\|Piece\|What it does\|\n\|-\|-\|\n((?:\|.*\n)+)", README)
        self.assertIsNotNone(m, "README's 'What gets installed' table is missing or reshaped")
        return re.findall(r"^\|`skills/([^/`]+)/`\|", m.group(1), re.M)

    def test_every_shipped_skill_is_documented(self):
        """A skill nobody mentions is a skill nobody finds.

        This assertion was weakened once, and wrongly: it failed because the README said
        "Five skills ship" while seven directories shipped, and the response was to relax
        it to "the name appears somewhere in the README" instead of asking whether the
        prose was right. A bare substring passes on an incidental mention in a code
        sample. Every shipped skill has to be documented in one of the two places a reader
        looks for the inventory: a row in the seed-pool table, or its own row in "What
        gets installed" (which is where the machinery skills -- `skill-compounder`,
        `contribute-skill`, `skill-authoring` -- belong, since they are not day-one
        seed skills).
        """
        documented = set(self.table_rows()) | set(self.install_table_rows())
        for name in self.shipped():
            # assertIn against README would print the whole file on failure. A 20 KB dump
            # for a one-word finding is output nobody reads.
            self.assertIn(
                name, documented,
                "skills/%s ships but no README table lists it: put it in the seed-pool "
                "table if a fresh install should reach for it on day one, or give it a "
                "`skills/%s/` row in 'What gets installed' if it is machinery"
                % (name, name))

    def test_no_row_describes_a_skill_that_does_not_ship(self):
        shipped = set(self.shipped())
        for name in self.table_rows():
            self.assertIn(name, shipped,
                          "README documents a seed skill `%s` that does not ship" % name)

    def test_the_stated_pool_size_matches(self):
        """And it is stated once.

        The README used to carry the count in three places ("five seed skills" in the
        intro, "(five more)" in the install table, "Five skills ship with the package" in
        the pool section) while seven skill directories shipped, which is both ambiguous
        -- five of what? -- and three chances to drift. So: every counted claim about how
        many skills ship has to agree with the pool table, wherever it is written.
        """
        words = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10}
        counted = re.findall(
            r"\b(three|four|five|six|seven|eight|nine|ten)\s+(?:more\s+|seed\s+)*"
            r"(?:skills?\b|of\s+the\s+(?:entries|rows|skills)\b)",
            README, re.I)
        self.assertTrue(counted, "README no longer states the seed-pool size")
        for word in counted:
            self.assertEqual(
                words.get(word.lower()), len(self.table_rows()),
                "README says %s skills; the seed-pool table lists %d. State the count "
                "once, in the pool section, and say what it counts"
                % (word, len(self.table_rows())))


class SkillBudgetTest(unittest.TestCase):
    """`skill-authoring` states two budgets; the skills that ship have to meet them.

    Both numbers are DERIVED from `skills/skill-authoring/SKILL.md`, never copied here, so
    raising or lowering a budget there moves this test with it. That is rule 1 of this
    file: a budget is a setting, and a setting is read off disk.

    Why it is here rather than in a seed-skill test file: `skill-compounder` is the one
    skill whose budgets nothing checked, and it was over BOTH of them -- 655 description
    characters and 642 body lines -- while its own sibling documented 500 and 500. A cap
    stated in one shipped file and violated by another shipped file in the same tree is
    exactly the drift the rest of this module exists to catch.
    """

    # Skills that ship over a budget, with the debt written down instead of the guard
    # switched off. Same shape as `UNVERIFIED` in tests/test_routing_claims.py: the list
    # may only shrink, and a name on it that is no longer over the ceiling fails below, so
    # a fix cannot leave a stale exemption behind. Do NOT add to it to make a red test
    # green -- split the body into `references/` the way `skill-authoring` does.
    # Empty since ai-tell-audit came under the ceiling (543 body lines to 496) by moving
    # its evidence and its script notes into skills/ai-tell-audit/references/.
    OVER_BODY_CEILING = set()

    AUTHORING = ROOT / "skills" / "skill-authoring" / "SKILL.md"

    def budgets(self):
        text = self.AUTHORING.read_text()
        desc = re.search(r"[Dd]escription at most (\d+) characters", text)
        front = re.search(r"frontmatter block at most (\d+)", text)
        body = re.search(r"Hard ceiling: (\d+) body\s+lines", text)
        for name, m in (("description", desc), ("frontmatter", front), ("body", body)):
            self.assertIsNotNone(
                m, "skills/skill-authoring/SKILL.md no longer states the %s budget in a "
                   "parseable form, so nothing here knows what the ceiling is" % name)
        return int(desc.group(1)), int(front.group(1)), int(body.group(1))

    def shipped(self):
        out = []
        for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            raw = path.read_text()
            parts = raw.split("---\n", 2)
            self.assertEqual(len(parts), 3, "%s has no frontmatter block" % path.parent.name)
            out.append((path.parent.name, parts[1], parts[2]))
        self.assertTrue(out, "no skills ship; this test is vacuous")
        return out

    def test_every_description_is_inside_the_documented_budget(self):
        desc_max, front_max, _ = self.budgets()
        for name, front, _body in self.shipped():
            meta = __import__("yaml").safe_load(front)
            self.assertLessEqual(
                len(meta["description"]), desc_max,
                "skills/%s description is %d characters against the %d `skill-authoring` "
                "documents. Padding makes the listing drop it under context pressure, "
                "which is the failure the budget is for"
                % (name, len(meta["description"]), desc_max))
            self.assertLessEqual(
                len(front), front_max,
                "skills/%s frontmatter block is %d characters against %d"
                % (name, len(front), front_max))

    def test_every_body_is_inside_the_documented_ceiling(self):
        _, _, body_max = self.budgets()
        for name, _front, body in self.shipped():
            lines = len(body.strip().splitlines())
            if name in self.OVER_BODY_CEILING:
                continue
            self.assertLessEqual(
                lines, body_max,
                "skills/%s has a %d-line body against the hard ceiling of %d that "
                "skills/skill-authoring/SKILL.md states. The body is a token cost paid on "
                "every turn after the skill loads; move depth into references/"
                % (name, lines, body_max))

    def test_the_over_ceiling_list_holds_only_skills_that_are_really_over(self):
        """A debt ledger that may only shrink. An exemption left behind after the fix is
        an exemption nobody notices is switched off."""
        _, _, body_max = self.budgets()
        sizes = {name: len(body.strip().splitlines())
                 for name, _f, body in self.shipped()}
        for name in sorted(self.OVER_BODY_CEILING):
            self.assertIn(name, sizes,
                          "OVER_BODY_CEILING names %r, which does not ship" % name)
            self.assertGreater(
                sizes[name], body_max,
                "skills/%s is %d lines, inside the %d-line ceiling, but is still listed in "
                "OVER_BODY_CEILING. Remove it from the list in the same commit that "
                "brought it under" % (name, sizes[name], body_max))


if __name__ == "__main__":
    unittest.main(verbosity=2)
