#!/usr/bin/env python3
"""Ledger v2: what triggered the build, what was built, used since, did it work.

The ledger used to answer one of those four questions and a half. These tests cover the
machinery that keeps the other two and a half current FROM HERE ON -- the trigger
recorded at `skillforge start`, the `origin` row every skill gets, the `use` row the
Skill hook writes on every invocation, the `verdict` row a judge writes, and the
`backfill` door reconstructed history comes through.

Two rules run through all of it:

* NO MOCKS. Every test runs the real scripts through subprocess against a real state
  directory, with HOME and SKILL_COMPOUNDER_STATE pinned into a temp dir and a minimal
  PATH, and reads the results back off disk. Hook payloads are the shapes measured off
  real Claude Code deliveries (2.1.245), not invented ones.
* AN ABSENT RECORD IS NOT A NEGATIVE RESULT. Several tests below exist only to check
  that this package says "unrecorded" where it means unrecorded, rather than printing a
  zero that reads like a measurement.

Every subprocess call against a hook passes `input=`: a hook reads its payload with
`payload="$(cat)"` and an inherited stdin makes it hang forever.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FORGE = REPO / "bin" / "skillforge"
REPORT = REPO / "bin" / "skillreport"
USE_HOOK = REPO / "hooks" / "skill-use.sh"

PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
T0 = 1786000000            # 2026-08-06 UTC


def iso(epoch):
    import datetime
    dt = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


class LedgerV2Case(unittest.TestCase):
    """A real temp state directory, the real CLIs, nothing pretended."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.transcripts = self.root / "projects"
        self.state.mkdir()
        self.transcripts.mkdir()
        self.ledger = self.state / "ledger.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, now=None, **extra):
        e = {"PATH": PATH, "HOME": str(self.root),
             "SKILL_COMPOUNDER_STATE": str(self.state),
             "SKILL_COMPOUNDER_TRANSCRIPTS": str(self.transcripts)}
        if now is not None:
            e["SKILLFORGE_NOW"] = str(now)
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def forge(self, *args, now=None, **extra):
        return subprocess.run([str(FORGE), *args], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, cwd=str(self.root),
                              env=self.env(now, **extra))

    def report(self, *args, script=None):
        return subprocess.run([str(script or REPORT), *args], capture_output=True,
                              text=True, stdin=subprocess.DEVNULL, cwd=str(self.root),
                              env=self.env())

    def hook(self, mode, payload, script=None, **extra):
        """A hook must never break a turn, so every call asserts exit 0."""
        proc = subprocess.run([str(script or USE_HOOK), mode], input=json.dumps(payload),
                              capture_output=True, text=True, cwd=str(self.root),
                              env=self.env(**extra))
        self.assertEqual(proc.returncode, 0,
                         "a hook must exit 0 on every path: " + proc.stderr)
        return proc

    def rows(self, event=None):
        if not self.ledger.exists():
            return []
        out = [json.loads(l) for l in self.ledger.read_text(encoding="utf-8").splitlines()
               if l.strip()]
        return [r for r in out if event is None or r.get("event") == event]

    def write_ledger(self, *records):
        self.ledger.write_text(
            "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records),
            encoding="utf-8")

    def transcript(self, project, session, invocations, entrypoint="cli"):
        """A real transcript file in the verified shape.

        invocations: (skill, epoch, cwd, tool_id, failed).
        """
        d = self.transcripts / project
        d.mkdir(parents=True, exist_ok=True)
        lines = []
        for skill, epoch, cwd, tool_id, failed in invocations:
            lines.append(json.dumps({
                "type": "assistant", "timestamp": iso(epoch), "sessionId": session,
                "cwd": cwd, "entrypoint": entrypoint, "version": "2.1.245",
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": tool_id, "name": "Skill",
                     "input": {"skill": skill}}]},
            }, separators=(",", ":")))
            if failed:
                lines.append(json.dumps({
                    "type": "user", "timestamp": iso(epoch + 1), "sessionId": session,
                    "cwd": cwd, "entrypoint": entrypoint,
                    "message": {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": tool_id,
                         "content": "<tool_use_error>Unknown skill: %s</tool_use_error>" % skill,
                         "is_error": True}]},
                }, separators=(",", ":")))
        (d / ("%s.jsonl" % session)).write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------- the trigger

