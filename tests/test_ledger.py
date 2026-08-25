#!/usr/bin/env python3
"""Forge ledger and usage rollup.

Runs the real skillforge and skillreport scripts as subprocesses against a real state
directory and real transcript files written to disk. No mocks: every assertion is made
against bytes that the scripts actually wrote or read.
"""

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
    import datetime
    dt = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


class LedgerTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.transcripts = self.root / "projects"
        self.state.mkdir()
        self.transcripts.mkdir()
        self.ledger = self.state / "ledger.jsonl"

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

    def report(self, *args, edit_every=None):
        e = self.env()
        if edit_every is not None:
            e["CI_EDIT_EVERY"] = str(edit_every)
        return subprocess.run([str(REPORT), *args], capture_output=True, text=True,
                              cwd=str(self.root), env=e)

    def records(self):
        if not self.ledger.exists():
            return []
        return [json.loads(l) for l in self.ledger.read_text(encoding="utf-8").splitlines() if l.strip()]

    def write_transcript(self, project, session, invocations):
        """Write a real .jsonl transcript. invocations: list of (skill, epoch, cwd)."""
        d = self.transcripts / project
        d.mkdir(parents=True, exist_ok=True)
        lines = []
        for skill, epoch, cwd in invocations:
            lines.append(json.dumps({
                "parentUuid": "00000000-0000-0000-0000-000000000000",
                "isSidechain": False,
                "type": "assistant",
                "uuid": "11111111-1111-1111-1111-111111111111",
                "timestamp": iso(epoch),
                "sessionId": session,
                "cwd": cwd,
                "version": "2.1.243",
                "gitBranch": "main",
                "message": {
                    "id": "msg_x", "type": "message", "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_x",
                                 "name": "Skill", "input": {"skill": skill}}],
                },
            }, separators=(",", ":")))
        (d / f"{session}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


class LedgerWriteTest(LedgerTestBase):

    def test_start_appends_a_start_record(self):
        r = self.forge("start", "my-skill", "8", "does", "a", "thing", now=T0)
        self.assertEqual(r.returncode, 0, r.stderr)
        recs = self.records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["event"], "start")
        self.assertEqual(recs[0]["name"], "my-skill")
        self.assertEqual(recs[0]["ts"], T0)
        self.assertEqual(recs[0]["steps"], 8)
        self.assertEqual(recs[0]["summary"], "does a thing")
        self.assertIn("project", recs[0])
        self.assertTrue(recs[0]["project"])

    def test_done_appends_outcome_with_duration_and_rounds(self):
        self.forge("start", "s", "8", "summary", now=T0)
        self.forge("step", "5", "red-team round 2", now=T0 + 100)
        r = self.forge("done", "clean red-team pass", now=T0 + 600)
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.records()[-1]
        self.assertEqual(rec["event"], "done")
        self.assertEqual(rec["ts"], T0 + 600)
        self.assertEqual(rec["duration"], 600)
        self.assertEqual(rec["step"], 8)
        self.assertEqual(rec["phase"], "clean red-team pass")
        # `done` snaps the step to the budget, so a completed forge reports the full
        # three rounds and the plan agrees with what happened.
        self.assertEqual(rec["rounds"], 3, "completed rounds, derived from the step reached")
        self.assertEqual(rec["rounds_planned"], 3, "8 steps budgeted as 2 + 2*rounds")

    def test_fail_is_recorded_so_abandoned_forges_are_not_lost(self):
        self.forge("start", "s", "6", "summary", now=T0)
        self.forge("step", "3", "red-team round 1", now=T0 + 50)
        self.forge("fail", "3 rounds, still ambiguous", now=T0 + 400)
        rec = self.records()[-1]
        self.assertEqual(rec["event"], "fail")
        self.assertEqual(rec["phase"], "3 rounds, still ambiguous")
        self.assertEqual(rec["step"], 3, "a failed forge keeps the step it reached")
        self.assertEqual(rec["duration"], 400)
        # An outcome record reports rounds COMPLETED, not rounds budgeted. Reporting the
        # plan here was a lie the ledger told about itself: a forge abandoned in the first
        # review had finished no rounds at all, and the whole point of this file is to
        # measure what actually happened.
        self.assertEqual(rec["rounds"], 0,
                         "abandoned during round 1, so no round completed")
        self.assertEqual(rec["rounds_planned"], 2, "6 steps budgeted as 2 + 2*rounds")

    def test_an_outcome_never_reports_more_rounds_than_happened(self):
        """The specific case a cold review caught: abandoned at step 3 of 8, recorded 3."""
        self.forge("start", "s", "8", "summary", now=T0)
        self.forge("step", "3", "red-team round 1", now=T0 + 50)
        self.forge("fail", "gave up in round 1", now=T0 + 60)
        rec = self.records()[-1]
        self.assertEqual(rec["rounds"], 0)
        self.assertEqual(rec["rounds_planned"], 3)
        self.assertLessEqual(rec["rounds"], rec["rounds_planned"])

    def test_clear_of_an_active_forge_is_recorded_as_abandonment(self):
        self.forge("start", "s", "4", "summary", now=T0)
        self.forge("clear", now=T0 + 30)
        recs = self.records()
        self.assertEqual([r["event"] for r in recs], ["start", "fail"])
        self.assertIn("cleared", recs[-1]["phase"])

    def test_clear_with_no_active_forge_writes_nothing(self):
        self.forge("clear", now=T0)
        self.assertEqual(self.records(), [])

    def test_rounds_never_go_negative(self):
        self.forge("start", "tiny", "1", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 10)
        self.assertEqual(self.records()[-1]["rounds"], 0)

    def test_every_line_is_one_complete_json_object(self):
        for i in range(5):
            self.forge("start", "s%d" % i, "6", "summary", now=T0 + i)
            self.forge("done", "ok", now=T0 + i + 1)
        text = self.ledger.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        for line in text.splitlines():
            json.loads(line)  # raises if two appends interleaved
        self.assertEqual(len(text.splitlines()), 10)

    def test_ledger_survives_a_full_forge_sequence(self):
        self.forge("start", "a", "8", "first", now=T0)
        self.forge("done", "ok", now=T0 + 100)
        self.forge("start", "b", "6", "second", now=T0 + 200)
        self.forge("fail", "gave up", now=T0 + 300)
        self.assertEqual([r["event"] for r in self.records()],
                         ["start", "done", "start", "fail"])


