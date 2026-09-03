#!/usr/bin/env python3
"""Tests for hooks/remind.sh -- the reminder store's delivery hook.

NO MOCKS, per this repo's standing rule. Every test writes a real `reminders.jsonl`, runs
the real shell script through subprocess with a minimal PATH, a HOME inside a temp
directory and SKILL_COMPOUNDER_STATE pinned there, feeds it a real payload on stdin, and
reads the emit and the state directory back off disk.

THE ROWS ARE HAND-WRITTEN HERE, DELIBERATELY. `bin/skillnote add --remind` is what writes
them in production and it is developed in parallel with this hook; a test that called it
would be testing two things at once and would go red for reasons that are not this
script's. The row shape below is the one notes/2026-09-02-tiers-design.md fixes, and it is
the contract between the two.

THE ONE EXCEPTION IS THE COMMAND ARM, and it is the point of that arm's tests. A command
rule is matched by BYTE EQUALITY against a normalised signature, and the normaliser is
hooks/repeat-gate.sh. So those fixtures are built by running `repeat-gate.sh --norm-of
Bash` for real: if the two ever stopped sharing one implementation, a hand-written
signature would keep passing while production stopped matching.

EVERY subprocess call against the hook passes `input=`. The script reads its payload with
`payload="$(cat)"`; without stdin it hangs forever.

The clock is pinned with REMIND_NOW -- the hook's own. Pinning another script's clock does
nothing to this one.
"""

import json
import os
import shutil
import subprocess
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "remind.sh")
NORMALISER = os.path.join(REPO, "hooks", "repeat-gate.sh")

# Minimal, explicit environment: the scripts must not depend on the ambient one.
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"

PROJECT = "/repo"


