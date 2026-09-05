#!/usr/bin/env python3
"""`scripts/reminder_conversion.py` is the sweep behind issue #30's conversion rate.

The 10.5% the issue opened with was a figure nobody could re-run. The script exists so the
figure is re-derivable, and this test exists so the script keeps deriving it the same way:
its `--selftest` builds a real eight-file fixture on disk (transcripts in the shape Claude
Code writes, a ledger, a nudge log), sweeps it with the real reader, and asserts every
count, including the four that separate a delivery from a mention (a quoted nudge is not a
delivery; an `is_error` Skill result is not a use; `grep -n skillnote` is a mention and not
a run; `--since`/`--until` filter events, not sessions). If a match rule drifts, the
selftest fails and this test reports it.

WHAT IS ASSERTED, AND HOW MUCH IT IS WORTH. Two things. The selftest exits 0 and prints
`selftest: OK` on its last line, which is the whole fixture-driven contract. And `--json`
over an EMPTY projects directory returns a parseable object whose top-level shape a later
reader can join on, so a rename of a key is a failure here rather than a silent zero in a
report. Nothing here touches the real `~/.claude`: the empty run is pointed at temp
directories, and the selftest builds its own.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "reminder_conversion.py")


def run(*args, env=None):
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env, timeout=120,
    )


class SelftestTest(unittest.TestCase):
    def test_selftest_builds_a_real_fixture_and_passes(self):
        r = run("--selftest")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "selftest: OK")

    def test_selftest_passes_under_a_minimal_environment(self):
        # The CI runner has none of what this box has in HOME or on PATH.
        with tempfile.TemporaryDirectory() as home:
            env = {"HOME": home, "PATH": "/usr/bin:/bin"}
            r = run("--selftest", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class JsonShapeTest(unittest.TestCase):
    def run_empty(self):
        with tempfile.TemporaryDirectory() as projects, tempfile.TemporaryDirectory() as state:
            r = run("--projects-dir", projects, "--state-dir", state, "--json")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            return projects, json.loads(r.stdout)

    def test_json_over_an_empty_store_has_the_joinable_shape(self):
        _, doc = self.run_empty()
        # The two subtrees a later reader joins on, and the counts inside them. A key
        # rename fails here rather than turning into a silent zero in a report.
        self.assertEqual(sorted(doc), ["nudge_log", "report"])
        report = doc["report"]
        self.assertEqual(sorted(report),
                         ["cohorts", "corpus", "deliveries", "per_project", "sessions_by_nudge_kind"])
        for cohort in ("all-sessions", "human-driven"):
            c = report["cohorts"][cohort]
            for rate in ("nudge_to_skill", "nudge_to_tier_cli", "nudge_to_any_output"):
                self.assertEqual(sorted(c[rate]), ["d", "n", "pct"], (cohort, rate))
            self.assertIn("nudged_sessions", c)
            self.assertIn("sessions_invoking_skill_compounder", c)
        for key in ("rows", "distinct_ids", "ledger_rows_with_from", "id_join_matched_rows"):
            self.assertIn(key, doc["nudge_log"])

    def test_json_over_an_empty_store_censuses_zero_transcripts(self):
        projects, doc = self.run_empty()
        corpus = doc["report"]["corpus"]
        # The census is derived from the directory it was pointed at, not from ~/.claude.
        self.assertEqual(corpus["projects_dir"], projects)
        self.assertEqual(corpus["transcript_files"], 0)
        self.assertEqual(corpus["nudged_distinct_sessions"], 0)
        for cohort in doc["report"]["cohorts"].values():
            self.assertEqual(cohort["nudge_to_skill"], {"d": 0, "n": 0, "pct": None})


if __name__ == "__main__":
    unittest.main()
