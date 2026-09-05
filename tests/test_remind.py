#!/usr/bin/env python3
"""Tests for hooks/remind.sh -- the reminder store's delivery hook.

NO MOCKS, per this repo's standing rule. Every test writes a real `reminders.jsonl`, runs
the real shell script through subprocess with a minimal PATH, a HOME inside a temp
directory and SKILL_COMPOUNDER_STATE pinned there, feeds it a real payload on stdin, and
reads the emit and the state directory back off disk.

THE ROWS ARE HAND-WRITTEN HERE, DELIBERATELY. `bin/skillnote add --remind` is what writes
them in production and it is developed in parallel with this hook; a test that called it
would be testing two things at once and would go red for reasons that are not this
script's. The row shape below is the one notes/2026-09-02-tiers-design.md fixes, and it is
the contract between the two.

THE ONE EXCEPTION IS THE COMMAND ARM, and it is the point of that arm's tests. A command
rule is matched by BYTE EQUALITY against a normalised signature, and the normaliser is
hooks/repeat-gate.sh. So those fixtures are built by running `repeat-gate.sh --norm-of
Bash` for real: if the two ever stopped sharing one implementation, a hand-written
signature would keep passing while production stopped matching.

EVERY subprocess call against the hook passes `input=`. The script reads its payload with
`payload="$(cat)"`; without stdin it hangs forever.

The clock is pinned with REMIND_NOW -- the hook's own. Pinning another script's clock does
nothing to this one.
"""

import json
import os
import shutil
import subprocess
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "remind.sh")
NORMALISER = os.path.join(REPO, "hooks", "repeat-gate.sh")

# Minimal, explicit environment: the scripts must not depend on the ambient one.
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"

PROJECT = "/repo"


