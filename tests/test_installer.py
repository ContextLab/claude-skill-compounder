#!/usr/bin/env python3
"""Real install/uninstall against a real temporary Claude directory.

No mocks: every test writes an actual settings.json, runs the actual installer,
and reads the file back off disk."""

import json
import os
import shutil
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


def local_surfer_source():
    """A real claude-history-surfer git checkout to clone FROM, with no network.

    The dependency step really clones and really runs history-surfer's own installer, so
    the only honest source is a real checkout of it. Four places are tried, in the order
    of how much they prove: an explicit override, the checkout whatever `surfer` is on
    PATH resolves back to, and the two default homes its own install.sh uses. Returns
    None when the machine has none, which is a machine where this cannot be tested
    without the network.
    """
    seen = []
    override = os.environ.get("SKILL_COMPOUNDER_SURFER_SRC", "").strip()
    if override:
        seen.append(Path(override).expanduser())
    on_path = shutil.which("surfer")
    if on_path:
        seen.append(Path(os.path.realpath(on_path)).parent.parent)
    seen.append(Path.home() / "claude-history-surfer")
    seen.append(Path.home() / ".claude" / "history-surfer-app")
    for cand in seen:
        if (cand / "scripts" / "setup.py").is_file() and (cand / ".git").exists():
            return cand
    return None


SURFER_SRC = local_surfer_source()
# Resolved at import: SurferTest.setUp narrows PATH, so asking again inside a
# test would answer about the narrowed one and not about the machine.
SURFER_ON_PATH = shutil.which("surfer")
# The checkout that `surfer` resolves back into, when it is one. `_surfer_from_path`
# makes the same walk; this is the test's independent copy of the question "is there a
# real history-surfer behind the CLI on this machine's PATH".
SURFER_PATH_CHECKOUT = None
if SURFER_ON_PATH:
    _cand = Path(os.path.realpath(SURFER_ON_PATH)).parent.parent
    if (_cand / "scripts" / "setup.py").is_file() and (_cand / "history_surfer").is_dir():
        SURFER_PATH_CHECKOUT = _cand


class NoSurferMixin(object):
    """Pin the history-surfer step OFF for every test that is not about it.

    `install()` now installs a dependency, and a test that is checking hook wiring has no
    business cloning a repository over the network to do it -- on a machine with no
    `surfer` this class of test would make one clone per install call. The switch is the
    shipped one (`SKILL_COMPOUNDER_NO_SURFER`), read by the real code path, which is the
    same discipline every other pin in this suite follows. SurferTest below sets it back.
    """

    def pin_surfer_off(self):
        before = os.environ.get(installer.SURFER_SKIP_ENV)
        os.environ[installer.SURFER_SKIP_ENV] = "1"

        def restore():
            if before is None:
                os.environ.pop(installer.SURFER_SKIP_ENV, None)
            else:
                os.environ[installer.SURFER_SKIP_ENV] = before
        self.addCleanup(restore)


