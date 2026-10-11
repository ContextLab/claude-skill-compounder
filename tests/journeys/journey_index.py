#!/usr/bin/env python3
"""The index. Real `claude -p` sessions; run by hand.

  shown     a session's first prompt is given the index of what is recorded: one `index`
            event, counting a lesson of ANOTHER project that carries a script.
  used      the task needs that script and does not name it or the lesson. The session
            runs the recorded program instead of writing its own, and its answer is the
            program's.
  once      a second prompt in the same session is given no second index.
  empty     in a world with nothing recorded but the package's own lessons, the index
            lists those and no error is written.

usage: journey_index.py [--model haiku] [--keep]
"""
import os

import common

TOOL = """#!/usr/bin/env python3
\"\"\"tally_failed.py DIR: count the records marked FAILED in every .rec file under DIR.

A record is a block of lines up to a blank line. It is FAILED when its `status:` line
says FAILED, unless a later `retry-of:` record in the same file names its `id:` and that
one says OK: a failure that was retried and passed is not counted. Prints one line a file
and a total.\"\"\"
import os, sys
total = 0
for name in sorted(os.listdir(sys.argv[1])):
    if not name.endswith(".rec"):
        continue
    blocks = [dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
              for block in open(os.path.join(sys.argv[1], name)).read().split("\\n\\n") if block.strip()]
    healed = set(b["retry-of"] for b in blocks if b.get("retry-of") and b.get("status") == "OK")
    failed = [b for b in blocks if b.get("status") == "FAILED" and b.get("id") not in healed]
    total += len(failed)
    print("%s %d" % (name, len(failed)))
print("TALLY-TOTAL %d" % total)
"""
TASK = ("The runs/ directory of this project holds the logs of last night's batch as .rec files. How many records "
        "failed, in total and for each file? A failure that was retried and then passed does not count. Give me "
        "the total as a number.")


def records(folder):
    """Three files. Counted naively (every FAILED) the total is 6; with retries that passed taken out it is 3."""
    os.makedirs(folder)
    files = {
        "a.rec": [("1", "OK", None), ("2", "FAILED", None), ("3", "OK", "2"), ("4", "FAILED", None)],
        "b.rec": [("1", "FAILED", None), ("2", "FAILED", None), ("3", "OK", "1"), ("4", "FAILED", "2")],
        "c.rec": [("1", "FAILED", None), ("2", "OK", "1"), ("3", "OK", None)],
    }
    for name, rows in files.items():
        with open(os.path.join(folder, name), "w") as fh:
            fh.write("\n\n".join("id: %s\nstatus: %s%s" % (i, status, "\nretry-of: %s" % of if of else "")
                                 for i, status, of in rows) + "\n")


def main():
    args = common.arguments(__doc__)
    w = common.World("index")
    other = w.project("tooling")
    script = os.path.join(w.tmp, "tally_failed.py")
    with open(script, "w") as fh:
        fh.write(TOOL)
    os.chmod(script, 0o755)
    # Only a script that RAN crosses from one project to another: the run is told to the CLI
    # as the mod tells it, and the lesson is recorded from the copy the CLI kept.
    import json
    noted = json.loads(w.cli(other, "evidence", "note", "--json", stdin=json.dumps(
        {"command": "python3 %s %s" % (script, other), "ok": True, "cwd": other})).stdout)["noted"]
    w.add(other, "tally-failed-records", "Use when counting the failed records in a directory of .rec batch logs.",
          "Run tally_failed.py (beside this lesson) on the directory: `python3 tally_failed.py runs/`. It prints a "
          "count for each file and a TALLY-TOTAL line. A failure that a later retry-of record healed is not counted.\n",
          "--from-evidence", noted[0]["id"])
    project = w.project("alpha")
    records(os.path.join(project, "runs"))

    s = w.session(project, [TASK, "Thanks. What is today's date? Run `date` to find out."], args.model)
    rows = w.events(project, session=s.sid, kind="index")
    w.show("index", rows)
    w.check("shown", "one index event, and it counts the other project's lesson with a script",
            len(rows) == 1 and rows[0].get("elsewhere") == 1 and rows[0].get("scripts", 0) >= 1
            and rows[0].get("chars", 99999) <= 9300, rows)
    w.check("once", "the second prompt was given no second index", len(rows) == 1 and "index" in w.claims(s.sid),
            w.claims(s.sid))
    ran = [c for c in s.bash() if "tally_failed.py" in c[0] and "show" not in c[0].split("tally_failed.py")[0][-40:]
           and c[1] is False and "TALLY-TOTAL" in c[2]]
    print("      calls: %s" % " | ".join("%s -> %s" % (c[0][:70].replace("\n", " "), "error" if c[1] else "ok") for c in s.bash()))
    w.check("used", "the session ran the recorded program", bool(ran), [c[0][:90] for c in s.bash()])
    w.check("used", "it ran the copy the other project keeps, and wrote none of its own",
            bool(ran) and os.path.join(other, ".claude", "compound", "lessons", "tally-failed-records") in ran[0][0]
            or bool(ran) and not any("cat >" in c[0] and ".py" in c[0] for c in s.bash()), [c[0][:120] for c in ran])
    w.check("used", "its answer is the program's: 3, not the 6 a plain count of FAILED gives",
            "3" in s.result and "TALLY-TOTAL 3" in "".join(c[2] for c in ran), s.result[:300])
    w.check("shown", "no error was written", w.events(project, session=s.sid, kind="error") == [],
            w.events(project, session=s.sid, kind="error"))

    w2 = common.World("index-empty")
    bare = w2.project("gamma")
    s = w2.session(bare, "Run `echo ready` and tell me what it printed.", args.model)
    rows = w2.events(bare, session=s.sid, kind="index")
    w.show("index", rows)
    w.check("empty", "with only the package's lessons the index lists those, none from elsewhere",
            len(rows) == 1 and rows[0].get("elsewhere") == 0 and rows[0].get("lessons", 0) >= 1, rows)
    w.check("empty", "no error was written", w2.events(bare, session=s.sid, kind="error") == [],
            w2.events(bare, session=s.sid, kind="error"))
    w.finish(args.keep)


if __name__ == "__main__":
    main()
