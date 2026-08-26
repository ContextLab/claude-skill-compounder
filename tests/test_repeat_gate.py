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
        e = {"PATH": BASE_PATH, "HOME": self.home,
             "SKILL_COMPOUNDER_STATE": self.state,
             "REPEAT_GATE_NOW": str(self.clock)}
        e.update({k: str(v) for k, v in extra.items()})
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
        """Not everything is Bash. An MCP tool failing the same way in two sessions is
        the same defect, and `jq -S` makes key order irrelevant."""
        a = {"owner": "x", "repo": "y"}
        b = {"repo": "y", "owner": "x"}
        self.tick(); self.run_hook(self.failure(a, "s1", tool="mcp__gh__list_prs",
                                                error="Exit code 1\nnot connected"))
        self.tick(); self.run_hook(self.failure(b, "s2", tool="mcp__gh__list_prs",
                                                error="Exit code 1\nnot connected"))
        self.assertEqual(len(self.sigs()), 1, self.sigs())
        self.tick()
        reason = self.assert_denied(self.run_hook(
            self.attempt(b, "s3", tool="mcp__gh__list_prs")))
        self.assertIn("not connected", reason)

    def test_an_interrupted_call_is_not_a_failure(self):
        """A user pressing stop is not the tool being broken. Recording it would teach
        the gate to refuse whatever they interrupted, in every later session."""
        self.tick()
        self.run_hook(self.failure("gh pr list", "s1", is_interrupt=True))
        self.tick()
        self.run_hook(self.failure("gh pr list", "s2", is_interrupt=True))
        self.assertEqual(self.rows(), [])


