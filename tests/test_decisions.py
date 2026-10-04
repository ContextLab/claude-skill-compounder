#!/usr/bin/env python3
"""The design decisions of 2026-10-04 (notes/2026-10-04-decisions.md), held to the CLI.

  D1  no guard yields: every guard in force that matches a call is a hit
  D2  a project lesson with the name of a user or general one is shadowed, not in force
  D3  a lesson directory that is no slug is reported and unused
  D4  `promote --to general --yes` refuses credential-like text, with no override
  D5  `compound log` takes only the types the mod writes
  D8  at most one recall per lesson, per revision, per session counts toward ineffective
  and: recurrence is counted by lesson, not by name; one `learn` or `skip` settles one
  capture; what `promote --to general` scans is what it publishes.
"""

import json
import os
import unittest

from test_support import NOW, Case, git_ok, seed_event

ECHO = r"(^\s*|[;&|(]\s*|\b(?:do|then|else)\s+)echo\s+=+"
MOD_TYPES = ("reuse", "guard", "recall", "capture", "remind", "refuse", "nudge", "judge", "repeat", "error", "retry")
CLI_TYPES = {"learn": "compound add", "skip": "compound skip", "rm": "compound rm", "skill": "compound skill",
             "promote": "compound promote", "candidate": "compound promote", "use": "compound use"}


class NoGuardYieldsTest(Case):
    """D1."""

    def check(self, command):
        proc = self.box.run("check", "--guards", stdin=json.dumps({"tool": "Bash", "input": {"command": command}}))
        self.assertExit(proc, 0)
        return json.loads(proc.stdout)

    def ship(self, name, pattern, body):
        self.box.write_lesson(self.box.lesson_dir(name, "general"), name, body=body,
                              extra="match: %s\n" % json.dumps([pattern]))

    def test_a_user_guard_and_a_general_guard_on_one_call_are_both_hits(self):
        self.ship("pool-equals", ECHO, "The pool's text.\n")
        self.box.add("my-equals", "Use when mine.", "My text.\n", "--level", "user", "--match", ECHO)
        reply = self.check("ls; echo =====")
        self.assertEqual([(hit["level"], hit["name"], hit["text"]) for hit in reply["hits"]],
                         [("user", "my-equals", "My text."), ("general", "pool-equals", "The pool's text.")])
        self.assertNotIn("yielded", reply)
        self.assertEqual(reply["guards"], 2)

    def test_an_unrelated_user_guard_no_longer_hides_a_general_one(self):
        """The bug D1 removes: any user guard that hit silenced every general guard that
        hit the same call, related or not."""
        self.ship("pool-equals", ECHO, "The pool's text.\n")
        self.box.add("my-deploy", "Use when deploying.", "Pass --target.\n", "--level", "user", "--match", r"deploy\.sh")
        reply = self.check("./deploy.sh; echo =====")
        self.assertEqual(sorted(hit["name"] for hit in reply["hits"]), ["my-deploy", "pool-equals"])
        self.assertNotIn("yielded", reply)

    def test_disable_is_how_a_user_keeps_only_their_own(self):
        self.ship("pool-equals", ECHO, "The pool's text.\n")
        self.box.add("my-equals", "Use when mine.", "My text.\n", "--level", "user", "--match", ECHO)
        self.assertExit(self.box.run("disable", "pool-equals"), 0)
        reply = self.check("echo =====")
        self.assertEqual([hit["name"] for hit in reply["hits"]], ["my-equals"])
        self.assertEqual(reply["guards"], 1)

    def test_guards_of_all_three_levels_are_hits_together(self):
        self.ship("pool-equals", ECHO, "G.\n")
        self.box.add("my-equals", "Use when mine.", "U.\n", "--level", "user", "--match", ECHO)
        self.box.add("here-equals", "Use when here.", "P.\n", "--match", ECHO)
        reply = self.check("echo ====")
        self.assertEqual([hit["level"] for hit in reply["hits"]], ["project", "user", "general"])


