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

# Scratch filenames the skill's own commands write under $TMPDIR. Each test points
# TMPDIR at its own directory, so a stale file cannot make the coverage gate look like it
# passed and two concurrent runs of this suite cannot delete each other's files.
SCRATCH = ("preflight-at-risk.txt", "preflight-covered.txt", "preflight-uncovered.txt")

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
GUARD = re.compile(r"(rev-parse -q --verify refs/stash|git stash show|git stash list)")
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

    def clear_scratch(self):
        for name in SCRATCH:
            (self.scratch / name).unlink(missing_ok=True)

    def scratch_text(self, name):
        return (self.scratch / name).read_text(encoding="utf-8")

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

    def bash(self, script, cwd):
        return subprocess.run(["bash", "-c", script], cwd=str(cwd), capture_output=True,
                              text=True, env=self.env)

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

    def test_description_names_the_history_rewriting_commands(self):
        """`reflog expire` and `gc --prune=now` destroy the skill's own fallback, so a
        session has to be able to recognise them from the trigger alone."""
        d = parse_frontmatter(split_frontmatter(read_skill())[0])["description"]
        for token in ("reflog expire", "gc --prune=now", "branch -D", "checkout -f",
                      "rebase", "filter-repo"):
            self.assertIn(token, d, "description omits %r" % token)

    def test_body_stays_under_the_line_ceiling(self):
        _, body = split_frontmatter(read_skill())
        n = len(body.strip().splitlines())
        self.assertLessEqual(n, MAX_BODY_LINES, "body is %d lines" % n)

    def test_iron_law_is_stated_exactly_once_and_demands_per_path(self):
        body = split_frontmatter(read_skill())[1]
        self.assertEqual(body.count("NO DESTRUCTIVE COMMAND WITHOUT"), 1)
        law = re.search(r"```text\n(NO DESTRUCTIVE COMMAND WITHOUT.*?)```", body, re.S)
        self.assertIn("PER-PATH", law.group(1))

    def test_bundled_references_exist_and_are_linked(self):
        body = split_frontmatter(read_skill())[1]
        linked = set(re.findall(r"\]\((references/[^)]+)\)", body))
        self.assertTrue(linked, "long reference material must be bundled, not inlined")
        for rel in linked:
            self.assertTrue((SKILL_DIR / rel).is_file(), "missing bundled file: %s" % rel)
        on_disk = {"references/" + p.name for p in (SKILL_DIR / "references").iterdir()}
        self.assertEqual(on_disk, linked, "every bundled reference must be linked")

    def test_unverified_datastore_claims_are_labelled_as_such(self):
        """This repo treats an unverified claim in a skill as a defect. The tools for
        these engines are not installed here, so the reference must say so rather than
        implying the commands were run."""
        ref = (SKILL_DIR / "references" / "datastore-preflight.md").read_text(
            encoding="utf-8")
        for engine in ("Postgres", "MySQL", "Prisma", "Rails", "Alembic", "Django"):
            block = re.search(r"^## %s\n(.*?)(?=^## |\Z)" % engine, ref, re.S | re.M)
            self.assertIsNotNone(block, "no section for %s" % engine)
            self.assertIn("NOT VERIFIED", block.group(1),
                          "%s section must carry a verification-status note" % engine)
        sqlite = re.search(r"^## SQLite\n(.*?)(?=^## |\Z)", ref, re.S | re.M)
        self.assertIn("VERIFIED", sqlite.group(1))

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
            r"(reset --hard|checkout -f|checkout --|restore --worktree|clean|stash drop"
            r"|branch -d|reflog expire|gc --prune|filter-repo|rebase|--force|rm -rf"
            r"|truncate|rollback|\bdrop\b|\breset\b)",
            description.lower())
        self.assertGreaterEqual(len(set(vocabulary)), 8,
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

        r = self.bash(prescribed_script(), repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        self.assertTrue((repo / DOOMED).is_file(), "the recovery-first sequence must save it")
        self.assertEqual((repo / DOOMED).read_bytes(), original, "byte-identical or bust")
        # B3: the ignored file has to come back too, which `-u` alone would not do.
        self.assertTrue((repo / IGNORED_SECRET).is_file(),
                        "the ignored credential must survive as well")
        self.assertEqual((repo / IGNORED_SECRET).read_bytes(), secret)
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
    """One test per blocking finding from the cold-agent review."""

    def test_b1_prescribed_script_aborts_when_the_stash_fails(self):
        """Mid-merge, `git stash push` exits 1 and stashes nothing. The unchained draft
        ran `reset --hard` on the next line anyway, with no recovery in existence."""
        repo = self.make_fixture("merge-conflict")
        before_head = self.head(repo)

        # Confirm the fixture really does break the stash, rather than assuming it.
        probe = self.sh("git stash push --all -m probe", repo)
        self.assertNotEqual(probe.returncode, 0, "fixture must make `stash push` fail")
        self.assertEqual(self.git(repo, "stash", "list").strip(), "")

        r = self.bash(prescribed_script(), repo)
        self.assertNotEqual(r.returncode, 0, "the script must abort, not continue")
        self.assertIn("ABORTED", r.stdout + r.stderr,
                      "the failure path must say so out loud")
        # The destructive line must not have run.
        self.assertEqual(self.head(repo), before_head, "reset --hard must not have run")
        self.assertTrue((repo / DOOMED).is_file(),
                        "the untracked file must still be on disk after the abort")

    def test_b2_prescribed_script_never_pops_a_stash_it_did_not_create(self):
        """On a clean tree `git stash push` prints `No local changes to save` and exits 0.
        An unguarded pop then injects a stranger's stash and destroys it."""
        repo = self.make_fixture("stranger-stash")
        stash_before = self.git(repo, "stash", "list").strip()
        self.assertIn("old-unrelated-work", stash_before)
        readme_before = (repo / "README.md").read_bytes()

        r = self.bash(prescribed_script(), repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        self.assertEqual((repo / "README.md").read_bytes(), readme_before,
                         "the stranger's stash must not be injected into the tree")
        self.assertEqual(self.git(repo, "stash", "list").strip(), stash_before,
                         "the stranger's stash must still be on the stack")
        self.assertNotIn("LAST WEEKS UNRELATED WORK",
                         (repo / "README.md").read_text(encoding="utf-8"))

    def test_b3_include_untracked_misses_ignored_files_and_all_does_not(self):
        """The gap that made the first draft's manifest wrong: `-u` leaves `!!` on disk."""
        repo = self.make_fixture()
        self.git(repo, "stash", "push", "--include-untracked", "-q", "-m", "u")
        self.assertTrue((repo / IGNORED_SECRET).is_file(),
                        "`-u` leaves the ignored credential on disk, unstashed")
        self.assertNotIn(IGNORED_SECRET,
                         self.git(repo, "stash", "show", "--include-untracked",
                                  "--name-only", "'stash@{0}'"))
        self.git(repo, "stash", "pop", "-q")

        self.git(repo, "stash", "push", "--all", "-q", "-m", "a")
        self.assertFalse((repo / IGNORED_SECRET).exists(),
                         "`--all` takes the ignored file into the stash")
        self.assertIn(IGNORED_SECRET,
                      self.git(repo, "stash", "show", "--include-untracked",
                               "--name-only", "'stash@{0}'"))
        self.git(repo, "stash", "pop", "-q")
        self.assertTrue((repo / IGNORED_SECRET).is_file())

        # And the skill must prescribe the one that works.
        self.assertIn("git stash push --all", prescribed_script())
        self.assertNotIn("git stash push --include-untracked -m", prescribed_script())

    def test_b4_coverage_gate_fails_when_a_path_is_uncovered(self):
        """The manifest was theatre because nothing checked it. The gate is a diff, so an
        uncovered path makes it exit non-zero rather than reading as fine."""
        repo = self.make_fixture()
        capture = ("git -c core.quotePath=false status --porcelain -uall --ignored "
                   "| grep -E '^(\\?\\?|!!| M| D|MM|AM)' | cut -c4- | sort "
                   '> "$TMPDIR"/preflight-at-risk.txt')
        gate = ("git stash show --include-untracked --name-only 'stash@{0}' | sort "
                '> "$TMPDIR"/preflight-covered.txt; '
                'comm -23 "$TMPDIR"/preflight-at-risk.txt "$TMPDIR"/preflight-covered.txt '
                '> "$TMPDIR"/preflight-uncovered.txt; '
                'test ! -s "$TMPDIR"/preflight-uncovered.txt')

        # An under-covering recovery (`-u`, which misses the ignored file) must fail it.
        r = self.bash("%s; git stash push --include-untracked -q -m weak; %s"
                      % (capture, gate), repo)
        self.assertNotEqual(r.returncode, 0, "the gate must reject an uncovered path")
        self.assertIn(IGNORED_SECRET, self.scratch_text("preflight-uncovered.txt"))
        self.git(repo, "stash", "pop", "-q")

        # The prescribed recovery (`--all`) must pass it.
        self.clear_scratch()
        r = self.bash("%s; git stash push --all -q -m strong; %s" % (capture, gate), repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.scratch_text("preflight-uncovered.txt"), "")

    def test_b4_coverage_gate_fails_when_the_enumeration_was_skipped(self):
        """Fires on absence: no at-risk file means `comm` errors, not that all is well."""
        repo = self.make_fixture()
        self.clear_scratch()
        r = self.bash(
            "git stash push --all -q -m x; "
            "git stash show --include-untracked --name-only 'stash@{0}' | sort "
            '> "$TMPDIR"/preflight-covered.txt; '
            'comm -23 "$TMPDIR"/preflight-at-risk.txt "$TMPDIR"/preflight-covered.txt', repo)
        self.assertNotEqual(r.returncode, 0,
                            "skipping Phase 2 must fail the gate, not bypass it")
        self.assertIn("No such file", r.stderr)

    def test_b5_prescribed_enumeration_lists_every_path_not_a_rollup(self):
        """50 untracked files under one directory. `clean -nd` says one line."""
        repo = self.make_fixture("scaffold50")

        rollup = self.git(repo, "clean", "-nd")
        self.assertEqual(len(rollup.strip().splitlines()), 1,
                         "this is the defect: a directory rollup")
        self.assertIn("scaffold/", rollup)

        enumerated = self.git(repo, "-c", "core.quotePath=false", "status",
                              "--porcelain", "-uall", "--ignored")
        paths = [ln[3:] for ln in enumerated.strip().splitlines()]
        self.assertEqual(len(paths), 50, "the prescribed enumeration must list each file")
        self.assertIn("scaffold/f37.txt", paths)

        # And the Phase 2 enumeration fence specifically must prescribe the form that
        # enumerates. Asserting on the whole body would pass on any other mention.
        body = split_frontmatter(read_skill())[1]
        phase2 = re.search(r"^## Phase 2:.*?^## Phase 3:", body, re.S | re.M)
        self.assertIsNotNone(phase2, "SKILL.md must have a Phase 2 section")
        status_lines = [ln for ln in phase2.group(0).splitlines()
                        if "status --porcelain" in ln]
        self.assertTrue(status_lines, "Phase 2 must enumerate with git status")
        for ln in status_lines:
            self.assertIn("-uall", ln,
                          "Phase 2 status command %r rolls untracked dirs up to one "
                          "line" % ln)
            self.assertIn("--ignored", ln)


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
            self.clear_scratch()
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
