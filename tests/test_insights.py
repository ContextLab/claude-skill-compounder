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
        # Dropping every directory that contains jq also drops /usr/bin on Linux, which
        # takes bash with it and measures the wrong thing. Build a shadow bin instead:
        # symlink every executable on PATH into one directory, minus jq.
        shadow = self.root / "nojq-bin"
        shadow.mkdir(exist_ok=True)
        for d in PATH.split(":"):
            if not os.path.isdir(d):
                continue
            for name in os.listdir(d):
                if name == "jq":
                    continue
                link = shadow / name
                if not link.exists() and not link.is_symlink():
                    try:
                        link.symlink_to(os.path.join(d, name))
                    except OSError:
                        pass
        no_jq = str(shadow)
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



# The session review that was paid for and never recorded. `hooks/session-review.sh`
# writes the model's raw answer to `reviews/.stage1-<session>.json`, indexes it, and only
# then removes that file; the first real dispatch this package ever made died in between
# -- 2026-08-25, $0.2221734, a well-formed CANDIDATE returned -- and left the answer on
# disk with nothing pointing at it. Everything below plants files of that SHAPE, never a
# copy of the real one, and drives the real CLI over them.
REVIEW_HOOK = REPO / "hooks" / "session-review.sh"

# A CANDIDATE whose EVIDENCE quotes a NONE line, which is the shape that broke the
# substring parser this rule replaced: the prompt orders the model to quote its evidence
# verbatim, and a transcript from this repo contains "VERDICT: NONE" constantly.
CANDIDATE_ANSWER = (
    "VERDICT: CANDIDATE orchestrator-delivery-unreliable\n"
    "DEAD END: the session waited on a message that was never delivered.\n"
    "SECOND OCCURRENCE: it happened again two hours later.\n"
    "EVIDENCE:\n"
    "VERDICT: NONE\n"
    "  VERDICT: CANDIDATE indented-and-must-not-win\n")

NONE_ANSWER = "VERDICT: NONE\nNothing in this session clears the bar.\n"


