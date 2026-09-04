#!/usr/bin/env python3
"""The forging doctrine is stated in three places. They must not drift apart.

`.claude/CLAUDE.md` carries the rule in prose: "Its doctrine is mirrored in
docs/architecture.md and in the user's global ~/.claude/CLAUDE.md stanza. Changing the
protocol means updating all three." That rule has been violated twice, both times the same
way: the skill changed and the prose describing it did not, so the long-form document
carried a round cap and a duration threshold the skill no longer had. A fresh session
reading it would have applied a rule that does not exist. The long-form mirror was
`README.md` until the docs split of 2026-09-03 moved the forging protocol to
`docs/architecture.md`; the mirror set is the same four files it always was.

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
    quoted above, and it USED to be unchecked here on the grounds that this repo neither
    shipped nor installed it. That stopped being true when `installer.py` grew
    `DOCTRINE_TEXT` and wrote the block itself, so the constant is now a mirror like any
    other. What still cannot be checked is the file on a particular machine: a user may
    edit the installed block, and nothing here reads anyone's `~/.claude/CLAUDE.md`.

`<!-- doctrine: <id> -->` anchors mark the pinned sentences in the two documents that
state the doctrine at length. They render as nothing, and they tell a human editing the
paragraph that the next sentence is pinned verbatim. `.claude/CLAUDE.md` is a condensed
stanza and carries the sentences without anchors.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from skill_compounder.installer import DOCTRINE_TEXT  # noqa: E402
SKILL = (ROOT / "skills" / "skill-compounder" / "SKILL.md").read_text()
README = (ROOT / "README.md").read_text()
# The four pages the docs split of 2026-09-03 carved out of the README. The forging
# protocol, the doctrine anchors and the two diagrams went to `architecture.md`; the knob
# tables and the derivation command went to `operations.md`. Every assertion below that
# used to read the README reads the page its text is now in.
ARCH = (ROOT / "docs" / "architecture.md").read_text()
OPERATIONS = (ROOT / "docs" / "operations.md").read_text()
MEASUREMENT = (ROOT / "docs" / "measurement.md").read_text()
DEVELOPMENT = (ROOT / "docs" / "development.md").read_text()
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
# The global stanza the installer writes into the user's own `~/.claude/CLAUDE.md`. It is
# the third mirror the rule in `.claude/CLAUDE.md` names, and it was unchecked here for as
# long as this repo neither shipped nor installed it. It does both now -- `installer.py`
# carries the text and `render_doctrine()` writes it -- so it is read from the constant
# rather than from any machine's file, and the `{app_home}` placeholder is substituted the
# way `render_doctrine` substitutes it.
STANZA_PATH = "skill_compounder/installer.py (DOCTRINE_TEXT)"
STANZA = DOCTRINE_TEXT.replace("{app_home}", "<the checkout>")
# The long-form mirror: the one document that states the doctrine at length, with an
# anchor comment against each pinned sentence. It was `README.md` until the docs split.
PROTOCOL_DOC = "docs/architecture.md"
PROTOCOL = ARCH
MIRRORS = {SKILL_PATH: SKILL, PROTOCOL_DOC: PROTOCOL, ".claude/CLAUDE.md": REPO_CLAUDE,
           STANZA_PATH: STANZA}

# Where an anchor comment is required alongside the sentence. `.claude/CLAUDE.md` and the
# installed stanza are excluded on purpose: both are condensed restatements with no room
# for an anchor per sentence. See the module docstring.
ANCHORED = (SKILL_PATH, PROTOCOL_DOC)


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
     (SKILL_PATH, PROTOCOL_DOC, ".claude/CLAUDE.md", STANZA_PATH),
     "A fresh reviewer is the one thing the loop cannot work without: a fork already knows "
     "what the skill was meant to say."),

    # `orchestrator-runs-the-rounds` ("The session that starts a forge does not run it.")
    # was retired on 2026-09-02 with the forge diet. The invariant it protected -- review
    # traffic must not land in the user's thread -- is real and is now carried by
    # `forge-runs-in-the-background`, which states it about the agents rather than about a
    # layer. The orchestrator itself is gone from the default forge: it caught no defect in
    # ten forges and caused the 86-hour stuck one, so a rule requiring one would now be
    # requiring the thing that was removed.
    ("forge-runs-in-the-background",
     "Every agent a forge dispatches runs in the background, and the session that starts "
     "one never blocks on it.",
     (SKILL_PATH, PROTOCOL_DOC, STANZA_PATH),
     "The reason the loop was moved off the main thread was never blocking -- the agents "
     "always ran in the background -- it was review traffic landing in the thread the user "
     "is talking to. Stated as 'someone else runs it', the rule died with the orchestrator; "
     "stated about the dispatches, it survives the diet."),

    ("tier-before-forge",
     "A procedure earns a skill only when it has steps a model gets wrong without them AND "
     "a trigger a description can route; otherwise it is a note or a reminder.",
     (SKILL_PATH, PROTOCOL_DOC, STANZA_PATH),
     "The threshold said only costly-and-recurring, which a note also passes. Ten days of "
     "the cheap branch being taken zero times is what a missing rule looks like: with one "
     "output path, everything that cleared the bar got a forge."),

    ("cheap-branch",
     "The cheap branch is a command, not an intention: `skillnote add` records the note or "
     "the reminder, and a lesson nobody ran a command for was not kept.",
     (SKILL_PATH, PROTOCOL_DOC),
     "The sentence this replaced -- 'write a note or update the project's CLAUDE.md' -- "
     "named no path, no CLI and no ledger row, and was taken zero times in ten days. A "
     "branch with no command behind it is a branch nobody can be shown to have taken."),

    ("hard-round-cap",
     "A third round is earned by a falling blocking count, and `skillforge` refuses the "
     "round without one.",
     (SKILL_PATH, PROTOCOL_DOC, STANZA_PATH),
     "Three of ten forges ran past an advisory cap that refused nothing, and rounds 3 and "
     "beyond were roughly 60% of the wall clock. A budget nothing enforces is a suggestion."),

    ("close-ownership",
     "You own `start`, `done` and `fail`; every agent you dispatch owns everything between.",
     (SKILL_PATH, PROTOCOL_DOC),
     "Exactly one party may close a forge; the CLI discards the second close at exit 0. "
     "Renamed from 'the orchestrator owns everything between' on 2026-09-02: the default "
     "forge has no orchestrator, and a rule naming a stage that is not there reads as "
     "inapplicable rather than as binding on the builder and the reviewer."),

    ("dispatched-agents-do-not-close",
     "A dispatched agent calls neither `done` nor `fail`.",
     (SKILL_PATH,),
     "The same rule named from the other side. A rule that only says someone does not "
     "close the forge can be read either way. Renamed from `orchestrator-does-not-close` "
     "for the reason above, and widened at the same time: C and D could always have called "
     "`done`, and the old wording forbade it only to a stage that no longer exists."),

    ("no-leading-prompt",
     "Never hand a reviewer a list of what not to flag.",
     (SKILL_PATH, PROTOCOL_DOC),
     "A brief that pre-classifies the allowed cases returns your own judgement with a "
     "second name on it."),

    ("neutral-retirement-question",
     'Ask a second fresh agent the neutral question, "should this be kept, fixed, or '
     'retired?", never "confirm this deletion".',
     (SKILL_PATH, PROTOCOL_DOC),
     "The retirement check has the same shape as the red-team check, and a leading prompt "
     "defeats both."),

    ("archive-the-source",
     "Archive the source, not the link.",
     (SKILL_PATH, PROTOCOL_DOC),
     "Skills are symlinks into a checkout: moving the link leaves the real directory for "
     "the next install to resurrect, and writes the tombstone into live source."),

    ("both-conditions",
     "Both must hold, or it gets a note rather than a skill.",
     (SKILL_PATH, PROTOCOL_DOC, STANZA_PATH),
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

    ("assess-convergence-every-round",
     "Decide whether the loop is converging at every round, not at the cap.",
     (SKILL_PATH,),
     "The rule this replaced put the scope decision AT the cap, and a reader followed it "
     "into a plan that would have narrowed a skill in its final round and shipped the "
     "result -- changing what the skill was and leaving that change unreviewed, in one "
     "step. A cap reached is not a decision point; it is the moment the budget for making "
     "one ran out."),

    ("the-assessment-binds-from-round-two",
     "The assessment binds from round 2, where the first comparison exists, and never from "
     "round 1.",
     (SKILL_PATH,),
     "A cold reviewer showed the catch-all firing at round 1: with one data point no "
     "trajectory can match the converging definition, so 'anything else is not converging' "
     "handed a pressed session permission to abandon after a single round. A rule that "
     "fires on one round is a licence to quit after one. Renumbered from 3 to 2 with the "
     "forge diet, because the cap is 2 and a rule that binds only from round 3 would never "
     "bind at all on a default forge; 2 is also where the first comparison exists, which is "
     "the property the rule was always about."),

    ("narrowing-restarts-the-review",
     "A narrowed skill is a new skill for review purposes: the rounds already spent "
     "certify a skill that no longer exists.",
     (SKILL_PATH,),
     "Without this, 'narrow its scope until it is clean' reads as an edit made on the way "
     "out the door rather than a decision that costs another cold round."),

    ("no-silent-workaround",
     "Never silently work around a skill that misfired.",
     (SKILL_PATH, PROTOCOL_DOC),
     "The workaround costs the same time again in every future session, and nothing "
     "records that the skill is broken."),

    ("never-rm-rf",
     "Never `rm -rf` a skill.",
     (SKILL_PATH, PROTOCOL_DOC),
     "Retirement can be wrong, so it has to be recoverable."),

    ("routing-gate-on-completion",
     "A forge cannot be reported clean while the skill's own must-fire prompts do not "
     "fire it.",
     (SKILL_PATH, PROTOCOL_DOC, STANZA_PATH),
     "Every seed skill passed a full red-team loop on a `## Trigger precision` section "
     "nobody ran; three of the claims were then false. A reviewer agreeing a description "
     "reads well is not a measurement of the router."),

    ("must-not-half-is-a-gate",
     "A skill that fires on everything is worse than no skill.",
     (SKILL_PATH, PROTOCOL_DOC),
     "Half a routing gate is not a gate: a skill that wins every prompt displaces the "
     "neighbour that would have handled it, which is the failure `stale-artifact-check` "
     "suffered from the other side."),

    ("unmeasured-is-not-verified",
     "A probe that could not run is never a pass.",
     (SKILL_PATH, PROTOCOL_DOC),
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

    ("boundary-without-the-address",
     "Where a boundary must still be stated, describe what it encloses and never name what "
     "lies outside it.",
     (SKILL_PATH,),
     "Isolation is a property of what an agent is GIVEN, and a prohibition is the one place "
     "that principle can be violated by the wording alone. The first end-to-end run told the "
     "orchestrator not to read a named project path, which handed it the address of the "
     "held-out data in the act of forbidding it. Both wordings are checked the same way -- "
     "grep the transcript, expect zero -- so naming the path buys nothing and leaks a target."),

    ("standard-is-not-project-content",
     "Isolation withholds the project, never the authoring standard.",
     (SKILL_PATH,),
     "The other side of the isolation rule, and the one a session gets wrong by being "
     "thorough. On the first end-to-end run B and C were denied the required section shape "
     "and the existence of the routing gate along with the project, so the draft came back "
     "with no `## Trigger precision` section and could not be gated at all. Neither cold "
     "reviewer could have caught it: a stranger cannot audit a convention they were never "
     "told."),

    ("quiesce-before-reading",
     "Nothing reads a draft while its author is still writing it.",
     (SKILL_PATH,),
     "The acceptance tester on the first end-to-end run reported the skill file changing "
     "underneath it, because the builder was applying fixes concurrently, so that review "
     "scored a file nobody shipped. Same hazard `docs/DESIGN.md` records from the other "
     "side for a script edited while it executes. A message saying `done` is not the "
     "confirmation; a marker file and an unchanged checksum are."),

    ("state-the-cost-bound",
     "The skill must state when it is not worth its own cost.",
     (SKILL_PATH,),
     "Raised by stage E against criteria A had pre-registered, which never asked for it. A "
     "reader who already suspects the procedure is more expensive than the problem is the "
     "one who abandons it halfway and does not say so; without a stated bound the skill has "
     "no exit ramp to offer them, and the forge has nowhere to record the judgement."),

    ("verdict-follows-the-apply",
     "A verdict is recorded after the skill has been applied to the problem that caused "
     "it, never before.",
     (SKILL_PATH,),
     "`skillforge verdict` had 0 rows in 807, and five of six closed forges had no `apply` "
     "row either. Both debts close in the same turn because that turn is the only moment "
     "anyone holds both the skill and the problem; a verdict written any earlier judges a "
     "text rather than an event."),

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
    """The cap moved 3 -> 5 in the skill and stayed 3 in the long-form doc for a release."""

    def cap(self):
        m = re.search(r"Cap at (\d+) rounds", SKILL)
        self.assertIsNotNone(m, "SKILL.md no longer states a round cap in a parseable form")
        return int(m.group(1))

    def test_the_protocol_doc_states_the_same_cap(self):
        self.assertRegex(
            PROTOCOL, r"cap at %d rounds" % self.cap(),
            "%s's forging diagram disagrees with SKILL.md about the round cap"
            % PROTOCOL_DOC,
        )

    def test_escalated_cap_agrees(self):
        """Both name the same number for a complex or important skill."""
        skill_hi = re.search(r"or (\d+) for a skill that is complex", SKILL)
        self.assertIsNotNone(skill_hi, "SKILL.md no longer states an escalated cap")
        self.assertIn(
            "(%s for a complex" % skill_hi.group(1), PROTOCOL,
            "%s and SKILL.md disagree about the escalated round cap" % PROTOCOL_DOC,
        )

    def test_status_line_example_budgets_the_documented_cap(self):
        """SKILL.md budgets steps as 2 + 2 x rounds. The doc's examples must show that.

        Defeated twice. First: `re.search` took the FIRST bar in the file, so adding a
        second example with a different budget ("the usual 5-round cap is a 6-step forge")
        left the suite green while the README taught the wrong arithmetic. Then: "every
        bar" was a lie, because the hardcoded glyph class `[█·]` did not include `▓`, which
        is what the renderer draws for the partly filled cell -- an example written with
        the real glyph was not a bar as far as this test was concerned. `BAR` is built from
        the renderer now.
        """
        # Both documents are read, not only the one the example sits in: a second bar
        # written into the README would otherwise teach a budget nothing checks.
        bars = [(doc, b) for doc, text in (("README.md", README), (PROTOCOL_DOC, PROTOCOL))
                for b in BAR.findall(text)]
        self.assertTrue(bars, "the status-line example is no longer parseable in %s"
                        % PROTOCOL_DOC)
        for doc, (step, total) in bars:
            self.assertEqual(
                int(total), 2 + 2 * self.cap(),
                "an example forge in %s budgets %s steps, which is not 2 + 2 x the "
                "%d-round cap SKILL.md states" % (doc, total, self.cap()))


class OrphanedConstantTest(unittest.TestCase):
    """A doc must not attribute a threshold constant to a skill that has dropped it."""

    def test_no_doc_cites_a_duration_the_skill_does_not_have(self):
        """Both directions a doc can name a duration: a `>N min` threshold and an
        `under N min` target.

        The pattern was `>\\s?(\\d+)\\s?min` alone, which made this test vacuous the day
        the skill dropped its last `>N min` threshold -- nothing in either document
        matched, so nothing was checked. The forge diet then put "under 30 minutes" into
        the README and the skill at once, which is exactly the pair that drifts.
        """
        pattern = re.compile(r"(?:>|under )\s?(\d+)\s?min")
        for name, text in (("README.md", README), (".claude/CLAUDE.md", REPO_CLAUDE),
                           (PROTOCOL_DOC, PROTOCOL), ("docs/operations.md", OPERATIONS),
                           ("docs/measurement.md", MEASUREMENT),
                           ("docs/development.md", DEVELOPMENT)):
            for cited in pattern.findall(text):
                self.assertRegex(
                    SKILL, r"(?:>|under )\s?%s\s?min" % cited,
                    "%s cites a %s-minute figure that SKILL.md does not define"
                    % (name, cited),
                )


# --------------------------------------------------------------------- counted claims
# A sentence may state how many knobs there are. The check that reads those
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
    """The integer a numeral in the docs denotes, or None if it does not denote one.

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