def norm_of(command):
    """The signature the repeat gate would compute for `command`.

    Called for real, so a fixture cannot drift away from the production normaliser.
    """
    p = subprocess.run(["bash", NORMALISER, "--norm-of", "Bash"], input=command,
                       capture_output=True, text=True,
                       env={"PATH": BASE_PATH, "HOME": "/tmp"}, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


class RemindCase(unittest.TestCase):
    """Shared harness: one temp state root per test, the real script, real payloads."""

    def setUp(self):
        self.tmp = os.path.join(
            os.environ.get("TMPDIR", "/tmp"),
            "remind-%d-%d" % (os.getpid(), int(time.time() * 1e6) % 10 ** 9))
        os.makedirs(self.tmp)
        self.home = os.path.join(self.tmp, "home")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.home)
        os.makedirs(self.state)
        self.clock = 1_756_900_000          # 2025-09-03T11:46:40Z

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------- plumbing
    @property
    def store(self):
        return os.path.join(self.state, "reminders.jsonl")

    @property
    def hits(self):
        return os.path.join(self.state, "remind", "hits.jsonl")

    def env(self, **extra):
        e = {"PATH": BASE_PATH, "HOME": self.home,
             "SKILL_COMPOUNDER_STATE": self.state,
             "REMIND_NOW": str(self.clock)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def run_hook(self, payload, hook=None, **env_extra):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(["bash", hook or HOOK], input=body, capture_output=True,
                              text=True, env=self.env(**env_extra), timeout=180)

    def write_rows(self, *rows):
        with open(self.store, "a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def row(self, rid, text, keywords=(), paths=(), commands=(), scope=PROJECT,
            created=None, source="session"):
        """A row in exactly the shape the design fixes for <state>/reminders.jsonl."""
        return {"id": rid, "text": text,
                "match": {"keywords": list(keywords), "paths": list(paths),
                          "commands": list(commands)},
                "scope": scope, "created": created if created is not None else 1_756_838_400,
                "source": source, "hits": 0}

    def tombstone(self, rid, ts=None):
        return {"id": rid, "t": "remove", "ts": ts if ts is not None else self.clock}

    # ------------------------------------------------------------------- payloads
    def prompt(self, text, session="s1", pid=None, cwd=PROJECT, **over):
        p = {"hook_event_name": "UserPromptSubmit", "session_id": session,
             "prompt_id": pid or ("p_%s" % session), "cwd": cwd,
             "transcript_path": os.path.join(self.tmp, "t.jsonl"), "prompt": text}
        p.update(over)
        return p

    def bash(self, command, session="s1", tuid=None, cwd=PROJECT, **over):
        p = {"hook_event_name": "PreToolUse", "session_id": session,
             "tool_use_id": tuid or ("toolu_%s" % session), "cwd": cwd,
             "transcript_path": os.path.join(self.tmp, "t.jsonl"),
             "permission_mode": "acceptEdits", "tool_name": "Bash",
             "tool_input": {"command": command, "description": "d"}}
        p.update(over)
        return p

    def write(self, file_path, session="s1", tuid=None, cwd=PROJECT, tool="Write", **over):
        p = {"hook_event_name": "PreToolUse", "session_id": session,
             "tool_use_id": tuid or ("toolu_%s" % session), "cwd": cwd,
             "transcript_path": os.path.join(self.tmp, "t.jsonl"),
             "permission_mode": "acceptEdits", "tool_name": tool,
             "tool_input": {"file_path": file_path, "content": "x"}}
        p.update(over)
        return p

    # ------------------------------------------------------------------- assertions
    def assert_silent(self, r):
        self.assertEqual(r.returncode, 0, "a hook must never exit non-zero: " + r.stderr)
        self.assertEqual(r.stdout.strip(), "",
                         "the hook spoke when it should have been silent: %r" % r.stdout)
        return r

    def context_of(self, r, event="UserPromptSubmit"):
        """The emitted additionalContext, with the shape checked on the way through."""
        self.assertEqual(r.returncode, 0, "a hook must never exit non-zero: " + r.stderr)
        self.assertTrue(r.stdout.strip(), "expected a reminder, got silence")
        d = json.loads(r.stdout)
        self.assertIs(d["suppressOutput"], True)
        hso = d["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], event)
        # The MEASURED field. `permissionDecision:"allow"` with a reason reaches nothing
        # (0 of 6 runs, docs/CLAUDE-CODE-BEHAVIOR.md), so its presence here would mean the
        # hook had silently stopped saying anything to anyone.
        self.assertNotIn("permissionDecision", hso)
        return hso["additionalContext"]

    def hit_rows(self):
        if not os.path.exists(self.hits):
            return []
        return [json.loads(l) for l in open(self.hits, encoding="utf-8") if l.strip()]


# ==================================================================== the keyword arm
class KeywordTest(RemindCase):
    """AND, not OR. A rule with two keywords fires only when the prompt carries both.

    OR would make a two-word rule fire on either word, which is how a reminder becomes
    noise: one that arrives when it does not apply teaches the reader to skip the next one.
    """

    def setUp(self):
        super().setUp()
        self.write_rows(self.row("n1x1", "Kill the runner and re-run the full suite.",
                                 keywords=["test", "fail"]))

    def test_both_keywords_present_fires(self):
        ctx = self.context_of(self.run_hook(self.prompt("the test keeps failing here")))
        self.assertIn("Kill the runner", ctx)

    def test_one_keyword_is_not_enough(self):
        self.assert_silent(self.run_hook(self.prompt("the test passed cleanly")))

    def test_neither_keyword_is_silent(self):
        self.assert_silent(self.run_hook(self.prompt("please rename this function")))

    def test_matching_is_case_insensitive_on_the_prompt(self):
        ctx = self.context_of(self.run_hook(self.prompt("The TEST keeps FAILING")))
        self.assertIn("Kill the runner", ctx)

    def test_a_keyword_matches_inside_a_longer_word(self):
        """Substring containment, stated so it is a decision rather than an accident:
        `fail` matches `failing`. Word-boundary matching would miss every inflection."""
        ctx = self.context_of(self.run_hook(self.prompt("tests are failing")))
        self.assertIn("Kill the runner", ctx)

    def test_a_row_with_no_keywords_never_matches_a_prompt(self):
        self.write_rows(self.row("n2x2", "A path-only rule.", paths=["*.py"]))
        ctx = self.context_of(self.run_hook(self.prompt("the test keeps failing")))
        self.assertNotIn("path-only", ctx)

    def test_the_frame_is_a_statement_of_fact_not_an_instruction(self):
        """Measured: the same field with imperative wording was refused as prompt
        injection in 2 of 4 runs, and accepted 3 of 3 when it read as a report
        (docs/CLAUDE-CODE-BEHAVIOR.md, CLI 2.1.258). The frame is what makes the text a
        report even when the reminder itself is written as an order."""
        ctx = self.context_of(self.run_hook(self.prompt("the test keeps failing")))
        self.assertTrue(ctx.startswith("Reminder recorded on 2025-09-02 for this project: "),
                        "unexpected frame: %r" % ctx)


# ==================================================================== the command arm
class CommandTest(RemindCase):
    """Byte equality against a NORMALISED signature, and the normaliser is shared.

    The whole value of this arm is that `gh issue comment 19 --body "x"` and
    `gh issue comment 4271 --body "quite another message"` are ONE call. Nothing here
    reimplements that judgement: the fixture is built by running the repeat gate's own
    `--norm-of`, so a second implementation appearing in remind.sh would fail these.
    """

    def setUp(self):
        super().setUp()
        self.sig = norm_of('gh issue comment 19 --body "first draft"')
        self.write_rows(self.row("n3x3", "gh issue comment needs the body in a file.",
                                 commands=[self.sig], scope="global"))

    def test_the_signature_really_is_normalised(self):
        """Guards the two tests below: if --norm-of started echoing its input, they would
        both still pass while proving nothing."""
        self.assertNotIn("first draft", self.sig)
        self.assertNotIn("19", self.sig)
        self.assertIn("gh issue comment", self.sig)

    def test_a_different_literal_of_the_same_call_fires(self):
        ctx = self.context_of(
            self.run_hook(self.bash('gh issue comment 4271 --body "quite another message"')),
            event="PreToolUse")
        self.assertIn("body in a file", ctx)

    def test_a_genuinely_different_command_does_not(self):
        self.assert_silent(self.run_hook(self.bash("gh pr list")))

    def test_the_stored_signature_is_not_matched_as_a_literal(self):
        """The rule holds a signature, not a command. A payload whose command IS the
        signature text must not be what makes the arm look like it works."""
        r = self.run_hook(self.bash("true # unrelated"))
        self.assert_silent(r)

    def test_without_the_normaliser_command_matching_is_skipped_not_guessed(self):
        """`remind.sh` calls repeat-gate.sh beside it. In a checkout without that script
        an approximate signature would match the WRONG reminders, so the arm goes quiet
        instead -- and the other arms keep working, which is what this checks."""
        lone = os.path.join(self.tmp, "hooks")
        os.makedirs(lone)
        copy = os.path.join(lone, "remind.sh")
        shutil.copy(HOOK, copy)
        self.write_rows(self.row("n4x4", "A keyword rule.", keywords=["hello"]))
        self.assert_silent(
            self.run_hook(self.bash('gh issue comment 7 --body "x"'), hook=copy))
        ctx = self.context_of(self.run_hook(self.prompt("hello there"), hook=copy))
        self.assertIn("A keyword rule", ctx)

    def test_the_repeat_gates_off_switch_does_not_disable_command_matching(self):
        """Two scripts, two switches. Turning the repeat gate off must not silently stop a
        reminder firing, which is what happened while `--norm-of` sat behind that gate's
        own off switch and returned nothing."""
        ctx = self.context_of(
            self.run_hook(self.bash('gh issue comment 8 --body "y"'),
                          SKILL_COMPOUNDER_REPEAT_GATE="0"),
            event="PreToolUse")
        self.assertIn("body in a file", ctx)

    def test_a_command_rule_does_not_fire_on_a_prompt(self):
        self.assert_silent(self.run_hook(self.prompt("gh issue comment 19 --body x")))


# ==================================================================== the path arm
class WriterReaderTest(RemindCase):
    """The row is written by the REAL `skillnote add --remind --command`, through a
    symlink the way the installer links it, and read by the real hook.

    Every other command test here hand-writes its row, which is how two shipped bugs got
    past the suite on 2026-09-02: the installed symlink could not find repeat-gate.sh, and
    skillnote stored `Bash\\n<sig>` while remind.sh compared the bare signature, so every
    command-keyed reminder was silent in a real session. This test drives both halves.
    """

    def test_a_command_reminder_written_by_skillnote_fires_in_the_hook(self):
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        link = os.path.join(bindir, "skillnote")
        os.symlink(os.path.join(REPO, "bin", "skillnote"), link)
        w = subprocess.run([link, "add", "--remind", "--scope", "global",
                            "--command", "make deploy",
                            "Deploys go through make deploy, which runs the preflight."],
                           capture_output=True, text=True, timeout=120,
                           env=dict(self.env(), SKILLNOTE_NOW="1756838400"))
        self.assertEqual(w.returncode, 0, w.stdout + w.stderr)
        with open(self.store, encoding="utf-8") as fh:
            row = json.loads(fh.readline())
        self.assertEqual(row["match"]["commands"], [norm_of("make deploy")],
                         "the writer must store exactly what --norm-of prints")
        ctx = self.context_of(self.run_hook(self.bash("make deploy")), event="PreToolUse")
        self.assertIn("runs the preflight", ctx)


class PathTest(RemindCase):

    def setUp(self):
        super().setUp()
        self.write_rows(self.row("n5x5", "Check which tests pin a skill's prose.",
                                 paths=["tests/*.py"]))

    def test_a_relative_glob_matches_a_path_under_the_scope(self):
        ctx = self.context_of(self.run_hook(self.write("/repo/tests/test_x.py")),
                              event="PreToolUse")
        self.assertIn("pin a skill's prose", ctx)

    def test_edit_fires_it_as_well_as_write(self):
        ctx = self.context_of(self.run_hook(self.write("/repo/tests/test_x.py", tool="Edit")),
                              event="PreToolUse")
        self.assertIn("pin a skill's prose", ctx)

    def test_a_path_outside_the_glob_is_silent(self):
        self.assert_silent(self.run_hook(self.write("/repo/hooks/remind.sh")))

    def test_an_absolute_glob_matches_the_absolute_path(self):
        self.write_rows(self.row("n6x6", "An absolute rule.", paths=["/repo/bin/*"]))
        ctx = self.context_of(self.run_hook(self.write("/repo/bin/skillnote")),
                              event="PreToolUse")
        self.assertIn("An absolute rule", ctx)

    def test_a_glob_is_a_glob_and_not_a_substring(self):
        """`tests/*.py` must not match `tests/data/x.py.bak`; the pattern is anchored at
        both ends by `case`."""
        self.assert_silent(self.run_hook(self.write("/repo/tests/test_x.py.bak")))

    def test_a_bash_call_does_not_go_through_the_path_arm(self):
        self.assert_silent(self.run_hook(self.bash("cat /repo/tests/test_x.py")))

    def test_a_tool_we_are_not_wired_for_is_silent(self):
        self.assert_silent(self.run_hook(self.write("/repo/tests/test_x.py", tool="Read")))


# ==================================================================== scope
class ScopeTest(RemindCase):
    """Scope is checked first, and it is a directory containment test rather than a
    prefix test: `/repo-other` starts with `/repo` and is a different project."""

    def setUp(self):
        super().setUp()
        self.write_rows(
            self.row("n7x7", "A project rule.", keywords=["alpha"], scope=PROJECT),
            self.row("n8x8", "A global rule.", keywords=["alpha"], scope="global"))

    def test_inside_the_scope_both_fire(self):
        ctx = self.context_of(self.run_hook(self.prompt("alpha", cwd=PROJECT)))
        self.assertIn("A project rule", ctx)
        self.assertIn("A global rule", ctx)

    def test_a_subdirectory_is_inside_the_scope(self):
        ctx = self.context_of(self.run_hook(self.prompt("alpha", cwd="/repo/tests/deep")))
        self.assertIn("A project rule", ctx)

    def test_a_sibling_project_gets_only_the_global_rule(self):
        ctx = self.context_of(self.run_hook(self.prompt("alpha", cwd="/other")))
        self.assertNotIn("A project rule", ctx)
        self.assertIn("A global rule", ctx)

    def test_a_prefix_that_is_not_a_subdirectory_is_not_inside_it(self):
        ctx = self.context_of(self.run_hook(self.prompt("alpha", cwd="/repo-other")))
        self.assertNotIn("A project rule", ctx)
        self.assertIn("A global rule", ctx)

    def test_a_payload_with_no_cwd_still_gets_global_rules(self):
        p = self.prompt("alpha")
        del p["cwd"]
        ctx = self.context_of(self.run_hook(p))
        self.assertNotIn("A project rule", ctx)
        self.assertIn("A global rule", ctx)

    def test_a_row_with_no_scope_at_all_is_treated_as_global(self):
        """And specifically NOT as "every path starts with /", which is what the naive
        spelling of the scope test does to a row whose scope is an empty string."""
        row = self.row("n9x9", "A scopeless rule.", keywords=["beta"])
        row["scope"] = ""
        self.write_rows(row)
        ctx = self.context_of(self.run_hook(self.prompt("beta", cwd="/somewhere/else")))
        self.assertIn("A scopeless rule", ctx)


# ==================================================================== ranking and cap
class RankingTest(RemindCase):
    """REMIND_MAX=2 by default, so which two arrive is a decision the hook makes on every
    event. score = 100 for a command match, +50 for a path match, +10 per keyword."""

    def test_the_cap_names_the_two_highest_scoring(self):
        self.write_rows(
            self.row("na", "THREE keywords.", keywords=["a", "b", "c"]),
            self.row("nb", "TWO keywords.", keywords=["a", "b"]),
            self.row("nc", "ONE keyword.", keywords=["a"]))
        ctx = self.context_of(self.run_hook(self.prompt("a b c")))
        self.assertIn("THREE keywords", ctx)
        self.assertIn("TWO keywords", ctx)
        self.assertNotIn("ONE keyword", ctx)
        self.assertEqual(len(ctx.split("\n")), 2)

    def test_the_higher_score_comes_first(self):
        self.write_rows(
            self.row("nb", "TWO keywords.", keywords=["a", "b"]),
            self.row("na", "THREE keywords.", keywords=["a", "b", "c"]))
        ctx = self.context_of(self.run_hook(self.prompt("a b c")))
        self.assertLess(ctx.index("THREE keywords"), ctx.index("TWO keywords"))

    def test_the_cap_is_configurable(self):
        self.write_rows(
            self.row("na", "THREE keywords.", keywords=["a", "b", "c"]),
            self.row("nb", "TWO keywords.", keywords=["a", "b"]))
        ctx = self.context_of(self.run_hook(self.prompt("a b c"), REMIND_MAX="1"))
        self.assertEqual(ctx.count("Reminder recorded"), 1)
        self.assertIn("THREE keywords", ctx)

    def test_a_tie_is_broken_by_fewer_live_hits(self):
        """An unheard reminder outranks one that has already been delivered."""
        self.write_rows(
            self.row("nd", "ALREADY heard.", keywords=["a"], created=1_756_838_400),
            self.row("ne", "NEVER heard.", keywords=["a"], created=1_756_838_400))
        os.makedirs(os.path.dirname(self.hits), exist_ok=True)
        with open(self.hits, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": "nd", "ts": 1, "session": "old",
                                 "event": "UserPromptSubmit"}) + "\n")
        ctx = self.context_of(self.run_hook(self.prompt("a"), REMIND_MAX="1"))
        self.assertIn("NEVER heard", ctx)

    def test_a_remaining_tie_is_broken_by_the_newer_row(self):
        self.write_rows(
            self.row("nf", "OLDER.", keywords=["a"], created=1_756_838_400),
            self.row("ng", "NEWER.", keywords=["a"], created=1_756_838_900))
        ctx = self.context_of(self.run_hook(self.prompt("a"), REMIND_MAX="1"))
        self.assertIn("NEWER", ctx)

    def test_a_command_match_outranks_a_path_match(self):
        sig = norm_of("./run_tests.sh")
        self.write_rows(
            self.row("nh", "PATH rule.", paths=["*"], scope="global"),
            self.row("ni", "COMMAND rule.", commands=[sig], scope="global"))
        ctx = self.context_of(self.run_hook(self.bash("./run_tests.sh")), event="PreToolUse")
        # A Bash call reaches only the command arm, so this also pins that the path arm
        # does not leak into it.
        self.assertIn("COMMAND rule", ctx)
        self.assertNotIn("PATH rule", ctx)


