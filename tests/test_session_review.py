#!/usr/bin/env python3
"""hooks/session-review.sh -- the automatic, deterministic dispatch.

Real scripts through subprocess, real files on disk, no mocks. Every call passes
``input=`` or ``stdin=DEVNULL``: a hook reads its payload with ``payload="$(cat)"`` and
hangs forever otherwise.

WHAT IS AND IS NOT ASSERTED HERE, stated plainly so nobody mistakes the coverage.

Everything up to the model call is exercised for real: every gate, the claim/lock/cooldown
state machine, the digest, the read surface, and the recursion barrier. The model call
itself is NOT exercised, and no stub stands in for it -- a fake ``claude`` on PATH would
turn "the dispatch works" into "our fake works", which is the failure this repo bans
mocks to avoid.

The end-to-end run was performed by hand against the real CLI on 2026-08-25 (CLI 2.1.245,
macOS 25.5.0) and its numbers are the ones quoted in hooks/session-review.sh:

    $0.191, 49s wall, sonnet, 60000-byte digest, verdict CANDIDATE with verbatim
    quotes from the transcript it was given.

and the non-blocking measurement, from a live headless session whose Stop hook launched a
detached ``claude -p``:

    hook body 3ms; parent turn 4.88s dispatching against a 6.04s baseline on the same
    prompt.

Neither number is reproducible in a test run without spending the user's quota on every
``./run_tests.sh``, which is exactly what test_never_fires_from_this_test_suite exists to
prevent.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REVIEW = REPO / "hooks" / "session-review.sh"
CAPTURE = REPO / "hooks" / "insight-capture.sh"
INSIGHT = REPO / "bin" / "skillinsight"

# Minimal PATH, exactly as the rest of the suite uses. Note what is NOT on it: the
# `claude` CLI lives in ~/.local/bin on the machine this was written on, and nowhere at
# all on a GitHub Actions runner.
PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

NOW = 1787616000  # 2026-08-25T00:00:00Z, inside ISO week 2026-W35

# Exit codes are the contract a test asserts on. Greping the prose breaks whenever the
# prose is improved, which is a false failure and teaches people to weaken tests.
OFF, RECURSION, CI_ENV, TEST_STATE = 10, 11, 12, 13
NO_CLI, BAD_ARGV, CLAIMED, LOCKED, COOLDOWN = 14, 15, 16, 17, 18
UNWRITABLE, NO_DIGEST = 19, 20


def assistant_record(**parts):
    """One real transcript line of the shape the digest reads."""
    return json.dumps({
        "type": "assistant",
        "isSidechain": False,
        "message": {"role": "assistant", "content": [parts]},
    })


class SessionReviewBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="session-review-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = Path(self.tmp) / "state"
        self.state.mkdir(parents=True)
        self.transcript = Path(self.tmp) / "transcript.jsonl"
        self.transcript.write_text(
            assistant_record(type="text", text="I fixed the parser.") + "\n"
            + assistant_record(type="tool_use", name="Edit", input={
                "file_path": "/repo/a.py", "old_string": "foo", "new_string": "bar"}) + "\n"
        )

    def env(self, **extra):
        e = {
            "PATH": PATH,
            "HOME": self.tmp,
            "SKILL_COMPOUNDER_STATE": str(self.state),
            "SKILL_COMPOUNDER_REVIEW_NOW": str(NOW),
        }
        e.update(extra)
        return e

    def run_review(self, env=None, sid="sess-1", transcript=None, audit_hash=""):
        return subprocess.run(
            [str(REVIEW), sid, self.tmp,
             str(transcript if transcript is not None else self.transcript),
             self.tmp, audit_hash],
            env=env if env is not None else self.env(),
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60,
        )


class GateTest(SessionReviewBase):
    """Each gate, in isolation, against the real script."""

    def test_off_switch_stops_everything(self):
        r = self.run_review(self.env(SKILL_COMPOUNDER_REVIEW="0"))
        self.assertEqual(r.returncode, OFF)
        self.assertFalse((self.state / "reviews").exists(),
                         "the off switch must not even create the state directory")

    def test_recursion_barrier_refuses_before_reading_any_file(self):
        """SKILL_COMPOUNDER_DISPATCHED is set on every process this script starts.

        This is the barrier that stops a dispatched session's own Stop hook from
        dispatching again, and it is checked before anything touches the disk so that it
        holds even when the state directory is unwritable or gone.
        """
        env = self.env(SKILL_COMPOUNDER_DISPATCHED="1",
                       SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1")
        r = self.run_review(env)
        self.assertEqual(r.returncode, RECURSION)
        self.assertFalse((self.state / "reviews").exists())

    def test_recursion_barrier_survives_a_missing_state_directory(self):
        shutil.rmtree(self.state)
        env = self.env(SKILL_COMPOUNDER_DISPATCHED="1",
                       SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1")
        self.assertEqual(self.run_review(env).returncode, RECURSION)

    def test_every_ci_marker_refuses(self):
        for var in ("CI", "GITHUB_ACTIONS", "CONTINUOUS_INTEGRATION",
                    "PYTEST_CURRENT_TEST", "SKILL_COMPOUNDER_TEST"):
            with self.subTest(var=var):
                env = self.env(SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1")
                env[var] = "1"
                r = self.run_review(env, sid="sess-" + var)
                self.assertEqual(r.returncode, CI_ENV)
                self.assertIn(var, r.stderr)

    def test_redirected_state_refuses_without_the_explicit_override(self):
        """Every test in this repo redirects SKILL_COMPOUNDER_STATE at a temp dir.

        Treating that as "this is not a real session" is what makes a test file nobody
        has written yet safe by default, rather than safe only if its author remembers.
        """
        self.assertEqual(self.run_review().returncode, TEST_STATE)

    def test_a_state_root_outside_a_temp_directory_is_not_treated_as_a_test(self):
        """README.md documents SKILL_COMPOUNDER_STATE as a user knob for relocating
        state. Refusing on the variable being set at all disabled this feature
        permanently and silently for anyone who used it as documented.
        """
        home_state = Path(self.tmp) / "notatemp"
        home_state.mkdir()
        env = self.env(SKILL_COMPOUNDER_STATE=str(home_state))
        # self.tmp IS under a temp dir here, so force the non-temp branch by asserting on
        # the code path with a path that is not: use the repo's own tests fixtures dir.
        env["SKILL_COMPOUNDER_STATE"] = str(REPO / "tests" / "fixtures" / "_state_probe")
        r = subprocess.run([str(REVIEW), "nt-1", self.tmp, str(self.transcript), self.tmp],
                           env=env, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertNotEqual(r.returncode, TEST_STATE,
                            "a state root outside a temp directory is a real user's")
        self.assertEqual(r.returncode, NO_CLI, "it should reach the CLI gate")
        # Nothing may be created: the CLI gate is before any mkdir.
        self.assertFalse((REPO / "tests" / "fixtures" / "_state_probe").exists())

    def test_a_temp_state_root_refuses_even_when_the_variable_is_unset(self):
        """The discriminator is the directory, so HOME under a temp dir is caught too."""
        env = {"PATH": PATH, "HOME": self.tmp,
               "SKILL_COMPOUNDER_REVIEW_NOW": str(NOW)}
        r = subprocess.run([str(REVIEW), "t-1", self.tmp, str(self.transcript), self.tmp],
                           env=env, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, TEST_STATE)

    def test_missing_transcript_refuses(self):
        env = self.env(SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1")
        r = self.run_review(env, transcript=Path(self.tmp) / "nope.jsonl")
        self.assertIn(r.returncode, (NO_CLI, BAD_ARGV))

    def test_empty_session_id_refuses(self):
        env = self.env(SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1")
        r = subprocess.run([str(REVIEW), "", self.tmp, str(self.transcript), self.tmp],
                           env=env, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertIn(r.returncode, (NO_CLI, BAD_ARGV))


class NeverInCiTest(SessionReviewBase):
    """The guarantee that ./run_tests.sh and GitHub Actions cannot fire this.

    Four independent reasons, any one of which is sufficient. They are asserted
    separately because a guarantee that rests on one mechanism is a guarantee that
    disappears the day somebody changes that mechanism.
    """

    def test_never_fires_from_this_test_suite(self):
        """Run it with exactly the environment every test file in this repo uses."""
        r = self.run_review()
        self.assertEqual(r.returncode, TEST_STATE)
        self.assertFalse((self.state / "reviews").exists())

    def test_the_ci_env_alone_is_sufficient(self):
        env = self.env(SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1", GITHUB_ACTIONS="true")
        self.assertEqual(self.run_review(env).returncode, CI_ENV)

    def test_no_cli_on_the_test_path_is_sufficient(self):
        """With every env gate lifted, the minimal PATH still has nothing to dispatch.

        This is the reason a GitHub Actions runner could not fire this even if every
        other gate were deleted: there is no `claude` binary and no credential on it.
        """
        env = self.env(SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1")
        self.assertIsNone(shutil.which("claude", path=PATH),
                          "the suite's minimal PATH must not carry a claude CLI")
        r = self.run_review(env)
        self.assertEqual(r.returncode, NO_CLI)

    def test_the_capture_hook_creates_no_reviews_under_a_test_environment(self):
        """The whole Stop path, end to end, under the suite's own environment.

        A payload that crosses the audit threshold, so the dispatch really is attempted,
        and nothing is left behind.
        """
        reminders = self.state / "reminders"
        reminders.mkdir(parents=True)
        sid = "cap-sess-1"
        (reminders / f"{sid}.edits").write_text("x" * 40)
        (reminders / f"{sid}.paths").write_text(
            "\n".join(f"/repo/f{i}.py" for i in range(12)) + "\n")
        payload = json.dumps({
            "session_id": sid, "cwd": self.tmp,
            "transcript_path": str(self.transcript),
            "hook_event_name": "Stop", "last_assistant_message": "done",
        })
        r = subprocess.run([str(CAPTURE)], input=payload, env=self.env(INSIGHT_NOW=str(NOW)),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "", "a capture hook must never write to stdout")
        # The audit arm must still have done its job; only the dispatch is suppressed.
        queue = self.state / "insights" / "2026-W35.jsonl"
        self.assertTrue(queue.exists(), "the session audit must still write its record")
        self.assertIn("session-audit", queue.read_text())
        # Give a detached child that should not exist time to prove it does not exist.
        time.sleep(1.0)
        self.assertFalse((self.state / "reviews").exists(),
                         "no dispatch may leave state behind under a test environment")


class ThrottleTest(SessionReviewBase):
    """Claim, lock and cooldown -- the three throttles, each proven separately."""

    def live_env(self, **extra):
        # /bin/cat is not a stub claude and nothing below asserts a dispatch succeeded.
        # It is here only to get past the "is there a CLI" gate, which sits in front of
        # the three throttles this class is about. Every assertion is on a refusal that
        # happens before any CLI is executed.
        return self.env(SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1",
                        SKILL_COMPOUNDER_REVIEW_CLAUDE="/bin/cat", **extra)

    def reviews(self):
        d = self.state / "reviews"
        (d / ".claims").mkdir(parents=True, exist_ok=True)
        return d

    def test_a_session_is_dispatched_at_most_once_ever(self):
        self.reviews()
        (self.state / "reviews" / ".claims" / "sess-1").mkdir()
        r = self.run_review(self.live_env(), sid="sess-1")
        self.assertEqual(r.returncode, CLAIMED)

    def test_the_session_id_is_sanitised_the_same_way_the_other_hooks_do_it(self):
        """A slash in a session id must not become a subdirectory.

        hooks/compound-improvement.sh and hooks/insight-capture.sh both apply
        `tr -c 'A-Za-z0-9._-' '_' | cut -c1-96`. If this script applied a different
        expression the claim would be filed under a name no other arm ever looks at,
        and the session would be dispatched again on the next Stop.
        """
        self.reviews()
        (self.state / "reviews" / ".claims" / "a_b_c").mkdir()
        r = self.run_review(self.live_env(), sid="a/b:c")
        self.assertEqual(r.returncode, CLAIMED)

    def test_a_held_lock_refuses(self):
        d = self.reviews()
        (d / ".lock").mkdir()
        r = self.run_review(self.live_env(), sid="fresh")
        self.assertEqual(r.returncode, LOCKED)

    def test_a_stale_lock_is_broken_rather_than_blocking_forever(self):
        d = self.reviews()
        (d / ".lock").mkdir()
        old = NOW - 100000  # older than the 5400s default TTL
        os.utime(d / ".lock", (old, old))
        (d / ".last-dispatch").write_text(str(NOW))  # so it stops at the next gate
        r = self.run_review(self.live_env(), sid="fresh")
        self.assertEqual(r.returncode, COOLDOWN,
                         "a stale lock must be broken, not treated as held")

    def test_the_lock_is_released_on_every_exit_path(self):
        d = self.reviews()
        (d / ".last-dispatch").write_text(str(NOW))
        self.assertEqual(self.run_review(self.live_env(), sid="s2").returncode, COOLDOWN)
        self.assertFalse((d / ".lock").exists(),
                         "a refused dispatch must not leave the global lock held")

    def test_the_cooldown_holds_for_the_configured_window(self):
        d = self.reviews()
        (d / ".last-dispatch").write_text(str(NOW - 3600))
        r = self.run_review(self.live_env(), sid="s3")
        self.assertEqual(r.returncode, COOLDOWN)
        self.assertIn("75600", r.stderr, "the default window is 21 hours")

    def test_a_cooldown_stamp_from_the_future_does_not_silence_the_trigger(self):
        """One bad clock reading must not disable the dispatch permanently.

        The queue nudge in hooks/compound-improvement.sh was measured going silent for
        ten years from a single future stamp. Same trap, same treatment: an impossible
        stamp reads as no stamp.
        """
        d = self.reviews()
        (d / ".last-dispatch").write_text(str(NOW + 315360000))  # ten years ahead
        r = self.run_review(self.live_env(), sid="s4")
        self.assertNotEqual(r.returncode, COOLDOWN)

    def test_a_backwards_running_clock_does_not_get_a_free_dispatch(self):
        """A one-sided `NOW - last` hands a clock that moves backwards one dispatch per
        step. A reviewer walked it back in one-second steps and got four dispatches in
        four seconds, each ratcheting the stamp further back. The comparison is on the
        absolute difference, so a move of less than the cooldown in EITHER direction is
        inside the window.
        """
        d = self.reviews()
        (d / ".last-dispatch").write_text(str(NOW))
        env = self.live_env()
        env["SKILL_COMPOUNDER_REVIEW_NOW"] = str(NOW - 1)
        r = subprocess.run([str(REVIEW), "back-1", self.tmp, str(self.transcript), self.tmp],
                           env=env, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, COOLDOWN)

    def test_a_gap_larger_than_the_cooldown_in_either_direction_still_dispatches(self):
        """The other half: one bad clock reading must not silence the trigger forever."""
        d = self.reviews()
        (d / ".last-dispatch").write_text(str(NOW + 315360000))  # ten years ahead
        self.assertNotEqual(self.run_review(self.live_env(), sid="fwd-1").returncode,
                            COOLDOWN)

    def test_a_failed_report_write_still_records_the_dispatch(self):
        """A dispatch that spends the quota and cannot write its report used to leave the
        cooldown stamped, no index line, no announcement, and nothing to find -- the
        exact silent failure this whole arm exists to make impossible, reproduced inside
        the arm itself. The report and the index are separate files and separate failure
        modes.
        """
        d = self.reviews()
        week_dir = d / "2026-W35"
        week_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(week_dir, 0o500)
        self.addCleanup(os.chmod, week_dir, 0o700)
        r = self.run_review(self.live_env(), sid="unwritable")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue((d / "index.jsonl").exists(),
                        "the dispatch must be recorded even when the report is not")
        rec = json.loads((d / "index.jsonl").read_text().strip().splitlines()[-1])
        self.assertEqual(rec["verdict"], "ERROR")
        self.assertIn("could not be written", rec["report"])
        self.assertTrue((d / ".unread").exists(),
                        "a failure a person is never told about is a silent failure")

    def test_a_session_refused_by_the_cooldown_keeps_its_claim_for_later(self):
        """Qualifying sessions cluster; the busiest days here had three.

        Burning the claim on a refusal meant the trigger always reviewed the FIRST
        session of a 21-hour window and silently dropped every later one.
        """
        d = self.reviews()
        (d / ".last-dispatch").write_text(str(NOW))
        self.assertEqual(self.run_review(self.live_env(), sid="deferred").returncode,
                         COOLDOWN)
        self.assertFalse((d / ".claims" / "deferred").exists(),
                         "a session the cooldown refused must not have spent its claim")
        # ... and once the window opens it is dispatched rather than reported as done.
        self.assertNotEqual(self.run_review(self.live_env(), sid="deferred").returncode,
                            CLAIMED)

    def test_a_frozen_CI_NOW_does_not_silence_the_trigger(self):
        """CI_NOW is what the suite freezes for the other hooks. If this script read it,
        `NOW - last` would be 0 forever and the trigger would never fire again."""
        d = self.reviews()
        env = self.live_env()
        env["CI_NOW"] = str(NOW)
        del env["SKILL_COMPOUNDER_REVIEW_NOW"]
        first = subprocess.run([str(REVIEW), "ci1", self.tmp, str(self.transcript), self.tmp],
                               env=env, capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=60)
        self.assertNotEqual(first.returncode, COOLDOWN)
        stamped = int((d / ".last-dispatch").read_text())
        self.assertNotEqual(stamped, NOW,
                            "the clock must come from date(1), not from CI_NOW")

    def test_the_cooldown_is_stamped_before_the_model_is_called(self):
        """Recursion barrier 3, and the reason two Stops a second apart cannot both fire.

        The run below is refused at the CLI gate, which is AFTER the stamp is written.
        A stamp written only on success would leave the whole dispatch window open.
        """
        d = self.reviews()
        self.run_review(self.live_env(), sid="s5")
        self.assertTrue((d / ".last-dispatch").exists())
        self.assertEqual((d / ".last-dispatch").read_text(), str(NOW))
        # ... and a second session immediately after is inside the window.
        self.assertEqual(self.run_review(self.live_env(), sid="s6").returncode, COOLDOWN)


class DigestTest(SessionReviewBase):
    """The transcript read is bounded, and reads the same records insight-capture does.

    These point SKILL_COMPOUNDER_REVIEW_CLAUDE at /bin/cat. That is NOT a stub claude and
    nothing here pretends it is: it exists only to get past the "is there a CLI" gate so
    that the digest gate behind it is exercised, and every assertion below is about the
    digest. The dispatch that follows genuinely fails and the report says so.
    """

    def live_env(self, **extra):
        e = self.env(SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1",
                     SKILL_COMPOUNDER_REVIEW_CLAUDE="/bin/cat")
        e.update(extra)
        return e

    def test_a_transcript_with_no_assistant_records_yields_no_digest(self):
        """Refusing beats dispatching a model against an empty prompt."""
        t = Path(self.tmp) / "empty.jsonl"
        t.write_text(json.dumps({"type": "user", "message": {"role": "user",
                                                             "content": "hi"}}) + "\n")
        r = self.run_review(self.live_env(), sid="d1", transcript=t)
        self.assertEqual(r.returncode, NO_DIGEST)

    def test_attachment_records_are_not_digested(self):
        """584 of 854 marker hits in the wild rode in `attachment` records.

        Those are the output-style plugin's own instruction echoed back. A reviewer fed
        those is reviewing our own prompt.
        """
        t = Path(self.tmp) / "attach.jsonl"
        t.write_text(json.dumps({
            "type": "attachment",
            "attachment": {"type": "hook_additional_context",
                           "content": "In order to encourage learning"},
        }) + "\n")
        r = self.run_review(self.live_env(), sid="d2", transcript=t)
        self.assertEqual(r.returncode, NO_DIGEST)

    def test_sidechain_records_are_not_digested(self):
        t = Path(self.tmp) / "side.jsonl"
        t.write_text(json.dumps({
            "type": "assistant", "isSidechain": True,
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": "subagent talking"}]},
        }) + "\n")
        r = self.run_review(self.live_env(), sid="d3", transcript=t)
        self.assertEqual(r.returncode, NO_DIGEST)

    def test_a_large_transcript_is_read_in_bounded_time(self):
        """The largest real transcript on the research machine was 663 MB.

        `tail -c` seeks, so the cost is the bound and not the file. 24 MB here is enough
        to catch a read that walks the whole file: an unbounded jq over it takes tens of
        seconds, and the assertion below is 20.
        """
        big = Path(self.tmp) / "big.jsonl"
        line = assistant_record(type="text", text="x" * 900) + "\n"
        with big.open("w") as fh:
            for _ in range(24000):
                fh.write(line)
        self.assertGreater(big.stat().st_size, 20 * 1024 * 1024)
        started = time.monotonic()
        # Refused at the CLI gate, which is after the transcript is opened but before
        # the digest -- so run it with the digest reached instead, by giving it a CLI.
        r = subprocess.run(
            [str(REVIEW), "d4", self.tmp, str(big), self.tmp],
            env=self.live_env(), capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=120)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 20.0,
                        f"the bounded read took {elapsed:.1f}s; it must not scale with "
                        "the transcript")
        # /bin/cat is not a claude CLI, so the dispatch cannot succeed. What matters
        # here is only that it got PAST the digest, i.e. the digest was non-empty.
        self.assertNotEqual(r.returncode, NO_DIGEST)


class ReadSurfaceTest(SessionReviewBase):
    """`skillinsight reviews` -- where a person or a later session reads the findings.

    The fixtures below are real files in the shape a real dispatch writes, produced by
    hand. They are data, not a stand-in implementation: nothing here fakes the dispatcher.
    """

    def setUp(self):
        super().setUp()
        self.reviews = self.state / "reviews" / "2026-W35"
        self.reviews.mkdir(parents=True)
        self.none_report = self.reviews / "aaa.md"
        self.none_report.write_text("# Session review\n\nVERDICT: NONE\nWHY: just bugs.\n")
        self.cand_report = self.reviews / "bbb.md"
        self.cand_report.write_text("# Session review\n\nVERDICT: CANDIDATE foo-bar\n")
        idx = self.state / "reviews" / "index.jsonl"
        idx.write_text(
            json.dumps({"ts": "2026-08-24T01:00:00Z", "week": "2026-W35",
                        "session": "aaa", "project": "/p/one", "verdict": "NONE",
                        "name": "", "report": str(self.none_report),
                        "cost_usd": "0.18", "model": "sonnet", "stage": "analysis"}) + "\n"
            + json.dumps({"ts": "2026-08-25T01:00:00Z", "week": "2026-W35",
                          "session": "bbb", "project": "/p/two", "verdict": "CANDIDATE",
                          "name": "foo-bar", "report": str(self.cand_report),
                          "cost_usd": "0.19", "model": "sonnet", "stage": "analysis"}) + "\n"
        )
        self.index = idx

    def insight(self, *args):
        return subprocess.run([str(INSIGHT), *args], env=self.env(INSIGHT_NOW=str(NOW)),
                              capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60)

    def test_reviews_lists_newest_first_and_reports_the_none_verdicts_too(self):
        r = self.insight("reviews")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("automatic session reviews: 2", r.stdout)
        # Newest first.
        self.assertLess(r.stdout.index("CANDIDATE"), r.stdout.index("NONE      "))
        self.assertIn("NONE is the expected verdict", r.stdout)
        self.assertIn("nothing in here has been forged or installed", r.stdout)

    def test_show_prints_the_nth_newest_in_full(self):
        self.assertIn("CANDIDATE foo-bar", self.insight("reviews", "--show", "1").stdout)
        self.assertIn("WHY: just bugs.", self.insight("reviews", "--show", "2").stdout)

    def test_a_half_written_index_line_loses_nothing_before_it(self):
        """The dispatcher appends from another process with no lock in between."""
        with self.index.open("a") as fh:
            fh.write('{"ts":"2026-08-26T01:00:00Z","verdi')
        r = self.insight("reviews")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("automatic session reviews: 2", r.stdout)
        self.assertIn("foo-bar", r.stdout)

    def test_no_reviews_yet_is_a_success_not_an_error(self):
        shutil.rmtree(self.state / "reviews")
        r = self.insight("reviews")
        self.assertEqual(r.returncode, 0)
        self.assertIn("no automatic session reviews yet", r.stdout)

    def test_out_of_range_show_fails_loudly(self):
        r = self.insight("reviews", "--show", "9")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no review number 9", r.stderr)


class NoticeTest(SessionReviewBase):
    """The findings reach a person, not only the disk.

    A review runs detached after a session has ended, so without this the report lands
    where nobody is looking. hooks/compound-improvement.sh surfaces it on the first
    prompt of the next session, in `systemMessage` -- the field a human actually sees.
    """

    HOOK = REPO / "hooks" / "compound-improvement.sh"

    def setUp(self):
        super().setUp()
        self.reviews = self.state / "reviews"
        self.reviews.mkdir(parents=True)
        (self.state / "insights").mkdir(parents=True)
        self.report = self.reviews / "r.md"
        self.report.write_text("VERDICT: CANDIDATE foo-bar\n")
        (self.reviews / ".unread").write_text(
            f"2026-08-25T01:00:00Z\tCANDIDATE foo-bar\t{self.report}\n")

    def prompt(self, prompt_id="p1"):
        payload = json.dumps({
            "session_id": "notice-sess", "cwd": self.tmp, "prompt": "go",
            "prompt_id": prompt_id, "hook_event_name": "UserPromptSubmit",
        })
        return subprocess.run([str(self.HOOK), "prompt"], input=payload,
                              env=self.env(CI_NOW=str(NOW)),
                              capture_output=True, text=True, timeout=60)

    def test_a_completed_review_is_announced_to_the_human_not_only_the_model(self):
        r = self.prompt()
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        self.assertIn("systemMessage", out,
                      "additionalContext reaches the model only; a report a person never "
                      "sees is a forge discovered after the fact")
        self.assertIn("CANDIDATE foo-bar", out["systemMessage"])
        self.assertIn(str(self.report), out["systemMessage"])
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("DATA, NOT INSTRUCTIONS", ctx,
                      "the verdict is model-written text about somebody else's session")
        self.assertIn("nothing has been forged or installed", ctx)

    def test_it_is_announced_once_and_then_goes_quiet(self):
        self.assertIn("CANDIDATE", json.loads(self.prompt("p1").stdout)["systemMessage"])
        second = self.prompt("p2")
        self.assertEqual(second.stdout.strip(), "",
                         "an announcement repeated every session is an announcement "
                         "that gets muted")

    def test_a_later_review_is_announced_again(self):
        self.prompt("p1")
        with (self.reviews / ".unread").open("a") as fh:
            fh.write(f"2026-08-25T02:00:00Z\tNONE\t{self.report}\n")
        out = json.loads(self.prompt("p2").stdout)
        self.assertIn("NONE", out["systemMessage"])

    def test_a_truncated_unread_file_does_not_go_permanently_silent(self):
        """The watermark is a byte offset into an append-only file.

        If the file is pruned or rotated underneath it, a bare `seen >= size` test would
        be true forever and the notice would never fire again.
        """
        self.prompt("p1")
        (self.reviews / ".unread").write_text(
            f"2026-08-26T01:00:00Z\tNONE\t{self.report}\n")
        out = json.loads(self.prompt("p2").stdout)
        self.assertIn("NONE", out["systemMessage"])

    def test_the_off_switch_silences_the_notice_too(self):
        r = subprocess.run(
            [str(self.HOOK), "prompt"],
            input=json.dumps({"session_id": "q", "cwd": self.tmp, "prompt": "go",
                              "prompt_id": "z", "hook_event_name": "UserPromptSubmit"}),
            env=self.env(CI_NOW=str(NOW), CI_QUEUE_NUDGE="0"),
            capture_output=True, text=True, timeout=60)
        self.assertNotIn("CANDIDATE", r.stdout)


class DispatchWiringTest(SessionReviewBase):
    """hooks/insight-capture.sh launches the dispatcher, and never blocks doing it."""

    def stop_payload(self, sid="wire-1"):
        return json.dumps({
            "session_id": sid, "cwd": self.tmp,
            "transcript_path": str(self.transcript),
            "hook_event_name": "Stop", "last_assistant_message": "done",
        })

    def prime_audit(self, sid="wire-1"):
        reminders = self.state / "reminders"
        reminders.mkdir(parents=True, exist_ok=True)
        (reminders / f"{sid}.edits").write_text("x" * 40)
        (reminders / f"{sid}.paths").write_text(
            "\n".join(f"/repo/f{i}.py" for i in range(12)) + "\n")

    def test_the_stop_hook_returns_immediately(self):
        """It must not wait for the dispatcher, and must not hold its descriptors.

        A child left holding the hook's inherited stdout pipe keeps the reader blocked
        until the child exits -- which is how a "detached" hook stalls a turn anyway.
        `capture_output=True` below IS that pipe.
        """
        self.prime_audit()
        started = time.monotonic()
        r = subprocess.run([str(CAPTURE)], input=self.stop_payload(),
                           env=self.env(INSIGHT_NOW=str(NOW),
                                        SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1"),
                           capture_output=True, text=True, timeout=30)
        elapsed = time.monotonic() - started
        self.assertEqual(r.returncode, 0)
        self.assertLess(elapsed, 5.0, f"the Stop hook took {elapsed:.1f}s")

    def test_no_dispatch_when_the_audit_wrote_nothing(self):
        """The dispatch rides on the audit gate and must not fire without it.

        Without this, every Stop of every session -- and there were 126 of them in 54
        days on the research machine -- is a Claude invocation on the user's quota.
        """
        payload = self.stop_payload("quiet-1")  # no counters primed at all
        env = self.env(INSIGHT_NOW=str(NOW),
                       SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1")
        r = subprocess.run([str(CAPTURE)], input=payload, env=env,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        time.sleep(1.0)
        self.assertFalse((self.state / "reviews").exists())

    def test_no_dispatch_on_a_second_stop_for_the_same_session(self):
        """Both install paths deliver Stop, and a long session Stops many times.

        The audit writes exactly one record per session, so the dispatch fires at most
        once per session for the same reason.
        """
        self.prime_audit("wire-2")
        env = self.env(INSIGHT_NOW=str(NOW),
                       SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1")
        for _ in range(3):
            subprocess.run([str(CAPTURE)], input=self.stop_payload("wire-2"), env=env,
                           capture_output=True, text=True, timeout=30)
        time.sleep(1.0)
        claims = self.state / "reviews" / ".claims"
        if claims.exists():
            self.assertLessEqual(len(list(claims.iterdir())), 1)

    def test_a_dispatched_session_writes_no_audit_record_of_its_own(self):
        """A stage-2 forge is a long, many-edit session and crosses the audit threshold
        every time. The record it would write describes our own machinery working, and
        it would land in the user's candidate queue alongside their real work.

        Observed on the first real forge run: the dispatched session's own hooks fired
        normally against the same state root.
        """
        self.prime_audit("wire-4")
        env = self.env(INSIGHT_NOW=str(NOW), SKILL_COMPOUNDER_DISPATCHED="1")
        r = subprocess.run([str(CAPTURE)], input=self.stop_payload("wire-4"), env=env,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        queue = self.state / "insights" / "2026-W35.jsonl"
        if queue.exists():
            self.assertNotIn("session-audit", queue.read_text())

    def test_an_ordinary_session_does_write_an_audit_record(self):
        """The control for the test above: the suppression must be specific to a
        session we started, not a general silencing of the audit arm."""
        self.prime_audit("wire-5")
        env = self.env(INSIGHT_NOW=str(NOW))
        subprocess.run([str(CAPTURE)], input=self.stop_payload("wire-5"), env=env,
                       capture_output=True, text=True, timeout=30)
        queue = self.state / "insights" / "2026-W35.jsonl"
        self.assertTrue(queue.exists())
        self.assertIn("session-audit", queue.read_text())

    def test_the_capture_hook_refuses_to_dispatch_from_inside_a_dispatched_session(self):
        self.prime_audit("wire-3")
        env = self.env(INSIGHT_NOW=str(NOW),
                       SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE="1",
                       SKILL_COMPOUNDER_DISPATCHED="1")
        r = subprocess.run([str(CAPTURE)], input=self.stop_payload("wire-3"), env=env,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        time.sleep(1.0)
        self.assertFalse((self.state / "reviews").exists(),
                         "a dispatched session must not dispatch another")


class WatchdogTest(unittest.TestCase):
    """The stage-2 wall-clock cap.

    It replaced `command -v timeout || command -v gtimeout || run uncapped`, which a
    reviewer showed was dead config on macOS without coreutils -- so a wedged forge would
    have held the global lock and spent quota until somebody noticed. It only ever runs on
    the branch that costs $3, which is the branch least likely to be exercised by hand.
    """

    def cap(self, seconds, *cmd):
        return subprocess.run([str(REVIEW), "--cap-probe", str(seconds), *cmd],
                              capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=120)

    def test_a_command_that_finishes_passes_its_own_status_through(self):
        self.assertEqual(self.cap(60, "/bin/sh", "-c", "exit 0").stdout.strip(), "0")
        self.assertEqual(self.cap(60, "/bin/sh", "-c", "exit 3").stdout.strip(), "3")

    def test_a_command_that_overruns_is_killed_and_reported_as_124(self):
        started = time.monotonic()
        r = self.cap(5, "/bin/sleep", "300")
        elapsed = time.monotonic() - started
        self.assertEqual(r.stdout.strip(), "124")
        self.assertLess(elapsed, 60, f"the cap did not hold; took {elapsed:.0f}s")

    def test_the_overrunning_process_is_actually_gone(self):
        marker = tempfile.mkdtemp(prefix="cap-probe-")
        self.addCleanup(shutil.rmtree, marker, True)
        script = Path(marker) / "slow.sh"
        script.write_text("#!/bin/sh\nsleep 300\n")
        script.chmod(0o755)
        self.cap(5, str(script))
        # A cap that reports 124 while leaving the child running is worse than no cap:
        # it releases the lock and the runaway keeps spending.
        survivors = subprocess.run(["/usr/bin/pgrep", "-f", str(script)],
                                   capture_output=True, text=True,
                                   stdin=subprocess.DEVNULL, timeout=30)
        self.assertNotEqual(survivors.returncode, 0,
                            f"the capped process survived: {survivors.stdout}")


class VerdictParsingTest(unittest.TestCase):
    """`session-review.sh --verdict-of` -- the real parser, driven with real text.

    Exposed as its own entry point precisely so this can be tested without standing a
    fake CLI in front of it.
    """

    def parse(self, text):
        r = subprocess.run([str(REVIEW), "--verdict-of"], input=text,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        verdict, _, name = r.stdout.strip().partition("\t")
        return verdict, name

    def test_a_candidate_that_quotes_the_string_VERDICT_NONE_stays_a_candidate(self):
        """The break a reviewer found on the first attempt.

        The prompt orders the reviewer to quote the evidence verbatim; the evidence is a
        transcript digest; in this repository a transcript contains the literal string
        below constantly. A substring test recorded this as NONE -- report and index
        disagreeing, stage 2 skipped, the announcement wrong, nothing reporting a problem.
        """
        verdict, name = self.parse(
            "VERDICT: CANDIDATE mid-flight-triage\n"
            "DEAD END: the suite went red mid-edit.\n"
            "EVIDENCE:\n"
            "SAY\tthe earlier report said VERDICT: NONE and that was wrong\n")
        self.assertEqual(verdict, "CANDIDATE")
        self.assertEqual(name, "mid-flight-triage")

    def test_a_plain_none_is_none(self):
        self.assertEqual(self.parse("VERDICT: NONE\nWHY: just bugs.\n"), ("NONE", ""))

    def test_a_verdict_that_is_not_at_the_start_of_a_line_is_not_a_verdict(self):
        """An indented or prefixed verdict is quoted text, not an answer."""
        for text in ("I think the answer is VERDICT: NONE probably\n",
                     "  VERDICT: NONE\n",
                     "> VERDICT: CANDIDATE something\n"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text)[0], "UNPARSED")

    def test_a_candidate_with_no_usable_name_is_unparsed_not_a_candidate(self):
        for text in ("VERDICT: CANDIDATE\n", "VERDICT: CANDIDATE ../../escape\n",
                     "VERDICT: CANDIDATE _leading_underscore\n"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text)[0], "UNPARSED",
                                 "a name that cannot be a directory must not name one")

    def test_prose_with_no_verdict_at_all_is_unparsed(self):
        self.assertEqual(self.parse("Sure! Here you go.\n")[0], "UNPARSED")
        self.assertEqual(self.parse("")[0], "UNPARSED")

    def test_the_first_verdict_line_wins(self):
        self.assertEqual(self.parse("VERDICT: NONE\nVERDICT: CANDIDATE x\n")[0], "NONE")


class SourceContractTest(unittest.TestCase):
    """Two properties that are cheaper to assert on the source than to reproduce."""

    def test_every_process_the_dispatcher_starts_carries_the_recursion_flag(self):
        """Barrier 1. Every `claude` invocation must be prefixed with it.

        Environment is inherited without limit, so this is what stops a forge's
        subagents -- and the routing probe's own sessions -- from dispatching again.
        """
        lines = REVIEW.read_text().splitlines()
        launches = [i for i, ln in enumerate(lines)
                    if '"$CLAUDE_BIN" -p' in ln and not ln.strip().startswith("#")]
        self.assertGreaterEqual(len(launches), 2, "expected a stage-1 and a stage-2 launch")
        for i in launches:
            window = "\n".join(lines[max(0, i - 4):i + 1])
            self.assertIn("SKILL_COMPOUNDER_DISPATCHED=1", window,
                          f"launch without the recursion flag nearby: {lines[i].strip()}")

    def test_no_heredoc_is_nested_inside_command_substitution(self):
        """`x="$(cat <<'EOF' ... EOF)"` is re-scanned for quotes by bash at RUNTIME.

        A single apostrophe in the body ("somebody else's session") sent the parser
        looking for a closing quote to the end of the file: `unexpected EOF while looking
        for matching '`. Both `bash -n` and `zsh -n` pass it, which are the two checks CI
        runs over every script here, so it survived several real end-to-end runs and then
        appeared when an unrelated comment two hundred lines below changed the parity of
        the apostrophes after it. The construct is the bug; `read -r -d ''` is the fix.
        """
        for script in sorted((REPO / "hooks").glob("*.sh")):
            for n, line in enumerate(script.read_text().splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                self.assertNotIn("$(cat <<", stripped,
                                 f"{script.name}:{n} nests a heredoc inside command "
                                 f"substitution; use `read -r -d ''` instead")

    def test_the_dispatcher_actually_parses_when_it_is_run(self):
        """`bash -n` is not enough, and this is the test that says so.

        The heredoc bug above passed every static check in this repository. The only
        thing that catches it is running the script far enough to reach the construct
        and looking at stderr.
        """
        tmp = tempfile.mkdtemp(prefix="parse-probe-")
        self.addCleanup(shutil.rmtree, tmp, True)
        state = Path(tmp) / "state"
        state.mkdir()
        transcript = Path(tmp) / "t.jsonl"
        transcript.write_text(json.dumps({
            "type": "assistant", "isSidechain": False,
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": "hello world"}]}}) + "\n")
        r = subprocess.run(
            [str(REVIEW), "parse-probe", tmp, str(transcript), tmp],
            env={"PATH": PATH, "HOME": tmp, "SKILL_COMPOUNDER_STATE": str(state),
                 "SKILL_COMPOUNDER_REVIEW_ALLOW_TEST_STATE": "1",
                 "SKILL_COMPOUNDER_REVIEW_CLAUDE": "/bin/cat",
                 "SKILL_COMPOUNDER_REVIEW_NOW": str(NOW)},
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
        for bad in ("syntax error", "unexpected EOF", "unbound variable",
                    "command not found"):
            self.assertNotIn(bad, r.stderr, f"runtime shell error: {r.stderr}")
        # It ran all the way through and recorded the (genuinely failed) dispatch.
        self.assertTrue((state / "reviews" / "index.jsonl").exists())

    def test_no_printf_format_starts_with_a_dash(self):
        """bash's builtin printf rejects a format beginning with `- ` as an option.

        zsh accepts it, this repo smoke-tests both, and the shell in the shebang is the
        one that rejects it -- so the failure is a block of output silently missing from
        a file while everything around it writes normally. It cost a real report its
        entire metadata header before it was found by reading the artifact.
        """
        for script in sorted((REPO / "hooks").glob("*.sh")) + \
                sorted(p for p in (REPO / "bin").glob("*") if p.is_file()):
            for n, line in enumerate(script.read_text().splitlines(), 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                for quote in ("'", '"'):
                    bad = f"printf {quote}-"
                    if bad in s and f"printf -- {quote}" not in s:
                        self.fail(f"{script.name}:{n} printf format starts with '-' "
                                  f"and needs `printf -- `: {s}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
