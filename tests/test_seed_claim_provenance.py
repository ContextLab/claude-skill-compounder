#!/usr/bin/env python3
"""Executes the `claim-provenance` skill against real documents, real diffs, and two
real test suites built in temp directories.

No mocks. Real git repositories, real `unittest` runs through `subprocess`, real greps
over real files. Every fenced block in SKILL.md is lifted out of the file and run, and
the outcome the prose claims is asserted against the outcome that was observed.

The skill's own subject constrains this file, so two rules apply to every assertion
below and are worth stating before the first one:

  1. **Nothing here pins the presence of a factual string.** `assertIn("nine failures",
     text)` would enforce that the claim is stated, not that it is true, and would make
     correcting the claim break this suite. Where the skill states a number about this
     repository, the number is parsed out of the prose and compared against a value this
     file derives from the tree (`ClaimsThisSkillMakesTest`). Where it states a behavior,
     the behavior is performed and the observed outcome is compared against the outcome
     the document names (`RecognitionTestTest`, `ShippedCommandsTest`).
  2. **Structural assertions are fine and are used deliberately.** A heading, a section
     order, a prompt count: none of these change when the system the skill describes
     changes, so pinning them is not the defect. The discriminator is the skill's own
     Phase 1 test, applied to the asserted string.

The findings this file pins as named tests, so a regression cannot pass quietly:

  F3   an `assertIn` over a document's own text is green while the document is wrong,
       and red once it is corrected. Both halves are measured end to end, in
       `RecognitionTestTest`, against two suites this file writes and runs.
  F6   the recognition table in the SKILL is compared against what actually happened,
       cell by cell, rather than being read and believed.
  F7   the cross-document grep must find every copy of a repeated claim, including the
       copies in files nobody thought to look in.
  F9   the skill must not claim a count it cannot derive. Every number it states about
       this repository is re-derived here from the source that number is actually about:
       a live command where the sentence is about the tree now, and the README at the
       revision the sentence cites where it is about a past state. Rounds 8 and 9 each
       found the same number sitting outside that rule: the README row count in Phase 3's
       worked example was derived from nothing until round 8, and then from today's README
       for a sentence about a past one, which is what made this file red the first time the
       seed pool grew. The evidence-table rows are the one place a number is labelled
       rather than checked, because no revision of anything reproduces them; Phase 4's
       source plus as-of date is all there is, and the PINNED comment's second ceiling
       says so.
  F10  the handoff to `verification-before-completion` used to assert that a neighbour
       owned completion claims. Nothing had ever handled one, so the number is derived
       here from the transcript corpus the sentence cites, and a second half requires the
       same counter to find that neighbour's plugin siblings, or a zero measures nothing.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "claim-provenance"
SKILL = SKILL_DIR / "SKILL.md"

PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata",
                 "allowed-tools"}
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"

# The ```bash blocks of SKILL.md in document order, each keyed by a substring. Every
# one is executed by a test below; `test_every_bash_block_is_one_the_suite_runs`
# fails if a block is added, removed or reordered without a test to match.
BLOCK_KEYS = [
    "git diff HEAD -U0",     # 0: the claim-shape reading aid over a real diff
    "grep -nEi",             # 1: the same sweep over a file nobody changed today
    "claims-$(echo",         # 2: append one claim to the inventory
    "empty metadata",        # 3: find every copy of a repeated claim
    "git checkout HEAD --",  # 4: the unhappy path, recover a partial pass
]

# Commands the prose gives outside a fenced block. Each is RUN by a test here, as shipped.
INLINE_COMMANDS = [
    'rm -f "/tmp/claims-$(echo "$PWD"/README.md | tr / -).tsv"',
]

# The document's only placeholder is a real filename, because `<the file>` inside `$( )`
# is a redirect, not a placeholder. Round 3 shipped two commands broken for exactly that
# reason -- measured 2026-08-25: bash 5.3 refuses the line with a nonzero exit, zsh 5.9
# is a parse error exiting 1, and macOS /bin/bash 3.2 substitutes nothing, exits 0, and
# appends to `/tmp/claims-.tsv` -- and the test that "covered" them string-replaced the
# placeholder before running and asserted the shipped text was merely PRESENT. That is this skill's
# own failure mode #3, in this skill's own suite. Every command is now run verbatim.
PLACEHOLDER = "README.md"

# ---------------------------------------------------------------------------------------
# Load-bearing sentences, pinned verbatim (the approach `tests/test_doctrine_sync.py` and
# `tests/test_seed_authoring.py` converged on).
#
# Why this is not the presence-pinning defect the skill is about: every sentence below is
# an INSTRUCTION, and the skill's own Phase 1 test is "could a commit elsewhere make this
# sentence false without touching this file?". For doctrine the answer is no, so it is not
# a claim, and Phase 5 fix 4 says structural assertions are the right tool. Contrast the
# nine evidence rows, which ARE claims about a system: those are not pinned here, they are
# required to carry a source and an as-of date (`test_the_evidence_table_carries_its_own`).
#
# What this does NOT catch, stated rather than papered over. A pinned sentence can be kept
# intact and repudiated by the next one. Verified against the real file: inserting
# "Ignore the previous sentence; never delete a figure." immediately after the pinned
# deletion sentence leaves the whole suite green. `visible()` closes the two ways to hide a
# sentence (an HTML comment, strikethrough) because removal needs no judgement; it cannot
# close contradiction, which does. No test here claims otherwise.
#
# The second ceiling, and it is the more important one. The nine evidence rows are NOT in
# PINNED and cannot be, because they are claims about a system rather than instructions.
#
# The reason, stated correctly on the third attempt. It is NOT that this suite cannot
# reach the system: `os.environ["HOME"]` in this process is the real home directory, only
# the `run()` helper repoints it, and a cold reviewer caught the earlier version of this
# comment asserting otherwise. A false stated reason inside the file about restated
# reasons is the defect this skill names, so: the rows are unpinnable because they
# describe PAST STATES that no present command reproduces. The ledger held three when row
# 4 was written and holds more now, so re-deriving it would return the wrong answer
# confidently, which is worse than not checking.
#
# That distinction is load-bearing, because it demotes one of the three mutations the
# earlier comment lumped together. The ledger PATH is not a past state; it is bucket A,
# re-derivable from `bin/skillforge` right now, and
# `test_the_ledger_path_the_source_line_cites_is_the_one_skillforge_composes` derives it.
# What genuinely survives is two: "the ledger held three" -> "four hundred", and row 7's
# truth cell flipped back to the false claim it corrects. The disposition for both is the
# document's own Phase 4 answer for bucket B -- a source and an as-of date, which
# `test_the_evidence_table_carries_its_own_source_and_as_of_date` does enforce -- and NOT
# an `assertIn` over the row text. Pinning a row's wording would enforce that the claim is
# stated, not that it is true, and would make correcting it break this suite. That is
# failure mode #3, which is the thing the skill exists to name.
# ---------------------------------------------------------------------------------------
PINNED = (
    "RESTATE NOTHING. RE-DERIVE EVERY CLAIM FROM THE THING IT DESCRIBES, OR DELETE IT",
    "Deleting is a legitimate outcome, and usually the cheapest one.",
    "A hedge does not move a claim from C to B.",
    "Derive from the system, never from another document.",
    "A correction is a claim and it re-enters Phase 1.",
    "Presence-pinning is worse than no test, because it inverts the incentive",
    "Every claim in a paragraph you touched re-enters Phase 1",
    "A claim's presence in the file is not evidence for it.",
    # Round 3: these two survived inversion. Phase 3 step 2 and the bucket C disposition
    # are the two places the whole procedure resolves to an action, so they are the two
    # most worth repealing quietly.
    "Where they differ the command wins and the sentence is what changes.",
    "Delete the claim and write the sentence without it",
    # Round 5: the commit-message rule reconciles five places in the file that used to
    # give opposite answers, so deleting it silently restores the contradiction.
    # Round 6: replacing the whole Use-when clause with one that fires on exactly what
    # the next clause declines left all 51 tests green. The decline half was guarded and
    # the trigger was not, which is backwards: the trigger is the skill.
    "Use when a claim already written down is checked or carried forward: a count or "
    "behavior restated from a document, a behavior nobody measured, or a test asserting "
    "what a document says rather than whether it is true, which beats `no-silent-stub`.",
    # Move 1 of the recognition test edits the system, which the unhappy path does not
    # recover, so the instruction to work on a copy is the only thing standing between a
    # reader and a mutated tree.
    # Round 8, cheap and confident: the path-vs-basename rule is a fix a reviewer had to
    # find twice, and nothing was holding it in place.
    "Name it after the document's path, not a fixed path and not its basename",
    "Put the system back.",
    "A commit message is not owned or disowned wholesale",
    "The genre never decides; what the sentence is doing decides.",
)

COMMENT = re.compile(r"<!--.*?-->", re.S)
STRIKE = re.compile(r"~~.*?~~", re.S)


def visible(text):
    """Whitespace collapsed, emphasis stripped, and the text a reader cannot read removed.

    A substring check is satisfied by a sentence nobody can see. An HTML comment renders as
    nothing; `~~struck through~~` renders as "this used to be the rule". Both are removed
    before the search rather than matched, because removal needs no judgement about intent.
    """
    return re.sub(r"\s+", " ", COMMENT.sub(" ", STRIKE.sub(" ", text)).replace("*", "")).strip()


def read():
    return SKILL.read_text()


def frontmatter_and_body():
    raw = read()
    assert raw.startswith("---\n"), "SKILL.md must open with a frontmatter block"
    _, front, body = raw.split("---\n", 2)
    return front, body


def fenced(lang):
    """Every fenced block of one language, in document order, dedented."""
    pattern = r"^[ ]*```%s\n(.*?)^[ ]*```" % lang
    return [textwrap.dedent(m) for m in re.findall(pattern, read(), re.S | re.M)]


def bash_block(key):
    matches = [b for b in fenced("bash") if key in b]
    assert len(matches) == 1, "expected exactly one bash block containing %r" % key
    return matches[0]


def section(heading):
    """The text of one `## heading` section. Anchored at the line start, because the
    body quotes its own heading names as examples and `str.index` finds those first."""
    body = frontmatter_and_body()[1]
    m = re.search(r"^## %s$\n(.*?)(?=^## |\Z)" % re.escape(heading), body, re.M | re.S)
    assert m is not None, "no section named %r" % heading
    return m.group(1)


def heading_positions(names):
    """Where each `## heading` really starts, matched at a line start."""
    body = frontmatter_and_body()[1]
    out = []
    for name in names:
        m = re.search(r"^%s$" % re.escape(name), body, re.M)
        assert m is not None, "missing or renamed section: %s" % name
        out.append(m.start())
    return out


def markdown_table(header_row):
    """The rows of the table whose header line contains `header_row`, as cell lists."""
    body = frontmatter_and_body()[1]
    lines = body.splitlines()
    start = next(i for i, l in enumerate(lines) if header_row in l)
    rows = []
    for line in lines[start + 2:]:            # skip the header and the |-|-| separator
        if not line.startswith("|"):
            break
        # Split on unescaped pipes only: a `\|` inside a code span is one cell's content.
        cells = re.split(r"(?<!\\)\|", line.strip("|"))
        rows.append([c.strip().replace("\\|", "|") for c in cells])
    return rows


def run(script, cwd, env=None):
    full = {"PATH": BASE_PATH, "HOME": str(cwd), "LC_ALL": "C"}
    full.update(env or {})
    return subprocess.run(["bash", "-c", script], cwd=str(cwd), env=full,
                          capture_output=True, text=True)


def git(cwd, *args):
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})
    return subprocess.run(["git", *args], cwd=str(cwd), env=env,
                          capture_output=True, text=True, check=True)


# --------------------------------------------------------------------------------
# Gate A and the house shape.
# --------------------------------------------------------------------------------

class SkillDocumentTest(unittest.TestCase):

    def setUp(self):
        self.front, self.body = frontmatter_and_body()

    def description(self):
        raw = re.search(r"^description: (.*)$", self.front, re.M).group(1)
        self.assertEqual(raw[:1], '"',
                         "double-quote it; a bare `#` or `: ` truncates the scalar silently")
        return json.loads(raw)

    def test_gate_a_frontmatter_parses_as_yaml_and_names_its_directory(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml is not installed")
        meta = yaml.safe_load(self.front)
        self.assertIsInstance(meta, dict)
        self.assertEqual(meta["name"], SKILL_DIR.name,
                         "the directory is the identity; the frontmatter name must match")
        self.assertEqual(meta["description"], self.description())

    def test_gate_a_keys_are_portable_and_budgets_hold(self):
        keys = set(re.findall(r"^([A-Za-z0-9_-]+):", self.front, re.M))
        self.assertEqual(keys - PORTABLE_KEYS, set())
        self.assertEqual({"name", "description"}, keys,
                         "seed skills in this repo carry name and description only")
        self.assertLessEqual(len(self.front), 1024)
        self.assertLessEqual(len(self.description()), 500)

    def test_the_description_carries_both_halves_and_the_precedence_rule(self):
        desc = self.description()
        self.assertTrue(desc.startswith("Use when"))
        self.assertIn("Do NOT use for", desc)
        # The router never reads the body, so every boundary the body draws has to be in
        # the description too. Derived from the body rather than listed here: a hardcoded
        # list is what let `no-silent-stub` get the longest boundary paragraph in the file
        # and no mention at all in the frontmatter.
        # Any backticked hyphenated name in the boundary section is a skill. Deriving the
        # set instead of listing it is what makes an omission fail: the earlier hardcoded
        # list quietly stopped requiring a neighbour the moment that neighbour was renamed.
        drawn = {x for x in re.findall(r"`([a-z][a-z0-9:-]+)`",
                                       section("When this is the wrong skill")) if "-" in x}
        self.assertGreaterEqual(len(drawn), 4, "boundaries drawn: %r" % (drawn,))
        for neighbour in sorted(drawn):
            self.assertIn(neighbour, desc,
                          "the body draws a boundary against %s but the description never "
                          "names it; a body-only precedence rule is one the router never "
                          "reads" % neighbour)

    def test_every_neighbour_the_description_declines_to_has_a_boundary_paragraph(self):
        """The other direction, so deleting a boundary paragraph cannot pass. Verified as a
        gap in round 3: removing the `verification-before-completion` bullet was green."""
        desc = self.description()
        declined = {x for x in re.findall(r"`([a-z][a-z0-9:-]+)`",
                                          desc.split("Do NOT use")[1]) if "-" in x}
        self.assertGreaterEqual(len(declined), 4, "declines: %r" % (declined,))
        block = section("When this is the wrong skill")
        bullets = [b for b in block.split("\n- **")]
        for neighbour in sorted(declined):
            owned = [b for b in bullets if b.lstrip("- *").startswith("`%s`" % neighbour)]
            self.assertEqual(len(owned), 1,
                             "the description declines to %s but the body draws no "
                             "boundary paragraph for it" % neighbour)

    def test_the_body_is_within_the_house_ceiling(self):
        lines = len(self.body.strip().splitlines())
        self.assertLessEqual(lines, 500, "hard ceiling from skill-authoring Phase 5")
        # A ratchet, not a round number: it has always equalled the body's actual size, so
        # any growth fails here and has to be argued for. Raised 400 -> 403 on 2026-08-26,
        # when the `verification-before-completion` handoff was corrected. The bullet grew
        # by five lines; two were paid back by compressing the three neighbouring boundary
        # paragraphs (no rule dropped, "same shape" and "entrench" intact). The remaining
        # three bought the measurement, its source and as-of date, and the reason no
        # rewording fixes it. Reset this to the new body size after any deliberate trim.
        # Raised 403 -> 404 on 2026-08-31. The routing pin gained a `runs:` line it never
        # carried: this section was pinned `verified 3/3` on a single run, before the
        # three-run floor existed, and the first --runs 3 measurement of it came back
        # `partial 8/9`. `runs` is what separates those two readings, so the line buys the
        # one fact that makes the pin above it interpretable. Nothing was trimmed to pay
        # for it because no line here is spare; the argument is that the line is load-bearing.
        self.assertLessEqual(lines, 404, "working ceiling; the body is paid on every turn")

    def test_the_iron_law_is_fenced_stated_once_and_is_a_procedure(self):
        law = re.search(r"## The Iron Law\n\n```\n(.+)\n```", read())
        self.assertIsNotNone(law, "the Iron Law must be fenced immediately under its heading")
        text = law.group(1)
        self.assertEqual(text, text.upper())
        self.assertEqual(read().count(text), 1, "state it once, do not repeat it")
        # Deliberately no substring check here. `assertIn("RE-DERIVE", text)` passed on
        # `RESTATE FREELY. RE-DERIVE EVERY CLAIM ...`, the law inverted. The law is pinned
        # verbatim in PINNED instead; this test owns only its shape.

    def test_house_sections_are_present_and_in_order(self):
        # Full heading text, anchored: a prefix match kept `## Red flags removed` green,
        # so a whole section could be retitled or deleted without failing anything.
        body = frontmatter_and_body()[1]
        phases = re.findall(r"^## (Phase \d+: .+)$", body, re.M)
        self.assertEqual([h.split(":")[0] for h in phases],
                         ["Phase %d" % i for i in range(1, 7)],
                         "six numbered phases, in order: %r" % (phases,))
        wanted = (["## The Iron Law", "## When this is the wrong skill"]
                  + ["## " + h for h in phases]
                  + ["## Red flags", "## Common rationalizations", "## Trigger precision",
                     "## Quick reference"])
        found = heading_positions(wanted)
        self.assertEqual(found, sorted(found), "house sections are out of order")

    def test_the_unhappy_path_is_answered(self):
        """skill-authoring Phase 5: every skill says what a half-finished run leaves and
        the command that recovers it. This is structural, not a factual claim."""
        headings = re.findall(r"^### (.+)$", self.body, re.M)
        self.assertTrue(any("Unhappy path" in h for h in headings),
                        "no unhappy-path section: %r" % (headings,))
        unhappy = self.body.split("### Unhappy path")[1].split("\n## ")[0]
        self.assertIn("git checkout HEAD --", unhappy, "name the command that recovers")
        self.assertIn("destructive-op-preflight", unhappy,
                      "the recovery discards uncommitted work and this repository ships "
                      "a skill that owns exactly that; cross-reference it")
        self.assertTrue((REPO / "skills" / "destructive-op-preflight" / "SKILL.md").is_file())
        # The inventory is retired on the success path too, not only this one.
        self.assertIn('rm -f "/tmp/claims-$(echo', section("Phase 4: Dispose of what "
                      "you could not re-derive"),
                      "a pass that succeeded must also delete its inventory")

    def test_load_bearing_sentences_survive_verbatim(self):
        """Each is an instruction, not a claim, so pinning it is structural. See the
        PINNED comment for what this catches and what it provably does not."""
        seen = visible(read())
        for sentence in PINNED:
            self.assertIn(visible(sentence), seen,
                          "a load-bearing sentence was reworded, hidden or repealed: %r"
                          % sentence)

    def test_hiding_a_pinned_sentence_is_caught_the_two_ways_it_can_be_hidden(self):
        """Measured, not assumed: `visible()` must remove both, or the pin is decorative."""
        one = PINNED[0]
        self.assertNotIn(visible(one), visible("before <!-- %s --> after" % one))
        self.assertNotIn(visible(one), visible("before ~~%s~~ after" % one))
        self.assertIn(visible(one), visible("before **%s**   after" % one))

    def test_every_as_of_date_is_a_real_date_and_is_not_in_the_future(self):
        """Phase 4 makes an as-of date the licence for a bucket B claim. A date that does
        not parse, or that has not happened, is not one."""
        import datetime
        dates = re.findall(r"as of (\d{4})-(\d{2})-(\d{2})", self.body)
        self.assertTrue(dates, "no as-of date anywhere; bucket B has no licence")
        today = datetime.date.today()
        # The lower bound is re-derived, not a magic literal: a measurement of this
        # repository cannot predate this repository. Found by mutation, where
        # `as of 2019-01-01` passed a check that only looked forward.
        born = subprocess.run(["git", "log", "--reverse", "--format=%cs"], cwd=str(REPO),
                              capture_output=True, text=True)
        if born.returncode != 0 or not born.stdout.strip():
            self.skipTest("not a git checkout, so the lower bound cannot be derived")
        first = datetime.date(*(int(x) for x in born.stdout.split("\n")[0].split("-")))
        for parts in dates:
            day = datetime.date(*(int(x) for x in parts))
            self.assertLessEqual(day, today, "as-of date %s has not happened yet" % (day,))
            self.assertGreaterEqual(day, first,
                                    "as-of date %s predates the repository's first commit "
                                    "(%s), so it cannot be when this was measured"
                                    % (day, first))

    def test_the_evidence_table_carries_its_own_source_and_as_of_date(self):
        """The finding that mattered in round 1: the nine rows are bucket B by this
        document's own Phase 4, and Phase 4's disposition for bucket B is a source plus an
        as-of date. The rows are not pinned verbatim (they are claims, not doctrine); what
        is enforced is the labelling the document demands of everyone else."""
        block = section("The nine, and what they have in common")
        self.assertRegex(block, r"\*\*Source, as of \d{4}-\d{2}-\d{2}:\*\*",
                         "the evidence table must carry the source line its own Phase 4 "
                         "requires of a bucket B claim")
        bucket_b = [r for r in markdown_table("|Bucket|Disposition|") if r[0] == "B"][0]
        for word in ("source", "as-of"):
            self.assertIn(word, bucket_b[1].lower(),
                          "Phase 4's bucket B row must actually prescribe what the "
                          "evidence table was just checked for: %r" % bucket_b)

    def test_prose_avoids_the_banned_house_style(self):
        text = read()
        self.assertEqual(text.count("—"), 0, "no em-dashes anywhere in this repo")
        for banned in ("it's worth noting", "leverage", "robust", "seamless", "delve",
                       "comprehensive", "crucial"):
            self.assertNotIn(banned, text.lower(), "banned word: %s" % banned)

    def test_the_skill_directory_ships_no_build_artifacts(self):
        """The directory is symlinked whole into the user's config."""
        stray = [str(p.relative_to(SKILL_DIR)) for p in SKILL_DIR.rglob("*")
                 if p.name == "__pycache__" or p.suffix in {".pyc", ".pyo"}
                 or p.name == ".DS_Store"]
        self.assertEqual(stray, [], "build artifacts would ship with the skill")
        self.assertEqual(sorted(p.name for p in SKILL_DIR.iterdir()), ["SKILL.md"])