class TriggerTest(LedgerV2Case):
    """`--trigger` is the one of the four questions that cannot be recovered later."""

    def test_the_trigger_and_its_kind_land_on_the_start_row(self):
        r = self.forge("start", "widget", "8", "summary",
                       "--trigger", "the user said: stop the flaky test",
                       "--trigger-kind", "user-prompt", now=T0)
        self.assertEqual(r.returncode, 0, r.stderr)
        start = self.rows("start")[0]
        self.assertEqual(start["trigger_verbatim"], "the user said: stop the flaky test")
        self.assertEqual(start["trigger_kind"], "user-prompt")

    def test_the_trigger_survives_on_the_forge_record_for_done_to_read(self):
        """`done` runs later, possibly in another directory. The record is the only
        thing that still remembers what was said."""
        self.forge("start", "widget", "8", "summary", "--trigger", "a checkpoint fired",
                   "--trigger-kind", "hook-checkpoint", now=T0)
        shown = json.loads(self.forge("show", "--name", "widget").stdout)
        self.assertEqual(shown["trigger"], "a checkpoint fired")
        self.assertEqual(shown["trigger_kind"], "hook-checkpoint")

    def test_a_missing_trigger_warns_loudly_but_still_forges(self):
        """REFUSING WOULD NOT PRODUCE A TRIGGER, IT WOULD PRODUCE NO ROW.

        Every caller written before the flag existed -- the README example, the demo
        script, the line setup.py prints on a fresh install -- would exit 2, and the
        cheapest way past a CLI that refuses is to stop calling it. A row with one
        missing field beats no row, no animation and no outcome.
        """
        r = self.forge("start", "widget", "8", "summary", now=T0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARNING", r.stderr)
        self.assertIn("--trigger", r.stderr)
        start = self.rows("start")[0]
        self.assertEqual(start.get("trigger_kind"), "unrecorded",
                         "the gap must be recorded AS a gap, not left silently absent")
        self.assertNotIn("trigger_verbatim", start)

    def test_require_trigger_makes_it_a_refusal_for_those_who_want_one(self):
        r = self.forge("start", "widget", "8", "summary", now=T0,
                       SKILLFORGE_REQUIRE_TRIGGER=1)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--trigger", r.stderr)
        self.assertEqual(self.rows("start"), [], "a refused start must write no row")

    def test_a_quote_with_no_kind_is_refused(self):
        """The quote says what was asked; the kind says who asked. 'Fix the flaky test'
        reads identically whether a person typed it or a hook produced it."""
        r = self.forge("start", "widget", "8", "s", "--trigger", "something", now=T0)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--trigger-kind", r.stderr)

    def test_an_invented_trigger_kind_is_refused(self):
        r = self.forge("start", "widget", "8", "s", "--trigger", "x",
                       "--trigger-kind", "vibes", now=T0)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("user-prompt", r.stderr)

    def test_the_word_trigger_in_a_fail_reason_is_left_alone(self):
        """--trigger is an option only where it means something, the same rule --all and
        --skill-dir follow."""
        self.forge("start", "widget", "4", "s", "--trigger", "x",
                   "--trigger-kind", "agent-decision", now=T0)
        r = self.forge("fail", "the --trigger was wrong", now=T0 + 10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--trigger was wrong", self.rows("fail")[0]["phase"])


# ---------------------------------------------------------------------- the origin

class OriginTest(LedgerV2Case):

    def skill_at(self, base, name):
        d = Path(base) / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            "---\nname: %s\ndescription: Use when testing.\n---\nbody\n" % name,
            encoding="utf-8")
        return d

    def test_done_writes_an_origin_row_carrying_the_trigger(self):
        repo = self.root / "repo"
        self.skill_at(repo, "widget")
        subprocess.run([str(FORGE), "start", "widget", "8", "s",
                        "--trigger", "the user asked for it", "--trigger-kind",
                        "user-prompt"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, cwd=str(repo), env=self.env(T0))
        r = subprocess.run([str(FORGE), "done", "clean pass"], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, cwd=str(repo),
                           env=self.env(T0 + 600))
        self.assertEqual(r.returncode, 0, r.stderr)
        origins = self.rows("origin")
        self.assertEqual(len(origins), 1, origins)
        o = origins[0]
        self.assertEqual(o["name"], "widget")
        self.assertEqual(o["origin"], "forged")
        self.assertEqual(o["trigger_verbatim"], "the user asked for it")
        self.assertEqual(o["trigger_kind"], "user-prompt")
        self.assertEqual(o["created_at"], T0, "created_at is when the forge began")
        # realpath on both sides: on macOS the temp root resolves through /private,
        # and the shell recorded the resolved form.
        self.assertEqual(os.path.realpath(o["skill_dir"]),
                         os.path.realpath(str(repo / "skills" / "widget")))
        self.assertIs(o["backfilled"], False)
        self.assertEqual(o["confidence"], "measured")

    def test_a_forge_that_produced_no_skill_gets_no_origin_row(self):
        """A fix, a retirement or a red-team round is a forge with no skill to describe.
        Writing an origin row for it would invent a skill that does not exist."""
        self.forge("start", "some-repair", "4", "s", "--trigger", "x",
                   "--trigger-kind", "agent-decision", now=T0)
        self.forge("done", "fixed it", now=T0 + 60)
        self.assertEqual(self.rows("origin"), [])

    def test_one_origin_row_per_skill_ever(self):
        r = self.forge("origin", "--name", "widget", "--origin", "adopted", now=T0)
        self.assertEqual(r.returncode, 0, r.stderr)
        r2 = self.forge("origin", "--name", "widget", "--origin", "forged", now=T0 + 5)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("already has an origin", r2.stdout)
        self.assertEqual([o["origin"] for o in self.rows("origin")], ["adopted"],
                         "the first answer stands; a second origin row would make "
                         "'how did this skill get here' unanswerable")

    def test_an_invented_origin_is_refused(self):
        r = self.forge("origin", "--name", "widget", "--origin", "magic", now=T0)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.rows("origin"), [])


# ------------------------------------------------------------------- the use rows

# The measured PostToolUse payload for a Skill call, 2.1.245. Keys and shapes as
# delivered; only the values are ours.
def use_payload(skill="no-silent-stub", session="sess-1", tool_id="toolu_01AAA",
                cwd="/Users/me/proj", transcript=None, tool_name="Skill"):
    payload = {
        "session_id": session,
        "cwd": cwd,
        "prompt_id": "prompt-1",
        "permission_mode": "default",
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": {"skill": skill},
        "tool_response": {"success": True, "commandName": skill},
        "tool_use_id": tool_id,
        "duration_ms": 12,
    }
    if transcript is not None:
        payload["transcript_path"] = str(transcript)
    return payload


class UseHookTest(LedgerV2Case):

    def a_transcript(self, entrypoint="cli", first_record_null=True):
        """Real transcript head. The first records of a session can carry a null
        entrypoint, which is why the hook takes the first NON-NULL one."""
        p = self.root / "t.jsonl"
        lines = []
        if first_record_null:
            lines.append(json.dumps({"type": "queue-operation", "entrypoint": None}))
        lines.append(json.dumps({"type": "attachment", "entrypoint": entrypoint,
                                 "cwd": "/Users/me/proj"}))
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_a_successful_invocation_becomes_one_use_row(self):
        self.hook("ok", use_payload(transcript=self.a_transcript("cli")))
        uses = self.rows("use")
        self.assertEqual(len(uses), 1, uses)
        u = uses[0]
        self.assertEqual(u["name"], "no-silent-stub")
        self.assertIs(u["ok"], True)
        self.assertEqual(u["session"], "sess-1")
        self.assertEqual(u["cwd"], "/Users/me/proj")
        self.assertEqual(u["recorded"], "live")
        self.assertIs(u["backfilled"], False)
        self.assertEqual(u["tool_use_id"], "toolu_01AAA")

    def test_the_same_event_delivered_twice_is_recorded_once(self):
        """With the installer's wiring and the plugin both active every hook event is
        delivered twice (measured, 2.1.241)."""
        payload = use_payload(transcript=self.a_transcript())
        self.hook("ok", payload)
        self.hook("ok", payload)
        self.assertEqual(len(self.rows("use")), 1)

    def test_the_ledger_refuses_a_duplicate_even_after_the_claim_ages_out(self):
        """The mkdir claim is per session and ages out after an hour; the ledger's own
        memory of the tool_use_id does not."""
        payload = use_payload(transcript=self.a_transcript())
        self.hook("ok", payload)
        for p in (self.state / "reminders").rglob("use-*"):
            p.rmdir()
        self.hook("ok", payload)
        self.assertEqual(len(self.rows("use")), 1)

    def test_a_script_driven_session_is_marked_harness_at_write_time(self):
        """`.entrypoint == "sdk-cli"` means a program chose the skill, not a person.
        This package's own probes are 93 of 98 invocations on the machine this was
        written on, and they must never reach the genuine column."""
        self.hook("ok", use_payload(transcript=self.a_transcript("sdk-cli")))
        self.assertIs(self.rows("use")[0]["harness"], True)
        self.assertEqual(self.rows("use")[0]["entrypoint"], "sdk-cli")

    def test_a_person_at_a_terminal_is_not_harness(self):
        self.hook("ok", use_payload(transcript=self.a_transcript("cli")))
        self.assertIs(self.rows("use")[0]["harness"], False)

    def test_an_unreadable_transcript_omits_harness_rather_than_guessing(self):
        """A guessed classification is worse than an absent one: defaulting to
        'counted' is exactly the move that inflated the headline the first time. The
        row still carries the session id, which is what a reader needs to classify it
        later."""
        self.hook("ok", use_payload(transcript=self.root / "does-not-exist.jsonl"))
        u = self.rows("use")[0]
        self.assertNotIn("harness", u)
        self.assertNotIn("entrypoint", u)
        self.assertEqual(u["session"], "sess-1")

    def test_the_failure_arm_records_ok_false(self):
        """PostToolUse fires only on success; a failure arrives as PostToolUseFailure.
        A success-only wiring would record every failure as a use."""
        payload = use_payload(transcript=self.a_transcript())
        payload["hook_event_name"] = "PostToolUseFailure"
        payload["tool_response"] = None
        self.hook("fail", payload)
        self.assertIs(self.rows("use")[0]["ok"], False)

    def test_a_payload_for_another_tool_writes_nothing(self):
        """The matcher already selects Skill, but this script can be wired with no
        matcher at all, and a use row naming Bash would be a false record."""
        self.hook("ok", use_payload(tool_name="Bash"))
        self.assertEqual(self.rows("use"), [])

    def test_garbage_in_never_breaks_the_turn(self):
        for payload in ({}, {"tool_name": "Skill"},
                        {"tool_name": "Skill", "tool_input": {}},
                        {"tool_name": "Skill", "tool_input": {"skill": ""}}):
            proc = subprocess.run([str(USE_HOOK), "ok"], input=json.dumps(payload),
                                  capture_output=True, text=True, env=self.env())
            self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.rows("use"), [])

    def test_recording_can_be_switched_off(self):
        self.hook("ok", use_payload(transcript=self.a_transcript()),
                  SKILL_COMPOUNDER_USE_LOG=0)
        self.assertEqual(self.rows("use"), [])

    def test_the_hook_prints_nothing(self):
        proc = self.hook("ok", use_payload(transcript=self.a_transcript()))
        self.assertEqual(proc.stdout, "", "a hook must not write to the terminal")
        self.assertEqual(proc.stderr, "", proc.stderr)