class ReindexTest(InsightsTestBase):

    def setUp(self):
        super().setUp()
        self.reviews = self.state / "reviews"
        self.reviews.mkdir(parents=True)
        self.transcripts = self.root / ".claude" / "projects"

    # ------------------------------------------------------------------ fixtures

    def plant(self, sid, answer=CANDIDATE_ANSWER, mtime=None, cost=0.2221734,
              as_stream=False, body=None):
        """A stage-1 file of the shape hooks/session-review.sh leaves behind.

        `session_id` here is the id of the session the MODEL ran in, which is what the
        real file carries and what makes reading the reviewed session out of the JSON
        wrong. The reviewed session is in the FILENAME.
        """
        row = {"type": "result", "subtype": "success", "is_error": False,
               "session_id": "99999999-9999-9999-9999-999999999999",
               "num_turns": 1, "duration_ms": 79817, "total_cost_usd": cost,
               "modelUsage": {"claude-haiku-4-5-20251001": {},
                              "claude-sonnet-5": {}}}
        if answer is not None:
            row["result"] = answer
        path = self.reviews / (".stage1-%s.json" % sid)
        if body is not None:
            path.write_text(body)
        else:
            path.write_text(json.dumps([row] if as_stream else row) + "\n")
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def transcript_for(self, sid, cwd, project_dir="-tmp-demo"):
        d = self.transcripts / project_dir
        d.mkdir(parents=True, exist_ok=True)
        p = d / ("%s.jsonl" % sid)
        p.write_text(json.dumps({"type": "summary", "summary": "no cwd here"}) + "\n"
                     + json.dumps({"type": "user", "cwd": cwd,
                                   "sessionId": sid}) + "\n")
        return p

    def rows(self):
        idx = self.reviews / "index.jsonl"
        if not idx.exists():
            return []
        return [json.loads(line) for line in idx.read_text().splitlines()
                if line.strip()]

    def unread(self):
        f = self.reviews / ".unread"
        return f.read_text().splitlines() if f.exists() else []

    def verdict_of_hook(self, answer):
        """What hooks/session-review.sh's own parser makes of the same text.

        `payload="$(cat)"`-shaped: the hook reads stdin, so `input=` is mandatory or the
        call hangs forever.
        """
        r = subprocess.run([str(REVIEW_HOOK), "--verdict-of"], input=answer,
                           capture_output=True, text=True, env=self.env(),
                           timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0, r.stderr)
        parts = r.stdout.rstrip("\n").split("\t")
        return parts[0], (parts[1] if len(parts) > 1 else "")

    # ------------------------------------------------------------------ recovery

    def test_a_lost_candidate_is_indexed_from_the_answer_it_left_behind(self):
        self.plant("aaaa1111-0000-0000-0000-000000000001")
        r = self.run_cli("reindex")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.rows()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["verdict"], "CANDIDATE")
        self.assertEqual(rows[0]["name"], "orchestrator-delivery-unreliable")
        self.assertEqual(rows[0]["session"], "aaaa1111-0000-0000-0000-000000000001")
        self.assertEqual(rows[0]["cost_usd"], "0.2221734")
        self.assertEqual(rows[0]["stage"], "analysis")

    def test_the_row_says_it_was_reindexed_and_names_the_file_it_came_from(self):
        """A row nobody can tell from a live one hides that a dispatch failed."""
        self.plant("aaaa1111-0000-0000-0000-000000000002")
        self.run_cli("reindex")
        row = self.rows()[0]
        self.assertIn("reindexed_at", row)
        self.assertTrue(row["reindexed_at"].endswith("Z"), row["reindexed_at"])
        self.assertEqual(row["source_file"],
                         ".stage1-aaaa1111-0000-0000-0000-000000000002.json")

    def test_a_second_run_appends_nothing(self):
        self.plant("aaaa1111-0000-0000-0000-000000000003")
        self.run_cli("reindex")
        first = (self.reviews / "index.jsonl").read_text()
        r = self.run_cli("reindex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.reviews / "index.jsonl").read_text(), first,
                         "reindex must be idempotent: the index is its own state")
        self.assertEqual(len(self.unread()), 1, "nor may it re-announce")
        self.assertIn("already indexed", r.stdout)

    def test_a_session_already_in_the_index_is_left_alone(self):
        sid = "aaaa1111-0000-0000-0000-000000000004"
        self.plant(sid)
        (self.reviews / "index.jsonl").write_text(json.dumps(
            {"ts": "2025-08-01T00:00:00Z", "week": "2025-W31", "session": sid,
             "verdict": "NONE", "name": "", "stage": "analysis"}) + "\n")
        self.run_cli("reindex")
        self.assertEqual(len(self.rows()), 1, "a live row must not be duplicated")
        self.assertNotIn("reindexed_at", self.rows()[0])

    def test_a_half_written_last_index_line_does_not_cause_a_duplicate(self):
        """The dispatcher appends from another process. A plain stream read aborts on a
        torn last line and loses every row before it -- here that means re-appending
        rows that are already there, which is the one thing this must never do."""
        sid = "aaaa1111-0000-0000-0000-000000000005"
        self.plant(sid)
        (self.reviews / "index.jsonl").write_text(
            json.dumps({"ts": "2025-08-01T00:00:00Z", "session": sid,
                        "verdict": "NONE"}) + "\n" + '{"ts":"2025-08-02T00:00')
        self.run_cli("reindex")
        text = (self.reviews / "index.jsonl").read_text()
        self.assertEqual(text.count(sid), 1, text)

    def test_the_stage_one_file_is_never_deleted(self):
        """It is the evidence for the row and the only copy of what was paid for."""
        p = self.plant("aaaa1111-0000-0000-0000-000000000006")
        self.run_cli("reindex")
        self.assertTrue(p.exists())

    # ------------------------------------------------------- the verdict rules

    def test_the_verdict_matches_the_dispatchers_own_parser(self):
        """Two copies of one rule need a check that they agree, not a comment saying so.

        `bin/skillinsight` reimplements `parse_verdict` because the CLI has to work with
        only itself on disk. This drives both over the same answers.
        """
        cases = {
            "aaaa2222-0000-0000-0000-000000000001": CANDIDATE_ANSWER,
            "aaaa2222-0000-0000-0000-000000000002": NONE_ANSWER,
            "aaaa2222-0000-0000-0000-000000000003":
                "The session went fine but nothing here begins with the word.\n",
            "aaaa2222-0000-0000-0000-000000000004":
                "VERDICT: CANDIDATE\nno name on the line at all\n",
            "aaaa2222-0000-0000-0000-000000000005":
                "  VERDICT: NONE\nindented, so it is not a verdict line\n",
            # THE CASE THAT MAKES THE ANCHOR LOAD-BEARING, and the only one here that
            # separates `grep '^VERDICT:'` from `grep 'VERDICT:'`. Dropping the caret
            # makes the first line win, and it is not a verdict -- so a real CANDIDATE
            # is recorded as UNPARSED. Checked by mutating the CLI: with the anchor
            # removed this row comes back UNPARSED and this test fails, which is what
            # tells us the rule is doing work rather than sitting there.
            "aaaa2222-0000-0000-0000-000000000006":
                "The reviewer had written VERDICT: NONE in a quote above.\n"
                "VERDICT: CANDIDATE quoted-line-must-not-win\n",
        }
        for sid, answer in cases.items():
            self.plant(sid, answer=answer)
        self.run_cli("reindex")
        rows = {row["session"]: row for row in self.rows()}
        self.assertEqual(len(rows), len(cases), rows)
        for sid, answer in cases.items():
            verdict, name = self.verdict_of_hook(answer)
            self.assertEqual(rows[sid]["verdict"], verdict,
                             "%s: CLI and hook disagree on %r" % (sid, answer))
            self.assertEqual(rows[sid]["name"], name, sid)

    def test_a_none_verdict_is_indexed_but_not_announced(self):
        """`.unread` is the next session's first-prompt announcement. "Nothing cleared
        the bar" is news on the day and noise a fortnight later; the index has it."""
        self.plant("aaaa3333-0000-0000-0000-000000000001", answer=NONE_ANSWER)
        self.run_cli("reindex")
        self.assertEqual(self.rows()[0]["verdict"], "NONE")
        self.assertEqual(self.unread(), [])

    def test_a_candidate_is_announced_in_unread(self):
        self.plant("aaaa3333-0000-0000-0000-000000000002")
        self.run_cli("reindex")
        lines = self.unread()
        self.assertEqual(len(lines), 1, lines)
        fields = lines[0].split("\t")
        self.assertEqual(len(fields), 3, fields)
        self.assertEqual(fields[1], "CANDIDATE orchestrator-delivery-unreliable")
        self.assertTrue(Path(fields[2]).exists(), fields[2])

    def test_an_answer_with_no_verdict_line_is_unparsed_not_error(self):
        """The call ran and was paid for. Reporting that as a crash sends whoever reads
        it looking for a bug in the wrong place."""
        self.plant("aaaa3333-0000-0000-0000-000000000003",
                   answer="I could not decide, sorry.\n")
        self.run_cli("reindex")
        self.assertEqual(self.rows()[0]["verdict"], "UNPARSED")

    def test_a_file_with_no_answer_in_it_is_not_indexed_at_all(self):
        """Nothing was recovered, so a permanent row asserting a failure this command
        cannot observe would only block a real recovery later -- the row IS the
        idempotence key."""
        self.plant("aaaa3333-0000-0000-0000-000000000004", answer=None)
        r = self.run_cli("reindex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows(), [])
        self.assertIn("no model answer", r.stdout)

    def test_a_stream_array_is_accepted_as_well_as_a_bare_object(self):
        """`--output-format json` returns either, depending on what else is loaded."""
        self.plant("aaaa3333-0000-0000-0000-000000000005", as_stream=True)
        self.run_cli("reindex")
        self.assertEqual(self.rows()[0]["verdict"], "CANDIDATE")

    def test_unreadable_json_is_survived(self):
        self.plant("aaaa3333-0000-0000-0000-000000000006", body="{not json at all\n")
        r = self.run_cli("reindex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows(), [])

    # ------------------------------------------------------------ what the row says

    def test_the_timestamp_is_the_answers_own_age_not_todays(self):
        """A verdict recovered a week late is still a verdict from the day it returned.
        Filing it under today would sort it above reviews that came after it."""
        old = NOW - 90 * 86400
        self.plant("aaaa4444-0000-0000-0000-000000000001", mtime=old)
        self.run_cli("reindex")
        row = self.rows()[0]
        self.assertEqual(row["ts"], time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime(old)))
        self.assertEqual(row["week"], time.strftime("%G-W%V", time.gmtime(old)))
        self.assertNotEqual(row["ts"], row["reindexed_at"])
        self.assertEqual(row["reindexed_at"],
                         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW)))

    def test_the_project_is_recovered_from_the_reviewed_sessions_transcript(self):
        """The stage-1 JSON's `session_id` is the id of the session the MODEL ran in, so
        the project can only come from the transcript of the session under review."""
        sid = "aaaa4444-0000-0000-0000-000000000002"
        self.plant(sid)
        self.transcript_for(sid, "/tmp/some-repo")
        self.run_cli("reindex")
        self.assertEqual(self.rows()[0]["project"], "/tmp/some-repo")

    def test_a_missing_transcript_leaves_the_project_empty_rather_than_guessed(self):
        self.plant("aaaa4444-0000-0000-0000-000000000003")
        self.run_cli("reindex")
        self.assertEqual(self.rows()[0]["project"], "")

    def test_the_transcript_root_is_overridable(self):
        sid = "aaaa4444-0000-0000-0000-000000000004"
        self.plant(sid)
        alt = self.root / "elsewhere"
        (alt / "-x").mkdir(parents=True)
        (alt / "-x" / ("%s.jsonl" % sid)).write_text(
            json.dumps({"type": "user", "cwd": "/tmp/elsewhere"}) + "\n")
        self.run_cli("reindex", SKILL_COMPOUNDER_TRANSCRIPTS=str(alt))
        self.assertEqual(self.rows()[0]["project"], "/tmp/elsewhere")

    def test_the_model_field_is_empty_rather_than_guessed(self):
        """`modelUsage` names every model the call touched -- on the real lost dispatch,
        two -- and none of them records which one the dispatcher asked for."""
        self.plant("aaaa4444-0000-0000-0000-000000000005")
        self.run_cli("reindex")
        self.assertEqual(self.rows()[0]["model"], "")

    # ---------------------------------------------------------------- the report

    def test_a_report_is_written_and_reviews_can_print_it(self):
        self.plant("aaaa5555-0000-0000-0000-000000000001")
        self.run_cli("reindex")
        report = Path(self.rows()[0]["report"])
        self.assertTrue(report.exists(), report)
        body = report.read_text()
        self.assertIn("orchestrator-delivery-unreliable", body)
        self.assertIn("- session:", body)
        r = self.run_cli("reviews", "--show", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("orchestrator-delivery-unreliable", r.stdout)

    def test_the_report_says_it_was_recovered_and_from_where(self):
        sid = "aaaa5555-0000-0000-0000-000000000002"
        self.plant(sid)
        self.run_cli("reindex")
        body = Path(self.rows()[0]["report"]).read_text()
        self.assertIn("recovered", body.lower())
        self.assertIn(".stage1-%s.json" % sid, body)

    def test_an_existing_report_is_never_overwritten(self):
        sid = "aaaa5555-0000-0000-0000-000000000003"
        old = NOW - 90 * 86400
        self.plant(sid, mtime=old)
        week = time.strftime("%G-W%V", time.gmtime(old))
        (self.reviews / week).mkdir(parents=True, exist_ok=True)
        existing = self.reviews / week / ("%s.md" % sid)
        existing.write_text("recovered by hand, do not clobber\n")
        self.run_cli("reindex")
        self.assertEqual(existing.read_text(), "recovered by hand, do not clobber\n")
        self.assertEqual(self.rows()[0]["report"], str(existing))

    def test_a_recovered_review_sorts_by_its_own_age_not_by_when_it_was_appended(self):
        """`reviews` promises "newest first" and `--show 1` promises the same row.

        Reversing the file delivered that for as long as the dispatcher was the only
        writer. `reindex` appends an answer that came back weeks ago, so a listing that
        reverses the file puts the OLDEST review at position 1 and calls it the newest.
        """
        idx = self.reviews / "index.jsonl"
        recent = self.reviews / "2025-W34"
        recent.mkdir(parents=True, exist_ok=True)
        live_report = recent / "live.md"
        live_report.write_text("# a review that happened yesterday\n")
        idx.write_text(json.dumps(
            {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 86400)),
             "week": WEEK, "session": "live-and-recent", "project": "/p",
             "verdict": "NONE", "name": "", "report": str(live_report),
             "cost_usd": "0.10", "model": "sonnet", "stage": "analysis"}) + "\n")
        self.plant("aaaa6666-0000-0000-0000-000000000001", mtime=NOW - 90 * 86400)
        self.run_cli("reindex")
        out = self.run_cli("reviews").stdout
        newest = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 86400))
        oldest = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 90 * 86400))
        self.assertIn(newest, out)
        self.assertIn(oldest, out)
        self.assertLess(out.index(newest), out.index(oldest),
                        "the recovered review is the OLDEST; it must not head the "
                        "list just because it was appended last:\n" + out)
        self.assertIn("a review that happened yesterday",
                      self.run_cli("reviews", "--show", "1").stdout)

    def test_the_listing_shows_the_recovered_review(self):
        self.plant("aaaa5555-0000-0000-0000-000000000004")
        self.run_cli("reindex")
        r = self.run_cli("reviews")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("orchestrator-delivery-unreliable", r.stdout)
        self.assertIn("automatic session reviews: 1", r.stdout)

    # ------------------------------------------------------------------ argument

    def test_nothing_to_do_is_a_success(self):
        r = self.run_cli("reindex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 indexed", r.stdout)

    def test_no_reviews_directory_at_all_is_a_success(self):
        shutil.rmtree(self.reviews)
        r = self.run_cli("reindex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing to reindex", r.stdout)

    def test_it_takes_no_arguments(self):
        r = self.run_cli("reindex", "--week", "2025-W34")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no arguments", r.stderr)

    def test_it_is_in_the_usage_text(self):
        """A recovery command nobody can find recovers nothing."""
        r = self.run_cli("--help")
        self.assertIn("skillinsight reindex", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
