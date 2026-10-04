#!/usr/bin/env python3
"""report: what the event log says the package did, each figure as numerator/denominator."""

import json
import os
import time
import unittest

from test_support import NOW, Case

DAY = 86400


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def fig(n, of, pct=None):
    return {"n": n, "of": of, "pct": pct}


def spread(n, median=None, p90=None):
    return {"n": n, "median": median, "p90": p90}


class ReportCase(Case):
    def ev(self, kind, ago, session="s1", **fields):
        """One event `ago` seconds before NOW: appended by the real `compound log`, or, for a
        type only a command of the CLI writes, seeded into the sandbox's log."""
        event = dict(fields, type=kind, ts=iso(NOW - ago), session=session)
        self.box.put(event)
        return self.box.read_events()[-1]

    def report(self, *args, **kw):
        return self.box.json("report", "--json", *args, **kw)

    def text(self, *args, **kw):
        proc = self.box.run("report", *args, **kw)
        self.assertExit(proc, 0)
        return proc.stdout


EMPTY_VERDICTS = {name: fig(0, 0) for name in ("named", "nothing", "not-substantial", "unanswered", "unreadable")}


class EmptyLogTest(ReportCase):
    def test_no_log_at_all_is_a_report_of_zeros_and_no_rate(self):
        data = self.report()
        self.assertEqual(data["min_n"], 10)
        self.assertEqual(data["window"], {
            "since": None, "until": None, "project": None, "first": None, "last": None, "events": 0,
            "sessions": 0, "unparseable": 0, "untimed": 0, "unread": {}})
        self.assertEqual(data["learn"], {
            "captures": 0, "recorded": fig(0, 0), "declined": fig(0, 0), "unsettled": fig(0, 0),
            "expired": fig(0, 0), "reasons": [], "settle_seconds": spread(0), "reminded": 0,
            "stops_refused": {"debt": 0, "strengthen": 0, "nudge": 0}, "nudges": 0, "lessons_recorded": 0,
            "lessons_rewritten": 0, "moved": 0, "candidates": 0})
        self.assertEqual(data["guards"], {
            "refusals": 0, "watched": 0, "changed": fig(0, 0), "same": fig(0, 0), "none": fig(0, 0),
            "unwatched": 0, "failed_after": fig(0, 0), "lessons": []})
        self.assertEqual(data["recall"], {
            "recalls": 0, "after_guard": fig(0, 0), "again": fig(0, 0), "ineffective": fig(0, 0), "owed": 0,
            "rewritten": fig(0, 0), "declined": fig(0, 0), "wrong_lesson": fig(0, 0), "removed": fig(0, 0),
            "open": fig(0, 0), "lessons": []})
        self.assertEqual(data["reuse"], {
            "checks": None, "reached": 0, "judged": fig(0, 0), "memo": fig(0, 0), "verdicts": EMPTY_VERDICTS, "offers": 0, "earlier_requests": 0, "items": [],
            "used": None})
        self.assertEqual(data["judge"]["calls"], 0)
        self.assertEqual(data["judge"]["ms"], spread(0))
        self.assertEqual(data["judge"]["moments"]["fix"], {
            "calls": 0, "ms": spread(0),
            "verdicts": {name: fig(0, 0) for name in ("fix", "known", "none", "unanswered", "unreadable")}})
        self.assertEqual(data["cost"]["errors"], {"total": 0, "kinds": []})
        self.assertEqual(sorted(data), ["cost", "guards", "judge", "learn", "min_n", "not_measured", "recall",
                                        "reuse", "window"])

    def test_the_text_of_an_empty_log_says_so_and_claims_no_rate(self):
        text = self.text()
        self.assertIn("the event log holds no event", text)
        self.assertNotIn("%", text)
        heads = [line for line in text.splitlines() if line and not line.startswith(" ")]
        self.assertEqual(heads, ["Window", "The learn loop", "Guards", "Recall", "Reuse", "The judge",
                                 "Cost to the user", "Not measured"])

    def test_report_writes_nothing(self):
        self.ev("guard", 50, lesson="a-guard", tool="Bash", text="echo ===")
        before = self.box.snapshot()
        self.report()
        self.text()
        self.assertEqual(self.box.snapshot(), before)


