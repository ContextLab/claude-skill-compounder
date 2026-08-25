#!/usr/bin/env python3
"""Tests for the `no-silent-stub` seed skill.

No mocks anywhere, which is not an aesthetic choice here: mocking the subject of
a skill about not mocking would refute the skill. Every fixture file is real
Python that runs, every scan is the real script in a subprocess, and every
number reported below was measured in this process.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "no-silent-stub"
SKILL_MD = SKILL_DIR / "SKILL.md"
SCAN = SKILL_DIR / "scripts" / "stub-scan.py"
FIXTURE = REPO / "tests" / "fixtures" / "no-silent-stub"

PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}

# Every taxonomy entry the skill claims, mapped to the fixture file that
# instantiates it and the rule the mechanical scan must fire on it.
TAXONOMY = {
    "stubs/hardcoded_return.py": "constant-stub",
    "stubs/swallowed_exception.py": "swallowed-exception",
    "stubs/credential_fallback.py": "credential-fallback",
    "stubs/services/ranker.py": "mock-outside-tests",
    "stubs/todo_return.py": "marker-return",
    "stubs/self_scoring_eval.py": "self-scoring-eval",
    "stubs/retry_returns_empty.py": "retry-exhaustion-empty",
    "stubs/cache_miss_default.py": "cache-miss-default",
}

# Real silent stubs with no syntactic tell. The scan is expected to miss these,
# and the test pins the miss so the skill's claimed ceiling stays honest.
BEYOND_THE_SCAN = ("hard/unmarked_fallback.py",)

LEGIT = (
    "legit/config_defaults.py",
    "legit/optional_lookup.py",
    "legit/caller_supplied_default.py",
    "legit/import_fallback.py",
    "legit/error_translation.py",
    "legit/abstract_interface.py",
    "legit/retry_then_raise.py",
    "legit/eval_harness_honest.py",
    "legit/tests/test_rate_math.py",
)


def note(message):
    print(message, file=sys.stderr)


class SeedStubTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.tree = self.home / "fixture"
        shutil.copytree(FIXTURE, self.tree)
        self.env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(self.home),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def tearDown(self):
        self.tmp.cleanup()

    # helpers -----------------------------------------------------------------

    def run_python(self, path, *args, cwd=None):
        return subprocess.run([sys.executable, str(path), *args], capture_output=True,
                              text=True, env=self.env, cwd=str(cwd or self.tree))

    def scan(self, *targets):
        """Run the real scan and return (findings, returncode).

        findings: list of (relative path, line, rule, message).
        """
        args = [str(self.tree / t) for t in targets] or [str(self.tree)]
        proc = subprocess.run([sys.executable, str(SCAN), *args], capture_output=True,
                              text=True, env=self.env, cwd=str(self.tree))
        self.assertEqual(proc.stderr, "", proc.stderr)
        findings = []
        for line in proc.stdout.splitlines():
            m = re.match(r"^(?P<path>.+):(?P<line>\d+): (?P<rule>[a-z-]+): (?P<msg>.*)$", line)
            self.assertIsNotNone(m, f"unparseable scan output line: {line!r}")
            findings.append((str(Path(m["path"]).relative_to(self.tree)), int(m["line"]),
                             m["rule"], m["msg"]))
        return findings, proc.returncode

    def flagged_files(self, findings):
        out = {}
        for path, _, rule, _ in findings:
            out.setdefault(path, set()).add(rule)
        return out

    def skill_text(self):
        return SKILL_MD.read_text(encoding="utf-8")

    def frontmatter_and_body(self):
        text = self.skill_text()
        self.assertTrue(text.startswith("---\n"), "SKILL.md must open with frontmatter")
        _, fm, body = text.split("---\n", 2)
        return fm, body

    # 1. the skill file itself ------------------------------------------------

    def test_skill_and_scan_exist_and_are_wired_together(self):
        self.assertTrue(SKILL_MD.is_file(), f"missing {SKILL_MD}")
        self.assertTrue(SCAN.is_file(), f"missing {SCAN}")
        text = self.skill_text()
        self.assertIn("scripts/stub-scan.py", text,
                      "SKILL.md must name the mechanical scan it prescribes")
        self.assertIn("IF IT CANNOT DO THE REAL THING, IT MUST FAIL IN A WAY THE CALLER "
                      "CANNOT MISS.", text, "the Iron Law must be stated verbatim, once")
        self.assertEqual(text.count("IF IT CANNOT DO THE REAL THING"), 1,
                         "the Iron Law is stated once, not repeated")

    def test_frontmatter_is_portable_and_within_limits(self):
        fm, body = self.frontmatter_and_body()
        keys = set(re.findall(r"^([A-Za-z-]+):", fm, re.M))
        self.assertTrue(keys <= PORTABLE_KEYS,
                        f"non-portable frontmatter keys: {sorted(keys - PORTABLE_KEYS)}")
        self.assertIn("name", keys)
        self.assertIn("description", keys)
        self.assertLessEqual(len(fm), 1024, f"frontmatter is {len(fm)} chars, cap is 1024")
        raw = re.search(r"^description: (.*)$", fm, re.M).group(1)
        # The value must be YAML-quoted: an unquoted `: ` inside it makes the whole
        # frontmatter fail to parse and the skill load with no metadata at all. So
        # measure the decoded string, not the quoted source line.
        self.assertEqual(raw[:1], '"',
                         "description must be double-quoted so a colon cannot break the parse")
        desc = json.loads(raw)
        self.assertLessEqual(len(desc), 500, f"description is {len(desc)} chars, cap is 500")
        self.assertTrue(desc.startswith("Use when"),
                        "description must be a pure 'Use when...' trigger clause")
        self.assertIn("Do NOT use for", desc,
                      "the negative scope belongs in the description sentence")
        for exclusion in ("default", "optional", "test double"):
            self.assertIn(exclusion, desc.lower(),
                          f"description must carve out {exclusion!r}")
        lines = len(body.strip().splitlines())
        self.assertLessEqual(lines, 500, f"body is {lines} lines, ceiling is 500")
        note(f"    SKILL.md: frontmatter {len(fm)} chars, description {len(desc)} chars, "
             f"body {lines} lines")

    def test_prose_style(self):
        text = self.skill_text()
        self.assertEqual(text.count("\u2014"), 0, "no em-dashes anywhere in this repo")
        for banned in ("it's worth noting", "leverage", "robust", "seamless", "delve",
                       "comprehensive", "crucial"):
            self.assertNotIn(banned, text.lower(), f"banned word: {banned}")

    def test_skill_names_every_rule_the_scan_implements(self):
        text = self.skill_text()
        for rule in sorted(set(TAXONOMY.values())):
            self.assertIn(rule, text, f"SKILL.md does not name the {rule} rule")

    # 2. trigger precision ----------------------------------------------------

    def parse_trigger_section(self):
        body = self.frontmatter_and_body()[1]
        section = re.search(r"^## Trigger precision\n(.*?)(?=^## )", body, re.M | re.S)
        self.assertIsNotNone(section, "SKILL.md needs a '## Trigger precision' section")
        block = section.group(1)
        must = re.search(r"^### Must fire\n(.*?)(?=^### )", block, re.M | re.S).group(1)
        must_not = re.search(r"^### Must not fire\n(.*)", block, re.M | re.S).group(1)
        bullets = lambda t: [b.strip("- ").strip() for b in t.strip().splitlines()
                             if b.strip().startswith("- ")]
        return bullets(must), bullets(must_not)

    def test_trigger_precision_is_declared_in_the_skill(self):
        must, must_not = self.parse_trigger_section()
        self.assertEqual(len(must), 3, f"need exactly 3 must-fire prompts, got {must}")
        self.assertEqual(len(must_not), 3, f"need exactly 3 must-not prompts, got {must_not}")
        self.assertEqual(len(set(must) & set(must_not)), 0)
        about_defaults = [p for p in must_not if "default" in p.lower()]
        self.assertGreaterEqual(len(about_defaults), 2,
                                "at least two must-not prompts must be about legitimate "
                                f"defaults, got {about_defaults}")
        for prompt in must + must_not:
            self.assertGreater(len(prompt), 30, f"trigger prompt too thin: {prompt!r}")

    # 3. does the mechanical scan actually discriminate? ----------------------

    def test_scan_flags_every_taxonomy_entry_with_the_right_rule(self):
        findings, code = self.scan("stubs")
        self.assertEqual(code, 1, "a directory full of stubs must exit 1")
        flagged = self.flagged_files(findings)
        for path, rule in TAXONOMY.items():
            self.assertIn(path, flagged, f"{path} was not flagged at all")
            self.assertIn(rule, flagged[path],
                          f"{path} flagged as {sorted(flagged[path])}, expected {rule}")

    def test_scan_flags_no_legitimate_file(self):
        findings, code = self.scan("legit")
        self.assertEqual(findings, [], f"false positives on legitimate code: {findings}")
        self.assertEqual(code, 0)

    def test_scan_misses_the_unmarked_fallback_and_that_is_the_measured_ceiling(self):
        findings, code = self.scan("hard")
        self.assertEqual(findings, [], "the hard case is documented as a miss; if the scan "
                                       "now catches it, update the skill's claimed ceiling")
        self.assertEqual(code, 0)
        proc = self.run_python(self.tree / "hard" / "unmarked_fallback.py")
        real, invented = proc.stdout.split()
        self.assertEqual(real, invented,
                         "the point of the hard case: the invented answer is byte-identical "
                         "to the real one")

    def test_discrimination_precision_and_recall(self):
        findings, _ = self.scan()
        flagged = set(self.flagged_files(findings))
        true_positives = flagged & set(TAXONOMY)
        false_positives = flagged & set(LEGIT)
        missed_taxonomy = set(TAXONOMY) - flagged
        missed_hard = set(BEYOND_THE_SCAN) - flagged

        precision = len(true_positives) / len(flagged) if flagged else 0.0
        recall_taxonomy = len(true_positives) / len(TAXONOMY)
        all_true = len(TAXONOMY) + len(BEYOND_THE_SCAN)
        recall_all = len(true_positives) / all_true

        note(f"    fixture: {len(TAXONOMY)} taxonomy stubs + {len(BEYOND_THE_SCAN)} "
             f"unmarked stub + {len(LEGIT)} legitimate files")
        note(f"    flagged {len(flagged)} files, {len(findings)} findings")
        note(f"    precision            = {precision:.2f} "
             f"({len(true_positives)} true / {len(flagged)} flagged)")
        note(f"    recall (taxonomy)    = {recall_taxonomy:.2f} "
             f"({len(true_positives)}/{len(TAXONOMY)})")
        note(f"    recall (all stubs)   = {recall_all:.2f} "
             f"({len(true_positives)}/{all_true}), missing {sorted(missed_hard)}")
        note("    the second recall number is the honest one: an unmarked fallback with no "
             "guard has no syntactic tell, so no grep or AST pass reaches it.")

        self.assertEqual(false_positives, set(), f"false positives: {sorted(false_positives)}")
        self.assertEqual(missed_taxonomy, set(), f"missed: {sorted(missed_taxonomy)}")
        self.assertEqual(precision, 1.0)
        self.assertEqual(recall_taxonomy, 1.0)
        self.assertLess(recall_all, 1.0, "the fixture must keep at least one honest miss")

    def test_scan_reports_a_file_it_cannot_parse_rather_than_skipping_it(self):
        broken = self.tree / "stubs" / "broken.py"
        broken.write_text("def f(:\n    pass\n", encoding="utf-8")
        findings, code = self.scan("stubs/broken.py")
        self.assertEqual(code, 1)
        self.assertEqual([f[2] for f in findings], ["unparseable"])

    def test_scan_usage_error_is_distinguishable_from_a_clean_run(self):
        proc = subprocess.run([sys.executable, str(SCAN)], capture_output=True, text=True,
                              env=self.env, cwd=str(self.tree))
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")

    # 4. is the failure observable after the prescribed fix? ------------------

    def test_prescribed_fix_turns_a_plausible_value_into_a_named_failure(self):
        target = self.tree / "stubs" / "credential_fallback.py"
        self.assertNotIn("FX_API_KEY", self.env,
                         "the fixture must run without the real key")

        before = self.run_python(target)
        self.assertEqual(before.returncode, 0)
        self.assertEqual(before.stdout.strip(), "rate=1.0",
                         "unfixed, the caller receives a legal-looking rate and no warning")

        # Phase 3 rung 1, verbatim from the skill: raise, naming the missing
        # precondition rather than the function.
        prescribed = (
            'raise RuntimeError("fetch_exchange_rate: FX_API_KEY is not set; '
            'cannot fetch a real rate")'
        )
        self.assertIn(prescribed, self.skill_text(),
                      "the skill must show the exact replacement this test applies")
        source = target.read_text(encoding="utf-8")
        fixed = source.replace("        return 1.0", f"        {prescribed}")
        self.assertNotEqual(fixed, source)
        target.write_text(fixed, encoding="utf-8")

        after = self.run_python(target)
        self.assertNotEqual(after.returncode, 0, "the fixed caller must fail, loudly")
        self.assertEqual(after.stdout.strip(), "",
                         "nothing value-shaped may reach stdout after the fix")
        self.assertIn("RuntimeError", after.stderr)
        self.assertIn("FX_API_KEY", after.stderr,
                      "the message must name the missing precondition, not just the function")
        self.assertIn("cannot fetch a real rate", after.stderr)

        findings, code = self.scan("stubs/credential_fallback.py")
        self.assertEqual((findings, code), ([], 0),
                         "the prescribed fix must also clear the mechanical scan")

    # 5. the self-referential case (anthropics/claude-code#54682) -------------

    def test_self_scoring_eval_reports_a_perfect_score_and_the_scan_catches_it(self):
        stub = self.tree / "stubs" / "self_scoring_eval.py"
        proc = self.run_python(stub)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "accuracy: 100.0%",
                         "the eval that scores itself against its own input reports perfect")

        findings, code = self.scan("stubs/self_scoring_eval.py")
        self.assertEqual(code, 1)
        rules = {f[2] for f in findings}
        self.assertEqual(rules, {"self-scoring-eval"})
        messages = " | ".join(f[3] for f in findings)
        self.assertIn("copied from `expected_answer`", messages,
                      "the column copy itself must be named")
        self.assertIn("aliases `expected_answer` as `claude_answer`", messages,
                      "the SQL form from #54682 must be caught too")
        self.assertIn("`is_correct` assigned the passing value", messages)

    def test_the_honest_eval_scores_lower_and_is_not_flagged(self):
        honest = self.tree / "legit" / "eval_harness_honest.py"
        proc = self.run_python(honest)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        score = float(re.search(r"([\d.]+)%", proc.stdout).group(1))
        self.assertLess(score, 100.0,
                        "an honest harness reports the score it measured, which here is "
                        "imperfect; that gap is the whole tell")
        findings, code = self.scan("legit/eval_harness_honest.py")
        self.assertEqual((findings, code), ([], 0))

    # 6. the fixture is real code, not decoration -----------------------------

    def test_every_fixture_file_actually_runs(self):
        runnable = [p for p in sorted(self.tree.rglob("*.py"))
                    if "tests" not in p.relative_to(self.tree).parts]
        self.assertGreaterEqual(len(runnable), len(TAXONOMY) + len(LEGIT) - 1)
        for path in runnable:
            with self.subTest(path=str(path.relative_to(self.tree))):
                proc = self.run_python(path)
                self.assertEqual(proc.returncode, 0,
                                 f"{path.name} did not run cleanly: {proc.stderr}")

    def test_the_deliberate_test_double_lives_on_a_test_path_and_passes(self):
        suite = self.tree / "legit" / "tests" / "test_rate_math.py"
        proc = self.run_python(suite)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OK", proc.stderr)
        findings, code = self.scan("legit/tests")
        self.assertEqual((findings, code), ([], 0),
                         "a project's own deliberate test doubles must not be flagged")

    def test_moving_the_same_double_off_the_test_path_does_flag_it(self):
        suite = (self.tree / "legit" / "tests" / "test_rate_math.py").read_text(encoding="utf-8")
        moved = self.tree / "legit" / "rate_math_runtime.py"
        moved.write_text(suite, encoding="utf-8")
        findings, code = self.scan("legit/rate_math_runtime.py")
        self.assertEqual(code, 1)
        self.assertEqual({f[2] for f in findings}, {"mock-outside-tests"},
                         "identical source, different path: location is the discriminator")


if __name__ == "__main__":
    unittest.main()
