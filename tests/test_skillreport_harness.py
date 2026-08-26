#!/usr/bin/env python3
"""This package's own probes and tests are not usage of its skills.

`scripts/probe_routing_claims.py` spawns one real `claude -p` session per routing
prompt, and the end-to-end and hot-reload probes do the same. Every one of those
sessions really invokes a real skill and really writes a real transcript, so
`skillreport` counted them as reuse. Derived on the machine this was written on: 98
recorded invocations of the nine skills this package ships, 93 of them from probe and
test working directories, 5 from real project directories -- and the headline read
"5 of 5 finished forges (100%)".

The discrimination rule is WHO DROVE THE SESSION. Claude Code stamps every transcript
record with `.entrypoint`: "cli" for a person at a terminal, "claude-vscode" for the
editor, "sdk-cli" for a session a program started, which is what `claude -p` is. A
skill invoked inside a session a script started was chosen by nobody. Where the session
ran is kept only as a label, never as a filter, so a real user working in /tmp is
counted and merely flagged.

Runs the real skillreport and skillforge scripts as subprocesses against a real state
directory and real transcript files written to disk, in the shapes verified against
actual Claude Code transcripts. No mocks.

Set SKILLREPORT_BIN to run these against a different copy of the script -- that is how
non-vacuity is shown, by pointing it at `git show HEAD:bin/skillreport`.
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

# Epoch seconds pinning every clock here. 1786000000 is 2026-08-06 UTC.
T0 = 1786000000

# A real project directory and a real macOS per-user temp root, both as they appear in
# transcripts (the kernel resolves /var/folders through /private on macOS, which is why
# the recorded path carries the /private prefix).
PROJ = "/Users/me/proj"
OTHER_PROJ = "/Users/me/other"
PROBE_DIR = ("/private/var/folders/tp/qtzc39jx5w556wl5w3dj21wr0000gn"
             "/T/routing-probe-zpxjtp29")


def iso(epoch):
    dt = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def use_record(skill, epoch, cwd, tool_id, entrypoint="cli", sidechain=False):
    """An assistant record holding one Skill tool_use, in the verified real shape.

    entrypoint=None omits the field entirely, which is what an older Claude Code wrote.
    """
    rec = {
        "parentUuid": "00000000-0000-0000-0000-000000000000",
        "isSidechain": sidechain,
        "type": "assistant",
        "uuid": "11111111-1111-1111-1111-111111111111",
        "timestamp": iso(epoch),
        "userType": "external",
        "sessionId": "sess",
        "cwd": cwd,
        "version": "2.1.245",
        "gitBranch": "main",
        "message": {
            "id": "msg_x", "type": "message", "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_id,
                         "name": "Skill", "input": {"skill": skill}}],
        },
    }
    if entrypoint is not None:
        rec["entrypoint"] = entrypoint
    return rec


def result_record(tool_id, epoch, is_error=None, content="Launching skill: widget"):
    """The tool_result for tool_id. A success has NO is_error key; a failure has true."""
    block = {"type": "tool_result", "content": content, "tool_use_id": tool_id}
    if is_error is not None:
        block["is_error"] = is_error
    return {
        "parentUuid": "22222222-2222-2222-2222-222222222222",
        "isSidechain": False,
        "type": "user",
        "uuid": "33333333-3333-3333-3333-333333333333",
        "timestamp": iso(epoch),
        "cwd": PROJ,
        "sessionId": "sess",
        "message": {"role": "user", "content": [block]},
    }


class Base(unittest.TestCase):

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
        # TMPDIR is deliberately absent: the script folds $TMPDIR into its temp roots,
        # and leaving it unset keeps the root set fixed so these assertions do not
        # depend on where the test runner happened to be given scratch space.
        e = {"PATH": PATH, "HOME": str(self.root),
             "SKILL_COMPOUNDER_STATE": str(self.state),
             "SKILL_COMPOUNDER_TRANSCRIPTS": str(self.transcripts)}
        if now is not None:
            e["SKILLFORGE_NOW"] = str(now)
        return e

    def forge(self, *args, now=None):
        return subprocess.run([str(FORGE), *args], capture_output=True, text=True,
                              cwd=str(self.root), env=self.env(now),
                              stdin=subprocess.DEVNULL)

    def report(self):
        r = subprocess.run([str(REPORT)], capture_output=True, text=True,
                           cwd=str(self.root), env=self.env(),
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def write_records(self, project, session, records):
        d = self.transcripts / project
        d.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(r, separators=(",", ":")) for r in records]
        (d / f"{session}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def finished_forge(self, name="widget"):
        self.forge("start", name, "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)

    def widget_row(self, out):
        rows = [l for l in out.splitlines() if l.startswith("widget")]
        self.assertTrue(rows, "no widget row in:\n" + out)
        return rows[0]

    def uses_projects(self, out):
        return self.widget_row(out).split()[-2:]


class HarnessIsNotUsageTest(Base):

    def test_a_genuine_project_use_counts(self):
        """A person at a terminal in a real repo: entrypoint "cli"."""
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, PROJ, "toolu_a", entrypoint="cli"),
            result_record("toolu_a", T0 + 5001),
        ])
        out = self.report()
        self.assertIn("1 of 1 finished forges (100%)", out)
        self.assertEqual(self.uses_projects(out), ["1", "1"], out)
        self.assertNotIn("EXCLUDED AS PROBE/TEST HARNESS", out,
                         "a genuine use was reported as harness:\n" + out)

    def test_a_probe_use_does_not_reach_the_headline(self):
        """One `claude -p` probe in a scratch dir: entrypoint "sdk-cli"."""
        self.finished_forge()
        self.write_records("-probe", "s", [
            use_record("widget", T0 + 5000, PROBE_DIR, "toolu_p",
                       entrypoint="sdk-cli"),
            result_record("toolu_p", T0 + 5001),
        ])
        out = self.report()
        self.assertIn("0 of 1 finished forges (0%)", out,
                      "a probe invocation was counted as reuse:\n" + out)
        self.assertEqual(self.uses_projects(out), ["0", "0"], out)

    def test_a_probe_use_is_reported_in_the_excluded_bucket(self):
        """Excluded is not the same as vanished: the number has to be on the page."""
        self.finished_forge()
        self.write_records("-probe", "s", [
            use_record("widget", T0 + 5000, PROBE_DIR, "toolu_p",
                       entrypoint="sdk-cli"),
            result_record("toolu_p", T0 + 5001),
        ])
        out = self.report()
        self.assertIn("EXCLUDED AS PROBE/TEST HARNESS", out,
                      "the excluded invocation was dropped in silence:\n" + out)
        self.assertIn("1 invocation(s) of these skills came from non-interactive", out)
        self.assertIn("1 of them landed after the forge", out)
        self.assertIn("1 in a system temp directory, 0 in a project directory", out)
        # Indented, so the table row (which starts at column 0) cannot be mistaken
        # for the breakdown line.
        breakdown = [l for l in out.splitlines() if l.startswith("    widget ")]
        self.assertTrue(breakdown, "no per-skill breakdown of the excluded bucket:\n" + out)
        self.assertEqual(breakdown[0].split()[-1], "1", breakdown[0])

    def test_mixed_input_splits(self):
        """Two genuine uses in two repos, three probe runs: 2/2 counted, 3 excluded."""
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, PROJ, "toolu_a", entrypoint="cli"),
            result_record("toolu_a", T0 + 5001),
            use_record("widget", T0 + 5100, OTHER_PROJ, "toolu_b",
                       entrypoint="claude-vscode"),
            result_record("toolu_b", T0 + 5101),
        ])
        self.write_records("-probe", "s", [
            r for i in range(3) for r in (
                use_record("widget", T0 + 6000 + i, PROBE_DIR, f"toolu_p{i}",
                           entrypoint="sdk-cli"),
                result_record(f"toolu_p{i}", T0 + 6001 + i))
        ])
        out = self.report()
        self.assertIn("1 of 1 finished forges (100%)", out)
        self.assertEqual(self.uses_projects(out), ["2", "2"],
                         "the counted half is wrong:\n" + out)
        self.assertIn("3 invocation(s) of these skills came from non-interactive", out)
        self.assertIn("3 in a system temp directory, 0 in a project directory", out)

    def test_the_editor_entrypoint_is_a_person(self):
        """"claude-vscode" is a human in an editor, not a script."""
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, PROJ, "toolu_v",
                       entrypoint="claude-vscode"),
            result_record("toolu_v", T0 + 5001),
        ])
        out = self.report()
        self.assertIn("1 of 1 finished forges (100%)", out)

    def test_a_subagent_of_a_real_session_counts(self):
        """Verified on real transcripts: a sidechain under an interactive session
        records `"entrypoint":"cli","isSidechain":true`. Delegated work is still the
        user's work, so a rule keyed on .isSidechain would have erased it."""
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, PROJ, "toolu_s",
                       entrypoint="cli", sidechain=True),
            result_record("toolu_s", T0 + 5001),
        ])
        out = self.report()
        self.assertIn("1 of 1 finished forges (100%)", out,
                      "a subagent invocation was thrown away:\n" + out)

    def test_a_record_with_no_entrypoint_counts(self):
        """An older Claude Code wrote no .entrypoint. Absence of the field is a version
        fact, not a probe signature, so it must not silently erase a use."""
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, PROJ, "toolu_o", entrypoint=None),
            result_record("toolu_o", T0 + 5001),
        ])
        out = self.report()
        self.assertIn("1 of 1 finished forges (100%)", out)


