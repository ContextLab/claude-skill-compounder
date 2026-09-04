#!/usr/bin/env python3
"""Tests for hooks/repeat-gate.sh and bin/skillrepeat -- the repeated-failure gate.

NO MOCKS, per this repo's standing rule. Every test runs the real shell scripts through
subprocess with a minimal PATH, a HOME inside a temp directory and SKILL_COMPOUNDER_STATE
pinned there, feeds them real payloads on stdin, and reads the store back off disk.

PAYLOAD SHAPES ARE COPIED FROM MEASURED ONES, not invented. Recorded on this machine
2026-08-26, Claude Code 2.1.245:

  PostToolUseFailure keys: cwd, duration_ms, error, hook_event_name, is_interrupt,
    permission_mode, prompt_id, session_id, tool_input, tool_name, tool_use_id,
    transcript_path.  There is NO tool_response.  `.error` for a failed Bash reads
    "Exit code 1\\nls: /x: No such file or directory".
  PostToolUse additionally carries tool_response and duration_ms, and carries no
    `entrypoint`.
  A FAILED Bash call fires ONLY PostToolUseFailure -- there is no PostToolUse for it,
  which is why the recovery arm can assume every PostToolUse it sees was a success.

EVERY subprocess call against the hook passes `input=`. The script reads its payload with
`payload="$(cat)"`; without stdin it hangs forever.

The clock is pinned with REPEAT_GATE_NOW (the hook's own) and SKILLREPEAT_NOW (the CLI's).
Pinning either one alone would leave the other reading the wall clock, and the tombstone
tests depend on the ORDER of the two.

THE REFUSE ARM IS OFF IN THE SHIPPED DEFAULT (`REPEAT_GATE_REFUSE`, issue #27), and this
harness switches it ON for every test. Every refusal test here predates that default and
is worth keeping exactly as it is: what the default changed is whether the arm runs, not
what it decides when it does. `RefuseArmDefaultTest` is the one class that takes the
variable back out -- `run_hook(..., REPEAT_GATE_REFUSE=None)` DELETES it rather than
setting it empty -- and asserts what a user with no configuration at all actually gets.
"""

import json
import os
import re
import shutil
import subprocess
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "repeat-gate.sh")
CLI = os.path.join(REPO, "bin", "skillrepeat")

# Minimal, explicit environment: the scripts must not depend on the ambient one.
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"

GH_ERR = "Exit code 127\ngh: command not found"
NET_ERR = "Exit code 1\ncurl: (7) Failed to connect to api.github.com port 443"

# Input that SATURATES both of the gate's normalisers: norm_bash caps the call at 400
# characters and the error class at 200, so anything longer than those produces the widest
# byte counts hashof() can print -- and therefore the widest signature the gate can write.
# Nothing here is a width; the widths are read back off what the gate does with this.
SATURATING_CMD = ("gh api repos/o/r/issues --paginate --jq '.[]|.number' "
                  + "--field key=value " * 40)
SATURATING_ERR = ("Exit code 127\n"
                  + "gh: command not found; see https://cli.github.com/manual/ " * 6)

# THE CANONICAL FAIL-THEN-FIX PAIR, AND IT SHARES CONTENT TOKENS ON PURPOSE.
#
# Since 2026-09-03 a SAME-TOOL `Bash` binding wants REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS (2) content
# tokens in common with the call that failed -- THE SAME-TOOL RULE IS NOT EVIDENCE FOR A
# SHELL, in the hook's header, and the live store that argued it. So a fixture pair like
# `gh pr list` -> `curl -s https://x/y` shares NOTHING (the URL is masked to `<P>` before
# tokens are taken, and `gh` and `pr` are under the three-character floor), and a test
# built on one now measures the new rule turning it away rather than whatever it was
# written for. Every pair below shares `list` and `limit`, which is what a real
# fail-then-fix usually looks like: the same command, corrected.
#
# THE TWO `--search` SPELLINGS NORMALISE TO ONE SHAPE (`--search <S>`) and the other two do
# not, which is what lets one fixture produce an AGREED recovery across two sessions and
# another produce a DISPUTED one. Do not "tidy" them into each other.
FAILING_CMD = "gh pr list --limit 5"
FIX_CMD = "gh pr list --limit 5 --repo ContextLab/claude-skill-compounder"
FIX_CMD_2 = "gh pr list --limit 5 --state open"
FIX_SEARCH_A = 'gh pr list --limit 5 --search "author:alice"'
FIX_SEARCH_B = 'gh pr list --limit 5 --search "author:bob"'
# A success sharing NOTHING with FAILING_CMD: the shape the same-tool rule now refuses.
UNRELATED_OK = "cat notes/OPEN-THREADS.md"


class GateCase(unittest.TestCase):
    """Shared harness: one temp state root per test, real scripts, real payloads."""

    def setUp(self):
        self.tmp = os.path.join(
            os.environ.get("TMPDIR", "/tmp"),
            "repeat-gate-%d-%d" % (os.getpid(), int(time.time() * 1e6) % 10 ** 9))
        os.makedirs(self.tmp)
        self.home = os.path.join(self.tmp, "home")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.home)
        self.clock = 1_000_000

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------- plumbing
    @property
    def store(self):
        return os.path.join(self.state, "repeats", "index.jsonl")

    def env(self, **extra):
        """`REPEAT_GATE_REFUSE=1` is part of the BASELINE here; see the module docstring.

        A value of None DELETES the key instead of stringifying it, which is what lets a
        test measure a genuinely unset variable. `str(None)` would export the four
        characters `None`, and a `case` guard reading that is not reading an unset
        variable -- it happens to reach the same branch here, and a test that depends on
        that coincidence is testing the wrong thing."""
        e = {"PATH": BASE_PATH, "HOME": self.home,
             "SKILL_COMPOUNDER_STATE": self.state,
             "REPEAT_GATE_NOW": str(self.clock),
             "REPEAT_GATE_REFUSE": "1"}
        for k, v in extra.items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = str(v)
        return e

    def run_hook(self, payload, **env_extra):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(["bash", HOOK], input=body, capture_output=True,
                              text=True, env=self.env(**env_extra), timeout=180)

    def run_cli(self, *args, **env_extra):
        timeout = env_extra.pop("timeout", 180)
        return subprocess.run(["bash", CLI] + list(args), input="",
                              capture_output=True, text=True,
                              env=self.env(**env_extra), timeout=timeout)

    def tick(self, n=1):
        self.clock += n
        return self.clock

    # ------------------------------------------------------------------- payloads
    def failure(self, command, session, error=GH_ERR, tuid=None, tool="Bash", **over):
        p = {"hook_event_name": "PostToolUseFailure", "session_id": session,
             "transcript_path": os.path.join(self.tmp, "t.jsonl"), "cwd": "/repo",
             "prompt_id": "p1", "permission_mode": "acceptEdits",
             "tool_name": tool, "tool_use_id": tuid or ("toolu_f_%d" % self.clock),
             "tool_input": ({"command": command, "description": "d"}
                            if tool == "Bash" else command),
             "error": error, "is_interrupt": False, "duration_ms": 12}
        p.update(over)
        return p

    def success(self, command, session, tuid=None, tool="Bash", **over):
        p = {"hook_event_name": "PostToolUse", "session_id": session,
             "transcript_path": os.path.join(self.tmp, "t.jsonl"), "cwd": "/repo",
             "prompt_id": "p1", "permission_mode": "acceptEdits",
             "tool_name": tool, "tool_use_id": tuid or ("toolu_s_%d" % self.clock),
             "tool_input": ({"command": command, "description": "d"}
                            if tool == "Bash" else command),
             "tool_response": {"stdout": "ok", "stderr": "", "interrupted": False},
             "duration_ms": 30}
        p.update(over)
        return p

    def attempt(self, command, session, tuid=None, tool="Bash", **over):
        p = {"hook_event_name": "PreToolUse", "session_id": session,
             "transcript_path": os.path.join(self.tmp, "t.jsonl"), "cwd": "/repo",
             "prompt_id": "p1", "permission_mode": "acceptEdits",
             "tool_name": tool, "tool_use_id": tuid or ("toolu_p_%d" % self.clock),
             "tool_input": ({"command": command, "description": "d"}
                            if tool == "Bash" else command)}
        p.update(over)
        return p

    # ------------------------------------------------------------------- assertions
    def assert_allowed(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "",
                         "the gate spoke when it should have been silent: %r" % r.stdout)
        return r

    def assert_denied(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.strip(), "expected a deny, got silence")
        d = json.loads(r.stdout)
        hso = d["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertEqual(hso["permissionDecision"], "deny")
        return hso["permissionDecisionReason"]

    def rows(self):
        if not os.path.exists(self.store):
            return []
        out = []
        with open(self.store, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    out.append({"t": "__unparsed__", "raw": line})
        return out

    # ------------------------------------------------------------------- scenarios
    def filler(self, session, i=0, **over):
        """A success that CONSUMES the recovery window and can never claim it.

        THE TOOL HAS TO BE ONE THE MATCHER REALLY DELIVERS. These were `Read` calls until
        2026-09-03 and every window test built on them was measuring a route no session
        can produce: the matcher has never selected `Read`, and the script now leaves on a
        payload shape it has no rule for, so a `Read` success consumes nothing. An
        `mcp__*` name is delivered on PostToolUse and is a DIFFERENT tool from both `Bash`
        and the MCP tool these tests fail on, so it reaches the cross-tool rule and is
        turned away there by the token overlap -- `page` and `slug` share nothing with a
        `gh` command or a `claude-skill-compounder` repo argument."""
        p = self.success({"page": "p%d" % i, "slug": "unrelated-filler"}, session,
                         tool="mcp__docs__fetch", tuid="toolu_fill_%d_%d" % (i, self.clock))
        p.update(over)
        return p

    def teach(self, command, sessions, error=GH_ERR, tool="Bash"):
        """Record one failure of `command` in each of `sessions`, at distinct times."""
        for s in sessions:
            self.tick()
            self.run_hook(self.failure(command, s, error=error, tool=tool))


# ============================================================== the refusal itself
class RefusalTest(GateCase):

    def test_two_distinct_sessions_deny_the_third(self):
        self.teach("gh pr list --limit 5", ["s1", "s2"])
        self.tick()
        reason = self.assert_denied(self.run_hook(self.attempt("gh pr list --limit 5", "s3")))
        self.assertIn("2 earlier sessions", reason)
        # The verbatim error head is what makes the refusal actionable rather than
        # merely obstructive.
        self.assertIn("gh: command not found", reason)

    def test_one_session_is_not_enough(self):
        self.teach("gh pr list --limit 5", ["s1"])
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list --limit 5", "s3")))

    def test_the_same_session_can_never_lock_itself_out(self):
        """Guard 1 against a bootstrap deadlock: own failures never count.

        Three failures in ONE session is three rows and one distinct session, so the
        threshold of two is not met however many times it happens.
        """
        self.teach("gh pr list --limit 5", ["s1", "s1", "s1"])
        self.assertEqual(len([r for r in self.rows() if r["t"] == "fail"]), 3)
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list --limit 5", "s1")))

    def test_it_denies_once_per_session_per_signature(self):
        """The second attempt goes through. An unconditional block on a false positive
        is unrecoverable, and the whole point is that the session was told what worked."""
        self.teach("gh pr list --limit 5", ["s1", "s2"])
        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list --limit 5", "s3",
                                                      tuid="toolu_a")))
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list --limit 5", "s3",
                                                       tuid="toolu_b")))
        # ...but a DIFFERENT session still gets told once.
        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list --limit 5", "s4")))

    def test_a_double_delivered_pretooluse_denies_only_once(self):
        """Both wirings active deliver every event twice; the deny-once claim is what
        stops the session being refused twice for one attempt."""
        self.teach("gh pr list --limit 5", ["s1", "s2"])
        self.tick()
        p = self.attempt("gh pr list --limit 5", "s3", tuid="toolu_dup")
        self.assert_denied(self.run_hook(p))
        self.assert_allowed(self.run_hook(p))

    def test_irrelevant_variation_does_not_split_the_signature(self):
        """Two sessions running the same call with different literals and integers are
        two sessions hitting one problem, which is the whole basis of the count."""
        self.tick(); self.run_hook(self.failure("gh issue view 19 --json body", "s1"))
        self.tick(); self.run_hook(self.failure("gh issue view 4271 --json body", "s2"))
        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh issue view 3 --json body", "s3")))

    def test_a_different_command_is_a_different_problem(self):
        self.teach("gh pr list --limit 5", ["s1", "s2"])
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr view 12", "s3")))


# ============================================================== signature semantics
class SignatureTest(GateCase):

    def sigs(self):
        return sorted({r["sig"] for r in self.rows() if r["t"] == "fail"})

    def test_the_same_command_failing_differently_does_not_share_a_signature(self):
        """THE load-bearing property of the two-part signature. A transient network
        failure and a missing binary are different facts about one command, and only a
        repeated STRUCTURAL failure is worth refusing a third session over."""
        self.tick(); self.run_hook(self.failure("gh pr list", "s1", error=GH_ERR))
        self.tick(); self.run_hook(self.failure("gh pr list", "s2", error=NET_ERR))
        self.assertEqual(len(self.sigs()), 2,
                         "one command, two error classes, but the store recorded "
                         "%r" % self.sigs())
        # Both rows share the callkey -- that is what lets the refusal arm find them
        # before the call runs -- but neither signature has two sessions behind it.
        cks = {r["ck"] for r in self.rows() if r["t"] == "fail"}
        self.assertEqual(len(cks), 1, "the callkey should not depend on the error")
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "s3")))

    def test_the_same_error_class_twice_does_deny(self):
        """Non-vacuity for the test above: with the error class held constant, the very
        same two sessions DO produce a refusal. Without this the test above would pass
        for any reason at all, including the gate being broken."""
        self.tick(); self.run_hook(self.failure("gh pr list", "s1", error=GH_ERR))
        self.tick(); self.run_hook(self.failure("gh pr list", "s2", error=GH_ERR))
        self.assertEqual(len(self.sigs()), 1)
        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list", "s3")))

    def test_the_error_class_ignores_varying_numbers_and_paths(self):
        """`ls: /a/b: No such file` and `ls: /c/d: No such file` are one class."""
        self.tick()
        self.run_hook(self.failure("ls -l --color", "s1",
                                   error="Exit code 1\nls: /a/b: No such file or directory"))
        self.tick()
        self.run_hook(self.failure("ls -l --color", "s2",
                                   error="Exit code 2\nls: /c/d/e: No such file or directory"))
        self.assertEqual(len(self.sigs()), 1, self.sigs())

    def test_a_structured_tool_gets_a_signature_too(self):
        """Not everything is Bash. `Skill` was the ONLY non-Bash tool the matcher
        delivered when this was written -- it used to use `mcp__gh__list_prs`, which
        nothing then delivered, so it demonstrated the branch on a route that did not
        exist while the live route went untested. Since 2026-09-03 the two learning events
        carry `Bash|Skill|mcp__.*`, so an MCP name is a live route as well; this one stays
        on `Skill` because both routes take the same branch and MatcherDeliveryTest drives
        the new one end to end."""
        a = {"skill": "finish-task", "args": "x"}
        b = {"args": "x", "skill": "finish-task"}      # `jq -S` makes key order irrelevant
        self.tick(); self.run_hook(self.failure(a, "s1", tool="Skill",
                                                error="Exit code 1\nnot connected"))
        self.tick(); self.run_hook(self.failure(b, "s2", tool="Skill",
                                                error="Exit code 1\nnot connected"))
        self.assertEqual(len(self.sigs()), 1, self.sigs())

    def test_a_skill_call_is_learned_but_never_refused(self):
        """LEARN BROADLY, REFUSE NARROWLY. Both of the refuse arm's escape hatches -- the
        `*skillrepeat*` guard and `allowlisted_head` -- sit inside the Bash branch, so a
        refused `Skill` call had no way past the refusal and no way to retire the signature
        behind it. A cold reviewer demonstrated a live deny of a Skill call on 2026-08-27
        by seeding two fail rows under the callkey `norm_structured` produces.

        The rows are still written: a Skill failure is data `skillreport` wants. Only the
        refusal is withheld."""
        a = {"skill": "finish-task"}
        for s in ("s1", "s2"):
            self.tick()
            self.run_hook(self.failure(a, s, tool="Skill",
                                       error="Exit code 1\nnot connected"))
        self.assertEqual(len(self.sigs()), 1,
                         "the failure was not learned: %s" % self.sigs())
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt(a, "s3", tool="Skill")))
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt(a, "s4", tool="Skill")))

    def test_an_interrupted_call_is_not_a_failure(self):
        """A user pressing stop is not the tool being broken. Recording it would teach
        the gate to refuse whatever they interrupted, in every later session."""
        self.tick()
        self.run_hook(self.failure("gh pr list", "s1", is_interrupt=True))
        self.tick()
        self.run_hook(self.failure("gh pr list", "s2", is_interrupt=True))
        self.assertEqual(self.rows(), [])


# ============================================== a red suite is not a broken call
class TestRunnerTest(GateCase):
    """A test suite that is red across two sessions had its first run in the third
    session DENIED. The call is not broken -- the code under test is -- and running it
    is precisely what the third session must do. Found by a cold reviewer on 2026-08-27
    driving the real hook: `./run_tests.sh` failing the same way in two sessions denied
    the third, and `python3 -m pytest tests/` reproduced it identically. It lands exactly
    on the loop the user's own CLAUDE.md mandates: when tests fail repeatedly, fix the
    code so the existing tests succeed.

    `runner_head` is a SECOND allowlist and a different argument from `allowlisted_head`:
    that one holds commands whose failure is nobody's bug, this one holds runners whose
    failure is the point.
    """

    SUITE_ERR = ("Exit code 1\n"
                 "FAILED tests/test_thing.py::test_it - AssertionError: 1 != 2")

    def _two_red_sessions(self, cmd):
        for s in ("s1", "s2"):
            self.tick()
            self.run_hook(self.failure(cmd, s, error=self.SUITE_ERR))
        self.tick()

    def test_a_repositorys_own_runner_script_is_never_refused(self):
        self._two_red_sessions("./run_tests.sh")
        self.assert_allowed(self.run_hook(self.attempt("./run_tests.sh", "s3")))

    def test_pytest_through_the_interpreter_is_never_refused(self):
        """The runner is the MODULE here; the head is only an interpreter."""
        self._two_red_sessions("python3 -m pytest tests/")
        self.assert_allowed(self.run_hook(self.attempt("python3 -m pytest tests/", "s3")))

    def test_a_bare_runner_is_never_refused(self):
        self._two_red_sessions("pytest -q tests/")
        self.assert_allowed(self.run_hook(self.attempt("pytest -q tests/", "s3")))

    def test_a_runner_under_an_absolute_path_and_an_assignment_is_never_refused(self):
        """Matched on the head as `allowlisted_head` leaves it: assignments stepped over,
        directory stripped."""
        cmd = "CI=1 /opt/proj/run_tests.sh --fast"
        self._two_red_sessions(cmd)
        self.assert_allowed(self.run_hook(self.attempt(cmd, "s3")))

    def test_a_multi_purpose_driver_is_gated_on_its_subcommand(self):
        """`npm test` failing means the code is broken. `npm install` failing in session
        after session is a broken call and is EXACTLY what this gate is for -- so the
        driver is allowlisted on its SUBCOMMAND and never wholesale. Both directions in
        one test, because the pair is the whole point of the distinction."""
        self._two_red_sessions("npm test")
        self.assert_allowed(self.run_hook(self.attempt("npm test", "s3")))

        install = "npm install --no-audit"
        for s in ("t1", "t2"):
            self.tick()
            self.run_hook(self.failure(install, s,
                                       error="Exit code 1\nERR! ENOTFOUND registry"))
        self.tick()
        reason = self.assert_denied(self.run_hook(self.attempt(install, "t3")))
        self.assertIn("npm install", reason)

    def test_a_non_runner_failing_the_same_way_twice_is_still_refused(self):
        """NON-VACUITY. Every assertion above is on SILENCE, and a gate that refused
        nothing at all would satisfy all of them."""
        self._two_red_sessions("gh pr list --state open")
        reason = self.assert_denied(self.run_hook(
            self.attempt("gh pr list --state open", "s3")))
        self.assertIn("gh pr list", reason)


