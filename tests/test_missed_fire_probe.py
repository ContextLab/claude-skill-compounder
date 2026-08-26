#!/usr/bin/env python3
"""scripts/probe_missed_fires.py -- the fired / should-have-fired instrument (issue #13).

Real script through subprocess, real files on disk, no mocks. The model call is NEVER
made from here: test_refuses_without_gate is the assertion that it cannot be, and every
other test drives the three quota-free subcommands (--list, --digest, --score) over
fixtures written into a temp dir. A fake `claude` that invented an answer would test the
fake, which is the thing this repo bans mocks to avoid.

`RECORDED_ANSWER` is the VERBATIM result of one real sonnet call made on 2026-08-26
(cli 2.1.245, $0.139, 65s) against a real 20 KB digest of a lab-manual session. It is
replayed through --score against a fixture digest that carries the same quoted line,
so what is pinned is what this script does with an answer the CLI already returned.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROBE = REPO / "scripts" / "probe_missed_fires.py"
PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

SKILL_NAMES = sorted(d.name for d in (REPO / "skills").iterdir() if (d / "SKILL.md").is_file())

RECORDED_QUOTE = ("BASH\tgit commit -q -F - <<'EOF' Reserve PI lunch break, fix registrar "
                  "scraper and 0-member filter Scheduling fixes: - Reserve the PI a free "
                  "15-minute slot in the 11:")

RECORDED_ANSWER = """SKILL: ai-tell-audit
MOMENT: YES
QUOTE: BASH\tgit commit -q -F - <<'EOF' Reserve PI lunch break, fix registrar scraper and 0-member filter Scheduling fixes: - Reserve the PI a free 15-minute slot in the 11:
WHY: The assistant drafted a multi-line commit message body, an artifact the skill's own description names as durable prose that fires the skill.

SKILL: claim-provenance
MOMENT: NO
QUOTE: NONE
WHY: The lint before/after comparison verifies a fresh measurement the assistant just made, not a previously written-down claim being checked or carried forward.

SKILL: contribute-skill
MOMENT: NO
QUOTE: NONE
WHY: No skill was forged, proposed upstream, or evaluated for a PR in this session.

SKILL: destructive-op-preflight
MOMENT: NO
QUOTE: NONE
WHY: The stash block and stale-lock removals were investigated after the fact and confirmed non-destructive (reversible git operations), not a live preflight before an irreversible action.

SKILL: no-silent-stub
MOMENT: NO
QUOTE: NONE
WHY: The assistant explicitly avoided faking results ("mocking is off-limits per your rules") rather than returning an uncomputed or stubbed value.

SKILL: session-handoff
MOMENT: NO
QUOTE: NONE
WHY: No context-loss, compaction, or session-ending moment occurs anywhere in the digest.

SKILL: skill-authoring
MOMENT: NO
QUOTE: NONE
WHY: No SKILL.md frontmatter was written, fixed, or discussed in this session.

SKILL: skill-compounder
MOMENT: NO
QUOTE: NONE
WHY: No skill misfired, was retired, or was evaluated for creation during this ordinary debugging/commit session.