class InstallerTest(NoSurferMixin, unittest.TestCase):

    def setUp(self):
        self.pin_surfer_off()
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
        matcher lists POSITIONALLY, so a reordering here is a drift failure there.

        Three entries now, and the shape of the list is the claim: the two that can DENY
        a tool call come first, and the one that only states a fact -- the reminder --
        comes after them. A gate that ran after a hook which had already emitted context
        would spend that context on a call it then refused. The mission left this list on
        2026-10-03, with the repeat gate; both are the mod's job.
        """
        self.do_install()
        pre = [h["command"] for g in self.read()["hooks"]["PreToolUse"] for h in g["hooks"]]
        names = [c.rsplit("/", 1)[-1].strip('"') for c in pre]
        self.assertEqual(names, ["claim-gate.sh", "doc-gate.sh", "remind.sh"])

    def test_the_repeat_gate_is_not_wired_and_an_older_install_s_entries_are_stripped(self):
        """`repeat-gate.sh` left the wiring on 2026-10-03, when the lesson moved to the
        function hooks in mod/compound. Not adding it is half of that; the other
        half is an UPGRADE, where settings.json already holds the three entries an older
        install wrote. Left there, the old hook would run beside the mod and announce
        every fix twice, with nothing on any surface to say why."""
        old = {"hooks": [{"type": "command", "timeout": 10,
                          "command": '"%s/hooks/repeat-gate.sh"' % APP_HOME}]}
        self.write_settings({"hooks": {
            "PreToolUse": [old, FOREIGN_HOOK],
            "PostToolUse": [dict(old, matcher="Bash|Skill|mcp__.*")],
            "PostToolUseFailure": [dict(old, matcher="Bash|Skill|mcp__.*")]}})
        self.do_install()
        hooks = self.read()["hooks"]
        wired = [(event, h["command"]) for event, groups in hooks.items()
                 for g in groups for h in g.get("hooks", []) if "repeat-gate.sh" in h["command"]]
        self.assertEqual(wired, [], "repeat-gate.sh is still wired after an install")
        self.assertTrue(any("other/tool.py" in h["command"]
                            for g in hooks["PreToolUse"] for h in g["hooks"]),
                        "the strip took somebody else's PreToolUse hook with it")

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
        """`env` is no longer a key install leaves alone -- it adds the mod's directory
        to one path list there -- so what is pinned is that the user's own entry is the
        same after install and that uninstall hands the object back exactly."""
        self.write_settings({"model": "opus", "env": {"FOO": "bar"}})
        self.do_install()
        s = self.read()
        self.assertEqual(s["model"], "opus")
        self.assertEqual(s["env"]["FOO"], "bar")
        self.assertEqual(sorted(s["env"]), ["CLAUDE_CODE_PLUGIN_DIRS", "FOO"])
        self.do_uninstall()
        self.assertEqual(self.read()["env"], {"FOO": "bar"})

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


class DoctrineTest(NoSurferMixin, unittest.TestCase):
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
        self.pin_surfer_off()

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


# ---------------------------------------------------- the mission: unwired, and the mod

MISSION = APP / "hooks" / "mission.sh"
# The five events hooks/mission.sh WAS wired to until 2026-10-03. Named here rather than
# derived, because what these tests pin is that an older install's entry comes off every
# one of them, and a list derived from the installer would agree with an installer that
# forgot one.
MISSION_EVENTS = ("SessionStart", "SubagentStart", "UserPromptSubmit", "PreToolUse", "Stop")
MOD_PATH = str(Path(APP_HOME) / "mod" / "compound")
MOD_KEY = "CLAUDE_CODE_PLUGIN_DIRS"
FOREIGN_PLUGIN = "/some/other/plugin-dir"


def old_install_entries():
    """The hooks an install from before 2026-10-03 left in settings.json: five
    `mission.sh` entries and three `repeat-gate.sh` entries, each beside a hook of the
    user's own on the same event."""
    def ours(script, matcher=None):
        group = {"hooks": [{"type": "command", "timeout": 10,
                            "command": '"%s/hooks/%s"' % (APP_HOME, script)}]}
        if matcher is not None:
            group["matcher"] = matcher
        return group
    learn = "Bash|Skill|mcp__.*"
    return {"SessionStart": [FOREIGN_HOOK, ours("mission.sh")],
            "SubagentStart": [FOREIGN_HOOK, ours("mission.sh")],
            "UserPromptSubmit": [FOREIGN_HOOK, ours("mission.sh")],
            "PreToolUse": [FOREIGN_HOOK, ours("repeat-gate.sh"), ours("mission.sh")],
            "PostToolUse": [FOREIGN_HOOK, ours("repeat-gate.sh", learn)],
            "PostToolUseFailure": [FOREIGN_HOOK, ours("repeat-gate.sh", learn)],
            "Stop": [FOREIGN_HOOK, ours("mission.sh")]}


class _ScratchInstall(NoSurferMixin):
    def setUp(self):
        self.pin_surfer_off()
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

    def do_install(self, home=APP_HOME):
        return installer.install(home, str(self.claude), str(self.bin), str(self.state))

    def do_uninstall(self, home=APP_HOME):
        return installer.uninstall(home, str(self.claude), str(self.bin), str(self.state))

    def manifest(self):
        return json.loads((self.state / "install-manifest.json").read_text(encoding="utf-8"))

    def entries(self, event, marker="mission.sh"):
        s = self.read()
        return [(g.get("matcher"), h["command"])
                for g in s.get("hooks", {}).get(event, []) for h in g["hooks"]
                if marker in h["command"]]

    def commands(self):
        return [(event, h["command"]) for event, groups in self.read().get("hooks", {}).items()
                for g in groups for h in g.get("hooks", [])]


