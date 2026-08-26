#!/usr/bin/env python3
"""The arm of the capture hook that does not ask the session anything.

WHAT THIS IS FOR. The 12-edit checkpoint is injected context, and injected context can
be disregarded. It was, three times out of three, in one long session that fired the
checkpoint at edits 12, 24 and 36 while fixing nine defects of a single kind. Each
refusal was honest: the checkpoint asks about "the procedure you are working through
right now", and per instance, mid-fix, the true answer really is "no, I am just fixing
a bug". Recurrence was only visible across the nine, and nothing in the session was
looking across them.

So the session-audit arm stops asking. Once a session crosses a mechanical threshold,
hooks/insight-capture.sh writes ONE queue record itself, stating what it counted, and
the cross-instance question is put to `skillinsight review` instead -- where someone
reads the set cold. These tests hold that line: after a session that reads nothing,
invokes nothing and writes no marker, there is a record on disk.

Everything here runs the real scripts through subprocess against real state
directories, and reads results back off disk. Every hook invocation passes `input=`;
a hook reads its payload with `payload="$(cat)"` and hangs forever without it.
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EDIT_HOOK = REPO / "hooks" / "compound-improvement.sh"
STOP_HOOK = REPO / "hooks" / "insight-capture.sh"
INSIGHT = REPO / "bin" / "skillinsight"

PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
# Pinned so the ISO-week filename and every timestamp are deterministic.
T_EDIT = 1787700000
T_STOP = 1787700600
WEEK = "2026-W35"


class AuditBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------- plumbing

    def env(self, **extra):
        e = {"PATH": PATH, "HOME": str(self.state),
             "SKILL_COMPOUNDER_STATE": str(self.state)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def edit(self, path, sid="s1", uid=None, tool="Edit", **extra):
        payload = {"session_id": sid, "tool_name": tool,
                   "tool_input": {"file_path": path}}
        if uid:
            payload["tool_use_id"] = uid
        extra.setdefault("CI_NOW", T_EDIT)
        return subprocess.run([str(EDIT_HOOK), "edit"], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env(**extra))

    def bash_edit(self, command, sid="s1", uid=None, **extra):
        payload = {"session_id": sid, "tool_name": "Bash",
                   "tool_input": {"command": command}}
        if uid:
            payload["tool_use_id"] = uid
        extra.setdefault("CI_NOW", T_EDIT)
        return subprocess.run([str(EDIT_HOOK), "edit"], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env(**extra))

    def stop(self, sid="s1", cwd=None, message="Fixed it. The suite is green.", **extra):
        payload = {"session_id": sid, "cwd": cwd or str(self.state),
                   "last_assistant_message": message}
        extra.setdefault("INSIGHT_NOW", T_STOP)
        return subprocess.run([str(STOP_HOOK)], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env(**extra))

    def cli(self, *args, **extra):
        extra.setdefault("INSIGHT_NOW", T_STOP)
        return subprocess.run([str(INSIGHT)] + list(args), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, env=self.env(**extra))

    # --------------------------------------------------------------- assertions

    def records(self):
        """Every queued candidate, read the way the shell tools read them.

        Two deliberate differences from a naive read. Python's `glob` matches a
        leading dot and the shell's does not, so `.declined.jsonl` -- which sits in
        this directory precisely because `"$DIR"/*.jsonl` skips it -- has to be
        skipped here too, or the test sees a file the product never does. And a line
        that a test planted to corrupt the file is skipped rather than raising, so a
        corruption test measures the hook instead of this parser.
        """
        out = []
        d = self.state / "insights"
        if d.is_dir():
            for f in sorted(d.glob("*.jsonl")):
                if f.name.startswith("."):
                    continue
                for line in f.read_text(errors="replace").splitlines():
                    if not line.strip():
                        continue
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        return out

    def audits(self):
        return [r for r in self.records() if r["source"] == "session-audit"]

    def work(self, sid="s1", files=9, per_file=3, prefix="/repo"):
        """A session that edits `files` distinct paths `per_file` times each.

        It writes no marker, emits no insight block, and does nothing with any hook
        output -- which is the whole point: this is the session that disregards.
        """
        # The tool_use_id has to be unique across EVERY call in a test, not just
        # within one: claim_once() is doing its job when it drops a repeat, and a
        # colliding id makes a second work() batch vanish. It must also stay SHORT --
        # claim_once truncates an id at 96 characters, so building one out of the
        # session id made a 300-character-sid test collapse to a single counted edit.
        self._batch = getattr(self, "_batch", 0) + 1
        i = 0
        for n in range(files):
            for k in range(per_file):
                i += 1
                uid = "u-%d-%02d-%02d" % (self._batch, n, k)
                r = self.edit("%s/file%02d.py" % (prefix, n), sid=sid, uid=uid)
                self.assertEqual(r.returncode, 0)
        return i


class DisregardStillLeavesARecordTest(AuditBase):
    """The requirement, stated as a test: ignoring every reminder produces the record."""

    def test_a_session_that_ignores_everything_still_leaves_one_record(self):
        n = self.work(files=9, per_file=3)
        self.assertEqual(n, 27)
        r = self.stop()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "", "a capture hook must never write to stdout")
        audits = self.audits()
        self.assertEqual(len(audits), 1, "exactly one record for one session")
        text = audits[0]["text"]
        self.assertIn("file edits counted      27", text)
        self.assertIn("distinct files touched  9", text)
        self.assertIn("/repo/file00.py", text)
        self.assertIn("SAME KIND", text,
                      "the record must carry the cross-instance question forward")

    def test_the_record_never_claims_to_have_classified_anything(self):
        """A hook cannot tell that nine fixes were of a kind. It must not imply it."""
        self.work()
        self.stop()
        text = self.audits()[0]["text"]
        self.assertIn("This hook did not classify anything above.", text)
        self.assertIn("It counted edits and files.", text)

    def test_the_schema_matches_every_other_queue_record(self):
        """`skillinsight` reads the queue generically; a new shape would break it."""
        self.work()
        self.stop()
        self.assertEqual(sorted(self.audits()[0]),
                         ["hash", "project", "session", "source", "text", "ts", "week"])
        self.assertEqual(self.audits()[0]["week"], WEEK)

    def test_the_source_is_distinguishable_from_a_session_authored_one(self):
        self.work()
        self.stop()
        self.assertEqual(self.audits()[0]["source"], "session-audit")

    def test_a_marker_in_the_same_turn_is_still_captured(self):
        """The audit must not swallow or displace the signals that already worked."""
        self.work()
        self.stop(message="Done.\n\n★ Skill candidate: always brace a multibyte "
                          "append in bash, or the glyph folds into the variable name.")
        self.assertEqual(sorted(r["source"] for r in self.records()),
                         ["marker", "session-audit"])


class ThresholdTest(AuditBase):
    """Noise is a failure mode too: a queue that fires constantly gets switched off."""

    def test_a_small_session_produces_nothing(self):
        self.work(files=3, per_file=2)          # 6 edits, 3 files
        self.stop()
        self.assertEqual(self.audits(), [])

    def test_many_edits_to_few_files_produce_nothing(self):
        """Iterating on one thing is not recurrence across things."""
        self.work(files=2, per_file=20)          # 40 edits, 2 files
        self.stop()
        self.assertEqual(self.audits(), [],
                         "40 edits across 2 files is one task, not many")

    def test_many_files_with_few_edits_produce_nothing(self):
        self.work(files=20, per_file=1)          # 20 edits, 20 files
        self.stop()
        self.assertEqual(self.audits(), [],
                         "below the edit floor, however wide the file spread")

    def test_both_thresholds_together_are_what_fires_it(self):
        self.work(files=8, per_file=3)           # 24 edits, 8 files: exactly at both
        self.stop()
        self.assertEqual(len(self.audits()), 1)

    def test_a_below_threshold_session_leaves_no_directory_behind(self):
        """Hoisting the queue-writer above the early exits broke this once already.

        Most turns capture nothing. A hook that creates the queue directory on load
        makes "nothing was captured" untestable, here and in tests/test_insights.py.
        """
        self.work(files=3, per_file=2)
        self.stop()
        self.assertFalse((self.state / "insights").exists())

    def test_a_shell_only_session_still_crosses_the_gate(self):
        """The blind spot that a visible-paths-only gate creates.

        Bypass-permissions sessions are instructed to edit with sed, heredocs and
        inline interpreters, all of which arrive as Bash with a command string and no
        file_path. Measured on 97 real transcripts here: six sessions passed 24 edits
        with fewer than 8 visible paths, one at 356 shell writes against 4 -- exactly
        the long autonomous sessions this record exists for.
        """
        for i in range(30):
            r = self.bash_edit("cat > out%d.txt <<'EOF'\nx\nEOF" % i, uid="sh%d" % i)
            self.assertEqual(r.returncode, 0)
        self.stop()
        self.assertEqual(len(self.audits()), 1)
        text = self.audits()[0]["text"]
        self.assertIn("distinct files touched  0", text)
        self.assertIn("edits with no visible target  30", text)

    def test_an_incomplete_file_list_says_so(self):
        """A floor presented as a total is the exact defect this package is about."""
        self.work(files=9, per_file=3)
        for i in range(5):
            self.bash_edit("sed -i '' s/a/b/ n%d.md" % i, uid="mix%d" % i)
        self.stop()
        text = self.audits()[0]["text"]
        self.assertIn("The file list below is INCOMPLETE.", text)
        self.assertIn("5 of the 32 edits were shell", text)
        self.assertIn("as a floor, never a total", text)

    def test_a_visible_session_is_still_gated_on_breadth(self):
        """The clause must not collapse the gate into 'any busy session'."""
        self.work(files=2, per_file=20)
        self.stop()
        self.assertEqual(self.audits(), [],
                         "40 edits across 2 VISIBLE files is one task; nothing is hidden")

    def test_a_few_shell_edits_do_not_open_the_gate_on_their_own(self):
        """Sites = visible files + invisible edits, and it still has to reach the floor."""
        self.work(files=2, per_file=10)
        for i in range(4):
            self.bash_edit("printf x > f%d" % i, uid="few%d" % i)
        self.stop()
        self.assertEqual(self.audits(), [],
                         "24 edits but only 2 + 4 = 6 sites is still below the floor")

    def test_a_mixed_session_counts_both_kinds_of_site(self):
        """20 shell writes plus 3 visible files is a wide session, and reads as one."""
        for i in range(20):
            self.bash_edit("python3 - <<'PY'\np.write_text(x)\nPY", uid="mx%d" % i)
        self.work(files=3, per_file=2, prefix="/real")
        self.stop()
        self.assertEqual(len(self.audits()), 1)
        text = self.audits()[0]["text"]
        self.assertIn("distinct files touched  3", text)
        self.assertIn("edits with no visible target  20", text)
        # The GATE pools the two numbers; the RECORD must not, because the pool is an
        # upper bound on sites and not a measurement of them.
        self.assertNotIn("distinct edit sites", text)

    def test_the_arm_can_be_switched_off_entirely(self):
        self.work(files=12, per_file=5)
        self.stop(INSIGHT_AUDIT_MIN_EDITS=0)
        self.assertEqual(self.audits(), [],
                         "a user who finds the rate wrong must be able to stop it")

    def test_the_path_list_is_capped_in_the_record(self):
        self.work(files=30, per_file=1, prefix="/wide")
        self.work(files=1, per_file=30, prefix="/deep")
        self.stop(INSIGHT_AUDIT_MAX_PATHS=5)
        text = self.audits()[0]["text"]
        self.assertIn("Files touched (5 of 31, as of this record):", text)
        listed = [l for l in text.splitlines() if l.startswith("  /wide/")
                  or l.startswith("  /deep/")]
        self.assertEqual(len(listed), 5, "the cap bounds the record, not the count")
        # sort -u, so /deep sorts ahead of /wide -- the cap truncates, it does not sample.
        self.assertEqual(listed[0].strip(), "/deep/file00.py")

    def test_a_nonsense_threshold_disables_rather_than_crashes(self):
        self.work(files=12, per_file=5)
        r = self.stop(INSIGHT_AUDIT_MIN_EDITS="lots")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.audits(), [])


class ExactlyOnceTest(AuditBase):
    """Stop fires on every turn, and both install paths deliver every event."""

    def test_repeated_stops_never_write_a_second_record(self):
        self.work()
        for _ in range(8):
            self.assertEqual(self.stop().returncode, 0)
        self.assertEqual(len(self.audits()), 1)

    def test_more_edits_after_the_record_do_not_write_another(self):
        self.work(files=9, per_file=3)
        self.stop()
        self.work(files=9, per_file=3, prefix="/more")
        self.stop()
        self.assertEqual(len(self.audits()), 1,
                         "one record per session, whatever else the session goes on to do")

    def test_both_install_paths_racing_on_one_event_write_one_record(self):
        """With settings.json and the plugin both wired, every Stop arrives twice."""
        self.work()
        procs = []
        payload = json.dumps({"session_id": "s1", "cwd": str(self.state),
                              "last_assistant_message": "done"})
        for _ in range(12):
            procs.append(subprocess.Popen(
                [str(STOP_HOOK)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, env=self.env(INSIGHT_NOW=T_STOP)))
        for pr in procs:
            pr.communicate(input=payload)
        for pr in procs:
            self.assertEqual(pr.returncode, 0)
        self.assertEqual(len(self.audits()), 1,
                         "twelve concurrent deliveries, one record")

    def test_separate_sessions_each_get_their_own(self):
        self.work(sid="alpha")
        self.work(sid="beta", prefix="/other")
        self.stop(sid="alpha")
        self.stop(sid="beta")
        self.assertEqual(len(self.audits()), 2)
        self.assertEqual(sorted(r["session"] for r in self.audits()), ["alpha", "beta"])

    def test_it_does_not_inflate_the_duplicate_statistic(self):
        """`stats` reports duplicates as candidates seen twice, not turns taken."""
        self.work()
        for _ in range(10):
            self.stop()
        dupes = self.state / "insights" / ".dedup-count"
        n = int(dupes.read_text()) if dupes.exists() else 0
        self.assertEqual(n, 0,
                         "re-offering a per-session key each turn is not a duplicate "
                         "candidate, and counting it as one turns the statistic into "
                         "a turn counter")

    def test_a_session_id_needing_sanitisation_still_audits_exactly_once(self):
        """Both hooks must sanitise the id identically or the audit reads nothing."""
        weird = "s/../../evil id"
        self.work(sid=weird)
        self.stop(sid=weird)
        self.stop(sid=weird)
        self.assertEqual(len(self.audits()), 1)
        self.assertEqual(self.audits()[0]["session"], weird,
                         "the record reports the real id, not the filename-safe one")


class EvidenceAccumulationTest(AuditBase):
    """What the edit hook records for the audit to read later."""

    def rem(self, name, sid="s1"):
        return self.state / "reminders" / ("%s.%s" % (sid, name))

    def test_paths_are_deduped_as_they_are_written(self):
        for i in range(6):
            self.edit("/repo/same.py", uid="d%d" % i)
        self.assertEqual(self.rem("paths").read_text().splitlines(), ["/repo/same.py"])

    def test_checkpoints_are_counted(self):
        for i in range(9):
            self.edit("/repo/f%d.py" % i, uid="c%d" % i, CI_EDIT_EVERY=3)
        self.assertEqual(len(self.rem("checkpoints").read_bytes()), 3)

    def test_the_first_edit_stamps_the_window_start(self):
        self.edit("/repo/a.py", uid="f1", CI_NOW=1700)
        self.edit("/repo/b.py", uid="f2", CI_NOW=9999)
        self.assertEqual(self.rem("first").read_text(), "1700",
                         "the stamp marks the first edit, not the latest")

    def test_a_file_writing_bash_command_counts_without_a_path(self):
        """`mutates_file` sees a command string; there is no file_path to record."""
        for i in range(4):
            self.bash_edit("sed -i '' s/a/b/ notes%d.md" % i, uid="b%d" % i)
        self.assertEqual(len(self.rem("edits").read_bytes()), 4)
        self.assertFalse(self.rem("paths").exists(),
                         "a Bash payload carries no file_path; inventing one would be "
                         "a guess, and the file count would stop being a count")

    def test_a_read_only_bash_command_records_nothing_at_all(self):
        self.bash_edit("git status", uid="ro1")
        self.assertFalse(self.rem("edits").exists())
        self.assertFalse(self.rem("first").exists())

    def test_a_subagents_edit_counts_against_the_parent_session(self):
        """Measured on 2.1.245: a subagent's Write arrives as an ordinary PostToolUse
        carrying the PARENT's session_id, plus an agent_id the parent's own events
        lack. Delegating work out does not escape the count, and the extra field must
        not change how the edit is recorded."""
        payload = {"session_id": "s1", "tool_name": "Write",
                   "tool_use_id": "sub1", "agent_id": "a8e650d3fc5fceb74",
                   "tool_input": {"file_path": "/repo/from_subagent.txt"}}
        r = subprocess.run([str(EDIT_HOOK), "edit"], input=json.dumps(payload),
                           capture_output=True, text=True,
                           env=self.env(CI_NOW=T_EDIT))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(self.rem("edits").read_bytes()), 1)
        self.assertEqual(self.rem("paths").read_text().splitlines(),
                         ["/repo/from_subagent.txt"])

    def test_the_evidence_writes_never_change_the_reminder_behaviour(self):
        r = self.edit("/repo/a.py", uid="k1", CI_EDIT_EVERY=1)
        self.assertIn("Checkpoint after 1 file edits", r.stdout)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["hookEventName"],
                         "PostToolUse")


class ForgeObservationTest(AuditBase):
    """Whether the session forged anything is reported as a fact, never as a gate."""

    def ledger(self, *rows):
        p = self.state / "ledger.jsonl"
        p.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return p

    def test_no_ledger_reads_as_none(self):
        self.work()
        self.stop()
        self.assertIn("forges started here     none", self.audits()[0]["text"])

    def test_a_forge_started_in_the_window_is_named(self):
        self.ledger({"event": "start", "name": "yaml-frontmatter", "ts": T_EDIT + 10,
                     "project": "/proj"})
        self.work()
        self.stop(cwd="/proj")
        self.assertIn("forges started here     yaml-frontmatter", self.audits()[0]["text"])

    def test_a_forge_from_before_the_session_is_not_claimed(self):
        self.ledger({"event": "start", "name": "old-one", "ts": T_EDIT - 5000,
                     "project": "/proj"})
        self.work()
        self.stop(cwd="/proj")
        self.assertIn("forges started here     none", self.audits()[0]["text"])

    def test_a_forge_in_another_project_is_not_claimed(self):
        self.ledger({"event": "start", "name": "elsewhere", "ts": T_EDIT + 10,
                     "project": "/somewhere-else"})
        self.work()
        self.stop(cwd="/proj")
        self.assertIn("forges started here     none", self.audits()[0]["text"])

    def test_a_forge_does_not_suppress_the_record(self):
        """One forge is no evidence that the other eight kinds were considered."""
        self.ledger({"event": "start", "name": "did-one", "ts": T_EDIT + 10,
                     "project": "/proj"})
        self.work()
        self.stop(cwd="/proj")
        self.assertEqual(len(self.audits()), 1)

    def test_a_half_written_ledger_line_does_not_lose_the_rest(self):
        p = self.ledger({"event": "start", "name": "good-one", "ts": T_EDIT + 10,
                         "project": "/proj"})
        p.write_text(p.read_text() + '{"event":"start","name":"trunc')
        self.work()
        self.stop(cwd="/proj")
        text = self.audits()[0]["text"]
        self.assertIn("good-one", text)
        self.assertEqual(len(self.audits()), 1)

    def test_a_ledger_of_pure_garbage_is_survivable(self):
        (self.state / "ledger.jsonl").write_bytes(b"\x00\xff not json at all\n" * 40)
        self.work()
        r = self.stop(cwd="/proj")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(self.audits()), 1)


class BrokenStateTest(AuditBase):
    """A hook must never break a turn, whatever it finds on disk."""

    def test_no_reminder_state_at_all(self):
        r = self.stop()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.audits(), [])

    def test_a_directory_where_a_counter_file_belongs(self):
        (self.state / "reminders").mkdir(parents=True)
        (self.state / "reminders" / "s1.edits").mkdir()
        r = self.stop()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.audits(), [])

    def test_an_unreadable_path_list(self):
        self.work()
        p = self.state / "reminders" / "s1.paths"
        p.chmod(0o000)
        try:
            r = self.stop()
        finally:
            p.chmod(0o644)
        self.assertEqual(r.returncode, 0)

    def test_a_read_only_state_root_writes_nothing_and_exits_zero(self):
        self.work()
        insights = self.state / "insights"
        insights.mkdir(exist_ok=True)
        insights.chmod(0o500)
        try:
            r = self.stop()
        finally:
            insights.chmod(0o755)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")

    def test_a_corrupt_queue_file_does_not_stop_the_record(self):
        d = self.state / "insights"
        d.mkdir(parents=True)
        (d / ("%s.jsonl" % WEEK)).write_text("{not json\n\x00\x01\n")
        self.work()
        r = self.stop()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(self.audits()), 1)

    def test_a_malformed_payload_is_survivable(self):
        r = subprocess.run([str(STOP_HOOK)], input="not json at all",
                           capture_output=True, text=True, env=self.env())
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")

    def test_an_empty_payload_is_survivable(self):
        r = subprocess.run([str(STOP_HOOK)], input="",
                           capture_output=True, text=True, env=self.env())
        self.assertEqual(r.returncode, 0)

    def test_home_unset_is_survivable(self):
        """cron, a container, a stripped env: reading $HOME under `set -u` aborts."""
        env = {"PATH": PATH, "SKILL_COMPOUNDER_STATE": str(self.state),
               "INSIGHT_NOW": str(T_STOP)}
        self.work()
        r = subprocess.run([str(STOP_HOOK)],
                           input=json.dumps({"session_id": "s1", "cwd": str(self.state)}),
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(self.audits()), 1)

    def test_a_missing_session_id_does_not_borrow_another_sessions_evidence(self):
        self.work(sid="s1")
        r = subprocess.run([str(STOP_HOOK)],
                           input=json.dumps({"cwd": str(self.state)}),
                           capture_output=True, text=True,
                           env=self.env(INSIGHT_NOW=T_STOP))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.audits(), [],
                         "an idless payload falls back to 'nosession', which has no "
                         "counters of its own; it must not adopt s1's")


class RedTeamFindingsTest(AuditBase):
    """Each of these reproduces a defect a cold reviewer found in this mechanism."""

    def test_a_failed_append_does_not_burn_the_sessions_only_claim(self):
        """The audit's claim key is the session id, so it is offered exactly once.

        The claim is taken before the append, so two racing hooks cannot both write.
        If the append then fails -- a full disk, a read-only queue -- keeping the
        claim retires that session's key permanently and no later Stop can recover it.
        """
        (self.state / "insights" / ".claims").mkdir(parents=True)
        blocked = self.state / "insights" / ("%s.jsonl" % WEEK)
        blocked.mkdir()                      # a directory where the queue file goes
        self.work()
        r = self.stop()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(list((self.state / "insights" / ".claims").iterdir()), [],
                         "a claim for a record that was never written must be released")
        blocked.rmdir()                      # the queue becomes writable again
        self.stop()
        self.assertEqual(len(self.audits()), 1, "the record must still be recoverable")

    def test_a_failed_append_stays_silent_on_stderr(self):
        """`>> "$f" 2>/dev/null` does not suppress a failed redirect.

        The shell reports the failure before applying the 2>/dev/null on the same
        command, so the message reaches the terminal and the hook stops being silent.
        """
        (self.state / "insights").mkdir(parents=True)
        (self.state / "insights" / ("%s.jsonl" % WEEK)).mkdir()
        self.work()
        r = self.stop()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stderr, "", "a hook must never print; it exits 0 silently")

    def test_the_record_never_states_a_site_count_it_did_not_measure(self):
        """24 `sed -i` against one README is 24 opaque edits and ONE site.

        The gate may pool visible files and opaque edits -- that is an upper bound
        used as a threshold. Printing the pooled number as a count of sites would be
        a system making a false claim about itself, which is the defect class this
        whole package exists to catch.
        """
        for i in range(24):
            self.bash_edit("sed -i '' s/a/b/ README.md", uid="same%d" % i)
        self.stop()
        text = self.audits()[0]["text"]
        self.assertIn("edits with no visible target  24", text)
        self.assertNotIn("distinct edit sites", text)

    def test_no_live_list_is_offered_when_no_list_was_ever_written(self):
        for i in range(24):
            self.bash_edit("printf x > out%d.txt" % i, uid="nl%d" % i)
        self.stop()
        text = self.audits()[0]["text"]
        self.assertNotIn("Live list", text)
        self.assertFalse((self.state / "reminders" / "s1.paths").exists())

    def test_scratch_redirects_are_not_project_edits(self):
        """A read-only analysis session must not queue a record.

        `jq . data.json > /tmp/out.json` is how a session parks intermediate output.
        Twenty-four of them changed no project file, and used to read as twenty-four
        edits -- enough to reach a checkpoint and now enough to queue a record.
        """
        scratch = ["jq . data.json > /tmp/out.json",
                   "grep -rn foo src > /var/folders/xx/hits.txt",
                   "cat x >> /private/tmp/log.txt",
                   "ls -la > /tmp/l"]
        for i in range(24):
            r = self.bash_edit(scratch[i % 4], uid="sc%d" % i)
            self.assertEqual(r.stdout.strip(), "", "scratch output is not an edit")
        self.stop()
        self.assertFalse((self.state / "reminders" / "s1.edits").exists())
        self.assertEqual(self.audits(), [])

    def test_a_real_project_write_is_still_counted(self):
        """The scratch filter must not cost the counter what it was built to see."""
        real = ["cat > src/app.py <<EOF\nx\nEOF",
                "./run_tests.sh > suite.log 2>&1",
                "sed -i '' s/a/b/ notes.md",
                "cp a.py b.py",
                "python3 - <<'PY'\np.write_text(x)\nPY"]
        for i, cmd in enumerate(real):
            self.bash_edit(cmd, uid="rw%d" % i)
        self.assertEqual(len((self.state / "reminders" / "s1.edits").read_bytes()),
                         len(real))

    def test_the_scratch_filter_is_written_in_portable_regex(self):
        """`\\|` alternation is a GNU extension; BSD sed matches nothing and says so
        with no error, which puts the old behaviour silently back on macOS."""
        body = (REPO / "hooks" / "compound-improvement.sh").read_text()
        probe = [l for l in body.splitlines() if "var/folders" in l and "sed" not in l]
        self.assertTrue(probe, "the scratch pattern moved; re-check its dialect")
        self.assertNotIn("\\|", probe[0],
                         "BRE alternation does not exist in BSD sed; use sed -E")

    def test_a_session_id_longer_than_a_filename_still_audits(self):
        """Every counter is "$STATE_DIR/$sid.<x>"; an over-long id fails every write."""
        long_sid = "a" * 300
        self.work(sid=long_sid)
        r = self.stop(sid=long_sid)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stderr, "")
        self.assertEqual(len(self.audits()), 1)
        self.assertEqual(self.audits()[0]["session"], long_sid)

    def test_list_counts_records_and_not_rendered_lines(self):
        """A wrapped candidate beginning with a digit was counted as a candidate."""
        self.work()
        self.stop(message="Done.\n\n★ Skill candidate: 12 factor config belongs in "
                          "the environment, not in a file the repository tracks.")
        out = self.cli("list").stdout
        self.assertIn("(2 candidates)", out)
        self.assertIn("12 factor config", out)


class DeclineTest(AuditBase):
    """Declining is an append. Disregarding is what leaves the record standing."""

    def setUp(self):
        super().setUp()
        self.work()
        self.stop()
        self.hash = self.audits()[0]["hash"]

    def test_the_record_names_the_command_that_closes_it(self):
        self.assertIn("skillinsight decline %s" % self.hash, self.audits()[0]["text"])

    def test_declining_never_removes_the_queued_line(self):
        before = (self.state / "insights" / ("%s.jsonl" % WEEK)).read_bytes()
        r = self.cli("decline", self.hash[:8], "--why", "one refactor, not nine kinds")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = (self.state / "insights" / ("%s.jsonl" % WEEK)).read_bytes()
        self.assertEqual(before, after, "the queue file must be byte-identical")

    def test_the_reason_is_recorded(self):
        self.cli("decline", self.hash, "--why", "one refactor, not nine kinds")
        log = self.state / "insights" / ".declined.jsonl"
        rec = json.loads(log.read_text().splitlines()[0])
        self.assertEqual(rec["hash"], self.hash)
        self.assertEqual(rec["why"], "one refactor, not nine kinds")

    def test_list_still_shows_it_marked(self):
        self.cli("decline", self.hash)
        out = self.cli("list").stdout
        self.assertIn("[declined]", out)
        self.assertIn("session-audit", out)

    def test_review_stops_presenting_it_and_says_so(self):
        before = self.cli("review").stdout
        self.assertIn(self.hash[:8], before)
        self.cli("decline", self.hash)
        after = self.cli("review").stdout
        self.assertNotIn(self.hash[:8], after)
        self.assertIn("1 already declined", after)

    def test_stats_counts_it(self):
        self.assertIn("declined:        0", self.cli("stats").stdout)
        self.cli("decline", self.hash)
        self.assertIn("declined:        1", self.cli("stats").stdout)

    def test_an_unknown_hash_is_refused(self):
        r = self.cli("decline", "0000000000")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no queued candidate", r.stderr)
        self.assertFalse((self.state / "insights" / ".declined.jsonl").exists())

    def test_an_ambiguous_prefix_is_refused(self):
        """A prefix that could close the wrong record must not close either."""
        self.work(sid="s2", prefix="/second")
        self.stop(sid="s2")
        r = self.cli("decline", "")
        self.assertNotEqual(r.returncode, 0)

    def test_the_decline_log_is_not_mistaken_for_a_week_of_candidates(self):
        """It lives inside the same directory the *.jsonl glob walks."""
        self.cli("decline", self.hash)
        stats = self.cli("stats").stdout
        self.assertIn("candidates:      1", stats)
        self.assertIn("weeks covered:   1", stats)
        self.assertNotIn(" null", stats)

    def test_declining_does_not_blocklist_the_hash_for_the_capture_hook(self):
        """A decline record carries `"hash":"<h>"`, the exact string the hook greps."""
        self.cli("decline", self.hash)
        self.work(sid="s2", prefix="/second")
        self.stop(sid="s2")
        self.assertEqual(len(self.audits()), 2)

    def test_it_works_when_the_state_directory_contains_a_space(self):
        """`jq ... $(all_files)` word-splits, and the failure looks like a typo.

        A state root under "Application Support" is entirely ordinary, and the broken
        form reported "no queued candidate has a hash starting ...", which reads as
        the reviewer having mistyped rather than as the command being unusable.
        """
        spaced = self.state / "a state dir"
        env = {"PATH": PATH, "HOME": str(self.state),
               "SKILL_COMPOUNDER_STATE": str(spaced), "INSIGHT_NOW": str(T_STOP),
               "CI_NOW": str(T_EDIT)}
        for n in range(9):
            for k in range(3):
                subprocess.run(
                    [str(EDIT_HOOK), "edit"], env=env, capture_output=True, text=True,
                    input=json.dumps({"session_id": "sp", "tool_name": "Edit",
                                      "tool_use_id": "sp%d-%d" % (n, k),
                                      "tool_input": {"file_path": "/r/f%d.py" % n}}))
        subprocess.run([str(STOP_HOOK)], env=env, capture_output=True, text=True,
                       input=json.dumps({"session_id": "sp", "cwd": "/r",
                                         "last_assistant_message": "done"}))
        queued = list((spaced / "insights").glob("*.jsonl"))
        self.assertEqual(len(queued), 1)
        h = json.loads(queued[0].read_text().splitlines()[0])["hash"]
        r = subprocess.run([str(INSIGHT), "decline", h[:8], "--why", "nope"],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("declined %s" % h, r.stdout)

    def test_a_corrupt_decline_log_does_not_make_the_queue_unreadable(self):
        self.cli("decline", self.hash)
        log = self.state / "insights" / ".declined.jsonl"
        log.write_text(log.read_text() + "{{{ not json\n")
        r = self.cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[declined]", r.stdout)


class ReviewSurfaceTest(AuditBase):
    """What the weekly review actually shows a reader."""

    def test_the_live_file_list_is_resolved_when_it_has_grown(self):
        """The record snapshots at the crossing; the session keeps editing after."""
        self.work(files=9, per_file=3)
        self.stop()
        self.assertNotIn("/later/file00.py", self.audits()[0]["text"])
        self.work(files=4, per_file=1, prefix="/later")
        out = self.cli("review").stdout
        self.assertIn("LIVE FILE LIST", out)
        self.assertIn("/later/file00.py", out)
        self.assertIn("13 distinct files", out)

    def test_review_tells_the_reader_that_step_one_does_not_apply(self):
        self.work()
        self.stop()
        out = self.cli("review").stdout
        self.assertIn("SESSION-AUDIT CANDIDATES ARE DIFFERENT", out)
        self.assertIn("NEVER AUTO-FORGE", out)

    def test_the_instructions_heredoc_runs_no_commands(self):
        """It interpolates $week and $n, so a backtick in it is a subshell."""
        self.work()
        self.stop()
        r = self.cli("review")
        self.assertEqual(r.stderr, "", "review must not execute its own prose")
        self.assertEqual(r.returncode, 0)

    def test_list_can_be_filtered_by_source(self):
        self.work()
        self.stop(message="Done.\n\n★ Skill candidate: brace a multibyte append in "
                          "bash or the glyph folds into the variable name.")
        self.assertEqual(len(self.records()), 2)
        out = self.cli("list", "--source", "session-audit").stdout
        self.assertIn("source=session-audit: 1 of 2", out)
        self.assertNotIn("marker  ", out)

    def test_an_unknown_source_filter_shows_nothing_rather_than_everything(self):
        self.work()
        self.stop()
        out = self.cli("list", "--source", "nope").stdout
        self.assertIn("0 of 1", out)

    def test_a_source_typo_is_not_silently_swallowed_by_the_week_parser(self):
        r = self.cli("list", "--sauce", "x")
        self.assertNotEqual(r.returncode, 0)


class InstallPathParityTest(unittest.TestCase):
    """The two install paths must wire the same events; see tests/test_plugin.py."""

    def test_no_new_hook_event_was_introduced(self):
        """Every event in hooks.json must be one the installer also wires.

        This used to freeze the event list as a literal, which went red on the next
        legitimate event (`PostToolUseFailure`) even though the installer had been
        changed in step -- exactly the case it was meant to wave through. So it now
        reads the installer's own `OUR_EVENTS` rather than a copy of it, and fails
        only when the two wirings genuinely disagree. `installer.py` is read as text,
        not imported, because this file runs without PYTHONPATH.
        """
        src = (REPO / "skill_compounder" / "installer.py").read_text()
        m = re.search(r"^OUR_EVENTS = \(([^)]*)\)", src, re.M)
        self.assertIsNotNone(m, "installer.py no longer declares OUR_EVENTS as a "
                                "single-line tuple; this guard needs updating")
        declared = sorted(re.findall(r'"([^"]+)"', m.group(1)))
        self.assertTrue(declared, "OUR_EVENTS parsed empty")
        wiring = json.loads((REPO / "hooks" / "hooks.json").read_text())
        self.assertEqual(sorted(wiring["hooks"]), declared,
                         "a new event here needs the installer changed in step, and "
                         "tests/test_plugin.py asserts the two agree")

    def test_the_audit_runs_on_the_event_that_is_already_wired(self):
        stop = json.loads((REPO / "hooks" / "hooks.json").read_text())["hooks"]["Stop"]
        cmds = [h["command"] for entry in stop for h in entry["hooks"]]
        self.assertTrue(any("insight-capture.sh" in c for c in cmds))


if __name__ == "__main__":
    unittest.main(verbosity=2)
