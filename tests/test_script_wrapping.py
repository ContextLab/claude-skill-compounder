#!/usr/bin/env python3
"""Every shipped script must survive being rewritten while it is running.

bash reads a script LAZILY, by byte offset, and resumes at that offset in whatever the
file contains AT THAT MOMENT. Every file in this package is executed by absolute path
out of the checkout -- the installer writes those paths into `settings.json` and
symlinks the CLIs -- so a `git pull`, a `git checkout` or one `sed -i` rewrites the
bytes of a run already in flight. That is not hypothetical: it cost a real, paid-for
`claude -p` dispatch on 2026-08-25 (docs/DESIGN.md, "Never edit a script that may still
be running", and notes/2026-08-25-first-live-review-verdict.md).

The fix has two halves and this file tests both, with real processes and real rewrites:

  (a) the whole body sits in one brace group, so bash must find the matching `}` before
      it may run any of it and the file goes through the parser in ONE pass;
  (b) the last statement inside the group is an `exit`, because a brace group protects
      its body and nothing past it.

RewriteUnderLoadTest drives the real `hooks/insight-capture.sh`, blocks it mid-run,
rewrites the file underneath it, and compares the run against an unrewritten baseline.
Its control -- the same script with only the brace group removed -- must be corrupted by
the same treatment, which is what keeps the passing case from being vacuous.

WrappingInvariantTest is the cheap static half: it reads every shipped script and
asserts the two halves are actually present.

NOTHING HERE IS MOCKED. The blocking point is a real `date` process the real script
really forks; the shim logs its argv, blocks on a real FIFO until this test releases it,
and then `exec`s the real `/bin/date`, so the script's own behaviour is unchanged apart
from taking longer -- which is exactly the shape of the incident.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATH_BASE = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
TIMEOUT = 60
NOW = "1755993600"        # 2025-08-24T00:00:00Z, ISO week 2025-W34

# Scripts that MUST carry both halves. These are the ones whose window times rate makes
# the collision a matter of when: the hooks and the status line are invoked by absolute
# path into the checkout on every turn and once a second respectively, and
# session-review.sh blocks for a minute inside `claude -p`.
REQUIRE_WRAPPED = (
    "hooks/session-review.sh",
    "hooks/insight-capture.sh",
    "hooks/compound-improvement.sh",
    "statusline/statusline.sh",
    "statusline/skillforge-status.sh",
    # The CLIs are symlinked into the user's bin directory and run out of this checkout,
    # so the same `git pull` that rewrites a hook rewrites these. `skillcontrib` is the
    # one with the incident's exact shape -- it blocks on serial `gh` calls against the
    # network, so its window is seconds long and set by someone else's latency.
    "bin/skillcontrib",
    "bin/skillforge",
    "bin/skillreport",
    "bin/skillinsight",
)

# Shipped scripts that are NOT wrapped, each with the reason it is tolerated. EMPTY as of
# 2026-08-26: every shipped script is wrapped, so `test_every_shipped_script_is_wrapped_or_listed`
# now covers all of them with nothing excused. Keep the set -- it is the ratchet, not an
# amnesty: a NEW script must either be wrapped or be added here on purpose, and every entry
# must still exist, so it cannot rot quietly. Anything added here needs a written reason and
# should be deleted the moment its script is wrapped.
KNOWN_UNWRAPPED = set()


# ---------------------------------------------------------------------------- $HOME
# A second way the same class of script dies before it prints anything: `$HOME` is not
# guaranteed to be set (cron, a stripped env, a container, a status line spawned from a
# sanitised environment), and under `set -u` expanding an unset HOME aborts the script
# non-zero. For a hook that breaks the one promise a hook has to keep; for the status
# line the segment silently goes blank, with the error going nowhere anyone will read.
# Every script here that expands `$HOME` must therefore default it first, with
#     : "${HOME:=/tmp}"
# placed above the first expansion.
#
# Same ratchet discipline as KNOWN_UNWRAPPED: an entry needs a written reason, and
# `test_the_home_ratchet_cannot_rot` deletes-or-fails it once the script is fixed.
HOME_UNGUARDED = {
    # Empty since 2026-08-26. statusline/statusline.sh was the last entry: with HOME and
    # SKILL_COMPOUNDER_STATE both unset it aborted on its STATE= line before printing a
    # byte, taking the user's own base status line down with ours. Fixed and verified by
    # running it with HOME removed from the environment (rc 0, empty stderr). An entry
    # here is a live defect somebody deferred, never an exemption -- add one only with the
    # reason and the owner, and delete it the moment the guard lands.
}

GUARD = ': "${HOME:=/tmp}"'


def first_home_expansion(text):
    """Line number (1-based) of the first `$HOME` outside a comment, or None.

    Comment lines are skipped because several scripts document the state paths they
    read in their own `--help` header, and documenting `$HOME` expands nothing. The
    guard itself writes `${HOME:=...}`, which does not contain the substring `$HOME`,
    so it never matches here.
    """
    for i, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith("#"):
            continue
        if "$HOME" in line:
            return i
    return None


def home_guard_line(text):
    for i, line in enumerate(text.split("\n"), 1):
        if line.strip() == GUARD:
            return i
    return None


def shipped_scripts():
    """Every shell script the installer wires or symlinks, as repo-relative paths."""
    out = []
    for d in ("hooks", "statusline", "bin"):
        for p in sorted((REPO / d).iterdir()):
            if not p.is_file():
                continue
            head = p.read_bytes()[:64]
            if head.startswith(b"#!") and (b"bash" in head.split(b"\n")[0]
                                           or b"/sh" in head.split(b"\n")[0]):
                out.append(p.relative_to(REPO).as_posix())
    return out


def is_wrapped(text):
    """True when the body is one top-level brace group closed by the last line."""
    lines = [l for l in text.split("\n")]
    body = [l for l in lines if l.strip()]
    if not body or body[-1] != "}":
        return False
    return any(l == "{" for l in lines)


def last_statement_in_group(text):
    """The last executable line inside the closing `}`, or None."""
    lines = text.split("\n")
    keep = [l for l in lines if l.strip()]
    assert keep[-1] == "}"
    for line in reversed(keep[:-1]):
        if line.lstrip().startswith("#"):
            continue
        return line
    return None


class WrappingInvariantTest(unittest.TestCase):
    """The static half. Cheap enough to run on every suite, so it always runs."""

    def test_every_shipped_script_parses(self):
        # `bash -n` is what proves the brace still closes the file. It proves nothing
        # about the exit; that is the next test.
        for rel in shipped_scripts():
            with self.subTest(script=rel):
                r = subprocess.run(["bash", "-n", str(REPO / rel)],
                                   capture_output=True, text=True, stdin=subprocess.DEVNULL)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_wrapped_script_ends_its_group_with_an_exit(self):
        """Half (b), checked everywhere. A group that is fallen off the end of is worse
        than no group: measured, bash resumed just past `}`, found rewritten text
        sitting there, and ran the whole body a SECOND time."""
        wrapped = [r for r in shipped_scripts() if is_wrapped((REPO / r).read_text())]
        self.assertTrue(wrapped, "nothing is wrapped; this test would pass vacuously")
        for rel in wrapped:
            with self.subTest(script=rel):
                last = last_statement_in_group((REPO / rel).read_text())
                self.assertIsNotNone(last, "%s: brace group has no statement in it" % rel)
                self.assertRegex(
                    last.strip(), r"^exit\b",
                    "%s: the last statement inside the brace group is %r, not an `exit`. "
                    "The group protects its body and nothing past it -- bash resumes at "
                    "the byte just after `}` in whatever the file now holds."
                    % (rel, last.strip()))

    def test_the_exposed_scripts_are_wrapped(self):
        for rel in REQUIRE_WRAPPED:
            with self.subTest(script=rel):
                self.assertTrue(
                    is_wrapped((REPO / rel).read_text()),
                    "%s is executed by absolute path out of the checkout and must have "
                    "its body in one brace group; see docs/DESIGN.md" % rel)

    def test_every_shipped_script_is_wrapped_or_listed(self):
        """A new script has to be classified on purpose, not by forgetting."""
        for rel in shipped_scripts():
            with self.subTest(script=rel):
                if rel in KNOWN_UNWRAPPED:
                    continue
                self.assertTrue(
                    is_wrapped((REPO / rel).read_text()),
                    "%s is neither wrapped nor listed in KNOWN_UNWRAPPED. Wrap it, or "
                    "add it there with the reason it is safe to leave open." % rel)

    def test_the_tolerated_list_cannot_rot(self):
        shipped = set(shipped_scripts())
        for rel in sorted(KNOWN_UNWRAPPED):
            self.assertIn(rel, shipped,
                          "KNOWN_UNWRAPPED names %s, which is not a shipped script "
                          "any more; drop the entry" % rel)
        self.assertFalse(set(REQUIRE_WRAPPED) & KNOWN_UNWRAPPED,
                         "a script cannot be both required and tolerated")


class HomeUnsetTest(unittest.TestCase):
    """`set -u` plus an unset HOME kills a script before it prints anything.

    The static half covers every shipped script. The live half runs the real
    statusline/skillforge-status.sh with HOME actually absent from its environment, and
    proves non-vacuity by running the same real file with ONLY the guard line deleted --
    which must die. SKILL_COMPOUNDER_STATE is deliberately left unset in both runs:
    setting it means `$HOME` is never expanded at all and the test would prove nothing.
    """

    SCRIPT = REPO / "statusline" / "skillforge-status.sh"

    def test_every_script_that_expands_home_defaults_it_first(self):
        for rel in shipped_scripts():
            if rel in HOME_UNGUARDED:
                continue
            text = (REPO / rel).read_text()
            first = first_home_expansion(text)
            if first is None:
                continue
            with self.subTest(script=rel):
                guard = home_guard_line(text)
                self.assertIsNotNone(
                    guard,
                    "%s expands $HOME on line %d under `set -u` but never defaults it. "
                    "Add `%s` above that line, or add the script to HOME_UNGUARDED with "
                    "the reason." % (rel, first, GUARD))
                self.assertLess(
                    guard, first,
                    "%s defaults HOME on line %d, AFTER it first expands it on line %d. "
                    "The abort happens at the first expansion." % (rel, guard, first))

    def test_the_home_ratchet_cannot_rot(self):
        shipped = set(shipped_scripts())
        for rel in sorted(HOME_UNGUARDED):
            self.assertIn(rel, shipped,
                          "HOME_UNGUARDED names %s, which is not a shipped script any "
                          "more; drop the entry" % rel)
            text = (REPO / rel).read_text()
            first, guard = first_home_expansion(text), home_guard_line(text)
            self.assertFalse(
                first is None or (guard is not None and guard < first),
                "%s is guarded now (or no longer expands $HOME); delete its "
                "HOME_UNGUARDED entry so the exemption cannot outlive the defect" % rel)

    # ------------------------------------------------------------------- live half
    def run_without_home(self, path):
        """Run `path` with HOME genuinely absent. Returns (rc, stderr)."""
        env = {"PATH": PATH_BASE}     # no HOME, no SKILL_COMPOUNDER_STATE
        r = subprocess.run([str(path)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, env=env, timeout=TIMEOUT)
        return r.returncode, r.stderr

    def test_the_status_segment_survives_an_unset_home(self):
        rc, err = self.run_without_home(self.SCRIPT)
        self.assertNotIn("unbound variable", err)
        self.assertEqual(err, "", "the status segment wrote to stderr: %r" % err)
        self.assertEqual(rc, 0, "exited %d with HOME unset" % rc)

    def test_the_same_script_without_its_guard_dies(self):
        """Non-vacuity. If this ever passes clean, the test above proves nothing."""
        text = self.SCRIPT.read_text()
        lines = text.split("\n")
        keep = [l for l in lines if l.strip() != GUARD]
        self.assertEqual(len(keep), len(lines) - 1,
                         "expected exactly one guard line to remove")
        tmp = tempfile.mkdtemp()
        try:
            probe = Path(tmp) / "skillforge-status.sh"
            probe.write_text("\n".join(keep))
            probe.chmod(0o755)
            rc, err = self.run_without_home(probe)
            self.assertIn("unbound variable", err,
                          "removing the guard changed nothing, so the guard is not what "
                          "is protecting the script (stderr=%r, rc=%d)" % (err, rc))
            self.assertNotEqual(rc, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RewriteUnderLoadHarness(unittest.TestCase):
    """Starts a real script, blocks it at a real point, rewrites it, releases it."""

    HOOK = REPO / "hooks" / "insight-capture.sh"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.t = Path(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --------------------------------------------------------------- variants
    @staticmethod
    def unwrapped(text):
        """The same script with ONLY the brace group removed.

        Deleting exactly two lines isolates half (a): everything else -- length, the
        `exit 0`, every byte of logic -- is identical, so a difference in outcome can
        only be the group.
        """
        lines = text.split("\n")
        i = lines.index("set -uo pipefail")
        j = next(k for k in range(i, len(lines)) if lines[k] == "{")
        del lines[j]
        k = max(k for k, l in enumerate(lines) if l.strip())
        assert lines[k] == "}", lines[k]
        del lines[k]
        return "\n".join(lines)

    # --------------------------------------------------------------- the run
    def drive(self, script_text, rewrite):
        """Run the script to completion, applying `rewrite` while it is blocked.

        Returns (returncode, stdout, stderr, date-shim argv log).

        The synchronisation is a happens-before chain, not a sleep: the shim creates
        `ready` and then blocks opening a FIFO for read; this test polls for `ready`,
        does the rewrite, and only then opens the FIFO for write -- which itself blocks
        until the shim has opened the read end. The script cannot get past the rewrite
        early, and the rewrite cannot land before the script is inside the shim.
        """
        t = self.t
        script = t / "hook.sh"
        script.write_text(script_text)
        script.chmod(0o755)

        shim = t / "shim"
        shim.mkdir(exist_ok=True)
        (shim / "date").write_text(
            '#!/bin/bash\n'
            '# Logs its argv, blocks the FIRST call until the test releases it, then\n'
            '# hands off to the real date. Nothing about the caller changes but timing.\n'
            'printf "%s\\n" "$*" >> "$DATE_LOG"\n'
            'if [ ! -e "$GATE" ]; then\n'
            '  : > "$GATE"\n'
            '  : > "$READY"\n'
            '  read -r _ < "$FIFO"\n'
            'fi\n'
            'exec /bin/date "$@"\n')
        (shim / "date").chmod(0o755)

        fifo = t / "fifo"
        if not fifo.exists():
            os.mkfifo(fifo)

        env = {"PATH": "%s:%s" % (shim, PATH_BASE), "HOME": str(t),
               "SKILL_COMPOUNDER_STATE": str(t / "state"),
               "INSIGHT_NOW": NOW,
               # Never dispatch a real `claude -p` from a test.
               "SKILL_COMPOUNDER_REVIEW": "0",
               "DATE_LOG": str(t / "date.log"), "GATE": str(t / "gate"),
               "READY": str(t / "ready"), "FIFO": str(fifo)}

        payload = json.dumps({"session_id": "s1", "cwd": str(t),
                              "transcript_path": str(t / "absent.jsonl"),
                              "hook_event_name": "Stop",
                              "last_assistant_message": "nothing here clears the bar"})
        (t / "payload.json").write_text(payload)
        fin = open(t / "payload.json")
        p = subprocess.Popen([str(script)], stdin=fin, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=env)
        fin.close()
        try:
            deadline = time.time() + TIMEOUT
            while not (t / "ready").exists():
                if p.poll() is not None:
                    raise AssertionError("script exited before reaching the shim: %s"
                                         % p.communicate()[1])
                if time.time() > deadline:
                    raise AssertionError("script never reached the date shim")
                time.sleep(0.005)
            if rewrite is not None:
                rewrite(script)
            with open(fifo, "w") as w:      # blocks until the shim's read end is open
                w.write("go\n")
            out, err = p.communicate(timeout=TIMEOUT)
        finally:
            if p.poll() is None:
                p.kill()
                p.communicate()
        log = (t / "date.log").read_text().splitlines() if (t / "date.log").exists() else []
        return p.returncode, out, err, log

    def fresh(self):
        """A clean temp dir, so each drive() in a test is independent."""
        self.tearDown()
        self.setUp()


class RewriteUnderLoadTest(RewriteUnderLoadHarness):

    def prepend(self, script):
        """Prepend more prose than the script is long.

        Size matters and is not arbitrary. bash resumes at the byte offset it had
        reached; making the prepended block longer than the whole file guarantees that
        offset now lands inside the prose rather than at some incidentally harmless
        comment, which is what the reproduction in docs/DESIGN.md did with 40 lines
        against a 25-line script.
        """
        line = "The bearer of this notice is non-transferable and void where prohibited.\n"
        text = script.read_text()
        script.write_text(line * (len(text) // len(line) + 40) + text)

    def test_the_wrapped_hook_is_unharmed_by_a_rewrite_mid_run(self):
        rc0, out0, err0, log0 = self.drive(self.HOOK.read_text(), None)
        self.fresh()
        rc1, out1, err1, log1 = self.drive(self.HOOK.read_text(), self.prepend)

        self.assertEqual(err1, "", "a wrapped script executed rewritten bytes: %r" % err1)
        self.assertEqual(rc1, rc0)
        self.assertEqual(out1, out0)
        self.assertEqual(log1, log0,
                         "the body ran a different number of times under the rewrite: "
                         "%r vs baseline %r" % (log1, log0))

    def test_the_same_hook_without_its_group_is_corrupted_by_the_same_rewrite(self):
        """Non-vacuity. If this ever passes clean, the test above proves nothing."""
        text = self.unwrapped(self.HOOK.read_text())
        rc0, out0, err0, log0 = self.drive(text, None)
        self.assertEqual(err0, "", "the control is broken before any rewrite: %r" % err0)
        self.fresh()
        rc1, out1, err1, log1 = self.drive(text, self.prepend)

        corrupted = (err1 != err0) or (rc1 != rc0) or (log1 != log0) or (out1 != out0)
        self.assertTrue(corrupted,
                        "removing the brace group changed nothing, so the harness is "
                        "not actually reproducing the hazard any more (bash %s)"
                        % subprocess.run(["bash", "--version"], capture_output=True,
                                         text=True).stdout.split("\n")[0])
        # What it actually does on bash 5.3.3(1): executes text that was not there when
        # it started, and re-enters a part of the body it had already run.
        self.assertIn("command not found", err1)
        self.assertGreater(len(log1), len(log0))


class FallingOffTheEndTest(unittest.TestCase):
    """Half (b), reproduced live against bash itself.

    A brace group protects its body and nothing past it. This is the probe from
    docs/DESIGN.md, run for real rather than quoted: a wrapped script with no `exit`
    before its `}` against the same wrapped script with one. It is deliberately a
    minimal script and not one of ours, because what is under test here is bash's
    resume behaviour -- the platform fact the whole rule rests on. Measured on the
    30KB `hooks/insight-capture.sh` this same rewrite did NOT resume past the group,
    so a large file is not proof either way and the small one is the honest probe.
    """

    # The gate file makes the block happen ONCE. Without it a body that runs a second
    # time blocks forever on a FIFO nobody will open again, and the probe hangs instead
    # of reporting what it found.
    BODY = ('#!/bin/bash\n'
            '{\n'
            'echo BODY-START\n'
            'if [ ! -e "$GATE" ]; then : > "$GATE"; read -r _ < "$FIFO"; fi\n'
            'echo BODY-END\n'
            '%s'
            '}\n')

    def run_probe(self, tail):
        tmp = tempfile.mkdtemp()
        try:
            t = Path(tmp)
            script = t / "probe.sh"
            script.write_text(self.BODY % tail)
            script.chmod(0o755)
            fifo = t / "fifo"
            os.mkfifo(fifo)
            p = subprocess.Popen([str(script)], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True,
                                 stdin=subprocess.DEVNULL,
                                 env={"PATH": PATH_BASE, "FIFO": str(fifo),
                                      "GATE": str(t / "gate")})
            # Opening the FIFO for write blocks until the script's `read` opens the
            # read end, so this is a sync point, not a sleep.
            w = open(fifo, "w")
            script.write_text("The bearer of this notice is non-transferable.\n" * 40
                              + script.read_text())
            w.write("go\n")
            w.close()
            out, _ = p.communicate(timeout=TIMEOUT)
            return out
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_without_a_terminating_exit_bash_resumes_past_the_closing_brace(self):
        out = self.run_probe("")
        self.assertEqual(out.count("BODY-START"), 2,
                         "expected the body to run twice; got %r" % out)
        self.assertIn("command not found", out)

    def test_with_a_terminating_exit_it_does_not(self):
        out = self.run_probe("exit 0\n")
        self.assertEqual(out.count("BODY-START"), 1, out)
        self.assertEqual(out.count("BODY-END"), 1, out)
        self.assertNotIn("command not found", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