@unittest.skipUnless(MISSION.is_file(), "hooks/mission.sh is not in this checkout")
class MissionRetiredTest(_ScratchInstall, unittest.TestCase):
    """`hooks/mission.sh` left the wiring on 2026-10-03: the mission is the mod's job.

    Not adding it is half of that. The other half is an UPGRADE, where settings.json
    already holds the five entries an older install wrote, on two event keys nothing of
    ours uses any more. Left there, the shell hook would state the mission beside the mod
    and every moment would land twice.
    """

    def test_the_mission_script_is_wired_to_no_event_at_all(self):
        self.do_install()
        self.assertEqual([(e, c) for e, c in self.commands() if "mission.sh" in c], [],
                         "hooks/mission.sh is still wired by an install")

    def test_a_fresh_install_writes_neither_of_the_two_keys_only_the_mission_used(self):
        """SessionStart and SubagentStart carried the mission and nothing else of ours.
        A key written holding an empty list is litter in someone's settings.json."""
        self.do_install()
        self.do_install()
        hooks = self.read()["hooks"]
        for event in ("SessionStart", "SubagentStart"):
            self.assertNotIn(event, hooks, "install wrote a %s key with nothing on it" % event)

    def test_the_marker_is_named_retired_so_doctor_does_not_expect_it_wired(self):
        """`skillforge doctor` reads every `*_MARKER = "x.sh"` line of the installer as a
        script that must be wired. These two must not be on that list."""
        text = (APP / "skill_compounder" / "installer.py").read_text(encoding="utf-8")
        self.assertIn('MISSION_RETIRED = "mission.sh"', text)
        self.assertIn('REPEAT_GATE_RETIRED = "repeat-gate.sh"', text)
        self.assertNotRegex(text, r'(?m)^[A-Z_]*MARKER = "(mission|repeat-gate)\.sh"')

    def test_an_older_install_s_eight_entries_are_stripped_and_foreign_hooks_survive(self):
        """Five `mission.sh` entries and three `repeat-gate.sh` entries, each beside a
        hook of the user's on the same event. All eight come off; all seven of the
        user's stay, on every event including the two only the mission used."""
        old = old_install_entries()
        self.write_settings({"hooks": old})
        before = [c for _e, c in self.commands()]
        self.assertEqual(sum("mission.sh" in c for c in before), 5)
        self.assertEqual(sum("repeat-gate.sh" in c for c in before), 3)
        self.do_install()
        after = self.commands()
        self.assertEqual([(e, c) for e, c in after
                          if "mission.sh" in c or "repeat-gate.sh" in c], [],
                         "an older install's retired entries survived an upgrade")
        for event in old:
            self.assertEqual(len(self.entries(event, "other/tool.py")), 1,
                             "the strip took the user's own %s hook with it" % event)

    def test_uninstall_strips_an_older_install_s_entries_too(self):
        """A user who never upgrades and simply uninstalls with a newer checkout must not
        be left with eight entries pointing at this package."""
        old = old_install_entries()
        self.write_settings({"hooks": old})
        self.do_uninstall()
        self.assertEqual(sorted(c for _e, c in self.commands()),
                         sorted([FOREIGN_HOOK["hooks"][0]["command"]] * len(old)),
                         "uninstall left a retired entry, or took a foreign one")

    def test_an_upgrade_deletes_a_key_that_held_only_the_old_mission_entry(self):
        """The older install CREATED SessionStart and SubagentStart. Stripped of the one
        entry they held, they are ours to remove rather than leave as empty lists."""
        old = old_install_entries()
        self.write_settings({"hooks": {"SessionStart": old["SessionStart"][1:],
                                       "SubagentStart": old["SubagentStart"][1:]}})
        self.do_install()
        hooks = self.read()["hooks"]
        for event in ("SessionStart", "SubagentStart"):
            self.assertNotIn(event, hooks,
                             "an upgrade left an empty %s key behind" % event)

    def test_a_users_own_session_start_hook_survives_both_directions(self):
        self.write_settings({"hooks": {"SessionStart": [FOREIGN_HOOK],
                                       "SubagentStart": [FOREIGN_HOOK]}})
        self.do_install()
        self.do_uninstall()
        hooks = self.read()["hooks"]
        for event in ("SessionStart", "SubagentStart"):
            self.assertEqual(hooks[event], [FOREIGN_HOOK],
                             "the user's own %s hook did not survive" % event)

    def test_an_empty_event_key_the_user_put_there_stays_theirs(self):
        self.write_settings({"hooks": {"SessionStart": [], "SubagentStart": []}})
        self.do_install()
        self.do_install()
        self.do_uninstall()
        hooks = self.read().get("hooks", {})
        for event in ("SessionStart", "SubagentStart"):
            self.assertIn(event, hooks,
                          "an empty %s list the user wrote was deleted" % event)
            self.assertEqual(hooks[event], [])

    def test_a_key_the_manifest_records_as_the_users_is_kept_through_an_upgrade(self):
        """The older install found an EMPTY SessionStart list of the user's, recorded the
        key as theirs and added its entry. The upgrade strips that entry, and the key is
        still theirs: emptied, never deleted."""
        self.state.mkdir()
        (self.state / "install-manifest.json").write_text(json.dumps(
            {"preexisting_hook_events": ["SessionStart"]}), encoding="utf-8")
        old = old_install_entries()
        self.write_settings({"hooks": {"SessionStart": old["SessionStart"][1:],
                                       "SubagentStart": old["SubagentStart"][1:]}})
        self.do_install()
        hooks = self.read()["hooks"]
        self.assertEqual(hooks.get("SessionStart"), [])
        self.assertNotIn("SubagentStart", hooks)


