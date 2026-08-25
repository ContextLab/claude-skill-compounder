#!/usr/bin/env python3
"""Tests for the `destructive-op-preflight` seed skill.

No mocks. Every test builds a real git repository with real `git` subprocesses, runs the
commands the SKILL.md actually prints, and reads the results back off disk. The point is
that this suite fails if the skill's prescribed commands are wrong, not merely if its
prose changes.

Red-team round 1 returned five blocking findings; `RedTeamRound1Test` pins each one, named
B1 through B5, so a regression to the pre-fix wording fails here.

`shell=True` is deliberate: the artifact under test prints shell one-liners with pipes,
`&&`, redirection and command substitution, and running them any other way would not be
running what the skill tells a session to run. The command text comes from a file in this
repository, never from user input, and every destructive path is confined to a
`TemporaryDirectory` with `HOME` pointed inside it.
"""

import re
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
IGNORED_SECRET = "build/.env.local"

MIN_PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"


# Commands that can destroy work. A `destructive` fence is never executed by the command
# sweep, so it has to earn the tag: at least one line must match this.
DESTRUCTIVE = re.compile(
    r"(reset\s+--hard|checkout\s+(-f|--\s)|restore\s+--(staged|worktree)|clean\s+-[a-zA-Z]*f"
    r"|stash\s+drop|branch\s+-D|reflog\s+expire|gc\s+--prune|filter-repo|rebase"
    r"|push\s+.*--force|\brm\s+-[a-zA-Z]*r|force-reset|drop\s+(table|database)"
    r"|truncate|db:reset|db:drop|migrate\s+reset)"
)
# Recovery moves may appear beside a destructive command to show the correct pairing.
RECOVERY = re.compile(r"(git stash push|git stash pop|git branch |cp -a |pg_dump|mysqldump)")
# Guard machinery: the exit-status and ref checks that make the sequence safe. These are
# inspections, so they may sit in a destructive fence without being executed separately.
GUARD = re.compile(r"(git rev-parse|git stash show|git stash list|git status)")
# Anything that runs a program. Used to prove nothing unverified hides in a script fence.
INVOCATION = re.compile(r"^\s*(git|rm|cp|mv|find|sqlite3|psql|mysql|npm|npx)\b")


def read_skill():
    return SKILL.read_text(encoding="utf-8")


def split_frontmatter(text):
    """Return (frontmatter_text, body_text). Raises if the delimiters are missing."""
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md must open with a '---' frontmatter delimiter")
    end = text.index("\n---\n", 3)
    return text[4:end + 1], text[end + len("\n---\n"):]


def parse_frontmatter(fm_text):
    """Minimal top-level `key: value` parser. Stdlib only, no PyYAML dependency.

    Mirrors what `claude plugin validate --strict` does to the YAML: a value holding an
    unquoted `: ` breaks the parse, and the skill then loads with empty metadata and never
    triggers, so quoting is checked rather than assumed.
    """
    fields = {}
    key = None
    for line in fm_text.splitlines():
        m = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s?(.*)$", line)
        if m:
            key = m.group(1)
            raw = m.group(2).strip()
            if ": " in raw and not (raw.startswith(('"', "'")) and raw[-1] == raw[0]):
                raise AssertionError(
                    "frontmatter value for %r contains an unquoted ': ', which makes the "
                    "whole YAML block fail to parse: %r" % (key, raw))
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
                raw = raw[1:-1]
            fields[key] = raw
        elif line.startswith((" ", "\t")) and key:
            fields[key] += " " + line.strip()
        elif line.strip():
            raise AssertionError("unparseable frontmatter line: %r" % line)
    return fields


