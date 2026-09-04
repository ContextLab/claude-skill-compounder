#!/usr/bin/env python3
"""Tests for the LESSON surfaces of bin/skillrepeat: `dismiss`, the LESSON column, and
what `show` prints about a lesson and a cross-tool recovery.

WHY A SECOND FILE. tests/test_repeat_gate.py drives the hook and the CLI together and is
already the longest file in the suite; what is here is the CLI reading two files it does
NOT write -- hooks/repeat-gate.sh's store and bin/skillnote's ledger -- which is a
different seam with a different way of going wrong. It runs as its own process under
run_tests.sh like every other file, so it registers itself by existing.

NO MOCKS, per this repo's standing rule. Every store row below is written by the REAL
hook from a real payload, every command is the real CLI through subprocess, and every
assertion reads what actually landed on disk. The one place a fixture is written by hand
is the ledger, and only where bin/skillnote cannot yet write it: `--lesson` is landing in
a parallel change, so `LiveSkillnoteTest` drives the real CLI the moment it can and says
out loud, by skipping, when it cannot. A hand-written ledger row that nothing ever
compared against the real writer is exactly the defect this repo recorded on 2026-09-02
-- a test that pins whichever side its author was looking at.

THE CONTRACT with bin/skillnote is one ledger row:
    {"event":"note", ..., "lesson_sig":"<the repeat signature>"}
This file reads it. It never writes one except to stand in for a writer that does not
exist yet, and `LiveSkillnoteTest` is what stops that standing in from becoming the
definition.

Clocks are pinned with REPEAT_GATE_NOW (the hook's) and SKILLREPEAT_NOW (this CLI's), and
`input=` is passed on every subprocess against the hook: it reads its payload with
`payload="$(cat)"` and hangs forever without one.
"""

import json
import os
import shutil
import subprocess
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "repeat-gate.sh")
CLI = os.path.join(REPO, "bin", "skillrepeat")
NOTE_CLI = os.path.join(REPO, "bin", "skillnote")

BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
GH_ERR = "Exit code 127\ngh: command not found"

# THE CANONICAL FAIL-THEN-FIX PAIR, AND IT SHARES CONTENT TOKENS ON PURPOSE.
# Since 2026-09-03 a same-tool `Bash` binding wants REPEAT_SAME_TOOL_MIN_TOKENS (2) content
# tokens in common with the call that failed (THE SAME-TOOL RULE IS NOT EVIDENCE FOR A
# SHELL, in hooks/repeat-gate.sh). `gh pr list --limit 5` -> `curl -s https://...` shares
# NONE of them -- the URL is masked to `<P>` before tokens are taken -- so a fixture built
# on that pair records no recovery at all and every column that reads one goes empty.
# These two share `list` and `limit`.
FAILING_CMD = "gh pr list --limit 5"
FIX_CMD = "gh pr list --limit 5 --repo ContextLab/claude-skill-compounder"


def skillnote_has_lesson():
    """Does THIS checkout's bin/skillnote take `--lesson`? Run it and read the answer,
    rather than deciding from a version number or from this file's own age."""
    if not os.path.exists(NOTE_CLI):
        return False
    try:
        r = subprocess.run(["bash", NOTE_CLI, "--help"], input="", capture_output=True,
                           text=True, timeout=60,
                           env={"PATH": BASE_PATH, "HOME": "/tmp"})
    except (OSError, subprocess.SubprocessError):
        return False
    return "--lesson" in (r.stdout + r.stderr)


HAVE_LESSON = skillnote_has_lesson()


