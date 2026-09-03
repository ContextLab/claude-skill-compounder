#!/usr/bin/env python3
"""`skillforge doctor` is the surface this package's silent failures are visible on.

The defect these pin. Every hook here opens with `command -v jq >/dev/null 2>&1 || exit 0`
and `mkdir -p "$STATE_DIR" 2>/dev/null || exit 0`, and both of those are RIGHT -- a hook
that fails a turn is worse than a hook that does nothing. The price is that a missing jq, a
state directory that has gone read-only, a SKILL_COMPOUNDER_STATE pointing somewhere that
no longer exists, a settings.json that stopped parsing, a skills symlink left dangling by a
moved checkout, or a ledger whose last append was cut short silences the WHOLE package --
no error, no status-line segment, no ledger row, nothing anywhere saying so. Seen from
outside, every one of those is indistinguishable from a package that simply had nothing to
say, which is why none of them was ever noticed from the inside.

Real CLI, real temp state, real files: a real `chmod` for the unwritable directory, a real
dangling symlink, a real truncated ledger line, real counter files in both of the forms the
reminder hook has written. Two knobs are pinned and both are ones `bin/skillforge` reads
for exactly that purpose -- SKILLFORGE_NOW for the clock, and SKILLFORGE_DOCTOR_JQ_VERSION
for the version string, so the too-old branch can be watched firing without shipping a jq
from 2015.

EVERY `FAIL` ASSERTED HERE HAS A `PASS` COUNTERPART in the same class. A check that cannot
come out clean is a check nobody can act on, and a doctor that always fails is a doctor
nobody runs twice.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"
INSTALLER = REPO / "skill_compounder" / "installer.py"
HOOKS_JSON = REPO / "hooks" / "hooks.json"

T0 = 1000000000
HOUR = 3600
DEFAULT_ACTIVE_TTL = 21600      # bin/skillforge: six hours, of IDLE time


def installer_hook_markers():
    """Every `*_MARKER = "...sh"` the installer declares, read the way doctor reads them.

    Read and not listed: this test would otherwise pass against a marker list that had
    drifted from the installer's own, which is the exact failure the doctor is written to
    avoid -- reporting a wiring nobody has.
    """
    out = []
    for line in INSTALLER.read_text().splitlines():
        m = re.match(r'^([A-Z_]*MARKER) = "(.*)"\s*$', line)
        if m and m.group(2).endswith(".sh"):
            out.append(m.group(2))
    return sorted(set(out))


def installer_const(name):
    for line in INSTALLER.read_text().splitlines():
        m = re.match(r'^%s = "(.*)"\s*$' % re.escape(name), line)
        if m:
            return m.group(1)
    raise AssertionError("%s is not defined in %s" % (name, INSTALLER))


def hooks_json_entry_count():
    hj = json.loads(HOOKS_JSON.read_text())
    return sum(len(g.get("hooks", []))
               for groups in hj["hooks"].values() for g in groups)


def verdict(out, label):
    """The verdict word for one check, or None when that check printed no line at all."""
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("PASS", "WARN", "FAIL") and parts[1] == label:
            return parts[0]
    return None


def line_for(out, label):
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("PASS", "WARN", "FAIL") and parts[1] == label:
            return line
    return ""


class DoctorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)

    def tearDown(self):
        # A test that chmods the state root read-only would otherwise take the whole
        # cleanup down with it, and the next test would run against a directory that
        # still existed.
        try:
            os.chmod(str(self.state), 0o755)
        except OSError:
            pass
        self.tmp.cleanup()

    def env(self, **extra):
        e = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
             "HOME": str(self.state),
             "SKILL_COMPOUNDER_STATE": str(self.state)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def run_cli(self, *args, **extra):
        return subprocess.run([str(CLI), *args], capture_output=True, text=True,
                              env=self.env(**extra))

    def doctor(self, **extra):
        r = self.run_cli("doctor", **extra)
        self.assertIn("skillforge doctor", r.stdout, "no doctor output at all: %r" % r)
        return r

    def start(self, name="demo-skill", now=T0):
        r = self.run_cli("start", name, "22", "a demo forge", "--trigger", "a test did it",
                         "--trigger-kind", "agent-decision", SKILLFORGE_NOW=now)
        self.assertEqual(r.returncode, 0, "start failed: %s" % r.stderr)

    # ------------------------------------------------------------------ settings.json

    def write_settings(self, drop_marker=None, statusline=True, malformed=False):
        """A settings.json wired exactly as hooks/hooks.json wires the plugin.

        Built by TRANSFORMING hooks/hooks.json rather than by hand, so the fixture cannot
        drift from the file the doctor counts against; tests/test_plugin.py already pins
        that file against what install.sh writes.
        """
        d = self.state / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "settings.json"
        if malformed:
            f.write_text('{"hooks": {"Stop": [ }')
            return f
        hj = json.loads(HOOKS_JSON.read_text())
        hooks = {}
        for event, groups in hj["hooks"].items():
            keep = []
            for g in groups:
                entries = [{"type": "command",
                            "command": h["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(REPO)),
                            "timeout": 10}
                           for h in g.get("hooks", [])
                           if not (drop_marker and drop_marker in h["command"])]
                if entries:
                    ng = dict(g)
                    ng["hooks"] = entries
                    keep.append(ng)
            if keep:
                hooks[event] = keep
        settings = {"hooks": hooks}
        if statusline:
            settings["statusLine"] = {
                "type": "command",
                "command": '"%s/statusline/statusline.sh"  %s'
                           % (REPO, installer_const("STATUSLINE_MARKER"))}
        f.write_text(json.dumps(settings, indent=2))
        return f


# ------------------------------------------------------------------------ the shape

class TheOutputIsReadableByAPersonAndByGrep(DoctorCase):
    def test_every_check_prints_one_line_whose_first_word_is_the_verdict(self):
        r = self.doctor(SKILLFORGE_NOW=T0)
        for label in ("jq", "state", "settings", "statusline", "skills",
                      "ledger", "counters", "forges", "review"):
            self.assertIn(verdict(r.stdout, label), ("PASS", "WARN", "FAIL"),
                          "no verdict line for '%s': %r" % (label, r.stdout))

    def test_a_clean_state_exits_zero_and_fails_nothing(self):
        """Non-vacuity for every FAIL below. A doctor that cannot come out clean is one
        nobody runs a second time, and then the real FAILs go unread with it."""
        self.write_settings()
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(r.returncode, 0, "a clean state exited %d: %s"
                         % (r.returncode, r.stdout))
        self.assertNotIn("FAIL", r.stdout, r.stdout)

    def test_the_summary_counts_what_was_printed(self):
        self.write_settings()
        r = self.doctor(SKILLFORGE_NOW=T0)
        m = re.search(r"^(\d+) pass, (\d+) warn, (\d+) fail$", r.stdout, re.M)
        self.assertTrue(m, "no summary line: %r" % r.stdout)
        counted = sum(int(g) for g in m.groups())
        printed = len([l for l in r.stdout.splitlines()
                       if l.split()[:1] and l.split()[0] in ("PASS", "WARN", "FAIL")])
        self.assertEqual(counted, printed,
                         "the summary says %d checks and %d lines were printed" %
                         (counted, printed))

    def test_doctor_leaves_the_state_directory_exactly_as_it_found_it(self):
        """It writes ONE probe file, to answer a question `[ -w ]` answers wrongly, and
        removes it. A health surface that edits what it measures cannot be run twice."""
        self.start()
        before = sorted(p.relative_to(self.state).as_posix()
                        for p in self.state.rglob("*"))
        self.doctor(SKILLFORGE_NOW=T0 + 8 * HOUR)
        after = sorted(p.relative_to(self.state).as_posix()
                       for p in self.state.rglob("*"))
        self.assertEqual(before, after, "doctor changed the state directory")

    def test_doctor_does_not_reap_the_forge_it_warns_about(self):
        """The one thing a person must be able to trust before running it against a live
        machine. Reporting and acting are different commands on purpose."""
        self.start()
        self.doctor(SKILLFORGE_NOW=T0 + 8 * HOUR)
        listing = self.run_cli("list", SKILLFORGE_NOW=T0 + 8 * HOUR)
        self.assertIn("active", listing.stdout, listing.stdout)
        ledger = (self.state / "ledger.jsonl").read_text()
        self.assertNotIn('"event":"fail"', ledger.replace(" ", ""),
                         "doctor wrote an outcome row")


# ------------------------------------------------------------------------------- jq

class TheJqCheck(DoctorCase):
    def test_it_names_the_version_and_where_it_came_from(self):
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "jq"), "PASS", line_for(r.stdout, "jq"))
        self.assertIn("jq-", line_for(r.stdout, "jq"),
                      "the jq line does not carry a version: %r" % line_for(r.stdout, "jq"))

    def test_a_jq_older_than_the_floor_fails_and_says_what_needs_it(self):
        """1.6 is not a guess at 'modern jq'. `skillforge backfill` passes --rawfile, and
        jq did not have --rawfile before 1.6."""
        r = self.doctor(SKILLFORGE_NOW=T0, SKILLFORGE_DOCTOR_JQ_VERSION="jq-1.5")
        self.assertEqual(verdict(r.stdout, "jq"), "FAIL", line_for(r.stdout, "jq"))
        self.assertIn("--rawfile", line_for(r.stdout, "jq"),
                      "the failure does not say what needs 1.6")
        self.assertEqual(r.returncode, 1, "a FAIL did not set the exit status")

    def test_the_floor_itself_passes(self):
        """One version under is a fail and the floor exactly is a pass. A guard nobody has
        watched flip is a guard nobody has watched at all."""
        r = self.doctor(SKILLFORGE_NOW=T0, SKILLFORGE_DOCTOR_JQ_VERSION="jq-1.6")
        self.assertEqual(verdict(r.stdout, "jq"), "PASS", line_for(r.stdout, "jq"))

    def test_a_version_string_it_cannot_parse_warns_rather_than_guessing(self):
        r = self.doctor(SKILLFORGE_NOW=T0, SKILLFORGE_DOCTOR_JQ_VERSION="jq-master-a1b2c3")
        self.assertEqual(verdict(r.stdout, "jq"), "WARN", line_for(r.stdout, "jq"))
        self.assertEqual(r.returncode, 0, "an unparseable version failed the command")


# ---------------------------------------------------------------------------- state

class TheStateCheck(DoctorCase):
    def test_a_writable_state_directory_passes_and_says_where_it_came_from(self):
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "state"), "PASS", line_for(r.stdout, "state"))
        self.assertIn("SKILL_COMPOUNDER_STATE", line_for(r.stdout, "state"),
                      "the line does not say which knob chose this directory")

    def test_a_state_directory_that_will_not_take_a_write_fails(self):
        """The exact silent failure: every hook does `mkdir -p ... || exit 0` and goes
        quiet, and `mkdir -p` SUCCEEDS on a directory that already exists however
        unwritable it has become, so nothing else in the package can notice."""
        self.start()
        os.chmod(str(self.state), 0o555)
        try:
            r = self.doctor(SKILLFORGE_NOW=T0)
        finally:
            os.chmod(str(self.state), 0o755)
        self.assertEqual(verdict(r.stdout, "state"), "FAIL", line_for(r.stdout, "state"))
        self.assertEqual(r.returncode, 1)

    def test_the_probe_file_is_never_left_behind_even_when_it_fails(self):
        """The probe is the only thing `doctor` writes anywhere, and a state directory
        slowly filling with `.doctor-probe.*` would be a health surface producing the kind
        of litter it exists to find. The failing path is the one to check: the success
        path removes it, and the failure path never created it."""
        self.start()
        os.chmod(str(self.state), 0o555)
        try:
            r = self.doctor(SKILLFORGE_NOW=T0)
            probes = list(self.state.glob(".doctor-probe.*"))
        finally:
            os.chmod(str(self.state), 0o755)
        self.assertEqual(verdict(r.stdout, "state"), "FAIL", line_for(r.stdout, "state"))
        self.assertEqual(probes, [], "a probe file was left behind: %r" % probes)


# ------------------------------------------------------------------------- settings

class TheSettingsCheck(DoctorCase):
    def test_a_full_wiring_passes_and_counts_against_hooks_json(self):
        self.write_settings()
        r = self.doctor(SKILLFORGE_NOW=T0)
        want = hooks_json_entry_count()
        self.assertEqual(verdict(r.stdout, "settings"), "PASS",
                         line_for(r.stdout, "settings"))
        self.assertIn("%d/%d" % (want, want), line_for(r.stdout, "settings"),
                      "the count is not reported against hooks/hooks.json")

    def test_a_partial_wiring_fails_and_names_the_script_nothing_runs(self):
        """A PARTIAL wiring is the shape that silences one event and leaves the rest
        working, so no other surface will ever report it."""
        dropped = installer_hook_markers()[0]
        self.write_settings(drop_marker=dropped)
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "settings"), "FAIL",
                         line_for(r.stdout, "settings"))
        self.assertIn(dropped, line_for(r.stdout, "settings"),
                      "the failure does not name the script that is not wired")
        self.assertEqual(r.returncode, 1)

    def test_every_marker_the_installer_declares_is_one_this_can_miss(self):
        """Not a spot check of one. Each marker in turn is removed and has to be named,
        which is what proves the list is READ from installer.py rather than copied."""
        for marker in installer_hook_markers():
            self.write_settings(drop_marker=marker)
            r = self.doctor(SKILLFORGE_NOW=T0)
            self.assertEqual(verdict(r.stdout, "settings"), "FAIL",
                             "dropping %s did not fail: %s" % (marker, r.stdout))
            self.assertIn(marker, line_for(r.stdout, "settings"),
                          "dropping %s was not reported by name" % marker)

    def test_no_entries_at_all_warns_rather_than_fails(self):
        """Correct for a plugin install, which carries hooks/hooks.json and writes nothing
        into settings.json. Failing here would make the doctor useless on that path."""
        (self.state / ".claude").mkdir(parents=True, exist_ok=True)
        (self.state / ".claude" / "settings.json").write_text('{"hooks": {}}')
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "settings"), "WARN",
                         line_for(r.stdout, "settings"))
        self.assertIn("PLUGIN", line_for(r.stdout, "settings").upper(),
                      "the warning does not say when this is expected")
        self.assertEqual(r.returncode, 0)

    def test_a_settings_json_that_does_not_parse_fails_loudly(self):
        """A malformed settings.json disables EVERY setting in it, not only ours, and
        nothing in a running session says so."""
        self.write_settings(malformed=True)
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "settings"), "FAIL",
                         line_for(r.stdout, "settings"))
        self.assertEqual(r.returncode, 1)

    def test_a_missing_settings_json_warns(self):
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "settings"), "WARN",
                         line_for(r.stdout, "settings"))
        self.assertEqual(r.returncode, 0)


class TheStatusLineCheck(DoctorCase):
    def test_the_marker_the_installer_writes_is_the_one_looked_for(self):
        self.write_settings()
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "statusline"), "PASS",
                         line_for(r.stdout, "statusline"))
        self.assertIn(installer_const("STATUSLINE_MARKER"),
                      line_for(r.stdout, "statusline"))

    def test_someone_elses_status_line_warns_and_does_not_fail(self):
        """It may be a deliberate choice, and a plugin install cannot carry a statusLine
        at all -- so this is the class of thing WARN exists for."""
        self.write_settings(statusline=False)
        f = self.state / ".claude" / "settings.json"
        s = json.loads(f.read_text())
        s["statusLine"] = {"type": "command", "command": "~/bin/git-statusline.sh"}
        f.write_text(json.dumps(s))
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "statusline"), "WARN",
                         line_for(r.stdout, "statusline"))
        self.assertEqual(r.returncode, 0)


# --------------------------------------------------------------------------- skills

class TheSkillLinkCheck(DoctorCase):
    def skills_dir(self):
        d = self.state / "skills-dest"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_links_that_resolve_pass_and_are_counted(self):
        d = self.skills_dir()
        (d / "skill-compounder").symlink_to(REPO / "skills" / "skill-compounder")
        r = self.doctor(SKILLFORGE_NOW=T0, SKILLFORGE_SKILLS_DIR=d)
        self.assertEqual(verdict(r.stdout, "skills"), "PASS", line_for(r.stdout, "skills"))
        self.assertIn("1 link", line_for(r.stdout, "skills"))

    def test_a_dangling_link_into_this_checkout_fails_and_is_named(self):
        """A dangling link is an 'Unknown skill' at the moment it is invoked and at no
        other moment, which is the worst time for it to be the first anyone hears."""
        d = self.skills_dir()
        (d / "skill-compounder").symlink_to(REPO / "skills" / "skill-compounder")
        (d / "ghost").symlink_to(REPO / "skills" / "no-such-skill")
        r = self.doctor(SKILLFORGE_NOW=T0, SKILLFORGE_SKILLS_DIR=d)
        self.assertEqual(verdict(r.stdout, "skills"), "FAIL", line_for(r.stdout, "skills"))
        self.assertIn("ghost", line_for(r.stdout, "skills"))
        self.assertEqual(r.returncode, 1)

    def test_a_dangling_link_pointing_elsewhere_is_reported_and_not_owned(self):
        """It may be the user's own, or another tool's. This package has twice destroyed a
        user's skills by being generous about what counts as its own, so a link it cannot
        vouch for is reported, never claimed and never failed on."""
        d = self.skills_dir()
        (d / "someone-elses").symlink_to(self.state / "not-here" / "thing")
        r = self.doctor(SKILLFORGE_NOW=T0, SKILLFORGE_SKILLS_DIR=d)
        self.assertEqual(verdict(r.stdout, "skills"), "PASS", line_for(r.stdout, "skills"))
        self.assertIn("someone-elses", r.stdout,
                      "a dangling foreign link was not reported at all")
        self.assertEqual(r.returncode, 0)

    def test_no_skills_directory_warns(self):
        r = self.doctor(SKILLFORGE_NOW=T0,
                        SKILLFORGE_SKILLS_DIR=self.state / "nowhere")
        self.assertEqual(verdict(r.stdout, "skills"), "WARN", line_for(r.stdout, "skills"))


# --------------------------------------------------------------------------- ledger

class TheLedgerCheck(DoctorCase):
    def test_a_ledger_written_by_the_cli_passes_and_reports_its_size(self):
        self.start()
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "ledger"), "PASS", line_for(r.stdout, "ledger"))
        self.assertIn("row(s)", line_for(r.stdout, "ledger"))

    def test_an_empty_ledger_is_not_a_fault(self):
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "ledger"), "PASS", line_for(r.stdout, "ledger"))

    def test_a_cut_short_last_line_fails(self):
        """The shape a killed append leaves. Every reader here drops it silently, so the
        forge it recorded is simply missing from every count with nothing saying so."""
        self.start()
        led = self.state / "ledger.jsonl"
        with led.open("a") as fh:
            fh.write('{"event":"done","name":"demo-skill","ts":10000000')
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "ledger"), "FAIL", line_for(r.stdout, "ledger"))
        self.assertEqual(r.returncode, 1)

    def test_a_bad_line_that_is_not_the_last_one_warns(self):
        """It is already lost -- nothing can recover it -- so it is not a FAIL, but the
        counts everywhere else are quietly short by one and that is worth saying."""
        self.start()
        led = self.state / "ledger.jsonl"
        rows = led.read_text().splitlines()
        rows.insert(1, '{"event":"done","name":"x"')
        led.write_text("\n".join(rows) + "\n")
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "ledger"), "WARN", line_for(r.stdout, "ledger"))
        self.assertEqual(r.returncode, 0)


# ------------------------------------------------------------------------- counters

class TheEditCounterCheck(DoctorCase):
    def counters(self, **files):
        d = self.state / "reminders"
        d.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (d / ("%s.edits" % name)).write_text(body)
        return d

    def test_a_unary_tally_passes_and_is_reported_as_a_tally(self):
        """The form hooks/compound-improvement.sh writes today: one byte appended per
        edit, so the count is the file SIZE. Chosen because a read-modify-write lost 48
        of 60 edits under the parallelism edits actually arrive at."""
        self.counters(sess="x" * 14)
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "counters"), "PASS",
                         line_for(r.stdout, "counters"))
        self.assertIn("1 unary", line_for(r.stdout, "counters"),
                      "the form on disk is not reported: %r" % line_for(r.stdout, "counters"))

    def test_a_digit_string_passes_and_is_reported_as_a_number(self):
        """The older form, and the one a reader that `cat`s the file and demands digits
        accepts. Both forms are legal to this check; which one a reader takes is that
        reader's business, and the two only have to agree."""
        self.counters(sess="14")
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "counters"), "PASS",
                         line_for(r.stdout, "counters"))
        self.assertIn("1 digit string", line_for(r.stdout, "counters"),
                      line_for(r.stdout, "counters"))

    def test_both_forms_at_once_warns_because_one_reader_drops_the_other(self):
        self.counters(old="14", new="x" * 9)
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "counters"), "WARN",
                         line_for(r.stdout, "counters"))
        self.assertEqual(r.returncode, 0)

    def test_a_number_with_a_tally_appended_to_it_fails_and_is_called_out(self):
        """Observed on this machine: one file holding `36` and then 900 `x` bytes -- a
        single session counted as a number, then appended to as a tally when the hook
        changed form under it. Neither reader can add the halves up."""
        self.counters(sess="36" + "x" * 900)
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "counters"), "FAIL",
                         line_for(r.stdout, "counters"))
        self.assertIn("sess.edits", line_for(r.stdout, "counters"))
        self.assertEqual(r.returncode, 1)

    def test_a_corrupt_counter_fails(self):
        self.counters(sess="not a count at all")
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "counters"), "FAIL",
                         line_for(r.stdout, "counters"))
        self.assertEqual(r.returncode, 1)

    def test_no_counters_yet_is_not_a_fault(self):
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "counters"), "PASS",
                         line_for(r.stdout, "counters"))


