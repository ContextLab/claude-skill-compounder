#!/usr/bin/env python3
"""Executes the `stale-artifact-check` skill against real stale artifacts.

No mocks. Real venvs, real non-editable installs, real sourceless bytecode, real
mtimes, a real git repo, and a real pytest run. Every shell block in SKILL.md is
lifted out of the file and executed here, and the exit status the skill claims is
asserted. An unverified claim in a skill is a defect, so a newly added block that
nothing below runs fails the suite.

Round 1 of the red-team loop found that every Phase 2 check and the Phase 4 gate were
wrong. Those findings are pinned here as named tests (B1 through B6) so a regression
cannot pass quietly:

  B1  an in-repo `.venv` puts site-packages under $PWD, so a $PWD test reads "current"
  B2  a flat layout is loaded from cwd, so a non-editable install was undetectable
  B3  __pycache__ orphans are NOT importable; a `.pyc` outside it is the real hazard
  B4  `find | ls -t` batches, and missing directories produced a false FRESH
  B5  `git diff | grep` passes on staged, untracked, and non-repo canaries
  B6  a stderr canary is invisible under a capturing runner

Everything lives under a TemporaryDirectory with HOME pointed into it. Nothing is
installed into the ambient interpreter. All path comparisons resolve symlinks first:
on macOS /var and /tmp are symlinks into /private, and comparing the two forms is
itself a source of false "stale" verdicts (it broke this file on the macOS runner).
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
REFERENCE = REPO / "skills" / "stale-artifact-check" / "references" / "served-artifacts.md"
FIXTURES = REPO / "tests" / "fixtures" / "stale-artifact-check"

PORTABLE_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "version"}
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
HOST_PYTHON_DIR = str(Path(sys.executable).parent)

# The ```bash blocks of SKILL.md in document order, each keyed by a substring. Every
# one is executed by a test below; the inventory test fails if the file grows a block
# that nothing here runs.
BLOCK_KEYS = [
    "od -An -N4",                       # 0: generate a canary token
    "importlib.util",                   # 1: which copy of the package loads
    "-not -path '*/__pycache__/*'",     # 2: sourceless bytecode
    'grep -rl "$CANARY" dist/',         # 3: the canary reached the build output
    "os.walk",                          # 4: build output vs source mtime
    "--exclude-dir=.git",               # 5: remove every canary
]


def real(path):
    """Resolve symlinks before any comparison. /var -> /private/var on macOS."""
    return os.path.realpath(str(path))


def blocks():
    return re.findall(r"^```bash\n(.*?)^```", SKILL.read_text(), re.S | re.M)


def block(key, **substitutions):
    matches = [b for b in blocks() if key in b]
    assert len(matches) == 1, "expected exactly one SKILL.md block containing %r" % key
    script = matches[0]
    for old, new in substitutions.items():
        script = script.replace(old, new)
    return script


def run(script, cwd, env=None, path_prefix=None):
    """Run a shell script the way a session would, with a minimal environment."""
    full = {"PATH": BASE_PATH, "HOME": str(cwd), "LC_ALL": "C"}
    if path_prefix:
        full["PATH"] = "%s:%s" % (path_prefix, BASE_PATH)
    full.update(env or {})
    return subprocess.run(["bash", "-c", script], cwd=str(cwd), env=full,
                          capture_output=True, text=True)


def make_venv(path):
    """A real venv, or a clear skip. Never a stand-in."""
    try:
        subprocess.run([sys.executable, "-m", "venv", str(path)],
                       check=True, capture_output=True, text=True, timeout=180)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise unittest.SkipTest("python -m venv is unavailable here: %s" % exc)
    python = Path(path) / "bin" / "python"
    if not python.exists():
        raise unittest.SkipTest("venv produced no bin/python (unsupported layout)")
    return python


class SkillDocumentTest(unittest.TestCase):
    """The static contract: frontmatter, size, structure, and the claims in the prose."""

    @classmethod
    def setUpClass(cls):
        cls.text = SKILL.read_text()
        cls.front = cls.text.split("---\n")[1]
        cls.body = cls.text.split("---\n", 2)[2]

    def description(self):
        raw = re.search(r"^description: (.*)$", self.front, re.M).group(1)
        return raw[1:-1] if raw[:1] in "\"'" else raw

    def test_frontmatter_uses_only_portable_keys(self):
        self.assertTrue(self.text.startswith("---\n"))
        keys = re.findall(r"^([A-Za-z0-9_-]+):", self.front, re.M)
        self.assertEqual(keys[0], "name")
        self.assertEqual(set(keys) - PORTABLE_KEYS, set())

    def test_description_is_quoted_so_the_yaml_cannot_break(self):
        """An unquoted colon-space ends the scalar and the skill loads with no metadata."""
        raw = re.search(r"^description: (.*)$", self.front, re.M).group(1)
        self.assertIn(raw[:1], "\"'",
                      "quote the description; an unquoted `: ` silently empties the metadata")
        self.assertEqual(raw[:1], raw[-1:], "the quote must be closed on the same line")

    def test_frontmatter_really_parses_as_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml not installed")
        spec = yaml.safe_load(self.front)
        self.assertIsInstance(spec, dict)
        self.assertEqual(spec["name"], SKILL.parent.name)
        self.assertEqual(spec["description"], self.description())

    def test_frontmatter_and_description_are_within_limits(self):
        self.assertLessEqual(len(self.front), 1024)
        self.assertLessEqual(len(self.description()), 500)
        self.assertTrue(self.description().startswith("Use when"))

    def test_description_does_not_claim_general_debugging(self):
        """B7. `systematic-debugging` owns the general trigger; two skills racing is worse."""
        description = self.description()
        self.assertIn("systematic-debugging", description,
                      "the description must hand the general case to the skill that owns it")
        self.assertIn("Do NOT use", description)
        for overreach in ("any bug", "unexpected behavior", "test failure"):
            self.assertNotIn(overreach, description,
                             "%r reads as the general debugging trigger" % overreach)

    def test_name_matches_directory_and_charset(self):
        name = re.search(r"^name: (.*)$", self.front, re.M).group(1)
        self.assertEqual(name, SKILL.parent.name)
        self.assertRegex(name, r"^[a-z0-9-]+$")

    def test_size_is_within_the_measured_house_range(self):
        """Prose at the measured median; total under the largest top-tier skill on disk.

        `wc -l` on this machine: superpowers:systematic-debugging is 283 lines and
        superpowers:test-driven-development is 320, both read in full as house-style
        exemplars, against a documented hard ceiling of 500. The fenced blocks here are
        executable and every line of them is run by this suite, so they are measured
        separately from the prose that a reader has to absorb.
        """
        lines = len(self.body.strip().splitlines())
        fenced = sum(len(m.splitlines())
                     for m in re.findall(r"^```(?:bash)?\n(.*?)^```", self.body, re.S | re.M))
        self.assertLessEqual(lines, 320, "longer than the largest top-tier skill measured")
        self.assertLessEqual(lines - fenced, 210, "prose must stay near the 200-line median")

    def test_iron_law_is_present_and_fenced(self):
        self.assertRegex(self.text, r"## The Iron Law\n\n```\n[A-Z ,'\-]+\n```")

    def test_house_structure_sections_are_present_in_order(self):
        wanted = ["## The Iron Law", "## When this is the wrong skill", "## Phase 1",
                  "## Phase 2", "## Phase 3", "## Phase 4", "## Red flags",
                  "## Common rationalizations", "## Trigger precision", "## Quick reference"]
        found = [self.text.index(s) for s in wanted]
        self.assertEqual(found, sorted(found))

    def test_trigger_precision_lists_three_each_and_defers_root_cause_hunts(self):
        section = self.text.split("## Trigger precision")[1].split("## Quick reference")[0]
        must, must_not = section.split("must NOT fire this skill")
        fire = re.findall(r'^- "(.+?)"', must, re.M)
        no_fire = re.findall(r'^- "(.+?)"', must_not, re.M)
        self.assertEqual(len(fire), 3, "exactly 3 must-fire prompts: %r" % (fire,))
        self.assertEqual(len(no_fire), 3, "exactly 3 must-not-fire prompts: %r" % (no_fire,))
        self.assertEqual(set(fire) & set(no_fire), set())
        self.assertIn("systematic-debugging", must_not,
                      "one must-not-fire prompt has to be a plain root-cause hunt, "
                      "which is the boundary against the skill that owns that trigger")

    def test_no_shared_canary_token_is_hardcoded(self):
        """A token baked into the document is the same token in every parallel agent."""
        for path in (SKILL, REFERENCE):
            tokens = set(re.findall(r"CANARY-[0-9a-f]{4,}", path.read_text()))
            self.assertEqual(tokens, set(), "%s hardcodes %r" % (path.name, tokens))
        self.assertIn("od -An -N4", self.body, "the skill must generate a fresh token")

    def test_the_documented_traps_are_actually_documented(self):
        """Each of these was a real defect; the fix is only real if the reasoning ships."""
        for claim, why in (
                ("realpath", "path comparisons must resolve symlinks"),
                ("/private", "macOS temp paths are the false-stale case"),
                ("sysconfig", "an in-repo .venv defeats a $PWD test"),
                ("ls -t", "the batching trap must be called out"),
                ("ModuleNotFoundError", "__pycache__ orphans are not importable"),
                ("git diff", "the diff-based cleanup gate must be warned against"),
                ("pytest -q -s", "the capture measurement must be stated")):
            self.assertIn(claim, self.body, "%s (%r missing)" % (why, claim))

    def test_prose_avoids_the_banned_style(self):
        for path in (SKILL, REFERENCE):
            text = path.read_text()
            self.assertNotIn("\u2014", text, "%s: no em-dashes" % path.name)
            for word in ("leverage", "robust", "seamless", "delve", "comprehensive", "crucial"):
                self.assertNotIn(word, text.lower(), "%s: banned word %r" % (path.name, word))

    def test_served_artifact_detail_is_bundled_not_inlined(self):
        self.assertTrue(REFERENCE.is_file())
        self.assertIn("references/served-artifacts.md", self.text)
        for command in ("docker ", "ssh ", "lsof "):
            self.assertNotIn(command, self.text, "%r belongs in the reference" % command)
            self.assertIn(command, REFERENCE.read_text())

    def test_reference_avoids_the_gnu_only_flag_in_its_commands(self):
        """`--time-style` is GNU coreutils and fails on a BSD or macOS remote.

        The prose is allowed to name the flag, because warning about it is the point.
        A command that uses it is the defect.
        """
        text = REFERENCE.read_text()
        for fence in re.findall(r"^```bash\n(.*?)^```", text, re.S | re.M):
            self.assertNotIn("--time-style", fence,
                             "a reference command must not depend on GNU coreutils")
        self.assertIn("--time-style", text, "the trap has to stay documented")

    def test_every_bash_block_is_one_the_suite_runs(self):
        found = blocks()
        self.assertEqual(len(found), len(BLOCK_KEYS),
                         "SKILL.md has %d bash blocks but %d are executed by this suite"
                         % (len(found), len(BLOCK_KEYS)))
        for script, key in zip(found, BLOCK_KEYS):
            self.assertIn(key, script, "bash blocks are out of the expected order")


class CanaryTokenTest(unittest.TestCase):
    """Block 0. The token has to be fresh every time and findable by prefix."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_generated_tokens_are_unique_and_prefixed(self):
        seen = set()
        for _ in range(5):
            result = run(block("od -An -N4"), self.dir)
            self.assertEqual(result.returncode, 0, result.stderr)
            token = result.stdout.strip()
            self.assertRegex(token, r"^CANARY-[0-9a-f]{8}$")
            seen.add(token)
        self.assertEqual(len(seen), 5, "tokens must not repeat: %r" % (seen,))