class LearnLoopTest(ReportCase):
    def seed(self):
        old = self.ev("capture", 20 * DAY, "s5", tool="Bash", failed="e", fixed="f")
        one = self.ev("capture", 5000, "s1", tool="Bash", failed="a", fixed="b")
        self.box.add("fix-one", "Use when a fails.", "Run b.\n", "--settles", one["id"], COMPOUND_NOW=NOW - 4900)
        two = self.ev("capture", 4000, "s2", tool="Bash", failed="c", fixed="d")
        self.assertExit(self.box.run("skip", "--why", "one-off: a typo in a file name", "--settles", two["id"],
                                     COMPOUND_NOW=NOW - 3700), 0)
        three = self.ev("capture", 3000, "s3", tool="Bash", failed="g", fixed="h")
        self.assertExit(self.box.run("skip", "--why", "One-off; nothing reusable", "--settles", three["id"],
                                     COMPOUND_NOW=NOW - 2500), 0)
        self.ev("capture", 1000, "s4", tool="Bash", failed="i", fixed="j")
        self.ev("remind", 900, "s6", captures=[old["id"]])
        self.ev("refuse", 800, "s4", why="debt")
        self.ev("refuse", 700, "s4", why="strengthen")
        self.ev("nudge", 600, "s4", calls=30)
        self.ev("refuse", 590, "s4", why="nudge")

    def test_each_capture_is_counted_by_how_it_ended(self):
        self.seed()
        learn = self.report()["learn"]
        self.assertEqual(learn, {
            "captures": 5, "recorded": fig(1, 5), "declined": fig(2, 5), "unsettled": fig(1, 5),
            "expired": fig(1, 5), "reasons": [{"reason": "one-off", "n": 2}], "settle_seconds": spread(3),
            "reminded": 1, "stops_refused": {"debt": 1, "strengthen": 1, "nudge": 1}, "nudges": 1,
            "lessons_recorded": 1, "lessons_rewritten": 0, "moved": 0, "candidates": 0})

    def test_the_text_gives_counts_over_the_captures_and_no_percentage_for_five(self):
        self.seed()
        text = self.text()
        self.assertRegex(text, r"(?m)^  captures +5$")
        self.assertRegex(text, r"(?m)^  a lesson recorded +1/5 \(n is too small: 5\)$")
        self.assertRegex(text, r"(?m)^  declined +2/5 \(n is too small: 5\)$")
        self.assertRegex(text, r"(?m)^    2  one-off$")
        self.assertRegex(text, r"(?m)^  still unsettled +1/5 \(n is too small: 5\)$")
        self.assertRegex(text, r"(?m)^  expired .*1/5 \(n is too small: 5\)$")
        self.assertRegex(text, r"(?m)^  capture to settlement +n is too small: 3$")

    def test_ten_settled_captures_have_a_rate_and_a_median(self):
        for index in range(10):
            cap = self.ev("capture", 9000 - index * 100, "c%d" % index, tool="Bash", failed="a%d" % index, fixed="b")
            # Settled 10, 20, ... 100 seconds later.
            self.ev("skip", 9000 - index * 100 - 10 * (index + 1), "c%d" % index, why="not worth keeping")
        learn = self.report()["learn"]
        self.assertEqual(learn["declined"], fig(10, 10, 100.0))
        self.assertEqual(learn["recorded"], fig(0, 10, 0.0))
        self.assertEqual(learn["settle_seconds"], spread(10, 55, 90))
        self.assertEqual(learn["reasons"], [{"reason": "not worth keeping", "n": 10}])
        text = self.text()
        self.assertRegex(text, r"(?m)^  declined +10/10 \(100\.0%\)$")
        self.assertRegex(text, r"(?m)^  capture to settlement +median 55 s, p90 90 s \(n=10\)$")


