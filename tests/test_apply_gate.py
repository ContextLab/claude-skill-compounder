#!/usr/bin/env python3
"""Tests for hooks/apply-gate.sh and the ⚑ pending-apply segment of the status line.

NO MOCKS, per this repo's standing rule. Every test writes real marker files to a real
temp directory, runs the real shell scripts through `subprocess` with a minimal PATH,
HOME and SKILL_COMPOUNDER_STATE pinned into that directory, and reads the decision or
the rendered segment off stdout.

THE MARKERS ARE WRITTEN DIRECTLY, NOT THROUGH `skillforge done`, AND THAT IS THE HONEST
TEST RATHER THAN A SHORTCUT. The gate's contract is the file:

    <state>/apply-pending/<safe-name>.json
      {"name": ..., "forge": ..., "skill_dir": ..., "trigger": ..., "trigger_kind": ...,
       "summary": ..., "closed": <epoch>, "session": ..., "installed": <bool>}

A test that drove the CLI would prove the pair agree with each other and nothing about
whether either agrees with the contract; writing the file is what pins the hook to the
shape a *different* program promises to produce. The same argument covers the forge slots
below, which are written straight into <state>/forge/ -- docs/DESIGN.md states that any
`*.json` there carrying `name` and `status` is a forge, so that shape is the contract too.

EVERY subprocess call against the hook passes `input=`. The script reads its payload with
`payload="$(cat)"`; without stdin it hangs forever. The status line does the same with
`cat >/dev/null`, so it gets `input=` as well.

BOTH CLOCKS ARE PINNED, AND THEY ARE DIFFERENT VARIABLES. The hook reads APPLY_GATE_NOW
and the status line reads SKILLFORGE_NOW; pinning one does nothing to the other, which is
exactly the trap .claude/CLAUDE.md warns about, so each test pins the one it needs.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "hooks" / "apply-gate.sh"
RENDER = REPO / "statusline" / "skillforge-status.sh"

BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
STATUS_PAYLOAD = json.dumps({"session_id": "abc", "workspace": {"current_dir": "/repo"}})
ANSI = re.compile(r"\033\[[0-9;]*m")

ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\ufeff"}


def cell_width(ch):
    """Terminal cells for one codepoint.

    Copied from tests/test_statusline.py deliberately rather than imported: a combining
    mark or a zero-width joiner advances the cursor by nothing and a CJK or emoji
    codepoint by two, and the renderer's own width table is what is under test here.
    """
    if unicodedata.combining(ch) or ch in ZERO_WIDTH or 0xFE00 <= ord(ch) <= 0xFE0F:
        return 0
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def columns(text):
    return sum(cell_width(c) for c in ANSI.sub("", text))


# A stand-in for the KERNEL, not for anything in this package: a real executable named
# `jq`, put first on PATH, that refuses any single argv element over MAX_ARG_STRLEN and
# otherwise execs the real jq. That is what execve(2) does on Linux and what macOS does
# not do, which is the whole reason CI could be red while this suite was green.
#
# The length is counted under LC_ALL=C so `${#a}` counts BYTES rather than characters --
# the kernel counts bytes, and a 409 KB message of 3-byte glyphs is only 136 KB of
# characters. LC_ALL is restored before the exec so the real jq runs in the caller's
# locale.
SHIM_JQ = r"""#!/bin/bash
_shim_saved_lc="${LC_ALL-}"
_shim_had_lc="${LC_ALL+yes}"
LC_ALL=C
for _shim_a in "$@"; do
  if [ "${#_shim_a}" -gt %(cap)d ]; then
    printf '%%s\n' "jq: Argument list too long" >&2
    exit 126
  fi
