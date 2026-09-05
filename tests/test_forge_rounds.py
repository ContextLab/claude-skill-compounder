#!/usr/bin/env python3
"""The round cap, and the only two ways past it.

Three of ten forges on record overran an advisory cap, so the cap stopped being advisory.
It could not go on `skillforge step` -- three tests in `tests/test_skillforge.py` pin
`step`'s overrun behaviour at exit 0, and they are right, because a budget is a plan and
the step reached is an observation. It went on `skillforge round`, which owns the per-forge
round record and therefore knows how many rounds are really on it.

What this file pins:

* `round` appends one line per round in the format the forging protocol has always written
  by hand, and exits 0 while budgeted rounds remain.
* A round past the budget exits **3** and writes **no row**. The "no row" half is the one
  that matters: a cap that records the round it just refused has refused nothing.
* `escalate --converging` exits **4** unless the last two recorded rounds show a strictly
  FALLING blocking count. Flat is not falling and rising is not falling.
* `escalate --narrowed "<what was cut>"` is granted once per forge and refused the second
  time, because a narrowed skill is a new skill for review purposes and owes exactly one
  cold round.
* Either grant raises the forge's `steps` by EXACTLY 2 -- one round, since the protocol
  budgets steps as 2 + 2 x rounds -- so `show`, the status line and the ledger's
  `rounds_planned` all see the raised budget; and appends one `escalate` row.
* Two grants per forge is the ceiling. A third is refused whichever kind it is, which is
  what bounds the loop at four rounds no matter what the counts do.
* `skillforge horizon` writes the ledger's horizon row on a fresh state and is idempotent.

House rules, not this file's:

* NO MOCKS. Every test runs the real `bin/skillforge` through `subprocess` against a real
  temp state directory, with `HOME` and `SKILL_COMPOUNDER_STATE` pinned into it and a
  minimal `PATH`, and reads the round record and the ledger back off disk.
* THE CLOCK IS PINNED, NOT MOCKED. `SKILLFORGE_NOW` is the knob `bin/skillforge` reads for
  exactly this purpose.
* `stdin=subprocess.DEVNULL` on every call: nothing here reads stdin, but a run that
  inherits this file's own is one refactor away from hanging the suite forever.
"""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"
SKILL = (REPO / "skills" / "skill-compounder" / "SKILL.md").read_text(encoding="utf-8")

PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
T0 = 1786000000            # 2026-08-06 UTC, the epoch the other ledger tests use

# The exit codes the CLI's own header names. Restated here as names rather than as bare
# integers at the call sites, so a test that asserts on the wrong one says which one it
# meant. 3 and 4 are separate on purpose: a caller that hit the cap has two documented
# moves left, and a caller whose escalation was refused has already spent one of them.
CAP = 3
REFUSED = 4
BAD_ARGV = 2