class LedgerCommandTest(LedgerTestBase):

    def test_empty_ledger_says_so_plainly(self):
        r = self.forge("ledger")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no forges recorded yet", r.stdout)

    def test_ledger_joins_start_to_outcome(self):
        self.forge("start", "alpha", "8", "summary", now=T0)
        self.forge("done", "clean pass", now=T0 + 600)
        r = self.forge("ledger")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("alpha", r.stdout)
        self.assertIn("[done]", r.stdout)
        self.assertIn("3 round(s)", r.stdout)
        self.assertIn("600s", r.stdout)
        self.assertIn("2026-08-06", r.stdout)
        self.assertIn("1 forge(s)", r.stdout)

    def test_ledger_reports_a_start_with_no_outcome(self):
        self.forge("start", "orphan", "6", "summary", now=T0)  # no done, no fail
        r = self.forge("ledger")
        self.assertIn("orphan", r.stdout)
        self.assertIn("[no outcome]", r.stdout)
        self.assertIn("1 never closed out", r.stdout)

    def test_ledger_counts_done_and_abandoned_separately(self):
        self.forge("start", "a", "8", "s", now=T0)
        self.forge("done", "ok", now=T0 + 10)
        self.forge("start", "b", "8", "s", now=T0 + 20)
        self.forge("fail", "nope", now=T0 + 30)
        r = self.forge("ledger")
        self.assertIn("1 done", r.stdout)
        self.assertIn("1 abandoned", r.stdout)

    def test_ledger_json_prints_raw_records(self):
        self.forge("start", "a", "8", "s", now=T0)
        self.forge("done", "ok", now=T0 + 10)
        r = self.forge("ledger", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        recs = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
        self.assertEqual([x["event"] for x in recs], ["start", "done"])

    def test_missing_project_renders_as_a_dash_not_the_string_null(self):
        self.ledger.write_text(
            json.dumps({"event": "start", "name": "a", "ts": T0, "steps": 8,
                        "summary": "s"}) + "\n", encoding="utf-8")
        r = self.forge("ledger")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("a", r.stdout)
        self.assertNotIn("null", r.stdout)

    def test_empty_project_renders_as_a_dash_not_the_string_null(self):
        self.ledger.write_text(
            json.dumps({"event": "start", "name": "a", "ts": T0, "steps": 8,
                        "summary": "s", "project": ""}) + "\n", encoding="utf-8")
        r = self.forge("ledger")
        self.assertNotIn("null", r.stdout)

    def test_root_project_renders_as_a_dash_not_the_string_null(self):
        self.ledger.write_text(
            json.dumps({"event": "start", "name": "a", "ts": T0, "steps": 8,
                        "summary": "s", "project": "/"}) + "\n", encoding="utf-8")
        r = self.forge("ledger")
        self.assertNotIn("null", r.stdout)

    def test_ledger_tolerates_a_corrupt_line(self):
        self.forge("start", "a", "8", "s", now=T0)
        self.forge("done", "ok", now=T0 + 10)
        with self.ledger.open("a", encoding="utf-8") as fh:
            fh.write("{not json at all\n")
        r = self.forge("ledger")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("a", r.stdout)
        self.assertIn("1 forge(s)", r.stdout)


class ReportTest(LedgerTestBase):

    def test_empty_ledger_never_prints_a_fabricated_percentage(self):
        r = self.report()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no forges recorded yet", r.stdout)
        self.assertNotIn("0%", r.stdout)
        self.assertNotIn("0 of 0", r.stdout)

    def test_help_documents_what_is_stored_and_where(self):
        r = self.report("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PRIVACY", r.stdout)
        self.assertIn("ledger.jsonl", r.stdout)
        self.assertIn("no network calls", r.stdout)
        self.assertIn("Nothing leaves the machine", r.stdout)

    def test_neither_script_contains_a_network_call(self):
        for script in (FORGE, REPORT):
            text = script.read_text(encoding="utf-8")
            for needle in ("curl ", "wget ", "nc ", "https://", "http://"):
                self.assertNotIn(needle, text, "%s must make no network calls" % script.name)

    def test_post_forge_invocation_counts_as_reuse(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.write_transcript("-Users-me-proj", "sess-1", [
            ("widget", T0 + 5000, "/Users/me/proj"),
            ("widget", T0 + 6000, "/Users/me/proj"),
        ])
        r = self.report()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)
        row = [l for l in r.stdout.splitlines() if l.startswith("widget")][0]
        self.assertEqual(row.split()[-2:], ["2", "1"], row)

    def test_pre_forge_invocation_does_not_count_as_reuse(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.write_transcript("-Users-me-proj", "sess-1", [
            ("widget", T0 - 5000, "/Users/me/proj"),
        ])
        r = self.report()
        self.assertIn("0 of 1 finished forges (0%)", r.stdout)

    def test_during_forge_invocation_is_reported_separately_not_as_reuse(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.write_transcript("-Users-me-proj", "sess-1", [
            ("widget", T0 + 300, "/Users/me/proj"),
        ])
        r = self.report()
        self.assertIn("0 of 1 finished forges (0%)", r.stdout)
        self.assertIn("1 invocation(s) fell inside a forge window", r.stdout)

    def test_namespaced_invocation_matches_a_bare_ledger_name(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.write_transcript("-Users-me-proj", "sess-1", [
            ("my-plugin:widget", T0 + 5000, "/Users/me/proj"),
        ])
        r = self.report()
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)

    def test_namespaced_ledger_name_matches_the_same_namespaced_invocation(self):
        self.forge("start", "my-plugin:widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.write_transcript("-Users-me-proj", "sess-1", [
            ("my-plugin:widget", T0 + 5000, "/Users/me/proj"),
        ])
        r = self.report()
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)

    def test_a_different_skill_is_not_counted(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.write_transcript("-Users-me-proj", "sess-1", [
            ("widget-factory", T0 + 5000, "/Users/me/proj"),
            ("other:widget-factory", T0 + 5001, "/Users/me/proj"),
        ])
        r = self.report()
        self.assertIn("0 of 1 finished forges (0%)", r.stdout)

    def test_distinct_projects_are_counted_across_transcripts(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.write_transcript("-a", "sess-a", [("widget", T0 + 5000, "/repos/a")])
        self.write_transcript("-b", "sess-b", [("widget", T0 + 5001, "/repos/b"),
                                               ("widget", T0 + 5002, "/repos/b")])
        self.write_transcript("-c", "sess-c", [("widget", T0 + 5003, "/repos/c")])
        r = self.report()
        row = [l for l in r.stdout.splitlines() if l.startswith("widget")][0]
        self.assertEqual(row.split()[-2:], ["4", "3"], row)

    def test_abandoned_forge_appears_in_the_table(self):
        self.forge("start", "flop", "6", "summary", now=T0)
        self.forge("fail", "gave up", now=T0 + 300)
        r = self.report()
        row = [l for l in r.stdout.splitlines() if l.startswith("flop")][0]
        self.assertIn("fail", row)
        self.assertIn("0 of 1 finished forges", r.stdout)

    def test_missing_transcripts_are_reported_not_silently_zero(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        r = self.report()
        self.assertIn("no transcripts found", r.stdout)

    def test_unparseable_timestamp_is_counted_separately(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        d = self.transcripts / "-p"
        d.mkdir()
        (d / "s.jsonl").write_text(json.dumps({
            "type": "assistant", "timestamp": "not-a-date", "cwd": "/repos/a",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t", "name": "Skill", "input": {"skill": "widget"}}]},
        }, separators=(",", ":")) + "\n", encoding="utf-8")
        r = self.report()
        self.assertIn("1 invocation(s) had no parseable timestamp", r.stdout)
        self.assertIn("0 of 1 finished forges (0%)", r.stdout)

    def test_a_line_mentioning_skill_without_a_tool_use_is_ignored(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        d = self.transcripts / "-p"
        d.mkdir()
        (d / "s.jsonl").write_text(json.dumps({
            "type": "user", "timestamp": iso(T0 + 5000), "cwd": "/repos/a",
            "message": {"role": "user", "content": [
                {"type": "text", "text": '"name":"Skill","input":{"skill":"widget"} in prose'}]},
        }, separators=(",", ":")) + "\n", encoding="utf-8")
        r = self.report()
        self.assertIn("0 of 1 finished forges (0%)", r.stdout)

    # -------------------------------------------------- forges that never closed out

    def test_unclosed_forge_never_counts_a_mid_forge_invocation_as_reuse(self):
        """A start with no done and no fail has no finish, so nothing is 'after' it."""
        self.forge("start", "open", "6", "summary", now=T0)  # never closed out
        self.write_transcript("-Users-me-proj", "sess-1", [
            ("open", T0 + 300, "/Users/me/proj"),   # during the forge, still running
            ("open", T0 + 90000, "/Users/me/proj"),  # long after, but still no finish
        ])
        r = self.report()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("100%", r.stdout)
        self.assertNotIn("1 of 1", r.stdout)
        self.assertIn("REUSE: not measurable", r.stdout)
        self.assertIn("1 forge(s) never closed out and are excluded", r.stdout)
        row = [l for l in r.stdout.splitlines() if l.startswith("open")][0]
        self.assertEqual(row.split()[-2:], ["-", "-"], row)

    def test_unclosed_forge_is_excluded_from_both_halves_of_the_fraction(self):
        self.forge("start", "shipped", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.forge("start", "open", "6", "summary", now=T0 + 1000)  # never closed out
        self.write_transcript("-Users-me-proj", "sess-1", [
            ("shipped", T0 + 5000, "/Users/me/proj"),
            ("open", T0 + 5000, "/Users/me/proj"),
        ])
        r = self.report()
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)
        self.assertIn("1 forge(s) never closed out and are excluded", r.stdout)

    def test_no_exclusion_line_when_every_forge_closed_out(self):
        self.forge("start", "shipped", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        r = self.report()
        self.assertNotIn("never closed out and are excluded", r.stdout)

    def test_a_cleared_forge_is_closed_and_still_measurable(self):
        """clear records a fail, so the forge has a finish and stays in the fraction."""
        self.forge("start", "dropped", "6", "summary", now=T0)
        self.forge("clear", now=T0 + 200)
        self.write_transcript("-p", "s", [("dropped", T0 + 5000, "/repos/a")])
        r = self.report()
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)
        self.assertNotIn("never closed out and are excluded", r.stdout)

    # ------------------------------------------------- names the tsv has to survive

    def test_a_skill_name_holding_a_tab_is_still_counted(self):
        self.forge("start", "odd\tname", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.write_transcript("-p", "s", [("odd\tname", T0 + 5000, "/repos/a")])
        r = self.report()
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)

    def test_a_skill_name_holding_a_backslash_is_still_counted(self):
        self.forge("start", "odd\\name", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.write_transcript("-p", "s", [("odd\\name", T0 + 5000, "/repos/a")])
        r = self.report()
        self.assertIn("1 of 1 finished forges (100%)", r.stdout)

    def test_a_backslash_name_does_not_match_its_unescaped_twin(self):
        """odd\\tname and odd<tab>name are different skills and must not be conflated."""
        self.forge("start", "odd\\tname", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        self.write_transcript("-p", "s", [("odd\tname", T0 + 5000, "/repos/a")])
        r = self.report()
        self.assertIn("0 of 1 finished forges (0%)", r.stdout)

    def test_reminder_conversion_is_derived_and_labelled_an_estimate(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        self.forge("done", "ok", now=T0 + 600)
        rem = self.state / "reminders"
        rem.mkdir()
        (rem / "sess-a.edits").write_text("30", encoding="utf-8")   # 2 checkpoints at 12
        (rem / "sess-b.edits").write_text("11", encoding="utf-8")   # 0 checkpoints
        r = self.report()
        self.assertIn("estimate", r.stdout)
        self.assertIn("2 session(s)", r.stdout)
        self.assertIn("checkpoints they imply:     2", r.stdout)
        self.assertIn("CI_EDIT_EVERY=12", r.stdout)
        self.assertIn("forges started, all time:   1", r.stdout)

    def test_reminder_conversion_honours_ci_edit_every(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        rem = self.state / "reminders"
        rem.mkdir()
        (rem / "sess-a.edits").write_text("30", encoding="utf-8")
        r = self.report(edit_every=5)
        self.assertIn("CI_EDIT_EVERY=5", r.stdout)
        self.assertIn("checkpoints they imply:     6", r.stdout)

    def test_reminder_conversion_ignores_junk_counters(self):
        self.forge("start", "widget", "8", "summary", now=T0)
        rem = self.state / "reminders"
        rem.mkdir()
        (rem / "sess-a.edits").write_text("not-a-number", encoding="utf-8")
        r = self.report()
        self.assertIn("0 session(s)", r.stdout)
        self.assertIn("not computable", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