class RepeatCliCase(unittest.TestCase):
    """One temp state root per test; real hook, real CLI, real files."""

    def setUp(self):
        self.tmp = os.path.join(
            os.environ.get("TMPDIR", "/tmp"),
            "skillrepeat-%d-%d" % (os.getpid(), int(time.time() * 1e6) % 10 ** 9))
        os.makedirs(self.tmp)
        self.home = os.path.join(self.tmp, "home")
        self.state = os.path.join(self.tmp, "state")
        # A PROJECT DIRECTORY OF ITS OWN, and it is not a convenience. `bin/skillnote add`
        # writes its dated line into the `.claude/CLAUDE.md` of the CURRENT WORKING
        # DIRECTORY, so a subprocess launched with the default cwd writes into THIS
        # REPOSITORY's own CLAUDE.md. That happened here, twice, before this line
        # existed; the guard in `LiveSkillnoteTest` below is what catches a recurrence.
        self.project = os.path.join(self.tmp, "project")
        os.makedirs(self.home)
        os.makedirs(os.path.join(self.project, ".claude"))
        self.clock = 2_000_000

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------- plumbing
    @property
    def store(self):
        return os.path.join(self.state, "repeats", "index.jsonl")

    @property
    def ledger(self):
        return os.path.join(self.state, "ledger.jsonl")

    def env(self, **extra):
        e = {"PATH": BASE_PATH, "HOME": self.home,
             "SKILL_COMPOUNDER_STATE": self.state,
             "REPEAT_GATE_NOW": str(self.clock),
             "SKILLREPEAT_NOW": str(self.clock)}
        for k, v in extra.items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = str(v)
        return e

    def tick(self, n=1):
        self.clock += n
        return self.clock

    def run_hook(self, payload, **env_extra):
        return subprocess.run(["bash", HOOK], input=json.dumps(payload),
                              capture_output=True, text=True,
                              env=self.env(**env_extra), timeout=180)

    def cli(self, *args, **env_extra):
        return subprocess.run(["bash", CLI] + list(args), input="", capture_output=True,
                              text=True, env=self.env(**env_extra), timeout=180)

    def note_cli(self, *args, **env_extra):
        """Run in THIS TEST's project directory. `skillnote add` writes into the
        `.claude/CLAUDE.md` of its cwd, so the default cwd is this repository."""
        return subprocess.run(["bash", NOTE_CLI] + list(args), input="",
                              capture_output=True, text=True, cwd=self.project,
                              env=self.env(SKILLNOTE_NOW=self.clock, **env_extra),
                              timeout=180)

    def rows(self):
        if not os.path.exists(self.store):
            return []
        out = []
        with open(self.store, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
        return out

    # ------------------------------------------------------------------- payloads
    def _base(self, event, command, session, tool, tuid):
        return {"hook_event_name": event, "session_id": session,
                "transcript_path": os.path.join(self.tmp, "t.jsonl"), "cwd": "/repo",
                "prompt_id": "p1", "permission_mode": "acceptEdits", "tool_name": tool,
                "tool_use_id": tuid or ("toolu_%d" % self.clock),
                "tool_input": ({"command": command, "description": "d"}
                               if tool == "Bash" else command)}

    def failure(self, command, session, error=GH_ERR, tool="Bash", tuid=None):
        p = self._base("PostToolUseFailure", command, session, tool, tuid)
        p.update({"error": error, "is_interrupt": False, "duration_ms": 12})
        return p

    def success(self, command, session, tool="Bash", tuid=None):
        p = self._base("PostToolUse", command, session, tool, tuid)
        p.update({"tool_response": {"stdout": "ok"}, "duration_ms": 30})
        return p

    # ------------------------------------------------------------------- scenarios
    def fail_then_fix(self, session, command=FAILING_CMD, fix=FIX_CMD, tool="Bash"):
        self.tick(); self.run_hook(self.failure(command, session, tool=tool))
        self.tick(); self.run_hook(self.success(fix, session))

    def only_fail(self, session, command="gh issue view 4"):
        self.tick(); self.run_hook(self.failure(command, session))

    def sig_of(self, command):
        """The signature the REAL hook wrote for a command, read back off the store."""
        for r in self.rows():
            if r.get("t") == "fail" and r.get("cmd") == command:
                return r["sig"]
        self.fail("no fail row for %r in %r" % (command, self.rows()))

    def lesson_column(self, sig):
        """The LESSON cell for one signature, sliced out of the rendered table by the
        header's own offsets. Nothing here knows a column width."""
        out = self.cli("list").stdout
        hdr = [l for l in out.splitlines() if l.startswith("SIGNATURE")]
        self.assertTrue(hdr, "no table header in:\n%s" % out)
        hdr = hdr[0]
        row = [l for l in out.splitlines() if l.startswith(sig)]
        self.assertEqual(len(row), 1, "no single row for %s in:\n%s" % (sig, out))
        return row[0][hdr.index("LESSON"):hdr.index("CALL")].strip()

    def write_lesson_row(self, sig, text="gh is not on PATH here; curl the API instead.",
                         note_id="n1x1", action="add"):
        """One ledger row in the shape bin/skillnote writes. `LiveSkillnoteTest` is what
        keeps this shape honest -- see the module docstring."""
        with open(self.ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "note", "action": action, "ts": self.clock,
                                 "id": note_id, "kind": "note", "scope": "project",
                                 "text": text, "lesson_sig": sig,
                                 "session": "cli"}) + "\n")
        return note_id

    def write_lesson_removal(self, note_id):
        """`skillnote remove <id>` appends a removal and DELETES NOTHING. The row carries
        the id and not the signature, which is why the join has to be on the id."""
        with open(self.ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "note", "action": "remove", "ts": self.clock,
                                 "id": note_id, "session": "cli"}) + "\n")


