#!/usr/bin/env python3
"""Executes the `stale-artifact-check` skill against real stale artifacts.

No mocks. Real venvs, real non-editable installs, real unrevalidated bytecode, a real
git repo, and a real pytest run. Every shell block in SKILL.md, and every inline
command it tells a session to run, is lifted out of the file and executed here, and
the exit status the skill claims is asserted.

The skill was cut down twice by cold review. What survives is the canary (Phase 1),
one Python import check (Phase 2), and remedies whose effect the canary verifies
(Phase 3). The rule that produced that shape is enforced mechanically below: a bash
block or a claimed command that nothing here runs fails the suite.

Findings pinned as named tests, so a regression cannot pass quietly.

Round 1:
  R1-B1  an in-repo `.venv` puts site-packages under $PWD, so a $PWD test reads current
  R1-B2  a flat layout is loaded from cwd, so one copy hid behind another
  R1-B5  `git diff | grep` passes on staged, untracked, and non-repo canaries
  R1-B6  a stderr canary is invisible under a capturing runner
Round 2:
  R2-B1  unchecked-hash and exact-mtime-restore bytecode serve old code invisibly
  R2-B2  a file canary with no truncate passes a re-prove that runs nothing
  R2-B3  a genuinely fresh flat layout must not be reported as stale
Round 3:
  R3-B1  `export CANARY=` does not survive a tool call, and an empty $CANARY grep
         matches every file, so the token is inlined literally everywhere
  R3-B2  a sourceless .pyc was reported CURRENT; one condition restores the verdict
  R3-B3  a module-scope raise is hidden by -qq/--tb=no and by a swallowing except
  R3-B4  tokens are stamped with a mint time, so an orphan is not mistaken for live
  R3-B5  a canary FILE with no matching text was reported CLEAN

Everything lives under a TemporaryDirectory with HOME pointed into it. Nothing is
installed into the ambient interpreter. All path comparisons resolve symlinks first:
on macOS /var and /tmp are symlinks into /private, and comparing the two forms is
itself a source of false stale verdicts.
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
FIXTURES = REPO / "tests" / "fixtures" / "stale-artifact-check"

PORTABLE_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "version"}
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
HOST_PYTHON_DIR = str(Path(sys.executable).parent)

# The ```bash blocks of SKILL.md in document order, each keyed by a substring.
BLOCK_KEYS = [
    "od -An -N4",         # 0: mint a time-stamped canary token
    "importlib.util",     # 1: which copy of the package loads
    "mine=CANARY",        # 2: sweep for your canary, and age everyone else's
]

# The placeholder the document uses in every example. It is deliberately not of the
# minted shape, so the Phase 4 sweep never mistakes this file or the SKILL for a live
# canary. Tests substitute a real token for it.
PLACEHOLDER = "CANARY-EPOCH-TOKEN"
TOKEN_SHAPE = re.compile(r"^CANARY-[0-9]{10}-[0-9a-f]{8}$")

# Commands the prose tells a session to run outside a fenced block. Each is executed
# by a test below, so the skill cannot make a claim the suite has not checked.
INLINE_COMMANDS = [
    'find . -name __pycache__ -type d -exec rm -rf {} +',
    'grep -ral CANARY-EPOCH-TOKEN dist/',
    'rm -f CANARY-EPOCH-TOKEN',
    'test -e CANARY-EPOCH-TOKEN && echo OBSERVED || echo ABSENT',
]


def mint(age_minutes=0):
    """A token of the shape the skill mints, optionally back-dated."""
    return "CANARY-%d-%s" % (int(time.time()) - age_minutes * 60, os.urandom(4).hex())


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


def strip_routing_pin(text):
    """Drop the `<!-- routing-pin ... -->` block. It is provenance metadata, not prose."""
    return re.sub(r"\n*<!-- routing-pin\b.*?-->\n*", "\n\n", text, count=1, flags=re.S)


class SkillDocumentTest(unittest.TestCase):
    """Frontmatter, size, structure, and the claims the prose makes."""

    @classmethod
    def setUpClass(cls):
        cls.text = SKILL.read_text()
        cls.front = cls.text.split("---\n")[1]
        cls.body = cls.text.split("---\n", 2)[2]

    def description(self):
        raw = re.search(r"^description: (.*)$", self.front, re.M).group(1)
        return raw[1:-1] if raw[:1] in "\"'" else raw

    def test_frontmatter_uses_only_portable_keys(self):
        keys = re.findall(r"^([A-Za-z0-9_-]+):", self.front, re.M)
        self.assertEqual(keys[0], "name")
        self.assertEqual(set(keys) - PORTABLE_KEYS, set())

    def test_description_is_quoted_so_the_yaml_cannot_break(self):
        raw = re.search(r"^description: (.*)$", self.front, re.M).group(1)
        self.assertIn(raw[:1], "\"'",
                      "quote it; an unquoted `: ` silently empties the metadata")
        self.assertEqual(raw[:1], raw[-1:])

    def test_frontmatter_really_parses_as_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml not installed")
        spec = yaml.safe_load(self.front)
        self.assertEqual(spec["name"], SKILL.parent.name)
        self.assertEqual(spec["description"], self.description())

    def test_frontmatter_and_description_are_within_limits(self):
        self.assertLessEqual(len(self.front), 1024)
        self.assertLessEqual(len(self.description()), 500)
        self.assertTrue(self.description().startswith("Use when")
                        or self.description().startswith("Use before"))

    # Round 3 deleted a test here that asserted the general-debugging phrases sat on
    # the negative side of the description. It measured clause position, and a router
    # matches on semantics, so it certified wording rather than behavior. The overlap
    # with `superpowers:systematic-debugging` is real and is reported, not asserted away.

    def test_the_skill_does_not_contradict_its_own_trigger(self):
        """R2 found "I added a console.log and nothing prints" routed both ways."""
        self.assertNotIn("not yet tried to fix", self.text,
                         "that clause excluded a case the Red flags section fires on")
        self.assertIn("nothing printed", self.text)
        self.assertIn("nothing prints", self.text.split("## Trigger precision")[1])

    def test_size_is_within_the_measured_house_range(self):
        """`wc -l` on this machine: superpowers:systematic-debugging 283, TDD 320, both
        read in full as house exemplars, against a documented hard ceiling of 500. The
        fenced blocks are executable and every one is run by this suite, so they are
        measured apart from the prose a reader has to absorb."""
        # The `<!-- routing-pin` block is machine-readable provenance for the routing
        # claims below it (tests/test_routing_claims.py), not prose. It is excluded for
        # the same reason the fenced blocks are: nobody reads it to learn the skill.
        prose = strip_routing_pin(self.body)
        lines = len(prose.strip().splitlines())
        fenced = sum(len(m.splitlines())
                     for m in re.findall(r"^```(?:bash)?\n(.*?)^```", prose, re.S | re.M))
        self.assertLessEqual(lines, 283)
        self.assertLessEqual(lines - fenced, 200, "prose at or under the measured median")

    def test_iron_law_is_present_and_fenced(self):
        self.assertRegex(self.text, r"## The Iron Law\n\n```\n[A-Z ,'\-]+\n```")

    def test_house_structure_sections_are_present_in_order(self):
        wanted = ["## The Iron Law", "## When this is the wrong skill", "## Phase 1",
                  "## Phase 2", "## Phase 3", "## Phase 4", "## Red flags",
                  "## Common rationalizations", "## Trigger precision", "## Quick reference"]
        found = [self.text.index(s) for s in wanted]
        self.assertEqual(found, sorted(found))

    def test_trigger_precision_lists_three_each_and_defers_defect_hunts(self):
        section = self.text.split("## Trigger precision")[1].split("## Quick reference")[0]
        must, must_not = section.split("must NOT fire this skill")
        fire = re.findall(r'^- "(.+?)"', must, re.M)
        no_fire = re.findall(r'^- "(.+?)"', must_not, re.M)
        self.assertEqual(len(fire), 3, "exactly 3 must-fire prompts: %r" % (fire,))
        self.assertEqual(len(no_fire), 3, "exactly 3 must-not-fire prompts: %r" % (no_fire,))
        self.assertEqual(set(fire) & set(no_fire), set())
        self.assertIn("systematic-debugging", must_not)

    def test_no_shared_canary_token_is_hardcoded(self):
        self.assertEqual(set(re.findall(r"CANARY-[0-9a-f]{4,}", self.text)), set())
        self.assertIn("od -An -N4", self.body)

    def test_r3_b1_no_command_depends_on_shell_state_from_an_earlier_call(self):
        """Separate tool calls do not share a shell, so `export CANARY=` is gone by the
        next one and `grep "$CANARY"` then matches every file and reports a canary that
        is not there. Every command must carry the token literally."""
        for script in blocks() + INLINE_COMMANDS:
            self.assertNotIn("$CANARY", script,
                             "a token read from the environment is empty in the next "
                             "tool call:\n%s" % script)
            self.assertNotIn("export CANARY", script)
        self.assertIn("separate tool calls do not share shell state", self.body,
                      "the lesson has now cost this repo two red-team rounds; record it")

    def test_r3_b1_the_document_only_ever_shows_a_non_minted_placeholder(self):
        """A real token in the docs would be found by every sweep in every checkout."""
        self.assertIn(PLACEHOLDER, self.body)
        self.assertEqual(re.findall(r"CANARY-[0-9]{10}-[0-9a-f]{8}", self.text), [],
                         "the SKILL must never contain a token of the minted shape")

    def test_only_python3_is_invoked_never_bare_python(self):
        """R2. Bare `python` is absent on Debian and stock macOS, and inside a venv it
        can resolve to a different interpreter than the one that was installed into."""
        for script in blocks():
            self.assertNotRegex(script, r"(?<![a-z0-9_.-])python(?![0-9])",
                                "use python3 explicitly:\n%s" % script)

    def test_r3_b3_the_file_form_is_the_default_and_the_raise_form_is_qualified(self):
        """A module-scope raise is hidden by -qq, --tb=no, --no-summary, -rN and by any
        swallowing except, so it cannot be the form a reader reaches for first."""
        table = self.body.split("|Form|Hidden by|")[1].split("\n\n")[0]
        rows = [r for r in table.splitlines() if r.startswith("|`")]
        self.assertIn("open(", rows[0], "the file form must be listed first")
        self.assertIn("Nothing", rows[0])
        self.assertIn("raise", rows[1])
        for flag in ("-qq", "--tb=no", "--no-summary", "-rN"):
            self.assertIn(flag, rows[1], "%s hides the raise form and must be named" % flag)
        self.assertIn("the default because", self.body)

    def test_r3_b4_the_sweep_matches_only_the_minted_token_shape(self):
        self.assertIn("CANARY-[0-9]{10}-[0-9a-f]{8}", block("mine=CANARY"))
        self.assertIn("date +%s", block("od -An -N4"),
                      "the token must carry its mint time")

    def test_undecidable_is_never_described_as_stale(self):
        """R2-B3. Prose may hedge; an exit code cannot, and the session acts on the code."""
        self.assertIn("Exit `0` is current, `1` is stale, `2` is undecidable and never "
                      "means either.", self.body)
        self.assertNotIn("SPLIT", self.body, "the ambiguous verdict must not read as a fault")

    def test_the_documented_traps_are_actually_documented(self):
        for claim, why in (
                ("realpath", "path comparisons must resolve symlinks"),
                ("/private", "macOS temp paths are the false-stale case"),
                ("sysconfig", "an in-repo .venv defeats a $PWD test"),
                ("unchecked-hash", "bytecode that is never revalidated"),
                ("A content check can", "R3, the narrowed bytecode claim"),
                ("mtime and size were restored", "the other invisible bytecode case"),
                ("git diff", "the diff-based cleanup gate must be warned against"),
                ("pytest -q -s", "the capture measurement must be stated"),
                ("Clear\nthe previous run's evidence first", "R2-B2, the truncate step"),
                ("--tb=no", "R3-B3, the flags that hide a raise canary"),
                ("exit status actually flips", "R3-B3, the output-independent signal"),
                ("sourceless `.pyc`", "R3-B2, the verdict that was missing"),
                ("import** name", "PKG is the import name, not the distribution name")):
            self.assertIn(claim, self.body, "%s (%r missing)" % (why, claim))

    def test_prose_avoids_the_banned_style(self):
        self.assertNotIn("\u2014", self.text, "no em-dashes")
        for word in ("leverage", "robust", "seamless", "delve", "comprehensive", "crucial"):
            self.assertNotIn(word, self.text.lower(), "banned word %r" % word)

    def test_nothing_unverifiable_survived_the_cut(self):
        """Round 2 asked for only what a fixture can check. Detectors for ecosystems
        this suite cannot exercise were deleted rather than shipped unverified."""
        self.assertFalse((SKILL.parent / "references").exists(),
                         "the served-artifact reference asserted docker and ssh behavior "
                         "that no fixture here can check")
        for gone in ("docker ", "ssh ", "lsof -ti", "--time-style", "ls -t"):
            self.assertNotIn(gone, self.text, "%r is a command this suite cannot verify" % gone)

    def test_every_bash_block_is_one_the_suite_runs(self):
        found = blocks()
        self.assertEqual(len(found), len(BLOCK_KEYS),
                         "SKILL.md has %d bash blocks but %d are executed here"
                         % (len(found), len(BLOCK_KEYS)))
        for script, key in zip(found, BLOCK_KEYS):
            self.assertIn(key, script, "bash blocks are out of the expected order")

    def test_every_inline_command_the_prose_claims_is_one_the_suite_runs(self):
        for command in INLINE_COMMANDS:
            self.assertIn(command, self.text,
                          "the suite runs %r; keep the text and the test in step" % command)


class PythonProvenanceTest(unittest.TestCase):
    """Block 1, against real venvs and real installs."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.python = make_venv(cls.root / "venv")

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

    def check(self, project, source):
        script = block("importlib.util",
                       **{"export PKG=mypkg SRC=src/mypkg/core.py":
                          "export PKG=mypkg SRC=%s" % source})
        return run(script, project, path_prefix=str(Path(self.python).parent))

    def value_from(self, cwd):
        """What the interpreter really returns, run from `cwd`."""
        result = subprocess.run([str(self.python), "-c",
                                 "import mypkg; print(mypkg.__file__); print(mypkg.f())"],
                                cwd=str(cwd), capture_output=True, text=True,
                                env={"PATH": BASE_PATH, "HOME": str(self.root)})
        self.assertEqual(result.returncode, 0, result.stderr)
        path, value = result.stdout.strip().splitlines()
        return real(path), value

    def test_non_editable_install_hides_the_edit_and_the_check_says_stale(self):
        project = self.project("src")
        self.install(project, editable=False)
        path, value = self.value_from(self.root)
        self.assertIn("site-packages", path)
        self.assertEqual(value, "OLD")

        (project / "src" / "mypkg" / "core.py").write_text('def f():\n    return "NEW"\n')
        self.assertEqual(self.value_from(self.root), (path, "OLD"),
                         "the edit is invisible: the whole failure mode")

        result = self.check(project, "src/mypkg/core.py")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("STALE", result.stdout)

    def test_editable_install_makes_the_check_pass_and_the_edit_visible(self):
        project = self.project("src")
        self.install(project, editable=False)
        (project / "src" / "mypkg" / "core.py").write_text('def f():\n    return "NEW"\n')
        self.assertEqual(self.check(project, "src/mypkg/core.py").returncode, 1)

        self.pip("uninstall", "-y", "mypkg")
        self.install(project, editable=True)

        result = self.check(project, "src/mypkg/core.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CURRENT", result.stdout)
        path, value = self.value_from(self.root)
        self.assertEqual(path, real(project / "src" / "mypkg" / "__init__.py"))
        self.assertEqual(value, "NEW")

    def test_r2_b3_a_fresh_flat_layout_is_never_reported_as_stale(self):
        """R2-B3. Flat package, non-editable install, edit, run from the repo root.

        The interpreter returns the NEW value, so this run IS current. The old code
        printed SPLIT and exited 1, and both the Phase 2 preamble and the quick
        reference define exit 1 as stale. Exit 2 is the honest answer: two copies
        exist and the directory you run from decides between them.
        """
        project = self.project("flat")
        self.install(project, editable=False)
        (project / "mypkg" / "core.py").write_text('def f():\n    return "NEW"\n')

        path, value = self.value_from(project)
        self.assertEqual(value, "NEW", "run from the repo root, this really is current")
        self.assertEqual(path, real(project / "mypkg" / "__init__.py"))

        result = self.check(project, "mypkg/core.py")
        self.assertNotEqual(result.returncode, 1,
                            "a current artifact must never be called stale:\n%s"
                            % (result.stdout + result.stderr))
        self.assertEqual(result.returncode, 2)
        self.assertIn("UNDECIDABLE", result.stdout)
        self.assertIn("site-packages", result.stdout,
                      "it must still name the other copy so the session can act")

    def test_flat_layout_with_nothing_installed_is_not_a_false_positive(self):
        project = self.project("flat")
        result = self.check(project, "mypkg/core.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CURRENT", result.stdout)

    def test_r3_b2_a_sourceless_pyc_is_stale_not_current(self):
        """Round 2 cut a stray-.pyc detector to a prose line. Round 3 showed the cut
        was the wrong half: with `mypkg/__init__.pyc` present and no `.py`, the runtime
        serves the compiled copy and the check printed CURRENT, exit 0."""
        project = Path(tempfile.mkdtemp(dir=str(self.root)))
        pkg = project / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text('def f():\n    return "OLD"\n')
        subprocess.run([str(self.python), "-m", "compileall", "-q", "mypkg"],
                       cwd=str(project), check=True, capture_output=True)
        tag = subprocess.run([str(self.python), "-c",
                              "import sys; print('cpython-%d%d' % sys.version_info[:2])"],
                             capture_output=True, text=True, check=True).stdout.strip()
        shutil.copy(str(pkg / "__pycache__" / ("__init__.%s.pyc" % tag)),
                    str(pkg / "__init__.pyc"))
        (pkg / "__init__.py").unlink()
        shutil.rmtree(str(pkg / "__pycache__"))
        (pkg / "core.py").write_text('def f():\n    return "NEW"\n')

        served = subprocess.run([str(self.python), "-c", "import mypkg; print(mypkg.f())"],
                                cwd=str(project), capture_output=True, text=True,
                                env={"PATH": BASE_PATH, "HOME": str(self.root)})
        self.assertEqual(served.stdout.strip(), "OLD",
                         "the sourceless .pyc really is what runs")

        result = self.check(project, "mypkg/core.py")
        self.assertEqual(result.returncode, 1,
                         "a sourceless .pyc must never read as current:\n%s"
                         % (result.stdout + result.stderr))
        self.assertIn("sourceless", result.stdout)

    def test_namespace_package_is_undecidable_rather_than_a_crash(self):
        project = Path(tempfile.mkdtemp(dir=str(self.root)))
        (project / "mypkg").mkdir()
        (project / "mypkg" / "thing.py").write_text("x = 1\n")
        result = self.check(project, "mypkg/thing.py")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("namespace", result.stdout)

    def test_unimportable_name_is_undecidable(self):
        project = self.project("src")
        script = block("importlib.util",
                       **{"export PKG=mypkg SRC=src/mypkg/core.py":
                          "export PKG=notapkg SRC=src/mypkg/core.py"})
        result = run(script, project, path_prefix=str(Path(self.python).parent))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not importable", result.stdout)

    def test_a_path_reached_through_a_symlink_does_not_read_as_stale(self):
        """macOS hands you a symlinked temp root for free (/var to /private/var); Linux
        does not. The condition under test is "the path is reached through a symlink",
        not "we are on a Mac", so build one when the platform has not supplied it.
        Skipping on Linux would leave this uncovered on the runner CI actually uses."""
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

        self.assertFalse(observed(), "the canary must NOT reach a run of the installed copy")
        self.pip("uninstall", "-y", "mypkg")
        self.install(project, editable=True)
        self.assertTrue(observed(), "once the pipeline is fixed the canary must appear")


