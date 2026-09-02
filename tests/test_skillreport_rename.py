#!/usr/bin/env python3
"""A skill renamed between forging and installing must not hide its own reuse.

`skillreport` joins invocations to forges BY NAME. A session invokes a skill by the
directory it sits in, so the invocations are recorded under the INSTALLED name, while the
forge row carries the FORGE name. When those differ, every use fell outside the join and
the table printed `0 uses since` -- not as an error, as a plausible number.

Measured on the real ledger before this was fixed: forge `dead-guard-check` produced the
skill `dead-guard-detection`, and `skillreport` reported 0 uses against 28 recorded
invocations of that skill. The 0 was accidentally correct there, because all 28 were
probe-harness traffic, which is worse rather than better: the figure looked right, and it
would have read 0 just the same after fifty real uses.

The mapping was already on disk and unused. `skillforge done` writes an `origin` row
naming the directory it linked, stamped with `created_at` equal to the start time of the
forge that produced it. That stamp is the join key.

Real scripts, real state directory, real transcript files. No mocks.

Set SKILLREPORT_BIN to point at another copy of the script; that is how non-vacuity is
shown here, against `git show HEAD:bin/skillreport`.
"""

import datetime
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FORGE = REPO / "bin" / "skillforge"
REPORT = Path(os.environ.get("SKILLREPORT_BIN") or (REPO / "bin" / "skillreport"))
PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

T0 = 1786000000                      # 2026-08-06 UTC
PROJ = "/Users/me/proj"

FORGE_NAME = "widget-check"          # what the forge was called
INSTALLED_NAME = "widget-detection"  # what the directory ended up being called


def iso(epoch):
    dt = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def use_record(skill, epoch, cwd, tool_id):
    """One assistant record holding a Skill tool_use, in the verified real shape.
    `entrypoint` is "cli": a person at a terminal, not a script."""
    return {
        "parentUuid": "00000000-0000-0000-0000-000000000000",
        "isSidechain": False, "type": "assistant",
        "uuid": "11111111-1111-1111-1111-111111111111",
        "timestamp": iso(epoch), "userType": "external", "sessionId": "sess",
        "cwd": cwd, "version": "2.1.245", "gitBranch": "main", "entrypoint": "cli",
        "message": {"id": "msg_x", "type": "message", "role": "assistant",
                    "content": [{"type": "tool_use", "id": tool_id, "name": "Skill",
                                 "input": {"skill": skill}}]},
    }


class RenamedSkillCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.transcripts = self.root / "projects"
        self.state.mkdir()
        self.transcripts.mkdir()
        # A real skill directory whose name differs from the forge name. This is what
        # makes `done` record the rename.
        self.skill_dir = self.root / "built" / INSTALLED_NAME
        self.skill_dir.mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text(
            '---\nname: %s\ndescription: "Use when a widget needs checking. '
            'Do NOT use for anything else."\n---\n\n# Widget\n' % INSTALLED_NAME,
            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def env(self):
        return {"PATH": PATH, "HOME": str(self.root),
                "SKILL_COMPOUNDER_STATE": str(self.state),
                "SKILL_COMPOUNDER_TRANSCRIPTS": str(self.transcripts),
                "SKILLFORGE_NO_INSTALL": "1"}

    def forge(self, *args, now=None):
        e = self.env()
        if now is not None:
            e["SKILLFORGE_NOW"] = str(now)
        return subprocess.run([str(FORGE), *args], capture_output=True, text=True,
                              cwd=str(self.root), env=e, stdin=subprocess.DEVNULL)

    def report(self):
        r = subprocess.run([str(REPORT)], capture_output=True, text=True,
                           cwd=str(self.root), env=self.env(),
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def forge_row(self, out):
        rows = [l for l in out.splitlines() if l.startswith(FORGE_NAME)]
        self.assertTrue(rows, "no %s row in:\n%s" % (FORGE_NAME, out))
        return rows[0]

    def uses_reported(self, out):
        """The USES SINCE column of the forge row."""
        return int(self.forge_row(out).split()[-2])

    def build(self, uses=2, under=INSTALLED_NAME):
        """A forge that produced a differently-named skill, then `uses` invocations of
        `under` by a person, all after the forge closed."""
        self.forge("start", FORGE_NAME, "8", "a widget checker",
                   "--trigger", "t", "--trigger-kind", "agent-decision", now=T0)
        r = self.forge("done", "--skill-dir", str(self.skill_dir), "clean", now=T0 + 600)
        self.assertEqual(r.returncode, 0, r.stderr)
        records = []
        for i in range(uses):
            records.append(use_record(under, T0 + 5000 + i * 60, PROJ, "toolu_%d" % i))
        d = self.transcripts / "-Users-me-proj"
        d.mkdir(parents=True, exist_ok=True)
        (d / "sess.jsonl").write_text(
            "\n".join(json.dumps(r, separators=(",", ":")) for r in records) + "\n",
            encoding="utf-8")


class TheRenameIsRecorded(RenamedSkillCase):

    def test_done_writes_an_origin_row_naming_the_directory(self):
        """The mapping this whole fix depends on. If `done` stops recording the installed
        name, or stops stamping it with the start time of its forge, the join below has
        nothing to join on and would silently go back to reporting 0."""
        self.build()
        rows = [json.loads(l) for l in
                (self.state / "ledger.jsonl").read_text().splitlines() if l.strip()]
        origins = [r for r in rows if r.get("event") == "origin"
                   and r.get("origin") == "forged"]
        self.assertTrue(origins, "no forged origin row was written by `done`")
        o = origins[0]
        self.assertEqual(o["name"], INSTALLED_NAME,
                         "the origin row names the forge, not the directory installed")
        starts = [r for r in rows if r.get("event") == "start"]
        self.assertEqual(o.get("created_at"), starts[0]["ts"],
                         "the origin row is not stamped with the start time of its "
                         "forge, so there is no key to join it on")


class TheUsesAreAttributed(RenamedSkillCase):

    def test_uses_of_the_installed_name_count_for_the_forge(self):
        self.build(uses=2)
        self.assertEqual(self.uses_reported(self.report()), 2,
                         "invocations recorded under the installed name did not reach "
                         "the forge that produced it:\n" + self.report())

    def test_the_reuse_headline_counts_it_too(self):
        """Not just the row. The fraction above the table is what a reader takes away,
        and a forge whose only uses were hidden was counted as never reused."""
        self.build(uses=1)
        self.assertRegex(self.report(), r"REUSE: 1 of 1 finished forges \(100%\)")

    def test_a_forge_whose_name_did_not_change_is_unaffected(self):
        """Non-vacuity in the other direction: the fix must not start counting uses of
        some unrelated skill that happens to share a window."""
        self.build(uses=3, under=FORGE_NAME)
        self.assertEqual(self.uses_reported(self.report()), 3)

    def test_uses_of_an_unrelated_skill_are_not_swept_in(self):
        self.build(uses=2, under="something-else-entirely")
        self.assertEqual(self.uses_reported(self.report()), 0,
                         "the join matched a skill this forge never produced")


class ForgedMoreThanOnce(RenamedSkillCase):
    """The same join, read the other way round: one NAME with several forge rows.

    `skillreport` matches invocations by name, and a name cannot say which of its forges
    it belongs to, so every forge row of a name was credited with ALL of that name's uses.
    Measured on the real ledger before this was fixed: `ai-tell-audit` had three forge rows
    each reporting the same 4 uses, `finish-task` the same, the harness breakdown printed
    `finish-task 72` three times, and the headline read "7 of 10 finished forges" over 5
    distinct skills -- a number inflated on both sides of the fraction at once.

    The unit is the skill, so a name gets one row: its latest SUCCESSFUL forge. Real
    scripts, real ledger written by the real CLI, real transcript files. No mocks.
    """

    NAME = "twice-forged"

    def forge_once(self, start, end, outcome="done"):
        r = self.forge("start", self.NAME, "8", "a thing",
                       "--trigger", "t", "--trigger-kind", "agent-decision", now=start)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.forge(outcome, "ok" if outcome == "done" else "gave up", now=end)
        self.assertEqual(r.returncode, 0, r.stderr)

    def uses(self, n, at=T0 + 5000):
        d = self.transcripts / "-Users-me-proj"
        d.mkdir(parents=True, exist_ok=True)
        (d / "sess.jsonl").write_text(
            "\n".join(json.dumps(use_record(self.NAME, at + i * 60, PROJ, "toolu_%d" % i),
                                 separators=(",", ":")) for i in range(n)) + "\n",
            encoding="utf-8")

    def rows(self, out):
        return [l for l in out.splitlines() if l.startswith(self.NAME)]

    def test_a_name_forged_twice_gets_one_row_not_two(self):
        self.forge_once(T0, T0 + 600)
        self.forge_once(T0 + 1000, T0 + 1600)
        self.uses(2)
        out = self.report()
        self.assertEqual(len(self.rows(out)), 1,
                         "one skill printed once per forge, so its uses are credited "
                         "once per forge too:\n" + out)

    def test_the_denominator_counts_skills_not_forge_rows(self):
        self.forge_once(T0, T0 + 600)
        self.forge_once(T0 + 1000, T0 + 1600)
        self.uses(2)
        out = self.report()
        self.assertRegex(out, r"REUSE: 1 of 1 finished forges \(100%\)")
        self.assertIn("1 of the 2 forge", out,
                      "the folded row is not reported, so the table silently loses "
                      "a forge instead of visibly folding it:\n" + out)

    def test_the_uses_are_counted_once(self):
        self.forge_once(T0, T0 + 600)
        self.forge_once(T0 + 1000, T0 + 1600)
        self.uses(2)
        self.assertEqual(int(self.rows(self.report())[0].split()[-2]), 2,
                         "the same invocations were credited to more than one forge")

    def test_a_later_failure_does_not_open_the_window_that_counts(self):
        """The `finish-task` shape from the real ledger: forged and shipped, used, then
        re-forged twice into failures. Ranking by recency alone measured the uses against
        a window opened by a forge that produced nothing, and reported 0."""
        self.forge_once(T0, T0 + 600)                          # the forge that shipped it
        self.uses(1, at=T0 + 5000)                             # used after that forge
        self.forge_once(T0 + 9000, T0 + 9600, outcome="fail")  # a later, failed re-forge
        out = self.report()
        self.assertEqual(len(self.rows(out)), 1, out)
        row = self.rows(out)[0]
        self.assertIn("done", row,
                      "the failed re-forge stands for the skill, but it built nothing "
                      "for anyone to invoke:\n" + out)
        self.assertEqual(int(row.split()[-2]), 1,
                         "the use was measured against the wrong forge window:\n" + out)
        self.assertRegex(out, r"REUSE: 1 of 1 finished forges \(100%\)")

    def test_two_different_names_are_still_two_rows(self):
        """Non-vacuity: the fold must key on the name, not swallow the table."""
        self.forge_once(T0, T0 + 600)
        r = self.forge("start", "other-thing", "8", "a thing",
                       "--trigger", "t", "--trigger-kind", "agent-decision", now=T0 + 2000)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.forge("done", "ok", now=T0 + 2600)
        out = self.report()
        self.assertEqual(len(self.rows(out)), 1, out)
        self.assertTrue([l for l in out.splitlines() if l.startswith("other-thing")], out)
        self.assertRegex(out, r"REUSE: 0 of 2 finished forges \(0%\)")
        self.assertNotIn("forge row(s) in the ledger share a name", out,
                         "nothing was folded, so nothing should say it was:\n" + out)


class ItActuallyNeededFixing(RenamedSkillCase):
    """Proof the tests above are not vacuous, run against whatever SKILLREPORT_BIN names.
    Skipped when it points at the working copy, since then there is nothing to contrast."""

    def test_the_previous_skillreport_reported_zero(self):
        if os.environ.get("SKILLREPORT_BIN") is None:
            self.skipTest("set SKILLREPORT_BIN to an older bin/skillreport to contrast")
        self.build(uses=2)
        self.assertEqual(self.uses_reported(self.report()), 0,
                         "the copy under SKILLREPORT_BIN already attributes the uses, so "
                         "it is not the pre-fix version and proves nothing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
