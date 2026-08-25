#!/usr/bin/env python3
"""Runs the real skillforge CLI as a subprocess against a real state directory."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"


class ForgeCase(unittest.TestCase):
    """Shared harness: a real temp state dir, the real CLI, no mocks anywhere."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.forge_dir = self.state / "forge"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([str(CLI), *args], capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                                   "HOME": str(self.state),
                                   "SKILL_COMPOUNDER_STATE": str(self.state)})

    def slot_files(self):
        if not self.forge_dir.is_dir():
            return []
        return sorted(p for p in self.forge_dir.glob("*.json") if p.is_file())

    def state_json(self, name=None):
        """The state of one forge, read back through the CLI the way a caller would."""
        args = ["show"] + (["--name", name] if name else [])
        r = self.run_cli(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def ledger(self):
        r = self.run_cli("ledger", "--json")
        return [json.loads(l) for l in r.stdout.splitlines() if l.strip()]


class SkillforgeTest(ForgeCase):

    def test_start_writes_complete_state(self):
        r = self.run_cli("start", "my-skill", "8", "does", "a", "useful", "thing")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.state_json()
        self.assertEqual(s["name"], "my-skill")
        self.assertEqual(s["steps"], 8)
        self.assertEqual(s["step"], 0)
        self.assertEqual(s["status"], "active")
        self.assertEqual(s["summary"], "does a useful thing")
        self.assertIsInstance(s["started"], int)

    def test_step_advances_and_records_phase(self):
        self.run_cli("start", "s", "6", "summary")
        r = self.run_cli("step", "3", "red-team round 1")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.state_json()
        self.assertEqual(s["step"], 3)
        self.assertEqual(s["phase"], "red-team round 1")
        self.assertIn("[3/6]", r.stdout)

    def test_step_records_an_overrun_instead_of_clamping_it(self):
        """Clamping made an overrun unrepresentable everywhere downstream: the status
        line could not draw it, `rounds_completed` under-counted it, and `skillreport`
        -- which reads nothing but the ledger -- could never report a forge that ran
        long. A budget is a plan; the step reached is an observation."""
        self.run_cli("start", "s", "4", "summary")
        r = self.run_cli("step", "6", "overshoot")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state_json()["step"], 6)
        self.assertEqual(self.state_json()["steps"], 4, "the budget itself is unchanged")
        self.assertIn("past the 4-step budget", r.stdout,
                      "the overrun must be said out loud, not only stored")

    def test_an_absurd_step_number_is_refused(self):
        """`--argjson n 1e20` is a float that fails every later integer test, and the
        stored step now also sets the width of a status-line field."""
        self.run_cli("start", "s", "4", "summary")
        r = self.run_cli("step", "99999999999999999999", "absurd")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.state_json()["step"], 0, "the record must be untouched")

    def test_done_does_not_rewind_a_forge_that_ran_past_its_budget(self):
        self.run_cli("start", "s", "4", "summary")
        self.run_cli("step", "7", "overshoot")
        self.run_cli("done", "shipped late")
        s = self.state_json()
        self.assertEqual(s["step"], 7, "`done` rewound the step reached to the budget")
        self.assertEqual(s["status"], "done")

    def test_the_ledger_counts_the_rounds_an_overrun_actually_completed(self):
        self.run_cli("start", "s", "4", "summary")
        self.run_cli("step", "8", "two rounds past the budget")
        self.run_cli("done", "shipped late")
        closes = [e for e in self.ledger() if e["event"] == "done"]
        self.assertEqual(len(closes), 1)
        self.assertEqual(closes[0]["step"], 8)
        self.assertEqual(closes[0]["rounds"], 3, "(8 - 2) / 2 rounds were completed")
        self.assertEqual(closes[0]["rounds_planned"], 1, "and 1 was budgeted")

    def test_done_fills_the_bar(self):
        self.run_cli("start", "s", "5", "summary")
        self.run_cli("step", "2", "midway")
        self.run_cli("done", "clean red-team pass")
        s = self.state_json()
        self.assertEqual(s["status"], "done")
        self.assertEqual(s["step"], s["steps"])
        self.assertEqual(s["phase"], "clean red-team pass")
        self.assertIn("finished", s)

    def test_fail_records_reason_without_filling_the_bar(self):
        self.run_cli("start", "s", "5", "summary")
        self.run_cli("step", "2", "midway")
        self.run_cli("fail", "3 rounds, still ambiguous")
        s = self.state_json()
        self.assertEqual(s["status"], "failed")
        self.assertEqual(s["step"], 2, "a failed forge must not show a full bar")
        self.assertEqual(s["phase"], "3 rounds, still ambiguous")

    def test_clear_removes_state(self):
        self.run_cli("start", "s", "3", "summary")
        self.run_cli("clear")
        self.assertEqual(self.slot_files(), [])

    def test_start_exits_zero_even_with_another_forge_live(self):
        """The `also live:` notice is printed by a conditional, and a trailing `&&`
        whose test is false would make the whole script exit non-zero. A caller that
        checks `skillforge start`'s status would then read a healthy forge as failed."""
        self.assertEqual(self.run_cli("start", "solo", "4", "summary").returncode, 0)
        r = self.run_cli("start", "second", "4", "summary")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("also live", r.stdout)

    # ------------------------------------------------------------- validation

    def test_summary_is_required(self):
        r = self.run_cli("start", "s", "3")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("summary is required", r.stderr)
        self.assertEqual(self.slot_files(), [])

    def test_non_numeric_steps_rejected(self):
        r = self.run_cli("start", "s", "many", "summary")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("positive integer", r.stderr)

    def test_zero_steps_rejected(self):
        r = self.run_cli("start", "s", "0", "summary")
        self.assertNotEqual(r.returncode, 0)

    def test_step_without_start_is_an_error(self):
        r = self.run_cli("step", "1", "phase")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no active forge", r.stderr)

    def test_unknown_command_is_an_error(self):
        r = self.run_cli("frobnicate")
        self.assertNotEqual(r.returncode, 0)

    def test_done_without_start_is_a_silent_noop(self):
        r = self.run_cli("done")
        self.assertEqual(r.returncode, 0, "closing an absent forge must not error")

    def test_a_name_containing_a_newline_is_rejected(self):
        """The name is the key of a one-line index. A newline in it would split one
        forge into two phantom rows and make every later --name lookup miss."""
        r = self.run_cli("start", "a\nb", "4", "summary")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.slot_files(), [])

    def test_a_name_containing_a_tab_still_round_trips(self):
        """skillreport has a regression test for a skill name holding a tab, so the
        slot index is US-separated rather than tab-separated. Nothing here may reject
        a name that the rest of the toolchain is required to carry."""
        r = self.run_cli("start", "odd\tname", "8", "summary")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state_json("odd\tname")["name"], "odd\tname")
        self.assertEqual(self.run_cli("step", "--name", "odd\tname", "3",
                                      "targeted by a tabbed name").returncode, 0)
        self.assertEqual(self.state_json("odd\tname")["step"], 3)


