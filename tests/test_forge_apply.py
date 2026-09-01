#!/usr/bin/env python3
"""The forge loop has to end at "and then it solved the thing", not at "installed".

A skill here is built AS NEEDED -- out of a problem that was in front of somebody. A
forge that ends the moment the skill is linked has produced a tool and left the problem
exactly where it was, and until `apply` existed nothing in this package could tell that
case from a closed loop: the ledger showed a `done` row and a skill directory, and both
are equally true of a skill nobody ever opened.

So `skillforge done` now leaves a DEBT behind -- one small JSON marker per closed forge,
under `<state>/apply-pending/` -- and `skillforge apply` is the only thing that pays it,
carrying the verbatim evidence of what happened when the skill was put on the problem.
These tests pin the on-disk shape of that marker, because three components read it (the
status line segment, `hooks/apply-gate.sh`, and `skillforge pending`), and they pin the
one property everything else in this ledger rests on: adding an event type must not move
any existing count.

Two rules run through all of it, and they are the house rules, not this file's:

* NO MOCKS. Every test runs the real `bin/skillforge` through subprocess against a real
  temp state directory, with HOME and SKILL_COMPOUNDER_STATE pinned into it and a minimal
  PATH, and reads the results back off disk. Where a test needs an installed skill it
  writes a real SKILL.md and lets the real installer link it.
* THE CLOCK IS PINNED, NOT MOCKED. `SKILLFORGE_NOW` is the knob `bin/skillforge` reads
  for exactly this purpose, so a test can assert on `elapsed` and on a marker age without
  anything being faked.

`stdin=subprocess.DEVNULL` on every call: nothing here reads stdin, but a run that
inherits this file's own is one refactor away from hanging the suite forever, and that is
how the hook tests in this repo already lost an afternoon.
"""

import json
import os
import re
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"

PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
T0 = 1786000000            # 2026-08-06 UTC, the epoch the other ledger tests use

# READ OUT OF THE CLI, NEVER RESTATED HERE. A limit written down twice is a limit that
# drifts: this file used to carry its own copy of the number, and a change to
# APPLY_EVIDENCE_MAX would have left the copy asserting the old bound and passing.
EVIDENCE_MAX = int(re.search(r"(?m)^\s*APPLY_EVIDENCE_MAX=(\d+)\s*$",
                             CLI.read_text(encoding="utf-8")).group(1))

SKILL_BODY = """---
name: %s
description: Use when a probe needs a real SKILL.md on disk. Do NOT use otherwise.
---

# %s

A real file, written by a real test.
"""