class GuardsTest(ReportCase):
    def seed(self):
        self.ev("guard", 900, "g1", lesson="no-echo", tool="Bash", text="echo ===", ms=50, watched=True)
        self.ev("retry", 890, "g1", lessons=["no-echo"], tool="Bash", same=False, text="printf '%s\\n' ===")
        self.ev("guard", 800, "g2", lesson="no-echo", tool="Bash", text="echo ===", ms=60, watched=True)
        self.ev("retry", 790, "g2", lessons=["no-echo"], tool="Bash", same=True, text="echo ===")
        self.ev("recall", 780, "g2", lesson="no-echo", tool="Bash", call="echo ===", error="x")
        self.ev("guard", 700, "g3", lesson="no-echo", tool="Bash", text="echo ===", ms=70, watched=True)
        self.ev("guard", 600, "g4", lesson="other-guard", tool="Bash", text="timeout 5 ls", ms=80)
        self.ev("guard", 500, "g5", lesson="no-echo", tool="Bash", text="echo ===", watched=True)
        # A follow-up that does not say whether the call was the same one says nothing.
        self.ev("retry", 490, "g5", lessons=["no-echo"], tool="Bash")

    def test_what_followed_each_refusal_is_read_from_the_retry_events(self):
        self.seed()
        guards = self.report()["guards"]
        self.assertEqual(guards, {
            "refusals": 5, "watched": 4, "changed": fig(1, 4), "same": fig(1, 4), "none": fig(2, 4),
            "unwatched": 1, "failed_after": fig(1, 5),
            "lessons": [
                {"name": "no-echo", "refusals": 4, "watched": 4, "changed": 1, "same": 1, "none": 2,
                 "failed_after": 1},
                {"name": "other-guard", "refusals": 1, "watched": 0, "changed": 0, "same": 0, "none": 0,
                 "failed_after": 0},
            ]})

    def test_the_text_names_the_field_a_refusal_lacks(self):
        self.seed()
        text = self.text()
        self.assertRegex(text, r"(?m)^  refusals +5$")
        self.assertRegex(text, r"(?m)^  then a different call +1/4 \(n is too small: 4\)$")
        self.assertRegex(text, r"(?m)^  then the same call again +1/4 \(n is too small: 4\)$")
        self.assertRegex(text, r"(?m)^  then no call of that tool +2/4 \(n is too small: 4\)$")
        self.assertIn("1 refusal carries no `watched` field", text)
        self.assertRegex(text, r"(?m)^  no-echo +4 +4 +1 +1 +2 +1$")

    def test_a_guard_time_is_part_of_the_cost(self):
        self.seed()
        self.assertEqual(self.report()["cost"]["tool_call"]["guard_ms"], spread(4))