def norm_of(command):
    """The signature the repeat gate would compute for `command`.

    Called for real, so a fixture cannot drift away from the production normaliser.
    """
    p = subprocess.run(["bash", NORMALISER, "--norm-of", "Bash"], input=command,
                       capture_output=True, text=True,
                       env={"PATH": BASE_PATH, "HOME": "/tmp"}, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


class RemindCase(unittest.TestCase):
    """Shared harness: one temp state root per test, the real script, real payloads."""

    def setUp(self):
        self.tmp = os.path.join(
            os.environ.get("TMPDIR", "/tmp"),
            "remind-%d-%d" % (os.getpid(), int(time.time() * 1e6) % 10 ** 9))
        os.makedirs(self.tmp)
        self.home = os.path.join(self.tmp, "home")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.home)
        os.makedirs(self.state)
        self.clock = 1_756_900_000          # 2025-09-03T11:46:40Z

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------- plumbing
    @property
    def store(self):
        return os.path.join(self.state, "reminders.jsonl")

    @property
    def hits(self):
        return os.path.join(self.state, "remind", "hits.jsonl")

    def env(self, **extra):
        e = {"PATH": BASE_PATH, "HOME": self.home,
             "SKILL_COMPOUNDER_STATE": self.state,
             "REMIND_NOW": str(self.clock)}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def run_hook(self, payload, hook=None, **env_extra):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(["bash", hook or HOOK], input=body, capture_output=True,
                              text=True, env=self.env(**env_extra), timeout=180)

    def write_rows(self, *rows):
        with open(self.store, "a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def row(self, rid, text, keywords=(), paths=(), commands=(), scope=PROJECT,
            created=None, source="session"):
        """A row in exactly the shape the design fixes for <state>/reminders.jsonl."""
        return {"id": rid, "text": text,
                "match": {"keywords": list(keywords), "paths": list(paths),
                          "commands": list(commands)},
                "scope": scope, "created": created if created is not None else 1_756_838_400,
                "source": source, "hits": 0}

    def tombstone(self, rid, ts=None):
        return {"id": rid, "t": "remove", "ts": ts if ts is not None else self.clock}

    # ------------------------------------------------------------------- payloads
    def prompt(self, text, session="s1", pid=None, cwd=PROJECT, **over):
        p = {"hook_event_name": "UserPromptSubmit", "session_id": session,
             "prompt_id": pid or ("p_%s" % session), "cwd": cwd,
             "transcript_path": os.path.join(self.tmp, "t.jsonl"), "prompt": text}
        p.update(over)
        return p

    def bash(self, command, session="s1", tuid=None, cwd=PROJECT, **over):
        p = {"hook_event_name": "PreToolUse", "session_id": session,
             "tool_use_id": tuid or ("toolu_%s" % session), "cwd": cwd,
             "transcript_path": os.path.join(self.tmp, "t.jsonl"),
             "permission_mode": "acceptEdits", "tool_name": "Bash",
             "tool_input": {"command": command, "description": "d"}}
        p.update(over)
        return p

    def write(self, file_path, session="s1", tuid=None, cwd=PROJECT, tool="Write", **over):
        p = {"hook_event_name": "PreToolUse", "session_id": session,
             "tool_use_id": tuid or ("toolu_%s" % session), "cwd": cwd,
             "transcript_path": os.path.join(self.tmp, "t.jsonl"),
             "permission_mode": "acceptEdits", "tool_name": tool,
             "tool_input": {"file_path": file_path, "content": "x"}}
        p.update(over)
        return p

    # ------------------------------------------------------------------- assertions
    def assert_silent(self, r):
        self.assertEqual(r.returncode, 0, "a hook must never exit non-zero: " + r.stderr)
        self.assertEqual(r.stdout.strip(), "",
                         "the hook spoke when it should have been silent: %r" % r.stdout)
        return r

    def context_of(self, r, event="UserPromptSubmit"):
        """The emitted additionalContext, with the shape checked on the way through."""
        self.assertEqual(r.returncode, 0, "a hook must never exit non-zero: " + r.stderr)
        self.assertTrue(r.stdout.strip(), "expected a reminder, got silence")
        d = json.loads(r.stdout)
        self.assertIs(d["suppressOutput"], True)
        hso = d["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], event)
        # The MEASURED field. `permissionDecision:"allow"` with a reason reaches nothing
        # (0 of 6 runs, docs/CLAUDE-CODE-BEHAVIOR.md), so its presence here would mean the
        # hook had silently stopped saying anything to anyone.
        self.assertNotIn("permissionDecision", hso)
        return hso["additionalContext"]

    def hit_rows(self):
        if not os.path.exists(self.hits):
            return []
        return [json.loads(l) for l in open(self.hits, encoding="utf-8") if l.strip()]


# ==================================================================== the keyword arm
class KeywordTest(RemindCase):
    """AND, not OR. A rule with two keywords fires only when the prompt carries both.

    OR would make a two-word rule fire on either word, which is how a reminder becomes
    noise: one that arrives when it does not apply teaches the reader to skip the next one.
    """

    def setUp(self):
        super().setUp()
        self.write_rows(self.row("n1x1", "Kill the runner and re-run the full suite.",
                                 keywords=["test", "fail"]))

    def test_both_keywords_present_fires(self):
        ctx = self.context_of(self.run_hook(self.prompt("the test keeps failing here")))
        self.assertIn("Kill the runner", ctx)

    def test_one_keyword_is_not_enough(self):
        self.assert_silent(self.run_hook(self.prompt("the test passed cleanly")))

    def test_neither_keyword_is_silent(self):
        self.assert_silent(self.run_hook(self.prompt("please rename this function")))

    def test_matching_is_case_insensitive_on_the_prompt(self):
        ctx = self.context_of(self.run_hook(self.prompt("The TEST keeps FAILING")))
        self.assertIn("Kill the runner", ctx)

    def test_a_keyword_matches_inside_a_longer_word(self):
        """Substring containment, stated so it is a decision rather than an accident:
        `fail` matches `failing`. Word-boundary matching would miss every inflection."""
        ctx = self.context_of(self.run_hook(self.prompt("tests are failing")))
        self.assertIn("Kill the runner", ctx)

    def test_a_row_with_no_keywords_never_matches_a_prompt(self):
        self.write_rows(self.row("n2x2", "A path-only rule.", paths=["*.py"]))
        ctx = self.context_of(self.run_hook(self.prompt("the test keeps failing")))
        self.assertNotIn("path-only", ctx)

    def test_the_frame_is_a_statement_of_fact_not_an_instruction(self):
        """Measured: the same field with imperative wording was refused as prompt
        injection in 2 of 4 runs, and accepted 3 of 3 when it read as a report
        (docs/CLAUDE-CODE-BEHAVIOR.md, CLI 2.1.258). The frame is what makes the text a
        report even when the reminder itself is written as an order."""
        ctx = self.context_of(self.run_hook(self.prompt("the test keeps failing")))
        self.assertTrue(ctx.startswith("Reminder recorded on 2025-09-02 for this project: "),
                        "unexpected frame: %r" % ctx)


# ==================================================================== the command arm
class CommandTest(RemindCase):
    """Byte equality against a NORMALISED signature, and the normaliser is shared.

    The whole value of this arm is that `gh issue comment 19 --body "x"` and
    `gh issue comment 4271 --body "quite another message"` are ONE call. Nothing here
    reimplements that judgement: the fixture is built by running the repeat gate's own
    `--norm-of`, so a second implementation appearing in remind.sh would fail these.
    """

    def setUp(self):
        super().setUp()
        self.sig = norm_of('gh issue comment 19 --body "first draft"')
        self.write_rows(self.row("n3x3", "gh issue comment needs the body in a file.",
                                 commands=[self.sig], scope="global"))

    def test_the_signature_really_is_normalised(self):
        """Guards the two tests below: if --norm-of started echoing its input, they would
        both still pass while proving nothing."""
        self.assertNotIn("first draft", self.sig)
        self.assertNotIn("19", self.sig)
        self.assertIn("gh issue comment", self.sig)

    def test_a_different_literal_of_the_same_call_fires(self):
        ctx = self.context_of(
            self.run_hook(self.bash('gh issue comment 4271 --body "quite another message"')),
            event="PreToolUse")
        self.assertIn("body in a file", ctx)

    def test_a_genuinely_different_command_does_not(self):
        self.assert_silent(self.run_hook(self.bash("gh pr list")))

    def test_the_stored_signature_is_not_matched_as_a_literal(self):
        """The rule holds a signature, not a command. A payload whose command IS the
        signature text must not be what makes the arm look like it works."""
        r = self.run_hook(self.bash("true # unrelated"))
        self.assert_silent(r)

    def test_without_the_normaliser_command_matching_is_skipped_not_guessed(self):
        """`remind.sh` calls repeat-gate.sh beside it. In a checkout without that script
        an approximate signature would match the WRONG reminders, so the arm goes quiet
        instead -- and the other arms keep working, which is what this checks."""
        lone = os.path.join(self.tmp, "hooks")
        os.makedirs(lone)
        copy = os.path.join(lone, "remind.sh")
        shutil.copy(HOOK, copy)
        self.write_rows(self.row("n4x4", "A keyword rule.", keywords=["hello"]))
        self.assert_silent(
            self.run_hook(self.bash('gh issue comment 7 --body "x"'), hook=copy))
        ctx = self.context_of(self.run_hook(self.prompt("hello there"), hook=copy))
        self.assertIn("A keyword rule", ctx)

    def test_the_repeat_gates_off_switch_does_not_disable_command_matching(self):
        """Two scripts, two switches. Turning the repeat gate off must not silently stop a
        reminder firing, which is what happened while `--norm-of` sat behind that gate's
        own off switch and returned nothing."""
        ctx = self.context_of(
            self.run_hook(self.bash('gh issue comment 8 --body "y"'),
                          SKILL_COMPOUNDER_REPEAT_GATE="0"),
            event="PreToolUse")
        self.assertIn("body in a file", ctx)

    def test_a_command_rule_does_not_fire_on_a_prompt(self):
        self.assert_silent(self.run_hook(self.prompt("gh issue comment 19 --body x")))


# ==================================================================== the segment split
class SegmentTest(RemindCase):
    """A rule is keyed on ONE call; a session types that call inside a compound one.

    Measured against the installed package on 2026-09-05: a lesson keyed on
    `python3 setup.py install` fired for that command alone and said NOTHING for
    `cd build && python3 setup.py install`, `ls; echo hi; python3 setup.py install` or
    `python3 setup.py install 2>&1` -- and the compound form is the one a session actually
    types, so the reminder was silent exactly when it was needed. The command is now split
    the way hooks/repeat-gate.sh splits one and every segment is normalised.

    The fixtures are built by running the real `--norm-of`, like every other command test
    here: a hand-typed signature would keep passing on the day production stopped matching.
    """

    CMD = "python3 setup.py install"

    def setUp(self):
        super().setUp()
        self.sig = norm_of(self.CMD)
        self.write_rows(self.row("nseg1", "setuptools is missing here; pip install -e . works.",
                                 commands=[self.sig], scope="global"))

    def fires(self, command, session):
        return self.context_of(self.run_hook(self.bash(command, session=session)),
                               event="PreToolUse")

    def test_the_bare_command_still_fires(self):
        """The case that already worked. Everything below is an ADDITION to it."""
        self.assertIn("pip install -e .", self.fires(self.CMD, "s-bare"))

    def test_a_leading_cd_does_not_silence_it(self):
        self.assertIn("pip install -e .",
                      self.fires("cd build && " + self.CMD, "s-cd"))

    def test_a_semicolon_run_up_does_not_silence_it(self):
        self.assertIn("pip install -e .",
                      self.fires("ls; echo hi; " + self.CMD, "s-semi"))

    def test_a_trailing_redirection_does_not_silence_it(self):
        """`2>&1` is not a separator, so this is ONE segment -- and the normaliser MASKS a
        redirection rather than dropping it (`... 2>&1` -> `... <N>>&<N>`), so the segment
        alone does not answer it. `strip_redirs` peels it off as an extra candidate."""
        self.assertIn("pip install -e .", self.fires(self.CMD + " 2>&1", "s-redir"))

    def test_a_redirection_to_a_file_does_not_silence_it_either(self):
        self.assertIn("pip install -e .",
                      self.fires(self.CMD + " > out.log 2>&1", "s-file"))
        self.assertIn("pip install -e .",
                      self.fires(self.CMD + " >out.log", "s-glued"))

    def test_a_pipeline_stage_matches(self):
        self.assertIn("pip install -e .",
                      self.fires(self.CMD + " | tail -20", "s-pipe"))

    def test_every_compound_form_together(self):
        """One assertion per shape is easy to read and easy to leave a hole in. This is the
        list, driven in one place, so a shape cannot be dropped by deleting a method."""
        for i, cmd in enumerate((
                "cd build && " + self.CMD,
                "cd build; " + self.CMD,
                self.CMD + " && echo done",
                self.CMD + " || echo failed",
                "ls; echo hi; " + self.CMD,
                self.CMD + " 2>&1 | tail -5",
                "set -e; cd build && " + self.CMD + " 2>&1")):
            self.assertIn("pip install -e .", self.fires(cmd, "s-all%d" % i),
                          "silent on %r" % cmd)

    def test_a_segment_that_merely_contains_the_signature_is_silent(self):
        """The rule holds a signature and the match is BYTE EQUALITY of a normalised
        segment. A command that quotes the signature, or extends it, is a different call
        and must stay silent -- otherwise the split would have traded one silence for a
        reminder that arrives when it does not apply, which teaches the reader to skip the
        next one."""
        for i, cmd in enumerate(('echo "%s"' % self.CMD,
                                 "echo %s >> notes.txt" % self.CMD,
                                 'git commit -m "%s"' % self.CMD,
                                 self.CMD + "-extra",
                                 "python3 setup.py installx")):
            self.assert_silent(self.run_hook(self.bash(cmd, session="s-sub%d" % i)))

    def test_a_genuinely_different_compound_is_still_silent(self):
        self.assert_silent(self.run_hook(self.bash("cd build && make all")))

    def test_a_rule_keyed_on_a_compound_command_still_fires(self):
        """The whole command is candidate ONE, so a rule written against a compound call
        keeps working: nothing that fired before this change can stop firing."""
        compound = "cd /tmp/forge && python3 setup.py install 2>&1 | tail -20"
        self.write_rows(self.row("nseg2", "The compound rule.",
                                 commands=[norm_of(compound)], scope="global"))
        self.assertIn("The compound rule", self.fires(compound, "s-comp"))

    def test_two_segments_matching_one_rule_deliver_it_once(self):
        cmd = "%s && %s" % (self.CMD, self.CMD)
        ctx = self.fires(cmd, "s-twice")
        self.assertEqual(ctx.count("pip install -e ."), 1, ctx)
        self.assertEqual(len(self.hit_rows()), 1, self.hit_rows())

    def test_a_command_the_splitter_cannot_model_falls_back_to_the_whole_command(self):
        """`split_segments` FAILS on an unterminated quote beside a separator, and the
        fallback here is the whole command -- never no matching at all. A rule keyed on
        such a command therefore still fires, which is what this drives."""
        weird = "echo 'unclosed && " + self.CMD
        self.write_rows(self.row("nseg3", "The unmodellable rule.",
                                 commands=[norm_of(weird)], scope="global"))
        self.assertIn("The unmodellable rule", self.fires(weird, "s-weird"))

    def test_the_cap_keeps_the_whole_command_first(self):
        """MAX_CANDIDATES bounds the forks. The whole command is candidate one, so a
        command with more segments than the cap still matches a rule keyed on all of it."""
        long_cmd = "; ".join("echo %d" % i for i in range(12)) + "; " + self.CMD
        self.write_rows(self.row("nseg4", "The long rule.",
                                 commands=[norm_of(long_cmd)], scope="global"))
        self.assertIn("The long rule", self.fires(long_cmd, "s-long"))


class SegmentCostGateTest(RemindCase):
    """Nothing is normalised unless the store holds a command rule, and that is what pays
    for the split. A store of keyword rules -- which is every store until someone writes a
    lesson -- now costs no fork at all on a Bash call, where it used to fork the normaliser
    on every one.

    Both JSON spellings have to be recognised: `bin/skillnote` writes `"commands":[...]`
    through `jq -c`, and every hand-written row here writes `"commands": [...]`.
    """

    def test_a_keyword_only_store_still_answers_a_prompt(self):
        self.write_rows(self.row("nk", "A keyword rule.", keywords=["widget"]))
        self.assertIn("A keyword rule", self.context_of(self.run_hook(self.prompt("widget"))))

    def test_a_keyword_only_store_is_silent_on_a_bash_call(self):
        self.write_rows(self.row("nk", "A keyword rule.", keywords=["widget"]))
        self.assert_silent(self.run_hook(self.bash("python3 setup.py install")))

    def test_an_empty_commands_array_does_not_open_the_gate(self):
        """Non-vacuity for the test below: `"commands": []` must NOT read as a rule."""
        self.write_rows(self.row("nk", "A keyword rule.", keywords=["widget"], commands=[]))
        self.assert_silent(self.run_hook(self.bash("python3 setup.py install")))

    def test_the_jq_written_spelling_opens_it(self):
        """The writer in production is `jq -c`, which emits no space after the colon. A
        gate that only recognised the hand-written spelling would be silent for every row
        bin/skillnote ever wrote -- the exact shape of the 2026-09-02 defect."""
        sig = norm_of("python3 setup.py install")
        with open(self.store, "a", encoding="utf-8") as fh:
            fh.write('{"id":"njq","text":"The compact rule.","match":{"keywords":[],'
                     '"paths":[],"commands":["%s"]},"scope":"global","created":1756838400,'
                     '"hits":0}\n' % sig)
        ctx = self.context_of(self.run_hook(self.bash("cd build && python3 setup.py install")),
                              event="PreToolUse")
        self.assertIn("The compact rule", ctx)


class SplitterSyncTest(unittest.TestCase):
    """`split_segments` lives in hooks/repeat-gate.sh and is COPIED into hooks/remind.sh.

    That gate exposes `--norm-of` and `--eligible-of` but no door onto the split itself,
    and this hook cannot open one, so the copy is pinned instead of wished about: two
    implementations of one rule drift, and the drift is invisible from either side -- a
    reminder that quietly stops matching a shape the gate still splits. If a door ever
    lands, delete the copy and call it; until then this test is the thing that notices.
    """

    def extract(self, path):
        keep, inside = [], False
        for line in open(path, encoding="utf-8"):
            if line.rstrip("\n") == "split_segments() {":
                inside = True
            if inside:
                keep.append(line)
                if line.rstrip("\n") == "}":
                    break
        self.assertTrue(keep, "no split_segments() in %s" % path)
        self.assertEqual(keep[-1].rstrip("\n"), "}", "unterminated split_segments in %s" % path)
        return "".join(keep)

    def test_the_two_copies_are_byte_identical(self):
        gate = self.extract(NORMALISER)
        hook = self.extract(HOOK)
        self.assertEqual(gate, hook,
                         "hooks/remind.sh's copy of split_segments has drifted from "
                         "hooks/repeat-gate.sh's. Re-copy the function verbatim -- the "
                         "hook matches command reminders per segment and a splitter that "
                         "disagrees with the gate's matches a different set of calls.")

    def test_the_extraction_is_not_vacuous(self):
        """Both halves must really have been found, or the comparison above proves
        nothing: two empty strings are equal."""
        self.assertGreater(len(self.extract(NORMALISER).splitlines()), 40)
        self.assertIn("SEGS=", self.extract(HOOK))


# ==================================================================== the path arm
class WriterReaderTest(RemindCase):
    """The row is written by the REAL `skillnote add --remind --command`, through a
    symlink the way the installer links it, and read by the real hook.

    Every other command test here hand-writes its row, which is how two shipped bugs got
    past the suite on 2026-09-02: the installed symlink could not find repeat-gate.sh, and
    skillnote stored `Bash\\n<sig>` while remind.sh compared the bare signature, so every
    command-keyed reminder was silent in a real session. This test drives both halves.
    """

    def test_a_command_reminder_written_by_skillnote_fires_in_the_hook(self):
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        link = os.path.join(bindir, "skillnote")
        os.symlink(os.path.join(REPO, "bin", "skillnote"), link)
        w = subprocess.run([link, "add", "--remind", "--scope", "global",
                            "--command", "make deploy",
                            "Deploys go through make deploy, which runs the preflight."],
                           capture_output=True, text=True, timeout=120,
                           env=dict(self.env(), SKILLNOTE_NOW="1756838400"))
        self.assertEqual(w.returncode, 0, w.stdout + w.stderr)
        with open(self.store, encoding="utf-8") as fh:
            row = json.loads(fh.readline())
        self.assertEqual(row["match"]["commands"], [norm_of("make deploy")],
                         "the writer must store exactly what --norm-of prints")
        ctx = self.context_of(self.run_hook(self.bash("make deploy")), event="PreToolUse")
        self.assertIn("runs the preflight", ctx)


class PathTest(RemindCase):

    def setUp(self):
        super().setUp()
        self.write_rows(self.row("n5x5", "Check which tests pin a skill's prose.",
                                 paths=["tests/*.py"]))

    def test_a_relative_glob_matches_a_path_under_the_scope(self):
        ctx = self.context_of(self.run_hook(self.write("/repo/tests/test_x.py")),
                              event="PreToolUse")
        self.assertIn("pin a skill's prose", ctx)

    def test_edit_fires_it_as_well_as_write(self):
        ctx = self.context_of(self.run_hook(self.write("/repo/tests/test_x.py", tool="Edit")),
                              event="PreToolUse")
        self.assertIn("pin a skill's prose", ctx)

    def test_a_path_outside_the_glob_is_silent(self):
        self.assert_silent(self.run_hook(self.write("/repo/hooks/remind.sh")))

    def test_an_absolute_glob_matches_the_absolute_path(self):
        self.write_rows(self.row("n6x6", "An absolute rule.", paths=["/repo/bin/*"]))
        ctx = self.context_of(self.run_hook(self.write("/repo/bin/skillnote")),
                              event="PreToolUse")
        self.assertIn("An absolute rule", ctx)

    def test_a_glob_is_a_glob_and_not_a_substring(self):
        """`tests/*.py` must not match `tests/data/x.py.bak`; the pattern is anchored at
        both ends by `case`."""
        self.assert_silent(self.run_hook(self.write("/repo/tests/test_x.py.bak")))

    def test_a_bash_call_does_not_go_through_the_path_arm(self):
        self.assert_silent(self.run_hook(self.bash("cat /repo/tests/test_x.py")))

    def test_a_tool_we_are_not_wired_for_is_silent(self):
        self.assert_silent(self.run_hook(self.write("/repo/tests/test_x.py", tool="Read")))


# ==================================================================== scope
class ScopeTest(RemindCase):
    """Scope is checked first, and it is a directory containment test rather than a
    prefix test: `/repo-other` starts with `/repo` and is a different project."""

    def setUp(self):
        super().setUp()
        self.write_rows(
            self.row("n7x7", "A project rule.", keywords=["alpha"], scope=PROJECT),
            self.row("n8x8", "A global rule.", keywords=["alpha"], scope="global"))

    def test_inside_the_scope_both_fire(self):
        ctx = self.context_of(self.run_hook(self.prompt("alpha", cwd=PROJECT)))
        self.assertIn("A project rule", ctx)
        self.assertIn("A global rule", ctx)

    def test_a_subdirectory_is_inside_the_scope(self):
        ctx = self.context_of(self.run_hook(self.prompt("alpha", cwd="/repo/tests/deep")))
        self.assertIn("A project rule", ctx)

    def test_a_sibling_project_gets_only_the_global_rule(self):
        ctx = self.context_of(self.run_hook(self.prompt("alpha", cwd="/other")))
        self.assertNotIn("A project rule", ctx)
        self.assertIn("A global rule", ctx)

    def test_a_prefix_that_is_not_a_subdirectory_is_not_inside_it(self):
        ctx = self.context_of(self.run_hook(self.prompt("alpha", cwd="/repo-other")))
        self.assertNotIn("A project rule", ctx)
        self.assertIn("A global rule", ctx)

    def test_a_payload_with_no_cwd_still_gets_global_rules(self):
        p = self.prompt("alpha")
        del p["cwd"]
        ctx = self.context_of(self.run_hook(p))
        self.assertNotIn("A project rule", ctx)
        self.assertIn("A global rule", ctx)

    def test_a_row_with_no_scope_at_all_is_treated_as_global(self):
        """And specifically NOT as "every path starts with /", which is what the naive
        spelling of the scope test does to a row whose scope is an empty string."""
        row = self.row("n9x9", "A scopeless rule.", keywords=["beta"])
        row["scope"] = ""
        self.write_rows(row)
        ctx = self.context_of(self.run_hook(self.prompt("beta", cwd="/somewhere/else")))
        self.assertIn("A scopeless rule", ctx)


# ==================================================================== ranking and cap
class RankingTest(RemindCase):
    """REMIND_MAX=2 by default, so which two arrive is a decision the hook makes on every
    event. score = 100 for a command match, +50 for a path match, +10 per keyword."""

    def test_the_cap_names_the_two_highest_scoring(self):
        self.write_rows(
            self.row("na", "THREE keywords.", keywords=["a", "b", "c"]),
            self.row("nb", "TWO keywords.", keywords=["a", "b"]),
            self.row("nc", "ONE keyword.", keywords=["a"]))
        ctx = self.context_of(self.run_hook(self.prompt("a b c")))
        self.assertIn("THREE keywords", ctx)
        self.assertIn("TWO keywords", ctx)
        self.assertNotIn("ONE keyword", ctx)
        self.assertEqual(len(ctx.split("\n")), 2)

    def test_the_higher_score_comes_first(self):
        self.write_rows(
            self.row("nb", "TWO keywords.", keywords=["a", "b"]),
            self.row("na", "THREE keywords.", keywords=["a", "b", "c"]))
        ctx = self.context_of(self.run_hook(self.prompt("a b c")))
        self.assertLess(ctx.index("THREE keywords"), ctx.index("TWO keywords"))

    def test_the_cap_is_configurable(self):
        self.write_rows(
            self.row("na", "THREE keywords.", keywords=["a", "b", "c"]),
            self.row("nb", "TWO keywords.", keywords=["a", "b"]))
        ctx = self.context_of(self.run_hook(self.prompt("a b c"), REMIND_MAX="1"))
        self.assertEqual(ctx.count("Reminder recorded"), 1)
        self.assertIn("THREE keywords", ctx)

    def test_a_tie_is_broken_by_fewer_live_hits(self):
        """An unheard reminder outranks one that has already been delivered."""
        self.write_rows(
            self.row("nd", "ALREADY heard.", keywords=["a"], created=1_756_838_400),
            self.row("ne", "NEVER heard.", keywords=["a"], created=1_756_838_400))
        os.makedirs(os.path.dirname(self.hits), exist_ok=True)
        with open(self.hits, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": "nd", "ts": 1, "session": "old",
                                 "event": "UserPromptSubmit"}) + "\n")
        ctx = self.context_of(self.run_hook(self.prompt("a"), REMIND_MAX="1"))
        self.assertIn("NEVER heard", ctx)

    def test_a_remaining_tie_is_broken_by_the_newer_row(self):
        self.write_rows(
            self.row("nf", "OLDER.", keywords=["a"], created=1_756_838_400),
            self.row("ng", "NEWER.", keywords=["a"], created=1_756_838_900))
        ctx = self.context_of(self.run_hook(self.prompt("a"), REMIND_MAX="1"))
        self.assertIn("NEWER", ctx)

    def test_a_command_match_outranks_a_path_match(self):
        sig = norm_of("./run_tests.sh")
        self.write_rows(
            self.row("nh", "PATH rule.", paths=["*"], scope="global"),
            self.row("ni", "COMMAND rule.", commands=[sig], scope="global"))
        ctx = self.context_of(self.run_hook(self.bash("./run_tests.sh")), event="PreToolUse")
        # A Bash call reaches only the command arm, so this also pins that the path arm
        # does not leak into it.
        self.assertIn("COMMAND rule", ctx)
        self.assertNotIn("PATH rule", ctx)


