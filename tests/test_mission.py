#!/usr/bin/env python3
"""Tests for hooks/mission.sh -- the hook that states the user's own requests back.

NO MOCKS, per this repo's standing rule. Every test writes a real `prompts.jsonl` in
history-surfer's real row shape, runs the real shell script through subprocess with a
minimal PATH, a HOME inside a temp directory, and SKILL_COMPOUNDER_STATE and
MISSION_SURFER_ROOT pinned there, feeds it a real payload on stdin, and reads the emit and
the state directory back off disk.

THE ROW SHAPE IS COPIED FROM THE LIVE STORE, not invented. One line of
~/.claude/history-surfer/projects/-Users-jmanning-claude-skill-compounder/prompts.jsonl
was read on 2026-09-03 (read only -- that file is never written by this suite) and its
keys are the keys below:

    {"ts":"2026-08-25T02:43:51Z","session_id":"32c3cd9e-...","cwd":"/Users/jmanning/...",
     "project_slug":"-Users-jmanning-...","seq":4,"prompt":"actually: i'd like to ...",
     "is_command":false,"text_final":true,"source":"transcript"}

AND THE HAND-WRITTEN SHAPE IS NOT TRUSTED ON ITS OWN. `RealWriterTest` drives
history-surfer's OWN UserPromptSubmit hook script -- the real `hooks/log_prompt.py` out of
the real checkout, found by resolving `surfer` on PATH -- to write the row, and then reads
it back through mission.sh. A writer and a reader that share a format must be driven into
each other; a hand-written fixture pins whichever side its author was looking at and lets
the other drift (the 2026-09-02 note in .claude/CLAUDE.md, which cost two dead readers).
It skips cleanly when history-surfer is not installed.

EVERY subprocess call against the hook passes `input=`. The script reads its payload with
`payload="$(cat)"`; without stdin it hangs forever.

The clock is pinned with MISSION_NOW -- the hook's own. Pinning another script's clock does
nothing to this one.
"""

import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "mission.sh")

# Minimal, explicit environment: the scripts must not depend on the ambient one.
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"

PROJECT = "/tmp/mission-project (a)"      # the parens and the space are the point: the
                                          # slug must survive characters a naive shell
                                          # expression would eat.
TIMEOUT = 180

# The cost bound this hook is held to, in milliseconds per event. It runs before every
# tool call, so a slow one is paid on every tool call.
COST_BUDGET_MS = 150.0


def slugify_cwd(cwd):
    """history-surfer's slug, in Python: history_surfer/store.py:slugify_cwd.

    Every non-alphanumeric becomes `-`, runs are NOT collapsed, empty becomes "unknown".
    Reproduced here so the test computes the directory name independently of the shell
    expression under test; if the two ever disagree, the hook reads an empty directory.
    """
    s = re.sub(r"[^a-zA-Z0-9]", "-", cwd or "")
    return s or "unknown"


LONG = ("please build the mission hook so that it reads history-surfer's own store and "
        "states the user's requests back verbatim at each of the five moments")
LONG2 = ("now add the tests that cover every moment, the budget and its elision marker, "
         "the short-prompt proxy and the stop arm blocking exactly once")
LONG3 = ("also make sure the stop arm never blocks twice for one prompt id and that "
         "stop_hook_active is honoured on the second delivery")