# A table of knobs, wherever in a document it sits: the two leading columns are the
# signature. Anything matching this is checked, so a third table needs no test edit.
VAR_TABLE = re.compile(r"^\|Variable\|Default\|[^\n]*\n\|(?:-\|)+\n((?:\|[^\n]*\n)+)", re.M)

# Every document that carries a knob table. The main tuning table moved to
# `docs/operations.md` with the docs split; the session review's five rows stayed in the
# README, beside the disclosure that says the review spends money, which is the only place
# its off switch is any use. Both are read, so a row cannot hide by being in the other file.
KNOB_DOCS = (("README.md", README), ("docs/operations.md", OPERATIONS))


class TuningTableTest(unittest.TestCase):
    """Every knob the hook actually reads has to be findable in the documentation."""

    def hook_vars(self):
        found = {v for v in re.findall(r"CI_[A-Z_]+", HOOK) if not PIN.search(v)}
        self.assertTrue(found, "no tunable CI_* variables found in the hook")
        return found

    def tables(self):
        """Every knob table in every knob document, as (doc, position, rows).

        Not just the one under `## Tuning`. The session review documents its knobs beside
        the disclosure that says it calls an API and costs money, which is the only place
        its off switch is any use; merging them into the tuning table would move that
        switch into a different file from the paragraph a reader needs it in. The
        documents keep the shape they need and the test follows them, rather than the five
        review rows sitting outside every assertion here because one table was all this
        knew how to read. Position is per document, since that is what `section_of` reads.
        """
        out = []
        for doc, text in KNOB_DOCS:
            for m in VAR_TABLE.finditer(text):
                rows = re.findall(r"^\|`([^`|]+)`\|([^|]*)\|", m.group(1), re.M)
                self.assertEqual(
                    len(rows), len(m.group(1).strip().splitlines()),
                    "a knob table in %s has a row this cannot read: every row must open "
                    "`|`NAME`|` and its default cell must not contain a `|`" % doc)
                out.append((doc, m.start(), rows))
        self.assertTrue(out, "no |Variable|Default| knob table in %s"
                        % " or ".join(d for d, _ in KNOB_DOCS))
        return out

    def all_rows(self):
        return [row for _doc, _pos, rows in self.tables() for row in rows]

    def table_rows(self):
        """Just the names, from every table in every knob document."""
        return [var for var, _ in self.all_rows()]

    def section_of(self, doc, pos):
        """The `##` section of `doc` containing `pos`, as (start, end)."""
        text = dict(KNOB_DOCS)[doc]
        starts = [m.start() for m in re.finditer(r"^## ", text, re.M)]
        lo = max([s for s in starts if s <= pos], default=0)
        hi = min([s for s in starts if s > pos], default=len(text))
        return lo, hi

    def tables_near(self, doc, pos):
        """Rows of every knob table in the same `##` section of the same document."""
        lo, hi = self.section_of(doc, pos)
        return [rows for d, start, rows in self.tables() if d == doc and lo <= start < hi]

    def find_once(self, pattern, what):
        """(doc, match) for a counted sentence that must sit in exactly one knob document.

        Stated in neither, nothing is checked; stated in both, two numbers drift against
        one table. Either way this fails and names which.
        """
        hits = [(doc, m) for doc, text in KNOB_DOCS
                for m in [re.search(pattern, text)] if m]
        self.assertEqual(
            len(hits), 1,
            "the sentence stating %s must appear in exactly one knob document; found it "
            "in %s" % (what, ", ".join(d for d, _ in hits) or "none of them"))
        return hits[0]

    def test_every_tunable_the_hook_reads_is_documented(self):
        for var in sorted(self.hook_vars() - set(self.table_rows())):
            self.fail("hooks/compound-improvement.sh reads %s but no tuning table in %s "
                      "lists it" % (var, " or ".join(d for d, _ in KNOB_DOCS)))

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
                "the docs document %s but nothing in bin/, hooks/ or statusline/ "
                "reads it" % var)

    def test_no_knob_is_documented_in_two_places(self):
        """One row per knob, across all tables: two rows are two defaults to keep in step,
        and the one nobody edits is the one a reader finds first."""
        seen = self.table_rows()
        for var in sorted(set(seen)):
            self.assertEqual(seen.count(var), 1,
                             "%s has %d documented rows across %s; a knob gets exactly one"
                             % (var, seen.count(var),
                                " and ".join(d for d, _ in KNOB_DOCS)))

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
                real, "the docs document a default for %s but no script defaults it" % var)
            literal = re.fullmatch(r"`([^`]+)`", cell.strip())
            if literal is None:
                self.assertEqual(
                    real.group(1), "",
                    "the docs describe %s's default in prose (%r) but the script defaults "
                    "it to %r; state a real default as a backticked literal"
                    % (var, cell.strip(), real.group(1)))
                continue
            # `$HOME/x` and `~/x` are the same path written two ways; everything else
            # has to match character for character.
            norm = lambda s: s.replace("$HOME", "~").replace("${HOME}", "~")
            self.assertEqual(
                norm(literal.group(1)), norm(real.group(1)),
                "the docs say %s defaults to %s; the script defaults it to %s"
                % (var, literal.group(1), real.group(1)))

    def test_stated_counts_match_the_table(self):
        tables = self.tables()
        doc, total = self.find_once(r"All ([\w-]+) are environment variables",
                                    "how many tunables there are")
        stated = count_word(total.group(1))
        self.assertIsNotNone(
            stated, "%s states a tunable count as %r, which is not a number "
            "`count_word` can read" % (doc, total.group(1)))
        local = self.tables_near(doc, total.start())
        self.assertEqual(len(local), 1,
                         "the sentence stating how many tunables there are is no longer in "
                         "a section with exactly one knob table, so nothing knows which "
                         "table it counts")
        self.assertEqual(stated, len(local[0]),
                         "%s says there are %s tunables; the table in that section "
                         "lists %d" % (doc, total.group(1), len(local[0])))
        doc, ci = self.find_once(r"Only the ([\w-]+) `CI_\*` variables",
                                 "how many CI_* vars the hook reads")
        local = self.tables_near(doc, ci.start())
        self.assertEqual(len(local), 1,
                         "the CI_* count sentence is no longer in a section with exactly "
                         "one knob table")
        self.assertEqual(count_word(ci.group(1)),
                         len([v for v, _ in local[0] if v.startswith("CI_")]),
                         "%s's CI_* count disagrees with the table beside it" % doc)
        # Defeated before: both counts above are pinned to one sentence each, so a THIRD
        # sentence with a different number ("Six knobs actually do anything") contradicted
        # the table with the suite green. Any counted claim about the knobs has to agree
        # with the table in its own section -- and with some real count anywhere else,
        # which is the weaker half of this and the reason a claim about knobs belongs in
        # the section whose table it counts.
        every = [len(rows) for _d, _p, rows in tables]
        for doc, text in KNOB_DOCS:
            for m in COUNTED_CLAIM.finditer(text):
                stated = count_word(m.group(1))
                self.assertIsNotNone(stated, "unreadable numeral %r" % m.group(1))
                local = self.tables_near(doc, m.start())
                allowed = ([len(rows) for rows in local] if local
                           else every + [sum(every)])
                self.assertIn(
                    stated, allowed,
                    "%s says %s %s; the knob table(s) it is counting list %s rows"
                    % (doc, m.group(1), m.group(2),
                       " or ".join(str(n) for n in sorted(set(allowed)))))


