#!/usr/bin/env python3
"""Tests for the `no-silent-stub` seed skill.

No mocks anywhere, which is not an aesthetic choice here: mocking the subject of
a skill about not mocking would refute the skill. Every fixture file is real
Python that runs, the skill's own shell commands are extracted from the SKILL.md
and executed against a real git repository, and its worked examples are imported
and called.

This skill deliberately ships no linter. Two independent red-team rounds built
their own corpora (308 kLOC and 893 kLOC of third-party Python) and measured a
scanner written for it at roughly 8% precision, blind to every stub in exception
form. `test_the_skill_ships_no_scanner` is the regression guard on that decision:
the doctrine is the deliverable.
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
FIXTURE = REPO / "tests" / "fixtures" / "no-silent-stub"

PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}

# The fixture corpus is the taxonomy as running code: one file per shape, plus
# the legitimate cases that must never be confused with them. Every file runs.
STUBS = (
    "stubs/hardcoded_return.py",
    "stubs/swallowed_exception.py",
    "stubs/credential_fallback.py",
    "stubs/services/ranker.py",
    "stubs/todo_return.py",
    "stubs/self_scoring_eval.py",
    "stubs/retry_returns_empty.py",
    "stubs/cache_miss_default.py",
)
BEYOND_ANY_CHECK = "hard/unmarked_fallback.py"
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

    def sh(self, script, cwd):
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                              env=self.env, cwd=str(cwd))

    def skill_text(self):
        return SKILL_MD.read_text(encoding="utf-8")

    def frontmatter_and_body(self):
        text = self.skill_text()
        self.assertTrue(text.startswith("---\n"), "SKILL.md must open with frontmatter")
        _, fm, body = text.split("---\n", 2)
        return fm, body

    def fenced(self, language):
        blocks = re.findall(rf"^```{language}\n(.*?)^```", self.frontmatter_and_body()[1],
                            re.M | re.S)
        self.assertTrue(blocks, f"SKILL.md has no ```{language} block")
        return blocks

    def git_repo(self, files, stage=True):
        root = self.home / "work"
        root.mkdir()
        run = lambda *a: subprocess.run(["git", *a], cwd=str(root), env=self.env,
                                        capture_output=True, text=True, check=True)
        run("init", "-q", ".")
        (root / "README.md").write_text("base\n", encoding="utf-8")
        run("add", "-A")
        run("commit", "-qm", "base")
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        if stage:
            run("add", "-A")
        return root

    # 1. the shape of the skill -----------------------------------------------

    def test_skill_exists_and_states_the_iron_law_once(self):
        self.assertTrue(SKILL_MD.is_file(), f"missing {SKILL_MD}")
        text = self.skill_text()
        self.assertTrue("IF IT CANNOT DO THE REAL THING, IT MUST FAIL IN A WAY THE CALLER "
                        "CANNOT MISS." in text, "the Iron Law must be stated verbatim")
        self.assertEqual(text.count("IF IT CANNOT DO THE REAL THING"), 1,
                         "the Iron Law is stated once, not repeated")

    def test_the_skill_ships_no_scanner(self):
        # Two independent corpora measured the scanner at ~8% precision, blind to
        # exception-form stubs. It was deleted rather than tuned. If it comes
        # back, it comes back with a precision number from a corpus nobody here
        # picked, and this test is where that argument gets made again.
        self.assertFalse((SKILL_DIR / "scripts").exists(),
                         "the scanner was removed on measured evidence; do not re-add it "
                         "without a precision measurement on an unchosen corpus")
        self.assertEqual(sorted(p.name for p in SKILL_DIR.rglob("*")), ["SKILL.md"])
        text = self.skill_text()
        for ghost in ("stub-scan", "scripts/", "--diff", "unscanned-language"):
            self.assertNotIn(ghost, text, f"dangling reference to the deleted scanner: {ghost}")

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

    def test_the_structure_the_house_style_asks_for(self):
        body = self.frontmatter_and_body()[1]
        headings = re.findall(r"^## (.+)$", body, re.M)
        for required in ("Iron Law", "The distinguishing question", "Red flags",
                         "Common rationalizations", "Trigger precision", "Quick reference"):
            self.assertIn(required, headings, f"missing section: {required}")
        self.assertLess(headings.index("Iron Law"), headings.index("Red flags"))
        self.assertLess(headings.index("Red flags"), headings.index("Common rationalizations"))

    def test_it_says_which_neighbouring_tool_to_reach_for_instead(self):
        text = self.skill_text()
        self.assertIn("pr-review-toolkit:silent-failure-hunter", text,
                      "the adjacent reviewer agent must be named, with when to use it")
        self.assertIn("agent, not a skill", text,
                      "say why it is not a trigger collision")
        self.assertIn("superpowers:verification-before-completion", text,
                      "Phase 5 must defer rather than compete")

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

    # 3. the prose the reviewers said carries the skill -----------------------

    def test_the_ladder_allows_a_visible_conditioned_skip(self):
        # Rung 2 used to forbid skip and xfail outright, which argues against
        # correct practice: a skipif naming its precondition is good engineering.
        text = self.skill_text()
        self.assertIn("skipif", text,
                      "the ladder must distinguish a reported skip from a hidden one")
        self.assertIn("does the suite output tell someone this was not checked, and why?",
                      text, "state the test that separates the two")
        rung = re.search(r"^2\. \*\*Fail the test.*?(?=^3\. )", self.frontmatter_and_body()[1],
                         re.M | re.S).group(0)
        self.assertIn("reason=", rung, "the good example must show a stated reason")
        self.assertIn("no reason", rung, "and name the bare skip as the bad one")

    def test_the_ladder_has_a_rung_for_best_effort_work(self):
        text = self.skill_text()
        self.assertIn("Log at error level and continue", text)
        self.assertTrue("cold-start" in text.lower(),
                        "the skill must name a case where the answer is not 'raise'")

    def test_the_import_shim_case_is_covered_and_its_example_behaves(self):
        text = self.skill_text()
        self.assertIn("Import shim", text, "a no-op shim is a stub for every call site")
        self.assertIn("not on PyPI", text, "cover the request as it actually arrives")
        shim = [b for b in self.fenced("python") if "class Client" in b]
        self.assertEqual(len(shim), 1, "exactly one worked shim example")
        module = self.home / "vendor_client.py"
        module.write_text(shim[0], encoding="utf-8")
        probe = subprocess.run(
            [sys.executable, "-c", "import vendor_client; print('IMPORT OK')"],
            capture_output=True, text=True, env=self.env, cwd=str(self.home))
        self.assertEqual(probe.stdout.strip(), "IMPORT OK",
                         f"the shim must still import: {probe.stderr}")
        call = subprocess.run(
            [sys.executable, "-c", "import vendor_client; vendor_client.Client()"],
            capture_output=True, text=True, env=self.env, cwd=str(self.home))
        self.assertNotEqual(call.returncode, 0, "calling it must fail")
        self.assertIn("NotImplementedError", call.stderr)
        self.assertIn("vendorsdk", call.stderr,
                      "the message must name the missing package")

    # 4. the skill's own commands must run ------------------------------------

    def test_the_prescribed_handler_search_matches_the_form_that_actually_bites(self):
        # The earlier version of this check used `except (Exception|BaseException)?\\s*:`
        # and `\\b`, and found nothing against `except Exception as exc:` under
        # git grep. A check that silently returns nothing reads as clean.
        command = [c for c in self.fenced("bash") if "except" in c]
        self.assertEqual(len(command), 1, "one handler-search command in the skill")
        script = command[0].replace("<the files between your raise and main>", "app.py")
        root = self.git_repo({"app.py": (
            "def total():\n"
            "    try:\n"
            "        return rate()\n"
            "    except Exception as exc:\n"
            "        return 0.0\n")})
        proc = self.sh(script, root)
        self.assertEqual(proc.returncode, 0,
                         f"the skill's own command found nothing: {proc.stderr}")
        self.assertIn("except Exception as exc:", proc.stdout,
                      "it must match the aliased handler, not only the bare one")

    def test_the_marker_grep_skips_prose_that_merely_discusses_stubs(self):
        command = [c for c in self.fenced("bash") if "git diff" in c]
        self.assertEqual(len(command), 1, "one marker-grep command in the skill")
        self.assertIn("'*.py'", command[0],
                      "the pathspec is what stops it flagging documentation")
        root = self.git_repo({}, stage=False)
        (root / "svc.py").write_text("x = 1\n", encoding="utf-8")
        (root / "NOTES.md").write_text("prose\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(root), env=self.env, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-qm", "two"], cwd=str(root), env=self.env,
                       check=True, capture_output=True)
        (root / "svc.py").write_text("x = 1\n# TODO: swap in the real thing\ny = []\n",
                                     encoding="utf-8")
        (root / "NOTES.md").write_text("prose\nmore TODO and placeholder and MagicMock\n",
                                       encoding="utf-8")
        proc = self.sh(command[0], root)
        self.assertIn("TODO: swap in the real thing", proc.stdout, proc.stderr)
        self.assertNotIn("placeholder", proc.stdout,
                         "documentation about stubs is not a finding")

    # 5. the fixture corpus, as running worked examples -----------------------

    def test_every_fixture_file_actually_runs(self):
        runnable = [p for p in sorted(self.tree.rglob("*.py"))
                    if "tests" not in p.relative_to(self.tree).parts]
        self.assertGreaterEqual(len(runnable), len(STUBS) + len(LEGIT) - 1)
        for path in runnable:
            with self.subTest(path=str(path.relative_to(self.tree))):
                proc = self.run_python(path)
                self.assertEqual(proc.returncode, 0,
                                 f"{path.name} did not run cleanly: {proc.stderr}")

    def test_the_corpus_covers_every_taxonomy_row(self):
        body = self.frontmatter_and_body()[1]
        table = re.search(r"^## Taxonomy.*?\n\n(\|Shape\|.*?)\n\n", body, re.M | re.S).group(1)
        rows = [r for r in table.splitlines()[2:] if r.startswith("|")]
        self.assertEqual(len(rows), 9, "nine shapes in the taxonomy")
        for rel in STUBS + (BEYOND_ANY_CHECK,):
            self.assertTrue((self.tree / rel).is_file(), f"missing worked example: {rel}")

    def test_every_stub_produces_output_that_looks_like_a_result(self):
        # This is the whole thesis in one assertion: none of these crash, and
        # every one of them prints something a reader would accept.
        for rel in STUBS:
            with self.subTest(stub=rel):
                proc = self.run_python(self.tree / rel)
                self.assertEqual(proc.returncode, 0,
                                 f"{rel} should not crash; that is the problem")
                self.assertTrue(proc.stdout.strip(),
                                f"{rel} should print a plausible-looking result")

    def test_the_unmarked_fallback_is_byte_identical_to_a_real_answer(self):
        proc = self.run_python(self.tree / BEYOND_ANY_CHECK)
        real, invented = proc.stdout.split()
        self.assertEqual(real, invented,
                         "the hard case: nothing mechanical reaches this, because the "
                         "invented answer is indistinguishable from the computed one")

    # 6. the self-referential case (anthropics/claude-code#54682) -------------

    def test_self_scoring_eval_reports_a_perfect_score(self):
        proc = self.run_python(self.tree / "stubs" / "self_scoring_eval.py")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "accuracy: 100.0%",
                         "the eval that scores itself against its own input reports perfect")
        source = (self.tree / "stubs" / "self_scoring_eval.py").read_text(encoding="utf-8")
        self.assertIn('actual_answer = row["expected_answer"]', source,
                      "the literal column copy from #54682")
        self.assertIn("expected_answer AS claude_answer", source,
                      "and its SQL form, which is how the incident was actually written")

    def test_the_honest_eval_scores_lower_on_a_harder_job(self):
        proc = self.run_python(self.tree / "legit" / "eval_harness_honest.py")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        score = float(re.search(r"([\d.]+)%", proc.stdout).group(1))
        self.assertLess(score, 100.0,
                        "an honest harness reports the score it measured, which here is "
                        "imperfect; that gap is the whole tell")

    # 7. does the prescribed fix make the failure observable? -----------------

    def test_prescribed_fix_turns_a_plausible_value_into_a_named_failure(self):
        target = self.tree / "stubs" / "credential_fallback.py"
        self.assertNotIn("FX_API_KEY", self.env, "the fixture must run without the real key")

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
            "    except Exception as exc:\n"
            "        return 0.0\n\n\n"
            "print(f'TOTAL {total():.2f}')\n", encoding="utf-8")
        proc = self.run_python(app)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "TOTAL 0.00",
                         "a correct raise, eaten two frames up, is still a silent stub")
        self.assertTrue("Then check that your raise survives" in self.skill_text(),
                        "the skill must tell you to check the raise is not eaten upstream")

    # 8. the legitimate half, which is the half that keeps it usable ----------

    def test_the_deliberate_test_double_lives_on_a_test_path_and_passes(self):
        suite = self.tree / "legit" / "tests" / "test_rate_math.py"
        proc = self.run_python(suite)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OK", proc.stderr)

    def test_the_legitimate_cases_are_all_present_and_each_names_why(self):
        for rel in LEGIT:
            with self.subTest(case=rel):
                path = self.tree / rel
                self.assertTrue(path.is_file(), f"missing counter-example: {rel}")
                doc = path.read_text(encoding="utf-8").split('"""')[1]
                self.assertTrue(doc.lstrip().lower().startswith("legitimate"),
                                f"{rel} must say in its docstring why it is not a stub")


if __name__ == "__main__":
    unittest.main()