class ApplyCase(unittest.TestCase):
    """A real temp state dir, a real temp project, the real CLI, nothing pretended."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # RESOLVED, because macOS puts the temp tree behind /var -> /private/var and the
        # shell reports the real path: `skill_dir` on the marker comes from the CLI's own
        # getcwd, so an unresolved expectation here fails on macOS and passes on Linux.
        self.root = Path(self.tmp.name).resolve()
        self.state = self.root / "state"
        self.state.mkdir()
        self.dest = self.root / "claude" / "skills"      # stands in for ~/.claude/skills
        self.dest.mkdir(parents=True)
        self.proj = self.root / "project"
        self.proj.mkdir()
        self.ledger = self.state / "ledger.jsonl"
        self.pending_dir = self.state / "apply-pending"

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------------ the harness

    def env(self, now=None, **extra):
        """A minimal environment. CLAUDE_CODE_SESSION_ID is deliberately ABSENT unless a
        test sets it: a session id inherited from whatever ran the suite would make the
        idempotence key differ between machines."""
        e = {"PATH": PATH, "HOME": str(self.root / "home"),
             "SKILL_COMPOUNDER_STATE": str(self.state),
             "SKILLFORGE_SKILLS_DIR": str(self.dest)}
        if now is not None:
            e["SKILLFORGE_NOW"] = str(now)
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def cli(self, *args, now=None, cwd=None, cli_path=None, **extra):
        return subprocess.run([str(cli_path or CLI), *args], capture_output=True,
                              text=True, stdin=subprocess.DEVNULL,
                              cwd=str(cwd or self.proj), env=self.env(now, **extra))

    def variant(self, name, pattern, replacement, count=1):
        """A copy of the real CLI with one line rewritten -- the same reconstruction
        tests/test_forge_close_race.py uses, and for the same reason: a crash BETWEEN two
        statements is not reachable from outside the process, and the state it leaves is
        the state these tests are about. The rewrite is asserted to have matched, so this
        can never quietly become a copy of the unmodified script."""
        src = CLI.read_text(encoding="utf-8")
        out, n = re.subn(pattern, replacement, src, count=count, flags=re.M)
        self.assertEqual(n, count,
                         "the anchor for the '%s' reconstruction is gone from "
                         "bin/skillforge, so this test is no longer testing it" % name)
        d = self.root / "bin"
        d.mkdir(exist_ok=True)
        p = d / name
        p.write_text(out, encoding="utf-8")
        os.chmod(p, 0o755)
        return p

    def claims(self):
        """Every apply claim on disk, by filename. `.f.` names a forge instance, `.r.` an
        ACT -- this skill, this outcome, this evidence, this session -- and `.s.` a
        session. The last two are the receipts a winner leaves so that a later delivery
        with no marker to key on lands on a path that is already taken: the act claim
        absorbs a re-delivery of the SAME act, and the session claim is what tells a
        second, distinct act from a first one."""
        return sorted(p.name for p in (self.state / "forge").iterdir()
                      if p.name.startswith(".apply.") and p.name.endswith(".claim"))

    def author(self, name, where="skills"):
        """Write a real skill the way a forging session would."""
        d = self.proj / where / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(SKILL_BODY % (name, name), encoding="utf-8")
        return d

    def forge_and_close(self, name="widget", steps="8", summary="a real forge",
                        trigger="the user said: stop the flaky test",
                        start_now=T0, done_now=T0 + 100, **extra):
        r = self.cli("start", name, steps, summary,
                     "--trigger", trigger, "--trigger-kind", "user-prompt",
                     now=start_now, **extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.cli("done", now=done_now, **extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def rows(self, event=None):
        if not self.ledger.exists():
            return []
        out = [json.loads(l) for l in self.ledger.read_text(encoding="utf-8").splitlines()
               if l.strip()]
        return [r for r in out if event is None or r.get("event") == event]

    def markers(self):
        if not self.pending_dir.is_dir():
            return {}
        return {p.name: json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(self.pending_dir.glob("*.json"))}

    def write_ledger(self, *records):
        self.ledger.write_text(
            "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records),
            encoding="utf-8")


# ------------------------------------------------------------------ done writes a debt

class DoneWritesTheMarker(ApplyCase):
    """`done` closing a forge is what creates the obligation to use what it forged."""

    def test_done_writes_a_marker_carrying_every_contracted_field(self):
        """The marker is a contract with three readers -- the status line, the Stop hook
        and `pending` -- so every field is asserted by name and by value, not just its
        presence. A field silently renamed here breaks components this file cannot see."""
        self.author("widget")
        self.forge_and_close("widget")
        got = self.markers()
        self.assertEqual(list(got), ["widget.json"], "expected one marker: %r" % got)
        m = got["widget.json"]
        self.assertEqual(m["name"], "widget")
        self.assertEqual(m["forge"], "widget")
        self.assertEqual(m["skill_dir"], str(self.proj / "skills" / "widget"))
        self.assertEqual(m["trigger"], "the user said: stop the flaky test")
        self.assertEqual(m["trigger_kind"], "user-prompt")
        self.assertEqual(m["summary"], "a real forge")
        self.assertEqual(m["closed"], T0 + 100)
        self.assertEqual(m["session"], "")
        self.assertIs(m["installed"], True)
        self.assertEqual(sorted(m),
                         ["closed", "forge", "forge_id", "installed", "name", "session",
                          "skill_dir", "summary", "trigger", "trigger_kind"],
                         "the marker grew or lost a key; three readers depend on it")
        self.assertTrue(m["forge_id"],
                        "the marker must name the forge instance it came from; without it "
                        "a second forge of one name in one session cannot be applied")

    def test_the_session_id_is_recorded_when_the_environment_carries_one(self):
        self.author("widget")
        self.forge_and_close("widget", CLAUDE_CODE_SESSION_ID="sess-abc")
        self.assertEqual(self.markers()["widget.json"]["session"], "sess-abc")

    def test_a_done_that_installed_nothing_still_writes_a_marker(self):
        """The case that must not be silently forgotten: a forge ran its rounds and
        produced a skill nobody can invoke. installed:false is the honest record of it,
        and the debt is still owed -- there is a problem out there that started this."""
        self.forge_and_close("ghost")            # no SKILL.md was ever authored
        m = self.markers()
        self.assertEqual(list(m), ["ghost.json"], "a done with no skill wrote no marker")
        self.assertIs(m["ghost.json"]["installed"], False)
        self.assertEqual(m["ghost.json"]["skill_dir"], "")

    def test_no_install_being_disabled_is_reported_as_not_installed(self):
        """SKILLFORGE_NO_INSTALL linked nothing, so nothing can invoke the skill. Saying
        installed:true because a directory happens to exist is the "it worked" this
        package exists to stop producing."""
        self.author("widget")
        self.forge_and_close("widget", SKILLFORGE_NO_INSTALL="1")
        m = self.markers()["widget.json"]
        self.assertIs(m["installed"], False)
        self.assertEqual(m["skill_dir"], str(self.proj / "skills" / "widget"),
                         "the directory is still recorded; only the linking did not happen")

    def test_the_marker_is_named_after_the_skill_directory_not_the_forge(self):
        """A session invokes a skill by the directory it sits in. A marker under the forge
        name would tell somebody to apply a name that answers `Unknown skill`."""
        skill = self.author("real-name")
        self.cli("start", "typo-name", "4", "s", "--skill-dir", str(skill),
                 "--trigger", "t", "--trigger-kind", "user-prompt", now=T0)
        self.cli("done", now=T0 + 10)
        m = self.markers()
        self.assertEqual(list(m), ["real-name.json"], "marker: %r" % m)
        self.assertEqual(m["real-name.json"]["name"], "real-name")
        self.assertEqual(m["real-name.json"]["forge"], "typo-name")

    def test_done_tells_the_caller_the_loop_is_not_closed_yet(self):
        self.author("widget")
        r = self.forge_and_close("widget")
        self.assertIn("NOT YET APPLIED", r.stdout)
        self.assertIn("skillforge apply --name 'widget'", r.stdout)

    def test_fail_writes_no_marker(self):
        """An abandoned forge produced nothing to apply. A debt nobody can discharge is a
        permanent false alarm, and a queue full of those teaches every reader to ignore
        it -- which costs more than the reminder was ever worth."""
        self.author("widget")
        self.cli("start", "widget", "4", "s", "--trigger", "t",
                 "--trigger-kind", "user-prompt", now=T0)
        r = self.cli("fail", "gave up", now=T0 + 10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.markers(), {}, "fail left a debt behind")

    def test_clear_of_an_active_forge_writes_no_marker_either(self):
        """`clear` records a `fail` row, and it is a fail for this purpose too."""
        self.cli("start", "widget", "4", "s", "--trigger", "t",
                 "--trigger-kind", "user-prompt", now=T0)
        self.cli("clear", now=T0 + 5)
        self.assertEqual(self.markers(), {})

    def test_a_second_done_does_not_recreate_a_discharged_debt(self):
        """The loser of the close race exits before the marker is written. Otherwise a
        stray second `done` would resurrect a debt that had already been paid, and the
        queue would never empty."""
        self.author("widget")
        self.forge_and_close("widget")
        self.cli("apply", "--name", "widget", "--outcome", "used",
                 "--evidence", "used it, the flake stopped", now=T0 + 200)
        self.assertEqual(self.markers(), {})
        r = self.cli("done", "--name", "widget", now=T0 + 300)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.markers(), {}, "a second done re-created a paid debt")


# --------------------------------------------------------------------------- apply

class ApplyWritesOneRow(ApplyCase):

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget")

    def test_apply_writes_exactly_one_row_and_removes_the_marker(self):
        r = self.cli("apply", "--name", "widget", "--outcome", "used",
                     "--evidence", "Skill(widget) ran and the flaky test passed",
                     now=T0 + 700)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.rows("apply")
        self.assertEqual(len(rows), 1, "expected one apply row, got %r" % rows)
        row = rows[0]
        self.assertEqual(row["name"], "widget")
        self.assertEqual(row["outcome"], "used")
        self.assertEqual(row["evidence"],
                         "Skill(widget) ran and the flaky test passed")
        self.assertEqual(row["ts"], T0 + 700)
        self.assertEqual(row["forge"], "widget")
        self.assertIs(row["marker"], True)
        self.assertEqual(self.markers(), {}, "the marker survived a successful apply")

    def test_elapsed_is_the_gap_between_the_close_and_the_apply(self):
        """Recorded because it is the only measurement that says whether the loop closes
        promptly or the queue is a graveyard, and it cannot be recovered afterwards."""
        self.cli("apply", "--name", "widget", "--outcome", "used",
                 "--evidence", "a quote", now=T0 + 100 + 3600)
        self.assertEqual(self.rows("apply")[0]["elapsed"], 3600)

    def test_the_row_carries_the_provenance_pair_every_v2_row_carries(self):
        self.cli("apply", "--name", "widget", "--outcome", "used",
                 "--evidence", "a quote", now=T0 + 200)
        row = self.rows("apply")[0]
        self.assertEqual(row["confidence"], "measured")
        self.assertIs(row["backfilled"], False)

    def test_the_session_is_recorded_from_the_environment(self):
        self.cli("apply", "--name", "widget", "--outcome", "used",
                 "--evidence", "a quote", now=T0 + 200,
                 CLAUDE_CODE_SESSION_ID="sess-applier")
        self.assertEqual(self.rows("apply")[0]["session"], "sess-applier")

    def test_an_explicit_session_flag_wins_over_the_environment(self):
        self.cli("apply", "--name", "widget", "--outcome", "used", "--session", "sess-flag",
                 "--evidence", "a quote", now=T0 + 200,
                 CLAUDE_CODE_SESSION_ID="sess-env")
        self.assertEqual(self.rows("apply")[0]["session"], "sess-flag")

    def test_all_three_outcomes_are_accepted(self):
        """`declined` and `failed` are real outcomes of a forge that closed perfectly
        well. A queue that only accepted `used` would be discharged by lying."""
        for outcome in ("used", "declined", "failed"):
            with self.subTest(outcome=outcome):
                self.setUp()
                self.author("widget")
                self.forge_and_close("widget")
                r = self.cli("apply", "--name", "widget", "--outcome", outcome,
                             "--evidence", "a verbatim quote", now=T0 + 200)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self.rows("apply")[0]["outcome"], outcome)

    def test_an_unknown_outcome_is_refused_and_the_choices_are_named(self):
        r = self.cli("apply", "--name", "widget", "--outcome", "maybe",
                     "--evidence", "a quote", now=T0 + 200)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("used declined failed", r.stderr)
        self.assertEqual(self.rows("apply"), [])
        self.assertNotEqual(self.markers(), {}, "a refused apply consumed the marker")

    def test_apply_needs_a_name(self):
        r = self.cli("apply", "--outcome", "used", "--evidence", "q", now=T0 + 200)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("usage", r.stderr)

    def test_a_flag_with_no_value_is_refused_rather_than_eating_the_next_flag(self):
        """The defect this shape of parse exists to prevent: `--evidence --outcome used`
        recording the string "--outcome" as the verbatim evidence."""
        r = self.cli("apply", "--name", "widget", "--evidence", now=T0 + 200)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("requires a value", r.stderr)
        self.assertEqual(self.rows("apply"), [])

    def test_a_positional_argument_is_refused(self):
        r = self.cli("apply", "widget", "--outcome", "used", "--evidence", "q",
                     now=T0 + 200)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("flags only", r.stderr)


class EvidenceIsRequired(ApplyCase):
    """"used it" with no quote behind it is the unsupported completion claim this whole
    package exists to refuse, arriving through a CLI instead of through a Stop hook."""

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget")

    def test_a_missing_evidence_flag_refuses_and_writes_nothing(self):
        r = self.cli("apply", "--name", "widget", "--outcome", "used", now=T0 + 200)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--evidence is required", r.stderr)
        self.assertEqual(self.rows("apply"), [])
        self.assertNotEqual(self.markers(), {},
                            "a refused apply must leave the debt where it was")

    def test_an_empty_evidence_string_refuses(self):
        r = self.cli("apply", "--name", "widget", "--outcome", "used",
                     "--evidence", "", now=T0 + 200)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--evidence is required", r.stderr)
        self.assertEqual(self.rows("apply"), [])

    def test_whitespace_only_evidence_refuses(self):
        """A tab and two spaces is a non-empty string and an empty quote. The check is on
        what is left after whitespace, not on the length."""
        r = self.cli("apply", "--name", "widget", "--outcome", "used",
                     "--evidence", " \t\n  ", now=T0 + 200)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--evidence is required", r.stderr)
        self.assertEqual(self.rows("apply"), [])

    def test_declined_and_failed_are_held_to_the_same_bar(self):
        for outcome in ("declined", "failed"):
            with self.subTest(outcome=outcome):
                r = self.cli("apply", "--name", "widget", "--outcome", outcome,
                             now=T0 + 200)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("--evidence is required", r.stderr)


class ApplyWithNoMarker(ApplyCase):

    def test_apply_without_a_marker_refuses_with_exit_2(self):
        r = self.cli("apply", "--name", "never-forged", "--outcome", "used",
                     "--evidence", "a quote", now=T0 + 200)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.rows("apply"), [])

    def test_the_refusal_names_what_actually_is_pending(self):
        """A refusal that says only "nothing is pending for 'wdiget'" leaves a caller who
        mistyped with nowhere to go, and the cheapest way past a CLI that refuses without
        helping is to stop calling it."""
        self.author("widget")
        self.forge_and_close("widget")
        self.author("gadget")
        self.forge_and_close("gadget", start_now=T0 + 200, done_now=T0 + 300)
        r = self.cli("apply", "--name", "wdiget", "--outcome", "used",
                     "--evidence", "a quote", now=T0 + 400)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("widget", r.stderr)
        self.assertIn("gadget", r.stderr)

    def test_the_refusal_says_nothing_when_nothing_is_pending(self):
        r = self.cli("apply", "--name", "x", "--outcome", "used",
                     "--evidence", "q", now=T0 + 200)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("(nothing)", r.stderr)

    def test_force_records_the_row_and_marks_it_marker_false(self):
        """The row is a REPORT rather than something this ledger watched happen, and it
        has to say so: a reader must be able to tell the two apart afterwards."""
        r = self.cli("apply", "--name", "elsewhere", "--outcome", "used",
                     "--evidence", "applied it by hand", "--force", now=T0 + 200)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.rows("apply")
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["marker"], False)
        self.assertNotIn("elapsed", rows[0],
                         "elapsed cannot be known without a marker and must be omitted")
        self.assertIn("marker:false", r.stderr)

    def test_force_on_a_real_marker_still_removes_it_and_records_marker_true(self):
        """--force lifts the refusal; it does not turn a measured apply into a report."""
        self.author("widget")
        self.forge_and_close("widget")
        r = self.cli("apply", "--name", "widget", "--outcome", "used", "--force",
                     "--evidence", "a quote", now=T0 + 400)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIs(self.rows("apply")[0]["marker"], True)
        self.assertEqual(self.markers(), {})


class ApplyIsIdempotent(ApplyCase):
    """Both install paths are live at once, so anything that can be delivered twice will
    be. One act must produce one row."""

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget")

    def test_applying_twice_in_sequence_writes_one_row(self):
        first = self.cli("apply", "--name", "widget", "--outcome", "used",
                         "--evidence", "a quote", now=T0 + 200,
                         CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.cli("apply", "--name", "widget", "--outcome", "used",
                          "--evidence", "a quote", now=T0 + 260,
                          CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(len(self.rows("apply")), 1,
                         "a second apply appended a second row:\n" + second.stdout
                         + second.stderr)

    def test_the_second_apply_is_told_why_nothing_was_written(self):
        self.cli("apply", "--name", "widget", "--outcome", "used",
                 "--evidence", "a quote", now=T0 + 200, CLAUDE_CODE_SESSION_ID="sess-1")
        second = self.cli("apply", "--name", "widget", "--outcome", "used",
                          "--evidence", "a quote", "--force", now=T0 + 260,
                          CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("already been recorded", second.stdout)
        self.assertEqual(len(self.rows("apply")), 1)

    def test_two_concurrent_applies_produce_one_row(self):
        """The claim is taken with `ln` of a fully-written file, so exactly one process
        can win it and nothing is HELD -- a killed process leaves no lock behind, because
        there was none. Without it both callers read the marker, both appended, and the
        ledger said one act had happened twice."""
        results = []
        lock = threading.Lock()

        def go(tag):
            r = self.cli("apply", "--name", "widget", "--outcome", "used",
                         "--evidence", "quote from %s" % tag, now=T0 + 200,
                         CLAUDE_CODE_SESSION_ID="sess-race")
            with lock:
                results.append(r)

        threads = [threading.Thread(target=go, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual([r.returncode for r in results], [0] * 6,
                         "every racer must exit 0: %r"
                         % [(r.returncode, r.stderr) for r in results])
        rows = self.rows("apply")
        self.assertEqual(len(rows), 1,
                         "%d apply rows from one act: %r" % (len(rows), rows))
        self.assertEqual(self.markers(), {}, "the marker outlived the race")

    def test_a_re_delivery_arriving_after_the_debt_is_paid_loses_quietly(self):
        """THE TOMBSTONE IS UNREACHABLE FOR THE DELIVERY IT WAS BUILT FOR, and the racing
        test above catches it only sometimes (2 of 10 racers, 2 runs in 8). A second
        delivery of one act that arrives after the winner has discharged the marker finds
        no marker, does not pass `--force` -- it is the same command, delivered twice --
        and was REFUSED with exit 2 before it ever reached the claim. Its own act is on
        the ledger; being told "no forge is waiting to be applied" is both wrong and, for
        a hook wired through both install paths, a non-zero exit on every second delivery.

        The session tombstone exists precisely so that a delivery with no marker to key on
        lands on a path that is already taken. It has to be consulted before the refusal."""
        args = ("apply", "--name", "widget", "--outcome", "used",
                "--evidence", "used it, the flake stopped")
        first = self.cli(*args, now=T0 + 200, CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.markers(), {}, "the winner did not discharge the debt")
        second = self.cli(*args, now=T0 + 210, CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(second.returncode, 0,
                         "a re-delivery of a recorded act was refused: %r" % second.stderr)
        self.assertIn("already been recorded", second.stdout, second.stdout)
        self.assertEqual(len(self.rows("apply")), 1, self.rows("apply"))

    def test_a_report_with_no_marker_and_no_tombstone_is_still_refused(self):
        """The refusal itself is not being softened: with nothing on disk tying this
        session to the skill, `apply` still refuses and names what is pending."""
        r = self.cli("apply", "--name", "other", "--outcome", "used",
                     "--evidence", "a quote", now=T0 + 200,
                     CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("no forge is waiting to be applied", r.stderr)
        self.assertIn("widget", r.stderr, "the refusal did not name the real debt")

    def test_a_different_session_applying_the_same_skill_is_a_new_act(self):
        """A report that names no forge instance -- `--force`, with no marker on disk to
        tie it to one -- keys on the session instead, so a second session reporting the
        same skill is a second act. Collapsing on name alone would make the ledger
        under-report reuse forever."""
        self.cli("apply", "--name", "widget", "--outcome", "used",
                 "--evidence", "a quote", now=T0 + 200, CLAUDE_CODE_SESSION_ID="sess-1")
        self.cli("apply", "--name", "widget", "--outcome", "failed", "--force",
                 "--evidence", "tried again later, it did not help", now=T0 + 9000,
                 CLAUDE_CODE_SESSION_ID="sess-2")
        rows = self.rows("apply")
        self.assertEqual([r["outcome"] for r in rows], ["used", "failed"],
                         "a second session was folded into the first: %r" % rows)


class NamesThatNeedSanitising(ApplyCase):
    """A forge name is free text; a filename is not. The marker path goes through the
    same `tr -c 'A-Za-z0-9._-' '_' | cut -c1-96` every other script in this package uses
    for the same job, so one skill can never become two entries under two spellings."""

    def test_a_name_with_a_slash_and_a_space_round_trips_through_the_marker(self):
        r = self.cli("start", "my skill/v2", "4", "s", "--trigger", "t",
                     "--trigger-kind", "user-prompt", now=T0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.cli("done", now=T0 + 10)
        self.assertEqual(list(self.markers()), ["my_skill_v2.json"],
                         "marker filename: %r" % list(self.markers()))
        self.assertEqual(self.markers()["my_skill_v2.json"]["name"], "my skill/v2",
                         "the sanitised filename leaked into the recorded name")
        r = self.cli("apply", "--name", "my skill/v2", "--outcome", "used",
                     "--evidence", "a quote", now=T0 + 100)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.rows("apply")[0]["name"], "my skill/v2")
        self.assertEqual(self.markers(), {})

    def test_a_very_long_name_is_bounded_to_an_openable_filename(self):
        long_name = "z" * 300
        self.cli("start", long_name, "4", "s", "--trigger", "t",
                 "--trigger-kind", "user-prompt", now=T0)
        self.cli("done", now=T0 + 10)
        names = list(self.markers())
        self.assertEqual(len(names), 1, "marker files: %r" % names)
        self.assertLessEqual(len(names[0]), 96 + len(".json"))
        r = self.cli("apply", "--name", long_name, "--outcome", "used",
                     "--evidence", "a quote", now=T0 + 100)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.markers(), {})

    def test_a_name_holding_a_tab_still_round_trips(self):
        """A forge name is allowed to contain a tab -- the slot index is US-separated for
        exactly that reason -- so the marker has to survive one too."""
        tabbed = "left\tright"
        self.cli("start", tabbed, "4", "s", "--trigger", "t",
                 "--trigger-kind", "user-prompt", now=T0)
        self.cli("done", now=T0 + 10)
        self.assertEqual(list(self.markers()), ["left_right.json"])
        self.assertEqual(self.markers()["left_right.json"]["name"], tabbed)
        r = self.cli("apply", "--name", tabbed, "--outcome", "used",
                     "--evidence", "a quote", now=T0 + 100)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.rows("apply")[0]["name"], tabbed)


# ------------------------------------------------------------------------- pending

class PendingLists(ApplyCase):

    def test_pending_is_quiet_and_exits_zero_with_nothing_to_do(self):
        r = self.cli("pending", now=T0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing is waiting to be applied", r.stdout)
        self.assertEqual(self.cli("pending", "--json", now=T0).stdout, "")

    def test_pending_lists_the_oldest_debt_first(self):
        """Oldest first, because the longest-standing debt is the forge most likely to
        have been forgotten -- which is the whole reason to keep a queue at all."""
        for i, name in enumerate(("first", "second", "third")):
            self.author(name)
            self.forge_and_close(name, start_now=T0 + i * 1000,
                                 done_now=T0 + i * 1000 + 10)
        out = self.cli("pending", now=T0 + 5000).stdout
        order = [l.split()[0] for l in out.splitlines()[1:4]]
        self.assertEqual(order, ["first", "second", "third"],
                         "pending is not oldest-first:\n" + out)

    def test_pending_reports_the_age_and_whether_it_installed(self):
        self.author("widget")
        self.forge_and_close("widget")               # closes at T0 + 100
        self.forge_and_close("ghost", start_now=T0 + 200, done_now=T0 + 300)
        out = self.cli("pending", now=T0 + 100 + 7200).stdout
        widget = [l for l in out.splitlines() if l.startswith("widget")][0]
        ghost = [l for l in out.splitlines() if l.startswith("ghost")][0]
        self.assertIn("2h", widget, widget)
        self.assertIn("yes", widget, "an installed skill was not reported as installed")
        self.assertIn("NO", ghost, "a skill nobody can invoke was reported as installed")
        self.assertIn("2 forge(s) closed and not yet applied", out)

    def test_pending_json_is_one_compact_object_per_line(self):
        for i, name in enumerate(("alpha", "beta")):
            self.author(name)
            self.forge_and_close(name, start_now=T0 + i * 100,
                                 done_now=T0 + i * 100 + 10)
        out = self.cli("pending", "--json", now=T0 + 500).stdout
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 2, out)
        got = [json.loads(l) for l in lines]
        self.assertEqual([g["name"] for g in got], ["alpha", "beta"])
        self.assertEqual(got[0]["age"], 500 - 10)

    def test_pending_json_holds_back_the_verbatim_trigger(self):
        """The forging protocol holds the trigger out as test data, and the orchestrator
        subagent that is handed this CLI must not hold it. A marker carries the trigger,
        so `pending --json` is a third door onto the held-out set and it gets the same
        redaction `show` and `ledger --json` get -- named, never silent."""
        self.author("widget")
        self.forge_and_close("widget")
        got = json.loads(self.cli("pending", "--json", now=T0 + 500).stdout.strip())
        self.assertNotIn("trigger", got, got)
        self.assertEqual(got["held_out"], ["trigger"])
        self.assertIn("--full", got["held_out_note"])
        self.assertIn("held out", self.cli("pending", now=T0 + 500).stdout)

    def test_full_lifts_it_for_the_party_the_test_set_belongs_to(self):
        self.author("widget")
        self.forge_and_close("widget")
        got = json.loads(
            self.cli("pending", "--json", "--full", now=T0 + 500).stdout.strip())
        self.assertEqual(got["trigger"], "the user said: stop the flaky test")
        self.assertNotIn("held_out", got)

    def test_the_file_on_disk_is_never_redacted(self):
        """Redaction is about what the CLI VOLUNTEERS. The record keeps everything."""
        self.author("widget")
        self.forge_and_close("widget")
        raw = json.loads((self.pending_dir / "widget.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["trigger"], "the user said: stop the flaky test")

    def test_an_unparseable_marker_is_skipped_not_deleted(self):
        """Same rule the forge slots follow: a half-written file from a concurrent writer,
        or a marker from a future version, must not take the queue down with it."""
        self.author("widget")
        self.forge_and_close("widget")
        junk = self.pending_dir / "junk.json"
        junk.write_text("{not json at all", encoding="utf-8")
        r = self.cli("pending", now=T0 + 500)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 forge(s) closed and not yet applied", r.stdout)
        self.assertTrue(junk.exists(), "an unreadable marker was deleted")

    def test_apply_says_how_many_debts_are_left(self):
        for i, name in enumerate(("alpha", "beta")):
            self.author(name)
            self.forge_and_close(name, start_now=T0 + i * 100,
                                 done_now=T0 + i * 100 + 10)
        r = self.cli("apply", "--name", "alpha", "--outcome", "used",
                     "--evidence", "a quote", now=T0 + 500)
        self.assertIn("1 forge(s) still waiting", r.stdout)


# ------------------------------------------- the existing join must not move an inch

class ExistingReadersAreUnchanged(ApplyCase):
    """THE RULE THIS SCHEMA RESTS ON: every reader selects the events it understands BY
    NAME, so a ledger holding `apply` rows is counted by the start/done join exactly as
    it was before. A reader that classified by exclusion -- anything that is not a start
    is an outcome -- would fold every apply row into the forge count on the day this
    landed, which is the shape of defect `tests/test_ledger_v2.py` pins for `use` rows.
    """

    def a_mixed_ledger(self):
        self.write_ledger(
            {"event": "horizon", "ts": T0 - 1, "known_from": T0 - 1,
             "confidence": "measured", "backfilled": False},
            {"event": "start", "name": "widget", "ts": T0, "steps": 8, "summary": "s",
             "project": "/Users/me/proj", "trigger_verbatim": "the user asked",
             "trigger_kind": "user-prompt"},
            {"event": "origin", "ts": T0 + 1, "name": "widget", "origin": "forged",
             "confidence": "measured", "backfilled": False},
            {"event": "done", "name": "widget", "ts": T0 + 600, "steps": 8,
             "summary": "s", "project": "/Users/me/proj", "step": 8, "phase": "ok",
             "duration": 600, "rounds": 3, "rounds_planned": 3},
            {"event": "use", "ts": T0 + 1000, "name": "widget", "ok": True,
             "harness": False, "recorded": "live", "session": "s0",
             "confidence": "measured", "backfilled": False},
            # Five apply rows. None of them is a forge, a start or an outcome.
            *[{"event": "apply", "ts": T0 + 2000 + i, "name": "widget",
               "outcome": "used", "evidence": "a quote", "marker": True,
               "forge": "widget", "session": "s%d" % i, "elapsed": 60,
               "confidence": "measured", "backfilled": False} for i in range(5)],
            {"event": "verdict", "ts": T0 + 3000, "name": "widget", "verdict": "WORKED",
             "evidence": "a quote", "confidence": "measured", "backfilled": False},
        )

    def test_the_forge_count_is_unchanged_by_apply_rows(self):
        self.a_mixed_ledger()
        out = self.cli("ledger", now=T0 + 4000).stdout
        self.assertIn("1 forge(s)", out, "an apply row was counted as a forge:\n" + out)
        self.assertIn("1 done", out)
        self.assertIn("0 abandoned", out)
        self.assertIn("0 never closed out", out)

    def test_the_table_prints_one_row_for_the_one_forge(self):
        self.a_mixed_ledger()
        out = self.cli("ledger", now=T0 + 4000).stdout
        table = [l for l in out.splitlines() if l.startswith("2026-")]
        self.assertEqual(len(table), 1, "the join grew rows:\n" + out)
        self.assertIn("[done]", table[0])

    def test_no_orphan_footnote_is_produced_by_apply_rows(self):
        """An outcome with no start is a real and important condition. An apply row is
        not one, and a reader that thought otherwise would print a warning about missing
        start records every time the loop closed properly."""
        self.a_mixed_ledger()
        out = self.cli("ledger", now=T0 + 4000).stdout
        self.assertNotIn("have no matching start record", out, out)

    def test_the_apply_rows_are_counted_by_name_in_their_own_line(self):
        self.a_mixed_ledger()
        out = self.cli("ledger", now=T0 + 4000).stdout
        self.assertIn("5 apply row(s): 5 used, 0 declined, 0 failed", out, out)

    def test_a_ledger_with_no_apply_rows_says_nothing_about_them(self):
        """A zero printed where nothing was recorded reads as a measurement. The line is
        absent when there is nothing to say, exactly like the orphan footnote."""
        self.author("widget")
        self.forge_and_close("widget")
        out = self.cli("ledger", now=T0 + 400).stdout
        self.assertNotIn("apply row(s)", out, out)

    def test_ledger_json_carries_apply_rows_one_per_line(self):
        self.a_mixed_ledger()
        out = self.cli("ledger", "--json", now=T0 + 4000).stdout
        rows = [json.loads(l) for l in out.splitlines() if l.strip()]
        self.assertEqual(len([r for r in rows if r.get("event") == "apply"]), 5)

    def test_skillreport_still_reads_one_finished_forge(self):
        """`bin/skillreport` selects `start`, `done`/`fail`, `origin`, `use`, `verdict`
        and `horizon` by name and nothing else, so apply rows are invisible to it. It
        does not yet REPORT them -- that is a separate change to a file this test does
        not own -- but it must not miscount because of them."""
        report = REPO / "bin" / "skillreport"
        self.a_mixed_ledger()
        r = subprocess.run([str(report)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, cwd=str(self.proj),
                           env=self.env())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("of 1 finished forges", r.stdout,
                      "the reuse denominator moved when apply rows were added:\n"
                      + r.stdout)

    def test_the_horizon_is_still_written_exactly_once(self):
        self.author("widget")
        self.forge_and_close("widget")
        self.cli("apply", "--name", "widget", "--outcome", "used",
                 "--evidence", "a quote", now=T0 + 200)
        self.assertEqual(len(self.rows("horizon")), 1)

    def test_an_apply_into_an_empty_ledger_still_gets_a_horizon(self):
        r = self.cli("apply", "--name", "x", "--outcome", "used", "--force",
                     "--evidence", "a quote", now=T0 + 200)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.rows("horizon")), 1)
        self.assertEqual(len(self.rows("apply")), 1)


# ------------------------------------------------- a second forge owes a second debt

class DebtsAreDistinguishedByForgeInstance(ApplyCase):
    """RE-FORGING A SKILL AFTER A RED-TEAM FIX IS THIS PROTOCOL'S OWN PRESCRIBED WORKFLOW,
    so one session routinely closes two forges of one name and owes two separate debts.
    Keyed on name+session the second one could not be paid: the first apply's claim was
    still on disk -- reaped only at `-mmin +60` -- so the second apply took the LOSER
    branch, deleted the fresh marker, said "already been recorded", and exited 0. One row
    on disk, and the second forge's evidence quote, which nothing else holds, gone.

    The claim now names the FORGE INSTANCE, which `done` stamps into the marker. What the
    claim was there for is unchanged and is asserted here too: one act delivered twice is
    still one row."""

    def two_forges(self, name="widget", session="sess-1"):
        self.author(name)
        self.forge_and_close(name, start_now=T0, done_now=T0 + 100,
                             CLAUDE_CODE_SESSION_ID=session)
        first = self.cli("apply", "--name", name, "--outcome", "used",
                         "--evidence", "it fixed the parse bug", now=T0 + 200,
                         CLAUDE_CODE_SESSION_ID=session)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.forge_and_close(name, start_now=T0 + 300, done_now=T0 + 400,
                             CLAUDE_CODE_SESSION_ID=session)
        return first

    def test_a_second_forge_in_one_session_can_be_applied(self):
        self.two_forges()
        self.assertEqual(list(self.markers()), ["widget.json"],
                         "the second done left no debt to pay")
        second = self.cli("apply", "--name", "widget", "--outcome", "used",
                          "--evidence", "second problem, also solved", now=T0 + 500,
                          CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotIn("already been recorded", second.stdout,
                         "the second debt was swallowed by the first apply's claim")
        self.assertEqual([r["evidence"] for r in self.rows("apply")],
                         ["it fixed the parse bug", "second problem, also solved"],
                         "the second forge's evidence was lost: %r" % self.rows("apply"))
        self.assertEqual(self.markers(), {}, "the second debt was not discharged")

    def test_the_two_forges_are_stamped_with_different_instances(self):
        """The id is what separates the two debts, so two forges of one name must never
        share one. It is the same id `close_forge` claims its outcome on."""
        self.author("widget")
        self.forge_and_close("widget", start_now=T0, done_now=T0 + 100)
        first = self.markers()["widget.json"]["forge_id"]
        self.cli("apply", "--name", "widget", "--outcome", "used",
                 "--evidence", "a quote", now=T0 + 200)
        self.forge_and_close("widget", start_now=T0 + 300, done_now=T0 + 400)
        second = self.markers()["widget.json"]["forge_id"]
        self.assertNotEqual(first, second,
                            "two forges shared one instance id (%r); the clock is pinned, "
                            "so an id built from the clock alone collapses here" % first)

    def test_one_act_delivered_twice_is_still_one_row(self):
        """The property the claim exists for, kept. Both deliveries find the SAME marker,
        so both compute the same instance and only one may append."""
        self.author("widget")
        self.forge_and_close("widget")
        args = ("apply", "--name", "widget", "--outcome", "used",
                "--evidence", "used it, the flake stopped")
        first = self.cli(*args, now=T0 + 200, CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.cli(*args, "--force", now=T0 + 210, CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("already been recorded", second.stdout)
        self.assertEqual(len(self.rows("apply")), 1,
                         "a re-delivery of one act wrote a second row: %r"
                         % self.rows("apply"))

    def test_a_racer_reading_the_marker_as_it_is_deleted_writes_no_second_row(self):
        """THE HAZARD THE INSTANCE KEY INTRODUCED, AND IT IS NOT HYPOTHETICAL. Keying on
        something read OUT OF the marker means the key is read from a file the winner is
        about to delete. Read field by field, a late racer got the close epoch and then an
        empty `forge_id`, fell back to a different key, won it and appended a SECOND row
        for one act -- 2 rows from 6 racers, first run. The CLI now takes one snapshot of
        the marker and derives every field from it, and the winner claims the session key
        as a tombstone before it removes the marker, so a racer that sees no marker at all
        still lands on a claim that is taken."""
        results = []
        lock = threading.Lock()

        def go(tag):
            r = self.cli("apply", "--name", "widget", "--outcome", "used",
                         "--evidence", "quote from %s" % tag, now=T0 + 200,
                         CLAUDE_CODE_SESSION_ID="sess-race")
            with lock:
                results.append(r)

        self.author("widget")
        self.forge_and_close("widget")
        threads = [threading.Thread(target=go, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        rows = self.rows("apply")
        self.assertEqual(len(rows), 1,
                         "%d apply rows from one act: %r" % (len(rows), rows))
        self.assertEqual([r.returncode for r in results], [0] * 10,
                         "a racer failed instead of losing quietly: %r"
                         % [(r.returncode, r.stdout, r.stderr) for r in results])
        self.assertEqual(self.markers(), {}, "the marker outlived the race")

    def test_two_session_ids_differing_past_the_64th_character_are_two_acts(self):
        """The house rule is one sanitising expression everywhere -- `tr -c 'A-Za-z0-9._-'
        '_' | cut -c1-96`. This site spelled it `cut -c1-64`, three lines under a comment
        claiming it was the same expression. Two ids that agree for 64 characters then
        collapsed onto one claim and the second act was never recorded."""
        self.author("widget")
        self.forge_and_close("widget")
        head = "s" * 64
        one, two = head + "-alpha", head + "-beta"
        self.cli("apply", "--name", "widget", "--outcome", "used",
                 "--evidence", "first session", now=T0 + 200, CLAUDE_CODE_SESSION_ID=one)
        second = self.cli("apply", "--name", "widget", "--outcome", "used", "--force",
                          "--evidence", "second session", now=T0 + 300,
                          CLAUDE_CODE_SESSION_ID=two)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual([r["session"] for r in self.rows("apply")], [one, two],
                         "two session ids collapsed onto one claim: %r"
                         % self.rows("apply"))


# ------------------------------------------------- a debt is paid only if the row lands

class AFailedAppendKeepsTheDebt(ApplyCase):
    """THE FALSE COMPLETION CLAIM, ARRIVING THROUGH THIS PACKAGE'S OWN CLI. The append was
    `printf ... >> "$LEDGER" 2>/dev/null || true` with an unconditional `rm -f` on the
    marker underneath it, so with the ledger read-only `apply` wrote nothing, deleted the
    debt, printed "The loop is closed.", and exited 0 -- and `pending` then said nothing
    was waiting. hooks/claim-gate.sh exists to refuse exactly that shape.

    chmod 444 on a real file, not a mock: the failure has to come from the filesystem the
    way it would in the field."""

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget")
        self.ledger.chmod(0o444)

    def tearDown(self):
        if self.ledger.exists():
            self.ledger.chmod(0o644)
        super().tearDown()

    def apply_it(self, **extra):
        return self.cli("apply", "--name", "widget", "--outcome", "used",
                        "--evidence", "used it, the flake stopped", now=T0 + 200, **extra)

    def test_a_failed_append_exits_non_zero_and_says_nothing_was_recorded(self):
        r = self.apply_it()
        self.assertNotEqual(r.returncode, 0,
                            "a write that never happened exited 0: %r" % r.stdout)
        self.assertIn("NOTHING was recorded", r.stderr, r.stderr)
        self.assertNotIn("The loop is closed", r.stdout,
                         "the loop was reported closed with no row on disk")

    def test_the_debt_survives_so_it_can_still_be_paid(self):
        self.apply_it()
        self.assertEqual(list(self.markers()), ["widget.json"],
                         "the debt was deleted by an apply that wrote nothing")
        self.ledger.chmod(0o644)
        out = self.cli("pending", now=T0 + 300).stdout
        self.assertIn("widget", out, "pending reported nothing waiting: %r" % out)

    def test_no_row_reached_the_ledger(self):
        self.apply_it()
        self.ledger.chmod(0o644)
        self.assertEqual(self.rows("apply"), [])

    def test_the_shell_error_is_suppressed_the_way_it_was_meant_to_be(self):
        """`2>/dev/null` on the redirect never suppressed anything: redirections are
        applied left to right, so `>>` is opened first and the SHELL reports the failure
        to a stderr that is still the terminal. The reproduction printed bash's own
        "Permission denied", naming a line number, above the tidy message."""
        r = self.apply_it()
        self.assertNotIn("Permission denied", r.stderr,
                         "bash's own error leaked past the redirect: %r" % r.stderr)
        self.assertNotIn("bin/skillforge: line", r.stderr, r.stderr)

    def test_the_retry_after_the_ledger_is_fixed_records_the_row(self):
        """The claim is released when the act it was taken for did not happen. Left in
        place it would send the retry -- the entire point of exiting non-zero -- down the
        loser branch, where it would delete the debt it came back to pay."""
        self.apply_it()
        self.ledger.chmod(0o644)
        r = self.apply_it()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([x["evidence"] for x in self.rows("apply")],
                         ["used it, the flake stopped"],
                         "the retry was refused as a duplicate of a row that never landed")
        self.assertEqual(self.markers(), {})


# ------------------------------------------------------- installed:false is a real answer

class InstalledFalseReachesTheRow(ApplyCase):
    """`field()` read `.[$k] // empty`, and jq's `//` takes the right-hand side for `false`
    as well as for null -- measured: `echo '{"installed":false}' | jq -r '.["installed"] //
    empty'` prints nothing. So the marker's `installed:false` read back as "" and the row
    OMITTED the field, making a skill nobody could invoke byte-identical to a `--force`
    report that never had a marker. That is the one case the field exists to record."""

    def apply_row(self, name):
        r = self.cli("apply", "--name", name, "--outcome", "used",
                     "--evidence", "used it anyway", now=T0 + 200)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.rows("apply")
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_a_skill_nobody_could_invoke_is_recorded_as_installed_false(self):
        self.forge_and_close("ghost")            # no SKILL.md was ever authored
        self.assertIs(self.markers()["ghost.json"]["installed"], False)
        row = self.apply_row("ghost")
        self.assertIn("installed", row,
                      "installed:false was dropped on the way into the row: %r" % row)
        self.assertIs(row["installed"], False)

    def test_an_installed_skill_still_records_installed_true(self):
        self.author("widget")
        self.forge_and_close("widget")
        self.assertIs(self.apply_row("widget")["installed"], True)

    def test_a_report_with_no_marker_is_the_case_that_omits_the_field(self):
        """Absent means "nothing here watched this happen". It must not also mean "we
        watched it and nothing was installed" -- those are opposite facts."""
        r = self.cli("apply", "--name", "never-forged", "--outcome", "used", "--force",
                     "--evidence", "a report, not something this ledger watched",
                     now=T0 + 200)
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.rows("apply")[0]
        self.assertNotIn("installed", row, row)
        self.assertIs(row["marker"], False)


