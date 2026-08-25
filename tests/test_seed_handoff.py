#!/usr/bin/env python3
"""Tests the `session-handoff` seed skill against real files and real git repositories.

The skill claims two things and both are executed here rather than inspected. "The resume
command lands you on the recorded state" is tested by moving the branch tip, dirtying the
tree, and running the command out of the handoff from an unrelated working directory. "The
validator proves rather than pattern-matches" is tested with inputs shaped to satisfy the
letter of every rule, including a fabricated sha aimed at a directory that is not a
repository.

The state-collection block in the SKILL.md is extracted and executed against five real
environments (a normal repo, a detached HEAD, a repo with no commits, a bare repo, and a
plain directory), because four of those give a plausible wrong answer to the obvious
command.

The skill deliberately does NOT preserve uncommitted work; a test here fails if that
mechanism is reintroduced, because every version of it restores nothing while appearing to
work. No mocks: real files, the real bash validator, real git."""

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

# The repository the good fixture describes. Author, committer, timestamps, branch and
# tree are pinned, so the sha is reproducible and the fixture can name it literally.
FIXTURE_BRANCH = "fix/lease-expiry"
FIXTURE_SHA = "f882c1ac93d08b780caba472786173d2fdd45b78"
FIXTURE_DATE = "2026-08-25T10:00:00+0000"
FIXTURE_PATH = "/srv/checkouts/admission"  # where the fixture's repo lived; tests relocate it
FIXTURE_SOURCE = "def is_expired(now, lease_end):\n    return now > lease_end\n"
GIT_ID = ["-c", "user.name=Handoff Fixture", "-c", "user.email=fixture@example.invalid"]


def read_skill():
    return SKILL_MD.read_text()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "SKILL.md must open with a YAML frontmatter block"
    return m.group(1)


def _fence_scan(lines):
    """Yield (line, in_fence, is_delimiter), mirroring the validator's fence tracker.

    Backtick and tilde fences both count, and a fence closes only on the same character in
    a run at least as long as the opener."""
    fence, flen, fch = False, 0, ""
    for line in lines:
        m = re.match(r"^(`+|~+)", line)
        if m and len(m.group(0)) >= 3:
            n, ch = len(m.group(0)), line[0]
            if not fence:
                fence, flen, fch = True, n, ch
                yield line, True, True
                continue
            if ch == fch and n >= flen:
                fence = False
                yield line, False, True
                continue
        yield line, fence, False


def sections_of(doc):
    """Map heading -> body. Fence-aware: a `## ` line inside a fence is pasted output."""
    bodies, current = {}, None
    for line, in_fence, is_delim in _fence_scan(doc.splitlines()):
        if not in_fence and not is_delim and line.startswith("## "):
            current = line.rstrip()
            bodies[current] = []
        elif current is not None:
            bodies[current].append(line)
    return {k: "\n".join(v) for k, v in bodies.items()}


def template_block(text):
    """Contents of the first fenced block inside `## Template`, outer fence stripped."""
    body = sections_of(text)["## Template"]
    out, started = [], False
    for line, in_fence, is_delim in _fence_scan(body.splitlines()):
        if is_delim and not started:
            started = True
            continue
        if is_delim and not in_fence:
            break
        if started:
            out.append(line)
    assert out, "no template block found in SKILL.md"
    return "\n".join(out)


def template_sections(text):
    return list(sections_of(template_block(text)))


def documented_sections(text):
    return [m.group(1) for m in re.finditer(r"^\|`(## [^`]+)`\|", text, re.MULTILINE)]


def _edit_section(doc, heading, new_body=None):
    """Replace a section's body, or drop the section entirely when new_body is None."""
    lines = doc.splitlines()
    flags = list(_fence_scan(lines))
    out, i, found = [], 0, False
    while i < len(lines):
        line, in_fence, is_delim = flags[i]
        if line == heading and not in_fence and not is_delim:
            found = True
            if new_body is not None:
                out.append(lines[i])
            i += 1
            while i < len(lines) and not (lines[i].startswith("## ")
                                          and not flags[i][1] and not flags[i][2]):
                i += 1
            if new_body is not None:
                out.extend(["", *new_body.splitlines(), ""])
            continue
        out.append(lines[i])
        i += 1
    assert found, f"{heading} not present"
    return "\n".join(out) + "\n"


def replace_section(doc, heading, new_body):
    return _edit_section(doc, heading, new_body)


def drop_section(doc, heading):
    return _edit_section(doc, heading, None)


def fenced_lines(body):
    return [line for line, in_fence, is_delim in _fence_scan(body.splitlines())
            if in_fence and not is_delim and line.strip() and not line.strip().startswith("#")]


def bash_block(text, heading):
    body = sections_of(text)[heading]
    out, started = [], False
    for line, in_fence, is_delim in _fence_scan(body.splitlines()):
        if is_delim and not started:
            started = True
            continue
        if is_delim and started:
            break
        if started:
            out.append(line)
    assert out, f"no bash block in {heading}"
    return "\n".join(out)