# ==================================================================== cooldown
class CooldownTest(RemindCase):

    def setUp(self):
        super().setUp()
        self.write_rows(self.row("nk", "Once is enough.", keywords=["alpha"]))

    def test_by_default_a_reminder_fires_once_per_session(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p1")))
        self.assert_silent(self.run_hook(self.prompt("alpha", session="s1", pid="p2")))

    def test_a_different_session_is_not_held_back(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="s1")))
        self.context_of(self.run_hook(self.prompt("alpha", session="s2")))

    def test_a_positive_cooldown_holds_it_back_until_it_expires(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p1"),
                                      REMIND_COOLDOWN="600"))
        self.assert_silent(self.run_hook(self.prompt("alpha", session="s1", pid="p2"),
                                         REMIND_COOLDOWN="600",
                                         REMIND_NOW=self.clock + 599))
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p3"),
                                      REMIND_COOLDOWN="600",
                                      REMIND_NOW=self.clock + 601))

    def test_a_clock_that_jumped_backwards_does_not_silence_it_forever(self):
        """The comparison is on |now - stamp|. A stamp from the future would otherwise
        hold the reminder back until the wall clock caught up."""
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p1"),
                                      REMIND_COOLDOWN="600"))
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p2"),
                                      REMIND_COOLDOWN="600",
                                      REMIND_NOW=self.clock - 5000))

    def test_the_stamp_holds_the_epoch_it_fired(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="s1")))
        stamp = os.path.join(self.state, "remind", "s1", "nk")
        self.assertEqual(open(stamp, encoding="utf-8").read().strip(), str(self.clock))

    def test_a_reminder_whose_stamp_cannot_be_written_is_not_emitted(self):
        """Firing on every event because the cooldown cannot be recorded is worse than
        not firing: the reminder would arrive on every prompt for the whole session."""
        sdir = os.path.join(self.state, "remind", "s1")
        os.makedirs(sdir)
        os.chmod(sdir, 0o500)
        try:
            self.assert_silent(self.run_hook(self.prompt("alpha", session="s1")))
        finally:
            os.chmod(sdir, 0o700)

    def test_a_held_back_reminder_does_not_consume_a_cap_slot(self):
        self.write_rows(self.row("nl", "Second.", keywords=["alpha"]),
                        self.row("nm", "Third.", keywords=["alpha"]))
        first = self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p1")))
        self.assertEqual(first.count("Reminder recorded"), 2)
        second = self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p2")))
        # The two already delivered are on cooldown; the third takes a slot rather than
        # being crowded out by them.
        self.assertEqual(second.count("Reminder recorded"), 1)
        for text in ("Once is enough", "Second.", "Third."):
            self.assertIn(text, first + second)