class ConcurrentForgeTest(ForgeCase):
    """Two forges live at once. The defect being fixed: the second `start` destroyed
    the first, and the status line then named the wrong job."""

    def test_a_second_start_does_not_destroy_the_first(self):
        self.run_cli("start", "first", "8", "the first forge")
        self.run_cli("step", "3", "first is at three")
        r = self.run_cli("start", "second", "12", "the second forge")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.slot_files()), 2)
        one = self.state_json("first")
        self.assertEqual(one["step"], 3, "the first forge's progress was overwritten")
        self.assertEqual(one["status"], "active")
        self.assertEqual(self.state_json("second")["steps"], 12)

    def test_start_names_the_other_live_forges(self):
        self.run_cli("start", "first", "8", "one")
        r = self.run_cli("start", "second", "8", "two")
        self.assertIn("first", r.stdout,
                      "starting a second forge must say that a first one is live")

    def test_a_second_start_of_the_same_active_name_is_refused(self):
        self.run_cli("start", "dup", "8", "the original")
        self.run_cli("step", "5", "well underway")
        r = self.run_cli("start", "dup", "4", "an accidental restart")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already live", r.stderr)
        s = self.state_json("dup")
        self.assertEqual(s["step"], 5, "the live forge must survive the refusal intact")
        self.assertEqual(s["steps"], 8)

    def test_the_same_name_can_be_forged_again_once_it_has_finished(self):
        self.run_cli("start", "again", "4", "first attempt")
        self.run_cli("done", "shipped")
        r = self.run_cli("start", "again", "6", "second attempt")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.state_json("again")
        self.assertEqual(s["status"], "active")
        self.assertEqual(s["steps"], 6)
        self.assertEqual(len(self.slot_files()), 1, "one slot per name, not two")

    # ---------------------------------------------------------------- targeting

    def test_step_with_no_name_refuses_while_two_are_live(self):
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "8", "two")
        r = self.run_cli("step", "4", "which one?")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("aaa", r.stderr)
        self.assertIn("bbb", r.stderr)
        self.assertIn("--name", r.stderr, "the refusal must say exactly what to type")
        self.assertEqual(self.state_json("aaa")["step"], 0, "neither forge may move")
        self.assertEqual(self.state_json("bbb")["step"], 0)

    def test_step_with_a_name_targets_only_that_forge(self):
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "8", "two")
        r = self.run_cli("step", "--name", "bbb", "6", "bbb is moving")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("bbb", r.stdout)
        self.assertEqual(self.state_json("bbb")["step"], 6)
        self.assertEqual(self.state_json("aaa")["step"], 0)

    def test_short_flag_and_environment_variable_both_target(self):
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "8", "two")
        self.assertEqual(self.run_cli("step", "-n", "aaa", "2", "via -n").returncode, 0)
        self.assertEqual(self.state_json("aaa")["step"], 2)
        env_run = subprocess.run(
            [str(CLI), "step", "3", "via the environment"], capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                 "HOME": str(self.state), "SKILL_COMPOUNDER_STATE": str(self.state),
                 "SKILLFORGE_NAME": "bbb"})
        self.assertEqual(env_run.returncode, 0, env_run.stderr)
        self.assertEqual(self.state_json("bbb")["step"], 3)
        self.assertEqual(self.state_json("aaa")["step"], 2)

    def test_no_name_is_unambiguous_again_once_only_one_is_active(self):
        """A finished forge lingers on disk for the status line's clear-out window.
        It must not make every bare command ambiguous for the next 30 seconds."""
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "8", "two")
        self.run_cli("done", "--name", "bbb", "finished")
        self.assertEqual(len(self.slot_files()), 2, "the done record must still be on disk")
        r = self.run_cli("step", "5", "no name needed now")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state_json("aaa")["step"], 5)

    def test_done_and_fail_with_no_name_refuse_rather_than_guess(self):
        for cmd in ("done", "fail"):
            with self.subTest(cmd=cmd):
                self.setUp()
                self.run_cli("start", "aaa", "8", "one")
                self.run_cli("start", "bbb", "8", "two")
                r = self.run_cli(cmd, "a message")
                self.assertNotEqual(r.returncode, 0, "closing a guessed forge is the bug")
                self.assertEqual(self.state_json("aaa")["status"], "active")
                self.assertEqual(self.state_json("bbb")["status"], "active")

    def test_done_on_one_leaves_the_other_running(self):
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "8", "two")
        self.run_cli("step", "--name", "aaa", "4", "still going")
        r = self.run_cli("done", "--name", "bbb", "clean pass")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("bbb", r.stdout)
        self.assertEqual(self.state_json("bbb")["status"], "done")
        aaa = self.state_json("aaa")
        self.assertEqual(aaa["status"], "active")
        self.assertEqual(aaa["step"], 4)

    def test_clear_with_a_name_removes_only_that_forge(self):
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "8", "two")
        self.run_cli("clear", "--name", "aaa")
        self.assertEqual(len(self.slot_files()), 1)
        self.assertEqual(self.state_json("bbb")["status"], "active")

    def test_clear_all_records_every_active_forge_in_the_ledger(self):
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "8", "two")
        r = self.run_cli("clear", "--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.slot_files(), [])
        fails = [e for e in self.ledger() if e["event"] == "fail"]
        self.assertEqual(sorted(e["name"] for e in fails), ["aaa", "bbb"],
                         "clearing an active forge must not vanish from the ledger")

    def test_clear_with_no_name_refuses_while_two_are_live(self):
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "8", "two")
        r = self.run_cli("clear")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--all", r.stderr, "the refusal must offer the way to clear both")
        self.assertEqual(len(self.slot_files()), 2)

    # -------------------------------------------------------------- inspection

    def test_show_with_no_name_reports_every_live_forge(self):
        """`show` is how a caller asks what is going on. Answering with one of several
        is the misreport this whole scheme exists to stop."""
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "8", "two")
        r = self.run_cli("show")
        self.assertEqual(r.returncode, 0, r.stderr)
        names = [json.loads(l)["name"] for l in r.stdout.splitlines() if l.strip()]
        self.assertEqual(sorted(names), ["aaa", "bbb"])
        # And every line has to stay parseable one at a time, because the liveness
        # check in the skill pipes this straight into `jq -re '.status'`.
        for line in r.stdout.splitlines():
            self.assertEqual(json.loads(line)["status"], "active")

    def test_list_shows_every_forge_with_its_progress(self):
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "12", "two")
        self.run_cli("step", "--name", "bbb", "7", "the bbb phase")
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("aaa", r.stdout)
        self.assertIn("bbb", r.stdout)
        self.assertIn("7/12", r.stdout)
        self.assertIn("the bbb phase", r.stdout)

    def test_list_and_show_are_quiet_with_no_forges(self):
        self.assertIn("no active forge", self.run_cli("list").stdout)
        self.assertIn("no active forge", self.run_cli("show").stdout)

    def test_the_ledger_records_both_forges_independently(self):
        self.run_cli("start", "aaa", "8", "one")
        self.run_cli("start", "bbb", "12", "two")
        self.run_cli("done", "--name", "aaa", "shipped")
        self.run_cli("fail", "--name", "bbb", "gave up")
        events = [(e["event"], e["name"]) for e in self.ledger()]
        self.assertIn(("start", "aaa"), events)
        self.assertIn(("start", "bbb"), events)
        self.assertIn(("done", "aaa"), events)
        self.assertIn(("fail", "bbb"), events)
        table = self.run_cli("ledger").stdout
        self.assertIn("2 forge(s): 1 done, 1 abandoned, 0 never closed out", table)