# ====================================================== callkey collisions
class CallkeyCollisionTest(GateCase):
    """THE CALLKEY IS A SHAPE, AND A SHAPE THAT IS TOO COARSE REFUSES CALLS THAT NEVER RAN.

    Reproduced against the real hook before the fix, with a pinned clock and a temp state
    root. Two `python3 -c "import boto3"` failures in sess-1 and sess-2, then a
    `python3 -c "print(1+1)"` attempt in sess-3 that had never been seen: the gate printed
    `permissionDecision: deny`, "This exact call has already failed in 2 earlier sessions,
    the same way each time.", and "the call: `python3 -c <S>`". Same shape for two
    different scripts: failures on `python3 /Users/x/build.py --jobs 4` denied
    `python3 /Users/y/deploy.py --jobs 8`. Both are `test_..._is_a_different_call` below,
    and both FAILED on the code that shipped before rules 2 and 4 of the header existed.

    Every test here has a partner. The two reproductions are paired with a non-vacuity
    test showing the very same setup still refuses what it should, because a normaliser
    that simply stopped masking would pass the reproductions and destroy the gate; and the
    argument-varying `gh` case -- the real case from the issue this gate was built for --
    is asserted to SURVIVE. The residual collisions are pinned as deliberate: a collision
    that is named and bounded is fine, one that is undocumented is the defect repeated.
    """

    BOTO_ERR = "Exit code 1\nModuleNotFoundError: No module named boto3"

    def key_of(self, command, session):
        """Record one failure and read back the (callkey, shape) the gate computed.

        Straight off the store, so the pins below assert on what the normaliser produced
        rather than on the deny path's opinion of it.
        """
        self.tick()
        self.run_hook(self.failure(command, session, error=self.BOTO_ERR))
        fails = [r for r in self.rows() if r["t"] == "fail"]
        self.assertTrue(fails, "no fail row was written for %r" % command)
        return fails[-1]["ck"], fails[-1]["norm"]

    def assert_collides(self, a, b, why):
        cka, na = self.key_of(a, "r1")
        ckb, nb = self.key_of(b, "r2")
        self.assertEqual(cka, ckb,
                         "%s -- expected one callkey, got %r for %r and %r for %r"
                         % (why, na, a, nb, b))
        return na

    def assert_distinct(self, a, b, why):
        cka, na = self.key_of(a, "r1")
        ckb, nb = self.key_of(b, "r2")
        self.assertNotEqual(cka, ckb,
                            "%s -- both landed on %r" % (why, na))
        return na, nb

    # ------------------------------------------------- reproduction 1: the eval program
    def test_a_different_eval_program_is_a_different_call(self):
        """`python3 -c "print(1+1)"` has never failed and must not be refused."""
        self.teach('python3 -c "import boto3"', ["sess-1", "sess-2"], error=self.BOTO_ERR)
        self.tick()
        self.assert_allowed(self.run_hook(
            self.attempt('python3 -c "print(1+1)"', "sess-3")))

    def test_the_same_eval_program_is_still_refused(self):
        """Non-vacuity for the test above: the identical program, same two sessions, is
        refused. Without this, deleting the masking entirely would pass."""
        self.teach('python3 -c "import boto3"', ["sess-1", "sess-2"], error=self.BOTO_ERR)
        self.tick()
        reason = self.assert_denied(self.run_hook(
            self.attempt('python3 -c "import boto3"', "sess-3")))
        self.assertIn("<C:import boto3>", reason)

    def test_the_quoting_style_of_an_eval_program_does_not_split_it(self):
        """`-c 'x'` and `-c "x"` are the same program, and a session that switched quote
        styles between attempts is still the same session hitting the same call."""
        self.assert_collides('python3 -c "import boto3"', "python3 -c 'import boto3'",
                             "quote style is not part of the program")

    def test_a_clustered_eval_flag_keeps_its_program_too(self):
        """`perl -ne` is the same case as `python3 -c`, which is why the rule matches a
        short cluster ENDING in c/e/E rather than the two bare flags."""
        a, b = self.assert_distinct("perl -ne 'print uc'", "perl -ne 'print lc'",
                                    "two perl one-liners are two calls")
        self.assertIn("<C:print uc>", a)
        self.assertIn("<C:print lc>", b)

    # ------------------------------------------------- reproduction 2: the path basename
    def test_a_different_script_basename_is_a_different_call(self):
        """`deploy.py` has never failed; only `build.py` has."""
        self.teach("python3 /Users/x/build.py --jobs 4", ["sess-1", "sess-2"],
                   error=self.BOTO_ERR)
        self.tick()
        self.assert_allowed(self.run_hook(
            self.attempt("python3 /Users/y/deploy.py --jobs 8", "sess-3")))

    def test_the_same_script_under_a_moved_checkout_is_still_refused(self):
        """Non-vacuity, and the reason rule 4 masks anything at all: the DIRECTORY is what
        legitimately varies between machines and checkouts, and a checkout that moved must
        not look like a new problem."""
        self.teach("python3 /Users/x/proj/build.py --jobs 4", ["sess-1", "sess-2"],
                   error=self.BOTO_ERR)
        self.tick()
        reason = self.assert_denied(self.run_hook(
            self.attempt("python3 /Users/y/elsewhere/build.py --jobs 8", "sess-3")))
        self.assertIn("<P>/build.py", reason)

    def test_a_single_segment_absolute_path_keeps_its_name(self):
        """`/opt` has no directory part that could vary between machines, so there is
        nothing to mask and it is left alone rather than reduced to a bare `<P>`."""
        _, norm = self.key_of("tar -xf /opt", "s1")
        self.assertIn("/opt", norm)
        self.assertNotIn("<P>", norm)

    # ------------------------------------------------- the feature that must survive
    def test_varying_argument_text_still_recognises_one_broken_call(self):
        """THE REAL CASE FROM ISSUE #19. Two sessions run `gh issue comment` with wholly
        different body text and different issue numbers; that is two sessions hitting ONE
        broken call, and the gate must still say so on the third."""
        self.tick()
        self.run_hook(self.failure('gh issue comment 19 --body "first draft"', "s1"))
        self.tick()
        self.run_hook(self.failure(
            'gh issue comment 4271 --body "quite another message entirely"', "s2"))
        self.tick()
        reason = self.assert_denied(self.run_hook(
            self.attempt('gh issue comment 3 --body "a third one"', "s3")))
        self.assertIn("gh issue comment <N> --body <S>", reason)

    def test_an_ordinary_flag_argument_is_still_masked(self):
        """`--body` and `-m` are not eval-like flags. Rule 2 must not have widened into
        rule 3 and kept every quoted argument."""
        self.assert_collides('git commit -m "wip: one thing"',
                             'git commit -m "and now a completely different message"',
                             "a commit message is an argument, not a program")

    # ------------------------------------------------- the deny reason's honesty
    def test_the_deny_reason_does_not_claim_the_call_was_exact(self):
        """The store cannot support "this exact call": the attempt below differs from
        what failed, matches only after masking, and is refused on that basis. The reason
        has to say so."""
        self.teach("gh pr list --limit 5", ["s1", "s2"])
        self.tick()
        reason = self.assert_denied(self.run_hook(
            self.attempt("gh pr list --limit 9", "s3")))
        self.assertNotIn("exact", reason)
        self.assertIn("NORMALISED SHAPE", reason)
        self.assertIn("the shape:", reason)
        self.assertIn("gh pr list --limit <N>", reason)

    # ------------------------------------------------- residual collisions, pinned
    # Each of these is a shape that STILL covers more than one literal command after the
    # fix. They are asserted to collide, on purpose, so that the header's WHAT STILL
    # COLLIDES list cannot quietly stop being true and so that a later reader finds them
    # named rather than reporting them as new. All fail in the same direction: one
    # refusal, once per session, and the next attempt goes through.
    def test_residual_a_quoted_program_in_a_positional_slot_still_collides(self):
        """Rule 2 keys off a FLAG. Finding the program slot of an arbitrary command needs
        per-program knowledge this script has no business carrying."""
        norm = self.assert_collides('ssh box "systemctl restart a"',
                                    'ssh box "rm -rf /tmp/x"',
                                    "a positional quoted command is not covered")
        self.assertIn("ssh box <S>", norm)

    def test_residual_two_awk_programs_still_collide(self):
        """The same residual in its other common costume: awk's program is positional."""
        self.assert_collides("awk '{print $1}' data.txt", "awk '{print $7}' data.txt",
                             "awk's program is positional, not flagged")

    def test_residual_nested_quotes_inside_a_kept_program_still_collide(self):
        """Rule 3 runs over the text rule 2 kept, so two programs identical outside their
        own string literals share a key."""
        norm = self.assert_collides("""python3 -c "print('hi')" ""","""python3 -c "print('bye')" """,
                                    "nested quotes inside a kept program")
        self.assertIn("<C:print(<S>)>", norm)

    def test_residual_bare_integers_still_collide(self):
        """Rule 5, and it is wanted: `gh issue view 19` and `gh issue view 4271` are one
        broken call, which is the same masking seen from the other side."""
        self.assert_collides("sleep 5", "sleep 9", "bare integers are masked by rule 5")

    def test_residual_a_url_host_is_masked_like_a_directory(self):
        """Rule 4 cannot tell a URL's host from a directory: both are the part before the
        last segment."""
        self.assert_collides("curl -sS https://api.github.com/x",
                             "curl -sS https://example.com/x",
                             "a URL host normalises like a directory")

    def test_residual_the_four_hundred_character_cap_still_collides(self):
        """Rule 6, and rule 2 made it matter more: a KEPT program is text that counts
        against the 400-character cap, where a masked `<S>` was three characters."""
        pad = "a" * 400
        norm = self.assert_collides('python3 -c "%s ONE"' % pad,
                                    'python3 -c "%s TWO"' % pad,
                                    "the shape is capped at 400 characters")
        self.assertEqual(len(norm), 400,
                         "expected a shape truncated at the cap, got %d chars" % len(norm))
        self.assertNotIn("ONE", norm)

    # ------------------------------------------------- the two masks differ on purpose
    def test_the_error_classifier_still_masks_a_whole_path(self):
        """THE ASYMMETRY, asserted from both sides in one test.

        The call normaliser keeps a basename; the error classifier does not. One command,
        failing twice with the SAME message about DIFFERENT files, is one signature -- or
        a random temp basename in an error would give every session its own class and
        nothing would ever reach the threshold.
        """
        self.tick()
        self.run_hook(self.failure(
            "python3 /Users/x/proj/build.py", "s1",
            error="Exit code 1\nFileNotFoundError: /tmp/tmpaaa/one.csv"))
        self.tick()
        self.run_hook(self.failure(
            "python3 /Users/y/other/build.py", "s2",
            error="Exit code 1\nFileNotFoundError: /tmp/tmpzzz/two.csv"))
        sigs = {r["sig"] for r in self.rows() if r["t"] == "fail"}
        self.assertEqual(len(sigs), 1,
                         "one call and one error class, but the store recorded %r" % sigs)
        # ...and the call side of the same pair keeps its basename, which is what makes
        # the asymmetry a choice rather than an accident.
        norms = {r["norm"] for r in self.rows() if r["t"] == "fail"}
        self.assertEqual(norms, {"python3 <P>/build.py"})
        self.tick()
        self.assert_denied(self.run_hook(
            self.attempt("python3 /Users/z/third/build.py", "s3")))


# ============================================================== recovery capture
class RecoveryTest(GateCase):

    def test_the_first_success_of_the_same_tool_is_recorded_as_the_recovery(self):
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s1"))
        self.tick(); self.run_hook(self.success(FIX_CMD, "s1"))
        rec = [r for r in self.rows() if r["t"] == "recover"]
        self.assertEqual(len(rec), 1, self.rows())
        self.assertEqual(rec[0]["cmd"], FIX_CMD)

    def test_only_the_first_success_is_bound(self):
        """One recovery per armed failure. A session that goes on working must not
        attach every later command to the same signature."""
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s1"))
        self.tick(); self.run_hook(self.success(FIX_CMD, "s1"))
        self.tick(); self.run_hook(self.success(FIX_CMD_2, "s1"))
        self.assertEqual(len([r for r in self.rows() if r["t"] == "recover"]), 1)

    def test_a_success_of_another_tool_does_not_bind(self):
        """A DIFFERENT tool with nothing in common: it reaches the cross-tool rule and is
        turned away by the token overlap, which is the only thing standing between the two.
        The other tool has to be one the matcher delivers, or this passes for the wrong
        reason -- see `filler`."""
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s1"))
        self.tick(); self.run_hook(self.filler("s1"))
        self.assertEqual([r for r in self.rows() if r["t"] == "recover"], [])

    def test_the_window_expires_and_a_late_success_is_not_the_fix(self):
        """The bound that stops an unrelated command twenty steps later from being
        recorded as the fix. Successes of any tool THIS HOOK IS WIRED FOR consume the
        window -- and nothing else is delivered, so the stream is far sparser than every
        tool call the session makes."""
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s1"))
        for i in range(5):
            self.tick()
            self.run_hook(self.filler("s1", i))
        self.tick(); self.run_hook(self.success(FIX_CMD, "s1"))
        self.assertEqual([r for r in self.rows() if r["t"] == "recover"], [],
                         "a success six calls after the failure was recorded as the fix")

    def test_inside_the_window_it_is_still_the_fix(self):
        """Non-vacuity for the window test: two intervening calls, same everything else,
        and the recovery IS recorded."""
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s1"))
        for i in range(2):
            self.tick()
            self.run_hook(self.filler("s1", i))
        self.tick(); self.run_hook(self.success(FIX_CMD, "s1"))
        self.assertEqual(len([r for r in self.rows() if r["t"] == "recover"]), 1)

    def test_the_window_is_configurable(self):
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s1"),
                                   REPEAT_RECOVERY_WINDOW=1)
        self.tick(); self.run_hook(self.filler("s1"), REPEAT_RECOVERY_WINDOW=1)
        self.tick(); self.run_hook(self.success(FIX_CMD, "s1"),
                                   REPEAT_RECOVERY_WINDOW=1)
        self.assertEqual([r for r in self.rows() if r["t"] == "recover"], [])

    def test_the_plurality_recovery_appears_in_the_deny_reason(self):
        """Two of three sessions reached for the same shape; one used something else. The
        refusal names the one the plurality agreed on, and says how many sessions that was.

        The two agreeing fixes differ in a QUOTED argument, which the normaliser masks to
        `<S>`, so they are one shape to the plurality while being two distinct commands on
        the wire -- exactly the case the grouping is by `norm` for."""
        for s, fix in (("s1", FIX_SEARCH_A), ("s2", FIX_SEARCH_B), ("s3", FIX_CMD_2)):
            self.tick(); self.run_hook(self.failure(FAILING_CMD, s))
            self.tick(); self.run_hook(self.success(fix, s))
        self.tick()
        reason = self.assert_denied(self.run_hook(self.attempt(FAILING_CMD, "s9")))
        self.assertIn("what worked instead, in 2 of them", reason)
        self.assertIn("--search", reason)
        self.assertNotIn("--state open", reason)

    def test_a_tie_names_no_recovery(self):
        """Announcing one of two equally-supported commands as `what worked` would be an
        invention, and this store's whole value is that it never invents."""
        for s, fix in (("s1", FIX_CMD), ("s2", FIX_CMD_2)):
            self.tick(); self.run_hook(self.failure(FAILING_CMD, s))
            self.tick(); self.run_hook(self.success(fix, s))
        self.tick()
        reason = self.assert_denied(self.run_hook(self.attempt(FAILING_CMD, "s9")))
        self.assertIn("none of them is agreed", reason)
        self.assertNotIn("what worked instead", reason)

    def test_a_success_of_the_same_call_is_not_a_recovery(self):
        """DEFECT: the deny naming the blocked call as its own cure. A flaky command that
        fails and then succeeds on the retry is the transient case the two-part signature
        exists to separate out, and the recovery arm binds by TOOL, so it binds the very
        call that just failed. A self-recovery is proof the call works, so the signature is
        not refused at all -- not refused while naming nothing."""
        net = "Exit code 1\nerror connecting to api.github.com: connection reset"
        for s in ("f1", "f2"):
            self.tick(); self.run_hook(self.failure("gh pr list", s, error=net))
            self.tick(); self.run_hook(self.success("gh pr list", s))
        # the recovery row IS written -- the recovery arm cannot know, and the exclusion
        # belongs where the refusal is decided, on the whole record. It is written even
        # though `gh pr list` carries ONE content token and the same-tool rule now wants
        # two: an exact self-recovery is carved out of that floor precisely so this
        # exclusion keeps its input (THE SAME-TOOL RULE IS NOT EVIDENCE FOR A SHELL).
        self.assertEqual(len([r for r in self.rows() if r["t"] == "recover"]), 2)
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "f3")))

    def test_a_self_recovery_does_not_get_named_even_beside_a_real_one(self):
        """Two sessions retried the identical call and it worked; a third found a genuine
        different command. The identical call must not be named, and the one session that
        proved the call can work is enough to stop the refusal."""
        net = "Exit code 1\nerror connecting to api.github.com: connection reset"
        for s, fix in (("f1", FAILING_CMD), ("f2", FAILING_CMD), ("f3", FIX_CMD)):
            self.tick(); self.run_hook(self.failure(FAILING_CMD, s, error=net))
            self.tick(); self.run_hook(self.success(fix, s))
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "f9")))

    def test_a_genuine_different_command_is_still_named(self):
        """Non-vacuity for both tests above: with the recoveries genuinely different from
        the failing call, the very same shape still refuses and still names the fix."""
        net = "Exit code 1\nerror connecting to api.github.com: connection reset"
        for s in ("f1", "f2"):
            self.tick(); self.run_hook(self.failure(FAILING_CMD, s, error=net))
            self.tick()
            self.run_hook(self.success(FIX_CMD, s))
        self.tick()
        reason = self.assert_denied(self.run_hook(self.attempt(FAILING_CMD, "f3")))
        self.assertIn("what worked instead, in 2 of them", reason)
        self.assertIn("--repo ContextLab/claude-skill-compounder", reason)
        self.assertNotIn("\n  gh pr list --limit <N>\n", reason)

    def test_the_cli_agrees_that_a_self_recovered_signature_does_not_refuse(self):
        """A CLI that reported `refuses` for a signature the gate lets through is exactly
        the disagreement the two queries exist to avoid."""
        net = "Exit code 1\nerror connecting to api.github.com: connection reset"
        for s in ("f1", "f2"):
            self.tick(); self.run_hook(self.failure("gh pr list", s, error=net))
            self.tick(); self.run_hook(self.success("gh pr list", s))
        got = json.loads(self.run_cli("list", "--json").stdout)
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0]["sessions"], 2)
        self.assertEqual(got[0]["transient_sessions"], 2)
        self.assertFalse(got[0]["refuses"])
        self.assertEqual(got[0]["recovery"], "")
        self.assertIn("transient", self.run_cli("list").stdout)
        self.assertEqual(json.loads(self.run_cli("stats", "--json").stdout)["refusing"], 0)

    def test_with_no_recovery_the_refusal_says_so(self):
        self.teach("gh pr list", ["s1", "s2"])
        self.tick()
        reason = self.assert_denied(self.run_hook(self.attempt("gh pr list", "s3")))
        self.assertIn("No recovery was ever recorded", reason)


