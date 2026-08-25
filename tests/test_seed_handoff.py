#!/usr/bin/env python3
"""Tests the `session-handoff` seed skill against real files and real git repositories.

The skill's central claim is that a handoff it produces is resumable, so the tests
execute resume commands rather than inspecting them: a throwaway repo is built, a handoff
naming its real branch and real commit is written, and the command out of that handoff is
run to see where it lands. One case moves the branch tip afterwards, which is precisely
where a branch-based resume command silently lands on the wrong commit.

Everything asserted about document shape is parsed out of the real SKILL.md, and the
validator locates its special sections by marker rather than by name, so a coordinated
rename must keep working. No mocks: real files, the real bash validator, real git."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "session-handoff"
SKILL_MD = SKILL_DIR / "SKILL.md"
VALIDATOR = SKILL_DIR / "scripts" / "check-handoff.sh"
FIXTURES = REPO / "tests" / "fixtures" / "session-handoff"

PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
MINIMAL_PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

# The repository tests/fixtures/session-handoff/good-handoff.md describes. Author,
# committer, timestamps, branch and tree are all pinned, so the sha is reproducible and
# the fixture can name it literally instead of gesturing at one.
FIXTURE_BRANCH = "fix/lease-expiry"
FIXTURE_SHA = "f882c1ac93d08b780caba472786173d2fdd45b78"
FIXTURE_DATE = "2026-08-25T10:00:00+0000"
FIXTURE_SOURCE = "def is_expired(now, lease_end):\n    return now > lease_end\n"
GIT_ID = ["-c", "user.name=Handoff Fixture", "-c", "user.email=fixture@example.invalid"]


def read_skill():
    return SKILL_MD.read_text()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "SKILL.md must open with a YAML frontmatter block"
    return m.group(1)


def template_block(text):
    """The four-backtick-fenced template under `## Template`.

    Four backticks so the template's own three-backtick fences survive, which is also how
    the bash validator finds it."""
    out, in_template, in_fence = [], False, False
    for line in text.splitlines():
        if not in_fence and line.strip() == "## Template":
            in_template = True
            continue
        if in_template and line.startswith("````"):
            in_fence = not in_fence
            continue
        if in_template and not in_fence and line.startswith("## "):
            in_template = False
            continue
        if in_template and in_fence:
            out.append(line)
    assert out, "no template block found in SKILL.md"
    return "\n".join(out)


def template_sections(text):
    return [ln for ln in template_block(text).splitlines() if ln.startswith("## ")]


def documented_sections(text):
    """Headings named in the mandatory-section table rows."""
    return [m.group(1) for m in re.finditer(r"^\|`(## [^`]+)`\|", text, re.MULTILINE)]


def sections_of(doc):
    bodies, current = {}, None
    for line in doc.splitlines():
        if line.startswith("## "):
            current = line.rstrip()
            bodies[current] = []
        elif current is not None:
            bodies[current].append(line)
    return {k: "\n".join(v) for k, v in bodies.items()}


def replace_section(doc, heading, new_body):
    """Swap one section's body, leaving every other line untouched."""
    lines, out, i = doc.splitlines(), [], 0
    found = False
    while i < len(lines):
        out.append(lines[i])
        if lines[i] == heading:
            found = True
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            out.extend(["", *new_body.splitlines(), ""])
            continue
        i += 1
    assert found, f"{heading} not present, cannot replace it"
    return "\n".join(out) + "\n"


def fenced_lines(body):
    out, in_fence = [], False
    for line in body.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and line.strip() and not line.strip().startswith("#"):
            out.append(line)
    return out


def build_fixture_repo(parent, env):
    """Materialise the repository the good fixture describes, and prove the sha matches."""
    repo = parent / "scratch-repo"
    repo.mkdir()

    def git(*args, extra_env=None):
        r = subprocess.run(["git", "-C", str(repo), *GIT_ID, *args], capture_output=True,
                           text=True, env={**env, **(extra_env or {})})
        assert r.returncode == 0, f"git {args} failed: {r.stderr}"
        return r.stdout.strip()

    git("init", "-q")
    git("symbolic-ref", "HEAD", f"refs/heads/{FIXTURE_BRANCH}")
    (repo / "admission.py").write_text(FIXTURE_SOURCE)
    git("add", "-A")
    git("commit", "-q", "-m", "Widen the lease window to a half-open interval",
        extra_env={"GIT_AUTHOR_DATE": FIXTURE_DATE, "GIT_COMMITTER_DATE": FIXTURE_DATE})
    # The fixture's porcelain block records one modified file, so make that true.
    (repo / "admission.py").write_text(FIXTURE_SOURCE + "\n\ndef renew(now, lease_end):\n    return now > lease_end\n")
    return repo, git


