#!/usr/bin/env python3
"""Real install/uninstall against a real temporary Claude directory, for issue #39's
review opt-in: set_env/unset_env, enable_review/disable_review, and uninstall's
manifest-gated removal of env.SKILL_COMPOUNDER_REVIEW.

No mocks: every test writes an actual settings.json, calls the actual installer
functions, and reads the files back off disk."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
APP_HOME = str(Path(__file__).resolve().parent.parent)

from skill_compounder import installer


class ReviewOptInTest(unittest.TestCase):

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

    def manifest(self):
        p = self.state / installer.MANIFEST
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def install(self):
        return installer.install(APP_HOME, str(self.claude), str(self.bin), str(self.state))

    def uninstall(self):
        return installer.uninstall(APP_HOME, str(self.claude), str(self.bin), str(self.state))

    # ------------------------------------------------------------- default install

    def test_default_install_does_not_touch_the_env_block(self):
        self.write_settings({"env": {"MY_OWN": "keep"}})
        self.install()
        self.assertEqual(self.read()["env"], {"MY_OWN": "keep"})
        self.assertNotIn("review_env_set", self.manifest())

    def test_install_with_no_settings_writes_no_env_block(self):
        self.install()
        self.assertNotIn("env", self.read())

    # ------------------------------------------------------------------ set_env

    def test_set_env_writes_exactly_that_key_and_keeps_others(self):
        self.write_settings({"env": {"OTHER": "1", "AND_ANOTHER": "yes"}})
        installer.set_env(str(self.claude), "SKILL_COMPOUNDER_REVIEW", "1")
        env = self.read()["env"]
        self.assertEqual(env["SKILL_COMPOUNDER_REVIEW"], "1")
        self.assertEqual(env["OTHER"], "1")
        self.assertEqual(env["AND_ANOTHER"], "yes")

    def test_set_env_on_missing_settings_creates_it(self):
        installer.set_env(str(self.claude), "K", "V")
        self.assertEqual(self.read()["env"], {"K": "V"})

    def test_set_env_twice_is_byte_identical(self):
        self.write_settings({"env": {"OTHER": "1"}})
        installer.set_env(str(self.claude), "K", "V")
        first = self.settings.read_bytes()
        installer.set_env(str(self.claude), "K", "V")
        second = self.settings.read_bytes()
        self.assertEqual(first, second)

    def test_unset_env_removes_only_the_named_key(self):
        self.write_settings({"env": {"K": "V", "OTHER": "1"}})
        installer.unset_env(str(self.claude), "K")
        self.assertEqual(self.read()["env"], {"OTHER": "1"})

    def test_unset_env_drops_the_whole_env_block_when_it_was_the_only_key(self):
        self.write_settings({"env": {"K": "V"}})
        installer.unset_env(str(self.claude), "K")
        self.assertNotIn("env", self.read())

    def test_unset_env_on_absent_key_changes_nothing(self):
        self.write_settings({"env": {"OTHER": "1"}})
        before = self.settings.read_bytes()
        result = installer.unset_env(str(self.claude), "NOT_THERE")
        self.assertFalse(result["changed"])
        self.assertEqual(self.settings.read_bytes(), before)

    # -------------------------------------------------------------- enable_review

    def test_enable_review_writes_exactly_that_key_and_leaves_others(self):
        self.write_settings({"env": {"USER_KEY": "kept"}, "otherTopLevel": True})
        self.install()
        result = installer.enable_review(str(self.claude), str(self.state))
        env = self.read()["env"]
        self.assertEqual(env["SKILL_COMPOUNDER_REVIEW"], "1")
        self.assertEqual(env["USER_KEY"], "kept")
        self.assertTrue(self.read()["otherTopLevel"])
        self.assertTrue(result["changed"])
        self.assertTrue(self.manifest()["review_env_set"])

    def test_enable_review_twice_is_byte_identical(self):
        self.install()
        installer.enable_review(str(self.claude), str(self.state))
        first = self.settings.read_bytes()
        installer.enable_review(str(self.claude), str(self.state))
        second = self.settings.read_bytes()
        self.assertEqual(first, second)

    def test_a_user_set_value_is_left_alone_and_reported(self):
        # The env key already exists, and the manifest has never recorded that this
        # package set it: it is the user's own choice (or another tool's), and
        # enable_review must not overwrite it.
        self.write_settings({"env": {"SKILL_COMPOUNDER_REVIEW": "0"}})
        self.install()
        self.assertNotIn("review_env_set", self.manifest())
        result = installer.enable_review(str(self.claude), str(self.state))
        self.assertFalse(result["changed"])
        self.assertIn("note", result)
        self.assertIn("left alone", result["note"])
        self.assertEqual(self.read()["env"]["SKILL_COMPOUNDER_REVIEW"], "0")
        self.assertNotIn("review_env_set", self.manifest())

    # ------------------------------------------------------------- disable_review

    def test_disable_review_removes_only_the_key_we_set(self):
        self.write_settings({"env": {"USER_KEY": "kept"}})
        self.install()
        installer.enable_review(str(self.claude), str(self.state))
        result = installer.disable_review(str(self.claude), str(self.state))
        self.assertTrue(result["changed"])
        env = self.read()["env"]
        self.assertNotIn("SKILL_COMPOUNDER_REVIEW", env)
        self.assertEqual(env["USER_KEY"], "kept")
        self.assertNotIn("review_env_set", self.manifest())

    def test_disable_review_leaves_a_user_set_value_alone(self):
        self.write_settings({"env": {"SKILL_COMPOUNDER_REVIEW": "1"}})
        self.install()
        result = installer.disable_review(str(self.claude), str(self.state))
        self.assertFalse(result["changed"])
        self.assertIn("not set by this package", result["note"])
        self.assertEqual(self.read()["env"]["SKILL_COMPOUNDER_REVIEW"], "1")

    def test_disable_review_on_a_key_never_set_is_a_no_op(self):
        self.install()
        result = installer.disable_review(str(self.claude), str(self.state))
        self.assertFalse(result["changed"])
        self.assertNotIn("env", self.read())

    # ------------------------------------------------------------------ uninstall

    def test_uninstall_removes_the_key_only_when_we_set_it(self):
        self.write_settings({"env": {"USER_KEY": "kept"}})
        self.install()
        installer.enable_review(str(self.claude), str(self.state))
        self.assertTrue(self.manifest()["review_env_set"])

        rep = self.uninstall()

        env = self.read().get("env", {})
        self.assertNotIn("SKILL_COMPOUNDER_REVIEW", env)
        self.assertEqual(env.get("USER_KEY"), "kept")
        self.assertIn("removed env.SKILL_COMPOUNDER_REVIEW", rep["review"])
        self.assertNotIn("review_env_set", self.manifest())

    def test_uninstall_leaves_a_user_set_value_alone(self):
        self.write_settings({"env": {"SKILL_COMPOUNDER_REVIEW": "1"}})
        self.install()
        self.assertNotIn("review_env_set", self.manifest())

        self.uninstall()

        self.assertEqual(self.read()["env"]["SKILL_COMPOUNDER_REVIEW"], "1")

    def test_uninstall_without_review_ever_enabled_touches_no_env_key(self):
        self.write_settings({"env": {"USER_KEY": "kept"}})
        self.install()
        rep = self.uninstall()
        self.assertEqual(self.read()["env"], {"USER_KEY": "kept"})
        self.assertNotIn("review", rep)


if __name__ == "__main__":
    unittest.main(verbosity=2)