# --------------------------------------------------------------------------- forges

class TheStuckForgeCheck(DoctorCase):
    def test_a_fresh_forge_is_not_warned_about(self):
        self.start()
        r = self.doctor(SKILLFORGE_NOW=T0 + HOUR)
        self.assertEqual(verdict(r.stdout, "forges"), "PASS", line_for(r.stdout, "forges"))

    def test_a_forge_past_the_ttl_warns_and_names_the_command_that_frees_it(self):
        self.start()
        r = self.doctor(SKILLFORGE_NOW=T0 + DEFAULT_ACTIVE_TTL)
        self.assertEqual(verdict(r.stdout, "forges"), "WARN", line_for(r.stdout, "forges"))
        self.assertIn("demo-skill", line_for(r.stdout, "forges"))
        self.assertIn("skillforge reap", r.stdout,
                      "nothing tells the reader what to do about it")

    def test_a_stale_forge_warns_and_does_not_fail_the_command(self):
        """An idle forge may still be live work, so it can never be a FAIL. It is also
        the check most likely to fire on a real machine, and one FAIL that is not a fault
        is enough to teach a person to stop reading the output."""
        self.start()
        r = self.doctor(SKILLFORGE_NOW=T0 + 3 * DEFAULT_ACTIVE_TTL)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_the_boundary_is_the_ttl_itself(self):
        self.start()
        under = self.doctor(SKILLFORGE_NOW=T0 + DEFAULT_ACTIVE_TTL - 1)
        at = self.doctor(SKILLFORGE_NOW=T0 + DEFAULT_ACTIVE_TTL)
        self.assertEqual(verdict(under.stdout, "forges"), "PASS",
                         line_for(under.stdout, "forges"))
        self.assertEqual(verdict(at.stdout, "forges"), "WARN",
                         line_for(at.stdout, "forges"))

    def test_the_ttl_knob_is_honoured(self):
        self.start()
        r = self.doctor(SKILLFORGE_NOW=T0 + 120, SKILLFORGE_ACTIVE_TTL=60)
        self.assertEqual(verdict(r.stdout, "forges"), "WARN", line_for(r.stdout, "forges"))

    def test_a_record_whose_age_cannot_be_read_is_never_called_healthy(self):
        """Never guess. Reporting a missing stamp as age zero renders the one forge
        nobody can account for as the healthiest row in the output."""
        self.start()
        slot = sorted((self.state / "forge").glob("*.json"))[0]
        rec = json.loads(slot.read_text())
        rec.pop("updated", None)
        slot.write_text(json.dumps(rec))
        r = self.doctor(SKILLFORGE_NOW=T0 + 8 * HOUR)
        self.assertEqual(verdict(r.stdout, "forges"), "WARN", line_for(r.stdout, "forges"))
        self.assertIn("cannot be read", line_for(r.stdout, "forges"))

    def test_a_ledger_start_whose_forge_file_is_gone_is_reported_as_unreachable(self):
        """A different set from the one reap can act on, and the distinction matters: reap
        closes a RECORD, and when the record is gone there is nothing left to close, so
        that row stays 'never closed out' in the ledger for good."""
        self.start(name="vanished")
        shutil.rmtree(str(self.state / "forge"))
        r = self.doctor(SKILLFORGE_NOW=T0 + 8 * HOUR)
        self.assertIn("cannot be reaped", r.stdout,
                      "an unreachable open start was not reported: %r" % r.stdout)


