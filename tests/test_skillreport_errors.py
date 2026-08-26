#!/usr/bin/env python3
"""A failed Skill invocation is not a use (issue #9).

skillreport counts reuse from transcript tool_use records. Every tool_use has an id,
and the transcript later carries a tool_result with the matching tool_use_id; when the
invocation failed (skill not installed, for instance) that result carries
"is_error":true and error text like "<tool_use_error>Unknown skill: ...</tool_use_error>".
Counting the tool_use alone counted those failures as reuse and inflated the one number
the report exists to produce.

Runs the real skillforge and skillreport scripts as subprocesses against a real state
directory and real transcript files written to disk, in the shapes verified against
actual Claude Code transcripts (a successful result has NO is_error key at all; a failed
one has "is_error":true). No mocks.
"""

import datetime
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FORGE = REPO / "bin" / "skillforge"
REPORT = REPO / "bin" / "skillreport"

PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

# Epoch seconds used to pin every clock in these tests. 1786000000 is 2026-08-06 UTC.
T0 = 1786000000


def iso(epoch):
    """Epoch seconds to the ISO-8601 shape Claude Code writes into transcripts."""
    dt = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def use_record(skill, epoch, cwd, tool_id):
    """An assistant record holding one Skill tool_use, in the verified real shape."""
    return {
        "parentUuid": "00000000-0000-0000-0000-000000000000",
        "isSidechain": False,
        "type": "assistant",
        "uuid": "11111111-1111-1111-1111-111111111111",
        "timestamp": iso(epoch),
        "sessionId": "sess",
        "cwd": cwd,
        "version": "2.1.243",
        "gitBranch": "main",
        "message": {
            "id": "msg_x", "type": "message", "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_id,
                         "name": "Skill", "input": {"skill": skill}}],
        },
    }


def result_record(tool_id, epoch, is_error=None, content="Launching skill: x"):
    """A user record holding the tool_result for tool_id.

    Verified against real transcripts: a successful result has NO is_error key; a
    failed one carries "is_error":true and its content is the error text. is_error=None
    reproduces the success shape, True/False write the key explicitly.
    """
    block = {"type": "tool_result", "content": content, "tool_use_id": tool_id}
    if is_error is not None:
        block["is_error"] = is_error
    return {
        "parentUuid": "22222222-2222-2222-2222-222222222222",
        "isSidechain": False,
        "type": "user",
        "uuid": "33333333-3333-3333-3333-333333333333",
        "timestamp": iso(epoch),
        "sessionId": "sess",
        "cwd": "/Users/me/proj",
        "message": {"role": "user", "content": [block]},
    }


class SkillInvocationErrorTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.transcripts = self.root / "projects"
        self.state.mkdir()
        self.transcripts.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, now=None):
        e = {"PATH": PATH, "HOME": str(self.root),
             "SKILL_COMPOUNDER_STATE": str(self.state),
             "SKILL_COMPOUNDER_TRANSCRIPTS": str(self.transcripts)}
        if now is not None:
            e["SKILLFORGE_NOW"] = str(now)
        return e

    def forge(self, *args, now=None):
        return subprocess.run([str(FORGE), *args], capture_output=True, text=True,
                              cwd=str(self.root), env=self.env(now))

    def report(self):
        return subprocess.run([str(REPORT)], capture_output=True, text=True,
                              cwd=str(self.root), env=self.env())

    def write_records(self, project, session, records):
        """Write a real .jsonl transcript from already-shaped record dicts."""
        d = self.transcripts / project
        d.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(r, separators=(",", ":")) for r in records]
        (d / f"{session}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def finished_forge(self, name="widget"):
        self.forge("start", name, "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)

    def widget_row(self, out):
        return [l for l in out.splitlines() if l.startswith("widget")][0]

    # ------------------------------------------------------------- the four cases

    def test_successful_invocation_counts_as_reuse(self):
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, "/Users/me/proj", "toolu_ok1"),
            result_record("toolu_ok1", T0 + 5001,
                          content="Launching skill: widget"),
        ])
        r = self.report()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)
        self.assertEqual(self.widget_row(r.stdout).split()[-2:], ["1", "1"])

    def test_failed_invocation_does_not_count_as_reuse(self):
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, "/Users/me/proj", "toolu_bad1"),
            result_record(
                "toolu_bad1", T0 + 5001, is_error=True,
                content="<tool_use_error>Unknown skill: widget</tool_use_error>"),
        ])
        r = self.report()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 of 1 finished forges (0%)", r.stdout)
        self.assertEqual(self.widget_row(r.stdout).split()[-2:], ["0", "0"])

    def test_mixed_file_counts_only_the_successes(self):
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, "/Users/me/proj", "toolu_bad1"),
            result_record(
                "toolu_bad1", T0 + 5001, is_error=True,
                content="<tool_use_error>Unknown skill: widget</tool_use_error>"),
            use_record("widget", T0 + 6000, "/Users/me/proj", "toolu_ok1"),
            result_record("toolu_ok1", T0 + 6001,
                          content="Launching skill: widget"),
            use_record("widget", T0 + 7000, "/Users/me/other", "toolu_bad2"),
            result_record(
                "toolu_bad2", T0 + 7001, is_error=True,
                content="<tool_use_error>Unknown skill: widget</tool_use_error>"),
        ])
        r = self.report()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)
        # One success in one project; the two failures add neither a use nor a project.
        self.assertEqual(self.widget_row(r.stdout).split()[-2:], ["1", "1"],
                         self.widget_row(r.stdout))

    def test_invocation_with_no_result_still_counts(self):
        """POLICY: a tool_use with no tool_result anywhere counts as a use. The usual
        reason a result is missing is a live session or a transcript cut off mid-turn,
        not a failure -- a failure writes its error result on the very next record --
        so dropping these would under-report exactly the freshest usage."""
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, "/Users/me/proj", "toolu_dangling"),
        ])
        r = self.report()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)
        self.assertEqual(self.widget_row(r.stdout).split()[-2:], ["1", "1"])

    # ---------------------------------------------------------------- edge shapes

    def test_explicit_is_error_false_counts(self):
        """Only is_error:true marks a failure; an explicit false is a success."""
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, "/Users/me/proj", "toolu_f1"),
            result_record("toolu_f1", T0 + 5001, is_error=False,
                          content="Launching skill: widget"),
        ])
        r = self.report()
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)

    def test_error_on_a_different_tool_does_not_veto_the_skill_use(self):
        """The join is by id: an is_error:true result for some OTHER tool_use in the
        same file must not knock out a Skill invocation with a different id."""
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, "/Users/me/proj", "toolu_skill1"),
            result_record("toolu_other_bash", T0 + 5001, is_error=True,
                          content="<tool_use_error>command not found</tool_use_error>"),
        ])
        r = self.report()
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)

    def test_failed_invocation_alone_never_inflates_an_otherwise_real_rate(self):
        """The measured incident from issue #9: one forged skill genuinely reused, one
        never installed but attempted. The attempt's failure must leave the headline at
        50%, not lift it to 100%."""
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.forge("start", "phantom", "8", "summary", now=T0 + 1000)
        self.forge("done", "ok", now=T0 + 1600)
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, "/Users/me/proj", "toolu_ok1"),
            result_record("toolu_ok1", T0 + 5001,
                          content="Launching skill: widget"),
            use_record("phantom", T0 + 6000, "/Users/me/proj", "toolu_bad1"),
            result_record(
                "toolu_bad1", T0 + 6001, is_error=True,
                content="<tool_use_error>Unknown skill: phantom</tool_use_error>"),
        ])
        r = self.report()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 of 2 finished forges (50%)", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
