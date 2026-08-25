#!/usr/bin/env python3
"""Tests for the `destructive-op-preflight` seed skill.

No mocks. Every test builds a real git repository with real `git` subprocesses, runs the
commands the SKILL.md actually prints, and reads the results back off disk. The point is
that this suite fails if the skill's prescribed commands are wrong, not merely if its
prose changes.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "destructive-op-preflight"
SKILL = SKILL_DIR / "SKILL.md"
MAKE_FIXTURE = REPO / "tests" / "fixtures" / "destructive-op-preflight" / "make-fixture.sh"

# The only frontmatter keys that validate outside Claude Code. Anything else is a hard
# error for a consumer of the Agent Skills spec.
PORTABLE_KEYS = {
    "allowed-tools", "compatibility", "description", "license", "metadata", "name",
}
MAX_FRONTMATTER_CHARS = 1024
MAX_DESCRIPTION_CHARS = 500
MAX_BODY_LINES = 500

# The sentinel that lives only in the untracked file. If this string turns up in a git
# object, the file was recoverable after all.
SENTINEL = "PRECIOUS PLAN"
DOOMED = "NOTES-DO-NOT-LOSE.md"

MIN_PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

# Commands that can destroy work. A fence tagged `destructive` is never executed, so it
# has to earn the tag: at least one line must match this.
DESTRUCTIVE = re.compile(
    r"(reset\s+--hard|checkout\s+--\s|restore\s+--(staged|worktree)|clean\s+-[a-zA-Z]*f"
    r"|stash\s+drop|push\s+.*--force|\brm\s+-[a-zA-Z]*r|force-reset|drop\s+(table|database)"
    r"|truncate|db:reset|db:drop|migrate\s+reset)"
)
# Recovery moves may appear beside a destructive command to show the correct pairing.
RECOVERY = re.compile(r"(git stash push|git stash pop|git branch |cp -a |pg_dump|mysqldump)")


def read_skill():
    return SKILL.read_text(encoding="utf-8")


def split_frontmatter(text):
    """Return (frontmatter_text, body_text). Raises if the delimiters are missing."""
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md must open with a '---' frontmatter delimiter")
    end = text.index("\n---\n", 3)
    return text[4:end + 1], text[end + len("\n---\n"):]


def parse_frontmatter(fm_text):
    """Minimal top-level `key: value` parser. Stdlib only, no PyYAML dependency."""
    fields = {}
    key = None
    for line in fm_text.splitlines():
        m = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s?(.*)$", line)
        if m:
            key = m.group(1)
            fields[key] = m.group(2).strip()
        elif line.startswith((" ", "\t")) and key:
            fields[key] += " " + line.strip()
        elif line.strip():
            raise AssertionError("unparseable frontmatter line: %r" % line)
    return fields


def fences(text):
    """Yield (tag, [command lines]) for every ```bash fence in the document."""
    for m in re.finditer(r"^```bash([^\n]*)\n(.*?)^```", text, re.S | re.M):
        tag = m.group(1).strip()
        lines = [ln for ln in m.group(2).splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        yield tag, lines


def claimed_exit(line):
    """A trailing `# exit: N` annotation is the skill's claim; absent it, the claim is 0."""
    m = re.search(r"#\s*exit:\s*(\d+)\s*$", line)
    return (int(m.group(1)), line[:m.start()].rstrip()) if m else (0, line)


