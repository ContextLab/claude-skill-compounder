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

    def test_symlinks_point_at_the_repo(self):
        rep = self.do_install()
        skill = Path(rep["skill"])
        cli = Path(rep["cli"])
        self.assertTrue(skill.is_symlink())
        self.assertTrue((skill / "SKILL.md").exists(), "skill symlink must expose SKILL.md")
        self.assertTrue(cli.is_symlink())
        self.assertTrue(os.access(str(cli), os.X_OK), "skillforge must be executable")

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

    def test_uninstall_leaves_a_foreign_file_at_the_symlink_path(self):
        real = self.bin / "skillforge"
        real.write_text("#!/bin/sh\necho not ours\n", encoding="utf-8")
        self.do_uninstall()
        self.assertTrue(real.exists(), "a real file must never be deleted by uninstall")
        self.assertIn("not ours", real.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