class RoundsCase(unittest.TestCase):
    """A real temp state dir, a real temp project, the real CLI, nothing pretended."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # RESOLVED, because macOS puts the temp tree behind /var -> /private/var and the
        # shell reports the real path.
        self.root = Path(self.tmp.name).resolve()
        self.state = self.root / "state"
        self.state.mkdir()
        self.proj = self.root / "project"
        self.proj.mkdir()
        self.ledger = self.state / "ledger.jsonl"
        self.rounds_dir = self.state / "rounds"

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------------ the harness

    def cli(self, *args, now=T0, **extra):
        env = {"PATH": PATH, "HOME": str(self.root / "home"),
               "SKILL_COMPOUNDER_STATE": str(self.state),
               # Nothing here wants a link into a skills directory; `done` is called in
               # one test only, to prove the raised budget reaches the ledger.
               "SKILLFORGE_NO_INSTALL": "1"}
        if now is not None:
            env["SKILLFORGE_NOW"] = str(now)
        env.update({k: str(v) for k, v in extra.items()})
        return subprocess.run([str(CLI), *args], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, cwd=str(self.proj), env=env)

    def start(self, name="demo", steps=6):
        r = self.cli("start", name, str(steps), "a forge under test",
                     "--trigger", "the verbatim thing that set this off",
                     "--trigger-kind", "user-prompt")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def round(self, name="demo", blocking=1, total=2, **flags):
        args = ["round", "--name", name, "--blocking", str(blocking),
                "--total", str(total)]
        for k, v in flags.items():
            args += ["--" + k.replace("_", "-"), v]
        return self.cli(*args)

    def tsv(self, name="demo"):
        """The round record exactly as it is on disk, or None when there is no file."""
        p = self.rounds_dir / ("%s.tsv" % name)
        return p.read_text(encoding="utf-8") if p.is_file() else None

    def rows(self, event):
        if not self.ledger.is_file():
            return []
        out = []
        for line in self.ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("event") == event:
                    out.append(r)
        return out

    def record(self, name="demo"):
        """The forge record, read back through the CLI the way a caller would."""
        r = self.cli("show", "--name", name, "--full")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)


# --------------------------------------------------------------------- the round record

class RoundRecordTest(RoundsCase):

    def test_a_round_is_appended_in_the_format_the_protocol_writes_by_hand(self):
        """Five tab-separated columns, keyed, in this order. The format is not new: two
        real round files exist on the machine this was written on, written by hand by the
        sessions that ran those forges, and the CLI had to join that format rather than
        invent one beside it."""
        self.start()
        r = self.round(blocking=4, total=9, subsystems="base-ladder;scratch-stamp",
                       shapes="route-terminates-nowhere;guard-exits-0")
        self.assertEqual(r.returncode, 0, r.stderr)
        line = self.tsv().splitlines()[0]
        self.assertEqual(
            line.split("\t"),
            ["1", "blocking=4", "total=9",
             "subsystems=base-ladder;scratch-stamp",
             "shapes=route-terminates-nowhere;guard-exits-0"])

    def test_the_optional_columns_are_present_and_empty_when_not_given(self):
        """A row with four columns is a row a reader taking column 5 by number reads as
        missing. The keys are always there; only their values are empty."""
        self.start()
        self.round(blocking=1, total=2)
        self.assertEqual(self.tsv().splitlines()[0].split("\t")[3:],
                         ["subsystems=", "shapes="])

    def test_a_tab_or_a_newline_inside_a_value_cannot_add_a_column_or_a_row(self):
        """A tab inside a subsystem list adds a column and a newline adds a row, and
        either makes the file say something nobody wrote."""
        self.start()
        self.round(blocking=1, total=2, subsystems="a\tb\nc", shapes="d\te")
        text = self.tsv()
        self.assertEqual(len(text.splitlines()), 1, text)
        self.assertEqual(text.splitlines()[0].split("\t"),
                         ["1", "blocking=1", "total=2", "subsystems=a b c", "shapes=d e"])

    def test_the_rounds_are_numbered_from_one_and_in_order(self):
        self.start(steps=8)                       # 3 planned rounds
        for i in range(3):
            self.assertEqual(self.round(blocking=3 - i, total=5).returncode, 0)
        self.assertEqual([l.split("\t")[0] for l in self.tsv().splitlines()],
                         ["1", "2", "3"])

    def test_the_record_lives_beside_the_ledger_under_rounds(self):
        """`skills/skill-compounder/SKILL.md` names the path
        `~/.claude/skill-compounder/rounds/<forge>.tsv`, and the state root is what
        SKILL_COMPOUNDER_STATE redirects."""
        self.start(name="a-forge")
        self.round(name="a-forge")
        self.assertTrue((self.state / "rounds" / "a-forge.tsv").is_file(),
                        sorted(p.name for p in self.state.iterdir()))


# ------------------------------------------------------------------------- the hard cap

class RoundCapTest(RoundsCase):

    def test_the_budgeted_rounds_are_granted(self):
        self.start(steps=6)                       # 2 planned rounds
        self.assertEqual(self.round(blocking=3, total=7).returncode, 0)
        self.assertEqual(self.round(blocking=2, total=5).returncode, 0)
        self.assertEqual(len(self.tsv().splitlines()), 2)

    def test_a_round_past_the_budget_exits_three(self):
        self.start(steps=6)
        self.round(blocking=3, total=7)
        self.round(blocking=2, total=5)
        r = self.round(blocking=1, total=4)
        self.assertEqual(r.returncode, CAP, r.stdout + r.stderr)

    def test_the_refused_round_writes_no_row(self):
        """The half that matters. A cap that records the round it just refused has
        refused nothing, and the next `round` would then be refused for a round the
        forge never ran."""
        self.start(steps=6)
        self.round(blocking=3, total=7)
        self.round(blocking=2, total=5)
        before = self.tsv()
        r = self.round(blocking=1, total=4)
        self.assertEqual(r.returncode, CAP)
        self.assertEqual(self.tsv(), before,
                         "the refused round was appended to the record anyway")

    def test_the_refusal_names_the_two_most_recent_blocking_counts(self):
        """'Not converging' is a claim about a trajectory, and a refusal that hides the
        trajectory is a refusal nobody can check."""
        self.start(steps=6)
        self.round(blocking=2, total=7)
        self.round(blocking=3, total=9)
        msg = self.round(blocking=1, total=4).stderr
        self.assertIn("round 2 = 3", msg)
        self.assertIn("round 1 = 2", msg)
        self.assertIn("it rose", msg)

    def test_the_refusal_names_both_escape_routes_and_the_close(self):
        self.start(steps=6)
        self.round(blocking=3, total=7)
        self.round(blocking=2, total=5)
        msg = self.round(blocking=1, total=4).stderr
        self.assertIn("--converging", msg)
        self.assertIn("--narrowed", msg)
        self.assertIn("skillforge fail --name demo", msg)

    def test_a_forge_with_no_budgeted_rounds_is_refused_at_round_one(self):
        """steps 2 is (2 - 2) / 2 = 0 planned rounds. The refusal must not divide by the
        count it does not have, and must say what it found instead."""
        self.start(steps=2)
        r = self.round(blocking=1, total=2)
        self.assertEqual(r.returncode, CAP, r.stdout + r.stderr)
        self.assertIn("0 of 0 planned", r.stderr)
        self.assertIsNone(self.tsv())

    def test_the_cap_the_skill_states_is_the_cap_the_cli_enforces(self):
        """DERIVED, and run. `SKILL.md` states a round cap and budgets steps as
        2 + 2 x rounds; the CLI derives its plan from the budget alone. Both numbers move
        in the documentation wave, so neither is written down here: the cap is read out of
        the skill, a forge is started with the budget that cap implies, and the CLI is
        asked to grant exactly that many rounds and refuse the next."""
        m = re.search(r"Cap at (\d+) rounds", SKILL)
        self.assertIsNotNone(
            m, "SKILL.md no longer states a round cap in a parseable form, so this check "
               "cannot derive the number the CLI is supposed to enforce")
        cap = int(m.group(1))
        self.start(steps=2 + 2 * cap)
        for i in range(cap):
            r = self.round(blocking=cap - i, total=cap + 4)
            self.assertEqual(r.returncode, 0,
                             "round %d of a %d-round budget was refused: %s"
                             % (i + 1, cap, r.stderr))
            self.assertIn("round %d/%d" % (i + 1, cap), r.stdout)
        over = self.round(blocking=0, total=1)
        self.assertEqual(over.returncode, CAP,
                         "SKILL.md caps the loop at %d rounds and the CLI granted a "
                         "%dth: %s" % (cap, cap + 1, over.stdout + over.stderr))


# ----------------------------------------------------------------------- the escalation

class EscalateTest(RoundsCase):

    def escalate(self, *args, name="demo"):
        return self.cli("escalate", "--name", name, *args)

    def test_converging_is_refused_on_a_flat_count(self):
        self.start(steps=6)
        self.round(blocking=3, total=7)
        self.round(blocking=3, total=8)
        r = self.escalate("--converging")
        self.assertEqual(r.returncode, REFUSED, r.stdout + r.stderr)
        self.assertIn("not a fall", r.stderr)
        self.assertEqual(self.record()["steps"], 6, "a refused escalation raised the budget")
        self.assertEqual(self.rows("escalate"), [])

    def test_converging_is_refused_on_a_rising_count(self):
        self.start(steps=6)
        self.round(blocking=2, total=7)
        self.round(blocking=4, total=9)
        r = self.escalate("--converging")
        self.assertEqual(r.returncode, REFUSED, r.stdout + r.stderr)
        self.assertEqual(self.record()["steps"], 6)

    def test_converging_is_refused_before_a_second_round_exists(self):
        """The assessment binds from round 2, where the first comparison exists. One data
        point cannot match the converging definition, and granting on one round is a
        licence to escalate after one."""
        self.start(steps=6)
        self.round(blocking=3, total=7)
        r = self.escalate("--converging")
        self.assertEqual(r.returncode, REFUSED, r.stdout + r.stderr)
        self.assertIn("no comparison to make", r.stderr)

    def test_converging_is_granted_on_a_strictly_falling_count(self):
        self.start(steps=6)
        self.round(blocking=4, total=9)
        self.round(blocking=2, total=7)
        r = self.escalate("--converging")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_grant_raises_the_budget_by_exactly_two_steps(self):
        """Exactly one round. The protocol budgets steps as 2 + 2 x rounds -- a review
        step and a revision step per round -- so any other number grants a fraction of a
        round and leaves `rounds_planned` disagreeing with the budget it came from."""
        self.start(steps=6)
        self.round(blocking=4, total=9)
        self.round(blocking=2, total=7)
        self.assertEqual(self.escalate("--converging").returncode, 0)
        self.assertEqual(self.record()["steps"], 8)

    def test_the_raised_budget_is_what_the_next_round_is_measured_against(self):
        """The point of raising `steps` rather than keeping a private counter: the plan
        every other surface reads is the plan the cap enforces."""
        self.start(steps=6)
        self.round(blocking=4, total=9)
        self.round(blocking=2, total=7)
        self.escalate("--converging")
        r = self.round(blocking=1, total=5)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("round 3/3", r.stdout)

    def test_a_grant_appends_one_escalate_row_carrying_the_counts_and_the_reason(self):
        self.start(steps=6)
        self.round(blocking=4, total=9)
        self.round(blocking=2, total=7)
        self.escalate("--converging")
        rows = self.rows("escalate")
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual(row["name"], "demo")
        self.assertEqual(row["reason"], "converging")
        self.assertEqual(row["grant"], 1)
        self.assertEqual(row["rounds_recorded"], 2)
        self.assertEqual(row["rounds_planned_before"], 2)
        self.assertEqual(row["rounds_planned_after"], 3)
        self.assertEqual(row["steps_before"], 6)
        self.assertEqual(row["steps_after"], 8)
        self.assertEqual(row["blocking_last"], 2)
        self.assertEqual(row["blocking_prev"], 4)
        self.assertEqual(row["ts"], T0)
        self.assertIs(row["backfilled"], False)

    def test_a_narrowed_grant_records_what_was_cut(self):
        self.start(steps=6)
        self.round(blocking=3, total=7)
        self.round(blocking=3, total=7)
        r = self.escalate("--narrowed", "dropped the scope half to finish-task")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        row = self.rows("escalate")[0]
        self.assertEqual(row["reason"], "narrowed")
        self.assertEqual(row["narrowed"], "dropped the scope half to finish-task")
        self.assertEqual(self.record()["steps"], 8)

    def test_narrowed_is_granted_once_per_forge_and_refused_the_second_time(self):
        """A narrowed skill is a new skill for review purposes and owes ONE cold round.
        A second narrowing is a different skill again, not a longer review of this one."""
        self.start(steps=6)
        self.round(blocking=3, total=7)
        self.round(blocking=3, total=7)
        self.assertEqual(self.escalate("--narrowed", "cut the scope half").returncode, 0)
        self.round(blocking=3, total=7)
        r = self.escalate("--narrowed", "cut it again")
        self.assertEqual(r.returncode, REFUSED, r.stdout + r.stderr)
        self.assertIn("once per forge", r.stderr)
        self.assertEqual(self.record()["steps"], 8, "the refused narrowing raised the budget")
        self.assertEqual(len(self.rows("escalate")), 1)

    def test_a_third_grant_of_either_kind_is_refused(self):
        """Two grants per forge is the ceiling, and it is what bounds the loop at four
        rounds no matter what the counts do."""
        self.start(steps=6)
        self.round(blocking=4, total=9)
        self.round(blocking=3, total=8)
        self.assertEqual(self.escalate("--converging").returncode, 0)   # grant 1
        self.round(blocking=2, total=7)
        self.assertEqual(self.escalate("--converging").returncode, 0)   # grant 2
        self.round(blocking=1, total=6)
        third = self.escalate("--converging")
        self.assertEqual(third.returncode, REFUSED, third.stdout + third.stderr)
        self.assertIn("ceiling", third.stderr)
        self.assertEqual(self.record()["steps"], 10)
        self.assertEqual(len(self.rows("escalate")), 2)

    def test_the_ceiling_holds_across_the_two_kinds(self):
        """A forge that narrows once and converges once has spent both grants; the third
        is refused whichever kind it asks for."""
        self.start(steps=6)
        self.round(blocking=3, total=7)
        self.round(blocking=3, total=7)
        self.assertEqual(self.escalate("--narrowed", "cut the scope half").returncode, 0)
        self.round(blocking=2, total=6)
        self.assertEqual(self.escalate("--converging").returncode, 0)
        self.round(blocking=1, total=5)
        r = self.escalate("--narrowed", "cut something else")
        self.assertEqual(r.returncode, REFUSED, r.stdout + r.stderr)

    def test_four_rounds_is_the_most_a_two_round_forge_can_reach(self):
        """The whole cap, end to end: two budgeted, two granted, and the fifth refused
        with nowhere left to appeal."""
        self.start(steps=6)
        for b in (4, 3):
            self.assertEqual(self.round(blocking=b, total=9).returncode, 0)
        self.assertEqual(self.escalate("--converging").returncode, 0)
        self.assertEqual(self.round(blocking=2, total=8).returncode, 0)
        self.assertEqual(self.escalate("--converging").returncode, 0)
        self.assertEqual(self.round(blocking=1, total=7).returncode, 0)
        self.assertEqual(self.round(blocking=0, total=6).returncode, CAP)
        self.assertEqual(self.escalate("--converging").returncode, REFUSED)
        self.assertEqual(len(self.tsv().splitlines()), 4)

    def test_both_claims_at_once_is_bad_argv_not_a_refusal(self):
        """They are different claims about why the round is owed, and the ledger row
        records which one bought it. Exit 2, because the caller can fix it by typing
        something else."""
        self.start(steps=6)
        self.round(blocking=4, total=9)
        self.round(blocking=2, total=7)
        r = self.escalate("--converging", "--narrowed", "x")
        self.assertEqual(r.returncode, BAD_ARGV, r.stdout + r.stderr)
        self.assertEqual(self.rows("escalate"), [])

    def test_a_narrowing_nobody_wrote_down_is_refused(self):
        self.start(steps=6)
        self.round(blocking=4, total=9)
        r = self.escalate("--narrowed", "   ")
        self.assertEqual(r.returncode, BAD_ARGV, r.stdout + r.stderr)
        self.assertEqual(self.record()["steps"], 6)

    def test_neither_claim_is_usage(self):
        self.start(steps=6)
        r = self.escalate()
        self.assertEqual(r.returncode, BAD_ARGV, r.stdout + r.stderr)
        self.assertIn("--converging", r.stderr)
        self.assertIn("--narrowed", r.stderr)


# ------------------------------------------------------- the raised budget in the ledger

class RaisedBudgetReachesTheLedgerTest(RoundsCase):

    def test_the_close_row_reports_the_raised_plan(self):
        """`rounds_planned` on a done row is derived from the record's `steps`, which is
        exactly why the grant is written there. A forge that was granted a third round and
        then ran it must not read as a forge that overran a two-round plan."""
        self.start(steps=6)
        self.round(blocking=4, total=9)
        self.round(blocking=2, total=7)
        self.assertEqual(self.cli("escalate", "--name", "demo", "--converging").returncode, 0)
        self.assertEqual(self.cli("step", "--name", "demo", "8", "closing").returncode, 0)
        self.assertEqual(self.cli("done", "--name", "demo", "clean").returncode, 0)
        done = self.rows("done")
        self.assertEqual(len(done), 1, done)
        self.assertEqual(done[0]["rounds_planned"], 3)
        self.assertEqual(done[0]["steps"], 8)

    def test_the_close_row_and_the_reader_agree_with_the_round_record(self):
        """DEFECT, 2026-09-05, from the first forge run under the diet. `watch-ci-run`
        closed at step 9 of 10 with FOUR rounds on `<state>/rounds/<forge>.tsv`, its
        `fail` row said `"rounds":3`, and `skillforge ledger` printed "3 of 4 round(s)"
        for a forge whose own record carries four of four.

        `rounds_completed` infers the count from the step reached, which is right only
        while a forge spends exactly two steps per round. An ESCALATION buys a round
        without the forge necessarily reaching the two steps that would imply it, so the
        inference undercounts every escalated forge. The round record is the count.

        The trajectory below is the real one: 6 steps, `--narrowed` then `--converging`,
        four rounds recorded, closed at step 9 of the raised 10-step budget."""
        self.start(steps=6)                            # 2 planned rounds
        self.assertEqual(self.round(blocking=6, total=13).returncode, 0)
        self.assertEqual(self.round(blocking=6, total=13).returncode, 0)
        self.assertEqual(self.cli("escalate", "--name", "demo",
                                  "--narrowed", "cut the listing subsystem").returncode,
                         0)
        self.assertEqual(self.round(blocking=5, total=13).returncode, 0)
        self.assertEqual(self.cli("escalate", "--name", "demo",
                                  "--converging").returncode, 0)
        self.assertEqual(self.round(blocking=7, total=21).returncode, 0)
        self.assertEqual(self.cli("step", "--name", "demo", "9", "closing").returncode, 0)
        self.assertEqual(self.cli("fail", "--name", "demo",
                                  "not converging: the same subsystem three rounds"
                                  ).returncode, 0)

        self.assertEqual(len(self.tsv().splitlines()), 4, self.tsv())
        fail = self.rows("fail")
        self.assertEqual(len(fail), 1, fail)
        self.assertEqual((fail[0]["steps"], fail[0]["step"]), (10, 9), fail[0])
        self.assertEqual(fail[0]["rounds"], 4,
                         "the fail row disagrees with the four rounds on the record: %r"
                         % fail[0])
        self.assertEqual(fail[0]["rounds_planned"], 4, fail[0])

        out = self.cli("ledger").stdout
        row = [l for l in out.splitlines() if " demo  [fail]" in l]
        self.assertEqual(len(row), 1, out)
        self.assertIn("4 round(s)", row[0], row[0])
        self.assertNotIn("3 of 4", row[0],
                         "the reader still reads the step arithmetic: " + row[0])

    def test_a_forge_with_no_round_record_falls_back_to_the_step_arithmetic(self):
        """The round record is the count when there is one. When there is none -- nothing
        was ever recorded, or the file was removed -- the arithmetic is the only thing
        left to read, and it is what shipped before."""
        self.start(steps=8)
        self.assertEqual(self.cli("step", "--name", "demo", "6", "mid").returncode, 0)
        self.assertEqual(self.cli("fail", "--name", "demo", "abandoned").returncode, 0)
        self.assertIsNone(self.tsv(), "no round was recorded, so there is no record")
        self.assertEqual(self.rows("fail")[0]["rounds"], 2)

    def test_the_escalate_row_is_invisible_to_the_start_to_outcome_join(self):
        """Every reader here selects its events BY NAME, so a new event type must not move
        an existing count. `escalate` is new; the join is `start` to `done`/`fail`."""
        self.start(steps=6)
        self.round(blocking=4, total=9)
        self.round(blocking=2, total=7)
        self.cli("escalate", "--name", "demo", "--converging")
        self.cli("done", "--name", "demo", "clean")
        self.assertEqual(len(self.rows("start")), 1)
        self.assertEqual(len(self.rows("done")), 1)
        out = self.cli("ledger").stdout
        self.assertIn("1 forge(s)", out, out)


# ----------------------------------------------------------------------------- horizon

class HorizonTest(RoundsCase):
    """`ledger_ensure_horizon` runs before every `skillforge` append and states where the
    record begins. `skillforge horizon` is that function and nothing else, so another CLI
    in this package can make sure the record says where it starts before appending a row
    of its own, rather than growing a second spelling of the same question."""

    def test_horizon_writes_the_row_on_a_fresh_state(self):
        r = self.cli("horizon")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.rows("horizon")
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["known_from"], T0)
        # `complete_from` is written ONLY when the ledger was empty, because only then is
        # "complete from here" something we know.
        self.assertEqual(rows[0]["complete_from"], T0)

    def test_horizon_is_idempotent(self):
        self.cli("horizon")
        self.assertEqual(self.cli("horizon", now=T0 + 900).returncode, 0)
        self.assertEqual(self.cli("horizon", now=T0 + 1800).returncode, 0)
        self.assertEqual(len(self.rows("horizon")), 1)

    def test_horizon_over_a_ledger_that_already_has_rows_claims_nothing_before_it(self):
        """A file that already holds rows gets `known_from` -- the earliest ts in it --
        and NO `complete_from`: the completeness of what came before is unestablished, and
        the absence of the field is what says so.

        The ledger is seeded here by writing a real row to the real file, because a row
        written through the CLI would take the horizon with it: `ledger_append` calls
        `ledger_ensure_horizon` first, so on an empty ledger the horizon lands before the
        row and correctly records `complete_from`."""
        self.ledger.write_text(
            json.dumps({"event": "use", "ts": T0 - 3600, "name": "some-skill",
                        "ok": True, "recorded": "live"}) + "\n", encoding="utf-8")
        self.assertEqual(self.cli("horizon", now=T0).returncode, 0)
        rows = self.rows("horizon")
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["known_from"], T0 - 3600)
        self.assertNotIn("complete_from", rows[0])

    def test_horizon_writes_nothing_else(self):
        self.cli("horizon")
        events = [json.loads(l)["event"]
                  for l in self.ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(events, ["horizon"])


# ------------------------------------------------------------------- argv and resolution

class ArgvTest(RoundsCase):

    def test_round_requires_a_live_forge(self):
        r = self.round(name="nothing-here")
        self.assertEqual(r.returncode, BAD_ARGV, r.stdout + r.stderr)
        self.assertIn("no forge named", r.stderr)

    def test_blocking_and_total_must_be_counts(self):
        self.start()
        for bad in ("x", "-1", "1.5", ""):
            r = self.cli("round", "--name", "demo", "--blocking", bad, "--total", "3")
            self.assertEqual(r.returncode, BAD_ARGV, "--blocking %r was accepted" % bad)
        self.assertIsNone(self.tsv())

    def test_blocking_cannot_exceed_total(self):
        """Blocking findings are a subset of the round's findings, so a row claiming
        otherwise is a typo -- and the convergence rule is read off exactly that column."""
        self.start()
        r = self.round(blocking=9, total=3)
        self.assertEqual(r.returncode, BAD_ARGV, r.stdout + r.stderr)
        self.assertIsNone(self.tsv())

    def test_a_flag_with_no_value_is_refused_rather_than_eating_the_next_flag(self):
        """The failure this normalisation exists to prevent: a missing value silently
        becoming the next flag's name, recorded on the round record as if it were a
        subsystem."""
        self.start()
        r = self.cli("round", "--name", "demo", "--blocking", "--total", "3")
        self.assertEqual(r.returncode, BAD_ARGV, r.stdout + r.stderr)
        self.assertIsNone(self.tsv())

    def test_an_unknown_flag_is_named(self):
        self.start()
        r = self.cli("round", "--name", "demo", "--blocking", "1", "--total", "2",
                     "--subsytems", "typo")
        self.assertEqual(r.returncode, BAD_ARGV, r.stdout + r.stderr)
        self.assertIn("--subsytems", r.stderr)

    def test_the_key_value_form_works_too(self):
        self.start()
        r = self.cli("round", "--name=demo", "--blocking=2", "--total=5",
                     "--subsystems=one;two")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("subsystems=one;two", self.tsv())

    def test_the_help_text_names_the_three_new_subcommands(self):
        """The header block IS the help text, printed by a `sed` range. A subcommand that
        is not in it is a subcommand nobody finds."""
        out = self.cli("help").stdout
        for token in ("skillforge round", "skillforge escalate", "skillforge horizon"):
            self.assertIn(token, out, "`%s` is missing from the help text" % token)
        self.assertNotIn("set -uo pipefail", out,
                         "the help range ran past the header into shell code")


if __name__ == "__main__":
    unittest.main(verbosity=2)