# ============================================================== double delivery
class DoubleDeliveryTest(GateCase):
    """Both wirings active deliver every hook event TWICE (measured, 2.1.241). Anything
    this script appends must survive being handed the same event a second time."""

    def test_a_repeated_failure_event_writes_exactly_one_row(self):
        p = self.failure("gh pr list", "s1", tuid="toolu_same")
        self.run_hook(p)
        self.run_hook(p)
        self.assertEqual(len([r for r in self.rows() if r["t"] == "fail"]), 1,
                         self.rows())

    def test_a_repeated_success_event_writes_exactly_one_recovery(self):
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s1"))
        self.tick()
        p = self.success(FIX_CMD, "s1", tuid="toolu_same_s")
        self.run_hook(p)
        self.run_hook(p)
        self.assertEqual(len([r for r in self.rows() if r["t"] == "recover"]), 1,
                         self.rows())

    def test_a_repeated_success_event_consumes_the_window_only_once(self):
        """The subtler half. A double-delivered success that decremented the window
        twice would halve REPEAT_RECOVERY_WINDOW silently, which is exactly the defect
        the claim exists to prevent -- and it would be invisible, because the recovery
        row count would still look right."""
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s1"))
        for i in range(2):
            self.tick()
            p = self.filler("s1", i, tool_use_id="toolu_fill_dup_%d" % i)
            self.run_hook(p)
            self.run_hook(p)          # the duplicate delivery
        self.tick(); self.run_hook(self.success(FIX_CMD, "s1"))
        self.assertEqual(len([r for r in self.rows() if r["t"] == "recover"]), 1,
                         "four deliveries of two calls burned the window: %r" % self.rows())

    def test_denied_session_directories_do_not_accumulate(self):
        """DEFECT: prune_claims collected `denied/<sid>/<marker>` and never the
        `denied/<sid>` that held it -- one empty directory per denied session, forever.

        The two-line sweep cannot collect in ONE pass what it just emptied: removing the
        marker RESETS the parent's mtime, so the parent is brand new to `-mtime +7`. That
        lag is deliberate (a `-empty` sweep with no age test could rmdir a directory a live
        PreToolUse had just created), so this ages the parents again and runs a second
        pass, which is where the collection has to happen."""
        denied = os.path.join(self.state, "repeats", "denied")
        old = time.time() - 10 * 86400
        parents = [os.path.join(denied, sid) for sid in ("sidA", "sidB")]
        for parent in parents:
            os.makedirs(os.path.join(parent, "marker"))
            os.utime(os.path.join(parent, "marker"), (old, old))
            os.utime(parent, (old, old))

        self.tick(); self.run_hook(self.failure("gh pr list", "z1", tuid="tz1"))
        for parent in parents:
            self.assertFalse(os.path.exists(os.path.join(parent, "marker")),
                             "the aged marker survived the sweep")
            os.utime(parent, (old, old))     # the removal reset it; age it again

        self.tick(); self.run_hook(self.failure("gh pr list", "z1", tuid="tz2"))
        for parent in parents:
            self.assertFalse(os.path.exists(parent),
                             "an emptied, aged denied/<sid> was never collected: %s"
                             % parent)

    def test_a_refusal_sweeps_the_denied_directories_too(self):
        """DEFECT: `prune_claims` was called from exactly ONE site, inside the
        PostToolUseFailure arm. The REFUSE arm is the only writer of `denied/<sid>`, so on a
        machine that refuses but records no failure of its own the sweep those last two
        lines exist for never ran at all -- an aged `denied/oldsid` survived a PreToolUse
        and a PostToolUse and was collected only by a PostToolUseFailure.

        Here the ONLY events after the aged directory is planted are PreToolUse denials."""
        self.teach("gh pr list", ["s1", "s2"])
        denied = os.path.join(self.state, "repeats", "denied")
        old = time.time() - 10 * 86400
        stale = os.path.join(denied, "oldsid")
        os.makedirs(os.path.join(stale, "marker"))
        os.utime(os.path.join(stale, "marker"), (old, old))
        os.utime(stale, (old, old))

        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list", "s3")))
        self.assertFalse(os.path.exists(os.path.join(stale, "marker")),
                         "a refusal did not sweep the aged marker: prune_denied still runs "
                         "on the failure arm only")
        os.utime(stale, (old, old))     # the removal reset the parent's mtime; age it again

        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list", "s4")))
        self.assertFalse(os.path.exists(stale),
                         "an emptied, aged denied/<sid> was never collected by a refusal")

    def test_a_refusal_does_not_sweep_the_claims_tree(self):
        """DEFECT: one sweep function collected BOTH trees and the REFUSE arm called it, so
        every deny walked `claims/` -- one marker per tool call, hundreds a session, kept
        two days. The comment justified it by refusals being rare, which is true and beside
        the point: a sweep costs what its TREE costs, not what its trigger's frequency is,
        and the deny path is in front of a tool call the session is blocked on.

        `claims/` is now swept by the arms that write it. A refusal must leave it alone --
        including an aged marker it would happily have collected."""
        self.teach("gh pr list", ["s1", "s2"])
        claims = os.path.join(self.state, "repeats", "claims")
        old_t = time.time() - 10 * 86400
        stale = os.path.join(claims, "oldsid", "f-oldtuid")
        os.makedirs(stale)
        for path in (stale, os.path.dirname(stale)):
            os.utime(path, (old_t, old_t))

        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list", "s3")))
        self.assertTrue(os.path.isdir(stale),
                        "a refusal walked and collected the claims tree: the deny path is "
                        "sweeping a tree it does not write")

        # Non-vacuity: the sweep still exists, on the arm that owns the tree.
        self.tick()
        self.run_hook(self.failure("ls /nope", "s4", tuid="tz8"))
        self.assertFalse(os.path.exists(stale),
                         "the LEARN arm no longer sweeps the claims tree either")

    def test_a_live_denied_directory_is_not_swept_out_from_under_a_refusal(self):
        """Non-vacuity, and the reason the age test is not dropped: a directory created
        moments ago must survive the sweep."""
        self.teach("gh pr list", ["s1", "s2"])
        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list", "s3")))
        live = os.path.join(self.state, "repeats", "denied", "s3")
        self.assertTrue(os.path.isdir(live))
        self.tick(); self.run_hook(self.failure("ls /nope", "s4", tuid="tz9"))
        self.assertTrue(os.path.isdir(live), "the sweep took a live session's marker dir")

    def test_an_event_with_no_tool_use_id_is_still_recorded(self):
        """A payload that cannot be claimed is always acted on. A duplicated row costs a
        wasted line; a dropped one costs the whole observation."""
        p = self.failure("gh pr list", "s1")
        del p["tool_use_id"]
        self.run_hook(p)
        self.assertEqual(len([r for r in self.rows() if r["t"] == "fail"]), 1)


