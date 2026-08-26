#!/usr/bin/env python3
"""Two closers, one forge, one ledger row.

`done` read the slot, saw `status: active`, wrote the record and appended an outcome row.
Two of them running at once both read `active` -- neither had written yet -- so both
appended, and the ledger counted one forge twice. Measured on the pre-fix script at 40 of
40 trials for two concurrent `done`s, 40 of 40 for a `fail` racing a `done`, and 40 of 40
for a `clear` racing a `done`. The ledger is the only evidence this protocol produces about
whether it pays for itself, and `bin/skillreport` reads nothing else, so a duplicated
outcome inflates the one number the whole package exists to report.

The fix claims the outcome the way a slot is claimed: `ln` of a fully-written file onto a
path named after the forge's id, which is atomic, holds nothing, and cannot wedge. These
tests run real processes against real state directories and read the results back off
disk. Nothing is mocked and nothing is stubbed.

Two reconstructions are built here by copying the real script and mutating one line:

  * PRE-FIX -- the claim path is made unique per process, so every closer wins its own
    claim and appends, which is exactly what the code did before the claim existed. The
    race tests are run against it to show they actually fail on the old behaviour rather
    than passing vacuously.
  * KILLED -- `kill -9 $$` is injected at each step of the claim sequence, so the crash
    windows are exercised by a process that really dies there rather than by an argument
    about how narrow they are.

Both mutations assert that the substitution matched, so a rewrite of `close_forge` that
moves those lines fails loudly here instead of silently testing nothing.
"""

import json
import os
import re
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"
PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

# Enough trials that the old behaviour cannot pass by luck: it failed on every single one.
TRIALS = 40