# ==================================================================== cooldown
class CooldownTest(RemindCase):

    def setUp(self):
        super().setUp()
        self.write_rows(self.row("nk", "Once is enough.", keywords=["alpha"]))

    def test_by_default_a_reminder_fires_once_per_session(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p1")))
        self.assert_silent(self.run_hook(self.prompt("alpha", session="s1", pid="p2")))

    def test_a_different_session_is_not_held_back(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="s1")))
        self.context_of(self.run_hook(self.prompt("alpha", session="s2")))

    def test_a_positive_cooldown_holds_it_back_until_it_expires(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p1"),
                                      REMIND_COOLDOWN="600"))
        self.assert_silent(self.run_hook(self.prompt("alpha", session="s1", pid="p2"),
                                         REMIND_COOLDOWN="600",
                                         REMIND_NOW=self.clock + 599))
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p3"),
                                      REMIND_COOLDOWN="600",
                                      REMIND_NOW=self.clock + 601))

    def test_a_clock_that_jumped_backwards_does_not_silence_it_forever(self):
        """The comparison is on |now - stamp|. A stamp from the future would otherwise
        hold the reminder back until the wall clock caught up."""
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p1"),
                                      REMIND_COOLDOWN="600"))
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p2"),
                                      REMIND_COOLDOWN="600",
                                      REMIND_NOW=self.clock - 5000))

    def test_the_stamp_holds_the_epoch_it_fired(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="s1")))
        stamp = os.path.join(self.state, "remind", "s1", "nk")
        self.assertEqual(open(stamp, encoding="utf-8").read().strip(), str(self.clock))

    def test_a_reminder_whose_stamp_cannot_be_written_is_not_emitted(self):
        """Firing on every event because the cooldown cannot be recorded is worse than
        not firing: the reminder would arrive on every prompt for the whole session."""
        sdir = os.path.join(self.state, "remind", "s1")
        os.makedirs(sdir)
        os.chmod(sdir, 0o500)
        try:
            self.assert_silent(self.run_hook(self.prompt("alpha", session="s1")))
        finally:
            os.chmod(sdir, 0o700)

    def test_a_held_back_reminder_does_not_consume_a_cap_slot(self):
        self.write_rows(self.row("nl", "Second.", keywords=["alpha"]),
                        self.row("nm", "Third.", keywords=["alpha"]))
        first = self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p1")))
        self.assertEqual(first.count("Reminder recorded"), 2)
        second = self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p2")))
        # The two already delivered are on cooldown; the third takes a slot rather than
        # being crowded out by them.
        self.assertEqual(second.count("Reminder recorded"), 1)
        for text in ("Once is enough", "Second.", "Third."):
            self.assertIn(text, first + second)