class KeptDecisionsTest(Case):
    """D2, D3 and D4 are what the code already did; these pin them."""

    def hand(self, name, level="project", **kw):
        self.box.write_lesson(self.box.lesson_dir(name, level), kw.pop("named", name), **kw)

    def test_d2_a_project_lesson_named_like_a_users_is_shadowed_with_no_override(self):
        self.box.add("house-rule", "Use when the user's.", "The user's text.\n", "--level", "user", "--match", "danger")
        self.hand("house-rule", body="The repository's text.\n", extra='match: ["harmless"]\n')
        rows = {row["level"]: row for row in self.box.json("list", "--json") if row["name"] == "house-rule"}
        self.assertTrue(rows["project"].get("shadowed"))
        self.assertFalse(rows["user"].get("shadowed", False))
        # Not in force: no guard, not found, and `show` prints the user's.
        proc = self.box.run("check", "--guards", stdin=json.dumps({"tool": "Bash", "input": {"command": "harmless"}}))
        self.assertEqual(json.loads(proc.stdout), {"hits": [], "guards": 1, "tools": ["Bash"]})
        self.assertIn("The user's text.", self.box.run("show", "house-rule").stdout)
        self.assertNotIn("The repository's text.", self.box.run("show", "house-rule").stdout)
        found = self.box.json("find", "repository", "--json")
        self.assertEqual([row for row in found["items"] if row["level"] == "project"], [])
        status = json.loads(self.box.run("status", "--json").stdout)
        duplicates = [row for row in status["health"] if row["check"] == "duplicates"][0]
        self.assertEqual(duplicates["status"], "FAIL")
        # No option renames it on load or lets the repository's copy win.
        for flag in ("--override", "--prefer-project", "--rename"):
            self.assertExit(self.box.run("list", flag), 2)

    def test_d3_a_directory_that_is_no_slug_or_differs_from_its_name_is_reported_and_unused(self):
        self.hand("Not_A_Slug", body="Bad directory.\n", extra='match: ["danger"]\n')
        self.hand("right-directory", named="another-name", body="Name differs.\n", extra='match: ["danger"]\n')
        names = [row["name"] for row in self.box.json("list", "--json")]
        self.assertEqual(names, [])
        proc = self.box.run("check", "--guards", stdin=json.dumps({"tool": "Bash", "input": {"command": "danger"}}))
        self.assertEqual(json.loads(proc.stdout), {"hits": [], "guards": 0, "tools": []})
        status = json.loads(self.box.run("status", "--json").stdout)
        parse = [row for row in status["health"] if row["check"] == "lessons parse"][0]
        self.assertEqual(parse["status"], "FAIL")
        self.assertIn("Not_A_Slug", parse["detail"])
        self.assertIn("right-directory", parse["detail"])

    def test_d4_the_credential_refusal_has_no_override(self):
        token = "ghp_" + "A1b2C3d4E5" * 3
        self.box.add("deploy-token", "Use when deploying.", "Export GH_TOKEN=%s first.\n" % token, "--level", "user")
        for flags in (("--yes",), ("--yes", "--force"), ("--yes", "--as-written"), ("--yes", "--new"),
                      ("--yes", "--allow-secrets")):
            proc = self.box.run("promote", "deploy-token", "--to", "general", *flags)
            self.assertExit(proc, 2)
            self.assertNotIn(token, proc.stderr)
        self.assertFalse(any(event["type"] == "promote" for event in self.box.read_events()))
        usage = self.box.run("promote", "--help").stdout
        for word in ("--force", "--allow", "--no-scan", "--skip-scan"):
            self.assertNotIn(word, usage)


class LogTypesTest(Case):
    """D5."""

    def test_log_takes_every_type_the_mod_writes(self):
        for kind in MOD_TYPES:
            self.assertExit(self.box.run("log", stdin=json.dumps({"type": kind})), 0)
        self.assertEqual([event["type"] for event in self.box.read_events()], list(MOD_TYPES))

    def test_log_refuses_each_type_a_command_writes_and_names_the_command(self):
        self.box.log({"type": "nudge", "calls": 1})
        before = self.box.snapshot()
        for kind, command in sorted(CLI_TYPES.items()):
            proc = self.box.run("log", stdin=json.dumps({"type": kind, "lesson": "x", "why": "forged"}))
            self.assertExit(proc, 2)
            self.assertIn("`%s`" % command, proc.stderr, kind)
            self.assertIn(repr(kind), proc.stderr)
        self.assertEqual(self.box.snapshot(), before, "a refused log wrote something")

    def test_a_session_cannot_settle_its_debt_through_log(self):
        self.box.log({"type": "capture", "id": "cap-1", "failed": "./deploy.sh", "fixed": "./deploy.sh --target x"})
        for forged in ({"type": "skip", "why": "not worth it"}, {"type": "learn", "lesson": "x", "settles": "cap-1"},
                       {"type": "skip", "why": "w", "settles": "cap-1"}):
            self.assertExit(self.box.run("log", stdin=json.dumps(forged)), 2)
        owed = self.box.json("events", "--unsettled", "--session", "sess-0001-aaaa", "--json")
        self.assertEqual([event["id"] for event in owed], ["cap-1"])
        # The command that does write a `skip` settles it.
        self.assertExit(self.box.run("skip", "--why", "not worth it"), 0)
        self.assertEqual(self.box.json("events", "--unsettled", "--session", "sess-0001-aaaa", "--json"), [])