# ---------------------------------------------------------------------------- review

class TheReviewCheck(DoctorCase):
    """Informational only: hooks/session-review.sh is a detached, paid-for surface named
    in neither settings.json nor hooks/hooks.json, so this is the only place a user can
    see whether it is live. It must never itself be a FAIL -- whether review is on or off
    is a choice, not a fault this package can judge."""

    def test_disabled_by_default(self):
        """The default flipped to OFF in issue #39.

        The paid review is the one arm that spends the user's quota and sends a transcript
        digest off the machine, and the advertised install is `curl | bash`, so it is now
        opt-in. This check is the only surface that reports which way it is set, so the
        default it reports is the claim most worth pinning.
        """
        r = self.doctor(SKILLFORGE_NOW=T0)
        self.assertEqual(verdict(r.stdout, "review"), "PASS", line_for(r.stdout, "review"))
        self.assertIn("review: disabled", line_for(r.stdout, "review"))

    def test_the_disabled_line_says_how_to_opt_in(self):
        """A user who wants it on has nowhere else to look: the script is in neither
        wiring, so nothing but this line can tell them the name of the switch."""
        line = line_for(self.doctor(SKILLFORGE_NOW=T0).stdout, "review")
        self.assertIn("SKILL_COMPOUNDER_REVIEW=1", line)
        self.assertIn("env", line)
        self.assertIn("README", line)

    def test_enabled_reflects_the_opt_in_and_still_passes(self):
        r = self.doctor(SKILLFORGE_NOW=T0, SKILL_COMPOUNDER_REVIEW=1)
        self.assertEqual(verdict(r.stdout, "review"), "PASS", line_for(r.stdout, "review"))
        self.assertIn("review: enabled", line_for(r.stdout, "review"))

    def test_the_enabled_line_carries_a_price(self):
        """Whoever switched it on is owed the figure, on the surface that confirms it is
        on. The number itself is README's to state and derive; doctor quotes it."""
        line = line_for(self.doctor(SKILLFORGE_NOW=T0, SKILL_COMPOUNDER_REVIEW=1).stdout,
                        "review")
        self.assertRegex(line, r"\$[0-9]+\.[0-9]+", "no price on the enabled line: %s" % line)
        self.assertIn("a week", line)

    def test_anything_other_than_the_literal_one_is_disabled(self):
        """hooks/session-review.sh only turns ON for the literal string '1'
        (REVIEW_ON="${SKILL_COMPOUNDER_REVIEW:-0}"; [ "$REVIEW_ON" = "1" ]), so this check
        has to read the switch the same way or it could report a wiring that script does
        not itself have. Before the flip this test ran the other way round, against a
        default of 1 and an off switch of '0'."""
        for value in ("false", "0", "", "true", "yes", "2"):
            with self.subTest(value=value):
                r = self.doctor(SKILLFORGE_NOW=T0, SKILL_COMPOUNDER_REVIEW=value)
                self.assertEqual(verdict(r.stdout, "review"), "PASS",
                                 line_for(r.stdout, "review"))
                self.assertIn("review: disabled", line_for(r.stdout, "review"))


