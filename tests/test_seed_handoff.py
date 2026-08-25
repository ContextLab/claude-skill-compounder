#!/usr/bin/env python3
"""Tests the `session-handoff` seed skill against real files and real git repositories.

The skill makes two headline claims, and both are executed here rather than inspected.
"The resume command lands you on the recorded state" is tested by moving the branch tip,
dirtying the tree, and running the command out of the handoff from an unrelated working
directory. "The validator proves rather than pattern-matches" is tested by feeding it
inputs shaped to satisfy the letter of every rule, including a fabricated sha pointed at a
directory that is not a repository.

The state-collection block in the SKILL.md is extracted and executed against four real
environments (a normal repo, a detached HEAD, a repo with no commits, and a plain
directory), because three of those print a plausible wrong answer to the obvious command.

No mocks: real files, the real bash validator, real git."""

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
PATCH_NAME = "2026-08-25-lease-expiry.patch"

PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
MINIMAL_PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

# The repository the good fixture describes. Author, committer, timestamps, branch and
# tree are pinned, so the sha is reproducible and the fixture can name it literally.
FIXTURE_BRANCH = "fix/lease-expiry"
FIXTURE_SHA = "f882c1ac93d08b780caba472786173d2fdd45b78"
FIXTURE_DATE = "2026-08-25T10:00:00+0000"
FIXTURE_PATH = "/srv/checkouts/admission"  # where the fixture's repo lived; tests relocate it
FIXTURE_SOURCE = "def is_expired(now, lease_end):\n    return now > lease_end\n"
FIXTURE_DIRTY = FIXTURE_SOURCE + "\n\ndef renew(now, lease_end):\n    return now > lease_end\n"
GIT_ID = ["-c", "user.name=Handoff Fixture", "-c", "user.email=fixture@example.invalid"]


def read_skill():
    return SKILL_MD.read_text()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "SKILL.md must open with a YAML frontmatter block"
    return m.group(1)


def _fence_scan(lines):
    """Yield (line, in_fence, is_delimiter), mirroring the validator's fence tracker.

    A fence closes only on a backtick run at least as long as the one that opened it, so a
    four-backtick block may contain three-backtick blocks."""
    fence, flen = False, 0
    for line in lines:
        m = re.match(r"^`+", line)
        if m and len(m.group(0)) >= 3:
            n = len(m.group(0))
            if not fence:
                fence, flen = True, n
                yield line, True, True
                continue
            if n >= flen:
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
    return [h for h in sections_of(template_block(text))]


def documented_sections(text):
    return [m.group(1) for m in re.finditer(r"^\|`(## [^`]+)`\|", text, re.MULTILINE)]


def replace_section(doc, heading, new_body):
    lines, out, i, found = doc.splitlines(), [], 0, False
    flags = list(_fence_scan(lines))
    while i < len(lines):
        out.append(lines[i])
        line, in_fence, is_delim = flags[i]
        if line == heading and not in_fence and not is_delim:
            found = True
            i += 1
            while i < len(lines) and not (lines[i].startswith("## ")
                                          and not flags[i][1] and not flags[i][2]):
                i += 1
            out.extend(["", *new_body.splitlines(), ""])
            continue
        i += 1
    assert found, f"{heading} not present, cannot replace it"
    return "\n".join(out) + "\n"


def drop_section(doc, heading):
    lines, out, i = doc.splitlines(), [], 0
    flags = list(_fence_scan(lines))
    while i < len(lines):
        line, in_fence, is_delim = flags[i]
        if line == heading and not in_fence and not is_delim:
            i += 1
            while i < len(lines) and not (lines[i].startswith("## ")
                                          and not flags[i][1] and not flags[i][2]):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out) + "\n"


def fenced_lines(body):
    return [line for line, in_fence, is_delim in _fence_scan(body.splitlines())
            if in_fence and not is_delim and line.strip() and not line.strip().startswith("#")]


def bash_block(text, heading):
    """The first ```bash block inside a SKILL.md section."""
    body = sections_of(text)[heading]
    out, started = [], False
    for line, in_fence, is_delim in _fence_scan(body.splitlines()):
        if is_delim and not started and line.strip().startswith("```"):
            started = True
            continue
        if is_delim and started:
            break
        if started:
            out.append(line)
    assert out, f"no bash block in {heading}"
    return "\n".join(out)


def run_validator(path, env=None, skill_md=None, minimal=False):
    args = [str(VALIDATOR)] + (["--minimal"] if minimal else []) + [str(path)]
    if skill_md:
        args.append(str(skill_md))
    return subprocess.run(args, capture_output=True, text=True,
                          env=env or {"PATH": MINIMAL_PATH, "HOME": "/nonexistent"})