# ============================================================== fail-open paths
class FailOpenTest(GateCase):
    """Every one of these must allow the call and print nothing. A gate that refuses when
    it cannot see is a gate that refuses at random."""

    def test_the_off_switch(self):
        self.teach("gh pr list", ["s1", "s2"])
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "s3"),
                                          SKILL_COMPOUNDER_REPEAT_GATE=0))

    def test_the_off_switch_also_stops_it_learning(self):
        self.run_hook(self.failure("gh pr list", "s1"),
                      SKILL_COMPOUNDER_REPEAT_GATE=0)
        self.assertEqual(self.rows(), [])

    def test_no_store_at_all(self):
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "s3")))

    def test_an_empty_store(self):
        os.makedirs(os.path.dirname(self.store))
        open(self.store, "w").close()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "s3")))

    def test_a_store_over_the_byte_cap(self):
        self.teach("gh pr list", ["s1", "s2"])
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "s3"),
                                          REPEAT_GATE_MAX_BYTES=10))
        # Non-vacuity: with the cap where it belongs, this same call is refused.
        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list", "s3")))

    def test_an_unreadable_store(self):
        self.teach("gh pr list", ["s1", "s2"])
        os.chmod(self.store, 0o000)
        try:
            self.tick()
            self.assert_allowed(self.run_hook(self.attempt("gh pr list", "s3")))
        finally:
            os.chmod(self.store, 0o644)

    def test_an_unwritable_state_directory(self):
        os.makedirs(os.path.join(self.state, "repeats"))
        os.chmod(os.path.join(self.state, "repeats"), 0o500)
        try:
            r = self.run_hook(self.failure("gh pr list", "s1"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "")
        finally:
            os.chmod(os.path.join(self.state, "repeats"), 0o755)

    def test_a_payload_that_is_not_json(self):
        r = self.run_hook("this is not json at all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_an_empty_payload(self):
        r = self.run_hook("")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_a_payload_with_no_session_id(self):
        """Every count here is a count of DISTINCT SESSIONS. With no session there is
        nothing to count, and inventing one would corrupt the threshold."""
        self.teach("gh pr list", ["s1", "s2"])
        p = self.attempt("gh pr list", "s3")
        del p["session_id"]
        self.assert_allowed(self.run_hook(p))

    def test_a_payload_with_no_tool_name(self):
        p = self.attempt("gh pr list", "s3")
        del p["tool_name"]
        self.assert_allowed(self.run_hook(p))

    def test_a_bash_payload_with_no_command(self):
        self.teach("gh pr list", ["s1", "s2"])
        p = self.attempt("gh pr list", "s3")
        p["tool_input"] = {}
        self.assert_allowed(self.run_hook(p))

    def test_an_unknown_hook_event(self):
        for ev in ("Stop", "UserPromptSubmit", "SessionStart", ""):
            with self.subTest(event=ev):
                p = self.attempt("gh pr list", "s3")
                p["hook_event_name"] = ev
                self.assert_allowed(self.run_hook(p))

    def test_a_failure_payload_with_no_error(self):
        p = self.failure("gh pr list", "s1")
        del p["error"]
        self.run_hook(p)
        self.assertEqual(self.rows(), [])

    def test_without_jq_the_gate_is_silent(self):
        """The dependency check is the very first thing after the off switch, before
        anything reads stdin, so a bare PATH exercises it exactly."""
        self.teach("gh pr list", ["s1", "s2"])
        bare = os.path.join(self.tmp, "emptybin")
        os.makedirs(bare)
        # bash itself has to be reachable or this measures the wrong thing; everything
        # else the script would need comes after the `command -v jq` check.
        os.symlink(shutil.which("bash") or "/bin/bash", os.path.join(bare, "bash"))
        self.tick()
        r = self.run_hook(self.attempt("gh pr list", "s3"), PATH=bare)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_garbage_tunables_do_not_reach_arithmetic(self):
        """A typo'd export must not print `[: integer expected` from a hook on the
        user's stderr for the rest of the session."""
        self.teach("gh pr list", ["s1", "s2"])
        self.tick()
        r = self.run_hook(self.attempt("gh pr list", "s3"),
                          REPEAT_MIN_SESSIONS="two", REPEAT_RECOVERY_WINDOW="lots",
                          REPEAT_GATE_MAX_BYTES="big", REPEAT_GATE_NOW="soon")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stderr, "", "a hook wrote to stderr: %r" % r.stderr)
        # Falling back to the documented default of 2 means this is still a refusal.
        self.assert_denied(r)


# ============================================================== a hostile store
class MalformedStoreTest(GateCase):

    def poison(self, *lines):
        os.makedirs(os.path.dirname(self.store), exist_ok=True)
        with open(self.store, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")

    def test_unparsable_and_foreign_lines_are_skipped_not_fatal(self):
        """Another tool's file landing in the state directory, or a row half-written by a
        killed hook, must cost the observations in that row and nothing else."""
        self.poison("not json at all", "", "[1,2,3]", '"a bare string"',
                    '{"t":"fail"}', '{"unrelated":"row"}')
        self.teach("gh pr list", ["s1", "s2"])
        self.poison('{"t":"fail","ts":"not-a-number","sig":"x","ck":"x"}')
        self.tick()
        reason = self.assert_denied(self.run_hook(self.attempt("gh pr list", "s3")))
        self.assertIn("2 earlier sessions", reason)

    def test_the_cli_survives_the_same_store(self):
        self.poison("not json at all", "[1,2,3]", '{"t":"fail"}')
        self.teach("gh pr list", ["s1", "s2"])
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gh pr list", r.stdout)
        r = self.run_cli("stats", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        # `{"t":"fail"}` parses but carries no signature, so it is not a failure anyone
        # can act on and it is excluded exactly where the signatures are counted.
        got = json.loads(r.stdout)
        self.assertEqual(got["failures"], 2)
        self.assertEqual(got["signatures"], 1)


# ============================================================== bootstrap deadlock
class NoCornerTest(GateCase):
    """A gate that learns from failures can learn to refuse the commands needed to
    inspect or undo it. Each of these is one of the four guards, tested where it bites."""

    def deny_would_fire(self, command):
        """Prove the store really would refuse this shape, so an allow below is the
        allowlist and not an empty store."""
        self.teach(command, ["s1", "s2"])

    def test_navigation_and_inspection_heads_are_never_refused(self):
        for command in ("ls -la /repo", "cd /repo && ./run_tests.sh", "cat notes/x.md",
                        "grep -rn foo src", "git push origin main", "jq . a.json",
                        "find . -name '*.py'", "FOO=1 ls /repo"):
            with self.subTest(command=command):
                self.tearDown(); self.setUp()
                self.deny_would_fire(command)
                self.tick()
                self.assert_allowed(self.run_hook(self.attempt(command, "s3")))

    def test_a_command_reaching_for_the_cli_is_never_refused(self):
        cmd = "gh pr list && skillrepeat list"
        self.deny_would_fire(cmd)
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt(cmd, "s3")))

    def test_the_allowlist_is_not_a_blanket(self):
        """Non-vacuity for the whole class: a non-allowlisted head with the same history
        IS refused, and `jq` after a pipe does not launder it -- consulting every command
        position would retire the gate for the commonest shape of the real defect."""
        for command in ("gh pr list --limit 5", "gh issue view 19 | jq .body"):
            with self.subTest(command=command):
                self.tearDown(); self.setUp()
                self.deny_would_fire(command)
                self.tick()
                self.assert_denied(self.run_hook(self.attempt(command, "s3")))


# ============================================================== what the wiring admits
class NormOfTest(GateCase):
    """`--norm-of <tool>` is the normaliser reachable on its own, and hooks/remind.sh
    matches a reminder's `commands` rule by BYTE EQUALITY against what it prints.

    That makes these tests the join between two scripts: if this arm ever stopped agreeing
    with what the LEARN arm records, a reminder would quietly stop firing and both halves
    would still look correct in isolation. So the expected value is never written down
    here -- it is read off the store the gate itself wrote.
    """

    def norm_of(self, text, tool="Bash", **env_extra):
        return subprocess.run(["bash", HOOK, "--norm-of", tool], input=text,
                              capture_output=True, text=True,
                              env=self.env(**env_extra), timeout=180)

    def learned_norm(self, command, tool="Bash"):
        """What the LEARN arm records as the norm for this call."""
        self.tick()
        self.run_hook(self.failure(command, "s-learn", tool=tool))
        rows = [r for r in self.rows() if r.get("t") == "fail"]
        self.assertEqual(len(rows), 1, rows)
        return rows[0]["norm"]

    def test_it_prints_exactly_what_the_learn_arm_records(self):
        cmd = 'gh issue comment 19 --body "first draft"'
        expected = self.learned_norm(cmd)
        r = self.norm_of(cmd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), expected)

    def test_the_five_hundred_character_cap_is_applied_here_too(self):
        """`compute_call` caps the raw command before normalising. Skipping the cap here
        would make byte equality a coin flip on any command longer than that."""
        cmd = SATURATING_CMD
        expected = self.learned_norm(cmd)
        self.assertEqual(self.norm_of(cmd).stdout.strip(), expected)

    def test_two_literals_of_one_call_normalise_the_same(self):
        a = self.norm_of('gh issue comment 19 --body "first draft"').stdout
        b = self.norm_of('gh issue comment 4271 --body "quite another message"').stdout
        self.assertEqual(a, b)
        self.assertNotEqual(a.strip(), self.norm_of("gh pr list").stdout.strip())

    def test_a_structured_tool_agrees_with_the_learn_arm_as_well(self):
        payload = {"name": "skill-compounder", "input": {"x": 1}}
        expected = self.learned_norm(payload, tool="Skill")
        r = self.norm_of(json.dumps(payload), tool="Skill")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), expected)

    def test_it_writes_nothing_at_all(self):
        """A pure function of its stdin. It is called from another hook on ordinary tool
        calls, so a store row per invocation would corrupt the gate's own session counts."""
        r = self.norm_of("gh pr list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.strip())
        self.assertFalse(os.path.exists(self.state),
                         "--norm-of created state: %s"
                         % (os.path.exists(self.state)
                            and os.listdir(self.state) or ""))

    def test_the_off_switch_does_not_reach_it(self):
        """Two scripts, two switches. Turning this gate off must not silently stop
        hooks/remind.sh matching commands, with nothing on any surface to say why."""
        r = self.norm_of("gh pr list", SKILL_COMPOUNDER_REPEAT_GATE="0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "gh pr list")

    def test_a_missing_tool_name_is_a_refusal_the_caller_can_see(self):
        r = self.norm_of("gh pr list", tool="")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout.strip(), "")

    def test_an_empty_command_prints_nothing(self):
        r = self.norm_of("")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_a_structured_tool_given_something_that_is_not_json_prints_nothing(self):
        r = self.norm_of("not json at all", tool="Skill")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_the_ordinary_arms_still_work_after_the_argv_check(self):
        """The guards `--norm-of` skips are the ones a real payload needs; a real payload
        must still meet every one of them."""
        self.teach("gh pr list", ["s1", "s2"])
        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list", "s3")))


class WiringTest(unittest.TestCase):
    """The matcher is a REGEX over the tool name, and since 2026-09-03 it is TWO strings
    over three events -- the same pair in BOTH install paths:

        PostToolUseFailure  `Bash|Skill|mcp__.*`   the two events that LEARN and RECOVER
        PostToolUse         `Bash|Skill|mcp__.*`
        PreToolUse          `Bash|Skill`           the one event that REFUSES

    Measured 2026-08-26 on 2.1.246 (docs/CLAUDE-CODE-BEHAVIOR.md, "A hook matcher is a
    regex over the tool name, not a substring"): of eight matchers on one event, `Bash`,
    `^Ba`, `Ba.*`, `Bash|mcp__.*`, `*` and `.*` all received a `Bash` call; `Ba` and `as`
    received nothing. `Bash|mcp__.*` receiving its `Bash` call is the whole of the evidence
    that a third alternative cannot cost the first two. That probe measured NOTHING about
    whether `mcp__.*` reaches a real MCP tool, and none has been observed arriving here, so
    the widening is unproven rather than proven -- which is a thing the header has to keep
    saying, and which the prose assertions below pin.

    The learning events are wider than the refusing one because nothing on PreToolUse reads
    a non-Bash payload: `lesson_gate` leaves on `[ "$tool" = "Bash" ]` and the repeat arm's
    Bash branch exits on everything else, both escape hatches being inside it. Below that
    it is still a cost bound -- this hook forks on every delivery and the read tools are the
    high-frequency ones -- and that bound is still the ONLY thing protecting Read/Glob/Grep
    from this gate. An in-script ALLOWLIST for them stays forbidden: the event is never
    delivered, so the case arm could never run. (The shape test at the top of the payload
    read is not that arm. It names what the script has a rule for instead of sparing a tool
    a refusal, and MatcherDeliveryTest drives it rather than reading the source.)"""

    EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure")
    MATCHERS = {"PreToolUse": "Bash|Skill",
                "PostToolUse": "Bash|Skill|mcp__.*",
                "PostToolUseFailure": "Bash|Skill|mcp__.*"}

    def test_both_install_paths_wire_the_same_matcher_on_each_event(self):
        """PER EVENT, and not one value asserted three times. The two learning events
        widened and the refusing one did not, so a test carrying a single shared value
        would have had to be loosened to something that also passes on the two being
        swapped -- which is the drift this whole test exists to catch."""
        seen = {}
        with open(os.path.join(REPO, "hooks", "hooks.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        for event, groups in manifest["hooks"].items():
            for group in groups:
                for hook in group.get("hooks", []):
                    if "repeat-gate.sh" in hook.get("command", ""):
                        seen[event] = group.get("matcher")
        self.assertEqual(sorted(seen), sorted(self.EVENTS), seen)
        self.assertEqual(seen, self.MATCHERS, seen)

        with open(os.path.join(REPO, "skill_compounder", "installer.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('REPEAT_LEARN_MATCHER = "Bash|Skill|mcp__.*"', src,
                      "the installer and the plugin manifest disagree about the matcher "
                      "the two learning events carry")
        self.assertIn('REPEAT_PRE_MATCHER = "Bash|Skill"', src,
                      "the installer and the plugin manifest disagree about the matcher "
                      "the refusing event carries")
        self.assertNotIn("REPEAT_MATCHER", src,
                         "the single-matcher constant is gone; a surviving reference means "
                         "one of its three uses was left pointing at a name that no longer "
                         "exists, which is an ImportError at install time")

    def test_the_gate_carries_no_allowlist_for_a_tool_it_can_never_receive(self):
        """A `case "$tool" in Read|Glob|Grep) exit 0` arm cannot fire under any of these
        matchers -- `Bash|Skill` on PreToolUse, `Bash|Skill|mcp__.*` on the two that learn,
        and no Read, Glob or Grep in either. Shipping a safety check nobody can reach is the
        defect skills/dead-guard-detection exists for, and re-adding one must fail here
        rather than read as caution.

        WHAT THIS DOES NOT FORBID is the `[ ]` shape test the payload read now begins with.
        That is not an exemption for a tool: it declines to compute a signature for a
        payload shape there is no normalising rule for, which became necessary when the
        second alternative stopped being an exact name. `--eligible-of`'s own tool test is
        written as `[ ]` for the same reason, and this assertion has always been about the
        `case` form specifically."""
        with open(HOOK, encoding="utf-8") as fh:
            body = [ln for ln in fh if not ln.lstrip().startswith("#")]
        for line in body:
            if line.lstrip().startswith("case ") and '"$tool"' in line:
                self.fail("the gate dispatches on $tool outside a comment, which the "
                          "`Bash|Skill` matcher makes dead code: %r" % line.strip())

    def test_the_header_describes_the_wiring_it_actually_has(self):
        """Prose that contradicts the wiring is how the dead guard got justified for three
        header lines. The recovery window counts what this hook is WIRED for, and the
        header claimed for its whole life that an `mcp__*` payload could never be delivered
        -- true until 2026-09-03 and false the moment the matcher widened, which is exactly
        the sentence a reader would have trusted."""
        with open(HOOK, encoding="utf-8") as fh:
            head = fh.read()
        self.assertFalse("successful tool calls, of any tool" in head,
                         "the window is documented as counting a stream it never sees")
        self.assertIn("Bash|Skill", head,
                      "the header never names the wiring it is describing")
        self.assertIn("Bash|Skill|mcp__.*", head,
                      "the header never names the matcher the two learning events carry")
        self.assertNotIn("All three events are wired with the matcher", head,
                         "the header still describes one matcher over three events")
        self.assertNotIn("so an `mcp__*` payload is never delivered", head,
                         "the header still says an MCP payload cannot reach this script")
        self.assertNotIn("UNREACHABLE ON THE CURRENT WIRING", head,
                         "the header claimed norm_structured was unreachable while every "
                         "`Skill` delivery reaches it; this assertion used to REQUIRE that "
                         "false sentence, and would have passed unchanged if the behaviour "
                         "it named had been removed")
        self.assertIn("REACHED BY EVERY `Skill` CALL", head,
                      "the header must say which tool actually takes that branch")
        self.assertIn("UNMEASURED", head,
                      "`mcp__.*` reaching a real MCP tool has never been observed")

    def test_the_cli_does_not_claim_its_query_is_the_gate_s(self):
        """The two queries agree on outcomes and are not the same query: the gate filters
        to one callkey and drops the current session before it groups, which is what keeps
        it flat. Claiming they are identical is what hid the CLI's cost."""
        with open(CLI, encoding="utf-8") as fh:
            src = fh.read()
        self.assertFalse("Identical in every clause" in src,
                         "bin/skillrepeat still claims its query is the gate's")


class MatcherDeliveryTest(GateCase):
    """WHAT THE WIDENED MATCHER HANDS THIS SCRIPT, driven through the real hook.

    WiringTest pins the strings; this pins what the script does with what they select, and
    the two are different silences. A matcher that selects nothing looks exactly like a
    hook with nothing to say, and a script that keys a payload it has no rule for looks
    exactly like one that ignored it -- neither shows up on any other surface."""

    MCP = "mcp__github__create_issue"
    MCP_ERR = "Exit code 1\nHTTP 403: Resource not accessible by integration"
    READ_INPUT = {"file_path": "/Users/x/proj/missing.py"}

    def test_an_mcp_failure_the_widened_matcher_delivers_is_learned(self):
        """The half of the maintainer's own example that could not fire before: under
        `Bash|Skill` a `mcp__*` name reached this script only when a test fed it one."""
        self.tick()
        r = self.run_hook(self.failure(
            {"owner": "ContextLab", "repo": "claude-skill-compounder", "title": "x"},
            "s1", error=self.MCP_ERR, tool=self.MCP))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "", r.stdout)
        fails = [x for x in self.rows() if x["t"] == "fail"]
        self.assertEqual(len(fails), 1, self.rows())
        self.assertEqual(fails[0]["tool"], self.MCP, fails)
        self.assertIn("ContextLab", fails[0]["norm"], fails)

    def test_a_tool_none_of_our_matchers_selects_writes_nothing(self):
        """A delivery this script has no rule for costs nothing and leaves no trace, on
        every one of the three events.

        NOT VACUOUS, and that was checked against the previous version of the hook rather
        than assumed: driven at the pre-2026-09-03 script, this same `Read` failure was
        keyed by `norm_structured` and stored as
        `{"t":"fail","tool":"Read","norm":"{\"file_path\":\"<P>/missing.py\"}"}`. Under
        `Bash|Skill` nothing could deliver it, so that was harmless; `mcp__.*` is a pattern
        rather than a name, so "not Bash means Skill" stopped holding and the script now
        says which shapes it keys."""
        for payload in (self.failure(self.READ_INPUT, "s1", tool="Read",
                                     error="Exit code 1\nFile does not exist"),
                        self.success(self.READ_INPUT, "s1", tool="Read"),
                        self.attempt(self.READ_INPUT, "s1", tool="Read")):
            self.tick()
            r = self.run_hook(payload)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, "",
                             "%s spoke about a tool it has no rule for: %r"
                             % (payload["hook_event_name"], r.stdout))
        self.assertEqual(self.rows(), [], self.rows())

    def test_the_shape_test_does_not_reach_the_argv_doors(self):
        """`--norm-of` and `--eligible-of` take the tool name as an ARGUMENT, and their
        callers -- bin/skillrepeat and bin/skillreport -- pass whatever the store recorded.
        The shape test lives inside the payload read, so a stored row naming a tool the
        matcher no longer delivers is still answerable."""
        r = subprocess.run(["bash", HOOK, "--eligible-of", "Read"], input="cat /x",
                           capture_output=True, text=True, env=self.env(), timeout=180)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "exempt-tool")


# ============================================================== the CLI
class CliTest(GateCase):

    def seed(self):
        """Two sessions, one signature, and two DIFFERENT commands that normalise to ONE
        shape -- so the plurality agrees and the CLI has a recovery to print. The pair
        shares `list` and `limit` with the failure, which is what the same-tool rule wants
        since 2026-09-03; see the constants at the top of this file."""
        for s, fix in (("s1", FIX_SEARCH_A), ("s2", FIX_SEARCH_B)):
            self.tick(); self.run_hook(self.failure(FAILING_CMD, s))
            self.tick(); self.run_hook(self.success(fix, s))
        return [r for r in self.rows() if r["t"] == "fail"][0]["sig"]

    def test_list_on_an_empty_store(self):
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("No repeated failures recorded", r.stdout)

    def test_list_and_its_json(self):
        sig = self.seed()
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(sig, r.stdout)
        self.assertIn("refuses", r.stdout)

        r = self.run_cli("list", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["sig"], sig)
        self.assertEqual(got[0]["sessions"], 2)
        self.assertTrue(got[0]["refuses"])
        self.assertIn("--search", got[0]["recovery"])

    # ---------------------------------------------------------------- column layout
    # `list` is a fixed-width table and the header is the ruler. Both tests below assert
    # the SAME thing -- that a row's CALL text begins at the column the header's "CALL"
    # begins at -- because that is what "the table lines up" means, and it is the only
    # assertion that catches an overflow and a shift with one rule.
    def columns(self, out):
        """(header line, [data lines]) with the trailing legend stripped."""
        lines = out.split("\n")
        self.assertTrue(lines and lines[0].startswith("SIGNATURE"),
                        "no table header in: %r" % out)
        data = []
        for ln in lines[1:]:
            if not ln.strip():
                break
            data.append(ln)
        return lines[0], data

    def assert_call_column_aligned(self, out, calls):
        hdr, data = self.columns(out)
        want = hdr.index("CALL")
        self.assertEqual(len(data), len(calls),
                         "expected %d rows, got %r" % (len(calls), data))
        for call in calls:
            row = [ln for ln in data if call in ln]
            self.assertEqual(len(row), 1, "no single row carrying %r in %r" % (call, data))
            self.assertEqual(
                row[0].index(call), want,
                "CALL column starts at %d for %r but the header puts it at %d:\n%s\n%s"
                % (row[0].index(call), call, want, hdr, row[0]))

    def test_the_gate_column_fits_its_widest_value(self):
        """DEFECT: the GATE column was `%-8s` and `transient` is NINE characters, so every
        row the self-recovery rule produces pushed CALL one column right and stopped
        lining up with the header.

        Where CALL begins is not written down here, or anywhere else. It is read off the
        header, which is the only place it lives."""
        # A signature two sessions failed and one of them then re-ran identically: transient.
        self.tick(); self.run_hook(self.failure("curl -s https://x/y", "s1"))
        self.tick(); self.run_hook(self.failure("curl -s https://x/y", "s2"))
        self.tick(); self.run_hook(self.success("curl -s https://x/y", "s2"))
        # ...and one that simply refuses.
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"))
        self.tick(); self.run_hook(self.failure("gh pr list", "s2"))

        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("transient", r.stdout)
        self.assertIn("refuses", r.stdout)
        self.assert_call_column_aligned(r.stdout, ["curl -s https:/<P>", "gh pr list"])

    def test_an_empty_column_does_not_shift_the_ones_after_it(self):
        """This is the test that fails when the `awk -F'\t'` formatter is put back into a
        `while IFS=$'\t' read` loop, and it is why that loop is not coming back.

        Tab is IFS WHITESPACE: `read` collapses runs of it, so ONE empty field silently
        shifts every field after it left by a column -- the same trap that made the pending
        file use US (0x1f). `awk -F'\t'` does not collapse. Measured on the row below: the
        loop starts CALL left of the column the header puts it in and prints the RECOVERY
        value under TOOL; awk starts it where the header does.

        The empty field is a foreign row's, which is exactly the shape this CLI already
        promises to survive (MalformedStoreTest): the gate itself never writes an empty
        tool, so nothing but another writer can produce one."""
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"))
        self.tick(); self.run_hook(self.failure("gh pr list", "s2"))
        with open(self.store, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": "fail", "ts": 5, "sig": "cFxF-eFxF", "ck": "cFxF",
                                 "ec": "?", "tool": "", "norm": "someone-elses-row --x",
                                 "cmd": "someone-elses-row --x", "err": "e",
                                 "session": "q1", "tuid": "t6"}) + "\n")
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_call_column_aligned(r.stdout, ["gh pr list", "someone-elses-row --x"])

    # ------------------------------------------ no width is written down anywhere
    # Two fixed widths in this table were overrun by their own producers, one round apart.
    # The repair was to stop writing widths down: bin/skillrepeat widens every padded
    # column to the widest value it actually holds and prints the header with the same
    # widths. So these helpers pin no number either. They DERIVE the widest value each
    # column's producer can emit and assert only that the header is still the ruler.

    def producer_alternatives(self, marker):
        """The values one closed-set column can hold, read out of bin/skillrepeat's own jq
        instead of restated here. Add an alternative to the CLI and this list grows; if the
        new one is the widest and no row below exercises it, the test fails."""
        with open(CLI, encoding="utf-8") as fh:
            body = fh.read()
        i = body.index(marker)
        return re.findall(r'"([^"]*)"', body[i:body.index("end)", i)])

    def widest_signature(self):
        """The widest signature hooks/repeat-gate.sh can write, derived from its hashof().

        A signature is `c<crc32>x<bytes>-e<crc32>x<bytes>`. The byte counts are whatever
        the gate's own normalisers produce at their own caps, so they are read back off a
        row the REAL gate wrote from saturating input rather than guessed; the CRC-32s are
        widened to the widest a CRC-32 has. Move a cap in the gate and this grows with it.

        Returns (the real signature, the widest one with those byte counts)."""
        self.tick()
        self.run_hook(self.failure(SATURATING_CMD, "w1", error=SATURATING_ERR))
        self.tick()
        self.run_hook(self.failure(SATURATING_CMD, "w2", error=SATURATING_ERR))
        fails = [r for r in self.rows() if r["t"] == "fail"]
        self.assertEqual(len(fails), 2, "the saturating failure was not recorded")
        real = fails[0]["sig"]
        ck_bytes, ec_bytes = real.split("-")[0].split("x")[1], real.split("-")[1].split("x")[1]
        # Non-vacuity for the derivation: the second half's byte count really is the length
        # of the error class the row carries, so `x<bytes>` is what this thinks it is.
        self.assertEqual(ec_bytes, str(len(fails[0]["ec"].encode("utf-8"))),
                         "hashof() no longer prints <crc32>x<bytes>: %r" % real)
        widest = "c%dx%s-e%dx%s" % (2 ** 32 - 1, ck_bytes, 2 ** 32 - 1, ec_bytes)
        self.assertGreaterEqual(len(widest), len(real))
        return real, widest

    def assert_table_lines_up(self):
        """Every rendered row's CALL begins exactly where the header's does.

        Driven off `list --json`, so it needs no knowledge of any column's width: whatever
        the header says, everything from that offset on must be exactly that row's call."""
        txt = self.run_cli("list")
        self.assertEqual(txt.returncode, 0, txt.stderr)
        js = self.run_cli("list", "--json")
        self.assertEqual(js.returncode, 0, js.stderr)
        by_sig = {e["sig"]: e for e in json.loads(js.stdout)}
        hdr, data = self.columns(txt.stdout)
        want = hdr.index("CALL")
        self.assertEqual(len(data), len(by_sig), "rendered %d rows for %d signatures"
                         % (len(data), len(by_sig)))
        for row in data:
            sig = row.split(" ")[0]
            self.assertIn(sig, by_sig, "unrecognised row: %r" % row)
            self.assertEqual(
                row[want:].rstrip(), by_sig[sig]["call"][:60],
                "the header puts CALL at %d; row %r does not start its call there:\n%s\n%s"
                % (want, sig, hdr, row))
        return hdr, data

    def test_no_column_can_overflow_its_header(self):
        """DEFECT: SIGNATURE was `%-30s` and the gate writes THIRTY-ONE character
        signatures from ordinary input, so CALL shifted one column right of its header.
        That is the second fixed width in this table overrun by its own producer; GATE at
        `%-8s` against `transient` was the first, one round earlier.

        So this test pins no width, for any column. It derives the widest value each
        producer can emit, puts all five in one store at once, and asserts only that the
        table still lines up. A third instance would have to get past a derivation rather
        than past a number somebody forgot to update.

        Three of the five producers have no bound even in principle -- SIGNATURE and TOOL
        are read off a store any writer may append to, and SESS counts distinct sessions,
        capped only by REPEAT_GATE_MAX_BYTES. The extremes for those arrive as foreign
        rows, which is the shape this CLI already promises to survive; what is under test
        here is the formatter, not the gate."""
        real_sig, widest_sig = self.widest_signature()
        self.assertGreater(len(real_sig), len("SIGNATURE"),
                           "the gate's own signature no longer stretches this column")

        # GATE = transient (a self-recovery) and RECOVERY = disputed (two sessions, two
        # different commands afterwards), both from the real gate.
        self.tick(); self.run_hook(self.failure("curl -s https://x/y", "t1"))
        self.tick(); self.run_hook(self.failure("curl -s https://x/y", "t2"))
        self.tick(); self.run_hook(self.success("curl -s https://x/y", "t2"))
        # Two sessions, two DIFFERENT shapes, both genuinely related to the failure --
        # which the same-tool rule requires since 2026-09-03 and which is what makes this
        # signature `disputed` rather than simply unrecovered.
        for sess, fix in (("d1", "gh pr view 1 --json title,url"),
                          ("d2", "gh pr view 1 --json body")):
            self.tick(); self.run_hook(self.failure("gh pr view 1 --json title", sess))
            self.tick(); self.run_hook(self.success(fix, sess))

        # TOOL and SIGNATURE at their widest, and SESS wider than its header: 10000
        # distinct sessions on one signature, which a store at the gate's byte cap holds.
        long_tool = "mcp__github_enterprise_server__pull_request_review_comment"
        sess_count = 10000
        with open(self.store, "a", encoding="utf-8") as fh:
            for i, sess in enumerate(("q1", "q2")):
                fh.write(json.dumps(
                    {"t": "fail", "ts": 5 + i, "sig": widest_sig, "ck": "cWx1", "ec": "?",
                     "tool": long_tool, "norm": "widest --row", "cmd": "widest --row",
                     "err": "e", "session": sess, "tuid": "tw%d" % i}) + "\n")
            for i in range(sess_count):
                fh.write(json.dumps(
                    {"t": "fail", "ts": 6, "sig": "cSxS-eSxS", "ck": "cSxS", "ec": "?",
                     "tool": "Bash", "norm": "many --sessions", "cmd": "many --sessions",
                     "err": "e", "session": "many%d" % i, "tuid": "tm%d" % i}) + "\n")
            # LESSON at ITS widest, `dismissed`, which needs a dismiss row for a signature
            # already in the table. Appended rather than run through the CLI because the
            # signature is one this test synthesised in the first place.
            fh.write(json.dumps({"t": "dismiss", "ts": 7, "sig": widest_sig,
                                 "session": "cli", "why": "known"}) + "\n")
        self.assertGreater(len(long_tool), len("TOOL"))
        self.assertGreater(len(str(sess_count)), len("SESS"))

        hdr, data = self.assert_table_lines_up()

        # ...and each extreme really is in the table, so the alignment above is not vacuous.
        flat = "\n".join(data)
        self.assertIn(real_sig, flat)
        self.assertIn(widest_sig, flat)
        self.assertIn(long_tool, flat)
        self.assertIn(str(sess_count), flat)
        for label, marker in (("RECOVERY", "(if .recovery"),
                              ("GATE", "(if .transient_sessions"),
                              ("LESSON", "(if .lesson_dismissed")):
            alts = self.producer_alternatives(marker)
            self.assertTrue(alts, "no alternatives found for %s" % label)
            widest = max(alts, key=len)
            self.assertTrue(any(widest in ln.split() for ln in data),
                            "%s's widest value %r is not exercised by any row here, so "
                            "nothing proves the column fits it: %r" % (label, widest, alts))

    def test_list_filtered_by_tool(self):
        self.seed()
        self.assertIn("gh pr list", self.run_cli("list", "--tool", "Bash").stdout)
        r = self.run_cli("list", "--tool", "Read")
        self.assertIn("No repeated failures recorded", r.stdout)

    def test_show_prints_every_row_verbatim(self):
        sig = self.seed()
        r = self.run_cli("show", sig)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gh: command not found", r.stdout)
        self.assertIn(FIX_SEARCH_A, r.stdout)
        self.assertIn(FIX_SEARCH_B, r.stdout)

    def test_show_json(self):
        sig = self.seed()
        got = json.loads(self.run_cli("show", sig, "--json").stdout)
        self.assertEqual(len(got), 4)
        self.assertEqual({r["t"] for r in got}, {"fail", "recover"})

    def test_show_an_unknown_signature(self):
        r = self.run_cli("show", "c1x1-e1x1")
        self.assertEqual(r.returncode, 3)
        self.assertIn("no rows", r.stderr)

    def test_stats(self):
        self.seed()
        r = self.run_cli("stats")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 failures", r.stdout)
        got = json.loads(self.run_cli("stats", "--json").stdout)
        self.assertEqual(got["failures"], 2)
        self.assertEqual(got["recoveries"], 2)
        self.assertEqual(got["signatures"], 1)
        self.assertEqual(got["refusing"], 1)
        self.assertEqual(got["with_recovery"], 1)

    def test_forget_appends_a_tombstone_and_deletes_nothing(self):
        sig = self.seed()
        before = len(self.rows())
        r = self.run_cli("forget", sig, "--why", "installed gh",
                         SKILLREPEAT_NOW=self.tick(100))
        self.assertEqual(r.returncode, 0, r.stderr)
        after = self.rows()
        self.assertEqual(len(after), before + 1)
        self.assertEqual(after[-1]["t"], "forget")
        self.assertEqual(after[-1]["why"], "installed gh")
        # every original row is still there, byte for byte
        self.assertEqual(after[:before], self.rows()[:before])
        self.assertIn(sig, self.run_cli("show", sig).stdout)

    def test_a_tombstone_suppresses_the_deny(self):
        sig = self.seed()
        self.tick()
        self.assert_denied(self.run_hook(self.attempt(FAILING_CMD, "s8")))
        self.run_cli("forget", sig, SKILLREPEAT_NOW=self.tick(100))
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt(FAILING_CMD, "s9")))
        self.assertNotIn("refuses", self.run_cli("list").stdout)

    def test_forgetting_is_re_armable(self):
        """`stop telling me` is a statement about today. Two fresh sessions after the
        tombstone and the refusal comes back, which is what makes append-only honest
        rather than merely conservative."""
        sig = self.seed()
        self.run_cli("forget", sig, SKILLREPEAT_NOW=self.tick(100))
        self.teach("gh pr list", ["s5", "s6"])
        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list", "s9")))

    def test_forgetting_an_unknown_signature_refuses(self):
        """A mistyped signature that silently appended a matching-nothing tombstone would
        look exactly like a successful forget, and the gate would go on refusing."""
        self.seed()
        before = len(self.rows())
        r = self.run_cli("forget", "c9x9-e9x9")
        self.assertEqual(r.returncode, 3)
        self.assertIn("nothing to forget", r.stderr)
        self.assertEqual(len(self.rows()), before)

    def test_usage_and_unknown_subcommands(self):
        self.assertEqual(self.run_cli("--help").returncode, 0)
        self.assertIn("skillrepeat list", self.run_cli("--help").stdout)
        r = self.run_cli("wat")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown subcommand", r.stderr)
        self.assertEqual(self.run_cli("show").returncode, 2)
        self.assertEqual(self.run_cli("forget").returncode, 2)
        self.assertEqual(self.run_cli("list", "--nope").returncode, 2)

    def test_the_cli_and_the_gate_agree_on_what_refuses(self):
        """A CLI that reports a different set from the one the gate acts on is worse than
        no CLI. Checked at the threshold boundary, in both directions."""
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"))
        got = json.loads(self.run_cli("list", "--json").stdout)
        self.assertFalse(got[0]["refuses"])
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "s3")))

        self.tick(); self.run_hook(self.failure("gh pr list", "s2"))
        got = json.loads(self.run_cli("list", "--json").stdout)
        self.assertTrue(got[0]["refuses"])
        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list", "s3")))