def run_validator(path, env=None, skill_md=None):
    args = [str(VALIDATOR), str(path)] + ([str(skill_md)] if skill_md else [])
    return subprocess.run(args, capture_output=True, text=True,
                          env=env or {"PATH": MINIMAL_PATH, "HOME": "/nonexistent"})


class TempRepoCase(unittest.TestCase):
    """A temp directory holding the fixture repo, with the fixture handoff beside it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {"PATH": MINIMAL_PATH, "HOME": str(self.root)}
        self.repo, self.git = build_fixture_repo(self.root, self.env)

    def tearDown(self):
        self.tmp.cleanup()

    def place(self, doc, name="handoff.md"):
        p = self.root / name
        p.write_text(doc)
        return p

    def good_doc(self):
        return (FIXTURES / "good-handoff.md").read_text()

    def check(self, doc, **kw):
        return run_validator(self.place(doc), env=self.env, **kw)


class TemplateContractTest(unittest.TestCase):
    """The template, the documented section table, and the fixture must agree."""

    def setUp(self):
        self.text = read_skill()

    def test_template_and_mandatory_section_table_do_not_drift(self):
        self.assertEqual(template_sections(self.text), documented_sections(self.text),
                         "the `## Template` block and the mandatory-section table list "
                         "different sections; one was edited without the other")

    def test_mandatory_section_table_is_not_empty(self):
        self.assertGreaterEqual(len(documented_sections(self.text)), 5)

    def test_good_fixture_has_every_mandatory_section_non_empty(self):
        bodies = sections_of((FIXTURES / "good-handoff.md").read_text())
        for heading in template_sections(self.text):
            self.assertIn(heading, bodies, f"fixture is missing {heading}")
            self.assertTrue(bodies[heading].strip(), f"fixture has an empty {heading}")

    def test_good_fixture_carries_no_surviving_placeholder(self):
        doc = (FIXTURES / "good-handoff.md").read_text()
        for ph in set(re.findall(r"<[^<>]*>", template_block(self.text))):
            self.assertNotIn(ph, doc, f"fixture left the template placeholder {ph} in place")

    def test_template_resume_command_checks_out_a_sha_not_a_branch(self):
        """B1: a branch-based resume command lands wherever the tip has moved to."""
        resume = sections_of(template_block(self.text))
        state_body = [b for b in resume.values() if re.search(r"^branch:", b, re.M)]
        self.assertTrue(state_body, "template has no section recording a branch")
        cd_line = [ln for b in resume.values() for ln in fenced_lines(b) if ln.startswith("cd ")]
        self.assertTrue(cd_line, "template has no resume command anchored with cd")
        self.assertIn("sha", cd_line[0],
                      f"the template resume command must check out the recorded sha: {cd_line[0]}")


class ValidatorTest(TempRepoCase):
    """The mechanical validator, run as the real bash script."""

    def test_validator_is_executable(self):
        self.assertTrue(os.access(VALIDATOR, os.X_OK), f"{VALIDATOR} is not executable")

    def test_the_fixture_repo_reproduces_the_sha_the_fixture_names(self):
        """The fixture names a literal sha, so the repo it describes must be reproducible."""
        self.assertEqual(self.git("rev-parse", "HEAD"), FIXTURE_SHA)
        porcelain = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                                   capture_output=True, text=True, env=self.env).stdout
        self.assertEqual(porcelain, " M admission.py\n",
                         "the fixture's pasted porcelain block must be true of this repo")
        self.assertIn(" M admission.py", self.good_doc())

    def test_validator_accepts_the_good_fixture(self):
        r = self.check(self.good_doc())
        self.assertEqual(r.returncode, 0, f"good fixture rejected:\n{r.stdout}{r.stderr}")

    def test_validator_rejects_a_summarised_handoff(self):
        p = FIXTURES / "bad-handoff.md"
        r = run_validator(p, env=self.env)
        self.assertEqual(r.returncode, 1, "a summarised handoff must be rejected")
        for rule in ("BRANCH_IS_HEAD", "NO_SHA", "NO_RESUME_COMMAND",
                     "SUMMARISED_ERROR", "NO_REPRO", "NON_ANSWER"):
            self.assertIn(rule, r.stdout, f"{rule} should have fired:\n{r.stdout}")

    def test_validator_rejects_a_missing_section(self):
        r = self.check(self.good_doc().split("## Dead ends")[0])
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING_SECTION ## Dead ends", r.stdout)

    def test_validator_rejects_an_unfilled_template(self):
        r = self.check(template_block(read_skill()))
        self.assertEqual(r.returncode, 1)
        self.assertIn("PLACEHOLDER", r.stdout)

    def test_validator_rejects_a_whitespace_only_section(self):
        r = self.check(replace_section(self.good_doc(), "## Next", "   "))
        self.assertEqual(r.returncode, 1)
        self.assertIn("EMPTY_SECTION ## Next", r.stdout)


class HostileInputTest(TempRepoCase):
    """B3: inputs shaped to satisfy the letter of the rules and none of the point."""

    def assert_rejected_with(self, doc, rule):
        r = self.check(doc)
        self.assertEqual(r.returncode, 1, f"expected {rule}, got exit 0")
        self.assertIn(rule, r.stdout, f"expected {rule}, got:\n{r.stdout}")

    def test_a_fabricated_sha_is_rejected(self):
        fake = "deadbeef" * 5
        self.assert_rejected_with(self.good_doc().replace(FIXTURE_SHA, fake), "UNKNOWN_COMMIT")

    def test_a_resume_fence_holding_only_a_comment_is_rejected(self):
        doc = replace_section(self.good_doc(), "## Resume command",
                              "```bash\n# TODO: figure out where the repo lives\n```")
        self.assert_rejected_with(doc, "NO_RESUME_COMMAND")

    def test_a_one_character_resume_command_is_rejected(self):
        doc = replace_section(self.good_doc(), "## Resume command", "```bash\nx\n```")
        self.assert_rejected_with(doc, "RESUME_NOT_ANCHORED")

    def test_a_resume_command_naming_a_directory_that_is_gone_is_rejected(self):
        doc = self.good_doc().replace("cd ./scratch-repo", "cd /no/such/directory")
        self.assert_rejected_with(doc, "UNREACHABLE_REPO")

    def test_a_truncated_error_is_rejected(self):
        doc = replace_section(
            self.good_doc(), "## Broken",
            "- test_admission_rejects_expired_lease\n\n```\n"
            "AssertionError: expected 1 ... (truncated)\n```\n\n"
            "repro: python3 -m pytest tests/test_scheduler.py -q")
        self.assert_rejected_with(doc, "TRUNCATED_OUTPUT")

    def test_a_bare_ellipsis_line_is_rejected(self):
        doc = replace_section(
            self.good_doc(), "## Broken",
            "- test_admission_rejects_expired_lease\n\n```\nTraceback:\n...\n"
            "AssertionError\n```\n\nrepro: python3 -m pytest -q")
        self.assert_rejected_with(doc, "TRUNCATED_OUTPUT")

    def test_tbd_is_not_an_answer(self):
        self.assert_rejected_with(replace_section(self.good_doc(), "## Done and verified", "TBD"),
                                  "NON_ANSWER")

    def test_see_above_is_not_an_answer(self):
        self.assert_rejected_with(replace_section(self.good_doc(), "## Dead ends", "see above"),
                                  "NON_ANSWER")

    def test_the_sanctioned_empty_marker_is_still_accepted(self):
        doc = replace_section(self.good_doc(), "## Dead ends", "None.")
        r = self.check(doc)
        self.assertEqual(r.returncode, 0, f"'None.' must remain valid:\n{r.stdout}")


class ResumeCommandTest(TempRepoCase):
    """B1: the resume command must land on the commit the handoff recorded."""

    def resume_from(self, doc):
        command = "\n".join(fenced_lines(sections_of(doc)["## Resume command"]))
        self.assertTrue(command.strip(), "no runnable resume command in the handoff")
        return subprocess.run(["bash", "-c", command], capture_output=True, text=True,
                              cwd=str(self.root), env=self.env)

    def move_the_branch_tip(self):
        """Commit on top of the recorded state, as a colleague pushing would."""
        (self.repo / "admission.py").write_text(FIXTURE_SOURCE + "\n# a later change\n")
        self.git("commit", "-q", "-a", "-m", "later work on the same branch")
        moved = self.git("rev-parse", "HEAD")
        self.assertNotEqual(moved, FIXTURE_SHA)
        return moved

    def test_resume_lands_on_the_recorded_commit_after_the_tip_moves(self):
        doc = self.good_doc()
        self.place(doc)
        moved = self.move_the_branch_tip()

        self.assertEqual(run_validator(self.root / "handoff.md", env=self.env).returncode, 0)
        r = self.resume_from(doc)
        self.assertEqual(r.returncode, 0, f"resume command failed:\n{r.stdout}{r.stderr}")
        head = self.git("rev-parse", "HEAD")
        self.assertEqual(head, FIXTURE_SHA,
                         f"resume landed on {head}, not the recorded {FIXTURE_SHA} "
                         f"(the branch tip is {moved})")

    def test_a_branch_only_resume_command_is_rejected(self):
        doc = self.good_doc().replace(f"git checkout {FIXTURE_SHA}",
                                      f"git checkout {FIXTURE_BRANCH}")
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn("RESUME_MISSING_SHA", r.stdout)

    def test_branch_recorded_as_the_literal_HEAD_is_rejected(self):
        doc = self.good_doc().replace(f"branch: {FIXTURE_BRANCH}", "branch: HEAD")
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn("BRANCH_IS_HEAD", r.stdout)

    def test_a_detached_head_handoff_records_detached_and_still_resumes(self):
        self.git("checkout", "-q", "--detach", FIXTURE_SHA)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "HEAD",
                         "precondition: abbrev-ref returns the literal HEAD when detached")
        symref = subprocess.run(["git", "-C", str(self.repo), "symbolic-ref", "--quiet",
                                 "--short", "HEAD"], capture_output=True, text=True, env=self.env)
        self.assertNotEqual(symref.returncode, 0,
                            "symbolic-ref is what the skill uses precisely because it fails here")
        self.assertEqual(symref.stdout.strip(), "")

        doc = self.good_doc().replace(f"branch: {FIXTURE_BRANCH}", "branch: (detached)")
        self.place(doc)
        self.assertEqual(run_validator(self.root / "handoff.md", env=self.env).returncode, 0)

        self.git("checkout", "-q", FIXTURE_BRANCH)
        self.move_the_branch_tip()
        r = self.resume_from(doc)
        self.assertEqual(r.returncode, 0, f"resume command failed:\n{r.stdout}{r.stderr}")
        self.assertEqual(self.git("rev-parse", "HEAD"), FIXTURE_SHA)


class RenameDriftTest(TempRepoCase):
    """B2: the special-rule sections are located by marker, so a rename must carry."""

    def renamed_skill(self, old, new):
        """A copy of the real SKILL.md with one section heading renamed."""
        copy = self.root / "SKILL.md"
        copy.write_text(re.sub(rf"^{re.escape(old)}$", new, read_skill(), flags=re.MULTILINE))
        return copy

    def test_renaming_the_broken_section_carries_to_the_rules(self):
        skill = self.renamed_skill("## Broken", "## Failing")
        doc = self.good_doc().replace("## Broken", "## Failing")
        r = self.check(doc, skill_md=skill)
        self.assertEqual(r.returncode, 0,
                         f"a coordinated rename must still validate:\n{r.stdout}{r.stderr}")

    def test_a_renamed_broken_section_is_still_policed_under_its_new_name(self):
        skill = self.renamed_skill("## Broken", "## Failing")
        doc = self.good_doc().replace("## Broken", "## Failing")
        doc = re.sub(r"^repro: .*$", "", doc, flags=re.MULTILINE)
        r = self.check(doc, skill_md=skill)
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO_REPRO ## Failing", r.stdout)
        self.assertNotIn("## Broken", r.stdout, "the validator named a section that no longer exists")

    def test_renaming_the_state_section_carries_to_the_rules(self):
        skill = self.renamed_skill("## State", "## Tree")
        doc = self.good_doc().replace("## State", "## Tree")
        r = self.check(doc, skill_md=skill)
        self.assertEqual(r.returncode, 0, f"rename broke the state rules:\n{r.stdout}{r.stderr}")

    def test_a_renamed_state_section_is_still_policed_under_its_new_name(self):
        skill = self.renamed_skill("## State", "## Tree")
        doc = self.good_doc().replace("## State", "## Tree").replace(f"commit: {FIXTURE_SHA}", "")
        r = self.check(doc, skill_md=skill)
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO_SHA ## Tree", r.stdout)

    def test_adding_a_section_to_the_template_makes_it_mandatory(self):
        copy = self.root / "SKILL.md"
        copy.write_text(read_skill().replace("## Watch out for\n\n- <trap a fresh session would hit>",
                                             "## Watch out for\n\n- <trap a fresh session would hit>"
                                             "\n\n## Budget\n\n- <what is left>"))
        r = self.check(self.good_doc(), skill_md=copy)
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING_SECTION ## Budget", r.stdout)


class TriggerPrecisionTest(unittest.TestCase):

    def setUp(self):
        self.text = read_skill()

    def examples(self, heading):
        parts = self.text.split(heading, 1)
        self.assertEqual(len(parts), 2, f"SKILL.md has no `{heading}` block")
        tail = parts[1].split("\n###", 1)[0].split("\n## ", 1)[0]
        return re.findall(r'^- "(.+)"$', tail, re.MULTILINE)

    def test_section_exists(self):
        self.assertIn("\n## Trigger precision\n", self.text)

    def test_three_must_fire_prompts(self):
        self.assertEqual(len(self.examples("### Must fire (3)")), 3)

    def test_three_must_not_fire_prompts(self):
        self.assertEqual(len(self.examples("### Must NOT fire (3)")), 3)

    def test_must_fire_and_must_not_fire_are_disjoint(self):
        self.assertEqual(set(self.examples("### Must fire (3)"))
                         & set(self.examples("### Must NOT fire (3)")), set())


class HouseStyleTest(unittest.TestCase):
    """Measured limits from notes/research/skill-ecosystem-survey.md."""

    def setUp(self):
        self.text = read_skill()
        self.fm = frontmatter(self.text)

    def description(self):
        m = re.search(r"^description: *(.+)$", self.fm, re.MULTILINE)
        self.assertIsNotNone(m, "SKILL.md needs a description")
        return m.group(1).strip().strip('"').strip("'")

    def test_only_portable_frontmatter_keys(self):
        keys = set(re.findall(r"^([A-Za-z][A-Za-z0-9-]*):", self.fm, re.MULTILINE))
        self.assertTrue(keys <= PORTABLE_KEYS, f"non-portable keys: {keys - PORTABLE_KEYS}")

    def test_name_matches_directory(self):
        m = re.search(r"^name: *(\S+)", self.fm, re.MULTILINE)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), SKILL_DIR.name)

    def test_frontmatter_under_1024_chars(self):
        self.assertLessEqual(len(self.fm), 1024, f"frontmatter is {len(self.fm)} chars")

    def test_description_under_500_chars(self):
        d = self.description()
        self.assertLessEqual(len(d), 500, f"description is {len(d)} chars")

    def test_description_excludes_a_mid_session_recap(self):
        """The negative scope must discriminate before the body ever loads."""
        d = self.description().lower()
        self.assertRegex(d, r"\b(do not use|not for|never use)\b")
        self.assertIn("recap", d, "the must-not-fire list includes a mid-session recap, "
                                  "so the description has to exclude it")

    def test_body_under_500_lines(self):
        self.assertLessEqual(len(self.text.split("\n---\n", 1)[1].splitlines()), 500)

    def test_the_minimal_fallback_comes_before_the_rationale(self):
        """B4: what to do when there is no context left must not sit behind the why."""
        lines = self.text.splitlines()
        fallback = next(i for i, l in enumerate(lines) if l.startswith("## If you have almost no context"))
        rationale = next(i for i, l in enumerate(lines) if l.startswith("## Why this exists"))
        self.assertLess(fallback, 40, f"the minimal fallback starts at line {fallback + 1}")
        self.assertLess(fallback, rationale, "the rationale must sit below the procedure")

    def test_no_em_dashes_anywhere_in_the_skill(self):
        em_dash = "\u2014"  # escaped so this file passes its own check
        for path in sorted(SKILL_DIR.rglob("*")) + sorted(FIXTURES.rglob("*")) + [Path(__file__)]:
            if path.is_file():
                self.assertNotIn(em_dash, path.read_text(), f"em-dash in {path}")


if __name__ == "__main__":
    unittest.main()
