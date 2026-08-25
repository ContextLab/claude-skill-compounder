#!/usr/bin/env python3
"""Runs the real capture hook and the real skillinsight CLI against real files.

No mocks. Every test writes a genuine hook payload, pipes it into the hook as a
subprocess, and reads the resulting JSONL queue back off disk. The transcript
fallback gets a real transcript file, including a truncated leading line, because
that is what `tail -c` on a live transcript actually produces.

The facts pinned here come from notes/research/insight-capture.md:

  * `last_assistant_message` alone catches 76% of blocks, so capture must work with
    no transcript file present at all.
  * The remaining 24% are mid-turn and need a bounded read of the transcript. The
    read must be bounded: the largest transcript measured was 663 MB.
  * 584 of 854 raw `★ Insight` hits were the output-style plugin's own SessionStart
    injection echoed back inside `attachment` records. Capturing those means the
    queue fills with our own instruction text.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "hooks" / "insight-capture.sh"
CLI = REPO / "bin" / "skillinsight"

PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
# Every subprocess call carries this. Nothing here does real work, so anything that
# takes longer is wedged, and a wedged hook must fail the test rather than stall the
# suite. One earlier version did stall: see test_a_large_transcript_does_not_wedge.
TIMEOUT = 20
NOW = 1755993600          # 2025-08-24T00:00:00Z, ISO week 2025-W34
WEEK = "2025-W34"

MARKER = ("★ Skill candidate: a hook that reads the whole transcript hangs, because the "
          "largest one on disk is 663 MB.\nBound the read with tail -c instead.")

INSIGHT = ("`★ Insight " + "─" * 20 + "`\n"
           "jq counts codepoints where bash counts bytes, which is why the progress bar "
           "drifts by one cell per multibyte glyph.\n"
           "`" + "─" * 24 + "`")

# The learning-output-style plugin's own SessionStart injection, verbatim in shape.
# This is the text behind the 584 false positives.
INJECTION = (
    "## Insights\nIn order to encourage learning, before and after writing code, always "
    "provide brief educational explanations about implementation choices using (with "
    'backticks): "`★ Insight ' + "─" * 20 + "`\n[2-3 key educational points]\n`"
    + "─" * 24 + '`"')


class InsightsTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.queue = self.state / "insights"

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra):
        e = {"PATH": PATH, "HOME": str(self.root),
             "SKILL_COMPOUNDER_STATE": str(self.state), "INSIGHT_NOW": str(NOW)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def run_hook(self, payload, raw=None, **extra):
        data = raw if raw is not None else json.dumps(payload)
        return subprocess.run([str(HOOK)], input=data, capture_output=True,
                              text=True, env=self.env(**extra), timeout=TIMEOUT)

    def run_cli(self, *args, **extra):
        return subprocess.run([str(CLI)] + list(args), capture_output=True,
                              text=True, env=self.env(**extra), timeout=TIMEOUT)

    def records(self, week=WEEK):
        f = self.queue / ("%s.jsonl" % week)
        if not f.exists():
            return []
        return [json.loads(line) for line in f.read_text().splitlines() if line.strip()]

    def write_transcript(self, *texts, truncated_first_line=True):
        """A real transcript file, shaped like the ones on disk."""
        path = self.root / "transcript.jsonl"
        rows = []
        # The plugin's injection, in the record type that actually carries it.
        rows.append({"type": "attachment",
                     "attachment": {"type": "hook_additional_context",
                                    "hookName": "SessionStart",
                                    "hookEvent": "SessionStart",
                                    "additionalContext": INJECTION}})
        rows.append({"type": "attachment",
                     "attachment": {"type": "hook_success",
                                    "hookName": "SessionStart:startup",
                                    "hookEvent": "SessionStart",
                                    "content": INJECTION}})
        for t in texts:
            rows.append({"type": "assistant", "isSidechain": False,
                         "sessionId": "s1", "cwd": str(self.root),
                         "message": {"role": "assistant", "content": [
                             {"type": "thinking", "thinking": "not assistant text"},
                             {"type": "text", "text": t}]}})
        body = "".join(json.dumps(r) + "\n" for r in rows)
        if truncated_first_line:
            body = '{"type":"assistant","message":{"content":[{"type":"te' + "\n" + body
        path.write_text(body)
        return path


class CaptureTest(InsightsTestBase):

    # ------------------------------------------------- last_assistant_message

    def test_marker_captured_from_last_assistant_message_with_no_transcript(self):
        r = self.run_hook({"session_id": "s1", "cwd": str(self.root),
                           "hook_event_name": "Stop",
                           "last_assistant_message": "Some preamble.\n\n" + MARKER + "\n"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "", "a capture hook must print nothing")
        recs = self.records()
        self.assertEqual(len(recs), 1, "the marker is the primary signal and must capture")
        self.assertEqual(recs[0]["source"], "marker")
        self.assertIn("663 MB", recs[0]["text"])
        self.assertIn("Bound the read", recs[0]["text"],
                      "the marker's whole paragraph is the candidate")
        self.assertNotIn("Some preamble", recs[0]["text"])
        self.assertEqual(recs[0]["week"], WEEK)
        self.assertEqual(recs[0]["session"], "s1")
        self.assertTrue(recs[0]["hash"])

    def test_star_insight_captured_from_last_assistant_message(self):
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "last_assistant_message": "Text.\n\n" + INSIGHT + "\n\nMore text."})
        recs = self.records()
        self.assertEqual([r["source"] for r in recs], ["star-insight"])
        self.assertIn("jq counts codepoints", recs[0]["text"])
        self.assertNotIn("★ Insight", recs[0]["text"], "the delimiters are not the lesson")

    def test_both_signals_in_one_turn(self):
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "last_assistant_message": INSIGHT + "\n\n" + MARKER + "\n"})
        self.assertEqual(sorted(r["source"] for r in self.records()),
                         ["marker", "star-insight"])

    def test_alternate_marker_spelling_is_accepted(self):
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "last_assistant_message":
                           "SKILL-CANDIDATE: the installer must back up settings.json "
                           "before every write, because one malformed file disables "
                           "every setting in it.\n"})
        recs = self.records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["source"], "marker")

    def test_record_has_every_documented_field(self):
        self.run_hook({"session_id": "s1", "cwd": str(self.root),
                       "hook_event_name": "Stop", "last_assistant_message": MARKER})
        rec = self.records()[0]
        self.assertEqual(sorted(rec),
                         ["hash", "project", "session", "source", "text", "ts", "week"])

    def test_project_resolves_to_the_git_toplevel(self):
        repo = self.root / "work" / "nested" / "deep"
        repo.mkdir(parents=True)
        top = self.root / "work"
        subprocess.run(["git", "init", "-q", str(top)], capture_output=True,
                       env={"PATH": PATH, "HOME": str(self.root)}, timeout=TIMEOUT)
        self.run_hook({"session_id": "s1", "cwd": str(repo),
                       "hook_event_name": "Stop", "last_assistant_message": MARKER})
        rec = self.records()[0]
        self.assertEqual(os.path.realpath(rec["project"]), os.path.realpath(str(top)),
                         "provenance is the repo root, not the subdirectory")

    # ------------------------------------------------------ bounded fallback

    def test_fallback_reads_the_transcript_when_last_assistant_message_is_absent(self):
        tp = self.write_transcript("mid-turn commentary.\n\n" + INSIGHT + "\n")
        r = self.run_hook({"session_id": "s1", "cwd": str(self.root),
                           "hook_event_name": "Stop", "transcript_path": str(tp)})
        self.assertEqual(r.returncode, 0)
        recs = self.records()
        self.assertEqual(len(recs), 1, "the 24% of mid-turn blocks need the transcript")
        self.assertIn("jq counts codepoints", recs[0]["text"])

    def test_fallback_read_is_bounded(self):
        """Only the tail within the byte budget may be read."""
        tp = self.write_transcript(INSIGHT + "\n")
        padding = json.dumps({"type": "assistant", "message": {"role": "assistant",
                              "content": [{"type": "text", "text": "x" * 4000}]}})
        with open(tp, "a") as f:
            for _ in range(400):          # roughly 1.6 MB of newer records
                f.write(padding + "\n")
        self.assertGreater(tp.stat().st_size, 1_000_000)
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "transcript_path": str(tp)}, INSIGHT_TAIL_BYTES=65536)
        self.assertEqual(self.records(), [],
                         "an insight older than the byte budget must not be reachable, "
                         "or the read was not bounded")

    def test_fallback_ignores_a_truncated_leading_line(self):
        tp = self.write_transcript(MARKER + "\n", truncated_first_line=True)
        r = self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                           "transcript_path": str(tp)})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(self.records()), 1)

    def test_missing_transcript_file_is_survivable(self):
        r = self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                           "transcript_path": str(self.root / "gone.jsonl")})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertFalse(self.queue.exists())

    # ------------------------------- the 584 false positives must be rejected

    def test_plugin_injection_in_attachment_records_is_not_captured(self):
        """584 of 854 raw marker hits were this text, echoed back in attachments."""
        tp = self.write_transcript()      # attachments only, no assistant text
        r = self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                           "transcript_path": str(tp)})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.records(), [],
                         "the plugin's own SessionStart injection is not an insight")

    def test_injection_alongside_real_text_captures_only_the_real_text(self):
        tp = self.write_transcript(INSIGHT + "\n")
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "transcript_path": str(tp)})
        recs = self.records()
        self.assertEqual(len(recs), 1)
        self.assertNotIn("key educational points", recs[0]["text"])

    def test_injection_reaching_assistant_text_is_still_rejected(self):
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "last_assistant_message": INJECTION})
        self.assertEqual(self.records(), [],
                         "the instruction template is never a candidate, wherever it rides")

    def test_hook_output_is_never_reingested(self):
        """Running the hook twice on its own instruction text stays at zero."""
        for _ in range(2):
            self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                           "last_assistant_message": INJECTION})
        self.assertEqual(self.records(), [])

    # -------------------------------------------------------------- dedup

    def test_the_same_insight_twice_yields_one_record(self):
        payload = {"session_id": "s1", "hook_event_name": "Stop",
                   "last_assistant_message": INSIGHT}
        self.run_hook(payload)
        self.run_hook(payload)
        self.assertEqual(len(self.records()), 1)

    def test_dedup_survives_reformatting(self):
        """Normalisation collapses whitespace and a trailing period before hashing."""
        first = "SKILL-CANDIDATE: settings.json is backed up before every write.\n"
        again = "SKILL-CANDIDATE: settings.json   is backed up\nbefore every write\n"
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "last_assistant_message": first})
        self.run_hook({"session_id": "s2", "hook_event_name": "Stop",
                       "last_assistant_message": again})
        self.assertEqual(len(self.records()), 1)

    def test_dedup_spans_weeks(self):
        payload = {"session_id": "s1", "hook_event_name": "Stop",
                   "last_assistant_message": INSIGHT}
        self.run_hook(payload)
        self.run_hook(payload, INSIGHT_NOW=NOW + 7 * 86400)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.records("2025-W35"), [])

    def test_distinct_insights_are_both_kept(self):
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "last_assistant_message": INSIGHT})
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "last_assistant_message": MARKER})
        self.assertEqual(len(self.records()), 2)

    def test_duplicates_are_counted(self):
        payload = {"session_id": "s1", "hook_event_name": "Stop",
                   "last_assistant_message": INSIGHT}
        self.run_hook(payload)
        self.run_hook(payload)
        self.assertEqual((self.queue / ".dedup-count").read_text().strip(), "1")

    # -------------------------------------------------------------- safety

    def test_malformed_payload_is_survivable(self):
        r = self.run_hook(None, raw="not json at all {{{")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertFalse(self.queue.exists())

    def test_empty_payload_is_survivable(self):
        r = self.run_hook(None, raw="")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_closed_stdin_does_not_block(self):
        """A hook that waits on stdin freezes the user's turn.

        `payload="$(cat)"` returns immediately on a closed descriptor, and this pins
        that: no input is written at all, the descriptor is /dev/null."""
        r = subprocess.run([str(HOOK)], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, env=self.env(),
                           timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertFalse(self.queue.exists())

    def test_transcript_path_that_is_a_directory_is_survivable(self):
        d = self.root / "notafile"
        d.mkdir()
        r = self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                           "transcript_path": str(d)})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_transcript_path_that_is_a_fifo_does_not_block(self):
        """A named pipe with no writer blocks forever on open. It must be skipped."""
        fifo = self.root / "fifo.jsonl"
        os.mkfifo(fifo)
        r = self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                           "transcript_path": str(fifo)})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_a_large_transcript_does_not_wedge(self):
        """Regression: the emptiness check used to be quadratic on bash 3.2.

        `[ -z "${text//[[:space:]]/}" ]` over the ~60 KB blob a bounded read returns
        spun for minutes on /bin/bash, which is what /usr/bin/env bash finds on
        macOS. The TIMEOUT on this call is the assertion."""
        tp = self.write_transcript(INSIGHT + "\n")
        padding = json.dumps({"type": "assistant", "message": {"role": "assistant",
                              "content": [{"type": "text", "text": "x" * 4000}]}})
        with open(tp, "a") as f:
            for _ in range(400):
                f.write(padding + "\n")
        started = time.monotonic()
        r = self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                           "transcript_path": str(tp)})
        self.assertEqual(r.returncode, 0)
        self.assertLess(time.monotonic() - started, 10,
                        "the bounded read path must stay cheap")

    def test_nothing_to_capture_writes_nothing(self):
        r = self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                           "last_assistant_message": "Done. The tests pass."})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertFalse(self.queue.exists(), "an empty turn must not create the queue")

    def test_missing_jq_is_survivable(self):
        """With jq off the PATH the hook must still exit 0 and stay silent.

        The PATH keeps every other tool, so this measures the hook's behaviour and
        not the shell's inability to start."""
        if shutil.which("jq", path=PATH) is None:
            self.skipTest("jq is not installed, so its absence proves nothing here")
        keep = [d for d in PATH.split(":") if not os.path.exists(os.path.join(d, "jq"))]
        no_jq = ":".join(keep)
        self.assertIsNone(shutil.which("jq", path=no_jq))
        self.assertIsNotNone(shutil.which("bash", path=no_jq),
                             "the shell itself must still be reachable")
        env = {"PATH": no_jq, "HOME": str(self.root),
               "SKILL_COMPOUNDER_STATE": str(self.state), "INSIGHT_NOW": str(NOW)}
        r = subprocess.run([str(HOOK)], input=json.dumps(
            {"session_id": "s1", "last_assistant_message": MARKER}),
            capture_output=True, text=True, env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertFalse(self.queue.exists())

    def test_subagent_stop_is_accepted(self):
        """Measured yield from subagents is zero, but it must not explode."""
        r = self.run_hook({"session_id": "s1", "hook_event_name": "SubagentStop",
                           "agent_id": "a1", "agent_type": "explore",
                           "last_assistant_message": "no candidates here"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_missing_session_id_is_survivable(self):
        r = self.run_hook({"hook_event_name": "Stop", "last_assistant_message": MARKER})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.records()[0]["session"], "nosession")

    def test_per_turn_cap_is_enforced(self):
        many = "\n\n".join("SKILL-CANDIDATE: distinct lesson number %d about ordering "
                           "constraints in the installer." % i for i in range(10))
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "last_assistant_message": many}, INSIGHT_MAX_PER_TURN=3)
        self.assertEqual(len(self.records()), 3)


