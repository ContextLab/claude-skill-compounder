#!/usr/bin/env python3
"""Moments 4 and 5, capture and stop. Real `claude -p` sessions; run by hand.

  capture   a session fails the build, then fixes it: a `capture` event holds the failing
            call, its error and the working call.
  settle    before the session ends, the debt is settled by a `learn` (a lesson written
            with `compound add`) or a `skip`; when the session tried to stop first, the
            stop was refused (the mod's `stop-<call>` claim says so).
  lesson    when a lesson was written, it exists in the store and names the working form.
  late      the fix comes after three other successful Bash calls: it is still captured.

usage: journey_capture.py [--model haiku] [--keep]
"""
import common

LATE = ("Do these steps in order, each as its own Bash call, and do not skip or merge any. 1: run ./build.sh with no "
        "arguments (it will fail; do not fix it yet). 2: run echo alpha . 3: run echo beta . 4: run echo gamma . "
        "5: now run the build correctly, as its error message said. Do not read or inspect build.sh. "
        "Then tell me what step 5 printed.")


def main():
    args = common.arguments(__doc__)
    w = common.World("capture")
    project = w.project("alpha", build=True)

    s = w.session(project, common.BUILD_TASK, args.model, tools=("Bash", "Skill"), COMPOUND_PROMPT_MIN_CHARS="100000")
    builds = [c for c in s.bash() if "build.sh" in c[0] and "compound" not in c[0]]
    w.check("capture", "the session failed the build and then fixed it",
            len(builds) >= 2 and builds[0][1] is True and any(c[1] is False for c in builds[1:]),
            " | ".join("%s -> %s" % (c[0][:60], "error" if c[1] else "ok") for c in builds))
    events = w.events(project, session=s.sid)
    w.show("event", events)
    kinds = [e["type"] for e in events]
    captures = [e for e in events if e["type"] == "capture"]
    w.check("capture", "a capture event was written", len(captures) >= 1, ", ".join(kinds))
    w.check("capture", "it holds the failing call, its error and the working call",
            bool(captures) and "build.sh" in captures[0].get("failed", "") and "profile is required" in captures[0].get("error", "")
            and "--profile" in captures[0].get("fixed", ""))
    after = kinds[kinds.index("capture") + 1:] if "capture" in kinds else []
    settled = [k for k in after if k in ("learn", "skip")]
    refused = [e for e in events if e["type"] == "refuse"]
    w.check("settle", "the debt was settled by a learn or a skip after the capture", bool(settled),
            "after capture: %s; stop refused: %s" % (", ".join(after) or "nothing", "yes" if refused else "no"))
    print("      the session %s; the stop was %s" % (
        "recorded a lesson" if "learn" in settled else "declined the lesson" if settled else "settled nothing",
        "refused once" if refused else "not refused (the debt was settled before the session tried to stop)"))
    w.check("settle", "no debt is left", not w.events(project, session=s.sid) or
            [e["type"] for e in w.events(project, session=s.sid) if e["type"] in ("capture", "learn", "skip")][-1] != "capture")
    if "learn" in settled:
        lessons = [i for i in w.items(project) if i["kind"] == "lesson"]
        w.check("lesson", "the lesson is in the store", len(lessons) >= 1, ", ".join(i["name"] for i in lessons))
        shown = w.cli(project, "show", lessons[0]["name"]).stdout if lessons else ""
        w.check("lesson", "it names the working form", "--profile" in shown, shown[-300:])
    w.check("capture", "nothing in the mod failed", [e for e in events if e["type"] == "error"] == [],
            [e for e in events if e["type"] == "error"])

    # A world of its own: the lesson the first session may have recorded would be recalled here.
    w2 = common.World("capture-late")
    late = w2.project("beta", build=True)
    s = w2.session(late, LATE, args.model, tools=("Bash", "Skill"), COMPOUND_PROMPT_MIN_CHARS="100000")
    order = [c for c in s.bash() if "compound" not in c[0]]
    print("      calls: %s" % " | ".join("%s -> %s" % (c[0][:40], "error" if c[1] else "ok") for c in order))
    failed = next((i for i, c in enumerate(order) if "build.sh" in c[0] and c[1] is True), None)
    fixed = next((i for i, c in enumerate(order) if "build.sh" in c[0] and c[1] is False), None)
    between = 0 if failed is None or fixed is None else len([c for c in order[failed + 1:fixed] if c[1] is False])
    w.check("late", "three or more successful calls came between the failure and the fix", between >= 3, "%d between" % between)
    captures = w2.events(late, session=s.sid, kind="capture")
    w.show("capture", captures)
    w.check("late", "the fix was still captured", len(captures) >= 1 and "--profile" in captures[0].get("fixed", ""),
            ", ".join(e["type"] for e in w2.events(late, session=s.sid)))
    print("      second root %s" % w2.root)
    w.finish(args.keep)


if __name__ == "__main__":
    main()