class SeedSkillFixture(unittest.TestCase):
    """Base class: a real repo, a temp HOME, and no ambient git config."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # A temp HOME means the developer's own ~/.gitconfig cannot influence a result,
        # and nothing destructive can escape the temp tree.
        self.home = self.root / "home"
        self.home.mkdir()
        (self.home / ".gitconfig").write_text(
            "[user]\n\tname = fixture\n\temail = fixture@example.invalid\n"
            "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n"
            "[protocol \"file\"]\n\tallow = always\n",
            encoding="utf-8",
        )
        self.env = {"PATH": MIN_PATH, "HOME": str(self.home), "LC_ALL": "C"}
        self.fixture_seq = 0

    def tearDown(self):
        self.tmp.cleanup()

    def make_fixture(self):
        """Build a fresh copy of the burned-repo fixture. Returns the working clone."""
        self.fixture_seq += 1
        target = self.root / ("fx%d" % self.fixture_seq)
        r = subprocess.run([str(MAKE_FIXTURE), str(target)],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        repo = target / "repo"
        self.assertTrue((repo / DOOMED).is_file(), "fixture must start with the doomed file")
        # Everything destructive below runs inside the temp tree, never the real repo.
        self.assertTrue(str(repo).startswith(str(self.root)))
        return repo

    def sh(self, cmd, cwd):
        return subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True,
                              text=True, env=self.env)

    def git(self, repo, *args):
        r = self.sh("git " + " ".join(args), repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def sentinel_in_object_store(self, repo):
        """True if any git object anywhere in the repo holds the untracked file's bytes."""
        listing = self.sh(
            "git cat-file --batch-all-objects --batch-check='%(objectname) %(objecttype)'",
            repo)
        self.assertEqual(listing.returncode, 0, listing.stderr)
        for line in listing.stdout.splitlines():
            sha, _, kind = line.partition(" ")
            if kind.strip() != "blob":
                continue
            body = self.sh("git cat-file -p %s" % sha, repo)
            if SENTINEL in body.stdout:
                return True
        return False


