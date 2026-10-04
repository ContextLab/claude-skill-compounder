#!/usr/bin/env python3
"""The mod's own failures. Real `claude -p` sessions; run by hand.

  error     the judge model is set to one that does not exist, so the reuse check's model
            call fails: an `error` event is written with where it failed, and the prompt
            is not blocked (the session still answers).
  report    the next typed prompt of the same process is told about the failure, once: the
            session can quote where it failed.
  off       with COMPOUND_OFF=1 the same prompt writes no event at all.

usage: journey_error.py [--model haiku] [--keep]
"""
import common

FIRST = ("I need a shell script for this project that tags a new release, updates the changelog and pushes the tag "
         "to the remote. Do not run any tool: reply with the single word READY.")
SECOND = ("Do not run any tool. Were you told, in a message that starts with [compound], that the compound mod itself "
          "failed in this session? If so, quote the line that says where it failed. If not, say NOT TOLD.")
BROKEN = {"COMPOUND_MODEL": "no-such-model-journey"}


def main():
    args = common.arguments(__doc__)
    w = common.World("error")
    project = w.project("alpha")
    w.add(project, "release-tagging", "Use when cutting, tagging or publishing a release of this project.",
          "Run scripts/release.sh <version>.\n")

    s = w.session(project, [FIRST, SECOND], args.model, **BROKEN)
    rows = w.events(project, session=s.sid)
    w.show("event", rows)
    errors = [e for e in rows if e["type"] == "error"]
    w.check("error", "an error event was written", len(errors) >= 1, ", ".join(e["type"] for e in rows))
    w.check("error", "it says where the mod failed and why",
            bool(errors) and errors[0].get("where", "").startswith("reuse") and bool(errors[0].get("message")),
            errors[0] if errors else "")
    w.check("error", "the prompt was not blocked: the session answered", "READY" in s.result, s.result[:200])
    w.check("error", "no reuse event was written from a failed check", not any(e["type"] == "reuse" for e in rows))
    w.check("report", "the next prompt was told about the failure", "reuse" in s.result and "NOT TOLD" not in s.result,
            s.result[-300:])
    w.check("report", "it was reported once per session", "errors-reported" in w.claims(s.sid), w.claims(s.sid))

    s = w.session(project, FIRST, args.model, COMPOUND_OFF="1", **BROKEN)
    w.check("off", "with COMPOUND_OFF=1 nothing was written", w.events(project, session=s.sid) == [], w.events(project, session=s.sid))
    w.check("off", "and nothing was claimed", w.claims(s.sid) == [], w.claims(s.sid))
    w.finish(args.keep)


if __name__ == "__main__":
    main()