def run_validator(path, env=None, skill_md=None):
    args = [str(VALIDATOR), str(path)] + ([str(skill_md)] if skill_md else [])
    return subprocess.run(args, capture_output=True, text=True,
                          env=env or {"PATH": MINIMAL_PATH, "HOME": "/nonexistent"})


class TempRepoCase(unittest.TestCase):
    """A temp root holding the repository the good fixture describes, with the handoff in
    the repo's own notes/ directory, exactly as the skill prescribes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {"PATH": MINIMAL_PATH, "HOME": str(self.root)}
        self.repo = self.root / "scratch-repo"
        (self.repo / "notes").mkdir(parents=True)
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", f"refs/heads/{FIXTURE_BRANCH}")
        (self.repo / "admission.py").write_text(FIXTURE_SOURCE)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Widen the lease window to a half-open interval",
                 extra={"GIT_AUTHOR_DATE": FIXTURE_DATE, "GIT_COMMITTER_DATE": FIXTURE_DATE})
        (self.repo / "admission.py").write_text(
            FIXTURE_SOURCE + "\n\ndef renew(now, lease_end):\n    return now > lease_end\n")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, extra=None, check=True, repo=None):
        r = subprocess.run(["git", "-C", str(repo or self.repo), *GIT_ID, *args],
                           capture_output=True, text=True, env={**self.env, **(extra or {})})
        if check:
            self.assertEqual(r.returncode, 0, f"git {args} failed: {r.stderr}")
        return r.stdout.strip()

    def good_doc(self):
        """The fixture, with the repository it describes relocated to this temp repo."""
        return (FIXTURES / "good-handoff.md").read_text().replace(FIXTURE_PATH, str(self.repo))

    def place(self, doc, name="2026-08-25-lease-expiry.md"):
        p = self.repo / "notes" / name
        p.write_text(doc)
        return p

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

    def test_good_fixture_has_every_mandatory_section_non_empty(self):
        bodies = sections_of((FIXTURES / "good-handoff.md").read_text())
        for heading in template_sections(self.text):
            self.assertIn(heading, bodies, f"fixture is missing {heading}")
            self.assertTrue(bodies[heading].strip(), f"fixture has an empty {heading}")

    def test_good_fixture_carries_no_surviving_placeholder(self):
        doc = (FIXTURES / "good-handoff.md").read_text()
        for ph in set(re.findall(r"<[^<>]*>", template_block(self.text))):
            self.assertNotIn(ph, doc, f"fixture left the template placeholder {ph} in place")

    def test_template_resume_command_checks_out_the_sha_on_a_named_branch(self):
        cmds = fenced_lines(sections_of(template_block(self.text))["## Resume command"])
        joined = "\n".join(cmds)
        self.assertTrue(cmds[0].startswith("cd "), f"resume must be anchored: {cmds[0]}")
        self.assertRegex(cmds[0], r'cd\s+["\']', "the cd path must be quoted; paths contain spaces")
        self.assertIn("sha", joined, "the resume command must check out the recorded sha")
        self.assertIn("stash", joined, "a dirty tree aborts a bare checkout; stash first")
        self.assertRegex(joined, r"git checkout -B|git switch -C|git switch --force-create",
                         "landing on a bare sha detaches HEAD, which phase 2 calls broken")

    def test_the_skill_does_not_claim_to_preserve_uncommitted_work(self):
        """Every serialisation of a dirty tree tried here restored nothing while looking
        like it worked, so the skill states the boundary instead. Reintroducing a patch or
        an implicit stash-and-restore needs its own red-team round, not a quiet edit."""
        self.assertNotIn("git apply", self.text,
                         "a patch is atomic: one binary file or one conflicting hunk "
                         "restores nothing at all")
        self.assertNotIn(".patch", self.text)
        emergency = sections_of(self.text)["## If you have almost no context left, start here"]
        self.assertRegex(emergency, r"(?i)does not preserve uncommitted work",
                         "the reader who only reads the emergency section must be told too")
        self.assertIn("## Known limitations", self.text,
                      "what the skill cannot do belongs in the skill, not in a review thread")

    def test_the_template_requires_a_disposition_for_uncommitted_work(self):
        """Prose alone is what the emergency reader skips, so the field is mandatory."""
        state = sections_of(template_block(self.text))["## State"]
        self.assertRegex(state, r"(?m)^uncommitted work:",
                         "the state section must carry an 'uncommitted work:' line")

    def test_the_skill_does_not_offer_a_partial_validation_mode(self):
        """A mode that validates the re-derivable half and blesses the absence of the rest
        manufactures confidence rather than measuring it."""
        self.assertNotIn("--minimal", self.text)
        self.assertNotIn("--minimal", VALIDATOR.read_text())


class DocumentedCommandsTest(unittest.TestCase):
    """The state-collection block in the SKILL.md, executed against real environments.

    Four of the five give a plausible wrong answer to the obvious command, which is the
    whole reason the block is shaped the way it is."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {"PATH": MINIMAL_PATH, "HOME": str(self.root)}
        self.script = bash_block(read_skill(),
                                 "## If you have almost no context left, start here")
        self.assertNotIn("<", self.script, "the emergency block must be runnable as pasted")

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, where):
        r = subprocess.run(["bash", "-c", self.script], capture_output=True, text=True,
                           cwd=str(where), env=self.env)
        return r.stdout.splitlines()

    def make_repo(self, name, commits=True):
        d = self.root / name
        d.mkdir()
        subprocess.run(["git", "-C", str(d), "init", "-q"], env=self.env, check=True)
        subprocess.run(["git", "-C", str(d), "symbolic-ref", "HEAD", "refs/heads/main"],
                       env=self.env, check=True)
        if commits:
            (d / "f.txt").write_text("hello\n")
            subprocess.run(["git", "-C", str(d), *GIT_ID, "add", "-A"], env=self.env, check=True)
            subprocess.run(["git", "-C", str(d), *GIT_ID, "commit", "-q", "-m", "c"],
                           env=self.env, check=True)
        return d

    def test_a_normal_repo_reports_its_branch_and_full_sha(self):
        out = self.collect(self.make_repo("normal"))
        self.assertEqual(out[0], "main")
        self.assertRegex(out[1], r"^[0-9a-f]{40}$")

    def test_a_detached_head_is_reported_as_detached_not_as_HEAD(self):
        d = self.make_repo("detached")
        sha = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True,
                             text=True, env=self.env).stdout.strip()
        subprocess.run(["git", "-C", str(d), "checkout", "-q", "--detach", sha],
                       env=self.env, check=True)
        abbrev = subprocess.run(["git", "-C", str(d), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, env=self.env).stdout.strip()
        self.assertEqual(abbrev, "HEAD", "precondition: the obvious command returns HEAD here")
        self.assertEqual(self.collect(d)[0], "(detached)")

    def test_a_repo_with_no_commits_does_not_record_the_literal_HEAD(self):
        d = self.make_repo("unborn", commits=False)
        raw = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True,
                             text=True, env=self.env)
        self.assertEqual(raw.returncode, 128)
        self.assertEqual(raw.stdout.strip(), "HEAD",
                         "precondition: rev-parse prints HEAD on stdout while failing")
        self.assertEqual(self.collect(d)[:2], ["main", "none (no commits yet)"])

    def test_a_bare_repo_is_not_also_reported_as_not_a_repository(self):
        """`A && { ...; } || C` runs C when anything inside the braces fails, and
        `git status` fails in a bare repo. The block uses if/then/else for this."""
        src = self.make_repo("src")
        bare = self.root / "bare.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(src), str(bare)],
                       env=self.env, check=True)
        out = self.collect(bare)
        self.assertNotIn("none (not a git repository)", out,
                         f"a bare repo reported itself as both a repo and not one: {out}")
        self.assertRegex(out[1], r"^[0-9a-f]{40}$")

    def test_a_plain_directory_is_not_reported_as_a_detached_head(self):
        d = self.root / "plain"
        d.mkdir()
        unguarded = subprocess.run(
            ["bash", "-c", 'git symbolic-ref --quiet --short HEAD || echo "(detached)"'],
            capture_output=True, text=True, cwd=str(d), env=self.env)
        self.assertEqual(unguarded.stdout.strip(), "(detached)",
                         "precondition: the unguarded form lies here")
        self.assertEqual(self.collect(d), ["none (not a git repository)"])

    def test_the_emergency_block_does_not_shout_help_text_in_a_non_repo(self):
        """At zero context budget, a stray `git diff` dumps ~70 lines of usage."""
        d = self.root / "plain2"
        d.mkdir()
        r = subprocess.run(["bash", "-c", self.script], capture_output=True, text=True,
                           cwd=str(d), env=self.env)
        self.assertLess(len(r.stderr.splitlines()), 5, f"noisy stderr:\n{r.stderr}")