@unittest.skipUnless(Path(MOD_PATH).is_dir(), "mod/compound is not in this checkout")
class ModEnableTest(_ScratchInstall, unittest.TestCase):
    """The settings.json install path enables the mod by adding ONE ELEMENT to a path
    list that is not this package's: `env.CLAUDE_CODE_PLUGIN_DIRS`, separated by
    `os.pathsep`. Every element it did not add stays, in order, in both directions."""

    def dirs(self):
        return self.read().get("env", {}).get(MOD_KEY, "").split(os.pathsep)

    def test_install_adds_the_mod_directory_and_records_exactly_what_it_added(self):
        rep = self.do_install()
        self.assertEqual(self.read()["env"], {MOD_KEY: MOD_PATH})
        self.assertEqual(self.manifest()["mod_plugin_dir"], MOD_PATH)
        self.assertIn(MOD_PATH, rep["mod"])
        self.assertTrue((Path(MOD_PATH) / "hooks" / "hooks.json").is_file(),
                        "the directory install enables is not a plugin of hooks")

    def test_the_suffix_is_the_constant_doctor_reads_and_is_not_a_marker(self):
        self.assertEqual(installer.MOD_DIR, "mod/compound")
        self.assertTrue(MOD_PATH.endswith("/" + installer.MOD_DIR))
        text = (APP / "skill_compounder" / "installer.py").read_text(encoding="utf-8")
        self.assertRegex(text, r'(?m)^MOD_DIR = "mod/compound"$',
                         "bin/skillforge reads this line with sed; it must stay one line")

    def test_it_lands_beside_a_foreign_element_and_leaves_with_only_itself(self):
        # Written the way the installer writes -- two-space indent, trailing newline --
        # so the byte comparison below is about content and not about a final "\n".
        self.settings.write_text(json.dumps(
            {"env": {"FOO": "bar", MOD_KEY: FOREIGN_PLUGIN}}, indent=2) + "\n",
            encoding="utf-8")
        original = self.settings.read_bytes()
        self.do_install()
        self.assertEqual(self.dirs(), [FOREIGN_PLUGIN, MOD_PATH])
        self.assertEqual(self.read()["env"]["FOO"], "bar")
        self.do_uninstall()
        self.assertEqual(self.read()["env"], {"FOO": "bar", MOD_KEY: FOREIGN_PLUGIN})
        self.assertEqual(self.settings.read_bytes(), original,
                         "install then uninstall did not hand back the file it was given")

    def test_two_foreign_elements_keep_their_order_around_ours(self):
        both = os.pathsep.join([FOREIGN_PLUGIN, "/another/one"])
        self.write_settings({"env": {MOD_KEY: both}})
        self.do_install()
        self.assertEqual(self.dirs(), [FOREIGN_PLUGIN, "/another/one", MOD_PATH])
        self.do_uninstall()
        self.assertEqual(self.read()["env"][MOD_KEY], both)

    def test_installing_twice_is_byte_identical_and_never_duplicates_ours(self):
        self.write_settings({"env": {MOD_KEY: FOREIGN_PLUGIN}})
        self.do_install()
        first = self.settings.read_bytes()
        self.do_install()
        self.assertEqual(self.settings.read_bytes(), first,
                         "a second install changed settings.json")
        self.assertEqual(self.dirs().count(MOD_PATH), 1)

    def test_an_element_already_there_is_not_rewritten_even_to_tidy_it(self):
        """Ours is present and the user's value carries an empty element. Nothing to add,
        so nothing is written into that value at all."""
        untidy = os.pathsep.join([FOREIGN_PLUGIN, "", MOD_PATH])
        self.write_settings({"env": {MOD_KEY: untidy}})
        self.do_install()
        self.assertEqual(self.read()["env"][MOD_KEY], untidy)

    def test_uninstall_drops_the_key_and_then_env_when_they_empty(self):
        self.write_settings({"model": "opus"})
        self.do_install()
        self.assertIn("env", self.read())
        self.do_uninstall()
        self.assertEqual(self.read(), {"model": "opus"})

    def test_uninstall_drops_the_key_and_keeps_an_env_that_holds_something_else(self):
        self.write_settings({"env": {"FOO": "bar"}})
        self.do_install()
        self.do_uninstall()
        self.assertEqual(self.read()["env"], {"FOO": "bar"})

    def test_uninstall_removes_the_recorded_path_when_the_checkout_has_moved(self):
        """The manifest records the exact string that was added, so a checkout that moved
        can still take its own element out -- and still leaves the one beside it."""
        self.do_install()
        gone = "/where/the/checkout/used/to/be/mod/compound"
        m = self.manifest()
        m["mod_plugin_dir"] = gone
        (self.state / "install-manifest.json").write_text(json.dumps(m), encoding="utf-8")
        s = self.read()
        s["env"][MOD_KEY] = os.pathsep.join([FOREIGN_PLUGIN, gone])
        self.write_settings(s)
        self.do_uninstall()
        self.assertEqual(self.read()["env"], {MOD_KEY: FOREIGN_PLUGIN})
        self.assertNotIn("mod_plugin_dir", self.manifest())

    def test_a_reinstall_from_a_moved_checkout_replaces_the_recorded_path(self):
        self.do_install()
        gone = "/where/the/checkout/used/to/be/mod/compound"
        m = self.manifest()
        m["mod_plugin_dir"] = gone
        (self.state / "install-manifest.json").write_text(json.dumps(m), encoding="utf-8")
        s = self.read()
        s["env"][MOD_KEY] = os.pathsep.join([gone, FOREIGN_PLUGIN])
        self.write_settings(s)
        self.do_install()
        self.assertEqual(self.dirs(), [FOREIGN_PLUGIN, MOD_PATH])
        self.assertEqual(self.manifest()["mod_plugin_dir"], MOD_PATH)

    def test_a_path_that_merely_ends_like_ours_is_somebody_elses(self):
        lookalike = "/elsewhere/mod/compound"
        self.write_settings({"env": {MOD_KEY: lookalike}})
        self.do_install()
        self.assertEqual(self.dirs(), [lookalike, MOD_PATH])
        self.do_uninstall()
        self.assertEqual(self.read()["env"], {MOD_KEY: lookalike})

    def test_a_checkout_without_the_mod_installs_and_touches_no_env(self):
        import shutil as _shutil
        dest = Path(self.tmp.name) / "checkout"
        _shutil.copytree(APP_HOME, dest, symlinks=True,
                         ignore=_shutil.ignore_patterns(".git", "__pycache__", "*.pyc",
                                                        "mod", "node_modules"))
        self.write_settings({"env": {MOD_KEY: FOREIGN_PLUGIN}})
        rep = self.do_install(home=str(dest))
        self.assertEqual(self.read()["env"], {MOD_KEY: FOREIGN_PLUGIN})
        self.assertIn("not enabled", rep["mod"])
        self.assertNotIn("mod_plugin_dir", self.manifest())

    def test_a_malformed_env_makes_install_refuse_and_changes_nothing(self):
        for bad in (["not", "an", "object"], "a string", 7):
            self.write_settings({"model": "opus", "env": bad})
            before = self.settings.read_bytes()
            with self.assertRaises(installer.SettingsShapeError) as ctx:
                self.do_install()
            self.assertIn('"env"', str(ctx.exception))
            self.assertEqual(self.settings.read_bytes(), before)
            self.assertEqual(list((self.claude / "skills").glob("*"))
                             if (self.claude / "skills").exists() else [], [],
                             "install refused and linked skills anyway")

    def test_a_plugin_dirs_value_that_is_not_a_string_makes_install_refuse(self):
        self.write_settings({"env": {MOD_KEY: ["/a", "/b"]}})
        before = self.settings.read_bytes()
        with self.assertRaises(installer.SettingsShapeError) as ctx:
            self.do_install()
        self.assertIn(MOD_KEY, str(ctx.exception))
        self.assertEqual(self.settings.read_bytes(), before)

    def test_uninstall_never_refuses_on_a_malformed_env(self):
        """A settings.json the user broke by hand is exactly when they most need to be
        able to take this package off. The hooks come off; the key we cannot read stays
        as it was and the report says so."""
        self.do_install()
        for bad in (["not", "an", "object"], {MOD_KEY: 7}):
            s = self.read()
            s["env"] = bad
            self.write_settings(s)
            rep = self.do_uninstall()
            self.assertIn("left alone", rep["mod"])
            self.assertEqual(self.read()["env"], bad)
            self.assertNotIn("hooks", self.read())
            self.do_install_over(bad)

    def do_install_over(self, bad):
        """Put a clean install back so the loop above can break it a second way."""
        self.write_settings({})
        self.do_install()