# ------------------------------------------------------------- evidence the flag can carry

class EvidenceIsReadAsBytes(ApplyCase):
    """BSD `tr` ABORTS with "Illegal byte sequence" on a byte that is not valid in the
    ambient locale, and the emptiness guard read the resulting empty string as "no
    evidence was given". Measured under LANG=en_US.UTF-8 with a quote beginning \377:
    "tr: Illegal byte sequence", then "--evidence is required", exit 2, for 40 characters
    of evidence. A verbatim quote is pasted terminal output; latin-1, a truncated
    multibyte character and a stray control byte are all ordinary in it.

    On a machine with no UTF-8 locale installed the ambient locale is already C and there
    is nothing here to trip over, so this passes trivially there. Where the locale exists
    -- macOS, and any glibc box that has it -- it is the reproduction."""

    UTF8 = "en_US.UTF-8"

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget")

    def test_evidence_holding_a_byte_invalid_in_the_locale_is_accepted(self):
        # surrogateescape is how Python carries a byte that is not valid UTF-8 through an
        # argv that is typed as text; subprocess encodes it back to the same raw byte.
        quote = b"\xffthe skill fired and closed the parse bug".decode("utf-8",
                                                                      "surrogateescape")
        r = self.cli("apply", "--name", "widget", "--outcome", "used",
                     "--evidence", quote, now=T0 + 200, LANG=self.UTF8)
        self.assertEqual(r.returncode, 0,
                         "43 characters of evidence were refused as empty:\n"
                         + r.stdout + r.stderr)
        self.assertNotIn("--evidence is required", r.stderr)
        self.assertEqual(len(self.rows("apply")), 1)

    def test_evidence_that_really_is_empty_is_still_refused_under_that_locale(self):
        """The guard must still do its job; the fix is to the locale, not to the bar."""
        r = self.cli("apply", "--name", "widget", "--outcome", "used",
                     "--evidence", "   \t  ", now=T0 + 200, LANG=self.UTF8)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--evidence is required", r.stderr)
        self.assertEqual(self.rows("apply"), [])