# ==================================================================== double delivery
class DoubleDeliveryTest(RemindCase):
    """With settings.json and the plugin both wired, every event is delivered twice."""

    def setUp(self):
        super().setUp()
        self.write_rows(self.row("nn", "Say it once.", keywords=["alpha"]))

    def test_the_same_prompt_delivered_twice_reminds_once(self):
        payload = self.prompt("alpha", session="s1", pid="p-abc")
        self.context_of(self.run_hook(payload))
        self.assert_silent(self.run_hook(payload))
        self.assertEqual(len(self.hit_rows()), 1, self.hit_rows())

    def test_the_same_tool_call_delivered_twice_reminds_once(self):
        self.write_rows(self.row("no", "Path once.", paths=["tests/*.py"]))
        payload = self.write("/repo/tests/test_x.py", session="s1", tuid="toolu_abc")
        self.context_of(self.run_hook(payload), event="PreToolUse")
        self.assert_silent(self.run_hook(payload))

    def test_the_claim_holds_even_once_the_cooldown_has_expired(self):
        """Isolates the claim from the cooldown: with a cooldown that has expired, only
        the per-event claim can be what suppresses the second delivery."""
        payload = self.prompt("alpha", session="s1", pid="p-abc")
        self.context_of(self.run_hook(payload, REMIND_COOLDOWN="10"))
        self.assert_silent(self.run_hook(payload, REMIND_COOLDOWN="10",
                                         REMIND_NOW=self.clock + 1000))

    def test_a_prompt_and_a_tool_call_sharing_an_id_do_not_claim_each_other(self):
        self.write_rows(self.row("np", "Path once.", paths=["tests/*.py"]))
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="dup")))
        self.context_of(self.run_hook(self.write("/repo/tests/t.py", session="s1",
                                                 tuid="dup")), event="PreToolUse")

    def test_an_event_with_no_id_still_fires(self):
        """Losing reminders is worse than a rare duplicate, so an unidentifiable event is
        always acted on."""
        p = self.prompt("alpha", session="s1")
        del p["prompt_id"]
        self.context_of(self.run_hook(p))

    def test_distinct_sessions_do_not_share_claims(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="alpha", pid="p-same")))
        self.context_of(self.run_hook(self.prompt("alpha", session="beta", pid="p-same")))