# ------------------------------------------------------------------- the verdicts

class VerdictTest(LedgerV2Case):

    def test_a_verdict_carries_its_quote_and_says_it_is_a_judgement(self):
        r = self.forge("verdict", "--name", "widget", "--verdict", "WORKED",
                       "--evidence", "it caught the stub: 'return []' was flagged",
                       "--use-session", "sess-1", "--judged-by", "session review",
                       now=T0)
        self.assertEqual(r.returncode, 0, r.stderr)
        v = self.rows("verdict")[0]
        self.assertEqual(v["verdict"], "WORKED")
        self.assertIn("return []", v["evidence"])
        self.assertEqual(v["use_session"], "sess-1")
        self.assertIn("judgement", v["judgement"],
                      "a verdict must label itself a judgement, never a measurement")

    def test_a_claim_with_no_quote_behind_it_is_not_written(self):
        for verdict in ("WORKED", "NO-OP", "MISFIRED"):
            r = self.forge("verdict", "--name", "widget", "--verdict", verdict, now=T0)
            self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.rows("verdict"), [])

    def test_unknown_is_first_class_and_may_be_written_bare(self):
        """UNKNOWN is the honest outcome when there is nothing to quote. Requiring a
        quote for it would make the honest answer the unwritable one."""
        r = self.forge("verdict", "--name", "widget", "--verdict", "UNKNOWN", now=T0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows("verdict")[0]["verdict"], "UNKNOWN")

    def test_an_invented_verdict_is_refused(self):
        r = self.forge("verdict", "--name", "w", "--verdict", "GREAT",
                       "--evidence", "x", now=T0)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.rows("verdict"), [])