SKILL: stale-artifact-check
MOMENT: NO
QUOTE: NONE
WHY: Each edit produced an observed change in failure count (20→7, then 20→6), so no edit ever appeared to have zero observable effect.
"""


def _rec(rtype, content, **extra):
    base = {"type": rtype, "isSidechain": False, "timestamp": "2026-08-20T10:00:00.000Z",
            "cwd": "/Users/someone/proj", "message": {"role": rtype, "content": content}}
    base.update(extra)
    return json.dumps(base)


def write_transcript(path):
    """A hand-built main-session transcript exercising every line kind the digest
    emits, plus the three things it must drop: a sidechain record, a slash-command
    echo, and a Skill invocation whose result came back is_error."""
    lines = [
        _rec("user", "<command-message>init</command-message>\n<command-name>/init</command-name>"),
        _rec("user", "please draft a comment on the issue explaining the regression"),
        _rec("assistant", [{"type": "text", "text": "I'll read the file first."},
                           {"type": "tool_use", "id": "t1", "name": "Bash",
                            "input": {"command": "grep -n regression src/*.py"}}]),
        _rec("user", [{"type": "tool_result", "tool_use_id": "t1",
                       "content": "src/a.py:12: # regression here"}]),
        _rec("assistant", [{"type": "tool_use", "id": "t2", "name": "Edit",
                            "input": {"file_path": "/x/a.py", "old_string": "return None",
                                      "new_string": "return compute()"}}]),
        _rec("assistant", [{"type": "tool_use", "id": "t3", "name": "Skill",
                            "input": {"skill": "stale-artifact-check"}}]),
        _rec("user", [{"type": "tool_result", "tool_use_id": "t3", "content": "ok"}]),
        _rec("assistant", [{"type": "tool_use", "id": "t4", "name": "Skill",
                            "input": {"skill": "session-handoff"}}]),
        _rec("user", [{"type": "tool_result", "tool_use_id": "t4", "is_error": True,
                       "content": "<tool_use_error>Unknown skill: session-handoff</tool_use_error>"}]),
        _rec("assistant", [{"type": "tool_use", "id": "t5", "name": "Skill",
                            "input": {"skill": "skill-compounder:ai-tell-audit"}}]),
        _rec("assistant", [{"type": "tool_use", "id": "t6", "name": "Task",
                            "input": {"description": "Audit the docs"}}]),
        # A sidechain (subagent) record with a Skill use: must not count and not appear.
        _rec("assistant", [{"type": "tool_use", "id": "t7", "name": "Skill",
                            "input": {"skill": "no-silent-stub"}}], isSidechain=True),
        "this line is not json and must be skipped",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args, env_extra=None, cwd=None, timeout=120):
    env = {"PATH": PATH, "HOME": cwd or tempfile.gettempdir(), "LANG": "C.UTF-8"}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(PROBE)] + args, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, env=env, timeout=timeout)


class GateTest(unittest.TestCase):
    def test_refuses_without_gate(self):
        """The default mode spends quota. Without SKILL_MISSED_FIRE_PROBE=1 it must exit
        before touching anything, whatever else the environment says."""
        with tempfile.TemporaryDirectory() as tmp:
            env = {"SKILL_MISSED_FIRE_PROBE_PROJECTS": tmp, "SKILL_COMPOUNDER_STATE": tmp,
                   "SKILL_ROUTING_PROBE": "1", "SKILL_SYNTHETIC_PROBE": "1"}
            p = run(["--n", "1"], env_extra=env, cwd=tmp)
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("SKILL_MISSED_FIRE_PROBE", p.stderr)
        self.assertEqual(p.stdout, "")

    def test_gated_run_with_no_transcripts_spends_nothing(self):
        """With the gate on but an empty projects dir there is nothing to audit; it must
        say so and exit non-zero without invoking any CLI (none is on PATH here)."""
        with tempfile.TemporaryDirectory() as tmp:
            env = {"SKILL_MISSED_FIRE_PROBE": "1", "SKILL_MISSED_FIRE_PROBE_PROJECTS": tmp,
                   "SKILL_COMPOUNDER_STATE": tmp}
            p = run(["--n", "1"], env_extra=env, cwd=tmp)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("no transcripts", p.stderr)


class DigestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.transcript = Path(self.tmp) / "-Users-someone-proj" / "abc.jsonl"
        self.transcript.parent.mkdir()
        write_transcript(self.transcript)

    def test_digest_lines_and_fired_count(self):
        p = run(["--digest", str(self.transcript)], cwd=self.tmp)
        self.assertEqual(p.returncode, 0, p.stderr)
        d = p.stdout
        self.assertIn("USER\tplease draft a comment on the issue", d)
        self.assertNotIn("<command-message>", d)
        self.assertIn("BASH\tgrep -n regression src/*.py", d)
        self.assertIn("RESULT\tsrc/a.py:12: # regression here", d)
        self.assertIn("EDIT\t/x/a.py\treturn None\treturn compute()", d)
        self.assertIn("SKILL\tstale-artifact-check", d)
        self.assertIn("SKILL\tsession-handoff", d)  # shown; just not counted
        self.assertIn("RESULT\tERROR <tool_use_error>Unknown skill", d)
        self.assertIn("SUBAGENT\tAudit the docs", d)
        self.assertNotIn("no-silent-stub", d)  # sidechain excluded
        # fired: the errored Skill is an attempt, the plugin-prefixed one counts bare,
        # the sidechain one is not this session's.
        fired = p.stderr
        self.assertIn("'stale-artifact-check': 1", fired)
        self.assertIn("'ai-tell-audit': 1", fired)
        self.assertNotIn("session-handoff", fired)
        self.assertNotIn("no-silent-stub", fired)

    def test_list_skips_harness_dirs_and_small_files(self):
        big = Path(self.tmp) / "-Users-someone-big" / "big.jsonl"
        big.parent.mkdir()
        big.write_text("x" * 70_000)
        probe = Path(self.tmp) / "-private-tmp-routing-probe-abc" / "p.jsonl"
        probe.parent.mkdir()
        probe.write_text("x" * 70_000)
        p = run(["--list"], env_extra={"SKILL_MISSED_FIRE_PROBE_PROJECTS": self.tmp}, cwd=self.tmp)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(str(big), p.stdout)
        self.assertNotIn(str(probe), p.stdout)
        self.assertNotIn(str(self.transcript), p.stdout)  # under 60 KB

    def test_bound_samples_the_whole_session(self):
        """Over budget, the digest is evenly spaced windows with visible elisions, so a
        moment in the middle of a long session is not hidden by construction."""
        lines = []
        for i in range(3000):
            lines.append(_rec("assistant", [{"type": "text", "text": "marker-%04d " % i + "x" * 60}]))
        self.transcript.write_text("\n".join(lines) + "\n")
        env = {"SKILL_MISSED_FIRE_PROBE_HEAD": "3000", "SKILL_MISSED_FIRE_PROBE_TAIL": "7000",
               "SKILL_MISSED_FIRE_PROBE_WINDOWS": "5"}
        p = run(["--digest", str(self.transcript)], env_extra=env, cwd=self.tmp)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("marker-0000", p.stdout)
        self.assertIn("marker-2999", p.stdout)
        self.assertIn("marker-15", p.stdout)  # the middle window lands around 1500
        self.assertEqual(p.stdout.count("bytes of this session elided"), 4)
        self.assertLess(len(p.stdout), 12_000)


class ScoreTest(unittest.TestCase):
    """--score is the whole provenance rule: a YES is counted only if its quote is in
    the digest, verbatim."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.digest = Path(self.tmp) / "digest.txt"
        self.answer = Path(self.tmp) / "answer.txt"

    def _score(self, digest, answer):
        self.digest.write_text(digest, encoding="utf-8")
        self.answer.write_text(answer, encoding="utf-8")
        p = run(["--score", "--digest-file", str(self.digest), "--answer-file", str(self.answer)],
                cwd=self.tmp)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_recorded_real_answer_replays(self):
        digest = ("USER\tfix the scheduler\nSAY\tRunning lint.\n" + RECORDED_QUOTE +
                  "\nRESULT\t[main abc123] Reserve PI lunch break\n")
        rows = self._score(digest, RECORDED_ANSWER)
        self.assertEqual(sorted(rows), SKILL_NAMES)
        self.assertEqual(rows["ai-tell-audit"]["status"], "VERIFIED")
        self.assertEqual(rows["ai-tell-audit"]["quote"], RECORDED_QUOTE)
        for name in SKILL_NAMES:
            if name != "ai-tell-audit":
                self.assertEqual(rows[name]["status"], "NO", name)
        # No transcript was given, so nothing fired.
        self.assertTrue(all(r["fired"] == 0 for r in rows.values()))

    def test_paraphrased_quote_is_unverified(self):
        digest = "USER\tplease draft a comment on the issue explaining the regression\n"
        answer = ("SKILL: ai-tell-audit\nMOMENT: YES\n"
                  "QUOTE: USER\tthe user asked for a comment on the issue about the regression\n"
                  "WHY: paraphrased.\n")
        rows = self._score(digest, answer)
        self.assertEqual(rows["ai-tell-audit"]["status"], "UNVERIFIED")

    def test_short_quote_is_unverified(self):
        digest = "USER\tplease draft a comment on the issue explaining the regression\n"
        answer = "SKILL: ai-tell-audit\nMOMENT: YES\nQUOTE: draft a comment\nWHY: too short.\n"
        rows = self._score(digest, answer)
        self.assertEqual(rows["ai-tell-audit"]["status"], "UNVERIFIED")

    def test_yes_with_no_quote_is_unverified_and_missing_skill_is_unparsed(self):
        digest = "USER\tplease draft a comment on the issue explaining the regression\n"
        answer = "SKILL: ai-tell-audit\nMOMENT: YES\nQUOTE: NONE\nWHY: no quote.\n"
        rows = self._score(digest, answer)
        self.assertEqual(rows["ai-tell-audit"]["status"], "UNVERIFIED")
        self.assertEqual(rows["stale-artifact-check"]["status"], "UNPARSED")

    def test_whitespace_differences_do_not_break_a_true_quote(self):
        digest = "USER\tplease   draft a comment\n on the issue explaining the regression\n"
        answer = ("SKILL: ai-tell-audit\nMOMENT: YES\n"
                  "QUOTE: `USER please draft a comment on the issue explaining the regression`\n"
                  "WHY: fine.\n")
        rows = self._score(digest, answer)
        self.assertEqual(rows["ai-tell-audit"]["status"], "VERIFIED")

    def test_score_counts_fires_from_a_transcript(self):
        t = Path(self.tmp) / "t.jsonl"
        write_transcript(t)
        self.digest.write_text("SKILL\tstale-artifact-check\n")
        self.answer.write_text("SKILL: stale-artifact-check\nMOMENT: YES\n"
                               "QUOTE: SKILL\tstale-artifact-check\nWHY: it fired.\n")
        p = run(["--score", "--digest-file", str(self.digest), "--answer-file", str(self.answer),
                 "--transcript", str(t)], cwd=self.tmp)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = json.loads(p.stdout)
        self.assertEqual(rows["stale-artifact-check"]["fired"], 1)
        self.assertEqual(rows["session-handoff"]["fired"], 0)  # errored attempt
        self.assertEqual(rows["ai-tell-audit"]["fired"], 1)  # plugin-prefixed spelling
        # A quoted SKILL line is a verbatim line of the digest and clears MIN_QUOTE.
        self.assertEqual(rows["stale-artifact-check"]["status"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
