#!/usr/bin/env python3
"""Exercises skillcontrib for real: real SKILL.md files, real git repositories, real reads.

No mocks. The preflight tests write actual skill directories into a temp dir and run
the actual script against them, and one of them runs the checker over every skill
installed on this machine. The dedup tests hit live GitHub through `gh`; they skip
cleanly when gh is missing or unauthenticated so a token-less CI run still passes.

`OfflineProposeTest` covers the half of `skillcontrib propose` that writes. It builds
two REAL bare git repositories in a temp directory, an "upstream" and a "fork", and the
CLI clones, branches, copies, commits and pushes into them with the real git binary;
every assertion about what landed is read back with `git --git-dir ... log` and
`ls-tree` out of the bare repo. Three environment variables the CLI reads for exactly
this purpose point it at them: SKILLCONTRIB_UPSTREAM_URL, SKILLCONTRIB_FORK_URL, and
SKILLCONTRIB_GH.

The last of those names a SHIM: a small shell script this file writes into the sandbox
(`FAKE_GH` below), which answers the handful of `gh` subcommands the CLI calls with
canned JSON, logs every call so a test can assert which subcommands ran, and can be told
to fail one so a partial run is exercised. It is not a mock of anything under test:
`bin/skillcontrib` runs unmodified and holds all of the logic. It replaces the one
dependency whose real form would open a public pull request on every run of the suite,
which is also why the live-GitHub classes at the bottom of this file are read-only and
skip without auth.
"""

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "bin" / "skillcontrib"
LIVE_REPO = "cli/cli"
SKILLS_REPO = "anthropics/skills"
NESTED_REPO = "anthropics/claude-code"
PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
WRITE_COMMANDS = ("gh repo fork", "gh repo sync", "gh pr create", "git push")
PATH_BASE = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

# A git that cannot read the machine's config, cannot prompt, and has an identity of its
# own, so the sandbox does not depend on the ambient environment. `propose` runs a real
# `git commit`, which refuses without an identity.
GIT_ENV = {
    "GIT_AUTHOR_NAME": "skillcontrib test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "skillcontrib test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}

VALID = """---
name: %s
description: Use when a sample is needed. Do NOT use for anything real.
---

# Sample

A body.
"""


def gh_ready():
    """True when a real, authenticated gh is available on this machine."""
    if shutil.which("gh") is None:
        return False
    return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0


LIVE = gh_ready()