# ==================================================================== double delivery
class DoubleDeliveryTest(RemindCase):
    """With settings.json and the plugin both wired, every event is delivered twice."""

    def setUp(self):
        super().setUp()
        self.write_rows(self.row("nn", "Say it once.", keywords=["alpha"]))

    def test_the_same_prompt_delivered_twice_reminds_once(self):
        payload = self.prompt("alpha", session="s1", pid="p-abc")
        self.context_of(self.run_hook(payload))
        self.assert_silent(self.run_hook(payload))
        self.assertEqual(len(self.hit_rows()), 1, self.hit_rows())

    def test_the_same_tool_call_delivered_twice_reminds_once(self):
        self.write_rows(self.row("no", "Path once.", paths=["tests/*.py"]))
        payload = self.write("/repo/tests/test_x.py", session="s1", tuid="toolu_abc")
        self.context_of(self.run_hook(payload), event="PreToolUse")
        self.assert_silent(self.run_hook(payload))

    def test_the_claim_holds_even_once_the_cooldown_has_expired(self):
        """Isolates the claim from the cooldown: with a cooldown that has expired, only
        the per-event claim can be what suppresses the second delivery."""
        payload = self.prompt("alpha", session="s1", pid="p-abc")
        self.context_of(self.run_hook(payload, REMIND_COOLDOWN="10"))
        self.assert_silent(self.run_hook(payload, REMIND_COOLDOWN="10",
                                         REMIND_NOW=self.clock + 1000))

    def test_a_prompt_and_a_tool_call_sharing_an_id_do_not_claim_each_other(self):
        self.write_rows(self.row("np", "Path once.", paths=["tests/*.py"]))
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="dup")))
        self.context_of(self.run_hook(self.write("/repo/tests/t.py", session="s1",
                                                 tuid="dup")), event="PreToolUse")

    def test_an_event_with_no_id_still_fires(self):
        """Losing reminders is worse than a rare duplicate, so an unidentifiable event is
        always acted on."""
        p = self.prompt("alpha", session="s1")
        del p["prompt_id"]
        self.context_of(self.run_hook(p))

    def test_distinct_sessions_do_not_share_claims(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="alpha", pid="p-same")))
        self.context_of(self.run_hook(self.prompt("alpha", session="beta", pid="p-same")))