# ============================================================== cost
class CostTest(GateCase):
    """A PreToolUse hook runs before EVERY tool call, so its cost is paid hundreds of times
    a session and a slow one is a tax on all of it. The store is bounded by
    REPEAT_GATE_MAX_BYTES precisely so this cost cannot grow with the user's history; this
    measures what the cap actually buys and prints it, so the figure in the script's header
    is one that was printed rather than guessed.

    IT IS MEASURED IN TWO SHAPES, and the second is the one the header quotes. A store whose
    rows all share ONE signature is the BEST case for the gate's `.ck==$ck` filter: every
    row survives it and then one group is built. A store of DISTINCT signatures is the worst
    case: the filter drops nearly everything, but the whole file is still parsed. Quoting
    only the first would understate the real figure severalfold."""

    ROW = {"t": "fail", "ts": 1, "sig": "cAxA-eBxB", "ck": "cAxA",
           "ec": "Exit code <N> gh: command not found", "tool": "Bash",
           "norm": "gh pr list --limit <N>", "cmd": "gh pr list",
           "err": GH_ERR, "session": "s0", "tuid": "t"}

    def fill(self, distinct):
        """Write a store just under REPEAT_GATE_MAX_BYTES, with `distinct` signatures.

        Just UNDER, deliberately: one byte over the cap and the gate fails open without
        reading anything, which would measure the guard rather than the query."""
        os.makedirs(os.path.dirname(self.store), exist_ok=True)
        target = 4 * 1024 * 1024 - 4096
        n = 0
        with open(self.store, "w", encoding="utf-8") as fh:
            while fh.tell() < target:
                k = n % distinct
                row = dict(self.ROW, sig="cA%dxA-eBxB" % k, ck="cA%dxA" % k,
                           norm="gh pr list --limit <N> %d" % k,
                           session="s%d" % (n % 50))
                fh.write(json.dumps(row) + "\n")
                n += 1
        size = os.path.getsize(self.store)
        self.assertGreater(size, target * 0.9)
        # The ACTUAL diversity, not the requested one. `distinct` is an upper bound: the
        # store holds `n` rows, so asking for 100000 signatures in 15831 rows gets 15831,
        # and printing the request would report a number the file does not contain.
        return n, size, min(n, distinct)

    def time_hook(self, label, distinct):
        n, size, distinct = self.fill(distinct)
        self.tick()
        t0 = time.time()
        r = self.run_hook(self.attempt("gh pr list --limit 5", "s999"))
        elapsed = time.time() - t0
        print("\n[cost] gate/%s: %d rows, %d distinct signatures, %d bytes, "
              "whole-hook wall time %.2fs" % (label, n, distinct, size, elapsed))
        self.assertEqual(r.returncode, 0, r.stderr)
        # A hook is wired with a 10s timeout. Being killed there is silent, so the cap has
        # to leave real headroom rather than merely fit.
        self.assertLess(elapsed, 5.0,
                        "a store at REPEAT_GATE_MAX_BYTES took %.2fs" % elapsed)
        return elapsed

    def test_a_store_at_the_cap_of_one_signature_is_the_best_case(self):
        self.time_hook("one signature", 1)

    def test_a_store_at_the_cap_of_distinct_signatures_is_the_figure_to_quote(self):
        self.time_hook("distinct signatures", 100000)

    def test_the_lesson_gate_on_its_expensive_path(self):
        """THE LESSON GATE SHIPS ON, so its cost is the one every user pays. There are two
        figures and only one of them is common.

        The CHEAP path is what the two tests above already measure: with no recovery bound
        in the session there is no `lessons/<sid>` directory and the arm leaves on one
        `[ -d ]`, which is why their figures did not move when it landed.

        This is the OTHER path -- a session that HAS bound a recovery -- and it parses the
        store and the ledger on top of everything else. It is bounded per signature per
        session rather than per tool call, because the marker is removed as soon as the
        signature is judged unable to qualify; this measures one of those few, at the
        store's byte cap, which is the worst case there is."""
        n, size, distinct = self.fill(100000)
        # A real failure and a real success, so the marker is written by the real arm --
        # and a RAISED CAP for those two calls only. The learn arm rotates the store at
        # HALF the read budget, so a failure recorded at the default cap archives the
        # 4 MB file this test just built and leaves a two-row one behind. Measured: that
        # is what a first draft of this test did, and it reported 0.08s for a query that
        # never saw the store. The PreToolUse below runs at the ordinary cap.
        big = 8 * 4194304
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s999"),
                                   REPEAT_GATE_MAX_BYTES=big)
        self.tick(); self.run_hook(self.success(FIX_CMD, "s999"),
                                   REPEAT_GATE_MAX_BYTES=big)
        self.assertGreater(os.path.getsize(self.store), size,
                           "the store was rotated out from under the measurement")
        marker = os.path.join(self.state, "repeats", "lessons", "s999")
        self.assertTrue(os.path.isdir(marker), "no lesson marker to measure against")
        with open(os.path.join(self.state, "ledger.jsonl"), "w", encoding="utf-8") as fh:
            for i in range(2000):
                fh.write(json.dumps({"event": "note", "ts": i, "id": "n%d" % i,
                                     "text": "x" * 120}) + "\n")
        self.tick()
        t0 = time.time()
        r = self.run_hook(self.attempt("npm install left-pad", "s999"),
                          REPEAT_GATE_REFUSE=None)
        elapsed = time.time() - t0
        print("\n[cost] lesson gate/expensive path: %d rows, %d distinct signatures, "
              "%d bytes + a %d-byte ledger, whole-hook wall time %.2fs"
              % (n, distinct, size, os.path.getsize(
                  os.path.join(self.state, "ledger.jsonl")), elapsed))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(elapsed, 5.0,
                        "the lesson gate took %.2fs at the store's cap" % elapsed)
        # NON-VACUITY: it really did the work -- the marker is gone, which only the arm
        # that read the store can do.
        self.assertEqual([f for f in os.listdir(marker) if f.startswith("s-")], [])


class CliCostTest(CostTest):
    """DEFECT: the only tool for inspecting and trimming the store died at the size the
    gate permits. The summary query selected `.t=="fail"` over the WHOLE store and then
    rescanned every row once per distinct signature -- O(signatures x rows). The gate stays
    flat only because it filters `.ck==$ck` and `.session!=$sid` FIRST, which the CLI cannot
    do and must not pretend to.

    Measured before the fix, at the gate's own cap with every signature distinct: `list`
    and `stats` were both still running after 120s and had to be killed, against 0.31s for
    the gate on the identical store. Scaling was 4x per doubling of the signature count.

    The bound below is generous on purpose -- this is a human-facing CLI, not a hook, and
    what it has to rule out is the quadratic, not a tenth of a second. The measurement is
    PRINTED on every run so the header's figure cannot quietly stop being true."""

    LIMIT = 10.0

    def time_cli(self, sub, distinct):
        n, size, distinct = self.fill(distinct)
        t0 = time.time()
        try:
            r = self.run_cli(sub, timeout=180)
        except subprocess.TimeoutExpired:
            self.fail("skillrepeat %s did not finish in 180s on a store of %d rows / %d "
                      "distinct signatures -- the quadratic is back" % (sub, n, distinct))
        elapsed = time.time() - t0
        print("\n[cost] skillrepeat %s: %d rows, %d distinct signatures, %d bytes, "
              "wall time %.2fs" % (sub, n, distinct, size, elapsed))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(elapsed, self.LIMIT,
                        "skillrepeat %s took %.2fs on a store at the cap" % (sub, elapsed))
        return r, elapsed

    def test_stats_at_the_cap_with_every_signature_distinct(self):
        r, _ = self.time_cli("stats", 100000)
        self.assertIn("signatures:", r.stdout)

    def test_list_at_the_cap_with_every_signature_distinct(self):
        r, _ = self.time_cli("list", 100000)
        self.assertIn("SIGNATURE", r.stdout)

    def test_stats_at_the_cap_with_one_signature(self):
        self.time_cli("stats", 1)


# ================================================== the claim taken before the emit
class DenyEmitFailureTest(GateCase):
    """The deny arm claims `denied/<session>/<sig>` BEFORE it emits, so an emit that
    dies silences that signature for the whole session with nothing on any surface.

    A cold reviewer raised this as a latent inconsistency with `hooks/apply-gate.sh`,
    whose header argues EMIT, AND ONLY THEN CLAIM at length, and judged it unreachable
    here because the reason is bounded (norm <= 400, err <= 400, cmd <= 500) so E2BIG
    cannot be reached through the message. That is true of the message and beside the
    point: `jq -n --arg r` is an exec, and **the environment counts against the same
    ARG_MAX as the argument vector**, which no cap in this file has any say over. Same
    route `tests/test_apply_gate.py::EmitFailureTest` takes, for the same reason.

    IT IS ONLY REACHABLE WITH THE REASON NEAR ITS CAP, and that is worth stating because
    it is why a first attempt at this test proved nothing. The largest exec on the deny
    path before the emit is the store query, whose jq program is about 1.3 KB; a typical
    deny reason is smaller (895 bytes measured for `gh pr list --state open --limit 20`),
    so E2BIG reaches the QUERY first, the hook fails open, and no claim is ever taken.
    The scenario below therefore drives the reason to its cap -- a command past the
    400-character normalisation cap, a long error, and a recorded recovery -- which
    measures 2096 bytes and puts the emit back on the far side of the query.

    THE ORDERING IS NOT SIMPLY INVERTED HERE, and that is the difference from the
    sibling. This arm's claim is deliberately fail-CLOSED: it serialises the duplicate
    delivery both wirings produce, and two refusals racing out for one call is worse
    than one missed. So the claim stays where it is and is RELEASED on every path that
    exits without emitting -- which buys the same property the sibling's ordering does
    (the next attempt tries again instead of the signature being gone for the session)
    without giving up the race.

    NOTHING IS MOCKED: a real environment, a real exec, real files. The window is
    CALIBRATED at run time because ARG_MAX is per-platform, and by BINARY SEARCH rather
    than the sibling's linear walk because the gap to straddle here is under a kilobyte.
    """

    UNIT = 200                      # bytes per padding variable: the search granularity
    SMALL = 1500                    # > the store query's argv; these execs must still work
    BIG = 2300                      # > the capped deny reason this scenario builds
    MAX_UNITS = 100000              # 20 MB of padding before giving up
    WINDOW = 40                     # UNITs either side of the proxy's answer to search

    _probes = 0

    def _pad_env(self, units, **extra):
        e = self.env(**extra)
        for i in range(units):
            e["REPEAT_GATE_TEST_PAD%05d" % i] = "x" * self.UNIT
        return e

    def _execs(self, units, argsize):
        """Can jq be exec'd with this much environment and an argument this size?"""
        try:
            r = subprocess.run(["jq", "-n", "--arg", "r", "R" * argsize, "$r|length"],
                               capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, env=self._pad_env(units))
            return r.returncode == 0
        except OSError:
            return False            # E2BIG surfaces here, before jq is ever entered

    def _calibrate(self):
        """The largest padding at which a SMALL exec still works, by binary search.

        A STARTING POINT, NOT THE ANSWER. `jq -n --arg r <1500 bytes>` is a proxy for
        the exec that actually has to survive -- the store query at
        hooks/repeat-gate.sh:993, ~1336 bytes of jq program plus its own argv -- and a
        proxy is not the thing. Linux charges every string in argv AND environ
        separately against ARG_MAX, so a padding calibrated on a single 1500-byte
        argument does not guarantee the query survives it: on ubuntu the query died
        first, the hook failed open, and the assertion below reported "never reached
        the deny arm; this test proved nothing". `_padding_that_silences_a_real_deny`
        walks out from this answer and MEASURES the hook instead of trusting it.
        """
        if not self._execs(0, self.SMALL):
            self.skipTest("a %d-byte exec fails with no padding at all" % self.SMALL)
        if self._execs(self.MAX_UNITS, self.SMALL):
            self.skipTest("no environment size below %d bytes separates a %d-byte exec "
                          "from a %d-byte one on this platform"
                          % (self.MAX_UNITS * self.UNIT, self.SMALL, self.BIG))
        lo, hi = 0, self.MAX_UNITS          # SMALL works at lo, fails at hi
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self._execs(mid, self.SMALL):
                lo = mid
            else:
                hi = mid
        if self._execs(lo, self.BIG):
            self.skipTest("could not straddle ARG_MAX: a %d-byte exec still succeeds at "
                          "the largest padding a %d-byte one survives"
                          % (self.BIG, self.SMALL))
        return lo

    # A command past the 400-character cap, a long error, and a recovery to quote: the
    # three inputs that put the reason near its ceiling. Measured together: 2096 bytes.
    LONG_CMD = "gh pr list --state open --search " + ("verylongtoken" * 40)
    LONG_ERR = "Exit code 1\n" + ("a failure message that goes on and on " * 20)
    FIX_CMD = "curl -sS https://api.github.com/repos/" + ("x" * 450)

    def _teach_a_big_refusal(self):
        for s in ("s1", "s2"):
            self.tick()
            self.run_hook(self.failure(self.LONG_CMD, s, error=self.LONG_ERR))
            self.tick()
            self.run_hook(self.success(self.FIX_CMD, s))
        self.tick()

    def _probe_sid(self):
        """A throwaway session id EXACTLY as long as the real one below.

        Two characters, like `s3`, because the session id is passed to the store query
        as `--arg sid` and therefore counts against the very limit being straddled. A
        probe id of a different length would size a slightly different exec from the one
        the assertions then run, and the window here is under a kilobyte wide.
        """
        n = self._probes
        self._probes += 1
        sid = chr(ord("a") + n // 10) + str(n % 10)      # a0..e9, never s1/s2/s3
        return sid

    def _probe_the_real_hook(self, units):
        """Deliver this scenario's attempt at this padding and report WHICH of the three
        things happened, measured off the hook itself:

          `emitted`      the deny reached stdout -- not enough padding, the emit lived
          `denied`       the deny arm ran and the emit died -- what this test needs
          `noisy`        an exec died and BASH announced it -- too much padding
          `failed-open`  an exec before the deny arm died quietly -- too much padding
          `unlaunchable` execve refused the hook itself -- far too much padding

        `noisy` is a band this walk found rather than predicted, and it is why the
        classification here does not assert. Just under the padding at which the hook
        cannot be launched at all there is a band where it launches and the sed stages
        of `norm_bash` cannot: each carries a regex program on its argv that `jq`'s
        30-byte argv does not, so `execve` refuses them first and bash writes
        `/usr/bin/sed: Argument list too long` to the hook's stderr, up to seven lines
        per call. Measured at 891800-891960 bytes of environment, one UNIT under the
        launch ceiling. The hook now closes its stderr with a builtin `exec` before its
        first exec, so this outcome is not expected to occur again; it is kept because
        a walk that could no longer name it would silently fold it into `failed-open`,
        and `ExecNoiseTest` below is where the silence is asserted, with the redirect
        switched off on one run to prove there is still something to silence. A padding
        in that band is useless to this test whatever else it does, so it is CLASSIFIED
        and stepped over -- the silence-on-stderr claim is asserted where it belongs, on
        the one run the walk selects, below. The exit status is asserted at every
        padding instead: no environment size excuses a hook breaking the turn, and
        none did.
        """
        self.tick()
        sid = self._probe_sid()
        try:
            r = subprocess.run(["bash", HOOK],
                               input=json.dumps(self.attempt(self.LONG_CMD, sid)),
                               capture_output=True, text=True, timeout=180,
                               env=self._pad_env(units, REPEAT_GATE_NOW=str(self.clock)))
        except OSError:
            return "unlaunchable"
        self.assertEqual(r.returncode, 0, "the hook exited %d at %d bytes of padding"
                                          % (r.returncode, units * self.UNIT))
        if r.stderr:
            return "noisy"
        if r.stdout.strip():
            return "emitted"
        if os.path.isdir(os.path.join(self.state, "repeats", "denied", sid)):
            return "denied"
        return "failed-open"

    def _padding_that_silences_a_real_deny(self):
        """The padding this test needs: past what the emit survives, short of what the
        store query before it survives. Found by walking OUT from the proxy's answer, a
        UNIT at a time, until the hook is OBSERVED reaching the deny arm and losing the
        emit -- and skipped, with the outcomes measured, if no padding does both.

        Both directions, not just down. The proxy calibrates on 1500 bytes; the query is
        ~1490 and the emit ~2150, so the proxy's answer can land on either side of the
        window depending on how a platform accounts for the environment, and a one-way
        walk would be right about one platform by construction.
        """
        start = self._calibrate()
        order = [start]
        for d in range(1, self.WINDOW + 1):
            order += [start - d, start + d]
        bands = {}
        for units in order:
            if units < 0:
                continue
            outcome = self._probe_the_real_hook(units)
            lo, hi, n = bands.get(outcome, (units, units, 0))
            bands[outcome] = (min(lo, units), max(hi, units), n + 1)
            if outcome == "denied":
                return units
        self.skipTest(
            "no environment size straddles the store query and the emit on this "
            "platform: the proxy calibrated at %d units (%d bytes), and every padding "
            "within %d bytes of it fell in a band that cannot show this -- %s"
            % (start, start * self.UNIT, self.WINDOW * self.UNIT,
               ", ".join("%s at %d-%d bytes (%d probes)"
                         % (k, lo * self.UNIT, hi * self.UNIT, n)
                         for k, (lo, hi, n) in sorted(bands.items()))))

    def test_the_scenario_really_does_refuse_and_the_reason_is_near_its_cap(self):
        """Non-vacuity for the test below, which asserts on SILENCE. Without this, a
        scenario that simply never refused would satisfy it."""
        self._teach_a_big_refusal()
        reason = self.assert_denied(self.run_hook(self.attempt(self.LONG_CMD, "s3")))
        self.assertGreater(len(reason.encode()), 1500,
                           "the reason is not near its cap, so this scenario cannot put "
                           "the emit on the far side of the store query")

    def test_a_deny_that_could_not_be_emitted_does_not_burn_the_claim(self):
        # TEACHING FIRST, because the calibration below now runs the real hook and a
        # hook with nothing to refuse cannot show whether it reached the deny arm.
        self._teach_a_big_refusal()
        units = self._padding_that_silences_a_real_deny()
        self.tick()

        r = subprocess.run(["bash", HOOK],
                           input=json.dumps(self.attempt(self.LONG_CMD, "s3")),
                           capture_output=True, text=True, timeout=180,
                           env=self._pad_env(units, REPEAT_GATE_NOW=str(self.clock)))
        # A hook may never break a turn and may never speak on stderr, whatever fails.
        self.assertEqual(r.returncode, 0, "the hook exited %d" % r.returncode)
        self.assertEqual(r.stderr, "", "the hook wrote to stderr: %r" % r.stderr)
        self.assertEqual(r.stdout, "",
                         "the emit was expected to fail in this environment, got %r"
                         % r.stdout)

        # THE HOOK REALLY DID REACH THE DENY ARM. Without this the test would also pass
        # if the hook had failed open at the store query and proved nothing: the session
        # directory is created on the line above the claim.
        denied = os.path.join(self.state, "repeats", "denied", "s3")
        self.assertTrue(os.path.isdir(denied),
                        "the hook never reached the deny arm; this test proved nothing")

        # And the claim it could not honour is not still standing.
        left = os.listdir(denied)
        self.assertEqual(left, [],
                         "a claim was burnt for a refusal nobody ever saw: %s" % left)

        # The consequence that matters: the next attempt in the SAME session refuses.
        self.tick()
        self.assert_denied(self.run_hook(self.attempt(self.LONG_CMD, "s3")))


# ============================================ the band where the normaliser cannot exec
class ExecNoiseTest(GateCase):
    """A hook may never speak on stderr, and for one band of environment size this one
    did. `execve` charges the environment against ARG_MAX along with the argument vector,
    so just under the padding at which `bash hooks/repeat-gate.sh` cannot be launched at
    all there is a band where it launches, `jq` execs on its 30-byte argv, and every
    `sed` in the normaliser -- each carrying a 100-250-byte regex program -- cannot. bash
    then wrote `line NNN: /usr/bin/sed: Argument list too long` for each of them, up to
    seven lines per tool call, to a terminal the hook is wired to leave alone. Exit
    status was 0 throughout and the store query ahead of any deny had already failed
    open, so nothing broke and nothing was lost except the silence.

    The hook now closes fd 2 with a builtin `exec` before its first exec, unless
    `REPEAT_GATE_STDERR=1`. These tests find the band on the platform they run on and
    drive the real hook through it twice at an IDENTICAL environment size -- the knob is
    `0` on one run and `1` on the other, one byte either way -- so the run with the
    redirect off has to show the noise the default run is asserted not to. Without that
    second run a hook that had never been noisy would pass the first assertion, and a
    redirect nobody has seen do anything is the kind of guard this package exists to
    catch.

    The second test is the reason no command-length cap was added instead: the command
    reaches `sed` through a pipe from a builtin `printf` and is never on an argv, so a
    twelve-byte command dies in the same band as a six-hundred-byte one. What is on the
    argv is the regex, which is the normaliser itself.

    Padding here is in BYTES, not the parent's 200-byte units: the band is about as wide
    as one unit, so a unit walk can step over it. The search starts from the largest
    padding the hook can be launched with at all, found by binary search on `OSError`,
    and walks down from there.
    """

    # Borrowed from the sibling rather than inherited: inheriting its test methods
    # would run its calibration a second time under this name.
    UNIT = DenyEmitFailureTest.UNIT
    LONG_CMD = DenyEmitFailureTest.LONG_CMD
    LONG_ERR = DenyEmitFailureTest.LONG_ERR
    FIX_CMD = DenyEmitFailureTest.FIX_CMD
    _probes = 0
    _teach_a_big_refusal = DenyEmitFailureTest._teach_a_big_refusal
    _probe_sid = DenyEmitFailureTest._probe_sid

    STEP = 20                       # bytes between probes; the band is ~200 wide
    REACH = 1200                    # bytes below the launch ceiling to search
    SHORT_CMD = "gh pr view 7"      # not allowlisted, and 12 bytes long

    def _pad_bytes(self, total, **extra):
        e = self.env(**extra)
        i = 0
        while total > 0:
            n = min(self.UNIT, total)
            e["REPEAT_GATE_TEST_PAD%05d" % i] = "x" * n
            total -= n
            i += 1
        return e

    def _run(self, total, cmd, stderr_knob):
        """One real delivery at `total` bytes of padding; None if execve refused the
        hook itself."""
        self.tick()
        sid = self._probe_sid()
        try:
            return subprocess.run(
                ["bash", HOOK], input=json.dumps(self.attempt(cmd, sid)),
                capture_output=True, text=True, timeout=180,
                env=self._pad_bytes(total, REPEAT_GATE_NOW=str(self.clock),
                                    REPEAT_GATE_STDERR=stderr_knob))
        except OSError:
            return None

    def _launch_ceiling(self):
        """The largest padding at which the hook can be launched at all."""
        lo, hi = 0, 4_000_000
        if self._run(lo, self.LONG_CMD, "1") is None:
            self.skipTest("the hook cannot be launched with no padding at all")
        while self._run(hi, self.LONG_CMD, "1") is not None:
            hi *= 2
            if hi > 64_000_000:
                self.skipTest("no environment size below 64 MB stops the hook launching")
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self._run(mid, self.LONG_CMD, "1") is not None:
                lo = mid
            else:
                hi = mid
        return lo

    def _noisy_padding(self, cmd, stage):
        """A padding at which the hook, with its redirect switched OFF, is observed
        writing E2BIG noise naming `stage` for this command. Measured, never assumed;
        and skipped with the measurement if this platform's accounting has no such band.

        There are two bands, not one, and `stage` picks between them. At the launch
        ceiling itself the FIRST exec, the `cat` that reads the payload, is the one that
        cannot start, so bash prints `/bin/cat: Argument list too long` and the hook
        exits 0 with an empty payload. Below that, `cat` and `jq` fit and the `sed`
        stages do not. Both were silenced by the same redirect; the sibling test needs
        the `sed` band, because its claim is about what happens AFTER the command has
        been read."""
        ceiling = self._launch_ceiling()
        seen = {}
        for total in range(ceiling, max(ceiling - self.REACH, 0) - 1, -self.STEP):
            r = self._run(total, cmd, "1")
            self.assertIsNotNone(r, "the hook launched at %d bytes and not at %d"
                                    % (ceiling, total))
            self.assertEqual(r.returncode, 0,
                             "the hook exited %d at %d bytes of padding with its "
                             "stderr connected" % (r.returncode, total))
            if "Argument list too long" in r.stderr and stage in r.stderr:
                return total, r
            seen[total] = r.stderr.strip().split("\n")[-1][-40:]
        self.skipTest("no padding within %d bytes under the launch ceiling (%d bytes) "
                      "made a %s exec inside the hook die E2BIG on this platform; last "
                      "stderr line seen at each: %s"
                      % (self.REACH, ceiling, stage, sorted(seen.items())))

    def test_the_band_where_the_normaliser_cannot_exec_is_silent_by_default(self):
        self._teach_a_big_refusal()
        total, loud = self._noisy_padding(self.LONG_CMD, "Argument list too long")
        # The run that proves the default is doing something: redirect off, noise on.
        self.assertIn(HOOK, loud.stderr,
                      "the noise at %d bytes did not come from inside the hook: %r"
                      % (total, loud.stderr))
        self.assertEqual(loud.stdout, "", "a deny was emitted from inside the band")

        r = self._run(total, self.LONG_CMD, "0")
        self.assertIsNotNone(r, "the hook launched at %d bytes with the knob on and "
                                "not with it off, at the same environment size" % total)
        self.assertEqual(r.returncode, 0, "the hook exited %d" % r.returncode)
        self.assertEqual(r.stderr, "", "the hook wrote to stderr at %d bytes of "
                                       "padding: %r" % (total, r.stderr))
        # And nothing it would have printed is lost: in this band the store query ahead
        # of any deny cannot exec either, so the hook had nothing to say on stdout.
        self.assertEqual(r.stdout, "", "a deny was emitted from inside the band: %r"
                                       % r.stdout)

    def test_a_short_command_dies_in_the_same_band_so_no_cap_could_have_fixed_it(self):
        self._teach_a_big_refusal()
        total, loud = self._noisy_padding(self.SHORT_CMD, "sed")
        self.assertIn("sed: Argument list too long", loud.stderr)
        r = self._run(total, self.SHORT_CMD, "0")
        self.assertIsNotNone(r)
        self.assertEqual(r.returncode, 0, "the hook exited %d" % r.returncode)
        self.assertEqual(r.stderr, "", "the hook wrote to stderr for a %d-byte command "
                                       "at %d bytes of padding: %r"
                                       % (len(self.SHORT_CMD), total, r.stderr))

    def test_the_redirect_costs_nothing_where_the_deny_is_emitted(self):
        """Below the band the hook still refuses, and identically with the knob either
        way: the redirect moves fd 2 and touches nothing else."""
        self._teach_a_big_refusal()
        self.tick()
        off = self.run_hook(self.attempt(self.LONG_CMD, "s3"), REPEAT_GATE_STDERR="0")
        self.tick()
        on = self.run_hook(self.attempt(self.LONG_CMD, "s4"), REPEAT_GATE_STDERR="1")
        for r in (off, on):
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stderr, "")
        self.assertEqual(self.assert_denied(off), self.assert_denied(on))