class RecallTest(ReportCase):
    def seed(self):
        self.box.add("lesson-a", "Use when a fails.", "Do the other thing.\n", COMPOUND_NOW=NOW - 9000)
        self.ev("recall", 5000, "r1", lesson="lesson-a", tool="Bash", call="x", error="e", ineffective=False)
        self.ev("recall", 4900, "r1", lesson="lesson-a", tool="Bash", call="x", error="e", ineffective=True)
        # Marked a second time in the same session: one debt, which the one decline settles.
        self.ev("recall", 4850, "r1", lesson="lesson-a", tool="Bash", call="x", error="e", ineffective=True)
        self.ev("skip", 4800, "r1", why="the recalled lesson does not describe this failure: wc met a directory")
        self.ev("recall", 4000, "r2", lesson="lesson-a", tool="Bash", call="x", error="e", ineffective=True)
        self.assertExit(self.box.run("add", "--update", "--name", "lesson-a", "--when", "Use when a fails with e.",
                                     COMPOUND_NOW=NOW - 3900, CLAUDE_CODE_SESSION_ID="r2"), 0)
        self.ev("recall", 3000, "r3", lesson="lesson-b", tool="Bash", call="y", error="e", ineffective=True)
        self.ev("guard", 2100, "r4", lesson="lesson-a", tool="Bash", text="x")
        self.ev("recall", 2000, "r4", lesson="lesson-a", tool="Bash", call="x", error="e")
        self.ev("recall", 1000, "r5", lesson="lesson-c", tool="Bash", call="z", error="e", ineffective=True)
        self.ev("skip", 900, "r5", why="not worth a pattern")

    def test_recalls_are_counted_by_what_came_after(self):
        self.seed()
        recall = self.report()["recall"]
        self.assertEqual(recall, {
            "recalls": 7, "after_guard": fig(1, 7), "again": fig(3, 7), "ineffective": fig(5, 7), "owed": 4,
            "rewritten": fig(1, 4), "declined": fig(2, 4), "wrong_lesson": fig(1, 4), "removed": fig(0, 4),
            "open": fig(1, 4),
            "lessons": [
                {"name": "lesson-a", "recalls": 5, "after_guard": 1, "again": 3, "ineffective": 3,
                 "wrong_lesson": 1},
                {"name": "lesson-b", "recalls": 1, "after_guard": 0, "again": 0, "ineffective": 1,
                 "wrong_lesson": 0},
                {"name": "lesson-c", "recalls": 1, "after_guard": 0, "again": 0, "ineffective": 1,
                 "wrong_lesson": 0},
            ]})

    def test_the_text_says_how_many_declines_said_the_lesson_was_the_wrong_one(self):
        self.seed()
        text = self.text()
        self.assertRegex(text, r"(?m)^  recalls +7$")
        self.assertRegex(text, r"(?m)^  the same lesson recalled again later +3/7 \(n is too small: 7\)$")
        self.assertRegex(text, r"(?m)^  marked ineffective +5/7 \(n is too small: 7\)$")
        self.assertRegex(text, r"(?m)^  stronger lessons owed +4$")
        self.assertRegex(text, r"(?m)^    declined: the lesson does not describe the failure +1/4 \(n is too small: 4\)$")
        self.assertRegex(text, r"(?m)^  lesson-a +5 +1 +3 +3 +1$")

    def test_the_rewrite_and_the_new_lesson_are_counted_apart(self):
        self.seed()
        learn = self.report()["learn"]
        self.assertEqual((learn["lessons_recorded"], learn["lessons_rewritten"]), (1, 1))


