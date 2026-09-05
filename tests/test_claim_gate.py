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

    def project_dir(self, *empty_files, **files_with_content):
        """A real directory under self.tmp holding the given files, so the runner-hint
        detection in hooks/claim-gate.sh (which reads `cwd` off the payload) sees real
        content rather than the nonexistent "/repo" every other fixture uses."""
        d = tempfile.mkdtemp(prefix="proj-", dir=self.tmp)
        for name in empty_files:
            open(os.path.join(d, name), "w", encoding="utf-8").close()
        for name, content in files_with_content.items():
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                fh.write(content)
        return d

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
        proj = self.project_dir("run_tests.sh")
        r = self.run_hook(self.stop_payload(
            "Done. The suite is now 1495 tests.", cwd=proj))
        reason = self.assert_blocked(r)
        self.assertIn("1495", reason)
        self.assertNotIn("443", reason)
        # The message must be actionable: it names what was missing and what to run.
        self.assertIn("no tool output", reason)
        self.assertIn("./run_tests.sh", reason)

    # --------------------------------------------------- the test-runner hint is derived
    # A hardcoded "./run_tests.sh" is this repo's own convention and is wrong, or
    # meaningless, in any project that has no such file. The hint must instead be derived
    # from what the working directory (`cwd`, carried on every payload) actually holds,
    # with a plain fallback when none of the known shapes are present.
    def test_runner_hint_makefile_test_target(self):
        self.write_transcript(self.a_test_run(443))
        proj = self.project_dir(**{"Makefile": "test:\n\tpytest\n"})
        r = self.run_hook(self.stop_payload(
            "Done. The suite is now 1495 tests.", cwd=proj))
        reason = self.assert_blocked(r)
        self.assertIn("make test", reason)
        self.assertNotIn("./run_tests.sh", reason)

    def test_runner_hint_makefile_check_target(self):
        self.write_transcript(self.a_test_run(443))
        proj = self.project_dir(**{"Makefile": "check:\n\tpytest\n"})
        r = self.run_hook(self.stop_payload(
            "Done. The suite is now 1495 tests.", cwd=proj))
        reason = self.assert_blocked(r)
        self.assertIn("make check", reason)

    def test_runner_hint_package_json_scripts_test(self):
        self.write_transcript(self.a_test_run(443))
        proj = self.project_dir(**{
            "package.json": '{"scripts": {"test": "jest"}}',
        })
        r = self.run_hook(self.stop_payload(
            "Done. The suite is now 1495 tests.", cwd=proj))
        reason = self.assert_blocked(r)
        self.assertIn("npm test", reason)

    def test_runner_hint_pyproject_toml(self):
        self.write_transcript(self.a_test_run(443))
        proj = self.project_dir(**{"pyproject.toml": "[tool.pytest.ini_options]\n"})
        r = self.run_hook(self.stop_payload(
            "Done. The suite is now 1495 tests.", cwd=proj))
        reason = self.assert_blocked(r)
        self.assertIn("pytest", reason)

    def test_runner_hint_pytest_ini(self):
        self.write_transcript(self.a_test_run(443))
        proj = self.project_dir(**{"pytest.ini": "[pytest]\n"})
        r = self.run_hook(self.stop_payload(
            "Done. The suite is now 1495 tests.", cwd=proj))
        reason = self.assert_blocked(r)
        self.assertIn("pytest", reason)

    def test_runner_hint_cargo_toml(self):
        self.write_transcript(self.a_test_run(443))
        proj = self.project_dir(**{"Cargo.toml": "[package]\nname = \"x\"\n"})
        r = self.run_hook(self.stop_payload(
            "Done. The suite is now 1495 tests.", cwd=proj))
        reason = self.assert_blocked(r)
        self.assertIn("cargo test", reason)

    def test_runner_hint_falls_back_when_nothing_detected(self):
        """A scratch project with none of the five known shapes -- this is the live
        red-team finding: "./run_tests.sh" must not appear where no such file exists."""
        self.write_transcript(self.a_test_run(443))
        proj = self.project_dir()
        r = self.run_hook(self.stop_payload(
            "Done. The suite is now 1495 tests.", cwd=proj))
        reason = self.assert_blocked(r)
        self.assertIn("the project's test command", reason)
        self.assertNotIn("./run_tests.sh", reason)
        self.assertNotIn("make test", reason)
        self.assertNotIn("npm test", reason)
        self.assertNotIn("cargo test", reason)

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

    # ------------------------------------------------- the check-runs shape (2026-09-05)
    # A real Stop block. The session followed the user's own CI note, which queries
    # `gh api .../check-runs` rather than `gh run`, and reported the result; the gate
    # answered "nothing in this session ran a test command". Both halves of that workflow
    # are pinned here, because the note is usually run through a wrapper script whose
    # COMMAND says nothing about CI and whose OUTPUT is where the evidence lives.
    CHECK_ROWS = (
        "commit cc2051b7abc1234def in ContextLab/claude-skill-compounder\n"
        "check-run\tlint (ubuntu)\tcompleted\tsuccess\thttps://github.com/o/r/runs/1\n"
        "check-run\ttests (macos)\tcompleted\tsuccess\thttps://github.com/o/r/runs/2\n"
        "status\tci/build\tsuccess\t-\thttps://github.com/o/r/statuses/3\n"
    )
    CHECK_CLAIM = "All five check-runs completed with success; CI is green for cc2051b7."

    def test_a_gh_api_check_runs_call_counts_as_a_ci_runner(self):
        self.write_transcript([
            user_prompt("is ci green"),
            tool_call("toolu_1", "gh api repos/ContextLab/claude-skill-compounder"
                                 "/commits/cc2051b7/check-runs --jq '.check_runs[]'"),
            tool_result("toolu_1", self.CHECK_ROWS),
        ])
        self.assert_silent(self.run_hook(self.stop_payload(self.CHECK_CLAIM)))

    def test_check_run_rows_count_as_a_ci_runner_whatever_ran_them(self):
        """The command is a wrapper script: only its OUTPUT can say this was a CI query."""
        self.write_transcript([
            user_prompt("is ci green"),
            tool_call("toolu_1", "bash ~/.claude/lessons/n3725829701x412/ci-checks.sh cc2051b7"),
            tool_result("toolu_1", self.CHECK_ROWS),
        ])
        self.assert_silent(self.run_hook(self.stop_payload(self.CHECK_CLAIM)))

    def test_an_unrelated_gh_api_call_is_not_a_ci_runner(self):
        """`gh api` is a general client; only the check-reporting paths count."""
        self.write_transcript([
            user_prompt("read the issue"),
            tool_call("toolu_1", "gh api repos/o/r/issues/43/comments"),
            tool_result("toolu_1", '[{"body": "hi"}]\n'),
        ])
        reason = self.assert_blocked(self.run_hook(self.stop_payload("CI is green.")))
        self.assertIn("nothing in this session ran a test command", reason)

    # ------------------------------------------------ mention versus use (2026-09-05)
    def test_a_ci_phrase_inside_double_quotes_is_a_mention(self):
        """Blocked mid-run for writing a sentence ABOUT the phrase `CI passed`."""
        self.write_transcript([
            user_prompt("what should the gate do"),
            tool_call("toolu_1", "grep -rn ci_claim hooks/claim-gate.sh"),
            tool_result("toolu_1", "hooks/claim-gate.sh:695:ci_claim_re=...\n"),
        ])
        self.assert_silent(self.run_hook(self.stop_payload(
            'The hard part is that there is no universal rule for what counts as '
            '"CI passed," so I read the rows by hand.')))

    def test_a_negated_ci_claim_is_a_mention(self):
        """Same sentence, no quotes: `no ... CI passed` asserts nothing about any run."""
        self.write_transcript([
            user_prompt("what should the gate do"),
            tool_call("toolu_1", "grep -rn ci_claim hooks/claim-gate.sh"),
            tool_result("toolu_1", "hooks/claim-gate.sh:695:ci_claim_re=...\n"),
        ])
        for msg in ("There is no agreed definition of what counts as CI passed.",
                    "I did not check whether CI is green on that commit.",
                    "Nothing here decides whether all checks passed."):
            self.assert_silent(self.run_hook(
                self.stop_payload(msg, prompt="p-" + msg[:12])))

    def test_a_plain_ci_claim_with_no_runner_still_blocks(self):
        """The exemptions are narrow: an unhedged claim with nothing behind it blocks."""
        self.write_transcript([
            user_prompt("fix the bug"),
            tool_call("toolu_1", "grep -rn foo src"),
            tool_result("toolu_1", "src/a.py:1:foo\n"),
        ])
        reason = self.assert_blocked(self.run_hook(self.stop_payload("CI passed.")))
        self.assertIn("nothing in this session ran a test command", reason)

    def test_a_negation_in_an_earlier_sentence_does_not_excuse_a_later_claim(self):
        """`[^.!?]*` keeps the exclusion inside one sentence, and this is what pins it."""
        self.write_transcript([
            user_prompt("fix the bug"),
            tool_call("toolu_1", "grep -rn foo src"),
            tool_result("toolu_1", "src/a.py:1:foo\n"),
        ])
        reason = self.assert_blocked(self.run_hook(self.stop_payload(
            "I did not touch the workflow file. CI passed.")))
        self.assertIn("nothing in this session ran a test command", reason)

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

    # ============================================ heredocs (2026-08-26 red team, #1)
    def test_an_unrelated_heredoc_is_not_read_as_the_commit_message(self):
        """The reviewer's repro, verbatim in shape: a document written with a heredoc,
        then a commit whose message carries no figure at all. Capture used to begin at
        the first `<<` and never stop, so the DOCUMENT BODY was judged as the commit
        message and the commit was denied on the benchmark numbers inside it.

        The figures are chosen to survive every other Tier-1 rule -- not round, not
        powers of two, no unit after them -- so the only thing that can make this pass
        is the heredoc being bounded by its own delimiter.
        """
        self.write_transcript(self.a_test_run(443))
        cmd = ("cat > notes/log.md <<'EOF'\n"
               "Benchmark: 4823 requests, buffer 6197 slots\n"
               "EOF\n"
               'git commit -m "add note"')
        self.assert_silent(self.run_hook(self.pre_payload(cmd)))

    def test_a_heredoc_feeding_git_commit_dash_F_is_read(self):
        """`git commit -F - <<'MSG'` is the other real form and must still be judged."""
        self.write_transcript(self.a_test_run(443))
        cmd = "git commit -F - <<'MSG'\nShip it\n\n1495 tests across 27 files\nMSG"
        self.assertIn("1495", self.assert_denied(self.run_hook(self.pre_payload(cmd))))

    def test_only_the_commit_heredoc_is_read_when_a_command_has_two(self):
        """One command, two heredocs: a note and the commit message. Exactly one of them
        is the claim under test."""
        self.write_transcript(self.a_test_run(443))
        cmd = ("cat > notes/log.md <<'DOC'\n"
               "Benchmark: 4823 requests, buffer 6197 slots\n"
               "DOC\n"
               "git commit -F - <<'MSG'\n"
               "Ship it: 7331 assertions\n"
               "MSG")
        reason = self.assert_denied(self.run_hook(self.pre_payload(cmd)))
        self.assertIn("7331", reason)
        self.assertNotIn("4823", reason)
        self.assertNotIn("6197", reason)

    def test_a_dash_m_inside_an_unrelated_heredoc_body_is_not_the_message(self):
        """Quoted shell inside a document is text, not the command being run."""
        self.write_transcript(self.a_test_run(443))
        cmd = ("cat > notes/log.md <<'EOF'\n"
               'Yesterday I ran git commit -m "9911 assertions" by hand.\n'
               "EOF\n"
               'git commit -m "tidy the note"')
        self.assert_silent(self.run_hook(self.pre_payload(cmd)))

    def test_a_here_string_does_not_open_a_heredoc(self):
        """`<<<` is a here-STRING with no body; mistaking it for a heredoc swallows the
        rest of the command."""
        self.write_transcript(self.a_test_run(443))
        cmd = ('grep -c x <<<"$BODY"\n'
               'git commit -m "note 4823 requests"')
        self.assertIn("4823", self.assert_denied(self.run_hook(self.pre_payload(cmd))))

    # ==================================== the read budget (2026-08-26 red team, #2)
    def _padded_transcript(self, head_records, pad_bytes):
        """head_records, then enough filler to push them out of a small read window.
        Filler carries no figure of its own."""
        recs = list(head_records)
        filler = "ok " * 400
        n = max(1, pad_bytes // len(filler))
        for i in range(n):
            recs.append(tool_result("toolu_pad%d" % i, filler))
        self.write_transcript(recs)

    def test_the_read_budget_is_actually_enforced(self):
        """MAX_BYTES was dead code on every BSD box: `wc -c < file` prints a leading
        space, the numeric guard read that as non-numeric and zeroed the size, and the
        whole transcript was parsed however large it was.

        Here the ONLY support for the figure sits before the window, so an enforced
        budget must not find it. This asserts the window exists -- the false positive it
        can cause is the documented cost of bounding the work.
        """
        recs = self.a_test_run(443)
        recs.append(tool_result("toolu_e", "the run produced 8675309 rows\n"))
        self._padded_transcript(recs, 200000)
        r = self.run_hook(self.stop_payload("The run produced 8675309 rows."),
                          CLAIM_GATE_MAX_BYTES=20000)
        self.assertIn("8675309", self.assert_blocked(r))

    def test_evidence_inside_the_window_is_still_found(self):
        """The other half of the same rule: a bounded window is not a broken one."""
        recs = self.a_test_run(443)
        self._padded_transcript(recs, 200000)
        recs2 = []
        with open(self.transcript, encoding="utf-8") as fh:
            recs2 = [json.loads(l) for l in fh]
        recs2.append(tool_result("toolu_last", "the run produced 8675309 rows\n"))
        self.write_transcript(recs2)
        self.assert_silent(self.run_hook(
            self.stop_payload("The run produced 8675309 rows."),
            CLAIM_GATE_MAX_BYTES=20000))

    def test_the_work_does_not_grow_with_the_transcript(self):
        """Bounded work, measured rather than asserted: with the budget pinned, a
        transcript 16x larger must not cost 16x more. Unbounded, the same pair was ~9x
        apart on the machine this was written on (0.33 s at 2 MB, 3.02 s at 32 MB), and
        a 695 MB session took 33.3 s against a `timeout 10`.

        A RATIO, not a wall-clock ceiling: it cancels how fast the machine is.
        """
        import time
        budget = 1048576
        elapsed = {}
        for mb in (2, 32):
            self._padded_transcript(self.a_test_run(443), mb * 1024 * 1024)
            p = self.stop_payload("Nothing to see here.", prompt="p-size%d" % mb)
            t0 = time.time()
            self.run_hook(p, CLAIM_GATE_MAX_BYTES=budget)
            elapsed[mb] = time.time() - t0
        self.assertLess(elapsed[32], elapsed[2] * 4 + 1.0,
                        "work scaled with the transcript, not with the budget: %r"
                        % elapsed)

    def test_truncation_does_not_let_tier2_claim_nothing_ran(self):
        """"Nothing ran in this session" is a statement about what the hook could SEE.
        With the window cutting off the run, that sentence is not true of the session,
        and a gate that blocks when it cannot see blocks at random."""
        self._padded_transcript(self.a_test_run(443), 200000)
        self.assert_silent(self.run_hook(self.stop_payload("All tests pass."),
                                         CLAIM_GATE_MAX_BYTES=20000))

    # ================================== tier 2, the CI arm (2026-08-26 red team, #3)
    def a_ci_run(self):
        return [
            user_prompt("check ci"),
            tool_call("toolu_c", "gh pr checks 129"),
            tool_result("toolu_c", "All checks were successful\n11 successful checks\n"),
        ]

    def test_a_ci_green_claim_does_not_go_stale_when_files_change_after(self):
        """A CI result is pinned to the commit SHA it ran on. Editing the working tree
        afterwards cannot change what the checks did on that commit, so the staleness
        question -- which is about the tree in front of you -- does not apply."""
        recs = self.a_ci_run()
        recs.append(file_write("toolu_w", "/repo/skill_compounder/installer.py"))
        recs.append(tool_result("toolu_w", "ok"))
        self.write_transcript(recs)
        self.assert_silent(self.run_hook(
            self.stop_payload("CI green across 11 checks on the pushed commit.")))

    def test_a_local_suite_claim_beside_a_ci_claim_is_still_checked(self):
        """The exemption covers the CI half of a sentence, not the other half: "all
        tests pass" IS about the current tree, so the edit still stales it."""
        recs = self.a_test_run(443) + self.a_ci_run()[1:]
        recs.append(file_write("toolu_w", "/repo/skill_compounder/installer.py"))
        recs.append(tool_result("toolu_w", "ok"))
        self.write_transcript(recs)
        reason = self.assert_blocked(self.run_hook(
            self.stop_payload("All tests pass and CI is green.")))
        self.assertIn("AFTER the last test run", reason)

    def test_a_ci_claim_with_no_ci_query_anywhere_still_blocks(self):
        """The exemption needs a CI query to have happened. Asserting CI is green with
        nothing in the session having asked CI anything is the original defect."""
        self.write_transcript([
            user_prompt("ship it"),
            tool_call("toolu_1", "git push"),
            tool_result("toolu_1", "Everything up-to-date\n"),
        ])
        reason = self.assert_blocked(self.run_hook(
            self.stop_payload("CI is green on the pushed commit.")))
        self.assertIn("nothing in this session ran a test command", reason)

    # ============================ tier 2, mention versus use (2026-08-26 red team, #3)
    def test_prose_about_testing_is_not_a_claim_that_a_suite_passed(self):
        """Both sentences are real, off real closing messages, and both fired Tier 2.
        Neither asserts that anything passed: one is a generalisation about mocks, the
        other a conditional about what a passing test would mean."""
        self.write_transcript([
            user_prompt("write up the decision"),
            tool_call("toolu_1", "cat README.md"),
            tool_result("toolu_1", "prose\n"),
        ])
        for i, msg in enumerate((
                "Mock-based testing creates a false sense of security. When tests pass "
                "against mocks but fail against real APIs, we have shipped bugs.",
                "An unmatched baseline would let the discrimination test pass trivially "
                "by detecting journal formatting instead of your voice.",
                "The slowdown is worth the guarantee: if the test passes, the code works "
                "against the actual service.")):
            self.assert_silent(self.run_hook(
                self.stop_payload(msg, prompt="p-prose%d" % i)))

    def test_a_determiner_or_a_count_still_makes_it_a_suite_claim(self):
        """The anchor must not have retired the check it is anchoring."""
        self.write_transcript([
            user_prompt("fix it"),
            tool_call("toolu_1", "grep -rn foo src"),
            tool_result("toolu_1", "src/a.py:1:foo\n"),
        ])
        for i, msg in enumerate(("The tests pass on this tree.",
                                 "Fixed it, and the whole suite is green.",
                                 "Tests pass now.")):
            reason = self.assert_blocked(self.run_hook(
                self.stop_payload(msg, prompt="p-claim%d" % i)))
            self.assertIn("nothing in this session ran a test command", reason)

    # =============================== tier 1, named constants (2026-08-26 red team, #3)
    def test_a_spaced_magnitude_unit_is_not_a_measured_count(self):
        """`2KB` was already exempt and `512 MB` was not, which is the same figure with
        a space in it. The list is units only -- see the guard test below."""
        self.write_transcript(self.a_test_run(443))
        msg = ("The artefact is 512 MB, the p99 is 250 ms, throughput held at 4823 rps "
               "and the header is 8447 bytes.")
        self.assert_silent(self.run_hook(self.stop_payload(msg)))

    def test_a_file_mode_is_not_a_count(self):
        """A leading zero means octal. The old code stripped the zero and manufactured a
        count of 644 out of `umask 0644` -- measured on a real closing message."""
        self.write_transcript(self.a_test_run(443))
        msg = "The key is saved world-readable (umask 0644) and the dir is 0755."
        self.assert_silent(self.run_hook(self.stop_payload(msg)))

    def test_round_and_power_of_two_constants_are_not_counts(self):
        """Budgets, limits, buffer and cache sizes. Same argument the powers-of-ten rule
        already makes: a real measurement almost never lands on one."""
        self.write_transcript(self.a_test_run(443))
        msg = ("Rationale (300 words): the cache holds 4096 entries, the file is 3400 "
               "lines, the limit is 1024 and the buffer is 8192.")
        self.assert_silent(self.run_hook(self.stop_payload(msg)))

    def test_the_widening_did_not_retire_tier_1(self):
        """THE GUARD. Every figure here is the shape the founding defect took, and each
        one must still be caught after the exemptions above. If a future widening makes
        this test silent, the widening went too far."""
        self.write_transcript(self.a_test_run(443))
        for i, (msg, num) in enumerate((
                ("The suite is now 1495 tests.", "1495"),
                ("Measured across 21926 words of prose.", "21926"),
                ("The scrub touched 1,847 records.", "1847"),
                ("That is 8675309 rows in the export.", "8675309"))):
            reason = self.assert_blocked(self.run_hook(
                self.stop_payload(msg, prompt="p-guard%d" % i)))
            self.assertIn(num, reason)

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