# --------------------------------------------------------------------------------
# Gate B, judged mechanically against the description.
# --------------------------------------------------------------------------------

class TriggerPrecisionTest(unittest.TestCase):

    def setUp(self):
        self.front, self.body = frontmatter_and_body()
        raw = re.search(r"^description: (.*)$", self.front, re.M).group(1)
        self.desc = json.loads(raw)
        block = section("Trigger precision")
        must, must_not = block.split("must NOT fire this skill")
        self.fire = re.findall(r'^\d+\. "(.+?)"', must, re.M)
        self.decline = re.findall(r'^\d+\. "(.+?)"', must_not, re.M)
        self.decline_entries = re.findall(r"^\d+\. (.+?)(?=^\d+\. |\Z)",
                                          must_not, re.M | re.S)

    def test_three_of_each_and_no_prompt_in_both_sets(self):
        self.assertEqual(len(self.fire), 3, "must-fire prompts: %r" % (self.fire,))
        self.assertEqual(len(self.decline), 3, "must-not prompts: %r" % (self.decline,))
        self.assertEqual(set(self.fire) & set(self.decline), set())
        for prompt in self.fire + self.decline:
            self.assertGreater(len(prompt), 30, "trigger prompt too thin: %r" % prompt)

    def test_at_least_two_must_fire_prompts_use_the_descriptions_own_vocabulary(self):
        """skill-authoring Gate B, applied by its own mechanical criterion: words of five
        or more letters from the `Use when` half, matched whole and case-insensitively.
        Stems, synonyms and plurals do not count."""
        use_when = self.desc.split("Do NOT use for")[0]
        vocab = {w.lower() for w in re.findall(r"[A-Za-z]{5,}", use_when)}
        sharing = []
        for prompt in self.fire:
            words = {w.lower() for w in re.findall(r"[A-Za-z]{5,}", prompt)}
            if words & vocab:
                sharing.append((prompt, sorted(words & vocab)))
        self.assertGreaterEqual(len(sharing), 2,
                                "only %d must-fire prompts share vocabulary with the "
                                "description; the set is testing intent, not the text: %r"
                                % (len(sharing), sharing))

    def test_no_decline_prompt_speaks_the_triggers_own_vocabulary(self):
        """The mechanical mirror of the must-fire rule, and the only guard on the negative
        set that does not need a router. Same criterion: words of five or more letters from
        the `Use when` half, matched whole and case-insensitively. Verified as a gap:
        swapping in "The README says we ship nine skills and I think that count is stale
        now." -- a prompt this skill plainly owns -- left the suite green. It shares
        `count`, so it now fails here."""
        vocab = {w.lower() for w in
                 re.findall(r"[A-Za-z]{5,}", self.desc.split("Do NOT use")[0])}
        for prompt in self.decline:
            shared = sorted({w.lower() for w in re.findall(r"[A-Za-z]{5,}", prompt)} & vocab)
            self.assertEqual(shared, [],
                             "a must-NOT prompt using the trigger's own words is not a "
                             "clean negative: %r shares %r" % (prompt, shared))

    def test_each_carve_out_is_attached_to_the_neighbour_that_owns_it(self):
        """Names being present is not the same as names being right. Verified as a gap:
        swapping `no-silent-stub` and `verification-before-completion` in the decline half
        left the suite green, and the description is all the router reads. Each clause is
        scored against every boundary paragraph; the one it names must win outright."""
        clauses = re.findall(r"(?:for|or) ([^(]+?) \(`([a-z][a-z0-9:-]+)`\)",
                             self.desc.split("Do NOT use")[1])
        self.assertGreaterEqual(len(clauses), 4, "carve-outs parsed: %r" % (clauses,))
        block = section("When this is the wrong skill")
        bullets = {}
        for b in block.split("\n- **")[1:]:
            m = re.match(r"`([a-z][a-z0-9:-]+)`", b)
            if m:
                bullets[m.group(1)] = b
        for clause, owner in clauses:
            self.assertIn(owner, bullets, "no boundary paragraph for %s" % owner)
            words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", clause)}
            score = {k: len(words & {w.lower() for w in re.findall(r"[A-Za-z]{4,}", v)})
                     for k, v in bullets.items()}
            best = max(score.values())
            winners = [k for k, s in score.items() if s == best]
            self.assertEqual(winners, [owner],
                             "the description sends %r to `%s`, but that clause matches "
                             "%r at least as well; the carve-outs are crossed"
                             % (clause.strip(), owner, winners))

    def test_exactly_one_negative_prompt_sits_in_an_overlap_and_names_its_owner(self):
        """More than one and the negative set stops exercising the clear cases; none and
        the precedence rule in the description is untested."""
        # A prompt sits in the overlap when it names a skill ANYWHERE in its entry, not
        # only in the gloss. Found by mutation: a decline prompt reading "Refactor this
        # function, which `no-silent-stub` flagged" slipped past the gloss-only version.
        local = {p.name for p in (REPO / "skills").iterdir() if (p / "SKILL.md").exists()}
        known = local | set(re.findall(r"`([a-z][a-z0-9:-]+)`", self.desc))
        overlapping = [e for e in self.decline_entries
                       if (set(re.findall(r"`([a-z][a-z0-9:-]+)`", e)) & known)
                       or "SKILL.md" in e]
        self.assertEqual(len(overlapping), 1,
                         "exactly one must-not prompt may sit in a documented overlap; "
                         "more and the negative set stops exercising the clear cases: %r"
                         % (overlapping,))
        gloss = overlapping[0].split('"', 2)[2]
        named = sorted(set(re.findall(r"`([a-z][a-z0-9:-]+)`", gloss)) & known)
        self.assertTrue(named, "the overlap entry must name the skill that OWNS the "
                               "prompt, in its gloss: %r" % overlapping[0])
        for owner in named:
            self.assertIn(owner, self.desc,
                          "the owner named in the negative set must also appear in the "
                          "description, or the router never sees the precedence rule")