class ClosedForgeTest(ForgeCase):
    """A finished record stays on disk for the status line's clear-out window. It must
    not be mutable: a bare `step` rewound the bar under a green tick, and a second
    `done` appended a second outcome record for one start, so the ledger counted one
    forge twice. Both reports join start to the FIRST close, which hid it."""

    def test_step_cannot_resurrect_a_closed_forge(self):
        self.run_cli("start", "solo", "4", "summary")
        self.run_cli("done", "wrapped up")
        r = self.run_cli("step", "2", "resurrecting?")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not running", r.stderr)
        s = self.state_json("solo")
        self.assertEqual(s["status"], "done")
        self.assertEqual(s["step"], s["steps"], "the full bar must survive")
        self.assertEqual(s["phase"], "wrapped up")

    def test_a_second_close_adds_no_second_outcome_record(self):
        self.run_cli("start", "solo", "4", "summary")
        self.run_cli("done", "wrapped up")
        for cmd, msg in (("done", "second close"), ("fail", "and again")):
            r = self.run_cli(cmd, msg)
            self.assertEqual(r.returncode, 0, "closing a closed forge must not error")
            self.assertIn("already closed", r.stdout)
        events = [e["event"] for e in self.ledger()]
        self.assertEqual(events, ["start", "done"],
                         "one start must produce exactly one outcome record")
        self.assertEqual(self.state_json("solo")["status"], "done")

    def test_a_closed_forge_can_still_be_shown_listed_and_cleared(self):
        self.run_cli("start", "solo", "4", "summary")
        self.run_cli("done", "wrapped up")
        self.assertEqual(self.state_json("solo")["status"], "done")
        self.assertIn("solo", self.run_cli("list").stdout)
        self.assertEqual(self.run_cli("clear").returncode, 0)
        self.assertEqual(self.slot_files(), [])

    def test_a_name_that_matches_nothing_is_an_error_not_a_silent_noop(self):
        """`done --name <typo>` closing nothing, saying nothing and exiting 0 leaves a
        forge running forever with no sign anything went wrong."""
        self.run_cli("start", "real", "4", "summary")
        for cmd in ("done", "fail", "clear", "step"):
            with self.subTest(cmd=cmd):
                args = [cmd, "--name", "nope"] + (["1", "phase"] if cmd == "step" else ["msg"])
                r = self.run_cli(*args)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("no forge named 'nope'", r.stderr)
        self.assertEqual(self.state_json("real")["status"], "active")