class DerivationCommandTest(unittest.TestCase):
    """`docs/operations.md` hands the reader a command and claims it prints every name any
    shipped script reads. That is a completeness claim, and unlike a claim about prose it
    is decidable: run the command the document actually carries -- not a copy retyped
    here -- and compare it against the names the scripts really read.

    This is what stands in for listing every knob in the tables. The tables are explicitly
    not the whole set; the command is, so the command is what gets checked.
    """

    # Read by a shipped script, owned by something else: the shell, or a tool the script
    # shells out to. Everything not on this list is ours and must be findable by the
    # documented command. The list is short and deliberately hand-maintained, so adopting
    # a new prefix means editing it in a commit a reviewer can see -- the same reason the
    # doctrine sentences above are pinned rather than derived.
    AMBIENT = {"HOME", "PATH", "PWD", "SHELL", "TMPDIR", "RANDOM", "IFS", "LANG", "LC_ALL",
               "CLAUDE_CONFIG_DIR", "GH_TOKEN", "GITHUB_TOKEN",
               # Exported by Claude Code into every process a session starts. `skillforge
               # apply` reads it so a ledger row can say which session closed the loop,
               # and `bin/skillforge`'s own header explains at length that it is NOT the
               # id a hook payload carries. Ours to read, never ours to set, so it belongs
               # here rather than in a tuning table nobody could act on.
               "CLAUDE_CODE_SESSION_ID",
               # claude-history-surfer's OWN data-directory override, read by
               # hooks/mission.sh so that hook resolves the prompt store exactly the way
               # its writer does (history_surfer/config.py:37-42). Same judgement as
               # CLAUDE_CONFIG_DIR above: ours to read, never ours to set, so a tuning
               # table row for it would document somebody else's knob as ours.
               "CLAUDE_HISTORY_SURFER_DIR"}

    DOC = "docs/operations.md"

    def command(self):
        i = OPERATIONS.find("prints every")
        self.assertNotEqual(
            i, -1,
            "%s no longer offers a command that prints every name a script reads" % self.DOC)
        m = re.search(r"```bash\n(.*?)```", OPERATIONS[i:], re.S)
        self.assertIsNotNone(m, "%s's derivation command is no longer in a ```bash fence "
                                "right after the sentence promising it" % self.DOC)
        return m.group(1)

    def test_the_documented_command_runs_and_prints_names(self):
        out = subprocess.run(["bash", "-c", self.command()], cwd=str(ROOT),
                             capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(out.returncode, 0,
                         "%s's derivation command fails from the repo root: %s"
                         % (self.DOC, out.stderr.strip()))
        self.assertTrue(out.stdout.split(),
                        "%s's derivation command prints nothing" % self.DOC)

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
            self.fail("%s says its command prints every name any shipped script reads, "
                      "but %s is read by a script and the command does not print it"
                      % (self.DOC, name))

    def test_the_documented_command_finds_every_documented_knob(self):
        printed = self.printed()
        for var in TuningTableTest("test_no_documented_tunable_is_imaginary").table_rows():
            self.assertIn(var, printed,
                          "the docs document %s in a table but the command %s offers as "
                          "the full list does not print it" % (var, self.DOC))


class ForgeDiagramTest(unittest.TestCase):
    """The forging diagrams are structure, not prose, so their shape is decidable.

    This is the only guard in this file that reads the long-form document's account of the
    protocol beyond a pinned sentence, and it can be, because ASCII tree indentation has a
    parse. The first version asserted only that the word "orchestrator" appeared somewhere
    in the document, which passes against a diagram that still hangs the builder off the
    main session. Bind the nesting instead.

    There are TWO diagrams since the forge diet: the default shape, where the session
    dispatches the builder and the reviewer itself, and the escalated shape, where an
    orchestrator takes the loop from the granted round on. Each is checked for the nesting
    it is supposed to have, and the escalated one is also checked against the condition
    `SKILL.md` states for reaching it -- so a README that keeps the old picture, or that
    keeps the new one and drops the old, fails here either way.
    """

    def diagrams(self):
        found = re.findall(r"```\nskillforge start.*?```", PROTOCOL, re.S)
        self.assertEqual(
            len(found), 2,
            "%s no longer carries exactly two `skillforge start` diagrams (the default "
            "forge and the escalated one); found %d" % (PROTOCOL_DOC, len(found)))
        return found

    @staticmethod
    def _index(lines, role, fail):
        for i, line in enumerate(lines):
            if re.search(r"[├└]─ %s" % re.escape(role), line):
                return i
        fail("the diagram omits %r" % role)

    def test_the_default_diagram_hangs_the_builder_and_reviewer_off_the_session(self):
        """No orchestrator in the default forge, and the builder and the reviewer are
        children of the session rather than of anything else."""
        lines = self.diagrams()[0].splitlines()
        self.assertNotIn(
            "orchestrator", self.diagrams()[0],
            "the FIRST forging diagram in %s still shows an orchestrator; the default "
            "forge dispatches the builder and the reviewer from the session itself"
            % PROTOCOL_DOC)
        session = self._index(lines, "A: this session", self.fail)
        depth = len(lines[session]) - len(lines[session].lstrip())
        for role in ("builder", "red-team", "loop"):
            i = self._index(lines, role, self.fail)
            self.assertEqual(
                len(lines[i]) - len(lines[i].lstrip()), depth,
                "the default diagram must place %r at the same depth as the session's own "
                "row, i.e. dispatched by the session: %r" % (role, lines[i].strip()))

    def test_the_escalated_diagram_still_nests_the_loop_under_the_orchestrator(self):
        if "orchestrator" not in FORGING:
            self.fail("SKILL.md no longer brings an orchestrator back on an escalated "
                      "forge, so this test needs re-deriving")
        lines = self.diagrams()[1].splitlines()

        def line_of(role):
            return self._index(lines, role, self.fail)

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
                "the escalated diagram must place %r after the orchestrator that "
                "dispatches it" % role)
            child = len(lines[i]) - len(lines[i].lstrip())
            self.assertGreater(
                child, orch,
                "the escalated diagram must nest %r *under* the orchestrator" % role)
            for between in lines[orch_i + 1:i]:
                if not between.strip():
                    continue
                depth = len(between) - len(between.lstrip())
                self.assertGreater(
                    depth, orch,
                    "the escalated diagram breaks out of the orchestrator's subtree before "
                    "reaching %r, so %r hangs off something else: %r"
                    % (role, role, between.strip()))

    def test_the_condition_for_the_second_diagram_is_the_cap_the_skill_states(self):
        """The escalated shape is reached at a stated number of rounds, and that number is
        the cap, not a second constant. Derived from `SKILL.md` on both sides."""
        m = re.search(r"budget exceeds (\w+) rounds", FORGING)
        self.assertIsNotNone(
            m, "the forging protocol no longer states the condition under which the "
               "orchestrator and the judge come back, so the second diagram documents a "
               "shape nothing can be reached from")
        stated = count_word(m.group(1))
        self.assertIsNotNone(stated, "unreadable numeral in %r" % m.group(0))
        cap = re.search(r"Cap at (\d+) rounds", SKILL)
        self.assertIsNotNone(cap, "SKILL.md no longer states a round cap")
        self.assertEqual(
            stated, int(cap.group(1)),
            "the protocol brings the orchestrator back past %d rounds but caps the loop at "
            "%s; one of the two numbers moved on its own" % (stated, cap.group(1)))


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
        # `skillforge done` was here until 2026-08-31 and was the WRONG recovery: it
        # records a forge that never finished as completed and installs its skill. The
        # honest closes are `fail` (it died, with a reason) and `clear` (discard it).
        for token in ("skillforge fail", "skillforge clear", "--name"):
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
                           ("README.md", README), (PROTOCOL_DOC, PROTOCOL),
                           ("docs/operations.md", OPERATIONS),
                           ("docs/measurement.md", MEASUREMENT),
                           ("docs/development.md", DEVELOPMENT)):
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
                           ("README.md", README), (".claude/CLAUDE.md", REPO_CLAUDE),
                           (PROTOCOL_DOC, PROTOCOL), ("docs/operations.md", OPERATIONS),
                           ("docs/measurement.md", MEASUREMENT),
                           ("docs/development.md", DEVELOPMENT)):
            for retired in RETIRED_WORDING:
                self.assertNotIn(
                    retired, text,
                    "%s carries %r, a sentence from the retired single-forge doctrine. "
                    "Forges are concurrent; a session that obeys it stalls, or drops its "
                    "animation and its ledger row, for a collision that cannot happen"
                    % (name, retired))