class PreflightTest(unittest.TestCase):
    """Real files, real script, minimal environment.

    The checker is deliberately narrow: SKILL.md exists, the frontmatter parses with a
    real YAML parser, and `name` matches the directory. An earlier version enforced
    length and key-portability limits and hard-failed 46 of 156 installed skills, so
    those checks are gone rather than re-tuned.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def skill(self, name, text=None):
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(text if text is not None else VALID % name)
        return d

    def preflight(self, path, *flags):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(self.root)}
        return subprocess.run([str(SCRIPT), "preflight", str(path)] + list(flags),
                              capture_output=True, text=True, env=env)

    def test_valid_skill_passes(self):
        r = self.preflight(self.skill("ok"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("name: ok (matches the directory)", r.stdout)

    def test_missing_directory_is_code_10(self):
        r = self.preflight(self.root / "nope")
        self.assertEqual(r.returncode, 10)
        self.assertIn("skill directory not found", r.stderr)

    def test_missing_skill_md_is_code_11(self):
        d = self.root / "empty"
        d.mkdir()
        r = self.preflight(d)
        self.assertEqual(r.returncode, 11)
        self.assertIn("SKILL.md not found", r.stderr)

    def test_no_frontmatter_is_code_12(self):
        r = self.preflight(self.skill("bare", "# Just a heading\n\nNo frontmatter.\n"))
        self.assertEqual(r.returncode, 12)
        self.assertIn("frontmatter missing", r.stderr)

    def test_unterminated_frontmatter_is_code_12(self):
        r = self.preflight(self.skill("open", "---\nname: open\ndescription: y\n\n# Body\n"))
        self.assertEqual(r.returncode, 12)
        self.assertIn("unterminated", r.stderr)

    def test_genuinely_broken_yaml_is_code_12(self):
        # Unbalanced quote: a real parser rejects this, a substring test would not.
        text = '---\nname: broke\ndescription: "unterminated\n---\n\n# B\n'
        r = self.preflight(self.skill("broke", text))
        self.assertEqual(r.returncode, 12)
        self.assertIn("does not parse as YAML", r.stderr)

    def test_missing_name_is_code_17(self):
        r = self.preflight(self.skill("anon", "---\ndescription: Use when nameless.\n---\n\n# B\n"))
        self.assertEqual(r.returncode, 17)
        self.assertIn("name is missing", r.stderr)

    def test_missing_description_is_code_17(self):
        # A skill with no description never fires, so this is precisely what preflight
        # is for. The check was removed by accident along with the length limits.
        r = self.preflight(self.skill("nodesc", "---\nname: nodesc\n---\n\n# B\n"))
        self.assertEqual(r.returncode, 17)
        self.assertIn("description is missing or empty", r.stderr)

    def test_empty_description_is_code_17(self):
        r = self.preflight(self.skill("blankdesc", '---\nname: blankdesc\ndescription: "  "\n---\n\n# B\n'))
        self.assertEqual(r.returncode, 17)
        self.assertIn("description is missing or empty", r.stderr)

    def test_name_not_matching_the_directory_is_code_17(self):
        # Claude Code addresses a skill by its directory, so this makes it unreachable.
        r = self.preflight(self.skill("dirname", VALID % "some-other-name"))
        self.assertEqual(r.returncode, 17)
        self.assertIn("name is 'some-other-name' but the directory is 'dirname'", r.stderr)

    # ------------------------------------------------- what must NOT be rejected

    def test_block_scalar_with_a_colon_is_accepted(self):
        # Valid YAML that a substring test for ": " wrongly rejected. This is the shape
        # the real huggingface-best skill uses.
        text = ('---\nname: demo\ndescription: >-\n  Use when the user wants a demo.\n'
                '  Triggers on: "demo", "show me".\n---\n\n# Demo\n')
        r = self.preflight(self.skill("demo", text))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_long_description_is_not_a_failure(self):
        # 29 of 156 installed skills exceed 500 characters. Length is a review topic.
        text = "---\nname: fat\ndescription: %s\n---\n\n# Body\n" % ("Use when " + "x" * 900)
        r = self.preflight(self.skill("fat", text))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_long_body_is_not_a_failure(self):
        body = "\n".join("line %d" % i for i in range(600))
        r = self.preflight(self.skill("longbody", (VALID % "longbody") + body + "\n"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_non_portable_frontmatter_keys_are_not_a_failure(self):
        # 44 of 156 installed skills carry keys like these, four of them Anthropic's.
        text = ('---\nname: custom\ndescription: Use when testing.\n'
                'argument-hint: "[thing]"\nlevel: 2\ntriggers: [a, b]\n---\n\n# B\n')
        r = self.preflight(self.skill("custom", text))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_other_files_in_the_skill_directory_are_listed(self):
        # A copy step that takes only SKILL.md silently drops these.
        d = self.skill("multi")
        (d / "scripts").mkdir()
        (d / "scripts" / "run.py").write_text("print('hi')\n")
        (d / "LICENSE.txt").write_text("license\n")
        r = self.preflight(d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LICENSE.txt", r.stdout)
        self.assertIn("scripts/run.py", r.stdout)


class InstalledSkillsSweepTest(unittest.TestCase):
    """The checker has to accept skills that actually ship, or nobody can use it."""

    def installed(self):
        found = []
        for root in (Path.home() / ".claude" / "skills",
                     Path.home() / ".claude" / "plugins" / "cache"):
            found += glob.glob(str(root) + "/**/SKILL.md", recursive=True)
        return sorted(set(found))

    def test_the_checker_accepts_essentially_every_installed_skill(self):
        skills = self.installed()
        if len(skills) < 20:
            self.skipTest("not enough installed skills on this machine to be meaningful")
        failures = []
        for f in skills:
            d = os.path.dirname(f)
            r = subprocess.run([str(SCRIPT), "preflight", d], capture_output=True, text=True)
            if r.returncode != 0:
                failures.append((d, r.stderr.strip().splitlines()[0] if r.stderr else ""))
        # The previous limit-enforcing version failed 46 of 156. Anything above a couple
        # of genuine name/directory mismatches means the gate is wrong again.
        self.assertLessEqual(len(failures), 3,
                             "checker rejects %d of %d installed skills:\n%s"
                             % (len(failures), len(skills),
                                "\n".join("%s :: %s" % f for f in failures[:10])))


class ShippedSkillTest(unittest.TestCase):
    """The skill this repo ships must satisfy the checker this repo ships."""

    SKILL_DIR = REPO / "skills" / "contribute-skill"

    def text(self):
        return (self.SKILL_DIR / "SKILL.md").read_text()

    def test_it_passes_its_own_preflight(self):
        r = subprocess.run([str(SCRIPT), "preflight", str(self.SKILL_DIR)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_frontmatter_is_parseable_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        data = yaml.safe_load(self.text().split("---\n")[1])
        self.assertIsInstance(data, dict)
        self.assertIsInstance(data.get("description"), str)
        self.assertTrue(set(data) <= PORTABLE_KEYS)

    def test_description_is_a_quoted_trigger_clause(self):
        desc = re.search(r"^description: (.+)$", self.text(), re.M).group(1)
        self.assertTrue(desc.startswith('"') and desc.endswith('"'),
                        "the description must be quoted so a colon cannot break the YAML")
        desc = desc[1:-1]
        self.assertTrue(desc.startswith("Use when"), desc[:60])
        self.assertIn("Do NOT use", desc)

    def test_the_description_still_matches_the_routing_pin(self):
        """The pin binds the description it was measured against.

        Rewriting the body of this skill is cheap; rewriting the description is not,
        because the pin then vouches for a string nobody measured and the only way to
        mend it is 18 real `claude -p` draws. `scripts/routing_claims.py lint` enforces
        this repo-wide; this asserts it here so the failure names the file that broke.
        """
        text = self.text()
        desc = re.search(r"^description: (.+)$", text, re.M).group(1)[1:-1]
        pinned = re.search(r"^description-sha256: ([0-9a-f]{64})$", text, re.M).group(1)
        self.assertEqual(hashlib.sha256(desc.encode("utf-8")).hexdigest(), pinned,
                         "the description changed but the routing pin still names the old "
                         "one. Re-measure with scripts/probe_routing_claims.py or revert.")

    # ---------------------------------------------------------- reading the document
    #
    # Everything below reads the SKILL.md as text. The class that executes the procedure
    # is OfflineProposeTest, which runs the real CLI against real local git repositories.

    def test_the_bar_is_stated_verbatim_and_wants_both(self):
        # Both conditions, in the wording the forge protocol uses. A paraphrase here
        # drifts from `skill-compounder`, and the bar is the one thing no probe checks.
        text = self.text()
        self.assertIn("Propose a skill upstream only when BOTH hold:", text)
        self.assertIn("**It came back clean from the `skill-compounder` red-team loop.**",
                      text)
        self.assertIn("Clean, from a cold red-teamer that was not a fork of the "
                      "authoring session.", text)
        self.assertIn("**It has been used again since it was forged.**", text)
        self.assertIn("At least one later invocation that did\n  the job, in real work, "
                      "not a rehearsal.", text)

    def test_the_procedure_is_the_dry_run_then_the_command(self):
        text = self.text()
        self.assertIn("skillcontrib recon <skill-name>", text)
        self.assertIn("skillcontrib propose <skill-name>", text)
        self.assertLess(text.index("skillcontrib recon"), text.index("skillcontrib propose"),
                        "the dry run must be named before the run that writes")

    def test_running_the_command_is_the_consent_and_no_gate_list_survives(self):
        # The seven lettered gates are gone on purpose. If any of them comes back the
        # document has two procedures in it and a session will walk whichever it reads
        # first.
        text = self.text()
        self.assertIn("Running it is the yes.", text)
        for gate in ("G0.", "G1.", "G2.", "G3.", "G4.", "G5.", "G6."):
            self.assertNotIn(gate, text, "consent gate %s is back alongside the command" % gate)

    def test_the_reader_never_types_a_network_write(self):
        """The whole point of the rewrite: the command performs the writes.

        Under the old procedure a session copied `gh repo fork` and `git push` out of
        this file by hand, which is what made the ordering rule something a session
        could get wrong. Now no shell block here contains one.
        """
        blocks = re.findall(r"```bash\n(.*?)```", self.text(), re.S)
        self.assertTrue(blocks, "the procedure must still show the commands to run")
        for block in blocks:
            for cmd in WRITE_COMMANDS:
                self.assertNotIn(cmd, block,
                                 "%r is in a block the reader is told to run:\n%s" % (cmd, block))
            for line in block.strip().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                self.assertTrue(line.startswith("skillcontrib "),
                                "a runnable block should invoke skillcontrib, got %r" % line)

    def test_every_network_write_is_documented_as_announced(self):
        text = self.text()
        self.assertIn("`WRITE:`", text)
        self.assertIn("at most three: the fork, the push, and `gh pr create`", text)

    def test_the_duplicate_check_is_still_three_probes(self):
        text = self.text()
        for probe in ("|tree|", "|files|", "|fuzzy|"):
            self.assertIn(probe, text, "the %s probe row is gone" % probe)
        self.assertIn("normalised key (lowercased, non-alphanumerics dropped)", text)
        self.assertIn("plugins/<x>/skills/<x>/SKILL.md", text)

    def test_the_maintainer_versus_fork_decision_is_still_described(self):
        text = self.text()
        self.assertIn("permission endpoint", text)
        self.assertIn("204 for read-only and triage collaborators", text)
        self.assertIn("`--head <fork-owner>:skill/<name>`", text)
        self.assertIn("push identity", text)

    def test_dry_run_is_not_claimed_to_be_read_only(self):
        # `gh pr create --dry-run` is gh's flag, not ours, and its own help says it may
        # push. `skillcontrib recon` is the preview; that flag is not.
        text = self.text()
        self.assertIn("May still push git changes", text)
        self.assertNotIn("without opening anything", text)

    def test_the_whole_skill_directory_travels(self):
        # A copy step that takes only SKILL.md silently drops scripts/ and references/.
        self.assertIn("copies the whole\n  skill directory", self.text())
        self.assertIn('cp -R "$skill_dir/."', SCRIPT.read_text(),
                      "the CLI must copy the directory, not just SKILL.md")

    def test_every_exit_code_the_document_names_is_in_the_script(self):
        """A code table nobody cross-checks is how a document starts lying.

        The script's header table is the source; this reads every bare number out of
        the document's own code column and requires the script to document it.
        """
        text = self.text()
        table = re.search(r"\|Code\|Meaning\|What to do\|\n(.*?)\n\n", text, re.S).group(1)
        codes = set()
        for row in table.splitlines():
            cell = row.split("|")[1]
            codes.update(int(n) for n in re.findall(r"\d+", cell))
        script = SCRIPT.read_text()
        header = script[:script.index("set -uo pipefail")]
        documented = set(int(n) for n in re.findall(r"^#\s+(\d+)\s+\S", header, re.M))
        self.assertTrue(codes, "the exit-code table went missing")
        self.assertLessEqual(codes, documented,
                             "the skill names exit codes the script does not document: %s"
                             % sorted(codes - documented))

    def test_no_em_dashes_anywhere(self):
        for p in [self.SKILL_DIR / "SKILL.md", SCRIPT,
                  REPO / "CONTRIBUTING.md", REPO / ".github" / "PULL_REQUEST_TEMPLATE.md"]:
            self.assertNotIn("—", p.read_text(), "em-dash in %s" % p)


# ----------------------------------------------------------------------------------
# The offline harness.
#
# `propose` is the only part of this package that writes to a service. Testing it needs
# two things that do not exist on a laptop: a repository to push to, and a `gh` that
# does not open real pull requests.
#
# The first is REAL. `upstream.git` and `fork.git` below are actual bare git
# repositories in a temp directory, and the CLI clones, branches, copies, commits and
# pushes into them with the real git binary. Every assertion about what landed is read
# back with `git --git-dir ... log` / `ls-tree` out of the bare repo, so what is checked
# is what a remote would hold.
#
# The second is a SHIM: `bin/gh` written below, named by SKILLCONTRIB_GH. It is not a
# mock of anything under test -- `bin/skillcontrib` runs unmodified, and the shim
# implements no logic of ours. It answers the handful of `gh` subcommands the CLI calls
# with canned JSON, logs every call to a file so the test can assert on what was and was
# not invoked, and can be told to fail one subcommand so a partial run is exercised. A
# real `gh` here would open a public pull request on every test run, which is why the
# live-GitHub classes further down are read-only and skip without auth.
# ----------------------------------------------------------------------------------

FAKE_GH = r"""#!/usr/bin/env bash
# Offline stand-in for `gh`, used only by tests/test_contribute.py. Canned answers, and
# a log of every call so the test can prove which subcommands ran.
set -u
printf '%s\n' "$*" >> "${FAKEGH_LOG:?}"
case "${1:-} ${2:-}" in
  "auth status") echo "github.com: logged in as ${FAKEGH_USER:-tester}"; exit 0 ;;
  "api user")    printf '%s\n' "${FAKEGH_USER:-tester}"; exit 0 ;;
  "repo view")
    case "$*" in
      *"--json name"*)
        # The fork-existence probe.
        if [ -f "${FAKEGH_DIR:?}/fork-exists" ]; then printf '{"name":"pool"}\n'; exit 0; fi
        echo "GraphQL: Could not resolve to a Repository" >&2; exit 1 ;;
      *)
        printf '{"isArchived":%s,"defaultBranchRef":{"name":"%s"}}\n' \
          "${FAKEGH_ARCHIVED:-false}" "${FAKEGH_BRANCH:-main}"; exit 0 ;;
    esac ;;
  "api "*)
    case "${2:-}" in
      */permission)
        if [ "${FAKEGH_PERM:-none}" = "none" ]; then
          echo "gh: Must have push access to view collaborator permission. (HTTP 403)"; exit 1
        fi
        printf '%s\n' "$FAKEGH_PERM"; exit 0 ;;
      *git/trees/*) cat "${FAKEGH_DIR:?}/tree.json"; exit 0 ;;
      *contents/*)  cat "${FAKEGH_DIR:?}/contents.md" 2>/dev/null; exit 0 ;;
      *) echo "fakegh: unhandled api path: ${2:-}" >&2; exit 1 ;;
    esac ;;
  "pr list") cat "${FAKEGH_DIR:?}/prs.json"; exit 0 ;;
  "repo fork")
    if [ -n "${FAKEGH_FORK_FAILS:-}" ]; then echo "fakegh: fork refused" >&2; exit 1; fi
    : > "${FAKEGH_DIR:?}/fork-exists"
    echo "Created fork ${FAKEGH_USER:-tester}/pool"; exit 0 ;;
  "pr create")
    if [ -n "${FAKEGH_PR_FAILS:-}" ]; then echo "fakegh: pr create refused" >&2; exit 1; fi
    printf '%s\n' "${FAKEGH_PR_URL:-https://github.com/acme/pool/pull/7}"; exit 0 ;;
  *) echo "fakegh: unhandled: $*" >&2; exit 1 ;;
esac
"""

PINNED = """---
name: demo-skill
description: "Use when a demo is needed for the offline harness. Do NOT use for real work."
---

# Demo

A body.

## Trigger precision

<!-- routing-pin
description-sha256: %s
prompts-sha256: %s
measured: %s
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: %s
-->

Prompts that MUST fire this skill:

1. "run the demo"
""" % ("0" * 64, "1" * 64, "%(measured)s", "%(result)s")


class OfflineProposeTest(unittest.TestCase):
    """`skillcontrib propose`, end to end, against local bare repos and a `gh` shim.

    Read the harness note above this class before changing anything here. Nothing about
    git is faked: the branch, the commit and the push are read back out of a bare
    repository with `git --git-dir`.
    """

    MEASURED = "measured: 2026-09-01"

    # ------------------------------------------------------------------ the sandbox

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.state = self.root / "state"
        self.canned = self.root / "canned"
        self.log = self.root / "gh-calls.log"
        for d in (self.home, self.canned, self.root / "bin"):
            d.mkdir(parents=True)
        shim = self.root / "bin" / "gh"
        shim.write_text(FAKE_GH)
        shim.chmod(0o755)
        self.log.write_text("")
        self.canned_tree(["skills/other/SKILL.md"])
        self.canned_prs([])
        self.upstream = self.build_bare("upstream.git", ["skills/other/SKILL.md"])
        self.fork = self.clone_bare("fork.git", self.upstream)
        self.write_skill()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, **kw):
        env = dict(GIT_ENV, PATH=PATH_BASE, HOME=str(self.home))
        r = subprocess.run(["git", *args], capture_output=True, text=True, env=env,
                           stdin=subprocess.DEVNULL, **kw)
        assert r.returncode == 0, "git %s\n%s\n%s" % (" ".join(args), r.stdout, r.stderr)
        return r.stdout

    def build_bare(self, name, paths):
        """A real bare repo with one commit on `main`, holding `paths`."""
        bare = self.root / name
        self.git("-c", "init.defaultBranch=main", "init", "--quiet", "--bare", str(bare))
        work = self.root / (name + ".work")
        work.mkdir()
        for p in paths:
            f = work / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("---\nname: %s\ndescription: x\n---\n\n# body\n" % Path(p).parent.name)
        self.git("-c", "init.defaultBranch=main", "init", "--quiet", str(work))
        self.git("-C", str(work), "add", "-A")
        self.git("-C", str(work), "commit", "--quiet", "-m", "seed")
        self.git("-C", str(work), "remote", "add", "origin", str(bare))
        self.git("-C", str(work), "push", "--quiet", "origin", "main")
        return bare

    def clone_bare(self, name, source):
        bare = self.root / name
        self.git("clone", "--quiet", "--bare", str(source), str(bare))
        return bare

    def canned_tree(self, paths):
        (self.canned / "tree.json").write_text(json.dumps(
            {"truncated": False, "tree": [{"path": p} for p in paths]}))

    def canned_prs(self, rows):
        (self.canned / "prs.json").write_text(json.dumps(rows))

    def write_skill(self, name="demo-skill", measured="2026-09-01",
                    result="verified 9/9 must-fire draws, 9/9 must-not-fire draws",
                    text=None, extra=True):
        d = self.home / ".claude" / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        body = text if text is not None else (PINNED % {"measured": measured,
                                                        "result": result})
        (d / "SKILL.md").write_text(body.replace("name: demo-skill", "name: " + name))
        if extra:
            (d / "scripts").mkdir(exist_ok=True)
            (d / "scripts" / "run.sh").write_text("echo hi\n")
        return d

    # ------------------------------------------------------------------ running it

    def env(self, **over):
        e = dict(GIT_ENV)
        e.update({
            "PATH": str(self.root / "bin") + ":" + PATH_BASE,
            "HOME": str(self.home),
            "SKILL_COMPOUNDER_STATE": str(self.state),
            "SKILLCONTRIB_GH": str(self.root / "bin" / "gh"),
            "SKILLCONTRIB_UPSTREAM_URL": "file://" + str(self.upstream),
            "SKILLCONTRIB_FORK_URL": "file://" + str(self.fork),
            "SKILLCONTRIB_NOW": "1700000000",
            "SKILLCONTRIB_FORK_SLEEP": "0",
            "SKILLCONTRIB_FORK_TRIES": "3",
            "FAKEGH_LOG": str(self.log),
            "FAKEGH_DIR": str(self.canned),
            "FAKEGH_USER": "tester",
            "FAKEGH_PERM": "none",
        })
        e.update(over)
        return e

    def propose(self, *args, **over):
        return subprocess.run([str(SCRIPT), "propose", "demo-skill",
                               "--upstream", "acme/pool", *args],
                              capture_output=True, text=True, env=self.env(**over),
                              stdin=subprocess.DEVNULL, timeout=120)

    def gh_calls(self):
        return [ln for ln in self.log.read_text().splitlines() if ln.strip()]

    def writes_called(self):
        return [c for c in self.gh_calls()
                if c.startswith("repo fork") or c.startswith("pr create")]

    def refs(self, bare):
        r = subprocess.run(["git", "--git-dir", str(bare), "show-ref"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return r.stdout

    def ledger_rows(self, event="contrib"):
        f = self.state / "ledger.jsonl"
        if not f.exists():
            return []
        out = []
        for ln in f.read_text().splitlines():
            if ln.strip():
                row = json.loads(ln)
                if row.get("event") == event:
                    out.append(row)
        return out

    def write_lines(self, stdout):
        return [ln for ln in stdout.splitlines() if ln.startswith("WRITE:")]

    # ---------------------------------------------------- the fork path, end to end

    def test_the_fork_path_lands_branch_commit_and_files_in_the_fork(self):
        before_upstream = self.refs(self.upstream)
        r = self.propose()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])

        self.assertIn("refs/heads/skill/demo-skill", self.refs(self.fork),
                      "the branch never reached the fork")
        listed = subprocess.run(
            ["git", "--git-dir", str(self.fork), "ls-tree", "-r", "--name-only",
             "skill/demo-skill"], capture_output=True, text=True,
            stdin=subprocess.DEVNULL).stdout
        self.assertIn("skills/demo-skill/SKILL.md", listed)
        self.assertIn("skills/demo-skill/scripts/run.sh", listed,
                      "the whole skill directory must travel, not just SKILL.md")
        self.assertEqual(before_upstream, self.refs(self.upstream),
                         "the fork path must not touch upstream")

    def test_the_commit_message_carries_the_routing_pins_measured_line(self):
        r = self.propose()
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        msg = subprocess.run(["git", "--git-dir", str(self.fork), "log", "-1",
                              "--pretty=%B", "skill/demo-skill"],
                             capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout
        self.assertIn("Add demo-skill skill", msg)
        self.assertIn(self.MEASURED, msg,
                      "a reviewer cannot tell a measured trigger from an unmeasured one "
                      "without this line: %r" % msg)

    def test_the_maintainer_path_pushes_to_upstream_and_never_forks(self):
        before_fork = self.refs(self.fork)
        r = self.propose(FAKEGH_PERM="admin")
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertIn("refs/heads/skill/demo-skill", self.refs(self.upstream))
        self.assertEqual(before_fork, self.refs(self.fork))
        self.assertEqual([c for c in self.gh_calls() if c.startswith("repo fork")], [],
                         "a maintainer must not fork a repo they can already write to")
        self.assertIn("maintainer path", r.stdout)

    def test_the_ledger_row_has_the_documented_shape(self):
        r = self.propose()
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        rows = self.ledger_rows()
        self.assertEqual(len(rows), 1, "expected exactly one contrib row, got %r" % rows)
        row = rows[0]
        self.assertEqual(row["name"], "demo-skill")
        self.assertEqual(row["upstream"], "acme/pool")
        self.assertEqual(row["fork"], True)
        self.assertEqual(row["pr"], "https://github.com/acme/pool/pull/7")
        self.assertEqual(row["ts"], 1700000000)

    def test_the_ledger_row_is_invisible_to_the_forge_join(self):
        # Every ledger reader selects BY NAME. A new event type must not be readable as
        # a forge start or outcome, or the forge counts move the day this lands.
        self.propose()
        for event in ("start", "done", "fail", "use", "origin"):
            self.assertEqual(self.ledger_rows(event), [],
                             "a contrib run wrote a %r row" % event)

    # -------------------------------------------------------------- the WRITE: lines

    def test_every_network_write_is_announced_and_nothing_else_is(self):
        r = self.propose()
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        lines = self.write_lines(r.stdout)
        self.assertEqual(len(lines), 3, "expected three WRITE: lines, got %r" % lines)
        self.assertIn("gh repo fork acme/pool", lines[0])
        self.assertIn("git push -u origin skill/demo-skill", lines[1])
        self.assertIn("gh pr create --repo acme/pool", lines[2])
        # And the writes that actually happened are those and no more: two through gh,
        # one through git (proved by the branch being in the fork).
        self.assertEqual(len(self.writes_called()), 2, self.gh_calls())
        self.assertIn("refs/heads/skill/demo-skill", self.refs(self.fork))

    def test_the_write_line_is_printed_before_the_write_it_names(self):
        """Proved by making the write fail.

        The fork is refused by the shim, so nothing after that line runs. The line is
        on stdout anyway, which is only possible if it was printed first.
        """
        r = self.propose(FAKEGH_FORK_FAILS="1")
        self.assertEqual(r.returncode, 23, r.stdout[-2000:] + r.stderr[-1000:])
        self.assertIn("WRITE: gh repo fork acme/pool --clone=false", r.stdout)
        self.assertNotIn("refs/heads/skill/demo-skill", self.refs(self.fork))
        self.assertEqual(self.ledger_rows(), [])

    def test_a_failed_pull_request_says_the_branch_is_already_pushed(self):
        # The dangerous half-state. Re-running propose would try to push again, so the
        # message has to say what already happened.
        r = self.propose(FAKEGH_PR_FAILS="1")
        self.assertEqual(r.returncode, 25, r.stdout[-2000:] + r.stderr[-1000:])
        self.assertIn("refs/heads/skill/demo-skill", self.refs(self.fork),
                      "the push happened before gh pr create; the fixture is wrong")
        self.assertIn("ALREADY PUSHED", r.stderr)
        self.assertEqual(self.ledger_rows(), [], "no pull request means no contrib row")

    # ------------------------------------------------------------------- the dry run

    def test_the_dry_run_writes_nothing_anywhere(self):
        before_fork, before_upstream = self.refs(self.fork), self.refs(self.upstream)
        r = self.propose("--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertEqual(before_fork, self.refs(self.fork))
        self.assertEqual(before_upstream, self.refs(self.upstream))
        self.assertEqual(self.writes_called(), [], self.gh_calls())
        self.assertEqual(self.ledger_rows(), [])
        self.assertFalse((self.state / "contrib").exists(),
                         "a dry run must not create the work tree either")
        self.assertEqual(self.write_lines(r.stdout), [],
                         "a dry run must not print a WRITE: line; it writes nothing")

    def test_the_dry_run_prints_what_the_real_run_would_do(self):
        r = self.propose("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        for expected in ("would run: gh repo fork acme/pool --clone=false",
                         "would run: git push -u origin skill/demo-skill",
                         "would run: gh pr create --repo acme/pool",
                         "would append one row to",
                         '"event":"contrib"'):
            self.assertIn(expected, r.stdout, "the plan does not mention %r" % expected)

    def test_the_dry_run_prints_the_whole_pull_request_body(self):
        r = self.propose("--dry-run")
        body = r.stdout[r.stdout.index("--- 8< ---"):r.stdout.index("--- >8 ---")]
        self.assertIn("Use when a demo is needed for the offline harness.", body,
                      "the body must carry the description a reviewer reads")
        self.assertIn("verified 9/9 must-fire draws", body,
                      "the body must carry the routing pin's own result line")
        self.assertIn("recorded uses since:", body,
                      "the body must carry the ledger's use count")

    def test_recon_is_the_dry_run_under_another_name(self):
        dry = self.propose("--dry-run")
        recon = subprocess.run([str(SCRIPT), "recon", "demo-skill", "--upstream", "acme/pool"],
                               capture_output=True, text=True, env=self.env(),
                               stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(recon.returncode, 0, recon.stderr[-2000:])
        self.assertEqual(recon.stdout, dry.stdout,
                         "recon must be propose --dry-run, byte for byte")

    # ------------------------------------------------------------------- refusals

    def test_a_skill_already_in_the_upstream_tree_is_refused(self):
        self.canned_tree(["skills/other/SKILL.md", "skills/demo-skill/SKILL.md"])
        (self.canned / "contents.md").write_text("---\nname: demo-skill\n---\n")
        before = self.refs(self.fork)
        r = self.propose()
        self.assertEqual(r.returncode, 9, r.stdout[-2000:])
        self.assertIn("ALREADY UPSTREAM", r.stdout)
        self.assertEqual(before, self.refs(self.fork))
        self.assertEqual(self.writes_called(), [])

    def test_a_skill_already_in_the_clone_is_refused_before_the_push(self):
        # The tree probe reads one commit of the default branch through an API. The
        # clone is the ground truth, and it can disagree: a fork that is ahead, a
        # listing that was truncated, a race. Overwriting there is how a contribution
        # silently replaces someone's work.
        self.upstream = self.build_bare("upstream2.git",
                                        ["skills/other/SKILL.md", "skills/demo-skill/SKILL.md"])
        self.fork = self.clone_bare("fork2.git", self.upstream)
        r = self.propose()
        self.assertEqual(r.returncode, 9, r.stdout[-2000:] + r.stderr[-1000:])
        self.assertIn("already exists", r.stderr)
        self.assertNotIn("refs/heads/skill/demo-skill", self.refs(self.fork))
        self.assertEqual(self.ledger_rows(), [])

    def test_an_open_proposal_upstream_stops_the_run(self):
        self.canned_prs([{"number": 12, "title": "Add demo-skill skill", "state": "OPEN",
                          "url": "https://github.com/acme/pool/pull/12",
                          "headRefName": "skill/demo-skill",
                          "files": [{"path": "skills/demo-skill/SKILL.md",
                                     "additions": 90, "deletions": 0}]}])
        r = self.propose()
        self.assertEqual(r.returncode, 4, r.stdout[-2000:])
        self.assertEqual(self.writes_called(), [])
        self.assertEqual(self.ledger_rows(), [])

    def test_a_missing_skill_is_refused_before_any_lookup(self):
        r = subprocess.run([str(SCRIPT), "propose", "no-such-skill", "--upstream", "acme/pool"],
                           capture_output=True, text=True, env=self.env(),
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, 10, r.stdout + r.stderr)
        self.assertEqual(self.gh_calls(), [],
                         "nothing should reach gh before the skill is even found")

    def test_the_parse_check_refuses_broken_frontmatter_before_any_lookup(self):
        self.write_skill(text='---\nname: demo-skill\ndescription: "unterminated\n---\n\n# B\n')
        r = self.propose()
        self.assertEqual(r.returncode, 12, r.stdout + r.stderr)
        self.assertIn("does not parse as YAML", r.stderr)
        self.assertEqual(self.gh_calls(), [])
        self.assertEqual(self.ledger_rows(), [])

    def test_a_skill_with_no_trigger_precision_section_is_refused(self):
        self.write_skill(text=('---\nname: demo-skill\ndescription: "Use when demoing. '
                               'Do NOT use otherwise."\n---\n\n# Demo\n\nA body.\n'))
        r = self.propose()
        self.assertEqual(r.returncode, 20, r.stdout + r.stderr)
        self.assertIn("Trigger precision", r.stderr)
        self.assertEqual(self.gh_calls(), [])

    def test_a_trigger_section_with_no_pin_is_refused(self):
        self.write_skill(text=('---\nname: demo-skill\ndescription: "Use when demoing. '
                               'Do NOT use otherwise."\n---\n\n# Demo\n\n'
                               '## Trigger precision\n\nProsp that MUST fire:\n\n1. "demo"\n'))
        r = self.propose()
        self.assertEqual(r.returncode, 21, r.stdout + r.stderr)
        self.assertEqual(self.gh_calls(), [])

    def test_an_unmeasured_routing_pin_is_refused_and_the_flag_lifts_it(self):
        self.write_skill(measured="never", result="unmeasured")
        r = self.propose()
        self.assertEqual(r.returncode, 22, r.stdout + r.stderr)
        self.assertIn("unmeasured", r.stderr)
        self.assertEqual(self.gh_calls(), [])

        ok = self.propose("--allow-unmeasured")
        self.assertEqual(ok.returncode, 0, ok.stdout[-3000:] + ok.stderr[-2000:])
        self.assertIn("UNMEASURED", ok.stdout)
        self.assertIn("refs/heads/skill/demo-skill", self.refs(self.fork))

    def test_an_installed_symlink_is_resolved_to_the_directory_it_names(self):
        """The installed path is almost always a symlink into a checkout.

        `~/.claude/skills/<name>` is what the installer creates, and the files that must
        travel with SKILL.md live at the other end of it. Copying the link's own
        directory finds only SKILL.md if it finds anything at all.
        """
        real = self.root / "checkout" / "skills" / "demo-skill"
        real.mkdir(parents=True)
        installed = self.home / ".claude" / "skills" / "demo-skill"
        for f in installed.iterdir():
            if f.is_dir():
                (real / f.name).mkdir()
                for g in f.iterdir():
                    (real / f.name / g.name).write_text(g.read_text())
            else:
                (real / f.name).write_text(f.read_text())
        shutil.rmtree(installed)
        installed.symlink_to(real)

        r = self.propose()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertIn("skill directory: %s" % real.resolve(), r.stdout,
                      "the path printed must be the checkout, not the link")
        listed = subprocess.run(
            ["git", "--git-dir", str(self.fork), "ls-tree", "-r", "--name-only",
             "skill/demo-skill"], capture_output=True, text=True,
            stdin=subprocess.DEVNULL).stdout
        self.assertIn("skills/demo-skill/scripts/run.sh", listed,
                      "following the symlink is what carries the rest of the directory")

    def test_a_project_level_skill_is_found_when_nothing_is_installed(self):
        # Level A: ./.claude/skills/<name>, for a skill that belongs to one repository.
        shutil.rmtree(self.home / ".claude" / "skills" / "demo-skill")
        project = self.root / "project"
        (project / ".claude" / "skills").mkdir(parents=True)
        d = project / ".claude" / "skills" / "demo-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(PINNED % {
            "measured": "2026-09-01",
            "result": "verified 9/9 must-fire draws, 9/9 must-not-fire draws"})
        r = subprocess.run([str(SCRIPT), "propose", "demo-skill", "--upstream", "acme/pool"],
                           capture_output=True, text=True, env=self.env(),
                           stdin=subprocess.DEVNULL, timeout=120, cwd=str(project))
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertIn("refs/heads/skill/demo-skill", self.refs(self.fork))

    def test_an_archived_upstream_stops_before_any_write(self):
        r = self.propose(FAKEGH_ARCHIVED="true")
        self.assertEqual(r.returncode, 18, r.stdout[-2000:] + r.stderr[-1000:])
        self.assertEqual(self.writes_called(), [])

    def test_an_existing_fork_is_reused_rather_than_created_again(self):
        (self.canned / "fork-exists").write_text("")
        r = self.propose()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertEqual([c for c in self.gh_calls() if c.startswith("repo fork")], [])
        self.assertIn("already exists and is reused", r.stdout)
        self.assertEqual(len(self.write_lines(r.stdout)), 2,
                         "with no fork to create there are two writes, not three")


class WriteSurfaceTest(unittest.TestCase):
    """Which commands in this CLI can write, and where those writes live in the file.

    Until `propose` landed the answer was "none", and one test asserted the strings were
    absent from the whole script. That test cannot survive the feature, so this replaces
    it with the two claims that still hold: every OTHER subcommand writes nothing (driven
    for real against the offline harness), and every write in the file is inside
    `cmd_propose`.
    """

    def test_only_cmd_propose_contains_an_executable_network_write(self):
        text = SCRIPT.read_text()
        start = text.index("cmd_propose() {")
        end = text.index("\ncmd=\"${1:-}\"")
        for pattern in ('"$GH" repo fork', '"$GH" pr create', 'push --quiet -u origin'):
            spots = [m.start() for m in re.finditer(re.escape(pattern), text)]
            self.assertTrue(spots, "%r is not in the script at all" % pattern)
            for spot in spots:
                line_start = text.rfind("\n", 0, spot) + 1
                if text[line_start:spot].lstrip().startswith("#"):
                    continue
                self.assertTrue(start < spot < end,
                                "%r is executed outside cmd_propose (offset %d)"
                                % (pattern, spot))

    def test_the_read_only_subcommands_reach_no_write(self):
        """Driven, not read: the real subcommands against the real shim."""
        case = OfflineProposeTest("test_the_dry_run_writes_nothing_anywhere")
        case.setUp()
        try:
            before = case.refs(case.fork)
            for argv in (["dedup", "demo-skill", "--repo", "acme/pool"],
                         ["whoami", "--repo", "acme/pool"],
                         ["preflight", str(case.home / ".claude" / "skills" / "demo-skill")],
                         ["recon", "demo-skill", "--upstream", "acme/pool"]):
                r = subprocess.run([str(SCRIPT), *argv], capture_output=True, text=True,
                                   env=case.env(), stdin=subprocess.DEVNULL, timeout=120)
                self.assertEqual(r.returncode, 0, "%s: %s%s" % (argv, r.stdout, r.stderr))
            self.assertEqual(case.writes_called(), [], case.gh_calls())
            self.assertEqual(before, case.refs(case.fork))
            self.assertEqual(case.ledger_rows(), [])
        finally:
            case.tearDown()

    def test_help_exits_zero_and_lists_every_subcommand(self):
        r = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        for cmd in ("skillcontrib dedup", "skillcontrib whoami", "skillcontrib preflight",
                    "skillcontrib recon", "skillcontrib propose"):
            self.assertIn(cmd, r.stdout)

    def test_help_says_running_propose_is_the_consent(self):
        r = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertIn("RUNNING THIS WITHOUT --dry-run IS THE", r.stdout)

    def test_help_warns_about_the_default_repo(self):
        r = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertIn("Pass it explicitly", r.stdout)

    def test_unknown_command_is_a_usage_error(self):
        r = subprocess.run([str(SCRIPT), "frobnicate"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown command", r.stderr)

    def test_dedup_without_a_name_is_a_usage_error(self):
        r = subprocess.run([str(SCRIPT), "dedup"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_propose_without_a_name_is_a_usage_error(self):
        r = subprocess.run([str(SCRIPT), "propose"], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 2)
        self.assertIn("propose <skill-name>", r.stderr)


@unittest.skipUnless(LIVE, "gh is missing or unauthenticated; live GitHub reads skipped")
class LiveDedupTest(unittest.TestCase):
    """Real calls against real repos with real history.

    These inherit the ambient environment on purpose: gh needs its own config and
    credentials, and pointing HOME at a temp dir would only test the unauthenticated
    path. anthropics/skills supplies shipped skills, an open proposal, and declined
    ones; anthropics/claude-code supplies the nested plugins/<x>/skills/<x>/ layout;
    cli/cli supplies thousands of pull requests in every state.
    """

    ROW = re.compile(r"^(proposal|touch|mention|fuzzy)\s+(OPEN|CLOSED|MERGED)\s")

    def dedup(self, *args, **kw):
        repo = kw.pop("repo", LIVE_REPO)
        return subprocess.run([str(SCRIPT), "dedup"] + list(args) + ["--repo", repo],
                              capture_output=True, text=True)

    def rows(self, stdout):
        return [ln.split() for ln in stdout.splitlines() if self.ROW.match(ln)]

    # ------------------------------------------- tree probe: normalisation and depth

    def test_a_skill_that_already_ships_upstream_is_not_clean(self):
        r = self.dedup("internal-comms", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 9, r.stdout[-800:])
        self.assertIn("ALREADY UPSTREAM", r.stdout)
        self.assertNotIn("CLEAN", r.stdout)

    def test_case_and_separator_variants_do_not_defeat_the_tree_probe(self):
        # skills/internal-comms/ ships upstream. Each of these returned 0 or 3 before.
        for variant in ("internal_comms", "Internal-Comms", "INTERNALCOMMS", "internalcomms"):
            r = self.dedup(variant, repo=SKILLS_REPO)
            self.assertEqual(r.returncode, 9,
                             "%r slipped past the tree probe (rc=%d)" % (variant, r.returncode))

    def test_nested_plugin_layouts_are_found(self):
        # plugins/<plugin>/skills/<skill>/SKILL.md is a real layout in a real Anthropic
        # repo, and a skills/<name>/ lookup never sees it.
        for nested in ("frontend-design", "plugin-settings", "mcp-integration", "writing-rules"):
            r = self.dedup(nested, repo=NESTED_REPO)
            self.assertEqual(r.returncode, 9,
                             "%r not found in the nested layout (rc=%d)" % (nested, r.returncode))
            self.assertRegex(r.stdout, r"ALREADY UPSTREAM: \S+/%s/SKILL\.md" % nested)

    def test_the_tree_probe_reads_the_upstream_name_frontmatter(self):
        r = self.dedup("internal-comms", repo=SKILLS_REPO)
        self.assertIn("frontmatter declares name: internal-comms", r.stdout)

    def test_a_name_absent_from_the_tree_is_not_reported_as_upstream(self):
        r = self.dedup("zzqqx-nonexistent-skill-name", repo=NESTED_REPO)
        self.assertEqual(r.returncode, 0, r.stdout[-800:])
        self.assertIn("CLEAN", r.stdout)

    # ------------------------------------------------- proposal versus mere mention

    def test_a_closed_proposal_still_blocks_with_code_5(self):
        # anthropics/skills#1407 added skills/macho/SKILL.md and was closed unmerged.
        r = self.dedup("macho", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 5, r.stdout[-800:])
        self.assertIn("BLOCKED", r.stdout)
        self.assertIn("proposal", {row[0] for row in self.rows(r.stdout)})

    def test_a_closed_proposal_is_not_called_a_rejection(self):
        # It is as often a superseded revision, and the difference is not machine-readable.
        r = self.dedup("macho", repo=SKILLS_REPO)
        self.assertNotIn("declined", r.stdout)
        self.assertIn("superseded", r.stdout)

    def test_a_typo_fix_is_not_reported_as_a_rejection(self):
        r = self.dedup("canvas-design", repo=SKILLS_REPO)
        self.assertNotIn("BLOCKED", r.stdout)
        self.assertNotEqual(r.returncode, 5)

    def test_closed_pull_requests_that_only_touch_the_name_do_not_block(self):
        # cli/cli has 14 CLOSED pull requests touching paths under an `extension`
        # directory and none of them proposes a skill. Treating any of those as a
        # rejection is what trains reflexive use of --override-rejected.
        r = self.dedup("extension")
        self.assertEqual(r.returncode, 3, r.stdout[-800:])
        self.assertIn("ASK THE USER", r.stdout)
        self.assertNotIn("BLOCKED", r.stdout)
        kinds = {row[0] for row in self.rows(r.stdout)}
        self.assertNotIn("proposal", kinds)
        states = {row[1] for row in self.rows(r.stdout)}
        self.assertIn("CLOSED", states, "the fixture must include closed pull requests")

    def test_a_proposal_at_any_depth_is_still_a_proposal(self):
        # anthropics/skills#1036 adds skills/skills/designlang/SKILL.md. The old
        # path-exact matcher called that a mere title mention.
        r = self.dedup("designlang", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 4, r.stdout[-800:])
        self.assertIn("proposal", {row[0] for row in self.rows(r.stdout)})

    def test_an_open_proposal_stops_with_code_4(self):
        r = self.dedup("presentation-chef", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 4, r.stdout[-800:])
        self.assertIn("STOP", r.stdout)

    def test_override_rejected_downgrades_the_block(self):
        r = self.dedup("macho", "--override-rejected", repo=SKILLS_REPO)
        self.assertIn(r.returncode, (3, 4), r.stdout[-800:])
        self.assertIn("OVERRIDE", r.stdout)

    # -------------------------------------------------------------- repo-level stops

    def test_an_archived_upstream_gets_its_own_exit_code(self):
        r = self.dedup("anything", repo="google/tink")
        self.assertEqual(r.returncode, 18, r.stdout + r.stderr)
        self.assertIn("archived", r.stderr)

    def test_unknown_repo_fails_loudly_rather_than_looking_clean(self):
        r = self.dedup("anything", repo="ContextLab/no-such-repo-zzqqx")
        self.assertEqual(r.returncode, 8, r.stdout + r.stderr)
        self.assertIn("could not resolve", r.stderr)

    def test_a_truncated_tree_listing_is_not_reported_as_clean(self):
        # torvalds/linux has ~72k paths, past the tree API's cap. Reporting rc 0 there
        # would be a clean result the probe cannot actually support.
        r = self.dedup("zzqqx-nonexistent-skill-name", repo="torvalds/linux")
        self.assertEqual(r.returncode, 19, r.stdout[-800:])
        self.assertIn("INCOMPLETE", r.stdout, "the caveat must be on stdout, not only stderr")
        self.assertIn("NOT CERTIFIED CLEAN", r.stdout)
        self.assertNotIn("CLEAN: no duplicate found", r.stdout)

    def test_a_clean_result_reports_the_upstream_layout(self):
        # Section 5a says to use the layout the tree probe found, which is unfollowable
        # if a clean result prints no layout.
        r = self.dedup("zzqqx-nonexistent-skill-name", repo=SKILLS_REPO)
        self.assertEqual(r.returncode, 0, r.stdout[-800:])
        self.assertIn("upstream keeps skills under:", r.stdout)

    def test_a_nested_repo_reports_its_nested_layout(self):
        r = self.dedup("zzqqx-nonexistent-skill-name", repo=NESTED_REPO)
        self.assertRegex(r.stdout, r"upstream keeps skills under: plugins/\S+/skills")

    def test_the_target_repo_is_printed(self):
        r = self.dedup("zzqqx-nonexistent-skill-name")
        self.assertIn("repo:        %s" % LIVE_REPO, r.stdout)
        self.assertIn("pass --repo", r.stdout)

    # ----------------------------------------------------------------- state coverage

    def test_state_all_sweep_returns_merged_and_closed(self):
        r = self.dedup("extension")  # thousands of pull requests in every state
        states = {row[1] for row in self.rows(r.stdout)}
        self.assertIn("MERGED", states, r.stdout[:2000])
        self.assertIn("CLOSED", states, r.stdout[:2000])

    def test_fuzzy_only_match_asks_the_user_with_code_3(self):
        r = self.dedup("zzqqx-nonexistent-skill-name", "--description",
                       "codespaces machine listing alongside repository visibility settings")
        self.assertEqual(r.returncode, 3, r.stdout[-800:])
        self.assertIn("ASK THE USER", r.stdout)
        self.assertEqual({row[0] for row in self.rows(r.stdout)}, {"fuzzy"})

    def test_sub_threshold_rows_are_shown_not_hidden(self):
        r = self.dedup("zzqqx-nonexistent-skill-name", "--description",
                       "codespaces machine listing alongside repository visibility settings")
        self.assertIn("below", {row[3] for row in self.rows(r.stdout)},
                      "sub-threshold fuzzy hits must still be printed")
        self.assertIn("shown but not counted", r.stdout)

    def test_no_match_is_clean(self):
        r = self.dedup("zzqqx-nonexistent-skill-name")
        self.assertEqual(r.returncode, 0, r.stdout[-800:])
        self.assertIn("CLEAN", r.stdout)

    def test_search_index_lag_is_disclosed(self):
        r = self.dedup("zzqqx-nonexistent-skill-name")
        self.assertIn("search index lags", r.stdout)


@unittest.skipUnless(LIVE, "gh is missing or unauthenticated; live GitHub reads skipped")
class LiveWhoamiTest(unittest.TestCase):

    def whoami(self, repo=LIVE_REPO):
        return subprocess.run([str(SCRIPT), "whoami", "--repo", repo],
                              capture_output=True, text=True)

    def test_reports_a_role_and_an_identity(self):
        r = self.whoami()
        self.assertEqual(r.returncode, 0, r.stderr)
        role = re.search(r"^role:\s+(\w+)$", r.stdout, re.M).group(1)
        self.assertIn(role, ("maintainer", "contributor"))
        self.assertRegex(r.stdout, re.compile(r"^acting as:\s+\S+$", re.M))
        self.assertRegex(r.stdout, re.compile(r"^archived:\s+(true|false)$", re.M))

    def test_permission_level_is_reported_not_just_collaborator_status(self):
        # The bare collaborators/<user> endpoint answers 204 for read-only collaborators
        # too, which would wrongly read as maintainer. The permission level is the answer.
        r = self.whoami()
        self.assertRegex(r.stdout, re.compile(r"^permission: \S+", re.M))
        self.assertNotIn("Must have push access", r.stdout)

    def test_the_identity_that_actually_pushes_is_reported(self):
        # gh's account and git's credential helper can be different accounts, and the
        # second one is what the commits land under. Nothing else surfaces it.
        r = self.whoami()
        self.assertRegex(r.stdout, re.compile(r"^push identity: ", re.M))

    def test_a_repo_the_user_cannot_push_to_takes_the_fork_path(self):
        r = self.whoami()
        self.assertIn("fork the repo", r.stdout)

    def test_archived_upstream_exits_18(self):
        r = self.whoami("google/tink")
        self.assertEqual(r.returncode, 18, r.stdout + r.stderr)
        self.assertIn("archived:  true", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