class ValidatorTest(TempRepoCase):

    def test_validator_is_executable(self):
        self.assertTrue(os.access(VALIDATOR, os.X_OK), f"{VALIDATOR} is not executable")

    def test_the_repo_reproduces_the_sha_and_the_porcelain_the_fixture_names(self):
        self.assertEqual(self.git("rev-parse", "HEAD"), FIXTURE_SHA)
        self.place(self.good_doc())
        porcelain = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                                   capture_output=True, text=True, env=self.env).stdout
        self.assertEqual(porcelain, " M admission.py\n?? notes/\n")
        self.assertIn(porcelain.rstrip("\n"), self.good_doc())

    def test_validator_accepts_the_good_fixture(self):
        r = self.check(self.good_doc())
        self.assertEqual(r.returncode, 0, f"good fixture rejected:\n{r.stdout}{r.stderr}")

    def test_the_unrelocated_fixture_is_rejected_because_its_repo_is_not_here(self):
        r = run_validator(FIXTURES / "good-handoff.md", env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("UNREACHABLE_REPO", r.stdout)

    def test_validator_rejects_a_summarised_handoff(self):
        r = run_validator(FIXTURES / "bad-handoff.md", env=self.env)
        self.assertEqual(r.returncode, 1)
        for rule in ("BRANCH_IS_HEAD", "NO_SHA", "NO_RESUME_COMMAND",
                     "SUMMARISED_ERROR", "NO_REPRO", "NON_ANSWER"):
            self.assertIn(rule, r.stdout, f"{rule} should have fired:\n{r.stdout}")

    def test_validator_rejects_a_missing_section(self):
        r = self.check(drop_section(self.good_doc(), "## Dead ends"))
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

    def test_a_missing_state_section_does_not_cascade(self):
        r = self.check(drop_section(self.good_doc(), "## State"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING_SECTION ## State", r.stdout)
        for noise in ("NO_BRANCH", "NO_SHA"):
            self.assertNotIn(noise, r.stdout,
                             f"{noise} names a section that is absent:\n{r.stdout}")


class ValidatorRobustnessTest(TempRepoCase):
    """The validator must reject, never abort. An abort reads as a pass to anyone who is
    not watching stderr, and silently skips every rule after it."""

    def test_prose_in_the_resume_section_rejects_instead_of_crashing(self):
        doc = replace_section(self.good_doc(), "## Resume command",
                              "Just pick up where we left off.")
        doc = re.sub(r"^repro: .*$", "", doc, flags=re.MULTILINE)
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("unbound variable", r.stderr, f"the script crashed:\n{r.stderr}")
        self.assertEqual(r.stderr.strip(), "", f"unexpected stderr:\n{r.stderr}")
        self.assertIn("NO_RESUME_COMMAND", r.stdout)
        self.assertIn("UNVERIFIABLE_COMMIT", r.stdout)
        self.assertIn("NO_REPRO", r.stdout,
                      "rules after the failure point must still run:\n" + r.stdout)

    def test_a_tilde_fence_containing_a_heading_does_not_truncate_its_section(self):
        state = sections_of(self.good_doc())["## State"]
        injected = state.replace(f"commit: {FIXTURE_SHA}",
                                 "~~~\n## Tree\nsome pasted listing\n~~~\n\n"
                                 f"commit: {FIXTURE_SHA}")
        r = self.check(replace_section(self.good_doc(), "## State", injected))
        self.assertEqual(r.returncode, 0, f"a tilde fence broke section parsing:\n{r.stdout}")


class FenceAwarenessTest(TempRepoCase):
    """Pasted output is the point of the document, so it must not be parsed as markup, and
    must not be punished for containing words the author never wrote."""

    def test_the_fixture_really_does_paste_output_containing_headings(self):
        doc = self.good_doc()
        raw = len([l for l in doc.splitlines() if l.startswith("## ")])
        self.assertGreater(raw, len(sections_of(doc)),
                           "this test is only meaningful if the fixture pastes '## ' lines "
                           "inside a fence; it no longer does")
        self.assertIn("## Tree", sections_of(doc)["## Broken"])

    def test_a_repro_line_below_pasted_headings_is_still_found(self):
        r = self.check(self.good_doc())
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("NO_REPRO", r.stdout)

    def test_pasted_output_is_never_read_as_an_elision(self):
        """A real traceback frame in etc.py, and a tool that truncates its own output, are
        both correctly pasted. Rejecting them would make editing the paste the only way to
        pass, which is exactly what the Iron Law forbids."""
        self.assertIn('File "/usr/lib/python3.11/etc.py"', self.good_doc(),
                      "the fixture must keep pinning this")
        self.assertEqual(self.check(self.good_doc()).returncode, 0)

        doc = replace_section(self.good_doc(), "## Broken",
                              "- test_x\n\n```\nE  AssertionError: expected 1\n"
                              "E  ...(truncated by pytest)\n```\n\nrepro: python3 -m pytest -q")
        r = self.check(doc)
        self.assertEqual(r.returncode, 0,
                         f"a tool's own truncation notice is not the author's:\n{r.stdout}")

    def test_an_elision_written_by_the_author_is_still_rejected(self):
        doc = replace_section(self.good_doc(), "## Broken",
                              "- test_x fails with an AssertionError (truncated)\n\n"
                              "```\nE  AssertionError\n```\n\nrepro: python3 -m pytest -q")
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn("TRUNCATED_OUTPUT", r.stdout)


class FabricatedStateTest(TempRepoCase):
    """There must be no path on which a sha is accepted without being checked."""

    def test_a_fake_sha_pointed_at_a_directory_that_is_not_a_repo_is_rejected(self):
        plain = self.root / "notarepo"
        plain.mkdir()
        doc = (self.good_doc().replace(str(self.repo), str(plain))
                             .replace(FIXTURE_SHA, "deadbeef" * 5))
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn("UNVERIFIABLE_COMMIT", r.stdout)

    def test_a_real_sha_from_an_unrelated_repository_is_rejected(self):
        other = self.root / "other"
        other.mkdir()
        self.git("init", "-q", repo=other)
        (other / "x").write_text("x")
        self.git("add", "-A", repo=other)
        self.git("commit", "-q", "-m", "unrelated", repo=other)
        foreign = self.git("rev-parse", "HEAD", repo=other)
        self.assertNotEqual(foreign, FIXTURE_SHA)
        r = self.check(self.good_doc().replace(FIXTURE_SHA, foreign))
        self.assertEqual(r.returncode, 1)
        self.assertIn("UNKNOWN_COMMIT", r.stdout)

    def test_a_seven_character_sha_is_rejected(self):
        r = self.check(self.good_doc().replace(f"commit: {FIXTURE_SHA}",
                                               f"commit: {FIXTURE_SHA[:7]}"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO_SHA", r.stdout)

    def test_a_plain_directory_must_be_recorded_as_one(self):
        plain = self.root / "plain"
        (plain / "notes").mkdir(parents=True)
        p = plain / "notes" / "h.md"
        p.write_text(self.good_doc().replace(str(self.repo), str(plain)))
        r = run_validator(p, env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("BRANCH_CONTRADICTS_REPO", r.stdout)

    def test_a_repo_with_no_commits_records_none_and_is_accepted(self):
        unborn = self.root / "unborn"
        (unborn / "notes").mkdir(parents=True)
        self.git("init", "-q", repo=unborn)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", repo=unborn)
        doc = (self.good_doc().replace(str(self.repo), str(unborn))
               .replace(f"branch: {FIXTURE_BRANCH}", "branch: main")
               .replace(f"commit: {FIXTURE_SHA}", "commit: none (no commits yet)"))
        doc = replace_section(doc, "## Resume command", f'```bash\ncd "{unborn}"\ngit status\n```')
        p = unborn / "notes" / "h.md"
        p.write_text(doc)
        r = run_validator(p, env=self.env)
        self.assertEqual(r.returncode, 0, f"an unborn repo must be recordable:\n{r.stdout}")

    def test_the_literal_HEAD_as_a_commit_is_rejected(self):
        r = self.check(self.good_doc().replace(f"commit: {FIXTURE_SHA}", "commit: HEAD"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO_SHA", r.stdout)


class ResumeCommandTest(TempRepoCase):
    """The command must land on the recorded state in the case it exists for."""

    def resume_from(self, doc, cwd=None):
        command = "\n".join(fenced_lines(sections_of(doc)["## Resume command"]))
        self.assertTrue(command.strip(), "no runnable resume command in the handoff")
        return subprocess.run(["bash", "-c", command], capture_output=True, text=True,
                              cwd=str(cwd or self.root), env=self.env)

    def move_the_tip_and_dirty_the_tree(self):
        (self.repo / "admission.py").write_text(FIXTURE_SOURCE + "\n# later work\n")
        self.git("commit", "-q", "-a", "-m", "later work on the same branch")
        moved = self.git("rev-parse", "HEAD")
        self.assertNotEqual(moved, FIXTURE_SHA)
        (self.repo / "admission.py").write_text(FIXTURE_SOURCE + "\n# later\n# uncommitted\n")
        self.assertTrue(self.git("status", "--porcelain"), "precondition: the tree is dirty")
        return moved

    def test_resume_lands_on_the_recorded_commit_with_a_moved_tip_and_a_dirty_tree(self):
        doc = self.good_doc()
        self.place(doc)
        self.assertEqual(run_validator(self.repo / "notes" / "2026-08-25-lease-expiry.md",
                                       env=self.env).returncode, 0)
        moved = self.move_the_tip_and_dirty_the_tree()
        r = self.resume_from(doc)
        self.assertEqual(r.returncode, 0,
                         f"resume failed on the state it exists for:\n{r.stdout}{r.stderr}")
        head = self.git("rev-parse", "HEAD")
        self.assertEqual(head, FIXTURE_SHA,
                         f"landed on {head}, not the recorded {FIXTURE_SHA} (tip was {moved})")

    def test_resume_leaves_a_named_branch_not_a_detached_head(self):
        self.move_the_tip_and_dirty_the_tree()
        self.resume_from(self.good_doc())
        self.assertEqual(self.git("symbolic-ref", "--quiet", "--short", "HEAD"),
                         "resume/lease-expiry",
                         "phase 2 calls a detached HEAD broken, so resume must not create one")

    def test_what_the_resume_displaces_is_findable_afterwards(self):
        self.move_the_tip_and_dirty_the_tree()
        self.resume_from(self.good_doc())
        stashes = self.git("stash", "list")
        self.assertEqual(len(stashes.splitlines()), 1,
                         "the tree the resume parked must be recoverable, not discarded")
        self.assertIn("before resuming", stashes,
                      "the stash must be labelled so the user can find it")

    def test_resume_works_from_an_unrelated_working_directory(self):
        self.move_the_tip_and_dirty_the_tree()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        r = self.resume_from(self.good_doc(), cwd=elsewhere)
        self.assertEqual(r.returncode, 0, f"{r.stdout}{r.stderr}")
        self.assertEqual(self.git("rev-parse", "HEAD"), FIXTURE_SHA)

    def test_a_repo_path_containing_a_space_validates_and_runs(self):
        spaced = self.root / "my repo"
        (spaced / "notes").mkdir(parents=True)
        self.git("init", "-q", repo=spaced)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", repo=spaced)
        (spaced / "f").write_text("f")
        self.git("add", "-A", repo=spaced)
        self.git("commit", "-q", "-m", "c", repo=spaced)
        sha = self.git("rev-parse", "HEAD", repo=spaced)
        doc = (self.good_doc().replace(str(self.repo), str(spaced))
               .replace(f"branch: {FIXTURE_BRANCH}", "branch: main")
               .replace(FIXTURE_SHA, sha))
        p = spaced / "notes" / "h.md"
        p.write_text(doc)
        r = run_validator(p, env=self.env)
        self.assertEqual(r.returncode, 0, f"a path with a space was rejected:\n{r.stdout}")
        run = self.resume_from(doc)
        self.assertEqual(run.returncode, 0, f"the quoted cd must run:\n{run.stderr}")
        self.assertEqual(self.git("rev-parse", "HEAD", repo=spaced), sha)

    def test_a_relative_cd_is_rejected_because_it_depends_on_the_caller(self):
        r = self.check(self.good_doc().replace(f'cd "{self.repo}"', "cd .."))
        self.assertEqual(r.returncode, 1)
        self.assertIn("RESUME_PATH_NOT_ABSOLUTE", r.stdout)

    def test_a_branch_only_resume_command_is_rejected(self):
        r = self.check(self.good_doc().replace(
            f"git checkout -B resume/lease-expiry {FIXTURE_SHA}",
            f"git checkout {FIXTURE_BRANCH}"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("RESUME_MISSING_SHA", r.stdout)

    def test_merely_mentioning_the_sha_is_not_checking_it_out(self):
        r = self.check(self.good_doc().replace(
            f"git checkout -B resume/lease-expiry {FIXTURE_SHA}", f"echo {FIXTURE_SHA}"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("RESUME_DOES_NOT_CHECKOUT", r.stdout)

    def test_branch_recorded_as_the_literal_HEAD_is_rejected(self):
        r = self.check(self.good_doc().replace(f"branch: {FIXTURE_BRANCH}", "branch: HEAD"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("BRANCH_IS_HEAD", r.stdout)


class HostileInputTest(TempRepoCase):
    """Inputs shaped to satisfy the letter of the rules and none of the point."""

    def assert_rejected_with(self, doc, rule):
        r = self.check(doc)
        self.assertEqual(r.returncode, 1, f"expected {rule}, got exit 0")
        self.assertIn(rule, r.stdout, f"expected {rule}, got:\n{r.stdout}")

    def test_a_resume_fence_holding_only_a_comment_is_rejected(self):
        self.assert_rejected_with(replace_section(
            self.good_doc(), "## Resume command",
            "```bash\n# TODO: figure out where the repo lives\n```"), "NO_RESUME_COMMAND")

    def test_a_one_character_resume_command_is_rejected(self):
        self.assert_rejected_with(replace_section(
            self.good_doc(), "## Resume command", "```bash\nx\n```"), "RESUME_NOT_ANCHORED")

    def test_a_resume_command_naming_a_directory_that_is_gone_is_rejected(self):
        self.assert_rejected_with(
            self.good_doc().replace(str(self.repo), "/no/such/directory"), "UNREACHABLE_REPO")

    def test_a_no_op_repro_is_rejected(self):
        self.assert_rejected_with(
            re.sub(r"^repro: .*$", "repro: true", self.good_doc(), flags=re.MULTILINE),
            "TRIVIAL_REPRO")

    def test_a_bare_ellipsis_standing_in_for_prose_is_rejected(self):
        self.assert_rejected_with(
            replace_section(self.good_doc(), "## Dead ends", "..."), "TRUNCATED_OUTPUT")

    def test_tbd_is_not_an_answer(self):
        self.assert_rejected_with(
            replace_section(self.good_doc(), "## Done and verified", "TBD"), "NON_ANSWER")

    def test_see_above_is_not_an_answer(self):
        self.assert_rejected_with(
            replace_section(self.good_doc(), "## Dead ends", "see above"), "NON_ANSWER")

    def test_the_sanctioned_empty_marker_is_still_accepted(self):
        r = self.check(replace_section(self.good_doc(), "## Dead ends", "None."))
        self.assertEqual(r.returncode, 0, f"'None.' must remain valid:\n{r.stdout}")


class RenameDriftTest(TempRepoCase):
    """The special-rule sections are located by marker, so a rename must carry."""

    def renamed_skill(self, old, new):
        copy = self.root / "SKILL.md"
        copy.write_text(re.sub(rf"^{re.escape(old)}$", new, read_skill(), flags=re.MULTILINE))
        return copy

    def test_renaming_the_broken_section_carries_to_the_rules(self):
        r = self.check(self.good_doc().replace("## Broken", "## Failing"),
                       skill_md=self.renamed_skill("## Broken", "## Failing"))
        self.assertEqual(r.returncode, 0, f"a coordinated rename must validate:\n{r.stdout}")

    def test_a_renamed_broken_section_is_policed_under_its_new_name(self):
        doc = re.sub(r"^repro: .*$", "", self.good_doc().replace("## Broken", "## Failing"),
                     flags=re.MULTILINE)
        r = self.check(doc, skill_md=self.renamed_skill("## Broken", "## Failing"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO_REPRO ## Failing", r.stdout)
        self.assertNotIn("## Broken", r.stdout, "named a section that no longer exists")

    def test_renaming_the_state_section_carries_to_the_rules(self):
        r = self.check(self.good_doc().replace("## State", "## Tree"),
                       skill_md=self.renamed_skill("## State", "## Tree"))
        self.assertEqual(r.returncode, 0, f"rename broke the state rules:\n{r.stdout}")

    def test_adding_a_section_to_the_template_makes_it_mandatory(self):
        copy = self.root / "SKILL.md"
        copy.write_text(read_skill().replace(
            "- <trap a fresh session would hit>",
            "- <trap a fresh session would hit>\n\n## Budget\n\n- <what is left>"))
        r = self.check(self.good_doc(), skill_md=copy)
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING_SECTION ## Budget", r.stdout)

    def test_an_ambiguous_marker_in_the_template_is_a_loud_failure(self):
        copy = self.root / "SKILL.md"
        copy.write_text(read_skill().replace(
            "## Done and verified\n\n- <what changed>.",
            "## Mirror\n\nbranch: <a second branch line>\n\n"
            "## Done and verified\n\n- <what changed>."))
        r = self.check(self.good_doc(), skill_md=copy)
        self.assertEqual(r.returncode, 2, f"ambiguity must not be resolved silently:\n{r.stdout}")
        self.assertIn("must be unique", r.stderr)


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
        self.assertEqual(re.search(r"^name: *(\S+)", self.fm, re.MULTILINE).group(1),
                         SKILL_DIR.name)

    def test_frontmatter_under_1024_chars(self):
        self.assertLessEqual(len(self.fm), 1024, f"frontmatter is {len(self.fm)} chars")

    def test_description_under_500_chars(self):
        self.assertLessEqual(len(self.description()), 500,
                             f"description is {len(self.description())} chars")

    def test_description_excludes_a_mid_session_recap(self):
        d = self.description().lower()
        self.assertRegex(d, r"\b(do not use|not for|never use)\b")
        self.assertIn("recap", d, "the must-not-fire list includes a mid-session recap, "
                                  "so the description has to exclude it")

    def test_body_under_500_lines(self):
        self.assertLessEqual(len(self.text.split("\n---\n", 1)[1].splitlines()), 500)

    def test_the_emergency_section_comes_before_the_rationale(self):
        lines = self.text.splitlines()
        first = next(i for i, l in enumerate(lines)
                     if l.startswith("## If you have almost no context"))
        rationale = next(i for i, l in enumerate(lines) if l.startswith("## Why this exists"))
        self.assertLess(first, 40, f"the emergency section starts at line {first + 1}")
        self.assertLess(first, rationale, "the rationale must sit below the procedure")

    def test_no_em_dashes_anywhere_in_the_skill(self):
        em_dash = "\u2014"  # escaped so this file passes its own check
        for path in sorted(SKILL_DIR.rglob("*")) + sorted(FIXTURES.rglob("*")) + [Path(__file__)]:
            if path.is_file():
                self.assertNotIn(em_dash, path.read_text(), f"em-dash in {path}")


class SilentRuleSuppressionTest(TempRepoCase):
    """Rules must not stop running just because the input got big or oddly shaped.

    Both failures here read as a pass to anyone who is not comparing the reject list
    against the document, which is the same class of defect twice over."""

    def test_a_multi_megabyte_section_does_not_disable_the_rules_that_scan_it(self):
        """`grep -q` exits on its first match, SIGPIPEing its writer. Under pipefail that
        141 reads as "no match", so a long pasted section silently turns rules off. This
        is exactly the input the skill demands: never abbreviate, paste it all."""
        huge = "\n".join(
            f"- a dead end that did not work, recorded at length [snip] number {i}"
            for i in range(25000))
        self.assertGreater(len(huge), 1_500_000, "the section must exceed the pipe buffer")
        r = self.check(replace_section(self.good_doc(), "## Dead ends", huge))
        self.assertNotIn("EMPTY_SECTION", r.stdout,
                         f"a 1.5MB section was reported empty:\n{r.stdout}")
        self.assertIn("TRUNCATED_OUTPUT", r.stdout,
                      f"the elision rule stopped running on a large section:\n{r.stdout}")

    def test_an_indented_fence_does_not_cascade_false_missing_sections(self):
        """A CommonMark-legal fence indented under a bullet. When the opener is missed but
        the closer is not, the rest of the file reads as fenced, and the reader cannot fix
        it by following any of the messages they get."""
        indented = ("- a second symptom, output indented under the bullet:\n\n"
                    "  ```\n  E  IndexError: list index out of range\n```\n\n"
                    "repro: python3 -m pytest -q")
        doc = self.good_doc().replace("repro: python3 -m pytest tests/test_notes.py"
                                      "::test_handoff_has_state -q", indented)
        r = self.check(doc)
        self.assertEqual(r.returncode, 0, f"an indented fence broke parsing:\n{r.stdout}")

    def test_crlf_input_is_normalised_rather_than_reported_as_twelve_missing_sections(self):
        doc = self.good_doc().replace("\n", "\r\n")
        p = self.repo / "notes" / "crlf.md"
        p.write_bytes(doc.encode())
        r = run_validator(p, env=self.env)
        self.assertEqual(r.returncode, 0, f"CRLF broke parsing:\n{r.stdout}")

    def test_an_unset_HOME_still_produces_rejects_rather_than_an_abort(self):
        doc = self.good_doc().replace(f"branch: {FIXTURE_BRANCH}", "branch: HEAD")
        p = self.place(doc)
        r = subprocess.run([str(VALIDATOR), str(p)], capture_output=True, text=True,
                           env={"PATH": MINIMAL_PATH})
        self.assertNotIn("unbound variable", r.stderr, r.stderr)
        self.assertEqual(r.returncode, 1)
        self.assertIn("BRANCH_IS_HEAD", r.stdout)


class UncommittedDispositionTest(TempRepoCase):
    """The one loss nothing here can undo is the one thing that must not be eyeballed."""

    def test_the_line_is_required(self):
        doc = re.sub(r"^uncommitted work:.*$\n", "", self.good_doc(), flags=re.MULTILINE)
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO_UNCOMMITTED_LINE", r.stdout)

    def test_claiming_none_while_the_tree_is_dirty_is_rejected(self):
        self.assertTrue(self.git("status", "--porcelain"), "precondition: the tree is dirty")
        doc = re.sub(r"^uncommitted work:.*$", "uncommitted work: none", self.good_doc(),
                     flags=re.MULTILINE)
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn("UNCOMMITTED_CONTRADICTS_TREE", r.stdout)

    def test_claiming_none_with_a_clean_tree_is_accepted(self):
        clean = self.root / "clean"
        (clean / "notes").mkdir(parents=True)
        self.git("init", "-q", repo=clean)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", repo=clean)
        (clean / "f").write_text("f")
        (clean / ".gitignore").write_text("notes/\n")
        self.git("add", "-A", repo=clean)
        self.git("commit", "-q", "-m", "c", repo=clean)
        sha = self.git("rev-parse", "HEAD", repo=clean)
        self.assertEqual(self.git("status", "--porcelain", repo=clean), "",
                         "precondition: the tree is clean")
        doc = (self.good_doc().replace(str(self.repo), str(clean))
               .replace(f"branch: {FIXTURE_BRANCH}", "branch: main")
               .replace(FIXTURE_SHA, sha))
        doc = re.sub(r"^uncommitted work:.*$", "uncommitted work: none", doc, flags=re.MULTILINE)
        p = clean / "notes" / "h.md"
        p.write_text(doc)
        r = run_validator(p, env=self.env)
        self.assertEqual(r.returncode, 0, f"a clean tree may say none:\n{r.stdout}")

    def test_a_bare_ellipsis_as_a_list_item_does_not_escape_the_rule(self):
        r = self.check(replace_section(self.good_doc(), "## Next", "1. keep going\n2. ..."))
        self.assertEqual(r.returncode, 1)
        self.assertIn("TRUNCATED_OUTPUT", r.stdout)


if __name__ == "__main__":
    unittest.main()