class LocationIsALabelNotAFilterTest(Base):

    def test_a_real_user_working_in_tmp_is_still_counted(self):
        self.finished_forge()
        self.write_records("-t", "s", [
            use_record("widget", T0 + 5000, "/private/tmp/scratch-work", "toolu_t",
                       entrypoint="cli"),
            result_record("toolu_t", T0 + 5001),
        ])
        out = self.report()
        self.assertIn("1 of 1 finished forges (100%)", out,
                      "an interactive session in /tmp was erased:\n" + out)
        self.assertEqual(self.uses_projects(out), ["1", "1"], out)
        self.assertIn("ran in a system temp directory from an interactive", out,
                      "the location was not flagged at all:\n" + out)

    def test_a_project_named_like_a_temp_root_is_not_a_temp_root(self):
        """Prefixes match whole path segments: /Users/me/tmpfoo is somebody's repo."""
        self.finished_forge()
        self.write_records("-x", "s", [
            use_record("widget", T0 + 5000, "/tmpfoo/repo", "toolu_x",
                       entrypoint="cli"),
            result_record("toolu_x", T0 + 5001),
        ])
        out = self.report()
        self.assertIn("1 of 1 finished forges (100%)", out)
        self.assertNotIn("ran in a system temp directory", out, out)

    def test_automation_in_a_real_project_is_excluded_but_named(self):
        """`claude -p` in a real repo may be the user's own automation rather than this
        package's harness. It leaves the headline, and it says so on its own line."""
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, PROJ, "toolu_auto", entrypoint="sdk-cli"),
            result_record("toolu_auto", T0 + 5001),
        ])
        out = self.report()
        self.assertIn("0 of 1 finished forges (0%)", out)
        self.assertIn("0 in a system temp directory, 1 in a project directory", out)
        self.assertIn("may be your own automation", out,
                      "nothing told the user their automation was excluded:\n" + out)


