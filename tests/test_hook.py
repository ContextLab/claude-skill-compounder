#!/usr/bin/env python3
"""Runs the real reminder hook with real payloads and checks the throttling.

The hook's contract is narrow but strict: emit valid Claude Code hook JSON when it
should fire, emit NOTHING and exit 0 when it should not, and never fail loudly."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "hooks" / "compound-improvement.sh"
LONG_PROMPT = "Please implement the retry-with-backoff wrapper and wire it into the scheduler."


class HookTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, mode, payload, **extra):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state),
               "SKILL_COMPOUNDER_STATE": str(self.state)}
        env.update({k: str(v) for k, v in extra.items()})
        return subprocess.run([str(HOOK), mode], input=json.dumps(payload),
                              capture_output=True, text=True, env=env)

    # -------------------------------------------------------------- edit mode

    def test_edit_fires_only_every_nth_edit(self):
        fired = []
        for i in range(1, 10):
            r = self.run_hook("edit", {"session_id": "s1", "tool_name": "Edit"}, CI_EDIT_EVERY=3)
            self.assertEqual(r.returncode, 0)
            if r.stdout.strip():
                fired.append(i)
        self.assertEqual(fired, [3, 6, 9])

    def test_edit_output_is_valid_hook_json(self):
        r = self.run_hook("edit", {"session_id": "s1"}, CI_EDIT_EVERY=1)
        out = json.loads(r.stdout)
        self.assertTrue(out["suppressOutput"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("skill-compounder", out["hookSpecificOutput"]["additionalContext"])

    def test_edit_counters_are_per_session(self):
        self.run_hook("edit", {"session_id": "a"}, CI_EDIT_EVERY=2)
        r = self.run_hook("edit", {"session_id": "b"}, CI_EDIT_EVERY=2)
        self.assertEqual(r.stdout.strip(), "",
                         "one session's edits must not advance another's counter")

    # ------------------------------------------------------------ prompt mode

    def test_short_prompts_never_fire(self):
        for text in ("yes", "continue", "ok do it", "thanks!"):
            r = self.run_hook("prompt", {"session_id": "s1", "prompt": text})
            self.assertEqual(r.stdout.strip(), "", "short prompt %r must not fire" % text)

    def test_long_prompt_fires_once_then_is_throttled(self):
        payload = {"session_id": "s1", "prompt": LONG_PROMPT}
        first = self.run_hook("prompt", payload, CI_NOW=1000)
        second = self.run_hook("prompt", payload, CI_NOW=1300)
        self.assertNotEqual(first.stdout.strip(), "")
        self.assertEqual(second.stdout.strip(), "", "cooldown must suppress the second")

    def test_cooldown_expires(self):
        payload = {"session_id": "s1", "prompt": LONG_PROMPT}
        self.run_hook("prompt", payload, CI_NOW=1000)
        later = self.run_hook("prompt", payload, CI_NOW=1000 + 1201)
        self.assertNotEqual(later.stdout.strip(), "", "reminder must return after the cooldown")

    def test_prompt_output_is_valid_hook_json(self):
        r = self.run_hook("prompt", {"session_id": "s1", "prompt": LONG_PROMPT})
        out = json.loads(r.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("skill-compounder", out["hookSpecificOutput"]["additionalContext"])

    # ---------------------------------------------------------------- safety

    def test_malformed_payload_is_survivable(self):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state)}
        for mode in ("prompt", "edit"):
            r = subprocess.run([str(HOOK), mode], input="not json at all",
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0,
                             "a bad payload must never break the user's turn (%s)" % mode)

    def test_missing_session_id_is_survivable(self):
        r = self.run_hook("edit", {"tool_name": "Edit"}, CI_EDIT_EVERY=1)
        self.assertEqual(r.returncode, 0)
        self.assertNotEqual(r.stdout.strip(), "")

    def test_unknown_mode_is_a_silent_noop(self):
        r = self.run_hook("nonsense", {"session_id": "s1"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")




class BashEditVisibilityTest(unittest.TestCase):
    """A PostToolUse matcher of Write|Edit is blind to how autonomous sessions edit.

    Bypass-permissions sessions are instructed to change files with sed, heredocs and
    inline interpreters, all of which arrive as Bash. Under the old matcher the counter
    on a real session reached 4 while dozens of files were being rewritten, so the
    checkpoint never fired in the sessions it was built for. These run the real hook
    against real payloads and read the counter back off disk.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def bash(self, command, sid="s1", uid=None, **extra):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state)}
        env.update({k: str(v) for k, v in extra.items()})
        payload = {"session_id": sid, "tool_name": "Bash",
                   "tool_input": {"command": command}}
        if uid:
            payload["tool_use_id"] = uid
        return subprocess.run([str(HOOK), "edit"], input=json.dumps(payload),
                              capture_output=True, text=True, env=env)

    def counted(self, sid="s1"):
        f = self.state / "reminders" / ("%s.edits" % sid)
        return len(f.read_bytes()) if f.exists() else 0

    def test_bash_writes_are_counted(self):
        for i, cmd in enumerate([
                "cat > out.txt <<'EOF'\nhi\nEOF",
                "sed -i '' s/a/b/ notes.md",
                "python3 - <<'PY'\np.write_text(x)\nPY",
                "cp a.py b.py",
                "./run_tests.sh > suite.log 2>&1"]):
            r = self.bash(cmd, uid="u%d" % i, CI_EDIT_EVERY=99)
            self.assertEqual(r.returncode, 0, cmd)
        self.assertEqual(self.counted(), 5,
                         "every one of these Bash commands writes a file")

    def test_read_only_bash_is_not_counted(self):
        for i, cmd in enumerate([
                "ls -la",
                "grep -rn foo . 2>/dev/null",
                "git status",
                "wc -c < notes.md",
                "jq -r .name package.json"]):
            r = self.bash(cmd, uid="r%d" % i, CI_EDIT_EVERY=99)
            self.assertEqual(r.returncode, 0, cmd)
            self.assertEqual(r.stdout.strip(), "", "read-only command emitted: %s" % cmd)
        self.assertEqual(self.counted(), 0,
                         "a checkpoint that counts `ls` trains the user to ignore it")

    def test_bash_write_can_reach_a_checkpoint(self):
        r = None
        for i in range(3):
            r = self.bash("printf x > f%d.txt" % i, uid="c%d" % i, CI_EDIT_EVERY=3)
        self.assertIn("Checkpoint after 3 file edits", r.stdout)