class TempRepoCase(unittest.TestCase):
    """A temp root holding the repository the good fixture describes, with the handoff and
    its patch in the repo's own notes/ directory, exactly as the skill prescribes."""

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
        (self.repo / "admission.py").write_text(FIXTURE_DIRTY)
        (self.repo / "notes" / PATCH_NAME).write_text((FIXTURES / PATCH_NAME).read_text())

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
        self.assertIn("sha", joined, "the resume command must check out the recorded sha")
        self.assertIn("stash", joined, "a dirty tree aborts a bare checkout; stash first")
        self.assertRegex(joined, r"git checkout -B|git switch -C|git switch --force-create",
                         "landing on a bare sha detaches HEAD, which phase 2 calls broken")

    def test_template_state_records_the_uncommitted_work(self):
        state = sections_of(template_block(self.text))["## State"]
        for marker in ("branch:", "commit:", "uncommitted:"):
            self.assertRegex(state, rf"(?m)^{marker}",
                             f"the state section must carry {marker}")


class DocumentedCommandsTest(unittest.TestCase):
    """The state-collection block in the SKILL.md, executed against real environments.

    Three of the four print a plausible wrong answer to the obvious command, which is the
    whole reason the block is shaped the way it is."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {"PATH": MINIMAL_PATH, "HOME": str(self.root)}
        block = bash_block(read_skill(), "## If you have almost no context left, do only this")
        self.script = block.replace("T=<topic>", "T=lease-expiry")
        self.assertNotIn("<", self.script, "the fallback block must be runnable once T is set")

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
        d = self.make_repo("normal")
        out = self.collect(d)
        self.assertEqual(out[0], "main")
        self.assertRegex(out[1], r"^[0-9a-f]{40}$")

    def test_a_detached_head_is_reported_as_detached_not_as_HEAD(self):
        d = self.make_repo("detached")
        sha = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True,
                             text=True, env=self.env).stdout.strip()
        subprocess.run(["git", "-C", str(d), "checkout", "-q", "--detach", sha], env=self.env,
                       check=True)
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
        out = self.collect(d)
        self.assertEqual(out[0], "main")
        self.assertEqual(out[1], "none (no commits yet)")

    def test_a_plain_directory_is_not_reported_as_a_detached_head(self):
        d = self.root / "plain"
        d.mkdir()
        unguarded = subprocess.run(
            ["bash", "-c", 'git symbolic-ref --quiet --short HEAD || echo "(detached)"'],
            capture_output=True, text=True, cwd=str(d), env=self.env)
        self.assertEqual(unguarded.stdout.strip(), "(detached)",
                         "precondition: the unguarded form lies here")
        self.assertEqual(self.collect(d), ["none (not a git repository)"])


class ValidatorTest(TempRepoCase):

    def test_validator_is_executable(self):
        self.assertTrue(os.access(VALIDATOR, os.X_OK), f"{VALIDATOR} is not executable")

    def test_the_repo_reproduces_the_sha_and_the_porcelain_the_fixture_names(self):
        self.assertEqual(self.git("rev-parse", "HEAD"), FIXTURE_SHA)
        porcelain = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                                   capture_output=True, text=True, env=self.env).stdout
        self.assertEqual(porcelain, " M admission.py\n?? notes/\n")
        self.assertIn(porcelain.rstrip("\n"), self.good_doc())

    def test_validator_accepts_the_good_fixture(self):
        r = self.check(self.good_doc())
        self.assertEqual(r.returncode, 0, f"good fixture rejected:\n{r.stdout}{r.stderr}")

    def test_the_unrelocated_fixture_is_rejected_because_its_repo_is_not_here(self):
        """Reachability is enforced, not skipped when the path is absent."""
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

    def test_a_missing_state_section_does_not_cascade_into_contradictory_rejects(self):
        r = self.check(drop_section(self.good_doc(), "## State"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING_SECTION ## State", r.stdout)
        for noise in ("NO_BRANCH", "NO_SHA", "NO_UNCOMMITTED_LINE"):
            self.assertNotIn(noise, r.stdout,
                             f"{noise} names a section that is absent:\n{r.stdout}")


class FenceAwarenessTest(TempRepoCase):
    """B3: pasted output is the point of the document, so it must not be parsed as markup."""

    def test_the_fixture_really_does_paste_output_containing_headings(self):
        doc = self.good_doc()
        raw = len([l for l in doc.splitlines() if l.startswith("## ")])
        real = len(sections_of(doc))
        self.assertGreater(raw, real,
                           "this test is only meaningful if the fixture pastes '## ' lines "
                           "inside a fence; it no longer does")
        self.assertIn("## Tree", sections_of(doc)["## Broken"],
                      "the pasted heading must land inside the Broken section's body")

    def test_a_repro_line_below_pasted_headings_is_still_found(self):
        r = self.check(self.good_doc())
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("NO_REPRO", r.stdout,
                         "the repro line sits below a fence containing '## ' lines")

    def test_obeying_the_iron_law_does_not_force_a_truncation_reject(self):
        """Pasting in full must not be punished, and trimming must not be the way out."""
        clean = self.check(self.good_doc())
        self.assertEqual(clean.returncode, 0)
        trimmed = self.check(replace_section(
            self.good_doc(), "## Broken",
            "- test_handoff_has_state\n\n```\nAssertionError ... (truncated)\n```\n\n"
            "repro: python3 -m pytest -q"))
        self.assertIn("TRUNCATED_OUTPUT", trimmed.stdout)


class FabricatedStateTest(TempRepoCase):
    """B1: there must be no path on which a sha is accepted without being checked."""

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
        doc = self.good_doc().replace(str(self.repo), str(plain))
        p = plain / "notes" / "h.md"
        p.write_text(doc)
        (plain / "notes" / PATCH_NAME).write_text((FIXTURES / PATCH_NAME).read_text())
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
               .replace(f"commit: {FIXTURE_SHA}", "commit: none (no commits yet)")
               .replace("uncommitted: notes/" + PATCH_NAME, "uncommitted: none"))
        doc = replace_section(doc, "## Resume command", f"```bash\ncd {unborn}\ngit status\n```")
        p = unborn / "notes" / "h.md"
        p.write_text(doc)
        r = run_validator(p, env=self.env)
        self.assertEqual(r.returncode, 0, f"an unborn repo must be recordable:\n{r.stdout}")

    def test_the_literal_HEAD_as_a_commit_is_rejected(self):
        r = self.check(self.good_doc().replace(f"commit: {FIXTURE_SHA}", "commit: HEAD"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO_SHA", r.stdout)


class UncommittedWorkTest(TempRepoCase):
    """B2: git status records filenames; the content lives only in the patch."""

    def test_the_uncommitted_line_is_mandatory(self):
        doc = self.good_doc().replace(f"uncommitted: notes/{PATCH_NAME}\n", "")
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO_UNCOMMITTED_LINE", r.stdout)

    def test_a_named_patch_that_is_not_there_is_rejected(self):
        (self.repo / "notes" / PATCH_NAME).unlink()
        r = self.check(self.good_doc())
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING_PATCH", r.stdout)

    def test_a_patch_the_resume_command_never_applies_is_rejected(self):
        doc = self.good_doc().replace(f"git apply notes/{PATCH_NAME}\n", "")
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO_PATCH_APPLY", r.stdout)

    def test_applying_a_patch_that_was_never_recorded_is_rejected(self):
        doc = self.good_doc().replace(f"uncommitted: notes/{PATCH_NAME}", "uncommitted: none")
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn("STRAY_PATCH_APPLY", r.stdout)


class ResumeCommandTest(TempRepoCase):
    """B2: the command must land on the recorded state in the case it exists for."""

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
        (self.repo / "admission.py").write_text(FIXTURE_SOURCE + "\n# later work\n# uncommitted\n")
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
        doc = self.good_doc()
        self.move_the_tip_and_dirty_the_tree()
        self.resume_from(doc)
        self.assertEqual(self.git("symbolic-ref", "--quiet", "--short", "HEAD"),
                         "resume/lease-expiry",
                         "phase 2 calls a detached HEAD broken, so resume must not create one")

    def test_resume_restores_the_uncommitted_work_and_keeps_what_it_displaced(self):
        doc = self.good_doc()
        self.move_the_tip_and_dirty_the_tree()
        self.resume_from(doc)
        self.assertIn("def renew", (self.repo / "admission.py").read_text(),
                      "the patch must put the uncommitted work back")
        self.assertEqual(len(self.git("stash", "list").splitlines()), 1,
                         "the work the resume displaced must be recoverable, not discarded")

    def test_resume_works_from_an_unrelated_working_directory(self):
        doc = self.good_doc()
        self.move_the_tip_and_dirty_the_tree()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        r = self.resume_from(doc, cwd=elsewhere)
        self.assertEqual(r.returncode, 0, f"{r.stdout}{r.stderr}")
        self.assertEqual(self.git("rev-parse", "HEAD"), FIXTURE_SHA)

    def test_a_relative_cd_is_rejected_because_it_depends_on_the_caller(self):
        doc = self.good_doc().replace(f"cd {self.repo}", "cd ..")
        r = self.check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn("RESUME_PATH_NOT_ABSOLUTE", r.stdout)

    def test_a_path_with_an_escaped_space_is_not_a_false_unreachable(self):
        spaced = self.root / "my repo"
        (spaced / "notes").mkdir(parents=True)
        self.git("init", "-q", repo=spaced)
        (spaced / "f").write_text("f")
        self.git("add", "-A", repo=spaced)
        self.git("commit", "-q", "-m", "c", repo=spaced)
        sha = self.git("rev-parse", "HEAD", repo=spaced)
        doc = (self.good_doc().replace(str(self.repo), str(spaced).replace(" ", "\\ "))
               .replace(FIXTURE_SHA, sha)
               .replace(f"uncommitted: notes/{PATCH_NAME}", "uncommitted: none")
               .replace(f"git apply notes/{PATCH_NAME}\n", ""))
        p = spaced / "notes" / "h.md"
        p.write_text(doc)
        r = run_validator(p, env=self.env)
        self.assertNotIn("UNREACHABLE_REPO", r.stdout, r.stdout)

    def test_a_branch_only_resume_command_is_rejected(self):
        r = self.check(self.good_doc().replace(f"git checkout -B resume/lease-expiry {FIXTURE_SHA}",
                                               f"git checkout {FIXTURE_BRANCH}"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("RESUME_MISSING_SHA", r.stdout)

    def test_merely_mentioning_the_sha_is_not_checking_it_out(self):
        r = self.check(self.good_doc().replace(f"git checkout -B resume/lease-expiry {FIXTURE_SHA}",
                                               f"echo {FIXTURE_SHA}"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("RESUME_DOES_NOT_CHECKOUT", r.stdout)

    def test_branch_recorded_as_the_literal_HEAD_is_rejected(self):
        r = self.check(self.good_doc().replace(f"branch: {FIXTURE_BRANCH}", "branch: HEAD"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("BRANCH_IS_HEAD", r.stdout)


class MinimalModeTest(TempRepoCase):
    """B7: the emergency fallback must produce a document that actually passes."""

    def minimal_doc(self):
        state = sections_of(self.good_doc())["## State"]
        resume = sections_of(self.good_doc())["## Resume command"]
        return (f"# 2026-08-25 handoff: lease-expiry\n\n## State\n{state}\n"
                f"\n## Resume command\n{resume}\n")

    def test_the_two_section_fallback_passes_in_minimal_mode(self):
        r = self.check(self.minimal_doc(), minimal=True)
        self.assertEqual(r.returncode, 0,
                         f"the fallback this skill prescribes must validate:\n{r.stdout}")

    def test_minimal_mode_lists_the_remaining_sections_as_work_not_as_rejects(self):
        r = self.check(self.minimal_doc(), minimal=True)
        self.assertNotIn("REJECT", r.stdout)
        for heading in ("## Broken", "## Dead ends", "## Next"):
            self.assertIn(heading, r.stderr)

    def test_minimal_mode_still_polices_the_two_sections_it_judges(self):
        doc = self.minimal_doc().replace(f"commit: {FIXTURE_SHA}", "commit: " + "deadbeef" * 5)
        r = self.check(doc, minimal=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("UNKNOWN_COMMIT", r.stdout)

    def test_the_same_document_is_rejected_in_full_mode(self):
        r = self.check(self.minimal_doc())
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING_SECTION", r.stdout)


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

    def test_a_bare_ellipsis_line_is_rejected(self):
        self.assert_rejected_with(replace_section(
            self.good_doc(), "## Broken",
            "- t\n\n```\nTraceback:\n...\nAssertionError\n```\n\nrepro: python3 -m pytest -q"),
            "TRUNCATED_OUTPUT")

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
            "## Mirror\n\nbranch: <a second branch line>\n\n## Done and verified\n\n- <what changed>."))
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
        m = re.search(r"^name: *(\S+)", self.fm, re.MULTILINE)
        self.assertEqual(m.group(1), SKILL_DIR.name)

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

    def test_the_minimal_fallback_comes_before_the_rationale(self):
        lines = self.text.splitlines()
        fallback = next(i for i, l in enumerate(lines)
                        if l.startswith("## If you have almost no context"))
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
