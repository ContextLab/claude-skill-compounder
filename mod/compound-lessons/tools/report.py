#!/usr/bin/env python3
"""What compound-lessons has done on this machine, read from its own log.

usage: report.py [--json]

Reads <state>/mod/events.jsonl (SKILL_COMPOUNDER_STATE, else ~/.claude/skill-compounder).
The figure this exists for is the last column: for each lesson, how many times a later
failure was matched to it. A lesson that keeps recurring was written and is not being
read; one that never recurs either worked or was never relevant again, and this log
cannot tell those two apart.
"""
import json
import os
import sys
import time

state = os.environ.get("SKILL_COMPOUNDER_STATE", os.path.expanduser("~/.claude/skill-compounder"))
path = os.path.join(state, "mod", "events.jsonl")
if not os.path.exists(path):
    print("no events yet: %s does not exist" % path)
    sys.exit(0)

with open(path) as fh:
    rows = [json.loads(line) for line in fh if line.strip()]

by = {}
for r in rows:
    by.setdefault(r["ev"], []).append(r)
fails, lessons = by.get("fail", []), by.get("lesson", [])
recurs, judged = by.get("recur", []), by.get("judged", [])

summary = {
    "path": path,
    "from": min(r["ts"] for r in rows),
    "to": max(r["ts"] for r in rows),
    "sessions": len({r.get("session") for r in rows}),
    "failures": len(fails),
    "failures_in_subagents": sum(1 for r in fails if r.get("agent")),
    "failures_matched_to_a_lesson": sum(1 for r in fails if r.get("recalled")),
    "successes_judged_no_lesson": len(judged),
    "lessons_written": len(lessons),
    "promoted_to_global": len(by.get("promote", [])),
    "write_failures": len(by.get("write-failed", [])) + len(by.get("promote-failed", [])),
    "lessons": [{
        "id": l["id"],
        "written": l["ts"],
        "project": l["project"],
        "text": l["text"],
        "recurrences_after": sum(1 for r in recurs if r["id"] == l["id"] and r["ts"] >= l["ts"]),
        "sessions_recurring": len({r.get("session") for r in recurs if r["id"] == l["id"]}),
    } for l in lessons],
}

if "--json" in sys.argv:
    print(json.dumps(summary, indent=2))
    sys.exit(0)

day = lambda t: time.strftime("%Y-%m-%d %H:%M", time.localtime(t))
print("%s\n%s .. %s, %d session(s)" % (path, day(summary["from"]), day(summary["to"]), summary["sessions"]))
print("failures seen            %d (%d in subagents)" % (summary["failures"], summary["failures_in_subagents"]))
print("  matched to a lesson    %d" % summary["failures_matched_to_a_lesson"])
print("successes judged, none   %d" % summary["successes_judged_no_lesson"])
print("lessons written          %d" % summary["lessons_written"])
print("moved to global          %d" % summary["promoted_to_global"])
print("writes that failed       %d" % summary["write_failures"])
for l in summary["lessons"]:
    print("\n%s  %s  %s" % (l["id"], day(l["written"]), l["project"]))
    print("  %s" % l["text"])
    print("  matched to %d later failure(s), in %d session(s)" % (l["recurrences_after"], l["sessions_recurring"]))