# ==================================================================== dismiss
class DismissTest(RepeatCliCase):
    """`dismiss` is the other half of the lesson gate, and it is a ROW. The store is the
    only record of which calls are broken, it is written by a hook nobody watches, and a
    decision that leaves no trace is indistinguishable afterwards from one nobody made."""

    def test_it_appends_a_row_and_deletes_nothing(self):
        self.fail_then_fix("s1")
        before = self.rows()
        sig = self.sig_of("gh pr list --limit 5")
        self.tick()
        r = self.cli("dismiss", sig, "--why", "gh is simply not installed on this box")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = self.rows()
        self.assertEqual(after[:len(before)], before, "an existing row was rewritten")
        self.assertEqual(len(after), len(before) + 1)
        row = after[-1]
        self.assertEqual(row["t"], "dismiss")
        self.assertEqual(row["sig"], sig)
        self.assertEqual(row["ts"], self.clock)
        self.assertEqual(row["session"], "cli")
        self.assertEqual(row["why"], "gh is simply not installed on this box")

    def test_the_clock_is_SKILLREPEAT_NOW(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.cli("dismiss", sig, SKILLREPEAT_NOW=2_500_000)
        self.assertEqual(self.rows()[-1]["ts"], 2500000)

    def test_it_falls_back_to_the_gates_clock(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.cli("dismiss", sig, SKILLREPEAT_NOW=None, REPEAT_GATE_NOW=2_400_000)
        self.assertEqual(self.rows()[-1]["ts"], 2400000)

    def test_a_why_is_optional_and_recorded_as_empty(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.assertEqual(self.cli("dismiss", sig).returncode, 0)
        self.assertEqual(self.rows()[-1]["why"], "")

    def test_the_equals_form_of_why_works_too(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.cli("dismiss", sig, "--why=no lesson needed")
        self.assertEqual(self.rows()[-1]["why"], "no lesson needed")

    def test_an_unknown_signature_is_refused(self):
        """Same refusal `forget` makes, same reason: a mistyped signature that silently
        appended a row matching nothing would look exactly like a successful dismissal,
        and the gate would go on declining calls over a signature the user believes they
        have cleared."""
        self.fail_then_fix("s1")
        r = self.cli("dismiss", "cNOPEx1-eNOPEx1", "--why", "x")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("nothing to dismiss", r.stderr)
        self.assertEqual([x for x in self.rows() if x["t"] == "dismiss"], [])

    def test_no_signature_is_a_usage_error(self):
        r = self.cli("dismiss")
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage: skillrepeat dismiss", r.stderr)

    def test_two_signatures_is_a_usage_error(self):
        r = self.cli("dismiss", "a", "b")
        self.assertEqual(r.returncode, 2)
        self.assertIn("one signature at a time", r.stderr)

    def test_an_unknown_flag_is_a_usage_error(self):
        r = self.cli("dismiss", "--nope", "sig")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown argument", r.stderr)

    def test_it_appears_in_the_usage_text(self):
        r = self.cli("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("skillrepeat dismiss <sig>", r.stdout)
        # ...and the older subcommands did not fall off the end of the sed range that
        # prints this block, which is the way a usage list loses a line.
        for sub in ("list", "show", "forget", "stats", "--help"):
            self.assertIn("skillrepeat %s" % sub, r.stdout)

    def test_it_is_not_forget(self):
        """The easy mistake, and the one thing that must not be true: a dismissal
        suppresses nothing. Every count is identical before and after."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        before = json.loads(self.cli("stats", "--json").stdout)
        sig = self.sig_of("gh pr list --limit 5")
        self.tick()
        self.cli("dismiss", sig, "--why", "known")
        after = json.loads(self.cli("stats", "--json").stdout)
        for key in ("failures", "recoveries", "tombstones", "signatures", "refusing",
                    "with_recovery"):
            self.assertEqual(before[key], after[key], key)
        entry = json.loads(self.cli("list", "--json").stdout)[0]
        self.assertEqual(entry["sessions"], 2)
        self.assertEqual(entry["suppressed"], 0)
        self.assertFalse(entry["forgotten"])
        # ...and a `forget` on the same signature, which is the command it is NOT, does
        # move exactly those numbers.
        self.tick()
        self.cli("forget", sig)
        forgotten = json.loads(self.cli("list", "--json", "--all").stdout)[0]
        self.assertTrue(forgotten["forgotten"])
        self.assertEqual(forgotten["sessions"], 0)


# ==================================================================== the LESSON column
class LessonColumnTest(RepeatCliCase):
    """Four values, and `-` means something DIFFERENT from `open`: nothing is written down
    about either, but `-` is a signature no session ever recovered from, so there is no fix
    to write down and nothing is owed."""

    def test_a_recovered_signature_is_open(self):
        self.fail_then_fix("s1")
        self.assertEqual(self.lesson_column(self.sig_of("gh pr list --limit 5")), "open")

    def test_a_signature_that_never_recovered_is_a_dash(self):
        self.only_fail("s1")
        self.assertEqual(self.lesson_column(self.sig_of("gh issue view 4")), "-")

    def test_a_dismissal_makes_it_dismissed(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.tick()
        self.cli("dismiss", sig, "--why", "known")
        self.assertEqual(self.lesson_column(sig), "dismissed")

    def test_a_lesson_ledger_row_makes_it_recorded(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.write_lesson_row(sig)
        self.assertEqual(self.lesson_column(sig), "recorded")

    def test_a_ledger_row_for_another_signature_changes_nothing(self):
        """NON-VACUITY: the join is on the signature, not on the existence of a ledger."""
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.write_lesson_row("cOTHERx1-eOTHERx1")
        self.assertEqual(self.lesson_column(sig), "open")

    def test_a_removed_note_is_not_a_recorded_lesson(self):
        """The ledger is append-only on BOTH sides: `skillnote remove` appends a removal
        and leaves the add row where it was. A reader matching on `lesson_sig` alone would
        print `recorded` for a lesson that is no longer in any CLAUDE.md at all."""
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        note_id = self.write_lesson_row(sig, note_id="n7x7")
        self.assertEqual(self.lesson_column(sig), "recorded")
        self.tick()
        self.write_lesson_removal(note_id)
        self.assertEqual(self.lesson_column(sig), "open")

    def test_a_removal_of_another_note_leaves_this_one_recorded(self):
        """NON-VACUITY: the subtraction is by id, not by the mere presence of a removal."""
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.write_lesson_row(sig, note_id="n7x7")
        self.write_lesson_removal("n8x8")
        self.assertEqual(self.lesson_column(sig), "recorded")

    def test_a_second_lesson_survives_the_first_being_removed(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.write_lesson_row(sig, note_id="n7x7")
        self.write_lesson_row(sig, note_id="n9x9", text="and the token has to be exported")
        self.write_lesson_removal("n7x7")
        self.assertEqual(self.lesson_column(sig), "recorded")

    def test_a_row_with_no_action_field_is_read_as_an_add(self):
        """Rows written before `action` existed carry none, and dropping them would
        silently un-record every lesson recorded before that field landed."""
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        with open(self.ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "note", "ts": 1, "id": "nOld",
                                 "lesson_sig": sig, "text": "an older row"}) + "\n")
        self.assertEqual(self.lesson_column(sig), "recorded")

    def test_a_dismissal_outranks_a_lesson(self):
        """Both recorded is not a contradiction and needs no resolution rule beyond an
        order: the column reports the decision that ends the demand, and `dismissed` is
        the more specific of the two facts."""
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.write_lesson_row(sig)
        self.tick()
        self.cli("dismiss", sig, "--why", "known")
        self.assertEqual(self.lesson_column(sig), "dismissed")

    def test_the_json_carries_the_same_three_facts(self):
        self.fail_then_fix("s1")
        self.only_fail("s2")
        by_sig = {e["sig"]: e for e in json.loads(self.cli("list", "--json").stdout)}
        rec = by_sig[self.sig_of("gh pr list --limit 5")]
        self.assertTrue(rec["recovered"])
        self.assertFalse(rec["lesson_recorded"])
        self.assertFalse(rec["lesson_dismissed"])
        never = by_sig[self.sig_of("gh issue view 4")]
        self.assertFalse(never["recovered"])

    def test_a_self_recovery_still_counts_as_recovered(self):
        """`candidates` cannot answer whether a lesson is owed: it counts only recoveries
        that could be NAMED as the fix, so a signature whose every recovery was a
        self-recovery has candidates 0 and is still a fail-then-fix."""
        self.tick(); self.run_hook(self.failure("gh pr list --limit 5", "s1",
                                                error="Exit code 1\nconnection reset"))
        self.tick(); self.run_hook(self.success("gh pr list --limit 5", "s1"))
        entry = json.loads(self.cli("list", "--json").stdout)[0]
        self.assertEqual(entry["candidates"], 0)
        self.assertTrue(entry["recovered"])
        self.assertEqual(self.lesson_column(entry["sig"]), "open")

    def test_the_legend_explains_every_value_the_column_can_print(self):
        """A legend that stops naming a value is how a column becomes unreadable. The
        values are read out of the CLI's own jq rather than restated here."""
        self.fail_then_fix("s1")
        with open(CLI, encoding="utf-8") as fh:
            body = fh.read()
        i = body.index("(if .lesson_dismissed")
        alts = [a for a in
                __import__("re").findall(r'"([^"]*)"', body[i:body.index("end)", i)])]
        self.assertTrue(alts)
        out = self.cli("list").stdout
        for alt in alts:
            if alt == "-":
                self.assertIn("       -         =", out, out)
            else:
                self.assertIn("%s " % alt, out, "LESSON value %r is unexplained" % alt)

    def test_a_malformed_ledger_does_not_take_the_cli_out(self):
        """The ledger is another program's file. A half-written line landing in it must
        not stop this CLI reading the store it does own."""
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        with open(self.ledger, "w", encoding="utf-8") as fh:
            fh.write("{not json at all\n")
            fh.write(json.dumps({"event": "note", "lesson_sig": sig}) + "\n")
            fh.write("[1,2,3]\n")
        r = self.cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.lesson_column(sig), "recorded")

    def test_no_ledger_at_all_reports_open_rather_than_an_error(self):
        self.fail_then_fix("s1")
        self.assertFalse(os.path.exists(self.ledger))
        r = self.cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.lesson_column(self.sig_of("gh pr list --limit 5")), "open")

    def test_an_unreadable_ledger_reports_open_rather_than_an_error(self):
        self.fail_then_fix("s1")
        with open(self.ledger, "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        os.chmod(self.ledger, 0)
        try:
            r = self.cli("list")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.lesson_column(self.sig_of("gh pr list --limit 5")),
                             "open")
        finally:
            os.chmod(self.ledger, 0o644)


# ==================================================================== show
class ShowTest(RepeatCliCase):

    def test_it_prints_the_dismiss_row_verbatim(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.tick()
        self.cli("dismiss", sig, "--why", "gh is deliberately absent on this box")
        out = self.cli("show", sig).stdout
        self.assertIn("dismiss  session=cli", out)
        self.assertIn("why:   gh is deliberately absent on this box", out)
        self.assertIn("lesson:    dismissed", out)

    def test_a_dismiss_row_with_no_reason_says_so(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.cli("dismiss", sig)
        self.assertIn("(no reason given)", self.cli("show", sig).stdout)

    def test_it_names_a_recorded_lesson(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.write_lesson_row(sig)
        out = self.cli("show", sig).stdout
        self.assertIn("lesson:    recorded", out)
        self.assertIn("ledger.jsonl", out)

    def test_it_says_when_nothing_is_written_down(self):
        self.fail_then_fix("s1")
        out = self.cli("show", self.sig_of("gh pr list --limit 5")).stdout
        self.assertIn("lesson:    none written", out)

    def test_it_says_nothing_about_a_lesson_where_none_is_owed(self):
        self.only_fail("s1")
        out = self.cli("show", self.sig_of("gh issue view 4")).stdout
        self.assertNotIn("lesson:", out)

    def test_a_cross_tool_recovery_is_marked_as_such(self):
        """A cross-tool binding is weaker evidence than a same-tool one -- it was matched
        on shared content tokens -- and `show` is where that has to be visible."""
        self.tick()
        self.run_hook(self.failure({"repo": "claude-skill-compounder"}, "s1",
                                   error="Exit code 1\nHTTP 403: not accessible",
                                   tool="mcp__github__create_issue"))
        self.tick()
        self.run_hook(self.success("gh repo view claude-skill-compounder", "s1"))
        sig = [r for r in self.rows() if r["t"] == "fail"][0]["sig"]
        out = self.cli("show", sig).stdout
        self.assertIn("bound cross-tool", out)
        self.assertIn("cross-tool: 1 of the recoveries", out)

    def test_a_same_tool_recovery_is_not_marked_cross_tool(self):
        self.fail_then_fix("s1")
        out = self.cli("show", self.sig_of("gh pr list --limit 5")).stdout
        self.assertNotIn("cross-tool", out)

    def test_the_json_form_is_untouched_by_any_of_this(self):
        """`show --json` is every row verbatim, and a dismissal is a row like the others."""
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.cli("dismiss", sig, "--why", "known")
        got = json.loads(self.cli("show", sig, "--json").stdout)
        self.assertEqual([r["t"] for r in got], ["fail", "recover", "dismiss"])


# ==================================================================== the real writer
@unittest.skipUnless(HAVE_LESSON, "bin/skillnote in this checkout has no --lesson yet")
class LiveSkillnoteTest(RepeatCliCase):
    """A TEST THAT WRITES INTO THE CHECKOUT IS A DEFECT, AND THIS ONE DID.

    `bin/skillnote add` appends its dated line to the `.claude/CLAUDE.md` of the current
    working directory. Run with the suite's default cwd, that is this repository, and two
    junk notes dated 1970 landed in it before anyone noticed -- from a test whose every
    assertion passed. The cwd is fixed above; this guard is what makes the fix
    non-optional, because it fails on the write rather than on its consequences."""

    REPO_NOTES = os.path.join(REPO, ".claude", "CLAUDE.md")

    def add_lesson(self, sig, text):
        """`--scope project --project <dir>` as well as the cwd, which is belt AND braces
        on purpose: the cwd is what skillnote reads by default and `--project` is what it
        reads when told, and only one of the two has to be forgotten for this test to
        start writing into the checkout."""
        return self.note_cli("add", "--scope", "project", "--project", self.project,
                             "--lesson", sig, text)

    def ledger_rows(self):
        with open(self.ledger, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def setUp(self):
        RepeatCliCase.setUp(self)
        with open(self.REPO_NOTES, "rb") as fh:
            self._repo_notes = fh.read()

    def tearDown(self):
        try:
            with open(self.REPO_NOTES, "rb") as fh:
                now = fh.read()
            self.assertEqual(now, self._repo_notes,
                             "this test wrote into the checkout's own .claude/CLAUDE.md")
        finally:
            RepeatCliCase.tearDown(self)
    """THE CONTRACT, DRIVEN END TO END. Every test above writes the ledger row by hand,
    which pins whichever side its author was looking at and lets the other drift -- the
    defect this repo recorded on 2026-09-02 after it happened twice in one day. This class
    is the antidote: the REAL bin/skillnote writes the row and the REAL reader reads it.

    It SKIPS, loudly, while `--lesson` does not exist. A skip is a statement that the
    contract is untested; a hand-written fixture pretending to be the writer is not."""

    def test_a_real_skillnote_lesson_is_read_back_as_recorded(self):
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.assertEqual(self.lesson_column(sig), "open")
        self.tick()
        r = self.add_lesson(sig, "gh is not on PATH here; curl the API instead.")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(self.ledger), "skillnote wrote no ledger row")
        rows = self.ledger_rows()
        carried = [x for x in rows
                   if x.get("event") == "note" and x.get("lesson_sig") == sig]
        self.assertTrue(carried, "no note row carries lesson_sig=%s: %r" % (sig, rows))
        self.assertEqual(carried[0].get("action"), "add")
        self.assertEqual(self.lesson_column(sig), "recorded")

    def test_a_real_skillnote_remove_takes_the_lesson_back_out(self):
        """The other half of the contract, and the half a reader gets wrong by default:
        `skillnote remove` appends a removal and deletes nothing, so a reader matching on
        `lesson_sig` alone goes on reporting a lesson that no longer exists. Driven with
        the real writer on both sides -- the id comes out of the row skillnote wrote."""
        self.fail_then_fix("s1")
        sig = self.sig_of("gh pr list --limit 5")
        self.tick()
        self.assertEqual(self.add_lesson(sig, "curl the API instead.").returncode, 0)
        self.assertEqual(self.lesson_column(sig), "recorded")
        note_id = [x for x in self.ledger_rows()
                   if x.get("lesson_sig") == sig and x.get("action") == "add"][0]["id"]
        self.tick()
        r = self.note_cli("remove", note_id)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        removed = [x for x in self.ledger_rows()
                   if x.get("event") == "note" and x.get("action") == "remove"]
        self.assertTrue(removed, "skillnote remove appended no row")
        self.assertEqual(removed[-1]["id"], note_id)
        self.assertEqual(self.lesson_column(sig), "open")

    def test_the_hook_stops_refusing_once_the_real_writer_has_run(self):
        """The whole point of the contract: the refusal lifts because a lesson exists,
        and nothing in this test writes that fact by hand."""
        self.fail_then_fix("s1")
        self.fail_then_fix("s2")
        sig = self.sig_of("gh pr list --limit 5")
        attempt = {"hook_event_name": "PreToolUse", "session_id": "s2",
                   "tool_name": "Bash", "tool_use_id": "toolu_probe_1",
                   "tool_input": {"command": "npm install left-pad"}}
        self.tick()
        denied = self.run_hook(attempt, REPEAT_GATE_REFUSE=None)
        self.assertTrue(denied.stdout.strip(), "the lesson gate refused nothing to start")
        self.tick()
        r = self.add_lesson(sig, "gh is not installed on this box.")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.tick()
        attempt["tool_use_id"] = "toolu_probe_2"
        after = self.run_hook(attempt, REPEAT_GATE_REFUSE=None)
        self.assertEqual(after.stdout.strip(), "",
                         "the refusal survived a real recorded lesson: %s" % after.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