class ReuseJudgeCostTest(ReportCase):
    def judge(self, ago, moment, verdict, ms, **more):
        return self.ev("judge", ago, "j%d" % ago, moment=moment, verdict=verdict, ms=ms, **more)

    def seed(self):
        self.judge(9000, "reuse", "named", 500, named=["x"])
        self.judge(8900, "reuse", "nothing", 700)
        self.judge(7900, "reuse", "named", 900, named=["x"])
        self.judge(7800, "reuse", "named", 0, memo=True, named=["x"])
        self.judge(7700, "reuse", "nothing", 300)
        self.judge(7600, "reuse", "not-substantial", 400)
        self.judge(7500, "reuse", "unanswered", 10000, reason="no answer within 10 s")
        self.judge(7400, "reuse", "unreadable", 600)
        self.judge(7200, "reuse", "not-substantial", 800)
        self.judge(7100, "reuse", "nothing", 1000)
        self.judge(7000, "reuse", "named", 1100, named=["x", "bin/tool"])
        self.judge(6000, "recall", "named", 650, tool="Bash", named=["x"])
        self.judge(5900, "recall", "none", 750, tool="Bash")
        self.judge(5800, "fix", "fix", 2000, tool="Bash")
        self.judge(5700, "fix", "none", 1500, tool="Bash", reason="next step")
        self.judge(5600, "fix", "known", 1200, tool="Bash", named=["x"])
        self.ev("reuse", 6990, "j7000", lessons=["x", "bin/tool"], prompts=["p1"], ms=1200, gather_ms=200, judge_ms=900)
        self.ev("reuse", 7890, "j7900", lessons=["x"], prompts=[], ms=1500, gather_ms=300, judge_ms=1100)
        self.ev("reuse", 7790, "j7800", lessons=[], prompts=["p1", "p2"], ms=100, gather_ms=100, judge_ms=0, memo=True)
        self.ev("error", 5000, "j7500", where="reuse.judge", message="haiku gave no answer")
        self.ev("error", 4900, "j7500", where="reuse.judge", message="haiku gave no answer")
        self.ev("error", 4800, "j1", where="guard.check", message="timed out")
        self.ev("error", 4700, "j1", message="no place named")

    def test_the_checks_that_had_a_candidate_are_counted_and_the_checks_made_are_not_claimed(self):
        self.seed()
        reuse = self.report()["reuse"]
        self.assertEqual(reuse, {
            "checks": None, "reached": 11, "judged": fig(10, 11, 90.9), "memo": fig(1, 11, 9.1),
            "verdicts": {"named": fig(4, 11, 36.4), "nothing": fig(3, 11, 27.3),
                         "not-substantial": fig(2, 11, 18.2), "unanswered": fig(1, 11, 9.1),
                         "unreadable": fig(1, 11, 9.1)},
            "offers": 3, "earlier_requests": 3,
            "items": [{"name": "x", "offered": 2}, {"name": "bin/tool", "offered": 1}],
            "used": None})

    def test_the_judge_has_counts_per_question_and_a_median_and_p90(self):
        self.seed()
        judge = self.report()["judge"]
        self.assertEqual(judge["calls"], 15)
        self.assertEqual(judge["ms"], spread(15, 800, 2000))
        self.assertEqual(judge["unanswered"], fig(1, 15, 6.7))
        self.assertEqual(judge["timeouts"], fig(1, 15, 6.7))
        self.assertEqual(judge["unreadable"], fig(1, 15, 6.7))
        self.assertEqual(judge["moments"]["reuse"], {
            "calls": 10, "ms": spread(10, 750, 1100),
            "verdicts": {"named": fig(3, 10, 30.0), "nothing": fig(3, 10, 30.0),
                         "not-substantial": fig(2, 10, 20.0), "unanswered": fig(1, 10, 10.0),
                         "unreadable": fig(1, 10, 10.0)}})
        self.assertEqual(judge["moments"]["recall"], {
            "calls": 2, "ms": spread(2),
            "verdicts": {"named": fig(1, 2), "none": fig(1, 2), "unanswered": fig(0, 2), "unreadable": fig(0, 2)}})
        self.assertEqual(judge["moments"]["fix"], {
            "calls": 3, "ms": spread(3),
            "verdicts": {"fix": fig(1, 3), "known": fig(1, 3), "none": fig(1, 3), "unanswered": fig(0, 3),
                         "unreadable": fig(0, 3)}})

    def test_the_cost_is_the_time_added_and_the_errors_by_kind(self):
        self.seed()
        cost = self.report()["cost"]
        self.assertEqual(cost, {
            "prompt": {"offered_ms": spread(3), "offered_gather_ms": spread(3), "offered_judge_ms": spread(3),
                       "judged_ms": spread(10, 750, 1100)},
            "tool_call": {"guard_ms": spread(0), "recall_ms": spread(2), "fix_ms": spread(3)},
            "errors": {"total": 4, "kinds": [{"where": "reuse.judge", "n": 2}, {"where": "?", "n": 1},
                                             {"where": "guard.check", "n": 1}]}})

    def test_the_text_prints_each_figure_over_its_denominator(self):
        self.seed()
        text = self.text()
        self.assertIn("checks made: not measurable. A check that finds no candidate writes no event.", text)
        self.assertRegex(text, r"(?m)^  checks with a candidate +11$")
        self.assertRegex(text, r"(?m)^  put to the judge +10/11 \(90\.9%\)$")
        self.assertRegex(text, r"(?m)^  answered from the memo +1/11 \(9\.1%\)$")
        self.assertRegex(text, r"(?m)^    named +4/11 \(36\.4%\)$")
        self.assertRegex(text, r"(?m)^    not substantial +2/11 \(18\.2%\)$")
        self.assertRegex(text, r"(?m)^  x +2$")
        self.assertRegex(text, r"(?m)^  model calls +15$")
        self.assertRegex(text, r"(?m)^  latency +median 800 ms, p90 2000 ms \(n=15\)$")
        self.assertRegex(text, r"(?m)^  no answer +1/15 \(6\.7%\)")
        self.assertRegex(text, r"(?m)^  reuse +10 +median 750 ms, p90 1100 ms \(n=10\)$")
        self.assertRegex(text, r"(?m)^    named +3/10 \(30\.0%\)$")
        self.assertRegex(text, r"(?m)^  fix +3 +n is too small: 3$")
        self.assertRegex(text, r"(?m)^  errors +4$")
        self.assertRegex(text, r"(?m)^    2  reuse\.judge$")
        self.assertIn("whether an offered item was then used", text)

    def test_no_percentage_is_printed_without_its_fraction(self):
        self.seed()
        for line in self.text().splitlines():
            if "%" in line:
                self.assertRegex(line, r"\d+/\d+ \(\d+\.\d%\)", line)