done
if [ -n "$_shim_had_lc" ]; then LC_ALL="$_shim_saved_lc"; else unset LC_ALL; fi
exec "%(real)s" "$@"
"""


class ApplyGateBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.pending = self.state / "apply-pending"
        self.pending.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------------ fixtures

    def marker(self, name, session="sess-A", closed=1000, trigger=None, **extra):
        """Write one apply-pending marker exactly as bin/skillforge promises to."""
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:96]
        rec = {
            "name": name,
            "forge": "forge-" + safe,
            "skill_dir": "/skills/" + safe,
            "trigger": trigger if trigger is not None else "%s was needed twice" % name,
            "trigger_kind": "named",
            "summary": "one line about %s" % name,
            "closed": closed,
            "session": session,
            "installed": True,
        }
        rec.update(extra)
        p = self.pending / (safe + ".json")
        p.write_text(json.dumps(rec))
        return p

    def forge_slot(self, name, status="active", **extra):
        """A live forge slot, in the shape docs/DESIGN.md documents as the contract."""
        d = self.state / "forge"
        d.mkdir(parents=True, exist_ok=True)
        rec = {"name": name, "status": status, "started": 900, "updated": 900,
               "step": 2, "steps": 8, "phase": "red-team round 1",
               "summary": "a summary"}
        rec.update(extra)
        # Truncated the way bin/skillforge's safe_name() truncates, for the same reason
        # marker() above does: a slot file is named by the sanitised skill name cut to 96,
        # and a filesystem refuses a longer one outright (ENAMETOOLONG) before any of this
        # code is reached.
        p = d / (re.sub(r"[^A-Za-z0-9._-]", "_", name)[:96] + ".json")
        p.write_text(json.dumps(rec))
        return p

    def env(self, **extra):
        e = {"PATH": BASE_PATH, "HOME": str(self.state),
             "SKILL_COMPOUNDER_STATE": str(self.state)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    # --------------------------------------------------------------------- runners

    def stop(self, session="sess-A", prompt="p1", now=4600, **envextra):
        payload = {"hook_event_name": "Stop", "session_id": session,
                   "prompt_id": prompt, "stop_hook_active": False,
                   "transcript_path": str(self.state / "t.jsonl"),
                   "last_assistant_message": "All done."}
        return self.run_hook(payload, APPLY_GATE_NOW=now, **envextra)

    def run_hook(self, payload, **envextra):
        r = subprocess.run([str(HOOK)], input=json.dumps(payload),
                           capture_output=True, text=True, env=self.env(**envextra))
        # A hook may never break a turn, whatever it decides.
        self.assertEqual(r.returncode, 0, "the hook exited %d: %r" % (r.returncode, r.stderr))
        self.assertEqual(r.stderr, "", "the hook wrote to stderr: %r" % r.stderr)
        return r.stdout

    def decision(self, out):
        """The parsed block, or None when the hook stayed silent."""
        if out.strip() == "":
            return None
        return json.loads(out)

    def render(self, now=4600, **envextra):
        r = subprocess.run([str(RENDER)], input=STATUS_PAYLOAD, capture_output=True,
                           text=True, env=self.env(SKILLFORGE_NOW=now, **envextra))
        self.assertEqual(r.returncode, 0, "the renderer exited %d" % r.returncode)
        self.assertEqual(r.stderr, "", "the renderer wrote to stderr: %r" % r.stderr)
        return r.stdout


# ============================================================================= hook
class ApplyGateHookTest(ApplyGateBase):

    def test_a_marker_from_this_session_blocks_the_turn(self):
        self.marker("dead-guard-detection")
        d = self.decision(self.stop())
        self.assertIsNotNone(d, "an unapplied skill forged in this session must block")
        self.assertEqual(d["decision"], "block")
        self.assertIn("dead-guard-detection", d["reason"])

    def test_a_marker_from_another_session_never_blocks(self):
        """Blocking session B on a forge it did not run is the misfire that would get
        this hook switched off: B cannot honestly write `used`, and writing `declined`
        to clear somebody else's flag puts a false row in the ledger. The status line
        carries it to B instead, which asks nothing of it."""
        self.marker("dead-guard-detection", session="sess-OTHER")
        self.assertIsNone(self.decision(self.stop(session="sess-A")))

    def test_the_reason_quotes_the_trigger_verbatim(self):
        trigger = ("wc -c < f prints a leading-space-padded count on BSD, so the numeric "
                   "case guard read the space as non-numeric and zeroed the cap")
        self.marker("dead-guard-detection", trigger=trigger)
        d = self.decision(self.stop())
        self.assertIn(trigger, d["reason"],
                      "the trigger is the whole argument for applying the skill and must "
                      "not be paraphrased")

    def test_the_reason_gives_the_exact_apply_command_for_both_outcomes(self):
        self.marker("finish-task")
        reason = self.decision(self.stop())["reason"]
        self.assertIn(
            'skillforge apply --name finish-task --outcome used --evidence "<what happened>"',
            reason)
        self.assertIn(
            'skillforge apply --name finish-task --outcome declined --evidence "<why not>"',
            reason)

    def test_it_blocks_at_most_once_per_session_per_skill(self):
        """A gate that can trap a session in a loop it cannot exit is worse than no gate,
        and a session may legitimately conclude the skill did not apply. So the gate says
        its piece once and then lets go, whatever the session does about it."""
        self.marker("documentation-sync")
        self.assertIsNotNone(self.decision(self.stop(prompt="p1")))
        self.assertIsNone(self.decision(self.stop(prompt="p2")),
                          "a second turn must not be blocked for the same skill")
        self.assertIsNone(self.decision(self.stop(prompt="p3")))

    def test_a_skill_forged_later_in_the_same_session_still_blocks(self):
        """The once-per-skill release must not become once-per-session: closing a second
        forge is a new open loop and the gate has not spoken about that one."""
        self.marker("documentation-sync")
        self.assertIsNotNone(self.decision(self.stop(prompt="p1")))
        self.marker("finish-task", closed=2000)
        d = self.decision(self.stop(prompt="p2"))
        self.assertIsNotNone(d)
        self.assertIn("finish-task", d["reason"])
        self.assertNotIn("documentation-sync", d["reason"],
                         "a skill already named once must not be named again")

    def test_double_delivery_of_one_event_blocks_exactly_once(self):
        """With settings.json and the plugin manifest both active every hook is delivered
        twice. The claim is keyed on session + prompt_id, so the duplicate is silent."""
        self.marker("dead-guard-detection")
        first = self.decision(self.stop(prompt="dup"))
        second = self.decision(self.stop(prompt="dup"))
        self.assertIsNotNone(first)
        self.assertIsNone(second, "the duplicate delivery must not interrupt a second time")

    def test_one_stop_event_produces_one_block_even_if_a_forge_closes_between_deliveries(self):
        """What the per-TURN claim buys that the per-skill claim does not.

        The per-skill `mkdir` alone makes a duplicate delivery silent whenever both
        deliveries see the same set of markers, which is why removing the turn claim
        broke no test until this one existed. It does NOT bound the interleaved case: two
        deliveries racing over two fresh markers can each win one and each print, so one
        Stop event interrupts the user twice. A marker appearing BETWEEN two deliveries of
        the same event is the deterministic stand-in for that race, and the turn claim is
        what holds the line at one block per event."""
        self.marker("first-skill", closed=1000)
        d1 = self.decision(self.stop(prompt="dup"))
        self.assertIn("first-skill", d1["reason"])
        self.marker("second-skill", closed=1200)
        self.assertIsNone(self.decision(self.stop(prompt="dup")),
                          "a second delivery of one Stop event must never block again")
        d3 = self.decision(self.stop(prompt="next-turn"))
        self.assertIsNotNone(d3, "the skill it stayed quiet about must return next turn")
        self.assertIn("second-skill", d3["reason"])

    def test_a_marker_older_than_the_window_is_not_blocked_on(self):
        """The two halves run as two DIFFERENT sessions rather than re-running setUp,
        because the once-per-session-per-skill claim would otherwise silence the second
        half for the wrong reason and the test would pass whatever the window did."""
        self.marker("stale-skill", closed=1000, session="sess-in")
        self.marker("stale-skill-2", closed=1000, session="sess-out")
        # 1000 + 86400 = 87400 is the last second inside the default window.
        self.assertIsNotNone(self.decision(self.stop(session="sess-in", now=87400)))
        self.assertIsNone(self.decision(self.stop(session="sess-out", now=87401)),
                          "a forge closed outside the window is archaeology, not a turn's "
                          "business")

    def test_the_window_is_tunable(self):
        self.marker("stale-skill", closed=1000, session="sess-out")
        self.marker("stale-skill-2", closed=1000, session="sess-in")
        self.assertIsNone(self.decision(
            self.stop(session="sess-out", now=1601, APPLY_GATE_WINDOW=600)))
        self.assertIsNotNone(self.decision(
            self.stop(session="sess-in", now=1600, APPLY_GATE_WINDOW=600)))

    def test_a_nonsense_window_falls_back_to_the_default(self):
        """A knob set wrong must degrade to the default, never to silence and never to an
        arithmetic error on a hook's stderr once per turn."""
        self.marker("dead-guard-detection")
        self.assertIsNotNone(self.decision(self.stop(APPLY_GATE_WINDOW="abc")))

    def test_the_off_switch_silences_it(self):
        self.marker("dead-guard-detection")
        self.assertIsNone(self.decision(
            self.stop(SKILL_COMPOUNDER_APPLY_GATE=0)))

    def test_stop_hook_active_is_honoured(self):
        """The platform's own loop flag: true on any Stop that exists only because a Stop
        hook blocked. Ignoring it loops the session."""
        self.marker("dead-guard-detection")
        payload = {"hook_event_name": "Stop", "session_id": "sess-A",
                   "prompt_id": "p1", "stop_hook_active": True}
        self.assertIsNone(self.decision(self.run_hook(payload, APPLY_GATE_NOW=4600)))

    def test_it_is_inert_on_every_other_event(self):
        self.marker("dead-guard-detection")
        for event in ("PreToolUse", "PostToolUse", "PostToolUseFailure",
                      "UserPromptSubmit", "SessionStart"):
            with self.subTest(event=event):
                payload = {"hook_event_name": event, "session_id": "sess-A",
                           "prompt_id": "p1", "tool_name": "Bash",
                           "tool_input": {"command": "ls"}}
                self.assertIsNone(self.decision(self.run_hook(payload, APPLY_GATE_NOW=4600)))

    def test_a_malformed_marker_is_skipped_and_is_not_fatal(self):
        """Skipped, never repaired and never deleted: it may be half-written, or written
        by a newer CLI than this hook. A good marker beside it must still be seen."""
        (self.pending / "truncated.json").write_text('{"name":"x","closed":')
        (self.pending / "notjson.json").write_text("this is not json at all")
        (self.pending / "anarray.json").write_text("[1,2,3]")
        (self.pending / "nostamp.json").write_text(
            json.dumps({"name": "no-closed", "session": "sess-A"}))
        (self.pending / "noname.json").write_text(
            json.dumps({"name": "   ", "session": "sess-A", "closed": 1000}))
        self.marker("dead-guard-detection")
        d = self.decision(self.stop())
        self.assertIsNotNone(d, "one unreadable marker must not disarm the gate")
        self.assertIn("dead-guard-detection", d["reason"])
        for f in ("truncated.json", "notjson.json", "anarray.json", "nostamp.json"):
            self.assertTrue((self.pending / f).exists(),
                            "%s was removed; this hook may not delete state it does not "
                            "understand" % f)

    def test_only_malformed_markers_means_silence(self):
        (self.pending / "notjson.json").write_text("nope")
        self.assertIsNone(self.decision(self.stop()))

    def test_no_pending_directory_is_silent(self):
        for f in self.pending.iterdir():
            f.unlink()
        self.pending.rmdir()
        self.assertIsNone(self.decision(self.stop()))

    def test_an_empty_pending_directory_is_silent(self):
        self.assertIsNone(self.decision(self.stop()))

    def test_a_payload_with_no_session_id_never_blocks(self):
        """The gate blocks only on what it can attribute to this session."""
        self.marker("dead-guard-detection", session="")
        payload = {"hook_event_name": "Stop", "prompt_id": "p1"}
        self.assertIsNone(self.decision(self.run_hook(payload, APPLY_GATE_NOW=4600)))

    def test_a_marker_with_no_session_is_never_blocked_on(self):
        self.marker("dead-guard-detection", session="")
        self.assertIsNone(self.decision(self.stop(session="sess-A")))

    def test_a_future_closed_stamp_is_treated_as_just_closed(self):
        """A stamp ahead of the clock is two clocks disagreeing, not a marker from
        tomorrow. Discarding it would silently drop a real flag."""
        self.marker("dead-guard-detection", closed=99999)
        d = self.decision(self.stop(now=4600))
        self.assertIsNotNone(d)
        self.assertIn("forged 0m ago", d["reason"])

    def test_the_hook_never_writes_or_removes_a_marker(self):
        p = self.marker("dead-guard-detection")
        before = p.read_text()
        self.stop()
        self.assertTrue(p.exists(), "the gate cleared its own flag; only `skillforge "
                                    "apply` may do that")
        self.assertEqual(p.read_text(), before)

    def test_several_pending_skills_are_all_named_in_one_block(self):
        """The claims and the message must not disagree: a skill silenced for the session
        but never shown to the user is a flag that vanished without being read."""
        for i, name in enumerate(("alpha-skill", "beta-skill", "gamma-skill")):
            self.marker(name, closed=1000 + i)
        d = self.decision(self.stop(prompt="p1"))
        for name in ("alpha-skill", "beta-skill", "gamma-skill"):
            self.assertIn(name, d["reason"])
        self.assertIsNone(self.decision(self.stop(prompt="p2")),
                          "every named skill must have been claimed by that one block")

    def test_skills_past_max_named_are_not_claimed_and_come_back(self):
        for i, name in enumerate(("alpha-skill", "beta-skill", "gamma-skill")):
            self.marker(name, closed=1000 + i)
        d = self.decision(self.stop(prompt="p1", APPLY_GATE_MAX_NAMED=1))
        named = [n for n in ("alpha-skill", "beta-skill", "gamma-skill")
                 if n in d["reason"]]
        self.assertEqual(len(named), 1)
        self.assertIn("2 more still pending", d["reason"])
        d2 = self.decision(self.stop(prompt="p2", APPLY_GATE_MAX_NAMED=1))
        self.assertIsNotNone(d2, "the unnamed ones must still be able to block later")
        self.assertNotIn(named[0], d2["reason"])

    def test_an_already_named_skill_is_not_counted_in_the_overflow(self):
        """The one place the `-d` test still decides something: whether a skill counts
        toward `... and N more still pending`. Naming one skill, then closing two more
        forges, puts an already-named skill ahead of a fresh one past MAX_NAMED -- and
        without the test the message overstates what is outstanding.

        The candidate order is the filename sort, so `b-skill` sits between `a-skill` and
        `c-skill` by construction."""
        self.marker("b-skill", closed=1000)
        d1 = self.decision(self.stop(prompt="p1", APPLY_GATE_MAX_NAMED=1))
        self.assertIn("b-skill", d1["reason"])
        self.marker("a-skill", closed=1100)
        self.marker("c-skill", closed=1200)
        d2 = self.decision(self.stop(prompt="p2", APPLY_GATE_MAX_NAMED=1))
        self.assertIn("a-skill", d2["reason"])
        self.assertIn("1 more still pending", d2["reason"])
        self.assertNotIn("2 more still pending", d2["reason"],
                         "b-skill has already been named and must not be counted again")

    def test_stale_claim_directories_are_pruned(self):
        """Claim markers are small but a long-lived state root must not keep them
        forever. Two days, the same shape hooks/claim-gate.sh uses."""
        self.marker("dead-guard-detection")
        gate = self.state / "apply-gate"
        gate.mkdir()
        old = gate / "ancient.turn"
        old.mkdir()
        fresh = gate / "recent.turn"
        fresh.mkdir()
        long_ago = 60 * 60 * 24 * 5
        os.utime(old, (os.stat(old).st_atime - long_ago,
                       os.stat(old).st_mtime - long_ago))
        self.stop()
        self.assertFalse(old.exists(), "a five-day-old claim directory must be pruned")
        self.assertTrue(fresh.exists(), "a fresh claim directory must survive")

    def test_an_unwritable_state_directory_fails_open(self):
        """Fail closed on the CLAIM means fail open on the TURN: with nowhere to record
        that it spoke, the hook must say nothing rather than risk speaking every turn."""
        self.marker("dead-guard-detection")
        gate = self.state / "apply-gate"
        gate.mkdir()
        os.chmod(gate, 0o500)
        try:
            self.assertIsNone(self.decision(self.stop()))
        finally:
            os.chmod(gate, 0o700)

    def test_the_debug_dump_captures_the_payload(self):
        dump = self.state / "dump.txt"
        self.marker("dead-guard-detection")
        self.stop(APPLY_GATE_DEBUG_DUMP=str(dump))
        self.assertIn("sess-A", dump.read_text())

    def test_a_trigger_with_shell_and_json_metacharacters_survives(self):
        """The trigger is free text written by whoever started the forge. It reaches the
        model through jq, so the block must still be valid JSON."""
        trigger = 'he said "$(rm -rf /)" and `backticks` and \\ and a } brace'
        self.marker("nasty-skill", trigger=trigger)
        d = self.decision(self.stop())
        self.assertIn(trigger, d["reason"])

    def test_control_characters_in_a_trigger_do_not_split_the_fields(self):
        """Fields are separated by US (0x1f) and cleaned inside jq. A trigger carrying a
        raw separator must not shift the parse."""
        self.marker("nasty-skill", trigger="line one\u001ftwo\nthree\ttab")
        d = self.decision(self.stop())
        self.assertIsNotNone(d)
        self.assertIn("nasty-skill", d["reason"])
        self.assertIn("line one two three tab", d["reason"])