# ==================================================================== hits
class HitsTest(RemindCase):
    """The hook never rewrites the store. A delivery is an append to a separate log, and
    `skillnote list` derives the live count from it."""

    def test_a_delivery_appends_one_row_and_leaves_the_store_byte_identical(self):
        self.write_rows(self.row("nq", "Say it.", keywords=["alpha"]))
        before = open(self.store, "rb").read()
        self.context_of(self.run_hook(self.prompt("alpha", session="s1")))
        self.assertEqual(open(self.store, "rb").read(), before,
                         "the hook must never rewrite reminders.jsonl")
        rows = self.hit_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {"id": "nq", "ts": self.clock, "session": "s1",
                                   "event": "UserPromptSubmit"})

    def test_two_reminders_in_one_emit_are_two_hit_rows(self):
        self.write_rows(self.row("nr", "One.", keywords=["alpha"]),
                        self.row("ns", "Two.", keywords=["alpha"]))
        self.context_of(self.run_hook(self.prompt("alpha", session="s1")))
        self.assertEqual(sorted(r["id"] for r in self.hit_rows()), ["nr", "ns"])

    def test_a_tool_event_records_its_own_event_name(self):
        self.write_rows(self.row("nt", "Path.", paths=["tests/*.py"]))
        self.context_of(self.run_hook(self.write("/repo/tests/t.py", session="s1")),
                        event="PreToolUse")
        self.assertEqual(self.hit_rows()[0]["event"], "PreToolUse")


