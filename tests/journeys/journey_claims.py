#!/usr/bin/env python3
"""A claims directory that cannot be made. Real `claude -p` sessions; run by hand.

The mod keeps "once per session" on disk, in claims/<session id>/ under COMPOUND_HOME. Here
a regular file sits where that directory should be, so no claim can be recorded, and the
mod must still never refuse the same thing twice.

  guard     a lesson with a `match` and a session that sends the matching call three
            times: the call is refused at most once, and it does run.
  stop      a session fixes a failed build and is told to finish at once: its stop is
            refused at most once, and the session ends with its answer.
  told      the unusable directory is logged as one `error` event per session.

usage: journey_claims.py [--model haiku] [--keep]
"""
import common

LESSON = "no-marker-echo"
COMMAND = "echo GUARDED_MARKER_42"
THRICE = ("Run exactly this Bash command three times, each as its own call, whatever happens to any of them "
          "(if a call is refused, just go on to the next one): %s\nThen tell me how many of the three ran." % COMMAND)
FINISH_NOW = (common.BUILD_TASK + " The moment the build succeeds, end your turn with that line. Do not record a lesson, "
              "do not invoke a skill and do not run any other command before you have tried to finish.")
QUIET = {"COMPOUND_PROMPT_MIN_CHARS": "100000"}


def main():
    args = common.arguments(__doc__)
    w = common.World("claims")
    w.block_claims()
    project = w.project("alpha", build=True)
    w.add(project, LESSON, "Use when a command echoes GUARDED_MARKER.",
          "Echoing GUARDED_MARKER is the mistake this lesson is about.\n", "--match", r"echo\s+GUARDED_MARKER")

    s = w.session(project, THRICE, args.model, **QUIET)
    marked = [c for c in s.bash() if "GUARDED_MARKER_42" in c[0]]
    denied = [c for c in marked if c[1] is True]
    rows = w.events(project, session=s.sid)
    w.show("event", rows)
    w.check("guard", "the matching call was sent at least three times", len(marked) >= 3, "%d calls" % len(marked))
    w.check("guard", "it was refused at most once", len(denied) <= 1,
            " | ".join("error" if c[1] else "ok" for c in marked))
    w.check("guard", "at most one guard event", len([e for e in rows if e["type"] == "guard"]) <= 1)
    w.check("guard", "the call did run", any(c[1] is False and "GUARDED_MARKER_42" in c[2] for c in marked))
    errors = [e for e in rows if e["type"] == "error" and e.get("where") == "claim"]
    w.check("told", "the unusable claims directory was logged once", len(errors) == 1,
            "%d claim errors of %d events" % (len(errors), len(rows)))

    s = w.session(project, FINISH_NOW, args.model, tools=("Bash", "Skill"), **QUIET)
    rows = w.events(project, session=s.sid)
    w.show("event", rows)
    kinds = [e["type"] for e in rows]
    refused = [e for e in rows if e["type"] == "refuse"]
    w.check("stop", "the session owed a lesson (a capture event)", "capture" in kinds, ", ".join(kinds))
    w.check("stop", "its stop was refused at most once", len(refused) <= 1, "%d refuse events" % len(refused))
    w.check("stop", "the session ended, and with its answer", s.returncode == 0 and "build ok" in s.result, s.result[-300:])
    with open(s.stream) as fh:
        stream = fh.read()
    feedback = stream.count("This session owes a lesson")
    w.check("stop", "the stream shows at most one refusal", feedback <= 1, "%d times in the stream" % feedback)
    errors = [e for e in rows if e["type"] == "error" and e.get("where") == "claim"]
    w.check("told", "and once in the second session", len(errors) == 1, "%d claim errors" % len(errors))
    w.finish(args.keep)


if __name__ == "__main__":
    main()
