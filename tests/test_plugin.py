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
import re
import shutil
import subprocess
import sys
import tempfile
import time
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

        # Matchers AND timeouts, on every event. An earlier version compared matchers
        # only for PostToolUse, so a plugin hook could carry a 1-second timeout while the
        # installer's carried 10 and nothing noticed. The timeout is the only backstop
        # against a slow hook, so a silent disagreement there is worth catching.
        for event in settings:
            s_matchers = [g.get("matcher") for g in settings[event]]
            p_matchers = [m for m, _c in plugin[event]]
            self.assertEqual(s_matchers, p_matchers,
                             "%s matchers must agree" % event)

        spec = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        for event in settings:
            s_timeouts = sorted(h.get("timeout") for g in settings[event] for h in g["hooks"])
            p_timeouts = sorted(h.get("timeout")
                                for g in spec["hooks"][event] for h in g["hooks"])
            self.assertEqual(s_timeouts, p_timeouts, "%s timeouts must agree" % event)

    def test_the_claim_gate_is_wired_on_both_paths_to_both_of_its_events(self):
        """The drift check above only proves the two paths AGREE. Two paths that both
        forgot the commit arm agree perfectly, so the wiring is also named here.

        `Stop` gates the closing message; `PreToolUse`/`Bash` gates a `git commit`
        message. The commit arm is not redundant with the Stop arm: a commit message
        never appears in `last_assistant_message`, and both incidents that motivated this
        gate were commit messages.
        """
        plugin = plugin_commands()
        settings = installer.merge_hooks({}, str(APP))["hooks"]
        for event, matcher in (("PreToolUse", "Bash"), ("Stop", None)):
            p_arm = [(m, c) for m, c in plugin.get(event, []) if "claim-gate.sh" in c]
            s_arm = [(g.get("matcher"), h["command"])
                     for g in settings.get(event, []) for h in g["hooks"]
                     if "claim-gate.sh" in h["command"]]
            self.assertEqual(len(p_arm), 1,
                             "hooks.json must wire the claim gate to %s exactly once"
                             % event)
            self.assertEqual(len(s_arm), 1,
                             "the installer must wire the claim gate to %s exactly once"
                             % event)
            self.assertEqual(p_arm[0][0], matcher,
                             "hooks.json %s matcher for the claim gate" % event)
            self.assertEqual(s_arm[0][0], matcher,
                             "installer %s matcher for the claim gate" % event)

    def test_the_reminder_hook_is_wired_on_both_paths_to_both_of_its_events(self):
        """The drift check above only proves the two paths AGREE. Two paths that both
        forgot an arm agree perfectly, so this names the wiring.

        `UserPromptSubmit` carries the keyword arm and `PreToolUse`/`Bash|Write|Edit`
        carries the command and path arms. Dropping either is silent: the hook still runs,
        and reminders of that kind simply never arrive.
        """
        plugin = plugin_commands()
        settings = installer.merge_hooks({}, str(APP))["hooks"]
        for event, matcher in (("UserPromptSubmit", None),
                               ("PreToolUse", "Bash|Write|Edit")):
            p_arm = [(m, c) for m, c in plugin.get(event, []) if "remind.sh" in c]
            s_arm = [(g.get("matcher"), h["command"])
                     for g in settings.get(event, []) for h in g["hooks"]
                     if "remind.sh" in h["command"]]
            self.assertEqual(len(p_arm), 1,
                             "hooks.json must wire the reminder to %s exactly once" % event)
            self.assertEqual(len(s_arm), 1,
                             "the installer must wire the reminder to %s exactly once"
                             % event)
            self.assertEqual(p_arm[0][0], matcher, "hooks.json %s matcher" % event)
            self.assertEqual(s_arm[0][0], matcher, "installer %s matcher" % event)

    def test_the_reminder_hook_is_wired_to_no_other_event(self):
        """It reads a prompt and a call about to happen. On PostToolUse there is nothing
        left to remind anyone about before the fact, and a Stop arm would arrive after the
        turn it applied to."""
        plugin = plugin_commands()
        settings = installer.merge_hooks({}, str(APP))["hooks"]
        for event in ("PostToolUse", "PostToolUseFailure", "Stop"):
            self.assertEqual([c for _m, c in plugin.get(event, []) if "remind.sh" in c], [])
            self.assertEqual([h["command"] for g in settings.get(event, [])
                              for h in g["hooks"] if "remind.sh" in h["command"]], [])

    def test_the_claim_gate_accumulator_arm_is_wired_on_neither_path(self):
        """Its PostToolUse arm records numbers out of every tool RESULT, an Agent/Task
        result included -- the subagent testimony the Stop arm excludes from its evidence
        on purpose. Wiring it on a `*` matcher makes the gate stop catching relayed
        figures, which is the defect it exists for. If it is ever wired it needs a matcher
        that excludes Agent and Task; update this test then, do not delete it."""
        plugin = plugin_commands()
        settings = installer.merge_hooks({}, str(APP))["hooks"]
        self.assertEqual([c for _m, c in plugin.get("PostToolUse", [])
                          if "claim-gate.sh" in c], [])
        self.assertEqual([h["command"] for g in settings.get("PostToolUse", [])
                          for h in g["hooks"] if "claim-gate.sh" in h["command"]], [])

    @unittest.skipUnless(shutil.which("claude"), "claude CLI not on PATH")
    def test_claude_plugin_validate_strict_passes(self):
        proc = subprocess.run(["claude", "plugin", "validate", str(APP), "--strict"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0,
                         "plugin validate --strict failed:\n%s\n%s"
                         % (proc.stdout, proc.stderr))


class SkillFrontmatterTest(unittest.TestCase):
    """Every shipped SKILL.md must have frontmatter that parses as strict YAML.

    Not because Claude Code's loader needs it to. Measured on CLI 2.1.245, that loader
    is lenient: a SKILL.md whose frontmatter `yaml.safe_load` rejects with
    `ScannerError` (an unquoted `: ` inside the description) still loads with its name
    and its **full description intact**, and still triggers normally. Verified by
    building the broken skill twice, once as a project skill under `.claude/skills/`
    and once inside a `--plugin-dir` plugin, and typing its trigger word: both fired
    and returned their sentinel token.

    What the leniency does not survive is a break that costs the parser the
    `description` key itself -- a tab-indented `description:` line, for instance. Then
    the skill still loads and still has a name, but the description is replaced by a
    fallback taken from the body, the trigger clause is gone, and the skill never
    fires. Verified the same way: that skill's trigger word produced nothing. So the
    real failure is a lost trigger, not empty metadata, and it is silent -- no error is
    printed anywhere.

    The reason to require strict YAML anyway is everything downstream that is not
    Claude Code's loader: the forging protocol's own `yaml.safe_load` step, and the
    upstream skills repo's validator. `claude plugin validate --strict` is not that
    check -- locally (2.1.245) it passes a plugin whose skill frontmatter raises
    `ScannerError`, because it reads the plugin manifest and nothing below it.
    """

    def skills(self):
        return sorted(d for d in (APP / "skills").iterdir() if (d / "SKILL.md").is_file())

    def frontmatter(self, skill_dir):
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"), "%s has no frontmatter" % skill_dir.name)
        end = text.index("\n---\n", 3)
        return text[4:end + 1]

    def test_no_unquoted_value_can_break_the_parse(self):
        """Runs everywhere, with no parser dependency."""
        for d in self.skills():
            for line in self.frontmatter(d).split("\n"):
                m = re.match(r"^([A-Za-z0-9_-]+):\s(.*)$", line)
                if not m:
                    continue
                key, value = m.group(1), m.group(2)
                if value[:1] in ('"', "'"):
                    continue
                self.assertNotIn(
                    ": ", value,
                    "%s: `%s` contains an unquoted colon-space, which makes the whole "
                    "frontmatter fail to parse under strict YAML"
                    % (d.name, key))
                self.assertNotIn(
                    value[:1], "[{*&!|>%@`#",
                    "%s: `%s` starts with a YAML indicator and must be quoted"
                    % (d.name, key))

    def test_frontmatter_really_parses(self):
        """The same thing again with a real parser, so the check above cannot drift
        out of agreement with actual YAML."""
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml not installed (CI installs it, so this always runs there)")
        for d in self.skills():
            try:
                spec = yaml.safe_load(self.frontmatter(d))
            except yaml.YAMLError as exc:
                self.fail("%s frontmatter does not parse: %s" % (d.name, exc))
            self.assertIsInstance(spec, dict, "%s frontmatter is not a mapping" % d.name)
            self.assertEqual(spec.get("name"), d.name,
                             "%s: the `name` field must match the directory" % d.name)
            self.assertTrue(spec.get("description"), "%s has no description" % d.name)

    def test_only_portable_frontmatter_keys(self):
        """A key Claude Code does not know is a hard error outside Claude Code."""
        portable = {"name", "description", "license", "allowed-tools",
                    "metadata", "version"}
        for d in self.skills():
            for line in self.frontmatter(d).split("\n"):
                m = re.match(r"^([A-Za-z0-9_-]+):", line)
                if m:
                    self.assertIn(m.group(1), portable,
                                  "%s uses non-portable frontmatter key `%s`"
                                  % (d.name, m.group(1)))


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
            # The counter is one appended byte per edit, so its size is the count.
            counted.append((self.state / "reminders" / "s2.edits").stat().st_size)
        self.assertEqual(counted, [1, 2, 3, 4],
                         "four distinct edits delivered twice each must count as four")

    def test_the_counter_does_not_lose_concurrent_edits(self):
        """A read-modify-write loses most of a burst, and edits arrive in bursts.

        Measured on the previous implementation at four-way parallelism: 12 of 60
        counted. The 12-edit checkpoint then fired about five times too rarely while
        still appearing to work, which is the failure mode this whole package is about.
        """
        import concurrent.futures
        n = 60
        def one(i):
            return self.run_hook("edit", {"session_id": "burst",
                                          "tool_use_id": "toolu_burst_%d" % i},
                                 CI_EDIT_EVERY="10000")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(one, range(n)))
        counted = (self.state / "reminders" / "burst.edits").stat().st_size
        self.assertEqual(counted, n,
                         "%d concurrent edits counted as %d" % (n, counted))

    def test_distinct_sessions_do_not_share_claims(self):
        payload = {"prompt_id": "p-same", "prompt": "y" * 120}
        a = self.run_hook("prompt", dict(payload, session_id="alpha"))
        b = self.run_hook("prompt", dict(payload, session_id="beta"))
        self.assertIn("skill-compounder", a)
        self.assertIn("skill-compounder", b, "a claim must not leak across sessions")

    def test_a_broken_state_directory_fails_open(self):
        """A claim that cannot be written must not silence every later reminder.

        mkdir failing because the marker exists is a duplicate. mkdir failing because the
        state directory is read-only or the disk is full is not, and treating the two the
        same would disable the reminders for the rest of the session with no error
        anywhere. Losing reminders is the worse failure, so this fails open.
        """
        reminders = self.state / "reminders"
        reminders.mkdir(parents=True)
        seen = reminders / "s9.seen"
        seen.mkdir()
        os.chmod(str(seen), 0o500)                           # no write permission
        try:
            # Pin the prune off. It samples roughly one event in CI_PRUNE_EVERY, and when
            # it does fire it correctly removes this directory (rmdir needs write on the
            # PARENT, not on the directory itself), which made the cleanup below fail on
            # whichever platform happened to roll the sample.
            out = self.run_hook("prompt", {"session_id": "s9", "prompt_id": "p-x",
                                           "prompt": "q" * 120},
                                CI_PRUNE_EVERY="1000000")
            self.assertIn("skill-compounder", out,
                          "an unwritable claim directory must not suppress the reminder")
        finally:
            if seen.is_dir():
                os.chmod(str(seen), 0o700)

    def test_claim_markers_do_not_leak(self):
        """The prune must actually empty the nested markers.

        Matching only '*.seen*' left the children behind, so the parent was never empty,
        rmdir always failed, and one directory leaked per file edit for the life of the
        machine. At 10,000 markers the prune itself cost 1.25 seconds on every event.
        """
        reminders = self.state / "reminders"
        seen = reminders / "old.seen"
        seen.mkdir(parents=True)
        for i in range(5):
            (seen / ("edit-t%d" % i)).mkdir()
        old = time.time() - 60 * 60 * 24 * 3
        for p in list(seen.iterdir()) + [seen]:
            os.utime(str(p), (old, old))
        # CI_PRUNE_EVERY=1 makes the sweep deterministic instead of sampled.
        self.run_hook("prompt", {"session_id": "fresh", "prompt_id": "p-z",
                                 "prompt": "r" * 120},
                      CI_PRUNE_EVERY="1", CI_CLAIM_TTL_MIN="60")
        left = [p for p in reminders.rglob("*") if p.is_dir() and p.name.startswith("edit-")]
        self.assertEqual(left, [], "stale claim markers were not pruned: %s" % left)
        self.assertFalse(seen.exists(), "the emptied .seen directory should go too")

    def test_an_event_with_no_id_still_fires(self):
        """Losing reminders is worse than a rare duplicate, so an unidentifiable
        event is always claimed rather than suppressed."""
        out = self.run_hook("prompt", {"session_id": "s3", "prompt": "z" * 120})
        self.assertIn("skill-compounder", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