# ==================================================================== tombstones
class TombstoneTest(RemindCase):
    """Removal is an appended tombstone, never a rewrite -- the same doctrine as
    `skillrepeat forget`, and for the same reason: a hook and a CLI both hold this file
    open and a rewrite loses whatever was appended between the read and the write."""

    def test_a_tombstoned_row_never_fires(self):
        self.write_rows(self.row("nu", "Retired.", keywords=["alpha"]))
        self.context_of(self.run_hook(self.prompt("alpha", session="s0")))
        self.write_rows(self.tombstone("nu"))
        self.assert_silent(self.run_hook(self.prompt("alpha", session="s1")))

    def test_the_tombstone_removes_nothing_from_the_file(self):
        self.write_rows(self.row("nv", "Retired.", keywords=["alpha"]),
                        self.tombstone("nv"))
        self.assert_silent(self.run_hook(self.prompt("alpha")))
        self.assertIn("Retired.", open(self.store, encoding="utf-8").read())

    def test_a_row_re_added_after_its_tombstone_fires_again(self):
        """The tombstone kills ids created at or before it, not the id forever."""
        self.write_rows(self.row("nw", "First life.", keywords=["alpha"],
                                 created=1_756_838_400),
                        self.tombstone("nw", ts=1_756_838_500),
                        self.row("nw", "Second life.", keywords=["alpha"],
                                 created=1_756_838_600))
        ctx = self.context_of(self.run_hook(self.prompt("alpha")))
        self.assertIn("Second life", ctx)

    def test_only_the_tombstoned_id_goes_quiet(self):
        self.write_rows(self.row("nx", "Gone.", keywords=["alpha"]),
                        self.row("ny", "Still here.", keywords=["alpha"]),
                        self.tombstone("nx"))
        ctx = self.context_of(self.run_hook(self.prompt("alpha")))
        self.assertNotIn("Gone.", ctx)
        self.assertIn("Still here", ctx)