class CliTest(InsightsTestBase):

    def seed(self):
        self.run_hook({"session_id": "s1", "cwd": str(self.root),
                       "hook_event_name": "Stop",
                       "last_assistant_message": INSIGHT + "\n\n" + MARKER + "\n"})
        self.assertEqual(len(self.records()), 2)

    def test_help_exits_zero_and_names_the_marker(self):
        r = self.run_cli("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("★ Skill candidate:", r.stdout)
        self.assertIn("SKILL-CANDIDATE:", r.stdout)

    def test_unknown_command_fails_loudly(self):
        r = self.run_cli("frobnicate")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown command", r.stderr)

    def test_list_shows_the_queue(self):
        self.seed()
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0)
        self.assertIn(WEEK, r.stdout)
        self.assertIn("marker", r.stdout)
        self.assertIn("star-insight", r.stdout)
        self.assertIn("jq counts codepoints", r.stdout)

    def test_list_accepts_an_explicit_week(self):
        self.seed()
        r = self.run_cli("list", "--week", "2025-W01")
        self.assertEqual(r.returncode, 0)
        self.assertIn("nothing queued for 2025-W01", r.stdout)

    def test_review_emits_one_batch_with_instructions(self):
        self.seed()
        r = self.run_cli("review")
        self.assertEqual(r.returncode, 0)
        self.assertIn("KERNEL EXTRACTION", r.stdout)
        self.assertIn("UNIVERSAL", r.stdout)
        self.assertIn("LOCAL", r.stdout)
        self.assertIn("DISCARD", r.stdout)
        self.assertIn("NEVER AUTO-FORGE", r.stdout)
        self.assertIn("663 MB", r.stdout)
        self.assertIn("jq counts codepoints", r.stdout)

    def test_review_refuses_to_imply_forging(self):
        self.seed()
        out = self.run_cli("review").stdout
        self.assertIn("skill-compounder", out,
                      "survivors must be routed to the existing threshold")
        self.assertIn("measured at chance", out,
                      "the dropped classifier must be recorded where the reviewer reads")

    def test_stats_counts_the_queue(self):
        self.seed()
        self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                       "last_assistant_message": INSIGHT})     # a duplicate
        r = self.run_cli("stats")
        self.assertEqual(r.returncode, 0)
        self.assertIn("candidates:      2", r.stdout)
        self.assertIn("weeks covered:   1", r.stdout)
        self.assertIn("duplicates skipped: 1", r.stdout)

    def test_stats_on_an_empty_queue(self):
        r = self.run_cli("stats")
        self.assertEqual(r.returncode, 0)
        self.assertIn("empty", r.stdout)

    def test_prune_archives_old_weeks_and_keeps_recent_ones(self):
        self.seed()
        self.run_hook({"session_id": "s2", "hook_event_name": "Stop",
                       "last_assistant_message":
                           "SKILL-CANDIDATE: a much later lesson about ordering.\n"},
                      INSIGHT_NOW=NOW + 5 * 7 * 86400)
        later = NOW + 5 * 7 * 86400
        r = self.run_cli("prune", "--older-than", "2", INSIGHT_NOW=later)
        self.assertEqual(r.returncode, 0)
        self.assertIn("archived 1", r.stdout)
        self.assertFalse((self.queue / ("%s.jsonl" % WEEK)).exists())
        self.assertTrue((self.queue / "archive" / ("%s.jsonl" % WEEK)).exists(),
                        "pruning archives, it never deletes")
        self.assertEqual(len(list(self.queue.glob("*.jsonl"))), 1)

    def test_prune_requires_its_argument(self):
        r = self.run_cli("prune")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--older-than", r.stderr)

    def test_prune_rejects_a_non_numeric_argument(self):
        r = self.run_cli("prune", "--older-than", "lots")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
