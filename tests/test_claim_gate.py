#!/usr/bin/env python3
"""Tests for hooks/claim-gate.sh -- the Stop / PreToolUse claim gate.

NO MOCKS, per this repo's standing rule. Every test writes a real JSONL transcript to a
temp directory, runs the real shell script through subprocess with a minimal PATH, HOME
and SKILL_COMPOUNDER_STATE pinned into that directory, and reads the decision off stdout.

RECORD SHAPES ARE COPIED FROM A REAL TRANSCRIPT, not invented. The field sets below were
read off ~/.claude/projects/.../f0feae4c-....jsonl on CLI 2.1.245:

  assistant record top-level keys:
    attributionSkill cwd effort entrypoint gitBranch isSidechain message parentUuid
    requestId sessionId session_id timestamp type userType uuid version
  tool-result record top-level keys:
    cwd entrypoint gitBranch isSidechain message parentUuid promptId sessionId session_id
    sourceToolAssistantUUID timestamp toolUseResult type userType uuid version
  a Bash tool_use is {"type","id","name","input":{"command","description"}}
  a tool_result is  {"type","tool_use_id","is_error","content"} with content a STRING
  a Bash toolUseResult is {interrupted,isImage,noOutputExpected,stderr,stdout}
  `isSidechain` is present and FALSE on main-session records.

EVERY subprocess call against a hook passes `input=`. The script reads its payload with
`payload="$(cat)"`; without stdin it hangs forever.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "claim-gate.sh")

# Minimal, explicit environment: the script must not depend on the ambient one.
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"


# --------------------------------------------------------------------------- fixtures
def user_prompt(text):
    return {
        "type": "user", "isSidechain": False, "isMeta": False,
        "userType": "external", "cwd": "/repo", "gitBranch": "main",
        "sessionId": "s", "uuid": "u-prompt", "parentUuid": None,
        "version": "2.1.245", "timestamp": "2026-08-25T00:00:00.000Z",
        "message": {"role": "user", "content": text},
    }


def tool_call(tool_id, command, name="Bash"):
    return {
        "type": "assistant", "isSidechain": False, "userType": "external",
        "cwd": "/repo", "gitBranch": "main", "sessionId": "s",
        "uuid": "u-" + tool_id, "parentUuid": "u-prompt", "requestId": "req",
        "version": "2.1.245", "timestamp": "2026-08-25T00:00:01.000Z",
        "message": {
            "role": "assistant", "type": "message", "id": "msg_" + tool_id,
            "model": "claude", "stop_reason": None, "stop_sequence": None,
            "usage": {}, "content": [
                {"type": "tool_use", "id": tool_id, "name": name,
                 "input": {"command": command, "description": "d"}},
            ],
        },
    }


def file_write(tool_id, path, name="Write"):
    r = tool_call(tool_id, "", name=name)
    r["message"]["content"][0]["input"] = {"file_path": path, "content": "x"}
    return r


def tool_result(tool_id, stdout, stderr=""):
    return {
        "type": "user", "isSidechain": False, "userType": "external",
        "cwd": "/repo", "gitBranch": "main", "sessionId": "s",
        "uuid": "u-res-" + tool_id, "parentUuid": "u-" + tool_id,
        "sourceToolAssistantUUID": "u-" + tool_id, "promptId": "p",
        "version": "2.1.245", "timestamp": "2026-08-25T00:00:02.000Z",
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_id,
             "is_error": False, "content": stdout},
        ]},
        "toolUseResult": {"interrupted": False, "isImage": False,
                          "noOutputExpected": False,
                          "stdout": stdout, "stderr": stderr},
    }


def assistant_text(text):
    r = tool_call("t-text", "")
    r["message"]["content"] = [{"type": "text", "text": text}]
    return r


def agent_call(tool_id, prompt):
    """An Agent dispatch. Its result is a subagent's TESTIMONY, not measurement."""
    r = tool_call(tool_id, "", name="Agent")
    r["message"]["content"][0]["input"] = {"prompt": prompt, "description": "d"}
    return r


def agent_result(tool_id, report):
    r = tool_result(tool_id, report)
    r["toolUseResult"] = {"agentId": "a1", "status": "completed",
                          "prompt": "the task", "description": "d",
                          "resolvedModel": "claude", "isAsync": False}
    return r


class ClaimGateTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="claimgate-")
        self.home = os.path.join(self.tmp, "home")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.home)
        os.makedirs(self.state)
        self.transcript = os.path.join(self.tmp, "transcript.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------- helpers
    def write_transcript(self, records):
        with open(self.transcript, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")

    def run_hook(self, payload, **env_extra):
        env = {"PATH": BASE_PATH, "HOME": self.home,
               "SKILL_COMPOUNDER_STATE": self.state}
        env.update({k: str(v) for k, v in env_extra.items()})
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(
            ["bash", HOOK], input=body, capture_output=True, text=True,
            env=env, timeout=180,
        )

    def stop_payload(self, message, session="s1", prompt="p1", **over):
        p = {"hook_event_name": "Stop", "session_id": session,
             "transcript_path": self.transcript, "cwd": "/repo",
             "prompt_id": prompt, "permission_mode": "auto",
             "effort": {"level": "high"}, "stop_hook_active": False,
             "last_assistant_message": message,
             "background_tasks": [], "session_crons": []}
        p.update(over)
        return p

    def pre_payload(self, command, session="s1", **over):
        p = {"hook_event_name": "PreToolUse", "session_id": session,
             "transcript_path": self.transcript, "cwd": "/repo",
             "prompt_id": "p1", "permission_mode": "auto",
             "effort": {"level": "high"}, "tool_name": "Bash",
             "tool_use_id": "toolu_pre",
             "tool_input": {"command": command, "description": "d"}}
        p.update(over)
        return p

    def decision(self, result):
        """Parse a decision off stdout, or None when the hook stayed silent."""
        self.assertEqual(result.returncode, 0,
                         "the gate must ALWAYS exit 0; stderr=%r" % result.stderr)
        out = result.stdout.strip()
        if not out:
            return None
        return json.loads(out)

    def assert_silent(self, result):
        d = self.decision(result)
        self.assertIsNone(d, "expected no decision, got %r" % result.stdout)

    def assert_blocked(self, result):
        d = self.decision(result)
        self.assertIsNotNone(d, "expected a block, got nothing")
        self.assertEqual(d.get("decision"), "block")
        return d["reason"]

    def assert_denied(self, result):
        d = self.decision(result)
        self.assertIsNotNone(d, "expected a deny, got nothing")
        h = d["hookSpecificOutput"]
        self.assertEqual(h["hookEventName"], "PreToolUse")
        self.assertEqual(h["permissionDecision"], "deny")
        return h["permissionDecisionReason"]

    def a_test_run(self, count=443):
        """A session in which ./run_tests.sh really ran and printed a count."""
        return [
            user_prompt("run the tests"),
            tool_call("toolu_1", "./run_tests.sh"),
            tool_result("toolu_1", "Ran %d tests in 12.5s\nOK\nALL TESTS PASSED\n" % count),
        ]

    # =================================================================== tier 1
    def test_supported_number_passes(self):
        self.write_transcript(self.a_test_run(443))
        r = self.run_hook(self.stop_payload("Done. 443 tests pass on this tree."))
        self.assert_silent(r)

    def test_unsupported_number_blocks_and_names_it(self):
        self.write_transcript(self.a_test_run(443))
        r = self.run_hook(self.stop_payload("Done. The suite is now 1495 tests."))
        reason = self.assert_blocked(r)
        self.assertIn("1495", reason)
        self.assertNotIn("443", reason)
        # The message must be actionable: it names what was missing and what to run.
        self.assertIn("no tool output", reason)
        self.assertIn("./run_tests.sh", reason)

    def test_comma_grouped_number_matches_plain_evidence(self):
        self.write_transcript(self.a_test_run(1495))
        r = self.run_hook(self.stop_payload("The suite is 1,495 tests."))
        self.assert_silent(r)

    def test_plain_number_matches_comma_grouped_evidence(self):
        recs = self.a_test_run(443)
        recs.append(tool_result("toolu_2", "processed 21,926 words of prose"))
        self.write_transcript(recs)
        r = self.run_hook(self.stop_payload("Measured over 21926 words."))
        self.assert_silent(r)

    def test_dates_versions_and_file_line_refs_do_not_block(self):
        self.write_transcript(self.a_test_run(443))
        msg = ("Fixed on 2026-08-25 against CLI 2.1.245 at 23:47, see "
               "hooks/claim-gate.sh:812 and line 404 of the doc. Closes #1495. "
               "HTTP 204 came back, RFC 2119 applies, sha 871ab33, 512MB free, "
               "and coverage moved 90% -> 100% (0.05 per 1000).")
        r = self.run_hook(self.stop_payload(msg))
        self.assert_silent(r)

    def test_numbers_inside_code_are_quotation_not_assertion(self):
        self.write_transcript(self.a_test_run(443))
        msg = ("The header still reads `1428 subagent transcripts`.\n\n"
               "```\nRan 99999 tests\n```\n\nNothing else changed.")
        r = self.run_hook(self.stop_payload(msg))
        self.assert_silent(r)

    def test_small_numbers_are_never_flagged(self):
        self.write_transcript(self.a_test_run(443))
        r = self.run_hook(self.stop_payload(
            "I fixed 7 defects across 12 files, 2 of 9 remain, 88 lines touched."))
        self.assert_silent(r)

    def test_min_digits_knob_lowers_the_floor(self):
        self.write_transcript(self.a_test_run(443))
        p = self.stop_payload("I fixed 88 defects.")
        self.assert_silent(self.run_hook(p))
        r = self.run_hook(p, CLAIM_GATE_MIN_DIGITS=2)
        self.assertIn("88", self.assert_blocked(r))

    def test_a_number_the_assistant_typed_into_a_command_is_not_evidence(self):
        """The founding defect: `git commit -m "1495 tests"` must not vouch for itself."""
        recs = self.a_test_run(443)
        recs.append(tool_call("toolu_9", 'git commit -m "1495 tests across 27 files"'))
        recs.append(tool_result("toolu_9", "[main abc1234] committed\n"))
        self.write_transcript(recs)
        r = self.run_hook(self.stop_payload("Committed: 1495 tests across 27 files."))
        self.assertIn("1495", self.assert_blocked(r))

    def test_a_subagent_report_is_testimony_not_evidence(self):
        """Relayed figures are the commonest real case, and must still be flagged."""
        recs = self.a_test_run(443)
        recs.append(agent_call("toolu_a", "go and count the words"))
        recs.append(agent_result("toolu_a", "I counted 21926 words of prose."))
        self.write_transcript(recs)
        r = self.run_hook(self.stop_payload("Measured across 21926 words of prose."))
        reason = self.assert_blocked(r)
        self.assertIn("21926", reason)
        self.assertIn("testimony", reason)

    def test_a_real_tool_output_in_the_same_session_is_evidence(self):
        recs = self.a_test_run(443)
        recs.append(tool_result("toolu_3", "   21926 total words\n"))
        self.write_transcript(recs)
        r = self.run_hook(self.stop_payload("Measured across 21926 words of prose."))
        self.assert_silent(r)

    def test_extra_evidence_directory_is_honoured(self):
        self.write_transcript(self.a_test_run(443))
        extra = os.path.join(self.tmp, "extra")
        os.makedirs(extra)
        with open(os.path.join(extra, "out.txt"), "w") as fh:
            fh.write("the run produced 8675309 rows\n")
        msg = "The run produced 8675309 rows."
        self.assertIn("8675309", self.assert_blocked(self.run_hook(self.stop_payload(msg))))
        r = self.run_hook(self.stop_payload(msg, prompt="p2"),
                          CLAIM_GATE_EXTRA_EVIDENCE=extra)
        self.assert_silent(r)

    def test_tier1_can_be_disabled(self):
        self.write_transcript(self.a_test_run(443))
        r = self.run_hook(self.stop_payload("The suite is 1495 tests."),
                          CLAIM_GATE_TIER1=0)
        self.assert_silent(r)

    def test_findings_are_capped(self):
        self.write_transcript(self.a_test_run(443))
        msg = "Counts: 1111 2222 3333 4444 5555 6666 7777 8888 tests."
        reason = self.assert_blocked(
            self.run_hook(self.stop_payload(msg), CLAIM_GATE_MAX_FINDINGS=3))
        self.assertEqual(reason.count("appears in no tool output"), 3)
        self.assertIn("and 5 more", reason)

    # =================================================================== tier 2
    def test_completion_claim_with_no_test_run_blocks(self):
        self.write_transcript([
            user_prompt("fix the bug"),
            tool_call("toolu_1", "grep -rn foo src"),
            tool_result("toolu_1", "src/a.py:1:foo\n"),
        ])
        reason = self.assert_blocked(
            self.run_hook(self.stop_payload("Fixed. All tests pass.")))
        self.assertIn("nothing in this session ran a test command", reason)

    def test_completion_claim_with_a_real_test_run_passes(self):
        self.write_transcript(self.a_test_run(443))
        self.assert_silent(self.run_hook(self.stop_payload("All tests pass.")))

    def test_completion_claim_survives_into_a_later_summary_turn(self):
        """Calibration case: restating a verification from an earlier turn is legitimate."""
        recs = self.a_test_run(443)
        recs.append(user_prompt("summarise where we are"))
        self.write_transcript(recs)
        self.assert_silent(self.run_hook(
            self.stop_payload("Everything is finished: the suite is green.")))

    def test_a_source_edit_after_the_test_run_makes_the_claim_stale(self):
        recs = self.a_test_run(443)
        recs.append(file_write("toolu_w", "/repo/skill_compounder/installer.py"))
        recs.append(tool_result("toolu_w", "ok"))
        self.write_transcript(recs)
        reason = self.assert_blocked(self.run_hook(self.stop_payload("All tests pass.")))
        self.assertIn("AFTER the last test run", reason)

    def test_a_note_or_scratch_edit_after_the_test_run_does_not(self):
        """Rewriting a note cannot turn a green suite red; calibration made this rule."""
        for path in ("/repo/notes/2026-08-25-session.md", "/repo/README.md",
                     "/private/tmp/scratch/out.txt"):
            recs = self.a_test_run(443)
            recs.append(file_write("toolu_w", path))
            recs.append(tool_result("toolu_w", "ok"))
            self.write_transcript(recs)
            r = self.run_hook(self.stop_payload("All tests pass.", prompt="p-" + path))
            self.assert_silent(r)

    def test_a_ci_query_counts_as_a_run_for_a_ci_claim(self):
        self.write_transcript([
            user_prompt("check ci"),
            tool_call("toolu_1", "gh run list --limit 1"),
            tool_result("toolu_1", 'completed\tsuccess\tmain\n'),
        ])
        self.assert_silent(self.run_hook(self.stop_payload("CI green on main.")))

    def test_bare_verified_is_deliberately_not_flagged(self):
        """Documented stance: 'verified' has real evidence no pattern can tie to it."""
        self.write_transcript([
            user_prompt("look at it"),
            tool_call("toolu_1", "cat README.md"),
            tool_result("toolu_1", "some prose\n"),
        ])
        for msg in ("I verified the wording is correct.",
                    "Confirmed: the link resolves.",
                    "Checked and verified against the doc."):
            self.assert_silent(self.run_hook(self.stop_payload(msg, prompt=msg[:8])))

    def test_tier2_can_be_disabled(self):
        self.write_transcript([user_prompt("fix"), tool_call("toolu_1", "ls"),
                               tool_result("toolu_1", "a\n")])
        self.assert_silent(self.run_hook(self.stop_payload("All tests pass."),
                                         CLAIM_GATE_TIER2=0))

    # ============================================================== loop guards
    def test_stop_hook_active_short_circuits(self):
        """PLATFORM FACT: true on any Stop that exists only because a hook blocked."""
        self.write_transcript(self.a_test_run(443))
        r = self.run_hook(self.stop_payload("The suite is 1495 tests.",
                                            stop_hook_active=True))
        self.assert_silent(r)

    def test_the_gate_blocks_at_most_once_per_turn(self):
        self.write_transcript(self.a_test_run(443))
        p = self.stop_payload("The suite is 1495 tests.", prompt="p-loop")
        self.assertIn("1495", self.assert_blocked(self.run_hook(p)))
        for _ in range(4):
            self.assert_silent(self.run_hook(p))

    def test_a_new_turn_is_judged_again(self):
        self.write_transcript(self.a_test_run(443))
        first = self.stop_payload("The suite is 1495 tests.", prompt="turn-a")
        second = self.stop_payload("The suite is 1495 tests.", prompt="turn-b")
        self.assert_blocked(self.run_hook(first))
        self.assert_blocked(self.run_hook(second))

    def test_max_blocks_knob_allows_more_than_one(self):
        self.write_transcript(self.a_test_run(443))
        p = self.stop_payload("The suite is 1495 tests.", prompt="p-two")
        self.assert_blocked(self.run_hook(p, CLAIM_GATE_MAX_BLOCKS=2))
        self.assert_blocked(self.run_hook(p, CLAIM_GATE_MAX_BLOCKS=2))
        self.assert_silent(self.run_hook(p, CLAIM_GATE_MAX_BLOCKS=2))

    def test_session_cap_bounds_the_worst_case(self):
        """Backstop for lost per-turn state: distinct turns still cannot block forever."""
        self.write_transcript(self.a_test_run(443))
        blocked = 0
        for i in range(6):
            p = self.stop_payload("The suite is 1495 tests.", prompt="p%d" % i)
            if self.decision(self.run_hook(p, CLAIM_GATE_MAX_SESSION=3)):
                blocked += 1
        self.assertEqual(blocked, 3)

    def test_double_delivery_is_idempotent(self):
        """With settings.json and the plugin both wired, every hook arrives twice."""
        self.write_transcript(self.a_test_run(443))
        p = json.dumps(self.stop_payload("The suite is 1495 tests.", prompt="p-dup"))
        outs = []
        for _ in range(2):
            outs.append(self.decision(self.run_hook(p)))
        self.assertEqual(sum(1 for o in outs if o), 1,
                         "exactly one of two identical deliveries may speak")

    def test_concurrent_double_delivery_blocks_only_once(self):
        self.write_transcript(self.a_test_run(443))
        body = json.dumps(self.stop_payload("The suite is 1495 tests.", prompt="p-race"))
        env = {"PATH": BASE_PATH, "HOME": self.home,
               "SKILL_COMPOUNDER_STATE": self.state}
        procs = [subprocess.Popen(["bash", HOOK], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, env=env) for _ in range(4)]
        outs = [p.communicate(input=body, timeout=180)[0].strip() for p in procs]
        self.assertEqual(sum(1 for o in outs if o), 1, outs)

    # ========================================================= never break a turn
    def test_malformed_payload_exits_zero_silently(self):
        self.write_transcript(self.a_test_run(443))
        for bad in ("", "not json at all", "[]", "null", '{"hook_event_name":',
                    '{"hook_event_name":"Stop"}', '{"hook_event_name":123}'):
            r = self.run_hook(bad)
            self.assertEqual(r.returncode, 0, bad)
            self.assertEqual(r.stdout.strip(), "", bad)

    def test_missing_transcript_exits_zero_silently(self):
        p = self.stop_payload("The suite is 1495 tests.",
                              transcript_path=os.path.join(self.tmp, "nope.jsonl"))
        self.assert_silent(self.run_hook(p))

    def test_unreadable_transcript_exits_zero_silently(self):
        self.write_transcript(self.a_test_run(443))
        os.chmod(self.transcript, 0o000)
        try:
            if os.access(self.transcript, os.R_OK):
                self.skipTest("running as a user that can read mode-000 files")
            self.assert_silent(self.run_hook(
                self.stop_payload("The suite is 1495 tests.")))
        finally:
            os.chmod(self.transcript, 0o644)

    def test_corrupt_transcript_lines_do_not_break_the_gate(self):
        with open(self.transcript, "w", encoding="utf-8") as fh:
            fh.write("{not json\n")
            for r in self.a_test_run(443):
                fh.write(json.dumps(r) + "\n")
            fh.write("\x00\x01 garbage\n")
        self.assert_silent(self.run_hook(self.stop_payload("443 tests pass.")))

    def test_empty_transcript_exits_zero_silently(self):
        open(self.transcript, "w").close()
        self.assert_silent(self.run_hook(self.stop_payload("The suite is 1495 tests.")))

    def test_without_jq_the_gate_is_silent(self):
        self.write_transcript(self.a_test_run(443))
        bare = os.path.join(self.tmp, "bin")
        os.makedirs(bare)
        for tool in ("bash", "cat", "grep", "sed", "awk", "sort", "mkdir",
                     "printf", "tr", "cut", "rev", "wc", "tail", "find", "mktemp"):
            src = shutil.which(tool)
            if src:
                os.symlink(src, os.path.join(bare, tool))
        r = self.run_hook(self.stop_payload("The suite is 1495 tests."), PATH=bare)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_unwritable_state_dir_never_breaks_the_turn(self):
        self.write_transcript(self.a_test_run(443))
        blocked = os.path.join(self.tmp, "nostate")
        os.makedirs(blocked)
        os.chmod(blocked, 0o500)
        try:
            r = self.run_hook(self.stop_payload("The suite is 1495 tests."),
                              SKILL_COMPOUNDER_STATE=os.path.join(blocked, "x"))
            self.assertEqual(r.returncode, 0)
        finally:
            os.chmod(blocked, 0o700)

    def test_no_message_exits_zero(self):
        self.write_transcript(self.a_test_run(443))
        self.assert_silent(self.run_hook(self.stop_payload("")))

    def test_master_switch_disables_everything(self):
        self.write_transcript(self.a_test_run(443))
        self.assert_silent(self.run_hook(self.stop_payload("The suite is 1495 tests."),
                                         CLAIM_GATE=0))

    def test_subagent_stop_is_ignored(self):
        self.write_transcript(self.a_test_run(443))
        p = self.stop_payload("The suite is 1495 tests.",
                              hook_event_name="SubagentStop")
        self.assert_silent(self.run_hook(p))

    def test_the_gate_never_exits_nonzero(self):
        """The single most important property: exit 0 on every path, block included."""
        self.write_transcript(self.a_test_run(443))
        for payload in (self.stop_payload("443 tests pass."),
                        self.stop_payload("The suite is 1495 tests."),
                        self.pre_payload('git commit -m "1495 tests"'),
                        "garbage"):
            self.assertEqual(self.run_hook(payload).returncode, 0)

    # ======================================================== the commit-message arm
    def test_a_commit_message_with_an_unsupported_figure_is_denied(self):
        self.write_transcript(self.a_test_run(443))
        reason = self.assert_denied(self.run_hook(
            self.pre_payload('git commit -m "1495 tests across 27 files, all green"')))
        self.assertIn("1495", reason)

    def test_a_command_that_merely_mentions_committing_is_not_denied(self):
        """`git` must sit in COMMAND POSITION, not merely appear in the text.

        The discriminating case has to carry an EXTRACTABLE -m message, or it is
        silent under either matcher and the test proves nothing. A first version of
        this test used a body with no -m at all and passed against the unfixed hook.
        """
        self.write_transcript(self.a_test_run(443))
        self.assert_silent(self.run_hook(self.pre_payload(
            'gh issue comment 16 --body '
            '\'we ran git commit -m "9911 tests pass" yesterday\'')))

    def test_a_commit_message_with_a_supported_figure_passes(self):
        self.write_transcript(self.a_test_run(443))
        self.assert_silent(self.run_hook(
            self.pre_payload('git commit -m "443 tests across 27 files, all green"')))

    def test_a_heredoc_commit_message_is_read(self):
        """The real shape of the founding defect: `git commit -m "$(cat <<'EOF' ...`."""
        self.write_transcript(self.a_test_run(443))
        cmd = ("git add -A && git commit -m \"$(cat <<'EOF'\n"
               "Fix the thing\n\n1495 tests across 27 files, all green.\nEOF\n)\"")
        self.assertIn("1495", self.assert_denied(self.run_hook(self.pre_payload(cmd))))

    def test_a_single_quoted_commit_message_is_read(self):
        self.write_transcript(self.a_test_run(443))
        self.assertIn("1495", self.assert_denied(self.run_hook(
            self.pre_payload("git commit -m 'ship it: 1495 tests'"))))

    def test_non_commit_bash_commands_are_ignored(self):
        self.write_transcript(self.a_test_run(443))
        for cmd in ("echo 1495", "ls -la", "git status", "git log --oneline -1495"):
            self.assert_silent(self.run_hook(self.pre_payload(cmd)))

    def test_non_bash_tools_are_ignored(self):
        self.write_transcript(self.a_test_run(443))
        p = self.pre_payload("x", tool_name="Write")
        p["tool_input"] = {"file_path": "/repo/a.md", "content": "1495 tests"}
        self.assert_silent(self.run_hook(p))

    def test_the_commit_arm_relents_after_repeated_identical_denials(self):
        """A denial cannot loop, but a verbatim retry must not cost the user forever."""
        self.write_transcript(self.a_test_run(443))
        p = self.pre_payload('git commit -m "1495 tests"', session="s-relent")
        self.assert_denied(self.run_hook(p))
        self.assert_denied(self.run_hook(p))
        self.assert_silent(self.run_hook(p))

    def test_the_commit_arm_can_be_disabled(self):
        self.write_transcript(self.a_test_run(443))
        self.assert_silent(self.run_hook(
            self.pre_payload('git commit -m "1495 tests"'), CLAIM_GATE_COMMIT=0))

    def test_the_deny_reason_is_a_statement_not_an_instruction(self):
        """PLATFORM FACT: the model correctly refuses directives arriving via a blocked
        tool result, so the deny reason must assert a fact rather than issue an order."""
        self.write_transcript(self.a_test_run(443))
        reason = self.assert_denied(self.run_hook(
            self.pre_payload('git commit -m "1495 tests"')))
        for imperative in ("Run ", "Do one of these", "./run_tests.sh"):
            self.assertNotIn(imperative, reason)

    # =========================================================== the accumulator arm
    def test_post_tool_use_records_numbers_from_output(self):
        self.write_transcript(self.a_test_run(443))
        payload = {"hook_event_name": "PostToolUse", "session_id": "s1",
                   "transcript_path": self.transcript, "cwd": "/repo",
                   "tool_name": "Bash", "tool_use_id": "toolu_5",
                   "tool_input": {"command": "echo 8675309"},
                   "tool_response": {"stdout": "counted 8675309 rows\n", "stderr": ""}}
        self.assert_silent(self.run_hook(payload))
        recorded = open(os.path.join(self.state, "claim-gate", "s1.numbers")).read()
        self.assertIn("8675309", recorded)

    def test_post_tool_use_ignores_tool_input(self):
        """A number the assistant typed must never reach the evidence set."""
        payload = {"hook_event_name": "PostToolUse", "session_id": "s1",
                   "transcript_path": self.transcript, "cwd": "/repo",
                   "tool_name": "Bash", "tool_use_id": "toolu_6",
                   "tool_input": {"command": 'git commit -m "1495 tests"'},
                   "tool_response": {"stdout": "[main abc] ok\n", "stderr": ""}}
        self.assert_silent(self.run_hook(payload))
        path = os.path.join(self.state, "claim-gate", "s1.numbers")
        recorded = open(path).read() if os.path.exists(path) else ""
        self.assertNotIn("1495", recorded)

    def test_accumulated_numbers_count_as_evidence(self):
        self.write_transcript(self.a_test_run(443))
        os.makedirs(os.path.join(self.state, "claim-gate"), exist_ok=True)
        with open(os.path.join(self.state, "claim-gate", "s1.numbers"), "w") as fh:
            fh.write("8675309\n")
        self.assert_silent(self.run_hook(
            self.stop_payload("The run produced 8675309 rows.")))

    def test_the_accumulator_can_be_disabled(self):
        payload = {"hook_event_name": "PostToolUse", "session_id": "s1",
                   "transcript_path": self.transcript, "cwd": "/repo",
                   "tool_name": "Bash", "tool_use_id": "toolu_7",
                   "tool_input": {}, "tool_response": {"stdout": "8675309\n"}}
        self.assert_silent(self.run_hook(payload, CLAIM_GATE_ACCUMULATE=0))
        self.assertFalse(os.path.exists(
            os.path.join(self.state, "claim-gate", "s1.numbers")))

    # ================================================================ script hygiene
    def test_the_script_parses_and_is_brace_wrapped(self):
        """House rule: the whole body is one brace group, `exit` before the closing `}`,
        so a `git pull` cannot execute half a rewritten file that is already running."""
        r = subprocess.run(["bash", "-n", HOOK], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l.rstrip() for l in open(HOOK, encoding="utf-8").read().splitlines()
                 if l.strip()]
        self.assertEqual(lines[-1].strip(), "}")
        self.assertTrue(lines[-2].strip().startswith("exit"), lines[-2])

    def test_every_env_knob_is_documented_in_the_header(self):
        text = open(HOOK, encoding="utf-8").read()
        header = text.split("set -uo pipefail")[0]
        import re
        knobs = set(re.findall(r'\$\{(CLAIM_GATE[A-Z_]*)', text))
        for knob in sorted(knobs):
            self.assertIn(knob, header, "%s is undocumented" % knob)

    def test_the_script_is_executable(self):
        self.assertTrue(os.access(HOOK, os.X_OK))




if __name__ == "__main__":
    unittest.main(verbosity=2)
