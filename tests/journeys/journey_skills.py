#!/usr/bin/env python3
"""The plugin's surface in a headless session. Real `claude -p` sessions; run by hand.

  listed    a session started with `--plugin-dir <repo>` lists the two skills as
            compound:learn and compound:reuse, and the /compound command.
  invoked   asked to, the session invokes compound:learn through the Skill tool, follows
            it, and a lesson is written with `compound add` (a `learn` event).

usage: journey_skills.py [--model haiku] [--keep]
"""
import json

import common

PROMPT = ("Use the Skill tool to invoke the skill compound:learn, then follow it to record this lesson for this "
          "project: running ./deploy.sh without --region fails with 'region is required'; run ./deploy.sh --region "
          "us-east-1. The compound CLI is at %s. Do not ask me anything: the lesson is exactly as stated, at the "
          "project level." % common.CLI)


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
    w.finish(args.keep)


if __name__ == "__main__":
    main()