# -------------------------------------------------------------------- the backfill

class BackfillTest(LedgerV2Case):

    def infile(self, *records):
        p = self.root / "reconstructed.jsonl"
        p.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return str(p)

    def test_reconstructed_rows_are_permanently_distinguishable(self):
        path = self.infile(
            {"event": "origin", "ts": T0, "name": "old-skill", "origin": "forged",
             "source": "transcript 2026-08-24, orchestrator session"},
            {"event": "use", "ts": T0 + 10, "name": "old-skill", "ok": True,
             "harness": False, "recorded": "derived",
             "source": "transcript -Users-me-proj/sess.jsonl"})
        r = self.forge("backfill", path, now=T0 + 1000)
        self.assertEqual(r.returncode, 0, r.stderr)
        for row in self.rows("origin") + self.rows("use"):
            self.assertIs(row.get("backfilled"), True)
            self.assertEqual(row["confidence"], "reconstructed")
            self.assertEqual(row["reconstructed_at"], T0 + 1000)
            self.assertTrue(row["source"])

    def test_a_row_with_no_source_refuses_the_whole_file(self):
        """All-or-nothing. There is no undo for an append, and a half-imported file
        cannot be told from a complete one afterwards."""
        path = self.infile(
            {"event": "origin", "ts": T0, "name": "a", "origin": "forged",
             "source": "a real transcript"},
            {"event": "use", "ts": T0, "name": "b", "ok": True})
        r = self.forge("backfill", path, now=T0)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("no source", r.stderr)
        self.assertEqual(self.rows("origin"), [], "nothing may be imported from a "
                                                  "file that was refused")

    def test_it_is_re_runnable(self):
        path = self.infile(
            {"event": "origin", "ts": T0, "name": "a", "origin": "forged",
             "source": "s"},
            {"event": "use", "ts": T0, "name": "a", "session": "x", "ok": True,
             "source": "s"})
        self.forge("backfill", path, now=T0)
        before = len(self.rows())
        r = self.forge("backfill", path, now=T0 + 5)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.rows()), before, "a second import duplicated rows")
        self.assertIn("skipped 2", r.stdout)

    def test_a_live_row_is_never_rewritten(self):
        self.forge("origin", "--name", "a", "--origin", "adopted", now=T0)
        path = self.infile({"event": "origin", "ts": T0 - 100, "name": "a",
                            "origin": "forged", "source": "a transcript"})
        r = self.forge("backfill", path, now=T0 + 10)
        self.assertEqual(r.returncode, 0, r.stderr)
        origins = self.rows("origin")
        self.assertEqual(len(origins), 1)
        self.assertIs(origins[0]["backfilled"], False,
                      "the reconstructed row overwrote a live one")

    def test_a_row_claiming_to_be_live_is_refused(self):
        path = self.infile({"event": "origin", "ts": T0, "name": "a",
                            "origin": "forged", "source": "s", "backfilled": False})
        r = self.forge("backfill", path, now=T0)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("backfilled:false", r.stderr)

    def test_a_forge_event_cannot_be_smuggled_in(self):
        """Only origin, use and verdict. A reconstructed `start` row would change the
        forge count and the reuse denominator, which are measurements."""
        path = self.infile({"event": "start", "ts": T0, "name": "a", "steps": 8,
                            "source": "s"})
        r = self.forge("backfill", path, now=T0)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.rows("start"), [])