# ====================================================================== status line
class PendingSegmentTest(ApplyGateBase):

    def test_a_pending_marker_renders_when_nothing_is_forging(self):
        self.marker("dead-guard-detection", closed=1000)
        out = ANSI.sub("", self.render(now=4600))
        self.assertIn("⚑", out)
        self.assertIn("dead-guard-detection", out)
        self.assertIn("not yet used", out)
        self.assertIn("1h00m", out)

    def test_a_marker_from_any_session_is_surfaced_here(self):
        """The complement of the hook's session rule: the gate refuses only its own
        session, so every other session has to learn about the flag from the line."""
        self.marker("dead-guard-detection", session="sess-OTHER")
        self.assertIn("dead-guard-detection", ANSI.sub("", self.render()))

    def test_nothing_renders_with_no_markers_and_no_forge(self):
        self.assertEqual(self.render(), "")

    def test_a_live_forge_always_wins_the_line(self):
        self.marker("dead-guard-detection")
        self.forge_slot("running-forge")
        out = ANSI.sub("", self.render())
        self.assertIn("running-forge", out)
        self.assertNotIn("⚑", out, "a pending flag may never displace a running forge")
        self.assertNotIn("dead-guard-detection", out)

    def test_a_terminal_forge_record_also_wins_until_it_is_reaped(self):
        """A ✓ still inside DONE_TTL is holding the line to say the forge closed. The ⚑
        takes over when it is reaped, which is the intended handoff: forged, then still
        not used."""
        self.marker("dead-guard-detection", closed=1000)
        self.forge_slot("closed-forge", status="done", finished=1000,
                        phase="clean pass", step=8)
        held = ANSI.sub("", self.render(now=1010))     # inside DONE_TTL (30s)
        self.assertIn("closed-forge", held)
        self.assertNotIn("⚑", held)
        after = ANSI.sub("", self.render(now=1100))    # past it; the slot is reaped
        self.assertIn("⚑", after)
        self.assertIn("dead-guard-detection", after)

    def test_the_segment_expires_on_its_own_ttl(self):
        self.marker("dead-guard-detection", closed=1000)
        self.assertIn("⚑", ANSI.sub("", self.render(now=87400)))    # 86400s old exactly
        self.assertEqual(self.render(now=87401), "",
                         "a marker nobody ever applied must not sit on the line forever")

    def test_the_ttl_is_tunable(self):
        self.marker("dead-guard-detection", closed=1000)
        self.assertIn("⚑", ANSI.sub("", self.render(now=1600, APPLY_PENDING_TTL=600)))
        self.assertEqual(self.render(now=1601, APPLY_PENDING_TTL=600), "")

    def test_a_nonsense_ttl_falls_back_to_the_default(self):
        self.marker("dead-guard-detection", closed=1000)
        self.assertIn("⚑", ANSI.sub("", self.render(now=4600, APPLY_PENDING_TTL="abc")))
        self.assertIn("⚑", ANSI.sub("", self.render(now=4600,
                                                    APPLY_PENDING_TTL="9999999999")))

    def test_expiry_hides_the_marker_but_never_deletes_it(self):
        """APPLY_PENDING_TTL governs SHOWING only. The marker belongs to the Stop gate and
        to `skillforge apply`; a renderer that deleted one would silently disarm a
        refusal, which is a liberty no display may take."""
        p = self.marker("dead-guard-detection", closed=1000)
        before = p.read_text()
        self.assertEqual(self.render(now=999999), "")
        self.assertTrue(p.exists(), "the status line deleted an apply-pending marker")
        self.assertEqual(p.read_text(), before)

    def test_several_markers_show_a_count_and_the_newest_name(self):
        self.marker("older-skill", closed=1000)
        self.marker("newest-skill", closed=3000)
        self.marker("middle-skill", closed=2000)
        out = ANSI.sub("", self.render(now=4600))
        self.assertIn("[3]", out)
        self.assertIn("newest-skill", out)
        self.assertNotIn("older-skill", out)

    def test_a_long_skill_name_does_not_blow_the_width_budget(self):
        """Nothing bounded the forge name once, and a 200-character one produced a
        275-column segment that wrapped the line and defeated in-place overwrite
        entirely. The flag segment is capped by the same NAME_WIDTH."""
        self.marker("x" * 400, closed=1000)
        out = self.render(now=4600)
        self.assertLessEqual(columns(out), 100,
                             "the pending segment must stay inside one terminal line")
        self.assertIn("…", ANSI.sub("", out), "a long name must be truncated, not wrapped")

    def test_a_wide_multibyte_name_is_measured_in_columns(self):
        """jq's `length` counts codepoints and a CJK codepoint occupies two cells. The
        cap has to be in columns or a wide name overruns it silently."""
        self.marker("スキルを鍛える段階" * 12, closed=1000)
        self.assertLessEqual(columns(self.render(now=4600)), 100)

    def test_a_malformed_marker_does_not_blank_the_segment(self):
        (self.pending / "notjson.json").write_text("nope")
        (self.pending / "anarray.json").write_text("[]")
        self.marker("dead-guard-detection", closed=1000)
        self.assertIn("dead-guard-detection", ANSI.sub("", self.render(now=4600)))

    def test_only_malformed_markers_render_nothing(self):
        (self.pending / "notjson.json").write_text("nope")
        self.assertEqual(self.render(), "")

    def test_a_future_closed_stamp_renders_as_just_now(self):
        self.marker("dead-guard-detection", closed=99999)
        self.assertIn("0m", ANSI.sub("", self.render(now=4600)))

    def test_a_pathological_name_cannot_defeat_the_width_cap(self):
        """THE CAP USED TO INVERT ON EXACTLY THE INPUT IT EXISTS FOR.

        `fit()` ended `... 2>/dev/null || printf '%s' "$1"`, and the jq it guards is an
        EXEC carrying the string in its argument vector. Past ARG_MAX (1048576 here) the
        exec fails, the redirect hides it, and the fallback printed the RAW UNCAPPED
        string -- so the bigger the input, the less the cap did.

        Measured before the fix, against a 32-column name budget: a 2000000-byte name in
        an apply-pending marker rendered 2000032 columns (2000064 bytes). Control, same
        run: the same marker with a 500000-byte name rendered 98 bytes, capped correctly --
        so the cap worked right up until the input got big enough to matter.

        The 400-byte case above is not this case. It never reaches the fallback, so it
        passed throughout and could not have caught this."""
        self.marker("N" * 2000000, closed=1000)
        out = self.render(now=4600)
        self.assertLessEqual(columns(out), 100,
                             "the width cap inverted: %d columns rendered into a "
                             "32-column name budget" % columns(out))
        self.assertIn("…", ANSI.sub("", out), "a cut name must say it was cut")

    def test_a_pathological_forge_name_cannot_defeat_the_width_cap(self):
        """Same exec, a different caller, and the reason the repair belongs in `fit`
        rather than at the pending segment: the forge-name path reads a `name` out of a
        slot file written by another program in exactly the same way. Measured before the
        fix: 2000073 columns (2000132 bytes) for one status line."""
        self.forge_slot("N" * 2000000)
        out = self.render(now=4600)
        self.assertLessEqual(columns(out), 120,
                             "%d columns rendered into one status line" % columns(out))
        self.assertIn("…", ANSI.sub("", out))

    def test_a_wide_input_at_the_boundary_still_renders_its_content(self):
        """The trim that keeps the exec alive must not become a cap of its own on
        anything a caller could legitimately show. The widest budget any caller may pass
        is SEGMENT_MAX (400 columns); this is comfortably inside the byte bound and must
        still render the name itself, not just an ellipsis."""
        self.marker("boundary-skill" + "x" * 300, closed=1000)
        out = ANSI.sub("", self.render(now=4600))
        self.assertIn("boundary-skill", out)
        self.assertLessEqual(columns(out), 100)

    def test_the_segment_is_stable_across_refreshes(self):
        """It carries no animation, so consecutive renders one second apart must be
        byte-identical -- escape sequences included. A width that wobbles makes the host
        clear and redraw the whole line once a second."""
        self.marker("dead-guard-detection", closed=1000)
        frames = {self.render(now=t) for t in range(4600, 4610)}
        self.assertEqual(len(frames), 1, "the pending segment must not flicker")


