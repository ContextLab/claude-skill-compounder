#!/usr/bin/env python3
"""A debt an earlier session left behind. Real `claude -p` sessions; run by hand.

  open      an earlier session's capture that nothing settled is listed by `compound status`
            under Open, with its id.
  told      the next session in the project is told about it at its first typed prompt
            (a `remind` event names the id). That session may not run commands, so it
            settles nothing: its stop is NOT refused, and the capture stays open.
  once      a second prompt of the same session is not told again.
  settle    a further session is told too, and settles it by its id: a `learn` or a `skip`
            that carries `settles`. Nothing is open afterwards.
  quiet     with nothing unsettled, a session is told nothing.

usage: journey_unsettled.py [--model haiku] [--keep]
"""
import json

import common

QUIET = {"COMPOUND_PROMPT_MIN_CHARS": "100000"}
READY = "Do not run any tool and do not invoke a skill. Reply with the single word READY."
AGAIN = "Do not run any tool. Reply with the single word AGAIN."
SETTLE = ("Please settle the lesson an earlier session left unsettled in this project. A [compound] message with this "
          "request describes it and gives the two ways to settle it; use either one, exactly as it says. When that is "
          "done, reply with the single word DONE.")


def unsettled(w, project):
    done = w.cli(project, "events", "--unsettled", "--project", project, "--json")
    return json.loads(done.stdout) if done.returncode == 0 else None


def main():
    args = common.arguments(__doc__)
    w = common.World("unsettled")
    project = w.project("alpha", build=True)
    seeded = w.cli(project, "log", "--json", stdin=json.dumps({
        "type": "capture", "session": "an-earlier-session", "tool": "Bash", "failed": "./build.sh",
        "error": "build.sh: error: a profile is required, e.g. ./build.sh --profile dev",
        "fixed": "./build.sh --profile dev"}))
    cid = json.loads(seeded.stdout)["id"]
    status = w.cli(project, "status")
    opened = status.stdout.split("Open")[-1]
    w.check("open", "status lists the unsettled capture under Open with its id", cid in opened, opened[:300])

    s = w.session(project, [READY, AGAIN], args.model, tools=("Skill",), **QUIET)
    rows = w.events(project, session=s.sid)
    w.show("event", rows)
    reminds = [e for e in rows if e["type"] == "remind"]
    w.check("told", "the first prompt was told about it (a remind event names the id)",
            len(reminds) >= 1 and reminds[0].get("captures") == [cid], reminds)
    w.check("told", "its stop was not refused", not any(e["type"] == "refuse" for e in rows) and s.returncode == 0,
            ", ".join(e["type"] for e in rows))
    w.check("told", "the session answered", "READY" in (w.turns(s) or [""])[0], s.result[:200])
    w.check("told", "the capture is still unsettled", [e.get("id") for e in unsettled(w, project) or []] == [cid])
    w.check("once", "the second prompt was not told again", len(reminds) == 1, "%d remind events" % len(reminds))

    s = w.session(project, SETTLE, args.model, tools=("Bash", "Skill"), **QUIET)
    rows = w.events(project, session=s.sid)
    w.show("event", rows)
    w.check("settle", "this session was told too", any(e["type"] == "remind" and cid in e.get("captures", []) for e in rows),
            ", ".join(e["type"] for e in rows))
    settled = [e for e in rows if e["type"] in ("learn", "skip") and e.get("settles") == cid]
    w.check("settle", "it settled the capture by its id (a learn or a skip that carries `settles`)", len(settled) >= 1,
            [(e["type"], e.get("settles")) for e in rows if e["type"] in ("learn", "skip")])
    w.check("settle", "nothing is unsettled afterwards", unsettled(w, project) == [], unsettled(w, project))
    w.check("settle", "its stop was not refused", not any(e["type"] == "refuse" for e in rows))
    opened = w.cli(project, "status").stdout.split("Open")[-1]
    w.check("settle", "status no longer lists it", cid not in opened.replace("--settles %s" % cid, ""), opened[:300])

    s = w.session(project, READY, args.model, tools=("Skill",), **QUIET)
    w.check("quiet", "with nothing unsettled a session is told nothing",
            w.events(project, session=s.sid, kind="remind") == [], w.events(project, session=s.sid))
    w.finish(args.keep)


if __name__ == "__main__":
    main()