# ==================================================================== hits
class HitsTest(RemindCase):
    """The hook never rewrites the store. A delivery is an append to a separate log, and
    `skillnote list` derives the live count from it."""

    def test_a_delivery_appends_one_row_and_leaves_the_store_byte_identical(self):
        self.write_rows(self.row("nq", "Say it.", keywords=["alpha"]))
        before = open(self.store, "rb").read()
        self.context_of(self.run_hook(self.prompt("alpha", session="s1")))
        self.assertEqual(open(self.store, "rb").read(), before,
                         "the hook must never rewrite reminders.jsonl")
        rows = self.hit_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {"id": "nq", "ts": self.clock, "session": "s1",
                                   "event": "UserPromptSubmit"})

    def test_two_reminders_in_one_emit_are_two_hit_rows(self):
        self.write_rows(self.row("nr", "One.", keywords=["alpha"]),
                        self.row("ns", "Two.", keywords=["alpha"]))
        self.context_of(self.run_hook(self.prompt("alpha", session="s1")))
        self.assertEqual(sorted(r["id"] for r in self.hit_rows()), ["nr", "ns"])

    def test_a_tool_event_records_its_own_event_name(self):
        self.write_rows(self.row("nt", "Path.", paths=["tests/*.py"]))
        self.context_of(self.run_hook(self.write("/repo/tests/t.py", session="s1")),
                        event="PreToolUse")
        self.assertEqual(self.hit_rows()[0]["event"], "PreToolUse")


# ==================================================================== tombstones
class TombstoneTest(RemindCase):
    """Removal is an appended tombstone, never a rewrite -- the same doctrine as
    `skillrepeat forget`, and for the same reason: a hook and a CLI both hold this file
    open and a rewrite loses whatever was appended between the read and the write."""

    def test_a_tombstoned_row_never_fires(self):
        self.write_rows(self.row("nu", "Retired.", keywords=["alpha"]))
        self.context_of(self.run_hook(self.prompt("alpha", session="s0")))
        self.write_rows(self.tombstone("nu"))
        self.assert_silent(self.run_hook(self.prompt("alpha", session="s1")))

    def test_the_tombstone_removes_nothing_from_the_file(self):
        self.write_rows(self.row("nv", "Retired.", keywords=["alpha"]),
                        self.tombstone("nv"))
        self.assert_silent(self.run_hook(self.prompt("alpha")))
        self.assertIn("Retired.", open(self.store, encoding="utf-8").read())

    def test_a_row_re_added_after_its_tombstone_fires_again(self):
        """The tombstone kills ids created at or before it, not the id forever."""
        self.write_rows(self.row("nw", "First life.", keywords=["alpha"],
                                 created=1_756_838_400),
                        self.tombstone("nw", ts=1_756_838_500),
                        self.row("nw", "Second life.", keywords=["alpha"],
                                 created=1_756_838_600))
        ctx = self.context_of(self.run_hook(self.prompt("alpha")))
        self.assertIn("Second life", ctx)

    def test_only_the_tombstoned_id_goes_quiet(self):
        self.write_rows(self.row("nx", "Gone.", keywords=["alpha"]),
                        self.row("ny", "Still here.", keywords=["alpha"]),
                        self.tombstone("nx"))
        ctx = self.context_of(self.run_hook(self.prompt("alpha")))
        self.assertNotIn("Gone.", ctx)
        self.assertIn("Still here", ctx)