# ==================================================================== fail open
class FailOpenTest(RemindCase):
    """A hook may never break a turn. Every path below exits 0 and says nothing."""

    def seed(self):
        self.write_rows(self.row("nz", "Anything.", keywords=["alpha"]))

    def test_the_off_switch(self):
        self.seed()
        self.assert_silent(self.run_hook(self.prompt("alpha"),
                                         SKILL_COMPOUNDER_REMIND="0"))

    def test_no_store_at_all(self):
        self.assert_silent(self.run_hook(self.prompt("alpha")))

    def test_an_empty_store(self):
        open(self.store, "w").close()
        self.assert_silent(self.run_hook(self.prompt("alpha")))

    def test_a_store_of_garbage(self):
        with open(self.store, "w", encoding="utf-8") as fh:
            fh.write("not json at all\n{\"half\": \n\n")
        self.assert_silent(self.run_hook(self.prompt("alpha")))

    def test_a_malformed_line_does_not_hide_the_rows_around_it(self):
        """`jq -s` over a store with one bad line fails the WHOLE read, which would make
        a store stop working forever because something once wrote half a line."""
        with open(self.store, "w", encoding="utf-8") as fh:
            fh.write("{\"broken\": \n")
        self.seed()
        ctx = self.context_of(self.run_hook(self.prompt("alpha")))
        self.assertIn("Anything.", ctx)

    def test_a_row_with_no_text_is_skipped(self):
        row = self.row("n00", "", keywords=["alpha"])
        self.write_rows(row)
        self.assert_silent(self.run_hook(self.prompt("alpha")))

    def test_a_row_whose_id_cannot_be_a_filename_is_skipped(self):
        """The id names the cooldown stamp under <state>/remind/<sid>/, so an id carrying
        a slash would write outside that directory. An id we cannot honour a cooldown for
        is one we must not fire."""
        self.write_rows(self.row("../../escape", "Escaped.", keywords=["alpha"]))
        self.assert_silent(self.run_hook(self.prompt("alpha")))

    def test_a_payload_that_is_not_json(self):
        self.seed()
        self.assert_silent(self.run_hook("this is not json"))

    def test_an_empty_payload(self):
        self.seed()
        self.assert_silent(self.run_hook(""))

    def test_an_unknown_hook_event(self):
        self.seed()
        self.assert_silent(self.run_hook(self.prompt("alpha",
                                                     hook_event_name="PostToolUse")))

    def test_a_payload_with_no_session_id_still_fires(self):
        """A missing session id costs a shared cooldown bucket, not the reminder."""
        self.seed()
        p = self.prompt("alpha")
        del p["session_id"]
        ctx = self.context_of(self.run_hook(p))
        self.assertIn("Anything.", ctx)

    def test_an_unwritable_state_directory(self):
        self.seed()
        os.chmod(self.state, 0o500)
        try:
            self.assert_silent(self.run_hook(self.prompt("alpha")))
        finally:
            os.chmod(self.state, 0o700)

    def test_garbage_tunables_do_not_reach_arithmetic(self):
        """A typo'd export must not print `[: integer expected` from a hook on the user's
        stderr for the rest of the session."""
        self.seed()
        r = self.run_hook(self.prompt("alpha"), REMIND_MAX="lots",
                          REMIND_COOLDOWN="soon", REMIND_MAX_ROWS="many",
                          REMIND_NOW="yesterday")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr.strip(), "", "a hook must not write to stderr")
        self.assertIn("Anything.", json.loads(r.stdout)["hookSpecificOutput"]
                      ["additionalContext"])

    def test_a_cap_of_zero_says_nothing(self):
        self.seed()
        self.assert_silent(self.run_hook(self.prompt("alpha"), REMIND_MAX="0"))

    def test_without_jq_it_is_silent(self):
        """The dependency check runs before anything reads stdin, so a bare PATH
        exercises it exactly."""
        self.seed()
        bare = os.path.join(self.tmp, "emptybin")
        os.makedirs(bare)
        os.symlink(shutil.which("bash") or "/bin/bash", os.path.join(bare, "bash"))
        self.assert_silent(self.run_hook(self.prompt("alpha"), PATH=bare))

    def test_only_the_last_max_rows_are_read(self):
        """The read is bounded, and the bound is the TAIL: the newest rows are the ones
        that survive it."""
        self.write_rows(*[self.row("nold%d" % i, "Old %d." % i, keywords=["alpha"])
                          for i in range(5)])
        self.write_rows(self.row("nnew", "Newest.", keywords=["alpha"]))
        ctx = self.context_of(self.run_hook(self.prompt("alpha"), REMIND_MAX_ROWS="1",
                                            REMIND_MAX="5"))
        self.assertEqual(ctx.count("Reminder recorded"), 1)
        self.assertIn("Newest.", ctx)


