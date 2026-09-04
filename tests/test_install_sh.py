#!/usr/bin/env python3
"""`install.sh --ref / --update / --rollback`, against a real origin, with no network.

Issue #38 asked for "a test [that] installs a tag into a temp config, upgrades to a later
tag, rolls back, and asserts the tree matches the first tag". Nothing here did: every other
installer test drives `scripts/setup.py` directly, so the clone/fetch/checkout logic those
three flags live in had no coverage at all except the manual runbook in `docs/releasing.md`,
which needs the network and two real tags.

NOTHING IS MOCKED. The origin is a real bare repository this file builds in a temp
directory: a work clone whose tree is this checkout at HEAD (`git archive HEAD`), committed
and tagged `v0.1`, then a second commit adding a visible marker file and tagged `v0.2`, both
pushed. `install.sh` is aimed at it with `SKILL_COMPOUNDER_REPO_URL`, and driven with
`--claude-dir/--bin-dir/--state-dir`, `CLAUDE_SKILL_COMPOUNDER_APP` and `HOME` all under the
temp tree, so nothing here can reach a real config.

Three choices worth knowing before editing this file:

* **The origin URL is a `file://` one on purpose.** Handed a bare path, git does a LOCAL
  clone and silently ignores `--depth 1`, which would leave the shallow single-branch shape
  untested -- and that shape is the whole reason `fetch_ref` spells its refspecs out. The
  first version of `--update` reported "could not fetch" for a ref sitting on the remote
  precisely there.
* **`install.sh` is overlaid from the working tree**, while the rest of the tree comes from
  HEAD. It is the file under test, and `<managed>/install.sh --update` runs the copy inside
  the checkout: taking that one from HEAD would test the last commit rather than the edit in
  hand, which is the failure mode the c9803bc case below exists to catch.
* **Assertions are on exit codes and `git rev-parse`**, never on prose -- with two
  exceptions, the two refusal messages a user is meant to read and act on.

Runtime is about ten seconds: five clones (four of them install.sh's own) and eleven
`scripts/setup.py` runs, measured at 9.7s on macOS with the origin built once per class.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATH_BASE = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
TIMEOUT = 120

# A git that cannot read the machine's config, cannot prompt, and has an identity of its
# own, so building the origin does not depend on the ambient environment.
GIT_ENV = {
    "GIT_AUTHOR_NAME": "install.sh test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "install.sh test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}

MARKER = "RELEASE-MARKER"   # present at v0.2, absent at v0.1


def run(argv, env, timeout=TIMEOUT):
    """Every call is bounded and captured; a hook or CLI reading stdin must not block."""
    return subprocess.run(argv, env=env, timeout=timeout, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL)


def where(r):
    return "rc=%s\n--- stdout ---\n%s--- stderr ---\n%s" % (r.returncode, r.stdout, r.stderr)


class RefHandlingTest(unittest.TestCase):
    """One origin, built once; a fresh sandbox and a fresh managed checkout per test."""

    # ------------------------------------------------------------------ the origin

    @classmethod
    def setUpClass(cls):
        cls._shared = tempfile.TemporaryDirectory()
        shared = Path(cls._shared.name)
        home = shared / "home"
        home.mkdir()
        cls.git_env = dict(GIT_ENV, PATH=PATH_BASE, HOME=str(home))

        origin = shared / "origin.git"
        cls.git("-c", "init.defaultBranch=main", "init", "--quiet", "--bare", str(origin))

        # This checkout's tree at HEAD, which is what makes the fake package real enough
        # for install.sh and scripts/setup.py to run against it.
        tar = shared / "head.tar"
        cls.git("-C", str(REPO), "archive", "--format=tar", "-o", str(tar), "HEAD")
        work = shared / "work"
        work.mkdir()
        r = run(["tar", "-xf", str(tar), "-C", str(work)], cls.git_env)
        assert r.returncode == 0, where(r)
        shutil.copy2(str(REPO / "install.sh"), str(work / "install.sh"))

        cls.git("-c", "init.defaultBranch=main", "init", "--quiet", str(work))
        cls.git("-C", str(work), "remote", "add", "origin", str(origin))
        cls.git("-C", str(work), "add", "-A")
        cls.git("-C", str(work), "commit", "--quiet", "-m", "v0.1")
        cls.git("-C", str(work), "tag", "v0.1")
        (work / MARKER).write_text("v0.2\n", encoding="utf-8")
        cls.git("-C", str(work), "add", "-A")
        cls.git("-C", str(work), "commit", "--quiet", "-m", "v0.2")
        cls.git("-C", str(work), "tag", "v0.2")
        cls.git("-C", str(work), "push", "--quiet", "origin", "main", "v0.1", "v0.2")

        cls.sha1 = cls.git("-C", str(work), "rev-parse", "v0.1^{commit}").stdout.strip()
        cls.sha2 = cls.git("-C", str(work), "rev-parse", "v0.2^{commit}").stdout.strip()
        assert cls.sha1 != cls.sha2
        # `file://` and not a bare path: see the module docstring.
        cls.origin_url = "file://" + str(origin)

    @classmethod
    def tearDownClass(cls):
        cls._shared.cleanup()

    @classmethod
    def git(cls, *args):
        r = run(["git", *args], cls.git_env)
        assert r.returncode == 0, "git %s\n%s" % (" ".join(args), where(r))
        return r

    # ------------------------------------------------------------------ per-test sandbox

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.claude = self.root / "claude"
        self.bin = self.root / "bin"
        for d in (self.home, self.claude, self.bin):
            d.mkdir()
        self.state = self.root / "state"
        self.app = self.root / "app"          # where install.sh will clone
        self.settings = self.claude / "settings.json"

        # The `curl … | bash` shape: a copy of install.sh with no checkout beside it, so
        # the script clones instead of installing whatever tree it happens to sit in.
        self.standalone = self.root / "install.sh"
        shutil.copy2(str(REPO / "install.sh"), str(self.standalone))

    def tearDown(self):
        self._tmp.cleanup()

    def env(self):
        return dict(GIT_ENV,
                    PATH=PATH_BASE,
                    HOME=str(self.home),
                    CLAUDE_SKILL_COMPOUNDER_APP=str(self.app),
                    CLAUDE_SKILL_COMPOUNDER_STATE=str(self.state),
                    SKILL_COMPOUNDER_REPO_URL=self.origin_url,
                    # The install step that clones history-surfer is a real network
                    # clone; this suite tests install.sh's pin and rollback, not that.
                    SKILL_COMPOUNDER_NO_SURFER="1")

    def dirs(self):
        return ["--claude-dir", str(self.claude),
                "--bin-dir", str(self.bin),
                "--state-dir", str(self.state)]

    def install(self, script, *args, expect=0):
        r = run(["bash", str(script), *args, *self.dirs()], self.env())
        if expect is not None:
            self.assertEqual(r.returncode, expect, where(r))
        return r

    # ------------------------------------------------------------------ observations

    def head(self, repo=None):
        return self.git("-C", str(repo or self.app), "rev-parse", "HEAD").stdout.strip()

    def described(self):
        return self.git("-C", str(self.app),
                        "describe", "--tags", "--exact-match", "HEAD").stdout.strip()

    def record(self):
        """`<state>/install-ref` as {"current": (ref, sha), "previous": (ref, sha)}."""
        out = {}
        for line in (self.state / "install-ref").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts and parts[0] in ("current", "previous"):
                out[parts[0]] = tuple(parts[1:3])
        return out

    # ------------------------------------------------------------------ the acceptance

    def test_pinned_install_then_update_then_rollback_and_back(self):
        """Issue #38's acceptance, plus what a SECOND --rollback actually does."""
        self.install(self.standalone, "--ref", "v0.1")
        self.assertEqual(self.described(), "v0.1")
        self.assertEqual(self.head(), self.sha1)
        self.assertFalse((self.app / MARKER).exists())
        self.assertEqual(self.record()["current"], ("v0.1", self.sha1))
        self.assertNotIn("previous", self.record(),
                         "a fresh install has nowhere to roll back to and must say so")

        # A plain re-run re-wires the checkout and must not move it.
        self.install(self.standalone)
        self.assertEqual(self.head(), self.sha1, "a plain re-run moved the checkout")
        self.assertEqual(self.record()["current"], ("v0.1", self.sha1))
        self.assertNotIn("previous", self.record(),
                         "a re-run invented a rollback target out of nothing")

        # --update moves it and records where it came from.
        self.install(self.standalone, "--update", "--ref", "v0.2")
        self.assertEqual(self.head(), self.sha2)
        self.assertEqual(self.described(), "v0.2")
        self.assertTrue((self.app / MARKER).exists())
        self.assertEqual(self.record()["current"], ("v0.2", self.sha2))
        self.assertEqual(self.record()["previous"], ("v0.1", self.sha1))

        # --rollback returns the tree to the first tag and swaps the record.
        self.install(self.standalone, "--rollback")
        self.assertEqual(self.head(), self.sha1, "the tree did not return to v0.1")
        self.assertEqual(self.described(), "v0.1")
        self.assertFalse((self.app / MARKER).exists(),
                         "HEAD moved but the working tree still holds v0.2's file")
        self.assertEqual(self.record()["current"], ("v0.1", self.sha1))
        self.assertEqual(self.record()["previous"], ("v0.2", self.sha2))

        # A second --rollback is not refused and is not a no-op: the record holds exactly
        # one previous ref, and the first rollback wrote v0.2 into it, so rolling back
        # again goes FORWARD. Two of them toggle. Recorded here because it is the
        # behaviour, not because it is the obvious reading of the word.
        self.install(self.standalone, "--rollback")
        self.assertEqual(self.head(), self.sha2)
        self.assertTrue((self.app / MARKER).exists())
        self.assertEqual(self.record()["current"], ("v0.2", self.sha2))
        self.assertEqual(self.record()["previous"], ("v0.1", self.sha1))

    def test_the_copy_inside_the_managed_checkout_moves_it_too(self):
        """Before c9803bc this exited 0, printed "Installed", and moved nothing.

        The gate recognised only the `curl | bash` case (no checkout beside the script),
        so `<managed>/install.sh --update` fell through as "your own clone, re-wiring it"
        -- which is what a user upgrading from their installed copy would run.
        """
        self.install(self.standalone, "--ref", "v0.1")
        managed = self.app / "install.sh"
        self.assertTrue(managed.is_file())

        self.install(managed, "--update", "--ref", "v0.2")
        self.assertEqual(self.head(), self.sha2,
                         "the managed checkout's own copy did not move the checkout")
        self.assertEqual(self.record()["previous"], ("v0.1", self.sha1))

        self.install(managed, "--rollback")
        self.assertEqual(self.head(), self.sha1)
        self.assertEqual(self.record()["current"], ("v0.1", self.sha1))

    def test_a_managed_checkout_with_local_changes_is_refused(self):
        """Exit 3 and the message by name, with nothing moved and nothing recorded.

        `checkout_ref` returning 2 used to take the shell out on the spot under `set -e`
        (`checkout_ref "$REF"; cr=$?`), so this exited 2 and the branch reading `cr` was
        dead code. The message printed anyway, by luck -- `checkout_ref` echoes before it
        returns -- which is why only the code pins the defect.
        """
        self.install(self.standalone, "--ref", "v0.1")
        with open(str(self.app / "README.md"), "a", encoding="utf-8") as fh:
            fh.write("\na local edit nobody made on purpose\n")

        r = self.install(self.standalone, "--update", "--ref", "v0.2", expect=3)
        self.assertIn("has local changes", r.stderr, where(r))
        self.assertEqual(self.head(), self.sha1, "a refused update moved the checkout")
        self.assertEqual(self.record()["current"], ("v0.1", self.sha1))
        self.assertNotIn("previous", self.record(),
                         "a refused update rotated the rollback record")

    def test_a_users_own_clone_is_refused_and_left_where_it_is(self):
        """--update/--rollback manage the checkout install.sh made, and nothing else."""
        mine = self.root / "mine"
        self.git("clone", "--quiet", self.origin_url, str(mine))
        before = self.head(mine)

        for flags in (["--update", "--ref", "v0.1"], ["--rollback"]):
            with self.subTest(flags=" ".join(flags)):
                r = self.install(mine / "install.sh", *flags, expect=2)
                self.assertIn("only manage the checkout install.sh made at", r.stderr,
                              where(r))
                self.assertEqual(self.head(mine), before,
                                 "a refusal still moved the user's own clone")
        self.assertFalse(self.app.exists(), "a refusal cloned a managed checkout anyway")

    def test_uninstall_gives_the_settings_file_back_byte_for_byte(self):
        pre = json.dumps({"model": "opus"}, indent=2) + "\n"
        self.settings.write_text(pre, encoding="utf-8")

        self.install(self.standalone, "--ref", "v0.1")
        self.assertIn("hooks", json.loads(self.settings.read_text(encoding="utf-8")),
                      "the install wrote nothing, so the comparison below is vacuous")

        r = run(["bash", str(self.app / "uninstall.sh"), *self.dirs()], self.env())
        self.assertEqual(r.returncode, 0, where(r))
        self.assertEqual(self.settings.read_bytes(), pre.encode("utf-8"),
                         "uninstall did not give settings.json back unchanged")


if __name__ == "__main__":
    unittest.main(verbosity=2)