# ==================================================================== fail open
class FailOpenTest(RemindCase):
    """A hook may never break a turn. Every path below exits 0 and says nothing."""

    def seed(self):
        self.write_rows(self.row("nz", "Anything.", keywords=["alpha"]))

    def test_the_off_switch(self):
        self.seed()
        self.assert_silent(self.run_hook(self.prompt("alpha"),
                                         SKILL_COMPOUNDER_REMIND="0"))

    def test_no_store_at_all(self):
        self.assert_silent(self.run_hook(self.prompt("alpha")))

    def test_an_empty_store(self):
        open(self.store, "w").close()
        self.assert_silent(self.run_hook(self.prompt("alpha")))

    def test_a_store_of_garbage(self):
        with open(self.store, "w", encoding="utf-8") as fh:
            fh.write("not json at all\n{\"half\": \n\n")
        self.assert_silent(self.run_hook(self.prompt("alpha")))

    def test_a_malformed_line_does_not_hide_the_rows_around_it(self):
        """`jq -s` over a store with one bad line fails the WHOLE read, which would make
        a store stop working forever because something once wrote half a line."""
        with open(self.store, "w", encoding="utf-8") as fh:
            fh.write("{\"broken\": \n")
        self.seed()
        ctx = self.context_of(self.run_hook(self.prompt("alpha")))
        self.assertIn("Anything.", ctx)

    def test_a_row_with_no_text_is_skipped(self):
        row = self.row("n00", "", keywords=["alpha"])
        self.write_rows(row)
        self.assert_silent(self.run_hook(self.prompt("alpha")))

    def test_a_row_whose_id_cannot_be_a_filename_is_skipped(self):
        """The id names the cooldown stamp under <state>/remind/<sid>/, so an id carrying
        a slash would write outside that directory. An id we cannot honour a cooldown for
        is one we must not fire."""
        self.write_rows(self.row("../../escape", "Escaped.", keywords=["alpha"]))
        self.assert_silent(self.run_hook(self.prompt("alpha")))

    def test_a_payload_that_is_not_json(self):
        self.seed()
        self.assert_silent(self.run_hook("this is not json"))

    def test_an_empty_payload(self):
        self.seed()
        self.assert_silent(self.run_hook(""))

    def test_an_unknown_hook_event(self):
        self.seed()
        self.assert_silent(self.run_hook(self.prompt("alpha",
                                                     hook_event_name="PostToolUse")))

    def test_a_payload_with_no_session_id_still_fires(self):
        """A missing session id costs a shared cooldown bucket, not the reminder."""
        self.seed()
        p = self.prompt("alpha")
        del p["session_id"]
        ctx = self.context_of(self.run_hook(p))
        self.assertIn("Anything.", ctx)

    def test_an_unwritable_state_directory(self):
        self.seed()
        os.chmod(self.state, 0o500)
        try:
            self.assert_silent(self.run_hook(self.prompt("alpha")))
        finally:
            os.chmod(self.state, 0o700)

    def test_garbage_tunables_do_not_reach_arithmetic(self):
        """A typo'd export must not print `[: integer expected` from a hook on the user's
        stderr for the rest of the session."""
        self.seed()
        r = self.run_hook(self.prompt("alpha"), REMIND_MAX="lots",
                          REMIND_COOLDOWN="soon", REMIND_MAX_ROWS="many",
                          REMIND_NOW="yesterday")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr.strip(), "", "a hook must not write to stderr")
        self.assertIn("Anything.", json.loads(r.stdout)["hookSpecificOutput"]
                      ["additionalContext"])

    def test_a_cap_of_zero_says_nothing(self):
        self.seed()
        self.assert_silent(self.run_hook(self.prompt("alpha"), REMIND_MAX="0"))

    def test_without_jq_it_is_silent(self):
        """The dependency check runs before anything reads stdin, so a bare PATH
        exercises it exactly."""
        self.seed()
        bare = os.path.join(self.tmp, "emptybin")
        os.makedirs(bare)
        os.symlink(shutil.which("bash") or "/bin/bash", os.path.join(bare, "bash"))
        self.assert_silent(self.run_hook(self.prompt("alpha"), PATH=bare))

    def test_only_the_last_max_rows_are_read(self):
        """The read is bounded, and the bound is the TAIL: the newest rows are the ones
        that survive it."""
        self.write_rows(*[self.row("nold%d" % i, "Old %d." % i, keywords=["alpha"])
                          for i in range(5)])
        self.write_rows(self.row("nnew", "Newest.", keywords=["alpha"]))
        ctx = self.context_of(self.run_hook(self.prompt("alpha"), REMIND_MAX_ROWS="1",
                                            REMIND_MAX="5"))
        self.assertEqual(ctx.count("Reminder recorded"), 1)
        self.assertIn("Newest.", ctx)


# ==================================================================== the prune
class PruneTest(RemindCase):
    """<state>/remind/ grows by a <sid>/ and a <sid>.seen/ per session that heard a
    reminder, and nothing else sweeps it (issue #33): `prune_stale_state()` in
    hooks/compound-improvement.sh walks <state>/reminders/, which is deliberately a
    different directory. So the hook sweeps its own tree, on a sampled event, by age
    against its own clock.

    THE TREE IS BUILT BY THE HOOK, never by hand: every directory below was written by a
    real delivery, so the sweep is tested against the shape the writer really produces.
    Age is then set with os.utime, which is the one thing a delivery cannot do.
    """

    DAY = 86400
    TTL = 7 * 86400

    def setUp(self):
        super().setUp()
        self.write_rows(self.row("np", "Sweep me.", keywords=["alpha"]))

    def dirs(self, sid):
        return (os.path.join(self.state, "remind", sid),
                os.path.join(self.state, "remind", sid + ".seen"))

    def deliver(self, sid, pid="p1"):
        """A real delivery, with the sweep switched off so the tree only grows."""
        self.context_of(self.run_hook(self.prompt("alpha", session=sid, pid=pid),
                                      REMIND_PRUNE_EVERY="0"))
        for d in self.dirs(sid):
            self.assertTrue(os.path.isdir(d), "the delivery did not write %s" % d)

    def age(self, sid, seconds):
        t = self.clock - seconds
        for d in self.dirs(sid):
            os.utime(d, (t, t))

    def sweep(self, sid="cur", pid="sweep"):
        """A forced sweep from session `sid`, on a prompt that matches nothing: the sweep
        runs before selection, so an event that delivers nothing still sweeps."""
        self.assert_silent(self.run_hook(self.prompt("nothing here", session=sid, pid=pid),
                                         REMIND_PRUNE_EVERY="1"))

    def test_a_real_stale_tree_is_swept_and_what_should_survive_survives(self):
        for sid in ("stale1", "stale2", "fresh", "future", "cur"):
            self.deliver(sid)
        self.age("stale1", 9 * self.DAY)          # well past the TTL
        self.age("stale2", self.TTL + 1)          # one second past it
        self.age("fresh", self.TTL - 1)           # one second inside it
        self.age("future", -10 * self.DAY)        # a clock that ran ahead
        self.age("cur", 30 * self.DAY)            # the sweeping session, ancient
        # CANARIES that must survive whatever the sweep does: the store, the checkpoint
        # hook's counter directory, and the hit log -- every one as old as the stale
        # sessions, so "it survived" cannot also mean "nothing was that old".
        counters = os.path.join(self.state, "reminders")
        os.makedirs(counters)
        canary = os.path.join(counters, "old.edits")
        with open(canary, "w", encoding="utf-8") as fh:
            fh.write("x")
        old = self.clock - 30 * self.DAY
        for p in (self.store, canary, self.hits):
            os.utime(p, (old, old))
        store_before = open(self.store, "rb").read()
        hits_before = open(self.hits, "rb").read()

        self.sweep("cur")

        for sid in ("stale1", "stale2"):
            for d in self.dirs(sid):
                self.assertFalse(os.path.exists(d), "%s should have been swept" % d)
        for sid in ("fresh", "future", "cur"):
            for d in self.dirs(sid):
                self.assertTrue(os.path.isdir(d), "%s should have survived" % d)
        self.assertEqual(open(self.store, "rb").read(), store_before,
                         "the sweep must never touch reminders.jsonl")
        self.assertTrue(os.path.exists(canary),
                        "the sweep reached <state>/reminders/, which is not its tree")
        self.assertEqual(open(self.hits, "rb").read(), hits_before,
                         "the sweep must never touch hits.jsonl")

    def test_the_sweep_is_sampled_and_zero_switches_it_off(self):
        self.deliver("stale1")
        self.deliver("cur")
        self.age("stale1", 30 * self.DAY)
        self.assert_silent(self.run_hook(self.prompt("nothing here", session="cur",
                                                     pid="p2"),
                                         REMIND_PRUNE_EVERY="0"))
        for d in self.dirs("stale1"):
            self.assertTrue(os.path.isdir(d), "REMIND_PRUNE_EVERY=0 must not sweep")
        self.sweep("cur")
        for d in self.dirs("stale1"):
            self.assertFalse(os.path.exists(d))

    def test_the_ttl_is_a_knob_and_reads_the_hooks_own_clock(self):
        self.deliver("s1")
        self.deliver("cur")
        self.age("s1", 100)
        self.assert_silent(self.run_hook(self.prompt("nothing here", session="cur",
                                                     pid="p2"),
                                         REMIND_PRUNE_EVERY="1", REMIND_PRUNE_TTL="99"))
        for d in self.dirs("s1"):
            self.assertFalse(os.path.exists(d), "a 100 s old directory beats a 99 s TTL")

    def test_a_sweep_never_re_arms_a_cooldown_in_the_session_that_runs_it(self):
        """The trap: a stamp removed from under a live session re-arms every cooldown in
        it, and a claim removed re-opens the double delivery. So the sweeping session's
        own pair is skipped whatever its age -- here, thirty days."""
        self.deliver("s1", pid="p1")
        self.age("s1", 30 * self.DAY)
        self.sweep("s1", pid="p2")
        for d in self.dirs("s1"):
            self.assertTrue(os.path.isdir(d), "the sweep removed its own session's %s" % d)
        # The cooldown still holds ...
        self.assert_silent(self.run_hook(self.prompt("alpha", session="s1", pid="p3"),
                                         REMIND_PRUNE_EVERY="1"))
        # ... and so does the claim on the event that already delivered.
        self.assert_silent(self.run_hook(self.prompt("alpha", session="s1", pid="p1"),
                                         REMIND_PRUNE_EVERY="1"))
        self.assertEqual(len(self.hit_rows()), 1, "the reminder was delivered twice")

    def test_another_sessions_sweep_does_reach_it_by_age(self):
        """The same pair, the same age, swept from a different session: gone, and the
        reminder fires again in the old session afterwards. That is what the sweep is
        for; the previous test is what bounds it."""
        self.deliver("s1", pid="p1")
        self.age("s1", 30 * self.DAY)
        self.sweep("s2")
        for d in self.dirs("s1"):
            self.assertFalse(os.path.exists(d))
        self.context_of(self.run_hook(self.prompt("alpha", session="s1", pid="p4"),
                                      REMIND_PRUNE_EVERY="0"))