class EvidenceIsBounded(ApplyCase):
    """The quote is appended verbatim and forever, and every reader of this ledger slurps
    the whole file through `jq -s`, so one pasted megabyte is carried by every later
    `ledger`, `pending` and `skillreport` run. The bound refuses a mistake -- a file
    redirected into the flag -- rather than truncating, because a truncated quote is still
    presented as verbatim and that is the flag's whole value.

    The environment here carries no LANG, so the CLI runs in the C locale and `${#...}`
    counts bytes; the limit is therefore both bytes and characters."""

    LIMIT = EVIDENCE_MAX

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget")

    def apply_evidence(self, quote):
        return self.cli("apply", "--name", "widget", "--outcome", "used",
                        "--evidence", quote, now=T0 + 200)

    def test_a_quote_at_the_limit_is_accepted(self):
        r = self.apply_evidence("x" * self.LIMIT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.rows("apply")[0]["evidence"]), self.LIMIT)

    def test_one_byte_past_the_limit_is_refused_and_the_figures_are_named(self):
        r = self.apply_evidence("x" * (self.LIMIT + 1))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(str(self.LIMIT + 1), r.stderr, r.stderr)
        self.assertIn(str(self.LIMIT), r.stderr, r.stderr)

    def test_a_refused_quote_writes_no_row_and_keeps_the_debt(self):
        self.apply_evidence("x" * (self.LIMIT + 1))
        self.assertEqual(self.rows("apply"), [])
        self.assertEqual(list(self.markers()), ["widget.json"],
                         "a refused apply discharged the debt anyway")