# ====================================================== the refuse arm's shipped default
class RefuseArmDefaultTest(GateCase):
    """ISSUE #27. The refuse arm had never refused anything in 81 real sessions -- there
    was no `repeats/denied/` directory on the machine at all -- and the ten signatures
    that had reached the threshold were every one of them exempt by their head, so the
    population that could ever trigger it was empty. It is now off unless
    `REPEAT_GATE_REFUSE=1`.

    What must survive the change: the LEARN arm, the RECOVER arm, and both read-only
    argv doors. Turning off a refusal nobody has ever seen is a small claim; turning off
    the store that four other components read would be a large one, and these assert the
    difference rather than trusting the placement of one `if`."""

    def seed_a_refusable_signature(self):
        """Two distinct earlier sessions of a call the gate does NOT exempt."""
        self.teach("gh pr list --limit 5", ["s1", "s2"])

    def test_the_default_denies_nothing(self):
        self.seed_a_refusable_signature()
        self.tick()
        r = self.run_hook(self.attempt("gh pr list --limit 5", "s3"),
                          REPEAT_GATE_REFUSE=None)
        self.assert_allowed(r)
        # AND NOTHING WAS CLAIMED. The deny marker is written one line above the emit, so
        # a gate that refused and failed to speak would still leave this behind -- which
        # would silence the signature for the rest of the session with nothing on any
        # surface. Its absence is what says the arm did not run at all.
        self.assertFalse(os.path.exists(os.path.join(self.state, "repeats", "denied")),
                         "the default wrote a deny marker for a refusal it never made")

    def test_the_same_store_still_denies_with_the_knob_on(self):
        """NON-VACUITY for the test above: the store really does hold a refusable
        signature, so the silence there is the knob and not an empty store."""
        self.seed_a_refusable_signature()
        self.tick()
        self.assert_denied(self.run_hook(self.attempt("gh pr list --limit 5", "s3")))
        self.assertTrue(os.path.isdir(os.path.join(self.state, "repeats", "denied", "s3")))

    def test_only_the_literal_1_switches_it_on(self):
        """A knob whose ON state can block a call the session is waiting on must not be
        switched on by a typo. `true`, `yes` and `0` are all off."""
        self.seed_a_refusable_signature()
        for value in ("0", "true", "yes", "", "01", " 1"):
            self.tick()
            self.assert_allowed(
                self.run_hook(self.attempt("gh pr list --limit 5", "s%s" % len(value)),
                              REPEAT_GATE_REFUSE=value))

    def test_the_learn_arm_still_records_with_the_arm_off(self):
        self.tick()
        r = self.run_hook(self.failure("gh pr list --limit 5", "s1"),
                          REPEAT_GATE_REFUSE=None)
        self.assertEqual(r.returncode, 0, r.stderr)
        fails = [x for x in self.rows() if x["t"] == "fail"]
        self.assertEqual(len(fails), 1, "the learn arm stopped recording: %r" % self.rows())

    def test_the_recovery_arm_still_records_with_the_arm_off(self):
        self.tick()
        self.run_hook(self.failure(FAILING_CMD, "s1"), REPEAT_GATE_REFUSE=None)
        self.tick()
        self.run_hook(self.success(FIX_CMD, "s1"), REPEAT_GATE_REFUSE=None)
        recs = [x for x in self.rows() if x["t"] == "recover"]
        self.assertEqual(len(recs), 1, "the recovery arm stopped recording: %r" % self.rows())
        self.assertEqual(recs[0]["cmd"], FIX_CMD)

    def test_both_argv_doors_answer_with_the_arm_off(self):
        """`--norm-of` is called by hooks/remind.sh and `--eligible-of` by two CLIs.
        Neither is the refusal, and neither may be switched off by its knob."""
        r = subprocess.run(["bash", HOOK, "--norm-of", "Bash"], input="gh pr list --limit 5",
                           capture_output=True, text=True,
                           env=self.env(REPEAT_GATE_REFUSE=None), timeout=180)
        self.assertEqual(r.stdout.strip(), "gh pr list --limit <N>")
        r = subprocess.run(["bash", HOOK, "--eligible-of", "Bash"], input="gh pr list",
                           capture_output=True, text=True,
                           env=self.env(REPEAT_GATE_REFUSE=None), timeout=180)
        self.assertEqual(r.stdout.strip(), "eligible")


# ============================================================== the --eligible-of door
class EligibleDoorTest(GateCase):
    """The head exemptions, asked of the gate rather than copied into a CLI.

    Every verdict below is checked TWICE: once through the door, and once by driving the
    REAL refuse arm at the threshold with the same command. A door that answered a
    different question from the arm would be a second implementation wearing the first
    one's name, which is the whole defect it exists to prevent."""

    CASES = [
        ("gh pr list --limit 5", "eligible"),
        ("curl -sf https://api.github.com/x", "eligible"),
        ("git clean -nd", "exempt-allowlist"),
        ("FOO=1 ls -la /nowhere", "exempt-allowlist"),
        ("./run_tests.sh", "exempt-runner"),
        ("npm run build --silent", "exempt-runner"),
        ("python3 -m pytest tests/", "exempt-runner"),
        ("skillrepeat forget c1x1-e1x1", "exempt-cli"),
        ("gh pr list && skillrepeat list", "exempt-cli"),
    ]

    def door(self, command, tool="Bash", **env_extra):
        argv = ["bash", HOOK, "--eligible-of"]
        if tool is not None:
            argv.append(tool)
        return subprocess.run(argv, input=command, capture_output=True, text=True,
                              env=self.env(**env_extra), timeout=180).stdout.strip()

    def test_every_verdict(self):
        for command, want in self.CASES:
            self.assertEqual(self.door(command), want, command)

    def test_a_non_bash_tool_and_an_empty_command(self):
        self.assertEqual(self.door('{"command":"x"}', tool="Skill"), "exempt-tool")
        self.assertEqual(self.door(""), "exempt-empty")
        # The tool argument defaults to Bash, which is what a caller with a Bash-only
        # store would otherwise have to remember to pass.
        self.assertEqual(self.door("gh pr list", tool=None), "eligible")

    def test_the_door_matches_what_the_real_arm_does(self):
        """NON-VACUITY, and the only assertion here that could catch a drifting copy."""
        for i, (command, want) in enumerate(self.CASES):
            self.teach(command, ["a%d" % i, "b%d" % i])
        for i, (command, want) in enumerate(self.CASES):
            self.tick()
            r = self.run_hook(self.attempt(command, "z%d" % i))
            denied = bool(r.stdout.strip())
            self.assertEqual(denied, want == "eligible",
                             "the door says %r and the arm %s: %s"
                             % (want, "denied" if denied else "allowed", command))

    def test_the_off_switch_does_not_close_the_door(self):
        """Two scripts, two switches -- the same rule `--norm-of` already holds to. A user
        who turns the gate off must not silently change what two instruments report."""
        self.assertEqual(self.door("git status", SKILL_COMPOUNDER_REPEAT_GATE=0),
                         "exempt-allowlist")
        self.assertEqual(self.door("gh pr list", SKILL_COMPOUNDER_REPEAT_GATE=0),
                         "eligible")


# ================================================ the CLI's count and the gate's, equal
class InstrumentAgreementTest(GateCase):
    """`bin/skillrepeat` says its summary and the gate's "must AGREE about what refuses".
    It did not: it counted distinct sessions and the self-recovery rule, and applied
    neither head exemption. Measured on the live store on 2026-09-02 -- 389 rows, 196
    signatures, 99 sessions -- `skillrepeat stats` printed `refusing: 10` and the real
    hook, driven against all ten, denied NONE.

    So the claim is now a measurement. The store below is built by the real hook out of
    commands covering every exemption kind, every threshold signature is put to the real
    refuse arm in a fresh session, and the CLI's number must equal the denials."""

    MIX = [
        ("gh pr list --limit 5", True),
        ("curl -sf https://api.github.com/x", True),
        ("git clean -nd", False),
        ("./run_tests.sh", False),
        ("npm run build --silent", False),
        ("skillrepeat list --json", False),
    ]

    def build(self):
        for i, (command, _) in enumerate(self.MIX):
            self.teach(command, ["a%d" % i, "b%d" % i])

    def hook_denials(self):
        """What the REAL arm does, asked one signature at a time in a fresh session."""
        n = 0
        for i, (command, _) in enumerate(self.MIX):
            self.tick()
            if self.run_hook(self.attempt(command, "q%d" % i)).stdout.strip():
                n += 1
        return n

    def cli_refusing(self):
        r = self.run_cli("stats", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["refusing"]

    def test_stats_and_list_both_equal_what_the_hook_denies(self):
        self.build()
        denied = self.hook_denials()
        # NON-VACUITY IN BOTH DIRECTIONS: some signatures refuse and some do not, so an
        # instrument that answered "all" or "none" could not pass this.
        self.assertEqual(denied, len([c for c in self.MIX if c[1]]))
        self.assertGreater(denied, 0)
        self.assertLess(denied, len(self.MIX))

        self.assertEqual(self.cli_refusing(), denied,
                         "skillrepeat stats disagrees with the gate")
        got = json.loads(self.run_cli("list", "--json").stdout)
        self.assertEqual(len([g for g in got if g["refuses"]]), denied,
                         "skillrepeat list --json disagrees with the gate")
        # ...and the threshold count on its own is the number that used to be printed, so
        # this test would have failed before the fix rather than passing vacuously.
        at_threshold = len([g for g in got if g["sessions"] >= 2])
        self.assertEqual(at_threshold, len(self.MIX))
        self.assertNotEqual(at_threshold, denied)

    def test_the_gate_column_names_the_exempt_ones(self):
        self.build()
        out = self.run_cli("list").stdout
        self.assertIn("exempt", out, "the table hides the exemption entirely:\n" + out)
        self.assertIn("refuses", out)
        # One row per signature, and every one of them at the threshold: no row may be
        # left as `-`, which would mean the count rule and the table disagree.
        body = [l for l in out.splitlines() if l.startswith("c")]
        self.assertEqual(len(body), len(self.MIX))
        # READ OUT OF THE GATE COLUMN AND NOT OUT OF THE WHOLE LINE. This was
        # `" - " in l`, and that stopped being a question about the GATE column the day
        # LESSON was added beside it: none of these signatures has a recovery, so every
        # one of them prints a legitimate `-` under LESSON and the substring matched all
        # six. The header is the ruler here as everywhere else in this table.
        hdr = [l for l in out.splitlines() if l.startswith("SIGNATURE")][0]
        gate = [l[hdr.index("GATE"):hdr.index("LESSON")].strip() for l in body]
        self.assertEqual([v for v in gate if v == "-"], [], gate)

    def test_a_skill_signature_at_the_threshold_is_not_reported_as_refusing(self):
        """The refuse arm is Bash-only and says so; the CLI reported `refuses` for a
        Skill signature that the arm can never even look at."""
        self.teach({"name": "some-skill"}, ["a", "b"], tool="Skill")
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt({"name": "some-skill"}, "q",
                                                       tool="Skill")))
        self.assertEqual(self.cli_refusing(), 0)

    def test_the_live_store_if_this_machine_has_one(self):
        """THE CLAIM ON REAL DATA, when there is any. This runs against a COPY of
        `~/.claude/skill-compounder/repeats/index.jsonl` in the temp state root, asserts
        only on COUNTS, and prints only counts -- the store holds command text and error
        text and none of it leaves this process. A machine with no store still runs every
        assertion above; this one adds the live population when it exists, which is the
        only place the ten-against-zero gap was ever visible."""
        live = os.path.join(os.path.expanduser("~"), ".claude", "skill-compounder",
                            "repeats", "index.jsonl")
        if not os.path.exists(live):
            print("\n[live] no store on this machine; the synthetic mix above stands alone")
            return
        os.makedirs(os.path.dirname(self.store), exist_ok=True)
        shutil.copyfile(live, self.store)
        rows = self.rows()
        sigs = {r.get("sig") for r in rows if r.get("t") == "fail"}
        cli = self.cli_refusing()
        got = json.loads(self.run_cli("list", "--json", "--all").stdout)
        at_threshold = len([g for g in got if g["sessions"] >= 2
                            and g["transient_sessions"] == 0])
        # Every threshold signature put to the REAL arm, in a session id no real session
        # can have used, so guard 1 (this session's own failures never count) cannot
        # accidentally suppress one.
        denied = 0
        for g in got:
            if g["sessions"] < 2 or g["transient_sessions"] > 0:
                continue
            self.tick()
            payload = self.attempt(g["raw"], "live-probe-%s" % g["sig"], tool=g["tool"])
            if self.run_hook(payload).stdout.strip():
                denied += 1
        print("\n[live] %d rows, %d signatures, %d at threshold, hook denies %d, "
              "skillrepeat stats says %d" % (len(rows), len(sigs), at_threshold,
                                             denied, cli))
        self.assertEqual(cli, denied,
                         "on the live store skillrepeat says %d and the gate denies %d"
                         % (cli, denied))


