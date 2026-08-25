#!/usr/bin/env python3
"""Regression tests for six installer defects found by installing for real.

Every one of these was reproduced by running the installer against a realistic
user configuration, never by reading the code. No mocks: real checkouts are
copied and relocated on disk, real ``settings.json`` files are written and read
back, and the end-to-end cases shell out to ``scripts/setup.py``.

The defects, in the order they appear below:

1. Moving or re-cloning the checkout wedged both install and uninstall, leaving
   dangling links forever and blaming the user for them.
2. A symlinked ``settings.json`` was silently replaced by a regular file.
3. A read-only bin directory produced a silent partial install.
4. Uninstall could strand the status-line wrapper and still exit 0.
5. Malformed or oddly-shaped ``settings.json`` produced a raw traceback, and a
   string ``statusLine`` made the package impossible to remove.
6. Cosmetic: repeat-uninstall wording, backup accumulation, dropped statusLine
   siblings.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
APP_HOME = str(Path(__file__).resolve().parent.parent)
APP = Path(APP_HOME)

from skill_compounder import installer


def clone_checkout(dest):
    """A real copy of this checkout, minus the git database (5 MB, not 14)."""
    shutil.copytree(APP_HOME, dest,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "notes"),
                    symlinks=True)
    return Path(dest)


def run_setup(app_home, claude, binn, state, uninstall=False):
    argv = [sys.executable, str(Path(app_home) / "scripts" / "setup.py"),
            "--claude-dir", str(claude), "--bin-dir", str(binn), "--state-dir", str(state)]
    if uninstall:
        argv.append("--uninstall")
    return subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL)


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.claude = self.root / "claude"
        self.bin = self.root / "bin"
        self.state = self.root / "state"
        self.claude.mkdir()
        self.bin.mkdir()
        self.settings = self.claude / "settings.json"

    def tearDown(self):
        # A test that made a directory read-only must not break cleanup.
        for d in (self.bin, self.claude, self.root):
            try:
                d.chmod(0o755)
            except OSError:
                pass
        self.tmp.cleanup()

    def write_settings(self, obj):
        self.settings.write_text(json.dumps(obj, indent=2), encoding="utf-8")

    def read(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def do_install(self, app_home=APP_HOME):
        return installer.install(app_home, str(self.claude), str(self.bin), str(self.state))

    def do_uninstall(self, app_home=APP_HOME):
        return installer.uninstall(app_home, str(self.claude), str(self.bin), str(self.state))

    def dangling(self):
        """Every symlink under the claude and bin dirs whose target does not exist."""
        out = []
        for d in (self.claude / "skills", self.bin):
            if not d.is_dir():
                continue
            for p in sorted(d.iterdir()):
                if p.is_symlink() and not p.exists():
                    out.append(str(p))
        return out


# ------------------------------------------------------------------ defect 1

class MovedCheckoutTest(Base):
    """Install from clone A, move it to B, then drive both commands from B.

    `curl | bash` clones to ~/.claude/skill-compounder-app and the README also
    documents installing from your own clone. Doing one and then the other is
    the documented path into this state.
    """

    def test_install_from_relocated_checkout_relinks_instead_of_refusing(self):
        a = clone_checkout(self.root / "clone-a")
        first = run_setup(a, self.claude, self.bin, self.state)
        self.assertEqual(first.returncode, 0, first.stderr)

        b = self.root / "clone-b"
        a.rename(b)                      # the checkout moved; the links now dangle

        second = run_setup(b, self.claude, self.bin, self.state)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotIn("NOT LINKED", second.stdout,
                         "a link this package made is not 'something you already had'")
        self.assertEqual(self.dangling(), [],
                         "reinstalling from the new location must repoint every link")

        for name in sorted(d.name for d in (b / "skills").iterdir()
                           if (d / "SKILL.md").is_file()):
            link = self.claude / "skills" / name
            self.assertTrue(link.is_symlink(), "%s is not linked" % name)
            self.assertTrue((link / "SKILL.md").is_file(), "%s link is dead" % name)

    def test_uninstall_from_relocated_checkout_cleans_up_its_own_links(self):
        a = clone_checkout(self.root / "clone-a")
        self.assertEqual(run_setup(a, self.claude, self.bin, self.state).returncode, 0)

        b = self.root / "clone-b"
        a.rename(b)

        out = run_setup(b, self.claude, self.bin, self.state, uninstall=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("left in place (not ours)", out.stdout,
                         "our own links must not be disowned because the checkout moved")
        self.assertEqual(self.dangling(), [],
                         "uninstall must not leave dangling links behind")

    def test_two_checkouts_with_no_install_record_still_recognise_each_other(self):
        """`curl | bash` after installing from a clone: both checkouts exist.

        With the state directory deleted there is no manifest, so ownership rests on
        the target living inside a directory that carries this package's own source.
        """
        a = clone_checkout(self.root / "clone-a")
        self.assertEqual(run_setup(a, self.claude, self.bin, self.state).returncode, 0)
        shutil.rmtree(str(self.state))

        b = clone_checkout(self.root / "clone-b")
        out = run_setup(b, self.claude, self.bin, self.state)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("NOT LINKED", out.stdout)
        link = self.claude / "skills" / "skill-compounder"
        self.assertEqual(os.path.realpath(str(link)),
                         os.path.realpath(str(b / "skills" / "skill-compounder")),
                         "the second checkout must take over the link")

    def test_a_users_own_link_is_never_adopted(self):
        """The narrow check exists to protect this. Widening must not break it."""
        theirs = self.root / "dotfiles" / "skill-compounder"
        theirs.mkdir(parents=True)
        (theirs / "SKILL.md").write_text("THEIR OWN SKILL\n", encoding="utf-8")
        (self.claude / "skills").mkdir()
        link = self.claude / "skills" / "skill-compounder"
        link.symlink_to(str(theirs))

        rep = self.do_install()
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.path.realpath(str(link)), os.path.realpath(str(theirs)),
                         "the user's own link was hijacked")
        self.assertIn("NOT LINKED", rep["skills"])

        self.do_uninstall()
        self.assertTrue(link.is_symlink(), "the user's own link was removed by uninstall")
        self.assertEqual(os.path.realpath(str(link)), os.path.realpath(str(theirs)))

    def test_a_users_dangling_link_is_never_adopted(self):
        """A dangling link we cannot prove we made stays exactly where it is."""
        (self.claude / "skills").mkdir()
        link = self.claude / "skills" / "skill-compounder"
        link.symlink_to(str(self.root / "gone" / "skills" / "skill-compounder"))

        self.do_install()
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(str(link)),
                         str(self.root / "gone" / "skills" / "skill-compounder"),
                         "a dangling link of the user's was adopted")
        self.do_uninstall()
        self.assertTrue(link.is_symlink(), "a dangling link of the user's was deleted")


# ------------------------------------------------------------------ defect 2

class SymlinkedSettingsTest(Base):
    """stow / chezmoi / hand-rolled dotfiles all present settings.json as a symlink."""

    def test_symlink_is_written_through_not_replaced(self):
        real = self.root / "dotfiles" / "settings.json"
        real.parent.mkdir(parents=True)
        real.write_text(json.dumps({"model": "opus"}, indent=2), encoding="utf-8")
        self.settings.symlink_to(str(real))

        self.do_install()

        self.assertTrue(self.settings.is_symlink(),
                        "the user's dotfiles symlink was replaced by a regular file")
        self.assertEqual(os.path.realpath(str(self.settings)), os.path.realpath(str(real)))
        written = json.loads(real.read_text(encoding="utf-8"))
        self.assertIn("hooks", written, "the install must land in the dotfiles file")
        self.assertEqual(written["model"], "opus")

    def test_symlink_survives_uninstall_too(self):
        real = self.root / "dotfiles" / "settings.json"
        real.parent.mkdir(parents=True)
        real.write_text(json.dumps({"model": "opus"}, indent=2), encoding="utf-8")
        self.settings.symlink_to(str(real))
        self.do_install()
        self.do_uninstall()
        self.assertTrue(self.settings.is_symlink(),
                        "uninstall replaced the dotfiles symlink with a regular file")
        self.assertNotIn("hooks", json.loads(real.read_text(encoding="utf-8")))


# ------------------------------------------------------------------ defect 3

@unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
class ReadOnlyBinTest(Base):

    def test_unwritable_bin_fails_before_anything_is_applied(self):
        self.write_settings({"model": "opus"})
        self.bin.chmod(0o500)
        try:
            with self.assertRaises(installer.InstallError) as ctx:
                self.do_install()
        finally:
            self.bin.chmod(0o755)
        self.assertIn(str(self.bin), str(ctx.exception),
                      "the message must name the directory it cannot write")

        self.assertEqual(self.read(), {"model": "opus"},
                         "settings must not be changed by a run that failed")
        self.assertFalse((self.claude / "skills").is_dir() and
                         any((self.claude / "skills").iterdir()),
                         "no skill may be linked by a run that failed")

    def test_a_failure_mid_loop_is_reported_against_the_name_it_hit(self):
        """Preflight catches the common case; a race or an ACL can still fail here.

        Reported per name and surfaced as an error, never raised: half an install plus a
        traceback tells the user nothing about which half landed.
        """
        self.bin.chmod(0o500)
        try:
            text, failed = installer._link_all(installer._cli_files(APP_HOME),
                                               self.bin, APP_HOME, {"links": {}})
        finally:
            self.bin.chmod(0o755)
        self.assertIn("NOT INSTALLED", text)
        self.assertIn("skillforge", text)
        self.assertTrue(failed)

    def test_setup_py_reports_the_problem_without_a_traceback(self):
        self.bin.chmod(0o500)
        try:
            out = run_setup(APP_HOME, self.claude, self.bin, self.state)
        finally:
            self.bin.chmod(0o755)
        self.assertNotEqual(out.returncode, 0)
        self.assertNotIn("Traceback", out.stderr, "the user must not see a traceback")
        self.assertIn(str(self.bin), out.stderr + out.stdout)


# ------------------------------------------------------------------ defect 4

class StrandedStatuslineTest(Base):

    def test_uninstall_never_leaves_the_statusline_pointing_at_nothing(self):
        a = clone_checkout(self.root / "clone-a")
        self.assertEqual(run_setup(a, self.claude, self.bin, self.state).returncode, 0)

        b = self.root / "clone-b"
        a.rename(b)
        shutil.rmtree(str(self.state))            # user deleted their runtime state

        out = run_setup(b, self.claude, self.bin, self.state, uninstall=True)
        command = str((self.read().get("statusLine") or {}).get("command", ""))
        self.assertNotIn(str(a), command,
                         "uninstall left statusLine pointing into a checkout that is gone")
        self.assertNotIn("statusline/statusline.sh", command,
                         "our wrapper must not survive uninstall")
        self.assertEqual(out.returncode, 0, out.stderr)


# ------------------------------------------------------------------ defect 5

class MalformedSettingsTest(Base):

    def test_odd_hook_shapes_fail_with_the_offending_key_named(self):
        for bad, key in (([], "hooks"),
                         ("str", "hooks"),
                         (3, "hooks"),
                         ({"PostToolUse": "oops"}, "hooks.PostToolUse"),
                         ({"PostToolUse": [1, 2]}, "hooks.PostToolUse[0]"),
                         ({"PostToolUse": [{"hooks": "oops"}]}, "hooks.PostToolUse[0].hooks")):
            with self.subTest(bad=bad):
                self.write_settings({"model": "opus", "hooks": bad})
                with self.assertRaises(ValueError) as ctx:
                    self.do_install()
                self.assertIn(key, str(ctx.exception),
                              "the message must name the key that is wrong")
                self.assertEqual(self.read(), {"model": "opus", "hooks": bad},
                                 "settings must be left exactly as they were")

    def test_null_hooks_is_treated_as_absent(self):
        self.write_settings({"model": "opus", "hooks": None})
        self.do_install()
        s = self.read()
        self.assertTrue(any("compound-improvement" in h["command"]
                            for g in s["hooks"]["UserPromptSubmit"] for h in g["hooks"]))

    def test_a_string_statusline_can_still_be_installed_over_and_removed(self):
        self.write_settings({"statusLine": "printf my-string-statusline"})
        self.do_install()
        s = self.read()
        self.assertIn("statusline.sh", s["statusLine"]["command"])
        base = (self.state / "statusline-base.sh").read_text(encoding="utf-8")
        self.assertIn("printf my-string-statusline", base,
                      "a string status line must be preserved like an object one")
        self.do_uninstall()
        self.assertEqual(self.read()["statusLine"], "printf my-string-statusline")

    def test_setup_py_prints_a_message_for_a_broken_settings_file(self):
        self.settings.write_text("{ this is not json", encoding="utf-8")
        out = run_setup(APP_HOME, self.claude, self.bin, self.state)
        self.assertNotEqual(out.returncode, 0)
        self.assertNotIn("Traceback", out.stderr)
        self.assertIn("settings.json", out.stderr + out.stdout)


# ------------------------------------------------------------------ defect 6

class CosmeticTest(Base):

    def test_repeat_uninstall_does_not_claim_links_are_not_ours(self):
        self.do_install()
        self.do_uninstall()
        rep = self.do_uninstall()
        self.assertNotIn("not ours", rep["skills"],
                         "a name that is simply absent is not 'not ours'")
        self.assertNotIn("not ours", rep["cli"])

    def test_backups_do_not_accumulate_one_per_run(self):
        """One run per day for a week used to leave seven identical copies.

        The timestamp is second-resolution, so a loop inside one second hides the
        defect; SKILL_COMPOUNDER_NOW pins the clock the way the shell scripts are
        pinned by SKILLFORGE_NOW.
        """
        self.write_settings({"model": "opus"})
        counts = []
        try:
            for day in range(8):
                os.environ["SKILL_COMPOUNDER_NOW"] = str(1767225600 + day * 86400)
                self.do_install()
                counts.append(len(list(
                    self.claude.glob("settings.json.bak-skill-compounder-*"))))
        finally:
            os.environ.pop("SKILL_COMPOUNDER_NOW", None)
        # One backup of the settings as they were, one of the installed state, then
        # nothing more however many times it is run.
        self.assertLessEqual(max(counts), 2, "backups piled up: %s" % counts)
        self.assertEqual(len(set(counts[2:])), 1,
                         "the backup count must stop growing: %s" % counts)

    def test_backups_are_capped(self):
        """Even distinct backups are bounded, and only our own naming is pruned."""
        theirs = self.claude / "settings.json.bak-mine"
        theirs.write_text("keep me", encoding="utf-8")
        self.write_settings({"model": "opus"})
        try:
            for day in range(20):
                os.environ["SKILL_COMPOUNDER_NOW"] = str(1767225600 + day * 86400)
                self.write_settings({"model": "opus", "n": day})
                self.do_install()
        finally:
            os.environ.pop("SKILL_COMPOUNDER_NOW", None)
        backups = sorted(self.claude.glob("settings.json.bak-skill-compounder-*"))
        self.assertLessEqual(len(backups), installer.MAX_BACKUPS)
        self.assertTrue(theirs.exists(), "a backup we did not create was deleted")

    def test_a_second_run_in_the_same_second_does_not_clobber_the_first_backup(self):
        self.write_settings({"model": "opus"})
        os.environ["SKILL_COMPOUNDER_NOW"] = "1767225600"
        try:
            first = Path(self.do_install()["backup"])
            second = Path(self.do_install()["backup"])
        finally:
            os.environ.pop("SKILL_COMPOUNDER_NOW", None)
        self.assertEqual(json.loads(first.read_text(encoding="utf-8")), {"model": "opus"},
                         "the pre-install backup was overwritten by a later run")
        self.assertTrue(second.exists())

    def test_statusline_sibling_keys_survive(self):
        self.write_settings({"statusLine": {"type": "command",
                                            "command": "printf hi",
                                            "padding": 0}})
        self.do_install()
        self.assertEqual(self.read()["statusLine"].get("padding"), 0,
                         "a sibling key of statusLine was dropped")
        self.do_uninstall()
        self.assertEqual(self.read()["statusLine"],
                         {"type": "command", "command": "printf hi", "padding": 0})


# ---------------------------------------------------------- README claim: uninstall

class CurlUninstallTest(Base):
    """`curl … uninstall.sh | bash` after installing from your own clone."""

    def test_uninstall_sh_finds_the_install_when_run_from_nowhere(self):
        a = clone_checkout(self.root / "clone-a")
        self.assertEqual(run_setup(a, self.claude, self.bin, self.state).returncode, 0)

        # Reproduce `curl … | bash`: the script runs with no checkout around it.
        loose = self.root / "loose-uninstall.sh"
        shutil.copy2(str(a / "uninstall.sh"), str(loose))
        env = dict(os.environ)
        env["HOME"] = str(self.root / "fakehome")
        (self.root / "fakehome").mkdir(exist_ok=True)
        env["CLAUDE_SKILL_COMPOUNDER_STATE"] = str(self.state)
        out = subprocess.run(["bash", str(loose),
                              "--claude-dir", str(self.claude),
                              "--bin-dir", str(self.bin),
                              "--state-dir", str(self.state)],
                             capture_output=True, text=True, env=env,
                             stdin=subprocess.DEVNULL)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("can't open file", out.stderr)
        self.assertEqual(self.dangling(), [])
        self.assertNotIn("statusLine", self.read())


# --------------------------------------------- found by a cold review of the above

class ColdReviewTest(Base):
    """Eight further defects, each reproduced before it was fixed."""

    def test_a_settings_file_that_will_not_parse_does_not_trap_the_user(self):
        self.do_install()
        with open(str(self.settings), "a", encoding="utf-8") as fh:
            fh.write('{"hooks": {')
        rep = self.do_uninstall()
        self.assertIn("LEFT ALONE", rep["settings"])
        self.assertIn("errors", rep, "an incomplete uninstall must say so")
        for name in sorted(d.name for d in (APP / "skills").iterdir()
                           if (d / "SKILL.md").is_file()):
            self.assertFalse((self.claude / "skills" / name).is_symlink(),
                             "%s survived an uninstall that could be completed" % name)
        self.assertFalse((self.bin / "skillforge").is_symlink())

    def test_a_name_that_stopped_shipping_does_not_leave_a_dead_link(self):
        a = clone_checkout(self.root / "clone-a")
        self.assertEqual(run_setup(a, self.claude, self.bin, self.state).returncode, 0)
        (a / "bin" / "skillreport").rename(a / "bin" / "skillreport2")
        (a / "skills" / "no-silent-stub").rename(a / "skills" / "no-stub-v2")

        self.assertEqual(run_setup(a, self.claude, self.bin, self.state).returncode, 0)
        self.assertEqual(self.dangling(), [],
                         "an upstream rename left a dead command on PATH")

        out = run_setup(a, self.claude, self.bin, self.state, uninstall=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.dangling(), [])

    def test_uninstall_alone_also_clears_a_renamed_name(self):
        a = clone_checkout(self.root / "clone-a")
        self.assertEqual(run_setup(a, self.claude, self.bin, self.state).returncode, 0)
        (a / "bin" / "skillreport").rename(a / "bin" / "skillreport2")
        out = run_setup(a, self.claude, self.bin, self.state, uninstall=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertFalse((self.bin / "skillreport").is_symlink(),
                         "uninstall enumerated only the current checkout and missed it")

    def test_a_statusline_the_user_deleted_is_not_resurrected(self):
        self.write_settings({"statusLine": {"type": "command",
                                            "command": "printf my-old-one"}})
        self.do_install()
        self.do_uninstall()
        s = self.read()
        del s["statusLine"]                       # the user drops it by hand
        self.write_settings(s)
        self.do_install()
        self.do_uninstall()
        self.assertNotIn("statusLine", self.read(),
                         "a status line the user deleted came back from stale state")
        self.assertFalse((self.state / "statusline-base.sh").exists(),
                         "the wrapper would still run the dead command every second")

    def test_a_dangling_skills_directory_is_caught_before_anything_is_applied(self):
        (self.claude / "skills").symlink_to(str(self.root / "nowhere"))
        with self.assertRaises(installer.InstallError) as ctx:
            self.do_install()
        self.assertIn("nowhere", str(ctx.exception),
                      "the message must name the dangling link, not say 'File exists'")
        self.assertFalse(self.settings.exists(), "settings were written by a failed run")
        self.assertFalse((self.bin / "skillforge").is_symlink(),
                         "CLIs were linked by a run that then reported failure")

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_a_link_uninstall_could_not_remove_is_not_called_not_ours(self):
        self.do_install()
        self.bin.chmod(0o500)
        try:
            rep = self.do_uninstall()
        finally:
            self.bin.chmod(0o755)
        self.assertNotIn("not ours", rep["cli"], "they are ours; saying otherwise is false")
        self.assertIn("OURS BUT NOT REMOVED", rep["cli"])
        self.assertIn("errors", rep)

    def test_a_checkout_with_no_executable_bits_is_refused_with_the_fix(self):
        a = clone_checkout(self.root / "clone-a")
        for p in list((a / "bin").iterdir()) + list((a / "hooks").glob("*.sh")) \
                + list((a / "statusline").glob("*.sh")):
            p.chmod(0o644)
        with self.assertRaises(installer.InstallError) as ctx:
            self.do_install(app_home=str(a))
        self.assertIn("chmod +x", str(ctx.exception))
        self.assertFalse(self.settings.exists(),
                         "a checkout that cannot run must not be half-wired")

    def test_concurrent_installs_agree_on_one_settings_file_and_one_manifest(self):
        procs = [subprocess.Popen(
            [sys.executable, str(APP / "scripts" / "setup.py"),
             "--claude-dir", str(self.claude), "--bin-dir", str(self.bin),
             "--state-dir", str(self.state)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
            for _ in range(6)]
        # communicate() first: waiting on a process whose pipe is unread can deadlock.
        outs = [(p.communicate(), p.returncode) for p in procs]
        for (out, err), code in outs:
            self.assertEqual(code, 0, err.decode("utf-8", "replace"))
            self.assertNotIn(b"NOT INSTALLED", out)
        s = self.read()
        for event in ("UserPromptSubmit", "PostToolUse", "Stop"):
            cmds = [h["command"] for g in s["hooks"][event] for h in g["hooks"]]
            self.assertEqual(len(cmds), len(set(cmds)), "%s duplicated" % event)
        json.loads((self.state / installer.MANIFEST).read_text(encoding="utf-8"))

    def test_an_empty_hook_list_of_the_users_is_left_alone(self):
        self.write_settings({"hooks": {"PostToolUse": [], "PreCompact": []}})
        self.do_install()
        self.do_uninstall()
        s = self.read()
        self.assertEqual(s["hooks"].get("PostToolUse"), [],
                         "a key the user set was deleted by uninstall")
        self.assertEqual(s["hooks"].get("PreCompact"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