# ---------------------------------------------------------------------- the horizon

class HorizonTest(LedgerV2Case):

    def test_a_fresh_ledger_records_that_it_is_complete_from_now(self):
        self.forge("start", "a", "4", "s", "--trigger", "x",
                   "--trigger-kind", "user-prompt", now=T0)
        h = self.rows("horizon")
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["known_from"], T0)
        self.assertEqual(h[0]["complete_from"], T0,
                         "an empty ledger is the one case where completeness IS known")

    def test_an_existing_ledger_gets_a_horizon_that_claims_nothing(self):
        """The live ledger on the machine this was written on has a 7.4-hour
        pre-history in which a real forge ran and produced a real skill, with no row of
        it anywhere. Read without a horizon, that absence reads as a negative result."""
        self.write_ledger({"event": "start", "name": "old", "ts": T0 - 5000,
                           "steps": 8, "summary": "s"})
        self.forge("start", "a", "4", "s", "--trigger", "x",
                   "--trigger-kind", "user-prompt", now=T0)
        h = self.rows("horizon")[0]
        self.assertEqual(h["known_from"], T0 - 5000,
                         "known_from is the earliest row actually present")
        self.assertNotIn("complete_from", h,
                         "completeness before an existing ledger is unestablished, so "
                         "the field must be absent rather than guessed")

    def test_only_one_horizon_is_ever_written(self):
        for i in range(3):
            self.forge("start", "a%d" % i, "4", "s", "--trigger", "x",
                       "--trigger-kind", "user-prompt", now=T0 + i)
            self.forge("done", "ok", now=T0 + i + 1)
        self.assertEqual(len(self.rows("horizon")), 1)