# ============================================================== cross-tool recovery
class CrossToolRecoveryTest(GateCase):
    """A failure of tool X bound to a success of tool Y, on shared content tokens.

    This is the maintainer's own example on the wire: the GitHub tool dies and the session
    gets it done with `gh`. Until 2026-09-03 the recovery arm bound only the same tool, so
    that pair was never recorded and the store never learned the one fix it was built for.

    THE MCP PAYLOADS HERE ARE FED TO THE HOOK DIRECTLY. That used to be the only way one
    could arrive at all -- the matcher was `Bash|Skill` on all three events -- and since
    2026-09-03 the two learning events carry `Bash|Skill|mcp__.*`, so the platform may
    deliver one (WiringTest pins the matchers per event). What is STILL unestablished is
    whether it does: no MCP tool failure has been observed arriving at a hook here. These
    tests establish that the RULE handles such a payload, not that anything is being
    learned from MCP calls on this machine."""

    MCP = "mcp__github__create_issue"
    MCP_ERR = ("Exit code 1\nHTTP 403: Resource not accessible by integration")

    def recoveries(self):
        return [r for r in self.rows() if r["t"] == "recover"]

    def test_an_mcp_failure_and_a_gh_success_bind_cross_tool(self):
        self.tick()
        self.run_hook(self.failure(
            {"owner": "ContextLab", "repo": "claude-skill-compounder", "title": "x"},
            "s1", error=self.MCP_ERR, tool=self.MCP))
        self.tick()
        self.run_hook(self.success(
            'gh issue create --repo ContextLab/claude-skill-compounder --title "x"', "s1"))
        rec = self.recoveries()
        self.assertEqual(len(rec), 1, self.rows())
        self.assertTrue(rec[0]["cross_tool"])
        self.assertEqual(rec[0]["tool"], "Bash")
        self.assertIn("gh issue create --repo ContextLab/claude-skill-compounder",
                      rec[0]["norm"])
        # The row is filed under the FAILING call's signature, which is the whole point:
        # a later session asking "what worked for this" has to find it there.
        fail_row = [r for r in self.rows() if r["t"] == "fail"][0]
        self.assertEqual(rec[0]["sig"], fail_row["sig"])

    def test_a_skill_failure_and_a_bash_success_bind_cross_tool(self):
        """`tool_input.skill` is where a Skill call's name arrives (measured 2026-08-26,
        docs/CLAUDE-CODE-BEHAVIOR.md), so the tokens come out of the skill name."""
        self.tick()
        self.run_hook(self.failure({"skill": "github-issue-triage"}, "s1",
                                   error="Exit code 1\nUnknown skill", tool="Skill"))
        self.tick()
        self.run_hook(self.success("gh issue list --repo github/docs", "s1"))
        rec = self.recoveries()
        self.assertEqual(len(rec), 1, self.rows())
        self.assertTrue(rec[0]["cross_tool"])
        self.assertEqual(rec[0]["tool"], "Bash")

    def test_a_same_tool_recovery_still_binds_and_is_not_marked_cross_tool(self):
        """The rule that was here first, unchanged, and NOT relabelled: a reader weighing
        the two kinds of evidence has to be able to tell them apart."""
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s1"))
        self.tick(); self.run_hook(self.success(FIX_CMD, "s1"))
        rec = self.recoveries()
        self.assertEqual(len(rec), 1)
        self.assertNotIn("cross_tool", rec[0], rec[0])

    def test_no_binding_when_the_tokens_do_not_overlap(self):
        self.tick()
        self.run_hook(self.failure({"owner": "ContextLab", "repo": "skill-compounder"},
                                   "s1", error=self.MCP_ERR, tool=self.MCP))
        self.tick()
        self.run_hook(self.success("brew upgrade sqlite", "s1"))
        self.assertEqual(self.recoveries(), [], self.rows())

    def test_one_shared_token_is_not_enough(self):
        """NON-VACUITY for the threshold: one token in common, everything else different,
        and nothing binds -- so the bindings above are not simply binding everything."""
        self.tick()
        self.run_hook(self.failure({"repo": "claude-skill-compounder"}, "s1",
                                   error=self.MCP_ERR, tool=self.MCP))
        self.tick()
        self.run_hook(self.success("brew upgrade compounder", "s1"))
        self.assertEqual(self.recoveries(), [], self.rows())

    def test_the_token_threshold_is_configurable(self):
        """Counted as a DELTA and in a fresh session each time. The store is append-only,
        so a test that read the running total would report the previous round's row as
        this round's binding and pass whatever the knob did."""
        def bound_under(min_tokens, session):
            before = len(self.recoveries())
            self.tick()
            self.run_hook(self.failure({"repo": "claude-skill-compounder"}, session,
                                       error=self.MCP_ERR, tool=self.MCP),
                          REPEAT_RECOVERY_MIN_TOKENS=min_tokens)
            self.tick()
            self.run_hook(self.success("gh repo view claude-skill-compounder", session),
                          REPEAT_RECOVERY_MIN_TOKENS=min_tokens)
            return len(self.recoveries()) - before
        # `repo`, `claude`, `skill`, `compounder` are the four shared tokens.
        self.assertEqual(bound_under(2, "a"), 1, "the default did not bind")
        self.assertEqual(bound_under(4, "b"), 1, "exactly four shared tokens did not bind")
        self.assertEqual(bound_under(5, "c"), 0, "a threshold of five bound anyway")
        self.assertEqual(bound_under(0, "d"), 0, "0 must switch cross-tool binding off")

    def test_zero_tokens_disables_cross_tool_without_touching_the_same_tool_rule(self):
        self.tick()
        self.run_hook(self.failure({"repo": "claude-skill-compounder"}, "s1",
                                   error=self.MCP_ERR, tool=self.MCP),
                      REPEAT_RECOVERY_MIN_TOKENS=0)
        self.tick()
        self.run_hook(self.success("gh repo view claude-skill-compounder", "s1"),
                      REPEAT_RECOVERY_MIN_TOKENS=0)
        self.assertEqual(self.recoveries(), [])
        # ...and the same-tool rule, which has its OWN threshold knob, is untouched by it.
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s2"),
                                   REPEAT_RECOVERY_MIN_TOKENS=0)
        self.tick(); self.run_hook(self.success(FIX_CMD, "s2"),
                                   REPEAT_RECOVERY_MIN_TOKENS=0)
        self.assertEqual(len(self.recoveries()), 1, "the same-tool rule was switched off")

    def test_the_window_bounds_a_cross_tool_binding_too(self):
        self.tick()
        self.run_hook(self.failure({"repo": "claude-skill-compounder"}, "s1",
                                   error=self.MCP_ERR, tool=self.MCP))
        for i in range(5):
            self.tick()
            self.run_hook(self.filler("s1", i))
        self.tick()
        self.run_hook(self.success("gh repo view claude-skill-compounder", "s1"))
        self.assertEqual(self.recoveries(), [],
                         "a cross-tool success past the window was bound anyway")

    def test_inside_the_window_the_same_pair_does_bind(self):
        """NON-VACUITY for the window test above: two intervening calls instead of five."""
        self.tick()
        self.run_hook(self.failure({"repo": "claude-skill-compounder"}, "s1",
                                   error=self.MCP_ERR, tool=self.MCP))
        for i in range(2):
            self.tick()
            self.run_hook(self.filler("s1", i))
        self.tick()
        self.run_hook(self.success("gh repo view claude-skill-compounder", "s1"))
        self.assertEqual(len(self.recoveries()), 1)

    def test_the_placeholders_contribute_no_tokens(self):
        """`<S>`, `<N>` and `<P>` are in EVERY normalised call, so if they counted, any two
        masked calls would share three tokens and bind. They survive the split as single
        letters and the length rule drops them; nothing names them."""
        self.tick()
        self.run_hook(self.failure({"note": "zzz", "count": 7, "where": "/aa/bb/cc"},
                                   "s1", error=self.MCP_ERR, tool=self.MCP))
        self.tick()
        self.run_hook(self.success('grep -n "qqq" /xx/yy/zz 41', "s1"))
        self.assertEqual(self.recoveries(), [], self.rows())

    def test_a_recovery_of_a_second_armed_failure_is_still_one_per_failure(self):
        """Two armed failures whose tokens both overlap the one success: each is bound
        once, and neither is bound twice."""
        self.tick()
        self.run_hook(self.failure({"repo": "claude-skill-compounder", "a": 1}, "s1",
                                   error=self.MCP_ERR, tool=self.MCP))
        self.tick()
        self.run_hook(self.failure({"repo": "claude-skill-compounder", "b": 2}, "s1",
                                   error=self.MCP_ERR, tool=self.MCP))
        self.tick()
        self.run_hook(self.success("gh repo view claude-skill-compounder", "s1"))
        rec = self.recoveries()
        self.assertEqual(len(rec), 2, self.rows())
        self.assertEqual(len({r["sig"] for r in rec}), 2)

    def test_a_double_delivered_success_writes_one_cross_tool_row(self):
        self.tick()
        self.run_hook(self.failure({"repo": "claude-skill-compounder"}, "s1",
                                   error=self.MCP_ERR, tool=self.MCP))
        self.tick()
        p = self.success("gh repo view claude-skill-compounder", "s1", tuid="toolu_same")
        self.run_hook(p)
        self.run_hook(p)
        self.assertEqual(len(self.recoveries()), 1, self.rows())


