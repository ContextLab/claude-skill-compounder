#!/usr/bin/env python3
"""The fifth question: was the new skill ever used on the problem that caused it?

The ledger used to answer four questions -- what triggered the build, what was built,
when it has been used since, and whether it worked. `apply` is the fifth, and it is not
the fourth one again:

* a `use` row is ANY invocation, ever, by anyone, for any reason;
* an `apply` row is the ONE that closes the forge loop, carrying an outcome
  (`used` / `declined` / `failed`) and the verbatim evidence behind it.

A skill here is forged AS NEEDED, out of a problem that was in front of somebody, so a
forge that ends at "installed" has produced a tool and left the problem exactly where it
was. `skillreport applied` and the APPLIED headline are what make that visible, and the
number the whole addition exists to produce is "N forges closed, M never applied".

THE RULE THESE TESTS ENFORCE HARDEST IS THE LEDGER'S OWN. Every reader selects its events
BY NAME; a reader that classified by exclusion would have folded `use` rows into the forge
count the day ledger v2 landed. So `test_the_reuse_headline_is_untouched_by_apply_rows`
runs the real report against ONE ledger, records the exact reuse line, appends real
`apply` rows to that same ledger, runs it again, and demands the identical string. That is
the test that fails if a selector is ever widened to a negation.

Also covered, because the two gates ship an escape and a threshold that nothing else
counts: <state>/repeats/index.jsonl and <state>/doc-gate/overrides.jsonl. AN ESCAPE
NOBODY COUNTS IS INDISTINGUISHABLE FROM A GATE NOBODY HAS -- the push went through either
way -- which is why the override total is on the report at all.

NO MOCKS. Every row in every store here is written by the real `bin/skillforge`, the real
`hooks/repeat-gate.sh` and the real `hooks/doc-gate.sh` running as subprocesses against a
real temp state directory, over a real git repository with a real upstream. Clocks are
pinned through the environment variables those scripts read for exactly that purpose
(SKILLFORGE_NOW, REPEAT_GATE_NOW, DOC_GATE_NOW). Every subprocess against a hook passes
`input=`, because a hook reads its payload with `payload="$(cat)"` and an inherited stdin
makes it hang forever.
"""

import datetime
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FORGE = REPO / "bin" / "skillforge"
REPORT = Path(os.environ.get("SKILLREPORT_BIN") or (REPO / "bin" / "skillreport"))
REPEAT_HOOK = REPO / "hooks" / "repeat-gate.sh"
DOC_HOOK = REPO / "hooks" / "doc-gate.sh"

PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"

# 1786000000 is 2026-08-06 UTC. Every timestamp below is an offset from it.
T0 = 1786000000
PROJ = "/Users/me/proj"


def iso(epoch):
    dt = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def use_record(skill, epoch, cwd, tool_id, entrypoint="cli"):
    """An assistant record holding one Skill tool_use, in the verified real shape."""
    return {
        "parentUuid": "00000000-0000-0000-0000-000000000000",
        "isSidechain": False,
        "type": "assistant",
        "uuid": "11111111-1111-1111-1111-111111111111",
        "timestamp": iso(epoch),
        "userType": "external",
        "sessionId": "sess",
        "cwd": cwd,
        "entrypoint": entrypoint,
        "version": "2.1.245",
        "gitBranch": "main",
        "message": {
            "id": "msg_x", "type": "message", "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_id,
                         "name": "Skill", "input": {"skill": skill}}],
        },
    }