class RaceCase(unittest.TestCase):
    """A fresh state directory per trial, and real concurrent processes against it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, state):
        return {"PATH": PATH, "HOME": str(state), "SKILL_COMPOUNDER_STATE": str(state)}

    def new_state(self):
        d = tempfile.mkdtemp(dir=str(self.root))
        return Path(d)

    def run_cli(self, state, *args, cli=None):
        return subprocess.run([str(cli or CLI), *args], capture_output=True, text=True,
                              env=self.env(state))

    def together(self, state, cmds, cli=None):
        """Start every process, then collect them. Real parallelism, not interleaving."""
        procs = [subprocess.Popen([str(cli or CLI), *c], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, env=self.env(state))
                 for c in cmds]
        return [p.communicate() for p in procs], [p.wait() for p in procs]

    def ledger(self, state):
        f = state / "ledger.jsonl"
        if not f.exists():
            return []
        return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]

    def outcomes(self, state):
        return [r for r in self.ledger(state) if r["event"] in ("done", "fail")]

    def slots(self, state):
        d = state / "forge"
        if not d.is_dir():
            return []
        return sorted(p for p in d.glob("*.json") if p.is_file())

    def slot_json(self, state):
        return [json.loads(p.read_text(encoding="utf-8")) for p in self.slots(state)]

    # ---------------------------------------------------------------- reconstructions

    def variant(self, name, pattern, replacement, count=1):
        """A copy of the real CLI with one line rewritten. Asserts the rewrite matched,
        so this can never quietly become a copy of the unmodified script."""
        src = CLI.read_text(encoding="utf-8")
        out, n = re.subn(pattern, replacement, src, count=count, flags=re.M)
        self.assertEqual(n, count,
                         "the anchor for the '%s' reconstruction is gone from "
                         "bin/skillforge, so this test is no longer testing it" % name)
        p = self.bin / name
        p.write_text(out, encoding="utf-8")
        os.chmod(p, 0o755)
        return p

    def prefix_cli(self):
        """The behaviour before the fix: no shared claim, so every closer writes a row."""
        return self.variant(
            "skillforge-prefix",
            r'^  cf_claim="\$DIR/\.outcome\.\$cf_id\.claim"$',
            '  cf_claim="$DIR/.outcome.$cf_id.$$.claim"')

    ANCHORS = {
        # before anything is claimed: the record is staged, nothing is published
        "before-claim": r'^  cf_line="\$\(ledger_close_line "\$cf_tmp" "\$cf_event"\)"$',
        # after the claim is won, before the row reaches the ledger
        "after-claim": r'^  if ln "\$cf_tmp" "\$cf_claim" 2>/dev/null; then$',
        # after the row is on disk, before the closed record is published
        "after-append": r'^  if \[ -n "\$cf_line" \]; then printf .*$',
    }

    def killed_cli(self, where, sig="9"):
        """A closer that really dies -- or really stops -- at one step of the sequence."""
        return self.variant("skillforge-%s-%s" % (sig, where), self.ANCHORS[where],
                            lambda m: m.group(0) + "\n  kill -%s $$" % sig)

    def legacy_cli(self):
        """A `start` that writes no `id`, as every version before the claim did. Records
        like this are still on disk after an upgrade, and are still driveable."""
        return self.variant(
            "skillforge-legacy",
            r'status:"active", started:\$now, updated:\$now, id:\$id\}',
            'status:"active", started:$now, updated:$now}')

    def slow_cli(self):
        """A closer that dawdles between resolving the forge and staging its record, so
        another command can land in that window on purpose."""
        return self.variant("skillforge-slow", r'^  \[ -f "\$cf_f" \] \|\| return 1$',
                            '  sleep 1\n  [ -f "$cf_f" ] || return 1')

    def wait_for_claim(self, state, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            claims = [p for p in (state / "forge").iterdir()
                      if p.name.startswith(".outcome.")]
            if claims:
                return claims[0]
            time.sleep(0.02)
        self.fail("no claim appeared within %gs" % timeout)


class ConcurrentCloseTest(RaceCase):
    """One forge, several closers, all at once."""

    def close_race(self, cmds, cli=None, trials=TRIALS):
        """Run one race `trials` times. Returns the row counts seen, per trial."""
        seen = []
        for trial in range(trials):
            state = self.new_state()
            r = self.run_cli(state, "start", "solo", "4", "a summary", cli=cli)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.together(state, cmds, cli=cli)
            seen.append(len(self.outcomes(state)))
            if cli is None:
                self.assertEqual(len(self.ledger(state)) - len(self.outcomes(state)), 1,
                                 "the start record must survive the race untouched")
        return seen

    def test_two_concurrent_dones_write_one_outcome_row(self):
        rows = self.close_race([["done", "first"], ["done", "second"]])
        self.assertEqual(set(rows), {1},
                         "%d of %d trials appended a duplicate outcome row"
                         % (sum(1 for n in rows if n != 1), len(rows)))

    def test_a_fail_racing_a_done_resolves_to_one_row(self):
        """Both are outcomes and neither has priority: the row is written by whichever
        links the claim first, and the other closer exits 0 reporting the forge closed."""
        rows = self.close_race([["done", "finished"], ["fail", "abandoned"]])
        self.assertEqual(set(rows), {1})

    def test_a_clear_racing_a_done_resolves_to_one_row(self):
        """`clear` of an active forge records an abandonment, so it is an outcome too and
        goes through the same claim."""
        rows = self.close_race([["done", "finished"], ["clear"]])
        self.assertEqual(set(rows), {1})

    def test_eight_concurrent_closers_write_one_outcome_row(self):
        rows = self.close_race([["done", "n%d" % i] for i in range(8)], trials=20)
        self.assertEqual(set(rows), {1})

    def test_the_forge_is_closed_out_once_the_race_is_over(self):
        """One row is not enough on its own: a forge left `active` with its outcome
        already claimed would animate forever and could never be closed again."""
        for trial in range(TRIALS):
            with self.subTest(trial=trial):
                state = self.new_state()
                self.run_cli(state, "start", "solo", "4", "a summary")
                self.together(state, [["done", "first"], ["done", "second"]])
                slots = self.slot_json(state)
                self.assertEqual(len(slots), 1, "the slot must survive the race")
                self.assertEqual(slots[0]["status"], "done")
                self.assertEqual(slots[0]["step"], slots[0]["steps"], "the bar must fill")

    def test_exactly_one_closer_reports_that_it_closed_the_forge(self):
        """The losers must say so rather than each claiming the forge as their own."""
        for trial in range(10):
            with self.subTest(trial=trial):
                state = self.new_state()
                self.run_cli(state, "start", "solo", "4", "a summary")
                outs, codes = self.together(
                    state, [["done", "n%d" % i] for i in range(4)])
                said_complete = [o for o, _ in outs if "complete" in o]
                said_closed = [o for o, _ in outs if "already closed out" in o]
                self.assertEqual(len(said_complete), 1, outs)
                self.assertEqual(len(said_closed), 3, outs)
                self.assertEqual(codes, [0, 0, 0, 0],
                                 "losing a close race is not an error")

    def test_the_race_test_fails_against_the_pre_fix_behaviour(self):
        """Proof that the tests above are not vacuous. Reconstructed by removing the one
        thing the fix added -- a claim path shared between closers -- which is the state
        the script was in when two concurrent `done`s duplicated a row 40 times out of
        40."""
        rows = self.close_race([["done", "first"], ["done", "second"]],
                               cli=self.prefix_cli(), trials=10)
        self.assertEqual(set(rows), {2},
                         "the reconstruction no longer reproduces the defect, so the "
                         "tests above prove nothing")


class KilledCloserTest(RaceCase):
    """What a SIGKILL at each step of the claim sequence leaves behind. The rule the whole
    design is built around: nothing is held, so no crash can leave a forge that a later
    invocation cannot close."""

    def start(self, state):
        r = self.run_cli(state, "start", "solo", "4", "a summary")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_closer_killed_before_it_claims_leaves_the_forge_untouched(self):
        state = self.new_state()
        self.start(state)
        r = self.run_cli(state, "done", "killed", cli=self.killed_cli("before-claim"))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.outcomes(state), [])
        self.assertEqual(self.slot_json(state)[0]["status"], "active")
        r = self.run_cli(state, "done", "retried")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("complete", r.stdout)
        self.assertEqual([o["event"] for o in self.outcomes(state)], ["done"])
        self.assertEqual(self.slot_json(state)[0]["status"], "done")

    def test_a_closer_killed_after_claiming_loses_its_row_and_wedges_nothing(self):
        """The one window that costs anything: the row never reaches the ledger. It is a
        single `printf` builtin wide, because everything that forks runs before the claim.
        The forge still closes, no duplicate is possible, and the ledger reports the start
        as never closed out rather than inventing an outcome for it."""
        state = self.new_state()
        self.start(state)
        r = self.run_cli(state, "done", "killed", cli=self.killed_cli("after-claim"))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.outcomes(state), [])
        self.assertEqual(self.slot_json(state)[0]["status"], "active",
                         "the record is published after the row, so it is still active")
        r = self.run_cli(state, "done", "retried")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already closed out", r.stdout)
        self.assertEqual(self.slot_json(state)[0]["status"], "done",
                         "a forge whose closer died must not stay active forever")
        self.assertEqual(self.slot_json(state)[0]["phase"], "killed",
                         "the retry must publish the record the WINNER staged")
        self.assertEqual(self.outcomes(state), [],
                         "the dead closer owns this outcome; nobody may write it twice")
        view = self.run_cli(state, "ledger").stdout
        self.assertIn("never closed out", view)
        self.assertEqual(self.run_cli(state, "done", "third").returncode, 0)
        self.assertEqual(self.outcomes(state), [])

    def test_a_closer_killed_after_appending_leaves_exactly_one_row(self):
        state = self.new_state()
        self.start(state)
        r = self.run_cli(state, "done", "killed", cli=self.killed_cli("after-append"))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual([o["event"] for o in self.outcomes(state)], ["done"])
        self.assertEqual(self.slot_json(state)[0]["status"], "active")
        r = self.run_cli(state, "done", "retried")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already closed out", r.stdout)
        self.assertEqual(self.slot_json(state)[0]["status"], "done")
        self.assertEqual(self.slot_json(state)[0]["phase"], "killed")
        self.assertEqual([o["event"] for o in self.outcomes(state)], ["done"],
                         "a retry after a half-finished close appended a second row")

    def test_a_forge_started_again_after_a_killed_close_is_closable(self):
        """The claim is named after an id that is never reused, so the spent claim of one
        forge can never refuse to close the next forge of the same name."""
        state = self.new_state()
        self.start(state)
        self.run_cli(state, "done", "killed", cli=self.killed_cli("after-claim"))
        self.run_cli(state, "done", "heals it")
        r = self.run_cli(state, "start", "solo", "4", "second time")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_cli(state, "done", "closed properly")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("complete", r.stdout)
        self.assertEqual([o["phase"] for o in self.outcomes(state)], ["closed properly"])


class ClaimHousekeepingTest(RaceCase):
    """A claim is a small file per closed forge. It must not accumulate forever, and it
    must not be reaped while it is still the only thing stopping a duplicate row."""

    def claims(self, state):
        return sorted(p.name for p in (state / "forge").iterdir()
                      if p.name.startswith(".outcome.") and p.name.endswith(".claim"))

    def age(self, state, name, seconds):
        p = state / "forge" / name
        os.utime(p, (p.stat().st_mtime - seconds, p.stat().st_mtime - seconds))

    def test_a_spent_claim_is_reaped_once_it_is_old(self):
        state = self.new_state()
        self.run_cli(state, "start", "solo", "4", "a summary")
        self.run_cli(state, "done", "finished")
        self.assertEqual(len(self.claims(state)), 1)
        self.age(state, self.claims(state)[0], 7200)
        self.run_cli(state, "start", "another", "4", "a summary")
        self.assertEqual(self.claims(state), [],
                         "one file per forge would accumulate without bound")

    def test_a_young_claim_is_left_alone(self):
        state = self.new_state()
        self.run_cli(state, "start", "solo", "4", "a summary")
        self.run_cli(state, "done", "finished")
        self.run_cli(state, "start", "another", "4", "a summary")
        self.assertEqual(len(self.claims(state)), 1)

    def test_a_claim_guarding_a_still_active_forge_is_never_reaped(self):
        """An old claim over an ACTIVE forge is the fingerprint of a closer killed
        between winning the claim and publishing. Reaping it by age alone would hand back
        the duplicate row an hour later."""
        state = self.new_state()
        self.run_cli(state, "start", "solo", "4", "a summary")
        self.run_cli(state, "done", "killed", cli=self.killed_cli("after-append"))
        self.assertEqual(self.slot_json(state)[0]["status"], "active")
        self.age(state, self.claims(state)[0], 7200)
        self.run_cli(state, "start", "another", "4", "a summary")
        self.assertEqual(len(self.claims(state)), 1,
                         "the claim that stops a second row was reaped out from under it")
        self.run_cli(state, "done", "--name", "solo", "retried")
        self.assertEqual(len([o for o in self.outcomes(state) if o["name"] == "solo"]), 1)

    def test_a_forge_whose_name_ends_in_tmp_is_never_reaped_as_one(self):
        """A forge may legitimately be NAMED `build.tmp`, and its slot file is then
        `build.tmp.forge.json`, which matches the temp-file glob. An hour into a long
        forge the next `start` deleted the live slot: the animation stopped and
        `done --name build.tmp` answered `no forge named build.tmp`."""
        state = self.new_state()
        self.run_cli(state, "start", "build.tmp", "6", "a long forge")
        slot = self.slots(state)[0]
        os.utime(slot, (slot.stat().st_mtime - 7200, slot.stat().st_mtime - 7200))
        self.run_cli(state, "start", "other", "6", "a second forge")
        self.assertTrue(slot.exists(), "a live slot was reaped as a temp file")
        r = self.run_cli(state, "done", "--name", "build.tmp", "finished")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("complete", r.stdout)

    def test_a_claim_is_never_visible_as_a_forge(self):
        state = self.new_state()
        self.run_cli(state, "start", "solo", "4", "a summary")
        self.run_cli(state, "done", "finished")
        self.assertEqual(len(self.slots(state)), 1, "a claim must not read as a slot")
        self.assertEqual(self.run_cli(state, "list").stdout.count("solo"), 1)


class OneForgeOneClaimTest(RaceCase):
    """Every one of these was found by a cold reviewer against the first version of the
    claim, and every one was reproduced before it was fixed. They share a shape: two
    forges that are not the same forge ended up answering to one claim, or one that is
    the same forge ended up with none."""

    def test_a_suspended_closer_cannot_bury_the_forge_that_replaced_its_own(self):
        """SIGSTOP is the honest version of "a loaded machine". Unguarded, the winner's
        publish had no time bound at all: stop a closer after it claims, let another
        process close the forge, start the same name again, then continue it -- and the
        live six-step forge was replaced by the four-step corpse, left with no outcome
        row, and could never be closed, because its own claim had never been taken."""
        state = self.new_state()
        self.run_cli(state, "start", "f", "4", "first forge")
        stopped = subprocess.Popen([str(self.killed_cli("after-claim", "STOP")),
                                    "done", "stopped"], env=self.env(state),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.wait_for_claim(state)
            self.run_cli(state, "done", "heals it")
            r = self.run_cli(state, "start", "f", "6", "second forge")
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            os.kill(stopped.pid, signal.SIGCONT)
            stopped.communicate(timeout=30)
        slot = self.slot_json(state)[0]
        self.assertEqual(slot["summary"], "second forge",
                         "a resumed closer buried the forge that replaced its own")
        r = self.run_cli(state, "done", "closed properly")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("complete", r.stdout)
        self.assertEqual([(o["name"], o["summary"]) for o in self.outcomes(state)],
                         [("f", "first forge"), ("f", "second forge")])

    def test_two_forges_with_no_id_in_one_slot_do_not_share_a_claim(self):
        """A record written before the `id` field existed falls back to an identity built
        from its slot's inode. Built from the slot NAME and start time instead, two
        successive forges of one name under a pinned clock shared a claim: the second was
        overwritten by the first one's corpse, got no ledger row, and was unclosable."""
        state = self.new_state()
        old = self.legacy_cli()
        env = dict(self.env(state), SKILLFORGE_NOW="1000")
        for summary in ("first run", "second run"):
            r = subprocess.run([str(old), "start", "proj", "4", summary],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run([str(CLI), "done", "closed"], capture_output=True,
                               text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("complete", r.stdout, "the second forge was never closable")
        self.assertEqual([o["summary"] for o in self.outcomes(state)],
                         ["first run", "second run"])
        self.assertEqual(self.slot_json(state)[0]["summary"], "second run")

    def test_two_foreign_records_with_similar_filenames_are_both_closable(self):
        """The identity of a record must be injective. Sanitizing an arbitrary string
        into a filename is not: `alpha!.json` and `alpha@.json` mapped to one claim, and
        closing the first destroyed the second and left it out of the ledger."""
        state = self.new_state()
        (state / "forge").mkdir(parents=True, exist_ok=True)
        for fname, name in (("alpha!.json", "alpha"), ("alpha@.json", "beta")):
            (state / "forge" / fname).write_text(json.dumps(
                {"name": name, "summary": name, "phase": "p", "step": 1, "steps": 4,
                 "status": "active", "started": 900}), encoding="utf-8")
        for name in ("alpha", "beta"):
            r = self.run_cli(state, "done", "--name", name, "closed")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("complete", r.stdout, "%s was not closable" % name)
        self.assertEqual(sorted(o["name"] for o in self.outcomes(state)),
                         ["alpha", "beta"])
        self.assertEqual(sorted(s["name"] for s in self.slot_json(state)),
                         ["alpha", "beta"], "one record was published over the other")

    def test_a_very_long_foreign_slot_name_still_gets_a_claim(self):
        """A claim path longer than NAME_MAX cannot be created, and the fall-through that
        keeps an unclaimable outcome from wedging then lets every closer write a row. The
        identity is bounded so the path cannot get there: 230 characters of foreign
        filename used to produce 2 rows and 0 claims."""
        state = self.new_state()
        (state / "forge").mkdir(parents=True, exist_ok=True)
        (state / "forge" / ("b" * 230 + ".json")).write_text(json.dumps(
            {"name": "big", "summary": "s", "phase": "p", "step": 1, "steps": 4,
             "status": "active", "started": 900}), encoding="utf-8")
        self.together(state, [["done", "--name", "big", "finished"],
                              ["fail", "--name", "big", "abandoned"]])
        self.assertEqual(len(self.outcomes(state)), 1)

    def test_a_forge_cleared_out_from_under_a_closer_reports_it_plainly(self):
        """`set -u` turns a message with a missing name in it into `CLOSED_NAME: unbound
        variable` on stderr and a failing exit from a `done` that did nothing wrong."""
        state = self.new_state()
        self.run_cli(state, "start", "solo", "4", "a summary")
        slow = subprocess.Popen([str(self.slow_cli()), "done", "first"],
                                env=self.env(state), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        time.sleep(0.3)
        self.run_cli(state, "clear")
        out, err = slow.communicate(timeout=30)
        self.assertEqual(slow.returncode, 0, err)
        self.assertEqual(err, "", "a shell diagnostic leaked to the user")
        self.assertIn("already closed out", out)
        self.assertEqual(len(self.outcomes(state)), 1)


class ManyForgesUnderLoadTest(RaceCase):
    """The properties that already held must go on holding: no forge, no ledger row and
    no slot is lost when many forges are started and closed at once. Twelve forges, three
    of whose names sanitize to the same slug, two closers each -- 360 real processes."""

    NAMES = (["Forge %d" % i for i in range(9)]
             + ["Same Slug", "same/slug", "same-slug"])

    def test_nothing_is_lost_when_every_forge_is_closed_at_once(self):
        for trial in range(10):
            with self.subTest(trial=trial):
                state = self.new_state()
                self.together(state, [["start", n, "6", "summary " + n]
                                      for n in self.NAMES])
                self.together(state, [["done", "--name", n, "close %d" % k]
                                      for n in self.NAMES for k in (0, 1)])
                led = self.ledger(state)
                self.assertEqual(sorted(r["name"] for r in led if r["event"] == "start"),
                                 sorted(self.NAMES), "a start record was lost")
                self.assertEqual(sorted(r["name"] for r in self.outcomes(state)),
                                 sorted(self.NAMES),
                                 "every forge must produce exactly one outcome row")
                self.assertEqual(len(self.slots(state)), len(self.NAMES),
                                 "a slot was lost")
                self.assertEqual([s["status"] for s in self.slot_json(state)],
                                 ["done"] * len(self.NAMES))


if __name__ == "__main__":
    unittest.main(verbosity=2)