# ============================================================== the quote is bounded
class TriggerCapTest(ApplyGateBase):
    """Nothing bounded what this hook pasted into the model's context.

    Reproduced before the cap existed, one marker and one Stop payload, trigger length
    against bytes on stdout: 100000 -> 101182, 400000 -> 401182, 800000 -> 801182,
    1030000 -> 1031182. Dead linear at a constant offset of 1182, so there was no bound at
    all -- only whatever the writer of the marker felt like. The same four inputs now
    render 2526, 2526, 2526 and 2528 bytes (re-measured after the cap grew its byte half,
    which widened the announcement; see TriggerByteBoundTest below). hooks/claim-gate.sh has
    capped its own input since it shipped (CLAIM_GATE_MAX_BYTES); this file had none.

    THIS CLASS ONLY EVER MEASURES THE CAP IN CODEPOINTS, which is why it stayed green while
    the cap was defeated at its own documented ceilings. TriggerByteBoundTest is the half it
    could not see.

    The marker is written by another program against a documented file shape, and that
    shape bounds nothing, so the bound has to be here.
    """

    def reason(self, **kw):
        d = self.decision(self.stop(**kw))
        self.assertIsNotNone(d, "expected a block, got silence")
        return d["reason"]

    def test_a_giant_trigger_is_cut_and_the_cut_announces_itself(self):
        """The reviewer's own input size, through the marker contract."""
        self.marker("big-skill", trigger="T" * 1030000)
        reason = self.reason()
        self.assertLess(len(reason), 5000,
                        "1030000 characters of trigger reached the model unbounded")
        # Verbatim up to the cap: the evidence is ENDED, never paraphrased.
        self.assertIn("T" * 1200, reason)
        self.assertNotIn("T" * 1201, reason)
        # The cap is OBSERVED FIRING, and it fires out loud, with both counts. A quote a
        # reader cannot tell is partial is a quote they will over-read.
        self.assertIn("1200 of 1030000 characters shown", reason)
        self.assertIn("apply-pending", reason,
                      "the message must say where the whole trigger still is")

    def test_a_trigger_inside_the_cap_is_untouched(self):
        """The cap must be invisible to every real trigger. The three recorded in this
        machine's ledger measure 359, 359 and 518 characters."""
        trigger = "x" * 518
        self.marker("normal-skill", trigger=trigger)
        reason = self.reason()
        self.assertIn(trigger, reason)
        self.assertNotIn("cut here", reason)

    def test_moving_the_cap_moves_the_output(self):
        """A cap nobody can move is a cap nobody has watched fire. Two sessions, because
        the once-per-session-per-skill claim would otherwise silence the second half for
        the wrong reason and the test would pass whatever the cap did."""
        self.marker("skill-tight", session="sess-tight", trigger="T" * 5000)
        self.marker("skill-wide", session="sess-wide", trigger="T" * 5000)
        tight = self.reason(session="sess-tight", APPLY_GATE_MAX_TRIGGER=100)
        wide = self.reason(session="sess-wide", APPLY_GATE_MAX_TRIGGER=4000)
        self.assertIn("T" * 100, tight)
        self.assertNotIn("T" * 101, tight)
        self.assertIn("T" * 4000, wide)
        self.assertGreater(len(wide) - len(tight), 3800)

    def test_a_nonsense_or_absurd_cap_falls_back_to_the_default(self):
        """A knob set wrong must degrade to the default, never to silence and never to an
        arithmetic error on a hook's stderr once per turn. `99999999` is the one that
        matters: all digits, so a digits-only guard would pass it straight through and
        the cap would be gone again."""
        for i, bad in enumerate(("abc", "", "0", "-5", "99999999", "9" * 30)):
            with self.subTest(cap=bad):
                sess = "sess-bad-%d" % i
                self.marker("skill-bad-%d" % i, session=sess, trigger="T" * 3000)
                r = self.reason(session=sess, APPLY_GATE_MAX_TRIGGER=bad)
                self.assertIn("1200 of 3000 characters shown", r)

    def test_the_named_ceiling_closes_the_other_half_of_the_bound(self):
        """A per-skill cap that MAX_NAMED can multiply without limit is not a bound at
        all -- N unbounded quotes is the same defect wearing a different knob."""
        for i in range(8):
            self.marker("skill-%02d" % i, closed=1000 + i, trigger="T" * 1200)
        r = self.reason(APPLY_GATE_MAX_NAMED=999)
        named = [n for n in ("skill-%02d" % i for i in range(8)) if n in r]
        self.assertEqual(len(named), 4,
                         "an absurd MAX_NAMED must fall back to the default, not be honoured")

    def test_a_legal_raise_of_max_named_is_still_honoured(self):
        """The ceiling must not have eaten the knob."""
        for i in range(8):
            self.marker("skill-%02d" % i, closed=1000 + i, trigger="short")
        r = self.reason(APPLY_GATE_MAX_NAMED=6)
        named = [n for n in ("skill-%02d" % i for i in range(8)) if n in r]
        self.assertEqual(len(named), 6)

    def test_a_giant_skill_name_is_cut_and_the_cut_is_visible(self):
        """The name is printed inside a command the reader may run, so a name cut
        silently would be a command that silently does the wrong thing. 96 is
        bin/skillforge safe_name()'s own cut, so the marker FILENAME already holds no
        more than that."""
        self.marker("N" * 4000, trigger="short")
        r = self.reason()
        self.assertLess(len(r), 3000, "an unbounded name is the same defect as an "
                                      "unbounded trigger")
        self.assertIn("N" * 95 + "…", r)
        self.assertNotIn("N" * 96, r)

    def test_a_truncated_name_is_still_claimed_exactly_once(self):
        """The claim key is derived from the FULL name inside jq, not from the truncated
        one the message shows, so truncation must not cost the gate its idempotence."""
        self.marker("N" * 4000, trigger="short")
        self.assertIsNotNone(self.decision(self.stop(prompt="p1")))
        self.assertIsNone(self.decision(self.stop(prompt="p2")),
                          "a skill named once must not be named again")


