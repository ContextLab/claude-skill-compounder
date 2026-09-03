#!/usr/bin/env python3
"""Runs the real PreCompact hook against real transcripts and a real state directory.

No mocks anywhere. Every test writes a genuine hook payload, pipes it into
`hooks/precompact.sh` as a subprocess, and reads the resulting JSONL queue back off disk.
The transcripts are real files with the shapes a live transcript has, truncated leading
line included, because that is what `tail -c` produces.

The payload these tests use is not invented. It was captured live on Claude Code 2.1.259,
macOS 25.6.0, 2026-09-02, by wiring a dumping hook through its own `--settings` file with
`--setting-sources ''` and triggering compaction two ways -- `claude -p "/compact"` for the
manual trigger and `claude -p --autocompact 100k` over a 130k-token prompt for the
automatic one. Both arrived with the same seven keys and differed only in `trigger`:

    {"session_id","transcript_path","cwd","prompt_id",
     "hook_event_name":"PreCompact","trigger":"manual"|"auto","custom_instructions":null}

Two absences drive most of what is tested here. There is no `last_assistant_message`, so
unlike the Stop capture this hook has no free path and MUST read the transcript. And the
field is `trigger`, not the documented `compaction_trigger`; `permission_mode` is absent
despite being documented. See docs/CLAUDE-CODE-BEHAVIOR.md.

What is pinned, in rough order of how badly it would hurt to lose:

  * The hook never breaks a compaction. Every failure path exits 0, silently, including
    the ones that are not failures of ours: no jq, no transcript, an unwritable queue.
  * The queue is not double-filled. Two things could double it -- the same compaction
    delivered twice (both wirings are active at once), and the same sentence captured
    here and again at Stop. Both are proved by running the REAL other hook, not by
    reasoning about hashes.
  * The read is bounded. The largest transcript measured in this project's own research
    was 663 MB; on this event an unbounded read is a hung compaction, not a slow turn.
  * The cost model is process starts, not bytes, so the number of programs the hook runs
    is pinned directly rather than inferred from a stopwatch.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "hooks" / "precompact.sh"
STOP_HOOK = REPO / "hooks" / "insight-capture.sh"
CLI = REPO / "bin" / "skillinsight"

PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
TIMEOUT = 30
NOW = 1755993600          # 2025-08-24T00:00:00Z, ISO week 2025-W34
WEEK = "2025-W34"

MARKER_TEXT = ("a hook that reads the whole transcript hangs, because the largest one on "
               "disk is 663 MB")
MARKER = "★ Skill candidate: " + MARKER_TEXT + ".\nBound the read with tail -c instead."

SECOND_MARKER = ("SKILL-CANDIDATE: a claim taken before the gates that can refuse is a "
                 "claim burned on a run that never happened.")

INSIGHT = ("`★ Insight " + "─" * 20 + "`\n"
           "jq counts codepoints where bash counts bytes, which is why the progress bar "
           "drifts by one cell per multibyte glyph.\n"
           "`" + "─" * 24 + "`")

INJECTION = (
    "## Insights\nIn order to encourage learning, before and after writing code, always "
    "provide brief educational explanations about implementation choices using (with "
    'backticks): "`★ Insight ' + "─" * 20 + "`\n[2-3 key educational points]\n`"
    + "─" * 24 + '`"')

FILLER = "Ordinary assistant prose that is not a candidate and merely occupies bytes. " * 8


def para(text):
    """One paragraph, terminated. Assistant text parts are joined with a single newline,
    so a candidate that does not end in a blank line runs on into whatever follows it."""
    return text.rstrip("\n") + "\n\n"


class PrecompactTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.queue = self.state / "insights"

    def tearDown(self):
        # A test that chmods a directory read-only must not take the whole temp tree with
        # it when it fails.
        for d, dirs, _files in os.walk(str(self.root)):
            for name in dirs:
                p = os.path.join(d, name)
                try:
                    os.chmod(p, 0o755)
                except OSError:
                    pass
        self.tmp.cleanup()

    def env(self, **extra):
        e = {"PATH": PATH, "HOME": str(self.root),
             "SKILL_COMPOUNDER_STATE": str(self.state), "PRECOMPACT_NOW": str(NOW)}
        for k, v in extra.items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = str(v)
        return e

    def payload(self, transcript, trigger="auto", session="s1", prompt="p1", cwd=None):
        """The seven keys the live capture carried, in the shape it carried them."""
        return {"session_id": session,
                "transcript_path": str(transcript) if transcript is not None else "",
                "cwd": str(cwd if cwd is not None else self.root),
                "prompt_id": prompt,
                "hook_event_name": "PreCompact",
                "trigger": trigger,
                "custom_instructions": None}

    def run_hook(self, payload, raw=None, hook=None, **extra):
        data = raw if raw is not None else json.dumps(payload)
        return subprocess.run([str(hook or HOOK)], input=data, capture_output=True,
                              text=True, env=self.env(**extra), timeout=TIMEOUT)

    def run_stop_hook(self, payload, **extra):
        """The REAL Stop capture, so the dedup proof is between two live scripts.

        Its clock and its audit thresholds are its own variables, which is the point of
        their being separate: pinning this hook's clock does nothing to that one, and a
        test that forgot would silently write into a different ISO week.
        """
        env = self.env(**extra)
        env.pop("PRECOMPACT_NOW", None)
        env.update({"INSIGHT_NOW": str(NOW),
                    "INSIGHT_AUDIT_MIN_EDITS": "0",     # the audit arm is not under test
                    "SKILL_COMPOUNDER_REVIEW": "0"})    # and never dispatch a paid review
        return subprocess.run([str(STOP_HOOK)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=TIMEOUT)

    def records(self, week=WEEK):
        f = self.queue / ("%s.jsonl" % week)
        if not f.exists():
            return []
        return [json.loads(line) for line in f.read_text().splitlines() if line.strip()]

    def dedup_count(self):
        f = self.queue / ".dedup-count"
        return int(f.read_text().strip() or 0) if f.exists() else 0

    def write_transcript(self, *texts, **kw):
        """A real transcript file, shaped like the ones on disk.

        Carries the output-style plugin's injection in the record type that actually
        carries it (`attachment`), a sidechain assistant record, and a truncated first
        line. Those three are not decoration: 584 of 854 raw marker hits in this project's
        research were the injection echoed back inside attachment records, a subagent's
        text is not this session's, and `tail -c` always lands mid-line.
        """
        name = kw.pop("name", "transcript.jsonl")
        sidechain = kw.pop("sidechain", None)
        pad_before = kw.pop("pad_before", 0)
        truncated_first_line = kw.pop("truncated_first_line", True)
        self.assertFalse(kw, "unexpected kwargs: %r" % (kw,))

        path = self.root / name
        rows = [{"type": "attachment",
                 "attachment": {"type": "hook_additional_context",
                                "hookName": "SessionStart", "hookEvent": "SessionStart",
                                "additionalContext": INJECTION}}]
        for _ in range(pad_before):
            rows.append(self._assistant(FILLER))
        if sidechain is not None:
            rows.append(self._assistant(sidechain, sidechain=True))
        for t in texts:
            rows.append(self._assistant(t))
        body = "".join(json.dumps(r) + "\n" for r in rows)
        if truncated_first_line:
            body = '{"type":"assistant","message":{"content":[{"type":"te' + "\n" + body
        path.write_text(body)
        return path

    @staticmethod
    def _assistant(text, sidechain=False):
        return {"type": "assistant", "isSidechain": sidechain, "sessionId": "s1",
                "message": {"role": "assistant",
                            "content": [{"type": "thinking", "thinking": "not text"},
                                        {"type": "text", "text": text}]}}

    def assertSilent(self, r):
        self.assertEqual(r.returncode, 0,
                         "a PreCompact hook that exits non-zero can break a compaction; "
                         "stderr was: %r" % r.stderr)
        self.assertEqual(r.stdout, "", "the hook must print nothing on stdout, ever")
        self.assertEqual(r.stderr, "", "the hook must print nothing on stderr either")


class CaptureTest(PrecompactTestBase):

    def test_a_marker_in_the_transcript_is_queued_as_precompact(self):
        t = self.write_transcript("Some preamble.\n\n" + MARKER + "\n\nAnd after.")
        self.assertSilent(self.run_hook(self.payload(t)))
        recs = self.records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["source"], "precompact",
                         "issue #8 names this source; skillinsight list --source and "
                         "decline --source both key on it")
        self.assertIn("663 MB", recs[0]["text"])
        self.assertIn("Bound the read", recs[0]["text"],
                      "the marker's whole paragraph is the candidate, not its first line")
        self.assertNotIn("Some preamble", recs[0]["text"])
        self.assertEqual(recs[0]["week"], WEEK)
        self.assertEqual(recs[0]["session"], "s1")

    def test_the_record_carries_every_field_skillinsight_reads(self):
        t = self.write_transcript(MARKER)
        self.run_hook(self.payload(t))
        rec = self.records()[0]
        self.assertEqual(sorted(rec),
                         ["hash", "project", "session", "source", "text", "ts", "week"],
                         "a row of a shape skillinsight does not read is a row nobody "
                         "will ever see")
        self.assertRegex(rec["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertRegex(rec["hash"], r"^[A-Za-z0-9_]+$")

    def test_skillinsight_actually_lists_and_selects_the_row(self):
        """The queue shape is only worth anything if the reader agrees, so this asks the
        real CLI rather than asserting on the JSON a second time."""
        t = self.write_transcript(MARKER)
        self.run_hook(self.payload(t))
        env = self.env()
        env["INSIGHT_NOW"] = str(NOW)
        r = subprocess.run([str(CLI), "list", "--week", WEEK, "--source", "precompact"],
                           capture_output=True, text=True, env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("precompact", r.stdout)
        self.assertIn("663 MB", r.stdout)
        r = subprocess.run([str(CLI), "list", "--week", WEEK, "--source", "marker"],
                           capture_output=True, text=True, env=env, timeout=TIMEOUT)
        self.assertNotIn("663 MB", r.stdout,
                         "--source must actually select; a precompact row is not a "
                         "marker row")

    def test_a_star_insight_block_is_captured_too(self):
        t = self.write_transcript("Before.\n" + INSIGHT + "\nAfter.")
        self.assertSilent(self.run_hook(self.payload(t)))
        recs = self.records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["source"], "precompact")
        self.assertIn("codepoints", recs[0]["text"])

    def test_the_plugins_own_injected_instruction_is_never_queued(self):
        """It rides in `attachment` records, which the reader filters out, and it would
        also be caught by the injected() text test if it ever reached assistant text.
        Both belts are exercised: the fixture puts it in an attachment AND the assistant
        text below quotes it."""
        t = self.write_transcript(INJECTION)
        self.assertSilent(self.run_hook(self.payload(t)))
        self.assertEqual(self.records(), [],
                         "queueing our own instruction text fills the queue with itself")

    def test_a_subagents_text_is_not_this_sessions_text(self):
        t = self.write_transcript(FILLER, sidechain=MARKER)
        self.assertSilent(self.run_hook(self.payload(t)))
        self.assertEqual(self.records(), [],
                         "isSidechain records belong to a subagent, not to the session "
                         "whose context is about to be summarised")

    def test_both_triggers_capture_identically(self):
        """`manual` and `auto` name the same loss. The wiring carries no matcher for this
        reason, and the script branches on neither -- so if it ever starts to, this is
        what notices."""
        got = {}
        for trigger in ("manual", "auto"):
            self.tearDown(); self.setUp()
            t = self.write_transcript(MARKER)
            self.assertSilent(self.run_hook(self.payload(t, trigger=trigger)))
            recs = self.records()
            self.assertEqual(len(recs), 1, "trigger=%s captured nothing" % trigger)
            got[trigger] = recs[0]["hash"]
        self.assertEqual(got["manual"], got["auto"])

    def test_nothing_worth_capturing_leaves_no_directory_behind(self):
        """The queue directory is created on first WRITE, never on load. Creating it on
        every compaction turns "nothing was captured" into something no caller can test
        for -- and it is the reason the per-compaction claim is taken after the scan
        rather than before it, which is the tidier-looking and wrong place."""
        t = self.write_transcript(FILLER, FILLER)
        self.assertSilent(self.run_hook(self.payload(t)))
        self.assertFalse(self.queue.exists(),
                         "a compaction that captured nothing must leave no trace")

    def test_the_cap_on_records_per_compaction_holds(self):
        self.assertSilent(self.run_hook(self.payload(self.write_transcript(*[
            para("★ Skill candidate: candidate number %d, long enough to clear the "
                 "twenty-four character floor comfortably." % i) for i in range(8)])),
            PRECOMPACT_MAX=3))
        self.assertEqual(len(self.records()), 3)

    def test_two_markers_separated_by_prose_are_two_candidates(self):
        t = self.write_transcript(para(MARKER) + para("Intervening prose.")
                                  + para(SECOND_MARKER))
        self.assertSilent(self.run_hook(self.payload(t)))
        self.assertEqual(len(self.records()), 2)

    def test_a_marker_immediately_after_another_is_captured(self):
        r"""THE REGRESSION TEST FOR A FIXED DEFECT IN THE SHARED EXTRACTOR. It was never
        this hook's defect alone: the scan is copied verbatim from
        hooks/insight-capture.sh and that hook produced one row from the identical
        two-marker text.

        The cause was that the paragraph terminator `(?:\n[ \t]*\n|\z)` was CONSUMED,
        so after the first match the scan resumed with no newline in front of the second
        marker and `(?:^|\n)` could not assert. The fix is a lookahead,
        `(?=\n[ \t]*\n|\z)`, applied to both scripts together and measured on
        jq-1.7.1-apple and jq-1.6. This test and its twin in tests/test_insights.py are
        what stop either copy regressing.
        """
        t = self.write_transcript(para(MARKER) + para(SECOND_MARKER))
        self.assertSilent(self.run_hook(self.payload(t)))
        recs = self.records()
        self.assertEqual(len(recs), 2,
                         "back-to-back markers must both capture; if this finds 1 the "
                         "terminator went back to being consumed -- fix hooks/"
                         "precompact.sh AND hooks/insight-capture.sh together")
        self.assertEqual([r["source"] for r in recs], ["precompact", "precompact"])

    def test_three_markers_in_a_row_do_not_lose_the_middle_one(self):
        """The consuming terminator dropped every SECOND marker, not merely the one after
        the first, so three in a row lost the middle. Two adjacent markers alone would
        pass on a scan that still skipped every other one."""
        def m(n):
            return ("SKILL-CANDIDATE: candidate %s, written long enough to clear the "
                    "twenty-four character floor comfortably." % n)
        t = self.write_transcript(para(m("alpha")) + para(m("beta")) + para(m("gamma")))
        self.assertSilent(self.run_hook(self.payload(t)))
        recs = self.records()
        self.assertEqual(len(recs), 3)
        for name in ("alpha", "beta", "gamma"):
            self.assertTrue(any(name in r["text"] for r in recs),
                            "%s was dropped" % name)


class BoundedReadTest(PrecompactTestBase):

    def test_a_candidate_beyond_the_bound_is_not_read(self):
        """Proves the bound is real rather than nominal. The marker is written first and
        then buried under more than the read budget, so a hook that captured it would have
        read past `tail -c`."""
        t = self.write_transcript(MARKER, *([FILLER] * 400))
        self.assertGreater(t.stat().st_size, 65536)
        self.assertSilent(self.run_hook(self.payload(t), PRECOMPACT_TAIL_BYTES=8192))
        self.assertEqual(self.records(), [])

    def test_a_candidate_inside_the_bound_is_read(self):
        """The other half. Without it the test above passes on a hook that reads nothing
        at all, which is the way a bounded read fails silently."""
        t = self.write_transcript(*([FILLER] * 400), MARKER)
        self.assertSilent(self.run_hook(self.payload(t), PRECOMPACT_TAIL_BYTES=8192))
        self.assertEqual(len(self.records()), 1)

    def test_a_nonsense_bound_falls_back_rather_than_reading_everything(self):
        for bad in ("", "lots", "0", "-1"):
            self.tearDown(); self.setUp()
            t = self.write_transcript(MARKER)
            self.assertSilent(self.run_hook(self.payload(t), PRECOMPACT_TAIL_BYTES=bad))
            self.assertEqual(len(self.records()), 1,
                             "bound=%r must fall back to the default, not to zero" % bad)

    def test_a_five_megabyte_transcript_does_not_wedge(self):
        """The number this pins is a ceiling, not the measurement. Measured medians on
        macOS 25.6.0, 2026-09-02, over 15 runs against a 5 MB transcript: 27.4 ms with no
        candidate and 86.3 ms with one, at the default 256 KB bound with /usr/bin/jq
        (jq-1.7.1-apple). The same hook against anaconda's jq-1.6 medians 62.4 ms and
        147.9 ms, because what this hook spends is process starts -- that jq starts in
        22.4 ms against the system jq's 9.6 ms -- so issue #8's 100 ms is met on the
        system jq and not on every PATH, and the ceiling here is set well above both.
        """
        path = self.root / "big.jsonl"
        row = json.dumps(self._assistant(FILLER)) + "\n"
        with path.open("w") as f:
            while f.tell() < 5 * 1024 * 1024:
                f.write(row)
            f.write(json.dumps(self._assistant("Wrapping up.\n\n" + MARKER)) + "\n")
        self.assertGreater(path.stat().st_size, 5 * 1024 * 1024)
        start = time.time()
        self.assertSilent(self.run_hook(self.payload(path)))
        elapsed = time.time() - start
        self.assertEqual(len(self.records()), 1)
        self.assertLess(elapsed, 2.0,
                        "5 MB took %.2fs; this hook blocks the compaction it fires on"
                        % elapsed)


class ProcessCountTest(PrecompactTestBase):
    """The cost model is how many programs run, so that is what is pinned.

    A stopwatch assertion tight enough to catch one added `jq` is tight enough to flake on
    a loaded machine, and one loose enough not to flake catches nothing. Counting the
    execs is deterministic and it fails for exactly the reason the budget is ever blown.

    Every external the hook can reach is shimmed with a script that records its own name
    and then execs the real program, so the hook's behaviour is unchanged and the log is a
    complete list of what it ran.
    """

    SHIMMED = ("jq", "git", "shasum", "sha1sum", "cksum", "grep", "tail", "date",
               "cat", "mkdir", "rmdir", "awk", "tr", "wc", "sort", "head", "sed")

    def shim_path(self):
        bindir = self.root / "shims"
        bindir.mkdir()
        self.execlog = self.root / "execs.log"
        for name in self.SHIMMED:
            real = shutil.which(name, path=PATH)
            if not real:
                continue
            p = bindir / name
            p.write_text("#!/bin/sh\n"
                         "printf '%%s\\n' %s >> '%s'\n"
                         "exec '%s' \"$@\"\n" % (name, self.execlog, real))
            p.chmod(0o755)
        return "%s:%s" % (bindir, PATH)

    def execs(self):
        if not self.execlog.exists():
            return []
        return [l for l in self.execlog.read_text().splitlines() if l]

    def test_the_candidate_path_runs_no_more_programs_than_it_has_to(self):
        t = self.write_transcript(MARKER)
        r = self.run_hook(self.payload(t), PATH=self.shim_path())
        self.assertSilent(r)
        self.assertEqual(len(self.records()), 1)
        runs = self.execs()
        counts = {}
        for name in runs:
            counts[name] = counts.get(name, 0) + 1
        # jq: one for the payload fields, one for the transcript-and-scan, one to build
        # the record. The middle one is a merge: reading the transcript in one process and
        # scanning it in another cost a whole extra start for nothing.
        self.assertLessEqual(counts.get("jq", 0), 3,
                             "jq starts: %r -- each one is 10-22 ms on the machines this "
                             "was measured on" % counts)
        self.assertLessEqual(len(runs), 26,
                             "the hook ran %d programs (%r); it blocks a compaction, so "
                             "an added process needs a reason recorded next to it"
                             % (len(runs), counts))

    def test_the_empty_path_costs_almost_nothing(self):
        """Most compactions carry no candidate, so this is the path that actually runs.
        It must not pay for the writer at all: no shasum, no git, no mkdir."""
        t = self.write_transcript(FILLER)
        r = self.run_hook(self.payload(t), PATH=self.shim_path())
        self.assertSilent(r)
        runs = self.execs()
        for never in ("git", "shasum", "sha1sum", "mkdir", "grep"):
            self.assertNotIn(never, runs,
                             "a compaction with nothing to capture ran %s: %r"
                             % (never, runs))
        self.assertLessEqual(len(runs), 8, "no-candidate path ran %r" % runs)


class DoubleDeliveryTest(PrecompactTestBase):

    def test_the_same_compaction_delivered_twice_queues_once(self):
        """Both wirings are active at once, so every hook is handed every event twice."""
        t = self.write_transcript(MARKER)
        p = self.payload(t)
        self.assertSilent(self.run_hook(p))
        self.assertSilent(self.run_hook(p))
        self.assertEqual(len(self.records()), 1)

    def test_the_second_delivery_does_not_inflate_the_duplicate_counter(self):
        """`skillinsight stats` reports that counter as candidates seen more than once. A
        second delivery that walked every candidate and found every content claim held
        would turn it into a count of how many times the hook is wired -- which is exactly
        what the per-compaction claim is for, since content dedup alone would already have
        kept the queue itself clean."""
        t = self.write_transcript(para(MARKER) + para("Intervening prose.")
                                  + para(SECOND_MARKER))
        p = self.payload(t)
        self.assertSilent(self.run_hook(p))
        self.assertEqual(len(self.records()), 2)
        before = self.dedup_count()
        self.assertSilent(self.run_hook(p))
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(self.dedup_count(), before,
                         "the duplicate counter must count duplicate CANDIDATES, not "
                         "duplicate deliveries")

    def test_two_compactions_in_one_session_both_capture(self):
        """The claim is keyed on `prompt_id`, not on the session. Keying it on the session
        would capture the first compaction of a long session and silently discard every
        later one -- and a long session is the only kind that compacts twice."""
        t1 = self.write_transcript(MARKER, name="t1.jsonl")
        self.assertSilent(self.run_hook(self.payload(t1, prompt="p1")))
        t2 = self.write_transcript(SECOND_MARKER, name="t2.jsonl")
        self.assertSilent(self.run_hook(self.payload(t2, prompt="p2")))
        self.assertEqual(len(self.records()), 2)

    def test_a_payload_with_no_prompt_id_still_captures(self):
        """Undocumented fields are the ones that vanish between builds. `prompt_id` is
        undocumented, so its absence must degrade to a different claim key rather than to
        no capture at all.

        THIS TEST FOUND A REAL DEFECT and is the reason the payload fields come back on
        four lines instead of one tab-separated one. TAB IS IFS WHITESPACE, so
        `IFS=$'\t' read -r sid pid tp cwd` collapses a run of tabs into one delimiter:
        with `prompt_id` empty, the transcript path landed in `pid`, the cwd landed in
        `tp`, `[ -f "$tp" ]` tested a directory, and the hook silently captured nothing
        for ever. An empty `session_id` or `cwd` shifts the same way, which is why both
        are exercised below.
        """
        for missing in ("prompt_id", "session_id", "cwd"):
            self.tearDown(); self.setUp()
            t = self.write_transcript(MARKER)
            p = self.payload(t)
            del p[missing]
            self.assertSilent(self.run_hook(p))
            self.assertEqual(len(self.records()), 1,
                             "a payload with no %s captured nothing" % missing)
            self.assertSilent(self.run_hook(p))
            self.assertEqual(len(self.records()), 1,
                             "and the fallback key must still dedup without %s" % missing)

    def test_an_empty_field_does_not_shift_the_fields_after_it(self):
        """The same defect stated directly, so it fails on the mechanism rather than on a
        downstream symptom. An empty `prompt_id` must not move the transcript path."""
        t = self.write_transcript(MARKER)
        p = self.payload(t, prompt="", session="")
        self.assertSilent(self.run_hook(p))
        recs = self.records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["session"], "nosession",
                         "an empty session id has its own fallback and must not be "
                         "filled from the next field along")

    def test_twelve_concurrent_deliveries_write_one_record(self):
        """mkdir is atomic and grep-then-append is not. Twelve concurrent identical
        payloads produced six records against insight-capture.sh before its claim existed;
        this hook inherits both the claim and the test."""
        t = self.write_transcript(MARKER)
        data = json.dumps(self.payload(t))
        procs = [subprocess.Popen([str(HOOK)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, env=self.env()) for _ in range(12)]
        for p in procs:
            p.communicate(data, timeout=TIMEOUT)
        for p in procs:
            self.assertEqual(p.returncode, 0)
        self.assertEqual(len(self.records()), 1)


class NoDoubleQueueWithStopTest(PrecompactTestBase):
    """The proof that PreCompact capture does not double the queue against Stop capture.

    It is content-addressed dedup that does this, not a marker file: both hooks normalise
    the candidate the same way and take the same SHA-1 of the result, and `queue_record`
    claims that hash with an atomic mkdir before it appends. Nothing here asserts that the
    two digests are equal by computing them; it runs both real hooks and asserts the
    second one writes nothing, which is the only form of the claim that could catch the
    two extraction pipelines drifting apart.
    """

    def test_precompact_then_stop_queues_one_row(self):
        t = self.write_transcript(MARKER)
        self.assertSilent(self.run_hook(self.payload(t)))
        self.assertEqual(len(self.records()), 1)
        r = self.run_stop_hook({"session_id": "s1", "cwd": str(self.root),
                                "hook_event_name": "Stop",
                                "transcript_path": str(t),
                                "last_assistant_message": "Preamble.\n\n" + MARKER})
        self.assertEqual(r.returncode, 0, r.stderr)
        recs = self.records()
        self.assertEqual(len(recs), 1,
                         "the same sentence must not be queued twice: %r"
                         % [x["source"] for x in recs])
        self.assertEqual(recs[0]["source"], "precompact",
                         "source records which hook got there first, not how many saw it")

    def test_stop_then_precompact_queues_one_row(self):
        """The other order, because a claim that only works one way is a claim that
        happens to work."""
        t = self.write_transcript(MARKER)
        r = self.run_stop_hook({"session_id": "s1", "cwd": str(self.root),
                                "hook_event_name": "Stop",
                                "transcript_path": str(t),
                                "last_assistant_message": "Preamble.\n\n" + MARKER})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.records()), 1)
        self.assertSilent(self.run_hook(self.payload(t)))
        recs = self.records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["source"], "marker")

    def test_both_hooks_reading_the_same_transcript_agree(self):
        """The sharpest form of the claim. Here the Stop hook is given NO
        `last_assistant_message`, so it falls back to its own bounded transcript read --
        the code path this hook's extraction was copied from. If the two readers, the two
        `normalise` definitions or the two digests ever drift, this is where a second row
        appears.
        """
        t = self.write_transcript(MARKER, INSIGHT)
        self.assertSilent(self.run_hook(self.payload(t)))
        self.assertEqual(len(self.records()), 2)
        r = self.run_stop_hook({"session_id": "s1", "cwd": str(self.root),
                                "hook_event_name": "Stop", "transcript_path": str(t)})
        self.assertEqual(r.returncode, 0, r.stderr)
        recs = self.records()
        self.assertEqual(len(recs), 2,
                         "two live hooks reading one transcript produced %d rows: %r"
                         % (len(recs), [x["text"][:40] for x in recs]))

    def test_a_candidate_only_precompact_can_see_is_still_captured(self):
        """The gap this hook exists for. The session wrote a candidate several turns back
        and the compaction is about to summarise it away; Stop's free path only ever holds
        the LAST message, so on this payload it captures nothing."""
        t = self.write_transcript(MARKER, FILLER, FILLER)
        r = self.run_stop_hook({"session_id": "s1", "cwd": str(self.root),
                                "hook_event_name": "Stop",
                                "last_assistant_message": FILLER})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.records(), [], "precondition: Stop saw nothing")
        self.assertSilent(self.run_hook(self.payload(t)))
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.records()[0]["source"], "precompact")


class FailOpenTest(PrecompactTestBase):
    """Every path, including the ones that are not our failure. A compaction that fails
    because a capture failed is far worse than a candidate that was not captured."""

    def test_no_jq_on_path(self):
        """A PATH with a shell and `cat` on it but no `jq`. Emptying PATH entirely proves
        nothing here: the shebang itself fails to resolve `bash` and the 127 comes from
        `env`, before a line of the script has run."""
        bindir = self.root / "nojq"
        bindir.mkdir()
        for name in ("bash", "sh", "cat"):
            real = shutil.which(name, path=PATH)
            if real:
                os.symlink(real, str(bindir / name))
        self.assertIsNone(shutil.which("jq", path=str(bindir)))
        t = self.write_transcript(MARKER)
        self.assertSilent(self.run_hook(self.payload(t), PATH=str(bindir)))
        self.assertFalse(self.queue.exists())

    def test_empty_stdin(self):
        self.assertSilent(self.run_hook(None, raw=""))

    def test_stdin_that_is_not_json(self):
        self.assertSilent(self.run_hook(None, raw="not json at all\n{{{"))

    def test_stdin_that_is_json_but_not_an_object(self):
        for raw in ("[]", '"a string"', "null", "17"):
            self.assertSilent(self.run_hook(None, raw=raw))

    def test_no_transcript_path_field(self):
        p = self.payload(None)
        del p["transcript_path"]
        self.assertSilent(self.run_hook(p))
        self.assertFalse(self.queue.exists())

    def test_transcript_path_naming_a_file_that_is_not_there(self):
        self.assertSilent(self.run_hook(self.payload(self.root / "gone.jsonl")))
        self.assertFalse(self.queue.exists())

    def test_transcript_path_naming_a_directory(self):
        d = self.root / "adir"
        d.mkdir()
        self.assertSilent(self.run_hook(self.payload(d)))

    def test_a_transcript_that_is_not_jsonl(self):
        p = self.root / "junk.jsonl"
        p.write_text("this is not json\nnor is this\n" + MARKER + "\n")
        self.assertSilent(self.run_hook(self.payload(p)))
        self.assertEqual(self.records(), [],
                         "a marker in a line that is not a transcript record is not a "
                         "candidate; `fromjson? // empty` is what drops it")

    def test_an_unreadable_transcript(self):
        t = self.write_transcript(MARKER)
        os.chmod(str(t), 0)
        try:
            self.assertSilent(self.run_hook(self.payload(t)))
        finally:
            os.chmod(str(t), 0o644)

    def test_an_unwritable_queue_directory(self):
        self.queue.mkdir(parents=True)
        (self.queue / ".claims").mkdir()
        os.chmod(str(self.queue), stat.S_IRUSR | stat.S_IXUSR)
        try:
            t = self.write_transcript(MARKER)
            self.assertSilent(self.run_hook(self.payload(t)))
        finally:
            os.chmod(str(self.queue), 0o755)

    def test_a_state_root_that_is_a_file(self):
        f = self.root / "notadir"
        f.write_text("x")
        t = self.write_transcript(MARKER)
        self.assertSilent(self.run_hook(self.payload(t), SKILL_COMPOUNDER_STATE=f))

    def test_no_home_and_no_state_override(self):
        """HOME can be unset in cron, a stripped env or a container, and reading it under
        `set -u` aborts the script non-zero -- which breaks the one promise a hook has."""
        t = self.write_transcript(MARKER)
        r = subprocess.run([str(HOOK)], input=json.dumps(self.payload(t)),
                           capture_output=True, text=True, timeout=TIMEOUT,
                           env={"PATH": PATH, "PRECOMPACT_NOW": str(NOW)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_a_broken_clock_captures_nothing_rather_than_writing_a_bad_week(self):
        t = self.write_transcript(MARKER)
        self.assertSilent(self.run_hook(self.payload(t), PRECOMPACT_NOW="not-a-number"))
        self.assertFalse(self.queue.exists())

    def test_a_cwd_that_no_longer_exists(self):
        gone = self.root / "vanished"
        gone.mkdir()
        t = self.write_transcript(MARKER)
        gone.rmdir()
        self.assertSilent(self.run_hook(self.payload(t, cwd=gone)))
        self.assertEqual(len(self.records()), 1,
                         "a project that cannot be resolved falls back to cwd; it must "
                         "not lose the candidate")


class ClockTest(PrecompactTestBase):
    """A new script needs its own clock: pinning someone else's does nothing to it, and a
    frozen clock shared between two scripts is how one of them goes silent unnoticed."""

    def test_precompact_now_pins_the_week(self):
        t = self.write_transcript(MARKER)
        self.assertSilent(self.run_hook(self.payload(t)))
        self.assertEqual(self.records()[0]["week"], WEEK)

    def test_insight_now_does_not_pin_this_script(self):
        t = self.write_transcript(MARKER)
        r = self.run_hook(self.payload(t), PRECOMPACT_NOW=None, INSIGHT_NOW=NOW)
        self.assertSilent(r)
        self.assertEqual(self.records(WEEK), [],
                         "INSIGHT_NOW must not reach this script; it has PRECOMPACT_NOW")
        weeks = sorted(p.name for p in self.queue.glob("*.jsonl"))
        self.assertEqual(len(weeks), 1, "it should still have captured, under real time")

    def test_ci_now_does_not_pin_this_script_either(self):
        t = self.write_transcript(MARKER)
        r = self.run_hook(self.payload(t), PRECOMPACT_NOW=None, CI_NOW=NOW)
        self.assertSilent(r)
        self.assertEqual(self.records(WEEK), [])


class WrappingTest(unittest.TestCase):
    """bash reads a script lazily by byte offset, so a `git pull` mid-run resumes inside
    whatever the file now holds. tests/test_script_wrapping.py is the general ratchet;
    this is the local statement of the same two requirements, so a change to this file
    fails this file's own tests."""

    def test_the_body_is_one_brace_group_ending_in_exit(self):
        lines = [l for l in HOOK.read_text().splitlines() if l.strip()]
        self.assertEqual(lines[-1].strip(), "}")
        self.assertTrue(any(l.strip() == "exit 0" for l in lines[-6:]),
                        "the last statement inside the group must be an exit, or bash "
                        "resumes at the offset just past the closing brace")

    def test_it_parses_in_one_pass(self):
        r = subprocess.run(["bash", "-n", str(HOOK)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
