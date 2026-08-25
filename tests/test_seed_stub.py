#!/usr/bin/env python3
"""Tests for the `no-silent-stub` seed skill.

No mocks anywhere, which is not an aesthetic choice here: mocking the subject of
a skill about not mocking would refute the skill. Every fixture file is real
Python that runs, every scan is the real script in a subprocess, every diff test
runs against a real git repository, and the false-positive budget is measured
against the real standard library, which is code neither this skill nor its
fixtures ever saw.
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

# Taxonomy entries the triage mode is measured strong enough to report.
TAXONOMY_TRIAGE = {
    "stubs/swallowed_exception.py": "swallowed-exception",
    "stubs/credential_fallback.py": "credential-fallback",
    "stubs/services/ranker.py": "mock-outside-tests",
    "stubs/todo_return.py": "marker-return",
    "stubs/self_scoring_eval.py": "self-scoring-eval",
    "stubs/retry_returns_empty.py": "retry-exhaustion-empty",
    "stubs/cache_miss_default.py": "cache-miss-default",
}
# Suppressed in triage because it scored 0 of 6 on third-party code. It runs
# under --diff, where the shapes it confuses with stubs are not present.
TAXONOMY_DIFF_ONLY = {"stubs/hardcoded_return.py": "constant-stub"}
TAXONOMY = {**TAXONOMY_TRIAGE, **TAXONOMY_DIFF_ONLY}

# Real silent stubs with no syntactic tell. The scan is expected to miss these,
# and the tests pin the misses so the skill's claimed ceiling stays honest.
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

# Standard-library modules present in any CPython 3. The scan must stay quiet
# on all of them: this is the regression guard on precision, and it fails if
# anyone loosens a rule back toward the version that emitted 411 findings over
# 308 kLOC of third-party code.
STDLIB_MODULES = ("json", "csv.py", "argparse.py", "logging", "email", "http", "xml", "ast.py")
STDLIB_BUDGET_PER_KLOC = 0.5


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
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
            "GIT_CONFIG_GLOBAL": str(self.home / "gitconfig"),
        }

    def tearDown(self):
        self.tmp.cleanup()

    # helpers -----------------------------------------------------------------

    def run_python(self, path, *args, cwd=None):
        return subprocess.run([sys.executable, str(path), *args], capture_output=True,
                              text=True, env=self.env, cwd=str(cwd or self.tree))

    def run_scan(self, *args, cwd=None):
        proc = subprocess.run([sys.executable, str(SCAN), *args], capture_output=True,
                              text=True, env=self.env, cwd=str(cwd or self.tree))
        # Without this, a missing script yields empty stdout, which every
        # "assert no findings" test below would read as a clean bill of health.
        # That is the defect this whole skill is about, so it must not live here.
        self.assertNotIn("can't open file", proc.stderr,
                         f"the scanner did not run at all: {proc.stderr}")
        self.assertNotIn("Traceback", proc.stderr, proc.stderr)
        return proc

    def parse(self, stdout, root=None):
        findings = []
        for line in stdout.splitlines():
            m = re.match(r"^(?P<path>.+):(?P<line>\d+): (?P<rule>[a-z-]+): (?P<msg>.*)$", line)
            self.assertIsNotNone(m, f"unparseable scan output line: {line!r}")
            path = Path(m["path"])
            if root and path.is_absolute():
                path = path.relative_to(root)
            findings.append((str(path), int(m["line"]), m["rule"], m["msg"]))
        return findings

    def scan(self, *targets):
        """Triage mode over fixture paths. Returns (findings, returncode)."""
        args = [str(self.tree / t) for t in targets] or [str(self.tree)]
        proc = self.run_scan(*args)
        self.assertIn("triage mode", proc.stderr,
                      "triage mode must state what it is worth on its own stderr")
        return self.parse(proc.stdout, self.tree), proc.returncode

    def git_repo(self, files, committed=None, stage=True):
        """A real git repo with `committed` at HEAD and `files` added on top."""
        root = self.home / "work"
        root.mkdir()
        run = lambda *a: subprocess.run(["git", *a], cwd=str(root), env=self.env,
                                        capture_output=True, text=True, check=True)
        run("init", "-q", ".")
        for rel, text in (committed or {"README.md": "base\n"}).items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        run("add", "-A")
        run("commit", "-qm", "base")
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        if stage:
            run("add", "-A")
        return root

    def scan_diff(self, root, *extra):
        proc = self.run_scan("--diff", *extra, cwd=root)
        self.assertNotIn("Traceback", proc.stderr, proc.stderr)
        return self.parse(proc.stdout), proc.returncode

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
        self.assertIn("skills/no-silent-stub/scripts/stub-scan.py", text,
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

    def test_skill_names_every_rule_and_states_what_the_scan_is_worth(self):
        text = self.skill_text()
        for rule in sorted(set(TAXONOMY.values())):
            self.assertTrue(rule in text, f"SKILL.md does not name the {rule} rule")
        self.assertTrue("What this scan is worth" in text,
                        "the skill must publish the scan's measured precision")
        self.assertTrue("308,000" in text,
                        "state the size of the corpus the numbers came from")

    def test_skill_documents_the_rungs_the_scanner_assumes(self):
        text = self.skill_text()
        self.assertTrue("Log at error level and continue" in text,
                      "the scanner goes quiet on any logging call, so the ladder must "
                      "have a rung for log-and-continue and say when it is correct")
        self.assertTrue("superpowers:verification-before-completion" in text,
                      "Phase 5 must defer to the skill that owns the completion-claim "
                      "trigger rather than competing with it")
        self.assertTrue("cold-start" in text.lower(),
                      "the skill must name a case where the answer is not 'raise'")

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

    # 3. precision, measured on code this repo did not write ------------------

    def test_false_positive_budget_on_the_standard_library(self):
        stdlib = Path(json.__file__).resolve().parent.parent
        targets = [stdlib / m for m in STDLIB_MODULES if (stdlib / m).exists()]
        self.assertGreaterEqual(len(targets), 5, f"could not locate stdlib under {stdlib}")
        loc = 0
        for t in targets:
            files = [t] if t.is_file() else list(t.rglob("*.py"))
            for f in files:
                try:
                    loc += len(f.read_text(encoding="utf-8").splitlines())
                except (OSError, UnicodeDecodeError):
                    pass
        proc = self.run_scan(*[str(t) for t in targets])
        findings = [f for f in self.parse(proc.stdout) if f[2] != "unscanned-language"]
        density = len(findings) / (loc / 1000.0)
        note(f"    stdlib false-positive budget: {len(findings)} findings over {loc} lines "
             f"= {density:.3f}/kLOC (budget {STDLIB_BUDGET_PER_KLOC}/kLOC)")
        for f in findings:
            note(f"      {f[0]}:{f[1]}: {f[2]}")
        self.assertLess(density, STDLIB_BUDGET_PER_KLOC,
                        "the scan got noisy on code nobody here wrote; tighten the rule "
                        "that fired, do not raise this budget")

    def test_triage_mode_flags_the_taxonomy_entries_it_claims(self):
        findings, code = self.scan("stubs")
        self.assertEqual(code, 1)
        flagged = {}
        for path, _, rule, _ in findings:
            flagged.setdefault(path, set()).add(rule)
        for path, rule in TAXONOMY_TRIAGE.items():
            self.assertIn(path, flagged, f"{path} was not flagged at all")
            self.assertIn(rule, flagged[path],
                          f"{path} flagged as {sorted(flagged[path])}, expected {rule}")

    def test_triage_mode_flags_no_legitimate_file(self):
        findings, code = self.scan("legit")
        self.assertEqual(findings, [], f"false positives on legitimate code: {findings}")
        self.assertEqual(code, 0)

    def test_constant_stub_is_suppressed_in_triage_and_live_on_a_diff(self):
        findings, _ = self.scan("stubs")
        self.assertNotIn("constant-stub", {f[2] for f in findings},
                         "constant-stub scored 0 of 6 on third-party code and must not "
                         "fire in triage mode")
        source = (self.tree / "stubs" / "hardcoded_return.py").read_text(encoding="utf-8")
        root = self.git_repo({"billing.py": source})
        findings, code = self.scan_diff(root)
        self.assertEqual(code, 1)
        self.assertIn("constant-stub", {f[2] for f in findings},
                      "the same file must be flagged when it is what this change added")

    def test_measured_discrimination_over_the_fixture(self):
        findings, _ = self.scan()
        flagged = {f[0] for f in findings}
        true_positives = flagged & set(TAXONOMY_TRIAGE)
        false_positives = flagged & set(LEGIT)
        precision = len(true_positives) / len(flagged) if flagged else 0.0
        recall_triage = len(true_positives) / len(TAXONOMY_TRIAGE)
        all_true = len(TAXONOMY) + len(BEYOND_THE_SCAN)
        note(f"    fixture, triage mode: precision {precision:.2f} "
             f"({len(true_positives)}/{len(flagged)} flagged files true), "
             f"recall {recall_triage:.2f} over the {len(TAXONOMY_TRIAGE)} triage shapes, "
             f"{len(true_positives)}/{all_true} over every true stub present")
        note("    the last number is the honest one: constant-stub is diff-only and an "
             "unmarked fallback has no syntactic tell at all.")
        self.assertEqual(false_positives, set(), f"false positives: {sorted(false_positives)}")
        self.assertEqual(precision, 1.0)
        self.assertEqual(recall_triage, 1.0)
        self.assertLess(len(true_positives) / all_true, 1.0,
                        "the fixture must keep at least one honest miss")

    def test_the_unmarked_fallback_is_missed_and_that_is_the_measured_ceiling(self):
        findings, code = self.scan("hard")
        self.assertEqual(findings, [], "the hard case is documented as a miss; if the scan "
                                       "now catches it, update the skill's claimed ceiling")
        self.assertEqual(code, 0)
        proc = self.run_python(self.tree / "hard" / "unmarked_fallback.py")
        real, invented = proc.stdout.split()
        self.assertEqual(real, invented,
                         "the point of the hard case: the invented answer is byte-identical "
                         "to the real one")

    def test_a_handler_returning_a_plausible_value_is_a_documented_miss(self):
        # `except ValueError: return 8080` is a real silent stub, and it was cut
        # from the rule set because on third-party code that shape is nearly
        # always deliberate (`except OSError: return False` in a predicate). The
        # prose taxonomy still covers it. This pins the tradeoff so it stays visible.
        findings, _ = self.scan("stubs/swallowed_exception.py")
        lines = {f[1] for f in findings}
        self.assertIn(11, lines, "the bare `except:` must still be caught")
        self.assertNotIn(19, lines, "the typed handler-return is a known, deliberate miss")
        self.assertTrue("except SpecificError: pass" in self.skill_text(),
                      "the skill must say which shapes it dropped and why")

    # 4. the scan must not itself fail silently -------------------------------

    def test_a_path_that_does_not_exist_is_an_error_not_a_clean_report(self):
        proc = self.run_scan(str(self.home / "nope"))
        self.assertEqual(proc.returncode, 2,
                         "a typo in the path must not produce a green Phase 4")
        self.assertEqual(proc.stdout, "")
        self.assertIn("no such path", proc.stderr)

    def test_non_python_files_are_reported_as_unscanned_not_skipped(self):
        other = self.tree / "polyglot"
        other.mkdir()
        (other / "handler.js").write_text(
            "function rate(p) {\n  // TODO: real provider\n  return 1.0;\n}\n", encoding="utf-8")
        (other / "svc.go").write_text(
            "func Rate(p string) float64 {\n\treturn 1.0\n}\n", encoding="utf-8")
        (other / "run.sh").write_text("set -e\ntrue || true\n", encoding="utf-8")
        findings, code = self.scan("polyglot")
        self.assertEqual(code, 1, "unscanned input is a finding, not a clean run")
        rules = {f[2] for f in findings}
        self.assertEqual(rules, {"unscanned-language"})
        self.assertIn("3 files not parsed", findings[0][3])
        self.assertIn("grep floor", findings[0][3])

    def test_the_grep_floor_covers_the_languages_the_parser_cannot(self):
        root = self.git_repo({
            "srv/handler.js": "function rate(p) {\n  // TODO: real provider\n  return 1.0;\n}\n",
            "srv/run.sh": "get_rate() {\n  # TODO: call the real provider\n  return 0\n}\n",
        })
        findings, code = self.scan_diff(root)
        self.assertEqual(code, 1)
        self.assertEqual({f[2] for f in findings}, {"floor-match"})
        self.assertEqual({f[0] for f in findings}, {"srv/handler.js", "srv/run.sh"})

    def test_usage_error_is_distinguishable_from_a_clean_run(self):
        proc = self.run_scan()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        proc = self.run_scan("--diff", str(self.tree))
        self.assertEqual(proc.returncode, 2, "--diff plus paths is a contradiction")

    def test_scan_reports_a_file_it_cannot_parse_rather_than_skipping_it(self):
        broken = self.tree / "stubs" / "broken.py"
        broken.write_text("def f(:\n    pass\n", encoding="utf-8")
        findings, code = self.scan("stubs/broken.py")
        self.assertEqual(code, 1)
        self.assertEqual([f[2] for f in findings], ["unparseable"])

    def test_the_documented_locate_idiom_finds_the_script_wherever_it_installs(self):
        # Phase 4 must not depend on a relative path that only resolves from
        # this repo's root. Rebuild the documented install layout and run it.
        install = self.home / ".claude" / "skills" / "no-silent-stub" / "scripts"
        install.mkdir(parents=True)
        shutil.copy(SCAN, install / "stub-scan.py")
        idiom = re.search(r"SCAN=\$\(ls.*?\)\n", self.skill_text(), re.S)
        self.assertIsNotNone(idiom, "SKILL.md must publish a locate idiom for the script")
        script = idiom.group(0) + 'python3 "$SCAN" --help >/dev/null && echo FOUND\n'
        proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                              env=self.env, cwd=str(self.tree))
        self.assertEqual(proc.stdout.strip(), "FOUND",
                         f"the skill's own locate idiom failed: {proc.stderr}")

    # 5. shapes a one-line edit used to hide ----------------------------------

    def test_a_literal_routed_through_one_local_is_still_a_literal(self):
        root = self.git_repo({"pricing.py": (
            "def quote(sku, region):\n"
            "    score = 0.42\n"
            "    return score\n")})
        findings, code = self.scan_diff(root)
        self.assertEqual(code, 1)
        self.assertEqual({f[2] for f in findings}, {"constant-stub"},
                         "constant propagation through a single local must not defeat it")

    def test_the_founding_example_from_54682_in_its_original_subscript_form(self):
        root = self.git_repo({"backfill.py": (
            'rec = {}\n'
            'row = {"expected_answer": "Paris"}\n'
            'rec["claude_answer"] = row["expected_answer"]\n'
            'rec["is_correct"] = True\n')})
        findings, code = self.scan_diff(root)
        self.assertEqual(code, 1)
        self.assertEqual({f[2] for f in findings}, {"self-scoring-eval"})
        self.assertEqual(len(findings), 2,
                         "both the column copy and the programmatic is_correct")

    def test_a_brand_new_untracked_file_is_not_invisible(self):
        # `git diff HEAD` never mentions a file that was never added to the
        # index, so without this the commonest case of all (the session wrote a
        # new module) scans clean. Found by running --diff against a real repo.
        root = self.git_repo({"srv/rates.py": (
            "import os\n\n\n"
            "def rate(pair):\n"
            "    key = os.environ.get('FX_API_KEY')\n"
            "    if not key:\n"
            "        return 1.0\n"
            "    return live(pair, key)\n")}, stage=False)
        proc = subprocess.run(["git", "status", "--porcelain"], cwd=str(root),
                              env=self.env, capture_output=True, text=True)
        self.assertIn("??", proc.stdout, "the file must really be untracked")
        findings, code = self.scan_diff(root)
        self.assertEqual(code, 1, "a new file full of stubs must not scan clean")
        self.assertIn("credential-fallback", {f[2] for f in findings})

    def test_documentation_that_discusses_stubs_is_not_a_finding(self):
        # Measured on a real unplanted diff: the floor fired nine times on prose
        # that merely mentions `except: pass` and TODO, including this skill's
        # own SKILL.md. Marker words now need something that returns beside them.
        root = self.git_repo({
            "NOTES.md": "We must never write `except: pass` or leave a TODO returning [].\n",
            "srv/ok.js": "// TODO: rename this variable one day\nconst rate = live();\n",
            "srv/bad.js": "function rate(p) {\n  // TODO: real provider\n  return 1.0;\n}\n",
        })
        findings, _ = self.scan_diff(root)
        flagged = {f[0] for f in findings}
        self.assertNotIn("NOTES.md", flagged, "prose is not code")
        self.assertNotIn("srv/ok.js", flagged, "a marker with no return beside it is a note")
        self.assertIn("srv/bad.js", flagged, "a marker directly above a return still counts")

    def test_a_change_that_adds_a_skip_or_xfail_is_reported(self):
        root = self.git_repo({"tests/test_rates.py": (
            "import pytest\n\n\n"
            "@pytest.mark.xfail\n"
            "def test_live_rate():\n"
            "    assert fetch() == 1.2\n")})
        findings, code = self.scan_diff(root)
        self.assertEqual(code, 1)
        self.assertIn("test-widening", {f[2] for f in findings},
                      "turning a red test green by skipping it is rung 2 of the ladder")

    # 6. is the failure observable after the prescribed fix? ------------------

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
        self.assertTrue(prescribed in self.skill_text(),
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

        findings, code = self.scan("stubs/credential_fallback.py")
        self.assertEqual((findings, code), ([], 0),
                         "the prescribed fix must also clear the mechanical scan")

    def test_a_raise_swallowed_upstream_is_still_a_stub_and_the_skill_says_so(self):
        # The prescribed raise only helps if it reaches a human. Demonstrate the
        # failure mode for real, then assert the skill tells you to check for it.
        app = self.tree / "outer.py"
        app.write_text(
            "def rate():\n"
            "    raise RuntimeError('rate: FX_API_KEY is not set')\n\n\n"
            "def total():\n"
            "    try:\n"
            "        return 100 * rate()\n"
            "    except Exception:\n"
            "        return 0.0\n\n\n"
            "print(f'TOTAL {total():.2f}')\n", encoding="utf-8")
        proc = self.run_python(app)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "TOTAL 0.00",
                         "a correct raise, eaten three frames up, is still a silent stub")
        self.assertTrue("Then check that your raise survives" in self.skill_text(),
                        "the skill must tell you to check the raise is not eaten upstream")

    # 7. the self-referential case (anthropics/claude-code#54682) -------------

    def test_self_scoring_eval_reports_a_perfect_score_and_the_scan_catches_it(self):
        stub = self.tree / "stubs" / "self_scoring_eval.py"
        proc = self.run_python(stub)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "accuracy: 100.0%",
                         "the eval that scores itself against its own input reports perfect")

        findings, code = self.scan("stubs/self_scoring_eval.py")
        self.assertEqual(code, 1)
        self.assertEqual({f[2] for f in findings}, {"self-scoring-eval"})
        messages = " | ".join(f[3] for f in findings)
        self.assertIn("copied from `expected_answer`", messages)
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

    # 8. the fixture is real code, not decoration -----------------------------

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