# ------------------------------------------------ a cleanup removes only its own work

class TheFailedAppendCleanupRemovesOnlyWhatItCreated(ApplyCase):
    """THE RELEASE THAT KEPT THE DEBT ALSO DESTROYED SOMEBODY ELSE'S RECEIPT. A failed
    append releases the claims so the retry can win them back -- correct for the claims
    this invocation took, and wrong for the SESSION TOMBSTONE, which it links only when
    that path was free. When it was not free the tombstone belongs to an EARLIER apply in
    the same session, the one whose row is already on the ledger; deleting it hands the
    session key back, and the next report that has no marker to key on -- a `--force`
    re-delivery of that first act -- wins it and writes the row a second time.

    The sequence is this protocol's own prescribed workflow: forge, apply, re-forge after
    a red-team fix, apply again. Only the second apply fails, and the row it damages is
    the first one's."""

    SESSION = "sess-1"
    ACT_ONE = "act one: it fixed the parse bug"
    ACT_TWO = "act two: the re-forge solved the next one"

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget", start_now=T0, done_now=T0 + 100,
                             CLAUDE_CODE_SESSION_ID=self.SESSION)
        first = self.cli("apply", "--name", "widget", "--outcome", "used",
                         "--evidence", self.ACT_ONE, now=T0 + 200,
                         CLAUDE_CODE_SESSION_ID=self.SESSION)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.tombstone = self.state / "forge" / (".apply.widget.s.%s.claim" % self.SESSION)
        self.assertTrue(self.tombstone.exists(),
                        "act one left no session tombstone; claims: %r" % self.claims())
        # The re-forge, and an apply that cannot reach the ledger.
        self.forge_and_close("widget", start_now=T0 + 300, done_now=T0 + 400,
                             CLAUDE_CODE_SESSION_ID=self.SESSION)
        self.ledger.chmod(0o444)
        self.failed = self.cli("apply", "--name", "widget", "--outcome", "used",
                               "--evidence", self.ACT_TWO, now=T0 + 500,
                               CLAUDE_CODE_SESSION_ID=self.SESSION)
        self.ledger.chmod(0o644)
        self.assertNotEqual(self.failed.returncode, 0,
                            "the read-only ledger did not fail the append: %r"
                            % self.failed.stdout)

    def test_the_earlier_applys_tombstone_survives_a_later_failed_append(self):
        self.assertTrue(self.tombstone.exists(),
                        "a failed append deleted a tombstone it never created; the "
                        "session key is free again and act one's row is unprotected. "
                        "claims now: %r" % self.claims())

    def test_the_debt_the_failed_append_could_not_pay_is_still_owed(self):
        """The half that already worked, kept: this invocation's OWN claim is released
        and its marker stays, so the retry can still pay it."""
        self.assertEqual(list(self.markers()), ["widget.json"], self.failed.stderr)
        self.assertEqual([r["evidence"] for r in self.rows("apply")], [self.ACT_ONE],
                         "the failed append wrote a row after all: %r" % self.rows("apply"))

    def test_a_re_delivery_of_the_first_act_cannot_write_a_second_row(self):
        """The consequence, end to end. The second debt is paid from another session --
        `apply` runs wherever the skill was used -- and then the first act is delivered a
        second time, as a doubly-wired hook or a retried command. Exactly one row per act,
        or the ledger says a skill was applied three times on the strength of two."""
        paid = self.cli("apply", "--name", "widget", "--outcome", "used",
                        "--evidence", self.ACT_TWO, now=T0 + 600,
                        CLAUDE_CODE_SESSION_ID="sess-2")
        self.assertEqual(paid.returncode, 0, paid.stderr)
        self.assertEqual(self.markers(), {}, "the second debt was not discharged")
        again = self.cli("apply", "--name", "widget", "--outcome", "used", "--force",
                         "--evidence", self.ACT_ONE, now=T0 + 700,
                         CLAUDE_CODE_SESSION_ID=self.SESSION)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual([r["evidence"] for r in self.rows("apply")],
                         [self.ACT_ONE, self.ACT_TWO],
                         "one act was recorded twice: %r" % self.rows("apply"))