class SeedPoolTest(unittest.TestCase):
    """Adding a skill to skills/ without adding its inventory row is the same drift.

    It happened: `ai-tell-audit` shipped, and the pool section kept describing four seed
    skills and a pool that did not contain it. Both inventory tables moved to
    `docs/architecture.md` with the docs split; the counted claims are read from the README
    as well, because the README still describes the pool in passing and a second number
    there would drift against the table just as easily.
    """

    # Where the two inventory tables live, and every document that may state their size.
    INVENTORY = PROTOCOL_DOC
    COUNTED_IN = (("README.md", README), (PROTOCOL_DOC, PROTOCOL))

    def shipped(self):
        return sorted(d.name for d in (ROOT / "skills").iterdir()
                      if (d / "SKILL.md").is_file())

    def table_rows(self):
        m = re.search(r"\|Skill\|Fires when\|The failure it prevents\|\n\|-\|-\|-\|\n((?:\|.*\n)+)",
                      PROTOCOL)
        self.assertIsNotNone(m, "%s's seed-pool table is missing or reshaped" % self.INVENTORY)
        return re.findall(r"^\|`([^`]+)`\|", m.group(1), re.M)

    def install_table_rows(self):
        """The `skills/<name>/` entries in the "What gets installed" table."""
        m = re.search(r"\|Piece\|What it does\|\n\|-\|-\|\n((?:\|.*\n)+)", PROTOCOL)
        self.assertIsNotNone(
            m, "%s's 'What gets installed' table is missing or reshaped" % self.INVENTORY)
        return re.findall(r"^\|`skills/([^/`]+)/`\|", m.group(1), re.M)

    def test_every_shipped_skill_is_documented(self):
        """A skill nobody mentions is a skill nobody finds.

        This assertion was weakened once, and wrongly: it failed because the docs said
        "Five skills ship" while seven directories shipped, and the response was to relax
        it to "the name appears somewhere in the document" instead of asking whether the
        prose was right. A bare substring passes on an incidental mention in a code
        sample. Every shipped skill has to be documented in one of the two places a reader
        looks for the inventory: a row in the seed-pool table, or its own row in "What
        gets installed" (which is where the machinery skills -- `skill-compounder`,
        `contribute-skill`, `skill-authoring` -- belong, since they are not day-one
        seed skills).
        """
        documented = set(self.table_rows()) | set(self.install_table_rows())
        for name in self.shipped():
            # assertIn against the document would print the whole file on failure. A
            # 20 KB dump for a one-word finding is output nobody reads.
            self.assertIn(
                name, documented,
                "skills/%s ships but no table in %s lists it: put it in the seed-pool "
                "table if a fresh install should reach for it on day one, or give it a "
                "`skills/%s/` row in 'What gets installed' if it is machinery"
                % (name, self.INVENTORY, name))

    def test_no_row_describes_a_skill_that_does_not_ship(self):
        shipped = set(self.shipped())
        for name in self.table_rows():
            self.assertIn(name, shipped,
                          "%s documents a seed skill `%s` that does not ship"
                          % (self.INVENTORY, name))

    def test_the_stated_pool_size_matches(self):
        """And it is stated once.

        The README used to carry the count in three places ("five seed skills" in the
        intro, "(five more)" in the install table, "Five skills ship with the package" in
        the pool section) while seven skill directories shipped, which is both ambiguous
        -- five of what? -- and three chances to drift. So: every counted claim about how
        many skills ship has to agree with the pool table, wherever it is written. The
        docs split gave the count a second document to drift in, so both are scanned.
        """
        words = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10}
        found = 0
        for doc, text in self.COUNTED_IN:
            counted = re.findall(
                r"\b(three|four|five|six|seven|eight|nine|ten)\s+(?:more\s+|seed\s+)*"
                r"(?:skills?\b|of\s+the\s+(?:entries|rows|skills)\b)",
                text, re.I)
            found += len(counted)
            for word in counted:
                self.assertEqual(
                    words.get(word.lower()), len(self.table_rows()),
                    "%s says %s skills; the seed-pool table lists %d. State the count "
                    "once, in the pool section, and say what it counts"
                    % (doc, word, len(self.table_rows())))
        self.assertTrue(found, "neither %s states the seed-pool size"
                        % " nor ".join(d for d, _ in self.COUNTED_IN))


