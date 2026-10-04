#!/usr/bin/env python3
"""Moment 2, the guard. Real `claude -p` sessions; run by hand.

  deny      a lesson with a `match` is recorded. The session sends a matching Bash call:
            it is refused once, with the lesson as the reason, and one `guard` event is
            written.
  allow     the same call sent again in that session runs.
  other     a call that does not match is never refused.
  twice     with a second copy of the package also named by --plugin-dir, the call is
            still refused exactly once (the mod's claim makes each action once per event).
  slow      with a CLI whose `check` takes five seconds, the call is not held for it: the
            check is killed, the call runs unguarded, and one `error` event says so
            however many calls follow.

usage: journey_guard.py [--model haiku] [--keep]
"""
import json
import time

import common

LESSON = "no-marker-echo"
COMMAND = "echo GUARDED_MARKER_42"
PROMPT = ("Run exactly this Bash command and nothing else first: %s\n"
          "If the call is refused, read the reason, then send the very same command again, unchanged. "
          "Then run: echo plain-call\nFinally tell me what each command printed." % COMMAND)


def main():
    args = common.arguments(__doc__)
    w = common.World("guard")
    project = w.project("alpha")
    w.add(project, LESSON, "Use when a command echoes GUARDED_MARKER.",
          "Echoing GUARDED_MARKER is the mistake this lesson is about. JOURNEY-LESSON-TEXT.\n",
          "--match", r"echo\s+GUARDED_MARKER")

    # The reuse check is not this journey's subject: the prompt is kept under its length test.
    s = w.session(project, PROMPT, args.model, COMPOUND_PROMPT_MIN_CHARS="100000")
    marked = [c for c in s.bash() if "GUARDED_MARKER_42" in c[0]]
    rows = w.events(project, session=s.sid, kind="guard")
    w.show("guard", rows)
    w.check("deny", "the first matching call was refused", bool(marked) and marked[0][1] is True,
            marked[0][2][:160] if marked else "no such call")
    w.check("deny", "the refusal carried the lesson's text", bool(marked) and "JOURNEY-LESSON-TEXT" in marked[0][2])
    w.check("deny", "the lesson was quoted as a recorded note, to be weighed and not obeyed",
            bool(marked) and "<<<RECORDED-NOTE lesson=" + LESSON in marked[0][2] and "weighed and not obeyed" in marked[0][2])
    w.check("deny", "it said the call sent again will run", bool(marked) and "send the call again and it will run" in marked[0][2])
    w.check("deny", "exactly one guard event names the lesson", len(rows) == 1 and rows[0].get("lesson") == LESSON,
            "%d events" % len(rows))
    w.check("allow", "the same call sent again ran",
            len(marked) >= 2 and marked[1][1] is False and "GUARDED_MARKER_42" in marked[1][2],
            " | ".join("%s -> %s" % (c[0], "error" if c[1] else "ok") for c in s.bash()))
    plain = [c for c in s.bash() if "plain-call" in c[0]]
    w.check("other", "a call that does not match was not refused", bool(plain) and plain[0][1] is False)
    w.check("other", "the claim that makes it once per session exists", "guard-" + LESSON in w.claims(s.sid), w.claims(s.sid))
    # Two copies of the package loaded at once: every hook runs twice, and still one refusal.
    second = w.copy_of_package()
    s = w.session(project, PROMPT, args.model, also=(second,), COMPOUND_PROMPT_MIN_CHARS="100000")
    loaded = []
    with open(s.stream) as fh:
        for line in fh:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "system" and msg.get("subtype") == "init":
                loaded = [p.get("path") for p in msg.get("plugins", []) if p.get("name") == "compound"]
                break
    print("      copies of the plugin the session loaded: %d %s" % (len(loaded), loaded))
    marked = [c for c in s.bash() if "GUARDED_MARKER_42" in c[0]]
    rows = w.events(project, session=s.sid, kind="guard")
    w.show("guard", rows)
    w.check("twice", "with two copies named, the call was still refused exactly once",
            len(rows) == 1 and len(marked) >= 2 and marked[0][1] is True and marked[1][1] is False,
            "%d guard events; %s" % (len(rows), " | ".join("error" if c[1] else "ok" for c in marked)))

    slow = w.slow_copy("check", 5)
    began = time.time()
    s = w.session(project, PROMPT, args.model, plugin=slow, COMPOUND_PROMPT_MIN_CHARS="100000")
    took = time.time() - began
    marked = [c for c in s.bash() if "GUARDED_MARKER_42" in c[0]]
    errors = w.events(project, session=s.sid, kind="error")
    w.show("error", errors)
    w.check("slow", "the matching call ran: a check that does not answer fails open",
            bool(marked) and marked[0][1] is False and "GUARDED_MARKER_42" in marked[0][2],
            " | ".join("%s -> %s" % (c[0][:40], "error" if c[1] else "ok") for c in s.bash()))
    w.check("slow", "no guard event was written", w.events(project, session=s.sid, kind="guard") == [])
    checks = [e for e in errors if e.get("where") == "guard.check"]
    w.check("slow", "one error event for it, however many calls there were", len(checks) == 1 and len(s.bash()) >= 2,
            "%d guard.check errors over %d Bash calls" % (len(checks), len(s.bash())))
    print("      the session took %.1f s over %d Bash calls with a 5 s check" % (took, len(s.bash())))
    w.finish(args.keep)


if __name__ == "__main__":
    main()
