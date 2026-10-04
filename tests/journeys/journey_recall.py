#!/usr/bin/env python3
"""Moment 3, recall, and the move to the user level. Real `claude -p` sessions; run by hand.

  recall    a lesson is recorded in project alpha. A session there fails the build the way
            the lesson describes: a `recall` event names the lesson, the build then
            succeeds, and no lesson is owed (a recalled failure is not captured).
  again     a second session fails the same way: with COMPOUND_RECUR_LIMIT=2 the CLI now
            lists the lesson as ineffective.
  promote   a lesson recorded in project beta is met by a failure in project gamma: it is
            recalled there and MOVED to the user level (a `promote` event; it is no longer
            in beta).

The reuse check is switched off by its length knob in every session here, so the lesson
reaches the session only through the failure.

usage: journey_recall.py [--model haiku] [--keep]
"""
import common

WHEN = "Use when ./build.sh fails with 'a profile is required'."
BODY = "Run ./build.sh --profile dev. A bare ./build.sh fails with 'error: a profile is required'. JOURNEY-RECALL-TEXT\n"
QUIET = {"COMPOUND_PROMPT_MIN_CHARS": "100000"}


def builds(s):
    return [c for c in s.bash() if "build.sh" in c[0] and "compound" not in c[0]]


def main():
    args = common.arguments(__doc__)
    w = common.World("recall")
    alpha = w.project("alpha", build=True)
    w.add(alpha, "build-needs-profile", WHEN, BODY)

    s = w.session(alpha, common.BUILD_TASK, args.model, **QUIET)
    b = builds(s)
    rows = w.events(alpha, session=s.sid)
    w.show("event", rows)
    recalls = [e for e in rows if e["type"] == "recall"]
    w.check("recall", "the build failed first", bool(b) and b[0][1] is True, b[0][0] if b else "no build call")
    w.check("recall", "a recall event names the recorded lesson",
            bool(recalls) and recalls[0].get("lesson") == "build-needs-profile", ", ".join(e["type"] for e in rows))
    w.check("recall", "the build then succeeded", any(c[1] is False for c in b[1:]))
    w.check("recall", "a recalled failure is not captured as a new lesson", not any(e["type"] == "capture" for e in rows))

    s = w.session(alpha, common.BUILD_TASK, args.model, **QUIET)
    rows = w.events(alpha, session=s.sid)
    w.show("event", rows)
    w.check("again", "a second session's failure recalled it again", any(e["type"] == "recall" for e in rows))
    item = [i for i in w.items(alpha) if i["name"] == "build-needs-profile"]
    w.check("again", "the CLI now lists the lesson as ineffective", bool(item) and item[0].get("ineffective") is True,
            item[0].get("counts") if item else "not listed")

    beta, gamma = w.project("beta", build=True), w.project("gamma", build=True)
    w.add(beta, "beta-build-profile", WHEN, BODY)
    # alpha's lesson would also match in gamma; it is removed so this step is about beta's alone.
    w.cli(alpha, "rm", "build-needs-profile")
    s = w.session(gamma, common.BUILD_TASK, args.model, **QUIET)
    b = builds(s)
    rows = w.events(gamma, session=s.sid)
    w.show("event", rows)
    promotes = w.events(gamma, kind="promote")
    w.show("promote", promotes)
    w.check("promote", "the build failed first in the second project", bool(b) and b[0][1] is True)
    w.check("promote", "the other project's lesson was recalled",
            any(e["type"] == "recall" and e.get("lesson") == "beta-build-profile" for e in rows), ", ".join(e["type"] for e in rows))
    w.check("promote", "a promote event moved it to the user level",
            any(e.get("lesson") == "beta-build-profile" and e.get("to") == "user" for e in promotes))
    at = {i["name"]: i["level"] for i in w.items(gamma)}
    w.check("promote", "it is now at the user level", at.get("beta-build-profile") == "user", at)
    still = [i["name"] for i in w.items(beta) if i["level"] == "project"]
    w.check("promote", "it was moved, not copied", "beta-build-profile" not in still, still)
    w.check("promote", "the build then succeeded", any(c[1] is False for c in b[1:]))
    w.finish(args.keep)


if __name__ == "__main__":
    main()
