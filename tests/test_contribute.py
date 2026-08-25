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

    def preflight(self, path):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.root)}
        return subprocess.run([str(SCRIPT), "preflight", str(path)],
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

    def test_600_char_description_is_code_14(self):
        long_desc = "Use when " + ("x" * 600)
        text = "---\nname: fat\ndescription: %s\n---\n\n# Body\n" % long_desc
        r = self.preflight(self.skill("fat", text))
        self.assertEqual(r.returncode, 14)
        self.assertRegex(r.stderr, r"description is 6\d\d characters; the limit is 500")

    def test_600_line_body_is_code_16(self):
        body = "\n".join("line %d" % i for i in range(600))
        r = self.preflight(self.skill("longbody", VALID + body + "\n"))
        self.assertEqual(r.returncode, 16)
        self.assertRegex(r.stderr, r"body is 6\d\d lines; the limit is 500")

    def test_oversize_frontmatter_is_code_15(self):
        # Every key portable and the description legal, but the block as a whole too big.
        pad = "\n".join("  - filler value %03d that pushes the block past 1024 bytes" % i
                        for i in range(20))
        text = ("---\nname: bulky\ndescription: Use when testing the frontmatter cap.\n"
                "metadata:\n%s\n---\n\n# Body\n" % pad)
        r = self.preflight(self.skill("bulky", text))
        self.assertEqual(r.returncode, 15)
        self.assertIn("the limit is 1024", r.stderr)

    def test_missing_name_is_code_17(self):
        r = self.preflight(self.skill("anon", "---\ndescription: Use when nameless.\n---\n\n# B\n"))
        self.assertEqual(r.returncode, 17)
        self.assertIn("required frontmatter field missing: name", r.stderr)


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
        self.assertTrue(desc.startswith("Use when"), desc[:60])
        self.assertIn("Do NOT use", desc)
        self.assertLessEqual(len(desc), 500)

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
    """Real calls against a real repo with real pull request history.

    These inherit the ambient environment on purpose: gh needs its own config and
    credentials, and pointing HOME at a temp dir would only test the unauthenticated path.
    """

    def dedup(self, *args):
        return subprocess.run([str(SCRIPT), "dedup"] + list(args) + ["--repo", LIVE_REPO],
                              capture_output=True, text=True)

    ROW = re.compile(r"^(exact|fuzzy)\s+(OPEN|CLOSED|MERGED)\s")

    def rows(self, stdout):
        return [ln.split() for ln in stdout.splitlines() if self.ROW.match(ln)]

    def test_state_all_sweep_returns_merged_and_closed(self):
        # The point of the closed-pull-request dedup layer: a --state all sweep has to
        # surface MERGED and CLOSED records, not just OPEN ones.
        r = self.dedup("extension")
        states = {row[1] for row in self.rows(r.stdout)}
        self.assertIn("MERGED", states, r.stdout[:2000])
        self.assertIn("CLOSED", states, r.stdout[:2000])

    def test_exact_match_on_closed_pr_blocks_with_code_5(self):
        r = self.dedup("extension")
        self.assertEqual(r.returncode, 5, r.stdout[-800:])
        self.assertIn("BLOCKED", r.stdout)

    def test_override_rejected_downgrades_the_block(self):
        r = self.dedup("extension", "--override-rejected")
        self.assertIn(r.returncode, (3, 4), r.stdout[-800:])
        self.assertIn("OVERRIDE", r.stdout)

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

    def test_no_match_is_clean(self):
        r = self.dedup("zzqqx-nonexistent-skill-name")
        self.assertEqual(r.returncode, 0, r.stdout[-800:])
        self.assertIn("CLEAN", r.stdout)
        self.assertIn("No matching pull request in any state.", r.stdout)

    def test_search_index_lag_is_disclosed(self):
        r = self.dedup("zzqqx-nonexistent-skill-name")
        self.assertIn("search index lags", r.stdout)

    def test_unknown_repo_fails_loudly_rather_than_looking_clean(self):
        r = subprocess.run([str(SCRIPT), "dedup", "anything",
                            "--repo", "ContextLab/no-such-repo-zzqqx"],
                           capture_output=True, text=True)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
