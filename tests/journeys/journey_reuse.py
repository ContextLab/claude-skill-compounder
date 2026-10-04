#!/usr/bin/env python3
"""Moment 1, the reuse check. Real `claude -p` sessions; run by hand.

  match     a substantial prompt, with a lesson recorded that covers it and an earlier
            request like it in the prompt log: a `reuse` event names the lesson and the
            earlier request, and the session can say what it was told to reuse.
  trivial   a short prompt in the same project: no `reuse` event.
  command   a slash command long enough to pass the length test: no `reuse` event.

usage: journey_reuse.py [--model haiku] [--keep]
"""
import common

LESSON = "release-tagging"
PROMPT = ("I need a shell script for this project that tags a new release, updates the changelog and pushes the tag "
          "to the remote. Before doing anything else, and without running any tool, tell me in one sentence whether "
          "you were told about existing work that covers this, and name it exactly.")


def main():
    args = common.arguments(__doc__)
    w = common.World("reuse")
    project = w.project("alpha")
    w.add(project, LESSON, "Use when cutting, tagging or publishing a release of this project.",
          "Run scripts/release.sh <version>. It tags the release, updates the changelog and pushes the tag.\n")
    w.seed_prompt("/Users/someone/older-project", "older-session-1",
                  "write a release script that tags the version, updates the changelog and pushes the tag")

    s = w.session(project, PROMPT, args.model)
    rows = w.events(project, session=s.sid, kind="reuse")
    w.show("reuse", rows)
    w.check("match", "one reuse event was written for the substantial prompt", len(rows) == 1, "%d events" % len(rows))
    w.check("match", "it names the recorded lesson", bool(rows) and LESSON in rows[0].get("lessons", []))
    w.check("match", "it names the earlier request from the prompt log",
            bool(rows) and "older-session-1:1" in rows[0].get("prompts", []), rows[0].get("prompts") if rows else "")
    w.check("match", "the session was told: its answer names the lesson", LESSON in s.result, s.result[:200])
    w.check("match", "nothing in the mod failed", w.events(project, session=s.sid, kind="error") == [],
            w.events(project, session=s.sid, kind="error"))

    s = w.session(project, "Say the single word hi.", args.model)
    w.check("trivial", "a short prompt wrote no reuse event", w.events(project, session=s.sid, kind="reuse") == [])
    w.check("trivial", "and no event at all", w.events(project, session=s.sid) == [], w.events(project, session=s.sid))

    s = w.session(project, "/compound " + "x" * 120, args.model)
    w.check("command", "a slash command wrote no reuse event", w.events(project, session=s.sid, kind="reuse") == [])
    w.check("command", "/compound answered with the status report", "lesson" in s.result.lower(), s.result[:200])
    w.finish(args.keep)


if __name__ == "__main__":
    main()