# ==================================================================== the hits cap
class HitsCapTest(RemindCase):
    """hits.jsonl was bounded on read and unbounded on write (issue #33). Now a delivery
    that pushes it past REMIND_MAX_ROWS rewrites it to its last REMIND_MAX_ROWS rows.

    The log is written past the cap by REAL deliveries and read back by the REAL reader:
    the hook's own tie-break on live hits. A hand-written log would pin whichever shape
    its author was looking at and let the other side drift.
    """

    def setUp(self):
        super().setUp()
        self.write_rows(self.row("na", "A.", keywords=["alpha"]),
                        self.row("nb", "B.", keywords=["alpha"]),
                        self.row("nc", "C.", keywords=["alpha"]))

    def test_writing_past_the_cap_keeps_exactly_the_newest_max_rows(self):
        for i, sid in enumerate(("s1", "s2", "s3")):
            ctx = self.context_of(self.run_hook(self.prompt("alpha", session=sid),
                                                REMIND_MAX="3", REMIND_MAX_ROWS="5",
                                                REMIND_NOW=self.clock + i))
            self.assertEqual(ctx.count("Reminder recorded"), 3)
        # 9 rows were appended; the file holds the last 5, every one of which parses.
        with open(self.hits, encoding="utf-8") as fh:
            raw = fh.read()
        self.assertTrue(raw.endswith("\n"), "the trimmed log lost its final newline")
        rows = [json.loads(l) for l in raw.splitlines() if l.strip()]
        self.assertEqual(len(rows), 5)
        self.assertEqual([r["ts"] for r in rows],
                         [self.clock + 1, self.clock + 1,
                          self.clock + 2, self.clock + 2, self.clock + 2],
                         "the rows kept are not the newest five")
        self.assertEqual([r["session"] for r in rows], ["s2", "s2", "s3", "s3", "s3"])
        self.assertFalse([f for f in os.listdir(os.path.dirname(self.hits))
                          if f.startswith(".hits.")],
                         "the rewrite left its temp file behind")

    def test_at_the_cap_nothing_is_rewritten(self):
        self.context_of(self.run_hook(self.prompt("alpha", session="s1"),
                                      REMIND_MAX="3", REMIND_MAX_ROWS="3"))
        self.assertEqual(len(self.hit_rows()), 3)
        self.assertEqual([r["id"] for r in self.hit_rows()], ["na", "nb", "nc"])

    def test_the_hook_still_reads_the_trimmed_log(self):
        """The real reader over the real writer's trimmed output. After the trim, only
        the newest rows count as hits, and the tie-break sees exactly those."""
        for i, sid in enumerate(("s1", "s2")):
            self.context_of(self.run_hook(self.prompt("alpha", session=sid),
                                          REMIND_MAX="3", REMIND_MAX_ROWS="5",
                                          REMIND_NOW=self.clock + i))
        # Six appended, five kept: s1's `na` row went; s1's `nb`, `nc` and all of s2 stay.
        self.assertEqual([(r["session"], r["id"]) for r in self.hit_rows()],
                         [("s1", "nb"), ("s1", "nc"), ("s2", "na"), ("s2", "nb"),
                          ("s2", "nc")])
        # `na` now has one live hit and `nb`, `nc` have two, so on a fresh session `na`
        # outranks both. That ordering exists only if the trimmed log was read: on the
        # untrimmed six every id has two hits and the tie falls to `created`, which is
        # equal, and nothing puts `na` first.
        ctx = self.context_of(self.run_hook(self.prompt("alpha", session="s3"),
                                            REMIND_MAX="1", REMIND_MAX_ROWS="5"))
        self.assertIn("A.", ctx)
        self.assertNotIn("B.", ctx)