class ErrorExclusionStillHoldsTest(Base):
    """The is_error fix (issue #9) must survive the harness classification."""

    def test_a_failed_genuine_invocation_still_does_not_count(self):
        self.finished_forge()
        self.write_records("-p", "s", [
            use_record("widget", T0 + 5000, PROJ, "toolu_bad", entrypoint="cli"),
            result_record("toolu_bad", T0 + 5001, is_error=True,
                          content="<tool_use_error>Unknown skill: widget"
                                  "</tool_use_error>"),
        ])
        out = self.report()
        self.assertIn("0 of 1 finished forges (0%)", out)
        self.assertEqual(self.uses_projects(out), ["0", "0"], out)
        self.assertNotIn("EXCLUDED AS PROBE/TEST HARNESS", out,
                         "a failed invocation was re-counted as harness:\n" + out)

    def test_a_failed_probe_invocation_is_dropped_not_double_counted(self):
        """A failure is already not an invocation; it must not reappear in the excluded
        bucket, or the two exclusions would each claim the same record."""
        self.finished_forge()
        self.write_records("-probe", "s", [
            use_record("widget", T0 + 5000, PROBE_DIR, "toolu_pb",
                       entrypoint="sdk-cli"),
            result_record("toolu_pb", T0 + 5001, is_error=True,
                          content="<tool_use_error>Unknown skill: widget"
                                  "</tool_use_error>"),
        ])
        out = self.report()
        self.assertIn("0 of 1 finished forges (0%)", out)
        self.assertNotIn("EXCLUDED AS PROBE/TEST HARNESS", out, out)

    def test_a_failed_probe_and_a_good_probe_leave_one_in_the_bucket(self):
        self.finished_forge()
        self.write_records("-probe", "s", [
            use_record("widget", T0 + 5000, PROBE_DIR, "toolu_pb",
                       entrypoint="sdk-cli"),
            result_record("toolu_pb", T0 + 5001, is_error=True,
                          content="<tool_use_error>Unknown skill: widget"
                                  "</tool_use_error>"),
            use_record("widget", T0 + 5100, PROBE_DIR, "toolu_pg",
                       entrypoint="sdk-cli"),
            result_record("toolu_pg", T0 + 5101),
        ])
        out = self.report()
        self.assertIn("1 invocation(s) of these skills came from non-interactive", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