class CanaryFormTest(unittest.TestCase):
    """Phase 1 steps 2 to 4, measured against a real pytest."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.token = mint()
        self.env = {"PATH": "%s:%s" % (HOST_PYTHON_DIR, BASE_PATH), "HOME": str(self.dir)}

    def tearDown(self):
        self.tmp.cleanup()

    def pytest_available(self):
        try:
            import pytest  # noqa: F401
        except ImportError:
            self.skipTest("pytest not importable by the host interpreter")

    def inline(self, index):
        return INLINE_COMMANDS[index].replace(PLACEHOLDER, self.token)

    def run_pytest(self, *flags):
        return subprocess.run([sys.executable, "-m", "pytest", *flags], cwd=str(self.dir),
                              capture_output=True, text=True, env=self.env)

    def test_minted_tokens_are_unique_stamped_and_of_the_swept_shape(self):
        seen = set()
        for _ in range(5):
            result = run(block("od -An -N4"), self.dir)
            self.assertEqual(result.returncode, 0, result.stderr)
            token = result.stdout.strip()
            self.assertRegex(token, TOKEN_SHAPE)
            minted = int(token.split("-")[1])
            self.assertLess(abs(minted - int(time.time())), 120,
                            "the stamp must be the real mint time or ageing is meaningless")
            seen.add(token)
        self.assertEqual(len(seen), 5, "tokens must not repeat: %r" % (seen,))

    def test_r3_b1_an_unset_variable_would_have_matched_every_file(self):
        """Why the token is inlined. This is the failure the skill now cannot make."""
        (self.dir / "dist").mkdir()
        (self.dir / "dist" / "bundle.js").write_text("totally unrelated build output\n")
        empty = run('grep -ral "$CANARY" dist/', self.dir, env={"CANARY": ""})
        self.assertEqual(empty.returncode, 0)
        self.assertIn("bundle.js", empty.stdout,
                      "an empty pattern matches anything, which reads as a canary found")
        literal = run(self.inline(1), self.dir)
        self.assertEqual(literal.returncode, 1,
                         "the inlined literal cannot produce that false positive")

    def test_r1_b6_a_stderr_canary_is_lost_but_a_file_canary_is_not(self):
        self.pytest_available()
        marker = self.dir / self.token
        (self.dir / "test_thing.py").write_text(textwrap.dedent("""
            import sys
            TOKEN = %r
            def helper():
                sys.stderr.write(TOKEN + "\\n")
                open(TOKEN, "a").write("x")
                return 1
            def test_ok():
                assert helper() == 1
        """) % self.token)
        quiet = self.run_pytest("-q")
        self.assertNotIn(self.token, quiet.stdout + quiet.stderr,
                         "a capturing runner swallows the stderr canary on a PASSING test")
        self.assertTrue(marker.exists(), "the file canary survives capture")
        marker.unlink()
        loud = self.run_pytest("-q", "-s")
        self.assertIn(self.token, loud.stdout + loud.stderr)

    def test_r3_b3_a_raise_canary_is_hidden_by_flags_and_by_a_swallowing_except(self):
        """The reason the file form is the default and the raise form carries caveats."""
        self.pytest_available()
        (self.dir / "mod.py").write_text('raise RuntimeError(%r)\n' % self.token)
        (self.dir / "test_thing.py").write_text(textwrap.dedent("""
            def test_ok():
                try:
                    import mod            # noqa: F401
                except Exception:
                    pass
                assert 1 == 1
        """))
        swallowed = self.run_pytest("-q")
        self.assertEqual(swallowed.returncode, 0)
        self.assertNotIn(self.token, swallowed.stdout + swallowed.stderr,
                         "an except clause hides the raise on a current artifact")

        (self.dir / "test_thing.py").write_text("import mod\ndef test_ok():\n    assert 1\n")
        hidden = self.run_pytest("-qq", "--tb=no", "-rN")
        self.assertNotEqual(hidden.returncode, 0,
                            "the exit status is the signal that survives every flag")
        self.assertNotIn(self.token, hidden.stdout + hidden.stderr,
                         "the token itself is hidden, so the text alone must not be trusted")

        shown = self.run_pytest("-q")
        self.assertIn(self.token, shown.stdout + shown.stderr,
                      "without those flags the raise form does work")

    def test_r2_b2_a_file_canary_passes_a_re_prove_that_ran_nothing(self):
        """Without the documented clear step the previous run answers for this one."""
        marker = self.dir / self.token
        marker.write_text("x")
        read = self.inline(3)
        stale = run('python3 -c "pass"; %s' % read, self.dir, path_prefix=HOST_PYTHON_DIR)
        self.assertIn("OBSERVED", stale.stdout,
                      "the defect: a run that executed nothing looks like a pass")

        cleared = run('%s; python3 -c "pass"; %s' % (self.inline(2), read), self.dir,
                      path_prefix=HOST_PYTHON_DIR)
        self.assertIn("ABSENT", cleared.stdout, "the documented rm -f closes it")
        self.assertFalse(marker.exists())

    def test_an_uncalled_canary_is_absent_from_a_current_artifact(self):
        self.pytest_available()
        (self.dir / "test_thing.py").write_text(textwrap.dedent("""
            def never_called():
                raise RuntimeError(%r)
            def test_ok():
                assert 1 == 1
        """) % self.token)
        result = self.run_pytest("-q")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn(self.token, result.stdout + result.stderr)
        self.assertIn("Absence proves nothing about a line that never runs", SKILL.read_text())

    def test_the_canary_grep_confirms_a_build_output(self):
        (self.dir / "dist").mkdir()
        (self.dir / "dist" / "index.js").write_text("// nothing\n")
        self.assertEqual(run(self.inline(1), self.dir).returncode, 1,
                         "no canary in the build output is a failure")
        (self.dir / "dist" / "index.js").write_text("// %s\n" % self.token)
        found = run(self.inline(1), self.dir)
        self.assertEqual(found.returncode, 0, found.stdout + found.stderr)
        self.assertIn("dist/index.js", found.stdout)


class InRepoVenvTest(unittest.TestCase):
    """R1-B1, which needs the venv inside the project directory."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.project = Path(cls.tmp.name) / "proj"
        shutil.copytree(str(FIXTURES / "pkg-src"), str(cls.project))
        cls.python = make_venv(cls.project / ".venv")
        env = dict(os.environ, HOME=cls.tmp.name, PIP_DISABLE_PIP_VERSION_CHECK="1")
        subprocess.run([str(cls.python), "-m", "pip", "--quiet", "install", "--no-index",
                        "--no-build-isolation", "."],
                       cwd=str(cls.project), env=env, check=True,
                       capture_output=True, text=True, timeout=300)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_r1_b1_site_packages_inside_the_repo_is_still_stale(self):
        """With `.venv` in the tree, site-packages IS under $PWD, so a path-prefix test
        reads "current" in the exact case the check exists for."""
        loaded = subprocess.run([str(self.python), "-c", "import mypkg; print(mypkg.__file__)"],
                                cwd=str(self.project), capture_output=True, text=True,
                                env={"PATH": BASE_PATH, "HOME": str(self.project)})
        installed = real(loaded.stdout.strip())
        self.assertTrue(installed.startswith(real(self.project) + os.sep),
                        "the fixture only tests this if site-packages is under the repo")
        self.assertIn("site-packages", installed)

        result = run(block("importlib.util"), self.project,
                     path_prefix=str(Path(self.python).parent))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("STALE", result.stdout)