# ============================================ the bound has to be in BYTES, not glyphs
class TriggerByteBoundTest(ApplyGateBase):
    """APPLY_GATE_MAX_TRIGGER counted CODEPOINTS; the exec it feeds counts BYTES.

    Both knobs have a documented legal ceiling -- MAX_TRIGGER 20000, MAX_NAMED 20 -- and at
    those two settings the codepoint cap bounded nothing that mattered: 20 skills x 20000
    codepoints of 3-byte text is 1200000 bytes of quote, and `jq -n --arg r "$reason"` is an
    exec whose argument vector is measured in bytes against ARG_MAX (1048576 here,
    `getconf ARG_MAX`). Measured before the fix, exactly this input: 0 bytes on stdout, rc 0,
    empty stderr, `sess-A.p1.turn` on disk -- the gate went silent at its own documented
    settings and said nothing anywhere about why. Independently, with the same shell:

        $ jq -n --arg r "$(cat 1210000-byte-file)" '{decision:"block",reason:$r}'
        argument list too long: jq        rc=127

    So the cut has to fire on codepoints OR bytes, whichever comes first. For ASCII the two
    coincide exactly, which is why nothing above this class changes.

    These tests exercise the CEILINGS, not a convenient small value, because the ceilings are
    the setting at which the old cap was already defeated.
    """

    CJK = "\u4e16"          # 3 bytes in UTF-8
    CEIL_TRIGGER = 20000    # APPLY_GATE_MAX_TRIGGER's documented ceiling
    CEIL_NAMED = 20         # APPLY_GATE_MAX_NAMED's documented ceiling

    def fill(self, n=None, trigger=None):
        """CEIL_NAMED markers, each carrying CEIL_TRIGGER codepoints of multibyte text."""
        trig = trigger if trigger is not None else self.CJK * self.CEIL_TRIGGER
        for i in range(n if n is not None else self.CEIL_NAMED):
            self.marker("skill-%02d" % i, closed=1000 + i, trigger=trig)
        return trig

    def at_ceilings(self, **kw):
        kw.setdefault("APPLY_GATE_MAX_TRIGGER", self.CEIL_TRIGGER)
        kw.setdefault("APPLY_GATE_MAX_NAMED", self.CEIL_NAMED)
        return self.stop(**kw)

    def test_the_block_still_emits_at_both_documented_ceilings_with_multibyte_text(self):
        trig = self.fill()
        raw = self.at_ceilings(prompt="p1")
        nbytes = len(raw.encode("utf-8"))
        print("\n  [byte bound] stdout at the ceilings: %d bytes "
              "(input was %d markers x %d bytes of trigger = %d bytes of quote)"
              % (nbytes, self.CEIL_NAMED, len(trig.encode("utf-8")),
                 self.CEIL_NAMED * len(trig.encode("utf-8"))))
        d = self.decision(raw)
        self.assertIsNotNone(
            d, "the gate emitted NOTHING at its own documented ceilings: the reason went "
               "over ARG_MAX and died into 2>/dev/null")
        self.assertEqual(d["decision"], "block")
        self.assertLess(nbytes, 600000,
                        "the emitted message is not bounded in bytes: %d bytes" % nbytes)

    def test_the_byte_bound_fires_and_announces_itself_in_bytes(self):
        self.fill()
        d = self.decision(self.at_ceilings(prompt="p1"))
        self.assertIsNotNone(d, "expected a block, got silence")
        reason = d["reason"]
        # 20000 bytes of a 3-byte glyph is 6666 whole glyphs (19998 bytes); 6667 would be
        # 20001. So the bound is OBSERVED at the exact glyph it has to cut at.
        self.assertIn(self.CJK * 6666, reason)
        self.assertNotIn(self.CJK * 6667, reason,
                         "a quote longer than the byte budget reached the model")
        # Announced, with the byte counts, for the same reason the codepoint cut is
        # announced: evidence a reader cannot tell is partial is evidence they over-read.
        self.assertIn("6666 of 20000 characters shown", reason)
        self.assertIn("19998 of 60000 bytes", reason)
        self.assertIn("apply-pending", reason)

    def test_every_quote_in_the_message_is_inside_the_byte_budget(self):
        self.fill()
        d = self.decision(self.at_ceilings(prompt="p1"))
        self.assertIsNotNone(d)
        runs = re.findall(self.CJK + "+", d["reason"])
        self.assertEqual(len(runs), self.CEIL_NAMED,
                         "expected one quote per named skill, got %d" % len(runs))
        worst = max(len(r.encode("utf-8")) for r in runs)
        print("  [byte bound] widest quote in the message: %d bytes "
              "(budget %d)" % (worst, self.CEIL_TRIGGER))
        self.assertLessEqual(worst, self.CEIL_TRIGGER,
                             "a %d-byte quote passed a %d-byte budget"
                             % (worst, self.CEIL_TRIGGER))

    def test_an_ascii_trigger_at_the_ceiling_is_unchanged_by_the_byte_bound(self):
        """The byte bound must be invisible where bytes and codepoints agree, or it is a
        second cap nobody asked for. 20000 ASCII characters is 20000 bytes: exactly the
        budget, so it must arrive whole."""
        self.marker("ascii-skill", trigger="T" * self.CEIL_TRIGGER)
        d = self.decision(self.at_ceilings(prompt="p1"))
        self.assertIsNotNone(d)
        self.assertIn("T" * self.CEIL_TRIGGER, d["reason"])
        self.assertNotIn("cut here", d["reason"])

    def test_the_widest_legal_input_of_all_still_emits(self):
        """The true worst case of the bound: 4-byte glyphs in the trigger AND in the name,
        at both ceilings. 20 x 20000 four-byte codepoints is 1600000 bytes of quote offered,
        which is over ARG_MAX (1048576 here) on the quote alone."""
        four = "\U0001D11E"        # 4 bytes in UTF-8
        for i in range(self.CEIL_NAMED):
            # The prefix keeps the marker FILENAMES distinct: sanitisation turns every
            # glyph into `_`, so names that differ only in glyphs are one file on disk.
            self.marker("skill-%02d" % i + four * 200, closed=1000 + i,
                        trigger=four * self.CEIL_TRIGGER)
        raw = self.at_ceilings(prompt="p1")
        nbytes = len(raw.encode("utf-8"))
        print("  [byte bound] widest legal input: %d bytes of quote offered, %d bytes "
              "emitted (ARG_MAX here: 1048576)"
              % (self.CEIL_NAMED * self.CEIL_TRIGGER * 4, nbytes))
        self.assertIsNotNone(self.decision(raw),
                             "the gate went silent on the widest input its own ENV block "
                             "calls legal")
        self.assertLess(nbytes, 600000, "%d bytes emitted" % nbytes)

    def test_the_claim_is_still_taken_only_after_a_real_emit_under_both_deliveries(self):
        """The ordering fixed last round, re-checked at the ceilings -- because that is the
        input on which the emit used to die while the claims said the skills had been
        named. Both deliveries of ONE event, then a later turn."""
        self.fill()
        first = self.decision(self.at_ceilings(prompt="dup"))
        self.assertIsNotNone(first, "the block never reached stdout at the ceilings")
        gate = self.state / "apply-gate"
        claimed = sorted(p.name.split(".named.")[1]
                         for p in gate.iterdir() if ".named." in p.name)
        self.assertEqual(claimed, sorted("skill-%02d" % i for i in range(self.CEIL_NAMED)),
                         "the claims and the message disagree")
        for name in claimed:
            self.assertIn(name, first["reason"])
        # Second delivery of the SAME event: silent.
        self.assertIsNone(self.decision(self.at_ceilings(prompt="dup")),
                          "the duplicate delivery interrupted the user a second time")
        # And a later turn: already said its piece, so it lets go.
        self.assertIsNone(self.decision(self.at_ceilings(prompt="p2")))