# --------------------------------------------------------------------------------
# Every number this skill states about this repository, re-derived.
# --------------------------------------------------------------------------------

class ClaimsThisSkillMakesTest(unittest.TestCase):
    """The skill applied to itself. Each test parses the claim out of the prose and
    derives the same value from the tree. Correcting the prose after the tree moves is
    what turns these green again; that is the point."""

    def setUp(self):
        self.front, self.body = frontmatter_and_body()

    def example_claim(self):
        """The bucket A cell: the number, the noun, and the command, parsed together."""
        row = [r for r in markdown_table("|Bucket|Disposition|") if r[0] == "A"][0]
        m = re.search(r"ships (\d+) `([^`]+)` files under `([^`]+)`", row[2])
        self.assertIsNotNone(m, "the bucket A example changed shape: %r" % row[2])
        command = re.search(r"`([^`]*find skills[^`]*)`", row[2]).group(1)
        return int(m.group(1)), m.group(2), m.group(3), command

    def test_the_file_count_it_states_matches_the_tree(self):
        claimed, filename, where, _ = self.example_claim()
        actual = len(list(REPO.glob("%s/*/%s" % (where.rstrip("/"), filename))))
        self.assertEqual(claimed, actual,
                         "the example says %d %s files under %s; the tree has %d. Correct "
                         "the prose (and its as-of date); correcting it is what turns this "
                         "green." % (claimed, filename, where, actual))

    def test_the_noun_in_the_example_is_the_noun_the_command_counts(self):
        """The round-6 finding, and the reason this file exists. The example used to read
        "9 seed skills" behind a command that counts SKILL.md files. The count was right
        and the quantity was wrong, and the two tests above locked the wrong quantity in
        so that correcting the prose turned the suite red. The noun is now derived from
        the command's own `-name` argument."""
        _, filename, _, command = self.example_claim()
        counted = re.search(r"-name (\S+)", command)
        self.assertIsNotNone(counted, "the example command no longer names what it counts")
        self.assertEqual(counted.group(1), filename,
                         "the sentence says %r but the command counts %r"
                         % (filename, counted.group(1)))

    def seed_pool_rows(self, readme):
        """Rows of the seed-pool table in whatever text of the README is handed over.

        Taking the text as an argument rather than reading the working tree is what lets
        the same derivation run against a past revision of the file, which is the only
        way to check a claim about a past state without believing it.
        """
        table = re.search(r"\|Skill\|Fires when\|The failure it prevents\|\n\|-\|-\|-\|\n"
                          r"((?:\|.*\n)+)", readme)
        self.assertIsNotNone(table, "the README seed-pool table reshaped; re-derive by hand")
        return len(re.findall(r"^\|`([^`]+)`\|", table.group(1), re.M))

    def seed_pool_size(self):
        """The pool as this repository defines it right now, derived the way `SeedPoolTest`
        does: rows of the README's seed-pool table, which excludes the machinery skills."""
        return self.seed_pool_rows((REPO / "README.md").read_text())

    @staticmethod
    def contested_noun_findings(text, pool):
        """Numbered uses of `seed skill` that disagree with the pool, ignoring specimens.

        Italic-quoted spans are quotations of a defect, not claims: Phase 3 quotes the
        wrong version of this very sentence as its worked example. They are removed rather
        than judged, the way `visible()` removes struck-through text.
        """
        asserted = re.sub(r'\*"[^"]*"\*', " ", text)
        return [int(x) for x in re.findall(r"(\d+) seed skills", asserted) if int(x) != pool]

    def test_the_contested_noun_guard_actually_fires(self):
        """The guard below found nothing on the real file, and a cold reviewer noticed the
        loop could not execute at all: the specimen strip removed the only match, so its
        one live assertion was that the README parses. A check that cannot fail is the
        presence-pinning defect wearing a different hat. So the checker is now exercised
        against a document that does contain the defect, and against one that quotes it."""
        pool = self.seed_pool_size()
        bad = "We ship %d seed skills across the pool." % (pool + 7)
        self.assertEqual(self.contested_noun_findings(bad, pool), [pool + 7],
                         "the checker must fire on a wrong count")
        good = "We ship %d seed skills across the pool." % pool
        self.assertEqual(self.contested_noun_findings(good, pool), [],
                         "and must not fire on the right one")
        quoted = 'The old line read *"this repository ships %d seed skills"* and was wrong.'
        self.assertEqual(self.contested_noun_findings(quoted % (pool + 7), pool), [],
                         "a quoted specimen is not a claim")

    def test_the_contested_noun_is_never_attached_to_a_number_it_does_not_match(self):
        """`seed skill` is narrower than "a directory under skills/". Any numbered use of
        the term outside a quoted specimen must match the README derivation."""
        pool = self.seed_pool_size()
        self.assertEqual(self.contested_noun_findings(self.body, pool), [],
                         "this file attaches a wrong number to `seed skills`; the README "
                         "seed pool has %d. A directory under skills/ is not a seed skill."
                         % pool)

    def test_both_numbers_in_the_worked_example_are_re_derived(self):
        """The round-8 finding, with the bucket call the failure of round 9 forced.

        Phase 3's worked example carries two numbers and they are NOT the same kind of
        claim, which is what the first version of this test got wrong by treating both as
        bucket A.

        The specimen (`9 seed skills`) is the number the wrong command returned, and the
        command is the live one Phase 4's bucket A row still ships, so it is bucket A: it
        tracks the tree and correcting the prose is what turns this green.

        The row count is not. The paragraph is narration in the past tense throughout --
        the example `read`, the count `was` right, a reviewer `found` it -- and the table
        it describes is the table as it stood when that was found. That is a past state, so
        by Phase 2 it is bucket B, and by Phase 4 its disposition is a source plus an as-of
        date. Deriving it from today's README instead is what made this test red when a
        sixth seed skill shipped, and the only edit that would have turned it green is one
        that makes the sentence false about the moment it describes. Worse, the pool grows
        toward the file count: at 9 the example would read "the count was right" beside a
        table with nine rows, and the lesson would contradict itself.

        Bucket B here is not a licence to state anything, because the source is nameable
        and runnable: the README at the revision the sentence cites. So this asserts the
        labelling Phase 4 requires AND runs the cited source to check the number against
        it. A wrong quantity fails, a missing label fails, a source that does not resolve
        fails, and a source pointing at a revision with a different table fails.
        """
        flat = re.sub(r"\s+", " ", self.body)
        specimen = re.search(r'\*"this repository ships (\d+) seed skills"\*', flat)
        self.assertIsNotNone(specimen, "the worked example changed shape")
        files = len(list(REPO.glob("skills/*/SKILL.md")))
        self.assertEqual(int(specimen.group(1)), files,
                         "the specimen quotes the number the wrong command returned, which "
                         "is the SKILL.md file count (%d)" % files)
        words = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
        labelled = re.search(r"seed-pool table, which had (\w+) rows "
                             r"\(`git show ([0-9a-f]{7,40}):README\.md`, "
                             r"as of (\d{4}-\d{2}-\d{2})\)", flat)
        self.assertIsNotNone(
            labelled,
            "the worked example's row count is a past state, so Phase 4 requires it to "
            "carry the source that produces it and the date it was read, in the shape "
            "``had <n> rows (`git show <rev>:README.md`, as of YYYY-MM-DD)``. Without the "
            "label there is nothing to check it against, and re-deriving it from today's "
            "README would answer a different question confidently")
        claimed = words.get(labelled.group(1).lower())
        self.assertIsNotNone(claimed, "unparsed number word: %r" % labelled.group(1))
        rev, as_of = labelled.group(2), labelled.group(3)
        if shutil.which("git") is None or not (REPO / ".git").exists():
            self.skipTest("not a git checkout, so the cited source cannot be run")
        shown = subprocess.run(["git", "show", "%s:README.md" % rev], cwd=str(REPO),
                               capture_output=True, text=True)
        self.assertEqual(shown.returncode, 0,
                         "the worked example cites `git show %s:README.md` as its source "
                         "and that does not resolve: %s" % (rev, shown.stderr.strip()))
        self.assertEqual(claimed, self.seed_pool_rows(shown.stdout),
                         "the worked example says the README table had %r rows at %s; "
                         "running the source it cites gives %d"
                         % (labelled.group(1), rev, self.seed_pool_rows(shown.stdout)))
        dated = subprocess.run(["git", "log", "-1", "--format=%cs", rev], cwd=str(REPO),
                               capture_output=True, text=True)
        self.assertEqual(dated.returncode, 0, dated.stderr)
        self.assertLessEqual(dated.stdout.strip(), as_of,
                             "the as-of date is %s but the revision it cites was committed "
                             "on %s; a claim cannot have been read before its source "
                             "existed" % (as_of, dated.stdout.strip()))
        self.assertNotEqual(claimed, files,
                            "the whole example rests on the two counts differing: the "
                            "command returned %d and the pool it should have counted had "
                            "%d. Equal, and the example teaches nothing"
                            % (files, claimed))

    def test_the_command_it_offers_for_that_count_actually_produces_it(self):
        """The disposition table tells a reader to ship the command instead of the
        number. Run the command it ships."""
        claimed, _, _, command = self.example_claim()
        self.assertIn("wc -l", command,
                      "the document must show the command that prints the number it "
                      "states, not one that prints a list of paths: %r" % command)
        result = run(command, REPO)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(int(result.stdout.strip()), claimed,
                         "the command in the document prints %r, the document says %d"
                         % (result.stdout.strip(), claimed))

    def test_the_measured_sweep_figures_are_re_derived_not_restated(self):
        """Phase 1 states two numbers about a file in this repository to justify the
        whole-file sweep. They are bucket A, so they are re-derived here with the sweeps
        the document itself ships. If `ai-tell-audit` changes, this goes red and the
        sentence is what gets corrected."""
        phase1 = section("Phase 1: Inventory the claims")
        m = re.search(r"sweep over `([^`]+)` matched (\d+) lines while the same pattern "
                      r"over the\nwhole file matched (\d+)", phase1)
        self.assertIsNotNone(phase1 and m, "the measured sentence changed shape")
        target, claimed_diff, claimed_whole = m.group(1), int(m.group(2)), int(m.group(3))
        self.assertTrue((REPO / target).is_file(), "names a file that does not exist")
        whole = run(bash_block("grep -nEi").strip().replace(PLACEHOLDER, target), REPO)
        matched = len([l for l in whole.stdout.splitlines() if l.strip()])
        self.assertEqual(matched, claimed_whole,
                         "the document says %d candidate lines in %s; the whole-file sweep "
                         "it ships matches %d" % (claimed_whole, target, matched))
        diff_line = bash_block("git diff HEAD -U0").splitlines()[0]
        diffed = run(diff_line.replace("git diff HEAD -U0",
                                       "git diff HEAD -U0 -- %s" % target), REPO)
        self.assertEqual(len([l for l in diffed.stdout.splitlines() if l.strip()]),
                         claimed_diff,
                         "the document says the diff sweep matches %d lines on that file"
                         % claimed_diff)

    def test_the_ledger_path_the_source_line_cites_is_the_one_skillforge_composes(self):
        """Bucket A, not B. `bin/skillforge` composes the path from two lines; this
        derives the same path from that source and compares it against the one the
        evidence table's source line names. If the CLI moves its state root, this goes
        red and the source line is what gets corrected."""
        cited = re.search(r"forge ledger at `([^`]+)`",
                          section("The nine, and what they have in common"))
        self.assertIsNotNone(cited, "the source line must name the ledger it cites")
        forge = (REPO / "bin" / "skillforge").read_text()
        root = re.search(r'^STATE_ROOT="\$\{SKILL_COMPOUNDER_STATE:-([^}]+)\}"',
                         forge, re.M)
        ledger = re.search(r'^LEDGER="\$STATE_ROOT/([^"]+)"', forge, re.M)
        self.assertTrue(root and ledger, "bin/skillforge no longer composes the path this "
                                         "way; re-derive the source line by hand")
        composed = "%s/%s" % (root.group(1).replace("$HOME", "~"), ledger.group(1))
        self.assertEqual(cited.group(1), composed,
                         "the evidence table cites %r; skillforge composes %r"
                         % (cited.group(1), composed))

    def test_the_heading_count_equals_the_number_of_rows_it_enumerates(self):
        """"The nine" is a claim about the table underneath it. Derive it from the
        table rather than pinning the word."""
        heading = re.search(r"^## The (\w+), and what they have in common", self.body, re.M)
        self.assertIsNotNone(heading, "the evidence section is missing")
        words = {"seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11}
        claimed = words[heading.group(1).lower()]
        rows = markdown_table("|Where it lived|What it said|")
        self.assertEqual(len(rows), claimed,
                         "the heading says %s, the table has %d rows"
                         % (heading.group(1), len(rows)))
        numbered = [int(r[0].split(".")[0]) for r in rows]
        self.assertEqual(numbered, list(range(1, claimed + 1)),
                         "the rows must be numbered 1..%d in order: %r" % (claimed, numbered))

    def test_every_row_reference_in_the_prose_points_at_a_row_that_exists(self):
        """A cross-reference is a claim. Row 5 of the table is a correction that was
        itself wrong; a dangling `Row 11` here would be the same defect."""
        rows = markdown_table("|Where it lived|What it said|")
        referenced = {int(n) for n in re.findall(r"[Rr]ows? (\d+)", self.body)}
        for lo, hi in re.findall(r"[Rr]ows (\d+) through (\d+)", self.body):
            referenced |= {int(lo), int(hi)}
        self.assertTrue(referenced, "the prose must actually cite the table it ships")
        self.assertLessEqual(max(referenced), len(rows),
                             "dangling row reference: cited %r, table has %d rows"
                             % (sorted(referenced), len(rows)))

    def test_the_boundary_against_every_neighbour_it_names_is_drawn(self):
        block = section("When this is the wrong skill")
        named = set(re.findall(r"`([a-z][a-z0-9:-]+)`", block))
        local = {p.name for p in (REPO / "skills").iterdir() if (p / "SKILL.md").exists()}
        cited_local = named & local
        for required in ("stale-artifact-check", "no-silent-stub", "ai-tell-audit"):
            self.assertIn(required, cited_local,
                          "the boundary against %s is load-bearing and must be drawn"
                          % required)
        # Every in-repo neighbour it names must be a directory that exists. A renamed
        # neighbour silently turns this section into a set of dangling pointers.
        for name in cited_local:
            self.assertTrue((REPO / "skills" / name / "SKILL.md").is_file(),
                            "names a neighbour that does not exist: %s" % name)

    def test_no_example_is_lifted_verbatim_from_the_neighbour_it_claims_to_differ_from(self):
        """Round 3 found bucket C's example was `ai-tell-audit`'s Unsourced precision
        "After" line, character for character, while this file claimed the two were
        orthogonal. Derived from that neighbour's file, so it tracks if either moves."""
        neighbour = (REPO / "skills" / "ai-tell-audit" / "SKILL.md").read_text()
        borrowed = set(re.findall(r"^\*\*(?:Before|After)\.\*\* `([^`]+)`", neighbour, re.M))
        self.assertGreaterEqual(len(borrowed), 4,
                                "the neighbour's example corpus did not parse: %r" % borrowed)
        mine = " ".join(c for row in markdown_table("|Bucket|Disposition|") for c in row)
        clash = sorted(x for x in borrowed if x in mine)
        self.assertEqual(clash, [], "Phase 4 example lifted verbatim from ai-tell-audit, "
                                    "which is the overlap this file says it does not have: "
                                    "%r" % clash)

    def test_the_no_silent_stub_overlap_is_conceded_rather_than_denied(self):
        """The neighbour really covers `a test scored against its own input`, which is
        the same shape as a presence-pinning assertion. The clause used to sit in the
        neighbour's frontmatter description; a routing repair trimmed it from there on
        2026-08-25 (routing verified 6/6), and its home is now the body's self-scoring
        row, whose signature draws the actual straight from the expected. So the check
        is against the neighbour's real text, description or body: the concession must
        not drift from what the neighbour actually covers. Then this skill's boundary
        paragraph must name both what is shared and what differs."""
        neighbour = (REPO / "skills" / "no-silent-stub" / "SKILL.md").read_text()
        front = neighbour.split("---\n", 2)[1]
        desc = json.loads(re.search(r"^description: (.*)$", front, re.M).group(1))
        covered_in_description = "a test scored against its own input" in desc
        # The body's self-scoring shape: an `actual` assigned from the expected value,
        # matched on the semantics rather than the row's title, so a reworded row still
        # counts and a deleted one does not.
        covered_in_body = re.search(r"actual\s*=[^|\n]*expected", neighbour) is not None
        self.assertTrue(covered_in_description or covered_in_body,
                        "the overlap this skill concedes (a test scored against its own "
                        "input) must be something the neighbour's own text still covers, "
                        "in its description or in its self-scoring taxonomy row; if the "
                        "neighbour dropped it, the concession here has drifted")
        block = section("When this is the wrong skill")
        para = [p for p in block.split("- **") if p.startswith("`no-silent-stub`")][0]
        self.assertIn("same shape", para, "the overlap is conceded, not argued away")
        self.assertIn("entrench", para,
                      "the difference that justifies a separate skill must be stated")

    def test_the_invocation_count_the_handoff_states_is_re_derived_not_asserted(self):
        """The correction of round 10, and the reason it is here rather than in an
        `assertIn`. The boundary paragraph used to hand completion claims to
        `verification-before-completion` and say nothing about whether that skill had ever
        handled one. It had not, so a skill about restated claims carried a restated claim
        of its own, which is its Phase 3 step 3 committed inside the document.

        The replacement states a number, so the number is derived here from the corpus the
        sentence names instead of being pinned as a string. Two halves, and the second is
        what makes this a truth pin rather than a grep that found nothing:

          1. the count the sentence states must equal the count this file derives, so the
             day that skill is genuinely invoked the suite goes red and the sentence is
             what gets corrected;
          2. the same counter, over the same corpus, must find invocations of that skill's
             own plugin siblings. A counter that returns zero for everything would make
             the sentence "true" while measuring nothing.

        `CLAIM_PROVENANCE_TRANSCRIPTS` repoints the corpus, in the manner of `CI_NOW` and
        `SKILLFORGE_NOW` elsewhere in this repo: it is how the non-vacuity of both halves
        was demonstrated, by pointing it at a directory holding one real-shaped record for
        a sibling and one for the skill itself, which turns half 1 red without the
        document being touched.
        """
        block = section("When this is the wrong skill")
        # The one boundary paragraph that hands work to a skill outside this repo. Found
        # by its content, then its own leading name is read off it: matching the name
        # first and the plugin later crossed two bullets and scored the wrong neighbour.
        owning = [b for b in ("\n" + block).split("\n- **") if "shipped by the" in b]
        self.assertEqual(len(owning), 1, "expected exactly one out-of-repo handoff")
        para = re.sub(r"\s+", " ", owning[0])
        m = re.match(r"`([a-z][a-z0-9-]+)`\*\* \(shipped by the `([a-z-]+)` plugin\)", para)
        self.assertIsNotNone(m, "the handoff paragraph no longer names a skill and a plugin")
        neighbour, plugin = m.group(1), m.group(2)
        stated = re.search(r"invoked (\d+) times in the local transcript corpus "
                           r"\(source: `Skill` records under `([^`]+)`, as of "
                           r"(\d{4}-\d{2}-\d{2})\)", para)
        self.assertIsNotNone(stated, "the measured sentence changed shape; it must keep "
                                     "the count, the source and the as-of date together")
        claimed, source = int(stated.group(1)), stated.group(2)

        root = Path(os.environ.get("CLAIM_PROVENANCE_TRANSCRIPTS",
                                   os.path.expanduser(source)))
        if not root.is_dir():
            self.skipTest("%s is not present, so the corpus the sentence cites cannot be "
                          "read from here" % root)
        counts = self.skill_invocations(root)

        derived = sum(v for k, v in counts.items() if k.split(":")[-1] == neighbour)
        self.assertEqual(derived, claimed,
                         "the document says %s has been invoked %d times under %s; this "
                         "corpus records %d. Correct the sentence and its as-of date; "
                         "correcting it is what turns this green."
                         % (neighbour, claimed, source, derived))

        siblings = {k: v for k, v in counts.items()
                    if k.startswith(plugin + ":") and k.split(":")[-1] != neighbour and v}
        self.assertTrue(siblings,
                        "the counter found no invocation of any %s skill in %s, so a zero "
                        "for %s measures nothing: %d records over %d skills in total"
                        % (plugin, root, neighbour, sum(counts.values()), len(counts)))

    @staticmethod
    def skill_invocations(root):
        """Every `Skill` tool_use in a transcript tree, counted by the skill it named.

        Reads the real records, on the real shape: an assistant message whose content
        list holds `{"type": "tool_use", "name": "Skill", "input": {"skill": ...}}`. The
        substring guard before `json.loads` is only a speed filter; every line that could
        hold one is still parsed. Lines that do not parse are counted and asserted on by
        the caller's non-vacuity half rather than swallowed.
        """
        counts = {}
        for f in root.rglob("*.jsonl"):
            try:
                text = f.read_text(errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if '"Skill"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                content = (rec.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for item in content:
                    if (isinstance(item, dict) and item.get("type") == "tool_use"
                            and item.get("name") == "Skill"):
                        named = (item.get("input") or {}).get("skill")
                        if named:
                            counts[named] = counts.get(named, 0) + 1
        return counts


# --------------------------------------------------------------------------------
# The heart: presence against truth, measured on two real suites.
# --------------------------------------------------------------------------------

class RecognitionTestTest(unittest.TestCase):
    """Builds the two assertion shapes the skill contrasts, runs each through three
    real states of the world, and checks the observed outcomes against the recognition
    table the SKILL ships, cell by cell.

    The truth-pinning assertion is not restated here. It is lifted verbatim out of
    SKILL.md's Phase 5 python block and executed, so the code the document teaches is
    the code that was measured.
    """

    N = 3

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.root = self.dir / "skills"
        self.doc = self.dir / "doc.md"
        self.set_system(self.N)
        self.set_document(self.N)
        # The presence-pinning assertion is built the way a real author builds one:
        # by copying the claim straight out of the document as it stands.
        self.copied = re.search(r"\d+ skills are installed",
                                self.doc.read_text()).group(0)
        self.write_suites()

    # --- the world -------------------------------------------------------------

    def set_system(self, n):
        if self.root.exists():
            shutil.rmtree(self.root)
        for i in range(n):
            (self.root / ("s%d" % i)).mkdir(parents=True)
            (self.root / ("s%d" % i) / "SKILL.md").write_text("---\nname: s%d\n---\n" % i)

    def set_document(self, n):
        self.doc.write_text("This tree is configuration only.\n"
                            "%d skills are installed in it, and nothing else is.\n" % n)

    # --- the two suites --------------------------------------------------------

    def write_suites(self):
        blocks = fenced("python")
        assert len(blocks) == 1, "expected exactly one python block in SKILL.md"
        shipped = blocks[0]
        assert "assertEqual" in shipped, shipped
        scaffold = (
            "import re, pathlib, unittest\n"
            "TEXT = pathlib.Path(%r).read_text()\n"
            "ROOT = pathlib.Path(%r)\n"
            "class T(unittest.TestCase):\n"
            "    def test_claim(self):\n"
            "        text, root = TEXT, ROOT\n"
            "%s\n"
            "unittest.main()\n")
        self.truth = self.dir / "test_truth.py"
        self.truth.write_text(scaffold % (str(self.doc), str(self.root),
                                          textwrap.indent(shipped, " " * 8)))
        self.presence = self.dir / "test_presence.py"
        self.presence.write_text(
            "import pathlib, unittest\n"
            "TEXT = pathlib.Path(%r).read_text()\n"
            "class T(unittest.TestCase):\n"
            "    def test_claim(self):\n"
            "        self.assertIn(%r, TEXT)\n"
            "unittest.main()\n" % (str(self.doc), self.copied))

    def outcome(self, path):
        result = subprocess.run([sys.executable, str(path)], cwd=str(self.dir),
                                capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1),
                      "the fixture suite errored rather than passing or failing:\n%s"
                      % result.stderr)
        return "green" if result.returncode == 0 else "red"

    # --- the measurements ------------------------------------------------------

    def test_both_suites_are_green_on_a_consistent_world(self):
        """Baseline. Without this, a suite that never passes would satisfy the rest."""
        self.assertEqual(self.outcome(self.truth), "green")
        self.assertEqual(self.outcome(self.presence), "green")

    def test_f3_move_1_the_system_moves_and_only_the_truth_assertion_notices(self):
        self.set_system(self.N + 1)
        self.assertEqual(self.outcome(self.truth), "red")
        self.assertEqual(self.outcome(self.presence), "green",
                         "an assertIn over the document's own text cannot see the system")

    def test_f3_move_2_correcting_the_document_is_what_breaks_the_presence_suite(self):
        """The entrenchment, end to end: while the document is wrong the presence suite
        is green, and the act of correcting it is what turns the suite red."""
        self.set_system(self.N + 1)
        self.assertEqual(self.outcome(self.presence), "green")
        self.set_document(self.N + 1)
        self.assertEqual(self.outcome(self.truth), "green")
        self.assertEqual(self.outcome(self.presence), "red",
                         "correcting a false claim must be what costs; that is the "
                         "incentive inversion the skill names")

    def test_f6_the_recognition_table_matches_what_was_observed(self):
        """The table is compared against the measurement rather than read and believed.
        Column 1 is the truth-pinning assertion, column 2 the presence-pinning one."""
        rows = markdown_table("|Move|Truth-pinning assertion|")
        self.assertEqual(len(rows), 2, "the recognition test has two moves: %r" % (rows,))
        self.set_system(self.N + 1)
        observed = [(self.outcome(self.truth), self.outcome(self.presence))]
        self.set_document(self.N + 1)
        observed.append((self.outcome(self.truth), self.outcome(self.presence)))
        for i, (row, (truth, presence)) in enumerate(zip(rows, observed)):
            self.assertEqual(row[1], truth,
                             "move %d: the table says the truth-pinning assertion %r, "
                             "it actually %r" % (i + 1, row[1], truth))
            self.assertEqual(row[2], presence,
                             "move %d: the table says the presence-pinning assertion %r, "
                             "it actually %r" % (i + 1, row[2], presence))

    def test_a_structural_assertion_survives_both_moves_and_is_therefore_fine(self):
        """Phase 5 fix 4: a heading does not change when the system changes, so pinning
        it is not the defect. Measured, not asserted."""
        structural = self.dir / "test_structural.py"
        structural.write_text(
            "import pathlib, unittest\n"
            "TEXT = pathlib.Path(%r).read_text()\n"
            "class T(unittest.TestCase):\n"
            "    def test_shape(self):\n"
            "        self.assertIn('configuration only', TEXT)\n"
            "unittest.main()\n" % str(self.doc))
        self.assertEqual(self.outcome(structural), "green")
        self.set_system(self.N + 1)
        self.set_document(self.N + 1)
        self.assertEqual(self.outcome(structural), "green",
                         "a structural assertion must be indifferent to both moves")


# --------------------------------------------------------------------------------
# Every command the skill ships, run for real.
# --------------------------------------------------------------------------------

class ShippedCommandsTest(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def test_every_bash_block_is_one_the_suite_runs(self):
        found = fenced("bash")
        self.assertEqual(len(found), len(BLOCK_KEYS),
                         "SKILL.md has %d bash blocks but %d are executed here"
                         % (len(found), len(BLOCK_KEYS)))
        for script, key in zip(found, BLOCK_KEYS):
            self.assertIn(key, script, "bash blocks are out of the expected order")

    def test_every_inline_command_the_prose_claims_is_one_the_suite_runs(self):
        for command in INLINE_COMMANDS:
            self.assertIn(command, read(),
                          "the suite runs %r; keep the text and the test in step" % command)

    def test_every_shipped_command_parses_as_written(self):
        """`bash -n` over the literal text, with nothing substituted. The round-3 defect
        was invisible to every test because each one edited the command before running."""
        for script in fenced("bash") + INLINE_COMMANDS:
            check = subprocess.run(["bash", "-n", "-c", script], capture_output=True,
                                   text=True)
            self.assertEqual(check.returncode, 0,
                             "shipped command does not parse:\n%s\n%s"
                             % (script, check.stderr))

    def test_no_angle_bracket_placeholder_sits_where_the_shell_reads_it(self):
        """`<the file>` in command position is a redirect from a file called `the`.
        Measured 2026-08-25: inside `$( )` bash 5.3 refuses the line with a nonzero
        exit, zsh 5.9 is a parse error exiting 1, and macOS /bin/bash 3.2 substitutes
        nothing, exits 0, and appends to `/tmp/claims-.tsv`; outside `$( )` it silently
        reads the wrong file. Inside double
        quotes it is ordinary data, which is why `"<claim>"` is fine and `-- <the file>` is
        not. Double-quoted spans are removed before the check rather than reasoned about."""
        for script in fenced("bash") + INLINE_COMMANDS:
            bare = re.sub(r'"[^"]*"', '""', script)
            self.assertNotRegex(bare, r"<[a-z][a-z ]+>",
                                "angle-bracket placeholder the shell will read:\n%s" % script)

    def test_b2_no_fixed_inventory_path_survives_anywhere(self):
        """Phase 1 forbids a fixed path; a line copied forward from an earlier draft still
        used one, so the documented cleanup deleted nothing. That is Phase 6, here.

        Two kinds of mention are now legitimate and only two. The shipped RECIPE, which
        must be exactly one path and must derive from `$PWD` (the measured collision fix:
        a relative-path name collides across repos and concurrent sessions). And the
        prose's `/tmp/claims-.tsv`, which is not a recipe but the documented bash-3.2
        failure artifact of the broken-placeholder line -- recognized here by DERIVING it
        from the shipped recipe (the substitution yielding nothing), never whitelisted as
        a literal, so a new fixed-path recipe still fails this test."""
        self.assertNotIn("/tmp/claims-inventory.tsv", read(),
                         "a fixed inventory path contradicts Phase 1 and strands the file")
        paths = set(re.findall(r'/tmp/claims-(?:\$\([^)]*\)|[^"`\s])*[^"`\s]', read()))
        recipes = {p for p in paths if "$(" in p}
        self.assertEqual(recipes,
                         {'/tmp/claims-$(echo "$PWD"/README.md | tr / -).tsv'},
                         "every shipped recipe must name the same $PWD-derived path: %r"
                         % (recipes,))
        # The one fixed path the prose may mention is the failure artifact: the recipe
        # with its substitution collapsed to the empty string, which is what bash 3.2
        # produces from the broken placeholder. Anything else fixed is a shipped recipe
        # in disguise and fails.
        artifact = re.sub(r"\$\([^)]*\)", "", next(iter(recipes)))
        fixed = {p for p in paths if "$(" not in p}
        self.assertLessEqual(fixed, {artifact},
                             "the only fixed path the prose may mention is the measured "
                             "failure artifact %r, got %r" % (artifact, fixed))
        # And no fixed path may sit anywhere executable: every path inside a fenced
        # block or an inline command the suite runs must be the $PWD recipe.
        for script in fenced("bash") + INLINE_COMMANDS:
            for p in re.findall(r'/tmp/claims-(?:\$\([^)]*\)|[^"`\s])*[^"`\s]', script):
                self.assertIn("$(", p,
                              "a fixed inventory path shipped as a runnable command:\n%s"
                              % script)

    def sweep_fixture(self):
        """A real repository with one modified tracked file and one untracked file."""
        if shutil.which("git") is None:
            self.skipTest("git is not on PATH")
        d = self.dir
        git(d, "init", "-q", "-b", "main")
        (d / "README.md").write_text("Opening line.\n")
        git(d, "add", "README.md")
        git(d, "commit", "-qm", "base")
        (d / "README.md").write_text("Opening line.\n"
                                  "The ledger holds 8 forges.\n"
                                  "The runner writes a file when it starts.\n")
        (d / "brand-new.py").write_text("assert 'None of the ten' in text\n")
        return d

    def test_the_claim_sweep_finds_a_count_and_a_universal_in_a_real_diff(self):
        d = self.sweep_fixture()
        result = run(bash_block("git diff HEAD -U0"), d)
        out = result.stdout
        self.assertIn("8 forges", out, "a count must be surfaced")
        self.assertIn("None of the ten", out, "a universal must be surfaced")
        self.assertNotIn("+++", out, "the diff header must not be reported as a claim")
        self.assertIn("brand-new.py", out,
                      "an untracked file is where claims live and `git diff` never "
                      "mentions it; the second line of the block must cover it")

    def test_b2_the_sweep_still_finds_the_claim_after_git_add(self):
        """By the time you are writing a commit message you have staged. A sweep that
        goes empty then is indistinguishable from a clean bill of health."""
        d = self.sweep_fixture()
        git(d, "add", "-A")
        result = run(bash_block("git diff HEAD -U0"), d)
        self.assertIn("8 forges", result.stdout,
                      "the sweep went blind the moment the file was staged")
        self.assertIn("None of the ten", result.stdout)

    def test_b2_the_form_the_skill_warns_against_really_does_go_empty(self):
        """The warning in the prose is a claim about git, so re-derive it rather than
        pinning its wording."""
        d = self.sweep_fixture()
        git(d, "add", "-A")
        pattern = r"[0-9]|\b(none|all|every|only|never|always|cannot)\b"
        without = run("git diff -U0 | grep -E '^\\+[^+]' | grep -iE '%s'" % pattern, d)
        self.assertEqual(without.stdout, "",
                         "if plain `git diff` stopped going empty on a staged file, the "
                         "prose explaining why HEAD is there needs rewriting")
        withhead = run("git diff HEAD -U0 | grep -E '^\\+[^+]' | grep -iE '%s'" % pattern, d)
        self.assertIn("8 forges", withhead.stdout)

    def test_the_sweep_is_safe_when_there_is_nothing_untracked(self):
        """`xargs` with no input runs `grep` once anyway on BSD; the trailing /dev/null is
        what keeps it off the terminal instead of hanging on stdin."""
        d = self.sweep_fixture()
        git(d, "add", "-A")
        git(d, "commit", "-qm", "all")
        result = run(bash_block("git diff HEAD -U0"), d)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "", "a clean tree must produce no noise")

    def test_the_claim_sweep_is_a_reading_aid_and_the_skill_does_not_overclaim_it(self):
        """It cannot see a behavior claim written in plain words, which is the shape
        that cost the most. Measured, and the document must not say otherwise."""
        if shutil.which("git") is None:
            self.skipTest("git is not on PATH")
        d = self.dir
        git(d, "init", "-q", "-b", "main")
        (d / "README.md").write_text("Opening line.\n")
        git(d, "add", "README.md")
        git(d, "commit", "-qm", "base")
        (d / "README.md").write_text(
            "Opening line.\n"
            "Broken frontmatter makes a skill load with empty metadata.\n")
        result = run(bash_block("git diff HEAD -U0"), d)
        self.assertNotIn("empty metadata", result.stdout,
                         "if the sweep grew teeth, the prose that calls it a reading aid "
                         "needs rewriting too")
        phase1 = section("Phase 1: Inventory the claims")
        self.assertRegex(phase1, r"is a detector; they are reading aids",
                         "the sweeps must be presented as incomplete where they are shown")
        for overclaim in ("finds every", "catches every", "will catch all"):
            self.assertNotIn(overclaim, read().lower(),
                             "the sweep must not be described as complete")

    def test_b4_the_diff_sweeps_are_blind_to_a_file_nobody_changed_today(self):
        """Must-fire prompt 1 audits an existing README. Both diff sweeps print nothing on
        an unmodified tracked file, and nothing reads as a clean bill of health."""
        d = self.sweep_fixture()
        git(d, "add", "-A")
        git(d, "commit", "-qm", "all")
        (d / "README.md").write_text("The ledger holds 8 forges.\nNone of the ten.\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "readme")
        diffed = run(bash_block("git diff HEAD -U0"), d)
        self.assertEqual(diffed.stdout, "", "the fixture must be an unmodified tree")
        whole = run(bash_block("grep -nEi"), d)
        self.assertEqual(whole.returncode, 0, whole.stderr)
        self.assertIn("8 forges", whole.stdout, "the whole-file sweep must find the count")
        self.assertIn("None of the ten", whole.stdout, "and the universal")

    def test_b4_the_document_says_which_sweep_applies_when(self):
        """Two commands with no rule for choosing is why the reader invented a third."""
        phase1 = section("Phase 1: Inventory the claims")
        self.assertIn("Use the diff sweeps when you are auditing a change you made", phase1)
        self.assertIn("auditing a document that was already there", phase1)

    def test_the_inventory_line_appends_and_the_cleanup_removes_it(self):
        # Run the shipped text verbatim, in a controlled temp cwd. Nothing is
        # substituted, because substituting is what hid a broken shipped line for a
        # whole round. The recipe embeds `$PWD` in the filename (the collision fix),
        # so the expected path is DERIVED with the recipe's own transformation --
        # `$PWD` as the same shell in the same cwd reports it, `/` turned to `-` --
        # not typed in as a constant.
        pwd = run("pwd", self.dir).stdout.strip()
        self.assertTrue(pwd, "the fixture shell must report its own cwd")
        inv = Path("/tmp/claims-%s.tsv"
                   % ("%s/%s" % (pwd, PLACEHOLDER)).replace("/", "-"))
        self.addCleanup(lambda: inv.exists() and inv.unlink())
        if inv.exists():
            inv.unlink()
        script = bash_block("claims-$(echo")
        result = run(script, self.dir)
        self.assertEqual(result.returncode, 0,
                         "the shipped inventory line must run as written: %s" % result.stderr)
        self.assertTrue(inv.exists(), "the shipped line must create %s" % inv)
        text = inv.read_text()
        self.assertEqual(text.count("\t"), 2, "one claim, three tab-separated fields")
        self.assertTrue(text.endswith("\n"))
        run(script, self.dir)
        self.assertEqual(len(inv.read_text().splitlines()), 2,
                         "the inventory appends rather than truncating")
        cleanup = INLINE_COMMANDS[0]
        self.assertEqual(run(cleanup, self.dir).returncode, 0, "shipped cleanup must run")
        self.assertFalse(inv.exists(), "the shipped cleanup must delete what the shipped "
                                       "inventory line created; the two must name one path")
        self.assertEqual(run(cleanup, self.dir).returncode, 0,
                         "the cleanup must be safe to run when nothing is there")

    def test_f7_the_cross_document_grep_finds_every_copy_of_a_repeated_claim(self):
        """Four files and a CONTRIBUTING.md agreed about a behavior nobody had measured.
        Fixing one copy leaves the rest to re-infect the next reader."""
        d = self.dir
        for name in ("a.md", "b.md", "docs/c.md", "CONTRIBUTING.md"):
            p = d / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("A skill with broken frontmatter loads with empty metadata.\n")
        # Row 7 hid four of its five copies outside markdown. The sweep must reach them.
        (d / "test_frontmatter.py").write_text(
            "def test_it():\n    assert 'empty metadata' in doc\n")
        (d / "unrelated.md").write_text("Nothing to see.\n")
        git(d, "init", "-q", "-b", "main")
        (d / ".git" / "decoy").write_text("empty metadata\n")
        result = run(bash_block("empty metadata"), d)
        self.assertEqual(result.returncode, 0, result.stderr)
        hits = {line.split(":")[0].lstrip("./") for line in result.stdout.splitlines()}
        self.assertEqual(hits, {"a.md", "b.md", "docs/c.md", "CONTRIBUTING.md",
                                "test_frontmatter.py"},
                         "every copy, including the one outside markdown: %r" % (hits,))
        self.assertNotIn(".git/", result.stdout, "--exclude-dir=.git must hold")

    def test_the_unhappy_path_commands_recover_a_partial_pass(self):
        if shutil.which("git") is None:
            self.skipTest("git is not on PATH")
        d = self.dir
        git(d, "init", "-q", "-b", "main")
        original = ("Paragraph one says 8 forges.\n"
                    "Paragraph two says none of the ten.\n"
                    "Paragraph three is untouched.\n")
        (d / "README.md").write_text(original)
        git(d, "add", "README.md")
        git(d, "commit", "-qm", "base")
        # A pass abandoned halfway: one claim corrected, one still wrong.
        (d / "README.md").write_text(original.replace("8 forges", "3 forges"))
        script = bash_block("git checkout HEAD --")
        diff_line = [l for l in script.splitlines() if "git diff" in l][0].split("#")[0]
        result = run(diff_line, d)
        changed = [l for l in result.stdout.splitlines()
                   if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        self.assertTrue(any(l.startswith("+") and "3 forges" in l for l in changed),
                        "`git diff` must show exactly which paragraphs were touched: %r"
                        % (changed,))
        self.assertTrue(all("Paragraph three" not in l for l in changed),
                        "an untouched paragraph must not appear as a change")
        checkout = [l for l in script.splitlines() if "git checkout" in l][0].split("#")[0]
        self.assertEqual(run(checkout, d).returncode, 0)
        self.assertEqual((d / "README.md").read_text(), original,
                         "the revert must restore the file byte for byte")

    def test_b1_the_recovery_reverts_a_pass_that_was_already_staged(self):
        """A half-finished pass is commonly staged. The round-1 form exited 0 and left it
        on disk, which is the state the section calls worse than never starting."""
        if shutil.which("git") is None:
            self.skipTest("git is not on PATH")
        d = self.dir
        git(d, "init", "-q", "-b", "main")
        original = "Paragraph one says 8 forges.\nParagraph two is untouched.\n"
        (d / "README.md").write_text(original)
        git(d, "add", "README.md")
        git(d, "commit", "-qm", "base")
        (d / "README.md").write_text(original.replace("8 forges", "3 forges"))
        git(d, "add", "README.md")
        self.assertIn("M ", git(d, "status", "--short").stdout, "the fixture must be staged")
        script = bash_block("git checkout HEAD --")
        diff_line = [l for l in script.splitlines() if "git diff" in l][0].split("#")[0]
        self.assertIn("3 forges", run(diff_line, d).stdout,
                      "`git diff HEAD` must still show a staged pass")
        checkout = [l for l in script.splitlines() if "git checkout" in l][0].split("#")[0]
        self.assertEqual(run(checkout, d).returncode, 0)
        self.assertEqual((d / "README.md").read_text(), original,
                         "the staged pass must be gone from the working tree")
        self.assertEqual(git(d, "status", "--short").stdout, "",
                         "and from the index: `git checkout HEAD --` resets both")

    def test_b1_the_form_the_skill_warns_against_really_no_ops_on_a_staged_file(self):
        """The warning is a claim about git, so re-derive it instead of pinning its words.
        If git ever changes this, the paragraph explaining HEAD needs rewriting."""
        if shutil.which("git") is None:
            self.skipTest("git is not on PATH")
        d = self.dir
        git(d, "init", "-q", "-b", "main")
        (d / "README.md").write_text("Paragraph one says 8 forges.\n")
        git(d, "add", "README.md")
        git(d, "commit", "-qm", "base")
        (d / "README.md").write_text("Paragraph one says 3 forges.\n")
        git(d, "add", "README.md")
        result = run("git checkout -- README.md", d)
        self.assertEqual(result.returncode, 0, "it exits 0, which is what makes it quiet")
        self.assertEqual(result.stdout + result.stderr, "", "and prints nothing")
        self.assertIn("3 forges", (d / "README.md").read_text(),
                      "the half-finished pass is still on disk, which is the whole point")

    def test_the_skill_ships_no_scanner_and_no_executables(self):
        """skill-authoring Phase 5: ship no detector that has not been measured against
        an external corpus. The reading aid in Phase 1 is presented as one, not as a
        tool, and there is nothing in scripts/ to switch on."""
        self.assertFalse((SKILL_DIR / "scripts").exists())
        self.assertFalse((SKILL_DIR / "references").exists(),
                         "everything here is exercised by this suite; nothing was split "
                         "out as unverifiable")


if __name__ == "__main__":
    unittest.main()