# ------------------------------------------- the readers must not miscount new rows

class BackCompatTest(LedgerV2Case):
    """A ledger holding v2 rows must be counted by both readers exactly as before.

    This is the assertion the whole schema rests on. Both readers select the events
    they understand BY NAME; a reader that classified by exclusion -- anything that is
    not a start is an outcome -- would fold every `use` row into the forge count on the
    day this landed.
    """

    def a_mixed_ledger(self):
        self.write_ledger(
            {"event": "horizon", "ts": T0 - 1, "known_from": T0 - 1,
             "confidence": "measured", "backfilled": False},
            {"event": "start", "name": "widget", "ts": T0, "steps": 8, "summary": "s",
             "project": "/Users/me/proj", "trigger_verbatim": "the user asked",
             "trigger_kind": "user-prompt"},
            {"event": "origin", "ts": T0 + 1, "name": "widget", "origin": "forged",
             "confidence": "measured", "backfilled": False},
            {"event": "done", "name": "widget", "ts": T0 + 600, "steps": 8,
             "summary": "s", "project": "/Users/me/proj", "step": 8, "phase": "ok",
             "duration": 600, "rounds": 3, "rounds_planned": 3},
            # Four use rows and a verdict: none of them is a forge.
            *[{"event": "use", "ts": T0 + 1000 + i, "name": "widget", "ok": True,
               "harness": False, "recorded": "live", "session": "s%d" % i,
               "confidence": "measured", "backfilled": False} for i in range(4)],
            {"event": "verdict", "ts": T0 + 2000, "name": "widget", "verdict": "WORKED",
             "evidence": "a quote", "confidence": "measured", "backfilled": False},
        )

    def test_the_forge_count_is_unchanged_by_use_rows(self):
        self.a_mixed_ledger()
        out = self.forge("ledger").stdout
        self.assertIn("1 forge(s)", out,
                      "a use row was counted as a forge:\n" + out)
        self.assertIn("1 done", out)

    def test_skillreport_counts_one_forge_and_one_denominator(self):
        self.a_mixed_ledger()
        out = self.report().stdout
        self.assertIn("of 1 finished forges", out,
                      "the reuse denominator moved when v2 rows were added:\n" + out)

    def test_use_rows_do_not_become_reuse_in_the_transcript_table(self):
        """USES SINCE counts transcript invocations. Ledger `use` rows are a different
        instrument over a different interval, and adding them would double-count the
        window where both exist."""
        self.a_mixed_ledger()
        self.transcript("-Users-me-proj", "sess-A",
                        [("widget", T0 + 5000, "/Users/me/proj", "toolu_1", False)])
        out = self.report().stdout
        row = [l for l in out.splitlines() if l.startswith("widget")][0]
        self.assertEqual(row.split()[-2:], ["1", "1"],
                         "one transcript invocation must count once: " + row)

    def test_the_harness_exclusion_still_holds_with_v2_rows_present(self):
        """The `sdk-cli` exclusion and the failed-invocation exclusion are the two
        corrections that made the headline honest. Neither may regress."""
        self.a_mixed_ledger()
        self.transcript("-Users-me-proj", "sess-probe",
                        [("widget", T0 + 5000, "/tmp/probe", "toolu_p", False)],
                        entrypoint="sdk-cli")
        self.transcript("-Users-me-proj2", "sess-bad",
                        [("widget", T0 + 6000, "/Users/me/proj", "toolu_b", True)],
                        entrypoint="cli")
        out = self.report().stdout
        row = [l for l in out.splitlines() if l.startswith("widget")][0]
        self.assertEqual(row.split()[-2], "0",
                         "a probe invocation or a failed one reached USES SINCE: " + row)
        self.assertIn("EXCLUDED AS PROBE/TEST HARNESS", out)
        self.assertIn("REUSE: 0 of 1", out)

    def test_an_event_from_the_future_is_ignored_rather_than_miscounted(self):
        """Forward compatibility, stated as a test: a row this build has never heard of
        must not become a forge, an outcome or a use."""
        self.a_mixed_ledger()
        with open(str(self.ledger), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "retirement", "ts": T0 + 3000,
                                 "name": "widget", "reason": "superseded"}) + "\n")
        self.assertIn("1 forge(s)", self.forge("ledger").stdout)
        self.assertIn("of 1 finished forges", self.report().stdout)