# ------------------------------------------- the loser heals nothing it cannot point at

ANCHOR_AFTER_APPLY_CLAIM = r'^      if ln "\$a_tmp" "\$a_claim" 2>/dev/null; then$'


class TheSecondDeliveryHealsOnlyARowThatLanded(ApplyCase):
    """EVERY HOOK EVENT IS DELIVERED TWICE, SO THE LOSER IS THE NORMAL CASE. It deletes
    the pending marker to finish work the winner may not have reached -- and that heal
    ASSUMED the winner's append succeeded. A winner killed between the claim and the
    append writes no row and keeps its marker on purpose; the loser then deleted that
    marker, printed "has already been recorded", and exited 0. The debt is gone, no row
    exists, `pending` says nothing is waiting: the same false completion claim a failed
    append used to produce, arriving by the other door.

    The winner really dies here -- `kill -9 $$` injected after the claim, the technique
    tests/test_forge_close_race.py uses -- because the state between those two statements
    is not reachable from outside the process."""

    EVIDENCE = "used it, the flake stopped"

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget")
        self.killer = self.variant(
            "skillforge-killed-after-apply-claim", ANCHOR_AFTER_APPLY_CLAIM,
            lambda m: m.group(0) + "\n        kill -9 $$")

    def deliver(self, cli_path=None, now=T0 + 200):
        return self.cli("apply", "--name", "widget", "--outcome", "used",
                        "--evidence", self.EVIDENCE, now=now,
                        CLAUDE_CODE_SESSION_ID="sess-1", cli_path=cli_path)

    def test_the_killed_winner_leaves_a_claim_a_debt_and_no_row(self):
        """The precondition, asserted rather than assumed: without this the test below
        would pass against anything."""
        r = self.deliver(cli_path=self.killer)
        self.assertNotEqual(r.returncode, 0, "the injected kill did not fire")
        self.assertEqual(self.rows("apply"), [],
                         "the winner appended before it died; the anchor moved")
        self.assertEqual(list(self.markers()), ["widget.json"])
        self.assertTrue([c for c in self.claims() if ".f." in c],
                        "no forge-instance claim was left behind: %r" % self.claims())

    def test_the_second_delivery_keeps_the_debt_when_no_row_landed(self):
        self.deliver(cli_path=self.killer)
        second = self.deliver(now=T0 + 210)
        self.assertEqual(self.rows("apply"), [],
                         "the loser appended a row it was not entitled to")
        self.assertEqual(list(self.markers()), ["widget.json"],
                         "the debt was deleted although NO apply row exists: stdout %r, "
                         "stderr %r" % (second.stdout, second.stderr))

    def test_the_second_delivery_does_not_report_the_act_as_recorded(self):
        self.deliver(cli_path=self.killer)
        second = self.deliver(now=T0 + 210)
        self.assertNotIn("already been recorded", second.stdout,
                         "it claimed the act was recorded with no row on disk")
        self.assertNotIn("The loop is closed", second.stdout, second.stdout)
        said = second.stdout + second.stderr
        self.assertIn("nothing was written", said,
                      "the caller was not told that nothing was written: %r" % said)
        self.assertIn("the debt is still owed", said,
                      "the caller was not told the debt survives: %r" % said)

    def test_pending_still_lists_the_debt_afterwards(self):
        self.deliver(cli_path=self.killer)
        self.deliver(now=T0 + 210)
        out = self.cli("pending", now=T0 + 300).stdout
        self.assertIn("widget", out,
                      "pending reported nothing waiting after two deliveries that "
                      "recorded nothing: %r" % out)

    def test_a_second_delivery_of_a_row_that_did_land_still_discharges_the_marker(self):
        """The heal itself is not being removed -- it is what stops a discharged debt
        sitting in the queue forever when the winner is killed between the append and the
        marker deletion. With the row really on the ledger it still fires."""
        marker = self.pending_dir / "widget.json"
        saved = marker.read_text(encoding="utf-8")
        first = self.deliver()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(len(self.rows("apply")), 1, self.rows("apply"))
        # A winner killed AFTER the append and BEFORE the marker deletion leaves exactly
        # this: the row on the ledger, the claim taken, the debt still in the queue. Same
        # marker, so the loser computes the same instance and loses on the same claim.
        marker.write_text(saved, encoding="utf-8")
        second = self.deliver(now=T0 + 260)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("already been recorded", second.stdout, second.stdout + second.stderr)
        self.assertEqual(len(self.rows("apply")), 1,
                         "the second delivery wrote a second row: %r" % self.rows("apply"))
        self.assertEqual(self.markers(), {},
                         "the discharged debt was left sitting in the queue")


# --------------------------------------------- `false` has to survive TWO spellings

class TheFalseHazardHasTwoSpellings(ApplyCase):
    """`.[$k] // empty` took the right-hand side for `null` AND for `false`, so a marker
    holding `installed:false` read back as "" and the row omitted the field -- a skill
    nobody could invoke, applied anyway, byte-identical to a `--force` report that never
    had a marker. The accessor was repaired. THE ACCESSOR IS NOT WHAT CARRIES THE FIELD:
    `apply` reads the marker through one jq SNAPSHOT (five separate reads could straddle a
    racing applier's deletion of it), and that snapshot spells the rule again, inline.

    So "fix it once at the accessor and every caller is safe" is false, and this pins it
    both ways: the shipped CLI records the field, and a reconstruction whose snapshot
    folds `false` back into `//` loses it while `field()` stays repaired."""

    # ANCHORED ON THE SNAPSHOT LINE, NOT ON THE EXPRESSION. The comment above `field()`
    # QUOTES that expression verbatim, so a pattern matching it alone rewrote the COMMENT
    # and left the code untouched -- a reconstruction that was really a copy of the
    # unmodified script, which `variant`'s match count cannot see. It was caught here only
    # because this test asserts on behaviour rather than on the rewrite.
    FOLDED = (r'\[\(\.closed // 0\), '
              r'\(\.installed \| if \. == null then "" else tostring end\),')

    def apply_ghost(self, cli_path=None):
        """A forge that produced no SKILL.md: installed:false is the whole point of it."""
        self.forge_and_close("ghost")
        self.assertIs(self.markers()["ghost.json"]["installed"], False)
        r = self.cli("apply", "--name", "ghost", "--outcome", "used",
                     "--evidence", "opened it, there was nothing to open", now=T0 + 200,
                     cli_path=cli_path)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.rows("apply")
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_the_shipped_cli_records_installed_false(self):
        self.assertIs(self.apply_ghost()["installed"], False,
                      "the one case the field exists to record was dropped")

    def test_repairing_only_the_accessor_would_not_have_carried_it(self):
        folded = self.variant("skillforge-installed-folded", self.FOLDED,
                              '[(.closed // 0), (.installed // ""),')
        self.assertIn("if . == null then empty else . end",
                      folded.read_text(encoding="utf-8"),
                      "the reconstruction also unpicked field(); it is meant to leave the "
                      "accessor repaired and fold only the snapshot")
        self.assertNotIn("installed", self.apply_ghost(cli_path=folded),
                         "the snapshot is not the spelling that carries this field after "
                         "all -- re-read the comment above field() in bin/skillforge")


