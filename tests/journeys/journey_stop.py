#!/usr/bin/env python3
"""Moment 5, the stop. Real `claude -p` sessions; run by hand.

  refuse    a session fixes a failed build and is told to finish at once, recording
            nothing. Its stop is refused once (the mod's `stop-<call>` claim), and the
            session then settles the debt with a `learn` or a `skip` before it ends.
  nudge     with COMPOUND_TURN_MIN_CALLS=3, a turn of four tool calls that recorded nothing
            is asked once: a `nudge` event carries the count, and the session still ends.
  quiet     the same turn under the default threshold (25 calls) writes no `nudge`.

usage: journey_stop.py [--model haiku] [--keep]
"""
import common

FINISH_NOW = (common.BUILD_TASK + " The moment the build succeeds, end your turn with that line. Do not record a lesson, "
              "do not invoke a skill and do not run any other command before you have tried to finish.")
FOUR = ("Run these four Bash commands one at a time, each as its own call: echo one ; echo two ; echo three ; echo four . "
        "Then tell me the four words.")
QUIET = {"COMPOUND_PROMPT_MIN_CHARS": "100000"}


def main():
    args = common.arguments(__doc__)
    w = common.World("stop")
    project = w.project("alpha", build=True)

    s = w.session(project, FINISH_NOW, args.model, tools=("Bash", "Skill"), **QUIET)
    events = w.events(project, session=s.sid)
    w.show("event", events)
    kinds = [e["type"] for e in events]
    w.check("refuse", "the session owed a lesson (a capture event)", "capture" in kinds, ", ".join(kinds))
    refused = [c for c in w.claims(s.sid) if c.startswith("stop-")]
    w.check("refuse", "its stop was refused once", len(refused) == 1, w.claims(s.sid))
    after = kinds[kinds.index("capture") + 1:] if "capture" in kinds else []
    w.check("refuse", "after the refusal it settled the debt with a learn or a skip",
            any(k in ("learn", "skip") for k in after), ", ".join(after) or "nothing after the capture")
    w.check("refuse", "the session then ended normally", s.returncode == 0 and s.result != "", s.result[-200:])

    quiet = w.project("beta")
    s = w.session(quiet, FOUR, args.model, COMPOUND_TURN_MIN_CALLS="3", **QUIET)
    rows = w.events(quiet, session=s.sid, kind="nudge")
    w.show("nudge", rows)
    w.check("nudge", "a turn of four calls over a threshold of three was asked once",
            len(rows) == 1 and rows[0].get("calls", 0) >= 3, "%d nudge events, %d Bash calls" % (len(rows), len(s.bash())))
    w.check("nudge", "the session still ended", s.returncode == 0 and s.result != "", s.result[-200:])

    s = w.session(quiet, FOUR, args.model, COMPOUND_NUDGE_COOLDOWN="0", **QUIET)
    w.check("quiet", "under the default threshold nothing was asked", w.events(quiet, session=s.sid, kind="nudge") == [])
    w.finish(args.keep)


if __name__ == "__main__":
    main()
