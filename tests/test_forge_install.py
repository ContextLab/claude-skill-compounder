#!/usr/bin/env python3
"""A forge that closes must leave the skill it forged actually usable.

Every test here drives the real `skillforge` CLI as a subprocess against a real temp
state directory, a real temp skills directory and real files on disk. Nothing is
mocked; the assertions read the filesystem back.

The gap these cover: `skills/<name>/SKILL.md` was written by the forging session and
never linked into the skills directory, because only the installer created those links
and it had last run before the skill existed. `Skill(name)` then answered
`Unknown skill: name` for a skill that had passed a ten-round red-team loop.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"
PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

SKILL_BODY = """---
name: %s
description: Use when a probe needs a real SKILL.md on disk. Do NOT use otherwise.
---

# %s

A real file, written by a real test.
"""


class ForgeInstallCase(unittest.TestCase):
    """A temp state dir, a temp skills destination, and a temp 'project' to forge in."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.dest = self.root / "claude" / "skills"     # stands in for ~/.claude/skills
        self.dest.mkdir(parents=True)
        self.proj = self.root / "project"
        self.proj.mkdir()

    def tearDown(self):
        # A test that made the destination read-only must not break the cleanup.
        for p in (self.dest, self.dest.parent):
            try:
                p.chmod(0o755)
            except OSError:
                pass
        self.tmp.cleanup()

    def run_cli(self, *args, **kw):
        cwd = kw.pop("cwd", self.proj)
        env = {"PATH": PATH, "HOME": str(self.root / "home"),
               "SKILL_COMPOUNDER_STATE": str(self.state),
               "SKILLFORGE_SKILLS_DIR": str(self.dest)}
        env.update(kw.pop("env", {}))
        return subprocess.run([str(CLI), *args], capture_output=True, text=True,
                              cwd=str(cwd), env=env, stdin=subprocess.DEVNULL)

    def author(self, name, where="skills", root=None):
        """Write a real skill the way a forging session would."""
        d = (root or self.proj) / where / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(SKILL_BODY % (name, name), encoding="utf-8")
        return d

    def forge(self, name, steps="4", summary="a real forge", *extra, **kw):
        r = self.run_cli("start", name, steps, summary, *extra, **kw)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def link(self, name):
        return self.dest / name


class DoneInstallsTheSkill(ForgeInstallCase):

    def test_done_links_the_forged_skill_into_the_skills_directory(self):
        """The whole point: after `done`, the skill is where Claude Code looks."""
        src = self.author("probe-alpha")
        self.forge("probe-alpha")
        r = self.run_cli("done", "clean red-team pass")
        self.assertEqual(r.returncode, 0, r.stderr)

        dst = self.link("probe-alpha")
        self.assertTrue(dst.is_symlink(), "no link was created: %s" % r.stdout)
        self.assertEqual(os.path.realpath(str(dst)), os.path.realpath(str(src)))
        self.assertTrue((dst / "SKILL.md").is_file(), "the link does not resolve")

    def test_done_says_what_it_installed(self):
        """A silent link is as bad as a silent failure."""
        self.author("probe-report")
        self.forge("probe-report")
        r = self.run_cli("done")
        self.assertIn("probe-report", r.stdout)
        self.assertIn(str(self.link("probe-report")), r.stdout,
                      "done did not name the destination it installed to")

    def test_a_forge_that_authored_no_skill_says_so_and_installs_nothing(self):
        """Not every forge writes a skill; a fix or a red-team round does not."""
        self.forge("probe-nothing")
        r = self.run_cli("done")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.link("probe-nothing").exists())
        self.assertFalse(self.link("probe-nothing").is_symlink())
        self.assertIn("nothing was installed", r.stdout.lower(),
                      "a forge that installed nothing must say so: %r" % r.stdout)