class MissionCase(unittest.TestCase):
    """Shared plumbing: a real store on disk, a real hook, a pinned clock."""

    def setUp(self):
        self.tmp = os.path.join(
            os.environ.get("TMPDIR", "/tmp"),
            "mission-%d-%d" % (os.getpid(), int(time.time() * 1e6) % 10 ** 9))
        os.makedirs(self.tmp)
        self.home = os.path.join(self.tmp, "home")
        self.state = os.path.join(self.tmp, "state")
        self.surfer = os.path.join(self.tmp, "surfer")
        for d in (self.home, self.state, self.surfer):
            os.makedirs(d)
        self.slug = slugify_cwd(PROJECT)
        self.projdir = os.path.join(self.surfer, "projects", self.slug)
        os.makedirs(self.projdir)
        self.clock = 1_756_900_000        # 2025-09-03T11:46:40Z
        self._seq = 0

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------- the store
    @property
    def store(self):
        return os.path.join(self.projdir, "prompts.jsonl")

    @property
    def overlay(self):
        return os.path.join(self.projdir, "overlay.jsonl")

    @property
    def hits(self):
        return os.path.join(self.state, "mission", "hits.jsonl")

    def row(self, prompt, session="S1", seq=None, is_command=False, text_final=True,
            ts=None, **over):
        """A row in exactly the shape the live store holds."""
        if seq is None:
            self._seq += 1
            seq = self._seq
        r = {"ts": ts or ("2026-09-03T%02d:00:00Z" % min(seq, 23)),
             "session_id": session, "cwd": PROJECT, "project_slug": self.slug,
             "seq": seq, "prompt": prompt, "is_command": is_command,
             "text_final": text_final, "source": "transcript"}
        r.update(over)
        return r

    def write_rows(self, *rows, **kw):
        path = kw.get("path", self.store)
        with open(path, "a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def default_store(self, session="S1"):
        """A five-prompt session: one long, one command, one short, two long."""
        self.write_rows(
            self.row(LONG, session=session),
            self.row("/clear", session=session, is_command=True),
            self.row("yes go ahead", session=session),
            self.row(LONG2, session=session),
            self.row(LONG3, session=session),
        )

    # ------------------------------------------------------------------- payloads
    def session_start(self, source="compact", session="S1", pid="pc1", **over):
        p = {"hook_event_name": "SessionStart", "session_id": session, "cwd": PROJECT,
             "source": source}
        if pid is not None:
            p["prompt_id"] = pid
        p.update(over)
        return p

    def pretooluse(self, tool="Read", session="S1", tuid="toolu_1", pid="p1", **over):
        p = {"hook_event_name": "PreToolUse", "session_id": session, "cwd": PROJECT,
             "prompt_id": pid, "tool_use_id": tuid, "tool_name": tool,
             "permission_mode": "default", "tool_input": {"file_path": "/tmp/x"}}
        p.update(over)
        return p

    def subagent_start(self, session="S1", aid="ag1", pid="p1", **over):
        p = {"hook_event_name": "SubagentStart", "session_id": session, "cwd": PROJECT,
             "prompt_id": pid, "agent_id": aid, "agent_type": "general-purpose"}
        p.update(over)
        return p

    def user_prompt(self, text, session="S1", pid="p2", **over):
        p = {"hook_event_name": "UserPromptSubmit", "session_id": session, "cwd": PROJECT,
             "prompt_id": pid, "prompt": text}
        p.update(over)
        return p

    def stop(self, message="Done -- the feature is implemented.", session="S1", pid="p1",
             active=False, **over):
        p = {"hook_event_name": "Stop", "session_id": session, "cwd": PROJECT,
             "prompt_id": pid, "stop_hook_active": active,
             "last_assistant_message": message}
        p.update(over)
        return p

    # ------------------------------------------------------------------- running
    def env(self, **extra):
        e = {"PATH": BASE_PATH, "HOME": self.home,
             "SKILL_COMPOUNDER_STATE": self.state,
             "MISSION_SURFER_ROOT": self.surfer,
             "MISSION_NOW": str(self.clock)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def run_hook(self, payload, **env_extra):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(["bash", HOOK], input=body, capture_output=True,
                              text=True, env=self.env(**env_extra), timeout=TIMEOUT)

    def bump_tools(self, n, pid="p1", session="S1", **env_extra):
        """Drive n real PreToolUse events so the turn's tool counter is real.

        Not a hand-written counter file: the Stop arm reads what the PreToolUse arm wrote,
        and a fixture would pin only one of the two.
        """
        for i in range(n):
            # The id carries the prompt id because a real tool_use_id is unique per call,
            # and the count claim is keyed on it: reusing one across two turns would make
            # the second turn's calls look like the first turn's duplicates.
            self.run_hook(self.pretooluse(tuid="toolu_%s_%d" % (pid, i), pid=pid,
                                          session=session), **env_extra)

    # ------------------------------------------------------------------- assertions
    def assert_silent(self, r):
        self.assertEqual(r.returncode, 0, "a hook must never exit non-zero: " + r.stderr)
        self.assertEqual(r.stdout.strip(), "",
                         "the hook spoke when it should have been silent: %r" % r.stdout)
        return r

    def context_of(self, r, event):
        self.assertEqual(r.returncode, 0, "a hook must never exit non-zero: " + r.stderr)
        self.assertTrue(r.stdout.strip(), "expected the mission, got silence")
        d = json.loads(r.stdout)
        hso = d["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], event)
        # The MEASURED field. `permissionDecision:"allow"` with a reason reaches nothing
        # (0 of 6 runs), so its presence here would mean the hook had silently stopped
        # saying anything to anyone.
        self.assertNotIn("permissionDecision", hso)
        if event in ("PreToolUse", "UserPromptSubmit"):
            self.assertIs(d["suppressOutput"], True)
        else:
            self.assertNotIn("suppressOutput", d)
        return hso["additionalContext"]

    def block_of(self, r):
        self.assertEqual(r.returncode, 0, "a hook must never exit non-zero: " + r.stderr)
        self.assertTrue(r.stdout.strip(), "expected a block, got silence")
        d = json.loads(r.stdout)
        self.assertEqual(d["decision"], "block")
        return d["reason"]

    def hit_rows(self):
        if not os.path.exists(self.hits):
            return []
        with open(self.hits, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]


# ==================================================================== the store contract
class StoreTest(MissionCase):
    """What is read, and what is not."""

    def test_a_missing_history_surfer_store_is_silent_on_every_event(self):
        """Principle i: no second copy. Without history-surfer the hook is inert.

        `skillforge doctor` is the surface that reports the missing dependency; a hook
        that fell back to its own capture would be the second copy the design forbids.
        """
        for payload in (self.session_start(), self.pretooluse(tool="Agent"),
                        self.subagent_start(), self.user_prompt("ok"), self.stop()):
            self.assert_silent(self.run_hook(payload))
        self.assertFalse(os.path.exists(self.hits))

    def test_an_empty_store_file_is_silent(self):
        open(self.store, "w").close()
        self.assert_silent(self.run_hook(self.session_start()))

    def test_a_store_for_another_project_is_not_read(self):
        """The slug is the whole address. Another project's prompts are not this mission."""
        other = os.path.join(self.surfer, "projects", slugify_cwd("/tmp/somewhere-else"))
        os.makedirs(other)
        self.write_rows(self.row(LONG), path=os.path.join(other, "prompts.jsonl"))
        self.assert_silent(self.run_hook(self.session_start()))

    def test_the_slug_reproduces_history_surfers_scheme_including_runs_and_punctuation(self):
        """`/tmp/mission-project (a)` -> `-tmp-mission-project--a-`; runs are NOT collapsed."""
        self.assertEqual(self.slug, "-tmp-mission-project--a-")
        self.default_store()
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn(LONG, ctx)

    def test_only_this_sessions_rows_are_read(self):
        self.write_rows(self.row("an entirely different question from another session",
                                 session="S2", seq=1))
        self.write_rows(self.row(LONG, session="S1", seq=1))
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn(LONG, ctx)
        self.assertNotIn("another session", ctx)

    def test_command_rows_and_empty_prompts_are_dropped(self):
        self.write_rows(
            self.row("/compact", is_command=True),
            self.row(""),
            self.row(LONG),
        )
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertNotIn("/compact", ctx)
        self.assertIn("1 recorded", ctx)

    def test_a_repeated_seq_prefers_the_text_final_row_then_the_later_ts(self):
        """history-surfer appends; store.py:_prefer decides. So does this hook."""
        self.write_rows(
            self.row("the first, non final capture of this request", seq=1,
                     text_final=False, ts="2026-09-03T01:00:00Z"),
            self.row(LONG, seq=1, text_final=True, ts="2026-09-03T01:00:01Z"),
        )
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn(LONG, ctx)
        self.assertNotIn("non final capture", ctx)
        self.assertIn("1 recorded", ctx)

    def test_an_overlay_delete_is_honoured_and_a_restore_undoes_it(self):
        self.write_rows(self.row(LONG, seq=1), self.row(LONG2, seq=2))
        self.write_rows({"ts": "2026-09-03T05:00:00Z", "session_id": "S1", "seq": 2,
                         "op": "delete", "value": True}, path=self.overlay)
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn(LONG, ctx)
        self.assertNotIn(LONG2, ctx)

        shutil.rmtree(os.path.join(self.state, "mission"), ignore_errors=True)
        self.write_rows({"ts": "2026-09-03T06:00:00Z", "session_id": "S1", "seq": 2,
                         "op": "restore", "value": True}, path=self.overlay)
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn(LONG2, ctx)

    def test_an_overlay_edit_replaces_the_text(self):
        self.write_rows(self.row(LONG, seq=1))
        self.write_rows({"ts": "2026-09-03T05:00:00Z", "session_id": "S1", "seq": 1,
                         "op": "edit", "value": "the corrected wording of the request"},
                        path=self.overlay)
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn("the corrected wording", ctx)
        self.assertNotIn(LONG, ctx)

    def test_a_malformed_line_does_not_take_the_whole_store_with_it(self):
        with open(self.store, "a", encoding="utf-8") as fh:
            fh.write('{"session_id":"S1","seq":1,"prompt":"half a lin\n')
        self.write_rows(self.row(LONG, seq=2))
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn(LONG, ctx)


# ==================================================================== moment 1: SessionStart
class SessionStartTest(MissionCase):
    """After a compaction, and on a resume; never at startup."""

    def setUp(self):
        super().setUp()
        self.default_store()

    def test_compact_delivers_the_mission(self):
        ctx = self.context_of(self.run_hook(self.session_start("compact")), "SessionStart")
        self.assertTrue(ctx.startswith("The user's requests in this session, verbatim"))
        self.assertIn(LONG, ctx)

    def test_resume_delivers_the_mission_even_with_no_id_in_the_payload(self):
        """A resume payload carries neither prompt_id nor tool_use_id (measured, 2.1.259).

        The claim key falls back to a digest of the payload, so the event is still claimed
        exactly once across the two wirings.
        """
        p = self.session_start("resume", pid=None)
        p["seconds_since_last_response"] = 55
        p["context_tokens"] = 30339
        ctx = self.context_of(self.run_hook(p), "SessionStart")
        self.assertIn(LONG, ctx)
        self.assert_silent(self.run_hook(p))

    def test_startup_emits_nothing(self):
        """At startup nothing has been asked yet in this session."""
        self.assert_silent(self.run_hook(self.session_start("startup")))
        self.assertEqual(self.hit_rows(), [])

    def test_the_text_is_a_statement_and_carries_no_imperative_opener(self):
        """Imperative wording in injected context was refused as prompt injection.

        2 of 4 measured runs; the frame is not decoration. This asserts the shape of the
        frame, which is what the measurement was about.
        """
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        first = ctx.split("\n", 1)[0]
        self.assertTrue(first.startswith("The user's requests in this session"))
        for opener in ("Remember to", "You must", "Make sure you", "Do not forget"):
            self.assertNotIn(opener, ctx)


# ==================================================================== moment 2: dispatch
class DispatchTest(MissionCase):
    """Before an expensive task: Agent, Task, Workflow."""

    def setUp(self):
        super().setUp()
        self.default_store()

    def test_each_dispatch_tool_delivers_the_mission_to_the_parent(self):
        for i, tool in enumerate(("Agent", "Task", "Workflow")):
            r = self.run_hook(self.pretooluse(tool=tool, tuid="toolu_d%d" % i))
            ctx = self.context_of(r, "PreToolUse")
            self.assertIn(LONG, ctx)

    def test_an_ordinary_tool_does_not_take_the_dispatch_arm(self):
        self.assert_silent(self.run_hook(self.pretooluse(tool="Read")))

    def test_a_dispatch_from_inside_a_subagent_still_fires(self):
        """A sub-dispatch is an expensive task wherever it is made."""
        r = self.run_hook(self.pretooluse(tool="Agent", agent_id="ag9"))
        self.assertIn(LONG, self.context_of(r, "PreToolUse"))
        self.assertEqual(self.hit_rows()[-1]["agent_id"], "ag9")


# ==================================================================== moment 3: subagent
class SubagentTest(MissionCase):

    def setUp(self):
        super().setUp()
        self.default_store()

    def test_a_subagent_gets_the_mission_and_the_closing_sentence(self):
        ctx = self.context_of(self.run_hook(self.subagent_start()), "SubagentStart")
        self.assertIn(LONG, ctx)
        self.assertIn("The parent's instructions to this agent appear above", ctx)

    def test_the_closing_sentence_is_on_no_other_arm(self):
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertNotIn("The parent's instructions", ctx)

    def test_the_hits_row_names_the_agent(self):
        self.run_hook(self.subagent_start(aid="ag-42"))
        row = self.hit_rows()[-1]
        self.assertEqual(row["moment"], "subagent")
        self.assertEqual(row["agent_id"], "ag-42")


# ==================================================================== moment 4: periodic
class PeriodicTest(MissionCase):

    def setUp(self):
        super().setUp()
        self.default_store()

    def test_the_first_tool_call_seeds_the_interval_and_says_nothing(self):
        """The interval's clock starts at the first event, not at zero.

        Otherwise the mission is restated one tool call after the prompt that set it.
        """
        self.assert_silent(self.run_hook(self.pretooluse(tuid="t1")))
        self.assertTrue(os.path.exists(
            os.path.join(self.state, "mission", "S1", "last")))

    def test_inside_the_interval_it_stays_silent(self):
        self.run_hook(self.pretooluse(tuid="t1"))
        self.assert_silent(self.run_hook(
            self.pretooluse(tuid="t2"), MISSION_NOW=self.clock + 600))

    def test_past_the_interval_it_delivers_again(self):
        self.run_hook(self.pretooluse(tuid="t1"))
        r = self.run_hook(self.pretooluse(tuid="t2"), MISSION_NOW=self.clock + 1201)
        self.assertIn(LONG, self.context_of(r, "PreToolUse"))
        self.assertEqual(self.hit_rows()[-1]["moment"], "periodic")

    def test_a_delivery_of_any_kind_re_arms_the_interval(self):
        """`last` means the last delivery, whichever moment made it."""
        self.run_hook(self.session_start())
        self.assert_silent(self.run_hook(
            self.pretooluse(tuid="t2"), MISSION_NOW=self.clock + 600))

    def test_the_periodic_arm_never_fires_inside_a_subagent(self):
        """A subagent got the whole mission at SubagentStart; a second copy is noise."""
        self.run_hook(self.pretooluse(tuid="t1", agent_id="ag1"))
        self.assert_silent(self.run_hook(
            self.pretooluse(tuid="t2", agent_id="ag1"), MISSION_NOW=self.clock + 99999))

    def test_a_backwards_clock_cannot_silence_the_arm_forever(self):
        """Compared on |now - last|, like every other cooldown in this package."""
        self.run_hook(self.pretooluse(tuid="t1"))
        r = self.run_hook(self.pretooluse(tuid="t2"), MISSION_NOW=self.clock - 5000)
        self.assertIn(LONG, self.context_of(r, "PreToolUse"))


# ==================================================================== moment 5: ambiguity
class AmbiguityTest(MissionCase):
    """A short prompt is the prompt that relies on memory."""

    def setUp(self):
        super().setUp()
        self.default_store()

    def test_a_short_prompt_gets_the_last_substantive_request(self):
        ctx = self.context_of(self.run_hook(self.user_prompt("continue")),
                              "UserPromptSubmit")
        self.assertTrue(ctx.startswith("The user's last substantive request"))
        self.assertIn(LONG3, ctx)

    def test_a_long_prompt_emits_nothing(self):
        self.assert_silent(self.run_hook(self.user_prompt(LONG2)))

    def test_the_boundary_is_MISSION_SHORT_WORDS_words(self):
        self.assert_silent(self.run_hook(self.user_prompt("one two three four five six")))
        r = self.run_hook(self.user_prompt("one two three four five"), pid="p9")
        self.assertTrue(r.stdout.strip())

    def test_a_prompt_of_globbing_characters_is_counted_as_words_not_filenames(self):
        """`set -f` before the word split, or `*` would be counted as a directory listing."""
        self.assertTrue(self.run_hook(self.user_prompt("* * ?")).stdout.strip())

    def test_the_current_prompt_is_never_restated_back_to_itself(self):
        """history-surfer's hook may have written this prompt already; ordering is undefined.

        Excluding it by text covers both orders, which is what "never twice" means.
        """
        self.write_rows(self.row("carry on"))
        ctx = self.context_of(self.run_hook(self.user_prompt("carry on")),
                              "UserPromptSubmit")
        self.assertNotIn("carry on", ctx)
        self.assertIn(LONG3, ctx)

    def test_it_falls_back_to_the_last_request_when_none_is_substantive(self):
        os.remove(self.store)
        self.write_rows(self.row("do it"), self.row("keep going"))
        ctx = self.context_of(self.run_hook(self.user_prompt("ok")), "UserPromptSubmit")
        self.assertIn("keep going", ctx)

    def test_a_session_whose_only_prompt_is_the_current_one_is_silent(self):
        os.remove(self.store)
        self.write_rows(self.row("go on"))
        self.assert_silent(self.run_hook(self.user_prompt("go on")))


# ==================================================================== moment 6: Stop
class StopTest(MissionCase):

    def setUp(self):
        super().setUp()
        self.default_store()

    def test_a_completion_claim_after_enough_tool_calls_blocks_once(self):
        self.bump_tools(8)
        reason = self.block_of(self.run_hook(self.stop()))
        self.assertIn(LONG, reason)
        self.assertIn("the one the user will read against those requests", reason)

    def test_a_second_stop_for_the_same_prompt_id_is_silent(self):
        self.bump_tools(8)
        self.block_of(self.run_hook(self.stop()))
        self.assert_silent(self.run_hook(self.stop()))
        self.assert_silent(self.run_hook(self.stop(message="All tests pass.")))

    def test_a_new_prompt_id_may_block_again(self):
        self.bump_tools(8, pid="p1")
        self.block_of(self.run_hook(self.stop(pid="p1")))
        self.bump_tools(8, pid="p2")
        self.block_of(self.run_hook(self.stop(pid="p2")))

    def test_stop_hook_active_is_honoured(self):
        """The platform's own loop flag. Without it a gate loops the session."""
        self.bump_tools(8)
        self.assert_silent(self.run_hook(self.stop(active=True)))
        self.assertEqual(self.hit_rows(), [])

    def test_below_the_tool_floor_it_does_not_block(self):
        self.bump_tools(7)
        self.assert_silent(self.run_hook(self.stop()))

    def test_the_tool_count_is_per_prompt_id(self):
        self.bump_tools(8, pid="p1")
        self.assert_silent(self.run_hook(self.stop(pid="p2")))

    def test_a_message_that_is_not_a_completion_claim_does_not_block(self):
        self.bump_tools(8)
        self.assert_silent(self.run_hook(
            self.stop(message="Here is what I found in the file; what would you like next?")))

    def test_each_word_of_the_stop_regex_fires(self):
        """The regex is short on purpose; every branch of it is exercised here."""
        phrases = ["Done.", "This is complete.", "I completed the refactor.",
                   "Finished the sweep.", "Implemented the arm.", "The change landed.",
                   "All tests pass.", "All tests passed locally.",
                   "All tests passing now.", "Ready to merge."]
        for i, phrase in enumerate(phrases):
            pid = "pr%d" % i
            self.bump_tools(8, pid=pid)
            self.assertTrue(self.run_hook(self.stop(message=phrase, pid=pid)).stdout.strip(),
                            "expected a block for %r" % phrase)

    def test_a_word_that_merely_contains_a_keyword_does_not_fire(self):
        """The bracket classes stand in for `\\b`, which BSD `grep -E` does not carry."""
        self.bump_tools(8)
        self.assert_silent(self.run_hook(
            self.stop(message="The undone work is listed in incompleteness order.")))

    def test_a_subagents_tool_calls_count_toward_the_turn(self):
        """They carry the parent's prompt_id and they are work done in the turn."""
        for i in range(8):
            self.run_hook(self.pretooluse(tuid="s%d" % i, agent_id="ag1"))
        self.block_of(self.run_hook(self.stop()))


# ==================================================================== the budget
class BudgetTest(MissionCase):

    def test_the_first_request_is_truncated_at_MISSION_FIRST_CHARS(self):
        # "word " * 600 is 3000 characters AND 600 words, so it is substantive: a
        # single 3000-character token would not be, and would be quoted as a recent
        # request at MISSION_EACH_CHARS instead.
        self.write_rows(self.row("word " * 600), self.row(LONG2))
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn("the first 1200 of 3000 characters", ctx)
        self.assertIn("word " * 240, ctx)
        self.assertNotIn("word " * 241, ctx)

    def test_each_recent_request_is_truncated_at_MISSION_EACH_CHARS(self):
        self.write_rows(self.row(LONG), self.row("B" * 900))
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn("the first 400 of 900 characters", ctx)
        self.assertNotIn("B" * 401, ctx)

    def test_only_MISSION_RECENT_recent_requests_are_quoted(self):
        for i in range(9):
            self.write_rows(self.row("request number %d in this long session" % i))
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn("9 recorded; 4 quoted below", ctx)
        for i in (6, 7, 8):
            self.assertIn("request number %d" % i, ctx)
        for i in (1, 2, 3, 4, 5):
            self.assertNotIn("request number %d" % i, ctx)

    def test_the_elision_marker_states_how_many_characters_were_cut(self):
        """Both halves of the cut: a request dropped whole, and one quoted in part."""
        self.write_rows(self.row(LONG), self.row("C" * 700), self.row(LONG2),
                        self.row(LONG3), self.row("D" * 900))
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        m = re.search(r"\[\.\.\. (\d+) characters of this session's requests "
                      r"are not quoted here \.\.\.\]", ctx)
        self.assertIsNotNone(m, "no elision marker in:\n" + ctx)
        # The 700-character request falls outside MISSION_RECENT and is dropped whole;
        # the 900-character one is quoted to MISSION_EACH_CHARS, cutting 500 more.
        self.assertEqual(int(m.group(1)), 700 + 500)

    def test_truncation_counts_codepoints_and_never_splits_a_character(self):
        """jq slices strings by codepoint; a byte slice would emit half a character."""
        self.write_rows(self.row(LONG), self.row("\u30d1\u30e9\u30e1\u30fc\u30bf" * 200))
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn("the first 400 of 1000 characters", ctx)
        self.assertIn("\u30d1\u30e9\u30e1\u30fc\u30bf" * 80, ctx)
        self.assertNotIn("\u30d1\u30e9\u30e1\u30fc\u30bf" * 81, ctx)

    def test_there_is_no_marker_when_nothing_was_cut(self):
        self.write_rows(self.row(LONG), self.row(LONG2))
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertNotIn("are not quoted here", ctx)

    def test_the_whole_text_is_capped_at_MISSION_MAX_CHARS(self):
        for i in range(6):
            self.write_rows(self.row(("D%d " % i) * 200))
        r = self.run_hook(self.session_start(), MISSION_MAX_CHARS=800)
        ctx = self.context_of(r, "SessionStart")
        self.assertLessEqual(len(ctx), 800)
        self.assertIn("are not quoted here", ctx)

    def test_a_cap_below_one_entry_hard_truncates_rather_than_emitting_nothing(self):
        self.write_rows(self.row(LONG), self.row(LONG2))
        ctx = self.context_of(self.run_hook(self.session_start(), MISSION_MAX_CHARS=120),
                              "SessionStart")
        self.assertEqual(len(ctx), 120)

    def test_a_garbage_knob_falls_back_to_its_default_and_never_reaches_a_test(self):
        self.write_rows(self.row("A" * 3000))
        r = self.run_hook(self.session_start(), MISSION_FIRST_CHARS="not-a-number",
                          MISSION_RECENT="", MISSION_MAX_CHARS="12x")
        ctx = self.context_of(r, "SessionStart")
        self.assertIn("the first 1200 of 3000 characters", ctx)
        self.assertEqual(r.stderr, "")


# ==================================================================== idempotence
class DoubleDeliveryTest(MissionCase):
    """Both wirings deliver every event twice. Everything here must survive that."""

    def setUp(self):
        super().setUp()
        self.default_store()

    def test_each_moment_is_claimed_once(self):
        cases = [
            (self.session_start(), "SessionStart"),
            (self.pretooluse(tool="Agent", tuid="td"), "PreToolUse"),
            (self.subagent_start(aid="agX"), "SubagentStart"),
            (self.user_prompt("go on", pid="pu"), "UserPromptSubmit"),
        ]
        for payload, event in cases:
            shutil.rmtree(os.path.join(self.state, "mission"), ignore_errors=True)
            first = self.run_hook(payload)
            self.assertTrue(self.context_of(first, event))
            self.assert_silent(self.run_hook(payload))
            self.assertEqual(len(self.hit_rows()), 1,
                             "%s wrote more than one hit for one event" % event)

    def test_the_periodic_arm_is_claimed_once(self):
        self.run_hook(self.pretooluse(tuid="t1"))
        later = dict(MISSION_NOW=self.clock + 1201)
        self.assertTrue(self.run_hook(self.pretooluse(tuid="t2"), **later).stdout.strip())
        self.assert_silent(self.run_hook(self.pretooluse(tuid="t2"), **later))

    def test_the_tool_counter_counts_a_duplicated_event_once(self):
        for _ in range(2):
            for i in range(8):
                self.run_hook(self.pretooluse(tuid="dup%d" % i))
        counter = os.path.join(self.state, "mission", "S1", "tools", "p1")
        self.assertEqual(os.path.getsize(counter), 8)

    def test_two_events_with_the_same_id_do_not_claim_each_other(self):
        """A PreToolUse and a UserPromptSubmit carrying one prompt_id are two events."""
        self.assertTrue(self.run_hook(
            self.pretooluse(tool="Agent", tuid="same", pid="same")).stdout.strip())
        self.assertTrue(self.run_hook(self.user_prompt("go on", pid="same")).stdout.strip())


# ==================================================================== the hits log
class HitsTest(MissionCase):

    def setUp(self):
        super().setUp()
        self.default_store()

    def test_a_delivery_writes_one_row_with_every_field(self):
        r = self.run_hook(self.session_start())
        ctx = self.context_of(r, "SessionStart")
        rows = self.hit_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(sorted(row), ["agent_id", "chars", "moment", "prompt_count",
                                       "session", "ts"])
        self.assertEqual(row["ts"], self.clock)
        self.assertEqual(row["session"], "S1")
        self.assertEqual(row["moment"], "resume")
        self.assertIsNone(row["agent_id"])
        self.assertEqual(row["chars"], len(ctx))
        self.assertEqual(row["prompt_count"], 4)

    def test_every_moment_names_itself(self):
        self.run_hook(self.session_start())
        self.run_hook(self.pretooluse(tool="Agent", tuid="td"))
        self.run_hook(self.subagent_start())
        self.run_hook(self.user_prompt("go on", pid="pu"))
        # Before the periodic delivery, so these calls sit inside the interval and say
        # nothing of their own.
        self.bump_tools(8, pid="ps")
        self.run_hook(self.pretooluse(tuid="tp"), MISSION_NOW=self.clock + 99999)
        self.run_hook(self.stop(pid="ps"))
        self.assertEqual([r["moment"] for r in self.hit_rows()],
                         ["resume", "dispatch", "subagent", "ambiguity", "periodic",
                          "completion"])

    def test_chars_is_codepoints_and_not_bytes_whatever_the_locale(self):
        """A column that is codepoints on one machine and bytes on the next is unusable.

        The suite's own environment carries no LANG at all, which is exactly where bash's
        `${#var}` counts bytes; the number therefore comes from jq, whose `length` on a
        string is codepoints everywhere.
        """
        os.remove(self.store)
        self.write_rows(self.row("\u30d1\u30e9\u30e1\u30fc\u30bf" * 20))
        r = self.run_hook(self.session_start())
        ctx = self.context_of(r, "SessionStart")
        row = self.hit_rows()[-1]
        self.assertEqual(row["chars"], len(ctx))
        self.assertLess(row["chars"], len(ctx.encode("utf-8")))

    def test_chars_counts_the_closing_sentence_too(self):
        r = self.run_hook(self.subagent_start())
        ctx = self.context_of(r, "SubagentStart")
        self.assertEqual(self.hit_rows()[-1]["chars"], len(ctx))

    def test_the_log_is_trimmed_on_write_not_only_on_read(self):
        os.makedirs(os.path.dirname(self.hits), exist_ok=True)
        with open(self.hits, "w", encoding="utf-8") as fh:
            for i in range(30):
                fh.write(json.dumps({"ts": i, "session": "old", "moment": "resume",
                                     "agent_id": None, "chars": 1,
                                     "prompt_count": 1}) + "\n")
        self.run_hook(self.session_start(), MISSION_MAX_ROWS=5)
        rows = self.hit_rows()
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[-1]["moment"], "resume")
        self.assertEqual(rows[-1]["session"], "S1")


# ==================================================================== the real writer
class RealWriterTest(MissionCase):
    """The real history-surfer hook writes the row; the real mission hook reads it.

    A writer and a reader that share a format must be driven into each other. This is the
    only test here that does not hand-write the row shape, and it is the one that catches
    history-surfer changing it.
    """

    def setUp(self):
        super().setUp()
        self.surfer_bin = shutil.which("surfer")
        if not self.surfer_bin:
            self.skipTest("history-surfer is not installed (`surfer` not on PATH)")
        root = os.path.dirname(os.path.dirname(os.path.realpath(self.surfer_bin)))
        self.log_prompt = os.path.join(root, "hooks", "log_prompt.py")
        if not os.path.exists(self.log_prompt):
            self.skipTest("history-surfer checkout has no hooks/log_prompt.py")

    def write_through_surfer(self, text, session="S1"):
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": session,
                   "cwd": PROJECT, "prompt": text}
        r = subprocess.run([sys.executable, self.log_prompt], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=TIMEOUT,
                           env={"PATH": BASE_PATH, "HOME": self.home,
                                "CLAUDE_HISTORY_SURFER_DIR": self.surfer})
        self.assertEqual(r.returncode, 0, r.stderr)
        # Contract of that hook: it must never write to stdout.
        self.assertEqual(r.stdout, "")
        return r

    def test_rows_written_by_history_surfer_are_read_back_as_the_mission(self):
        self.write_through_surfer(LONG)
        self.write_through_surfer("/clear")
        self.write_through_surfer(LONG2)
        self.assertTrue(os.path.exists(self.store),
                        "history-surfer wrote no store at %s" % self.store)
        ctx = self.context_of(self.run_hook(self.session_start()), "SessionStart")
        self.assertIn(LONG, ctx)
        self.assertIn(LONG2, ctx)
        self.assertNotIn("/clear", ctx)
        self.assertIn("2 recorded", ctx)

    def test_the_short_prompt_arm_reads_a_row_history_surfer_wrote(self):
        self.write_through_surfer(LONG)
        ctx = self.context_of(self.run_hook(self.user_prompt("continue")),
                              "UserPromptSubmit")
        self.assertIn(LONG, ctx)


# ==================================================================== cost
class CostTest(MissionCase):
    """This runs before every tool call, so a slow one is paid on every tool call."""

    def test_every_event_is_under_the_budget_on_a_200_prompt_store(self):
        rows = [self.row("request %d: %s" % (i, LONG), seq=i + 1) for i in range(200)]
        self.write_rows(*rows)
        self.bump_tools(8, pid="pc")

        cases = [
            ("SessionStart", self.session_start()),
            ("PreToolUse dispatch", self.pretooluse(tool="Agent", tuid="tc")),
            ("PreToolUse ordinary", self.pretooluse(tuid="to")),
            ("SubagentStart", self.subagent_start(aid="agc")),
            ("UserPromptSubmit", self.user_prompt("go on", pid="puc")),
            ("Stop", self.stop(pid="pc")),
        ]
        worst = 0.0
        report = []
        for name, payload in cases:
            samples = []
            for _ in range(5):
                t0 = time.time()
                self.run_hook(payload)
                samples.append((time.time() - t0) * 1000.0)
            med = statistics.median(samples)
            report.append("%-22s %6.1f ms" % (name, med))
            worst = max(worst, med)
        print("\nhooks/mission.sh, 200-prompt store, median of 5:\n  "
              + "\n  ".join(report))
        self.assertLess(worst, COST_BUDGET_MS,
                        "an event exceeded %.0f ms:\n%s" % (COST_BUDGET_MS,
                                                            "\n".join(report)))

    def test_the_missing_store_path_is_the_cheapest(self):
        samples = []
        for _ in range(5):
            t0 = time.time()
            self.run_hook(self.pretooluse())
            samples.append((time.time() - t0) * 1000.0)
        med = statistics.median(samples)
        print("hooks/mission.sh, no store: %.1f ms" % med)
        self.assertLess(med, COST_BUDGET_MS)


# ==================================================================== the contract
class HookContractTest(MissionCase):
    """A hook must never break a turn, whatever it is handed."""

    def test_an_unknown_event_is_silent(self):
        self.default_store()
        for event in ("PostToolUse", "PreCompact", "SubagentStop", "Notification", ""):
            self.assert_silent(self.run_hook(
                {"hook_event_name": event, "session_id": "S1", "cwd": PROJECT}))

    def test_garbage_on_stdin_exits_zero_in_silence(self):
        self.default_store()
        for body in ("", "not json at all", "[]", "null", "{"):
            self.assert_silent(self.run_hook(body))

    def test_the_disable_switch_silences_everything(self):
        self.default_store()
        self.assert_silent(self.run_hook(self.session_start(), MISSION_ENABLED=0))

    def test_a_payload_with_no_cwd_reads_the_unknown_slug_and_stays_silent(self):
        self.default_store()
        self.assert_silent(self.run_hook(
            {"hook_event_name": "SessionStart", "session_id": "S1", "source": "compact"}))

    def test_a_read_only_state_directory_does_not_break_the_turn(self):
        self.default_store()
        os.chmod(self.state, 0o500)
        try:
            r = self.run_hook(self.session_start())
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            os.chmod(self.state, 0o700)

    def test_nothing_is_ever_written_into_history_surfers_store(self):
        self.default_store()
        before = open(self.store, "rb").read()
        self.run_hook(self.session_start())
        self.run_hook(self.pretooluse(tool="Agent", tuid="tz"))
        self.assertEqual(open(self.store, "rb").read(), before)


# --------------------------------------------------------------------- the store root

class StoreRootTest(MissionCase):
    """WHICH directory the store is read from -- one test per rung of the order.

    The order is MISSION_SURFER_ROOT, then CLAUDE_HISTORY_SURFER_DIR, then
    ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/history-surfer. Rung 3 was the literal
    `$HOME/.claude/history-surfer` until 2026-09-03, so an install into a non-default
    `--claude-dir` put the store somewhere the hook never looked and the hook went silent
    with nothing to say why -- found by the E2E journey, which had to set
    MISSION_SURFER_ROOT by hand to measure its own mission steps at all.

    Each test puts a REAL store, in history-surfer's own layout, under the rung it is
    about, and DECOYS holding a different sentence under the rungs it must not read. The
    assertion is on which sentence comes back, so a test cannot pass by the hook finding
    the right prompt at the wrong path.
    """

    R1 = "the mission surfer root override is the first rung of the three"
    R2 = "history surfer's own directory override is the second rung of the three"
    R3 = "the claude config dir is the third rung of the three"
    R4 = "the home dot claude default is the last rung of the three"

    def bare_env(self, **extra):
        """The hook's environment with NO store-root variable in it at all.

        `MissionCase.env` always exports MISSION_SURFER_ROOT, which is the one thing
        these tests may not assume: a rung is only measured when the rungs above it are
        genuinely absent from the environment, not merely pointed elsewhere.
        """
        e = {"PATH": BASE_PATH, "HOME": self.home,
             "SKILL_COMPOUNDER_STATE": self.state,
             "MISSION_NOW": str(self.clock)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def run_bare(self, payload, **env_extra):
        body = json.dumps(payload)
        return subprocess.run(["bash", HOOK], input=body, capture_output=True,
                              text=True, env=self.bare_env(**env_extra), timeout=TIMEOUT)

    def store_at(self, root, phrase):
        """A real one-prompt store under `root`, in history-surfer's own layout."""
        d = os.path.join(root, "projects", self.slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "prompts.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(self.row(phrase)) + "\n")
        return root

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)

    def assert_read(self, r, wanted, *not_wanted):
        ctx = self.context_of(r, "SessionStart")
        self.assertIn(wanted, ctx, "the wrong store was read: %r" % ctx)
        for other in not_wanted:
            self.assertNotIn(other, ctx, "a decoy store was read: %r" % ctx)

    # ------------------------------------------------------------------------ rung 1

    def test_rung_1_mission_surfer_root_wins_over_both_rungs_below_it(self):
        self.store_at(self.store_at(self.surfer, self.R1), self.R1)
        hs = self.store_at(self.path("hs-dir"), self.R2)
        cfg = self.path("cfg")
        self.store_at(os.path.join(cfg, "history-surfer"), self.R3)
        r = self.run_bare(self.session_start(), MISSION_SURFER_ROOT=self.surfer,
                          CLAUDE_HISTORY_SURFER_DIR=hs, CLAUDE_CONFIG_DIR=cfg)
        self.assert_read(r, self.R1, self.R2, self.R3)

    # ------------------------------------------------------------------------ rung 2

    def test_rung_2_history_surfer_dir_is_read_when_rung_1_is_absent(self):
        """CLAUDE_HISTORY_SURFER_DIR is history-surfer's OWN override
        (history_surfer/config.py:39-41), so honouring it is what keeps the writer and
        this reader on one file."""
        hs = self.store_at(self.path("hs-dir"), self.R2)
        cfg = self.path("cfg")
        self.store_at(os.path.join(cfg, "history-surfer"), self.R3)
        r = self.run_bare(self.session_start(), CLAUDE_HISTORY_SURFER_DIR=hs,
                          CLAUDE_CONFIG_DIR=cfg)
        self.assert_read(r, self.R2, self.R3)

    # ------------------------------------------------------------------------ rung 3

    def test_rung_3_is_the_claude_config_dir_when_neither_override_is_set(self):
        cfg = self.path("cfg")
        self.store_at(os.path.join(cfg, "history-surfer"), self.R3)
        # And the old hardcoded path is not merely absent, it is SCAFFOLDED AND EMPTY --
        # which is what history-surfer's own installer leaves behind. A hook still reading
        # it finds a directory, no rows, and says nothing.
        os.makedirs(os.path.join(self.home, ".claude", "history-surfer", "projects",
                                 self.slug))
        r = self.run_bare(self.session_start(), CLAUDE_CONFIG_DIR=cfg)
        self.assert_read(r, self.R3)

    def test_rung_3_falls_back_to_home_dot_claude_when_nothing_is_set(self):
        """The default on every ordinary machine, and the one rung with no variable
        behind it."""
        self.store_at(os.path.join(self.home, ".claude", "history-surfer"), self.R4)
        r = self.run_bare(self.session_start())
        self.assert_read(r, self.R4)

    # ------------------------------------------------------------- the empty-value rule

    def test_an_exported_but_empty_override_falls_through_to_the_next_rung(self):
        """`:-` and not `-` at every rung. An exported-but-empty variable is a typo in
        somebody's shell profile, and taking it would make the root the literal
        `/projects/<slug>` and silence the hook for good."""
        cfg = self.path("cfg")
        self.store_at(os.path.join(cfg, "history-surfer"), self.R3)
        r = self.run_bare(self.session_start(), MISSION_SURFER_ROOT="",
                          CLAUDE_HISTORY_SURFER_DIR="", CLAUDE_CONFIG_DIR=cfg)
        self.assert_read(r, self.R3)

    def test_an_empty_rung_1_still_falls_through_to_rung_2(self):
        hs = self.store_at(self.path("hs-dir"), self.R2)
        r = self.run_bare(self.session_start(), MISSION_SURFER_ROOT="",
                          CLAUDE_HISTORY_SURFER_DIR=hs)
        self.assert_read(r, self.R2)

    # ------------------------------------------------------------------- the regression

    def test_a_non_default_claude_dir_no_longer_silences_the_hook(self):
        """The defect itself, stated as the E2E run found it: history-surfer installed
        into a non-default claude dir, prompts captured there, and the hook reading
        `$HOME/.claude/history-surfer` -- which does not even exist. Before the fix this
        was silence; the store is reachable by derivation alone now."""
        cfg = self.path("throwaway-claude")
        self.store_at(os.path.join(cfg, "history-surfer"), self.R3)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude")),
                         "the old hardcoded root must not exist for this to prove anything")
        r = self.run_bare(self.session_start(), CLAUDE_CONFIG_DIR=cfg)
        self.assert_read(r, self.R3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
