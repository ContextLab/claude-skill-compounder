#!/usr/bin/env python3
"""Moment 1, the reuse check. Real `claude -p` sessions; run by hand.

  match     a substantial prompt, with a lesson recorded that covers it and an earlier
            request like it in the prompt log: a `reuse` event names the lesson and the
            earlier request, and the session can say what it was told to reuse.
  other     a substantial prompt about something else, with a lesson and an earlier
            request that only share words with it: nothing is added, and no `reuse` event.
  memo      the first prompt again in a new session: the same thing is added, and no
            model is asked for it.
  trivial   a short prompt in the same project: no `reuse` event.
  command   a slash command long enough to pass the length test: no `reuse` event.

usage: journey_reuse.py [--model haiku] [--keep]
"""
import common

LESSON = "release-tagging"
PROMPT = ("I need a shell script for this project that tags a new release, updates the changelog and pushes the tag "
          "to the remote. Before doing anything else, and without running any tool, tell me in one sentence whether "
          "you were told about existing work that covers this, and name it exactly.")
OTHER = ("Add a dark mode toggle to the settings page of the web app and remember the user's choice in local storage. "
         "Before doing anything else, and without running any tool, tell me in one sentence whether you were told "
         "about existing work that covers this.")


def main():
    args = common.arguments(__doc__)
    w = common.World("reuse")
    project = w.project("alpha")
    w.add(project, LESSON, "Use when cutting, tagging or publishing a release of this project.",
          "Run scripts/release.sh <version>. It tags the release, updates the changelog and pushes the tag.\n")
    w.seed_prompt("/Users/someone/older-project", "older-session-1",
                  "write a release script that tags the version, updates the changelog and pushes the tag")

    w.add(project, "settings-page-cache", "Use when the settings page shows stale values after a deploy.",
          "Clear the CDN cache for /settings after every deploy.\n")
    w.seed_prompt("/Users/someone/older-project", "older-session-2", "centre the login button on the settings page of the web app")

    s = w.session(project, PROMPT, args.model)
    rows = w.events(project, session=s.sid, kind="reuse")
    w.show("reuse", rows)
    w.check("match", "one reuse event was written for the substantial prompt", len(rows) == 1, "%d events" % len(rows))
    w.check("match", "it names the recorded lesson and no other", bool(rows) and rows[0].get("lessons") == [LESSON],
            rows[0].get("lessons") if rows else "")
    w.check("match", "it names the earlier request from the prompt log",
            bool(rows) and "older-session-1:1" in rows[0].get("prompts", []), rows[0].get("prompts") if rows else "")
    w.check("match", "the session was told: its answer names the lesson", LESSON in s.result, s.result[:200])
    w.check("match", "nothing in the mod failed", w.events(project, session=s.sid, kind="error") == [],
            w.events(project, session=s.sid, kind="error"))

    s = w.session(project, OTHER, args.model)
    rows = w.events(project, session=s.sid)
    w.show("event", rows)
    # The lesson shares `settings` and `page` with the prompt, so the judge is asked: its
    # verdict is logged, and it names nothing.
    w.check("other", "a prompt that only shares words with the store and the log got nothing",
            [e for e in rows if e["type"] != "judge"] == [], ", ".join(e["type"] for e in rows))
    w.check("other", "the judge, if it was asked, named nothing",
            all(e.get("verdict") in ("nothing", "not-substantial") for e in rows if e["type"] == "judge"),
            [e.get("verdict") for e in rows])

    # The first prompt again, in a new session: the verdict is in the memo and no model is asked.
    s = w.session(project, PROMPT, args.model)
    judged = [e for e in w.events(project, session=s.sid, kind="judge") if e.get("moment") == "reuse"]
    rows = w.events(project, session=s.sid, kind="reuse")
    w.show("event", judged + rows)
    w.check("memo", "the same prompt in another session asked no model", len(judged) == 1 and judged[0].get("memo") is True
            and judged[0].get("ms") == 0, judged)
    w.check("memo", "and was given the same lesson and earlier request",
            len(rows) == 1 and rows[0].get("lessons") == [LESSON] and "older-session-1:1" in rows[0].get("prompts", [])
            and rows[0].get("memo") is True, rows)
    w.check("memo", "the session was told again", LESSON in s.result, s.result[:200])

    s = w.session(project, "Say the single word hi.", args.model)
    w.check("trivial", "a short prompt wrote no reuse event", w.events(project, session=s.sid, kind="reuse") == [])
    w.check("trivial", "and no event at all", w.events(project, session=s.sid) == [], w.events(project, session=s.sid))

    s = w.session(project, "/compound " + "x" * 120, args.model)
    w.check("command", "a slash command wrote no reuse event", w.events(project, session=s.sid, kind="reuse") == [])
    w.check("command", "/compound answered with the status report", "lesson" in s.result.lower(), s.result[:200])
    w.finish(args.keep)


if __name__ == "__main__":
    main()