class RoughLogTest(ReportCase):
    def test_unparseable_lines_other_types_and_missing_fields_are_counted_and_break_nothing(self):
        self.ev("guard", 900, "s1", tool="Bash")                 # no lesson
        self.ev("recall", 800, "s1")                             # no lesson
        self.ev("capture", 700, "s1")                            # no calls
        self.ev("judge", 600, "s1")                              # no moment, no verdict, no ms
        self.ev("judge", 590, "s1", moment="reuse", verdict="named", ms="fast")
        self.ev("judge", 580, "s1", moment="fix", verdict="fix", ms="1500")
        self.ev("reuse", 500, "s1")                              # no lessons, no times
        self.ev("skip", 400, "s2")                               # no why
        self.ev("error", 300, "s1")
        self.ev("retry", 200, "s1")
        with open(self.box.events, "a") as handle:
            handle.write("not json\n")
            handle.write("[1, 2]\n")
            handle.write(json.dumps({"ts": iso(NOW - 100), "type": "use", "session": "s1", "lesson": "x"}) + "\n")
            handle.write(json.dumps({"ts": iso(NOW - 90), "type": 7, "session": "s1"}) + "\n")
            handle.write(json.dumps({"type": "nudge", "session": 3, "ts": "soon"}) + "\n")
        data = self.report()
        self.assertEqual(data["window"]["unparseable"], 2)
        self.assertEqual(data["window"]["events"], 13)
        self.assertEqual(data["window"]["untimed"], 1)
        self.assertEqual(data["window"]["unread"], {"use": 1, "?": 1})
        self.assertEqual(data["guards"]["refusals"], 1)
        self.assertEqual(data["guards"]["lessons"], [
            {"name": "?", "refusals": 1, "watched": 0, "changed": 0, "same": 0, "none": 0, "failed_after": 0}])
        self.assertEqual(data["recall"]["recalls"], 1)
        self.assertEqual(data["learn"]["captures"], 1)
        # The capture and the skip are of two sessions, and the skip names no capture.
        self.assertEqual(data["learn"]["unsettled"], fig(1, 1))
        self.assertEqual(data["learn"]["nudges"], 1)
        self.assertEqual(data["judge"]["calls"], 3)
        # A time that is not a number is no time; a string of digits is one.
        self.assertEqual(data["judge"]["ms"], spread(1))
        self.assertEqual(data["judge"]["moments"]["?"], {"calls": 1, "ms": spread(0), "verdicts": {"?": fig(1, 1)}})
        self.assertEqual(data["reuse"]["offers"], 1)
        self.assertEqual(data["cost"]["errors"], {"total": 1, "kinds": [{"where": "?", "n": 1}]})
        text = self.text()
        self.assertIn("2 lines of the log do not parse", text)
        self.assertIn("not read by this report: ? 1, use 1", text)

    def test_a_use_event_is_counted_nowhere(self):
        self.ev("reuse", 500, "s1", lessons=["x"], prompts=[])
        with open(self.box.events, "a") as handle:
            handle.write(json.dumps({"ts": iso(NOW - 100), "type": "use", "session": "s1", "lesson": "x"}) + "\n")
        data = self.report()
        self.assertEqual(data["reuse"]["items"], [{"name": "x", "offered": 1}])
        self.assertEqual(data["reuse"]["used"], None)
        self.assertEqual(data["window"]["unread"], {"use": 1})

    def test_nothing_printed_carries_a_control_character(self):
        self.ev("guard", 900, "s1", lesson="bad\x1b[31mname\x07", tool="Bash", text="x", watched=True)
        self.ev("skip", 800, "s1", why="odd\x1b]0;title\x07 reason: more")
        self.ev("capture", 850, "s1", failed="a", fixed="b")
        self.ev("error", 700, "s1", where="here\x1b[2J", message="m")
        text = self.text()
        self.assertNotRegex(text, "[\x00-\x09\x0b-\x1f\x7f]")