# =========================================== the per-argument cap Linux enforces
class LinuxArgvCapTest(ApplyGateBase):
    """The gate emitted NOTHING at its own documented ceilings on Linux, and a green macOS
    suite could not see it. This class makes the platform difference reproducible HERE.

    Linux enforces two separate exec limits. ARG_MAX bounds the whole vector (a quarter of
    the stack rlimit, typically 2 MB) and was never the binding one. MAX_ARG_STRLEN bounds
    ONE argument at a hard 131072 bytes -- 32 pages, `include/uapi/linux/binfmts.h`, not
    tunable, not raised by a larger ARG_MAX. macOS has no per-argument cap at all, only
    ARG_MAX 1048576 (`getconf ARG_MAX`).

    `jq -n --arg r "$reason"` put the whole block message into ONE argument. At the two
    documented ceilings (MAX_TRIGGER 20000, MAX_NAMED 20) that message is 409452 bytes:
    comfortably inside macOS's total, and 3.1x over Linux's per-argument cap. So
    TriggerByteBoundTest above passed here and failed on ubuntu, and the gate was silent
    on Linux at settings its own ENV block calls legal.

    THE SHIM IS A STAND-IN FOR THE KERNEL, NOT FOR ANY CODE IN THIS PACKAGE. It is a real
    executable named `jq`, first on PATH, that refuses any argv element over 131072 bytes
    and otherwise `exec`s the real jq -- which is precisely what execve(2) does on Linux.
    The hook is the real hook, the markers are real files, and the jq that answers is the
    real jq. `test_the_shim_itself_refuses_and_only_over_the_cap` proves the shim is live
    before anything is concluded from it; a fault injector that quietly does nothing is
    the dead guard this repo has a skill about.
    """

    MAX_ARG_STRLEN = 131072
    CJK = "\u4e16"
    CEIL_TRIGGER = 20000
    CEIL_NAMED = 20

    def setUp(self):
        super().setUp()
        real = shutil.which("jq", path=BASE_PATH)
        self.assertIsNotNone(real, "jq is not on the test PATH; this suite needs it")
        self.shimdir = self.state / "argv-cap-shim"
        self.shimdir.mkdir()
        shim = self.shimdir / "jq"
        shim.write_text(SHIM_JQ % {"real": real, "cap": self.MAX_ARG_STRLEN})
        shim.chmod(0o755)

    def shim_env(self, **extra):
        e = self.env(**extra)
        e["PATH"] = "%s:%s" % (self.shimdir, BASE_PATH)
        return e

    def shim_stop(self, session="sess-A", prompt="p1", now=4600, **envextra):
        payload = {"hook_event_name": "Stop", "session_id": session,
                   "prompt_id": prompt, "stop_hook_active": False}
        envextra.setdefault("APPLY_GATE_MAX_TRIGGER", self.CEIL_TRIGGER)
        envextra.setdefault("APPLY_GATE_MAX_NAMED", self.CEIL_NAMED)
        r = subprocess.run([str(HOOK)], input=json.dumps(payload), capture_output=True,
                           text=True, env=self.shim_env(APPLY_GATE_NOW=now, **envextra))
        self.assertEqual(r.returncode, 0, "the hook exited %d: %r" % (r.returncode, r.stderr))
        self.assertEqual(r.stderr, "", "the hook wrote to stderr: %r" % r.stderr)
        return r.stdout

    def fill(self):
        trig = self.CJK * self.CEIL_TRIGGER
        for i in range(self.CEIL_NAMED):
            self.marker("skill-%02d" % i, closed=1000 + i, trigger=trig)

    def test_the_shim_itself_refuses_and_only_over_the_cap(self):
        """The injector must be observed working, in both directions, or every other
        assertion in this class is vacuous."""
        env = self.shim_env()
        over = subprocess.run(["jq", "-n", "--arg", "r", "R" * (self.MAX_ARG_STRLEN + 1),
                               "$r|length"], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, env=env)
        self.assertNotEqual(over.returncode, 0,
                            "the shim let a %d-byte argument through; Linux would not"
                            % (self.MAX_ARG_STRLEN + 1))
        self.assertEqual(over.stdout, "", "a refused exec must produce no answer")
        under = subprocess.run(["jq", "-n", "--arg", "r", "R" * (self.MAX_ARG_STRLEN - 1),
                                "$r|length"], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, env=env)
        self.assertEqual(under.returncode, 0,
                         "the shim refused a LEGAL argument: %r" % under.stderr)
        self.assertEqual(under.stdout.strip(), str(self.MAX_ARG_STRLEN - 1))

    def test_the_gate_still_emits_at_the_ceilings_under_the_linux_argv_cap(self):
        """The ubuntu failure, reproduced and then closed. Before the streaming fix this
        produced nothing at all."""
        self.fill()
        raw = self.shim_stop()
        d = self.decision(raw)
        self.assertIsNotNone(
            d, "the gate emitted NOTHING with Linux's per-argument cap simulated: the "
               "reason is still travelling in argv")
        self.assertEqual(d["decision"], "block")
        for i in range(self.CEIL_NAMED):
            self.assertIn("skill-%02d" % i, d["reason"])

    def test_the_message_really_is_bigger_than_one_linux_argument(self):
        """Otherwise the test above would pass with the old spelling too. The message has
        to be over the cap for the cap to have been what silenced it."""
        self.fill()
        d = self.decision(self.shim_stop())
        self.assertIsNotNone(d)
        n = len(d["reason"].encode("utf-8"))
        print("\n  [linux argv cap] reason: %d bytes (MAX_ARG_STRLEN %d, ratio %.1fx)"
              % (n, self.MAX_ARG_STRLEN, n / float(self.MAX_ARG_STRLEN)))
        self.assertGreater(n, self.MAX_ARG_STRLEN,
                           "%d bytes would have fitted in one Linux argument, so this "
                           "class proves nothing" % n)

    def test_the_default_settings_were_never_over_the_cap(self):
        """Which is why this went unseen for as long as it did: nobody's real trigger
        comes near it. The three recorded on this machine are 359, 359 and 518
        codepoints."""
        self.marker("ordinary", trigger="a dead end that cost an afternoon " * 15)
        d = self.decision(self.shim_stop(APPLY_GATE_MAX_TRIGGER=1200,
                                         APPLY_GATE_MAX_NAMED=4))
        self.assertIsNotNone(d)
        self.assertLess(len(d["reason"].encode("utf-8")), self.MAX_ARG_STRLEN)

    def test_the_claims_still_match_the_message_under_the_cap(self):
        """A block that reaches stdout must claim exactly the skills it named, whatever
        the exec limits are."""
        self.fill()
        d = self.decision(self.shim_stop())
        self.assertIsNotNone(d)
        gate = self.state / "apply-gate"
        claimed = sorted(p.name.split(".named.")[1]
                         for p in gate.iterdir() if ".named." in p.name)
        self.assertEqual(claimed, sorted("skill-%02d" % i for i in range(self.CEIL_NAMED)))
        for name in claimed:
            self.assertIn(name, d["reason"])