def fences(text):
    """Yield (tag, command lines, raw block) for every ```bash fence in the document."""
    for m in re.finditer(r"^```bash([^\n]*)\n(.*?)^```", text, re.S | re.M):
        raw = m.group(2)
        lines = [ln for ln in raw.splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        yield m.group(1).strip(), lines, raw


def claimed_exit(line):
    """A trailing `# exit: N` annotation is the skill's claim; absent it, the claim is 0."""
    m = re.search(r"#\s*exit:\s*(\d+)\s*$", line)
    return (int(m.group(1)), line[:m.start()].rstrip()) if m else (0, line)


def prescribed_script():
    """The Phase 5 sequence, read out of the artifact rather than copied into the test."""
    blocks = [raw for tag, _, raw in fences(read_skill()) if tag == "destructive"]
    if len(blocks) != 1:
        raise AssertionError("expected exactly one prescribed sequence, found %d"
                             % len(blocks))
    return blocks[0]


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
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()
        self.env = {"PATH": MIN_PATH, "HOME": str(self.home), "LC_ALL": "C",
                    "TMPDIR": str(self.scratch)}
        self.fixture_seq = 0

    def tearDown(self):
        self.tmp.cleanup()


    def make_fixture(self, mode="standard"):
        """Build a fresh copy of a burned-repo fixture. Returns the working clone."""
        self.fixture_seq += 1
        target = self.root / ("fx%d" % self.fixture_seq)
        r = subprocess.run([str(MAKE_FIXTURE), str(target), mode],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        repo = target / "repo"
        # Everything destructive below runs inside the temp tree, never the real repo.
        self.assertTrue(str(repo).startswith(str(self.root)))
        return repo

    def sh(self, cmd, cwd):
        return subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True,
                              text=True, env=self.env)

    def bash(self, script, cwd, **extra_env):
        env = dict(self.env)
        env.update(extra_env)
        return subprocess.run(["bash", "-c", script], cwd=str(cwd), capture_output=True,
                              text=True, env=env)

    def run_prescribed(self, repo, target="origin/main"):
        """Execute the Phase 5 script exactly as the artifact prints it."""
        return self.bash(prescribed_script(), repo, TARGET=target)

    def git(self, repo, *args):
        r = self.sh("git " + " ".join(args), repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def head(self, repo):
        return self.git(repo, "rev-parse", "HEAD").strip()

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
            if SENTINEL in self.sh("git cat-file -p %s" % sha, repo).stdout:
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

    def test_description_is_quoted_so_strict_yaml_validation_passes(self):
        """An unquoted `: ` empties the metadata and the skill silently never fires."""
        raw = [ln for ln in split_frontmatter(read_skill())[0].splitlines()
               if ln.startswith("description:")]
        self.assertEqual(len(raw), 1)
        value = raw[0][len("description:"):].strip()
        self.assertIn(": ", value, "this description does contain a colon-space")
        self.assertTrue(value.startswith('"') and value.endswith('"'),
                        "a description containing ': ' must be quoted")

    def test_description_describes_the_situation_not_a_command_vocabulary(self):
        """A description that is a list of command tokens both over-fires on dry runs and
        under-fires on paraphrase. It must name the irreversible outcome instead."""
        d = parse_frontmatter(split_frontmatter(read_skill())[0])["description"]
        tokens = re.findall(
            r"(--hard|-rf|--force\b|git clean|stash drop|branch -D|reflog expire"
            r"|gc --prune|filter-repo|\brebase\b|checkout|truncate|drop table)", d.lower())
        self.assertLessEqual(len(set(tokens)), 1,
                             "description reads as a command list: %s" % sorted(set(tokens)))
        for phrase in ("uncommitted", "untracked", "never pushed", "reflog"):
            self.assertIn(phrase, d.lower(), "description omits %r" % phrase)

    def test_datastore_scope_is_cut_from_the_skill_body(self):
        """Six of eight engines were self-declared unverified. Unverified advice about
        wiping a production database is the worst place to keep a defect."""
        body = split_frontmatter(read_skill())[1]
        self.assertNotIn("## Datastores", body)
        d = parse_frontmatter(split_frontmatter(read_skill())[0])["description"].lower()
        for word in ("database", "migration", "truncate", "rollback", "sql"):
            self.assertNotIn(word, d, "description still claims database scope via %r" % word)
        for engine in ("postgres", "mysql", "prisma", "alembic", "django"):
            self.assertNotIn(engine, body.lower(),
                             "%s advice must not live in the skill body" % engine)
        ref = (SKILL_DIR / "references" / "sqlite-preflight.md").read_text(encoding="utf-8")
        self.assertIn("the one datastore whose procedure was executed end to end", ref)

    def test_body_stays_under_the_line_ceiling(self):
        _, body = split_frontmatter(read_skill())
        n = len(body.strip().splitlines())
        self.assertLessEqual(n, MAX_BODY_LINES, "body is %d lines" % n)

    def test_iron_law_is_stated_exactly_once_and_demands_a_measured_residue(self):
        body = split_frontmatter(read_skill())[1]
        self.assertEqual(body.count("NO DESTRUCTIVE COMMAND UNTIL"), 1)
        law = re.search(r"```text\n(NO DESTRUCTIVE COMMAND UNTIL.*?)```", body, re.S)
        self.assertIn("PROVED EMPTY", law.group(1),
                      "the law must demand a measured residue, not a checked-off list")

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

    def test_trigger_does_not_depend_on_sharing_words_with_the_prompt(self):
        """A keyword-matching description misses the paraphrase that carries the real
        risk. At least one must-fire prompt has to work with no vocabulary in common."""
        description = parse_frontmatter(split_frontmatter(read_skill())[0])["description"]
        desc_words = set(re.findall(r"[a-z]{4,}", description.lower()))
        fire, _ = self.prompts()
        overlaps = []
        for prompt in fire:
            shared = set(re.findall(r"[a-z]{4,}", prompt.lower())) & desc_words
            overlaps.append((prompt, shared))
        self.assertTrue(any(not shared for _, shared in overlaps),
                        "every must-fire prompt shares vocabulary with the description, so "
                        "the trigger is keyword matching: %s" % overlaps)

    def test_must_not_prompts_include_the_adversarial_near_misses(self):
        """A dry run and a reflog-reversible history edit both name commands this skill
        cares about, and both must be refused."""
        _, no_fire = self.prompts()
        joined = " ".join(no_fire).lower()
        self.assertIn("-nd", joined, "a dry-run prompt must be in the must-not set")
        self.assertIn("rebase", joined,
                      "a reflog-reversible rebase must be in the must-not set")

    def test_must_not_prompts_land_inside_the_declared_negative_scope(self):
        description = parse_frontmatter(split_frontmatter(read_skill())[0])["description"]
        negative = description.lower().split("do not use for", 1)[1]
        excluded = set(re.findall(r"[a-z]{4,}", negative))
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

    def test_prescribed_sequence_preserves_the_untracked_and_the_ignored_file(self):
        """Runs the script read out of the SKILL.md itself, not a copy of it here, so a
        wrong prescription in the artifact fails this test."""
        repo = self.make_fixture()
        original = (repo / DOOMED).read_bytes()
        secret = (repo / IGNORED_SECRET).read_bytes()

        r = self.run_prescribed(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        self.assertTrue((repo / DOOMED).is_file(), "the recovery-first sequence must save it")
        self.assertEqual((repo / DOOMED).read_bytes(), original, "byte-identical or bust")
        # B3: the ignored file has to come back too, which `-u` alone would not do.
        self.assertTrue((repo / IGNORED_SECRET).is_file(),
                        "the ignored credential must survive as well")
        self.assertEqual((repo / IGNORED_SECRET).read_bytes(), secret)
        # The unpushed commit is not in the stash; the backup branch is what returns it.
        backups = self.git(repo, "branch", "--list", "'backup-*'").split()
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
        self.assertIn("app v2", (repo / "src/app.py").read_text())

        self.git(repo, "checkout", "--", "src/app.py")
        self.assertIn("app v2", (repo / "src/app.py").read_text(),
                      "checkout -- restores from the index, so the staged content stays")

        self.git(repo, "restore", "--staged", "--worktree", "src/app.py")
        self.assertIn("app v1", (repo / "src/app.py").read_text(),
                      "restore --staged --worktree is what actually reverts to HEAD")
        self.assertEqual(self.git(repo, "diff", "--cached", "--name-only").strip(), "")

    def test_clean_fxd_on_a_directory_removes_the_directory(self):
        """`-- build/` reads like a scope limit. It takes .env.local with it."""
        repo = self.make_fixture()
        self.assertTrue((repo / IGNORED_SECRET).is_file())

        self.assertIn("Would remove build/", self.git(repo, "clean", "-ndx", "--", "build/"))
        self.git(repo, "clean", "-fdxq", "--", "build/")
        self.assertFalse((repo / "build").exists())


class RedTeamRound1Test(SeedSkillFixture):
    """One test per blocking finding from the first cold-agent review."""

    def test_b1_prescribed_script_aborts_when_the_stash_fails(self):
        """Mid-merge, `git stash push` exits 1 and stashes nothing. The unchained draft
        ran `reset --hard` on the next line anyway, with no recovery in existence."""
        repo = self.make_fixture("merge-conflict")
        before_head = self.head(repo)

        probe = self.sh("git stash push --all -m probe", repo)
        self.assertNotEqual(probe.returncode, 0, "fixture must make `stash push` fail")
        self.assertEqual(self.git(repo, "stash", "list").strip(), "")

        r = self.run_prescribed(repo)
        self.assertNotEqual(r.returncode, 0, "the script must abort, not continue")
        self.assertIn("ABORTED", r.stdout + r.stderr)
        self.assertEqual(self.head(repo), before_head, "reset --hard must not have run")
        self.assertTrue((repo / DOOMED).is_file())

    def test_b2_prescribed_script_never_pops_a_stash_it_did_not_create(self):
        """On a clean tree `git stash push` prints `No local changes to save` and exits 0.
        An unguarded pop then injects a stranger's stash and destroys it."""
        repo = self.make_fixture("stranger-stash")
        stash_before = self.git(repo, "stash", "list").strip()
        self.assertIn("old-unrelated-work", stash_before)
        readme_before = (repo / "README.md").read_bytes()

        r = self.run_prescribed(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        self.assertEqual((repo / "README.md").read_bytes(), readme_before,
                         "the stranger's stash must not be injected into the tree")
        self.assertEqual(self.git(repo, "stash", "list").strip(), stash_before,
                         "the stranger's stash must still be on the stack")

    def test_b3_include_untracked_misses_ignored_files_and_all_does_not(self):
        """The gap that made the first draft's manifest wrong: `-u` leaves `!!` on disk."""
        repo = self.make_fixture()
        self.git(repo, "stash", "push", "--include-untracked", "-q", "-m", "u")
        self.assertTrue((repo / IGNORED_SECRET).is_file(),
                        "`-u` leaves the ignored credential on disk, unstashed")
        self.git(repo, "stash", "pop", "-q")

        self.git(repo, "stash", "push", "--all", "-q", "-m", "a")
        self.assertFalse((repo / IGNORED_SECRET).exists(),
                         "`--all` takes the ignored file into the stash")
        self.git(repo, "stash", "pop", "-q")
        self.assertTrue((repo / IGNORED_SECRET).is_file())

        self.assertIn("git stash push --all", prescribed_script())

    def test_b5_prescribed_enumeration_lists_every_path_not_a_rollup(self):
        """50 untracked files under one directory. `clean -nd` says one line."""
        repo = self.make_fixture("scaffold50")

        rollup = self.git(repo, "clean", "-nd")
        self.assertEqual(len(rollup.strip().splitlines()), 1,
                         "this is the defect: a directory rollup")

        enumerated = self.sh(
            "git status --porcelain -z -uall --ignored | tr '\\0' '\\n'", repo)
        paths = [ln[3:] for ln in enumerated.stdout.strip().splitlines()]
        self.assertEqual(len(paths), 50, "the prescribed enumeration must list each file")
        self.assertIn("scaffold/f37.txt", paths)

        body = split_frontmatter(read_skill())[1]
        phase2 = re.search(r"^## Phase 2:.*?^## Phase 3:", body, re.S | re.M)
        self.assertIsNotNone(phase2, "SKILL.md must have a Phase 2 section")
        status_lines = [ln for ln in phase2.group(0).splitlines()
                        if "status --porcelain" in ln]
        self.assertTrue(status_lines, "Phase 2 must enumerate with git status")
        for ln in status_lines:
            for flag in ("-uall", "--ignored", "-z"):
                self.assertIn(flag, ln, "Phase 2 command %r lacks %s" % (ln, flag))


class RedTeamRound2Test(SeedSkillFixture):
    """One test per blocking finding from the second cold-agent review."""

    def test_b1_staged_rename_with_an_edit_is_enumerated_and_covered(self):
        """`RM` matches no hand-written list of dirty codes, so the old gate reported an
        empty blast radius while two hours of work sat in the renamed file."""
        repo = self.make_fixture("staged-rename")
        work = (repo / "FINAL-REPORT.md").read_bytes()
        self.assertIn(b"TWO HOURS OF WORK", work)

        # The defect, reproduced: the retired code list matches nothing here.
        codes = self.sh("git status --porcelain -uall --ignored "
                        "| grep -E '^(\\?\\?|!!| M| D|MM|AM)' | cut -c4-", repo)
        self.assertNotIn("FINAL-REPORT.md", codes.stdout,
                         "this is the finding: the RM row contributes nothing to the "
                         "retired at-risk list, so the file holding the work is invisible")
        self.assertNotIn("README.md", codes.stdout)

        # The prescribed enumeration must show it, unquoted and split across two lines.
        enumerated = self.sh(
            "git status --porcelain -z -uall --ignored | tr '\\0' '\\n'", repo)
        self.assertIn("FINAL-REPORT.md", enumerated.stdout, "the new path must appear")
        self.assertIn("README.md", enumerated.stdout, "the old path must appear too")
        self.assertNotIn("->", enumerated.stdout, "-z must not emit the rename arrow")

        # And the prescribed script must bring the work back.
        r = self.run_prescribed(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((repo / "FINAL-REPORT.md").is_file(),
                        "the renamed file holding the work must survive")
        self.assertEqual((repo / "FINAL-REPORT.md").read_bytes(), work)

    def test_b1_residue_gate_catches_a_path_the_stash_did_not_take(self):
        """Subtraction rather than a code list: whatever the stash missed is still on disk,
        whether or not anyone anticipated its status code."""
        repo = self.make_fixture()
        # `-u` deliberately under-covers: the ignored file stays behind.
        self.git(repo, "stash", "push", "--include-untracked", "-q", "-m", "weak")
        residue = self.sh("git status --porcelain -uall --ignored", repo).stdout
        self.assertIn(IGNORED_SECRET, residue, "the uncovered path must show as residue")
        gate = self.sh('test -z "$(git status --porcelain -uall --ignored)"', repo)
        self.assertNotEqual(gate.returncode, 0, "the residue gate must fail closed")
        self.git(repo, "stash", "pop", "-q")

        # The prescribed recovery leaves nothing behind, so the gate passes.
        self.git(repo, "stash", "push", "--all", "-q", "-m", "strong")
        gate = self.sh('test -z "$(git status --porcelain -uall --ignored)"', repo)
        self.assertEqual(gate.returncode, 0,
                         self.sh("git status --porcelain -uall --ignored", repo).stdout)

    def test_b1_submodule_only_change_fails_the_gate_closed(self):
        """`stash push --all` exits 0 creating no entry at all. The old ref comparison read
        that as `MINE=no` and ran the destructive command with zero recovery."""
        repo = self.make_fixture("submodule")
        self.assertIn(" M sub", self.git(repo, "status", "--porcelain"))

        before = self.sh("git rev-parse -q --verify refs/stash", repo).stdout.strip()
        self.git(repo, "stash", "push", "--all", "-q", "-m", "probe")
        after = self.sh("git rev-parse -q --verify refs/stash", repo).stdout.strip()
        self.assertEqual(before, after, "no stash entry is created for a submodule change")

        gate = self.sh('test -z "$(git status --porcelain -uall --ignored)"', repo)
        self.assertNotEqual(gate.returncode, 0, "the residue gate must fail closed")

        r = self.run_prescribed(repo)
        self.assertNotEqual(r.returncode, 0, "the script must refuse to continue")
        self.assertIn("not in the stash", r.stdout + r.stderr)

    def test_b2_gate_cannot_be_passed_by_an_empty_redirect(self):
        """The retired gate wrote its output through a redirect, so a failing `comm` still
        created an empty file and `test ! -s` reported success."""
        repo = self.make_fixture()
        old_gate = ('comm -23 "$TMPDIR"/missing-at-risk.txt "$TMPDIR"/missing-covered.txt '
                    '> "$TMPDIR"/uncovered.txt; test ! -s "$TMPDIR"/uncovered.txt')
        r = self.bash(old_gate, repo)
        self.assertEqual(r.returncode, 0,
                         "this is the finding: the retired gate passes on missing input")

        # The shipped gate takes no file input, so there is nothing to be missing.
        body = split_frontmatter(read_skill())[1]
        self.assertNotIn("comm -23", body, "the path-list gate must be gone")
        self.assertNotIn("at-risk.txt", body)
        self.assertIn("RESIDUE=$(git status --porcelain -uall --ignored)", body)
        self.assertIn('test -z "$RESIDUE"', body)

    def test_b3_concurrent_stash_does_not_redirect_the_pop(self):
        """Comparing the top of refs/stash proves the top changed, not that you made it."""
        repo = self.make_fixture()
        script = prescribed_script()
        self.assertIn("git stash list --format=", script,
                      "the script must resolve its own entry by message")
        self.assertNotIn("BEFORE=", script, "the retired ref comparison must be gone")

        # Our entry stays findable after another process pushes on top of it.
        stamp = "preflight-unique-marker-12345"
        self.git(repo, "stash", "push", "--all", "-q", "-m", stamp)
        self.sh("echo stranger >> README.md && git stash push -q -m other-process", repo)
        listing = self.git(repo, "stash", "list", "--format='%gd %gs'")
        ours = [ln for ln in listing.splitlines() if stamp in ln]
        self.assertEqual(len(ours), 1)
        self.assertIn("stash@{1}", ours[0], "ours shifted, and is still identifiable")

        self.git(repo, "stash", "pop", "--index", "stash@{1}")
        self.assertTrue((repo / DOOMED).is_file(), "we popped our own entry")
        self.assertIn("other-process", self.git(repo, "stash", "list"),
                      "the other process's stash is untouched")

    def test_b4_every_failure_after_the_stash_says_where_the_work_went(self):
        """An emptied tree plus a raw `set -e` exit leaves the user with no idea their work
        is recoverable. Two one-line triggers, both real."""
        for mode, target, why in (("standard", "origin/does-not-exist", "unresolvable target"),
                                  ("no-remote", "origin/main", "no remote at all")):
            repo = self.make_fixture(mode if mode != "standard" else "standard")
            r = self.run_prescribed(repo, target=target)
            self.assertNotEqual(r.returncode, 0, why)
            out = r.stdout + r.stderr
            self.assertIn("ABORTED", out, why)
            # Aborting before the stash keeps the tree intact, and says so.
            self.assertIn("No preflight stash exists", out, why)
            self.assertTrue((repo / DOOMED).is_file(),
                            "the tree must be untouched when we abort this early: %s" % why)

    def test_b4_branch_name_collision_no_longer_strands_the_tree(self):
        """A pre-existing ref named `backup` made `backup/preflight-...` fail with
        `cannot lock ref`, after the tree had already been emptied."""
        repo = self.make_fixture("backup-branch-exists")
        self.assertIn("backup", self.git(repo, "branch", "--list", "backup"))

        r = self.run_prescribed(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((repo / DOOMED).is_file())
        self.assertNotIn("backup/", prescribed_script(),
                         "a slashed backup name collides with a ref named `backup`")

    def test_b5_script_refuses_to_run_mid_rebase(self):
        """Stopped at a rebase `break` the index is clean, the stash succeeds, and
        `reset --hard` completes at rc=0 with the rebase still in progress."""
        repo = self.make_fixture("mid-rebase")
        gitdir = self.git(repo, "rev-parse", "--git-dir").strip()
        self.assertTrue((repo / gitdir / "rebase-merge").exists()
                        or (repo / gitdir / "rebase-apply").exists(),
                        "fixture must actually be mid-rebase")
        before_head = self.head(repo)

        r = self.run_prescribed(repo)
        self.assertNotEqual(r.returncode, 0, "the script must refuse")
        self.assertIn("operation is in progress", r.stdout + r.stderr)
        self.assertEqual(self.head(repo), before_head)
        self.assertTrue((repo / DOOMED).is_file())

    def test_b6_sqlite_census_rejects_the_false_proofs(self):
        """Errors go to stderr, so a naive count comparison compares two empty strings.

        Both the census function and the guard lines are lifted out of the reference, so
        deleting a guard from the artifact fails this test rather than passing on a copy
        kept here.
        """
        ref = (SKILL_DIR / "references" / "sqlite-preflight.md").read_text(encoding="utf-8")
        census = re.search(r"```bash\n(census\(\) \{.*?\n\})\n```", ref, re.S)
        self.assertIsNotNone(census, "the reference must define the census function")
        fn = census.group(1)

        procedure = re.search(r"## The full procedure\n+```bash\n(.*?)```", ref, re.S)
        self.assertIsNotNone(procedure, "the reference must carry the full procedure")
        guards = [ln for ln in procedure.group(1).splitlines()
                  if ln.startswith("test ") and ("$SRC" in ln or "$DST" in ln)]
        self.assertEqual(len(guards), 3,
                         "the procedure must guard on a non-empty source census, a "
                         "non-empty restored census, and a match; found %r" % guards)
        self.assertTrue(any('test -n "$SRC"' in g for g in guards),
                        "no non-empty source-census guard in the reference")
        self.assertTrue(any('test -n "$DST"' in g for g in guards),
                        "no non-empty restored-census guard in the reference")
        self.assertTrue(any('test "$SRC" = "$DST"' in g for g in guards),
                        "no census-comparison guard in the reference")
        self.assertIn("-bail", procedure.group(1))
        self.assertIn("test ! -e", procedure.group(1),
                      "the scratch database must be refused if it already exists")

        work = self.root / "sqlite"
        work.mkdir()
        self.assertEqual(self.bash(
            'sqlite3 app.db "create table users(a); insert into users values(1),(2);'
            ' create table accounts(b); insert into accounts values(9);"', work).returncode, 0)

        def check(setup):
            script = "\n".join([
                fn, setup,
                'SRC=$(census app.db | sort); DST=$(census rc.db | sort)',
                *guards,
                "echo VERIFIED"])
            return self.bash(script, work)

        # A zero-byte dump: both censuses come back empty and would compare equal.
        r = check('rm -f rc.db; : > d.sql; sqlite3 -bail rc.db < d.sql')
        self.assertNotEqual(r.returncode, 0, "an empty census must not read as success")
        self.assertNotIn("VERIFIED", r.stdout)

        # A dump of one table while another table has no backup at all.
        r = check('rm -f rc.db; sqlite3 app.db ".dump users" > d.sql; '
                  'sqlite3 -bail rc.db < d.sql')
        self.assertNotEqual(r.returncode, 0, "a partial backup must not read as success")
        self.assertNotIn("VERIFIED", r.stdout)

        # The real thing passes.
        r = check('rm -f rc.db; sqlite3 app.db ".dump" > d.sql; sqlite3 -bail rc.db < d.sql')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("VERIFIED", r.stdout)


class RedTeamRound3Test(SeedSkillFixture):
    """One test per blocking finding from the third cold-agent review."""

    def test_b1_assume_unchanged_edit_is_destroyed_without_the_index_flag_check(self):
        """The loss itself: invisible to status, skipped by `stash --all`, no object left."""
        repo = self.make_fixture("assume-unchanged")
        self.assertIn("IMPORTANT LOCAL EDIT", (repo / "au.txt").read_text())

        # Invisible to every check the previous version made.
        self.assertNotIn("au.txt", self.git(repo, "status", "--porcelain", "-uall",
                                            "--ignored"))
        # The recovery does not contain it. This is the deterministic half: whether the
        # stash also overwrites the file in place is timing-dependent (git trusts the
        # cached stat data), so the test asserts only what always holds.
        self.git(repo, "stash", "push", "--all", "-q", "-m", "probe")
        self.assertNotIn("au.txt",
                         self.git(repo, "stash", "show", "--include-untracked",
                                  "--name-only", "'stash@{0}'"),
                         "the assume-unchanged path is not captured by the stash")

        # A residue-only gate reports a perfectly clean tree over the gap.
        self.assertEqual(
            self.sh('test -z "$(git status --porcelain -uall --ignored)"', repo).returncode,
            0, "this is the finding: the residue-only gate passes")

        # Whether `reset --hard` then clobbers the working copy is itself unspecified:
        # observed overwriting it in 34 of 34 sequential and CPU-loaded runs, and sparing
        # it in a few runs during concurrent suite execution, which is a racy-index
        # timing effect. The test asserts the invariant instead of the coin flip.
        self.git(repo, "reset", "--hard", "HEAD")

        # Nothing anywhere holds the edit.
        self.assertFalse(self.sh("git fsck --lost-found --unreachable", repo).stdout.strip(),
                         "no object survives, so the edit is unrecoverable")
        self.assertFalse(any("IMPORTANT LOCAL EDIT" in self.sh("git cat-file -p %s" % sha,
                                                               repo).stdout
                             for sha in re.findall(
                                 r"^(\w{40}) blob$",
                                 self.sh("git cat-file --batch-all-objects "
                                         "--batch-check='%(objectname) %(objecttype)'",
                                         repo).stdout, re.M)),
                         "the edit was never written as a git object")

    def test_b1_index_flag_check_makes_the_gate_fail_closed(self):
        """`git ls-files -v` is the half of the residue that `status` cannot see."""
        repo = self.make_fixture("assume-unchanged")
        flagged = self.sh("git ls-files -v | grep '^[a-z]'", repo)
        self.assertEqual(flagged.returncode, 0)
        self.assertIn("au.txt", flagged.stdout)

        r = self.run_prescribed(repo)
        self.assertNotEqual(r.returncode, 0, "the script must refuse to continue")
        self.assertIn("assume-unchanged", r.stdout + r.stderr)
        self.assertIn("au.txt", r.stdout + r.stderr, "it must name the invisible file")
        self.assertIn("IMPORTANT LOCAL EDIT", (repo / "au.txt").read_text(),
                      "the edit must still be on disk, so the abort has to land before "
                      "the stash, which is itself what overwrites it")
        self.assertEqual(self.git(repo, "stash", "list").strip(), "",
                         "the script must not have stashed at all")

        body = split_frontmatter(read_skill())[1]
        self.assertIn("git ls-files -v", body, "Phase 2 must read the index flags")

    def test_b1_phase4_proof_block_also_refuses_a_flagged_index(self):
        """The Phase 4 block is a standalone procedure, so it needs the same precondition.
        Run it against the flagged fixture rather than only reading it."""
        blocks = [lines for tag, lines, _ in fences(read_skill()) if tag == "safe-seq"]
        self.assertEqual(len(blocks), 1)
        block = "set -e\n" + "\n".join(claimed_exit(ln)[1] for ln in blocks[0])

        repo = self.make_fixture("assume-unchanged")
        r = self.bash(block, repo)
        self.assertNotEqual(r.returncode, 0,
                            "the proof block must refuse a flagged index:\n%s"
                            % (r.stdout + r.stderr))
        self.assertIn("IMPORTANT LOCAL EDIT", (repo / "au.txt").read_text(),
                      "and must refuse before the stash overwrites the edit")
        self.assertEqual(self.git(repo, "stash", "list").strip(), "",
                         "nothing should have been stashed")

    def test_b1_skip_worktree_is_not_treated_as_a_stop_condition(self):
        """Over-correcting on `S` would fail the gate on a flag whose edit survives, and a
        gate that cries wolf is a gate people route around."""
        repo = self.make_fixture("skip-worktree")
        self.assertIn("S sw.txt", self.git(repo, "ls-files", "-v"))

        # Verified premise: this edit really does survive a hard reset.
        self.git(repo, "reset", "--hard", "HEAD")
        self.assertIn("SKIP WORKTREE EDIT", (repo / "sw.txt").read_text())

        r = self.run_prescribed(repo)
        self.assertEqual(r.returncode, 0,
                         "skip-worktree alone must not abort:\n%s" % (r.stdout + r.stderr))
        self.assertIn("SKIP WORKTREE EDIT", (repo / "sw.txt").read_text())

    def test_b2_ours_does_not_match_a_superstring_stash_message(self):
        """Runs the artifact's own `ours()`. Unanchored, it selects a concurrent
        `${STAMP}-continued`, pops it, drops it, and exits 0."""
        repo = self.make_fixture()
        script = prescribed_script()
        ours_def = [ln for ln in script.splitlines() if ln.startswith("ours()")]
        self.assertEqual(len(ours_def), 1, "the script must define ours() exactly once")

        stamp = "preflight-20260825-010101-999-42"
        self.git(repo, "stash", "push", "--all", "-q", "-m", stamp)
        self.sh("echo stranger > s.txt && git add s.txt "
                "&& git stash push --all -q -m '%s-continued'" % stamp, repo)
        listing = self.git(repo, "stash", "list", "--format='%gd %gs'")
        self.assertIn("%s-continued" % stamp, listing)

        # The unanchored form is the defect, and it picks the stranger.
        wrong = self.bash("STAMP=%s; git stash list --format='%%gd %%gs' "
                          "| grep -F \"$STAMP\" | head -1 | cut -d' ' -f1" % stamp, repo)
        self.assertEqual(wrong.stdout.strip(), "stash@{0}",
                         "this is the finding: unanchored grep selects the stranger")

        # The shipped definition must pick ours.
        right = self.bash("STAMP=%s\n%s\nours" % (stamp, ours_def[0]), repo)
        self.assertEqual(right.stdout.strip(), "stash@{1}",
                         "the artifact's ours() must resolve to our own entry")
        self.assertIn("grep -E", ours_def[0], "the match must be anchored")

    def test_b2_prescribed_script_survives_a_superstring_neighbour(self):
        """End to end: a stash whose message extends ours must be left untouched."""
        repo = self.make_fixture()
        # A pre-existing entry whose message is a superstring of any preflight stamp.
        # Scope it to one path so the fixture's own dirty state is left intact.
        self.sh("echo stranger > s.txt && git add s.txt && git stash push --all -q "
                "-m 'preflight-continued-do-not-touch' -- s.txt", repo)
        self.assertTrue((repo / DOOMED).is_file(), "fixture state must survive the setup")
        before = self.git(repo, "stash", "list").strip()

        r = self.run_prescribed(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((repo / DOOMED).is_file(), "our own work must come back")
        self.assertEqual(self.git(repo, "stash", "list").strip(), before,
                         "the neighbour's stash must survive untouched")
        self.assertFalse((repo / "s.txt").exists(),
                         "the neighbour's content must not be injected into our tree")


class SkillCommandsExecuteTest(SeedSkillFixture):
    """Unverified claims in a skill are defects. Run the safe ones and check the status."""

    def test_every_bash_fence_is_classified(self):
        tags = [tag for tag, _, _ in fences(read_skill())]
        self.assertTrue(tags, "SKILL.md must contain runnable commands")
        for tag in tags:
            self.assertIn(tag, {"safe", "safe-seq", "destructive"},
                          "untagged bash fence: %r" % tag)

    def test_safe_commands_run_with_the_exit_status_the_skill_claims(self):
        ran = 0
        for tag, lines, _ in fences(read_skill()):
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
        for tag, lines, _ in fences(read_skill()):
            if tag != "safe-seq":
                continue
            repo = self.make_fixture()
            r = self.bash("set -e\n" + "\n".join(claimed_exit(ln)[1] for ln in lines), repo)
            self.assertEqual(r.returncode, 0,
                             "safe-seq failed:\n%s" % (r.stdout + r.stderr))
            self.assertTrue((repo / DOOMED).is_file(),
                            "a safe sequence must leave the untracked file in place")
            self.assertTrue((repo / IGNORED_SECRET).is_file(),
                            "and the ignored file too")
            ran += 1
        self.assertGreaterEqual(ran, 1)

    def test_destructive_fence_earns_its_tag_and_hides_nothing(self):
        tagged = [(lines, raw) for tag, lines, raw in fences(read_skill())
                  if tag == "destructive"]
        self.assertEqual(len(tagged), 1)
        lines, _ = tagged[0]
        self.assertTrue(any(DESTRUCTIVE.search(ln) for ln in lines),
                        "a destructive fence must contain a destructive command")
        for line in lines:
            if not INVOCATION.search(line.strip().lstrip("{ ").lstrip("if ")):
                continue   # shell control flow and variable assignment
            self.assertTrue(
                DESTRUCTIVE.search(line) or RECOVERY.search(line) or GUARD.search(line),
                "%r is neither destructive, a recovery move, nor guard machinery, so it "
                "belongs in a `safe` fence where it gets executed" % line)

    def test_prescribed_script_is_chained_and_exit_checked(self):
        """B1 in the artifact rather than in behaviour: four bare lines is the defect."""
        script = prescribed_script()
        self.assertIn("set -euo pipefail", script)
        stash_line = [ln for ln in script.splitlines() if "git stash push" in ln]
        self.assertTrue(stash_line)
        self.assertIn("||", stash_line[0],
                      "the stash must carry an explicit failure branch")
        self.assertIn("exit 1", stash_line[0])


if __name__ == "__main__":
    unittest.main()