# --------------------------------------------------------------- the surfer dependency

class SurferTest(unittest.TestCase):
    """history-surfer is installed as a real dependency, from a real git clone.

    No fixture and no fake `surfer`: the source is a real claude-history-surfer checkout
    (`SKILL_COMPOUNDER_SURFER_URL` points the step at it, which is the same role
    `SKILL_COMPOUNDER_REPO_URL` plays for install.sh), and the assertions are that its
    real CLI lands in the temp bin directory and its real hooks land in the temp
    settings.json. The offline test needs no source at all and runs everywhere.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.claude = root / "claude"
        self.bin = root / "bin"
        self.state = root / "state"
        self.surfer_home = root / "app" / "claude-history-surfer"
        self.claude.mkdir()
        self.bin.mkdir()
        self.settings = self.claude / "settings.json"
        self.set_env(installer.SURFER_HOME_ENV, str(self.surfer_home))
        # `_surfer_store` honours this, and an operator who has one exported would send
        # both `_surfer_has_store` and history-surfer's own scaffolding at their REAL
        # prompt store. The store under test is the one below the temp claude dir.
        self.set_env("CLAUDE_HISTORY_SURFER_DIR", None)
        # `install_surfer` asks PATH first, and this process's PATH has whatever the
        # developer has installed on it. Narrowed so the clone branch is the one under
        # test rather than whichever machine happens to be running it.
        self.set_env("PATH", "/usr/bin:/bin")

    def tearDown(self):
        self.tmp.cleanup()

    def set_env(self, key, value):
        before = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

        def restore():
            if before is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = before
        self.addCleanup(restore)

    def do_install(self):
        return installer.install(APP_HOME, str(self.claude), str(self.bin),
                                 str(self.state))

    def manifest(self):
        return json.loads((self.state / "install-manifest.json").read_text(encoding="utf-8"))

    def read(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ the real thing

    @unittest.skipUnless(SURFER_SRC, "no local claude-history-surfer checkout to clone "
                                     "from (set SKILL_COMPOUNDER_SURFER_SRC)")
    def test_it_clones_and_wires_history_surfer_into_the_same_directories(self):
        self.set_env(installer.SURFER_URL_ENV, str(SURFER_SRC))
        rep = self.do_install()

        self.assertTrue((self.surfer_home / "scripts" / "setup.py").is_file(),
                        "nothing was cloned: %s" % rep["surfer"])
        cli = self.bin / "surfer"
        self.assertTrue(cli.exists(), "surfer did not land in %s: %s"
                        % (self.bin, rep["surfer"]))
        self.assertTrue(os.access(str(os.path.realpath(str(cli))), os.X_OK))

        # Its own hooks, in the settings.json this install was pointed at -- not the
        # developer's. Two wirings in one file is the whole point of handing its
        # installer the same --claude-dir.
        cmds = [h["command"] for groups in self.read()["hooks"].values()
                for g in groups for h in g["hooks"]]
        self.assertTrue(any("log_prompt.py" in c for c in cmds),
                        "history-surfer's capture hook is not wired: %r" % cmds)
        self.assertTrue(any("flush.py" in c for c in cmds),
                        "history-surfer's flush hook is not wired: %r" % cmds)
        # And ours are still there beside them.
        self.assertTrue(any("compound-improvement.sh" in c for c in cmds),
                        "our own wiring was lost: %r" % cmds)

        # The store it scaffolds is under the claude dir it was given, which is what makes
        # `surfer` and the mission read one file rather than two.
        self.assertTrue((self.claude / "history-surfer" / "projects").is_dir())

        record = self.manifest()["surfer"]
        self.assertEqual(record["home"], str(self.surfer_home))
        self.assertEqual(record["url"], str(SURFER_SRC))
        self.assertTrue(record.get("installed"))
        self.assertRegex(record["sha"], r"^[0-9a-f]{40}$",
                         "the manifest must pin the commit that was installed")

    @unittest.skipUnless(SURFER_SRC, "no local claude-history-surfer checkout to clone "
                                     "from (set SKILL_COMPOUNDER_SURFER_SRC)")
    def test_a_second_install_does_not_clone_again(self):
        self.set_env(installer.SURFER_URL_ENV, str(SURFER_SRC))
        self.do_install()
        marker = self.surfer_home / ".this-checkout-was-not-replaced"
        marker.write_text("x", encoding="utf-8")
        rep = self.do_install()
        self.assertTrue(marker.exists(),
                        "the checkout was replaced on a second install: %s" % rep["surfer"])
        # The second install stops at the target settings.json, which the first one wired.
        self.assertIn("already wired into", rep["surfer"])

    @unittest.skipUnless(SURFER_PATH_CHECKOUT,
                         "no surfer on this machine's PATH that resolves back into a "
                         "history-surfer checkout")
    def test_a_surfer_already_on_path_is_wired_into_the_target_config(self):
        """The defect the 2026-09-03 E2E run found, and the one this asserts is gone.

        `install_surfer` used to return on `shutil.which("surfer")`, so an install into a
        non-default `--claude-dir` on a machine that already had the CLI wired NOTHING
        into that config: no capture hook, so no store, so `hooks/mission.sh` inert
        there. PATH is a fact about the machine; the mission hook needs a fact about the
        config. Nothing here is a fixture: `surfer` reaches PATH as a symlink to the real
        one, and the real checkout behind it runs its own real installer.
        """
        fake_bin = Path(self.tmp.name) / "path-bin"
        fake_bin.mkdir()
        (fake_bin / "surfer").symlink_to(os.path.abspath(SURFER_ON_PATH))
        # git and python live in the ordinary places; only `surfer` is contributed here.
        self.set_env("PATH", os.pathsep.join([str(fake_bin), "/usr/bin", "/bin"]))
        # Proof that no clone was even attempted: this url could not be cloned from.
        self.set_env(installer.SURFER_URL_ENV, "/nowhere-this-must-not-be-reached.git")

        rep = self.do_install()

        self.assertFalse(self.surfer_home.exists(),
                         "a checkout already on this machine must not be cloned again: %s"
                         % rep["surfer"])
        cmds = [h["command"] for groups in self.read()["hooks"].values()
                for g in groups for h in g["hooks"]]
        for marker in installer.SURFER_HOOK_MARKERS:
            self.assertTrue(any(marker in c for c in cmds),
                            "history-surfer's %s is not wired into the target config: "
                            "%s -- %r" % (marker, rep["surfer"], cmds))
        self.assertTrue(any("compound-improvement.sh" in c for c in cmds),
                        "our own wiring was lost: %r" % cmds)
        record = self.manifest()["surfer"]
        self.assertEqual(record["home"], str(SURFER_PATH_CHECKOUT))
        self.assertFalse(record["cloned"],
                         "the manifest claims this package cloned a checkout it reused")
        self.assertEqual(record["url"], "",
                         "the manifest names a source for a checkout it did not clone")

        # And a second install is a no-op on the file, byte for byte: the wiring check
        # reads the target settings.json, so the whole step stops there.
        before = self.settings.read_bytes()
        rep2 = self.do_install()
        self.assertIn("already wired into", rep2["surfer"])
        self.assertEqual(self.settings.read_bytes(), before,
                         "a second install rewrote settings.json: %s" % rep2["surfer"])

    @unittest.skipUnless(SURFER_PATH_CHECKOUT,
                         "no surfer on this machine's PATH that resolves back into a "
                         "history-surfer checkout")
    def test_a_symlinked_settings_json_survives_the_dependencys_own_installer(self):
        """stow / chezmoi / a hand-rolled dotfiles repo present settings.json as a link.

        This package writes THROUGH such a link so the dotfiles source is not orphaned.
        history-surfer's installer renames over the path instead, which replaces the LINK
        -- so the moment this step started really running its installer (rather than
        returning on `shutil.which`), a stowed settings.json became a regular file. The
        real dependency really runs here; nothing about this is simulated.
        """
        real = Path(self.tmp.name) / "dotfiles" / "settings.json"
        real.parent.mkdir(parents=True)
        real.write_text(json.dumps({"model": "opus"}, indent=2) + "\n", encoding="utf-8")
        self.settings.symlink_to(str(real))

        fake_bin = Path(self.tmp.name) / "path-bin"
        fake_bin.mkdir()
        (fake_bin / "surfer").symlink_to(os.path.abspath(SURFER_ON_PATH))
        self.set_env("PATH", os.pathsep.join([str(fake_bin), "/usr/bin", "/bin"]))
        self.set_env(installer.SURFER_URL_ENV, "/nowhere-this-must-not-be-reached.git")

        rep = self.do_install()

        self.assertTrue(self.settings.is_symlink(),
                        "the dotfiles symlink was replaced by a regular file: %s"
                        % rep["surfer"])
        self.assertEqual(os.path.realpath(str(self.settings)), os.path.realpath(str(real)))
        # And nothing was lost on the way through: the user's key, our wiring and
        # history-surfer's are all in the dotfiles file itself.
        written = json.loads(real.read_text(encoding="utf-8"))
        self.assertEqual(written["model"], "opus")
        cmds = [h["command"] for groups in written["hooks"].values()
                for g in groups for h in g["hooks"]]
        for marker in installer.SURFER_HOOK_MARKERS:
            self.assertTrue(any(marker in c for c in cmds),
                            "%s did not reach the dotfiles file: %r" % (marker, cmds))
        self.assertTrue(any("compound-improvement.sh" in c for c in cmds),
                        "our own wiring did not reach the dotfiles file: %r" % cmds)
        self.assertIn(MOD_PATH, written["env"]["CLAUDE_CODE_PLUGIN_DIRS"].split(os.pathsep),
                      "the mod's directory did not reach the dotfiles file")

    def test_a_half_wired_config_is_not_read_as_wired(self):
        """One of the two markers present is an interrupted install, not a finished one.

        Returning True on it would leave the config half-wired for good, and half-wired
        is a store nothing flushes. No `surfer` is needed to ask this question, so this
        one runs on every machine.
        """
        self.settings.write_text(json.dumps({"hooks": {"UserPromptSubmit": [
            {"hooks": [{"type": "command",
                        "command": "python3 /somewhere/hooks/log_prompt.py"}]}]}},
            indent=2) + "\n", encoding="utf-8")
        self.assertFalse(installer._surfer_wired(self.claude))
        self.set_env(installer.SURFER_URL_ENV,
                     str(Path(self.tmp.name) / "there-is-no-repo-here.git"))
        rep = self.do_install()
        self.assertNotIn("already wired into", rep["surfer"])

    # ------------------------------------------------------------------ failing softly

    def test_no_source_to_clone_from_does_not_fail_the_install(self):
        """The offline case, and the one that must hold everywhere. A user on a plane
        still gets the hooks, the skills and the CLIs; only the mission goes quiet, and
        `skillforge doctor` is where that is visible."""
        self.set_env(installer.SURFER_URL_ENV,
                     str(Path(self.tmp.name) / "there-is-no-repo-here.git"))
        rep = self.do_install()
        self.assertIn("NOT INSTALLED", rep["surfer"])
        self.assertIn("claude-history-surfer", rep["surfer"],
                      "the report must say how to install it by hand")
        self.assertNotIn("errors", rep, "the install itself must have succeeded")
        self.assertTrue((self.claude / "skills" / "skill-compounder").exists(),
                        "the rest of the install did not happen")
        self.assertTrue((self.bin / "skillforge").exists())

    def test_a_failed_clone_leaves_nothing_half_written_behind(self):
        """`_surfer_checkout` reads a directory as installed, so a half-clone left at the
        destination would make every later install skip the step for good."""
        self.set_env(installer.SURFER_URL_ENV,
                     str(Path(self.tmp.name) / "there-is-no-repo-here.git"))
        self.do_install()
        self.assertFalse(self.surfer_home.exists(),
                         "a failed clone left %s behind" % self.surfer_home)
        leftovers = [p.name for p in self.surfer_home.parent.iterdir()] \
            if self.surfer_home.parent.is_dir() else []
        self.assertEqual(leftovers, [], "a temporary clone was left behind: %r" % leftovers)

    def test_the_opt_out_skips_it_entirely(self):
        self.set_env(installer.SURFER_SKIP_ENV, "1")
        self.set_env(installer.SURFER_URL_ENV, "/nowhere-this-must-not-be-reached.git")
        rep = self.do_install()
        self.assertIn(installer.SURFER_SKIP_ENV, rep["surfer"])
        self.assertFalse(self.surfer_home.exists())
        self.assertTrue(self.manifest()["surfer"]["skipped"])

    def test_an_existing_store_is_never_installed_over(self):
        """Prompts already captured mean history-surfer is installed somewhere this run
        cannot see. A second checkout on top of that is how one store becomes two, which
        is exactly what the design's single-source-of-truth rule forbids."""
        projects = self.claude / "history-surfer" / "projects"
        projects.mkdir(parents=True)
        (projects / "some-project.jsonl").write_text(
            '{"ts":"2026-09-03T00:00:00Z","prompt":"hello"}\n', encoding="utf-8")
        self.set_env(installer.SURFER_URL_ENV, "/nowhere-this-must-not-be-reached.git")
        rep = self.do_install()
        self.assertIn("already holds captured prompts", rep["surfer"])
        self.assertFalse(self.surfer_home.exists())

    def test_a_scaffolded_but_empty_store_is_not_mistaken_for_one(self):
        """history-surfer's own installer creates `projects/` empty. Reading that as a
        store would stop this step from ever finishing a job it had only started."""
        (self.claude / "history-surfer" / "projects").mkdir(parents=True)
        self.set_env(installer.SURFER_URL_ENV,
                     str(Path(self.tmp.name) / "there-is-no-repo-here.git"))
        rep = self.do_install()
        self.assertIn("NOT INSTALLED", rep["surfer"],
                      "an empty scaffold was read as a populated store: %s" % rep["surfer"])

    def test_a_directory_of_the_users_at_that_path_is_never_replaced(self):
        """`<app home>/../claude-history-surfer` is a path a user could plausibly have
        made themselves -- this machine had a real checkout there before any of this
        existed. Whatever is at that path, an install must not clobber it, and the report
        must say so rather than exiting 0 over the top of it."""
        self.surfer_home.mkdir(parents=True)
        keep = self.surfer_home / "something-of-mine.txt"
        keep.write_text("do not delete me\n", encoding="utf-8")
        self.set_env(installer.SURFER_URL_ENV, str(SURFER_SRC or "/nowhere.git"))
        rep = self.do_install()
        self.assertTrue(keep.exists(), "the user's own directory was replaced")
        self.assertEqual(keep.read_text(encoding="utf-8"), "do not delete me\n")
        self.assertIn("NOT INSTALLED", rep["surfer"])
        self.assertNotIn("errors", rep, "the install itself must still have succeeded")

    def test_a_setup_py_with_no_package_beside_it_is_not_taken_for_a_checkout(self):
        """The step ENDS BY EXECUTING <home>/scripts/setup.py. A guessable path holding a
        runnable file is not proof of what that file is, so the package directory has to
        be there too -- which is the same file history-surfer's own install.sh uses to
        decide it is inside a clone."""
        (self.surfer_home / "scripts").mkdir(parents=True)
        (self.surfer_home / "scripts" / "setup.py").write_text(
            "raise SystemExit('this must never be run')\n", encoding="utf-8")
        self.set_env(installer.SURFER_URL_ENV,
                     str(Path(self.tmp.name) / "there-is-no-repo-here.git"))
        rep = self.do_install()
        self.assertIn("NOT INSTALLED", rep["surfer"],
                      "a bare scripts/setup.py was run as if it were history-surfer: %s"
                      % rep["surfer"])
        self.assertNotIn("this must never be run", rep["surfer"])

    # ---------------------------------------------------------------------- uninstall

    @unittest.skipUnless(SURFER_SRC, "no local claude-history-surfer checkout to clone "
                                     "from (set SKILL_COMPOUNDER_SURFER_SRC)")
    def test_uninstall_leaves_history_surfer_where_it_is_and_says_so(self):
        """It holds every prompt the user has ever typed. This package did not create
        that data and cannot put it back, so uninstall reports it and removes nothing --
        the same judgement it makes about the state directory."""
        self.set_env(installer.SURFER_URL_ENV, str(SURFER_SRC))
        self.do_install()
        store = self.claude / "history-surfer"
        rep = installer.uninstall(APP_HOME, str(self.claude), str(self.bin),
                                  str(self.state))
        self.assertIn("LEFT IN PLACE", rep["surfer"])
        self.assertIn(str(self.surfer_home), rep["surfer"])
        self.assertIn("--uninstall", rep["surfer"],
                      "the note must say how to remove it")
        self.assertIn(str(store), rep["surfer"],
                      "the note must say where the captured prompts are")
        self.assertTrue(self.surfer_home.is_dir(), "uninstall removed the checkout")
        self.assertTrue((self.bin / "surfer").exists(),
                        "uninstall removed the surfer CLI, which is not ours to remove")
        self.assertTrue(store.is_dir(), "uninstall removed the prompt store")

    def test_uninstall_says_nothing_it_cannot_prove_when_we_never_installed_it(self):
        self.set_env(installer.SURFER_SKIP_ENV, "1")
        self.do_install()
        rep = installer.uninstall(APP_HOME, str(self.claude), str(self.bin),
                                  str(self.state))
        self.assertIn("did not install it", rep["surfer"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