# ==================================================================== cost
class CostTest(RemindCase):
    """This runs before EVERY Bash, Write and Edit call and on every prompt, so its cost
    is paid hundreds of times a session. The figure quoted in the design is 500 rows under
    300 ms; it is measured here rather than assumed, and printed so it can be re-read."""

    def fill(self, n=500, matching=1):
        rows = []
        for i in range(n - matching):
            rows.append(self.row("nc%06d" % i, "Filler reminder number %d." % i,
                                 keywords=["kw%d" % i, "other"],
                                 paths=["src/%d/*.py" % i],
                                 scope=PROJECT if i % 2 else "global",
                                 created=1_756_000_000 + i))
        for i in range(matching):
            rows.append(self.row("nhit%02d" % i, "The one that matches.",
                                 keywords=["alpha"], created=1_756_900_000))
        self.write_rows(*rows)
        return os.path.getsize(self.store)

    def fill_with_a_command_rule(self, n=500):
        """The same 500 rows, one of them keyed on a command, so `has_command_rule` opens
        the gate and every candidate is really normalised. This is the expensive case the
        segment split introduced, and it is the one worth a stopwatch."""
        rows = []
        for i in range(n - 1):
            rows.append(self.row("nc%06d" % i, "Filler reminder number %d." % i,
                                 keywords=["kw%d" % i, "other"],
                                 paths=["src/%d/*.py" % i],
                                 scope=PROJECT if i % 2 else "global",
                                 created=1_756_000_000 + i))
        rows.append(self.row("nhitcmd", "The one that matches.",
                             commands=[norm_of("python3 setup.py install")],
                             scope="global", created=1_756_900_000))
        self.write_rows(*rows)
        return os.path.getsize(self.store)

    def timed(self, label, payload, filler=None, bound=0.300):
        size = (filler or self.fill)()
        runs = []
        for i in range(5):
            p = dict(payload)
            p["session_id"] = "cost%d" % i
            p["prompt_id"] = "p%d" % i
            p["tool_use_id"] = "t%d" % i
            t0 = time.time()
            r = self.run_hook(p)
            runs.append(time.time() - t0)
            self.assertEqual(r.returncode, 0, r.stderr)
        runs.sort()
        median = runs[len(runs) // 2]
        print("\n[cost] remind/%s: 500 rows, %d bytes, median %.0f ms (min %.0f, max %.0f)"
              % (label, size, median * 1000, runs[0] * 1000, runs[-1] * 1000))
        self.assertLess(median, bound,
                        "a 500-row store took %.0f ms on %s (bound %.0f ms)"
                        % (median * 1000, label, bound * 1000))
        return median

    def test_a_prompt_against_500_rows(self):
        self.timed("UserPromptSubmit", self.prompt("alpha"))

    def test_a_write_against_500_rows(self):
        self.timed("PreToolUse/Write", self.write("/repo/src/1/x.py"))

    def test_a_bash_call_against_500_rows(self):
        """A store of keyword and path rules -- every store until someone writes a lesson.
        `has_command_rule` finds no command rule, so this arm forks NOTHING, where it used
        to fork the normaliser unconditionally."""
        self.timed("PreToolUse/Bash", self.bash("gh pr list"))

    def test_a_bash_call_against_a_store_that_holds_a_command_rule(self):
        """Now the gate is open and the whole command is normalised: one fork."""
        self.timed("PreToolUse/Bash+cmd", self.bash("python3 setup.py install"),
                   filler=self.fill_with_a_command_rule)

    def test_a_compound_bash_call_against_a_store_that_holds_a_command_rule(self):
        """The worst case the split can reach on an ordinary command: the whole command
        plus three segments, four forks of repeat-gate.sh. MAX_CANDIDATES is what stops a
        pasted script going further.

        THE BOUND IS ITS OWN, AND HIGHER, because the budget here is process starts rather
        than bytes: four forks of an external script, measured at 160-169 ms on this
        machine against 49-50 ms for the same store with the gate shut. 300 ms is the
        figure the design fixes for the ORDINARY path and the three cases above still hold
        it; a compound call against a store that holds a command rule is a different case.
        800 rather than 500 is measured too, and it is not slack: running this file beside
        one other test file put the same case at 396 ms and every other arm at roughly
        double its solo figure, so a bound set from an idle machine is a coin toss on a
        loaded one -- and a suite that goes red for load teaches its reader to re-run it
        rather than to read it. What it still catches is the thing worth catching: a cap
        that stopped bounding the forks."""
        self.timed("PreToolUse/Bash+compound",
                   self.bash("cd build; ls; python3 setup.py install 2>&1"),
                   filler=self.fill_with_a_command_rule, bound=0.800)


# ==================================================================== ids that are not names
class UnsafeSessionIdTest(RemindCase):
    """`.` and `..` are inside `A-Za-z0-9._-`, so the sanitiser passes them through.

    This hook keys its per-session claims and its cooldown stamps on `<state>/remind/<sid>/`
    and `<sid>.seen/`, and `prune_stale_sessions()` walks one level under `<state>/remind/`.
    With `sid` = `.` the stamps land in `<state>/remind/` itself; with `..` they land in the
    STATE ROOT, beside reminders.jsonl and ledger.jsonl. One guard line, spelled the same
    way in every script here, maps all three unsafe names to `_`.
    """

    def setUp(self):
        RemindCase.setUp(self)
        self.write_rows(self.row("r1", "The lesson.", keywords=["widget"]))

    def remind_dir(self):
        return os.path.join(self.state, "remind")

    def test_a_session_id_of_dot_keys_its_state_under_the_safe_name(self):
        self.context_of(self.run_hook(self.prompt("the widget again", session=".")))
        rd = self.remind_dir()
        self.assertTrue(os.path.isdir(os.path.join(rd, "_"))
                        or os.path.isdir(os.path.join(rd, "_.seen")),
                        "nothing was keyed under the safe name: %r" % sorted(os.listdir(rd)))
        # `hits.jsonl` is the only file this hook writes directly into <state>/remind/.
        for name in sorted(os.listdir(rd)):
            self.assertTrue(name in ("hits.jsonl", "_", "_.seen") or name.startswith(".hits."),
                            "`.` put %r straight into <state>/remind/" % name)

    def test_a_session_id_of_dotdot_writes_nothing_into_the_state_root(self):
        before = sorted(os.listdir(self.state))
        self.context_of(self.run_hook(self.prompt("the widget again", session="..")))
        after = sorted(os.listdir(self.state))
        self.assertEqual(after, sorted(set(before) | {"remind"}),
                         "`..` put something in the state root: %r -> %r" % (before, after))

    def test_the_hits_row_carries_the_guarded_name(self):
        self.context_of(self.run_hook(self.prompt("the widget again", session="..")))
        rows = self.hit_rows()
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["session"], "_")

    def test_the_dot_session_is_still_deduplicated_against_itself(self):
        """The claim has to work under the safe name too, or the guard would have traded
        one defect for the double delivery this hook exists to survive."""
        first = self.run_hook(self.prompt("the widget again", session=".", pid="pX"))
        self.context_of(first)
        second = self.run_hook(self.prompt("the widget again", session=".", pid="pX"))
        self.assert_silent(second)


# ==================================================================== a log that will not open
class AppendFailureTest(RemindCase):
    """`2>/dev/null` after a `>>` silences the COMMAND, not the shell's failure to OPEN
    the append -- which the shell reports itself, before the later redirection applies.
    Measured with a directory in place of the log: the wrong order prints
    "bash: hits.jsonl: Is a directory" onto the user's terminal from inside a hook."""

    def test_a_delivery_whose_hits_log_is_a_directory_is_silent_on_stderr(self):
        self.write_rows(self.row("r1", "The lesson.", keywords=["widget"]))
        os.makedirs(self.hits)
        r = self.run_hook(self.prompt("the widget again"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "",
                         "the shell's redirection failure reached the user: %r" % r.stderr)
        self.context_of(r)

    def test_the_same_holds_for_the_row_that_carries_a_candidate(self):
        """The other append: the two `printf` calls differ only by the lineage field."""
        self.write_rows(dict(self.row("r1", "The lesson.", keywords=["widget"]),
                             candidate="c12345678"))
        os.makedirs(self.hits)
        r = self.run_hook(self.prompt("the widget again"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "", r.stderr)


# ==================================================================== knobs out of range
class KnobMagnitudeTest(RemindCase):
    """23 nines is all digits, so `*[!0-9]*` passed it and `[ "$MAX" -lt 1 ]` printed
    `integer expression expected` on the user's stderr from a hook. Out of range takes the
    documented DEFAULT; the shape guard alone could never have caught it."""

    HUGE = "99999999999999999999999"

    def test_every_remind_knob_refuses_a_value_that_large(self):
        self.write_rows(self.row("r1", "The lesson.", keywords=["widget"]))
        for knob in ("REMIND_MAX", "REMIND_COOLDOWN", "REMIND_MAX_ROWS",
                     "REMIND_PRUNE_TTL", "REMIND_PRUNE_EVERY"):
            r = self.run_hook(self.prompt("the widget again", session="s-" + knob),
                              **{knob: self.HUGE})
            self.assertEqual(r.returncode, 0, "%s: %s" % (knob, r.stderr))
            self.assertEqual(r.stderr, "", "%s=%s printed: %r" % (knob, self.HUGE, r.stderr))
            self.assertTrue(r.stdout.strip(),
                            "%s=%s silenced the reminder instead of taking the default"
                            % (knob, self.HUGE))

    def test_a_ten_digit_value_is_still_in_range(self):
        """Non-vacuity: 11 `?` rejects eleven digits, not ten."""
        self.write_rows(self.row("r1", "The lesson.", keywords=["widget"]))
        r = self.run_hook(self.prompt("the widget again"), REMIND_PRUNE_TTL="9999999999")
        self.assertEqual(r.stderr, "", r.stderr)
        self.assertTrue(r.stdout.strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