class OneRecallPerSessionTest(Case):
    """D8. The recalls are written with the real `compound log`, as the mod writes them:
    without `ineffective`, which the CLI decides and answers."""

    def recall(self, name, session, at, **more):
        event = {"type": "recall", "lesson": name, "tool": "Bash", "call": "./flaky.sh", "error": "boom"}
        event.update(more)
        proc = self.box.run("log", "--json", stdin=json.dumps(event), COMPOUND_NOW=at, CLAUDE_CODE_SESSION_ID=session)
        self.assertExit(proc, 0)
        return json.loads(proc.stdout)

    def row(self, name):
        return [row for row in self.box.json("list", "--json") if row["name"] == name][0]

    def test_two_recalls_a_second_apart_in_one_session_do_not_make_a_lesson_ineffective(self):
        self.box.add("flaky")
        first = self.recall("flaky", "s-one", NOW + 60)
        second = self.recall("flaky", "s-one", NOW + 61)
        self.assertEqual((first["counted"], first["ineffective"]), (True, False))
        self.assertEqual((second["counted"], second["ineffective"]), (False, False))
        row = self.row("flaky")
        self.assertEqual(row["counts"]["recall"], 2, "every recall is still logged and shown")
        self.assertFalse(row["ineffective"])
        self.assertEqual(self.box.json("show", "flaky", "--json")["recalls_since"], 1)
        self.assertEqual(self.box.json("events", "--unsettled", "--json"), [])
        status = json.loads(self.box.run("status", "--json").stdout)
        self.assertEqual(status["open"]["ineffective"], [])
        logged = [event for event in self.box.read_events() if event["type"] == "recall"]
        self.assertEqual([(event["counted"], event["ineffective"]) for event in logged], [(True, False), (False, False)])

    def test_recalls_in_two_sessions_do(self):
        self.box.add("flaky")
        first = self.recall("flaky", "s-one", NOW + 60)
        second = self.recall("flaky", "s-two", NOW + 61)
        self.assertEqual((first["counted"], first["ineffective"]), (True, False))
        self.assertEqual((second["counted"], second["ineffective"]), (True, True))
        self.assertTrue(self.row("flaky")["ineffective"])
        self.assertEqual(self.box.json("show", "flaky", "--json")["recalls_since"], 2)
        owed = self.box.json("events", "--unsettled", "--session", "s-two", "--json")
        self.assertEqual([(event["type"], event["lesson"]) for event in owed], [("recall", "flaky")])
        self.assertEqual(self.box.json("events", "--unsettled", "--session", "s-one", "--json"), [])

    def test_a_third_recall_in_the_session_that_made_it_ineffective_is_not_counted_again(self):
        self.box.add("flaky")
        self.recall("flaky", "s-one", NOW + 60)
        self.recall("flaky", "s-two", NOW + 61)
        third = self.recall("flaky", "s-two", NOW + 62)
        self.assertEqual((third["counted"], third["ineffective"]), (False, False))
        self.assertEqual(self.box.json("show", "flaky", "--json")["recalls_since"], 2)

    def test_a_rewrite_is_a_new_revision_and_the_same_session_counts_once_more(self):
        self.box.add("flaky")
        self.recall("flaky", "s-one", NOW + 60)
        self.assertExit(self.box.run("add", "--update", "--name", "flaky", "--match", "flaky", COMPOUND_NOW=NOW + 100,
                                     CLAUDE_CODE_SESSION_ID="s-one"), 0)
        self.assertEqual(self.box.json("show", "flaky", "--json")["recalls_since"], 0)
        again = self.recall("flaky", "s-one", NOW + 200)
        twice = self.recall("flaky", "s-one", NOW + 201)
        self.assertEqual((again["counted"], twice["counted"]), (True, False))
        self.assertEqual(self.box.json("show", "flaky", "--json")["recalls_since"], 1)
        self.assertFalse(self.row("flaky")["ineffective"])

    def test_the_limit_counts_sessions(self):
        self.box.add("flaky")
        said = []
        for index, session in enumerate(("s-one", "s-one", "s-two", "s-two", "s-three")):
            said.append(self.recall("flaky", session, NOW + 60 + index, COMPOUND_RECUR_LIMIT=None)["ineffective"])
        self.assertEqual(said, [False, False, True, False, True])
        proc = self.box.run("list", "--json", COMPOUND_RECUR_LIMIT="4")
        self.assertFalse([row for row in json.loads(proc.stdout) if row["name"] == "flaky"][0]["ineffective"])

    def test_a_general_lesson_recurs_by_sessions_too_and_is_never_ineffective(self):
        self.box.write_lesson(self.box.lesson_dir("shipped-note", "general"), "shipped-note")
        os.utime(os.path.join(self.box.lesson_dir("shipped-note", "general"), "SKILL.md"), (NOW, NOW))
        self.recall("shipped-note", "s-one", NOW + 60)
        same = self.recall("shipped-note", "s-one", NOW + 61)
        self.assertFalse(self.row("shipped-note")["recurring"])
        other = self.recall("shipped-note", "s-two", NOW + 62)
        self.assertEqual((same["counted"], same["ineffective"], other["counted"], other["ineffective"]),
                         (False, False, True, False))
        row = self.row("shipped-note")
        self.assertEqual((row["recurring"], row["ineffective"], row["counts"]["recall"]), (True, False, 3))

    def test_a_recall_after_the_lessons_own_guard_refused_is_still_not_counted(self):
        self.box.add("flaky", "Use when.", "Body.\n", "--match", "flaky")
        self.box.log({"type": "guard", "lesson": "flaky"}, COMPOUND_NOW=NOW + 50, CLAUDE_CODE_SESSION_ID="s-one")
        after = self.recall("flaky", "s-one", NOW + 60)
        self.assertEqual((after["counted"], after["ineffective"]), (False, False))
        self.assertEqual(self.box.json("show", "flaky", "--json")["recalls_since"], 0)

    def test_an_event_that_says_ineffective_itself_is_kept_as_it_is(self):
        """`log` fills the field in when it is absent, as it fills `ts` and `id`."""
        self.box.add("flaky")
        kept = self.recall("flaky", "s-one", NOW + 60, ineffective=True)
        self.assertTrue(kept["ineffective"])

    def test_a_recall_of_a_name_that_is_no_lesson_is_logged_and_counts_for_nothing(self):
        gone = self.recall("no-such-lesson", "s-one", NOW + 60)
        self.assertEqual((gone["counted"], gone["ineffective"]), (False, False))