# ==================================================================== cost
class CostTest(RemindCase):
    """This runs before EVERY Bash, Write and Edit call and on every prompt, so its cost
    is paid hundreds of times a session. The figure quoted in the design is 500 rows under
    300 ms; it is measured here rather than assumed, and printed so it can be re-read."""

    def fill(self, n=500, matching=1):
        rows = []
        for i in range(n - matching):
            rows.append(self.row("nc%06d" % i, "Filler reminder number %d." % i,
                                 keywords=["kw%d" % i, "other"],
                                 paths=["src/%d/*.py" % i],
                                 scope=PROJECT if i % 2 else "global",
                                 created=1_756_000_000 + i))
        for i in range(matching):
            rows.append(self.row("nhit%02d" % i, "The one that matches.",
                                 keywords=["alpha"], created=1_756_900_000))
        self.write_rows(*rows)
        return os.path.getsize(self.store)

    def timed(self, label, payload):
        size = self.fill()
        runs = []
        for i in range(5):
            p = dict(payload)
            p["session_id"] = "cost%d" % i
            p["prompt_id"] = "p%d" % i
            p["tool_use_id"] = "t%d" % i
            t0 = time.time()
            r = self.run_hook(p)
            runs.append(time.time() - t0)
            self.assertEqual(r.returncode, 0, r.stderr)
        runs.sort()
        median = runs[len(runs) // 2]
        print("\n[cost] remind/%s: 500 rows, %d bytes, median %.0f ms (min %.0f, max %.0f)"
              % (label, size, median * 1000, runs[0] * 1000, runs[-1] * 1000))
        self.assertLess(median, 0.300,
                        "a 500-row store took %.0f ms on %s" % (median * 1000, label))
        return median

    def test_a_prompt_against_500_rows(self):
        self.timed("UserPromptSubmit", self.prompt("alpha"))

    def test_a_write_against_500_rows(self):
        self.timed("PreToolUse/Write", self.write("/repo/src/1/x.py"))

    def test_a_bash_call_against_500_rows(self):
        """The most expensive arm: it forks the shared normaliser as well."""
        self.timed("PreToolUse/Bash", self.bash("gh pr list"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
