#!/usr/bin/env python3
"""Executes the `stale-artifact-check` skill against real stale artifacts.

No mocks. The test builds a real venv in a temp directory, really installs a real
package into it non-editably, really edits the working tree, and then runs the exact
shell blocks lifted out of SKILL.md to prove they detect the staleness the skill
claims they detect. Everything the installer touches lives under a TemporaryDirectory
with HOME pointed into it, so the ambient interpreter is never modified.

The package installs offline (`--no-index --no-build-isolation`) against the
setuptools that `python -m venv` provides, so no test here needs the network.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "stale-artifact-check" / "SKILL.md"
REFERENCE = REPO / "skills" / "stale-artifact-check" / "references" / "servers-and-images.md"
FIXTURES = REPO / "tests" / "fixtures" / "stale-artifact-check"

PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
CANARY = "CANARY-7f3a"

# Every ```bash block in SKILL.md, keyed by a substring that identifies it. The test
# asserts this mapping covers the file exactly, so a newly added command that nobody
# verified fails the suite rather than shipping as an unchecked claim.
BLOCK_KEYS = ["import importlib, os, sys", "SHADOWED", "ORPHAN", "newest_build", "git diff"]


def bash_blocks(text):
    """Return the body of every ```bash fenced block, in document order."""
    return re.findall(r"^```bash\n(.*?)^```", text, re.S | re.M)


def run(script, cwd, env=None, path_prefix=None):
    """Run a shell script the way a session would, and hand back the CompletedProcess."""
    full_env = {"PATH": BASE_PATH, "HOME": str(cwd), "LC_ALL": "C"}
    if path_prefix:
        full_env["PATH"] = "%s:%s" % (path_prefix, BASE_PATH)
    full_env.update(env or {})
    return subprocess.run(["bash", "-c", script], cwd=str(cwd), env=full_env,
                          capture_output=True, text=True)


class SkillDocumentTest(unittest.TestCase):
    """Static contract: frontmatter, size, and trigger precision, read off the real file."""

    @classmethod
    def setUpClass(cls):
        cls.text = SKILL.read_text()

    def test_frontmatter_uses_only_portable_keys(self):
        self.assertTrue(self.text.startswith("---\n"), "SKILL.md must open with frontmatter")
        front = self.text.split("---\n")[1]
        keys = re.findall(r"^([A-Za-z0-9_-]+):", front, re.M)
        self.assertEqual(keys[0], "name")
        self.assertEqual(set(keys) - PORTABLE_KEYS, set(),
                         "only the six portable frontmatter keys survive outside Claude Code")

    def test_frontmatter_and_description_are_within_limits(self):
        front = self.text.split("---\n")[1]
        self.assertLessEqual(len(front), 1024, "frontmatter must stay under 1024 chars")
        description = re.search(r"^description: (.*)$", front, re.M).group(1)
        self.assertLessEqual(len(description), 500, "description must stay under 500 chars")
        self.assertTrue(description.startswith("Use when"),
                        "description must be a pure 'Use when...' trigger clause")
        self.assertIn("Do NOT use", description,
                      "negative scope belongs in the description sentence, not only the body")

    def test_name_matches_directory_and_charset(self):
        name = re.search(r"^name: (.*)$", self.text.split("---\n")[1], re.M).group(1)
        self.assertEqual(name, SKILL.parent.name)
        self.assertRegex(name, r"^[a-z0-9-]+$")

    def test_body_is_within_the_house_line_ceiling(self):
        body = self.text.split("---\n", 2)[2]
        lines = len(body.strip().splitlines())
        self.assertLessEqual(lines, 500, "hard ceiling from the official skill docs")
        self.assertLessEqual(lines, 260, "house target is near the 200-line measured median")

    def test_iron_law_is_present_and_fenced(self):
        self.assertRegex(self.text, r"## The Iron Law\n\n```\n[A-Z ,'\-]+\n```")

    def test_house_structure_sections_are_present_in_order(self):
        wanted = ["## The Iron Law", "## Phase 1", "## Red flags",
                  "## Common rationalizations", "## Trigger precision", "## Quick reference"]
        found = [self.text.index(s) for s in wanted]
        self.assertEqual(found, sorted(found), "sections must appear in house order")

    def test_trigger_precision_lists_three_must_fire_and_three_must_not(self):
        section = self.text.split("## Trigger precision")[1].split("## Quick reference")[0]
        must, must_not = section.split("must NOT fire this skill")
        fire = re.findall(r'^- "(.+?)"', must, re.M)
        no_fire = re.findall(r'^- "(.+?)"', must_not, re.M)
        self.assertEqual(len(fire), 3, "exactly 3 must-fire prompts: %r" % (fire,))
        self.assertEqual(len(no_fire), 3, "exactly 3 must-not-fire prompts: %r" % (no_fire,))
        self.assertEqual(set(fire) & set(no_fire), set(), "the two lists must not overlap")

    def test_prose_avoids_the_banned_style(self):
        for path in (SKILL, REFERENCE):
            text = path.read_text()
            self.assertNotIn("\u2014", text, "%s: no em-dashes" % path.name)
            for word in ("leverage", "robust", "seamless", "delve", "comprehensive", "crucial"):
                self.assertNotIn(word, text.lower(), "%s: banned word %r" % (path.name, word))

    def test_heavy_per_stack_detail_is_bundled_not_inlined(self):
        self.assertTrue(REFERENCE.is_file())
        self.assertIn("references/servers-and-images.md", self.text,
                      "the body must point at the bundled reference")
        for command in ("docker ", "ssh ", "lsof "):
            self.assertNotIn(command, self.text,
                             "%r is served-artifact detail and belongs in the reference" % command)
            self.assertIn(command, REFERENCE.read_text(),
                          "the reference must actually carry %r" % command)

    def test_every_bash_block_is_one_the_suite_verifies(self):
        blocks = bash_blocks(self.text)
        self.assertEqual(len(blocks), len(BLOCK_KEYS),
                         "SKILL.md has %d bash blocks but %d are verified below"
                         % (len(blocks), len(BLOCK_KEYS)))
        for block, key in zip(blocks, BLOCK_KEYS):
            self.assertIn(key, block, "bash blocks are out of the expected order")

    def test_inline_commands_that_make_claims_are_the_ones_the_suite_runs(self):
        for command in ('pip install -e .',
                        'python -c "import sys; print(sys.prefix)"',
                        'find . -name __pycache__ -type d -exec rm -rf {} +'):
            self.assertIn(command, self.text,
                          "the suite verifies %r; keep the text and the test in step" % command)


class StaleArtifactFixtureTest(unittest.TestCase):
    """The real fixtures: a real venv, a real install, real mtimes, a real canary."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.venv = cls.root / "venv"
        try:
            subprocess.run([sys.executable, "-m", "venv", str(cls.venv)],
                           check=True, capture_output=True, text=True, timeout=180)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            cls.tmp.cleanup()
            raise unittest.SkipTest("python -m venv is unavailable here: %s" % exc)
        cls.python = cls.venv / "bin" / "python"
        if not cls.python.exists():
            cls.tmp.cleanup()
            raise unittest.SkipTest("venv produced no bin/python (unsupported platform layout)")
        cls.blocks = bash_blocks(SKILL.read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.proj = Path(tempfile.mkdtemp(dir=str(self.root)))
        shutil.copytree(str(FIXTURES / "pypkg"), str(self.proj), dirs_exist_ok=True)
        shutil.copytree(str(FIXTURES / "nodeproj"), str(self.proj), dirs_exist_ok=True)
        self.source = self.proj / "src" / "widget" / "__init__.py"
        self.pip("uninstall", "-y", "widget", check=False)

    # ------------------------------------------------------------------ helpers

    def pip(self, *args, check=True):
        env = dict(os.environ)
        env.update({"HOME": str(self.root), "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                    "PIP_NO_INPUT": "1", "PIP_CACHE_DIR": str(self.root / "pipcache")})
        result = subprocess.run([str(self.python), "-m", "pip", "--quiet", *args],
                                cwd=str(self.proj), env=env, capture_output=True,
                                text=True, timeout=300)
        if check and result.returncode != 0:
            self.fail("pip %s failed:\n%s\n%s" % (" ".join(args), result.stdout, result.stderr))
        return result

    def install(self, editable):
        args = ["install", "--no-index", "--no-build-isolation"]
        if editable:
            args.append("-e")
        self.pip(*args, ".")

    def write_source(self, body):
        self.source.write_text(textwrap.dedent(body).lstrip())

    def block(self, key, **substitutions):
        """Fetch the SKILL.md bash block identified by `key`, with placeholders filled."""
        matches = [b for b in self.blocks if key in b]
        self.assertEqual(len(matches), 1, "expected exactly one block containing %r" % key)
        script = matches[0].replace("mypkg", "widget")
        for name, value in substitutions.items():
            script = script.replace(name, value)
        return script

    def run_block(self, key, cwd=None, **substitutions):
        return run(self.block(key, **substitutions), cwd or self.proj,
                   path_prefix=str(self.venv / "bin"))

    def import_widget(self, cwd=None):
        """Import the package the way an unrelated caller would, and report file + value."""
        result = subprocess.run(
            [str(self.python), "-c",
             "import widget; print(widget.__file__); print(widget.f())"],
            cwd=str(cwd or self.root), capture_output=True, text=True,
            env={"PATH": BASE_PATH, "HOME": str(self.root)})
        self.assertEqual(result.returncode, 0, result.stderr)
        path, value = result.stdout.strip().splitlines()
        return path, value

    # -------------------------------------------------- fixture 1: python install

    def test_non_editable_install_really_hides_the_edit(self):
        self.install(editable=False)
        path, value = self.import_widget()
        self.assertIn("site-packages", path, "a non-editable install must land in site-packages")
        self.assertEqual(value, "OLD")

        self.write_source('def f():\n    return "NEW"\n')
        path_after, value_after = self.import_widget()
        self.assertEqual(path_after, path, "the import still resolves to the installed copy")
        self.assertEqual(value_after, "OLD",
                         "the edit is invisible to the runtime: this is the whole failure mode")
        self.assertEqual(self.source.read_text().strip().splitlines()[-1].strip(),
                         'return "NEW"', "the working tree really was edited")

    def test_skill_detection_command_catches_the_non_editable_install(self):
        self.install(editable=False)
        self.write_source('def f():\n    return "NEW"\n')
        result = self.run_block("import importlib, os, sys")
        self.assertEqual(result.returncode, 1,
                         "the skill claims exit 1 for a stale import; got %d\n%s"
                         % (result.returncode, result.stdout + result.stderr))
        self.assertIn("site-packages", result.stdout)

    def test_editable_install_makes_the_detection_pass_and_the_edit_visible(self):
        self.install(editable=False)
        self.write_source('def f():\n    return "NEW"\n')
        self.assertEqual(self.run_block("import importlib, os, sys").returncode, 1)

        self.pip("uninstall", "-y", "widget")
        self.install(editable=True)

        result = self.run_block("import importlib, os, sys")
        self.assertEqual(result.returncode, 0,
                         "the skill claims exit 0 once the install is editable; got:\n%s"
                         % (result.stdout + result.stderr))
        self.assertNotIn("site-packages", result.stdout)
        path, value = self.import_widget()
        self.assertEqual(os.path.realpath(path), os.path.realpath(str(self.source)))
        self.assertEqual(value, "NEW", "the edit is finally visible to the runtime")

    def test_shadow_check_discriminates_between_layouts(self):
        self.install(editable=False)
        clean = self.run_block("SHADOWED")
        self.assertEqual(clean.returncode, 0,
                         "a src-layout tree does not shadow: %s" % (clean.stdout + clean.stderr))
        self.assertIn("CONSISTENT", clean.stdout)

        shadow = self.proj / "widget"
        shadow.mkdir()
        (shadow / "__init__.py").write_text('def f():\n    return "SHADOW"\n')
        shadowed = self.run_block("SHADOWED")
        self.assertEqual(shadowed.returncode, 1,
                         "a package directory in cwd must be reported: %s"
                         % (shadowed.stdout + shadowed.stderr))
        self.assertIn("SHADOWED", shadowed.stdout)

    def test_orphan_bytecode_check_and_the_documented_cleanup(self):
        cache = self.proj / "src" / "widget" / "__pycache__"
        cache.mkdir()
        (cache / "gone.cpython-39.pyc").write_bytes(b"\x00\x00\x00\x00stale bytecode")
        orphaned = self.run_block("ORPHAN")
        self.assertEqual(orphaned.returncode, 1,
                         "bytecode with no source must be flagged: %s"
                         % (orphaned.stdout + orphaned.stderr))
        self.assertIn("ORPHAN:", orphaned.stdout)

        cleanup = run("find . -name __pycache__ -type d -exec rm -rf {} +", self.proj)
        self.assertEqual(cleanup.returncode, 0, cleanup.stderr)
        self.assertFalse(cache.exists())
        self.assertEqual(self.run_block("ORPHAN").returncode, 0,
                         "after the documented cleanup the check must pass")

    def test_documented_interpreter_probe_runs(self):
        probe = run('python -c "import sys; print(sys.prefix)"', self.proj,
                    path_prefix=str(self.venv / "bin"))
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(probe.stdout.strip(), str(self.venv),
                         "the probe must name the interpreter that will run the code")

    # ------------------------------------------------------ fixture 2: unrebuilt dist

    def test_unrebuilt_dist_is_flagged_and_a_rebuild_clears_it(self):
        old = time.time() - 600
        os.utime(self.proj / "dist" / "index.js", (old, old))
        (self.proj / "src" / "index.js").write_text(
            'module.exports = function greet() {\n  return "NEW";\n};\n')

        stale = self.run_block("newest_build")
        self.assertEqual(stale.returncode, 1,
                         "dist/ older than src/ must exit 1: %s" % (stale.stdout + stale.stderr))
        self.assertIn("STALE", stale.stdout)

        build = run("cp src/index.js dist/index.js", self.proj)
        self.assertEqual(build.returncode, 0, build.stderr)
        fresh = self.run_block("newest_build")
        self.assertEqual(fresh.returncode, 0,
                         "after the build the check must pass: %s" % (fresh.stdout + fresh.stderr))
        self.assertIn("FRESH", fresh.stdout)
        self.assertIn("NEW", (self.proj / "dist" / "index.js").read_text())

    def test_dist_check_reports_a_missing_build_directory(self):
        shutil.rmtree(str(self.proj / "dist"))
        result = self.run_block("newest_build")
        self.assertEqual(result.returncode, 1, "no build output at all is the stale case")
        self.assertIn("STALE", result.stdout)

    # ------------------------------------------------------------ the canary itself

    def canary_observed(self):
        """Run the exact command whose result the session was about to trust."""
        result = subprocess.run([str(self.python), "-c", "import widget; widget.f()"],
                                cwd=str(self.root), capture_output=True, text=True,
                                env={"PATH": BASE_PATH, "HOME": str(self.root)})
        return CANARY in (result.stdout + result.stderr)

    def test_canary_is_absent_on_the_stale_artifact_and_present_once_fixed(self):
        self.install(editable=False)
        self.write_source("""
            def f():
                raise RuntimeError("%s")
        """ % CANARY)

        self.assertFalse(self.canary_observed(),
                         "a raised canary must NOT reach a run that loads the installed copy; "
                         "any conclusion drawn from such a run is void")

        self.pip("uninstall", "-y", "widget")
        self.install(editable=True)
        self.assertTrue(self.canary_observed(),
                        "once the pipeline is fixed the canary must be observed, which is the "
                        "only proof that the run contains the edit")

    def test_canary_removal_check_reads_the_printed_count(self):
        git = run("git init -q . && git add -A && "
                  "git -c user.email=t@t -c user.name=t commit -qm base", self.proj)
        if git.returncode != 0:
            self.skipTest("git is unavailable: %s" % git.stderr.strip())

        clean = self.run_block("git diff")
        self.assertEqual(clean.stdout.strip(), "0",
                         "a clean tree must print 0, as the skill claims")

        self.write_source('def f():\n    raise RuntimeError("%s")\n' % CANARY)
        dirty = self.run_block("git diff")
        self.assertGreater(int(dirty.stdout.strip()), 0,
                           "a canary left in the tree must be found before committing")


if __name__ == "__main__":
    unittest.main()