class RecurrenceByLessonTest(Case):
    """Two projects may each hold a lesson of one name. Their recalls are not shared."""

    def setUp(self):
        Case.setUp(self)
        self.other = os.path.join(self.box.root, "other-project")
        os.makedirs(self.other)
        self.box.add("build-flag", "Use when building here.", "Pass --profile dev.\n")
        self.box.add("build-flag", "Use when building there.", "Pass --release.\n", COMPOUND_PROJECT=self.other)

    def recall(self, session, at, project, **more):
        event = {"type": "recall", "lesson": "build-flag", "tool": "Bash", "call": "./build.sh", "error": "boom"}
        event.update(more)
        proc = self.box.run("log", "--json", stdin=json.dumps(event), COMPOUND_NOW=at, CLAUDE_CODE_SESSION_ID=session,
                            COMPOUND_PROJECT=project)
        self.assertExit(proc, 0)
        return json.loads(proc.stdout)

    def row(self, project):
        rows = [row for row in self.box.json("list", "--json", COMPOUND_PROJECT=project) if row["name"] == "build-flag"]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_two_projects_with_different_lessons_of_one_name_keep_their_own_counts(self):
        self.assertNotEqual(self.row(self.box.project)["description"], self.row(self.other)["description"])
        first = self.recall("s-one", NOW + 60, self.box.project)
        second = self.recall("s-two", NOW + 61, self.other)
        self.assertEqual((first["ineffective"], second["ineffective"]), (False, False),
                         "one recall of each lesson is not two recalls of either")
        here, there = self.row(self.box.project), self.row(self.other)
        self.assertEqual((here["counts"]["recall"], there["counts"]["recall"]), (1, 1))
        self.assertEqual((here["ineffective"], there["ineffective"]), (False, False))
        third = self.recall("s-three", NOW + 62, self.box.project)
        self.assertTrue(third["ineffective"])
        here, there = self.row(self.box.project), self.row(self.other)
        self.assertEqual((here["counts"]["recall"], there["counts"]["recall"]), (2, 1))
        self.assertEqual((here["ineffective"], there["ineffective"]), (True, False))
        shown = self.box.json("show", "build-flag", "--json", COMPOUND_PROJECT=self.other)
        self.assertEqual((shown["recalls_since"], shown["ineffective"]), (1, False))
        status = json.loads(self.box.run("status", "--json", COMPOUND_PROJECT=self.other).stdout)
        self.assertEqual(status["open"]["ineffective"], [])
        status = json.loads(self.box.run("status", "--json").stdout)
        self.assertEqual([row["name"] for row in status["open"]["ineffective"]], ["build-flag"])

    def test_the_other_counters_are_kept_apart_as_well(self):
        self.box.log({"type": "guard", "lesson": "build-flag"})
        self.box.log({"type": "reuse", "lessons": ["build-flag"]})
        self.box.log({"type": "reuse", "lessons": ["build-flag"]}, COMPOUND_PROJECT=self.other)
        here, there = self.row(self.box.project)["counts"], self.row(self.other)["counts"]
        self.assertEqual((here["guard"], here["reuse"], here["learn"]), (1, 1, 1))
        self.assertEqual((there["guard"], there["reuse"], there["learn"]), (0, 1, 1))

    def test_a_recall_names_the_lesson_it_was_by_level_and_path(self):
        """A lesson left in another project is recalled from a session elsewhere: the event's
        `project` is the session's, and `level` and `path` say whose lesson it was."""
        third = os.path.join(self.box.root, "third-project")
        os.makedirs(third)
        path = os.path.join(self.other, ".claude", "compound", "lessons", "build-flag")
        for index, session in enumerate(("s-one", "s-two")):
            said = self.recall(session, NOW + 60 + index, third, level="project", path=path)
            self.assertFalse(said["ineffective"], "a lesson left in another project is that project's to rewrite")
        here, there = self.row(self.box.project), self.row(self.other)
        self.assertEqual((here["counts"]["recall"], there["counts"]["recall"]), (0, 2))
        self.assertEqual((here["ineffective"], there["ineffective"]), (False, True))

    def test_a_user_lesson_is_one_lesson_in_every_project(self):
        self.box.add("zsh-thing", "Use when zsh.", "Quote it.\n", "--level", "user")
        for index, project in enumerate((self.box.project, self.other)):
            event = {"type": "recall", "lesson": "zsh-thing", "level": "user",
                     "path": self.box.lesson_dir("zsh-thing", "user")}
            self.box.log(event, COMPOUND_NOW=NOW + 60 + index, CLAUDE_CODE_SESSION_ID="s-%d" % index,
                         COMPOUND_PROJECT=project)
        for project in (self.box.project, self.other):
            row = [row for row in self.box.json("list", "--json", COMPOUND_PROJECT=project) if row["name"] == "zsh-thing"][0]
            self.assertEqual((row["counts"]["recall"], row["ineffective"]), (2, True))

    def test_a_lesson_that_moved_to_the_user_level_keeps_its_history(self):
        path = self.box.lesson_dir("build-flag")
        self.recall("s-one", NOW + 60, self.box.project, level="project", path=path)
        self.assertExit(self.box.run("promote", "build-flag", "--to", "user", "--as", "build-flag-here"), 0)
        # Under its new name it starts over; the other project's lesson was never touched.
        self.assertEqual(self.row(self.other)["counts"]["recall"], 0)
        self.box.add("solo", "Use when alone.", "Body.\n")
        solo = self.box.lesson_dir("solo")
        self.box.log({"type": "recall", "lesson": "solo", "level": "project", "path": solo}, COMPOUND_NOW=NOW + 70)
        self.assertExit(self.box.run("promote", "solo", "--to", "user"), 0)
        row = [row for row in self.box.json("list", "--json") if row["name"] == "solo"][0]
        self.assertEqual((row["level"], row["counts"]["recall"]), ("user", 1))