# --------------------------------------------------------------------------- --json

class TheJsonForm(DoctorCase):
    def json_doctor(self, **extra):
        r = self.run_cli("doctor", "--json", **extra)
        return r

    def test_it_parses_as_one_json_object_and_nothing_else_is_on_stdout(self):
        self.write_settings()
        r = self.json_doctor(SKILLFORGE_NOW=T0)
        obj = json.loads(r.stdout)
        self.assertIsInstance(obj, dict, r.stdout)
        for key in ("checks", "pass", "warn", "fail", "exit", "now", "state"):
            self.assertIn(key, obj, "missing '%s': %r" % (key, obj))

    def test_every_check_the_text_form_prints_is_in_the_json_form(self):
        self.write_settings()
        text = self.doctor(SKILLFORGE_NOW=T0)
        js = self.json_doctor(SKILLFORGE_NOW=T0)
        obj = json.loads(js.stdout)
        names = {c["name"] for c in obj["checks"]}
        for label in ("jq", "state", "settings", "statusline", "skills",
                      "ledger", "counters", "forges", "review"):
            self.assertIn(label, names, "'%s' is in the text form but not --json" % label)
            self.assertEqual(verdict(text.stdout, label),
                             next(c["status"] for c in obj["checks"] if c["name"] == label),
                             "the verdict for '%s' differs between the text and JSON forms" % label)

    def test_the_counts_match_the_text_forms_counts(self):
        self.write_settings()
        text = self.doctor(SKILLFORGE_NOW=T0)
        js = self.json_doctor(SKILLFORGE_NOW=T0)
        obj = json.loads(js.stdout)
        m = re.search(r"^(\d+) pass, (\d+) warn, (\d+) fail$", text.stdout, re.M)
        self.assertTrue(m, "no summary line in the text form: %r" % text.stdout)
        want_pass, want_warn, want_fail = (int(g) for g in m.groups())
        self.assertEqual(obj["pass"], want_pass)
        self.assertEqual(obj["warn"], want_warn)
        self.assertEqual(obj["fail"], want_fail)
        self.assertEqual(len(obj["checks"]), want_pass + want_warn + want_fail)

    def test_a_clean_state_exits_zero_with_exit_field_zero(self):
        self.write_settings()
        r = self.json_doctor(SKILLFORGE_NOW=T0)
        obj = json.loads(r.stdout)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(obj["exit"], 0)
        self.assertEqual(obj["fail"], 0)

    def test_a_fail_sets_both_the_process_exit_and_the_json_exit_field(self):
        """Same fault the text form's test_a_state_directory_that_will_not_take_a_write_
        fails uses: chmod the state root read-only so the probe write fails."""
        self.start()
        os.chmod(str(self.state), 0o555)
        try:
            r = self.json_doctor(SKILLFORGE_NOW=T0)
        finally:
            os.chmod(str(self.state), 0o755)
        obj = json.loads(r.stdout)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(obj["exit"], 1)
        self.assertGreaterEqual(obj["fail"], 1)
        self.assertEqual(next(c["status"] for c in obj["checks"] if c["name"] == "state"),
                         "FAIL")

    def test_the_review_check_reflects_the_env_var_in_json_too(self):
        # `on` has to be asked for since the flip in issue #39; unset is `off`.
        on = self.json_doctor(SKILLFORGE_NOW=T0, SKILL_COMPOUNDER_REVIEW=1)
        off = self.json_doctor(SKILLFORGE_NOW=T0)
        on_review = next(c for c in json.loads(on.stdout)["checks"] if c["name"] == "review")
        off_review = next(c for c in json.loads(off.stdout)["checks"] if c["name"] == "review")
        self.assertEqual(on_review["status"], "PASS")
        self.assertIn("enabled", on_review["detail"])
        self.assertEqual(off_review["status"], "PASS")
        self.assertIn("disabled", off_review["detail"])

    def test_doctor_leaves_the_state_directory_exactly_as_it_found_it_in_json_mode(self):
        self.start()
        before = sorted(p.relative_to(self.state).as_posix()
                        for p in self.state.rglob("*"))
        self.json_doctor(SKILLFORGE_NOW=T0 + 8 * HOUR)
        after = sorted(p.relative_to(self.state).as_posix()
                       for p in self.state.rglob("*"))
        self.assertEqual(before, after, "doctor --json changed the state directory")


if __name__ == "__main__":
    unittest.main(verbosity=2)