class SkillDocumentTest(SeedSkillFixture):
    """Mechanical checks on the artifact itself."""

    def test_frontmatter_uses_only_portable_keys_within_limits(self):
        fm_text, _ = split_frontmatter(read_skill())
        self.assertLessEqual(len(fm_text), MAX_FRONTMATTER_CHARS,
                             "frontmatter is %d chars" % len(fm_text))
        fields = parse_frontmatter(fm_text)
        self.assertEqual(set(fields) - PORTABLE_KEYS, set(),
                         "non-portable frontmatter keys present")
        self.assertEqual(fields["name"], SKILL_DIR.name,
                         "frontmatter name must match the directory name")
        self.assertRegex(fields["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertLessEqual(len(fields["description"]), MAX_DESCRIPTION_CHARS,
                             "description is %d chars" % len(fields["description"]))
        # The description is a trigger clause with its negative scope in the same sentence.
        self.assertIn("Use when", fields["description"])
        self.assertIn("Do NOT use for", fields["description"])

    def test_body_stays_under_the_line_ceiling(self):
        _, body = split_frontmatter(read_skill())
        n = len(body.strip().splitlines())
        self.assertLessEqual(n, MAX_BODY_LINES, "body is %d lines" % n)

    def test_iron_law_is_stated_exactly_once(self):
        body = split_frontmatter(read_skill())[1]
        self.assertEqual(body.count("NO DESTRUCTIVE COMMAND WITHOUT"), 1)

    def test_bundled_references_exist_and_are_linked(self):
        body = split_frontmatter(read_skill())[1]
        linked = set(re.findall(r"\]\((references/[^)]+)\)", body))
        self.assertTrue(linked, "long reference material must be bundled, not inlined")
        for rel in linked:
            self.assertTrue((SKILL_DIR / rel).is_file(), "missing bundled file: %s" % rel)
        on_disk = {"references/" + p.name for p in (SKILL_DIR / "references").iterdir()}
        self.assertEqual(on_disk, linked, "every bundled reference must be linked")

    def test_no_em_dashes_anywhere_in_the_skill(self):
        for path in sorted(SKILL_DIR.rglob("*.md")):
            self.assertNotIn("—", path.read_text(encoding="utf-8"),
                             "em-dash in %s" % path)


class TriggerPrecisionTest(SeedSkillFixture):
    """The description has to discriminate, and the skill has to say how."""

    def prompts(self):
        body = split_frontmatter(read_skill())[1]
        m = re.search(r"^## Trigger precision\n(.*?)^## ", body, re.S | re.M)
        self.assertIsNotNone(m, "SKILL.md must carry a '## Trigger precision' section")
        section = m.group(1)
        must = re.search(r"MUST fire:\n((?:\d+\. .*\n)+)", section)
        must_not = re.search(r"MUST NOT fire:\n((?:\d+\. .*\n)+)", section)
        self.assertIsNotNone(must)
        self.assertIsNotNone(must_not)
        grab = lambda blk: [re.sub(r'^\d+\.\s*"?|"?$', "", ln).strip()
                            for ln in blk.strip().splitlines()]
        return grab(must.group(1)), grab(must_not.group(1))

    def test_three_prompts_each_way_and_disjoint(self):
        fire, no_fire = self.prompts()
        self.assertEqual(len(fire), 3, fire)
        self.assertEqual(len(no_fire), 3, no_fire)
        self.assertEqual(set(fire) & set(no_fire), set())

    def test_must_not_prompts_avoid_every_destructive_word_the_description_names(self):
        """A must-not prompt containing the description's own trigger vocabulary would
        prove nothing: the discrimination has to hold on prompts that share no keyword."""
        description = parse_frontmatter(split_frontmatter(read_skill())[0])["description"]
        vocabulary = re.findall(
            r"(reset --hard|checkout --|restore --worktree|git clean|stash drop|--force"
            r"|rm -rf|truncate|rollback|\bdrop\b|\breset\b|\bdestroy\b)",
            description.lower())
        self.assertGreaterEqual(len(set(vocabulary)), 5,
                                "the description must name the destructive commands: %s"
                                % sorted(set(vocabulary)))
        _, no_fire = self.prompts()
        for prompt in no_fire:
            for word in set(vocabulary):
                self.assertNotIn(word, prompt.lower(),
                                 "must-not prompt %r contains trigger word %r"
                                 % (prompt, word))

    def test_must_not_prompts_land_inside_the_declared_negative_scope(self):
        description = parse_frontmatter(split_frontmatter(read_skill())[0])["description"]
        negative = description.lower().split("do not use for", 1)[1]
        excluded = {w for w in re.findall(r"[a-z]{4,}", negative)}
        _, no_fire = self.prompts()
        for prompt in no_fire:
            stems = {w[:6] for w in re.findall(r"[a-z]{4,}", prompt.lower())}
            hit = {e for e in excluded if e[:6] in stems}
            self.assertTrue(hit, "must-not prompt %r matches nothing the description "
                                 "explicitly excludes" % prompt)


class LossDemonstrationTest(SeedSkillFixture):
    """The loss the skill exists to prevent, reproduced for real, then prevented."""

    def test_naive_sequence_destroys_the_untracked_file_beyond_recovery(self):
        repo = self.make_fixture()
        original = (repo / DOOMED).read_bytes()

        # Exactly what #34746 reported: sync to origin, then tidy up.
        r = self.sh("git reset --hard origin/main && git clean -fd", repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        self.assertFalse((repo / DOOMED).exists(), "the naive sequence should destroy it")
        self.assertNotIn(SENTINEL, self.git(repo, "reflog"))
        self.assertEqual(self.git(repo, "stash", "list").strip(), "")
        # The decisive assertion: no object anywhere in the repository holds the bytes,
        # so no reflog walk, `fsck --lost-found`, or `fsck --unreachable` can return it.
        self.assertFalse(self.sentinel_in_object_store(repo),
                         "the untracked file must have no git object behind it")
        self.assertNotEqual(original, b"")

    def test_prescribed_recovery_first_sequence_preserves_the_same_file(self):
        """Runs the sequence read out of the SKILL.md itself, not a copy of it here, so a
        wrong prescription in the artifact fails this test."""
        repo = self.make_fixture()
        original = (repo / DOOMED).read_bytes()

        blocks = [lines for tag, lines in fences(read_skill()) if tag == "destructive"]
        self.assertEqual(len(blocks), 1, "expected exactly one prescribed sequence")
        prescribed = [claimed_exit(ln)[1] for ln in blocks[0]]
        self.assertTrue(any("reset --hard" in ln for ln in prescribed))

        for cmd in prescribed:
            if "reset --hard" in cmd:
                # Proof step, before the irreversible line: the stash has to be shown to
                # hold the doomed path.
                self.assertIn(DOOMED,
                              self.git(repo, "stash", "show", "--include-untracked",
                                       "--stat", "'stash@{0}'"))
            r = self.sh(cmd, repo)
            self.assertEqual(r.returncode, 0, "%r failed:\n%s" % (cmd, r.stdout + r.stderr))

        self.assertTrue((repo / DOOMED).is_file(), "the recovery-first sequence must save it")
        self.assertEqual((repo / DOOMED).read_bytes(), original, "byte-identical or bust")
        # The unpushed commit is not in the stash; the backup branch is what returns it.
        backups = self.git(repo, "branch", "--list", "'backup/*'").split()
        self.assertTrue(backups, "the sequence must leave a named backup of the commits")
        self.assertIn("def feature",
                      self.git(repo, "show", "%s:src/feature.py" % backups[0]))
        # And `--index` preserves the staged/unstaged split the manifest recorded.
        status = self.git(repo, "status", "--porcelain")
        self.assertIn("M  src/app.py", status)
        self.assertIn(" M README.md", status)

    def test_checkout_dash_dash_does_not_revert_a_staged_mutation(self):
        """The trap the SKILL.md names. If git ever changes this, the skill is wrong."""
        repo = self.make_fixture()
        self.assertIn('app v2', (repo / "src/app.py").read_text())

        self.git(repo, "checkout", "--", "src/app.py")
        self.assertIn('app v2', (repo / "src/app.py").read_text(),
                      "checkout -- restores from the index, so the staged content stays")

        self.git(repo, "restore", "--staged", "--worktree", "src/app.py")
        self.assertIn('app v1', (repo / "src/app.py").read_text(),
                      "restore --staged --worktree is what actually reverts to HEAD")
        self.assertEqual(self.git(repo, "diff", "--cached", "--name-only").strip(), "")

    def test_clean_fxd_on_a_directory_removes_the_directory(self):
        """`-- build/` reads like a scope limit. It takes .env.local with it."""
        repo = self.make_fixture()
        self.assertTrue((repo / "build" / ".env.local").is_file())

        preview = self.git(repo, "clean", "-ndx", "--", "build/")
        self.assertIn("Would remove build/", preview)

        self.git(repo, "clean", "-fdxq", "--", "build/")
        self.assertFalse((repo / "build").exists())
        self.assertFalse((repo / "build" / ".env.local").exists())


class SkillCommandsExecuteTest(SeedSkillFixture):
    """Unverified claims in a skill are defects. Run the safe ones and check the status."""

    def test_every_bash_fence_is_classified(self):
        tags = [tag for tag, _ in fences(read_skill())]
        self.assertTrue(tags, "SKILL.md must contain runnable commands")
        for tag in tags:
            self.assertIn(tag, {"safe", "safe-seq", "destructive"},
                          "untagged bash fence: %r" % tag)

    def test_safe_commands_run_with_the_exit_status_the_skill_claims(self):
        ran = 0
        for tag, lines in fences(read_skill()):
            if tag != "safe":
                continue
            for line in lines:
                want, cmd = claimed_exit(line)
                repo = self.make_fixture()   # a clean fixture per command
                r = self.sh(cmd, repo)
                self.assertEqual(r.returncode, want,
                                 "%r exited %d, skill claims %d\n%s"
                                 % (cmd, r.returncode, want, r.stdout + r.stderr))
                ran += 1
        self.assertGreaterEqual(ran, 12, "only %d safe commands verified" % ran)

    def test_safe_sequences_run_end_to_end(self):
        ran = 0
        for tag, lines in fences(read_skill()):
            if tag != "safe-seq":
                continue
            repo = self.make_fixture()
            r = self.sh(" && ".join(claimed_exit(ln)[1] for ln in lines), repo)
            self.assertEqual(r.returncode, 0,
                             "safe-seq failed:\n%s" % (r.stdout + r.stderr))
            # A proof-of-recovery sequence has to actually name the doomed file.
            if "stash show" in r.stdout or "stash show" in " ".join(lines):
                self.assertIn(DOOMED, r.stdout)
            self.assertTrue((repo / DOOMED).is_file(),
                            "a safe sequence must leave the untracked file in place")
            ran += 1
        self.assertGreaterEqual(ran, 1)

    def test_destructive_fences_earn_their_tag_and_hide_nothing(self):
        seen = 0
        for tag, lines in fences(read_skill()):
            if tag != "destructive":
                continue
            seen += 1
            self.assertTrue(any(DESTRUCTIVE.search(ln) for ln in lines),
                            "a destructive fence must contain a destructive command")
            for line in lines:
                self.assertTrue(DESTRUCTIVE.search(line) or RECOVERY.search(line),
                                "%r is neither destructive nor a recovery move, so it "
                                "belongs in a `safe` fence where it gets executed" % line)
        self.assertGreaterEqual(seen, 1)


if __name__ == "__main__":
    unittest.main()