class Base(unittest.TestCase):
    """A real temp state directory, the real CLIs and hooks, nothing pretended."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.transcripts = self.root / "projects"
        self.skills = self.root / "skills"
        self.home = self.root / "home"
        for d in (self.state, self.transcripts, self.skills, self.home):
            d.mkdir()
        self.ledger = self.state / "ledger.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------------ environment
    def env(self, **extra):
        # TMPDIR is deliberately absent: skillreport folds $TMPDIR into the temp roots it
        # labels invocations against, and leaving it unset keeps that set fixed so no
        # assertion here depends on where the runner was given scratch space.
        e = {"PATH": PATH, "HOME": str(self.home),
             "SKILL_COMPOUNDER_STATE": str(self.state),
             "SKILL_COMPOUNDER_TRANSCRIPTS": str(self.transcripts)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def sh(self, argv, **env_extra):
        return subprocess.run(argv, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, env=self.env(**env_extra),
                              timeout=180)

    # ------------------------------------------------------------------ the real CLI
    def make_skill(self, name):
        d = self.skills / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            "---\nname: %s\ndescription: Use when testing the apply column.\n---\n\nbody\n"
            % name, encoding="utf-8")
        return d

    def forge(self, name, start=100, done=400):
        """One real forge: a real start row and a real done row, from the real CLI."""
        d = self.make_skill(name)
        r = self.sh([str(FORGE), "start", name, "6", "summary for " + name,
                      "--skill-dir", str(d), "--trigger", "verbatim trigger for " + name,
                      "--trigger-kind", "user-prompt"], SKILLFORGE_NOW=T0 + start)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.sh([str(FORGE), "done", "--name", name, "--skill-dir", str(d),
                      "closed"], SKILLFORGE_NOW=T0 + done)
        self.assertEqual(r.returncode, 0, r.stderr)

    def apply(self, name, at, outcome, evidence, session=None, force=False, forge=None):
        argv = [str(FORGE), "apply", "--name", name, "--outcome", outcome,
                "--evidence", evidence, "--session", session or ("sess-" + name)]
        if forge:
            argv += ["--forge", forge]
        if force:
            argv += ["--force"]
        r = self.sh(argv, SKILLFORGE_NOW=T0 + at)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def transcript(self, records, name="proj/a.jsonl"):
        # COMPACT, with no spaces after the separators. Claude Code writes transcripts
        # that way and skillreport's grep prefilter is keyed on the exact substring
        # '"name":"Skill"'. json.dumps' default `", "` / `": "` produces a record the
        # prefilter never matches, and every count silently comes back zero.
        path = self.transcripts / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, separators=(",", ":")) + "\n")

    def junk(self):
        """A malformed line, a foreign object and a foreign ARRAY, all appended for real.

        The array is the one that matters. `fromjson? // empty` lets it through -- it is
        valid JSON -- and every reader that then reaches for `.event` on it raises
        "Cannot index array with string", jq exits 5, and the whole view collapses to
        "no forges recorded yet" with every real row still on disk.
        """
        with self.ledger.open("a", encoding="utf-8") as fh:
            fh.write("this is not json at all {{{\n")
            fh.write('{"tool":"something-else","note":"a foreign line, no event key"}\n')
            fh.write("[1,2,3]\n")

    # ------------------------------------------------------------------ the report
    def report(self, *args, **env_extra):
        r = self.sh([str(REPORT)] + list(args), **env_extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def reuse_line(self, out):
        m = re.search(r"^REUSE:.*$", out, re.M)
        self.assertIsNotNone(m, "no REUSE line in:\n" + out)
        return m.group(0)

    def applied_line(self, out):
        m = re.search(r"^APPLIED: .*$", out, re.M)
        self.assertIsNotNone(m, "no APPLIED headline in:\n" + out)
        return m.group(0)


# ======================================================================= the column
class AppliedColumnTest(Base):

    def test_the_applied_view_shows_the_outcome_and_how_long_after(self):
        self.forge("alpha-gate", start=100, done=400)
        self.apply("alpha-gate", 8000, "used",
                   "ran it on the failing push and the gate refused with the right reason")
        out = self.report("applied")
        row = [l for l in out.splitlines() if l.startswith("alpha-gate")]
        self.assertEqual(len(row), 1, out)
        self.assertIn("used", row[0])
        # 8000 - 400 = 7600s, which is 2h to the resolution this column prints.
        self.assertIn("2h", row[0])
        self.assertIn("ran it on the failing push", row[0])

    def test_the_skills_view_carries_an_applied_line_per_skill(self):
        self.forge("alpha-gate", start=100, done=400)
        self.apply("alpha-gate", 8000, "used", "put it on the push that started this")
        out = self.report("skills")
        self.assertIn("  applied   used, 2h after the forge closed", out)
        self.assertIn("put it on the push that started this", out)

    def test_a_declined_apply_is_an_outcome_not_an_absence(self):
        """`declined` means somebody read the skill and judged it did not fit. That is a
        real answer to the fifth question and must never read as 'never applied'."""
        self.forge("beta-parser", start=500, done=900)
        self.apply("beta-parser", 99000, "declined",
                   "read the skill and it did not fit the parser problem")
        out = self.report("applied")
        self.assertIn("declined", out)
        self.assertIn("1 forges closed, 0 never applied.", out)
        self.assertNotIn("NEVER", out)

    def test_a_forge_matched_by_its_forge_field_rather_than_its_name(self):
        """`done` records the FORGE's name; the apply marker records the INSTALLED
        skill's name, and the two are not always the same string. An apply row carrying
        `forge` discharges the forge of that name even when `name` differs."""
        self.forge("widget-forge", start=100, done=400)
        self.apply("widget-skill", 5000, "used", "used the installed skill on the problem",
                   force=True, forge="widget-forge")
        out = self.report("applied")
        self.assertIn("0 never applied", out)
        self.assertNotIn("NEVER", out)


# ================================================================ the never-applied count
class NeverAppliedTest(Base):

    def test_the_headline_counts_closed_forges_with_no_apply_row(self):
        self.forge("alpha-gate", start=100, done=400)
        self.forge("beta-parser", start=500, done=900)
        self.forge("gamma-runner", start=1000, done=1400)
        self.apply("alpha-gate", 8000, "used", "used it on the thing that caused it")
        self.assertEqual(self.applied_line(self.report()),
                         "APPLIED: 3 forges closed, 2 never applied.")
        self.assertIn("3 forges closed, 2 never applied.", self.report("applied"))

    def test_a_never_applied_forge_is_named_in_the_applied_view(self):
        self.forge("gamma-runner", start=1000, done=1400)
        out = self.report("applied")
        row = [l for l in out.splitlines() if l.startswith("gamma-runner")]
        self.assertEqual(len(row), 1, out)
        self.assertIn("NEVER", row[0])
        self.assertIn("  applied   NOT APPLIED", self.report("skills"))

    def test_zero_of_zero_is_printed_rather_than_hidden(self):
        """A count that only appears once it looks good is not a measurement. A ledger
        with a start and no done has nothing to apply, and the report says so."""
        self.make_skill("half-done")
        r = self.sh([str(FORGE), "start", "half-done", "6", "s",
                      "--skill-dir", str(self.skills / "half-done"),
                      "--trigger", "t", "--trigger-kind", "user-prompt"],
                     SKILLFORGE_NOW=T0 + 100)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.report()
        self.assertEqual(self.applied_line(out),
                         "APPLIED: 0 forges closed, 0 never applied.")
        self.assertIn("nothing to apply yet", out)

    def test_a_failed_forge_is_not_counted_as_a_closed_one(self):
        """`fail` writes no pending-apply marker: an abandoned forge produced nothing to
        apply, and a debt nobody can pay is not a debt. It must not be in the
        denominator either."""
        self.make_skill("doomed")
        self.sh([str(FORGE), "start", "doomed", "6", "s",
                  "--skill-dir", str(self.skills / "doomed"),
                  "--trigger", "t", "--trigger-kind", "user-prompt"],
                 SKILLFORGE_NOW=T0 + 100)
        r = self.sh([str(FORGE), "fail", "--name", "doomed", "red team never cleared it"],
                     SKILLFORGE_NOW=T0 + 400)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.applied_line(self.report()),
                         "APPLIED: 0 forges closed, 0 never applied.")


# =========================================================== apply rows with no forge
class LooseApplyTest(Base):

    def test_an_apply_row_for_a_skill_this_ledger_never_forged(self):
        """`--force` records an apply for a skill forged on another machine, or one whose
        marker is long gone. It is a real record of a real act, so it is shown -- and it
        is in NEITHER half of the closed/never-applied fraction, because there is no
        forge here for it to discharge."""
        self.forge("alpha-gate", start=100, done=400)
        self.apply("alpha-gate", 8000, "used", "used it on the failing push")
        self.apply("orphan-skill", 95000, "used", "used the skill someone else forged",
                   force=True)
        out = self.report("applied")
        self.assertIn("1 forges closed, 0 never applied.", out)
        self.assertIn("APPLY ROWS WITH NO FORGE IN THIS LEDGER (1)", out)
        self.assertIn("orphan-skill", out)
        self.assertIn("used the skill someone else forged", out)
        j = json.loads(self.report("applied", "--json"))
        self.assertEqual(j["closed"], 1)
        self.assertEqual(j["never"], 0)
        self.assertEqual([r["name"] for r in j["loose"]], ["orphan-skill"])

    def test_a_loose_apply_row_gets_its_own_block_in_the_skills_view(self):
        self.apply("orphan-skill", 95000, "used", "used a skill forged elsewhere",
                   force=True)
        out = self.report("skills")
        self.assertIn("orphan-skill", out)
        self.assertIn("  applied   used", out)
        self.assertIn("used a skill forged elsewhere", out)


# ============================================================ two applies, one skill
class TwoAppliesTest(Base):

    def test_two_apply_rows_for_one_skill_discharge_one_forge_between_them(self):
        """One apply per done, greedily and in ledger order, for the reason the forge
        join gives one outcome per start: a skill applied twice must not make one forge
        read as two."""
        self.forge("delta-linter", start=2000, done=2400)
        self.apply("delta-linter", 3000, "failed", "fired on the lint run and did not help")
        self.apply("delta-linter", 90000, "used",
                   "second pass, this time it caught the real defect",
                   session="sess-delta-2", force=True)
        j = json.loads(self.report("applied", "--json"))
        self.assertEqual(j["closed"], 1)
        self.assertEqual(j["never"], 0)
        # The FIRST apply after the done discharges it; the second is a further record of
        # a further act, kept and shown rather than folded into the same forge.
        self.assertEqual([f["outcome"] for f in j["forges"]], ["failed"])
        self.assertEqual([r["outcome"] for r in j["loose"]], ["used"])
        out = self.report("skills")
        self.assertEqual(out.count("  applied   "), 1 + 1,
                         "both apply rows should appear on their own line:\n" + out)

    def test_two_forges_of_one_name_and_two_applies_pair_off_in_order(self):
        self.forge("twice", start=100, done=400)
        self.apply("twice", 500, "failed", "did not help the first time")
        self.forge("twice", start=1000, done=1400)
        # A DIFFERENT SESSION for the second apply, and not for tidiness: `skillforge
        # apply` is idempotent on name+session, so a second apply from the same session
        # is treated as the second delivery of one intent and writes nothing at all.
        self.apply("twice", 1500, "used", "the rebuilt one worked on the same problem",
                   session="sess-twice-2")
        j = json.loads(self.report("applied", "--json"))
        self.assertEqual(j["closed"], 2)
        self.assertEqual(j["never"], 0)
        self.assertEqual(j["loose"], [])
        self.assertEqual(sorted(f["outcome"] for f in j["forges"]), ["failed", "used"])


# ================================================ nothing that already worked moved
class NoExistingCountMovedTest(Base):
    """The rule: add an event type freely, never widen a selector to a negation."""

    def build_a_ledger_with_a_real_reuse_number(self):
        """Two forges, one of them genuinely reused after it closed. The reuse headline
        is therefore a real fraction and not a degenerate 0-of-0."""
        self.forge("alpha-gate", start=100, done=400)
        self.forge("gamma-runner", start=1000, done=1400)
        self.transcript([use_record("alpha-gate", T0 + 9000, PROJ, "toolu_1")])

    def test_the_reuse_headline_is_untouched_by_apply_rows(self):
        self.build_a_ledger_with_a_real_reuse_number()
        before_out = self.report()
        before = self.reuse_line(before_out)
        self.assertEqual(before,
                         "REUSE: 1 of 2 finished forges (50%) produced a skill that was invoked")

        # The SAME ledger, with real apply rows appended by the real CLI.
        self.apply("alpha-gate", 8000, "used", "used it on the push that caused it")
        self.apply("gamma-runner", 9000, "declined", "read it and it did not fit")
        after_out = self.report()

        self.assertEqual(self.reuse_line(after_out), before,
                         "an apply row moved the reuse headline")
        # And every other pre-existing count on the page, line for line, apart from the
        # APPLIED block this change adds -- and the FUNNEL block, which issue #37 added
        # and which an apply row is SUPPOSED to move: an apply row is a lineage's last
        # hop but one, so a funnel blind to it would be the estimate again in a new
        # shape. The equality below still covers the reuse headline, the forge table,
        # the harness lines and the conversion, which are the counts this class exists
        # to hold still.
        def strip(out):
            lines = out.splitlines()
            keep, skip = [], False
            for l in lines:
                if l.startswith("APPLIED: ") or l.startswith("FUNNEL ("):
                    skip = True
                elif skip and (l == "" or l.startswith("REUSE") or not l.startswith(" ")):
                    skip = False
                if not skip:
                    keep.append(l)
            return "\n".join(keep)
        self.assertEqual(strip(after_out), strip(before_out))

        # The funnel moved by EXACTLY the two apply rows, neither of which carries a
        # lineage id (nothing started those forges from a candidate), so both are
        # reported as unattributed rather than dropped or guessed at.
        def unattributed(out):
            line = [l for l in out.splitlines() if "UNATTRIBUTED:" in l][0]
            return int(line.split("UNATTRIBUTED:")[1].split()[0])
        self.assertEqual(unattributed(after_out), unattributed(before_out) + 2,
                         "the funnel did not count the two apply rows:\n" + after_out)

    def test_apply_rows_are_not_counted_as_forge_starts(self):
        self.forge("alpha-gate", start=100, done=400)
        before = self.report()
        self.assertIn("forges started, all time:   1", before)
        self.apply("alpha-gate", 8000, "used", "used it on the problem")
        self.assertIn("forges started, all time:   1", self.report())

    def test_apply_rows_are_not_counted_as_uses(self):
        self.forge("alpha-gate", start=100, done=400)
        self.apply("alpha-gate", 8000, "used", "used it on the problem")
        out = self.report("skills")
        self.assertIn("  uses      none recorded", out)
        self.assertIn("  skills with a recorded use:     0", out)

    def test_apply_rows_are_not_counted_as_outcomes_in_the_forge_table(self):
        """The forge join names `start`, `done` and `fail`. An `apply` row must be
        invisible to it -- not an orphan outcome, not a second done."""
        self.forge("alpha-gate", start=100, done=400)
        self.apply("alpha-gate", 8000, "used", "used it on the problem")
        out = self.report()
        self.assertNotIn("outcome record(s) have no matching start record", out)
        self.assertEqual(len([l for l in out.splitlines()
                              if l.startswith("alpha-gate")]), 1, out)


# ================================================================ junk in the ledger
class JunkLinesTest(Base):

    def test_malformed_and_foreign_lines_are_skipped_everywhere(self):
        self.forge("alpha-gate", start=100, done=400)
        self.forge("gamma-runner", start=1000, done=1400)
        self.apply("alpha-gate", 8000, "used", "used it on the problem that caused it")
        self.junk()

        out = self.report()
        self.assertIn("alpha-gate", out)
        self.assertNotIn("no forges recorded yet", out)
        self.assertEqual(self.applied_line(out),
                         "APPLIED: 2 forges closed, 1 never applied.")
        self.assertEqual(self.reuse_line(out),
                         "REUSE: 0 of 2 finished forges (0%) produced a skill that was invoked")

        skills = self.report("skills")
        self.assertIn("alpha-gate", skills)
        self.assertNotIn("no ledger yet", skills)

        j = json.loads(self.report("applied", "--json"))
        self.assertEqual(j["closed"], 2)
        self.assertEqual(j["never"], 1)

    def test_a_foreign_json_array_does_not_take_the_table_down(self):
        """Regression, measured while this column was being added: `[1,2,3]` on a line of
        its own is valid JSON, so `fromjson?` keeps it, and `.event` on an array raises
        "Cannot index array with string". jq exits 5, the forge table comes back empty,
        and the report announces "no forges recorded yet" over a ledger full of forges."""
        self.forge("alpha-gate", start=100, done=400)
        with self.ledger.open("a", encoding="utf-8") as fh:
            fh.write("[1,2,3]\n")
        out = self.report()
        self.assertNotIn("no forges recorded yet", out)
        self.assertIn("alpha-gate", out)

    def test_an_empty_ledger_still_answers_in_json(self):
        """`--json` over an empty ledger must still parse. A report a caller's script
        cannot parse is worse than one that says zero."""
        j = json.loads(self.report("applied", "--json"))
        self.assertEqual(j, {"forges": [], "loose": [], "closed": 0, "never": 0,
                             "used": 0, "declined": 0, "failed": 0})

    def test_an_unknown_option_to_applied_is_refused(self):
        r = self.sh([str(REPORT), "applied", "--nonsense"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown option", r.stderr)


# ==================================================================== the two gates
class GateSurfacesTest(Base):
    """<state>/repeats/index.jsonl and <state>/doc-gate/overrides.jsonl, both written
    here by the real hooks."""

    GH_ERR = "Exit code 127\ngh: command not found"

    # ------------------------------------------------------------- the repeat gate
    def repeat_hook(self, payload, now, **env_extra):
        """`REPEAT_GATE_REFUSE=1` because the gate's refuse arm ships OFF (issue #27) and
        the `pre()` deliveries below are here to measure what it decides, not whether it
        is switched on. The learn and recover arms ignore the variable entirely, so the
        stores these tests build are the ones a real machine builds."""
        env = {"REPEAT_GATE_NOW": now, "REPEAT_GATE_REFUSE": "1"}
        env.update(env_extra)
        return subprocess.run(
            ["bash", str(REPEAT_HOOK)], input=json.dumps(payload), capture_output=True,
            text=True, env=self.env(**env), timeout=180)

    # NOT `fail`. `unittest.TestCase.fail(msg)` is what every assertion in this class
    # calls to report itself, and a helper of that name shadowed it: a failing
    # assertion here raised `fail() missing 2 required positional arguments` instead
    # of printing the failure it had found.
    def record_failure(self, command, session, now, error=None):
        p = {"hook_event_name": "PostToolUseFailure", "session_id": session,
             "transcript_path": str(self.root / "t.jsonl"), "cwd": "/repo",
             "prompt_id": "p1", "permission_mode": "acceptEdits", "tool_name": "Bash",
             "tool_use_id": "toolu_f_%s_%d" % (session, now),
             "tool_input": {"command": command, "description": "d"},
             "error": error or self.GH_ERR, "is_interrupt": False, "duration_ms": 12}
        r = self.repeat_hook(p, now)
        self.assertEqual(r.returncode, 0, r.stderr)

    def succeed(self, command, session, now):
        p = {"hook_event_name": "PostToolUse", "session_id": session,
             "transcript_path": str(self.root / "t.jsonl"), "cwd": "/repo",
             "prompt_id": "p1", "permission_mode": "acceptEdits", "tool_name": "Bash",
             "tool_use_id": "toolu_s_%s_%d" % (session, now),
             "tool_input": {"command": command, "description": "d"},
             "tool_response": {"stdout": "ok", "stderr": "", "interrupted": False},
             "duration_ms": 30}
        r = self.repeat_hook(p, now)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_the_empty_case_says_no_store_rather_than_zero(self):
        """AN ABSENT RECORD IS NOT A NEGATIVE RESULT. A missing store means the gate has
        recorded nothing on this machine, which is not the claim that nothing failed."""
        out = self.report()
        self.assertIn("GATES", out)
        self.assertIn("repeat gate:   no store yet", out)
        self.assertIn("doc gate:      no overrides recorded", out)
        self.assertNotIn("0 distinct failure signature(s)", out)

    def test_the_gates_are_surfaced_even_with_no_ledger_at_all(self):
        """The gates are written by hooks, not by a forge. A machine that has never
        forged anything can still have refused a repeat, and is owed the number."""
        self.record_failure("gh pr list --state all", "s1", T0 + 100)
        out = self.report()
        self.assertIn("no forges recorded yet", out)
        self.assertIn("1 distinct failure signature(s) known", out)

    def test_distinct_signatures_and_the_deny_threshold(self):
        self.forge("alpha-gate", start=100, done=400)
        # One signature failing in two DISTINCT sessions: at the threshold.
        self.record_failure("gh pr list --state all", "s1", T0 + 100)
        self.record_failure("gh pr list --state all", "s2", T0 + 300)
        # A second signature in one session only: known, below the threshold.
        self.record_failure("npm run build --silent", "s3", T0 + 500,
                  error="Exit code 1\nmissing tsconfig")
        out = self.report()
        self.assertIn("2 distinct failure signature(s) known", out)
        self.assertIn("1 of them at or past the", out)
        self.assertIn("(>= 2 distinct sessions)", out)

    def test_the_threshold_reported_is_the_one_in_force(self):
        self.forge("alpha-gate", start=100, done=400)
        self.record_failure("gh pr list --state all", "s1", T0 + 100)
        self.record_failure("gh pr list --state all", "s2", T0 + 300)
        out = self.report(REPEAT_MIN_SESSIONS=3)
        self.assertIn("(>= 3 distinct sessions)", out)
        self.assertIn("0 of them at or past the", out)

    def test_a_nonsense_threshold_does_not_abort_the_report(self):
        self.forge("alpha-gate", start=100, done=400)
        self.record_failure("gh pr list --state all", "s1", T0 + 100)
        out = self.report(REPEAT_MIN_SESSIONS="abc")
        self.assertIn("(>= 2 distinct sessions)", out)
        self.assertIn("REUSE:", out)

    def test_recoveries_are_counted_and_named_by_row_type(self):
        self.forge("alpha-gate", start=100, done=400)
        self.record_failure("gh pr list --state all", "s1", T0 + 100)
        # A same-tool shell binding needs REPEAT_RECOVERY_SAME_TOOL_MIN_TOKENS (2)
        # shared content tokens since 2026-09-03; `brew install gh` shares none with
        # the failure (`gh` is two characters, below the token floor) and would no
        # longer bind, which is the rule working rather than the report breaking.
        self.succeed("gh pr list --state all --limit 200", "s1", T0 + 200)
        out = self.report()
        self.assertIn("1 recovery row(s)", out)

    def pre(self, command, session, now, tuid=None):
        """One real PreToolUse delivery, which is the arm that actually refuses."""
        p = {"hook_event_name": "PreToolUse", "session_id": session,
             "transcript_path": str(self.root / "t.jsonl"), "cwd": "/repo",
             "prompt_id": "p1", "permission_mode": "acceptEdits", "tool_name": "Bash",
             "tool_use_id": tuid or ("toolu_p_%s_%d" % (session, now)),
             "tool_input": {"command": command, "description": "d"}}
        r = self.repeat_hook(p, now)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_the_refusal_count_excludes_a_signature_the_gate_calls_transient(self):
        """THE REPORT MUST NOT DESCRIBE A REFUSAL THE GATE WOULD NOT MAKE.

        `hooks/repeat-gate.sh` refuses on `select(.n >= $min and .selfn == 0)`: a
        signature with a SELF-RECOVERY behind it -- an earlier session ran the identical
        call and it worked -- is never refused at all, however many sessions it failed
        in. Counting `.n >= $min` alone states a refusal that would not happen, in a
        report whose whole job is to be true about the other components.

        Both signatures below reach the threshold. Only one of them is refusable, and
        the real gate is asked, in this same test, which.
        """
        self.forge("alpha-gate", start=100, done=400)
        # Structurally broken: two distinct sessions, nothing ever recovered it.
        self.record_failure("gh pr list --state all", "s1", T0 + 100)
        self.record_failure("gh pr list --state all", "s2", T0 + 300)
        # Transient: two distinct sessions, and in the first of them the IDENTICAL call
        # was run again and succeeded. That is an observation that the call is not broken.
        self.record_failure("npm run build --silent", "s3", T0 + 500,
                  error="Exit code 1\nEAGAIN: resource temporarily unavailable")
        self.succeed("npm run build --silent", "s3", T0 + 600)
        self.record_failure("npm run build --silent", "s4", T0 + 700,
                  error="Exit code 1\nEAGAIN: resource temporarily unavailable")

        # What the real gate does, asked directly rather than assumed.
        denied = self.pre("gh pr list --state all", "s9", T0 + 900)
        self.assertNotEqual(denied.strip(), "",
                            "the gate did not refuse the structural signature at all")
        decision = json.loads(denied)["hookSpecificOutput"]["permissionDecision"]
        self.assertEqual(decision, "deny",
                         "the gate did not refuse the structural signature: " + denied)
        allowed = self.pre("npm run build --silent", "s9", T0 + 901)
        self.assertEqual(allowed.strip(), "",
                         "the gate refused a transient signature: " + allowed)

        out = self.report()
        self.assertIn("2 distinct failure signature(s) known", out)
        self.assertIn("1 of them at or past the", out,
                      "the report counts a refusal the gate would not make:\n" + out)
        self.assertIn("(>= 2 distinct sessions)", out)
        self.assertIn("transient", out,
                      "the transient signature is dropped from the count and never "
                      "accounted for:\n" + out)

    def test_the_deny_count_excludes_a_signature_the_gate_exempts_by_its_head(self):
        """ISSUE #27, AND IT IS THE SAME DEFECT AS THE TEST ABOVE IN A SECOND COSTUME.

        Before it refuses anything the gate exempts a Bash command whose HEAD is on
        either of its two lists -- navigation and inspection commands whose failure is
        nobody's bug, and test and build runners whose failure is the point. This report
        applied neither, so it counted refusals the gate does not make. Measured on the
        live store on 2026-09-02: this report said ten would be refused, and the real
        hook, driven against all ten, denied none.

        Both signatures below reach the threshold with nothing recovering them. Only one
        of them is refusable, and the real gate is asked, in this same test, which."""
        self.forge("alpha-gate", start=100, done=400)
        # Refusable: `gh` is on neither list.
        self.record_failure("gh pr list --state all", "s1", T0 + 100)
        self.record_failure("gh pr list --state all", "s2", T0 + 300)
        # Exempt by `allowlisted_head`: a session orienting itself in a repository, which
        # is what every one of the live store's ten threshold signatures turned out to be.
        self.record_failure("git clean -nd", "s3", T0 + 500,
                            error="Exit code 128\nfatal: not a git repository")
        self.record_failure("git clean -nd", "s4", T0 + 700,
                            error="Exit code 128\nfatal: not a git repository")

        # What the real gate does, asked directly rather than assumed.
        self.assertNotEqual(self.pre("gh pr list --state all", "s9", T0 + 900).strip(), "",
                            "the gate did not refuse the non-exempt signature at all")
        self.assertEqual(self.pre("git clean -nd", "s9", T0 + 901).strip(), "",
                         "the gate refused a signature its own head allowlist exempts")

        out = self.report()
        self.assertIn("2 distinct failure signature(s) known", out)
        self.assertIn("1 of them at or past the", out,
                      "the report counts a refusal the gate would not make:\n" + out)
        # The exempt one is ACCOUNTED FOR rather than silently dropped: a count that fell
        # from 2 to 1 with nothing saying why is how a reader concludes the store shrank.
        self.assertIn("1 more reached that count", out, out)
        self.assertIn("exempts the command they run", out, out)

    def test_a_foreign_row_type_in_the_repeat_store_is_skipped_not_counted(self):
        self.forge("alpha-gate", start=100, done=400)
        self.record_failure("gh pr list --state all", "s1", T0 + 100)
        store = self.state / "repeats" / "index.jsonl"
        with store.open("a", encoding="utf-8") as fh:
            fh.write('{"t":"something-else","sig":"nope","ts":1}\n')
            fh.write("not json at all\n")
            fh.write("[1,2,3]\n")
        out = self.report()
        self.assertIn("1 distinct failure signature(s) known", out)

    # ---------------------------------------------------------------- the doc gate
    def git(self, *args, cwd=None):
        env = {"PATH": PATH, "HOME": str(self.home),
               "GIT_AUTHOR_NAME": "Apply Test",
               "GIT_AUTHOR_EMAIL": "apply@example.invalid",
               "GIT_COMMITTER_NAME": "Apply Test",
               "GIT_COMMITTER_EMAIL": "apply@example.invalid",
               "GIT_CONFIG_NOSYSTEM": "1"}
        r = subprocess.run(["git"] + list(args), cwd=cwd or str(self.repo), env=env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=120)
        self.assertEqual(r.returncode, 0,
                         "git %s: %s%s" % (" ".join(args), r.stdout, r.stderr))
        return r.stdout

    def make_repo(self):
        """A real git repository with a real upstream, which is what `@{u}` resolves
        against inside the gate."""
        self.repo = self.root / "repo"
        remote = self.root / "remote.git"
        self.git("init", "--bare", "-q", str(remote), cwd=str(self.root))
        self.git("init", "-q", str(self.repo), cwd=str(self.root))
        (self.repo / "README.md").write_text("# project\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "initial")
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "-u", "origin", "HEAD")

    def code_commit(self, text, message="change code only"):
        (self.repo / "src" / "a.py").write_text(text, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def push(self, command, session, tuid, now):
        p = {"hook_event_name": "PreToolUse", "session_id": session,
             "transcript_path": str(self.root / "t.jsonl"), "cwd": str(self.repo),
             "prompt_id": "p1", "permission_mode": "acceptEdits",
             "effort": {"level": "high"}, "tool_name": "Bash", "tool_use_id": tuid,
             "tool_input": {"command": command, "description": "d"}}
        r = subprocess.run(["bash", str(DOC_HOOK)], input=json.dumps(p),
                           capture_output=True, text=True,
                           env=self.env(DOC_GATE_NOW=now), timeout=180)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_doc_gate_overrides_are_counted_with_their_reason(self):
        """AN ESCAPE NOBODY COUNTS IS INDISTINGUISHABLE FROM A GATE NOBODY HAS. Both
        pushes below went through; the only thing that separates a gate being used from a
        gate being routed around is this number and the reason beside it."""
        self.forge("alpha-gate", start=100, done=400)
        self.make_repo()
        self.code_commit("x = 2\ny = 3\n")
        self.push('DOC_GATE_OVERRIDE="vendored dependency bump" git push',
                  "d1", "tu1", T0 + 1000)
        overrides = self.state / "doc-gate" / "overrides.jsonl"
        self.assertTrue(overrides.exists(), "the real hook wrote no override row")

        out = self.report()
        self.assertIn("doc gate:      1 override(s) taken (1 inline).", out)
        self.assertIn('most recent reason: "vendored dependency bump"', out)
        self.assertIn("An escape nobody counts is indistinguishable from a gate nobody has",
                      out)

    def test_two_overrides_of_different_kinds_are_broken_out(self):
        self.forge("alpha-gate", start=100, done=400)
        self.make_repo()
        self.code_commit("x = 2\n")
        self.push('DOC_GATE_OVERRIDE="vendored bump" git push', "d1", "tu1", T0 + 1000)
        self.code_commit("x = 3\n", message="more code")
        self.git("commit", "-q", "--allow-empty", "-m",
                 "trailer commit\n\nDoc-Gate-Override: already described in DESIGN.md")
        self.push("git push origin HEAD", "d2", "tu2", T0 + 2000)
        out = self.report()
        self.assertIn("2 override(s) taken", out)
        self.assertIn("1 inline", out)
        self.assertIn("1 trailer", out)
        self.assertIn('most recent reason: "already described in DESIGN.md"', out)

    def test_a_malformed_override_row_does_not_take_the_section_down(self):
        self.forge("alpha-gate", start=100, done=400)
        d = self.state / "doc-gate"
        d.mkdir(parents=True, exist_ok=True)
        with (d / "overrides.jsonl").open("a", encoding="utf-8") as fh:
            fh.write('{"ts":1,"event":"override","kind":"inline","reason":"a real one"}\n')
            fh.write("not json\n")
            fh.write("[1,2,3]\n")
            fh.write('{"event":"something-else"}\n')
        out = self.report()
        self.assertIn("1 override(s) taken (1 inline).", out)


# ==================================================== a verdict on an abandoned forge
class FailedForgeVerdictTest(Base):
    """A verdict naming a forge that was ABANDONED is not a verdict on a shipped skill.

    The live ledger carries exactly one: `watch-ci-run` was closed with `skillforge fail`
    and quarantined on 2026-09-05, and a MISFIRED row was written for it eleven seconds
    later at exit 0. `skillforge verdict` refuses that row now, but the ledger is
    append-only and the row stays on the record, so these readers have to say what it is
    rather than print it like a judgement on something that shipped. `apply_join` pairs
    `apply` rows against `done` rows only, so an abandoned forge is invisible to it and
    the block used to read "no closed forge under this name".
    """

    def failed_forge(self, name, start=100, fail=400):
        d = self.make_skill(name)
        r = self.sh([str(FORGE), "start", name, "6", "summary for " + name,
                     "--skill-dir", str(d), "--trigger", "verbatim trigger for " + name,
                     "--trigger-kind", "user-prompt"], SKILLFORGE_NOW=T0 + start)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.sh([str(FORGE), "fail", "--name", name, "not converging"],
                    SKILLFORGE_NOW=T0 + fail)
        self.assertEqual(r.returncode, 0, r.stderr)

    def plant_verdict(self, name, at, verdict="MISFIRED"):
        """Appended by hand, and it has to be: the CLI refuses this row now (exit 5).
        The live ledger holds one written before that gate existed."""
        with self.ledger.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"event": "verdict", "ts": T0 + at, "name": name, "verdict": verdict,
                 "evidence": "round 4's cold reviewer: PASSED at exit 0",
                 "confidence": "measured", "backfilled": False,
                 "judgement": "model judgement over recorded evidence, not a measurement"},
                separators=(",", ":")) + "\n")

    def test_the_block_says_the_forge_failed_instead_of_reading_like_a_judgement(self):
        self.failed_forge("dead-gate")
        self.plant_verdict("dead-gate", 500)
        out = self.report("skills")
        block = re.search(r"^dead-gate$.*?(?=\n\n)", out, re.M | re.S)
        self.assertIsNotNone(block, out)
        block = block.group(0)
        self.assertIn("verdict   1 MISFIRED", block, block)
        self.assertIn("forge failed", block,
                      "a verdict on an abandoned forge printed unqualified:\n" + block)
        self.assertIn("verdict stands on the record only", block, block)
        self.assertNotIn("no closed forge under this name", block,
                         "a forge that failed is not a forge that never happened:\n"
                         + block)
        self.assertIn("NOT APPLICABLE", block, block)

    def test_coverage_counts_it_apart_from_a_verdict_on_a_shipped_skill(self):
        """Counted apart, never dropped: the row is on the ledger and pretending
        otherwise is the same silence this block exists to end."""
        self.forge("alpha-gate", start=100, done=400)
        self.apply("alpha-gate", 800, "used", "used it on the push that caused it")
        r = self.sh([str(FORGE), "verdict", "--name", "alpha-gate", "--verdict", "WORKED",
                     "--evidence", "it refused the push"], SKILLFORGE_NOW=T0 + 900)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.failed_forge("dead-gate", start=1000, fail=1400)
        self.plant_verdict("dead-gate", 1500)
        line = [l for l in self.report("skills").splitlines()
                if "skills with a verdict:" in l]
        self.assertEqual(len(line), 1, line)
        self.assertIn("skills with a verdict:          1", line[0], line[0])
        self.assertIn("+1 whose forge was abandoned", line[0], line[0])

    def test_a_re_forge_that_shipped_is_not_marked(self):
        """The NEWEST close row decides. A name that failed and was then forged again to
        a `done` and applied is a shipped skill, and its verdict is a plain verdict."""
        self.failed_forge("twice", start=100, fail=200)
        self.forge("twice", start=300, done=400)
        self.apply("twice", 500, "used", "used it the second time")
        r = self.sh([str(FORGE), "verdict", "--name", "twice", "--verdict", "WORKED",
                     "--evidence", "it held"], SKILLFORGE_NOW=T0 + 600)
        self.assertEqual(r.returncode, 0, r.stderr)
        block = re.search(r"^twice$.*?(?=\n\n)", self.report("skills"), re.M | re.S)
        self.assertIsNotNone(block)
        self.assertNotIn("forge failed", block.group(0), block.group(0))


# ================================================================== the whole page
class WholePageTest(Base):
    """One mixed ledger, every event type in it, read by every view."""

    def test_every_view_survives_a_ledger_holding_every_event_type(self):
        self.forge("alpha-gate", start=100, done=400)
        self.forge("beta-parser", start=500, done=900)
        self.forge("gamma-runner", start=1000, done=1400)
        self.apply("alpha-gate", 8000, "used", "used it on the push that caused it")
        self.apply("beta-parser", 99000, "declined", "read it and it did not fit")
        self.apply("orphan-skill", 95000, "used", "forged elsewhere", force=True)
        for argv in ([str(FORGE), "use", "--name", "alpha-gate", "--ok",
                      "--session", "s1", "--cwd", PROJ, "--entrypoint", "cli"],
                     [str(FORGE), "verdict", "--name", "alpha-gate", "--verdict", "WORKED",
                      "--evidence", "it refused the push"],
                     [str(FORGE), "origin", "--name", "hand-written",
                      "--origin", "adopted"]):
            r = self.sh(argv, SKILLFORGE_NOW=T0 + 9000)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.junk()
        self.transcript([use_record("alpha-gate", T0 + 9000, PROJ, "toolu_1")])

        table = self.report()
        self.assertEqual(self.reuse_line(table),
                         "REUSE: 1 of 3 finished forges (33%) produced a skill that was invoked")
        self.assertEqual(self.applied_line(table),
                         "APPLIED: 3 forges closed, 1 never applied.")

        skills = self.report("skills")
        for name in ("alpha-gate", "beta-parser", "gamma-runner", "hand-written",
                     "orphan-skill"):
            self.assertIn(name, skills)
        self.assertIn("forges closed, never applied:   1 of 3", skills)

        j = json.loads(self.report("applied", "--json"))
        self.assertEqual((j["closed"], j["never"], j["used"], j["declined"]),
                         (3, 1, 1, 1))


# ============================================ four defects a cold reviewer reproduced
#
# Each of the four below was reported with the wrong output pasted underneath it, each
# was reproduced by hand before anything was changed, and each test here was watched
# failing against `git show HEAD:bin/skillreport` (via SKILLREPORT_BIN) before the fix
# was written. They are grouped by the shape of the mistake rather than by the view they
# touch, because three of the four are the same mistake: a fact stated in two places.
class HandMaintainedCountTest(Base):
    """DEFECT 1. The PRIVACY header counted its own list, by hand, and the count went stale.

    `skillreport --help` prints the whole comment block, so the sentence and the list it
    introduces are shown to the user one above the other. The sentence said "three files"
    while the list held five: the repeat store and the doc-gate override store were
    appended and the sentence was left alone. Understating what a privacy-relevant tool
    opens is the one direction that claim must not be wrong in.

    This test does not check for the word "five". It DERIVES the count from the block --
    the entries are the lines beginning with a `${...}` path -- and compares it to the
    number the sentence states, so appending a sixth entry without touching the sentence
    fails here rather than shipping.
    """

    def privacy_block(self):
        out = self.report("--help")
        start = re.search(r"^PRIVACY\.", out, re.M)
        self.assertIsNotNone(start, "no PRIVACY paragraph in --help:\n" + out)
        end = re.search(r"^`skillreport skills` reads", out[start.start():], re.M)
        self.assertIsNotNone(end, "PRIVACY block has no terminator in --help:\n" + out)
        return out[start.start():start.start() + end.start()]

    def test_the_privacy_count_is_the_number_of_entries_beneath_it(self):
        block = self.privacy_block()
        entries = re.findall(r"^  \$\{", block, re.M)
        self.assertGreaterEqual(len(entries), 5,
                                "the PRIVACY list lost entries:\n" + block)
        stated = re.search(r"reads (\d+) files", block)
        self.assertIsNotNone(
            stated,
            "the PRIVACY sentence states no machine-readable count, so nothing can check "
            "it against the %d entries below it:\n%s" % (len(entries), block))
        self.assertEqual(int(stated.group(1)), len(entries),
                         "the PRIVACY sentence says %s files and lists %d:\n%s"
                         % (stated.group(1), len(entries), block))

    def test_the_two_stores_say_what_they_hold_and_what_is_printed(self):
        """The count was not the whole of it: what those two files HOLD was unsaid.

        The repeat store carries the failing command and the error text; the override
        store carries a reason somebody typed, and `skillreport` quotes that reason back
        on every run. A privacy note that lists a path without saying either is not a
        privacy note.
        """
        block = self.privacy_block()
        repeats = block[block.index("repeats/index.jsonl"):block.index("doc-gate/overrides.jsonl")]
        self.assertRegex(repeats.lower(), r"command",
                         "the repeat store entry never says it holds command text:\n" + repeats)
        self.assertRegex(repeats.lower(), r"error text",
                         "the repeat store entry never says it holds error text:\n" + repeats)
        overrides = block[block.index("doc-gate/overrides.jsonl"):]
        self.assertRegex(overrides.lower(), r"reason",
                         "the override entry never says it holds a written reason:\n" + overrides)
        self.assertRegex(overrides.lower(), r"print|quoted back",
                         "the override entry never says the reason is printed back, which "
                         "it is, clipped to 60 characters:\n" + overrides)


class DurationAgreementTest(Base):
    """DEFECT 2. `applied` and `skills` each carried their own copy of `dur`, and drifted.

    Only the `applied` copy guarded a NEGATIVE interval. An apply row stamped BEFORE the
    `done` row it discharges -- a stepped clock, a ledger merged from two machines, a
    marker that had aged out so the join computes the interval rather than reading it --
    made the two views disagree off the same bytes: "-" in one, a fabricated "-200s" in
    the other.

    Every row here is written by the real `bin/skillforge`. The aged-out marker is a real
    deleted file, which is the documented case in which the join computes `elapsed`
    itself instead of reading the field.
    """

    def stated_in_applied(self, out, skill):
        rows = [l for l in out.splitlines() if l.startswith(skill + " ")]
        self.assertEqual(len(rows), 1, "expected one %s row in:\n%s" % (skill, out))
        # SKILL pad(28), CLOSED pad(12), APPLIED pad(10), AFTER pad(7), then evidence.
        cell = rows[0].split()[3]
        return None if cell == "-" else cell

    def stated_in_skills(self, out, skill):
        block = re.search(r"^%s\n(?:  .*\n)+" % re.escape(skill), out, re.M)
        self.assertIsNotNone(block, "no %s block in:\n%s" % (skill, out))
        line = re.search(r"^  applied   .*$", block.group(0), re.M)
        self.assertIsNotNone(line, "no applied line in:\n" + block.group(0))
        m = re.search(r", (\S+) after the forge closed", line.group(0))
        return None if m is None else m.group(1)

    def test_the_two_views_agree_on_an_apply_stamped_before_its_forge_closed(self):
        self.forge("skew-gate", start=100, done=400)
        marker = self.state / "apply-pending" / "skew-gate.json"
        self.assertTrue(marker.exists(), "the real forge wrote no pending marker")
        marker.unlink()          # an aged-out marker: the join must compute the interval
        self.apply("skew-gate", 200, "used", "ran it on the failing push", force=True)

        applied = self.report("applied")
        skills = self.report("skills")
        self.assertEqual(self.stated_in_applied(applied, "skew-gate"),
                         self.stated_in_skills(skills, "skew-gate"),
                         "the two views state different intervals for one apply row:\n"
                         "--- applied ---\n%s\n--- skills ---\n%s" % (applied, skills))
        self.assertIsNone(self.stated_in_skills(skills, "skew-gate"),
                          "the skills view invented an interval for a negative one:\n" + skills)
        self.assertNotIn("-200s", skills)
        self.assertNotIn("-200s", applied)

    def test_the_two_views_agree_on_an_ordinary_interval_too(self):
        """The agreement above is worthless if both views simply print nothing.

        Same ledger shape, a marker left in place and an apply five minutes after the
        close, so both views must state the SAME non-empty interval.
        """
        self.forge("steady-gate", start=100, done=400)
        self.apply("steady-gate", 700, "used", "ran it and it refused the push")
        applied = self.report("applied")
        skills = self.report("skills")
        self.assertEqual(self.stated_in_applied(applied, "steady-gate"), "5m", applied)
        self.assertEqual(self.stated_in_skills(skills, "steady-gate"), "5m", skills)


class OneApplyOneBlockTest(Base):
    """DEFECT 3. One apply row was rendered under two skill blocks.

    The join matches an apply row to a `done` row by `apply.name == done.name` OR
    `apply.forge == done.name`, which exists so a skill INSTALLED under one name can
    discharge a forge run under another. The skills view then tested the joined row
    against both names, so in exactly the case the dual match was built for the same row,
    with the same evidence, printed twice.

    The block kept is the installed name -- what `use` rows carry and what COVERAGE
    counts. The forge-name block still says where its debt went; it just does not repeat
    the row.
    """

    def test_an_apply_under_a_different_installed_name_is_printed_once(self):
        self.forge("beta", start=100, done=400)
        r = self.sh([str(FORGE), "use", "--name", "beta", "--ok", "--session", "s1",
                     "--cwd", PROJ, "--entrypoint", "cli"], SKILLFORGE_NOW=T0 + 500)
        self.assertEqual(r.returncode, 0, r.stderr)
        evidence = "put it on the very push that caused the forge"
        self.apply("beta-installed", 800, "used", evidence, force=True, forge="beta")

        out = self.report("skills")
        self.assertEqual(out.count(evidence), 1,
                         "the one apply row is rendered %d times:\n%s"
                         % (out.count(evidence), out))
        installed = re.search(r"^beta-installed\n(?:  .*\n)+", out, re.M)
        self.assertIsNotNone(installed, out)
        self.assertIn(evidence, installed.group(0),
                      "the row is not under the installed name a reader looks up:\n" + out)
        forged = re.search(r"^beta\n(?:  .*\n)+", out, re.M)
        self.assertIsNotNone(forged, out)
        self.assertNotIn("nothing to discharge", forged.group(0),
                         "the forge block claims there was nothing to discharge, and there "
                         "was -- it was discharged under the installed name:\n" + out)
        self.assertIn("beta-installed", forged.group(0),
                      "the forge block does not say where its debt went:\n" + out)
        # And the join itself still counts it exactly once.
        j = json.loads(self.report("applied", "--json"))
        self.assertEqual((j["closed"], j["never"], j["used"]), (1, 0, 1))


class BothArmsTest(Base):
    """A standing debt must not disappear because an EARLIER forge was discharged.

    The skills view chained its apply lines `if ($ap|length) > 0 ... elif ($unapplied
    |length) > 0`, so the NOT APPLIED arm was unreachable for any name that had ever
    had one apply row. Two forges of one name, one applied and one not, reported only
    the applied one -- and the debt vanished precisely because the older one was paid.
    """

    def test_an_applied_forge_and_an_unapplied_one_are_both_reported(self):
        self.forge("dual-gate", start=100, done=400)
        self.apply("dual-gate", 700, "used", "put it on the push that caused the forge")
        # A SECOND forge of the same name, closed and never applied. The greedy join
        # gives the one apply row to the first `done`, so this one is a live debt.
        self.forge("dual-gate", start=1000, done=1400)

        j = json.loads(self.report("applied", "--json"))
        self.assertEqual((j["closed"], j["never"]), (2, 1), j)

        out = self.report("skills")
        block = re.search(r"^dual-gate\n(?:  .*\n)+", out, re.M)
        self.assertIsNotNone(block, out)
        self.assertIn("applied   used", block.group(0))
        self.assertIn("NOT APPLIED", block.group(0),
                      "the unapplied forge is invisible because an earlier one was "
                      "discharged:\n" + out)


class ViewsAgreeOnTheNameTest(Base):
    """`skillreport skills` files an apply row under the INSTALLED name; the `applied`
    view rendered the FORGE name for the same row. One row, two views, two labels."""

    def test_the_two_views_file_one_apply_row_under_the_same_name(self):
        evidence = "used the installed skill on the problem that caused the forge"
        self.forge("widget-forge", start=100, done=400)
        self.apply("widget-skill", 5000, "used", evidence, force=True,
                   forge="widget-forge")

        skills = self.report("skills")
        installed = re.search(r"^widget-skill\n(?:  .*\n)+", skills, re.M)
        self.assertIsNotNone(installed, skills)
        self.assertIn(evidence, installed.group(0))

        applied = self.report("applied")
        rows = [l for l in applied.splitlines() if evidence[:40] in l]
        self.assertEqual(len(rows), 1, applied)
        self.assertTrue(rows[0].startswith("widget-skill"),
                        "the applied view labels the row %r while the skills view files "
                        "it under widget-skill:\n%s" % (rows[0].split()[0], applied))
        # The forge name is not lost, it is just not the label.
        self.assertIn("widget-forge", applied)


class PadEllipsisTest(Base):
    """`pad` truncated at the column width with no marker -- unlike `clip` beside it --
    so a cut-off name was indistinguishable from a name that really ends there, and two
    skills sharing a 28-character prefix rendered as the same label with nothing saying
    so."""

    A = "prefix-that-runs-past-the-column-alpha"
    B = "prefix-that-runs-past-the-column-beta"

    def test_a_name_past_the_column_width_is_marked_as_truncated(self):
        shared = 0
        for x, y in zip(self.A, self.B):
            if x != y:
                break
            shared += 1
        self.assertGreaterEqual(shared, 28,
                                "this test needs two names sharing the column width")
        self.forge(self.A, start=100, done=400)
        self.forge(self.B, start=500, done=900)
        out = self.report("applied")
        labels = [l[:28] for l in out.splitlines() if l.startswith("prefix-that-runs")]
        self.assertEqual(len(labels), 2, out)
        self.assertIn("...", labels[0],
                      "a truncated name carries no marker, so it is indistinguishable "
                      "from a name that really is 28 characters:\n" + out)
        self.assertEqual(len(labels[0]), 28, labels[0])


class UnconditionalHeadlineTest(Base):
    """DEFECT 4. "printed even when it is zero of zero" was written, and was not true.

    Both early exits of the table view -- an empty or absent ledger, and a ledger with no
    `start` rows -- called `print_gates` and returned without the APPLIED headline. The
    second is not a corner case: a ledger holding an `origin` row and a `--force` apply
    row, which is the whole supported shape for a skill forged on another machine, has no
    `start` row in it. The default view printed "no forges recorded yet" and said nothing
    at all about the apply rows sitting in the file.
    """

    def test_the_headline_prints_with_no_ledger_at_all(self):
        out = self.report()
        self.assertIn("no forges recorded yet", out)
        self.assertEqual(self.applied_line(out),
                         "APPLIED: 0 forges closed, 0 never applied.")

    def test_the_headline_prints_when_the_ledger_holds_no_start_row(self):
        # The real CLI, the real supported shape: an apply row for a skill this machine
        # never forged. No `start` row is written by any of it.
        self.apply("elsewhere-gate", 900, "used",
                   "used it on the problem on the other machine", force=True)
        self.assertNotIn('"event":"start"', self.ledger.read_text(encoding="utf-8"))
        out = self.report()
        self.assertIn("has no 'start' records", out)
        self.assertEqual(self.applied_line(out),
                         "APPLIED: 0 forges closed, 0 never applied.")
        self.assertIn("1 apply row(s) name no forge in this ledger", out,
                      "the headline reports 0 over a ledger holding a real apply row and "
                      "never mentions it:\n" + out)

    def test_the_headline_still_prints_on_the_ordinary_path(self):
        """The third exit, so the three cannot be fixed apart.

        A forge that closed and was applied: the same function, the same ledger, the
        numbers the other two paths could not reach.
        """
        self.forge("normal-gate", start=100, done=400)
        self.apply("normal-gate", 700, "used", "ran it on the push that caused it")
        out = self.report()
        self.assertEqual(self.applied_line(out),
                         "APPLIED: 1 forges closed, 0 never applied.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