class SettlementScopeTest(Case):
    """One `learn` or `skip` settles one capture."""

    def capture(self, cid, failed, session="sess-0001-aaaa", offset=0):
        self.box.log({"type": "capture", "id": cid, "failed": failed, "error": "boom", "fixed": failed + " --fixed"},
                     COMPOUND_NOW=NOW + offset, CLAUDE_CODE_SESSION_ID=session)

    def owed(self, session="sess-0001-aaaa"):
        return [event["id"] for event in self.box.json("events", "--unsettled", "--session", session, "--json")
                if event["type"] == "capture"]

    def test_with_one_unsettled_capture_a_plain_add_or_skip_settles_it(self):
        self.capture("cap-1", "./deploy.sh")
        self.assertExit(self.box.run("add", "--name", "deploy-target", "--when", "Use when deploying.",
                                     stdin="Pass --target.\n", COMPOUND_NOW=NOW + 10), 0)
        self.assertEqual(self.owed(), [])
        self.capture("cap-2", "make dcos", offset=20)
        self.assertExit(self.box.run("skip", "--why", "a typo", COMPOUND_NOW=NOW + 30), 0)
        self.assertEqual(self.owed(), [])

    def test_with_two_a_plain_add_is_refused_and_lists_the_ids_and_the_failing_calls(self):
        self.capture("cap-1", "./deploy.sh\n  --second-line")
        self.capture("cap-2", "make dcos", offset=5)
        before = self.box.snapshot()
        proc = self.box.run("add", "--name", "deploy-target", "--when", "Use when deploying.", stdin="Pass --target.\n",
                            COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 2)
        self.assertIn("--settles ID", proc.stderr)
        self.assertIn("2 captures", proc.stderr)
        self.assertIn("cap-1  `./deploy.sh`", proc.stderr)
        self.assertIn("cap-2  `make dcos`", proc.stderr)
        self.assertNotIn("--second-line", proc.stderr, "the first line of each failing call")
        self.assertEqual(self.box.snapshot(), before, "a refused add wrote something")
        self.assertEqual(self.owed(), ["cap-1", "cap-2"])

    def test_with_two_a_plain_skip_is_refused_the_same_way(self):
        self.capture("cap-1", "./deploy.sh")
        self.capture("cap-2", "make dcos", offset=5)
        before = self.box.snapshot()
        proc = self.box.run("skip", "--why", "neither is worth it")
        self.assertExit(proc, 2)
        self.assertIn("--settles ID", proc.stderr)
        self.assertIn("cap-1  `./deploy.sh`", proc.stderr)
        self.assertIn("cap-2  `make dcos`", proc.stderr)
        self.assertEqual(self.box.snapshot(), before)

    def test_settles_names_one_and_the_other_stays_owed(self):
        self.capture("cap-1", "./deploy.sh")
        self.capture("cap-2", "make dcos", offset=5)
        self.assertExit(self.box.run("add", "--name", "deploy-target", "--when", "Use when deploying.",
                                     "--settles", "cap-1", stdin="Pass --target.\n", COMPOUND_NOW=NOW + 10), 0)
        self.assertEqual(self.owed(), ["cap-2"], "one lesson settled one capture, not both")
        # One is left, so a plain skip is enough again.
        self.assertExit(self.box.run("skip", "--why", "a typo", COMPOUND_NOW=NOW + 20), 0)
        self.assertEqual(self.owed(), [])

    def test_another_sessions_captures_do_not_make_settles_required(self):
        self.capture("cap-1", "./deploy.sh")
        self.capture("cap-other", "make dcos", session="sess-0002-bbbb", offset=5)
        self.assertExit(self.box.run("skip", "--why", "a typo", COMPOUND_NOW=NOW + 10), 0)
        self.assertEqual(self.owed(), [])
        self.assertEqual(self.owed("sess-0002-bbbb"), ["cap-other"])

    def test_an_update_in_a_session_that_owes_two_is_held_to_the_same_rule(self):
        self.box.add("existing")
        self.capture("cap-1", "./deploy.sh", offset=5)
        self.capture("cap-2", "make dcos", offset=6)
        proc = self.box.run("add", "--update", "--name", "existing", "--match", "deploy", COMPOUND_NOW=NOW + 10)
        self.assertExit(proc, 2)
        self.assertIn("--settles ID", proc.stderr)
        self.assertExit(self.box.run("add", "--update", "--name", "existing", "--match", "deploy", "--settles", "cap-2",
                                     COMPOUND_NOW=NOW + 10), 0)
        self.assertEqual(self.owed(), ["cap-1"])

    def test_an_older_log_line_without_settles_still_settles_what_its_session_owed(self):
        """The log is append-only and its old lines keep their meaning: a `learn` written
        before this rule, from a session with two captures, settled both."""
        self.capture("cap-1", "./deploy.sh")
        self.capture("cap-2", "make dcos", offset=5)
        seed_event(self.box.events, {"ts": "2026-09-21T14:20:00Z", "type": "learn", "session": "sess-0001-aaaa",
                                     "project": self.box.project, "lesson": "old-lesson", "level": "project"})
        self.assertEqual(self.owed(), [])