class PythonProvenanceTest(unittest.TestCase):
    """Block 1, against a real venv and real installs. Covers B1 (partly), B2, and B6."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.venv = cls.root / "venv"
        cls.python = make_venv(cls.venv)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.pip("uninstall", "-y", "mypkg", check=False)

    def project(self, layout):
        path = Path(tempfile.mkdtemp(dir=str(self.root)))
        shutil.copytree(str(FIXTURES / ("pkg-" + layout)), str(path), dirs_exist_ok=True)
        return path

    def pip(self, *args, cwd=None, check=True):
        env = dict(os.environ)
        env.update({"HOME": str(self.root), "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                    "PIP_NO_INPUT": "1", "PIP_CACHE_DIR": str(self.root / "pipcache")})
        result = subprocess.run([str(self.python), "-m", "pip", "--quiet", *args],
                                cwd=str(cwd or self.root), env=env, capture_output=True,
                                text=True, timeout=300)
        if check and result.returncode != 0:
            self.fail("pip %s failed:\n%s\n%s" % (" ".join(args), result.stdout, result.stderr))
        return result

    def install(self, project, editable):
        args = ["install", "--no-index", "--no-build-isolation"]
        if editable:
            args.append("-e")
        self.pip(*args, ".", cwd=project)

    def check(self, project, source, python=None):
        script = block("importlib.util",
                       **{"export PKG=mypkg SRC=src/mypkg/core.py":
                          "export PKG=mypkg SRC=%s" % source})
        return run(script, project,
                   path_prefix=str(Path(python or self.python).parent))

    def import_value(self, project, python=None):
        """Import from a neutral directory and report the resolved file and the value."""
        result = subprocess.run(
            [str(python or self.python), "-c",
             "import mypkg; print(mypkg.__file__); print(mypkg.f())"],
            cwd=str(self.root), capture_output=True, text=True,
            env={"PATH": BASE_PATH, "HOME": str(self.root)})
        self.assertEqual(result.returncode, 0, result.stderr)
        path, value = result.stdout.strip().splitlines()
        return real(path), value

    def test_non_editable_install_hides_the_edit_and_the_check_says_stale(self):
        project = self.project("src")
        self.install(project, editable=False)
        path, value = self.import_value(project)
        self.assertIn("site-packages", path)
        self.assertEqual(value, "OLD")

        (project / "src" / "mypkg" / "core.py").write_text('def f():\n    return "NEW"\n')
        path_after, value_after = self.import_value(project)
        self.assertEqual(path_after, path)
        self.assertEqual(value_after, "OLD", "the edit is invisible: the whole failure mode")

        result = self.check(project, "src/mypkg/core.py")
        self.assertEqual(result.returncode, 1,
                         "the skill claims exit 1 here; got %d\n%s"
                         % (result.returncode, result.stdout + result.stderr))
        self.assertIn("STALE", result.stdout)

    def test_editable_install_makes_the_check_pass_and_the_edit_visible(self):
        project = self.project("src")
        self.install(project, editable=False)
        (project / "src" / "mypkg" / "core.py").write_text('def f():\n    return "NEW"\n')
        self.assertEqual(self.check(project, "src/mypkg/core.py").returncode, 1)

        self.pip("uninstall", "-y", "mypkg")
        self.install(project, editable=True)

        result = self.check(project, "src/mypkg/core.py")
        self.assertEqual(result.returncode, 0,
                         "the skill claims exit 0 once editable; got:\n%s"
                         % (result.stdout + result.stderr))
        self.assertIn("CURRENT", result.stdout)
        path, value = self.import_value(project)
        self.assertEqual(path, real(project / "src" / "mypkg" / "__init__.py"))
        self.assertEqual(value, "NEW")

    def test_b2_flat_layout_with_a_non_editable_install_is_reported_as_split(self):
        """B2. cwd is on sys.path, so the repo root and everywhere else load different files.

        The old `$PWD`-prefix check printed the tree path and exited 0 here, which made a
        non-editable install undetectable for every flat-layout project.
        """
        project = self.project("flat")
        self.install(project, editable=False)
        result = self.check(project, "mypkg/core.py")
        self.assertEqual(result.returncode, 1,
                         "a flat layout shadowing an installed copy must not read as current:\n%s"
                         % (result.stdout + result.stderr))
        self.assertIn("SPLIT", result.stdout)
        self.assertIn("site-packages", result.stdout,
                      "the report must name the other copy so the session can act on it")

    def test_flat_layout_with_nothing_installed_is_not_a_false_positive(self):
        project = self.project("flat")
        result = self.check(project, "mypkg/core.py")
        self.assertEqual(result.returncode, 0,
                         "an ordinary never-installed checkout is current:\n%s"
                         % (result.stdout + result.stderr))
        self.assertIn("CURRENT", result.stdout)

    def test_namespace_package_reports_cannot_check_rather_than_crashing(self):
        """`mod.__file__` is None for a namespace package; a crash used to read as stale."""
        project = Path(tempfile.mkdtemp(dir=str(self.root)))
        (project / "mypkg").mkdir()
        (project / "mypkg" / "thing.py").write_text("x = 1\n")
        result = self.check(project, "mypkg/thing.py")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("CANNOT CHECK", result.stdout)
        self.assertIn("namespace", result.stdout)

    def test_unimportable_name_reports_cannot_check(self):
        project = self.project("src")
        script = block("importlib.util",
                       **{"export PKG=mypkg SRC=src/mypkg/core.py":
                          "export PKG=notapkg SRC=src/mypkg/core.py"})
        result = run(script, project, path_prefix=str(Path(self.python).parent))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not importable", result.stdout)

    def test_paths_under_a_macos_temp_symlink_do_not_read_as_stale(self):
        """CI-1. /var is a symlink to /private/var; an unresolved compare fails everywhere.

        macOS supplies the symlinked temp root for free and Linux does not, so rather than
        skip on Linux (which would leave the regression uncovered on the platform CI runs
        most) the test builds the symlink itself when the environment has not already
        provided one. The condition under test is "reached through a symlink", not
        "running on a Mac".
        """
        project = self.project("src")
        self.install(project, editable=True)
        if str(project) == real(project):
            alias = self.root / ("alias-" + project.name)
            alias.symlink_to(real(project))
            project = alias
        self.assertNotEqual(str(project), real(project),
                            "the path under test must be reached through a symlink")
        result = self.check(project, "src/mypkg/core.py")
        self.assertEqual(result.returncode, 0,
                         "an unresolved path comparison reports a false STALE here:\n%s"
                         % (result.stdout + result.stderr))

    def test_canary_is_absent_on_the_stale_artifact_and_present_once_fixed(self):
        """The Iron Law, demonstrated rather than asserted."""
        project = self.project("src")
        self.install(project, editable=False)
        token = "CANARY-%s" % os.urandom(4).hex()
        (project / "src" / "mypkg" / "core.py").write_text(
            'def f():\n    raise RuntimeError("%s")\n' % token)

        def observed():
            result = subprocess.run([str(self.python), "-c", "import mypkg; mypkg.f()"],
                                    cwd=str(self.root), capture_output=True, text=True,
                                    env={"PATH": BASE_PATH, "HOME": str(self.root)})
            return token in (result.stdout + result.stderr)

        self.assertFalse(observed(),
                         "the canary must NOT reach a run that loads the installed copy; "
                         "every conclusion from such a run is void")
        self.pip("uninstall", "-y", "mypkg")
        self.install(project, editable=True)
        self.assertTrue(observed(),
                        "once the pipeline is fixed the canary must appear, which is the "
                        "only proof that the run contains the edit")

    @unittest.skipUnless(shutil.which("git"), "git not on PATH")
    def test_b6_a_stderr_canary_is_lost_but_a_file_canary_is_not(self):
        """B6. Measured against a real pytest, which is why the skill ranks the forms."""
        try:
            import pytest  # noqa: F401
        except ImportError:
            self.skipTest("pytest not importable by the host interpreter")
        project = Path(tempfile.mkdtemp(dir=str(self.root)))
        token = "CANARY-%s" % os.urandom(4).hex()
        marker = project / "canary.out"
        (project / "test_thing.py").write_text(textwrap.dedent("""
            import os, sys
            TOKEN = %r
            def helper():
                sys.stderr.write(TOKEN + "\\n")
                open(os.environ["CANARY_FILE"], "a").write(TOKEN + "\\n")
                return 1
            def test_ok():
                assert helper() == 1
        """) % token)
        env = {"PATH": "%s:%s" % (HOST_PYTHON_DIR, BASE_PATH), "HOME": str(self.root),
               "CANARY_FILE": str(marker)}
        quiet = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=str(project),
                               capture_output=True, text=True, env=env)
        self.assertNotIn(token, quiet.stdout + quiet.stderr,
                         "a capturing runner swallows the stderr canary, as the skill says")
        self.assertIn(token, marker.read_text(),
                      "the file canary survives capture, which is why the skill ranks it above")
        marker.unlink()
        loud = subprocess.run([sys.executable, "-m", "pytest", "-q", "-s"], cwd=str(project),
                              capture_output=True, text=True, env=env)
        self.assertIn(token, loud.stdout + loud.stderr,
                      "with capture disabled the printed form does work")

    def test_a_canary_on_a_path_that_never_runs_is_absent_from_a_current_artifact(self):
        """The trap the skill has to warn about: absence is only evidence on an executed line."""
        try:
            import pytest  # noqa: F401
        except ImportError:
            self.skipTest("pytest not importable by the host interpreter")
        project = Path(tempfile.mkdtemp(dir=str(self.root)))
        token = "CANARY-%s" % os.urandom(4).hex()
        (project / "test_thing.py").write_text(textwrap.dedent("""
            def never_called():
                raise RuntimeError(%r)
            def test_ok():
                assert 1 == 1
        """) % token)
        result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=str(project),
                                capture_output=True, text=True,
                                env={"PATH": "%s:%s" % (HOST_PYTHON_DIR, BASE_PATH),
                                     "HOME": str(self.root)})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn(token, result.stdout + result.stderr)
        self.assertIn("Absence proves nothing about a line that never runs", SKILL.read_text(),
                      "the skill must warn about this or it sends sessions to Phase 2 for free")


class InRepoVenvTest(unittest.TestCase):
    """B1 on its own, because it needs the venv inside the project directory."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.project = Path(cls.tmp.name) / "proj"
        shutil.copytree(str(FIXTURES / "pkg-src"), str(cls.project))
        cls.python = make_venv(cls.project / ".venv")
        env = dict(os.environ)
        env.update({"HOME": cls.tmp.name, "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
        subprocess.run([str(cls.python), "-m", "pip", "--quiet", "install", "--no-index",
                        "--no-build-isolation", "."],
                       cwd=str(cls.project), env=env, check=True,
                       capture_output=True, text=True, timeout=300)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_b1_site_packages_inside_the_repo_is_still_stale(self):
        """B1. With `.venv` in the tree, site-packages IS under $PWD.

        The old check tested whether the resolved path started with $PWD and so printed
        `<repo>/.venv/lib/python3.x/site-packages/mypkg/__init__.py` and exited 0, reading
        "current" in the exact case the check exists for. An in-repo venv is the common case.
        """
        loaded = subprocess.run(
            [str(self.python), "-c", "import mypkg; print(mypkg.__file__)"],
            cwd=str(self.project), capture_output=True, text=True,
            env={"PATH": BASE_PATH, "HOME": str(self.project)})
        installed = real(loaded.stdout.strip())
        self.assertTrue(installed.startswith(real(self.project) + os.sep),
                        "the fixture only tests B1 if site-packages really is under the repo")
        self.assertIn("site-packages", installed)

        result = run(block("importlib.util"), self.project,
                     path_prefix=str(Path(self.python).parent))
        self.assertEqual(result.returncode, 1,
                         "an in-repo .venv must still be reported as an installed copy:\n%s"
                         % (result.stdout + result.stderr))
        self.assertIn("STALE", result.stdout)


class SourcelessBytecodeTest(unittest.TestCase):
    """B3. The importable case is a `.pyc` outside __pycache__, not an orphan inside it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "foo.py").write_text('def f():\n    return "OLD"\n')
        subprocess.run([sys.executable, "-m", "compileall", "-q", "foo.py"],
                       cwd=str(self.dir), check=True, capture_output=True)
        tag = "cpython-%d%d" % sys.version_info[:2]
        self.cached = self.dir / "__pycache__" / ("foo.%s.pyc" % tag)
        self.assertTrue(self.cached.is_file())
        (self.dir / "foo.py").unlink()

    def tearDown(self):
        self.tmp.cleanup()

    def imports(self):
        return subprocess.run([sys.executable, "-c", "import foo; print(foo.f())"],
                              cwd=str(self.dir), capture_output=True, text=True,
                              env={"PATH": BASE_PATH, "HOME": str(self.dir)})

    def test_b3_a_pycache_orphan_is_not_importable_and_is_not_flagged(self):
        result = self.imports()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ModuleNotFoundError", result.stderr,
                      "PEP 3147 bytecode never imports without its source, so the old "
                      "detector only ever found harmless files")
        check = run(block("-not -path '*/__pycache__/*'"), self.dir)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("CURRENT", check.stdout)

    def test_b3_a_pyc_outside_pycache_serves_old_code_and_is_flagged(self):
        shutil.copy(str(self.cached), str(self.dir / "foo.pyc"))
        result = self.imports()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "OLD",
                         "this is the arrangement that silently serves old code")
        check = run(block("-not -path '*/__pycache__/*'"), self.dir)
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        self.assertIn("foo.pyc", check.stdout)


class BuildFreshnessTest(unittest.TestCase):
    """B4. Blocks 3 and 4, against real mtimes and a directory big enough to batch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        shutil.copytree(str(FIXTURES / "nodeproj"), str(self.dir), dirs_exist_ok=True)
        self.prefix = str(Path(sys.executable).parent)

    def tearDown(self):
        self.tmp.cleanup()

    def mtime_check(self):
        return run(block("os.walk"), self.dir, path_prefix=self.prefix)

    def test_an_unrebuilt_dist_is_stale_and_a_rebuild_clears_it(self):
        old = time.time() - 600
        os.utime(str(self.dir / "dist" / "index.js"), (old, old))
        (self.dir / "src" / "index.js").write_text(
            'module.exports = function greet() {\n  return "NEW";\n};\n')

        stale = self.mtime_check()
        self.assertEqual(stale.returncode, 1, stale.stdout + stale.stderr)
        self.assertIn("STALE", stale.stdout)

        build = run("cp src/index.js dist/index.js", self.dir)
        self.assertEqual(build.returncode, 0, build.stderr)
        fresh = self.mtime_check()
        self.assertEqual(fresh.returncode, 0, fresh.stdout + fresh.stderr)
        self.assertIn("FRESH", fresh.stdout)

    def test_b4_the_newest_build_file_is_found_exactly_not_per_batch(self):
        """`find dist -type f -exec ls -t {} + | head -1` sorts each exec batch separately."""
        now = time.time()
        for i in range(2500):
            path = self.dir / "dist" / ("f%04d.js" % i)
            path.write_text("x")
            stamp = now - 1000 + i * 0.001
            os.utime(str(path), (stamp, stamp))
        winner = self.dir / "dist" / "f0007.js"
        os.utime(str(winner), (now, now))
        os.utime(str(self.dir / "src" / "index.js"), (now - 500, now - 500))

        result = self.mtime_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dist/f0007.js", result.stdout,
                      "the check must name the true newest file, whatever the batch layout")

    def test_b4_a_missing_source_directory_cannot_report_fresh(self):
        shutil.rmtree(str(self.dir / "src"))
        result = self.mtime_check()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("CANNOT CHECK", result.stdout)
        self.assertNotIn("FRESH", result.stdout, "a missing directory is not a pass")
        self.assertEqual(result.stderr, "", "no unredirected error noise from a missing path")

    def test_b4_a_missing_build_directory_says_so_by_name(self):
        shutil.rmtree(str(self.dir / "dist"))
        result = self.mtime_check()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("'dist'", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_b4_a_content_free_touch_reports_stale_and_the_skill_admits_it(self):
        now = time.time() + 5
        os.utime(str(self.dir / "src" / "index.js"), (now, now))
        result = self.mtime_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Mtime lies in both directions", SKILL.read_text(),
                      "an mtime proxy that can be wrong must say so in the skill")

    def test_the_canary_grep_outranks_the_timestamp(self):
        token = "CANARY-%s" % os.urandom(4).hex()
        env = {"CANARY": token}
        missing = run(block('grep -rl "$CANARY" dist/'), self.dir, env=env)
        self.assertEqual(missing.returncode, 1, "no canary in the build output is a failure")
        self.assertIn("STALE", missing.stdout, "a silent failure is not a verdict")

        (self.dir / "dist" / "index.js").write_text('// %s\n' % token)
        present = run(block('grep -rl "$CANARY" dist/'), self.dir, env=env)
        self.assertEqual(present.returncode, 0, present.stdout + present.stderr)
        self.assertIn("CURRENT", present.stdout)


class CanaryCleanupTest(unittest.TestCase):
    """B5. The Phase 4 gate, against the three cases `git diff | grep` passes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.token = "CANARY-%s" % os.urandom(4).hex()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                              cwd=str(self.dir), capture_output=True, text=True,
                              env={"PATH": BASE_PATH, "HOME": str(self.dir)})

    def gate(self):
        return run(block("--exclude-dir=.git"), self.dir)

    def diff_gate(self):
        """The old gate, kept here only to demonstrate that it passes when it should not."""
        return run('git diff | grep -c "%s"' % self.token, self.dir)

    def test_a_clean_tree_passes(self):
        (self.dir / "a.py").write_text("def f():\n    return 1\n")
        result = self.gate()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("CLEAN", result.stdout)

    @unittest.skipUnless(shutil.which("git"), "git not on PATH")
    def test_b5_a_staged_canary_slips_past_git_diff_but_not_past_the_tree_grep(self):
        self.git("init", "-q", ".")
        (self.dir / "a.py").write_text("def f():\n    return 1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        (self.dir / "a.py").write_text('def f():\n    raise RuntimeError("%s")\n' % self.token)
        self.git("add", "a.py")

        self.assertEqual(self.diff_gate().stdout.strip(), "0",
                         "this is the defect: git diff reports nothing once the file is staged")
        result = self.gate()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("a.py", result.stdout)

    @unittest.skipUnless(shutil.which("git"), "git not on PATH")
    def test_b5_a_canary_in_an_untracked_file_is_caught(self):
        self.git("init", "-q", ".")
        (self.dir / "new.py").write_text('raise RuntimeError("%s")\n' % self.token)
        self.assertEqual(self.diff_gate().stdout.strip(), "0")
        self.assertEqual(self.gate().returncode, 1)

    def test_b5_the_gate_works_outside_a_repository(self):
        (self.dir / "b.py").write_text('raise RuntimeError("%s")\n' % self.token)
        result = self.gate()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("b.py", result.stdout)

    def test_b5_a_token_from_another_session_is_found_by_prefix(self):
        (self.dir / "c.py").write_text('raise RuntimeError("CANARY-0badc0de")\n')
        result = self.gate()
        self.assertEqual(result.returncode, 1,
                         "an interrupted session records nothing, so the prefix is the record")
        self.assertIn("c.py", result.stdout)


if __name__ == "__main__":
    unittest.main()
