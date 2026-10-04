#!/usr/bin/env python3
"""Moment 3, recall, and the move to the user level. Real `claude -p` sessions; run by hand.

  recall    a lesson is recorded in project alpha. A session there fails the build the way
            the lesson describes: a `recall` event names the lesson, the build then
            succeeds, and no lesson is owed (a recalled failure is not captured).
  again     a second session fails the same way: with COMPOUND_RECUR_LIMIT=2 that recall is
            marked ineffective, and the lesson is then either rewritten by the session (which
            clears the flag) or listed by the CLI as ineffective.
  promote   a lesson recorded in project beta, which git does not track there, is met by a
            failure in project gamma: it is recalled there and MOVED to the user level (a
            `promote` event that belongs to gamma and names beta as `from`; it is no longer
            in beta).
  tracked   a lesson COMMITTED in project delta is met by a failure in project epsilon: it
            is recalled there, read from delta in place, and NOT moved. delta's working tree
            is unchanged, a `candidate` event names both projects, and `compound status`
            lists the move under Open with the command that makes it.

The reuse check is switched off by its length knob in every session here, so the lesson
reaches the session only through the failure.

usage: journey_recall.py [--model haiku] [--keep]
"""
import json
import os
import subprocess

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
    again = [e for e in rows if e["type"] == "recall"]
    w.check("again", "a second session's failure recalled it again", bool(again))
    w.check("again", "that recall is marked ineffective", bool(again) and again[0].get("ineffective") is True, again[:1])
    item = [i for i in w.items(alpha) if i["name"] == "build-needs-profile"]
    rewritten = any(e["type"] == "learn" and e.get("update") is True and e.get("lesson") == "build-needs-profile" for e in rows)
    w.check("again", "the lesson was rewritten by the session, or the CLI lists it as ineffective",
            bool(item) and (rewritten or item[0].get("ineffective") is True),
            "rewritten %s, %s" % (rewritten, item[0].get("counts") if item else "not listed"))

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
    w.check("promote", "the event belongs to the session's project and names the source as `from`",
            any(e.get("project") == gamma and e.get("from") == beta for e in promotes), promotes)
    at = {i["name"]: i["level"] for i in w.items(gamma)}
    w.check("promote", "it is now at the user level", at.get("beta-build-profile") == "user", at)
    still = [i["name"] for i in w.items(beta) if i["level"] == "project"]
    w.check("promote", "it was moved, not copied", "beta-build-profile" not in still, still)
    w.check("promote", "the build then succeeded", any(c[1] is False for c in b[1:]))

    delta, epsilon = w.project("delta", build=True), w.project("epsilon", build=True)
    # beta's lesson, now at the user level, would match in epsilon too; this step is about delta's.
    w.cli(gamma, "rm", "beta-build-profile")
    w.add(delta, "delta-build-profile", WHEN, BODY)

    def git(*argv):
        return subprocess.run(["git", "-c", "user.name=Journey", "-c", "user.email=journey@example.invalid",
                               "-c", "commit.gpgsign=false", *argv], cwd=delta, capture_output=True, text=True)

    git("init")
    git("add", "-A")
    committed = git("commit", "-m", "the project's lesson")
    lesson_file = os.path.join(delta, ".claude", "compound", "lessons", "delta-build-profile", "SKILL.md")
    w.check("tracked", "delta's lesson is committed", committed.returncode == 0 and git("status", "--porcelain").stdout == "",
            committed.stderr[-200:])
    s = w.session(epsilon, common.BUILD_TASK, args.model, **QUIET)
    b = builds(s)
    rows = w.events(epsilon, session=s.sid)
    w.show("event", rows)
    w.check("tracked", "the build failed first in epsilon", bool(b) and b[0][1] is True)
    w.check("tracked", "delta's lesson was recalled there",
            any(e["type"] == "recall" and e.get("lesson") == "delta-build-profile" for e in rows), ", ".join(e["type"] for e in rows))
    w.check("tracked", "the committed file is still in delta", os.path.isfile(lesson_file))
    w.check("tracked", "delta's working tree is unchanged", git("status", "--porcelain").stdout == "", git("status", "--porcelain").stdout)
    w.check("tracked", "no promote event moved it",
            not any(e.get("lesson") == "delta-build-profile" for e in w.events(epsilon, kind="promote")))
    candidates = w.events(epsilon, kind="candidate")
    w.show("candidate", candidates)
    w.check("tracked", "a candidate event names the lesson and both projects",
            any(e.get("lesson") == "delta-build-profile" and e.get("from") == delta and e.get("seen_in") == epsilon
                for e in candidates))
    status = json.loads(w.cli(epsilon, "status", "--json").stdout or "{}")
    command = "COMPOUND_PROJECT=%s compound promote delta-build-profile --to user" % delta
    w.check("tracked", "status lists the move under Open with the exact command",
            any(c.get("command") == command for c in status.get("open", {}).get("candidates", [])),
            status.get("open", {}).get("candidates"))
    w.check("tracked", "the build then succeeded", any(c[1] is False for c in b[1:]))
    w.finish(args.keep)


if __name__ == "__main__":
    main()