class SimultaneousStartTest(ForgeCase):
    """Truly concurrent starts, not merely interleaved ones. The first attempt claimed
    a slot with a zero-byte file, which every racing starter read as an abandoned claim
    and took as well: three starts whose names share a slug collapsed into one slot and
    two forges were lost, silently, with exit status 0 from all three."""

    def start_together(self, *names):
        procs = [subprocess.Popen([str(CLI), "start", n, "4", "summary " + n],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                                       "HOME": str(self.state),
                                       "SKILL_COMPOUNDER_STATE": str(self.state)})
                 for n in names]
        return [p.communicate() for p in procs], [p.returncode for p in procs]

    def test_names_sharing_a_slug_each_keep_their_own_slot(self):
        for trial in range(5):
            with self.subTest(trial=trial):
                self.setUp()
                self.start_together("Foo Bar", "foo/bar", "foo-bar")
                self.assertEqual(len(self.slot_files()), 3,
                                 "a simultaneous start was silently discarded")
                names = sorted(e["name"] for e in self.ledger() if e["event"] == "start")
                self.assertEqual(names, ["Foo Bar", "foo-bar", "foo/bar"])
                for n in names:
                    self.assertEqual(self.state_json(n)["status"], "active")

    def test_two_starts_of_one_name_produce_one_forge_and_one_loser(self):
        for trial in range(5):
            with self.subTest(trial=trial):
                self.setUp()
                _, codes = self.start_together("same", "same")
                self.assertEqual(len(self.slot_files()), 1)
                starts = [e for e in self.ledger() if e["event"] == "start"]
                self.assertEqual(len(starts), 1,
                                 "two start records for one slot desyncs the ledger")
                self.assertEqual(sorted(codes), [0, 2],
                                 "exactly one starter must win and the other must fail")