class LocationIsKnownAtDoneTime(ForgeInstallCase):

    def test_skill_dir_recorded_at_start_is_used_at_done(self):
        """A skill outside the conventional layout is found because start recorded it."""
        src = self.root / "elsewhere" / "probe-recorded"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text(SKILL_BODY % ("probe-recorded", "probe-recorded"), encoding="utf-8")
        self.forge("probe-recorded", "4", "summary", "--skill-dir", str(src))
        self.assertEqual(json.loads(self.run_cli("show").stdout)["skill_dir"], str(src))

        r = self.run_cli("done")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.path.realpath(str(self.link("probe-recorded"))),
                         os.path.realpath(str(src)))

    def test_a_start_that_predates_the_change_still_installs(self):
        """An in-flight forge whose record has no skill_dir and no root."""
        src = self.author("probe-legacy")
        forge_dir = self.state / "forge"
        forge_dir.mkdir(parents=True, exist_ok=True)
        (forge_dir / "probe-legacy.forge.json").write_text(json.dumps({
            "name": "probe-legacy", "summary": "old record", "phase": "initializing",
            "step": 0, "steps": 4, "status": "active", "started": 1, "updated": 1,
            "id": "1.1.11",
        }), encoding="utf-8")

        r = self.run_cli("done")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.path.realpath(str(self.link("probe-legacy"))),
                         os.path.realpath(str(src)))

    def test_a_skill_authored_outside_any_repo_is_found_from_the_working_directory(self):
        """No git repo anywhere: the working directory is the only anchor there is."""
        loose = self.root / "loose"
        loose.mkdir()
        src = self.author("probe-loose", root=loose)
        self.forge("probe-loose", cwd=loose)
        r = self.run_cli("done", cwd=loose)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.path.realpath(str(self.link("probe-loose"))),
                         os.path.realpath(str(src)))

    def test_a_skill_dir_that_holds_no_skill_is_reported_not_ignored(self):
        empty = self.root / "empty-dir"
        empty.mkdir()
        self.forge("probe-empty", "4", "summary", "--skill-dir", str(empty))
        r = self.run_cli("done")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.link("probe-empty").is_symlink())
        self.assertIn("SKILL.md", r.stdout + r.stderr)


class NeverClobbersWhatIsAlreadyThere(ForgeInstallCase):

    def test_a_real_directory_the_user_owns_is_left_untouched(self):
        mine = self.dest / "probe-mine"
        mine.mkdir()
        (mine / "SKILL.md").write_text("MY OWN SKILL", encoding="utf-8")
        self.author("probe-mine")
        self.forge("probe-mine")
        r = self.run_cli("done")

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(mine.is_symlink(), "the user's own directory was replaced")
        self.assertEqual((mine / "SKILL.md").read_text(encoding="utf-8"), "MY OWN SKILL")
        self.assertIn("NOT INSTALLED", r.stdout + r.stderr,
                      "a refused install must say so loudly: %r" % (r.stdout + r.stderr))

    def test_a_link_of_the_users_own_into_their_dotfiles_is_left_untouched(self):
        dotfiles = self.root / "dotfiles" / "probe-theirs"
        dotfiles.mkdir(parents=True)
        (dotfiles / "SKILL.md").write_text("THEIR VERSION", encoding="utf-8")
        (self.dest / "probe-theirs").symlink_to(str(dotfiles))

        self.author("probe-theirs")
        self.forge("probe-theirs")
        r = self.run_cli("done")
        self.assertEqual(os.path.realpath(str(self.link("probe-theirs"))),
                         os.path.realpath(str(dotfiles)),
                         "the user's own link was repointed at our skill")
        self.assertIn("NOT INSTALLED", r.stdout + r.stderr)

    def test_a_dangling_link_that_is_not_ours_is_left_alone_and_reported(self):
        (self.dest / "probe-dangle").symlink_to(str(self.root / "gone" / "probe-dangle"))
        self.author("probe-dangle")
        self.forge("probe-dangle")
        r = self.run_cli("done")

        dst = self.link("probe-dangle")
        self.assertTrue(dst.is_symlink())
        self.assertFalse(dst.exists(), "a foreign dangling link was adopted and replaced")
        self.assertIn("NOT INSTALLED", r.stdout + r.stderr)

    def test_a_read_only_skills_directory_fails_loudly_without_a_traceback(self):
        self.author("probe-readonly")
        self.forge("probe-readonly")
        self.dest.chmod(0o555)
        try:
            r = self.run_cli("done")
        finally:
            self.dest.chmod(0o755)
        both = r.stdout + r.stderr
        self.assertNotIn("Traceback", both)
        self.assertIn("NOT INSTALLED", both, both)
        self.assertFalse(self.link("probe-readonly").exists())