# ----------------------------------------------------------------- the skills view

class SkillsViewTest(LedgerV2Case):

    def populated(self):
        self.write_ledger(
            {"event": "horizon", "ts": T0, "known_from": T0,
             "note": "n", "confidence": "measured", "backfilled": False},
            {"event": "origin", "ts": T0, "name": "widget", "origin": "forged",
             "skill_dir": "/Users/me/proj/skills/widget", "shipped": False,
             "trigger_verbatim": "the user said: stop the flake",
             "trigger_kind": "user-prompt", "confidence": "measured",
             "backfilled": False},
            {"event": "origin", "ts": T0, "name": "seeded-one", "origin": "adopted",
             "shipped": True, "trigger_kind": "unrecorded",
             "confidence": "measured", "backfilled": False},
            {"event": "use", "ts": T0 + 100, "name": "widget", "ok": True,
             "harness": False, "session": "s1", "recorded": "live",
             "confidence": "measured", "backfilled": False},
            {"event": "use", "ts": T0 + 200, "name": "widget", "ok": True,
             "harness": True, "session": "probe", "recorded": "live",
             "confidence": "measured", "backfilled": False},
            {"event": "verdict", "ts": T0 + 300, "name": "widget", "verdict": "WORKED",
             "evidence": "quote", "judgement": "model judgement",
             "confidence": "measured", "backfilled": False},
        )

    def test_it_answers_all_four_questions_for_one_skill(self):
        self.populated()
        out = self.report("skills").stdout
        self.assertIn("stop the flake", out, "what triggered the build")
        self.assertIn("user-prompt", out)
        self.assertIn("/Users/me/proj/skills/widget", out, "what was built, and where")
        self.assertIn("1 genuine", out, "used since")
        self.assertIn("WORKED", out, "did it work")

    def test_harness_traffic_is_never_folded_into_genuine_use(self):
        self.populated()
        out = self.report("skills").stdout
        self.assertIn("1 harness", out)
        self.assertNotIn("2 genuine", out,
                         "a probe invocation was counted as a genuine one")

    def test_an_unrecorded_trigger_says_so_rather_than_printing_nothing(self):
        self.populated()
        out = self.report("skills").stdout
        self.assertIn("NOT RECORDED", out)

    def test_a_verdict_is_labelled_a_judgement(self):
        self.populated()
        self.assertIn("not measurements", self.report("skills").stdout)

    def test_the_horizon_is_printed_so_absence_is_not_read_as_none(self):
        self.populated()
        out = self.report("skills").stdout
        self.assertIn("horizon", out.lower())
        self.assertIn("UNKNOWN, not none", out)

    def test_an_empty_ledger_reports_no_data_rather_than_zeroes(self):
        out = self.report("skills").stdout
        self.assertIn("no ledger yet", out)
        self.assertNotIn("0%", out)

    def test_a_skill_with_uses_but_no_origin_is_shown_not_hidden(self):
        self.write_ledger(
            {"event": "use", "ts": T0, "name": "stranger", "ok": True,
             "harness": False, "session": "s1", "recorded": "live",
             "confidence": "measured", "backfilled": False})
        out = self.report("skills").stdout
        self.assertIn("stranger", out)
        self.assertIn("NO ORIGIN ROW", out)

    def test_reconstructed_rows_are_labelled_in_the_view(self):
        self.write_ledger(
            {"event": "origin", "ts": T0, "name": "old", "origin": "forged",
             "backfilled": True, "confidence": "reconstructed",
             "source": "transcript 2026-08-24", "reconstructed_at": T0 + 1})
        out = self.report("skills").stdout
        self.assertIn("reconstructed", out)
        self.assertIn("transcript 2026-08-24", out)