# ================================================== the claim outlives a failed emit
class EmitFailureTest(ApplyGateBase):
    """The claim was burnt BEFORE the message was emitted, so an emit failure silenced
    the skill for the rest of the session and the user never saw the flag.

    Reproduced before that fix: a marker with a 2 MB trigger, one Stop payload -> stdout 0
    bytes, rc 0, and both `sess-A.named.big-skill` and `sess-A.p1.turn` already on disk.
    The reason was handed to `jq -n --arg r`, the exec died, `2>/dev/null` and `|| exit 0`
    swallowed it -- while the claim said the skill had been named. That violates the
    file's own rule: "a skill silenced for this session but never shown to the user is a
    flag that disappeared without being read."

    THE INJECTOR CHANGED WHEN THE EMIT DID, AND THE REASON IT CHANGED IS THE FIX ITSELF.
    This test used to reach a failed emit by padding the ENVIRONMENT until the exec of
    `jq -n --arg r "$reason"` went over ARG_MAX. The reason no longer travels in argv at
    all -- the hook writes it to a file and jq reads it back with `--rawfile` -- so the
    emit's argument vector is a few hundred bytes, SMALLER than the ~4 KB jq program the
    hook already exec'd once per marker to get here. No environment size can therefore
    fail the emit without failing the candidate read first, and a hook that never reaches
    the emit proves nothing about what it claims afterwards. Keeping the old padding would
    have been asserting on a failure mode the fix removed.

    So the failure is injected where the message is now built: `ulimit -f 1` on the hook
    itself, a file-size rlimit of one 512-byte block. Nothing is mocked -- the kernel
    refuses the write exactly as a full filesystem would. 512 is above everything the hook
    writes before the reason (`cand.txt` is ~180 bytes for these four short markers) and
    far below the reason itself (~1.9 KB), so the first write it stops is the one under
    test. `_rlimit_bites` proves the limit is really enforced before anything is concluded
    from the silence.
    """

    FSIZE_BLOCKS = 1        # `ulimit -f` counts 512-byte blocks, on both platforms

    def under_fsize_limit(self, argv, **kw):
        """Run argv with RLIMIT_FSIZE set, via a shell that `exec`s into it -- so the
        process under test IS the hook and the captured stderr is the hook's own."""
        return subprocess.run(
            ["/bin/sh", "-c", 'ulimit -f %d; exec "$0" "$@"' % self.FSIZE_BLOCKS] + argv,
            capture_output=True, text=True, **kw)

    def _rlimit_bites(self):
        probe = self.state / "rlimit-probe"
        r = self.under_fsize_limit(["/bin/sh", "-c", 'printf "%2000s" "" > "$0"',
                                    str(probe)], stdin=subprocess.DEVNULL,
                                   env={"PATH": BASE_PATH})
        wrote = probe.stat().st_size if probe.exists() else 0
        if r.returncode == 0 and wrote >= 2000:
            self.skipTest("RLIMIT_FSIZE is not enforced here: a 2000-byte write succeeded "
                          "under `ulimit -f %d`" % self.FSIZE_BLOCKS)

    def test_a_block_that_could_not_be_emitted_does_not_burn_the_claim(self):
        self._rlimit_bites()
        for i in range(4):
            self.marker("skill-%d" % i, closed=1000 + i)
        payload = {"hook_event_name": "Stop", "session_id": "sess-A",
                   "prompt_id": "p1", "stop_hook_active": False}
        r = self.under_fsize_limit([str(HOOK)], input=json.dumps(payload),
                                   env=self.env(APPLY_GATE_NOW=4600))
        # A hook may never break a turn, and may never speak on stderr, whatever fails.
        # The stderr assertion is not incidental here: `printf` is a builtin, so a single
        # subshell would have let bash report "Filesize limit exceeded" from the MAIN
        # shell. This is the test that holds the second subshell in place.
        self.assertEqual(r.returncode, 0, "the hook exited %d: %r" % (r.returncode, r.stderr))
        self.assertEqual(r.stderr, "", "the hook wrote to stderr: %r" % r.stderr)
        self.assertEqual(r.stdout, "", "the emit was expected to fail under the rlimit")

        gate = self.state / "apply-gate"
        # THE HOOK REALLY DID REACH THE EMIT. The per-turn claim is taken after the
        # candidates are read and before the body is built, so its presence proves the
        # candidate stage worked and the write that died was the message itself -- without
        # it this test would also pass if the hook had exited early for some unrelated
        # reason.
        self.assertTrue((gate / "sess-A.p1.turn").exists(),
                        "the hook never got as far as the emit; this test proved nothing")
        burnt = sorted(p.name for p in gate.iterdir() if ".named." in p.name)
        self.assertEqual(burnt, [], "claims were burnt for a block nobody ever saw: %s"
                                    % burnt)

        # And the flag is still standing next turn, in an ordinary environment. This is
        # also the control: same markers, same hook, no rlimit -> a block.
        d = self.decision(self.stop(prompt="p2"))
        self.assertIsNotNone(d, "the skill was silenced for the rest of the session by a "
                                "block the user never saw")
        for i in range(4):
            self.assertIn("skill-%d" % i, d["reason"])

    def test_a_block_that_was_emitted_does_claim_every_skill_it_named(self):
        """The other direction, so the fix cannot be "never claim at all". The claims and
        the message must agree exactly."""
        for i in range(3):
            self.marker("skill-%d" % i, closed=1000 + i)
        d = self.decision(self.stop(prompt="p1"))
        self.assertIsNotNone(d)
        gate = self.state / "apply-gate"
        claimed = sorted(p.name.split(".named.")[1]
                         for p in gate.iterdir() if ".named." in p.name)
        self.assertEqual(claimed, ["skill-0", "skill-1", "skill-2"])
        for name in claimed:
            self.assertIn(name, d["reason"])
        self.assertIsNone(self.decision(self.stop(prompt="p2")))