# --------------------------------------------------------------------- the help text

class HelpMentionsApply(ApplyCase):
    """The header block is the help text, printed by a `sed` range that has to be moved
    by hand when the header grows. Too small silently truncates it; too large prints
    shell code at the user. Both are caught here."""

    def test_help_reaches_the_end_of_the_header_and_no_further(self):
        out = self.cli("help").stdout
        self.assertIn("skillforge apply", out, out)
        self.assertIn("skillforge pending", out)
        self.assertIn("FIVE QUESTIONS", out)
        self.assertIn("apply-pending/", out)
        self.assertIn("skillforge recreates it on the next forge", out,
                      "the help range stops short of the end of the header")
        self.assertNotIn("set -uo pipefail", out,
                         "the help range ran past the header into shell code")


# ------------------------------------------- the landed-check has to survive a long row

class TheLandedCheckHasNoPatternLengthLimit(ApplyCase):
    """THE LOSER ASKS THE LEDGER WHETHER THE WINNER'S ROW LANDED, AND THE TOOL IT ASKED
    WITH HAD A CEILING. `grep -F -x -q -e "$row"` against BSD grep 2.6.0-FreeBSD -- the
    `grep` on the front of this suite's own PATH, /usr/bin -- aborts with `grep: out of
    memory` and exit 2 once the fixed pattern passes a certain length. Nothing here quotes
    that length: `ceiling()` below BISECTS it on the machine the test runs on, and every
    case prints what it found together with the length of the row it built.

    An ordinary long quote produces a row past it. Exit 2 reads as "no match", the loser
    concludes the winner recorded nothing, and it then keeps a debt that has in fact been
    discharged and tells the caller the act was never recorded. Wrong in the direction
    that loses a paid debt, about a row sitting on the ledger.

    The scenario is the one the heal exists for: a winner killed after its append and
    before its `rm` of the marker leaves the row on the ledger, the claim taken and the
    debt still in the queue, and the next delivery of the same act has to finish it.
    """

    SESSION = "sess-long"
    _ceiling = "unmeasured"

    def setUp(self):
        super().setUp()
        self.author("widget")

    def ceiling(self):
        """The longest fixed pattern /usr/bin/grep accepts here, by bisection -- measured,
        not quoted, so this test cannot be reading a stale figure off a comment. Returns
        None where there is no ceiling below the search top (GNU grep on Linux), in which
        case there is nothing to probe on either side of."""
        if TheLandedCheckHasNoPatternLengthLimit._ceiling != "unmeasured":
            return TheLandedCheckHasNoPatternLengthLimit._ceiling
        probe = self.root / "grep-probe.txt"

        def accepts(n):
            probe.write_text("x" * n + "\n", encoding="utf-8")
            r = subprocess.run(["/usr/bin/grep", "-F", "-x", "-q", "-e", "x" * n,
                                str(probe)], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL)
            return r.returncode == 0

        lo, hi = 1, 1 << 18          # well inside ARG_MAX, so argv is never the failure
        self.assertTrue(accepts(lo), "/usr/bin/grep refused a one-character pattern")
        if accepts(hi):
            found = None
        else:
            while lo + 1 < hi:
                mid = (lo + hi) // 2
                if accepts(mid):
                    lo = mid
                else:
                    hi = mid
            found = lo
        TheLandedCheckHasNoPatternLengthLimit._ceiling = found
        print("\n  /usr/bin/grep -F -x takes patterns up to %s characters"
              % ("no ceiling below %d" % (1 << 18) if found is None else found))
        return found

    def cycle(self, evidence, start, done, apply_at):
        """One whole forge -> close -> apply, returning the marker bytes as they were just
        before the apply -- which is exactly what a winner killed before its `rm` leaves."""
        self.forge_and_close("widget", start_now=start, done_now=done,
                             CLAUDE_CODE_SESSION_ID=self.SESSION)
        saved = (self.pending_dir / "widget.json").read_text(encoding="utf-8")
        r = self.cli("apply", "--name", "widget", "--outcome", "used",
                     "--evidence", evidence, now=apply_at,
                     CLAUDE_CODE_SESSION_ID=self.SESSION)
        self.assertEqual(r.returncode, 0, r.stderr)
        return saved

    def overhead(self):
        """How many characters of the row are NOT the evidence, measured on a real row
        rather than reconstructed. The probe runs on the same clock offsets as the row
        under test, so `ts` and `elapsed` have the same number of digits in both."""
        probe = "x" * 1000
        self.cycle(probe, T0, T0 + 100, T0 + 200)
        row = self.ledger.read_text(encoding="utf-8").splitlines()[-1]
        self.assertIn(probe, row)
        return len(row) - len(probe)

    def deliver_again_and_assert_healed(self, target=None, evidence_len=None):
        """Land a row -- of exactly `target` characters, or built from `evidence_len`
        characters of evidence -- then put the debt back the way a killed winner leaves it
        and deliver the same act again."""
        over = self.overhead()
        want = evidence_len if target is None else target - over
        self.assertGreater(want, 0, "the row overhead alone is past the target")
        self.assertLessEqual(want, EVIDENCE_MAX,
                             "%r characters of evidence is past the cap the CLI states"
                             % want)
        evidence = "y" * want
        saved = self.cycle(evidence, T0 + 300, T0 + 400, T0 + 500)
        row = self.ledger.read_text(encoding="utf-8").splitlines()[-1]
        # What /usr/bin/grep does with a pattern that long, printed rather than asserted:
        # the point is that the CLI no longer cares, and the ceiling is a property of the
        # platform this happens to run on.
        probe = subprocess.run(["/usr/bin/grep", "-F", "-x", "-q", "-e", row,
                                str(self.ledger)], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL)
        print("  row on the ledger: %d characters (evidence %d); /usr/bin/grep -F -x on "
              "it: exit %d %r" % (len(row), want, probe.returncode, probe.stderr.strip()))
        if target is not None:
            self.assertEqual(len(row), target,
                             "the construction did not hit the target row length")
        (self.pending_dir / "widget.json").write_text(saved, encoding="utf-8")
        second = self.cli("apply", "--name", "widget", "--outcome", "used",
                          "--evidence", evidence, now=T0 + 560,
                          CLAUDE_CODE_SESSION_ID=self.SESSION)
        said = second.stdout + second.stderr
        self.assertEqual(second.returncode, 0, said)
        self.assertIn("already been recorded", second.stdout,
                      "the loser could not see a row that IS on the ledger, so it "
                      "reported the act as unrecorded: %r" % said)
        self.assertEqual(len(self.rows("apply")), 2,
                         "a row was appended twice: %r"
                         % [len(r["evidence"]) for r in self.rows("apply")])
        self.assertEqual(self.markers(), {},
                         "a discharged debt was left in the queue: %r" % said)

    def test_a_row_at_the_measured_ceiling_is_found(self):
        c = self.ceiling()
        if c is None:
            self.skipTest("no fixed-pattern ceiling on this platform's /usr/bin/grep")
        self.deliver_again_and_assert_healed(target=c)

    def test_a_row_one_character_past_the_measured_ceiling_is_found(self):
        """The row length at which the old check returned exit 2, and the loser read that
        as "the winner's row is not there"."""
        c = self.ceiling()
        if c is None:
            self.skipTest("no fixed-pattern ceiling on this platform's /usr/bin/grep")
        self.deliver_again_and_assert_healed(target=c + 1)

    def test_the_longest_row_this_cli_can_produce_is_found(self):
        """Evidence at the cap the CLI states, which is as long as a row from it ever
        gets; the printout says where that lands relative to the measured ceiling."""
        self.deliver_again_and_assert_healed(evidence_len=EVIDENCE_MAX)


# ------------------------------------- nothing in `apply` may be steered from outside