class InputBoundsTest(ForgeCase):

    def test_an_unusable_step_budget_is_refused(self):
        """jq accepts 99999999999999999999 as the float 1e+20. Stored, it failed every
        later integer test: bash printed `[: integer expected` on stderr and the status
        line rendered a forge at step 5 as a full bar at 100%."""
        r = self.run_cli("start", "huge", "99999999999999999999", "summary")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("between 1 and 9999", r.stderr)
        self.assertNotIn("integer expected", r.stderr, "raw bash diagnostics must not leak")
        self.assertEqual(self.slot_files(), [])

    def test_a_realistic_budget_is_still_accepted(self):
        self.assertEqual(self.run_cli("start", "ok", "9999", "summary").returncode, 0)

    def test_an_unwritable_state_directory_reports_why(self):
        self.forge_dir.mkdir(parents=True, exist_ok=True)
        self.forge_dir.chmod(0o555)
        try:
            r = self.run_cli("start", "ro", "4", "summary")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("is it writable?", r.stderr)
            self.assertNotIn("Permission denied", r.stderr,
                             "the shell's own redirect error must not leak alongside it")
        finally:
            self.forge_dir.chmod(0o755)


class LegacyStateTest(ForgeCase):
    """An install upgraded mid-forge has a single-file record on disk from the old
    scheme. It must keep working, and it must not be deleted behind the user's back."""

    LEGACY = ('{"name":"legacy-forge","summary":"left over","phase":"round 2",'
              '"step":5,"steps":12,"status":"active","started":900,"updated":950}')

    def write_legacy(self):
        self.forge_dir.mkdir(parents=True, exist_ok=True)
        p = self.forge_dir / "current.json"
        p.write_text(self.LEGACY, encoding="utf-8")
        return p

    def test_a_legacy_record_is_adopted_as_a_forge(self):
        legacy = self.write_legacy()
        self.assertEqual(self.state_json()["name"], "legacy-forge")
        r = self.run_cli("step", "6", "still driveable")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(legacy.read_text(encoding="utf-8"))["step"], 6,
                         "the legacy file itself must be updated in place")

    def test_starting_a_new_forge_leaves_the_legacy_record_alone(self):
        legacy = self.write_legacy()
        before = legacy.read_text(encoding="utf-8")
        r = self.run_cli("start", "brand-new", "8", "a fresh forge")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(legacy.exists(), "the old record must never be silently deleted")
        self.assertEqual(legacy.read_text(encoding="utf-8"), before)
        self.assertEqual(self.state_json("brand-new")["status"], "active")

    def test_an_unparseable_state_file_is_ignored_not_deleted(self):
        self.forge_dir.mkdir(parents=True, exist_ok=True)
        junk = self.forge_dir / "half-written.json"
        junk.write_text('{"name":"truncated', encoding="utf-8")
        r = self.run_cli("start", "healthy", "4", "unaffected")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state_json()["name"], "healthy",
                         "garbage on disk must not make every command ambiguous")
        self.assertTrue(junk.exists(), "skillforge never deletes what it cannot read")


if __name__ == "__main__":
    unittest.main(verbosity=2)
