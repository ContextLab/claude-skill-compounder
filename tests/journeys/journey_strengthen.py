#!/usr/bin/env python3
"""A lesson that did not prevent its failure. Real `claude -p` sessions; run by hand.

  first     a lesson is recorded. A session fails the build the way the lesson describes:
            the lesson is recalled, it is not yet ineffective, and no stop is refused for it.
  refuse    a second session fails the same way and is told to finish at once. The recall
            is marked ineffective. Then either the session strengthens the lesson before
            it tries to finish and no stop is refused, or the stop is refused once with
            why "strengthen" and the lesson named (the `strengthen-<lesson>` claim says
            so). A second refusal, or neither outcome, fails.
  clear     the session rewrites the lesson (`learn` with `update`) or declines (`skip`),
            after the refusal when there was one. After an update the CLI no longer lists
            the lesson as ineffective. The session still ends with its answer.
  guard     a lesson that already has a match pattern which does not catch the failing call
            recurs: its recall is marked `guard` and ineffective, and the session does not
            end with the strengthening owed (it rewrites or declines, at once or after the
            one refusal).

usage: journey_strengthen.py [--model haiku] [--keep]
"""
import json
import time

import common

NAME = "build-needs-profile"
WHEN = "Use when ./build.sh fails with 'a profile is required'."
BODY = "Run ./build.sh --profile dev. A bare ./build.sh fails with 'error: a profile is required'.\n"
QUIET = {"COMPOUND_PROMPT_MIN_CHARS": "100000"}
# The message beside the failure already says to strengthen the lesson, and a session
# usually does so at once. This one is told to try to finish first, so the stop is reached
# with the strengthening still owed.
FINISH_NOW = (common.BUILD_TASK + " This is a test of what happens when you finish too early, so follow this exactly: if "
              "a [compound] message beside a tool result tells you to strengthen a lesson, do NOT do it yet. Run nothing "
              "but the build. The moment the build succeeds, end your turn with the line it printed. Only if that "
              "attempt to finish is refused by a [compound] message, do what the refusal asks, by adding a match "
              "pattern with the command it gives, and then give your answer again.")


def main():
    args = common.arguments(__doc__)
    w = common.World("strengthen")
    project = w.project("alpha", build=True)
    w.add(project, NAME, WHEN, BODY)

    s = w.session(project, common.BUILD_TASK, args.model, **QUIET)
    rows = w.events(project, session=s.sid)
    w.show("event", rows)
    recalls = [e for e in rows if e["type"] == "recall"]
    w.check("first", "the lesson was recalled and is not yet ineffective",
            bool(recalls) and recalls[0].get("lesson") == NAME and recalls[0].get("ineffective") is False, recalls[:1])
    w.check("first", "no stop was refused for it", not any(e["type"] == "refuse" and e.get("why") == "strengthen" for e in rows))

    s = w.session(project, FINISH_NOW, args.model, tools=("Bash", "Skill"), **QUIET)
    rows = w.events(project, session=s.sid)
    w.show("event", rows)
    kinds = [e["type"] for e in rows]
    recalls = [e for e in rows if e["type"] == "recall"]
    w.check("refuse", "the second recurrence is marked ineffective",
            bool(recalls) and recalls[0].get("lesson") == NAME and recalls[0].get("ineffective") is True, recalls[:1])
    # Two outcomes are right. The session strengthens the lesson before it tries to finish,
    # and no stop is refused; or it tries to finish, the stop is refused once with the
    # lesson named, and it strengthens the lesson then. Neither, or a second refusal, fails.
    refused = [e for e in rows if e["type"] == "refuse" and e.get("why") == "strengthen"]
    at = rows.index(recalls[0]) if recalls else len(rows)

    def settles(e):
        return (e["type"] == "learn" and e.get("update") is True and e.get("lesson") == NAME) or e["type"] == "skip"

    if not refused:
        after = rows[at + 1:]
        w.check("refuse", "the lesson was strengthened before the stop, so no stop was refused",
                any(settles(e) for e in after), ", ".join(kinds))
        w.check("refuse", "no claim was taken for a refusal that did not happen",
                "strengthen-%s" % NAME not in w.claims(s.sid), w.claims(s.sid))
    else:
        after = rows[rows.index(refused[0]) + 1:]
        w.check("refuse", "the stop was refused once, with the lesson named",
                len(refused) == 1 and refused[0].get("lessons") == [NAME], [e for e in rows if e["type"] == "refuse"])
        w.check("refuse", "the claim that keeps it to once exists", "strengthen-%s" % NAME in w.claims(s.sid), w.claims(s.sid))
    updates = [e for e in after if e["type"] == "learn" and e.get("update") is True and e.get("lesson") == NAME]
    skips = [e for e in after if e["type"] == "skip"]
    w.check("clear", "the session updated the lesson or declined (after the refusal, when there was one)", bool(updates or skips),
            ", ".join(e["type"] for e in after) or "nothing after it (%s)" % ", ".join(kinds))
    item = [i for i in w.items(project) if i["name"] == NAME]
    w.check("clear", "the session's update cleared it: the lesson is no longer ineffective",
            bool(updates) and bool(item) and item[0].get("ineffective") is False,
            "updates %d, skips %d, item %s" % (len(updates), len(skips), item[0] if item else "gone"))
    print("      the lesson now: match %s" % (item[0].get("match") if item else "-"))
    w.check("clear", "the session ended with its answer", s.returncode == 0 and "build ok" in s.result, s.result[-300:])

    w2 = common.World("strengthen-guard")
    other = w2.project("beta", build=True)
    w2.add(other, NAME, WHEN, BODY, "--match", r"make\s+build\s*$")
    time.sleep(1.5)  # a recurrence counts when it is later than the lesson's last write, to the second
    w2.cli(other, "log", stdin=json.dumps({"type": "recall", "session": "an-earlier-session", "lesson": NAME,
                                           "tool": "Bash", "error": "a profile is required"}))
    s = w2.session(other, common.BUILD_TASK, args.model, tools=("Bash", "Skill"), **QUIET)
    rows = w2.events(other, session=s.sid)
    w.show("event", rows)
    recalls = [e for e in rows if e["type"] == "recall"]
    w.check("guard", "a guard whose pattern missed the call is recalled as guard and ineffective",
            bool(recalls) and recalls[0].get("guard") is True and recalls[0].get("ineffective") is True
            and "build.sh" in recalls[0].get("call", ""), recalls[:1])
    at = rows.index(recalls[0]) if recalls else len(rows)
    settled = [e for e in rows[at:] if (e["type"] == "learn" and e.get("update") is True) or e["type"] == "skip"]
    refused = [e for e in rows if e["type"] == "refuse" and e.get("why") == "strengthen"]
    w.check("guard", "the session did not end with the strengthening owed", bool(settled) and len(refused) <= 1,
            "%s; refused %d time(s)" % (", ".join(e["type"] for e in rows), len(refused)))
    print("      second root %s" % w2.root)
    w.finish(args.keep)


if __name__ == "__main__":
    main()
