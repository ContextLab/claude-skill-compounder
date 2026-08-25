#!/usr/bin/env python3
"""Real install/uninstall against a real temporary Claude directory.

No mocks: every test writes an actual settings.json, runs the actual installer,
and reads the file back off disk."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
APP_HOME = str(Path(__file__).resolve().parent.parent)
APP = Path(APP_HOME)

from skill_compounder import installer


FOREIGN_HOOK = {"hooks": [{"type": "command", "command": "/usr/bin/python3 /some/other/tool.py"}]}
FOREIGN_STATUSLINE = {"type": "command", "command": 'printf "my original status line"'}


class InstallerTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.claude = root / "claude"
        self.bin = root / "bin"
        self.state = root / "state"
        self.claude.mkdir()
        self.bin.mkdir()
        self.settings = self.claude / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write_settings(self, obj):
        self.settings.write_text(json.dumps(obj, indent=2), encoding="utf-8")

    def read(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def do_install(self):
        return installer.install(APP_HOME, str(self.claude), str(self.bin), str(self.state))

    def do_uninstall(self):
        return installer.uninstall(APP_HOME, str(self.claude), str(self.bin), str(self.state))

    # ------------------------------------------------------------------ basics

    def test_install_into_empty_config(self):
        self.do_install()
        s = self.read()
        ups = s["hooks"]["UserPromptSubmit"]
        ptu = s["hooks"]["PostToolUse"]
        self.assertTrue(any("compound-improvement.sh\" prompt" in h["command"]
                            for g in ups for h in g["hooks"]))
        self.assertTrue(any("compound-improvement.sh\" edit" in h["command"]
                            for g in ptu for h in g["hooks"]))
        self.assertEqual(ptu[0]["matcher"], "Write|Edit")
        self.assertIn("statusline.sh", s["statusLine"]["command"])
        self.assertEqual(s["statusLine"]["refreshInterval"], 1)

    def test_every_shipped_skill_and_cli_is_linked(self):
        """Discovery, not a hardcoded list: adding a seed skill must need no installer edit.

        Asserted against what is actually in the repo, so a skill that ships without
        being installed fails here rather than being noticed by a user.
        """
        self.do_install()
        shipped_skills = sorted(d.name for d in (APP / "skills").iterdir()
                                if (d / "SKILL.md").is_file())
        self.assertTrue(shipped_skills, "the repo must ship at least one skill")
        for name in shipped_skills:
            link = self.claude / "skills" / name
            self.assertTrue(link.is_symlink(), "%s was not linked" % name)
            self.assertTrue((link / "SKILL.md").exists(),
                            "%s symlink must expose SKILL.md" % name)

        shipped_clis = sorted(f.name for f in (APP / "bin").iterdir()
                              if f.is_file() and os.access(str(f), os.X_OK)
                              and not f.name.startswith("."))
        self.assertIn("skillforge", shipped_clis)
        for name in shipped_clis:
            link = self.bin / name
            self.assertTrue(link.is_symlink(), "%s was not linked" % name)
            self.assertTrue(os.access(str(link), os.X_OK),
                            "%s must be executable through the link" % name)

    def test_uninstall_removes_every_link_it_made(self):
        self.do_install()
        self.do_uninstall()
        for d in (APP / "skills").iterdir():
            if (d / "SKILL.md").is_file():
                self.assertFalse((self.claude / "skills" / d.name).is_symlink(),
                                 "%s survived uninstall" % d.name)
        for f in (APP / "bin").iterdir():
            if f.is_file() and os.access(str(f), os.X_OK) and not f.name.startswith("."):
                self.assertFalse((self.bin / f.name).is_symlink(),
                                 "%s survived uninstall" % f.name)

    def test_install_is_idempotent(self):
        self.do_install()
        self.do_install()
        self.do_install()
        s = self.read()
        prompt_hooks = [h for g in s["hooks"]["UserPromptSubmit"] for h in g["hooks"]
                        if "compound-improvement" in h["command"]]
        edit_hooks = [h for g in s["hooks"]["PostToolUse"] for h in g["hooks"]
                      if "compound-improvement" in h["command"]]
        self.assertEqual(len(prompt_hooks), 1, "reinstall must not duplicate the prompt hook")
        self.assertEqual(len(edit_hooks), 1, "reinstall must not duplicate the edit hook")
        stop_hooks = [h for g in s["hooks"].get("Stop", []) for h in g["hooks"]
                      if "insight-capture" in h["command"]]
        self.assertEqual(len(stop_hooks), 1, "reinstall must not duplicate the Stop hook")

    def test_stop_hook_is_wired_and_removed(self):
        self.do_install()
        s = self.read()
        self.assertTrue(any("insight-capture.sh" in h["command"]
                            for g in s["hooks"]["Stop"] for h in g["hooks"]),
                        "insight capture must be wired on Stop")
        self.do_uninstall()
        s = self.read()
        self.assertFalse(any("insight-capture.sh" in h["command"]
                             for g in s.get("hooks", {}).get("Stop", [])
                             for h in g["hooks"]))

    # -------------------------------------------------- coexisting with other tools

    def test_foreign_hooks_survive_install_and_uninstall(self):
        self.write_settings({"hooks": {"UserPromptSubmit": [FOREIGN_HOOK],
                                       "Stop": [FOREIGN_HOOK]}})
        self.do_install()
        s = self.read()
        self.assertTrue(any("other/tool.py" in h["command"]
                            for g in s["hooks"]["UserPromptSubmit"] for h in g["hooks"]))
        self.do_uninstall()
        s = self.read()
        self.assertTrue(any("other/tool.py" in h["command"]
                            for g in s["hooks"]["UserPromptSubmit"] for h in g["hooks"]),
                        "uninstall must not remove another tool's hook")
        self.assertIn("Stop", s["hooks"])

    def test_unrelated_settings_keys_are_untouched(self):
        self.write_settings({"model": "opus", "env": {"FOO": "bar"}})
        self.do_install()
        s = self.read()
        self.assertEqual(s["model"], "opus")
        self.assertEqual(s["env"], {"FOO": "bar"})

    # -------------------------------------------------------------- status line

    def test_existing_statusline_is_preserved_and_restored(self):
        self.write_settings({"statusLine": FOREIGN_STATUSLINE})
        self.do_install()
        base = self.state / "statusline-base.sh"
        self.assertTrue(base.exists(), "previous status line must be saved")
        self.assertIn("my original status line", base.read_text(encoding="utf-8"))
        self.assertTrue(os.access(str(base), os.X_OK), "saved base must be executable")

        self.do_uninstall()
        self.assertEqual(self.read()["statusLine"], FOREIGN_STATUSLINE)

    def test_no_statusline_before_means_none_after_uninstall(self):
        self.write_settings({"model": "opus"})
        self.do_install()
        self.assertIn("statusLine", self.read())
        self.do_uninstall()
        self.assertNotIn("statusLine", self.read())

    def test_reinstall_does_not_wrap_our_own_statusline(self):
        self.write_settings({"statusLine": FOREIGN_STATUSLINE})
        self.do_install()
        first = (self.state / "statusline-base.sh").read_text(encoding="utf-8")
        self.do_install()
        second = (self.state / "statusline-base.sh").read_text(encoding="utf-8")
        self.assertEqual(first, second, "reinstall must not capture our own wrapper as the base")
        # The comment header legitimately names statusline.sh, so check the command
        # itself: the last non-empty line must still be the user's original command.
        command_line = [ln for ln in second.splitlines() if ln and not ln.startswith("#")][-1]
        self.assertEqual(command_line, FOREIGN_STATUSLINE["command"])

    def test_foreign_statusline_installed_later_is_not_clobbered_by_uninstall(self):
        self.do_install()
        s = self.read()
        s["statusLine"] = FOREIGN_STATUSLINE          # user replaced it by hand
        self.write_settings(s)
        self.do_uninstall()
        self.assertEqual(self.read()["statusLine"], FOREIGN_STATUSLINE)

    # ------------------------------------------------------------------ safety

    def test_backup_is_written_before_changes(self):
        self.write_settings({"model": "opus"})
        rep = self.do_install()
        backup = Path(rep["backup"])
        self.assertTrue(backup.exists())
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), {"model": "opus"})

    def test_malformed_settings_raises_rather_than_discarding(self):
        self.settings.write_text("{ this is not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.do_install()

    def test_install_never_destroys_something_the_user_already_had(self):
        """The blast radius grew from two names to ten, and one of them is `session-handoff`.

        The previous implementation called shutil.rmtree on whatever sat at the
        destination. A user with their own skill by that name lost it on install, and
        uninstall then removed our link as "ours" and left them with nothing at all.
        """
        theirs_skill = self.claude / "skills" / "session-handoff"
        theirs_skill.mkdir(parents=True)
        (theirs_skill / "SKILL.md").write_text("THEIR OWN SKILL\n", encoding="utf-8")
        self.bin.mkdir(parents=True, exist_ok=True)
        theirs_cli = self.bin / "skillforge"
        theirs_cli.write_text("#!/bin/sh\necho theirs\n", encoding="utf-8")

        rep = self.do_install()

        self.assertTrue(theirs_skill.is_dir() and not theirs_skill.is_symlink())
        self.assertEqual((theirs_skill / "SKILL.md").read_text(encoding="utf-8"),
                         "THEIR OWN SKILL\n", "the user's own skill was overwritten")
        self.assertEqual(theirs_cli.read_text(encoding="utf-8"),
                         "#!/bin/sh\necho theirs\n", "the user's own script was overwritten")
        self.assertIn("NOT LINKED", rep["skills"], "a collision must be reported, not silent")
        self.assertIn("session-handoff", rep["skills"])
        self.assertIn("NOT LINKED", rep["cli"])

        # And uninstall must not remove what it never linked.
        self.do_uninstall()
        self.assertTrue((theirs_skill / "SKILL.md").exists())
        self.assertTrue(theirs_cli.exists())

    def test_a_users_own_statusline_script_is_not_mistaken_for_ours(self):
        """`statusline.sh` as a bare substring matches other people's scripts too.

        A user whose status line is ~/bin/git-statusline.sh had it treated as ours:
        never saved to original-statusline.json, never called by the wrapper, and gone
        after uninstall. The marker now includes the directory component.
        """
        for command in ('"/usr/local/bin/my-statusline.sh"',
                        '"$HOME/bin/git-statusline.sh"'):
            with self.subTest(command=command):
                self.setUp()
                self.write_settings({"statusLine": {"type": "command", "command": command}})
                self.do_install()
                saved = Path(self.state) / "original-statusline.json"
                self.assertTrue(saved.exists(),
                                "their status line must be preserved: %s" % command)
                self.do_uninstall()
                self.assertEqual(self.read()["statusLine"]["command"], command,
                                 "their status line must come back verbatim")

    def test_uninstall_leaves_a_foreign_file_at_the_symlink_path(self):
        real = self.bin / "skillforge"
        real.write_text("#!/bin/sh\necho not ours\n", encoding="utf-8")
        self.do_uninstall()
        self.assertTrue(real.exists(), "a real file must never be deleted by uninstall")
        self.assertIn("not ours", real.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
