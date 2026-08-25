#!/usr/bin/env python3
"""Regression tests for defects found by stress-testing the real scripts.

Every test here was written against the broken code first and observed to fail; the
comment on each one records what it did before the fix. Nothing is mocked: the real
`bin/skillforge`, `bin/skillreport` and `statusline/skillforge-status.sh` are run as
subprocesses against a real state directory, and their output is read back.

The clock is pinned with SKILLFORGE_NOW so every assertion is deterministic.
"""

import json
import os
import re
import subprocess
import tempfile
import time
import unicodedata
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "skillforge"
REPORT = REPO / "bin" / "skillreport"
RENDER = REPO / "statusline" / "skillforge-status.sh"
PAYLOAD = json.dumps({"session_id": "abc", "workspace": {"current_dir": str(REPO)}})
ANSI = re.compile(r"\033\[[0-9;]*m")

# A renderer that has not printed in this long is not slow, it is stuck. The whole
# defect class below is a status line that never returns while the host asks it to
# refresh once a second, so the cap has to be far under a human's patience and the
# failure has to be fast rather than a hung suite.
RENDER_TIMEOUT = 15


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        (self.state / "forge").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        # A test that chmods the slot directory read-only must not leave it that way,
        # or TemporaryDirectory cleanup fails and the failure lands on a later test.
        d = self.state / "forge"
        if d.exists():
            os.chmod(d, 0o755)
        self.tmp.cleanup()

    def env(self, **extra):
        e = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
             "HOME": str(self.state),
             "SKILL_COMPOUNDER_STATE": str(self.state),
             "SKILL_COMPOUNDER_TRANSCRIPTS": str(self.state / "no-transcripts")}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def forge(self, *args, **envextra):
        return subprocess.run([str(CLI), *args], capture_output=True, text=True,
                              env=self.env(**envextra))

    def report(self, **envextra):
        return subprocess.run([str(REPORT)], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, env=self.env(**envextra))

    def render(self, **envextra):
        """Runs the renderer under a hard timeout and returns its plain-text output."""
        started = time.time()
        try:
            r = subprocess.run([str(RENDER)], input=PAYLOAD, capture_output=True,
                               text=True, env=self.env(**envextra),
                               timeout=RENDER_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the renderer did not finish in %ds with %r -- the status line "
                      "refreshes once a second, so stuck renderers accumulate without "
                      "bound" % (RENDER_TIMEOUT, envextra))
        self.assertLess(time.time() - started, RENDER_TIMEOUT)
        self.assertEqual(r.stderr, "", "the renderer wrote to stderr")
        return ANSI.sub("", r.stdout)

    def write_ledger(self, *records):
        (self.state / "ledger.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


# --------------------------------------------------------------------------------
# 1. A knob value that hangs the status line permanently
# --------------------------------------------------------------------------------

class WidthKnobTest(Base):
    """`SKILLFORGE_BAR_WIDTH=999999` passed the six-digit guard and then ran a million
    `bar="${bar}·"` appends: still running after 20 seconds, once a second, forever.
    `=9999` "succeeded" in ~2s and emitted a 10,070-column line. TAIL_WIDTH=999999
    emitted a 1,000,044-column line. Six digits constrains shape, not magnitude, and
    magnitude is what breaks a line that must never wrap."""

    # Wider than any terminal a status line is rendered into. Every knob is a fraction
    # of one line, so a segment past this has wrapped whatever the value "meant".
    MAX_COLUMNS = 500

    def setUp(self):
        super().setUp()
        self.forge("start", "widthy", "8", "a summary", SKILLFORGE_NOW=1000)

    def test_an_absurd_bar_width_neither_hangs_nor_wraps(self):
        for value in ("999999", "99999", "9999", "1000", "201"):
            with self.subTest(value=value):
                out = self.render(SKILLFORGE_NOW=1000, SKILLFORGE_BAR_WIDTH=value)
                self.assertIn("widthy", out, "the segment vanished")
                self.assertLess(len(out), self.MAX_COLUMNS,
                                "SKILLFORGE_BAR_WIDTH=%s drew a line no terminal can "
                                "show" % value)

    def test_an_absurd_tail_width_neither_hangs_nor_wraps(self):
        for value in ("999999", "99999", "9999", "401"):
            with self.subTest(value=value):
                out = self.render(SKILLFORGE_NOW=1000, SKILLFORGE_TAIL_WIDTH=value)
                self.assertIn("widthy", out)
                self.assertLess(len(out), self.MAX_COLUMNS,
                                "SKILLFORGE_TAIL_WIDTH=%s drew a line no terminal can "
                                "show" % value)

    def test_an_absurd_name_width_neither_hangs_nor_wraps(self):
        out = self.render(SKILLFORGE_NOW=1000, SKILLFORGE_NAME_WIDTH="999999")
        self.assertIn("widthy", out)
        self.assertLess(len(out), self.MAX_COLUMNS)

    def test_a_width_a_terminal_can_show_is_still_honoured(self):
        """The bound must reject what cannot render, not every value but the default."""
        wide = self.render(SKILLFORGE_NOW=1000, SKILLFORGE_BAR_WIDTH="40")
        plain = self.render(SKILLFORGE_NOW=1000)
        self.assertGreater(len(wide), len(plain), "a usable width was rejected too")
        self.assertLess(len(wide), self.MAX_COLUMNS)


# --------------------------------------------------------------------------------
# 2 + 7. The ledger silently under-reports, and never showed the budget
# --------------------------------------------------------------------------------

class UnmatchedOutcomeTest(Base):
    """`skillforge start` claims its slot with `ln` and appends its ledger row a moment
    later; killed between the two it leaves a live forge with no `start` row (4 of 60
    SIGKILL trials). Both the ledger view and skillreport joined by walking start
    records only, so the eventual `done` was DISCARDED IN SILENCE -- a planted
    `ghost-one` record produced output reading "6 forge(s)" that never mentioned it.
    The forges that get dropped are exactly the ones that crashed."""

    def plant(self):
        self.write_ledger(
            {"event": "start", "name": "normal", "ts": 100, "steps": 8,
             "summary": "s", "project": "/p/normal"},
            {"event": "done", "name": "normal", "ts": 120, "steps": 8, "summary": "s",
             "project": "/p/normal", "step": 8, "phase": "ok", "duration": 20,
             "rounds": 3, "rounds_planned": 3},
            {"event": "done", "name": "ghost-one", "ts": 200, "steps": 8,
             "summary": "g", "project": "/p/ghost", "step": 8, "phase": "crashed early",
             "duration": 5, "rounds": 3, "rounds_planned": 3},
        )

    def test_the_ledger_view_names_an_outcome_with_no_start(self):
        self.plant()
        out = self.forge("ledger").stdout
        self.assertIn("ghost-one", out, "an outcome with no start was dropped silently")
        self.assertIn("2 forge(s)", out, "the unmatched outcome was not counted")
        self.assertIn("*", out, "the unmatched outcome was not distinguished")
        self.assertIn("no matching start", out,
                      "nothing told the reader why the row is different")

    def test_skillreport_names_an_outcome_with_no_start(self):
        self.plant()
        out = self.report().stdout
        self.assertIn("ghost-one", out, "skillreport dropped an unmatched outcome")
        self.assertIn("no matching start", out)
        self.assertIn("done*", out, "the unmatched outcome was not distinguished")

    def test_a_matched_outcome_is_never_reported_as_unmatched(self):
        self.plant()
        out = self.forge("ledger").stdout
        normal = [ln for ln in out.splitlines() if " normal " in ln]
        self.assertEqual(len(normal), 1, out)
        self.assertNotIn("*", normal[0], "a joined outcome was marked unmatched")

    def test_a_real_kill_between_slot_claim_and_ledger_row_is_still_visible(self):
        """Not a planted record: the state this produces is reached by killing `start`,
        and the recovery path is the same one."""
        self.forge("start", "crashed", "8", "s", SKILLFORGE_NOW=1000)
        # Reproduce the crash by removing the start row the process would not have
        # written, leaving the live slot exactly as a SIGKILL leaves it.
        lines = (self.state / "ledger.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        (self.state / "ledger.jsonl").write_text("", encoding="utf-8")
        self.forge("step", "6", "still going", SKILLFORGE_NOW=1010)
        self.forge("done", "finished anyway", SKILLFORGE_NOW=1020)
        out = self.forge("ledger").stdout
        self.assertIn("crashed", out,
                      "a forge whose start row was lost to a kill vanished entirely")
        self.assertIn("1 forge(s)", out)


class OverrunReportingTest(Base):
    """`rounds_planned` has been in the JSONL since the overrun was made representable
    and nothing ever printed it, so a forge that ran six rounds against a three-round
    budget read as a plain "6 round(s)" -- indistinguishable from one that spent
    exactly what it planned."""

    def run_overrun(self):
        self.forge("start", "over-one", "8", "s", SKILLFORGE_NOW=100)
        self.forge("step", "14", "past the budget", SKILLFORGE_NOW=110)
        self.forge("done", SKILLFORGE_NOW=120)
        rec = json.loads((self.state / "ledger.jsonl").read_text().splitlines()[-1])
        self.assertEqual((rec["rounds"], rec["rounds_planned"]), (6, 3),
                         "the fixture is not an overrun")

    def test_the_ledger_view_shows_the_budget_that_was_overrun(self):
        self.run_overrun()
        out = self.forge("ledger").stdout
        self.assertIn("6 of 3 round(s)", out,
                      "an overrun read as a plain round count:\n" + out)
        self.assertIn("(over)", out)

    def test_skillreport_shows_the_budget_that_was_overrun(self):
        self.run_overrun()
        out = self.report().stdout
        self.assertIn("6/3", out, "skillreport read an overrun as a plain count:\n" + out)
        self.assertIn("completed/planned", out, "nothing explained the second number")

    def test_a_forge_that_spent_its_budget_exactly_still_reads_plainly(self):
        self.forge("start", "on-plan", "8", "s", SKILLFORGE_NOW=100)
        self.forge("step", "8", "done stepping", SKILLFORGE_NOW=110)
        self.forge("done", SKILLFORGE_NOW=120)
        out = self.forge("ledger").stdout
        self.assertIn("3 round(s)", out)
        self.assertNotIn("(over)", out)


# --------------------------------------------------------------------------------
# 4. The documented rotation ceiling did not hold
# --------------------------------------------------------------------------------

class RotationCeilingTest(Base):
    """`SKILLFORGE_ROTATE_SECS=3600` hid every forge but one for a full hour while
    `[2/3]` truthfully reported three -- the precise defect rotation exists to prevent,
    reached by the documented ceiling value itself, because the guard was `-gt 3600`."""

    def names_seen(self, span, **envextra):
        seen = set()
        for t in range(1000, 1000 + span):
            out = self.render(SKILLFORGE_NOW=t, **envextra)
            for nm in ("alpha", "bravo", "charlie"):
                if nm in out:
                    seen.add(nm)
        return seen

    def test_no_rotation_period_can_hide_a_forge_for_minutes(self):
        for nm in ("alpha", "bravo", "charlie"):
            self.forge("start", nm, "8", "s", SKILLFORGE_NOW=900)
        for value in ("3600", "3599", "61"):
            with self.subTest(value=value):
                seen = self.names_seen(62, SKILLFORGE_ROTATE_SECS=value)
                self.assertEqual(seen, {"alpha", "bravo", "charlie"},
                                 "SKILLFORGE_ROTATE_SECS=%s hid %s for over a minute "
                                 "while the counter said there were three"
                                 % (value, {"alpha", "bravo", "charlie"} - seen))

    def test_a_usable_rotation_period_is_still_honoured(self):
        for nm in ("alpha", "bravo"):
            self.forge("start", nm, "8", "s", SKILLFORGE_NOW=900)
        # 30s is under the ceiling, so it must actually pin the pick for 30 seconds.
        picks = {re.search(r"forge (\S+)", self.render(
                     SKILLFORGE_NOW=t, SKILLFORGE_ROTATE_SECS=30)).group(1)
                 for t in range(1200, 1215)}
        self.assertEqual(len(picks), 1, "a legal rotation period was ignored")


# --------------------------------------------------------------------------------
# 5. `skillforge step` leaked the shell's own error
# --------------------------------------------------------------------------------

class StepErrorTest(Base):
    """`jq "$@" "$f" > "$tmp" 2>/dev/null` cannot suppress the diagnostic, because a
    redirect that cannot open its target is reported by the SHELL, not by jq. The user
    saw `.../skillforge: line 66: ...tmp.28218: Permission denied` above the tidy
    message. `start` already wraps the whole group; `step` did not."""

    def test_an_unwritable_slot_directory_reports_only_the_tidy_message(self):
        self.forge("start", "locked", "8", "s", SKILLFORGE_NOW=100)
        os.chmod(self.state / "forge", 0o555)
        try:
            r = self.forge("step", "3", "phase", SKILLFORGE_NOW=110)
        finally:
            os.chmod(self.state / "forge", 0o755)
        self.assertEqual(r.returncode, 2)
        self.assertIn("skillforge: could not update", r.stderr)
        self.assertNotIn("Permission denied", r.stderr,
                         "the shell's own diagnostic leaked:\n" + r.stderr)
        self.assertNotIn("line ", r.stderr,
                         "a shell line number leaked to the user:\n" + r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)


# --------------------------------------------------------------------------------
# 6. Orphan temp files accumulated forever
# --------------------------------------------------------------------------------

class TempReapTest(Base):
    """29 `.start.<pid>.<ts>.tmp` files survived 60 SIGKILLs and nothing reaped them.
    They are invisible to the renderer, so the only symptom is a slot directory that
    grows without bound."""

    def temps(self):
        return sorted(p.name for p in (self.state / "forge").iterdir()
                      if not p.name.endswith(".json"))

    def test_an_abandoned_temp_file_is_eventually_reaped(self):
        d = self.state / "forge"
        old_start = d / ".start.999.111.tmp"
        old_update = d / "gone.forge.json.tmp.42"
        for p in (old_start, old_update):
            p.write_text("{}", encoding="utf-8")
            os.utime(p, (time.time() - 7200, time.time() - 7200))
        self.assertEqual(self.temps(), [old_start.name, old_update.name])
        self.forge("start", "fresh", "8", "s", SKILLFORGE_NOW=100)
        self.assertEqual(self.temps(), [],
                         "orphan temp files accumulate forever")

    def test_a_temp_file_a_live_writer_may_own_is_left_alone(self):
        """Age, not existence, is the test: a young temp may belong to a concurrent
        `start` that is still running, and deleting it would corrupt that forge."""
        young = self.state / "forge" / ".start.888.222.tmp"
        young.write_text("{}", encoding="utf-8")
        self.forge("start", "fresh", "8", "s", SKILLFORGE_NOW=100)
        self.assertEqual(self.temps(), [young.name],
                         "a temp file young enough to have a live writer was deleted")

    def test_reaping_never_makes_a_temp_file_visible_as_a_slot(self):
        d = self.state / "forge"
        p = d / ".start.777.333.tmp"
        p.write_text(json.dumps({"name": "phantom", "status": "active", "step": 1,
                                 "steps": 8, "started": 50}), encoding="utf-8")
        self.forge("start", "fresh", "8", "s", SKILLFORGE_NOW=100)
        self.assertNotIn("phantom", self.forge("list").stdout)
        self.assertNotIn("phantom", self.render(SKILLFORGE_NOW=100))


# --------------------------------------------------------------------------------
# 8. Cheap if cheap
# --------------------------------------------------------------------------------

class CheapGuardsTest(Base):

    def test_a_nonsense_clock_names_the_clock_not_the_directory(self):
        """`SKILLFORGE_NOW=abc` reached `--argjson now abc`; jq failed and the only
        thing `start` could report was its fallback -- "could not write to .../forge
        (is it writable?)" against a perfectly writable directory."""
        r = self.forge("start", "x", "5", "s", SKILLFORGE_NOW="abc")
        self.assertEqual(r.returncode, 2)
        self.assertIn("SKILLFORGE_NOW", r.stderr, r.stderr)
        self.assertNotIn("is it writable", r.stderr,
                         "the message blamed the directory:\n" + r.stderr)
        self.assertTrue(os.access(self.state / "forge", os.W_OK),
                        "the fixture directory really is writable")

    def test_a_foreign_record_cannot_break_the_list_table(self):
        """A foreign `"step": {"a":1}` was printed by `field` with -r, which
        pretty-prints a container: raw newlines landed mid-row and split one forge
        across three lines of a fixed-width table."""
        (self.state / "forge" / "weird.json").write_text(
            json.dumps({"name": "weird", "status": "active", "step": {"a": 1},
                        "steps": 4, "phase": "one\ntwo", "started": 50}),
            encoding="utf-8")
        self.forge("start", "sane", "8", "s", SKILLFORGE_NOW=100)
        lines = self.forge("list").stdout.rstrip("\n").split("\n")
        self.assertEqual(len(lines), 3, "the table gained rows:\n" + "\n".join(lines))
        self.assertTrue(any(ln.startswith("weird") for ln in lines), lines)
        self.assertTrue(any(ln.startswith("sane") for ln in lines), lines)

    def test_every_blocking_forge_is_named_when_a_command_refuses(self):
        """`${list:+, }` dropped a blank name silently, so `step` refused while naming
        three forges when four were blocking it -- and the one it would not name is the
        one the user cannot clear without being told which file it is."""
        (self.state / "forge" / "blank.json").write_text(
            json.dumps({"name": "", "status": "active", "step": 1, "steps": 4,
                        "phase": "p", "started": 60}), encoding="utf-8")
        for nm in ("bee", "cee", "dee"):
            self.forge("start", nm, "4", "s", SKILLFORGE_NOW=100)
        r = self.forge("step", "2", "x", SKILLFORGE_NOW=200)
        self.assertEqual(r.returncode, 2)
        named = r.stderr.split(" are all live")[0].split(", ")
        self.assertEqual(len(named), 4,
                         "refused over 4 forges while naming %d:\n%s"
                         % (len(named), r.stderr))
        self.assertIn("blank.json", r.stderr,
                      "the unnameable record was counted but not identified")

    def test_list_and_the_refusal_agree_about_what_is_live(self):
        (self.state / "forge" / "blank.json").write_text(
            json.dumps({"name": "", "status": "active", "step": 1, "steps": 4,
                        "phase": "p", "started": 60}), encoding="utf-8")
        self.forge("start", "bee", "4", "s", SKILLFORGE_NOW=100)
        rows = self.forge("list").stdout.rstrip("\n").split("\n")[1:]
        self.assertEqual(len(rows), 2, rows)
        self.assertTrue(any("blank.json" in ln for ln in rows),
                        "`list` showed a blank row where the refusal names a file")


# --------------------------------------------------------------------------------
# Found by a cold reviewer against the fixes above, and reproduced before acting.
# --------------------------------------------------------------------------------

def columns(text):
    """Terminal cells, counting a wide codepoint as two and a combining mark as none."""
    t = ANSI.sub("", text)
    return sum(0 if unicodedata.combining(c) or c in "\u200b\u200d\ufeff"
               else (2 if unicodedata.east_asian_width(c) in "WF" else 1) for c in t)


class JoinClaimsEachOutcomeOnceTest(Base):
    """Matching by name alone let one `done` be consumed by TWO starts of the same
    name: `start alpha` -> slot file lost -> `start alpha` -> `done` reported two
    finished forges, the abandoned one wearing the other's date, duration and phase.
    That inflates the denominator of the one number skillreport exists to produce."""

    def two_starts_one_done(self):
        self.forge("start", "alpha", "8", "s", SKILLFORGE_NOW=1000)
        for f in (self.state / "forge").glob("*.json"):
            f.unlink()
        self.forge("start", "alpha", "8", "s", SKILLFORGE_NOW=2000)
        self.forge("done", SKILLFORGE_NOW=2100)

    def test_the_ledger_view_closes_out_only_one_of_them(self):
        self.two_starts_one_done()
        out = self.forge("ledger").stdout
        self.assertIn("2 forge(s): 1 done, 0 abandoned, 1 never closed out", out, out)
        self.assertEqual(out.count("[done]"), 1, out)
        self.assertEqual(out.count("[no outcome]"), 1, out)

    def test_skillreport_counts_only_one_of_them_as_finished(self):
        self.two_starts_one_done()
        out = self.report().stdout
        self.assertIn("0 of 1 finished forges", out,
                      "an abandoned forge was counted as finished:\n" + out)

    def test_an_outcome_claimed_by_a_start_is_not_also_an_orphan(self):
        self.two_starts_one_done()
        out = self.forge("ledger").stdout
        self.assertNotIn("*", out, "a claimed outcome was also reported unmatched")


class OrphanFootnoteTest(Base):
    """The footnote asserted a cause it cannot know. `skillforge`'s own header invites
    deleting the ledger at any time, and doing so mid-forge produces the same orphan;
    the note claimed the process had been killed."""

    def test_the_note_does_not_assert_one_cause_as_fact(self):
        self.forge("start", "beta", "8", "s", SKILLFORGE_NOW=1000)
        (self.state / "ledger.jsonl").unlink()
        self.forge("done", SKILLFORGE_NOW=1100)
        for out in (self.forge("ledger").stdout, self.report().stdout):
            self.assertIn("no matching start record", out, out)
            self.assertIn("or when the ledger was truncated", out,
                          "the note gave one cause as fact:\n" + out)


class SegmentFitsOneLineTest(Base):
    """Each width knob was bounded on its own and they still summed past the line:
    SKILLFORGE_TAIL_WIDTH=400 alone rendered 445 columns and 200/400/400 rendered 629,
    both past the ceiling the bound was named for."""

    MAX = 400

    def setUp(self):
        super().setUp()
        self.forge("start", "a-name", "8", "summary", SKILLFORGE_NOW=1000)

    def test_no_combination_of_width_knobs_wraps_the_line(self):
        combos = [{"SKILLFORGE_TAIL_WIDTH": "400"},
                  {"SKILLFORGE_NAME_WIDTH": "400"},
                  {"SKILLFORGE_BAR_WIDTH": "200"},
                  {"SKILLFORGE_TAIL_WIDTH": "300"},
                  {"SKILLFORGE_BAR_WIDTH": "200", "SKILLFORGE_TAIL_WIDTH": "400",
                   "SKILLFORGE_NAME_WIDTH": "400"},
                  {"SKILLFORGE_BAR_WIDTH": "100", "SKILLFORGE_TAIL_WIDTH": "200",
                   "SKILLFORGE_NAME_WIDTH": "50"}]
        for combo in combos:
            with self.subTest(**combo):
                got = columns(self.render(SKILLFORGE_NOW=1000, **combo))
                self.assertLessEqual(got, self.MAX,
                                     "%r rendered %d columns" % (combo, got))
                self.assertGreater(got, 0)


class TableTruncationTest(Base):
    """`printf '%.28s'` and `%-28s` are BYTE-based: a CJK forge name was cut
    mid-character, so a stray \347 reached the terminal, and padded to 28 bytes rather
    than 28 columns, shifting every later column of the table."""

    LONG_CJK = "スキルを鍛える段階のとても長い名前です本当に長い"

    def test_a_wide_name_is_never_cut_mid_character(self):
        self.forge("start", self.LONG_CJK, "8", "s", SKILLFORGE_NOW=1000)
        r = subprocess.run([str(CLI), "list"], capture_output=True, env=self.env())
        r.stdout.decode("utf-8")   # raises on the stray byte the old cut produced
        self.assertEqual(r.returncode, 0)

    def test_a_wide_name_keeps_the_table_columns_aligned(self):
        self.forge("start", self.LONG_CJK, "8", "s", SKILLFORGE_NOW=1000)
        self.forge("start", "short", "8", "s", SKILLFORGE_NOW=1001)
        rows = self.forge("list").stdout.rstrip("\n").split("\n")[1:]
        self.assertEqual(len(rows), 2, rows)
        starts = {columns(r[:r.index("active")]) for r in rows}
        self.assertEqual(len(starts), 1,
                         "the STATE column landed in two different places: %r" % rows)


class ReportKnobTest(Base):
    """CI_EDIT_EVERY reaches integer arithmetic twice and was unguarded: `abc` aborted
    the whole script mid-report under `set -u`, and `0` divided by zero. Either way the
    reminder section reported the wrong reason or never printed at all."""

    def setUp(self):
        super().setUp()
        self.forge("start", "gamma", "8", "s", SKILLFORGE_NOW=1000)
        (self.state / "reminders").mkdir(parents=True, exist_ok=True)
        (self.state / "reminders" / "s.edits").write_text("60", encoding="utf-8")

    def test_a_nonsense_edit_interval_neither_aborts_nor_lies(self):
        for value in ("abc", "0", "-1", "", " ", "9" * 40):
            with self.subTest(value=value):
                r = subprocess.run([str(REPORT)], capture_output=True, text=True,
                                   stdin=subprocess.DEVNULL,
                                   env=self.env(CI_EDIT_EVERY=value))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stderr, "", r.stderr)
                self.assertIn("rough conversion:", r.stdout,
                              "the reminder section was lost:\n" + r.stdout)
                self.assertNotIn("no checkpoints implied yet", r.stdout,
                                 "60 edits implied no checkpoints:\n" + r.stdout)


class QuietRefusalTest(Base):

    def test_show_with_a_name_that_matches_nothing_is_an_error(self):
        """`show --name typo` answered "no active forge" at exit 0 -- which is what a
        quiet system prints -- so a typo read as "your forge finished"."""
        self.forge("start", "real", "8", "s", SKILLFORGE_NOW=1000)
        r = self.forge("show", "--name", "nope")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no forge named 'nope'", r.stderr)

    def test_clear_with_nothing_to_clear_does_not_claim_it_cleared(self):
        r = self.forge("clear")
        self.assertEqual(r.returncode, 0)
        self.assertIn("nothing to clear", r.stdout, r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
