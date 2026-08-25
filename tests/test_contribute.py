#!/usr/bin/env python3
"""Exercises skillcontrib for real: real SKILL.md files on disk, real GitHub reads.

No mocks. The preflight tests write actual skill directories into a temp dir and run
the actual script against them. The dedup tests hit the live GitHub search index via
`gh`, against cli/cli, which has thousands of pull requests in every state; they skip
cleanly when gh is missing or unauthenticated so a token-less CI run still passes.
"""

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
PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}

VALID = """---
name: sample-skill
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
    """Real files, real script, minimal environment."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def skill(self, name, text):
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(text)
        return d

    def preflight(self, path, *flags):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.root)}
        return subprocess.run([str(SCRIPT), "preflight", str(path)] + list(flags),
                              capture_output=True, text=True, env=env)

    def test_valid_skill_passes(self):
        r = self.preflight(self.skill("ok", VALID))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK:", r.stdout)
        self.assertIn("frontmatter keys: name description", r.stdout)

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
        r = self.preflight(self.skill("open", "---\nname: x\ndescription: y\n\n# Body\n"))
        self.assertEqual(r.returncode, 12)
        self.assertIn("unterminated", r.stderr)

    def test_non_portable_key_is_code_13(self):
        text = VALID.replace("description:", "triggers: [a, b]\ndescription:")
        r = self.preflight(self.skill("custom", text))
        self.assertEqual(r.returncode, 13)
        self.assertIn("non-portable frontmatter key 'triggers'", r.stderr)

    def test_600_char_description_warns_but_passes(self):
        # Re-derived limit. 29 of 156 installed skills exceed 500 characters, and this
        # repo's own parallel-agents-one-codebase is 780, so 500 cannot be a hard failure.
        long_desc = "Use when " + ("x" * 600)
        text = "---\nname: fat\ndescription: %s\n---\n\n# Body\n" % long_desc
        r = self.preflight(self.skill("fat", text))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stderr, r"WARNING: description is 6\d\d characters")

    def test_600_char_description_is_code_14_under_strict(self):
        long_desc = "Use when " + ("x" * 600)
        text = "---\nname: fat\ndescription: %s\n---\n\n# Body\n" % long_desc
        r = self.preflight(self.skill("fat", text), "--strict")
        self.assertEqual(r.returncode, 14)
        self.assertRegex(r.stderr, r"description is 6\d\d characters; --strict enforces 500")

    def test_description_past_the_hard_cap_is_code_14(self):
        # 1024 is the cap the upstream skills repo validates against.
        text = "---\nname: huge\ndescription: %s\n---\n\n# Body\n" % ("x" * 1100)
        r = self.preflight(self.skill("huge", text))
        self.assertEqual(r.returncode, 14)
        self.assertIn("the hard limit is 1024", r.stderr)

    def test_600_line_body_warns_but_passes(self):
        body = "\n".join("line %d" % i for i in range(600))
        r = self.preflight(self.skill("longbody", VALID + body + "\n"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stderr, r"WARNING: body is 6\d\d lines")

    def test_600_line_body_is_code_16_under_strict(self):
        body = "\n".join("line %d" % i for i in range(600))
        r = self.preflight(self.skill("longbody", VALID + body + "\n"), "--strict")
        self.assertEqual(r.returncode, 16)
        self.assertRegex(r.stderr, r"body is 6\d\d lines; --strict enforces 500")

    def test_unquoted_colon_in_description_is_rejected(self):
        # This is the failure that loads the skill with empty metadata and no error.
        text = "---\nname: broken\ndescription: Use when broken: it will not parse.\n---\n\n# B\n"
        r = self.preflight(self.skill("broken", text))
        self.assertEqual(r.returncode, 12)
        self.assertIn("unquoted", r.stderr)

    def test_quoted_colon_in_description_is_accepted(self):
        text = '---\nname: fine\ndescription: "Use when fine: quoting fixes it."\n---\n\n# B\n'
        r = self.preflight(self.skill("fine", text))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_other_files_in_the_skill_directory_are_listed(self):
        # A copy step that takes only SKILL.md silently drops these.
        d = self.skill("multi", VALID)
        (d / "scripts").mkdir()
        (d / "scripts" / "run.py").write_text("print('hi')\n")
        (d / "LICENSE.txt").write_text("license\n")
        r = self.preflight(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LICENSE.txt", r.stdout)
        self.assertIn("scripts/run.py", r.stdout)

    def test_oversize_frontmatter_is_code_15(self):
        # Every key portable and the description legal, but the block as a whole too big.
        pad = "\n".join("  - filler value %03d that pushes the block past the hard cap" % i
                        for i in range(30))
        text = ("---\nname: bulky\ndescription: Use when testing the frontmatter cap.\n"
                "metadata:\n%s\n---\n\n# Body\n" % pad)
        r = self.preflight(self.skill("bulky", text))
        self.assertEqual(r.returncode, 15)
        self.assertIn("the hard limit is 1536", r.stderr)

    def test_missing_name_is_code_17(self):
        r = self.preflight(self.skill("anon", "---\ndescription: Use when nameless.\n---\n\n# B\n"))
        self.assertEqual(r.returncode, 17)
        self.assertIn("required frontmatter field missing: name", r.stderr)


INSTALLED = Path.home() / ".claude" / "skills" / "parallel-agents-one-codebase"


class RealWorldSkillTest(unittest.TestCase):
    """The limits have to accept skills that actually ship, or nobody can use them."""

    @unittest.skipUnless(INSTALLED.is_dir(), "parallel-agents-one-codebase is not installed")
    def test_a_real_installed_skill_passes_preflight(self):
        r = subprocess.run([str(SCRIPT), "preflight", str(INSTALLED)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        # Its description is 780 characters. A 500-char hard cap would reject it.
        self.assertRegex(r.stdout, r"description: \d{3,} chars")


class ShippedSkillTest(unittest.TestCase):
    """The skill this repo ships must satisfy the checker this repo ships."""

    SKILL_DIR = REPO / "skills" / "contribute-skill"

    def test_frontmatter_uses_only_portable_keys(self):
        text = (self.SKILL_DIR / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        block = text.split("---\n", 2)[1]
        keys = set(re.findall(r"^([A-Za-z][A-Za-z0-9_-]*):", block, re.M))
        self.assertTrue(keys, "frontmatter parsed to no keys at all")
        self.assertTrue(keys <= PORTABLE_KEYS, "non-portable keys: %s" % (keys - PORTABLE_KEYS))

    def test_it_passes_its_own_preflight(self):
        r = subprocess.run([str(SCRIPT), "preflight", str(self.SKILL_DIR)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_description_is_a_trigger_clause(self):
        text = (self.SKILL_DIR / "SKILL.md").read_text()
        desc = re.search(r"^description: (.+)$", text, re.M).group(1)
        self.assertTrue(desc.startswith('"') and desc.endswith('"'),
                        "the description must be quoted so a colon cannot break the YAML")
        desc = desc[1:-1]
        self.assertTrue(desc.startswith("Use when"), desc[:60])
        self.assertIn("Do NOT use", desc)
        self.assertLessEqual(len(desc), 500)

    def test_frontmatter_is_parseable_yaml(self):
        yaml = None
        try:
            import yaml  # noqa: F811
        except ImportError:
            self.skipTest("PyYAML not installed")
        text = (self.SKILL_DIR / "SKILL.md").read_text()
        data = yaml.safe_load(text.split("---\n")[1])
        self.assertIsInstance(data, dict)
        self.assertIsInstance(data.get("description"), str)
        self.assertTrue(set(data) <= PORTABLE_KEYS)

    def test_writes_are_gated_after_the_consent_checklist(self):
        # B2/B3: no network write may appear before the gates in the document order.
        text = (self.SKILL_DIR / "SKILL.md").read_text()
        gates = text.index("## 4. Consent gates")
        for write in ("gh repo fork", "gh pr create", "gh repo sync"):
            first = text.find(write)
            if first != -1:
                self.assertGreater(first, gates,
                                   "%r appears before the consent gates" % write)

    def test_dry_run_is_not_claimed_to_be_read_only(self):
        # B3: gh pr create --dry-run "may still push git changes".
        text = (self.SKILL_DIR / "SKILL.md").read_text()
        self.assertIn("may still push git changes", text)
        self.assertNotIn("without opening anything", text)

    def test_the_whole_skill_directory_is_copied(self):
        text = (self.SKILL_DIR / "SKILL.md").read_text()
        self.assertIn("cp -R", text)

    def test_no_em_dashes_anywhere(self):
        for p in [self.SKILL_DIR / "SKILL.md", SCRIPT,
                  REPO / "CONTRIBUTING.md", REPO / ".github" / "PULL_REQUEST_TEMPLATE.md"]:
            self.assertNotIn("—", p.read_text(), "em-dash in %s" % p)


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

    def test_unknown_command_is_a_usage_error(self):
        r = subprocess.run([str(SCRIPT), "frobnicate"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown command", r.stderr)

    def test_dedup_without_a_name_is_a_usage_error(self):
        r = subprocess.run([str(SCRIPT), "dedup"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


@unittest.skipUnless(LIVE, "gh is missing or unauthenticated; live GitHub reads skipped")
class LiveDedupTest(unittest.TestCase):
    """Real calls against real repos with real pull request history.

    These inherit the ambient environment on purpose: gh needs its own config and
    credentials, and pointing HOME at a temp dir would only test the unauthenticated path.
    anthropics/skills is the fixture for the tree and file probes because it is a real
    skills repo with shipped skills, open proposals, and declined ones. cli/cli is the
    fixture for state coverage because it has thousands of pull requests in every state.
    """

    ROW = re.compile(r"^(proposal|touch|mention|fuzzy)\s+(OPEN|CLOSED|MERGED)\s")

    def dedup(self, *args, **kw):
        repo = kw.pop("repo", LIVE_REPO)
        return subprocess.run([str(SCRIPT), "dedup"] + list(args) + ["--repo", repo],
                              capture_output=True, text=True)

    def rows(self, stdout):
        return [ln.split() for ln in stdout.splitlines() if self.ROW.match(ln)]

    # ---------------------------------------------------------------- B1: tree probe

    def test_a_skill_that_already_ships_upstream_is_not_clean(self):
        # B1. internal-comms ships in anthropics/skills, and no pull request search
        # finds it. Before the tree probe this returned CLEAN with rc 0.
        r = self.dedup("internal-comms", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 9, r.stdout[-800:])
        self.assertIn("ALREADY UPSTREAM", r.stdout)
        self.assertNotIn("CLEAN", r.stdout)

    def test_the_tree_probe_reads_the_upstream_name_frontmatter(self):
        # The SKILL.md claims layer 1 checks `name:` frontmatter. Make that true.
        r = self.dedup("internal-comms", repo=SKILLS_REPO)
        self.assertIn("frontmatter declares name: internal-comms", r.stdout)

    def test_a_name_absent_from_the_tree_is_not_reported_as_upstream(self):
        r = self.dedup("zzqqx-nonexistent-skill-name", repo=SKILLS_REPO)
        self.assertNotEqual(r.returncode, 9)
        self.assertNotIn("ALREADY UPSTREAM", r.stdout)

    # ------------------------------------------------- B4: proposal versus mention

    def test_a_declined_proposal_still_blocks_with_code_5(self):
        # anthropics/skills#1407 added skills/macho/SKILL.md and was closed unmerged.
        r = self.dedup("macho", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 5, r.stdout[-800:])
        self.assertIn("BLOCKED", r.stdout)
        kinds = {row[0] for row in self.rows(r.stdout)}
        self.assertIn("proposal", kinds)

    def test_a_typo_fix_is_not_reported_as_a_rejection(self):
        # B4. canvas-design is only ever touched by edit-sized pull requests such as
        # #411 and #1543. It must never produce the rejection block.
        r = self.dedup("canvas-design", repo=SKILLS_REPO)
        self.assertNotIn("BLOCKED", r.stdout)
        self.assertNotEqual(r.returncode, 5)

    def test_a_title_mention_asks_rather_than_blocking(self):
        # anthropics/skills#1036 is titled "Add: designlang skill" but adds the file at
        # skills/skills/designlang/SKILL.md, so it is a mention, not a proposal.
        r = self.dedup("designlang", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 3, r.stdout[-800:])
        self.assertIn("ASK THE USER", r.stdout)
        kinds = {row[0] for row in self.rows(r.stdout)}
        self.assertNotIn("proposal", kinds)

    def test_an_open_proposal_stops_with_code_4(self):
        r = self.dedup("presentation-chef", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 4, r.stdout[-800:])
        self.assertIn("STOP", r.stdout)

    def test_override_rejected_downgrades_the_block(self):
        r = self.dedup("macho", "--override-rejected", repo=SKILLS_REPO)
        self.assertIn(r.returncode, (3, 4), r.stdout[-800:])
        self.assertIn("OVERRIDE", r.stdout)

    # --------------------------------------------------------- B5: archived upstream

    def test_an_archived_upstream_gets_its_own_exit_code(self):
        # B5. google/tink is archived and rejects writes, so a clean rc 0 was wrong.
        r = self.dedup("anything", repo="google/tink")
        self.assertEqual(r.returncode, 18, r.stdout + r.stderr)
        self.assertIn("archived", r.stderr)

    # ----------------------------------------------------------------- state coverage

    def test_state_all_sweep_returns_merged_and_closed(self):
        r = self.dedup("extension")
        states = {row[1] for row in self.rows(r.stdout)}
        self.assertIn("MERGED", states, r.stdout[:2000])
        self.assertIn("CLOSED", states, r.stdout[:2000])

    def test_fuzzy_only_match_asks_the_user_with_code_3(self):
        r = self.dedup("zzqqx-nonexistent-skill-name",
                       "--description", "codespaces machine listing alongside repository visibility settings")
        self.assertEqual(r.returncode, 3, r.stdout[-800:])
        self.assertIn("ASK THE USER", r.stdout)
        kinds = {row[0] for row in self.rows(r.stdout)}
        self.assertEqual(kinds, {"fuzzy"})

    def test_sub_threshold_rows_are_shown_not_hidden(self):
        r = self.dedup("zzqqx-nonexistent-skill-name",
                       "--description", "codespaces machine listing alongside repository visibility settings")
        bands = {row[3] for row in self.rows(r.stdout)}
        self.assertIn("below", bands, "sub-threshold fuzzy hits must still be printed")
        self.assertIn("shown but not counted", r.stdout)

    def test_no_match_is_clean(self):
        r = self.dedup("zzqqx-nonexistent-skill-name")
        self.assertEqual(r.returncode, 0, r.stdout[-800:])
        self.assertIn("CLEAN", r.stdout)

    def test_search_index_lag_is_disclosed(self):
        r = self.dedup("zzqqx-nonexistent-skill-name")
        self.assertIn("search index lags", r.stdout)

    def test_unknown_repo_fails_loudly_rather_than_looking_clean(self):
        r = self.dedup("anything", repo="ContextLab/no-such-repo-zzqqx")
        self.assertEqual(r.returncode, 8, r.stdout + r.stderr)
        self.assertIn("could not resolve", r.stderr)


@unittest.skipUnless(LIVE, "gh is missing or unauthenticated; live GitHub reads skipped")
class LiveWhoamiTest(unittest.TestCase):

    def test_reports_a_role_and_an_identity(self):
        r = subprocess.run([str(SCRIPT), "whoami", "--repo", LIVE_REPO],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        role = re.search(r"^role:\s+(\w+)$", r.stdout, re.M).group(1)
        self.assertIn(role, ("maintainer", "contributor"))
        self.assertRegex(r.stdout, re.compile(r"^acting as:\s+\S+$", re.M))
        self.assertRegex(r.stdout, re.compile(r"^archived:\s+(true|false)$", re.M))

    def test_a_repo_the_user_cannot_push_to_takes_the_fork_path(self):
        # cli/cli is not writable by an ordinary account, so the fork path is correct.
        r = subprocess.run([str(SCRIPT), "whoami", "--repo", LIVE_REPO],
                           capture_output=True, text=True)
        self.assertIn("fork the repo", r.stdout)

    def test_permission_level_is_reported_not_just_collaborator_status(self):
        # The bare collaborators/<user> endpoint answers 204 for read-only collaborators
        # too, which would wrongly read as maintainer. The permission level is the answer.
        r = subprocess.run([str(SCRIPT), "whoami", "--repo", LIVE_REPO],
                           capture_output=True, text=True)
        self.assertRegex(r.stdout, re.compile(r"^permission: \S+", re.M))
        self.assertNotIn("Must have push access", r.stdout)

    def test_archived_upstream_exits_18(self):
        r = subprocess.run([str(SCRIPT), "whoami", "--repo", "google/tink"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 18, r.stdout + r.stderr)
        self.assertIn("archived:  true", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