# ============================================================== the same-tool rule
class SameToolBindingTest(GateCase):
    """A SHELL'S TOOL NAME IS NOT EVIDENCE, and three defects observed together in one
    live session on 2026-09-03 (state root ~/.claude/skill-compounder, session f288cf8c).

    A `gh issue view <N> --comments` call exited 1 on a deprecation warning. The store then
    held FOUR byte-identical `recover` rows under ONE tool_use_id naming
    `cat notes/OPEN-THREADS.md` as the fix, and the statement the session was given named a
    THIRD command, `TEST_TIMEOUT=... ./run_tests.sh`. Each assertion below is one of those.

    The payloads are the live ones, shortened only where the length carries nothing."""

    GH_DEPRECATION = ("Exit code 1\nGraphQL: Projects (classic) is being deprecated in "
                      "favor of the new Projects experience, see: "
                      "https://github.blog/changelog/x. (repository.issue.projectCards)")
    FAILING = "gh issue view 43 --comments 2>&1"
    # Shares `issue`, `view` and `comments` with the failure: the real fix, which is the
    # same call with the flag that avoids the deprecated field.
    REAL_FIX = "gh issue view 43 --comments --json comments --jq '.comments[].body'"
    # Shares NOTHING with it. `cat`, `notes`, `open`, `threads` against `issue`, `view`,
    # `comments` -- and it is the command the live store recorded as the recovery.
    UNRELATED = "cat notes/OPEN-THREADS.md 2>&1"

    def recoveries(self):
        return [r for r in self.rows() if r["t"] == "recover"]

    def context_of(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout.strip():
            return None
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def arm(self, n, session="S", cmd=None):
        """`n` failures of ONE signature, each a distinct call with its own tool_use_id --
        which is what the live session did, and what arms `n` separate pending lines."""
        for i in range(n):
            self.tick()
            # The tool_use_id carries the CLOCK as well as the index: `claim_once` drops a
            # repeat of one id as the duplicate delivery, so a second arming round reusing
            # `toolu_fail_0` would silently record nothing at all.
            self.run_hook(self.failure(cmd or (self.FAILING.replace("43", str(30 + i))),
                                       session, error=self.GH_DEPRECATION,
                                       tuid="toolu_fail_%d_%d" % (self.clock, i)))

    # ------------------------------------------------------- (2) the duplicated rows
    def test_many_armed_failures_of_one_signature_write_one_recovery_row(self):
        """DEFECT: N failures of one signature arm N pending lines, and the success bound
        every one of them and wrote a row for each -- four byte-identical rows under one
        tool_use_id on the live store. The pending lines are still consumed one apiece;
        what is de-duplicated is the ROW."""
        self.arm(4)
        self.tick()
        self.run_hook(self.success(self.REAL_FIX, "S", tuid="toolu_fix"))
        rec = self.recoveries()
        self.assertEqual(len(rec), 1, "one success wrote %d rows: %r" % (len(rec), rec))
        self.assertEqual(rec[0]["cmd"], self.REAL_FIX)

    def test_sig_and_tuid_together_are_unique_in_the_store(self):
        """The invariant the row de-duplication buys, stated the way the live store was
        interrogated: `jq recover | (sig, tuid) | uniq -c` must print nothing above 1."""
        self.arm(3)
        self.tick()
        p = self.success(self.REAL_FIX, "S", tuid="toolu_fix")
        self.run_hook(p)
        self.run_hook(p)                      # ...and the duplicate delivery on top
        seen = {}
        for r in self.recoveries():
            key = (r["sig"], r["tuid"])
            seen[key] = seen.get(key, 0) + 1
        self.assertTrue(seen, "nothing bound at all")
        self.assertEqual([k for k, v in seen.items() if v > 1], [],
                         "duplicate (sig, tuid) rows: %r" % seen)

    def test_two_distinct_signatures_bound_by_one_success_still_write_two_rows(self):
        """NON-VACUITY for the de-duplication: it is per SIGNATURE, not per event. Two
        genuinely different failures that the same success recovers are two recoveries."""
        self.arm(2)
        self.tick()
        self.run_hook(self.failure("gh issue view 43 --comments --json body", "S",
                                   error="Exit code 1\nunknown field: body",
                                   tuid="toolu_other"))
        self.tick()
        self.run_hook(self.success(self.REAL_FIX, "S", tuid="toolu_fix"))
        rec = self.recoveries()
        self.assertEqual(len(rec), 2, rec)
        self.assertEqual(len({r["sig"] for r in rec}), 2)

    # ------------------------------------------- (3) the statement and the row agreeing
    def test_the_statement_names_the_call_the_row_records(self):
        self.arm(1)
        self.tick()
        ctx = self.context_of(self.run_hook(self.success(self.REAL_FIX, "S",
                                                         tuid="toolu_fix")))
        self.assertIsNotNone(ctx, "the arm bound a recovery and said nothing")
        rec = self.recoveries()
        self.assertEqual(len(rec), 1)
        worked = [ln for ln in ctx.split("\n") if ln.strip().startswith("worked:")]
        self.assertEqual(len(worked), 1, ctx)
        self.assertIn(rec[0]["norm"], worked[0],
                      "the statement names a different call from the row it belongs to:\n"
                      "  statement: %s\n  row norm:  %s" % (worked[0], rec[0]["norm"]))

    def test_a_second_recovery_does_not_rewrite_the_statement_already_told(self):
        """DEFECT, and the exact shape observed live: a LATER, genuinely different recovery
        of the same signature rewrote the marker file while the `said-` claim stopped the
        session being told again -- so the lesson gate would later quote a command the
        session had never been shown. First binding wins, because the first binding is the
        one the session was told about."""
        self.arm(1)
        self.tick()
        first = self.context_of(self.run_hook(self.success(self.REAL_FIX, "S",
                                                           tuid="toolu_fix1")))
        self.assertIsNotNone(first)
        self.arm(1, cmd=self.FAILING)          # arm the SAME signature again
        self.tick()
        second_fix = "gh issue view 43 --comments --json comments --jq '.comments[].url'"
        self.assertIsNone(self.context_of(self.run_hook(
            self.success(second_fix, "S", tuid="toolu_fix2"))),
            "the session was told twice for one signature")
        self.assertEqual(len(self.recoveries()), 2, "the second recovery lost its row")
        markers = os.path.join(self.state, "repeats", "lessons", "S")
        names = [n for n in os.listdir(markers) if n.startswith("s-")]
        self.assertEqual(len(names), 1, names)
        stored = open(os.path.join(markers, names[0]), encoding="utf-8").read()
        self.assertEqual(stored, first,
                         "the stored statement drifted from the one the session was told")

    def test_every_signature_a_success_bound_gets_its_own_marker(self):
        """DEFECT: the marker was written once, after the loop, for the FIRST bound
        signature only -- so a success that bound two wrote two rows and left the second
        invisible to the lesson gate, which reads its signatures off these filenames."""
        self.arm(1)
        self.tick()
        self.run_hook(self.failure("gh issue view 43 --comments --json body", "S",
                                   error="Exit code 1\nunknown field: body",
                                   tuid="toolu_other"))
        self.tick()
        self.run_hook(self.success(self.REAL_FIX, "S", tuid="toolu_fix"))
        sigs = {r["sig"] for r in self.recoveries()}
        self.assertEqual(len(sigs), 2, self.recoveries())
        markers = os.path.join(self.state, "repeats", "lessons", "S")
        names = {n[2:] for n in os.listdir(markers) if n.startswith("s-")}
        self.assertEqual(names, {re.sub(r"[^A-Za-z0-9._-]", "_", x) for x in sigs},
                         "a bound signature has a row and no marker: %r vs %r"
                         % (names, sigs))

    # ------------------------------------------------------- the rule itself
    def test_an_unrelated_bash_success_does_not_bind(self):
        """The live binding, verbatim. `Bash` following `Bash` is not evidence of anything,
        and these two share no content token at all."""
        self.arm(4)
        self.tick()
        self.run_hook(self.success(self.UNRELATED, "S", tuid="toolu_cat"))
        self.assertEqual(self.recoveries(), [],
                         "an unrelated command was recorded as the fix: %r" % self.rows())

    def test_an_unrelated_success_says_nothing_to_the_session(self):
        self.arm(1)
        self.tick()
        self.assertIsNone(self.context_of(
            self.run_hook(self.success(self.UNRELATED, "S", tuid="toolu_cat"))))

    def test_an_unrelated_success_leaves_the_failure_armed_for_the_real_fix(self):
        """THE COST THAT IS NOT NOISE. A binding CONSUMES its armed failure, so under the
        old rule the unrelated success ate the arming and the genuine fix arriving two
        calls later could never be recorded at all. On the live store one `cat` disarmed
        four `gh issue view` failures."""
        self.arm(1)
        self.tick(); self.run_hook(self.success(self.UNRELATED, "S", tuid="toolu_cat"))
        self.tick(); self.run_hook(self.success(self.REAL_FIX, "S", tuid="toolu_fix"))
        rec = self.recoveries()
        self.assertEqual(len(rec), 1, self.rows())
        self.assertEqual(rec[0]["cmd"], self.REAL_FIX)

    def test_a_related_success_binds_and_is_not_marked_cross_tool(self):
        self.arm(1)
        self.tick()
        self.run_hook(self.success(self.REAL_FIX, "S", tuid="toolu_fix"))
        rec = self.recoveries()
        self.assertEqual(len(rec), 1, self.rows())
        self.assertNotIn("cross_tool", rec[0], rec[0])

    def test_an_exact_self_recovery_binds_below_the_threshold(self):
        """THE CARVE-OUT, and it is load-bearing rather than a convenience: the refusal
        arm's self-recovery exclusion is built on these rows, and `pwd` carries ONE content
        token, so no positive floor could ever admit it."""
        self.tick()
        self.run_hook(self.failure("pwd", "S", error="Exit code 1\npwd: cannot access",
                                   tuid="toolu_pwd_f"))
        self.tick()
        self.run_hook(self.success("pwd", "S", tuid="toolu_pwd_s"))
        rec = self.recoveries()
        self.assertEqual(len(rec), 1, "an exact self-recovery was turned away: %r"
                         % self.rows())
        self.assertEqual(rec[0]["norm"], "pwd")

    def test_one_shared_token_is_not_enough_for_a_shell(self):
        """NON-VACUITY for the floor: `echo` alone in common -- the single commonest
        accidental overlap in the live store, 11 of its 31 one-token bindings -- binds
        nothing."""
        self.tick()
        self.run_hook(self.failure("echo start; gh issue view 43 --comments", "S",
                                   error=self.GH_DEPRECATION, tuid="toolu_e1"))
        self.tick()
        self.run_hook(self.success("echo done; cat notes/OPEN-THREADS.md", "S",
                                   tuid="toolu_e2"))
        self.assertEqual(self.recoveries(), [], self.rows())

    def test_the_threshold_is_REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS(self):
        """Counted as a DELTA in a fresh session each time: the store is append-only, so a
        running total would report the previous round's row as this round's binding."""
        def bound_under(value, session):
            before = len(self.recoveries())
            self.tick()
            self.run_hook(self.failure(self.FAILING, session, error=self.GH_DEPRECATION,
                                       tuid="toolu_%s_f" % session),
                          REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS=value)
            self.tick()
            self.run_hook(self.success(self.UNRELATED, session,
                                       tuid="toolu_%s_s" % session),
                          REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS=value)
            return len(self.recoveries()) - before
        self.assertEqual(bound_under(2, "a"), 0, "the shipped default bound an unrelated "
                                                 "command")
        self.assertEqual(bound_under(0, "b"), 1, "0 must restore the unconditional "
                                                 "same-tool binding")
        self.assertEqual(bound_under(1, "c"), 0, "zero shared tokens cleared a floor of 1")
        # A misspelling lands on the documented default rather than switching the rule off.
        self.assertEqual(bound_under("two", "d"), 0)

    def test_the_threshold_admits_a_pair_that_clears_it(self):
        """NON-VACUITY for the knob: the same session shape with a RELATED success binds
        at every one of those settings."""
        for i, value in enumerate((2, 0, 1, "two")):
            session = "n%d" % i
            before = len(self.recoveries())
            self.tick()
            self.run_hook(self.failure(self.FAILING, session, error=self.GH_DEPRECATION,
                                       tuid="toolu_%s_f" % session),
                          REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS=value)
            self.tick()
            self.run_hook(self.success(self.REAL_FIX, session,
                                       tuid="toolu_%s_s" % session),
                          REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS=value)
            self.assertEqual(len(self.recoveries()) - before, 1,
                             "a related fix did not bind at %r" % (value,))

    def test_a_non_shell_tool_still_binds_on_the_tool_alone(self):
        """`mcp__docs__fetch` names its operation in its own name, so a success of it after
        a failure of it is the same operation by construction. Only `Bash` is content
        tested; `shell_tool()` is the one place that decides which is which."""
        self.tick()
        self.run_hook(self.failure({"page": "alpha"}, "S", tool="mcp__docs__fetch",
                                   error="Exit code 1\nHTTP 500", tuid="toolu_m1"))
        self.tick()
        self.run_hook(self.success({"slug": "zulu"}, "S", tool="mcp__docs__fetch",
                                   tuid="toolu_m2"))
        rec = self.recoveries()
        self.assertEqual(len(rec), 1, "a same-tool MCP recovery stopped binding: %r"
                         % self.rows())
        self.assertNotIn("cross_tool", rec[0], rec[0])

    def test_norm_of_is_unchanged_by_the_new_knob(self):
        """`--norm-of` is a pure function of its stdin and reads no store. The knob must
        not reach it: bin/skillrepeat and bin/skillreport compare its output BYTE FOR BYTE
        against signatures already in the store, so a shift in either direction would make
        every stored signature unmatchable."""
        corpus = [self.FAILING, self.REAL_FIX, self.UNRELATED, "pwd",
                  FAILING_CMD, FIX_CMD, SATURATING_CMD,
                  "cd /tmp && python3 - <<'EOF'\nprint(1)\nEOF"]
        baseline = []
        for cmd in corpus:
            r = subprocess.run(["bash", HOOK, "--norm-of", "Bash"], input=cmd,
                               capture_output=True, text=True, env=self.env(), timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            baseline.append(r.stdout)
        self.assertTrue(all(baseline), baseline)
        for value in (0, 1, 2, 9, "two"):
            for cmd, want in zip(corpus, baseline):
                r = subprocess.run(["bash", HOOK, "--norm-of", "Bash"], input=cmd,
                                   capture_output=True, text=True, timeout=60,
                                   env=self.env(REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS=value))
                self.assertEqual(r.stdout, want,
                                 "--norm-of moved at REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS=%r for "
                                 "%r" % (value, cmd))


# ============================================================== the lesson statement
class LessonStatementTest(GateCase):
    """THE FIRST TIME: SAY IT. A recovery used to write a row into a file nobody reads
    mid-session. The arm now states the fact at the moment both halves are known."""

    def context_of(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout.strip():
            return None
        d = json.loads(r.stdout)
        hso = d["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PostToolUse")
        return hso["additionalContext"]

    def recover_once(self, session="s1", cmd=FAILING_CMD, fix=FIX_CMD, **kw):
        self.tick(); self.run_hook(self.failure(cmd, session, **kw))
        self.tick()
        return self.run_hook(self.success(fix, session))

    def test_the_statement_names_the_failure_the_fix_and_both_commands(self):
        ctx = self.context_of(self.recover_once())
        self.assertIsNotNone(ctx, "the recovery arm said nothing at all")
        sig = [r for r in self.rows() if r["t"] == "fail"][0]["sig"]
        self.assertIn("gh pr list --limit <N>", ctx)
        self.assertIn("gh: command not found", ctx)
        self.assertIn("--repo ContextLab/claude-skill-compounder", ctx)
        self.assertIn("skillnote add --lesson %s" % sig, ctx)
        self.assertIn("skillrepeat dismiss %s --why" % sig, ctx)

    def test_it_is_a_statement_and_carries_no_imperative(self):
        """Measured (PLATFORM FACTS 4): the model treats text arriving through a hook as
        untrusted and refuses directives in it, so an imperative is both ignored and
        misleading about who is asking. This asserts the shape, not the model."""
        ctx = self.context_of(self.recover_once())
        first_words = [ln.strip().split(" ")[0].lower()
                       for ln in ctx.split("\n") if ln.strip()]
        for bad in ("run", "write", "record", "please", "you", "do", "call", "use"):
            self.assertNotIn(bad, first_words, "imperative opener %r in:\n%s" % (bad, ctx))

    def test_the_statement_stays_under_seven_hundred_characters(self):
        """Measured against input that saturates both normalisers, not against a typical
        command: the caps inside the builder are what has to hold, and the widest input
        the gate can produce is the only thing that tests them."""
        ctx = self.context_of(self.recover_once(cmd=SATURATING_CMD, error=SATURATING_ERR,
                                                fix=SATURATING_CMD.replace("gh ", "curl ")))
        self.assertIsNotNone(ctx)
        self.assertLess(len(ctx), 700, "the statement is %d characters:\n%s"
                        % (len(ctx), ctx))
        # ...and it is not short because the pieces went missing.
        self.assertGreater(len(ctx), 300, ctx)
        self.assertIn("skillnote add --lesson", ctx)
        self.assertIn("skillrepeat dismiss", ctx)

    def test_a_cross_tool_recovery_says_it_too(self):
        self.tick()
        self.run_hook(self.failure({"repo": "claude-skill-compounder"}, "s1",
                                   error="Exit code 1\nHTTP 403: not accessible",
                                   tool="mcp__github__create_issue"))
        self.tick()
        ctx = self.context_of(self.run_hook(
            self.success("gh repo view claude-skill-compounder", "s1")))
        self.assertIsNotNone(ctx)
        self.assertIn("gh repo view claude-skill-compounder", ctx)

    def test_once_per_signature_per_session(self):
        """A second, genuinely different recovery of the same signature later in the
        session writes its row and says nothing: the session has already been told."""
        first = self.context_of(self.recover_once())
        self.assertIsNotNone(first)
        second = self.context_of(self.recover_once(fix=FIX_CMD_2))
        self.assertIsNone(second, "the arm said it twice in one session:\n%s" % second)
        self.assertEqual(len([r for r in self.rows() if r["t"] == "recover"]), 2)

    def test_a_double_delivered_success_says_it_once(self):
        """Both wirings deliver every event twice. The duplicate is dropped by the arm's
        own claim before it reaches the statement, and this pins that it stays dropped."""
        self.tick(); self.run_hook(self.failure(FAILING_CMD, "s1"))
        self.tick()
        p = self.success(FIX_CMD, "s1", tuid="toolu_same_s")
        self.assertIsNotNone(self.context_of(self.run_hook(p)))
        self.assertIsNone(self.context_of(self.run_hook(p)))

    def test_a_different_session_is_told_as_well(self):
        """Per session, not per store: a fresh session has not seen the first statement."""
        self.assertIsNotNone(self.context_of(self.recover_once("s1")))
        self.assertIsNotNone(self.context_of(self.recover_once("s2")))

    def test_a_success_that_binds_nothing_says_nothing(self):
        self.tick()
        self.assertIsNone(self.context_of(
            self.run_hook(self.success("echo hello", "s1"))))


# ============================================================== the lesson gate
class LessonGateTest(GateCase):
    """THE SECOND TIME: REFUSE UNTIL IT IS WRITTEN.

    `REPEAT_GATE_REFUSE` is DELETED throughout this class. The lesson gate ships ON and
    the repeat arm ships OFF, so a test that left the repeat arm switched on could not
    tell which rule produced a refusal -- and the configuration under test here is the
    shipped one."""

    ERR = "Exit code 127\ngh: command not found"

    def env(self, **extra):
        extra.setdefault("REPEAT_GATE_REFUSE", None)
        return GateCase.env(self, **extra)

    def sig(self):
        return [r for r in self.rows() if r["t"] == "fail"][0]["sig"]

    def fail_then_fix(self, session, cmd=FAILING_CMD, fix=FIX_CMD, **kw):
        self.tick(); self.run_hook(self.failure(cmd, session, error=self.ERR), **kw)
        self.tick(); self.run_hook(self.success(fix, session), **kw)

    def probe(self, session="s2", command="npm install left-pad", **kw):
        self.tick()
        return self.run_hook(self.attempt(command, session), **kw)

    def assert_lesson_deny(self, r):
        reason = self.assert_denied(r)
        self.assertIn("No lesson references this signature yet", reason)
        return reason

    # ------------------------------------------------------------------ the rule
    def test_the_first_session_is_told_and_not_refused(self):
        self.fail_then_fix("s1")
        self.assert_allowed(self.probe("s1"))

    def test_the_second_session_is_refused(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        reason = self.assert_lesson_deny(self.probe("s2"))
        self.assertIn("gh pr list --limit <N>", reason)
        self.assertIn("gh: command not found", reason)
        self.assertIn("--repo ContextLab/claude-skill-compounder", reason)
        self.assertIn("skillnote add --lesson %s" % self.sig(), reason)
        self.assertIn("skillrepeat dismiss %s" % self.sig(), reason)
        self.assertIn("lifts the moment either command has been run", reason)

    def test_a_session_that_recovered_nothing_is_never_refused(self):
        """The gate is keyed on a recovery bound in THIS session, so a session that only
        watched the failure happen is not asked to write anything down."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.tick(); self.run_hook(self.failure("gh pr list --limit 5", "s3",
                                                error=self.ERR))
        self.assert_allowed(self.probe("s3"))

    def test_the_threshold_is_REPEAT_MIN_SESSIONS(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.assert_allowed(self.probe("s2", REPEAT_MIN_SESSIONS=3))
        self.fail_then_fix("s3")
        self.assert_lesson_deny(self.probe("s3", REPEAT_MIN_SESSIONS=3))

    # ------------------------------------------------------------------ what lifts it
    def write_lesson_row(self, sig, note_id="n1x1"):
        """The CONTRACT with bin/skillnote: a `note` ledger row carrying `lesson_sig`.
        Written here as a real row in a real file -- the reader under test is this hook,
        and what it reads is a line of JSON on disk whoever put it there.
        tests/test_skillrepeat.py::LiveSkillnoteTest drives the REAL writer into the real
        reader, which is what keeps this shape from becoming its own definition."""
        path = os.path.join(self.state, "ledger.jsonl")
        os.makedirs(self.state, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "note", "action": "add", "ts": self.clock,
                                 "id": note_id, "kind": "note", "scope": "project",
                                 "text": "gh is not on PATH here; curl the API instead.",
                                 "lesson_sig": sig, "session": "cli"}) + "\n")
        return path

    def write_lesson_removal(self, note_id="n1x1"):
        """`skillnote remove <id>` appends this and DELETES NOTHING -- the same append-only
        discipline `forget` and `dismiss` follow. The row carries the note id and not the
        signature, so the join has to be on the id."""
        path = os.path.join(self.state, "ledger.jsonl")
        os.makedirs(self.state, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "note", "action": "remove", "ts": self.clock,
                                 "id": note_id, "session": "cli"}) + "\n")
        return path

    def test_a_lesson_ledger_row_lifts_it(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.write_lesson_row(self.sig())
        self.assert_allowed(self.probe("s2"))

    def test_a_ledger_row_for_another_signature_does_not_lift_it(self):
        """NON-VACUITY: the reader matches on the signature and not on the presence of a
        ledger. A row that names something else leaves the refusal exactly where it was."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.write_lesson_row("c1x1-e1x1")
        self.assert_lesson_deny(self.probe("s2"))

    def test_a_withdrawn_lesson_is_not_a_standing_one(self):
        """The ledger is append-only on both sides: `skillnote remove <id>` appends a
        removal and leaves the add row where it was. A reader matching on `lesson_sig`
        alone would treat a withdrawn lesson as standing while the note itself was gone
        from the CLAUDE.md it was meant to be read from."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.write_lesson_row(self.sig(), note_id="n7x7")
        self.tick()
        self.write_lesson_removal("n7x7")
        self.assert_lesson_deny(self.probe("s2"))

    def test_a_removal_of_a_different_note_leaves_the_lesson_standing(self):
        """NON-VACUITY: the subtraction is by id, not by the presence of any removal."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.write_lesson_row(self.sig(), note_id="n7x7")
        self.write_lesson_removal("n8x8")
        self.assert_allowed(self.probe("s2"))

    def test_a_lesson_withdrawn_after_the_gate_saw_it_does_not_re_arm_this_session(self):
        """A LIMIT, ASSERTED RATHER THAN LEFT TO BE DISCOVERED, and it is the price of the
        marker sweep: once the gate has judged a signature settled it removes the marker,
        so a lesson withdrawn LATER in the same session is not noticed until the next
        session binds a recovery for that signature. The alternative is re-parsing the
        store and the ledger on every remaining tool call of the session, at the cost
        printed by CostTest, to catch a person un-writing a lesson minutes after writing
        it. The window is one session and the deny budget is two, so nothing is lost that
        the next session does not offer again."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.write_lesson_row(self.sig(), note_id="n7x7")
        self.assert_allowed(self.probe("s2", command="npm install a"))
        self.tick()
        self.write_lesson_removal("n7x7")
        self.assert_allowed(self.probe("s2", command="npm install b"))
        # ...and the next session that recovers it is armed again, so this is a delay and
        # not a hole.
        self.fail_then_fix("s3")
        self.assert_lesson_deny(self.probe("s3", command="npm install c"))

    def test_a_row_with_no_action_field_is_read_as_an_add(self):
        """Rows written before `action` existed carry none, and dropping them would
        silently un-record every lesson recorded before that field landed."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        path = os.path.join(self.state, "ledger.jsonl")
        os.makedirs(self.state, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "note", "ts": 1, "id": "nOld",
                                 "lesson_sig": self.sig(),
                                 "text": "an older row"}) + "\n")
        self.assert_allowed(self.probe("s2"))

    def test_a_note_row_with_no_lesson_sig_does_not_lift_it(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        path = os.path.join(self.state, "ledger.jsonl")
        os.makedirs(self.state, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "note", "action": "add", "ts": 1,
                                 "text": "an ordinary note"}) + "\n")
        self.assert_lesson_deny(self.probe("s2"))

    def test_skillrepeat_dismiss_lifts_it(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        r = self.run_cli("dismiss", self.sig(), "--why", "gh is not installed here")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_allowed(self.probe("s2"))

    def test_a_dismissal_suppresses_nothing_it_only_ends_the_demand(self):
        """`dismiss` is not `forget`. Every count the store reports is identical before
        and after one, which is what makes the two commands worth having separately."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        before = json.loads(self.run_cli("list", "--json").stdout)
        self.run_cli("dismiss", self.sig(), "--why", "known")
        after = json.loads(self.run_cli("list", "--json").stdout)
        for key in ("sessions", "failures", "suppressed", "forgotten", "recovery"):
            self.assertEqual([e[key] for e in before], [e[key] for e in after], key)

    def test_a_tombstone_takes_the_count_below_the_threshold(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.tick()
        r = self.run_cli("forget", self.sig(), SKILLREPEAT_NOW=self.clock)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_allowed(self.probe("s2"))

    # ------------------------------------------------------------------ and it lets go
    def test_it_is_capped_at_REPEAT_LESSON_MAX_DENIES(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.assert_lesson_deny(self.probe("s2", command="npm install a"))
        self.assert_lesson_deny(self.probe("s2", command="npm install b"))
        self.assert_allowed(self.probe("s2", command="npm install c"))
        self.assert_allowed(self.probe("s2", command="npm install d"))

    def test_the_cap_is_configurable(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.assert_lesson_deny(self.probe("s2", command="npm install a",
                                           REPEAT_LESSON_MAX_DENIES=1))
        self.assert_allowed(self.probe("s2", command="npm install b",
                                       REPEAT_LESSON_MAX_DENIES=1))

    def test_a_cap_of_zero_refuses_nothing(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.assert_allowed(self.probe("s2", REPEAT_LESSON_MAX_DENIES=0))

    def test_a_double_delivered_pretooluse_refuses_once_and_spends_one(self):
        """Both wirings deliver the same event twice. Two refusals for one call is the
        outcome ranked worse than a missed one, and a duplicate must not eat the budget."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.tick()
        p = self.attempt("npm install left-pad", "s2", tuid="toolu_dup")
        self.assert_lesson_deny(self.run_hook(p))
        self.assert_allowed(self.run_hook(p))
        # ...and the second delivery did not spend the second refusal.
        self.assert_lesson_deny(self.probe("s2", command="npm install other"))

    # ------------------------------------------------------------------ what it spares
    def test_the_two_commands_that_lift_it_are_never_themselves_refused(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        for command in ('skillnote add --lesson %s "gh is missing"' % self.sig(),
                        "skillrepeat dismiss %s --why x" % self.sig(),
                        "bash -c 'skillnote list' && echo ok"):
            self.assert_allowed(self.probe("s2", command=command))

    def test_the_head_allowlists_are_honoured(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        for command in ("cd /tmp", "git status", "ls -la", "jq . x.json",
                        "./run_tests.sh", "pytest tests/", "npm test"):
            self.assert_allowed(self.probe("s2", command=command))
        # NON-VACUITY: the same session, one command off both lists, is refused.
        self.assert_lesson_deny(self.probe("s2", command="npm install left-pad"))

    def test_a_skill_call_is_never_refused_by_it(self):
        """Bash-only, for the reason the repeat arm is Bash-only: neither escape hatch
        exists for a Skill call, and refusing one blocks the mechanism this package
        exists to promote."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt({"skill": "anything"}, "s2",
                                                       tool="Skill")))

    def test_a_call_with_no_tool_use_id_is_not_refused(self):
        """An unclaimed refusal is emitted TWICE under the double delivery both wirings
        produce. The learn arm can afford an unclaimed event and a refusal cannot."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.tick()
        p = self.attempt("npm install left-pad", "s2")
        del p["tool_use_id"]
        self.assert_allowed(self.run_hook(p))

    def test_with_both_refusals_armed_only_one_deny_is_emitted(self):
        """Two rules on one event, and a call can satisfy both. The reason a session gets
        must be ONE object -- two concatenated JSON documents on stdout is not a deny, it
        is a parse error -- so the lesson gate exits the script when it has spoken."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.fail_then_fix("s3")
        self.tick()
        r = self.run_hook(self.attempt("gh pr list --limit 5", "s3"),
                          REPEAT_GATE_REFUSE=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        # One document, not two: json.loads on the whole of stdout is the assertion.
        reason = self.assert_lesson_deny(r)
        self.assertNotIn("already failed in", reason,
                         "the repeat arm's reason was concatenated onto the lesson one")
        # NON-VACUITY: the repeat arm really would have denied this call on its own.
        self.tick()
        self.assertIn("already failed in",
                      self.assert_denied(self.run_hook(
                          self.attempt("gh pr list --limit 5", "s9"),
                          REPEAT_GATE_REFUSE=1)))

    # ------------------------------------------------------------------ the knob
    def test_REPEAT_LESSON_GATE_0_refuses_nothing(self):
        self.fail_then_fix("s1", REPEAT_LESSON_GATE=0)
        self.fail_then_fix("s2", REPEAT_LESSON_GATE=0)
        self.assert_allowed(self.probe("s2", REPEAT_LESSON_GATE=0))

    def test_only_the_literal_zero_switches_it_off(self):
        """The REVERSE spelling from REPEAT_GATE_REFUSE, and deliberately: this knob ships
        ON, so a typo must land on the documented default rather than silently off."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        for value in ("false", "no", "", "00", "1"):
            self.assert_lesson_deny(self.probe("s2", command="npm install %s" % value,
                                               REPEAT_LESSON_GATE=value,
                                               REPEAT_LESSON_MAX_DENIES=99))

    def test_the_off_switch_stops_it_with_everything_else(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        self.assert_allowed(self.probe("s2", SKILL_COMPOUNDER_REPEAT_GATE=0))

    # ------------------------------------------------------------------ fail open
    def test_an_unreadable_ledger_refuses_nothing(self):
        """Fails CLOSED ON DENYING, which is the opposite direction from the store reads:
        a refusal whose escape cannot be verified is a trap."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        path = self.write_lesson_row("something-else")
        os.chmod(path, 0)
        try:
            self.assert_allowed(self.probe("s2"))
        finally:
            os.chmod(path, 0o644)
        # NON-VACUITY: readable again, same store, and it refuses.
        self.assert_lesson_deny(self.probe("s2", command="npm install other"))

    def test_a_ledger_over_the_byte_cap_refuses_nothing(self):
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        path = os.path.join(self.state, "ledger.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x" * 4096)
        self.assert_allowed(self.probe("s2", REPEAT_GATE_MAX_BYTES=2048))

    def test_a_session_that_bound_no_recovery_costs_no_store_read(self):
        """The cheap path, which is the one that matters because this arm ships ON: with
        no `lessons/<sid>` directory the gate leaves on a single `[ -d ]`. Asserted by
        making the store unreadable -- anything that opened it would fail differently --
        and by the marker directory genuinely not existing."""
        self.tick(); self.run_hook(self.failure("gh pr list", "s1", error=self.ERR))
        lessons = os.path.join(self.state, "repeats", "lessons")
        self.assertFalse(os.path.exists(os.path.join(lessons, "s1")), lessons)
        os.chmod(self.store, 0)
        try:
            self.assert_allowed(self.probe("s1"))
        finally:
            os.chmod(self.store, 0o644)

    def test_the_marker_is_spent_and_the_store_is_not_reread_all_session(self):
        """A signature judged unable to qualify has its marker removed, so the next tool
        call in the session does not re-parse the store to reach the same answer."""
        self.fail_then_fix("s1")
        marker_dir = os.path.join(self.state, "repeats", "lessons", "s1")
        self.assertTrue(os.listdir(marker_dir), marker_dir)
        self.assert_allowed(self.probe("s1"))
        self.assertEqual([n for n in os.listdir(marker_dir) if n.startswith("s-")], [],
                         "the marker survived a verdict that cannot change this session")


if __name__ == "__main__":
    unittest.main(verbosity=2)
