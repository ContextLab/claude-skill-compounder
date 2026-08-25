#!/usr/bin/env python3
"""Tests the `session-handoff` seed skill against real files and a real git repo.

The skill's central claim is that a handoff it produces is *resumable*. That claim is
only testable if the resume command actually runs, so one test builds a throwaway git
repo, writes a handoff naming that repo's real branch and real commit sha, then executes
the resume command straight out of the handoff and checks where it lands.

Everything the tests assert about mandatory sections is parsed out of the real SKILL.md,
so the template, the documented section table, and the validator cannot drift apart
without a failure here. No mocks: real files, the real bash validator, real git."""

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
GIT_ID = ["-c", "user.email=test@example.invalid", "-c", "user.name=Handoff Test"]


def read_skill():
    return SKILL_MD.read_text()


def frontmatter(text):
    """The raw text between the opening and closing `---` delimiters."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "SKILL.md must open with a YAML frontmatter block"
    return m.group(1)


def template_block(text):
    """The four-backtick-fenced template under `## Template`.

    Four backticks are used so the template's own three-backtick fences survive, which is
    also how the bash validator finds it."""
    lines = text.splitlines()
    out, in_template, in_fence = [], False, False
    for line in lines:
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
    """Headings named in the mandatory-section table rows (`|`## Foo`|...`)."""
    return [m.group(1) for m in re.finditer(r"^\|`(## [^`]+)`\|", text, re.MULTILINE)]


def sections_of(doc):
    """Map heading -> body text, for a handoff document."""
    bodies, current = {}, None
    for line in doc.splitlines():
        if line.startswith("## "):
            current = line.rstrip()
            bodies[current] = []
        elif current is not None:
            bodies[current].append(line)
    return {k: "\n".join(v) for k, v in bodies.items()}


def fenced_lines(body):
    out, in_fence = [], False
    for line in body.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and line.strip():
            out.append(line)
    return out


def run_validator(path, env=None):
    return subprocess.run([str(VALIDATOR), str(path)], capture_output=True, text=True,
                          env=env or {"PATH": MINIMAL_PATH})


class TemplateContractTest(unittest.TestCase):
    """The template, the documented section table, and the fixtures must agree."""

    def setUp(self):
        self.text = read_skill()

    def test_template_and_mandatory_section_table_do_not_drift(self):
        self.assertEqual(template_sections(self.text), documented_sections(self.text),
                         "the `## Template` block and the mandatory-section table list "
                         "different sections; one of them was edited without the other")

    def test_mandatory_section_table_is_not_empty(self):
        self.assertGreaterEqual(len(documented_sections(self.text)), 5)

    def test_good_fixture_has_every_mandatory_section_non_empty(self):
        doc = (FIXTURES / "good-handoff.md").read_text()
        bodies = sections_of(doc)
        for heading in template_sections(self.text):
            self.assertIn(heading, bodies, f"fixture is missing {heading}")
            self.assertTrue(bodies[heading].strip(), f"fixture has an empty {heading}")

    def test_good_fixture_carries_no_surviving_placeholder(self):
        placeholders = set(re.findall(r"<[^<>]*>", template_block(self.text)))
        doc = (FIXTURES / "good-handoff.md").read_text()
        for ph in placeholders:
            self.assertNotIn(ph, doc, f"fixture left the template placeholder {ph} in place")


class ValidatorTest(unittest.TestCase):
    """The mechanical validator, run as the real bash script."""

    def test_validator_is_executable(self):
        self.assertTrue(os.access(VALIDATOR, os.X_OK), f"{VALIDATOR} is not executable")

    def test_validator_accepts_the_good_fixture(self):
        r = run_validator(FIXTURES / "good-handoff.md")
        self.assertEqual(r.returncode, 0, f"good fixture rejected:\n{r.stdout}{r.stderr}")

    def test_validator_rejects_a_summarised_handoff(self):
        r = run_validator(FIXTURES / "bad-handoff.md")
        self.assertEqual(r.returncode, 1, "a summarised handoff must be rejected")
        for rule in ("NO_SHA", "NO_RESUME_COMMAND", "SUMMARISED_ERROR", "NO_REPRO"):
            self.assertIn(rule, r.stdout, f"{rule} should have fired:\n{r.stdout}")

    def test_validator_rejects_a_missing_section(self):
        doc = (FIXTURES / "good-handoff.md").read_text()
        stripped = doc.split("## Dead ends")[0]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "handoff.md"
            p.write_text(stripped)
            r = run_validator(p)
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING_SECTION ## Dead ends", r.stdout)

    def test_validator_rejects_an_unfilled_template(self):
        """Copying the template out and not filling it in must not pass."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "handoff.md"
            p.write_text(template_block(read_skill()))
            r = run_validator(p)
        self.assertEqual(r.returncode, 1)
        self.assertIn("PLACEHOLDER", r.stdout)


class ResumeCommandTest(unittest.TestCase):
    """The resume command must be a command, and it must land on the stated commit."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work = self.root / "scratch-repo"
        self.work.mkdir()
        self.env = {"PATH": MINIMAL_PATH, "HOME": str(self.root)}

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, check=True):
        r = subprocess.run(["git", "-C", str(self.work), *GIT_ID, *args],
                           capture_output=True, text=True, env=self.env)
        if check:
            self.assertEqual(r.returncode, 0, f"git {args} failed: {r.stderr}")
        return r.stdout.strip()

    def build_repo(self):
        self.git("init", "-q")
        (self.work / "admission.py").write_text("def is_expired(t, lease):\n    return t >= lease\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "initial")
        home_branch = self.git("rev-parse", "--abbrev-ref", "HEAD")
        self.git("checkout", "-q", "-b", "fix/lease-expiry")
        (self.work / "admission.py").write_text("def is_expired(t, lease):\n    return t > lease\n")
        self.git("commit", "-q", "-a", "-m", "half-open lease window")
        sha = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", home_branch)
        return home_branch, sha

    def compose_handoff(self, branch, sha):
        """Build a handoff filling every section the SKILL.md declares mandatory."""
        resume = f"cd {self.work} && git checkout fix/lease-expiry && git rev-parse HEAD"
        filled = {
            "## Resume command": f"```bash\n{resume}\n```",
            "## State": (f"branch: {branch}\ncommit: {sha}\n\n```\n$ git status --porcelain\n```"),
            "## Done and verified": ("- Half-open lease window committed. Proved by "
                                     "`git log --oneline -1`, which printed "
                                     f"`{sha[:7]} half-open lease window`."),
            "## Done but NOT verified": "- Nothing exercises the renew path yet.",
            "## Broken": ("- test_admission_rejects_expired_lease\n\n```\n"
                          "E       AssertionError: assert 'admitted' == 'rejected'\n"
                          "tests/test_scheduler.py:212: AssertionError\n```\n\n"
                          "repro: python3 -m pytest tests/test_scheduler.py -q"),
            "## Dead ends": "- Tried freezegun in a worker thread. It does not patch there.",
            "## Corrections to earlier notes": "None.",
            "## Open decisions": "- Renew or reject a lease expiring at the scheduling instant?",
            "## Next": "1. Inject Clock into Scheduler.",
            "## Watch out for": "- The scheduler test leaves a live thread behind on failure.",
        }
        headings = template_sections(read_skill())
        missing = [h for h in headings if h not in filled]
        self.assertEqual(missing, [], f"test does not know how to fill {missing}")
        parts = [f"# 2026-08-25 handoff: lease expiry"]
        parts += [f"{h}\n\n{filled[h]}" for h in headings]
        return "\n\n".join(parts) + "\n"

    def test_resume_command_lands_on_the_stated_commit(self):
        branch, sha = self.build_repo()
        self.assertNotEqual(self.git("rev-parse", "HEAD"), sha,
                            "precondition: the repo must not already be on the handoff commit")

        handoff = self.root / "notes" / "2026-08-25-lease-expiry.md"
        handoff.parent.mkdir()
        handoff.write_text(self.compose_handoff(branch, sha))

        valid = run_validator(handoff, env=self.env)
        self.assertEqual(valid.returncode, 0,
                         f"composed handoff failed validation:\n{valid.stdout}{valid.stderr}")

        command = "\n".join(fenced_lines(sections_of(handoff.read_text())["## Resume command"]))
        self.assertTrue(command.strip(), "no runnable resume command in the handoff")

        r = subprocess.run(["bash", "-c", command], capture_output=True, text=True,
                           cwd=str(self.root), env=self.env)
        self.assertEqual(r.returncode, 0,
                         f"resume command failed:\n{command}\n{r.stdout}{r.stderr}")
        self.assertIn(sha, r.stdout, "resume command did not print the handoff's commit")
        self.assertEqual(self.git("rev-parse", "HEAD"), sha,
                         "resume command did not leave the repo on the stated commit")

    def test_a_handoff_without_a_sha_cannot_be_resumed_to_a_commit(self):
        """The rule that bites: strip the commit line and the validator refuses."""
        branch, sha = self.build_repo()
        doc = self.compose_handoff(branch, sha).replace(f"commit: {sha}\n", "")
        p = self.root / "no-sha.md"
        p.write_text(doc)
        r = run_validator(p, env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO_SHA", r.stdout)


class TriggerPrecisionTest(unittest.TestCase):

    def setUp(self):
        self.text = read_skill()

    def examples(self, heading):
        block = self.text.split(heading, 1)
        self.assertEqual(len(block), 2, f"SKILL.md has no `{heading}` block")
        tail = block[1].split("\n###", 1)[0].split("\n## ", 1)[0]
        return re.findall(r'^- "(.+)"$', tail, re.MULTILINE)

    def test_section_exists(self):
        self.assertIn("\n## Trigger precision\n", self.text)

    def test_three_must_fire_prompts(self):
        self.assertEqual(len(self.examples("### Must fire (3)")), 3)

    def test_three_must_not_fire_prompts(self):
        self.assertEqual(len(self.examples("### Must NOT fire (3)")), 3)

    def test_must_fire_and_must_not_fire_are_disjoint(self):
        fire = set(self.examples("### Must fire (3)"))
        never = set(self.examples("### Must NOT fire (3)"))
        self.assertEqual(fire & never, set())


class HouseStyleTest(unittest.TestCase):
    """Measured limits from notes/research/skill-ecosystem-survey.md."""

    def setUp(self):
        self.text = read_skill()
        self.fm = frontmatter(self.text)

    def test_only_portable_frontmatter_keys(self):
        keys = set(re.findall(r"^([A-Za-z][A-Za-z0-9-]*):", self.fm, re.MULTILINE))
        self.assertTrue(keys <= PORTABLE_KEYS, f"non-portable frontmatter keys: {keys - PORTABLE_KEYS}")

    def test_name_matches_directory(self):
        m = re.search(r"^name: *(\S+)", self.fm, re.MULTILINE)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), SKILL_DIR.name)

    def test_frontmatter_under_1024_chars(self):
        self.assertLessEqual(len(self.fm), 1024, f"frontmatter is {len(self.fm)} chars")

    def test_description_under_500_chars(self):
        m = re.search(r"^description: *(.+)$", self.fm, re.MULTILINE)
        self.assertIsNotNone(m, "SKILL.md needs a description")
        self.assertLessEqual(len(m.group(1)), 500, f"description is {len(m.group(1))} chars")

    def test_description_carries_a_negative_scope_clause(self):
        m = re.search(r"^description: *(.+)$", self.fm, re.MULTILINE)
        self.assertRegex(m.group(1), r"(?i)\b(do not use|not for|never use)\b")

    def test_body_under_500_lines(self):
        body = self.text.split("\n---\n", 1)[1]
        self.assertLessEqual(len(body.splitlines()), 500)

    def test_no_em_dashes_in_the_skill(self):
        em_dash = "\u2014"  # escaped so this file passes its own check
        paths = sorted(SKILL_DIR.rglob("*")) + sorted(FIXTURES.rglob("*")) + [Path(__file__)]
        for path in paths:
            if path.is_file():
                self.assertNotIn(em_dash, path.read_text(), f"em-dash in {path}")


if __name__ == "__main__":
    unittest.main()