class WindowTest(ReportCase):
    def seed(self):
        self.ev("guard", 5000, "w1", lesson="a-guard", tool="Bash", text="x", project="/work/one")
        self.ev("guard", 3000, "w2", lesson="a-guard", tool="Bash", text="x", project="/work/two")
        self.ev("guard", 1000, "w3", lesson="a-guard", tool="Bash", text="x", project="/work/one")

    def test_since_until_and_project_choose_the_events(self):
        self.seed()
        data = self.report()
        self.assertEqual((data["window"]["first"], data["window"]["last"], data["window"]["events"],
                          data["window"]["sessions"]), (iso(NOW - 5000), iso(NOW - 1000), 3, 3))
        data = self.report("--since", iso(NOW - 4000))
        self.assertEqual((data["window"]["since"], data["window"]["events"], data["guards"]["refusals"]),
                         (iso(NOW - 4000), 2, 2))
        data = self.report("--since", str(NOW - 4000), "--until", iso(NOW - 2000))
        self.assertEqual((data["window"]["until"], data["window"]["events"], data["window"]["first"]),
                         (iso(NOW - 2000), 1, iso(NOW - 3000)))
        data = self.report("--project", "/work/one")
        self.assertEqual((data["window"]["project"], data["window"]["events"]), ("/work/one", 2))

    def test_what_followed_is_looked_for_past_the_end_of_the_window(self):
        cap = self.ev("capture", 5000, "w1", failed="a", fixed="b")
        self.ev("skip", 1000, "w9", why="late", settles=cap["id"])
        data = self.report("--until", iso(NOW - 2000))
        self.assertEqual(data["window"]["events"], 1)
        self.assertEqual(data["learn"]["declined"], fig(1, 1))

    def test_the_text_states_the_window(self):
        self.seed()
        text = self.text("--since", iso(NOW - 4000))
        self.assertIn("%s to %s" % (iso(NOW - 3000), iso(NOW - 1000)), text)
        self.assertIn("since %s" % iso(NOW - 4000), text)
        self.assertIn("2 events in 2 sessions", text)

    def test_a_time_that_is_none_is_a_usage_error(self):
        for flag in ("--since", "--until"):
            proc = self.box.run("report", flag, "last tuesday")
            self.assertExit(proc, 2)
            self.assertIn(flag, proc.stderr)

    def test_lines_fit_the_width_they_are_given(self):
        self.ev("guard", 900, "s1", lesson="a-guard", tool="Bash", text="x")
        self.ev("capture", 800, "s1", failed="a", fixed="b")
        self.ev("skip", 700, "s1", why="a reason that goes on " * 12)
        for line in self.text(COLUMNS="60").splitlines():
            self.assertLessEqual(len(line), 60, line)


class RetryEventTest(ReportCase):
    def test_log_takes_a_retry_and_status_keeps_it_out_of_recent_and_of_the_counts(self):
        self.ev("guard", 900, "s1", lesson="a-guard", tool="Bash", text="x", watched=True)
        self.ev("retry", 890, "s1", lessons=["a-guard"], tool="Bash", same=False, text="y")
        proc = self.box.run("status", "--json")
        data = json.loads(proc.stdout)
        self.assertEqual([event["type"] for event in data["recent"]], ["guard"])
        self.assertEqual(data["totals"]["guarded"], 1)
        fired = [row for row in data["health"] if row["check"] == "mod last fired"][0]
        self.assertEqual(fired["status"], "PASS")
        proc = self.box.run("events")
        self.assertExit(proc, 0)
        self.assertIn("a-guard: a different call", proc.stdout)


if __name__ == "__main__":
    unittest.main()
