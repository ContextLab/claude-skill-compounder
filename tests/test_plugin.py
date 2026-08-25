#!/usr/bin/env python3
"""The repo ships as a Claude Code plugin as well as via the installer.

Two install paths mean two chances to drift apart, so most of what is here is a
drift check: hooks.json and the installer must wire the same scripts to the same
events, and every command either of them names must actually exist on disk.

No mocks. The hook idempotence tests run the real shell script through subprocess
with real payloads and read the real state directory back off disk. The plugin
validation test shells out to the real `claude` CLI when it is available.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from skill_compounder import installer

PLUGIN_JSON = APP / ".claude-plugin" / "plugin.json"
HOOKS_JSON = APP / "hooks" / "hooks.json"
HOOK = APP / "hooks" / "compound-improvement.sh"


def plugin_commands():
    """Every command string in hooks.json, keyed by event."""
    spec = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    out = {}
    for event, groups in spec["hooks"].items():
        out[event] = [(g.get("matcher"), h["command"]) for g in groups for h in g["hooks"]]
    return out


class ManifestTest(unittest.TestCase):

    def test_plugin_manifest_is_valid_and_named(self):
        spec = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
        self.assertEqual(spec["name"], "skill-compounder")
        for key in ("version", "description", "repository", "license"):
            self.assertIn(key, spec)
        # Plugin skills are namespaced <plugin>:<skill>, so the plugin name is part of
        # every skill's trigger identity. Renaming it silently renames all of them.
        self.assertRegex(spec["version"], r"^\d+\.\d+\.\d+$")

    def test_claude_md_is_not_at_the_plugin_root(self):
        """`claude plugin validate --strict` fails on a root CLAUDE.md.

        It warns that the file will not load as project context, and --strict turns
        warnings into errors. `.claude/CLAUDE.md` loads exactly the same way and does
        not trip the validator, which was confirmed by running a headless session in a
        scratch repo and reading a token back out of it.
        """
        self.assertFalse((APP / "CLAUDE.md").exists(),
                         "CLAUDE.md at the repo root breaks `claude plugin validate --strict`; "
                         "it belongs at .claude/CLAUDE.md")
        self.assertTrue((APP / ".claude" / "CLAUDE.md").is_file(),
                        "the repo guidance must still be somewhere Claude Code loads it")

    def test_every_plugin_hook_command_exists_and_is_executable(self):
        for event, entries in plugin_commands().items():
            for _matcher, command in entries:
                self.assertIn("${CLAUDE_PLUGIN_ROOT}", command,
                              "%s command must be plugin-root relative: %s" % (event, command))
                rel = command.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1].split('"', 1)[0]
                script = APP / rel
                self.assertTrue(script.is_file(), "%s does not exist" % script)
                self.assertTrue(os.access(str(script), os.X_OK), "%s is not executable" % script)

    def test_plugin_and_installer_wire_the_same_things(self):
        """The drift check. Two wirings, one behavior."""
        settings = installer.merge_hooks({}, str(APP))["hooks"]
        plugin = plugin_commands()

        self.assertEqual(set(settings), set(plugin),
                         "the installer and hooks.json disagree about which events to hook")

        for event in settings:
            s_cmds = [h["command"] for g in settings[event] for h in g["hooks"]]
            p_cmds = [c for _m, c in plugin[event]]
            self.assertEqual(len(s_cmds), len(p_cmds))
            for s_cmd, p_cmd in zip(sorted(s_cmds), sorted(p_cmds)):
                # Same script, same trailing mode argument; only the root differs.
                self.assertEqual(s_cmd.replace(str(APP), "ROOT"),
                                 p_cmd.replace("${CLAUDE_PLUGIN_ROOT}", "ROOT"))

        s_matchers = [g.get("matcher") for g in settings["PostToolUse"]]
        p_matchers = [m for m, _c in plugin["PostToolUse"]]
        self.assertEqual(s_matchers, p_matchers, "PostToolUse matchers must agree")

    @unittest.skipUnless(shutil.which("claude"), "claude CLI not on PATH")
    def test_claude_plugin_validate_strict_passes(self):
        proc = subprocess.run(["claude", "plugin", "validate", str(APP), "--strict"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0,
                         "plugin validate --strict failed:\n%s\n%s"
                         % (proc.stdout, proc.stderr))


class HookIdempotenceTest(unittest.TestCase):
    """Installing via the one-liner AND enabling the plugin delivers every event twice.

    Measured on CLI 2.1.241: with both wirings active a single Write produced two
    PostToolUse deliveries. Undetected, that halves CI_EDIT_EVERY. The hook claims each
    event by its id, so the second delivery is a no-op.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": self.tmp.name,
            "SKILL_COMPOUNDER_STATE": str(self.state),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, mode, payload, **extra):
        env = dict(self.env)
        env.update(extra)
        proc = subprocess.run([str(HOOK), mode], input=json.dumps(payload),
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, "a hook must never exit non-zero: " + proc.stderr)
        return proc.stdout.strip()

    def test_the_same_prompt_delivered_twice_reminds_once(self):
        payload = {"session_id": "s1", "prompt_id": "p-abc",
                   "prompt": "x" * 120, "hook_event_name": "UserPromptSubmit"}
        first = self.run_hook("prompt", payload)
        second = self.run_hook("prompt", payload)
        self.assertIn("skill-compounder", first, "the first delivery must fire")
        self.assertEqual(second, "", "the duplicate delivery must emit nothing")

    def test_the_same_edit_delivered_twice_counts_once(self):
        counted = []
        for i in range(4):
            payload = {"session_id": "s2", "tool_use_id": "toolu_%d" % i,
                       "hook_event_name": "PostToolUse"}
            self.run_hook("edit", payload, CI_EDIT_EVERY="100")
            self.run_hook("edit", payload, CI_EDIT_EVERY="100")   # the plugin's copy
            counted.append(int((self.state / "reminders" / "s2.edits").read_text()))
        self.assertEqual(counted, [1, 2, 3, 4],
                         "four distinct edits delivered twice each must count as four")

    def test_distinct_sessions_do_not_share_claims(self):
        payload = {"prompt_id": "p-same", "prompt": "y" * 120}
        a = self.run_hook("prompt", dict(payload, session_id="alpha"))
        b = self.run_hook("prompt", dict(payload, session_id="beta"))
        self.assertIn("skill-compounder", a)
        self.assertIn("skill-compounder", b, "a claim must not leak across sessions")

    def test_an_event_with_no_id_still_fires(self):
        """Losing reminders is worse than a rare duplicate, so an unidentifiable
        event is always claimed rather than suppressed."""
        out = self.run_hook("prompt", {"session_id": "s3", "prompt": "z" * 120})
        self.assertIn("skill-compounder", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