class ApplyReadsNoInternalStateFromTheEnvironment(ApplyCase):
    """`A_NO_MARKER` was read as `${A_NO_MARKER:-0}` and assigned on exactly one branch,
    so it was the only variable in this arm whose value could arrive from the ambient
    environment. An exported `A_NO_MARKER=1` then hijacked the refusal: a delivery WITH a
    pending marker took the no-marker path and was refused, and `A_NO_MARKER=0` disarmed
    the refusal for a delivery that had nothing to discharge."""

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget")

    def test_an_exported_flag_cannot_refuse_a_real_debt(self):
        r = self.cli("apply", "--name", "widget", "--outcome", "used",
                     "--evidence", "a quote", now=T0 + 200,
                     CLAUDE_CODE_SESSION_ID="sess-1", A_NO_MARKER=1)
        self.assertEqual(r.returncode, 0,
                         "an exported A_NO_MARKER refused a real debt: %r" % r.stderr)
        self.assertEqual(len(self.rows("apply")), 1, self.rows("apply"))
        self.assertEqual(self.markers(), {})

    def test_an_exported_flag_cannot_disarm_the_refusal(self):
        r = self.cli("apply", "--name", "never-forged", "--outcome", "used",
                     "--evidence", "a quote", now=T0 + 200,
                     CLAUDE_CODE_SESSION_ID="sess-1", A_NO_MARKER=0)
        self.assertEqual(r.returncode, 2,
                         "an exported A_NO_MARKER=0 let a report with nothing to "
                         "discharge through: %r" % (r.stdout + r.stderr))
        self.assertEqual(self.rows("apply"), [])

    def code(self):
        """bin/skillforge with its comment lines dropped. The file argues about its own
        variables in prose -- this defect's own note quotes `${A_NO_MARKER:-0}` -- and a
        scan that reads the argument as if it were code reports the thing it describes."""
        return "\n".join(l for l in (REPO / "bin" / "skillforge")
                          .read_text(encoding="utf-8").splitlines()
                          if not l.lstrip().startswith("#"))

    def test_every_environment_read_in_the_file_is_a_documented_knob(self):
        """The audit itself, kept as a test so a new `${FOO:-}` cannot quietly add a
        second one. Anything read with a default that is not in this list is either a
        knob that belongs in the header or internal state that must be initialised."""
        names = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)(?::-|:=)", self.code()))
        knobs = {
            # Read from the environment on purpose; each is named in the header.
            "HOME", "RANDOM", "SKILL_COMPOUNDER_STATE", "SKILLFORGE_NOW",
            "SKILLFORGE_SKILLS_DIR", "CLAUDE_CONFIG_DIR", "SKILLFORGE_NO_INSTALL",
            "SKILLFORGE_NAME", "SKILLFORGE_SKILL_DIR", "SKILLFORGE_REQUIRE_TRIGGER",
            "CLAUDE_CODE_SESSION_ID",
            # Shared with statusline/skillforge-status.sh on purpose: `list` marks a forge
            # stale at the same threshold the renderer calls idle, and two thresholds that
            # can drift would let one surface call a forge dead while the other calls it
            # healthy.
            "SKILLFORGE_IDLE_SECS",
            # Internal state, initialised on every path that reaches the read; the
            # default is a `set -u` belt, not a way in.
            "TRIGGER_TEXT", "TRIGGER_KIND", "SKILL_PRESENT", "RESOLVED_NAME",
            "INSTALL_STATUS", "FOUND", "CLOSED_ID",
        }
        self.assertEqual(names - knobs, set(),
                         "a new environment-defaulted variable appeared in "
                         "bin/skillforge; classify it as a knob or initialise it")

    def test_the_internal_ones_are_initialised_before_anything_reads_them(self):
        """The half that cannot be read off the grep above: each of these is assigned an
        initial value somewhere in the file, so the `:-` never supplies the answer."""
        src = self.code()
        for name in ("TRIGGER_TEXT", "TRIGGER_KIND", "SKILL_PRESENT", "RESOLVED_NAME",
                     "INSTALL_STATUS", "FOUND", "CLOSED_ID", "A_NO_MARKER"):
            self.assertTrue(re.search(r'(?m)(^|;)\s*%s=("")?(0)?[\s;]' % name, src),
                            "%s is never initialised, so its value can come from the "
                            "ambient environment" % name)


# ------------------------------- one run, one story: the two streams may not contradict

class TheLoserSaysOneThingOnBothStreams(ApplyCase):
    """The loser branch printed, on the same run, a stderr line saying the recorded row
    "does not say the recorded row discharges that forge" and a stdout line asserting
    "'widget' has already been recorded as applied for THIS FORGE". A caller reading
    either one alone is misled by the other."""

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget")

    def unparseable_marker_delivery(self):
        """A marker this build cannot read is still a real debt, so `apply` proceeds with
        no forge instance to key on -- the one path on which the loser can lose a claim
        that does not name this debt."""
        args = ("apply", "--name", "widget", "--outcome", "used",
                "--evidence", "used it, the flake stopped")
        first = self.cli(*args, now=T0 + 200, CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(first.returncode, 0, first.stderr)
        (self.pending_dir / "widget.json").write_text("{ this is not json",
                                                      encoding="utf-8")
        return self.cli(*args, now=T0 + 260, CLAUDE_CODE_SESSION_ID="sess-1")

    def test_the_two_streams_do_not_contradict_each_other(self):
        r = self.unparseable_marker_delivery()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LEFT WHERE IT IS", r.stderr, r.stderr)
        self.assertNotIn("for this forge", r.stdout,
                         "stdout claimed the row discharges the forge that stderr had "
                         "just said it does not: stdout %r stderr %r"
                         % (r.stdout, r.stderr))

    def test_the_debt_it_says_it_kept_is_really_kept(self):
        r = self.unparseable_marker_delivery()
        self.assertEqual(list(self.markers_raw()), ["widget.json"],
                         "the marker stderr said was left where it is, is gone: %r"
                         % (r.stdout + r.stderr))
        self.assertEqual(len(self.rows("apply")), 1, self.rows("apply"))

    def test_the_forge_keyed_loser_still_says_it_discharged_the_forge(self):
        """The other half: when the claim it lost DOES name this debt, the two streams
        agree in the other direction and the marker really goes."""
        marker = self.pending_dir / "widget.json"
        saved = marker.read_text(encoding="utf-8")
        args = ("apply", "--name", "widget", "--outcome", "used", "--evidence", "a quote")
        self.assertEqual(self.cli(*args, now=T0 + 200,
                                  CLAUDE_CODE_SESSION_ID="sess-1").returncode, 0)
        marker.write_text(saved, encoding="utf-8")
        second = self.cli(*args, now=T0 + 260, CLAUDE_CODE_SESSION_ID="sess-1")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotIn("LEFT WHERE IT IS", second.stderr, second.stderr)
        self.assertIn("for this forge", second.stdout, second.stdout)
        self.assertEqual(self.markers(), {})

    def markers_raw(self):
        """`markers()` parses, and the marker under test here deliberately does not."""
        return {p.name: p.read_text(encoding="utf-8")
                for p in sorted(self.pending_dir.glob("*.json"))}


# -------------------------- a second, distinct act is not the same thing as a re-delivery

class ASecondActIsNotARedelivery(ApplyCase):
    """THE MOVED REFUSAL MADE THEM LOOK IDENTICAL TO A CALLER. Falling through to the
    session tombstone is right for the SECOND DELIVERY OF ONE ACT -- the same command,
    twice -- and wrong for a genuinely second, distinct act on the same skill in the same
    session: that one has evidence of its own, no marker to key on, and was answered with
    "has already been recorded", exit 0, and no row -- a completion claim about something
    that was never written down.

    IT IS NOT ANSWERED BY REFUSING, and the reason is the racer. A delivery that finds no
    marker is far more often one of several concurrent deliveries that read the directory
    after the winner discharged the debt -- and two agents wording one act do not type the
    same quote, so a racer looks exactly like a second act from here. `apply` therefore
    still exits 0 and still writes nothing (ten of them may not write ten rows), and the
    fix is in what it SAYS: this act was not recorded, it is not the act that was, and
    here is the flag that records it. The two race tests above pin the exit code; this
    class pins the wording, which is the part a caller acts on."""

    SESSION = "sess-1"
    ACT_ONE = "act one: used it on the flaky test, the flake stopped"
    ACT_TWO = "act two: used it again on the retry storm, that stopped too"

    def setUp(self):
        super().setUp()
        self.author("widget")
        self.forge_and_close("widget")
        first = self.cli("apply", "--name", "widget", "--outcome", "used",
                         "--evidence", self.ACT_ONE, now=T0 + 200,
                         CLAUDE_CODE_SESSION_ID=self.SESSION)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.markers(), {})

    def second_act(self, *extra, **kw):
        return self.cli("apply", "--name", "widget", "--outcome", "used",
                        "--evidence", self.ACT_TWO, *extra,
                        now=kw.pop("now", T0 + 400),
                        CLAUDE_CODE_SESSION_ID=self.SESSION, **kw)

    def redelivery(self, *extra, **kw):
        return self.cli("apply", "--name", "widget", "--outcome", "used",
                        "--evidence", self.ACT_ONE, *extra,
                        now=kw.pop("now", T0 + 400),
                        CLAUDE_CODE_SESSION_ID=self.SESSION, **kw)

    def test_a_distinct_second_act_is_named_and_not_swallowed(self):
        r = self.second_act()
        said = r.stdout + r.stderr
        self.assertEqual([x["evidence"] for x in self.rows("apply")], [self.ACT_ONE],
                         "the bare call appended a row after all: %r" % said)
        self.assertNotIn("already been recorded", said,
                         "it reported this act as recorded with no row for it anywhere: "
                         "%r" % said)
        self.assertIn("NOTHING WAS RECORDED", said,
                      "the caller was not told its act went nowhere: %r" % said)
        self.assertIn("--force", said,
                      "the caller was not told what records it: %r" % said)

    def test_it_exits_zero_because_a_racer_cannot_be_told_from_a_second_act(self):
        """The deterministic form of what the ten-racer test above catches only sometimes:
        a delivery that finds no marker, carrying its own wording of the evidence, is the
        state every late racer is in. A non-zero exit here is a hook failing on every
        event."""
        self.assertEqual(self.second_act().returncode, 0)

    def test_the_two_cases_do_not_look_the_same_to_a_caller(self):
        act = self.second_act()
        again = self.redelivery()
        self.assertNotEqual((act.returncode, act.stdout, act.stderr),
                            (again.returncode, again.stdout, again.stderr),
                            "a second act and a re-delivery produced the identical "
                            "answer, so a caller cannot tell them apart")

    def test_a_re_delivery_is_still_absorbed_quietly(self):
        """The half that must not regress: the same command twice still costs one row and
        still exits 0."""
        r = self.redelivery()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already been recorded", r.stdout, r.stdout + r.stderr)
        self.assertEqual([x["evidence"] for x in self.rows("apply")], [self.ACT_ONE])

    def test_force_records_the_second_act(self):
        """Whatever the bare call does, the flag the message names has to work: `--force`
        on a genuinely second act must put it on the ledger."""
        r = self.second_act("--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([x["evidence"] for x in self.rows("apply")],
                         [self.ACT_ONE, self.ACT_TWO],
                         "--force could not record the second act")

    def test_a_forced_re_delivery_of_the_second_act_still_writes_one_row(self):
        self.second_act("--force")
        self.second_act("--force", now=T0 + 500)
        self.assertEqual([x["evidence"] for x in self.rows("apply")],
                         [self.ACT_ONE, self.ACT_TWO],
                         "the forced act was recorded twice: %r" % self.rows("apply"))

    def test_a_different_outcome_on_the_same_evidence_is_also_a_second_act(self):
        r = self.cli("apply", "--name", "widget", "--outcome", "failed", "--force",
                     "--evidence", self.ACT_ONE, now=T0 + 400,
                     CLAUDE_CODE_SESSION_ID=self.SESSION)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([x["outcome"] for x in self.rows("apply")], ["used", "failed"],
                         "a different outcome was folded into the first act")


if __name__ == "__main__":
    unittest.main(verbosity=2)
