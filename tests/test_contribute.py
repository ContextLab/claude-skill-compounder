#!/usr/bin/env python3
"""Exercises skillcontrib for real: real SKILL.md files on disk, real GitHub reads.

No mocks. The preflight tests write actual skill directories into a temp dir and run
the actual script against them, and one of them runs the checker over every skill
installed on this machine. The dedup tests hit live GitHub through `gh`; they skip
cleanly when gh is missing or unauthenticated so a token-less CI run still passes.
"""

import glob
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "bin" / "skillcontrib"
LIVE_REPO = "cli/cli"
SKILLS_REPO = "anthropics/skills"
NESTED_REPO = "anthropics/claude-code"
PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
WRITE_COMMANDS = ("gh repo fork", "gh repo sync", "gh pr create", "git push")

VALID = """---
name: %s
description: Use when a sample is needed. Do NOT use for anything real.
---

# Sample

A body.
"""


def gh_ready():
    """True when a real, authenticated gh is available on this machine."""
    if shutil.which("gh") is None:
        return False
    return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0


LIVE = gh_ready()


class PreflightTest(unittest.TestCase):
    """Real files, real script, minimal environment.

    The checker is deliberately narrow: SKILL.md exists, the frontmatter parses with a
    real YAML parser, and `name` matches the directory. An earlier version enforced
    length and key-portability limits and hard-failed 46 of 156 installed skills, so
    those checks are gone rather than re-tuned.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def skill(self, name, text=None):
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(text if text is not None else VALID % name)
        return d

    def preflight(self, path, *flags):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.root)}
        return subprocess.run([str(SCRIPT), "preflight", str(path)] + list(flags),
                              capture_output=True, text=True, env=env)

    def test_valid_skill_passes(self):
        r = self.preflight(self.skill("ok"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("name: ok (matches the directory)", r.stdout)

    def test_missing_directory_is_code_10(self):
        r = self.preflight(self.root / "nope")
        self.assertEqual(r.returncode, 10)
        self.assertIn("skill directory not found", r.stderr)

    def test_missing_skill_md_is_code_11(self):
        d = self.root / "empty"
        d.mkdir()
        r = self.preflight(d)
        self.assertEqual(r.returncode, 11)
        self.assertIn("SKILL.md not found", r.stderr)

    def test_no_frontmatter_is_code_12(self):
        r = self.preflight(self.skill("bare", "# Just a heading\n\nNo frontmatter.\n"))
        self.assertEqual(r.returncode, 12)
        self.assertIn("frontmatter missing", r.stderr)

    def test_unterminated_frontmatter_is_code_12(self):
        r = self.preflight(self.skill("open", "---\nname: open\ndescription: y\n\n# Body\n"))
        self.assertEqual(r.returncode, 12)
        self.assertIn("unterminated", r.stderr)

    def test_genuinely_broken_yaml_is_code_12(self):
        # Unbalanced quote: a real parser rejects this, a substring test would not.
        text = '---\nname: broke\ndescription: "unterminated\n---\n\n# B\n'
        r = self.preflight(self.skill("broke", text))
        self.assertEqual(r.returncode, 12)
        self.assertIn("does not parse as YAML", r.stderr)

    def test_missing_name_is_code_17(self):
        r = self.preflight(self.skill("anon", "---\ndescription: Use when nameless.\n---\n\n# B\n"))
        self.assertEqual(r.returncode, 17)
        self.assertIn("name is missing", r.stderr)

    def test_missing_description_is_code_17(self):
        # A skill with no description never fires, so this is precisely what preflight
        # is for. The check was removed by accident along with the length limits.
        r = self.preflight(self.skill("nodesc", "---\nname: nodesc\n---\n\n# B\n"))
        self.assertEqual(r.returncode, 17)
        self.assertIn("description is missing or empty", r.stderr)

    def test_empty_description_is_code_17(self):
        r = self.preflight(self.skill("blankdesc", '---\nname: blankdesc\ndescription: "  "\n---\n\n# B\n'))
        self.assertEqual(r.returncode, 17)
        self.assertIn("description is missing or empty", r.stderr)

    def test_name_not_matching_the_directory_is_code_17(self):
        # Claude Code addresses a skill by its directory, so this makes it unreachable.
        r = self.preflight(self.skill("dirname", VALID % "some-other-name"))
        self.assertEqual(r.returncode, 17)
        self.assertIn("name is 'some-other-name' but the directory is 'dirname'", r.stderr)

    # ------------------------------------------------- what must NOT be rejected

    def test_block_scalar_with_a_colon_is_accepted(self):
        # Valid YAML that a substring test for ": " wrongly rejected. This is the shape
        # the real huggingface-best skill uses.
        text = ('---\nname: demo\ndescription: >-\n  Use when the user wants a demo.\n'
                '  Triggers on: "demo", "show me".\n---\n\n# Demo\n')
        r = self.preflight(self.skill("demo", text))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_long_description_is_not_a_failure(self):
        # 29 of 156 installed skills exceed 500 characters. Length is a review topic.
        text = "---\nname: fat\ndescription: %s\n---\n\n# Body\n" % ("Use when " + "x" * 900)
        r = self.preflight(self.skill("fat", text))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_long_body_is_not_a_failure(self):
        body = "\n".join("line %d" % i for i in range(600))
        r = self.preflight(self.skill("longbody", (VALID % "longbody") + body + "\n"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_non_portable_frontmatter_keys_are_not_a_failure(self):
        # 44 of 156 installed skills carry keys like these, four of them Anthropic's.
        text = ('---\nname: custom\ndescription: Use when testing.\n'
                'argument-hint: "[thing]"\nlevel: 2\ntriggers: [a, b]\n---\n\n# B\n')
        r = self.preflight(self.skill("custom", text))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_other_files_in_the_skill_directory_are_listed(self):
        # A copy step that takes only SKILL.md silently drops these.
        d = self.skill("multi")
        (d / "scripts").mkdir()
        (d / "scripts" / "run.py").write_text("print('hi')\n")
        (d / "LICENSE.txt").write_text("license\n")
        r = self.preflight(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LICENSE.txt", r.stdout)
        self.assertIn("scripts/run.py", r.stdout)


class InstalledSkillsSweepTest(unittest.TestCase):
    """The checker has to accept skills that actually ship, or nobody can use it."""

    def installed(self):
        found = []
        for root in (Path.home() / ".claude" / "skills",
                     Path.home() / ".claude" / "plugins" / "cache"):
            found += glob.glob(str(root) + "/**/SKILL.md", recursive=True)
        return sorted(set(found))

    def test_the_checker_accepts_essentially_every_installed_skill(self):
        skills = self.installed()
        if len(skills) < 20:
            self.skipTest("not enough installed skills on this machine to be meaningful")
        failures = []
        for f in skills:
            d = os.path.dirname(f)
            r = subprocess.run([str(SCRIPT), "preflight", d], capture_output=True, text=True)
            if r.returncode != 0:
                failures.append((d, r.stderr.strip().splitlines()[0] if r.stderr else ""))
        # The previous limit-enforcing version failed 46 of 156. Anything above a couple
        # of genuine name/directory mismatches means the gate is wrong again.
        self.assertLessEqual(len(failures), 3,
                             "checker rejects %d of %d installed skills:\n%s"
                             % (len(failures), len(skills),
                                "\n".join("%s :: %s" % f for f in failures[:10])))


class ShippedSkillTest(unittest.TestCase):
    """The skill this repo ships must satisfy the checker this repo ships."""

    SKILL_DIR = REPO / "skills" / "contribute-skill"

    def text(self):
        return (self.SKILL_DIR / "SKILL.md").read_text()

    def test_it_passes_its_own_preflight(self):
        r = subprocess.run([str(SCRIPT), "preflight", str(self.SKILL_DIR)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_frontmatter_is_parseable_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        data = yaml.safe_load(self.text().split("---\n")[1])
        self.assertIsInstance(data, dict)
        self.assertIsInstance(data.get("description"), str)
        self.assertTrue(set(data) <= PORTABLE_KEYS)

    def test_description_is_a_quoted_trigger_clause(self):
        desc = re.search(r"^description: (.+)$", self.text(), re.M).group(1)
        self.assertTrue(desc.startswith('"') and desc.endswith('"'),
                        "the description must be quoted so a colon cannot break the YAML")
        desc = desc[1:-1]
        self.assertTrue(desc.startswith("Use when"), desc[:60])
        self.assertIn("Do NOT use", desc)

    # ---------------------------------------------------------- reading the document
    #
    # Everything below reads the SKILL.md as text. It does NOT execute the procedure.
    # The one test that executes anything is ExecutableStagingTest, which runs the
    # read-only staging block against a local git repository.

    def split_at_writes(self):
        text = self.text()
        marker = "## 6. The write sequence"
        self.assertIn(marker, text, "the write sequence must be its own section")
        return text[:text.index(marker)], text[text.index(marker):]

    def test_no_write_command_appears_before_the_write_section(self):
        before, _ = self.split_at_writes()
        for cmd in WRITE_COMMANDS:
            self.assertNotIn(cmd, before,
                             "%r appears in the read-only half of the procedure" % cmd)

    def test_a_read_only_clone_exists_for_staging(self):
        # The defect this pins: the gates required staging in a clone, and the only
        # clone the procedure defined was `gh repo fork --clone`, a network write. So
        # the ordering rule was circular and could not be obeyed.
        before, _ = self.split_at_writes()
        self.assertIn("git clone https://github.com/", before,
                      "the procedure must define a read-only clone to stage in")
        staging = before[before.index("### 5a."):before.index("### 5b.")]
        self.assertIn("git clone", staging)
        for cmd in WRITE_COMMANDS:
            self.assertNotIn(cmd, staging, "%r appears in the staging step" % cmd)

    def test_the_upload_step_is_spelled_out(self):
        # "Upload the branch" is not an instruction a cold session can follow, and it
        # hid the fact that a push is a write.
        _, writes = self.split_at_writes()
        self.assertIn("git push -u origin", writes)
        self.assertIn("git push -u fork", writes)

    def test_the_fork_is_the_first_write_on_the_fork_path(self):
        _, writes = self.split_at_writes()
        fork_section = writes[writes.index("### 6b."):]
        self.assertLess(fork_section.index("gh repo fork"), fork_section.index("git push"),
                        "the fork must precede the push on the fork path")

    def test_repo_sync_targets_the_fork_and_never_upstream(self):
        # `gh repo sync` writes to its argument: "Syncing uses the default branch of the
        # source repository to update the matching branch on the destination." Naming
        # upstream there fast-forwards upstream's default branch, an unconsented write
        # that succeeds for real when upstream is itself a fork.
        text = self.text()
        occurrences = re.findall(r"`?gh repo sync ([^`\s]+)", text)
        self.assertTrue(occurrences, "the stale-fork remedy must still be documented")
        for target in occurrences:
            self.assertIn("fork-owner", target,
                          "gh repo sync must name the fork as its destination, got %r" % target)
        self.assertNotIn("gh repo sync <owner>/<repo>", text)

    def test_dry_run_is_not_claimed_to_be_read_only(self):
        text = self.text()
        self.assertIn("May still push git changes", text)
        self.assertNotIn("without opening anything", text)

    def test_the_whole_skill_directory_is_copied(self):
        self.assertIn("cp -R", self.text())

    def test_no_em_dashes_anywhere(self):
        for p in [self.SKILL_DIR / "SKILL.md", SCRIPT,
                  REPO / "CONTRIBUTING.md", REPO / ".github" / "PULL_REQUEST_TEMPLATE.md"]:
            self.assertNotIn("—", p.read_text(), "em-dash in %s" % p)


class ExecutableStagingTest(unittest.TestCase):
    """Runs the read-only staging block from the SKILL.md, for real, against real git.

    This is the one test that executes the procedure rather than reading it. It proves
    two things the document tests cannot: that the commands as written actually work,
    and that running them leaves the upstream repository untouched. It uses a local
    repository, so it needs no network and creates nothing on GitHub.
    """

    SKILL_DIR = REPO / "skills" / "contribute-skill"

    def staging_block(self):
        text = (self.SKILL_DIR / "SKILL.md").read_text()
        section = text[text.index("### 5a."):text.index("### 5b.")]
        blocks = re.findall(r"```bash\n(.*?)```", section, re.S)
        self.assertEqual(len(blocks), 1, "5a must contain exactly one bash block")
        return blocks[0]

    def test_the_staging_block_runs_and_writes_nothing_upstream(self):
        block = self.staging_block()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = root / "upstream.git"
            seed = root / "seed"
            # A real upstream: a bare repo with one commit on its default branch.
            subprocess.run(["git", "init", "--bare", "-b", "main", str(upstream)],
                           check=True, capture_output=True)
            seed.mkdir()
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                       GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
            for cmd in (["git", "init", "-b", "main"], ["git", "commit", "--allow-empty", "-m", "seed"],
                        ["git", "remote", "add", "origin", str(upstream)],
                        ["git", "push", "origin", "main"]):
                subprocess.run(cmd, cwd=seed, check=True, capture_output=True, env=env)
            before = subprocess.run(["git", "show-ref"], cwd=upstream,
                                    capture_output=True, text=True).stdout

            # A real skill to contribute, with a file besides SKILL.md so the `cp -R`
            # is genuinely exercised.
            src = root / "demo-skill"
            (src / "scripts").mkdir(parents=True)
            (src / "SKILL.md").write_text(VALID % "demo-skill")
            (src / "scripts" / "run.sh").write_text("echo hi\n")

            script = (block
                      .replace("https://github.com/<owner>/<repo>.git", str(upstream))
                      .replace("/tmp/contrib-<name>", str(root / "clone"))
                      .replace("<path-to-skill-dir>", str(src))
                      .replace("<skills-dir>", "skills")
                      .replace("<name>", "demo-skill"))
            r = subprocess.run(["bash", "-euo", "pipefail", "-c", script],
                               capture_output=True, text=True, env=env, cwd=str(root))
            self.assertEqual(r.returncode, 0,
                             "the staging block as written failed:\n%s\n%s" % (script, r.stderr))

            clone = root / "clone"
            listed = subprocess.run(["git", "show", "--name-only", "--pretty=format:", "HEAD"],
                                    cwd=clone, capture_output=True, text=True).stdout
            self.assertIn("skills/demo-skill/SKILL.md", listed)
            self.assertIn("skills/demo-skill/scripts/run.sh", listed,
                          "cp -R must carry the whole skill directory, not just SKILL.md")
            branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                    cwd=clone, capture_output=True, text=True).stdout.strip()
            self.assertEqual(branch, "add-skill-demo-skill")

            after = subprocess.run(["git", "show-ref"], cwd=upstream,
                                   capture_output=True, text=True).stdout
            self.assertEqual(before, after,
                             "staging must leave upstream untouched; refs changed")


class ReadOnlyTest(unittest.TestCase):
    """skillcontrib does reconnaissance. The writes belong to the skill, behind gates."""

    def test_script_contains_no_network_writes(self):
        text = SCRIPT.read_text()
        for forbidden in ("gh pr create", "gh repo fork", "git push"):
            self.assertNotIn(forbidden, text,
                             "%r appears in a script that must never write" % forbidden)

    def test_help_exits_zero(self):
        r = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("skillcontrib dedup", r.stdout)

    def test_help_warns_about_the_default_repo(self):
        r = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertIn("Pass it explicitly", r.stdout)

    def test_unknown_command_is_a_usage_error(self):
        r = subprocess.run([str(SCRIPT), "frobnicate"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown command", r.stderr)

    def test_dedup_without_a_name_is_a_usage_error(self):
        r = subprocess.run([str(SCRIPT), "dedup"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


@unittest.skipUnless(LIVE, "gh is missing or unauthenticated; live GitHub reads skipped")
class LiveDedupTest(unittest.TestCase):
    """Real calls against real repos with real history.

    These inherit the ambient environment on purpose: gh needs its own config and
    credentials, and pointing HOME at a temp dir would only test the unauthenticated
    path. anthropics/skills supplies shipped skills, an open proposal, and declined
    ones; anthropics/claude-code supplies the nested plugins/<x>/skills/<x>/ layout;
    cli/cli supplies thousands of pull requests in every state.
    """

    ROW = re.compile(r"^(proposal|touch|mention|fuzzy)\s+(OPEN|CLOSED|MERGED)\s")

    def dedup(self, *args, **kw):
        repo = kw.pop("repo", LIVE_REPO)
        return subprocess.run([str(SCRIPT), "dedup"] + list(args) + ["--repo", repo],
                              capture_output=True, text=True)

    def rows(self, stdout):
        return [ln.split() for ln in stdout.splitlines() if self.ROW.match(ln)]

    # ------------------------------------------- tree probe: normalisation and depth

    def test_a_skill_that_already_ships_upstream_is_not_clean(self):
        r = self.dedup("internal-comms", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 9, r.stdout[-800:])
        self.assertIn("ALREADY UPSTREAM", r.stdout)
        self.assertNotIn("CLEAN", r.stdout)

    def test_case_and_separator_variants_do_not_defeat_the_tree_probe(self):
        # skills/internal-comms/ ships upstream. Each of these returned 0 or 3 before.
        for variant in ("internal_comms", "Internal-Comms", "INTERNALCOMMS", "internalcomms"):
            r = self.dedup(variant, repo=SKILLS_REPO)
            self.assertEqual(r.returncode, 9,
                             "%r slipped past the tree probe (rc=%d)" % (variant, r.returncode))

    def test_nested_plugin_layouts_are_found(self):
        # plugins/<plugin>/skills/<skill>/SKILL.md is a real layout in a real Anthropic
        # repo, and a skills/<name>/ lookup never sees it.
        for nested in ("frontend-design", "plugin-settings", "mcp-integration", "writing-rules"):
            r = self.dedup(nested, repo=NESTED_REPO)
            self.assertEqual(r.returncode, 9,
                             "%r not found in the nested layout (rc=%d)" % (nested, r.returncode))
            self.assertRegex(r.stdout, r"ALREADY UPSTREAM: \S+/%s/SKILL\.md" % nested)

    def test_the_tree_probe_reads_the_upstream_name_frontmatter(self):
        r = self.dedup("internal-comms", repo=SKILLS_REPO)
        self.assertIn("frontmatter declares name: internal-comms", r.stdout)

    def test_a_name_absent_from_the_tree_is_not_reported_as_upstream(self):
        r = self.dedup("zzqqx-nonexistent-skill-name", repo=NESTED_REPO)
        self.assertEqual(r.returncode, 0, r.stdout[-800:])
        self.assertIn("CLEAN", r.stdout)

    # ------------------------------------------------- proposal versus mere mention

    def test_a_closed_proposal_still_blocks_with_code_5(self):
        # anthropics/skills#1407 added skills/macho/SKILL.md and was closed unmerged.
        r = self.dedup("macho", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 5, r.stdout[-800:])
        self.assertIn("BLOCKED", r.stdout)
        self.assertIn("proposal", {row[0] for row in self.rows(r.stdout)})

    def test_a_closed_proposal_is_not_called_a_rejection(self):
        # It is as often a superseded revision, and the difference is not machine-readable.
        r = self.dedup("macho", repo=SKILLS_REPO)
        self.assertNotIn("declined", r.stdout)
        self.assertIn("superseded", r.stdout)

    def test_a_typo_fix_is_not_reported_as_a_rejection(self):
        r = self.dedup("canvas-design", repo=SKILLS_REPO)
        self.assertNotIn("BLOCKED", r.stdout)
        self.assertNotEqual(r.returncode, 5)

    def test_closed_pull_requests_that_only_touch_the_name_do_not_block(self):
        # cli/cli has 14 CLOSED pull requests touching paths under an `extension`
        # directory and none of them proposes a skill. Treating any of those as a
        # rejection is what trains reflexive use of --override-rejected.
        r = self.dedup("extension")
        self.assertEqual(r.returncode, 3, r.stdout[-800:])
        self.assertIn("ASK THE USER", r.stdout)
        self.assertNotIn("BLOCKED", r.stdout)
        kinds = {row[0] for row in self.rows(r.stdout)}
        self.assertNotIn("proposal", kinds)
        states = {row[1] for row in self.rows(r.stdout)}
        self.assertIn("CLOSED", states, "the fixture must include closed pull requests")

    def test_a_proposal_at_any_depth_is_still_a_proposal(self):
        # anthropics/skills#1036 adds skills/skills/designlang/SKILL.md. The old
        # path-exact matcher called that a mere title mention.
        r = self.dedup("designlang", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 4, r.stdout[-800:])
        self.assertIn("proposal", {row[0] for row in self.rows(r.stdout)})

    def test_an_open_proposal_stops_with_code_4(self):
        r = self.dedup("presentation-chef", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 4, r.stdout[-800:])
        self.assertIn("STOP", r.stdout)

    def test_override_rejected_downgrades_the_block(self):
        r = self.dedup("macho", "--override-rejected", repo=SKILLS_REPO)
        self.assertIn(r.returncode, (3, 4), r.stdout[-800:])
        self.assertIn("OVERRIDE", r.stdout)

    # -------------------------------------------------------------- repo-level stops

    def test_an_archived_upstream_gets_its_own_exit_code(self):
        r = self.dedup("anything", repo="google/tink")
        self.assertEqual(r.returncode, 18, r.stdout + r.stderr)
        self.assertIn("archived", r.stderr)

    def test_unknown_repo_fails_loudly_rather_than_looking_clean(self):
        r = self.dedup("anything", repo="ContextLab/no-such-repo-zzqqx")
        self.assertEqual(r.returncode, 8, r.stdout + r.stderr)
        self.assertIn("could not resolve", r.stderr)

    def test_a_truncated_tree_listing_is_not_reported_as_clean(self):
        # torvalds/linux has ~72k paths, past the tree API's cap. Reporting rc 0 there
        # would be a clean result the probe cannot actually support.
        r = self.dedup("zzqqx-nonexistent-skill-name", repo="torvalds/linux")
        self.assertEqual(r.returncode, 19, r.stdout[-800:])
        self.assertIn("INCOMPLETE", r.stdout, "the caveat must be on stdout, not only stderr")
        self.assertIn("NOT CERTIFIED CLEAN", r.stdout)
        self.assertNotIn("CLEAN: no duplicate found", r.stdout)

    def test_a_clean_result_reports_the_upstream_layout(self):
        # Section 5a says to use the layout the tree probe found, which is unfollowable
        # if a clean result prints no layout.
        r = self.dedup("zzqqx-nonexistent-skill-name", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 0, r.stdout[-800:])
        self.assertIn("upstream keeps skills under:", r.stdout)

    def test_a_nested_repo_reports_its_nested_layout(self):
        r = self.dedup("zzqqx-nonexistent-skill-name", repo=NESTED_REPO)
        self.assertRegex(r.stdout, r"upstream keeps skills under: plugins/\S+/skills")

    def test_the_target_repo_is_printed(self):
        r = self.dedup("zzqqx-nonexistent-skill-name")
        self.assertIn("repo:        %s" % LIVE_REPO, r.stdout)
        self.assertIn("pass --repo", r.stdout)

    # ----------------------------------------------------------------- state coverage

    def test_state_all_sweep_returns_merged_and_closed(self):
        r = self.dedup("extension")  # thousands of pull requests in every state
        states = {row[1] for row in self.rows(r.stdout)}
        self.assertIn("MERGED", states, r.stdout[:2000])
        self.assertIn("CLOSED", states, r.stdout[:2000])

    def test_fuzzy_only_match_asks_the_user_with_code_3(self):
        r = self.dedup("zzqqx-nonexistent-skill-name", "--description",
                       "codespaces machine listing alongside repository visibility settings")
        self.assertEqual(r.returncode, 3, r.stdout[-800:])
        self.assertIn("ASK THE USER", r.stdout)
        self.assertEqual({row[0] for row in self.rows(r.stdout)}, {"fuzzy"})

    def test_sub_threshold_rows_are_shown_not_hidden(self):
        r = self.dedup("zzqqx-nonexistent-skill-name", "--description",
                       "codespaces machine listing alongside repository visibility settings")
        self.assertIn("below", {row[3] for row in self.rows(r.stdout)},
                      "sub-threshold fuzzy hits must still be printed")
        self.assertIn("shown but not counted", r.stdout)

    def test_no_match_is_clean(self):
        r = self.dedup("zzqqx-nonexistent-skill-name")
        self.assertEqual(r.returncode, 0, r.stdout[-800:])
        self.assertIn("CLEAN", r.stdout)

    def test_search_index_lag_is_disclosed(self):
        r = self.dedup("zzqqx-nonexistent-skill-name")
        self.assertIn("search index lags", r.stdout)


@unittest.skipUnless(LIVE, "gh is missing or unauthenticated; live GitHub reads skipped")
class LiveWhoamiTest(unittest.TestCase):

    def whoami(self, repo=LIVE_REPO):
        return subprocess.run([str(SCRIPT), "whoami", "--repo", repo],
                              capture_output=True, text=True)

    def test_reports_a_role_and_an_identity(self):
        r = self.whoami()
        self.assertEqual(r.returncode, 0, r.stderr)
        role = re.search(r"^role:\s+(\w+)$", r.stdout, re.M).group(1)
        self.assertIn(role, ("maintainer", "contributor"))
        self.assertRegex(r.stdout, re.compile(r"^acting as:\s+\S+$", re.M))
        self.assertRegex(r.stdout, re.compile(r"^archived:\s+(true|false)$", re.M))

    def test_permission_level_is_reported_not_just_collaborator_status(self):
        # The bare collaborators/<user> endpoint answers 204 for read-only collaborators
        # too, which would wrongly read as maintainer. The permission level is the answer.
        r = self.whoami()
        self.assertRegex(r.stdout, re.compile(r"^permission: \S+", re.M))
        self.assertNotIn("Must have push access", r.stdout)

    def test_the_identity_that_actually_pushes_is_reported(self):
        # gh's account and git's credential helper can be different accounts, and the
        # second one is what the commits land under. Nothing else surfaces it.
        r = self.whoami()
        self.assertRegex(r.stdout, re.compile(r"^push identity: ", re.M))

    def test_a_repo_the_user_cannot_push_to_takes_the_fork_path(self):
        r = self.whoami()
        self.assertIn("fork the repo", r.stdout)

    def test_archived_upstream_exits_18(self):
        r = self.whoami("google/tink")
        self.assertEqual(r.returncode, 18, r.stdout + r.stderr)
        self.assertIn("archived:  true", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
