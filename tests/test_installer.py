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

    def make_checkout_without(self, *scripts):
        """A real copy of this checkout with named hook scripts removed.

        The installer decides what to wire by asking whether each script EXISTS, so the
        only honest way to test "a gate whose script this checkout does not carry" is to
        hand it a checkout that does not carry it."""
        import shutil
        dest = Path(self.tmp.name) / "checkout"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(APP_HOME, dest, symlinks=True,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        for name in scripts:
            (dest / "hooks" / name).unlink()
        return str(dest)

    def test_a_stale_entry_is_stripped_even_when_nothing_replaces_it(self):
        """`_strip_marker` returns a NEW list, and the write-back was guarded on there
        being something to write. So when the strip emptied the list and this checkout
        wired nothing onto that event, the result was never assigned and the ORIGINAL
        list -- stale entry still in it -- stayed in settings.json, pointing at a script
        that is gone. Found by a cold reviewer on 2026-08-27, reproduced on PreToolUse
        and on Stop.

        The partial case was always handled, because one surviving gate makes the guard
        true, which is why this needs a checkout carrying NONE of the event's scripts."""
        gone = "/gone/checkout/hooks"
        self.write_settings({"hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
                            "command": '"%s/claim-gate.sh" # claude-skill-compounder claim-gate'
                                       % gone}]}],
            "Stop": [{"hooks": [{"type": "command",
                      "command": '"%s/apply-gate.sh" # claude-skill-compounder apply-gate'
                                 % gone}]}],
        }})
        home = self.make_checkout_without("claim-gate.sh", "doc-gate.sh", "repeat-gate.sh",
                                          "apply-gate.sh", "insight-capture.sh")
        installer.install(home, str(self.claude), str(self.bin), str(self.state))
        s = self.read()
        for event in ("PreToolUse", "Stop"):
            with self.subTest(event=event):
                cmds = [h["command"] for g in s["hooks"].get(event, []) for h in g["hooks"]]
                self.assertFalse([c for c in cmds if gone in c],
                                 "a stale entry pointing at a script that is gone "
                                 "survived on %s: %r" % (event, cmds))

    def test_a_stale_post_tool_use_failure_entry_is_stripped_too(self):
        """THE THIRD SITE, and it had no test until a cold reviewer reverted each of the
        three write-backs one at a time and found this one green with the fix removed.
        The commit that made the change said "the three sites now match it" while the test
        seeded stale entries on two of them, so the claim outran what was pinned."""
        gone = "/gone/checkout/hooks"
        self.write_settings({"hooks": {"PostToolUseFailure": [
            {"matcher": "Skill", "hooks": [{"type": "command",
             "command": '"%s/skill-use.sh" fail # claude-skill-compounder skill-use'
                        % gone}]}]}})
        home = self.make_checkout_without("skill-use.sh", "repeat-gate.sh")
        installer.install(home, str(self.claude), str(self.bin), str(self.state))
        cmds = [h["command"]
                for g in self.read()["hooks"].get("PostToolUseFailure", [])
                for h in g["hooks"]]
        self.assertFalse([c for c in cmds if gone in c],
                         "a stale PostToolUseFailure entry pointing at a script that is "
                         "gone survived: %r" % cmds)

    def test_a_foreign_entry_survives_that_same_strip(self):
        """NON-VACUITY, and the failure it guards against is the destructive one: a
        write-back that simply dropped the event would satisfy the test above."""
        gone = "/gone/checkout/hooks"
        self.write_settings({"hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command",
                 "command": '"%s/claim-gate.sh" # claude-skill-compounder claim-gate' % gone}]},
                {"matcher": "Bash", "hooks": [{"type": "command",
                 "command": "/usr/bin/python3 /some/other/tool.py"}]},
            ],
        }})
        home = self.make_checkout_without("claim-gate.sh", "doc-gate.sh", "repeat-gate.sh")
        installer.install(home, str(self.claude), str(self.bin), str(self.state))
        cmds = [h["command"] for g in self.read()["hooks"].get("PreToolUse", [])
                for h in g["hooks"]]
        self.assertIn("/usr/bin/python3 /some/other/tool.py", cmds,
                      "another tool's PreToolUse hook was removed: %r" % cmds)

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
        self.assertEqual(ptu[0]["matcher"], "Write|Edit|Bash")
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
        # Both claim-gate arms. Stop now holds two entries of ours, so a strip that
        # handled only the first marker would duplicate this one on every reinstall.
        for event in ("PreToolUse", "Stop"):
            gate = [h for g in s["hooks"][event] for h in g["hooks"]
                    if "claim-gate.sh" in h["command"]]
            self.assertEqual(len(gate), 1,
                             "reinstall duplicated the claim gate on %s" % event)

    def test_claim_gate_is_wired_to_both_of_its_events(self):
        """Two arms, two events, and the commit arm is the one that cannot be dropped.

        A commit message never appears in `last_assistant_message`, so a Stop-only wiring
        would miss both incidents that motivated the gate. Asserted per event rather than
        "claim-gate.sh appears somewhere", which a half-wiring would pass.
        """
        self.do_install()
        s = self.read()
        pre = s["hooks"]["PreToolUse"]
        gate = [(g.get("matcher"), h["command"]) for g in pre for h in g["hooks"]
                if "claim-gate.sh" in h["command"]]
        self.assertEqual(len(gate), 1, "the commit arm must be wired exactly once")
        self.assertEqual(gate[0][0], "Bash",
                         "the commit arm must match Bash; the gate decides what is a commit")
        stop_gate = [h for g in s["hooks"]["Stop"] for h in g["hooks"]
                     if "claim-gate.sh" in h["command"]]
        self.assertEqual(len(stop_gate), 1, "the Stop arm must be wired exactly once")
        self.assertEqual(stop_gate[0]["timeout"], 10)
        # The Stop arm carries no matcher: Stop has nothing to match on, and a matcher
        # there is silently ignored rather than rejected.
        for g in s["hooks"]["Stop"]:
            if any("claim-gate.sh" in h["command"] for h in g["hooks"]):
                self.assertIsNone(g.get("matcher"))

    def test_claim_gate_accumulator_arm_is_not_wired(self):
        """The PostToolUse arm is deliberately left out, and this pins that decision.

        It records numbers out of every tool RESULT, an Agent/Task result included, which
        is precisely the subagent testimony the Stop arm excludes from its evidence on
        purpose. Wiring it on a `*` matcher would make the gate stop catching relayed
        figures -- the defect it exists for. If it is ever wired it needs a matcher that
        excludes Agent and Task, and this test should be updated to assert that, not
        deleted.
        """
        self.do_install()
        s = self.read()
        for g in s["hooks"].get("PostToolUse", []):
            for h in g["hooks"]:
                self.assertNotIn("claim-gate.sh", h["command"],
                                 "the accumulator arm must not be wired on a matcher that "
                                 "admits Agent/Task results as evidence")

    def test_claim_gate_is_removed_from_both_events(self):
        self.do_install()
        self.do_uninstall()
        s = self.read()
        for event in ("PreToolUse", "Stop"):
            self.assertFalse(any("claim-gate.sh" in h["command"]
                                 for g in s.get("hooks", {}).get(event, [])
                                 for h in g["hooks"]),
                             "the claim gate survived uninstall on %s" % event)
        self.assertNotIn("PreToolUse", s.get("hooks", {}),
                         "an event key we created must not be left behind empty")

    def test_the_reminder_hook_is_wired_to_both_of_its_events(self):
        """Two events, one entry each, and the PreToolUse matcher covers all three tools.

        Splitting the tool arm into `Bash` and `Write|Edit` entries would deliver the same
        event twice for the same work; the script dispatches on `.tool_name` instead.
        """
        self.do_install()
        s = self.read()
        pre = [(g.get("matcher"), h["command"]) for g in s["hooks"]["PreToolUse"]
               for h in g["hooks"] if "remind.sh" in h["command"]]
        self.assertEqual(len(pre), 1, "the tool arm must be wired exactly once")
        self.assertEqual(pre[0][0], "Bash|Write|Edit")
        ups = [(g.get("matcher"), h["command"]) for g in s["hooks"]["UserPromptSubmit"]
               for h in g["hooks"] if "remind.sh" in h["command"]]
        self.assertEqual(len(ups), 1, "the prompt arm must be wired exactly once")
        self.assertIsNone(ups[0][0],
                          "UserPromptSubmit has nothing to match on")
        for g in s["hooks"]["PreToolUse"] + s["hooks"]["UserPromptSubmit"]:
            for h in g["hooks"]:
                if "remind.sh" in h["command"]:
                    self.assertEqual(h["timeout"], 10)

    def test_the_reminder_hook_is_wired_after_the_gates_that_can_deny(self):
        """Order is load-bearing: tests/test_plugin.py compares the two wirings'
        matcher lists POSITIONALLY, so a reordering here is a drift failure there."""
        self.do_install()
        pre = [h["command"] for g in self.read()["hooks"]["PreToolUse"] for h in g["hooks"]]
        names = [c.rsplit("/", 1)[-1].strip('"') for c in pre]
        self.assertEqual(names, ["claim-gate.sh", "doc-gate.sh", "repeat-gate.sh",
                                 "remind.sh"])

    def test_installing_twice_leaves_one_reminder_entry_per_event(self):
        self.do_install()
        self.do_install()
        s = self.read()
        for event in ("UserPromptSubmit", "PreToolUse"):
            found = [h for g in s["hooks"][event] for h in g["hooks"]
                     if "remind.sh" in h["command"]]
            self.assertEqual(len(found), 1, "%s grew a duplicate entry" % event)

    def test_the_reminder_hook_is_removed_from_both_events(self):
        self.do_install()
        self.do_uninstall()
        s = self.read()
        for event in ("UserPromptSubmit", "PreToolUse"):
            self.assertFalse(any("remind.sh" in h["command"]
                                 for g in s.get("hooks", {}).get(event, [])
                                 for h in g["hooks"]),
                             "the reminder hook survived uninstall on %s" % event)

    def test_a_users_own_prompt_hook_survives_beside_the_reminder(self):
        self.write_settings({"hooks": {"UserPromptSubmit": [FOREIGN_HOOK]}})
        self.do_install()
        cmds = [h["command"] for g in self.read()["hooks"]["UserPromptSubmit"]
                for h in g["hooks"]]
        self.assertTrue(any("other/tool.py" in c for c in cmds))
        self.assertTrue(any("remind.sh" in c for c in cmds))
        self.do_uninstall()
        cmds = [h["command"] for g in self.read()["hooks"]["UserPromptSubmit"]
                for h in g["hooks"]]
        self.assertEqual([c for c in cmds if "other/tool.py" in c], cmds,
                         "uninstall must leave another tool's prompt hook as it found it")

    def test_a_checkout_without_the_reminder_hook_still_installs(self):
        """The package must stay installable from a checkout older than any one
        component; refusing turns a partial upgrade into no upgrade at all."""
        home = self.make_checkout_without("remind.sh")
        installer.install(home, str(self.claude), str(self.bin), str(self.state))
        s = self.read()
        for event in ("UserPromptSubmit", "PreToolUse"):
            self.assertFalse(any("remind.sh" in h["command"]
                                 for g in s["hooks"][event] for h in g["hooks"]),
                             "%s wired a script this checkout does not carry" % event)
        self.assertTrue(any("compound-improvement.sh" in h["command"]
                            for g in s["hooks"]["UserPromptSubmit"] for h in g["hooks"]),
                        "the rest of the wiring must still be installed")

    def test_a_stale_reminder_entry_is_stripped_by_a_checkout_without_it(self):
        """The strip runs before any append, so an entry left by a newer checkout is
        removed rather than left pointing at a file that is gone."""
        self.do_install()
        home = self.make_checkout_without("remind.sh")
        installer.install(home, str(self.claude), str(self.bin), str(self.state))
        s = self.read()
        for event in ("UserPromptSubmit", "PreToolUse"):
            self.assertFalse(any("remind.sh" in h["command"]
                                 for g in s["hooks"][event] for h in g["hooks"]),
                             "a stale %s entry was left orphaned" % event)

    def test_a_foreign_pretooluse_hook_survives_install_and_uninstall(self):
        """PreToolUse is the event a user is most likely to already be using: it is where
        permission rules live. Ours must land beside theirs and leave with only itself."""
        self.write_settings({"hooks": {"PreToolUse": [{"matcher": "Bash",
                                                       "hooks": FOREIGN_HOOK["hooks"]}]}})
        self.do_install()
        s = self.read()
        cmds = [h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertTrue(any("other/tool.py" in c for c in cmds))
        self.assertTrue(any("claim-gate.sh" in c for c in cmds))
        self.do_uninstall()
        s = self.read()
        cmds = [h["command"] for g in s["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertEqual([c for c in cmds if "other/tool.py" in c], cmds,
                         "uninstall must leave another tool's PreToolUse hook exactly as "
                         "it found it")

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

    def test_precompact_hook_is_wired_and_removed(self):
        self.do_install()
        s = self.read()
        self.assertTrue(any("precompact.sh" in h["command"]
                            for g in s["hooks"]["PreCompact"] for h in g["hooks"]),
                        "the PreCompact capture must be wired")
        self.do_uninstall()
        s = self.read()
        self.assertNotIn("PreCompact", s.get("hooks", {}),
                         "uninstall created no PreCompact key for the user, so it must "
                         "not leave an empty one behind")

    def test_a_users_own_precompact_hook_survives_both_directions(self):
        """`PreCompact` is a new event key for this package, and a new key is exactly
        where an installer forgets that someone else may already be there. It is also the
        event most likely to be occupied: checkpointing something before a compaction is
        the obvious use for it, and at least one other tool ships such a hook."""
        self.write_settings({"hooks": {"PreCompact": [FOREIGN_HOOK]}})
        self.do_install()
        s = self.read()
        cmds = [h["command"] for g in s["hooks"]["PreCompact"] for h in g["hooks"]]
        self.assertTrue(any("other/tool.py" in c for c in cmds),
                        "install must not displace another tool's PreCompact hook")
        self.assertTrue(any("precompact.sh" in c for c in cmds))
        self.do_uninstall()
        s = self.read()
        cmds = [h["command"] for g in s["hooks"]["PreCompact"] for h in g["hooks"]]
        self.assertEqual([c for c in cmds if "other/tool.py" in c], cmds,
                         "uninstall must leave the user's PreCompact hook and only that")

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


class DoctrineTest(unittest.TestCase):
    """The doctrine stanza the hooks refer to, written where the model actually reads it.

    The hooks fire reminders that name three habits; before this existed those habits
    lived only in a stanza the author had hand-typed into his own ~/.claude/CLAUDE.md, so
    every other installation got a reminder pointing at a rule it had never been given.

    Nothing here hardcodes the stanza. The expected bytes come from
    `installer.render_doctrine(APP_HOME)`, so rewording the doctrine does not fail these
    tests -- only losing it, duplicating it, or failing to take it back out does.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.claude = root / "claude"
        self.bin = root / "bin"
        self.state = root / "state"
        self.claude.mkdir()
        self.bin.mkdir()
        self.md = self.claude / "CLAUDE.md"

    def tearDown(self):
        self.tmp.cleanup()

    def do_install(self, **kw):
        return installer.install(APP_HOME, str(self.claude), str(self.bin),
                                 str(self.state), **kw)

    def do_uninstall(self):
        return installer.uninstall(APP_HOME, str(self.claude), str(self.bin),
                                   str(self.state))

    def manifest(self):
        return json.loads((self.state / "install-manifest.json").read_text(encoding="utf-8"))

    def block(self):
        return installer.render_doctrine(APP_HOME)

    def backups(self):
        return sorted(p.name for p in self.claude.iterdir()
                      if p.name.startswith("CLAUDE.md" + installer.BACKUP_PREFIX))

    # ---------------------------------------------------------------- install

    def test_a_fresh_claude_directory_gets_the_block(self):
        rep = self.do_install()
        self.assertTrue(self.md.exists(), "install wrote no CLAUDE.md at all")
        text = self.md.read_text(encoding="utf-8")
        self.assertIn(self.block(), text)
        self.assertIn(installer.DOCTRINE_HEADING, text)
        # The habits the hooks name, so a reminder cannot point at a rule that is absent.
        for habit in ("Before any major implementation", "During work",
                      "When a skill misfires"):
            self.assertIn(habit, text, "the doctrine lost the habit %r" % habit)
        self.assertIn(str(self.md), rep["doctrine"])
        self.assertEqual(self.manifest()["doctrine"], "installed")
        self.assertIs(self.manifest()["doctrine_created"], True)

    def test_the_checkout_path_is_substituted_not_left_as_a_placeholder(self):
        """The stanza names the clone twice. A hardcoded ~/claude-skill-compounder is
        wrong for anyone who cloned somewhere else, and `{app_home}` is wrong for
        everyone."""
        self.do_install()
        text = self.md.read_text(encoding="utf-8")
        self.assertNotIn("{app_home}", text)
        self.assertIn(APP_HOME + "/hooks/compound-improvement.sh", text)

    def test_a_second_install_leaves_the_file_byte_identical(self):
        self.do_install()
        first = self.md.read_bytes()
        self.do_install()
        self.assertEqual(self.md.read_bytes(), first,
                         "a second install rewrote CLAUDE.md")
        self.assertEqual(self.backups(), [],
                         "a run that changed nothing wrote a backup anyway")

    def test_existing_content_is_preserved_before_and_after_the_block(self):
        before = "# My own notes\n\nSome rule of mine.\n"
        after = "\n## A section of mine after it\n\nMore of my words.\n"
        self.md.write_text(before + "\n" + self.block() + "\n" + after, encoding="utf-8")

        self.do_install()
        text = self.md.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(before), "content before the block was rewritten")
        self.assertTrue(text.endswith(after), "content after the block was rewritten")
        self.assertEqual(text.count(installer.DOCTRINE_START), 1)

        self.do_uninstall()
        left = self.md.read_text(encoding="utf-8")
        self.assertNotIn(installer.DOCTRINE_START, left)
        self.assertIn("Some rule of mine.", left)
        self.assertIn("More of my words.", left)

    def test_an_existing_file_is_backed_up_before_it_is_touched(self):
        self.md.write_text("# Mine\n", encoding="utf-8")
        os.environ["SKILL_COMPOUNDER_NOW"] = "1700000000"
        try:
            self.do_install()
        finally:
            del os.environ["SKILL_COMPOUNDER_NOW"]
        saved = self.backups()
        self.assertEqual(len(saved), 1, "no stamped backup of CLAUDE.md: %s" % saved)
        self.assertIn("20", saved[0].split(installer.BACKUP_PREFIX)[1][:2])
        self.assertEqual((self.claude / saved[0]).read_text(encoding="utf-8"), "# Mine\n")

    # ------------------------------------------------------------- user-owned

    def test_a_stanza_the_user_wrote_by_hand_is_detected_and_not_duplicated(self):
        """The author's own machine: the heading is there, outside any marker of ours.
        Appending would hand that session the doctrine twice."""
        mine = ("# Global rules\n\n%s\n\nMy own wording of the habits.\n"
                % installer.DOCTRINE_HEADING)
        self.md.write_text(mine, encoding="utf-8")

        rep = self.do_install()

        self.assertEqual(self.md.read_text(encoding="utf-8"), mine,
                         "a user-owned CLAUDE.md was modified")
        self.assertNotIn(installer.DOCTRINE_START, self.md.read_text(encoding="utf-8"))
        self.assertEqual(self.manifest()["doctrine"], "user-owned")
        self.assertIn("already has its own", rep["doctrine"])

    def test_our_own_block_is_not_read_as_the_users_stanza(self):
        """The heading is inside our block too. Looking for it across the whole file
        would make every install after the first report `user-owned` and never update."""
        self.do_install()
        self.do_install()
        self.assertEqual(self.manifest()["doctrine"], "installed")

    def test_an_unterminated_marker_is_left_alone(self):
        text = "# Mine\n\n%s\nhalf a block\n" % installer.DOCTRINE_START
        self.md.write_text(text, encoding="utf-8")
        rep = self.do_install()
        self.assertEqual(self.md.read_text(encoding="utf-8"), text)
        self.assertEqual(self.manifest()["doctrine"], "left-alone")
        self.assertIn("LEFT ALONE", rep["doctrine"])

    # ------------------------------------------------------------- opting out

    def test_no_doctrine_writes_nothing(self):
        rep = self.do_install(doctrine=False)
        self.assertFalse(self.md.exists(), "--no-doctrine still wrote CLAUDE.md")
        self.assertEqual(self.manifest()["doctrine"], "declined")
        self.assertIn("SKILL_COMPOUNDER_DOCTRINE", rep["doctrine"])

    def test_the_environment_switch_turns_it_off_too(self):
        os.environ["SKILL_COMPOUNDER_DOCTRINE"] = "0"
        try:
            self.do_install()
        finally:
            del os.environ["SKILL_COMPOUNDER_DOCTRINE"]
        self.assertFalse(self.md.exists())
        self.assertEqual(self.manifest()["doctrine"], "declined")

    # -------------------------------------------------------------- uninstall

    def test_uninstall_removes_only_the_block(self):
        self.md.write_text("# Mine\n\nkeep me\n", encoding="utf-8")
        self.do_install()
        self.assertIn(installer.DOCTRINE_START, self.md.read_text(encoding="utf-8"))

        rep = self.do_uninstall()

        self.assertTrue(self.md.exists(), "a file we did not create was deleted")
        self.assertEqual(self.md.read_text(encoding="utf-8"), "# Mine\n\nkeep me\n")
        self.assertIn("block removed", rep["doctrine"])
        self.assertNotIn("doctrine", self.manifest())

    def test_uninstall_deletes_a_file_it_created_and_nothing_else_is_in(self):
        self.do_install()
        self.do_uninstall()
        self.assertFalse(self.md.exists(),
                         "the file we created, holding only our block, was left behind")

    def test_uninstall_keeps_a_file_it_created_that_the_user_has_since_written_in(self):
        self.do_install()
        self.md.write_text(self.md.read_text(encoding="utf-8") + "\n# Since then\n",
                           encoding="utf-8")
        self.do_uninstall()
        self.assertTrue(self.md.exists())
        self.assertIn("# Since then", self.md.read_text(encoding="utf-8"))
        self.assertNotIn(installer.DOCTRINE_START, self.md.read_text(encoding="utf-8"))

    def test_uninstall_leaves_a_claude_md_that_was_never_ours(self):
        self.md.write_text("# Nothing to do with us\n", encoding="utf-8")
        rep = self.do_uninstall()
        self.assertEqual(self.md.read_text(encoding="utf-8"), "# Nothing to do with us\n")
        self.assertIn("no block of ours", rep["doctrine"])

    # ---------------------------------------------------------------- symlink

    def test_a_symlinked_claude_md_is_written_through_not_over(self):
        """stow and chezmoi present CLAUDE.md as a link into a dotfiles repo, exactly as
        they do settings.json. Replacing the link orphans the source with exit 0."""
        dotfiles = Path(self.tmp.name) / "dotfiles"
        dotfiles.mkdir()
        source = dotfiles / "CLAUDE.md"
        source.write_text("# from dotfiles\n", encoding="utf-8")
        self.md.symlink_to(source)

        self.do_install()

        self.assertTrue(self.md.is_symlink(), "the symlink was replaced by a real file")
        self.assertEqual(os.path.realpath(str(self.md)), os.path.realpath(str(source)))
        self.assertIn(self.block(), source.read_text(encoding="utf-8"))
        self.assertTrue(source.read_text(encoding="utf-8").startswith("# from dotfiles"))

        self.do_uninstall()

        self.assertTrue(self.md.is_symlink(), "uninstall replaced the symlink")
        self.assertEqual(source.read_text(encoding="utf-8"), "# from dotfiles\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