# ============================================================== recovery capture
class RecoveryTest(GateCase):

    def test_the_first_success_of_the_same_tool_is_recorded_as_the_recovery(self):
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"))
        self.tick(); self.run_hook(self.success("curl -s https://api.github.com/x", "s1"))
        rec = [r for r in self.rows() if r["t"] == "recover"]
        self.assertEqual(len(rec), 1, self.rows())
        self.assertEqual(rec[0]["cmd"], "curl -s https://api.github.com/x")

    def test_only_the_first_success_is_bound(self):
        """One recovery per armed failure. A session that goes on working must not
        attach every later command to the same signature."""
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"))
        self.tick(); self.run_hook(self.success("curl -s https://api.github.com/x", "s1"))
        self.tick(); self.run_hook(self.success("echo done", "s1"))
        self.assertEqual(len([r for r in self.rows() if r["t"] == "recover"]), 1)

    def test_a_success_of_another_tool_does_not_bind(self):
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"))
        self.tick(); self.run_hook(self.success({"file_path": "/a/b.py"}, "s1",
                                                tool="Read"))
        self.assertEqual([r for r in self.rows() if r["t"] == "recover"], [])

    def test_the_window_expires_and_a_late_success_is_not_the_fix(self):
        """The bound that stops an unrelated command twenty steps later from being
        recorded as the fix. Successes of ANY tool consume the window; only a success of
        the SAME tool can claim it."""
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"))
        for i in range(5):
            self.tick()
            self.run_hook(self.success({"file_path": "/a/%d.py" % i}, "s1", tool="Read"))
        self.tick(); self.run_hook(self.success("curl -s https://api.github.com/x", "s1"))
        self.assertEqual([r for r in self.rows() if r["t"] == "recover"], [],
                         "a success six calls after the failure was recorded as the fix")

    def test_inside_the_window_it_is_still_the_fix(self):
        """Non-vacuity for the window test: two intervening calls, same everything else,
        and the recovery IS recorded."""
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"))
        for i in range(2):
            self.tick()
            self.run_hook(self.success({"file_path": "/a/%d.py" % i}, "s1", tool="Read"))
        self.tick(); self.run_hook(self.success("curl -s https://api.github.com/x", "s1"))
        self.assertEqual(len([r for r in self.rows() if r["t"] == "recover"]), 1)

    def test_the_window_is_configurable(self):
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"),
                                   REPEAT_RECOVERY_WINDOW=1)
        self.tick(); self.run_hook(self.success({"file_path": "/a/b.py"}, "s1",
                                                tool="Read"),
                                   REPEAT_RECOVERY_WINDOW=1)
        self.tick(); self.run_hook(self.success("curl -s https://x", "s1"),
                                   REPEAT_RECOVERY_WINDOW=1)
        self.assertEqual([r for r in self.rows() if r["t"] == "recover"], [])

    def test_the_plurality_recovery_appears_in_the_deny_reason(self):
        """Two of three sessions used curl; one used something else. The refusal names
        the one the plurality agreed on, and says how many sessions that was."""
        for s, fix in (("s1", "curl -s https://api.github.com/repos/a/b/pulls"),
                       ("s2", "curl -s https://api.github.com/repos/c/d/pulls"),
                       ("s3", "python3 -c import urllib")):
            self.tick(); self.run_hook(self.failure("gh pr list", s))
            self.tick(); self.run_hook(self.success(fix, s))
        self.tick()
        reason = self.assert_denied(self.run_hook(self.attempt("gh pr list", "s9")))
        self.assertIn("what worked instead, in 2 of them", reason)
        self.assertIn("curl -s https://api.github.com/repos", reason)
        self.assertNotIn("python3", reason)

    def test_a_tie_names_no_recovery(self):
        """Announcing one of two equally-supported commands as `what worked` would be an
        invention, and this store's whole value is that it never invents."""
        for s, fix in (("s1", "curl -s https://one.example/a"),
                       ("s2", "python3 -c import_urllib")):
            self.tick(); self.run_hook(self.failure("gh pr list", s))
            self.tick(); self.run_hook(self.success(fix, s))
        self.tick()
        reason = self.assert_denied(self.run_hook(self.attempt("gh pr list", "s9")))
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
        # belongs where the refusal is decided, on the whole record.
        self.assertEqual(len([r for r in self.rows() if r["t"] == "recover"]), 2)
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "f3")))

    def test_a_self_recovery_does_not_get_named_even_beside_a_real_one(self):
        """Two sessions retried the identical call and it worked; a third found a genuine
        different command. The identical call must not be named, and the one session that
        proved the call can work is enough to stop the refusal."""
        net = "Exit code 1\nerror connecting to api.github.com: connection reset"
        for s, fix in (("f1", "gh pr list"), ("f2", "gh pr list"),
                       ("f3", "curl -s https://api.github.com/repos/a/b/pulls")):
            self.tick(); self.run_hook(self.failure("gh pr list", s, error=net))
            self.tick(); self.run_hook(self.success(fix, s))
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "f9")))

    def test_a_genuine_different_command_is_still_named(self):
        """Non-vacuity for both tests above: with the recoveries genuinely different from
        the failing call, the very same shape still refuses and still names the fix."""
        net = "Exit code 1\nerror connecting to api.github.com: connection reset"
        for s in ("f1", "f2"):
            self.tick(); self.run_hook(self.failure("gh pr list", s, error=net))
            self.tick()
            self.run_hook(self.success("curl -s https://api.github.com/repos/a/b/pulls", s))
        self.tick()
        reason = self.assert_denied(self.run_hook(self.attempt("gh pr list", "f3")))
        self.assertIn("what worked instead, in 2 of them", reason)
        self.assertIn("curl -s https://api.github.com/repos", reason)
        self.assertNotIn("\n  gh pr list", reason)

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
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"))
        self.tick()
        p = self.success("curl -s https://x/y", "s1", tuid="toolu_same_s")
        self.run_hook(p)
        self.run_hook(p)
        self.assertEqual(len([r for r in self.rows() if r["t"] == "recover"]), 1,
                         self.rows())

    def test_a_repeated_success_event_consumes_the_window_only_once(self):
        """The subtler half. A double-delivered success that decremented the window
        twice would halve REPEAT_RECOVERY_WINDOW silently, which is exactly the defect
        the claim exists to prevent -- and it would be invisible, because the recovery
        row count would still look right."""
        self.tick(); self.run_hook(self.failure("gh pr list", "s1"))
        for i in range(2):
            self.tick()
            p = self.success({"file_path": "/a/%d.py" % i}, "s1", tool="Read",
                             tuid="toolu_read_%d" % i)
            self.run_hook(p)
            self.run_hook(p)          # the duplicate delivery
        self.tick(); self.run_hook(self.success("curl -s https://x/y", "s1"))
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
class WiringTest(unittest.TestCase):
    """The matcher is a REGEX over the tool name, and it is `Bash|Skill` on all three
    events in BOTH install paths. Measured 2026-08-26 on 2.1.246: of eight matchers on one
    event, `Bash`, `^Ba`, `Ba.*`, `Bash|mcp__.*`, `*` and `.*` all received a `Bash` call;
    `Ba` and `as` received nothing.

    That wiring is a deliberate cost bound -- this hook forks on every delivery and the
    read tools are the high-frequency ones -- and it is also the ONLY thing protecting
    Read/Glob/Grep from this gate. An in-script allowlist for them was a guard with no live
    path: the event is never delivered, so the case arm could never run. This asserts the
    wiring is what the script's header says it is, and that no such dead allowlist has
    grown back."""

    EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure")

    def test_both_install_paths_wire_the_gate_to_bash_and_skill_only(self):
        seen = {}
        with open(os.path.join(REPO, "hooks", "hooks.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        for event, groups in manifest["hooks"].items():
            for group in groups:
                for hook in group.get("hooks", []):
                    if "repeat-gate.sh" in hook.get("command", ""):
                        seen[event] = group.get("matcher")
        self.assertEqual(sorted(seen), sorted(self.EVENTS), seen)
        for event in self.EVENTS:
            self.assertEqual(seen[event], "Bash|Skill", seen)

        with open(os.path.join(REPO, "skill_compounder", "installer.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('REPEAT_MATCHER = "Bash|Skill"', src,
                      "the installer and the plugin manifest disagree about the matcher")

    def test_the_gate_carries_no_allowlist_for_a_tool_it_can_never_receive(self):
        """A `case "$tool" in Read|Glob|Grep) exit 0` arm cannot fire under `Bash|Skill`.
        Shipping a safety check nobody can reach is the defect skills/dead-guard-detection
        exists for, and re-adding one must fail here rather than read as caution."""
        with open(HOOK, encoding="utf-8") as fh:
            body = [ln for ln in fh if not ln.lstrip().startswith("#")]
        for line in body:
            if line.lstrip().startswith("case ") and '"$tool"' in line:
                self.fail("the gate dispatches on $tool outside a comment, which the "
                          "`Bash|Skill` matcher makes dead code: %r" % line.strip())

    def test_the_header_describes_the_wiring_it_actually_has(self):
        """Prose that contradicts the wiring is how the dead guard got justified for three
        header lines. The recovery window counts what this hook is WIRED for, and the
        structured-tool path is unreachable until someone widens the matcher."""
        with open(HOOK, encoding="utf-8") as fh:
            head = fh.read()
        self.assertFalse("successful tool calls, of any tool" in head,
                         "the window is documented as counting a stream it never sees")
        self.assertIn("Bash|Skill", head,
                      "the header never names the wiring it is describing")
        self.assertIn("UNREACHABLE ON THE CURRENT WIRING", head,
                      "norm_structured has no production producer and must say so")
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


# ============================================================== the CLI
class CliTest(GateCase):

    def seed(self):
        for s, fix in (("s1", "curl -s https://api.github.com/repos/a/b/pulls"),
                       ("s2", "curl -s https://api.github.com/repos/c/d/pulls")):
            self.tick(); self.run_hook(self.failure("gh pr list", s))
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
        self.assertIn("curl -s https://api.github.com/repos", got[0]["recovery"])

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
        for sess, fix in (("d1", "gh pr list --json url"), ("d2", "gh pr status")):
            self.tick(); self.run_hook(self.failure("gh pr view 1", sess))
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
                              ("GATE", "(if .transient_sessions")):
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
        self.assertIn("curl -s https://api.github.com/repos/a/b/pulls", r.stdout)
        self.assertIn("curl -s https://api.github.com/repos/c/d/pulls", r.stdout)

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
        self.assert_denied(self.run_hook(self.attempt("gh pr list", "s8")))
        self.run_cli("forget", sig, SKILLREPEAT_NOW=self.tick(100))
        self.tick()
        self.assert_allowed(self.run_hook(self.attempt("gh pr list", "s9")))
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