# ====================================== what a green suite must not be able to hide
class MarkerSessionIdentityTest(ApplyGateBase):
    """Every other test in this file writes the marker's `session` ITSELF and then picks
    the same string for the payload's `.session_id`, so the two sides agree by
    construction. If the writer ever recorded a different identifier from the one the
    payload carries, this gate would go permanently silent -- and every test above would
    still be green, because none of them ever asks a real writer what it writes.

    So this one drives the real bin/skillforge for the WRITE and the payload for the READ.
    It pins the writer's choice of identifier to the reader's.

    IT DOES NOT SETTLE THE PLATFORM QUESTION, and must not be read as if it did.
    bin/skillforge records `$CLAUDE_CODE_SESSION_ID`; the hook compares against the hook
    payload's `.session_id`. docs/DESIGN.md states those are DIFFERENT values for the same
    session; a cold reviewer measured them EQUAL on cli 2.1.246. That disagreement is
    unresolved and is reported as unresolved. What this test buys is that a divergence
    introduced in THIS repository fails loudly instead of silently.
    """

    def test_the_marker_the_real_cli_writes_carries_the_id_the_gate_compares(self):
        sid = "live-session-id-0001"
        cli = REPO / "bin" / "skillforge"
        env = self.env(CLAUDE_CODE_SESSION_ID=sid)
        for args in (["start", "real-skill", "3", "a summary",
                      "--trigger", "the dead end that set this off",
                      "--trigger-kind", "user-prompt"],
                     ["done", "--name", "real-skill", "closed"]):
            subprocess.run([str(cli)] + args, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, env=env)
        marker = self.pending / "real-skill.json"
        self.assertTrue(marker.exists(), "the CLI wrote no apply-pending marker")
        rec = json.loads(marker.read_text())
        self.assertEqual(rec["session"], sid,
                         "bin/skillforge no longer records the identifier this gate "
                         "compares against; the gate is now permanently silent")
        d = self.decision(self.stop(session=sid, now=rec["closed"] + 10))
        self.assertIsNotNone(d, "the gate did not recognise a marker the real CLI wrote "
                                "for the session it was handed")
        self.assertIn("real-skill", d["reason"])

    def test_a_marker_whose_session_diverges_by_one_character_is_silently_skipped(self):
        """The failure mode itself, written down so nobody has to rediscover its shape:
        one character of difference and the gate says nothing at all, with no error
        anywhere. The status line is the only surface left, which is why the ⚑ segment
        deliberately has no session rule."""
        self.marker("drifted-skill", session="sess-A-x")
        self.assertIsNone(self.decision(self.stop(session="sess-A")))
        self.assertIn("drifted-skill", ANSI.sub("", self.render()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