class PublishScanTest(Case):
    """`promote --to general`: what is scanned is a frozen copy, in full, and that copy is
    what is published. The upstream is a local bare repository (COMPOUND_UPSTREAM_GIT), so
    nothing here goes to GitHub."""

    KEY = "ghp_" + "A1b2C3d4E5" * 3

    def setUp(self):
        Case.setUp(self)
        self.upstream = os.path.join(self.box.root, "upstream.git")
        seedrepo = os.path.join(self.box.root, "seed")
        os.makedirs(os.path.join(seedrepo, "lessons"))
        with open(os.path.join(seedrepo, "lessons", ".gitkeep"), "w") as handle:
            handle.write("")
        os.makedirs(os.path.join(seedrepo, "lessons", "taken-name"))
        with open(os.path.join(seedrepo, "lessons", "taken-name", "SKILL.md"), "w") as handle:
            handle.write("---\nname: taken-name\ndescription: Use when taken.\n---\nThe pool's own.\n")
        git_ok("init", cwd=seedrepo)
        git_ok("add", "-A", cwd=seedrepo)
        git_ok("commit", "-m", "the pool", cwd=seedrepo)
        git_ok("clone", "--bare", seedrepo, self.upstream)
        self.git_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "COMPOUND_UPSTREAM_GIT": self.upstream,
                        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
                        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}

    def attach(self, name, data, mode=0o644):
        path = os.path.join(self.box.root, name)
        with open(path, "wb") as handle:
            handle.write(data)
        os.chmod(path, mode)
        return path

    def branches(self):
        return git_ok("branch", "--list", "--format=%(refname:short)", cwd=self.upstream).split()

    def published(self, branch, rel):
        import subprocess
        return subprocess.run(["git", "show", "%s:%s" % (branch, rel)], cwd=self.upstream, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True).stdout

    def test_a_credential_past_the_first_megabyte_of_an_attachment_is_found(self):
        big = self.attach("data.txt", b"x" * (1200 * 1024) + b"\ntoken " + self.KEY.encode() + b"\n")
        self.box.add("big-note", "Use when big.", "See data.txt.\n", "--level", "user", "--attach", big)
        plan = self.box.json("promote", "big-note", "--to", "general", "--json")
        self.assertEqual(plan["secrets"], ["data.txt: an API token"])
        proc = self.box.run("promote", "big-note", "--to", "general", "--yes", "--upstream", self.upstream, **self.git_env)
        self.assertExit(proc, 2)
        self.assertIn("data.txt: an API token", proc.stderr)
        self.assertNotIn(self.KEY, proc.stderr)
        self.assertEqual(self.branches(), ["main"])

    def test_a_file_that_cannot_be_read_is_refused_and_named(self):
        helper = self.attach("helper.sh", b"#!/bin/sh\necho ok\n")
        self.box.add("locked-note", "Use when locked.", "Run helper.sh.\n", "--level", "user", "--attach", helper)
        inside = os.path.join(self.box.lesson_dir("locked-note", "user"), "helper.sh")
        os.chmod(inside, 0)
        self.addCleanup(os.chmod, inside, 0o644)
        if os.access(inside, os.R_OK):
            self.skipTest("this user reads a file of mode 0 (root)")
        plan = self.box.json("promote", "locked-note", "--to", "general", "--json")
        self.assertEqual(len(plan["unpublishable"]), 1)
        self.assertTrue(plan["unpublishable"][0].startswith("helper.sh: cannot be read"), plan["unpublishable"])
        self.assertIn("NOT PUBLISHABLE", self.box.run("promote", "locked-note", "--to", "general").stdout)
        proc = self.box.run("promote", "locked-note", "--to", "general", "--yes", "--upstream", self.upstream, **self.git_env)
        self.assertExit(proc, 2)
        self.assertIn("helper.sh: cannot be read", proc.stderr)
        self.assertEqual(self.branches(), ["main"])
        self.assertFalse(any(event["type"] == "promote" for event in self.box.read_events()))

    def test_a_file_too_large_to_scan_is_refused_and_named_not_skipped(self):
        huge = self.attach("huge.bin", b"\0" * (8 * 1024 * 1024 + 1))
        self.box.add("huge-note", "Use when huge.", "See huge.bin.\n", "--level", "user", "--attach", huge)
        plan = self.box.json("promote", "huge-note", "--to", "general", "--json")
        self.assertEqual(len(plan["unpublishable"]), 1)
        self.assertTrue(plan["unpublishable"][0].startswith("huge.bin: 8388609 bytes"), plan["unpublishable"])
        proc = self.box.run("promote", "huge-note", "--to", "general", "--yes", "--upstream", self.upstream, **self.git_env)
        self.assertExit(proc, 2)
        self.assertIn("huge.bin", proc.stderr)
        self.assertIn("too large to scan", proc.stderr)
        self.assertEqual(self.branches(), ["main"])

    def test_what_is_published_is_what_was_scanned_byte_for_byte(self):
        script = b"#!/bin/sh\n# a helper\nprintf '%s\\n' \"caf\xc3\xa9\"\n"
        blob = bytes(range(256)) * 5000  # 1.28 MB: longer than the old scan read
        helper = self.attach("fix.sh", script, 0o755)
        data = self.attach("table.bin", blob)
        self.box.add("zsh-equals-word", "Use when a zsh line has a bare equals word.", "Quote the word.\n",
                     "--level", "user", "--match", r"echo\s+=+", "--attach", helper, "--attach", data)
        plan = self.box.json("promote", "zsh-equals-word", "--to", "general", "--json")
        self.assertEqual((plan["secrets"], plan["unpublishable"]), ([], []))
        before = self.box.snapshot(self.box.chome)
        proc = self.box.run("promote", "zsh-equals-word", "--to", "general", "--yes", "--upstream", self.upstream, "--json", **self.git_env)
        self.assertExit(proc, 0)
        done = json.loads(proc.stdout)
        branch = "compound/lesson-zsh-equals-word"
        self.assertEqual(sorted(self.branches()), [branch, "main"])
        self.assertEqual(done["url"], "%s#%s" % (self.upstream, branch))
        base = "lessons/zsh-equals-word/"
        self.assertEqual(self.published(branch, base + "fix.sh"), script)
        self.assertEqual(self.published(branch, base + "table.bin"), blob)
        self.assertEqual(self.published(branch, base + "SKILL.md").decode("utf-8"), plan["skill_md"])
        self.assertNotIn(b"origin:", self.published(branch, base + "SKILL.md"))
        tree = git_ok("ls-tree", "-r", branch, cwd=self.upstream).splitlines()
        self.assertEqual(sorted(line.split("\t")[1] for line in tree),
                         ["lessons/.gitkeep", "lessons/taken-name/SKILL.md", base + "SKILL.md", base + "fix.sh",
                          base + "table.bin"])
        modes = {line.split("\t")[1]: line.split()[0] for line in tree}
        self.assertEqual((modes[base + "fix.sh"], modes[base + "table.bin"]), ("100755", "100644"))
        # The lesson stays where it was, and one `promote` event was logged.
        after = self.box.snapshot(self.box.chome)
        after.pop("events.jsonl")
        before.pop("events.jsonl")
        self.assertEqual(after, before)
        event = self.box.read_events()[-1]
        self.assertEqual((event["type"], event["lesson"], event["to"], event["url"]),
                         ("promote", "zsh-equals-word", "general", done["url"]))

    def test_the_staging_copy_is_removed_and_the_dry_run_writes_nothing(self):
        helper = self.attach("fix.sh", b"#!/bin/sh\necho ok\n")
        self.box.add("plain-note", "Use when plain.", "Body.\n", "--level", "user", "--attach", helper)
        scratch = os.path.join(self.box.root, "scratch")
        os.makedirs(scratch)
        before = self.box.snapshot()
        self.assertExit(self.box.run("promote", "plain-note", "--to", "general", TMPDIR=scratch), 0)
        self.assertExit(self.box.run("promote", "plain-note", "--to", "general", "--yes", "--upstream", self.upstream, TMPDIR=scratch,
                                     **self.git_env), 0)
        self.assertEqual(os.listdir(scratch), [], "the staging copy and the clone were left behind")
        after = self.box.snapshot()
        changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key)
                         and not key.startswith("upstream.git"))
        self.assertEqual(changed, [os.path.relpath(self.box.events, self.box.root)])

    def test_a_name_the_pool_already_holds_is_refused_and_nothing_is_pushed(self):
        self.box.add("taken-name", "Use when mine.", "My own.\n", "--level", "user")
        proc = self.box.run("promote", "taken-name", "--to", "general", "--yes", "--upstream", self.upstream, **self.git_env)
        self.assertExit(proc, 1)
        self.assertIn("lessons/taken-name already exists", proc.stderr)
        self.assertEqual(self.branches(), ["main"])
        self.assertFalse(any(event["type"] == "promote" for event in self.box.read_events()))

    def test_a_file_swapped_for_a_link_after_the_listing_is_not_followed(self):
        """The staging copy opens each file without following a link, so a path that
        became a link to something outside the lesson is refused, not published."""
        secret = self.attach("outside.txt", b"token " + self.KEY.encode() + b"\n")
        helper = self.attach("fix.sh", b"#!/bin/sh\necho ok\n")
        self.box.add("linked-note", "Use when linked.", "Body.\n", "--level", "user", "--attach", helper)
        inside = os.path.join(self.box.lesson_dir("linked-note", "user"), "fix.sh")
        os.unlink(inside)
        os.symlink(secret, inside)
        plan = self.box.json("promote", "linked-note", "--to", "general", "--json")
        self.assertEqual(plan["files"], ["lessons/linked-note/SKILL.md"])
        self.assertEqual(plan["excluded"], ["fix.sh"])
        self.assertExit(self.box.run("promote", "linked-note", "--to", "general", "--yes", "--upstream", self.upstream, **self.git_env), 0)
        tree = git_ok("ls-tree", "-r", "--name-only", "compound/lesson-linked-note", cwd=self.upstream).splitlines()
        self.assertNotIn("lessons/linked-note/fix.sh", tree)


if __name__ == "__main__":
    unittest.main()