class HeldOutIsConstructionNotInstructionTest(unittest.TestCase):
    """Step 2 makes a claim about the CLI. The CLI has to actually do it.

    The forging protocol's organising claim is that the original project is held-out test
    data. C and D are denied it by construction; B was denied it only by a sentence in
    its brief, while being handed `skillforge` and told to call `step`. Step 2 now says
    the CLI holds those fields back -- which is a claim about a program, and this file's
    rule for a claim about a program is to run it.

    The two directions are separate failures. A sentence that outran the tool sends B to
    a command that leaks; a tool that outran the sentence leaves the next author
    believing the isolation is still a rule they may relax.
    """

    HELD = ("root", "trigger", "project", "trigger_verbatim")

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        state = Path(cls._tmp.name)
        cls.trigger = "the verbatim thing a user typed, which B must never hold"

        def cli(*args):
            return subprocess.run(
                [str(ROOT / "bin" / "skillforge"), *args],
                capture_output=True, text=True, stdin=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                     "HOME": str(state), "SKILL_COMPOUNDER_STATE": str(state)})

        cli("start", "held-out", "12", "a summary",
            "--trigger", cls.trigger, "--trigger-kind", "user-prompt")
        cls.shown = cli("show", "--name", "held-out")
        cls.shown_full = cli("show", "--full", "--name", "held-out")
        cls.rows = cli("ledger", "--json")
        cls.state = state

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def sentence(self):
        m = re.search(r"Do \*\*not\*\* hand a dispatched agent the project.*?\n\n",
                      SKILL, re.S)
        self.assertIsNotNone(
            m, "the forging protocol no longer tells the orchestrator's dispatcher what "
               "to withhold, so there is nothing left for this test to check")
        return flatten(m.group(0))

    def test_the_protocol_claims_the_cli_withholds_them(self):
        said = self.sentence()
        self.assertIn("`--full`", said,
                      "step 2 states the isolation as a rule B is asked to obey, with no "
                      "mention of the flag that makes it a property of the tool")
        for field in self.HELD:
            self.assertIn("`%s`" % field, said,
                          "step 2 does not name `%s` among the fields the CLI holds "
                          "back" % field)

    def test_the_cli_actually_withholds_them(self):
        self.assertEqual(self.shown.returncode, 0, self.shown.stderr)
        self.assertNotIn(self.trigger, self.shown.stdout)
        self.assertNotIn(self.trigger, self.rows.stdout)
        shown = json.loads(self.shown.stdout)
        for field in self.HELD:
            self.assertNotIn(field, shown)
        for line in self.rows.stdout.splitlines():
            if not line.strip():
                continue
            for field in self.HELD:
                self.assertNotIn(field, json.loads(line))

    def test_the_record_keeps_what_the_view_withholds(self):
        """`--full` is for A, who owns the test set, and the file is never filtered:
        `bin/skillreport` reads it directly and E gets the trigger from A by hand."""
        self.assertIn(self.trigger, json.loads(self.shown_full.stdout)["trigger"])
        self.assertIn(self.trigger,
                      (self.state / "ledger.jsonl").read_text(encoding="utf-8"))


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
            try:
                description = __import__("yaml").safe_load(front)["description"]
            except ImportError:
                # A clean-environment run (`env -i ... /usr/bin/python3`) has no
                # PyYAML. The routing gate's own parser reads the same field with
                # the stdlib, so the budget is checked by the reader that enforces
                # it rather than skipped where the wheel is absent.
                import sys
                sys.path.insert(0, str(ROOT / "scripts"))
                from routing_claims import _frontmatter_description
                description = _frontmatter_description("---\n" + front + "---\n")
            self.assertLessEqual(
                len(description), desc_max,
                "skills/%s description is %d characters against the %d `skill-authoring` "
                "documents. Padding makes the listing drop it under context pressure, "
                "which is the failure the budget is for"
                % (name, len(description), desc_max))
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