class SaysOnlyWhatIsTrue(ForgeInstallCase):
    """Every one of these was a message that read like success while being false. A
    silent failure and a confident wrong sentence cost the same thing: the user stops
    looking."""

    def test_the_name_that_answers_is_the_directory_name_not_the_forge_name(self):
        """Claude Code resolves a skill by its directory. A forge called `typo-name`
        pointed at `.../real-name` installs `real-name`, and saying otherwise promises a
        skill that will answer `Unknown skill` forever."""
        src = self.author("real-name")
        self.forge("typo-name", "4", "summary", "--skill-dir", str(src))
        r = self.run_cli("done")

        self.assertTrue(self.link("real-name").is_symlink())
        self.assertFalse(self.link("typo-name").exists())
        self.assertIn("real-name", r.stdout)
        self.assertIn("typo-name", r.stdout, "the mismatch itself must be reported")
        self.assertNotIn("installed 'typo-name'", r.stdout)

    def test_a_forge_that_wrote_nothing_does_not_claim_the_users_skill_as_its_own(self):
        mine = self.dest / "probe-unrelated"
        mine.mkdir()
        (mine / "SKILL.md").write_text("MY OWN SKILL", encoding="utf-8")
        self.forge("probe-unrelated")
        r = self.run_cli("done")
        self.assertIn("nothing was installed", r.stdout.lower(), r.stdout)
        self.assertIn("did not put it there", r.stdout, r.stdout)

    def test_a_read_only_destination_is_not_blamed_on_the_name(self):
        """"Free the name" for a name that is free sends the user to do something that
        changes nothing and then fails again."""
        self.author("probe-ro")
        self.forge("probe-ro")
        self.dest.chmod(0o555)
        try:
            r = self.run_cli("done")
        finally:
            self.dest.chmod(0o755)
        self.assertIn("NOT INSTALLED", r.stdout + r.stderr)
        self.assertNotIn("Free that name", r.stdout + r.stderr)

    def test_a_tab_in_the_forge_name_still_finds_the_skill(self):
        """The forge index is US-separated precisely so a tab in a name round-trips.
        Installing off the printable form of the name looked for a directory nobody
        had written, and reported it missing."""
        name = "probe\ttab"
        src = self.author(name)
        self.forge(name)
        r = self.run_cli("done")
        self.assertTrue(self.link(name).is_symlink(), r.stdout + r.stderr)
        self.assertEqual(os.path.realpath(str(self.link(name))),
                         os.path.realpath(str(src)))

    def test_replacing_an_earlier_link_of_ours_is_reported(self):
        first = self.author("probe-moved")
        self.forge("probe-moved")
        self.run_cli("done")
        second = self.root / "second-checkout" / "skills" / "probe-moved"
        second.mkdir(parents=True)
        (second / "SKILL.md").write_text(SKILL_BODY % ("probe-moved", "probe-moved"),
                                         encoding="utf-8")
        r = self.run_cli("install", "probe-moved", "--skill-dir", str(second))

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.path.realpath(str(self.link("probe-moved"))),
                         os.path.realpath(str(second)))
        self.assertIn(str(first), r.stdout,
                      "the skill that stopped answering to this name was not named")


    def test_a_frontmatter_name_that_disagrees_with_the_directory_is_flagged(self):
        src = self.author("probe-aliased")
        (src / "SKILL.md").write_text(SKILL_BODY % ("something-else", "probe-aliased"),
                                      encoding="utf-8")
        self.forge("probe-aliased")
        r = self.run_cli("done")
        self.assertTrue(self.link("probe-aliased").is_symlink())
        both = r.stdout + r.stderr
        self.assertIn("something-else", both, both)
        self.assertIn("WARNING", both, both)


