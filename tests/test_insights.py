#!/usr/bin/env python3
"""`compound insights`: the harvest of what Claude Code's /insights wrote under usage-data/."""

import fcntl
import json
import os
import subprocess
import sys
import time
import unittest

from test_support import NOW, Case, git_ok, iso, write_usage_data

SESSION = "11111111-aaaa-bbbb-cccc-000000000001"


def facet(session, detail="The run kept using the wrong flag.", counts=None, goal="Build a small tool"):
    return {"underlying_goal": goal, "friction_counts": {"wrong_approach": 1} if counts is None else counts,
            "friction_detail": detail, "session_id": session}


class HarvestTest(Case):
    def repo(self, name="repo"):
        path = os.path.join(self.box.root, name)
        os.makedirs(path)
        git_ok("init", "-q", cwd=path)
        return os.path.realpath(path)

    def usage(self, facets, meta=None, items=None):
        return write_usage_data(self.box.claude, facets, meta or {}, items)

    def harvest(self, **kw):
        return self.box.json("insights", "--harvest", "--json", **kw)

    def insights(self):
        return [event for event in self.box.read_events() if event["type"] == "insight"]

    def errors(self):
        return [event for event in self.box.read_events() if event["type"] == "error"]

    def one_session(self, detail="The run kept using the wrong flag.", project=None, **more):
        project = project or self.repo()
        self.usage({SESSION: facet(SESSION, detail, **more)}, {SESSION: {"session_id": SESSION, "project_path": project}})
        return project

    def test_a_facet_with_friction_becomes_one_event_in_its_project(self):
        repo = self.repo()
        self.usage({SESSION: facet(SESSION, "x", {"wrong_approach": 2})},
                   {SESSION: {"session_id": SESSION, "project_path": repo}})
        result = self.harvest()
        self.assertEqual((result["new"], result["facets"], result["outcome"]), (1, 1, "ok"))
        (event,) = self.insights()
        self.assertEqual(event["source"], "facet")
        self.assertEqual(event["project"], os.path.realpath(repo))
        self.assertEqual(event["kinds"], ["wrong_approach"])
        self.assertEqual(event["session"], "insights")
        self.assertEqual(event["of"], SESSION)
        self.assertEqual((event["text"], event["goal"], event["learned"]), ("x", "Build a small tool", []))
        self.assertEqual(event["ts"], iso(NOW))
        self.assertRegex(event["id"], r"^in-[0-9a-f]{16}$")

    def test_harvesting_twice_writes_nothing_twice(self):
        self.one_session()
        self.assertEqual(self.harvest()["new"], 1)
        before = self.box.read_events()
        self.assertEqual(self.harvest()["new"], 0)
        self.assertEqual(self.box.read_events(), before)

    def test_a_facet_without_friction_detail_is_not_a_finding(self):
        self.one_session(detail="")
        result = self.harvest()
        self.assertEqual((result["new"], result["facets"], result["skipped"], result["outcome"]), (0, 1, 0, "ok"))
        self.assertEqual(self.insights(), [])

    def test_a_session_started_in_a_subdirectory_lands_at_the_repository_root(self):
        repo = self.repo()
        sub = os.path.join(repo, "src", "deep")
        os.makedirs(sub)
        link = os.path.join(self.box.root, "link")
        os.symlink(sub, link)
        other = "22222222-aaaa-bbbb-cccc-000000000002"
        self.usage({SESSION: facet(SESSION), other: facet(other)},
                   {SESSION: {"session_id": SESSION, "project_path": sub},
                    other: {"session_id": other, "project_path": link}})
        self.assertEqual(self.harvest()["new"], 2)
        self.assertEqual({event["project"] for event in self.insights()}, {repo})

    def test_a_facet_whose_project_is_gone_or_has_no_metadata_is_dropped(self):
        gone = "33333333-aaaa-bbbb-cccc-000000000003"
        bare = "44444444-aaaa-bbbb-cccc-000000000004"
        self.usage({gone: facet(gone), bare: facet(bare)},
                   {gone: {"session_id": gone, "project_path": os.path.join(self.box.root, "removed")}})
        result = self.harvest()
        self.assertEqual((result["new"], result["dropped"], result["skipped"], result["outcome"]), (0, 2, 0, "ok"))
        self.assertEqual(self.insights(), [])

    def test_learned_names_the_lessons_that_session_wrote(self):
        self.one_session()
        self.box.seed({"type": "learn", "session": SESSION, "lesson": "a-lesson"})
        self.box.seed({"type": "learn", "session": "another", "lesson": "not-this-one"})
        self.assertEqual(self.harvest()["new"], 1)
        self.assertEqual(self.insights()[0]["learned"], ["a-lesson"])

    def test_malformed_facets_are_skipped_and_the_rest_harvested(self):
        repo = self.repo()
        top = self.usage({SESSION: facet(SESSION)}, {SESSION: {"session_id": SESSION, "project_path": repo}})
        directory = os.path.join(top, "facets")

        def put(name, data):
            with open(os.path.join(directory, name + ".json"), "wb") as handle:
                handle.write(data)

        put("a", b"[1, 2]")
        put("b", b'{"friction_detail": "\xff\xfe", "session_id": "b"}')
        put("c", b'{"friction_detail": "' + b"x" * 999978 + b'"}')
        put("d", json.dumps({"friction_detail": "x", "friction_counts": "many", "session_id": "d"}).encode())
        put("e", json.dumps({"friction_detail": "x", "session_id": "not-e"}).encode())
        self.assertEqual(os.path.getsize(os.path.join(directory, "c.json")), 1000001)
        result = self.harvest()
        self.assertEqual((result["facets"], result["skipped"], result["new"], result["outcome"]), (6, 5, 1, "ok"))
        self.assertEqual([event["of"] for event in self.insights()], [SESSION])

    def test_every_facet_malformed_is_unreadable_and_offers_nothing(self):
        self.usage({}, {}, [("Use the flag.", "Because it helps.")])
        with open(os.path.join(self.box.claude, "usage-data", "facets", "a.json"), "w") as handle:
            json.dump({"friction_detail": 7, "session_id": "a"}, handle)
        result = self.harvest()
        self.assertEqual((result["outcome"], result["new"], result["skipped"]), ("unreadable", 0, 1))
        self.assertEqual(self.insights(), [])
        (error,) = self.errors()
        self.assertEqual(error["where"], "insights.harvest")
        self.assertIn("a.json", error["message"])
        self.assertIn("friction_detail", error["message"])
        self.assertEqual(self.box.json("insights", "--json")["outcome"], "unreadable")

    def test_kinds_keep_only_slugs_and_at_most_eight(self):
        counts = {"kind_%s" % letter: 1 for letter in "abcdefghij"}
        counts.update({"Bad Kind": 1, "x" * 41: 1, "with-dash": 1})
        self.one_session(counts=counts)
        self.harvest()
        self.assertEqual(self.insights()[0]["kinds"], ["kind_%s" % letter for letter in "abcdefgh"])

    def test_a_trailing_newline_makes_neither_a_kind_nor_a_session_id(self):
        self.one_session(counts={"wrong\n": 1, "right": 1})
        self.harvest()
        self.assertEqual(self.insights()[0]["kinds"], ["right"])
        bad = "55555555-aaaa\n"
        top = os.path.join(self.box.claude, "usage-data", "facets")
        with open(os.path.join(top, bad + ".json"), "w") as handle:
            json.dump(facet(bad), handle)
        self.assertEqual(self.harvest()["skipped"], 1)

    def test_text_is_one_line_masked_and_cut(self):
        self.one_session(detail=("word " * 70) + "\nsecond line password=hunter2secret " + "y" * 400, goal="g" * 500)
        self.harvest()
        (event,) = self.insights()
        self.assertLessEqual(len(event["text"]), 600)
        self.assertNotIn("\n", event["text"])
        self.assertNotIn("hunter2secret", event["text"])
        self.assertLessEqual(len(event["goal"]), 200)

    def test_a_secret_that_straddles_the_cut_is_masked_before_the_cut(self):
        self.one_session(detail=("word " * 118) + "password=hunter2secret")
        self.harvest()
        self.assertNotIn("hunter2", self.insights()[0]["text"])

    def test_report_items_become_findings_without_a_project_once(self):
        self.usage({}, {}, [("Prefer rg over grep.", "It was faster."), ("Run   the tests\nfirst.", "Failures hid.")])
        self.assertEqual(self.harvest()["report"], 2)
        self.assertEqual(self.harvest()["report"], 0)
        events = self.insights()
        self.assertEqual(len(events), 2)
        for event in events:
            self.assertEqual(event["source"], "report")
            self.assertNotIn("project", event)
            self.assertEqual(event["session"], "insights")
            self.assertRegex(event["id"], r"^in-[0-9a-f]{16}$")
        self.assertEqual([event["why"] for event in events], ["It was faster.", "Failures hid."])

    def test_a_report_item_with_other_spacing_is_the_same_finding(self):
        self.usage({}, {}, [("Prefer   RG over grep.", "a")])
        self.harvest()
        self.usage({}, {}, [("prefer rg\nover grep.", "b")])
        self.assertEqual(self.harvest()["report"], 0)
        self.assertEqual(len(self.insights()), 1)

    def test_a_report_with_the_section_and_no_parsable_item_is_unreadable(self):
        self.usage({}, {}, [])
        result = self.harvest()
        self.assertEqual((result["outcome"], result["report"]), ("unreadable", 0))
        (error,) = self.errors()
        self.assertIn("report.html", error["message"])

    def test_an_unreadable_report_withholds_the_good_facet_findings_too(self):
        self.one_session()
        write_usage_data(self.box.claude, {}, {}, [])
        result = self.harvest()
        self.assertEqual((result["outcome"], result["new"]), ("unreadable", 0))
        self.assertEqual(self.insights(), [])

    def test_a_state_file_that_cannot_be_written_does_not_fail_a_harvest_that_recorded(self):
        self.one_session()
        os.makedirs(self.box.chome)
        os.mkdir(os.path.join(self.box.chome, "insights.json"))
        proc = self.box.run("insights", "--harvest", "--json")
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout)["new"], 1)
        self.assertIn("state file", proc.stderr)
        self.assertEqual(len(self.insights()), 1)

    def test_no_usage_data_directory_is_ok_and_empty(self):
        result = self.harvest()
        self.assertEqual((result["outcome"], result["new"], result["facets"], result["report"]), ("ok", 0, 0, 0))
        self.assertEqual(self.box.read_events(), [])

    def test_the_claude_directory_follows_claude_config_dir_when_compound_has_none(self):
        other = os.path.join(self.box.root, "elsewhere")
        write_usage_data(other, {}, {}, [("Prefer rg over grep.", "It was faster.")])
        result = self.harvest(COMPOUND_CLAUDE_DIR=None, CLAUDE_CONFIG_DIR=other)
        self.assertEqual(result["report"], 1)

    def test_compound_log_refuses_an_insight_event(self):
        proc = self.box.run("log", stdin=json.dumps({"type": "insight"}))
        self.assertExit(proc, 2)
        self.assertIn("compound insights", proc.stderr)

    def test_the_state_command_prints_the_last_outcome(self):
        self.assertIsNone(self.box.json("insights", "--json")["outcome"])
        self.one_session()
        self.harvest()
        state = self.box.json("insights", "--json")
        self.assertEqual(state["outcome"], "ok")
        self.assertEqual(state["finished"], iso(NOW))
        self.assertEqual(state["harvested"], {"facets": 1, "findings": 1, "report": 0, "skipped": 0, "dropped": 0})
        text = self.box.run("insights")
        self.assertExit(text, 0)
        self.assertIn("ok", text.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.box.chome, "insights.lock")))

    def test_a_harvest_waits_for_the_lock_and_then_records(self):
        self.one_session()
        os.makedirs(self.box.chome)
        fd = os.open(os.path.join(self.box.chome, "insights.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            proc = subprocess.Popen([sys.executable, self.box.script, "insights", "--harvest", "--json"],
                                    cwd=self.box.project, env=self.box.env(), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            self.addCleanup(proc.kill)
            time.sleep(1.5)
            self.assertIsNone(proc.poll(), "the harvest did not wait for the lock")
            self.assertEqual(self.insights(), [])
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(json.loads(out)["new"], 1)
        self.assertEqual(len(self.insights()), 1)


    def test_the_state_command_lists_each_finding_with_its_state(self):
        self.assertEqual(self.box.json("insights", "--json")["findings"], [])
        project = self.one_session("The run kept using the wrong flag.")
        self.harvest()
        (event,) = self.insights()
        (row,) = self.box.json("insights", "--json")["findings"]
        self.assertEqual(row, {"id": event["id"], "source": "facet", "project": project, "state": "open",
                               "text": "The run kept using the wrong flag."})
        listing = self.box.run("insights")
        self.assertExit(listing, 0)
        self.assertIn(event["id"], listing.stdout)
        self.assertIn("open", listing.stdout)


if __name__ == "__main__":
    unittest.main()
