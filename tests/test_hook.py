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




class ReminderStoreIsNotSweptTest(unittest.TestCase):
    """<state>/reminders.jsonl is a SIBLING of <state>/reminders/, and that is the whole
    reason the reminder store can keep that name.

    `prune_stale_state()` deletes files under its STATE_DIR older than seven days, and
    STATE_DIR is `<state>/reminders`. A store one directory level up is out of reach; a
    store INSIDE it would silently empty itself after a week, which is a data-loss bug
    that nothing would report. This pins the relationship rather than the sweep's glob,
    because the glob is what would change.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        (self.state / "reminders").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_old_reminder_store_survives_a_sweep_that_really_fired(self):
        import os
        import time as _time
        store = self.state / "reminders.jsonl"
        store.write_text('{"id":"n1x1","text":"keep me","scope":"global"}\n',
                         encoding="utf-8")
        # The CANARY: a file of the same age INSIDE the swept directory. Without it,
        # "the store survived" would also pass if the sweep never ran at all.
        canary = self.state / "reminders" / "old.edits"
        canary.write_text("x", encoding="utf-8")
        old = _time.time() - 60 * 60 * 24 * 9
        for p in (store, canary):
            os.utime(str(p), (old, old))
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state),
               "CI_PRUNE_EVERY": "1"}
        r = subprocess.run([str(HOOK), "prompt"],
                           input=json.dumps({"session_id": "sweep", "prompt_id": "p1",
                                             "prompt": "z" * 120}),
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(canary.exists(),
                         "the sweep did not run, so this test proves nothing")
        self.assertTrue(store.exists(),
                        "the reminder store was deleted by the counter sweep")
        self.assertIn("keep me", store.read_text(encoding="utf-8"))


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


class NudgeLogSurvivesTheSweepTest(unittest.TestCase):
    """THE FUNNEL DIED OF THE HOUSEKEEPING THAT PREDATED IT.

    `<state>/reminders/nudges.jsonl` is the delivery log issue #37 added, and it lives in
    the same directory as the per-session counters because that is where this hook's state
    goes. The sweep there was `find "$STATE_DIR" -type f -mtime +7 -delete`, written when
    the only files under it were counters that a session finishing makes dead. A log that
    is appended to once per nudge and then left alone is exactly seven days from deletion
    on any quiet install, so bin/skillreport's FUNNEL reported "no deliveries logged yet"
    against an install that had been delivering all along -- and nothing said why.

    The sweep is by NAME now. This drives the real hook with the real sampler forced on,
    against a real week-old log written the way the hook writes it.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        (self.state / "reminders").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def sweep(self, sid="sweep"):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state),
               "CI_PRUNE_EVERY": "1"}
        r = subprocess.run([str(HOOK), "prompt"],
                           input=json.dumps({"session_id": sid, "prompt_id": "p1",
                                             "prompt": "z" * 120}),
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def age(self, *paths, days=9):
        import os
        import time as _time
        old = _time.time() - 60 * 60 * 24 * days
        for p in paths:
            os.utime(str(p), (old, old))

    def test_a_week_old_delivery_log_survives_and_a_week_old_counter_does_not(self):
        log = self.state / "reminders" / "nudges.jsonl"
        log.write_text('{"id":"ci-checkpoint","ts":1,"session":"s1",'
                       '"kind":"checkpoint","event":"PostToolUse"}\n', encoding="utf-8")
        # THE CANARY, and it is the file the sweep was actually written for. Without it
        # "the log survived" would also pass on a sweep that never ran.
        canary = self.state / "reminders" / "s9.edits"
        canary.write_text("xxxx", encoding="utf-8")
        self.age(log, canary)

        self.sweep()

        self.assertFalse(canary.exists(),
                         "the sweep did not fire, so this test proves nothing")
        self.assertTrue(log.exists(), "the sweep deleted the delivery log")
        self.assertIn("ci-checkpoint", log.read_text(encoding="utf-8"))

    def test_every_counter_suffix_the_hook_writes_is_still_swept(self):
        """The allowlist is only right if it names all eight. Each of these is written by
        this hook under `<sid>.<suffix>`; a suffix left out of the list leaks forever."""
        made = []
        for suffix in ("edits", "first", "paths", "opaque", "checkpoints", "prose",
                       "nudge", "prompt"):
            p = self.state / "reminders" / ("s9.%s" % suffix)
            p.write_text("x", encoding="utf-8")
            made.append(p)
        self.age(*made)
        self.sweep()
        left = [p.name for p in made if p.exists()]
        self.assertEqual(left, [], "these counters were never swept: %r" % left)

    def test_the_sweep_does_not_reach_outside_its_own_directory(self):
        """It walks one level. A stale file in a SIBLING tree of the state root is not
        this hook's to delete, and nor is one nested inside a claim directory."""
        import os
        other = self.state / "remind"
        other.mkdir()
        sibling = other / "hits.jsonl"
        sibling.write_text("x", encoding="utf-8")
        nested = self.state / "reminders" / "s9.seen"
        nested.mkdir()
        deep = nested / "edit-u1.edits"
        deep.write_text("x", encoding="utf-8")
        self.age(sibling, deep, nested)
        canary = self.state / "reminders" / "s9.edits"
        canary.write_text("x", encoding="utf-8")
        self.age(canary)

        self.sweep()

        self.assertFalse(canary.exists(), "the sweep did not fire")
        self.assertTrue(sibling.exists(), "it deleted a file in a sibling tree")
        self.assertTrue(deep.exists() or not nested.exists(),
                        "it reached inside a claim directory to delete a file")


class SweepKnobTest(unittest.TestCase):
    """A knob from the tuning table must never be able to break a turn.

    `CI_PRUNE_EVERY=0` reached `$(( ${RANDOM:-0} % PRUNE_EVERY ))` unguarded, and bash
    reports `division by 0` on stderr and leaves the arithmetic command failing -- so the
    hook printed a shell error into the user's terminal and exited 1. It is the last
    statement in the script, so every event that ran to completion took it. Found while
    testing something else, with `CI_PRUNE_EVERY=0` set for no reason but tidiness.

    0 means OFF now, which is what it already meant in hooks/mission.sh and
    hooks/remind.sh; nonsense and out-of-range values take the default.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        (self.state / "reminders").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_to_the_end(self, **extra):
        """A prose edit with the checkpoint far away: it emits nothing and falls through
        to `prune_stale_state` at the foot of the script."""
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state),
               "CI_EDIT_EVERY": "99"}
        env.update({k: str(v) for k, v in extra.items()})
        return subprocess.run(
            [str(HOOK), "edit"],
            input=json.dumps({"session_id": "s1", "tool_use_id": "u1", "tool_name": "Edit",
                              "tool_input": {"file_path": "/repo/src/a.py"}}),
            capture_output=True, text=True, env=env)

    def stale(self, name="s9.edits"):
        import os
        import time as _time
        p = self.state / "reminders" / name
        p.write_text("x", encoding="utf-8")
        old = _time.time() - 60 * 60 * 24 * 9
        os.utime(str(p), (old, old))
        return p

    def test_zero_switches_the_sweep_off_instead_of_breaking_the_turn(self):
        canary = self.stale()
        r = self.run_to_the_end(CI_PRUNE_EVERY=0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "", "a hook printed a shell error: %r" % r.stderr)
        self.assertTrue(canary.exists(), "CI_PRUNE_EVERY=0 swept anyway")

    def test_nonsense_and_out_of_range_take_the_default_and_still_sweep(self):
        for bad in ("banana", "-1", "1.5", "", "99999999999999999999999"):
            self.tearDown(); self.setUp()
            canary = self.stale()
            r = self.run_to_the_end(CI_PRUNE_EVERY=bad, CI_CLAIM_TTL_MIN=bad)
            self.assertEqual(r.returncode, 0, "%r: %s" % (bad, r.stderr))
            self.assertEqual(r.stderr, "", "%r printed: %r" % (bad, r.stderr))
            # The default is 25, so one run sweeps with probability 1/25 -- assert only
            # that nothing broke, and pin the sweeping separately below.
            del canary

    def test_the_default_really_does_sweep_when_it_draws(self):
        """Non-vacuity for the two above: with the sampler forced on, the same event
        removes the same canary."""
        canary = self.stale()
        r = self.run_to_the_end(CI_PRUNE_EVERY=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(canary.exists(), "the sweep never fired at all")


class AppendFailureTest(unittest.TestCase):
    """`2>/dev/null` AFTER a `>>` silences the COMMAND, not the redirection.

    The shell opens the append first, and when the open fails it says so itself -- on a
    stderr the later `2>/dev/null` has not applied to yet. Measured directly: with a
    directory in place of the target, `printf x >> f 2>/dev/null` prints "bash: f: Is a
    directory" and `printf x 2>/dev/null >> f` prints nothing. A hook must never break a
    turn, and printing a shell error into the user's terminal is the visible half of that.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        (self.state / "reminders").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, sid="s1", uid="u1", **extra):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state),
               "CI_PRUNE_EVERY": "0"}
        env.update({k: str(v) for k, v in extra.items()})
        return subprocess.run(
            [str(HOOK), "edit"],
            input=json.dumps({"session_id": sid, "tool_use_id": uid, "tool_name": "Edit",
                              "tool_input": {"file_path": "/repo/src/a.py"}}),
            capture_output=True, text=True, env=env)

    def test_the_shell_never_reports_a_blocked_append_to_the_user(self):
        """Every per-session append on the PostToolUse path, one at a time: the edit
        counter, the first-seen stamp, the visible-path list and the opaque-edit tally."""
        for name in ("s1.edits", "s1.first", "s1.paths", "s1.opaque"):
            (self.state / "reminders" / name).mkdir()
        r = self.edit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "",
                         "the shell's redirection failure reached the user: %r" % r.stderr)

    def test_a_blocked_checkpoint_tally_and_delivery_log_are_silent_too(self):
        """The checkpoint turn writes two more: `<sid>.checkpoints` and nudges.jsonl."""
        for name in ("s1.checkpoints", "nudges.jsonl"):
            (self.state / "reminders" / name).mkdir()
        r = self.edit(CI_EDIT_EVERY=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "", "stderr from a hook: %r" % r.stderr)
        self.assertIn("Checkpoint after 1 file edits", r.stdout,
                      "the nudge itself must still be delivered; the logs are best-effort")

    def test_a_blocked_prose_marker_is_silent_too(self):
        (self.state / "reminders" / "s1.prose").mkdir()
        r = subprocess.run(
            [str(HOOK), "edit"],
            input=json.dumps({"session_id": "s1", "tool_use_id": "u2", "tool_name": "Edit",
                              "tool_input": {"file_path": "/repo/README.md"}}),
            capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                 "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state),
                 "CI_PRUNE_EVERY": "0", "CI_EDIT_EVERY": "99"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "", "stderr from a hook: %r" % r.stderr)

    def test_the_wrong_order_really_does_leak(self):
        """Non-vacuity for the whole class: the two orderings, driven against a real
        directory-as-target, must actually differ. If they did not, every assertion above
        would be pinning nothing."""
        d = self.state / "target"
        d.mkdir()
        wrong = subprocess.run(
            ["bash", "-c", 'printf x >> "$1" 2>/dev/null || true', "_", str(d)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL)
        right = subprocess.run(
            ["bash", "-c", 'printf x 2>/dev/null >> "$1" || true', "_", str(d)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertIn("Is a directory", wrong.stderr)
        self.assertEqual(right.stderr, "")


class KnobGuardTest(unittest.TestCase):
    """Every numeric knob this hook reads, driven with the four values a knob gets typed
    wrong as, plus the value 0 that means something different for each of them.

    SweepKnobTest above is this argument for the two knobs prune_stale_state reads.
    The rest were left unguarded, and the same two failures were still reachable --
    driven against this same script with the guards removed, on /bin/bash 3.2.57:
    `CI_EDIT_EVERY=0` reached `$(( n % EDIT_EVERY ))`, and bash printed `division by 0`
    and left the hook exiting 1 on EVERY counted edit; `CI_PROMPT_MIN_CHARS=abc` reached
    `[` and printed `abc: integer expression expected`; `CI_PROMPT_COOLDOWN=` twenty-three
    digits printed the same thing, because that overflows the strtoimax behind `[` as
    surely as `abc` does; and `CI_NOW=abc` reached `$(( now - last ))` on the second
    prompt of a session, where `set -u` turned it into `abc: unbound variable` and exit 1.
    A knob the tuning table invites people to set must never put a shell error on the
    user's stderr.

    What each 0 means is the part worth reading. `CI_EDIT_EVERY=0` takes the DEFAULT --
    there is no off switch for the checkpoint, and inventing one silently would turn a
    typo into a session with no checkpoints and nothing to say why. `CI_PROMPT_COOLDOWN=0`
    and `CI_PROMPT_MIN_CHARS=0` are real settings and pass through. `CI_NOW=0` is epoch 0.
    Out of range takes the default everywhere.
    """

    BAD = ("abc", "-1", "1.5", "", "9" * 23)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir(parents=True)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra):
        e = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
             "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def edit(self, sid, n, **extra):
        """One counted edit against a source path, so neither prose arm can answer for
        the checkpoint."""
        payload = {"session_id": sid, "tool_name": "Edit", "tool_use_id": "%s-%03d" % (sid, n),
                   "tool_input": {"file_path": "%s/src/a%03d.py" % (self.repo, n)}}
        return subprocess.run([str(HOOK), "edit"], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env(**extra))

    def prompt(self, sid, pid, text=LONG_PROMPT, **extra):
        payload = {"session_id": sid, "prompt_id": pid, "prompt": text,
                   "cwd": str(self.repo)}
        return subprocess.run([str(HOOK), "prompt"], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env(**extra))

    def checkpoints_over_12_edits(self, sid, **extra):
        """Returns the 1-based edit numbers that produced a checkpoint, asserting a
        clean exit and a silent stderr on every single one."""
        fired = []
        for n in range(1, 13):
            r = self.edit(sid, n, **extra)
            self.assertEqual(r.returncode, 0, "edit %d: %s" % (n, r.stderr))
            self.assertEqual(r.stderr, "", "edit %d printed: %r" % (n, r.stderr))
            if "Checkpoint after" in r.stdout:
                fired.append(n)
        return fired

    # ------------------------------------------------------------- CI_EDIT_EVERY

    def test_edit_every_zero_takes_the_default_instead_of_dividing_by_it(self):
        self.assertEqual(self.checkpoints_over_12_edits("z", CI_EDIT_EVERY=0), [12],
                         "0 did not fall back to the documented default of 12")

    def test_edit_every_nonsense_and_out_of_range_take_the_default(self):
        for i, bad in enumerate(self.BAD):
            self.assertEqual(self.checkpoints_over_12_edits("b%d" % i, CI_EDIT_EVERY=bad),
                             [12], "%r did not take the default" % bad)

    def test_a_usable_edit_every_is_still_honoured(self):
        """Non-vacuity: the guard must normalise the four bad values WITHOUT flattening
        a good one onto the default."""
        self.assertEqual(self.checkpoints_over_12_edits("g", CI_EDIT_EVERY=4), [4, 8, 12])

    # --------------------------------------------------------- CI_PROMPT_MIN_CHARS

    def test_prompt_min_chars_zero_is_a_real_setting_not_the_default(self):
        r = self.prompt("m0", "p1", text="ok", CI_PROMPT_MIN_CHARS=0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        self.assertIn("Before starting implementation", r.stdout,
                      "0 was read as the default 60 and swallowed a two-character prompt")

    def test_prompt_min_chars_nonsense_and_out_of_range_take_the_default(self):
        for i, bad in enumerate(self.BAD):
            short = self.prompt("mn%d" % i, "s", text="ok", CI_PROMPT_MIN_CHARS=bad)
            self.assertEqual(short.returncode, 0, "%r: %s" % (bad, short.stderr))
            self.assertEqual(short.stderr, "", "%r printed: %r" % (bad, short.stderr))
            self.assertEqual(short.stdout, "", "%r let a two-character prompt through" % bad)
            long = self.prompt("ml%d" % i, "l", CI_PROMPT_MIN_CHARS=bad)
            self.assertEqual(long.returncode, 0, "%r: %s" % (bad, long.stderr))
            self.assertEqual(long.stderr, "", "%r printed: %r" % (bad, long.stderr))
            self.assertIn("Before starting implementation", long.stdout,
                          "%r blocked a %d-character prompt" % (bad, len(LONG_PROMPT)))

    # ---------------------------------------------------------- CI_PROMPT_COOLDOWN

    def test_prompt_cooldown_zero_is_a_real_setting_not_the_default(self):
        first = self.prompt("c0", "p1", CI_NOW=1000, CI_PROMPT_COOLDOWN=0)
        second = self.prompt("c0", "p2", CI_NOW=1000, CI_PROMPT_COOLDOWN=0)
        for r in (first, second):
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stderr, "")
        self.assertIn("Before starting implementation", second.stdout,
                      "0 was read as the default 1200 and throttled the next prompt")

    def test_prompt_cooldown_nonsense_and_out_of_range_take_the_default(self):
        for i, bad in enumerate(self.BAD):
            sid = "cn%d" % i
            for pid, clock, want in (("p1", 1000, True), ("p2", 1300, False),
                                     ("p3", 1000 + 1201, True)):
                r = self.prompt(sid, pid, CI_NOW=clock, CI_PROMPT_COOLDOWN=bad)
                self.assertEqual(r.returncode, 0, "%r/%s: %s" % (bad, pid, r.stderr))
                self.assertEqual(r.stderr, "", "%r printed: %r" % (bad, r.stderr))
                fired = "Before starting implementation" in r.stdout
                self.assertEqual(fired, want,
                                 "%r at t=%d: fired=%s, the default 1200 wants %s"
                                 % (bad, clock, fired, want))

    # ------------------------------------------------------------------- CI_NOW

    def test_the_clock_pin_falls_back_to_the_real_clock(self):
        """CI_NOW is read straight into `$(( now - last ))`, where bash resolves a
        non-numeric string as a variable name and `set -u` turned that into
        `abc: unbound variable` and exit 1.

        TWO prompts per value, because the first one never reaches that arithmetic: an
        absent stamp short-circuits the cooldown test, so a one-prompt version of this
        would have missed the failure it exists for: measured with `CI_NOW=abc`, the
        one-prompt form left stderr empty and the two-prompt form exited 1.
        """
        import time as _time
        for i, bad in enumerate(self.BAD):
            first = self.prompt("n%d" % i, "p0", CI_NOW=1000)
            self.assertEqual(first.stderr, "", "%r: setup printed %r" % (bad, first.stderr))
            r = self.prompt("n%d" % i, "p1", CI_NOW=bad)
            self.assertEqual(r.returncode, 0, "%r: %s" % (bad, r.stderr))
            self.assertEqual(r.stderr, "", "%r printed: %r" % (bad, r.stderr))
            stamp = (self.state / "reminders" / ("n%d.prompt" % i)).read_text()
            self.assertRegex(stamp, r"^[0-9]+$", "%r reached the stamp" % bad)
            self.assertLess(abs(int(stamp) - int(_time.time())), 120,
                            "%r did not fall back to the real clock: %s" % (bad, stamp))

    def test_clock_zero_is_epoch_zero_and_not_the_fallback(self):
        """Non-vacuity for the test above: 0 is a legal reading and must survive."""
        r = self.prompt("n0", "p1", CI_NOW=0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        self.assertEqual((self.state / "reminders" / "n0.prompt").read_text(), "0")

    # ------------------------------------------- CI_QUEUE_NUDGE_MIN / _NUDGE_MAX

    T0 = 1756000000

    def a_real_queued_candidate(self):
        """One genuine queue record, written by the real Stop hook out of a real marker.

        The nudge bounds are only reached once `skillinsight pending` reports a
        candidate, so a hand-made queue file would leave the two comparisons below
        untested -- which is the whole of what these bounds guard.
        """
        stop = {"session_id": "queued", "cwd": str(self.repo),
                "last_assistant_message":
                    "SKILL-CANDIDATE: the retry-with-backoff wrapper is worth "
                    "crystallizing.\n\nDone."}
        r = subprocess.run([str(REPO / "hooks" / "insight-capture.sh")],
                           input=json.dumps(stop), capture_output=True, text=True,
                           env=self.env(INSIGHT_NOW=self.T0))
        self.assertEqual(r.returncode, 0, r.stderr)
        queue = list((self.state / "insights").glob("*.jsonl"))
        self.assertTrue(queue, "fixture wrote no queue record")

    def stamp_the_nudge(self, age, seen=0):
        (self.state / "insights" / ".nudge").write_text(
            "%d %d\n" % (self.T0 - age, seen), encoding="utf-8")

    def nudged(self, sid, **extra):
        r = self.prompt(sid, "p1", CI_NOW=self.T0, **extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "", "a hook printed: %r" % r.stderr)
        return "skill-candidate queue has" in r.stdout

    def test_queue_nudge_min_out_of_range_takes_the_default(self):
        """A 23-digit floor passed the old shape-only guard, which checked the two
        bounds CONCATENATED, and reached `[ "$qn_age" -lt "$NUDGE_MIN" ]`."""
        self.a_real_queued_candidate()
        for bad in self.BAD:
            self.stamp_the_nudge(age=1)
            self.assertFalse(self.nudged("qa-%s" % bad, CI_QUEUE_NUDGE_MIN=bad),
                             "%r announced one second after the last announcement" % bad)
            self.stamp_the_nudge(age=300000)
            self.assertTrue(self.nudged("qb-%s" % bad, CI_QUEUE_NUDGE_MIN=bad),
                            "%r stayed silent past the default floor of 259200" % bad)

    def test_queue_nudge_max_out_of_range_takes_the_default(self):
        """The ceiling, judged with the growth watermark already caught up, so only
        NUDGE_MAX can let the announcement through."""
        self.a_real_queued_candidate()
        for bad in self.BAD:
            self.stamp_the_nudge(age=300000, seen=self.T0)
            self.assertFalse(self.nudged("qc-%s" % bad, CI_QUEUE_NUDGE_MAX=bad),
                             "%r announced an unchanged queue inside the ceiling" % bad)
            self.stamp_the_nudge(age=2000000, seen=self.T0)
            self.assertTrue(self.nudged("qd-%s" % bad, CI_QUEUE_NUDGE_MAX=bad),
                            "%r stayed silent past the default ceiling of 1209600" % bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