# ------------------------------------------------------------------- adoption

class AdoptionTest(unittest.TestCase):
    """Install gives every skill in the pool an origin row, or honestly says unknown.

    Runs the real installer against a real temporary Claude directory, and reads the
    ledger the real `skillforge` wrote. Three of the nine shipped skills had a forge
    record; the other six were invisible to every question the ledger is asked, and a
    skill with no origin row reports zero uses -- which reads as "nobody used it" when
    the truth is that nobody was recording.
    """

    def setUp(self):
        from skill_compounder import installer
        self.installer = installer
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.claude = self.root / "claude"
        self.bin = self.root / "bin"
        self.state = self.root / "state"
        for d in (self.claude, self.bin, self.state):
            d.mkdir(parents=True)
        self.ledger = self.state / "ledger.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def install(self):
        return self.installer.install(str(REPO), str(self.claude), str(self.bin),
                                      str(self.state))

    def origins(self):
        if not self.ledger.exists():
            return {}
        out = {}
        for line in self.ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("event") == "origin":
                out.setdefault(row["name"], []).append(row)
        return out

    def test_every_shipped_skill_gets_an_origin_row(self):
        self.install()
        shipped = sorted(d.name for d in (REPO / "skills").iterdir()
                         if (d / "SKILL.md").is_file())
        origins = self.origins()
        for name in shipped:
            self.assertIn(name, origins, "%s entered the pool with no origin row" % name)
            self.assertEqual(origins[name][0]["origin"], "adopted")
            self.assertIs(origins[name][0]["shipped"], True)
            self.assertIs(origins[name][0]["backfilled"], False)

    def test_installing_twice_writes_one_row_per_skill(self):
        self.install()
        first = {k: len(v) for k, v in self.origins().items()}
        self.install()
        second = {k: len(v) for k, v in self.origins().items()}
        self.assertEqual(second, first)
        self.assertTrue(all(n == 1 for n in second.values()), second)

    def test_somebody_elses_skill_is_never_adopted(self):
        """A link into another project's checkout belongs to that project. Writing a
        row for it would be this package describing a skill it never touched --
        `_link_is_ours` is the same four-proof judgement the rest of the installer uses,
        and a link that proves nothing is reported, not adopted.
        """
        foreign_src = self.root / "other-project" / "skills" / "history-surfer"
        foreign_src.mkdir(parents=True)
        (foreign_src / "SKILL.md").write_text(
            "---\nname: history-surfer\ndescription: Use when searching history.\n---\n",
            encoding="utf-8")
        (self.claude / "skills").mkdir(exist_ok=True)
        os.symlink(str(foreign_src), str(self.claude / "skills" / "history-surfer"))
        report = self.install()
        self.assertNotIn("history-surfer", self.origins(),
                         "another project's skill was adopted into our ledger")
        self.assertIn("another project", report["ledger"])

    def test_a_skill_the_user_has_of_their_own_is_recorded_as_unknown(self):
        """A real directory in the installed skills dir may be one we forged there for
        personal use -- the normal case in the field -- or the user's own work. Nothing
        can tell the two apart, so the row says `unknown`, which is a better record than
        no record and an honest one either way."""
        mine = self.claude / "skills" / "hand-written"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text(
            "---\nname: hand-written\ndescription: Use when writing by hand.\n---\n",
            encoding="utf-8")
        self.install()
        origins = self.origins()
        self.assertIn("hand-written", origins)
        self.assertEqual(origins["hand-written"][0]["origin"], "unknown",
                         "authorship this package cannot prove must not be claimed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