class BytecodeRemedyTest(unittest.TestCase):
    """R2-B1. Two arrangements serve old code with no path evidence at all.

    Round 1 replaced a detector that only found harmless files. Round 2 showed the
    replacement was also wrong: `mod.__file__` points at the edited source in both
    cases below, so no path check can see them. The skill therefore ships a remedy,
    and these tests verify the remedy rather than a detector.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def value(self):
        result = subprocess.run([sys.executable, "-c",
                                 "import mod; print(mod.__file__); print(mod.f())"],
                                cwd=str(self.dir), capture_output=True, text=True,
                                env={"PATH": BASE_PATH, "HOME": str(self.dir)})
        self.assertEqual(result.returncode, 0, result.stderr)
        path, value = result.stdout.strip().splitlines()
        return real(path), value

    def source(self):
        return self.dir / "mod.py"

    def remedy(self):
        return run(INLINE_COMMANDS[0], self.dir)

    def test_r2_b1_unchecked_hash_bytecode_serves_old_code_until_pycache_is_cleared(self):
        self.source().write_text('def f():\n    return "OLD"\n')
        subprocess.run([sys.executable, "-m", "compileall", "-q",
                        "--invalidation-mode", "unchecked-hash", "mod.py"],
                       cwd=str(self.dir), check=True, capture_output=True)
        self.source().write_text('def f():\n    return "NEW"\n')

        path, value = self.value()
        self.assertEqual(value, "OLD", "unchecked-hash bytecode is never revalidated")
        self.assertEqual(path, real(self.source()),
                         "and __file__ points at the EDITED source, so no path check sees it")

        self.assertEqual(self.remedy().returncode, 0)
        self.assertEqual(self.value()[1], "NEW", "clearing __pycache__ is exactly the fix")

    def test_r2_b1_an_exactly_restored_mtime_serves_old_code_until_pycache_is_cleared(self):
        self.source().write_text('def f():\n    return "OLD"\n')
        before = os.stat(str(self.source()))
        subprocess.run([sys.executable, "-m", "compileall", "-q", "mod.py"],
                       cwd=str(self.dir), check=True, capture_output=True)
        self.source().write_text('def f():\n    return "NEW"\n')   # identical length
        os.utime(str(self.source()), (before.st_atime, before.st_mtime))

        self.assertEqual(self.value()[1], "OLD",
                         "same mtime and same size means no revalidation")
        self.assertEqual(self.remedy().returncode, 0)
        self.assertEqual(self.value()[1], "NEW")

    def test_a_pycache_orphan_is_harmless_which_is_why_it_is_not_a_detector(self):
        self.source().write_text('def f():\n    return "OLD"\n')
        subprocess.run([sys.executable, "-m", "compileall", "-q", "mod.py"],
                       cwd=str(self.dir), check=True, capture_output=True)
        self.source().unlink()
        result = subprocess.run([sys.executable, "-c", "import mod"], cwd=str(self.dir),
                                capture_output=True, text=True,
                                env={"PATH": BASE_PATH, "HOME": str(self.dir)})
        self.assertIn("ModuleNotFoundError", result.stderr,
                      "PEP 3147 bytecode never imports without its source")


class CanaryCleanupTest(unittest.TestCase):
    """Block 2. R1-B5, plus the round-3 orphan, file, and false-positive findings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.token = mint()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                              cwd=str(self.dir), capture_output=True, text=True,
                              env={"PATH": BASE_PATH, "HOME": str(self.dir)})

    def sweep(self, cwd=None):
        return run(block("mine=CANARY").replace(PLACEHOLDER, self.token), cwd or self.dir)

    def diff_gate(self):
        """The obvious version, kept only to show that it passes when it should not."""
        return run('git diff | grep -c "%s"' % self.token, self.dir)

    def test_a_clean_tree_passes(self):
        (self.dir / "a.py").write_text("def f():\n    return 1\n")
        result = self.sweep()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("CLEAN", result.stdout)

    @unittest.skipUnless(shutil.which("git"), "git not on PATH")
    def test_r1_b5_a_staged_canary_slips_past_git_diff_but_not_past_the_sweep(self):
        self.git("init", "-q", ".")
        (self.dir / "a.py").write_text("def f():\n    return 1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        (self.dir / "a.py").write_text('def f():\n    raise RuntimeError("%s")\n' % self.token)
        self.git("add", "a.py")

        self.assertEqual(self.diff_gate().stdout.strip(), "0",
                         "the defect: git diff reports nothing once the file is staged")
        result = self.sweep()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("a.py", result.stdout)

    @unittest.skipUnless(shutil.which("git"), "git not on PATH")
    def test_r1_b5_a_canary_in_an_untracked_file_is_caught(self):
        self.git("init", "-q", ".")
        (self.dir / "new.py").write_text('raise RuntimeError("%s")\n' % self.token)
        self.assertEqual(self.diff_gate().stdout.strip(), "0")
        self.assertEqual(self.sweep().returncode, 1)

    def test_r1_b5_the_sweep_works_outside_a_repository(self):
        (self.dir / "b.py").write_text('raise RuntimeError("%s")\n' % self.token)
        result = self.sweep()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("b.py", result.stdout)

    def test_r3_b5_an_empty_canary_file_is_not_clean(self):
        """The sweep was content-only, so a marker file with no matching text passed."""
        marker = self.dir / self.token
        marker.write_text("")
        content = run('grep -ranF --exclude-dir=.git "%s" .' % self.token, self.dir)
        self.assertEqual(content.returncode, 1,
                         "there is no matching TEXT anywhere, which is the trap")
        result = self.sweep()
        self.assertEqual(result.returncode, 1,
                         "the canary FILE is still on disk:\n%s" % result.stdout)
        self.assertIn(self.token, result.stdout)

    def test_a_canary_inside_node_modules_is_not_excluded(self):
        (self.dir / "node_modules" / "pkg").mkdir(parents=True)
        (self.dir / "node_modules" / "pkg" / "index.js").write_text(
            'throw new Error("%s");\n' % self.token)
        result = self.sweep()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("node_modules", result.stdout)

    def test_r3_b4_a_dead_sessions_orphan_is_distinguishable_from_a_live_canary(self):
        """Round 2 called every foreign token live and told the reader to leave it, so
        nothing could ever be removed. The mint time in the token settles it."""
        orphan, live = mint(age_minutes=180), mint(age_minutes=5)
        (self.dir / "dead.py").write_text('x = "%s"\n' % orphan)
        (self.dir / "alive.py").write_text('y = "%s"\n' % live)
        result = self.sweep()
        self.assertEqual(result.returncode, 0,
                         "another session's canary must not block your own cleanup")
        lines = result.stdout.splitlines()
        orphan_line = [l for l in lines if orphan in l][0]
        live_line = [l for l in lines if live in l][0]
        self.assertIn("ORPHAN", orphan_line)
        self.assertIn("safe to remove", orphan_line)
        self.assertIn("180m", orphan_line, "the age must be reported, not just the verdict")
        self.assertIn("LIVE in another session", live_line)
        self.assertIn("leave it alone", live_line)
        self.assertTrue((self.dir / "alive.py").exists())

    def test_yours_and_theirs_are_reported_separately(self):
        theirs = mint(age_minutes=2)
        (self.dir / "theirs.py").write_text('raise RuntimeError("%s")\n' % theirs)
        (self.dir / "mine.py").write_text('raise RuntimeError("%s")\n' % self.token)
        result = self.sweep()
        self.assertEqual(result.returncode, 1)
        yours = result.stdout.split("YOUR CANARY")[1]
        self.assertIn("mine.py", yours)
        self.assertNotIn("theirs.py", yours, "do not order removal of a live foreign canary")

    def test_r3_b4_the_sweep_is_silent_on_this_repository(self):
        """The round-2 sweep produced 12 hits from SKILL.md and this test file. The
        minted shape is what stops that, so it is checked against the real tree."""
        result = self.sweep(cwd=REPO)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("ORPHAN", result.stdout,
                         "documentation placeholders must never read as canaries")
        self.assertNotIn("LIVE in another session", result.stdout)
        self.assertIn("CLEAN", result.stdout)


if __name__ == "__main__":
    unittest.main()
