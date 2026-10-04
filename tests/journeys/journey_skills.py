#!/usr/bin/env python3
"""The plugin's surface in a headless session. Real `claude -p` sessions; run by hand.

  listed    a session started with `--plugin-dir <repo>` lists the two skills as
            compound:learn and compound:reuse, and the /compound command.
  invoked   asked to, the session invokes compound:learn through the Skill tool, follows
            it, and a lesson is written with `compound add` (a `learn` event).
  commands  the session runs `compound skill`, `compound rm` and a plan-only `compound
            promote --to general` itself. After each the mod reads the log for what the
            command wrote: the `skill` and `rm` events are there, the plan wrote no
            `promote` event, and the mod logged no error doing so.

usage: journey_skills.py [--model haiku] [--keep]
"""
import json

import common

PROMPT = ("Use the Skill tool to invoke the skill compound:learn, then follow it to record this lesson for this "
          "project: running ./deploy.sh without --region fails with 'region is required'; run ./deploy.sh --region "
          "us-east-1. The compound CLI is at %s. Do not ask me anything: the lesson is exactly as stated, at the "
          "project level." % common.CLI)

COMMANDS = ("Run exactly these three Bash commands, one call each, in this order, and then tell me what each printed:\n"
            "%(cli)s promote keep-me --to general\n%(cli)s skill make-me-a-skill\n%(cli)s rm remove-me" % {"cli": common.CLI})


def main():
    args = common.arguments(__doc__)
    w = common.World("skills")
    project = w.project("alpha")
    s = w.session(project, PROMPT, args.model, tools=("Bash", "Skill"), COMPOUND_PROMPT_MIN_CHARS="100000")
    init = {}
    with open(s.stream) as fh:
        for line in fh:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "system" and msg.get("subtype") == "init":
                init = msg
                break
    skills = [x for x in init.get("skills", []) if "compound" in str(x)]
    commands = [x for x in init.get("slash_commands", []) if "compound" in str(x)]
    print("      skills %s; slash commands %s" % (skills, commands))
    w.check("listed", "the session lists compound:learn and compound:reuse",
            "compound:learn" in skills and "compound:reuse" in skills, skills)
    w.check("listed", "and the /compound command", "compound" in commands, commands)
    used = [c for c in s.calls if c[0] == "Skill"]
    w.check("invoked", "the session invoked compound:learn with the Skill tool",
            any("learn" in json.dumps(c[1]) and c[2] is False for c in used), [c[1] for c in used])
    rows = w.events(project, session=s.sid, kind="learn")
    w.show("learn", rows)
    w.check("invoked", "following it wrote a lesson (a learn event)", len(rows) >= 1)
    lessons = [i for i in w.items(project) if i["kind"] == "lesson"]
    shown = w.cli(project, "show", lessons[0]["name"]).stdout if lessons else ""
    w.check("invoked", "the lesson is at the project level and names the working form",
            bool(lessons) and lessons[0]["level"] == "project" and "--region" in shown, shown[-300:])

    beta = w.project("beta")
    for name in ("keep-me", "make-me-a-skill", "remove-me"):
        w.add(beta, name, "Use when the journey says %s." % name, "The body of %s.\n" % name)
    s = w.session(beta, COMMANDS, args.model, COMPOUND_PROMPT_MIN_CHARS="100000")
    rows = w.events(beta, session=s.sid)
    w.show("event", rows)
    ran = [c for c in s.bash() if common.CLI in c[0]]
    w.check("commands", "the session ran the three commands and none failed", len(ran) >= 3 and not any(c[1] for c in ran),
            " | ".join("%s -> %s" % (c[0][-40:], "error" if c[1] else "ok") for c in s.bash()))
    w.check("commands", "`compound skill` wrote a skill event and `compound rm` an rm event",
            [e.get("lesson") for e in rows if e["type"] == "skill"] == ["make-me-a-skill"]
            and [e.get("lesson") for e in rows if e["type"] == "rm"] == ["remove-me"], [e["type"] for e in rows])
    w.check("commands", "the plan wrote no promote event, so there is nothing to announce as moved",
            not any(e["type"] == "promote" for e in rows) and any("nothing has been written" in c[2] for c in ran))
    w.check("commands", "reading the log after each command logged no error", not any(e["type"] == "error" for e in rows),
            [e for e in rows if e["type"] == "error"])
    w.finish(args.keep)


if __name__ == "__main__":
    main()
