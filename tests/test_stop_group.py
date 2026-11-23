#!/usr/bin/env python3
"""The kill of a timed-out /insights worker: `stop_group` against real process groups, and
the parsing of COMPOUND_INSIGHTS_TIMEOUT.

No command prints the effective timeout, and the timeout path of `insights --run` can only be
reached with a real `claude` that hangs (the journey `journey_insights.py --leg timeout` does
that by hand). So the two functions are taken from a copy of `bin/compound` loaded as a
module: `stop_group` is given real `/bin/sh` process groups started in sessions of their own,
and `insights_timeout` is called in a child interpreter whose environment and settings file
are the sandbox's.

The checks that a group is gone need an init that reaps orphans: a killed child of the
leader is reparented to it, and on Linux `killpg(pgid, 0)` succeeds while it is a zombie.
In a container, run with `--init`."""

import importlib.machinery
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
import unittest

from test_support import Case, Sandbox

# Children that ignore SIGTERM: each writes its own pid after the trap is set, then becomes
# `sleep`, which keeps the ignored disposition across exec.
IGNORER = 'trap "" TERM; echo $$ >> "$1"; exec sleep 300'


def load_compound(box):
    """The sandbox's copy of `bin/compound` as a module, with no bytecode written anywhere."""
    sys.dont_write_bytecode = True
    loader = importlib.machinery.SourceFileLoader("compound_under_test", box.script)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def group_exists(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pid_exists(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def gone_within(check, seconds):
    """Whether `check()` turns false within `seconds`: a member killed with its leader is
    reparented and reaped by init, which takes a moment, and is a zombie until then."""
    end = time.monotonic() + seconds
    while check():
        if time.monotonic() >= end:
            return False
        time.sleep(0.05)
    return True


class StopGroup(Case):
    @classmethod
    def setUpClass(cls):
        box = Sandbox()
        try:
            cls.compound = load_compound(box)
        finally:
            box.close()

    def setUp(self):
        super().setUp()
        self.procs = []
        self.pids_file = os.path.join(self.box.root, "pids")
        self.addCleanup(self.kill_everything)

    def kill_everything(self):
        """Whatever a failed test left: SIGKILL to each group and each recorded pid."""
        for proc in self.procs:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            for pid in self.pids():
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            for stream in (proc.stdout, proc.stderr):
                if stream:
                    stream.close()

    def start(self, script):
        """`/bin/sh -c script` leading a session and group of its own, its output piped as the
        worker pipes the output of `claude`."""
        proc = subprocess.Popen(["/bin/sh", "-c", script, "leader", self.pids_file], start_new_session=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, errors="replace")
        self.procs.append(proc)
        return proc

    def pids(self):
        try:
            with open(self.pids_file) as handle:
                return [int(line) for line in handle.read().split()]
        except (OSError, ValueError):
            return []

    def wait_for_pids(self, count):
        end = time.monotonic() + 10
        while len(self.pids()) < count:
            self.assertLess(time.monotonic(), end, "the group did not start its %d children" % count)
            time.sleep(0.05)
        return self.pids()

    def stop(self, proc):
        began = time.monotonic()
        result = self.compound.stop_group(proc)
        return result, time.monotonic() - began

    def assertNothingLeft(self, proc, pids):
        self.assertIsNotNone(proc.poll(), "the leader was not reaped")
        self.assertTrue(gone_within(lambda: group_exists(proc.pid), 3),
                        "process group %d still has members" % proc.pid)
        with self.assertRaises(ProcessLookupError):
            os.killpg(proc.pid, 0)
        for pid in pids:
            self.assertTrue(gone_within(lambda: pid_exists(pid), 3), "child %d is still alive" % pid)

    def test_a_group_that_obeys_sigterm_is_gone_at_once(self):
        proc = self.start('sleep 300 & echo $! >> "$1"; sleep 300 & echo $! >> "$1"; echo out; wait')
        pids = self.wait_for_pids(2)
        (out, err), took = self.stop(proc)
        self.assertLess(took, 4, "stop_group took %.1f s for a group that obeys SIGTERM" % took)
        self.assertEqual(out, "out\n")
        self.assertEqual(err, "")
        self.assertEqual(proc.returncode, -signal.SIGTERM)
        self.assertNothingLeft(proc, pids)

    def test_a_child_that_ignores_sigterm_is_killed_by_the_sweep(self):
        proc = self.start('sleep 300 & echo $! >> "$1"; sh -c \'%s\' ignorer "$1" & wait' % IGNORER)
        pids = self.wait_for_pids(2)
        _, took = self.stop(proc)
        # SIGTERM, five seconds for the group to go, then SIGKILL to what is left.
        self.assertGreaterEqual(took, 4.5, "the SIGKILL came before the five seconds were up")
        self.assertLess(took, 10, "stop_group took %.1f s" % took)
        self.assertNothingLeft(proc, pids)

    def test_a_child_that_outlives_its_exited_leader_is_killed(self):
        proc = self.start('sh -c \'%s\' ignorer "$1" & sleep 300 & echo $! >> "$1"; exit 0' % IGNORER)
        pids = self.wait_for_pids(2)
        self.assertEqual(proc.wait(timeout=10), 0)
        self.assertTrue(group_exists(proc.pid), "the children did not keep the group alive")
        _, took = self.stop(proc)
        self.assertLess(took, 10, "stop_group took %.1f s" % took)
        self.assertNothingLeft(proc, pids)

    def test_a_dead_group_is_stopped_again_harmlessly(self):
        proc = self.start('sleep 300 & echo $! >> "$1"; wait')
        pids = self.wait_for_pids(1)
        self.stop(proc)
        self.assertNothingLeft(proc, pids)
        code = proc.returncode
        (out, err), took = self.stop(proc)
        self.assertLess(took, 1, "a second stop_group took %.1f s" % took)
        self.assertEqual(proc.returncode, code)
        self.assertNothingLeft(proc, pids)

    def test_a_group_that_already_finished_is_stopped_harmlessly(self):
        proc = self.start('echo done')
        self.assertEqual(proc.wait(timeout=10), 0)
        self.assertTrue(gone_within(lambda: group_exists(proc.pid), 3))
        (out, err), took = self.stop(proc)
        self.assertLess(took, 1, "stop_group of a finished group took %.1f s" % took)
        self.assertEqual(out, "done\n")
        self.assertEqual(proc.returncode, 0)


PRINT_TIMEOUT = (
    "import importlib.machinery, importlib.util, sys\n"
    "sys.dont_write_bytecode = True\n"
    "loader = importlib.machinery.SourceFileLoader('compound_under_test', sys.argv[1])\n"
    "module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))\n"
    "loader.exec_module(module)\n"
    "print(module.insights_timeout())\n"
)


class InsightsTimeout(Case):
    def timeout(self, **env):
        proc = subprocess.run([sys.executable, "-c", PRINT_TIMEOUT, self.box.script], cwd=self.box.project,
                              env=self.box.env(**env), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=60)
        self.assertExit(proc, 0)
        return int(proc.stdout)

    def test_the_default_is_900(self):
        self.assertEqual(self.timeout(), 900)

    def test_a_whole_number_of_at_least_one_is_taken(self):
        for value, want in (("1", 1), ("30", 30), ("900", 900), ("3600", 3600), ("007", 7)):
            self.assertEqual(self.timeout(COMPOUND_INSIGHTS_TIMEOUT=value), want, value)

    def test_anything_else_gives_the_default(self):
        for value in ("0", "00", "-5", "abc", "1.5", "1e3", " 30", "30 ", "", "   ", "1234567890"):
            self.assertEqual(self.timeout(COMPOUND_INSIGHTS_TIMEOUT=value), 900, repr(value))

    def test_the_env_block_of_settings_json_is_read_and_the_environment_wins(self):
        with open(self.box.settings, "w", encoding="utf-8") as handle:
            json.dump({"env": {"COMPOUND_INSIGHTS_TIMEOUT": "45"}}, handle)
        self.assertEqual(self.timeout(), 45)
        self.assertEqual(self.timeout(COMPOUND_INSIGHTS_TIMEOUT="12"), 12)
        with open(self.box.settings, "w", encoding="utf-8") as handle:
            json.dump({"env": {"COMPOUND_INSIGHTS_TIMEOUT": "0"}}, handle)
        self.assertEqual(self.timeout(), 900)


if __name__ == "__main__":
    unittest.main()