class Idempotence(ForgeInstallCase):

    def test_forging_a_name_that_is_already_linked_is_a_no_op(self):
        src = self.author("probe-again")
        self.forge("probe-again")
        self.run_cli("done")
        self.forge("probe-again")
        r = self.run_cli("done")

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("NOT INSTALLED", r.stdout + r.stderr)
        self.assertEqual(os.path.realpath(str(self.link("probe-again"))),
                         os.path.realpath(str(src)))
        self.assertEqual(len(list(self.dest.iterdir())), 1)

    def test_closing_the_same_forge_twice_neither_errors_nor_duplicates(self):
        src = self.author("probe-twice")
        self.forge("probe-twice")
        self.run_cli("done")
        r = self.run_cli("done")

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.path.realpath(str(self.link("probe-twice"))),
                         os.path.realpath(str(src)))
        ledger = [json.loads(l) for l in
                  (self.state / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
                  if l.strip()]
        self.assertEqual(len([e for e in ledger if e.get("event") == "done"]), 1)

    def test_the_link_is_recorded_so_uninstall_can_recognise_it(self):
        self.author("probe-manifest")
        self.forge("probe-manifest")
        self.run_cli("done")
        manifest = json.loads((self.state / "install-manifest.json")
                              .read_text(encoding="utf-8"))
        self.assertIn(str(self.link("probe-manifest")), manifest.get("links", {}))


class ProjectLocalSkills(ForgeInstallCase):

    def test_a_project_local_skill_stays_project_scoped_and_says_so(self):
        """`<repo>/.claude/skills/<name>` is already loaded for that project. Linking it
        into the personal directory would silently widen a scope its author chose."""
        self.author("probe-project", where=".claude/skills")
        self.forge("probe-project")
        r = self.run_cli("done")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.link("probe-project").exists())
        self.assertIn("project", r.stdout.lower(), r.stdout)

    def test_an_explicit_skill_dir_installs_a_project_local_skill_anyway(self):
        src = self.author("probe-explicit", where=".claude/skills")
        self.forge("probe-explicit", "4", "summary", "--skill-dir", str(src))
        r = self.run_cli("done")
        self.assertEqual(os.path.realpath(str(self.link("probe-explicit"))),
                         os.path.realpath(str(src)), r.stdout)


class ManualInstallCommand(ForgeInstallCase):
    """`skillforge install` is the retry path after a refusal, and the repair path for a
    forge that was closed before this mechanism existed."""

    def test_install_links_a_named_skill(self):
        src = self.author("probe-manual")
        r = self.run_cli("install", "probe-manual")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.path.realpath(str(self.link("probe-manual"))),
                         os.path.realpath(str(src)))

    def test_install_is_idempotent(self):
        self.author("probe-manual2")
        self.run_cli("install", "probe-manual2")
        r = self.run_cli("install", "probe-manual2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("NOT INSTALLED", r.stdout + r.stderr)

    def test_install_refuses_a_name_the_user_owns(self):
        mine = self.dest / "probe-manual3"
        mine.mkdir()
        (mine / "SKILL.md").write_text("MINE", encoding="utf-8")
        self.author("probe-manual3")
        r = self.run_cli("install", "probe-manual3")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((mine / "SKILL.md").read_text(encoding="utf-8"), "MINE")


class InstallerApi(unittest.TestCase):
    """link_skill() reuses the installer's own four-proof ownership judgement."""

    def setUp(self):
        sys.path.insert(0, str(REPO))
        from skill_compounder import installer
        self.installer = installer
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.skills = self.root / "skills-dest"
        self.skills.mkdir()
        self.state = self.root / "state"
        self.state.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, name):
        d = self.root / "src" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(SKILL_BODY % (name, name), encoding="utf-8")
        return d

    def test_link_skill_reports_linked_then_already_linked(self):
        src = self.make("api-a")
        first = self.installer.link_skill(src, self.skills, app_home=REPO,
                                          state_dir=self.state)
        second = self.installer.link_skill(src, self.skills, app_home=REPO,
                                           state_dir=self.state)
        self.assertEqual(first["status"], "linked")
        self.assertEqual(second["status"], "already-linked")

    def test_link_skill_refuses_a_foreign_link(self):
        src = self.make("api-b")
        theirs = self.root / "theirs"
        theirs.mkdir()
        (self.skills / "api-b").symlink_to(str(theirs))
        out = self.installer.link_skill(src, self.skills, app_home=REPO,
                                        state_dir=self.state)
        self.assertEqual(out["status"], "refused")
        self.assertEqual(os.path.realpath(str(self.skills / "api-b")),
                         os.path.realpath(str(theirs)))

    def test_link_skill_names_the_link_it_replaced(self):
        one = self.make("api-d")
        two = self.root / "other" / "api-d"
        two.mkdir(parents=True)
        (two / "SKILL.md").write_text(SKILL_BODY % ("api-d", "api-d"), encoding="utf-8")
        self.installer.link_skill(one, self.skills, app_home=REPO, state_dir=self.state)
        out = self.installer.link_skill(two, self.skills, app_home=REPO,
                                        state_dir=self.state)
        self.assertEqual(out["status"], "linked")
        self.assertEqual(out["displaced"], os.path.normpath(os.path.abspath(str(one))))

    def test_link_skill_rejects_a_directory_with_no_skill_md(self):
        empty = self.root / "src" / "api-c"
        empty.mkdir(parents=True)
        with self.assertRaises(self.installer.InstallError):
            self.installer.link_skill(empty, self.skills, app_home=REPO,
                                      state_dir=self.state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