class ProseReminderTest(unittest.TestCase):
    """`ai-tell-audit` names a README in its description but had nothing to fire it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, path, sid="s1", uid=None, **extra):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state)}
        env.update({k: str(v) for k, v in extra.items()})
        payload = {"session_id": sid, "tool_name": "Edit",
                   "tool_input": {"file_path": path}}
        if uid:
            payload["tool_use_id"] = uid
        return subprocess.run([str(HOOK), "edit"], input=json.dumps(payload),
                              capture_output=True, text=True, env=env)

    def test_editing_a_readme_names_the_audit_skill(self):
        r = self.edit("/repo/README.md", uid="p1", CI_EDIT_EVERY=99)
        self.assertIn("ai-tell-audit", r.stdout)
        self.assertIn("README.md", r.stdout)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["hookEventName"],
                         "PostToolUse")

    def test_it_fires_once_per_file_per_session(self):
        self.edit("/repo/README.md", uid="p1", CI_EDIT_EVERY=99)
        r = self.edit("/repo/README.md", uid="p2", CI_EDIT_EVERY=99)
        self.assertEqual(r.stdout.strip(), "",
                         "one reminder per file; a per-edit reminder is noise")

    def test_a_second_prose_file_still_fires(self):
        self.edit("/repo/README.md", uid="p1", CI_EDIT_EVERY=99)
        r = self.edit("/repo/docs/DESIGN.md", uid="p2", CI_EDIT_EVERY=99)
        self.assertIn("DESIGN.md", r.stdout)

    def test_code_never_fires_it(self):
        for i, path in enumerate(["/repo/src/main.py", "/repo/tests/test_x.py",
                                  "/repo/notes/2026-08-25-session.md"]):
            r = self.edit(path, uid="n%d" % i, CI_EDIT_EVERY=99)
            self.assertEqual(r.stdout.strip(), "", "fired on %s" % path)

    def test_the_checkpoint_wins_when_both_are_due(self):
        """Only one context can be emitted per invocation; the rarer one must win."""
        r = self.edit("/repo/README.md", uid="w1", CI_EDIT_EVERY=1)
        self.assertIn("Checkpoint after 1 file edits", r.stdout)
        self.assertNotIn("ai-tell-audit", r.stdout)

if __name__ == "__main__":
    unittest.main(verbosity=2)
